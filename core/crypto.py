# -*- coding: utf-8 -*-
"""加密/解密引擎 — 纯函数，无 UI 依赖"""

import os
import base64
import hashlib

HAS_CRYPTO = False
try:
    from Crypto.Cipher import AES, DES, DES3, Blowfish, ChaCha20, ARC4
    from Crypto.Util.Padding import pad, unpad
    from Crypto.Random import get_random_bytes
    HAS_CRYPTO = True
except ImportError:
    try:
        from Cryptodome.Cipher import AES, DES, DES3, Blowfish, ChaCha20, ARC4
        from Cryptodome.Util.Padding import pad, unpad
        from Cryptodome.Random import get_random_bytes
        HAS_CRYPTO = True
    except ImportError:
        pass

# ── 算法 → 可用模式 映射 ─────────────────────────────────────
CIPHER_MODES = {
    "AES":      ["ECB", "CBC", "CFB", "OFB", "CTR", "GCM"],
    "DES":      ["ECB", "CBC"],
    "3DES":     ["ECB", "CBC"],
    "Blowfish": ["ECB", "CBC"],
    "ChaCha20": [],
    "RC4":      [],
    "XOR":      [],
}

CIPHER_KEY_SIZES = {
    'AES': 32, 'DES': 8, '3DES': 24, 'Blowfish': 16,
    'ChaCha20': 32, 'RC4': 16, 'XOR': 16,
}

# 显示名 → 内部算法名
DISPLAY_NAMES = ["AES", "DES", "3DES (Triple DES)", "Blowfish",
                 "ChaCha20", "RC4", "XOR"]
ALGO_KEY_MAP = {"3DES (Triple DES)": "3DES"}


def _rand(n):
    return get_random_bytes(n) if HAS_CRYPTO else os.urandom(n)


# ── 密钥 / IV 准备 ──────────────────────────────────────────
def prepare_key(key_text: str, key_format: str, algo: str) -> bytes:
    if not key_text:
        raise ValueError("密钥不能为空")
    key_bytes = (bytes.fromhex(key_text.replace(' ', ''))
                 if key_format == 'hex' else key_text.encode('utf-8'))

    if algo == 'AES':
        klen = len(key_bytes)
        target = 16 if klen <= 16 else (24 if klen <= 24 else 32)
        if klen < target:
            key_bytes = key_bytes.ljust(target, b'\x00')
        elif klen > target:
            key_bytes = hashlib.sha256(key_bytes).digest()[:target]
    elif algo == 'DES':
        if len(key_bytes) != 8:
            key_bytes = hashlib.sha256(key_bytes).digest()[:8]
    elif algo == '3DES':
        if len(key_bytes) < 24:
            key_bytes = hashlib.sha256(key_bytes).digest()[:24]
        else:
            key_bytes = key_bytes[:24]
    elif algo == 'Blowfish':
        if len(key_bytes) < 4:
            key_bytes = key_bytes.ljust(4, b'\x00')
        elif len(key_bytes) > 56:
            key_bytes = hashlib.sha256(key_bytes).digest()
    elif algo == 'ChaCha20':
        if len(key_bytes) != 32:
            key_bytes = hashlib.sha256(key_bytes).digest()
    return key_bytes


def prepare_iv(iv_text: str, key_format: str, size: int) -> bytes:
    if not iv_text:
        return _rand(size)
    iv_bytes = (bytes.fromhex(iv_text.replace(' ', ''))
                if key_format == 'hex' else iv_text.encode('utf-8'))
    if len(iv_bytes) < size:
        iv_bytes = iv_bytes.ljust(size, b'\x00')
    elif len(iv_bytes) > size:
        iv_bytes = iv_bytes[:size]
    return iv_bytes


def format_bytes(data: bytes, fmt: str) -> str:
    return data.hex() if fmt == 'hex' else base64.b64encode(data).decode('ascii')


def parse_bytes(text: str, fmt: str) -> bytes:
    text = text.strip()
    return bytes.fromhex(text.replace(' ', '')) if fmt == 'hex' else base64.b64decode(text)


def safe_bytes_to_str(data: bytes) -> str:
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return f"[无法解码为 UTF-8，共 {len(data)} 字节]\nHex: {data.hex()}"


# ── 分组密码通用加密 / 解密 ──────────────────────────────────
def _block_encrypt(cm, data, key, iv_text, kf, mode, of):
    bs = cm.block_size
    if mode == 'ECB':
        ct = cm.new(key, cm.MODE_ECB).encrypt(pad(data, bs))
    elif mode in ('CBC', 'CFB', 'OFB'):
        iv = prepare_iv(iv_text, kf, bs)
        mc = getattr(cm, f'MODE_{mode}')
        cipher = cm.new(key, mc, iv=iv)
        enc = cipher.encrypt(pad(data, bs) if mode == 'CBC' else data)
        ct = iv + enc
    elif mode == 'CTR':
        cipher = cm.new(key, cm.MODE_CTR)
        ct = cipher.nonce + cipher.encrypt(data)
    elif mode == 'GCM':
        nonce = prepare_iv(iv_text, kf, 12) if iv_text else _rand(12)
        cipher = cm.new(key, cm.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(data)
        ct = nonce + tag + ciphertext
    else:
        raise ValueError(f"不支持的模式: {mode}")
    return format_bytes(ct, of)


def _block_decrypt(cm, raw, key, iv_text, kf, mode):
    bs = cm.block_size
    if mode == 'ECB':
        pt = unpad(cm.new(key, cm.MODE_ECB).decrypt(raw), bs)
    elif mode in ('CBC', 'CFB', 'OFB'):
        if iv_text:
            iv = prepare_iv(iv_text, kf, bs)
            enc = raw
        else:
            iv, enc = raw[:bs], raw[bs:]
        mc = getattr(cm, f'MODE_{mode}')
        cipher = cm.new(key, mc, iv=iv)
        pt = unpad(cipher.decrypt(enc), bs) if mode == 'CBC' else cipher.decrypt(enc)
    elif mode == 'CTR':
        ns = bs // 2
        cipher = cm.new(key, cm.MODE_CTR, nonce=raw[:ns])
        pt = cipher.decrypt(raw[ns:])
    elif mode == 'GCM':
        nonce, tag, enc = raw[:12], raw[12:28], raw[28:]
        cipher = cm.new(key, cm.MODE_GCM, nonce=nonce)
        pt = cipher.decrypt_and_verify(enc, tag)
    else:
        raise ValueError(f"不支持的模式: {mode}")
    return pt


_CIPHER_MAP = {}  # 延迟填充，避免未安装时 NameError

def _get_cipher_mod(algo):
    global _CIPHER_MAP
    if not _CIPHER_MAP and HAS_CRYPTO:
        _CIPHER_MAP = {'AES': AES, 'DES': DES, '3DES': DES3, 'Blowfish': Blowfish}
    return _CIPHER_MAP.get(algo)


# ── 统一入口 ─────────────────────────────────────────────────
def do_encrypt(algo, plaintext, key, iv, mode, key_fmt, out_fmt):
    if not HAS_CRYPTO and algo != 'XOR':
        raise RuntimeError("加密功能需要安装 pycryptodome:\npip install pycryptodome")
    data = plaintext.encode('utf-8')
    key_bytes = prepare_key(key, key_fmt, algo)

    cm = _get_cipher_mod(algo)
    if cm:
        return _block_encrypt(cm, data, key_bytes, iv, key_fmt, mode, out_fmt)
    if algo == 'ChaCha20':
        cipher = ChaCha20.new(key=key_bytes)
        return format_bytes(cipher.nonce + cipher.encrypt(data), out_fmt)
    if algo == 'RC4':
        return format_bytes(ARC4.new(key_bytes).encrypt(data), out_fmt)
    if algo == 'XOR':
        xk = (bytes.fromhex(key.replace(' ', '')) if key_fmt == 'hex'
              else key.encode('utf-8'))
        if not xk:
            raise ValueError("XOR 密钥不能为空")
        return format_bytes(bytes(b ^ xk[i % len(xk)] for i, b in enumerate(data)), out_fmt)
    raise ValueError(f"不支持的算法: {algo}")


def do_decrypt(algo, ciphertext, key, iv, mode, key_fmt, in_fmt):
    if not HAS_CRYPTO and algo != 'XOR':
        raise RuntimeError("解密功能需要安装 pycryptodome:\npip install pycryptodome")
    raw = parse_bytes(ciphertext, in_fmt)
    key_bytes = prepare_key(key, key_fmt, algo)

    cm = _get_cipher_mod(algo)
    if cm:
        return safe_bytes_to_str(_block_decrypt(cm, raw, key_bytes, iv, key_fmt, mode))
    if algo == 'ChaCha20':
        cipher = ChaCha20.new(key=key_bytes, nonce=raw[:8])
        pt = cipher.decrypt(raw[8:])
    elif algo == 'RC4':
        pt = ARC4.new(key_bytes).decrypt(raw)
    elif algo == 'XOR':
        xk = (bytes.fromhex(key.replace(' ', '')) if key_fmt == 'hex'
              else key.encode('utf-8'))
        if not xk:
            raise ValueError("XOR 密钥不能为空")
        pt = bytes(b ^ xk[i % len(xk)] for i, b in enumerate(raw))
    else:
        raise ValueError(f"不支持的算法: {algo}")
    return safe_bytes_to_str(pt)
