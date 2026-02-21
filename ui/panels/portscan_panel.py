# -*- coding: utf-8 -*-
"""端口扫描 & 服务探测面板 — 支持 SOCKS5/HTTP 代理、服务预设、Raw TCP 探测"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QGroupBox, QSpinBox, QApplication,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QProgressBar, QComboBox, QCheckBox, QTabWidget, QPlainTextEdit,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.port_scanner import (
    check_port, parse_ports, raw_tcp_probe,
    COMMON_PORTS, WELL_KNOWN_PORTS,
    SERVICE_PRESETS, SERVICE_PRESET_NAMES,
)


# ── 后台扫描线程 ─────────────────────────────────────────────
class ScanThread(QThread):
    result_ready = pyqtSignal(dict)
    progress = pyqtSignal(int, int)
    finished_all = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, host, ports, timeout, proxy=None):
        super().__init__()
        self.host = host
        self.ports = ports
        self.timeout = timeout
        self.proxy = proxy
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        total = len(self.ports)
        for i, port in enumerate(self.ports):
            if self._stop:
                break
            try:
                r = check_port(self.host, port, self.timeout, self.proxy)
                self.result_ready.emit(r)
            except Exception as e:
                self.error.emit(f"端口 {port}: {e}")
            self.progress.emit(i + 1, total)
        self.finished_all.emit()


# ── Raw TCP 探测线程 ──────────────────────────────────────────
class RawProbeThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, host, port, send_data, timeout, proxy=None):
        super().__init__()
        self.host = host
        self.port = port
        self.send_data = send_data
        self.timeout = timeout
        self.proxy = proxy

    def run(self):
        try:
            r = raw_tcp_probe(
                self.host, self.port, self.send_data,
                self.timeout, self.proxy)
            self.finished.emit(r)
        except Exception as e:
            self.error.emit(str(e))


# ══════════════════════════════════════════════════════════════
#  面板
# ══════════════════════════════════════════════════════════════
class PortScanPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mono = QFont("Consolas", 10)
        self._mono.setStyleHint(QFont.Monospace)
        self._scan_thread = None
        self._raw_thread = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(6)

        # 用 Tab 区分 "批量扫描" 和 "Raw TCP 探测"
        tabs = QTabWidget()
        tabs.addTab(self._build_scan_tab(), "批量端口扫描")
        tabs.addTab(self._build_raw_tab(),  "Raw TCP 探测")
        root.addWidget(tabs)

    # ══════════════════════════════════════════════════════════
    #  Tab 1: 批量扫描
    # ══════════════════════════════════════════════════════════
    def _build_scan_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ── 参数区 ────────────────────────────────────────────
        group = QGroupBox("扫描参数")
        g = QVBoxLayout(group)

        # 主机
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("主机:"))
        self._host = QLineEdit("127.0.0.1")
        self._host.setPlaceholderText("IP 或域名")
        r1.addWidget(self._host, stretch=1)
        g.addLayout(r1)

        # 端口 + 服务预设
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("端口:"))
        self._ports = QLineEdit("22,80,443,3306,6379,8080")
        self._ports.setPlaceholderText("80 / 80-90 / 22,80,443")
        r2.addWidget(self._ports, stretch=1)

        self._preset = QComboBox()
        self._preset.addItems(SERVICE_PRESET_NAMES)
        self._preset.setFixedWidth(160)
        self._preset.currentIndexChanged.connect(self._on_preset)
        r2.addWidget(self._preset)
        g.addLayout(r2)

        # 超时
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("超时:"))
        self._timeout = QSpinBox()
        self._timeout.setRange(1, 30)
        self._timeout.setValue(3)
        self._timeout.setSuffix(" 秒")
        self._timeout.setFixedWidth(80)
        r3.addWidget(self._timeout)
        r3.addStretch()
        g.addLayout(r3)

        layout.addWidget(group)

        # ── 代理设置 ──────────────────────────────────────────
        proxy_group = QGroupBox("代理设置（可选）")
        pg = QVBoxLayout(proxy_group)

        pr1 = QHBoxLayout()
        self._proxy_enable = QCheckBox("通过代理扫描")
        pr1.addWidget(self._proxy_enable)
        pr1.addStretch()
        pr1.addWidget(QLabel("类型:"))
        self._proxy_type = QComboBox()
        self._proxy_type.addItems(["SOCKS5", "HTTP"])
        self._proxy_type.setFixedWidth(100)
        pr1.addWidget(self._proxy_type)
        pg.addLayout(pr1)

        pr2 = QHBoxLayout()
        pr2.addWidget(QLabel("地址:"))
        self._proxy_host = QLineEdit("127.0.0.1")
        self._proxy_host.setFixedWidth(180)
        pr2.addWidget(self._proxy_host)
        pr2.addWidget(QLabel("端口:"))
        self._proxy_port = QSpinBox()
        self._proxy_port.setRange(1, 65535)
        self._proxy_port.setValue(1080)
        self._proxy_port.setFixedWidth(90)
        pr2.addWidget(self._proxy_port)
        pr2.addSpacing(12)
        pr2.addWidget(QLabel("用户:"))
        self._proxy_user = QLineEdit()
        self._proxy_user.setPlaceholderText("可选")
        self._proxy_user.setFixedWidth(100)
        pr2.addWidget(self._proxy_user)
        pr2.addWidget(QLabel("密码:"))
        self._proxy_pass = QLineEdit()
        self._proxy_pass.setEchoMode(QLineEdit.Password)
        self._proxy_pass.setPlaceholderText("可选")
        self._proxy_pass.setFixedWidth(100)
        pr2.addWidget(self._proxy_pass)
        pr2.addStretch()
        pg.addLayout(pr2)

        layout.addWidget(proxy_group)

        # ── 按钮行 ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._scan_btn = QPushButton("  开始扫描")
        self._scan_btn.setFixedHeight(34)
        self._scan_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:13px;border-radius:4px;padding:0 22px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}")
        self._scan_btn.clicked.connect(self._start_scan)
        btn_row.addWidget(self._scan_btn)

        self._stop_btn = QPushButton("停止")
        self._stop_btn.setFixedHeight(30)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_scan)
        btn_row.addWidget(self._stop_btn)

        self._clear_btn = QPushButton("清空")
        self._clear_btn.setFixedHeight(30)
        self._clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── 进度条 ────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setFixedHeight(18)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # ── 结果表格 ──────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("扫描结果:"))
        hdr.addStretch()
        self._result_label = QLabel("")
        hdr.addWidget(self._result_label)
        copy_btn = QPushButton("复制结果")
        copy_btn.setFixedWidth(90)
        copy_btn.clicked.connect(self._copy_results)
        hdr.addWidget(copy_btn)
        layout.addLayout(hdr)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["端口", "状态", "服务", "详情 / Banner", "知名服务"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 65)
        self._table.setColumnWidth(1, 60)
        self._table.setColumnWidth(2, 170)
        self._table.setColumnWidth(4, 100)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.setFont(self._mono)
        self._table.setSortingEnabled(True)
        layout.addWidget(self._table, stretch=1)

        self._status = QLabel("就绪")
        self._status.setStyleSheet("color:#666;font-size:11px")
        layout.addWidget(self._status)

        return w

    # ══════════════════════════════════════════════════════════
    #  Tab 2: Raw TCP 探测
    # ══════════════════════════════════════════════════════════
    def _build_raw_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        group = QGroupBox("Raw TCP 连接 — 自定义服务探测")
        g = QVBoxLayout(group)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("主机:"))
        self._raw_host = QLineEdit("127.0.0.1")
        self._raw_host.setFixedWidth(200)
        r1.addWidget(self._raw_host)
        r1.addWidget(QLabel("端口:"))
        self._raw_port = QSpinBox()
        self._raw_port.setRange(1, 65535)
        self._raw_port.setValue(8888)
        self._raw_port.setFixedWidth(90)
        r1.addWidget(self._raw_port)
        r1.addWidget(QLabel("超时:"))
        self._raw_timeout = QSpinBox()
        self._raw_timeout.setRange(1, 30)
        self._raw_timeout.setValue(5)
        self._raw_timeout.setSuffix(" 秒")
        self._raw_timeout.setFixedWidth(80)
        r1.addWidget(self._raw_timeout)
        r1.addStretch()
        g.addLayout(r1)

        r_proxy = QHBoxLayout()
        self._raw_proxy_enable = QCheckBox("通过代理")
        r_proxy.addWidget(self._raw_proxy_enable)
        r_proxy.addWidget(QLabel("(使用上方批量扫描 Tab 中设置的代理)"))
        r_proxy.addStretch()
        g.addLayout(r_proxy)

        g.addWidget(QLabel("发送数据（留空则只接收 Banner）:"))

        r_fmt = QHBoxLayout()
        self._raw_fmt = QComboBox()
        self._raw_fmt.addItems(["UTF-8 文本", "Hex 字节", "原始转义 (\\r\\n)"])
        self._raw_fmt.setFixedWidth(160)
        r_fmt.addWidget(self._raw_fmt)
        r_fmt.addStretch()
        g.addLayout(r_fmt)

        self._raw_send = QPlainTextEdit()
        self._raw_send.setFont(self._mono)
        self._raw_send.setPlaceholderText(
            "示例 (UTF-8):  GET / HTTP/1.1\\r\\nHost: 127.0.0.1\\r\\n\\r\\n\n"
            "示例 (Hex):    05 01 00\n"
            "留空: 仅连接并接收服务端主动发送的数据")
        self._raw_send.setMaximumHeight(90)
        g.addWidget(self._raw_send)

        r_btn = QHBoxLayout()
        self._raw_btn = QPushButton("  发送探测")
        self._raw_btn.setFixedHeight(34)
        self._raw_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:13px;border-radius:4px;padding:0 22px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}")
        self._raw_btn.clicked.connect(self._raw_probe)
        r_btn.addWidget(self._raw_btn)
        r_btn.addStretch()
        g.addLayout(r_btn)

        layout.addWidget(group)

        # 响应区
        layout.addWidget(QLabel("响应数据:"))

        resp_tabs = QTabWidget()
        self._raw_resp_text = QPlainTextEdit()
        self._raw_resp_text.setFont(self._mono)
        self._raw_resp_text.setReadOnly(True)
        resp_tabs.addTab(self._raw_resp_text, "文本")

        self._raw_resp_hex = QPlainTextEdit()
        self._raw_resp_hex.setFont(self._mono)
        self._raw_resp_hex.setReadOnly(True)
        resp_tabs.addTab(self._raw_resp_hex, "Hex")
        layout.addWidget(resp_tabs, stretch=1)

        self._raw_status = QLabel("就绪")
        self._raw_status.setStyleSheet("color:#666;font-size:11px")
        layout.addWidget(self._raw_status)

        return w

    # ══════════════════════════════════════════════════════════
    #  辅助: 获取代理配置
    # ══════════════════════════════════════════════════════════
    def _get_proxy(self):
        if not self._proxy_enable.isChecked():
            return None
        proxy = {
            'type': self._proxy_type.currentText(),
            'host': self._proxy_host.text().strip(),
            'port': self._proxy_port.value(),
        }
        user = self._proxy_user.text().strip()
        pwd = self._proxy_pass.text().strip()
        if user:
            proxy['username'] = user
            proxy['password'] = pwd
        return proxy

    # ══════════════════════════════════════════════════════════
    #  服务预设
    # ══════════════════════════════════════════════════════════
    def _on_preset(self, idx):
        if idx <= 0:
            return
        keys = list(SERVICE_PRESETS.keys())
        if idx - 1 < len(keys):
            ports = SERVICE_PRESETS[keys[idx - 1]][1]
            self._ports.setText(','.join(str(p) for p in ports))

    # ══════════════════════════════════════════════════════════
    #  批量扫描逻辑
    # ══════════════════════════════════════════════════════════
    def _start_scan(self):
        if self._scan_thread and self._scan_thread.isRunning():
            self._status.setText("扫描正在进行，请等待完成或点击停止")
            return
        host = self._host.text().strip()
        port_text = self._ports.text().strip()
        if not host:
            self._status.setText("请输入主机地址")
            return
        if not port_text:
            self._status.setText("请输入端口号")
            return
        try:
            ports = parse_ports(port_text)
        except ValueError as e:
            self._status.setText(str(e))
            return
        if not ports:
            self._status.setText("无有效端口")
            return

        self._table.setRowCount(0)
        self._table.setSortingEnabled(False)
        self._open_count = 0
        self._progress.setRange(0, len(ports))
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._scan_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._result_label.setText("")

        proxy = self._get_proxy()
        via = ''
        if proxy:
            via = f" (via {proxy['type']} {proxy['host']}:{proxy['port']})"
        self._status.setText(
            f"正在扫描 {host} 的 {len(ports)} 个端口{via} ...")

        self._scan_thread = ScanThread(
            host, ports, self._timeout.value(), proxy)
        self._scan_thread.result_ready.connect(self._on_result)
        self._scan_thread.progress.connect(self._on_progress)
        self._scan_thread.finished_all.connect(self._on_finished)
        self._scan_thread.error.connect(
            lambda msg: self._status.setText(msg))
        self._scan_thread.start()

    def _stop_scan(self):
        if self._scan_thread and self._scan_thread.isRunning():
            self._scan_thread.stop()
            self._status.setText("正在停止...")

    def _on_result(self, r):
        row = self._table.rowCount()
        self._table.insertRow(row)

        port_item = QTableWidgetItem()
        port_item.setData(Qt.DisplayRole, r['port'])
        port_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, 0, port_item)

        if r['open']:
            self._open_count += 1
            status_item = QTableWidgetItem("开放")
            status_item.setBackground(QColor('#ccffcc'))
            status_item.setTextAlignment(Qt.AlignCenter)
        else:
            status_item = QTableWidgetItem("关闭")
            status_item.setBackground(QColor('#ffcccc'))
            status_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, 1, status_item)

        self._table.setItem(row, 2, QTableWidgetItem(r['service']))

        detail = r['detail'] or r['banner']
        if detail:
            detail = detail.replace('\n', ' | ').strip()
            if len(detail) > 300:
                detail = detail[:300] + '...'
        self._table.setItem(row, 3, QTableWidgetItem(detail))

        known = WELL_KNOWN_PORTS.get(r['port'], '')
        self._table.setItem(row, 4, QTableWidgetItem(known))

    def _on_progress(self, current, total):
        self._progress.setValue(current)
        self._result_label.setText(
            f"进度 {current}/{total} | 开放 {self._open_count}")

    def _on_finished(self):
        self._progress.setVisible(False)
        self._scan_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._table.setSortingEnabled(True)
        total = self._table.rowCount()
        self._result_label.setText(
            f"共 {total} 个端口 | 开放 {self._open_count}")
        self._status.setText("扫描完成")

    # ══════════════════════════════════════════════════════════
    #  Raw TCP 探测
    # ══════════════════════════════════════════════════════════
    def _parse_send_data(self):
        """根据选择的格式解析用户输入为 bytes"""
        text = self._raw_send.toPlainText()
        if not text.strip():
            return b''

        fmt = self._raw_fmt.currentIndex()
        if fmt == 0:  # UTF-8
            return text.encode('utf-8')
        elif fmt == 1:  # Hex
            hex_str = text.replace(' ', '').replace('\n', '').replace('\r', '')
            return bytes.fromhex(hex_str)
        else:  # 原始转义
            return text.encode('utf-8').decode('unicode_escape').encode('latin-1')

    def _raw_probe(self):
        if self._raw_thread and self._raw_thread.isRunning():
            self._raw_status.setText("探测正在进行，请稍候")
            return
        host = self._raw_host.text().strip()
        port = self._raw_port.value()
        if not host:
            self._raw_status.setText("请输入主机地址")
            return

        try:
            send_data = self._parse_send_data()
        except Exception as e:
            self._raw_status.setText(f"数据格式错误: {e}")
            return

        proxy = None
        if self._raw_proxy_enable.isChecked():
            proxy = self._get_proxy()

        self._raw_status.setText(
            f"正在连接 {host}:{port} ...")
        self._raw_resp_text.clear()
        self._raw_resp_hex.clear()
        self._raw_btn.setEnabled(False)

        self._raw_thread = RawProbeThread(
            host, port, send_data,
            self._raw_timeout.value(), proxy)
        self._raw_thread.finished.connect(self._on_raw_result)
        self._raw_thread.error.connect(self._on_raw_error)
        self._raw_thread.start()

    def _on_raw_result(self, r):
        self._raw_btn.setEnabled(True)
        if not r['connected']:
            self._raw_resp_text.setPlainText(r['error'])
            self._raw_status.setText("连接失败")
            return

        self._raw_resp_text.setPlainText(r['recv_text'])
        self._raw_resp_hex.setPlainText(r['recv_hex'])

        recv_len = len(r['recv_bytes'])
        self._raw_status.setText(
            f"连接成功 | 发送 {r['sent']} 字节 | "
            f"接收 {recv_len} 字节"
            + (f" | 错误: {r['error']}" if r['error'] else ''))

    def _on_raw_error(self, msg):
        self._raw_btn.setEnabled(True)
        self._raw_status.setText(f"错误: {msg}")

    # ══════════════════════════════════════════════════════════
    #  工具
    # ══════════════════════════════════════════════════════════
    def _clear(self):
        self._table.setRowCount(0)
        self._result_label.setText("")
        self._status.setText("已清空")

    def _copy_results(self):
        rows = self._table.rowCount()
        if rows == 0:
            return
        lines = [f"{'端口':<8}{'状态':<8}{'服务':<25}{'详情'}"]
        lines.append('-' * 80)
        for i in range(rows):
            port = self._table.item(i, 0).text() if self._table.item(i, 0) else ''
            status = self._table.item(i, 1).text() if self._table.item(i, 1) else ''
            service = self._table.item(i, 2).text() if self._table.item(i, 2) else ''
            detail = self._table.item(i, 3).text() if self._table.item(i, 3) else ''
            lines.append(f"{port:<8}{status:<8}{service:<25}{detail}")
        QApplication.clipboard().setText('\n'.join(lines))
        self._status.setText("已复制到剪贴板")
