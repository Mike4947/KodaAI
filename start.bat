@echo off
cd /d "%~dp0"

if not exist ".env" (
    echo Creating .env from .env.example...
    copy .env.example .env
)

where python >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not on PATH.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo Installing dependencies...
    pip install -e .
    call npm install
    call npm install --prefix frontend
)

echo Starting KodaAI...

REM Free port 8000 if a previous backend instance is still running
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Stopping previous backend on port 8000 ^(PID %%a^)...
    taskkill /PID %%a /F >nul 2>&1
)

start http://localhost:5173
call npm run dev
