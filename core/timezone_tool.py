# -*- coding: utf-8 -*-
"""时区工具 — 世界时钟 + 时间戳互转（纯本地，不联网）

依赖: zoneinfo (Python 3.9+ 内置) + tzdata (Windows 需安装: pip install tzdata)
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

# ── 主要国家/地区时区表 ──────────────────────────────────────────
# 顺序: 中国优先，然后亚洲 → 欧洲 → 美洲 → 大洋洲
WORLD_ZONES: list[tuple[str, str]] = [
    ("中国 (北京/上海)",    "Asia/Shanghai"),
    ("日本 (东京)",         "Asia/Tokyo"),
    ("韩国 (首尔)",         "Asia/Seoul"),
    ("新加坡",              "Asia/Singapore"),
    ("印度 (新德里)",       "Asia/Kolkata"),
    ("阿联酋 (迪拜)",       "Asia/Dubai"),
    ("沙特阿拉伯 (利雅得)", "Asia/Riyadh"),
    ("俄罗斯 (莫斯科)",     "Europe/Moscow"),
    ("德国 (柏林)",         "Europe/Berlin"),
    ("法国 (巴黎)",         "Europe/Paris"),
    ("英国 (伦敦)",         "Europe/London"),
    ("巴西 (圣保罗)",       "America/Sao_Paulo"),
    ("美国东部 (纽约)",     "America/New_York"),
    ("美国中部 (芝加哥)",   "America/Chicago"),
    ("美国西部 (洛杉矶)",   "America/Los_Angeles"),
    ("加拿大 (多伦多)",     "America/Toronto"),
    ("澳大利亚 (悉尼)",     "Australia/Sydney"),
    ("新西兰 (奥克兰)",     "Pacific/Auckland"),
]

# ── 常用日期时间格式 ────────────────────────────────────────────
# (格式字符串, 示例说明)
DATETIME_FORMATS: list[tuple[str, str]] = [
    ("%Y-%m-%d %H:%M:%S",   "2024-01-15 12:30:00"),
    ("%Y/%m/%d %H:%M:%S",   "2024/01/15 12:30:00"),
    ("%Y-%m-%dT%H:%M:%S",   "2024-01-15T12:30:00  (ISO 8601)"),
    ("%d/%m/%Y %H:%M:%S",   "15/01/2024 12:30:00"),
    ("%m/%d/%Y %H:%M:%S",   "01/15/2024 12:30:00"),
    ("%Y-%m-%d",            "2024-01-15  (仅日期)"),
    ("%Y/%m/%d",            "2024/01/15  (仅日期)"),
    ("%H:%M:%S",            "12:30:00  (仅时间)"),
    ("%Y年%m月%d日 %H:%M:%S", "2024年01月15日 12:30:00"),
]

# ── UTC 偏移格式化 ──────────────────────────────────────────────
def _fmt_offset(dt: datetime) -> str:
    off = dt.utcoffset()
    if off is None:
        return "UTC?"
    total_sec = int(off.total_seconds())
    sign = "+" if total_sec >= 0 else "-"
    total_sec = abs(total_sec)
    h, m = divmod(total_sec // 60, 60)
    return f"UTC{sign}{h}" if m == 0 else f"UTC{sign}{h}:{m:02d}"


# ── 世界时钟 ──────────────────────────────────────────────────
def get_world_times() -> list[dict]:
    """返回所有时区的当前时间信息，每次调用返回最新时刻。"""
    now_utc = datetime.now(ZoneInfo("UTC"))
    result = []
    for name, zone_id in WORLD_ZONES:
        try:
            dt = now_utc.astimezone(ZoneInfo(zone_id))
            active = 9 <= dt.hour < 21
            result.append({
                "name":       name,
                "zone_id":    zone_id,
                "time":       dt.strftime("%H:%M:%S"),
                "date":       dt.strftime("%m-%d  %a"),
                "offset_str": _fmt_offset(dt),
                "active":     active,
            })
        except Exception:
            result.append({
                "name":       name,
                "zone_id":    zone_id,
                "time":       "错误",
                "date":       "",
                "offset_str": "",
                "active":     False,
            })
    return result


# ── 时间戳 → 格式化时间 ───────────────────────────────────────
def ts_to_datetime(timestamp_str: str, zone_id: str, fmt: str) -> str:
    """Unix 时间戳 → 格式化时间字符串。

    自动识别秒级（≤10位整数）和毫秒级（13位整数）。
    """
    ts = float(timestamp_str.strip())
    # 毫秒检测: 绝对值 > 1e10 视为毫秒
    if abs(ts) > 1e10:
        ts = ts / 1000.0
    tz = ZoneInfo(zone_id)
    dt = datetime.fromtimestamp(ts, tz=tz)
    return dt.strftime(fmt)


# ── 格式化时间 → 时间戳 ───────────────────────────────────────
def datetime_to_ts(dt_str: str, zone_id: str, fmt: str) -> tuple[int, int]:
    """格式化时间字符串 → (秒级时间戳, 毫秒级时间戳)。"""
    dt = datetime.strptime(dt_str.strip(), fmt)
    tz = ZoneInfo(zone_id)
    dt = dt.replace(tzinfo=tz)
    ts_f = dt.timestamp()
    return int(ts_f), int(ts_f * 1000)


# ── 当前时间戳 ─────────────────────────────────────────────────
def current_timestamp_s() -> int:
    return int(time.time())

def current_timestamp_ms() -> int:
    return int(time.time() * 1000)
