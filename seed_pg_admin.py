"""Add admin user to PostgreSQL database"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import db
from backend.utils import hashpw, get_vietnam_time

# Connect to PostgreSQL
DB_URL = os.environ.get('DATABASE_URL', 'postgresql://neondb_owner:npg_MBpyCtcL27vm@ep-small-bar-a1bpplnk-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require')
db.init_db(DB_URL)
print(f"Connected to: {db._db_type}")

# Check existing admin
existing = db.get_columns_data(
    table_name='tbsys_Users',
    columns=['ID', 'Username', 'Fullname', 'ID_VaiTro'],
    col_where={'Username': ('=', 'admin')}
)
print(f"Existing admin entries:\n{existing}")

# Get phinho's role
phinho_role = db.get_columns_data(
    table_name='tbsys_Users',
    columns=['ID_VaiTro'],
    data_type='value',
    col_where={'Username': ('=', 'phinho')}
)
print(f"Phinho role: {phinho_role}")

if len(sys.argv) >= 3:
    username = sys.argv[1]
    password = sys.argv[2]
    fullname = sys.argv[3] if len(sys.argv) > 3 else 'Admin'
else:
    username = 'admin'
    password = '2810'
    fullname = 'Admin'

role_id = phinho_role if phinho_role else 1

if existing.empty:
    hashed = hashpw(password)
    now_str = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')
    cols = ['Username', 'Password', 'Fullname', 'ID_VaiTro', 'Người tạo', 'Thời gian tạo']
    vals = [username, hashed, fullname, role_id, 'system', now_str]
    result = db.insert_data_to_table('tbsys_Users', cols, vals)
    print(f"Insert result: {result}")
else:
    print("Admin already exists, updating password...")
    admin_id = existing.iloc[0]['ID']
    hashed = hashpw(password)
    result = db.update_data_by_id('tbsys_Users', admin_id, {'Password': hashed}, 'system')
    print(f"Update result: {result}")

# Verify
final = db.get_columns_data(
    table_name='tbsys_Users',
    columns=['ID', 'Username', 'Fullname', 'ID_VaiTro'],
    col_where={'Username': ('=', 'admin')}
)
print(f"\nFinal admin record:\n{final}")
