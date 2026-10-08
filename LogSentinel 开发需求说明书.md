# LogSentinel 开发需求说明书（V2 修订版）

> 修订说明：本版在原稿基础上修正了 MVP 范围矛盾、补齐告警引擎语义定义、重构数据模型、补充权限矩阵与非功能指标。凡与旧版冲突之处，以本版为准。

## 0. 给智能体的开发指令

请根据本文档开发一个完整可运行的 Web 日志监控告警系统。

- 项目名：LogSentinel
- 中文名：日志监控告警系统
- 仓库名：log-sentinel
- 定位：可部署在服务器上的 Web 日志监控与钉钉告警平台，支持多项目、多日志源、关键字/错误码规则、钉钉通知与 @人、报错日志存储查询。

要求：

1. 优先实现 MVP，代码可运行、可维护。
2. 包含数据库初始化 SQL、Docker Compose、README、API 文档、示例配置。
3. 不要只给伪代码。
4. **MVP 范围**：登录权限（RBAC）、项目/主机/日志源配置、主机 SSH 连接测试、**远程 SSH 采集 + 本机采集**（采集器内嵌后端进程，系统集中部署后连接多台服务器）、关键字/错误码/告警规则（含立即告警、N 秒内 M 次、连续 N 次、基础版恢复通知、基础版聚合通知、维护窗口）、钉钉通知与 @人、**邮件通知**、报错日志保存/查询/删除/**导出**、基础仪表盘、采集管理（查看 + 启停）、Docker Compose 部署。
5. **后续扩展（架构预留，不实现）**：远程 SSH 采集、企微/飞书/邮件/Webhook 渠道、Agent 采集、集群部署、值班表、增强版聚合/恢复通知、全文检索。

## 1. 项目概述

### 1.1 项目命名

- 产品名：LogSentinel
- 中文名：日志监控告警系统
- 仓库名：log-sentinel
- 描述：Web-based Log Monitoring & DingTalk Alerting Platform
- Docker 镜像：log-sentinel:latest
- 后端结构：Python（FastAPI），代码位于 backend/app/modules/*
- 数据库表前缀：ls_
- API 前缀：/api/v1

### 1.2 系统定位

LogSentinel 是一个可部署在服务器上的 Web 日志监控与告警平台。MVP 阶段支持本机采集，集中管理多项目、多主机、多日志源，按关键字、错误码、正则、日志级别规则发现异常，发送钉钉告警，保存报错日志，支持 Web 查询与管理。架构上为远程采集与多渠道通知预留抽象。

### 1.3 核心目标

- 定时/准实时采集日志（默认采集间隔 5 秒，可配置）。
- 按项目、日志源、规则匹配关键字/错误码/正则/日志级别。
- 生成告警并发送钉钉消息，消息含报错内容、项目、主机、日志文件、@人，并做中文可读优化。
- 保存报错日志，支持 Web 查询、删除、导出。
- 所有配置通过浏览器 Web 页面管理。

### 1.4 采集模式

| 模式 | 说明 | 阶段 |
|------|------|------|
| 远程采集 | **系统集中部署在一台服务器（10.99.99.152），通过 SSH/SFTP 连接多台目标服务器读取日志**，主机在"服务器配置"中维护，支持密码/私钥认证、断线重连 | MVP（主模式） |
| 本机采集 | 部署服务器自身的日志直接读取本地文件 | MVP |
| Agent 采集 | 独立 Agent 自动注册上报 | 后续 |

采集器以后端进程内嵌线程池运行：每个日志源一个采集线程，远程模式经 Paramiko SFTP 按字节 offset 读取，心跳与断点状态统一存中心 MySQL。

## 2. 技术栈与项目结构

### 2.1 技术栈

- 后端：Python 3.12 + FastAPI + SQLAlchemy 2 + Pydantic v2 + APScheduler（自带 Swagger API 文档）
- 前端：React 18 + Vite + TypeScript + Ant Design 6 + ECharts（主题严格使用 sereneTheme.ts，不得修改主题配色）
- 数据库：MySQL 8
- 缓存/内存计算：Redis。**MVP 中职责明确为三项**：滑动窗口计数（N 秒内 M 次）、通知限流计数、告警幂等指纹去重
- 实时推送：**SSE**（Server-Sent Events，MVP 不使用 WebSocket；Nginx 需配置 `proxy_buffering off`）
- SSH：**Paramiko**（Python SSH 库，用于主机连接测试 / 后续远程采集）
- 钉钉：钉钉机器人 Webhook + 加签
- 部署：Docker Compose + Nginx（主），systemd（裸机备选，与 Docker 方式**互斥**）

### 2.2 项目结构

```text
log-sentinel/
  backend/       后端 API、告警引擎、内嵌采集器
  frontend/      Web 前端
  deploy/        Docker Compose、Nginx 配置、systemd 示例（备选）
  sql/           初始化 SQL（含初始管理员账号）
  docs/          API 文档、部署文档、示例配置
```

> 说明：MVP 采集器内嵌于 backend，不独立成模块；包结构上以 `collector` 包隔离，为后续独立部署/Agent 化预留。

## 3. 功能需求

### 3.1 主机/节点管理

字段必须包含：

- 主机名称、IP 地址、SSH 端口
- 认证方式：密码 / 私钥
- 用户名、密码或私钥（**加密存储**，AES-256，密钥来自环境变量）
- 环境：dev / test / prod / 自定义
- 标签：支持多个，如 订单、支付、核心
- 状态：在线 / 离线 / 连接失败 / 未知（**本机模式**主机状态固定为"本机"，不做 SSH 探活）
- 最后检测时间、备注

功能要求：

- 新增、编辑、删除、查询主机。
- **支持测试 SSH 连接**（MVP 实现，供后续远程采集使用；接口需鉴权 + 审计，防止被用作内网探测）。
- 支持按环境、标签筛选。
- 敏感字段加密存储、界面脱敏显示。
- 主机类型：`LOCAL`（本机）/ `REMOTE`（远程）。MVP 仅 LOCAL 类型可被日志源绑定采集。

### 3.2 项目管理

字段必须包含：项目名、项目编码（唯一）、负责人、环境、通知渠道（引用 `ls_notify_channel`）、默认 @人（引用 `ls_mention_rule`，可为空）、状态、描述。

功能要求：

- 一个项目可绑定多个日志源。
- @人三级配置，**优先级：规则级 > 主机级 > 项目级**，上级未配置时向下取。
- 删除项目时若存在关联日志源/规则，**阻断删除并提示**（不做级联删除）。

### 3.3 日志源配置

支持配置多个日志位置，例如：`/opt/fscr/app/logs/项目名/*.log`

必须支持：

- 多项目、多文件、通配符（支持 `*` 与 `**` 递归，采用标准 glob 语法）
- 排除规则（排除通配符，如 `*-debug.log`）
- 文件编码 UTF-8 / GBK（**按源配置，不做自动检测**；offset 按字节记录、按行对齐恢复，避免多字节编码错位）
- 多行堆栈合并（规则见 §4.3）
- 日志轮转处理（rename+create 与 copytruncate 两种模式均支持，见 §4.4）
- 断点续读（见 §4.5）
- 采集间隔可配置（默认 5 秒，最低 1 秒）
- 每个日志源关联项目、主机、环境、标签；**环境/标签继承链：日志源 > 项目 > 主机**，下级未配置时取上级值
- 删除日志源时阻断提示：关联规则与采集状态需先解除

### 3.4 采集管理

采集状态字段必须包含：采集器状态（运行中 / 停止 / 异常 / 重连中）、最后读取位置、offset、inode、当前文件、轮转文件、最后心跳时间、错误信息、重连次数、最后重连时间。

功能要求：

- 支持日志轮转识别、断点续读、重启后按 offset + inode 恢复、错误自动重连、失败记录。
- Web 页面可查看采集器状态、offset、inode、轮转文件、错误重连信息、采集延迟、最后读取时间。
- **Web 页面支持对单个日志源的采集执行 启动 / 停止 / 重启**（操作需运维及以上权限，记录审计）。
- 采集状态统一存中心 MySQL（`ls_collector_state`），由采集线程每 10 秒心跳上报，offset 变更在**处理落库后**提交（见 §4.5）。

### 3.5 告警规则

规则类型（MVP 全部实现）：

1. 立即告警：命中即通知。
2. N 秒内 M 次：滑动窗口内达到次数才告警（窗口语义见 §4.6）。
3. 连续 N 次：连续命中 N 次才告警（语义见 §4.7）。
4. 恢复通知：基础版（进入告警态后连续 X 秒无命中判定恢复，见 §4.8）。
5. 聚合通知：基础版（固定窗口合并，见 §4.9）。
6. 维护窗口：支持跨天、每日周期，窗口内只记录不通知（见 §4.10）。

字段必须包含：

- 规则名称、严重级别（CRITICAL / MAJOR / MINOR）、是否启用
- 关联日志源：**多对多**（中间表 `ls_alert_rule_source`）
- 匹配条件：引用关键字库 / 错误码库（多对多），或直接配置正则 / 日志级别（ERROR、FATAL 等）
- 排除条件（白名单）：命中排除关键字则不告警（黑名单即匹配条件本身）
- 是否告警（关闭则只保存报错日志不通知，用于观察期规则）
- 静默期秒数、时间窗口秒数、触发次数、连续次数
- 是否恢复通知、恢复判定窗口秒数（默认 300）
- 是否聚合通知、聚合窗口秒数（默认 60）
- 维护窗口开始/结束时间（HH:mm，支持跨天）
- @人规则（引用 `ls_mention_rule`）
- 通知模板（引用 `ls_notify_template`）

匹配类型与操作符：关键字、正则表达式、错误码（提取规则见 §4.2）、日志级别；包含 / 不包含 / 等于 / 正则匹配。

### 3.6 通知渠道与钉钉通知

**渠道抽象**：通知渠道统一为 `ls_notify_channel`（type + config_json），MVP 实现 type=`dingtalk`，企微/飞书/邮件/Webhook 仅作枚举预留。**不再单独设钉钉配置表与钉钉专用 API**。

钉钉渠道 config_json 字段：Webhook、Secret 加签、消息类型（**固定 markdown**，用于关键字加粗高亮）、默认 @人、是否 @所有人、重试次数（默认 3）、超时时间（默认 5s）、是否启用。

钉钉消息内容模板：

```text
【LogSentinel 告警】
项目：fscr-order
主机：192.168.1.10
环境：prod
级别：ERROR
时间：2026-09-28 10:23:45
错误码：500
关键字：NullPointerException
日志文件：/opt/fscr/app/logs/fscr-order/error.log
内容：
...
@张三 @李四
```

消息优化要求（**按以下顺序执行，单步失败跳过不影响整体发送**）：

1. 解码 `\uXXXX` Unicode 转义
2. 清理 ANSI 颜色码
3. 解码 HTML 实体
4. 常见乱码替换
5. 关键字 markdown 加粗高亮
6. 超长截断：正文超过 **4000 字节**截断，尾部追加"完整内容请登录 LogSentinel 查看"及详情页链接
7. **脱敏**（手机号、身份证、密码、token，正则替换）：**仅作用于发送用的"优化后内容"，数据库"原始内容"完整保留不脱敏**

通知失败必须记录：告警 ID、渠道、请求内容、失败原因、重试次数、最终状态；多次失败后入失败记录，**支持 Web 页面人工重发**。

### 3.7 报错日志存储与查询

保存字段必须包含：项目、主机、日志源、文件路径、行号、级别、错误码、关键字、原始内容、优化后内容、发生时间、创建时间、**告警状态（已通知 / 已抑制 / 仅记录）**、告警指纹（幂等键，见 §4.5）。

功能要求：

- 按时间、项目、主机、级别、错误码、关键字查询；分页；详情查看。
- 删除、批量删除（运维及以上权限，记录审计）。
- **导出（MVP 实现）**：CSV 格式，单次上限 10000 条；导出内容默认使用"优化后内容"（已脱敏），导出操作记录审计。
- 保留策略：`ls_error_log` 默认 30 天（可配置），定时任务清理；告警/通知记录默认 90 天；**审计日志默认 180 天且界面不可删除**。

### 3.8 Web 页面

必须包含：登录页、仪表盘、项目管理、主机管理、日志源管理、采集管理（状态查看 + 启停）、告警规则、关键字配置、错误码配置、@人配置、通知渠道配置（含钉钉）、通知模板配置、报错日志查询、告警记录、通知记录、通知失败记录（含人工重发）、用户与权限、操作审计、系统设置。

### 3.9 配置中心

统一管理：通知渠道配置、通知模板配置、服务器（主机）配置、日志源配置、@人配置、错误码配置、关键字配置、告警规则配置、采集参数配置。

**配置热更新范围（MVP）**：告警规则、关键字、错误码、通知渠道、通知模板、@人 —— 修改后 ≤30 秒生效无需重启（DB 变更轮询/事件刷新）。采集间隔、线程池、端口等系统参数修改后需重启，界面明确标注。增强热更新为后续扩展。

### 3.10 统计看板

首页仪表盘必须展示：今日告警数、今日通知数、今日通知失败数、Top 项目、Top 错误码、告警趋势图、采集异常列表、采集延迟、最近告警列表。支持按时间范围、项目、环境筛选。统计口径时区统一为服务器时区（默认 Asia/Shanghai），页面展示与筛选均按此时区。

## 4. 告警引擎核心语义定义（强制实现标准）

> 本章为开发的强制约定，所有语义必须在单元测试中覆盖。

### 4.1 告警指纹与幂等

- 告警指纹 = SHA-256(project_id + log_source_id + file_path + inode + offset + 内容前 512 字节)
- 语义为 **at-least-once + 幂等去重**：同指纹 24 小时内只生成一条报错日志与一次告警（指纹存 Redis，过期 24h）。
- **不承诺 exactly-once**。

### 4.2 错误码提取

- 错误码不直接做裸文本包含匹配（避免"500"误中端口号等数字）。
- 每个错误码配置**提取正则**，如 HTTP 500：`(?<!\d)500(?!\d)`；业务码 `ERR_XXX`：`ERR_[A-Z0-9_]+`。
- 匹配流程：先用提取正则从日志行提取候选码，再与规则引用的错误码比对。

### 4.3 多行堆栈合并

- 默认规则：行首匹配 `^\d{4}-\d{2}-\d{2}`（时间戳）视为新日志行起点，否则并入上一条。
- 起始正则每个日志源可配置。
- 合并上限：单条最多 200 行，超出截断为独立条目。

### 4.4 日志轮转

- **rename+create 模式**：检测 inode 变化 → 记录 `rotated_file`，读完旧文件剩余内容后切换到新文件从头读。
- **copytruncate 模式**：inode 不变但当前文件大小 < 已记录 offset → 判定截断，offset 重置为 0 重读（接受此模式下的重复风险，由指纹幂等兜底）。

### 4.5 断点续读与 offset 提交

- offset 按字节记录；**提交时机：该 offset 对应的日志条目完成规则匹配并落库 `ls_error_log`（或确认未命中）之后才提交**，提交前宕机则重启后重读，由指纹幂等去重。
- 重启恢复：按 (log_source_id, inode) 查 `ls_collector_state`，inode 匹配则从 offset 继续，否则从头读当前文件。
- 断点状态统一存中心 MySQL。

### 4.6 N 秒内 M 次

- **滑动窗口**：以 (rule_id, log_source_id) 为键，命中时间戳存入 Redis ZSET，每次命中时剔除窗口外元素后计数，≥M 触发告警，触发后清空窗口重新计数。

### 4.7 连续 N 次

- 维度：同一 (rule_id, log_source_id)。
- 判定：相邻两条命中之间**无任何未命中日志行**则连续计数 +1，中间出现未命中行则清零；达到 N 触发告警并清零。

### 4.8 恢复通知

- 规则因"N 秒内 M 次"或"连续 N 次"进入告警态后开始计时：连续 `recover_window_seconds`（默认 300 秒，可配）无任何命中 → 判定恢复，发送恢复通知，退出告警态。
- 立即告警类规则不进入告警态，不产生恢复通知。

### 4.9 聚合通知

- 开启聚合的规则：命中后不立即发送，按 (rule_id, project_id) 归入聚合窗口（`aggregate_window_seconds`，默认 60 秒）。
- 窗口结束合并为一条消息发送，正文最多附 10 条命中摘要，超出以"等 N 条"表示。
- 聚合窗口内 CRITICAL 级别命中可配置为立即穿透发送。

### 4.10 维护窗口

- 每日周期生效，支持跨天（如 22:00–06:00）。
- 优先级最高：窗口内所有命中只保存报错日志（告警状态=已抑制），不发送任何通知；窗口结束后不补发。

### 4.11 静默期

- 维度：(rule_id, host_id, 匹配键)。匹配键 = 错误码或关键字；未配置匹配键时退化为 (rule_id, host_id)。
- 静默期内相同维度命中：保存报错日志（告警状态=已抑制），不通知。

### 4.12 通知流水线

- 采集 → 匹配 → 落库（同步）；通知（**异步**，独立线程池 + 有界队列，容量 10000，满则丢弃 MINOR 并记录）。
- 钉钉限流：遵循机器人 20 条/分钟上限，Redis 计数；超限按级别优先级排队（CRITICAL > MAJOR > MINOR），排队超过 5 分钟的 MINOR 降级合并为聚合摘要。

## 5. 数据库设计

### 5.1 表清单

```text
ls_user                用户
ls_role                角色
ls_user_role           用户-角色关联
ls_project             项目
ls_host                服务器/主机
ls_log_source          日志源
ls_collector_state     采集状态
ls_keyword             关键字库（可复用资源）
ls_error_code          错误码库（可复用资源）
ls_alert_rule          告警规则
ls_alert_rule_source   规则-日志源关联（M:N）
ls_rule_keyword        规则-关键字关联（M:N，含匹配操作符 include/exclude）
ls_rule_error_code     规则-错误码关联（M:N）
ls_mention_rule        @人规则
ls_notify_channel      通知渠道（钉钉为 type 之一）
ls_notify_template     通知模板
ls_alert_record        告警记录
ls_notify_record       通知记录
ls_notify_fail_record  通知失败记录（死信，支持人工重发）
ls_error_log           报错日志
ls_audit_log           审计日志
```

### 5.2 关键字段

```text
ls_user:
  id, username, password_hash, real_name, status,
  login_fail_count, locked_until, last_login_at, created_at, updated_at

ls_host:
  id, name, ip, ssh_port, auth_type(PASSWORD/KEY), username,
  password_enc, private_key_enc, host_type(LOCAL/REMOTE),
  env, tags, status, last_check_at, remark

ls_project:
  id, name, code(UK), owner, env, notify_channel_id(FK),
  default_mention_id(FK), status, description

ls_log_source:
  id, project_id(FK), host_id(FK), name, path_pattern, exclude_pattern,
  encoding(UTF-8/GBK), multiline_pattern, interval_seconds,
  env, tags, enabled

ls_keyword:
  id, name, pattern, match_op(CONTAINS/NOT_CONTAINS/EQUALS/REGEX), enabled

ls_error_code:
  id, code, extract_regex, description, enabled

ls_alert_rule:
  id, name, severity(CRITICAL/MAJOR/MINOR),
  match_type(KEYWORD/REGEX/ERROR_CODE/LOG_LEVEL), match_content,
  alert_enabled, silence_seconds, window_seconds, threshold_count,
  consecutive_count, recover_notify, recover_window_seconds,
  aggregate_notify, aggregate_window_seconds,
  maintenance_start, maintenance_end,
  mention_id(FK), template_id(FK), enabled

ls_mention_rule:
  id, name, mobile, dingtalk_userid, scope(PROJECT/HOST/RULE), ref_id

ls_notify_channel:
  id, name, type(dingtalk/wecom/feishu/email/webhook),
  config_json(敏感字段加密), enabled

ls_notify_template:
  id, name, channel_type, msg_type, content_template, enabled

ls_collector_state:
  id, host_id, log_source_id, status, last_read_position, offset, inode,
  current_file, rotated_file, last_heartbeat, error_msg, retry_count, last_retry_at

ls_error_log:
  id, project_id, host_id, log_source_id, file_path, line_no, level,
  error_code, keyword, raw_content, optimized_content, occurred_at,
  created_at, alert_status(NOTIFIED/SUPPRESSED/RECORD_ONLY), fingerprint(UK)

ls_notify_fail_record:
  id, channel_id, alert_id, request_body, error_msg, retry_count,
  status(FAILED/RESEND_SUCCESS/RESEND_FAILED), created_at

ls_audit_log:
  id, user_id, action, target, ip, result, detail, created_at
```

## 6. 权限设计（RBAC）

角色：管理员（ADMIN）、运维（OPS）、只读（VIEWER）。

| 功能 | 管理员 | 运维 | 只读 |
|------|:------:|:----:|:----:|
| 用户与角色管理 | ✓ | ✗ | ✗ |
| 系统设置 | ✓ | ✗ | ✗ |
| 项目/主机/日志源 增删改 | ✓ | ✓ | ✗ |
| 关键字/错误码/告警规则/@人/模板配置 | ✓ | ✓ | ✗ |
| 通知渠道配置 | ✓ | ✗ | ✗ |
| 采集器 启动/停止/重启 | ✓ | ✓ | ✗ |
| 报错日志 删除/导出 | ✓ | ✓ | ✗ |
| 通知失败记录 人工重发 | ✓ | ✓ | ✗ |
| 所有页面查看与查询 | ✓ | ✓ | ✓ |

- 接口级鉴权：每个 API 标注所需角色，后端统一拦截校验。
- 敏感操作（删除、导出、渠道修改、采集器控制）前端二次确认 + 后端审计。

## 7. API 概览

```text
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
PUT    /api/v1/auth/password               修改密码
GET    /api/v1/health                      健康检查（无需鉴权）
GET    /api/v1/dashboard                   仪表盘汇总

CRUD   /api/v1/users
CRUD   /api/v1/roles

CRUD   /api/v1/projects
CRUD   /api/v1/hosts
POST   /api/v1/hosts/{id}/test-ssh         测试 SSH 连接（OPS+，记审计）

CRUD   /api/v1/log-sources

GET    /api/v1/collector/status            采集状态列表（只读，不开放 CRUD）
POST   /api/v1/collector/{logSourceId}/start
POST   /api/v1/collector/{logSourceId}/stop
POST   /api/v1/collector/{logSourceId}/restart

CRUD   /api/v1/alert-rules
CRUD   /api/v1/keywords
CRUD   /api/v1/error-codes
CRUD   /api/v1/mentions
CRUD   /api/v1/notify-channels
POST   /api/v1/notify-channels/{id}/test   发送测试消息
CRUD   /api/v1/notify-templates

GET    /api/v1/error-logs
GET    /api/v1/error-logs/{id}
GET    /api/v1/error-logs/export           CSV 导出（OPS+，记审计）
DELETE /api/v1/error-logs/{id}
POST   /api/v1/error-logs/batch-delete

GET    /api/v1/alerts
GET    /api/v1/notify-records
GET    /api/v1/notify-fail-records
POST   /api/v1/notify-fail-records/{id}/resend   人工重发

GET    /api/v1/audit-logs
GET    /api/v1/system/settings
PUT    /api/v1/system/settings

GET    /api/v1/stream                      SSE 实时推送（新告警/采集异常）
```

> CRUD = GET 列表 / GET 详情 / POST / PUT / DELETE。所有列表接口支持分页（page/size，默认 1/20，size 上限 200）。

## 8. 告警处理流程（修正版）

1. 采集器读取日志文件（本机内嵌线程）。
2. 多行合并（§4.3），处理轮转（§4.4）与断点（§4.5）。
3. 按项目、日志源、规则匹配关键字/错误码/正则/日志级别。
4. **命中后立即保存报错日志**：生成告警指纹，指纹已存在则跳过（幂等）；否则落库 `ls_error_log`，告警状态=待通知，并提交 offset。
5. 通知决策（顺序）：维护窗口 → 是否告警开关 → 静默期 → 频率阈值/连续次数 → 聚合归并。任一环节抑制则更新告警状态=已抑制，流程结束。
6. 渲染通知模板 → 中文优化与截断（§3.6）→ 复制"原始内容"生成"优化后内容"并脱敏。
7. **异步发送**（§4.12）：通知线程池 + 限流队列，按 @人优先级（规则 > 主机 > 项目）解析手机号 at。
8. 保存告警记录与通知记录。
9. SSE 推送 Web 页面实时展示。
10. 发送失败自动重试（默认 3 次，间隔 10s/60s/300s），仍失败写入 `ls_notify_fail_record`，支持人工重发。

## 9. 安全需求

- 认证：JWT（access token 2 小时 + refresh token 7 天），**前端 localStorage 存储，经 Authorization Header 携带**；因不使用 Cookie，**无需 CSRF 防护**（若后续改为 Cookie 方案，必须启用 CSRF Token）。
- 授权：RBAC 接口级鉴权（§6）。
- 密码 BCrypt 加密存储；登录连续失败 5 次锁定 15 分钟（`locked_until`）。
- SSH 密码/私钥、渠道 Secret 等 AES-256 加密存储，密钥仅来自环境变量；界面与接口返回值脱敏（`******`）。
- 配置导出与日志导出均使用脱敏后内容。
- XSS 防护：前端默认转义 + 后端富文本/日志内容展示白名单过滤；所有接口参数化查询防 SQL 注入。
- 审计日志：记录登录、配置增删改、删除/导出、采集器控制、测试连接、人工重发；审计日志界面不可删除。
- 初始管理员：由初始化 SQL 预置 `admin / Admin@123`，首次登录强制修改密码。
- 敏感操作二次确认（前端）+ 审计（后端）。

## 10. 可靠性需求

- 重启恢复：服务重启后按 offset/inode 继续读取（§4.5）。
- 语义：**at-least-once + 幂等去重**（§4.1），不丢、不重告警。
- 限流：钉钉通知限流与优先级排队（§4.12）。
- 重试：通知失败阶梯重试，超限入死信可人工重发。
- 失败记录：采集失败、通知失败均落库。
- 静默/抑制命中的日志仍完整保存（告警状态可区分）。
- 采集断点续读、日志轮转、错误自动重连（指数退避，上限 5 分钟，重连次数上报）。

## 11. 部署需求

- **主方式：Docker Compose 一键启动**（服务：mysql、redis、backend、nginx；nginx 反代前端静态资源与 `/api`，SSE 端点关闭缓冲）。
- **备选方式（与 Docker 互斥，二选一）**：裸机 jar + systemd 托管 + Nginx，提供 systemd 配置示例。
- 配置热更新范围见 §3.9。
- 单机部署；集群部署架构预留（采集状态、指纹、窗口计数均已外置 MySQL/Redis，无本地粘性状态）。
- 健康检查：`GET /api/v1/health`（compose 配置 healthcheck）。
- 数据库备份：README 提供 mysqldump 每日备份脚本示例。
- 环境变量与配置文件分离：密钥、DB 连接、Redis 连接均走环境变量，compose 提供 `.env.example`。
- MVP 采集器内嵌后端进程；独立部署/Agent 化为后续扩展。

## 12. 非功能需求

| 类别 | 指标 |
|------|------|
| 性能 | 采集延迟 P95 ≤ 10 秒（默认采集间隔 5s、吞吐未超上限前提下） |
| 性能 | 告警发送 P95 ≤ 15 秒（未触发钉钉限流排队时） |
| 吞吐 | 单实例峰值 ≥ 2000 行/秒；采集侧有界队列背压，超限降级并记录 |
| 容量 | MVP 支持 50 个项目、200 个日志文件 |
| 可靠性 | 断点续读、at-least-once + 幂等、重试、死信、异常恢复、失败记录 |
| 安全 | 见 §9 |
| 可维护 | 模块清晰、日志完善（采集/匹配/通知分 logger）、异常处理完整 |
| 可部署 | Docker Compose 一键启动 |
| 可扩展 | 渠道抽象、采集器包隔离、状态外置，支持后续企微/飞书/邮件/Webhook、远程采集、Agent、集群 |

## 13. MVP 范围与后续扩展

### 13.1 MVP 必须完成

- 登录与 RBAC（三角色，含初始管理员与首次改密）。
- 项目、主机（含 SSH 连接测试）、日志源配置。
- 关键字库、错误码库、告警规则（六种规则类型基础版，语义见 §4）。
- 日志采集（**远程 SSH 采集为主** + 本机采集，内嵌采集器，含多行合并、轮转、断点续读、断线重连）。
- 钉钉通知与 @人（markdown、中文优化、截断、脱敏、重试、死信重发）。
- 邮件通知（SMTP，作为第二通知渠道）。
- 报错日志保存、查询、删除、**CSV 导出**。
- 基础仪表盘（§3.10）。
- 采集管理页面（状态查看 + 启停）。
- SSE 实时推送（新告警/采集异常）。
- 通知渠道/通知模板配置（仅钉钉实现）。
- 操作审计。
- Docker Compose 部署、README、数据库初始化 SQL、API 文档。

### 13.2 后续扩展

- 企微、飞书、通用 Webhook（渠道抽象已预留）。
- 值班表。
- 增强版聚合/恢复通知（多维度聚合、抖动抑制）。
- Agent 自动注册、采集器独立部署。
- 集群部署。
- 全文检索（ES/OpenSearch）。
- 配置热更新增强（全量配置无重启生效）。

## 14. 验收用例

### 14.1 功能验收

1. 配置项目 fscr-order，日志路径 `/opt/fscr/app/logs/fscr-order/*.log`；配置关键字 `NullPointerException`、错误码 500（提取正则 `(?<!\d)500(?!\d)`）、@张三（已配手机号）。
2. 向日志写入包含该关键字的错误行（含多行堆栈），系统 10 秒内捕获，堆栈合并为一条。
3. 钉钉收到 markdown 消息，中文正常，关键字加粗，包含项目、日志内容，@张三 真实生效（手机号 at）。
4. 数据库保存报错日志（原始内容完整未脱敏，优化后内容已脱敏），Web 可查询、可删除、可导出 CSV。
5. 配置多个日志源（含 GBK 编码文件），均可正常采集。
6. 分别模拟 rename+create 与 copytruncate 轮转，采集不中断、不丢行。
7. 主机管理可测试 SSH 连接，操作有审计记录。
8. 采集管理页面可查看 offset、inode、轮转文件、重连次数，并可执行停止/启动，操作有审计。
9. 告警规则逐一验证：立即告警；N 秒内 M 次（滑动窗口）；连续 N 次（中间插入未命中行验证清零）；恢复通知（300 秒无命中后收到恢复消息）；聚合通知（60 秒窗口合并为一条）；维护窗口（跨天配置，窗口内只记录不通知）。
10. 静默期验证：静默期内命中仍保存报错日志且状态=已抑制，不发送通知。
11. 统计看板展示今日告警数、Top 项目、Top 错误码、趋势图、采集异常、采集延迟。
12. 断开网络模拟通知失败：自动重试 3 次后写入失败记录，页面人工重发成功。
13. 审计日志可查询上述全部操作。
14. 服务重启后采集从断点恢复，已告警日志不重复告警（指纹幂等）。

### 14.2 非功能验收

15. 性能：模拟 200 个日志文件、峰值 2000 行/秒写入，持续 10 分钟，采集延迟 P95 ≤ 10 秒，无 OOM。
16. 限流：1 分钟内构造 50 条告警，钉钉发送不超 20 条/分钟，CRITICAL 优先，超限 MINOR 降级聚合。
17. 安全：只读账号调用删除/导出接口返回 403；未登录访问任意 API 返回 401；登录失败 5 次账号锁定 15 分钟；报错日志含 `<script>` 时页面展示不执行；接口返回的主机密钥/渠道 Secret 为脱敏值。
18. 可靠性：采集进程中杀后重启，验证不丢（重启期间写入的日志被补采）不重（已告警内容不重复告警）。
19. 部署：干净机器上 `docker compose up -d` 一键启动，健康检查通过，admin 首次登录强制改密。

## 15. 交付物

- 完整源代码（backend、frontend）
- 数据库初始化 SQL（含表结构、索引、初始角色与管理员）
- Dockerfile 与 docker-compose.yml（含 .env.example）
- Nginx 配置（含 SSE 配置）
- systemd 配置示例（裸机备选）
- README 部署文档（含数据库备份说明）
- API 文档（含各接口所需角色）
- 示例配置（项目/日志源/规则/钉钉渠道示例）
- 基础单元测试（**必须覆盖 §4 全部告警引擎语义**）
- 操作截图或使用说明

项目最终命名统一使用：

- 产品名：LogSentinel
- 中文名：日志监控告警系统
- 仓库名：log-sentinel
- 描述：Web-based Log Monitoring & DingTalk Alerting Platform
