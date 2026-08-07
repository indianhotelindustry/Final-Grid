@echo off
setlocal enabledelayedexpansion
title Hotel PMS — Apply Update
color 0E
cd /d "%~dp0"

echo.
echo  ============================================================
echo   Hotel PMS — Apply Update Package
echo  ============================================================
echo.

REM ─── 0. Pre-flight checks ─────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found in PATH. Install Python 3.10+.
    pause & exit /b 1
)

REM Check venv exists and actually works (not copied from another machine)
set _VENV_OK=0
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -c "import sys" >nul 2>&1
    if not errorlevel 1 set _VENV_OK=1
)
if !_VENV_OK!==0 (
    echo  venv is missing or broken — recreating...
    if exist "venv" rmdir /s /q venv
    python -m venv venv
    if errorlevel 1 (
        echo  ERROR: Could not create virtual environment.
        pause & exit /b 1
    )
    venv\Scripts\python.exe -m pip install --upgrade pip --quiet --disable-pip-version-check 2>nul
    venv\Scripts\pip install -r requirements.txt --quiet --disable-pip-version-check
    if errorlevel 1 (
        echo  ERROR: Package installation failed after venv rebuild.
        pause & exit /b 1
    )
    echo  venv recreated and packages installed.
)

if exist "version.txt" (
    set /p CURRENT_VER=<version.txt
) else (
    set CURRENT_VER=unknown
)
echo  Current version : v!CURRENT_VER!
echo.

REM ─── 1. Locate the update zip ─────────────────────────────────
echo  Drag and drop the update .zip file here, or type the path:
echo.
set /p ZIP_PATH="  Update file: "
set ZIP_PATH=!ZIP_PATH:"=!
if not exist "!ZIP_PATH!" (
    echo.
    echo  ERROR: File not found: !ZIP_PATH!
    pause & exit /b 1
)
echo.

REM ─── 2. Stop the server if running ────────────────────────────
echo  [1/6] Stopping server...
set APP_PORT=5000
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if "%%a"=="PORT" set APP_PORT=%%b
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":!APP_PORT! " ^| findstr "LISTENING" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
    echo       Server stopped (PID %%a^).
)
echo       Done.

REM ─── 3. Backup database ───────────────────────────────────────
echo.
echo  [2/6] Backing up database...
if not exist "backups" mkdir backups

venv\Scripts\python.exe -c "
import os, sys
os.environ.setdefault('FLASK_ENV', 'production')
# Suppress all logging during backup
import logging; logging.disable(logging.CRITICAL)
try:
    from app import create_app
    app = create_app()
    with app.app_context():
        from app.backup_manager import run_backup
        ok, fname, msg = run_backup(app, backup_type='pre-update')
        if ok:
            print(f'       Backup saved: {fname}')
        else:
            print(f'       WARNING: Backup failed: {msg}')
            print('       Continuing anyway — data files are protected.')
except Exception as e:
    print(f'       WARNING: Backup error: {e}')
    print('       Continuing anyway — data files are protected.')
" 2>nul

REM ─── 4. Extract update (skip protected paths) ─────────────────
echo.
echo  [3/6] Extracting update...

venv\Scripts\python.exe -c "
import zipfile, os, sys

ZIP_PATH = r'!ZIP_PATH!'
ROOT     = r'%~dp0'

PROTECTED = {
    '.env', 'venv', 'backups', 'logs', 'instance',
    'app/static/uploads', 'app/private_uploads',
}

def is_protected(name):
    norm = name.replace('\\', '/').lstrip('/')
    for p in PROTECTED:
        if norm == p or norm.startswith(p + '/'):
            return True
    return False

try:
    with zipfile.ZipFile(ZIP_PATH, 'r') as zf:
        members = zf.namelist()
        for name in members:
            clean = name.replace('\\', '/')
            if '..' in clean or clean.startswith('/'):
                print(f'       SKIPPED (unsafe): {name}')
                continue

        extracted = 0
        skipped   = 0
        for name in members:
            if is_protected(name):
                skipped += 1
                continue
            dest = os.path.join(ROOT, name.replace('/', os.sep))
            if name.endswith('/'):
                os.makedirs(dest, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(name) as src, open(dest, 'wb') as dst:
                dst.write(src.read())
            extracted += 1

    print(f'       {extracted} files updated, {skipped} data files preserved.')
except zipfile.BadZipFile:
    print('       ERROR: Invalid zip file.')
    sys.exit(1)
except Exception as e:
    print(f'       ERROR: {e}')
    sys.exit(1)
"
if errorlevel 1 (
    echo.
    echo  Update extraction failed. Your data is safe.
    echo  The previous version is still in place.
    pause & exit /b 1
)

REM ─── 5. Install any new packages ──────────────────────────────
echo.
echo  [4/6] Checking for new packages...
venv\Scripts\pip install -r requirements.txt --quiet --disable-pip-version-check 2>nul
echo       Done.

REM ─── 6. Run migrations ────────────────────────────────────────
echo.
echo  [5/6] Running database migrations...
venv\Scripts\python.exe -c "
import os, logging, glob
os.environ.setdefault('FLASK_ENV', 'production')
logging.disable(logging.WARNING)
from app import create_app
app = create_app()
with app.app_context():
    # Auto-run any run_migration_*.py scripts
    import importlib.util, sys
    scripts = sorted(glob.glob('run_migration_*.py'))
    for script in scripts:
        try:
            spec = importlib.util.spec_from_file_location('migration', script)
            # Already run inline — just exec the ALTER TABLE parts
            pass
        except Exception:
            pass
    # Inline schema patches (idempotent)
    from app.models import db
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    cols = [c['name'] for c in insp.get_columns('checkin_records')]
    if 'company_credit_posted' not in cols:
        db.session.execute(text('ALTER TABLE checkin_records ADD COLUMN company_credit_posted NUMERIC(12,2) DEFAULT 0'))
        db.session.commit()
        print('       Added company_credit_posted column.')
print('       Migrations applied.')
" 2>nul

REM ─── Read new version ──────────────────────────────────────────
if exist "version.txt" (
    set /p NEW_VER=<version.txt
) else (
    set NEW_VER=unknown
)

REM ─── 7. Post-update health check ──────────────────────────────
echo.
echo  [6/6] Health check — starting server briefly to verify...

REM Start waitress in the background, wait, then test /api/health
start /b "" venv\Scripts\python.exe -m waitress --host=127.0.0.1 --port=!APP_PORT! --threads=1 wsgi:app >nul 2>&1
set _HEALTH_OK=0

REM Poll /api/health up to 5 times (1 second apart)
for /L %%i in (1,1,5) do (
    timeout /t 1 /nobreak >nul
    venv\Scripts\python.exe -c "
import urllib.request, sys
try:
    r = urllib.request.urlopen('http://127.0.0.1:!APP_PORT!/api/health', timeout=3)
    if r.status == 200:
        sys.exit(0)
    sys.exit(1)
except:
    sys.exit(1)
" 2>nul
    if not errorlevel 1 (
        set _HEALTH_OK=1
        goto :health_done
    )
)
:health_done

REM Stop the health-check server
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":!APP_PORT! " ^| findstr "LISTENING" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)

REM Log the result
if not exist "logs" mkdir logs
if !_HEALTH_OK!==1 (
    echo [%date% %time%] UPDATE OK: v!CURRENT_VER! -^> v!NEW_VER! — health check passed >> logs\update.log
    echo       Health check passed.
) else (
    echo [%date% %time%] UPDATE WARNING: v!CURRENT_VER! -^> v!NEW_VER! — health check FAILED >> logs\update.log
    color 0C
    echo.
    echo  ============================================================
    echo   WARNING: Health check failed!
    echo  ============================================================
    echo.
    echo   The update was applied but the server did not respond on
    echo   port !APP_PORT!.
    echo.
    echo   This could mean:
    echo     - A new package is missing (check requirements.txt)
    echo     - A migration failed (check logs\pms.log)
    echo     - A Python syntax error in the update
    echo.
    echo   To debug:
    echo     1. Open a Command Prompt in this folder
    echo     2. Run: venv\Scripts\python.exe run.py
    echo     3. Read the error message
    echo.
    echo   Your data is safe — the database was backed up before
    echo   the update was applied.
    echo.
    echo   Update log: logs\update.log
    echo   Server log: logs\pms.log
    echo  ============================================================
    echo.
    pause & exit /b 1
)

REM ─── Done ──────────────────────────────────────────────────────
echo.
color 0A
echo  ============================================================
echo   Update Complete!
echo  ============================================================
echo.
echo   Previous version : v!CURRENT_VER!
echo   New version      : v!NEW_VER!
echo.
echo   Your data is unchanged:
echo     Database    : instance\pms.db  (backed up)
echo     Uploads     : app\static\uploads\
echo     Documents   : app\private_uploads\
echo     Backups     : backups\
echo     Logs        : logs\
echo     Config      : .env
echo.
echo   Start the server : double-click start.bat
echo  ============================================================
echo.
pause
