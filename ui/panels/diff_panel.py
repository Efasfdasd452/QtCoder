# -*- coding: utf-8 -*-
"""字符串比对面板"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QGroupBox, QSplitter,
    QRadioButton, QButtonGroup, QApplication
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from core.string_diff import compute_diff, compute_inline_diff


class DiffPanel(QWidget):
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

        # ── 选项 ─────────────────────────────────────────────
        group = QGroupBox("比对选项")
        g = QHBoxLayout(group)
        g.addWidget(QLabel("比对模式:"))
        self._mode_group = QButtonGroup(self)
        self._mode_line = QRadioButton("逐行比对")
        self._mode_char = QRadioButton("逐字符比对")
        self._mode_line.setChecked(True)
        self._mode_group.addButton(self._mode_line, 0)
        self._mode_group.addButton(self._mode_char, 1)
        g.addWidget(self._mode_line)
        g.addWidget(self._mode_char)
        g.addStretch()
        root.addWidget(group)

        # ── 两栏输入 ─────────────────────────────────────────
        input_splitter = QSplitter(Qt.Horizontal)

        # 文本 A
        a_w = QWidget()
        a_l = QVBoxLayout(a_w)
        a_l.setContentsMargins(0, 0, 0, 0)
        a_l.addWidget(QLabel("文本 A:"))
        self._input_a = QTextEdit()
        self._input_a.setFont(self._mono)
        self._input_a.setPlaceholderText("输入第一段文本…")
        a_l.addWidget(self._input_a)
        input_splitter.addWidget(a_w)

        # 文本 B
        b_w = QWidget()
        b_l = QVBoxLayout(b_w)
        b_l.setContentsMargins(0, 0, 0, 0)
        b_l.addWidget(QLabel("文本 B:"))
        self._input_b = QTextEdit()
        self._input_b.setFont(self._mono)
        self._input_b.setPlaceholderText("输入第二段文本…")
        b_l.addWidget(self._input_b)
        input_splitter.addWidget(b_w)

        root.addWidget(input_splitter, stretch=3)

        # ── 按钮行 ───────────────────────────────────────────
        btn_row = QHBoxLayout()
        exec_btn = QPushButton("▶  比对")
        exec_btn.setFixedHeight(34)
        exec_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:13px;border-radius:4px;padding:0 22px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}")
        exec_btn.clicked.connect(self._execute)
        btn_row.addWidget(exec_btn)

        swap_btn = QPushButton("⇅ 交换")
        swap_btn.setFixedHeight(30)
        swap_btn.clicked.connect(self._swap)
        btn_row.addWidget(swap_btn)

        clear_btn = QPushButton("清空")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── 输出区 ───────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("比对结果:"))
        hdr.addStretch()
        self._summary_label = QLabel("")
        hdr.addWidget(self._summary_label)
        copy_btn = QPushButton("复制")
        copy_btn.setFixedWidth(70)
        copy_btn.clicked.connect(self._copy)
        hdr.addWidget(copy_btn)
        root.addLayout(hdr)

        self._output = QTextEdit()
        self._output.setFont(self._mono)
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("比对结果将显示在此…")
        root.addWidget(self._output, stretch=3)

        # 状态
        self._status = QLabel("就绪")
        self._status.setStyleSheet("color:#666;font-size:11px")
        root.addWidget(self._status)

    # ── 事件处理 ─────────────────────────────────────────────
    def _execute(self):
        text_a = self._input_a.toPlainText()
        text_b = self._input_b.toPlainText()

        if not text_a and not text_b:
            self._status.setText("请输入要比对的文本")
            return

        try:
            if self._mode_char.isChecked():
                summary, html = compute_inline_diff(text_a, text_b)
            else:
                summary, html = compute_diff(text_a, text_b)

            self._summary_label.setText(summary)
            if html:
                self._output.setHtml(html)
            else:
                self._output.setPlainText(summary)
            self._status.setText("比对完成")
        except Exception as e:
            self._output.setPlainText(f"错误: {e}")
            self._status.setText(f"出错: {type(e).__name__}")

    def _swap(self):
        a = self._input_a.toPlainText()
        b = self._input_b.toPlainText()
        self._input_a.setPlainText(b)
        self._input_b.setPlainText(a)

    def _clear(self):
        self._input_a.clear()
        self._input_b.clear()
        self._output.clear()
        self._summary_label.setText("")
        self._status.setText("已清空")

    def _copy(self):
        t = self._output.toPlainText()
        if t:
            QApplication.clipboard().setText(t)
            self._status.setText("已复制到剪贴板")
