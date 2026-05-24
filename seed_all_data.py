# -*- coding: utf-8 -*-
"""
Kịch bản tự động nạp tất cả dữ liệu KHSX tuần W21 (18-23/05/2026) vào database_new.db
Sử dụng các lớp Importer có sẵn của ứng dụng
"""
import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime

# Đảm bảo import được config và utils từ flask_appKHSX
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import config
from utils.stock_importer import StockImporter
from utils.bag_report_importer import BagReportImporter
from utils.forecast_importer import ForecastImporter
from utils.silo_importer import SiloImporter
from utils.bacang_importer import BaCangImporter
from utils.tonbon_importer import TonBonImporter

DB_PATH = config.DATABASE_PATH
print(f"📁 Database Path: {DB_PATH}")

def seed_ffstock():
    print("\n📦 1. Đang nạp dữ liệu FFStock (Tồn kho thành phẩm) đầu tuần W21...")
    file_path = r"D:\Kê hoạch sản xuât\FSTOCK-BAG\FFSTOCK 17 -05-2026.xlsm"
    
    if not os.path.exists(file_path):
        print(f"❌ File FFStock không tồn tại tại: {file_path}")
        return False
        
    importer = StockImporter(db_path=DB_PATH)
    result = importer.import_ffstock(
        file_path=file_path,
        nguoi_import="system_seed",
        ngay_stock="2026-05-17",
        overwrite=True,
        auto_add_missing=True # Tự động điền SanPham!
    )
    
    print(f"   ✓ Nạp thành công: {result.get('success')} sản phẩm")
    print(f"   ✓ Tự động thêm sản phẩm mới: {len(result.get('auto_added', []))} sản phẩm")
    if result.get('errors'):
        print(f"   ⚠️ Lỗi: {len(result.get('errors'))}")
    return True

def seed_empty_bags():
    print("\n🎒 2. Đang nạp dữ liệu Empty Bags (Tồn kho bao bì) đầu tuần W21...")
    file_path = r"D:\Kê hoạch sản xuât\FSTOCK-BAG\DAILY STOCK EMPTY BAG REPORT  17-05-2026 .xlsm"
    
    if not os.path.exists(file_path):
        print(f"❌ File Empty Bags không tồn tại tại: {file_path}")
        return False
        
    importer = BagReportImporter(db_path=DB_PATH)
    result = importer.import_bag_report(
        file_path=file_path,
        nguoi_import="system_seed",
        ngay_stock="2026-05-17",
        overwrite=True
    )
    
    print(f"   ✓ Nạp thành công: {result.get('success')} bản ghi tồn bao bì")
    if result.get('errors'):
        print(f"   ⚠️ Lỗi: {len(result.get('errors'))}")
    return True

def seed_forecast():
    print("\n📈 3. Đang nạp dữ liệu Forecast (Dự báo bán hàng) tuần W21...")
    file_path = r"D:\Kê hoạch sản xuât\FORECAST\W21.(18-23-05-) SALEFORECAST 2026.xlsx"
    
    if not os.path.exists(file_path):
        print(f"❌ File Forecast không tồn tại tại: {file_path}")
        return False
        
    importer = ForecastImporter(db_path=DB_PATH)
    
    # Lấy danh sách sheet và chọn sheet cuối cùng (W21)
    sheets = importer.get_available_sheets(file_path)
    if not sheets:
        print("❌ Không tìm thấy sheet dự báo hợp lệ!")
        return False
        
    sheet_name = sheets[-1]
    print(f"   ✓ Sheet sử dụng: {sheet_name}")
    
    # Import dữ liệu vào bảng Forecast
    res_fc = importer.import_forecast_data(
        file_path=file_path,
        sheet_name=sheet_name,
        nguoi_import="system_seed"
    )
    print(f"   ✓ Nạp bảng Forecast: {res_fc.get('success')} dòng thành công, đã xóa {res_fc.get('deleted', 0)} dòng cũ")
    
    # Import dữ liệu chênh lệch vào bảng DatHang
    res_dh = importer.import_forecast_to_dathang(
        file_path=file_path,
        sheet_name=sheet_name,
        nguoi_import="system_seed"
    )
    print(f"   ✓ Nạp bảng DatHang (Forecast): {res_dh.get('success')} dòng thành công, đã bỏ qua {res_dh.get('skipped', 0)} dòng đã đủ từ Bá Cang/Silo")
    
    return True

def seed_silo():
    print("\n🚛 4. Đang nạp dữ liệu Xe bồn Silo tuần W21...")
    file_path = r"D:\Kê hoạch sản xuât\SILO\SILO W21-18-23-05-2026.xlsx"
    
    if not os.path.exists(file_path):
        print(f"❌ File Silo không tồn tại tại: {file_path}")
        return False
        
    importer = SiloImporter(db_path=DB_PATH)
    sheets = importer.get_available_sheets(file_path)
    if not sheets:
        print("❌ Không tìm thấy sheet silo hợp lệ!")
        return False
        
    sheet_name = sheets[-1]
    print(f"   ✓ Sheet sử dụng: {sheet_name}")
    
    result = importer.import_silo_data(
        file_path=file_path,
        sheet_name=sheet_name,
        nguoi_import="system_seed"
    )
    
    print(f"   ✓ Nạp bảng DatHang (Silo): {result.get('success')} dòng đặt hàng silo thành công")
    if result.get('not_found'):
        print(f"   ⚠️ Không tìm thấy sản phẩm cho: {len(result.get('not_found'))} mã cám")
    return True

def seed_bacang():
    print("\n🛒 5. Đang nạp dữ liệu Đại lý Võ Bá Cang tuần W21...")
    file_path = r"D:\Kê hoạch sản xuât\BACANG\KẾ HOẠCH CÁM TUẦN VÕ BÁ CANG 2026 (1).xlsx"
    
    if not os.path.exists(file_path):
        print(f"❌ File Võ Bá Cang không tồn tại tại: {file_path}")
        return False
        
    importer = BaCangImporter(db_path=DB_PATH)
    result = importer.import_bacang_data(
        file_path=file_path,
        sheet_name='TUẦN 21',
        nguoi_import="system_seed"
    )
    
    print(f"   ✓ Nạp bảng DatHang (Bá Cang): {result.get('success')} dòng đặt hàng thành công")
    if result.get('not_found'):
        print(f"   ⚠️ Không tìm thấy sản phẩm cho: {len(result.get('not_found'))} mã cám: {result.get('not_found')}")
    return True

def seed_tonbon():
    print("\n🛢️ 6. Đang nạp dữ liệu Tồn bồn ngày 17/05 (Đầu tuần W21)...")
    file_path = r"D:\Kê hoạch sản xuât\BATCHING-TONBON\Bao cao ton bon thanh pham 05.2026.xlsx"
    
    if not os.path.exists(file_path):
        print(f"❌ File Tồn bồn không tồn tại tại: {file_path}")
        return False
        
    importer = TonBonImporter(db_path=DB_PATH)
    result = importer.import_tonbon(
        file_path=file_path,
        sheet_name='17',
        ngay_kiem='2026-05-17',
        nguoi_import="system_seed",
        loai_san_pham="Thành phẩm",
        overwrite=True
    )
    
    print(f"   ✓ Nạp bảng TonBon: {result.get('success')} dòng tồn bồn thành công")
    if result.get('not_found'):
        print(f"   ⚠️ Không tìm thấy sản phẩm cho: {len(result.get('not_found'))} mã cám")
    return True

def seed_pellet_capacity():
    print("\n⚡ 7. Đang nạp dữ liệu Pellet Capacity (Năng suất 7 máy Pellet)...")
    file_path = r"D:\Kê hoạch sản xuât\data_history\Tong_hop_Pellet_Capacity_20260523_1630.xlsx"
    
    if not os.path.exists(file_path):
        print(f"❌ File tổng hợp Pellet Capacity không tồn tại tại: {file_path}")
        return False
        
    try:
        df = pd.read_excel(file_path, sheet_name='Tổng hợp Pellet Capacity', header=None)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Xóa dữ liệu cũ
        cursor.execute("DELETE FROM PelletCapacity")
        deleted = cursor.rowcount
        print(f"   ✓ Đã xóa {deleted} record Pellet Capacity cũ")
        
        success_count = 0
        not_found = []
        thoi_gian_import = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Bắt đầu duyệt từ row 4
        for idx in range(4, len(df)):
            row = df.iloc[idx]
            code_cam = str(row[1]).strip()
            so_may = str(row[2]).strip()
            
            # Sử dụng cột 3 (Công suất TB) làm T/h, cột 4 (Năng lượng TB) làm Kwh/T
            try:
                t_h = float(row[3])
                kwh_t = float(row[4]) if pd.notna(row[4]) else 0.0
                so_lo = int(row[5]) if pd.notna(row[5]) else 1
            except (ValueError, TypeError):
                continue
                
            # Tìm ID sản phẩm
            cursor.execute("SELECT ID, [Tên cám] FROM SanPham WHERE [Code cám] = ? AND [Đã xóa] = 0 LIMIT 1", (code_cam,))
            sp_row = cursor.fetchone()
            
            id_sanpham = None
            ten_cam = code_cam
            if sp_row:
                id_sanpham = sp_row[0]
                ten_cam = sp_row[1]
            else:
                # Thử tìm theo tên cám
                cursor.execute("SELECT ID, [Code cám] FROM SanPham WHERE [Tên cám] = ? AND [Đã xóa] = 0 LIMIT 1", (code_cam,))
                sp_row = cursor.fetchone()
                if sp_row:
                    id_sanpham = sp_row[0]
                    
            if not id_sanpham:
                not_found.append(code_cam)
                
            # Chèn vào bảng PelletCapacity
            cursor.execute("""
                INSERT INTO PelletCapacity 
                ([Ngày], [Số máy], [Code cám], [Tên cám], [T/h], [Kwh/T], 
                 [ID sản phẩm], [Số lô], [Nguồn file], [Thời gian import], [Người import], [Đã xóa])
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                '2026-05-23', # Ngày xuất báo cáo
                so_may,
                code_cam,
                ten_cam,
                t_h,
                kwh_t,
                id_sanpham,
                so_lo,
                os.path.basename(file_path),
                thoi_gian_import,
                'system_seed'
            ))
            success_count += 1
            
        conn.commit()
        conn.close()
        
        print(f"   ✓ Nạp thành công: {success_count} dòng năng suất máy ép viên")
        if not_found:
            print(f"   ⚠️ Không tìm thấy sản phẩm trong danh mục cho {len(set(not_found))} mã cám: {list(set(not_found))[:5]}...")
            
        return True
    except Exception as e:
        print(f"❌ Lỗi nạp Pellet Capacity: {e}")
        return False

def main():
    print("=" * 60)
    print("🚀 BẮT ĐẦU TỰ ĐỘNG NẠP DỮ LIỆU KHSX TUẦN W21")
    print("=" * 60)
    
    start_time = datetime.now()
    
    # 1. FFStock (SanPham + StockOld)
    if not seed_ffstock():
        print("❌ Lỗi nghiêm trọng tại bước 1. Dừng kịch bản!")
        return
        
    # 2. Empty Bags (BagStock)
    seed_empty_bags()
    
    # 3. Forecast
    seed_forecast()
    
    # 4. Silo
    seed_silo()
    
    # 5. Ba Cang
    seed_bacang()
    
    # 6. TonBon
    seed_tonbon()
    
    # 7. Pellet Capacity
    seed_pellet_capacity()
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print("\n" + "=" * 60)
    print(f"🎉 HOÀN THÀNH TỰ ĐỘNG NẠP DỮ LIỆU TRONG {duration:.2f} GIÂY!")
    print("=" * 60)

if __name__ == '__main__':
    main()
