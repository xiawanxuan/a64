from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, Float, DateTime, SmallInteger, Text, DECIMAL, Date, Index
from app.database.mysql import MySQLBase


class WindFarm(MySQLBase):
    __tablename__ = "wind_farms"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    farm_code = Column(String(64), unique=True, nullable=False, comment="风电场编码")
    farm_name = Column(String(128), nullable=False, comment="风电场名称")
    location = Column(String(256), comment="地理位置")
    installed_capacity = Column(DECIMAL(10, 2), comment="装机容量(MW)")
    turbine_count = Column(Integer, default=0, comment="风机数量")
    commissioned_at = Column(Date, comment="投运日期")
    operator = Column(String(128), comment="运维单位")
    status = Column(SmallInteger, nullable=False, default=1, comment="状态:0停用1启用")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_farm_code", "farm_code"),
        Index("idx_farm_name", "farm_name"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "comment": "风电场信息表"}
    )


class WindTurbine(MySQLBase):
    __tablename__ = "wind_turbines"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    turbine_id = Column(String(64), unique=True, nullable=False, comment="风机唯一编号")
    turbine_name = Column(String(128), nullable=False, comment="风机名称")
    farm_id = Column(BigInteger, nullable=False, comment="所属风电场ID")
    farm_code = Column(String(64), nullable=False, comment="风电场编码")
    model = Column(String(128), comment="风机型号")
    manufacturer = Column(String(128), comment="制造商")
    rated_power = Column(DECIMAL(10, 2), comment="额定功率(kW)")
    hub_height = Column(DECIMAL(8, 2), comment="轮毂高度(m)")
    rotor_diameter = Column(DECIMAL(8, 2), comment="叶轮直径(m)")
    rated_speed = Column(DECIMAL(8, 2), comment="额定转速(rpm)")
    min_speed = Column(DECIMAL(8, 2), comment="最低转速(rpm)")
    max_speed = Column(DECIMAL(8, 2), comment="最高转速(rpm)")
    location_lat = Column(DECIMAL(10, 6), comment="纬度")
    location_lng = Column(DECIMAL(10, 6), comment="经度")
    installed_at = Column(Date, comment="安装日期")
    commissioned_at = Column(Date, comment="投运日期")
    status = Column(SmallInteger, nullable=False, default=1, comment="状态:0停运1运行2维护3故障")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_turbine_id", "turbine_id"),
        Index("idx_farm_id", "farm_id"),
        Index("idx_status", "status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "comment": "风机台账表"}
    )


class Gearbox(MySQLBase):
    __tablename__ = "gearboxes"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    gear_id = Column(String(64), unique=True, nullable=False, comment="齿轮箱唯一编号")
    gear_name = Column(String(128), nullable=False, comment="齿轮箱名称")
    turbine_id = Column(String(64), nullable=False, comment="所属风机编号")
    model = Column(String(128), comment="齿轮箱型号")
    manufacturer = Column(String(128), comment="制造商")
    gear_ratio = Column(DECIMAL(10, 4), nullable=False, comment="齿轮箱总传动比")
    stages = Column(SmallInteger, nullable=False, default=2, comment="传动级数")
    lubricant_type = Column(String(64), comment="润滑油型号")
    lubricant_capacity = Column(DECIMAL(8, 2), comment="润滑油容量(L)")
    installed_at = Column(Date, comment="安装日期")
    status = Column(SmallInteger, nullable=False, default=1, comment="状态:0停用1正常2预警3故障")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_gear_id", "gear_id"),
        Index("idx_turbine_id", "turbine_id"),
        Index("idx_status", "status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "comment": "齿轮箱信息表"}
    )


class GearParam(MySQLBase):
    __tablename__ = "gear_params"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    gear_param_id = Column(String(64), unique=True, nullable=False, comment="齿轮参数唯一ID")
    gear_id = Column(String(64), nullable=False, comment="所属齿轮箱编号")
    stage = Column(SmallInteger, nullable=False, comment="传动级:1第一级,2第二级,3第三级")
    gear_type = Column(String(32), nullable=False, comment="齿轮类型:sun太阳轮,planetary行星轮,ring内齿圈,helical斜齿")
    position = Column(String(32), nullable=False, comment="位置:input输入级,intermediate中间级,output输出级")
    teeth_count = Column(Integer, nullable=False, comment="齿数Z")
    module = Column(DECIMAL(10, 4), nullable=False, comment="模数m(mm)")
    pressure_angle = Column(DECIMAL(6, 2), nullable=False, default=20.0, comment="压力角(°)")
    helix_angle = Column(DECIMAL(6, 2), default=0, comment="螺旋角(°)")
    pitch_diameter = Column(DECIMAL(12, 4), nullable=False, comment="节圆直径(mm)")
    face_width = Column(DECIMAL(8, 2), comment="齿宽(mm)")
    material = Column(String(64), comment="材料")
    hardness = Column(String(64), comment="硬度")
    mesh_frequency = Column(DECIMAL(14, 6), comment="啮合频率基值")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_gear_id", "gear_id"),
        Index("idx_gear_param_id", "gear_param_id"),
        Index("idx_stage", "stage"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "comment": "齿轮参数表"}
    )


class Shaft(MySQLBase):
    __tablename__ = "shafts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    shaft_id = Column(String(64), unique=True, nullable=False, comment="轴唯一编号")
    shaft_name = Column(String(128), nullable=False, comment="轴名称")
    turbine_id = Column(String(64), nullable=False, comment="所属风机编号")
    gear_id = Column(String(64), comment="所属齿轮箱编号")
    position = Column(String(32), nullable=False, comment="位置:low_speed低速轴,intermediate中间轴,high_speed高速轴")
    rated_speed = Column(DECIMAL(10, 2), comment="额定转速(rpm)")
    diameter = Column(DECIMAL(8, 2), comment="轴直径(mm)")
    length = Column(DECIMAL(10, 2), comment="轴长度(mm)")
    material = Column(String(64), comment="材料")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_shaft_id", "shaft_id"),
        Index("idx_turbine_id", "turbine_id"),
        Index("idx_gear_id", "gear_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "comment": "轴系参数表"}
    )


class Sensor(MySQLBase):
    __tablename__ = "sensors"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sensor_id = Column(String(64), unique=True, nullable=False, comment="传感器唯一编号")
    sensor_name = Column(String(128), nullable=False, comment="传感器名称")
    turbine_id = Column(String(64), nullable=False, comment="所属风机编号")
    gear_id = Column(String(64), comment="所属齿轮箱编号")
    sensor_type = Column(String(32), nullable=False, comment="传感器类型:acc加速度,vel速度,disp位移,temp温度")
    measure_axis = Column(String(8), nullable=False, default="Z", comment="测量轴:X/Y/Z")
    mount_position = Column(String(64), comment="安装位置描述")
    sensitivity = Column(DECIMAL(12, 6), comment="灵敏度")
    frequency_range_min = Column(DECIMAL(12, 4), comment="频率范围下限(Hz)")
    frequency_range_max = Column(DECIMAL(12, 4), comment="频率范围上限(Hz)")
    sample_rate = Column(Integer, default=25600, comment="默认采样率(Hz)")
    installed_at = Column(Date, comment="安装日期")
    status = Column(SmallInteger, nullable=False, default=1, comment="状态:0停用1正常2维护3故障")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_sensor_id", "sensor_id"),
        Index("idx_turbine_id", "turbine_id"),
        Index("idx_gear_id", "gear_id"),
        Index("idx_type", "sensor_type"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "comment": "传感器配置表"}
    )


class Bearing(MySQLBase):
    __tablename__ = "bearings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    bearing_id = Column(String(64), unique=True, nullable=False, comment="轴承唯一编号")
    bearing_name = Column(String(128), nullable=False, comment="轴承名称")
    turbine_id = Column(String(64), nullable=False, comment="所属风机编号")
    gear_id = Column(String(64), comment="所属齿轮箱编号")
    shaft_id = Column(String(64), comment="所属轴编号")
    model = Column(String(128), comment="轴承型号")
    manufacturer = Column(String(128), comment="制造商")
    roller_count = Column(Integer, comment="滚动体数量")
    roller_diameter = Column(DECIMAL(10, 4), comment="滚动体直径(mm)")
    pitch_diameter = Column(DECIMAL(12, 4), comment="节圆直径(mm)")
    contact_angle = Column(DECIMAL(6, 2), comment="接触角(°)")
    bpfo = Column(DECIMAL(12, 6), comment="外圈故障特征频率系数")
    bpfi = Column(DECIMAL(12, 6), comment="内圈故障特征频率系数")
    bsf = Column(DECIMAL(12, 6), comment="滚动体自转故障特征频率系数")
    ftf = Column(DECIMAL(12, 6), comment="保持架故障特征频率系数")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_bearing_id", "bearing_id"),
        Index("idx_turbine_id", "turbine_id"),
        Index("idx_gear_id", "gear_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "comment": "轴承参数表"}
    )
