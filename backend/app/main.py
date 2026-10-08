"""LogSentinel 后端入口（FastAPI）。

启动时自动完成：
1. 预置角色（ADMIN/OPS/VIEWER）
2. 无任何用户时创建初始管理员（密码取 ADMIN_INITIAL_PASSWORD，首次登录强制改密）
Swagger API 文档：/docs
"""
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .common.exceptions import register_exception_handlers
from .common.response import ok
from .common.security import aes_encrypt, hash_password
from .config import settings
from .database import SessionLocal
from .models import (ErrorCode, Keyword, NotifyChannel, Role, User, UserRole)
from .modules.agents.api import router as agent_api_router
from .modules.agents.router import router as agents_router
from .modules.audit.router import router as audit_router
from .modules.auth.router import router as auth_router
from .modules.channels.router import router as channels_router
from .modules.error_codes.router import router as error_codes_router
from .modules.error_logs.router import router as error_logs_router
from .modules.hosts.router import router as hosts_router
from .modules.keywords.router import router as keywords_router
from .modules.log_sources.router import router as log_sources_router
from .modules.mentions.router import router as mentions_router
from .modules.projects.router import router as projects_router
from .modules.rules.router import router as rules_router
from .modules.collector.manager import manager as collector_manager
from .modules.collector.router import router as collector_router
from .modules.dashboard.router import router as dashboard_router
from .modules.notify import pipeline
from .modules.notify.router import router as notify_router
from .modules.system.router import router as system_router
from .modules.templates.router import router as templates_router
from .modules.users.router import router as users_router
from .scheduler import scheduler, start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("logsentinel")

DEFAULT_ROLES = [
    ("ADMIN", "管理员", "全部权限"),
    ("OPS", "运维", "业务配置与运维操作"),
    ("VIEWER", "只读", "仅查看与查询"),
]


def init_data() -> None:
    """初始化角色与初始管理员。"""
    db = SessionLocal()
    try:
        for code, name, desc in DEFAULT_ROLES:
            if not db.query(Role).filter(Role.code == code).first():
                db.add(Role(code=code, name=name, description=desc))
        db.commit()

        if db.query(User).count() == 0:
            admin = User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_initial_password),
                real_name="系统管理员",
                status=1,
                must_change_pwd=1,
            )
            db.add(admin)
            db.flush()
            admin_role = db.query(Role).filter(Role.code == "ADMIN").first()
            db.add(UserRole(user_id=admin.id, role_id=admin_role.id))
            db.commit()
            logger.info("已创建初始管理员: %s（首次登录需修改密码）", settings.admin_username)

        # 预置默认通知渠道（无任何渠道且环境变量已配置时）
        if db.query(NotifyChannel).count() == 0:
            if settings.dingtalk_webhook:
                db.add(NotifyChannel(
                    name="默认钉钉群", type="dingtalk", enabled=1,
                    config_json=json.dumps({
                        "webhook": settings.dingtalk_webhook,
                        "secret": aes_encrypt(settings.dingtalk_secret) if settings.dingtalk_secret else "",
                        "at_all": False, "timeout": 5,
                    }, ensure_ascii=False)))
                logger.info("已预置默认钉钉渠道")
            if settings.email_host and settings.email_user:
                db.add(NotifyChannel(
                    name="默认邮件", type="email", enabled=1,
                    config_json=json.dumps({
                        "host": settings.email_host, "port": settings.email_port,
                        "user": settings.email_user,
                        "password": aes_encrypt(settings.email_password) if settings.email_password else "",
                        "to": [x.strip() for x in settings.email_to.split(",") if x.strip()],
                    }, ensure_ascii=False)))
                logger.info("已预置默认邮件渠道")
            db.commit()

        # 预置示例关键字与错误码（让新手开箱即有可勾选的数据）
        if db.query(Keyword).count() == 0:
            db.add(Keyword(name="空指针异常（示例）", pattern="NullPointerException",
                           match_op="CONTAINS", enabled=1))
            db.add(Keyword(name="内存溢出（示例）", pattern="OutOfMemoryError",
                           match_op="CONTAINS", enabled=1))
            logger.info("已预置示例关键字")
        if db.query(ErrorCode).count() == 0:
            db.add(ErrorCode(code="500", extract_regex=r"(?<!\d)500(?!\d)",
                             description="HTTP 服务器内部错误（示例）", enabled=1))
            logger.info("已预置示例错误码")
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("初始化数据失败")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_data()
    # 启动顺序：通知 worker → 调度器（含规则缓存）→ 采集器自启
    pipeline.start_workers()
    start_scheduler()
    collector_manager.start_all_enabled()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="LogSentinel API",
    description="Web-based Log Monitoring & DingTalk Alerting Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

for r in (auth_router, users_router, projects_router, hosts_router,
          log_sources_router, keywords_router, error_codes_router, rules_router,
          mentions_router, channels_router, templates_router, audit_router,
          error_logs_router, collector_router, notify_router, system_router,
          dashboard_router, agent_api_router, agents_router):
    app.include_router(r)


@app.get("/api/v1/health", tags=["系统"])
def health():
    """健康检查（无需鉴权，供 Docker healthcheck / 监控使用）。"""
    return ok({"status": "UP"})
