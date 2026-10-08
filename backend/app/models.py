"""全部数据表模型（与 sql/init.sql 一一对应）。

统一放在单个文件中：便于查阅、避免跨模块循环导入。
"""
from datetime import datetime

from sqlalchemy import (BigInteger, Column, DateTime, Integer, String, Text,
                        UniqueConstraint)

from .database import Base


# ---------------- 用户与权限 ----------------

class User(Base):
    __tablename__ = "ls_user"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, unique=True)
    password_hash = Column(String(128), nullable=False)
    real_name = Column(String(64))
    status = Column(Integer, nullable=False, default=1)           # 1启用 0禁用
    must_change_pwd = Column(Integer, nullable=False, default=0)  # 1首次登录强制改密
    login_fail_count = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime)
    last_login_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class Role(Base):
    __tablename__ = "ls_role"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(32), nullable=False, unique=True)  # ADMIN/OPS/VIEWER
    name = Column(String(64), nullable=False)
    description = Column(String(255))
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class UserRole(Base):
    __tablename__ = "ls_user_role"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uk_user_role"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    role_id = Column(BigInteger, nullable=False)


# ---------------- 项目 / 主机 / 日志源 ----------------

class Project(Base):
    __tablename__ = "ls_project"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    code = Column(String(64), nullable=False, unique=True)
    owner = Column(String(64))
    env = Column(String(32))
    notify_channel_id = Column(BigInteger)
    default_mention_id = Column(BigInteger)
    status = Column(Integer, nullable=False, default=1)
    description = Column(String(500))
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class Host(Base):
    __tablename__ = "ls_host"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    ip = Column(String(64), nullable=False)
    ssh_port = Column(Integer, nullable=False, default=22)
    auth_type = Column(String(16), nullable=False, default="PASSWORD")  # PASSWORD/KEY
    username = Column(String(64))
    password_enc = Column(String(1024))          # AES 加密
    private_key_enc = Column(Text)               # AES 加密
    host_type = Column(String(16), nullable=False, default="LOCAL")  # LOCAL/REMOTE
    # 跳板机/堡垒机（可选：目标服务器无法直连时经跳板机中转）
    bastion_ip = Column(String(64))
    bastion_port = Column(Integer, default=22)
    bastion_username = Column(String(64))
    bastion_auth_type = Column(String(16), default="PASSWORD")
    bastion_password_enc = Column(String(1024))
    bastion_key_enc = Column(Text)
    env = Column(String(32))
    tags = Column(String(255))                   # 逗号分隔
    status = Column(String(16), nullable=False, default="UNKNOWN")  # ONLINE/OFFLINE/FAILED/UNKNOWN/LOCAL
    last_check_at = Column(DateTime)
    remark = Column(String(500))
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class LogSource(Base):
    __tablename__ = "ls_log_source"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, nullable=False)
    host_id = Column(BigInteger, nullable=False)
    collect_mode = Column(String(8), nullable=False, default="SSH")  # SSH/LOCAL/AGENT
    agent_id = Column(BigInteger)  # AGENT 模式时关联的 Agent
    name = Column(String(128), nullable=False)
    path_pattern = Column(String(512), nullable=False)       # glob，支持 * 与 **
    exclude_pattern = Column(String(512))
    encoding = Column(String(16), nullable=False, default="UTF-8")  # UTF-8/GBK
    multiline_pattern = Column(String(255), nullable=False, default=r"^\d{4}-\d{2}-\d{2}")
    interval_seconds = Column(Integer, nullable=False, default=5)
    env = Column(String(32))
    tags = Column(String(255))
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class CollectorState(Base):
    __tablename__ = "ls_collector_state"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    host_id = Column(BigInteger, nullable=False)
    log_source_id = Column(BigInteger, nullable=False, unique=True)
    status = Column(String(16), nullable=False, default="STOPPED")  # RUNNING/STOPPED/ERROR/RECONNECTING
    last_read_position = Column(BigInteger, nullable=False, default=0)
    read_offset = Column(BigInteger, nullable=False, default=0)
    inode = Column(String(64))
    current_file = Column(String(512))
    rotated_file = Column(String(512))
    last_heartbeat = Column(DateTime)
    error_msg = Column(String(1024))
    retry_count = Column(Integer, nullable=False, default=0)
    last_retry_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class Agent(Base):
    __tablename__ = "ls_agent"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_key = Column(String(64), nullable=False, unique=True)  # 创建时生成
    name = Column(String(128), nullable=False)
    hostname = Column(String(128), default="")
    ip = Column(String(64), default="")
    os = Column(String(32), default="")
    arch = Column(String(16), default="")
    version = Column(String(32), default="")
    token_hash = Column(String(64), nullable=False)  # Token 的 SHA-256
    status = Column(String(16), nullable=False, default="OFFLINE")  # ONLINE/OFFLINE
    last_heartbeat = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


# ---------------- 规则资源库 ----------------

class Keyword(Base):
    __tablename__ = "ls_keyword"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    pattern = Column(String(512), nullable=False)
    match_op = Column(String(16), nullable=False, default="CONTAINS")  # CONTAINS/NOT_CONTAINS/EQUALS/REGEX
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class ErrorCode(Base):
    __tablename__ = "ls_error_code"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(64), nullable=False)
    extract_regex = Column(String(255), nullable=False)
    description = Column(String(255))
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


# ---------------- 告警规则 ----------------

class AlertRule(Base):
    __tablename__ = "ls_alert_rule"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    severity = Column(String(16), nullable=False, default="MAJOR")  # CRITICAL/MAJOR/MINOR
    match_type = Column(String(16), nullable=False, default="KEYWORD")  # KEYWORD/REGEX/ERROR_CODE/LOG_LEVEL
    match_content = Column(String(512))
    alert_enabled = Column(Integer, nullable=False, default=1)  # 0=只记录不通知
    silence_seconds = Column(Integer, nullable=False, default=300)
    window_seconds = Column(Integer)          # N秒内M次-窗口
    threshold_count = Column(Integer)         # N秒内M次-次数
    consecutive_count = Column(Integer)       # 连续N次
    recover_notify = Column(Integer, nullable=False, default=0)
    recover_window_seconds = Column(Integer, nullable=False, default=300)
    aggregate_notify = Column(Integer, nullable=False, default=0)
    aggregate_window_seconds = Column(Integer, nullable=False, default=60)
    maintenance_start = Column(String(8))     # HH:mm，支持跨天
    maintenance_end = Column(String(8))
    mention_id = Column(BigInteger)
    template_id = Column(BigInteger)
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class AlertRuleSource(Base):
    __tablename__ = "ls_alert_rule_source"
    __table_args__ = (UniqueConstraint("rule_id", "log_source_id", name="uk_rule_source"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rule_id = Column(BigInteger, nullable=False)
    log_source_id = Column(BigInteger, nullable=False)


class RuleKeyword(Base):
    __tablename__ = "ls_rule_keyword"
    __table_args__ = (UniqueConstraint("rule_id", "keyword_id", name="uk_rule_keyword"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rule_id = Column(BigInteger, nullable=False)
    keyword_id = Column(BigInteger, nullable=False)


class RuleErrorCode(Base):
    __tablename__ = "ls_rule_error_code"
    __table_args__ = (UniqueConstraint("rule_id", "error_code_id", name="uk_rule_error_code"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rule_id = Column(BigInteger, nullable=False)
    error_code_id = Column(BigInteger, nullable=False)


# ---------------- 通知 ----------------

class MentionRule(Base):
    __tablename__ = "ls_mention_rule"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    mobile = Column(String(32), nullable=False)
    dingtalk_userid = Column(String(64))
    scope = Column(String(16), nullable=False, default="PROJECT")  # PROJECT/HOST/RULE
    ref_id = Column(BigInteger)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class NotifyChannel(Base):
    __tablename__ = "ls_notify_channel"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    type = Column(String(16), nullable=False, default="dingtalk")  # dingtalk/email/wecom/feishu/webhook
    config_json = Column(Text, nullable=False)  # JSON 字符串，敏感字段 AES 加密
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class NotifyTemplate(Base):
    __tablename__ = "ls_notify_template"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    channel_type = Column(String(16), nullable=False, default="dingtalk")
    msg_type = Column(String(16), nullable=False, default="markdown")
    content_template = Column(Text, nullable=False)
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


# ---------------- 告警 / 通知记录 ----------------

class AlertRecord(Base):
    __tablename__ = "ls_alert_record"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rule_id = Column(BigInteger)
    rule_name = Column(String(128))
    project_id = Column(BigInteger)
    host_id = Column(BigInteger)
    log_source_id = Column(BigInteger)
    error_log_id = Column(BigInteger)
    severity = Column(String(16))
    status = Column(String(16), nullable=False, default="NOTIFIED")  # NOTIFIED/SUPPRESSED/AGGREGATED/RECORD_ONLY
    notified_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class NotifyRecord(Base):
    __tablename__ = "ls_notify_record"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    alert_id = Column(BigInteger)
    channel_id = Column(BigInteger)
    channel_type = Column(String(16))
    request_body = Column(Text)
    response_body = Column(Text)
    status = Column(String(16), nullable=False, default="SUCCESS")  # SUCCESS/FAILED
    retry_count = Column(Integer, nullable=False, default=0)
    error_msg = Column(String(1024))
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class NotifyFailRecord(Base):
    __tablename__ = "ls_notify_fail_record"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger)
    alert_id = Column(BigInteger)
    request_body = Column(Text)
    error_msg = Column(String(1024))
    retry_count = Column(Integer, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="FAILED")  # FAILED/RESEND_SUCCESS/RESEND_FAILED
    resent_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


# ---------------- 系统设置 ----------------

class SystemSetting(Base):
    __tablename__ = "ls_system_setting"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    skey = Column(String(64), nullable=False, unique=True)
    svalue = Column(String(1024), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


# ---------------- 报错日志 ----------------

class ErrorLog(Base):
    __tablename__ = "ls_error_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, nullable=False)
    host_id = Column(BigInteger, nullable=False)
    log_source_id = Column(BigInteger, nullable=False)
    file_path = Column(String(512))
    line_no = Column(BigInteger)
    level = Column(String(16))
    error_code = Column(String(64))
    keyword = Column(String(255))
    raw_content = Column(Text)           # 原始内容（不脱敏）
    optimized_content = Column(Text)     # 优化后内容（已脱敏）
    occurred_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    alert_status = Column(String(16), nullable=False, default="RECORD_ONLY")  # NOTIFIED/SUPPRESSED/RECORD_ONLY
    fingerprint = Column(String(64), nullable=False, unique=True)
