#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QtCoder — 开发工具箱  入口"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont, QPalette, QColor
from PyQt5.QtCore import Qt


def main():
    # High-DPI 支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # ── 全局字体: 中英文兼顾，11pt 舒适阅读 ──────────────
    font = QFont("Microsoft YaHei UI", 11)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)

    # ── Fusion 调色板微调 ─────────────────────────────────
    palette = QPalette()
    palette.setColor(QPalette.Window,          QColor("#f0f2f5"))
    palette.setColor(QPalette.WindowText,      QColor("#1e2433"))
    palette.setColor(QPalette.Base,            QColor("#ffffff"))
    palette.setColor(QPalette.AlternateBase,   QColor("#f5f6f8"))
    palette.setColor(QPalette.Text,            QColor("#1e2433"))
    palette.setColor(QPalette.Button,          QColor("#e8eaed"))
    palette.setColor(QPalette.ButtonText,      QColor("#1e2433"))
    palette.setColor(QPalette.Highlight,       QColor("#0078d4"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase,     QColor("#1e2433"))
    palette.setColor(QPalette.ToolTipText,     QColor("#ffffff"))
    app.setPalette(palette)

    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
