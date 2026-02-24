# -*- coding: utf-8 -*-
"""文件哈希计算工具

支持 MD5 / SHA-1 / SHA-256 / SHA-512 / SHA3-256，
单文件、批量文件、整个文件夹（可递归）一次性计算，
对大文件分块读取，内存友好。
"""

import hashlib
import os
from pathlib import Path

# ── 算法定义 ──────────────────────────────────────────────────
ALGORITHMS = ['MD5', 'SHA-1', 'SHA-256', 'SHA-512', 'SHA3-256']
_ALGO_MAP  = {
    'MD5':     'md5',
    'SHA-1':   'sha1',
    'SHA-256': 'sha256',
    'SHA-512': 'sha512',
    'SHA3-256':'sha3_256',
}

_CHUNK = 1 << 17   # 128 KB


def hash_file(path: str, algos: list[str]) -> dict[str, str]:
    """对单个文件同时计算多种哈希，一次 I/O 完成。

    Returns: {algo_name: hexdigest}
    """
    hashes = {a: hashlib.new(_ALGO_MAP[a]) for a in algos}
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(_CHUNK), b''):
            for h in hashes.values():
                h.update(chunk)
    return {a: hashes[a].hexdigest() for a in algos}


def collect_files(paths: list[str], recursive: bool = True) -> list[str]:
    """将文件路径 + 文件夹展开为纯文件列表（去重，保序）。"""
    seen = set()
    result = []
    for p in paths:
        p = Path(p)
        if p.is_file():
            key = str(p.resolve())
            if key not in seen:
                seen.add(key)
                result.append(str(p))
        elif p.is_dir():
            it = p.rglob('*') if recursive else p.iterdir()
            for f in sorted(it):
                if f.is_file():
                    key = str(f.resolve())
                    if key not in seen:
                        seen.add(key)
                        result.append(str(f))
    return result


def compare_hash(computed: str, expected: str) -> bool:
    """大小写不敏感地比较哈希值。"""
    return computed.strip().lower() == expected.strip().lower()


def fmt_size(n: int) -> str:
    """将字节数格式化为人类可读的大小字符串。"""
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != 'B' else f"{n} B"
        n /= 1024
    return f"{n:.1f} PB"
