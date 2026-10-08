-- ============================================================
-- LogSentinel 数据库初始化脚本
-- MySQL 8.x / utf8mb4
-- 说明：角色在本脚本预置；初始管理员由后端首次启动时创建
--       （账号 admin，密码取环境变量 ADMIN_INITIAL_PASSWORD，
--        默认 Admin@123，首次登录强制修改密码）
-- ============================================================

CREATE DATABASE IF NOT EXISTS logsentinel DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE logsentinel;

-- ---------- 用户与权限 ----------
CREATE TABLE IF NOT EXISTS ls_user (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  username         VARCHAR(64)  NOT NULL UNIQUE COMMENT '登录名',
  password_hash    VARCHAR(128) NOT NULL COMMENT 'BCrypt 密码哈希',
  real_name        VARCHAR(64)  DEFAULT NULL COMMENT '姓名',
  status           TINYINT      NOT NULL DEFAULT 1 COMMENT '1启用 0禁用',
  must_change_pwd  TINYINT      NOT NULL DEFAULT 0 COMMENT '1首次登录强制改密',
  login_fail_count INT          NOT NULL DEFAULT 0 COMMENT '连续登录失败次数',
  locked_until     DATETIME     DEFAULT NULL COMMENT '锁定截止时间',
  last_login_at    DATETIME     DEFAULT NULL COMMENT '最后登录时间',
  created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT '用户';

CREATE TABLE IF NOT EXISTS ls_role (
  id          BIGINT PRIMARY KEY AUTO_INCREMENT,
  code        VARCHAR(32) NOT NULL UNIQUE COMMENT '角色编码 ADMIN/OPS/VIEWER',
  name        VARCHAR(64) NOT NULL COMMENT '角色名称',
  description VARCHAR(255) DEFAULT NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) COMMENT '角色';

CREATE TABLE IF NOT EXISTS ls_user_role (
  id      BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  role_id BIGINT NOT NULL,
  UNIQUE KEY uk_user_role (user_id, role_id)
) COMMENT '用户-角色关联';

-- ---------- 项目 / 主机 / 日志源 ----------
CREATE TABLE IF NOT EXISTS ls_project (
  id                 BIGINT PRIMARY KEY AUTO_INCREMENT,
  name               VARCHAR(128) NOT NULL COMMENT '项目名',
  code               VARCHAR(64)  NOT NULL UNIQUE COMMENT '项目编码',
  owner              VARCHAR(64)  DEFAULT NULL COMMENT '负责人',
  env                VARCHAR(32)  DEFAULT NULL COMMENT '环境',
  notify_channel_id  BIGINT       DEFAULT NULL COMMENT '默认通知渠道',
  default_mention_id BIGINT       DEFAULT NULL COMMENT '默认@人',
  status             TINYINT      NOT NULL DEFAULT 1,
  description        VARCHAR(500) DEFAULT NULL,
  created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT '项目';

CREATE TABLE IF NOT EXISTS ls_host (
  id             BIGINT PRIMARY KEY AUTO_INCREMENT,
  name           VARCHAR(128) NOT NULL COMMENT '主机名称',
  ip             VARCHAR(64)  NOT NULL COMMENT 'IP地址',
  ssh_port       INT          NOT NULL DEFAULT 22,
  auth_type      VARCHAR(16)  NOT NULL DEFAULT 'PASSWORD' COMMENT 'PASSWORD/KEY',
  username       VARCHAR(64)  DEFAULT NULL,
  password_enc   VARCHAR(1024) DEFAULT NULL COMMENT 'AES加密',
  private_key_enc TEXT         DEFAULT NULL COMMENT 'AES加密',
  host_type      VARCHAR(16)  NOT NULL DEFAULT 'LOCAL' COMMENT 'LOCAL/REMOTE',
  bastion_ip     VARCHAR(64)  DEFAULT NULL COMMENT '跳板机IP（可选）',
  bastion_port   INT          DEFAULT 22,
  bastion_username VARCHAR(64) DEFAULT NULL,
  bastion_auth_type VARCHAR(16) DEFAULT 'PASSWORD',
  bastion_password_enc VARCHAR(1024) DEFAULT NULL COMMENT 'AES加密',
  bastion_key_enc TEXT         DEFAULT NULL COMMENT 'AES加密',
  env            VARCHAR(32)  DEFAULT NULL,
  tags           VARCHAR(255) DEFAULT NULL COMMENT '逗号分隔',
  status         VARCHAR(16)  NOT NULL DEFAULT 'UNKNOWN' COMMENT 'ONLINE/OFFLINE/FAILED/UNKNOWN/LOCAL',
  last_check_at  DATETIME     DEFAULT NULL,
  remark         VARCHAR(500) DEFAULT NULL,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_host_env (env)
) COMMENT '服务器/主机';

CREATE TABLE IF NOT EXISTS ls_log_source (
  id                BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id        BIGINT NOT NULL,
  host_id           BIGINT NOT NULL,
  collect_mode      VARCHAR(8) NOT NULL DEFAULT 'SSH' COMMENT 'SSH/LOCAL/AGENT',
  agent_id          BIGINT DEFAULT NULL COMMENT 'Agent 模式时关联的 Agent',
  name              VARCHAR(128) NOT NULL,
  path_pattern      VARCHAR(512) NOT NULL COMMENT 'glob 路径，支持 * 与 **',
  exclude_pattern   VARCHAR(512) DEFAULT NULL COMMENT '排除 glob',
  encoding          VARCHAR(16)  NOT NULL DEFAULT 'UTF-8' COMMENT 'UTF-8/GBK',
  multiline_pattern VARCHAR(255) NOT NULL DEFAULT '^\\d{4}-\\d{2}-\\d{2}' COMMENT '新行起始正则',
  interval_seconds  INT          NOT NULL DEFAULT 5 COMMENT '采集间隔秒',
  env               VARCHAR(32)  DEFAULT NULL,
  tags              VARCHAR(255) DEFAULT NULL,
  enabled           TINYINT      NOT NULL DEFAULT 1,
  created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_source_project (project_id),
  KEY idx_source_host (host_id)
) COMMENT '日志源';

-- ---------- 采集状态 ----------
CREATE TABLE IF NOT EXISTS ls_collector_state (
  id                 BIGINT PRIMARY KEY AUTO_INCREMENT,
  host_id            BIGINT NOT NULL,
  log_source_id      BIGINT NOT NULL UNIQUE,
  status             VARCHAR(16) NOT NULL DEFAULT 'STOPPED' COMMENT 'RUNNING/STOPPED/ERROR/RECONNECTING',
  last_read_position BIGINT      NOT NULL DEFAULT 0 COMMENT '最后读取位置',
  read_offset        BIGINT      NOT NULL DEFAULT 0 COMMENT '字节偏移（处理落库后提交）',
  inode              VARCHAR(64) DEFAULT NULL,
  current_file       VARCHAR(512) DEFAULT NULL,
  rotated_file       VARCHAR(512) DEFAULT NULL,
  last_heartbeat     DATETIME     DEFAULT NULL,
  error_msg          VARCHAR(1024) DEFAULT NULL,
  retry_count        INT          NOT NULL DEFAULT 0,
  last_retry_at      DATETIME     DEFAULT NULL,
  created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT '采集状态';

-- ---------- 采集 Agent（内网主动上报模式） ----------
CREATE TABLE IF NOT EXISTS ls_agent (
  id             BIGINT PRIMARY KEY AUTO_INCREMENT,
  agent_key      VARCHAR(64)  NOT NULL UNIQUE COMMENT 'Agent 标识（创建时生成）',
  name           VARCHAR(128) NOT NULL COMMENT '备注名',
  hostname       VARCHAR(128) DEFAULT '',
  ip             VARCHAR(64)  DEFAULT '',
  os             VARCHAR(32)  DEFAULT '' COMMENT 'linux/windows',
  arch           VARCHAR(16)  DEFAULT '',
  version        VARCHAR(32)  DEFAULT '' COMMENT 'Agent 版本',
  token_hash     CHAR(64)     NOT NULL COMMENT 'Token 的 SHA-256',
  status         VARCHAR(16)  NOT NULL DEFAULT 'OFFLINE' COMMENT 'ONLINE/OFFLINE',
  last_heartbeat DATETIME     DEFAULT NULL,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_agent_status (status)
) COMMENT '采集 Agent';

-- ---------- 规则资源库 ----------
CREATE TABLE IF NOT EXISTS ls_keyword (
  id         BIGINT PRIMARY KEY AUTO_INCREMENT,
  name       VARCHAR(128) NOT NULL COMMENT '关键字名称',
  pattern    VARCHAR(512) NOT NULL COMMENT '匹配内容',
  match_op   VARCHAR(16)  NOT NULL DEFAULT 'CONTAINS' COMMENT 'CONTAINS/NOT_CONTAINS/EQUALS/REGEX',
  enabled    TINYINT      NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT '关键字库';

CREATE TABLE IF NOT EXISTS ls_error_code (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  code          VARCHAR(64)  NOT NULL COMMENT '错误码，如 500 / ERR_TIMEOUT',
  extract_regex VARCHAR(255) NOT NULL COMMENT '提取正则，如 (?<!\\d)500(?!\\d)',
  description   VARCHAR(255) DEFAULT NULL,
  enabled       TINYINT      NOT NULL DEFAULT 1,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_code_regex (code, extract_regex)
) COMMENT '错误码库';

-- ---------- 告警规则 ----------
CREATE TABLE IF NOT EXISTS ls_alert_rule (
  id                      BIGINT PRIMARY KEY AUTO_INCREMENT,
  name                    VARCHAR(128) NOT NULL,
  severity                VARCHAR(16)  NOT NULL DEFAULT 'MAJOR' COMMENT 'CRITICAL/MAJOR/MINOR',
  match_type              VARCHAR(16)  NOT NULL DEFAULT 'KEYWORD' COMMENT 'KEYWORD/REGEX/ERROR_CODE/LOG_LEVEL',
  match_content           VARCHAR(512) DEFAULT NULL COMMENT 'match_type 为 REGEX/LOG_LEVEL 时直接存内容',
  alert_enabled           TINYINT      NOT NULL DEFAULT 1 COMMENT '0=只记录不通知',
  silence_seconds         INT          NOT NULL DEFAULT 300 COMMENT '静默期秒',
  window_seconds          INT          DEFAULT NULL COMMENT 'N秒内M次-窗口秒',
  threshold_count         INT          DEFAULT NULL COMMENT 'N秒内M次-次数',
  consecutive_count       INT          DEFAULT NULL COMMENT '连续N次',
  recover_notify          TINYINT      NOT NULL DEFAULT 0,
  recover_window_seconds  INT          NOT NULL DEFAULT 300 COMMENT '恢复判定窗口秒',
  aggregate_notify        TINYINT      NOT NULL DEFAULT 0,
  aggregate_window_seconds INT         NOT NULL DEFAULT 60 COMMENT '聚合窗口秒',
  maintenance_start       VARCHAR(8)   DEFAULT NULL COMMENT 'HH:mm 支持跨天',
  maintenance_end         VARCHAR(8)   DEFAULT NULL,
  mention_id              BIGINT       DEFAULT NULL,
  template_id             BIGINT       DEFAULT NULL,
  enabled                 TINYINT      NOT NULL DEFAULT 1,
  created_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT '告警规则';

CREATE TABLE IF NOT EXISTS ls_alert_rule_source (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  rule_id       BIGINT NOT NULL,
  log_source_id BIGINT NOT NULL,
  UNIQUE KEY uk_rule_source (rule_id, log_source_id)
) COMMENT '规则-日志源关联';

CREATE TABLE IF NOT EXISTS ls_rule_keyword (
  id         BIGINT PRIMARY KEY AUTO_INCREMENT,
  rule_id    BIGINT NOT NULL,
  keyword_id BIGINT NOT NULL,
  UNIQUE KEY uk_rule_keyword (rule_id, keyword_id)
) COMMENT '规则-关键字关联';

CREATE TABLE IF NOT EXISTS ls_rule_error_code (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  rule_id       BIGINT NOT NULL,
  error_code_id BIGINT NOT NULL,
  UNIQUE KEY uk_rule_error_code (rule_id, error_code_id)
) COMMENT '规则-错误码关联';

-- ---------- 通知 ----------
CREATE TABLE IF NOT EXISTS ls_mention_rule (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  name             VARCHAR(64) NOT NULL COMMENT '姓名',
  mobile           VARCHAR(32) NOT NULL COMMENT '钉钉@用手机号',
  dingtalk_userid  VARCHAR(64) DEFAULT NULL,
  scope            VARCHAR(16) NOT NULL DEFAULT 'PROJECT' COMMENT 'PROJECT/HOST/RULE',
  ref_id           BIGINT      DEFAULT NULL COMMENT '关联对象ID',
  created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT '@人规则';

CREATE TABLE IF NOT EXISTS ls_notify_channel (
  id          BIGINT PRIMARY KEY AUTO_INCREMENT,
  name        VARCHAR(128) NOT NULL,
  type        VARCHAR(16)  NOT NULL DEFAULT 'dingtalk' COMMENT 'dingtalk/wecom/feishu/email/webhook',
  config_json TEXT         NOT NULL COMMENT '渠道配置（敏感字段AES加密后存储）',
  enabled     TINYINT      NOT NULL DEFAULT 1,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT '通知渠道';

CREATE TABLE IF NOT EXISTS ls_notify_template (
  id               BIGINT PRIMARY KEY AUTO_INCREMENT,
  name             VARCHAR(128) NOT NULL,
  channel_type     VARCHAR(16)  NOT NULL DEFAULT 'dingtalk',
  msg_type         VARCHAR(16)  NOT NULL DEFAULT 'markdown',
  content_template TEXT         NOT NULL COMMENT '模板，占位符 ${project} ${host} ${env} ${level} ${time} ${errorCode} ${keyword} ${file} ${content} ${mentions}',
  enabled          TINYINT      NOT NULL DEFAULT 1,
  created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT '通知模板';

-- ---------- 告警 / 通知记录 ----------
CREATE TABLE IF NOT EXISTS ls_alert_record (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  rule_id       BIGINT DEFAULT NULL,
  rule_name     VARCHAR(128) DEFAULT NULL,
  project_id    BIGINT DEFAULT NULL,
  host_id       BIGINT DEFAULT NULL,
  log_source_id BIGINT DEFAULT NULL,
  error_log_id  BIGINT DEFAULT NULL,
  severity      VARCHAR(16)  DEFAULT NULL,
  status        VARCHAR(16)  NOT NULL DEFAULT 'NOTIFIED' COMMENT 'NOTIFIED/SUPPRESSED/AGGREGATED/RECORD_ONLY',
  notified_at   DATETIME     DEFAULT NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_alert_created (created_at),
  KEY idx_alert_project (project_id, created_at)
) COMMENT '告警记录';

CREATE TABLE IF NOT EXISTS ls_notify_record (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  alert_id      BIGINT DEFAULT NULL,
  channel_id    BIGINT DEFAULT NULL,
  channel_type  VARCHAR(16)  DEFAULT NULL,
  request_body  TEXT         DEFAULT NULL,
  response_body TEXT         DEFAULT NULL,
  status        VARCHAR(16)  NOT NULL DEFAULT 'SUCCESS' COMMENT 'SUCCESS/FAILED',
  retry_count   INT          NOT NULL DEFAULT 0,
  error_msg     VARCHAR(1024) DEFAULT NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_notify_created (created_at)
) COMMENT '通知记录';

CREATE TABLE IF NOT EXISTS ls_notify_fail_record (
  id           BIGINT PRIMARY KEY AUTO_INCREMENT,
  channel_id   BIGINT DEFAULT NULL,
  alert_id     BIGINT DEFAULT NULL,
  request_body TEXT         DEFAULT NULL,
  error_msg    VARCHAR(1024) DEFAULT NULL,
  retry_count  INT          NOT NULL DEFAULT 0,
  status       VARCHAR(16)  NOT NULL DEFAULT 'FAILED' COMMENT 'FAILED/RESEND_SUCCESS/RESEND_FAILED',
  resent_at    DATETIME     DEFAULT NULL,
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) COMMENT '通知失败记录（死信）';

-- ---------- 报错日志 ----------
CREATE TABLE IF NOT EXISTS ls_error_log (
  id                BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id        BIGINT NOT NULL,
  host_id           BIGINT NOT NULL,
  log_source_id     BIGINT NOT NULL,
  file_path         VARCHAR(512) DEFAULT NULL,
  line_no           BIGINT       DEFAULT NULL,
  level             VARCHAR(16)  DEFAULT NULL,
  error_code        VARCHAR(64)  DEFAULT NULL,
  keyword           VARCHAR(255) DEFAULT NULL,
  raw_content       MEDIUMTEXT   DEFAULT NULL COMMENT '原始内容（不脱敏）',
  optimized_content MEDIUMTEXT   DEFAULT NULL COMMENT '优化后内容（已脱敏）',
  occurred_at       DATETIME     NOT NULL,
  created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  alert_status      VARCHAR(16)  NOT NULL DEFAULT 'RECORD_ONLY' COMMENT 'NOTIFIED/SUPPRESSED/RECORD_ONLY',
  fingerprint       VARCHAR(64)  NOT NULL COMMENT '幂等指纹 SHA-256',
  UNIQUE KEY uk_fingerprint (fingerprint),
  KEY idx_errlog_query (project_id, occurred_at),
  KEY idx_errlog_time (occurred_at),
  KEY idx_errlog_code (error_code)
) COMMENT '报错日志';

-- ---------- 系统设置（DB 覆盖环境变量，支持热更新） ----------
CREATE TABLE IF NOT EXISTS ls_system_setting (
  id         BIGINT PRIMARY KEY AUTO_INCREMENT,
  skey       VARCHAR(64)  NOT NULL UNIQUE COMMENT '设置键',
  svalue     VARCHAR(1024) NOT NULL COMMENT '设置值',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT '系统设置';

-- ---------- 审计 ----------
CREATE TABLE IF NOT EXISTS ls_audit_log (
  id         BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id    BIGINT       DEFAULT NULL,
  username   VARCHAR(64)  DEFAULT NULL,
  action     VARCHAR(64)  NOT NULL COMMENT '操作，如 LOGIN/CREATE/UPDATE/DELETE/EXPORT/COLLECTOR_CTRL',
  target     VARCHAR(255) DEFAULT NULL COMMENT '操作对象',
  ip         VARCHAR(64)  DEFAULT NULL,
  result     VARCHAR(16)  NOT NULL DEFAULT 'SUCCESS' COMMENT 'SUCCESS/FAIL',
  detail     VARCHAR(1024) DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_audit_created (created_at),
  KEY idx_audit_user (user_id, created_at)
) COMMENT '审计日志';

-- ---------- 种子数据 ----------
INSERT INTO ls_role (code, name, description) VALUES
  ('ADMIN',  '管理员', '全部权限'),
  ('OPS',    '运维',   '业务配置与运维操作'),
  ('VIEWER', '只读',   '仅查看与查询')
ON DUPLICATE KEY UPDATE name = VALUES(name);

INSERT INTO ls_notify_template (name, channel_type, msg_type, content_template, enabled) VALUES
  ('默认钉钉Markdown模板', 'dingtalk', 'markdown',
   '#### ⚠️ [${env}] ${project} · ${level}\n\n> **项目**：${project}\n> **主机**：${host}\n> **级别**：<font color="${sev_color}">${level}</font>\n> **时间**：${time}\n> **错误码**：${errorCode}${keyword_part}\n\n---\n\n**错误摘要**\n\n<font color="${sev_color}">${summary}</font>\n\n**错误日志**\n\n```\n${content}\n```\n\n**日志文件**：${file}\n\n${mentions}',
   1)
ON DUPLICATE KEY UPDATE name = name;
