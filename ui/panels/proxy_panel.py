# -*- coding: utf-8 -*-
"""代理 URL 批量测试面板 — 基于 aiohttp 异步并发"""

import asyncio
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QGroupBox, QComboBox, QSpinBox,
    QApplication, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QProgressBar, QSplitter, QMessageBox,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.proxy_tester import build_proxy_url, batch_test


# ── 后台异步测试线程 ─────────────────────────────────────────
class ProxyTestThread(QThread):
    """在后台线程运行 asyncio 事件循环执行批量测试。"""
    result_ready = pyqtSignal(dict)
    progress = pyqtSignal(int, int)
    finished_all = pyqtSignal(str)     # 完成摘要
    error = pyqtSignal(str)

    def __init__(self, urls, proxy_url, timeout, concurrency):
        super().__init__()
        self.urls = urls
        self.proxy_url = proxy_url
        self.timeout = timeout
        self.concurrency = concurrency
        self._stop_event = None

    def stop(self):
        if self._stop_event:
            self._stop_event.set()

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._stop_event = asyncio.Event()

            results = loop.run_until_complete(
                batch_test(
                    self.urls,
                    proxy_url=self.proxy_url,
                    timeout=self.timeout,
                    concurrency=self.concurrency,
                    stop_event=self._stop_event,
                    on_result=lambda r: self.result_ready.emit(r),
                    on_progress=lambda d, t: self.progress.emit(d, t),
                )
            )
            loop.close()

            ok = sum(1 for r in results if r and r.get('ok'))
            fail = len(results) - ok
            self.finished_all.emit(f"完成: {ok} 成功, {fail} 失败")
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")
            self.finished_all.emit("出错终止")


# ── 面板 ─────────────────────────────────────────────────────
class ProxyTestPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mono = QFont("Consolas", 10)
        self._mono.setStyleHint(QFont.Monospace)
        self._thread = None
        self._ok_count = 0
        self._fail_count = 0
        self._build_ui()

    # ── UI 搭建 ──────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(6)

        # ── 代理设置 ─────────────────────────────────────────
        proxy_group = QGroupBox("代理设置")
        pg = QVBoxLayout(proxy_group)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("代理类型:"))
        self._proxy_type = QComboBox()
        self._proxy_type.addItems(["无代理", "HTTP", "SOCKS5", "SOCKS4"])
        self._proxy_type.setFixedWidth(110)
        self._proxy_type.currentTextChanged.connect(self._on_proxy_type)
        r1.addWidget(self._proxy_type)
        r1.addSpacing(12)
        r1.addWidget(QLabel("地址:"))
        self._proxy_host = QLineEdit()
        self._proxy_host.setPlaceholderText("127.0.0.1")
        self._proxy_host.setFixedWidth(180)
        r1.addWidget(self._proxy_host)
        r1.addWidget(QLabel(":"))
        self._proxy_port = QSpinBox()
        self._proxy_port.setRange(1, 65535)
        self._proxy_port.setValue(1080)
        self._proxy_port.setFixedWidth(80)
        r1.addWidget(self._proxy_port)
        r1.addStretch()
        pg.addLayout(r1)

        # 认证行
        self._auth_row = QWidget()
        r2 = QHBoxLayout(self._auth_row)
        r2.setContentsMargins(0, 0, 0, 0)
        r2.addWidget(QLabel("用户名:"))
        self._proxy_user = QLineEdit()
        self._proxy_user.setPlaceholderText("可选")
        self._proxy_user.setFixedWidth(140)
        r2.addWidget(self._proxy_user)
        r2.addSpacing(12)
        r2.addWidget(QLabel("密码:"))
        self._proxy_pass = QLineEdit()
        self._proxy_pass.setPlaceholderText("可选")
        self._proxy_pass.setEchoMode(QLineEdit.Password)
        self._proxy_pass.setFixedWidth(140)
        r2.addWidget(self._proxy_pass)
        r2.addStretch()
        pg.addWidget(self._auth_row)
        self._auth_row.setVisible(False)

        root.addWidget(proxy_group)

        # ── URL 输入 & 参数 ──────────────────────────────────
        splitter = QSplitter(Qt.Vertical)

        # URL 输入
        url_w = QWidget()
        url_l = QVBoxLayout(url_w)
        url_l.setContentsMargins(0, 0, 0, 0)
        url_hdr = QHBoxLayout()
        url_hdr.addWidget(QLabel("URL 列表（每行一个）:"))
        url_hdr.addStretch()
        self._url_count_label = QLabel("")
        url_hdr.addWidget(self._url_count_label)
        url_l.addLayout(url_hdr)

        self._url_input = QTextEdit()
        self._url_input.setFont(self._mono)
        self._url_input.setPlaceholderText(
            "每行一个 URL，例如:\n"
            "https://www.google.com\n"
            "https://www.github.com\n"
            "https://www.baidu.com\n"
            "https://httpbin.org/ip"
        )
        self._url_input.textChanged.connect(self._update_url_count)
        url_l.addWidget(self._url_input)
        splitter.addWidget(url_w)

        # 结果表格
        result_w = QWidget()
        result_l = QVBoxLayout(result_w)
        result_l.setContentsMargins(0, 0, 0, 0)
        res_hdr = QHBoxLayout()
        res_hdr.addWidget(QLabel("测试结果:"))
        res_hdr.addStretch()
        self._result_label = QLabel("")
        res_hdr.addWidget(self._result_label)
        copy_btn = QPushButton("复制结果")
        copy_btn.setFixedWidth(90)
        copy_btn.clicked.connect(self._copy_results)
        res_hdr.addWidget(copy_btn)
        result_l.addLayout(res_hdr)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "URL", "状态码", "耗时", "大小", "Server", "类型", "错误"
        ])
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 7):
            h.setSectionResizeMode(col, QHeaderView.Interactive)
        self._table.setColumnWidth(1, 60)
        self._table.setColumnWidth(2, 70)
        self._table.setColumnWidth(3, 75)
        self._table.setColumnWidth(4, 130)
        self._table.setColumnWidth(5, 140)
        self._table.setColumnWidth(6, 200)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.setFont(self._mono)
        self._table.setSortingEnabled(True)
        result_l.addWidget(self._table)
        splitter.addWidget(result_w)

        splitter.setSizes([200, 350])
        root.addWidget(splitter, stretch=1)

        # ── 控制行 ───────────────────────────────────────────
        ctrl = QHBoxLayout()

        ctrl.addWidget(QLabel("并发:"))
        self._concurrency = QSpinBox()
        self._concurrency.setRange(1, 100)
        self._concurrency.setValue(10)
        self._concurrency.setFixedWidth(65)
        ctrl.addWidget(self._concurrency)

        ctrl.addSpacing(10)
        ctrl.addWidget(QLabel("超时:"))
        self._timeout = QSpinBox()
        self._timeout.setRange(1, 120)
        self._timeout.setValue(10)
        self._timeout.setSuffix(" 秒")
        self._timeout.setFixedWidth(80)
        ctrl.addWidget(self._timeout)

        ctrl.addSpacing(16)

        self._start_btn = QPushButton("▶  开始测试")
        self._start_btn.setFixedHeight(34)
        self._start_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:13px;border-radius:4px;padding:0 22px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}")
        self._start_btn.clicked.connect(self._start)
        ctrl.addWidget(self._start_btn)

        self._stop_btn = QPushButton("■ 停止")
        self._stop_btn.setFixedHeight(30)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop)
        ctrl.addWidget(self._stop_btn)

        self._clear_btn = QPushButton("清空结果")
        self._clear_btn.setFixedHeight(30)
        self._clear_btn.clicked.connect(self._clear_results)
        ctrl.addWidget(self._clear_btn)

        ctrl.addStretch()
        root.addLayout(ctrl)

        # ── 进度条 ───────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setFixedHeight(18)
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        # 状态
        self._status = QLabel("就绪")
        self._status.setStyleSheet("color:#666;font-size:11px")
        root.addWidget(self._status)

    # ── 事件处理 ─────────────────────────────────────────────
    def _on_proxy_type(self, ptype):
        has_proxy = ptype != "无代理"
        self._proxy_host.setEnabled(has_proxy)
        self._proxy_port.setEnabled(has_proxy)
        self._auth_row.setVisible(has_proxy)

    def _update_url_count(self):
        urls = self._parse_urls()
        self._url_count_label.setText(f"{len(urls)} 个 URL")

    def _parse_urls(self):
        text = self._url_input.toPlainText()
        urls = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # 自动补全 scheme
            if not line.startswith(('http://', 'https://')):
                line = 'http://' + line
            urls.append(line)
        return urls

    def _start(self):
        if self._thread and self._thread.isRunning():
            QMessageBox.information(
                self, "提示", "当前测试正在进行，请等待完成或点击停止。")
            return
        urls = self._parse_urls()
        if not urls:
            self._status.setText("请输入至少一个 URL")
            return

        # 构建代理 URL
        proxy_url = None
        ptype = self._proxy_type.currentText()
        if ptype != "无代理":
            try:
                proxy_url = build_proxy_url(
                    ptype,
                    self._proxy_host.text(),
                    self._proxy_port.value(),
                    self._proxy_user.text(),
                    self._proxy_pass.text(),
                )
            except ValueError as e:
                self._status.setText(str(e))
                return

        # 重置
        self._table.setRowCount(0)
        self._table.setSortingEnabled(False)
        self._ok_count = 0
        self._fail_count = 0
        self._progress.setRange(0, len(urls))
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)

        proxy_info = f" (via {ptype} {self._proxy_host.text()}:{self._proxy_port.value()})" if proxy_url else " (直连)"
        self._status.setText(
            f"正在测试 {len(urls)} 个 URL{proxy_info}…")

        # 启动线程
        self._thread = ProxyTestThread(
            urls, proxy_url,
            self._timeout.value(),
            self._concurrency.value(),
        )
        self._thread.result_ready.connect(self._on_result)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished_all.connect(self._on_finished)
        self._thread.error.connect(
            lambda msg: self._status.setText(f"错误: {msg}"))
        self._thread.start()

    def _stop(self):
        if self._thread and self._thread.isRunning():
            self._thread.stop()
            self._status.setText("正在停止…")

    def _on_result(self, r):
        row = self._table.rowCount()
        self._table.insertRow(row)

        # URL
        self._table.setItem(row, 0, QTableWidgetItem(r['url']))

        # 状态码
        status = r['status']
        s_item = QTableWidgetItem(str(status) if status else '-')
        s_item.setTextAlignment(Qt.AlignCenter)
        if r['ok']:
            self._ok_count += 1
            if 200 <= status < 300:
                s_item.setBackground(QColor('#ccffcc'))
            elif 300 <= status < 400:
                s_item.setBackground(QColor('#ffffcc'))
            else:
                s_item.setBackground(QColor('#ffd9cc'))
        else:
            self._fail_count += 1
            s_item.setBackground(QColor('#ffcccc'))
        self._table.setItem(row, 1, s_item)

        # 耗时
        t_item = QTableWidgetItem(f"{r['time_ms']}ms")
        t_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._table.setItem(row, 2, t_item)

        # 大小
        size = r['size']
        if size >= 1024 * 1024:
            size_str = f"{size / 1024 / 1024:.1f}MB"
        elif size >= 1024:
            size_str = f"{size / 1024:.1f}KB"
        elif size > 0:
            size_str = f"{size}B"
        else:
            size_str = "-"
        sz_item = QTableWidgetItem(size_str)
        sz_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._table.setItem(row, 3, sz_item)

        # Server
        self._table.setItem(row, 4, QTableWidgetItem(r.get('server', '')))

        # Content-Type (简化)
        ct = r.get('content_type', '')
        if ';' in ct:
            ct = ct.split(';')[0].strip()
        self._table.setItem(row, 5, QTableWidgetItem(ct))

        # 错误
        self._table.setItem(row, 6, QTableWidgetItem(r['error']))

    def _on_progress(self, current, total):
        self._progress.setValue(current)
        self._result_label.setText(
            f"{current}/{total} | 成功 {self._ok_count} | 失败 {self._fail_count}")

    def _on_finished(self, summary):
        self._progress.setVisible(False)
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._table.setSortingEnabled(True)
        self._result_label.setText(
            f"共 {self._table.rowCount()} | "
            f"成功 {self._ok_count} | 失败 {self._fail_count}")
        self._status.setText(summary)

    def _clear_results(self):
        self._table.setRowCount(0)
        self._result_label.setText("")
        self._ok_count = 0
        self._fail_count = 0
        self._status.setText("已清空")

    def _copy_results(self):
        rows = self._table.rowCount()
        if rows == 0:
            return
        lines = [f"{'URL':<50}{'状态':<8}{'耗时':<10}{'大小':<10}{'Server':<20}{'错误'}"]
        lines.append('-' * 120)
        for i in range(rows):
            cells = []
            for c in range(self._table.columnCount()):
                item = self._table.item(i, c)
                cells.append(item.text() if item else '')
            url, status, time_ms, size, server, ct, error = cells
            lines.append(
                f"{url:<50}{status:<8}{time_ms:<10}{size:<10}{server:<20}{error}")
        QApplication.clipboard().setText('\n'.join(lines))
        self._status.setText("已复制到剪贴板")
