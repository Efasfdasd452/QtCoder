#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QtCoder 跨平台打包脚本

用法:
    python build.py                              # 自动检测本机平台，完整打包
    python build.py --target linux64             # 为 Linux x64 准备发行包
    python build.py --target win64               # 为 Windows x64 准备发行包
    python build.py --download-ffmpeg            # 仅下载本机平台的 FFmpeg
    python build.py --download-ffmpeg --target linuxarm64  # 下载指定平台的 FFmpeg
    python build.py --clean                      # 清理 build/dist

目标平台 (--target):
    win64       Windows x86_64
    winarm64    Windows ARM64
    linux64     Linux x86_64
    linuxarm64  Linux ARM64

说明:
    PyInstaller 不支持交叉编译。如果 --target 与当前系统不同，
    脚本会跳过 PyInstaller 打包步骤，只下载对应平台的 FFmpeg
    并准备 dist/ 目录结构。
    实际编译需在目标平台上执行，或使用 Docker / CI。
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
APP_NAME = "QtCoder"
IS_WIN = os.name == "nt"

if IS_WIN:
    VENV_PYTHON = os.path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe")
else:
    VENV_PYTHON = os.path.join(PROJECT_DIR, ".venv", "bin", "python")


# ── 日志 ──────────────────────────────────────────────────────

def log(msg):
    print(f"  [*] {msg}")


def log_ok(msg):
    print(f"  [OK] {msg}")


def log_warn(msg):
    print(f"  [WARN] {msg}")


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


# ── 平台判断 ─────────────────────────────────────────────────

def native_target() -> str:
    sys.path.insert(0, PROJECT_DIR)
    from core.ffmpeg_downloader import detect_native_target
    return detect_native_target()


def can_pyinstaller(target: str) -> bool:
    """判断当前环境能否用 PyInstaller 为 target 打包。"""
    try:
        nt = native_target()
    except RuntimeError:
        return False
    return nt == target


# ── FFmpeg 下载 ──────────────────────────────────────────────

def ensure_ffmpeg(target: str):
    """确保指定 target 的 ffmpeg 已下载。"""
    sys.path.insert(0, PROJECT_DIR)
    from core.ffmpeg_downloader import (
        get_ffmpeg_path, download_ffmpeg, get_download_url,
        get_download_size_hint, vendor_dir,
    )

    existing = get_ffmpeg_path(target)
    if existing:
        size_mb = os.path.getsize(existing) / (1024 * 1024)
        log_ok(f"FFmpeg [{target}] 已存在: {existing} ({size_mb:.0f} MB)")
        return

    url = get_download_url(target)
    size = get_download_size_hint(target)
    log(f"下载 FFmpeg [{target}] ({size}) ...")
    log(f"  {url}")

    def on_progress(downloaded, total):
        if total > 0:
            pct = downloaded / total * 100
            bar_len = 30
            filled = int(bar_len * downloaded / total)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"\r  [DL] {bar} {pct:5.1f}%  "
                  f"{downloaded // (1024*1024):>4d}/"
                  f"{total // (1024*1024)} MB", end="", flush=True)

    path = download_ffmpeg(target=target, progress_cb=on_progress)
    print()
    log_ok(f"FFmpeg [{target}] 已下载: {path}")


def get_ffmpeg_src_dir(target: str) -> str:
    """根据目标平台返回本地 FFmpeg 二进制文件的源目录。

    Windows 目标: vendor/ffmpeg/bin/
    Linux 目标:   linux_ffmpeg/ffmpeg/bin/
    """
    if target.startswith("win"):
        return os.path.join(PROJECT_DIR, "vendor", "ffmpeg", "bin")
    else:
        return os.path.join(PROJECT_DIR, "linux_ffmpeg", "ffmpeg", "bin")


def copy_ffmpeg(target: str):
    """将平台对应的 FFmpeg 二进制文件复制到 dist/QtCoder/ffmpeg/。"""
    src = get_ffmpeg_src_dir(target)
    dst = os.path.join(DIST_DIR, APP_NAME, "ffmpeg")

    if not os.path.isdir(src):
        log_err(f"未找到 FFmpeg [{target}]: {src}")
        log_err(f"请将对应平台的 FFmpeg 放入: {src}")
        return False
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    files = os.listdir(dst)
    total_size = sum(
        os.path.getsize(os.path.join(dst, f)) for f in files
    )
    log_ok(f"FFmpeg [{target}] 已复制到 dist/{APP_NAME}/ffmpeg/ "
           f"({len(files)} 个文件, {total_size / (1024*1024):.0f} MB)")
    return True


def copy_nmap():
    """将 bin/nmap/ 复制到 dist/QtCoder/bin/nmap/。

    若不存在则跳过并提示：端口扫描功能不可用。
    """
    src = os.path.join(PROJECT_DIR, "bin", "nmap")
    dst = os.path.join(DIST_DIR, APP_NAME, "bin", "nmap")

    if not os.path.isdir(src):
        log_warn("未找到 bin/nmap/，发行包中不包含 nmap，端口扫描功能不可用")
        return False

    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    total_size = 0
    file_count = 0
    for _root, _dirs, _files in os.walk(dst):
        for _f in _files:
            file_count += 1
            total_size += os.path.getsize(os.path.join(_root, _f))
    log_ok(f"nmap (bin/nmap/) 已复制到 dist/{APP_NAME}/bin/nmap/ "
           f"({file_count} 个文件, {total_size / (1024*1024):.1f} MB)")
    return True


def copy_calibre():
    """将 bin/calibre（Calibre 便携版安装包或已解压目录）复制到 dist/QtCoder/bin/calibre/。

    若项目根下存在 bin/calibre/，则整目录复制到发行包，便于用户从安装包内解压到短路径后指定。
    若不存在则跳过并提示：Calibre 需用户自行下载并解压到路径少于 59 字符的目录后，在软件内指定 ebook-convert.exe。
    """
    src = os.path.join(PROJECT_DIR, "bin", "calibre")
    dst = os.path.join(DIST_DIR, APP_NAME, "bin", "calibre")

    if not os.path.isdir(src):
        log_warn("未找到 bin/calibre/，发行包中不包含 Calibre")
        log("  用户需自行从 https://calibre-ebook.com/download 下载便携版，")
        log("  解压到路径少于 59 字符的目录（如 C:\\ec\\calibre），")
        log("  在「电子书转换」面板中点击「浏览」指定 ebook-convert.exe。")
        return False

    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    # 统计大小（仅顶层，避免过深遍历）
    total_size = 0
    file_count = 0
    for _root, _dirs, _files in os.walk(dst):
        for _f in _files:
            file_count += 1
            total_size += os.path.getsize(os.path.join(_root, _f))
    log_ok(f"Calibre (bin/calibre/) 已复制到 dist/{APP_NAME}/bin/calibre/ "
           f"({file_count} 个文件, {total_size / (1024*1024):.0f} MB)")
    log("  提示：若路径过长导致转换失败，请将 bin/calibre 内内容解压到短路径（如 C:\\ec\\calibre）后在软件中指定路径。")
    return True


# ── 清理 ─────────────────────────────────────────────────────

def clean():
    for d in [BUILD_DIR, DIST_DIR]:
        if os.path.isdir(d):
            shutil.rmtree(d)
            log(f"已删除 {os.path.basename(d)}/")
    log_ok("清理完成")


# ── PyInstaller 打包 ─────────────────────────────────────────

def build_exe(python, target: str):
    if not os.path.isfile(SPEC_FILE):
        log_err(f"未找到 spec 文件: {SPEC_FILE}")
        sys.exit(1)

    is_win_build = target.startswith("win")
    output_name = f"{APP_NAME}.exe" if is_win_build else APP_NAME
    # 文件夹模式: 输出到 dist/QtCoder/QtCoder.exe
    output_dir = os.path.join(DIST_DIR, APP_NAME)
    output_bin = os.path.join(output_dir, output_name)

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

    if os.path.isfile(output_bin):
        # 统计整个文件夹大小
        total_size = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, fns in os.walk(output_dir)
            for f in fns
        )
        log_ok(f"打包成功  ({elapsed:.1f}s)")
        log_ok(f"输出目录: {output_dir}")
        log_ok(f"总大小: {total_size / (1024 * 1024):.1f} MB")
        return output_bin
    else:
        log_err("打包似乎成功但未找到输出文件")
        sys.exit(1)


# ── 主流程 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="QtCoder 跨平台打包脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "目标平台:\n"
            "  win64       Windows x86_64\n"
            "  winarm64    Windows ARM64\n"
            "  linux64     Linux x86_64\n"
            "  linuxarm64  Linux ARM64\n"
            "\n"
            "示例:\n"
            "  python build.py                              # 本机打包\n"
            "  python build.py --target linux64             # Linux x64\n"
            "  python build.py --download-ffmpeg --target linuxarm64\n"
        ),
    )
    parser.add_argument(
        "--target", choices=["win64", "winarm64", "linux64", "linuxarm64"],
        default=None,
        help="目标平台 (默认: 自动检测本机)")
    parser.add_argument("--clean", action="store_true",
                        help="仅清理 build/ 和 dist/")
    parser.add_argument("--no-clean", action="store_true",
                        help="打包前不清理旧文件")
    parser.add_argument("--download-ffmpeg", action="store_true",
                        help="仅下载 FFmpeg (不打包)")
    args = parser.parse_args()

    target = args.target or native_target()
    is_native = can_pyinstaller(target)

    print()
    print("=" * 60)
    print(f"  {APP_NAME} — Build")
    print(f"  目标平台: {target}"
          f"{'  (本机)' if is_native else '  (交叉)'}")
    print(f"  当前系统: {platform.system()} {platform.machine()}")
    print("=" * 60)
    print()

    # ── 仅清理
    if args.clean:
        clean()
        return

    # ── 仅下载 FFmpeg
    if args.download_ffmpeg:
        ensure_ffmpeg(target)
        return

    # ── 完整打包流程
    python = get_python()

    log("检查依赖 ...")
    check_pyinstaller(python)

    log(f"检查 FFmpeg [{target}] ...")
    ffmpeg_src = get_ffmpeg_src_dir(target)
    if os.path.isdir(ffmpeg_src) and os.listdir(ffmpeg_src):
        files = os.listdir(ffmpeg_src)
        log_ok(f"FFmpeg [{target}] 已存在: {ffmpeg_src} ({len(files)} 个文件)")
    else:
        log_err(f"未找到 FFmpeg [{target}]: {ffmpeg_src}")
        if target.startswith("win"):
            log_err("请将 FFmpeg 放入 vendor/ffmpeg/bin/ 目录")
        else:
            log_err("请将 FFmpeg 放入 linux_ffmpeg/ffmpeg/bin/ 目录")
        sys.exit(1)

    if not args.no_clean:
        log("清理旧构建 ...")
        clean()

    if is_native:
        log("开始 PyInstaller 打包 ...")
        build_exe(python, target)
    else:
        log_warn(f"PyInstaller 不支持交叉编译")
        log_warn(f"当前系统无法直接打包 [{target}] 的可执行文件")
        log_warn(f"跳过打包步骤，仅准备 FFmpeg")
        log("")
        log("要完成打包，请在目标平台上执行:")
        if target.startswith("win"):
            log(f"  .venv\\Scripts\\python build.py --target {target}")
        else:
            log(f"  .venv/bin/python build.py --target {target}")
        log("")
        log("或使用 Docker:")
        log(f"  docker run --rm -v %cd%:/app -w /app python:3.12 "
            f"bash -c 'pip install -r requirements.txt && "
            f"python build.py --target {target}'")
        os.makedirs(DIST_DIR, exist_ok=True)

    log(f"复制 FFmpeg [{target}] 到发行目录 ...")
    copy_ffmpeg(target)

    log("复制 nmap（若存在）到发行目录 ...")
    has_nmap = copy_nmap()

    log("复制 Calibre（若存在）到发行目录 ...")
    has_calibre = copy_calibre()

    # ── 汇总
    is_win_build = target.startswith("win")
    bin_name = f"{APP_NAME}.exe" if is_win_build else APP_NAME
    ffmpeg_dst = os.path.join(DIST_DIR, APP_NAME, "ffmpeg")
    ffmpeg_files = sorted(os.listdir(ffmpeg_dst)) if os.path.isdir(ffmpeg_dst) else []
    nmap_dst = os.path.join(DIST_DIR, APP_NAME, "bin", "nmap")
    calibre_dst = os.path.join(DIST_DIR, APP_NAME, "bin", "calibre")

    print()
    print("-" * 60)
    log_ok(f"发行目录 [{target}]:")
    print(f"       dist/{APP_NAME}/")
    if is_native:
        print(f"       ├── {bin_name}")
    else:
        print(f"       ├── ({bin_name} — 需在目标平台编译)")
    print(f"       ├── ... (依赖库)")
    print(f"       ├── ffmpeg/")
    for i, f in enumerate(ffmpeg_files):
        prefix = "│   ├──" if i < len(ffmpeg_files) - 1 else "│   └──"
        print(f"       {prefix} {f}")
    if has_nmap and os.path.isdir(nmap_dst):
        print(f"       ├── bin/nmap/  (端口扫描)")
    else:
        print(f"       ├── (nmap 未包含，端口扫描功能不可用)")
    if has_calibre and os.path.isdir(calibre_dst):
        print(f"       └── bin/calibre/  (Calibre 安装包或已解压，路径过长时请在软件内指定短路径下的 ebook-convert.exe)")
    else:
        print(f"       └── (Calibre 未包含，需用户自行下载并解压到短路径后指定)")
    print()
    print("=" * 60)
    print("  Done!")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
