#!/usr/bin/env python3
"""Re-import Batching (cac ngay bi thieu code) + Ton Bon sau khi them 5 code moi"""
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
from utils import get_db_connection
from utils.production_importer import ProductionImporter
from utils.tonbon_importer import TonBonImporter

FOLDER    = Path(r'D:\Github\flask_appKHSX\update flask app khsx\BATCHING-TONBON')
MONTH     = 5
YEAR      = 2026
USER      = 'phinho'
DB        = config.DATABASE_PATH

# Cac ngay batching bi thieu code
REIMPORT_BATCHING_DAYS = [8, 11, 12, 13]

print()
print("=" * 65)
print("  RE-IMPORT BATCHING + TON BON (sau khi them 5 code moi)")
print(f"  DB: {DB[:55]}...")
print("=" * 65)

# ============================================================
# Refresh SP cache
# ============================================================
print()
print("[PREP] Refresh SanPham cache...")
conn0 = get_db_connection(DB)
cur0  = conn0.cursor()
cur0.execute('SELECT "Code cám", "ID" FROM "SanPham" WHERE "Đã xóa"::integer = 0')
sp_cache = {}
for row in cur0.fetchall():
    code = str(row[0]).strip() if row[0] else ''
    if code:
        sp_cache[code] = row[1]
conn0.close()
print(f"  Loaded {len(sp_cache)} san pham (co them 5 code moi)\n")

def get_day_from_csv(fname):
    m = re.search(r'(?:PRODUCTION|PRO)\s*(\d+)', fname, re.IGNORECASE)
    return int(m.group(1)) if m else None

csv_map = {}
for f in FOLDER.glob('*.csv'):
    day = get_day_from_csv(f.name)
    if day and day in REIMPORT_BATCHING_DAYS:
        csv_map[day] = f

prod_importer = ProductionImporter(db_path=DB)

# ============================================================
# PHAN 1: RE-IMPORT BATCHING
# ============================================================
print(">>> PHAN 1: RE-IMPORT BATCHING")
print(f"    Cac ngay: {', '.join(str(d)+'/5' for d in REIMPORT_BATCHING_DAYS)}")
print("-" * 65)

batch_success = []
batch_not_found_all = {}

for day in REIMPORT_BATCHING_DAYS:
    if day not in csv_map:
        print(f"\n  --- Ngay {day}/5 --- [SKIP] Khong tim thay file CSV")
        continue

    fpath    = csv_map[day]
    ngay_str = f"{YEAR}-{MONTH:02d}-{day:02d}"
    print(f"\n  --- Ngay {day}/5/2026 --- {fpath.name}")

    try:
        parsed   = prod_importer._parse_production_csv(fpath)
        products = parsed.get('products', [])
        if not products:
            print(f"    [FAIL] Khong co du lieu")
            continue

        conn = get_db_connection(DB)
        cur  = conn.cursor()

        # Xoa du lieu cu
        cur.execute(
            'UPDATE "Mixer" SET "Đã xóa" = %s, "Người sửa" = %s WHERE "Ngày trộn" = %s',
            ('1', 'system_reimport', ngay_str)
        )
        deleted = cur.rowcount

        # MAX mixer code
        cur.execute("SELECT MAX(\"Mã mixer\") FROM \"Mixer\" WHERE \"Mã mixer\" LIKE 'MX%'")
        row = cur.fetchone()
        max_mx   = row[0] if row and row[0] else None
        next_num = int(max_mx[2:]) + 1 if max_mx else 1

        thoi_gian = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ok_count  = 0
        nf_list   = []

        for item in products:
            code  = item['code_cam'].strip().rstrip('*')
            id_sp = sp_cache.get(code) or sp_cache.get(item['code_cam'].strip())
            if not id_sp:
                if code not in ('026903',):
                    nf_list.append(code)
                continue

            ma_mx    = f"MX{next_num:05d}"
            next_num += 1
            du       = item.get('description', '').upper()
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
                nf_list.append(f"ERR:{code}:{e}")
                conn.rollback()
                cur = conn.cursor()

        conn.commit()
        conn.close()

        print(f"    [OK] {ok_count} san pham (xoa cu: {deleted})")
        if nf_list:
            uniq = sorted(set(nf_list))
            print(f"    [!] Chua co: {uniq}")
            for c in uniq:
                if c not in batch_not_found_all:
                    batch_not_found_all[c] = []
                batch_not_found_all[c].append(f"{day}/5")
        if ok_count > 0:
            batch_success.append(day)

    except Exception as e:
        print(f"    [ERR] {e}")

    time.sleep(0.1)

# ============================================================
# PHAN 2: RE-IMPORT TON BON (full - vi khong biet ngay nao co code moi)
# ============================================================
print()
print(">>> PHAN 2: RE-IMPORT TON BON (tat ca 16 ngay)")
print("-" * 65)

ton_files = (list(FOLDER.glob('Bao cao ton bon*.xlsx')) +
             list(FOLDER.glob('*ton bon*.xlsx')))

if not ton_files:
    print("  [!] Khong tim thay file Ton Bon!")
else:
    tonbon_file = ton_files[0]
    print(f"  File: {tonbon_file.name}")
    ton_importer = TonBonImporter(db_path=DB)
    try:
        result = ton_importer.import_all_days(
            file_path=tonbon_file,
            nguoi_import=USER,
            overwrite=True
        )
        ok_tb   = result.get('success', 0)
        nf_tb   = result.get('not_found', [])
        days_tb = result.get('days_imported', 0)
        print(f"\n  [OK] Ton bon: {ok_tb} records tu {days_tb} ngay")
        if nf_tb:
            print(f"  [!] Code van CHUA CO: {sorted(set(nf_tb))}")
        else:
            print("  Tat ca code cam da duoc nhan dang!")
    except Exception as e:
        print(f"  [ERR] {e}")

# ============================================================
# TONG KET
# ============================================================
print()
print("=" * 65)
print("  KET QUA RE-IMPORT:")
print()
print(f"  [BATCHING] Thanh cong: {len(batch_success)} ngay")
if batch_success:
    print(f"    {', '.join(str(d)+'/5' for d in batch_success)}")
if batch_not_found_all:
    print(f"  [!] Van con code chua co:")
    for c, days in sorted(batch_not_found_all.items()):
        print(f"    - {c} ({', '.join(days)})")
else:
    print("  Tat ca code cam da duoc nhan dang!")
print()
print("  Kiem tra tai:")
print("    Batching: https://flask-appkhsx.onrender.com/page/mixer")
print("    Ton bon : https://flask-appkhsx.onrender.com/page/tonbon")
print("=" * 65)
input("\nNhan Enter de dong...")
