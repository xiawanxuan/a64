from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database.timescaledb import get_timescale_session
from app.database.mysql import get_mysql_session
from app.schemas.analysis import (
    OrderAnalysisRequest, OrderAnalysisResponse,
    OrderSpectrumData, GearFaultFeatureData,
    AnalysisStatus, FaultSeverity
)
from app.services.order_analysis_service import run_order_analysis
from app.core.exceptions import BusinessException
from app.core.error_codes import ErrorCode

router = APIRouter(prefix="/analysis", tags=["阶次分析与故障特征提取"])


@router.post(
    "/order-spectrum",
    response_model=OrderAnalysisResponse,
    summary="执行阶次跟踪分析",
    description=(
        "根据风机编号、齿轮箱、时间范围从时序库拉取原始振动波形与转速数据；\n"
        "完成：转速平滑→角度域重采样→阶次谱(STFT)分解→各级齿轮啮合阶次搜索\n"
        "→边频带幅值提取→多指标故障严重度评估，最终返回完整分析结果并入库"
    )
)
async def execute_order_analysis(
    req: OrderAnalysisRequest,
    ts_db: AsyncSession = Depends(get_timescale_session),
    mysql_db: AsyncSession = Depends(get_mysql_session),
):
    speed_range = req.speed_range
    min_speed = speed_range.min_speed if speed_range else None
    max_speed = speed_range.max_speed if speed_range else None

    result = await run_order_analysis(
        ts_db=ts_db,
        mysql_db=mysql_db,
        turbine_id=req.turbine_id,
        gear_id=req.gear_id,
        sensor_id=req.sensor_id,
        shaft_id=req.shaft_id,
        start_time=req.time_range.start_time,
        end_time=req.time_range.end_time,
        min_speed=min_speed,
        max_speed=max_speed,
        target_stage=req.stage,
    )
    await ts_db.commit()

    status = result.get("status", AnalysisStatus.COMPLETED)
    message = result.get("message")

    spectrum_raw = result.get("spectrum")
    spectrum_data = None
    if spectrum_raw:
        order_vals = spectrum_raw.get("order_axis", [])
        amp_vals = spectrum_raw.get("spectrum", [])
        spectrum_data = OrderSpectrumData(
            spectrum_id=spectrum_raw.get("id"),
            turbine_id=req.turbine_id,
            gear_id=req.gear_id,
            analysis_start=req.time_range.start_time,
            analysis_end=req.time_range.end_time,
            order_values=[float(x) for x in order_vals],
            amplitude_values=[float(x) for x in amp_vals],
            max_order=float(spectrum_raw.get("max_order", 0)),
            order_resolution=float(spectrum_raw.get("order_resolution", 0)),
            resampled_count=int(spectrum_raw.get("resampled_count", 0)),
            created_at=spectrum_raw.get("created_at"),
        )

    features_raw = result.get("fault_features", [])
    fault_features = []
    for fr in features_raw:
        fault_features.append(GearFaultFeatureData(
            feature_id=fr.get("id"),
            spectrum_id=fr.get("spectrum_id"),
            turbine_id=req.turbine_id,
            gear_id=req.gear_id,
            gear_param_id=fr.get("gear_param_id"),
            stage=int(fr.get("stage", 0)),
            gear_type=fr.get("gear_type", ""),
            teeth_count=int(fr.get("teeth_count", 0)),
            mesh_order=float(fr.get("mesh_order", 0)),
            mesh_amplitude=float(fr.get("mesh_amplitude", 0)),
            sideband_orders=[float(x) for x in fr.get("sideband_orders", [])],
            sideband_amplitudes=[float(x) for x in fr.get("sideband_amplitudes", [])],
            sideband_spacing=float(fr.get("sideband_spacing", 0)),
            max_sideband_amp=float(fr.get("max_sideband_amp", 0)),
            sideband_energy=float(fr.get("sideband_energy", 0)),
            kurtosis=float(fr["kurtosis"]) if fr.get("kurtosis") is not None else None,
            crest_factor=float(fr["crest_factor"]) if fr.get("crest_factor") is not None else None,
            rms_value=float(fr["rms_value"]) if fr.get("rms_value") is not None else None,
            peak_value=float(fr["peak_value"]) if fr.get("peak_value") is not None else None,
            fault_severity=FaultSeverity(int(fr.get("fault_severity", 0))),
            diagnosis_note=fr.get("diagnosis_note"),
            created_at=fr.get("created_at"),
        ))

    return OrderAnalysisResponse(
        turbine_id=req.turbine_id,
        gear_id=req.gear_id,
        status=AnalysisStatus(int(status)),
        time_range=req.time_range,
        mean_speed_rpm=float(result.get("mean_speed_rpm", 0)),
        valid_duration_sec=float(result.get("valid_duration_sec", 0)),
        spectrum=spectrum_data,
        fault_features=fault_features,
        overall_severity=FaultSeverity(int(result.get("overall_severity", 0))),
        analysis_cost_ms=float(result.get("analysis_cost_ms", 0)),
        message=message,
    )
