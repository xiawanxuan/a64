import uuid
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.common import TimeRange, SpeedRange, PageParams, PaginatedResponse
from app.schemas.analysis import GearFaultFeatureData, OrderSpectrumData, FaultSeverity
from app.schemas.upload import UploadBatchInfo


class WaveformQueryRequest(BaseModel):
    turbine_id: str = Field(..., min_length=1, max_length=64, description="风机编号")
    sensor_id: Optional[str] = Field(None, max_length=64, description="传感器编号")
    time_range: TimeRange = Field(..., description="查询时间范围")
    speed_range: Optional[SpeedRange] = Field(None, description="转速区间过滤")
    max_points: int = Field(100000, ge=100, le=10000000, description="最大返回点数(用于降采样)")
    downsample: bool = Field(True, description="超出max_points时是否自动降采样")


class WaveformDataPoint(BaseModel):
    time: datetime = Field(..., description="采样时间")
    acceleration_x: Optional[float] = Field(None, description="X向加速度(g)")
    acceleration_y: Optional[float] = Field(None, description="Y向加速度(g)")
    acceleration_z: Optional[float] = Field(None, description="Z向加速度(g)")
    velocity_x: Optional[float] = Field(None, description="X向速度(mm/s)")
    velocity_y: Optional[float] = Field(None, description="Y向速度(mm/s)")
    velocity_z: Optional[float] = Field(None, description="Z向速度(mm/s)")
    temperature: Optional[float] = Field(None, description="温度(℃)")


class WaveformQueryResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    turbine_id: str = Field(..., description="风机编号")
    sensor_id: Optional[str] = Field(None, description="传感器编号")
    time_range: TimeRange = Field(..., description="实际数据时间范围")
    sample_rate: int = Field(..., description="采样率(Hz)")
    total_points: int = Field(..., description="原始总点数")
    returned_points: int = Field(..., description="实际返回点数")
    downsampled: bool = Field(False, description="是否降采样")
    downsample_ratio: float = Field(1.0, description="降采样比率")
    data: List[WaveformDataPoint] = Field(default_factory=list, description="波形数据")


class SpeedQueryRequest(BaseModel):
    turbine_id: str = Field(..., min_length=1, max_length=64, description="风机编号")
    shaft_id: Optional[str] = Field(None, max_length=64, description="轴编号")
    time_range: TimeRange = Field(..., description="查询时间范围")


class SpeedDataPoint(BaseModel):
    time: datetime = Field(..., description="时间")
    speed_rpm: float = Field(..., description="转速(rpm)")
    shaft_id: str = Field(..., description="轴编号")


class SpeedQueryResponse(BaseModel):
    turbine_id: str = Field(..., description="风机编号")
    shaft_id: Optional[str] = Field(None, description="轴编号")
    time_range: TimeRange = Field(..., description="时间范围")
    total_points: int = Field(..., description="总点数")
    min_speed: float = Field(..., description="最低转速")
    max_speed: float = Field(..., description="最高转速")
    mean_speed: float = Field(..., description="平均转速")
    data: List[SpeedDataPoint] = Field(default_factory=list, description="转速数据")


class SpectrumQueryRequest(BaseModel):
    turbine_id: Optional[str] = Field(None, description="风机编号")
    gear_id: Optional[str] = Field(None, description="齿轮箱编号")
    time_range: TimeRange = Field(..., description="查询时间范围")
    page: PageParams = Field(default_factory=PageParams, description="分页参数")


class FeatureQueryRequest(BaseModel):
    turbine_id: Optional[str] = Field(None, description="风机编号")
    gear_id: Optional[str] = Field(None, description="齿轮箱编号")
    time_range: TimeRange = Field(..., description="查询时间范围")
    min_severity: Optional[FaultSeverity] = Field(None, description="最小严重度过滤")
    page: PageParams = Field(default_factory=PageParams, description="分页参数")


class TurbineLedgerInfo(BaseModel):
    turbine_id: str = Field(..., description="风机编号")
    turbine_name: str = Field(..., description="风机名称")
    farm_code: str = Field(..., description="风电场编码")
    farm_name: Optional[str] = Field(None, description="风电场名称")
    model: Optional[str] = Field(None, description="风机型号")
    manufacturer: Optional[str] = Field(None, description="制造商")
    rated_power: Optional[float] = Field(None, description="额定功率(kW)")
    rated_speed: Optional[float] = Field(None, description="额定转速(rpm)")
    min_speed: Optional[float] = Field(None, description="最低转速(rpm)")
    max_speed: Optional[float] = Field(None, description="最高转速(rpm)")
    status: int = Field(..., description="状态")
    gearbox_count: int = Field(0, description="关联齿轮箱数量")
    sensor_count: int = Field(0, description="关联传感器数量")


class GearboxLedgerInfo(BaseModel):
    gear_id: str = Field(..., description="齿轮箱编号")
    gear_name: str = Field(..., description="齿轮箱名称")
    turbine_id: str = Field(..., description="所属风机编号")
    turbine_name: Optional[str] = Field(None, description="风机名称")
    model: Optional[str] = Field(None, description="齿轮箱型号")
    manufacturer: Optional[str] = Field(None, description="制造商")
    gear_ratio: float = Field(..., description="总传动比")
    stages: int = Field(..., description="传动级数")
    status: int = Field(..., description="状态")
    gear_params_count: int = Field(0, description="齿轮参数数量")


class GearParamInfo(BaseModel):
    gear_param_id: str = Field(..., description="齿轮参数ID")
    gear_id: str = Field(..., description="齿轮箱编号")
    stage: int = Field(..., description="传动级")
    gear_type: str = Field(..., description="齿轮类型")
    position: str = Field(..., description="位置")
    teeth_count: int = Field(..., description="齿数")
    module: float = Field(..., description="模数")
    pitch_diameter: float = Field(..., description="节圆直径")
    mesh_order_ref: float = Field(..., description="参考啮合阶次(相对该级输入轴)")


class SensorInfo(BaseModel):
    sensor_id: str = Field(..., description="传感器编号")
    sensor_name: str = Field(..., description="传感器名称")
    turbine_id: str = Field(..., description="所属风机编号")
    gear_id: Optional[str] = Field(None, description="所属齿轮箱编号")
    sensor_type: str = Field(..., description="传感器类型")
    measure_axis: str = Field(..., description="测量轴")
    mount_position: Optional[str] = Field(None, description="安装位置")
    sample_rate: int = Field(..., description="默认采样率")
    status: int = Field(..., description="状态")


class BatchQueryRequest(BaseModel):
    turbine_id: Optional[str] = Field(None, description="风机编号")
    status: Optional[int] = Field(None, description="状态过滤")
    started_from: Optional[datetime] = Field(None, description="开始时间起")
    started_to: Optional[datetime] = Field(None, description="开始时间止")
    page: PageParams = Field(default_factory=PageParams, description="分页参数")


class FailedRecordInfo(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: uuid.UUID = Field(..., description="记录ID")
    turbine_id: str = Field(..., description="风机编号")
    gear_id: Optional[str] = Field(None, description="齿轮箱编号")
    analysis_type: str = Field(..., description="分析类型")
    batch_id: Optional[uuid.UUID] = Field(None, description="上传批次ID")
    waveform_file: str = Field(..., description="留存波形文件路径")
    speed_file: Optional[str] = Field(None, description="留存转速文件路径")
    error_type: str = Field(..., description="错误类型")
    error_message: str = Field(..., description="错误消息")
    params: Optional[dict] = Field(None, description="调用参数")
    created_at: datetime = Field(..., description="创建时间")


class FailedRecordQueryRequest(BaseModel):
    turbine_id: Optional[str] = Field(None, description="风机编号")
    gear_id: Optional[str] = Field(None, description="齿轮箱编号")
    analysis_type: Optional[str] = Field(None, description="分析类型")
    error_type: Optional[str] = Field(None, description="错误类型")
    time_range: Optional[TimeRange] = Field(None, description="时间范围")
    page: PageParams = Field(default_factory=PageParams, description="分页参数")
