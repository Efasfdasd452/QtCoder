# -*- coding: utf-8 -*-
"""字符串比对引擎 — 纯函数，无 UI 依赖"""

import difflib
import html as html_lib


def compute_diff(text_a, text_b):
    """逐行比对，返回 (summary, html)"""
    if text_a == text_b:
        return "两个文本完全相同。", ""

    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)

    sm = difflib.SequenceMatcher(None, lines_a, lines_b)
    html_parts = []
    stats = {'added': 0, 'deleted': 0, 'changed': 0}

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            for line in lines_a[i1:i2]:
                html_parts.append(f'  {html_lib.escape(line)}')

        elif op == 'delete':
            stats['deleted'] += i2 - i1
            for line in lines_a[i1:i2]:
                escaped = html_lib.escape(line)
                html_parts.append(
                    '<span style="background-color:#ffcccc;'
                    'text-decoration:line-through;">'
                    f'- {escaped}</span>'
                )

        elif op == 'insert':
            stats['added'] += j2 - j1
            for line in lines_b[j1:j2]:
                escaped = html_lib.escape(line)
                html_parts.append(
                    '<span style="background-color:#ccffcc;">'
                    f'+ {escaped}</span>'
                )

        elif op == 'replace':
            stats['changed'] += max(i2 - i1, j2 - j1)
            # 对被替换的行做逐字符高亮
            old_lines = lines_a[i1:i2]
            new_lines = lines_b[j1:j2]
            for k in range(max(len(old_lines), len(new_lines))):
                if k < len(old_lines) and k < len(new_lines):
                    html_parts.append(
                        _inline_char_diff(old_lines[k], new_lines[k])
                    )
                elif k < len(old_lines):
                    escaped = html_lib.escape(old_lines[k])
                    html_parts.append(
                        '<span style="background-color:#ffcccc;'
                        'text-decoration:line-through;">'
                        f'- {escaped}</span>'
                    )
                else:
                    escaped = html_lib.escape(new_lines[k])
                    html_parts.append(
                        '<span style="background-color:#ccffcc;">'
                        f'+ {escaped}</span>'
                    )

    summary = (
        f"差异统计: 删除 {stats['deleted']} 行, "
        f"新增 {stats['added']} 行, "
        f"修改 {stats['changed']} 行"
    )
    html_content = ''.join(html_parts).replace('\n', '<br>')
    full_html = (
        '<pre style="font-family:Consolas,monospace;font-size:10pt;'
        f'white-space:pre-wrap;line-height:1.6;">{html_content}</pre>'
    )
    return summary, full_html


def compute_inline_diff(text_a, text_b):
    """逐字符比对，返回 (summary, html)"""
    if text_a == text_b:
        return "两个文本完全相同。", ""

    sm = difflib.SequenceMatcher(None, text_a, text_b)
    html_parts = []

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            html_parts.append(html_lib.escape(text_a[i1:i2]))
        elif op == 'delete':
            escaped = html_lib.escape(text_a[i1:i2])
            html_parts.append(
                '<span style="background-color:#ff9999;'
                'text-decoration:line-through;">'
                f'{escaped}</span>'
            )
        elif op == 'insert':
            escaped = html_lib.escape(text_b[j1:j2])
            html_parts.append(
                f'<span style="background-color:#99ff99;">{escaped}</span>'
            )
        elif op == 'replace':
            old = html_lib.escape(text_a[i1:i2])
            new = html_lib.escape(text_b[j1:j2])
            html_parts.append(
                '<span style="background-color:#ff9999;'
                f'text-decoration:line-through;">{old}</span>'
                f'<span style="background-color:#99ff99;">{new}</span>'
            )

    a_len, b_len = len(text_a), len(text_b)
    summary = (
        f"文本A: {a_len} 字符, 文本B: {b_len} 字符, "
        f"长度差: {abs(a_len - b_len)} 字符"
    )
    html_content = ''.join(html_parts).replace('\n', '<br>')
    full_html = (
        '<pre style="font-family:Consolas,monospace;font-size:10pt;'
        f'white-space:pre-wrap;line-height:1.6;">{html_content}</pre>'
    )
    return summary, full_html


# ── 内部工具 ──────────────────────────────────────────────────
def _inline_char_diff(old_line, new_line):
    """对一对被替换的行做逐字符 diff，返回 HTML 片段"""
    sm = difflib.SequenceMatcher(None, old_line, new_line)
    old_parts, new_parts = [], []

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            old_parts.append(html_lib.escape(old_line[i1:i2]))
            new_parts.append(html_lib.escape(new_line[j1:j2]))
        elif op == 'delete':
            old_parts.append(
                '<span style="background-color:#ff6666;font-weight:bold;">'
                f'{html_lib.escape(old_line[i1:i2])}</span>'
            )
        elif op == 'insert':
            new_parts.append(
                '<span style="background-color:#66ff66;font-weight:bold;">'
                f'{html_lib.escape(new_line[j1:j2])}</span>'
            )
        elif op == 'replace':
            old_parts.append(
                '<span style="background-color:#ff6666;font-weight:bold;">'
                f'{html_lib.escape(old_line[i1:i2])}</span>'
            )
            new_parts.append(
                '<span style="background-color:#66ff66;font-weight:bold;">'
                f'{html_lib.escape(new_line[j1:j2])}</span>'
            )

    return (
        '<span style="background-color:#ffcccc;text-decoration:line-through;">'
        f'- {"".join(old_parts)}</span>'
        '<span style="background-color:#ccffcc;">'
        f'+ {"".join(new_parts)}</span>'
    )
