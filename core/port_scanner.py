# -*- coding: utf-8 -*-
"""端口扫描 & 服务探测引擎 — 纯函数，无 UI 依赖

探测流程:
1. TCP 连接测试（判断端口是否开放）— 可选走 SOCKS5/HTTP 代理
2. 被动 Banner 抓取（SSH / FTP / SMTP 等会主动发送欢迎信息）
3. 主动发送协议探针（HTTP / SOCKS / Redis 等需要客户端先发数据）
4. 兜底: 按知名端口号推测服务
"""

import socket
import struct
import ssl
import base64

# ══════════════════════════════════════════════════════════════
#  知名端口 / 服务 预设
# ══════════════════════════════════════════════════════════════
WELL_KNOWN_PORTS = {
    20: 'FTP-Data',   21: 'FTP',       22: 'SSH',       23: 'Telnet',
    25: 'SMTP',       53: 'DNS',       80: 'HTTP',      110: 'POP3',
    143: 'IMAP',      443: 'HTTPS',    445: 'SMB',      465: 'SMTPS',
    587: 'SMTP',      993: 'IMAPS',    995: 'POP3S',
    1080: 'SOCKS',    1433: 'MSSQL',   1521: 'Oracle',
    3128: 'HTTP-Proxy', 3306: 'MySQL', 3389: 'RDP',
    5432: 'PostgreSQL', 5900: 'VNC',   6379: 'Redis',
    8080: 'HTTP-Alt', 8443: 'HTTPS-Alt', 8888: 'HTTP-Alt',
    9090: 'HTTP-Alt', 11211: 'Memcached', 27017: 'MongoDB',
    9050: 'Tor-SOCKS', 6667: 'IRC',   5222: 'XMPP',
    2049: 'NFS',      514: 'Syslog',  161: 'SNMP',
    8081: 'HTTP-Alt', 9200: 'Elasticsearch', 5601: 'Kibana',
    2375: 'Docker',   2376: 'Docker-TLS', 8500: 'Consul',
}

COMMON_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 143, 443, 445,
    1080, 1433, 3128, 3306, 3389, 5432, 5900, 6379,
    8080, 8443, 8888, 9090, 27017,
]

# ── 服务预设 ──────────────────────────────────────────────────
SERVICE_PRESETS = {
    'common':   ('常用端口 (23个)',  COMMON_PORTS),
    'web':      ('Web 服务',        [80, 443, 8080, 8443, 8888, 9090, 3000, 5000, 8081]),
    'database': ('数据库服务',       [3306, 5432, 6379, 27017, 11211, 1433, 1521, 9200, 5601]),
    'proxy':    ('代理服务',         [1080, 3128, 8080, 8888, 9050, 9090, 7890, 7891]),
    'mail':     ('邮件服务',         [25, 110, 143, 465, 587, 993, 995]),
    'remote':   ('远程管理',         [22, 23, 3389, 5900, 2222, 5901]),
    'file':     ('文件服务',         [20, 21, 69, 445, 873, 2049]),
    'devops':   ('DevOps / 容器',    [2375, 2376, 8500, 9200, 5601, 8080, 6443]),
}

# 预设名称列表（用于 UI ComboBox）
SERVICE_PRESET_NAMES = ['自定义'] + [v[0] for v in SERVICE_PRESETS.values()]


# ══════════════════════════════════════════════════════════════
#  端口号解析
# ══════════════════════════════════════════════════════════════
def parse_ports(text):
    """解析端口字符串，支持 '80'、'80-90'、'22,80,443'、'20-25,80,443,8080-8090'"""
    ports = set()
    for part in text.replace('\uff0c', ',').replace(' ', '').split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            lo, hi = part.split('-', 1)
            lo, hi = int(lo), int(hi)
            lo, hi = min(lo, hi), max(lo, hi)
            if hi - lo > 5000:
                raise ValueError(f"端口范围过大: {lo}-{hi}（最多 5000 个端口）")
            for p in range(lo, hi + 1):
                if 1 <= p <= 65535:
                    ports.add(p)
        else:
            p = int(part)
            if 1 <= p <= 65535:
                ports.add(p)
    return sorted(ports)


def get_preset_ports(key):
    """根据预设 key 返回端口列表"""
    if key in SERVICE_PRESETS:
        return SERVICE_PRESETS[key][1]
    return COMMON_PORTS


# ══════════════════════════════════════════════════════════════
#  代理连接
# ══════════════════════════════════════════════════════════════
def _connect_via_socks5(proxy_host, proxy_port, dest_host, dest_port,
                        timeout, username=None, password=None):
    """通过 SOCKS5 代理建立到目标的 TCP 连接。返回已连接的 socket 或 None。"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((proxy_host, proxy_port))

        # ── 握手: 协商认证方式 ────────────────────────────────
        if username and password:
            sock.sendall(b'\x05\x02\x00\x02')  # NO_AUTH + USERNAME
        else:
            sock.sendall(b'\x05\x01\x00')       # NO_AUTH

        resp = sock.recv(2)
        if len(resp) < 2 or resp[0] != 0x05:
            sock.close()
            return None

        method = resp[1]
        if method == 0x02 and username and password:
            # RFC 1929 用户名/密码认证
            uname = username.encode('utf-8')
            passwd = password.encode('utf-8')
            auth = b'\x01' + bytes([len(uname)]) + uname + \
                   bytes([len(passwd)]) + passwd
            sock.sendall(auth)
            auth_resp = sock.recv(2)
            if len(auth_resp) < 2 or auth_resp[1] != 0x00:
                sock.close()
                return None
        elif method == 0xFF:
            sock.close()
            return None

        # ── CONNECT 请求 ─────────────────────────────────────
        req = b'\x05\x01\x00'  # VER, CMD=CONNECT, RSV
        try:
            addr_bytes = socket.inet_aton(dest_host)
            req += b'\x01' + addr_bytes
        except OSError:
            domain = dest_host.encode('ascii')
            req += b'\x03' + bytes([len(domain)]) + domain
        req += struct.pack('>H', dest_port)
        sock.sendall(req)

        # 读取回复（至少 10 字节）
        reply = sock.recv(32)
        if len(reply) < 2 or reply[1] != 0x00:
            sock.close()
            return None

        return sock

    except Exception:
        return None


def _connect_via_http_proxy(proxy_host, proxy_port, dest_host, dest_port,
                            timeout, username=None, password=None):
    """通过 HTTP CONNECT 代理建立到目标的 TCP 连接。"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((proxy_host, proxy_port))

        auth_hdr = ''
        if username and password:
            cred = base64.b64encode(
                f'{username}:{password}'.encode()).decode()
            auth_hdr = f'Proxy-Authorization: Basic {cred}\r\n'

        req = (
            f'CONNECT {dest_host}:{dest_port} HTTP/1.1\r\n'
            f'Host: {dest_host}:{dest_port}\r\n'
            f'{auth_hdr}\r\n'
        ).encode()
        sock.sendall(req)

        # 读取回复
        resp = b''
        while b'\r\n\r\n' not in resp and len(resp) < 4096:
            chunk = sock.recv(4096)
            if not chunk:
                break
            resp += chunk

        first_line = resp.split(b'\r\n')[0].decode('ascii', errors='replace')
        if '200' in first_line:
            return sock

        sock.close()
        return None

    except Exception:
        return None


def _connect_with_proxy(host, port, timeout, proxy=None):
    """建立到目标的 TCP 连接（可选代理）。

    proxy 格式:
        None — 直连
        {'type': 'SOCKS5'|'HTTP', 'host': str, 'port': int,
         'username': str|None, 'password': str|None}
    返回已连接的 socket 或 None。
    """
    if proxy is None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            return sock
        except Exception:
            return None

    ptype = proxy.get('type', 'SOCKS5').upper()
    phost = proxy['host']
    pport = proxy['port']
    puser = proxy.get('username')
    ppass = proxy.get('password')

    if ptype == 'SOCKS5':
        return _connect_via_socks5(
            phost, pport, host, port, timeout, puser, ppass)
    elif ptype in ('HTTP', 'HTTPS'):
        return _connect_via_http_proxy(
            phost, pport, host, port, timeout, puser, ppass)
    else:
        return None


# ══════════════════════════════════════════════════════════════
#  主入口
# ══════════════════════════════════════════════════════════════
def check_port(host, port, timeout=3.0, proxy=None):
    """检测单个端口是否开放并探测服务。

    proxy: 同 _connect_with_proxy 参数。
    返回 dict: host, port, open, service, banner, detail
    """
    result = {
        'host': host, 'port': port,
        'open': False, 'service': '', 'banner': '', 'detail': '',
    }

    # 1) TCP 连接 + Banner 抓取
    banner_bytes = _connect_and_grab(host, port, timeout, proxy)
    if banner_bytes is None:
        return result
    result['open'] = True

    # 2) 分析 Banner
    if banner_bytes:
        result['banner'] = _safe_decode(banner_bytes)
        svc = _identify_from_banner(banner_bytes)
        if svc:
            result['service'] = svc
            return result

    # 3) 主动探针
    probes = _ordered_probes(port)
    for probe_fn in probes:
        svc, detail = probe_fn(host, port, timeout, proxy)
        if svc:
            result['service'] = svc
            if detail:
                result['detail'] = detail
            return result

    # 4) 兜底
    if port in WELL_KNOWN_PORTS:
        result['service'] = f"{WELL_KNOWN_PORTS[port]}（推测）"
    else:
        result['service'] = "未知服务"

    return result


# ══════════════════════════════════════════════════════════════
#  Raw TCP 探测（自定义服务）
# ══════════════════════════════════════════════════════════════
def raw_tcp_probe(host, port, send_data=b'', timeout=5.0, proxy=None):
    """手动 TCP 探测: 连接 → 可选发送数据 → 读取响应。

    send_data: bytes，要发送的原始数据
    返回 dict: connected, sent, recv_bytes, recv_text, error
    """
    result = {
        'connected': False,
        'sent': len(send_data),
        'recv_bytes': b'',
        'recv_hex': '',
        'recv_text': '',
        'error': '',
    }

    sock = _connect_with_proxy(host, port, timeout, proxy)
    if sock is None:
        result['error'] = '连接失败（端口可能未开放或代理不可用）'
        return result
    result['connected'] = True

    try:
        if send_data:
            sock.sendall(send_data)

        sock.settimeout(min(timeout, 3.0))
        chunks = []
        total = 0
        try:
            while total < 65536:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
                total += len(data)
        except socket.timeout:
            pass

        recv = b''.join(chunks)
        result['recv_bytes'] = recv
        result['recv_hex'] = recv.hex(' ') if recv else ''
        result['recv_text'] = _safe_decode(recv) if recv else '（无响应数据）'

    except Exception as e:
        result['error'] = str(e)
    finally:
        sock.close()

    return result


# ══════════════════════════════════════════════════════════════
#  连接 & Banner
# ══════════════════════════════════════════════════════════════
def _connect_and_grab(host, port, timeout, proxy=None):
    """连接并尝试读取 Banner。成功返回 bytes（可能为空），失败返回 None。"""
    sock = _connect_with_proxy(host, port, timeout, proxy)
    if sock is None:
        return None

    try:
        sock.settimeout(min(timeout, 2.0))
        data = sock.recv(4096)
    except socket.timeout:
        data = b''
    except OSError:
        data = b''
    finally:
        sock.close()
    return data


# ══════════════════════════════════════════════════════════════
#  Banner 识别
# ══════════════════════════════════════════════════════════════
def _identify_from_banner(data):
    """从被动接收的 Banner 识别服务。"""
    if not data:
        return ''
    text = _safe_decode(data)
    upper = text.upper()

    if data[:4] == b'SSH-':
        return f"SSH ({text.strip()})"
    if upper.startswith('220') and ('FTP' in upper or 'FILEZILLA' in upper
                                    or 'VSFTPD' in upper or 'PROFTP' in upper):
        return f"FTP ({text.strip().splitlines()[0]})"
    if upper.startswith('220') and ('SMTP' in upper or 'ESMTP' in upper
                                    or 'POSTFIX' in upper or 'MAIL' in upper):
        return f"SMTP ({text.strip().splitlines()[0]})"
    if upper.startswith('+OK') and ('POP' in upper or 'READY' in upper
                                    or 'DOVECOT' in upper):
        return f"POP3 ({text.strip().splitlines()[0]})"
    if upper.startswith('* OK') and ('IMAP' in upper or 'DOVECOT' in upper):
        return f"IMAP ({text.strip().splitlines()[0]})"
    if len(data) > 5 and data[4] == 0x0a:
        try:
            ver_end = data.index(b'\x00', 5)
            version = data[5:ver_end].decode('ascii', errors='replace')
            return f"MySQL ({version})"
        except (ValueError, IndexError):
            pass
    if data.startswith(b'-') and b'DENIED' in data.upper():
        return "Redis（需要认证）"
    if data.startswith(b'-ERR') or data.startswith(b'-NOAUTH'):
        return "Redis（需要认证）"
    if b'ERROR' in data[:20]:
        return "Memcached（可能）"
    if upper.startswith('220'):
        return f"服务 Banner: {text.strip().splitlines()[0]}"

    return ''


# ══════════════════════════════════════════════════════════════
#  主动探针
# ══════════════════════════════════════════════════════════════
def _probe_socket(host, port, timeout, send_data, recv_size=4096, proxy=None):
    """建立连接、发送数据、读取响应。返回 bytes 或 None。"""
    sock = _connect_with_proxy(host, port, timeout, proxy)
    if sock is None:
        return None
    try:
        sock.sendall(send_data)
        sock.settimeout(min(timeout, 2.0))
        resp = sock.recv(recv_size)
        return resp
    except Exception:
        return None
    finally:
        sock.close()


def _probe_http(host, port, timeout, proxy=None):
    req = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"User-Agent: QtCoder-PortScanner/1.0\r\n"
        f"Connection: close\r\n\r\n"
    ).encode()
    resp = _probe_socket(host, port, timeout, req, proxy=proxy)
    if resp and resp[:5] in (b'HTTP/', b'http/'):
        text = _safe_decode(resp)
        first_line = text.splitlines()[0] if text else ''
        if '407' in first_line or 'proxy' in text.lower()[:500]:
            return "HTTP 代理", first_line
        server = _extract_header(text, 'Server')
        status = first_line.strip()
        detail = f"{status}"
        if server:
            detail += f" | Server: {server}"
        return "HTTP", detail
    return '', ''


def _probe_https(host, port, timeout, proxy=None):
    # HTTPS 通过代理时需要先建立隧道再做 TLS
    try:
        sock = _connect_with_proxy(host, port, timeout, proxy)
        if sock is None:
            return '', ''
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ss = ctx.wrap_socket(sock, server_hostname=host)
        cipher = ss.cipher()
        ss.sendall(
            f"GET / HTTP/1.1\r\nHost: {host}\r\n"
            f"Connection: close\r\n\r\n".encode()
        )
        ss.settimeout(2)
        resp = b''
        try:
            resp = ss.recv(4096)
        except Exception:
            pass
        ss.close()

        detail = ''
        if cipher:
            detail = f"TLS {cipher[1]} | {cipher[0]}"
        if resp and resp[:5] == b'HTTP/':
            text = _safe_decode(resp)
            server = _extract_header(text, 'Server')
            if server:
                detail += f" | Server: {server}"
            return "HTTPS", detail
        return "TLS/SSL", detail
    except ssl.SSLError:
        return '', ''
    except Exception:
        return '', ''


def _probe_socks5(host, port, timeout, proxy=None):
    resp = _probe_socket(host, port, timeout, b'\x05\x01\x00', proxy=proxy)
    if resp and len(resp) >= 2 and resp[0] == 0x05:
        if resp[1] == 0x00:
            return "SOCKS5 代理", "无需认证"
        elif resp[1] == 0x02:
            return "SOCKS5 代理", "需要用户名/密码认证"
        elif resp[1] == 0xFF:
            return "SOCKS5 代理", "无可接受的认证方式"
        return "SOCKS5 代理", ""
    return '', ''


def _probe_socks4(host, port, timeout, proxy=None):
    payload = b'\x04\x01' + struct.pack('>H', 80) + \
              b'\x01\x01\x01\x01' + b'\x00'
    resp = _probe_socket(host, port, timeout, payload, proxy=proxy)
    if resp and len(resp) >= 2 and resp[0] == 0x00 and resp[1] == 0x5a:
        return "SOCKS4 代理", "连接允许"
    if resp and len(resp) >= 2 and resp[0] == 0x00 and resp[1] == 0x5b:
        return "SOCKS4 代理", "连接被拒绝"
    return '', ''


def _probe_http_proxy(host, port, timeout, proxy=None):
    req = (
        "CONNECT www.google.com:443 HTTP/1.1\r\n"
        f"Host: www.google.com:443\r\n"
        "User-Agent: QtCoder/1.0\r\n\r\n"
    ).encode()
    resp = _probe_socket(host, port, timeout, req, proxy=proxy)
    if resp and resp[:5] in (b'HTTP/', b'http/'):
        text = _safe_decode(resp)
        first_line = text.splitlines()[0].strip() if text else ''
        if '200' in first_line:
            return "HTTP 代理 (CONNECT)", first_line
        elif '407' in first_line:
            return "HTTP 代理 (需认证)", first_line
        elif '403' in first_line or '405' in first_line:
            return "HTTP 代理 (受限)", first_line
    return '', ''


def _probe_redis(host, port, timeout, proxy=None):
    resp = _probe_socket(host, port, timeout, b"PING\r\n", proxy=proxy)
    if resp:
        text = _safe_decode(resp).strip()
        if text.startswith('+PONG'):
            return "Redis", "无密码 (PING -> PONG)"
        if 'NOAUTH' in text.upper() or 'DENIED' in text.upper():
            return "Redis", "需要密码认证"
    return '', ''


def _probe_mysql(host, port, timeout, proxy=None):
    data = _connect_and_grab(host, port, min(timeout, 2), proxy)
    if data and len(data) > 5 and data[4] == 0x0a:
        try:
            ver_end = data.index(b'\x00', 5)
            version = data[5:ver_end].decode('ascii', errors='replace')
            return "MySQL", version
        except Exception:
            return "MySQL", ""
    return '', ''


def _probe_postgresql(host, port, timeout, proxy=None):
    payload = struct.pack('>I', 8) + struct.pack('>I', 80877103)
    resp = _probe_socket(host, port, timeout, payload, proxy=proxy)
    if resp and len(resp) >= 1:
        if resp[0:1] == b'N':
            return "PostgreSQL", "不支持 SSL"
        elif resp[0:1] == b'S':
            return "PostgreSQL", "支持 SSL"
    return '', ''


# ── 探针优先级 ────────────────────────────────────────────────
def _ordered_probes(port):
    all_probes = [
        _probe_http, _probe_socks5, _probe_redis,
        _probe_http_proxy, _probe_socks4, _probe_https,
        _probe_mysql, _probe_postgresql,
    ]
    priority = {
        80:    [_probe_http],
        443:   [_probe_https, _probe_http],
        8443:  [_probe_https, _probe_http],
        1080:  [_probe_socks5, _probe_socks4, _probe_http_proxy],
        3128:  [_probe_http_proxy, _probe_http, _probe_socks5],
        8080:  [_probe_http, _probe_http_proxy, _probe_socks5],
        8888:  [_probe_http, _probe_http_proxy, _probe_socks5],
        9090:  [_probe_http, _probe_http_proxy],
        9050:  [_probe_socks5, _probe_socks4],
        6379:  [_probe_redis],
        3306:  [_probe_mysql],
        5432:  [_probe_postgresql],
    }
    if port in priority:
        first = priority[port]
        rest = [p for p in all_probes if p not in first]
        return first + rest
    return all_probes


# ══════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════
def _safe_decode(data):
    for enc in ('utf-8', 'gbk', 'latin-1'):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return repr(data)


def _extract_header(http_text, header_name):
    for line in http_text.splitlines():
        if line.lower().startswith(header_name.lower() + ':'):
            return line.split(':', 1)[1].strip()
    return ''
