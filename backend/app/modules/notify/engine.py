"""告警引擎：规则匹配 + 通知决策（语义严格对应需求 §4）。

- §4.1 指纹幂等：Redis SETNX ls:fp:*，24h 内同指纹只告警一次（at-least-once + 幂等）
- §4.6 滑动窗口：Redis ZSET
- §4.7 连续 N 次：未命中行清零
- §4.10 维护窗口：支持跨天，优先级最高
- §4.11 静默期：(rule_id, host_id, 匹配键) 三元组
规则缓存 30 秒热更新（见 scheduler）。
"""
import hashlib
import logging
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from ...common import text_opt
from ...database import SessionLocal, redis_client
from ...models import (AlertRecord, AlertRule, AlertRuleSource, ErrorCode,
                       ErrorLog, Host, Keyword, LogSource, MentionRule,
                       NotifyTemplate, Project, RuleErrorCode, RuleKeyword)
from . import pipeline

logger = logging.getLogger("logsentinel.engine")

# ---------------- 规则缓存 ----------------

@dataclass
class RuleCtx:
    rule: AlertRule
    keywords: list[Keyword] = field(default_factory=list)
    error_codes: list[ErrorCode] = field(default_factory=list)
    mention: MentionRule | None = None
    template: NotifyTemplate | None = None


_lock = threading.Lock()
_cache: dict[int, list[RuleCtx]] = {}  # log_source_id -> rules


def refresh_rule_cache() -> None:
    """重建规则缓存（周期调用，实现配置热更新）。"""
    db = SessionLocal()
    try:
        rules = db.query(AlertRule).filter(AlertRule.enabled == 1).all()
        new_cache: dict[int, list[RuleCtx]] = {}
        for r in rules:
            kid = [x.keyword_id for x in db.query(RuleKeyword).filter(RuleKeyword.rule_id == r.id)]
            eid = [x.error_code_id for x in db.query(RuleErrorCode).filter(RuleErrorCode.rule_id == r.id)]
            ctx = RuleCtx(
                rule=r,
                keywords=db.query(Keyword).filter(Keyword.id.in_(kid), Keyword.enabled == 1).all() if kid else [],
                error_codes=db.query(ErrorCode).filter(ErrorCode.id.in_(eid), ErrorCode.enabled == 1).all() if eid else [],
                mention=db.query(MentionRule).filter(MentionRule.id == r.mention_id).first() if r.mention_id else None,
                template=db.query(NotifyTemplate).filter(NotifyTemplate.id == r.template_id).first() if r.template_id else None,
            )
            for x in db.query(AlertRuleSource).filter(AlertRuleSource.rule_id == r.id):
                new_cache.setdefault(x.log_source_id, []).append(ctx)
        with _lock:
            _cache.clear()
            _cache.update(new_cache)
        logger.debug("规则缓存已刷新: %d 个日志源", len(new_cache))
    except Exception:
        logger.exception("规则缓存刷新失败")
    finally:
        db.close()


def _rules_of(source_id: int) -> list[RuleCtx]:
    with _lock:
        return list(_cache.get(source_id, []))


# ---------------- 匹配 ----------------

def _match_keyword(kw: Keyword, text: str) -> bool:
    if kw.match_op == "CONTAINS":
        return kw.pattern in text
    if kw.match_op == "NOT_CONTAINS":
        return kw.pattern in text  # 命中排除词（由调用方按排除语义处理）
    if kw.match_op == "EQUALS":
        return kw.pattern == text.strip()
    if kw.match_op == "REGEX":
        try:
            return re.search(kw.pattern, text) is not None
        except re.error:
            return False
    return False


def match_rule(ctx: RuleCtx, text: str) -> tuple[bool, str | None, str | None]:
    """返回 (是否命中, 匹配键[错误码/关键字], 命中关键字词)。

    排除语义：任一 NOT_CONTAINS 关键字在文本中出现 → 整体不命中（白名单）。
    """
    r = ctx.rule
    if r.match_type == "KEYWORD":
        for kw in ctx.keywords:
            if kw.match_op == "NOT_CONTAINS" and _match_keyword(kw, text):
                return False, None, None
        for kw in ctx.keywords:
            if kw.match_op != "NOT_CONTAINS" and _match_keyword(kw, text):
                return True, kw.pattern, kw.pattern
        return False, None, None

    if r.match_type == "REGEX":
        try:
            if re.search(r.match_content or "", text):
                return True, r.match_content, r.match_content
        except re.error:
            pass
        return False, None, None

    if r.match_type == "ERROR_CODE":
        for ec in ctx.error_codes:
            try:
                found = re.findall(ec.extract_regex, text)
            except re.error:
                continue
            # findall：无分组返回整体匹配串，有分组返回分组内容（多分组为元组）
            candidates: set[str] = set()
            for t in found:
                if isinstance(t, tuple):
                    candidates.update(g for g in t if g)
                else:
                    candidates.add(t)
            # 命中条件：候选即错误码；或整体匹配串中按词边界包含错误码
            # （兼容 "code":\s*123 这类带前缀的整体匹配）
            if ec.code in candidates or any(
                    re.search(rf"(?<![A-Za-z0-9_]){re.escape(ec.code)}(?![A-Za-z0-9_])", c)
                    for c in candidates):
                return True, ec.code, ec.code
        return False, None, None

    if r.match_type == "LOG_LEVEL":
        level = (r.match_content or "").upper()
        if level and re.search(rf"\b{re.escape(level)}\b", text):
            return True, level, level
        return False, None, None

    return False, None, None


# ---------------- 判定工具 ----------------

def _in_maintenance(rule: AlertRule, now: datetime) -> bool:
    """维护窗口：HH:mm，支持跨天（如 22:00-06:00）。"""
    if not rule.maintenance_start or not rule.maintenance_end:
        return False
    cur = now.strftime("%H:%M")
    s, e = rule.maintenance_start, rule.maintenance_end
    return s <= cur <= e if s <= e else (cur >= s or cur <= e)


def _check_silence(rule: AlertRule, host_id: int, match_key: str) -> bool:
    """静默期：True=处于静默（应抑制）。仅在触发时写入静默键。"""
    if not rule.silence_seconds:
        return False
    key = f"ls:silence:{rule.id}:{host_id}:{match_key or '-'}"
    return redis_client.exists(key) > 0


def _mark_silence(rule: AlertRule, host_id: int, match_key: str) -> None:
    if rule.silence_seconds:
        key = f"ls:silence:{rule.id}:{host_id}:{match_key or '-'}"
        redis_client.set(key, 1, ex=rule.silence_seconds)


def _eval_window(rule: AlertRule, source_id: int) -> bool:
    """§4.6 滑动窗口：窗口内命中数 >= threshold 触发，触发后清空重计。"""
    now = datetime.now().timestamp()
    key = f"ls:win:{rule.id}:{source_id}"
    # member 需带唯一后缀：同一时间戳的多次命中不能互相覆盖
    member = f"{now}:{uuid.uuid4().hex[:8]}"
    pipe = redis_client.pipeline()
    pipe.zadd(key, {member: now})
    pipe.zremrangebyscore(key, 0, now - rule.window_seconds)
    pipe.zcard(key)
    _, _, count = pipe.execute()
    if rule.window_seconds and rule.threshold_count and count >= rule.threshold_count:
        redis_client.delete(key)
        return True
    return False


def _eval_consecutive(rule: AlertRule, source_id: int) -> bool:
    """§4.7 连续 N 次。"""
    key = f"ls:cons:{rule.id}:{source_id}"
    count = redis_client.incr(key)
    if rule.consecutive_count and count >= rule.consecutive_count:
        redis_client.delete(key)
        return True
    return False


def reset_consecutive(rule_id: int, source_id: int) -> None:
    """未命中行清零连续计数（§4.7）。"""
    redis_client.delete(f"ls:cons:{rule_id}:{source_id}")


def _eval_trigger(rule: AlertRule, source_id: int) -> bool:
    """按规则类型判定是否触发。"""
    if rule.window_seconds and rule.threshold_count:
        return _eval_window(rule, source_id)
    if rule.consecutive_count:
        return _eval_consecutive(rule, source_id)
    return True  # 立即告警


def _fingerprint(project_id: int, source_id: int, file_path: str,
                 inode: str, start_offset: int, text: str) -> str:
    raw = f"{project_id}:{source_id}:{file_path}:{inode}:{start_offset}:{text[:512]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------- 主入口 ----------------

def process_entry(db: Session, source: LogSource, project: Project, host: Host,
                  file_path: str, inode: str, start_offset: int,
                  text: str, occurred_at: datetime) -> None:
    """处理一条合并后的日志条目（命中与未命中都会调用，用于连续计数清零）。"""
    for ctx in _rules_of(source.id):
        matched, match_key, hit_word = match_rule(ctx, text)
        rule = ctx.rule
        if not matched:
            if rule.consecutive_count:
                reset_consecutive(rule.id, source.id)
            continue

        # §4.1 指纹幂等
        fp = _fingerprint(project.id, source.id, file_path, inode, start_offset, text)
        if not redis_client.set(f"ls:fp:{fp}", 1, nx=True, ex=86400):
            continue

        # 恢复判定：记录最近命中时间
        redis_client.set(f"ls:lasthit:{rule.id}:{source.id}",
                         datetime.now().timestamp())

        # 决策流水线：维护窗口 → 是否告警 → 静默 → 触发判定
        now = datetime.now()
        if _in_maintenance(rule, now):
            status = "SUPPRESSED"
            triggered = False
        elif not rule.alert_enabled:
            status = "RECORD_ONLY"
            triggered = False
        elif _check_silence(rule, host.id, match_key):
            status = "SUPPRESSED"
            triggered = False
        else:
            triggered = _eval_trigger(rule, source.id)
            status = "RECORD_ONLY" if not triggered else (
                "AGGREGATED" if rule.aggregate_notify else "NOTIFIED")

        # 命中即落库（原始内容完整保留，优化后内容脱敏）
        # 关键字字段仅对关键字/正则规则记录命中词；错误码规则只记 error_code
        level = text_opt.extract_level(text)
        keyword_hit = hit_word if rule.match_type in ("KEYWORD", "REGEX") else None
        try:
            error_log = ErrorLog(
                project_id=project.id, host_id=host.id, log_source_id=source.id,
                file_path=file_path, level=level,
                error_code=match_key if rule.match_type == "ERROR_CODE" else None,
                keyword=keyword_hit, raw_content=text,
                optimized_content=text_opt.optimize(text),
                occurred_at=occurred_at, alert_status=status, fingerprint=fp)
            db.add(error_log)
            db.commit()
            db.refresh(error_log)
        except Exception:
            db.rollback()
            continue  # 指纹冲突等并发重复，跳过

        db.add(AlertRecord(
            rule_id=rule.id, rule_name=rule.name, project_id=project.id,
            host_id=host.id, log_source_id=source.id, error_log_id=error_log.id,
            severity=rule.severity, status=status,
            notified_at=now if status in ("NOTIFIED", "AGGREGATED") else None))
        db.commit()

        if not triggered:
            continue

        _mark_silence(rule, host.id, match_key)
        if rule.recover_notify and (rule.window_seconds or rule.consecutive_count):
            redis_client.set(f"ls:alerted:{rule.id}:{source.id}", 1)

        pipeline.dispatch(rule=rule, ctx=ctx, project=project, host=host,
                          source=source, error_log=error_log)
