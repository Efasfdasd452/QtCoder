# -*- coding: utf-8 -*-
"""中文简繁转换引擎 — 纯函数，无 UI 依赖"""

HAS_ZHCONV = False
try:
    import zhconv as _zhconv
    HAS_ZHCONV = True
except ImportError:
    pass

LOCALE_MAP = {
    '简体 → 繁体':         'zh-hant',
    '简体 → 繁体 (台湾)':  'zh-tw',
    '简体 → 繁体 (香港)':  'zh-hk',
    '繁体 → 简体':         'zh-hans',
}


def convert_zh(text, direction='简体 → 繁体'):
    """将文本在简体与繁体之间转换"""
    if not HAS_ZHCONV:
        raise RuntimeError("需要安装 zhconv:\npip install zhconv")

    locale = LOCALE_MAP.get(direction)
    if not locale:
        raise ValueError(f"不支持的转换方向: {direction}")

    return _zhconv.convert(text, locale)
