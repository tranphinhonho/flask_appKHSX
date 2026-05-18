#!/usr/bin/env python3
"""
Import Batching (PRODUCTION CSV) + Ton bon (Excel)
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
from utils.production_importer import ProductionImporter
from utils.tonbon_importer import TonBonImporter

FOLDER    = Path(r'D:\Github\flask_appKHSX\update flask app khsx\BATCHING-TONBON')
MONTH     = 5
YEAR      = 2026
DAY_START = 1
DAY_END   = 17
USER      = 'phinho'

DB = config.DATABASE_PATH

print()
print("=" * 65)
print("  IMPORT BATCHING + TON BON THANG 5/2026 -> NEON.TECH")
print(f"  Folder: {FOLDER.name}")
print(f"  DB    : {DB[:55]}...")
print("=" * 65)

# ============================================================
# PHAN 1: BATCHING (PRODUCTION CSV)
# ============================================================
print()
print(">>> PHAN 1: BATCHING (PRODUCTION CSV)")
print("-" * 65)

prod_importer = ProductionImporter(db_path=DB)

# Scan CSV files: PRODUCTION N.csv or PRO9.csv
def get_day_from_csv(fname):
    m = re.search(r'(?:PRODUCTION|PRO)\s*(\d+)', fname, re.IGNORECASE)
    return int(m.group(1)) if m else None

csv_map = {}
for f in FOLDER.glob('*.csv'):
    day = get_day_from_csv(f.name)
    if day and DAY_START <= day <= DAY_END:
        csv_map[day] = f
        print(f"  [FOUND] Ngay {day:2d}/5 -> {f.name}")

print()
missing_csv = [d for d in range(DAY_START, DAY_END + 1) if d not in csv_map]
if missing_csv:
    print(f"  [!] Khong co CSV cho ngay: {', '.join(str(d)+'/5' for d in missing_csv)}")
print()

batch_success = []
batch_fail    = []
batch_skip    = []
batch_not_found_all = {}

for day in range(DAY_START, DAY_END + 1):
    if day not in csv_map:
        batch_skip.append(day)
        continue

    fpath    = csv_map[day]
    ngay_str = f"{YEAR}-{MONTH:02d}-{day:02d}"
    print(f"  --- Ngay {day}/5/2026 --- {fpath.name}")

    try:
        result = prod_importer.import_production(
            file_path=fpath,
            nguoi_import=USER,
            ngay_san_xuat=ngay_str,
            overwrite=True
        )

        ok        = result.get('success', 0)
        not_found = result.get('not_found', [])
        errors    = result.get('errors', [])
        skipped   = result.get('skipped', False)

        if skipped:
            print(f"    [SKIP] {errors[0] if errors else 'Da import'}")
            batch_skip.append(day)
        elif ok > 0:
            print(f"    [OK] {ok} san pham")
            batch_success.append(day)
        else:
            errmsg = ', '.join(str(e) for e in errors) if errors else 'Khong co du lieu'
            print(f"    [FAIL] {errmsg}")
            batch_fail.append(day)

        if not_found:
            print(f"    [!] Code CHUA CO trong DB: {not_found}")
            for code in not_found:
                if code not in batch_not_found_all:
                    batch_not_found_all[code] = []
                batch_not_found_all[code].append(f"{day}/{MONTH}")

    except Exception as e:
        print(f"    [ERR] {e}")
        batch_fail.append(day)

    time.sleep(0.1)

# ============================================================
# PHAN 2: TON BON (Excel - 1 file nhieu sheet)
# ============================================================
print()
print(">>> PHAN 2: TON BON (Excel)")
print("-" * 65)

ton_importer = TonBonImporter(db_path=DB)

# Tim file Bao cao ton bon
tonbon_files = list(FOLDER.glob('Bao cao ton bon*.xlsx')) + \
               list(FOLDER.glob('Bao cao ton bon*.xlsm')) + \
               list(FOLDER.glob('*ton bon*.xlsx')) + \
               list(FOLDER.glob('*ton bon*.xlsm'))

if not tonbon_files:
    print("  [!] Khong tim thay file Bao cao ton bon trong folder!")
    tonbon_result = None
else:
    tonbon_file = tonbon_files[0]
    print(f"  [FOUND] {tonbon_file.name}")
    print()
    print("  Import tat ca ngay tu sheet so (1-17)...")

    try:
        tonbon_result = ton_importer.import_all_days(
            file_path=tonbon_file,
            nguoi_import=USER,
            overwrite=True
        )
        ok_tb       = tonbon_result.get('success', 0)
        nf_tb       = tonbon_result.get('not_found', [])
        err_tb      = tonbon_result.get('errors', [])
        days_tb     = tonbon_result.get('days_imported', 0)

        print(f"\n  [OK] Ton bon: {ok_tb} records tu {days_tb} ngay")
        if nf_tb:
            print(f"  [!] Code CHUA CO trong DB ({len(nf_tb)} code):")
            for code in sorted(set(nf_tb)):
                print(f"       - {code}")
        if err_tb:
            print(f"  [WARN] {len(err_tb)} loi:")
            for e in err_tb[:5]:
                print(f"    {e}")

    except Exception as e:
        print(f"  [ERR] {e}")
        tonbon_result = None

# ============================================================
# TONG KET
# ============================================================
print()
print("=" * 65)
print("  KET QUA IMPORT THANG 5/2026 (NGAY 1-17):")
print()

print("  [BATCHING]")
print(f"    Thanh cong: {len(batch_success)} ngay - {', '.join(str(d)+'/5' for d in batch_success)}")
if batch_fail:
    print(f"    THAT BAI  : {len(batch_fail)} ngay - {', '.join(str(d)+'/5' for d in batch_fail)}")
if batch_skip:
    print(f"    Khong file: {len(batch_skip)} ngay - {', '.join(str(d)+'/5' for d in batch_skip)}")
if batch_not_found_all:
    print(f"    CODE CHUA CO TRONG DB ({len(batch_not_found_all)} code):")
    for code, days in sorted(batch_not_found_all.items()):
        print(f"      - {code}  (ngay: {', '.join(days)})")
else:
    print("    Tat ca code cam da duoc nhan dang!")

print()
print("  [TON BON]")
if tonbon_result:
    ok_tb   = tonbon_result.get('success', 0)
    nf_tb   = tonbon_result.get('not_found', [])
    days_tb = tonbon_result.get('days_imported', 0)
    print(f"    Thanh cong: {ok_tb} records tu {days_tb} ngay")
    if nf_tb:
        print(f"    CODE CHUA CO: {sorted(set(nf_tb))}")
    else:
        print("    Tat ca code cam da duoc nhan dang!")
    # Kiem tra ngay con thieu
    missing_tb = [d for d in range(DAY_START, DAY_END + 1) if d not in batch_success and d not in batch_skip]
    if missing_tb:
        print(f"    [!] Chua co du lieu cho ngay: {', '.join(str(d)+'/5' for d in missing_tb)}")
else:
    print("    [!] Khong import duoc file ton bon")

print()
print("  Kiem tra tai:")
print("    - Batching: https://flask-appkhsx.onrender.com/page/mixer")
print("    - Ton bon : https://flask-appkhsx.onrender.com/page/tonbon")
print("=" * 65)
print()
input("Nhan Enter de dong...")
