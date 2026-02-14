# -*- coding: utf-8 -*-
"""加密 / 哈希方式识别器 — 根据密文的文本特征推断可能的算法

识别策略 (按优先级):
1. 前缀匹配 — bcrypt $2b$, crypt $6$, Argon2, Django, Cisco …
2. 结构/格式匹配 — JWT, PGP, X.509, SSH, UUID, OpenSSL Salted …
3. Hex 串分析 — 长度 → 哈希算法; 块对齐 → AES/DES; 大小写特征
4. Base64 分析 — 解码后检测魔术字节、块大小对齐
5. Base32 / Base58 / Base85 检测
6. URL 编码检测
7. 统计分析 (字符集、Shannon 熵、可打印字符比例)

每条结果还附带 meta 字段，包含 charset / length / entropy 等摘要信息。
"""

import re
import math
import base64
import string
from collections import Counter

# ══════════════════════════════════════════════════════════════
#  公共接口
# ══════════════════════════════════════════════════════════════

def identify(text):
    """分析密文/哈希字符串，返回可能的算法列表。

    返回:
        {
          'results': [{'algorithm': str, 'confidence': str, 'detail': str}, ...],
          'meta': {
              'length': int,
              'entropy': float,
              'charset': str,          # 'hex' / 'base64' / 'base32' / 'printable' / 'binary' / 'mixed'
              'char_summary': str,     # 人类可读的字符集描述
          }
        }
        confidence: '高' / '中' / '低'

    向后兼容: 如果调用者只迭代 identify(text)，仍得到 results 列表。
    """
    text = text.strip()
    if not text:
        return _wrap([], text)

    results = []

    # ── 1. 前缀匹配 (Unix crypt / password hash) ────────────
    results.extend(_check_prefix(text))

    # ── 2. 格式匹配 ─────────────────────────────────────────
    results.extend(_check_format(text))

    # ── 3. 纯 Hex 串 ────────────────────────────────────────
    results.extend(_check_hex(text))

    # ── 4. Base64 特征 ───────────────────────────────────────
    results.extend(_check_base64(text))

    # ── 5. Base32 ────────────────────────────────────────────
    results.extend(_check_base32(text))

    # ── 6. Base58 ────────────────────────────────────────────
    results.extend(_check_base58(text))

    # ── 7. Base85 / Ascii85 ──────────────────────────────────
    results.extend(_check_base85(text))

    # ── 8. URL 编码 ──────────────────────────────────────────
    results.extend(_check_url_encoding(text))

    # ── 9. HTML 实体编码 ─────────────────────────────────────
    results.extend(_check_html_entity(text))

    # ── 10. Unicode 转义 ─────────────────────────────────────
    results.extend(_check_unicode_escape(text))

    # ── 如果没有匹配，做统计分析 ────────────────────────────
    if not results:
        results.extend(_statistical_analysis(text))

    # 去重 + 按置信度排序
    results = _dedupe_and_sort(results)

    # 如果已有高置信度结果, 移除兜底的 "未知 crypt 格式"
    has_high = any(r['confidence'] == '高' for r in results)
    if has_high:
        results = [r for r in results if r['algorithm'] != '未知 crypt 格式']

    return _wrap(results, text)


def _wrap(results, text):
    """将结果包装成 dict，同时保持可迭代兼容。"""
    meta = _compute_meta(text) if text else {
        'length': 0, 'entropy': 0.0,
        'charset': '', 'char_summary': '',
    }
    return IdentifyResult(results, meta)


class IdentifyResult:
    """同时表现为 list (向后兼容) 和带 meta 的结构。"""

    def __init__(self, results, meta):
        self.results = results
        self.meta = meta

    # 向后兼容: 可直接 for r in identify(text)
    def __iter__(self):
        return iter(self.results)

    def __len__(self):
        return len(self.results)

    def __bool__(self):
        return bool(self.results)

    def __getitem__(self, idx):
        return self.results[idx]


# ══════════════════════════════════════════════════════════════
#  辅助: 字符集 & 熵 & meta
# ══════════════════════════════════════════════════════════════

def _shannon_entropy(text):
    """计算 Shannon 信息熵 (bit/char)"""
    if not text:
        return 0.0
    freq = Counter(text)
    length = len(text)
    return -sum((c / length) * math.log2(c / length) for c in freq.values() if c > 0)


def _byte_entropy(data: bytes) -> float:
    """计算原始字节流的 Shannon 熵 (bit/byte), 取值 0~8。
    真正的加密数据接近 8.0, 普通文本通常 < 5.0, 纯 ASCII < 6.5。"""
    if not data or len(data) < 4:
        return 0.0
    freq = Counter(data)
    length = len(data)
    return -sum((c / length) * math.log2(c / length) for c in freq.values() if c > 0)


def _looks_like_encrypted_bytes(data: bytes) -> tuple:
    """分析原始字节流是否像加密数据。
    返回 (is_likely: bool, confidence: str, reason: str)

    核心思路:
    对于较短数据 (< 256 字节), 绝对字节熵受限于 log2(n), 不可能达到 8.0。
    因此使用 **熵比率 = 实际熵 / 理论最大熵** 来判断:
      - 真正的加密数据 ratio > 0.90
      - 编码/压缩数据 ratio ~0.70-0.85
      - 普通文本      ratio < 0.70

    额外参考:
      - 字节多样性 (unique_bytes / min(n, 256))
      - 高低半字节分布均匀度
    """
    n = len(data)
    if n < 8:
        return False, '', '数据太短'

    ent = _byte_entropy(data)
    freq = Counter(data)
    unique_bytes = len(freq)

    # 理论最大熵: min(log2(n), 8.0)
    max_ent = min(math.log2(n), 8.0) if n > 1 else 0.0
    ent_ratio = ent / max_ent if max_ent > 0 else 0.0

    # 字节多样性: 真正的加密数据, 在 n=96 时约有 80 种不同字节
    diversity = unique_bytes / min(n, 256)

    # 期望唯一字节数 (假设均匀分布): E[unique] = 256 * (1 - (255/256)^n)
    expected_unique = 256 * (1 - (255 / 256) ** n)
    unique_ratio = unique_bytes / expected_unique if expected_unique > 0 else 0

    ent_str = f'字节熵 {ent:.2f} (比率 {ent_ratio:.0%})'
    div_str = f'{unique_bytes} 种字节值'

    # ── 高置信度: 熵比率高 + 多样性好 ────────────────────────
    if ent_ratio >= 0.92 and unique_ratio >= 0.75 and n >= 16:
        return True, '高', f'{ent_str}, {div_str}, 高度随机'
    if ent_ratio >= 0.95 and n >= 16:
        return True, '高', f'{ent_str}, 高度随机'
    # 大数据量: 绝对熵也很可靠
    if ent >= 7.5 and n >= 256:
        return True, '高', f'{ent_str}, {div_str}, 高度随机 (大样本)'

    # ── 中置信度: 熵比率较高 ─────────────────────────────────
    if ent_ratio >= 0.85 and unique_ratio >= 0.60 and n >= 16:
        return True, '中', f'{ent_str}, {div_str}'
    if ent_ratio >= 0.90 and n >= 12:
        return True, '中', f'{ent_str}'
    if ent >= 7.0 and n >= 128:
        return True, '中', f'{ent_str}, {div_str}'

    # ── 低置信度: 中等熵, 但有加密可能 ──────────────────────
    if ent_ratio >= 0.75 and unique_ratio >= 0.50 and n >= 16:
        return True, '低', f'{ent_str}, {div_str}, 可能是加密数据'
    if ent_ratio >= 0.80 and n >= 8:
        return True, '低', f'{ent_str}, 可能是加密数据'

    return False, '', f'{ent_str}, {div_str}, 不太像加密数据'


def _classify_charset(text):
    """返回 (charset_id, human_description)"""
    clean = text.replace('\n', '').replace('\r', '').replace(' ', '')
    if not clean:
        return 'empty', '空'

    has_upper = bool(re.search(r'[A-Z]', clean))
    has_lower = bool(re.search(r'[a-z]', clean))
    has_digit = bool(re.search(r'[0-9]', clean))
    has_hex_only = bool(re.match(r'^[0-9a-fA-F]+$', clean))
    has_b64 = bool(re.match(r'^[A-Za-z0-9+/=]+$', clean))
    has_b64url = bool(re.match(r'^[A-Za-z0-9_\-=]+$', clean))
    has_b32 = bool(re.match(r'^[A-Z2-7=]+$', clean.upper()))

    parts = []
    if has_upper:
        parts.append('大写字母')
    if has_lower:
        parts.append('小写字母')
    if has_digit:
        parts.append('数字')
    specials = set(clean) - set(string.ascii_letters + string.digits)
    if specials:
        display = ''.join(sorted(specials)[:10])
        parts.append(f'特殊字符({display})')

    desc = ' + '.join(parts) if parts else '未知'

    if has_hex_only:
        if has_upper and not has_lower:
            return 'hex_upper', f'纯大写 Hex 字符 — {desc}'
        elif has_lower and not has_upper:
            return 'hex_lower', f'纯小写 Hex 字符 — {desc}'
        else:
            return 'hex', f'Hex 字符 — {desc}'
    if has_b64:
        return 'base64', f'Base64 字符集 — {desc}'
    if has_b64url:
        return 'base64url', f'Base64url 字符集 — {desc}'
    if has_b32:
        return 'base32', f'Base32 字符集 — {desc}'

    non_print = sum(1 for c in clean if ord(c) < 32 or ord(c) > 126)
    if non_print > len(clean) * 0.3:
        return 'binary', f'含大量不可打印字符 — {desc}'

    return 'mixed', desc


def _compute_meta(text):
    entropy = _shannon_entropy(text.strip())
    charset_id, char_summary = _classify_charset(text.strip())
    return {
        'length': len(text.strip()),
        'entropy': round(entropy, 3),
        'charset': charset_id,
        'char_summary': char_summary,
    }


# ══════════════════════════════════════════════════════════════
#  去重 + 排序
# ══════════════════════════════════════════════════════════════
_CONF_ORDER = {'高': 0, '中': 1, '低': 2}


def _dedupe_and_sort(results):
    seen = set()
    unique = []
    for r in results:
        key = r['algorithm']
        if key not in seen:
            seen.add(key)
            unique.append(r)
    unique.sort(key=lambda r: _CONF_ORDER.get(r['confidence'], 9))
    return unique


# ══════════════════════════════════════════════════════════════
#  1. 前缀匹配
# ══════════════════════════════════════════════════════════════
_PREFIX_PATTERNS = [
    # ── bcrypt ───────────────────────────────────────────────
    (r'^\$2[aby]\$\d{2}\$.{53}$',
     'bcrypt', '高', 'Blowfish 密码哈希 ($2b$), 60 字符'),
    (r'^\$2[aby]\$\d{2}\$',
     'bcrypt', '高', 'Blowfish 密码哈希 ($2a/$2b/$2y)'),

    # ── Unix SHA-512 crypt ───────────────────────────────────
    (r'^\$6\$rounds=\d+\$[^\$]+\$[A-Za-z0-9./]{86}$',
     'SHA-512 crypt', '高', 'Unix SHA-512 密码哈希 ($6$), 含 rounds 参数'),
    (r'^\$6\$[^\$]+\$[A-Za-z0-9./]{86}$',
     'SHA-512 crypt', '高', 'Unix SHA-512 密码哈希 ($6$)'),
    (r'^\$6\$',
     'SHA-512 crypt', '中', 'Unix SHA-512 密码哈希 ($6$) — 格式不完整'),

    # ── Unix SHA-256 crypt ───────────────────────────────────
    (r'^\$5\$[^\$]+\$[A-Za-z0-9./]{43}$',
     'SHA-256 crypt', '高', 'Unix SHA-256 密码哈希 ($5$)'),
    (r'^\$5\$',
     'SHA-256 crypt', '中', 'Unix SHA-256 密码哈希 ($5$)'),

    # ── Unix MD5 crypt ───────────────────────────────────────
    (r'^\$1\$[^\$]+\$[A-Za-z0-9./]{22}$',
     'MD5 crypt', '高', 'Unix MD5 密码哈希 ($1$)'),
    (r'^\$1\$',
     'MD5 crypt', '中', 'Unix MD5 密码哈希 ($1$)'),

    # ── yescrypt ─────────────────────────────────────────────
    (r'^\$y\$',
     'yescrypt', '高', 'yescrypt 密码哈希 ($y$)'),

    # ── Argon2 ───────────────────────────────────────────────
    (r'^\$argon2(id?|d)\$v=\d+\$m=\d+,t=\d+,p=\d+\$',
     'Argon2', '高', 'Argon2 密码哈希 (含完整参数)'),
    (r'^\$argon2(id?|d)\$',
     'Argon2', '高', 'Argon2 密码哈希'),

    # ── scrypt ───────────────────────────────────────────────
    (r'^\$scrypt\$',
     'scrypt', '高', 'scrypt 密码哈希'),
    (r'^\$7\$',
     'scrypt (crypt)', '高', 'scrypt Unix crypt 格式 ($7$)'),

    # ── PBKDF2 ───────────────────────────────────────────────
    (r'^\$pbkdf2-sha(256|512|1)\$\d+\$',
     'PBKDF2', '高', 'PBKDF2 密码哈希 (Passlib 格式)'),
    (r'^pbkdf2:sha\d+:\d+\$',
     'Werkzeug PBKDF2', '高', 'Flask/Werkzeug PBKDF2 密码哈希'),
    (r'^PBKDF2\$',
     'PBKDF2', '高', 'PBKDF2 密码哈希 (通用格式)'),

    # ── Apache APR1 ──────────────────────────────────────────
    (r'^\$apr1\$[^\$]+\$[A-Za-z0-9./]{22}$',
     'Apache APR1 (MD5)', '高', 'Apache MD5 密码哈希 ($apr1$)'),
    (r'^\$apr1\$',
     'Apache APR1 (MD5)', '高', 'Apache MD5 密码哈希'),

    # ── LDAP 格式 ────────────────────────────────────────────
    (r'^\{SHA\}[A-Za-z0-9+/=]{28}$',
     'SHA-1 (LDAP)', '高', 'LDAP SHA-1 密码哈希, 28 字符 Base64'),
    (r'^\{SHA\}',
     'SHA-1 (LDAP)', '高', 'LDAP SHA-1 密码哈希'),
    (r'^\{SSHA\}',
     'SSHA (LDAP)', '高', 'LDAP Salted SHA-1'),
    (r'^\{SHA256\}',
     'SHA-256 (LDAP)', '高', 'LDAP SHA-256 密码哈希'),
    (r'^\{SHA512\}',
     'SHA-512 (LDAP)', '高', 'LDAP SHA-512 密码哈希'),
    (r'^\{SSHA256\}',
     'SSHA-256 (LDAP)', '高', 'LDAP Salted SHA-256'),
    (r'^\{SSHA512\}',
     'SSHA-512 (LDAP)', '高', 'LDAP Salted SHA-512'),
    (r'^\{MD5\}',
     'MD5 (LDAP)', '高', 'LDAP MD5 密码哈希'),
    (r'^\{SMD5\}',
     'SMD5 (LDAP)', '高', 'LDAP Salted MD5'),
    (r'^\{CRYPT\}',
     'crypt (LDAP)', '高', 'LDAP crypt 封装'),
    (r'^\{BCRYPT\}',
     'bcrypt (LDAP)', '高', 'LDAP bcrypt 封装'),

    # ── MySQL ────────────────────────────────────────────────
    (r'^\*[A-Fa-f0-9]{40}$',
     'MySQL 密码哈希', '高', 'MySQL PASSWORD() SHA-1 双重哈希'),

    # ── MSSQL ────────────────────────────────────────────────
    (r'^0x0100[0-9A-Fa-f]{88}$',
     'MSSQL 2005 密码哈希', '高', 'MSSQL 2005 SHA-1 密码哈希'),
    (r'^0x0200[0-9A-Fa-f]{136}$',
     'MSSQL 2012+ 密码哈希', '高', 'MSSQL 2012+ SHA-512 密码哈希'),
    (r'^0x0100[0-9A-Fa-f]+$',
     'MSSQL 密码哈希（可能）', '中', 'MSSQL 密码哈希格式'),

    # ── Oracle ───────────────────────────────────────────────
    (r'^S:[A-Fa-f0-9]{60}$',
     'Oracle 11g+ 密码哈希', '高', 'Oracle 11g/12c SHA-1 密码哈希'),

    # ── Django ───────────────────────────────────────────────
    (r'^pbkdf2_sha256\$\d+\$',
     'Django PBKDF2-SHA256', '高', 'Django 默认密码哈希'),
    (r'^pbkdf2_sha1\$\d+\$',
     'Django PBKDF2-SHA1', '高', 'Django PBKDF2-SHA1 密码哈希'),
    (r'^sha1\$[^\$]+\$[0-9a-f]{40}$',
     'Django SHA-1', '高', 'Django 旧版 SHA-1 密码哈希'),
    (r'^md5\$[^\$]+\$[0-9a-f]{32}$',
     'Django MD5', '高', 'Django 旧版 MD5 密码哈希'),
    (r'^bcrypt_sha256\$\$',
     'Django bcrypt-SHA256', '高', 'Django bcrypt-SHA256 密码哈希'),
    (r'^bcrypt\$\$',
     'Django bcrypt', '高', 'Django bcrypt 密码哈希'),
    (r'^argon2\$argon2',
     'Django Argon2', '高', 'Django Argon2 密码哈希'),

    # ── WordPress / PHPass ───────────────────────────────────
    (r'^\$P\$[A-Za-z0-9./]{31}$',
     'WordPress (PHPass MD5)', '高', 'WordPress 密码哈希'),
    (r'^\$P\$',
     'PHPass (WordPress/Drupal)', '中', 'PHPass 便携式密码哈希'),
    (r'^\$H\$[A-Za-z0-9./]{31}$',
     'PHPass', '高', 'PHPass 便携式密码哈希'),
    (r'^\$H\$',
     'PHPass', '中', 'PHPass 便携式密码哈希'),

    # ── Drupal ───────────────────────────────────────────────
    (r'^\$S\$[A-Za-z0-9./]{52}$',
     'Drupal 7+ (SHA-512)', '高', 'Drupal 7 SHA-512 密码哈希'),
    (r'^\$S\$',
     'Drupal (SHA-512)', '中', 'Drupal SHA-512 密码哈希'),

    # ── Cisco ────────────────────────────────────────────────
    (r'^\$8\$[^\$]+\$[A-Za-z0-9./]{43}$',
     'Cisco Type 8 (PBKDF2-SHA256)', '高', 'Cisco IOS Type 8 密码哈希'),
    (r'^\$8\$',
     'Cisco Type 8', '中', 'Cisco IOS Type 8 密码哈希'),
    (r'^\$9\$[^\$]+\$[A-Za-z0-9./]+$',
     'Cisco Type 9 (scrypt)', '高', 'Cisco IOS Type 9 密码哈希'),
    (r'^\$9\$',
     'Cisco Type 9', '中', 'Cisco IOS Type 9 密码哈希'),

    # ── MD5 + salt ───────────────────────────────────────────
    (r'^[a-f0-9]{32}:[a-f0-9]+$',
     'MD5 + Salt', '中', 'MD5 哈希 + 盐值 (hex:hex)'),
    (r'^[a-f0-9]{32}:.+$',
     'MD5 + Salt', '低', 'MD5 哈希 + 盐值 (hash:salt)'),

    # ── SHA + salt ───────────────────────────────────────────
    (r'^[a-f0-9]{40}:[a-f0-9]+$',
     'SHA-1 + Salt', '中', 'SHA-1 哈希 + 盐值'),
    (r'^[a-f0-9]{64}:[a-f0-9]+$',
     'SHA-256 + Salt', '中', 'SHA-256 哈希 + 盐值'),
    (r'^[a-f0-9]{128}:[a-f0-9]+$',
     'SHA-512 + Salt', '中', 'SHA-512 哈希 + 盐值'),

    # ── Grub PBKDF2 ──────────────────────────────────────────
    (r'^grub\.pbkdf2\.sha512\.',
     'GRUB PBKDF2-SHA512', '高', 'GRUB2 PBKDF2-SHA512 密码哈希'),
]


def _check_prefix(text):
    results = []
    matched_algos = set()
    for pattern, algo, conf, detail in _PREFIX_PATTERNS:
        if algo in matched_algos:
            continue
        if re.match(pattern, text):
            results.append({
                'algorithm': algo,
                'confidence': conf,
                'detail': detail,
            })
            matched_algos.add(algo)
    return results


# ══════════════════════════════════════════════════════════════
#  2. 格式匹配
# ══════════════════════════════════════════════════════════════
def _check_format(text):
    results = []

    # ── JWT (JSON Web Token): xxx.xxx.xxx ────────────────────
    if re.match(r'^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$', text):
        parts = text.split('.')
        try:
            header_padded = parts[0] + '=' * (4 - len(parts[0]) % 4)
            decoded = base64.urlsafe_b64decode(header_padded).decode('utf-8')
            if '"alg"' in decoded or '"typ"' in decoded:
                algo_match = re.search(r'"alg"\s*:\s*"([^"]+)"', decoded)
                jwt_algo = algo_match.group(1) if algo_match else '?'
                results.append({
                    'algorithm': f'JWT ({jwt_algo})',
                    'confidence': '高',
                    'detail': f'JSON Web Token, 签名算法: {jwt_algo}, '
                              f'header 长度 {len(parts[0])}, '
                              f'payload 长度 {len(parts[1])}, '
                              f'signature 长度 {len(parts[2])}',
                })
            else:
                results.append({
                    'algorithm': 'JWT（可能）',
                    'confidence': '中',
                    'detail': f'三段式 Base64url 格式, header 可解码但无 alg/typ 字段',
                })
        except Exception:
            # header 不是有效 JSON -> 可能是 JWE 或其他 dot-separated 格式
            if len(parts[0]) > 10 and len(parts[1]) > 10 and len(parts[2]) > 10:
                results.append({
                    'algorithm': 'JWT / JWE（可能）',
                    'confidence': '低',
                    'detail': '三段式 dot-separated Base64url 格式',
                })

    # ── JWE (5 parts) ────────────────────────────────────────
    if re.match(r'^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$', text):
        results.append({
            'algorithm': 'JWE (JSON Web Encryption)',
            'confidence': '中',
            'detail': '五段式 dot-separated 格式, 符合 JWE Compact Serialization',
        })

    # ── PGP ──────────────────────────────────────────────────
    if '-----BEGIN PGP' in text:
        if 'MESSAGE' in text:
            results.append({'algorithm': 'PGP 加密消息', 'confidence': '高',
                            'detail': 'PGP/GPG 加密消息'})
        elif 'SIGNATURE' in text:
            results.append({'algorithm': 'PGP 签名', 'confidence': '高',
                            'detail': 'PGP/GPG 数字签名'})
        elif 'PUBLIC KEY' in text:
            results.append({'algorithm': 'PGP 公钥', 'confidence': '高',
                            'detail': 'PGP/GPG 公钥'})
        elif 'PRIVATE KEY' in text:
            results.append({'algorithm': 'PGP 私钥', 'confidence': '高',
                            'detail': 'PGP/GPG 私钥'})

    # ── X.509 / PEM 格式 ─────────────────────────────────────
    pem_types = [
        ('-----BEGIN CERTIFICATE-----', 'X.509 证书 (PEM)', 'X.509 PEM 格式数字证书'),
        ('-----BEGIN RSA PRIVATE KEY-----', 'RSA 私钥 (PKCS#1)', 'RSA PKCS#1 PEM 私钥'),
        ('-----BEGIN RSA PUBLIC KEY-----', 'RSA 公钥 (PKCS#1)', 'RSA PKCS#1 PEM 公钥'),
        ('-----BEGIN PRIVATE KEY-----', '私钥 (PKCS#8)', 'PKCS#8 PEM 私钥 (RSA/EC/Ed25519)'),
        ('-----BEGIN EC PRIVATE KEY-----', 'EC 私钥', '椭圆曲线 PEM 私钥'),
        ('-----BEGIN PUBLIC KEY-----', '公钥 (SPKI)', 'SubjectPublicKeyInfo PEM 公钥'),
        ('-----BEGIN ENCRYPTED PRIVATE KEY-----', '加密的 PKCS#8 私钥', '密码保护的 PKCS#8 PEM 私钥'),
        ('-----BEGIN CERTIFICATE REQUEST-----', 'CSR 证书签名请求', 'PKCS#10 证书签名请求'),
        ('-----BEGIN NEW CERTIFICATE REQUEST-----', 'CSR 证书签名请求', '证书签名请求 (Microsoft 格式)'),
        ('-----BEGIN X509 CRL-----', 'X.509 CRL', '证书吊销列表'),
        ('-----BEGIN DH PARAMETERS-----', 'DH 参数', 'Diffie-Hellman 参数'),
        ('-----BEGIN EC PARAMETERS-----', 'EC 参数', '椭圆曲线参数'),
        ('-----BEGIN OPENSSH PRIVATE KEY-----', 'OpenSSH 私钥', 'OpenSSH 新格式私钥'),
        ('-----BEGIN SSH2 PUBLIC KEY-----', 'SSH2 公钥', 'SSH2 格式公钥'),
        ('-----BEGIN DSA PRIVATE KEY-----', 'DSA 私钥', 'DSA PEM 私钥'),
    ]
    for marker, algo, detail in pem_types:
        if marker in text:
            results.append({'algorithm': algo, 'confidence': '高', 'detail': detail})

    if '-----BEGIN ENCRYPTED' in text and not any(m in text for m, _, _ in pem_types if 'ENCRYPTED' in m):
        results.append({'algorithm': '加密的 PEM 密钥', 'confidence': '高',
                        'detail': '密码保护的 PEM 编码密钥'})

    # ── SSH 公钥 ─────────────────────────────────────────────
    ssh_prefixes = ['ssh-rsa ', 'ssh-ed25519 ', 'ecdsa-sha2-', 'ssh-dss ']
    for prefix in ssh_prefixes:
        if text.startswith(prefix):
            algo_name = text.split()[0]
            results.append({'algorithm': f'SSH 公钥 ({algo_name})', 'confidence': '高',
                            'detail': 'OpenSSH 格式公钥'})
            break

    # ── UUID ─────────────────────────────────────────────────
    if re.match(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
        r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$', text):
        ver = text[14]
        results.append({'algorithm': f'UUID v{ver}', 'confidence': '高',
                        'detail': f'通用唯一标识符 v{ver}, 36 字符含连字符'})

    # ── Windows LM:NTLM 格式 ────────────────────────────────
    if re.match(r'^[a-fA-F0-9]{32}:[a-fA-F0-9]{32}$', text):
        results.append({'algorithm': 'LM:NTLM 密码哈希', 'confidence': '高',
                        'detail': 'Windows LM:NTLM 格式密码哈希 (32:32 hex)'})

    # ── Cisco Type 7 ─────────────────────────────────────────
    # Cisco Type 7: 2位数字偏移 + 偶数个hex字符, 通常总长 10~100
    # 排除: 纯数字开头但太长的字符串 (> 100), 或太短 (< 10)
    if re.match(r'^\d{2}[0-9A-Fa-f]{8,98}$', text) and 10 <= len(text) <= 100:
        first_two = int(text[:2])
        if first_two <= 52 and len(text) % 2 == 0:
            results.append({'algorithm': 'Cisco Type 7', 'confidence': '中',
                            'detail': f'Cisco Type 7 可逆密码 (起始偏移 {first_two}, {len(text)} 字符)'})

    # ── OpenSSL enc 格式 (Salted__) ──────────────────────────
    if text.startswith('U2FsdGVkX1'):
        results.append({'algorithm': 'OpenSSL enc (Salted)', 'confidence': '高',
                        'detail': 'OpenSSL enc 加密数据 (Base64 编码, 以 "Salted__" 开头)'})

    # ── Fernet token ─────────────────────────────────────────
    if re.match(r'^gAAAAA[A-Za-z0-9_-]+={0,2}$', text):
        results.append({'algorithm': 'Fernet Token', 'confidence': '高',
                        'detail': 'Python cryptography Fernet 令牌 (以 gAAAAA 开头)'})

    # ── AWS Key ──────────────────────────────────────────────
    if re.match(r'^AKIA[0-9A-Z]{16}$', text):
        results.append({'algorithm': 'AWS Access Key ID', 'confidence': '高',
                        'detail': 'AWS IAM Access Key ID (以 AKIA 开头, 20 字符)'})

    # ── GitHub Token ─────────────────────────────────────────
    if re.match(r'^gh[ps]_[A-Za-z0-9]{36,}$', text):
        results.append({'algorithm': 'GitHub Token', 'confidence': '高',
                        'detail': 'GitHub 个人访问令牌 (ghp_/ghs_ 前缀)'})
    if re.match(r'^github_pat_[A-Za-z0-9_]{22,}$', text):
        results.append({'algorithm': 'GitHub Fine-grained PAT', 'confidence': '高',
                        'detail': 'GitHub 细粒度个人访问令牌'})

    # ── Ethereum 地址 ────────────────────────────────────────
    if re.match(r'^0x[0-9a-fA-F]{40}$', text):
        results.append({'algorithm': 'Ethereum 地址', 'confidence': '中',
                        'detail': '以太坊地址 (0x + 40 hex = 20 字节)'})

    # ── MongoDB ObjectId ─────────────────────────────────────
    if re.match(r'^[0-9a-f]{24}$', text):
        results.append({'algorithm': 'MongoDB ObjectId', 'confidence': '中',
                        'detail': 'MongoDB ObjectId (24 hex = 12 字节)'})

    # ── Hash with $ separator (generic) ──────────────────────
    # 仅在 _check_format 自身没有高置信匹配时才添加;
    # 注意: 前缀匹配 (_check_prefix) 的结果不在这个 results 里,
    # 所以需要在主流程中二次过滤 (在 _dedupe_and_sort 之后)。
    # 但这里做第一层防护: 如果本函数已有高置信度结果, 就不添加。
    if re.match(r'^\$[a-zA-Z0-9]+\$', text) and not any(
        r['confidence'] == '高' for r in results):
        results.append({'algorithm': '未知 crypt 格式',
                        'confidence': '低',
                        'detail': f'以 $ 分隔的哈希格式, 可能是某种密码哈希'})

    return results


# ══════════════════════════════════════════════════════════════
#  3. Hex 串分析
# ══════════════════════════════════════════════════════════════
_HEX_LENGTHS = {
    8:   [('CRC-32', '中', 'CRC-32 校验值 (8 hex = 4 字节)'),
          ('Adler-32', '低', 'Adler-32 校验值 (8 hex)')],
    16:  [('半个 MD5 / MySQL OLD_PASSWORD', '低', '16 hex = 8 字节'),
          ('SipHash-64', '低', 'SipHash-2-4 (64 bit)')],
    24:  [('MongoDB ObjectId', '中', 'MongoDB ObjectId (24 hex = 12 字节)')],
    32:  [('MD5', '高', 'MD5 哈希 (128 bit = 32 hex)'),
          ('NTLM', '中', 'Windows NTLM 哈希 (32 hex)'),
          ('MD4', '低', 'MD4 哈希 (32 hex)'),
          ('MD2', '低', 'MD2 哈希 (32 hex)')],
    40:  [('SHA-1', '高', 'SHA-1 哈希 (160 bit = 40 hex)'),
          ('RIPEMD-160', '低', 'RIPEMD-160 哈希 (40 hex)'),
          ('HAS-160', '低', 'HAS-160 哈希 (40 hex)')],
    48:  [('Tiger-192', '低', 'Tiger/Tiger2 哈希 (192 bit = 48 hex)'),
          ('HAVAL-192', '低', 'HAVAL-192 哈希 (48 hex)')],
    56:  [('SHA-224', '高', 'SHA-224 哈希 (224 bit = 56 hex)'),
          ('SHA3-224', '中', 'SHA3-224 哈希 (56 hex)'),
          ('HAVAL-224', '低', 'HAVAL-224 哈希 (56 hex)')],
    64:  [('SHA-256', '高', 'SHA-256 哈希 (256 bit = 64 hex)'),
          ('SHA3-256', '中', 'SHA3-256 哈希 (64 hex)'),
          ('BLAKE2s-256', '低', 'BLAKE2s-256 哈希 (64 hex)'),
          ('GOST R 34.11-94', '低', 'GOST 哈希 (64 hex)'),
          ('Snefru-256', '低', 'Snefru-256 哈希 (64 hex)')],
    80:  [('RIPEMD-320', '低', 'RIPEMD-320 哈希 (320 bit = 80 hex)')],
    96:  [('SHA-384', '高', 'SHA-384 哈希 (384 bit = 96 hex)'),
          ('SHA3-384', '中', 'SHA3-384 哈希 (96 hex)')],
    128: [('SHA-512', '高', 'SHA-512 哈希 (512 bit = 128 hex)'),
          ('SHA3-512', '中', 'SHA3-512 哈希 (128 hex)'),
          ('BLAKE2b-512', '低', 'BLAKE2b-512 哈希 (128 hex)'),
          ('Whirlpool', '低', 'Whirlpool 哈希 (128 hex)'),
          ('SHA-512/256', '低', 'SHA-512/256 或完整 SHA-512 (128 hex)')],
}


def _check_hex(text):
    # 如果是 UUID 格式, 跳过 hex 分析 (避免误判为 MD5 等)
    if re.match(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
        r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$', text.strip()):
        return []

    # 处理 0x 前缀
    clean = text.strip()
    has_0x = clean.lower().startswith('0x')
    if has_0x:
        clean = clean[2:]

    # 清除常见分隔符
    clean = clean.replace(' ', '').replace(':', '').replace('-', '').replace('\n', '').replace('\r', '')

    if not re.match(r'^[0-9a-fA-F]+$', clean):
        return []

    results = []
    length = len(clean)

    # 大小写特征分析
    has_upper_hex = bool(re.search(r'[A-F]', clean))
    has_lower_hex = bool(re.search(r'[a-f]', clean))
    case_note = ''
    if has_upper_hex and not has_lower_hex:
        case_note = ', 全大写'
    elif has_lower_hex and not has_upper_hex:
        case_note = ', 全小写'
    elif has_upper_hex and has_lower_hex:
        case_note = ', 大小写混合'

    if has_0x:
        case_note += ', 含 0x 前缀'

    # 解码成字节, 用于后续字节熵分析
    raw_bytes = None
    if length % 2 == 0 and length >= 2:
        try:
            raw_bytes = bytes.fromhex(clean)
        except ValueError:
            pass

    if length in _HEX_LENGTHS:
        for algo, conf, detail in _HEX_LENGTHS[length]:
            results.append({
                'algorithm': algo,
                'confidence': conf,
                'detail': f'{detail} (长度 {length}{case_note})',
            })

        # ── 标准哈希长度同时也是 AES 块对齐 → 额外检测 AES ──
        # 例如 64 hex = 32B = 2 AES 块, 96 hex = 48B = 3 AES 块, 128 hex = 64B = 4 AES 块
        # 但置信度上限为 "中", 因为标准哈希长度优先级更高
        byte_len = length // 2
        if byte_len % 16 == 0 and byte_len >= 32 and raw_bytes:
            is_enc, enc_conf, enc_reason = _looks_like_encrypted_bytes(raw_bytes)
            if is_enc:
                # 标准哈希长度 → AES 置信度最高只给 "中"
                capped_conf = '中' if enc_conf == '高' else enc_conf
                aes_results = _analyze_aes_hex(raw_bytes, byte_len, case_note, capped_conf, enc_reason)
                results.extend(aes_results)

    else:
        # 非标准长度的 hex
        if length % 2 == 0 and length >= 2:
            byte_len = length // 2
            results.append({
                'algorithm': f'Hex 编码 ({byte_len} 字节)',
                'confidence': '低',
                'detail': f'{length} 个十六进制字符 = {byte_len} 字节{case_note}',
            })

            # ── AES 密文深度分析 ─────────────────────────────
            if byte_len % 16 == 0 and byte_len >= 16 and raw_bytes:
                aes_results = _analyze_aes_hex(raw_bytes, byte_len, case_note, None, None)
                results.extend(aes_results)

            # ── AES-GCM 结构检测 (非块对齐也可能) ────────────
            elif byte_len >= 28 and raw_bytes:
                # GCM: nonce(12) + tag(16) + ciphertext(any)
                gcm_results = _analyze_gcm_structure(raw_bytes, byte_len, 'hex', case_note)
                results.extend(gcm_results)

            # ── AES-CTR 结构检测 (非块对齐也可能) ────────────
            elif byte_len >= 9 and raw_bytes:
                # CTR: nonce(8) + ciphertext(any)
                ctr_results = _analyze_ctr_structure(raw_bytes, byte_len, 'hex', case_note)
                results.extend(ctr_results)

            # ── DES/3DES (8 字节块对齐) ──────────────────────
            if byte_len % 8 == 0 and byte_len >= 8 and byte_len % 16 != 0:
                blocks = byte_len // 8
                if raw_bytes:
                    is_enc, enc_conf, enc_reason = _looks_like_encrypted_bytes(raw_bytes)
                    if is_enc:
                        results.append({
                            'algorithm': f'DES/3DES 密文（{enc_conf}概率）',
                            'confidence': enc_conf,
                            'detail': f'{byte_len} 字节 = {blocks} 个 DES 块 (64-bit), {enc_reason}',
                        })
                    else:
                        results.append({
                            'algorithm': 'DES/3DES 密文（可能）',
                            'confidence': '低',
                            'detail': f'{byte_len} 字节 = {blocks} 个 DES 块 (64-bit)',
                        })
                else:
                    results.append({
                        'algorithm': 'DES/3DES 密文（可能）',
                        'confidence': '低',
                        'detail': f'{byte_len} 字节 = {blocks} 个 DES 块 (64-bit)',
                    })

    return results


def _analyze_aes_hex(raw_bytes, byte_len, case_note, override_conf, override_reason):
    """深度分析可能的 AES 密文 (Hex 编码)。
    根据字节熵和数据结构区分 AES-ECB / AES-CBC / AES-GCM / AES-CTR。"""
    results = []
    blocks = byte_len // 16

    # 先做字节熵分析
    if override_conf is not None:
        is_enc, enc_conf, enc_reason = True, override_conf, override_reason
    else:
        is_enc, enc_conf, enc_reason = _looks_like_encrypted_bytes(raw_bytes)

    if not is_enc:
        # 字节熵太低, 不太像密文, 只给低置信度
        results.append({
            'algorithm': f'AES 密文（可能性低）',
            'confidence': '低',
            'detail': f'{byte_len} 字节 = {blocks} 个 AES 块, '
                      f'但 {enc_reason}{case_note}',
        })
        return results

    # ── 检测 ECB 模式 (重复块检测) ───────────────────────────
    block_list = [raw_bytes[i:i+16] for i in range(0, byte_len, 16)]
    unique_blocks = len(set(block_list))
    has_repeated = unique_blocks < len(block_list)

    if has_repeated and blocks >= 2:
        dup_count = len(block_list) - unique_blocks
        results.append({
            'algorithm': 'AES-ECB 密文',
            'confidence': '高',
            'detail': f'{byte_len} 字节 = {blocks} 个 AES 块, '
                      f'发现 {dup_count} 个重复块 → 高概率 ECB 模式! '
                      f'{enc_reason}{case_note}',
        })
        return results  # ECB 确定性很高, 无需继续

    # ── 检测 CBC 模式 (IV + 密文结构) ────────────────────────
    if blocks >= 2:
        # CBC: 首 16 字节是 IV, 后续是密文
        iv_part = raw_bytes[:16]
        ct_part = raw_bytes[16:]
        iv_ent = _byte_entropy(iv_part)
        ct_ent = _byte_entropy(ct_part) if len(ct_part) >= 16 else 0

        mode_notes = []
        if blocks >= 3:
            # 足够多的块可以区分
            if ct_ent >= 7.0 and iv_ent >= 3.0:
                mode_notes.append(f'可能是 CBC/CFB/OFB 模式 (首 16B 为 IV, IV 熵={iv_ent:.1f}, 密文熵={ct_ent:.1f})')
        elif blocks == 2:
            if iv_ent >= 3.0:
                mode_notes.append(f'可能是 CBC 模式 (首 16B 为 IV + 1 块密文)')

        conf = enc_conf
        detail_parts = [
            f'{byte_len} 字节 = {blocks} 个 AES 块',
            enc_reason,
        ]
        if mode_notes:
            detail_parts.extend(mode_notes)
        else:
            detail_parts.append('可能是 ECB (无 IV) 或 CBC (含 IV)')

        results.append({
            'algorithm': f'AES 密文 (Hex, {byte_len}B)',
            'confidence': conf,
            'detail': '; '.join(detail_parts) + case_note,
        })
    else:
        # 单块
        results.append({
            'algorithm': f'AES 密文 (Hex, 单块 {byte_len}B)',
            'confidence': enc_conf,
            'detail': f'{byte_len} 字节 = 1 个 AES 块, {enc_reason}, '
                      f'可能是 ECB 单块加密{case_note}',
        })

    return results


def _analyze_gcm_structure(raw_bytes, byte_len, encoding, extra_note=''):
    """检测 AES-GCM 结构: nonce(12B) + tag(16B) + ciphertext(任意长度)"""
    if byte_len < 28:
        return []

    nonce = raw_bytes[:12]
    tag = raw_bytes[12:28]
    ct = raw_bytes[28:]

    results = []
    if len(ct) > 0:
        is_enc, enc_conf, enc_reason = _looks_like_encrypted_bytes(raw_bytes)
        if is_enc:
            ct_len = len(ct)
            results.append({
                'algorithm': f'AES-GCM 密文（可能, {encoding}）',
                'confidence': enc_conf,
                'detail': f'{byte_len} 字节: nonce(12B) + tag(16B) + 密文({ct_len}B), '
                          f'{enc_reason}{extra_note}',
            })

    return results


def _analyze_ctr_structure(raw_bytes, byte_len, encoding, extra_note=''):
    """检测 AES-CTR 结构: nonce(8B) + ciphertext(任意长度)"""
    if byte_len < 9:
        return []

    ct = raw_bytes[8:]
    results = []
    if len(ct) > 0:
        is_enc, enc_conf, enc_reason = _looks_like_encrypted_bytes(raw_bytes)
        if is_enc and enc_conf != '低':
            ct_len = len(ct)
            results.append({
                'algorithm': f'AES-CTR 密文（可能, {encoding}）',
                'confidence': '低',
                'detail': f'{byte_len} 字节: nonce(8B) + 密文({ct_len}B), '
                          f'{enc_reason}{extra_note}',
            })

    # ChaCha20: nonce(8B) + ciphertext
    if byte_len >= 16:
        is_enc, enc_conf, enc_reason = _looks_like_encrypted_bytes(raw_bytes)
        if is_enc and enc_conf != '低':
            results.append({
                'algorithm': f'ChaCha20 密文（可能, {encoding}）',
                'confidence': '低',
                'detail': f'{byte_len} 字节: nonce(8B) + 密文({byte_len-8}B), '
                          f'{enc_reason}{extra_note}',
            })

    return results


# ══════════════════════════════════════════════════════════════
#  4. Base64 分析
# ══════════════════════════════════════════════════════════════

# 常见魔术字节 (解码后的前缀)
_MAGIC_BYTES = [
    (b'Salted__', 'OpenSSL enc (Salted)', '高',
     'OpenSSL enc 命令加密数据, 以 "Salted__" + 8字节盐开头'),
    (b'\x00\x00\x00\x07ssh-', 'SSH 密钥数据', '中',
     'SSH 格式二进制密钥数据'),
    (b'openssh-key-v1\x00', 'OpenSSH 私钥数据', '高',
     'OpenSSH 新格式私钥二进制数据'),
    (b'\x30\x82', 'DER/ASN.1 编码 (Base64)', '中',
     '可能是证书或密钥的 DER 编码 (SEQUENCE 标签)'),
    (b'PK\x03\x04', 'ZIP 压缩数据 (Base64)', '中',
     '数据解码后为 ZIP 格式 (PK 头)'),
    (b'\x1f\x8b', 'Gzip 压缩数据 (Base64)', '中',
     '数据解码后为 Gzip 格式'),
    (b'\x89PNG', 'PNG 图片 (Base64)', '高',
     '数据解码后为 PNG 图片'),
    (b'\xff\xd8\xff', 'JPEG 图片 (Base64)', '高',
     '数据解码后为 JPEG 图片'),
    (b'GIF8', 'GIF 图片 (Base64)', '高',
     '数据解码后为 GIF 图片'),
    (b'%PDF', 'PDF 文档 (Base64)', '高',
     '数据解码后为 PDF 文档'),
]


def _check_base64(text):
    clean = text.replace('\n', '').replace('\r', '').strip()

    # 标准 Base64
    is_std_b64 = bool(re.match(r'^[A-Za-z0-9+/]+={0,2}$', clean))
    # URL-safe Base64
    is_url_b64 = bool(re.match(r'^[A-Za-z0-9_-]+={0,2}$', clean))

    if not is_std_b64 and not is_url_b64:
        return []

    if len(clean) < 4:
        return []

    results = []

    try:
        if is_url_b64 and ('_' in clean or '-' in clean):
            padded = clean + '=' * (4 - len(clean) % 4) if len(clean) % 4 else clean
            decoded = base64.urlsafe_b64decode(padded)
            results.append({
                'algorithm': 'Base64url 编码',
                'confidence': '中',
                'detail': f'URL 安全 Base64, 解码后 {len(decoded)} 字节',
            })
        elif is_std_b64:
            decoded = base64.b64decode(clean)
            byte_len = len(decoded)

            results.append({
                'algorithm': 'Base64 编码',
                'confidence': '中',
                'detail': f'标准 Base64, 解码后 {byte_len} 字节',
            })

            # ── 检测魔术字节 ─────────────────────────────────
            for magic, algo, conf, detail in _MAGIC_BYTES:
                if decoded.startswith(magic):
                    results.append({
                        'algorithm': algo,
                        'confidence': conf,
                        'detail': detail,
                    })
                    break

            # ── 解码后是否可打印 → 可能只是文本编码 ──────────
            is_text = False
            try:
                text_content = decoded.decode('utf-8')
                printable_ratio = sum(1 for c in text_content if c.isprintable() or c in '\n\r\t') / max(len(text_content), 1)
                if printable_ratio > 0.9 and len(text_content) > 3:
                    is_text = True
                    results.insert(0, {
                        'algorithm': 'Base64 编码的文本',
                        'confidence': '高',
                        'detail': f'解码为可读文本 ({len(text_content)} 字符, '
                                  f'{printable_ratio*100:.0f}% 可打印)',
                    })
            except (UnicodeDecodeError, ZeroDivisionError):
                pass

            # ── 如果不是纯文本, 做加密数据深度分析 ───────────
            if not is_text:
                results.extend(_analyze_b64_crypto(decoded, byte_len))

    except Exception:
        pass

    return results


def _analyze_b64_crypto(decoded, byte_len):
    """对 Base64 解码后的二进制数据做加密算法深度分析。"""
    results = []
    is_enc, enc_conf, enc_reason = _looks_like_encrypted_bytes(decoded)

    # ── AES 块对齐分析 (16 字节倍数) ────────────────────────
    if byte_len >= 16 and byte_len % 16 == 0:
        blocks = byte_len // 16
        block_list = [decoded[i:i+16] for i in range(0, byte_len, 16)]
        unique_blocks = len(set(block_list))
        has_repeated = unique_blocks < len(block_list)

        if is_enc:
            if has_repeated and blocks >= 2:
                dup_count = len(block_list) - unique_blocks
                results.append({
                    'algorithm': 'AES-ECB 密文 (Base64)',
                    'confidence': '高',
                    'detail': f'解码后 {byte_len} 字节 = {blocks} 个 AES 块, '
                              f'发现 {dup_count} 个重复块 → 高概率 ECB! {enc_reason}',
                })
            elif blocks >= 2:
                # 分析 CBC 结构: IV(16B) + ciphertext
                iv_ent = _byte_entropy(decoded[:16])
                ct_ent = _byte_entropy(decoded[16:]) if byte_len > 16 else 0

                mode_hint = ''
                if blocks >= 3 and ct_ent >= 7.0 and iv_ent >= 3.0:
                    mode_hint = f'CBC/CFB/OFB 模式 (IV 熵={iv_ent:.1f}, 密文熵={ct_ent:.1f})'
                elif blocks == 2:
                    mode_hint = f'CBC (IV+1块) 或 ECB (2块)'

                results.append({
                    'algorithm': f'AES 密文 (Base64, {byte_len}B)',
                    'confidence': enc_conf,
                    'detail': f'解码后 {byte_len}B = {blocks} 个 AES 块; '
                              f'{enc_reason}; {mode_hint}' if mode_hint else
                              f'解码后 {byte_len}B = {blocks} 个 AES 块; {enc_reason}',
                })
            else:
                results.append({
                    'algorithm': f'AES 单块密文 (Base64, {byte_len}B)',
                    'confidence': enc_conf,
                    'detail': f'解码后 {byte_len}B = 1 个 AES 块; {enc_reason}',
                })
        else:
            # 不太像加密, 低置信度
            results.append({
                'algorithm': f'AES 密文 (Base64, {byte_len}B, 可能性低)',
                'confidence': '低',
                'detail': f'解码后 {byte_len}B = {blocks} 个 AES 块, '
                          f'但 {enc_reason}',
            })

    # ── AES-GCM 结构 (非块对齐也可能) ───────────────────────
    # GCM: nonce(12) + tag(16) + ciphertext(任意长度)
    elif byte_len >= 28:
        gcm_results = _analyze_gcm_structure(decoded, byte_len, 'Base64')
        results.extend(gcm_results)

        # 也检查 CTR
        ctr_results = _analyze_ctr_structure(decoded, byte_len, 'Base64')
        results.extend(ctr_results)

    # ── AES-CTR / 流密码结构 (非块对齐) ─────────────────────
    elif byte_len >= 9:
        ctr_results = _analyze_ctr_structure(decoded, byte_len, 'Base64')
        results.extend(ctr_results)

    # ── DES/3DES (8 字节对齐, 但非 16 字节对齐) ─────────────
    if byte_len >= 8 and byte_len % 8 == 0 and byte_len % 16 != 0:
        blocks = byte_len // 8
        if is_enc:
            results.append({
                'algorithm': f'DES/3DES 密文 (Base64, {byte_len}B)',
                'confidence': enc_conf,
                'detail': f'解码后 {byte_len}B = {blocks} 个 DES 块; {enc_reason}',
            })
        else:
            results.append({
                'algorithm': f'DES/3DES 密文 (Base64, {byte_len}B)',
                'confidence': '低',
                'detail': f'解码后 {byte_len}B = {blocks} 个 DES 块',
            })

    # ── RSA 密文/签名判断 ────────────────────────────────────
    if byte_len in (64, 128, 256, 384, 512):
        bit_len = byte_len * 8
        if is_enc:
            results.append({
                'algorithm': f'RSA 密文/签名 (Base64, {bit_len}bit)',
                'confidence': '中' if byte_len >= 128 else '低',
                'detail': f'解码后 {byte_len}B = {bit_len}bit, '
                          f'{enc_reason}, 可能是 RSA-{bit_len}',
            })
        else:
            results.append({
                'algorithm': f'RSA 密文/签名 (Base64, {bit_len}bit)',
                'confidence': '低',
                'detail': f'解码后 {byte_len}B = {bit_len}bit, 可能是 RSA-{bit_len}',
            })

    # ── ChaCha20-Poly1305: nonce(12) + tag(16) + ct ─────────
    if byte_len >= 29:
        is_enc_full, enc_conf_full, enc_reason_full = _looks_like_encrypted_bytes(decoded)
        if is_enc_full and enc_conf_full != '低':
            results.append({
                'algorithm': f'ChaCha20-Poly1305 密文（可能, Base64）',
                'confidence': '低',
                'detail': f'解码后 {byte_len}B: nonce(12)+tag(16)+密文({byte_len-28}B); '
                          f'{enc_reason_full}',
            })

    return results


# ══════════════════════════════════════════════════════════════
#  5. Base32
# ══════════════════════════════════════════════════════════════
def _check_base32(text):
    clean = text.strip().upper()
    if not re.match(r'^[A-Z2-7]+=*$', clean):
        return []
    if len(clean) < 8:
        return []
    # 排除纯 hex (hex 字符是 base32 的子集)
    if re.match(r'^[A-F0-9]+$', clean):
        return []
    try:
        decoded = base64.b32decode(clean)
        return [{
            'algorithm': 'Base32 编码',
            'confidence': '中',
            'detail': f'Base32, 解码后 {len(decoded)} 字节',
        }]
    except Exception:
        pass
    return []


# ══════════════════════════════════════════════════════════════
#  6. Base58 (Bitcoin / IPFS)
# ══════════════════════════════════════════════════════════════
_BASE58_ALPHABET = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')


def _check_base58(text):
    clean = text.strip()
    if not clean or len(clean) < 10:
        return []

    # 必须全是 Base58 字符
    if set(clean) - _BASE58_ALPHABET:
        return []

    # 排除纯 hex (0-9a-f) — 在 _check_hex 已处理
    if re.match(r'^[0-9a-fA-F]+$', clean):
        return []

    results = []

    # ── Bitcoin 地址 (Legacy P2PKH) ──────────────────────────
    if clean.startswith('1') and 25 <= len(clean) <= 34:
        results.append({'algorithm': 'Bitcoin 地址 (P2PKH)', 'confidence': '高',
                        'detail': f'比特币 Legacy 地址, 以 1 开头, {len(clean)} 字符'})
    # ── Bitcoin 地址 (P2SH) ──────────────────────────────────
    elif clean.startswith('3') and 25 <= len(clean) <= 34:
        results.append({'algorithm': 'Bitcoin 地址 (P2SH)', 'confidence': '高',
                        'detail': f'比特币 P2SH 地址, 以 3 开头, {len(clean)} 字符'})
    # ── Bitcoin WIF 私钥 ─────────────────────────────────────
    elif clean.startswith(('5H', '5J', '5K')) and len(clean) == 51:
        results.append({'algorithm': 'Bitcoin WIF 私钥', 'confidence': '高',
                        'detail': 'Wallet Import Format 比特币私钥 (未压缩, 51 字符)'})
    elif clean.startswith(('K', 'L')) and len(clean) == 52:
        results.append({'algorithm': 'Bitcoin WIF 私钥 (压缩)', 'confidence': '高',
                        'detail': 'Wallet Import Format 比特币私钥 (压缩, 52 字符)'})
    # ── IPFS CID v0 ──────────────────────────────────────────
    elif clean.startswith('Qm') and len(clean) == 46:
        results.append({'algorithm': 'IPFS CID v0', 'confidence': '高',
                        'detail': 'IPFS 内容标识符 v0 (Base58, Qm 前缀, 46 字符)'})
    # ── 通用 Base58 ──────────────────────────────────────────
    else:
        if len(clean) >= 20:
            results.append({'algorithm': 'Base58 编码', 'confidence': '低',
                            'detail': f'Base58 字符集, {len(clean)} 字符, 可能是加密货币相关数据'})

    return results


# ══════════════════════════════════════════════════════════════
#  7. Base85 / Ascii85
# ══════════════════════════════════════════════════════════════
def _check_base85(text):
    clean = text.strip()

    # Ascii85 (<~ ... ~>)
    if clean.startswith('<~') and clean.endswith('~>'):
        return [{
            'algorithm': 'Ascii85 编码',
            'confidence': '高',
            'detail': 'Adobe Ascii85 编码, 以 <~ 开头 ~> 结尾',
        }]

    # Z85 / Base85: 可打印 ASCII 85 字符集
    # 字符集: 0-9, a-z, A-Z, .-:+=^!/*?&<>()[]{}@%$#
    if len(clean) >= 10 and len(clean) % 5 == 0:
        b85_chars = set(string.digits + string.ascii_letters + '.-:+=^!/*?&<>()[]{}@%$#')
        if set(clean).issubset(b85_chars) and not clean.isalnum():
            # 需要包含一些特殊字符才可能是 Base85
            special_count = sum(1 for c in clean if c in '.-:+=^!/*?&<>()[]{}@%$#')
            if special_count >= len(clean) * 0.05:
                return [{
                    'algorithm': 'Base85/Z85 编码（可能）',
                    'confidence': '低',
                    'detail': f'长度 {len(clean)} 是 5 的倍数, 字符集匹配 Base85',
                }]

    return []


# ══════════════════════════════════════════════════════════════
#  8. URL 编码
# ══════════════════════════════════════════════════════════════
def _check_url_encoding(text):
    if '%' not in text:
        return []

    encoded_chars = re.findall(r'%[0-9A-Fa-f]{2}', text)
    count = len(encoded_chars)
    if count < 2:
        return []

    total_len = len(text)
    encoded_ratio = (count * 3) / total_len  # 每个 %XX 占 3 字符
    results = []

    if encoded_ratio > 0.5:
        results.append({
            'algorithm': 'URL 编码 (Percent-encoding)',
            'confidence': '高',
            'detail': f'包含 {count} 个 URL 编码字符, '
                      f'编码占比 {encoded_ratio*100:.0f}%, 大量内容被编码',
        })
    else:
        results.append({
            'algorithm': 'URL 编码 (Percent-encoding)',
            'confidence': '中',
            'detail': f'包含 {count} 个 URL 编码字符, 编码占比 {encoded_ratio*100:.0f}%',
        })

    # 双重 URL 编码检测
    if re.search(r'%25[0-9A-Fa-f]{2}', text):
        results.append({
            'algorithm': '双重 URL 编码',
            'confidence': '中',
            'detail': '检测到 %25XX 模式, 可能是双重 URL 编码',
        })

    return results


# ══════════════════════════════════════════════════════════════
#  9. HTML 实体编码
# ══════════════════════════════════════════════════════════════
def _check_html_entity(text):
    # &#xHH; 或 &#DDD; 或 &name;
    numeric = re.findall(r'&#x?[0-9A-Fa-f]+;', text)
    named = re.findall(r'&[a-zA-Z]+;', text)
    total = len(numeric) + len(named)
    if total >= 2:
        return [{
            'algorithm': 'HTML 实体编码',
            'confidence': '中',
            'detail': f'包含 {len(numeric)} 个数字实体 + {len(named)} 个命名实体',
        }]
    return []


# ══════════════════════════════════════════════════════════════
#  10. Unicode 转义
# ══════════════════════════════════════════════════════════════
def _check_unicode_escape(text):
    results = []
    # \uXXXX
    u_escapes = re.findall(r'\\u[0-9A-Fa-f]{4}', text)
    if len(u_escapes) >= 2:
        results.append({
            'algorithm': 'Unicode 转义 (\\uXXXX)',
            'confidence': '中',
            'detail': f'包含 {len(u_escapes)} 个 \\uXXXX 转义序列',
        })
    # \x hex
    x_escapes = re.findall(r'\\x[0-9A-Fa-f]{2}', text)
    if len(x_escapes) >= 3:
        results.append({
            'algorithm': 'Hex 转义 (\\xHH)',
            'confidence': '中',
            'detail': f'包含 {len(x_escapes)} 个 \\xHH 十六进制转义',
        })
    return results


# ══════════════════════════════════════════════════════════════
#  11. 统计分析（兜底）
# ══════════════════════════════════════════════════════════════
def _statistical_analysis(text):
    results = []
    entropy = _shannon_entropy(text)
    length = len(text)

    # 计算字符分布特征
    char_classes = {
        'uppercase': sum(1 for c in text if c.isupper()),
        'lowercase': sum(1 for c in text if c.islower()),
        'digits': sum(1 for c in text if c.isdigit()),
        'special': sum(1 for c in text if not c.isalnum() and not c.isspace()),
        'spaces': sum(1 for c in text if c.isspace()),
        'non_ascii': sum(1 for c in text if ord(c) > 127),
    }

    dist_info = ', '.join(f'{k}={v}' for k, v in char_classes.items() if v > 0)

    if entropy > 5.8:
        results.append({
            'algorithm': '高熵密文 / 加密数据',
            'confidence': '低',
            'detail': f'Shannon 熵 = {entropy:.2f} bit/char (极高), '
                      f'高概率是加密或压缩数据 [{dist_info}]',
        })
    elif entropy > 5.0:
        results.append({
            'algorithm': '高熵 (加密/压缩/随机)',
            'confidence': '低',
            'detail': f'Shannon 熵 = {entropy:.2f} bit/char (高), '
                      f'可能是加密、压缩或高质量随机数据 [{dist_info}]',
        })
    elif entropy > 4.0:
        results.append({
            'algorithm': '中等熵 (编码或混淆)',
            'confidence': '低',
            'detail': f'Shannon 熵 = {entropy:.2f} bit/char (中), '
                      f'可能是编码数据或混淆文本 [{dist_info}]',
        })
    elif entropy > 2.5:
        results.append({
            'algorithm': '低熵 (弱编码或自然文本)',
            'confidence': '低',
            'detail': f'Shannon 熵 = {entropy:.2f} bit/char (较低), '
                      f'可能是简单替换/凯撒密码或自然语言 [{dist_info}]',
        })
    else:
        results.append({
            'algorithm': '极低熵 (明文或重复数据)',
            'confidence': '低',
            'detail': f'Shannon 熵 = {entropy:.2f} bit/char (极低), '
                      f'高概率不是加密数据 [{dist_info}]',
        })

    # 补充: 如果看起来像凯撒/ROT13
    if length >= 10 and char_classes['non_ascii'] == 0 and char_classes['special'] <= length * 0.1:
        alpha = char_classes['uppercase'] + char_classes['lowercase']
        if alpha > length * 0.7:
            results.append({
                'algorithm': '简单替换密码 / ROT13（可能）',
                'confidence': '低',
                'detail': f'文本以字母为主 ({alpha}/{length}), 可能是凯撒/ROT13 等替换密码',
            })

    # 补充: 纯数字
    if text.isdigit():
        results.append({
            'algorithm': '纯数字串',
            'confidence': '低',
            'detail': f'{length} 位纯数字, 可能是时间戳、ID、电话号码或数字密文',
        })
        if length == 10 and text.startswith(('1', '2')):
            results.append({
                'algorithm': 'Unix 时间戳（可能）',
                'confidence': '中',
                'detail': f'10 位数字以 {text[0]} 开头, 格式匹配 Unix 时间戳',
            })
        elif length == 13 and text.startswith(('1', '2')):
            results.append({
                'algorithm': 'Unix 毫秒时间戳（可能）',
                'confidence': '中',
                'detail': f'13 位数字以 {text[0]} 开头, 格式匹配毫秒级 Unix 时间戳',
            })

    return results
