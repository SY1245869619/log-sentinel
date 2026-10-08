"""通知流水线（需求 §4.12）：异步队列 + 钉钉限流 + 阶梯重试 + 死信。

- 聚合（§4.9）：开启聚合的规则先入 Redis 列表，窗口到期由调度器合并发送
- 恢复（§4.8）：调度器轮询告警态，recover_window 无命中发送恢复通知
- 限流：钉钉 20 条/分钟，CRITICAL 优先，MAJOR/MINOR 延迟重排
"""
import json
import logging
import queue
import threading
from datetime import datetime

from ...common import text_opt
from ...config import settings
from ...database import SessionLocal, redis_client
from ...models import (AlertRecord, AlertRule, ErrorLog, Host, LogSource,
                       MentionRule, NotifyChannel, NotifyFailRecord,
                       NotifyRecord, Project)
from ..channels.router import send_by_channel
from ..system import sse

logger = logging.getLogger("logsentinel.pipeline")

_queue: queue.Queue = queue.Queue(maxsize=settings.notify_queue_capacity)
SEVERITY_ORDER = {"CRITICAL": 0, "MAJOR": 1, "MINOR": 2}
_workers_started = False


# ---------------- 模板渲染与消息构建 ----------------

SEVERITY_COLORS = {"CRITICAL": "#cf1322", "MAJOR": "#d46b08", "MINOR": "#8c8c8c"}

DEFAULT_TEMPLATE = (
    "#### ⚠️ [${env}] ${project} · ${level}\n\n"
    "> **项目**：${project}\n"
    "> **主机**：${host}\n"
    "> **级别**：<font color=\"${sev_color}\">${level}</font>\n"
    "> **时间**：${time}\n"
    "> **错误码**：${errorCode}${keyword_part}\n\n"
    "---\n\n"
    "**错误摘要**\n\n"
    "<font color=\"${sev_color}\">${summary}</font>\n\n"
    "**错误日志**\n\n"
    "```\n${content}\n```\n\n"
    "**日志文件**：${file}\n\n"
    "${mentions}"
)


def render_template(template: str, ctx: dict) -> str:
    result = template
    for k, v in ctx.items():
        result = result.replace("${" + k + "}", str(v if v is not None else "-"))
    return result


def resolve_mentions(db, rule: AlertRule, host: Host, project: Project) -> list[MentionRule]:
    """@人三级优先级：规则级 > 主机级 > 项目级。"""
    if rule.mention_id:
        m = db.query(MentionRule).filter(MentionRule.id == rule.mention_id).first()
        if m:
            return [m]
    host_mentions = db.query(MentionRule).filter(
        MentionRule.scope == "HOST", MentionRule.ref_id == host.id).all()
    if host_mentions:
        return host_mentions
    if project.default_mention_id:
        m = db.query(MentionRule).filter(MentionRule.id == project.default_mention_id).first()
        if m:
            return [m]
    return []


def resolve_channel(db, project: Project) -> NotifyChannel | None:
    if project.notify_channel_id:
        c = db.query(NotifyChannel).filter(
            NotifyChannel.id == project.notify_channel_id, NotifyChannel.enabled == 1).first()
        if c:
            return c
    # 兜底：第一个启用的钉钉渠道
    return db.query(NotifyChannel).filter(
        NotifyChannel.type == "dingtalk", NotifyChannel.enabled == 1).first()


def build_message(db, rule, ctx, project, host, source, error_log) -> dict:
    mentions = resolve_mentions(db, rule, host, project)
    mention_text = " ".join(f"@{m.name}" for m in mentions)
    mobiles = [m.mobile for m in mentions if m.mobile]
    template = ctx.template.content_template if ctx and ctx.template else DEFAULT_TEMPLATE
    env = host.env or source.env or project.env or "-"
    raw_content = error_log.optimized_content or ""
    summary = text_opt.extract_summary(raw_content)
    level = error_log.level or rule.severity
    # 关键字部分：仅有关键字命中词时展示（错误码规则不显示）
    keyword_part = (f"　**关键字**：{error_log.keyword}" if error_log.keyword else "")
    content = render_template(template, {
        "project": project.name, "host": host.ip, "env": env,
        "level": level,
        "sev_color": SEVERITY_COLORS.get(rule.severity, "#d46b08"),
        "time": error_log.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
        "errorCode": error_log.error_code or "-",
        "keyword": error_log.keyword or "-",
        "keyword_part": keyword_part,
        "file": error_log.file_path or "-",
        "summary": summary,
        # 完整日志（optimize 阶段已按 4000 字节安全截断）
        "content": raw_content,
        "mentions": mention_text,
    })
    # 钉钉消息列表预览显示的标题：带上摘要一眼看懂
    return {"title": f"【LogSentinel】{project.name}：{summary[:30]}",
            "content": content, "at_mobiles": mobiles}


# ---------------- 分发入口（引擎调用） ----------------

def dispatch(rule, ctx, project, host, source, error_log) -> None:
    if rule.aggregate_notify:
        # §4.9 聚合：入 Redis 列表，窗口到期合并发送
        key = f"ls:agg:{rule.id}:{project.id}"
        redis_client.rpush(key, json.dumps({
            "error_log_id": error_log.id,
            "occurred_at": error_log.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
            "severity": rule.severity,
        }, ensure_ascii=False))
        ts_key = f"ls:aggts:{rule.id}:{project.id}"
        redis_client.set(ts_key, datetime.now().timestamp(), nx=True,
                         ex=rule.aggregate_window_seconds * 3)
        return

    db = SessionLocal()
    try:
        channel = resolve_channel(db, project)
        if not channel:
            logger.warning("无可用通知渠道，告警 %s 未发送", error_log.id)
            return
        msg = build_message(db, rule, ctx, project, host, source, error_log)
        _enqueue({
            "kind": "alert", "severity": rule.severity, "attempts": 0, "delay_count": 0,
            "channel_id": channel.id, "alert_id": error_log.id,
            "title": msg["title"], "content": msg["content"],
            "at_mobiles": msg["at_mobiles"],
        })
        sse.publish({"type": "alert", "severity": rule.severity,
                     "project": project.name, "error_log_id": error_log.id})
    finally:
        db.close()


def _enqueue(item: dict) -> None:
    try:
        _queue.put_nowait(item)
    except queue.Full:
        # 队列满：丢弃 MINOR 并记录（§4.12 背压）
        if item.get("severity") == "MINOR":
            logger.error("通知队列已满，丢弃 MINOR 告警: %s", item.get("title"))
        else:
            logger.error("通知队列已满，阻塞写入: %s", item.get("title"))
            _queue.put(item)


# ---------------- 消费 worker ----------------

def start_workers() -> None:
    global _workers_started
    if _workers_started:
        return
    _workers_started = True
    for i in range(settings.notify_core_pool_size):
        t = threading.Thread(target=_consume, name=f"notify-worker-{i}", daemon=True)
        t.start()
    logger.info("通知流水线已启动 %d 个 worker", settings.notify_core_pool_size)


def _consume() -> None:
    while True:
        item = _queue.get()
        try:
            _send(item)
        except Exception:
            logger.exception("通知发送处理异常: %s", item)
        finally:
            _queue.task_done()


def _rate_limited(channel_type: str, severity: str) -> bool:
    """钉钉限流：20 条/分钟。CRITICAL 不限（仍计数）。"""
    if channel_type != "dingtalk":
        return False
    minute_key = datetime.now().strftime("ls:rate:dt:%Y%m%d%H%M")
    count = redis_client.incr(minute_key)
    redis_client.expire(minute_key, 70)
    if count <= settings.dingtalk_rate_per_minute:
        return False
    return severity != "CRITICAL"


def _send(item: dict) -> None:
    db = SessionLocal()
    try:
        channel = db.query(NotifyChannel).filter(NotifyChannel.id == item["channel_id"]).first()
        if not channel or not channel.enabled:
            _record(db, item, "FAILED", "渠道不存在或已停用")
            return
        item["channel_type"] = channel.type

        if _rate_limited(channel.type, item.get("severity", "MAJOR")):
            item["delay_count"] = item.get("delay_count", 0) + 1
            if item["delay_count"] > 60 and item.get("severity") == "MINOR":
                _record(db, item, "FAILED", "限流排队超时丢弃")
                return
            threading.Timer(5, _enqueue, args=(item,)).start()
            return

        success, message = send_by_channel(
            channel, item["title"], item["content"], item.get("at_mobiles"))

        if success:
            _record(db, item, "SUCCESS", message)
            sse.publish({"type": "notify", "status": "SUCCESS",
                         "channel": channel.name, "title": item["title"]})
        else:
            intervals = settings.retry_intervals
            if item["attempts"] < len(intervals):
                item["attempts"] += 1
                threading.Timer(intervals[item["attempts"] - 1],
                                _enqueue, args=(item,)).start()
                logger.warning("通知失败，%ds 后第 %d 次重试: %s",
                               intervals[item["attempts"] - 1], item["attempts"], message)
            else:
                _record(db, item, "FAILED", message)
                _dead_letter(db, item, message)
                sse.publish({"type": "notify", "status": "FAILED",
                             "channel": channel.name, "title": item["title"]})
    finally:
        db.close()


def _record(db, item: dict, status: str, message: str) -> None:
    try:
        db.add(NotifyRecord(
            alert_id=item.get("alert_id"), channel_id=item.get("channel_id"),
            channel_type=item.get("channel_type"),
            request_body=item.get("content", "")[:6000],
            response_body=message[:4000] if message else None,
            status=status, retry_count=item.get("attempts", 0),
            error_msg=message[:1000] if status == "FAILED" else None))
        db.commit()
    except Exception:
        db.rollback()


def _dead_letter(db, item: dict, message: str) -> None:
    try:
        db.add(NotifyFailRecord(
            channel_id=item.get("channel_id"), alert_id=item.get("alert_id"),
            request_body=json.dumps({
                "title": item.get("title"), "content": item.get("content"),
                "at_mobiles": item.get("at_mobiles"),
            }, ensure_ascii=False)[:6000],
            error_msg=(message or "")[:1000], retry_count=item.get("attempts", 0),
            status="FAILED"))
        db.commit()
    except Exception:
        db.rollback()


# ---------------- 调度任务（scheduler 周期调用） ----------------

def flush_aggregations() -> None:
    """§4.9 聚合窗口到期合并发送（每 10s 检查一次）。"""
    now = datetime.now().timestamp()
    for ts_key in redis_client.scan_iter("ls:aggts:*"):
        try:
            first_ts = float(redis_client.get(ts_key) or 0)
            _, _, rule_id, project_id = ts_key.split(":")
            agg_key = f"ls:agg:{rule_id}:{project_id}"
            db = SessionLocal()
            try:
                rule = db.query(AlertRule).filter(AlertRule.id == int(rule_id)).first()
                window = rule.aggregate_window_seconds if rule else 60
                if now - first_ts < window:
                    continue
                items = [json.loads(x) for x in redis_client.lrange(agg_key, 0, -1)]
                redis_client.delete(agg_key, ts_key)
                if not items or not rule:
                    continue
                project = db.query(Project).filter(Project.id == int(project_id)).first()
                channel = resolve_channel(db, project) if project else None
                if not project or not channel:
                    continue
                lines = [f"### 【LogSentinel 聚合告警】{project.name}",
                         f"规则：{rule.name}（{window}s 内 {len(items)} 条）\n"]
                for it in items[:10]:  # 最多附 10 条摘要
                    log = db.query(ErrorLog).filter(ErrorLog.id == it["error_log_id"]).first()
                    if log:
                        lines.append(f"- [{it['occurred_at']}] "
                                     f"{text_opt.truncate_bytes(log.optimized_content or '', 200)}")
                if len(items) > 10:
                    lines.append(f"... 等 {len(items)} 条")
                _enqueue({
                    "kind": "aggregate", "severity": rule.severity,
                    "attempts": 0, "delay_count": 0, "channel_id": channel.id,
                    "alert_id": items[0]["error_log_id"],
                    "title": f"【LogSentinel 聚合告警】{project.name}",
                    "content": "\n".join(lines), "at_mobiles": [],
                })
            finally:
                db.close()
        except Exception:
            logger.exception("聚合 flush 异常: %s", ts_key)


def check_recoveries() -> None:
    """§4.8 恢复判定：进入告警态后 recover_window 秒无命中 → 发送恢复通知。"""
    now = datetime.now().timestamp()
    for key in redis_client.scan_iter("ls:alerted:*"):
        try:
            _, _, rule_id, source_id = key.split(":")
            last_hit = float(redis_client.get(f"ls:lasthit:{rule_id}:{source_id}") or 0)
            db = SessionLocal()
            try:
                rule = db.query(AlertRule).filter(AlertRule.id == int(rule_id)).first()
                if not rule or not rule.recover_notify:
                    redis_client.delete(key)
                    continue
                if now - last_hit < rule.recover_window_seconds:
                    continue
                source = db.query(LogSource).filter(LogSource.id == int(source_id)).first()
                project = db.query(Project).filter(Project.id == source.project_id).first() if source else None
                channel = resolve_channel(db, project) if project else None
                if channel and project:
                    _enqueue({
                        "kind": "recovery", "severity": "MINOR",
                        "attempts": 0, "delay_count": 0, "channel_id": channel.id,
                        "alert_id": None,
                        "title": f"【LogSentinel】{project.name} 已恢复",
                        "content": (
                            f"#### ✅ {project.name} 告警恢复\n\n"
                            f"> **规则**: {rule.name}\n"
                            f"> **说明**: 已连续 {rule.recover_window_seconds} 秒无新命中，判定恢复。"
                        ),
                        "at_mobiles": [],
                    })
                db.add(AlertRecord(rule_id=rule.id, rule_name=rule.name,
                                   project_id=project.id if project else None,
                                   log_source_id=int(source_id), severity=rule.severity,
                                   status="NOTIFIED", notified_at=datetime.now()))
                db.commit()
                redis_client.delete(key)
            finally:
                db.close()
        except Exception:
            logger.exception("恢复判定异常: %s", key)
