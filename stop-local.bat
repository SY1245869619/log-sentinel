@echo off
chcp 65001 >nul
title LogSentinel 本地环境停止
echo ==========================================
echo   日志监控告警系统 - 本地环境停止
echo ==========================================
echo.

echo [1/3] 停止后端（uvicorn）...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /r "0.0.0.0:8080 .*LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo [2/3] 停止前端（vite）...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /r ":5173 .*LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo [3/3] 停止 Redis 容器...
docker stop logsentinel-redis-dev >nul 2>&1

echo.
echo 已全部停止（MySQL 是你本机服务，保持运行即可）。
pause
