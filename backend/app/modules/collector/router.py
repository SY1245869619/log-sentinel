"""采集管理：状态查看（只读）+ 启动/停止/重启（OPS+，记审计）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok, page_result
from ...database import get_db
from ...models import CollectorState, Host, LogSource, Project
from ..auth.deps import ROLE_ADMIN, ROLE_OPS, CurrentUser, client_ip, require_roles
from .manager import manager

router = APIRouter(prefix="/api/v1/collector", tags=["采集管理"])

CTRL = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))


def _to_dict(db: Session, st: CollectorState) -> dict:
    source = db.query(LogSource).filter(LogSource.id == st.log_source_id).first()
    project = db.query(Project).filter(Project.id == source.project_id).first() if source else None
    host = db.query(Host).filter(Host.id == st.host_id).first()
    delay = None
    if st.last_heartbeat:
        delay = int((datetime.now() - st.last_heartbeat).total_seconds())
    return {
        "id": st.id, "log_source_id": st.log_source_id,
        "source_name": source.name if source else None,
        "path_pattern": source.path_pattern if source else None,
        "project_name": project.name if project else None,
        "host_name": host.name if host else None,
        "host_ip": host.ip if host else None,
        "host_id": st.host_id,
        "status": st.status,
        "alive": manager.is_running(st.log_source_id),
        "last_read_position": st.last_read_position,
        "read_offset": st.read_offset, "inode": st.inode,
        "current_file": st.current_file, "rotated_file": st.rotated_file,
        "last_heartbeat": st.last_heartbeat, "error_msg": st.error_msg,
        "retry_count": st.retry_count, "last_retry_at": st.last_retry_at,
        "delay_seconds": delay,
    }


@router.get("/status")
def list_status(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
                status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(CollectorState)
    if status:
        q = q.filter(CollectorState.status == status)
    total = q.count()
    items = q.order_by(CollectorState.id.desc()).offset((page - 1) * size).limit(size).all()
    return page_result([_to_dict(db, s) for s in items], total, page, size)


def _control(source_id: int, action: str, request: Request, db: Session,
             me: CurrentUser):
    source = db.query(LogSource).filter(LogSource.id == source_id).first()
    if not source:
        raise BizException("日志源不存在", code=404)
    if action == "start":
        manager.start_source(source_id)
    elif action == "stop":
        manager.stop_source(source_id)
    else:
        manager.restart_source(source_id)
    record_audit(db, user_id=me.id, username=me.username, action="COLLECTOR_CTRL",
                 target=f"log_source:{source.name}", ip=client_ip(request),
                 detail=action)
    return ok(msg={"start": "已启动", "stop": "已停止", "restart": "已重启"}[action])


@router.post("/{source_id}/start", dependencies=[CTRL])
def start(source_id: int, request: Request, db: Session = Depends(get_db),
          me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    return _control(source_id, "start", request, db, me)


@router.post("/{source_id}/stop", dependencies=[CTRL])
def stop(source_id: int, request: Request, db: Session = Depends(get_db),
         me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    return _control(source_id, "stop", request, db, me)


@router.post("/{source_id}/restart", dependencies=[CTRL])
def restart(source_id: int, request: Request, db: Session = Depends(get_db),
            me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    return _control(source_id, "restart", request, db, me)
