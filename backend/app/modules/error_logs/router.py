"""报错日志：查询 / 详情 / 删除 / 批量删除 / CSV 导出（导出限 OPS+ 且记审计）。"""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok, page_result
from ...database import get_db
from ...models import ErrorLog, Host, LogSource, Project
from ..auth.deps import ROLE_ADMIN, ROLE_OPS, CurrentUser, client_ip, require_roles

router = APIRouter(prefix="/api/v1/error-logs", tags=["报错日志"])

OPS_WRITE = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))
EXPORT_LIMIT = 10000


class BatchDeleteIn(BaseModel):
    ids: list[int]


def _to_dict(e: ErrorLog, names: dict) -> dict:
    return {
        "id": e.id, "project_id": e.project_id, "project_name": names["projects"].get(e.project_id),
        "host_id": e.host_id, "host_name": names["hosts"].get(e.host_id),
        "log_source_id": e.log_source_id, "log_source_name": names["sources"].get(e.log_source_id),
        "file_path": e.file_path, "line_no": e.line_no, "level": e.level,
        "error_code": e.error_code, "keyword": e.keyword,
        "raw_content": e.raw_content, "optimized_content": e.optimized_content,
        "occurred_at": e.occurred_at, "created_at": e.created_at,
        "alert_status": e.alert_status, "fingerprint": e.fingerprint,
    }


def _names(db: Session, rows: list[ErrorLog]) -> dict:
    pids = {r.project_id for r in rows}
    hids = {r.host_id for r in rows}
    sids = {r.log_source_id for r in rows}
    return {
        "projects": {p.id: p.name for p in db.query(Project).filter(Project.id.in_(pids))} if pids else {},
        "hosts": {h.id: h.name for h in db.query(Host).filter(Host.id.in_(hids))} if hids else {},
        "sources": {s.id: s.name for s in db.query(LogSource).filter(LogSource.id.in_(sids))} if sids else {},
    }


def _query(db: Session, project_id, host_id, level, error_code, keyword,
           alert_status, start_time, end_time):
    q = db.query(ErrorLog)
    if project_id:
        q = q.filter(ErrorLog.project_id == project_id)
    if host_id:
        q = q.filter(ErrorLog.host_id == host_id)
    if level:
        q = q.filter(ErrorLog.level == level)
    if error_code:
        q = q.filter(ErrorLog.error_code == error_code)
    if keyword:
        q = q.filter(ErrorLog.keyword.like(f"%{keyword}%"))
    if alert_status:
        q = q.filter(ErrorLog.alert_status == alert_status)
    if start_time:
        q = q.filter(ErrorLog.occurred_at >= start_time)
    if end_time:
        q = q.filter(ErrorLog.occurred_at <= end_time)
    return q


@router.get("")
def list_error_logs(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
                    project_id: int | None = None, host_id: int | None = None,
                    level: str | None = None, error_code: str | None = None,
                    keyword: str | None = None, alert_status: str | None = None,
                    start_time: datetime | None = None, end_time: datetime | None = None,
                    db: Session = Depends(get_db)):
    q = _query(db, project_id, host_id, level, error_code, keyword,
               alert_status, start_time, end_time)
    total = q.count()
    items = q.order_by(ErrorLog.id.desc()).offset((page - 1) * size).limit(size).all()
    names = _names(db, items)
    return page_result([_to_dict(e, names) for e in items], total, page, size)


@router.get("/export", dependencies=[OPS_WRITE])
def export_error_logs(request: Request, project_id: int | None = None,
                      host_id: int | None = None, level: str | None = None,
                      error_code: str | None = None, keyword: str | None = None,
                      alert_status: str | None = None,
                      start_time: datetime | None = None, end_time: datetime | None = None,
                      db: Session = Depends(get_db),
                      me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    q = _query(db, project_id, host_id, level, error_code, keyword,
               alert_status, start_time, end_time)
    rows = q.order_by(ErrorLog.id.desc()).limit(EXPORT_LIMIT).all()
    names = _names(db, rows)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "项目", "主机", "日志源", "文件", "行号", "级别",
                     "错误码", "关键字", "优化后内容(已脱敏)", "发生时间", "告警状态"])
    for e in rows:
        writer.writerow([
            e.id, names["projects"].get(e.project_id), names["hosts"].get(e.host_id),
            names["sources"].get(e.log_source_id), e.file_path, e.line_no, e.level,
            e.error_code, e.keyword,
            (e.optimized_content or "").replace("\r", " ")[:2000],
            e.occurred_at, e.alert_status,
        ])
    record_audit(db, user_id=me.id, username=me.username, action="EXPORT",
                 target="error_logs", ip=client_ip(request),
                 detail=f"导出 {len(rows)} 条")
    # utf-8-sig：Excel 打开中文不乱码
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=error_logs.csv"},
    )


@router.get("/{log_id}")
def get_error_log(log_id: int, db: Session = Depends(get_db)):
    e = db.query(ErrorLog).filter(ErrorLog.id == log_id).first()
    if not e:
        raise BizException("记录不存在", code=404)
    return ok(_to_dict(e, _names(db, [e])))


@router.delete("/{log_id}", dependencies=[OPS_WRITE])
def delete_error_log(log_id: int, request: Request, db: Session = Depends(get_db),
                     me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    e = db.query(ErrorLog).filter(ErrorLog.id == log_id).first()
    if not e:
        raise BizException("记录不存在", code=404)
    db.delete(e)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target=f"error_log:{log_id}", ip=client_ip(request))
    return ok(msg="删除成功")


@router.post("/batch-delete", dependencies=[OPS_WRITE])
def batch_delete(body: BatchDeleteIn, request: Request, db: Session = Depends(get_db),
                 me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    if not body.ids:
        raise BizException("请选择要删除的记录", code=400)
    count = db.query(ErrorLog).filter(ErrorLog.id.in_(body.ids)).delete(synchronize_session=False)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target="error_logs", ip=client_ip(request),
                 detail=f"批量删除 {count} 条")
    return ok(msg=f"已删除 {count} 条")
