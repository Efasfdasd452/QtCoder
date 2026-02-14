# -*- coding: utf-8 -*-
"""OpenSSL 非对称密钥对生成面板

支持 X25519/Ed25519 Raw 公钥 (Base64url)、PEM、DER、OpenSSH 等格式。
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTextEdit, QGroupBox, QLineEdit, QSplitter,
    QApplication, QFileDialog, QCheckBox, QTabWidget, QPlainTextEdit,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

from core.openssl_keygen import (
    generate_keypair, openssl_version, find_openssl,
    KEY_TYPE_NAMES, RAW_SUPPORTED, OPENSSH_SUPPORTED,
    HAS_CRYPTO_LIB,
)


class OpensslPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mono = QFont("Consolas", 10)
        self._mono.setStyleHint(QFont.Monospace)
        self._last_result = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(6)

        if not HAS_CRYPTO_LIB:
            warn = QLabel(
                "cryptography 库未安装，请运行:\n"
                "pip install cryptography")
            warn.setStyleSheet(
                "color:red;font-weight:bold;font-size:13px;padding:20px")
            root.addWidget(warn)
            root.addStretch()
            return

        # ── OpenSSL 状态 ──────────────────────────────────────
        ver = openssl_version()
        ssl_path = find_openssl()
        if ver:
            ssl_label = QLabel(f"OpenSSL CLI: {ver}  ({ssl_path})")
            ssl_label.setStyleSheet("color:#107c10;font-size:11px")
        else:
            ssl_label = QLabel(
                "OpenSSL CLI 未找到 (非必须, 程序使用 cryptography 库内置 OpenSSL)")
            ssl_label.setStyleSheet("color:#888;font-size:11px")
        root.addWidget(ssl_label)

        # ── 参数区 ────────────────────────────────────────────
        group = QGroupBox("密钥参数")
        g = QVBoxLayout(group)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("密钥类型:"))
        self._key_type = QComboBox()
        self._key_type.addItems(KEY_TYPE_NAMES)
        self._key_type.setCurrentText('X25519')
        self._key_type.setFixedWidth(160)
        self._key_type.currentTextChanged.connect(self._on_type_changed)
        r1.addWidget(self._key_type)

        r1.addSpacing(20)
        self._use_pass = QCheckBox("密码保护私钥")
        r1.addWidget(self._use_pass)
        self._passphrase = QLineEdit()
        self._passphrase.setPlaceholderText("输入密码")
        self._passphrase.setEchoMode(QLineEdit.Password)
        self._passphrase.setFixedWidth(200)
        self._passphrase.setEnabled(False)
        self._use_pass.toggled.connect(self._passphrase.setEnabled)
        r1.addWidget(self._passphrase)
        r1.addStretch()
        g.addLayout(r1)

        # 密钥类型说明
        self._type_desc = QLabel("")
        self._type_desc.setStyleSheet("color:#6b7a8d;font-size:11px")
        g.addWidget(self._type_desc)
        self._on_type_changed(self._key_type.currentText())

        root.addWidget(group)

        # ── 按钮行 ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        gen_btn = QPushButton("  生成密钥对")
        gen_btn.setFixedHeight(36)
        gen_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:14px;border-radius:4px;padding:0 24px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}")
        gen_btn.clicked.connect(self._generate)
        btn_row.addWidget(gen_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── 输出区 (Tab) ──────────────────────────────────────
        out_tabs = QTabWidget()

        # Tab 1: Raw 公钥 (Base64url)
        raw_w = QWidget()
        raw_l = QVBoxLayout(raw_w)
        raw_l.setContentsMargins(6, 6, 6, 6)
        raw_hdr = QHBoxLayout()
        raw_hdr.addWidget(QLabel("Raw 公钥 (Base64url):"))
        raw_hdr.addStretch()
        raw_copy = QPushButton("复制")
        raw_copy.setFixedWidth(60)
        raw_copy.clicked.connect(lambda: self._copy_text(self._raw_pub))
        raw_hdr.addWidget(raw_copy)
        raw_l.addLayout(raw_hdr)

        self._raw_pub = QLineEdit()
        self._raw_pub.setFont(QFont("Consolas", 13))
        self._raw_pub.setReadOnly(True)
        self._raw_pub.setPlaceholderText(
            "生成后显示, 如: Hw1sCTC9xVvgNWXhnRwxGXKc_unH_-BUuGAT-RbSKiI")
        self._raw_pub.setStyleSheet(
            "QLineEdit{padding:8px;background:#f8f9fa;"
            "border:1px solid #ddd;border-radius:4px;font-size:14px}")
        raw_l.addWidget(self._raw_pub)

        raw_l.addWidget(QLabel("密钥信息:"))
        self._key_info = QPlainTextEdit()
        self._key_info.setFont(self._mono)
        self._key_info.setReadOnly(True)
        self._key_info.setMaximumHeight(100)
        raw_l.addWidget(self._key_info)

        raw_l.addWidget(QLabel("等效 openssl 命令:"))
        self._openssl_cmd = QPlainTextEdit()
        self._openssl_cmd.setFont(self._mono)
        self._openssl_cmd.setReadOnly(True)
        self._openssl_cmd.setMaximumHeight(120)
        self._openssl_cmd.setStyleSheet(
            "QPlainTextEdit{background:#1e2433;color:#a0d0a0;"
            "border-radius:4px;padding:6px}")
        raw_l.addWidget(self._openssl_cmd)
        raw_l.addStretch()
        out_tabs.addTab(raw_w, "Raw 公钥")

        # Tab 2: PEM 私钥
        priv_w = QWidget()
        priv_l = QVBoxLayout(priv_w)
        priv_l.setContentsMargins(6, 6, 6, 6)
        priv_hdr = QHBoxLayout()
        priv_hdr.addWidget(QLabel("私钥 (PKCS#8 PEM):"))
        priv_hdr.addStretch()
        priv_copy = QPushButton("复制")
        priv_copy.setFixedWidth(60)
        priv_copy.clicked.connect(lambda: self._copy_text(self._priv_text))
        priv_hdr.addWidget(priv_copy)
        priv_export = QPushButton("导出 .pem")
        priv_export.setFixedWidth(80)
        priv_export.clicked.connect(lambda: self._export('private_pem'))
        priv_hdr.addWidget(priv_export)
        priv_l.addLayout(priv_hdr)
        self._priv_text = QPlainTextEdit()
        self._priv_text.setFont(self._mono)
        self._priv_text.setReadOnly(True)
        priv_l.addWidget(self._priv_text)
        out_tabs.addTab(priv_w, "私钥 PEM")

        # Tab 3: PEM 公钥
        pub_w = QWidget()
        pub_l = QVBoxLayout(pub_w)
        pub_l.setContentsMargins(6, 6, 6, 6)
        pub_hdr = QHBoxLayout()
        pub_hdr.addWidget(QLabel("公钥 (SPKI PEM):"))
        pub_hdr.addStretch()
        pub_copy = QPushButton("复制")
        pub_copy.setFixedWidth(60)
        pub_copy.clicked.connect(lambda: self._copy_text(self._pub_text))
        pub_hdr.addWidget(pub_copy)
        pub_export = QPushButton("导出 .pem")
        pub_export.setFixedWidth(80)
        pub_export.clicked.connect(lambda: self._export('public_pem'))
        pub_hdr.addWidget(pub_export)
        pub_l.addLayout(pub_hdr)
        self._pub_text = QPlainTextEdit()
        self._pub_text.setFont(self._mono)
        self._pub_text.setReadOnly(True)
        pub_l.addWidget(self._pub_text)
        out_tabs.addTab(pub_w, "公钥 PEM")

        # Tab 4: OpenSSH
        ssh_w = QWidget()
        ssh_l = QVBoxLayout(ssh_w)
        ssh_l.setContentsMargins(6, 6, 6, 6)
        ssh_hdr = QHBoxLayout()
        ssh_hdr.addWidget(QLabel("OpenSSH 公钥:"))
        ssh_hdr.addStretch()
        ssh_copy = QPushButton("复制")
        ssh_copy.setFixedWidth(60)
        ssh_copy.clicked.connect(lambda: self._copy_text(self._ssh_text))
        ssh_hdr.addWidget(ssh_copy)
        ssh_l.addLayout(ssh_hdr)
        self._ssh_text = QPlainTextEdit()
        self._ssh_text.setFont(self._mono)
        self._ssh_text.setReadOnly(True)
        ssh_l.addWidget(self._ssh_text)
        out_tabs.addTab(ssh_w, "OpenSSH")

        # Tab 5: JWK
        jwk_w = QWidget()
        jwk_l = QVBoxLayout(jwk_w)
        jwk_l.setContentsMargins(6, 6, 6, 6)
        jwk_hdr = QHBoxLayout()
        jwk_hdr.addWidget(QLabel("JWK (JSON Web Key):"))
        jwk_hdr.addStretch()
        jwk_copy = QPushButton("复制")
        jwk_copy.setFixedWidth(60)
        jwk_copy.clicked.connect(lambda: self._copy_text(self._jwk_text))
        jwk_hdr.addWidget(jwk_copy)
        jwk_l.addLayout(jwk_hdr)
        self._jwk_text = QPlainTextEdit()
        self._jwk_text.setFont(self._mono)
        self._jwk_text.setReadOnly(True)
        jwk_l.addWidget(self._jwk_text)
        out_tabs.addTab(jwk_w, "JWK")

        root.addWidget(out_tabs, stretch=1)

        # 状态
        self._status = QLabel("就绪")
        self._status.setStyleSheet("color:#666;font-size:11px")
        root.addWidget(self._status)

    # ══════════════════════════════════════════════════════════
    #  事件
    # ══════════════════════════════════════════════════════════
    def _on_type_changed(self, key_type):
        desc_map = {
            'RSA-2048':  'RSA 2048 位 — 通用加密/签名, 兼容性最好',
            'RSA-3072':  'RSA 3072 位 — 安全强度等同 128 位对称加密',
            'RSA-4096':  'RSA 4096 位 — 高安全性, 速度较慢',
            'EC P-256':  'ECDSA/ECDH P-256 — TLS 默认曲线, 性能优秀',
            'EC P-384':  'ECDSA/ECDH P-384 — 政府级安全',
            'EC P-521':  'ECDSA/ECDH P-521 — 最高安全等级',
            'X25519':    'X25519 — 现代密钥交换 (Curve25519), WireGuard/Signal 使用',
            'Ed25519':   'Ed25519 — 现代数字签名, SSH/区块链广泛使用',
            'X448':      'X448 — 448 位密钥交换, 比 X25519 更高安全余量',
            'Ed448':     'Ed448 — 448 位数字签名',
        }
        self._type_desc.setText(desc_map.get(key_type, ''))

    def _generate(self):
        key_type = self._key_type.currentText()
        passphrase = None
        if self._use_pass.isChecked():
            passphrase = self._passphrase.text()
            if not passphrase:
                self._status.setText("请输入密码")
                return

        self._status.setText("正在生成...")
        QApplication.processEvents()

        try:
            result = generate_keypair(key_type, passphrase)
            self._last_result = result

            # Raw 公钥
            if result['public_raw_b64url']:
                self._raw_pub.setText(result['public_raw_b64url'])
            else:
                self._raw_pub.setText(
                    f"({key_type} 不支持 Raw 格式, 请查看 PEM 标签页)")

            self._key_info.setPlainText(result['key_info'])
            self._openssl_cmd.setPlainText(result['openssl_cmd'])
            self._priv_text.setPlainText(result['private_pem'])
            self._pub_text.setPlainText(result['public_pem'])

            if result['public_openssh']:
                self._ssh_text.setPlainText(result['public_openssh'])
            else:
                self._ssh_text.setPlainText(
                    f"({key_type} 不支持 OpenSSH 格式)")

            self._jwk_text.setPlainText(result['public_jwk'])

            self._status.setText(f"生成完成: {key_type}")

        except Exception as e:
            self._status.setText(f"错误: {e}")
            import traceback
            self._priv_text.setPlainText(traceback.format_exc())

    def _copy_text(self, widget):
        if isinstance(widget, QLineEdit):
            t = widget.text()
        else:
            t = widget.toPlainText()
        if t:
            QApplication.clipboard().setText(t)
            self._status.setText("已复制到剪贴板")

    def _export(self, which):
        if not self._last_result:
            return
        kt = self._last_result['key_type'].lower().replace(' ', '_')
        if which == 'private_pem':
            name = f"private_{kt}.pem"
            content = self._last_result['private_pem']
        elif which == 'public_pem':
            name = f"public_{kt}.pem"
            content = self._last_result['public_pem']
        else:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "导出密钥", name,
            "PEM Files (*.pem);;All Files (*)")
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            self._status.setText(f"已导出: {path}")
