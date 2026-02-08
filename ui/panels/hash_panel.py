# -*- coding: utf-8 -*-
"""哈希/摘要 面板"""

from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QComboBox, QLabel,
    QGroupBox, QLineEdit, QWidget
)
from .base_panel import BasePanel
from core.hashing import HASH_METHODS, do_hash


class HashPanel(BasePanel):

    def build_controls(self, layout):
        group = QGroupBox("哈希/摘要 选项")
        g = QVBoxLayout(group)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("算法:"))
        self._method = QComboBox()
        self._method.addItems(HASH_METHODS)
        self._method.setMinimumWidth(160)
        self._method.currentTextChanged.connect(self._on_method_changed)
        r1.addWidget(self._method)
        r1.addStretch()
        g.addLayout(r1)

        # HMAC 密钥行
        self._key_row = QWidget()
        kr = QHBoxLayout(self._key_row)
        kr.setContentsMargins(0, 0, 0, 0)
        kr.addWidget(QLabel("HMAC 密钥:"))
        self._key = QLineEdit()
        self._key.setPlaceholderText("输入 HMAC 密钥")
        kr.addWidget(self._key, stretch=1)
        g.addWidget(self._key_row)
        self._key_row.setVisible(False)

        layout.addWidget(group)

    def _on_method_changed(self, method):
        self._key_row.setVisible(method.startswith("HMAC"))

    def process(self, text):
        method = self._method.currentText()
        key = self._key.text() if method.startswith("HMAC") else ''
        return do_hash(method, text, key)
