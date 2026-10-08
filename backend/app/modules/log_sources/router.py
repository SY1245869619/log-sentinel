"""日志源管理。创建时自动建立采集状态行；删除受规则引用阻断。"""
import re

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok, page_result
from ...database import get_db
from ...models import (Agent, AlertRuleSource, CollectorState, Host, LogSource,
                       Project)
from ..auth.deps import ROLE_ADMIN, ROLE_OPS, CurrentUser, client_ip, require_roles

router = APIRouter(prefix="/api/v1/log-sources", tags=["日志源管理"])

WRITE = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))


class LogSourceIn(BaseModel):
    project_id: int
    host_id: int
    collect_mode: str = Field(default="SSH", pattern="^(SSH|LOCAL|AGENT)$")
    agent_id: int | None = None
    name: str = Field(min_length=1, max_length=128)
    path_pattern: str = Field(min_length=1, max_length=512)
    exclude_pattern: str | None = None
    encoding: str = Field(default="UTF-8", pattern="^(UTF-8|GBK)$")
    multiline_pattern: str = r"^\[?\d{4}-\d{2}-\d{2}"
    interval_seconds: int = Field(default=5, ge=1, le=3600)
    env: str | None = None
    tags: str | None = None
    enabled: int = 1


def _to_dict(s: LogSource, db: Session) -> dict:
    project = db.query(Project).filter(Project.id == s.project_id).first()
    host = db.query(Host).filter(Host.id == s.host_id).first()
    return {
        "id": s.id, "project_id": s.project_id,
        "project_name": project.name if project else None,
        "host_id": s.host_id,
        "host_name": host.name if host else None,
        "host_ip": host.ip if host else None,
        "collect_mode": s.collect_mode, "agent_id": s.agent_id,
        "name": s.name, "path_pattern": s.path_pattern,
        "exclude_pattern": s.exclude_pattern, "encoding": s.encoding,
        "multiline_pattern": s.multiline_pattern,
        "interval_seconds": s.interval_seconds, "env": s.env, "tags": s.tags,
        "enabled": s.enabled, "created_at": s.created_at, "updated_at": s.updated_at,
    }


def _validate(body: LogSourceIn, db: Session) -> None:
    project = db.query(Project).filter(Project.id == body.project_id).first()
    if not project:
        raise BizException("关联项目不存在", code=400)
    host = db.query(Host).filter(Host.id == body.host_id).first()
    if not host:
        raise BizException("关联主机不存在", code=400)
    try:
        re.compile(body.multiline_pattern)
    except re.error:
        raise BizException("多行起始正则无法编译", code=400)
    # AGENT 模式必须绑定 Agent，且该 Agent 未被其他来源占用校验
    if body.collect_mode == "AGENT":
        if not body.agent_id:
            raise BizException("Agent 模式必须选择 Agent", code=400)
        if not db.query(Agent).filter(Agent.id == body.agent_id).first():
            raise BizException("关联 Agent 不存在", code=400)
    else:
        body.agent_id = None
    # 环境以主机为准（页面不再配置项目/日志源环境）
    body.env = host.env


@router.get("")
def list_sources(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
                 project_id: int | None = None, host_id: int | None = None,
                 name: str | None = None, db: Session = Depends(get_db)):
    q = db.query(LogSource)
    if project_id:
        q = q.filter(LogSource.project_id == project_id)
    if host_id:
        q = q.filter(LogSource.host_id == host_id)
    if name:
        q = q.filter(LogSource.name.like(f"%{name}%"))
    total = q.count()
    items = q.order_by(LogSource.id.desc()).offset((page - 1) * size).limit(size).all()
    return page_result([_to_dict(s, db) for s in items], total, page, size)


@router.get("/{source_id}")
def get_source(source_id: int, db: Session = Depends(get_db)):
    s = db.query(LogSource).filter(LogSource.id == source_id).first()
    if not s:
        raise BizException("日志源不存在", code=404)
    return ok(_to_dict(s, db))


@router.post("", dependencies=[WRITE])
def create_source(body: LogSourceIn, request: Request, db: Session = Depends(get_db),
                  me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    _validate(body, db)
    s = LogSource(**body.model_dump())
    db.add(s)
    db.flush()
    # 自动建立采集状态行（默认停止，由采集管理页面启动）
    db.add(CollectorState(host_id=s.host_id, log_source_id=s.id, status="STOPPED"))
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="CREATE",
                 target=f"log_source:{s.name}", ip=client_ip(request))
    return ok(_to_dict(s, db), msg="创建成功")


@router.put("/{source_id}", dependencies=[WRITE])
def update_source(source_id: int, body: LogSourceIn, request: Request,
                  db: Session = Depends(get_db),
                  me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    s = db.query(LogSource).filter(LogSource.id == source_id).first()
    if not s:
        raise BizException("日志源不存在", code=404)
    _validate(body, db)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="UPDATE",
                 target=f"log_source:{s.name}", ip=client_ip(request))
    return ok(_to_dict(s, db), msg="更新成功")


@router.delete("/{source_id}", dependencies=[WRITE])
def delete_source(source_id: int, request: Request, db: Session = Depends(get_db),
                  me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    s = db.query(LogSource).filter(LogSource.id == source_id).first()
    if not s:
        raise BizException("日志源不存在", code=404)
    if db.query(AlertRuleSource).filter(AlertRuleSource.log_source_id == source_id).count() > 0:
        raise BizException("该日志源已被告警规则引用，请先解除规则关联", code=400)
    db.query(CollectorState).filter(CollectorState.log_source_id == source_id).delete()
    db.delete(s)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target=f"log_source:{s.name}", ip=client_ip(request))
    return ok(msg="删除成功")
