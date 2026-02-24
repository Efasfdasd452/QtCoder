# -*- coding: utf-8 -*-
"""时区面板 — 世界时钟 + 时间戳互转

Tab 1 · 世界时钟  — 实时显示 18 个主要国家/地区时间，标注是否处于活跃时段
Tab 2 · 时间戳转换 — Unix 时间戳 ↔ 格式化时间字符串（支持秒/毫秒，多时区，多格式）
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QTabWidget, QApplication,
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt, QTimer

from core.timezone_tool import (
    get_world_times, ts_to_datetime, datetime_to_ts,
    current_timestamp_s, current_timestamp_ms,
    WORLD_ZONES, DATETIME_FORMATS,
)

# ── 字体 / 颜色 ───────────────────────────────────────────────
_MONO = QFont("Consolas", 10)
_MONO.setStyleHint(QFont.Monospace)

_CLR_ACTIVE_BG = QColor("#e6f4ea")   # 活跃时段行背景（浅绿）
_CLR_ACTIVE_FG = QColor("#107c10")   # 活跃状态文字（深绿）
_CLR_REST_BG   = QColor("#ffffff")   # 休息时段行背景（白）
_CLR_REST_FG   = QColor("#9e9e9e")   # 休息状态文字（灰）
_CLR_CHINA_BG  = QColor("#fff8e1")   # 中国行背景（淡黄，突出参考时区）

# ── 工具 ───────────────────────────────────────────────────────
def _btn(text: str, color: str, width: int = 0) -> QPushButton:
    b = QPushButton(text)
    if width:
        b.setFixedWidth(width)
    b.setFixedHeight(30)
    b.setStyleSheet(
        f"QPushButton{{background:{color};color:#fff;font-weight:bold;"
        f"border-radius:4px;border:none;font-size:12px;}}"
        f"QPushButton:hover{{opacity:0.85;}}"
    )
    return b


def _combo_set(combo: QComboBox, text: str):
    idx = combo.findText(text)
    if idx >= 0:
        combo.setCurrentIndex(idx)


# ═════════════════════════════════════════════════════════════
#  面板主体
# ═════════════════════════════════════════════════════════════
class TimezonePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh_clock)
        self._build_ui()

    # ── 生命周期：面板可见时才开始计时，节省资源 ─────────────
    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_clock()
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    # ── 整体布局 ──────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(8)

        tabs = QTabWidget()
        tabs.addTab(self._build_clock_tab(),     "🌍  世界时钟")
        tabs.addTab(self._build_converter_tab(), "⏱  时间戳转换")
        root.addWidget(tabs)

    # ─────────────────────────────────────────────────────────
    #  Tab 1: 世界时钟
    # ─────────────────────────────────────────────────────────
    def _build_clock_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        hint = QLabel(
            "🟡 活跃时段：当地时间 09:00 ~ 21:00     "
            "🇨🇳 中国（北京/上海）为参考时区，每秒自动刷新"
        )
        hint.setStyleSheet("color:#555; font-size:12px;")
        lay.addWidget(hint)

        self._clock_table = QTableWidget(0, 5)
        self._clock_table.setHorizontalHeaderLabels(
            ["国家 / 地区", "当前时间", "日期", "UTC 偏移", "活跃状态"])
        hdr = self._clock_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 2, 3, 4):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self._clock_table.verticalHeader().setDefaultSectionSize(30)
        self._clock_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._clock_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._clock_table.setFont(_MONO)
        self._clock_table.setAlternatingRowColors(False)
        lay.addWidget(self._clock_table)
        return w

    def _refresh_clock(self):
        times = get_world_times()
        table = self._clock_table
        if table.rowCount() != len(times):
            table.setRowCount(len(times))

        for row, info in enumerate(times):
            active  = info["active"]
            is_china = row == 0          # 第一行是中国

            # 行背景
            if is_china:
                bg = _CLR_CHINA_BG
            elif active:
                bg = _CLR_ACTIVE_BG
            else:
                bg = _CLR_REST_BG

            cells = [
                (info["name"],        Qt.AlignVCenter | Qt.AlignLeft),
                (info["time"],        Qt.AlignCenter),
                (info["date"],        Qt.AlignCenter),
                (info["offset_str"],  Qt.AlignCenter),
                ("● 活跃" if active else "○ 休息", Qt.AlignCenter),
            ]
            for col, (text, align) in enumerate(cells):
                item = table.item(row, col)
                if item is None:
                    item = QTableWidgetItem()
                    table.setItem(row, col, item)
                item.setText(text)
                item.setTextAlignment(align)
                item.setBackground(bg)
                if col == 4:
                    item.setForeground(_CLR_ACTIVE_FG if active else _CLR_REST_FG)
                else:
                    item.setForeground(QColor("#1e2433"))
                # 中国行加粗
                font = QFont(_MONO)
                if is_china:
                    font.setBold(True)
                item.setFont(font)

    # ─────────────────────────────────────────────────────────
    #  Tab 2: 时间戳转换
    # ─────────────────────────────────────────────────────────
    def _build_converter_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(12)

        lay.addWidget(self._build_ts_to_dt_group())
        lay.addWidget(self._build_dt_to_ts_group())
        lay.addStretch()
        return w

    # ── 时间戳 → 时间字符串 ───────────────────────────────────
    def _build_ts_to_dt_group(self) -> QGroupBox:
        grp = QGroupBox("时间戳  →  格式化时间")
        g = QVBoxLayout(grp)
        g.setSpacing(7)

        # 输入行
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Unix 时间戳:"))
        self._ts_in = QLineEdit()
        self._ts_in.setFont(_MONO)
        self._ts_in.setPlaceholderText("秒级（10位）或毫秒级（13位），如 1705280400 或 1705280400000")
        r1.addWidget(self._ts_in, stretch=1)

        b_s = QPushButton("当前(秒)")
        b_s.setFixedWidth(70)
        b_s.clicked.connect(lambda: self._ts_in.setText(str(current_timestamp_s())))
        b_ms = QPushButton("当前(毫秒)")
        b_ms.setFixedWidth(80)
        b_ms.clicked.connect(lambda: self._ts_in.setText(str(current_timestamp_ms())))
        r1.addWidget(b_s)
        r1.addWidget(b_ms)
        g.addLayout(r1)

        # 选项行
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("时区:"))
        self._ts_tz = self._make_tz_combo()
        r2.addWidget(self._ts_tz, stretch=1)
        r2.addSpacing(12)
        r2.addWidget(QLabel("格式:"))
        self._ts_fmt = self._make_fmt_combo()
        r2.addWidget(self._ts_fmt, stretch=2)
        g.addLayout(r2)

        # 输出行
        r3 = QHBoxLayout()
        b_conv = _btn("转 换  →", "#0078d4", 90)
        b_conv.clicked.connect(self._on_ts_to_dt)
        r3.addWidget(b_conv)
        self._ts_out = QLineEdit()
        self._ts_out.setFont(_MONO)
        self._ts_out.setReadOnly(True)
        self._ts_out.setPlaceholderText("转换结果")
        r3.addWidget(self._ts_out, stretch=1)
        b_copy = QPushButton("复制")
        b_copy.setFixedWidth(50)
        b_copy.clicked.connect(
            lambda: QApplication.clipboard().setText(self._ts_out.text()))
        r3.addWidget(b_copy)
        g.addLayout(r3)

        self._ts_err = QLabel("")
        self._ts_err.setStyleSheet("color:#ca5010; font-size:11px;")
        g.addWidget(self._ts_err)
        return grp

    def _on_ts_to_dt(self):
        ts_str = self._ts_in.text().strip()
        if not ts_str:
            self._ts_err.setText("请输入时间戳")
            return
        try:
            result = ts_to_datetime(ts_str, self._ts_tz.currentData(),
                                    self._ts_fmt.currentData())
            self._ts_out.setText(result)
            self._ts_err.setText("")
        except Exception as e:
            self._ts_err.setText(f"错误：{e}")
            self._ts_out.clear()

    # ── 时间字符串 → 时间戳 ───────────────────────────────────
    def _build_dt_to_ts_group(self) -> QGroupBox:
        grp = QGroupBox("格式化时间  →  时间戳")
        g = QVBoxLayout(grp)
        g.setSpacing(7)

        # 输入行
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("时间字符串:"))
        self._dt_in = QLineEdit()
        self._dt_in.setFont(_MONO)
        self._dt_in.setPlaceholderText("如 2024-01-15 12:30:00")
        r1.addWidget(self._dt_in, stretch=1)
        b_now = QPushButton("当前时间")
        b_now.setFixedWidth(70)
        b_now.clicked.connect(self._fill_current_dt)
        r1.addWidget(b_now)
        g.addLayout(r1)

        # 选项行
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("时区:"))
        self._dt_tz = self._make_tz_combo()
        r2.addWidget(self._dt_tz, stretch=1)
        r2.addSpacing(12)
        r2.addWidget(QLabel("格式:"))
        self._dt_fmt = self._make_fmt_combo()
        r2.addWidget(self._dt_fmt, stretch=2)
        g.addLayout(r2)

        # 输出行：秒 + 毫秒 并排
        r3 = QHBoxLayout()
        b_conv = _btn("转 换  →", "#107c10", 90)
        b_conv.clicked.connect(self._on_dt_to_ts)
        r3.addWidget(b_conv)

        r3.addWidget(QLabel("秒:"))
        self._dt_out_s = QLineEdit()
        self._dt_out_s.setFont(_MONO)
        self._dt_out_s.setReadOnly(True)
        self._dt_out_s.setPlaceholderText("秒级时间戳")
        r3.addWidget(self._dt_out_s)
        b_cs = QPushButton("复制")
        b_cs.setFixedWidth(50)
        b_cs.clicked.connect(
            lambda: QApplication.clipboard().setText(self._dt_out_s.text()))
        r3.addWidget(b_cs)

        r3.addSpacing(8)
        r3.addWidget(QLabel("毫秒:"))
        self._dt_out_ms = QLineEdit()
        self._dt_out_ms.setFont(_MONO)
        self._dt_out_ms.setReadOnly(True)
        self._dt_out_ms.setPlaceholderText("毫秒级时间戳")
        r3.addWidget(self._dt_out_ms)
        b_cms = QPushButton("复制")
        b_cms.setFixedWidth(50)
        b_cms.clicked.connect(
            lambda: QApplication.clipboard().setText(self._dt_out_ms.text()))
        r3.addWidget(b_cms)
        g.addLayout(r3)

        self._dt_err = QLabel("")
        self._dt_err.setStyleSheet("color:#ca5010; font-size:11px;")
        g.addWidget(self._dt_err)
        return grp

    def _on_dt_to_ts(self):
        dt_str = self._dt_in.text().strip()
        if not dt_str:
            self._dt_err.setText("请输入时间字符串")
            return
        try:
            s, ms = datetime_to_ts(dt_str, self._dt_tz.currentData(),
                                   self._dt_fmt.currentData())
            self._dt_out_s.setText(str(s))
            self._dt_out_ms.setText(str(ms))
            self._dt_err.setText("")
        except Exception as e:
            self._dt_err.setText(f"错误：{e}")
            self._dt_out_s.clear()
            self._dt_out_ms.clear()

    def _fill_current_dt(self):
        zone_id = self._dt_tz.currentData()
        fmt = self._dt_fmt.currentData()
        try:
            dt = datetime.now(ZoneInfo(zone_id))
        except Exception:
            dt = datetime.now()
        self._dt_in.setText(dt.strftime(fmt))

    # ── 复用：时区下拉 / 格式下拉 ─────────────────────────────
    def _make_tz_combo(self) -> QComboBox:
        cb = QComboBox()
        cb.addItem("UTC", "UTC")
        for name, zid in WORLD_ZONES:
            cb.addItem(name, zid)
        _combo_set(cb, "中国 (北京/上海)")
        return cb

    def _make_fmt_combo(self) -> QComboBox:
        cb = QComboBox()
        for fmt, example in DATETIME_FORMATS:
            cb.addItem(f"{fmt}    （示例：{example}）", fmt)
        return cb
