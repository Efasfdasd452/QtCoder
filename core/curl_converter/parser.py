# -*- coding: utf-8 -*-
"""curl 命令解析器 — 将 curl 命令字符串解析为结构化的 ParsedRequest"""

import json
import re
import shlex
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlencode


@dataclass
class ParsedRequest:
    """解析后的 HTTP 请求结构"""
    url: str = ''
    method: str = ''
    headers: Dict[str, str] = field(default_factory=dict)
    data: Optional[str] = None
    data_type: str = 'raw'        # raw / json / form / multipart
    json_data: Any = None         # 解析后的 JSON 对象
    form_data: List[str] = field(default_factory=list)
    auth: Optional[Tuple[str, str]] = None
    auth_type: str = 'basic'      # basic / digest / bearer
    bearer_token: str = ''
    cookies: Dict[str, str] = field(default_factory=dict)
    proxy: str = ''
    verify_ssl: bool = True
    follow_redirects: bool = False
    timeout: Optional[float] = None
    compressed: bool = False
    output_file: str = ''
    user_agent: str = ''
    referer: str = ''

    @property
    def effective_method(self) -> str:
        if self.method:
            return self.method
        if self.data or self.form_data or self.json_data:
            return 'POST'
        return 'GET'

    @property
    def has_body(self) -> bool:
        return bool(self.data or self.form_data)


def _tokenize(command: str) -> List[str]:
    """将 curl 命令字符串拆分为 token 列表"""
    cmd = command.strip()
    # 去掉行续接符
    cmd = re.sub(r'\\\s*\n', ' ', cmd)   # Unix
    cmd = re.sub(r'`\s*\n', ' ', cmd)    # PowerShell
    cmd = re.sub(r'\^\s*\r?\n', ' ', cmd)  # Windows CMD

    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError:
        tokens = shlex.split(cmd, posix=False)

    if not tokens:
        raise ValueError("空的 curl 命令")

    # 跳过开头的 curl / curl.exe
    if tokens[0].lower().rstrip('.exe') == 'curl':
        tokens = tokens[1:]
    return tokens


def parse_curl(command: str) -> ParsedRequest:
    """解析 curl 命令字符串，返回 ParsedRequest 对象"""
    tokens = _tokenize(command)
    req = ParsedRequest()

    i = 0
    while i < len(tokens):
        t = tokens[i]

        # ── URL ────────────────────────────────────────────
        if t in ('--url',):
            i += 1; req.url = tokens[i]

        # ── 方法 ───────────────────────────────────────────
        elif t in ('-X', '--request'):
            i += 1; req.method = tokens[i].upper()
        elif t in ('-I', '--head'):
            req.method = 'HEAD'
        elif t in ('-G', '--get'):
            req.method = 'GET'

        # ── 请求头 ─────────────────────────────────────────
        elif t in ('-H', '--header'):
            i += 1
            key, _, value = tokens[i].partition(':')
            req.headers[key.strip()] = value.strip()
        elif t in ('-A', '--user-agent'):
            i += 1; req.user_agent = tokens[i]
        elif t in ('-e', '--referer'):
            i += 1; req.referer = tokens[i]

        # ── 数据 ───────────────────────────────────────────
        elif t in ('-d', '--data', '--data-raw', '--data-ascii',
                   '--data-binary'):
            i += 1; req.data = tokens[i]
        elif t == '--data-urlencode':
            i += 1
            req.data = tokens[i]
            req.data_type = 'form'
        elif t == '--json':
            i += 1
            req.data = tokens[i]
            req.data_type = 'json'
            req.headers.setdefault('Content-Type', 'application/json')
            req.headers.setdefault('Accept', 'application/json')
        elif t in ('-F', '--form', '--form-string'):
            i += 1
            req.form_data.append(tokens[i])
            req.data_type = 'multipart'

        # ── 认证 ───────────────────────────────────────────
        elif t in ('-u', '--user'):
            i += 1
            parts = tokens[i].split(':', 1)
            req.auth = (parts[0], parts[1] if len(parts) > 1 else '')
        elif t == '--basic':
            req.auth_type = 'basic'
        elif t == '--digest':
            req.auth_type = 'digest'
        elif t == '--oauth2-bearer':
            i += 1
            req.bearer_token = tokens[i]
            req.auth_type = 'bearer'

        # ── Cookie ─────────────────────────────────────────
        elif t in ('-b', '--cookie'):
            i += 1
            for ck in tokens[i].split(';'):
                ck = ck.strip()
                if '=' in ck:
                    k, v = ck.split('=', 1)
                    req.cookies[k.strip()] = v.strip()

        # ── 连接选项 ───────────────────────────────────────
        elif t in ('-L', '--location'):
            req.follow_redirects = True
        elif t in ('-k', '--insecure'):
            req.verify_ssl = False
        elif t in ('-x', '--proxy'):
            i += 1; req.proxy = tokens[i]
        elif t in ('--connect-timeout',):
            i += 1; req.timeout = float(tokens[i])
        elif t in ('-m', '--max-time'):
            i += 1; req.timeout = float(tokens[i])
        elif t == '--compressed':
            req.compressed = True

        # ── 输出 ───────────────────────────────────────────
        elif t in ('-o', '--output'):
            i += 1; req.output_file = tokens[i]

        # ── 裸 URL ────────────────────────────────────────
        elif not t.startswith('-') and not req.url:
            req.url = t

        i += 1

    # 后处理
    if not req.url:
        raise ValueError("未找到 URL")

    if req.user_agent:
        req.headers['User-Agent'] = req.user_agent
    if req.referer:
        req.headers['Referer'] = req.referer

    # 自动识别 JSON
    if req.data and req.data_type == 'raw':
        ct = req.headers.get('Content-Type', '')
        if 'application/json' in ct:
            req.data_type = 'json'
        elif 'application/x-www-form-urlencoded' in ct:
            req.data_type = 'form'

    if req.data and req.data_type == 'json':
        try:
            req.json_data = json.loads(req.data)
        except (json.JSONDecodeError, ValueError):
            pass

    if req.form_data:
        req.data_type = 'multipart'

    return req
