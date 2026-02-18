# -*- coding: utf-8 -*-
"""视频压缩核心模块 — 基于 FFmpeg

功能:
  - 视频信息探测 (ffprobe)
  - 压缩命令构建 (ffmpeg)
  - 进度解析
  - 硬件编码器检测
"""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

_NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}


# ── FFmpeg / FFprobe 查找（只用本地 vendor/ffmpeg/ 目录）─────

def find_ffmpeg() -> Optional[str]:
    from core.ffmpeg_downloader import get_ffmpeg_path
    return get_ffmpeg_path()


def find_ffprobe() -> Optional[str]:
    from core.ffmpeg_downloader import get_ffprobe_path
    return get_ffprobe_path()


# ── 视频信息 ─────────────────────────────────────────────────

@dataclass
class VideoInfo:
    path: str = ""
    file_size: int = 0
    duration: float = 0.0
    width: int = 0
    height: int = 0
    video_codec: str = ""
    video_bitrate: int = 0      # kbps
    fps: float = 0.0
    audio_codec: str = ""
    audio_bitrate: int = 0      # kbps
    audio_channels: int = 0
    audio_sample_rate: int = 0

    @property
    def duration_str(self) -> str:
        s = int(self.duration)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    @property
    def file_size_str(self) -> str:
        if self.file_size >= 1024 ** 3:
            return f"{self.file_size / 1024 ** 3:.2f} GB"
        if self.file_size >= 1024 ** 2:
            return f"{self.file_size / 1024 ** 2:.1f} MB"
        return f"{self.file_size / 1024:.0f} KB"

    @property
    def resolution_str(self) -> str:
        return f"{self.width}×{self.height}" if self.width else "未知"

    @property
    def video_bitrate_str(self) -> str:
        if self.video_bitrate >= 1000:
            return f"{self.video_bitrate / 1000:.1f} Mbps"
        return f"{self.video_bitrate} kbps" if self.video_bitrate else "未知"

    @property
    def audio_info_str(self) -> str:
        parts = []
        if self.audio_codec:
            parts.append(self.audio_codec.upper())
        if self.audio_channels:
            parts.append(f"{self.audio_channels}声道")
        if self.audio_sample_rate:
            parts.append(f"{self.audio_sample_rate} Hz")
        if self.audio_bitrate:
            parts.append(f"{self.audio_bitrate} kbps")
        return "  ".join(parts) if parts else "无音频"


def probe_video(path: str) -> VideoInfo:
    ffprobe = find_ffprobe()
    if not ffprobe:
        raise FileNotFoundError("未找到 ffprobe，请安装 FFmpeg")

    result = subprocess.run(
        [ffprobe, "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace", **_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {result.stderr[:500]}")

    data = json.loads(result.stdout)
    info = VideoInfo(path=path, file_size=os.path.getsize(path))

    fmt = data.get("format", {})
    info.duration = float(fmt.get("duration", 0))

    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not info.video_codec:
            info.video_codec = s.get("codec_name", "")
            info.width = int(s.get("width", 0))
            info.height = int(s.get("height", 0))
            br = s.get("bit_rate")
            if br:
                info.video_bitrate = int(br) // 1000
            rfr = s.get("r_frame_rate", "0/1")
            try:
                n, d = rfr.split("/")
                info.fps = round(float(n) / float(d), 3) if float(d) else 0
            except (ValueError, ZeroDivisionError):
                pass
        elif s.get("codec_type") == "audio" and not info.audio_codec:
            info.audio_codec = s.get("codec_name", "")
            br = s.get("bit_rate")
            if br:
                info.audio_bitrate = int(br) // 1000
            info.audio_channels = int(s.get("channels", 0))
            info.audio_sample_rate = int(s.get("sample_rate", 0))

    if not info.video_bitrate and info.duration > 0:
        total = int(fmt.get("bit_rate", 0)) // 1000
        info.video_bitrate = max(total - info.audio_bitrate, 0)

    return info


# ── 预设与选项 ───────────────────────────────────────────────

PRESETS = {
    "compat": {
        "name": "通用兼容",
        "desc": "H.264 CRF 18 · 画质优先 · 所有设备可播放",
        "vcodec": "libx264", "crf": 18, "speed": "medium",
        "acodec": "aac", "abitrate": "192k",
    },
    "balanced": {
        "name": "推荐均衡",
        "desc": "H.265 CRF 20 · 画质体积兼顾 · PC/手机可播放",
        "vcodec": "libx265", "crf": 20, "speed": "medium",
        "acodec": "aac", "abitrate": "192k",
    },
    "max_compress": {
        "name": "极限压缩",
        "desc": "H.265 CRF 23 · 体积最小 · 画质仍然不错",
        "vcodec": "libx265", "crf": 23, "speed": "slow",
        "acodec": "aac", "abitrate": "128k",
    },
}

CODECS = [
    ("libx264",    "H.264 (兼容性最佳)"),
    ("libx265",    "H.265 / HEVC (压缩率高，推荐)"),
    ("libaom-av1", "AV1 (压缩率最高，编码很慢)"),
    ("libvpx-vp9", "VP9 (适合 Web)"),
]

SPEEDS = [
    ("ultrafast", "极快 (质量最低)"),
    ("superfast", "超快"),
    ("veryfast",  "很快"),
    ("faster",    "较快"),
    ("fast",      "快"),
    ("medium",    "中等 (推荐)"),
    ("slow",      "慢 (质量更好)"),
    ("slower",    "较慢"),
    ("veryslow",  "很慢 (质量最好)"),
]

RESOLUTIONS = [
    (0,    0,    "保持原始分辨率"),
    (3840, 2160, "3840×2160 (4K)"),
    (2560, 1440, "2560×1440 (2K)"),
    (1920, 1080, "1920×1080 (1080P)"),
    (1280, 720,  "1280×720 (720P)"),
]

AUDIO_OPTS = [
    ("copy",    "直接复制 (不重编码)"),
    ("aac_320", "AAC 320 kbps (高品质)"),
    ("aac_192", "AAC 192 kbps (推荐)"),
    ("aac_128", "AAC 128 kbps (体积小)"),
]


# ── 硬件编码器检测 ───────────────────────────────────────────

def detect_hw_encoders() -> list:
    """返回 [(codec_name, display_name), ...]"""
    ff = find_ffmpeg()
    if not ff:
        return []
    try:
        r = subprocess.run(
            [ff, "-hide_banner", "-encoders"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=10, **_NO_WINDOW,
        )
        out = r.stdout
    except Exception:
        return []

    candidates = [
        ("h264_nvenc", "H.264 NVENC (NVIDIA)"),
        ("hevc_nvenc", "H.265 NVENC (NVIDIA)"),
        ("h264_qsv",  "H.264 QSV (Intel)"),
        ("hevc_qsv",  "H.265 QSV (Intel)"),
        ("h264_amf",  "H.264 AMF (AMD)"),
        ("hevc_amf",  "H.265 AMF (AMD)"),
    ]
    return [(c, n) for c, n in candidates if c in out]


# ── 压缩配置与命令构建 ──────────────────────────────────────

@dataclass
class CompressConfig:
    input_path: str = ""
    output_path: str = ""
    vcodec: str = "libx265"
    crf: int = 20
    speed: str = "medium"
    target_width: int = 0       # 0 = 保持原始
    target_height: int = 0
    audio_mode: str = "aac_192"

    @classmethod
    def from_preset(cls, key: str, inp: str, out: str):
        p = PRESETS[key]
        return cls(
            input_path=inp, output_path=out,
            vcodec=p["vcodec"], crf=p["crf"], speed=p["speed"],
            audio_mode="aac_192",
        )


def build_command(cfg: CompressConfig) -> list:
    ff = find_ffmpeg()
    if not ff:
        raise FileNotFoundError("未找到 ffmpeg")

    cmd = [ff, "-y", "-hide_banner", "-i", cfg.input_path]

    cmd += ["-c:v", cfg.vcodec]

    vc = cfg.vcodec
    if vc in ("libx264", "libx265"):
        cmd += ["-crf", str(cfg.crf), "-preset", cfg.speed]
    elif vc == "libaom-av1":
        cpu = {"ultrafast": "8", "superfast": "7", "veryfast": "6",
               "faster": "5", "fast": "4", "medium": "4",
               "slow": "2", "slower": "1", "veryslow": "0"}.get(cfg.speed, "4")
        cmd += ["-crf", str(cfg.crf), "-cpu-used", cpu, "-row-mt", "1"]
    elif vc == "libvpx-vp9":
        cpu = {"ultrafast": "5", "superfast": "4", "veryfast": "3",
               "faster": "2", "fast": "2", "medium": "1",
               "slow": "1", "slower": "0", "veryslow": "0"}.get(cfg.speed, "1")
        cmd += ["-crf", str(cfg.crf), "-b:v", "0", "-cpu-used", cpu,
                "-row-mt", "1"]
    elif "nvenc" in vc:
        preset = {"ultrafast": "p1", "superfast": "p2", "veryfast": "p3",
                  "faster": "p4", "fast": "p5", "medium": "p5",
                  "slow": "p6", "slower": "p7", "veryslow": "p7"
                  }.get(cfg.speed, "p5")
        cmd += ["-rc", "vbr", "-cq", str(cfg.crf), "-preset", preset]
    elif "qsv" in vc:
        cmd += ["-global_quality", str(cfg.crf), "-preset", cfg.speed]
    elif "amf" in vc:
        cmd += ["-rc", "vbr_latency",
                "-qp_i", str(cfg.crf), "-qp_p", str(cfg.crf)]

    if cfg.target_width > 0:
        cmd += ["-vf", f"scale={cfg.target_width}:-2:flags=lanczos"]

    if cfg.audio_mode == "copy":
        cmd += ["-c:a", "copy"]
    else:
        parts = cfg.audio_mode.split("_")
        codec = parts[0]
        bitrate = (parts[1] + "k") if len(parts) > 1 else "192k"
        cmd += ["-c:a", codec, "-b:a", bitrate]

    if cfg.output_path.lower().endswith(".mp4"):
        cmd += ["-movflags", "+faststart"]

    cmd.append(cfg.output_path)
    return cmd


# ── 进度解析 ─────────────────────────────────────────────────

_RE_TIME = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")
_RE_SPEED = re.compile(r"speed=\s*([\d.]+)x")


def parse_progress(line: str, total_dur: float) -> Optional[dict]:
    m = _RE_TIME.search(line)
    if not m:
        return None

    cur = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + float(f"0.{m[4]}")
    pct = min(cur / total_dur * 100, 100.0) if total_dur > 0 else 0.0

    spd = 0.0
    sm = _RE_SPEED.search(line)
    if sm:
        try:
            spd = float(sm[1])
        except ValueError:
            pass

    eta = (total_dur - cur) / spd if spd > 0 and total_dur > 0 else 0.0
    return {"percent": pct, "current": cur, "speed": spd, "eta": eta}


# ── 支持的格式 ───────────────────────────────────────────────

VIDEO_EXTS = (
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m2ts", ".mts", ".ts", ".m4v", ".mpg", ".mpeg", ".vob",
    ".3gp", ".ogv", ".rm", ".rmvb", ".asf", ".f4v",
)

VIDEO_FILTER = (
    "视频文件 (" + " ".join(f"*{e}" for e in VIDEO_EXTS) + ");;"
    "所有文件 (*)"
)

OUTPUT_FILTER = "MP4 (*.mp4);;MKV (*.mkv);;WebM (*.webm);;所有文件 (*)"
