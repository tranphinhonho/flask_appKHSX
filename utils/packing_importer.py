"""
Module import dữ liệu Packing từ file Excel DAILY PACKING
Parse dữ liệu từ các sheet theo ngày (1, 2, 3, ..., 31)
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
from utils import get_db_connection, is_postgres, q, ph


class PackingImporter:
    """Class xử lý import dữ liệu Packing từ file Excel DAILY PACKING"""
    
    # Default file path
    DEFAULT_FILE = "EXCEL/DAILY PACKING THANG 1.2026.xlsm"
    
    # Column mapping (0-indexed)
    COL_TEN_CAM = 21      # Cột V - Tên cám (code)
    COL_KICH_CO_BAO = 7   # Cột H - Kích cỡ đóng bao
    COL_SO_LUONG_BAO = 14 # Cột O - Số lượng bao
    COL_SO_LUONG_KG = 15  # Cột P - Số lượng kg
    
    # Start row (0-indexed, data starts from row 3 in Excel = row 2 in pandas)
    START_ROW = 2
    
    def __init__(self, db_path: str = "database_new.db"):
        self.db_path = db_path
        self._is_pg = is_postgres(db_path)
    
    def _get_connection(self):
        return get_db_connection(self.db_path)
    
    def _q(self, name: str) -> str:
        return q(name, self.db_path)
    
    def _ph(self) -> str:
        return ph(self.db_path)
    
    def _da_xoa_check(self, val='0') -> str:
        if self._is_pg:
            return f'{self._q("Đã xóa")}::integer = {val}'
        else:
            return f'{self._q("Đã xóa")} = {val}'
    
    def get_available_sheets(self, file_path: str | Path = None) -> List[str]:
        """
        Lấy danh sách các sheet (ngày) có sẵn trong file Excel
        
        Args:
            file_path: Đường dẫn file Excel
            
        Returns:
            List các tên sheet
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
            
        xl = pd.ExcelFile(file_path)
        # Chỉ lấy các sheet là số (ngày)
        day_sheets = [s for s in xl.sheet_names if s.isdigit()]
        return sorted(day_sheets, key=lambda x: int(x))
    
    def get_excel_total(
        self, 
        file_path: str | Path = None, 
        sheet_name: str = "1"
    ) -> Optional[float]:
        """
        Lấy giá trị tổng sản lượng từ ô P2 trong Excel
        
        Args:
            file_path: Đường dẫn file Excel
            sheet_name: Tên sheet (ngày)
            
        Returns:
            Giá trị tổng từ ô P2 hoặc None nếu không có
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
        
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
            # Ô P2 = row index 1, column index 15
            value = df.iloc[1, 15]
            if pd.notna(value):
                return float(value)
            return None
        except Exception:
            return None
    
    def preview_data(
        self, 
        file_path: str | Path = None, 
        sheet_name: str = "1",
        limit: int = 10
    ) -> pd.DataFrame:
        """
        Xem trước dữ liệu từ một sheet
        
        Args:
            file_path: Đường dẫn file Excel
            sheet_name: Tên sheet (ngày)
            limit: Số dòng tối đa hiển thị
            
        Returns:
            DataFrame chứa dữ liệu preview
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
        
        try:
            # Đọc sheet không có header
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        except Exception:
            return pd.DataFrame()
        
        # Lấy các cột cần thiết
        data = []
        end_row = len(df) if limit is None else min(len(df), self.START_ROW + limit)
        for idx in range(self.START_ROW, end_row):
            row = df.iloc[idx]
            
            ten_cam = row[self.COL_TEN_CAM]
            kich_co_bao = row[self.COL_KICH_CO_BAO]
            so_luong_bao = row[self.COL_SO_LUONG_BAO]
            so_luong_kg = row[self.COL_SO_LUONG_KG]
            
            # Bỏ qua dòng trống
            if pd.isna(ten_cam) or pd.isna(so_luong_kg):
                continue
            
            # Xử lý kích cỡ bao - chuyển thành string để tránh lỗi
            try:
                kich_co_bao_val = str(int(kich_co_bao)) if pd.notna(kich_co_bao) else ""
            except (ValueError, TypeError):
                kich_co_bao_val = str(kich_co_bao) if pd.notna(kich_co_bao) else ""
            
            # Xử lý số lượng bao - có thể bị định dạng Date trong Excel
            try:
                if pd.notna(so_luong_bao):
                    # Nếu là datetime, chuyển thành Excel serial number
                    if hasattr(so_luong_bao, 'toordinal'):
                        # datetime object - convert to Excel serial
                        so_luong_bao_val = int((so_luong_bao - pd.Timestamp('1899-12-31')).days)
                    elif isinstance(so_luong_bao, (int, float)):
                        so_luong_bao_val = int(so_luong_bao)
                    else:
                        so_luong_bao_val = int(float(str(so_luong_bao)))
                else:
                    so_luong_bao_val = 0
            except (ValueError, TypeError):
                so_luong_bao_val = 0
            
            # Xử lý số lượng kg - có thể bị định dạng Date trong Excel
            try:
                if pd.notna(so_luong_kg):
                    if hasattr(so_luong_kg, 'toordinal'):
                        so_luong_kg_val = int((so_luong_kg - pd.Timestamp('1899-12-31')).days)
                    elif isinstance(so_luong_kg, (int, float)):
                        so_luong_kg_val = float(so_luong_kg)
                    else:
                        so_luong_kg_val = float(str(so_luong_kg))
                else:
                    so_luong_kg_val = 0
            except (ValueError, TypeError):
                so_luong_kg_val = 0
                
            data.append({
                'Tên cám': str(ten_cam).strip(),
                'Kích cỡ bao (kg)': kich_co_bao_val,
                'Số lượng bao': so_luong_bao_val,
                'Số lượng (kg)': so_luong_kg_val
            })
        
        return pd.DataFrame(data)
    
    def _read_sheet_data(
        self, 
        file_path: str | Path, 
        sheet_name: str
    ) -> List[Dict]:
        """
        Đọc toàn bộ dữ liệu từ một sheet và gộp các dòng cùng tên cám
        
        Returns:
            List dict chứa dữ liệu mỗi sản phẩm (đã gộp)
        """
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        
        # Dictionary để gộp dữ liệu theo tên cám
        aggregated = {}
        
        for idx in range(self.START_ROW, len(df)):
            row = df.iloc[idx]
            
            ten_cam = row[self.COL_TEN_CAM]
            kich_co_bao = row[self.COL_KICH_CO_BAO]
            so_luong_bao = row[self.COL_SO_LUONG_BAO]
            so_luong_kg = row[self.COL_SO_LUONG_KG]
            
            # Bỏ qua dòng trống hoặc không có số lượng
            if pd.isna(ten_cam) or pd.isna(so_luong_kg):
                continue
            
            # Parse số lượng kg - xử lý trường hợp Date format
            try:
                if pd.notna(so_luong_kg):
                    if hasattr(so_luong_kg, 'toordinal'):
                        so_luong_kg_val = float((so_luong_kg - pd.Timestamp('1899-12-31')).days)
                    elif isinstance(so_luong_kg, (int, float)):
                        so_luong_kg_val = float(so_luong_kg)
                    else:
                        so_luong_kg_val = float(str(so_luong_kg))
                else:
                    so_luong_kg_val = 0
            except (ValueError, TypeError):
                continue
            
            # Parse số lượng bao - xử lý trường hợp Date format
            try:
                if pd.notna(so_luong_bao):
                    if hasattr(so_luong_bao, 'toordinal'):
                        so_luong_bao_val = int((so_luong_bao - pd.Timestamp('1899-12-31')).days)
                    elif isinstance(so_luong_bao, (int, float)):
                        so_luong_bao_val = int(so_luong_bao)
                    else:
                        so_luong_bao_val = int(float(str(so_luong_bao)))
                else:
                    so_luong_bao_val = 0
            except (ValueError, TypeError):
                so_luong_bao_val = 0
            
            if so_luong_kg_val <= 0:
                continue
            
            ten_cam_clean = str(ten_cam).strip()
            
            # Gộp vào dictionary
            if ten_cam_clean in aggregated:
                aggregated[ten_cam_clean]['so_luong_bao'] += so_luong_bao_val
                aggregated[ten_cam_clean]['so_luong_kg'] += so_luong_kg_val
            else:
                aggregated[ten_cam_clean] = {
                    'ten_cam': ten_cam_clean,
                    'kich_co_bao': kich_co_bao,
                    'so_luong_bao': so_luong_bao_val,
                    'so_luong_kg': so_luong_kg_val
                }
        
        return list(aggregated.values())
    
    def _get_product_id(self, cursor, ten_cam: str) -> Optional[int]:
        """Tìm ID sản phẩm từ Tên cám"""
        _p = self._ph()
        cursor.execute(f"""
            SELECT {self._q('ID')} 
            FROM {self._q('SanPham')} 
            WHERE TRIM({self._q('Tên cám')}) = {_p} AND {self._da_xoa_check()}
        """, (ten_cam,))
        result = cursor.fetchone()
        return result[0] if result else None
    
    def _generate_packing_code(self, cursor) -> str:
        """Tạo mã Packing tự động (PK00001, PK00002...)"""
        cursor.execute(f"""
            SELECT MAX({self._q('Mã packing')}) 
            FROM {self._q('Packing')} 
            WHERE {self._q('Mã packing')} LIKE 'PK%%'
        """)
        result = cursor.fetchone()[0]
        
        if result:
            try:
                last_num = int(result[2:])
                next_num = last_num + 1
            except ValueError:
                next_num = 1
        else:
            next_num = 1
            
        return f"PK{next_num:05d}"
    
    def _delete_packing_by_date(self, cursor, ngay_packing: str) -> int:
        _p = self._ph()
        cursor.execute(f"""
            SELECT COUNT(*) FROM {self._q('Packing')} 
            WHERE {self._q('Ngày packing')} = {_p} 
            AND {self._q('Ghi chú')} LIKE '%%Import từ DAILY PACKING%%'
            AND {self._da_xoa_check()}
        """, (ngay_packing,))
        count = cursor.fetchone()[0]
        
        da_xoa_val = "'1'" if self._is_pg else "1"
        cursor.execute(f"""
            UPDATE {self._q('Packing')} 
            SET {self._q('Đã xóa')} = {da_xoa_val} 
            WHERE {self._q('Ngày packing')} = {_p} 
            AND {self._q('Ghi chú')} LIKE '%%Import từ DAILY PACKING%%'
            AND {self._da_xoa_check()}
        """, (ngay_packing,))
        
        return count
    
    def import_packing_data(
        self,
        file_path: str | Path = None,
        sheet_name: str = "1",
        nguoi_import: str = "system",
        ngay_packing: Optional[str] = None,
        year: int = 2026,
        month: int = 1
    ) -> Dict:
        """
        Import dữ liệu Packing từ Excel vào database
        
        Args:
            file_path: Đường dẫn file Excel
            sheet_name: Tên sheet (ngày trong tháng)
            nguoi_import: Username người import
            ngay_packing: Ngày packing (YYYY-MM-DD), mặc định tính từ sheet
            year: Năm (mặc định 2026)
            month: Tháng (mặc định 1)
            
        Returns:
            Dict chứa kết quả import
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
            
        result = {
            'success': 0,
            'errors': [],
            'not_found': [],
            'ma_packing': None,
            'ngay_packing': None,
            'deleted': 0
        }
        
        try:
            # Tính ngày packing từ sheet name
            if ngay_packing is None:
                day = int(sheet_name)
                ngay_packing = f"{year}-{month:02d}-{day:02d}"
            
            result['ngay_packing'] = ngay_packing
            
            # Đọc dữ liệu từ sheet
            data = self._read_sheet_data(file_path, sheet_name)
            
            if not data:
                result['errors'].append("Không có dữ liệu hợp lệ trong sheet")
                return result
            
            # Kết nối database
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                # Xóa dữ liệu cũ của ngày này trước
                deleted_count = self._delete_packing_by_date(cursor, ngay_packing)
                result['deleted'] = deleted_count
                
                # Tạo mã packing
                ma_packing = self._generate_packing_code(cursor)
                result['ma_packing'] = ma_packing
                
                thoi_gian_tao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Import từng dòng
                for item in data:
                    product_id = self._get_product_id(cursor, item['ten_cam'])
                    
                    if not product_id:
                        result['not_found'].append(item['ten_cam'])
                        continue
                    
                    # Insert vào Packing
                    _p = self._ph()
                    da_xoa_val = "'0'" if self._is_pg else "0"
                    cursor.execute(f"""
                        INSERT INTO {self._q('Packing')} 
                        ({self._q('ID sản phẩm')}, {self._q('Mã packing')}, {self._q('Số lượng')}, {self._q('Ngày packing')},
                         {self._q('Ghi chú')}, {self._q('Người tạo')}, {self._q('Thời gian tạo')}, {self._q('Đã xóa')})
                        VALUES ({_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {da_xoa_val})
                    """, (
                        product_id,
                        ma_packing,
                        int(item['so_luong_kg']),
                        ngay_packing,
                        f"Import từ DAILY PACKING sheet {sheet_name}.{month}.{year}",
                        nguoi_import,
                        thoi_gian_tao
                    ))
                    
                    result['success'] += 1
                
                conn.commit()
                
            finally:
                conn.close()
                
        except Exception as e:
            result['errors'].append(str(e))
            
        return result


def test_packing_importer():
    """Test function"""
    importer = PackingImporter()
    
    print("=== Test PackingImporter ===")
    
    # Test lấy danh sách sheets
    print("\n1. Lấy danh sách sheets:")
    sheets = importer.get_available_sheets()
    print(f"   Có {len(sheets)} sheets: {sheets[:5]}...")
    
    # Test preview
    print("\n2. Preview sheet '2':")
    preview = importer.preview_data(sheet_name="2", limit=5)
    print(preview)
    
    print("\n=== Test hoàn tất ===")


if __name__ == "__main__":
    test_packing_importer()
