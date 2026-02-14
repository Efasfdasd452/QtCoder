# -*- coding: utf-8 -*-
"""JSON 格式化引擎 — 纯函数，无 UI 依赖"""

import json


def format_json(text, indent=4, sort_keys=False, ensure_ascii=False):
    """格式化（美化）JSON"""
    obj = json.loads(text)
    return json.dumps(obj, indent=indent, sort_keys=sort_keys,
                      ensure_ascii=ensure_ascii)


def minify_json(text):
    """压缩 JSON（去除空白）"""
    obj = json.loads(text)
    return json.dumps(obj, separators=(',', ':'), ensure_ascii=False)


def validate_json(text):
    """验证 JSON 是否合法，返回 (ok, message)"""
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            info = f"有效的 JSON 对象，包含 {len(obj)} 个键"
        elif isinstance(obj, list):
            info = f"有效的 JSON 数组，包含 {len(obj)} 个元素"
        else:
            info = f"有效的 JSON 值 (类型: {type(obj).__name__})"
        return True, info
    except json.JSONDecodeError as e:
        return False, f"JSON 语法错误:\n行 {e.lineno}, 列 {e.colno}: {e.msg}"
