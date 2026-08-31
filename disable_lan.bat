@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title FinalGrid — Disable LAN access

REM ═══════════════════════════════════════════════════════════════════
REM  FinalGrid — Disable LAN Access
REM  ─────────────────────────────────────────────────────────────────
REM   1. Sets ALLOW_LAN=0 in .env.
REM   2. Removes the Windows Firewall rule.
REM   3. Prompts for restart.
REM  Idempotent. Run as admin for the firewall step.
REM ═══════════════════════════════════════════════════════════════════

echo.
echo  Disabling LAN access for FinalGrid...
echo.

if not exist ".env" (
    echo  ERROR: .env not found in current directory.
    pause & exit /b 1
)

REM ─── Flip ALLOW_LAN=0 ───────────────────────────────────────────
powershell -NoProfile -Command ^
    "$p='.env'; $c = Get-Content $p -Raw; if ($c -match '(?m)^ALLOW_LAN=.*$') { $c = [regex]::Replace($c, '(?m)^ALLOW_LAN=.*$', 'ALLOW_LAN=0') } else { $c = $c.TrimEnd() + [Environment]::NewLine + 'ALLOW_LAN=0' + [Environment]::NewLine }; [System.IO.File]::WriteAllText($p, $c, (New-Object Text.UTF8Encoding $false))"

if errorlevel 1 (
    echo  ERROR: Could not rewrite .env.
    pause & exit /b 1
)
echo  [OK] .env now has ALLOW_LAN=0

REM ─── Remove firewall rule (no-op if absent) ─────────────────────
netsh advfirewall firewall delete rule name="SukoonPMS" >nul 2>&1
echo  [OK] Firewall rule removed (if it existed).

echo.
echo  Restart the PMS server to return to 127.0.0.1-only binding:
echo    1. Double-click stop.bat
echo    2. Double-click start.bat
echo.
pause
exit /b 0
