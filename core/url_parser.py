# -*- coding: utf-8 -*-
"""URL 解析与 Python requests 代码生成

解析任意复杂 URL，提取各组件与查询参数（自动 URL 解码），
生成可直接运行的 Python requests 代码。
"""

import json
from urllib.parse import (
    urlparse, parse_qsl, urlencode, urlunparse, unquote_plus
)


def parse_url(url: str) -> dict:
    """解析 URL，返回各组件字典。

    Returns:
        scheme, host, port, path, fragment, base_url,
        params: list[tuple[str, str]]  (保留顺序，保留重复键)
    """
    url = url.strip()
    p = urlparse(url)

    # 解析 query string，保留重复键（如 tag=a&tag=b）
    params = [(unquote_plus(k), unquote_plus(v))
              for k, v in parse_qsl(p.query, keep_blank_values=True)]

    base_url = urlunparse((p.scheme, p.netloc, p.path, '', '', ''))

    return {
        'scheme':   p.scheme,
        'host':     p.hostname or '',
        'port':     p.port,
        'netloc':   p.netloc,
        'path':     p.path,
        'fragment': p.fragment,
        'base_url': base_url,
        'params':   params,   # list of (key, value)
        'raw_url':  url,
    }


def rebuild_url(base_url: str, params: list[tuple[str, str]],
                fragment: str = '') -> str:
    """从 base_url + params 重新构建 URL。"""
    qs = urlencode(params, doseq=True)
    p = urlparse(base_url)
    return urlunparse((p.scheme, p.netloc, p.path, '', qs, fragment))


def to_requests_code(parsed: dict,
                     method: str = 'GET',
                     headers: list[tuple[str, str]] | None = None,
                     body_type: str = 'none') -> str:
    """生成 Python requests 代码字符串。

    Args:
        method:    GET / POST / PUT / DELETE / PATCH
        headers:   [(name, value), ...]
        body_type: 'none' | 'json' | 'form'
                   POST 时可将 params 移入 json= 或 data=
    """
    lines = ['import requests', '']

    base = parsed['base_url']
    params = parsed['params']
    fragment = parsed.get('fragment', '')

    lines.append(f'url = {json.dumps(base)}')

    # params
    if params:
        lines.append('')
        # 检测是否有重复 key
        keys = [k for k, _ in params]
        if len(keys) == len(set(keys)):
            # 无重复：用 dict
            lines.append('params = {')
            for k, v in params:
                lines.append(f'    {json.dumps(k)}: {json.dumps(v)},')
            lines.append('}')
        else:
            # 有重复：用 list of tuples
            lines.append('params = [')
            for k, v in params:
                lines.append(f'    ({json.dumps(k)}, {json.dumps(v)}),')
            lines.append(']')

    # headers
    if headers:
        lines.append('')
        lines.append('headers = {')
        for k, v in headers:
            lines.append(f'    {json.dumps(k)}: {json.dumps(v)},')
        lines.append('}')

    lines.append('')

    m = method.lower()
    args = ['url']

    if body_type == 'json' and params:
        # POST JSON body: params → json={}
        lines_before_call = []
        lines_before_call.append('')
        lines_before_call.append('# 请求体（JSON）')
        lines_before_call.append('payload = {')
        for k, v in params:
            lines_before_call.append(f'    {json.dumps(k)}: {json.dumps(v)},')
        lines_before_call.append('}')
        lines.extend(lines_before_call)
        args.append('json=payload')
    elif body_type == 'form' and params:
        lines_before_call = []
        lines_before_call.append('')
        lines_before_call.append('# 请求体（表单）')
        lines_before_call.append('data = {')
        for k, v in params:
            lines_before_call.append(f'    {json.dumps(k)}: {json.dumps(v)},')
        lines_before_call.append('}')
        lines.extend(lines_before_call)
        args.append('data=data')
    elif params:
        args.append('params=params')

    if headers:
        args.append('headers=headers')

    lines.append('')
    lines.append(f'response = requests.{m}({", ".join(args)})')
    lines.append('print(response.status_code)')
    lines.append('print(response.text)')

    return '\n'.join(lines)
