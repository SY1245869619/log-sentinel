-- LogSentinel Agent 上报模式（内网/JumpServer 场景）
-- 在已有库上执行：mysql -uroot -p logsentinel < migration_agent.sql

-- ---------- Agent 表 ----------
CREATE TABLE IF NOT EXISTS ls_agent (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  agent_key     VARCHAR(64)  NOT NULL UNIQUE COMMENT 'Agent 标识（创建时生成）',
  name          VARCHAR(128) NOT NULL COMMENT '备注名',
  hostname      VARCHAR(128) DEFAULT '',
  ip            VARCHAR(64)  DEFAULT '',
  os            VARCHAR(32)  DEFAULT '' COMMENT 'linux/windows',
  arch          VARCHAR(16)  DEFAULT '',
  version       VARCHAR(32)  DEFAULT '' COMMENT 'Agent 版本',
  token_hash    CHAR(64)     NOT NULL COMMENT 'Token 的 SHA-256',
  status        VARCHAR(16)  NOT NULL DEFAULT 'OFFLINE' COMMENT 'ONLINE/OFFLINE',
  last_heartbeat DATETIME    NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_status (status)
) COMMENT '采集 Agent';

-- ---------- 日志源支持 Agent 模式 ----------
ALTER TABLE ls_log_source
  ADD COLUMN collect_mode VARCHAR(8) NOT NULL DEFAULT 'SSH' COMMENT 'SSH/LOCAL/AGENT' AFTER host_id,
  ADD COLUMN agent_id BIGINT NULL COMMENT 'Agent 模式时关联的 Agent' AFTER collect_mode;
