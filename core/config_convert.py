# -*- coding: utf-8 -*-
"""配置文件格式互转 — JSON ↔ YAML ↔ TOML

依赖:
    pyyaml  — pip install pyyaml
    toml    — pip install toml
"""

import json


# ── 懒加载：给出清晰的错误提示 ───────────────────────────────
def _yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        raise ImportError("请先安装 pyyaml：pip install pyyaml")


def _toml():
    try:
        import toml
        return toml
    except ImportError:
        raise ImportError("请先安装 toml：pip install toml")


# ── 格式常量 ──────────────────────────────────────────────────
FORMATS = ['JSON', 'YAML', 'TOML']


# ── 解析（输入格式 → Python 对象）──────────────────────────────
def _load(text: str, fmt: str) -> object:
    fmt = fmt.upper()
    if fmt == 'JSON':
        return json.loads(text)
    elif fmt == 'YAML':
        return _yaml().safe_load(text)
    elif fmt == 'TOML':
        return _toml().loads(text)
    else:
        raise ValueError(f"不支持的格式: {fmt}")


# ── 序列化（Python 对象 → 输出格式）──────────────────────────
def _dump(obj: object, fmt: str, indent: int = 2) -> str:
    fmt = fmt.upper()
    if fmt == 'JSON':
        return json.dumps(obj, ensure_ascii=False, indent=indent)
    elif fmt == 'YAML':
        yaml = _yaml()
        return yaml.dump(obj, allow_unicode=True,
                         default_flow_style=False, sort_keys=False)
    elif fmt == 'TOML':
        toml = _toml()
        return toml.dumps(obj)
    else:
        raise ValueError(f"不支持的格式: {fmt}")


# ── 公共转换接口 ──────────────────────────────────────────────
def convert(text: str, from_fmt: str, to_fmt: str,
            json_indent: int = 2) -> str:
    """将 text 从 from_fmt 转换为 to_fmt。

    Raises: ValueError / ImportError / json.JSONDecodeError / yaml.YAMLError
    """
    if from_fmt.upper() == to_fmt.upper():
        # 同格式：直接格式化/重新美化
        obj = _load(text, from_fmt)
        return _dump(obj, to_fmt, indent=json_indent)

    obj = _load(text, from_fmt)
    return _dump(obj, to_fmt, indent=json_indent)


def check_deps() -> dict[str, bool]:
    """检查可选依赖是否已安装。"""
    result = {}
    try:
        import yaml   # noqa
        result['pyyaml'] = True
    except ImportError:
        result['pyyaml'] = False
    try:
        import toml   # noqa
        result['toml'] = True
    except ImportError:
        result['toml'] = False
    return result
