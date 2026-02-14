# -*- coding: utf-8 -*-
"""中文简繁转换面板"""

from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QComboBox, QLabel, QGroupBox
)
from .base_panel import BasePanel
from core.zh_convert import convert_zh, LOCALE_MAP, HAS_ZHCONV


class ZhconvPanel(BasePanel):

    def build_controls(self, layout):
        group = QGroupBox("简繁转换选项")
        g = QVBoxLayout(group)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("转换方向:"))
        self._direction = QComboBox()
        self._direction.addItems(list(LOCALE_MAP.keys()))
        self._direction.setMinimumWidth(200)
        r1.addWidget(self._direction)
        r1.addStretch()
        g.addLayout(r1)

        if not HAS_ZHCONV:
            warn = QLabel("⚠ 未安装 zhconv，请运行: pip install zhconv")
            warn.setStyleSheet("color:red;font-size:11px")
            g.addWidget(warn)

        layout.addWidget(group)

    def process(self, text):
        direction = self._direction.currentText()
        return convert_zh(text, direction)
