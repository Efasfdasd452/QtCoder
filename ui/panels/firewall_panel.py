# -*- coding: utf-8 -*-
"""防火墙规则生成面板"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QGroupBox, QTextEdit, QGridLayout,
    QApplication, QSplitter, QFrame, QToolTip, QCheckBox,
)
from PyQt5.QtGui import QFont, QCursor
from PyQt5.QtCore import Qt

from core.firewall_gen import (
    FwRule, CHAINS, ACTIONS, PROTOCOLS, GENERATORS,
    generate_all, generate_one,
)


class FirewallPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mono = QFont("Consolas", 10)
        self._mono.setStyleHint(QFont.Monospace)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Vertical)

        # ══════════════ 上半部分：参数表单 ══════════════
        top = QWidget()
        top_l = QVBoxLayout(top)
        top_l.setContentsMargins(0, 0, 0, 0)
        top_l.setSpacing(6)

        # ── 基础设置 ──
        g1 = QGroupBox("基础设置")
        g1_l = QGridLayout(g1)
        g1_l.setHorizontalSpacing(12)
        g1_l.setVerticalSpacing(8)

        # 链
        g1_l.addWidget(QLabel("链 (Chain):"), 0, 0)
        self._chain = QComboBox()
        for name, info in CHAINS.items():
            self._chain.addItem(f"{name} — {info['desc']}", name)
        self._chain.currentIndexChanged.connect(self._on_chain_changed)
        g1_l.addWidget(self._chain, 0, 1, 1, 3)

        # 链说明
        self._chain_hint = QLabel()
        self._chain_hint.setWordWrap(True)
        self._chain_hint.setStyleSheet(
            "color:#6b7a8d; font-size:11px; padding:2px 4px; "
            "background:#f0f6ff; border:1px solid #dfe2e8; border-radius:4px;")
        g1_l.addWidget(self._chain_hint, 1, 0, 1, 4)

        # 动作
        g1_l.addWidget(QLabel("动作 (Action):"), 2, 0)
        self._action = QComboBox()
        for act, desc in ACTIONS.items():
            self._action.addItem(f"{act} — {desc}", act)
        g1_l.addWidget(self._action, 2, 1)

        # 协议
        g1_l.addWidget(QLabel("协议:"), 2, 2)
        self._protocol = QComboBox()
        self._protocol.addItems(["tcp", "udp", "tcp+udp", "icmp", "any"])
        g1_l.addWidget(self._protocol, 2, 3)

        top_l.addWidget(g1)

        # ── 地址与端口 ──
        g2 = QGroupBox("地址与端口")
        g2_l = QGridLayout(g2)
        g2_l.setHorizontalSpacing(12)
        g2_l.setVerticalSpacing(8)

        g2_l.addWidget(QLabel("源 IP / CIDR:"), 0, 0)
        self._src_ip = QLineEdit()
        self._src_ip.setPlaceholderText("如 192.168.1.0/24 或留空=any")
        g2_l.addWidget(self._src_ip, 0, 1)

        g2_l.addWidget(QLabel("目标 IP / CIDR:"), 0, 2)
        self._dst_ip = QLineEdit()
        self._dst_ip.setPlaceholderText("如 10.0.0.1 或留空=any")
        g2_l.addWidget(self._dst_ip, 0, 3)

        g2_l.addWidget(QLabel("目标端口:"), 1, 0)
        self._port = QLineEdit()
        self._port.setPlaceholderText("如 80 或 8000:9000 或留空=all")
        g2_l.addWidget(self._port, 1, 1)

        g2_l.addWidget(QLabel("源端口:"), 1, 2)
        self._src_port = QLineEdit()
        self._src_port.setPlaceholderText("一般留空")
        g2_l.addWidget(self._src_port, 1, 3)

        top_l.addWidget(g2)

        # ── 高级选项 ──
        g3 = QGroupBox("高级选项")
        g3_l = QGridLayout(g3)
        g3_l.setHorizontalSpacing(12)
        g3_l.setVerticalSpacing(8)

        g3_l.addWidget(QLabel("入站网卡:"), 0, 0)
        self._iface_in = QLineEdit()
        self._iface_in.setPlaceholderText("如 eth0 (可选)")
        g3_l.addWidget(self._iface_in, 0, 1)

        g3_l.addWidget(QLabel("出站网卡:"), 0, 2)
        self._iface_out = QLineEdit()
        self._iface_out.setPlaceholderText("如 eth1 (可选)")
        g3_l.addWidget(self._iface_out, 0, 3)

        g3_l.addWidget(QLabel("NAT 目标:"), 1, 0)
        self._nat_dst = QLineEdit()
        self._nat_dst.setPlaceholderText("DNAT 目标 如 192.168.1.100:8080 (PREROUTING 用)")
        g3_l.addWidget(self._nat_dst, 1, 1)

        g3_l.addWidget(QLabel("NAT 源:"), 1, 2)
        self._nat_src = QLineEdit()
        self._nat_src.setPlaceholderText("SNAT 源 IP (POSTROUTING 用)")
        g3_l.addWidget(self._nat_src, 1, 3)

        g3_l.addWidget(QLabel("代理端口:"), 2, 0)
        self._proxy_port = QLineEdit()
        self._proxy_port.setPlaceholderText("透明代理端口 如 7893 (REDIRECT 用)")
        g3_l.addWidget(self._proxy_port, 2, 1)

        self._skip_private = QCheckBox("跳过私有/保留地址")
        self._skip_private.setToolTip(
            "透明代理必选：跳过 10.0.0.0/8、192.168.0.0/16、127.0.0.0/8 等\n"
            "避免内网流量和回环流量被代理")
        self._skip_private.setChecked(False)
        g3_l.addWidget(self._skip_private, 2, 2, 1, 2)

        g3_l.addWidget(QLabel("备注:"), 3, 0)
        self._comment = QLineEdit()
        self._comment.setPlaceholderText("规则说明 (如: Allow SSH)")
        g3_l.addWidget(self._comment, 3, 1, 1, 2)

        g3_l.addWidget(QLabel("日志前缀:"), 3, 3)
        self._log_prefix = QLineEdit()
        self._log_prefix.setPlaceholderText("LOG 动作用")
        g3_l.addWidget(self._log_prefix, 4, 0, 1, 2)

        top_l.addWidget(g3)

        # 动作切换时提示透明代理参数
        self._action.currentIndexChanged.connect(self._on_action_changed)

        # ── 按钮行 ──
        btn_row = QHBoxLayout()

        # 输出格式选择
        btn_row.addWidget(QLabel("输出格式:"))
        self._format = QComboBox()
        self._format.addItem("全部格式", "all")
        for key, (label, _) in GENERATORS.items():
            self._format.addItem(label, key)
        self._format.setMinimumWidth(200)
        btn_row.addWidget(self._format)

        btn_row.addSpacing(12)

        exec_btn = QPushButton("▶  生成规则")
        exec_btn.setFixedHeight(34)
        exec_btn.setStyleSheet(
            "QPushButton{background:#0078d4;color:#fff;font-weight:bold;"
            "font-size:13px;border-radius:4px;padding:0 22px}"
            "QPushButton:hover{background:#106ebe}"
            "QPushButton:pressed{background:#005a9e}")
        exec_btn.clicked.connect(self._generate)
        btn_row.addWidget(exec_btn)

        clear_btn = QPushButton("清空")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(clear_btn)

        btn_row.addStretch()
        top_l.addLayout(btn_row)

        splitter.addWidget(top)

        # ══════════════ 下半部分：输出 ══════════════
        bottom = QWidget()
        bot_l = QVBoxLayout(bottom)
        bot_l.setContentsMargins(0, 0, 0, 0)
        bot_l.setSpacing(4)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("生成结果:"))
        hdr.addStretch()
        copy_btn = QPushButton("复制全部")
        copy_btn.setFixedWidth(80)
        copy_btn.clicked.connect(self._copy)
        hdr.addWidget(copy_btn)
        bot_l.addLayout(hdr)

        self._output = QTextEdit()
        self._output.setFont(self._mono)
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("生成的防火墙规则将显示在此…")
        bot_l.addWidget(self._output)

        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        root.addWidget(splitter)

        # 状态
        self._status = QLabel("就绪")
        self._status.setStyleSheet("color:#666; font-size:11px;")
        root.addWidget(self._status)

        self._on_chain_changed()

    # ── 链切换时更新说明 ──
    def _on_chain_changed(self):
        chain = self._chain.currentData()
        if chain and chain in CHAINS:
            info = CHAINS[chain]
            self._chain_hint.setText(
                f"<b>用途:</b> {info['desc']}<br>"
                f"<b>典型场景:</b> {info['scene']}")

    # ── 动作切换时自动设置透明代理默认值 ──
    def _on_action_changed(self):
        is_redirect = self._action.currentData() == "REDIRECT"
        if is_redirect:
            if not self._proxy_port.text().strip():
                self._proxy_port.setPlaceholderText("如 7893 (Clash) / 12345 (V2Ray)")
            self._skip_private.setChecked(True)
            chain = self._chain.currentData()
            if chain not in ("PREROUTING", "OUTPUT"):
                self._chain.setCurrentIndex(
                    next(i for i in range(self._chain.count())
                         if self._chain.itemData(i) == "PREROUTING"))

    # ── 收集参数 ──
    def _collect_rule(self) -> FwRule:
        return FwRule(
            action=self._action.currentData(),
            chain=self._chain.currentData(),
            protocol=self._protocol.currentText(),
            src_ip=self._src_ip.text().strip(),
            dst_ip=self._dst_ip.text().strip(),
            port=self._port.text().strip(),
            src_port=self._src_port.text().strip(),
            interface_in=self._iface_in.text().strip(),
            interface_out=self._iface_out.text().strip(),
            comment=self._comment.text().strip(),
            nat_dst=self._nat_dst.text().strip(),
            nat_src=self._nat_src.text().strip(),
            log_prefix=self._log_prefix.text().strip(),
            proxy_port=self._proxy_port.text().strip(),
            skip_private=self._skip_private.isChecked(),
        )

    # ── 生成 ──
    def _generate(self):
        rule = self._collect_rule()
        fmt = self._format.currentData()

        try:
            if fmt == "all":
                result = generate_all(rule)
            else:
                result = generate_one(rule, fmt)
            self._output.setPlainText(result)
            self._status.setText("生成完成")
        except Exception as e:
            self._output.setPlainText(f"错误: {e}")
            self._status.setText(f"出错: {type(e).__name__}")

    def _copy(self):
        t = self._output.toPlainText()
        if t:
            QApplication.clipboard().setText(t)
            self._status.setText("已复制到剪贴板")

    def _clear(self):
        self._output.clear()
        self._src_ip.clear()
        self._dst_ip.clear()
        self._port.clear()
        self._src_port.clear()
        self._iface_in.clear()
        self._iface_out.clear()
        self._nat_dst.clear()
        self._nat_src.clear()
        self._comment.clear()
        self._log_prefix.clear()
        self._proxy_port.clear()
        self._skip_private.setChecked(False)
        self._status.setText("已清空")
