# -*- coding: utf-8 -*-
"""Base64 → 图片 面板

功能:
  - 粘贴/导入一条或多条 Base64 字符串（支持 data URI 与纯 Base64）
  - 批量解码并保存为图片文件
  - 结果表格显示每条的格式、大小与状态
"""

import os
import subprocess

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QGroupBox, QRadioButton, QButtonGroup,
    QLineEdit, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QProgressBar, QMessageBox,
    QApplication, QSizePolicy, QSplitter,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.b64_image import parse_entries, convert_and_save


# ── 样式常量 ─────────────────────────────────────────────────────────
_BTN_PRIMARY = (
    "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
    "font-size:13px;border-radius:4px;padding:0 20px}"
    "QPushButton:hover{background:#106ebe}"
    "QPushButton:pressed{background:#005a9e}")

_BTN_PLAIN = (
    "QPushButton{border:1px solid #dfe2e8;border-radius:4px;"
    "padding:0 14px;background:#fff;color:#1e2433;font-size:12px}"
    "QPushButton:hover{background:#f0f2f5}")

_PROGRESS_STYLE = (
    "QProgressBar{border:1px solid #dfe2e8;background:#e8eaed;"
    "border-radius:3px;text-align:center;font-size:11px;}"
    "QProgressBar::chunk{background:#0078d4;border-radius:3px;}")

_MONO = QFont("Consolas", 9)
_MONO.setStyleHint(QFont.Monospace)


def _fmt_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


# ── 后台工作线程 ─────────────────────────────────────────────────────
class _Worker(QThread):
    row_done  = pyqtSignal(dict)          # 每条处理完成
    all_done  = pyqtSignal(int, int)      # (成功数, 总数)

    def __init__(self, entries, output_dir, prefix):
        super().__init__()
        self._entries    = entries
        self._output_dir = output_dir
        self._prefix     = prefix

    def run(self):
        results = convert_and_save(self._entries, self._output_dir, self._prefix)
        ok = 0
        for r in results:
            self.row_done.emit(r)
            if not r['error']:
                ok += 1
        self.all_done.emit(ok, len(results))


# ── 面板 ─────────────────────────────────────────────────────────────
class B64ImagePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._output_dir = ''
        self._worker     = None
        self._build_ui()

    # ─────────────────────────────────────────────────────────────────
    #  构建 UI
    # ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Vertical)

        # ── 输入区 ────────────────────────────────────────────────────
        in_group = QGroupBox("Base64 输入")
        in_lay   = QVBoxLayout(in_group)
        in_lay.setContentsMargins(6, 6, 6, 6)
        in_lay.setSpacing(6)

        hint = QLabel(
            "支持 data URI（data:image/png;base64,…）或纯 Base64，"
            "每行一条；可粘贴多行，也可导入含多条的文本文件。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6b7a8d;font-size:11px;")
        in_lay.addWidget(hint)

        self._input = QPlainTextEdit()
        self._input.setFont(_MONO)
        self._input.setPlaceholderText(
            "在此粘贴 Base64 字符串，每行一条…\n\n"
            "示例（data URI）:\n"
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA…\n\n"
            "示例（纯 Base64）:\n"
            "iVBORw0KGgoAAAANSUhEUgAA…")
        self._input.setMinimumHeight(130)
        in_lay.addWidget(self._input)

        # 分隔方式 + 导入按钮
        ctrl_row = QHBoxLayout()
        split_lbl = QLabel("分隔方式:")
        split_lbl.setStyleSheet("font-size:12px;")
        ctrl_row.addWidget(split_lbl)

        self._split_group = QButtonGroup(self)
        self._rb_line  = QRadioButton("每行一条")
        self._rb_block = QRadioButton("空行分隔（多行 Base64）")
        self._rb_line.setChecked(True)
        self._split_group.addButton(self._rb_line,  0)
        self._split_group.addButton(self._rb_block, 1)
        ctrl_row.addWidget(self._rb_line)
        ctrl_row.addWidget(self._rb_block)
        ctrl_row.addStretch()

        self._import_btn = QPushButton("导入文本文件")
        self._import_btn.setFixedHeight(28)
        self._import_btn.setStyleSheet(_BTN_PLAIN)
        self._import_btn.clicked.connect(self._on_import)
        ctrl_row.addWidget(self._import_btn)

        self._clear_input_btn = QPushButton("清空")
        self._clear_input_btn.setFixedHeight(28)
        self._clear_input_btn.setStyleSheet(_BTN_PLAIN)
        self._clear_input_btn.clicked.connect(self._on_clear)
        ctrl_row.addWidget(self._clear_input_btn)
        in_lay.addLayout(ctrl_row)

        splitter.addWidget(in_group)

        # ── 设置 + 操作区 ─────────────────────────────────────────────
        cfg_group = QGroupBox("输出设置")
        cfg_lay   = QVBoxLayout(cfg_group)
        cfg_lay.setContentsMargins(6, 6, 6, 6)
        cfg_lay.setSpacing(6)

        # 输出目录
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("输出文件夹:"))
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("（点击右侧按钮选择）")
        self._dir_edit.setReadOnly(True)
        dir_row.addWidget(self._dir_edit, stretch=1)
        self._pick_dir_btn = QPushButton("选择…")
        self._pick_dir_btn.setFixedHeight(26)
        self._pick_dir_btn.setStyleSheet(_BTN_PLAIN)
        self._pick_dir_btn.clicked.connect(self._on_pick_dir)
        dir_row.addWidget(self._pick_dir_btn)
        cfg_lay.addLayout(dir_row)

        # 文件名前缀
        pfx_row = QHBoxLayout()
        pfx_row.addWidget(QLabel("文件名前缀:"))
        self._prefix_edit = QLineEdit("image")
        self._prefix_edit.setFixedWidth(120)
        self._prefix_edit.setPlaceholderText("image")
        pfx_row.addWidget(self._prefix_edit)
        pfx_row.addWidget(QLabel("  → 生成  image_001.png  image_002.jpg  …"))
        pfx_row.addStretch()
        cfg_lay.addLayout(pfx_row)

        # 操作按钮
        act_row = QHBoxLayout()
        self._start_btn = QPushButton("▶  开始转换")
        self._start_btn.setFixedHeight(34)
        self._start_btn.setStyleSheet(_BTN_PRIMARY)
        self._start_btn.clicked.connect(self._on_start)
        act_row.addWidget(self._start_btn)

        self._open_dir_btn = QPushButton("打开输出文件夹")
        self._open_dir_btn.setFixedHeight(30)
        self._open_dir_btn.setStyleSheet(_BTN_PLAIN)
        self._open_dir_btn.clicked.connect(self._on_open_dir)
        self._open_dir_btn.setEnabled(False)
        act_row.addWidget(self._open_dir_btn)
        act_row.addStretch()

        self._status_lbl = QLabel("就绪")
        self._status_lbl.setStyleSheet("color:#666;font-size:11px;")
        act_row.addWidget(self._status_lbl)
        cfg_lay.addLayout(act_row)

        # 进度条
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(18)
        self._progress.setStyleSheet(_PROGRESS_STYLE)
        self._progress.setVisible(False)
        cfg_lay.addWidget(self._progress)

        splitter.addWidget(cfg_group)

        # ── 结果表格 ─────────────────────────────────────────────────
        out_group = QGroupBox("转换结果")
        out_lay   = QVBoxLayout(out_group)
        out_lay.setContentsMargins(6, 6, 6, 6)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["#", "格式", "大小", "状态 / 文件名"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.setColumnWidth(0, 45)
        self._table.setColumnWidth(1, 60)
        self._table.setColumnWidth(2, 80)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        out_lay.addWidget(self._table)

        splitter.addWidget(out_group)
        splitter.setSizes([260, 180, 220])
        root.addWidget(splitter, stretch=1)

    # ─────────────────────────────────────────────────────────────────
    #  事件处理
    # ─────────────────────────────────────────────────────────────────
    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入文本文件", "",
            "文本文件 (*.txt *.b64 *.base64);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self._input.setPlainText(f.read())
        except UnicodeDecodeError:
            with open(path, 'r', encoding='gbk', errors='replace') as f:
                self._input.setPlainText(f.read())
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))
            return
        self._set_status(f"已导入: {os.path.basename(path)}")

    def _on_clear(self):
        self._input.clear()
        self._table.setRowCount(0)
        self._progress.setVisible(False)
        self._open_dir_btn.setEnabled(False)
        self._set_status("就绪")

    def _on_pick_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if folder:
            self._output_dir = folder
            self._dir_edit.setText(folder)

    def _on_start(self):
        if self._worker and self._worker.isRunning():
            return

        text = self._input.toPlainText().strip()
        if not text:
            self._set_status("请先输入 Base64 内容")
            return

        if not self._output_dir or not os.path.isdir(self._output_dir):
            # 如果还没选输出目录，弹出选择框
            folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
            if not folder:
                return
            self._output_dir = folder
            self._dir_edit.setText(folder)

        split_mode = 'block' if self._rb_block.isChecked() else 'line'
        entries = parse_entries(text, split_mode)
        if not entries:
            self._set_status("未解析到任何 Base64 条目")
            return

        prefix = self._prefix_edit.text().strip() or 'image'

        # 初始化表格
        self._table.setRowCount(len(entries))
        for row in range(len(entries)):
            self._table.setItem(row, 0, self._make_item(str(row + 1), Qt.AlignCenter))
            self._table.setItem(row, 1, self._make_item('…',    Qt.AlignCenter))
            self._table.setItem(row, 2, self._make_item('…',    Qt.AlignCenter))
            self._table.setItem(row, 3, self._make_item('处理中…'))

        self._progress.setRange(0, len(entries))
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._start_btn.setEnabled(False)
        self._open_dir_btn.setEnabled(False)
        self._set_status(f"转换中… 共 {len(entries)} 条")

        self._worker = _Worker(entries, self._output_dir, prefix)
        self._worker.row_done.connect(self._on_row_done)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _on_row_done(self, rec: dict):
        row = rec['index'] - 1
        if rec['error']:
            self._table.item(row, 1).setText('ERR')
            self._table.item(row, 2).setText('—')
            err_item = self._make_item(f"失败: {rec['error']}")
            err_item.setForeground(QColor('#d13438'))
            self._table.setItem(row, 3, err_item)
        else:
            self._table.item(row, 1).setText(rec['ext'].upper())
            self._table.item(row, 2).setText(_fmt_size(rec['size']))
            ok_item = self._make_item(os.path.basename(rec['path']))
            ok_item.setForeground(QColor('#107c10'))
            self._table.setItem(row, 3, ok_item)
        self._progress.setValue(rec['index'])

    def _on_all_done(self, ok: int, total: int):
        self._start_btn.setEnabled(True)
        self._open_dir_btn.setEnabled(bool(self._output_dir))
        if ok == total:
            self._set_status(f"全部完成，共 {total} 张图片已保存")
        else:
            self._set_status(f"完成 {ok}/{total}，{total - ok} 条失败")

    def _on_open_dir(self):
        if self._output_dir and os.path.isdir(self._output_dir):
            if os.name == 'nt':
                os.startfile(self._output_dir)
            else:
                subprocess.Popen(['xdg-open', self._output_dir])

    # ─────────────────────────────────────────────────────────────────
    #  工具方法
    # ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _make_item(text: str, align: int = Qt.AlignLeft | Qt.AlignVCenter) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(align)
        return item

    def _set_status(self, msg: str):
        self._status_lbl.setText(msg)
