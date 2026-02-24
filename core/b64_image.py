# -*- coding: utf-8 -*-
"""Base64 → 图片 解码工具

支持:
  - 标准 data URI:  data:image/png;base64,<data>
  - 纯 Base64 字符串（自动通过魔数识别格式）
  - 批量：文本中每行一条，或空行分隔的多行块
"""

import base64
import os
import re
from typing import List, Tuple, Optional


# ── 格式魔数检测 ──────────────────────────────────────────────────────
_MAGIC: List[Tuple[bytes, Optional[int], str]] = [
    (b'\x89PNG\r\n\x1a\n', None, 'png'),
    (b'\xff\xd8\xff',      None, 'jpg'),
    (b'GIF87a',            None, 'gif'),
    (b'GIF89a',            None, 'gif'),
    (b'RIFF',              None, '_check_webp'),   # 需二次确认
    (b'BM',                None, 'bmp'),
    (b'\x00\x00\x01\x00', None, 'ico'),
    (b'\x00\x00\x02\x00', None, 'ico'),
    (b'II*\x00',           None, 'tif'),
    (b'MM\x00*',           None, 'tif'),
]

_DATA_URI_RE = re.compile(
    r'data:image/([a-zA-Z0-9+\-]+);base64,([A-Za-z0-9+/=\s]+)',
    re.DOTALL,
)

_EXT_MAP = {
    'jpeg': 'jpg',
    'jpg':  'jpg',
    'png':  'png',
    'gif':  'gif',
    'webp': 'webp',
    'bmp':  'bmp',
    'ico':  'ico',
    'tiff': 'tif',
    'tif':  'tif',
    'svg+xml': 'svg',
}


def _detect_format(data: bytes) -> str:
    for magic, _, fmt in _MAGIC:
        if data[:len(magic)] == magic:
            if fmt == '_check_webp':
                return 'webp' if data[8:12] == b'WEBP' else 'bin'
            return fmt
    return 'bin'


def _fix_padding(s: str) -> str:
    """补全 Base64 padding。"""
    s = s.strip()
    pad = len(s) % 4
    if pad:
        s += '=' * (4 - pad)
    return s


def decode_b64_image(raw: str) -> Tuple[bytes, str]:
    """
    解码单条 Base64 字符串为图片字节。

    参数
    ----
    raw : 原始字符串（data URI 或纯 Base64）

    返回
    ----
    (image_bytes, ext)  ext 如 'png'/'jpg'/'gif'/'webp'/'bin' …
    """
    raw = raw.strip()
    m = _DATA_URI_RE.match(raw)
    if m:
        fmt_str = m.group(1).lower()
        b64_data = re.sub(r'\s', '', m.group(2))
        ext = _EXT_MAP.get(fmt_str, fmt_str)
    else:
        # 纯 Base64：去除所有空白
        b64_data = re.sub(r'\s', '', raw)
        ext = None

    b64_data = _fix_padding(b64_data)
    image_bytes = base64.b64decode(b64_data)

    if ext is None:
        ext = _detect_format(image_bytes)

    return image_bytes, ext


def parse_entries(text: str, split_mode: str = 'line') -> List[str]:
    """
    从文本中解析出多条 Base64 条目。

    split_mode
    ----------
    'line'  : 每行一条（忽略空行）
    'block' : 空行分隔的多行块（适合多行格式化的 Base64）
    """
    if split_mode == 'block':
        blocks = re.split(r'\n\s*\n', text.strip())
        return [''.join(b.split()) for b in blocks if b.strip()]
    else:
        return [line.strip() for line in text.splitlines() if line.strip()]


def convert_and_save(
    entries: List[str],
    output_dir: str,
    prefix: str = 'image',
) -> List[dict]:
    """
    批量转换 Base64 条目并保存为图片文件。

    返回值
    ------
    list of {
        'index'  : int,
        'path'   : str,    # 保存路径
        'ext'    : str,    # 文件扩展名
        'size'   : int,    # 字节数
        'error'  : str,    # 空字符串表示成功
    }
    """
    os.makedirs(output_dir, exist_ok=True)
    results = []
    for i, entry in enumerate(entries, 1):
        rec: dict = {'index': i, 'path': '', 'ext': '', 'size': 0, 'error': ''}
        try:
            image_bytes, ext = decode_b64_image(entry)
            filename = f"{prefix}_{i:03d}.{ext}"
            save_path = os.path.join(output_dir, filename)
            with open(save_path, 'wb') as f:
                f.write(image_bytes)
            rec['path'] = save_path
            rec['ext'] = ext
            rec['size'] = len(image_bytes)
        except Exception as e:
            rec['error'] = str(e)
        results.append(rec)
    return results
