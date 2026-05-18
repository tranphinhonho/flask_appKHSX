#!/usr/bin/env python3
"""
Import Packing THANG 5/2026 trực tiếp vào Neon.tech PostgreSQL
Không cần qua API server
"""
import sys, os, time
sys.path.insert(0, r'D:\Github\flask_appKHSX')

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

os.environ['DATABASE_URL'] = (
    'postgresql://neondb_owner:npg_MBpyCtcL27vm'
    '@ep-small-bar-a1bpplnk-pooler.ap-southeast-1.aws.neon.tech'
    '/neondb?sslmode=require'
)

import config
from utils.packing_importer import PackingImporter

# ============================================================
DATA_DIR     = r'D:\Github\flask_appKHSX\update flask app khsx'
PACKING_FILE = os.path.join(DATA_DIR, 'DAILY PACKING THANG 5.2026.xlsm')
MONTH        = 5
YEAR         = 2026
DAY_START    = 1
DAY_END      = 17
USER         = 'phinho'
# ============================================================

print()
print("=" * 60)
print("  IMPORT PACKING THANG 5/2026 TRUC TIEP VAO NEON.TECH")
print(f"  File: {os.path.basename(PACKING_FILE)}")
print(f"  DB  : {config.DATABASE_PATH[:60]}...")
print("=" * 60)
print()

if not os.path.exists(PACKING_FILE):
    print(f"[LOI] Khong tim thay file: {PACKING_FILE}")
    sys.exit(1)
print(f"[OK] File Excel: {os.path.basename(PACKING_FILE)}")
print()

importer = PackingImporter(db_path=config.DATABASE_PATH)

success_days  = []
fail_days     = []
not_found_all = {}  # code -> [day, ...]

print("[STEP] Import tung ngay...")
print("-" * 60)

for day in range(DAY_START, DAY_END + 1):
    sheet = str(day)
    print(f"\n  --- Ngay {day}/{MONTH}/{YEAR} (Sheet: \"{sheet}\") ---")

    try:
        result = importer.import_packing_data(
            file_path=PACKING_FILE,
            sheet_name=sheet,
            nguoi_import=USER,
            year=YEAR,
            month=MONTH
        )

        ok        = result['success']
        not_found = result.get('not_found', [])
        errors    = result.get('errors', [])
        deleted   = result.get('deleted', 0)

        if ok > 0:
            print(f"  [OK] Import thanh cong {ok} san pham (da xoa {deleted} cu)")
            success_days.append(day)
        else:
            errmsg = ', '.join(errors) if errors else 'Khong co du lieu hop le'
            print(f"  [FAIL] {errmsg}")
            fail_days.append(day)

        if not_found:
            print(f"  [!] Code cam CHUA CO trong DB ({len(not_found)} code):")
            for code in not_found:
                print(f"       - {code}")
                if code not in not_found_all:
                    not_found_all[code] = []
                not_found_all[code].append(f"{day}/{MONTH}")

    except Exception as e:
        print(f"  [ERR] {e}")
        fail_days.append(day)

    time.sleep(0.3)

# ---- Tong ket ----
print()
print("=" * 60)
print("  KET QUA IMPORT PACKING THANG 5/2026 (NGAY 1-17):")
print()
print(f"  Thanh cong: {len(success_days)} ngay")
if success_days:
    print(f"    Ngay: {', '.join(f'{d}/{MONTH}' for d in success_days)}")
print()
print(f"  CHUA CAP NHAT: {len(fail_days)} ngay")
if fail_days:
    print(f"    Ngay: {', '.join(f'{d}/{MONTH}' for d in fail_days)}")
    print("    (Sheet trong, sai dinh dang, hoac loi DB)")
else:
    print("    Tat ca da cap nhat thanh cong!")
print()

if not_found_all:
    print(f"  CODE CAM CHUA CO TRONG DATABASE ({len(not_found_all)} code):")
    for code, days in sorted(not_found_all.items()):
        print(f"    - {code}  (gap o ngay: {', '.join(days)})")
    print()
    print("  [!] Can them cac code nay vao SanPham roi import lai.")
else:
    print("  Tat ca code cam da duoc nhan dang trong DB.")
print()
print("  Kiem tra tai: https://flask-appkhsx.onrender.com/page/packing")
print("=" * 60)
print()
input("Nhan Enter de dong...")
