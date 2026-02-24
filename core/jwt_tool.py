# -*- coding: utf-8 -*-
"""JWT 解析工具（纯本地，不验证签名，只解码）

支持解码 Header / Payload，检查过期时间，
不需要任何第三方依赖。
"""

import base64
import json
import time
from datetime import datetime, timezone


def _b64url_decode(segment: str) -> bytes:
    """Base64url 解码（自动补齐 padding）。"""
    segment += '=' * (4 - len(segment) % 4)
    return base64.urlsafe_b64decode(segment)


def decode_jwt(token: str) -> tuple[dict, dict, str]:
    """解码 JWT，返回 (header, payload, signature_b64)。

    不验证签名，纯本地解码。
    Raises: ValueError 当 token 格式错误
    """
    token = token.strip()
    # 移除常见前缀
    for prefix in ('Bearer ', 'bearer ', 'TOKEN '):
        if token.startswith(prefix):
            token = token[len(prefix):]

    parts = token.split('.')
    if len(parts) != 3:
        raise ValueError(
            f"无效的 JWT 格式：应为 3 段（header.payload.signature），"
            f"实际 {len(parts)} 段"
        )
    try:
        header  = json.loads(_b64url_decode(parts[0]))
    except Exception as e:
        raise ValueError(f"Header 解码失败：{e}")
    try:
        payload = json.loads(_b64url_decode(parts[1]))
    except Exception as e:
        raise ValueError(f"Payload 解码失败：{e}")

    return header, payload, parts[2]


def get_expiry_info(payload: dict) -> dict:
    """分析 Payload 中的时间相关字段。

    Returns:
        status: 'no_exp' | 'valid' | 'expired' | 'not_yet_valid'
        exp / iat / nbf: 原始时间戳（或 None）
        exp_dt / iat_dt / nbf_dt: 格式化字符串（或 ''）
        message: 中文状态描述
    """
    now = time.time()
    exp = payload.get('exp')
    iat = payload.get('iat')
    nbf = payload.get('nbf')

    def _fmt(ts):
        if ts is None:
            return ''
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                '%Y-%m-%d %H:%M:%S UTC')
        except Exception:
            return str(ts)

    info = {
        'exp': exp, 'iat': iat, 'nbf': nbf,
        'exp_dt': _fmt(exp), 'iat_dt': _fmt(iat), 'nbf_dt': _fmt(nbf),
        'now': now,
    }

    if nbf is not None and now < nbf:
        info['status']  = 'not_yet_valid'
        info['message'] = f'未生效（还差 {int(nbf - now)} 秒）'
    elif exp is None:
        info['status']  = 'no_exp'
        info['message'] = '无过期时间（永久有效）'
    elif now > exp:
        ago = int(now - exp)
        if ago < 60:
            ago_str = f'{ago} 秒'
        elif ago < 3600:
            ago_str = f'{ago // 60} 分钟'
        elif ago < 86400:
            ago_str = f'{ago // 3600} 小时'
        else:
            ago_str = f'{ago // 86400} 天'
        info['status']  = 'expired'
        info['message'] = f'已过期（{ago_str}前）'
    else:
        left = int(exp - now)
        if left < 60:
            left_str = f'{left} 秒'
        elif left < 3600:
            left_str = f'{left // 60} 分钟'
        elif left < 86400:
            left_str = f'{left // 3600} 小时'
        else:
            left_str = f'{left // 86400} 天'
        info['status']  = 'valid'
        info['message'] = f'有效（还剩 {left_str}）'

    return info


# ── 常见 Payload 字段说明 ─────────────────────────────────────
CLAIM_DESCRIPTIONS = {
    'iss': '签发方 (Issuer)',
    'sub': '主题/用户 (Subject)',
    'aud': '接收方 (Audience)',
    'exp': '过期时间 (Expiration)',
    'nbf': '生效时间 (Not Before)',
    'iat': '签发时间 (Issued At)',
    'jti': 'JWT 唯一 ID (JWT ID)',
    'name':  '用户姓名',
    'email': '邮箱',
    'role':  '角色',
    'scope': '权限范围',
}
