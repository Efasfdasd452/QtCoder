# -*- coding: utf-8 -*-
"""HTML 美化 & 搜索引擎 — 纯函数，无 UI 依赖

功能:
    - HTML 代码美化 / 格式化（基于 lxml）
    - XPath 搜索
    - 关键字搜索（带行号）
    - 正则搜索（带行号）
"""

import re

HAS_LXML = False
try:
    from lxml import html, etree
    HAS_LXML = True
except ImportError:
    pass


# ── HTML 美化 ─────────────────────────────────────────────────
def beautify_html(html_str, indent=2):
    """将压缩的 HTML 格式化为缩进排版的多行 HTML。"""
    if not HAS_LXML:
        raise RuntimeError("需要安装 lxml:\npip install lxml")

    html_str = html_str.strip()
    if not html_str:
        return ''

    # 判断是完整文档还是片段
    is_full_doc = bool(
        re.match(r'\s*<(!doctype|html)\b', html_str, re.IGNORECASE)
    )

    try:
        if is_full_doc:
            doc = html.document_fromstring(html_str)
            etree.indent(doc, space=' ' * indent)
            result = etree.tostring(
                doc, pretty_print=True, encoding='unicode', method='html'
            )
        else:
            # 片段: 可能包含多个顶级元素
            fragments = html.fragments_fromstring(html_str)
            parts = []
            for frag in fragments:
                if hasattr(frag, 'tag'):
                    etree.indent(frag, space=' ' * indent)
                    s = etree.tostring(
                        frag, pretty_print=True,
                        encoding='unicode', method='html'
                    )
                    parts.append(s)
                else:
                    # 纯文本节点
                    t = str(frag).strip()
                    if t:
                        parts.append(t)
            result = '\n'.join(parts)
    except etree.XMLSyntaxError:
        # 最后保底: 强制解析
        doc = html.document_fromstring(html_str)
        etree.indent(doc, space=' ' * indent)
        result = etree.tostring(
            doc, pretty_print=True, encoding='unicode', method='html'
        )

    return result.rstrip('\n') + '\n'


# ── XPath 搜索 ───────────────────────────────────────────────
def xpath_search(html_str, xpath_expr):
    """在 HTML 中执行 XPath 查询。

    返回: [{'index': 1, 'text': '<div>...</div>', 'tag': 'div'}, ...]
    """
    if not HAS_LXML:
        raise RuntimeError("需要安装 lxml:\npip install lxml")

    doc = html.document_fromstring(html_str)
    try:
        nodes = doc.xpath(xpath_expr)
    except etree.XPathEvalError as e:
        raise ValueError(f"XPath 语法错误: {e}")

    results = []
    for i, node in enumerate(nodes, 1):
        if hasattr(node, 'tag'):
            text = etree.tostring(
                node, pretty_print=True,
                encoding='unicode', method='html'
            ).strip()
            tag = node.tag
        elif isinstance(node, str):
            text = node
            tag = '(text)'
        else:
            text = str(node)
            tag = type(node).__name__
        results.append({'index': i, 'text': text, 'tag': tag})

    return results


# ── 关键字搜索 ───────────────────────────────────────────────
def keyword_search(text, keyword, case_sensitive=False):
    """在文本中搜索关键字，返回所有匹配位置。

    返回: [{'line': 1, 'col': 5, 'pos': 4, 'length': 3, 'context': '...'}, ...]
    """
    if not keyword:
        return []

    if not case_sensitive:
        search_text = text.lower()
        search_key = keyword.lower()
    else:
        search_text = text
        search_key = keyword

    results = []
    lines = text.splitlines()
    abs_pos = 0  # 文本中的绝对位置

    for line_no, line in enumerate(lines, 1):
        s_line = line.lower() if not case_sensitive else line
        col = 0
        while True:
            idx = s_line.find(search_key, col)
            if idx == -1:
                break
            results.append({
                'line': line_no,
                'col': idx + 1,
                'pos': abs_pos + idx,
                'length': len(keyword),
                'context': _truncate(line.strip(), 120),
            })
            col = idx + 1
        abs_pos += len(line) + 1  # +1 换行符

    return results


# ── 正则搜索 ─────────────────────────────────────────────────
def regex_search_html(text, pattern, ignore_case=False):
    """在文本中用正则搜索，返回所有匹配位置。

    返回: [{'line': 1, 'col': 5, 'pos': 4, 'length': 3,
            'match': '...', 'context': '...'}, ...]
    """
    flags = re.IGNORECASE if ignore_case else 0
    try:
        compiled = re.compile(pattern, flags)
    except re.error as e:
        raise ValueError(f"正则表达式错误: {e}")

    lines = text.splitlines()
    results = []
    for m in compiled.finditer(text):
        line_no = text[:m.start()].count('\n') + 1
        line_start = text.rfind('\n', 0, m.start()) + 1
        col = m.start() - line_start + 1
        ctx = lines[line_no - 1] if line_no <= len(lines) else ''
        results.append({
            'line': line_no,
            'col': col,
            'pos': m.start(),
            'length': m.end() - m.start(),
            'match': m.group(),
            'context': _truncate(ctx.strip(), 120),
        })
    return results


# ── 工具 ─────────────────────────────────────────────────────
def _truncate(s, max_len):
    return s if len(s) <= max_len else s[:max_len] + '…'
