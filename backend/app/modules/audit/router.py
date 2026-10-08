"""审计日志查询（只读，界面不提供删除）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...common.response import page_result
from ...database import get_db
from ...common.audit import AuditLog

router = APIRouter(prefix="/api/v1/audit-logs", tags=["操作审计"])


@router.get("")
def list_audit_logs(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
                    username: str | None = None, action: str | None = None,
                    start_time: datetime | None = None, end_time: datetime | None = None,
                    db: Session = Depends(get_db)):
    q = db.query(AuditLog)
    if username:
        q = q.filter(AuditLog.username.like(f"%{username}%"))
    if action:
        q = q.filter(AuditLog.action == action)
    if start_time:
        q = q.filter(AuditLog.created_at >= start_time)
    if end_time:
        q = q.filter(AuditLog.created_at <= end_time)
    total = q.count()
    items = q.order_by(AuditLog.id.desc()).offset((page - 1) * size).limit(size).all()
    return page_result([{
        "id": a.id, "user_id": a.user_id, "username": a.username,
        "action": a.action, "target": a.target, "ip": a.ip,
        "result": a.result, "detail": a.detail, "created_at": a.created_at,
    } for a in items], total, page, size)
