@echo off
setlocal
cd /d "%~dp0"
title Sukoon PMS - Stopping Server

REM ─── Read port from .env ──────────────────────────────────────
set APP_PORT=5000
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if "%%a"=="PORT" set APP_PORT=%%b
    )
)

echo Stopping PMS server on port %APP_PORT%...

REM ─── Kill process(es) listening on the port ─────────────────
set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%APP_PORT% " ^| findstr "LISTENING"') do (
    echo  Stopping process PID %%a...
    taskkill /PID %%a /F >nul 2>&1
    set FOUND=1
)

REM ─── Defense in depth: kill any python(.exe|w.exe) running from this dir ──
REM Some setups (Task Scheduler, system tray) may respawn python; this catches
REM workers whose port socket was already torn down by the taskkill above, and
REM also catches stale processes that didn't bind any port.
set _PSCMD=$d=(Resolve-Path '%~dp0').Path.TrimEnd([char]92);Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='waitress-serve.exe'" ^| Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($d,'OrdinalIgnoreCase') } ^| ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }
powershell -NoProfile -Command "%_PSCMD%" >nul 2>&1

if %FOUND%==0 (
    echo  No server found on port %APP_PORT%.
) else (
    echo  Server stopped.
)

REM IMPORTANT: NO `pause` here. This script is invoked headlessly by the
REM Inno Setup patch installer (SW_HIDE + ewWaitUntilTerminated). A `pause`
REM would block the installer forever waiting for a keystroke that never
REM comes — and that is exactly what made v2.2.0 patches leave the old
REM server process running with stale Jinja templates in memory.
exit /b 0
