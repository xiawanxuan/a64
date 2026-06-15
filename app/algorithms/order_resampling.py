import numpy as np
from scipy import interpolate
from typing import Tuple, Optional, Dict, Any
from loguru import logger

from app.core.hyperparams import load_hyperparams
from app.core.exceptions import BusinessException
from app.core.error_codes import ErrorCode

hyperparams = load_hyperparams()


def compute_phase_from_speed(
    speed_rpm: np.ndarray,
    fs: float,
    detrend: bool = True
) -> np.ndarray:
    if fs <= 0:
        raise BusinessException(ErrorCode.PARAM_INVALID, "采样率必须大于0")
    if len(speed_rpm) < 2:
        raise BusinessException(ErrorCode.SPEED_DATA_INVALID, "转速数据长度不足")

    speed_hz = speed_rpm / 60.0
    dt = 1.0 / fs

    if detrend:
        speed_mean = np.mean(speed_hz)
        if speed_mean < 0.01:
            raise BusinessException(
                ErrorCode.ORDER_RESAMPLE_SPEED_TOO_LOW,
                f"平均转速过低: {speed_mean * 60:.2f} rpm"
            )

    phase = np.cumsum(speed_hz) * dt
    phase = phase - phase[0]
    return phase


def uniform_phase_axis(
    phase: np.ndarray,
    max_order: float,
    order_resolution: float,
    oversample: float = 1.2
) -> Tuple[np.ndarray, int, float]:
    if max_order <= 0 or order_resolution <= 0:
        raise BusinessException(ErrorCode.PARAM_INVALID, "阶次参数必须为正数")

    total_phase = float(phase[-1] - phase[0])
    if total_phase <= 0:
        raise BusinessException(ErrorCode.ORDER_RESAMPLE_FAILED, "相位增量非正")

    nyquist_order = max_order * oversample
    samples_per_rev = 2.0 * nyquist_order
    total_samples = int(np.ceil(total_phase * samples_per_rev))

    if total_samples < 10:
        raise BusinessException(
            ErrorCode.ORDER_RESAMPLE_FAILED,
            f"重采样点数过少: {total_samples}"
        )

    phase_uniform = np.linspace(phase[0], phase[-1], total_samples)
    actual_resolution = samples_per_rev / total_samples
    if actual_resolution > 0:
        actual_resolution = 1.0 / actual_resolution
    else:
        actual_resolution = order_resolution

    return phase_uniform, total_samples, actual_resolution


def resample_to_angle_domain(
    vibration_data: np.ndarray,
    speed_rpm: np.ndarray,
    fs: float,
    max_order: Optional[float] = None,
    order_resolution: Optional[float] = None,
    interpolation_method: str = "spline"
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    cfg = hyperparams.resampling or {}

    if max_order is None:
        max_order = cfg.get("max_order", 100.0)
    if order_resolution is None:
        order_resolution = cfg.get("order_resolution", 0.01)
    if not interpolation_method:
        interpolation_method = cfg.get("interpolation_method", "spline")

    min_valid_speed = cfg.get("min_valid_speed_rpm", 2.0)
    mean_speed = np.mean(speed_rpm)
    if mean_speed < min_valid_speed:
        raise BusinessException(
            ErrorCode.ORDER_RESAMPLE_SPEED_TOO_LOW,
            f"平均转速 {mean_speed:.2f} rpm 低于最低有效值 {min_valid_speed} rpm"
        )

    if len(vibration_data) != len(speed_rpm):
        ratio = len(speed_rpm) / len(vibration_data) if len(vibration_data) > 0 else 0
        raise BusinessException(
            ErrorCode.ORDER_RESAMPLE_SIZE_MISMATCH,
            f"波形长度({len(vibration_data)})与转速长度({len(speed_rpm)})不匹配, ratio={ratio:.3f}"
        )

    if len(vibration_data) < 64:
        raise BusinessException(
            ErrorCode.WAVEFORM_INSUFFICIENT_DATA,
            f"波形数据样本不足: {len(vibration_data)} < 64"
        )

    phase = compute_phase_from_speed(
        speed_rpm, fs,
        detrend=cfg.get("detrend_before_resample", True)
    )

    oversample = cfg.get("resample_oversample", 1.2)
    phase_uniform, N, actual_res = uniform_phase_axis(
        phase, max_order, order_resolution, oversample
    )

    time_axis = np.arange(len(vibration_data)) / fs

    try:
        if interpolation_method == "linear":
            interp_func = interpolate.interp1d(
                phase, vibration_data, kind="linear",
                bounds_error=False, fill_value="extrapolate"
            )
            vibration_angular = interp_func(phase_uniform)
        elif interpolation_method == "spline":
            spline_order = 3
            if len(phase) <= spline_order:
                spline_order = len(phase) - 1
            tck = interpolate.splrep(phase, vibration_data, k=spline_order, s=0)
            vibration_angular = interpolate.splev(phase_uniform, tck, der=0)
        elif interpolation_method == "cubic":
            interp_func = interpolate.interp1d(
                phase, vibration_data, kind="cubic",
                bounds_error=False, fill_value="extrapolate"
            )
            vibration_angular = interp_func(phase_uniform)
        else:
            interp_func = interpolate.interp1d(
                phase, vibration_data, kind="linear",
                bounds_error=False, fill_value="extrapolate"
            )
            vibration_angular = interp_func(phase_uniform)
    except Exception as e:
        logger.error(f"阶次重采样插值失败: {e}, fallback到线性插值")
        try:
            interp_func = interpolate.interp1d(
                phase, vibration_data, kind="linear",
                bounds_error=False, fill_value="extrapolate"
            )
            vibration_angular = interp_func(phase_uniform)
        except Exception as e2:
            raise BusinessException(
                ErrorCode.ORDER_RESAMPLE_FAILED,
                f"角度域插值失败: {e2}",
                cause=e2
            )

    vibration_angular = np.nan_to_num(vibration_angular, nan=0.0, posinf=0.0, neginf=0.0)

    meta = {
        "total_phase_rev": float(phase[-1] - phase[0]),
        "samples_per_rev": float(N) / max(float(phase[-1] - phase[0]), 1.0),
        "interpolation_method": interpolation_method,
        "mean_speed_rpm": float(mean_speed),
        "min_speed_rpm": float(np.min(speed_rpm)),
        "max_speed_rpm": float(np.max(speed_rpm)),
        "actual_order_resolution": float(actual_res),
    }

    return vibration_angular, phase_uniform, phase, meta


def align_speed_to_vibration(
    speed_times: np.ndarray,
    speed_values: np.ndarray,
    vib_start_time: float,
    vib_end_time: float,
    vib_sample_rate: float,
    vib_len: int
) -> np.ndarray:
    if len(speed_times) == 0 or len(speed_values) == 0:
        raise BusinessException(ErrorCode.SPEED_DATA_MISSING, "转速数据为空")
    if vib_sample_rate <= 0:
        raise BusinessException(ErrorCode.PARAM_INVALID, "采样率必须为正数")

    vib_time_axis = vib_start_time + np.arange(vib_len) / vib_sample_rate

    try:
        if len(speed_times) == 1:
            return np.full(vib_len, float(speed_values[0]), dtype=float)

        interp_kind = "linear" if len(speed_times) < 4 else "cubic"
        if len(speed_times) < 4:
            interp_kind = "linear"

        valid_mask = ~np.isnan(speed_values)
        if np.sum(valid_mask) < 2:
            raise BusinessException(ErrorCode.SPEED_DATA_INVALID, "有效转速数据点不足2个")

        f = interpolate.interp1d(
            speed_times[valid_mask], speed_values[valid_mask],
            kind=interp_kind, bounds_error=False, fill_value="extrapolate"
        )
        aligned_speed = f(vib_time_axis)
        aligned_speed = np.nan_to_num(aligned_speed, nan=0.0, posinf=0.0, neginf=0.0)

        cfg = hyperparams.resampling or {}
        min_speed = cfg.get("min_valid_speed_rpm", 2.0)
        aligned_speed = np.maximum(aligned_speed, min_speed * 0.5)

        return aligned_speed
    except BusinessException:
        raise
    except Exception as e:
        raise BusinessException(
            ErrorCode.SPEED_DATA_INVALID,
            f"转速时间对齐失败: {e}",
            cause=e
        )
