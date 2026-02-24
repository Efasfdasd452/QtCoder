# -*- coding: utf-8 -*-
"""PGP 分离签名验证工具

典型用途：
    下载 nmap-7.92.exe + nmap-7.92.exe.asc，
    配合官方公钥验证安装包未被篡改。

依赖: pgpy==0.6.0  (pip install pgpy)
"""

from __future__ import annotations

import hashlib
import urllib.request
import urllib.parse

# Z-Base-32 字母表（WKD 协议使用）
_ZBASE32 = 'ybndrfg8ejkmcpqxot1uwisza345h769'


def _zbase32_encode(data: bytes) -> str:
    """Z-Base-32 编码（RFC 6189 变体，WKD 使用 SHA-1 摘要定位公钥）。"""
    result = []
    acc = bits = 0
    for byte in data:
        acc = (acc << 8) | byte
        bits += 8
        while bits >= 5:
            bits -= 5
            result.append(_ZBASE32[(acc >> bits) & 0x1F])
    if bits:
        result.append(_ZBASE32[(acc << (5 - bits)) & 0x1F])
    return ''.join(result)


def fetch_key_wkd(email: str) -> bytes:
    """通过 Web Key Directory (WKD) 协议获取 OpenPGP 公钥。

    按 RFC 9637：先尝试 Advanced 方法，再尝试 Direct 方法。
    返回二进制 OpenPGP 格式数据（pgpy.PGPKey.from_blob 可直接加载）。
    失败时抛出 ConnectionError / ValueError。

    用法示例（Tor Browser）：
        data = fetch_key_wkd('torbrowser@torproject.org')
    """
    email = email.strip()
    if '@' not in email:
        raise ValueError(f"无效邮箱地址: {email}")
    localpart, domain = email.rsplit('@', 1)
    domain = domain.lower()
    z32hash = _zbase32_encode(hashlib.sha1(localpart.lower().encode()).digest())
    l_enc   = urllib.parse.quote(localpart.lower())

    urls = [
        # Advanced method（优先）
        f"https://openpgpkey.{domain}/.well-known/openpgpkey/{domain}/hu/{z32hash}?l={l_enc}",
        # Direct method（备用）
        f"https://{domain}/.well-known/openpgpkey/hu/{z32hash}?l={l_enc}",
    ]
    last_err = None
    for url in urls:
        try:
            req = urllib.request.Request(
                url, headers={'User-Agent': 'QtCoder-PGP/1.0'})
            with urllib.request.urlopen(req, timeout=12) as resp:
                return resp.read()
        except Exception as e:
            last_err = e
    raise ConnectionError(f"WKD 获取失败 ({email}): {last_err}")


def fetch_key_keyserver(query: str) -> str:
    """从 keys.openpgp.org 通过指纹、Key ID 或邮箱获取公钥（返回 Armored 文本）。

    query 可以是：
      - 完整指纹（40 位十六进制，可带 0x 前缀）
      - 短 Key ID（16 位十六进制，可带 0x 前缀）
      - 邮箱地址
    """
    query = query.strip()
    if '@' in query:
        url = (f"https://keys.openpgp.org/vks/v1/by-email/"
               f"{urllib.parse.quote(query)}")
    else:
        fp = query.upper().replace(' ', '')
        if fp.startswith('0X'):
            fp = fp[2:]
        endpoint = 'by-keyid' if len(fp) == 16 else 'by-fingerprint'
        url = f"https://keys.openpgp.org/vks/v1/{endpoint}/{fp}"

    req = urllib.request.Request(
        url, headers={
            'Accept': 'application/pgp-keys',
            'User-Agent': 'QtCoder-PGP/1.0',
        })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode('utf-8', errors='replace')


def _load(cls, source: str | bytes, is_file: bool):
    """统一加载 PGPKey / PGPSignature，兼容返回 tuple 或单对象两种情况。"""
    result = cls.from_file(source) if is_file else cls.from_blob(
        source if isinstance(source, (bytes, bytearray))
        else source.strip()
    )
    return result[0] if isinstance(result, tuple) else result


def _fmt_fingerprint(fp_str: str) -> str:
    """格式化指纹：每 4 个字符一组，中间用双空格分隔。"""
    s = fp_str.upper()
    groups = [s[i:i+4] for i in range(0, len(s), 4)]
    mid = len(groups) // 2
    return ' '.join(groups[:mid]) + '  ' + ' '.join(groups[mid:])


def _algo_name(enum_val) -> str:
    """将 pgpy 枚举值转为可读名称。"""
    try:
        return enum_val.name
    except AttributeError:
        return str(enum_val)


def peek_signature(sig_source: str | bytes,
                   sig_is_file: bool = True) -> dict:
    """仅解析签名文件，返回签名者 Key ID / 时间 / 算法，不做验证。
    失败时 key_id 为空字符串。
    """
    try:
        import pgpy
    except ImportError:
        return {'key_id': '', 'created': '', 'hash_algo': ''}
    try:
        sig = _load(pgpy.PGPSignature, sig_source, sig_is_file)
        created_str = (sig.created.strftime('%Y-%m-%d %H:%M:%S UTC')
                       if sig.created else '')
        return {
            'key_id':    sig.signer or '',
            'created':   created_str,
            'hash_algo': _algo_name(sig.hash_algorithm),
        }
    except Exception:
        return {'key_id': '', 'created': '', 'hash_algo': ''}


def verify_pgp_detached(
    file_path: str,
    sig_source: str | bytes,
    pubkey_source: str | bytes,
    sig_is_file: bool = True,
    pubkey_is_file: bool = True,
) -> dict:
    """验证文件的 PGP 分离签名。

    Args:
        file_path:      待验证文件的完整路径
        sig_source:     签名文件路径 或 armor 文本
        pubkey_source:  公钥文件路径 或 armor 文本
        sig_is_file:    True = sig_source 是文件路径
        pubkey_is_file: True = pubkey_source 是文件路径

    Returns dict:
        valid      : bool        有效 / 无效
        message    : str         中文说明
        fingerprint: str         格式化的完整指纹
        key_id     : str         短 Key ID（最后16位十六进制）
        sig_time   : str         签名时间（UTC）
        user_ids   : list[str]   公钥绑定的用户 UID
        hash_algo  : str         哈希算法（如 SHA512）
        key_algo   : str         密钥算法（如 RSAEncryptOrSign）
        sig_key_id : str         签名文件声明的 Key ID（用于排查不匹配问题）
    """
    try:
        import pgpy
        from pgpy.errors import PGPError
    except ImportError:
        raise ImportError("请先安装 pgpy：pip install pgpy")

    # ── 加载公钥 ─────────────────────────────────────────
    pub_key = _load(pgpy.PGPKey, pubkey_source, pubkey_is_file)

    # ── 加载签名 ─────────────────────────────────────────
    sig = _load(pgpy.PGPSignature, sig_source, sig_is_file)

    # ── 提取签名元信息 ────────────────────────────────────
    sig_key_id  = sig.signer or ''
    sig_time    = (sig.created.strftime('%Y-%m-%d %H:%M:%S UTC')
                   if sig.created else '')
    hash_algo   = _algo_name(sig.hash_algorithm)

    # ── 提取公钥元信息 ────────────────────────────────────
    fp_str     = str(pub_key.fingerprint)
    fingerprint = _fmt_fingerprint(fp_str)
    key_id      = fp_str[-16:] if len(fp_str) >= 16 else fp_str
    key_algo    = _algo_name(pub_key.key_algorithm)

    user_ids = []
    for uid in pub_key.userids:
        try:
            name  = uid.name  or ''
            email = uid.email or ''
            user_ids.append(f"{name} <{email}>" if email else name)
        except Exception:
            pass

    # ── 读取文件 ─────────────────────────────────────────
    with open(file_path, 'rb') as f:
        file_data = f.read()

    # ── 验证 ─────────────────────────────────────────────
    try:
        verification = pub_key.verify(file_data, sig)
        valid = bool(verification)
        if valid:
            message = '签名验证通过 ✓  文件完整，未被篡改'
        else:
            message = '签名验证失败 ✗  文件内容与签名不符'
    except PGPError as e:
        err_str = str(e)
        if 'No signatures to verify' in err_str:
            message = (
                f'密钥不匹配 ✗\n'
                f'签名文件对应 Key ID: 0x{sig_key_id}\n'
                f'提供的公钥  Key ID: 0x{key_id}\n'
                f'请使用正确的公钥文件重试'
            )
        else:
            message = f'验证出错：{err_str}'
        valid = False

    return {
        'valid':       valid,
        'message':     message,
        'fingerprint': fingerprint,
        'key_id':      key_id,
        'sig_time':    sig_time,
        'user_ids':    user_ids,
        'hash_algo':   hash_algo,
        'key_algo':    key_algo,
        'sig_key_id':  sig_key_id,
    }
