"""
Module import dữ liệu Sale từ file Excel DAILY SALED REPORT
Parse dữ liệu từ các sheet theo ngày (1, 2, 3, ..., 31)
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
from utils import get_db_connection, is_postgres, q, ph


class SaleImporter:
    """Class xử lý import dữ liệu Sale từ file Excel DAILY SALED REPORT"""
    
    # Default file path
    DEFAULT_FILE = "EXCEL/DAILY SALED REPORT THANG 1.2026.xlsm"
    
    # Column mapping (0-indexed)
    COL_TEN_CAM = 28      # Cột AC - Tên cám
    COL_KICH_CO_BAO = 29  # Cột AD - Kích cỡ đóng bao
    COL_SO_LUONG_BAO = 10 # Cột K - Số lượng bao
    COL_SO_LUONG_KG = 12  # Cột M - Số lượng kg
    
    # Start row (0-indexed, data starts from row 3 in Excel = row 2 in pandas)
    START_ROW = 2
    
    def __init__(self, db_path: str = "database_new.db"):
        """
        Khởi tạo SaleImporter
        
        Args:
            db_path: Đường dẫn database SQLite hoặc PostgreSQL URL
        """
        self.db_path = db_path
        self._is_pg = is_postgres(db_path)
    
    def _get_connection(self):
        """Tạo connection đến database (SQLite hoặc PostgreSQL)"""
        return get_db_connection(self.db_path)
    
    def _q(self, name: str) -> str:
        """Quote column/table name"""
        return q(name, self.db_path)
    
    def _ph(self) -> str:
        """Placeholder cho parameterized query"""
        return ph(self.db_path)
    
    def _now_func(self) -> str:
        """SQL function cho thời gian hiện tại"""
        return "NOW()" if self._is_pg else "datetime('now')"
    
    def _da_xoa_check(self, val='0') -> str:
        """So sánh cột 'Đã xóa' - PostgreSQL là TEXT nên cần cast"""
        if self._is_pg:
            return f'{self._q("Đã xóa")}::integer = {val}'
        else:
            return f'{self._q("Đã xóa")} = {val}'
    
    def get_available_sheets(self, file_path: str | Path = None) -> List[str]:
        """
        Lấy danh sách các sheet (ngày) có sẵn trong file Excel
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
        Lấy giá trị tổng sản lượng từ ô M4 trong Excel
        
        Args:
            file_path: Đường dẫn file Excel
            sheet_name: Tên sheet (ngày)
            
        Returns:
            Giá trị tổng từ ô M4 hoặc None nếu không có
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
        
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
            # Ô M4 = row index 3, column index 12
            value = df.iloc[3, 12]
            if pd.notna(value):
                # Xử lý trường hợp Date format
                if hasattr(value, 'toordinal'):
                    return float((value - pd.Timestamp('1899-12-31')).days)
                return float(value)
            return None
        except Exception:
            return None
    
    def preview_data(
        self, 
        file_path: str | Path = None, 
        sheet_name: str = "1",
        limit: int = 15
    ) -> pd.DataFrame:
        """
        Xem trước dữ liệu từ một sheet
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
        
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        except Exception:
            # Sheet trống hoặc không có dữ liệu
            return pd.DataFrame()
        
        # Kiểm tra số cột tối thiểu cần thiết
        min_cols_required = max(self.COL_TEN_CAM, self.COL_KICH_CO_BAO, self.COL_SO_LUONG_BAO, self.COL_SO_LUONG_KG) + 1
        if len(df.columns) < min_cols_required:
            # File không đúng format, trả về DataFrame rỗng
            return pd.DataFrame()
        
        data = []
        end_row = len(df) if limit is None else min(len(df), self.START_ROW + limit * 2)
        for idx in range(self.START_ROW, end_row):
            row = df.iloc[idx]
            
            ten_cam = row[self.COL_TEN_CAM]
            kich_co_bao = row[self.COL_KICH_CO_BAO]
            so_luong_bao = row[self.COL_SO_LUONG_BAO]
            so_luong_kg = row[self.COL_SO_LUONG_KG]
            
            # Bỏ qua dòng trống
            if pd.isna(ten_cam) or pd.isna(so_luong_kg):
                continue
            
            # Xử lý kích cỡ bao - convert to numeric
            try:
                kich_co_bao_num = float(kich_co_bao)
            except (ValueError, TypeError):
                # Nếu là text (như "Silo"), giữ nguyên nhưng đặt thành text
                kich_co_bao_num = None
            
            # Xử lý số lượng bao - có thể bị định dạng Date trong Excel
            try:
                if pd.notna(so_luong_bao):
                    if hasattr(so_luong_bao, 'toordinal'):
                        so_luong_bao_num = int((so_luong_bao - pd.Timestamp('1899-12-31')).days)
                    elif isinstance(so_luong_bao, (int, float)):
                        so_luong_bao_num = int(so_luong_bao)
                    else:
                        so_luong_bao_num = int(float(str(so_luong_bao)))
                else:
                    so_luong_bao_num = 0
            except (ValueError, TypeError):
                so_luong_bao_num = 0
            
            # Xử lý số lượng kg - có thể bị định dạng Date trong Excel
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
                so_luong_kg_val = 0
                
            data.append({
                'Tên cám': str(ten_cam).strip(),
                'Kích cỡ bao (kg)': kich_co_bao_num if kich_co_bao_num else str(kich_co_bao),
                'Số lượng bao': so_luong_bao_num,
                'Số lượng (kg)': so_luong_kg_val
            })
            
            if limit is not None and len(data) >= limit:
                break
        
        return pd.DataFrame(data)
    
    def _read_sheet_data(
        self, 
        file_path: str | Path, 
        sheet_name: str
    ) -> List[Dict]:
        """
        Đọc toàn bộ dữ liệu từ một sheet và gộp các dòng cùng tên cám
        """
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        
        # Kiểm tra số cột tối thiểu cần thiết
        min_cols_required = max(self.COL_TEN_CAM, self.COL_KICH_CO_BAO, self.COL_SO_LUONG_BAO, self.COL_SO_LUONG_KG) + 1
        if len(df.columns) < min_cols_required:
            return []  # File không đúng format
        
        # Dictionary để gộp dữ liệu theo tên cám
        aggregated = {}
        
        for idx in range(self.START_ROW, len(df)):
            row = df.iloc[idx]
            
            ten_cam = row[self.COL_TEN_CAM]
            kich_co_bao = row[self.COL_KICH_CO_BAO]
            so_luong_bao = row[self.COL_SO_LUONG_BAO]
            so_luong_kg = row[self.COL_SO_LUONG_KG]
            
            # Bỏ qua dòng trống
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
    
    def _generate_sale_code(self, cursor) -> str:
        """Tạo mã Sale tự động (SL00001, SL00002...)"""
        cursor.execute(f"""
            SELECT MAX({self._q('Mã sale')}) 
            FROM {self._q('Sale')} 
            WHERE {self._q('Mã sale')} LIKE 'SL%%'
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
            
        return f"SL{next_num:05d}"
    
    def _delete_sale_by_date(self, cursor, ngay_sale: str) -> int:
        """
        Xóa tất cả sale của ngày cụ thể (import từ DAILY SALED REPORT)
        """
        _p = self._ph()
        cursor.execute(f"""
            SELECT COUNT(*) FROM {self._q('Sale')} 
            WHERE {self._q('Ngày sale')} = {_p} 
            AND {self._q('Ghi chú')} LIKE '%%Import từ DAILY SALED REPORT%%'
            AND {self._da_xoa_check()}
        """, (ngay_sale,))
        count = cursor.fetchone()[0]
        
        da_xoa_val = "'1'" if self._is_pg else "1"
        cursor.execute(f"""
            UPDATE {self._q('Sale')} 
            SET {self._q('Đã xóa')} = {da_xoa_val} 
            WHERE {self._q('Ngày sale')} = {_p} 
            AND {self._q('Ghi chú')} LIKE '%%Import từ DAILY SALED REPORT%%'
            AND {self._da_xoa_check()}
        """, (ngay_sale,))
        
        return count
    
    def import_sale_data(
        self,
        file_path: str | Path = None,
        sheet_name: str = "1",
        nguoi_import: str = "system",
        ngay_sale: Optional[str] = None,
        year: int = 2026,
        month: int = 1
    ) -> Dict:
        """
        Import dữ liệu Sale từ Excel vào database
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
            
        result = {
            'success': 0,
            'errors': [],
            'not_found': [],
            'ma_sale': None,
            'ngay_sale': None,
            'deleted': 0
        }
        
        try:
            # Tính ngày sale từ sheet name
            if ngay_sale is None:
                day = int(sheet_name)
                ngay_sale = f"{year}-{month:02d}-{day:02d}"
            
            result['ngay_sale'] = ngay_sale
            
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
                deleted_count = self._delete_sale_by_date(cursor, ngay_sale)
                result['deleted'] = deleted_count
                
                # Tạo mã sale
                ma_sale = self._generate_sale_code(cursor)
                result['ma_sale'] = ma_sale
                
                thoi_gian_tao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Import từng dòng
                for item in data:
                    product_id = self._get_product_id(cursor, item['ten_cam'])
                    
                    if not product_id:
                        result['not_found'].append(item['ten_cam'])
                        continue
                    
                    # Insert vào Sale
                    _p = self._ph()
                    da_xoa_val = "'0'" if self._is_pg else "0"
                    cursor.execute(f"""
                        INSERT INTO {self._q('Sale')} 
                        ({self._q('ID sản phẩm')}, {self._q('Mã sale')}, {self._q('Số lượng')}, {self._q('Ngày sale')},
                         {self._q('Ghi chú')}, {self._q('Người tạo')}, {self._q('Thời gian tạo')}, {self._q('Đã xóa')})
                        VALUES ({_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {da_xoa_val})
                    """, (
                        product_id,
                        ma_sale,
                        int(item['so_luong_kg']),
                        ngay_sale,
                        f"Import từ DAILY SALED REPORT sheet {sheet_name}.{month}.{year}",
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


def test_sale_importer():
    """Test function"""
    importer = SaleImporter()
    
    print("=== Test SaleImporter ===")
    
    print("\n1. Lấy danh sách sheets:")
    sheets = importer.get_available_sheets()
    print(f"   Có {len(sheets)} sheets: {sheets[:5]}...")
    
    print("\n2. Preview sheet '2':")
    preview = importer.preview_data(sheet_name="2", limit=5)
    print(preview)
    
    print("\n=== Test hoàn tất ===")


if __name__ == "__main__":
    test_sale_importer()
