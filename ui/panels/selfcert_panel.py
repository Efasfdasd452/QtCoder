# -*- coding: utf-8 -*-
"""网站自签名证书生成面板

填写域名、SAN、组织信息 → 一键生成含 SAN 扩展的 X.509 v3 证书，
导出 .crt / .key 文件，兼容 nginx / Apache / 本地开发 HTTPS。
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QLineEdit, QGroupBox, QTabWidget, QPlainTextEdit,
    QApplication, QFileDialog, QSpinBox, QSizePolicy, QFrame,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from core.selfcert import generate_cert, KEY_TYPE_NAMES, HAS_CRYPTO


# ──────────────────────────────────────────────────────────────
#  小工具
# ──────────────────────────────────────────────────────────────

def _label(text: str, color: str = "", bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    styles = []
    if color:
        styles.append(f"color:{color}")
    if bold:
        styles.append("font-weight:bold")
    if styles:
        lbl.setStyleSheet(";".join(styles))
    return lbl


def _copy_btn(parent, slot) -> QPushButton:
    btn = QPushButton("复制")
    btn.setFixedWidth(58)
    btn.clicked.connect(slot)
    return btn


def _export_btn(parent, label: str, slot) -> QPushButton:
    btn = QPushButton(label)
    btn.setFixedWidth(84)
    btn.clicked.connect(slot)
    return btn


# ──────────────────────────────────────────────────────────────
#  面板
# ──────────────────────────────────────────────────────────────

class SelfCertPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mono = QFont("Consolas", 10)
        self._mono.setStyleHint(QFont.Monospace)
        self._last: dict = {}
        self._build_ui()

    # ─────────────────────────────────────────────────────────
    #  构建界面
    # ─────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(8)

        if not HAS_CRYPTO:
            warn = QLabel(
                "cryptography 库未安装，无法生成证书。\n\n"
                "请在项目虚拟环境中运行:\n"
                "    pip install cryptography"
            )
            warn.setStyleSheet(
                "color:#c00;font-weight:bold;font-size:13px;"
                "padding:24px;background:#fff8f8;border-radius:6px")
            root.addWidget(warn)
            root.addStretch()
            return

        # ── 参数区 ────────────────────────────────────────────
        group = QGroupBox("证书参数")
        g = QVBoxLayout(group)
        g.setSpacing(10)

        # 行 1：域名 + 密钥类型 + 有效期
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("域名 (CN) *"))
        self._cn = QLineEdit()
        self._cn.setPlaceholderText("example.com")
        r1.addWidget(self._cn, stretch=3)

        r1.addSpacing(16)
        r1.addWidget(QLabel("密钥类型"))
        self._key_type = QComboBox()
        self._key_type.addItems(KEY_TYPE_NAMES)
        self._key_type.setCurrentText("RSA-2048")
        self._key_type.setFixedWidth(130)
        r1.addWidget(self._key_type)

        r1.addSpacing(16)
        r1.addWidget(QLabel("有效期 (天)"))
        self._days = QSpinBox()
        self._days.setRange(1, 36500)
        self._days.setValue(365)
        self._days.setFixedWidth(80)
        r1.addWidget(self._days)
        g.addLayout(r1)

        # 行 2：SAN
        r2 = QHBoxLayout()
        san_lbl = QLabel("附加域名/IP\n(SAN)")
        san_lbl.setAlignment(Qt.AlignTop)
        r2.addWidget(san_lbl)
        self._san = QLineEdit()
        self._san.setPlaceholderText(
            "*.example.com, sub.example.com, 192.168.1.1  （逗号分隔；CN 已自动包含）"
        )
        r2.addWidget(self._san, stretch=1)
        g.addLayout(r2)

        # 行 3：组织 + 国家
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("组织 (O)"))
        self._org = QLineEdit()
        self._org.setText("My Organization")
        r3.addWidget(self._org, stretch=3)

        r3.addSpacing(16)
        r3.addWidget(QLabel("国家代码 (C)"))
        self._country = QLineEdit()
        self._country.setText("CN")
        self._country.setMaxLength(2)
        self._country.setFixedWidth(46)
        self._country.setAlignment(Qt.AlignCenter)
        r3.addWidget(self._country)
        r3.addStretch()
        g.addLayout(r3)

        root.addWidget(group)

        # ── 生成按钮 + 状态 ───────────────────────────────────
        btn_row = QHBoxLayout()
        self._gen_btn = QPushButton("  生成自签名证书")
        self._gen_btn.setFixedHeight(36)
        self._gen_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:14px;border-radius:4px;padding:0 24px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}"
        )
        self._gen_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(self._gen_btn)

        self._fp_label = QLabel("")
        self._fp_label.setStyleSheet(
            "color:#107c10;font-size:11px;font-family:Consolas,monospace")
        btn_row.addSpacing(12)
        btn_row.addWidget(self._fp_label)
        btn_row.addStretch()

        self._status = QLabel("就绪")
        self._status.setStyleSheet("color:#666;font-size:11px")
        btn_row.addWidget(self._status)
        root.addLayout(btn_row)

        # ── 输出区 (Tabs) ─────────────────────────────────────
        tabs = QTabWidget()

        # Tab 1：证书 PEM
        cert_w = QWidget()
        cl = QVBoxLayout(cert_w)
        cl.setContentsMargins(6, 6, 6, 6)
        ch = QHBoxLayout()
        ch.addWidget(QLabel("证书文件 (server.crt / server.pem):"))
        ch.addStretch()
        ch.addWidget(_copy_btn(self, lambda: self._copy(self._cert_out)))
        ch.addWidget(_export_btn(self, "导出 .crt",
                                 lambda: self._export("cert")))
        cl.addLayout(ch)
        self._cert_out = QPlainTextEdit()
        self._cert_out.setFont(self._mono)
        self._cert_out.setReadOnly(True)
        self._cert_out.setPlaceholderText("生成后显示 PEM 格式证书…")
        cl.addWidget(self._cert_out)
        tabs.addTab(cert_w, "证书 (.crt)")

        # Tab 2：私钥 PEM
        key_w = QWidget()
        kl = QVBoxLayout(key_w)
        kl.setContentsMargins(6, 6, 6, 6)
        kh = QHBoxLayout()
        kh.addWidget(QLabel("私钥文件 (server.key):"))
        kh.addStretch()
        kh.addWidget(_copy_btn(self, lambda: self._copy(self._key_out)))
        kh.addWidget(_export_btn(self, "导出 .key",
                                 lambda: self._export("key")))
        kl.addLayout(kh)
        self._key_out = QPlainTextEdit()
        self._key_out.setFont(self._mono)
        self._key_out.setReadOnly(True)
        self._key_out.setPlaceholderText("生成后显示 PEM 格式私钥…")
        kl.addWidget(self._key_out)
        tabs.addTab(key_w, "私钥 (.key)")

        # Tab 3：证书信息
        info_w = QWidget()
        il = QVBoxLayout(info_w)
        il.setContentsMargins(6, 6, 6, 6)
        ih = QHBoxLayout()
        ih.addWidget(QLabel("证书详细信息:"))
        ih.addStretch()
        ih.addWidget(_copy_btn(self, lambda: self._copy(self._info_out)))
        il.addLayout(ih)
        self._info_out = QPlainTextEdit()
        self._info_out.setFont(self._mono)
        self._info_out.setReadOnly(True)
        il.addWidget(self._info_out)
        tabs.addTab(info_w, "证书信息")

        # Tab 4：等效命令
        cmd_w = QWidget()
        mml = QVBoxLayout(cmd_w)
        mml.setContentsMargins(6, 6, 6, 6)
        mmh = QHBoxLayout()
        mmh.addWidget(QLabel("等效 openssl 命令（可直接在终端执行）:"))
        mmh.addStretch()
        mmh.addWidget(_copy_btn(self, lambda: self._copy(self._cmd_out)))
        mml.addLayout(mmh)
        self._cmd_out = QPlainTextEdit()
        self._cmd_out.setFont(self._mono)
        self._cmd_out.setReadOnly(True)
        self._cmd_out.setStyleSheet(
            "QPlainTextEdit{background:#1e2433;color:#a0d0a0;"
            "border-radius:4px;padding:8px}")
        mml.addWidget(self._cmd_out)
        tabs.addTab(cmd_w, "openssl 命令")

        root.addWidget(tabs, stretch=1)

    # ─────────────────────────────────────────────────────────
    #  事件处理
    # ─────────────────────────────────────────────────────────

    def _on_generate(self):
        cn = self._cn.text().strip()
        if not cn:
            self._status.setText("请输入域名 (CN)")
            self._cn.setFocus()
            return

        self._status.setText("生成中…")
        self._fp_label.setText("")
        QApplication.processEvents()

        try:
            result = generate_cert(
                common_name=cn,
                san_extra=self._san.text().strip(),
                org=self._org.text().strip() or "My Organization",
                country=self._country.text().strip() or "CN",
                valid_days=self._days.value(),
                key_type=self._key_type.currentText(),
            )
            self._last = result
            self._cert_out.setPlainText(result["cert_pem"])
            self._key_out.setPlainText(result["key_pem"])
            self._info_out.setPlainText(result["cert_info"])
            self._cmd_out.setPlainText(result["openssl_cmd"])

            fp = result["fingerprint"]
            self._fp_label.setText("SHA-256: " + fp[:29] + "…")
            self._status.setText("生成成功")

        except Exception as e:
            import traceback
            self._status.setText("错误: " + str(e))
            self._cert_out.setPlainText("生成失败:\n\n" + traceback.format_exc())
            self._fp_label.setText("")

    def _copy(self, widget: QPlainTextEdit):
        text = widget.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._status.setText("已复制到剪贴板")

    def _export(self, which: str):
        if not self._last:
            self._status.setText("请先生成证书")
            return

        safe_cn = (self._cn.text().strip()
                   .replace(".", "_").replace("*", "star").replace(" ", "_")
                   or "server")

        if which == "cert":
            default_name = f"{safe_cn}.crt"
            content      = self._last["cert_pem"].encode("utf-8")
            filt         = "Certificate (*.crt *.pem);;All Files (*)"
        else:
            default_name = f"{safe_cn}.key"
            content      = self._last["key_pem"].encode("utf-8")
            filt         = "Private Key (*.key *.pem);;All Files (*)"

        path, _ = QFileDialog.getSaveFileName(
            self, "导出文件", default_name, filt)
        if path:
            with open(path, "wb") as f:
                f.write(content)
            self._status.setText("已导出: " + path)
