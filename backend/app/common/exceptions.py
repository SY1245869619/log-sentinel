"""业务异常与全局异常处理。"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .response import fail

logger = logging.getLogger("logsentinel")


class BizException(Exception):
    """业务异常：message 直接返回给前端展示。"""

    def __init__(self, message: str, code: int = 500):
        super().__init__(message)
        self.message = message
        self.code = code


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizException)
    async def handle_biz(request: Request, exc: BizException):
        logger.warning("业务异常: %s", exc.message)
        # 401/403 必须返回真实 HTTP 状态码，前端才能识别并自动跳登录
        status_code = exc.code if exc.code in (401, 403) else 200
        return JSONResponse(status_code=status_code, content=fail(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        msgs = [
            f"{'.'.join(str(p) for p in e['loc'] if p != 'body')}: {e['msg']}"
            for e in exc.errors()
        ]
        return JSONResponse(status_code=200, content=fail(400, "; ".join(msgs) or "参数校验失败"))

    @app.exception_handler(Exception)
    async def handle_other(request: Request, exc: Exception):
        logger.exception("系统异常: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=200, content=fail(500, "系统异常，请稍后重试"))
