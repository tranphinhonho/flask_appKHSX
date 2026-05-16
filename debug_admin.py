"""Check admin's Da xoa value in PostgreSQL"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import db

DB_URL = 'postgresql://neondb_owner:npg_MBpyCtcL27vm@ep-small-bar-a1bpplnk-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require'
db.init_db(DB_URL)

# Get ALL users without the Da xoa filter
df = db.get_columns_data(
    table_name='tbsys_Users',
    columns=['ID', 'Username', 'Fullname', 'ID_VaiTro', 'Đã xóa']
)
print("All users (no filter):")
print(df.to_string())
print(f"\nDtypes:\n{df.dtypes}")

# Check what Da xoa values look like
for _, row in df.iterrows():
    v = row['Đã xóa']
    print(f"  User={row['Username']}, Da_xoa={v!r}, type={type(v).__name__}")
