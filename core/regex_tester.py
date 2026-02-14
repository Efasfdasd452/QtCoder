# -*- coding: utf-8 -*-
"""正则表达式测试引擎 — 纯函数，无 UI 依赖"""

import re
import html as html_lib

# 高亮颜色循环
MATCH_COLORS = [
    '#FFFF00', '#FF9632', '#00FF96', '#00CFFF',
    '#FF69B4', '#DDA0DD', '#87CEEB', '#98FB98',
]


def test_regex(pattern, text, ignore_case=False, multiline=False, dotall=False):
    """执行正则匹配。

    返回:
        (matches, details_text, highlighted_html)
        - 正则错误时 matches=None, details 为错误信息
        - 无匹配时 matches=[]
    """
    flags = 0
    if ignore_case:
        flags |= re.IGNORECASE
    if multiline:
        flags |= re.MULTILINE
    if dotall:
        flags |= re.DOTALL

    try:
        compiled = re.compile(pattern, flags)
    except re.error as e:
        return None, f"正则表达式错误: {e}", ""

    matches = list(compiled.finditer(text))
    highlighted = _build_highlighted_html(text, matches)

    if not matches:
        return matches, "没有找到匹配", highlighted

    details = _build_match_details(matches)
    return matches, details, highlighted


# ── 内部函数 ──────────────────────────────────────────────────
def _build_highlighted_html(text, matches):
    """将匹配部分用彩色 <span> 包裹"""
    if not matches:
        escaped = html_lib.escape(text).replace('\n', '<br>')
        return (
            '<pre style="font-family:Consolas,monospace;font-size:10pt;'
            f'white-space:pre-wrap;">{escaped}</pre>'
        )

    parts = []
    last_end = 0
    for i, m in enumerate(matches):
        color = MATCH_COLORS[i % len(MATCH_COLORS)]
        if m.start() > last_end:
            parts.append(html_lib.escape(text[last_end:m.start()]))
        matched = html_lib.escape(text[m.start():m.end()])
        parts.append(
            f'<span style="background-color:{color};color:#000;'
            f'border-radius:2px;padding:1px 2px;">{matched}</span>'
        )
        last_end = m.end()

    if last_end < len(text):
        parts.append(html_lib.escape(text[last_end:]))

    html_text = ''.join(parts).replace('\n', '<br>')
    return (
        '<pre style="font-family:Consolas,monospace;font-size:10pt;'
        f'white-space:pre-wrap;">{html_text}</pre>'
    )


def _build_match_details(matches):
    """生成匹配详情文本"""
    lines = [f"共找到 {len(matches)} 个匹配:\n"]
    for i, m in enumerate(matches):
        lines.append(
            f"匹配 #{i + 1}: \"{m.group()}\"  位置: [{m.start()}-{m.end()})"
        )
        if m.groupdict():
            for name, val in m.groupdict().items():
                if val is not None:
                    lines.append(f"  命名组 '{name}': \"{val}\"")
        if m.groups():
            for j, g in enumerate(m.groups(), 1):
                if g is not None:
                    lines.append(f"  组 {j}: \"{g}\"")
    return '\n'.join(lines)
