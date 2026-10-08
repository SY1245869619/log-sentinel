# LogSentinel 日志监控告警系统 - Docker 部署指南

> 适用：已有一台 Linux 服务器（10.99.99.152，Docker 等环境由运维装好）。
> 本文档带你完成**首次部署**：你只需在服务器上敲 2 条命令、在 Jenkins 网页上点几下按钮；
> 完成之后，每次更新代码点一次"立即构建"即可自动部署。

---

## 目录

0. [部署流程总览](#0-部署流程总览)
1. [前置条件](#1-前置条件)
2. [项目需要准备的文件](#2-项目需要准备的文件)
3. [Jenkins 项目配置](#3-jenkins-项目配置)
4. [首次构建与部署](#4-首次构建与部署)
5. [后续更新流程](#5-后续更新流程)
6. [常用运维命令](#6-常用运维命令)
7. [故障排查](#7-故障排查)

---

## 0. 部署流程总览

1. **配任务** — [第 3 章](#3-jenkins-项目配置)：Jenkins 新建任务 `log-sentinel`，填 Git 仓库地址（只做一次）
2. **建目录** — [第 4 章 · 4.1](#41-在服务器上创建部署目录一次性手动)：服务器敲 2 条命令创建 `/opt/logsentinel`（只做一次）
3. **点构建** — [第 4 章 · 4.2](#42-在-jenkins-上触发首次构建)：机器自动完成：拉代码 → 构建 4 个镜像/容器 → 启动 → 体检
4. **访问** — 浏览器打开 `http://10.99.99.152:6064`，账号 `admin / Admin@123`，首次登录强制改密

系统由 4 个容器组成：`logsentinel-mysql`、`logsentinel-redis`、`logsentinel-backend`、`logsentinel-web`。
数据（MySQL/Redis/日志）持久化在 `/opt/logsentinel`，重新部署不会丢。

---

## 1. 前置条件

**服务器端已就绪**（由运维或管理员提前配置好）：

| 组件 | 说明 | 验证方式 |
|------|------|----------|
| Jenkins | 已安装并运行，浏览器可访问 | `http://10.99.99.152:<Jenkins端口>` |
| Docker | 已安装，支持 compose 插件 | `docker --version && docker compose version` |
| Git 凭据 | GitHub 仓库的 **用户名 + 访问令牌（Token）** | 见 7.4 |
| 部署目录 | `/opt/logsentinel` 已创建、Jenkins 可写 | 见 4.1 |
| 安全组/防火墙 | 服务器 **6064** 端口已对外开放 | 浏览器访问用 |

> 首次构建需从外网拉取基础镜像（python:3.12-slim、node:20-alpine、nginx、mysql:8.4、redis:7.4-alpine），
> 请确认服务器能访问 Docker Hub（或已配置镜像加速）。

---

## 2. 项目需要准备的文件

这些文件已在代码仓库里，**全部不用改**：

```text
log-sentinel/                ← Git 仓库根目录
├── Jenkinsfile              # 自动化脚本：拉代码 → 构建 → 部署 → 体检
├── docker-compose.yml       # 4 个服务的编排清单
├── .env.example             # 环境变量示例（密钥模板）
├── sql/init.sql             # 数据库初始化（首次启动 MySQL 自动执行）
├── backend/
│   ├── Dockerfile           # 后端镜像（Python 3.12 + FastAPI）
│   ├── requirements.txt
│   └── app/                 # 后端源码
└── frontend/
    ├── Dockerfile           # 前端镜像（Node 构建 + Nginx 托管）
    ├── nginx.conf           # 反向代理 /api 到后端，SSE 关闭缓冲
    └── src/                 # 前端源码
```

### 2.1 docker-compose.yml 关键点

- `web` 服务对外端口 **6064**（`WEB_PORT` 可改）
- `mysql` / `redis` 不对外暴露，仅容器网络内访问
- 数据持久化：`/opt/logsentinel/data/mysql`、`/opt/logsentinel/data/redis`、`/opt/logsentinel/logs`
- `LOG_ROOT`（默认 /var/log）只读挂载到后端容器 `/logs` —— **仅"本机模式"采集部署机自身日志时需要**；远程 SSH 采集不依赖它

### 2.2 Jenkinsfile 工作流程

1. **Checkout**：拉取仓库代码
2. **Build Docker Images**：`docker compose build` 构建 backend 与 web 镜像
3. **Deploy**：
   - 创建 `/opt/logsentinel` 各数据目录
   - 同步 `docker-compose.yml` 与 `sql/init.sql` 到部署目录
   - **首次自动生成 `.env`（随机密钥）**，已存在则保留不覆盖
   - `docker compose up -d` 启动 4 个容器
4. **Health Check**：等待 40 秒后检查 `logsentinel-backend` 健康状态，失败则打印日志并报错

---

## 3. Jenkins 项目配置

### 3.1 新建任务、选择流水线（Pipeline）

1. 打开 Jenkins：`http://10.99.99.152:<Jenkins端口>`
2. 点击左侧 **新建任务**
3. 输入任务名称：`log-sentinel`
4. 类型选择 **流水线（Pipeline）**，点击 **确定**

### 3.2 配置 General

- **描述**：LogSentinel 日志哨兵：Web 日志监控与钉钉/邮件告警平台（FastAPI + React + MySQL + Redis）
- （可选）勾选 **丢弃旧的构建**，最大构建数 10

### 3.3 配置流水线（Pipeline）

| 配置项（界面名） | 操作 | 值 |
|------|------|-----|
| 定义（Definition） | 选择 | 来自 SCM 的 Pipeline 脚本（Pipeline script from SCM） |
| 源码管理（SCM） | 选择 | Git |
| 仓库地址（Repository URL） | 输入 | `https://github.com/SY1245869619/log-sentinel.git` |
| 凭据（Credentials） | 选择 | 配置好的 Git 访问凭据（见 7.4，ID 建议 `git-pat`） |
| 要构建的分支（Branches to build） | 输入 | `*/main`（以仓库页显示为准） |
| 脚本路径（Script Path） | 输入 | `Jenkinsfile` |

填完点击 **保存**。

---

## 4. 首次构建与部署

### 4.1 在服务器上创建部署目录（一次性，手动）

```bash
sudo mkdir -p /opt/logsentinel
sudo chown -R $USER:$USER /opt/logsentinel
```

说明：

- `/opt/logsentinel` 是程序在服务器上"安家"的文件夹，**只在首次部署时创建一次**；
- 下面的 `data/mysql`、`data/redis`、`logs` 子目录由 Jenkins 自动创建；
- 如果 Jenkins 以独立账户运行（如 `jenkins`），把 `$USER` 换成该账户名。

### 4.2 在 Jenkins 上触发首次构建

1. 进入 `log-sentinel` 任务页 → 点击 **立即构建**
2. 查看 **控制台输出**，等待 4 个阶段依次变绿：
   - `Checkout`（拉取代码）
   - `Build Docker Images`（首次较慢，约 5~15 分钟：要拉基础镜像、装 pip/npm 依赖）
   - `Deploy`（启动容器）
   - `Health Check`（体检）

控制台最后出现 `✅ 构建并部署成功，访问 http://10.99.99.152:6064` 即完成。

### 4.3 配置密钥（重要，首次部署后必做）

Jenkins 首次部署自动生成的 `.env` 使用**随机密钥**，位于 `/opt/logsentinel/.env`。
如需预置默认钉钉/邮件渠道，编辑该文件追加：

```bash
sudo vi /opt/logsentinel/.env
```

```ini
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=你的token
DINGTALK_SECRET=SEC你的加签
EMAIL_HOST=smtp.qq.com
EMAIL_PORT=465
EMAIL_USER=1245869619@qq.com
EMAIL_PASSWORD=你的SMTP授权码
EMAIL_TO=收件人1@xx.com,收件人2@xx.com
```

> 渠道也可以不在这里配，直接登录系统后在 **通知渠道** 页面可视化配置（密钥同样加密存储）。
> 修改 `.env` 后需重启后端生效：`cd /opt/logsentinel && docker compose up -d --force-recreate backend`

### 4.4 验证部署

```bash
# ① 查看 4 个容器状态（STATUS 为 Up / healthy 即正常）
docker ps | grep logsentinel

# ② 健康检查（返回 {"code":0,...} 即正常）
curl http://127.0.0.1:6064/api/v1/health

# ③ 浏览器访问（需安全组已放行 6064）
#    http://10.99.99.152:6064   账号 admin / Admin@123（首次登录强制改密）
```

> 浏览器打不开？到云服务器控制台 → 安全组/防火墙，放行 **TCP 6064** 端口；
> 若服务器有 control-proxy 代理，参考 7.6 放行 6064。

---

## 5. 后续更新流程

```bash
git add .
git commit -m "update: 说明改了啥"
git push origin main
```

然后 Jenkins 任务页点 **立即构建**。

> **数据不会丢**：数据库、Redis、应用日志都在 `/opt/logsentinel` 下，重新部署不影响。
> **MySQL 表结构变更注意**：`sql/init.sql` 只在 MySQL **首次**启动（数据目录为空）时执行；
> 后续加表/改表需手动执行 SQL 或删除数据目录重建（会丢数据，慎用）。

---

## 6. 常用运维命令

```bash
# 查看容器状态
docker ps | grep logsentinel

# 查看后端运行日志（Ctrl+C 退出）
docker logs -f logsentinel-backend

# 重启某个服务
cd /opt/logsentinel && docker compose restart backend

# 进入后端容器排查
docker exec -it logsentinel-backend /bin/bash

# 停止全部（数据不丢）
cd /opt/logsentinel && docker compose down

# 手动重新部署（不走 Jenkins）
cd /opt/logsentinel && docker compose up -d --build

# 数据库备份
docker exec logsentinel-mysql mysqldump -uroot -p"<.env中的MYSQL_ROOT_PASSWORD>" logsentinel > backup_$(date +%Y%m%d).sql
```

---

## 7. 故障排查

### 7.1 Jenkins 构建报错 "docker: command not found"

**原因**：Jenkins 容器没权限调用宿主机 Docker。

**解决**：联系管理员，确认 Jenkins 启动时挂载了：
```bash
-v /var/run/docker.sock:/var/run/docker.sock
-v /usr/bin/docker:/usr/bin/docker
```

### 7.2 构建成功但容器没启动

```bash
cd /opt/logsentinel
docker compose ps
docker compose logs backend | tail -50
docker compose logs mysql | tail -50
```

**常见原因**：
- 6064 端口被占用 → `sudo lsof -i:6064` 查看
- `.env` 中 `AES_KEY` 不是正好 16 字节 / `JWT_SECRET` 不足 32 字节 → 后端启动报错，日志中有明确提示
- MySQL 还没就绪后端就先启动失败 → compose 已配置健康检查依赖，重新 `docker compose up -d` 即可

### 7.3 Health Check 失败

```bash
docker inspect --format='{{.State.Health.Status}}' logsentinel-backend
docker logs logsentinel-backend --tail 100
```

后端首次启动要等 MySQL 初始化完成（约 30~60 秒），若偶发超时可在 Jenkins 再点一次构建。

### 7.4 Git 拉取失败

**配置 GitHub 凭据（只需做一次）**：

1. 生成 Token：GitHub → 头像 → `Settings` → 最底部 `Developer settings` → `Personal access tokens` → `Tokens (classic)` → `Generate new token (classic)` → 勾选 `repo` → 生成并复制 `ghp_` 开头的 Token
2. Jenkins → 凭据 → 系统 → 全局凭据 → 添加凭据：
   - 类型：**Username with password**
   - Username：GitHub 用户名 `SY1245869619`
   - Password：粘贴 Token（不是账号密码）
   - ID：`git-pat`
3. 回到任务配置页，凭据选择 `git-pat`，保存后重新构建

### 7.5 代码改了，浏览器里还是旧页面

生产环境用的是**镜像内文件**，必须重新构建部署（Jenkins 点构建，或服务器上 `docker compose up -d --build`）。
强刷浏览器（Ctrl+F5）排除缓存。

### 7.6 容器正常但外部无法访问（Connection refused）

**现象**：`curl http://127.0.0.1:6064` 正常，但 `curl http://10.99.99.152:6064` 拒绝连接。

**原因**：服务器 control-proxy 代理未放行 6064。

**解决**：

1. SSH 登录代理服务器：`ssh -p 2222 169.254.133.12`
2. 编辑配置：`sudo vi /etc/default/proxy-trigger`
3. Vim 操作：`G` 到最后一行 → `yy` 复制上一行规则 → `p` 粘贴 → `:s/6063/6064/g` 替换端口 → `:wq` 保存

   > **重要**：务必用 `yy`+`p` 复制已有规则，不要手写（隐藏字符会导致规则无效）。

4. 重启代理：`sudo systemctl restart control-proxy.service`
5. 验证：`curl -v http://10.99.99.152:6064/api/v1/health`

### 7.7 钉钉收不到告警

排查顺序：

1. **通知渠道**页面点"测试发送" → 成功说明渠道正常
2. 检查告警规则：是否启用、`发送通知`开关是否打开、是否处于维护窗口/静默期
3. **报错日志**页面看记录状态：`已抑制`（静默/维护窗口）、`仅记录`（未触发阈值）、`已通知`（已发送）
4. **通知记录** / **通知失败**页面看具体错误（如 webhook 失效、加签错误、限流）
5. 失败记录可点"人工重发"验证

### 7.8 采集一直"重连中"

1. **主机管理**点"测试SSH"确认账号密码/私钥有效
2. 确认目标服务器日志路径存在且有读权限（采集用的是 SSH 账号的权限）
3. 远程 glob 依赖目标机的 `bash`（`globstar`），极简系统没有 bash 时 `**` 递归不可用，改用单层 `*`
4. 看 `docker logs logsentinel-backend` 中 `collector` 相关错误
