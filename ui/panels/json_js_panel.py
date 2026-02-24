# -*- coding: utf-8 -*-
"""JSON 转 JavaScript/TypeScript 类型定义面板"""

from PyQt5.QtWidgets import QLineEdit, QLabel, QHBoxLayout
from .base_panel import BasePanel
from core.json_to_js import json_to_js


class JsonJsPanel(BasePanel):
    """输入 JSON，输出 TypeScript interface 定义（可用于 JS JSDoc）。"""

    def _build_ui(self):
        super()._build_ui()
        self.input_area.setPlaceholderText(
            "粘贴 JSON 对象，例如:\n"
            '{"site": "json", "name": "tomi", "age": 28, "list": [1,2,3], '
            '"dict": {"a1": "123", "b2": 789}}'
        )

    def build_controls(self, layout):
        row = QHBoxLayout()
        row.addWidget(QLabel("根类名:"))
        self._root_name = QLineEdit()
        self._root_name.setPlaceholderText("MyClass")
        self._root_name.setMaximumWidth(160)
        self._root_name.setText("MyClass")
        row.addWidget(self._root_name)
        row.addStretch()
        layout.addLayout(row)

    def process(self, text):
        name = (self._root_name.text() or "MyClass").strip() or "MyClass"
        return json_to_js(text, root_class_name=name)
