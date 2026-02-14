# -*- coding: utf-8 -*-
"""OpenSSL 非对称密钥对生成引擎 — 使用 cryptography 库 (内部封装 OpenSSL)

支持密钥类型:
  - RSA:     2048 / 3072 / 4096
  - EC:      P-256 / P-384 / P-521
  - X25519:  密钥交换 (ECDH)
  - Ed25519: 数字签名 (EdDSA)
  - X448:    密钥交换
  - Ed448:   数字签名

输出格式:
  - Raw Base64url  (公钥原始字节, 如 Hw1sCTC9xVvgNWXhnRwxGXKc_unH_-...)
  - PEM            (PKCS#8 私钥 / SPKI 公钥)
  - DER            (二进制)
  - OpenSSH        (ssh-ed25519 AAAA...)
  - JWK 摘要       (JSON 格式)

同时支持检测并调用系统 openssl CLI。
"""

import base64
import json
import os
import subprocess
import shutil

HAS_CRYPTO_LIB = False
try:
    from cryptography.hazmat.primitives.asymmetric import (
        rsa, ec, x25519, ed25519, x448, ed448,
    )
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, PublicFormat,
        BestAvailableEncryption, NoEncryption,
    )
    HAS_CRYPTO_LIB = True
except ImportError:
    pass

# ═════════════════════════════════════════════════════════════
#  密钥类型配置
# ═════════════════════════════════════════════════════════════
KEY_TYPES = {
    'RSA-2048':   {'family': 'rsa',     'bits': 2048},
    'RSA-3072':   {'family': 'rsa',     'bits': 3072},
    'RSA-4096':   {'family': 'rsa',     'bits': 4096},
    'EC P-256':   {'family': 'ec',      'curve': ec.SECP256R1()   if HAS_CRYPTO_LIB else None},
    'EC P-384':   {'family': 'ec',      'curve': ec.SECP384R1()   if HAS_CRYPTO_LIB else None},
    'EC P-521':   {'family': 'ec',      'curve': ec.SECP521R1()   if HAS_CRYPTO_LIB else None},
    'X25519':     {'family': 'x25519'},
    'Ed25519':    {'family': 'ed25519'},
    'X448':       {'family': 'x448'},
    'Ed448':      {'family': 'ed448'},
}

KEY_TYPE_NAMES = list(KEY_TYPES.keys())

# ── 哪些类型支持 Raw 公钥 ────────────────────────────────────
RAW_SUPPORTED = {'x25519', 'ed25519', 'x448', 'ed448'}

# ── 哪些类型支持 OpenSSH 格式 ─────────────────────────────────
OPENSSH_SUPPORTED = {'rsa', 'ec', 'ed25519'}

# ═════════════════════════════════════════════════════════════
#  生成密钥对
# ═════════════════════════════════════════════════════════════

def generate_keypair(key_type='X25519', passphrase=None):
    """生成非对称密钥对。

    返回 dict:
        key_type, family,
        private_pem, public_pem,
        private_der, public_der,
        public_raw_b64url,   # Base64url 原始公钥 (X25519/Ed25519/X448/Ed448)
        public_openssh,      # OpenSSH 格式 (RSA/EC/Ed25519)
        public_jwk,          # JWK JSON 摘要
        key_info,            # 文字信息
        openssl_cmd,         # 等效的 openssl 命令
    """
    if not HAS_CRYPTO_LIB:
        raise RuntimeError(
            "需要安装 cryptography 库:\npip install cryptography")

    cfg = KEY_TYPES[key_type]
    family = cfg['family']

    # ── 生成私钥 ─────────────────────────────────────────────
    if family == 'rsa':
        priv_key = rsa.generate_private_key(
            public_exponent=65537, key_size=cfg['bits'])
    elif family == 'ec':
        priv_key = ec.generate_private_key(cfg['curve'])
    elif family == 'x25519':
        priv_key = x25519.X25519PrivateKey.generate()
    elif family == 'ed25519':
        priv_key = ed25519.Ed25519PrivateKey.generate()
    elif family == 'x448':
        priv_key = x448.X448PrivateKey.generate()
    elif family == 'ed448':
        priv_key = ed448.Ed448PrivateKey.generate()
    else:
        raise ValueError(f"不支持的密钥类型: {key_type}")

    pub_key = priv_key.public_key()

    # ── 加密参数 ─────────────────────────────────────────────
    enc = BestAvailableEncryption(
        passphrase.encode('utf-8')) if passphrase else NoEncryption()

    # ── 私钥 PEM (PKCS#8) ────────────────────────────────────
    priv_pem = priv_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, enc
    ).decode('utf-8')

    # ── 私钥 DER ─────────────────────────────────────────────
    priv_der = priv_key.private_bytes(
        Encoding.DER, PrivateFormat.PKCS8,
        NoEncryption()  # DER 通常不加密
    )

    # ── 公钥 PEM (SPKI) ─────────────────────────────────────
    pub_pem = pub_key.public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

    # ── 公钥 DER ─────────────────────────────────────────────
    pub_der = pub_key.public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo
    )

    # ── 公钥 Raw (Base64url) ─────────────────────────────────
    raw_b64url = ''
    if family in RAW_SUPPORTED:
        raw_bytes = pub_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        raw_b64url = base64.urlsafe_b64encode(raw_bytes).decode().rstrip('=')

    # ── 公钥 OpenSSH ─────────────────────────────────────────
    pub_openssh = ''
    if family in OPENSSH_SUPPORTED:
        try:
            pub_openssh = pub_key.public_bytes(
                Encoding.OpenSSH, PublicFormat.OpenSSH
            ).decode('utf-8')
        except (ValueError, TypeError):
            pass

    # ── JWK 摘要 ─────────────────────────────────────────────
    jwk = _build_jwk_summary(pub_key, family, key_type)

    # ── 密钥信息 ─────────────────────────────────────────────
    key_info = _build_key_info(key_type, family, cfg, pub_der)

    # ── 等效 openssl 命令 ────────────────────────────────────
    openssl_cmd = _build_openssl_cmd(key_type, family, cfg, passphrase)

    return {
        'key_type':          key_type,
        'family':            family,
        'private_pem':       priv_pem,
        'public_pem':        pub_pem,
        'private_der':       priv_der,
        'public_der':        pub_der,
        'public_raw_b64url': raw_b64url,
        'public_openssh':    pub_openssh,
        'public_jwk':        jwk,
        'key_info':          key_info,
        'openssl_cmd':       openssl_cmd,
    }


# ═════════════════════════════════════════════════════════════
#  OpenSSL CLI 集成
# ═════════════════════════════════════════════════════════════

def find_openssl():
    """查找系统上的 openssl 可执行文件。

    搜索顺序: PATH → Git for Windows → 项目 tools/ 目录
    返回路径字符串或 None。
    """
    # 1) PATH
    path = shutil.which('openssl')
    if path:
        return path

    # 2) Git for Windows 常见位置
    for git_dir in [
        r'C:\Program Files\Git\usr\bin',
        r'C:\Program Files (x86)\Git\usr\bin',
        os.path.expanduser(r'~\scoop\apps\git\current\usr\bin'),
    ]:
        candidate = os.path.join(git_dir, 'openssl.exe')
        if os.path.isfile(candidate):
            return candidate

    # 3) 项目 tools/ 目录
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tools_openssl = os.path.join(project_dir, 'tools', 'openssl.exe')
    if os.path.isfile(tools_openssl):
        return tools_openssl

    return None


def openssl_version():
    """获取 openssl 版本，找不到返回 None"""
    path = find_openssl()
    if not path:
        return None
    try:
        r = subprocess.run(
            [path, 'version'], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def openssl_generate(key_type, passphrase=None):
    """通过 openssl CLI 生成密钥对 (备用方案)。

    返回 dict: private_pem, public_pem, raw_b64url
    """
    path = find_openssl()
    if not path:
        raise RuntimeError("未找到 openssl，请安装 Git for Windows 或将 openssl.exe 放入 tools/ 目录")

    cfg = KEY_TYPES[key_type]
    family = cfg['family']

    # ── 构造 genpkey 命令 ─────────────────────────────────────
    cmd = [path, 'genpkey']
    if family == 'rsa':
        cmd += ['-algorithm', 'RSA', '-pkeyopt', f'rsa_keygen_bits:{cfg["bits"]}']
    elif family == 'ec':
        curve_name = {
            'EC P-256': 'P-256', 'EC P-384': 'P-384', 'EC P-521': 'P-521'
        }.get(key_type, 'P-256')
        cmd += ['-algorithm', 'EC', '-pkeyopt', f'ec_paramgen_curve:{curve_name}']
    elif family in ('x25519', 'ed25519', 'x448', 'ed448'):
        algo_map = {
            'x25519': 'X25519', 'ed25519': 'ED25519',
            'x448': 'X448', 'ed448': 'ED448',
        }
        cmd += ['-algorithm', algo_map[family]]

    if passphrase:
        cmd += ['-aes-256-cbc', '-pass', f'pass:{passphrase}']

    # 生成私钥
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"openssl genpkey 失败:\n{r.stderr}")
    priv_pem = r.stdout

    # 提取公钥
    cmd2 = [path, 'pkey', '-pubout']
    if passphrase:
        cmd2 += ['-passin', f'pass:{passphrase}']
    r2 = subprocess.run(
        cmd2, input=priv_pem, capture_output=True, text=True, timeout=10)
    if r2.returncode != 0:
        raise RuntimeError(f"openssl pkey -pubout 失败:\n{r2.stderr}")
    pub_pem = r2.stdout

    # 提取 raw 公钥 (DER → 跳过 header)
    raw_b64url = ''
    if family in RAW_SUPPORTED:
        cmd3 = [path, 'pkey', '-pubout', '-outform', 'DER']
        if passphrase:
            cmd3 += ['-passin', f'pass:{passphrase}']
        r3 = subprocess.run(
            cmd3, input=priv_pem.encode(),
            capture_output=True, timeout=10)
        if r3.returncode == 0 and r3.stdout:
            # DER 公钥: 固定 header + raw bytes
            der = r3.stdout
            # X25519/Ed25519: 12-byte header + 32-byte raw
            # X448: 12-byte header + 56-byte raw
            # Ed448: 12-byte header + 57-byte raw
            raw = der[12:] if len(der) > 12 else der
            raw_b64url = base64.urlsafe_b64encode(raw).decode().rstrip('=')

    return {
        'private_pem': priv_pem,
        'public_pem': pub_pem,
        'public_raw_b64url': raw_b64url,
    }


# ═════════════════════════════════════════════════════════════
#  辅助函数
# ═════════════════════════════════════════════════════════════

def _build_jwk_summary(pub_key, family, key_type):
    """构造 JWK 格式摘要"""
    try:
        if family == 'x25519':
            raw = pub_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
            return json.dumps({
                'kty': 'OKP', 'crv': 'X25519',
                'x': base64.urlsafe_b64encode(raw).decode().rstrip('='),
            }, indent=2)
        elif family == 'ed25519':
            raw = pub_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
            return json.dumps({
                'kty': 'OKP', 'crv': 'Ed25519',
                'x': base64.urlsafe_b64encode(raw).decode().rstrip('='),
            }, indent=2)
        elif family == 'ec':
            # EC 公钥 → 未压缩点
            der = pub_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
            curve_map = {
                'EC P-256': ('P-256', 32),
                'EC P-384': ('P-384', 48),
                'EC P-521': ('P-521', 66),
            }
            crv, size = curve_map.get(key_type, ('P-256', 32))
            # 从 DER 中提取 x, y 坐标（简化）
            return json.dumps({'kty': 'EC', 'crv': crv}, indent=2)
        elif family == 'rsa':
            return json.dumps({'kty': 'RSA', 'key_size': KEY_TYPES[key_type]['bits']}, indent=2)
        else:
            return '{}'
    except Exception:
        return '{}'


def _build_key_info(key_type, family, cfg, pub_der):
    """构造密钥信息字符串"""
    lines = [f"算法: {key_type}"]
    if family == 'rsa':
        lines.append(f"密钥长度: {cfg['bits']} bits")
        lines.append(f"公钥指数: 65537 (0x10001)")
    elif family == 'ec':
        curve_names = {
            'EC P-256': 'secp256r1 (NIST P-256)',
            'EC P-384': 'secp384r1 (NIST P-384)',
            'EC P-521': 'secp521r1 (NIST P-521)',
        }
        lines.append(f"曲线: {curve_names.get(key_type, '?')}")
    elif family in ('x25519', 'x448'):
        lines.append("用途: 密钥交换 (ECDH)")
        lines.append(f"公钥长度: {32 if family == 'x25519' else 56} bytes")
    elif family in ('ed25519', 'ed448'):
        lines.append("用途: 数字签名 (EdDSA)")
        lines.append(f"公钥长度: {32 if family == 'ed25519' else 57} bytes")

    lines.append(f"公钥 DER 长度: {len(pub_der)} bytes")
    return '\n'.join(lines)


def _build_openssl_cmd(key_type, family, cfg, passphrase):
    """构造等效的 openssl CLI 命令"""
    lines = ["# 等效 openssl 命令:"]

    # genpkey
    if family == 'rsa':
        lines.append(
            f"openssl genpkey -algorithm RSA "
            f"-pkeyopt rsa_keygen_bits:{cfg['bits']} -out private.pem")
    elif family == 'ec':
        curve = {'EC P-256': 'P-256', 'EC P-384': 'P-384',
                 'EC P-521': 'P-521'}.get(key_type, 'P-256')
        lines.append(
            f"openssl genpkey -algorithm EC "
            f"-pkeyopt ec_paramgen_curve:{curve} -out private.pem")
    else:
        algo = {'x25519': 'X25519', 'ed25519': 'ED25519',
                'x448': 'X448', 'ed448': 'ED448'}.get(family, family)
        lines.append(
            f"openssl genpkey -algorithm {algo} -out private.pem")

    if passphrase:
        lines[-1] += " -aes-256-cbc"

    # 公钥
    lines.append("openssl pkey -in private.pem -pubout -out public.pem")

    # Raw 公钥
    if family in RAW_SUPPORTED:
        lines.append(
            "# 提取 Raw 公钥 (Base64url):")
        lines.append(
            "openssl pkey -in private.pem -pubout -outform DER | "
            "tail -c 32 | base64 | tr '+/' '-_' | tr -d '='")

    return '\n'.join(lines)
