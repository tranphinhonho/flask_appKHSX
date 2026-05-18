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

# Test 1: COALESCE with alias
print("=== Test 1: COALESCE regex ===")
sql = 'SELECT COALESCE(sh."Số lượng", 0) FROM "StockHomNay" sh LIMIT 1'
print(f"Input:  {sql}")
translated = db._translate_sql(sql)
print(f"Output: {translated}")
assert '::numeric' in translated, "FAIL: ::numeric not found!"
print("PASS\n")

# Test 2: Plan calculate query (manual plan check)
print("=== Test 2: Plan manual check query ===")
conn = db.connect_db()
cursor = conn.cursor()
try:
    SH_LATEST = """(
        SELECT sh2.[ID sản phẩm], sh2.[Số lượng]
        FROM StockHomNay sh2
        WHERE sh2.[Đã xóa] = 0
          AND sh2.[Ngày stock] = (
              SELECT MAX(sh3.[Ngày stock]) FROM StockHomNay sh3
              WHERE sh3.[ID sản phẩm] = sh2.[ID sản phẩm] AND sh3.[Đã xóa] = 0
          )
    )"""
    cursor.execute(f"""
        SELECT p.[ID sản phẩm], sp.[Code cám], sp.[Tên cám], p.[Số lượng],
               p.[Ghi chú], p.[Mã plan], COALESCE(sh.[Số lượng], 0) as stock
        FROM Plan p
        JOIN SanPham sp ON p.[ID sản phẩm] = sp.ID
        LEFT JOIN {SH_LATEST} sh ON sp.ID = sh.[ID sản phẩm]
        WHERE (p.[Ngày plan] = ? OR p.[Ngày plan] = ?) AND p.[Đã xóa] = 0
        ORDER BY p.ID ASC
    """, ('2026-05-19', '19/05/2026'))
    rows = cursor.fetchall()
    print(f"Manual plans: {len(rows)}")
    print("PASS\n")
except Exception as e:
    print(f"FAIL: {e}")
    traceback.print_exc()

# Test 3: StockHomNay get_list query
print("=== Test 3: StockHomNay get_list ===")
try:
    cursor.execute("""
        SELECT COUNT(*) FROM StockHomNay s 
        LEFT JOIN SanPham sp ON s.[ID sản phẩm] = sp.ID 
        WHERE s.[Đã xóa] = 0 AND CAST(s.[Ngày stock] AS TEXT) = ?
    """, ('2026-05-18',))
    total = cursor.fetchone()[0]
    print(f"Total: {total}")

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
    """, ('2026-05-18', 300))
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    print(f"Rows: {len(rows)}")
    
    # Test float conversion
    if rows:
        d = dict(zip(cols, rows[0]))
        print(f"  Sample: stock={d['Số lượng']} type={type(d['Số lượng'])}")
        print(f"  batch_size={d['Batch size']} type={type(d['Batch size'])}")
        print(f"  kq={d['Kết quả GC2']} type={type(d['Kết quả GC2'])}")
        stock = float(d['Số lượng'] or 0)
        print(f"  float(stock)={stock} OK")
    print("PASS\n")
except Exception as e:
    print(f"FAIL: {e}")
    traceback.print_exc()

# Test 4: days-in-month
print("=== Test 4: days-in-month ===")
try:
    cursor.execute("""
        SELECT DISTINCT LEFT(CAST([Ngày stock] AS TEXT), 10) as ngay_str
        FROM StockHomNay
        WHERE [Đã xóa] = 0
          AND LEFT(CAST([Ngày stock] AS TEXT), 10) >= ?
          AND LEFT(CAST([Ngày stock] AS TEXT), 10) <= ?
        ORDER BY ngay_str
    """, ('2026-05-01', '2026-05-31'))
    rows = cursor.fetchall()
    days = [int(str(r[0])[8:10]) for r in rows if r[0] and len(str(r[0])) >= 10]
    print(f"Days with data: {days}")
    print("PASS\n")
except Exception as e:
    print(f"FAIL: {e}")
    traceback.print_exc()

conn.close()
print("=== ALL TESTS DONE ===")
