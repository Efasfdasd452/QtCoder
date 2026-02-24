# -*- coding: utf-8 -*-
"""JSON 转代码 — 公共解析与类型推断

将 JSON 对象解析为语言无关的 schema（成员名 + 类型标记），
供 C++/Java/Python/PHP/JS 等生成器使用。
"""

import json
from typing import Any, Dict, List, Optional, Tuple


def class_name_from_key(key: str) -> str:
    """将 JSON 键名转为类名：首字母大写。"""
    if not key:
        return "Item"
    return key[0].upper() + key[1:]


# 类型标记（语言无关）
TYPE_STRING = "string"
TYPE_INT = "int"
TYPE_DOUBLE = "double"
TYPE_BOOL = "bool"
TYPE_ARRAY_INT = "array_int"
TYPE_ARRAY_DOUBLE = "array_double"
TYPE_ARRAY_STRING = "array_string"
TYPE_ARRAY_BOOL = "array_bool"
TYPE_ARRAY_OBJ = "array_obj"  # 需配合 class_name
TYPE_OBJ = "obj"              # 需配合 class_name


def _infer_type(value: Any, key: str) -> Tuple[str, Optional[str], Any]:
    """推断类型。返回 (type_token, class_name_if_obj_or_array_obj, nested_value)。"""
    if value is None:
        return TYPE_STRING, None, None
    if isinstance(value, bool):
        return TYPE_BOOL, None, value
    if isinstance(value, int):
        return TYPE_INT, None, value
    if isinstance(value, float):
        return TYPE_DOUBLE, None, value
    if isinstance(value, str):
        return TYPE_STRING, None, value
    if isinstance(value, list):
        if not value:
            return TYPE_ARRAY_INT, None, None
        first = value[0]
        if isinstance(first, dict):
            cls = class_name_from_key(key)
            return TYPE_ARRAY_OBJ, cls, first
        if isinstance(first, bool):
            return TYPE_ARRAY_BOOL, None, None
        if isinstance(first, int):
            return TYPE_ARRAY_INT, None, None
        if isinstance(first, float):
            return TYPE_ARRAY_DOUBLE, None, None
        if isinstance(first, str):
            return TYPE_ARRAY_STRING, None, None
        return TYPE_ARRAY_INT, None, None
    if isinstance(value, dict):
        cls = class_name_from_key(key)
        return TYPE_OBJ, cls, value
    return TYPE_STRING, None, None


def _collect_nested(obj: dict, key: str, nested: Dict[str, List[Tuple[str, str, Optional[str]]]]) -> None:
    """递归收集嵌套类的 (成员名, type_token, class_name)。"""
    class_name = class_name_from_key(key)
    if class_name in nested:
        return
    members = []
    for k, v in obj.items():
        token, cls, nested_val = _infer_type(v, k)
        if token == TYPE_OBJ and cls:
            members.append((k, token, cls))
            if isinstance(nested_val, dict):
                _collect_nested(nested_val, k, nested)
        elif token == TYPE_ARRAY_OBJ and cls and isinstance(nested_val, dict):
            members.append((k, token, cls))
            _collect_nested(nested_val, k, nested)
        else:
            members.append((k, token, None))
    nested[class_name] = members


def parse_json_to_schema(
    json_str: str,
    root_class_name: str = "MyClass",
) -> Tuple[Optional[str], List[Tuple[str, str, Optional[str]]], Dict[str, List[Tuple[str, str, Optional[str]]]]]:
    """解析 JSON 得到 schema。

    Returns:
        (error_message, root_members, nested)
        成功时 error_message 为 None；root_members 为 [(name, type_token, class_name?)];
        nested 为 { class_name: [(name, type_token, class_name?)], ... }。
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return f"JSON 解析错误: {e}", [], {}

    if not isinstance(data, dict):
        return "请输入 JSON 对象（键值对），当前为数组或标量", [], {}

    root_members = []
    nested = {}

    for k, v in data.items():
        token, cls, nested_val = _infer_type(v, k)
        root_members.append((k, token, cls))
        if token == TYPE_OBJ and isinstance(nested_val, dict):
            _collect_nested(nested_val, k, nested)
        elif token == TYPE_ARRAY_OBJ and nested_val and isinstance(nested_val, dict):
            _collect_nested(nested_val, k, nested)

    return None, root_members, nested
