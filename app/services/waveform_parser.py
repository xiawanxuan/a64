import struct
import numpy as np
from typing import Tuple, Optional, List
from datetime import datetime, timedelta
from loguru import logger

from app.core.exceptions import BusinessException
from app.core.error_codes import ErrorCode


FORMAT_MAP = {
    "float32_be": (">f", 4, np.float32),
    "float32_le": ("<f", 4, np.float32),
    "float64_be": (">d", 8, np.float64),
    "float64_le": ("<d", 8, np.float64),
    "int16_be": (">h", 2, np.int16),
    "int16_le": ("<h", 2, np.int16),
    "int32_be": (">i", 4, np.int32),
    "int32_le": ("<i", 4, np.int32),
}


def detect_format(data: bytes, sample_count: int) -> str:
    candidates = ["float32_le", "float32_be", "int16_le", "int16_le"]
    best = "float32_le"
    best_score = -1e18
    for fmt in candidates:
        _, elem_size, np_type = FORMAT_MAP[fmt]
        if len(data) < sample_count * elem_size:
            continue
        try:
            arr = np.frombuffer(data[:sample_count * elem_size], dtype=np_type)
            if np_type in (np.int16, np.int32):
                arr = arr.astype(np.float64) / (2 ** (elem_size * 8 - 1))
            if len(arr) < 10:
                continue
            std = float(np.std(arr))
            kurt = float(np.mean((arr - np.mean(arr)) ** 4) / (std ** 4)) if std > 0 else 0
            ratio_nonzero = float(np.sum(np.abs(arr) > 1e-8)) / len(arr)
            if 2.0 <= kurt <= 50.0 and 0.5 < ratio_nonzero < 1.0:
                score = kurt * ratio_nonzero
                if score > best_score:
                    best_score = score
                    best = fmt
        except Exception:
            continue
    return best


def parse_binary_waveform(
    binary_data: bytes,
    waveform_format: str = "float32_le",
    start_time: Optional[datetime] = None,
    sample_rate: int = 25600,
    num_channels: int = 1,
    channel_layout: str = "interleaved",
    scale_factor: float = 1.0,
    offset: float = 0.0,
) -> Tuple[List[datetime], np.ndarray]:
    if waveform_format not in FORMAT_MAP:
        raise BusinessException(
            ErrorCode.WAVEFORM_FORMAT_UNSUPPORTED,
            f"不支持的二进制格式: {waveform_format}"
        )

    _, elem_size, np_type = FORMAT_MAP[waveform_format]

    if len(binary_data) == 0:
        raise BusinessException(ErrorCode.WAVEFORM_PARSE_ERROR, "二进制数据为空")

    total_elems = len(binary_data) // elem_size
    if total_elems == 0:
        raise BusinessException(
            ErrorCode.WAVEFORM_PARSE_ERROR,
            f"数据长度不足: {len(binary_data)} bytes, 元素大小: {elem_size}"
        )

    try:
        raw_arr = np.frombuffer(binary_data[:total_elems * elem_size], dtype=np_type)
    except Exception as e:
        raise BusinessException(
            ErrorCode.WAVEFORM_PARSE_ERROR,
            f"numpy解析失败: {e}",
            cause=e
        )

    try:
        if np_type in (np.int16, np.int32):
            max_val = float(2 ** (elem_size * 8 - 1))
            arr = raw_arr.astype(np.float64) / max_val
        else:
            arr = raw_arr.astype(np.float64)

        if scale_factor != 1.0 or offset != 0.0:
            arr = arr * scale_factor + offset

        if num_channels > 1:
            if channel_layout == "interleaved":
                arr = arr.reshape(-1, num_channels).T
            else:
                arr = arr.reshape(num_channels, -1)

        sample_count = arr.shape[-1] if arr.ndim > 1 else len(arr)

        if start_time is None:
            start_time = datetime.utcnow()

        dt = timedelta(seconds=1.0 / sample_rate)
        times = [start_time + i * dt for i in range(sample_count)]

        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)

        return times, arr

    except BusinessException:
        raise
    except Exception as e:
        raise BusinessException(
            ErrorCode.WAVEFORM_PARSE_ERROR,
            f"波形解析错误: {e}",
            cause=e
        )


def split_channels(
    multi_channel_data: np.ndarray,
    channel_names: Optional[List[str]] = None
) -> dict:
    if multi_channel_data.ndim == 1:
        return {"ch0": multi_channel_data}

    result = {}
    n_channels = multi_channel_data.shape[0]
    if channel_names is None:
        channel_names = [f"ch{i}" for i in range(n_channels)]
    for i in range(min(n_channels, len(channel_names))):
        result[channel_names[i]] = multi_channel_data[i]
    return result


def compute_time_vector(
    sample_count: int,
    sample_rate: int,
    start_time: datetime
) -> List[datetime]:
    if sample_rate <= 0:
        raise BusinessException(ErrorCode.PARAM_INVALID, "采样率必须为正数")
    dt = timedelta(seconds=1.0 / sample_rate)
    return [start_time + i * dt for i in range(sample_count)]
