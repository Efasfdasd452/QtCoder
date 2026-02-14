# -*- coding: utf-8 -*-
"""SSH 密钥生成面板"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTextEdit, QGroupBox, QLineEdit, QApplication,
    QFileDialog, QMessageBox, QSplitter
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from core.ssh_keygen import generate_keypair, KEY_TYPES, HAS_KEYGEN


class SshPanel(QWidget):
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
        group = QGroupBox("SSH 密钥生成选项")
        g = QVBoxLayout(group)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("密钥类型:"))
        self._key_type = QComboBox()
        self._key_type.addItems(list(KEY_TYPES.keys()))
        self._key_type.setMinimumWidth(160)
        r1.addWidget(self._key_type)
        r1.addStretch()
        g.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("密码短语:"))
        self._passphrase = QLineEdit()
        self._passphrase.setPlaceholderText("可选，留空则不加密私钥")
        self._passphrase.setEchoMode(QLineEdit.Password)
        r2.addWidget(self._passphrase, stretch=1)
        r2.addSpacing(12)
        r2.addWidget(QLabel("注释:"))
        self._comment = QLineEdit()
        self._comment.setPlaceholderText("如 user@host")
        r2.addWidget(self._comment, stretch=1)
        g.addLayout(r2)

        if not HAS_KEYGEN:
            warn = QLabel("⚠ 未安装 pycryptodome，请运行: pip install pycryptodome")
            warn.setStyleSheet("color:red;font-size:11px")
            g.addWidget(warn)

        root.addWidget(group)

        # ── 按钮行 ───────────────────────────────────────────
        btn_row = QHBoxLayout()
        gen_btn = QPushButton("▶  生成密钥对")
        gen_btn.setFixedHeight(34)
        gen_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:13px;border-radius:4px;padding:0 22px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}")
        gen_btn.clicked.connect(self._generate)
        btn_row.addWidget(gen_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── 密钥展示区（上下分栏） ──────────────────────────
        splitter = QSplitter(Qt.Vertical)

        # 私钥
        priv_w = QWidget()
        priv_l = QVBoxLayout(priv_w)
        priv_l.setContentsMargins(0, 0, 0, 0)
        priv_hdr = QHBoxLayout()
        priv_hdr.addWidget(QLabel("私钥 (Private Key):"))
        priv_hdr.addStretch()
        priv_copy = QPushButton("复制")
        priv_copy.setFixedWidth(70)
        priv_copy.clicked.connect(lambda: self._copy(self._priv_area))
        priv_hdr.addWidget(priv_copy)
        priv_export = QPushButton("导出私钥")
        priv_export.setFixedWidth(90)
        priv_export.clicked.connect(self._export_private)
        priv_hdr.addWidget(priv_export)
        priv_l.addLayout(priv_hdr)
        self._priv_area = QTextEdit()
        self._priv_area.setFont(self._mono)
        self._priv_area.setReadOnly(True)
        self._priv_area.setPlaceholderText("私钥将显示在此…")
        priv_l.addWidget(self._priv_area)
        splitter.addWidget(priv_w)

        # 公钥
        pub_w = QWidget()
        pub_l = QVBoxLayout(pub_w)
        pub_l.setContentsMargins(0, 0, 0, 0)
        pub_hdr = QHBoxLayout()
        pub_hdr.addWidget(QLabel("公钥 (Public Key):"))
        pub_hdr.addStretch()
        pub_copy = QPushButton("复制")
        pub_copy.setFixedWidth(70)
        pub_copy.clicked.connect(lambda: self._copy(self._pub_area))
        pub_hdr.addWidget(pub_copy)
        pub_export = QPushButton("导出公钥")
        pub_export.setFixedWidth(90)
        pub_export.clicked.connect(self._export_public)
        pub_hdr.addWidget(pub_export)
        pub_l.addLayout(pub_hdr)
        self._pub_area = QTextEdit()
        self._pub_area.setFont(self._mono)
        self._pub_area.setReadOnly(True)
        self._pub_area.setPlaceholderText("公钥将显示在此…")
        pub_l.addWidget(self._pub_area)
        splitter.addWidget(pub_w)

        root.addWidget(splitter, stretch=1)

        # 状态
        self._status = QLabel("就绪")
        self._status.setStyleSheet("color:#666;font-size:11px")
        root.addWidget(self._status)

    # ── 事件处理 ─────────────────────────────────────────────
    def _generate(self):
        if not HAS_KEYGEN:
            QMessageBox.warning(
                self, "依赖缺失",
                "需要安装 pycryptodome:\npip install pycryptodome")
            return

        key_type = self._key_type.currentText()
        passphrase = self._passphrase.text() or None
        comment = self._comment.text()

        try:
            private_key, public_key = generate_keypair(
                key_type, passphrase, comment)
            self._priv_area.setPlainText(private_key)
            self._pub_area.setPlainText(public_key)
            self._status.setText(f"已生成 {key_type} 密钥对")
        except Exception as e:
            QMessageBox.warning(self, "生成失败", str(e))
            self._status.setText(f"出错: {type(e).__name__}")

    def _copy(self, area):
        t = area.toPlainText()
        if t:
            QApplication.clipboard().setText(t)
            self._status.setText("已复制到剪贴板")

    def _export_private(self):
        kt = self._key_type.currentText().lower().replace('-', '_')
        default = f"id_{kt}"
        self._export_key(self._priv_area, default, "私钥")

    def _export_public(self):
        kt = self._key_type.currentText().lower().replace('-', '_')
        default = f"id_{kt}.pub"
        self._export_key(self._pub_area, default, "公钥")

    def _export_key(self, area, default_name, label):
        t = area.toPlainText()
        if not t:
            QMessageBox.information(
                self, "提示", f"{label}为空，请先生成密钥")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, f"导出{label}", default_name, "所有文件 (*)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(t)
                if not t.endswith('\n'):
                    f.write('\n')
            self._status.setText(f"已导出{label}: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
