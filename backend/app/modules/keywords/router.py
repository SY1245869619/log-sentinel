"""关键字库（可复用资源，被告警规则引用）。"""
import re

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok, page_result
from ...database import get_db
from ...models import Keyword, RuleKeyword
from ..auth.deps import ROLE_ADMIN, ROLE_OPS, CurrentUser, client_ip, require_roles

router = APIRouter(prefix="/api/v1/keywords", tags=["关键字配置"])

WRITE = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))
OPS = ("CONTAINS", "NOT_CONTAINS", "EQUALS", "REGEX")


class KeywordIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    pattern: str = Field(min_length=1, max_length=512)
    match_op: str = Field(default="CONTAINS")
    enabled: int = 1


def _validate(body: KeywordIn) -> None:
    if body.match_op not in OPS:
        raise BizException(f"匹配操作符必须是 {'/'.join(OPS)}", code=400)
    if body.match_op == "REGEX":
        try:
            re.compile(body.pattern)
        except re.error:
            raise BizException("正则表达式无法编译", code=400)


def _to_dict(k: Keyword) -> dict:
    return {c: getattr(k, c) for c in
            ["id", "name", "pattern", "match_op", "enabled", "created_at", "updated_at"]}


@router.get("")
def list_keywords(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
                  name: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Keyword)
    if name:
        q = q.filter(Keyword.name.like(f"%{name}%"))
    total = q.count()
    items = q.order_by(Keyword.id.desc()).offset((page - 1) * size).limit(size).all()
    return page_result([_to_dict(k) for k in items], total, page, size)


@router.post("", dependencies=[WRITE])
def create_keyword(body: KeywordIn, request: Request, db: Session = Depends(get_db),
                   me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    _validate(body)
    k = Keyword(**body.model_dump())
    db.add(k)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="CREATE",
                 target=f"keyword:{k.name}", ip=client_ip(request))
    return ok(_to_dict(k), msg="创建成功")


@router.put("/{keyword_id}", dependencies=[WRITE])
def update_keyword(keyword_id: int, body: KeywordIn, request: Request,
                   db: Session = Depends(get_db),
                   me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    k = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if not k:
        raise BizException("关键字不存在", code=404)
    _validate(body)
    for key, v in body.model_dump().items():
        setattr(k, key, v)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="UPDATE",
                 target=f"keyword:{k.name}", ip=client_ip(request))
    return ok(_to_dict(k), msg="更新成功")


@router.delete("/{keyword_id}", dependencies=[WRITE])
def delete_keyword(keyword_id: int, request: Request, db: Session = Depends(get_db),
                   me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    k = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if not k:
        raise BizException("关键字不存在", code=404)
    if db.query(RuleKeyword).filter(RuleKeyword.keyword_id == keyword_id).count() > 0:
        raise BizException("该关键字已被告警规则引用，请先解除关联", code=400)
    db.delete(k)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target=f"keyword:{k.name}", ip=client_ip(request))
    return ok(msg="删除成功")
