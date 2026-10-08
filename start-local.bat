@echo off
chcp 65001 >nul
title LogSentinel 本地环境启动
echo ==========================================
echo   日志监控告警系统 - 本地环境启动
echo ==========================================
echo.

REM ---------- 1. Redis（Docker 容器） ----------
echo [1/4] 启动 Redis（Docker）...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [失败] Docker Desktop 没有运行！
    echo 请先打开 Docker Desktop（桌面右下角鲸鱼图标变绿），再重新执行本脚本。
    echo.
    pause
    exit /b 1
)
docker start logsentinel-redis-dev >nul 2>&1
if %errorlevel% neq 0 (
    docker run -d --name logsentinel-redis-dev -p 6379:6379 redis:latest >nul 2>&1
)
docker ps --filter name=logsentinel-redis-dev --format "{{.Names}} {{.Status}}" | findstr /i "Up" >nul
if %errorlevel% neq 0 (
    echo.
    echo [失败] Redis 容器启动失败！
    echo 打开 Docker Desktop - 容器，手动启动 logsentinel-redis-dev 看报错，然后重试。
    echo.
    pause
    exit /b 1
)
echo       Redis 已运行

REM ---------- 2. MySQL（本机服务，确认在跑） ----------
echo [2/4] 检查 MySQL 服务...
sc query MySQL80 | findstr /i "RUNNING" >nul
if %errorlevel% equ 0 (echo       MySQL80 运行中) else (echo       [警告] MySQL80 未运行，请在“服务”里启动它)

REM ---------- 3. 后端（FastAPI，端口 8080） ----------
echo [3/4] 启动后端 http://localhost:8080 ...
REM 端口已被占用说明后端已在运行，跳过（避免 10048 报错）
netstat -ano | findstr "0.0.0.0:8080" | findstr /i "LISTENING" >nul
if %errorlevel% equ 0 (
    echo       后端已在运行，跳过重复启动
) else (
    start "LogSentinel-后端" /min cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8080"
)

REM ---------- 4. 前端（Vite，端口 5173） ----------
echo [4/4] 启动前端 http://localhost:5173 ...
netstat -ano | findstr ":5173" | findstr /i "LISTENING" >nul
if %errorlevel% equ 0 (
    echo       前端已在运行，跳过重复启动
) else (
    start "LogSentinel-前端" /min cmd /k "cd /d %~dp0frontend && npm run dev"
)

echo.
echo ==========================================
echo   启动完成！等 10 秒后打开浏览器：
echo   系统页面  http://localhost:5173
echo   API文档   http://localhost:8080/docs
echo   账号 admin / Admin@123（首登强制改密）
echo ==========================================
echo.
echo 后端、前端各开了一个最小化窗口，关掉窗口即停止对应服务。
pause
