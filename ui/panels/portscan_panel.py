# -*- coding: utf-8 -*-
"""端口扫描面板 — 基于 nmap + Raw TCP/UDP 探测"""

import subprocess

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QSpinBox, QApplication,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QProgressBar, QComboBox, QCheckBox, QTabWidget, QPlainTextEdit,
    QSizePolicy, QFrame,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.port_scanner import (
    parse_ports, raw_tcp_probe, raw_udp_probe,
    parse_nmap_xml, build_nmap_cmd,
    WELL_KNOWN_PORTS, SERVICE_PRESETS, SERVICE_PRESET_NAMES,
    SCAN_TYPE_NAMES, SCAN_TYPE_FLAGS, TIMING_NAMES,
)
from core.nmap_finder import (
    is_nmap_available, download_nmap,
    NMAP_ZIP_URL, NMAP_VERSION, NMAP_BIN_DIR,
)


_BTN_PRIMARY = (
    "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
    "font-size:13px;border-radius:4px;padding:0 22px}"
    "QPushButton:hover{background:#106ebe}"
    "QPushButton:pressed{background:#005a9e}")

_BTN_PLAIN = (
    "QPushButton{border:1px solid #dfe2e8;border-radius:4px;"
    "padding:0 14px;background:#fff;color:#1e2433;font-size:12px}"
    "QPushButton:hover{background:#f0f2f5}")


# ── nmap 下载线程 ─────────────────────────────────────────────
class NmapDownloadThread(QThread):
    progress   = pyqtSignal(int, int)   # (downloaded_bytes, total_bytes)
    finished   = pyqtSignal(str)        # nmap_exe_path
    error      = pyqtSignal(str)

    def run(self):
        try:
            path = download_nmap(
                progress_cb=lambda d, t: self.progress.emit(d, t))
            self.finished.emit(path)
        except Exception as e:
            self.error.emit(str(e))


# ── nmap 扫描线程 ─────────────────────────────────────────────
class NmapScanThread(QThread):
    scan_done  = pyqtSignal(list, str)   # (results, cmd_str)
    scan_error = pyqtSignal(str)

    def __init__(self, host, ports, scan_flags, service_detect,
                 os_detect, script, timing, timeout):
        super().__init__()
        self._host           = host
        self._ports          = ports
        self._scan_flags     = scan_flags
        self._service_detect = service_detect
        self._os_detect      = os_detect
        self._script         = script
        self._timing         = timing
        self._timeout        = timeout
        self._proc           = None

    def stop(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass

    def run(self):
        cmd = build_nmap_cmd(
            self._host, self._ports, self._scan_flags,
            self._service_detect, self._os_detect,
            self._script, self._timing,
        )
        cmd_str = ' '.join(cmd)
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = self._proc.communicate(timeout=self._timeout)
            if self._proc.returncode not in (0, 1):
                err = stderr.decode('utf-8', errors='replace')
                self.scan_error.emit(
                    f"nmap 错误 (exit {self._proc.returncode}):\n{err}")
                return
            results = parse_nmap_xml(stdout.decode('utf-8', errors='replace'))
            self.scan_done.emit(results, cmd_str)
        except subprocess.TimeoutExpired:
            if self._proc:
                self._proc.kill()
            self.scan_error.emit(f"nmap 扫描超时 ({self._timeout}秒)")
        except FileNotFoundError:
            self.scan_error.emit(
                "找不到 nmap，请先安装 nmap。\n"
                "下载地址: https://nmap.org/download")
        except Exception as e:
            self.scan_error.emit(str(e))


# ── Raw TCP 探测线程 ──────────────────────────────────────────
class RawTcpThread(QThread):
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(self, host, port, send_data, timeout, proxy=None):
        super().__init__()
        self.host      = host
        self.port      = port
        self.send_data = send_data
        self.timeout   = timeout
        self.proxy     = proxy

    def run(self):
        try:
            r = raw_tcp_probe(self.host, self.port, self.send_data,
                              self.timeout, self.proxy)
            self.finished.emit(r)
        except Exception as e:
            self.error.emit(str(e))


# ── Raw UDP 探测线程 ──────────────────────────────────────────
class RawUdpThread(QThread):
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(self, host, port, send_data, timeout):
        super().__init__()
        self.host      = host
        self.port      = port
        self.send_data = send_data
        self.timeout   = timeout

    def run(self):
        try:
            r = raw_udp_probe(self.host, self.port, self.send_data,
                              self.timeout)
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
        self._scan_thread     = None
        self._raw_tcp_thread  = None
        self._raw_udp_thread  = None
        self._download_thread = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(6)

        tabs = QTabWidget()
        tabs.addTab(self._build_scan_tab(),    "nmap 端口扫描")
        tabs.addTab(self._build_raw_tcp_tab(), "Raw TCP 探测")
        tabs.addTab(self._build_raw_udp_tab(), "Raw UDP 探测")
        root.addWidget(tabs)

    # ══════════════════════════════════════════════════════════
    #  Tab 1: nmap 批量扫描
    # ══════════════════════════════════════════════════════════
    def _build_scan_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ── nmap 状态横幅 ─────────────────────────────────────
        self._nmap_banner = QFrame()
        self._nmap_banner.setStyleSheet(
            "QFrame{background:#fff3cd;border:1px solid #ffc107;"
            "border-radius:4px;padding:2px;}")
        banner_row = QHBoxLayout(self._nmap_banner)
        banner_row.setContentsMargins(8, 4, 8, 4)
        self._nmap_banner_lbl = QLabel(
            f"nmap 未找到 — 需要下载 nmap {NMAP_VERSION} 才能使用扫描功能")
        self._nmap_banner_lbl.setStyleSheet("color:#856404;font-size:11px;")
        banner_row.addWidget(self._nmap_banner_lbl, stretch=1)

        self._dl_btn = QPushButton(f"⬇ 下载 nmap {NMAP_VERSION}")
        self._dl_btn.setFixedHeight(26)
        self._dl_btn.setStyleSheet(
            "QPushButton{background:#ffc107;color:#333;border-radius:3px;"
            "padding:0 10px;font-size:12px;font-weight:bold;}"
            "QPushButton:hover{background:#ffca2c}"
            "QPushButton:disabled{background:#e0c060;color:#888}")
        self._dl_btn.clicked.connect(self._start_download)
        banner_row.addWidget(self._dl_btn)

        self._dl_progress = QProgressBar()
        self._dl_progress.setFixedHeight(18)
        self._dl_progress.setFixedWidth(160)
        self._dl_progress.setVisible(False)
        banner_row.addWidget(self._dl_progress)

        layout.addWidget(self._nmap_banner)
        self._nmap_banner.setVisible(not is_nmap_available())

        # ── 基础参数 ──────────────────────────────────────────
        param_group = QGroupBox("扫描参数")
        pg = QVBoxLayout(param_group)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("主机:"))
        self._host = QLineEdit("127.0.0.1")
        self._host.setPlaceholderText("IP 或域名")
        r1.addWidget(self._host, stretch=1)
        pg.addLayout(r1)

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
        pg.addLayout(r2)

        layout.addWidget(param_group)

        # ── nmap 选项 ─────────────────────────────────────────
        opt_group = QGroupBox("nmap 选项")
        og = QVBoxLayout(opt_group)

        o1 = QHBoxLayout()
        o1.addWidget(QLabel("扫描类型:"))
        self._scan_type = QComboBox()
        self._scan_type.addItems(SCAN_TYPE_NAMES)
        self._scan_type.setFixedWidth(280)
        o1.addWidget(self._scan_type)
        o1.addSpacing(16)
        o1.addWidget(QLabel("时序:"))
        self._timing = QComboBox()
        self._timing.addItems(TIMING_NAMES)
        self._timing.setCurrentIndex(4)     # -T4
        self._timing.setFixedWidth(180)
        o1.addWidget(self._timing)
        o1.addSpacing(16)
        o1.addWidget(QLabel("超时:"))
        self._timeout = QSpinBox()
        self._timeout.setRange(10, 3600)
        self._timeout.setValue(120)
        self._timeout.setSuffix(" 秒")
        self._timeout.setFixedWidth(90)
        o1.addWidget(self._timeout)
        o1.addStretch()
        og.addLayout(o1)

        o2 = QHBoxLayout()
        self._svc_detect = QCheckBox("服务版本检测 (-sV)")
        self._os_detect  = QCheckBox("OS 检测 (-O)  [需 root/Npcap]")
        self._script     = QCheckBox("默认脚本 (-sC)")
        o2.addWidget(self._svc_detect)
        o2.addSpacing(12)
        o2.addWidget(self._os_detect)
        o2.addSpacing(12)
        o2.addWidget(self._script)
        o2.addStretch()
        og.addLayout(o2)

        # nmap 命令预览
        o3 = QHBoxLayout()
        o3.addWidget(QLabel("命令预览:"))
        self._cmd_preview = QLineEdit()
        self._cmd_preview.setReadOnly(True)
        self._cmd_preview.setFont(self._mono)
        self._cmd_preview.setStyleSheet("background:#f5f6fa;color:#333;")
        o3.addWidget(self._cmd_preview, stretch=1)
        og.addLayout(o3)

        # 当选项改变时刷新命令预览
        self._host.textChanged.connect(self._refresh_cmd_preview)
        self._ports.textChanged.connect(self._refresh_cmd_preview)
        self._scan_type.currentIndexChanged.connect(self._refresh_cmd_preview)
        self._timing.currentIndexChanged.connect(self._refresh_cmd_preview)
        self._svc_detect.stateChanged.connect(self._refresh_cmd_preview)
        self._os_detect.stateChanged.connect(self._refresh_cmd_preview)
        self._script.stateChanged.connect(self._refresh_cmd_preview)
        self._refresh_cmd_preview()

        layout.addWidget(opt_group)

        # ── 按钮行 ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._scan_btn = QPushButton("▶  开始扫描")
        self._scan_btn.setFixedHeight(34)
        self._scan_btn.setStyleSheet(_BTN_PRIMARY)
        self._scan_btn.clicked.connect(self._start_scan)
        btn_row.addWidget(self._scan_btn)

        self._stop_btn = QPushButton("■ 停止")
        self._stop_btn.setFixedHeight(30)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_scan)
        btn_row.addWidget(self._stop_btn)

        self._clear_btn = QPushButton("清空")
        self._clear_btn.setFixedHeight(30)
        self._clear_btn.setStyleSheet(_BTN_PLAIN)
        self._clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch()

        self._result_label = QLabel("")
        btn_row.addWidget(self._result_label)

        copy_btn = QPushButton("复制结果")
        copy_btn.setFixedWidth(90)
        copy_btn.setStyleSheet(_BTN_PLAIN)
        copy_btn.clicked.connect(self._copy_results)
        btn_row.addWidget(copy_btn)
        layout.addLayout(btn_row)

        # ── 进度条 ────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setFixedHeight(18)
        self._progress.setRange(0, 0)   # 不定式
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # ── 结果表格 ──────────────────────────────────────────
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["端口", "协议", "状态", "原因", "服务", "版本", "知名服务"])
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        h.setSectionResizeMode(1, QHeaderView.Fixed)
        h.setSectionResizeMode(2, QHeaderView.Fixed)
        h.setSectionResizeMode(3, QHeaderView.Fixed)
        h.setSectionResizeMode(4, QHeaderView.Interactive)
        h.setSectionResizeMode(5, QHeaderView.Stretch)
        h.setSectionResizeMode(6, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 65)
        self._table.setColumnWidth(1, 55)
        self._table.setColumnWidth(2, 80)
        self._table.setColumnWidth(3, 100)
        self._table.setColumnWidth(4, 120)
        self._table.setColumnWidth(6, 120)
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
    def _build_raw_tcp_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        group = QGroupBox("Raw TCP 连接 — 自定义服务探测")
        g = QVBoxLayout(group)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("主机:"))
        self._tcp_host = QLineEdit("127.0.0.1")
        self._tcp_host.setFixedWidth(200)
        r1.addWidget(self._tcp_host)
        r1.addWidget(QLabel("端口:"))
        self._tcp_port = QSpinBox()
        self._tcp_port.setRange(1, 65535)
        self._tcp_port.setValue(8888)
        self._tcp_port.setFixedWidth(90)
        r1.addWidget(self._tcp_port)
        r1.addWidget(QLabel("超时:"))
        self._tcp_timeout = QSpinBox()
        self._tcp_timeout.setRange(1, 60)
        self._tcp_timeout.setValue(5)
        self._tcp_timeout.setSuffix(" 秒")
        self._tcp_timeout.setFixedWidth(80)
        r1.addWidget(self._tcp_timeout)
        r1.addStretch()
        g.addLayout(r1)

        g.addWidget(QLabel("发送数据（留空则只接收 Banner）:"))

        r_fmt = QHBoxLayout()
        self._tcp_fmt = QComboBox()
        self._tcp_fmt.addItems(["UTF-8 文本", "Hex 字节", r"原始转义 (\r\n)"])
        self._tcp_fmt.setFixedWidth(160)
        r_fmt.addWidget(self._tcp_fmt)
        r_fmt.addStretch()
        g.addLayout(r_fmt)

        self._tcp_send = QPlainTextEdit()
        self._tcp_send.setFont(self._mono)
        self._tcp_send.setPlaceholderText(
            "示例 (UTF-8):  GET / HTTP/1.1\\r\\nHost: 127.0.0.1\\r\\n\\r\\n\n"
            "示例 (Hex):    05 01 00\n"
            "留空: 仅连接并接收服务端主动发送的数据")
        self._tcp_send.setMaximumHeight(90)
        g.addWidget(self._tcp_send)

        r_btn = QHBoxLayout()
        self._tcp_btn = QPushButton("▶  发送探测")
        self._tcp_btn.setFixedHeight(34)
        self._tcp_btn.setStyleSheet(_BTN_PRIMARY)
        self._tcp_btn.clicked.connect(self._tcp_probe)
        r_btn.addWidget(self._tcp_btn)
        r_btn.addStretch()
        g.addLayout(r_btn)

        layout.addWidget(group)

        layout.addWidget(QLabel("响应数据:"))
        resp_tabs = QTabWidget()
        self._tcp_resp_text = QPlainTextEdit()
        self._tcp_resp_text.setFont(self._mono)
        self._tcp_resp_text.setReadOnly(True)
        resp_tabs.addTab(self._tcp_resp_text, "文本")

        self._tcp_resp_hex = QPlainTextEdit()
        self._tcp_resp_hex.setFont(self._mono)
        self._tcp_resp_hex.setReadOnly(True)
        resp_tabs.addTab(self._tcp_resp_hex, "Hex")
        layout.addWidget(resp_tabs, stretch=1)

        self._tcp_status = QLabel("就绪")
        self._tcp_status.setStyleSheet("color:#666;font-size:11px")
        layout.addWidget(self._tcp_status)

        return w

    # ══════════════════════════════════════════════════════════
    #  Tab 3: Raw UDP 探测
    # ══════════════════════════════════════════════════════════
    def _build_raw_udp_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        group = QGroupBox("Raw UDP 探测 — 发送 UDP 数据包并等待响应")
        g = QVBoxLayout(group)

        hint = QLabel(
            "UDP 无连接，状态含义:  "
            "open = 收到 UDP 响应；  "
            "open|filtered = 超时（可能开放或防火墙过滤）；  "
            "closed = 收到 ICMP 不可达")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6b7a8d;font-size:11px;")
        g.addWidget(hint)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("主机:"))
        self._udp_host = QLineEdit("127.0.0.1")
        self._udp_host.setFixedWidth(200)
        r1.addWidget(self._udp_host)
        r1.addWidget(QLabel("端口:"))
        self._udp_port = QSpinBox()
        self._udp_port.setRange(1, 65535)
        self._udp_port.setValue(53)
        self._udp_port.setFixedWidth(90)
        r1.addWidget(self._udp_port)
        r1.addWidget(QLabel("超时:"))
        self._udp_timeout = QSpinBox()
        self._udp_timeout.setRange(1, 60)
        self._udp_timeout.setValue(5)
        self._udp_timeout.setSuffix(" 秒")
        self._udp_timeout.setFixedWidth(80)
        r1.addWidget(self._udp_timeout)
        r1.addStretch()
        g.addLayout(r1)

        g.addWidget(QLabel("发送数据（留空则发送空 UDP 包）:"))

        r_fmt = QHBoxLayout()
        self._udp_fmt = QComboBox()
        self._udp_fmt.addItems(["UTF-8 文本", "Hex 字节", r"原始转义 (\r\n)"])
        self._udp_fmt.setFixedWidth(160)
        r_fmt.addWidget(self._udp_fmt)

        udp_presets = QComboBox()
        udp_presets.addItems(["快捷填充…", "DNS 查询 (A记录 example.com)",
                               "NTP 版本请求", "空包（探测响应）"])
        udp_presets.setFixedWidth(220)
        udp_presets.currentIndexChanged.connect(self._udp_preset)
        r_fmt.addWidget(udp_presets)
        r_fmt.addStretch()
        g.addLayout(r_fmt)

        self._udp_send = QPlainTextEdit()
        self._udp_send.setFont(self._mono)
        self._udp_send.setPlaceholderText(
            "示例 (Hex，DNS 查询): "
            "00 01 01 00 00 01 00 00 00 00 00 00 07 65 78 61 6d 70 6c 65 03 63 6f 6d 00 00 01 00 01\n"
            "留空: 发送空 UDP 包（适合探测是否有任何响应）")
        self._udp_send.setMaximumHeight(90)
        g.addWidget(self._udp_send)

        r_btn = QHBoxLayout()
        self._udp_btn = QPushButton("▶  发送 UDP 探测")
        self._udp_btn.setFixedHeight(34)
        self._udp_btn.setStyleSheet(_BTN_PRIMARY)
        self._udp_btn.clicked.connect(self._udp_probe)
        r_btn.addWidget(self._udp_btn)
        r_btn.addStretch()
        g.addLayout(r_btn)

        layout.addWidget(group)

        layout.addWidget(QLabel("响应数据:"))
        resp_tabs = QTabWidget()
        self._udp_resp_text = QPlainTextEdit()
        self._udp_resp_text.setFont(self._mono)
        self._udp_resp_text.setReadOnly(True)
        resp_tabs.addTab(self._udp_resp_text, "文本")

        self._udp_resp_hex = QPlainTextEdit()
        self._udp_resp_hex.setFont(self._mono)
        self._udp_resp_hex.setReadOnly(True)
        resp_tabs.addTab(self._udp_resp_hex, "Hex")
        layout.addWidget(resp_tabs, stretch=1)

        self._udp_status = QLabel("就绪")
        self._udp_status.setStyleSheet("color:#666;font-size:11px")
        layout.addWidget(self._udp_status)

        return w

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
    #  命令预览刷新
    # ══════════════════════════════════════════════════════════
    def _refresh_cmd_preview(self):
        host  = self._host.text().strip() or '<host>'
        ports = self._ports.text().strip() or '1-1000'
        idx   = self._scan_type.currentIndex()
        flags = SCAN_TYPE_FLAGS[idx] if idx < len(SCAN_TYPE_FLAGS) else ['-sT']
        timing = self._timing.currentIndex()
        try:
            port_list = parse_ports(ports) if ports != '1-1000' else []
        except Exception:
            port_list = []
        display_ports = ports if not port_list else ports
        cmd = build_nmap_cmd(
            host, display_ports, flags,
            self._svc_detect.isChecked(),
            self._os_detect.isChecked(),
            self._script.isChecked(),
            timing,
        )
        self._cmd_preview.setText(' '.join(cmd))

    # ══════════════════════════════════════════════════════════
    #  nmap 下载逻辑
    # ══════════════════════════════════════════════════════════
    def _start_download(self):
        if self._download_thread and self._download_thread.isRunning():
            return
        self._dl_btn.setEnabled(False)
        self._dl_progress.setRange(0, 100)
        self._dl_progress.setValue(0)
        self._dl_progress.setVisible(True)
        self._nmap_banner_lbl.setText(
            f"正在下载 nmap {NMAP_VERSION}，请稍候… (来源: {NMAP_ZIP_URL})")

        self._download_thread = NmapDownloadThread()
        self._download_thread.progress.connect(self._on_dl_progress)
        self._download_thread.finished.connect(self._on_dl_finished)
        self._download_thread.error.connect(self._on_dl_error)
        self._download_thread.start()

    def _on_dl_progress(self, downloaded, total):
        if total > 0:
            pct = int(downloaded * 100 / total)
            self._dl_progress.setValue(pct)
            mb_d = downloaded / 1_048_576
            mb_t = total      / 1_048_576
            self._nmap_banner_lbl.setText(
                f"下载中… {mb_d:.1f} / {mb_t:.1f} MB")

    def _on_dl_finished(self, exe_path):
        self._dl_progress.setVisible(False)
        self._nmap_banner.setVisible(False)
        self._status.setText(
            f"nmap {NMAP_VERSION} 下载完成！路径: {exe_path}")

    def _on_dl_error(self, msg):
        self._dl_btn.setEnabled(True)
        self._dl_progress.setVisible(False)
        self._nmap_banner_lbl.setText(f"下载失败: {msg}  — 点击重试")

    # ══════════════════════════════════════════════════════════
    #  nmap 扫描逻辑
    # ══════════════════════════════════════════════════════════
    def _start_scan(self):
        if self._scan_thread and self._scan_thread.isRunning():
            self._status.setText("扫描正在进行，请等待完成或点击停止")
            return

        if not is_nmap_available():
            self._status.setText("未找到 nmap，请先安装: https://nmap.org/download")
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
        self._progress.setVisible(True)
        self._scan_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._result_label.setText("扫描中…")

        idx   = self._scan_type.currentIndex()
        flags = SCAN_TYPE_FLAGS[idx] if idx < len(SCAN_TYPE_FLAGS) else ['-sT']
        timing = self._timing.currentIndex()

        self._status.setText(
            f"正在扫描 {host} ({len(ports)} 个端口) — 请稍候…")

        self._scan_thread = NmapScanThread(
            host, ports, flags,
            self._svc_detect.isChecked(),
            self._os_detect.isChecked(),
            self._script.isChecked(),
            timing,
            self._timeout.value(),
        )
        self._scan_thread.scan_done.connect(self._on_scan_done)
        self._scan_thread.scan_error.connect(self._on_scan_error)
        self._scan_thread.start()

    def _stop_scan(self):
        if self._scan_thread and self._scan_thread.isRunning():
            self._scan_thread.stop()
            self._status.setText("正在停止…")

    def _on_scan_done(self, results, cmd_str):
        self._progress.setVisible(False)
        self._scan_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

        # 填充表格
        self._table.setRowCount(len(results))
        open_cnt = 0
        for row, r in enumerate(results):
            port_item = QTableWidgetItem()
            port_item.setData(Qt.DisplayRole, r['port'])
            port_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 0, port_item)

            proto_item = QTableWidgetItem(r['protocol'])
            proto_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 1, proto_item)

            state = r['state']
            s_item = QTableWidgetItem(state)
            s_item.setTextAlignment(Qt.AlignCenter)
            if state == 'open':
                open_cnt += 1
                s_item.setBackground(QColor('#ccffcc'))
            elif state == 'filtered':
                s_item.setBackground(QColor('#ffffcc'))
            elif state == 'closed':
                s_item.setBackground(QColor('#ffcccc'))
            self._table.setItem(row, 2, s_item)

            self._table.setItem(row, 3, QTableWidgetItem(r['reason']))
            self._table.setItem(row, 4, QTableWidgetItem(r['service']))
            self._table.setItem(row, 5, QTableWidgetItem(r['version']))
            known = WELL_KNOWN_PORTS.get(r['port'], '')
            self._table.setItem(row, 6, QTableWidgetItem(known))

        self._table.setSortingEnabled(True)
        self._result_label.setText(
            f"共 {len(results)} 个端口 | 开放 {open_cnt}")
        self._status.setText(f"扫描完成  |  {cmd_str}")

    def _on_scan_error(self, msg):
        self._progress.setVisible(False)
        self._scan_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._status.setText(f"错误: {msg}")
        self._result_label.setText("")

    # ══════════════════════════════════════════════════════════
    #  Raw TCP 逻辑
    # ══════════════════════════════════════════════════════════
    def _parse_tcp_data(self):
        text = self._tcp_send.toPlainText()
        if not text.strip():
            return b''
        fmt = self._tcp_fmt.currentIndex()
        if fmt == 0:
            return text.encode('utf-8')
        elif fmt == 1:
            hex_str = text.replace(' ', '').replace('\n', '').replace('\r', '')
            return bytes.fromhex(hex_str)
        else:
            return text.encode('utf-8').decode('unicode_escape').encode('latin-1')

    def _tcp_probe(self):
        if self._raw_tcp_thread and self._raw_tcp_thread.isRunning():
            self._tcp_status.setText("探测正在进行，请稍候")
            return
        host = self._tcp_host.text().strip()
        port = self._tcp_port.value()
        if not host:
            self._tcp_status.setText("请输入主机地址")
            return
        try:
            send_data = self._parse_tcp_data()
        except Exception as e:
            self._tcp_status.setText(f"数据格式错误: {e}")
            return

        self._tcp_status.setText(f"正在连接 {host}:{port} …")
        self._tcp_resp_text.clear()
        self._tcp_resp_hex.clear()
        self._tcp_btn.setEnabled(False)

        self._raw_tcp_thread = RawTcpThread(
            host, port, send_data, self._tcp_timeout.value())
        self._raw_tcp_thread.finished.connect(self._on_tcp_result)
        self._raw_tcp_thread.error.connect(self._on_tcp_error)
        self._raw_tcp_thread.start()

    def _on_tcp_result(self, r):
        self._tcp_btn.setEnabled(True)
        if not r['connected']:
            self._tcp_resp_text.setPlainText(r['error'])
            self._tcp_status.setText("连接失败")
            return
        self._tcp_resp_text.setPlainText(r['recv_text'])
        self._tcp_resp_hex.setPlainText(r['recv_hex'])
        recv_len = len(r['recv_bytes'])
        self._tcp_status.setText(
            f"连接成功 | 发送 {r['sent']} 字节 | 接收 {recv_len} 字节"
            + (f" | {r['error']}" if r['error'] else ''))

    def _on_tcp_error(self, msg):
        self._tcp_btn.setEnabled(True)
        self._tcp_status.setText(f"错误: {msg}")

    # ══════════════════════════════════════════════════════════
    #  Raw UDP 逻辑
    # ══════════════════════════════════════════════════════════
    _UDP_PRESETS = {
        1: ("16", "00 01 01 00 00 01 00 00 00 00 00 00 "
                   "07 65 78 61 6d 70 6c 65 03 63 6f 6d 00 00 01 00 01"),  # DNS
        2: ("53", "1b 00 00 00 00 00 00 00 00 00 00 00 "
                   "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"),  # NTP
        3: ("",  ""),  # empty
    }

    def _udp_preset(self, idx):
        if idx == 0:
            return
        if idx == 1:
            self._udp_port.setValue(53)
            self._udp_fmt.setCurrentIndex(1)  # Hex
            self._udp_send.setPlainText(
                "00 01 01 00 00 01 00 00 00 00 00 00 "
                "07 65 78 61 6d 70 6c 65 03 63 6f 6d 00 00 01 00 01")
        elif idx == 2:
            self._udp_port.setValue(123)
            self._udp_fmt.setCurrentIndex(1)  # Hex
            self._udp_send.setPlainText(
                "1b 00 00 00 00 00 00 00 00 00 00 00 "
                "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
        elif idx == 3:
            self._udp_send.clear()

    def _parse_udp_data(self):
        text = self._udp_send.toPlainText()
        if not text.strip():
            return b''
        fmt = self._udp_fmt.currentIndex()
        if fmt == 0:
            return text.encode('utf-8')
        elif fmt == 1:
            hex_str = text.replace(' ', '').replace('\n', '').replace('\r', '')
            return bytes.fromhex(hex_str)
        else:
            return text.encode('utf-8').decode('unicode_escape').encode('latin-1')

    def _udp_probe(self):
        if self._raw_udp_thread and self._raw_udp_thread.isRunning():
            self._udp_status.setText("探测正在进行，请稍候")
            return
        host = self._udp_host.text().strip()
        port = self._udp_port.value()
        if not host:
            self._udp_status.setText("请输入主机地址")
            return
        try:
            send_data = self._parse_udp_data()
        except Exception as e:
            self._udp_status.setText(f"数据格式错误: {e}")
            return

        self._udp_status.setText(f"正在发送 UDP 包到 {host}:{port} …")
        self._udp_resp_text.clear()
        self._udp_resp_hex.clear()
        self._udp_btn.setEnabled(False)

        self._raw_udp_thread = RawUdpThread(
            host, port, send_data, self._udp_timeout.value())
        self._raw_udp_thread.finished.connect(self._on_udp_result)
        self._raw_udp_thread.error.connect(self._on_udp_error)
        self._raw_udp_thread.start()

    def _on_udp_result(self, r):
        self._udp_btn.setEnabled(True)
        state = r['state']
        if state == 'open':
            self._udp_resp_text.setPlainText(r['recv_text'])
            self._udp_resp_hex.setPlainText(r['recv_hex'])
            self._udp_status.setText(
                f"状态: open | 发送 {r['sent']} 字节 | 接收 {len(r['recv_bytes'])} 字节")
        elif state == 'open|filtered':
            self._udp_resp_text.setPlainText("（无响应）")
            self._udp_status.setText(f"状态: open|filtered — {r['error']}")
        elif state == 'closed':
            self._udp_resp_text.setPlainText("（端口已关闭）")
            self._udp_status.setText(f"状态: closed — {r['error']}")
        else:
            self._udp_resp_text.setPlainText(r['error'])
            self._udp_status.setText(f"状态: error — {r['error']}")

    def _on_udp_error(self, msg):
        self._udp_btn.setEnabled(True)
        self._udp_status.setText(f"错误: {msg}")

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
        headers = ["端口", "协议", "状态", "原因", "服务", "版本", "知名服务"]
        lines = ['\t'.join(headers)]
        for i in range(rows):
            cells = []
            for c in range(self._table.columnCount()):
                item = self._table.item(i, c)
                cells.append(item.text() if item else '')
            lines.append('\t'.join(cells))
        QApplication.clipboard().setText('\n'.join(lines))
        self._status.setText("已复制到剪贴板")
