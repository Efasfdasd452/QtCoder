# -*- coding: utf-8 -*-
"""FFmpeg 本地管理模块

- 运行时只使用 vendor/ffmpeg/ 目录下的 ffmpeg / ffprobe
- 支持指定目标平台下载（可在 Windows 上下载 Linux 版本）
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

# ── 目标平台定义 ──────────────────────────────────────────────

TARGETS = ("win64", "winarm64", "linux64", "linuxarm64")

_BTBN_BASE = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
_FFMPEG_VERSION = "n7.1"

_ARCHIVE_MAP = {
    "win64":      f"ffmpeg-{_FFMPEG_VERSION}-latest-win64-gpl-7.1.zip",
    "winarm64":   f"ffmpeg-{_FFMPEG_VERSION}-latest-winarm64-gpl-7.1.zip",
    "linux64":    f"ffmpeg-{_FFMPEG_VERSION}-latest-linux64-gpl-7.1.tar.xz",
    "linuxarm64": f"ffmpeg-{_FFMPEG_VERSION}-latest-linuxarm64-gpl-7.1.tar.xz",
}

_SIZE_HINT = {
    "win64":      "~149 MB",
    "winarm64":   "~103 MB",
    "linux64":    "~111 MB",
    "linuxarm64": "~95 MB",
}

_PLATFORM_AUTO_MAP = {
    ("Windows", "x86_64"):  "win64",
    ("Windows", "AMD64"):   "win64",
    ("Windows", "ARM64"):   "winarm64",
    ("Linux",   "x86_64"):  "linux64",
    ("Linux",   "aarch64"): "linuxarm64",
}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def detect_native_target() -> str:
    """根据当前系统返回本机对应的 target 名称。"""
    key = (platform.system(), platform.machine())
    t = _PLATFORM_AUTO_MAP.get(key)
    if not t:
        raise RuntimeError(
            f"不支持的平台: {key[0]} {key[1]}\n"
            f"支持的目标: {', '.join(TARGETS)}")
    return t


def get_download_url(target: Optional[str] = None) -> str:
    target = target or detect_native_target()
    return f"{_BTBN_BASE}/{_ARCHIVE_MAP[target]}"


def get_download_size_hint(target: Optional[str] = None) -> str:
    target = target or detect_native_target()
    return _SIZE_HINT.get(target, "~100 MB")


def is_win_target(target: str) -> bool:
    return target.startswith("win")


# ── 路径解析 ──────────────────────────────────────────────────

def _project_root() -> str:
    """项目根目录（core/ 的上级目录）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _app_base() -> str:
    """应用根目录：打包后为可执行文件所在目录，开发时为项目根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return _project_root()


def _runtime_ffmpeg_dir() -> str:
    """运行时 ffmpeg 可执行文件所在目录。

    打包后 (frozen): <exe所在目录>/ffmpeg/
    开发时 (Windows): <项目根>/vendor/ffmpeg/bin/
    开发时 (Linux):   <项目根>/linux_ffmpeg/ffmpeg/bin/
    """
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "ffmpeg")
    root = _project_root()
    if os.name == "nt":
        return os.path.join(root, "vendor", "ffmpeg", "bin")
    else:
        return os.path.join(root, "linux_ffmpeg", "ffmpeg", "bin")


def vendor_dir(target: Optional[str] = None) -> str:
    """返回 vendor 目录路径（用于下载/构建）。
    指定 target 时返回 vendor/ffmpeg-{target}/。
    不指定 target 时返回运行时 ffmpeg 目录。"""
    if target:
        base = _project_root()
        return os.path.join(base, "vendor", f"ffmpeg-{target}")
    return _runtime_ffmpeg_dir()


def get_ffmpeg_path(target: Optional[str] = None) -> Optional[str]:
    """本地 ffmpeg 可执行文件路径，不存在返回 None。
    不传 target 时自动根据环境（打包/开发）和平台查找。"""
    vdir = vendor_dir(target)
    is_win = is_win_target(target) if target else (os.name == "nt")
    ext = ".exe" if is_win else ""
    p = os.path.join(vdir, f"ffmpeg{ext}")
    return p if os.path.isfile(p) else None


def get_ffprobe_path(target: Optional[str] = None) -> Optional[str]:
    vdir = vendor_dir(target)
    is_win = is_win_target(target) if target else (os.name == "nt")
    ext = ".exe" if is_win else ""
    p = os.path.join(vdir, f"ffprobe{ext}")
    return p if os.path.isfile(p) else None


def is_available(target: Optional[str] = None) -> bool:
    return (get_ffmpeg_path(target) is not None
            and get_ffprobe_path(target) is not None)


# ── 下载与解压 ────────────────────────────────────────────────

def download_ffmpeg(
    target: Optional[str] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> str:
    """下载并解压 FFmpeg。

    Args:
        target: 目标平台 (win64/winarm64/linux64/linuxarm64)。
                None 表示：有 target 参数时下载到 vendor/ffmpeg-{target}/，
                无参数时下载到 vendor/ffmpeg/（运行时默认）。
        progress_cb: 进度回调 (downloaded_bytes, total_bytes)。

    Returns:
        ffmpeg 可执行文件的绝对路径。
    """
    existing = get_ffmpeg_path(target)
    if existing:
        return existing

    resolved_target = target or detect_native_target()
    vdir = vendor_dir(target)
    os.makedirs(vdir, exist_ok=True)

    url = get_download_url(resolved_target)
    archive_name = url.rsplit("/", 1)[-1]
    tmp_path = os.path.join(tempfile.gettempdir(), archive_name)

    try:
        _download_file(url, tmp_path, progress_cb)

        if tmp_path.endswith(".zip"):
            _extract_zip(tmp_path, vdir, is_win_target(resolved_target))
        elif ".tar" in tmp_path:
            _extract_tar(tmp_path, vdir)
        else:
            raise RuntimeError(f"未知的压缩格式: {archive_name}")

    finally:
        if os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    if not is_win_target(resolved_target):
        for name in ("ffmpeg", "ffprobe", "ffplay"):
            p = os.path.join(vdir, name)
            if os.path.isfile(p):
                os.chmod(p, 0o755)

    result = get_ffmpeg_path(target)
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


def _extract_zip(zip_path: str, dest: str, win: bool = True):
    """从 zip 中提取 bin/ 下的可执行文件到 dest（扁平放置）。"""
    target_name = "ffmpeg.exe" if win else "ffmpeg"
    with zipfile.ZipFile(zip_path, "r") as zf:
        bin_prefix = _find_bin_prefix(zf.namelist(), target_name)
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
