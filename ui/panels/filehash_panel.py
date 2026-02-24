# -*- coding: utf-8 -*-
"""文件哈希 & PGP 验证面板

Tab 1 · 哈希计算  — 拖放批量计算 MD5/SHA-1/SHA-256/SHA-512/SHA3-256，支持预期哈希对比
Tab 2 · PGP 验证  — 验证文件的 PGP 分离签名（.asc）
         公钥来源：本地文件 / 粘贴文本 / 在线获取（WKD 或 keys.openpgp.org）
"""

import os
import csv

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QProgressBar, QApplication,
    QFileDialog, QFrame, QTabWidget, QPlainTextEdit,
)
from PyQt5.QtGui import QFont, QColor, QDragEnterEvent, QDropEvent
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.file_hash import (
    ALGORITHMS, hash_file, collect_files, compare_hash, fmt_size
)

_MONO = QFont("Consolas", 9)
_MONO.setStyleHint(QFont.Monospace)

_CLR_OK   = QColor("#e6f4ea")
_CLR_FAIL = QColor("#fce8e6")
_CLR_NONE = QColor("#ffffff")


# ════════════════════════════════════════════════════════════
#  哈希后台线程
# ════════════════════════════════════════════════════════════
class _HashWorker(QThread):
    progress = pyqtSignal(int, int)
    row_done = pyqtSignal(str, dict, int)
    error    = pyqtSignal(str, str)
    finished = pyqtSignal()

    def __init__(self, files: list[str], algos: list[str]):
        super().__init__()
        self._files = files
        self._algos = algos
        self._stop  = False

    def stop(self):
        self._stop = True

    def run(self):
        total = len(self._files)
        for i, path in enumerate(self._files):
            if self._stop:
                break
            try:
                size   = os.path.getsize(path)
                hashes = hash_file(path, self._algos)
                self.row_done.emit(path, hashes, size)
            except Exception as e:
                self.error.emit(path, str(e))
            self.progress.emit(i + 1, total)
        self.finished.emit()


# ════════════════════════════════════════════════════════════
#  PGP 验证后台线程
# ════════════════════════════════════════════════════════════
class _PgpWorker(QThread):
    done = pyqtSignal(dict)

    def __init__(self, file_path, sig_source, pubkey_source,
                 sig_is_file, pubkey_is_file):
        super().__init__()
        self._file_path      = file_path
        self._sig_source     = sig_source
        self._pubkey_source  = pubkey_source
        self._sig_is_file    = sig_is_file
        self._pubkey_is_file = pubkey_is_file

    def run(self):
        try:
            from core.pgp_verify import verify_pgp_detached
            result = verify_pgp_detached(
                self._file_path, self._sig_source, self._pubkey_source,
                self._sig_is_file, self._pubkey_is_file)
        except Exception as e:
            result = {
                'valid': False, 'message': str(e),
                'fingerprint': '', 'key_id': '', 'sig_time': '',
                'user_ids': [], 'hash_algo': '', 'key_algo': '',
                'sig_key_id': '',
            }
        self.done.emit(result)


# ════════════════════════════════════════════════════════════
#  公钥在线获取后台线程
# ════════════════════════════════════════════════════════════
class _KeyFetchWorker(QThread):
    done  = pyqtSignal(object, str)   # (key_data: bytes|str, source_desc)
    error = pyqtSignal(str)

    def __init__(self, mode: str, query: str):
        super().__init__()
        self._mode  = mode    # 'wkd' | 'keyserver'
        self._query = query

    def run(self):
        try:
            from core.pgp_verify import fetch_key_wkd, fetch_key_keyserver
            if self._mode == 'wkd':
                data = fetch_key_wkd(self._query)
                self.done.emit(data, f"WKD ({self._query})")
            else:
                data = fetch_key_keyserver(self._query)
                self.done.emit(data, f"keys.openpgp.org ({self._query})")
        except Exception as e:
            self.error.emit(str(e))


# ════════════════════════════════════════════════════════════
#  拖放区域
# ════════════════════════════════════════════════════════════
class _DropArea(QFrame):
    files_dropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setFixedHeight(60)
        self._set_normal()
        lay = QHBoxLayout(self)
        lbl = QLabel("🗂  拖放文件或文件夹到此处（支持多选）")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color:#888; font-size:13px; background:transparent;")
        lay.addWidget(lbl)

    def _set_normal(self):
        self.setStyleSheet(
            "QFrame{border:2px dashed #c0c8d4; border-radius:8px; background:#fafbfc;}")

    def _set_hover(self):
        self.setStyleSheet(
            "QFrame{border:2px dashed #0078d4; border-radius:8px; background:#e8f4fc;}")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_hover()

    def dragLeaveEvent(self, e):
        self._set_normal()

    def dropEvent(self, event: QDropEvent):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self._set_normal()
        self.files_dropped.emit(paths)


# ════════════════════════════════════════════════════════════
#  主面板
# ════════════════════════════════════════════════════════════
class FileHashPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[str] = []
        self._worker:      _HashWorker     | None = None
        self._pgp_worker:  _PgpWorker      | None = None
        self._key_worker:  _KeyFetchWorker | None = None
        self._pgp_fetched_key_data = None   # bytes (WKD) or str (keyserver)
        self._build_ui()

    # ── 整体结构 ──────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(0)

        tabs = QTabWidget()
        tabs.addTab(self._build_hash_tab(), "🔢  哈希计算")
        tabs.addTab(self._build_pgp_tab(),  "🔏  PGP 签名验证")
        root.addWidget(tabs, stretch=1)

    # ─────────────────────────────────────────────────────────
    #  Tab 1: 哈希计算
    # ─────────────────────────────────────────────────────────
    def _build_hash_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        drop = _DropArea()
        drop.files_dropped.connect(self._add_paths)
        lay.addWidget(drop)

        opt = QHBoxLayout()
        opt.addWidget(QLabel("算法:"))
        self._algo_checks: dict[str, QCheckBox] = {}
        for algo in ALGORITHMS:
            cb = QCheckBox(algo)
            cb.setChecked(algo == 'SHA-256')
            self._algo_checks[algo] = cb
            opt.addWidget(cb)
        opt.addSpacing(12)
        opt.addWidget(QLabel("预期哈希 (可选):"))
        self._expected = QLineEdit()
        self._expected.setFont(_MONO)
        self._expected.setPlaceholderText("粘贴已知哈希值，计算后自动对比")
        self._expected.setFixedWidth(340)
        opt.addWidget(self._expected)
        opt.addStretch()
        lay.addLayout(opt)

        btns = QHBoxLayout()
        for text, slot, color in [
            ("添加文件",   self._add_file,   "#0078d4"),
            ("添加文件夹", self._add_folder, "#5c2d91"),
            ("开始计算",   self._start,      "#107c10"),
            ("停止",       self._stop,       "#d83b01"),
            ("清空",       self._clear,      "#666666"),
        ]:
            b = QPushButton(text)
            b.setFixedHeight(30)
            b.setStyleSheet(
                f"QPushButton{{background:{color};color:#fff;font-weight:bold;"
                f"border-radius:4px;border:none;font-size:12px;}}")
            b.clicked.connect(slot)
            btns.addWidget(b)
            if text == "停止":
                self._stop_btn = b
                b.setEnabled(False)
        btns.addStretch()
        self._export_btn = QPushButton("导出 CSV")
        self._export_btn.setFixedHeight(30)
        self._export_btn.clicked.connect(self._export_csv)
        btns.addWidget(self._export_btn)
        lay.addLayout(btns)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(5)
        self._progress.setTextVisible(False)
        self._progress.hide()
        lay.addWidget(self._progress)

        self._status = QLabel("就绪  —  文件数: 0")
        self._status.setStyleSheet("color:#555; font-size:11px;")
        lay.addWidget(self._status)

        self._table = QTableWidget()
        self._table.setFont(_MONO)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setDefaultSectionSize(26)
        lay.addWidget(self._table, stretch=1)
        return w

    # ── 哈希逻辑 ──────────────────────────────────────────
    def _add_paths(self, paths):
        existing = set(self._files)
        for p in collect_files(paths):
            if p not in existing:
                self._files.append(p)
                existing.add(p)
        self._status.setText(f"就绪  —  文件数: {len(self._files)}")

    def _add_file(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        if paths:
            self._add_paths(paths)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self._add_paths([folder])

    def _clear(self):
        self._files.clear()
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._status.setText("就绪  —  文件数: 0")

    def _selected_algos(self):
        return [a for a, cb in self._algo_checks.items() if cb.isChecked()]

    def _start(self):
        if not self._files:
            self._status.setText("请先添加文件")
            return
        algos = self._selected_algos()
        if not algos:
            self._status.setText("请至少选择一种算法")
            return
        cols = ['文件路径', '大小'] + algos + ['验证']
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(cols)):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._table.setRowCount(len(self._files))
        for row, path in enumerate(self._files):
            self._table.setItem(row, 0, QTableWidgetItem(path))
        self._progress.setRange(0, len(self._files))
        self._progress.setValue(0)
        self._progress.show()
        self._stop_btn.setEnabled(True)
        self._algos_computing = algos
        self._worker = _HashWorker(self._files, algos)
        self._worker.progress.connect(self._on_progress)
        self._worker.row_done.connect(self._on_row_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _stop(self):
        if self._worker:
            self._worker.stop()

    def _on_progress(self, cur, total):
        self._progress.setValue(cur)
        self._status.setText(f"计算中：{cur} / {total}")

    def _on_row_done(self, path, hashes, size):
        try:
            row = self._files.index(path)
        except ValueError:
            return
        algos = self._algos_computing
        it = QTableWidgetItem(fmt_size(size))
        it.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, 1, it)
        expected = self._expected.text().strip()
        verified = False
        for i, algo in enumerate(algos):
            h = hashes.get(algo, '')
            hi = QTableWidgetItem(h)
            hi.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 2 + i, hi)
            if expected and compare_hash(h, expected):
                verified = True
        v_col = 2 + len(algos)
        if expected:
            txt = "✓ 匹配" if verified else "✗ 不匹配"
            bg  = _CLR_OK if verified else _CLR_FAIL
        else:
            txt, bg = "—", _CLR_NONE
        vi = QTableWidgetItem(txt)
        vi.setTextAlignment(Qt.AlignCenter)
        vi.setBackground(bg)
        self._table.setItem(row, v_col, vi)

    def _on_error(self, path, msg):
        try:
            row = self._files.index(path)
        except ValueError:
            return
        it = QTableWidgetItem(f"错误: {msg}")
        it.setForeground(QColor("#ca5010"))
        self._table.setItem(row, 2, it)

    def _on_finished(self):
        self._progress.hide()
        self._stop_btn.setEnabled(False)
        self._status.setText(f"完成  —  共 {len(self._files)} 个文件")

    def _export_csv(self):
        if self._table.rowCount() == 0:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", "hashes.csv", "CSV (*.csv)")
        if not path:
            return
        headers = [self._table.horizontalHeaderItem(c).text()
                   for c in range(self._table.columnCount())]
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(headers)
            for row in range(self._table.rowCount()):
                w.writerow([
                    (self._table.item(row, col).text()
                     if self._table.item(row, col) else '')
                    for col in range(self._table.columnCount())
                ])
        self._status.setText(f"已导出至 {path}")

    # ─────────────────────────────────────────────────────────
    #  Tab 2: PGP 签名验证
    # ─────────────────────────────────────────────────────────
    def _build_pgp_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # ── 文件 & 签名 ──────────────────────────────────
        files_grp = QGroupBox("文件 & 签名")
        fg = QVBoxLayout(files_grp)
        fg.setSpacing(6)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("待验证文件:"))
        self._pgp_file_in = QLineEdit()
        self._pgp_file_in.setFont(_MONO)
        self._pgp_file_in.setPlaceholderText("下载的文件，如 tor-browser-windows-x86_64-portable-14.0.exe")
        r1.addWidget(self._pgp_file_in, stretch=1)
        b1 = QPushButton("浏览")
        b1.setFixedWidth(50)
        b1.clicked.connect(self._pgp_browse_file)
        r1.addWidget(b1)
        fg.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("签名文件:  "))
        self._pgp_sig_in = QLineEdit()
        self._pgp_sig_in.setFont(_MONO)
        self._pgp_sig_in.setPlaceholderText("对应的 .asc 签名文件（选择主文件后自动检测）")
        self._pgp_sig_in.textChanged.connect(self._pgp_on_sig_path_changed)
        r2.addWidget(self._pgp_sig_in, stretch=1)
        b2 = QPushButton("浏览 .asc")
        b2.setFixedWidth(72)
        b2.clicked.connect(self._pgp_browse_sig)
        r2.addWidget(b2)
        fg.addLayout(r2)

        self._pgp_sig_info = QLabel("")
        self._pgp_sig_info.setStyleSheet(
            "color:#0078d4; font-size:11px; padding:0px 2px;")
        fg.addWidget(self._pgp_sig_info)

        lay.addWidget(files_grp)

        # ── 公钥来源 ─────────────────────────────────────
        key_grp = QGroupBox("公钥来源  （务必从软件官方网站获取）")
        kg = QVBoxLayout(key_grp)
        kg.setContentsMargins(6, 4, 6, 6)

        key_tabs = QTabWidget()
        key_tabs.setFixedHeight(150)

        # Tab 0: 从文件
        kf_w = QWidget()
        kfw = QHBoxLayout(kf_w)
        kfw.setContentsMargins(6, 10, 6, 6)
        self._pgp_key_file_in = QLineEdit()
        self._pgp_key_file_in.setFont(_MONO)
        self._pgp_key_file_in.setPlaceholderText(
            "公钥文件路径（Armored .asc 或二进制 .gpg / .pgp，或无扩展名的下载文件）")
        kfw.addWidget(self._pgp_key_file_in, stretch=1)
        b3 = QPushButton("浏览")
        b3.setFixedWidth(50)
        b3.clicked.connect(self._pgp_browse_key)
        kfw.addWidget(b3)
        key_tabs.addTab(kf_w, "从文件导入")          # 支持 Armored(.asc) 与二进制(.gpg) 格式

        # Tab 1: 粘贴文本
        kt_w = QWidget()
        ktw = QVBoxLayout(kt_w)
        ktw.setContentsMargins(4, 4, 4, 4)
        self._pgp_key_text = QPlainTextEdit()
        self._pgp_key_text.setFont(_MONO)
        self._pgp_key_text.setPlaceholderText(
            "粘贴 PGP 公钥文本（-----BEGIN PGP PUBLIC KEY BLOCK----- ...）")
        ktw.addWidget(self._pgp_key_text)
        key_tabs.addTab(kt_w, "粘贴公钥文本")

        # Tab 2: 在线获取（WKD / 密钥服务器）
        ko_w = QWidget()
        kow = QVBoxLayout(ko_w)
        kow.setContentsMargins(6, 6, 6, 4)
        kow.setSpacing(4)

        wkd_row = QHBoxLayout()
        wkd_lbl = QLabel("邮箱 (WKD):")
        wkd_lbl.setFixedWidth(92)
        wkd_row.addWidget(wkd_lbl)
        self._pgp_key_email = QLineEdit()
        self._pgp_key_email.setFont(_MONO)
        self._pgp_key_email.setPlaceholderText("如 torbrowser@torproject.org")
        wkd_row.addWidget(self._pgp_key_email, stretch=1)
        b_wkd = QPushButton("WKD 获取")
        b_wkd.setFixedWidth(80)
        b_wkd.clicked.connect(self._pgp_fetch_wkd)
        wkd_row.addWidget(b_wkd)
        kow.addLayout(wkd_row)

        ks_row = QHBoxLayout()
        ks_lbl = QLabel("指纹/Key ID:")
        ks_lbl.setFixedWidth(92)
        ks_row.addWidget(ks_lbl)
        self._pgp_key_fp = QLineEdit()
        self._pgp_key_fp.setFont(_MONO)
        self._pgp_key_fp.setPlaceholderText(
            "如 EF6E286DDA85EA2A4BA7DE684E2C6E8793298290（从官网复制）")
        ks_row.addWidget(self._pgp_key_fp, stretch=1)
        b_ks = QPushButton("服务器获取")
        b_ks.setFixedWidth(80)
        b_ks.clicked.connect(self._pgp_fetch_keyserver)
        ks_row.addWidget(b_ks)
        kow.addLayout(ks_row)

        self._pgp_key_fetch_status = QLabel(
            "未获取  ·  WKD：从软件官方域名获取  ·  服务器：从 keys.openpgp.org 获取")
        self._pgp_key_fetch_status.setStyleSheet("color:#888; font-size:11px;")
        self._pgp_key_fetch_status.setWordWrap(True)
        kow.addWidget(self._pgp_key_fetch_status)

        exp_row = QHBoxLayout()
        self._pgp_export_btn = QPushButton("导出公钥到本地文件…")
        self._pgp_export_btn.setFixedHeight(26)
        self._pgp_export_btn.setEnabled(False)
        self._pgp_export_btn.setToolTip("保存已获取的公钥，下次直接用「从文件导入」加载，无需重新联网")
        self._pgp_export_btn.clicked.connect(self._pgp_export_key)
        exp_row.addWidget(self._pgp_export_btn)
        exp_row.addStretch()
        kow.addLayout(exp_row)

        key_tabs.addTab(ko_w, "在线获取")

        self._pgp_key_tabs = key_tabs
        kg.addWidget(key_tabs)
        lay.addWidget(key_grp)

        # ── 验证按钮 ─────────────────────────────────────
        btn_row = QHBoxLayout()
        self._pgp_btn = QPushButton("  开 始 验 证  ")
        self._pgp_btn.setFixedHeight(36)
        self._pgp_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "border-radius:6px;border:none;font-size:14px;}"
            "QPushButton:hover{background:#106ebe;}"
            "QPushButton:disabled{background:#aaa;}")
        self._pgp_btn.clicked.connect(self._pgp_verify)
        btn_row.addWidget(self._pgp_btn)
        btn_row.addStretch()
        self._pgp_err = QLabel("")
        self._pgp_err.setStyleSheet("color:#ca5010; font-size:11px;")
        self._pgp_err.setWordWrap(True)
        btn_row.addWidget(self._pgp_err)
        lay.addLayout(btn_row)

        # ── 验证结果 ─────────────────────────────────────
        self._pgp_result_grp = QGroupBox("验证结果")
        self._pgp_result_grp.hide()
        rg = QVBoxLayout(self._pgp_result_grp)
        rg.setContentsMargins(8, 6, 8, 8)
        rg.setSpacing(6)

        self._pgp_banner = QLabel("")
        self._pgp_banner.setAlignment(Qt.AlignCenter)
        self._pgp_banner.setFixedHeight(42)
        self._pgp_banner.setStyleSheet(
            "font-size:14px; font-weight:bold; border-radius:6px; padding:0 12px;")
        rg.addWidget(self._pgp_banner)

        # 指纹验证提示（仅验证通过时显示）
        self._pgp_fp_warn = QLabel(
            "⚠  安全提示：请将下方「完整指纹」与软件官方网站公布的指纹逐字对照，"
            "确认完全一致后方可信任此签名")
        self._pgp_fp_warn.setStyleSheet(
            "background:#fff8e1; color:#856404; padding:5px 10px;"
            "border-radius:4px; font-size:11px;")
        self._pgp_fp_warn.setWordWrap(True)
        self._pgp_fp_warn.hide()
        rg.addWidget(self._pgp_fp_warn)

        self._pgp_details: dict[str, QLabel] = {}
        detail_items = [
            ('签名者',   '公钥绑定的用户名 / 邮箱（UID）'),
            ('签名时间', '此签名的创建时间（UTC）'),
            ('密钥 ID',  '签名密钥的短 ID（最后16位十六进制）'),
            ('完整指纹', '公钥的完整指纹 — 请与官方网站公布的指纹对照确认'),
            ('哈希算法', '签名使用的哈希算法'),
            ('密钥算法', '公钥算法类型'),
        ]
        for key, tooltip in detail_items:
            row = QHBoxLayout()
            lk = QLabel(f"<b>{key}:</b>")
            lk.setFixedWidth(72)
            lk.setToolTip(tooltip)
            lv = QLabel("—")
            lv.setFont(_MONO)
            lv.setWordWrap(True)
            lv.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(lk)
            row.addWidget(lv, stretch=1)
            rg.addLayout(row)
            self._pgp_details[key] = lv

        lay.addWidget(self._pgp_result_grp)
        lay.addStretch()
        return w

    # ── PGP 文件浏览 ──────────────────────────────────────
    def _pgp_browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择待验证文件")
        if not path:
            return
        self._pgp_file_in.setText(path)
        asc = path + '.asc'
        if os.path.isfile(asc) and not self._pgp_sig_in.text().strip():
            self._pgp_sig_in.setText(asc)

    def _pgp_browse_sig(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择签名文件", "",
            "PGP 签名 (*.asc *.sig);;所有文件 (*)")
        if path:
            self._pgp_sig_in.setText(path)

    def _pgp_browse_key(self):
        # "所有文件" 排第一，方便选取无扩展名的二进制 WKD 下载文件
        path, _ = QFileDialog.getOpenFileName(
            self, "选择公钥文件", "",
            "所有文件 (*);;PGP Armored (*.asc);;二进制 OpenPGP (*.gpg *.pgp)")
        if path:
            self._pgp_key_file_in.setText(path)

    def _pgp_on_sig_path_changed(self, path: str):
        """解析签名文件，预览签名者 Key ID / 时间 / 算法。"""
        path = path.strip()
        if not path or not os.path.isfile(path):
            self._pgp_sig_info.setText("")
            return
        try:
            from core.pgp_verify import peek_signature
            info = peek_signature(path, sig_is_file=True)
            if info['key_id']:
                parts = [f"ℹ  签名者 Key ID: 0x{info['key_id']}"]
                if info['created']:
                    parts.append(f"签名时间: {info['created']}")
                if info['hash_algo']:
                    parts.append(f"哈希算法: {info['hash_algo']}")
                self._pgp_sig_info.setText("    ·    ".join(parts))
            else:
                self._pgp_sig_info.setText("")
        except Exception as e:
            self._pgp_sig_info.setText(f"⚠  无法解析签名文件: {e}")

    # ── 在线获取公钥 ──────────────────────────────────────
    def _pgp_fetch_wkd(self):
        email = self._pgp_key_email.text().strip()
        if not email or '@' not in email:
            self._pgp_key_fetch_status.setStyleSheet("color:#ca5010; font-size:11px;")
            self._pgp_key_fetch_status.setText("请输入有效邮箱地址")
            return
        self._pgp_fetched_key_data = None
        self._pgp_export_btn.setEnabled(False)
        self._pgp_key_fetch_status.setStyleSheet("color:#555; font-size:11px;")
        self._pgp_key_fetch_status.setText(f"WKD 获取中…  ({email})")
        self._key_worker = _KeyFetchWorker('wkd', email)
        self._key_worker.done.connect(self._pgp_on_key_fetched)
        self._key_worker.error.connect(self._pgp_on_key_fetch_error)
        self._key_worker.start()

    def _pgp_fetch_keyserver(self):
        query = self._pgp_key_fp.text().strip()
        if not query:
            self._pgp_key_fetch_status.setStyleSheet("color:#ca5010; font-size:11px;")
            self._pgp_key_fetch_status.setText("请输入指纹或 Key ID")
            return
        self._pgp_fetched_key_data = None
        self._pgp_export_btn.setEnabled(False)
        self._pgp_key_fetch_status.setStyleSheet("color:#555; font-size:11px;")
        self._pgp_key_fetch_status.setText(f"密钥服务器获取中…  ({query})")
        self._key_worker = _KeyFetchWorker('keyserver', query)
        self._key_worker.done.connect(self._pgp_on_key_fetched)
        self._key_worker.error.connect(self._pgp_on_key_fetch_error)
        self._key_worker.start()

    def _pgp_on_key_fetched(self, data, desc: str):
        self._pgp_fetched_key_data = data
        self._pgp_export_btn.setEnabled(True)
        try:
            import pgpy
            result = (pgpy.PGPKey.from_blob(data)
                      if isinstance(data, (bytes, bytearray))
                      else pgpy.PGPKey.from_blob(data.strip()))
            key = result[0] if isinstance(result, tuple) else result
            uids = []
            for uid in key.userids:
                try:
                    name  = uid.name  or ''
                    email = uid.email or ''
                    uids.append(f"{name} <{email}>" if email else name)
                except Exception:
                    pass
            uid_str = ' / '.join(uids[:2]) if uids else '（无 UID 信息）'
            self._pgp_key_fetch_status.setStyleSheet("color:#107c10; font-size:11px;")
            self._pgp_key_fetch_status.setText(f"✓ 已获取 ({desc}): {uid_str}")
        except Exception as e:
            self._pgp_key_fetch_status.setStyleSheet("color:#107c10; font-size:11px;")
            self._pgp_key_fetch_status.setText(
                f"✓ 已获取 ({desc}) — 预览解析失败: {e}")

    def _pgp_on_key_fetch_error(self, err: str):
        self._pgp_fetched_key_data = None
        self._pgp_export_btn.setEnabled(False)
        self._pgp_key_fetch_status.setStyleSheet("color:#ca5010; font-size:11px;")
        self._pgp_key_fetch_status.setText(f"✗ 获取失败: {err}")

    # ── 导出已获取的公钥 ──────────────────────────────────
    def _pgp_export_key(self):
        data = self._pgp_fetched_key_data
        if not data:
            return
        is_binary = isinstance(data, (bytes, bytearray))
        if is_binary:
            default_name = "public_key.gpg"
            file_filter  = "二进制 OpenPGP (*.gpg);;所有文件 (*)"
        else:
            default_name = "public_key.asc"
            file_filter  = "PGP Armored (*.asc);;所有文件 (*)"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出公钥到文件", default_name, file_filter)
        if not path:
            return
        with open(path, 'wb' if is_binary else 'w',
                  **({}  if is_binary else {'encoding': 'utf-8'})) as f:
            f.write(data)
        self._pgp_key_fetch_status.setText(
            self._pgp_key_fetch_status.text().split("  →  ")[0]
            + f"  →  已导出: {os.path.basename(path)}")

    # ── 执行验证 ──────────────────────────────────────────
    def _pgp_verify(self):
        file_path = self._pgp_file_in.text().strip()
        sig_path  = self._pgp_sig_in.text().strip()
        key_tab   = self._pgp_key_tabs.currentIndex()

        if not file_path:
            self._pgp_err.setText("请选择待验证文件")
            return
        if not os.path.isfile(file_path):
            self._pgp_err.setText(f"文件不存在: {file_path}")
            return
        if not sig_path:
            self._pgp_err.setText("请选择签名文件 (.asc)")
            return
        if not os.path.isfile(sig_path):
            self._pgp_err.setText(f"签名文件不存在: {sig_path}")
            return

        if key_tab == 0:
            key_src     = self._pgp_key_file_in.text().strip()
            key_is_file = True
            if not key_src:
                self._pgp_err.setText("请选择公钥文件")
                return
            if not os.path.isfile(key_src):
                self._pgp_err.setText(f"公钥文件不存在: {key_src}")
                return
        elif key_tab == 1:
            key_src     = self._pgp_key_text.toPlainText().strip()
            key_is_file = False
            if not key_src:
                self._pgp_err.setText("请粘贴公钥内容")
                return
        else:  # tab 2: 在线获取
            if not self._pgp_fetched_key_data:
                self._pgp_err.setText(
                    "请先点击「WKD 获取」或「服务器获取」拉取公钥")
                return
            key_src     = self._pgp_fetched_key_data
            key_is_file = False

        self._pgp_err.setText("")
        self._pgp_btn.setEnabled(False)
        self._pgp_btn.setText("验证中…")
        self._pgp_result_grp.hide()

        self._pgp_worker = _PgpWorker(
            file_path, sig_path, key_src, True, key_is_file)
        self._pgp_worker.done.connect(self._pgp_on_done)
        self._pgp_worker.start()

    def _pgp_on_done(self, result: dict):
        self._pgp_btn.setEnabled(True)
        self._pgp_btn.setText("  开 始 验 证  ")

        valid   = result['valid']
        uids    = result.get('user_ids', [])
        uid_str = uids[0] if uids else ''

        if valid:
            if uid_str:
                banner_text = f"✓ 签名验证通过  —  Good signature from \"{uid_str}\""
            else:
                banner_text = "✓  签名验证通过  —  文件完整，来源可信"
            bg, fg = '#e6f4ea', '#107c10'
            self._pgp_fp_warn.show()
        else:
            banner_text = "✗  签名验证失败"
            bg, fg = '#fce8e6', '#c0392b'
            self._pgp_fp_warn.hide()

        self._pgp_banner.setText(banner_text)
        self._pgp_banner.setStyleSheet(
            f"background:{bg}; color:{fg}; font-size:14px; font-weight:bold;"
            f" border-radius:6px; padding:0 12px;")

        self._pgp_details['签名者'].setText('\n'.join(uids) if uids else '—')
        self._pgp_details['签名时间'].setText(result.get('sig_time') or '—')
        kid = result.get('key_id', '')
        self._pgp_details['密钥 ID'].setText(f"0x{kid}" if kid else '—')
        self._pgp_details['完整指纹'].setText(result.get('fingerprint') or '—')
        self._pgp_details['哈希算法'].setText(result.get('hash_algo') or '—')
        self._pgp_details['密钥算法'].setText(result.get('key_algo') or '—')

        if not valid:
            msg = result.get('message', '')
            if msg:
                self._pgp_err.setText(msg)

        self._pgp_result_grp.show()
