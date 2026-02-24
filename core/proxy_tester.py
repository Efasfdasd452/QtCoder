# -*- coding: utf-8 -*-
"""代理测试引擎 — 双引擎：aiohttp 异步 + nmap 精准

两套引擎各有侧重:

  aiohttp 引擎
    - 真实发出 HTTP/HTTPS 请求，获取状态码、响应大小、Server 头等
    - 异步并发，大批量 URL 测速极快
    - 支持 HTTP / SOCKS4 / SOCKS5 代理

  nmap 引擎
    - TCP 端口连通性检测，精确区分 open / filtered / closed
    - 支持 HTTP CONNECT 代理 和 SOCKS4 代理
    - 注意: nmap --proxies 不支持 SOCKS5
"""

import asyncio
import subprocess
import shutil
import time
import ssl as _ssl
import xml.etree.ElementTree as ET

import aiohttp
from aiohttp_socks import ProxyConnector

from core.nmap_finder import get_nmap_exe, is_nmap_available   # noqa: F401


# ══════════════════════════════════════════════════════════════
#  通用工具
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
#  aiohttp 引擎 — 异步 URL 批量测试
# ══════════════════════════════════════════════════════════════

def build_proxy_url(proxy_type, host, port, username='', password=''):
    """构建 aiohttp/aiohttp_socks 代理 URL。

    返回 None 表示直连，返回字符串用于 ProxyConnector.from_url()。
    """
    if not proxy_type or proxy_type == '无代理':
        return None
    scheme = {
        'HTTP':   'http',
        'HTTPS':  'http',
        'SOCKS5': 'socks5',
        'SOCKS4': 'socks4',
    }.get(proxy_type.upper(), 'http')

    host = host.strip()
    if not host:
        raise ValueError("代理地址不能为空")

    auth = ''
    if username:
        auth = f"{username}:{password}@" if password else f"{username}@"

    return f"{scheme}://{auth}{host}:{port}"


async def _test_single_url(session, url, timeout):
    """测试单个 URL，返回结果字典。"""
    start = time.monotonic()
    try:
        ssl_ctx = _ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = _ssl.CERT_NONE

        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            ssl=ssl_ctx,
            allow_redirects=True,
        ) as resp:
            elapsed = time.monotonic() - start
            body = await resp.read()
            return {
                'url':          url,
                'status':       resp.status,
                'reason':       resp.reason or '',
                'time_ms':      round(elapsed * 1000),
                'size':         len(body),
                'content_type': resp.headers.get('Content-Type', ''),
                'server':       resp.headers.get('Server', ''),
                'error':        '',
                'ok':           True,
            }
    except asyncio.CancelledError:
        raise
    except aiohttp.ClientConnectorError as e:
        elapsed = time.monotonic() - start
        return _url_err(url, elapsed, f"连接失败: {e}")
    except aiohttp.ClientProxyConnectionError as e:
        elapsed = time.monotonic() - start
        return _url_err(url, elapsed, f"代理连接失败: {e}")
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start
        return _url_err(url, elapsed, "超时")
    except Exception as e:
        elapsed = time.monotonic() - start
        return _url_err(url, elapsed, f"{type(e).__name__}: {e}")


async def batch_test(urls, proxy_url=None, timeout=10,
                     concurrency=10, stop_event=None,
                     on_result=None, on_progress=None):
    """异步并发批量测试 URL。

    Args:
        urls:        URL 列表
        proxy_url:   代理 URL (None = 直连)；由 build_proxy_url() 生成
        timeout:     单个请求超时(秒)
        concurrency: 并发数
        stop_event:  asyncio.Event，set 时停止
        on_result:   回调 fn(result_dict)
        on_progress: 回调 fn(done, total)
    """
    connector = ProxyConnector.from_url(proxy_url) if proxy_url else None
    sem = asyncio.Semaphore(concurrency)
    done_count = 0
    total = len(urls)
    results = []

    async def _test_one(url):
        nonlocal done_count
        if stop_event and stop_event.is_set():
            return
        async with sem:
            if stop_event and stop_event.is_set():
                return
            result = await _test_single_url(session, url, timeout)
            done_count += 1
            results.append(result)
            if on_result:
                on_result(result)
            if on_progress:
                on_progress(done_count, total)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [asyncio.create_task(_test_one(u)) for u in urls]
        await asyncio.gather(*tasks, return_exceptions=True)

    return results


def _url_err(url, elapsed, msg):
    return {
        'url': url, 'status': 0, 'reason': '',
        'time_ms': round(elapsed * 1000), 'size': 0,
        'content_type': '', 'server': '', 'error': msg, 'ok': False,
    }


# ══════════════════════════════════════════════════════════════
#  nmap 引擎 — TCP 端口连通性检测（精准）
# ══════════════════════════════════════════════════════════════

def build_nmap_proxy_url(proxy_type, host, port, username='', password=''):
    """构建 nmap --proxies 兼容的代理 URL。

    支持:
        http://[user:pass@]host:port   (HTTP CONNECT)
        socks4://host:port             (SOCKS4，nmap 不支持认证)

    SOCKS5 不被 nmap --proxies 支持，调用时抛出 ValueError。
    """
    host = host.strip()
    if not host:
        raise ValueError("代理地址不能为空")

    ptype = proxy_type.upper()
    if ptype in ('HTTP', 'HTTPS'):
        auth = ''
        if username:
            auth = f"{username}:{password}@" if password else f"{username}@"
        return f"http://{auth}{host}:{port}"
    elif ptype == 'SOCKS4':
        return f"socks4://{host}:{port}"
    elif ptype == 'SOCKS5':
        raise ValueError(
            "nmap --proxies 不支持 SOCKS5。\n"
            "端口扫描模式请改用 HTTP 或 SOCKS4 代理。"
        )
    else:
        raise ValueError(f"未知代理类型: {proxy_type}")


def _parse_nmap_xml(xml_output):
    """解析 nmap -oX 输出，返回端口结果列表。"""
    results = []
    try:
        root = ET.fromstring(xml_output)
    except ET.ParseError:
        return results
    for host_elem in root.findall('host'):
        ports_elem = host_elem.find('ports')
        if ports_elem is None:
            continue
        for port_elem in ports_elem.findall('port'):
            portid     = int(port_elem.get('portid', 0))
            state_elem = port_elem.find('state')
            if state_elem is not None:
                state  = state_elem.get('state', 'unknown')
                reason = state_elem.get('reason', '')
            else:
                state, reason = 'unknown', ''
            service_elem = port_elem.find('service')
            service = ''
            if service_elem is not None:
                service = service_elem.get('name', '')
            results.append({
                'port':    portid,
                'state':   state,
                'reason':  reason,
                'service': service,
                'open':    state == 'open',
            })
    return results


def test_proxy_via_nmap(proxy_url, target_host, ports, timing=4, timeout=60):
    """通过 nmap --proxies 测试目标端口的 TCP 可达性。

    返回: (results, cmd_str, elapsed_sec)
        results: list of {port, state, reason, service, open}
    """
    if isinstance(ports, (list, tuple)):
        port_str = ','.join(str(p) for p in ports)
    else:
        port_str = str(ports)

    nmap_exe = get_nmap_exe() or 'nmap'
    cmd = [
        nmap_exe, '-sT',
        '--proxies', proxy_url,
        '-p', port_str,
        '-oX', '-',
        f'-T{timing}',
        target_host,
    ]
    cmd_str = ' '.join(cmd)
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate(timeout=timeout)
        elapsed = time.monotonic() - start

        if proc.returncode not in (0, 1):
            err = stderr.decode('utf-8', errors='replace')
            raise RuntimeError(f"nmap 错误 (exit {proc.returncode}):\n{err}")

        return _parse_nmap_xml(stdout.decode('utf-8', errors='replace')), cmd_str, elapsed

    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError(f"nmap 超时（{timeout} 秒）")
    except FileNotFoundError:
        raise RuntimeError(
            "找不到 nmap，请先安装。\n下载: https://nmap.org/download")
