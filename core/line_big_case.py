# -*- coding: utf-8 -*-
"""下划线命名与驼峰命名互转

- 下划线 → 驼峰：out_trade_no → outTradeNo（首字母小写）
- 驼峰 → 下划线：outTradeNo → out_trade_no
在整段文本中识别并转换所有匹配的标识符，其余内容不变。
"""

import re


def _snake_to_camel_one(ident: str) -> str:
    """单个下划线标识符转小驼峰。out_trade_no -> outTradeNo"""
    if not ident or "_" not in ident:
        return ident
    parts = ident.split("_")
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:] if p)


def _camel_to_snake_one(ident: str) -> str:
    """单个驼峰标识符转下划线。outTradeNo -> out_trade_no"""
    if not ident or ident.islower() or not re.search(r"[a-z][A-Z]|[A-Z][a-z]", ident):
        return ident
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", ident)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return s.lower()


def snake_to_camel(text: str) -> str:
    """将文本中所有下划线命名标识符转为小驼峰，其余不变。支持前置下划线（_private_var）。"""
    # 使用 (?<![a-zA-Z0-9]) 替代 \b，避免 _ 与字母之间无法产生边界的问题
    # group(1)=前置下划线（0个或多个），group(2)=标识符主体
    pattern = r"(?<![a-zA-Z0-9])(_*)([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b"
    def replace(m):
        return m.group(1) + _snake_to_camel_one(m.group(2))
    return re.sub(pattern, replace, text)


def camel_to_snake(text: str) -> str:
    """将文本中所有驼峰标识符（含 PascalCase）转为下划线命名，其余不变。"""
    # 允许大写字母开头，以兼容 PascalCase（MyClass、HttpClient、URLParser 等）
    # _camel_to_snake_one 内部会过滤掉纯大写（HTTP）或普通单词（String）
    pattern = r"\b([a-zA-Z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*)\b"
    def replace(m):
        return _camel_to_snake_one(m.group(1))
    return re.sub(pattern, replace, text)
