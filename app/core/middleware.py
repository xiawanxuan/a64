import time
import json
import uuid
from typing import Callable
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from loguru import logger

from app.core.exceptions import build_response_body
from app.core.error_codes import ErrorCode


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        request_id = str(uuid.uuid4())
        start_time = time.time()

        request.state.request_id = request_id

        client_ip = request.client.host if request.client else "unknown"
        method = request.method
        path = request.url.path
        query = str(request.url.query) if request.url.query else ""

        logger.info(
            f"[REQ] id={request_id} | ip={client_ip} | "
            f"{method} {path}" + (f"?{query}" if query else "")
        )

        try:
            response = await call_next(request)
            process_time_ms = (time.time() - start_time) * 1000
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time-MS"] = f"{process_time_ms:.2f}"

            logger.info(
                f"[RSP] id={request_id} | status={response.status_code} | "
                f"cost={process_time_ms:.2f}ms"
            )
            return response
        except Exception as exc:
            process_time_ms = (time.time() - start_time) * 1000
            tb = __import__("traceback").format_exc()
            logger.error(
                f"[ERR] id={request_id} | cost={process_time_ms:.2f}ms | "
                f"exception={type(exc).__name__}: {exc}\n{tb}"
            )
            body = build_response_body(
                ErrorCode.INTERNAL_ERROR,
                "系统内部错误，请联系管理员"
            )
            return Response(
                content=json.dumps(body, ensure_ascii=False),
                status_code=500,
                media_type="application/json",
                headers={
                    "X-Request-ID": request_id,
                    "X-Process-Time-MS": f"{process_time_ms:.2f}"
                }
            )


class ResponseBodyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)

        if path_should_wrap(request.url.path):
            return response

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        if response.status_code == 200:
            try:
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk
                original = json.loads(body.decode("utf-8")) if body else None

                if isinstance(original, dict) and "code" in original:
                    return Response(
                        content=body,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type="application/json"
                    )

                wrapped = build_response_body(ErrorCode.SUCCESS, "操作成功", original)
                return Response(
                    content=json.dumps(wrapped, ensure_ascii=False).encode("utf-8"),
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type="application/json"
                )
            except Exception:
                return response

        return response


def path_should_wrap(path: str) -> bool:
    exclude_prefixes = ["/docs", "/redoc", "/openapi", "/static"]
    for prefix in exclude_prefixes:
        if path.startswith(prefix):
            return True
    return False


def setup_middleware(app: FastAPI):
    app.add_middleware(RequestLoggingMiddleware)
