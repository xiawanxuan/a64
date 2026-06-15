import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config.settings import get_settings
from app.core.exceptions import setup_exception_handlers
from app.core.middleware import setup_middleware
from app.core.logger import setup_logger
from app.database.timescaledb import init_timescaledb
from app.database.mysql import init_mysql
from app.routers import vibration_upload, order_analysis, query, health

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        setup_logger(settings.log_dir, settings.log_level)
        for directory in [settings.chunk_upload_dir, settings.failed_analysis_dir, settings.log_dir]:
            Path(directory).mkdir(parents=True, exist_ok=True)
        await init_timescaledb()
        await init_mysql()
        logger.info(f"{settings.app_name} v{settings.app_version} 启动成功")
        yield
    except Exception as e:
        logger.error(f"应用启动失败: {e}")
        raise
    finally:
        logger.info("应用正在关闭...")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="风电场设备诊断平台 - 齿轮箱变转速振动波形分析与故障特征提取系统",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        contact={
            "name": "风电场设备诊断平台开发团队",
            "email": "support@windfarm-diagnosis.com"
        },
        license_info={
            "name": "Apache 2.0",
            "url": "https://www.apache.org/licenses/LICENSE-2.0.html"
        }
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    setup_middleware(app)
    setup_exception_handlers(app)

    api_prefix = settings.api_prefix
    app.include_router(health.router, prefix=api_prefix, tags=["健康检查"])
    app.include_router(vibration_upload.router, prefix=api_prefix, tags=["振动波形接入"])
    app.include_router(order_analysis.router, prefix=api_prefix, tags=["阶次分析与故障特征提取"])
    app.include_router(query.router, prefix=api_prefix, tags=["多维度查询"])

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
