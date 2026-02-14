# -*- coding: utf-8 -*-
"""加密/解密 面板"""

import os
from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QComboBox, QLabel,
    QRadioButton, QButtonGroup, QGroupBox,
    QLineEdit, QPushButton, QWidget
)
from .base_panel import BasePanel
from core.crypto import (
    DISPLAY_NAMES, ALGO_KEY_MAP, CIPHER_MODES, CIPHER_KEY_SIZES,
    _8BYTE_BLOCK_ALGOS, do_encrypt, do_decrypt, HAS_CRYPTO, _rand
)


class CryptoPanel(BasePanel):

    def build_controls(self, layout):
        group = QGroupBox("加密/解密 选项")
        g = QVBoxLayout(group)

        # 算法 + 方向
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("算法:"))
        self._algo = QComboBox()
        self._algo.addItems(DISPLAY_NAMES)
        self._algo.setMinimumWidth(160)
        self._algo.currentTextChanged.connect(self._on_algo_changed)
        r1.addWidget(self._algo)
        r1.addSpacing(16)
        r1.addWidget(QLabel("操作:"))
        self._dir = QButtonGroup(self)
        self._btn_enc = QRadioButton("加密")
        self._btn_dec = QRadioButton("解密")
        self._btn_enc.setChecked(True)
        self._dir.addButton(self._btn_enc, 0)
        self._dir.addButton(self._btn_dec, 1)
        r1.addWidget(self._btn_enc)
        r1.addWidget(self._btn_dec)
        r1.addStretch()
        g.addLayout(r1)

        # 密钥
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("密钥:"))
        self._key = QLineEdit()
        self._key.setPlaceholderText("输入密钥")
        r2.addWidget(self._key, stretch=1)
        r2.addWidget(QLabel("格式:"))
        self._key_fmt = QComboBox()
        self._key_fmt.addItems(["文本 (UTF-8)", "Hex"])
        self._key_fmt.setFixedWidth(110)
        r2.addWidget(self._key_fmt)
        self._gen_key = QPushButton("随机密钥")
        self._gen_key.setFixedWidth(80)
        self._gen_key.clicked.connect(self._random_key)
        r2.addWidget(self._gen_key)
        g.addLayout(r2)

        # IV
        self._iv_row = QWidget()
        r3 = QHBoxLayout(self._iv_row)
        r3.setContentsMargins(0, 0, 0, 0)
        r3.addWidget(QLabel("IV:     "))
        self._iv = QLineEdit()
        self._iv.setPlaceholderText("留空则自动生成 (解密时自动提取)")
        r3.addWidget(self._iv, stretch=1)
        self._gen_iv = QPushButton("随机 IV")
        self._gen_iv.setFixedWidth(80)
        self._gen_iv.clicked.connect(self._random_iv)
        r3.addWidget(self._gen_iv)
        g.addWidget(self._iv_row)

        # 模式 + 密文格式
        self._mode_row = QWidget()
        r4 = QHBoxLayout(self._mode_row)
        r4.setContentsMargins(0, 0, 0, 0)
        r4.addWidget(QLabel("模式:"))
        self._mode = QComboBox()
        self._mode.setFixedWidth(100)
        self._mode.currentTextChanged.connect(self._on_mode_changed)
        r4.addWidget(self._mode)
        r4.addSpacing(20)
        r4.addWidget(QLabel("密文格式:"))
        self._out_fmt = QComboBox()
        self._out_fmt.addItems(["Base64", "Hex"])
        self._out_fmt.setFixedWidth(100)
        r4.addWidget(self._out_fmt)
        r4.addStretch()
        g.addWidget(self._mode_row)

        layout.addWidget(group)

        # 初始化
        self._on_algo_changed(self._algo.currentText())

    def _algo_name(self):
        return ALGO_KEY_MAP.get(self._algo.currentText(), self._algo.currentText())

    def _on_algo_changed(self, display_name):
        algo = ALGO_KEY_MAP.get(display_name, display_name)
        modes = CIPHER_MODES.get(algo, [])
        self._mode.blockSignals(True)
        self._mode.clear()
        self._mode.addItems(modes)
        if "CBC" in modes:
            self._mode.setCurrentText("CBC")
        self._mode.blockSignals(False)

        has_modes = bool(modes)
        self._mode_row.setVisible(has_modes)
        self._iv_row.setVisible(has_modes and self._mode.currentText() != 'ECB')

    def _on_mode_changed(self, mode):
        self._iv_row.setVisible(mode != 'ECB')

    def _random_key(self):
        algo = self._algo_name()
        size = CIPHER_KEY_SIZES.get(algo, 16)
        self._key_fmt.setCurrentIndex(1)
        self._key.setText(_rand(size).hex())

    def _random_iv(self):
        algo = self._algo_name()
        mode = self._mode.currentText()
        size = 12 if mode == 'GCM' else (8 if algo in _8BYTE_BLOCK_ALGOS else 16)
        self._iv.setText(_rand(size).hex())

    def process(self, text):
        algo = self._algo_name()
        key = self._key.text()
        iv = self._iv.text()
        mode = self._mode.currentText() if self._mode.isVisible() else ''
        kf = 'hex' if self._key_fmt.currentIndex() == 1 else 'text'
        of = 'hex' if self._out_fmt.currentIndex() == 1 else 'base64'

        if self._btn_enc.isChecked():
            return do_encrypt(algo, text, key, iv, mode, kf, of)
        return do_decrypt(algo, text, key, iv, mode, kf, of)
