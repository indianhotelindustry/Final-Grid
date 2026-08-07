@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ═══════════════════════════════════════════════════════════════════
REM  Sukoon PMS — Start (installed version)
REM  Starts the server and opens the browser.
REM ═══════════════════════════════════════════════════════════════════

REM Read port from .env
set APP_PORT=5000
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if "%%a"=="PORT" set APP_PORT=%%b
    )
)

REM Check if already running
set _RUNNING=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%APP_PORT% " ^| findstr "LISTENING" 2^>nul') do set _RUNNING=1
if !_RUNNING!==1 (
    REM Already running — just open browser
    start "" "http://localhost:%APP_PORT%"
    exit /b 0
)

REM Start server in background (hidden)
if exist "start_hidden.vbs" (
    wscript.exe "start_hidden.vbs"
) else (
    start "" "start.bat"
)

REM Wait for server to be ready
echo Starting Sukoon PMS...
for /L %%i in (1,1,10) do (
    timeout /t 1 /nobreak >nul
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%APP_PORT% " ^| findstr "LISTENING" 2^>nul') do (
        start "" "http://localhost:%APP_PORT%"
        exit /b 0
    )
)

REM Fallback: open anyway
start "" "http://localhost:%APP_PORT%"
exit /b 0
