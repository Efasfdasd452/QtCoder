# -*- coding: utf-8 -*-
"""Cookie 解析工具

支持两种模式:
  1. 请求 Cookie 头:  Cookie: key1=val1; key2=val2
  2. 响应 Set-Cookie: name=value; Path=/; HttpOnly; Secure; ...

纯标准库实现，无外部依赖。
"""

import json
from datetime import datetime, timezone


# ── 请求 Cookie 头解析 ─────────────────────────────────────────
def parse_request_cookie(header: str) -> list[tuple[str, str]]:
    """解析 Cookie: 请求头为有序的 [(name, value), ...] 列表。

    header 可以含或不含 "Cookie:" 前缀。
    """
    # 去掉 'Cookie:' 前缀
    s = header.strip()
    if s.lower().startswith('cookie:'):
        s = s[len('cookie:'):].strip()

    result = []
    for item in s.split(';'):
        item = item.strip()
        if not item:
            continue
        if '=' in item:
            k, _, v = item.partition('=')
            result.append((k.strip(), v.strip()))
        else:
            result.append((item, ''))
    return result


def cookies_to_dict_code(cookies: list[tuple[str, str]]) -> str:
    """生成 Python dict 字面量（用于 requests.get(cookies=...)）。"""
    lines = ['cookies = {']
    for k, v in cookies:
        lines.append(f'    {json.dumps(k)}: {json.dumps(v)},')
    lines.append('}')
    return '\n'.join(lines)


def cookies_to_header(cookies: list[tuple[str, str]]) -> str:
    """重建 Cookie: 请求头字符串。"""
    return 'Cookie: ' + '; '.join(
        f'{k}={v}' if v else k for k, v in cookies)


# ── Set-Cookie 响应头解析 ───────────────────────────────────────
# Set-Cookie 属性（标准化小写名 → 显示名）
_SET_COOKIE_ATTRS = {
    'path':     'Path',
    'domain':   'Domain',
    'expires':  'Expires',
    'max-age':  'Max-Age',
    'samesite': 'SameSite',
    'secure':   'Secure',
    'httponly': 'HttpOnly',
    'partitioned': 'Partitioned',
}


def parse_set_cookie(header: str) -> dict:
    """解析 Set-Cookie: 响应头。

    Returns:
        name, value: cookie 本体
        attributes: {attr_lower: value_or_True}
        expires_dt: 格式化过期时间（或 ''）
        security_flags: [str]  (Secure / HttpOnly 等)
    """
    s = header.strip()
    if s.lower().startswith('set-cookie:'):
        s = s[len('set-cookie:'):].strip()

    parts = [p.strip() for p in s.split(';')]

    # 第一段是 name=value
    first = parts[0] if parts else ''
    if '=' in first:
        k, _, v = first.partition('=')
        name, value = k.strip(), v.strip()
    else:
        name, value = first.strip(), ''

    attrs = {}
    for part in parts[1:]:
        if not part:
            continue
        if '=' in part:
            ak, _, av = part.partition('=')
            attrs[ak.strip().lower()] = av.strip()
        else:
            attrs[part.lower()] = True

    # 格式化 expires
    expires_dt = ''
    if 'expires' in attrs and isinstance(attrs['expires'], str):
        try:
            # 尝试解析 HTTP-date 格式
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(attrs['expires'])
            expires_dt = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        except Exception:
            expires_dt = attrs['expires']

    security_flags = [f for f in ('secure', 'httponly', 'partitioned')
                      if attrs.get(f) is True]

    return {
        'name':          name,
        'value':         value,
        'attributes':    attrs,
        'expires_dt':    expires_dt,
        'security_flags': security_flags,
    }
