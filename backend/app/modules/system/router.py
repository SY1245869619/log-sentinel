"""系统设置（DB 覆盖环境变量）+ SSE 实时推送端点。"""
import asyncio
import queue
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...common.audit import record_audit
from ...common.response import ok
from ...config import settings
from ...database import get_db
from ...models import SystemSetting
from ..auth.deps import ROLE_ADMIN, CurrentUser, client_ip, get_current_user, require_roles
from . import sse

router = APIRouter(prefix="/api/v1", tags=["系统"])

# 允许在界面修改的设置键（其余只读展示环境变量值）
# 值：(描述, 是否必须为正整数)
EDITABLE_KEYS = {
    "retention_error_log_days": ("报错日志保留天数", True),
    "retention_record_days": ("告警/通知记录保留天数", True),
    "retention_audit_days": ("审计日志保留天数", True),
    "dingtalk_rate_per_minute": ("钉钉每分钟限流条数", True),
    "login_wallpaper": ("登录页壁纸（内置 ocean/aurora/dusk 或自定义 CSS background 值）", False),
}

DEFAULT_WALLPAPER = "ocean"


def _effective(db: Session, key: str, env_value) -> dict:
    row = db.query(SystemSetting).filter(SystemSetting.skey == key).first()
    desc, _ = EDITABLE_KEYS.get(key, ("", True))
    return {"key": key, "value": row.svalue if row else str(env_value),
            "source": "db" if row else "env",
            "description": desc}


@router.get("/system/settings", dependencies=[Depends(require_roles(ROLE_ADMIN))])
def get_settings(db: Session = Depends(get_db)):
    return ok({
        "items": [
            _effective(db, "retention_error_log_days", settings.retention_error_log_days),
            _effective(db, "retention_record_days", settings.retention_record_days),
            _effective(db, "retention_audit_days", settings.retention_audit_days),
            _effective(db, "dingtalk_rate_per_minute", settings.dingtalk_rate_per_minute),
            _effective(db, "login_wallpaper", DEFAULT_WALLPAPER),
        ],
        "readonly": {
            "collector_heartbeat_seconds": settings.collector_heartbeat_seconds,
            "notify_retry_intervals": settings.notify_retry_intervals,
            "notify_max_content_bytes": settings.notify_max_content_bytes,
            "jwt_access_ttl_minutes": settings.jwt_access_ttl_minutes,
        },
        "note": "readonly 项由环境变量配置，修改需调整 .env 并重启",
    })


class SettingIn(BaseModel):
    key: str
    value: str


@router.put("/system/settings", dependencies=[Depends(require_roles(ROLE_ADMIN))])
def put_setting(body: SettingIn, request: Request, db: Session = Depends(get_db),
                me: CurrentUser = Depends(require_roles(ROLE_ADMIN))):
    if body.key not in EDITABLE_KEYS:
        from ...common.exceptions import BizException
        raise BizException(f"设置项 {body.key} 不允许修改", code=400)
    _, need_int = EDITABLE_KEYS[body.key]
    if need_int and (not body.value.isdigit() or int(body.value) < 1):
        from ...common.exceptions import BizException
        raise BizException("设置值必须为正整数", code=400)
    if not body.value.strip():
        from ...common.exceptions import BizException
        raise BizException("设置值不能为空", code=400)
    row = db.query(SystemSetting).filter(SystemSetting.skey == body.key).first()
    if row:
        row.svalue = body.value
    else:
        db.add(SystemSetting(skey=body.key, svalue=body.value))
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="UPDATE",
                 target=f"setting:{body.key}", ip=client_ip(request),
                 detail=body.value)
    return ok(msg="设置成功（即时生效）")


def get_setting_int(db: Session, key: str, default: int) -> int:
    """供调度任务读取有效设置值。"""
    row = db.query(SystemSetting).filter(SystemSetting.skey == key).first()
    try:
        return int(row.svalue) if row else default
    except ValueError:
        return default


@router.get("/system/login-config")
def login_config(db: Session = Depends(get_db)):
    """界面公开配置（壁纸等，无需鉴权，登录页与全局共用）。"""
    row = db.query(SystemSetting).filter(SystemSetting.skey == "login_wallpaper").first()
    return ok({"wallpaper": row.svalue if row else DEFAULT_WALLPAPER})


# ---------------- 壁纸图片管理（多图：上传/列表/删除/切换） ----------------

WALLPAPER_DIR = Path(__file__).resolve().parents[3] / "uploads" / "wallpapers"
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _list_wallpapers() -> list[dict]:
    if not WALLPAPER_DIR.exists():
        return []
    files = sorted(WALLPAPER_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    return [{
        "name": f.name,
        "url": f"/api/v1/system/wallpapers/{f.name}",
        "size": f.stat().st_size,
    } for f in files if f.suffix.lower() in ALLOWED_IMAGE_EXT]


@router.get("/system/wallpapers", dependencies=[Depends(require_roles(ROLE_ADMIN))])
def list_wallpapers():
    return ok(_list_wallpapers())


@router.post("/system/wallpaper/upload", dependencies=[Depends(require_roles(ROLE_ADMIN))])
async def upload_wallpaper(request: Request, file: UploadFile = File(...),
                           db: Session = Depends(get_db),
                           me: CurrentUser = Depends(require_roles(ROLE_ADMIN))):
    """上传壁纸图片（多图存储，上传后自动切换为当前壁纸）。"""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        from ...common.exceptions import BizException
        raise BizException("仅支持 jpg/png/webp/gif 图片", code=400)
    WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}{ext}"
    (WALLPAPER_DIR / name).write_bytes(await file.read())
    url = f"/api/v1/system/wallpapers/{name}"

    row = db.query(SystemSetting).filter(SystemSetting.skey == "login_wallpaper").first()
    if row:
        row.svalue = url
    else:
        db.add(SystemSetting(skey="login_wallpaper", svalue=url))
    db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="UPDATE",
                 target="setting:login_wallpaper", ip=client_ip(request),
                 detail=f"上传壁纸 {name}")
    return ok({"url": url}, msg="壁纸已上传并应用")


@router.delete("/system/wallpapers/{filename}", dependencies=[Depends(require_roles(ROLE_ADMIN))])
def delete_wallpaper(filename: str, request: Request, db: Session = Depends(get_db),
                     me: CurrentUser = Depends(require_roles(ROLE_ADMIN))):
    """删除已上传壁纸；若为当前使用中的壁纸则回退到默认。"""
    from ...common.exceptions import BizException
    target = WALLPAPER_DIR / filename
    if not target.exists() or target.suffix.lower() not in ALLOWED_IMAGE_EXT:
        raise BizException("壁纸不存在", code=404)
    target.unlink()
    row = db.query(SystemSetting).filter(SystemSetting.skey == "login_wallpaper").first()
    if row and row.svalue.endswith(filename):
        row.svalue = DEFAULT_WALLPAPER
        db.commit()
    record_audit(db, user_id=me.id, username=me.username, action="DELETE",
                 target=f"wallpaper:{filename}", ip=client_ip(request))
    return ok(msg="已删除")


@router.get("/system/wallpapers/{filename}")
def wallpaper_file(filename: str):
    """公开访问壁纸图片（登录页与全局背景共用）。"""
    from ...common.exceptions import BizException
    f = WALLPAPER_DIR / filename
    if not f.exists() or f.suffix.lower() not in ALLOWED_IMAGE_EXT:
        raise BizException("壁纸不存在", code=404)
    return FileResponse(f)


@router.get("/stream")
def stream(user: CurrentUser = Depends(get_current_user)):
    """SSE 实时推送（鉴权复用 JWT，?token= 传参）。"""
    q = sse.subscribe()

    async def events():
        try:
            yield sse.format_sse('{"type":"connected"}')
            while True:
                try:
                    data = await asyncio.to_thread(q.get, True, 15)
                    yield sse.format_sse(data)
                except queue.Empty:
                    yield ": heartbeat\n\n"
        finally:
            sse.unsubscribe(q)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
