@echo off
setlocal enabledelayedexpansion
title FinalGrid — Factory Reset
color 0C
cd /d "%~dp0"

echo.
echo  ============================================================
echo   FinalGrid — Factory Reset
echo  ============================================================
echo.
echo   This will PERMANENTLY DELETE all operational data:
echo.
echo     - All reservations, check-ins, checkouts
echo     - All guest records and ID documents
echo     - All payments, invoices, folios
echo     - All night audit history
echo     - All shifts and cash reconciliation
echo     - All notification and webhook logs
echo.
echo   The following will be PRESERVED:
echo.
echo     - Room inventory (60 rooms)
echo     - Room types, rate plans, POS catalog
echo     - Staff user accounts
echo     - Hotel settings and configuration
echo     - App code and version
echo.

REM ─── Confirmation gate ─────────────────────────────────────────
echo  Type RESET to confirm, or press Enter to cancel:
echo.
set /p CONFIRM="  > "
if /i not "!CONFIRM!"=="RESET" (
    color 0A
    echo.
    echo  Cancelled. No changes were made.
    echo.
    pause & exit /b 0
)

echo.
echo  ────────────────────────────────────────────────────────────

REM ─── 0. Pre-flight ─────────────────────────────────────────────
if not exist "venv\Scripts\python.exe" (
    echo  ERROR: venv not found. Run setup.bat first.
    pause & exit /b 1
)

REM ─── 1. Stop the server if running ─────────────────────────────
echo.
echo  [1/5] Stopping server...
set APP_PORT=5000
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if "%%a"=="PORT" set APP_PORT=%%b
    )
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":!APP_PORT! " ^| findstr "LISTENING" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)
echo       Done.

REM ─── 2. Backup existing database ──────────────────────────────
echo.
echo  [2/5] Backing up current database...
if not exist "backups" mkdir backups

if exist "instance\pms.db" (
    set TS=!date:~-4!!date:~4,2!!date:~7,2!_!time:~0,2!!time:~3,2!!time:~6,2!
    set TS=!TS: =0!
    set BACKUP_NAME=backup_pre_reset_!TS!.db
    copy /y "instance\pms.db" "backups\!BACKUP_NAME!" >nul
    echo       Saved: backups\!BACKUP_NAME!
) else (
    echo       No existing database found — skipping backup.
)

REM ─── 3. Delete database ────────────────────────────────────────
echo.
echo  [3/5] Deleting database...
if exist "instance\pms.db" (
    del /f /q "instance\pms.db"
    echo       instance\pms.db deleted.
) else (
    echo       Already clean.
)
if exist "instance\pms.db-wal" del /f /q "instance\pms.db-wal"
if exist "instance\pms.db-shm" del /f /q "instance\pms.db-shm"

REM ─── 4. Optionally clear uploads ──────────────────────────────
echo.
echo  Clear guest photos and ID document scans?
echo  (These are tied to the old hotel's guests.)
echo.
set /p CLEAR_UPLOADS="  Clear uploads? (Y/N) [Y]: "
if "!CLEAR_UPLOADS!"=="" set CLEAR_UPLOADS=Y

if /i "!CLEAR_UPLOADS!"=="Y" (
    echo.
    echo  [4/5] Clearing uploads...
    if exist "app\static\uploads" (
        rd /s /q "app\static\uploads"
        mkdir "app\static\uploads"
        echo       app\static\uploads\ cleared.
    )
    if exist "app\private_uploads" (
        rd /s /q "app\private_uploads"
        mkdir "app\private_uploads"
        echo       app\private_uploads\ cleared.
    )
) else (
    echo.
    echo  [4/5] Keeping uploads (user chose to skip^).
)

REM ─── 5. Recreate fresh database ───────────────────────────────
echo.
echo  [5/5] Creating fresh database with seed data...
venv\Scripts\python.exe -c "
import os
os.environ.setdefault('FLASK_ENV', 'production')
from app import create_app
app = create_app()
print('       Fresh database created.')
" 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Database creation failed. Check the error above.
    echo  Your old database backup is in the backups\ folder.
    pause & exit /b 1
)

REM ─── Log the reset ─────────────────────────────────────────────
if not exist "logs" mkdir logs
echo [%date% %time%] FACTORY RESET performed. Uploads cleared: !CLEAR_UPLOADS! >> logs\reset.log

REM ─── Done ──────────────────────────────────────────────────────
echo.
color 0A
echo  ============================================================
echo   Factory Reset Complete
echo  ============================================================
echo.
echo   The PMS is ready for a new hotel.
echo.
echo   Next steps:
echo     1. Double-click start.bat to start the server
echo     2. Log in with:  admin / (password shown in console)
echo     3. Go to Masters and update:
echo        - Hotel name, address, GSTIN
echo        - Room types and rates
echo        - Staff accounts
echo.
echo   Old database backup: backups\!BACKUP_NAME!
echo  ============================================================
echo.
pause
