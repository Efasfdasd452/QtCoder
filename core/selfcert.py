# -*- coding: utf-8 -*-
"""网站自签名 X.509 证书生成器

使用 cryptography 库生成含 SAN 扩展的 X.509 v3 自签名证书，
兼容现代浏览器 (Chrome/Firefox/Edge)。

支持密钥类型: RSA-2048 / RSA-4096 / EC P-256 / EC P-384
"""

import datetime
import ipaddress
from typing import List, Optional, Tuple

HAS_CRYPTO = False
try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, ec
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, NoEncryption,
    )
    HAS_CRYPTO = True
except ImportError:
    pass

KEY_TYPE_NAMES = ["RSA-2048", "RSA-4096", "EC P-256", "EC P-384"]


def _gen_key(key_type: str):
    if key_type == "RSA-2048":
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)
    if key_type == "RSA-4096":
        return rsa.generate_private_key(public_exponent=65537, key_size=4096)
    if key_type == "EC P-256":
        return ec.generate_private_key(ec.SECP256R1())
    if key_type == "EC P-384":
        return ec.generate_private_key(ec.SECP384R1())
    raise ValueError(f"不支持的密钥类型: {key_type}")


def _parse_san(san_str: str, cn: str):
    """解析 SAN 字符串，返回 (dns_list, ip_list)。CN 自动加入 DNS。"""
    dns_seen = set()
    dns_list: List[str] = []
    ip_list:  List[ipaddress.IPv4Address] = []

    def add_dns(name: str):
        name = name.strip()
        if name and name not in dns_seen:
            dns_seen.add(name)
            dns_list.append(name)

    add_dns(cn)

    for entry in san_str.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            ip_list.append(ipaddress.ip_address(entry))
        except ValueError:
            add_dns(entry)

    return dns_list, ip_list


def generate_cert(
    common_name: str,
    san_extra: str = "",
    org: str = "My Organization",
    country: str = "CN",
    valid_days: int = 365,
    key_type: str = "RSA-2048",
) -> dict:
    """生成自签名证书。

    Returns dict:
        cert_pem      : str  — PEM 格式证书
        key_pem       : str  — PEM 格式私钥 (PKCS#1/SEC1, 无密码)
        cert_info     : str  — 人类可读证书摘要
        openssl_cmd   : str  — 等效 openssl 命令
        fingerprint   : str  — SHA-256 指纹（冒号分隔十六进制）
    """
    if not HAS_CRYPTO:
        raise RuntimeError("需要 cryptography 库: pip install cryptography")
    if not common_name.strip():
        raise ValueError("域名 (Common Name) 不能为空")

    country = (country.strip().upper() or "CN")[:2]
    org = org.strip() or "My Organization"

    priv_key = _gen_key(key_type)
    is_rsa   = key_type.startswith("RSA")

    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME,      country),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, org),
        x509.NameAttribute(NameOID.COMMON_NAME,       common_name),
    ])

    now        = datetime.datetime.now(datetime.timezone.utc)
    not_before = now - datetime.timedelta(seconds=10)
    not_after  = now + datetime.timedelta(days=valid_days)

    dns_list, ip_list = _parse_san(san_extra, common_name)
    san_entries = [x509.DNSName(d) for d in dns_list] + \
                  [x509.IPAddress(ip) for ip in ip_list]

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(priv_key.public_key())
        .serial_number(x509.random_serial_number())
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=is_rsa,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH,
                ExtendedKeyUsageOID.CLIENT_AUTH,
            ]), critical=False)
    )

    if san_entries:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(san_entries), critical=False)

    # cryptography >= 42 推荐 not_valid_before_utc；旧版用 not_valid_before
    if hasattr(builder, "not_valid_before_utc"):
        builder = builder.not_valid_before_utc(not_before).not_valid_after_utc(not_after)
    else:
        builder = (builder
                   .not_valid_before(not_before.replace(tzinfo=None))
                   .not_valid_after(not_after.replace(tzinfo=None)))

    cert = builder.sign(priv_key, hashes.SHA256())

    cert_pem = cert.public_bytes(Encoding.PEM).decode("utf-8")
    key_pem  = priv_key.private_bytes(
        Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()
    ).decode("utf-8")

    fp_bytes = cert.fingerprint(hashes.SHA256())
    fp_hex   = ":".join(f"{b:02X}" for b in fp_bytes)

    # ── 证书摘要 ─────────────────────────────────────────────
    san_display = ", ".join(
        str(e.value) for e in san_entries
    ) if san_entries else "(无)"

    nb_str = not_before.strftime("%Y-%m-%d %H:%M:%S UTC")
    na_str = not_after.strftime("%Y-%m-%d %H:%M:%S UTC")

    info_lines = [
        f"域名 (CN)  :  {common_name}",
        f"SAN        :  {san_display}",
        f"组织 (O)   :  {org}",
        f"国家 (C)   :  {country}",
        f"密钥类型   :  {key_type}",
        f"有效期     :  {valid_days} 天",
        f"生效时间   :  {nb_str}",
        f"到期时间   :  {na_str}",
        f"序列号     :  {cert.serial_number}",
        f"SHA-256 指纹:",
        f"  {fp_hex}",
    ]

    # ── 等效 openssl 命令 ─────────────────────────────────────
    key_cmd = {
        "RSA-2048": "openssl genrsa -out server.key 2048",
        "RSA-4096": "openssl genrsa -out server.key 4096",
        "EC P-256":  "openssl ecparam -genkey -name prime256v1 -noout -out server.key",
        "EC P-384":  "openssl ecparam -genkey -name secp384r1  -noout -out server.key",
    }[key_type]

    san_openssl_parts = [f"DNS:{d}" for d in dns_list] + \
                        [f"IP:{ip}"  for ip in ip_list]
    san_openssl = ",".join(san_openssl_parts) if san_openssl_parts else f"DNS:{common_name}"

    openssl_cmd = f"""\
# 生成自签名证书（等效 openssl 命令）
# 适用于 nginx / Apache / 本地开发 HTTPS

# ① 生成私钥
{key_cmd}

# ② 创建 SAN 配置文件
cat > san.cnf << 'EOF'
[req]
default_bits       = 2048
prompt             = no
default_md         = sha256
distinguished_name = dn
req_extensions     = v3_req

[dn]
C  = {country}
O  = {org}
CN = {common_name}

[v3_req]
subjectAltName = {san_openssl}
EOF

# ③ 生成自签名证书（一步完成）
openssl req -new -x509 \\
    -key server.key \\
    -out server.crt \\
    -days {valid_days} \\
    -config san.cnf \\
    -extensions v3_req

# ④ 验证
openssl x509 -in server.crt -text -noout | grep -A3 "Subject Alternative"
"""

    return {
        "cert_pem":    cert_pem,
        "key_pem":     key_pem,
        "cert_info":   "\n".join(info_lines),
        "openssl_cmd": openssl_cmd,
        "fingerprint": fp_hex,
    }
