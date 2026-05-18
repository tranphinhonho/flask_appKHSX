import sys, os
sys.path.insert(0, r'D:\Github\flask_appKHSX')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = (
    'postgresql://neondb_owner:npg_MBpyCtcL27vm'
    '@ep-small-bar-a1bpplnk-pooler.ap-southeast-1.aws.neon.tech'
    '/neondb?sslmode=require'
)
import config
from utils import get_db_connection

conn = get_db_connection(config.DATABASE_PATH)
cur  = conn.cursor()

# Kiem tra du lieu StockHomNay thang 5/2026
cur.execute("""
    SELECT "Ngày stock", COUNT(*) as cnt, MAX("Thời gian tạo") as created
    FROM "StockHomNay"
    WHERE "Đã xóa" = '0'
    AND "Ngày stock"::text LIKE '2026-05%'
    GROUP BY "Ngày stock"
    ORDER BY "Ngày stock"
""")
rows = cur.fetchall()
print("=== StockHomNay thang 5/2026 ===")
for r in rows:
    print(f"  Ngay {r[0]}: {r[1]} SP | Tao luc: {r[2]}")

# Kiem tra ST00046
cur.execute("""
    SELECT "Mã stock", "Ngày stock", COUNT(*) as cnt
    FROM "StockHomNay"
    WHERE "Mã stock" = 'ST00046'
    GROUP BY "Mã stock", "Ngày stock"
""")
rows2 = cur.fetchall()
print("\n=== Ma stock ST00046 ===")
for r in rows2:
    print(f"  Ma: {r[0]} | Ngay: {r[1]} | So SP: {r[2]}")

# Kiem tra SP 510
cur.execute("""
    SELECT sh."Ngày stock", sh."Số lượng", sp."Code cám"
    FROM "StockHomNay" sh
    JOIN "SanPham" sp ON sh."ID sản phẩm"::integer = sp."ID"
    WHERE sp."Code cám" = '510' AND sh."Đã xóa" = '0'
    ORDER BY sh."Ngày stock" DESC LIMIT 5
""")
rows3 = cur.fetchall()
print("\n=== SP 510 trong StockHomNay ===")
for r in rows3:
    print(f"  Ngay: {r[0]} | Stock: {r[1]} kg")

conn.close()
input("\nNhan Enter de dong...")
