# -*- coding: utf-8 -*-
"""JSON 结构转 PHP 类定义（PHP 7.4+ 类型属性）"""

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


def _schema_type_to_php(token: str, class_name: Optional[str]) -> str:
    if token == TYPE_STRING:
        return "string"
    if token == TYPE_INT:
        return "int"
    if token == TYPE_DOUBLE:
        return "float"
    if token == TYPE_BOOL:
        return "bool"
    if token == TYPE_ARRAY_INT:
        return "array"  # int[]
    if token == TYPE_ARRAY_DOUBLE:
        return "array"
    if token == TYPE_ARRAY_STRING:
        return "array"
    if token == TYPE_ARRAY_BOOL:
        return "array"
    if token == TYPE_ARRAY_OBJ and class_name:
        return "array"  # DocBlock 标注
    if token == TYPE_OBJ and class_name:
        return class_name
    return "mixed"


def _php_doc_array(m_name: str, token: str, class_name: Optional[str]) -> Optional[str]:
    if token == TYPE_ARRAY_INT:
        return "int[]"
    if token == TYPE_ARRAY_DOUBLE:
        return "float[]"
    if token == TYPE_ARRAY_STRING:
        return "string[]"
    if token == TYPE_ARRAY_BOOL:
        return "bool[]"
    if token == TYPE_ARRAY_OBJ and class_name:
        return f"{class_name}[]"
    return None


def _generate_php_class(
    name: str,
    members: List[Tuple[str, str, Optional[str]]],
) -> str:
    lines = [f"class {name} {{"]
    for m_name, token, cls in members:
        php_type = _schema_type_to_php(token, cls)
        doc = _php_doc_array(m_name, token, cls)
        if doc is not None:
            lines.append("    /** @var %s */" % doc)
        lines.append(f"    public {php_type} ${m_name};")
    lines.append("}")
    return "\n".join(lines)


def json_to_php(json_str: str, root_class_name: str = "MyClass") -> str:
    """将 JSON 字符串转换为 PHP 类定义。"""
    err, root_members, nested = parse_json_to_schema(json_str, root_class_name)
    if err:
        return f"<?php\n// {err}"

    parts = ["<?php\n\n"]
    # 嵌套类在前
    for cls_name, mems in nested.items():
        parts.append(_generate_php_class(cls_name, mems))
        parts.append("\n\n")
    parts.append(_generate_php_class(root_class_name, root_members))
    return "".join(parts)
