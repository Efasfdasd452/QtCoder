# -*- coding: utf-8 -*-
"""JSON 结构转 JavaScript/TypeScript 类型定义（interface）"""

from typing import Any, Dict, List, Optional, Tuple

from .json_to_code_schema import (
    TYPE_ARRAY_BOOL,
    TYPE_ARRAY_DOUBLE,
    TYPE_ARRAY_INT,
    TYPE_ARRAY_OBJ,
    TYPE_ARRAY_STRING,
    TYPE_BOOL,
    TYPE_DOUBLE,
    TYPE_INT,
    TYPE_OBJ,
    TYPE_STRING,
    parse_json_to_schema,
)


def _schema_type_to_ts(token: str, class_name: Optional[str]) -> str:
    if token == TYPE_STRING:
        return "string"
    if token == TYPE_INT:
        return "number"
    if token == TYPE_DOUBLE:
        return "number"
    if token == TYPE_BOOL:
        return "boolean"
    if token == TYPE_ARRAY_INT:
        return "number[]"
    if token == TYPE_ARRAY_DOUBLE:
        return "number[]"
    if token == TYPE_ARRAY_STRING:
        return "string[]"
    if token == TYPE_ARRAY_BOOL:
        return "boolean[]"
    if token == TYPE_ARRAY_OBJ and class_name:
        return f"{class_name}[]"
    if token == TYPE_OBJ and class_name:
        return class_name
    return "unknown"


def _generate_ts_interface(
    name: str,
    members: List[Tuple[str, str, Optional[str]]],
) -> str:
    lines = [f"interface {name} {{"]
    for m_name, token, cls in members:
        ts_type = _schema_type_to_ts(token, cls)
        lines.append(f"    {m_name}: {ts_type};")
    lines.append("}")
    return "\n".join(lines)


def json_to_js(json_str: str, root_class_name: str = "MyClass") -> str:
    """将 JSON 字符串转换为 TypeScript interface 定义（亦可用于 JSDoc）。"""
    err, root_members, nested = parse_json_to_schema(json_str, root_class_name)
    if err:
        return f"/* {err} */"

    parts = []
    # 嵌套类型在前，根类型在后
    for cls_name, mems in nested.items():
        parts.append(_generate_ts_interface(cls_name, mems))
        parts.append("\n\n")
    parts.append(_generate_ts_interface(root_class_name, root_members))
    return "".join(parts)
