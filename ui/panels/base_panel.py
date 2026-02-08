# -*- coding: utf-8 -*-
"""面板基类 — 提供统一的 输入区 / 输出区 / 按钮 骨架"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QFileDialog, QMessageBox,
    QApplication, QShortcut
)
from PyQt5.QtGui import QFont, QKeySequence


class BasePanel(QWidget):
    """所有功能面板的基类。

    子类只需实现:
        build_controls(layout)  — 在输入区与输出区之间添加自己的控件
        process(input_text)     — 返回处理后的字符串
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mono = QFont("Consolas", 10)
        self._mono.setStyleHint(QFont.Monospace)
        self._build_ui()

    # ── 骨架搭建 ────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(6)

        # 输入区
        hdr_in = QHBoxLayout()
        hdr_in.addWidget(QLabel("输入:"))
        hdr_in.addStretch()
        self._char_label = QLabel("")
        hdr_in.addWidget(self._char_label)
        self._import_btn = QPushButton("导入文件")
        self._import_btn.setFixedWidth(90)
        self._import_btn.clicked.connect(self._import_file)
        hdr_in.addWidget(self._import_btn)
        root.addLayout(hdr_in)

        self.input_area = QTextEdit()
        self.input_area.setFont(self._mono)
        self.input_area.setPlaceholderText("在此输入或粘贴文本…")
        self.input_area.setMinimumHeight(100)
        self.input_area.textChanged.connect(self._update_char_count)
        root.addWidget(self.input_area, stretch=3)

        # 子类控件区
        self._ctrl_layout = QVBoxLayout()
        self.build_controls(self._ctrl_layout)
        root.addLayout(self._ctrl_layout)

        # 操作按钮行
        btn_row = QHBoxLayout()
        self._exec_btn = QPushButton("▶  执行")
        self._exec_btn.setFixedHeight(34)
        self._exec_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:13px;border-radius:4px;padding:0 22px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}")
        self._exec_btn.clicked.connect(self._on_execute)
        btn_row.addWidget(self._exec_btn)
        self._swap_btn = QPushButton("⇅ 交换")
        self._swap_btn.setFixedHeight(30)
        self._swap_btn.clicked.connect(self._swap)
        btn_row.addWidget(self._swap_btn)
        self._clear_btn = QPushButton("清空")
        self._clear_btn.setFixedHeight(30)
        self._clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # 输出区
        hdr_out = QHBoxLayout()
        hdr_out.addWidget(QLabel("输出:"))
        hdr_out.addStretch()
        self._out_label = QLabel("")
        hdr_out.addWidget(self._out_label)
        self._copy_btn = QPushButton("复制")
        self._copy_btn.setFixedWidth(70)
        self._copy_btn.clicked.connect(self._copy)
        hdr_out.addWidget(self._copy_btn)
        self._export_btn = QPushButton("导出文件")
        self._export_btn.setFixedWidth(90)
        self._export_btn.clicked.connect(self._export_file)
        hdr_out.addWidget(self._export_btn)
        root.addLayout(hdr_out)

        self.output_area = QTextEdit()
        self.output_area.setFont(self._mono)
        self.output_area.setReadOnly(True)
        self.output_area.setPlaceholderText("结果将显示在此…")
        self.output_area.setMinimumHeight(100)
        root.addWidget(self.output_area, stretch=3)

        # 状态
        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet("color:#666;font-size:11px")
        root.addWidget(self._status_label)

        # 快捷键
        QShortcut(QKeySequence("Ctrl+Return"), self, self._on_execute)

    # ── 子类接口 ────────────────────────────────────────────
    def build_controls(self, layout):
        """子类重写：向 layout 添加自己的控件"""

    def process(self, input_text: str) -> str:
        """子类重写：处理输入文本并返回结果"""
        raise NotImplementedError

    # ── 内部逻辑 ────────────────────────────────────────────
    def _on_execute(self):
        text = self.input_area.toPlainText()
        if not text:
            self._status("请先输入文本")
            return
        try:
            result = self.process(text)
            self.output_area.setPlainText(result)
            self._out_label.setText(f"{len(result)} 字符")
            self._status("处理完成")
        except Exception as e:
            self.output_area.setPlainText(f"错误 [{type(e).__name__}]: {e}")
            self._out_label.setText("")
            self._status(f"出错: {type(e).__name__}")

    def _status(self, msg: str):
        self._status_label.setText(msg)

    def _update_char_count(self):
        t = self.input_area.toPlainText()
        self._char_label.setText(f"{len(t)} 字符 / {len(t.encode('utf-8'))} 字节")

    def _swap(self):
        o, i = self.output_area.toPlainText(), self.input_area.toPlainText()
        self.input_area.setPlainText(o)
        self.output_area.setPlainText(i)

    def _clear(self):
        self.input_area.clear()
        self.output_area.clear()
        self._out_label.setText("")
        self._char_label.setText("")
        self._status("已清空")

    def _copy(self):
        t = self.output_area.toPlainText()
        if t:
            QApplication.clipboard().setText(t)
            self._status("已复制到剪贴板")

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入文件", "",
            "文本文件 (*.txt *.json *.xml *.csv *.log *.sh);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.input_area.setPlainText(f.read())
        except UnicodeDecodeError:
            with open(path, 'r', encoding='gbk', errors='replace') as f:
                self.input_area.setPlainText(f.read())
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))
            return
        self._status(f"已导入: {os.path.basename(path)}")

    def _export_file(self):
        t = self.output_area.toPlainText()
        if not t:
            QMessageBox.information(self, "提示", "输出为空")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出文件", "output.txt",
            "文本文件 (*.txt);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(t)
            self._status(f"已导出: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
