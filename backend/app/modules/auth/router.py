"""认证接口：登录 / 登出 / 修改密码 / 当前用户信息。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok
from ...common.security import (create_access_token, create_refresh_token,
                                hash_password, verify_password)
from ...config import settings
from ...database import get_db
from ...models import Role, User, UserRole
from .deps import CurrentUser, client_ip, get_current_user
from .schemas import ChangePasswordRequest, LoginRequest

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


def _user_roles(db: Session, user_id: int) -> list[str]:
    return [
        r.code for r in db.query(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user_id).all()
    ]


@router.post("/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    user = db.query(User).filter(User.username == body.username).first()

    if not user:
        record_audit(db, user_id=None, username=body.username,
                     action="LOGIN", ip=ip, result="FAIL", detail="用户不存在")
        raise BizException("用户名或密码错误", code=400)

    # 锁定检查
    if user.locked_until and user.locked_until > datetime.now():
        minutes = int((user.locked_until - datetime.now()).total_seconds() // 60) + 1
        raise BizException(f"账号已锁定，请 {minutes} 分钟后重试", code=400)

    if user.status != 1:
        raise BizException("账号已禁用", code=400)

    if not verify_password(body.password, user.password_hash):
        user.login_fail_count = (user.login_fail_count or 0) + 1
        if user.login_fail_count >= settings.login_max_fail:
            user.locked_until = datetime.now() + timedelta(minutes=settings.login_lock_minutes)
            user.login_fail_count = 0
            detail = f"连续失败{settings.login_max_fail}次，锁定{settings.login_lock_minutes}分钟"
        else:
            detail = "密码错误"
        db.commit()
        record_audit(db, user_id=user.id, username=user.username,
                     action="LOGIN", ip=ip, result="FAIL", detail=detail)
        raise BizException("用户名或密码错误", code=400)

    # 登录成功
    user.login_fail_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now()
    db.commit()
    record_audit(db, user_id=user.id, username=user.username, action="LOGIN", ip=ip)

    roles = _user_roles(db, user.id)
    return ok({
        "access_token": create_access_token(user.id, user.username),
        "refresh_token": create_refresh_token(user.id, user.username),
        "expires_in": settings.jwt_access_ttl_minutes * 60,
        "must_change_pwd": bool(user.must_change_pwd),
        "user": {
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "roles": roles,
        },
    })


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db),
           user: CurrentUser = Depends(get_current_user)):
    # 无状态 JWT：客户端丢弃 token 即可，这里记录审计
    record_audit(db, user_id=user.id, username=user.username,
                 action="LOGOUT", ip=client_ip(request))
    return ok()


@router.put("/password")
def change_password(body: ChangePasswordRequest, request: Request,
                    db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    db_user = db.query(User).filter(User.id == user.id).first()
    if not verify_password(body.old_password, db_user.password_hash):
        record_audit(db, user_id=user.id, username=user.username,
                     action="CHANGE_PASSWORD", ip=client_ip(request), result="FAIL")
        raise BizException("原密码错误", code=400)
    if body.old_password == body.new_password:
        raise BizException("新密码不能与原密码相同", code=400)

    db_user.password_hash = hash_password(body.new_password)
    db_user.must_change_pwd = 0
    db.commit()
    record_audit(db, user_id=user.id, username=user.username,
                 action="CHANGE_PASSWORD", ip=client_ip(request))
    return ok(msg="密码修改成功")


@router.get("/profile")
def profile(user: CurrentUser = Depends(get_current_user)):
    return ok({
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "roles": user.roles,
    })
