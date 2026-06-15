import os
import gzip
import uuid
import json
import shutil
import traceback
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.config.settings import get_settings
from app.core.hyperparams import load_hyperparams
from app.models.timescale_models import FailedAnalysisRecord
from app.core.exceptions import BusinessException
from app.core.error_codes import ErrorCode

settings = get_settings()
hyperparams = load_hyperparams()


def _get_storage_dir() -> Path:
    base = Path(settings.failed_analysis_dir)
    today = datetime.utcnow().strftime("%Y/%m/%d")
    storage_dir = base / today
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def _check_storage_quota() -> None:
    fp_cfg = hyperparams.failure_preservation or {}
    if not fp_cfg.get("enabled", True):
        return

    max_bytes = float(fp_cfg.get("max_storage_gb", 100.0)) * (1024 ** 3)
    base = Path(settings.failed_analysis_dir)
    if not base.exists():
        return

    total = 0
    for f in base.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
            if total > max_bytes:
                break

    usage_pct = (total / max_bytes * 100.0) if max_bytes > 0 else 0
    cleanup_threshold = float(fp_cfg.get("cleanup_threshold", 85.0))

    if usage_pct >= cleanup_threshold:
        logger.warning(
            f"分析失败存储使用率 {usage_pct:.1f}% 超过阈值 {cleanup_threshold}%, 启动清理"
        )
        _cleanup_old_records(fp_cfg)


def _cleanup_old_records(fp_cfg: Dict[str, Any]) -> None:
    retention_days = int(fp_cfg.get("retention_days", 90))
    base = Path(settings.failed_analysis_dir)
    cutoff = datetime.utcnow().timestamp() - (retention_days * 86400)

    removed = 0
    for f in base.rglob("*"):
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                removed += 1
        except Exception:
            continue

    for d in sorted(base.rglob("*"), reverse=True):
        try:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except Exception:
            continue

    logger.info(f"清理过期分析失败记录: 删除 {removed} 个文件")


def _save_numpy_array(
    data: np.ndarray,
    base_path: Path,
    filename_prefix: str,
    compress: bool = True,
) -> str:
    fp_cfg = hyperparams.failure_preservation or {}
    fmt = fp_cfg.get("waveform_format", "npy")
    compress_alg = fp_cfg.get("compress_algorithm", "gzip")

    if fmt == "npy":
        file_path = base_path / f"{filename_prefix}.npy"
        np.save(str(file_path), data, allow_pickle=False)
        if compress and compress_alg == "gzip":
            gz_path = base_path / f"{filename_prefix}.npy.gz"
            with open(str(file_path), "rb") as f_in:
                with gzip.open(str(gz_path), "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            file_path.unlink(missing_ok=True)
            file_path = gz_path
        return str(file_path)

    if fmt == "csv":
        file_path = base_path / f"{filename_prefix}.csv"
        np.savetxt(str(file_path), data, delimiter=",")
        return str(file_path)

    if fmt == "binary":
        file_path = base_path / f"{filename_prefix}.bin"
        data.astype(np.float32).tofile(str(file_path))
        return str(file_path)

    file_path = base_path / f"{filename_prefix}.npy"
    np.save(str(file_path), data, allow_pickle=False)
    return str(file_path)


async def preserve_failed_analysis(
    db: AsyncSession,
    turbine_id: str,
    analysis_type: str,
    error: Exception,
    waveform_data: Optional[np.ndarray] = None,
    sample_rate: int = 0,
    speed_times: Optional[np.ndarray] = None,
    speed_values: Optional[np.ndarray] = None,
    gear_id: Optional[str] = None,
    batch_id: Optional[uuid.UUID] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    fp_cfg = hyperparams.failure_preservation or {}
    if not fp_cfg.get("enabled", True):
        return None

    try:
        _check_storage_quota()

        storage_dir = _get_storage_dir()
        record_id = uuid.uuid4()
        prefix = f"{record_id}_{turbine_id}_{analysis_type}"

        waveform_file = ""
        if waveform_data is not None and len(waveform_data) > 0:
            try:
                compress = bool(fp_cfg.get("compress_data", True))
                waveform_file = _save_numpy_array(
                    waveform_data, storage_dir, f"{prefix}_waveform", compress
                )
            except Exception as e:
                logger.warning(f"留存波形文件失败: {e}")
                waveform_file = ""

        speed_file = ""
        if speed_values is not None and len(speed_values) > 0:
            try:
                combined = speed_values
                if speed_times is not None and len(speed_times) == len(speed_values):
                    combined = np.column_stack([speed_times, speed_values])
                compress = bool(fp_cfg.get("compress_data", True))
                speed_file = _save_numpy_array(
                    combined, storage_dir, f"{prefix}_speed", compress
                )
            except Exception as e:
                logger.warning(f"留存转速文件失败: {e}")

        error_type = type(error).__name__
        error_message = str(error)
        stack_trace = "".join(
            traceback.format_exception(
                type(error), error, error.__traceback__
            )
        ) if error.__traceback__ else ""

        record = FailedAnalysisRecord(
            id=record_id,
            turbine_id=turbine_id,
            gear_id=gear_id,
            analysis_type=analysis_type,
            batch_id=batch_id,
            waveform_file=waveform_file or "not_saved",
            speed_file=speed_file or None,
            error_type=error_type,
            error_message=error_message[:5000],
            stack_trace=stack_trace[:10000] if stack_trace else None,
            params=json.dumps(params, ensure_ascii=False, default=str) if params else None,
            created_at=datetime.utcnow(),
        )
        db.add(record)
        await db.flush()

        logger.warning(
            f"已留存分析失败记录 id={record_id} | "
            f"turbine={turbine_id} | type={analysis_type} | "
            f"error={error_type}: {error_message[:100]}"
        )
        return str(record_id)

    except Exception as e:
        logger.error(f"分析失败留存操作异常: {e}")
        return None


async def query_failed_records(
    db: AsyncSession,
    turbine_id: Optional[str] = None,
    gear_id: Optional[str] = None,
    analysis_type: Optional[str] = None,
    error_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple:
    stmt = select(FailedAnalysisRecord)
    conditions = []

    if turbine_id:
        conditions.append(FailedAnalysisRecord.turbine_id == turbine_id)
    if gear_id:
        conditions.append(FailedAnalysisRecord.gear_id == gear_id)
    if analysis_type:
        conditions.append(FailedAnalysisRecord.analysis_type == analysis_type)
    if error_type:
        conditions.append(FailedAnalysisRecord.error_type == error_type)
    if start_time:
        conditions.append(FailedAnalysisRecord.created_at >= start_time)
    if end_time:
        conditions.append(FailedAnalysisRecord.created_at <= end_time)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    stmt = stmt.order_by(FailedAnalysisRecord.created_at.desc())
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    result = await db.execute(stmt)
    items = result.scalars().all()

    return list(items), int(total)
