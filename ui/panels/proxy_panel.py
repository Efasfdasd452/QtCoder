# -*- coding: utf-8 -*-
"""代理测试面板 — 双引擎

Tab 1: URL 批量测试  (aiohttp 异步并发 — 真实 HTTP 请求，支持 SOCKS5)
Tab 2: 端口连通性   (nmap --proxies — 精准 open/filtered/closed，支持 HTTP/SOCKS4)
"""

import asyncio
import subprocess

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QGroupBox, QComboBox, QSpinBox,
    QApplication, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QProgressBar, QSplitter, QMessageBox,
    QTabWidget, QCheckBox, QFrame,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.proxy_tester import (
    build_proxy_url, batch_test,
    build_nmap_proxy_url, _parse_nmap_xml,
)
from core.nmap_finder import (
    get_nmap_exe, is_nmap_available,
    download_nmap, NMAP_VERSION, NMAP_ZIP_URL,
)


# ── nmap 下载线程 ─────────────────────────────────────────────
class NmapDownloadThread(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def run(self):
        try:
            path = download_nmap(
                progress_cb=lambda d, t: self.progress.emit(d, t))
            self.finished.emit(path)
        except Exception as e:
            self.error.emit(str(e))
from core.port_scanner import (
    parse_ports, SERVICE_PRESETS, SERVICE_PRESET_NAMES, WELL_KNOWN_PORTS,
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


# ══════════════════════════════════════════════════════════════
#  线程: aiohttp 异步 URL 批量测试
# ══════════════════════════════════════════════════════════════
class AiohttpTestThread(QThread):
    result_ready = pyqtSignal(dict)
    progress     = pyqtSignal(int, int)
    finished_all = pyqtSignal(str)
    error        = pyqtSignal(str)

    def __init__(self, urls, proxy_url, timeout, concurrency):
        super().__init__()
        self.urls        = urls
        self.proxy_url   = proxy_url
        self.timeout     = timeout
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
                    proxy_url    = self.proxy_url,
                    timeout      = self.timeout,
                    concurrency  = self.concurrency,
                    stop_event   = self._stop_event,
                    on_result    = lambda r: self.result_ready.emit(r),
                    on_progress  = lambda d, t: self.progress.emit(d, t),
                )
            )
            loop.close()

            ok   = sum(1 for r in results if r and r.get('ok'))
            fail = len(results) - ok
            self.finished_all.emit(f"完成: {ok} 成功, {fail} 失败")
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")
            self.finished_all.emit("出错终止")


# ══════════════════════════════════════════════════════════════
#  线程: nmap 端口连通性检测
# ══════════════════════════════════════════════════════════════
class NmapProxyThread(QThread):
    scan_done  = pyqtSignal(list, str, float)
    scan_error = pyqtSignal(str)

    def __init__(self, target_host, ports, timing, timeout, proxy_url=None):
        super().__init__()
        self._proxy_url   = proxy_url   # None = 直连，不加 --proxies
        self._target_host = target_host
        self._ports       = ports
        self._timing      = timing
        self._timeout     = timeout
        self._proc        = None

    def stop(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass

    def run(self):
        import time
        nmap_exe = get_nmap_exe() or 'nmap'
        if isinstance(self._ports, (list, tuple)):
            port_str = ','.join(str(p) for p in self._ports)
        else:
            port_str = str(self._ports)

        cmd = [nmap_exe, '-sT']
        if self._proxy_url:
            cmd += ['--proxies', self._proxy_url]
        cmd += ['-p', port_str, '-oX', '-', f'-T{self._timing}', self._target_host]

        cmd_str = ' '.join(cmd)
        start = time.monotonic()
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = self._proc.communicate(timeout=self._timeout)
            elapsed = time.monotonic() - start

            if self._proc.returncode not in (0, 1):
                err = stderr.decode('utf-8', errors='replace')
                self.scan_error.emit(
                    f"nmap 错误 (exit {self._proc.returncode}):\n{err}")
                return

            results = _parse_nmap_xml(stdout.decode('utf-8', errors='replace'))
            self.scan_done.emit(results, cmd_str, elapsed)

        except subprocess.TimeoutExpired:
            if self._proc:
                self._proc.kill()
            self.scan_error.emit(f"nmap 超时（{self._timeout} 秒）")
        except FileNotFoundError:
            self.scan_error.emit("找不到 nmap 可执行文件")
        except Exception as e:
            self.scan_error.emit(str(e))


# ══════════════════════════════════════════════════════════════
#  面板
# ══════════════════════════════════════════════════════════════
class ProxyTestPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mono = QFont("Consolas", 10)
        self._mono.setStyleHint(QFont.Monospace)
        self._aiohttp_thread = None
        self._nmap_thread    = None
        self._dl_thread      = None
        self._ok_count = self._fail_count = 0
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(6)

        # ── 代理设置（共用）────────────────────────────────────
        proxy_group = QGroupBox("代理设置（两个模式共用）")
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

        # ── 两个模式的 Tab ────────────────────────────────────
        tabs = QTabWidget()
        tabs.addTab(self._build_url_tab(),  "URL 批量测试  (aiohttp 异步)")
        tabs.addTab(self._build_nmap_tab(), "端口连通性  (nmap 精准)")
        root.addWidget(tabs, stretch=1)

    # ══════════════════════════════════════════════════════════
    #  Tab 1: aiohttp URL 批量测试
    # ══════════════════════════════════════════════════════════
    def _build_url_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        hint = QLabel(
            "真实发出 HTTP/HTTPS 请求，返回状态码、耗时、大小等。"
            "支持 HTTP / SOCKS4 / SOCKS5 代理，高并发批量测速。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6b7a8d;font-size:11px;")
        root.addWidget(hint)

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
            "https://httpbin.org/ip")
        self._url_input.textChanged.connect(self._update_url_count)
        url_l.addWidget(self._url_input)
        splitter.addWidget(url_w)

        # 结果表格
        res_w = QWidget()
        res_l = QVBoxLayout(res_w)
        res_l.setContentsMargins(0, 0, 0, 0)
        res_hdr = QHBoxLayout()
        res_hdr.addWidget(QLabel("测试结果:"))
        res_hdr.addStretch()
        self._url_result_label = QLabel("")
        res_hdr.addWidget(self._url_result_label)
        copy_btn = QPushButton("复制结果")
        copy_btn.setFixedWidth(90)
        copy_btn.setStyleSheet(_BTN_PLAIN)
        copy_btn.clicked.connect(self._copy_url_results)
        res_hdr.addWidget(copy_btn)
        res_l.addLayout(res_hdr)

        self._url_table = QTableWidget(0, 7)
        self._url_table.setHorizontalHeaderLabels(
            ["URL", "状态码", "耗时", "大小", "Server", "类型", "错误"])
        h = self._url_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 7):
            h.setSectionResizeMode(col, QHeaderView.Interactive)
        self._url_table.setColumnWidth(1, 60)
        self._url_table.setColumnWidth(2, 70)
        self._url_table.setColumnWidth(3, 75)
        self._url_table.setColumnWidth(4, 130)
        self._url_table.setColumnWidth(5, 140)
        self._url_table.setColumnWidth(6, 200)
        self._url_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._url_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._url_table.verticalHeader().setDefaultSectionSize(26)
        self._url_table.setFont(self._mono)
        self._url_table.setSortingEnabled(True)
        res_l.addWidget(self._url_table)
        splitter.addWidget(res_w)

        splitter.setSizes([200, 350])
        root.addWidget(splitter, stretch=1)

        # 控制行
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("并发:"))
        self._concurrency = QSpinBox()
        self._concurrency.setRange(1, 100)
        self._concurrency.setValue(10)
        self._concurrency.setFixedWidth(65)
        ctrl.addWidget(self._concurrency)

        ctrl.addSpacing(10)
        ctrl.addWidget(QLabel("超时:"))
        self._url_timeout = QSpinBox()
        self._url_timeout.setRange(1, 120)
        self._url_timeout.setValue(10)
        self._url_timeout.setSuffix(" 秒")
        self._url_timeout.setFixedWidth(80)
        ctrl.addWidget(self._url_timeout)

        ctrl.addSpacing(16)
        self._url_start_btn = QPushButton("▶  开始测试")
        self._url_start_btn.setFixedHeight(34)
        self._url_start_btn.setStyleSheet(_BTN_PRIMARY)
        self._url_start_btn.clicked.connect(self._start_url)
        ctrl.addWidget(self._url_start_btn)

        self._url_stop_btn = QPushButton("■ 停止")
        self._url_stop_btn.setFixedHeight(30)
        self._url_stop_btn.setEnabled(False)
        self._url_stop_btn.clicked.connect(self._stop_url)
        ctrl.addWidget(self._url_stop_btn)

        self._url_clear_btn = QPushButton("清空结果")
        self._url_clear_btn.setFixedHeight(30)
        self._url_clear_btn.setStyleSheet(_BTN_PLAIN)
        self._url_clear_btn.clicked.connect(self._clear_url)
        ctrl.addWidget(self._url_clear_btn)
        ctrl.addStretch()
        root.addLayout(ctrl)

        self._url_progress = QProgressBar()
        self._url_progress.setFixedHeight(18)
        self._url_progress.setVisible(False)
        root.addWidget(self._url_progress)

        self._url_status = QLabel("就绪")
        self._url_status.setStyleSheet("color:#666;font-size:11px")
        root.addWidget(self._url_status)

        return w

    # ══════════════════════════════════════════════════════════
    #  Tab 2: nmap 端口连通性
    # ══════════════════════════════════════════════════════════
    def _build_nmap_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        hint = QLabel(
            "通过 nmap -sT 精准检测端口状态 (open / filtered / closed)。"
            "可选配代理（HTTP/SOCKS4）；不配代理则直连扫描目标。"
            "注：nmap --proxies 不支持 SOCKS5。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6b7a8d;font-size:11px;")
        root.addWidget(hint)

        # nmap 未找到横幅
        self._proxy_nmap_banner = QFrame()
        self._proxy_nmap_banner.setStyleSheet(
            "QFrame{background:#fff3cd;border:1px solid #ffc107;"
            "border-radius:4px;}")
        pnb_row = QHBoxLayout(self._proxy_nmap_banner)
        pnb_row.setContentsMargins(8, 4, 8, 4)
        self._proxy_nmap_lbl = QLabel(
            f"nmap 未找到 — 点击下载后才能使用端口扫描")
        self._proxy_nmap_lbl.setStyleSheet("color:#856404;font-size:11px;")
        pnb_row.addWidget(self._proxy_nmap_lbl, stretch=1)
        self._proxy_dl_btn = QPushButton(f"⬇ 下载 nmap {NMAP_VERSION}")
        self._proxy_dl_btn.setFixedHeight(26)
        self._proxy_dl_btn.setStyleSheet(
            "QPushButton{background:#ffc107;color:#333;border-radius:3px;"
            "padding:0 10px;font-size:12px;font-weight:bold;}"
            "QPushButton:hover{background:#ffca2c}"
            "QPushButton:disabled{background:#e0c060;color:#888}")
        self._proxy_dl_btn.clicked.connect(self._start_proxy_nmap_dl)
        pnb_row.addWidget(self._proxy_dl_btn)
        self._proxy_dl_progress = QProgressBar()
        self._proxy_dl_progress.setFixedHeight(18)
        self._proxy_dl_progress.setFixedWidth(160)
        self._proxy_dl_progress.setVisible(False)
        pnb_row.addWidget(self._proxy_dl_progress)
        root.addWidget(self._proxy_nmap_banner)
        self._proxy_nmap_banner.setVisible(not is_nmap_available())

        # 目标参数
        target_group = QGroupBox("扫描目标")
        tg = QVBoxLayout(target_group)

        t1 = QHBoxLayout()
        t1.addWidget(QLabel("目标主机:"))
        self._nmap_target = QLineEdit()
        self._nmap_target.setPlaceholderText("IP 或域名，如 www.example.com")
        t1.addWidget(self._nmap_target, stretch=1)
        tg.addLayout(t1)

        t2 = QHBoxLayout()
        t2.addWidget(QLabel("目标端口:"))
        self._nmap_ports = QLineEdit("80,443,22,3389")
        self._nmap_ports.setPlaceholderText("80 / 80-90 / 22,80,443")
        t2.addWidget(self._nmap_ports, stretch=1)
        self._nmap_preset = QComboBox()
        self._nmap_preset.addItems(SERVICE_PRESET_NAMES)
        self._nmap_preset.setFixedWidth(160)
        self._nmap_preset.currentIndexChanged.connect(self._on_nmap_preset)
        t2.addWidget(self._nmap_preset)
        tg.addLayout(t2)

        t3 = QHBoxLayout()
        t3.addWidget(QLabel("超时:"))
        self._nmap_timeout = QSpinBox()
        self._nmap_timeout.setRange(10, 600)
        self._nmap_timeout.setValue(60)
        self._nmap_timeout.setSuffix(" 秒")
        self._nmap_timeout.setFixedWidth(90)
        t3.addWidget(self._nmap_timeout)
        t3.addStretch()
        tg.addLayout(t3)

        root.addWidget(target_group)

        # 命令预览
        cmd_row = QHBoxLayout()
        cmd_row.addWidget(QLabel("命令预览:"))
        self._nmap_cmd_preview = QLineEdit()
        self._nmap_cmd_preview.setReadOnly(True)
        self._nmap_cmd_preview.setFont(self._mono)
        self._nmap_cmd_preview.setStyleSheet("background:#f5f6fa;color:#333;")
        cmd_row.addWidget(self._nmap_cmd_preview, stretch=1)
        root.addLayout(cmd_row)

        # 刷新预览触发器
        for w2 in (self._proxy_host, self._proxy_user, self._proxy_pass,
                   self._nmap_target, self._nmap_ports):
            w2.textChanged.connect(self._refresh_nmap_preview)
        self._proxy_type.currentTextChanged.connect(self._refresh_nmap_preview)
        self._proxy_port.valueChanged.connect(self._refresh_nmap_preview)
        self._refresh_nmap_preview()

        # 控制行
        ctrl = QHBoxLayout()
        self._nmap_start_btn = QPushButton("▶  开始扫描")
        self._nmap_start_btn.setFixedHeight(34)
        self._nmap_start_btn.setStyleSheet(_BTN_PRIMARY)
        self._nmap_start_btn.clicked.connect(self._start_nmap)
        ctrl.addWidget(self._nmap_start_btn)

        self._nmap_stop_btn = QPushButton("■ 停止")
        self._nmap_stop_btn.setFixedHeight(30)
        self._nmap_stop_btn.setEnabled(False)
        self._nmap_stop_btn.clicked.connect(self._stop_nmap)
        ctrl.addWidget(self._nmap_stop_btn)

        self._nmap_clear_btn = QPushButton("清空结果")
        self._nmap_clear_btn.setFixedHeight(30)
        self._nmap_clear_btn.setStyleSheet(_BTN_PLAIN)
        self._nmap_clear_btn.clicked.connect(self._clear_nmap)
        ctrl.addWidget(self._nmap_clear_btn)
        ctrl.addStretch()

        self._nmap_result_label = QLabel("")
        ctrl.addWidget(self._nmap_result_label)

        nmap_copy_btn = QPushButton("复制结果")
        nmap_copy_btn.setFixedWidth(90)
        nmap_copy_btn.setStyleSheet(_BTN_PLAIN)
        nmap_copy_btn.clicked.connect(self._copy_nmap_results)
        ctrl.addWidget(nmap_copy_btn)
        root.addLayout(ctrl)

        self._nmap_progress = QProgressBar()
        self._nmap_progress.setFixedHeight(18)
        self._nmap_progress.setRange(0, 0)
        self._nmap_progress.setVisible(False)
        root.addWidget(self._nmap_progress)

        # 结果表格
        self._nmap_table = QTableWidget(0, 5)
        self._nmap_table.setHorizontalHeaderLabels(
            ["端口", "状态", "原因", "服务", "知名服务"])
        h = self._nmap_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        h.setSectionResizeMode(1, QHeaderView.Fixed)
        h.setSectionResizeMode(2, QHeaderView.Fixed)
        h.setSectionResizeMode(3, QHeaderView.Interactive)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        self._nmap_table.setColumnWidth(0, 70)
        self._nmap_table.setColumnWidth(1, 80)
        self._nmap_table.setColumnWidth(2, 100)
        self._nmap_table.setColumnWidth(3, 120)
        self._nmap_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._nmap_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._nmap_table.verticalHeader().setDefaultSectionSize(26)
        self._nmap_table.setFont(self._mono)
        self._nmap_table.setSortingEnabled(True)
        root.addWidget(self._nmap_table, stretch=1)

        self._nmap_status = QLabel("就绪")
        self._nmap_status.setStyleSheet("color:#666;font-size:11px")
        root.addWidget(self._nmap_status)

        return w

    # ══════════════════════════════════════════════════════════
    #  nmap 下载（代理面板内）
    # ══════════════════════════════════════════════════════════
    def _start_proxy_nmap_dl(self):
        if self._dl_thread and self._dl_thread.isRunning():
            return
        self._proxy_dl_btn.setEnabled(False)
        self._proxy_dl_progress.setRange(0, 100)
        self._proxy_dl_progress.setValue(0)
        self._proxy_dl_progress.setVisible(True)
        self._proxy_nmap_lbl.setText(
            f"正在下载 nmap {NMAP_VERSION}… ({NMAP_ZIP_URL})")

        self._dl_thread = NmapDownloadThread()
        self._dl_thread.progress.connect(self._on_proxy_dl_progress)
        self._dl_thread.finished.connect(self._on_proxy_dl_finished)
        self._dl_thread.error.connect(self._on_proxy_dl_error)
        self._dl_thread.start()

    def _on_proxy_dl_progress(self, downloaded, total):
        if total > 0:
            self._proxy_dl_progress.setValue(int(downloaded * 100 / total))
            self._proxy_nmap_lbl.setText(
                f"下载中… {downloaded/1048576:.1f} / {total/1048576:.1f} MB")

    def _on_proxy_dl_finished(self, exe_path):
        self._proxy_dl_progress.setVisible(False)
        self._proxy_nmap_banner.setVisible(False)
        self._nmap_status.setText(f"nmap {NMAP_VERSION} 下载完成！{exe_path}")

    def _on_proxy_dl_error(self, msg):
        self._proxy_dl_btn.setEnabled(True)
        self._proxy_dl_progress.setVisible(False)
        self._proxy_nmap_lbl.setText(f"下载失败: {msg}  — 点击重试")

    # ══════════════════════════════════════════════════════════
    #  代理类型切换
    # ══════════════════════════════════════════════════════════
    def _on_proxy_type(self, ptype):
        has_proxy = ptype != "无代理"
        self._proxy_host.setEnabled(has_proxy)
        self._proxy_port.setEnabled(has_proxy)
        self._auth_row.setVisible(has_proxy)
        self._refresh_nmap_preview()

    # ══════════════════════════════════════════════════════════
    #  aiohttp URL 测试逻辑
    # ══════════════════════════════════════════════════════════
    def _parse_urls(self):
        text = self._url_input.toPlainText()
        urls = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if not line.startswith(('http://', 'https://')):
                line = 'http://' + line
            urls.append(line)
        return urls

    def _update_url_count(self):
        self._url_count_label.setText(f"{len(self._parse_urls())} 个 URL")

    def _start_url(self):
        if self._aiohttp_thread and self._aiohttp_thread.isRunning():
            QMessageBox.information(self, "提示", "测试正在进行，请等待完成或点击停止。")
            return

        urls = self._parse_urls()
        if not urls:
            self._url_status.setText("请输入至少一个 URL")
            return

        proxy_url = None
        ptype = self._proxy_type.currentText()
        if ptype != "无代理":
            ph = self._proxy_host.text().strip()
            if not ph:
                self._url_status.setText("请输入代理地址")
                return
            try:
                proxy_url = build_proxy_url(
                    ptype, ph, self._proxy_port.value(),
                    self._proxy_user.text().strip(),
                    self._proxy_pass.text().strip(),
                )
            except ValueError as e:
                self._url_status.setText(str(e))
                return

        self._url_table.setRowCount(0)
        self._url_table.setSortingEnabled(False)
        self._ok_count = self._fail_count = 0
        self._url_progress.setRange(0, len(urls))
        self._url_progress.setValue(0)
        self._url_progress.setVisible(True)
        self._url_start_btn.setEnabled(False)
        self._url_stop_btn.setEnabled(True)

        via = f" via {ptype} {self._proxy_host.text()}:{self._proxy_port.value()}" if proxy_url else " 直连"
        self._url_status.setText(f"正在测试 {len(urls)} 个 URL{via}…")

        self._aiohttp_thread = AiohttpTestThread(
            urls, proxy_url,
            self._url_timeout.value(),
            self._concurrency.value(),
        )
        self._aiohttp_thread.result_ready.connect(self._on_url_result)
        self._aiohttp_thread.progress.connect(self._on_url_progress)
        self._aiohttp_thread.finished_all.connect(self._on_url_finished)
        self._aiohttp_thread.error.connect(
            lambda msg: self._url_status.setText(f"错误: {msg}"))
        self._aiohttp_thread.start()

    def _stop_url(self):
        if self._aiohttp_thread and self._aiohttp_thread.isRunning():
            self._aiohttp_thread.stop()
            self._url_status.setText("正在停止…")

    def _on_url_result(self, r):
        row = self._url_table.rowCount()
        self._url_table.insertRow(row)

        self._url_table.setItem(row, 0, QTableWidgetItem(r['url']))

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
        self._url_table.setItem(row, 1, s_item)

        t_item = QTableWidgetItem(f"{r['time_ms']}ms")
        t_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._url_table.setItem(row, 2, t_item)

        size = r['size']
        if size >= 1_048_576:
            size_str = f"{size/1048576:.1f}MB"
        elif size >= 1024:
            size_str = f"{size/1024:.1f}KB"
        elif size > 0:
            size_str = f"{size}B"
        else:
            size_str = "-"
        sz_item = QTableWidgetItem(size_str)
        sz_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._url_table.setItem(row, 3, sz_item)

        self._url_table.setItem(row, 4, QTableWidgetItem(r.get('server', '')))

        ct = r.get('content_type', '')
        if ';' in ct:
            ct = ct.split(';')[0].strip()
        self._url_table.setItem(row, 5, QTableWidgetItem(ct))
        self._url_table.setItem(row, 6, QTableWidgetItem(r['error']))

    def _on_url_progress(self, current, total):
        self._url_progress.setValue(current)
        self._url_result_label.setText(
            f"{current}/{total} | 成功 {self._ok_count} | 失败 {self._fail_count}")

    def _on_url_finished(self, summary):
        self._url_progress.setVisible(False)
        self._url_start_btn.setEnabled(True)
        self._url_stop_btn.setEnabled(False)
        self._url_table.setSortingEnabled(True)
        self._url_result_label.setText(
            f"共 {self._url_table.rowCount()} | "
            f"成功 {self._ok_count} | 失败 {self._fail_count}")
        self._url_status.setText(summary)

    def _clear_url(self):
        self._url_table.setRowCount(0)
        self._url_result_label.setText("")
        self._ok_count = self._fail_count = 0
        self._url_status.setText("已清空")

    def _copy_url_results(self):
        rows = self._url_table.rowCount()
        if rows == 0:
            return
        lines = ['\t'.join(["URL", "状态码", "耗时", "大小", "Server", "类型", "错误"])]
        for i in range(rows):
            cells = [
                (self._url_table.item(i, c).text()
                 if self._url_table.item(i, c) else '')
                for c in range(self._url_table.columnCount())
            ]
            lines.append('\t'.join(cells))
        QApplication.clipboard().setText('\n'.join(lines))
        self._url_status.setText("已复制到剪贴板")

    # ══════════════════════════════════════════════════════════
    #  nmap 端口检测逻辑
    # ══════════════════════════════════════════════════════════
    def _refresh_nmap_preview(self):
        nmap_exe = get_nmap_exe() or 'nmap'
        target   = self._nmap_target.text().strip() or '<target>'
        ports    = self._nmap_ports.text().strip() or '80,443'
        ptype    = self._proxy_type.currentText()

        if ptype == '无代理':
            self._nmap_cmd_preview.setText(
                f"{nmap_exe} -sT -p {ports} -oX - -T4 {target}")
            return

        try:
            proxy_url = build_nmap_proxy_url(
                ptype,
                self._proxy_host.text().strip() or '<host>',
                self._proxy_port.value(),
                self._proxy_user.text().strip(),
                self._proxy_pass.text().strip(),
            )
        except ValueError:
            self._nmap_cmd_preview.setText(
                "（SOCKS5 不支持 --proxies，请切换到 HTTP 或 SOCKS4）")
            return
        self._nmap_cmd_preview.setText(
            f"{nmap_exe} -sT --proxies {proxy_url} -p {ports} -oX - -T4 {target}")

    def _on_nmap_preset(self, idx):
        if idx <= 0:
            return
        keys = list(SERVICE_PRESETS.keys())
        if idx - 1 < len(keys):
            ports = SERVICE_PRESETS[keys[idx - 1]][1]
            self._nmap_ports.setText(','.join(str(p) for p in ports))

    def _start_nmap(self):
        if self._nmap_thread and self._nmap_thread.isRunning():
            QMessageBox.information(self, "提示", "扫描正在进行，请等待或点击停止。")
            return

        if not is_nmap_available():
            self._nmap_status.setText("未找到 nmap 可执行文件")
            return

        target = self._nmap_target.text().strip()
        if not target:
            self._nmap_status.setText("请输入目标主机")
            return

        try:
            ports = parse_ports(self._nmap_ports.text().strip())
        except ValueError as e:
            self._nmap_status.setText(str(e))
            return
        if not ports:
            self._nmap_status.setText("无有效端口")
            return

        # 代理可选：无代理则直连
        proxy_url = None
        ptype = self._proxy_type.currentText()
        if ptype != '无代理':
            ph = self._proxy_host.text().strip()
            if not ph:
                self._nmap_status.setText("请输入代理地址")
                return
            try:
                proxy_url = build_nmap_proxy_url(
                    ptype, ph, self._proxy_port.value(),
                    self._proxy_user.text().strip(),
                    self._proxy_pass.text().strip(),
                )
            except ValueError as e:
                self._nmap_status.setText(str(e))
                return

        self._nmap_table.setRowCount(0)
        self._nmap_table.setSortingEnabled(False)
        self._nmap_progress.setVisible(True)
        self._nmap_start_btn.setEnabled(False)
        self._nmap_stop_btn.setEnabled(True)
        self._nmap_result_label.setText("扫描中…")

        via = f" (via {ptype} {self._proxy_host.text()}:{self._proxy_port.value()})" if proxy_url else " (直连)"
        self._nmap_status.setText(f"正在扫描 {target} 的 {len(ports)} 个端口{via}…")

        self._nmap_thread = NmapProxyThread(
            target, ports, 4, self._nmap_timeout.value(), proxy_url)
        self._nmap_thread.scan_done.connect(self._on_nmap_done)
        self._nmap_thread.scan_error.connect(self._on_nmap_error)
        self._nmap_thread.start()

    def _stop_nmap(self):
        if self._nmap_thread and self._nmap_thread.isRunning():
            self._nmap_thread.stop()
            self._nmap_status.setText("正在停止…")

    def _on_nmap_done(self, results, cmd_str, elapsed):
        self._nmap_progress.setVisible(False)
        self._nmap_start_btn.setEnabled(True)
        self._nmap_stop_btn.setEnabled(False)

        self._nmap_table.setRowCount(len(results))
        open_cnt = 0
        for row, r in enumerate(results):
            port_item = QTableWidgetItem()
            port_item.setData(Qt.DisplayRole, r['port'])
            port_item.setTextAlignment(Qt.AlignCenter)
            self._nmap_table.setItem(row, 0, port_item)

            state  = r['state']
            s_item = QTableWidgetItem(state)
            s_item.setTextAlignment(Qt.AlignCenter)
            if state == 'open':
                open_cnt += 1
                s_item.setBackground(QColor('#ccffcc'))
            elif state == 'filtered':
                s_item.setBackground(QColor('#ffffcc'))
            elif state == 'closed':
                s_item.setBackground(QColor('#ffcccc'))
            self._nmap_table.setItem(row, 1, s_item)

            self._nmap_table.setItem(row, 2, QTableWidgetItem(r['reason']))
            self._nmap_table.setItem(row, 3, QTableWidgetItem(r['service']))
            known = WELL_KNOWN_PORTS.get(r['port'], '')
            self._nmap_table.setItem(row, 4, QTableWidgetItem(known))

        self._nmap_table.setSortingEnabled(True)
        self._nmap_result_label.setText(
            f"共 {len(results)} 个端口 | 开放 {open_cnt} | 耗时 {elapsed:.1f}s")
        self._nmap_status.setText(f"完成  |  {cmd_str}")

    def _on_nmap_error(self, msg):
        self._nmap_progress.setVisible(False)
        self._nmap_start_btn.setEnabled(True)
        self._nmap_stop_btn.setEnabled(False)
        self._nmap_status.setText(f"错误: {msg}")
        self._nmap_result_label.setText("")

    def _clear_nmap(self):
        self._nmap_table.setRowCount(0)
        self._nmap_result_label.setText("")
        self._nmap_status.setText("已清空")

    def _copy_nmap_results(self):
        rows = self._nmap_table.rowCount()
        if rows == 0:
            return
        lines = ['\t'.join(["端口", "状态", "原因", "服务", "知名服务"])]
        for i in range(rows):
            cells = [
                (self._nmap_table.item(i, c).text()
                 if self._nmap_table.item(i, c) else '')
                for c in range(self._nmap_table.columnCount())
            ]
            lines.append('\t'.join(cells))
        QApplication.clipboard().setText('\n'.join(lines))
        self._nmap_status.setText("已复制到剪贴板")
