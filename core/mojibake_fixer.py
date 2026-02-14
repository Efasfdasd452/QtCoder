# -*- coding: utf-8 -*-
"""乱码修复引擎 — 纯函数，无 UI 依赖

原理: 乱码产生于 "原始字节用错误编码解读"。
修复: 把乱码字符串用 '错误编码' 重新编码回字节，再用 '正确编码' 解码。
"""

# ── 自动编码检测 ──────────────────────────────────────────────
HAS_CHARDET = False
try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    pass


def detect_encoding(data):
    """自动检测 bytes 或 str 的编码。

    参数:
        data: bytes 或 str（str 会先用 latin-1 编码为字节再检测）

    返回:
        [{'encoding': 'UTF-8', 'confidence': 0.99, 'language': 'Chinese'}, ...]
    """
    if not HAS_CHARDET:
        return [{'encoding': '(需安装 chardet)', 'confidence': 0, 'language': ''}]

    if isinstance(data, str):
        # 尝试多种编码把文本还原为字节再检测
        results = []
        seen = set()
        for enc in ['latin-1', 'cp1252', 'gbk', 'utf-8', 'shift_jis']:
            try:
                raw = data.encode(enc)
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            det = chardet.detect(raw)
            if det and det.get('encoding'):
                key = det['encoding'].upper()
                if key not in seen:
                    seen.add(key)
                    results.append({
                        'encoding': det['encoding'],
                        'confidence': det.get('confidence', 0),
                        'language': det.get('language', ''),
                        'source_encoding': enc,
                    })
        results.sort(key=lambda x: x['confidence'], reverse=True)
        return results if results else [{'encoding': '无法识别', 'confidence': 0, 'language': ''}]

    # bytes
    det = chardet.detect(data)
    if det and det.get('encoding'):
        return [{
            'encoding': det['encoding'],
            'confidence': det.get('confidence', 0),
            'language': det.get('language', ''),
        }]
    return [{'encoding': '无法识别', 'confidence': 0, 'language': ''}]


# ── 常用编码列表 ──────────────────────────────────────────────
ENCODINGS = [
    ('UTF-8',        'utf-8'),
    ('GBK',          'gbk'),
    ('GB2312',       'gb2312'),
    ('GB18030',      'gb18030'),
    ('Big5',         'big5'),
    ('Shift-JIS',    'shift_jis'),
    ('EUC-JP',       'euc-jp'),
    ('EUC-KR',       'euc-kr'),
    ('Latin-1',      'latin-1'),
    ('Windows-1252', 'cp1252'),
    ('ISO-8859-15',  'iso-8859-15'),
    ('CP437',        'cp437'),
    ('CP850',        'cp850'),
    ('ASCII',        'ascii'),
    ('UTF-16-LE',    'utf-16-le'),
    ('UTF-16-BE',    'utf-16-be'),
]

ENCODING_NAMES = [name for name, _ in ENCODINGS]


def fix_mojibake(garbled_text, max_results=30):
    """自动尝试所有编码组合修复乱码。

    返回按可读性评分降序排列的列表:
        [{'path': 'Latin-1 → UTF-8', 'text': '修复后文本', 'score': 85}, ...]
    """
    garbled_len = len(garbled_text)
    results = []
    seen = set()

    for src_name, src_enc in ENCODINGS:
        # 1) 把乱码字符串用 src_enc 编码回字节
        try:
            raw = garbled_text.encode(src_enc)
        except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
            continue

        for dst_name, dst_enc in ENCODINGS:
            if src_enc == dst_enc:
                continue

            # 2) 用 dst_enc 解码字节
            try:
                fixed = raw.decode(dst_enc)
            except (UnicodeDecodeError, UnicodeEncodeError, LookupError):
                continue

            # 跳过与原文完全相同的结果
            if fixed == garbled_text:
                continue
            # 跳过空文本
            if not fixed.strip():
                continue
            # 跳过重复
            if fixed in seen:
                continue
            seen.add(fixed)

            score = _readability_score(fixed, garbled_len)
            if score > 0:
                results.append({
                    'path': f"{src_name} → {dst_name}",
                    'text': fixed,
                    'score': score,
                })

    results.sort(key=lambda r: r['score'], reverse=True)
    return results[:max_results]


def fix_mojibake_manual(garbled_text, src_encoding, dst_encoding):
    """手动指定编码组合修复乱码。"""
    raw = garbled_text.encode(src_encoding)
    return raw.decode(dst_encoding)


# ── 可读性评分 ────────────────────────────────────────────────
def _readability_score(text, garbled_len=0):
    """对文本的可读性打分（基于比率）。分数越高越可能是正确解码。

    核心思路:
    - 高比率的 CJK 汉字 / 可打印 ASCII = 好
    - 控制字符 / 替换字符 / 私用区 = 坏
    - 结果比乱码短（多字节→单字节的逆过程）= 更可能正确
    - 结果比乱码长很多（如 UTF-16 膨胀）= 可能是假阳性
    """
    if not text:
        return 0

    total = len(text)
    cjk = 0             # 中日韩统一表意文字
    cjk_punct = 0       # 中文标点
    ascii_print = 0     # 可打印 ASCII
    whitespace = 0      # 常见空白
    control = 0         # 控制字符（不含常见空白）
    replacement = 0     # U+FFFD 替换字符
    private_use = 0     # 私用区字符
    hangul = 0          # 韩文
    kana = 0            # 日文假名

    for ch in text:
        cp = ord(ch)
        if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
            cjk += 1
        elif 0x3000 <= cp <= 0x303F or 0xFF00 <= cp <= 0xFFEF:
            cjk_punct += 1
        elif 0x20 <= cp <= 0x7E:
            ascii_print += 1
        elif cp in (0x09, 0x0A, 0x0D, 0x20):
            whitespace += 1
        elif cp < 0x20:
            control += 1
        elif cp == 0xFFFD:
            replacement += 1
        elif 0xE000 <= cp <= 0xF8FF:
            private_use += 1
        elif 0xAC00 <= cp <= 0xD7AF:
            hangul += 1
        elif 0x3040 <= cp <= 0x30FF:
            kana += 1

    # ── 基础: 可读字符比率 (0~100) ───────────────────────
    readable = cjk + cjk_punct + ascii_print + whitespace + hangul + kana
    bad = control + replacement + private_use

    if total == 0:
        return 0
    ratio = readable / total
    bad_ratio = bad / total

    score = ratio * 100

    # ── 奖惩 ─────────────────────────────────────────────
    # CJK 为主的文本通常就是正确结果
    cjk_all = cjk + hangul + kana
    if total > 0 and cjk_all / total > 0.6:
        score += 30
    elif total > 0 and cjk_all / total > 0.3:
        score += 15

    # 坏字符扣分
    score -= bad_ratio * 200

    # 可读比率过低 → 扣分
    if ratio < 0.7:
        score -= 20
    if ratio < 0.5:
        score -= 30

    # ── 长度惩罚: 结果比原文长很多 = 大概率假阳性 ────────
    if garbled_len > 0:
        len_ratio = total / garbled_len
        if len_ratio > 1.5:
            score -= 40      # 明显膨胀
        elif len_ratio > 1.2:
            score -= 15
        elif len_ratio < 0.8:
            score += 10      # 压缩 = 多字节还原，加分

    return max(score, 0)
