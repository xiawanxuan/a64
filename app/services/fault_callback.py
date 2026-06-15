import asyncio
import uuid
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from loguru import logger
import httpx

from app.config.settings import get_settings
from app.core.hyperparams import load_hyperparams
from app.core.exceptions import BusinessException
from app.core.error_codes import ErrorCode
from app.algorithms.fault_feature_extraction import GearFaultFeatures


settings = get_settings()
hyperparams = load_hyperparams()


_callback_cooldown_cache: Dict[Tuple[str, str], float] = {}
_callback_last_push_time: Dict[Tuple[str, str], float] = {}


@dataclass
class FaultCallbackPayload:
    push_id: str
    push_time: str
    turbine_id: str
    gear_id: str
    analysis_start: str
    analysis_end: str
    mean_speed_rpm: float
    overall_severity: int
    triggered_features: List[Dict[str, Any]]
    spectrum_summary: Optional[Dict[str, Any]] = None
    raw_spectrum: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def _get_callback_config() -> Dict[str, Any]:
    cfg = hyperparams.get("fault_callback") or {}
    if not isinstance(cfg, dict):
        return {}
    return cfg


def is_callback_enabled() -> bool:
    cfg_enabled = bool(_get_callback_config().get("enabled", True))
    return bool(settings.fault_callback_enabled and cfg_enabled)


def _check_cooldown(turbine_id: str, gear_id: str) -> Tuple[bool, float]:
    cfg = _get_callback_config()
    cooldown_sec = float(cfg.get("cooldown_seconds", 300))
    key = (turbine_id, gear_id)
    now = time.time()
    last_push = _callback_last_push_time.get(key, 0.0)
    elapsed = now - last_push
    if elapsed < cooldown_sec:
        return False, cooldown_sec - elapsed
    return True, 0.0


def _is_triggered(
    feature: GearFaultFeatures,
    noise_floor: float,
    cfg: Dict[str, Any]
) -> bool:
    min_severity = int(cfg.get("min_severity_to_push", 2))
    if feature.fault_severity >= min_severity:
        return True

    mesh_abs_thresh = float(cfg.get("mesh_amplitude_absolute_threshold", 10.0))
    if feature.mesh_amplitude >= mesh_abs_thresh:
        return True

    mesh_noise_ratio = float(cfg.get("mesh_amplitude_noise_ratio", 10.0))
    if noise_floor > 0 and feature.mesh_amplitude >= noise_floor * mesh_noise_ratio:
        return True

    max_sb_ratio = float(cfg.get("max_sideband_amp_ratio", 0.3))
    if feature.mesh_amplitude > 0 and feature.max_sideband_amp / feature.mesh_amplitude >= max_sb_ratio:
        return True

    return False


def _get_noise_floor_from_spectrum(
    spectrum_amps: Optional[List[float]]
) -> float:
    if not spectrum_amps or len(spectrum_amps) < 10:
        return 0.0
    try:
        import numpy as np
        arr = np.array(spectrum_amps, dtype=np.float64)
        return float(np.percentile(arr, 10))
    except Exception:
        return 0.0


def _serialize_feature_for_push(
    feature: Dict[str, Any],
    include_sidebands: bool,
    cfg: Dict[str, Any]
) -> Dict[str, Any]:
    out = {
        "gear_param_id": feature.get("gear_param_id"),
        "stage": feature.get("stage"),
        "gear_type": feature.get("gear_type"),
        "teeth_count": feature.get("teeth_count"),
        "mesh_order": feature.get("mesh_order"),
        "mesh_amplitude": feature.get("mesh_amplitude"),
        "sideband_spacing": feature.get("sideband_spacing"),
        "max_sideband_amp": feature.get("max_sideband_amp"),
        "sideband_energy": feature.get("sideband_energy"),
        "kurtosis": feature.get("kurtosis"),
        "crest_factor": feature.get("crest_factor"),
        "rms_value": feature.get("rms_value"),
        "peak_value": feature.get("peak_value"),
        "fault_severity": feature.get("fault_severity"),
        "diagnosis_note": feature.get("diagnosis_note"),
    }
    if include_sidebands:
        out["sideband_orders"] = feature.get("sideband_orders", [])
        out["sideband_amplitudes"] = feature.get("sideband_amplitudes", [])
    return out


def _validate_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    return url.startswith("http://") or url.startswith("https://")


async def _send_http_request(
    url: str,
    payload: Dict[str, Any],
    timeout_sec: int,
    headers: Dict[str, str]
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        return await client.post(url, json=payload, headers=headers)


async def push_fault_notification(
    turbine_id: str,
    gear_id: str,
    analysis_start: datetime,
    analysis_end: datetime,
    feature_results: List[Dict[str, Any]],
    spectrum_data: Optional[Dict[str, Any]] = None,
    mean_speed_rpm: float = 0.0,
    overall_severity: int = 0,
    noise_floor: Optional[float] = None,
    analysis_cost_ms: Optional[float] = None,
    spectrum_id: Optional[uuid.UUID] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    force_push: bool = False,
) -> Tuple[bool, Optional[str], Optional[FaultCallbackPayload]]:
    if not is_callback_enabled() and not force_push:
        return False, "callback disabled", None

    cfg = _get_callback_config()
    include_sidebands = bool(cfg.get("include_sideband_details", True))
    include_full_spectrum = bool(cfg.get("include_full_spectrum", False))

    if not _validate_url(settings.fault_callback_url):
        err = f"回调地址无效: {settings.fault_callback_url}"
        logger.warning(err)
        if force_push:
            raise BusinessException(ErrorCode.CALLBACK_URL_INVALID, err)
        return False, err, None

    if noise_floor is None and spectrum_data:
        noise_floor = _get_noise_floor_from_spectrum(spectrum_data.get("amplitude_values"))

    if noise_floor is None:
        noise_floor = 0.0

    triggered = []
    for fr in feature_results:
        try:
            gear_feat = GearFaultFeatures(
                gear_param_id=str(fr.get("gear_param_id", "")),
                stage=int(fr.get("stage", 0)),
                gear_type=str(fr.get("gear_type", "")),
                teeth_count=int(fr.get("teeth_count", 0)),
                mesh_order=float(fr.get("mesh_order", 0.0)),
                mesh_amplitude=float(fr.get("mesh_amplitude", 0.0)),
                sideband_orders=list(fr.get("sideband_orders", [])),
                sideband_amplitudes=list(fr.get("sideband_amplitudes", [])),
                sideband_spacing=float(fr.get("sideband_spacing", 0.0)),
                max_sideband_amp=float(fr.get("max_sideband_amp", 0.0)),
                sideband_energy=float(fr.get("sideband_energy", 0.0)),
                kurtosis=float(fr.get("kurtosis") or 0.0),
                crest_factor=float(fr.get("crest_factor") or 0.0),
                rms_value=float(fr.get("rms_value") or 0.0),
                peak_value=float(fr.get("peak_value") or 0.0),
                fault_severity=int(fr.get("fault_severity", 0)),
                diagnosis_note=str(fr.get("diagnosis_note", "")),
            )
            if force_push or _is_triggered(gear_feat, noise_floor, cfg):
                triggered.append(_serialize_feature_for_push(fr, include_sidebands, cfg))
        except Exception as e:
            logger.warning(f"特征筛选异常，跳过: {e}")
            continue

    if not triggered and not force_push:
        return False, "no triggered features", None

    can_push, wait_sec = _check_cooldown(turbine_id, gear_id)
    if not can_push and not force_push:
        return False, f"cooldown active, wait {wait_sec:.1f}s", None

    push_id = str(uuid.uuid4())
    payload = FaultCallbackPayload(
        push_id=push_id,
        push_time=datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
        turbine_id=turbine_id,
        gear_id=gear_id,
        analysis_start=analysis_start.replace(tzinfo=timezone.utc).isoformat(),
        analysis_end=analysis_end.replace(tzinfo=timezone.utc).isoformat(),
        mean_speed_rpm=float(mean_speed_rpm),
        overall_severity=int(overall_severity),
        triggered_features=triggered,
        metadata={
            "noise_floor": float(noise_floor) if noise_floor is not None else None,
            "analysis_cost_ms": float(analysis_cost_ms) if analysis_cost_ms is not None else None,
            "spectrum_id": str(spectrum_id) if spectrum_id else None,
            "source": "windfarm-diagnosis-platform",
            "version": settings.app_version,
        }
    )

    if spectrum_data:
        payload.spectrum_summary = {
            "max_order": spectrum_data.get("max_order"),
            "order_resolution": spectrum_data.get("order_resolution"),
            "resampled_count": spectrum_data.get("resampled_count"),
            "peak_order": spectrum_data.get("peak_order"),
            "peak_amplitude": spectrum_data.get("peak_amplitude"),
        }
        if include_full_spectrum:
            payload.raw_spectrum = {
                "order_values": spectrum_data.get("order_values"),
                "amplitude_values": spectrum_data.get("amplitude_values"),
            }

    if extra_metadata:
        payload.metadata.update(extra_metadata)

    payload_dict = None
    try:
        payload_dict = asdict(payload)
        json.dumps(payload_dict, ensure_ascii=False, default=str)
    except Exception as e:
        err = f"推送数据序列化失败: {e}"
        logger.error(err)
        if force_push:
            raise BusinessException(ErrorCode.CALLBACK_SERIALIZATION_FAILED, err, cause=e)
        return False, err, None

    headers = {"Content-Type": "application/json"}
    if settings.fault_callback_auth_header and settings.fault_callback_auth_token:
        headers[settings.fault_callback_auth_header] = settings.fault_callback_auth_token

    max_retries = max(0, int(settings.fault_callback_max_retries))
    retry_interval = max(0, int(settings.fault_callback_retry_interval_sec))
    timeout_sec = max(1, int(settings.fault_callback_timeout_sec))

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = await _send_http_request(
                url=settings.fault_callback_url,
                payload=payload_dict,
                timeout_sec=timeout_sec,
                headers=headers,
            )
            if 200 <= response.status_code < 300:
                _callback_last_push_time[(turbine_id, gear_id)] = time.time()
                logger.info(
                    f"[Callback] 推送成功 push_id={push_id} "
                    f"turbine={turbine_id} gear={gear_id} "
                    f"triggered={len(triggered)} severity={overall_severity}"
                )
                return True, None, payload
            else:
                last_error = (
                    f"响应状态码错误 status={response.status_code} "
                    f"body={response.text[:200]}"
                )
                logger.warning(f"[Callback] 推送失败(attempt {attempt + 1}/{max_retries + 1}): {last_error}")
        except httpx.TimeoutException as e:
            last_error = f"请求超时: {e}"
            logger.warning(f"[Callback] 推送超时(attempt {attempt + 1}/{max_retries + 1}): {last_error}")
        except httpx.HTTPError as e:
            last_error = f"HTTP错误: {e}"
            logger.warning(f"[Callback] 推送HTTP错误(attempt {attempt + 1}/{max_retries + 1}): {last_error}")
        except Exception as e:
            last_error = f"未知错误: {type(e).__name__}: {e}"
            logger.exception(f"[Callback] 推送异常(attempt {attempt + 1}/{max_retries + 1})")

        if attempt < max_retries and retry_interval > 0:
            await asyncio.sleep(retry_interval)

    err_msg = last_error or "推送失败原因未知"
    logger.error(
        f"[Callback] 推送重试耗尽 push_id={push_id} "
        f"turbine={turbine_id} gear={gear_id}: {err_msg}"
    )
    if force_push:
        raise BusinessException(ErrorCode.CALLBACK_RETRY_EXHAUSTED, err_msg)
    return False, err_msg, payload


async def push_fault_notification_async(
    *args,
    **kwargs,
) -> None:
    try:
        await push_fault_notification(*args, **kwargs)
    except Exception as e:
        logger.warning(f"[Callback] 异步推送后台任务异常: {e}")


def create_background_push_task(
    turbine_id: str,
    gear_id: str,
    analysis_start: datetime,
    analysis_end: datetime,
    feature_results: List[Dict[str, Any]],
    spectrum_data: Optional[Dict[str, Any]] = None,
    mean_speed_rpm: float = 0.0,
    overall_severity: int = 0,
    noise_floor: Optional[float] = None,
    analysis_cost_ms: Optional[float] = None,
    spectrum_id: Optional[uuid.UUID] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> asyncio.Task:
    return asyncio.create_task(
        push_fault_notification_async(
            turbine_id=turbine_id,
            gear_id=gear_id,
            analysis_start=analysis_start,
            analysis_end=analysis_end,
            feature_results=feature_results,
            spectrum_data=spectrum_data,
            mean_speed_rpm=mean_speed_rpm,
            overall_severity=overall_severity,
            noise_floor=noise_floor,
            analysis_cost_ms=analysis_cost_ms,
            spectrum_id=spectrum_id,
            extra_metadata=extra_metadata,
        )
    )
