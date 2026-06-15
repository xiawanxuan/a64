import uuid
from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database.timescaledb import get_timescale_session
from app.schemas.upload import (
    UploadInitRequest, UploadInitResponse,
    UploadChunkResponse, UploadCompleteRequest, UploadCompleteResponse,
    UploadStatus
)
from app.services import upload_service
from app.services.waveform_parser import parse_binary_waveform
from app.core.exceptions import BusinessException
from app.core.error_codes import ErrorCode

router = APIRouter(prefix="/upload", tags=["振动波形接入"])


@router.post(
    "/init",
    response_model=UploadInitResponse,
    summary="初始化分片上传批次",
    description="在上传二进制波形分片前，先调用此接口创建上传批次，获取 batch_id 用于后续分片上传"
)
async def init_upload(
    req: UploadInitRequest,
    db: AsyncSession = Depends(get_timescale_session),
):
    batch = await upload_service.create_upload_batch(
        db=db,
        turbine_id=req.turbine_id,
        sensor_id=req.sensor_id,
        total_chunks=req.total_chunks,
        total_samples=req.total_samples,
        sample_rate=req.sample_rate,
        file_name=req.file_name,
        shaft_id=req.shaft_id,
        waveform_format=req.waveform_format,
        has_speed_data=req.has_speed_data,
        start_time=req.start_time,
    )
    await db.commit()
    return UploadInitResponse(
        batch_id=batch.id,
        turbine_id=batch.turbine_id,
        sensor_id=req.sensor_id,
        total_chunks=batch.total_chunks,
        sample_rate=batch.sample_rate,
        status=UploadStatus(batch.status),
        created_at=batch.started_at,
    )


@router.post(
    "/chunk",
    response_model=UploadChunkResponse,
    summary="上传单个分片",
    description="以 multipart/form-data 方式上传二进制波形的一个分片；chunk_index 从 0 开始"
)
async def upload_chunk(
    batch_id: uuid.UUID = Form(..., description="上传批次ID"),
    chunk_index: int = Form(..., ge=0, description="分片索引(从0开始)"),
    chunk_data: UploadFile = File(..., description="分片二进制内容"),
    db: AsyncSession = Depends(get_timescale_session),
):
    data_bytes = await chunk_data.read()
    if not data_bytes:
        raise BusinessException(ErrorCode.UPLOAD_CHUNK_INVALID, "分片内容为空")

    await upload_service.save_chunk_file(batch_id, chunk_index, data_bytes)
    batch, uploaded_count, completed = await upload_service.update_batch_chunk_count(
        db, batch_id, chunk_index
    )
    await db.commit()

    return UploadChunkResponse(
        batch_id=batch.id,
        chunk_index=chunk_index,
        uploaded_chunks=uploaded_count,
        total_chunks=batch.total_chunks,
        completed=completed,
        status=UploadStatus(batch.status),
    )


@router.post(
    "/complete",
    response_model=UploadCompleteResponse,
    summary="完成上传并解析入库",
    description="所有分片上传完成后，调用此接口触发分片合并、二进制解析和批量写入时序数据库"
)
async def complete_upload(
    req: UploadCompleteRequest,
    db: AsyncSession = Depends(get_timescale_session),
):
    from app.models.timescale_models import UploadBatch
    from sqlalchemy import select

    result = await db.execute(
        select(UploadBatch).where(UploadBatch.id == req.batch_id).with_for_update()
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise BusinessException(ErrorCode.UPLOAD_BATCH_NOT_FOUND)

    if batch.status < int(UploadStatus.COMPLETED):
        raise BusinessException(
            ErrorCode.UPLOAD_IN_PROGRESS,
            f"上传未完成, 当前状态={batch.status}, 已上传={batch.uploaded_chunks}/{batch.total_chunks}"
        )

    await upload_service.set_batch_status(db, batch.id, int(UploadStatus.PROCESSING))
    await db.flush()
    await db.commit()

    waveform_inserted = 0
    speed_inserted = 0
    try:
        merged_bytes = await upload_service.merge_chunks_to_binary(
            batch.id, batch.total_chunks
        )

        start_ts = batch.started_at.replace(tzinfo=timezone.utc).timestamp() \
            if batch.started_at.tzinfo is None else batch.started_at.timestamp()

        parsed = parse_binary_waveform(
            binary_data=merged_bytes,
            sample_rate=batch.sample_rate,
            total_samples=batch.total_samples,
            start_timestamp=start_ts,
        )

        channel_data = {}
        if len(parsed.get("acceleration_x", [])) > 0:
            channel_data["acceleration_x"] = parsed["acceleration_x"]
        if len(parsed.get("acceleration_y", [])) > 0:
            channel_data["acceleration_y"] = parsed["acceleration_y"]
        if len(parsed.get("acceleration_z", [])) > 0:
            channel_data["acceleration_z"] = parsed["acceleration_z"]

        resolved_sensor_id = batch.sensor_id or f"S-{batch.turbine_id}-DEFAULT"
        waveform_inserted = await upload_service.batch_insert_waveform(
            db=db,
            times_list=parsed["time_vector"],
            turbine_id=batch.turbine_id,
            sensor_id=resolved_sensor_id,
            sample_rate=batch.sample_rate,
            channel_data=channel_data,
            batch_id=batch.id,
        )

        speed_data = parsed.get("speed_rpm", [])
        speed_times = parsed.get("speed_times", [])
        if len(speed_data) > 0 and len(speed_times) > 0:
            import numpy as np
            resolved_shaft_id = batch.shaft_id or f"SH-{batch.turbine_id}-DEFAULT"
            speed_inserted = await upload_service.batch_insert_speed(
                db=db,
                times_list=speed_times,
                turbine_id=batch.turbine_id,
                shaft_id=resolved_shaft_id,
                speed_rpm=np.array(speed_data, dtype=np.float64),
                batch_id=batch.id,
            )

        await upload_service.set_batch_status(db, batch.id, int(UploadStatus.PROCESSED))
        await db.commit()

        await upload_service.cleanup_chunk_files(batch.id)

    except BusinessException as be:
        await upload_service.set_batch_status(
            db, batch.id, int(UploadStatus.FAILED), str(be)
        )
        await db.commit()
        raise
    except Exception as e:
        logger.exception(f"解析并写入批次 {batch.id} 失败")
        await upload_service.set_batch_status(
            db, batch.id, int(UploadStatus.FAILED), f"{type(e).__name__}: {e}"
        )
        await db.commit()
        raise BusinessException(
            ErrorCode.UPLOAD_PARSE_FAILED,
            f"波形解析失败: {e}",
            cause=e
        )

    return UploadCompleteResponse(
        batch_id=batch.id,
        status=UploadStatus.PROCESSED,
        total_samples=batch.total_samples,
        waveform_points_inserted=waveform_inserted,
        speed_points_inserted=speed_inserted,
    )


@router.get(
    "/batch/{batch_id}",
    summary="查询上传批次状态",
    description="根据 batch_id 查询单个上传批次的详细状态与进度"
)
async def get_upload_batch(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_timescale_session),
):
    from app.models.timescale_models import UploadBatch
    from sqlalchemy import select

    result = await db.execute(
        select(UploadBatch).where(UploadBatch.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise BusinessException(ErrorCode.UPLOAD_BATCH_NOT_FOUND)

    return {
        "batch_id": batch.id,
        "turbine_id": batch.turbine_id,
        "sensor_id": batch.sensor_id,
        "shaft_id": batch.shaft_id,
        "total_chunks": batch.total_chunks,
        "uploaded_chunks": batch.uploaded_chunks,
        "total_samples": batch.total_samples,
        "sample_rate": batch.sample_rate,
        "waveform_format": batch.waveform_format,
        "has_speed_data": bool(batch.has_speed_data),
        "start_time": batch.start_time,
        "status": batch.status,
        "file_name": batch.file_name,
        "started_at": batch.started_at,
        "completed_at": batch.completed_at,
        "error_message": batch.error_message,
    }
