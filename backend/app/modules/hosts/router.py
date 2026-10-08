"""主机管理：CRUD + SSH 连接测试（Paramiko）。

敏感字段（密码/私钥）AES 加密存储，接口返回值脱敏；
更新时传 "******" 表示保持不变。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok, page_result
from ...common.security import aes_decrypt, aes_encrypt, mask
from ...database import get_db
from ...models import Host, LogSource
from ..auth.deps import ROLE_ADMIN, ROLE_OPS, CurrentUser, client_ip, require_roles
from .ssh import test_ssh_connection

router = APIRouter(prefix="/api/v1/hosts", tags=["主机管理"])

WRITE = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))
MASKED = "******"


class HostIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    ip: str = Field(min_length=1, max_length=64)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    auth_type: str = Field(default="PASSWORD", pattern="^(PASSWORD|KEY)$")
    username: str | None = None
    password: str | None = None       # 明文入参，加密落库；****** 表示不变
    private_key: str | None = None
    # 主机一律为远程（SSH 采集），不再区分本机
    host_type: str = "REMOTE"
    # 跳板机/堡垒机（可选）
    bastion_ip: str | None = None
    bastion_port: int | None = Field(default=22, ge=1, le=65535)
    bastion_username: str | None = None
    bastion_auth_type: str | None = Field(default="PASSWORD", pattern="^(PASSWORD|KEY)$")
    bastion_password: str | None = None
    bastion_key: str | None = None
    env: str | None = None
    tags: str | None = None
    remark: str | None = None


def _to_dict(h: Host) -> dict:
    return {
        "id": h.id, "name": h.name, "ip": h.ip, "ssh_port": h.ssh_port,
        "auth_type": h.auth_type, "username": h.username,
        "password": mask(h.password_enc), "private_key": mask(h.private_key_enc),
        "host_type": h.host_type,
        "bastion_ip": h.bastion_ip, "bastion_port": h.bastion_port,
        "bastion_username": h.bastion_username,
        "bastion_auth_type": h.bastion_auth_type,
        "bastion_password": mask(h.bastion_password_enc),
        "bastion_key": mask(h.bastion_key_enc),
        "env": h.env, "tags": h.tags,
        "status": h.status, "last_check_at": h.last_check_at, "remark": h.remark,
        "created_at": h.created_at, "updated_at": h.updated_at,
    }


def _apply(h: Host, body: HostIn) -> None:
    h.name, h.ip, h.ssh_port = body.name, body.ip, body.ssh_port
    h.auth_type, h.username = body.auth_type, body.username
    h.host_type, h.env, h.tags, h.remark = body.host_type, body.env, body.tags, body.remark
    if body.password and body.password != MASKED:
        h.password_enc = aes_encrypt(body.password)
    if body.private_key and body.private_key != MASKED:
        h.private_key_enc = aes_encrypt(body.private_key)
    # 跳板机
    h.bastion_ip = body.bastion_ip or None
    h.bastion_port = body.bastion_port or 22
    h.bastion_username = body.bastion_username
    h.bastion_auth_type = body.bastion_auth_type or "PASSWORD"
    if body.bastion_password and body.bastion_password != MASKED:
        h.bastion_password_enc = aes_encrypt(body.bastion_password)
    if body.bastion_key and body.bastion_key != MASKED:
        h.bastion_key_enc = aes_encrypt(body.bastion_key)


def _bastion_of(h: Host) -> dict | None:
    if not h.bastion_ip:
        return None
    return {
        "ip": h.bastion_ip, "port": h.bastion_port or 22,
        "username": h.bastion_username or "",
        "auth_type": h.bastion_auth_type or "PASSWORD",
        "password": aes_decrypt(h.bastion_password_enc),
        "private_key": aes_decrypt(h.bastion_key_enc),
    }


@router.get("")
def list_hosts(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
               name: str | None = None, env: str | None = None, tag: str | None = None,
               db: Session = Depends(get_db)):
    q = db.query(Host)
    if name:
        q = q.filter(Host.name.like(f"%{name}%"))
    if env:
        q = q.filter(Host.env == env)
    if tag:
        q = q.filter(Host.tags.like(f"%{tag}%"))
    total = q.count()
    items = q.order_by(Host.id.desc()).offset((page - 1) * size).limit(size).all()
    return page_result([_to_dict(h) for h in items], total, page, size)


@router.get("/{host_id}")
def get_host(host_id: int, db: Session = Depends(get_db)):
    h = db.query(Host).filter(Host.id == host_id).first()
    if not h:
        raise BizException("主机不存在", code=404)
    return ok(_to_dict(h))


@router.post("", dependencies=[WRITE])
def create_host(body: HostIn, request: Request, db: Session = Depends(get_db),
                me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    h = Host(status="UNKNOWN")
    _apply(h, body)
    h.host_type = "REMOTE"
    db.add(h)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="CREATE",
                 target=f"host:{h.name}({h.ip})", ip=client_ip(request))
    return ok(_to_dict(h), msg="创建成功")


@router.put("/{host_id}", dependencies=[WRITE])
def update_host(host_id: int, body: HostIn, request: Request, db: Session = Depends(get_db),
                me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    h = db.query(Host).filter(Host.id == host_id).first()
    if not h:
        raise BizException("主机不存在", code=404)
    _apply(h, body)
    h.host_type = "REMOTE"
    h.status = "UNKNOWN"
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="UPDATE",
                 target=f"host:{h.name}({h.ip})", ip=client_ip(request))
    return ok(_to_dict(h), msg="更新成功")


@router.delete("/{host_id}", dependencies=[WRITE])
def delete_host(host_id: int, request: Request, db: Session = Depends(get_db),
                me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    h = db.query(Host).filter(Host.id == host_id).first()
    if not h:
        raise BizException("主机不存在", code=404)
    if db.query(LogSource).filter(LogSource.host_id == host_id).count() > 0:
        raise BizException("该主机下存在日志源，请先删除关联日志源", code=400)
    db.delete(h)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target=f"host:{h.name}({h.ip})", ip=client_ip(request))
    return ok(msg="删除成功")


@router.post("/{host_id}/test-ssh", dependencies=[WRITE])
def test_ssh(host_id: int, request: Request, db: Session = Depends(get_db),
             me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    h = db.query(Host).filter(Host.id == host_id).first()
    if not h:
        raise BizException("主机不存在", code=404)
    if h.host_type != "REMOTE":
        h.host_type = "REMOTE"
    success, message = test_ssh_connection(
        ip=h.ip, port=h.ssh_port, username=h.username or "",
        auth_type=h.auth_type,
        password=aes_decrypt(h.password_enc),
        private_key=aes_decrypt(h.private_key_enc),
        bastion=_bastion_of(h),
    )
    h.status = "ONLINE" if success else "FAILED"
    h.last_check_at = datetime.now()
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="TEST_SSH",
                 target=f"host:{h.name}({h.ip})", ip=client_ip(request),
                 result="SUCCESS" if success else "FAIL", detail=message)
    if not success:
        raise BizException(f"SSH 连接失败：{message}", code=400)
    return ok({"success": True, "message": message})
