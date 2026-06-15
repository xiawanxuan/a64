import uuid
from typing import Optional, List
from datetime import datetime
from enum import IntEnum
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.common import TimeRange, SpeedRange


class AnalysisStatus(IntEnum):
    PENDING = 0
    PROCESSING = 1
    COMPLETED = 2
    FAILED = 3


class FaultSeverity(IntEnum):
    NORMAL = 0
    WARNING = 1
    ALARM = 2
    CRITICAL = 3


class OrderAnalysisRequest(BaseModel):
    turbine_id: str = Field(..., min_length=1, max_length=64, description="风机编号")
    gear_id: str = Field(..., min_length=1, max_length=64, description="齿轮箱编号")
    sensor_id: Optional[str] = Field(None, max_length=64, description="传感器编号(默认使用Z向主传感器)")
    shaft_id: Optional[str] = Field(None, max_length=64, description="低速轴编号(用于获取转速)")
    time_range: TimeRange = Field(..., description="分析时间范围")
    speed_range: Optional[SpeedRange] = Field(None, description="转速过滤范围")
    stage: Optional[int] = Field(None, ge=1, description="分析指定传动级, 默认分析全部")


class OrderSpectrumData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    spectrum_id: uuid.UUID = Field(..., description="频谱ID")
    turbine_id: str = Field(..., description="风机编号")
    gear_id: str = Field(..., description="齿轮箱编号")
    analysis_start: datetime = Field(..., description="分析开始时间")
    analysis_end: datetime = Field(..., description="分析结束时间")
    order_values: List[float] = Field(..., description="阶次值数组")
    amplitude_values: List[float] = Field(..., description="幅值数组")
    max_order: float = Field(..., description="最大分析阶次")
    order_resolution: float = Field(..., description="阶次分辨率")
    resampled_count: int = Field(..., description="重采样后点数")
    created_at: datetime = Field(..., description="创建时间")


class GearFaultFeatureData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    feature_id: uuid.UUID = Field(..., description="特征ID")
    spectrum_id: Optional[uuid.UUID] = Field(None, description="关联频谱ID")
    turbine_id: str = Field(..., description="风机编号")
    gear_id: str = Field(..., description="齿轮箱编号")
    gear_param_id: Optional[str] = Field(None, description="齿轮参数ID")
    stage: int = Field(..., description="传动级")
    gear_type: str = Field(..., description="齿轮类型")
    teeth_count: int = Field(..., description="齿数")
    mesh_order: float = Field(..., description="啮合阶次(转频倍数)")
    mesh_amplitude: float = Field(..., description="啮合阶次幅值")
    sideband_orders: List[float] = Field(..., description="边频阶次列表")
    sideband_amplitudes: List[float] = Field(..., description="边频幅值列表")
    sideband_spacing: float = Field(..., description="边频间隔(等于调制转频阶次)")
    max_sideband_amp: float = Field(..., description="最大边频幅值")
    sideband_energy: float = Field(..., description="边频总能量")
    kurtosis: Optional[float] = Field(None, description="峭度")
    crest_factor: Optional[float] = Field(None, description="峰值因子")
    rms_value: Optional[float] = Field(None, description="RMS有效值")
    peak_value: Optional[float] = Field(None, description="峰值")
    fault_severity: FaultSeverity = Field(..., description="故障严重度:0正常1预警2报警3严重")
    diagnosis_note: Optional[str] = Field(None, description="诊断说明")
    created_at: datetime = Field(..., description="创建时间")


class OrderAnalysisResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    turbine_id: str = Field(..., description="风机编号")
    gear_id: str = Field(..., description="齿轮箱编号")
    status: AnalysisStatus = Field(..., description="分析状态")
    time_range: TimeRange = Field(..., description="分析时间范围")
    mean_speed_rpm: float = Field(0, description="分析期间平均转速(rpm)")
    valid_duration_sec: float = Field(0, description="有效数据时长(秒)")
    spectrum: Optional[OrderSpectrumData] = Field(None, description="阶次谱数据")
    fault_features: List[GearFaultFeatureData] = Field(default_factory=list, description="各级齿轮故障特征")
    overall_severity: FaultSeverity = Field(FaultSeverity.NORMAL, description="整体故障严重度")
    analysis_cost_ms: float = Field(0, description="分析耗时(毫秒)")
    message: Optional[str] = Field(None, description="处理说明或错误信息")


class BatchAnalysisRequest(BaseModel):
    turbine_ids: List[str] = Field(..., min_length=1, description="风机编号列表")
    gear_id: Optional[str] = Field(None, description="指定齿轮箱(不填则分析全部)")
    time_range: TimeRange = Field(..., description="分析时间范围")
    speed_range: Optional[SpeedRange] = Field(None, description="转速过滤范围")
