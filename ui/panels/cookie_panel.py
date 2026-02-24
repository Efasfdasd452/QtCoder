# -*- coding: utf-8 -*-
"""Cookie 解析面板

Tab 1 · 请求 Cookie    — 解析 Cookie: 请求头，生成 Python dict / requests 代码
Tab 2 · Set-Cookie     — 解析 Set-Cookie: 响应头，展示所有属性及安全标志
"""

import json

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QTabWidget, QApplication,
    QFrame,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

from core.cookie_parser import (
    parse_request_cookie, cookies_to_dict_code, cookies_to_header,
    parse_set_cookie,
)

_MONO = QFont("Consolas", 10)
_MONO.setStyleHint(QFont.Monospace)


class CookiePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(8)

        tabs = QTabWidget()
        tabs.addTab(self._build_request_tab(), "🍪  Cookie 请求头")
        tabs.addTab(self._build_setcookie_tab(), "📋  Set-Cookie 响应头")
        root.addWidget(tabs)

    # ─────────────────────────────────────────────────────────
    #  Tab 1: Cookie 请求头解析
    # ─────────────────────────────────────────────────────────
    def _build_request_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # 输入
        in_grp = QGroupBox("Cookie: 请求头内容")
        ig = QVBoxLayout(in_grp)
        self._req_in = QPlainTextEdit()
        self._req_in.setFont(_MONO)
        self._req_in.setFixedHeight(70)
        self._req_in.setPlaceholderText(
            "粘贴 Cookie 请求头（可含或不含 'Cookie:' 前缀），如：\n"
            "session_id=abc123; user=admin; token=eyJhbG...; theme=dark")
        self._req_in.textChanged.connect(self._on_request_parse)
        ig.addWidget(self._req_in)
        lay.addWidget(in_grp)

        # 参数表格
        tbl_grp = QGroupBox("解析结果")
        tg = QVBoxLayout(tbl_grp)
        tg.setContentsMargins(4, 4, 4, 4)
        self._req_table = QTableWidget(0, 2)
        self._req_table.setHorizontalHeaderLabels(['Cookie 名', 'Cookie 值'])
        self._req_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Interactive)
        self._req_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self._req_table.setColumnWidth(0, 200)
        self._req_table.verticalHeader().setDefaultSectionSize(26)
        self._req_table.setFont(_MONO)
        self._req_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._req_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        tg.addWidget(self._req_table)

        # 复制按钮区
        copy_row = QHBoxLayout()
        self._req_count = QLabel("共 0 条")
        self._req_count.setStyleSheet("color:#666; font-size:11px;")
        copy_row.addWidget(self._req_count)
        copy_row.addStretch()

        for text, slot in [
            ("复制为 Python dict", self._copy_req_dict),
            ("复制为 requests cookies=", self._copy_req_requests),
            ("复制为 JSON",        self._copy_req_json),
            ("重建 Cookie 头",     self._copy_req_header),
        ]:
            b = QPushButton(text)
            b.setFixedHeight(26)
            b.clicked.connect(slot)
            copy_row.addWidget(b)
        tg.addLayout(copy_row)
        lay.addWidget(tbl_grp)

        self._req_err = QLabel("")
        self._req_err.setStyleSheet("color:#ca5010; font-size:11px;")
        lay.addWidget(self._req_err)
        lay.addStretch()
        return w

    def _on_request_parse(self):
        text = self._req_in.toPlainText().strip()
        if not text:
            self._req_table.setRowCount(0)
            self._req_count.setText("共 0 条")
            return
        try:
            cookies = parse_request_cookie(text)
            self._req_err.setText("")
        except Exception as e:
            self._req_err.setText(str(e))
            return

        self._req_table.setRowCount(len(cookies))
        for row, (k, v) in enumerate(cookies):
            ki = QTableWidgetItem(k)
            vi = QTableWidgetItem(v)
            self._req_table.setItem(row, 0, ki)
            self._req_table.setItem(row, 1, vi)
        self._req_count.setText(f"共 {len(cookies)} 条")

    def _get_req_cookies(self):
        return [(self._req_table.item(r, 0).text(),
                 self._req_table.item(r, 1).text())
                for r in range(self._req_table.rowCount())
                if self._req_table.item(r, 0)]

    def _copy_req_dict(self):
        QApplication.clipboard().setText(
            cookies_to_dict_code(self._get_req_cookies()))

    def _copy_req_requests(self):
        cookies = self._get_req_cookies()
        lines = ['# 在 requests 中使用：',
                 'response = requests.get(url, cookies=cookies)',
                 '',
                 cookies_to_dict_code(cookies)]
        QApplication.clipboard().setText('\n'.join(lines))

    def _copy_req_json(self):
        QApplication.clipboard().setText(
            json.dumps(dict(self._get_req_cookies()),
                       ensure_ascii=False, indent=2))

    def _copy_req_header(self):
        QApplication.clipboard().setText(
            cookies_to_header(self._get_req_cookies()))

    # ─────────────────────────────────────────────────────────
    #  Tab 2: Set-Cookie 解析
    # ─────────────────────────────────────────────────────────
    def _build_setcookie_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        in_grp = QGroupBox("Set-Cookie: 响应头内容")
        ig = QVBoxLayout(in_grp)
        self._sc_in = QPlainTextEdit()
        self._sc_in.setFont(_MONO)
        self._sc_in.setFixedHeight(70)
        self._sc_in.setPlaceholderText(
            "粘贴 Set-Cookie 响应头（可含或不含 'Set-Cookie:' 前缀），如：\n"
            "session=abc123; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=3600")
        self._sc_in.textChanged.connect(self._on_sc_parse)
        ig.addWidget(self._sc_in)
        lay.addWidget(in_grp)

        # 主体：两列展示
        result_grp = QGroupBox("解析结果")
        rg = QVBoxLayout(result_grp)
        rg.setContentsMargins(8, 8, 8, 8)
        rg.setSpacing(6)

        # Cookie 本体
        body_row = QHBoxLayout()
        body_row.addWidget(QLabel("名称:"))
        self._sc_name = QLabel("—")
        self._sc_name.setFont(_MONO)
        self._sc_name.setStyleSheet("font-weight:bold; color:#0078d4;")
        body_row.addWidget(self._sc_name)
        body_row.addSpacing(24)
        body_row.addWidget(QLabel("值:"))
        self._sc_value = QLabel("—")
        self._sc_value.setFont(_MONO)
        self._sc_value.setWordWrap(True)
        body_row.addWidget(self._sc_value, stretch=1)
        rg.addLayout(body_row)

        # 安全标志
        flag_row = QHBoxLayout()
        flag_row.addWidget(QLabel("安全标志:"))
        self._sc_flags = QLabel("—")
        self._sc_flags.setStyleSheet("font-weight:bold;")
        flag_row.addWidget(self._sc_flags)
        flag_row.addStretch()
        rg.addLayout(flag_row)

        # 过期信息
        exp_row = QHBoxLayout()
        exp_row.addWidget(QLabel("过期时间:"))
        self._sc_expires = QLabel("—")
        exp_row.addWidget(self._sc_expires)
        exp_row.addStretch()
        rg.addLayout(exp_row)

        # 属性表格
        rg.addWidget(QLabel("全部属性:"))
        self._sc_table = QTableWidget(0, 2)
        self._sc_table.setHorizontalHeaderLabels(['属性', '值'])
        self._sc_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Interactive)
        self._sc_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self._sc_table.setColumnWidth(0, 130)
        self._sc_table.verticalHeader().setDefaultSectionSize(26)
        self._sc_table.setFont(_MONO)
        self._sc_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        rg.addWidget(self._sc_table)

        lay.addWidget(result_grp)
        self._sc_err = QLabel("")
        self._sc_err.setStyleSheet("color:#ca5010; font-size:11px;")
        lay.addWidget(self._sc_err)
        lay.addStretch()
        return w

    def _on_sc_parse(self):
        text = self._sc_in.toPlainText().strip()
        if not text:
            self._sc_name.setText("—")
            self._sc_value.setText("—")
            self._sc_flags.setText("—")
            self._sc_expires.setText("—")
            self._sc_table.setRowCount(0)
            return
        try:
            info = parse_set_cookie(text)
            self._sc_err.setText("")
        except Exception as e:
            self._sc_err.setText(str(e))
            return

        self._sc_name.setText(info['name'])
        self._sc_value.setText(info['value'])

        flags = info['security_flags']
        if flags:
            flag_colors = {'secure': '#107c10', 'httponly': '#0078d4',
                           'partitioned': '#5c2d91'}
            parts = []
            for f in flags:
                color = flag_colors.get(f, '#333')
                parts.append(
                    f"<span style='color:{color};font-weight:bold;'>"
                    f"{f.capitalize()}</span>")
            self._sc_flags.setText("  ".join(parts))
        else:
            self._sc_flags.setText("无")

        exp_dt = info['expires_dt']
        self._sc_expires.setText(exp_dt if exp_dt else "—（会话 Cookie）")

        attrs = info['attributes']
        rows = [(k, str(v)) for k, v in attrs.items()]
        self._sc_table.setRowCount(len(rows))
        for row, (k, v) in enumerate(rows):
            ki = QTableWidgetItem(k)
            ki.setFont(_MONO)
            vi = QTableWidgetItem("✓" if v == 'True' else v)
            vi.setFont(_MONO)
            self._sc_table.setItem(row, 0, ki)
            self._sc_table.setItem(row, 1, vi)
