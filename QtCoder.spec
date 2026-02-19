# -*- mode: python ; coding: utf-8 -*-
# QtCoder - PyInstaller 打包配置 (文件夹模式)
#
# 用法:
#   .venv/Scripts/pyinstaller QtCoder.spec --noconfirm
#   或运行 python build.py

import os
import sys
import platform

block_cipher = None

# ── 项目根目录 ────────────────────────────────────────────────
PROJECT_DIR = os.path.abspath(SPECPATH)

# ── 平台判断与 FFmpeg 路径 ────────────────────────────────────
IS_WIN = os.name == 'nt'
if IS_WIN:
    _ffmpeg_src = os.path.join(PROJECT_DIR, 'vendor', 'ffmpeg', 'bin')
else:
    _ffmpeg_src = os.path.join(PROJECT_DIR, 'linux_ffmpeg', 'ffmpeg', 'bin')

# 收集 FFmpeg 二进制文件 → 打包后放在 ffmpeg/ 目录下
_ffmpeg_binaries = []
if os.path.isdir(_ffmpeg_src):
    for f in os.listdir(_ffmpeg_src):
        fp = os.path.join(_ffmpeg_src, f)
        if os.path.isfile(fp):
            _ffmpeg_binaries.append((fp, 'ffmpeg'))
else:
    print(f"[WARN] FFmpeg 目录不存在: {_ffmpeg_src}")
    print(f"[WARN] 打包后将不包含 FFmpeg，视频功能不可用")

# ── Hidden Imports ────────────────────────────────────────────
# PyInstaller 无法自动检测的模块
hidden_imports = [
    # ── PyCryptodome ─────────────────────────────────────────
    'Crypto',
    'Crypto.Cipher',
    'Crypto.Cipher.AES',
    'Crypto.Cipher.DES',
    'Crypto.Cipher.DES3',
    'Crypto.Cipher.Blowfish',
    'Crypto.Cipher.CAST',
    'Crypto.Cipher.ARC2',
    'Crypto.Cipher.ARC4',
    'Crypto.Cipher.ChaCha20',
    'Crypto.Cipher.ChaCha20_Poly1305',
    'Crypto.Cipher.Salsa20',
    'Crypto.Hash',
    'Crypto.Hash.MD5',
    'Crypto.Hash.SHA1',
    'Crypto.Hash.SHA224',
    'Crypto.Hash.SHA256',
    'Crypto.Hash.SHA384',
    'Crypto.Hash.SHA512',
    'Crypto.Hash.SHA3_256',
    'Crypto.Hash.SHA3_512',
    'Crypto.Hash.BLAKE2b',
    'Crypto.Hash.BLAKE2s',
    'Crypto.Hash.HMAC',
    'Crypto.Hash.SHAKE128',
    'Crypto.Hash.SHAKE256',
    'Crypto.PublicKey',
    'Crypto.PublicKey.RSA',
    'Crypto.PublicKey.ECC',
    'Crypto.IO',
    'Crypto.IO.PEM',
    'Crypto.IO.PKCS8',
    'Crypto.Util',
    'Crypto.Util.Padding',
    'Crypto.Util.Counter',
    'Crypto.Random',

    # ── zhconv ───────────────────────────────────────────────
    'zhconv',
    'zhconv.zhconv',

    # ── aiohttp + socks ─────────────────────────────────────
    'aiohttp',
    'aiohttp.web',
    'aiohttp.client',
    'aiohttp.connector',
    'aiohttp.resolver',
    'aiohttp.tracing',
    'aiohttp_socks',

    # ── lxml ─────────────────────────────────────────────────
    'lxml',
    'lxml.etree',
    'lxml.html',
    'lxml._elementpath',

    # ── chardet ─────────────────────────────────────────────
    'chardet',
    'chardet.universaldetector',

    # ── cryptography ─────────────────────────────────────────
    'cryptography',
    'cryptography.hazmat',
    'cryptography.hazmat.primitives',
    'cryptography.hazmat.primitives.asymmetric',
    'cryptography.hazmat.primitives.asymmetric.rsa',
    'cryptography.hazmat.primitives.asymmetric.ec',
    'cryptography.hazmat.primitives.asymmetric.x25519',
    'cryptography.hazmat.primitives.asymmetric.ed25519',
    'cryptography.hazmat.primitives.asymmetric.x448',
    'cryptography.hazmat.primitives.asymmetric.ed448',
    'cryptography.hazmat.primitives.serialization',
    'cryptography.hazmat.backends',
    'cffi',
    '_cffi_backend',

    # ── 标准库（偶尔漏检的模块）────────────────────────────
    'asyncio',
    'ssl',
    'socket',
    'hashlib',
    'json',
    'uuid',
    're',
    'difflib',
    'html.parser',

    # ── 项目内部模块 ─────────────────────────────────────────
    'core.encoding',
    'core.crypto',
    'core.hashing',
    'core.json_fmt',
    'core.uuid_gen',
    'core.ssh_keygen',
    'core.regex_tester',
    'core.string_diff',
    'core.zh_convert',
    'core.mojibake_fixer',
    'core.port_scanner',
    'core.proxy_tester',
    'core.html_tools',
    'core.openssl_keygen',
    'core.cipher_identifier',
    'core.curl_converter',
    'core.curl_converter.parser',
    'core.curl_converter.generators',
    'core.curl_converter.generators.python_gen',
    'core.curl_converter.generators.javascript_gen',
    'core.curl_converter.generators.nodejs_gen',
    'core.curl_converter.generators.php_gen',
    'core.curl_converter.generators.java_gen',
    'core.curl_converter.generators.csharp_gen',
    'core.curl_converter.generators.ruby_gen',
    'core.curl_converter.generators.rust_gen',
    'core.curl_converter.generators.go_gen',
    'core.curl_converter.generators.wget_gen',
    'core.curl_converter.generators.httpie_gen',
    'core.curl_converter.generators.powershell_gen',

    'ui.main_window',
    'ui.panels.base_panel',
    'ui.panels.codec_panel',
    'ui.panels.crypto_panel',
    'ui.panels.hash_panel',
    'ui.panels.curl_panel',
    'ui.panels.uuid_panel',
    'ui.panels.ssh_panel',
    'ui.panels.regex_panel',
    'ui.panels.diff_panel',
    'ui.panels.json_panel',
    'ui.panels.zhconv_panel',
    'ui.panels.mojibake_panel',
    'ui.panels.portscan_panel',
    'ui.panels.proxy_panel',
    'ui.panels.html_panel',
    'ui.panels.openssl_panel',
    'ui.panels.identifier_panel',
    'ui.panels.watermark_panel',
    'ui.panels.firewall_panel',
    'ui.panels.video_panel',
    'ui.panels.image_panel',

    # ── 图片压缩 (Pillow) ───────────────────────────────────
    'PIL',
    'PIL.Image',
    'PIL.JpegImagePlugin',
    'PIL.PngImagePlugin',
    'PIL.WebPImagePlugin',
    'core.image_compress',

    # ── 水印检测 ───────────────────────────────────────────
    'core.watermark_detector',
    'core.firewall_gen',
    'core.video_compress',
    'core.ffmpeg_downloader',

    # ── blind_watermark ────────────────────────────────────
    'blind_watermark',
    'blind_watermark.blind_watermark',
    'blind_watermark.bwm_core',
    'blind_watermark.pool',
    'blind_watermark.recover',
    'blind_watermark.att',
    'blind_watermark.version',
    'blind_watermark.cli_tools',

    # ── numpy ──────────────────────────────────────────────
    'numpy',
    'numpy.core',
    'numpy.core._methods',
    'numpy.lib',
    'numpy.lib.format',
    'numpy.fft',
    'numpy.linalg',
    'numpy.random',

    # ── opencv ─────────────────────────────────────────────
    'cv2',

    # ── PyWavelets ─────────────────────────────────────────
    'pywt',
    'pywt._extensions',
    'pywt._extensions._pywt',
    'pywt._extensions._dwt',
    'pywt._extensions._swt',
]

# ── 数据文件 ──────────────────────────────────────────────────
# zhconv 需要编码映射表数据
datas = []
try:
    import zhconv as _zhconv
    zhconv_dir = os.path.dirname(_zhconv.__file__)
    # 收集 zhconv 的所有数据文件
    for f in os.listdir(zhconv_dir):
        if f.endswith(('.json', '.dat', '.pkl', '.py')):
            src = os.path.join(zhconv_dir, f)
            datas.append((src, 'zhconv'))
except ImportError:
    pass

# ── 排除不需要的模块（减小体积）────────────────────────────
excludes = [
    'tkinter', '_tkinter',
    'matplotlib', 'pandas', 'scipy',
    'unittest', 'test', 'tests',
    # 注意: setuptools / distutils / pkg_resources 不能排除,
    # PyInstaller 6.x + Python 3.12 的 hook-distutils 依赖 setuptools
    'xmlrpc', 'pydoc',
]

# ══════════════════════════════════════════════════════════════
#  Analysis
# ══════════════════════════════════════════════════════════════
a = Analysis(
    ['main.py'],
    pathex=[PROJECT_DIR],
    binaries=_ffmpeg_binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)

# ══════════════════════════════════════════════════════════════
#  PYZ (Python bytecode archive)
# ══════════════════════════════════════════════════════════════
pyz = PYZ(a.pure, cipher=block_cipher)

# ══════════════════════════════════════════════════════════════
#  EXE
# ══════════════════════════════════════════════════════════════
# 如果项目根目录有 QtCoder.ico 则使用，否则无图标
_icon = os.path.join(PROJECT_DIR, 'QtCoder.ico')
_icon_param = [_icon] if os.path.isfile(_icon) else []

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # 文件夹模式：二进制文件由 COLLECT 收集
    name='QtCoder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                  # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_param,
)

# ══════════════════════════════════════════════════════════════
#  COLLECT (文件夹打包)
# ══════════════════════════════════════════════════════════════
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='QtCoder',
)
