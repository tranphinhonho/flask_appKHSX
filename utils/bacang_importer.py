"""
Module import dữ liệu Đại lý Bá Cang hàng tuần từ file Excel KẾ HOẠCH CÁM TUẦN VÕ BÁ CANG
Parse dữ liệu trực tiếp từ source columns (không cần chạy VBA)

Bảng 1 (Xe tải bao 25kg):
- Dữ liệu nguồn: Cột A (mã cám), Cột B-G (số lượng theo ngày)
- Ngày: Hàng 7, cột B-G
- Sản phẩm: Từ hàng 8 đến hàng TOTAL

Bảng 2 (Xe bồn Silo):
- Tìm "MÃ CÁM" ở cột C làm mốc
- Cột B: Ngày (có thể merged)
- Cột C: Mã cám
- Cột D: Số lượng (kg)
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import re
from utils import get_db_connection, is_postgres, q, ph


class BaCangImporter:
    """Class xử lý import dữ liệu Đại lý Bá Cang từ file Excel"""
    
    # Default file path
    DEFAULT_FILE = "EXCEL/KẾ HOẠCH CÁM TUẦN VÕ BÁ CANG 2026.xlsm"
    
    # Bảng 1: Dữ liệu nguồn (0-indexed)
    TABLE1_PRODUCT_COL = 0        # Cột A - Mã sản phẩm
    TABLE1_DATE_COLS = [1, 2, 3, 4, 5, 6]  # Cột B-G - Số lượng theo ngày
    TABLE1_DATE_ROW = 6           # Hàng 7 - Chứa ngày
    TABLE1_START_ROW = 7          # Hàng 8 - Bắt đầu dữ liệu sản phẩm
    
    # Bảng 2: Dữ liệu nguồn  
    TABLE2_DATE_COL = 1           # Cột B - Ngày
    TABLE2_PRODUCT_COL = 2        # Cột C - Mã cám
    TABLE2_QTY_COL = 3            # Cột D - Số lượng
    TABLE2_HEADER = "MÃ CÁM"      # Từ khóa để tìm header bảng 2
    
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
        Lấy danh sách các sheet (tuần) có sẵn trong file Excel
        Sắp xếp theo số tuần (xử lý chuyển năm: tuần 52 → tuần 1)
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
            
        xl = pd.ExcelFile(file_path)
        sheet_names = xl.sheet_names
        
        # Sắp xếp theo số tuần (extract số từ tên sheet)
        def get_week_number(sheet_name: str) -> int:
            # Tìm số tuần trong tên sheet (e.g., "TUẦN 5" -> 5, "TUẦN 52@" -> 52)
            match = re.search(r'(\d+)', sheet_name)
            if match:
                return int(match.group(1))
            return 0
        
        # Xác định tuần hiện tại để xử lý chuyển năm
        current_week = datetime.now().isocalendar()[1]
        
        # Sắp xếp: nếu đang ở tuần 1-10, coi các tuần 50-52 là "năm trước" (đặt lên đầu)
        def sort_key(sheet_name: str) -> int:
            week_num = get_week_number(sheet_name)
            # Nếu đang ở đầu năm (tuần 1-10) và gặp tuần cuối năm (50-52)
            # thì đặt tuần cuối năm lên đầu danh sách
            if current_week <= 10 and week_num >= 50:
                return week_num - 100  # Sẽ có giá trị âm, đứng đầu
            return week_num
        
        sorted_sheets = sorted(sheet_names, key=sort_key)
        return sorted_sheets
    
    def _find_total_row(self, df: pd.DataFrame) -> int:
        """Tìm hàng chứa TOTAL ở cột A"""
        for idx in range(len(df)):
            val = df.iloc[idx, 0]
            if pd.notna(val) and str(val).strip().upper() == "TOTAL":
                return idx
        return len(df)  # Nếu không tìm thấy, trả về cuối file
    
    def _find_table2_header(self, df: pd.DataFrame) -> int:
        """Tìm hàng chứa MÃ CÁM ở cột C để làm mốc bảng 2"""
        for idx in range(len(df)):
            if self.TABLE2_PRODUCT_COL < len(df.columns):
                val = df.iloc[idx, self.TABLE2_PRODUCT_COL]
                if pd.notna(val) and self.TABLE2_HEADER in str(val).upper():
                    return idx
        return -1  # Không tìm thấy
    
    def _format_date(self, date_val) -> str:
        """Format ngày thành chuỗi dd/mm/yyyy"""
        if pd.isna(date_val):
            return ""
        if isinstance(date_val, datetime):
            return date_val.strftime('%d/%m/%Y')
        try:
            # Thử parse nếu là chuỗi
            parsed = pd.to_datetime(date_val)
            return parsed.strftime('%d/%m/%Y')
        except:
            return str(date_val)
    
    def _format_date_db(self, date_val) -> Optional[str]:
        """Format ngày thành chuỗi YYYY-MM-DD cho database"""
        if pd.isna(date_val):
            return None
        if isinstance(date_val, datetime):
            return date_val.strftime('%Y-%m-%d')
        try:
            parsed = pd.to_datetime(date_val)
            return parsed.strftime('%Y-%m-%d')
        except:
            return None
    
    def preview_data(
        self, 
        file_path: str | Path = None, 
        sheet_name: str = None,
        limit: int = 50
    ) -> tuple:
        """
        Xem trước dữ liệu từ một sheet
        Đọc trực tiếp từ source columns (không cần VBA)
        Returns: (DataFrame bảng 1, DataFrame bảng 2)
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
        
        if sheet_name is None:
            sheets = self.get_available_sheets(file_path)
            sheet_name = sheets[-1] if sheets else None
            
        if not sheet_name:
            return pd.DataFrame(), pd.DataFrame()
        
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        except Exception as e:
            print(f"Error reading Excel: {e}")
            return pd.DataFrame(), pd.DataFrame()
        
        # === BẢNG 1: Xe tải bao 25kg ===
        data1 = []
        total_row = self._find_total_row(df)
        
        # Lấy ngày từ hàng 7 (index 6)
        dates = []
        for col in self.TABLE1_DATE_COLS:
            if col < len(df.columns):
                dates.append(df.iloc[self.TABLE1_DATE_ROW, col])
            else:
                dates.append(None)
        
        # Duyệt qua các hàng sản phẩm
        for row_idx in range(self.TABLE1_START_ROW, total_row):
            product_code = df.iloc[row_idx, self.TABLE1_PRODUCT_COL]
            
            if pd.isna(product_code) or str(product_code).strip() == "":
                continue
            
            product_code_clean = str(product_code).strip()
            
            # Duyệt qua từng cột ngày
            for col_offset, col in enumerate(self.TABLE1_DATE_COLS):
                if col >= len(df.columns):
                    continue
                    
                qty = df.iloc[row_idx, col]
                
                if pd.isna(qty):
                    continue
                    
                try:
                    qty_val = float(qty)
                except (ValueError, TypeError):
                    continue
                
                if qty_val <= 0:
                    continue
                
                date_val = dates[col_offset]
                
                data1.append({
                    'Ngày lấy': self._format_date(date_val),
                    'Tên cám': product_code_clean,
                    'Số bao': int(qty_val),
                    'Số lượng (kg)': int(qty_val * 25)  # Mỗi bao 25kg
                })
                
                if len(data1) >= limit:
                    break
            
            if len(data1) >= limit:
                break
        
        # === BẢNG 2: Xe bồn Silo ===
        data2 = []
        table2_header_row = self._find_table2_header(df)
        
        if table2_header_row >= 0:
            table2_start = table2_header_row + 1
            last_date = None  # Để xử lý merged cells
            
            for row_idx in range(table2_start, len(df)):
                product_code = df.iloc[row_idx, self.TABLE2_PRODUCT_COL]
                
                if pd.isna(product_code) or str(product_code).strip() == "":
                    continue
                    
                product_code_clean = str(product_code).strip()
                
                # Bỏ qua các dòng tổng cộng
                if "TỔNG" in product_code_clean.upper() or "TOTAL" in product_code_clean.upper():
                    continue
                
                qty = df.iloc[row_idx, self.TABLE2_QTY_COL]
                
                try:
                    qty_val = float(qty) if pd.notna(qty) else 0
                except (ValueError, TypeError):
                    continue
                    
                if qty_val <= 0:
                    continue
                
                # Xử lý ngày (có thể merged)
                date_val = df.iloc[row_idx, self.TABLE2_DATE_COL]
                if pd.notna(date_val):
                    last_date = date_val
                
                data2.append({
                    'Ngày lấy': self._format_date(last_date),
                    'Tên cám': product_code_clean,
                    'Số lượng (kg)': int(qty_val)
                })
                
                if len(data2) >= limit:
                    break
        
        return pd.DataFrame(data1), pd.DataFrame(data2)
    
    def _read_sheet_data(
        self, 
        file_path: str | Path, 
        sheet_name: str
    ) -> List[Dict]:
        """
        Đọc toàn bộ dữ liệu từ cả 2 bảng trong sheet
        Đọc trực tiếp từ source columns
        """
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        except Exception:
            return []
        
        data = []
        
        # === BẢNG 1: Xe tải bao 25kg ===
        total_row = self._find_total_row(df)
        
        # Lấy ngày từ hàng 7 (index 6)
        dates = []
        for col in self.TABLE1_DATE_COLS:
            if col < len(df.columns):
                dates.append(df.iloc[self.TABLE1_DATE_ROW, col])
            else:
                dates.append(None)
        
        # Duyệt qua các hàng sản phẩm
        for row_idx in range(self.TABLE1_START_ROW, total_row):
            product_code = df.iloc[row_idx, self.TABLE1_PRODUCT_COL]
            
            if pd.isna(product_code) or str(product_code).strip() == "":
                continue
            
            product_code_clean = str(product_code).strip()
            
            # Duyệt qua từng cột ngày
            for col_offset, col in enumerate(self.TABLE1_DATE_COLS):
                if col >= len(df.columns):
                    continue
                    
                qty = df.iloc[row_idx, col]
                
                if pd.isna(qty):
                    continue
                    
                try:
                    qty_val = float(qty)
                except (ValueError, TypeError):
                    continue
                
                if qty_val <= 0:
                    continue
                
                date_val = dates[col_offset]
                
                data.append({
                    'ten_cam': product_code_clean,
                    'ngay_lay': self._format_date_db(date_val),
                    'so_luong': int(qty_val * 25),  # Mỗi bao 25kg
                    'source': 'table1'
                })
        
        # === BẢNG 2: Xe bồn Silo ===
        table2_header_row = self._find_table2_header(df)
        
        if table2_header_row >= 0:
            table2_start = table2_header_row + 1
            last_date = None
            
            for row_idx in range(table2_start, len(df)):
                product_code = df.iloc[row_idx, self.TABLE2_PRODUCT_COL]
                
                if pd.isna(product_code) or str(product_code).strip() == "":
                    continue
                    
                product_code_clean = str(product_code).strip()
                
                # Bỏ qua các dòng tổng cộng
                if "TỔNG" in product_code_clean.upper() or "TOTAL" in product_code_clean.upper():
                    continue
                
                qty = df.iloc[row_idx, self.TABLE2_QTY_COL]
                
                try:
                    qty_val = float(qty) if pd.notna(qty) else 0
                except (ValueError, TypeError):
                    continue
                    
                if qty_val <= 0:
                    continue
                
                # Xử lý ngày (có thể merged)
                date_val = df.iloc[row_idx, self.TABLE2_DATE_COL]
                if pd.notna(date_val):
                    last_date = date_val
                
                data.append({
                    'ten_cam': product_code_clean,
                    'ngay_lay': self._format_date_db(last_date),
                    'so_luong': int(qty_val),
                    'source': 'table2'
                })
        
        return data
    
    def _get_product_id(self, cursor, ten_cam: str) -> Optional[int]:
        _p = self._ph()
        cursor.execute(f"""
            SELECT {self._q('ID')} 
            FROM {self._q('SanPham')} 
            WHERE TRIM({self._q('Tên cám')}) = {_p} AND {self._da_xoa_check()}
        """, (ten_cam,))
        result = cursor.fetchone()
        if result:
            return result[0]
        
        ten_cam_clean = ten_cam.lstrip("'")
        cursor.execute(f"""
            SELECT {self._q('ID')} 
            FROM {self._q('SanPham')} 
            WHERE TRIM({self._q('Code cám')}) = {_p} AND {self._da_xoa_check()}
        """, (ten_cam_clean,))
        result = cursor.fetchone()
        return result[0] if result else None
    
    def _generate_dathang_code(self, cursor) -> str:
        cursor.execute(f"""
            SELECT MAX({self._q('Mã đặt hàng')}) 
            FROM {self._q('DatHang')} 
            WHERE {self._q('Mã đặt hàng')} LIKE 'DH%%'
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
        return f"DH{next_num:05d}"
    
    def _delete_bacang_by_sheet(self, cursor, sheet_name: str) -> int:
        _p = self._ph()
        cursor.execute(f"""
            SELECT COUNT(*) FROM {self._q('DatHang')} 
            WHERE {self._q('Ghi chú')} LIKE {_p} 
            AND {self._q('Loại đặt hàng')} = 'Đại lý Bá Cang'
            AND {self._da_xoa_check()}
        """, (f'%{sheet_name}%',))
        count = cursor.fetchone()[0]
        
        da_xoa_val = "'1'" if self._is_pg else "1"
        cursor.execute(f"""
            UPDATE {self._q('DatHang')} 
            SET {self._q('Đã xóa')} = {da_xoa_val} 
            WHERE {self._q('Ghi chú')} LIKE {_p} 
            AND {self._q('Loại đặt hàng')} = 'Đại lý Bá Cang'
            AND {self._da_xoa_check()}
        """, (f'%{sheet_name}%',))
        
        return count
    
    def delete_all_bacang_data(self) -> Dict:
        """
        Xóa tất cả dữ liệu Đại lý Bá Cang
        Returns: Dict với số lượng đã xóa và thông báo
        """
        result = {
            'deleted': 0,
            'success': False,
            'message': ''
        }
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT COUNT(*) FROM {self._q('DatHang')} 
                WHERE {self._q('Loại đặt hàng')} = 'Đại lý Bá Cang'
                AND {self._da_xoa_check()}
            """)
            count = cursor.fetchone()[0]
            
            da_xoa_val = "'1'" if self._is_pg else "1"
            cursor.execute(f"""
                UPDATE {self._q('DatHang')} 
                SET {self._q('Đã xóa')} = {da_xoa_val} 
                WHERE {self._q('Loại đặt hàng')} = 'Đại lý Bá Cang'
                AND {self._da_xoa_check()}
            """)
            
            conn.commit()
            conn.close()
            
            result['deleted'] = count
            result['success'] = True
            result['message'] = f"Đã xóa {count} bản ghi Đại lý Bá Cang"
            
        except Exception as e:
            result['message'] = str(e)
            
        return result
    
    def import_bacang_data(
        self,
        file_path: str | Path = None,
        sheet_name: str = None,
        nguoi_import: str = "system"
    ) -> Dict:
        """
        Import dữ liệu Đại lý Bá Cang từ Excel vào database (bảng DatHang)
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
            
        if sheet_name is None:
            sheets = self.get_available_sheets(file_path)
            sheet_name = sheets[-1] if sheets else None
            
        result = {
            'success': 0,
            'errors': [],
            'not_found': [],
            'ma_dathang': None,
            'sheet_name': sheet_name,
            'deleted': 0
        }
        
        if not sheet_name:
            result['errors'].append("Không tìm thấy sheet hợp lệ")
            return result
        
        try:
            # Đọc dữ liệu từ sheet (cả 2 bảng)
            data = self._read_sheet_data(file_path, sheet_name)
            
            if not data:
                result['errors'].append("Không có dữ liệu hợp lệ trong sheet")
                return result
            
            # Kết nối database
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                # Xóa dữ liệu cũ
                deleted_count = self._delete_bacang_by_sheet(cursor, sheet_name)
                result['deleted'] = deleted_count
                
                # Tạo mã đặt hàng
                ma_dathang = self._generate_dathang_code(cursor)
                result['ma_dathang'] = ma_dathang
                
                thoi_gian_tao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ngay_dat = datetime.now().strftime('%Y-%m-%d')
                
                # Import từng dòng
                for item in data:
                    product_id = self._get_product_id(cursor, item['ten_cam'])
                    
                    if not product_id:
                        if item['ten_cam'] not in result['not_found']:
                            result['not_found'].append(item['ten_cam'])
                        continue
                    
                    # Số lượng (kg)
                    so_luong = item['so_luong']
                    
                    # Insert vào DatHang
                    _p = self._ph()
                    da_xoa_val = "'0'" if self._is_pg else "0"
                    cursor.execute(f"""
                        INSERT INTO {self._q('DatHang')} 
                        ({self._q('ID sản phẩm')}, {self._q('Mã đặt hàng')}, {self._q('Số lượng')}, {self._q('Ngày đặt')}, {self._q('Ngày lấy')},
                         {self._q('Loại đặt hàng')}, {self._q('Khách vãng lai')}, {self._q('Ghi chú')}, 
                         {self._q('Người tạo')}, {self._q('Thời gian tạo')}, {self._q('Đã xóa')})
                        VALUES ({_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {da_xoa_val})
                    """, (
                        product_id,
                        ma_dathang,
                        so_luong,
                        ngay_dat,
                        item['ngay_lay'],
                        'Đại lý Bá Cang',
                        0,
                        f"Import từ Bá Cang {sheet_name} ({item['source']})",
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


def test_bacang_importer():
    """Test function"""
    importer = BaCangImporter()
    
    print("=== Test BaCangImporter ===")
    
    print("\n1. Lấy danh sách sheets:")
    try:
        sheets = importer.get_available_sheets()
        print(f"   Sheets: {sheets}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n2. Preview sheet cuối:")
    try:
        df1, df2 = importer.preview_data(limit=10)
        print("Bảng 1 (Xe tải bao 25kg):")
        print(df1)
        print("\nBảng 2 (Xe bồn Silo):")
        print(df2)
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n=== Test hoàn tất ===")


if __name__ == "__main__":
    test_bacang_importer()
