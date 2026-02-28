# -*- coding: utf-8 -*-
"""Word 文档批量转 PDF

引擎优先级（每个文件独立尝试，成功即止）：
  1. docx2pdf   —— 仅限 .docx / Windows+macOS（不支持 .doc，不支持 Linux）
  2. pywin32    —— Windows 专用，支持 .doc 和 .docx（需安装 Microsoft Word）
  3. LibreOffice CLI —— 全平台兜底，支持 .doc 和 .docx

docx2pdf 在 Windows 上要求安装 Microsoft Word。
Linux 平台 docx2pdf 抛 NotImplementedError，会自动跳过。
"""

import os
import sys
import subprocess
import threading


# ── 检测 ─────────────────────────────────────────────────────

def _has_docx2pdf() -> bool:
    try:
        import docx2pdf  # noqa: F401
        return True
    except ImportError:
        return False


def _has_pywin32() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import win32com.client  # noqa: F401
        return True
    except ImportError:
        return False


def find_libreoffice() -> str | None:
    import shutil
    for name in ("soffice", "libreoffice", "soffice.exe"):
        exe = shutil.which(name)
        if exe:
            return exe
    for p in [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/libreoffice",
        "/usr/bin/soffice",
        "/usr/local/bin/soffice",
        "/opt/libreoffice/program/soffice",
    ]:
        if os.path.isfile(p):
            return p
    return None


def detect_engine() -> str:
    """返回将优先使用的引擎名（仅供 UI 提示，不影响实际转换逻辑）。"""
    if _has_docx2pdf() and sys.platform != "linux":
        return "docx2pdf"
    if _has_pywin32():
        return "pywin32"
    if find_libreoffice():
        return "libreoffice"
    return "none"


# ── 各引擎实现 ───────────────────────────────────────────────

def _via_docx2pdf(src_abs: str, dest: str) -> str | None:
    """仅支持 .docx（docx2pdf 硬限制）。返回 None=成功，否则返回错误信息。"""
    from docx2pdf import convert
    convert(src_abs, dest)
    if os.path.isfile(dest):
        return None
    # 有时 docx2pdf 存到源目录，尝试搬过来
    fallback = os.path.splitext(src_abs)[0] + ".pdf"
    if os.path.isfile(fallback) and os.path.abspath(fallback) != os.path.abspath(dest):
        import shutil
        shutil.move(fallback, dest)
        return None if os.path.isfile(dest) else "docx2pdf 未生成输出文件"
    return "docx2pdf 未生成输出文件"


def _via_pywin32(word_app, src_abs: str, dest: str) -> str | None:
    doc = word_app.Documents.Open(src_abs)
    doc.SaveAs(dest, FileFormat=17)   # 17 = wdExportFormatPDF
    doc.Close(0)                      # 0  = wdDoNotSaveChanges
    if os.path.isfile(dest):
        return None
    return "pywin32 未生成输出文件"


def _via_libreoffice(soffice: str, src_abs: str,
                     dest_dir: str, dest: str) -> str | None:
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf",
         "--outdir", dest_dir, src_abs],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode == 0 and os.path.isfile(dest):
        return None
    return (result.stderr or result.stdout
            or f"soffice exit {result.returncode}").strip() or "LibreOffice 转换失败"


# ── 公共入口 ─────────────────────────────────────────────────

def convert_batch(
    files: list[str],
    output_dir: str | None,
    on_file_done,
    stop_event: threading.Event,
) -> None:
    """批量转换 doc/docx → PDF。

    Parameters
    ----------
    files        : 源文件路径列表
    output_dir   : 输出目录；None 表示与源文件同目录
    on_file_done : callable(src, dest_or_None, error_or_None)
    stop_event   : threading.Event，set() 后停止后续文件
    """
    has_d2p = _has_docx2pdf()
    has_pw  = _has_pywin32()
    soffice = find_libreoffice()

    # pywin32 Word 实例：复用，提升批量效率
    word_app = None
    if has_pw:
        try:
            import win32com.client
            word_app = win32com.client.Dispatch("Word.Application")
            word_app.Visible       = False
            word_app.DisplayAlerts = 0
        except Exception:
            has_pw   = False
            word_app = None

    try:
        for src in files:
            if stop_event.is_set():
                break

            src_abs = os.path.abspath(src)
            ext     = os.path.splitext(src_abs)[1].lower()
            base    = os.path.splitext(os.path.basename(src_abs))[0]
            dest_dir_actual = output_dir if output_dir else os.path.dirname(src_abs)
            os.makedirs(dest_dir_actual, exist_ok=True)
            dest = os.path.join(dest_dir_actual, base + ".pdf")

            err: str | None = None

            # ── 引擎 1: docx2pdf ──────────────────────────
            # 只支持 .docx，且 Linux 不支持（立即 NotImplementedError）
            if has_d2p and ext == ".docx" and sys.platform != "linux":
                try:
                    err = _via_docx2pdf(src_abs, dest)
                    if err is None:
                        on_file_done(src, dest, None)
                        continue
                except NotImplementedError:
                    err = "docx2pdf 不支持当前平台"
                except Exception as exc:
                    err = str(exc) or repr(exc)
                    if sys.platform != "win32":
                        err = (
                            f"docx2pdf 在 Linux/macOS 上需要 LibreOffice，"
                            f"请安装：sudo apt install libreoffice\n原始错误：{err}"
                        )

            # ── 引擎 2: pywin32 ───────────────────────────
            if has_pw and word_app:
                try:
                    err = _via_pywin32(word_app, src_abs, dest)
                    if err is None:
                        on_file_done(src, dest, None)
                        continue
                except Exception as exc:
                    err = str(exc) or repr(exc)

            # ── 引擎 3: LibreOffice CLI ───────────────────
            if soffice:
                try:
                    err = _via_libreoffice(soffice, src_abs, dest_dir_actual, dest)
                    if err is None:
                        on_file_done(src, dest, None)
                        continue
                except subprocess.TimeoutExpired:
                    err = "LibreOffice 超时（>120s）"
                except Exception as exc:
                    err = str(exc) or repr(exc)

            # ── 所有引擎均失败 ────────────────────────────
            if not err:
                if ext == ".doc" and has_d2p and not has_pw and not soffice:
                    err = (
                        "docx2pdf 不支持 .doc 格式\n"
                        "请安装 pywin32（pip install pywin32）"
                        "或 LibreOffice 来支持 .doc 转换"
                    )
                else:
                    err = (
                        "无可用转换引擎\n"
                        "请安装 docx2pdf（pip install docx2pdf）"
                        "或 LibreOffice（https://www.libreoffice.org/download/）"
                    )
            on_file_done(src, None, err)

    finally:
        if word_app:
            try:
                word_app.Quit()
            except Exception:
                pass
