# -*- coding: utf-8 -*-
"""JSON 结构转 Java 类定义"""

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


def _schema_type_to_java(token: str, class_name: Optional[str]) -> str:
    if token == TYPE_STRING:
        return "String"
    if token == TYPE_INT:
        return "int"
    if token == TYPE_DOUBLE:
        return "double"
    if token == TYPE_BOOL:
        return "boolean"
    if token == TYPE_ARRAY_INT:
        return "List<Integer>"
    if token == TYPE_ARRAY_DOUBLE:
        return "List<Double>"
    if token == TYPE_ARRAY_STRING:
        return "List<String>"
    if token == TYPE_ARRAY_BOOL:
        return "List<Boolean>"
    if token == TYPE_ARRAY_OBJ and class_name:
        return f"List<{class_name}>"
    if token == TYPE_OBJ and class_name:
        return class_name
    return "Object"


def _generate_java_class(
    name: str,
    members: List[Tuple[str, str, Optional[str]]],
) -> str:
    lines = [f"public class {name} {{"]
    for m_name, token, cls in members:
        java_type = _schema_type_to_java(token, cls)
        lines.append(f"    public {java_type} {m_name};")
    lines.append("")
    lines.append("    public %s() {}" % name)
    lines.append("}")
    return "\n".join(lines)


def json_to_java(json_str: str, root_class_name: str = "MyClass") -> str:
    """将 JSON 字符串转换为 Java 类定义。"""
    err, root_members, nested = parse_json_to_schema(json_str, root_class_name)
    if err:
        return f"/* {err} */"

    needs_list = any(m[1].startswith("array_") for m in root_members)
    for mems in nested.values():
        if any(m[1].startswith("array_") for m in mems):
            needs_list = True
            break

    parts = []
    if needs_list:
        parts.append("import java.util.List;\n")

    root_class = _generate_java_class(root_class_name, root_members)
    parts.append(root_class)

    for cls_name, mems in nested.items():
        parts.append("\n\n")
        parts.append(_generate_java_class(cls_name, mems))

    return "".join(parts)
