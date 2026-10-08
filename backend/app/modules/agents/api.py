"""Agent 端 API（/api/v1/agent/*，Token 鉴权，不走 JWT）。

协议：HTTP + JSON（批量事件支持 gzip），与 Filebeat/FluentBit 等主流 Agent 一致。
"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, object_session

from ...common.response import ok
from ...database import get_db, redis_client
from ...models import Agent, CollectorState, Host, LogSource, Project
from ..notify import engine
from .auth import verify_agent

logger = logging.getLogger("logsentinel.agent")

router = APIRouter(prefix="/api/v1/agent", tags=["Agent上报"])

HEARTBEAT_INTERVAL = 30      # 心跳间隔（秒）
OFFLINE_AFTER = 90           # 超过该秒数无心跳视为离线
SCAN_KEY = "ls:agent:scan:{}"       # 扫描结果缓存
SCAN_REQ_KEY = "ls:agent:scanreq:{}"  # 扫描请求（管理端发起，心跳时下发）


# ---------------- 请求模型 ----------------

class RegisterReq(BaseModel):
    hostname: str = ""
    ip: str = ""
    os: str = ""
    arch: str = ""
    version: str = ""


class HeartbeatReq(BaseModel):
    version: str = ""
    events_sent: int = 0       # 累计上报事件数（供监控）
    queue_size: int = 0        # 当前积压（背压监控）


class LogEvent(BaseModel):
    file: str
    offset: int = 0            # 条目起始字节偏移（用于指纹幂等）
    line_no: int | None = None
    content: str
    occurred_at: datetime


class EventsReq(BaseModel):
    source_id: int
    inode: str = ""            # Agent 端文件标识（路径+设备/卷序列号即可）
    events: list[LogEvent] = Field(default_factory=list, max_length=200)


class ScanReportReq(BaseModel):
    base_dir: str
    files: list[str] = Field(default_factory=list, max_length=5000)


# ---------------- 注册 / 心跳 / 配置 ----------------

@router.post("/register")
def register(req: RegisterReq, agent: Agent = Depends(verify_agent),
             db: Session = Depends(get_db)):
    """Agent 启动注册：上报主机信息，标记上线。"""
    agent.hostname = req.hostname[:128]
    agent.ip = req.ip[:64]
    agent.os = req.os[:32]
    agent.arch = req.arch[:16]
    agent.version = req.version[:32]
    agent.status = "ONLINE"
    agent.last_heartbeat = datetime.now()
    object_session(agent).commit()
    logger.info("Agent 注册: %s(%s) %s %s", agent.name, agent.hostname, req.os, req.version)
    return ok({
        "agent_id": agent.id,
        "heartbeat_interval": HEARTBEAT_INTERVAL,
        "config_version": _config_version(db, agent.id),
    })


@router.post("/heartbeat")
def heartbeat(req: HeartbeatReq, agent: Agent = Depends(verify_agent),
              db: Session = Depends(get_db)):
    """心跳：保活 + 告知配置版本 + 下发扫描请求。"""
    agent.status = "ONLINE"
    agent.last_heartbeat = datetime.now()
    if req.version:
        agent.version = req.version[:32]
    object_session(agent).commit()
    version = _config_version(db, agent.id)
    scan_req = redis_client.getdel(SCAN_REQ_KEY.format(agent.id))
    return ok({
        "config_version": version,
        "scan_request": scan_req,   # 非空时 Agent 应执行扫描并 POST /scan/report
        "queue_size": req.queue_size,
    })


@router.get("/config")
def get_config(agent: Agent = Depends(verify_agent), db: Session = Depends(get_db)):
    """拉取采集配置：该 Agent 名下的全部启用日志源。"""
    sources = db.query(LogSource).filter(
        LogSource.agent_id == agent.id,
        LogSource.collect_mode == "AGENT",
        LogSource.enabled == 1).all()
    return ok({
        "config_version": _config_version(db, agent.id),
        "sources": [{
            "source_id": s.id,
            "name": s.name,
            "path_pattern": s.path_pattern,
            "exclude_pattern": s.exclude_pattern or "",
            "encoding": s.encoding,
            "multiline_pattern": s.multiline_pattern,
            "interval_seconds": s.interval_seconds,
        } for s in sources],
    })


# ---------------- 日志事件上报（复用中心告警引擎） ----------------

@router.post("/events")
def report_events(req: EventsReq, agent: Agent = Depends(verify_agent),
                  db: Session = Depends(get_db)):
    """批量上报合并后的日志条目，进入与 SSH 采集完全相同的处理链。"""
    source = db.query(LogSource).filter(
        LogSource.id == req.source_id,
        LogSource.agent_id == agent.id).first()
    if not source:
        return ok({"accepted": 0, "message": "日志源不存在或不属于该 Agent"})
    project = db.query(Project).filter(Project.id == source.project_id).first()
    host = db.query(Host).filter(Host.id == source.host_id).first()
    if not project or not host:
        return ok({"accepted": 0, "message": "日志源关联的项目/主机不完整"})

    accepted = 0
    for ev in req.events:
        try:
            engine.process_entry(
                db, source, project, host,
                file_path=ev.file, inode=req.inode or ev.file,
                start_offset=ev.offset, text=ev.content,
                occurred_at=ev.occurred_at)
            accepted += 1
        except Exception:
            logger.exception("Agent 事件处理失败: source=%d file=%s", req.source_id, ev.file)

    # 刷新采集状态（采集管理页可见 Agent 源的运行情况）
    st = db.query(CollectorState).filter(CollectorState.log_source_id == source.id).first()
    if st:
        st.status = "RUNNING"
        st.last_heartbeat = datetime.now()
        if req.events:
            st.current_file = req.events[-1].file
            st.read_offset = req.events[-1].offset
        db.commit()
    return ok({"accepted": accepted})


# ---------------- 目录扫描 ----------------

@router.post("/scan/report")
def scan_report(req: ScanReportReq, agent: Agent = Depends(verify_agent)):
    """Agent 上报目录扫描结果（管理端在前端查看）。"""
    redis_client.set(SCAN_KEY.format(agent.id), json.dumps({
        "base_dir": req.base_dir,
        "files": req.files,
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False), ex=86400)
    return ok({"received": len(req.files)})


# ---------------- 内部工具 ----------------

def _config_version(db: Session, agent_id: int) -> int:
    """配置版本 = 该 Agent 日志源最近更新时间戳（变更即触发 Agent 重新拉取）。"""
    latest = db.query(LogSource).filter(
        LogSource.agent_id == agent_id,
        LogSource.collect_mode == "AGENT") \
        .order_by(LogSource.updated_at.desc()).first()
    return int(latest.updated_at.timestamp()) if latest else 0
