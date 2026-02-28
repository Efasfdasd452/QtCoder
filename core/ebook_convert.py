# -*- coding: utf-8 -*-
"""电子书格式批量转换（Calibre ebook-convert）

支持方向：
  EPUB → PDF / MOBI
  PDF  → EPUB / MOBI
  MOBI → PDF / EPUB
  AZW / AZW3 → PDF / EPUB / MOBI

Calibre 已预置于项目目录 bin/calibre/portable/Calibre/ebook-convert.exe
"""

import os
import subprocess
import shutil
import sys
import threading
from pathlib import Path

# ── 路径常量 ─────────────────────────────────────────────────

# 项目根目录（main.py 所在位置）
_ROOT = Path(__file__).resolve().parent.parent

# 预置 Calibre 路径
_BUNDLED_CALIBRE = _ROOT / "bin" / "calibre" / "portable" / "Calibre" / "ebook-convert.exe"

# 短路径工作目录（用于绕过 Calibre 对路径长度约 59 字符的限制）
_SHORT_BASE = Path("C:/ec") if sys.platform == "win32" else Path("/tmp/ec")

# 用户指定路径的配置文件（项目 config/calibre_path.txt）
_CALIBRE_PATH_FILE = _ROOT / "config" / "calibre_path.txt"

# 接受的输入扩展名
SUPPORTED_INPUT  = {".epub", ".pdf", ".mobi", ".azw", ".azw3"}
# 提供的输出格式
SUPPORTED_OUTPUT = ["pdf", "epub", "mobi"]


# ── 用户指定路径（供 UI 读写）────────────────────────────────

def get_calibre_custom_path() -> str | None:
    """读取用户指定的 ebook-convert 路径，未设置或文件不存在则返回 None。"""
    if not _CALIBRE_PATH_FILE.is_file():
        return None
    try:
        path = _CALIBRE_PATH_FILE.read_text(encoding="utf-8").strip()
        if path and os.path.isfile(path):
            return path
    except Exception:
        pass
    return None


def set_calibre_custom_path(path: str | None) -> None:
    """保存用户指定的 ebook-convert 路径；传入 None 或空字符串则清除。"""
    _CALIBRE_PATH_FILE.parent.mkdir(parents=True, exist_ok=True)
    if path and path.strip():
        _CALIBRE_PATH_FILE.write_text(path.strip(), encoding="utf-8")
    elif _CALIBRE_PATH_FILE.is_file():
        try:
            _CALIBRE_PATH_FILE.unlink()
        except OSError:
            pass


# ── 查找 ebook-convert ───────────────────────────────────────

def find_calibre() -> str | None:
    """按优先级查找 ebook-convert 可执行文件路径，找不到返回 None。

    查找顺序：
      1. 用户指定路径（config/calibre_path.txt）
      2. bin/calibre/portable/Calibre/
      3. bin/calibre/ 下递归搜索 ebook-convert.exe
      4. PATH
      5. 常见安装路径
    """
    # 1. 用户指定路径（优先，便于解压到短路径后手动指定）
    custom = get_calibre_custom_path()
    if custom:
        return custom

    # 2. 项目预置固定路径
    if _BUNDLED_CALIBRE.is_file():
        return str(_BUNDLED_CALIBRE)

    # 3. 在 bin/calibre 下递归找 ebook-convert.exe（兼容不同解压结构）
    bin_calibre = _ROOT / "bin" / "calibre"
    if bin_calibre.is_dir():
        for exe in bin_calibre.rglob("ebook-convert.exe"):
            if exe.is_file():
                return str(exe.resolve())

    # 4. PATH
    exe = shutil.which("ebook-convert")
    if exe:
        return exe

    # 5. 常见安装路径
    for p in [
        r"C:\Program Files\Calibre2\ebook-convert.exe",
        r"C:\Program Files (x86)\Calibre2\ebook-convert.exe",
        r"C:\Program Files\calibre2\ebook-convert.exe",
        "/usr/bin/ebook-convert",
        "/usr/local/bin/ebook-convert",
        "/Applications/calibre.app/Contents/MacOS/ebook-convert",
        "/opt/calibre/ebook-convert",
    ]:
        if os.path.isfile(p):
            return p

    return None


def calibre_download_info() -> dict:
    """返回 Calibre 下载信息，供 UI 显示未安装时的提示。"""
    return {"version": "7.x"}


def download_and_setup_calibre(
    on_progress=None,
    on_status=None,
    stop_event=None,
) -> str | None:
    """下载并解压 Calibre 到 bin/calibre/。成功返回 None，失败返回错误信息。"""
    # 可选：在此实现从 calibre-ebook.com 下载便携版的逻辑
    return "自动下载功能未实现，请手动从 https://calibre-ebook.com/download 下载并解压到 bin/calibre/ 目录"


def _get_short_path(long_path: str) -> str:
    """Windows: 返回 8.3 短路径，若失败或非 Windows 则返回原路径。"""
    if sys.platform != "win32" or not long_path or len(long_path) <= 59:
        return long_path
    try:
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        n = kernel32.GetShortPathNameW(long_path, buf, len(buf))
        if n and n < len(buf):
            return buf.value
    except Exception:
        pass
    return long_path


# ── 批量转换 ─────────────────────────────────────────────────

def convert_batch(
    files: list[str],
    output_format: str,
    output_dir: str | None,
    on_file_done,
    stop_event: threading.Event,
) -> None:
    """批量转换电子书格式。

    Parameters
    ----------
    files         : 源文件路径列表
    output_format : 目标格式，如 'pdf' / 'epub' / 'mobi'
    output_dir    : 输出目录；None 表示与源文件同目录
    on_file_done  : callable(src, dest_or_None, error_or_None)
    stop_event    : threading.Event，set() 后停止后续文件
    """
    ebook_convert = find_calibre()
    if not ebook_convert:
        msg = (
            "未找到 Calibre。\n"
            "请点击面板中的「下载 Calibre」按钮自动安装，"
            "或手动安装：https://calibre-ebook.com/download"
        )
        for f in files:
            on_file_done(f, None, msg)
        return

    fmt = output_format.lower().lstrip(".")

    for src in files:
        if stop_event.is_set():
            break

        src_abs  = os.path.abspath(src)
        base     = os.path.splitext(os.path.basename(src_abs))[0]
        dest_dir = output_dir if output_dir else os.path.dirname(src_abs)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, f"{base}.{fmt}")

        # 同格式直接拷贝
        src_ext = os.path.splitext(src_abs)[1].lower().lstrip(".")
        if src_ext == fmt:
            try:
                if os.path.abspath(src_abs) != os.path.abspath(dest):
                    shutil.copy2(src_abs, dest)
                on_file_done(src, dest, None)
            except Exception as exc:
                on_file_done(src, None, str(exc))
            continue

        # 使用短路径工作目录，绕过 Calibre 对路径长度（约 59 字符）的限制
        _SHORT_BASE.mkdir(parents=True, exist_ok=True)
        short_in = _SHORT_BASE / ("in" + os.path.splitext(src_abs)[1])
        short_out = _SHORT_BASE / ("out." + fmt)
        exe_to_use = _get_short_path(ebook_convert)
        try:
            shutil.copy2(src_abs, short_in)
            result = subprocess.run(
                [exe_to_use, str(short_in), str(short_out)],
                cwd=str(_SHORT_BASE),
                capture_output=True, text=True,
                timeout=300,
            )
            if result.returncode == 0 and short_out.is_file():
                shutil.copy2(short_out, dest)
                on_file_done(src, dest, None)
            else:
                err = (result.stderr or result.stdout
                       or f"ebook-convert exit {result.returncode}").strip()
                on_file_done(src, None, err or "Calibre 转换失败（未知错误）")
        except subprocess.TimeoutExpired:
            on_file_done(src, None, "超时（>300s），文件可能过大")
        except Exception as exc:
            on_file_done(src, None, str(exc) or repr(exc))
        finally:
            if short_in.exists():
                try:
                    short_in.unlink()
                except OSError:
                    pass
            if short_out.exists():
                try:
                    short_out.unlink()
                except OSError:
                    pass
