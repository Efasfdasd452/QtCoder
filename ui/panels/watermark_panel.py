# -*- coding: utf-8 -*-
"""隐藏水印检测 / 嵌入 / 提取面板

三个 Tab:
  1. 水印检测 — FFT/DCT/位平面/小波等多维度分析
  2. 嵌入水印 — 使用 blind_watermark 嵌入文字或图片盲水印
  3. 提取水印 — 使用 blind_watermark 提取盲水印
"""

import os
import cv2
import numpy as np

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QComboBox, QScrollArea, QGridLayout, QFrame,
    QGroupBox, QMessageBox, QSizePolicy, QApplication,
    QProgressBar, QSplitter, QTabWidget, QLineEdit, QSpinBox,
    QRadioButton, QButtonGroup, QTextEdit,
)
from PyQt5.QtGui import QImage, QPixmap, QFont, QCursor
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize

from core.watermark_detector import (
    DETECT_METHODS, run_detection, run_all_quick,
    bwm_embed_text, bwm_extract_text,
    bwm_embed_image, bwm_extract_image,
)

# ═══════════════════════════════════════════════════════════════
#  样式常量
# ═══════════════════════════════════════════════════════════════

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

_BTN_ORANGE = (
    "QPushButton{background:#ca5010;color:#fff;font-weight:bold;"
    "font-size:13px;border-radius:4px;padding:0 28px}"
    "QPushButton:hover{background:#b3470e}"
    "QPushButton:pressed{background:#9a3d0c}")

_PROGRESS_STYLE = (
    "QProgressBar{border:none;background:#e0e0e0;border-radius:2px;}"
    "QProgressBar::chunk{background:#0078d4;border-radius:2px;}")

_IMG_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp')

_IMG_FILTER = "图片文件 (*.png *.jpg *.jpeg *.bmp *.tiff *.tif *.webp);;所有文件 (*)"


# ═══════════════════════════════════════════════════════════════
#  后台工作线程
# ═══════════════════════════════════════════════════════════════

class _DetectWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, img, method_key=None):
        super().__init__()
        self._img = img
        self._method = method_key

    def run(self):
        try:
            if self._method is None:
                results = run_all_quick(self._img)
            else:
                results = run_detection(self._img, self._method)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


class _BwmWorker(QThread):
    """blind_watermark 嵌入/提取通用线程"""
    text_result = pyqtSignal(str)
    file_result = pyqtSignal(str)
    embed_result = pyqtSignal(str, int)  # (out_path, wm_bit_len)
    error = pyqtSignal(str)

    def __init__(self, task, **kwargs):
        super().__init__()
        self._task = task
        self._kw = kwargs

    def run(self):
        try:
            if self._task == "embed_text":
                out, wm_len = bwm_embed_text(
                    self._kw['img_path'], self._kw['text'],
                    self._kw['pwd_img'], self._kw['pwd_wm'])
                self.embed_result.emit(out, wm_len)

            elif self._task == "embed_image":
                out = bwm_embed_image(
                    self._kw['img_path'], self._kw['wm_path'],
                    self._kw['pwd_img'], self._kw['pwd_wm'])
                self.file_result.emit(out)

            elif self._task == "extract_text":
                txt = bwm_extract_text(
                    self._kw['img_path'], self._kw['wm_len'],
                    self._kw['pwd_img'], self._kw['pwd_wm'])
                self.text_result.emit(txt)

            elif self._task == "extract_image":
                out = bwm_extract_image(
                    self._kw['img_path'], self._kw['wm_shape'],
                    self._kw['pwd_img'], self._kw['pwd_wm'])
                self.file_result.emit(out)

        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


# ═══════════════════════════════════════════════════════════════
#  可点击放大的结果缩略图
# ═══════════════════════════════════════════════════════════════

class _ResultCard(QFrame):

    def __init__(self, label: str, bgr_img: np.ndarray, parent=None):
        super().__init__(parent)
        self._label_text = label
        self._bgr = bgr_img
        self.setObjectName("resultCard")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._build_ui()
        self._apply_style(False)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignCenter)
        self._img_label.setMinimumSize(200, 150)
        self._img_label.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._set_pixmap()
        layout.addWidget(self._img_label, stretch=1)

        txt = QLabel(self._label_text)
        txt.setAlignment(Qt.AlignCenter)
        txt.setWordWrap(True)
        txt.setStyleSheet(
            "font-size:11px; font-weight:bold; color:#1e2433; "
            "background:transparent; border:none; padding:2px;")
        layout.addWidget(txt)

    def _set_pixmap(self):
        pix = _cv_to_pixmap(self._bgr)
        self._full_pixmap = pix
        scaled = pix.scaled(
            QSize(240, 180), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._img_label.setPixmap(scaled)

    def _apply_style(self, hovered):
        border = "2px solid #0078d4" if hovered else "1px solid #dfe2e8"
        bg = "#f0f6ff" if hovered else "#ffffff"
        self.setStyleSheet(
            f"#resultCard{{background:{bg}; border:{border}; border-radius:8px;}}")

    def enterEvent(self, e):
        self._apply_style(True)

    def leaveEvent(self, e):
        self._apply_style(False)

    def mousePressEvent(self, e):
        self._show_full()

    def _show_full(self):
        viewer = QWidget(self.window(), Qt.Window)
        viewer.setWindowTitle(f"水印检测 — {self._label_text}")
        viewer.resize(800, 600)
        layout = QVBoxLayout(viewer)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:#1e1e1e;")

        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setPixmap(self._full_pixmap)
        lbl.setStyleSheet("background:#1e1e1e;")
        scroll.setWidget(lbl)
        layout.addWidget(scroll)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(8, 4, 8, 4)
        save_btn = QPushButton("保存图片")
        save_btn.setFixedHeight(30)
        save_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "border-radius:4px;padding:0 16px}"
            "QPushButton:hover{background:#106ebe}")
        bgr_ref = self._bgr
        label_ref = self._label_text

        def _save():
            path, _ = QFileDialog.getSaveFileName(
                viewer, "保存检测结果", f"watermark_{label_ref}.png",
                "PNG (*.png);;JPEG (*.jpg);;所有文件 (*)")
            if path:
                cv2.imwrite(path, bgr_ref)

        save_btn.clicked.connect(_save)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)
        viewer.show()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, '_full_pixmap'):
            w = self._img_label.width() - 4
            h = self._img_label.height() - 4
            if w > 10 and h > 10:
                scaled = self._full_pixmap.scaled(
                    QSize(w, h), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._img_label.setPixmap(scaled)


# ═══════════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════════

def _load_cv_image(path: str, keep_alpha=False):
    data = np.fromfile(path, dtype=np.uint8)
    flag = cv2.IMREAD_UNCHANGED if keep_alpha else cv2.IMREAD_COLOR
    return cv2.imdecode(data, flag)


def _cv_to_pixmap(img: np.ndarray) -> QPixmap:
    h, w = img.shape[:2]
    if len(img.shape) == 3 and img.shape[2] == 4:
        rgba = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
        qimg = QImage(rgba.data, w, h, w * 4, QImage.Format_RGBA8888)
    elif len(img.shape) == 3:
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
    else:
        qimg = QImage(img.data, w, h, w, QImage.Format_Grayscale8)
    return QPixmap.fromImage(qimg)


def _set_preview(label: QLabel, pixmap: QPixmap):
    pw = max(label.width() - 4, 100)
    ph = max(label.height() - 4, 80)
    scaled = pixmap.scaled(
        QSize(pw, ph), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    label.setPixmap(scaled)


def _make_progress():
    p = QProgressBar()
    p.setRange(0, 0)
    p.setFixedHeight(4)
    p.setStyleSheet(_PROGRESS_STYLE)
    p.setVisible(False)
    return p


def _make_preview_frame(title_text: str):
    frame = QFrame()
    frame.setStyleSheet(
        "QFrame{background:#f8f9fa; border:1px solid #dfe2e8; "
        "border-radius:6px;}")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(6, 6, 6, 6)

    title = QLabel(title_text)
    title.setStyleSheet(
        "font-size:11px; font-weight:bold; color:#6b7a8d; "
        "border:none; background:transparent;")
    layout.addWidget(title)

    preview = QLabel()
    preview.setAlignment(Qt.AlignCenter)
    preview.setMinimumSize(200, 140)
    preview.setStyleSheet("border:none; background:transparent;")
    layout.addWidget(preview, stretch=1)
    return frame, preview


# ═══════════════════════════════════════════════════════════════
#  Tab 1: 水印检测
# ═══════════════════════════════════════════════════════════════

class _DetectTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._img = None
        self._img_path = ""
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Vertical)

        # ── 上半: 图片加载 + 控制 ──
        top = QWidget()
        top_l = QVBoxLayout(top)
        top_l.setContentsMargins(0, 0, 0, 0)
        top_l.setSpacing(6)

        # 导入行
        imp = QHBoxLayout()
        self._import_btn = QPushButton("打开图片")
        self._import_btn.setFixedHeight(34)
        self._import_btn.setStyleSheet(_BTN_PRIMARY)
        self._import_btn.clicked.connect(self._open_image)
        imp.addWidget(self._import_btn)
        self._file_label = QLabel("未选择图片")
        self._file_label.setStyleSheet("color:#6b7a8d; font-size:12px;")
        imp.addWidget(self._file_label, stretch=1)
        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color:#6b7a8d; font-size:11px;")
        imp.addWidget(self._info_label)
        top_l.addLayout(imp)

        # 预览 + 控制
        ctrl_row = QHBoxLayout()

        pf, self._preview = _make_preview_frame("原图预览")
        self._preview.setText("拖放或点击\"打开图片\"")
        ctrl_row.addWidget(pf, stretch=2)

        ctrl_frame = QGroupBox("检测设置")
        ctrl_inner = QVBoxLayout(ctrl_frame)

        mr = QHBoxLayout()
        mr.addWidget(QLabel("检测方法:"))
        self._method_combo = QComboBox()
        self._method_combo.addItem("全部快速检测")
        for name in DETECT_METHODS:
            self._method_combo.addItem(name)
        self._method_combo.setMinimumWidth(180)
        mr.addWidget(self._method_combo, stretch=1)
        ctrl_inner.addLayout(mr)

        self._desc_label = QLabel("执行所有主要检测方法的快速综合分析")
        self._desc_label.setWordWrap(True)
        self._desc_label.setStyleSheet(
            "color:#6b7a8d; font-size:11px; padding:4px;")
        ctrl_inner.addWidget(self._desc_label)
        self._method_combo.currentTextChanged.connect(self._on_method_changed)

        ctrl_inner.addStretch()

        br = QHBoxLayout()
        self._exec_btn = QPushButton("▶  开始检测")
        self._exec_btn.setFixedHeight(36)
        self._exec_btn.setStyleSheet(_BTN_GREEN)
        self._exec_btn.clicked.connect(self._run_detect)
        br.addWidget(self._exec_btn)
        self._save_all_btn = QPushButton("全部保存")
        self._save_all_btn.setFixedHeight(30)
        self._save_all_btn.clicked.connect(self._save_all)
        self._save_all_btn.setEnabled(False)
        br.addWidget(self._save_all_btn)
        br.addStretch()
        ctrl_inner.addLayout(br)

        self._progress = _make_progress()
        ctrl_inner.addWidget(self._progress)

        ctrl_row.addWidget(ctrl_frame, stretch=3)
        top_l.addLayout(ctrl_row)
        splitter.addWidget(top)

        # ── 下半: 结果网格 ──
        bottom = QWidget()
        bot_l = QVBoxLayout(bottom)
        bot_l.setContentsMargins(0, 0, 0, 0)
        bot_l.setSpacing(4)
        rh = QHBoxLayout()
        rh.addWidget(QLabel("检测结果:"))
        rh.addStretch()
        self._result_count = QLabel("")
        self._result_count.setStyleSheet("color:#6b7a8d; font-size:11px;")
        rh.addWidget(self._result_count)
        bot_l.addLayout(rh)

        self._result_scroll = QScrollArea()
        self._result_scroll.setWidgetResizable(True)
        self._result_scroll.setStyleSheet(
            "QScrollArea{border:1px solid #dfe2e8; border-radius:6px; "
            "background:#f8f9fa;}")
        self._result_container = QWidget()
        self._result_container.setStyleSheet("background:transparent;")
        self._result_grid = QGridLayout(self._result_container)
        self._result_grid.setSpacing(10)
        self._result_grid.setContentsMargins(10, 10, 10, 10)
        ph_lbl = QLabel("请先打开图片，然后点击\"开始检测\"")
        ph_lbl.setAlignment(Qt.AlignCenter)
        ph_lbl.setStyleSheet("color:#999; font-size:13px; padding:40px;")
        self._result_grid.addWidget(ph_lbl, 0, 0)
        self._result_scroll.setWidget(self._result_container)
        bot_l.addWidget(self._result_scroll)

        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        root.addWidget(splitter)

        self._status = QLabel("就绪 — 支持 PNG / JPEG / BMP / TIFF / WebP")
        self._status.setStyleSheet("color:#666; font-size:11px;")
        root.addWidget(self._status)
        self.setAcceptDrops(True)

    # ── drag & drop ──
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            for url in e.mimeData().urls():
                if url.toLocalFile().lower().endswith(_IMG_EXTS):
                    e.acceptProposedAction()
                    return

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            self._load_image(url.toLocalFile())
            return

    def _open_image(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择图片", "", _IMG_FILTER)
        if p:
            self._load_image(p)

    def _load_image(self, path):
        img = _load_cv_image(path, keep_alpha=True)
        if img is None:
            QMessageBox.warning(self, "加载失败", "无法解析图片文件")
            return
        self._img = img
        self._img_path = path
        self._file_label.setText(os.path.basename(path))
        h, w = img.shape[:2]
        ch = img.shape[2] if len(img.shape) == 3 else 1
        alpha_hint = " (含Alpha)" if ch == 4 else ""
        self._info_label.setText(
            f"{w}×{h}  {ch}通道{alpha_hint}  "
            f"{os.path.getsize(path)/1024:.1f} KB")
        _set_preview(self._preview, _cv_to_pixmap(img))
        self._status.setText(f"已加载: {os.path.basename(path)}")

    def _on_method_changed(self, text):
        if text == "全部快速检测":
            self._desc_label.setText("执行所有主要检测方法的快速综合分析")
        elif text in DETECT_METHODS:
            self._desc_label.setText(DETECT_METHODS[text][1])

    def _run_detect(self):
        if self._img is None:
            QMessageBox.information(self, "提示", "请先打开一张图片")
            return
        if self._worker and self._worker.isRunning():
            return
        method = self._method_combo.currentText()
        key = None if method == "全部快速检测" else method
        self._exec_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status.setText("正在检测…")
        self._worker = _DetectWorker(self._img, key)
        self._worker.finished.connect(self._on_results)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_results(self, results):
        self._progress.setVisible(False)
        self._exec_btn.setEnabled(True)
        self._save_all_btn.setEnabled(True)
        self._last_results = results
        self._clear_results()
        cols = 3 if len(results) >= 3 else max(len(results), 1)
        for i, (label, bgr_img) in enumerate(results):
            card = _ResultCard(label, bgr_img)
            card.setMinimumHeight(200)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._result_grid.addWidget(card, i // cols, i % cols)
        for c in range(cols):
            self._result_grid.setColumnStretch(c, 1)
        self._result_count.setText(f"共 {len(results)} 项结果")
        self._status.setText(
            f"检测完成 — {len(results)} 项结果 (点击可放大查看)")

    def _on_error(self, msg):
        self._progress.setVisible(False)
        self._exec_btn.setEnabled(True)
        self._status.setText(f"检测出错: {msg}")
        QMessageBox.warning(self, "检测失败", msg)

    def _clear_results(self):
        while self._result_grid.count():
            item = self._result_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _save_all(self):
        if not hasattr(self, '_last_results') or not self._last_results:
            return
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not folder:
            return
        base = os.path.splitext(os.path.basename(self._img_path))[0]
        count = 0
        for label, bgr_img in self._last_results:
            safe = label.replace(" ", "_").replace("/", "-").replace("|", "-")
            cv2.imwrite(os.path.join(folder, f"{base}_{safe}.png"), bgr_img)
            count += 1
        self._status.setText(f"已保存 {count} 张图片到 {folder}")
        QMessageBox.information(
            self, "保存完成", f"已保存 {count} 张图片到:\n{folder}")


# ═══════════════════════════════════════════════════════════════
#  Tab 2: 嵌入水印
# ═══════════════════════════════════════════════════════════════

class _EmbedTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # ── 原图选择 ──
        g1 = QGroupBox("原始图片")
        g1l = QHBoxLayout(g1)
        self._img_btn = QPushButton("选择图片")
        self._img_btn.setFixedHeight(30)
        self._img_btn.setStyleSheet(_BTN_PRIMARY)
        self._img_btn.clicked.connect(self._pick_img)
        g1l.addWidget(self._img_btn)
        self._img_path_label = QLabel("未选择")
        self._img_path_label.setStyleSheet("color:#6b7a8d;")
        g1l.addWidget(self._img_path_label, stretch=1)
        root.addWidget(g1)

        # ── 水印类型 ──
        g2 = QGroupBox("水印内容")
        g2l = QVBoxLayout(g2)

        type_row = QHBoxLayout()
        self._type_group = QButtonGroup(self)
        self._rb_text = QRadioButton("文字水印")
        self._rb_img = QRadioButton("图片水印")
        self._rb_text.setChecked(True)
        self._type_group.addButton(self._rb_text, 0)
        self._type_group.addButton(self._rb_img, 1)
        type_row.addWidget(self._rb_text)
        type_row.addWidget(self._rb_img)
        type_row.addStretch()
        g2l.addLayout(type_row)

        # 文字输入
        self._text_widget = QWidget()
        twl = QVBoxLayout(self._text_widget)
        twl.setContentsMargins(0, 0, 0, 0)
        twl.addWidget(QLabel("水印文字:"))
        self._wm_text = QLineEdit()
        self._wm_text.setPlaceholderText("输入要嵌入的水印文字…")
        twl.addWidget(self._wm_text)
        g2l.addWidget(self._text_widget)

        # 图片选择
        self._img_widget = QWidget()
        iwl = QHBoxLayout(self._img_widget)
        iwl.setContentsMargins(0, 0, 0, 0)
        iwl.addWidget(QLabel("水印图片:"))
        self._wm_img_btn = QPushButton("选择水印图片")
        self._wm_img_btn.clicked.connect(self._pick_wm_img)
        iwl.addWidget(self._wm_img_btn)
        self._wm_img_label = QLabel("未选择")
        self._wm_img_label.setStyleSheet("color:#6b7a8d;")
        iwl.addWidget(self._wm_img_label, stretch=1)
        g2l.addWidget(self._img_widget)
        self._img_widget.setVisible(False)

        self._rb_text.toggled.connect(self._on_type_changed)
        root.addWidget(g2)

        # ── 密码 ──
        g3 = QGroupBox("密码设置")
        g3l = QHBoxLayout(g3)
        g3l.addWidget(QLabel("图片密码:"))
        self._pwd_img = QSpinBox()
        self._pwd_img.setRange(0, 999999)
        self._pwd_img.setValue(1)
        g3l.addWidget(self._pwd_img)
        g3l.addSpacing(20)
        g3l.addWidget(QLabel("水印密码:"))
        self._pwd_wm = QSpinBox()
        self._pwd_wm.setRange(0, 999999)
        self._pwd_wm.setValue(1)
        g3l.addWidget(self._pwd_wm)
        g3l.addStretch()
        root.addWidget(g3)

        # ── 执行 ──
        br = QHBoxLayout()
        self._exec_btn = QPushButton("▶  嵌入水印")
        self._exec_btn.setFixedHeight(36)
        self._exec_btn.setStyleSheet(_BTN_GREEN)
        self._exec_btn.clicked.connect(self._run_embed)
        br.addWidget(self._exec_btn)
        br.addStretch()
        root.addLayout(br)

        self._progress = _make_progress()
        root.addWidget(self._progress)

        # ── 结果 ──
        g4 = QGroupBox("嵌入结果")
        g4l = QVBoxLayout(g4)
        self._result_info = QLabel("")
        self._result_info.setWordWrap(True)
        self._result_info.setStyleSheet("font-size:12px; padding:4px;")
        g4l.addWidget(self._result_info)

        pf, self._result_preview = _make_preview_frame("嵌入后预览")
        self._result_preview.setText("嵌入后的图片将显示在此")
        g4l.addWidget(pf)

        sbr = QHBoxLayout()
        self._save_btn = QPushButton("保存嵌入后的图片")
        self._save_btn.setFixedHeight(30)
        self._save_btn.setStyleSheet(_BTN_PRIMARY)
        self._save_btn.clicked.connect(self._save_result)
        self._save_btn.setEnabled(False)
        sbr.addWidget(self._save_btn)
        sbr.addStretch()
        g4l.addLayout(sbr)

        root.addWidget(g4, stretch=1)

        self._status = QLabel("就绪")
        self._status.setStyleSheet("color:#666; font-size:11px;")
        root.addWidget(self._status)

        self._img_path = ""
        self._wm_img_path = ""
        self._result_path = ""

    def _on_type_changed(self, checked):
        self._text_widget.setVisible(checked)
        self._img_widget.setVisible(not checked)

    def _pick_img(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择原始图片", "", _IMG_FILTER)
        if p:
            self._img_path = p
            self._img_path_label.setText(os.path.basename(p))

    def _pick_wm_img(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择水印图片", "", _IMG_FILTER)
        if p:
            self._wm_img_path = p
            self._wm_img_label.setText(os.path.basename(p))

    def _run_embed(self):
        if not self._img_path:
            QMessageBox.information(self, "提示", "请先选择原始图片")
            return
        if self._worker and self._worker.isRunning():
            return

        pwd_i = self._pwd_img.value()
        pwd_w = self._pwd_wm.value()

        if self._rb_text.isChecked():
            text = self._wm_text.text().strip()
            if not text:
                QMessageBox.information(self, "提示", "请输入水印文字")
                return
            self._worker = _BwmWorker(
                "embed_text", img_path=self._img_path,
                text=text, pwd_img=pwd_i, pwd_wm=pwd_w)
            self._worker.embed_result.connect(self._on_embed_text_done)
        else:
            if not self._wm_img_path:
                QMessageBox.information(self, "提示", "请选择水印图片")
                return
            self._worker = _BwmWorker(
                "embed_image", img_path=self._img_path,
                wm_path=self._wm_img_path, pwd_img=pwd_i, pwd_wm=pwd_w)
            self._worker.file_result.connect(self._on_embed_img_done)

        self._worker.error.connect(self._on_error)
        self._exec_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status.setText("正在嵌入水印…")
        self._worker.start()

    def _on_embed_text_done(self, out_path, wm_len):
        self._progress.setVisible(False)
        self._exec_btn.setEnabled(True)
        self._result_path = out_path
        self._save_btn.setEnabled(True)
        self._result_info.setText(
            f"嵌入成功！\n"
            f"wm_bit 长度: {wm_len} (提取时需要此值)\n"
            f"图片密码: {self._pwd_img.value()}  "
            f"水印密码: {self._pwd_wm.value()}")
        img = _load_cv_image(out_path)
        if img is not None:
            _set_preview(self._result_preview, _cv_to_pixmap(img))
        self._status.setText("嵌入完成")

    def _on_embed_img_done(self, out_path):
        self._progress.setVisible(False)
        self._exec_btn.setEnabled(True)
        self._result_path = out_path
        self._save_btn.setEnabled(True)
        self._result_info.setText(
            f"嵌入成功！\n"
            f"图片密码: {self._pwd_img.value()}  "
            f"水印密码: {self._pwd_wm.value()}\n"
            f"提取时需要水印图片尺寸 (宽×高)")
        img = _load_cv_image(out_path)
        if img is not None:
            _set_preview(self._result_preview, _cv_to_pixmap(img))
        self._status.setText("嵌入完成")

    def _on_error(self, msg):
        self._progress.setVisible(False)
        self._exec_btn.setEnabled(True)
        self._status.setText(f"出错: {msg}")
        QMessageBox.warning(self, "嵌入失败", msg)

    def _save_result(self):
        if not self._result_path:
            return
        p, _ = QFileDialog.getSaveFileName(
            self, "保存图片", "embedded.png",
            "PNG (*.png);;所有文件 (*)")
        if p:
            import shutil
            shutil.copy2(self._result_path, p)
            self._status.setText(f"已保存: {p}")


# ═══════════════════════════════════════════════════════════════
#  Tab 3: 提取水印
# ═══════════════════════════════════════════════════════════════

class _ExtractTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # ── 待提取图片 ──
        g1 = QGroupBox("待提取图片")
        g1l = QHBoxLayout(g1)
        self._img_btn = QPushButton("选择图片")
        self._img_btn.setFixedHeight(30)
        self._img_btn.setStyleSheet(_BTN_PRIMARY)
        self._img_btn.clicked.connect(self._pick_img)
        g1l.addWidget(self._img_btn)
        self._img_path_label = QLabel("未选择")
        self._img_path_label.setStyleSheet("color:#6b7a8d;")
        g1l.addWidget(self._img_path_label, stretch=1)
        root.addWidget(g1)

        # ── 提取类型 ──
        g2 = QGroupBox("水印类型")
        g2l = QVBoxLayout(g2)

        type_row = QHBoxLayout()
        self._type_group = QButtonGroup(self)
        self._rb_text = QRadioButton("文字水印")
        self._rb_img = QRadioButton("图片水印")
        self._rb_text.setChecked(True)
        self._type_group.addButton(self._rb_text, 0)
        self._type_group.addButton(self._rb_img, 1)
        type_row.addWidget(self._rb_text)
        type_row.addWidget(self._rb_img)
        type_row.addStretch()
        g2l.addLayout(type_row)

        # 文字参数
        self._text_widget = QWidget()
        twl = QHBoxLayout(self._text_widget)
        twl.setContentsMargins(0, 0, 0, 0)
        twl.addWidget(QLabel("wm_bit 长度:"))
        self._wm_len = QSpinBox()
        self._wm_len.setRange(1, 999999)
        self._wm_len.setValue(100)
        self._wm_len.setMinimumWidth(120)
        twl.addWidget(self._wm_len)
        twl.addStretch()
        g2l.addWidget(self._text_widget)

        # 图片参数
        self._img_widget = QWidget()
        iwl = QHBoxLayout(self._img_widget)
        iwl.setContentsMargins(0, 0, 0, 0)
        iwl.addWidget(QLabel("水印宽度:"))
        self._wm_w = QSpinBox()
        self._wm_w.setRange(1, 9999)
        self._wm_w.setValue(128)
        iwl.addWidget(self._wm_w)
        iwl.addSpacing(10)
        iwl.addWidget(QLabel("水印高度:"))
        self._wm_h = QSpinBox()
        self._wm_h.setRange(1, 9999)
        self._wm_h.setValue(128)
        iwl.addWidget(self._wm_h)
        iwl.addStretch()
        g2l.addWidget(self._img_widget)
        self._img_widget.setVisible(False)

        self._rb_text.toggled.connect(self._on_type_changed)
        root.addWidget(g2)

        # ── 密码 ──
        g3 = QGroupBox("密码设置")
        g3l = QHBoxLayout(g3)
        g3l.addWidget(QLabel("图片密码:"))
        self._pwd_img = QSpinBox()
        self._pwd_img.setRange(0, 999999)
        self._pwd_img.setValue(1)
        g3l.addWidget(self._pwd_img)
        g3l.addSpacing(20)
        g3l.addWidget(QLabel("水印密码:"))
        self._pwd_wm = QSpinBox()
        self._pwd_wm.setRange(0, 999999)
        self._pwd_wm.setValue(1)
        g3l.addWidget(self._pwd_wm)
        g3l.addStretch()
        root.addWidget(g3)

        # ── 执行 ──
        br = QHBoxLayout()
        self._exec_btn = QPushButton("▶  提取水印")
        self._exec_btn.setFixedHeight(36)
        self._exec_btn.setStyleSheet(_BTN_ORANGE)
        self._exec_btn.clicked.connect(self._run_extract)
        br.addWidget(self._exec_btn)
        br.addStretch()
        root.addLayout(br)

        self._progress = _make_progress()
        root.addWidget(self._progress)

        # ── 结果 ──
        g4 = QGroupBox("提取结果")
        g4l = QVBoxLayout(g4)

        # 文字结果
        self._text_result_widget = QWidget()
        trl = QVBoxLayout(self._text_result_widget)
        trl.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("提取的文字:")
        lbl.setStyleSheet("font-weight:bold;")
        trl.addWidget(lbl)
        self._extracted_text = QTextEdit()
        self._extracted_text.setReadOnly(True)
        self._extracted_text.setFont(QFont("Consolas", 11))
        self._extracted_text.setPlaceholderText("提取的水印文字将显示在此…")
        trl.addWidget(self._extracted_text)
        copy_row = QHBoxLayout()
        copy_btn = QPushButton("复制")
        copy_btn.setFixedWidth(70)
        copy_btn.clicked.connect(self._copy_text)
        copy_row.addStretch()
        copy_row.addWidget(copy_btn)
        trl.addLayout(copy_row)
        g4l.addWidget(self._text_result_widget)

        # 图片结果
        self._img_result_widget = QWidget()
        irl = QVBoxLayout(self._img_result_widget)
        irl.setContentsMargins(0, 0, 0, 0)
        pf, self._wm_preview = _make_preview_frame("提取的水印图片")
        self._wm_preview.setText("提取的水印图片将显示在此")
        irl.addWidget(pf)
        save_row = QHBoxLayout()
        self._save_wm_btn = QPushButton("保存水印图片")
        self._save_wm_btn.setFixedHeight(30)
        self._save_wm_btn.setStyleSheet(_BTN_PRIMARY)
        self._save_wm_btn.clicked.connect(self._save_wm)
        self._save_wm_btn.setEnabled(False)
        save_row.addStretch()
        save_row.addWidget(self._save_wm_btn)
        irl.addLayout(save_row)
        g4l.addWidget(self._img_result_widget)
        self._img_result_widget.setVisible(False)

        root.addWidget(g4, stretch=1)

        self._status = QLabel("就绪")
        self._status.setStyleSheet("color:#666; font-size:11px;")
        root.addWidget(self._status)

        self._img_path = ""
        self._wm_result_path = ""

    def _on_type_changed(self, checked):
        self._text_widget.setVisible(checked)
        self._img_widget.setVisible(not checked)
        self._text_result_widget.setVisible(checked)
        self._img_result_widget.setVisible(not checked)

    def _pick_img(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择图片", "", _IMG_FILTER)
        if p:
            self._img_path = p
            self._img_path_label.setText(os.path.basename(p))

    def _run_extract(self):
        if not self._img_path:
            QMessageBox.information(self, "提示", "请先选择图片")
            return
        if self._worker and self._worker.isRunning():
            return

        pwd_i = self._pwd_img.value()
        pwd_w = self._pwd_wm.value()

        if self._rb_text.isChecked():
            self._worker = _BwmWorker(
                "extract_text", img_path=self._img_path,
                wm_len=self._wm_len.value(), pwd_img=pwd_i, pwd_wm=pwd_w)
            self._worker.text_result.connect(self._on_text_done)
        else:
            shape = (self._wm_h.value(), self._wm_w.value())
            self._worker = _BwmWorker(
                "extract_image", img_path=self._img_path,
                wm_shape=shape, pwd_img=pwd_i, pwd_wm=pwd_w)
            self._worker.file_result.connect(self._on_img_done)

        self._worker.error.connect(self._on_error)
        self._exec_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status.setText("正在提取水印…")
        self._worker.start()

    def _on_text_done(self, text):
        self._progress.setVisible(False)
        self._exec_btn.setEnabled(True)
        self._extracted_text.setPlainText(text)
        self._status.setText("提取完成")

    def _on_img_done(self, path):
        self._progress.setVisible(False)
        self._exec_btn.setEnabled(True)
        self._wm_result_path = path
        self._save_wm_btn.setEnabled(True)
        img = _load_cv_image(path)
        if img is not None:
            _set_preview(self._wm_preview, _cv_to_pixmap(img))
        self._status.setText("提取完成")

    def _on_error(self, msg):
        self._progress.setVisible(False)
        self._exec_btn.setEnabled(True)
        self._status.setText(f"出错: {msg}")
        QMessageBox.warning(self, "提取失败", msg)

    def _copy_text(self):
        t = self._extracted_text.toPlainText()
        if t:
            QApplication.clipboard().setText(t)
            self._status.setText("已复制到剪贴板")

    def _save_wm(self):
        if not self._wm_result_path:
            return
        p, _ = QFileDialog.getSaveFileName(
            self, "保存水印图片", "extracted_watermark.png",
            "PNG (*.png);;所有文件 (*)")
        if p:
            import shutil
            shutil.copy2(self._wm_result_path, p)
            self._status.setText(f"已保存: {p}")


# ═══════════════════════════════════════════════════════════════
#  主面板 — TabWidget 容器
# ═══════════════════════════════════════════════════════════════

class WatermarkPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #dfe2e8;
                border-radius: 4px;
                background: #f8f9fa;
            }
            QTabBar::tab {
                padding: 8px 24px;
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #dfe2e8;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                background: #e8eaed;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #f8f9fa;
                color: #0078d4;
            }
            QTabBar::tab:hover:!selected {
                background: #f0f2f5;
            }
        """)

        tabs.addTab(_DetectTab(), "水印检测")
        tabs.addTab(_EmbedTab(), "嵌入水印")
        tabs.addTab(_ExtractTab(), "提取水印")

        root.addWidget(tabs)
