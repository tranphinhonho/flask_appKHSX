"""
Script khởi tạo 15 bảng dữ liệu KHSX cốt lõi cho web app
Sử dụng cấu hình DB từ config.py
"""
import sqlite3
import os
import sys

# Thêm thư mục hiện tại vào sys.path để import config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

DB_PATH = config.DATABASE_PATH
print(f"📁 Đang kết nối database tại: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 1. Bảng SanPham
cursor.execute("""
CREATE TABLE IF NOT EXISTS SanPham (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [Code cám] TEXT,
    [Tên cám] TEXT,
    [Kích cỡ ép viên] TEXT,
    [Dạng ép viên] TEXT,
    [Kích cỡ đóng bao] INTEGER,
    [Pellet] TEXT,
    [Packing] TEXT,
    [Batch size] REAL,
    [Vật nuôi] TEXT,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: SanPham")

# 2. Bảng DatHang
cursor.execute("""
CREATE TABLE IF NOT EXISTS DatHang (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [ID sản phẩm] INTEGER,
    [Mã đặt hàng] TEXT,
    [Số lượng] REAL,
    [Ngày đặt] TEXT,
    [Ngày lấy] TEXT,
    [Loại đặt hàng] TEXT,
    [Khách vãng lai] INTEGER DEFAULT 0,
    [Ghi chú] TEXT,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: DatHang")

# 3. Bảng Plan
cursor.execute("""
CREATE TABLE IF NOT EXISTS Plan (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [ID sản phẩm] INTEGER,
    [Mã plan] TEXT,
    [Số lượng] REAL,
    [Ngày plan] TEXT,
    [Ghi chú] TEXT,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: Plan")

# 4. Bảng Sale
cursor.execute("""
CREATE TABLE IF NOT EXISTS Sale (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [ID sản phẩm] INTEGER,
    [Mã sale] TEXT,
    [Số lượng] REAL,
    [Ngày sale] TEXT,
    [Ghi chú] TEXT,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: Sale")

# 5. Bảng Packing
cursor.execute("""
CREATE TABLE IF NOT EXISTS Packing (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [ID sản phẩm] INTEGER,
    [Mã packing] TEXT,
    [Số lượng] REAL,
    [Ngày packing] TEXT,
    [Ghi chú] TEXT,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: Packing")

# 6. Bảng Mixer (Batching)
cursor.execute("""
CREATE TABLE IF NOT EXISTS Mixer (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [Mã mixer] TEXT,
    [Ngày trộn] TEXT,
    [ID sản phẩm] INTEGER,
    [Batch size] REAL,
    [Số lượng thực tế] REAL,
    [Loss (kg)] REAL,
    [Loss (%)] REAL,
    [Đích đến] TEXT,
    [Số máy] TEXT,
    [Ca sản xuất] TEXT,
    [Ghi chú] TEXT,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: Mixer")

# 7. Bảng StockOld
cursor.execute("""
CREATE TABLE IF NOT EXISTS StockOld (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [ID sản phẩm] INTEGER,
    [Mã stock old] TEXT,
    [Số lượng] REAL,
    [Ngày stock old] TEXT,
    [Ghi chú] TEXT,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: StockOld")

# 8. Bảng StockHomNay
cursor.execute("""
CREATE TABLE IF NOT EXISTS StockHomNay (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [ID sản phẩm] INTEGER,
    [Mã stock] TEXT,
    [Số lượng] REAL,
    [Ngày stock] TEXT,
    [Ghi chú] TEXT,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: StockHomNay")

# 9. Bảng TonBon
cursor.execute("""
CREATE TABLE IF NOT EXISTS TonBon (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [ID sản phẩm] INTEGER,
    [Mã tồn bồn] TEXT,
    [Số bồn] INTEGER,
    [Số lượng (kg)] REAL,
    [Ngày kiểm kho] TEXT,
    [Loại bồn] TEXT,
    [Loại sản phẩm] TEXT,
    [Trạng thái] TEXT,
    [Kích cỡ đóng bao] TEXT,
    [Ca sản xuất] TEXT,
    [Ghi chú] TEXT,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: TonBon")

# 10. Bảng BaoBi
cursor.execute("""
CREATE TABLE IF NOT EXISTS BaoBi (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [Ngày kiểm tra] TEXT,
    [Loại bao] TEXT,
    [Kích cỡ (kg)] INTEGER,
    [Tồn kho hiện tại] REAL,
    [Nhu cầu dự kiến] REAL,
    [Số lượng thiếu] REAL,
    [Mức cảnh báo] TEXT,
    [Ghi chú] TEXT,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: BaoBi")

# 11. Bảng BagStock (Tồn kho bao bì chi tiết từ excel)
cursor.execute("""
CREATE TABLE IF NOT EXISTS BagStock (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    NgayStock DATE NOT NULL,
    TenCam TEXT NOT NULL,
    KichCoDongBao INTEGER,
    SoLuongBaoBi INTEGER,
    TenFile TEXT,
    NguoiTao TEXT,
    ThoiGianTao DATETIME DEFAULT CURRENT_TIMESTAMP,
    DaXoa INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: BagStock")

# 12. Bảng Forecast
cursor.execute("""
CREATE TABLE IF NOT EXISTS Forecast (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [ID sản phẩm] INTEGER,
    [Mã forecast] TEXT,
    [Số lượng tấn] REAL,
    [Tuần] INTEGER,
    [Ngày bắt đầu] DATE,
    [Ngày kết thúc] DATE,
    [Ghi chú] TEXT,
    [Người tạo] TEXT,
    [Thời gian tạo] DATETIME DEFAULT CURRENT_TIMESTAMP,
    [Người sửa] TEXT,
    [Thời gian sửa] DATETIME,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: Forecast")

# 13. Bảng PelletCapacity (Năng suất máy pellet)
cursor.execute("""
CREATE TABLE IF NOT EXISTS PelletCapacity (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [Ngày] DATE,
    [Số máy] TEXT,
    [Code cám] TEXT,
    [Tên cám] TEXT,
    [T/h] REAL,
    [Kwh/T] REAL,
    [Thông số khuôn] TEXT,
    [ID sản phẩm] INTEGER,
    [Số lô] INTEGER DEFAULT 1,
    [Nguồn file] TEXT,
    [Thời gian import] DATETIME,
    [Người import] TEXT,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: PelletCapacity")

# 14. Bảng PelletPlan (Kế hoạch sản xuất pellet)
cursor.execute("""
CREATE TABLE IF NOT EXISTS PelletPlan (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [Ngày plan] DATE,
    [Số máy] TEXT,
    [Ca] TEXT,
    [Code cám] TEXT,
    [Số mẻ] REAL,
    [Số lượng (tons)] REAL,
    [Số giờ] REAL,
    [T/h] REAL,
    [Người tạo] TEXT,
    [Thời gian tạo] DATETIME,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: PelletPlan")

# 15. Bảng PackingPlan (Kế hoạch đóng bao)
cursor.execute("""
CREATE TABLE IF NOT EXISTS PackingPlan (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    [Ngày đóng bao] TEXT,
    [ID sản phẩm] INTEGER,
    [Số lượng (tấn)] REAL,
    [Kích cỡ bao (kg)] INTEGER,
    [Số bao] INTEGER,
    [Line đóng bao] TEXT,
    [Thời gian bắt đầu] TEXT,
    [Thời gian kết thúc] TEXT,
    [Ghi chú] TEXT,
    [Người tạo] TEXT,
    [Thời gian tạo] TEXT,
    [Người sửa] TEXT,
    [Thời gian sửa] TEXT,
    [Đã xóa] INTEGER DEFAULT 0
)
""")
print("✅ Đã khởi tạo bảng: PackingPlan")

conn.commit()
conn.close()
print("\n🎉 Khởi tạo 15 bảng KHSX cốt lõi thành công!")
