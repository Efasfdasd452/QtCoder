# -*- coding: utf-8 -*-
"""JSON 结构转 C++ 类定义

将 JSON 对象转换为 C++ 类声明：成员类型根据 JSON 值推断，
嵌套对象生成独立类，顺序为根类在前、嵌套类在后。
"""

import json
from typing import Any, List, Tuple


def _class_name_from_key(key: str) -> str:
    """将 JSON 键名转为 C++ 类名：首字母大写。"""
    if not key:
        return "Item"
    return key[0].upper() + key[1:]


def _infer_cpp_type(value: Any, key: str) -> Tuple[str, Any]:
    """根据 JSON 值推断 C++ 类型，返回 (cpp_type_str, normalized_value_for_nested)。
    若为嵌套对象则返回 (ClassName, obj)；若为数组则返回 (vector_type, element_sample)。
    """
    if value is None:
        return "std::string", None  # 保守用 string 占位
    if isinstance(value, bool):
        return "bool", value
    if isinstance(value, int):
        return "int", value
    if isinstance(value, float):
        return "double", value
    if isinstance(value, str):
        return "std::string", value
    if isinstance(value, list):
        if not value:
            return "std::vector<int>", None
        first = value[0]
        if isinstance(first, dict):
            # 数组元素为对象：用 key 的类名作为元素类型
            elem_class = _class_name_from_key(key)
            return f"std::vector<{elem_class}>", first
        if isinstance(first, bool):
            return "std::vector<bool>", None
        if isinstance(first, int):
            return "std::vector<int>", None
        if isinstance(first, float):
            return "std::vector<double>", None
        if isinstance(first, str):
            return "std::vector<std::string>", None
        return "std::vector<int>", None
    if isinstance(value, dict):
        class_name = _class_name_from_key(key)
        return class_name, value
    return "std::string", None


def _collect_nested_classes(obj: dict, key: str, collected: dict) -> None:
    """递归收集所有嵌套对象，用于生成子类。key 为当前对象的键名（用于类名）。"""
    class_name = _class_name_from_key(key)
    if class_name in collected:
        return
    members = []
    for k, v in obj.items():
        cpp_type, nested = _infer_cpp_type(v, k)
        members.append((k, cpp_type, nested))
        if isinstance(nested, dict):
            _collect_nested_classes(nested, k, collected)
        elif isinstance(nested, list) and nested and isinstance(nested[0], dict):
            _collect_nested_classes(nested[0], k, collected)
    collected[class_name] = members


def _generate_class(name: str, members: List[Tuple[str, str, Any]]) -> str:
    """生成单个 C++ 类定义。"""
    lines = [
        f"class {name} {{",
        "public:",
    ]
    for member_name, cpp_type in [(m[0], m[1]) for m in members]:
        lines.append(f"    {cpp_type} {member_name};")
    lines.append("")
    lines.append("    %s() = default;" % name)
    lines.append("    ~%s() = default;" % name)
    lines.append("};")
    return "\n".join(lines)


def json_to_cpp(json_str: str, root_class_name: str = "MyClass") -> str:
    """将 JSON 字符串转换为 C++ 类定义代码。

    Args:
        json_str: 合法 JSON 字符串（通常为对象）。
        root_class_name: 根对象对应的 C++ 类名。

    Returns:
        多行 C++ 代码；若输入不是对象或解析失败则抛出或返回错误信息。
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return f"/* JSON 解析错误: {e} */"

    if not isinstance(data, dict):
        return "/* 请输入 JSON 对象（键值对），当前为数组或标量 */"

    # 收集根与所有嵌套类的成员
    root_members = []
    nested = {}  # class_name -> list of (member_name, cpp_type, nested_value)

    for k, v in data.items():
        cpp_type, nested_val = _infer_cpp_type(v, k)
        root_members.append((k, cpp_type, nested_val))
        if isinstance(nested_val, dict):
            _collect_nested_classes(nested_val, k, nested)
        elif isinstance(nested_val, list) and nested_val and isinstance(nested_val[0], dict):
            _collect_nested_classes(nested_val[0], k, nested)

    # 根类成员只保留 (name, type)，不重复收集根自身
    root_only = [(m[0], m[1]) for m in root_members]
    root_class = _generate_class(root_class_name, root_only)

    # 嵌套类：只生成在 root 里被引用的、且未在 root 中定义的类
    nested_classes = []
    for cls_name, members in nested.items():
        member_tuples = [(m[0], m[1]) for m in members]
        nested_classes.append(_generate_class(cls_name, member_tuples))

    if nested_classes:
        return root_class + "\n\n\n" + "\n\n\n".join(nested_classes)
    return root_class
