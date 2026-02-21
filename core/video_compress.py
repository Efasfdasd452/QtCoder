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
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

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
    def resolution_tier_str(self) -> str:
        """根据短边或高度返回规格：4K / 2K / 1080p / 720p / 480p / 360p / 其他"""
        h = self.height or 0
        w = self.width or 0
        if h <= 0 and w <= 0:
            return "未知"
        # 竖屏以宽为短边，横屏以高为短边
        short = min(w, h) if (w and h) else (h or w)
        if short >= 2160:
            return "4K"
        if short >= 1440:
            return "2K"
        if short >= 1080:
            return "1080p"
        if short >= 720:
            return "720p"
        if short >= 480:
            return "480p"
        if short >= 360:
            return "360p"
        if short >= 240:
            return "240p"
        if short > 0:
            return "其他"
        return "未知"

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

# 输出帧率：0=保持源帧率；48=折中（流畅与体积平衡）；30/24=更小体积
OUTPUT_FPS_OPTS = [
    (0.0,  "保持原始"),
    (48.0, "48 fps（折中：比60小、比30顺）"),
    (30.0, "30 fps（体积更小）"),
    (24.0, "24 fps（更小）"),
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


# ── 软件编码器 → 硬件编码器自动映射 ─────────────────────────

_HW_ENCODER_MAP = {
    "libx264": ["h264_nvenc", "h264_qsv", "h264_amf"],
    "libx265": ["hevc_nvenc", "hevc_qsv", "hevc_amf"],
}


def auto_select_encoder(sw_codec: str, available_hw: list) -> str:
    """若有可用硬件编码器则自动替换，优先级 NVENC > QSV > AMF。
    available_hw: [(codec_name, display_name), ...]
    """
    hw_names = {c for c, _ in available_hw}
    for candidate in _HW_ENCODER_MAP.get(sw_codec, []):
        if candidate in hw_names:
            return candidate
    return sw_codec


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
    input_fps: float = 0.0     # 源视频帧率（用于 -r 当 output_fps=0）
    output_fps: float = 0.0    # 0=保持源帧率，>0=强制该帧率（如 30 可显著减小体积）

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

    # 要降帧时必须在输入端加 -r，否则解码仍按源帧率喂给编码器，体积不会变小
    r_out = cfg.output_fps if cfg.output_fps > 0 else cfg.input_fps
    cmd = [ff, "-y", "-hide_banner"]
    if r_out > 0 and cfg.output_fps > 0:
        cmd += ["-r", str(round(r_out, 3))]
    cmd += ["-i", cfg.input_path]

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
        # NVENC 的 CQ 与 x265 CRF 标度不同：CQ 18 与 20 体积差异常很小，属硬件编码器特性
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
        cmd += ["-vf", f"scale={cfg.target_width}:-2:flags=lanczos,setsar=1"]

    # 输出端也标上帧率（降帧时已在输入端用 -r 限流，这里保证 muxer 一致）
    if r_out > 0:
        cmd += ["-r", str(round(r_out, 3))]

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


# ── 支持的格式（主流视频格式，用于单文件与批量）────────────────

VIDEO_EXTS = (
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".m2ts", ".mts", ".ts", ".m4v", ".mpg", ".mpeg", ".vob",
    ".3gp", ".ogv", ".rm", ".rmvb", ".asf", ".f4v",
)


def _ext_is_video(name: str) -> bool:
    return name.lower().endswith(VIDEO_EXTS)


def collect_videos_from_folder(
    folder: str, recursive: bool = True
) -> List[str]:
    """从文件夹收集所有视频文件路径；recursive=True 时包含子文件夹。"""
    if not os.path.isdir(folder):
        return []
    out = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for f in files:
                if _ext_is_video(f):
                    out.append(os.path.normpath(os.path.join(root, f)))
    else:
        for f in os.listdir(folder):
            path = os.path.join(folder, f)
            if os.path.isfile(path) and _ext_is_video(f):
                out.append(os.path.normpath(path))
    return sorted(out)


# 各预设下预估压缩后约为原大小的比例（经验值，用于批量预估）
PRESET_ESTIMATE_RATIO = {
    "compat": 0.65,
    "balanced": 0.45,
    "max_compress": 0.35,
    "custom": 0.45,   # 仅当未传自定义参数时的回退
}


def get_custom_estimate_ratio(crf: int, output_fps: float) -> float:
    """根据自定义 CRF 与输出帧率估算压缩比。output_fps=0 表示保持源帧率。"""
    # CRF 经验比例（H.265 大致范围）
    if crf <= 18:
        base = 0.55
    elif crf <= 23:
        base = 0.55 - (crf - 18) * 0.04
    elif crf <= 30:
        base = 0.35 - (crf - 23) * 0.02
    else:
        base = 0.22
    # 输出帧率：若指定则按 60fps 源折算（30→0.5, 48→0.8）
    if output_fps and output_fps > 0:
        base *= (output_fps / 60.0)
    return max(0.15, min(0.9, base))


def estimate_one_file_size(size_bytes: int, preset_key: str) -> int:
    """单文件按预设估算压缩后字节数。"""
    ratio = PRESET_ESTIMATE_RATIO.get(preset_key, 0.45)
    return int(size_bytes * ratio)


def estimate_one_file_size_custom(
    size_bytes: int, crf: int, output_fps: float = 0.0
) -> int:
    """单文件按自定义 CRF、输出帧率估算压缩后字节数。"""
    ratio = get_custom_estimate_ratio(crf, output_fps)
    return int(size_bytes * ratio)


def estimate_compressed_size(
    file_paths_with_size: List[Tuple[str, int]],
    preset_key: str,
) -> int:
    """根据预设估算压缩后总字节数。file_paths_with_size: [(path, size_bytes), ...]"""
    return sum(
        estimate_one_file_size(size, preset_key)
        for _, size in file_paths_with_size
    )


def estimate_compressed_size_custom(
    file_paths_with_size: List[Tuple[str, int]],
    crf: int,
    output_fps: float = 0.0,
) -> int:
    """根据自定义 CRF、输出帧率估算压缩后总字节数。"""
    return sum(
        estimate_one_file_size_custom(size, crf, output_fps)
        for _, size in file_paths_with_size
    )


def get_disk_free_bytes(path: str) -> int:
    """返回 path 所在磁盘的可用空间（字节）。"""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        path = os.path.dirname(path)
    if not path or not os.path.exists(path):
        return 0
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0

VIDEO_FILTER = (
    "视频文件 (" + " ".join(f"*{e}" for e in VIDEO_EXTS) + ");;"
    "所有文件 (*)"
)

OUTPUT_FILTER = "MP4 (*.mp4);;MKV (*.mkv);;WebM (*.webm);;所有文件 (*)"
