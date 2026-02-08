# -*- coding: utf-8 -*-
"""哈希/摘要引擎 — 纯函数，无 UI 依赖"""

import hashlib
import hmac as hmac_module
import zlib

HASH_METHODS = [
    "MD5", "SHA-1", "SHA-224", "SHA-256", "SHA-384", "SHA-512",
    "SHA3-256", "SHA3-512", "BLAKE2b", "BLAKE2s",
    "CRC32", "Adler32",
    "HMAC-MD5", "HMAC-SHA256", "HMAC-SHA512",
]

_HASHLIB_MAP = {
    'MD5':      hashlib.md5,
    'SHA-1':    hashlib.sha1,
    'SHA-224':  hashlib.sha224,
    'SHA-256':  hashlib.sha256,
    'SHA-384':  hashlib.sha384,
    'SHA-512':  hashlib.sha512,
    'SHA3-256': hashlib.sha3_256,
    'SHA3-512': hashlib.sha3_512,
    'BLAKE2b':  hashlib.blake2b,
    'BLAKE2s':  hashlib.blake2s,
}

_HMAC_MAP = {
    'HMAC-MD5':    hashlib.md5,
    'HMAC-SHA256': hashlib.sha256,
    'HMAC-SHA512': hashlib.sha512,
}


def do_hash(method: str, text: str, hmac_key: str = '') -> str:
    """计算哈希摘要，HMAC 类方法需要提供 hmac_key"""
    data = text.encode('utf-8')

    if method in _HASHLIB_MAP:
        return _HASHLIB_MAP[method](data).hexdigest()

    if method == 'CRC32':
        return format(zlib.crc32(data) & 0xFFFFFFFF, '08x')
    if method == 'Adler32':
        return format(zlib.adler32(data) & 0xFFFFFFFF, '08x')

    if method in _HMAC_MAP:
        if not hmac_key:
            raise ValueError("HMAC 需要提供密钥")
        return hmac_module.new(
            hmac_key.encode('utf-8'), data, _HMAC_MAP[method]
        ).hexdigest()

    raise ValueError(f"不支持的哈希算法: {method}")
