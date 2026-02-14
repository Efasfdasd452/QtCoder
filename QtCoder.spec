# -*- mode: python ; coding: utf-8 -*-
# QtCoder - PyInstaller 打包配置
#
# 用法:
#   .venv/Scripts/pyinstaller QtCoder.spec --noconfirm
#   或直接运行 build.bat

import os
import sys

block_cipher = None

# ── 项目根目录 ────────────────────────────────────────────────
PROJECT_DIR = os.path.abspath(SPECPATH)

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
    'matplotlib', 'numpy', 'pandas', 'scipy',
    'PIL', 'cv2',
    'unittest', 'test', 'tests',
    'setuptools', 'pkg_resources',
    'distutils',
    'xmlrpc', 'pydoc',
]

# ══════════════════════════════════════════════════════════════
#  Analysis
# ══════════════════════════════════════════════════════════════
a = Analysis(
    ['main.py'],
    pathex=[PROJECT_DIR],
    binaries=[],
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
#  EXE (单文件输出)
# ══════════════════════════════════════════════════════════════
# 如果项目根目录有 QtCoder.ico 则使用，否则无图标
_icon = os.path.join(PROJECT_DIR, 'QtCoder.ico')
_icon_param = [_icon] if os.path.isfile(_icon) else []

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
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
