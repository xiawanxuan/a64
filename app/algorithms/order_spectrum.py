import numpy as np
from scipy import signal, fft
from typing import Tuple, Dict, Any, Optional
from loguru import logger

from app.core.hyperparams import load_hyperparams
from app.core.exceptions import BusinessException
from app.core.error_codes import ErrorCode

hyperparams = load_hyperparams()


def _next_power_of_two(n: int) -> int:
    if n <= 0:
        return 1
    return 1 << (n - 1).bit_length()


def _get_window(name: str, n: int) -> np.ndarray:
    windows = {
        "hann": signal.windows.hann,
        "hamming": signal.windows.hamming,
        "blackman": signal.windows.blackman,
        "kaiser": lambda N: signal.windows.kaiser(N, beta=14),
        "flattop": signal.windows.flattop,
    }
    func = windows.get(name.lower(), signal.windows.hann)
    return func(n)


def _normalize_amplitude(
    spectrum: np.ndarray,
    method: str = "max"
) -> np.ndarray:
    if method == "none" or method is None:
        return spectrum
    if method == "max":
        mx = np.max(np.abs(spectrum))
        return spectrum / mx if mx > 0 else spectrum
    if method == "rms":
        rms = np.sqrt(np.mean(spectrum ** 2))
        return spectrum / rms if rms > 0 else spectrum
    if method == "energy":
        energy = np.sum(spectrum ** 2)
        return spectrum / np.sqrt(energy) if energy > 0 else spectrum
    return spectrum


def _interpolate_peak(
    order_axis: np.ndarray,
    spectrum: np.ndarray,
    peak_idx: int,
    method: str = "quadratic"
) -> Tuple[float, float]:
    if method == "none" or peak_idx <= 0 or peak_idx >= len(spectrum) - 1:
        return float(order_axis[peak_idx]), float(spectrum[peak_idx])

    if method == "quadratic":
        y1 = float(spectrum[peak_idx - 1])
        y2 = float(spectrum[peak_idx])
        y3 = float(spectrum[peak_idx + 1])
        denom = (y1 - 2 * y2 + y3)
        if abs(denom) < 1e-18:
            return float(order_axis[peak_idx]), y2
        d = 0.5 * (y1 - y3) / denom
        true_amp = y2 - 0.25 * (y1 - y3) * d
        d_order = order_axis[1] - order_axis[0] if len(order_axis) > 1 else 1.0
        true_order = float(order_axis[peak_idx]) + d * d_order
        return true_order, max(true_amp, 0.0)

    if method == "gaussian":
        eps = 1e-20
        y1 = max(float(spectrum[peak_idx - 1]), eps)
        y2 = max(float(spectrum[peak_idx]), eps)
        y3 = max(float(spectrum[peak_idx + 1]), eps)
        ly1, ly2, ly3 = np.log(y1), np.log(y2), np.log(y3)
        denom = (ly1 - 2 * ly2 + ly3)
        if abs(denom) < 1e-18:
            return float(order_axis[peak_idx]), float(spectrum[peak_idx])
        d = 0.5 * (ly1 - ly3) / denom
        log_true_amp = ly2 - 0.25 * (ly1 - ly3) * d
        true_amp = np.exp(log_true_amp)
        d_order = order_axis[1] - order_axis[0] if len(order_axis) > 1 else 1.0
        true_order = float(order_axis[peak_idx]) + d * d_order
        return true_order, float(true_amp)

    return float(order_axis[peak_idx]), float(spectrum[peak_idx])


def compute_order_spectrum(
    angular_signal: np.ndarray,
    samples_per_rev: float,
    max_order: Optional[float] = None,
    order_resolution: Optional[float] = None,
    cfg_override: Optional[Dict[str, Any]] = None
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    cfg = (hyperparams.spectrum or {}).copy()
    if cfg_override:
        cfg.update(cfg_override)

    if max_order is None:
        max_order = float(hyperparams.resampling.get("max_order", 100.0))
    if order_resolution is None:
        order_resolution = float(hyperparams.resampling.get("order_resolution", 0.01))

    window_type = cfg.get("window_type", "hann")
    overlap = float(cfg.get("window_overlap", 0.75))
    averaging = cfg.get("averaging_method", "rms")
    min_segments = int(cfg.get("min_segments", 4))
    max_segments = int(cfg.get("max_segments", 128))
    peak_interp = cfg.get("peak_interpolation", "quadratic")
    norm_method = cfg.get("amplitude_normalization", "max")

    N = len(angular_signal)
    if N < 64:
        raise BusinessException(
            ErrorCode.SPECTRUM_NO_DATA,
            f"角度域信号长度不足: {N}"
        )

    order_bw = samples_per_rev / 2.0 if samples_per_rev > 0 else 1.0
    target_order_bw = max_order * 2.0
    if order_bw < target_order_bw * 1.1:
        logger.warning(
            f"阶次带宽不足: samples_per_rev={samples_per_rev:.1f}, "
            f"有效BW={order_bw:.1f}, 目标={target_order_bw:.1f}"
        )

    perf_cfg = hyperparams.performance or {}
    fft_pad_power2 = perf_cfg.get("fft_pad_to_power_of_two", True)
    min_fft_len = int(perf_cfg.get("min_fft_length", 4096))
    max_fft_len = int(perf_cfg.get("max_fft_length", 1048576))

    base_nperseg = min_fft_len
    if N > 0:
        desired_res_nseg = int(order_bw / order_resolution) * 2
        if fft_pad_power2:
            base_nperseg = max(min_fft_len, _next_power_of_two(desired_res_nseg))
        else:
            base_nperseg = max(min_fft_len, desired_res_nseg)
    base_nperseg = min(base_nperseg, max_fft_len)

    if base_nperseg > N:
        base_nperseg = _next_power_of_two(N) if fft_pad_power2 else N

    noverlap = int(base_nperseg * overlap)
    num_segments = (N - noverlap) // (base_nperseg - noverlap) if base_nperseg > noverlap else 0

    if num_segments < min_segments and N > base_nperseg * 2:
        base_nperseg = max(
            min_fft_len,
            _next_power_of_two(int(N / (min_segments * (1 - overlap) + overlap)))
        ) if fft_pad_power2 else int(N / (min_segments * (1 - overlap) + overlap))
        base_nperseg = min(base_nperseg, max_fft_len)
        noverlap = int(base_nperseg * overlap)
        num_segments = (N - noverlap) // (base_nperseg - noverlap) if base_nperseg > noverlap else 0

    num_segments = min(num_segments, max_segments) if num_segments > 0 else 1

    try:
        window = _get_window(window_type, base_nperseg)
        window_energy = np.sum(window ** 2)

        f, t, Zxx = signal.stft(
            angular_signal,
            fs=samples_per_rev,
            window=window,
            nperseg=base_nperseg,
            noverlap=noverlap,
            nfft=base_nperseg,
            detrend=False,
            return_onesided=True,
            padded=True,
            scaling="psd" if cfg.get("compute_psd", True) else "spectrum"
        )
    except Exception as e:
        raise BusinessException(
            ErrorCode.SPECTRUM_FFT_ERROR,
            f"STFT计算失败: {e}",
            cause=e
        )

    if Zxx is None or Zxx.size == 0:
        raise BusinessException(ErrorCode.SPECTRUM_NO_DATA, "STFT输出为空")

    spectrum_seg = np.abs(Zxx)
    if averaging == "rms":
        spectrum = np.sqrt(np.mean(spectrum_seg ** 2, axis=-1))
    elif averaging == "linear":
        spectrum = np.mean(spectrum_seg, axis=-1)
    elif averaging == "peak_hold":
        spectrum = np.max(spectrum_seg, axis=-1)
    else:
        spectrum = np.sqrt(np.mean(spectrum_seg ** 2, axis=-1))

    order_axis = f

    if window_energy > 0:
        spectrum = spectrum * np.sqrt(1.0 / window_energy)

    order_mask = (order_axis >= 0) & (order_axis <= max_order)
    if not np.any(order_mask):
        raise BusinessException(ErrorCode.SPECTRUM_NO_DATA, "阶次轴过滤后无数据")

    order_axis_final = order_axis[order_mask]
    spectrum_final = spectrum[order_mask]

    if cfg.get("use_bandpass_filter", True):
        bp_low = cfg.get("bandpass_order_low", 0.5)
        bp_high = cfg.get("bandpass_order_high", max_order * 0.95)
        bp_mask = (order_axis_final >= bp_low) & (order_axis_final <= bp_high)
        if np.any(bp_mask):
            floor = np.percentile(spectrum_final[bp_mask], 5) if np.sum(bp_mask) > 10 else 0.0
            spectrum_final[~bp_mask] = floor * 0.1

    spectrum_final = _normalize_amplitude(spectrum_final, norm_method)
    spectrum_final = np.nan_to_num(spectrum_final, nan=0.0, posinf=0.0, neginf=0.0)

    actual_res = float(order_axis_final[1] - order_axis_final[0]) if len(order_axis_final) > 1 else order_resolution

    meta = {
        "nperseg": int(base_nperseg),
        "noverlap": int(noverlap),
        "num_segments": int(num_segments),
        "window": window_type,
        "averaging": averaging,
        "actual_resolution": actual_res,
        "max_order_analyzed": float(np.max(order_axis_final)),
        "fft_length": int(base_nperseg),
        "bandpass_enabled": bool(cfg.get("use_bandpass_filter", True)),
    }

    return order_axis_final, spectrum_final, meta


def find_spectral_peaks(
    order_axis: np.ndarray,
    spectrum: np.ndarray,
    prominence_ratio: float = 0.02,
    min_distance: float = 0.05,
    max_peaks: int = 100
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(order_axis) != len(spectrum) or len(order_axis) < 10:
        return np.array([]), np.array([]), np.array([])

    try:
        d_order = float(order_axis[1] - order_axis[0]) if len(order_axis) > 1 else 1.0
        min_dist_samples = max(1, int(min_distance / d_order))
        peak_height = float(np.max(spectrum)) * prominence_ratio

        peak_indices, props = signal.find_peaks(
            spectrum,
            height=peak_height,
            distance=min_dist_samples,
            prominence=peak_height * 0.3,
        )

        if len(peak_indices) == 0:
            return np.array([]), np.array([]), np.array([])

        peak_orders = []
        peak_amplitudes = []
        for idx in peak_indices:
            true_order, true_amp = _interpolate_peak(
                order_axis, spectrum, int(idx), method="quadratic"
            )
            peak_orders.append(true_order)
            peak_amplitudes.append(true_amp)

        peak_orders = np.array(peak_orders, dtype=float)
        peak_amplitudes = np.array(peak_amplitudes, dtype=float)
        sorted_idx = np.argsort(-peak_amplitudes)
        if len(sorted_idx) > max_peaks:
            sorted_idx = sorted_idx[:max_peaks]

        return peak_orders[sorted_idx], peak_amplitudes[sorted_idx], peak_indices[sorted_idx]

    except Exception as e:
        logger.warning(f"谱峰搜索失败: {e}")
        return np.array([]), np.array([]), np.array([])
