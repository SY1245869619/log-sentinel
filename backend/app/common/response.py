"""统一响应体：code=0 成功，非 0 失败。"""
from typing import Any


def ok(data: Any = None, msg: str = "success") -> dict:
    return {"code": 0, "msg": msg, "data": data}


def fail(code: int, msg: str) -> dict:
    return {"code": code, "msg": msg, "data": None}


def page_result(items: list, total: int, page: int, size: int) -> dict:
    """分页结果封装。"""
    return ok({"list": items, "total": total, "page": page, "size": size})
