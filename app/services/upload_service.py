import os
import uuid
import aiofiles
import numpy as np
from typing import Tuple, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
from loguru import logger
from sqlalchemy import select, update, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.models.timescale_models import VibrationWaveform, RotationSpeed, UploadBatch
from app.core.exceptions import BusinessException
from app.core.error_codes import ErrorCode
from app.services.waveform_parser import parse_binary_waveform

settings = get_settings()


def _get_chunk_dir(batch_id: uuid.UUID) -> Path:
    chunk_dir = Path(settings.chunk_upload_dir) / str(batch_id)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    return chunk_dir


async def create_upload_batch(
    db: AsyncSession,
    turbine_id: str,
    sensor_id: str,
    total_chunks: int,
    total_samples: int,
    sample_rate: int,
    file_name: Optional[str] = None,
    shaft_id: Optional[str] = None,
    waveform_format: Optional[str] = None,
    has_speed_data: bool = False,
    start_time: Optional[datetime] = None,
) -> UploadBatch:
    try:
        batch = UploadBatch(
            id=uuid.uuid4(),
            turbine_id=turbine_id,
            sensor_id=sensor_id,
            shaft_id=shaft_id,
            total_chunks=total_chunks,
            uploaded_chunks=0,
            total_samples=total_samples,
            sample_rate=sample_rate,
            waveform_format=waveform_format,
            has_speed_data=has_speed_data,
            start_time=start_time,
            status=0,
            file_name=file_name,
            started_at=datetime.utcnow(),
        )
        db.add(batch)
        await db.flush()
        _get_chunk_dir(batch.id)
        logger.info(
            f"创建上传批次 batch_id={batch.id} | turbine={turbine_id} "
            f"| chunks={total_chunks} | samples={total_samples}"
        )
        return batch
    except BusinessException:
        raise
    except Exception as e:
        raise BusinessException(
            ErrorCode.DB_TIMESCALE_ERROR,
            f"创建上传批次失败: {e}",
            cause=e
        )


async def save_chunk_file(
    batch_id: uuid.UUID,
    chunk_index: int,
    chunk_data: bytes,
) -> Path:
    if chunk_index < 0:
        raise BusinessException(
            ErrorCode.UPLOAD_CHUNK_INVALID,
            f"分片索引无效: {chunk_index}"
        )

    max_size_bytes = settings.max_chunk_size_mb * 1024 * 1024
    if len(chunk_data) > max_size_bytes:
        raise BusinessException(
            ErrorCode.UPLOAD_FILE_TOO_LARGE,
            f"分片大小 {len(chunk_data)} bytes 超过限制 {max_size_bytes} bytes"
        )

    chunk_dir = _get_chunk_dir(batch_id)
    chunk_path = chunk_dir / f"chunk_{chunk_index:08d}.bin"

    try:
        async with aiofiles.open(str(chunk_path), "wb") as f:
            await f.write(chunk_data)
        logger.debug(f"保存分片: {chunk_path.name}, size={len(chunk_data)}")
        return chunk_path
    except Exception as e:
        raise BusinessException(
            ErrorCode.UPLOAD_CHUNK_INVALID,
            f"分片保存失败: {e}",
            cause=e
        )


async def update_batch_chunk_count(
    db: AsyncSession,
    batch_id: uuid.UUID,
    chunk_index: int,
) -> Tuple[UploadBatch, int, bool]:
    result = await db.execute(
        select(UploadBatch).where(UploadBatch.id == batch_id).with_for_update()
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise BusinessException(ErrorCode.UPLOAD_BATCH_NOT_FOUND)

    new_count = max(batch.uploaded_chunks, chunk_index + 1)
    if new_count > batch.total_chunks:
        raise BusinessException(
            ErrorCode.UPLOAD_CHUNK_OUT_OF_ORDER,
            f"分片索引 {chunk_index} 超过总数 {batch.total_chunks}"
        )

    batch.uploaded_chunks = new_count
    batch.status = 1 if new_count < batch.total_chunks else 2
    await db.flush()

    is_complete = (new_count >= batch.total_chunks)
    return batch, new_count, is_complete


async def merge_chunks_to_binary(
    batch_id: uuid.UUID,
    total_chunks: int,
) -> bytes:
    chunk_dir = _get_chunk_dir(batch_id)
    chunks_exist = sorted(chunk_dir.glob("chunk_*.bin"))
    if len(chunks_exist) < total_chunks:
        raise BusinessException(
            ErrorCode.UPLOAD_IN_PROGRESS,
            f"缺失分片: 期望 {total_chunks}, 实际 {len(chunks_exist)}"
        )

    merged = bytearray()
    try:
        for i in range(total_chunks):
            chunk_path = chunk_dir / f"chunk_{i:08d}.bin"
            if not chunk_path.exists():
                raise BusinessException(
                    ErrorCode.UPLOAD_CHUNK_OUT_OF_ORDER,
                    f"分片文件缺失: {chunk_path.name}"
                )
            async with aiofiles.open(str(chunk_path), "rb") as f:
                data = await f.read()
                merged.extend(data)
        logger.info(f"合并分片完成 batch_id={batch_id}, total={len(merged)} bytes")
        return bytes(merged)
    except BusinessException:
        raise
    except Exception as e:
        raise BusinessException(
            ErrorCode.UPLOAD_MERGE_FAILED,
            f"分片合并失败: {e}",
            cause=e
        )


async def batch_insert_waveform(
    db: AsyncSession,
    times_list: list,
    turbine_id: str,
    sensor_id: str,
    sample_rate: int,
    channel_data: Dict[str, np.ndarray],
    batch_id: Optional[uuid.UUID] = None,
) -> int:
    if not times_list:
        return 0

    batch_size = settings.batch_insert_size
    total_inserted = 0
    total_samples = len(times_list)

    channels = list(channel_data.keys())
    has_x = "acceleration_x" in channels
    has_y = "acceleration_y" in channels
    has_z = "acceleration_z" in channels

    try:
        for start in range(0, total_samples, batch_size):
            end = min(start + batch_size, total_samples)
            n = end - start
            records = []
            for i in range(n):
                idx = start + i
                rec = {
                    "time": times_list[idx],
                    "turbine_id": turbine_id,
                    "sensor_id": sensor_id,
                    "sample_rate": sample_rate,
                    "upload_batch_id": batch_id,
                }
                if has_x:
                    rec["acceleration_x"] = float(channel_data["acceleration_x"][idx])
                if has_y:
                    rec["acceleration_y"] = float(channel_data["acceleration_y"][idx])
                if has_z:
                    rec["acceleration_z"] = float(channel_data["acceleration_z"][idx])
                records.append(rec)

            if records:
                await db.execute(
                    VibrationWaveform.__table__.insert().values(records),
                    execution_options={"populate_existing": False}
                )
                total_inserted += len(records)

        logger.info(
            f"批量写入波形: turbine={turbine_id}, sensor={sensor_id}, "
            f"points={total_inserted}/{total_samples}"
        )
        return total_inserted

    except Exception as e:
        raise BusinessException(
            ErrorCode.DB_TIMESCALE_ERROR,
            f"波形批量写入失败: {e}",
            cause=e
        )


async def batch_insert_speed(
    db: AsyncSession,
    times_list: list,
    turbine_id: str,
    shaft_id: str,
    speed_rpm: np.ndarray,
    batch_id: Optional[uuid.UUID] = None,
) -> int:
    if not times_list or len(speed_rpm) == 0:
        return 0

    batch_size = settings.batch_insert_size
    total_inserted = 0
    n_total = min(len(times_list), len(speed_rpm))

    try:
        for start in range(0, n_total, batch_size):
            end = min(start + batch_size, n_total)
            n = end - start
            records = []
            for i in range(n):
                idx = start + i
                records.append({
                    "time": times_list[idx],
                    "turbine_id": turbine_id,
                    "shaft_id": shaft_id,
                    "speed_rpm": float(speed_rpm[idx]),
                    "upload_batch_id": batch_id,
                })

            if records:
                await db.execute(
                    RotationSpeed.__table__.insert().values(records)
                )
                total_inserted += len(records)

        logger.info(
            f"批量写入转速: turbine={turbine_id}, shaft={shaft_id}, points={total_inserted}"
        )
        return total_inserted

    except Exception as e:
        raise BusinessException(
            ErrorCode.DB_TIMESCALE_ERROR,
            f"转速批量写入失败: {e}",
            cause=e
        )


async def set_batch_status(
    db: AsyncSession,
    batch_id: uuid.UUID,
    status: int,
    error_message: Optional[str] = None,
) -> None:
    updates = {"status": status}
    if status in (4, 5):
        updates["completed_at"] = datetime.utcnow()
    if error_message:
        updates["error_message"] = error_message

    await db.execute(
        update(UploadBatch)
        .where(UploadBatch.id == batch_id)
        .values(**updates)
    )


async def cleanup_chunk_files(batch_id: uuid.UUID) -> None:
    chunk_dir = Path(settings.chunk_upload_dir) / str(batch_id)
    try:
        if chunk_dir.exists():
            for f in chunk_dir.glob("*"):
                f.unlink(missing_ok=True)
            chunk_dir.rmdir()
            logger.debug(f"已清理分片目录: {chunk_dir}")
    except Exception as e:
        logger.warning(f"清理分片文件失败 batch_id={batch_id}: {e}")
