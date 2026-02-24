# -*- coding: utf-8 -*-
"""配置文件格式互转面板

支持 JSON ↔ YAML ↔ TOML 双向转换，左右编辑器，一键转换 / 互换。
依赖: pyyaml, toml（未安装时面板给出提示）
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QPlainTextEdit, QSplitter, QApplication,
    QGroupBox, QFrame,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

from core.config_convert import convert, check_deps, FORMATS

_MONO = QFont("Consolas", 10)
_MONO.setStyleHint(QFont.Monospace)


def _make_editor(readonly=False, placeholder='') -> QPlainTextEdit:
    te = QPlainTextEdit()
    te.setFont(_MONO)
    te.setReadOnly(readonly)
    if placeholder:
        te.setPlaceholderText(placeholder)
    return te


class ConfigConvertPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._check_deps()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(6)

        # 依赖提示（按需显示）
        self._dep_warn = QLabel("")
        self._dep_warn.setStyleSheet(
            "background:#fff8e1; color:#856404; padding:6px 10px; "
            "border-radius:4px; font-size:12px;")
        self._dep_warn.setWordWrap(True)
        self._dep_warn.hide()
        root.addWidget(self._dep_warn)

        # ── 控制栏 ────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        ctrl.addWidget(QLabel("输入格式:"))
        self._from_fmt = QComboBox()
        self._from_fmt.addItems(FORMATS)
        self._from_fmt.setFixedWidth(90)
        ctrl.addWidget(self._from_fmt)

        b_conv = QPushButton("→  转 换")
        b_conv.setFixedWidth(90)
        b_conv.setFixedHeight(30)
        b_conv.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "border-radius:4px;border:none;}"
            "QPushButton:hover{background:#106ebe;}")
        b_conv.clicked.connect(self._on_convert)
        ctrl.addWidget(b_conv)

        b_swap = QPushButton("⇌  互 换")
        b_swap.setFixedWidth(90)
        b_swap.setFixedHeight(30)
        b_swap.setStyleSheet(
            "QPushButton{background:#5c2d91;color:#fff;font-weight:bold;"
            "border-radius:4px;border:none;}")
        b_swap.clicked.connect(self._on_swap)
        ctrl.addWidget(b_swap)

        ctrl.addWidget(QLabel("输出格式:"))
        self._to_fmt = QComboBox()
        self._to_fmt.addItems(FORMATS)
        self._to_fmt.setCurrentIndex(1)   # 默认 JSON → YAML
        self._to_fmt.setFixedWidth(90)
        ctrl.addWidget(self._to_fmt)

        ctrl.addStretch()

        b_copy = QPushButton("复制输出")
        b_copy.setFixedHeight(30)
        b_copy.clicked.connect(
            lambda: QApplication.clipboard().setText(self._out_edit.toPlainText()))
        ctrl.addWidget(b_copy)

        b_clear = QPushButton("清空")
        b_clear.setFixedHeight(30)
        b_clear.clicked.connect(self._on_clear)
        ctrl.addWidget(b_clear)

        root.addLayout(ctrl)

        # ── 左右编辑器 ────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        left_grp = QGroupBox("输入")
        lg = QVBoxLayout(left_grp)
        lg.setContentsMargins(4, 4, 4, 4)
        self._in_edit = _make_editor(
            placeholder="在此粘贴 JSON / YAML / TOML 内容…")
        lg.addWidget(self._in_edit)
        splitter.addWidget(left_grp)

        right_grp = QGroupBox("输出（只读）")
        rg = QVBoxLayout(right_grp)
        rg.setContentsMargins(4, 4, 4, 4)
        self._out_edit = _make_editor(readonly=True)
        rg.addWidget(self._out_edit)
        splitter.addWidget(right_grp)

        splitter.setSizes([490, 490])
        root.addWidget(splitter, stretch=1)

        # 错误提示
        self._err_lbl = QLabel("")
        self._err_lbl.setStyleSheet("color:#ca5010; font-size:11px;")
        self._err_lbl.setWordWrap(True)
        root.addWidget(self._err_lbl)

        # 格式说明
        hint = QLabel(
            "📌  JSON / YAML / TOML 三种格式互转  ·  TOML 不支持非字符串键或顶层数组")
        hint.setStyleSheet("color:#888; font-size:11px;")
        root.addWidget(hint)

    # ── 依赖检查 ──────────────────────────────────────────
    def _check_deps(self):
        deps = check_deps()
        missing = [p for p, ok in [
            ('pyyaml', deps['pyyaml']),
            ('toml',   deps['toml']),
        ] if not ok]
        if missing:
            self._dep_warn.setText(
                f"⚠ 缺少依赖包：{', '.join(missing)}  —  "
                f"请运行：pip install {' '.join(missing)}"
            )
            self._dep_warn.show()

    # ── 转换 ──────────────────────────────────────────────
    def _on_convert(self):
        text = self._in_edit.toPlainText().strip()
        if not text:
            self._err_lbl.setText("请输入内容")
            return
        from_fmt = self._from_fmt.currentText()
        to_fmt   = self._to_fmt.currentText()
        try:
            result = convert(text, from_fmt, to_fmt)
            self._out_edit.setPlainText(result)
            self._err_lbl.setText("")
        except Exception as e:
            self._err_lbl.setText(f"转换失败 ({from_fmt} → {to_fmt})：{e}")
            self._out_edit.clear()

    def _on_swap(self):
        # 交换内容 + 格式
        in_text  = self._in_edit.toPlainText()
        out_text = self._out_edit.toPlainText()
        from_idx = self._from_fmt.currentIndex()
        to_idx   = self._to_fmt.currentIndex()

        self._in_edit.setPlainText(out_text)
        self._out_edit.setPlainText(in_text)   # 回填（只读临时解除没必要）
        self._from_fmt.setCurrentIndex(to_idx)
        self._to_fmt.setCurrentIndex(from_idx)

    def _on_clear(self):
        self._in_edit.clear()
        self._out_edit.setPlainText("")
        self._err_lbl.setText("")
