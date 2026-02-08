# -*- coding: utf-8 -*-
"""主窗口 — 通过 QTabWidget 组合所有功能面板"""

from PyQt5.QtWidgets import QMainWindow, QTabWidget

from .panels.codec_panel import CodecPanel
from .panels.crypto_panel import CryptoPanel
from .panels.hash_panel import HashPanel
from .panels.curl_panel import CurlPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("编码解码 & 加密解密工具")
        self.setMinimumSize(920, 740)
        self.resize(980, 800)

        tabs = QTabWidget()
        tabs.addTab(CodecPanel(),  "编码/解码")
        tabs.addTab(CryptoPanel(), "加密/解密")
        tabs.addTab(HashPanel(),   "哈希/摘要")
        tabs.addTab(CurlPanel(),   "cURL 转换")
        self.setCentralWidget(tabs)
