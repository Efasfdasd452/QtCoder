# -*- coding: utf-8 -*-
"""JSON 格式化面板"""

from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel,
    QRadioButton, QButtonGroup, QGroupBox,
    QCheckBox, QSpinBox
)
from .base_panel import BasePanel
from core.json_fmt import format_json, minify_json, validate_json


class JsonPanel(BasePanel):

    def _build_ui(self):
        """覆写以定制 placeholder"""
        super()._build_ui()
        self.input_area.setPlaceholderText(
            '粘贴 JSON 文本，例如:\n'
            '{"name": "test", "value": 123, "list": [1, 2, 3]}'
        )

    def build_controls(self, layout):
        group = QGroupBox("JSON 选项")
        g = QVBoxLayout(group)

        # 操作模式
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("操作:"))
        self._op_group = QButtonGroup(self)
        self._btn_format = QRadioButton("格式化")
        self._btn_minify = QRadioButton("压缩")
        self._btn_validate = QRadioButton("验证")
        self._btn_format.setChecked(True)
        self._op_group.addButton(self._btn_format, 0)
        self._op_group.addButton(self._btn_minify, 1)
        self._op_group.addButton(self._btn_validate, 2)
        r1.addWidget(self._btn_format)
        r1.addWidget(self._btn_minify)
        r1.addWidget(self._btn_validate)
        r1.addStretch()
        g.addLayout(r1)

        # 格式化选项
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("缩进:"))
        self._indent = QSpinBox()
        self._indent.setRange(1, 8)
        self._indent.setValue(4)
        self._indent.setFixedWidth(60)
        r2.addWidget(self._indent)
        r2.addSpacing(16)
        self._sort_keys = QCheckBox("排序键名")
        r2.addWidget(self._sort_keys)
        self._ensure_ascii = QCheckBox("ASCII 转义")
        r2.addWidget(self._ensure_ascii)
        r2.addStretch()
        g.addLayout(r2)

        layout.addWidget(group)

    def process(self, text):
        if self._btn_format.isChecked():
            return format_json(
                text,
                indent=self._indent.value(),
                sort_keys=self._sort_keys.isChecked(),
                ensure_ascii=self._ensure_ascii.isChecked(),
            )
        elif self._btn_minify.isChecked():
            return minify_json(text)
        else:
            ok, msg = validate_json(text)
            return msg
