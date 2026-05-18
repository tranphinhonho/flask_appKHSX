#!/usr/bin/env python3
"""
Import Bao Bi (DAILY STOCK EMPTY BAG REPORT) truc tiep vao Neon.tech PostgreSQL
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
from utils.bag_report_importer import BagReportImporter

# ============================================================
FOLDER    = Path(r'D:\Github\flask_appKHSX\update flask app khsx\FSTOCK-BAG')
MONTH     = 5
YEAR      = 2026
DAY_START = 1
DAY_END   = 17
USER      = 'phinho'
# ============================================================

print()
print("=" * 60)
print("  IMPORT BAO BI (DAILY STOCK EMPTY BAG REPORT) THANG 5/2026")
print(f"  Folder: {FOLDER.name}")
print(f"  DB    : {config.DATABASE_PATH[:55]}...")
print("=" * 60)
print()

importer = BagReportImporter(db_path=config.DATABASE_PATH)

def extract_date(filename):
    """Trich xuat ngay tu ten file - xu ly nhieu khoang trang"""
    normalized = re.sub(r'\s+', ' ', filename)
    normalized = re.sub(r'\s*-\s*', '-', normalized)
    m = re.search(r'(\d{1,2})-(\d{2})-(\d{4})', normalized)
    if m:
        day, mon, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return yr, mon, day
    return None, None, None

# Scan file BAG REPORT
file_map = {}
for f in sorted(FOLDER.glob('DAILY STOCK EMPTY BAG REPORT*.xlsm')):
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

success_days = []
fail_days    = []
skip_days    = []

for day in range(DAY_START, DAY_END + 1):
    if day not in file_map:
        print(f"\n  --- Ngay {day}/5 --- [SKIP] Khong co file")
        skip_days.append(day)
        continue

    fpath = file_map[day]
    ngay_str = f"{YEAR}-{MONTH:02d}-{day:02d}"
    print(f"\n  --- Ngay {day}/5/2026 --- {fpath.name}")

    try:
        result = importer.import_bag_report(
            file_path=fpath,
            nguoi_import=USER,
            ngay_stock=ngay_str,
            overwrite=True
        )

        ok      = result.get('success', 0)
        errors  = result.get('errors', [])
        skipped = result.get('skipped', False)

        if skipped:
            print(f"  [SKIP] {errors[0] if errors else 'Da import truoc'}")
            skip_days.append(day)
        elif ok > 0:
            print(f"  [OK] Import thanh cong {ok} dong")
            success_days.append(day)
        else:
            errmsg = ', '.join(str(e) for e in errors) if errors else 'Khong co du lieu hop le'
            print(f"  [FAIL] {errmsg}")
            fail_days.append(day)

        if errors and not skipped:
            for e in errors[:3]:
                print(f"    [ERR] {e}")

    except Exception as e:
        print(f"  [ERR] {e}")
        fail_days.append(day)

    time.sleep(0.2)

# ---- Tong ket ----
print()
print("=" * 60)
print("  KET QUA IMPORT BAO BI THANG 5/2026 (NGAY 1-17):")
print()
print(f"  Thanh cong: {len(success_days)} ngay")
if success_days:
    print(f"    Ngay: {', '.join(f'{d}/{MONTH}' for d in success_days)}")
print()
print(f"  THAT BAI: {len(fail_days)} ngay")
if fail_days:
    print(f"    Ngay: {', '.join(f'{d}/{MONTH}' for d in fail_days)}")
else:
    print("    Khong co ngay that bai!")
print()
print(f"  KHONG CO FILE: {len(skip_days)} ngay")
if skip_days:
    print(f"    Ngay: {', '.join(f'{d}/{MONTH}' for d in skip_days)}")
print()
print("  Kiem tra tai: https://flask-appkhsx.onrender.com/page/baobi")
print("=" * 60)
print()
input("Nhan Enter de dong...")
