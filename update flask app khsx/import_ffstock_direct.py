#!/usr/bin/env python3
"""
Import FFSTOCK (Stock hom nay) tu folder FSTOCK-BAG
Truc tiep vao Neon.tech PostgreSQL
"""
import sys, os, re, time
from pathlib import Path

sys.path.insert(0, r'D:\Github\flask_appKHSX')
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

os.environ['DATABASE_URL'] = (
    'postgresql://neondb_owner:npg_MBpyCtcL27vm'
    '@ep-small-bar-a1bpplnk-pooler.ap-southeast-1.aws.neon.tech'
    '/neondb?sslmode=require'
)

import config
from utils.stock_importer import StockImporter

# ============================================================
FOLDER   = Path(r'D:\Github\flask_appKHSX\update flask app khsx\FSTOCK-BAG')
MONTH    = 5
YEAR     = 2026
DAY_START = 1
DAY_END   = 17
USER     = 'phinho'
# ============================================================

print()
print("=" * 60)
print("  IMPORT FFSTOCK (STOCK HOM NAY) THANG 5/2026")
print(f"  Folder: {FOLDER.name}")
print(f"  DB    : {config.DATABASE_PATH[:55]}...")
print("=" * 60)
print()

importer = StockImporter(db_path=config.DATABASE_PATH)

# --- Quet tat ca file trong folder, map ngay -> file ---
def extract_date(filename):
    """Trich xuat ngay tu ten file FFSTOCK DD-MM-YYYY.xlsm
    Ho tro ten file co nhieu khoang trang bat ky: 'FFSTOCK 03 -05-2026.xlsm'
    """
    # Chuan hoa: thu gon nhieu khoang trang thanh 1, loai khoang trang quanh dau gach
    normalized = re.sub(r'\s+', ' ', filename)          # nhieu space -> 1 space
    normalized = re.sub(r'\s*-\s*', '-', normalized)    # 'X -Y' -> 'X-Y'
    m = re.search(r'(\d{1,2})-(\d{2})-(\d{4})', normalized)
    if m:
        day, mon, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return yr, mon, day
    return None, None, None

file_map = {}  # day -> Path
for f in sorted(FOLDER.glob('FFSTOCK*.xlsm')):
    yr, mon, day = extract_date(f.name)
    if yr == YEAR and mon == MONTH and DAY_START <= day <= DAY_END:
        file_map[day] = f
        print(f"  [FOUND] Ngay {day:2d}/5 -> {f.name}")

print()
missing_days = [d for d in range(DAY_START, DAY_END + 1) if d not in file_map]
if missing_days:
    print(f"  [!] Khong co file cho cac ngay: {', '.join(str(d)+'/5' for d in missing_days)}")
print()

# --- Import tung file ---
print("[STEP] Import tung file...")
print("-" * 60)

success_days  = []
fail_days     = []
skip_days     = []
not_found_all = {}  # code -> [day]
auto_added_all = []

for day in range(DAY_START, DAY_END + 1):
    if day not in file_map:
        print(f"\n  --- Ngay {day}/5 --- [SKIP] Khong co file")
        skip_days.append(day)
        continue

    fpath = file_map[day]
    ngay_str = f"{YEAR}-{MONTH:02d}-{day:02d}"
    print(f"\n  --- Ngay {day}/5/2026 --- {fpath.name}")

    try:
        result = importer.import_ffstock(
            file_path=fpath,
            nguoi_import=USER,
            ngay_stock=ngay_str,
            overwrite=True,        # Overwrite neu da import truoc
            auto_add_missing=False # Khong tu dong them SP - bao not_found
        )

        ok         = result.get('success', 0)
        not_found  = result.get('not_found', [])
        auto_added = result.get('auto_added', [])
        errors     = result.get('errors', [])
        skipped    = result.get('skipped', False)

        if skipped:
            print(f"  [SKIP] {errors[0] if errors else 'Da import truoc'}")
            skip_days.append(day)
        elif ok > 0:
            print(f"  [OK] Import thanh cong {ok} san pham")
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

        if auto_added:
            for sp in auto_added:
                print(f"  [AUTO] Tu dong them SP: {sp['code']} - {sp['ten']}")
                auto_added_all.append(f"{sp['code']} ({day}/5)")

    except Exception as e:
        print(f"  [ERR] {e}")
        fail_days.append(day)

    time.sleep(0.2)

# ---- Tong ket ----
print()
print("=" * 60)
print("  KET QUA IMPORT FFSTOCK THANG 5/2026 (NGAY 1-17):")
print()
print(f"  Thanh cong: {len(success_days)} ngay")
if success_days:
    print(f"    Ngay: {', '.join(f'{d}/{MONTH}' for d in success_days)}")
print()
print(f"  CHUA CAP NHAT: {len(fail_days)} ngay")
if fail_days:
    print(f"    Ngay: {', '.join(f'{d}/{MONTH}' for d in fail_days)}")
    print("    (Khong co du lieu hoac loi DB)")
else:
    print("    Tat ca da cap nhat thanh cong!")
print()
print(f"  KHONG CO FILE: {len(skip_days)} ngay")
if skip_days:
    print(f"    Ngay: {', '.join(f'{d}/{MONTH}' for d in skip_days)}")
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
if auto_added_all:
    print(f"  TU DONG THEM VAO SANPHAM ({len(auto_added_all)} san pham):")
    for item in auto_added_all:
        print(f"    + {item}")
    print()
print("  Kiem tra tai: https://flask-appkhsx.onrender.com/page/stockold")
print("=" * 60)
print()
input("Nhan Enter de dong...")
