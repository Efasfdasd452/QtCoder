# -*- coding: utf-8 -*-
"""下划线命名与驼峰命名互转面板"""

from PyQt5.QtWidgets import QVBoxLayout, QGroupBox, QRadioButton, QButtonGroup
from .base_panel import BasePanel
from core.line_big_case import snake_to_camel, camel_to_snake


class LineBigPanel(BasePanel):
    """下划线命名（snake_case）与驼峰命名（camelCase）互转，自动识别文本中的标识符。"""

    def _build_ui(self):
        super()._build_ui()
        self.input_area.setPlaceholderText(
            "粘贴包含 下划线命名 或 驼峰命名 的文本，例如:\n"
            "private String out_trade_no;\n"
            "private String auth_code;\n"
            "private double total_amount;"
        )

    def build_controls(self, layout):
        group = QGroupBox("转换方向")
        g = QVBoxLayout(group)
        self._mode_group = QButtonGroup(self)
        self._btn_snake2camel = QRadioButton("下划线 → 驼峰（out_trade_no → outTradeNo）")
        self._btn_camel2snake = QRadioButton("驼峰 → 下划线（outTradeNo → out_trade_no）")
        self._btn_snake2camel.setChecked(True)
        self._mode_group.addButton(self._btn_snake2camel)
        self._mode_group.addButton(self._btn_camel2snake)
        g.addWidget(self._btn_snake2camel)
        g.addWidget(self._btn_camel2snake)
        layout.addWidget(group)

    def process(self, text):
        if not text.strip():
            return ""
        if self._btn_snake2camel.isChecked():
            return snake_to_camel(text)
        return camel_to_snake(text)
