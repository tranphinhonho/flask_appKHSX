@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

set "BASE_URL=https://flask-appkhsx.onrender.com"
set "DATA_DIR=%~dp0"
set "COOKIE_FILE=%TEMP%\khsx_cookies_sale5.txt"
set "SALE_FILE=%DATA_DIR%DAILY SALED REPORT THANG 5.2026.xlsm"
set "PY_PARSE=%DATA_DIR%parse_sale_result.py"
set "NOT_FOUND_LOG=%TEMP%\khsx_not_found_s5.txt"

title [KHSX] Upload Sale Thang 5 2026 Ngay 1-17

echo. > "%NOT_FOUND_LOG%"

echo.
echo  ===========================================================
echo     UPLOAD SALE THANG 5/2026 NGAY 1 den 17
echo     File: DAILY SALED REPORT THANG 5.2026.xlsm
echo     Server: %BASE_URL%
echo  ===========================================================
echo.

if not exist "%SALE_FILE%" (
    echo  [LOI] Khong tim thay file: %SALE_FILE%
    pause & exit /b 1
)
echo  [OK] Da tim thay file Excel.
echo.

if exist "%DATA_DIR%credentials.bat" (
    call "%DATA_DIR%credentials.bat"
    echo  User: %USERNAME%
) else (
    set /p "USERNAME=  Username: "
    set /p "PASSWORD=  Password: "
)
echo.

echo  [STEP 1] Dang dang nhap...
curl -s -c "%COOKIE_FILE%" -X POST "%BASE_URL%/api/login" ^
     -H "Content-Type: application/json" ^
     -d "{\"username\":\"%USERNAME%\",\"password\":\"%PASSWORD%\"}" ^
     -o "%TEMP%\khsx_login_s5.json" 2>nul

findstr /C:"true" "%TEMP%\khsx_login_s5.json" >nul 2>&1
if errorlevel 1 (
    echo  [LOI] Dang nhap that bai!
    type "%TEMP%\khsx_login_s5.json"
    pause & exit /b 1
)
echo  [OK] Dang nhap thanh cong!
echo.

echo  [STEP 2] Upload du lieu tung ngay tu 1 den 17...
echo  ------------------------------------------------------------

set "SUCCESS_COUNT=0"
set "FAIL_COUNT=0"
set "FAIL_DAYS="
set "SUCCESS_DAYS="

call :UPLOAD_DAY 1
call :UPLOAD_DAY 2
call :UPLOAD_DAY 3
call :UPLOAD_DAY 4
call :UPLOAD_DAY 5
call :UPLOAD_DAY 6
call :UPLOAD_DAY 7
call :UPLOAD_DAY 8
call :UPLOAD_DAY 9
call :UPLOAD_DAY 10
call :UPLOAD_DAY 11
call :UPLOAD_DAY 12
call :UPLOAD_DAY 13
call :UPLOAD_DAY 14
call :UPLOAD_DAY 15
call :UPLOAD_DAY 16
call :UPLOAD_DAY 17

goto :DONE

:UPLOAD_DAY
set "DAY=%~1"
set "SHEET_NAME=%DAY%.5.2026"
set "RES_FILE=%TEMP%\khsx_day%DAY%.json"
echo.
echo  --- Ngay %DAY%/5/2026 ^(Sheet: %SHEET_NAME%^) ---

curl -s -b "%COOKIE_FILE%" ^
     -X POST "%BASE_URL%/api/sale/upload-import" ^
     -F "file=@%SALE_FILE%" ^
     -F "sheet=%SHEET_NAME%" ^
     -o "%RES_FILE%" 2>nul

if exist "%RES_FILE%" (
    python "%PY_PARSE%" "%RES_FILE%" "%DAY%" "%NOT_FOUND_LOG%"
    if errorlevel 1 (
        set /a "FAIL_COUNT+=1"
        set "FAIL_DAYS=!FAIL_DAYS! %DAY%/5"
    ) else (
        set /a "SUCCESS_COUNT+=1"
        set "SUCCESS_DAYS=!SUCCESS_DAYS! %DAY%/5"
    )
    del "%RES_FILE%" >nul 2>&1
) else (
    echo  [FAIL] Ngay %DAY%/5 - Khong nhan duoc phan hoi tu server!
    set /a "FAIL_COUNT+=1"
    set "FAIL_DAYS=!FAIL_DAYS! %DAY%/5"
)
timeout /t 1 /nobreak >nul
goto :eof

:DONE
echo.
echo  [STEP 3] Dang xuat...
curl -s -b "%COOKIE_FILE%" -X POST "%BASE_URL%/api/logout" >nul 2>&1
del "%COOKIE_FILE%" >nul 2>&1
del "%TEMP%\khsx_login_s5.json" >nul 2>&1

echo.
echo  ===========================================================
echo    KET QUA UPLOAD SALE THANG 5/2026 (NGAY 1-17):
echo.
echo    Thanh cong: %SUCCESS_COUNT% ngay
if defined SUCCESS_DAYS echo      Ngay:!SUCCESS_DAYS!
echo.
echo    CHUA CAP NHAT: %FAIL_COUNT% ngay
if defined FAIL_DAYS (
    echo      Ngay:!FAIL_DAYS!
    echo      ^(Sheet chua co du lieu, sai dinh dang, hoac loi server^)
) else (
    echo      Tat ca da cap nhat thanh cong!
)
echo.

REM Hien thi danh sach code cam chua co trong DB
python -c "
import sys
sys.stdout.reconfigure(encoding='utf-8')
lines=[l.strip() for l in open(r'%NOT_FOUND_LOG%',encoding='utf-8') if l.strip()]
if lines:
    print('  CODE CAM CHUA CO TRONG DATABASE:')
    for l in lines:
        print('   -', l)
    print()
    print('  [!] Can them cac code cam nay vao SanPham tren web roi import lai.')
else:
    print('  Tat ca code cam da duoc nhan dang trong DB.')
"

del "%NOT_FOUND_LOG%" >nul 2>&1
echo.
echo    Kiem tra tai: %BASE_URL%/page/sale
echo  ===========================================================
echo.
pause
