#!/usr/bin/env python3
"""
Upload Sale THANG 5/2026 - Ngay 1 den 17
File: DAILY SALED REPORT THANG 5.2026.xlsm
Server: https://flask-appkhsx.onrender.com
"""
import sys, os, json, time, requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# ============================================================
BASE_URL  = "https://flask-appkhsx.onrender.com"
DATA_DIR  = Path(__file__).parent
SALE_FILE = DATA_DIR / "DAILY SALED REPORT THANG 5.2026.xlsm"
USERNAME  = "phinho"
PASSWORD  = "nho123"
MONTH     = 5
YEAR      = 2026
DAY_START = 1
DAY_END   = 17
# ============================================================

print()
print("=" * 60)
print("  UPLOAD SALE THANG 5/2026 - NGAY 1 den 17")
print(f"  File: {SALE_FILE.name}")
print(f"  Server: {BASE_URL}")
print("=" * 60)
print()

# Kiem tra file
if not SALE_FILE.exists():
    print(f"[LOI] Khong tim thay file: {SALE_FILE}")
    sys.exit(1)
print(f"[OK] File Excel: {SALE_FILE.name} ({SALE_FILE.stat().st_size/1024/1024:.1f} MB)")
print()

# ---- Dang nhap ----
session = requests.Session()
print("[STEP 1] Dang dang nhap...")
try:
    resp = session.post(f"{BASE_URL}/api/login",
                        json={"username": USERNAME, "password": PASSWORD},
                        timeout=30, verify=False)
    data = resp.json()
    if not data.get("success"):
        print(f"[LOI] Dang nhap that bai: {data}")
        sys.exit(1)
    print("[OK] Dang nhap thanh cong!")
except Exception as e:
    print(f"[LOI] Khong ket noi duoc server: {e}")
    sys.exit(1)
print()

# ---- Upload tung ngay ----
print("[STEP 2] Upload du lieu tung ngay...")
print("-" * 60)

success_days = []
fail_days    = []
not_found_all = {}  # { "code": ["day1", "day2", ...] }

for day in range(DAY_START, DAY_END + 1):
    sheet_name = str(day)  # Ten sheet la "1", "2", ... "17"
    print(f"\n  --- Ngay {day}/{MONTH}/{YEAR} (Sheet: \"{sheet_name}\") ---")

    try:
        with open(SALE_FILE, "rb") as f:
            resp = session.post(
                f"{BASE_URL}/api/sale/upload-import",
                files={"file": (SALE_FILE.name, f, "application/vnd.ms-excel.sheet.macroEnabled.12")},
                data={"sheet": sheet_name},
                timeout=120, verify=False
            )
        result = resp.json()

        ok        = result.get("success", False)
        msg       = result.get("message", "")
        count     = result.get("count", 0)
        not_found = result.get("not_found", [])

        if ok:
            print(f"  [OK] Ngay {day}/{MONTH} - Import thanh cong {count} san pham")
            success_days.append(day)
        else:
            print(f"  [FAIL] Ngay {day}/{MONTH} - {msg}")
            fail_days.append(day)

        if not_found:
            print(f"  [!] Code cam CHUA CO trong DB ({len(not_found)} code):")
            for code in not_found:
                print(f"       - {code}")
                if code not in not_found_all:
                    not_found_all[code] = []
                not_found_all[code].append(f"{day}/{MONTH}")

    except Exception as e:
        print(f"  [ERR] Loi ket noi: {e}")
        fail_days.append(day)

    time.sleep(0.5)

# ---- Dang xuat ----
print()
print("[STEP 3] Dang xuat...")
try:
    session.post(f"{BASE_URL}/api/logout", timeout=10, verify=False)
except:
    pass

# ---- Ket qua tong ket ----
print()
print("=" * 60)
print("  KET QUA UPLOAD SALE THANG 5/2026 (NGAY 1-17):")
print()
print(f"  Thanh cong: {len(success_days)} ngay")
if success_days:
    days_str = ", ".join(f"{d}/{MONTH}" for d in success_days)
    print(f"    Ngay: {days_str}")
print()
print(f"  CHUA CAP NHAT: {len(fail_days)} ngay")
if fail_days:
    days_str = ", ".join(f"{d}/{MONTH}" for d in fail_days)
    print(f"    Ngay: {days_str}")
    print("    (Sheet chua co du lieu, sai dinh dang, hoac loi server)")
else:
    print("    Tat ca da cap nhat thanh cong!")
print()

if not_found_all:
    print(f"  CODE CAM CHUA CO TRONG DATABASE ({len(not_found_all)} code):")
    for code, days in sorted(not_found_all.items()):
        days_str = ", ".join(days)
        print(f"    - {code}  (gap o ngay: {days_str})")
    print()
    print("  [!] Can them cac code cam nay vao SanPham tren web roi import lai.")
else:
    print("  Tat ca code cam da duoc nhan dang trong DB.")
print()
print(f"  Kiem tra tai: {BASE_URL}/page/sale")
print("=" * 60)
print()
input("Nhan Enter de dong...")
