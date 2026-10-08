"""Agent Token 鉴权：每个 Agent 创建时生成一次性 Token，存 SHA-256。

Agent 每次请求携带：
  X-Agent-Key: <agent_key>
  Authorization: Bearer <token>
"""
import hashlib
import secrets

from fastapi import Header

from ...common.exceptions import BizException
from ...database import SessionLocal
from ...models import Agent


def new_token() -> str:
    """生成 32 字节随机 Token（hex，仅创建时展示一次）。"""
    return secrets.token_hex(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_agent(x_agent_key: str = Header(default=""),
                 authorization: str = Header(default="")):
    """FastAPI 依赖（生成器）：校验 Agent 身份，会话存活至请求结束，
    端点内对返回的 agent 对象修改后可直接 object_session(agent).commit()。"""
    if not x_agent_key or not authorization.startswith("Bearer "):
        raise BizException(401, "缺少 Agent 身份头（X-Agent-Key / Bearer Token）")
    token = authorization.removeprefix("Bearer ").strip()
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.agent_key == x_agent_key).first()
        if not agent or agent.token_hash != hash_token(token):
            raise BizException(401, "Agent 身份校验失败")
        yield agent
    finally:
        db.close()
