"""Fix admin's Da xoa value in PostgreSQL"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import db

DB_URL = 'postgresql://neondb_owner:npg_MBpyCtcL27vm@ep-small-bar-a1bpplnk-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require'
db.init_db(DB_URL)

# Fix: Set Da xoa to '0' for admin
db.query_database(
    'UPDATE "tbsys_Users" SET "Đã xóa" = %s WHERE "Username" = %s',
    params=('0', 'admin')
)
print("Fixed Da xoa for admin")

# Verify
df = db.get_columns_data(
    table_name='tbsys_Users',
    columns=['ID', 'Username', 'Đã xóa'],
)
print(df.to_string())
