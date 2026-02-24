# -*- coding: utf-8 -*-
"""JSON 结构转 Python 类定义（dataclass + 类型注解）"""

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


def _schema_type_to_python(token: str, class_name: Optional[str]) -> str:
    if token == TYPE_STRING:
        return "str"
    if token == TYPE_INT:
        return "int"
    if token == TYPE_DOUBLE:
        return "float"
    if token == TYPE_BOOL:
        return "bool"
    if token == TYPE_ARRAY_INT:
        return "List[int]"
    if token == TYPE_ARRAY_DOUBLE:
        return "List[float]"
    if token == TYPE_ARRAY_STRING:
        return "List[str]"
    if token == TYPE_ARRAY_BOOL:
        return "List[bool]"
    if token == TYPE_ARRAY_OBJ and class_name:
        return f"List[{class_name}]"
    if token == TYPE_OBJ and class_name:
        return class_name
    return "Any"


def _generate_python_class(
    name: str,
    members: List[Tuple[str, str, Optional[str]]],
) -> str:
    lines = ["@dataclass", f"class {name}:"]
    for m_name, token, cls in members:
        py_type = _schema_type_to_python(token, cls)
        lines.append(f"    {m_name}: {py_type}")
    return "\n".join(lines)


def json_to_python(json_str: str, root_class_name: str = "MyClass") -> str:
    """将 JSON 字符串转换为 Python dataclass 定义。"""
    err, root_members, nested = parse_json_to_schema(json_str, root_class_name)
    if err:
        return f"# {err}"

    needs_list = any(m[1].startswith("array_") or m[1] == TYPE_OBJ for m in root_members)
    for mems in nested.values():
        if any(m[1].startswith("array_") or m[1] == TYPE_OBJ for m in mems):
            needs_list = True
            break

    parts = ["from dataclasses import dataclass\n"]
    if needs_list:
        parts.append("from typing import List\n\n")
    else:
        parts.append("\n")

    # 嵌套类在前，根类在后
    for cls_name, mems in nested.items():
        parts.append(_generate_python_class(cls_name, mems))
        parts.append("\n\n")
    parts.append(_generate_python_class(root_class_name, root_members))

    return "".join(parts)
