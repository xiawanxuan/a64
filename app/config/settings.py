from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class TimescaleDBConfig(BaseSettings):
    host: str = Field(default="localhost", alias="TIMESCALEDB_HOST")
    port: int = Field(default=5432, alias="TIMESCALEDB_PORT")
    user: str = Field(default="postgres", alias="TIMESCALEDB_USER")
    password: str = Field(default="postgres", alias="TIMESCALEDB_PASSWORD")
    database: str = Field(default="vibration_db", alias="TIMESCALEDB_DATABASE")
    pool_size: int = Field(default=20, alias="TIMESCALEDB_POOL_SIZE")
    max_overflow: int = Field(default=30, alias="TIMESCALEDB_MAX_OVERFLOW")

    @property
    def async_url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def sync_url(self) -> str:
        return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class MySQLConfig(BaseSettings):
    host: str = Field(default="localhost", alias="MYSQL_HOST")
    port: int = Field(default=3306, alias="MYSQL_PORT")
    user: str = Field(default="root", alias="MYSQL_USER")
    password: str = Field(default="root", alias="MYSQL_PASSWORD")
    database: str = Field(default="turbine_ledger", alias="MYSQL_DATABASE")
    pool_size: int = Field(default=20, alias="MYSQL_POOL_SIZE")
    max_overflow: int = Field(default=30, alias="MYSQL_MAX_OVERFLOW")

    @property
    def async_url(self) -> str:
        return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def sync_url(self) -> str:
        return f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    app_name: str = Field(default="风电场设备诊断平台", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    debug: bool = Field(default=False, alias="APP_DEBUG")
    host: str = Field(default="0.0.0.0", alias="APP_HOST")
    port: int = Field(default=8000, alias="APP_PORT")
    api_prefix: str = Field(default="/api/v1", alias="API_PREFIX")

    timescaledb: TimescaleDBConfig = TimescaleDBConfig()
    mysql: MySQLConfig = MySQLConfig()

    chunk_upload_dir: str = Field(default="./data/chunks", alias="CHUNK_UPLOAD_DIR")
    failed_analysis_dir: str = Field(default="./data/failed_analysis", alias="FAILED_ANALYSIS_DIR")

    max_chunk_size_mb: int = Field(default=100, alias="MAX_CHUNK_SIZE_MB")
    batch_insert_size: int = Field(default=10000, alias="BATCH_INSERT_SIZE")

    hyperparams_config_path: str = Field(default="./config/hyperparams.yaml", alias="HYPERPARAMS_CONFIG_PATH")

    log_dir: str = Field(default="./logs", alias="LOG_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # 故障回调推送配置
    fault_callback_enabled: bool = Field(default=False, alias="FAULT_CALLBACK_ENABLED")
    fault_callback_url: str = Field(default="", alias="FAULT_CALLBACK_URL")
    fault_callback_timeout_sec: int = Field(default=10, alias="FAULT_CALLBACK_TIMEOUT_SEC")
    fault_callback_max_retries: int = Field(default=3, alias="FAULT_CALLBACK_MAX_RETRIES")
    fault_callback_retry_interval_sec: int = Field(default=2, alias="FAULT_CALLBACK_RETRY_INTERVAL_SEC")
    fault_callback_auth_header: str = Field(default="", alias="FAULT_CALLBACK_AUTH_HEADER")
    fault_callback_auth_token: str = Field(default="", alias="FAULT_CALLBACK_AUTH_TOKEN")


@lru_cache()
def get_settings() -> AppSettings:
    return AppSettings()
