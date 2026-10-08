"""告警规则：CRUD + 日志源/关键字/错误码多对多关联。"""
import re

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok, page_result
from ...database import get_db
from ...models import (AlertRule, AlertRuleSource, ErrorCode, Keyword,
                       LogSource, RuleErrorCode, RuleKeyword)
from ..auth.deps import ROLE_ADMIN, ROLE_OPS, CurrentUser, client_ip, require_roles

router = APIRouter(prefix="/api/v1/alert-rules", tags=["告警规则"])

WRITE = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    severity: str = Field(default="MAJOR", pattern="^(CRITICAL|MAJOR|MINOR)$")
    match_type: str = Field(default="KEYWORD", pattern="^(KEYWORD|REGEX|ERROR_CODE|LOG_LEVEL)$")
    match_content: str | None = None  # REGEX / LOG_LEVEL 直接存内容
    alert_enabled: int = 1
    silence_seconds: int = Field(default=300, ge=0)
    window_seconds: int | None = Field(default=None, ge=1)
    threshold_count: int | None = Field(default=None, ge=1)
    consecutive_count: int | None = Field(default=None, ge=1)
    recover_notify: int = 0
    recover_window_seconds: int = Field(default=300, ge=1)
    aggregate_notify: int = 0
    aggregate_window_seconds: int = Field(default=60, ge=1)
    maintenance_start: str | None = None  # HH:mm
    maintenance_end: str | None = None
    mention_id: int | None = None
    template_id: int | None = None
    enabled: int = 1
    # 关联资源
    log_source_ids: list[int] = []
    keyword_ids: list[int] = []
    error_code_ids: list[int] = []


def _validate(body: RuleIn, db: Session) -> None:
    if body.match_type == "REGEX":
        if not body.match_content:
            raise BizException("正则匹配类型必须填写匹配内容", code=400)
        try:
            re.compile(body.match_content)
        except re.error:
            raise BizException("正则表达式无法编译", code=400)
    if body.match_type == "KEYWORD" and not body.keyword_ids:
        raise BizException("关键字规则至少关联一个关键字", code=400)
    if body.match_type == "ERROR_CODE" and not body.error_code_ids:
        raise BizException("错误码规则至少关联一个错误码", code=400)
    if not body.log_source_ids:
        raise BizException("至少关联一个日志源", code=400)
    for t in (body.maintenance_start, body.maintenance_end):
        if t and not HHMM.match(t):
            raise BizException("维护窗口时间格式必须为 HH:mm", code=400)
    if body.maintenance_start and not body.maintenance_end:
        raise BizException("维护窗口需要同时填写开始与结束时间", code=400)
    for sid in body.log_source_ids:
        if not db.query(LogSource).filter(LogSource.id == sid).first():
            raise BizException(f"日志源不存在: {sid}", code=400)
    for kid in body.keyword_ids:
        if not db.query(Keyword).filter(Keyword.id == kid).first():
            raise BizException(f"关键字不存在: {kid}", code=400)
    for eid in body.error_code_ids:
        if not db.query(ErrorCode).filter(ErrorCode.id == eid).first():
            raise BizException(f"错误码不存在: {eid}", code=400)


def _save_refs(db: Session, rule_id: int, body: RuleIn) -> None:
    db.query(AlertRuleSource).filter(AlertRuleSource.rule_id == rule_id).delete()
    db.query(RuleKeyword).filter(RuleKeyword.rule_id == rule_id).delete()
    db.query(RuleErrorCode).filter(RuleErrorCode.rule_id == rule_id).delete()
    for sid in set(body.log_source_ids):
        db.add(AlertRuleSource(rule_id=rule_id, log_source_id=sid))
    for kid in set(body.keyword_ids):
        db.add(RuleKeyword(rule_id=rule_id, keyword_id=kid))
    for eid in set(body.error_code_ids):
        db.add(RuleErrorCode(rule_id=rule_id, error_code_id=eid))


def _to_dict(db: Session, r: AlertRule) -> dict:
    data = {c: getattr(r, c) for c in [
        "id", "name", "severity", "match_type", "match_content", "alert_enabled",
        "silence_seconds", "window_seconds", "threshold_count", "consecutive_count",
        "recover_notify", "recover_window_seconds", "aggregate_notify",
        "aggregate_window_seconds", "maintenance_start", "maintenance_end",
        "mention_id", "template_id", "enabled", "created_at", "updated_at"]}
    data["log_source_ids"] = [x.log_source_id for x in
                              db.query(AlertRuleSource).filter(AlertRuleSource.rule_id == r.id).all()]
    data["keyword_ids"] = [x.keyword_id for x in
                           db.query(RuleKeyword).filter(RuleKeyword.rule_id == r.id).all()]
    data["error_code_ids"] = [x.error_code_id for x in
                              db.query(RuleErrorCode).filter(RuleErrorCode.rule_id == r.id).all()]
    return data


@router.get("")
def list_rules(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
               name: str | None = None, severity: str | None = None,
               db: Session = Depends(get_db)):
    q = db.query(AlertRule)
    if name:
        q = q.filter(AlertRule.name.like(f"%{name}%"))
    if severity:
        q = q.filter(AlertRule.severity == severity)
    total = q.count()
    items = q.order_by(AlertRule.id.desc()).offset((page - 1) * size).limit(size).all()
    return page_result([_to_dict(db, r) for r in items], total, page, size)


@router.get("/{rule_id}")
def get_rule(rule_id: int, db: Session = Depends(get_db)):
    r = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not r:
        raise BizException("规则不存在", code=404)
    return ok(_to_dict(db, r))


@router.post("", dependencies=[WRITE])
def create_rule(body: RuleIn, request: Request, db: Session = Depends(get_db),
                me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    _validate(body, db)
    refs = body.model_dump(include={"log_source_ids", "keyword_ids", "error_code_ids"})
    r = AlertRule(**body.model_dump(exclude=set(refs)))
    db.add(r)
    db.flush()
    _save_refs(db, r.id, body)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="CREATE",
                 target=f"alert_rule:{r.name}", ip=client_ip(request))
    return ok(_to_dict(db, r), msg="创建成功")


@router.put("/{rule_id}", dependencies=[WRITE])
def update_rule(rule_id: int, body: RuleIn, request: Request,
                db: Session = Depends(get_db),
                me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    r = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not r:
        raise BizException("规则不存在", code=404)
    _validate(body, db)
    refs = {"log_source_ids", "keyword_ids", "error_code_ids"}
    for k, v in body.model_dump(exclude=refs).items():
        setattr(r, k, v)
    _save_refs(db, r.id, body)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="UPDATE",
                 target=f"alert_rule:{r.name}", ip=client_ip(request))
    return ok(_to_dict(db, r), msg="更新成功")


@router.delete("/{rule_id}", dependencies=[WRITE])
def delete_rule(rule_id: int, request: Request, db: Session = Depends(get_db),
                me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    r = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not r:
        raise BizException("规则不存在", code=404)
    db.query(AlertRuleSource).filter(AlertRuleSource.rule_id == rule_id).delete()
    db.query(RuleKeyword).filter(RuleKeyword.rule_id == rule_id).delete()
    db.query(RuleErrorCode).filter(RuleErrorCode.rule_id == rule_id).delete()
    db.delete(r)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target=f"alert_rule:{r.name}", ip=client_ip(request))
    return ok(msg="删除成功")
