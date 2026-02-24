# -*- coding: utf-8 -*-
"""nmap 可执行文件定位工具

搜索顺序:
    1. PyInstaller 打包后: <exe 同目录>/bin/nmap/nmap.exe
    2. 开发模式: <项目根>/bin/nmap/nmap.exe
    3. 系统 PATH: shutil.which('nmap')
"""

import os
import sys
import shutil

# ── 开发模式下的路径 ─────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NMAP_BIN_DIR  = os.path.join(_PROJECT_ROOT, 'bin', 'nmap')
NMAP_EXE_PATH = os.path.join(NMAP_BIN_DIR, 'nmap.exe')

NMAP_ZIP_URL = 'https://nmap.org/dist/nmap-7.92-win32.zip'
NMAP_VERSION = '7.92'


def get_nmap_exe() -> str | None:
    """返回可用的 nmap 可执行文件路径，找不到返回 None。"""

    if getattr(sys, 'frozen', False):
        # PyInstaller 打包模式：nmap 在 exe 同目录下的 bin/nmap/
        bundled = os.path.join(
            os.path.dirname(sys.executable), 'bin', 'nmap', 'nmap.exe')
        if os.path.isfile(bundled):
            return bundled
    else:
        # 开发模式：项目根目录下的 bin/nmap/
        if os.path.isfile(NMAP_EXE_PATH):
            return NMAP_EXE_PATH

    # 最后回退到系统 PATH
    return shutil.which('nmap')


def is_nmap_available() -> bool:
    return get_nmap_exe() is not None


def download_nmap(progress_cb=None) -> str:
    """（备用）下载 nmap-7.92-win32.zip 并解压到 bin/nmap/。

    正常情况下 nmap 已随应用打包，无需调用此函数。
    仅当 get_nmap_exe() 返回 None 时才会触发。
    """
    import urllib.request
    import zipfile
    import tempfile

    os.makedirs(NMAP_BIN_DIR, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.zip')
    os.close(tmp_fd)
    try:
        def _hook(n, bs, total):
            if progress_cb and total > 0:
                progress_cb(min(n * bs, total), total)

        urllib.request.urlretrieve(NMAP_ZIP_URL, tmp_path, _hook)

        with zipfile.ZipFile(tmp_path, 'r') as zf:
            with tempfile.TemporaryDirectory() as td:
                zf.extractall(td)
                sub_dirs = [d for d in os.listdir(td)
                            if os.path.isdir(os.path.join(td, d))]
                if not sub_dirs:
                    raise RuntimeError("zip 内容异常")
                src = os.path.join(td, sub_dirs[0])
                import shutil as _sh
                for item in os.listdir(src):
                    s = os.path.join(src, item)
                    d = os.path.join(NMAP_BIN_DIR, item)
                    if os.path.isdir(s):
                        if os.path.exists(d):
                            _sh.rmtree(d)
                        _sh.copytree(s, d)
                    else:
                        _sh.copy2(s, d)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not os.path.isfile(NMAP_EXE_PATH):
        raise RuntimeError(f"解压后找不到 nmap.exe: {NMAP_EXE_PATH}")
    return NMAP_EXE_PATH
