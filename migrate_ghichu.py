import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend import db

db.init_db('database_new.db')
conn = db.connect_db()
cursor = conn.cursor()

sql = (
    "CREATE TABLE IF NOT EXISTS [GhiChu] ("
    "[ID] INTEGER PRIMARY KEY AUTOINCREMENT, "
    "[TieuDe] TEXT, [NoiDung] TEXT, [LoaiVanDe] TEXT, "
    "[MucDo] TEXT, [TrangThai] TEXT DEFAULT 'Cho xu ly', "
    "[HinhAnh] TEXT, [ThoiGianTao] TEXT, [NguoiTao] TEXT, "
    "[ThoiGianSua] TEXT, [NguoiSua] TEXT, [Da xoa] INTEGER DEFAULT 0)"
)
cursor.execute(sql)
conn.commit()
cursor.execute("SELECT COUNT(*) FROM [GhiChu]")
print("GhiChu table OK, rows:", cursor.fetchone()[0])
conn.close()
print("Migration done!")
