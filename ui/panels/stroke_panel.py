# -*- coding: utf-8 -*-
"""汉字笔画数统计面板

输入一段汉字文本，自动过滤英文/数字/符号，
输出每个汉字的笔画数，末尾显示总笔画数统计。
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QApplication, QAbstractItemView, QSizePolicy,
    QSplitter,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

from core.stroke_count import analyze_text, summary


# ── 字体 ────────────────────────────────────────────────────────
_MONO = QFont("Consolas", 10)
_MONO.setStyleHint(QFont.Monospace)
_CJK_FONT = QFont("Microsoft YaHei", 12)


class StrokePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    # ─────────────────────────────────────────────────────────────
    #  界面构建
    # ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Vertical)

        # ── 输入区 ────────────────────────────────────────────────
        in_group = QGroupBox("输入文本")
        in_lay = QVBoxLayout(in_group)
        in_lay.setContentsMargins(6, 6, 6, 6)

        self._input = QPlainTextEdit()
        self._input.setFont(_CJK_FONT)
        self._input.setPlaceholderText(
            "在此粘贴或输入汉字文本…\n英文、数字、标点将自动过滤，只统计汉字笔画。"
        )
        self._input.setFixedHeight(110)
        in_lay.addWidget(self._input)

        btn_row = QHBoxLayout()
        self._analyze_btn = QPushButton("  统计笔画")
        self._analyze_btn.setFixedHeight(32)
        self._analyze_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:13px;border-radius:4px;padding:0 20px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}"
        )
        self._analyze_btn.clicked.connect(self._on_analyze)
        btn_row.addWidget(self._analyze_btn)

        self._clear_btn = QPushButton("清空")
        self._clear_btn.setFixedWidth(64)
        self._clear_btn.setFixedHeight(32)
        self._clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(self._clear_btn)

        btn_row.addStretch()

        self._status = QLabel("就绪")
        self._status.setStyleSheet("color:#666;font-size:11px")
        btn_row.addWidget(self._status)
        in_lay.addLayout(btn_row)

        splitter.addWidget(in_group)

        # ── 输出区 ────────────────────────────────────────────────
        out_group = QGroupBox("笔画统计结果")
        out_lay = QVBoxLayout(out_group)
        out_lay.setContentsMargins(6, 6, 6, 6)
        out_lay.setSpacing(6)

        # 汇总栏
        sum_row = QHBoxLayout()
        self._lbl_total_chars = QLabel("汉字数: —")
        self._lbl_total_chars.setStyleSheet("font-weight:bold;font-size:12px")
        self._lbl_total_strokes = QLabel("总笔画: —")
        self._lbl_total_strokes.setStyleSheet(
            "font-weight:bold;font-size:12px;color:#0078d4")
        self._lbl_unknown = QLabel("")
        self._lbl_unknown.setStyleSheet("color:#ca5010;font-size:11px")

        sum_row.addWidget(self._lbl_total_chars)
        sum_row.addSpacing(24)
        sum_row.addWidget(self._lbl_total_strokes)
        sum_row.addSpacing(24)
        sum_row.addWidget(self._lbl_unknown)
        sum_row.addStretch()

        self._copy_btn = QPushButton("复制结果")
        self._copy_btn.setFixedWidth(80)
        self._copy_btn.clicked.connect(self._on_copy)
        sum_row.addWidget(self._copy_btn)
        out_lay.addLayout(sum_row)

        # 表格
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["汉字", "笔画数"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Fixed)
        self._table.setColumnWidth(1, 80)
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setFont(_CJK_FONT)
        out_lay.addWidget(self._table)

        splitter.addWidget(out_group)
        splitter.setSizes([220, 480])
        root.addWidget(splitter, stretch=1)

    # ─────────────────────────────────────────────────────────────
    #  事件处理
    # ─────────────────────────────────────────────────────────────

    def _on_analyze(self):
        text = self._input.toPlainText()
        if not text.strip():
            self._status.setText("请先输入文本")
            return

        items = analyze_text(text)
        if not items:
            self._status.setText("未检测到汉字")
            self._table.setRowCount(0)
            self._lbl_total_chars.setText("汉字数: 0")
            self._lbl_total_strokes.setText("总笔画: 0")
            self._lbl_unknown.setText("")
            return

        stat = summary(items)

        # 填表
        self._table.setRowCount(len(items))
        for row, (ch, strokes) in enumerate(items):
            ch_item = QTableWidgetItem(ch)
            ch_item.setTextAlignment(Qt.AlignCenter)
            if strokes < 0:
                s_item = QTableWidgetItem("?")
                s_item.setForeground(QColor("#ca5010"))
            else:
                s_item = QTableWidgetItem(str(strokes))
            s_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 0, ch_item)
            self._table.setItem(row, 1, s_item)

        # 更新汇总
        self._lbl_total_chars.setText(
            f"汉字数: {stat['total_chars']}  （不重复: {stat['unique_chars']}）"
        )
        self._lbl_total_strokes.setText(
            f"总笔画: {stat['total_strokes']}"
        )
        unknown = stat["unknown_list"]
        if unknown:
            self._lbl_unknown.setText(
                f"未知笔画 {len(unknown)} 字: {''.join(unknown[:12])}"
                + ("…" if len(unknown) > 12 else "")
            )
        else:
            self._lbl_unknown.setText("")

        self._status.setText(
            f"完成：{stat['total_chars']} 个汉字，"
            f"总笔画 {stat['total_strokes']}"
        )

    def _on_clear(self):
        self._input.clear()
        self._table.setRowCount(0)
        self._lbl_total_chars.setText("汉字数: —")
        self._lbl_total_strokes.setText("总笔画: —")
        self._lbl_unknown.setText("")
        self._status.setText("就绪")

    def _on_copy(self):
        rows = self._table.rowCount()
        if rows == 0:
            self._status.setText("暂无结果可复制")
            return
        lines = []
        for r in range(rows):
            ch = self._table.item(r, 0).text()
            s  = self._table.item(r, 1).text()
            lines.append(f"{ch}\t{s}")
        # 追加汇总
        total_text = self._lbl_total_strokes.text()
        lines.append("")
        lines.append(total_text)
        QApplication.clipboard().setText("\n".join(lines))
        self._status.setText("已复制到剪贴板")
