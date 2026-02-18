# -*- coding: utf-8 -*-
"""FFmpeg 本地管理模块

- 运行时只使用 vendor/ffmpeg/ 目录下的 ffmpeg / ffprobe
- 支持 Windows (x64/arm64) 和 Linux (x64/arm64)
- 从 BtbN/FFmpeg-Builds GitHub releases 下载 GPL 静态构建
- 兼容 PyInstaller 打包环境（frozen）和开发环境
"""

import os
import platform
import shutil
import sys
import tarfile
import tempfile
import zipfile
from typing import Callable, Optional
from urllib.request import urlopen, Request

# ── 下载源 ────────────────────────────────────────────────────

_BTBN_BASE = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
_FFMPEG_VERSION = "n7.1"

_DOWNLOAD_MAP = {
    ("Windows", "x86_64"):  f"ffmpeg-{_FFMPEG_VERSION}-latest-win64-gpl-7.1.zip",
    ("Windows", "AMD64"):   f"ffmpeg-{_FFMPEG_VERSION}-latest-win64-gpl-7.1.zip",
    ("Windows", "ARM64"):   f"ffmpeg-{_FFMPEG_VERSION}-latest-winarm64-gpl-7.1.zip",
    ("Linux",   "x86_64"):  f"ffmpeg-{_FFMPEG_VERSION}-latest-linux64-gpl-7.1.tar.xz",
    ("Linux",   "aarch64"): f"ffmpeg-{_FFMPEG_VERSION}-latest-linuxarm64-gpl-7.1.tar.xz",
}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _detect_archive() -> str:
    """根据当前系统/架构返回应下载的文件名。"""
    system = platform.system()
    machine = platform.machine()
    key = (system, machine)
    if key not in _DOWNLOAD_MAP:
        raise RuntimeError(
            f"不支持的平台: {system} {machine}\n"
            f"支持: {', '.join(f'{s}-{m}' for s, m in _DOWNLOAD_MAP)}")
    return _DOWNLOAD_MAP[key]


def get_download_url() -> str:
    return f"{_BTBN_BASE}/{_detect_archive()}"


def get_download_size_hint() -> str:
    """返回预估下载大小供 UI 提示。"""
    name = _detect_archive()
    if "win64-gpl-7.1.zip" in name:
        return "~149 MB"
    if "winarm64" in name:
        return "~103 MB"
    if "linux64" in name:
        return "~111 MB"
    if "linuxarm64" in name:
        return "~95 MB"
    return "~100 MB"


# ── 路径解析 ──────────────────────────────────────────────────

def _app_base() -> str:
    """应用根目录：打包后为可执行文件所在目录，开发时为项目根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _vendor_dir() -> str:
    return os.path.join(_app_base(), "vendor", "ffmpeg")


def get_ffmpeg_path() -> Optional[str]:
    """本地 ffmpeg 可执行文件路径，不存在返回 None。"""
    ext = ".exe" if os.name == "nt" else ""
    p = os.path.join(_vendor_dir(), f"ffmpeg{ext}")
    return p if os.path.isfile(p) else None


def get_ffprobe_path() -> Optional[str]:
    ext = ".exe" if os.name == "nt" else ""
    p = os.path.join(_vendor_dir(), f"ffprobe{ext}")
    return p if os.path.isfile(p) else None


def is_available() -> bool:
    return get_ffmpeg_path() is not None and get_ffprobe_path() is not None


# ── 下载与解压 ────────────────────────────────────────────────

def download_ffmpeg(
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> str:
    """下载并解压 FFmpeg 到 vendor/ffmpeg/。

    Args:
        progress_cb: 进度回调 (downloaded_bytes, total_bytes)。

    Returns:
        ffmpeg 可执行文件的绝对路径。
    """
    existing = get_ffmpeg_path()
    if existing:
        return existing

    vdir = _vendor_dir()
    os.makedirs(vdir, exist_ok=True)

    url = get_download_url()
    archive_name = url.rsplit("/", 1)[-1]
    tmp_path = os.path.join(tempfile.gettempdir(), archive_name)

    try:
        _download_file(url, tmp_path, progress_cb)

        if tmp_path.endswith(".zip"):
            _extract_zip(tmp_path, vdir)
        elif tmp_path.endswith((".tar.xz", ".tar.gz")):
            _extract_tar(tmp_path, vdir)
        else:
            raise RuntimeError(f"未知的压缩格式: {archive_name}")

    finally:
        if os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    if os.name != "nt":
        for name in ("ffmpeg", "ffprobe"):
            p = os.path.join(vdir, name)
            if os.path.isfile(p):
                os.chmod(p, 0o755)

    result = get_ffmpeg_path()
    if not result:
        raise FileNotFoundError("解压完成但未找到 ffmpeg 可执行文件")
    return result


def _download_file(
    url: str,
    dest: str,
    progress_cb: Optional[Callable[[int, int], None]],
):
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    resp = urlopen(req, timeout=300)
    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    chunk_size = 256 * 1024

    with open(dest, "wb") as f:
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if progress_cb:
                progress_cb(downloaded, total)


def _extract_zip(zip_path: str, dest: str):
    """从 zip 中提取 bin/ 下的可执行文件到 dest（扁平放置）。"""
    with zipfile.ZipFile(zip_path, "r") as zf:
        bin_prefix = _find_bin_prefix(zf.namelist(), "ffmpeg.exe")
        if not bin_prefix:
            raise FileNotFoundError("ZIP 内未找到 ffmpeg，下载文件可能损坏")

        for member in zf.infolist():
            if member.filename.startswith(bin_prefix) and not member.is_dir():
                filename = os.path.basename(member.filename)
                if not filename:
                    continue
                dest_path = os.path.join(dest, filename)
                with zf.open(member) as src, open(dest_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)


def _extract_tar(tar_path: str, dest: str):
    """从 tar.xz 中提取 bin/ 下的可执行文件到 dest（扁平放置）。"""
    with tarfile.open(tar_path, "r:*") as tf:
        names = tf.getnames()
        bin_prefix = _find_bin_prefix(names, "ffmpeg")
        if not bin_prefix:
            raise FileNotFoundError("归档内未找到 ffmpeg，下载文件可能损坏")

        for member in tf.getmembers():
            if member.name.startswith(bin_prefix) and member.isfile():
                filename = os.path.basename(member.name)
                if not filename:
                    continue
                dest_path = os.path.join(dest, filename)
                src = tf.extractfile(member)
                if src:
                    with open(dest_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)


def _find_bin_prefix(names: list, target: str) -> Optional[str]:
    """在归档文件名列表中找到 bin/ 目录的前缀。"""
    for name in names:
        normalized = name.replace("\\", "/")
        if normalized.endswith(f"/bin/{target}"):
            return normalized.rsplit(f"bin/{target}", 1)[0] + "bin/"
    return None
