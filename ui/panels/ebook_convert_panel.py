# -*- coding: utf-8 -*-
"""电子书格式转换面板

支持：EPUB / PDF / MOBI / AZW / AZW3 互相转换
引擎：Calibre ebook-convert
      · 已安装系统 Calibre → 直接使用
      · 未安装 → 点击「下载 Calibre」按钮自动下载并解压到 bin/calibre/
"""

import os
import threading

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QProgressBar,
    QFileDialog, QFrame, QComboBox, QSizePolicy,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.ebook_convert import (
    SUPPORTED_INPUT,
    SUPPORTED_OUTPUT,
    get_calibre_custom_path,
    set_calibre_custom_path,
)

_MONO = QFont("Consolas", 9)
_MONO.setStyleHint(QFont.Monospace)

_CLR_PENDING = QColor("#ffffff")
_CLR_OK      = QColor("#e6f4ea")
_CLR_ERR     = QColor("#fce8e6")
_FMT_LABEL   = {"pdf": "PDF", "epub": "EPUB", "mobi": "MOBI"}


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
        lbl = QLabel("🗂  拖放 EPUB / PDF / MOBI / AZW 文件或文件夹到此处")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color:#888; font-size:13px; background:transparent;")
        lay.addWidget(lbl)

    def _set_normal(self):
        self.setStyleSheet(
            "QFrame{border:2px dashed #c0c8d4;"
            "border-radius:8px; background:#fafbfc;}")

    def _set_hover(self):
        self.setStyleSheet(
            "QFrame{border:2px dashed #0078d4;"
            "border-radius:8px; background:#e8f4fc;}")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_hover()

    def dragLeaveEvent(self, e):
        self._set_normal()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        self._set_normal()
        self.files_dropped.emit(paths)


# ════════════════════════════════════════════════════════════
#  Calibre 下载线程
# ════════════════════════════════════════════════════════════
class _DownloadWorker(QThread):
    progress = pyqtSignal(float, float)   # (downloaded_mb, total_mb)
    status   = pyqtSignal(str)
    finished = pyqtSignal(str)            # "" = success, else error msg

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        from core.ebook_convert import download_and_setup_calibre
        err = download_and_setup_calibre(
            on_progress=lambda d, t: self.progress.emit(d, t),
            on_status=lambda m: self.status.emit(m),
            stop_event=self._stop,
        )
        self.finished.emit(err or "")


# ════════════════════════════════════════════════════════════
#  转换后台线程
# ════════════════════════════════════════════════════════════
class _ConvertWorker(QThread):
    progress  = pyqtSignal(int, int)
    file_done = pyqtSignal(str, str, str)
    finished  = pyqtSignal()

    def __init__(self, files: list[str], output_format: str,
                 output_dir: str | None):
        super().__init__()
        self._files         = files
        self._output_format = output_format
        self._output_dir    = output_dir
        self._stop          = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        total      = len(self._files)
        done_count = [0]

        def on_done(src, dest, err):
            done_count[0] += 1
            self.file_done.emit(src, dest or "", err or "")
            self.progress.emit(done_count[0], total)

        from core.ebook_convert import convert_batch
        convert_batch(
            self._files, self._output_format,
            self._output_dir, on_done, self._stop,
        )
        self.finished.emit()


# ════════════════════════════════════════════════════════════
#  主面板
# ════════════════════════════════════════════════════════════
class EbookConvertPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[str] = []
        self._convert_worker: _ConvertWorker | None = None
        self._dl_worker: _DownloadWorker | None = None
        self._build_ui()
        self._refresh_calibre_hint()

    # ── 构建界面 ──────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(6)

        # 拖放区域
        drop = _DropArea()
        drop.files_dropped.connect(self._add_paths)
        root.addWidget(drop)

        # ── Calibre 状态行 ────────────────────────────────
        cal_row = QHBoxLayout()
        self._calibre_hint = QLabel("")
        self._calibre_hint.setStyleSheet("font-size:11px;")
        self._calibre_hint.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred)
        cal_row.addWidget(self._calibre_hint, stretch=1)

        self._dl_btn = QPushButton("⬇  下载 Calibre (~191 MB)")
        self._dl_btn.setFixedHeight(26)
        self._dl_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-size:11px;"
            "border-radius:4px;border:none;font-weight:bold;}"
            "QPushButton:hover{background:#106ebe;}"
            "QPushButton:disabled{background:#aaa;color:#eee;}")
        self._dl_btn.clicked.connect(self._start_download)
        cal_row.addWidget(self._dl_btn)

        self._dl_cancel_btn = QPushButton("取消")
        self._dl_cancel_btn.setFixedHeight(26)
        self._dl_cancel_btn.setFixedWidth(46)
        self._dl_cancel_btn.setStyleSheet(
            "QPushButton{background:#d83b01;color:#fff;font-size:11px;"
            "border-radius:4px;border:none;}"
            "QPushButton:disabled{background:#aaa;}")
        self._dl_cancel_btn.clicked.connect(self._cancel_download)
        self._dl_cancel_btn.hide()
        cal_row.addWidget(self._dl_cancel_btn)
        root.addLayout(cal_row)

        # 下载进度条（默认隐藏）
        self._dl_progress = QProgressBar()
        self._dl_progress.setFixedHeight(5)
        self._dl_progress.setTextVisible(False)
        self._dl_progress.setRange(0, 1000)
        self._dl_progress.hide()
        root.addWidget(self._dl_progress)

        # ── 提示：bin/calibre 为安装包，需解压到短路径后指定 ─────
        tip = QLabel(
            "提示：bin/calibre 下为安装包，Calibre 要求路径少于 59 字符。"
            "请将安装包解压到短路径目录（如 C:\\ec\\calibre）后，在下方指定 ebook-convert.exe 的路径。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("font-size:11px; color:#666; margin:4px 0;")
        root.addWidget(tip)

        # ── 指定 Calibre 可执行文件路径 ─────────────────────
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("指定路径:"))
        self._calibre_path_edit = QLineEdit()
        self._calibre_path_edit.setPlaceholderText("可选，浏览选择 ebook-convert.exe…")
        self._calibre_path_edit.setStyleSheet("font-family:Consolas; font-size:11px;")
        self._calibre_path_edit.textChanged.connect(self._on_calibre_path_changed)
        path_row.addWidget(self._calibre_path_edit, stretch=1)
        self._calibre_browse_btn = QPushButton("浏览…")
        self._calibre_browse_btn.setFixedWidth(56)
        self._calibre_browse_btn.clicked.connect(self._browse_calibre_exe)
        path_row.addWidget(self._calibre_browse_btn)
        root.addLayout(path_row)
        # 加载已保存的指定路径
        saved = get_calibre_custom_path()
        if saved:
            self._calibre_path_edit.setText(saved)

        # ── 输出格式 + 输出目录 ───────────────────────────
        cfg_row = QHBoxLayout()

        cfg_row.addWidget(QLabel("转换为:"))
        self._fmt_combo = QComboBox()
        for fmt in SUPPORTED_OUTPUT:
            self._fmt_combo.addItem(_FMT_LABEL[fmt], fmt)
        self._fmt_combo.setFixedWidth(90)
        cfg_row.addWidget(self._fmt_combo)

        cfg_row.addSpacing(16)
        self._same_dir_cb = QCheckBox("与源文件同目录")
        self._same_dir_cb.setChecked(True)
        self._same_dir_cb.toggled.connect(self._on_same_dir_toggle)
        cfg_row.addWidget(self._same_dir_cb)

        cfg_row.addSpacing(8)
        cfg_row.addWidget(QLabel("输出目录:"))
        self._out_dir_edit = QLineEdit()
        self._out_dir_edit.setPlaceholderText("选择输出目录…")
        self._out_dir_edit.setEnabled(False)
        cfg_row.addWidget(self._out_dir_edit, stretch=1)

        self._browse_btn = QPushButton("浏览…")
        self._browse_btn.setFixedWidth(56)
        self._browse_btn.setEnabled(False)
        self._browse_btn.clicked.connect(self._browse_output_dir)
        cfg_row.addWidget(self._browse_btn)
        root.addLayout(cfg_row)

        # ── 操作按钮 ──────────────────────────────────────
        btn_row = QHBoxLayout()
        for text, slot, color in [
            ("添加文件",   self._add_file,   "#0078d4"),
            ("添加文件夹", self._add_folder, "#5c2d91"),
            ("开始转换",   self._start,      "#107c10"),
            ("停止",       self._stop_conv,  "#d83b01"),
            ("清空",       self._clear,      "#666666"),
        ]:
            b = QPushButton(text)
            b.setFixedHeight(30)
            b.setStyleSheet(
                f"QPushButton{{background:{color};color:#fff;font-weight:bold;"
                f"border-radius:4px;border:none;font-size:12px;}}"
                f"QPushButton:disabled{{background:#aaa;color:#eee;}}")
            b.clicked.connect(slot)
            btn_row.addWidget(b)
            if text == "停止":
                self._stop_btn = b
                b.setEnabled(False)
            if text == "开始转换":
                self._start_btn = b
        btn_row.addStretch()
        root.addLayout(btn_row)

        # 转换进度条
        self._progress = QProgressBar()
        self._progress.setFixedHeight(5)
        self._progress.setTextVisible(False)
        self._progress.hide()
        root.addWidget(self._progress)

        # 状态行
        self._status = QLabel("就绪  —  文件数: 0")
        self._status.setStyleSheet("color:#555; font-size:11px;")
        root.addWidget(self._status)

        # 文件列表表格
        self._table = QTableWidget()
        self._table.setFont(_MONO)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(
            ["文件名", "原路径", "状态", "输出路径"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        root.addWidget(self._table, stretch=1)

    # ── 指定路径与 Calibre 状态 ───────────────────────────
    def _on_calibre_path_changed(self, text: str):
        path = text.strip() or None
        # 仅当清空或指向已存在的文件时保存并刷新，避免输入过程中误清配置
        if path is not None and not os.path.isfile(path):
            return
        set_calibre_custom_path(path)
        self._refresh_calibre_hint()

    def _browse_calibre_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 ebook-convert.exe",
            self._calibre_path_edit.text() or "",
            "可执行文件 (ebook-convert.exe);;所有文件 (*)",
        )
        if path:
            self._calibre_path_edit.setText(path)

    # ── Calibre 状态检测 ──────────────────────────────────
    def _refresh_calibre_hint(self):
        from core.ebook_convert import find_calibre, calibre_download_info
        path = find_calibre()
        if path:
            self._calibre_hint.setText(f"✓ Calibre 已就绪：{path}")
            self._calibre_hint.setStyleSheet("font-size:11px; color:#107c10;")
            self._dl_btn.hide()
        else:
            info = calibre_download_info()
            self._calibre_hint.setText(
                f"✗ 未找到 Calibre v{info['version']}，点击右侧按钮自动下载安装到 bin/calibre/")
            self._calibre_hint.setStyleSheet("font-size:11px; color:#c0392b;")
            self._dl_btn.show()

    # ── Calibre 下载 ──────────────────────────────────────
    def _start_download(self):
        self._dl_btn.setEnabled(False)
        self._dl_cancel_btn.show()
        self._dl_progress.show()
        self._dl_progress.setValue(0)
        self._calibre_hint.setText("准备下载…")
        self._calibre_hint.setStyleSheet("font-size:11px; color:#555;")

        self._dl_worker = _DownloadWorker()
        self._dl_worker.progress.connect(self._on_dl_progress)
        self._dl_worker.status.connect(self._on_dl_status)
        self._dl_worker.finished.connect(self._on_dl_finished)
        self._dl_worker.start()

    def _cancel_download(self):
        if self._dl_worker:
            self._dl_worker.stop()

    def _on_dl_progress(self, downloaded: float, total: float):
        if total > 0:
            pct = int(downloaded / total * 1000)
            self._dl_progress.setValue(pct)
            self._calibre_hint.setText(
                f"下载中：{downloaded:.1f} / {total:.1f} MB")

    def _on_dl_status(self, msg: str):
        self._calibre_hint.setText(msg)

    def _on_dl_finished(self, err: str):
        self._dl_progress.hide()
        self._dl_cancel_btn.hide()
        self._dl_btn.setEnabled(True)
        if err:
            self._calibre_hint.setText(f"✗ 安装失败：{err}")
            self._calibre_hint.setStyleSheet("font-size:11px; color:#c0392b;")
        else:
            self._refresh_calibre_hint()

    # ── 输出目录切换 ──────────────────────────────────────
    def _on_same_dir_toggle(self, checked: bool):
        self._out_dir_edit.setEnabled(not checked)
        self._browse_btn.setEnabled(not checked)

    def _browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self._out_dir_edit.setText(d)

    # ── 文件管理 ──────────────────────────────────────────
    def _collect_ebook_files(self, paths: list) -> list:
        result = []
        for p in paths:
            if os.path.isfile(p):
                if os.path.splitext(p)[1].lower() in SUPPORTED_INPUT:
                    result.append(p)
            elif os.path.isdir(p):
                for root_dir, _, fnames in os.walk(p):
                    for fn in sorted(fnames):
                        if os.path.splitext(fn)[1].lower() in SUPPORTED_INPUT:
                            result.append(os.path.join(root_dir, fn))
        return result

    def _add_paths(self, paths: list):
        existing = set(self._files)
        for f in self._collect_ebook_files(paths):
            if f not in existing:
                self._files.append(f)
                existing.add(f)
                row = self._table.rowCount()
                self._table.insertRow(row)
                self._table.setItem(
                    row, 0, QTableWidgetItem(os.path.basename(f)))
                self._table.setItem(row, 1, QTableWidgetItem(f))
                it_s = QTableWidgetItem("待转换")
                it_s.setTextAlignment(Qt.AlignCenter)
                self._table.setItem(row, 2, it_s)
                self._table.setItem(row, 3, QTableWidgetItem(""))
        self._status.setText(f"就绪  —  文件数: {len(self._files)}")

    def _add_file(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择电子书文件", "",
            "电子书文件 (*.epub *.pdf *.mobi *.azw *.azw3);;所有文件 (*)")
        if paths:
            self._add_paths(paths)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self._add_paths([folder])

    def _clear(self):
        self._files.clear()
        self._table.setRowCount(0)
        self._status.setText("就绪  —  文件数: 0")

    # ── 转换控制 ──────────────────────────────────────────
    def _start(self):
        if not self._files:
            self._status.setText("请先添加文件")
            return

        output_dir = None
        if not self._same_dir_cb.isChecked():
            output_dir = self._out_dir_edit.text().strip()
            if not output_dir:
                self._status.setText("请选择输出目录，或勾选「与源文件同目录」")
                return
            if not os.path.isdir(output_dir):
                self._status.setText(f"输出目录不存在: {output_dir}")
                return

        for row in range(self._table.rowCount()):
            it = self._table.item(row, 2)
            if it:
                it.setText("待转换")
                it.setBackground(_CLR_PENDING)
            out_it = self._table.item(row, 3)
            if out_it:
                out_it.setText("")

        self._progress.setRange(0, len(self._files))
        self._progress.setValue(0)
        self._progress.show()
        self._stop_btn.setEnabled(True)
        self._start_btn.setEnabled(False)

        fmt = self._fmt_combo.currentData()
        self._convert_worker = _ConvertWorker(
            list(self._files), fmt, output_dir)
        self._convert_worker.progress.connect(self._on_progress)
        self._convert_worker.file_done.connect(self._on_file_done)
        self._convert_worker.finished.connect(self._on_finished)
        self._convert_worker.start()
        self._status.setText(f"转换中…  → {_FMT_LABEL[fmt]}")

    def _stop_conv(self):
        if self._convert_worker:
            self._convert_worker.stop()
            self._status.setText("正在停止，等待当前文件完成…")

    # ── 信号处理 ──────────────────────────────────────────
    def _on_progress(self, cur: int, total: int):
        self._progress.setValue(cur)
        self._status.setText(f"转换中：{cur} / {total}")

    def _on_file_done(self, src: str, dest: str, err: str):
        try:
            row = self._files.index(src)
        except ValueError:
            return

        status_item = QTableWidgetItem()
        status_item.setTextAlignment(Qt.AlignCenter)
        out_item = QTableWidgetItem()

        if dest:
            status_item.setText("✓ 完成")
            status_item.setBackground(_CLR_OK)
            out_item.setText(dest)
        else:
            status_item.setText("失败")
            status_item.setBackground(_CLR_ERR)
            status_item.setToolTip(err)
            out_item.setText(err[:120])
            out_item.setForeground(QColor("#ca5010"))

        self._table.setItem(row, 2, status_item)
        self._table.setItem(row, 3, out_item)

    def _on_finished(self):
        self._progress.hide()
        self._stop_btn.setEnabled(False)
        self._start_btn.setEnabled(True)
        ok = sum(
            1 for r in range(self._table.rowCount())
            if self._table.item(r, 2)
            and "✓" in (self._table.item(r, 2).text() or "")
        )
        total = len(self._files)
        self._status.setText(f"完成  —  成功 {ok} / 共 {total} 个文件")
