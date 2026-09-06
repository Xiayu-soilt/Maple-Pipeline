@echo off
title Sunflower Pipeline

echo ================================================
echo   Sunflower Pipeline - CI Quality Gate Platform
echo ================================================
echo.

set "ROOT=%~dp0"

echo [1/5] Checking Python ...
python --version
if errorlevel 1 (
    echo.
    echo [ERROR] Python not found in PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    echo IMPORTANT: tick "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo.
echo [2/5] Checking backend dependencies ...
cd /d "%ROOT%backend"
python -c "import fastapi, uvicorn, sqlalchemy, httpx, dotenv, pydantic_settings" >nul 2>&1
if errorlevel 1 (
    echo       Installing backend packages ^(first run only, using mirror^) ...
    python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 60 --retries 3
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install backend dependencies. Check your network.
        pause
        exit /b 1
    )
) else (
    echo       Backend dependencies already installed. Skip.
)

echo.
echo [3/5] Checking Node.js ...
node --version
if errorlevel 1 (
    echo.
    echo [ERROR] Node.js not found in PATH.
    echo Install Node.js 18+ from https://nodejs.org/
    pause
    exit /b 1
)

echo.
echo [4/5] Checking frontend dependencies ...
cd /d "%ROOT%frontend"
if not exist "node_modules" (
    echo       Installing frontend packages ^(first run only, may take minutes^) ...
    call npm install --no-audit --no-fund --registry=https://registry.npmmirror.com
)

echo.
echo [5/5] Starting servers ...
start "Sunflower Backend" cmd /k "cd /d %ROOT%backend && python -m uvicorn app.main:app --port 8800"
start "Sunflower Frontend" cmd /k "cd /d %ROOT%frontend && npm run dev"

echo       Waiting for servers to boot ...
ping -n 9 127.0.0.1 >nul
start "" "http://localhost:5273"

echo.
echo ================================================
echo   All started!
echo   Frontend : http://localhost:5273
echo   Backend  : http://127.0.0.1:8800   (docs: /docs)
echo.
echo   Two console windows are running the servers.
echo   Close both windows to stop the app.
echo ================================================
echo.
pause
