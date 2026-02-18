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
    QSpinBox, QTextEdit, QApplication,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from core.video_compress import (
    find_ffmpeg, probe_video, VideoInfo,
    PRESETS, CODECS, SPEEDS, RESOLUTIONS, AUDIO_OPTS,
    CompressConfig, build_command, parse_progress,
    VIDEO_EXTS, VIDEO_FILTER, OUTPUT_FILTER,
    detect_hw_encoders,
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


# ── 主面板 ───────────────────────────────────────────────────

class VideoPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info: VideoInfo = None
        self._worker: _CompressWorker = None
        self._hw_encoders = []
        self._hw_detected = False
        self._start_time = 0
        self._output_path = ""
        self._build_ui()
        self.setAcceptDrops(True)

    # ── UI 搭建 ──────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(8)

        # ── 源文件 ──
        g1 = QGroupBox("源文件")
        g1l = QVBoxLayout(g1)

        file_row = QHBoxLayout()
        self._open_btn = QPushButton("选择视频文件")
        self._open_btn.setFixedHeight(32)
        self._open_btn.setStyleSheet(_BTN_PRIMARY)
        self._open_btn.clicked.connect(self._pick_file)
        file_row.addWidget(self._open_btn)
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
        root.addWidget(g1)

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
        r1.addWidget(self._codec_combo)
        r1.addSpacing(16)
        r1.addWidget(QLabel("CRF:"))
        self._crf_spin = QSpinBox()
        self._crf_spin.setRange(0, 51)
        self._crf_spin.setValue(20)
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
        r2.addWidget(self._speed_combo)
        r2.addSpacing(16)
        r2.addWidget(QLabel("分辨率:"))
        self._res_combo = QComboBox()
        for w, h, name in RESOLUTIONS:
            self._res_combo.addItem(name, (w, h))
        self._res_combo.setMinimumWidth(180)
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
        r3.addWidget(self._audio_combo)
        r3.addStretch()
        cl.addLayout(r3)

        self._hw_label = QLabel()
        self._hw_label.setStyleSheet("color:#8764b8;font-size:11px;")
        self._hw_label.setVisible(False)
        cl.addWidget(self._hw_label)

        g2l.addWidget(self._custom_widget)
        root.addWidget(g2)

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
        root.addWidget(g3)

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

    def _pick_output(self):
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
            if not self._hw_detected:
                self._hw_detected = True
                self._hw_encoders = detect_hw_encoders()
                if self._hw_encoders:
                    for codec, name in self._hw_encoders:
                        self._codec_combo.addItem(f"{name} (硬件)", codec)
                    names = ", ".join(n for _, n in self._hw_encoders)
                    self._hw_label.setText(f"检测到硬件编码器: {names}")
                    self._hw_label.setVisible(True)
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

        return cfg

    # ── 开始 / 取消 ──────────────────────────────────────────

    def _start(self):
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
        if self._worker:
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
        if self._output_path and os.path.isfile(self._output_path):
            folder = os.path.dirname(os.path.abspath(self._output_path))
            if os.name == "nt":
                os.startfile(folder)
            else:
                subprocess.Popen(["xdg-open", folder])


def _fmt_size(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024:.0f} KB"
