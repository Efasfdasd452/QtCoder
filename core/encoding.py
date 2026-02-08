# -*- coding: utf-8 -*-
"""编码/解码引擎 — 纯函数，无 UI 依赖"""

import base64
import codecs
import html as html_lib
import json
import quopri
import urllib.parse

# ── 摩尔斯电码表 ──────────────────────────────────────────────
MORSE_TABLE = {
    'A': '.-',    'B': '-...',  'C': '-.-.',  'D': '-..',   'E': '.',
    'F': '..-.',  'G': '--.',   'H': '....',  'I': '..',    'J': '.---',
    'K': '-.-',   'L': '.-..',  'M': '--',    'N': '-.',    'O': '---',
    'P': '.--.',  'Q': '--.-',  'R': '.-.',   'S': '...',   'T': '-',
    'U': '..-',   'V': '...-',  'W': '.--',   'X': '-..-',  'Y': '-.--',
    'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
    '.': '.-.-.-',   ',': '--..--',  '?': '..--..',  "'": '.----.',
    '!': '-.-.--',   '/': '-..-.',   '(': '-.--.',   ')': '-.--.-',
    '&': '.-...',    ':': '---...',  ';': '-.-.-.',  '=': '-...-',
    '+': '.-.-.',    '-': '-....-',  '_': '..--.-',  '"': '.-..-.',
    '$': '...-..-',  '@': '.--.-.',  ' ': '/',
}
MORSE_REVERSE = {v: k for k, v in MORSE_TABLE.items()}


# ── 编码/解码函数 ────────────────────────────────────────────
def enc_base64(text):
    return base64.b64encode(text.encode('utf-8')).decode('ascii')

def dec_base64(text):
    return base64.b64decode(text.strip()).decode('utf-8')

def enc_base32(text):
    return base64.b32encode(text.encode('utf-8')).decode('ascii')

def dec_base32(text):
    return base64.b32decode(text.strip()).decode('utf-8')

def enc_hex(text):
    return text.encode('utf-8').hex()

def dec_hex(text):
    return bytes.fromhex(text.strip().replace(' ', '')).decode('utf-8')

def enc_base85(text):
    return base64.b85encode(text.encode('utf-8')).decode('ascii')

def dec_base85(text):
    return base64.b85decode(text.strip()).decode('utf-8')

def enc_url(text):
    return urllib.parse.quote(text, safe='')

def dec_url(text):
    return urllib.parse.unquote(text)

def enc_html(text):
    return html_lib.escape(text, quote=True)

def dec_html(text):
    return html_lib.unescape(text)

def enc_unicode_escape(text):
    return text.encode('unicode_escape').decode('ascii')

def dec_unicode_escape(text):
    return text.encode('raw_unicode_escape').decode('unicode_escape')

def enc_quoted_printable(text):
    return quopri.encodestring(text.encode('utf-8')).decode('ascii')

def dec_quoted_printable(text):
    return quopri.decodestring(text.encode('ascii')).decode('utf-8')

def enc_rot13(text):
    return codecs.encode(text, 'rot_13')

def dec_rot13(text):
    return codecs.encode(text, 'rot_13')

def enc_morse(text):
    result = []
    for ch in text.upper():
        if ch in MORSE_TABLE:
            result.append(MORSE_TABLE[ch])
        else:
            result.append(ch)
    return ' '.join(result)

def dec_morse(text):
    words = text.strip().split(' / ')
    result = []
    for word in words:
        for ch in word.strip().split(' '):
            ch = ch.strip()
            if not ch:
                continue
            result.append(MORSE_REVERSE.get(ch, f'[{ch}]'))
        result.append(' ')
    return ''.join(result).strip()

def enc_binary(text):
    return ' '.join(format(b, '08b') for b in text.encode('utf-8'))

def dec_binary(text):
    bits = text.strip().replace(' ', '')
    return bytes(int(bits[i:i+8], 2) for i in range(0, len(bits), 8)).decode('utf-8')

def enc_octal(text):
    return ' '.join(format(b, '03o') for b in text.encode('utf-8'))

def dec_octal(text):
    return bytes(int(o, 8) for o in text.strip().split()).decode('utf-8')

def enc_decimal(text):
    return ' '.join(str(b) for b in text.encode('utf-8'))

def dec_decimal(text):
    return bytes(int(n) for n in text.strip().split()).decode('utf-8')

def dec_jwt(text):
    parts = text.strip().split('.')
    if len(parts) not in (2, 3):
        raise ValueError("无效的 JWT 格式 (需要 2-3 段由 . 分隔)")
    result = []
    labels = ["Header", "Payload", "Signature"]
    for i, part in enumerate(parts):
        if i < 2:
            padded = part + '=' * (-len(part) % 4)
            decoded = base64.urlsafe_b64decode(padded).decode('utf-8')
            try:
                decoded = json.dumps(json.loads(decoded), indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
            result.append(f"=== {labels[i]} ===\n{decoded}")
        else:
            result.append(f"=== {labels[i]} ===\n{part}")
    return '\n\n'.join(result)


# ── 方法注册表 ───────────────────────────────────────────────
# {显示名: (编码函数, 解码函数)}   None 表示不支持该方向
ENCODING_METHODS = {
    "Base64":            (enc_base64, dec_base64),
    "Base32":            (enc_base32, dec_base32),
    "Hex (Base16)":      (enc_hex, dec_hex),
    "Base85":            (enc_base85, dec_base85),
    "URL 编码":          (enc_url, dec_url),
    "HTML 实体":         (enc_html, dec_html),
    "Unicode 转义":      (enc_unicode_escape, dec_unicode_escape),
    "Quoted-Printable":  (enc_quoted_printable, dec_quoted_printable),
    "ROT13":             (enc_rot13, dec_rot13),
    "摩尔斯电码":        (enc_morse, dec_morse),
    "二进制":            (enc_binary, dec_binary),
    "八进制":            (enc_octal, dec_octal),
    "十进制":            (enc_decimal, dec_decimal),
    "JWT 解析":          (None, dec_jwt),
}


def process_encoding(method: str, text: str, encode: bool) -> str:
    """统一入口: 根据方法名和方向执行编码/解码"""
    if method == "JWT 解析":
        return dec_jwt(text)
    if method not in ENCODING_METHODS:
        raise ValueError(f"不支持的方法: {method}")
    enc_fn, dec_fn = ENCODING_METHODS[method]
    if encode:
        if enc_fn is None:
            raise ValueError(f"{method} 不支持编码操作")
        return enc_fn(text)
    else:
        if dec_fn is None:
            raise ValueError(f"{method} 不支持解码操作")
        return dec_fn(text)
