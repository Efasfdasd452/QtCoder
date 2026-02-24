# -*- coding: utf-8 -*-
"""Bencode 编解码，用于 .torrent 文件解析与生成。"""

import re
from typing import Any, Tuple


def _decode_string(s: bytes, i: int) -> Tuple[Any, int]:
    m = re.match(rb"(\d+):", s[i:])
    if not m:
        raise ValueError("invalid string length at %d" % i)
    length = int(m.group(1))
    start = i + m.end()
    return s[start : start + length].decode("utf-8", errors="replace"), start + length


def _decode_int(s: bytes, i: int) -> Tuple[int, int]:
    if s[i : i + 1] != b"i":
        raise ValueError("expected 'i' at %d" % i)
    m = re.match(rb"i(-?\d+)e", s[i:])
    if not m:
        raise ValueError("invalid int at %d" % i)
    return int(m.group(1)), i + m.end()


def _decode_list(s: bytes, i: int) -> Tuple[list, int]:
    if s[i : i + 1] != b"l":
        raise ValueError("expected 'l' at %d" % i)
    i += 1
    out = []
    while i < len(s) and s[i : i + 1] != b"e":
        v, i = decode_next(s, i)
        out.append(v)
    if i >= len(s):
        raise ValueError("unterminated list")
    return out, i + 1


def _decode_dict(s: bytes, i: int) -> Tuple[dict, int]:
    if s[i : i + 1] != b"d":
        raise ValueError("expected 'd' at %d" % i)
    i += 1
    out = {}
    while i < len(s) and s[i : i + 1] != b"e":
        k, i = decode_next(s, i)
        if not isinstance(k, (str, bytes)):
            raise ValueError("dict key must be string at %d" % i)
        if isinstance(k, bytes):
            k = k.decode("utf-8", errors="replace")
        v, i = decode_next(s, i)
        out[k] = v
    if i >= len(s):
        raise ValueError("unterminated dict")
    return out, i + 1


def decode_next(s: bytes, i: int) -> Tuple[Any, int]:
    if i >= len(s):
        raise ValueError("unexpected end at %d" % i)
    c = s[i : i + 1]
    if c == b"i":
        return _decode_int(s, i)
    if c == b"l":
        return _decode_list(s, i)
    if c == b"d":
        return _decode_dict(s, i)
    if c in b"0123456789":
        return _decode_string(s, i)
    raise ValueError("invalid bencode at %d" % i)


def bdecode(s: bytes) -> Any:
    """解码 bencode 字节串，返回 Python 对象。"""
    if not s:
        raise ValueError("empty input")
    v, i = decode_next(s, 0)
    if i != len(s):
        raise ValueError("trailing data after %d" % i)
    return v


def _bencode_string(x: str) -> bytes:
    data = x.encode("utf-8")
    return str(len(data)).encode("ascii") + b":" + data


def _bencode_bytes(x: bytes) -> bytes:
    return str(len(x)).encode("ascii") + b":" + x


def bencode(x: Any) -> bytes:
    """将 Python 对象编码为 bencode 字节串。"""
    if isinstance(x, dict):
        return b"d" + b"".join(_bencode_string(k) + bencode(v) for k, v in sorted(x.items())) + b"e"
    if isinstance(x, list):
        return b"l" + b"".join(bencode(v) for v in x) + b"e"
    if isinstance(x, int):
        return b"i" + str(x).encode("ascii") + b"e"
    if isinstance(x, (str,)):
        return _bencode_string(x)
    if isinstance(x, bytes):
        return _bencode_bytes(x)
    raise TypeError("unsupported type for bencode: %s" % type(x))
