"""告警记录 / 通知记录 / 通知失败记录（含人工重发）。"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok, page_result
from ...database import get_db
from ...models import (AlertRecord, ErrorLog, Host, NotifyChannel,
                       NotifyFailRecord, NotifyRecord, Project)
from ..auth.deps import ROLE_ADMIN, ROLE_OPS, CurrentUser, client_ip, require_roles
from ..channels.router import send_by_channel

router = APIRouter(prefix="/api/v1", tags=["告警与通知记录"])

OPS_WRITE = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))


@router.get("/alerts")
def list_alerts(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
                project_id: int | None = None, severity: str | None = None,
                status: str | None = None,
                start_time: datetime | None = None, end_time: datetime | None = None,
                db: Session = Depends(get_db)):
    q = db.query(AlertRecord)
    if project_id:
        q = q.filter(AlertRecord.project_id == project_id)
    if severity:
        q = q.filter(AlertRecord.severity == severity)
    if status:
        q = q.filter(AlertRecord.status == status)
    if start_time:
        q = q.filter(AlertRecord.created_at >= start_time)
    if end_time:
        q = q.filter(AlertRecord.created_at <= end_time)
    total = q.count()
    items = q.order_by(AlertRecord.id.desc()).offset((page - 1) * size).limit(size).all()
    names = {p.id: p.name for p in db.query(Project).all()}
    return page_result([{
        "id": a.id, "rule_id": a.rule_id, "rule_name": a.rule_name,
        "project_id": a.project_id, "project_name": names.get(a.project_id),
        "log_source_id": a.log_source_id, "error_log_id": a.error_log_id,
        "severity": a.severity, "status": a.status,
        "notified_at": a.notified_at, "created_at": a.created_at,
    } for a in items], total, page, size)


@router.get("/notify-records")
def list_notify_records(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
                        status: str | None = None, channel_id: int | None = None,
                        start_time: datetime | None = None, end_time: datetime | None = None,
                        db: Session = Depends(get_db)):
    q = db.query(NotifyRecord)
    if status:
        q = q.filter(NotifyRecord.status == status)
    if channel_id:
        q = q.filter(NotifyRecord.channel_id == channel_id)
    if start_time:
        q = q.filter(NotifyRecord.created_at >= start_time)
    if end_time:
        q = q.filter(NotifyRecord.created_at <= end_time)
    total = q.count()
    items = q.order_by(NotifyRecord.id.desc()).offset((page - 1) * size).limit(size).all()
    channels = {c.id: c.name for c in db.query(NotifyChannel).all()}
    return page_result([{
        "id": r.id, "alert_id": r.alert_id, "channel_id": r.channel_id,
        "channel_name": channels.get(r.channel_id), "channel_type": r.channel_type,
        "request_body": r.request_body, "response_body": r.response_body,
        "status": r.status, "retry_count": r.retry_count,
        "error_msg": r.error_msg, "created_at": r.created_at,
    } for r in items], total, page, size)


@router.get("/notify-fail-records")
def list_fail_records(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
                      status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(NotifyFailRecord)
    if status:
        q = q.filter(NotifyFailRecord.status == status)
    total = q.count()
    items = q.order_by(NotifyFailRecord.id.desc()).offset((page - 1) * size).limit(size).all()
    channels = {c.id: c.name for c in db.query(NotifyChannel).all()}
    return page_result([{
        "id": r.id, "channel_id": r.channel_id, "channel_name": channels.get(r.channel_id),
        "alert_id": r.alert_id, "request_body": r.request_body,
        "error_msg": r.error_msg, "retry_count": r.retry_count,
        "status": r.status, "resent_at": r.resent_at, "created_at": r.created_at,
    } for r in items], total, page, size)


@router.post("/notify-fail-records/{record_id}/resend", dependencies=[OPS_WRITE])
def resend(record_id: int, request: Request, db: Session = Depends(get_db),
           me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    """死信人工重发（OPS+，记审计）。"""
    record = db.query(NotifyFailRecord).filter(NotifyFailRecord.id == record_id).first()
    if not record:
        raise BizException("记录不存在", code=404)
    channel = db.query(NotifyChannel).filter(NotifyChannel.id == record.channel_id).first()
    if not channel or not channel.enabled:
        raise BizException("渠道不存在或已停用", code=400)
    try:
        body = json.loads(record.request_body or "{}")
    except json.JSONDecodeError:
        raise BizException("原始请求内容无法解析", code=400)

    success, message = send_by_channel(
        channel, body.get("title", "LogSentinel 重发"),
        body.get("content", ""), body.get("at_mobiles"))
    record.status = "RESEND_SUCCESS" if success else "RESEND_FAILED"
    record.resent_at = datetime.now()
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="RESEND",
                 target=f"notify_fail:{record_id}", ip=client_ip(request),
                 result="SUCCESS" if success else "FAIL", detail=message)
    if not success:
        raise BizException(f"重发失败：{message}", code=400)
    return ok(msg="重发成功")
