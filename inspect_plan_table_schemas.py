import sqlite3, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

db_path = r'D:\Kê hoạch sản xuât\database_new.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

tables = ['Plan', 'DatHang', 'TonBon', 'BagStock', 'Forecast', 'PackingPlan']

for tbl in tables:
    print(f"\n=== Columns in [{tbl}] ===")
    cursor.execute(f"PRAGMA table_info([{tbl}])")
    for r in cursor.fetchall():
        print(f"  {r[1]} ({r[2]})")

conn.close()
