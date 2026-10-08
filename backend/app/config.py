"""全局配置：从环境变量读取（与 docker-compose.yml / .env 对应）。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_database: str = "logsentinel"
    mysql_user: str = "root"
    mysql_password: str = "root"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    # JWT
    jwt_secret: str = "dev-only-secret-please-change-32bytes"
    jwt_access_ttl_minutes: int = 120
    jwt_refresh_ttl_days: int = 7

    # 安全
    aes_key: str = "dev-only-aes-key"  # 必须正好 16 字节
    login_max_fail: int = 5
    login_lock_minutes: int = 15

    # 初始管理员（仅首次启动无用户时创建）
    admin_username: str = "admin"
    admin_initial_password: str = "Admin@123"

    # 采集器
    collector_heartbeat_seconds: int = 10
    collector_queue_capacity: int = 10000
    multiline_max_lines: int = 200

    # 通知
    notify_core_pool_size: int = 4
    notify_queue_capacity: int = 10000
    dingtalk_rate_per_minute: int = 20
    notify_retry_intervals: str = "10,60,300"
    notify_max_content_bytes: int = 4000

    # Agent 二进制目录（install 命令下载源）
    agent_binary_dir: str = "../agent/dist"

    # 保留策略（天）
    retention_error_log_days: int = 30
    retention_record_days: int = 90
    retention_audit_days: int = 180

    # 系统 Web 访问地址（用于钉钉消息中的"查看完整日志"链接，留空则不附链接）
    web_base_url: str = ""

    # 默认钉钉渠道（首次启动无渠道时自动入库）
    dingtalk_webhook: str = ""
    dingtalk_secret: str = ""

    # 默认邮件渠道（首次启动无渠道时自动入库）
    email_host: str = ""
    email_port: int = 465
    email_user: str = ""
    email_password: str = ""
    email_to: str = ""  # 多个收件人用英文逗号分隔

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def retry_intervals(self) -> list[int]:
        return [int(x) for x in self.notify_retry_intervals.split(",") if x.strip()]


settings = Settings()
