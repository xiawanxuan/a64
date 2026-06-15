from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from loguru import logger

from app.config.settings import get_settings

settings = get_settings()


class MySQLBase(DeclarativeBase):
    pass


mysql_engine = create_async_engine(
    settings.mysql.async_url,
    pool_size=settings.mysql.pool_size,
    max_overflow=settings.mysql.max_overflow,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.debug,
    future=True
)

AsyncMySQLSession = async_sessionmaker(
    bind=mysql_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def init_mysql():
    try:
        async with mysql_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.commit()
        logger.info("MySQL 连接池初始化成功")
    except Exception as e:
        logger.warning(f"MySQL 连接失败，应用将继续启动但数据库操作可能失败: {e}")


async def get_mysql_session() -> AsyncSession:
    async with AsyncMySQLSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
