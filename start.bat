@echo off
title Flask App - KHSX

cd /d "%~dp0"

echo ============================================
echo   Dang khoi dong Flask App KHSX...
echo ============================================
echo.

set PYTHON_CMD=python
python --version >nul 2>&1
if errorlevel 1 (
    py --version >nul 2>&1
    if errorlevel 1 (
        echo [LOI] Khong tim thay Python hoac Py launcher!
        echo.
        pause
        exit /b 1
    ) else (
        set PYTHON_CMD=py
    )
)

set USE_VENV=1
if not exist "venv\Scripts\activate.bat" (
    echo [INFO] Dang tao virtual environment...
    %PYTHON_CMD% -m venv venv
    if errorlevel 1 (
        echo [WARN] Tao venv that bai. Se fallback chay global Python.
        set USE_VENV=0
    ) else (
        echo [OK] Tao venv thanh cong.
    )
)

if "%USE_VENV%"=="1" (
    echo [INFO] Kich hoat venv...
    call venv\Scripts\activate.bat
    echo [INFO] Cai dat dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [WARN] Cai dat dependencies trong venv that bai. Se fallback chay global Python.
        set USE_VENV=0
        rem deactivate if active
        call deactivate >nul 2>&1
    )
)

echo.
echo ============================================
echo   Flask App KHSX dang chay!
echo   Truy cap: http://localhost:5000
echo   Nhan Ctrl+C de dung server
echo ============================================
echo.

set DATABASE_URL=postgresql://neondb_owner:npg_MBpyCtcL27vm@ep-small-bar-a1bpplnk-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
set SUPABASE_URL=https://iynjxkqarvmdybnuenog.supabase.co
set SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml5bmp4a3FhcnZtZHlibnVlbm9nIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTAyNjA2MSwiZXhwIjoyMDk0NjAyMDYxfQ.oywemp6TzLgw7CRxqn4ByRNoDxT05vPhG1imFK30c0c

if "%USE_VENV%"=="1" (
    python app.py
) else (
    py app.py
)

echo.
echo [INFO] Server da dung.
pause
