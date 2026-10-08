"""Agent 管理端 API（JWT + RBAC）：创建/列表/删除/安装命令/扫描。"""
import json
import secrets
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok
from ...database import get_db, redis_client
from ...models import Agent, LogSource
from ..auth.deps import client_ip, require_roles
from .api import OFFLINE_AFTER, SCAN_KEY, SCAN_REQ_KEY
from .auth import hash_token, new_token

router = APIRouter(prefix="/api/v1/agents", tags=["Agent管理"])


def _new_key() -> str:
    return "agt_" + secrets.token_hex(12)


def _to_dict(a: Agent) -> dict:
    # 超时的 ONLINE 视为离线（调度器也会兜底标记）
    status = a.status
    if status == "ONLINE" and a.last_heartbeat and \
            datetime.now() - a.last_heartbeat > timedelta(seconds=OFFLINE_AFTER):
        status = "OFFLINE"
    return {
        "id": a.id, "agent_key": a.agent_key, "name": a.name,
        "hostname": a.hostname, "ip": a.ip, "os": a.os, "arch": a.arch,
        "version": a.version, "status": status,
        "last_heartbeat": a.last_heartbeat,
        "source_count": None,  # 列表接口填充
        "created_at": a.created_at,
    }


class AgentCreateReq(BaseModel):
    name: str


@router.get("")
def list_agents(db: Session = Depends(get_db), _=Depends(require_roles("ADMIN", "OPS", "VIEWER"))):
    agents = db.query(Agent).order_by(Agent.id.desc()).all()
    # 统计每个 Agent 的日志源数量
    counter = Counter(row[0] for row in db.query(LogSource.agent_id)
                      .filter(LogSource.collect_mode == "AGENT", LogSource.agent_id.isnot(None)).all())
    items = []
    for a in agents:
        d = _to_dict(a)
        d["source_count"] = counter.get(a.id, 0)
        items.append(d)
    return ok(items)


@router.post("")
def create_agent(req: AgentCreateReq, request: Request,
                 db: Session = Depends(get_db),
                 user=Depends(require_roles("ADMIN", "OPS"))):
    """创建 Agent：返回一次性 Token（仅此一次展示，请立即复制）。"""
    token = new_token()
    agent = Agent(agent_key=_new_key(), name=req.name.strip(), token_hash=hash_token(token))
    db.add(agent)
    db.commit()
    db.refresh(agent)
    record_audit(db, user, "AGENT_CREATE", f"创建Agent: {agent.name}", client_ip(request))
    return ok({**_to_dict(agent), "token": token})


@router.delete("/{agent_id}")
def delete_agent(agent_id: int, request: Request,
                 db: Session = Depends(get_db),
                 user=Depends(require_roles("ADMIN"))):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise BizException(404, "Agent 不存在")
    used = db.query(LogSource).filter(LogSource.agent_id == agent_id).count()
    if used:
        raise BizException(400, f"该 Agent 仍被 {used} 个日志源引用，请先解除关联")
    db.delete(agent)
    db.commit()
    record_audit(db, user, "AGENT_DELETE", f"删除Agent: {agent.name}", client_ip(request))
    return ok(True)


@router.get("/{agent_id}/install")
def install_command(agent_id: int, request: Request,
                    os_name: str = "linux",
                    db: Session = Depends(get_db),
                    _=Depends(require_roles("ADMIN", "OPS"))):
    """生成一键安装命令（Token 需用户持有创建时保存的，不在此返回）。"""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise BizException(404, "Agent 不存在")
    base = str(request.base_url).rstrip("/")
    if os_name == "windows":
        cmd = (
            f"irm {base}/api/v1/agents/{agent.id}/binary?os=windows -OutFile logsentinel-agent.exe; "
            f".\\logsentinel-agent.exe -server {base} -key {agent.agent_key} -token <创建时保存的Token>"
        )
    else:
        cmd = (
            f"curl -sSL {base}/api/v1/agents/{agent.id}/binary?os=linux -o logsentinel-agent && "
            f"chmod +x logsentinel-agent && "
            f"./logsentinel-agent -server {base} -key {agent.agent_key} -token <创建时保存的Token>"
        )
    return ok({"command": cmd, "agent_key": agent.agent_key})


@router.get("/{agent_id}/binary")
def download_binary(agent_id: int, os: str = "linux",
                    db: Session = Depends(get_db),
                    _=Depends(require_roles("ADMIN", "OPS"))):
    """下载 Agent 二进制（install 命令中的下载源）。"""
    from pathlib import Path

    from fastapi.responses import FileResponse

    from ...config import settings
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise BizException(404, "Agent 不存在")
    name = "logsentinel-agent.exe" if os == "windows" else "logsentinel-agent"
    path = Path(settings.agent_binary_dir) / name
    if not path.exists():
        raise BizException(404, f"Agent 二进制未就绪: {path}（请先交叉编译放入该目录）")
    return FileResponse(path, filename=name)


@router.get("/{agent_id}/files")
def agent_files(agent_id: int, db: Session = Depends(get_db),
                _=Depends(require_roles("ADMIN", "OPS", "VIEWER"))):
    """查看 Agent 最近一次目录扫描结果。"""
    raw = redis_client.get(SCAN_KEY.format(agent_id))
    if not raw:
        return ok(None)
    return ok(json.loads(raw))


@router.post("/{agent_id}/scan")
def request_scan(agent_id: int, request: Request,
                 body: dict | None = None,
                 db: Session = Depends(get_db),
                 user=Depends(require_roles("ADMIN", "OPS"))):
    """发起扫描：下次心跳时下发给 Agent。"""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise BizException(404, "Agent 不存在")
    base_dir = (body or {}).get("base_dir", "/")
    redis_client.set(SCAN_REQ_KEY.format(agent_id), base_dir, ex=300)
    record_audit(db, user, "AGENT_SCAN", f"请求Agent扫描: {agent.name} {base_dir}", client_ip(request))
    return ok({"message": "扫描请求已下发，Agent 下次心跳后执行"})
