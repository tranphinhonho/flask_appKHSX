@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

set "BASE_URL=https://flask-appkhsx.onrender.com"
set "DATA_DIR=%~dp0"
set "COOKIE=%TEMP%\khsx_ck3.txt"

title [KHSX] Silo, Ba Cang, Forecast
echo.
echo  ===========================================================
echo    UPDATE SILO, BA CANG, FORECAST
echo    %BASE_URL%
echo  ===========================================================
echo.

if exist "%DATA_DIR%credentials.bat" (
    call "%DATA_DIR%credentials.bat"
    echo  User: %USERNAME%
) else (
    echo  Khong tim thay credentials.bat, nhap thu cong:
    set /p "USERNAME=  Username: "
    set /p "PASSWORD=  Password: "
)
echo.
echo  [1/5] Dang dang nhap...
curl -s -c "%COOKIE%" -X POST "%BASE_URL%/api/login" -H "Content-Type: application/json" -d "{\"username\":\"%USERNAME%\",\"password\":\"%PASSWORD%\"}" -o "%TEMP%\khsx_l3.json" 2>nul

if not exist "%TEMP%\khsx_l3.json" (
    echo  [LOI] Khong ket noi duoc den server!
    pause
    exit /b 1
)
findstr /C:"true" "%TEMP%\khsx_l3.json" >nul 2>&1
if errorlevel 1 (
    echo  [LOI] Dang nhap that bai!
    type "%TEMP%\khsx_l3.json"
    pause
    exit /b 1
)
echo  [OK] Dang nhap thanh cong!
echo.

REM === SILO ===
echo  ------------------------------------------------------------
echo  [2/5] SILO - Tim file SILO...
echo  ------------------------------------------------------------
set "SILO_FILE="
for %%f in ("%DATA_DIR%SILO*.xlsx") do set "SILO_FILE=%%f"
if not defined SILO_FILE (
    echo  [SKIP] Khong tim thay file SILO. Bo qua.
    goto :BACANG
)
echo  File: !SILO_FILE!
echo  Upload...
curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/silo/upload" -F "file=@!SILO_FILE!" -o "%TEMP%\khsx_silo_up.json" 2>nul
echo  Upload result:
type "%TEMP%\khsx_silo_up.json"
echo.

for /f "tokens=2 delims=:," %%a in ('findstr /C:"file_path" "%TEMP%\khsx_silo_up.json"') do (
    set "SILO_PATH=%%~a"
    set "SILO_PATH=!SILO_PATH: =!"
    set "SILO_PATH=!SILO_PATH:"=!"
)

if not defined SILO_PATH (
    echo  [SKIP] Khong lay duoc file_path. Bo qua Silo import.
    goto :BACANG
)

echo.
echo  Danh sach sheets co trong file. Hay chon sheet de import.
set /p "SILO_SHEET=  Nhap ten sheet Silo: "
echo  Import Silo sheet "!SILO_SHEET!"...
curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/silo/import" -H "Content-Type: application/json" -d "{\"file_path\":\"!SILO_PATH!\",\"sheet_name\":\"!SILO_SHEET!\"}" -o "%TEMP%\khsx_silo_r.json" 2>nul
echo  Ket qua:
type "%TEMP%\khsx_silo_r.json"
echo.

REM === BA CANG ===
:BACANG
echo.
echo  ------------------------------------------------------------
echo  [3/5] BA CANG - Tim file KE HOACH CAM...
echo  ------------------------------------------------------------
set "BC_FILE="
for %%f in ("%DATA_DIR%*BA CANG*.xlsx" "%DATA_DIR%*B*CANG*.xlsx") do (
    if exist "%%f" set "BC_FILE=%%f"
)
if not defined BC_FILE (
    for %%f in ("%DATA_DIR%*CAM TUAN*.xlsx") do set "BC_FILE=%%f"
)
if not defined BC_FILE (
    echo  [SKIP] Khong tim thay file Ba Cang. Bo qua.
    goto :FORECAST
)
echo  File: !BC_FILE!
echo  Upload...
curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/bacang/upload" -F "file=@!BC_FILE!" -o "%TEMP%\khsx_bc_up.json" 2>nul
echo  Upload result:
type "%TEMP%\khsx_bc_up.json"
echo.

for /f "tokens=2 delims=:," %%a in ('findstr /C:"file_path" "%TEMP%\khsx_bc_up.json"') do (
    set "BC_PATH=%%~a"
    set "BC_PATH=!BC_PATH: =!"
    set "BC_PATH=!BC_PATH:"=!"
)

if not defined BC_PATH (
    echo  [SKIP] Khong lay duoc file_path. Bo qua Ba Cang import.
    goto :FORECAST
)

echo.
set /p "BC_SHEET=  Nhap ten sheet Ba Cang: "
echo  Import Ba Cang sheet "!BC_SHEET!"...
curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/bacang/import" -H "Content-Type: application/json" -d "{\"file_path\":\"!BC_PATH!\",\"sheet_name\":\"!BC_SHEET!\"}" -o "%TEMP%\khsx_bc_r.json" 2>nul
echo  Ket qua:
type "%TEMP%\khsx_bc_r.json"
echo.

REM === FORECAST ===
:FORECAST
echo.
echo  ------------------------------------------------------------
echo  [4/5] FORECAST - Tim file SALEFORECAST...
echo  ------------------------------------------------------------
set "FC_FILE="
for %%f in ("%DATA_DIR%*SALEFORECAST*.xlsx" "%DATA_DIR%*FORECAST*.xlsx") do (
    if exist "%%f" set "FC_FILE=%%f"
)
if not defined FC_FILE (
    echo  [SKIP] Khong tim thay file Forecast. Bo qua.
    goto :DONE3
)
echo  File: !FC_FILE!
echo  Upload...
curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/forecast/upload" -F "file=@!FC_FILE!" -o "%TEMP%\khsx_fc_up.json" 2>nul
echo  Upload result:
type "%TEMP%\khsx_fc_up.json"
echo.

for /f "tokens=2 delims=:," %%a in ('findstr /C:"file_path" "%TEMP%\khsx_fc_up.json"') do (
    set "FC_PATH=%%~a"
    set "FC_PATH=!FC_PATH: =!"
    set "FC_PATH=!FC_PATH:"=!"
)

if not defined FC_PATH (
    echo  [SKIP] Khong lay duoc file_path. Bo qua Forecast import.
    goto :DONE3
)

echo.
set /p "FC_SHEET=  Nhap ten sheet Forecast: "

echo  Chon kieu import:
echo    1. Import vao bang Forecast
echo    2. Import vao DatHang (tru da co tu Ba Cang/Silo)
set /p "FC_MODE=  Chon (1 hoac 2): "

if "!FC_MODE!"=="2" (
    echo  Import Forecast vao DatHang...
    curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/forecast/import-to-dathang" -H "Content-Type: application/json" -d "{\"file_path\":\"!FC_PATH!\",\"sheet_name\":\"!FC_SHEET!\"}" -o "%TEMP%\khsx_fc_r.json" 2>nul
) else (
    echo  Import Forecast vao bang Forecast...
    curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/forecast/import" -H "Content-Type: application/json" -d "{\"file_path\":\"!FC_PATH!\",\"sheet_name\":\"!FC_SHEET!\"}" -o "%TEMP%\khsx_fc_r.json" 2>nul
)
echo  Ket qua:
type "%TEMP%\khsx_fc_r.json"
echo.

:DONE3
echo.
echo  ------------------------------------------------------------
echo  [5/5] Don dep...
echo  ------------------------------------------------------------
curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/logout" >nul 2>&1
del "%COOKIE%" >nul 2>&1

echo.
echo  ===========================================================
echo    HOAN TAT SILO, BA CANG, FORECAST
echo    Kiem tra: %BASE_URL%/dashboard
echo  ===========================================================
echo.
pause
