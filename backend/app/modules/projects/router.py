"""项目管理。删除策略：存在关联日志源时阻断。"""
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.exceptions import BizException
from ...common.response import ok, page_result
from ...database import get_db
from ...models import LogSource, Project
from ..auth.deps import ROLE_ADMIN, ROLE_OPS, CurrentUser, client_ip, require_roles

router = APIRouter(prefix="/api/v1/projects", tags=["项目管理"])

WRITE = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    code: str | None = Field(default=None, max_length=64)  # 不填则自动取项目名
    owner: str | None = None
    env: str | None = None
    notify_channel_id: int | None = None
    default_mention_id: int | None = None
    status: int = 1
    description: str | None = None


def _to_dict(p: Project) -> dict:
    return {c: getattr(p, c) for c in
            ["id", "name", "code", "owner", "env", "notify_channel_id",
             "default_mention_id", "status", "description", "created_at", "updated_at"]}


@router.get("")
def list_projects(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=200),
                  name: str | None = None, env: str | None = None,
                  db: Session = Depends(get_db)):
    q = db.query(Project)
    if name:
        q = q.filter(Project.name.like(f"%{name}%"))
    if env:
        q = q.filter(Project.env == env)
    total = q.count()
    items = q.order_by(Project.id.desc()).offset((page - 1) * size).limit(size).all()
    return page_result([_to_dict(p) for p in items], total, page, size)


@router.get("/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise BizException("项目不存在", code=404)
    return ok(_to_dict(p))


@router.post("", dependencies=[WRITE])
def create_project(body: ProjectIn, request: Request, db: Session = Depends(get_db),
                   me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    code = body.code or body.name
    if db.query(Project).filter(Project.code == code).first():
        raise BizException("项目名已存在", code=400)
    data = body.model_dump()
    data["code"] = code
    p = Project(**data)
    db.add(p)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="CREATE",
                 target=f"project:{p.code}", ip=client_ip(request))
    return ok(_to_dict(p), msg="创建成功")


@router.put("/{project_id}", dependencies=[WRITE])
def update_project(project_id: int, body: ProjectIn, request: Request,
                   db: Session = Depends(get_db),
                   me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise BizException("项目不存在", code=404)
    code = body.code or body.name
    dup = db.query(Project).filter(Project.code == code, Project.id != project_id).first()
    if dup:
        raise BizException("项目名已被占用", code=400)
    data = body.model_dump()
    data["code"] = code
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="UPDATE",
                 target=f"project:{p.code}", ip=client_ip(request))
    return ok(_to_dict(p), msg="更新成功")


@router.delete("/{project_id}", dependencies=[WRITE])
def delete_project(project_id: int, request: Request, db: Session = Depends(get_db),
                   me: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_OPS))):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise BizException("项目不存在", code=404)
    if db.query(LogSource).filter(LogSource.project_id == project_id).count() > 0:
        raise BizException("该项目下存在日志源，请先删除关联日志源", code=400)
    db.delete(p)
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target=f"project:{p.code}", ip=client_ip(request))
    return ok(msg="删除成功")
