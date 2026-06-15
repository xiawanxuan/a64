-- ============================================================
-- 风电场设备诊断平台 - TimescaleDB 时序数据库初始化脚本
-- 存储：原始振动波形、转速时序、阶次分析结果、故障特征
-- ============================================================

-- 创建数据库（需手动执行）
-- CREATE DATABASE vibration_db;

-- 扩展 TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. 原始振动波形数据表 (Hypertable)
-- ============================================================
CREATE TABLE IF NOT EXISTS vibration_waveform (
    time            TIMESTAMPTZ         NOT NULL,
    turbine_id      VARCHAR(64)         NOT NULL,
    sensor_id       VARCHAR(64)         NOT NULL,
    sample_rate     INTEGER             NOT NULL,
    acceleration_x  DOUBLE PRECISION,
    acceleration_y  DOUBLE PRECISION,
    acceleration_z  DOUBLE PRECISION,
    velocity_x      DOUBLE PRECISION,
    velocity_y      DOUBLE PRECISION,
    velocity_z      DOUBLE PRECISION,
    temperature     DOUBLE PRECISION,
    upload_batch_id UUID,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('vibration_waveform', 'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 hour'
);

CREATE INDEX IF NOT EXISTS idx_vibration_turbine_time
    ON vibration_waveform (turbine_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_vibration_sensor_time
    ON vibration_waveform (sensor_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_vibration_batch
    ON vibration_waveform (upload_batch_id);

-- ============================================================
-- 2. 转速时序数据表 (Hypertable)
-- ============================================================
CREATE TABLE IF NOT EXISTS rotation_speed (
    time            TIMESTAMPTZ         NOT NULL,
    turbine_id      VARCHAR(64)         NOT NULL,
    shaft_id        VARCHAR(64)         NOT NULL,
    speed_rpm       DOUBLE PRECISION    NOT NULL,
    upload_batch_id UUID,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('rotation_speed', 'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '10 minutes'
);

CREATE INDEX IF NOT EXISTS idx_speed_turbine_time
    ON rotation_speed (turbine_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_speed_shaft_time
    ON rotation_speed (shaft_id, time DESC);

-- ============================================================
-- 3. 阶次谱分析结果表 (Hypertable)
-- ============================================================
CREATE TABLE IF NOT EXISTS order_spectrum (
    id              UUID                PRIMARY KEY DEFAULT uuid_generate_v4(),
    time            TIMESTAMPTZ         NOT NULL,
    turbine_id      VARCHAR(64)         NOT NULL,
    gear_id         VARCHAR(64)         NOT NULL,
    analysis_start  TIMESTAMPTZ         NOT NULL,
    analysis_end    TIMESTAMPTZ         NOT NULL,
    order_values    DOUBLE PRECISION[]  NOT NULL,
    amplitude_values DOUBLE PRECISION[] NOT NULL,
    max_order       DOUBLE PRECISION    NOT NULL,
    order_resolution DOUBLE PRECISION   NOT NULL,
    resampled_count INTEGER             NOT NULL,
    status          SMALLINT            NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('order_spectrum', 'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

CREATE INDEX IF NOT EXISTS idx_spectrum_turbine_time
    ON order_spectrum (turbine_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_spectrum_gear_time
    ON order_spectrum (gear_id, time DESC);

-- ============================================================
-- 4. 齿轮故障特征提取结果表 (Hypertable)
-- ============================================================
CREATE TABLE IF NOT EXISTS gear_fault_features (
    id                  UUID                PRIMARY KEY DEFAULT uuid_generate_v4(),
    time                TIMESTAMPTZ         NOT NULL,
    turbine_id          VARCHAR(64)         NOT NULL,
    gear_id             VARCHAR(64)         NOT NULL,
    spectrum_id         UUID                REFERENCES order_spectrum(id),
    mesh_order          DOUBLE PRECISION    NOT NULL,
    mesh_amplitude      DOUBLE PRECISION    NOT NULL,
    sideband_orders     DOUBLE PRECISION[]  NOT NULL,
    sideband_amplitudes DOUBLE PRECISION[] NOT NULL,
    sideband_spacing    DOUBLE PRECISION    NOT NULL,
    max_sideband_amp    DOUBLE PRECISION    NOT NULL,
    sideband_energy     DOUBLE PRECISION    NOT NULL,
    kurtosis            DOUBLE PRECISION,
    crest_factor        DOUBLE PRECISION,
    rms_value           DOUBLE PRECISION,
    peak_value          DOUBLE PRECISION,
    fault_severity      SMALLINT            NOT NULL DEFAULT 0,
    status              SMALLINT            NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('gear_fault_features', 'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

CREATE INDEX IF NOT EXISTS idx_features_turbine_time
    ON gear_fault_features (turbine_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_features_gear_time
    ON gear_fault_features (gear_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_features_severity
    ON gear_fault_features (fault_severity);

-- ============================================================
-- 5. 上传批次记录表
-- ============================================================
CREATE TABLE IF NOT EXISTS upload_batches (
    id              UUID                PRIMARY KEY DEFAULT uuid_generate_v4(),
    turbine_id      VARCHAR(64)         NOT NULL,
    sensor_id       VARCHAR(64),
    shaft_id        VARCHAR(64),
    total_chunks    INTEGER             NOT NULL,
    uploaded_chunks INTEGER             NOT NULL DEFAULT 0,
    total_samples   BIGINT              NOT NULL DEFAULT 0,
    sample_rate     INTEGER             NOT NULL,
    waveform_format VARCHAR(32),
    has_speed_data  BOOLEAN             DEFAULT FALSE,
    start_time      TIMESTAMPTZ,
    status          SMALLINT            NOT NULL DEFAULT 0,
    file_name       VARCHAR(256),
    started_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_batches_turbine
    ON upload_batches (turbine_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_batches_turbine_status
    ON upload_batches (turbine_id, status);
CREATE INDEX IF NOT EXISTS idx_batches_status
    ON upload_batches (status);

-- ============================================================
-- 6. 分析失败留存记录表
-- ============================================================
CREATE TABLE IF NOT EXISTS failed_analysis_records (
    id              UUID                PRIMARY KEY DEFAULT uuid_generate_v4(),
    turbine_id      VARCHAR(64)         NOT NULL,
    gear_id         VARCHAR(64),
    analysis_type   VARCHAR(64)         NOT NULL,
    batch_id        UUID,
    waveform_file   VARCHAR(512)        NOT NULL,
    speed_file      VARCHAR(512),
    error_type      VARCHAR(128)        NOT NULL,
    error_message   TEXT                NOT NULL,
    stack_trace     TEXT,
    params          JSONB,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_failed_turbine
    ON failed_analysis_records (turbine_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_failed_type
    ON failed_analysis_records (error_type);

-- ============================================================
-- 7. 压缩策略
-- ============================================================
ALTER TABLE vibration_waveform SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'turbine_id, sensor_id',
    timescaledb.compress_orderby = 'time'
);

ALTER TABLE rotation_speed SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'turbine_id, shaft_id',
    timescaledb.compress_orderby = 'time'
);

SELECT add_compression_policy('vibration_waveform', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_compression_policy('rotation_speed', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_compression_policy('order_spectrum', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_compression_policy('gear_fault_features', INTERVAL '30 days', if_not_exists => TRUE);

-- ============================================================
-- 8. 数据保留策略
-- ============================================================
SELECT add_retention_policy('vibration_waveform', INTERVAL '365 days', if_not_exists => TRUE);
SELECT add_retention_policy('rotation_speed', INTERVAL '365 days', if_not_exists => TRUE);
SELECT add_retention_policy('order_spectrum', INTERVAL '730 days', if_not_exists => TRUE);
SELECT add_retention_policy('gear_fault_features', INTERVAL '730 days', if_not_exists => TRUE);
