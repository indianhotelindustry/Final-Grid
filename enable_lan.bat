@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Sukoon PMS — Enable LAN access

REM ═══════════════════════════════════════════════════════════════════
REM  Sukoon PMS — Enable LAN Access
REM  ─────────────────────────────────────────────────────────────────
REM  Opts this install in to LAN multi-user mode:
REM   1. Sets ALLOW_LAN=1 in .env (idempotent — toggles if already present).
REM   2. Adds a Windows Firewall rule on TCP PORT from .env.
REM   3. Prompts the operator to restart the server.
REM
REM  Safe to run on an already-enabled install (idempotent). Run as admin.
REM ═══════════════════════════════════════════════════════════════════

echo.
echo  Enabling LAN access for Sukoon PMS...
echo.

REM ─── Find PORT from .env, default 5000 ──────────────────────────
set APP_PORT=5000
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if /i "%%a"=="PORT" set APP_PORT=%%b
    )
) else (
    echo  ERROR: .env not found in current directory.
    echo  Run this from the Sukoon PMS install folder (same dir as start.bat).
    pause & exit /b 1
)

REM ─── Flip ALLOW_LAN=1 in .env ───────────────────────────────────
REM   Simple line rewrite: if an ALLOW_LAN= line exists, replace it.
REM   Otherwise append. We use PowerShell because batch string replace
REM   is unreliable with special characters.
powershell -NoProfile -Command ^
    "$p='.env'; $c = Get-Content $p -Raw; if ($c -match '(?m)^ALLOW_LAN=.*$') { $c = [regex]::Replace($c, '(?m)^ALLOW_LAN=.*$', 'ALLOW_LAN=1') } else { $c = $c.TrimEnd() + [Environment]::NewLine + 'ALLOW_LAN=1' + [Environment]::NewLine }; [System.IO.File]::WriteAllText($p, $c, (New-Object Text.UTF8Encoding $false))"

if errorlevel 1 (
    echo  ERROR: Could not rewrite .env — check permissions and retry.
    pause & exit /b 1
)
echo  [OK] .env now has ALLOW_LAN=1

REM ─── Open Windows Firewall port ─────────────────────────────────
REM   Requires admin — we ask netsh directly and let it fail loudly if not.
echo  Opening firewall port TCP %APP_PORT% (private + domain profiles)...
netsh advfirewall firewall delete rule name="SukoonPMS" >nul 2>&1
netsh advfirewall firewall add rule name="SukoonPMS" dir=in action=allow protocol=TCP localport=%APP_PORT% profile=private,domain
if errorlevel 1 (
    echo.
    echo  WARNING: Firewall rule could not be added.
    echo  Run this script as Administrator, OR add the rule manually:
    echo    netsh advfirewall firewall add rule name="SukoonPMS" ^
 dir=in action=allow protocol=TCP localport=%APP_PORT% profile=private,domain
    echo.
) else (
    echo  [OK] Firewall rule added for TCP %APP_PORT%.
)

REM ─── Print the IP addresses peers can connect to ────────────────
echo.
echo  LAN peers can reach this install via:
for /f "tokens=14" %%a in ('ipconfig ^| findstr /C:"IPv4"') do (
    echo    http://%%a:%APP_PORT%
)
echo.
echo  IMPORTANT: restart the PMS server for the new binding to take effect.
echo    1. Double-click stop.bat
echo    2. Double-click start.bat  (or log out and log back in)
echo.
pause
exit /b 0
