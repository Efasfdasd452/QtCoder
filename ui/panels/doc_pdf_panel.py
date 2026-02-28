# -*- coding: utf-8 -*-
"""Doc / Docx → PDF 批量转换面板

引擎自动检测优先级：docx2pdf → pywin32 → LibreOffice CLI
"""

import os
import threading

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QProgressBar,
    QFileDialog, QFrame,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal

_MONO = QFont("Consolas", 9)
_MONO.setStyleHint(QFont.Monospace)

_DOC_EXTS    = {".doc", ".docx"}
_CLR_PENDING = QColor("#ffffff")
_CLR_OK      = QColor("#e6f4ea")
_CLR_ERR     = QColor("#fce8e6")

_ENGINE_LABEL = {
    "docx2pdf":   "docx2pdf",
    "pywin32":    "pywin32（Word COM）",
    "libreoffice": "LibreOffice CLI",
    "none":       "无可用引擎",
}
_ENGINE_COLOR = {
    "docx2pdf":    "#107c10",
    "pywin32":     "#0078d4",
    "libreoffice": "#0078d4",
    "none":        "#c0392b",
}


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
        lbl = QLabel("🗂  拖放 .doc / .docx 文件或文件夹到此处（支持多选）")
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
#  后台转换线程
# ════════════════════════════════════════════════════════════
class _ConvertWorker(QThread):
    progress  = pyqtSignal(int, int)       # (current, total)
    file_done = pyqtSignal(str, str, str)  # (src, dest_or_empty, error_or_empty)
    finished  = pyqtSignal()

    def __init__(self, files: list[str], output_dir: str | None):
        super().__init__()
        self._files      = files
        self._output_dir = output_dir
        self._stop       = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        total      = len(self._files)
        done_count = [0]

        def on_done(src, dest, err):
            done_count[0] += 1
            self.file_done.emit(src, dest or "", err or "")
            self.progress.emit(done_count[0], total)

        from core.doc_to_pdf import convert_batch
        convert_batch(self._files, self._output_dir, on_done, self._stop)
        self.finished.emit()


# ════════════════════════════════════════════════════════════
#  主面板
# ════════════════════════════════════════════════════════════
class DocPdfPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[str] = []
        self._worker: _ConvertWorker | None = None
        self._build_ui()
        self._refresh_engine_hint()

    # ── 构建界面 ──────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(6)

        # 拖放区域
        drop = _DropArea()
        drop.files_dropped.connect(self._add_paths)
        root.addWidget(drop)

        # 引擎状态提示
        self._engine_hint = QLabel("")
        self._engine_hint.setStyleSheet("font-size:11px; padding:0 2px;")
        root.addWidget(self._engine_hint)

        # 输出目录行
        out_row = QHBoxLayout()
        self._same_dir_cb = QCheckBox("与源文件同目录")
        self._same_dir_cb.setChecked(True)
        self._same_dir_cb.toggled.connect(self._on_same_dir_toggle)
        out_row.addWidget(self._same_dir_cb)
        out_row.addSpacing(12)

        out_row.addWidget(QLabel("输出目录:"))
        self._out_dir_edit = QLineEdit()
        self._out_dir_edit.setPlaceholderText("选择 PDF 保存目录…")
        self._out_dir_edit.setEnabled(False)
        out_row.addWidget(self._out_dir_edit, stretch=1)

        self._browse_out_btn = QPushButton("浏览…")
        self._browse_out_btn.setFixedWidth(56)
        self._browse_out_btn.setEnabled(False)
        self._browse_out_btn.clicked.connect(self._browse_output_dir)
        out_row.addWidget(self._browse_out_btn)
        root.addLayout(out_row)

        # 操作按钮行
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

        # 进度条
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

    # ── 引擎检测提示 ──────────────────────────────────────
    def _refresh_engine_hint(self):
        from core.doc_to_pdf import detect_engine, find_libreoffice, _has_docx2pdf, _has_pywin32

        has_d2p = _has_docx2pdf()
        has_pw  = _has_pywin32()
        lo      = find_libreoffice()
        engine  = detect_engine()

        label = _ENGINE_LABEL.get(engine, engine)
        color = _ENGINE_COLOR.get(engine, "#555")

        if engine == "none":
            hint = (
                "✗ 未找到可用引擎  |  "
                "推荐安装：pip install docx2pdf"
            )
        else:
            parts = []
            if has_d2p:
                parts.append("✓ docx2pdf")
            if has_pw:
                parts.append("✓ pywin32")
            if lo:
                parts.append(f"✓ LibreOffice ({lo})")
            if not has_d2p:
                parts.append("✗ docx2pdf（pip install docx2pdf）")
            hint = f"将使用：{label}    |    已检测：{'    '.join(parts)}"

        self._engine_hint.setText(hint)
        self._engine_hint.setStyleSheet(
            f"font-size:11px; color:{color}; padding:0 2px;")

    # ── 输出目录切换 ──────────────────────────────────────
    def _on_same_dir_toggle(self, checked: bool):
        self._out_dir_edit.setEnabled(not checked)
        self._browse_out_btn.setEnabled(not checked)

    def _browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self._out_dir_edit.setText(d)

    # ── 文件管理 ──────────────────────────────────────────
    def _collect_doc_files(self, paths: list) -> list:
        result = []
        for p in paths:
            if os.path.isfile(p):
                if os.path.splitext(p)[1].lower() in _DOC_EXTS:
                    result.append(p)
            elif os.path.isdir(p):
                for root_dir, _, fnames in os.walk(p):
                    for fn in sorted(fnames):
                        if os.path.splitext(fn)[1].lower() in _DOC_EXTS:
                            result.append(os.path.join(root_dir, fn))
        return result

    def _add_paths(self, paths: list):
        existing = set(self._files)
        for f in self._collect_doc_files(paths):
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
            self, "选择 Word 文档", "",
            "Word 文档 (*.doc *.docx);;所有文件 (*)")
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

        self._worker = _ConvertWorker(list(self._files), output_dir)
        self._worker.progress.connect(self._on_progress)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()
        self._status.setText("转换中…")

    def _stop_conv(self):
        if self._worker:
            self._worker.stop()
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

        if dest:  # dest 非空 = 成功，err 非空 = 失败（两者互斥）
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
