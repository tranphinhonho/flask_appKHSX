#!/usr/bin/env python3
"""Import Batching (PRODUCTION CSV) truc tiep vao Neon.tech - bypass connection abort"""
import sys, os, re, time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, r'D:\Github\flask_appKHSX')
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

os.environ['DATABASE_URL'] = (
    'postgresql://neondb_owner:npg_MBpyCtcL27vm'
    '@ep-small-bar-a1bpplnk-pooler.ap-southeast-1.aws.neon.tech'
    '/neondb?sslmode=require'
)

import config
from utils import get_db_connection, is_postgres, q, ph
from utils.production_importer import ProductionImporter

FOLDER    = Path(r'D:\Github\flask_appKHSX\update flask app khsx\BATCHING-TONBON')
MONTH     = 5
YEAR      = 2026
DAY_START = 1
DAY_END   = 17
USER      = 'phinho'
DB        = config.DATABASE_PATH

print()
print("=" * 65)
print("  IMPORT BATCHING (PRODUCTION CSV) THANG 5/2026 -> NEON.TECH")
print(f"  DB: {DB[:55]}...")
print("=" * 65)
print()

# Build product lookup cache (code_cam -> ID) to avoid repeated queries
print("[PREP] Building SanPham lookup cache...")
conn0 = get_db_connection(DB)
cur0  = conn0.cursor()
cur0.execute('SELECT "Code cám", "ID" FROM "SanPham" WHERE "Đã xóa"::integer = 0')
sp_cache = {}
for row in cur0.fetchall():
    code = str(row[0]).strip() if row[0] else ''
    if code:
        sp_cache[code] = row[1]
conn0.close()
print(f"  Loaded {len(sp_cache)} san pham vao cache\n")

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
    print(f"  [!] Khong co CSV: {', '.join(str(d)+'/5' for d in missing_csv)}")
print()

prod_importer = ProductionImporter(db_path=DB)

success_days     = []
fail_days        = []
skip_days        = [d for d in range(DAY_START, DAY_END + 1) if d not in csv_map]
not_found_all    = {}  # code -> [days]

print("[STEP] Import tung file...")
print("-" * 65)

for day in range(DAY_START, DAY_END + 1):
    if day not in csv_map:
        continue

    fpath    = csv_map[day]
    ngay_str = f"{YEAR}-{MONTH:02d}-{day:02d}"
    print(f"\n  --- Ngay {day}/5/2026 --- {fpath.name}")

    # Parse CSV
    try:
        parsed = prod_importer._parse_production_csv(fpath)
    except Exception as e:
        print(f"    [ERR] Parse CSV: {e}")
        fail_days.append(day)
        continue

    products = parsed.get('products', [])
    if not products:
        print(f"    [FAIL] Khong co du lieu trong CSV")
        fail_days.append(day)
        continue

    # Dung connection rieng cho moi ngay de tranh abort state
    try:
        conn = get_db_connection(DB)
        cur  = conn.cursor()

        # Xoa du lieu cu cua ngay nay
        cur.execute(
            'UPDATE "Mixer" SET "Đã xóa" = %s, "Người sửa" = %s WHERE "Ngày trộn" = %s',
            ('1', 'system_reimport', ngay_str)
        )
        deleted = cur.rowcount

        thoi_gian = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ok_count  = 0
        nf_list   = []
        err_list  = []

        # MAX mixer code
        cur.execute('SELECT MAX("Mã mixer") FROM "Mixer" WHERE "Mã mixer" LIKE \'MX%\'')
        row = cur.fetchone()
        max_mx = row[0] if row and row[0] else None
        next_num = int(max_mx[2:]) + 1 if max_mx else 1

        for item in products:
            code = item['code_cam'].strip().rstrip('*')
            # Lookup tu cache
            id_sp = sp_cache.get(code)
            if not id_sp:
                # Thu tim 8-char code (batch code)
                id_sp = sp_cache.get(item['code_cam'].strip())
            if not id_sp:
                if code not in ('026903',):
                    nf_list.append(code)
                continue

            ma_mx = f"MX{next_num:05d}"
            next_num += 1

            desc = item.get('description', '')
            du = desc.upper()
            dich_den = 'Packing' if (' M ' in du or du.endswith(' M')) else 'Pellet'
            so_may   = 'Packing 3' if dich_den == 'Packing' else 'Pellet 1'

            try:
                cur.execute(
                    'INSERT INTO "Mixer" '
                    '("Mã mixer","Ngày trộn","ID sản phẩm","Batch size",'
                    '"Số lượng thực tế","Loss (kg)","Loss (%%)","Đích đến",'
                    '"Số máy","Ca sản xuất","Ghi chú","Người tạo","Thời gian tạo","Đã xóa")'
                    ' VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (ma_mx, ngay_str, id_sp,
                     item['batch_size'], item['actual'], item['loss_kg'], item['loss_pct'],
                     dich_den, so_may, 'Import',
                     f"Import tu {fpath.name}", USER, thoi_gian, '0')
                )
                ok_count += 1
            except Exception as e:
                err_list.append(f"{code}: {e}")
                conn.rollback()  # Reset aborted state
                # Re-open cursor after rollback
                cur = conn.cursor()

        conn.commit()
        conn.close()

        print(f"    [OK] {ok_count} san pham (xoa cu: {deleted})")
        if nf_list:
            uniq_nf = sorted(set(nf_list))
            print(f"    [!] Code CHUA CO trong DB ({len(uniq_nf)}): {uniq_nf[:10]}")
            for c in uniq_nf:
                if c not in not_found_all:
                    not_found_all[c] = []
                not_found_all[c].append(f"{day}/5")
        if err_list:
            print(f"    [WARN] {len(err_list)} loi insert")

        if ok_count > 0:
            success_days.append(day)
        else:
            fail_days.append(day)

    except Exception as e:
        print(f"    [ERR] {e}")
        fail_days.append(day)
        try: conn.close()
        except: pass

    time.sleep(0.1)

# Tong ket
print()
print("=" * 65)
print("  KET QUA IMPORT BATCHING THANG 5/2026:")
print()
print(f"  Thanh cong: {len(success_days)} ngay")
if success_days:
    print(f"    {', '.join(str(d)+'/5' for d in success_days)}")
if fail_days:
    print(f"  THAT BAI  : {', '.join(str(d)+'/5' for d in fail_days)}")
if skip_days:
    print(f"  Khong file: {', '.join(str(d)+'/5' for d in skip_days)}")
print()
if not_found_all:
    print(f"  CODE CAM CHUA CO TRONG DB ({len(not_found_all)} code):")
    for code, days in sorted(not_found_all.items()):
        print(f"    - {code}  (ngay: {', '.join(days)})")
else:
    print("  Tat ca code cam da nhan dang!")
print()
print("  Kiem tra tai: https://flask-appkhsx.onrender.com/page/mixer")
print("=" * 65)
input("\nNhan Enter de dong...")
