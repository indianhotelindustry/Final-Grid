@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ─── Pre-flight checks ────────────────────────────────────────
if not exist ".env" (
    echo  ERROR: .env not found. Run setup.bat first.
    pause & exit /b 1
)
if not exist "venv\Scripts\python.exe" (
    echo  ERROR: venv not found. Run setup.bat first.
    pause & exit /b 1
)
venv\Scripts\python.exe -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: venv is broken — Python executable does not work.
    echo.
    echo  This usually means the venv was copied from a different PC
    echo  or the original Python installation was moved or uninstalled.
    echo.
    echo  Fix: delete the venv folder and run setup.bat again:
    echo    1. Delete the "venv" folder in this directory
    echo    2. Double-click setup.bat
    echo.
    pause & exit /b 1
)

REM ─── Read hotel name, port + LAN toggle from .env ──────────────
set HOTEL_NAME=Hotel PMS
set APP_PORT=5000
set ALLOW_LAN=0
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if /i "%%a"=="HOTEL_NAME" set HOTEL_NAME=%%b
    if /i "%%a"=="PORT"       set APP_PORT=%%b
    if /i "%%a"=="ALLOW_LAN"  set ALLOW_LAN=%%b
)

REM ── Resolve bind host from ALLOW_LAN ─────────────────────────────
REM   Default (ALLOW_LAN=0): bind to 127.0.0.1 — single-machine install.
REM   Opt-in (ALLOW_LAN=1) : bind to 0.0.0.0 — reachable from LAN peers.
REM   Accepted truthy values: 1 / true / yes (case-insensitive).
set BIND_HOST=127.0.0.1
if /i "!ALLOW_LAN!"=="1"    set BIND_HOST=0.0.0.0
if /i "!ALLOW_LAN!"=="true" set BIND_HOST=0.0.0.0
if /i "!ALLOW_LAN!"=="yes"  set BIND_HOST=0.0.0.0

title FinalGrid — %HOTEL_NAME%
color 0A

REM ─── Ensure writable folders exist ─────────────────────────────
if not exist "instance"             mkdir instance
if not exist "logs"                 mkdir logs
if not exist "backups"              mkdir backups
if not exist "app\static\uploads"   mkdir app\static\uploads
if not exist "app\private_uploads"  mkdir app\private_uploads

REM ─── Read version + latest migration for startup log ──────────
set APP_VER=unknown
if exist "version.txt" set /p APP_VER=<version.txt
set MIG_VER=unknown
if exist "_startup_info.py" (
    for /f "usebackq delims=" %%v in (`venv\Scripts\python.exe _startup_info.py 2^>nul`) do set MIG_VER=%%v
)

REM ─── Log this start event ────────────────────────────────────
echo [%date% %time%] PMS starting ^| version=v!APP_VER! ^| latest_migration=!MIG_VER! ^| port=%APP_PORT% >> logs\start.log

REM ═══════════════════════════════════════════════════════════════
REM  GHOST PROCESS GUARD — kill any stale PMS before launching
REM ═══════════════════════════════════════════════════════════════
call :kill_stale_pms
if errorlevel 1 (
    color 0C
    echo.
    echo  ERROR: Could not free port %APP_PORT% — another process is holding it.
    echo  Check logs\start.log for details.
    echo.
    echo  Try: close any other PMS windows, then run this again.
    echo.
    pause & exit /b 1
)

echo.
echo  ================================================================
echo   FinalGrid  ^|  %HOTEL_NAME%
echo  ================================================================
echo   Version  : v!APP_VER!   (DB migration: !MIG_VER!)
echo   Local    : http://localhost:%APP_PORT%
if /i "!ALLOW_LAN!"=="1" (
    echo   LAN      : http://^<this-machine-ip^>:%APP_PORT%   (opt-in enabled)
)
echo   Stop     : Close this window  (or Ctrl+C)
echo  ================================================================
echo.

REM ─── Open browser (only if running interactively, not hidden) ──
if "%1"=="" start "" "http://localhost:%APP_PORT%"

REM ─── Server loop with auto-restart ─────────────────────────────
:loop
if exist ".restart_flag" del ".restart_flag"

REM Kill any stale process on the port before each restart
call :kill_stale_pms
if errorlevel 1 (
    echo.
    echo  [%date% %time%] Could not free port %APP_PORT% — aborting restart.
    echo  [%date% %time%] ABORT: port %APP_PORT% still held after retry >> logs\start.log
    pause & exit /b 1
)

echo  [%date% %time%] Starting server on %BIND_HOST%:%APP_PORT% (ALLOW_LAN=%ALLOW_LAN%)...
venv\Scripts\python.exe -m waitress --host=%BIND_HOST% --port=%APP_PORT% --threads=4 wsgi:app
set _ERR=%ERRORLEVEL%

if exist ".restart_flag" (
    echo.
    echo  [%date% %time%] Restart requested via update — restarting...
    echo  [%date% %time%] Restart flag detected — restarting >> logs\start.log
    del ".restart_flag"
    timeout /t 1 /nobreak >nul
    echo.
    goto loop
)

if %_ERR% NEQ 0 (
    echo.
    echo  [%date% %time%] Server stopped unexpectedly (exit code %_ERR%).
    echo  [%date% %time%] Server crashed exit_code=%_ERR% — auto-restart in 5s >> logs\start.log
    echo  Auto-restarting in 5 seconds... (Ctrl+C to cancel)
    timeout /t 5 /nobreak >nul
    echo.
    goto loop
)

echo.
echo  Server stopped normally.
echo  [%date% %time%] Server stopped normally >> logs\start.log
pause
exit /b 0


REM ═══════════════════════════════════════════════════════════════
REM  Helper: kill_stale_pms
REM  Kills any process listening on APP_PORT.  v2.2.17: retries up to
REM  five times with a wider delay so a waitress socket still in
REM  TIME_WAIT after a patch restart has time to release.
REM  Logs every killed PID to logs\start.log.
REM  Also scans for duplicate python processes running wsgi:app.
REM ═══════════════════════════════════════════════════════════════
:kill_stale_pms
set _RETRY=0
:kill_retry
set _FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%APP_PORT% " ^| findstr "LISTENING" 2^>nul') do (
    set _FOUND=1
    echo  [%date% %time%] Killing stale PID %%a on port %APP_PORT%
    echo [%date% %time%] GHOST_KILL: pid=%%a port=%APP_PORT% version=v!APP_VER! retry=!_RETRY! >> logs\start.log
    taskkill /PID %%a /F >nul 2>&1
)
if !_FOUND!==1 (
    timeout /t 3 /nobreak >nul
    REM Re-check — port should now be free
    set _STILL=0
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%APP_PORT% " ^| findstr "LISTENING" 2^>nul') do set _STILL=1
    if !_STILL!==1 (
        set /a _RETRY+=1
        if !_RETRY! LSS 5 (
            echo  [%date% %time%] Port still held, retry !_RETRY!/5...
            echo [%date% %time%] GHOST_KILL_RETRY: port %APP_PORT% still held, retry !_RETRY!/5 >> logs\start.log
            timeout /t 3 /nobreak >nul
            goto kill_retry
        )
        echo [%date% %time%] GHOST_KILL_FAILED: port %APP_PORT% still held after 5 retries >> logs\start.log
        exit /b 1
    )
)

REM ─── Duplicate-process scan: find any other python.exe running this app ──
REM Uses PowerShell because wmic is deprecated/removed on newer Windows.
REM Matches on wsgi:app in commandline — avoids killing unrelated python processes.
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*wsgi:app*' } | Select-Object -ExpandProperty ProcessId" 2^>nul`) do (
    set _DUP_PID=%%p
    if not "!_DUP_PID!"=="" (
        echo  [%date% %time%] Killing duplicate PMS python.exe PID !_DUP_PID!
        echo [%date% %time%] DUP_KILL: duplicate pms process pid=!_DUP_PID! >> logs\start.log
        taskkill /PID !_DUP_PID! /F >nul 2>&1
    )
)

exit /b 0
