# -*- coding: utf-8 -*-
"""乱码修复面板"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTextEdit, QGroupBox, QSplitter, QApplication,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

from core.mojibake_fixer import (
    fix_mojibake, fix_mojibake_manual, detect_encoding,
    ENCODING_NAMES, ENCODINGS, HAS_CHARDET,
)


class MojibakePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mono = QFont("Consolas", 10)
        self._mono.setStyleHint(QFont.Monospace)
        self._results = []
        self._build_ui()

    # ── UI 搭建 ──────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(6)

        # ── 输入区 ───────────────────────────────────────────
        hdr_in = QHBoxLayout()
        hdr_in.addWidget(QLabel("乱码文本:"))
        hdr_in.addStretch()
        self._char_label = QLabel("")
        hdr_in.addWidget(self._char_label)
        root.addLayout(hdr_in)

        self._input = QTextEdit()
        self._input.setFont(self._mono)
        self._input.setPlaceholderText(
            "在此粘贴乱码文本，例如:\n"
            "ÐÂÄÔ˜Óé  /  ÄãºÃ  /  鑴掕绋嬫帹  /  ç¹ä½"
        )
        self._input.setMinimumHeight(80)
        self._input.textChanged.connect(self._update_char_count)
        root.addWidget(self._input, stretch=2)

        # ── 操作区 ───────────────────────────────────────────
        group = QGroupBox("修复选项")
        g = QVBoxLayout(group)

        # 自动修复按钮行
        r1 = QHBoxLayout()
        auto_btn = QPushButton("  一键自动修复")
        auto_btn.setFixedHeight(34)
        auto_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:13px;border-radius:4px;padding:0 22px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}")
        auto_btn.clicked.connect(self._auto_fix)
        r1.addWidget(auto_btn)

        detect_btn = QPushButton("  自动识别编码")
        detect_btn.setFixedHeight(34)
        detect_btn.setStyleSheet(
            "QPushButton{background:#107c10;color:#fff;font-weight:bold;"
            "font-size:13px;border-radius:4px;padding:0 18px}"
            "QPushButton:hover{background:#0e6b0e}"
            "QPushButton:pressed{background:#0c5a0c}")
        detect_btn.clicked.connect(self._detect_encoding)
        r1.addWidget(detect_btn)

        clear_btn = QPushButton("清空")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._clear)
        r1.addWidget(clear_btn)
        r1.addStretch()
        g.addLayout(r1)

        # 编码检测结果
        self._detect_label = QLabel("")
        self._detect_label.setWordWrap(True)
        self._detect_label.setStyleSheet(
            "color:#107c10; font-size:12px; padding:2px 4px;")
        g.addWidget(self._detect_label)

        # 手动编码选择行
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("手动指定:"))
        r2.addWidget(QLabel("错误编码:"))
        self._src_enc = QComboBox()
        self._src_enc.addItems(ENCODING_NAMES)
        self._src_enc.setCurrentText("Latin-1")
        self._src_enc.setMinimumWidth(120)
        r2.addWidget(self._src_enc)
        r2.addWidget(QLabel("→  正确编码:"))
        self._dst_enc = QComboBox()
        self._dst_enc.addItems(ENCODING_NAMES)
        self._dst_enc.setCurrentText("UTF-8")
        self._dst_enc.setMinimumWidth(120)
        r2.addWidget(self._dst_enc)

        manual_btn = QPushButton("手动修复")
        manual_btn.setFixedHeight(28)
        manual_btn.clicked.connect(self._manual_fix)
        r2.addWidget(manual_btn)
        r2.addStretch()
        g.addLayout(r2)

        root.addWidget(group)

        # ── 结果区 ───────────────────────────────────────────
        splitter = QSplitter(Qt.Vertical)

        # 结果列表（表格）
        table_w = QWidget()
        table_l = QVBoxLayout(table_w)
        table_l.setContentsMargins(0, 0, 0, 0)
        tbl_hdr = QHBoxLayout()
        tbl_hdr.addWidget(QLabel("修复结果（点击行查看完整文本）:"))
        tbl_hdr.addStretch()
        self._result_count = QLabel("")
        tbl_hdr.addWidget(self._result_count)
        table_l.addLayout(tbl_hdr)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["评分", "编码路径", "修复后文本（预览）"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setColumnWidth(0, 55)
        self._table.setColumnWidth(1, 160)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.setFont(self._mono)
        self._table.currentCellChanged.connect(self._on_row_selected)
        table_l.addWidget(self._table)
        splitter.addWidget(table_w)

        # 完整文本预览
        preview_w = QWidget()
        preview_l = QVBoxLayout(preview_w)
        preview_l.setContentsMargins(0, 0, 0, 0)
        prev_hdr = QHBoxLayout()
        prev_hdr.addWidget(QLabel("完整文本:"))
        prev_hdr.addStretch()
        self._path_label = QLabel("")
        self._path_label.setStyleSheet("color:#0078d4;font-weight:bold")
        prev_hdr.addWidget(self._path_label)
        copy_btn = QPushButton("复制")
        copy_btn.setFixedWidth(70)
        copy_btn.clicked.connect(self._copy_preview)
        prev_hdr.addWidget(copy_btn)
        preview_l.addLayout(prev_hdr)

        self._preview = QTextEdit()
        self._preview.setFont(self._mono)
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText("在上方表格中选择一行查看完整修复文本…")
        preview_l.addWidget(self._preview)
        splitter.addWidget(preview_w)

        splitter.setSizes([300, 200])
        root.addWidget(splitter, stretch=4)

        # 状态
        self._status = QLabel("就绪")
        self._status.setStyleSheet("color:#666;font-size:11px")
        root.addWidget(self._status)

    # ── 事件处理 ─────────────────────────────────────────────
    def _update_char_count(self):
        t = self._input.toPlainText()
        self._char_label.setText(f"{len(t)} 字符")

    def _detect_encoding(self):
        """使用 chardet 自动识别粘贴文本的可能编码"""
        text = self._input.toPlainText()
        if not text:
            self._status.setText("请先粘贴乱码文本")
            return

        if not HAS_CHARDET:
            self._detect_label.setText(
                "需要安装 chardet: pip install chardet")
            self._detect_label.setStyleSheet(
                "color:#cc0000; font-size:12px; padding:2px 4px;")
            return

        try:
            results = detect_encoding(text)
        except Exception as e:
            self._detect_label.setText(f"识别出错: {type(e).__name__}")
            self._detect_label.setStyleSheet(
                "color:#cc0000; font-size:12px; padding:2px 4px;")
            self._status.setText(f"出错: {e}")
            return

        if not results:
            self._detect_label.setText("无法识别编码")
            return

        lines = []
        for r in results[:5]:
            conf = r.get('confidence', 0)
            enc = r.get('encoding', '?')
            lang = r.get('language', '')
            src = r.get('source_encoding', '')
            line = f"{enc} (置信度 {conf:.0%})"
            if lang:
                line += f" [{lang}]"
            if src:
                line += f"  (原始字节按 {src} 编码)"
            lines.append(line)

        self._detect_label.setText(
            "检测结果: " + "  |  ".join(lines))
        self._detect_label.setStyleSheet(
            "color:#107c10; font-size:12px; padding:2px 4px;")

        # 如果检测到高置信度结果，自动设置手动编码选择
        best = results[0]
        if best.get('confidence', 0) > 0.5:
            src_enc = best.get('source_encoding', '')
            dst_enc = best.get('encoding', '')
            if src_enc:
                # 找到对应的显示名
                for name, code in ENCODINGS:
                    if code == src_enc:
                        self._src_enc.setCurrentText(name)
                        break
            if dst_enc:
                for name, code in ENCODINGS:
                    if code.lower() == dst_enc.lower().replace('-', '_'):
                        self._dst_enc.setCurrentText(name)
                        break
                    if name.upper() == dst_enc.upper():
                        self._dst_enc.setCurrentText(name)
                        break

        self._status.setText("编码识别完成")

    def _auto_fix(self):
        text = self._input.toPlainText()
        if not text:
            self._status.setText("请先粘贴乱码文本")
            return

        self._status.setText("正在尝试所有编码组合…")
        QApplication.processEvents()

        try:
            self._results = fix_mojibake(text)
        except Exception as e:
            self._results = []
            self._populate_table()
            self._status.setText(f"修复出错: {type(e).__name__}")
            self._result_count.setText("")
            return

        self._populate_table()

        if not self._results:
            self._status.setText("未找到可读的修复结果")
            self._result_count.setText("0 个结果")
        else:
            self._status.setText(f"找到 {len(self._results)} 个可能的修复")
            self._result_count.setText(f"{len(self._results)} 个结果")
            self._table.selectRow(0)

    def _manual_fix(self):
        text = self._input.toPlainText()
        if not text:
            self._status.setText("请先粘贴乱码文本")
            return

        src_name = self._src_enc.currentText()
        dst_name = self._dst_enc.currentText()
        # 查表获取编码名
        src_enc = dict(ENCODINGS).get(src_name, src_name.lower())
        dst_enc = dict(ENCODINGS).get(dst_name, dst_name.lower())

        try:
            fixed = fix_mojibake_manual(text, src_enc, dst_enc)
            self._results = [{
                'path': f"{src_name} → {dst_name}",
                'text': fixed,
                'score': 0,
            }]
            self._populate_table()
            self._table.selectRow(0)
            self._status.setText(f"手动修复完成: {src_name} → {dst_name}")
        except Exception as e:
            self._preview.setPlainText(f"修复失败: {e}")
            self._status.setText(f"出错: {type(e).__name__}")

    def _populate_table(self):
        self._table.setRowCount(0)
        self._table.setRowCount(len(self._results))

        for i, r in enumerate(self._results):
            # 评分
            score_item = QTableWidgetItem(str(int(r['score'])))
            score_item.setTextAlignment(Qt.AlignCenter)
            if r['score'] >= 50:
                score_item.setBackground(QColor('#ccffcc'))
            elif r['score'] >= 20:
                score_item.setBackground(QColor('#ffffcc'))
            self._table.setItem(i, 0, score_item)

            # 编码路径
            self._table.setItem(i, 1, QTableWidgetItem(r['path']))

            # 预览（截取前 200 字符，合并为单行）
            preview = r['text'].replace('\n', '↵ ')
            if len(preview) > 200:
                preview = preview[:200] + '…'
            self._table.setItem(i, 2, QTableWidgetItem(preview))

    def _on_row_selected(self, row, _col, _prev_row, _prev_col):
        if 0 <= row < len(self._results):
            r = self._results[row]
            self._preview.setPlainText(r['text'])
            self._path_label.setText(r['path'])

    def _copy_preview(self):
        t = self._preview.toPlainText()
        if t:
            QApplication.clipboard().setText(t)
            self._status.setText("已复制到剪贴板")

    def _clear(self):
        self._input.clear()
        self._preview.clear()
        self._table.setRowCount(0)
        self._results.clear()
        self._char_label.setText("")
        self._result_count.setText("")
        self._path_label.setText("")
        self._status.setText("已清空")
