# -*- coding: utf-8 -*-
"""HTML 美化 & 搜索面板

大字符串优化:
    - 使用 QPlainTextEdit 替代 QTextEdit（无富文本开销）
    - 美化操作放在 QThread 后台执行
    - 搜索高亮限制最多 5000 个以避免卡顿
    - 支持导入 / 导出文件
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QPlainTextEdit, QGroupBox, QComboBox, QSpinBox,
    QApplication, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog, QMessageBox,
    QCheckBox, QShortcut
)
from PyQt5.QtGui import QFont, QColor, QTextCursor, QTextCharFormat, QKeySequence
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.html_tools import (
    beautify_html, xpath_search, keyword_search, regex_search_html,
    HAS_LXML,
)

_MAX_HIGHLIGHTS = 5000  # 高亮上限，防止大文件卡顿


# ── 后台美化线程 ─────────────────────────────────────────────
class BeautifyThread(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, html_str, indent):
        super().__init__()
        self.html_str = html_str
        self.indent = indent

    def run(self):
        try:
            result = beautify_html(self.html_str, self.indent)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ── 面板 ─────────────────────────────────────────────────────
class HtmlPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mono = QFont("Consolas", 10)
        self._mono.setStyleHint(QFont.Monospace)
        self._thread = None
        self._build_ui()

    # ── UI 搭建 ──────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(5)

        # ============ 上半部分: 输入 + 输出 ==================
        editor_splitter = QSplitter(Qt.Vertical)

        # ── 输入区 ───────────────────────────────────────────
        in_w = QWidget()
        in_l = QVBoxLayout(in_w)
        in_l.setContentsMargins(0, 0, 0, 0)
        in_l.setSpacing(3)

        in_hdr = QHBoxLayout()
        in_hdr.addWidget(QLabel("HTML 输入:"))
        in_hdr.addStretch()
        self._in_info = QLabel("")
        self._in_info.setStyleSheet("color:#666;font-size:11px")
        in_hdr.addWidget(self._in_info)
        import_btn = QPushButton("导入文件")
        import_btn.setFixedWidth(90)
        import_btn.clicked.connect(self._import_file)
        in_hdr.addWidget(import_btn)
        in_l.addLayout(in_hdr)

        self._input = QPlainTextEdit()
        self._input.setFont(self._mono)
        self._input.setPlaceholderText(
            "粘贴或导入 HTML 代码，例如:\n"
            '<div class="box"><p>Hello</p><ul><li>A</li><li>B</li></ul></div>'
        )
        self._input.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._input.textChanged.connect(self._on_input_changed)
        in_l.addWidget(self._input)
        editor_splitter.addWidget(in_w)

        # ── 操作行 ───────────────────────────────────────────
        ctrl_w = QWidget()
        ctrl_l = QHBoxLayout(ctrl_w)
        ctrl_l.setContentsMargins(0, 2, 0, 2)

        self._beautify_btn = QPushButton("▶  美化 HTML")
        self._beautify_btn.setFixedHeight(34)
        self._beautify_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:13px;border-radius:4px;padding:0 22px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}")
        self._beautify_btn.clicked.connect(self._beautify)
        ctrl_l.addWidget(self._beautify_btn)

        ctrl_l.addWidget(QLabel("缩进:"))
        self._indent = QSpinBox()
        self._indent.setRange(1, 8)
        self._indent.setValue(2)
        self._indent.setFixedWidth(55)
        ctrl_l.addWidget(self._indent)

        swap_btn = QPushButton("⇅ 交换")
        swap_btn.setFixedHeight(30)
        swap_btn.clicked.connect(self._swap)
        ctrl_l.addWidget(swap_btn)

        clear_btn = QPushButton("清空")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._clear_all)
        ctrl_l.addWidget(clear_btn)

        self._wrap_cb = QCheckBox("自动换行")
        self._wrap_cb.toggled.connect(self._toggle_wrap)
        ctrl_l.addWidget(self._wrap_cb)

        ctrl_l.addStretch()
        editor_splitter.addWidget(ctrl_w)

        # ── 输出区 ───────────────────────────────────────────
        out_w = QWidget()
        out_l = QVBoxLayout(out_w)
        out_l.setContentsMargins(0, 0, 0, 0)
        out_l.setSpacing(3)

        out_hdr = QHBoxLayout()
        out_hdr.addWidget(QLabel("美化输出:"))
        out_hdr.addStretch()
        self._out_info = QLabel("")
        self._out_info.setStyleSheet("color:#666;font-size:11px")
        out_hdr.addWidget(self._out_info)
        copy_btn = QPushButton("复制")
        copy_btn.setFixedWidth(70)
        copy_btn.clicked.connect(self._copy_output)
        out_hdr.addWidget(copy_btn)
        export_btn = QPushButton("导出文件")
        export_btn.setFixedWidth(90)
        export_btn.clicked.connect(self._export_file)
        out_hdr.addWidget(export_btn)
        out_l.addLayout(out_hdr)

        self._output = QPlainTextEdit()
        self._output.setFont(self._mono)
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("美化后的 HTML 将显示在此…")
        self._output.setLineWrapMode(QPlainTextEdit.NoWrap)
        out_l.addWidget(self._output)
        editor_splitter.addWidget(out_w)

        editor_splitter.setSizes([200, 34, 250])
        root.addWidget(editor_splitter, stretch=5)

        # ============ 下半部分: 搜索 =========================
        search_group = QGroupBox("搜索（在输出中搜索）")
        sg = QVBoxLayout(search_group)
        sg.setSpacing(4)

        # 搜索栏
        s_row = QHBoxLayout()
        s_row.addWidget(QLabel("模式:"))
        self._search_mode = QComboBox()
        self._search_mode.addItems(["关键字", "正则表达式", "XPath"])
        self._search_mode.setFixedWidth(110)
        s_row.addWidget(self._search_mode)

        self._search_input = QLineEdit()
        self._search_input.setFont(self._mono)
        self._search_input.setPlaceholderText(
            "输入搜索内容… (关键字 / 正则 / XPath 如 //div[@class])")
        self._search_input.returnPressed.connect(self._do_search)
        s_row.addWidget(self._search_input, stretch=1)

        self._case_cb = QCheckBox("区分大小写")
        s_row.addWidget(self._case_cb)

        search_btn = QPushButton("搜索")
        search_btn.setFixedHeight(28)
        search_btn.clicked.connect(self._do_search)
        s_row.addWidget(search_btn)

        clear_search_btn = QPushButton("清除")
        clear_search_btn.setFixedHeight(28)
        clear_search_btn.clicked.connect(self._clear_search)
        s_row.addWidget(clear_search_btn)
        sg.addLayout(s_row)

        # 搜索结果
        self._search_label = QLabel("")
        self._search_label.setStyleSheet("color:#666;font-size:11px")
        sg.addWidget(self._search_label)

        self._result_table = QTableWidget(0, 3)
        self._result_table.setHorizontalHeaderLabels(["行:列", "匹配", "上下文"])
        self._result_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Fixed)
        self._result_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Interactive)
        self._result_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch)
        self._result_table.setColumnWidth(0, 70)
        self._result_table.setColumnWidth(1, 180)
        self._result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._result_table.verticalHeader().setDefaultSectionSize(24)
        self._result_table.setFont(self._mono)
        self._result_table.cellClicked.connect(self._on_result_click)
        sg.addWidget(self._result_table)

        root.addWidget(search_group, stretch=3)

        # 状态
        self._status = QLabel("就绪" + ("" if HAS_LXML
                                        else " | ⚠ lxml 未安装，XPath 和美化不可用"))
        self._status.setStyleSheet("color:#666;font-size:11px")
        root.addWidget(self._status)

        # 快捷键
        QShortcut(QKeySequence("Ctrl+Return"), self, self._beautify)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: (
            self._search_input.setFocus(), self._search_input.selectAll()))

    # ── 输入 ─────────────────────────────────────────────────
    def _on_input_changed(self):
        t = self._input.toPlainText()
        size = len(t.encode('utf-8'))
        if size >= 1024 * 1024:
            self._in_info.setText(f"{len(t):,} 字符 / {size / 1024 / 1024:.1f} MB")
        elif size >= 1024:
            self._in_info.setText(f"{len(t):,} 字符 / {size / 1024:.1f} KB")
        else:
            self._in_info.setText(f"{len(t):,} 字符 / {size} B")

    # ── 美化 ─────────────────────────────────────────────────
    def _beautify(self):
        text = self._input.toPlainText()
        if not text.strip():
            self._status.setText("请先输入 HTML")
            return
        if not HAS_LXML:
            self._status.setText("需要安装 lxml: pip install lxml")
            return

        self._beautify_btn.setEnabled(False)
        self._beautify_btn.setText("处理中…")
        self._status.setText("正在美化…")
        QApplication.processEvents()

        indent = self._indent.value()

        # 小文本直接同步处理，大文本走线程
        if self._thread and self._thread.isRunning():
            self._status.setText("正在处理中，请稍候…")
            return
        if len(text) < 200_000:
            try:
                result = beautify_html(text, indent)
                self._set_output(result)
                self._status.setText("美化完成")
            except Exception as e:
                self._output.setPlainText(f"错误: {e}")
                self._status.setText(f"出错: {type(e).__name__}")
            finally:
                self._beautify_btn.setEnabled(True)
                self._beautify_btn.setText("▶  美化 HTML")
        else:
            self._thread = BeautifyThread(text, indent)
            self._thread.finished.connect(self._on_beautify_done)
            self._thread.error.connect(self._on_beautify_error)
            self._thread.start()

    def _on_beautify_done(self, result):
        self._set_output(result)
        self._beautify_btn.setEnabled(True)
        self._beautify_btn.setText("▶  美化 HTML")
        self._status.setText("美化完成")

    def _on_beautify_error(self, msg):
        self._output.setPlainText(f"错误: {msg}")
        self._beautify_btn.setEnabled(True)
        self._beautify_btn.setText("▶  美化 HTML")
        self._status.setText("美化出错")

    def _set_output(self, text):
        self._output.setPlainText(text)
        size = len(text.encode('utf-8'))
        lines = text.count('\n') + 1
        if size >= 1024 * 1024:
            self._out_info.setText(f"{lines:,} 行 / {size / 1024 / 1024:.1f} MB")
        elif size >= 1024:
            self._out_info.setText(f"{lines:,} 行 / {size / 1024:.1f} KB")
        else:
            self._out_info.setText(f"{lines:,} 行 / {size} B")

    # ── 搜索 ─────────────────────────────────────────────────
    def _do_search(self):
        text = self._output.toPlainText()
        query = self._search_input.text().strip()
        if not text:
            self._status.setText("输出为空，请先美化 HTML")
            return
        if not query:
            self._status.setText("请输入搜索内容")
            return

        mode = self._search_mode.currentText()
        case = self._case_cb.isChecked()
        self._result_table.setRowCount(0)
        self._output.setExtraSelections([])
        self._search_positions = []

        try:
            if mode == "XPath":
                self._search_xpath(text, query)
            elif mode == "关键字":
                self._search_keyword(text, query, case)
            else:
                self._search_regex(text, query, case)
        except Exception as e:
            self._search_label.setText(f"搜索出错: {e}")
            self._status.setText(f"搜索出错: {type(e).__name__}")

    def _search_xpath(self, text, xpath_expr):
        # XPath 搜索：结果是 DOM 元素，不做文本高亮
        raw_html = self._input.toPlainText() or text
        results = xpath_search(raw_html, xpath_expr)

        self._result_table.setColumnCount(3)
        self._result_table.setHorizontalHeaderLabels(["序号", "标签", "内容"])
        self._result_table.setColumnWidth(0, 50)
        self._result_table.setColumnWidth(1, 80)
        self._search_positions = []

        for r in results[:_MAX_HIGHLIGHTS]:
            row = self._result_table.rowCount()
            self._result_table.insertRow(row)
            idx_item = QTableWidgetItem(str(r['index']))
            idx_item.setTextAlignment(Qt.AlignCenter)
            self._result_table.setItem(row, 0, idx_item)
            self._result_table.setItem(row, 1, QTableWidgetItem(r['tag']))
            preview = r['text'].replace('\n', ' ')
            if len(preview) > 200:
                preview = preview[:200] + '…'
            self._result_table.setItem(row, 2, QTableWidgetItem(preview))
            self._search_positions.append(r)

        total = len(results)
        shown = min(total, _MAX_HIGHLIGHTS)
        self._search_label.setText(
            f"XPath 找到 {total} 个节点" +
            (f"（显示前 {shown} 个）" if total > shown else ""))
        self._status.setText(f"XPath 搜索完成: {total} 个匹配")

    def _search_keyword(self, text, keyword, case_sensitive):
        results = keyword_search(text, keyword, case_sensitive)
        self._populate_text_results(results, keyword_len=len(keyword))

    def _search_regex(self, text, pattern, case_sensitive):
        results = regex_search_html(text, pattern,
                                    ignore_case=not case_sensitive)
        self._populate_text_results(results)

    def _populate_text_results(self, results, keyword_len=None):
        """填充关键字 / 正则搜索结果 + 高亮输出区。"""
        self._result_table.setColumnCount(3)
        self._result_table.setHorizontalHeaderLabels(
            ["行:列", "匹配", "上下文"])
        self._result_table.setColumnWidth(0, 70)
        self._result_table.setColumnWidth(1, 180)
        self._search_positions = []

        # 高亮
        fmt = QTextCharFormat()
        fmt.setBackground(QColor('#FFFF00'))
        fmt.setForeground(QColor('#000000'))
        selections = []

        for i, r in enumerate(results):
            if i >= _MAX_HIGHLIGHTS:
                break
            # 表格行
            row = self._result_table.rowCount()
            self._result_table.insertRow(row)
            self._result_table.setItem(
                row, 0, QTableWidgetItem(f"{r['line']}:{r['col']}"))
            match_text = r.get('match', '') or ''
            if not match_text and keyword_len:
                # keyword search 没有 'match' 字段，从 context 中截取
                pass
            self._result_table.setItem(
                row, 1, QTableWidgetItem(match_text or r['context'][:40]))
            self._result_table.setItem(
                row, 2, QTableWidgetItem(r['context']))

            self._search_positions.append(r)

            # 高亮
            sel = QPlainTextEdit.ExtraSelection()  # type: ignore
            sel.format = fmt
            cursor = self._output.textCursor()
            cursor.setPosition(r['pos'])
            cursor.movePosition(
                QTextCursor.Right, QTextCursor.KeepAnchor, r['length'])
            sel.cursor = cursor
            selections.append(sel)

        self._output.setExtraSelections(selections)

        total = len(results)
        shown = min(total, _MAX_HIGHLIGHTS)
        self._search_label.setText(
            f"找到 {total} 个匹配" +
            (f"（高亮前 {shown} 个）" if total > shown else ""))
        self._status.setText(f"搜索完成: {total} 个匹配")

    def _on_result_click(self, row, _col):
        """点击搜索结果 → 跳转到输出区对应位置。"""
        if row >= len(self._search_positions):
            return
        r = self._search_positions[row]

        mode = self._search_mode.currentText()
        if mode == "XPath":
            # XPath 结果: 显示在弹出剪贴板 / 状态
            text = r.get('text', '')
            QApplication.clipboard().setText(text)
            self._status.setText(f"已复制第 {r['index']} 个节点到剪贴板")
            return

        # 关键字 / 正则: 跳转到位置
        cursor = self._output.textCursor()
        cursor.setPosition(r['pos'])
        cursor.movePosition(
            QTextCursor.Right, QTextCursor.KeepAnchor, r['length'])
        self._output.setTextCursor(cursor)
        self._output.centerCursor()
        self._output.setFocus()

    def _clear_search(self):
        self._search_input.clear()
        self._result_table.setRowCount(0)
        self._search_label.setText("")
        self._output.setExtraSelections([])
        self._search_positions = []

    # ── 通用操作 ─────────────────────────────────────────────
    def _swap(self):
        o = self._output.toPlainText()
        i = self._input.toPlainText()
        self._input.setPlainText(o)
        self._output.setPlainText(i)

    def _clear_all(self):
        self._input.clear()
        self._output.clear()
        self._clear_search()
        self._in_info.setText("")
        self._out_info.setText("")
        self._status.setText("已清空")

    def _toggle_wrap(self, checked):
        mode = (QPlainTextEdit.WidgetWidth if checked
                else QPlainTextEdit.NoWrap)
        self._input.setLineWrapMode(mode)
        self._output.setLineWrapMode(mode)

    def _copy_output(self):
        t = self._output.toPlainText()
        if t:
            QApplication.clipboard().setText(t)
            self._status.setText("已复制到剪贴板")

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 HTML 文件", "",
            "HTML 文件 (*.html *.htm *.xhtml *.xml *.svg);;"
            "文本文件 (*.txt *.log);;"
            "所有文件 (*)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(path, 'r', encoding='gbk', errors='replace') as f:
                    content = f.read()
            except Exception as e:
                QMessageBox.warning(self, "导入失败", str(e))
                return
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))
            return

        self._input.setPlainText(content)
        self._status.setText(f"已导入: {os.path.basename(path)}")

    def _export_file(self):
        t = self._output.toPlainText()
        if not t:
            QMessageBox.information(self, "提示", "输出为空")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 HTML 文件", "output.html",
            "HTML 文件 (*.html);;文本文件 (*.txt);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(t)
            self._status.setText(f"已导出: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
