# -*- coding: utf-8 -*-
"""JWT 解析面板

解码 JWT Token 的 Header / Payload，检查过期/生效时间，
无需密钥，纯本地，不联网。
"""

import json

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QGroupBox, QSplitter, QApplication,
    QFrame, QScrollArea,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

from core.jwt_tool import decode_jwt, get_expiry_info, CLAIM_DESCRIPTIONS

_MONO = QFont("Consolas", 10)
_MONO.setStyleHint(QFont.Monospace)

_STATUS_COLORS = {
    'valid':         ('#e6f4ea', '#107c10'),
    'expired':       ('#fce8e6', '#c0392b'),
    'no_exp':        ('#fff8e1', '#856404'),
    'not_yet_valid': ('#e3f2fd', '#0078d4'),
}


class JwtPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(8)

        # ── 输入区 ────────────────────────────────────────
        in_grp = QGroupBox("JWT Token 输入")
        ig = QVBoxLayout(in_grp)
        ig.setSpacing(6)

        self._token_in = QPlainTextEdit()
        self._token_in.setFont(_MONO)
        self._token_in.setFixedHeight(80)
        self._token_in.setPlaceholderText(
            "粘贴 JWT Token（支持带 Bearer 前缀），如：\n"
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwib..."
        )
        ig.addWidget(self._token_in)

        btn_row = QHBoxLayout()
        b_decode = QPushButton("解 码")
        b_decode.setFixedWidth(80)
        b_decode.setFixedHeight(30)
        b_decode.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "border-radius:4px;border:none;}"
            "QPushButton:hover{background:#106ebe;}")
        b_decode.clicked.connect(self._on_decode)
        self._token_in.textChanged.connect(self._on_decode)

        b_clear = QPushButton("清空")
        b_clear.setFixedWidth(60)
        b_clear.setFixedHeight(30)
        b_clear.clicked.connect(self._on_clear)

        btn_row.addWidget(b_decode)
        btn_row.addWidget(b_clear)
        btn_row.addStretch()
        self._err_lbl = QLabel("")
        self._err_lbl.setStyleSheet("color:#ca5010; font-size:11px;")
        btn_row.addWidget(self._err_lbl)
        ig.addLayout(btn_row)
        root.addWidget(in_grp)

        # ── 状态条 ────────────────────────────────────────
        self._status_bar = QLabel("")
        self._status_bar.setAlignment(Qt.AlignCenter)
        self._status_bar.setFixedHeight(32)
        self._status_bar.setStyleSheet(
            "border-radius:6px; font-weight:bold; font-size:13px; padding:0 12px;")
        self._status_bar.hide()
        root.addWidget(self._status_bar)

        # ── 解码结果（Header / Payload 并排）─────────────
        splitter = QSplitter(Qt.Horizontal)

        self._header_box  = self._make_json_box("Header（算法信息）")
        self._payload_box = self._make_json_box("Payload（业务数据）")

        splitter.addWidget(self._header_box)
        splitter.addWidget(self._payload_box)
        splitter.setSizes([380, 560])
        root.addWidget(splitter, stretch=1)

        # ── Payload 字段说明 ──────────────────────────────
        self._info_grp = QGroupBox("标准字段解析")
        self._info_grp.hide()
        ig2 = QVBoxLayout(self._info_grp)
        ig2.setContentsMargins(6, 4, 6, 4)
        self._info_lbl = QLabel("")
        self._info_lbl.setWordWrap(True)
        self._info_lbl.setStyleSheet("font-size:12px; color:#333;")
        ig2.addWidget(self._info_lbl)
        root.addWidget(self._info_grp)

    def _make_json_box(self, title: str):
        grp = QGroupBox(title)
        lay = QVBoxLayout(grp)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        te = QPlainTextEdit()
        te.setFont(_MONO)
        te.setReadOnly(True)
        lay.addWidget(te)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        b = QPushButton("复制")
        b.setFixedHeight(24)
        b.setFixedWidth(50)
        b.clicked.connect(lambda: QApplication.clipboard().setText(te.toPlainText()))
        btn_row.addWidget(b)
        lay.addLayout(btn_row)

        grp._text_edit = te
        return grp

    # ── 解码逻辑 ──────────────────────────────────────────
    def _on_decode(self):
        token = self._token_in.toPlainText().strip()
        if not token:
            self._clear_output()
            return
        try:
            header, payload, sig = decode_jwt(token)
            self._err_lbl.setText("")
        except Exception as e:
            self._err_lbl.setText(str(e))
            self._clear_output()
            return

        self._header_box._text_edit.setPlainText(
            json.dumps(header, ensure_ascii=False, indent=2))
        self._payload_box._text_edit.setPlainText(
            json.dumps(payload, ensure_ascii=False, indent=2))

        # 状态条
        exp_info = get_expiry_info(payload)
        status   = exp_info['status']
        bg, fg   = _STATUS_COLORS.get(status, ('#f0f0f0', '#333'))
        self._status_bar.setText(exp_info['message'])
        self._status_bar.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:6px; "
            f"font-weight:bold; font-size:13px; padding:0 12px;")
        self._status_bar.show()

        # 字段说明
        lines = []
        for field, desc in CLAIM_DESCRIPTIONS.items():
            if field in payload:
                val = payload[field]
                # 时间戳格式化
                if field in ('exp', 'iat', 'nbf'):
                    dt_str = exp_info.get(f'{field}_dt', '')
                    val_str = f"{val}  （{dt_str}）" if dt_str else str(val)
                else:
                    val_str = str(val)
                lines.append(f"<b>{field}</b>  <span style='color:#666'>({desc})</span>：{val_str}")
        if lines:
            self._info_lbl.setText("  |  ".join(lines))
            self._info_grp.show()
        else:
            self._info_grp.hide()

    def _on_clear(self):
        self._token_in.clear()
        self._clear_output()

    def _clear_output(self):
        self._header_box._text_edit.clear()
        self._payload_box._text_edit.clear()
        self._status_bar.hide()
        self._info_grp.hide()
        self._err_lbl.setText("")
