@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

set "BASE_URL=https://flask-appkhsx.onrender.com"
set "DATA_DIR=%~dp0"
set "COOKIE=%TEMP%\khsx_ck2.txt"

title [KHSX] Batching, Stock, Bag, Ton Bon
echo.
echo  ===========================================================
echo    UPDATE BATCHING, FFSTOCK, BAG REPORT, TON BON
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
echo  [1/6] Dang dang nhap...
curl -s -c "%COOKIE%" -X POST "%BASE_URL%/api/login" -H "Content-Type: application/json" -d "{\"username\":\"%USERNAME%\",\"password\":\"%PASSWORD%\"}" -o "%TEMP%\khsx_l2.json" 2>nul

if not exist "%TEMP%\khsx_l2.json" (
    echo  [LOI] Khong ket noi duoc den server!
    pause
    exit /b 1
)
findstr /C:"true" "%TEMP%\khsx_l2.json" >nul 2>&1
if errorlevel 1 (
    echo  [LOI] Dang nhap that bai!
    type "%TEMP%\khsx_l2.json"
    pause
    exit /b 1
)
echo  [OK] Dang nhap thanh cong!
echo.

REM === BATCHING ===
echo  ------------------------------------------------------------
echo  [2/6] BATCHING - Tim file PRODUCTION CSV...
echo  ------------------------------------------------------------
set "BF="
for %%f in ("%DATA_DIR%PRODUCTION*.csv") do set "BF=%%f"
if not defined BF (
    echo  [SKIP] Khong tim thay file PRODUCTION*.csv. Bo qua.
    goto :FFSTOCK
)
echo  File: !BF!
echo  Upload preview...
curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/batching/upload-preview" -F "file=@!BF!" -o "%TEMP%\khsx_bp.json" 2>nul
type "%TEMP%\khsx_bp.json"
echo.

for /f "tokens=2 delims=:," %%a in ('findstr /C:"tmp_path" "%TEMP%\khsx_bp.json"') do (
    set "TP=%%~a"
    set "TP=!TP: =!"
    set "TP=!TP:"=!"
)
if not defined TP (
    echo  [SKIP] Khong lay duoc tmp_path. Bo qua.
    goto :FFSTOCK
)
set /p "NGAY_SX=  Ngay san xuat (YYYY-MM-DD): "
echo  Import Batching...
curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/batching/import" -H "Content-Type: application/json" -d "{\"tmp_path\":\"!TP!\",\"file_type\":\"csv\",\"ngay_san_xuat\":\"!NGAY_SX!\",\"overwrite\":true}" -o "%TEMP%\khsx_br.json" 2>nul
echo  Ket qua:
type "%TEMP%\khsx_br.json"
echo.

REM === FFSTOCK ===
:FFSTOCK
echo.
echo  ------------------------------------------------------------
echo  [3/6] FFSTOCK - Tim file...
echo  ------------------------------------------------------------
set "SF="
for %%f in ("%DATA_DIR%FFSTOCK*.xls*") do set "SF=%%f"
if not defined SF (
    echo  [SKIP] Khong tim thay FFSTOCK. Bo qua.
    goto :BAG
)
echo  File: !SF!
curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/email/upload-import" -F "file=@!SF!" -F "file_type=FFSTOCK" -F "overwrite=true" -o "%TEMP%\khsx_sr.json" 2>nul
echo  Ket qua:
type "%TEMP%\khsx_sr.json"
echo.

REM === BAG REPORT ===
:BAG
echo.
echo  ------------------------------------------------------------
echo  [4/6] BAG REPORT - Tim file STOCK EMPTY BAG...
echo  ------------------------------------------------------------
set "BGF="
for %%f in ("%DATA_DIR%*STOCK EMPTY BAG*.xls*") do set "BGF=%%f"
if not defined BGF (
    echo  [SKIP] Khong tim thay file BAG. Bo qua.
    goto :TONBON
)
echo  File: !BGF!
curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/email/upload-import" -F "file=@!BGF!" -F "file_type=BAG_REPORT" -F "overwrite=true" -o "%TEMP%\khsx_bgr.json" 2>nul
echo  Ket qua:
type "%TEMP%\khsx_bgr.json"
echo.

REM === TON BON ===
:TONBON
echo.
echo  ------------------------------------------------------------
echo  [5/6] TON BON - Tim file Bao cao ton bon...
echo  ------------------------------------------------------------
set "TBF="
for %%f in ("%DATA_DIR%Bao cao ton bon*.xlsx") do set "TBF=%%f"
if not defined TBF (
    echo  [SKIP] Khong tim thay file Ton Bon. Bo qua.
    goto :DONE2
)
echo  File: !TBF!
curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/tonbon/upload-import" -F "file=@!TBF!" -F "mode=all" -F "loai_sp=Thanh pham" -F "overwrite=true" -o "%TEMP%\khsx_tbr.json" 2>nul
echo  Ket qua:
type "%TEMP%\khsx_tbr.json"
echo.

:DONE2
echo.
echo  ------------------------------------------------------------
echo  [6/6] Don dep...
echo  ------------------------------------------------------------
curl -s -b "%COOKIE%" -X POST "%BASE_URL%/api/logout" >nul 2>&1
del "%COOKIE%" >nul 2>&1

echo.
echo  ===========================================================
echo    HOAN TAT BATCHING, STOCK, BAG, TON BON
echo    Kiem tra: %BASE_URL%/dashboard
echo  ===========================================================
echo.
pause
