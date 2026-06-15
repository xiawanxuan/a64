-- ============================================================
-- 风电场设备诊断平台 - MySQL 台账数据库初始化脚本
-- 存储：风机台账、齿轮箱参数、传感器配置
-- ============================================================

-- 创建数据库（需手动执行）
-- CREATE DATABASE turbine_ledger DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE turbine_ledger;

-- ============================================================
-- 1. 风电场信息表
-- ============================================================
CREATE TABLE IF NOT EXISTS wind_farms (
    id              BIGINT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    farm_code       VARCHAR(64)     NOT NULL UNIQUE COMMENT '风电场编码',
    farm_name       VARCHAR(128)    NOT NULL COMMENT '风电场名称',
    location        VARCHAR(256)    COMMENT '地理位置',
    installed_capacity DECIMAL(10,2) COMMENT '装机容量(MW)',
    turbine_count   INT             DEFAULT 0 COMMENT '风机数量',
    commissioned_at DATE            COMMENT '投运日期',
    operator        VARCHAR(128)    COMMENT '运维单位',
    status          TINYINT         NOT NULL DEFAULT 1 COMMENT '状态:0停用1启用',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_farm_code (farm_code),
    INDEX idx_farm_name (farm_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='风电场信息表';

-- ============================================================
-- 2. 风机台账表
-- ============================================================
CREATE TABLE IF NOT EXISTS wind_turbines (
    id              BIGINT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    turbine_id      VARCHAR(64)     NOT NULL UNIQUE COMMENT '风机唯一编号',
    turbine_name    VARCHAR(128)    NOT NULL COMMENT '风机名称',
    farm_id         BIGINT          NOT NULL COMMENT '所属风电场ID',
    farm_code       VARCHAR(64)     NOT NULL COMMENT '风电场编码',
    model           VARCHAR(128)    COMMENT '风机型号',
    manufacturer    VARCHAR(128)    COMMENT '制造商',
    rated_power     DECIMAL(10,2)   COMMENT '额定功率(kW)',
    hub_height      DECIMAL(8,2)    COMMENT '轮毂高度(m)',
    rotor_diameter  DECIMAL(8,2)    COMMENT '叶轮直径(m)',
    rated_speed     DECIMAL(8,2)    COMMENT '额定转速(rpm)',
    min_speed       DECIMAL(8,2)    COMMENT '最低转速(rpm)',
    max_speed       DECIMAL(8,2)    COMMENT '最高转速(rpm)',
    location_lat    DECIMAL(10,6)   COMMENT '纬度',
    location_lng    DECIMAL(10,6)   COMMENT '经度',
    installed_at    DATE            COMMENT '安装日期',
    commissioned_at DATE            COMMENT '投运日期',
    status          TINYINT         NOT NULL DEFAULT 1 COMMENT '状态:0停运1运行2维护3故障',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_turbine_id (turbine_id),
    INDEX idx_farm_id (farm_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='风机台账表';

-- ============================================================
-- 3. 齿轮箱信息表
-- ============================================================
CREATE TABLE IF NOT EXISTS gearboxes (
    id              BIGINT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    gear_id         VARCHAR(64)     NOT NULL UNIQUE COMMENT '齿轮箱唯一编号',
    gear_name       VARCHAR(128)    NOT NULL COMMENT '齿轮箱名称',
    turbine_id      VARCHAR(64)     NOT NULL COMMENT '所属风机编号',
    model           VARCHAR(128)    COMMENT '齿轮箱型号',
    manufacturer    VARCHAR(128)    COMMENT '制造商',
    gear_ratio      DECIMAL(10,4)   NOT NULL COMMENT '齿轮箱总传动比',
    stages          TINYINT         NOT NULL DEFAULT 2 COMMENT '传动级数',
    lubricant_type  VARCHAR(64)     COMMENT '润滑油型号',
    lubricant_capacity DECIMAL(8,2) COMMENT '润滑油容量(L)',
    installed_at    DATE            COMMENT '安装日期',
    status          TINYINT         NOT NULL DEFAULT 1 COMMENT '状态:0停用1正常2预警3故障',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_gear_id (gear_id),
    INDEX idx_turbine_id (turbine_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='齿轮箱信息表';

-- ============================================================
-- 4. 齿轮参数表（各级齿轮详细参数）
-- ============================================================
CREATE TABLE IF NOT EXISTS gear_params (
    id              BIGINT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    gear_param_id   VARCHAR(64)     NOT NULL UNIQUE COMMENT '齿轮参数唯一ID',
    gear_id         VARCHAR(64)     NOT NULL COMMENT '所属齿轮箱编号',
    stage           TINYINT         NOT NULL COMMENT '传动级:1第一级,2第二级,3第三级',
    gear_type       VARCHAR(32)     NOT NULL COMMENT '齿轮类型:sun太阳轮,planetary行星轮,ring内齿圈,helical斜齿',
    position        VARCHAR(32)     NOT NULL COMMENT '位置:input输入级,intermediate中间级,output输出级',
    teeth_count     INT             NOT NULL COMMENT '齿数Z',
    module          DECIMAL(10,4)   NOT NULL COMMENT '模数m(mm)',
    pressure_angle  DECIMAL(6,2)    NOT NULL DEFAULT 20.0 COMMENT '压力角(°)',
    helix_angle     DECIMAL(6,2)    DEFAULT 0 COMMENT '螺旋角(°)',
    pitch_diameter  DECIMAL(12,4)   NOT NULL COMMENT '节圆直径(mm)',
    face_width      DECIMAL(8,2)    COMMENT '齿宽(mm)',
    material        VARCHAR(64)     COMMENT '材料',
    hardness        VARCHAR(64)     COMMENT '硬度',
    mesh_frequency  DECIMAL(14,6)   COMMENT '啮合频率基值',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_gear_id (gear_id),
    INDEX idx_gear_param_id (gear_param_id),
    INDEX idx_stage (stage)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='齿轮参数表';

-- ============================================================
-- 5. 轴系参数表
-- ============================================================
CREATE TABLE IF NOT EXISTS shafts (
    id              BIGINT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    shaft_id        VARCHAR(64)     NOT NULL UNIQUE COMMENT '轴唯一编号',
    shaft_name      VARCHAR(128)    NOT NULL COMMENT '轴名称',
    turbine_id      VARCHAR(64)     NOT NULL COMMENT '所属风机编号',
    gear_id         VARCHAR(64)     COMMENT '所属齿轮箱编号',
    position        VARCHAR(32)     NOT NULL COMMENT '位置:low_speed低速轴,intermediate中间轴,high_speed高速轴',
    rated_speed     DECIMAL(10,2)   COMMENT '额定转速(rpm)',
    diameter        DECIMAL(8,2)    COMMENT '轴直径(mm)',
    length          DECIMAL(10,2)   COMMENT '轴长度(mm)',
    material        VARCHAR(64)     COMMENT '材料',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_shaft_id (shaft_id),
    INDEX idx_turbine_id (turbine_id),
    INDEX idx_gear_id (gear_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='轴系参数表';

-- ============================================================
-- 6. 传感器配置表
-- ============================================================
CREATE TABLE IF NOT EXISTS sensors (
    id              BIGINT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    sensor_id       VARCHAR(64)     NOT NULL UNIQUE COMMENT '传感器唯一编号',
    sensor_name     VARCHAR(128)    NOT NULL COMMENT '传感器名称',
    turbine_id      VARCHAR(64)     NOT NULL COMMENT '所属风机编号',
    gear_id         VARCHAR(64)     COMMENT '所属齿轮箱编号',
    sensor_type     VARCHAR(32)     NOT NULL COMMENT '传感器类型:acc加速度,vel速度,disp位移,temp温度',
    measure_axis    VARCHAR(8)      NOT NULL DEFAULT 'Z' COMMENT '测量轴:X/Y/Z',
    mount_position  VARCHAR(64)     COMMENT '安装位置描述',
    sensitivity     DECIMAL(12,6)   COMMENT '灵敏度',
    frequency_range_min DECIMAL(12,4) COMMENT '频率范围下限(Hz)',
    frequency_range_max DECIMAL(12,4) COMMENT '频率范围上限(Hz)',
    sample_rate     INT             DEFAULT 25600 COMMENT '默认采样率(Hz)',
    installed_at    DATE            COMMENT '安装日期',
    status          TINYINT         NOT NULL DEFAULT 1 COMMENT '状态:0停用1正常2维护3故障',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_sensor_id (sensor_id),
    INDEX idx_turbine_id (turbine_id),
    INDEX idx_gear_id (gear_id),
    INDEX idx_type (sensor_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='传感器配置表';

-- ============================================================
-- 7. 轴承参数表
-- ============================================================
CREATE TABLE IF NOT EXISTS bearings (
    id              BIGINT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    bearing_id      VARCHAR(64)     NOT NULL UNIQUE COMMENT '轴承唯一编号',
    bearing_name    VARCHAR(128)    NOT NULL COMMENT '轴承名称',
    turbine_id      VARCHAR(64)     NOT NULL COMMENT '所属风机编号',
    gear_id         VARCHAR(64)     COMMENT '所属齿轮箱编号',
    shaft_id        VARCHAR(64)     COMMENT '所属轴编号',
    model           VARCHAR(128)    COMMENT '轴承型号',
    manufacturer    VARCHAR(128)    COMMENT '制造商',
    roller_count    INT             COMMENT '滚动体数量',
    roller_diameter DECIMAL(10,4)   COMMENT '滚动体直径(mm)',
    pitch_diameter  DECIMAL(12,4)   COMMENT '节圆直径(mm)',
    contact_angle   DECIMAL(6,2)    COMMENT '接触角(°)',
    bpfo            DECIMAL(12,6)   COMMENT '外圈故障特征频率系数',
    bpfi            DECIMAL(12,6)   COMMENT '内圈故障特征频率系数',
    bsf             DECIMAL(12,6)   COMMENT '滚动体自转故障特征频率系数',
    ftf             DECIMAL(12,6)   COMMENT '保持架故障特征频率系数',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_bearing_id (bearing_id),
    INDEX idx_turbine_id (turbine_id),
    INDEX idx_gear_id (gear_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='轴承参数表';

-- ============================================================
-- 插入示例数据
-- ============================================================
INSERT IGNORE INTO wind_farms (farm_code, farm_name, location, installed_capacity, turbine_count, operator) VALUES
('WF-001', '华北风电场一号', '河北省张家口市', 100.00, 50, '华能新能源有限公司'),
('WF-002', '华东风电场A区', '江苏省盐城市', 200.00, 100, '国家电投江苏分公司');

INSERT IGNORE INTO wind_turbines (turbine_id, turbine_name, farm_id, farm_code, model, manufacturer, rated_power, rated_speed, min_speed, max_speed, status) VALUES
('WT-A001', 'A区1号风机', 1, 'WF-001', 'GW121-2.0MW', '金风科技', 2000.00, 17.2, 6.0, 18.0, 1),
('WT-A002', 'A区2号风机', 1, 'WF-001', 'GW121-2.0MW', '金风科技', 2000.00, 17.2, 6.0, 18.0, 1),
('WT-B001', 'B区1号风机', 2, 'WF-002', 'SEW131-2.5MW', '上海电气', 2500.00, 14.8, 5.0, 16.0, 1);

INSERT IGNORE INTO gearboxes (gear_id, gear_name, turbine_id, model, manufacturer, gear_ratio, stages, status) VALUES
('GB-WT-A001-01', 'A001风机主齿轮箱', 'WT-A001', 'WP4000-2.0MW', '重齿集团', 109.3284, 2, 1),
('GB-WT-A002-01', 'A002风机主齿轮箱', 'WT-A002', 'WP4000-2.0MW', '重齿集团', 109.3284, 2, 1),
('GB-WT-B001-01', 'B001风机主齿轮箱', 'WT-B001', 'WPU4500-2.5MW', '南高齿', 115.6720, 3, 1);

INSERT IGNORE INTO gear_params (gear_param_id, gear_id, stage, gear_type, position, teeth_count, module, pressure_angle, helix_angle, pitch_diameter, face_width) VALUES
('GP001-GB001', 'GB-WT-A001-01', 1, 'planetary', 'input', 41, 12.0000, 20.0, 8.0, 492.0000, 220.00),
('GP002-GB001', 'GB-WT-A001-01', 1, 'sun', 'input', 21, 12.0000, 20.0, 8.0, 252.0000, 220.00),
('GP003-GB001', 'GB-WT-A001-01', 1, 'ring', 'input', 83, 12.0000, 20.0, 8.0, 996.0000, 220.00),
('GP004-GB001', 'GB-WT-A001-01', 2, 'helical', 'intermediate', 22, 10.0000, 20.0, 12.0, 220.0000, 180.00),
('GP005-GB001', 'GB-WT-A001-01', 2, 'helical', 'output', 113, 10.0000, 20.0, 12.0, 1130.0000, 180.00),
('GP001-GB002', 'GB-WT-A002-01', 1, 'planetary', 'input', 41, 12.0000, 20.0, 8.0, 492.0000, 220.00),
('GP002-GB002', 'GB-WT-A002-01', 1, 'sun', 'input', 21, 12.0000, 20.0, 8.0, 252.0000, 220.00),
('GP003-GB002', 'GB-WT-A002-01', 1, 'ring', 'input', 83, 12.0000, 20.0, 8.0, 996.0000, 220.00),
('GP004-GB002', 'GB-WT-A002-01', 2, 'helical', 'intermediate', 22, 10.0000, 20.0, 12.0, 220.0000, 180.00),
('GP005-GB002', 'GB-WT-A002-01', 2, 'helical', 'output', 113, 10.0000, 20.0, 12.0, 1130.0000, 180.00);

INSERT IGNORE INTO shafts (shaft_id, shaft_name, turbine_id, gear_id, position, rated_speed) VALUES
('SH-WT-A001-LS', 'A001低速轴', 'WT-A001', 'GB-WT-A001-01', 'low_speed', 17.2),
('SH-WT-A001-IS', 'A001中间轴', 'WT-A001', 'GB-WT-A001-01', 'intermediate', 625.8),
('SH-WT-A001-HS', 'A001高速轴', 'WT-A001', 'GB-WT-A001-01', 'high_speed', 1878.5);

INSERT IGNORE INTO sensors (sensor_id, sensor_name, turbine_id, gear_id, sensor_type, measure_axis, mount_position, sample_rate, status) VALUES
('SEN-A001-ACC-01', 'A001齿轮箱输入端Z向加速度', 'WT-A001', 'GB-WT-A001-01', 'acc', 'Z', '行星架输入侧轴承座', 25600, 1),
('SEN-A001-ACC-02', 'A001齿轮箱输出端Z向加速度', 'WT-A001', 'GB-WT-A001-01', 'acc', 'Z', '高速轴输出侧轴承座', 25600, 1),
('SEN-A001-ACC-03', 'A001齿轮箱中间X向加速度', 'WT-A001', 'GB-WT-A001-01', 'acc', 'X', '中间齿轮轴承座', 25600, 1),
('SEN-A001-TMP-01', 'A001齿轮箱油温', 'WT-A001', 'GB-WT-A001-01', 'temp', 'Z', '润滑油池', 10, 1);
