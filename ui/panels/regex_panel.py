# -*- coding: utf-8 -*-
"""正则表达式测试面板"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QCheckBox, QPushButton, QTextEdit, QGroupBox, QSplitter,
    QApplication
)
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtCore import Qt

from core.regex_tester import test_regex


class RegexPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mono = QFont("Consolas", 10)
        self._mono.setStyleHint(QFont.Monospace)
        self._build_ui()

    # ── UI 搭建 ──────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(6)

        # ── 正则选项 ─────────────────────────────────────────
        group = QGroupBox("正则表达式选项")
        g = QVBoxLayout(group)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("正则:"))
        self._pattern = QLineEdit()
        self._pattern.setFont(self._mono)
        self._pattern.setPlaceholderText(
            r'输入正则表达式，如 \d+、[a-zA-Z]+、(\w+)@(\w+)\.(\w+)')
        r1.addWidget(self._pattern, stretch=1)
        g.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("标志:"))
        self._flag_i = QCheckBox("忽略大小写 (re.I)")
        self._flag_m = QCheckBox("多行模式 (re.M)")
        self._flag_s = QCheckBox("单行模式 (re.S)")
        r2.addWidget(self._flag_i)
        r2.addWidget(self._flag_m)
        r2.addWidget(self._flag_s)
        r2.addStretch()
        g.addLayout(r2)

        root.addWidget(group)

        # ── 测试文本 ─────────────────────────────────────────
        hdr_in = QHBoxLayout()
        hdr_in.addWidget(QLabel("测试文本:"))
        hdr_in.addStretch()
        self._char_label = QLabel("")
        hdr_in.addWidget(self._char_label)
        root.addLayout(hdr_in)

        self._input = QTextEdit()
        self._input.setFont(self._mono)
        self._input.setPlaceholderText("在此输入要测试的文本…")
        self._input.setMinimumHeight(80)
        self._input.textChanged.connect(self._update_char_count)
        root.addWidget(self._input, stretch=2)

        # ── 按钮行 ───────────────────────────────────────────
        btn_row = QHBoxLayout()
        exec_btn = QPushButton("▶  匹配测试")
        exec_btn.setFixedHeight(34)
        exec_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:13px;border-radius:4px;padding:0 22px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}")
        exec_btn.clicked.connect(self._execute)
        btn_row.addWidget(exec_btn)
        clear_btn = QPushButton("清空")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── 结果区（上: 高亮，下: 详情） ────────────────────
        splitter = QSplitter(Qt.Vertical)

        hl_w = QWidget()
        hl_l = QVBoxLayout(hl_w)
        hl_l.setContentsMargins(0, 0, 0, 0)
        hl_l.addWidget(QLabel("高亮结果:"))
        self._highlight_area = QTextEdit()
        self._highlight_area.setFont(self._mono)
        self._highlight_area.setReadOnly(True)
        self._highlight_area.setPlaceholderText("匹配高亮将显示在此…")
        hl_l.addWidget(self._highlight_area)
        splitter.addWidget(hl_w)

        det_w = QWidget()
        det_l = QVBoxLayout(det_w)
        det_l.setContentsMargins(0, 0, 0, 0)
        det_hdr = QHBoxLayout()
        det_hdr.addWidget(QLabel("匹配详情:"))
        det_hdr.addStretch()
        copy_btn = QPushButton("复制")
        copy_btn.setFixedWidth(70)
        copy_btn.clicked.connect(self._copy_details)
        det_hdr.addWidget(copy_btn)
        det_l.addLayout(det_hdr)
        self._detail_area = QTextEdit()
        self._detail_area.setFont(self._mono)
        self._detail_area.setReadOnly(True)
        det_l.addWidget(self._detail_area)
        splitter.addWidget(det_w)

        root.addWidget(splitter, stretch=3)

        # 状态
        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet("color:#666;font-size:11px")
        root.addWidget(self._status_label)

    # ── 事件处理 ─────────────────────────────────────────────
    def _update_char_count(self):
        t = self._input.toPlainText()
        self._char_label.setText(f"{len(t)} 字符")

    def _execute(self):
        pattern = self._pattern.text()
        text = self._input.toPlainText()

        if not pattern:
            self._status_label.setText("请输入正则表达式")
            return
        if not text:
            self._status_label.setText("请输入测试文本")
            return

        matches, details, highlighted = test_regex(
            pattern, text,
            ignore_case=self._flag_i.isChecked(),
            multiline=self._flag_m.isChecked(),
            dotall=self._flag_s.isChecked(),
        )

        if matches is None:
            self._detail_area.setPlainText(details)
            self._highlight_area.clear()
            self._status_label.setText("正则表达式错误")
        else:
            self._highlight_area.setHtml(highlighted)
            self._detail_area.setPlainText(details)
            count = len(matches) if matches else 0
            self._status_label.setText(f"找到 {count} 个匹配")

    def _clear(self):
        self._pattern.clear()
        self._input.clear()
        self._highlight_area.clear()
        self._detail_area.clear()
        self._char_label.setText("")
        self._status_label.setText("已清空")

    def _copy_details(self):
        t = self._detail_area.toPlainText()
        if t:
            QApplication.clipboard().setText(t)
            self._status_label.setText("已复制到剪贴板")
