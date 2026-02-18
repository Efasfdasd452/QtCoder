#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QtCoder 跨平台打包脚本

用法:
    python build.py                     # 自动检测平台，打包
    python build.py --download-ffmpeg   # 仅下载 FFmpeg 到 vendor/
    python build.py --clean             # 仅清理 build/dist
    python build.py --no-clean          # 打包前不清理旧文件

支持平台:
    Windows x64 / ARM64
    Linux   x64 / ARM64 (Ubuntu, Debian, Fedora, Arch …)
"""

import os
import platform
import sys
import shutil
import subprocess
import argparse
import time

# ── 配置 ──────────────────────────────────────────────────────

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SPEC_FILE = os.path.join(PROJECT_DIR, "QtCoder.spec")
DIST_DIR = os.path.join(PROJECT_DIR, "dist")
BUILD_DIR = os.path.join(PROJECT_DIR, "build")
VENDOR_FFMPEG_SRC = os.path.join(PROJECT_DIR, "vendor", "ffmpeg")
VENDOR_FFMPEG_DST = os.path.join(DIST_DIR, "vendor", "ffmpeg")

IS_WIN = os.name == "nt"
APP_NAME = "QtCoder"
OUTPUT_BIN = os.path.join(DIST_DIR, f"{APP_NAME}.exe" if IS_WIN else APP_NAME)

if IS_WIN:
    VENV_PYTHON = os.path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe")
else:
    VENV_PYTHON = os.path.join(PROJECT_DIR, ".venv", "bin", "python")


# ── 日志 ──────────────────────────────────────────────────────

def log(msg):
    print(f"  [*] {msg}")


def log_ok(msg):
    print(f"  [OK] {msg}")


def log_err(msg):
    print(f"  [ERROR] {msg}", file=sys.stderr)


# ── Python 环境 ──────────────────────────────────────────────

def get_python():
    if os.path.isfile(VENV_PYTHON):
        return VENV_PYTHON
    log_err(f"虚拟环境未找到: {VENV_PYTHON}")
    if IS_WIN:
        log_err("请先创建: python -m venv .venv && "
                ".venv\\Scripts\\pip install -r requirements.txt")
    else:
        log_err("请先创建: python3 -m venv .venv && "
                ".venv/bin/pip install -r requirements.txt")
    sys.exit(1)


def check_pyinstaller(python):
    try:
        subprocess.run(
            [python, "-c", "import PyInstaller"],
            check=True, capture_output=True,
        )
        result = subprocess.run(
            [python, "-c",
             "import PyInstaller; print(PyInstaller.__version__)"],
            capture_output=True, text=True,
        )
        log_ok(f"PyInstaller {result.stdout.strip()}")
    except subprocess.CalledProcessError:
        log("PyInstaller 未安装，正在安装 ...")
        subprocess.run(
            [python, "-m", "pip", "install", "pyinstaller"],
            check=True,
        )
        log_ok("PyInstaller 安装完成")


# ── FFmpeg 下载 ──────────────────────────────────────────────

def ensure_ffmpeg():
    """确保 vendor/ffmpeg/ 里有 ffmpeg 可执行文件，没有则自动下载。"""
    ext = ".exe" if IS_WIN else ""
    ffmpeg_bin = os.path.join(VENDOR_FFMPEG_SRC, f"ffmpeg{ext}")

    if os.path.isfile(ffmpeg_bin):
        size_mb = os.path.getsize(ffmpeg_bin) / (1024 * 1024)
        log_ok(f"FFmpeg 已存在: {ffmpeg_bin} ({size_mb:.0f} MB)")
        return

    log("vendor/ffmpeg/ 中未找到 ffmpeg，开始下载 ...")

    sys.path.insert(0, PROJECT_DIR)
    from core.ffmpeg_downloader import download_ffmpeg, get_download_url

    url = get_download_url()
    log(f"下载: {url}")

    def on_progress(downloaded, total):
        if total > 0:
            pct = downloaded / total * 100
            bar_len = 30
            filled = int(bar_len * downloaded / total)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"\r  [DL] {bar} {pct:5.1f}%  "
                  f"{downloaded // (1024*1024):>4d}/"
                  f"{total // (1024*1024)} MB", end="", flush=True)

    path = download_ffmpeg(progress_cb=on_progress)
    print()
    log_ok(f"FFmpeg 已下载: {path}")


def copy_ffmpeg():
    """将 vendor/ffmpeg/ 复制到 dist/vendor/ffmpeg/。"""
    if not os.path.isdir(VENDOR_FFMPEG_SRC):
        log_err(f"未找到本地 FFmpeg: {VENDOR_FFMPEG_SRC}")
        log_err("请先运行: python build.py --download-ffmpeg")
        return False
    if os.path.isdir(VENDOR_FFMPEG_DST):
        shutil.rmtree(VENDOR_FFMPEG_DST)
    shutil.copytree(VENDOR_FFMPEG_SRC, VENDOR_FFMPEG_DST)
    files = os.listdir(VENDOR_FFMPEG_DST)
    total_size = sum(
        os.path.getsize(os.path.join(VENDOR_FFMPEG_DST, f))
        for f in files
    )
    log_ok(f"FFmpeg 已复制到 dist/vendor/ffmpeg/ "
           f"({len(files)} 个文件, {total_size / (1024*1024):.0f} MB)")
    return True


# ── 清理 ─────────────────────────────────────────────────────

def clean():
    for d in [BUILD_DIR, DIST_DIR]:
        if os.path.isdir(d):
            shutil.rmtree(d)
            log(f"已删除 {os.path.basename(d)}/")
    log_ok("清理完成")


# ── 打包 ─────────────────────────────────────────────────────

def build(python):
    if not os.path.isfile(SPEC_FILE):
        log_err(f"未找到 spec 文件: {SPEC_FILE}")
        sys.exit(1)

    cmd = [
        python, "-m", "PyInstaller",
        SPEC_FILE,
        "--noconfirm",
        "--distpath", DIST_DIR,
        "--workpath", BUILD_DIR,
    ]

    log(f"执行: {' '.join(os.path.basename(c) for c in cmd)}")
    print()

    t0 = time.time()
    result = subprocess.run(cmd, cwd=PROJECT_DIR)
    elapsed = time.time() - t0

    print()
    if result.returncode != 0:
        log_err(f"PyInstaller 退出码: {result.returncode}")
        sys.exit(result.returncode)

    if os.path.isfile(OUTPUT_BIN):
        size_mb = os.path.getsize(OUTPUT_BIN) / (1024 * 1024)
        log_ok(f"打包成功  ({elapsed:.1f}s)")
        log_ok(f"输出: {OUTPUT_BIN}")
        log_ok(f"大小: {size_mb:.1f} MB")
    else:
        log_err("打包似乎成功但未找到输出文件")
        sys.exit(1)


# ── 主流程 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="QtCoder 跨平台打包脚本")
    parser.add_argument("--clean", action="store_true",
                        help="仅清理 build/ 和 dist/")
    parser.add_argument("--no-clean", action="store_true",
                        help="打包前不清理旧文件")
    parser.add_argument("--download-ffmpeg", action="store_true",
                        help="仅下载 FFmpeg 到 vendor/ffmpeg/")
    args = parser.parse_args()

    system = platform.system()
    machine = platform.machine()

    print()
    print("=" * 55)
    print(f"  {APP_NAME} — Build  [{system} {machine}]")
    print("=" * 55)
    print()

    if args.clean:
        clean()
        return

    if args.download_ffmpeg:
        ensure_ffmpeg()
        return

    python = get_python()

    log("检查依赖 ...")
    check_pyinstaller(python)

    log("检查 FFmpeg ...")
    ensure_ffmpeg()

    if not args.no_clean:
        log("清理旧构建 ...")
        clean()

    log("开始打包 ...")
    build(python)

    log("复制 FFmpeg 到发行目录 ...")
    copy_ffmpeg()

    # 汇总
    print()
    print("-" * 55)
    log_ok("发行目录结构:")
    print(f"       dist/")
    print(f"       ├── {APP_NAME}{'.exe' if IS_WIN else ''}")
    print(f"       └── vendor/ffmpeg/")
    for f in sorted(os.listdir(VENDOR_FFMPEG_DST)):
        print(f"           ├── {f}")
    print()
    print("=" * 55)
    print("  Done!")
    print("=" * 55)
    print()


if __name__ == "__main__":
    main()
