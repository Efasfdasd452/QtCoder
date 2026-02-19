# -*- coding: utf-8 -*-
"""视频压缩面板 — 基于 FFmpeg

支持:
  - 多格式输入 (mp4/mkv/avi/m2ts/ts/mov/...)
  - 三档预设 + 自定义模式
  - 硬件加速编码 (NVENC / QSV / AMF)
  - 实时进度、速度、剩余时间
  - 压缩前后大小对比
"""

import os
import subprocess
import time

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QComboBox, QGroupBox, QMessageBox, QSizePolicy,
    QProgressBar, QFrame, QRadioButton, QButtonGroup,
    QSpinBox, QTextEdit, QApplication, QTabWidget,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.video_compress import (
    find_ffmpeg, probe_video, VideoInfo,
    PRESETS, CODECS, SPEEDS, RESOLUTIONS, AUDIO_OPTS,
    CompressConfig, build_command, parse_progress,
    VIDEO_EXTS, VIDEO_FILTER, OUTPUT_FILTER,
    detect_hw_encoders, auto_select_encoder,
    collect_videos_from_folder,
    estimate_compressed_size,
    estimate_one_file_size,
    PRESET_ESTIMATE_RATIO,
    get_disk_free_bytes,
)
from core.ffmpeg_downloader import (
    download_ffmpeg, is_available as ffmpeg_available, get_download_size_hint,
)

# ── 样式常量 ─────────────────────────────────────────────────

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

_INFO_FRAME = (
    "QFrame{background:#f8f9fa;border:1px solid #dfe2e8;"
    "border-radius:6px;padding:8px;}")

_PROGRESS_STYLE = (
    "QProgressBar{border:1px solid #dfe2e8;background:#e8eaed;"
    "border-radius:3px;text-align:center;font-size:11px;}"
    "QProgressBar::chunk{background:qlineargradient("
    "x1:0,y1:0,x2:1,y2:0,stop:0 #0078d4,stop:1 #00b7c3);"
    "border-radius:3px;}")


# ── FFmpeg 下载线程 ──────────────────────────────────────────

class _DownloadWorker(QThread):
    progress = pyqtSignal(int, int)  # downloaded, total
    finished = pyqtSignal(bool, str)  # success, message_or_path

    def run(self):
        try:
            path = download_ffmpeg(
                progress_cb=lambda dl, total: self.progress.emit(dl, total)
            )
            self.finished.emit(True, path)
        except Exception as e:
            self.finished.emit(False, f"{type(e).__name__}: {e}")


# ── 硬件编码器检测线程 ───────────────────────────────────────

class _HwDetectWorker(QThread):
    done = pyqtSignal(list)

    def run(self):
        self.done.emit(detect_hw_encoders())


# ── 压缩工作线程 ─────────────────────────────────────────────

class _CompressWorker(QThread):
    progress = pyqtSignal(dict)
    log_line = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, cmd, total_duration):
        super().__init__()
        self._cmd = cmd
        self._dur = total_duration
        self._proc = None
        self._cancelled = False

    def run(self):
        try:
            kw = {}
            if os.name == "nt":
                kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
            self._proc = subprocess.Popen(
                self._cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                **kw,
            )

            buf = b""
            while True:
                byte = self._proc.stderr.read(1)
                if not byte:
                    break
                if byte in (b"\r", b"\n"):
                    if buf:
                        line = buf.decode("utf-8", errors="replace")
                        self.log_line.emit(line)
                        p = parse_progress(line, self._dur)
                        if p:
                            self.progress.emit(p)
                        buf = b""
                else:
                    buf += byte

            self._proc.wait()

            if self._cancelled:
                self.finished.emit(False, "已取消")
            elif self._proc.returncode == 0:
                self.finished.emit(True, "压缩完成")
            else:
                self.finished.emit(
                    False, f"FFmpeg 错误 (退出码 {self._proc.returncode})")
        except Exception as e:
            self.finished.emit(False, f"{type(e).__name__}: {e}")

    def cancel(self):
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            self._proc.kill()


# ── 批量压缩工作线程 ───────────────────────────────────────────

class _BatchCompressWorker(QThread):
    """逐个压缩多个视频，发射进度与日志。"""
    progress = pyqtSignal(int, int, float)  # current_index, total, current_file_percent
    log_line = pyqtSignal(str)
    file_done = pyqtSignal(int, bool, str)   # index, success, message
    finished = pyqtSignal(bool, str)

    def __init__(self, tasks, hw_encoders=None):
        super().__init__()
        # tasks: [(input_path, output_path, preset_key), ...]
        self._tasks = list(tasks)
        self._hw_encoders = hw_encoders or []
        self._cancelled = False
        self._proc = None

    def run(self):
        total = len(self._tasks)
        if total == 0:
            self.finished.emit(False, "没有待压缩文件")
            return
        failed = []
        for i, (inp, out, preset_key) in enumerate(self._tasks):
            if self._cancelled:
                self.finished.emit(False, "已取消")
                return
            try:
                info = probe_video(inp)
            except Exception as e:
                self.log_line.emit(f"[{os.path.basename(inp)}] 探测失败: {e}")
                self.file_done.emit(i, False, str(e))
                failed.append(os.path.basename(inp))
                continue
            cfg = CompressConfig.from_preset(preset_key, inp, out)
            cfg.vcodec = auto_select_encoder(cfg.vcodec, self._hw_encoders)
            try:
                cmd = build_command(cfg)
            except Exception as e:
                self.log_line.emit(f"[{os.path.basename(inp)}] 构建命令失败: {e}")
                self.file_done.emit(i, False, str(e))
                failed.append(os.path.basename(inp))
                continue
            os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
            kw = {}
            if os.name == "nt":
                kw["creationflags"] = 0x08000000
            try:
                self._proc = subprocess.Popen(
                    cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, **kw
                )
                buf = b""
                while True:
                    byte = self._proc.stderr.read(1)
                    if not byte:
                        break
                    if byte in (b"\r", b"\n"):
                        if buf:
                            line = buf.decode("utf-8", errors="replace")
                            self.log_line.emit(line)
                            p = parse_progress(line, info.duration)
                            if p:
                                self.progress.emit(i, total, p["percent"])
                            buf = b""
                    else:
                        buf += byte
                self._proc.wait()
            except Exception as e:
                self.log_line.emit(f"[{os.path.basename(inp)}] 执行异常: {e}")
                self.file_done.emit(i, False, str(e))
                failed.append(os.path.basename(inp))
                continue
            if self._cancelled:
                if self._proc and self._proc.poll() is None:
                    self._proc.kill()
                if out and os.path.isfile(out):
                    try:
                        os.remove(out)
                    except OSError:
                        pass
                self.finished.emit(False, "已取消")
                return
            if self._proc.returncode == 0:
                self.progress.emit(i, total, 100.0)
                self.file_done.emit(i, True, "完成")
            else:
                if out and os.path.isfile(out):
                    try:
                        os.remove(out)
                    except OSError:
                        pass
                self.file_done.emit(i, False, f"退出码 {self._proc.returncode}")
                failed.append(os.path.basename(inp))
        if failed:
            self.finished.emit(False, f"部分失败: {', '.join(failed[:5])}{'…' if len(failed) > 5 else ''}")
        else:
            self.finished.emit(True, f"全部完成，共 {total} 个文件")

    def cancel(self):
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            self._proc.kill()


# ── 主面板 ───────────────────────────────────────────────────

class VideoPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info: VideoInfo = None
        self._worker: _CompressWorker = None
        self._batch_worker: _BatchCompressWorker = None
        self._hw_encoders = []
        self._hw_detected = False
        self._start_time = 0
        self._output_path = ""
        self._batch_videos = []       # [(path, size_bytes), ...]
        self._batch_source_dir = ""
        self._batch_output_dir = ""
        self._multi_videos = []       # 单文件页多选: [(path, size), ...]
        self._multi_output_dir = ""   # 多选时的输出文件夹
        self._build_ui()
        self.setAcceptDrops(True)
        self._detect_hw()

    # ── UI 搭建 ──────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(8)

        self._tabs = QTabWidget()
        # ── 单文件页 ──
        single_w = QWidget()
        single_l = QVBoxLayout(single_w)
        single_l.setContentsMargins(0, 0, 0, 0)

        # ── 源文件 ──
        g1 = QGroupBox("源文件")
        g1l = QVBoxLayout(g1)

        file_row = QHBoxLayout()
        self._open_btn = QPushButton("选择视频文件")
        self._open_btn.setFixedHeight(32)
        self._open_btn.setStyleSheet(_BTN_PRIMARY)
        self._open_btn.clicked.connect(self._pick_file)
        file_row.addWidget(self._open_btn)
        self._open_multi_btn = QPushButton("选择多个视频")
        self._open_multi_btn.setFixedHeight(32)
        self._open_multi_btn.setStyleSheet(_BTN_PRIMARY)
        self._open_multi_btn.clicked.connect(self._pick_multi_files)
        file_row.addWidget(self._open_multi_btn)
        self._file_label = QLabel("拖放或点击选择视频文件")
        self._file_label.setStyleSheet("color:#6b7a8d;font-size:12px;")
        file_row.addWidget(self._file_label, stretch=1)
        g1l.addLayout(file_row)

        self._info_frame = QFrame()
        self._info_frame.setStyleSheet(_INFO_FRAME)
        self._info_frame.setVisible(False)
        ifl = QVBoxLayout(self._info_frame)
        ifl.setContentsMargins(10, 8, 10, 8)
        ifl.setSpacing(3)
        self._lbl_video = QLabel()
        self._lbl_video.setStyleSheet(
            "font-size:12px;color:#1e2433;border:none;background:transparent;")
        self._lbl_audio = QLabel()
        self._lbl_audio.setStyleSheet(
            "font-size:12px;color:#1e2433;border:none;background:transparent;")
        self._lbl_file = QLabel()
        self._lbl_file.setStyleSheet(
            "font-size:12px;color:#6b7a8d;border:none;background:transparent;")
        ifl.addWidget(self._lbl_video)
        ifl.addWidget(self._lbl_audio)
        ifl.addWidget(self._lbl_file)
        g1l.addWidget(self._info_frame)
        single_l.addWidget(g1)

        # ── 压缩设置 ──
        g2 = QGroupBox("压缩设置")
        g2l = QVBoxLayout(g2)

        preset_row = QHBoxLayout()
        self._preset_group = QButtonGroup(self)
        self._preset_btns = {}
        for i, (key, p) in enumerate(PRESETS.items()):
            rb = QRadioButton(p["name"])
            rb.setToolTip(p["desc"])
            self._preset_group.addButton(rb, i)
            self._preset_btns[key] = rb
            preset_row.addWidget(rb)
        rb_custom = QRadioButton("自定义")
        rb_custom.setToolTip("手动配置所有编码参数")
        self._preset_group.addButton(rb_custom, len(PRESETS))
        self._preset_btns["custom"] = rb_custom
        preset_row.addWidget(rb_custom)
        preset_row.addStretch()
        g2l.addLayout(preset_row)

        self._preset_desc = QLabel(PRESETS["balanced"]["desc"])
        self._preset_desc.setStyleSheet(
            "color:#6b7a8d;font-size:11px;padding:2px 4px;")
        g2l.addWidget(self._preset_desc)

        self._preset_btns["balanced"].setChecked(True)
        self._preset_group.buttonClicked.connect(self._on_preset_changed)

        # 自定义面板
        self._custom_widget = QWidget()
        self._custom_widget.setVisible(False)
        cl = QVBoxLayout(self._custom_widget)
        cl.setContentsMargins(0, 4, 0, 0)
        cl.setSpacing(6)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("编码器:"))
        self._codec_combo = QComboBox()
        for codec, name in CODECS:
            self._codec_combo.addItem(name, codec)
        self._codec_combo.setCurrentIndex(1)
        self._codec_combo.setMinimumWidth(220)
        self._codec_combo.setFixedHeight(28)
        r1.addWidget(self._codec_combo)
        r1.addSpacing(16)
        r1.addWidget(QLabel("CRF:"))
        self._crf_spin = QSpinBox()
        self._crf_spin.setRange(0, 51)
        self._crf_spin.setValue(20)
        self._crf_spin.setFixedHeight(28)
        self._crf_spin.setToolTip(
            "0 = 无损  18 = 视觉无损  23 = 高质量  28 = 中等\n"
            "越低画质越好、文件越大")
        r1.addWidget(self._crf_spin)
        self._crf_hint = QLabel("高画质")
        self._crf_hint.setStyleSheet("color:#107c10;font-size:11px;")
        r1.addWidget(self._crf_hint)
        self._crf_spin.valueChanged.connect(self._on_crf_changed)
        r1.addStretch()
        cl.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("编码速度:"))
        self._speed_combo = QComboBox()
        for speed, name in SPEEDS:
            self._speed_combo.addItem(name, speed)
        self._speed_combo.setCurrentIndex(5)
        self._speed_combo.setMinimumWidth(160)
        self._speed_combo.setFixedHeight(28)
        r2.addWidget(self._speed_combo)
        r2.addSpacing(16)
        r2.addWidget(QLabel("分辨率:"))
        self._res_combo = QComboBox()
        for w, h, name in RESOLUTIONS:
            self._res_combo.addItem(name, (w, h))
        self._res_combo.setMinimumWidth(180)
        self._res_combo.setFixedHeight(28)
        r2.addWidget(self._res_combo)
        r2.addStretch()
        cl.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(QLabel("音频:"))
        self._audio_combo = QComboBox()
        for mode, name in AUDIO_OPTS:
            self._audio_combo.addItem(name, mode)
        self._audio_combo.setCurrentIndex(2)
        self._audio_combo.setMinimumWidth(180)
        self._audio_combo.setFixedHeight(28)
        r3.addWidget(self._audio_combo)
        r3.addStretch()
        cl.addLayout(r3)

        self._hw_label = QLabel()
        self._hw_label.setStyleSheet("color:#8764b8;font-size:11px;")
        self._hw_label.setVisible(False)
        cl.addWidget(self._hw_label)

        g2l.addWidget(self._custom_widget)
        single_l.addWidget(g2)

        # ── 输出 ──
        g3 = QGroupBox("输出")
        g3l = QHBoxLayout(g3)
        self._out_btn = QPushButton("选择输出路径")
        self._out_btn.setFixedHeight(30)
        self._out_btn.clicked.connect(self._pick_output)
        g3l.addWidget(self._out_btn)
        self._out_label = QLabel("将自动生成输出路径")
        self._out_label.setStyleSheet("color:#6b7a8d;font-size:12px;")
        g3l.addWidget(self._out_label, stretch=1)
        single_l.addWidget(g3)

        single_l.addStretch()
        self._tabs.addTab(single_w, "单文件")

        # ── 批量（文件夹）页 ──
        self._batch_tab_widget = QWidget()
        bl = QVBoxLayout(self._batch_tab_widget)
        bl.setContentsMargins(0, 0, 0, 0)

        bg1 = QGroupBox("源文件夹")
        bg1l = QVBoxLayout(bg1)
        brow1 = QHBoxLayout()
        self._batch_src_btn = QPushButton("选择源文件夹")
        self._batch_src_btn.setFixedHeight(32)
        self._batch_src_btn.setStyleSheet(_BTN_PRIMARY)
        self._batch_src_btn.clicked.connect(self._pick_batch_source)
        brow1.addWidget(self._batch_src_btn)
        self._batch_recursive = QCheckBox("包含子文件夹（递归）")
        self._batch_recursive.setChecked(True)
        self._batch_recursive.stateChanged.connect(self._refresh_batch_list)
        brow1.addWidget(self._batch_recursive)
        brow1.addStretch()
        bg1l.addLayout(brow1)
        self._batch_src_label = QLabel("未选择文件夹")
        self._batch_src_label.setStyleSheet("color:#6b7a8d;font-size:12px;")
        bg1l.addWidget(self._batch_src_label)
        self._batch_summary = QLabel("")
        self._batch_summary.setStyleSheet("color:#1e2433;font-size:12px;")
        self._batch_summary.setWordWrap(True)
        bg1l.addWidget(self._batch_summary)
        bl.addWidget(bg1)

        bg2 = QGroupBox("压缩方式")
        bg2l = QVBoxLayout(bg2)
        self._batch_mode_unified = QRadioButton("所有视频统一使用当前预设")
        self._batch_mode_per = QRadioButton("每个视频单独设置")
        self._batch_mode_unified.setChecked(True)
        self._batch_mode_unified.toggled.connect(self._on_batch_mode_changed)
        bg2l.addWidget(self._batch_mode_unified)
        bg2l.addWidget(self._batch_mode_per)
        self._batch_unified_row = QWidget()
        preset_row_b = QHBoxLayout(self._batch_unified_row)
        preset_row_b.setContentsMargins(0, 0, 0, 0)
        preset_row_b.addWidget(QLabel("统一预设:"))
        self._batch_unified_preset = QComboBox()
        for key, p in PRESETS.items():
            self._batch_unified_preset.addItem(p["name"], key)
        self._batch_unified_preset.currentIndexChanged.connect(self._update_batch_estimate)
        preset_row_b.addWidget(self._batch_unified_preset)
        preset_row_b.addStretch()
        bg2l.addWidget(self._batch_unified_row)
        self._batch_table = QTableWidget()
        self._batch_table.setColumnCount(4)
        self._batch_table.setHorizontalHeaderLabels(["文件名", "预设", "原始大小", "预估大小"])
        self._batch_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._batch_table.setVisible(False)
        bg2l.addWidget(self._batch_table)
        bl.addWidget(bg2)

        bg3 = QGroupBox("输出")
        bg3l = QVBoxLayout(bg3)
        brow3 = QHBoxLayout()
        self._batch_out_btn = QPushButton("选择输出文件夹")
        self._batch_out_btn.setFixedHeight(30)
        self._batch_out_btn.clicked.connect(self._pick_batch_output)
        brow3.addWidget(self._batch_out_btn)
        self._batch_out_label = QLabel("请先选择输出文件夹（将保持子目录结构）")
        self._batch_out_label.setStyleSheet("color:#6b7a8d;font-size:12px;")
        brow3.addWidget(self._batch_out_label, stretch=1)
        bg3l.addLayout(brow3)
        self._batch_estimate_label = QLabel("")
        self._batch_estimate_label.setStyleSheet("color:#107c10;font-size:11px;")
        bg3l.addWidget(self._batch_estimate_label)
        bl.addWidget(bg3)
        bl.addStretch()
        self._tabs.addTab(self._batch_tab_widget, "批量（文件夹）")

        root.addWidget(self._tabs, stretch=1)

        # ── 操作行 ──
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

        # ── 进度 ──
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

        # ── 结果 ──
        self._result_frame = QFrame()
        self._result_frame.setVisible(False)
        rfl = QVBoxLayout(self._result_frame)
        rfl.setContentsMargins(10, 8, 10, 8)
        rfl.setSpacing(4)
        self._result_label = QLabel()
        self._result_label.setWordWrap(True)
        self._result_label.setStyleSheet(
            "font-size:13px;color:#1e2433;font-weight:bold;"
            "border:none;background:transparent;")
        rfl.addWidget(self._result_label)
        rbr = QHBoxLayout()
        self._open_folder_btn = QPushButton("打开输出文件夹")
        self._open_folder_btn.setFixedHeight(28)
        self._open_folder_btn.clicked.connect(self._open_folder)
        rbr.addWidget(self._open_folder_btn)
        rbr.addStretch()
        rfl.addLayout(rbr)
        root.addWidget(self._result_frame)

        # ── 日志 ──
        self._log_btn = QPushButton("显示日志 ▾")
        self._log_btn.setFixedHeight(24)
        self._log_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#6b7a8d;"
            "font-size:11px;border:none;text-align:left;padding:0;}"
            "QPushButton:hover{color:#0078d4;}")
        self._log_btn.clicked.connect(self._toggle_log)
        root.addWidget(self._log_btn)

        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setFont(QFont("Consolas", 9))
        self._log_area.setMaximumHeight(150)
        self._log_area.setStyleSheet(
            "QTextEdit{background:#1e1e1e;color:#cccccc;"
            "border:1px solid #333;border-radius:4px;}")
        self._log_area.setVisible(False)
        root.addWidget(self._log_area)

        root.addStretch()

        # ── 状态栏 ──
        self._status = QLabel(
            "就绪 — 支持 MP4 / MKV / AVI / M2TS / MOV / FLV / WebM 等格式")
        self._status.setStyleSheet("color:#666;font-size:11px;")
        root.addWidget(self._status)

    # ── 硬件加速检测 ─────────────────────────────────────────

    def _detect_hw(self):
        if not find_ffmpeg():
            return
        self._hw_detect_worker = _HwDetectWorker()
        self._hw_detect_worker.done.connect(self._on_hw_detected)
        self._hw_detect_worker.start()

    def _on_hw_detected(self, encoders):
        self._hw_encoders = encoders
        self._hw_detected = True
        if not encoders:
            return
        names = ", ".join(n for _, n in encoders)
        # 填充自定义模式的编码器下拉框
        for codec, name in encoders:
            if self._codec_combo.findData(codec) == -1:
                self._codec_combo.addItem(f"{name} (硬件)", codec)
        self._hw_label.setText(f"检测到硬件编码器: {names}")
        self._status.setText(
            f"GPU 硬件加速可用: {names}  —  使用预设时将自动启用")

    # ── Drag & Drop ──────────────────────────────────────────

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            for url in e.mimeData().urls():
                if url.toLocalFile().lower().endswith(VIDEO_EXTS):
                    e.acceptProposedAction()
                    return

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if p.lower().endswith(VIDEO_EXTS):
                self._load_file(p)
                return

    # ── 文件操作 ─────────────────────────────────────────────

    def _pick_file(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", VIDEO_FILTER)
        if p:
            self._load_file(p)

    def _pick_multi_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择多个视频", "", VIDEO_FILTER)
        if not paths:
            return
        self._info = None
        self._info_frame.setVisible(False)
        self._multi_videos = []
        for p in paths:
            try:
                self._multi_videos.append((p, os.path.getsize(p)))
            except OSError:
                pass
        if not self._multi_videos:
            return
        self._file_label.setText(f"已选 {len(self._multi_videos)} 个视频")
        self._multi_output_dir = ""
        self._out_label.setText("请选择输出文件夹（多选批量）")
        self._result_frame.setVisible(False)
        self._status.setText(f"已选 {len(self._multi_videos)} 个视频，请选择输出文件夹后开始压缩")

    def _load_file(self, path):
        self._status.setText("正在读取视频信息…")
        QApplication.processEvents()
        try:
            info = probe_video(path)
        except FileNotFoundError as e:
            size_hint = get_download_size_hint()
            r = QMessageBox.question(
                self, "FFmpeg 未安装",
                f"{e}\n\n是否自动下载 FFmpeg 到本地目录？\n"
                f"（{size_hint}，来源: BtbN/FFmpeg-Builds GPL 静态构建）",
                QMessageBox.Yes | QMessageBox.No)
            if r == QMessageBox.Yes:
                self._pending_load_path = path
                self._start_ffmpeg_download()
            else:
                self._status.setText("就绪")
            return
        except Exception as e:
            QMessageBox.warning(self, "读取失败", str(e))
            self._status.setText("就绪")
            return

        self._multi_videos = []
        self._multi_output_dir = ""
        self._info = info
        self._file_label.setText(os.path.basename(path))

        self._lbl_video.setText(
            f"视频: {info.video_codec.upper()}  {info.resolution_str}  "
            f"{info.fps:.3g} fps  {info.video_bitrate_str}")
        self._lbl_audio.setText(f"音频: {info.audio_info_str}")
        self._lbl_file.setText(
            f"时长: {info.duration_str}  大小: {info.file_size_str}")
        self._info_frame.setVisible(True)

        base, _ = os.path.splitext(path)
        self._output_path = f"{base}_compressed.mp4"
        self._out_label.setText(os.path.basename(self._output_path))

        self._status.setText(f"已加载: {os.path.basename(path)}")
        self._result_frame.setVisible(False)

    def _get_single_preset_key(self):
        """单文件页当前选中的预设 key（自定义时返回 balanced）。"""
        for key, rb in self._preset_btns.items():
            if rb.isChecked() and key in PRESETS:
                return key
        return "balanced"

    def _pick_output(self):
        if self._multi_videos:
            folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹（多选批量）")
            if folder:
                preset = self._get_single_preset_key()
                est = sum(estimate_one_file_size(s, preset) for _, s in self._multi_videos)
                free = get_disk_free_bytes(folder)
                if free > 0 and est > free:
                    r = QMessageBox.warning(
                        self, "空间可能不足",
                        f"预估压缩后约 {_fmt_size(est)}，该磁盘可用 {_fmt_size(free)}，可能不足。\n\n是否仍要选择？",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if r != QMessageBox.Yes:
                        return
                self._multi_output_dir = folder
                self._out_label.setText(folder)
            return
        default = self._output_path or "output.mp4"
        p, filt = QFileDialog.getSaveFileName(
            self, "保存压缩视频", default, OUTPUT_FILTER)
        if p:
            _, ext = os.path.splitext(p)
            if not ext:
                if "MKV" in filt:
                    p += ".mkv"
                elif "WebM" in filt:
                    p += ".webm"
                else:
                    p += ".mp4"
            self._output_path = p
            self._out_label.setText(os.path.basename(p))

    # ── FFmpeg 下载 ────────────────────────────────────────────

    def _start_ffmpeg_download(self):
        self._progress.setVisible(True)
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
        self._progress_label.setVisible(True)
        self._progress_label.setText("正在下载 FFmpeg …")
        self._status.setText("正在下载 FFmpeg …")
        self._open_btn.setEnabled(False)

        self._dl_worker = _DownloadWorker()
        self._dl_worker.progress.connect(self._on_dl_progress)
        self._dl_worker.finished.connect(self._on_dl_finished)
        self._dl_worker.start()

    def _on_dl_progress(self, downloaded, total):
        if total > 0:
            pct = downloaded / total * 100
            self._progress.setValue(int(pct * 10))
            self._progress_label.setText(
                f"正在下载 FFmpeg … {downloaded // (1024*1024)} / "
                f"{total // (1024*1024)} MB  ({pct:.0f}%)")
        else:
            self._progress_label.setText(
                f"正在下载 FFmpeg … {downloaded // (1024*1024)} MB")

    def _on_dl_finished(self, success, msg):
        self._progress.setVisible(False)
        self._progress_label.setVisible(False)
        self._open_btn.setEnabled(True)

        if success:
            self._status.setText(f"FFmpeg 已就绪: {msg}")
            QMessageBox.information(
                self, "下载完成",
                f"FFmpeg 已下载到:\n{msg}\n\n现在可以正常使用视频压缩功能。")
            pending = getattr(self, "_pending_load_path", None)
            if pending:
                self._pending_load_path = None
                self._load_file(pending)
        else:
            self._status.setText("FFmpeg 下载失败")
            QMessageBox.critical(
                self, "下载失败",
                f"FFmpeg 下载失败:\n{msg}\n\n"
                "你也可以手动下载 FFmpeg 并放入 vendor/ffmpeg/ 目录:\n"
                "https://github.com/BtbN/FFmpeg-Builds/releases")

    # ── 预设切换 ─────────────────────────────────────────────

    def _on_preset_changed(self, btn):
        is_custom = btn is self._preset_btns.get("custom")
        self._custom_widget.setVisible(is_custom)

        if is_custom:
            self._hw_label.setVisible(bool(self._hw_encoders))
            self._preset_desc.setText("手动配置编码参数")
        else:
            for key, rb in self._preset_btns.items():
                if rb is btn and key in PRESETS:
                    self._preset_desc.setText(PRESETS[key]["desc"])
                    break

    def _on_crf_changed(self, val):
        if val <= 15:
            txt, color = "极高画质 (文件较大)", "#0078d4"
        elif val <= 20:
            txt, color = "高画质 (推荐)", "#107c10"
        elif val <= 25:
            txt, color = "中高画质", "#ca5010"
        elif val <= 30:
            txt, color = "中等画质", "#d13438"
        else:
            txt, color = "低画质 (文件很小)", "#d13438"
        self._crf_hint.setText(txt)
        self._crf_hint.setStyleSheet(f"color:{color};font-size:11px;")

    # ── 构建配置 ─────────────────────────────────────────────

    def _build_config(self) -> CompressConfig:
        if not self._output_path:
            raise ValueError("请选择输出路径")

        is_custom = self._preset_btns["custom"].isChecked()

        if is_custom:
            cfg = CompressConfig(
                input_path=self._info.path,
                output_path=self._output_path,
                vcodec=self._codec_combo.currentData(),
                crf=self._crf_spin.value(),
                speed=self._speed_combo.currentData(),
                audio_mode=self._audio_combo.currentData(),
            )
            w, h = self._res_combo.currentData()
            if w > 0 and self._info and w < self._info.width:
                cfg.target_width = w
                cfg.target_height = h
        else:
            preset_key = "balanced"
            for key, rb in self._preset_btns.items():
                if rb.isChecked() and key in PRESETS:
                    preset_key = key
                    break
            cfg = CompressConfig.from_preset(
                preset_key, self._info.path, self._output_path)
            cfg.vcodec = auto_select_encoder(cfg.vcodec, self._hw_encoders)

        return cfg

    # ── 开始 / 取消 ──────────────────────────────────────────

    def _start(self):
        # 根据当前标签页执行单文件或批量
        if self._tabs.currentWidget() == self._batch_tab_widget:
            self._start_batch()
            return
        if self._multi_videos:
            self._start_batch_from_multi()
            return
        if not self._info:
            QMessageBox.information(self, "提示", "请先选择视频文件")
            return
        if self._worker and self._worker.isRunning():
            return

        try:
            cfg = self._build_config()
            cmd = build_command(cfg)
        except Exception as e:
            QMessageBox.warning(self, "配置错误", str(e))
            return

        if os.path.isfile(cfg.output_path):
            r = QMessageBox.question(
                self, "文件已存在",
                f"输出文件已存在:\n{cfg.output_path}\n\n是否覆盖?",
                QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                return

        self._log_area.clear()
        self._log_area.append(f"命令: {' '.join(cmd)}\n")
        self._result_frame.setVisible(False)

        self._start_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.setVisible(True)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._progress_label.setVisible(True)
        self._progress_label.setText("正在压缩…")
        self._status.setText("正在压缩…")

        self._start_time = time.time()
        self._worker = _CompressWorker(cmd, self._info.duration)
        self._worker.progress.connect(self._on_progress)
        self._worker.log_line.connect(self._on_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _cancel(self):
        if self._batch_worker and self._batch_worker.isRunning():
            self._batch_worker.cancel()
        elif self._worker:
            self._worker.cancel()
        self._cancel_btn.setEnabled(False)
        self._status.setText("正在取消…")

    # ── 回调 ─────────────────────────────────────────────────

    def _on_progress(self, p):
        pct = p["percent"]
        self._progress.setValue(int(pct * 10))

        parts = [f"{pct:.1f}%"]
        spd = p["speed"]
        if spd > 0:
            parts.append(f"速度: {spd:.2f}x")
        eta = p["eta"]
        if eta > 0:
            em, es = divmod(int(eta), 60)
            eh, em = divmod(em, 60)
            if eh:
                parts.append(f"剩余: {eh}:{em:02d}:{es:02d}")
            else:
                parts.append(f"剩余: {em}:{es:02d}")

        self._progress_label.setText("    ".join(parts))

    def _on_log(self, line):
        self._log_area.append(line)

    def _on_finished(self, success, msg):
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setVisible(False)
        self._progress.setVisible(False)
        self._progress_label.setVisible(False)

        elapsed = time.time() - self._start_time
        em, es = divmod(int(elapsed), 60)
        eh, em = divmod(em, 60)
        elapsed_str = f"{eh}:{em:02d}:{es:02d}" if eh else f"{em}:{es:02d}"

        if success and os.path.isfile(self._output_path):
            out_size = os.path.getsize(self._output_path)
            in_size = self._info.file_size
            saved = in_size - out_size
            pct = saved / in_size * 100 if in_size > 0 else 0

            self._result_frame.setStyleSheet(
                "QFrame{background:#f0fff0;border:1px solid #107c10;"
                "border-radius:6px;padding:8px;}")
            self._result_label.setText(
                f"压缩完成！\n"
                f"原始: {_fmt_size(in_size)} → 压缩后: {_fmt_size(out_size)}    "
                f"节省: {_fmt_size(saved)} ({pct:.1f}%)\n"
                f"耗时: {elapsed_str}")
            self._result_frame.setVisible(True)
            self._status.setText(
                f"压缩完成 — {_fmt_size(out_size)} (节省 {pct:.1f}%)")
        else:
            if self._output_path and os.path.isfile(self._output_path):
                try:
                    os.remove(self._output_path)
                except OSError:
                    pass
            self._result_frame.setStyleSheet(
                "QFrame{background:#fff0f0;border:1px solid #d13438;"
                "border-radius:6px;padding:8px;}")
            self._result_label.setText(f"压缩失败: {msg}\n耗时: {elapsed_str}")
            self._result_frame.setVisible(True)
            self._status.setText(f"失败: {msg}")

    # ── 辅助 ─────────────────────────────────────────────────

    def _toggle_log(self):
        vis = not self._log_area.isVisible()
        self._log_area.setVisible(vis)
        self._log_btn.setText("隐藏日志 ▴" if vis else "显示日志 ▾")

    def _open_folder(self):
        if not self._output_path:
            return
        folder = self._output_path if os.path.isdir(self._output_path) else os.path.dirname(os.path.abspath(self._output_path))
        if folder and os.path.exists(folder):
            if os.name == "nt":
                os.startfile(folder)
            else:
                subprocess.Popen(["xdg-open", folder])

    # ── 批量压缩 ─────────────────────────────────────────────

    def _pick_batch_source(self):
        folder = QFileDialog.getExistingDirectory(self, "选择源文件夹")
        if not folder:
            return
        self._batch_source_dir = folder
        self._batch_src_label.setText(folder)
        self._refresh_batch_list()

    def _refresh_batch_list(self):
        if not self._batch_source_dir or not os.path.isdir(self._batch_source_dir):
            self._batch_videos = []
            self._batch_summary.setText("")
            self._batch_estimate_label.setText("")
            self._batch_table.setRowCount(0)
            self._batch_table.setVisible(False)
            return
        recursive = self._batch_recursive.isChecked()
        paths = collect_videos_from_folder(self._batch_source_dir, recursive=recursive)
        self._batch_videos = []
        for p in paths:
            try:
                size = os.path.getsize(p)
                self._batch_videos.append((p, size))
            except OSError:
                pass
        total_size = sum(s for _, s in self._batch_videos)
        self._batch_summary.setText(
            f"找到 {len(self._batch_videos)} 个视频，总大小 {_fmt_size(total_size)}"
        )
        self._update_batch_estimate()
        # 表格：每个视频一行
        self._batch_table.setRowCount(len(self._batch_videos))
        preset_keys = list(PRESETS.keys())
        for i, (path, size) in enumerate(self._batch_videos):
            self._batch_table.setItem(i, 0, QTableWidgetItem(os.path.basename(path)))
            combo = QComboBox()
            for key, p in PRESETS.items():
                combo.addItem(p["name"], key)
            combo.setCurrentIndex(1)  # balanced
            combo.currentIndexChanged.connect(self._update_batch_estimate)
            self._batch_table.setCellWidget(i, 1, combo)
            self._batch_table.setItem(i, 2, QTableWidgetItem(_fmt_size(size)))
            est = estimate_one_file_size(size, "balanced")
            self._batch_table.setItem(i, 3, QTableWidgetItem(_fmt_size(est)))
        self._batch_table.setVisible(self._batch_mode_per.isChecked())

    def _on_batch_mode_changed(self):
        unified = self._batch_mode_unified.isChecked()
        self._batch_unified_row.setVisible(unified)
        self._batch_table.setVisible(not unified and len(self._batch_videos) > 0)
        self._update_batch_estimate()

    def _update_batch_estimate(self):
        if not self._batch_videos:
            self._batch_estimate_label.setText("")
            return
        if self._batch_mode_unified.isChecked():
            preset_key = self._batch_unified_preset.currentData()
            total_orig = sum(s for _, s in self._batch_videos)
            est_bytes = estimate_compressed_size(self._batch_videos, preset_key)
            ratio = (est_bytes / total_orig * 100) if total_orig else 0
            self._batch_estimate_label.setText(
                f"预估压缩后总大小约 {_fmt_size(est_bytes)}（约为原大小的 {ratio:.0f}%）"
            )
        else:
            est_total = 0
            for i in range(self._batch_table.rowCount()):
                combo = self._batch_table.cellWidget(i, 1)
                if combo:
                    preset_key = combo.currentData()
                    _, size = self._batch_videos[i]
                    est_total += estimate_one_file_size(size, preset_key)
            total_orig = sum(s for _, s in self._batch_videos)
            ratio = (est_total / total_orig * 100) if total_orig else 0
            self._batch_estimate_label.setText(
                f"预估压缩后总大小约 {_fmt_size(est_total)}（约为原大小的 {ratio:.0f}%）"
            )
        # 更新表格中每行预估
        if self._batch_mode_per.isChecked():
            for i in range(self._batch_table.rowCount()):
                combo = self._batch_table.cellWidget(i, 1)
                if combo:
                    _, size = self._batch_videos[i]
                    est = estimate_one_file_size(size, combo.currentData())
                    self._batch_table.setItem(i, 3, QTableWidgetItem(_fmt_size(est)))

    def _pick_batch_output(self):
        if not self._batch_videos:
            QMessageBox.information(self, "提示", "请先选择源文件夹并确认已扫描到视频文件")
            return
        # 计算当前预估总大小
        if self._batch_mode_unified.isChecked():
            preset_key = self._batch_unified_preset.currentData()
            est_bytes = estimate_compressed_size(self._batch_videos, preset_key)
        else:
            est_bytes = 0
            for i in range(self._batch_table.rowCount()):
                combo = self._batch_table.cellWidget(i, 1)
                if combo:
                    est_bytes += estimate_one_file_size(self._batch_videos[i][1], combo.currentData())
        folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if not folder:
            return
        free = get_disk_free_bytes(folder)
        if free > 0 and est_bytes > free:
            r = QMessageBox.warning(
                self, "空间可能不足",
                f"预估压缩后总大小约 {_fmt_size(est_bytes)}，该磁盘可用空间 {_fmt_size(free)}，可能不足。\n\n是否仍要选择此文件夹？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if r != QMessageBox.Yes:
                return
        self._batch_output_dir = folder
        self._batch_out_label.setText(folder)

    def _start_batch_from_multi(self):
        """单文件页多选后批量压缩。"""
        if not self._multi_videos:
            QMessageBox.information(self, "提示", "请先选择多个视频")
            return
        if not self._multi_output_dir or not os.path.isdir(self._multi_output_dir):
            QMessageBox.information(self, "提示", "请先选择输出文件夹")
            return
        if self._batch_worker and self._batch_worker.isRunning():
            return
        preset = self._get_single_preset_key()
        out_dir = os.path.normpath(self._multi_output_dir)
        tasks = []
        used = {}
        for path, _ in self._multi_videos:
            base, ext = os.path.splitext(os.path.basename(path))
            key = base + "_compressed" + ext
            if key in used:
                used[key] += 1
                out_name = f"{base}_compressed_{used[key]}{ext}"
            else:
                used[key] = 1
                out_name = key
            out_path = os.path.join(out_dir, out_name)
            tasks.append((path, out_path, preset))
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
        self._status.setText("批量压缩中…")
        self._batch_worker = _BatchCompressWorker(tasks, hw_encoders=self._hw_encoders)
        self._batch_worker.progress.connect(self._on_batch_progress)
        self._batch_worker.log_line.connect(self._on_log)
        self._batch_worker.finished.connect(self._on_batch_finished)
        self._batch_worker.start()

    def _start_batch(self):
        if not self._batch_videos:
            QMessageBox.information(self, "提示", "请先选择源文件夹")
            return
        if not self._batch_output_dir or not os.path.isdir(self._batch_output_dir):
            QMessageBox.information(self, "提示", "请先选择输出文件夹")
            return
        if self._batch_worker and self._batch_worker.isRunning():
            return
        # 构建任务列表：(input_path, output_path, preset_key)
        tasks = []
        src = os.path.normpath(self._batch_source_dir)
        out_dir = os.path.normpath(self._batch_output_dir)
        for i, (path, _) in enumerate(self._batch_videos):
            rel = os.path.relpath(path, src)
            base, ext = os.path.splitext(rel)
            new_rel = base + "_compressed" + ext
            out_path = os.path.join(out_dir, new_rel)
            if self._batch_mode_unified.isChecked():
                preset_key = self._batch_unified_preset.currentData()
            else:
                combo = self._batch_table.cellWidget(i, 1)
                preset_key = combo.currentData() if combo else "balanced"
            tasks.append((path, out_path, preset_key))
        self._log_area.clear()
        self._log_area.setVisible(True)
        self._log_btn.setText("隐藏日志 ▴")
        self._start_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.setVisible(True)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._progress_label.setVisible(True)
        self._progress_label.setText("准备中…")
        self._result_frame.setVisible(False)
        self._status.setText("批量压缩中…")
        self._batch_worker = _BatchCompressWorker(tasks, hw_encoders=self._hw_encoders)
        self._batch_worker.progress.connect(self._on_batch_progress)
        self._batch_worker.log_line.connect(self._on_log)
        self._batch_worker.finished.connect(self._on_batch_finished)
        self._batch_worker.start()

    def _on_batch_progress(self, idx, total, pct):
        overall = (idx * 100.0 + pct) / total if total else 0
        self._progress.setValue(int(overall * 10))
        self._progress_label.setText(f"当前 {idx + 1}/{total} · 本文件 {pct:.1f}%")

    def _on_batch_finished(self, success, msg):
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setVisible(False)
        self._progress.setVisible(False)
        self._progress_label.setVisible(False)
        self._output_path = self._multi_output_dir or self._batch_output_dir  # 便于“打开输出文件夹”
        self._result_frame.setStyleSheet(
            "QFrame{background:#f0fff0;border:1px solid #107c10;"
            "border-radius:6px;padding:8px;}" if success else
            "QFrame{background:#fff0f0;border:1px solid #d13438;"
            "border-radius:6px;padding:8px;}")
        self._result_label.setText(msg)
        self._result_frame.setVisible(True)
        self._status.setText("批量压缩完成" if success else msg)


def _fmt_size(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024:.0f} KB"
