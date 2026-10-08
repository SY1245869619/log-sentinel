"""审计日志：模型与记录函数（界面不可删除，保留 180 天）。"""
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, String
from sqlalchemy.orm import Session

from ..database import Base


class AuditLog(Base):
    __tablename__ = "ls_audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    username = Column(String(64))
    action = Column(String(64), nullable=False)   # LOGIN/CREATE/UPDATE/DELETE/EXPORT/COLLECTOR_CTRL...
    target = Column(String(255))
    ip = Column(String(64))
    result = Column(String(16), nullable=False, default="SUCCESS")  # SUCCESS/FAIL
    detail = Column(String(1024))
    created_at = Column(DateTime, nullable=False, default=datetime.now)


def record_audit(db: Session, *, user_id: int | None, username: str | None,
                 action: str, target: str | None = None, ip: str | None = None,
                 result: str = "SUCCESS", detail: str | None = None) -> None:
    """记录审计日志（失败不阻断主流程）。"""
    try:
        db.add(AuditLog(
            user_id=user_id, username=username, action=action, target=target,
            ip=ip, result=result, detail=(detail or "")[:1000] or None,
        ))
        db.commit()
    except Exception:
        db.rollback()
