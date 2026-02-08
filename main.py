#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编码解码 & 加密解密工具 — 入口"""

import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
