import sys, os, traceback
sys.path.insert(0, r'D:\Github\flask_appKHSX')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = (
    'postgresql://neondb_owner:npg_MBpyCtcL27vm'
    '@ep-small-bar-a1bpplnk-pooler.ap-southeast-1.aws.neon.tech'
    '/neondb?sslmode=require'
)

from backend import db
db.init_db(os.environ['DATABASE_URL'])

conn = db.connect_db()
cursor = conn.cursor()

ngay = '2026-05-18'

# Step 1: Main query
print("=== Step 1: Main query ===")
try:
    cursor.execute("""
        SELECT COUNT(*) FROM StockHomNay s 
        LEFT JOIN SanPham sp ON s.[ID sản phẩm] = sp.ID 
        WHERE s.[Đã xóa] = 0 AND CAST(s.[Ngày stock] AS TEXT) = ?
    """, (ngay,))
    total = cursor.fetchone()[0]
    print(f"Total: {total}")
except Exception as e:
    print(f"ERROR Step 1: {e}")
    traceback.print_exc()

# Step 2: Fetch rows
print("\n=== Step 2: Fetch rows ===")
try:
    cursor.execute("""
        SELECT s.ID, s.[ID sản phẩm], sp.[Code cám], sp.[Tên cám],
               sp.[Vật nuôi], sp.[Batch size],
               s.[Số lượng], s.[Ngày stock], s.[Ghi chú],
               s.[Ghi chú 2], s.[Kết quả GC2],
               s.[Ghi chú 2 A], s.[Kết quả GC2 A],
               s.[Ghi chú 2 B], s.[Kết quả GC2 B],
               s.[Người tạo]
        FROM StockHomNay s
        LEFT JOIN SanPham sp ON s.[ID sản phẩm] = sp.ID
        WHERE s.[Đã xóa] = 0 AND CAST(s.[Ngày stock] AS TEXT) = ?
        ORDER BY s.[Kết quả GC2] ASC LIMIT ?
    """, (ngay, 300))
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    print(f"Rows: {len(rows)}")
    if rows:
        print(f"First row col1 (ID SP): {rows[0][1]} type: {type(rows[0][1])}")
except Exception as e:
    print(f"ERROR Step 2: {e}")
    traceback.print_exc()
    conn.close()
    exit()

if not rows:
    print("No rows found!")
    conn.close()
    exit()

# Step 3: Build id_sp_list
id_sp_list = list({row[1] for row in rows})
print(f"\n=== Step 3: id_sp_list ===")
print(f"Count: {len(id_sp_list)}")
print(f"Sample: {id_sp_list[:5]}")
print(f"Types: {[type(x) for x in id_sp_list[:3]]}")

# Step 4: Batch Aver query
print("\n=== Step 4: Batch Aver ===")
try:
    placeholders = ','.join(['?' for _ in id_sp_list])
    cursor.execute(f"""
        SELECT [ID sản phẩm],
               COALESCE(SUM([Số lượng]),0) as tong,
               COUNT(DISTINCT [Ngày sale]) as so_ngay
        FROM Sale
        WHERE [Đã xóa] = 0 AND [ID sản phẩm] IN ({placeholders})
        GROUP BY [ID sản phẩm]
    """, id_sp_list)
    aver_rows = cursor.fetchall()
    print(f"Aver rows: {len(aver_rows)}")
    if aver_rows:
        print(f"Sample: id={aver_rows[0][0]}, tong={aver_rows[0][1]}, so_ngay={aver_rows[0][2]}")
except Exception as e:
    print(f"ERROR Step 4: {e}")
    traceback.print_exc()

# Step 5: Batch Day5 query
print("\n=== Step 5: Batch Day5 ===")
try:
    from datetime import timedelta
    from backend.utils import get_vietnam_time
    today = get_vietnam_time().date()
    date_5ago = (today - timedelta(days=5)).strftime('%Y-%m-%d')
    cursor.execute(f"""
        SELECT [ID sản phẩm], COALESCE(SUM([Số lượng]),0)
        FROM Packing
        WHERE [Đã xóa] = 0
          AND CAST([Ngày packing] AS TEXT) >= ?
          AND [ID sản phẩm] IN ({placeholders})
        GROUP BY [ID sản phẩm]
    """, [date_5ago] + id_sp_list)
    day5_rows = cursor.fetchall()
    print(f"Day5 rows: {len(day5_rows)}")
except Exception as e:
    print(f"ERROR Step 5: {e}")
    traceback.print_exc()

conn.close()
print("\n=== DONE ===")
