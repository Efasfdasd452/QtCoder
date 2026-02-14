# -*- coding: utf-8 -*-
"""加密 / 哈希方式识别面板"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QApplication,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFrame, QGroupBox,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

from core.cipher_identifier import identify


class IdentifierPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mono = QFont("Consolas", 10)
        self._mono.setStyleHint(QFont.Monospace)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(6)

        # ── 输入区 ────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("粘贴加密/哈希字符串:"))
        hdr.addStretch()
        self._char_label = QLabel("")
        hdr.addWidget(self._char_label)
        root.addLayout(hdr)

        self._input = QTextEdit()
        self._input.setFont(self._mono)
        self._input.setPlaceholderText(
            "在此粘贴要识别的字符串，例如:\n"
            "  e10adc3949ba59abbe56e057f20f883e\n"
            "  $2b$12$LJ3m4ys3Lk.X7eEFJ5PNru...\n"
            "  eyJhbGciOiJIUzI1NiJ9.eyJ...\n"
            "  -----BEGIN PGP MESSAGE-----\n"
            "  U2FsdGVkX1+... (OpenSSL enc)\n"
            "  1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa (Bitcoin)\n"
        )
        self._input.setMaximumHeight(150)
        self._input.textChanged.connect(self._on_text_changed)
        root.addWidget(self._input)

        # ── 按钮行 ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        id_btn = QPushButton("  识别算法")
        id_btn.setFixedHeight(36)
        id_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:14px;border-radius:4px;padding:0 24px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}")
        id_btn.clicked.connect(self._identify)
        btn_row.addWidget(id_btn)

        clear_btn = QPushButton("清空")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(clear_btn)

        paste_btn = QPushButton("粘贴")
        paste_btn.setFixedHeight(30)
        paste_btn.clicked.connect(self._paste)
        btn_row.addWidget(paste_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── 摘要信息区 ────────────────────────────────────────
        self._meta_box = QGroupBox("密文特征摘要")
        self._meta_box.setStyleSheet(
            "QGroupBox{font-weight:bold;border:1px solid #ccc;"
            "border-radius:4px;margin-top:6px;padding-top:14px}"
            "QGroupBox::title{subcontrol-origin:margin;"
            "left:10px;padding:0 4px}")
        meta_layout = QHBoxLayout(self._meta_box)
        meta_layout.setContentsMargins(10, 4, 10, 4)
        meta_layout.setSpacing(20)

        self._lbl_length = QLabel("长度: -")
        self._lbl_entropy = QLabel("Shannon 熵: -")
        self._lbl_charset = QLabel("字符集: -")
        for lbl in (self._lbl_length, self._lbl_entropy, self._lbl_charset):
            lbl.setFont(QFont("Consolas", 9))
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            meta_layout.addWidget(lbl)
        meta_layout.addStretch()

        self._meta_box.setVisible(False)
        root.addWidget(self._meta_box)

        # ── 结果表格 ──────────────────────────────────────────
        root.addWidget(QLabel("识别结果:"))

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(
            ["可能的算法", "置信度", "说明"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch)
        self._table.setColumnWidth(0, 260)
        self._table.setColumnWidth(1, 80)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setWordWrap(True)
        self._table.verticalHeader().setDefaultSectionSize(32)
        self._table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.setFont(self._mono)
        root.addWidget(self._table, stretch=1)

        # 状态
        self._status = QLabel("就绪 — 粘贴密文/哈希字符串后点击识别")
        self._status.setStyleSheet("color:#666;font-size:11px")
        root.addWidget(self._status)

    def _on_text_changed(self):
        t = self._input.toPlainText()
        self._char_label.setText(f"{len(t)} 字符")

    def _identify(self):
        text = self._input.toPlainText().strip()
        if not text:
            self._status.setText("请先粘贴要识别的字符串")
            return

        result = identify(text)

        # 取出 results 列表和 meta
        results = result.results
        meta = result.meta

        # ── 更新摘要区 ────────────────────────────────────────
        self._lbl_length.setText(f"长度: {meta['length']} 字符")
        self._lbl_entropy.setText(f"Shannon 熵: {meta['entropy']:.3f} bit/char")
        self._lbl_charset.setText(f"字符集: {meta['char_summary']}")
        self._meta_box.setVisible(True)

        # ── 更新结果表格 ──────────────────────────────────────
        self._table.setRowCount(0)

        if not results:
            self._status.setText("未能识别出已知算法")
            return

        self._table.setRowCount(len(results))
        for i, r in enumerate(results):
            # 算法
            algo_item = QTableWidgetItem(r['algorithm'])
            algo_item.setFont(QFont("Consolas", 10, QFont.Bold))
            algo_item.setToolTip(r['algorithm'])
            self._table.setItem(i, 0, algo_item)

            # 置信度
            conf = r['confidence']
            conf_item = QTableWidgetItem(conf)
            conf_item.setTextAlignment(Qt.AlignCenter)
            if conf == '高':
                conf_item.setBackground(QColor('#ccffcc'))
                conf_item.setForeground(QColor('#006600'))
            elif conf == '中':
                conf_item.setBackground(QColor('#ffffcc'))
                conf_item.setForeground(QColor('#666600'))
            else:
                conf_item.setBackground(QColor('#ffe0cc'))
                conf_item.setForeground(QColor('#994400'))
            self._table.setItem(i, 1, conf_item)

            # 说明 — 设置 tooltip 防止文字被截断看不到
            detail_item = QTableWidgetItem(r['detail'])
            detail_item.setToolTip(r['detail'])
            self._table.setItem(i, 2, detail_item)

        self._status.setText(
            f"找到 {len(results)} 个可能的匹配 | "
            f"长度 {meta['length']} | 熵 {meta['entropy']:.2f}")

    def _clear(self):
        self._input.clear()
        self._table.setRowCount(0)
        self._char_label.setText("")
        self._meta_box.setVisible(False)
        self._status.setText("已清空")

    def _paste(self):
        clip = QApplication.clipboard().text()
        if clip:
            self._input.setPlainText(clip)
