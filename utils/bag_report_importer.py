"""
Module import dữ liệu từ file DAILY STOCK EMPTY BAG REPORT vào database
Đọc từ sheet MAP: cột B (Tên cám), D (Kích cỡ đóng bao), G (Số lượng bao bì)
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import re
from utils import get_db_connection, is_postgres, q, ph


class BagReportImporter:
    """Class xử lý import BAG REPORT vào database"""
    
    # Cấu hình sheet nguồn
    SHEET_MAP = "MAP"
    
    # Hàng bắt đầu dữ liệu (0-indexed, hàng 2 trong Excel)
    START_ROW = 1
    
    # Mapping cột (0-indexed: A=0, B=1, ...)
    COL_MAPPING = {
        'ten_cam': 1,         # Cột B - Tên cám
        'kich_co_bao': 3,     # Cột D - Kích cỡ đóng bao (25/40/50)
        'so_luong': 6,        # Cột G - Số lượng bao bì tồn
    }
    
    def __init__(self, db_path: str = "database_new.db"):
        """
        Khởi tạo BagReportImporter
        
        Args:
            db_path: Đường dẫn database SQLite hoặc PostgreSQL URL
        """
        self.db_path = db_path
        self._is_pg = is_postgres(db_path)
    
    def _get_connection(self):
        """Tạo connection đến database (SQLite hoặc PostgreSQL)"""
        return get_db_connection(self.db_path)
    
    def _ph(self) -> str:
        return ph(self.db_path)
    
    def _ensure_tables(self):
        """Tạo các bảng cần thiết nếu chưa có"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Bảng BagStock
        if self._is_pg:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS "BagStock" (
                    "ID" SERIAL PRIMARY KEY,
                    "NgayStock" DATE NOT NULL,
                    "TenCam" TEXT NOT NULL,
                    "KichCoDongBao" INTEGER,
                    "SoLuongBaoBi" INTEGER,
                    "TenFile" TEXT,
                    "NguoiTao" TEXT,
                    "ThoiGianTao" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    "DaXoa" INTEGER DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS "EmailImportLog" (
                    "ID" SERIAL PRIMARY KEY,
                    "TenFile" TEXT NOT NULL UNIQUE,
                    "NgayEmail" DATE,
                    "LoaiFile" TEXT NOT NULL,
                    "SoLuongDong" INTEGER DEFAULT 0,
                    "ThoiGianImport" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    "NguoiImport" TEXT
                )
            """)
        else:
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS EmailImportLog (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    TenFile TEXT NOT NULL UNIQUE,
                    NgayEmail DATE,
                    LoaiFile TEXT NOT NULL,
                    SoLuongDong INTEGER DEFAULT 0,
                    ThoiGianImport DATETIME DEFAULT CURRENT_TIMESTAMP,
                    NguoiImport TEXT
                )
            """)
        
        conn.commit()
        conn.close()
    
    def check_duplicate(self, filename: str) -> bool:
        """
        Kiểm tra file đã được import chưa
        
        Returns:
            True nếu đã import (duplicate)
        """
        self._ensure_tables()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            f'SELECT "ID" FROM "EmailImportLog" WHERE "TenFile" = {self._ph()} AND "LoaiFile" = \'BAG_REPORT\'',
            (filename,)
        )
        
        result = cursor.fetchone()
        conn.close()
        
        return result is not None
    
    def _log_import(
        self, 
        filename: str, 
        so_luong: int,
        ngay_email: Optional[str] = None,
        nguoi_import: Optional[str] = None
    ):
        """Ghi log import vào database"""
        self._ensure_tables()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        _p = self._ph()
        cursor.execute(f"""
            INSERT INTO "EmailImportLog" 
            ("TenFile", "NgayEmail", "LoaiFile", "SoLuongDong", "NguoiImport")
            VALUES ({_p}, {_p}, 'BAG_REPORT', {_p}, {_p})
        """, (filename, ngay_email, so_luong, nguoi_import))
        
        conn.commit()
        conn.close()
    
    def _delete_old_import(self, filename: str):
        """Xóa dữ liệu import cũ trước khi import lại"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Lấy ngày từ log cũ
        _p = self._ph()
        cursor.execute(f"""
            SELECT "NgayEmail" FROM "EmailImportLog" 
            WHERE "TenFile" = {_p} AND "LoaiFile" = 'BAG_REPORT'
        """, (filename,))
        result = cursor.fetchone()
        
        if result:
            ngay_email = result[0]
            
            # Xóa mềm BagStock
            _p = self._ph()
            cursor.execute(f"""
                UPDATE "BagStock" 
                SET "DaXoa" = 1
                WHERE "NgayStock" = {_p} AND "TenFile" = {_p}
            """, (ngay_email, filename))
            
            deleted_count = cursor.rowcount
            print(f"🗑️ Đã xóa mềm {deleted_count} record BagStock cũ")
            
            # Xóa log import cũ
            cursor.execute(f"""
                DELETE FROM "EmailImportLog" 
                WHERE "TenFile" = {self._ph()} AND "LoaiFile" = 'BAG_REPORT'
            """, (filename,))
        
        conn.commit()
        conn.close()
    
    def extract_date_from_filename(self, filename: str) -> Optional[str]:
        """
        Trích xuất ngày từ tên file
        Ví dụ: DAILY STOCK EMPTY BAG REPORT  10-01-2026  .xlsm → 2026-01-10
        
        Returns:
            Date string format YYYY-MM-DD hoặc None
        """
        match = re.search(r'(\d{1,2})-(\d{1,2})-(\d{4})', filename)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return None
    
    def preview_data(
        self, 
        file_path: str | Path,
        limit: int = 20
    ) -> Optional[pd.DataFrame]:
        """
        Preview dữ liệu trong file BAG REPORT trước khi import
        
        Args:
            file_path: Đường dẫn file Excel
            limit: Số dòng tối đa hiển thị
            
        Returns:
            DataFrame preview hoặc None nếu lỗi
        """
        file_path = Path(file_path)
        
        try:
            # Đọc sheet MAP
            df = pd.read_excel(
                file_path,
                sheet_name=self.SHEET_MAP,
                header=None,
                skiprows=self.START_ROW
            )
            
            data = []
            for idx, row in df.iterrows():
                if idx >= limit:
                    break
                    
                # Lấy tên cám
                ten_cam = row.iloc[self.COL_MAPPING['ten_cam']]
                if pd.isna(ten_cam) or str(ten_cam).strip() == "":
                    continue
                ten_cam = str(ten_cam).strip()
                
                # Lấy kích cỡ đóng bao
                kich_co_bao = row.iloc[self.COL_MAPPING['kich_co_bao']]
                try:
                    kich_co_bao = int(float(kich_co_bao))
                except:
                    kich_co_bao = 0
                
                # Lấy số lượng
                so_luong = row.iloc[self.COL_MAPPING['so_luong']]
                try:
                    so_luong = int(float(so_luong))
                except:
                    so_luong = 0
                
                if so_luong > 0:
                    data.append({
                        'Tên cám': ten_cam,
                        'Kích cỡ (kg)': kich_co_bao,
                        'Số lượng': so_luong
                    })
            
            if not data:
                return None
            
            return pd.DataFrame(data)
            
        except Exception as e:
            print(f"❌ Lỗi preview: {e}")
            return None
    
    def import_bag_report(
        self,
        file_path: str | Path,
        nguoi_import: str = "system",
        ngay_stock: Optional[str] = None,
        overwrite: bool = False
    ) -> Dict:
        """
        Import file BAG REPORT vào database BagStock
        
        Args:
            file_path: Đường dẫn file Excel
            nguoi_import: Username người import
            ngay_stock: Ngày stock (YYYY-MM-DD), mặc định trích từ tên file
            overwrite: Nếu True, xóa dữ liệu cũ trước khi import lại
            
        Returns:
            Dict kết quả: {success, errors, skipped}
        """
        file_path = Path(file_path)
        filename = file_path.name
        
        # Kiểm tra trùng lặp
        is_duplicate = self.check_duplicate(filename)
        
        if is_duplicate and not overwrite:
            return {
                'success': 0,
                'errors': [f"File '{filename}' đã được import trước đó"],
                'skipped': True
            }
        
        # Nếu overwrite, xóa dữ liệu cũ
        if is_duplicate and overwrite:
            self._delete_old_import(filename)
        
        # Trích xuất ngày từ tên file
        if not ngay_stock:
            ngay_stock = self.extract_date_from_filename(filename)
            if not ngay_stock:
                ngay_stock = datetime.now().strftime('%Y-%m-%d')
        
        # Đọc dữ liệu từ sheet MAP
        try:
            df = pd.read_excel(
                file_path,
                sheet_name=self.SHEET_MAP,
                header=None,
                skiprows=self.START_ROW
            )
            print(f"✅ Đọc được {len(df)} dòng từ sheet MAP")
        except Exception as e:
            return {
                'success': 0,
                'errors': [f"Lỗi đọc file Excel: {e}"],
                'skipped': False
            }
        
        # Parse và import
        conn = self._get_connection()
        cursor = conn.cursor()
        self._ensure_tables()
        
        success_count = 0
        errors = []
        thoi_gian_tao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        for idx, row in df.iterrows():
            try:
                # Lấy tên cám (cột B)
                ten_cam = row.iloc[self.COL_MAPPING['ten_cam']]
                if pd.isna(ten_cam) or str(ten_cam).strip() == "":
                    continue
                ten_cam = str(ten_cam).strip()
                
                # Lấy kích cỡ đóng bao (cột D)
                kich_co_bao = row.iloc[self.COL_MAPPING['kich_co_bao']]
                try:
                    kich_co_bao = int(float(kich_co_bao))
                except:
                    kich_co_bao = 0
                
                # Lấy số lượng (cột G)
                so_luong = row.iloc[self.COL_MAPPING['so_luong']]
                try:
                    so_luong = int(float(so_luong))
                except:
                    so_luong = 0
                
                # Bỏ qua nếu số lượng <= 0
                if so_luong <= 0:
                    continue
                
                # Insert vào BagStock
                _p = self._ph()
                cursor.execute(f"""
                    INSERT INTO "BagStock" 
                    ("NgayStock", "TenCam", "KichCoDongBao", "SoLuongBaoBi", 
                     "TenFile", "NguoiTao", "ThoiGianTao", "DaXoa")
                    VALUES ({_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, 0)
                """, (
                    ngay_stock,
                    ten_cam,
                    kich_co_bao,
                    so_luong,
                    filename,
                    nguoi_import,
                    thoi_gian_tao
                ))
                
                success_count += 1
                
            except Exception as e:
                errors.append(f"Dòng {idx+2}: {e}")
        
        conn.commit()
        conn.close()
        
        # Ghi log import
        if success_count > 0:
            self._log_import(
                filename=filename,
                so_luong=success_count,
                ngay_email=ngay_stock,
                nguoi_import=nguoi_import
            )
        
        print(f"✅ Import thành công: {success_count} dòng")
        if errors:
            print(f"⚠️ Có {len(errors)} lỗi")
        
        return {
            'success': success_count,
            'errors': errors,
            'skipped': False,
            'ngay_stock': ngay_stock
        }
    
    def get_import_history(self, limit: int = 20) -> List[Dict]:
        """Lấy lịch sử import BAG_REPORT"""
        self._ensure_tables()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(f"""
            SELECT "ID", "TenFile", "NgayEmail", "SoLuongDong", 
                   "ThoiGianImport", "NguoiImport"
            FROM "EmailImportLog"
            WHERE "LoaiFile" = 'BAG_REPORT'
            ORDER BY "ThoiGianImport" DESC
            LIMIT {self._ph()}
        """, (limit,))
        
        columns = ['ID', 'TenFile', 'NgayEmail', 'SoLuongDong', 
                   'ThoiGianImport', 'NguoiImport']
        
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        conn.close()
        return results


def test_bag_report_importer():
    """Test function"""
    print("=" * 60)
    print("🔍 TEST BAG REPORT IMPORTER")
    print("=" * 60)
    
    importer = BagReportImporter()
    
    # Test với file mẫu
    test_file = Path("D:/PYTHON/B7KHSX/EXCEL/DAILY STOCK EMPTY BAG REPORT  10-01-2026  .xlsm")
    
    if not test_file.exists():
        print(f"❌ File test không tồn tại: {test_file}")
        return
    
    print(f"\n📁 File: {test_file}")
    print(f"📊 Database: {importer.db_path}")
    
    # Kiểm tra duplicate
    if importer.check_duplicate(test_file.name):
        print(f"\n⚠️ File đã được import trước đó!")
        print("Sử dụng overwrite=True để import lại")
        return
    
    print("\n🚀 Bắt đầu import...")
    result = importer.import_bag_report(
        file_path=test_file,
        nguoi_import="test_user"
    )
    
    print(f"\n📊 KẾT QUẢ:")
    print(f"   ✅ Thành công: {result['success']}")
    print(f"   ❌ Lỗi: {len(result['errors'])}")
    print(f"   📅 Ngày stock: {result.get('ngay_stock')}")


if __name__ == "__main__":
    test_bag_report_importer()
