"""通知渠道：CRUD + 测试发送。

config_json 为 JSON 字符串：
  dingtalk: {"webhook": "...", "secret": "...", "at_all": false, "timeout": 5}
  email:    {"host": "...", "port": 465, "user": "...", "password": "...", "to": ["a@b.com"]}
敏感字段（secret / password）AES 加密存储；读取时脱敏为 ******，更新传 ****** 表示不变。
"""
import json

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok, page_result
from ...common.security import aes_decrypt, aes_encrypt
from ...database import get_db
from ...models import NotifyChannel
from ...notify_engine import dingtalk, emailer
from ..auth.deps import ROLE_ADMIN, ROLE_OPS, CurrentUser, client_ip, require_roles

router = APIRouter(prefix="/api/v1/notify-channels", tags=["通知渠道"])

# 查看：全部角色；增删改与测试：仅管理员
WRITE = Depends(require_roles(ROLE_ADMIN))
MASKED = "******"
SENSITIVE_FIELDS = {"dingtalk": ["secret"], "email": ["password"]}
CHANNEL_TYPES = ("dingtalk", "email", "wecom", "feishu", "webhook")


class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    type: str = "dingtalk"
    config: dict = {}
    enabled: int = 1


def _encrypt_config(channel_type: str, config: dict, old_config: dict | None = None) -> dict:
    """敏感字段加密；****** 表示沿用旧值。"""
    result = dict(config)
    for field in SENSITIVE_FIELDS.get(channel_type, []):
        value = result.get(field)
        if value == MASKED and old_config:
            result[field] = old_config.get(field)
        elif value:
            result[field] = aes_encrypt(value)
    return result


def _to_dict(c: NotifyChannel) -> dict:
    try:
        config = json.loads(c.config_json)
    except (json.JSONDecodeError, TypeError):
        config = {}
    for field in SENSITIVE_FIELDS.get(c.type, []):
        if config.get(field):
            config[field] = MASKED
    return {"id": c.id, "name": c.name, "type": c.type, "config": config,
            "enabled": c.enabled, "created_at": c.created_at, "updated_at": c.updated_at}


def load_channel_config(c: NotifyChannel) -> dict:
    """加载并解密渠道配置（发送用）。"""
    config = json.loads(c.config_json)
    for field in SENSITIVE_FIELDS.get(c.type, []):
        if config.get(field):
            config[field] = aes_decrypt(config[field])
    return config


@router.get("")
def list_channels(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
                  channel_type: str | None = Query(default=None, alias="type"),
                  db: Session = Depends(get_db)):
    q = db.query(NotifyChannel)
    if channel_type:
        q = q.filter(NotifyChannel.type == channel_type)
    total = q.count()
    items = q.order_by(NotifyChannel.id.desc()).offset((page - 1) * size).limit(size).all()
    return page_result([_to_dict(c) for c in items], total, page, size)


@router.get("/{channel_id}")
def get_channel(channel_id: int, db: Session = Depends(get_db)):
    c = db.query(NotifyChannel).filter(NotifyChannel.id == channel_id).first()
    if not c:
        raise BizException("渠道不存在", code=404)
    return ok(_to_dict(c))


@router.post("", dependencies=[WRITE])
def create_channel(body: ChannelIn, request: Request, db: Session = Depends(get_db),
                   me: CurrentUser = Depends(require_roles(ROLE_ADMIN))):
    if body.type not in CHANNEL_TYPES:
        raise BizException(f"渠道类型必须是 {'/'.join(CHANNEL_TYPES)}", code=400)
    config = _encrypt_config(body.type, body.config)
    c = NotifyChannel(name=body.name, type=body.type,
                      config_json=json.dumps(config, ensure_ascii=False),
                      enabled=body.enabled)
    db.add(c)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="CREATE",
                 target=f"channel:{c.name}({c.type})", ip=client_ip(request))
    return ok(_to_dict(c), msg="创建成功")


@router.put("/{channel_id}", dependencies=[WRITE])
def update_channel(channel_id: int, body: ChannelIn, request: Request,
                   db: Session = Depends(get_db),
                   me: CurrentUser = Depends(require_roles(ROLE_ADMIN))):
    c = db.query(NotifyChannel).filter(NotifyChannel.id == channel_id).first()
    if not c:
        raise BizException("渠道不存在", code=404)
    old_config = json.loads(c.config_json)
    c.name, c.type, c.enabled = body.name, body.type, body.enabled
    c.config_json = json.dumps(_encrypt_config(body.type, body.config, old_config),
                               ensure_ascii=False)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="UPDATE",
                 target=f"channel:{c.name}({c.type})", ip=client_ip(request))
    return ok(_to_dict(c), msg="更新成功")


@router.delete("/{channel_id}", dependencies=[WRITE])
def delete_channel(channel_id: int, request: Request, db: Session = Depends(get_db),
                   me: CurrentUser = Depends(require_roles(ROLE_ADMIN))):
    c = db.query(NotifyChannel).filter(NotifyChannel.id == channel_id).first()
    if not c:
        raise BizException("渠道不存在", code=404)
    db.delete(c)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target=f"channel:{c.name}({c.type})", ip=client_ip(request))
    return ok(msg="删除成功")


@router.post("/{channel_id}/test", dependencies=[WRITE])
def test_channel(channel_id: int, request: Request, db: Session = Depends(get_db),
                 me: CurrentUser = Depends(require_roles(ROLE_ADMIN))):
    """发送测试消息（OPS+ 可用，记审计）。"""
    c = db.query(NotifyChannel).filter(NotifyChannel.id == channel_id).first()
    if not c:
        raise BizException("渠道不存在", code=404)
    success, message = send_by_channel(c, "LogSentinel 测试消息",
                                       "这是一条来自 LogSentinel 的测试消息，收到即表示渠道配置正确。")
    record_audit(db, user_id=me.id, username=me.username, action="TEST_CHANNEL",
                 target=f"channel:{c.name}({c.type})", ip=client_ip(request),
                 result="SUCCESS" if success else "FAIL", detail=message)
    if not success:
        raise BizException(f"测试发送失败：{message}", code=400)
    return ok({"success": True, "message": message})


def send_by_channel(c: NotifyChannel, title: str, content: str,
                    at_mobiles: list[str] | None = None) -> tuple[bool, str]:
    """按渠道类型发送消息（测试与告警流水线共用）。"""
    config = load_channel_config(c)
    if c.type == "dingtalk":
        return dingtalk.send_markdown(
            webhook=config.get("webhook", ""), secret=config.get("secret", ""),
            title=title, text=content, at_mobiles=at_mobiles,
            is_at_all=bool(config.get("at_all")),
            timeout=float(config.get("timeout", 5)))
    if c.type == "email":
        return emailer.send_email(
            host=config.get("host", ""), port=int(config.get("port", 465)),
            user=config.get("user", ""), password=config.get("password", ""),
            to_list=config.get("to", []), subject=title, content=content)
    return False, f"渠道类型暂未实现: {c.type}"
