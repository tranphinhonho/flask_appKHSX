@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

REM ============================================================
REM  UPDATE SALE va PACKING - Gui du lieu len web
REM  Trang web: https://flask-appkhsx.onrender.com
REM ============================================================

set "BASE_URL=https://flask-appkhsx.onrender.com"
set "DATA_DIR=%~dp0"
set "COOKIE_FILE=%TEMP%\khsx_cookies.txt"

title [KHSX] Update Sale va Packing
echo.
echo  ===========================================================
echo     UPDATE SALE va PACKING LEN WEB KHSX
echo     %BASE_URL%
echo  ===========================================================
echo.

REM --- Doc thong tin dang nhap ---
if exist "%DATA_DIR%credentials.bat" (
    call "%DATA_DIR%credentials.bat"
    echo  User: %USERNAME%
) else (
    echo  Khong tim thay credentials.bat, nhap thu cong:
    set /p "USERNAME=  Username: "
    set /p "PASSWORD=  Password: "
)
echo.

REM --- Dang nhap ---
echo  [1/4] Dang dang nhap...
curl -s -c "%COOKIE_FILE%" -X POST "%BASE_URL%/api/login" ^
     -H "Content-Type: application/json" ^
     -d "{\"username\":\"%USERNAME%\",\"password\":\"%PASSWORD%\"}" ^
     -o "%TEMP%\khsx_login_result.json" 2>nul

if not exist "%TEMP%\khsx_login_result.json" (
    echo  [LOI] Khong ket noi duoc den server!
    echo  Kiem tra ket noi mang hoac URL.
    pause
    exit /b 1
)

findstr /C:"\"success\": true" "%TEMP%\khsx_login_result.json" >nul 2>&1
if errorlevel 1 (
    findstr /C:"\"success\":true" "%TEMP%\khsx_login_result.json" >nul 2>&1
    if errorlevel 1 (
        echo  [LOI] Dang nhap that bai! Kiem tra lai username/password.
        type "%TEMP%\khsx_login_result.json"
        echo.
        pause
        exit /b 1
    )
)
echo  [OK] Dang nhap thanh cong!
echo.

REM ============================================================
REM  SALE - Upload file DAILY SALED REPORT
REM ============================================================
echo  ------------------------------------------------------------
echo  [2/4] SALE - Tim file DAILY SALED REPORT...
echo  ------------------------------------------------------------

set "SALE_FILE="
for %%f in ("%DATA_DIR%DAILY SALED REPORT*.xls*") do (
    set "SALE_FILE=%%f"
)

if not defined SALE_FILE (
    echo  [SKIP] Khong tim thay file DAILY SALED REPORT trong thu muc!
    echo.
    goto :PACKING
)

echo  File: !SALE_FILE!
echo  Dang upload va import Sale (sheet "1"^)...

curl -s -b "%COOKIE_FILE%" -X POST "%BASE_URL%/api/sale/upload-import" ^
     -F "file=@!SALE_FILE!" ^
     -F "sheet=1" ^
     -o "%TEMP%\khsx_sale_result.json" 2>nul

echo  Ket qua Sale:
type "%TEMP%\khsx_sale_result.json"
echo.
echo.

REM Hoi import them sheet khac khong
set /p "MORE_SHEETS=  Ban co muon import them sheet khac? (y/n): "
if /i "!MORE_SHEETS!"=="y" (
    :SALE_LOOP
    set /p "SHEET_NUM=  Nhap ten/so sheet (hoac 'q' de dung): "
    if /i "!SHEET_NUM!"=="q" goto :PACKING

    echo  Dang import Sale sheet "!SHEET_NUM!"...
    curl -s -b "%COOKIE_FILE%" -X POST "%BASE_URL%/api/sale/upload-import" ^
         -F "file=@!SALE_FILE!" ^
         -F "sheet=!SHEET_NUM!" ^
         -o "%TEMP%\khsx_sale_result.json" 2>nul

    echo  Ket qua:
    type "%TEMP%\khsx_sale_result.json"
    echo.
    echo.
    goto :SALE_LOOP
)

REM ============================================================
REM  PACKING - Upload file DAILY PACKING
REM ============================================================
:PACKING
echo.
echo  ------------------------------------------------------------
echo  [3/4] PACKING - Tim file DAILY PACKING...
echo  ------------------------------------------------------------

set "PACKING_FILE="
for %%f in ("%DATA_DIR%DAILY PACKING*.xls*") do (
    set "PACKING_FILE=%%f"
)

if not defined PACKING_FILE (
    echo  [SKIP] Khong tim thay file DAILY PACKING trong thu muc!
    echo.
    goto :DONE
)

echo  File: !PACKING_FILE!
echo  Dang upload va import Packing (sheet "1"^)...

curl -s -b "%COOKIE_FILE%" -X POST "%BASE_URL%/api/packing/upload-import" ^
     -F "file=@!PACKING_FILE!" ^
     -F "sheet=1" ^
     -o "%TEMP%\khsx_packing_result.json" 2>nul

echo  Ket qua Packing:
type "%TEMP%\khsx_packing_result.json"
echo.
echo.

REM Hoi import them sheet khac khong
set /p "MORE_PK_SHEETS=  Ban co muon import them sheet khac? (y/n): "
if /i "!MORE_PK_SHEETS!"=="y" (
    :PACKING_LOOP
    set /p "PK_SHEET_NUM=  Nhap ten/so sheet (hoac 'q' de dung): "
    if /i "!PK_SHEET_NUM!"=="q" goto :DONE

    echo  Dang import Packing sheet "!PK_SHEET_NUM!"...
    curl -s -b "%COOKIE_FILE%" -X POST "%BASE_URL%/api/packing/upload-import" ^
         -F "file=@!PACKING_FILE!" ^
         -F "sheet=!PK_SHEET_NUM!" ^
         -o "%TEMP%\khsx_packing_result.json" 2>nul

    echo  Ket qua:
    type "%TEMP%\khsx_packing_result.json"
    echo.
    echo.
    goto :PACKING_LOOP
)

:DONE
echo.
echo  ------------------------------------------------------------
echo  [4/4] Don dep...
echo  ------------------------------------------------------------

REM --- Dang xuat ---
curl -s -b "%COOKIE_FILE%" -X POST "%BASE_URL%/api/logout" >nul 2>&1
del "%COOKIE_FILE%" >nul 2>&1
del "%TEMP%\khsx_login_result.json" >nul 2>&1
del "%TEMP%\khsx_sale_result.json" >nul 2>&1
del "%TEMP%\khsx_packing_result.json" >nul 2>&1

echo.
echo  ===========================================================
echo    HOAN TAT UPDATE SALE va PACKING!
echo    Kiem tra: %BASE_URL%/dashboard
echo  ===========================================================
echo.
pause
