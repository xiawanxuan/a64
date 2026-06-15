import json
import traceback
from typing import Any, Optional, Dict
from fastapi import Request, status
from fastapi.responses import ORJSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from loguru import logger

from app.core.error_codes import ErrorCode, get_error_message


class BusinessException(Exception):
    def __init__(
        self,
        code: int,
        message: Optional[str] = None,
        data: Any = None,
        http_status: int = status.HTTP_400_BAD_REQUEST,
        cause: Optional[Exception] = None
    ):
        self.code = code
        self.message = message or get_error_message(code)
        self.data = data
        self.http_status = http_status
        self.cause = cause
        super().__init__(self.message)


def build_response_body(code: int, message: str, data: Any = None) -> Dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data,
        "success": code == ErrorCode.SUCCESS
    }


def setup_exception_handlers(app):
    @app.exception_handler(BusinessException)
    async def business_exception_handler(request: Request, exc: BusinessException):
        logger.warning(
            f"业务异常 | code={exc.code} | message={exc.message} | "
            f"path={request.url.path} | method={request.method}"
        )
        if exc.cause:
            logger.debug(f"异常根因: {exc.cause}")
        body = build_response_body(exc.code, exc.message, exc.data)
        return ORJSONResponse(status_code=exc.http_status, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        error_detail = exc.errors()
        logger.warning(
            f"参数校验失败 | path={request.url.path} | "
            f"method={request.method} | errors={json.dumps(error_detail, ensure_ascii=False)}"
        )
        fields = []
        for err in error_detail:
            loc = err.get("loc", [])
            field = ".".join(str(x) for x in loc[1:]) if len(loc) > 1 else "unknown"
            fields.append(f"{field}: {err.get('msg', 'invalid')}")
        msg = f"参数校验失败: {'; '.join(fields)}"
        body = build_response_body(ErrorCode.PARAM_INVALID, msg, error_detail)
        return ORJSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        logger.warning(
            f"HTTP异常 | status={exc.status_code} | detail={exc.detail} | "
            f"path={request.url.path} | method={request.method}"
        )
        code_map = {
            404: ErrorCode.PARAM_INVALID,
            401: ErrorCode.PARAM_INVALID,
            403: ErrorCode.PARAM_INVALID,
            405: ErrorCode.PARAM_INVALID,
        }
        code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        message_map = {
            404: f"请求路径不存在: {request.url.path}",
            401: "未授权访问",
            403: "访问被拒绝",
            405: f"不支持的请求方法: {request.method}",
        }
        msg = message_map.get(exc.status_code, str(exc.detail))
        body = build_response_body(code, msg)
        return ORJSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        tb = traceback.format_exc()
        logger.error(
            f"未处理异常 | path={request.url.path} | method={request.method} | "
            f"exception_type={type(exc).__name__} | message={exc}\n{tb}"
        )
        body = build_response_body(
            ErrorCode.INTERNAL_ERROR,
            "系统内部错误，请联系管理员",
            None
        )
        return ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=body
        )
