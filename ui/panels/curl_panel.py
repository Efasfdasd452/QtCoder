# -*- coding: utf-8 -*-
"""cURL 转换 面板"""

from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QComboBox, QLabel, QGroupBox
)
from .base_panel import BasePanel
from core.curl_converter import parse_curl, generate_code, GENERATORS


class CurlPanel(BasePanel):
    """将 curl 命令转换为多种编程语言的等效代码"""

    def _build_ui(self):
        """覆写以定制 placeholder"""
        super()._build_ui()
        self.input_area.setPlaceholderText(
            '粘贴 curl 命令，例如:\n'
            'curl -X POST https://api.example.com/data \\\n'
            '  -H "Content-Type: application/json" \\\n'
            '  -d \'{"key": "value"}\''
        )
        self._swap_btn.setVisible(False)  # curl 转换无需交换

    def build_controls(self, layout):
        group = QGroupBox("转换选项")
        g = QVBoxLayout(group)

        row = QHBoxLayout()
        row.addWidget(QLabel("目标语言:"))
        self._lang = QComboBox()
        self._lang.addItems(list(GENERATORS.keys()))
        self._lang.setMinimumWidth(220)
        row.addWidget(self._lang)
        row.addStretch()
        g.addLayout(row)

        layout.addWidget(group)

    def process(self, text):
        req = parse_curl(text)
        lang = self._lang.currentText()
        return generate_code(lang, req)
