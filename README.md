# LogSentinel 日志监控告警系统

Web-based Log Monitoring & DingTalk Alerting Platform
可部署在服务器上的 Web 日志监控与告警平台：集中部署后通过 SSH 连接多台服务器采集日志，按关键字/错误码/正则/日志级别规则发现异常，钉钉/邮件告警，报错日志存储查询。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy 2 + Redis + APScheduler |
| 前端 | React 18 + Vite + TypeScript + Ant Design 6（sereneTheme） |
| 数据库 | MySQL 8（表前缀 ls_） |
| 缓存/计算 | Redis（滑动窗口/限流/幂等指纹/断点） |
| 采集 | 进程内嵌线程，Paramiko SFTP（远程）+ 本地文件（本机） |
| 部署 | Docker Compose + Nginx，Jenkins 流水线 |

## 目录结构

```text
log-sentinel/
  backend/            后端（FastAPI）
    app/
      main.py         入口（启动初始化/路由注册）
      config.py       环境变量配置
      database.py     MySQL/Redis 连接
      models.py       全部数据表模型
      common/         响应/异常/安全(JWT/AES/BCrypt)/审计/文本优化
      modules/        auth/users/projects/hosts/log_sources/keywords/
                        error_codes/rules/mentions/channels/templates/
                        collector/notify/error_logs/audit/dashboard/system
      notify_engine/  钉钉加签发送 / 邮件 SMTP
      scheduler.py    周期任务（热更新/聚合/恢复/保留清理）
    tests/            单元测试（pytest，覆盖 §4 告警语义）
  frontend/           前端（React + antd6）
    src/sereneTheme.ts  主题（不可修改）
  sql/init.sql        数据库初始化（21 张表 + 种子数据）
  deploy 相关：docker-compose.yml / Jenkinsfile / .env.example
  docs/               需求说明书
```

## 快速开始（Docker 一键部署）

前置：服务器已安装 Docker 与 docker compose 插件。

```bash
# 1. 配置密钥
cp .env.example .env
# 编辑 .env：MYSQL_ROOT_PASSWORD / JWT_SECRET(≥32字节) / AES_KEY(正好16字节)
# 可选：DINGTALK_* / EMAIL_* 首次启动自动预置为默认渠道

# 2. 启动全部服务
docker compose up -d --build

# 3. 验证
curl http://localhost:8080/api/v1/health        # 后端健康检查（容器内）
# 浏览器访问 http://<服务器IP>:6064
# 初始账号 admin / Admin@123（.env 中 ADMIN_INITIAL_PASSWORD 可改），首次登录强制改密
```

服务组成：mysql(内部) / redis(内部) / backend(内部 8080) / web(nginx，对外 6064)。

## 本机开发

```bash
# 后端（需本机有 MySQL 与 Redis，或用 docker compose 只起这两个）
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8080
# API 文档（Swagger）：http://localhost:8080/docs

# 前端
cd frontend
npm install
npm run dev        # http://localhost:5173，已配置 /api 代理到 8080

# 单元测试
cd backend
python -m pytest tests -q
```

## 使用流程（对应验收用例）

1. **主机管理** → 新增目标服务器（REMOTE，填 SSH 密码或私钥）→ 点"测试SSH"验证连通
2. **项目管理** → 新增项目（如 fscr-order），可选默认钉钉渠道与默认 @人
3. **@人配置** → 新增人员（姓名 + 手机号，钉钉 @ 依赖手机号）
4. **关键字/错误码配置** → 如 `NullPointerException`；错误码 500 提取正则 `(?<!\d)500(?!\d)`
5. **日志源管理** → 选择项目与主机，填日志路径 `/opt/fscr/app/logs/fscr-order/*.log`
6. **告警规则** → 关联日志源与关键字，选择触发方式（立即/N秒内M次/连续N次），配静默期/恢复/聚合/维护窗口
7. **采集管理** → 对日志源点"启动"，观察状态变为"运行中"，查看 offset/inode/心跳
8. 向目标日志写入含关键字的错误行 → 10 秒内钉钉收到告警（@对应人）
9. **报错日志** → 查询/详情/删除/导出 CSV；**通知失败** → 死信可人工重发

## 关键机制（详见需求说明书 §4）

- 断点续读：offset 按字节存 Redis，处理落库后才提交；重启自动恢复
- 日志轮转：rename+create（inode 变化）与 copytruncate（size<offset 归 0）双模式
- 幂等：告警指纹 SHA-256，24h 内同指纹不重复告警（at-least-once + 幂等）
- 静默期：(规则, 主机, 匹配键) 三元组，抑制期命中仍保存日志（状态=已抑制）
- 钉钉限流 20 条/分钟，CRITICAL 穿透；失败阶梯重试 10s/60s/300s → 死信
- 脱敏：手机号/身份证/密钥，仅作用于"优化后内容"，原始内容完整保留

## 安全说明

- JWT（access 2h + refresh 7d）Header 携带；RBAC 三角色（管理员/运维/只读）
- SSH 密码/私钥、渠道 Secret AES 加密存储（密钥来自 AES_KEY 环境变量）
- 登录失败 5 次锁定 15 分钟；敏感操作二次确认 + 审计日志
- `.env` 严禁提交 Git（已 gitignore）

## Jenkins 自动部署

见 [JENKINS_DEPLOY.md](./JENKINS_DEPLOY.md)。

## 数据库备份

```bash
docker exec logsentinel-mysql mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" logsentinel \
  > backup_$(date +%Y%m%d).sql
```
