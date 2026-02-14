# -*- coding: utf-8 -*-
"""SSH 密钥生成引擎 — 纯函数，无 UI 依赖"""

HAS_KEYGEN = False
try:
    from Crypto.PublicKey import RSA, ECC
    HAS_KEYGEN = True
except ImportError:
    try:
        from Cryptodome.PublicKey import RSA, ECC
        HAS_KEYGEN = True
    except ImportError:
        pass

KEY_TYPES = {
    'RSA-2048':   ('RSA', 2048),
    'RSA-3072':   ('RSA', 3072),
    'RSA-4096':   ('RSA', 4096),
    'Ed25519':    ('Ed25519', None),
    'ECDSA-P256': ('P-256', None),
    'ECDSA-P384': ('P-384', None),
}


def generate_keypair(key_type='RSA-2048', passphrase=None, comment=''):
    """生成密钥对，返回 (私钥PEM, 公钥OpenSSH)"""
    if not HAS_KEYGEN:
        raise RuntimeError("需要安装 pycryptodome:\npip install pycryptodome")

    algo, param = KEY_TYPES[key_type]

    if algo == 'RSA':
        key = RSA.generate(param)
        if passphrase:
            private_pem = key.export_key(
                format='PEM', passphrase=passphrase,
                protection='scryptAndAES128-CBC'
            )
        else:
            private_pem = key.export_key(format='PEM')
        public_key = key.publickey().export_key(format='OpenSSH')
    else:
        # Ed25519 / ECDSA (P-256, P-384)
        curve = algo
        key = ECC.generate(curve=curve)
        if passphrase:
            private_pem = key.export_key(
                format='PEM', passphrase=passphrase,
                protection='scryptAndAES128-CBC'
            )
        else:
            private_pem = key.export_key(format='PEM')
        public_key = key.public_key().export_key(format='OpenSSH')

    # 统一转为 str
    if isinstance(private_pem, bytes):
        private_pem = private_pem.decode('utf-8')
    if isinstance(public_key, bytes):
        public_key = public_key.decode('utf-8')

    if comment:
        public_key = f"{public_key} {comment}"

    return private_pem, public_key
