from typing import Any, Optional, Generic, TypeVar, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    code: int = Field(0, description="响应码，0表示成功")
    message: str = Field("操作成功", description="响应消息")
    data: Optional[T] = Field(None, description="响应数据")
    success: bool = Field(True, description="是否成功")


class PageParams(BaseModel):
    page: int = Field(1, ge=1, description="页码，从1开始")
    page_size: int = Field(20, ge=1, le=500, description="每页条数")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T] = Field(..., description="数据列表")
    total: int = Field(..., ge=0, description="总记录数")
    page: int = Field(..., ge=1, description="当前页码")
    page_size: int = Field(..., ge=1, description="每页条数")
    total_pages: int = Field(..., ge=0, description="总页数")


class TimeRange(BaseModel):
    start_time: datetime = Field(..., description="开始时间")
    end_time: datetime = Field(..., description="结束时间")


class SpeedRange(BaseModel):
    min_speed: Optional[float] = Field(None, ge=0, description="最小转速(rpm)")
    max_speed: Optional[float] = Field(None, ge=0, description="最大转速(rpm)")
