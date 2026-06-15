from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.timescaledb import get_timescale_session
from app.database.mysql import get_mysql_session
from app.schemas.query import (
    WaveformQueryRequest, WaveformQueryResponse, WaveformDataPoint,
    SpeedQueryRequest, SpeedQueryResponse, SpeedDataPoint,
    SpectrumQueryRequest, FeatureQueryRequest,
    TurbineLedgerInfo, GearboxLedgerInfo, GearParamInfo, SensorInfo,
    BatchQueryRequest, UploadBatchInfo,
    FailedRecordQueryRequest, FailedRecordInfo
)
from app.schemas.upload import UploadStatus
from app.schemas.common import PaginatedResponse, PageParams
from app.services import query_service
from app.services.failure_preservation import query_failed_records
from app.core.exceptions import BusinessException
from app.core.error_codes import ErrorCode

router = APIRouter(prefix="/query", tags=["多维度查询"])


# ==================== 原始波形查询 ====================

@router.post(
    "/waveform",
    response_model=WaveformQueryResponse,
    summary="查询原始振动波形",
    description=(
        "按风机编号、传感器、时间范围、转速区间查询原始振动波形；\n"
        "返回数据超过 max_points 时自动降采样，返回实际采样率与降采样比率"
    )
)
async def query_waveform_data(
    req: WaveformQueryRequest,
    ts_db: AsyncSession = Depends(get_timescale_session),
):
    speed_range = req.speed_range
    min_speed = speed_range.min_speed if speed_range else None
    max_speed = speed_range.max_speed if speed_range else None

    result = await query_service.query_waveform(
        ts_db=ts_db,
        turbine_id=req.turbine_id,
        sensor_id=req.sensor_id,
        start_time=req.time_range.start_time,
        end_time=req.time_range.end_time,
        min_speed=min_speed,
        max_speed=max_speed,
        max_points=req.max_points,
        downsample=req.downsample,
    )

    data_points = [
        WaveformDataPoint(**dp) for dp in result.get("data", [])
    ]

    return WaveformQueryResponse(
        turbine_id=result["turbine_id"],
        sensor_id=result.get("sensor_id"),
        time_range=result["time_range"],
        sample_rate=int(result["sample_rate"]),
        total_points=int(result["total_points"]),
        returned_points=int(result["returned_points"]),
        downsampled=bool(result.get("downsampled", False)),
        downsample_ratio=float(result.get("downsample_ratio", 1.0)),
        data=data_points,
    )


# ==================== 转速数据查询 ====================

@router.post(
    "/speed",
    response_model=SpeedQueryResponse,
    summary="查询主轴转速序列",
    description="按风机编号、轴编号、时间范围查询转速时序数据，返回最小/最大/平均转速统计"
)
async def query_speed_data(
    req: SpeedQueryRequest,
    ts_db: AsyncSession = Depends(get_timescale_session),
):
    result = await query_service.query_speed(
        ts_db=ts_db,
        turbine_id=req.turbine_id,
        shaft_id=req.shaft_id,
        start_time=req.time_range.start_time,
        end_time=req.time_range.end_time,
    )

    data_points = [
        SpeedDataPoint(**dp) for dp in result.get("data", [])
    ]

    return SpeedQueryResponse(
        turbine_id=result["turbine_id"],
        shaft_id=result.get("shaft_id"),
        time_range=result["time_range"],
        total_points=int(result["total_points"]),
        min_speed=float(result["min_speed"]),
        max_speed=float(result["max_speed"]),
        mean_speed=float(result["mean_speed"]),
        data=data_points,
    )


# ==================== 阶次谱查询 ====================

@router.post(
    "/spectrums",
    response_model=PaginatedResponse,
    summary="分页查询阶次谱分析历史",
    description="按风机、齿轮箱、时间范围分页查询已完成的阶次谱分析记录"
)
async def query_spectrum_history(
    req: SpectrumQueryRequest,
    ts_db: AsyncSession = Depends(get_timescale_session),
):
    page = req.page.page
    page_size = req.page.page_size

    items, total, total_pages = await query_service.query_spectrums(
        ts_db=ts_db,
        turbine_id=req.turbine_id,
        gear_id=req.gear_id,
        start_time=req.time_range.start_time,
        end_time=req.time_range.end_time,
        page=page,
        page_size=page_size,
    )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ==================== 故障特征查询 ====================

@router.post(
    "/fault-features",
    response_model=PaginatedResponse,
    summary="分页查询故障特征提取历史",
    description="按风机、齿轮箱、严重度阈值、时间范围分页查询故障特征，支持按严重度过滤"
)
async def query_fault_feature_history(
    req: FeatureQueryRequest,
    ts_db: AsyncSession = Depends(get_timescale_session),
):
    page = req.page.page
    page_size = req.page.page_size
    min_sev = int(req.min_severity) if req.min_severity is not None else None

    items, total, total_pages = await query_service.query_fault_features(
        ts_db=ts_db,
        turbine_id=req.turbine_id,
        gear_id=req.gear_id,
        start_time=req.time_range.start_time,
        end_time=req.time_range.end_time,
        min_severity=min_sev,
        page=page,
        page_size=page_size,
    )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ==================== 上传批次查询 ====================

@router.post(
    "/upload-batches",
    response_model=PaginatedResponse,
    summary="分页查询上传批次",
    description="按风机、状态、时间范围分页查询波形上传批次记录"
)
async def query_upload_batch_history(
    req: BatchQueryRequest,
    ts_db: AsyncSession = Depends(get_timescale_session),
):
    page = req.page.page
    page_size = req.page.page_size

    items, total, total_pages = await query_service.query_upload_batches(
        ts_db=ts_db,
        turbine_id=req.turbine_id,
        status=req.status,
        started_from=req.started_from,
        started_to=req.started_to,
        page=page,
        page_size=page_size,
    )

    batch_items = []
    for it in items:
        batch_items.append(UploadBatchInfo(
            batch_id=it["batch_id"],
            turbine_id=it["turbine_id"],
            sensor_id=it.get("sensor_id"),
            shaft_id=it.get("shaft_id"),
            total_chunks=int(it["total_chunks"]),
            uploaded_chunks=int(it["uploaded_chunks"]),
            total_samples=int(it["total_samples"]),
            sample_rate=int(it["sample_rate"]),
            waveform_format=it.get("waveform_format"),
            has_speed_data=bool(it.get("has_speed_data", False)),
            start_time=it.get("start_time"),
            status=UploadStatus(int(it["status"])),
            file_name=it.get("file_name"),
            started_at=it["started_at"],
            completed_at=it.get("completed_at"),
            error_message=it.get("error_message"),
        ))

    return PaginatedResponse(
        items=[bi.model_dump() for bi in batch_items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ==================== 台账查询：风机 ====================

@router.get(
    "/turbines",
    response_model=List[TurbineLedgerInfo],
    summary="查询风机台账列表",
    description="返回所有风机台账的聚合信息（含关联齿轮箱和传感器数量）"
)
async def list_turbine_ledger(
    farm_code: Optional[str] = Query(None, description="风电场编码过滤"),
    turbine_id: Optional[str] = Query(None, description="风机编号精确匹配"),
    mysql_db: AsyncSession = Depends(get_mysql_session),
):
    items = await query_service.query_turbine_ledger(
        mysql_db, farm_code=farm_code, turbine_id=turbine_id
    )
    return [
        TurbineLedgerInfo(
            turbine_id=it["turbine_id"],
            turbine_name=it["turbine_name"],
            farm_code=it["farm_code"],
            farm_name=it.get("farm_name"),
            model=it.get("model"),
            manufacturer=it.get("manufacturer"),
            rated_power=float(it["rated_power"]) if it.get("rated_power") is not None else None,
            rated_speed=float(it["rated_speed"]) if it.get("rated_speed") is not None else None,
            min_speed=float(it["min_speed"]) if it.get("min_speed") is not None else None,
            max_speed=float(it["max_speed"]) if it.get("max_speed") is not None else None,
            status=int(it["status"]),
            gearbox_count=int(it.get("gearbox_count", 0)),
            sensor_count=int(it.get("sensor_count", 0)),
        )
        for it in items
    ]


# ==================== 台账查询：齿轮箱 ====================

@router.get(
    "/gearboxes",
    response_model=List[GearboxLedgerInfo],
    summary="查询齿轮箱台账列表",
    description="按风机编号过滤查询齿轮箱台账，含各级齿轮参数数量统计"
)
async def list_gearbox_ledger(
    turbine_id: Optional[str] = Query(None, description="所属风机编号过滤"),
    gear_id: Optional[str] = Query(None, description="齿轮箱编号精确匹配"),
    mysql_db: AsyncSession = Depends(get_mysql_session),
):
    items = await query_service.query_gearbox_ledger(
        mysql_db, turbine_id=turbine_id, gear_id=gear_id
    )
    return [
        GearboxLedgerInfo(
            gear_id=it["gear_id"],
            gear_name=it["gear_name"],
            turbine_id=it["turbine_id"],
            turbine_name=it.get("turbine_name"),
            model=it.get("model"),
            manufacturer=it.get("manufacturer"),
            gear_ratio=float(it["gear_ratio"]),
            stages=int(it["stages"]),
            status=int(it["status"]),
            gear_params_count=int(it.get("gear_params_count", 0)),
        )
        for it in items
    ]


# ==================== 台账查询：齿轮参数 ====================

@router.get(
    "/gear-params/{gear_id}",
    response_model=List[GearParamInfo],
    summary="查询指定齿轮箱的齿轮参数",
    description="按齿轮箱编号查询所有传动级的齿轮参数（齿数、模数、节圆直径、啮合阶次等）"
)
async def list_gear_params(
    gear_id: str,
    mysql_db: AsyncSession = Depends(get_mysql_session),
):
    from app.models.mysql_models import GearParam
    from sqlalchemy import select, and_

    stmt = (
        select(GearParam)
        .where(GearParam.gear_id == gear_id)
        .order_by(GearParam.stage, GearParam.id)
    )
    res = await mysql_db.execute(stmt)
    rows = list(res.scalars().all())

    return [
        GearParamInfo(
            gear_param_id=r.id,
            gear_id=r.gear_id,
            stage=int(r.stage),
            gear_type=r.gear_type,
            position=r.position,
            teeth_count=int(r.teeth_count),
            module=float(r.module or 0),
            pitch_diameter=float(r.pitch_diameter or 0),
            mesh_order_ref=float(r.mesh_order_ref or 0),
        )
        for r in rows
    ]


# ==================== 台账查询：传感器 ====================

@router.get(
    "/sensors",
    response_model=List[SensorInfo],
    summary="查询传感器台账列表",
    description="按风机或齿轮箱过滤查询传感器台账，含类型、测量轴、安装位置等信息"
)
async def list_sensors(
    turbine_id: Optional[str] = Query(None, description="所属风机编号过滤"),
    gear_id: Optional[str] = Query(None, description="所属齿轮箱编号过滤"),
    mysql_db: AsyncSession = Depends(get_mysql_session),
):
    from app.models.mysql_models import Sensor
    from sqlalchemy import select, and_

    conds = []
    if turbine_id:
        conds.append(Sensor.turbine_id == turbine_id)
    if gear_id:
        conds.append(Sensor.gear_id == gear_id)

    stmt = select(Sensor)
    if conds:
        stmt = stmt.where(and_(*conds))
    stmt = stmt.order_by(Sensor.turbine_id, Sensor.id)

    res = await mysql_db.execute(stmt)
    rows = list(res.scalars().all())

    return [
        SensorInfo(
            sensor_id=r.sensor_id,
            sensor_name=r.sensor_name,
            turbine_id=r.turbine_id,
            gear_id=r.gear_id,
            sensor_type=r.sensor_type,
            measure_axis=r.measure_axis,
            mount_position=r.mount_position,
            sample_rate=int(r.sample_rate or 0),
            status=int(r.status),
        )
        for r in rows
    ]


# ==================== 失败分析记录查询 ====================

@router.post(
    "/failed-records",
    response_model=PaginatedResponse,
    summary="分页查询分析失败留存记录",
    description="查询失败分析的留存记录，包含原始数据文件路径、错误类型、调用参数快照"
)
async def list_failed_analysis_records(
    req: FailedRecordQueryRequest,
    ts_db: AsyncSession = Depends(get_timescale_session),
):
    page = req.page.page
    page_size = req.page.page_size
    time_range = req.time_range
    start_time = time_range.start_time if time_range else None
    end_time = time_range.end_time if time_range else None

    items, total = await query_failed_records(
        db=ts_db,
        turbine_id=req.turbine_id,
        gear_id=req.gear_id,
        analysis_type=req.analysis_type,
        error_type=req.error_type,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )

    record_items = [
        FailedRecordInfo(
            id=r.id,
            turbine_id=r.turbine_id,
            gear_id=r.gear_id,
            analysis_type=r.analysis_type,
            batch_id=r.upload_batch_id,
            waveform_file=r.waveform_file,
            speed_file=r.speed_file,
            error_type=r.error_type,
            error_message=r.error_message,
            params=r.params,
            created_at=r.created_at,
        ).model_dump()
        for r in items
    ]

    import math
    total_pages = math.ceil(total / page_size) if page_size > 0 else 0

    return PaginatedResponse(
        items=record_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
