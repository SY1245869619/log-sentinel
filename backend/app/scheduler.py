"""周期任务调度（APScheduler）：

- 规则缓存刷新（30s，配置热更新）
- 聚合窗口 flush（10s）
- 恢复判定（15s）
- 数据保留清理（每日 03:00，保留天数取系统设置）
"""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings
from .database import SessionLocal
from .models import Agent, AlertRecord, ErrorLog, NotifyFailRecord, NotifyRecord
from .common.audit import AuditLog
from .modules.notify import engine, pipeline
from .modules.system.router import get_setting_int

logger = logging.getLogger("logsentinel.scheduler")

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def retention_cleanup() -> None:
    """按保留策略清理历史数据（审计日志只按天数清理，不提供界面删除）。"""
    db = SessionLocal()
    try:
        error_days = get_setting_int(db, "retention_error_log_days", settings.retention_error_log_days)
        record_days = get_setting_int(db, "retention_record_days", settings.retention_record_days)
        audit_days = get_setting_int(db, "retention_audit_days", settings.retention_audit_days)

        def cut(days: int) -> datetime:
            return datetime.now() - timedelta(days=days)

        n1 = db.query(ErrorLog).filter(ErrorLog.created_at < cut(error_days)).delete(synchronize_session=False)
        n2 = db.query(AlertRecord).filter(AlertRecord.created_at < cut(record_days)).delete(synchronize_session=False)
        n3 = db.query(NotifyRecord).filter(NotifyRecord.created_at < cut(record_days)).delete(synchronize_session=False)
        n4 = db.query(NotifyFailRecord).filter(NotifyFailRecord.created_at < cut(record_days)).delete(synchronize_session=False)
        n5 = db.query(AuditLog).filter(AuditLog.created_at < cut(audit_days)).delete(synchronize_session=False)
        db.commit()
        if any([n1, n2, n3, n4, n5]):
            logger.info("保留清理: error_log=%d alert=%d notify=%d fail=%d audit=%d",
                        n1, n2, n3, n4, n5)
    except Exception:
        db.rollback()
        logger.exception("保留清理失败")
    finally:
        db.close()


def mark_offline_agents() -> None:
    """90 秒无心跳的 Agent 标记为离线。"""
    from .modules.agents.api import OFFLINE_AFTER
    db = SessionLocal()
    try:
        deadline = datetime.now() - timedelta(seconds=OFFLINE_AFTER)
        n = db.query(Agent).filter(
            Agent.status == "ONLINE",
            (Agent.last_heartbeat.is_(None)) | (Agent.last_heartbeat < deadline),
        ).update({"status": "OFFLINE"}, synchronize_session=False)
        db.commit()
        if n:
            logger.info("Agent 离线标记: %d 个", n)
    except Exception:
        db.rollback()
    finally:
        db.close()


def start_scheduler() -> None:
    engine.refresh_rule_cache()
    scheduler.add_job(engine.refresh_rule_cache, "interval", seconds=30,
                      id="refresh_rule_cache", replace_existing=True)
    scheduler.add_job(pipeline.flush_aggregations, "interval", seconds=10,
                      id="flush_aggregations", replace_existing=True)
    scheduler.add_job(pipeline.check_recoveries, "interval", seconds=15,
                      id="check_recoveries", replace_existing=True)
    scheduler.add_job(mark_offline_agents, "interval", seconds=60,
                      id="mark_offline_agents", replace_existing=True)
    scheduler.add_job(retention_cleanup, "cron", hour=3, minute=0,
                      id="retention_cleanup", replace_existing=True)
    scheduler.start()
    logger.info("调度器已启动")
