import math
import numpy as np
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
from loguru import logger
from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.timescale_models import (
    VibrationWaveform, RotationSpeed, OrderSpectrum, GearFaultFeatures, UploadBatch
)
from app.models.mysql_models import (
    WindTurbine, WindFarm, Gearbox, GearParam, Sensor, Shaft
)
from app.core.exceptions import BusinessException
from app.core.error_codes import ErrorCode


async def query_waveform(
    ts_db: AsyncSession,
    turbine_id: str,
    sensor_id: Optional[str],
    start_time: datetime,
    end_time: datetime,
    min_speed: Optional[float] = None,
    max_speed: Optional[float] = None,
    max_points: int = 100000,
    downsample: bool = True,
) -> Dict[str, Any]:
    if end_time <= start_time:
        raise BusinessException(ErrorCode.QUERY_TIME_RANGE_INVALID)

    speed_filtered = False
    valid_time_start, valid_time_end = start_time, end_time

    if min_speed is not None or max_speed is not None:
        speed_conds = [
            RotationSpeed.turbine_id == turbine_id,
            RotationSpeed.time >= start_time,
            RotationSpeed.time <= end_time,
        ]
        if min_speed is not None:
            speed_conds.append(RotationSpeed.speed_rpm >= min_speed)
        if max_speed is not None:
            speed_conds.append(RotationSpeed.speed_rpm <= max_speed)

        speed_stmt = (
            select(RotationSpeed.time)
            .where(and_(*speed_conds))
            .order_by(RotationSpeed.time.asc())
        )
        speed_times_res = await ts_db.execute(speed_stmt)
        speed_times_list = list(speed_times_res.scalars().all())

        if not speed_times_list:
            raise BusinessException(ErrorCode.QUERY_NO_DATA, "转速过滤后无有效数据")

        valid_time_start = min(speed_times_list)
        valid_time_end = max(speed_times_list)
        speed_filtered = True

    vib_conds = [
        VibrationWaveform.turbine_id == turbine_id,
        VibrationWaveform.time >= valid_time_start,
        VibrationWaveform.time <= valid_time_end,
    ]
    if sensor_id:
        vib_conds.append(VibrationWaveform.sensor_id == sensor_id)

    count_stmt = select(func.count()).select_from(
        select(VibrationWaveform).where(and_(*vib_conds)).subquery()
    )
    total_points = await ts_db.scalar(count_stmt) or 0

    if total_points == 0:
        raise BusinessException(ErrorCode.QUERY_NO_DATA)

    sample_rate_stmt = (
        select(VibrationWaveform.sample_rate)
        .where(and_(*vib_conds))
        .limit(1)
    )
    sample_rate_res = await ts_db.execute(sample_rate_stmt)
    sample_rate = int(sample_rate_res.scalar_one_or_none() or 25600)

    actual_max_points = max_points
    ratio = 1.0
    is_downsampled = False
    limit = total_points

    if downsample and total_points > actual_max_points:
        ratio = total_points / actual_max_points
        limit = actual_max_points
        is_downsampled = True

    vib_stmt = (
        select(VibrationWaveform)
        .where(and_(*vib_conds))
        .order_by(VibrationWaveform.time.asc())
        .limit(limit)
    )
    vib_res = await ts_db.execute(vib_stmt)
    vib_rows = list(vib_res.scalars().all())

    if is_downsampled and total_points > actual_max_points:
        step = max(1, total_points // actual_max_points)
        vib_rows = vib_rows[::step]

    data_points = []
    actual_times = []
    for r in vib_rows:
        dp = {
            "time": r.time,
            "acceleration_x": float(r.acceleration_x) if r.acceleration_x is not None else None,
            "acceleration_y": float(r.acceleration_y) if r.acceleration_y is not None else None,
            "acceleration_z": float(r.acceleration_z) if r.acceleration_z is not None else None,
            "velocity_x": float(r.velocity_x) if r.velocity_x is not None else None,
            "velocity_y": float(r.velocity_y) if r.velocity_y is not None else None,
            "velocity_z": float(r.velocity_z) if r.velocity_z is not None else None,
            "temperature": float(r.temperature) if r.temperature is not None else None,
        }
        data_points.append(dp)
        actual_times.append(r.time)

    actual_start = min(actual_times) if actual_times else valid_time_start
    actual_end = max(actual_times) if actual_times else valid_time_end

    return {
        "turbine_id": turbine_id,
        "sensor_id": sensor_id,
        "time_range": {"start_time": actual_start, "end_time": actual_end},
        "sample_rate": sample_rate,
        "total_points": int(total_points),
        "returned_points": len(data_points),
        "downsampled": is_downsampled,
        "downsample_ratio": float(ratio),
        "speed_filtered": speed_filtered,
        "data": data_points,
    }


async def query_speed(
    ts_db: AsyncSession,
    turbine_id: str,
    shaft_id: Optional[str],
    start_time: datetime,
    end_time: datetime,
) -> Dict[str, Any]:
    if end_time <= start_time:
        raise BusinessException(ErrorCode.QUERY_TIME_RANGE_INVALID)

    conds = [
        RotationSpeed.turbine_id == turbine_id,
        RotationSpeed.time >= start_time,
        RotationSpeed.time <= end_time,
    ]
    if shaft_id:
        conds.append(RotationSpeed.shaft_id == shaft_id)

    speed_stmt = (
        select(RotationSpeed)
        .where(and_(*conds))
        .order_by(RotationSpeed.time.asc())
    )
    speed_res = await ts_db.execute(speed_stmt)
    speed_rows = list(speed_res.scalars().all())

    if not speed_rows:
        raise BusinessException(ErrorCode.QUERY_NO_DATA, "转速数据为空")

    values = [float(r.speed_rpm) for r in speed_rows]
    data_points = [
        {"time": r.time, "speed_rpm": float(r.speed_rpm), "shaft_id": r.shaft_id}
        for r in speed_rows
    ]
    actual_start = speed_rows[0].time
    actual_end = speed_rows[-1].time

    return {
        "turbine_id": turbine_id,
        "shaft_id": shaft_id,
        "time_range": {"start_time": actual_start, "end_time": actual_end},
        "total_points": len(speed_rows),
        "min_speed": float(min(values)),
        "max_speed": float(max(values)),
        "mean_speed": float(np.mean(values)),
        "data": data_points,
    }


async def query_spectrums(
    ts_db: AsyncSession,
    turbine_id: Optional[str],
    gear_id: Optional[str],
    start_time: datetime,
    end_time: datetime,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Dict[str, Any]], int, int]:
    if end_time <= start_time:
        raise BusinessException(ErrorCode.QUERY_TIME_RANGE_INVALID)

    conds = [
        OrderSpectrum.time >= start_time,
        OrderSpectrum.time <= end_time,
    ]
    if turbine_id:
        conds.append(OrderSpectrum.turbine_id == turbine_id)
    if gear_id:
        conds.append(OrderSpectrum.gear_id == gear_id)

    count_stmt = select(func.count()).select_from(
        select(OrderSpectrum).where(and_(*conds)).subquery()
    )
    total = await ts_db.scalar(count_stmt) or 0

    stmt = (
        select(OrderSpectrum)
        .where(and_(*conds))
        .order_by(OrderSpectrum.time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    res = await ts_db.execute(stmt)
    rows = list(res.scalars().all())

    items = []
    for r in rows:
        items.append({
            "spectrum_id": r.id,
            "turbine_id": r.turbine_id,
            "gear_id": r.gear_id,
            "analysis_start": r.analysis_start,
            "analysis_end": r.analysis_end,
            "max_order": float(r.max_order),
            "order_resolution": float(r.order_resolution),
            "resampled_count": int(r.resampled_count),
            "status": int(r.status),
            "created_at": r.created_at,
        })

    total_pages = math.ceil(total / page_size) if page_size > 0 else 0
    return items, int(total), total_pages


async def query_fault_features(
    ts_db: AsyncSession,
    turbine_id: Optional[str],
    gear_id: Optional[str],
    start_time: datetime,
    end_time: datetime,
    min_severity: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Dict[str, Any]], int, int]:
    if end_time <= start_time:
        raise BusinessException(ErrorCode.QUERY_TIME_RANGE_INVALID)

    conds = [
        GearFaultFeatures.time >= start_time,
        GearFaultFeatures.time <= end_time,
    ]
    if turbine_id:
        conds.append(GearFaultFeatures.turbine_id == turbine_id)
    if gear_id:
        conds.append(GearFaultFeatures.gear_id == gear_id)
    if min_severity is not None:
        conds.append(GearFaultFeatures.fault_severity >= int(min_severity))

    count_stmt = select(func.count()).select_from(
        select(GearFaultFeatures).where(and_(*conds)).subquery()
    )
    total = await ts_db.scalar(count_stmt) or 0

    stmt = (
        select(GearFaultFeatures)
        .where(and_(*conds))
        .order_by(GearFaultFeatures.time.desc(), GearFaultFeatures.fault_severity.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    res = await ts_db.execute(stmt)
    rows = list(res.scalars().all())

    items = []
    for r in rows:
        items.append({
            "feature_id": r.id,
            "spectrum_id": r.spectrum_id,
            "turbine_id": r.turbine_id,
            "gear_id": r.gear_id,
            "mesh_order": float(r.mesh_order),
            "mesh_amplitude": float(r.mesh_amplitude),
            "sideband_spacing": float(r.sideband_spacing),
            "max_sideband_amp": float(r.max_sideband_amp),
            "sideband_energy": float(r.sideband_energy),
            "kurtosis": float(r.kurtosis) if r.kurtosis is not None else None,
            "crest_factor": float(r.crest_factor) if r.crest_factor is not None else None,
            "rms_value": float(r.rms_value) if r.rms_value is not None else None,
            "peak_value": float(r.peak_value) if r.peak_value is not None else None,
            "fault_severity": int(r.fault_severity),
            "status": int(r.status),
            "created_at": r.created_at,
        })

    total_pages = math.ceil(total / page_size) if page_size > 0 else 0
    return items, int(total), total_pages


async def query_upload_batches(
    ts_db: AsyncSession,
    turbine_id: Optional[str] = None,
    status: Optional[int] = None,
    started_from: Optional[datetime] = None,
    started_to: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Dict[str, Any]], int, int]:
    conds = []
    if turbine_id:
        conds.append(UploadBatch.turbine_id == turbine_id)
    if status is not None:
        conds.append(UploadBatch.status == int(status))
    if started_from:
        conds.append(UploadBatch.started_at >= started_from)
    if started_to:
        conds.append(UploadBatch.started_at <= started_to)

    stmt = select(UploadBatch)
    if conds:
        stmt = stmt.where(and_(*conds))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await ts_db.scalar(count_stmt) or 0

    stmt = stmt.order_by(UploadBatch.started_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    res = await ts_db.execute(stmt)
    rows = list(res.scalars().all())

    items = [
        {
            "batch_id": r.id,
            "turbine_id": r.turbine_id,
            "sensor_id": r.sensor_id,
            "shaft_id": r.shaft_id,
            "total_chunks": int(r.total_chunks),
            "uploaded_chunks": int(r.uploaded_chunks),
            "total_samples": int(r.total_samples),
            "sample_rate": int(r.sample_rate),
            "waveform_format": r.waveform_format,
            "has_speed_data": bool(r.has_speed_data) if r.has_speed_data is not None else False,
            "start_time": r.start_time,
            "status": int(r.status),
            "file_name": r.file_name,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "error_message": r.error_message,
        }
        for r in rows
    ]

    total_pages = math.ceil(total / page_size) if page_size > 0 else 0
    return items, int(total), total_pages


async def query_turbine_ledger(
    mysql_db: AsyncSession,
    turbine_id: Optional[str] = None,
    farm_code: Optional[str] = None,
) -> List[Dict[str, Any]]:
    stmt = select(WindTurbine)
    conds = []
    if turbine_id:
        conds.append(WindTurbine.turbine_id == turbine_id)
    if farm_code:
        conds.append(WindTurbine.farm_code == farm_code)
    if conds:
        stmt = stmt.where(and_(*conds))

    res = await mysql_db.execute(stmt.order_by(WindTurbine.turbine_id))
    turbines = list(res.scalars().all())

    results = []
    for t in turbines:
        gb_count_stmt = select(func.count(Gearbox.id)).where(Gearbox.turbine_id == t.turbine_id)
        sn_count_stmt = select(func.count(Sensor.id)).where(Sensor.turbine_id == t.turbine_id)
        farm_name_stmt = select(WindFarm.farm_name).where(WindFarm.farm_code == t.farm_code)

        gb_count = await mysql_db.scalar(gb_count_stmt) or 0
        sn_count = await mysql_db.scalar(sn_count_stmt) or 0
        farm_name = await mysql_db.scalar(farm_name_stmt)

        results.append({
            "turbine_id": t.turbine_id,
            "turbine_name": t.turbine_name,
            "farm_code": t.farm_code,
            "farm_name": farm_name,
            "model": t.model,
            "manufacturer": t.manufacturer,
            "rated_power": float(t.rated_power) if t.rated_power else None,
            "rated_speed": float(t.rated_speed) if t.rated_speed else None,
            "min_speed": float(t.min_speed) if t.min_speed else None,
            "max_speed": float(t.max_speed) if t.max_speed else None,
            "status": int(t.status),
            "gearbox_count": int(gb_count),
            "sensor_count": int(sn_count),
        })
    return results


async def query_gearbox_ledger(
    mysql_db: AsyncSession,
    turbine_id: Optional[str] = None,
    gear_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    stmt = select(Gearbox)
    conds = []
    if turbine_id:
        conds.append(Gearbox.turbine_id == turbine_id)
    if gear_id:
        conds.append(Gearbox.gear_id == gear_id)
    if conds:
        stmt = stmt.where(and_(*conds))

    res = await mysql_db.execute(stmt.order_by(Gearbox.gear_id))
    gearboxes = list(res.scalars().all())

    results = []
    for g in gearboxes:
        gp_count_stmt = select(func.count(GearParam.id)).where(GearParam.gear_id == g.gear_id)
        gp_count = await mysql_db.scalar(gp_count_stmt) or 0
        t_name_stmt = select(WindTurbine.turbine_name).where(WindTurbine.turbine_id == g.turbine_id)
        t_name = await mysql_db.scalar(t_name_stmt)

        gp_stmt = (
            select(GearParam)
            .where(GearParam.gear_id == g.gear_id)
            .order_by(GearParam.stage, GearParam.id)
        )
        gp_res = await mysql_db.execute(gp_stmt)
        gp_list = list(gp_res.scalars().all())

        results.append({
            "gear_id": g.gear_id,
            "gear_name": g.gear_name,
            "turbine_id": g.turbine_id,
            "turbine_name": t_name,
            "model": g.model,
            "manufacturer": g.manufacturer,
            "gear_ratio": float(g.gear_ratio) if g.gear_ratio else 0.0,
            "stages": int(g.stages),
            "status": int(g.status),
            "gear_params_count": int(gp_count),
            "gear_params": [
                {
                    "gear_param_id": gp.gear_param_id,
                    "gear_id": gp.gear_id,
                    "stage": int(gp.stage),
                    "gear_type": gp.gear_type,
                    "position": gp.position,
                    "teeth_count": int(gp.teeth_count),
                    "module": float(gp.module) if gp.module else 0.0,
                    "pitch_diameter": float(gp.pitch_diameter) if gp.pitch_diameter else 0.0,
                    "mesh_order_ref": float(gp.teeth_count),
                }
                for gp in gp_list
            ],
        })
    return results
