"""通知模板：占位符 ${project} ${host} ${env} ${level} ${time} ${errorCode} ${keyword} ${file} ${content} ${mentions}。"""
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok, page_result
from ...database import get_db
from ...models import NotifyTemplate
from ..auth.deps import ROLE_ADMIN, ROLE_OPS, CurrentUser, client_ip, require_roles

router = APIRouter(prefix="/api/v1/notify-templates", tags=["通知模板"])

WRITE = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    channel_type: str = Field(default="dingtalk")
    msg_type: str = Field(default="markdown", pattern="^(markdown|text)$")
    content_template: str = Field(min_length=1)
    enabled: int = 1


def _to_dict(t: NotifyTemplate) -> dict:
    return {c: getattr(t, c) for c in
            ["id", "name", "channel_type", "msg_type", "content_template",
             "enabled", "created_at", "updated_at"]}


@router.get("")
def list_templates(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
                   channel_type: str | None = None, db: Session = Depends(get_db)):
    q = db.query(NotifyTemplate)
    if channel_type:
        q = q.filter(NotifyTemplate.channel_type == channel_type)
    total = q.count()
    items = q.order_by(NotifyTemplate.id.desc()).offset((page - 1) * size).limit(size).all()
    return page_result([_to_dict(t) for t in items], total, page, size)


@router.post("", dependencies=[WRITE])
def create_template(body: TemplateIn, request: Request, db: Session = Depends(get_db),
                    me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    t = NotifyTemplate(**body.model_dump())
    db.add(t)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="CREATE",
                 target=f"template:{t.name}", ip=client_ip(request))
    return ok(_to_dict(t), msg="创建成功")


@router.put("/{template_id}", dependencies=[WRITE])
def update_template(template_id: int, body: TemplateIn, request: Request,
                    db: Session = Depends(get_db),
                    me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    t = db.query(NotifyTemplate).filter(NotifyTemplate.id == template_id).first()
    if not t:
        raise BizException("模板不存在", code=404)
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="UPDATE",
                 target=f"template:{t.name}", ip=client_ip(request))
    return ok(_to_dict(t), msg="更新成功")


@router.delete("/{template_id}", dependencies=[WRITE])
def delete_template(template_id: int, request: Request, db: Session = Depends(get_db),
                    me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    t = db.query(NotifyTemplate).filter(NotifyTemplate.id == template_id).first()
    if not t:
        raise BizException("模板不存在", code=404)
    db.delete(t)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target=f"template:{t.name}", ip=client_ip(request))
    return ok(msg="删除成功")
