# -*- coding: utf-8 -*-
"""主窗口 — 侧边栏导航 + 首页卡片 + 功能面板

布局:
    ┌─────────────┬──────────────────────────────┐
    │  Sidebar     │  Home Page / Feature Panel   │
    │  230px       │  (QStackedWidget)            │
    │  深色导航     │  浅色内容区                    │
    └─────────────┴──────────────────────────────┘

窗口比例 ≈ 黄金分割 (1200 × 742  →  1200/742 ≈ 1.617 ≈ φ)
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QPushButton, QStackedWidget, QScrollArea, QFrame,
    QSizePolicy,
)
from PyQt5.QtGui import QCursor
from PyQt5.QtCore import Qt, pyqtSignal

# ── 功能面板导入 ─────────────────────────────────────────────
from .panels.codec_panel   import CodecPanel
from .panels.crypto_panel  import CryptoPanel
from .panels.hash_panel    import HashPanel
from .panels.curl_panel    import CurlPanel
from .panels.uuid_panel    import UuidPanel
from .panels.ssh_panel     import SshPanel
from .panels.regex_panel   import RegexPanel
from .panels.diff_panel    import DiffPanel
from .panels.json_panel    import JsonPanel
from .panels.zhconv_panel  import ZhconvPanel
from .panels.mojibake_panel  import MojibakePanel
from .panels.portscan_panel  import PortScanPanel
from .panels.proxy_panel     import ProxyTestPanel
from .panels.html_panel      import HtmlPanel
from .panels.openssl_panel   import OpensslPanel
from .panels.identifier_panel import IdentifierPanel

# ── 功能注册表 ───────────────────────────────────────────────
# (分类名, 分类色, [(显示名, 简介, Panel类), ...])
FEATURES = [
    ("编码转换", "#0078d4", [
        ("编码 / 解码",   "Base64、URL、Hex、Unicode 等编解码转换",   CodecPanel),
        ("JSON 格式化",   "JSON 美化、压缩、语法验证",              JsonPanel),
        ("HTML 美化",     "HTML 代码格式化，XPath / 正则搜索",      HtmlPanel),
        ("简繁转换",      "中文简体繁体互转，支持台湾/香港变体",       ZhconvPanel),
        ("乱码修复",      "自动检测编码组合，一键修复乱码文本",       MojibakePanel),
    ]),
    ("加密安全", "#107c10", [
        ("加密 / 解密",   "AES、3DES、ChaCha20、Salsa20 等 11 种算法", CryptoPanel),
        ("哈希 / 摘要",   "MD5、SHA、BLAKE2、HMAC 等哈希计算",        HashPanel),
        ("密文识别",      "根据特征识别加密/哈希算法 (MD5, bcrypt, JWT ...)", IdentifierPanel),
        ("SSH 密钥",      "生成 RSA / Ed25519 / ECDSA 密钥对并导出",  SshPanel),
        ("OpenSSL 密钥",  "非对称密钥对生成 (PEM/DER/OpenSSH 导出)",   OpensslPanel),
        ("UUID 生成",     "UUID v1/v3/v4/v5 批量生成，多种格式",       UuidPanel),
    ]),
    ("开发辅助", "#ca5010", [
        ("cURL 转换",     "cURL 命令转换为 Python / Go / Java 等代码", CurlPanel),
        ("正则测试",      "正则表达式实时匹配测试与高亮显示",           RegexPanel),
        ("字符串比对",    "两段文本逐行 / 逐字符差异高亮对比",          DiffPanel),
    ]),
    ("网络工具", "#8764b8", [
        ("端口扫描",      "TCP 端口开放检测与服务协议自动识别",         PortScanPanel),
        ("代理测试",      "HTTP / SOCKS5 代理批量测试 URL 可达性",     ProxyTestPanel),
    ]),
]


# ═════════════════════════════════════════════════════════════
#  首页卡片
# ═════════════════════════════════════════════════════════════
class FeatureCard(QFrame):
    """可点击的功能卡片"""
    clicked = pyqtSignal()

    def __init__(self, title, description, color, parent=None):
        super().__init__(parent)
        self.setObjectName("featureCard")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._color = color
        self._setup_ui(title, description, color)
        self._apply_style(False)

    def _setup_ui(self, title, desc, color):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        # 顶部色条
        bar = QFrame()
        bar.setFixedHeight(4)
        bar.setStyleSheet(
            f"background:{color}; border-radius:2px; border:none;")
        layout.addWidget(bar)

        # 标题
        t = QLabel(title)
        t.setStyleSheet(
            "font-size:15px; font-weight:bold; color:#1e2433; "
            "background:transparent; border:none; padding:0;")
        layout.addWidget(t)

        # 描述
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(
            "font-size:12px; color:#6b7a8d; line-height:1.5; "
            "background:transparent; border:none; padding:0;")
        layout.addWidget(d)
        layout.addStretch()

    def _apply_style(self, hovered):
        if hovered:
            self.setStyleSheet(
                f"#featureCard{{background:#f8fbff; "
                f"border:2px solid {self._color}; border-radius:10px;}}")
        else:
            self.setStyleSheet(
                "#featureCard{background:#ffffff; "
                "border:1px solid #dfe2e8; border-radius:10px;}")

    def enterEvent(self, e):
        self._apply_style(True)

    def leaveEvent(self, e):
        self._apply_style(False)

    def mousePressEvent(self, e):
        self.clicked.emit()


# ═════════════════════════════════════════════════════════════
#  主窗口
# ═════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._nav_btns = []           # 侧边栏按钮
        self._panel_index_map = {}    # btn_id → stack_index
        self._active_btn = None

        self._setup_window()
        self._build_ui()

    # ── 窗口属性 ─────────────────────────────────────────────
    def _setup_window(self):
        self.setWindowTitle("QtCoder — 开发工具箱")
        # 黄金分割: 1200/742 ≈ 1.617 ≈ φ
        self.resize(1200, 742)
        self.setMinimumSize(980, 605)

    # ── 整体布局 ─────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        self._stack.setObjectName("contentArea")
        self._stack.setStyleSheet(
            "#contentArea{background:#f0f2f5; border:none;}")

        # index 0 = 首页
        self._stack.addWidget(self._build_home_page())

        # index 1.. = 各功能面板
        idx = 1
        for _cat, _color, items in FEATURES:
            for _name, _desc, PanelClass in items:
                self._stack.addWidget(PanelClass())
                idx += 1

        root.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

        # 默认显示首页
        self._go_home()

    # ── 侧边栏 ──────────────────────────────────────────────
    def _build_sidebar(self):
        sidebar = QWidget()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet(
            "background: qlineargradient("
            "x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #1a1f2e, stop:1 #232939);"
        )

        outer = QVBoxLayout(sidebar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── 品牌区 ───────────────────────────────────────────
        brand = QWidget()
        brand.setStyleSheet("background:transparent;")
        bl = QVBoxLayout(brand)
        bl.setContentsMargins(22, 20, 22, 6)
        bl.setSpacing(2)

        title = QLabel("QtCoder")
        title.setStyleSheet(
            "color:#ffffff; font-size:20px; font-weight:bold; "
            "background:transparent;")
        bl.addWidget(title)

        sub = QLabel("开发工具箱")
        sub.setStyleSheet(
            "color:#707d8f; font-size:12px; background:transparent;")
        bl.addWidget(sub)
        outer.addWidget(brand)

        # 分隔线
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#2e3650; border:none;")
        outer.addWidget(sep)

        # ── 导航按钮（可滚动）──────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{border:none; background:transparent;}"
            "QScrollBar:vertical{width:5px; background:transparent;}"
            "QScrollBar::handle:vertical{background:#3a4254; "
            "border-radius:2px; min-height:30px;}"
            "QScrollBar::add-line:vertical,"
            "QScrollBar::sub-line:vertical{height:0;}"
        )

        nav = QWidget()
        nav.setStyleSheet("background:transparent;")
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(0, 10, 0, 16)
        nl.setSpacing(0)

        # 主页按钮
        self._home_btn = self._make_nav_btn("  主页", bold=True)
        self._home_btn.clicked.connect(self._go_home)
        nl.addWidget(self._home_btn)
        nl.addSpacing(4)

        # 功能分类
        panel_idx = 1
        for cat_name, cat_color, items in FEATURES:
            # 分类标题
            cat = QLabel(f"  {cat_name}")
            cat.setStyleSheet(
                f"color:#5c6a7e; font-size:10px; font-weight:bold; "
                f"letter-spacing:3px; padding:16px 20px 6px 16px; "
                f"background:transparent;")
            nl.addWidget(cat)

            for name, desc, _cls in items:
                btn = self._make_nav_btn(f"  {name}")
                idx = panel_idx
                btn.clicked.connect(
                    lambda checked, i=idx: self._go_panel(i))
                nl.addWidget(btn)
                self._nav_btns.append(btn)
                self._panel_index_map[id(btn)] = idx
                panel_idx += 1

        nl.addStretch()
        scroll.setWidget(nav)
        outer.addWidget(scroll, stretch=1)

        return sidebar

    def _make_nav_btn(self, text, bold=False):
        btn = QPushButton(text)
        weight = "bold" if bold else "normal"
        btn.setFixedHeight(38)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setStyleSheet(f"""
            QPushButton {{
                text-align:left; padding:0 20px 0 22px;
                border:none; border-radius:6px;
                margin:1px 10px; color:#b0b8c4;
                background:transparent;
                font-size:13px; font-weight:{weight};
            }}
            QPushButton:hover {{
                background:rgba(255,255,255,0.07); color:#e0e4ea;
            }}
        """)
        return btn

    def _set_btn_active(self, btn):
        # 取消上一个
        if self._active_btn:
            bold = self._active_btn is self._home_btn
            weight = "bold" if bold else "normal"
            self._active_btn.setStyleSheet(f"""
                QPushButton {{
                    text-align:left; padding:0 20px 0 22px;
                    border:none; border-radius:6px;
                    margin:1px 10px; color:#b0b8c4;
                    background:transparent;
                    font-size:13px; font-weight:{weight};
                }}
                QPushButton:hover {{
                    background:rgba(255,255,255,0.07); color:#e0e4ea;
                }}
            """)
        # 激活新的
        self._active_btn = btn
        btn.setStyleSheet("""
            QPushButton {
                text-align:left; padding:0 20px 0 22px;
                border:none; border-radius:6px;
                margin:1px 10px; color:#ffffff;
                background:#0078d4;
                font-size:13px; font-weight:bold;
            }
            QPushButton:hover { background:#106ebe; }
        """)

    # ── 首页 ─────────────────────────────────────────────────
    def _build_home_page(self):
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setStyleSheet(
            "QScrollArea{border:none; background:#f0f2f5;}")

        container = QWidget()
        container.setStyleSheet("background:#f0f2f5;")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(36, 32, 36, 32)
        cl.setSpacing(12)

        # 欢迎标题
        welcome = QLabel("QtCoder")
        welcome.setStyleSheet(
            "font-size:28px; font-weight:bold; color:#1e2433; "
            "background:transparent;")
        cl.addWidget(welcome)

        welcome_sub = QLabel("选择一个工具开始使用")
        welcome_sub.setStyleSheet(
            "font-size:14px; color:#6b7a8d; background:transparent; "
            "margin-bottom:8px;")
        cl.addWidget(welcome_sub)

        # 各分类卡片
        panel_idx = 1
        for cat_name, cat_color, items in FEATURES:
            cl.addSpacing(8)

            # 分类标题 (带色条)
            cat_row = QHBoxLayout()
            cat_bar = QFrame()
            cat_bar.setFixedSize(4, 20)
            cat_bar.setStyleSheet(
                f"background:{cat_color}; border-radius:2px; border:none;")
            cat_row.addWidget(cat_bar)
            cat_label = QLabel(f" {cat_name}")
            cat_label.setStyleSheet(
                "font-size:16px; font-weight:bold; color:#1e2433; "
                "background:transparent;")
            cat_row.addWidget(cat_label)
            cat_row.addStretch()
            cl.addLayout(cat_row)

            cl.addSpacing(4)

            # 卡片网格 — 3 列
            grid = QGridLayout()
            grid.setSpacing(16)
            for i, (name, desc, _cls) in enumerate(items):
                card = FeatureCard(name, desc, cat_color)
                card.setMinimumSize(220, 120)
                card.setSizePolicy(
                    QSizePolicy.Expanding, QSizePolicy.Fixed)
                idx = panel_idx + i
                card.clicked.connect(
                    lambda i=idx: self._go_panel(i))
                grid.addWidget(card, i // 3, i % 3)

            # 填充空列，保持 3 列等宽
            col_count = min(len(items), 3)
            for c in range(col_count, 3):
                spacer = QWidget()
                spacer.setStyleSheet("background:transparent;")
                grid.addWidget(spacer, 0, c)
            for c in range(3):
                grid.setColumnStretch(c, 1)

            cl.addLayout(grid)
            panel_idx += len(items)

        cl.addStretch()
        page.setWidget(container)
        return page

    # ── 导航 ─────────────────────────────────────────────────
    def _go_home(self):
        self._stack.setCurrentIndex(0)
        self._set_btn_active(self._home_btn)

    def _go_panel(self, idx):
        self._stack.setCurrentIndex(idx)
        # 找到对应的侧边栏按钮并激活
        for btn in self._nav_btns:
            if self._panel_index_map.get(id(btn)) == idx:
                self._set_btn_active(btn)
                return
