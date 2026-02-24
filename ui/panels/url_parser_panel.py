# -*- coding: utf-8 -*-
"""URL 解析面板

解析任意复杂 URL（含大量查询参数、URL 编码），
展示各组件，可编辑参数表格，自动生成 Python requests 代码。
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QPlainTextEdit,
    QSplitter, QApplication, QTabWidget,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

from core.url_parser import parse_url, rebuild_url, to_requests_code

_MONO = QFont("Consolas", 10)
_MONO.setStyleHint(QFont.Monospace)


class UrlParserPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parsed: dict | None = None
        self._build_ui()

    # ── 界面 ──────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(8)

        # 输入行
        top = QHBoxLayout()
        top.addWidget(QLabel("URL:"))
        self._url_in = QLineEdit()
        self._url_in.setFont(_MONO)
        self._url_in.setPlaceholderText(
            "粘贴任意复杂 URL，如 https://api.example.com/search?q=test&page=1&sort=asc&...")
        self._url_in.returnPressed.connect(self._on_parse)
        top.addWidget(self._url_in, stretch=1)

        self._method = QComboBox()
        self._method.addItems(['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
        self._method.setFixedWidth(80)
        self._method.currentTextChanged.connect(self._update_code)
        top.addWidget(self._method)

        b = QPushButton("解 析")
        b.setFixedWidth(70)
        b.setFixedHeight(30)
        b.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "border-radius:4px;border:none;}"
            "QPushButton:hover{background:#106ebe;}")
        b.clicked.connect(self._on_parse)
        top.addWidget(b)
        root.addLayout(top)

        # 主体：左侧参数表 + 右侧代码
        splitter = QSplitter(Qt.Horizontal)

        # ── 左：Tab (参数 / URL组件 / 请求头) ────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 4, 0)
        ll.setSpacing(4)

        tabs_left = QTabWidget()

        # Tab: 参数列表
        params_w = QWidget()
        pw = QVBoxLayout(params_w)
        pw.setContentsMargins(4, 4, 4, 4)
        pw.setSpacing(4)

        tbl_btns = QHBoxLayout()
        b_add = QPushButton("+ 添加行")
        b_add.setFixedHeight(26)
        b_add.clicked.connect(self._add_param_row)
        b_del = QPushButton("- 删除行")
        b_del.setFixedHeight(26)
        b_del.clicked.connect(self._del_param_row)
        b_rebuild = QPushButton("↻ 重建 URL")
        b_rebuild.setFixedHeight(26)
        b_rebuild.clicked.connect(self._rebuild_url)
        tbl_btns.addWidget(b_add)
        tbl_btns.addWidget(b_del)
        tbl_btns.addStretch()
        tbl_btns.addWidget(b_rebuild)
        pw.addLayout(tbl_btns)

        self._param_table = QTableWidget(0, 2)
        self._param_table.setHorizontalHeaderLabels(['参数名', '参数值（已解码）'])
        self._param_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Interactive)
        self._param_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self._param_table.setColumnWidth(0, 160)
        self._param_table.verticalHeader().setDefaultSectionSize(26)
        self._param_table.setFont(_MONO)
        self._param_table.itemChanged.connect(self._update_code)
        pw.addWidget(self._param_table)
        tabs_left.addTab(params_w, "查询参数")

        # Tab: URL 组件
        comp_w = QWidget()
        cw = QVBoxLayout(comp_w)
        cw.setContentsMargins(8, 8, 8, 8)
        cw.setSpacing(6)
        self._comp_fields: dict[str, QLineEdit] = {}
        for label, key in [
            ("协议 (Scheme)", "scheme"),
            ("主机 (Host)",   "netloc"),
            ("路径 (Path)",   "path"),
            ("Fragment",      "fragment"),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            le = QLineEdit()
            le.setReadOnly(True)
            le.setFont(_MONO)
            row.addWidget(le)
            self._comp_fields[key] = le
            cw.addLayout(row)
        cw.addStretch()
        tabs_left.addTab(comp_w, "URL 组件")

        # Tab: 附加 Headers（可选，加入代码）
        hdr_w = QWidget()
        hw = QVBoxLayout(hdr_w)
        hw.setContentsMargins(4, 4, 4, 4)
        hw.setSpacing(4)
        hw.addWidget(QLabel("可选：添加后将出现在生成代码的 headers 中"))

        hdr_tbl_btns = QHBoxLayout()
        bha = QPushButton("+ 添加")
        bha.setFixedHeight(26)
        bha.clicked.connect(self._add_header_row)
        bhd = QPushButton("- 删除")
        bhd.setFixedHeight(26)
        bhd.clicked.connect(self._del_header_row)
        hdr_tbl_btns.addWidget(bha)
        hdr_tbl_btns.addWidget(bhd)
        hdr_tbl_btns.addStretch()
        hw.addLayout(hdr_tbl_btns)

        self._hdr_table = QTableWidget(0, 2)
        self._hdr_table.setHorizontalHeaderLabels(['Header 名', 'Header 值'])
        self._hdr_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Interactive)
        self._hdr_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self._hdr_table.setColumnWidth(0, 160)
        self._hdr_table.verticalHeader().setDefaultSectionSize(26)
        self._hdr_table.setFont(_MONO)
        self._hdr_table.itemChanged.connect(self._update_code)
        hw.addWidget(self._hdr_table)
        tabs_left.addTab(hdr_w, "请求头 (可选)")

        ll.addWidget(tabs_left)

        # POST body type selector
        body_row = QHBoxLayout()
        body_row.addWidget(QLabel("POST 参数位置:"))
        self._body_type = QComboBox()
        self._body_type.addItems(['query (params=)', 'json body', 'form body'])
        self._body_type.currentIndexChanged.connect(self._update_code)
        body_row.addWidget(self._body_type)
        body_row.addStretch()
        ll.addLayout(body_row)

        splitter.addWidget(left)

        # ── 右：生成代码 ───────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)
        rl.setSpacing(4)

        code_top = QHBoxLayout()
        code_top.addWidget(QLabel("Python requests 代码"))
        code_top.addStretch()
        b_copy = QPushButton("复制代码")
        b_copy.setFixedHeight(26)
        b_copy.clicked.connect(
            lambda: QApplication.clipboard().setText(self._code_out.toPlainText()))
        code_top.addWidget(b_copy)
        rl.addLayout(code_top)

        self._code_out = QPlainTextEdit()
        self._code_out.setFont(_MONO)
        self._code_out.setReadOnly(True)
        self._code_out.setPlaceholderText("解析 URL 后自动生成代码…")
        rl.addWidget(self._code_out)

        splitter.addWidget(right)
        splitter.setSizes([420, 560])
        root.addWidget(splitter, stretch=1)

        # 状态
        self._status = QLabel("")
        self._status.setStyleSheet("color:#ca5010; font-size:11px;")
        root.addWidget(self._status)

    # ── 逻辑 ──────────────────────────────────────────────
    def _on_parse(self):
        url = self._url_in.text().strip()
        if not url:
            self._status.setText("请输入 URL")
            return
        try:
            self._parsed = parse_url(url)
            self._status.setText("")
        except Exception as e:
            self._status.setText(f"解析失败：{e}")
            return
        self._fill_ui()
        self._update_code()

    def _fill_ui(self):
        p = self._parsed
        # 参数表
        self._param_table.blockSignals(True)
        self._param_table.setRowCount(len(p['params']))
        for row, (k, v) in enumerate(p['params']):
            ki = QTableWidgetItem(k)
            vi = QTableWidgetItem(v)
            self._param_table.setItem(row, 0, ki)
            self._param_table.setItem(row, 1, vi)
        self._param_table.blockSignals(False)
        # 组件
        for key, le in self._comp_fields.items():
            le.setText(str(p.get(key, '')))

    def _get_params_from_table(self) -> list[tuple[str, str]]:
        result = []
        for row in range(self._param_table.rowCount()):
            k_item = self._param_table.item(row, 0)
            v_item = self._param_table.item(row, 1)
            k = k_item.text() if k_item else ''
            v = v_item.text() if v_item else ''
            if k:
                result.append((k, v))
        return result

    def _get_headers_from_table(self) -> list[tuple[str, str]]:
        result = []
        for row in range(self._hdr_table.rowCount()):
            k_item = self._hdr_table.item(row, 0)
            v_item = self._hdr_table.item(row, 1)
            k = k_item.text() if k_item else ''
            v = v_item.text() if v_item else ''
            if k:
                result.append((k, v))
        return result

    def _update_code(self):
        if self._parsed is None:
            return
        params  = self._get_params_from_table()
        headers = self._get_headers_from_table() or None
        method  = self._method.currentText()

        bt_idx  = self._body_type.currentIndex()
        body_type_map = {0: 'none', 1: 'json', 2: 'form'}
        body_type = body_type_map.get(bt_idx, 'none')

        tmp_parsed = dict(self._parsed)
        tmp_parsed['params'] = params

        code = to_requests_code(tmp_parsed, method, headers, body_type)
        self._code_out.setPlainText(code)

    def _rebuild_url(self):
        if self._parsed is None:
            return
        params = self._get_params_from_table()
        url = rebuild_url(self._parsed['base_url'], params,
                          self._parsed.get('fragment', ''))
        self._url_in.setText(url)

    def _add_param_row(self):
        row = self._param_table.rowCount()
        self._param_table.insertRow(row)
        self._param_table.setItem(row, 0, QTableWidgetItem(''))
        self._param_table.setItem(row, 1, QTableWidgetItem(''))

    def _del_param_row(self):
        rows = sorted(set(i.row() for i in self._param_table.selectedItems()),
                      reverse=True)
        for r in rows:
            self._param_table.removeRow(r)
        self._update_code()

    def _add_header_row(self):
        row = self._hdr_table.rowCount()
        self._hdr_table.insertRow(row)
        self._hdr_table.setItem(row, 0, QTableWidgetItem(''))
        self._hdr_table.setItem(row, 1, QTableWidgetItem(''))

    def _del_header_row(self):
        rows = sorted(set(i.row() for i in self._hdr_table.selectedItems()),
                      reverse=True)
        for r in rows:
            self._hdr_table.removeRow(r)
        self._update_code()
