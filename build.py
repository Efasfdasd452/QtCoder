#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QtCoder 打包脚本 — 打包为单文件 EXE

用法:
    .venv/Scripts/python build.py          # 默认打包
    .venv/Scripts/python build.py --clean  # 仅清理 build/dist
"""

import os
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
OUTPUT_EXE = os.path.join(DIST_DIR, "QtCoder.exe")

# 虚拟环境路径
VENV_PYTHON = os.path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe")
VENV_PIP = os.path.join(PROJECT_DIR, ".venv", "Scripts", "pip.exe")


def log(msg):
    print(f"  [*] {msg}")


def log_ok(msg):
    print(f"  [OK] {msg}")


def log_err(msg):
    print(f"  [ERROR] {msg}", file=sys.stderr)


def get_python():
    """确定使用哪个 Python 解释器"""
    if os.path.isfile(VENV_PYTHON):
        return VENV_PYTHON
    log_err(f"虚拟环境未找到: {VENV_PYTHON}")
    log_err("请先创建: python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt")
    sys.exit(1)


def check_pyinstaller(python):
    """检查 PyInstaller 是否已安装，未安装则自动安装"""
    try:
        subprocess.run(
            [python, "-c", "import PyInstaller"],
            check=True, capture_output=True,
        )
        # 获取版本
        result = subprocess.run(
            [python, "-c", "import PyInstaller; print(PyInstaller.__version__)"],
            capture_output=True, text=True,
        )
        ver = result.stdout.strip()
        log_ok(f"PyInstaller {ver}")
    except subprocess.CalledProcessError:
        log("PyInstaller 未安装，正在安装 ...")
        subprocess.run(
            [python, "-m", "pip", "install", "pyinstaller"],
            check=True,
        )
        log_ok("PyInstaller 安装完成")


def clean():
    """清理构建产物"""
    for d in [BUILD_DIR, DIST_DIR]:
        if os.path.isdir(d):
            shutil.rmtree(d)
            log(f"已删除 {os.path.basename(d)}/")
    log_ok("清理完成")


def build(python):
    """执行 PyInstaller 打包"""
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

    if os.path.isfile(OUTPUT_EXE):
        size_mb = os.path.getsize(OUTPUT_EXE) / (1024 * 1024)
        log_ok(f"打包成功  ({elapsed:.1f}s)")
        log_ok(f"输出: {OUTPUT_EXE}")
        log_ok(f"大小: {size_mb:.1f} MB")
    else:
        log_err("打包似乎成功但未找到输出文件")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="QtCoder build script")
    parser.add_argument("--clean", action="store_true",
                        help="仅清理 build/ 和 dist/")
    parser.add_argument("--no-clean", action="store_true",
                        help="打包前不清理旧文件")
    args = parser.parse_args()

    print()
    print("=" * 50)
    print("  QtCoder — Build")
    print("=" * 50)
    print()

    if args.clean:
        clean()
        return

    python = get_python()

    log("检查依赖 ...")
    check_pyinstaller(python)

    if not args.no_clean:
        log("清理旧构建 ...")
        clean()

    log("开始打包 ...")
    build(python)

    print()
    print("=" * 50)
    print("  Done!")
    print("=" * 50)
    print()


if __name__ == "__main__":
    main()
