"""@人规则：钉钉 @ 依赖手机号。"""
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok, page_result
from ...database import get_db
from ...models import MentionRule
from ..auth.deps import ROLE_ADMIN, ROLE_OPS, CurrentUser, client_ip, require_roles

router = APIRouter(prefix="/api/v1/mentions", tags=["@人配置"])

WRITE = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))


class MentionIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    mobile: str = Field(min_length=5, max_length=32)
    dingtalk_userid: str | None = None
    scope: str = Field(default="PROJECT", pattern="^(PROJECT|HOST|RULE)$")
    ref_id: int | None = None


def _to_dict(m: MentionRule) -> dict:
    return {c: getattr(m, c) for c in
            ["id", "name", "mobile", "dingtalk_userid", "scope", "ref_id",
             "created_at", "updated_at"]}


@router.get("")
def list_mentions(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
                  name: str | None = None, scope: str | None = None,
                  db: Session = Depends(get_db)):
    q = db.query(MentionRule)
    if name:
        q = q.filter(MentionRule.name.like(f"%{name}%"))
    if scope:
        q = q.filter(MentionRule.scope == scope)
    total = q.count()
    items = q.order_by(MentionRule.id.desc()).offset((page - 1) * size).limit(size).all()
    return page_result([_to_dict(m) for m in items], total, page, size)


@router.post("", dependencies=[WRITE])
def create_mention(body: MentionIn, request: Request, db: Session = Depends(get_db),
                   me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    m = MentionRule(**body.model_dump())
    db.add(m)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="CREATE",
                 target=f"mention:{m.name}", ip=client_ip(request))
    return ok(_to_dict(m), msg="创建成功")


@router.put("/{mention_id}", dependencies=[WRITE])
def update_mention(mention_id: int, body: MentionIn, request: Request,
                   db: Session = Depends(get_db),
                   me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    m = db.query(MentionRule).filter(MentionRule.id == mention_id).first()
    if not m:
        raise BizException("@人不存在", code=404)
    for k, v in body.model_dump().items():
        setattr(m, k, v)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="UPDATE",
                 target=f"mention:{m.name}", ip=client_ip(request))
    return ok(_to_dict(m), msg="更新成功")


@router.delete("/{mention_id}", dependencies=[WRITE])
def delete_mention(mention_id: int, request: Request, db: Session = Depends(get_db),
                   me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    m = db.query(MentionRule).filter(MentionRule.id == mention_id).first()
    if not m:
        raise BizException("@人不存在", code=404)
    db.delete(m)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target=f"mention:{m.name}", ip=client_ip(request))
    return ok(msg="删除成功")
