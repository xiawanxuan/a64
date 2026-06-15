import time
import uuid
import numpy as np
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime, timezone
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.models.timescale_models import OrderSpectrum, GearFaultFeatures, VibrationWaveform, RotationSpeed
from app.models.mysql_models import Gearbox, GearParam, Shaft, Sensor, WindTurbine
from app.algorithms.preprocessing import preprocess_waveform
from app.algorithms.order_resampling import resample_to_angle_domain, align_speed_to_vibration
from app.algorithms.order_spectrum import compute_order_spectrum
from app.algorithms.fault_feature_extraction import extract_gear_fault_features, GearFaultFeatures as FeatResult
from app.core.exceptions import BusinessException
from app.core.error_codes import ErrorCode
from app.core.hyperparams import load_hyperparams
from app.services.failure_preservation import preserve_failed_analysis

hyperparams = load_hyperparams()


async def validate_turbine_and_gear(
    mysql_db: AsyncSession,
    turbine_id: str,
    gear_id: Optional[str] = None,
) -> Tuple[WindTurbine, List[GearParam], Gearbox]:
    turbine_result = await mysql_db.execute(
        select(WindTurbine).where(WindTurbine.turbine_id == turbine_id)
    )
    turbine = turbine_result.scalar_one_or_none()
    if not turbine:
        raise BusinessException(ErrorCode.TURBINE_NOT_FOUND)

    if not gear_id:
        gear_result = await mysql_db.execute(
            select(Gearbox).where(Gearbox.turbine_id == turbine_id).limit(1)
        )
        gearbox = gear_result.scalar_one_or_none()
        if not gearbox:
            raise BusinessException(
                ErrorCode.GEARBOX_NOT_FOUND,
                f"风机 {turbine_id} 未配置齿轮箱"
            )
        gear_id = gearbox.gear_id
    else:
        gear_result = await mysql_db.execute(
            select(Gearbox).where(
                and_(
                    Gearbox.gear_id == gear_id,
                    Gearbox.turbine_id == turbine_id
                )
            )
        )
        gearbox = gear_result.scalar_one_or_none()
        if not gearbox:
            raise BusinessException(ErrorCode.GEARBOX_NOT_FOUND)

    params_result = await mysql_db.execute(
        select(GearParam).where(GearParam.gear_id == gear_id).order_by(GearParam.stage, GearParam.id)
    )
    gear_params = list(params_result.scalars().all())
    if not gear_params:
        raise BusinessException(
            ErrorCode.GEAR_PARAM_NOT_FOUND,
            f"齿轮箱 {gear_id} 未配置齿轮参数"
        )

    return turbine, gear_params, gearbox


async def resolve_speed_shaft(
    mysql_db: AsyncSession,
    turbine_id: str,
    user_shaft_id: Optional[str] = None,
) -> str:
    if user_shaft_id:
        return user_shaft_id

    result = await mysql_db.execute(
        select(Shaft).where(
            and_(
                Shaft.turbine_id == turbine_id,
                Shaft.position == "low_speed"
            )
        ).limit(1)
    )
    shaft = result.scalar_one_or_none()
    if shaft:
        return shaft.shaft_id

    result2 = await mysql_db.execute(
        select(Shaft).where(Shaft.turbine_id == turbine_id).order_by(Shaft.id).limit(1)
    )
    any_shaft = result2.scalar_one_or_none()
    if any_shaft:
        return any_shaft.shaft_id

    return f"SH-{turbine_id}-DEFAULT"


async def resolve_sensor(
    mysql_db: AsyncSession,
    turbine_id: str,
    gear_id: str,
    user_sensor_id: Optional[str] = None,
) -> Sensor:
    if user_sensor_id:
        result = await mysql_db.execute(
            select(Sensor).where(
                and_(
                    Sensor.sensor_id == user_sensor_id,
                    Sensor.turbine_id == turbine_id
                )
            )
        )
        sensor = result.scalar_one_or_none()
        if sensor:
            return sensor
        raise BusinessException(ErrorCode.SENSOR_NOT_FOUND)

    result = await mysql_db.execute(
        select(Sensor).where(
            and_(
                Sensor.turbine_id == turbine_id,
                Sensor.gear_id == gear_id,
                Sensor.sensor_type == "acc",
                Sensor.measure_axis == "Z"
            )
        ).limit(1)
    )
    sensor = result.scalar_one_or_none()
    if sensor:
        return sensor

    result2 = await mysql_db.execute(
        select(Sensor).where(
            and_(
                Sensor.turbine_id == turbine_id,
                Sensor.sensor_type == "acc"
            )
        ).order_by(Sensor.id).limit(1)
    )
    sensor = result2.scalar_one_or_none()
    if not sensor:
        raise BusinessException(
            ErrorCode.SENSOR_NOT_FOUND,
            f"风机 {turbine_id} 未配置加速度传感器"
        )
    return sensor


def _datetime_to_unix(dt_list: List[datetime]) -> np.ndarray:
    return np.array([
        (d.replace(tzinfo=timezone.utc).timestamp() if d.tzinfo else d.timestamp())
        for d in dt_list
    ], dtype=np.float64)


async def fetch_waveform_and_speed(
    ts_db: AsyncSession,
    turbine_id: str,
    sensor_id: str,
    shaft_id: str,
    start_time: datetime,
    end_time: datetime,
    min_speed: Optional[float] = None,
    max_speed: Optional[float] = None,
) -> Tuple[List[datetime], np.ndarray, np.ndarray, List[datetime], int]:
    if end_time <= start_time:
        raise BusinessException(ErrorCode.QUERY_TIME_RANGE_INVALID)

    speed_conditions = [
        RotationSpeed.turbine_id == turbine_id,
        RotationSpeed.time >= start_time,
        RotationSpeed.time <= end_time,
    ]
    if shaft_id:
        speed_conditions.append(RotationSpeed.shaft_id == shaft_id)
    if min_speed is not None:
        speed_conditions.append(RotationSpeed.speed_rpm >= min_speed)
    if max_speed is not None:
        speed_conditions.append(RotationSpeed.speed_rpm <= max_speed)

    speed_stmt = (
        select(RotationSpeed)
        .where(and_(*speed_conditions))
        .order_by(RotationSpeed.time.asc())
    )
    speed_result = await ts_db.execute(speed_stmt)
    speed_rows = list(speed_result.scalars().all())

    if not speed_rows:
        raise BusinessException(
            ErrorCode.SPEED_DATA_MISSING,
            f"时间范围内无有效转速数据: {start_time} ~ {end_time}"
        )

    valid_start = max(start_time, speed_rows[0].time)
    valid_end = min(end_time, speed_rows[-1].time)
    if valid_end <= valid_start:
        raise BusinessException(
            ErrorCode.QUERY_TIME_RANGE_INVALID,
            "有效转速时间范围为空"
        )

    vib_stmt = (
        select(VibrationWaveform)
        .where(
            and_(
                VibrationWaveform.turbine_id == turbine_id,
                VibrationWaveform.sensor_id == sensor_id,
                VibrationWaveform.time >= valid_start,
                VibrationWaveform.time <= valid_end,
            )
        )
        .order_by(VibrationWaveform.time.asc())
    )
    vib_result = await ts_db.execute(vib_stmt)
    vib_rows = list(vib_result.scalars().all())

    if not vib_rows:
        raise BusinessException(
            ErrorCode.QUERY_NO_DATA,
            f"时间范围内无振动波形: turbine={turbine_id}, sensor={sensor_id}"
        )

    vib_times = [r.time for r in vib_rows]
    sample_rates = [r.sample_rate for r in vib_rows]
    if not sample_rates:
        raise BusinessException(ErrorCode.PARAM_INVALID, "波形采样率缺失")
    sample_rate = int(sample_rates[0])

    vib_values = np.array([
        r.acceleration_z if r.acceleration_z is not None
        else (r.acceleration_x if r.acceleration_x is not None else 0.0)
        for r in vib_rows
    ], dtype=np.float64)

    speed_times = [r.time for r in speed_rows]
    speed_values = np.array([r.speed_rpm for r in speed_rows], dtype=np.float64)

    if len(vib_times) < 256:
        raise BusinessException(
            ErrorCode.WAVEFORM_INSUFFICIENT_DATA,
            f"有效波形样本数不足: {len(vib_times)} < 256"
        )

    return vib_times, vib_values, speed_values, speed_times, sample_rate


def build_gear_params_with_ratios(
    gear_params_list: List[GearParam]
) -> List[Dict[str, Any]]:
    params_by_stage: Dict[int, List[GearParam]] = {}
    for gp in gear_params_list:
        params_by_stage.setdefault(gp.stage, []).append(gp)

    sorted_stages = sorted(params_by_stage.keys())
    stage_ratios: Dict[int, float] = {}

    cumulative = 1.0
    for stage in sorted_stages:
        stage_params = params_by_stage[stage]
        driving = [g for g in stage_params if g.position in ("input", "intermediate")]
        driven = [g for g in stage_params if g.position in ("intermediate", "output")]

        if driving and driven:
            zin = min(g.teeth_count for g in driving)
            zout = max(g.teeth_count for g in driven)
            if zin > 0:
                stage_ratio = float(zout) / float(zin)
            else:
                stage_ratio = 1.0
        else:
            total_teeth = sum(g.teeth_count for g in stage_params)
            stage_ratio = float(total_teeth) / len(stage_params) if stage_params else 1.0

        stage_ratios[stage] = cumulative
        cumulative *= stage_ratio

    result: List[Dict[str, Any]] = []
    for gp in gear_params_list:
        result.append({
            "gear_param_id": gp.gear_param_id,
            "stage": gp.stage,
            "gear_type": gp.gear_type,
            "position": gp.position,
            "teeth_count": int(gp.teeth_count),
            "pitch_diameter": float(gp.pitch_diameter or 0),
            "module": float(gp.module or 0),
            "stage_speed_ratio": stage_ratios.get(gp.stage, 1.0),
        })

    return result


async def run_order_analysis(
    ts_db: AsyncSession,
    mysql_db: AsyncSession,
    turbine_id: str,
    gear_id: str,
    sensor_id: Optional[str],
    shaft_id: Optional[str],
    start_time: datetime,
    end_time: datetime,
    min_speed: Optional[float] = None,
    max_speed: Optional[float] = None,
    target_stage: Optional[int] = None,
) -> Dict[str, Any]:
    start_ts = time.time()

    saved_waveform = None
    saved_speed_vals = None
    saved_speed_times = None

    try:
        turbine, gear_params_raw, gearbox = await validate_turbine_and_gear(
            mysql_db, turbine_id, gear_id
        )
        sensor = await resolve_sensor(mysql_db, turbine_id, gearbox.gear_id, sensor_id)
        shaft_id_resolved = await resolve_speed_shaft(mysql_db, turbine_id, shaft_id)

        vib_times, vib_data, speed_vals, speed_times, sample_rate = await fetch_waveform_and_speed(
            ts_db, turbine_id, sensor.sensor_id, shaft_id_resolved,
            start_time, end_time, min_speed, max_speed
        )

        saved_waveform = vib_data.copy()
        saved_speed_vals = speed_vals.copy()
        saved_speed_times = _datetime_to_unix(speed_times)

        vib_unix_times = _datetime_to_unix(vib_times)
        vib_start_unix = float(vib_unix_times[0]) if len(vib_unix_times) > 0 else 0.0
        vib_end_unix = float(vib_unix_times[-1]) if len(vib_unix_times) > 0 else 0.0

        speed_unix_times = _datetime_to_unix(speed_times)
        aligned_speed = align_speed_to_vibration(
            speed_unix_times, speed_vals,
            vib_start_unix, vib_end_unix,
            sample_rate, len(vib_times),
            vib_actual_times=vib_unix_times
        )

        proc_waveform, proc_speed = preprocess_waveform(
            vib_data, sample_rate, aligned_speed
        )
        if proc_speed is None:
            proc_speed = aligned_speed

        angular_signal, phase_uniform, phase_orig, resample_meta = resample_to_angle_domain(
            proc_waveform, proc_speed, sample_rate,
            vibration_time_axis=vib_unix_times
        )

        samples_per_rev = float(resample_meta.get("samples_per_rev", 0))
        order_axis, spectrum, spectrum_meta = compute_order_spectrum(
            angular_signal, samples_per_rev
        )

        gear_params_with_ratio = build_gear_params_with_ratios(gear_params_raw)
        if target_stage is not None:
            gear_params_with_ratio = [
                g for g in gear_params_with_ratio if g["stage"] == target_stage
            ]
            if not gear_params_with_ratio:
                raise BusinessException(
                    ErrorCode.GEAR_PARAM_NOT_FOUND,
                    f"未找到第 {target_stage} 级齿轮参数"
                )

        feature_results = extract_gear_fault_features(
            order_axis, spectrum, proc_waveform,
            gear_params_with_ratio, speed_modulation_order=1.0
        )

        spectrum_id = uuid.uuid4()
        analysis_time = datetime.utcnow()
        max_order = float(np.max(order_axis))
        order_res = float(order_axis[1] - order_axis[0]) if len(order_axis) > 1 else 0.0

        spectrum_record = OrderSpectrum(
            id=spectrum_id,
            time=analysis_time,
            turbine_id=turbine_id,
            gear_id=gearbox.gear_id,
            analysis_start=vib_times[0],
            analysis_end=vib_times[-1],
            order_values=order_axis.astype(float).tolist(),
            amplitude_values=spectrum.astype(float).tolist(),
            max_order=max_order,
            order_resolution=order_res,
            resampled_count=len(angular_signal),
            status=0,
            created_at=analysis_time,
        )
        ts_db.add(spectrum_record)

        feature_ids = []
        for fr in feature_results:
            fid = uuid.uuid4()
            feature_ids.append(fid)
            feat_record = GearFaultFeatures(
                id=fid,
                time=analysis_time,
                turbine_id=turbine_id,
                gear_id=gearbox.gear_id,
                spectrum_id=spectrum_id,
                mesh_order=float(fr.mesh_order),
                mesh_amplitude=float(fr.mesh_amplitude),
                sideband_orders=[float(x) for x in fr.sideband_orders],
                sideband_amplitudes=[float(x) for x in fr.sideband_amplitudes],
                sideband_spacing=float(fr.sideband_spacing),
                max_sideband_amp=float(fr.max_sideband_amp),
                sideband_energy=float(fr.sideband_energy),
                kurtosis=float(fr.kurtosis) if fr.kurtosis else None,
                crest_factor=float(fr.crest_factor) if fr.crest_factor else None,
                rms_value=float(fr.rms_value) if fr.rms_value else None,
                peak_value=float(fr.peak_value) if fr.peak_value else None,
                fault_severity=int(fr.fault_severity),
                status=0,
                created_at=analysis_time,
            )
            ts_db.add(feat_record)

        cost_ms = (time.time() - start_ts) * 1000.0
        overall_severity = max((fr.fault_severity for fr in feature_results), default=0)
        mean_speed_rpm = float(np.mean(proc_speed))

        return {
            "turbine_id": turbine_id,
            "gear_id": gearbox.gear_id,
            "status": 2,
            "time_range": {"start_time": vib_times[0], "end_time": vib_times[-1]},
            "mean_speed_rpm": mean_speed_rpm,
            "valid_duration_sec": float(len(vib_times) / sample_rate),
            "spectrum": {
                "spectrum_id": spectrum_id,
                "turbine_id": turbine_id,
                "gear_id": gearbox.gear_id,
                "analysis_start": vib_times[0],
                "analysis_end": vib_times[-1],
                "order_values": order_axis.astype(float).tolist(),
                "amplitude_values": spectrum.astype(float).tolist(),
                "max_order": max_order,
                "order_resolution": order_res,
                "resampled_count": len(angular_signal),
                "created_at": analysis_time,
            },
            "fault_features": [
                {
                    "feature_id": feature_ids[i],
                    "spectrum_id": spectrum_id,
                    "turbine_id": turbine_id,
                    "gear_id": gearbox.gear_id,
                    "gear_param_id": fr.gear_param_id,
                    "stage": fr.stage,
                    "gear_type": fr.gear_type,
                    "teeth_count": fr.teeth_count,
                    "mesh_order": float(fr.mesh_order),
                    "mesh_amplitude": float(fr.mesh_amplitude),
                    "sideband_orders": [float(x) for x in fr.sideband_orders],
                    "sideband_amplitudes": [float(x) for x in fr.sideband_amplitudes],
                    "sideband_spacing": float(fr.sideband_spacing),
                    "max_sideband_amp": float(fr.max_sideband_amp),
                    "sideband_energy": float(fr.sideband_energy),
                    "kurtosis": float(fr.kurtosis) if fr.kurtosis else None,
                    "crest_factor": float(fr.crest_factor) if fr.crest_factor else None,
                    "rms_value": float(fr.rms_value) if fr.rms_value else None,
                    "peak_value": float(fr.peak_value) if fr.peak_value else None,
                    "fault_severity": int(fr.fault_severity),
                    "diagnosis_note": fr.diagnosis_note,
                    "created_at": analysis_time,
                }
                for i, fr in enumerate(feature_results)
            ],
            "overall_severity": overall_severity,
            "analysis_cost_ms": cost_ms,
            "message": f"分析成功, 共提取 {len(feature_results)} 组齿轮故障特征",
        }

    except BusinessException as be:
        await preserve_failed_analysis(
            ts_db,
            turbine_id=turbine_id,
            analysis_type="order_analysis",
            error=be,
            waveform_data=saved_waveform,
            speed_values=saved_speed_vals,
            speed_times=saved_speed_times,
            gear_id=gear_id,
            params={
                "start_time": str(start_time),
                "end_time": str(end_time),
                "sensor_id": sensor_id,
                "shaft_id": shaft_id,
                "min_speed": min_speed,
                "max_speed": max_speed,
                "target_stage": target_stage,
            },
        )
        raise
    except Exception as e:
        await preserve_failed_analysis(
            ts_db,
            turbine_id=turbine_id,
            analysis_type="order_analysis",
            error=e,
            waveform_data=saved_waveform,
            speed_values=saved_speed_vals,
            speed_times=saved_speed_times,
            gear_id=gear_id,
            params={
                "start_time": str(start_time),
                "end_time": str(end_time),
                "sensor_id": sensor_id,
                "shaft_id": shaft_id,
                "min_speed": min_speed,
                "max_speed": max_speed,
                "target_stage": target_stage,
            },
        )
        raise BusinessException(
            ErrorCode.FEATURE_EXTRACT_FAILED,
            f"阶次分析失败: {e}",
            cause=e
        )
