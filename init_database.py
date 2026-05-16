"""
Script khởi tạo database SQLite với các bảng hệ thống cần thiết
và tạo user admin mặc định.
"""
import sqlite3
import bcrypt
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database_new.db')
print(f"Database path: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# ===== 1. Bảng tbsys_Users =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS tbsys_Users (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    Username TEXT NOT NULL,
    Password TEXT NOT NULL,
    Fullname TEXT,
    ID_VaiTro TEXT,
    [Đã xóa] INTEGER DEFAULT 0,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT
)
""")

# ===== 2. Bảng tbsys_ChucNangChinh =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS tbsys_ChucNangChinh (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [Chức năng chính] TEXT,
    [Thứ tự ưu tiên] INTEGER,
    Icon TEXT,
    [Đã xóa] INTEGER DEFAULT 0,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT
)
""")

# ===== 3. Bảng tbsys_DanhSachChucNang =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS tbsys_DanhSachChucNang (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [ID Chức năng chính] TEXT,
    [Chức năng con] TEXT,
    [Thứ tự ưu tiên] INTEGER,
    [Đã xóa] INTEGER DEFAULT 0,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT
)
""")

# ===== 4. Bảng tbsys_ChucNangTheoVaiTro =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS tbsys_ChucNangTheoVaiTro (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [ID Vai trò] TEXT,
    [ID Danh sách chức năng] TEXT,
    [Đã xóa] INTEGER DEFAULT 0,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT
)
""")

# ===== 5. Bảng tbsys_VaiTro =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS tbsys_VaiTro (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [Vai trò] TEXT,
    [Đã xóa] INTEGER DEFAULT 0,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT
)
""")

# ===== 6. Bảng tbsys_ModuleChucNang =====
cursor.execute("""
CREATE TABLE IF NOT EXISTS tbsys_ModuleChucNang (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_DanhSachChucNang TEXT,
    ModulePath TEXT,
    [Đã xóa] INTEGER DEFAULT 0,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT
)
""")

# ===== Tạo vai trò Admin =====
cursor.execute("SELECT COUNT(*) FROM tbsys_VaiTro WHERE [Vai trò] = 'Admin'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO tbsys_VaiTro ([Vai trò]) VALUES ('Admin')")
    print("✅ Đã tạo vai trò 'Admin'")

# Lấy ID vai trò Admin
cursor.execute("SELECT ID FROM tbsys_VaiTro WHERE [Vai trò] = 'Admin' AND [Đã xóa] = 0")
admin_role_id = str(cursor.fetchone()[0])

# ===== Tạo user phinho =====
cursor.execute("SELECT COUNT(*) FROM tbsys_Users WHERE Username = 'phinho'")
if cursor.fetchone()[0] == 0:
    hashed_pw = bcrypt.hashpw('nho123'.encode(), bcrypt.gensalt()).decode()
    cursor.execute(
        "INSERT INTO tbsys_Users (Username, Password, Fullname, ID_VaiTro) VALUES (?, ?, ?, ?)",
        ('phinho', hashed_pw, 'Phan Phin Ho', admin_role_id)
    )
    print(f"✅ Đã tạo user 'phinho' với password 'nho123' (bcrypt hash)")
    print(f"   Hash: {hashed_pw}")
else:
    print("ℹ️  User 'phinho' đã tồn tại")

# ===== Tạo chức năng chính mẫu =====
sample_functions = [
    ('Kế hoạch sản xuất', 1, 'calendar-check'),
    ('Quản lý kho', 2, 'box-seam'),
    ('Báo cáo', 3, 'file-earmark-bar-graph'),
]

for func_name, priority, icon in sample_functions:
    cursor.execute("SELECT COUNT(*) FROM tbsys_ChucNangChinh WHERE [Chức năng chính] = ?", (func_name,))
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO tbsys_ChucNangChinh ([Chức năng chính], [Thứ tự ưu tiên], Icon) VALUES (?, ?, ?)",
            (func_name, priority, icon)
        )

# ===== Tạo chức năng con mẫu =====
sub_functions = [
    ('1', 'Đặt hàng', 1),
    ('1', 'Lịch tháng', 2),
    ('1', 'Sản phẩm', 3),
    ('2', 'Tồn bồn', 1),
    ('2', 'Packing Plan', 2),
    ('2', 'Stock hôm nay', 3),
]

for main_id, sub_name, priority in sub_functions:
    cursor.execute("SELECT COUNT(*) FROM tbsys_DanhSachChucNang WHERE [Chức năng con] = ?", (sub_name,))
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO tbsys_DanhSachChucNang ([ID Chức năng chính], [Chức năng con], [Thứ tự ưu tiên]) VALUES (?, ?, ?)",
            (main_id, sub_name, priority)
        )

# ===== Gán chức năng cho vai trò Admin =====
cursor.execute("SELECT ID FROM tbsys_DanhSachChucNang WHERE [Đã xóa] = 0")
all_func_ids = cursor.fetchall()

for func_id in all_func_ids:
    fid = str(func_id[0])
    cursor.execute(
        "SELECT COUNT(*) FROM tbsys_ChucNangTheoVaiTro WHERE [ID Vai trò] = ? AND [ID Danh sách chức năng] = ?",
        (admin_role_id, fid)
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO tbsys_ChucNangTheoVaiTro ([ID Vai trò], [ID Danh sách chức năng]) VALUES (?, ?)",
            (admin_role_id, fid)
        )

# ===== Tạo module paths mẫu =====
module_mappings = {
    'Đặt hàng': 'DatHang.DatHang',
    'Lịch tháng': 'LichThang.LichThang',
    'Sản phẩm': 'SanPham.SanPham',
    'Tồn bồn': 'TonBon.TonBon',
    'Packing Plan': 'PackingPlan.PackingPlan',
    'Stock hôm nay': 'StockHomNay.StockHomNay',
}

for sub_name, module_path in module_mappings.items():
    cursor.execute("SELECT ID FROM tbsys_DanhSachChucNang WHERE [Chức năng con] = ? AND [Đã xóa] = 0", (sub_name,))
    row = cursor.fetchone()
    if row:
        fid = str(row[0])
        cursor.execute(
            "SELECT COUNT(*) FROM tbsys_ModuleChucNang WHERE ID_DanhSachChucNang = ? AND [Đã xóa] = 0",
            (fid,)
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO tbsys_ModuleChucNang (ID_DanhSachChucNang, ModulePath) VALUES (?, ?)",
                (fid, module_path)
            )

conn.commit()

# ===== Kiểm tra kết quả =====
print("\n=== Kết quả khởi tạo ===")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
print(f"Số bảng: {len(tables)}")
for t in tables:
    cursor.execute(f"SELECT COUNT(*) FROM [{t[0]}]")
    count = cursor.fetchone()[0]
    print(f"  - {t[0]}: {count} bản ghi")

cursor.execute("SELECT Username, Fullname, ID_VaiTro, [Đã xóa] FROM tbsys_Users")
users = cursor.fetchall()
print(f"\nUsers:")
for u in users:
    print(f"  - {u[0]} ({u[1]}) | Vai trò ID: {u[2]} | Xóa: {u[3]}")

conn.close()
print("\n✅ Khởi tạo database hoàn tất!")
