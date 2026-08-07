@echo off
REM ============================================================
REM  Sukoon PMS — Full Startup Script
REM  Starts both the Flask app and the Cloudflare tunnel.
REM  Run this every morning when you start the PC.
REM ============================================================

set PMS_DIR=%~dp0..
set VENV=%PMS_DIR%\venv\Scripts

echo.
echo  ====================================
echo    Sukoon City View PMS — Startup
echo  ====================================
echo.

REM 1. Start Flask PMS in background
echo  [1/2] Starting PMS server...
start "Sukoon PMS Server" cmd /k "cd /d %PMS_DIR% && %VENV%\python.exe run.py"
timeout /t 5 /nobreak >nul

REM 2. Start Cloudflare Tunnel
echo  [2/2] Starting Cloudflare Tunnel...
start "Sukoon Cloudflare Tunnel" cmd /k "cloudflared tunnel --config "%~dp0config.yml" run"

echo.
echo  PMS is starting up...
echo  Open your browser and go to: http://localhost:5000
echo.
echo  Both windows must stay open while operating.
echo.
pause
