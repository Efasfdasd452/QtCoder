# -*- coding: utf-8 -*-
"""图片压缩面板 — 单张/多选/文件夹批量，肉眼无差异

- 单文件、多选、文件夹（递归）三种方式
- 预估压缩后大小，选择输出目录前提示空间
- 使用 Pillow 高质/无损参数（JPEG 98、PNG 优化、WebP lossless/100）
"""

import os
import subprocess

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QGroupBox, QMessageBox, QProgressBar, QFrame,
    QCheckBox, QTextEdit, QTabWidget, QRadioButton, QButtonGroup,
    QComboBox,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QThread, pyqtSignal

from core.image_compress import (
    collect_images_from_folder,
    estimate_compressed_size_total,
    get_disk_free_bytes,
    compress_image,
    is_available,
    IMAGE_FILTER,
    IMAGE_EXTS,
    PRESETS,
)

_BTN_PRIMARY = (
    "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
    "font-size:13px;border-radius:4px;padding:0 22px}"
    "QPushButton:hover{background:#106ebe}"
    "QPushButton:pressed{background:#005a9e}")

_BTN_GREEN = (
    "QPushButton{background:#107c10;color:#fff;font-weight:bold;"
    "font-size:13px;border-radius:4px;padding:0 28px}"
    "QPushButton:hover{background:#0e6b0e}"
    "QPushButton:pressed{background:#0a5a0a}")

_BTN_RED = (
    "QPushButton{background:#d13438;color:#fff;font-weight:bold;"
    "font-size:13px;border-radius:4px;padding:0 22px}"
    "QPushButton:hover{background:#b52e31}"
    "QPushButton:pressed{background:#9a2729}")

_PROGRESS_STYLE = (
    "QProgressBar{border:1px solid #dfe2e8;background:#e8eaed;"
    "border-radius:3px;text-align:center;font-size:11px;}"
    "QProgressBar::chunk{background:qlineargradient("
    "x1:0,y1:0,x2:1,y2:0,stop:0 #0078d4,stop:1 #00b7c3);"
    "border-radius:3px;}")


def _fmt_size(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024:.0f} KB"


class _ImageCompressWorker(QThread):
    progress = pyqtSignal(int, int)  # current_index, total
    log_line = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, tasks, preset_key="balanced"):
        super().__init__()
        # tasks: [(src_path, out_path), ...]
        self._tasks = list(tasks)
        self._preset_key = preset_key
        self._cancelled = False

    def run(self):
        total = len(self._tasks)
        if total == 0:
            self.finished.emit(False, "没有待压缩文件")
            return
        failed = []
        for i, (src, out) in enumerate(self._tasks):
            if self._cancelled:
                self.finished.emit(False, "已取消")
                return
            self.progress.emit(i, total)
            try:
                os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
                compress_image(src, out, keep_format=True, preset_key=self._preset_key)
                self.log_line.emit(f"OK: {os.path.basename(src)}")
            except Exception as e:
                self.log_line.emit(f"失败 [{os.path.basename(src)}]: {e}")
                failed.append(os.path.basename(src))
        if failed:
            self.finished.emit(False, f"部分失败: {', '.join(failed[:5])}{'…' if len(failed) > 5 else ''}")
        else:
            self.finished.emit(True, f"全部完成，共 {total} 张")

    def cancel(self):
        self._cancelled = True


class ImagePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._images = []  # 文件夹页: [(path, size), ...]
        self._source_dir = ""
        self._output_dir = ""
        self._single_path = ""        # 单张路径
        self._single_output = ""      # 单张输出路径
        self._multi_images = []       # 多选: [(path, size), ...]
        self._multi_output_dir = ""   # 多选输出文件夹
        self._last_output_path = ""  # 完成后“打开输出”用（文件或目录）
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(8)

        if not is_available():
            root.addWidget(QLabel("未检测到 Pillow，请安装: pip install Pillow"))
            return

        self._tabs = QTabWidget()

        # ── 单文件页（单张 + 多选）──
        single_w = QWidget()
        single_l = QVBoxLayout(single_w)
        single_l.setContentsMargins(0, 0, 0, 0)

        gs = QGroupBox("源图片")
        gsl = QVBoxLayout(gs)
        file_row = QHBoxLayout()
        self._open_btn = QPushButton("选择图片")
        self._open_btn.setFixedHeight(32)
        self._open_btn.setStyleSheet(_BTN_PRIMARY)
        self._open_btn.clicked.connect(self._pick_single)
        file_row.addWidget(self._open_btn)
        self._open_multi_btn = QPushButton("选择多个图片")
        self._open_multi_btn.setFixedHeight(32)
        self._open_multi_btn.setStyleSheet(_BTN_PRIMARY)
        self._open_multi_btn.clicked.connect(self._pick_multi)
        file_row.addWidget(self._open_multi_btn)
        self._file_label = QLabel("拖放或点击选择图片")
        self._file_label.setStyleSheet("color:#6b7a8d;font-size:12px;")
        file_row.addWidget(self._file_label, stretch=1)
        gsl.addLayout(file_row)
        single_l.addWidget(gs)

        gpre = QGroupBox("压缩策略")
        gprel = QVBoxLayout(gpre)
        self._preset_btns = {}
        self._preset_group = QButtonGroup(self)
        preset_row = QHBoxLayout()
        for i, (key, p) in enumerate(PRESETS.items()):
            rb = QRadioButton(p["name"])
            rb.setToolTip(p["desc"])
            self._preset_group.addButton(rb, i)
            self._preset_btns[key] = rb
            preset_row.addWidget(rb)
        preset_row.addStretch()
        gprel.addLayout(preset_row)
        self._preset_desc = QLabel(PRESETS["balanced"]["desc"])
        self._preset_desc.setStyleSheet("color:#6b7a8d;font-size:11px;padding:2px 4px;")
        gprel.addWidget(self._preset_desc)
        self._preset_btns["balanced"].setChecked(True)
        self._preset_group.buttonClicked.connect(self._on_single_preset_changed)
        single_l.addWidget(gpre)

        go = QGroupBox("输出")
        gol = QVBoxLayout(go)
        out_row = QHBoxLayout()
        self._out_btn = QPushButton("选择输出路径")
        self._out_btn.setFixedHeight(30)
        self._out_btn.clicked.connect(self._pick_output)
        out_row.addWidget(self._out_btn)
        self._out_label = QLabel("单张：将自动生成；多选：请选择输出文件夹")
        self._out_label.setStyleSheet("color:#6b7a8d;font-size:12px;")
        out_row.addWidget(self._out_label, stretch=1)
        gol.addLayout(out_row)
        self._single_estimate_label = QLabel("")
        self._single_estimate_label.setStyleSheet("color:#107c10;font-size:11px;")
        gol.addWidget(self._single_estimate_label)
        single_l.addWidget(go)
        single_l.addStretch()
        self._tabs.addTab(single_w, "单文件")

        # ── 批量（文件夹）页 ──
        batch_w = QWidget()
        bl = QVBoxLayout(batch_w)
        bl.setContentsMargins(0, 0, 0, 0)

        g1 = QGroupBox("源文件夹")
        g1l = QVBoxLayout(g1)
        row1 = QHBoxLayout()
        self._src_btn = QPushButton("选择源文件夹")
        self._src_btn.setFixedHeight(32)
        self._src_btn.setStyleSheet(_BTN_PRIMARY)
        self._src_btn.clicked.connect(self._pick_source)
        row1.addWidget(self._src_btn)
        self._recursive = QCheckBox("包含子文件夹（递归）")
        self._recursive.setChecked(True)
        self._recursive.stateChanged.connect(self._refresh_list)
        row1.addWidget(self._recursive)
        row1.addStretch()
        g1l.addLayout(row1)
        self._src_label = QLabel("未选择文件夹")
        self._src_label.setStyleSheet("color:#6b7a8d;font-size:12px;")
        g1l.addWidget(self._src_label)
        self._summary = QLabel("")
        self._summary.setStyleSheet("color:#1e2433;font-size:12px;")
        self._summary.setWordWrap(True)
        g1l.addWidget(self._summary)
        bl.addWidget(g1)

        g2p = QGroupBox("压缩策略")
        g2pl = QVBoxLayout(g2p)
        rowp = QHBoxLayout()
        rowp.addWidget(QLabel("统一策略:"))
        self._batch_preset = QComboBox()
        for key, p in PRESETS.items():
            self._batch_preset.addItem(p["name"], key)
        self._batch_preset.currentIndexChanged.connect(self._update_batch_estimate)
        rowp.addWidget(self._batch_preset)
        rowp.addStretch()
        g2pl.addLayout(rowp)
        bl.addWidget(g2p)

        g2 = QGroupBox("输出")
        g2l = QVBoxLayout(g2)
        row2 = QHBoxLayout()
        self._batch_out_btn = QPushButton("选择输出文件夹")
        self._batch_out_btn.setFixedHeight(30)
        self._batch_out_btn.clicked.connect(self._pick_batch_output)
        row2.addWidget(self._batch_out_btn)
        self._out_batch_label = QLabel("请先选择输出文件夹（将保持子目录结构）")
        self._out_batch_label.setStyleSheet("color:#6b7a8d;font-size:12px;")
        row2.addWidget(self._out_batch_label, stretch=1)
        g2l.addLayout(row2)
        self._estimate_label = QLabel("")
        self._estimate_label.setStyleSheet("color:#107c10;font-size:11px;")
        g2l.addWidget(self._estimate_label)
        bl.addWidget(g2)
        bl.addStretch()
        self._tabs.addTab(batch_w, "批量（文件夹）")

        root.addWidget(self._tabs)

        hint = QLabel("压缩策略：肉眼无差异（JPEG 98 / PNG 优化 / WebP 无损或 100）")
        hint.setStyleSheet("color:#6b7a8d;font-size:11px;")
        root.addWidget(hint)

        act_row = QHBoxLayout()
        self._start_btn = QPushButton("▶  开始压缩")
        self._start_btn.setFixedHeight(36)
        self._start_btn.setStyleSheet(_BTN_GREEN)
        self._start_btn.clicked.connect(self._start)
        act_row.addWidget(self._start_btn)
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setFixedHeight(36)
        self._cancel_btn.setStyleSheet(_BTN_RED)
        self._cancel_btn.clicked.connect(self._cancel)
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setVisible(False)
        act_row.addWidget(self._cancel_btn)
        act_row.addStretch()
        root.addLayout(act_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
        self._progress.setFixedHeight(22)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(_PROGRESS_STYLE)
        self._progress.setVisible(False)
        root.addWidget(self._progress)
        self._progress_label = QLabel()
        self._progress_label.setStyleSheet("color:#1e2433;font-size:12px;")
        self._progress_label.setVisible(False)
        root.addWidget(self._progress_label)

        self._result_frame = QFrame()
        self._result_frame.setVisible(False)
        rfl = QVBoxLayout(self._result_frame)
        rfl.setContentsMargins(10, 8, 10, 8)
        self._result_label = QLabel()
        self._result_label.setWordWrap(True)
        self._result_label.setStyleSheet("font-size:13px;color:#1e2433;font-weight:bold;")
        rfl.addWidget(self._result_label)
        rbr = QHBoxLayout()
        self._open_folder_btn = QPushButton("打开输出文件夹")
        self._open_folder_btn.setFixedHeight(28)
        self._open_folder_btn.clicked.connect(self._open_folder)
        rbr.addWidget(self._open_folder_btn)
        rbr.addStretch()
        rfl.addLayout(rbr)
        root.addWidget(self._result_frame)

        self._log_btn = QPushButton("显示日志 ▾")
        self._log_btn.setFixedHeight(24)
        self._log_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#6b7a8d;font-size:11px;"
            "border:none;text-align:left;padding:0;} QPushButton:hover{color:#0078d4;}")
        self._log_btn.clicked.connect(self._toggle_log)
        root.addWidget(self._log_btn)
        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setFont(QFont("Consolas", 9))
        self._log_area.setMaximumHeight(150)
        self._log_area.setStyleSheet(
            "QTextEdit{background:#1e1e1e;color:#cccccc;border:1px solid #333;border-radius:4px;}")
        self._log_area.setVisible(False)
        root.addWidget(self._log_area)
        root.addStretch()
        self._status = QLabel("就绪 — 支持 JPG / PNG / WebP / BMP / TIFF 等格式")
        self._status.setStyleSheet("color:#666;font-size:11px;")
        root.addWidget(self._status)

    def _pick_single(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", IMAGE_FILTER)
        if not path:
            return
        self._multi_images = []
        self._multi_output_dir = ""
        self._single_path = path
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        self._file_label.setText(os.path.basename(path))
        base, ext = os.path.splitext(path)
        self._single_output = f"{base}_compressed{ext}"
        self._out_label.setText(os.path.basename(self._single_output))
        self._single_estimate_label.setText(
            f"原始 {_fmt_size(size)}，预估约 {_fmt_size(estimate_compressed_size_total([size], self._get_single_preset_key()))}"
        )
        self._result_frame.setVisible(False)
        self._status.setText(f"已选: {os.path.basename(path)}")

    def _pick_multi(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择多个图片", "", IMAGE_FILTER)
        if not paths:
            return
        self._single_path = ""
        self._single_output = ""
        self._multi_images = []
        for p in paths:
            try:
                self._multi_images.append((p, os.path.getsize(p)))
            except OSError:
                pass
        if not self._multi_images:
            return
        self._file_label.setText(f"已选 {len(self._multi_images)} 张图片")
        self._multi_output_dir = ""
        self._out_label.setText("请选择输出文件夹（多选批量）")
        total = sum(s for _, s in self._multi_images)
        est = estimate_compressed_size_total([s for _, s in self._multi_images], self._get_single_preset_key())
        self._single_estimate_label.setText(
            f"共 {len(self._multi_images)} 张，总大小 {_fmt_size(total)}，预估约 {_fmt_size(est)}"
        )
        self._result_frame.setVisible(False)
        self._status.setText(f"已选 {len(self._multi_images)} 张，请选择输出文件夹后开始压缩")

    def _get_single_preset_key(self):
        for key, rb in self._preset_btns.items():
            if rb.isChecked():
                return key
        return "balanced"

    def _on_single_preset_changed(self, btn):
        for key, rb in self._preset_btns.items():
            if rb is btn:
                self._preset_desc.setText(PRESETS[key]["desc"])
                break
        if self._single_path:
            try:
                size = os.path.getsize(self._single_path)
                self._single_estimate_label.setText(
                    f"原始 {_fmt_size(size)}，预估约 {_fmt_size(estimate_compressed_size_total([size], self._get_single_preset_key()))}"
                )
            except OSError:
                pass
        elif self._multi_images:
            total = sum(s for _, s in self._multi_images)
            est = estimate_compressed_size_total([s for _, s in self._multi_images], self._get_single_preset_key())
            self._single_estimate_label.setText(
                f"共 {len(self._multi_images)} 张，总大小 {_fmt_size(total)}，预估约 {_fmt_size(est)}"
            )

    def _pick_output(self):
        if self._multi_images:
            folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹（多选批量）")
            if not folder:
                return
            est = estimate_compressed_size_total([s for _, s in self._multi_images], self._get_single_preset_key())
            free = get_disk_free_bytes(folder)
            if free > 0 and est > free:
                r = QMessageBox.warning(
                    self, "空间可能不足",
                    f"预估约 {_fmt_size(est)}，该磁盘可用 {_fmt_size(free)}，可能不足。\n\n是否仍要选择？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if r != QMessageBox.Yes:
                    return
            self._multi_output_dir = folder
            self._out_label.setText(folder)
            return
        if not self._single_path:
            QMessageBox.information(self, "提示", "请先选择一张图片")
            return
        default = self._single_output or "output.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存压缩图片", default, IMAGE_FILTER)
        if path:
            self._single_output = path
            self._out_label.setText(os.path.basename(path))

    def _pick_source(self):
        folder = QFileDialog.getExistingDirectory(self, "选择源文件夹")
        if not folder:
            return
        self._source_dir = folder
        self._src_label.setText(folder)
        self._refresh_list()

    def _pick_batch_output(self):
        if not self._images:
            QMessageBox.information(self, "提示", "请先选择源文件夹并确认已扫描到图片")
            return
        preset = self._batch_preset.currentData() or "balanced"
        est = estimate_compressed_size_total([s for _, s in self._images], preset)
        folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if not folder:
            return
        free = get_disk_free_bytes(folder)
        if free > 0 and est > free:
            r = QMessageBox.warning(
                self, "空间可能不足",
                f"预估压缩后总大小约 {_fmt_size(est)}，该磁盘可用空间 {_fmt_size(free)}，可能不足。\n\n是否仍要选择此文件夹？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if r != QMessageBox.Yes:
                return
        self._output_dir = folder
        self._out_batch_label.setText(folder)

    def _refresh_list(self):
        if not self._source_dir or not os.path.isdir(self._source_dir):
            self._images = []
            self._summary.setText("")
            self._estimate_label.setText("")
            return
        recursive = self._recursive.isChecked()
        paths = collect_images_from_folder(self._source_dir, recursive=recursive)
        self._images = []
        for p in paths:
            try:
                self._images.append((p, os.path.getsize(p)))
            except OSError:
                pass
        total_size = sum(s for _, s in self._images)
        self._summary.setText(f"找到 {len(self._images)} 张图片，总大小 {_fmt_size(total_size)}")
        self._update_batch_estimate()

    def _update_batch_estimate(self):
        if not self._images:
            self._estimate_label.setText("")
            return
        preset = self._batch_preset.currentData() if hasattr(self, "_batch_preset") else "balanced"
        total_size = sum(s for _, s in self._images)
        est = estimate_compressed_size_total([s for _, s in self._images], preset)
        ratio = (est / total_size * 100) if total_size else 0
        self._estimate_label.setText(
            f"预估压缩后总大小约 {_fmt_size(est)}（约为原大小的 {ratio:.0f}%）"
        )

    def _pick_output(self):
        if not self._images:
            QMessageBox.information(self, "提示", "请先选择源文件夹并确认已扫描到图片")
            return
        est = estimate_compressed_size_total([s for _, s in self._images])
        folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if not folder:
            return
        free = get_disk_free_bytes(folder)
        if free > 0 and est > free:
            r = QMessageBox.warning(
                self, "空间可能不足",
                f"预估压缩后总大小约 {_fmt_size(est)}，该磁盘可用空间 {_fmt_size(free)}，可能不足。\n\n是否仍要选择此文件夹？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if r != QMessageBox.Yes:
                return
        self._output_dir = folder
        self._out_label.setText(folder)

    def _start(self):
        if self._worker and self._worker.isRunning():
            return
        if self._tabs.currentIndex() == 0:
            preset = self._get_single_preset_key()
            if self._multi_images:
                if not self._multi_output_dir or not os.path.isdir(self._multi_output_dir):
                    QMessageBox.information(self, "提示", "请先选择输出文件夹")
                    return
                tasks = []
                used = {}
                for path, _ in self._multi_images:
                    base, ext = os.path.splitext(os.path.basename(path))
                    key = base + "_compressed" + ext
                    if key in used:
                        used[key] += 1
                        out_name = f"{base}_compressed_{used[key]}{ext}"
                    else:
                        used[key] = 1
                        out_name = key
                    tasks.append((path, os.path.join(self._multi_output_dir, out_name)))
                self._run_batch(tasks, preset, is_single_tab=True)
                return
            if self._single_path:
                if not self._single_output:
                    QMessageBox.information(self, "提示", "请先选择输出路径")
                    return
                self._run_batch([(self._single_path, self._single_output)], preset, is_single_tab=True)
                return
            QMessageBox.information(self, "提示", "请先选择图片或多个图片")
            return
        # 批量（文件夹）页
        preset = self._batch_preset.currentData() or "balanced"
        if not self._images:
            QMessageBox.information(self, "提示", "请先选择源文件夹")
            return
        if not self._output_dir or not os.path.isdir(self._output_dir):
            QMessageBox.information(self, "提示", "请先选择输出文件夹")
            return
        src = os.path.normpath(self._source_dir)
        out_dir = os.path.normpath(self._output_dir)
        tasks = []
        for path, _ in self._images:
            rel = os.path.relpath(path, src)
            base, ext = os.path.splitext(rel)
            new_rel = base + "_compressed" + ext
            tasks.append((path, os.path.join(out_dir, new_rel)))
        self._run_batch(tasks, preset, is_single_tab=False)

    def _run_batch(self, tasks, preset_key="balanced", is_single_tab=False):
        self._log_area.clear()
        self._log_area.setVisible(True)
        self._log_btn.setText("隐藏日志 ▴")
        self._start_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.setVisible(True)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._progress_label.setVisible(True)
        self._result_frame.setVisible(False)
        self._status.setText("压缩中…")
        self._worker = _ImageCompressWorker(tasks, preset_key=preset_key)
        self._worker.progress.connect(self._on_progress)
        self._worker.log_line.connect(self._log_area.append)
        self._worker.finished.connect(lambda ok, msg: self._on_finished(ok, msg, is_single_tab))
        self._worker.start()

    def _cancel(self):
        if self._worker:
            self._worker.cancel()
        self._cancel_btn.setEnabled(False)
        self._status.setText("正在取消…")

    def _on_progress(self, idx, total):
        pct = (idx + 1) / total * 100 if total else 0
        self._progress.setValue(int(pct * 10))
        self._progress_label.setText(f"当前 {idx + 1}/{total}")

    def _on_finished(self, success, msg, is_single_tab=False):
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setVisible(False)
        self._progress.setVisible(False)
        self._progress_label.setVisible(False)
        if is_single_tab:
            if self._multi_images and self._multi_output_dir:
                self._last_output_path = self._multi_output_dir
            elif self._single_output:
                self._last_output_path = os.path.dirname(self._single_output) or self._single_output
            else:
                self._last_output_path = ""
        else:
            self._last_output_path = self._output_dir
        self._result_frame.setStyleSheet(
            "QFrame{background:#f0fff0;border:1px solid #107c10;"
            "border-radius:6px;padding:8px;}" if success else
            "QFrame{background:#fff0f0;border:1px solid #d13438;"
            "border-radius:6px;padding:8px;}")
        self._result_label.setText(msg)
        self._result_frame.setVisible(True)
        self._status.setText("压缩完成" if success else msg)

    def _toggle_log(self):
        vis = not self._log_area.isVisible()
        self._log_area.setVisible(vis)
        self._log_btn.setText("隐藏日志 ▴" if vis else "显示日志 ▾")

    def _open_folder(self):
        path = self._last_output_path or self._output_dir
        if path and os.path.exists(path):
            target = path if os.path.isdir(path) else os.path.dirname(path)
            if target and os.path.exists(target):
                if os.name == "nt":
                    os.startfile(target)
                else:
                    subprocess.Popen(["xdg-open", target])
