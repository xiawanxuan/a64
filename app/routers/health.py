from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.database.timescaledb import get_timescale_session
from app.database.mysql import get_mysql_session
from app.config.settings import get_settings

router = APIRouter(prefix="/health", tags=["健康检查"])

settings = get_settings()


@router.get(
    "/ping",
    summary="服务存活检查",
    description="最基本的健康检查端点，确认HTTP服务正常运行"
)
async def ping():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.app_name,
        "version": settings.app_version
    }


@router.get(
    "/database",
    summary="数据库连通性检查",
    description="检查 TimescaleDB 和 MySQL 两个数据库的连接状态"
)
async def check_database(
    ts_db: AsyncSession = Depends(get_timescale_session),
    mysql_db: AsyncSession = Depends(get_mysql_session),
):
    ts_status = "ok"
    mysql_status = "ok"
    ts_latency_ms = 0.0
    mysql_latency_ms = 0.0

    try:
        t0 = datetime.utcnow()
        await ts_db.execute(text("SELECT 1"))
        ts_latency_ms = (datetime.utcnow() - t0).total_seconds() * 1000
    except Exception as e:
        ts_status = f"error: {e}"

    try:
        t0 = datetime.utcnow()
        await mysql_db.execute(text("SELECT 1"))
        mysql_latency_ms = (datetime.utcnow() - t0).total_seconds() * 1000
    except Exception as e:
        mysql_status = f"error: {e}"

    overall = "ok" if ts_status == "ok" and mysql_status == "ok" else "degraded"

    return {
        "status": overall,
        "timestamp": datetime.utcnow().isoformat(),
        "databases": {
            "timescaledb": {
                "status": ts_status,
                "latency_ms": round(ts_latency_ms, 2)
            },
            "mysql": {
                "status": mysql_status,
                "latency_ms": round(mysql_latency_ms, 2)
            }
        }
    }


@router.get(
    "/info",
    summary="系统信息",
    description="返回当前部署的系统配置信息（脱敏）"
)
async def system_info():
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "api_prefix": settings.api_prefix,
        "debug": settings.debug,
        "host": settings.host,
        "port": settings.port,
        "batch_insert_size": settings.batch_insert_size,
        "max_chunk_size_mb": settings.max_chunk_size_mb,
        "hyperparams_config": str(settings.hyperparams_config)
    }
