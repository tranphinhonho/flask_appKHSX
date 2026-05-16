"""
Seed admin user into database.
Run once: python seed_admin.py
Usage: python seed_admin.py <username> <password> <fullname>

This script is NOT committed to git - add to .gitignore.
"""
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import db
from backend.utils import hashpw, get_vietnam_time

# Initialize database
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'database_new.db')
db_path = os.path.abspath(db_path)
if os.path.exists(db_path):
    db.init_db(db_path)
else:
    print(f"Database not found at: {db_path}")
    sys.exit(1)


def seed_user(username, password, fullname, id_vaitro=1):
    """Add a user to tbsys_Users if not exists"""
    # Check if user already exists
    existing = db.get_columns_data(
        table_name='tbsys_Users',
        columns=['Username'],
        data_type='value',
        col_where={'Username': ('=', username), 'Đã xóa': ('=', 0)}
    )

    if existing:
        print(f"User '{username}' already exists. Updating password...")
        now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')
        result = db.query_database(
            "UPDATE tbsys_Users SET [Password] = ?, [Thời gian sửa] = ? WHERE LOWER([Username]) = LOWER(?) AND [Đã xóa] = 0",
            params=(hashpw(password), now, username)
        )
        print(f"Password updated for '{username}'")
        return

    hashed = hashpw(password)
    now = get_vietnam_time()

    cols = ['Username', 'Password', 'Fullname', 'ID_VaiTro',
            'Người tạo', 'Thời gian tạo']
    vals = [username, hashed, fullname, id_vaitro,
            'system', now.strftime('%Y-%m-%d %H:%M:%S')]

    result = db.insert_data_to_table('tbsys_Users', cols, vals)
    if result.get('success'):
        print(f"[OK] User '{username}' created successfully (role ID: {id_vaitro})")
    else:
        print(f"[ERROR] Error creating user: {result.get('message')}")


if __name__ == '__main__':
    if len(sys.argv) >= 3:
        username = sys.argv[1]
        password = sys.argv[2]
        fullname = sys.argv[3] if len(sys.argv) > 3 else username.title()
    else:
        print("Usage: python seed_admin.py <username> <password> [fullname]")
        print("Example: python seed_admin.py admin mypassword Admin")
        sys.exit(1)

    # Get phinho's role ID to match permissions
    phinho_role = db.get_columns_data(
        table_name='tbsys_Users',
        columns=['ID_VaiTro'],
        data_type='value',
        col_where={'Username': ('=', 'phinho'), 'Đã xóa': ('=', 0)}
    )

    role_id = phinho_role if phinho_role else 1
    print(f"Using role ID: {role_id} (same as phinho)")

    seed_user(username, password, fullname, role_id)
