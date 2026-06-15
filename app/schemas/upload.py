import uuid
from typing import Optional, List
from datetime import datetime
from enum import IntEnum
from pydantic import BaseModel, Field, ConfigDict


class UploadStatus(IntEnum):
    PENDING = 0
    UPLOADING = 1
    COMPLETED = 2
    PROCESSING = 3
    PROCESSED = 4
    FAILED = 5


class WaveformFormat(str):
    FLOAT32_BE = "float32_be"
    FLOAT32_LE = "float32_le"
    FLOAT64_BE = "float64_be"
    FLOAT64_LE = "float64_le"
    INT16_BE = "int16_be"
    INT16_LE = "int16_le"
    INT32_BE = "int32_be"
    INT32_LE = "int32_le"


class UploadInitRequest(BaseModel):
    turbine_id: str = Field(..., min_length=1, max_length=64, description="风机编号")
    sensor_id: str = Field(..., min_length=1, max_length=64, description="传感器编号")
    shaft_id: Optional[str] = Field(None, max_length=64, description="轴编号(用于转速数据)")
    total_chunks: int = Field(..., ge=1, description="总分片数")
    total_samples: int = Field(..., ge=1, description="总采样点数")
    sample_rate: int = Field(..., ge=1, le=512000, description="采样率(Hz)")
    start_time: datetime = Field(..., description="采集开始时间")
    file_name: Optional[str] = Field(None, max_length=256, description="原始文件名")
    waveform_format: str = Field(WaveformFormat.FLOAT32_LE, description="二进制波形格式")
    has_speed_data: bool = Field(False, description="是否包含同步转速数据")


class UploadInitResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    batch_id: uuid.UUID = Field(..., description="上传批次ID")
    turbine_id: str = Field(..., description="风机编号")
    sensor_id: str = Field(..., description="传感器编号")
    total_chunks: int = Field(..., description="总分片数")
    sample_rate: int = Field(..., description="采样率")
    status: UploadStatus = Field(..., description="上传状态")
    created_at: datetime = Field(..., description="创建时间")


class UploadChunkResponse(BaseModel):
    batch_id: uuid.UUID = Field(..., description="批次ID")
    chunk_index: int = Field(..., description="当前分片索引")
    uploaded_chunks: int = Field(..., description="已上传分片数")
    total_chunks: int = Field(..., description="总分片数")
    completed: bool = Field(..., description="是否全部上传完成")
    status: UploadStatus = Field(..., description="上传状态")


class UploadCompleteRequest(BaseModel):
    batch_id: uuid.UUID = Field(..., description="批次ID")


class UploadCompleteResponse(BaseModel):
    batch_id: uuid.UUID = Field(..., description="批次ID")
    status: UploadStatus = Field(..., description="处理状态")
    total_samples: int = Field(..., description="总样本数")
    waveform_points_inserted: int = Field(0, description="已写入波形点数")
    speed_points_inserted: int = Field(0, description="已写入转速点数")


class UploadBatchInfo(BaseModel):
    batch_id: uuid.UUID = Field(..., description="批次ID")
    turbine_id: str = Field(..., description="风机编号")
    sensor_id: Optional[str] = Field(None, description="传感器编号")
    shaft_id: Optional[str] = Field(None, description="轴编号")
    total_chunks: int = Field(..., description="总分片数")
    uploaded_chunks: int = Field(..., description="已上传分片数")
    total_samples: int = Field(..., description="总样本数")
    sample_rate: int = Field(..., description="采样率")
    waveform_format: Optional[str] = Field(None, description="二进制波形格式")
    has_speed_data: bool = Field(False, description="是否包含转速数据")
    start_time: Optional[datetime] = Field(None, description="采集开始时间")
    status: UploadStatus = Field(..., description="状态")
    file_name: Optional[str] = Field(None, description="文件名")
    started_at: datetime = Field(..., description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    error_message: Optional[str] = Field(None, description="错误信息")


class WaveformParseResult(BaseModel):
    time_vector: List[datetime] = Field(..., description="时间序列")
    acceleration_x: List[float] = Field(default_factory=list, description="X向加速度")
    acceleration_y: List[float] = Field(default_factory=list, description="Y向加速度")
    acceleration_z: List[float] = Field(default_factory=list, description="Z向加速度")
    speed_rpm: List[float] = Field(default_factory=list, description="转速序列(rpm)")
    speed_times: List[datetime] = Field(default_factory=list, description="转速时间序列")
