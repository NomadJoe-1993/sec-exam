@echo off
echo 📱 证券从业 · 掌上刷题 服务器启动中...
echo.

cd /d C:\Users\34558\Desktop\证券从业\mobile

REM 检查 Node.js
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ 未找到 Node.js，尝试使用 Python...
    where python >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        python -m http.server 9090
    ) else (
        echo ❌ 未找到 Node.js 或 Python
        pause
        exit /b
    )
) else (
    npx serve -p 9090 --cors
)

pause
