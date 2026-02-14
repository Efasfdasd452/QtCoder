# -*- coding: utf-8 -*-
"""UUID 生成面板"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QSpinBox, QCheckBox, QPushButton, QTextEdit, QGroupBox,
    QLineEdit, QApplication
)
from PyQt5.QtGui import QFont

from core.uuid_gen import generate_uuid, NAMESPACE_MAP


class UuidPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mono = QFont("Consolas", 10)
        self._mono.setStyleHint(QFont.Monospace)
        self._build_ui()

    # ── UI 搭建 ──────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(6)

        # ── 选项区 ───────────────────────────────────────────
        group = QGroupBox("UUID 生成选项")
        g = QVBoxLayout(group)

        # 版本
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("版本:"))
        self._version = QComboBox()
        self._version.addItems([
            'UUID v1 (时间戳)',
            'UUID v3 (MD5)',
            'UUID v4 (随机)',
            'UUID v5 (SHA-1)',
        ])
        self._version.setCurrentIndex(2)
        self._version.currentIndexChanged.connect(self._on_version_changed)
        r1.addWidget(self._version)
        r1.addStretch()
        g.addLayout(r1)

        # 命名空间 + 名称 (v3/v5)
        self._ns_row = QWidget()
        r2 = QHBoxLayout(self._ns_row)
        r2.setContentsMargins(0, 0, 0, 0)
        r2.addWidget(QLabel("命名空间:"))
        self._namespace = QComboBox()
        self._namespace.addItems(list(NAMESPACE_MAP.keys()))
        r2.addWidget(self._namespace)
        r2.addSpacing(12)
        r2.addWidget(QLabel("名称:"))
        self._name = QLineEdit()
        self._name.setPlaceholderText("输入名称（如 example.com）")
        r2.addWidget(self._name, stretch=1)
        g.addWidget(self._ns_row)
        self._ns_row.setVisible(False)

        # 数量 + 格式
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("生成数量:"))
        self._count = QSpinBox()
        self._count.setRange(1, 1000)
        self._count.setValue(1)
        r3.addWidget(self._count)
        r3.addSpacing(12)
        self._uppercase = QCheckBox("大写")
        r3.addWidget(self._uppercase)
        self._no_dash = QCheckBox("无连字符")
        r3.addWidget(self._no_dash)
        r3.addStretch()
        g.addLayout(r3)

        root.addWidget(group)

        # ── 按钮行 ───────────────────────────────────────────
        btn_row = QHBoxLayout()
        gen_btn = QPushButton("▶  生成 UUID")
        gen_btn.setFixedHeight(34)
        gen_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:13px;border-radius:4px;padding:0 22px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}")
        gen_btn.clicked.connect(self._generate)
        btn_row.addWidget(gen_btn)

        clear_btn = QPushButton("清空")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(lambda: (self._output.clear(),
                                           self._out_label.setText("")))
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── 输出区 ───────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("输出:"))
        hdr.addStretch()
        self._out_label = QLabel("")
        hdr.addWidget(self._out_label)
        copy_btn = QPushButton("复制")
        copy_btn.setFixedWidth(70)
        copy_btn.clicked.connect(self._copy)
        hdr.addWidget(copy_btn)
        root.addLayout(hdr)

        self._output = QTextEdit()
        self._output.setFont(self._mono)
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("生成的 UUID 将显示在此…")
        root.addWidget(self._output, stretch=1)

        # 状态
        self._status = QLabel("就绪")
        self._status.setStyleSheet("color:#666;font-size:11px")
        root.addWidget(self._status)

    # ── 事件处理 ─────────────────────────────────────────────
    def _on_version_changed(self, idx):
        self._ns_row.setVisible(idx in (1, 3))  # v3 / v5

    def _generate(self):
        version_map = {0: 1, 1: 3, 2: 4, 3: 5}
        version = version_map[self._version.currentIndex()]
        namespace = self._namespace.currentText()
        name = self._name.text()
        uppercase = self._uppercase.isChecked()
        count = self._count.value()

        try:
            result = generate_uuid(version, namespace, name, uppercase, count)
            if self._no_dash.isChecked():
                result = result.replace('-', '')
            self._output.setPlainText(result)
            self._out_label.setText(f"已生成 {count} 个 UUID")
            self._status.setText("生成完成")
        except Exception as e:
            self._output.setPlainText(f"错误: {e}")
            self._status.setText(f"出错: {type(e).__name__}")

    def _copy(self):
        t = self._output.toPlainText()
        if t:
            QApplication.clipboard().setText(t)
            self._status.setText("已复制到剪贴板")
