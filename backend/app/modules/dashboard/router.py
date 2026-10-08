"""统计看板（需求 §3.10）：今日指标 / Top 榜 / 趋势 / 采集异常 / 最近告警。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...common.response import ok
from ...database import get_db
from ...models import (AlertRecord, CollectorState, ErrorLog, Host, LogSource,
                       NotifyRecord, Project)

router = APIRouter(prefix="/api/v1/dashboard", tags=["统计看板"])


@router.get("")
def dashboard(project_id: int | None = None,
              days: int = Query(7, ge=1, le=30),
              db: Session = Depends(get_db)):
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    def scoped(q):
        return q.filter(AlertRecord.project_id == project_id) if project_id else q

    # 今日指标
    today_alerts = scoped(db.query(func.count(AlertRecord.id))).filter(
        AlertRecord.created_at >= today_start).scalar() or 0
    today_notifies = db.query(func.count(NotifyRecord.id)).filter(
        NotifyRecord.created_at >= today_start).scalar() or 0
    today_notify_fails = db.query(func.count(NotifyRecord.id)).filter(
        NotifyRecord.created_at >= today_start,
        NotifyRecord.status == "FAILED").scalar() or 0

    # Top 项目（按告警数）
    top_projects = [
        {"project_id": pid, "project_name": name, "count": cnt}
        for pid, name, cnt in db.query(
            AlertRecord.project_id, Project.name, func.count(AlertRecord.id))
        .join(Project, Project.id == AlertRecord.project_id, isouter=True)
        .group_by(AlertRecord.project_id, Project.name)
        .order_by(func.count(AlertRecord.id).desc()).limit(5).all()
    ]

    # Top 错误码
    top_codes = [
        {"error_code": code, "count": cnt}
        for code, cnt in db.query(ErrorLog.error_code, func.count(ErrorLog.id))
        .filter(ErrorLog.error_code.isnot(None))
        .group_by(ErrorLog.error_code)
        .order_by(func.count(ErrorLog.id).desc()).limit(5).all()
    ]

    # 告警趋势（近 N 天，按日聚合）
    trend_start = today_start - timedelta(days=days - 1)
    raw_trend = dict(db.query(
        func.date(AlertRecord.created_at), func.count(AlertRecord.id))
        .filter(AlertRecord.created_at >= trend_start)
        .group_by(func.date(AlertRecord.created_at)).all())
    trend = []
    for i in range(days):
        day = (trend_start + timedelta(days=i)).date()
        trend.append({"date": day.strftime("%m-%d"), "count": int(raw_trend.get(day, 0))})

    # 采集异常与延迟
    collector_issues = []
    for st in db.query(CollectorState).all():
        delay = int((datetime.now() - st.last_heartbeat).total_seconds()) if st.last_heartbeat else None
        if st.status in ("ERROR", "RECONNECTING") or (delay is not None and delay > 60):
            collector_issues.append({
                "log_source_id": st.log_source_id, "status": st.status,
                "error_msg": st.error_msg, "retry_count": st.retry_count,
                "delay_seconds": delay, "last_heartbeat": st.last_heartbeat,
            })

    # 最近告警
    recent_alerts = [{
        "id": a.id, "rule_name": a.rule_name, "severity": a.severity,
        "status": a.status, "created_at": a.created_at,
        "project_name": names.get(a.project_id),
    } for a in scoped(db.query(AlertRecord)).order_by(AlertRecord.id.desc()).limit(10).all()
        for names in [{p.id: p.name for p in db.query(Project).all()}]]

    # 资源概览
    total_projects = db.query(func.count(Project.id)).scalar() or 0
    total_hosts = db.query(func.count(Host.id)).scalar() or 0
    total_sources = db.query(func.count(LogSource.id)).scalar() or 0
    running_collectors = db.query(func.count(CollectorState.id)).filter(
        CollectorState.status == "RUNNING").scalar() or 0

    # 告警级别分布（近 N 天）
    level_distribution = [
        {"severity": sev, "count": cnt}
        for sev, cnt in db.query(AlertRecord.severity, func.count(AlertRecord.id))
        .filter(AlertRecord.created_at >= trend_start)
        .group_by(AlertRecord.severity).all()
    ]

    return ok({
        "today_alerts": today_alerts,
        "today_notifies": today_notifies,
        "today_notify_fails": today_notify_fails,
        "total_projects": total_projects,
        "total_hosts": total_hosts,
        "total_log_sources": total_sources,
        "running_collectors": running_collectors,
        "level_distribution": level_distribution,
        "top_projects": top_projects,
        "top_error_codes": top_codes,
        "trend": trend,
        "collector_issues": collector_issues,
        "recent_alerts": recent_alerts,
    })
