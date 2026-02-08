# -*- coding: utf-8 -*-
"""编码/解码 面板"""

from PyQt5.QtWidgets import (
    QHBoxLayout, QComboBox, QLabel,
    QRadioButton, QButtonGroup, QGroupBox, QVBoxLayout
)
from .base_panel import BasePanel
from core.encoding import ENCODING_METHODS, process_encoding


class CodecPanel(BasePanel):

    def build_controls(self, layout):
        group = QGroupBox("编码/解码 选项")
        g_layout = QVBoxLayout(group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("方法:"))
        self._method = QComboBox()
        self._method.addItems(list(ENCODING_METHODS.keys()))
        self._method.setMinimumWidth(160)
        self._method.currentTextChanged.connect(self._on_method_changed)
        row1.addWidget(self._method)
        row1.addStretch()
        g_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("操作:"))
        self._dir_group = QButtonGroup(self)
        self._btn_enc = QRadioButton("编码")
        self._btn_dec = QRadioButton("解码")
        self._btn_enc.setChecked(True)
        self._dir_group.addButton(self._btn_enc, 0)
        self._dir_group.addButton(self._btn_dec, 1)
        row2.addWidget(self._btn_enc)
        row2.addWidget(self._btn_dec)
        row2.addStretch()
        g_layout.addLayout(row2)

        layout.addWidget(group)

    def _on_method_changed(self, method):
        if method == "JWT 解析":
            self._btn_dec.setChecked(True)
            self._btn_enc.setEnabled(False)
        else:
            self._btn_enc.setEnabled(True)

    def process(self, text):
        method = self._method.currentText()
        encode = self._btn_enc.isChecked()
        return process_encoding(method, text, encode)
