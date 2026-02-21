# -*- coding: utf-8 -*-
"""图片压缩核心 — 肉眼无差异（近无损）

- 支持 JPEG / PNG / WebP / BMP / TIFF 等主流格式
- JPEG: quality=98 高质重编码
- PNG: 无损优化（optimize + 合理 compress_level）
- WebP: lossless 或 quality=100
- 输出格式可与原格式一致或统一为指定格式
"""

import os
import shutil
from typing import List, Optional, Tuple

try:
    from PIL import Image
except ImportError:
    Image = None

# 支持的图片扩展名（主流格式）
IMAGE_EXTS = (
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif",
    ".gif", ".avif",
)

# 文件选择器用
IMAGE_FILTER = (
    "图片文件 (" + " ".join(f"*{e}" for e in IMAGE_EXTS) + ");;"
    "所有文件 (*)"
)


def _ext_is_image(name: str) -> bool:
    return name.lower().endswith(IMAGE_EXTS)


def collect_images_from_folder(
    folder: str, recursive: bool = True
) -> List[str]:
    """从文件夹收集所有图片路径；recursive=True 时包含子文件夹。"""
    if not os.path.isdir(folder):
        return []
    out = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for f in files:
                if _ext_is_image(f):
                    out.append(os.path.normpath(os.path.join(root, f)))
    else:
        for f in os.listdir(folder):
            path = os.path.join(folder, f)
            if os.path.isfile(path) and _ext_is_image(f):
                out.append(os.path.normpath(path))
    return sorted(out)


def get_disk_free_bytes(path: str) -> int:
    """path 所在磁盘可用空间（字节）。"""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        path = os.path.dirname(path)
    if not path or not os.path.exists(path):
        return 0
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


# ── 预设策略（与视频面板一致：三档）────────────────────────────

PRESETS = {
    "quality": {
        "name": "画质优先",
        "desc": "JPEG 100 / PNG 低压缩 / WebP 无损 · 体积最大、肉眼无差异",
        "jpeg_quality": 100,
        "png_compress": 4,
        "webp_quality": 100,
        "webp_lossless": True,
    },
    "balanced": {
        "name": "推荐均衡",
        "desc": "JPEG 98 / PNG 中等 / WebP 100 · 画质与体积兼顾",
        "jpeg_quality": 98,
        "png_compress": 6,
        "webp_quality": 100,
        "webp_lossless": True,
    },
    "size": {
        "name": "体积优先",
        "desc": "JPEG 95 / PNG 高压缩 / WebP 95 · 体积更小、仍肉眼无差异",
        "jpeg_quality": 95,
        "png_compress": 8,
        "webp_quality": 95,
        "webp_lossless": False,
    },
}

# 各预设预估压缩后约为原大小的比例
PRESET_ESTIMATE_RATIO = {
    "quality": 0.85,
    "balanced": 0.75,
    "size": 0.60,
}


def estimate_compressed_size_total(file_sizes: List[int], preset_key: str = "balanced") -> int:
    """按预设估算批量压缩后总字节数。"""
    ratio = PRESET_ESTIMATE_RATIO.get(preset_key, 0.75)
    return int(sum(file_sizes) * ratio)


def compress_image(
    src_path: str,
    out_path: str,
    *,
    keep_format: bool = True,
    preset_key: str = "balanced",
) -> int:
    """
    单张图片压缩，按预设策略。
    preset_key: quality / balanced / size
    返回压缩后文件字节数。
    """
    if Image is None:
        raise RuntimeError("请安装 Pillow: pip install Pillow")
    try:
        if os.path.normpath(os.path.abspath(src_path)) == os.path.normpath(os.path.abspath(out_path)):
            raise ValueError("输出路径不能与源文件相同，请另选保存位置")
    except OSError:
        pass

    p = PRESETS.get(preset_key, PRESETS["balanced"])
    jpeg_q = p["jpeg_quality"]
    png_level = p["png_compress"]
    webp_q = p["webp_quality"]
    webp_lossless = p["webp_lossless"]

    img = Image.open(src_path)
    if img.mode in ("P", "PA"):
        img = img.convert("RGBA" if img.mode == "PA" or (img.mode == "P" and img.info.get("transparency") is not None) else "RGB")
    elif img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")

    ext = os.path.splitext(out_path)[1].lower()
    src_ext = os.path.splitext(src_path)[1].lower()

    if keep_format:
        out_ext = ext or src_ext
    else:
        out_ext = ext

    if out_ext in (".jpg", ".jpeg"):
        img.save(out_path, "JPEG", quality=jpeg_q, optimize=True)
    elif out_ext == ".webp":
        if webp_lossless:
            img.save(out_path, "WEBP", lossless=True)
        else:
            img.save(out_path, "WEBP", quality=webp_q, method=6)
    elif out_ext in (".png",):
        img.save(out_path, "PNG", optimize=True, compress_level=png_level)
    elif out_ext in (".tiff", ".tif"):
        img.save(out_path, "TIFF", compression="tiff_deflate")
    else:
        img.save(out_path, "PNG", optimize=True, compress_level=png_level)

    return os.path.getsize(out_path)


def is_available() -> bool:
    """是否可用（Pillow 已安装）。"""
    return Image is not None
