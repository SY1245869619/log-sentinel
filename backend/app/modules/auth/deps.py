"""认证与权限依赖注入。

token 来源：优先 Authorization: Bearer <token>，
其次 ?token= 查询参数（SSE EventSource 无法设置 Header）。
"""
from dataclasses import dataclass, field

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ...common.exceptions import BizException
from ...common.security import TOKEN_TYPE_ACCESS, parse_token
from ...database import get_db
from ...models import Role, User, UserRole

bearer = HTTPBearer(auto_error=False)

ROLE_ADMIN = "ADMIN"
ROLE_OPS = "OPS"
ROLE_VIEWER = "VIEWER"


@dataclass
class CurrentUser:
    id: int
    username: str
    real_name: str | None
    roles: list[str] = field(default_factory=list)

    def has_role(self, *roles: str) -> bool:
        return any(r in self.roles for r in roles)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    token_param: str | None = Query(default=None, alias="token"),
    db: Session = Depends(get_db),
) -> CurrentUser:
    token = credentials.credentials if credentials else token_param
    if not token:
        raise BizException("未登录或登录已过期", code=401)
    payload = parse_token(token)
    if not payload or payload.get("type") != TOKEN_TYPE_ACCESS:
        raise BizException("未登录或登录已过期", code=401)

    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user or user.status != 1:
        raise BizException("账号不存在或已禁用", code=401)

    roles = [
        r.code
        for r in db.query(Role).join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user.id).all()
    ]
    return CurrentUser(id=user.id, username=user.username,
                       real_name=user.real_name, roles=roles)


def require_roles(*roles: str):
    """接口级角色校验：require_roles("ADMIN", "OPS")。"""

    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_role(*roles):
            raise BizException("无权限执行该操作", code=403)
        return user

    return checker


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""
