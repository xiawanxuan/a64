import numpy as np
from scipy import signal
from typing import Tuple, Optional
from loguru import logger

from app.core.hyperparams import load_hyperparams

hyperparams = load_hyperparams()


def detrend_signal(signal_data: np.ndarray, method: str = "linear") -> np.ndarray:
    if method == "mean":
        return signal_data - np.mean(signal_data)
    elif method == "linear":
        return signal.detrend(signal_data, type="linear")
    elif method == "constant":
        return signal.detrend(signal_data, type="constant")
    return signal_data


def remove_outliers(signal_data: np.ndarray, method: str = "median_filter",
                    kernel_size: int = 5, sigma: float = 10.0) -> np.ndarray:
    if method == "none":
        return signal_data

    if method == "median_filter":
        if kernel_size % 2 == 0:
            kernel_size += 1
        filtered = signal.medfilt(signal_data, kernel_size=kernel_size)
        residual = signal_data - filtered
        std = np.std(residual)
        if std > 0:
            mask = np.abs(residual) > sigma * std
            signal_data = signal_data.copy()
            signal_data[mask] = filtered[mask]
        return signal_data

    if method == "clip":
        mean = np.mean(signal_data)
        std = np.std(signal_data)
        if std > 0:
            lower = mean - sigma * std
            upper = mean + sigma * std
            return np.clip(signal_data, lower, upper)
        return signal_data

    return signal_data


def highpass_filter(signal_data: np.ndarray, fs: float, cutoff_hz: float = 0.5,
                    order: int = 4) -> np.ndarray:
    if cutoff_hz <= 0 or fs <= 0:
        return signal_data
    nyq = 0.5 * fs
    norm_cutoff = cutoff_hz / nyq
    if norm_cutoff >= 1.0:
        return signal_data
    b, a = signal.butter(order, norm_cutoff, btype="high", output="ba")
    return signal.filtfilt(b, a, signal_data)


def lowpass_filter(signal_data: np.ndarray, fs: float, cutoff_hz: float,
                   order: int = 4) -> np.ndarray:
    if cutoff_hz <= 0 or fs <= 0:
        return signal_data
    nyq = 0.5 * fs
    norm_cutoff = cutoff_hz / nyq
    if norm_cutoff >= 1.0:
        return signal_data
    b, a = signal.butter(order, norm_cutoff, btype="low", output="ba")
    return signal.filtfilt(b, a, signal_data)


def bandpass_filter(signal_data: np.ndarray, fs: float,
                    low_hz: float, high_hz: float, order: int = 4) -> np.ndarray:
    if fs <= 0 or low_hz >= high_hz:
        return signal_data
    nyq = 0.5 * fs
    low = low_hz / nyq
    high = high_hz / nyq
    if high >= 1.0:
        high = 0.99
    if low <= 0:
        low = 0.0001
    b, a = signal.butter(order, [low, high], btype="band", output="ba")
    return signal.filtfilt(b, a, signal_data)


def notch_filter(signal_data: np.ndarray, fs: float,
                 notch_freqs: np.ndarray, q: float = 30.0) -> np.ndarray:
    if len(notch_freqs) == 0 or fs <= 0:
        return signal_data

    result = signal_data.copy()
    for freq in notch_freqs:
        if freq <= 0 or freq >= fs / 2:
            continue
        b, a = signal.iirnotch(freq, q, fs)
        result = signal.filtfilt(b, a, result)
    return result


def smooth_speed(speed_data: np.ndarray, window_size: int = 50) -> np.ndarray:
    if window_size <= 1 or len(speed_data) < window_size:
        return speed_data
    if window_size % 2 == 0:
        window_size += 1
    return signal.savgol_filter(speed_data, window_size, 3)


def remove_speed_outliers(speed_data: np.ndarray, zscore_threshold: float = 3.0) -> np.ndarray:
    if len(speed_data) < 4:
        return speed_data
    median = np.median(speed_data)
    mad = np.median(np.abs(speed_data - median))
    if mad == 0:
        std = np.std(speed_data)
        if std == 0:
            return speed_data
        modified_z = 0.6745 * (speed_data - median) / std
    else:
        modified_z = 0.6745 * (speed_data - median) / mad
    mask = np.abs(modified_z) <= zscore_threshold
    cleaned = speed_data.copy()
    cleaned[~mask] = np.interp(
        np.where(~mask)[0],
        np.where(mask)[0],
        speed_data[mask]
    ) if np.any(mask) else speed_data
    return cleaned


def preprocess_waveform(
    vibration_data: np.ndarray,
    sample_rate: float,
    speed_data: Optional[np.ndarray] = None
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    pp = hyperparams.preprocessing or {}

    detrend_method = pp.get("detrend_method", "linear")
    vibration = detrend_signal(vibration_data, detrend_method)

    outlier_method = pp.get("outlier_handling", "median_filter")
    median_size = pp.get("median_filter_size", 5)
    clip_sigma = pp.get("clip_sigma", 10.0)
    vibration = remove_outliers(vibration, outlier_method, median_size, clip_sigma)

    highpass_hz = pp.get("highpass_cutoff_hz", 0.5)
    vibration = highpass_filter(vibration, sample_rate, highpass_hz)

    lowpass_hz = pp.get("lowpass_cutoff_hz", 0)
    if lowpass_hz and lowpass_hz > 0:
        vibration = lowpass_filter(vibration, sample_rate, lowpass_hz)

    notch_freqs = np.array(pp.get("notch_frequencies", []), dtype=float)
    notch_q = pp.get("notch_q", 30.0)
    if len(notch_freqs) > 0:
        vibration = notch_filter(vibration, sample_rate, notch_freqs, notch_q)

    processed_speed = None
    if speed_data is not None and len(speed_data) > 0:
        resamp = hyperparams.resampling or {}
        speed_clean = remove_speed_outliers(
            speed_data,
            resamp.get("speed_outlier_zscore", 3.0)
        )
        processed_speed = smooth_speed(
            speed_clean,
            resamp.get("speed_smooth_window", 50)
        )

    return vibration, processed_speed
