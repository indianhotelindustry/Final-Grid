@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Sukoon PMS (App Mode)

REM ═══════════════════════════════════════════════════════════════════
REM  Sukoon PMS — App Mode launcher
REM  ─────────────────────────────────────────────────────────────────
REM  Opens the PMS in a dedicated native window (via pywebview) if the
REM  package is installed, else falls back to the default browser.
REM
REM  Users never have to install pywebview themselves — this script is
REM  safe to click even on a stock install; it will transparently use
REM  the browser when pywebview isn't present.
REM
REM  Design choice: start from this bat rather than a .vbs because the
REM  pywebview window is foreground UI — hiding the console isn't useful
REM  when pywebview itself provides the visible shell.
REM ═══════════════════════════════════════════════════════════════════

if not exist "venv\Scripts\python.exe" (
    echo.
    echo  ERROR: venv not found. Run setup.bat (or reinstall) first.
    pause & exit /b 1
)
if not exist "desktop_window.py" (
    echo.
    echo  desktop_window.py not present — opening in browser instead.
    if exist "start_pms.bat" (
        call "start_pms.bat"
    ) else (
        start "" "http://localhost:5000"
    )
    exit /b 0
)

REM Let desktop_window.py decide whether to use pywebview or fall back.
venv\Scripts\python.exe desktop_window.py
exit /b %ERRORLEVEL%
