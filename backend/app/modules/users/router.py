"""用户与角色管理（仅管理员）。"""
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok, page_result
from ...common.security import hash_password
from ...database import get_db
from ...models import Role, User, UserRole
from ..auth.deps import ROLE_ADMIN, CurrentUser, client_ip, require_roles

router = APIRouter(prefix="/api/v1", tags=["用户与权限"],
                   dependencies=[Depends(require_roles(ROLE_ADMIN))])


class UserIn(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    real_name: str | None = None
    status: int = 1
    role_ids: list[int] = []


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=128)
    real_name: str | None = None
    status: int | None = None
    role_ids: list[int] | None = None


def _roles_of(db: Session, user_id: int) -> list[dict]:
    return [
        {"id": r.id, "code": r.code, "name": r.name}
        for r in db.query(Role).join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user_id).all()
    ]


def _to_dict(db: Session, u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "real_name": u.real_name,
        "status": u.status, "last_login_at": u.last_login_at,
        "roles": _roles_of(db, u.id),
    }


@router.get("/roles")
def list_roles(db: Session = Depends(get_db)):
    return ok([{"id": r.id, "code": r.code, "name": r.name, "description": r.description}
               for r in db.query(Role).all()])


class RoleIn(BaseModel):
    code: str = Field(min_length=2, max_length=32, pattern="^[A-Z][A-Z0-9_]+$")
    name: str = Field(min_length=1, max_length=64)
    description: str | None = None


@router.post("/roles")
def create_role(body: RoleIn, request: Request, db: Session = Depends(get_db),
                me: CurrentUser = Depends(require_roles(ROLE_ADMIN))):
    if db.query(Role).filter(Role.code == body.code).first():
        raise BizException("角色编码已存在", code=400)
    r = Role(**body.model_dump())
    db.add(r)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="CREATE",
                 target=f"role:{r.code}", ip=client_ip(request))
    return ok({"id": r.id, "code": r.code, "name": r.name, "description": r.description},
              msg="创建成功")


@router.put("/roles/{role_id}")
def update_role(role_id: int, body: RoleIn, request: Request,
                db: Session = Depends(get_db),
                me: CurrentUser = Depends(require_roles(ROLE_ADMIN))):
    r = db.query(Role).filter(Role.id == role_id).first()
    if not r:
        raise BizException("角色不存在", code=404)
    if r.code in ("ADMIN", "OPS", "VIEWER") and body.code != r.code:
        raise BizException("内置角色编码不可修改", code=400)
    r.name, r.description = body.name, body.description
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="UPDATE",
                 target=f"role:{r.code}", ip=client_ip(request))
    return ok({"id": r.id, "code": r.code, "name": r.name, "description": r.description},
              msg="更新成功")


@router.delete("/roles/{role_id}")
def delete_role(role_id: int, request: Request, db: Session = Depends(get_db),
                me: CurrentUser = Depends(require_roles(ROLE_ADMIN))):
    r = db.query(Role).filter(Role.id == role_id).first()
    if not r:
        raise BizException("角色不存在", code=404)
    if r.code in ("ADMIN", "OPS", "VIEWER"):
        raise BizException("内置角色不可删除", code=400)
    if db.query(UserRole).filter(UserRole.role_id == role_id).count() > 0:
        raise BizException("该角色已分配给用户，无法删除", code=400)
    db.delete(r)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target=f"role:{r.code}", ip=client_ip(request))
    return ok(msg="删除成功")


@router.get("/users")
def list_users(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
               username: str | None = None, db: Session = Depends(get_db)):
    q = db.query(User)
    if username:
        q = q.filter(User.username.like(f"%{username}%"))
    total = q.count()
    items = q.order_by(User.id).offset((page - 1) * size).limit(size).all()
    return page_result([_to_dict(db, u) for u in items], total, page, size)


@router.post("/users")
def create_user(body: UserIn, request: Request, db: Session = Depends(get_db),
                me: CurrentUser = Depends(require_roles(ROLE_ADMIN))):
    if db.query(User).filter(User.username == body.username).first():
        raise BizException("用户名已存在", code=400)
    if not body.password:
        raise BizException("初始密码不能为空", code=400)
    user = User(username=body.username, password_hash=hash_password(body.password),
                real_name=body.real_name, status=body.status)
    db.add(user)
    db.flush()
    for rid in body.role_ids:
        db.add(UserRole(user_id=user.id, role_id=rid))
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="CREATE",
                 target=f"user:{user.username}", ip=client_ip(request))
    return ok(_to_dict(db, user), msg="创建成功")


@router.put("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request,
                db: Session = Depends(get_db),
                me: CurrentUser = Depends(require_roles(ROLE_ADMIN))):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise BizException("用户不存在", code=404)
    if body.password:
        user.password_hash = hash_password(body.password)
    if body.real_name is not None:
        user.real_name = body.real_name
    if body.status is not None:
        if user.id == me.id and body.status == 0:
            raise BizException("不能禁用自己的账号", code=400)
        user.status = body.status
    if body.role_ids is not None:
        if user.id == me.id:
            raise BizException("不能修改自己的角色", code=400)
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        for rid in body.role_ids:
            db.add(UserRole(user_id=user.id, role_id=rid))
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="UPDATE",
                 target=f"user:{user.username}", ip=client_ip(request))
    return ok(_to_dict(db, user), msg="更新成功")


@router.delete("/users/{user_id}")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db),
                me: CurrentUser = Depends(require_roles(ROLE_ADMIN))):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise BizException("用户不存在", code=404)
    if user.id == me.id:
        raise BizException("不能删除自己的账号", code=400)
    db.query(UserRole).filter(UserRole.user_id == user.id).delete()
    db.delete(user)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target=f"user:{user.username}", ip=client_ip(request))
    return ok(msg="删除成功")
