# -*- coding: utf-8 -*-
"""JSON 转 Python 类定义面板"""

from PyQt5.QtWidgets import QLineEdit, QLabel, QHBoxLayout
from .base_panel import BasePanel
from core.json_to_python import json_to_python


class JsonPythonPanel(BasePanel):
    """输入 JSON，输出 Python dataclass 定义（含 List、嵌套类）。"""

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
        return json_to_python(text, root_class_name=name)
