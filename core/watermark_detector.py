# -*- coding: utf-8 -*-
"""隐藏水印检测核心模块

支持多种隐写/水印检测技术：
- 频域分析 (FFT / DCT)
- 位平面分解 (Bit Plane)
- 颜色通道分离
- 直方图均衡化增强
- 边缘检测 (Laplacian / Sobel)
- 高通滤波
- 小波变换 (DWT)
- Gamma 校正
- 色差分析
- 奇异值分解 (SVD)
- blind_watermark 频域盲水印嵌入/提取
"""

import os
import tempfile
import numpy as np
import cv2
from blind_watermark import WaterMark


# ═══════════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════════

def _strip_alpha(img: np.ndarray) -> np.ndarray:
    """BGRA → BGR，其余原样返回"""
    if len(img.shape) == 3 and img.shape[2] == 4:
        return img[:, :, :3].copy()
    return img


def _to_gray(img: np.ndarray) -> np.ndarray:
    if len(img.shape) == 2:
        return img
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _normalize_u8(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype(np.float64)
    mn, mx = arr.min(), arr.max()
    if mx - mn < 1e-8:
        return np.zeros_like(arr, dtype=np.uint8)
    return ((arr - mn) / (mx - mn) * 255).astype(np.uint8)


def _to_bgr(gray: np.ndarray) -> np.ndarray:
    if len(gray.shape) == 2:
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    if gray.shape[2] == 4:
        return gray[:, :, :3].copy()
    return gray


# ═══════════════════════════════════════════════════════════════
#  FFT 频域分析
# ═══════════════════════════════════════════════════════════════

def detect_fft(img: np.ndarray) -> np.ndarray:
    """FFT 幅度谱 — 揭示频域嵌入的水印模式"""
    gray = _to_gray(img)
    f = np.fft.fft2(gray.astype(np.float64))
    fshift = np.fft.fftshift(f)
    magnitude = np.log1p(np.abs(fshift))
    return _to_bgr(_normalize_u8(magnitude))


def detect_fft_phase(img: np.ndarray) -> np.ndarray:
    """FFT 相位谱 — 某些水印嵌入在相位信息中"""
    gray = _to_gray(img)
    f = np.fft.fft2(gray.astype(np.float64))
    fshift = np.fft.fftshift(f)
    phase = np.angle(fshift)
    return _to_bgr(_normalize_u8(phase))


# ═══════════════════════════════════════════════════════════════
#  DCT 分析
# ═══════════════════════════════════════════════════════════════

def detect_dct(img: np.ndarray) -> np.ndarray:
    """DCT 频谱 — JPEG 水印常使用 DCT 域"""
    gray = _to_gray(img).astype(np.float64)
    h, w = gray.shape
    h = h - h % 2
    w = w - w % 2
    gray = gray[:h, :w]
    dct = cv2.dct(gray)
    magnitude = np.log1p(np.abs(dct))
    return _to_bgr(_normalize_u8(magnitude))


# ═══════════════════════════════════════════════════════════════
#  位平面分解 (Bit Plane)
# ═══════════════════════════════════════════════════════════════

def detect_bit_plane(img: np.ndarray, bit: int = 0) -> np.ndarray:
    """提取指定位平面 (bit 0=LSB, 7=MSB)"""
    gray = _to_gray(img)
    plane = ((gray >> bit) & 1) * 255
    return _to_bgr(plane.astype(np.uint8))


def detect_bit_planes_all(img: np.ndarray) -> list:
    """返回所有 8 个位平面 [(label, image), ...]"""
    results = []
    for b in range(8):
        label = f"位平面 {b} ({'LSB' if b == 0 else 'MSB' if b == 7 else f'Bit {b}'})"
        results.append((label, detect_bit_plane(img, b)))
    return results


# ═══════════════════════════════════════════════════════════════
#  颜色通道分离
# ═══════════════════════════════════════════════════════════════

def detect_channels(img: np.ndarray) -> list:
    """分离 R/G/B 通道"""
    if len(img.shape) == 2:
        return [("灰度通道", _to_bgr(img))]
    b, g, r = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    results = [
        ("红色通道 (R)", _to_bgr(r)),
        ("绿色通道 (G)", _to_bgr(g)),
        ("蓝色通道 (B)", _to_bgr(b)),
    ]
    if img.shape[2] == 4:
        results.append(("Alpha 通道", _to_bgr(img[:, :, 3])))
    return results


# ═══════════════════════════════════════════════════════════════
#  直方图均衡化
# ═══════════════════════════════════════════════════════════════

def detect_histogram_eq(img: np.ndarray) -> np.ndarray:
    """全局直方图均衡化 — 增强低对比度隐藏内容"""
    gray = _to_gray(img)
    eq = cv2.equalizeHist(gray)
    return _to_bgr(eq)


def detect_clahe(img: np.ndarray) -> np.ndarray:
    """CLAHE 自适应直方图均衡化 — 局部增强"""
    gray = _to_gray(img)
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
    result = clahe.apply(gray)
    return _to_bgr(result)


# ═══════════════════════════════════════════════════════════════
#  边缘检测
# ═══════════════════════════════════════════════════════════════

def detect_laplacian(img: np.ndarray) -> np.ndarray:
    """Laplacian 边缘检测 — 检测图像中突变"""
    gray = _to_gray(img)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return _to_bgr(_normalize_u8(np.abs(lap)))


def detect_sobel(img: np.ndarray) -> np.ndarray:
    """Sobel 边缘检测 (梯度幅值)"""
    gray = _to_gray(img)
    sx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(sx ** 2 + sy ** 2)
    return _to_bgr(_normalize_u8(mag))


# ═══════════════════════════════════════════════════════════════
#  高通滤波 (原图 - 模糊 = 高频细节)
# ═══════════════════════════════════════════════════════════════

def detect_highpass(img: np.ndarray) -> np.ndarray:
    """高通滤波 — 提取高频成分 (可能包含水印)"""
    gray = _to_gray(img).astype(np.float64)
    blurred = cv2.GaussianBlur(gray, (21, 21), 0).astype(np.float64)
    highpass = gray - blurred
    enhanced = _normalize_u8(highpass)
    return _to_bgr(enhanced)


# ═══════════════════════════════════════════════════════════════
#  小波变换 (DWT)
# ═══════════════════════════════════════════════════════════════

def detect_wavelet(img: np.ndarray) -> list:
    """Haar 小波变换 — 分解为 LL/LH/HL/HH 子带"""
    try:
        import pywt
    except ImportError:
        gray = _to_gray(img)
        return [("小波变换 (需安装 PyWavelets)", _to_bgr(gray))]

    gray = _to_gray(img).astype(np.float64)
    coeffs = pywt.dwt2(gray, 'haar')
    cA, (cH, cV, cD) = coeffs
    labels = [
        ("小波 LL (近似)", cA),
        ("小波 LH (水平细节)", cH),
        ("小波 HL (垂直细节)", cV),
        ("小波 HH (对角细节)", cD),
    ]
    return [(lbl, _to_bgr(_normalize_u8(c))) for lbl, c in labels]


# ═══════════════════════════════════════════════════════════════
#  Gamma 校正
# ═══════════════════════════════════════════════════════════════

def detect_gamma(img: np.ndarray, gamma: float = 0.25) -> np.ndarray:
    """Gamma 校正 — 低 gamma 值提亮暗部隐藏信息"""
    table = np.array(
        [((i / 255.0) ** gamma) * 255 for i in range(256)]
    ).astype(np.uint8)
    src = _strip_alpha(img) if len(img.shape) == 3 else _to_bgr(img)
    return cv2.LUT(src, table)


def detect_gamma_set(img: np.ndarray) -> list:
    """多种 Gamma 值检测"""
    gammas = [0.1, 0.25, 0.5, 2.0, 4.0]
    return [
        (f"Gamma γ={g}", detect_gamma(img, g))
        for g in gammas
    ]


# ═══════════════════════════════════════════════════════════════
#  色差分析
# ═══════════════════════════════════════════════════════════════

def detect_color_diff(img: np.ndarray) -> list:
    """通道间差异 — 水印可能只存在于特定通道"""
    if len(img.shape) == 2:
        return [("色差分析 (需要彩色图)", _to_bgr(img))]
    b = img[:, :, 0].astype(np.float64)
    g = img[:, :, 1].astype(np.float64)
    r = img[:, :, 2].astype(np.float64)
    return [
        ("色差 |R-G|", _to_bgr(_normalize_u8(np.abs(r - g)))),
        ("色差 |R-B|", _to_bgr(_normalize_u8(np.abs(r - b)))),
        ("色差 |G-B|", _to_bgr(_normalize_u8(np.abs(g - b)))),
    ]


# ═══════════════════════════════════════════════════════════════
#  奇异值分解 (SVD) 残差
# ═══════════════════════════════════════════════════════════════

def detect_svd_residual(img: np.ndarray, keep: int = 10) -> np.ndarray:
    """SVD 低秩近似残差 — 保留前 k 个奇异值后的残差可能含水印"""
    gray = _to_gray(img).astype(np.float64)
    U, S, Vt = np.linalg.svd(gray, full_matrices=False)
    S_trunc = S.copy()
    S_trunc[:keep] = 0
    residual = U @ np.diag(S_trunc) @ Vt
    return _to_bgr(_normalize_u8(residual))


# ═══════════════════════════════════════════════════════════════
#  颜色空间转换增强
# ═══════════════════════════════════════════════════════════════

def detect_hsv_channels(img: np.ndarray) -> list:
    """HSV 空间分离 — 某些水印在饱和度/明度通道更明显"""
    if len(img.shape) == 2:
        return [("HSV 分析 (需要彩色图)", _to_bgr(img))]
    bgr = _strip_alpha(img)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    return [
        ("HSV - 色相 (H)", _to_bgr(_normalize_u8(h.astype(np.float64)))),
        ("HSV - 饱和度 (S)", _to_bgr(s)),
        ("HSV - 明度 (V)", _to_bgr(v)),
    ]


# ═══════════════════════════════════════════════════════════════
#  反色
# ═══════════════════════════════════════════════════════════════

def detect_invert(img: np.ndarray) -> np.ndarray:
    """反色 — 255 减去每个像素值"""
    src = _strip_alpha(img) if len(img.shape) == 3 else _to_bgr(img)
    return cv2.bitwise_not(src)


# ═══════════════════════════════════════════════════════════════
#  Gray Bits — 灰度值按位可视化
# ═══════════════════════════════════════════════════════════════

def detect_gray_bits(img: np.ndarray) -> np.ndarray:
    """Gray Bits — 将灰度值各位用随机颜色映射增强"""
    gray = _to_gray(img)
    h, w = gray.shape
    out = np.zeros((h, w, 3), dtype=np.uint8)
    for bit in range(8):
        plane = ((gray >> bit) & 1).astype(np.uint8)
        weight = 1 << bit
        out[:, :, 0] += plane * ((weight * 29) % 256)
        out[:, :, 1] += plane * ((weight * 43) % 256)
        out[:, :, 2] += plane * ((weight * 61) % 256)
    return out


# ═══════════════════════════════════════════════════════════════
#  Random Color Map — 随机颜色映射
# ═══════════════════════════════════════════════════════════════

def detect_random_colormap(img: np.ndarray, seed: int = 42) -> np.ndarray:
    """将灰度值通过随机颜色映射表着色，揭示微小值差异"""
    rng = np.random.RandomState(seed)
    lut = rng.randint(0, 256, (256, 3), dtype=np.uint8)
    gray = _to_gray(img)
    h, w = gray.shape
    out = lut[gray.ravel()].reshape(h, w, 3)
    return out


# ═══════════════════════════════════════════════════════════════
#  Full Channel — 单通道满色显示
# ═══════════════════════════════════════════════════════════════

def _get_alpha(img: np.ndarray) -> np.ndarray:
    """获取 Alpha 通道，如果没有则返回全 255"""
    if len(img.shape) == 3 and img.shape[2] == 4:
        return img[:, :, 3]
    return np.full(img.shape[:2], 255, dtype=np.uint8)


def _get_bgra(img: np.ndarray):
    """拆分 B, G, R, A 四个通道"""
    if len(img.shape) == 2:
        g = img
        return g, g, g, np.full_like(g, 255)
    if img.shape[2] == 4:
        return img[:, :, 0], img[:, :, 1], img[:, :, 2], img[:, :, 3]
    b, g, r = cv2.split(img)
    return b, g, r, np.full_like(b, 255)


def detect_full_red(img: np.ndarray) -> np.ndarray:
    """Full Red — 仅红色通道，映射为红色"""
    _, _, r, _ = _get_bgra(img)
    z = np.zeros_like(r)
    return np.dstack([z, z, r])


def detect_full_green(img: np.ndarray) -> np.ndarray:
    """Full Green — 仅绿色通道，映射为绿色"""
    _, g, _, _ = _get_bgra(img)
    z = np.zeros_like(g)
    return np.dstack([z, g, z])


def detect_full_blue(img: np.ndarray) -> np.ndarray:
    """Full Blue — 仅蓝色通道，映射为蓝色"""
    b, _, _, _ = _get_bgra(img)
    z = np.zeros_like(b)
    return np.dstack([b, z, z])


def detect_full_alpha(img: np.ndarray) -> np.ndarray:
    """Full Alpha — Alpha 通道灰度显示"""
    a = _get_alpha(img)
    return _to_bgr(a)


# ═══════════════════════════════════════════════════════════════
#  单通道位平面 — R/G/B/A Plane N
# ═══════════════════════════════════════════════════════════════

def detect_channel_plane(img: np.ndarray, channel: str, bit: int) -> np.ndarray:
    """提取指定通道的指定位平面 (channel='r'/'g'/'b'/'a', bit=0..7)"""
    b_ch, g_ch, r_ch, a_ch = _get_bgra(img)
    ch_map = {'r': r_ch, 'g': g_ch, 'b': b_ch, 'a': a_ch}
    ch = ch_map[channel]
    plane = ((ch >> bit) & 1) * 255
    return _to_bgr(plane.astype(np.uint8))


def detect_color_planes(img: np.ndarray) -> list:
    """全部 R/G/B/A Plane 0-7"""
    results = []
    has_alpha = len(img.shape) == 3 and img.shape[2] == 4
    for ch_name, ch_label in [('r', 'Red'), ('g', 'Green'), ('b', 'Blue')]:
        for bit in range(8):
            results.append(
                (f"{ch_label} Plane {bit}", detect_channel_plane(img, ch_name, bit)))
    if has_alpha:
        for bit in range(8):
            results.append(
                (f"Alpha Plane {bit}", detect_channel_plane(img, 'a', bit)))
    return results


# ═══════════════════════════════════════════════════════════════
#  综合检测入口
# ═══════════════════════════════════════════════════════════════

DETECT_METHODS = {
    "FFT 幅度谱":         ("fft_mag",       "频域水印检测，显示傅里叶幅度谱"),
    "FFT 相位谱":         ("fft_phase",     "频域相位信息分析"),
    "DCT 频谱":           ("dct",           "离散余弦变换，JPEG 水印检测"),
    "反色":               ("invert",        "图像反色 (255 - pixel)"),
    "Gray Bits":          ("gray_bits",     "灰度位混合可视化"),
    "Random Color Map 1": ("rcmap1",        "随机颜色映射 (Seed 42)，揭示微小值差异"),
    "Random Color Map 2": ("rcmap2",        "随机颜色映射 (Seed 97)，不同配色方案"),
    "Full Red":           ("full_r",        "仅显示红色通道 (红色着色)"),
    "Full Green":         ("full_g",        "仅显示绿色通道 (绿色着色)"),
    "Full Blue":          ("full_b",        "仅显示蓝色通道 (蓝色着色)"),
    "Full Alpha":         ("full_a",        "Alpha 通道灰度显示"),
    "Red Plane 0":        ("rp0",           "红色通道 Bit 0 (LSB)"),
    "Red Plane 1":        ("rp1",           "红色通道 Bit 1"),
    "Red Plane 2":        ("rp2",           "红色通道 Bit 2"),
    "Green Plane 0":      ("gp0",           "绿色通道 Bit 0 (LSB)"),
    "Green Plane 1":      ("gp1",           "绿色通道 Bit 1"),
    "Green Plane 2":      ("gp2",           "绿色通道 Bit 2"),
    "Blue Plane 0":       ("bp0",           "蓝色通道 Bit 0 (LSB)"),
    "Blue Plane 1":       ("bp1",           "蓝色通道 Bit 1"),
    "Blue Plane 2":       ("bp2",           "蓝色通道 Bit 2"),
    "Alpha Plane 0":      ("ap0",           "Alpha 通道 Bit 0 (LSB)"),
    "Alpha Plane 1":      ("ap1",           "Alpha 通道 Bit 1"),
    "Alpha Plane 2":      ("ap2",           "Alpha 通道 Bit 2"),
    "位平面 (LSB)":       ("bit_lsb",       "灰度最低有效位，LSB 隐写检测"),
    "位平面 (全部)":      ("bit_all",       "灰度所有 8 个位平面分解"),
    "颜色通道":           ("channels",      "R/G/B 通道分离灰度显示"),
    "直方图均衡化":       ("hist_eq",       "全局直方图均衡化增强"),
    "CLAHE 增强":         ("clahe",         "自适应局部直方图均衡化"),
    "Laplacian 边缘":     ("laplacian",     "拉普拉斯边缘检测"),
    "Sobel 边缘":         ("sobel",         "Sobel 梯度幅值"),
    "高通滤波":           ("highpass",      "提取高频成分"),
    "小波变换":           ("wavelet",       "Haar 小波多分辨率分解"),
    "Gamma 校正":         ("gamma",         "多种 Gamma 值增强"),
    "色差分析":           ("color_diff",    "通道间差异分析"),
    "SVD 残差":           ("svd",           "奇异值分解低秩残差"),
    "HSV 通道":           ("hsv",           "HSV 颜色空间分析"),
    "通道位平面 (全部)":  ("all_ch_planes", "R/G/B/A 各通道 Bit 0-7 全部分解"),
}

# code → 处理函数映射，使 run_detection 简洁
_DISPATCH = {
    "fft_mag":       lambda img: [("FFT 幅度谱", detect_fft(img))],
    "fft_phase":     lambda img: [("FFT 相位谱", detect_fft_phase(img))],
    "dct":           lambda img: [("DCT 频谱", detect_dct(img))],
    "invert":        lambda img: [("反色", detect_invert(img))],
    "gray_bits":     lambda img: [("Gray Bits", detect_gray_bits(img))],
    "rcmap1":        lambda img: [("Random Color Map 1", detect_random_colormap(img, 42))],
    "rcmap2":        lambda img: [("Random Color Map 2", detect_random_colormap(img, 97))],
    "full_r":        lambda img: [("Full Red", detect_full_red(img))],
    "full_g":        lambda img: [("Full Green", detect_full_green(img))],
    "full_b":        lambda img: [("Full Blue", detect_full_blue(img))],
    "full_a":        lambda img: [("Full Alpha", detect_full_alpha(img))],
    "rp0":           lambda img: [("Red Plane 0", detect_channel_plane(img, 'r', 0))],
    "rp1":           lambda img: [("Red Plane 1", detect_channel_plane(img, 'r', 1))],
    "rp2":           lambda img: [("Red Plane 2", detect_channel_plane(img, 'r', 2))],
    "gp0":           lambda img: [("Green Plane 0", detect_channel_plane(img, 'g', 0))],
    "gp1":           lambda img: [("Green Plane 1", detect_channel_plane(img, 'g', 1))],
    "gp2":           lambda img: [("Green Plane 2", detect_channel_plane(img, 'g', 2))],
    "bp0":           lambda img: [("Blue Plane 0", detect_channel_plane(img, 'b', 0))],
    "bp1":           lambda img: [("Blue Plane 1", detect_channel_plane(img, 'b', 1))],
    "bp2":           lambda img: [("Blue Plane 2", detect_channel_plane(img, 'b', 2))],
    "ap0":           lambda img: [("Alpha Plane 0", detect_channel_plane(img, 'a', 0))],
    "ap1":           lambda img: [("Alpha Plane 1", detect_channel_plane(img, 'a', 1))],
    "ap2":           lambda img: [("Alpha Plane 2", detect_channel_plane(img, 'a', 2))],
    "bit_lsb":       lambda img: [("位平面 0 (LSB)", detect_bit_plane(img, 0))],
    "bit_all":       lambda img: detect_bit_planes_all(img),
    "channels":      lambda img: detect_channels(img),
    "hist_eq":       lambda img: [("直方图均衡化", detect_histogram_eq(img))],
    "clahe":         lambda img: [("CLAHE 增强", detect_clahe(img))],
    "laplacian":     lambda img: [("Laplacian 边缘", detect_laplacian(img))],
    "sobel":         lambda img: [("Sobel 边缘", detect_sobel(img))],
    "highpass":      lambda img: [("高通滤波", detect_highpass(img))],
    "wavelet":       lambda img: detect_wavelet(img),
    "gamma":         lambda img: detect_gamma_set(img),
    "color_diff":    lambda img: detect_color_diff(img),
    "svd":           lambda img: [("SVD 残差 (k=10)", detect_svd_residual(img, 10))],
    "hsv":           lambda img: detect_hsv_channels(img),
    "all_ch_planes": lambda img: detect_color_planes(img),
}


def run_detection(img: np.ndarray, method_key: str) -> list:
    """执行指定检测方法，返回 [(标签, BGR图像), ...]"""
    code = DETECT_METHODS[method_key][0]
    handler = _DISPATCH.get(code)
    if handler:
        return handler(img)
    return []


def run_all_quick(img: np.ndarray) -> list:
    """快速全面检测 — 每种方法的代表性结果"""
    results = []
    results.append(("FFT 幅度谱", detect_fft(img)))
    results.append(("FFT 相位谱", detect_fft_phase(img)))
    results.append(("DCT 频谱", detect_dct(img)))
    results.append(("反色", detect_invert(img)))
    results.append(("Gray Bits", detect_gray_bits(img)))
    results.append(("Random Color Map 1", detect_random_colormap(img, 42)))
    results.append(("Random Color Map 2", detect_random_colormap(img, 97)))
    results.append(("Full Red", detect_full_red(img)))
    results.append(("Full Green", detect_full_green(img)))
    results.append(("Full Blue", detect_full_blue(img)))
    results.append(("Full Alpha", detect_full_alpha(img)))
    results.append(("Red Plane 0", detect_channel_plane(img, 'r', 0)))
    results.append(("Green Plane 0", detect_channel_plane(img, 'g', 0)))
    results.append(("Blue Plane 0", detect_channel_plane(img, 'b', 0)))
    results.append(("位平面 0 (LSB)", detect_bit_plane(img, 0)))
    results.append(("位平面 1", detect_bit_plane(img, 1)))
    results += detect_channels(img)
    results.append(("直方图均衡化", detect_histogram_eq(img)))
    results.append(("CLAHE 增强", detect_clahe(img)))
    results.append(("Laplacian 边缘", detect_laplacian(img)))
    results.append(("高通滤波", detect_highpass(img)))
    results += detect_wavelet(img)
    results.append(("Gamma γ=0.25", detect_gamma(img, 0.25)))
    results += detect_color_diff(img)
    results.append(("SVD 残差", detect_svd_residual(img, 10)))
    return results


# ═══════════════════════════════════════════════════════════════
#  blind_watermark 频域盲水印
# ═══════════════════════════════════════════════════════════════

def _tmp_path(suffix=".png"):
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return path


def _safe_copy(src_path: str) -> str:
    """将文件复制到纯 ASCII 临时路径，解决 cv2.imread 不支持中文路径的问题"""
    ext = os.path.splitext(src_path)[1] or ".png"
    tmp = _tmp_path(ext)
    import shutil
    shutil.copy2(src_path, tmp)
    return tmp


def bwm_embed_text(img_path: str, text: str,
                   pwd_img: int = 1, pwd_wm: int = 1) -> tuple:
    """嵌入文字盲水印，返回 (输出图路径, wm_bit长度)"""
    safe_img = _safe_copy(img_path)
    try:
        bwm = WaterMark(password_img=pwd_img, password_wm=pwd_wm)
        bwm.read_img(safe_img)
        bwm.read_wm(text, mode='str')
        out = _tmp_path(".png")
        bwm.embed(out)
        wm_len = len(bwm.wm_bit)
        return out, wm_len
    finally:
        os.remove(safe_img)


def bwm_extract_text(img_path: str, wm_len: int,
                     pwd_img: int = 1, pwd_wm: int = 1) -> str:
    """从图片中提取文字盲水印"""
    safe_img = _safe_copy(img_path)
    try:
        bwm = WaterMark(password_img=pwd_img, password_wm=pwd_wm)
        return bwm.extract(safe_img, wm_shape=wm_len, mode='str')
    finally:
        os.remove(safe_img)


def bwm_embed_image(img_path: str, wm_path: str,
                    pwd_img: int = 1, pwd_wm: int = 1) -> str:
    """嵌入图片盲水印，返回输出图路径"""
    safe_img = _safe_copy(img_path)
    safe_wm = _safe_copy(wm_path)
    try:
        bwm = WaterMark(password_img=pwd_img, password_wm=pwd_wm)
        bwm.read_img(safe_img)
        bwm.read_wm(safe_wm)
        out = _tmp_path(".png")
        bwm.embed(out)
        return out
    finally:
        os.remove(safe_img)
        os.remove(safe_wm)


def bwm_extract_image(img_path: str, wm_shape: tuple,
                      pwd_img: int = 1, pwd_wm: int = 1) -> str:
    """从图片中提取图片盲水印，返回水印图路径"""
    safe_img = _safe_copy(img_path)
    try:
        bwm = WaterMark(password_img=pwd_img, password_wm=pwd_wm)
        out = _tmp_path(".png")
        bwm.extract(filename=safe_img, wm_shape=wm_shape, out_wm_name=out)
        return out
    finally:
        os.remove(safe_img)
