"""错误码库（含提取正则，被告警规则引用）。"""
import re

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok, page_result
from ...database import get_db
from ...models import ErrorCode, RuleErrorCode
from ..auth.deps import ROLE_ADMIN, ROLE_OPS, CurrentUser, client_ip, require_roles

router = APIRouter(prefix="/api/v1/error-codes", tags=["错误码配置"])

WRITE = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))


class ErrorCodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    extract_regex: str = Field(min_length=1, max_length=255)
    description: str | None = None
    enabled: int = 1


def _validate(body: ErrorCodeIn) -> None:
    try:
        re.compile(body.extract_regex)
    except re.error:
        raise BizException("提取正则无法编译", code=400)


def _to_dict(e: ErrorCode) -> dict:
    return {c: getattr(e, c) for c in
            ["id", "code", "extract_regex", "description", "enabled",
             "created_at", "updated_at"]}


@router.get("")
def list_error_codes(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
                     code: str | None = None, db: Session = Depends(get_db)):
    q = db.query(ErrorCode)
    if code:
        q = q.filter(ErrorCode.code.like(f"%{code}%"))
    total = q.count()
    items = q.order_by(ErrorCode.id.desc()).offset((page - 1) * size).limit(size).all()
    return page_result([_to_dict(e) for e in items], total, page, size)


@router.post("", dependencies=[WRITE])
def create_error_code(body: ErrorCodeIn, request: Request, db: Session = Depends(get_db),
                      me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    _validate(body)
    e = ErrorCode(**body.model_dump())
    db.add(e)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="CREATE",
                 target=f"error_code:{e.code}", ip=client_ip(request))
    return ok(_to_dict(e), msg="创建成功")


@router.put("/{code_id}", dependencies=[WRITE])
def update_error_code(code_id: int, body: ErrorCodeIn, request: Request,
                      db: Session = Depends(get_db),
                      me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    e = db.query(ErrorCode).filter(ErrorCode.id == code_id).first()
    if not e:
        raise BizException("错误码不存在", code=404)
    _validate(body)
    for k, v in body.model_dump().items():
        setattr(e, k, v)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="UPDATE",
                 target=f"error_code:{e.code}", ip=client_ip(request))
    return ok(_to_dict(e), msg="更新成功")


@router.delete("/{code_id}", dependencies=[WRITE])
def delete_error_code(code_id: int, request: Request, db: Session = Depends(get_db),
                      me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    e = db.query(ErrorCode).filter(ErrorCode.id == code_id).first()
    if not e:
        raise BizException("错误码不存在", code=404)
    if db.query(RuleErrorCode).filter(RuleErrorCode.error_code_id == code_id).count() > 0:
        raise BizException("该错误码已被告警规则引用，请先解除关联", code=400)
    db.delete(e)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target=f"error_code:{e.code}", ip=client_ip(request))
    return ok(msg="删除成功")
