"""
Module import dữ liệu Xe bồn Silo hàng tuần từ file Excel SILO
Parse dữ liệu từ các sheet theo tuần (VD: 12-17-01-2026)
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import re
from utils import get_db_connection, is_postgres, q, ph


class SiloImporter:
    """Class xử lý import dữ liệu Xe bồn Silo từ file Excel"""
    
    # Default file path
    DEFAULT_FILE = "EXCEL/SILO W3-12-17-01-2026.xlsm"
    
    # ===== Column mapping for .XLSM files (with VBA macro) =====
    # Dữ liệu đã được xử lý bởi VBA, nằm ở cột L, M, N
    COL_NGAY_LAY = 11     # Cột L - Ngày lấy cám
    COL_TEN_CAM = 12      # Cột M - Tên cám
    COL_SO_LUONG = 13     # Cột N - Số lượng cám cần lấy
    
    # Start row for .xlsm (0-indexed, data starts from row 3 in Excel = row 2 in pandas)
    START_ROW = 2
    
    # ===== Column mapping for .XLSX files (without VBA macro) =====
    # Đọc trực tiếp từ dữ liệu gốc theo logic VBA:
    # - Cột A (index 0): Tên cám
    # - Cột C-I (index 2-8): Số lượng theo từng ngày (tối đa 7 ngày, bao gồm Chủ nhật)
    # - Dòng 5 (index 4): Chứa ngày của mỗi cột
    # - Dòng 6-70 (index 5-69): Dữ liệu
    XLSX_COL_TEN_CAM = 0           # Cột A - Tên cám
    XLSX_COL_SO_LUONG_START = 2    # Cột C (bắt đầu)
    XLSX_COL_SO_LUONG_END = 8      # Cột I (kết thúc) - 7 ngày bao gồm Chủ nhật
    XLSX_ROW_DATES = 4             # Dòng 5 (0-indexed = 4) chứa ngày
    XLSX_START_ROW = 5             # Dòng 6 (0-indexed = 5) bắt đầu dữ liệu
    XLSX_END_ROW = 69              # Dòng 70 (0-indexed = 69)
    XLSX_MIN_QUANTITY = 99         # Số lượng tối thiểu > 99
    
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
    
    def _is_xlsx_file(self, file_path: str | Path) -> bool:
        """Kiểm tra file có phải là .xlsx (không có VBA) hay không"""
        path_str = str(file_path).lower()
        return path_str.endswith('.xlsx')
    
    def _detect_week_column_range(self, df: pd.DataFrame) -> int:
        """
        Tự động phát hiện cột kết thúc dựa trên ngày trong header (dòng 5).
        
        Logic:
        - Nếu C5 là Chủ nhật (weekday=6) hoặc I5 có ngày → tuần có 7 ngày (C-I)
        - Nếu C5 là Thứ 2 và H5 là Thứ 7 → tuần có 6 ngày (C-H)
        
        Returns:
            int: Column index kết thúc (7 cho H, 8 cho I)
        """
        if self.XLSX_ROW_DATES >= len(df):
            return self.XLSX_COL_SO_LUONG_END  # Mặc định
        
        dates_row = df.iloc[self.XLSX_ROW_DATES]
        
        # Kiểm tra cột C (index 2) - ngày đầu tiên
        col_c_date = dates_row[2] if 2 < len(dates_row) else None
        
        # Kiểm tra cột I (index 8) - có thể là ngày thứ 7
        col_i_date = dates_row[8] if 8 < len(dates_row) else None
        
        # Kiểm tra cột H (index 7) - ngày thứ 6 hoặc cuối
        col_h_date = dates_row[7] if 7 < len(dates_row) else None
        
        # Nếu cột I có ngày hợp lệ → tuần 7 ngày
        if pd.notna(col_i_date):
            try:
                if isinstance(col_i_date, datetime):
                    print(f"[DEBUG] Column I has date: {col_i_date} (weekday={col_i_date.weekday()}) → 7 days")
                    return 8  # Cột I
                else:
                    # Thử parse string thành datetime
                    parsed = pd.to_datetime(col_i_date, errors='coerce')
                    if pd.notna(parsed):
                        print(f"[DEBUG] Column I has date: {parsed} → 7 days")
                        return 8
            except:
                pass
        
        # Kiểm tra ngày đầu tiên (C5) có phải Chủ nhật không
        if pd.notna(col_c_date):
            try:
                if isinstance(col_c_date, datetime):
                    if col_c_date.weekday() == 6:  # Chủ nhật
                        print(f"[DEBUG] Column C is Sunday: {col_c_date} → 7 days")
                        return 8  # Có Chủ nhật đầu tuần
                else:
                    parsed = pd.to_datetime(col_c_date, errors='coerce')
                    if pd.notna(parsed) and parsed.weekday() == 6:
                        print(f"[DEBUG] Column C is Sunday: {parsed} → 7 days")
                        return 8
            except:
                pass
        
        # Mặc định 6 ngày (C-H)
        print(f"[DEBUG] Default: 6 days (C-H)")
        return 7
    
    def get_available_sheets(self, file_path: str | Path = None) -> List[str]:
        """
        Lấy danh sách các sheet (tuần) có sẵn trong file Excel
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
            
        xl = pd.ExcelFile(file_path)
        # Lấy tất cả sheets có định dạng ngày
        return xl.sheet_names
    
    def preview_data(
        self, 
        file_path: str | Path = None, 
        sheet_name: str = None,
        limit: int = 15
    ) -> pd.DataFrame:
        """
        Xem trước dữ liệu từ một sheet
        Tự động detect loại file và áp dụng logic phù hợp
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
        
        if sheet_name is None:
            sheets = self.get_available_sheets(file_path)
            sheet_name = sheets[-1] if sheets else None
            
        if not sheet_name:
            return pd.DataFrame()
        
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        except Exception as e:
            print(f"[DEBUG] Error reading Excel: {e}")
            return pd.DataFrame()
        
        is_xlsx = self._is_xlsx_file(file_path)
        data = []
        
        print(f"[DEBUG] File: {file_path}")
        print(f"[DEBUG] Sheet: {sheet_name}")
        print(f"[DEBUG] Is XLSX: {is_xlsx}")
        print(f"[DEBUG] Total rows: {len(df)}, columns: {len(df.columns)}")
        
        if is_xlsx:
            # Logic cho file .xlsx (không VBA) - đọc trực tiếp như VBA
            # Tự động phát hiện số cột dựa trên ngày trong header
            col_end = self._detect_week_column_range(df)
            dates_row = df.iloc[self.XLSX_ROW_DATES] if self.XLSX_ROW_DATES < len(df) else None
            
            print(f"[DEBUG] Detected column range: C to {chr(65 + col_end)} (index 2 to {col_end})")
            
            # Duyệt theo thứ tự cột (C đến H hoặc I tùy vào tuần)
            for col_idx in range(self.XLSX_COL_SO_LUONG_START, col_end + 1):
                # Lấy ngày của cột này từ dòng 5
                ngay_lay = dates_row[col_idx] if dates_row is not None and col_idx < len(dates_row) else None
                ngay_lay_str = ""
                if pd.notna(ngay_lay):
                    if isinstance(ngay_lay, datetime):
                        ngay_lay_str = ngay_lay.strftime('%d/%m/%Y')
                    else:
                        ngay_lay_str = str(ngay_lay)
                
                # Duyệt qua các dòng 6-70 (index 5-69)
                for row_idx in range(self.XLSX_START_ROW, min(len(df), self.XLSX_END_ROW + 1)):
                    row = df.iloc[row_idx]
                    
                    # Cột A = Tên cám
                    ten_cam = row[self.XLSX_COL_TEN_CAM] if self.XLSX_COL_TEN_CAM < len(row) else None
                    # Cột hiện tại = Số lượng
                    so_luong = row[col_idx] if col_idx < len(row) else None
                    
                    # Bỏ qua dòng trống hoặc không phải số
                    if pd.isna(ten_cam) or not str(ten_cam).strip():
                        continue
                    
                    # Xử lý số lượng - chỉ lấy nếu > 99 (theo VBA)
                    try:
                        so_luong_val = float(so_luong) if pd.notna(so_luong) else 0
                    except (ValueError, TypeError):
                        continue
                    
                    if so_luong_val <= self.XLSX_MIN_QUANTITY:
                        continue
                    
                    data.append({
                        'Ngày lấy': ngay_lay_str,
                        'Tên cám': str(ten_cam).strip(),
                        'Số lượng (kg)': so_luong_val
                    })
                    
                    if len(data) >= limit:
                        break
                
                if len(data) >= limit:
                    break
        else:
            # Logic cho file .xlsm (có VBA) - đọc từ cột L, M, N
            for idx in range(self.START_ROW, min(len(df), self.START_ROW + limit * 2)):
                row = df.iloc[idx]
                
                ngay_lay = row[self.COL_NGAY_LAY] if self.COL_NGAY_LAY < len(row) else None
                ten_cam = row[self.COL_TEN_CAM] if self.COL_TEN_CAM < len(row) else None
                so_luong = row[self.COL_SO_LUONG] if self.COL_SO_LUONG < len(row) else None
                
                # Bỏ qua dòng trống
                if pd.isna(ten_cam) or pd.isna(so_luong):
                    continue
                
                # Xử lý số lượng
                try:
                    so_luong_val = float(so_luong) if pd.notna(so_luong) else 0
                except (ValueError, TypeError):
                    continue
                
                if so_luong_val <= 0:
                    continue
                
                # Format ngày lấy
                ngay_lay_str = ""
                if pd.notna(ngay_lay):
                    if isinstance(ngay_lay, datetime):
                        ngay_lay_str = ngay_lay.strftime('%d/%m/%Y')
                    else:
                        ngay_lay_str = str(ngay_lay)
                    
                data.append({
                    'Ngày lấy': ngay_lay_str,
                    'Tên cám': str(ten_cam).strip(),
                    'Số lượng (kg)': so_luong_val
                })
                
                if len(data) >= limit:
                    break
        
        print(f"[DEBUG] Data found: {len(data)}")
        return pd.DataFrame(data)
    
    def _read_sheet_data(
        self, 
        file_path: str | Path, 
        sheet_name: str
    ) -> List[Dict]:
        """
        Đọc toàn bộ dữ liệu từ một sheet - mỗi dòng là 1 bản ghi riêng biệt
        Tự động detect loại file và áp dụng logic phù hợp
        """
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        except Exception:
            return []
        
        is_xlsx = self._is_xlsx_file(file_path)
        data = []
        
        if is_xlsx:
            # Logic cho file .xlsx (không VBA) - đọc trực tiếp như VBA
            # Tự động phát hiện số cột dựa trên ngày trong header
            col_end = self._detect_week_column_range(df)
            dates_row = df.iloc[self.XLSX_ROW_DATES] if self.XLSX_ROW_DATES < len(df) else None
            
            # Duyệt theo thứ tự cột (C đến H hoặc I tùy vào tuần)
            for col_idx in range(self.XLSX_COL_SO_LUONG_START, col_end + 1):
                # Lấy ngày của cột này từ dòng 5
                ngay_lay = dates_row[col_idx] if dates_row is not None and col_idx < len(dates_row) else None
                ngay_lay_str = None
                if pd.notna(ngay_lay):
                    if isinstance(ngay_lay, datetime):
                        ngay_lay_str = ngay_lay.strftime('%Y-%m-%d')
                    else:
                        try:
                            ngay_lay_str = str(ngay_lay)
                        except:
                            pass
                
                # Duyệt qua các dòng 6-70 (index 5-69)
                for row_idx in range(self.XLSX_START_ROW, min(len(df), self.XLSX_END_ROW + 1)):
                    row = df.iloc[row_idx]
                    
                    # Cột A = Tên cám
                    ten_cam = row[self.XLSX_COL_TEN_CAM] if self.XLSX_COL_TEN_CAM < len(row) else None
                    # Cột hiện tại = Số lượng
                    so_luong = row[col_idx] if col_idx < len(row) else None
                    
                    # Bỏ qua dòng trống hoặc không phải số
                    if pd.isna(ten_cam) or not str(ten_cam).strip():
                        continue
                    
                    # Xử lý số lượng - chỉ lấy nếu > 99 (theo VBA)
                    try:
                        so_luong_val = float(so_luong) if pd.notna(so_luong) else 0
                    except (ValueError, TypeError):
                        continue
                    
                    if so_luong_val <= self.XLSX_MIN_QUANTITY:
                        continue
                    
                    ten_cam_clean = str(ten_cam).strip()
                    
                    data.append({
                        'ten_cam': ten_cam_clean,
                        'ngay_lay': ngay_lay_str,
                        'so_luong': so_luong_val
                    })
        else:
            # Logic cho file .xlsm (có VBA) - đọc từ cột L, M, N
            for idx in range(self.START_ROW, len(df)):
                row = df.iloc[idx]
                
                ngay_lay = row[self.COL_NGAY_LAY] if self.COL_NGAY_LAY < len(row) else None
                ten_cam = row[self.COL_TEN_CAM] if self.COL_TEN_CAM < len(row) else None
                so_luong = row[self.COL_SO_LUONG] if self.COL_SO_LUONG < len(row) else None
                
                # Bỏ qua dòng trống
                if pd.isna(ten_cam) or pd.isna(so_luong):
                    continue
                
                # Parse số lượng (đơn vị tấn)
                try:
                    so_luong_val = float(so_luong) if pd.notna(so_luong) else 0
                except (ValueError, TypeError):
                    continue
                
                if so_luong_val <= 0:
                    continue
                
                ten_cam_clean = str(ten_cam).strip()
                
                # Format ngày lấy thành YYYY-MM-DD
                ngay_lay_str = None
                if pd.notna(ngay_lay):
                    if isinstance(ngay_lay, datetime):
                        ngay_lay_str = ngay_lay.strftime('%Y-%m-%d')
                    else:
                        try:
                            ngay_lay_str = str(ngay_lay)
                        except:
                            pass
                
                # Thêm trực tiếp vào list, không gộp
                data.append({
                    'ten_cam': ten_cam_clean,
                    'ngay_lay': ngay_lay_str,
                    'so_luong': so_luong_val
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
    
    def _parse_week_info(self, sheet_name: str) -> tuple:
        """
        Parse thông tin tuần từ tên sheet
        VD: "12-17-01-2026" -> (ngày bắt đầu, ngày kết thúc)
        """
        # Tìm ngày tháng năm
        date_match = re.search(r'(\d+)-(\d+)-(\d+)-(\d+)', sheet_name)
        if date_match:
            day_start = int(date_match.group(1))
            day_end = int(date_match.group(2))
            month = int(date_match.group(3))
            year = int(date_match.group(4))
            
            date_start = f"{year}-{month:02d}-{day_start:02d}"
            date_end = f"{year}-{month:02d}-{day_end:02d}"
        else:
            date_start = datetime.now().strftime('%Y-%m-%d')
            date_end = date_start
            
        return date_start, date_end
    
    def _delete_silo_by_sheet(self, cursor, sheet_name: str) -> int:
        _p = self._ph()
        cursor.execute(f"""
            SELECT COUNT(*) FROM {self._q('DatHang')} 
            WHERE {self._q('Ghi chú')} LIKE {_p} 
            AND {self._q('Loại đặt hàng')} = 'Xe bồn Silo'
            AND {self._da_xoa_check()}
        """, (f'%{sheet_name}%',))
        count = cursor.fetchone()[0]
        
        da_xoa_val = "'1'" if self._is_pg else "1"
        cursor.execute(f"""
            UPDATE {self._q('DatHang')} 
            SET {self._q('Đã xóa')} = {da_xoa_val} 
            WHERE {self._q('Ghi chú')} LIKE {_p} 
            AND {self._q('Loại đặt hàng')} = 'Xe bồn Silo'
            AND {self._da_xoa_check()}
        """, (f'%{sheet_name}%',))
        
        return count
    
    def import_silo_data(
        self,
        file_path: str | Path = None,
        sheet_name: str = None,
        nguoi_import: str = "system"
    ) -> Dict:
        """
        Import dữ liệu Xe bồn Silo từ Excel vào database (bảng DatHang)
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
            'week_info': None,
            'deleted': 0
        }
        
        if not sheet_name:
            result['errors'].append("Không tìm thấy sheet hợp lệ")
            return result
        
        try:
            # Parse thông tin tuần
            date_start, date_end = self._parse_week_info(sheet_name)
            result['week_info'] = f"Tuần: {date_start} đến {date_end}"
            
            # Đọc dữ liệu từ sheet
            data = self._read_sheet_data(file_path, sheet_name)
            
            if not data:
                result['errors'].append("Không có dữ liệu hợp lệ trong sheet")
                return result
            
            # Kết nối database
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                # Xóa dữ liệu cũ
                deleted_count = self._delete_silo_by_sheet(cursor, sheet_name)
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
                        result['not_found'].append(item['ten_cam'])
                        continue
                    
                    # Số lượng (chuyển từ tấn sang kg nếu cần - hiện giữ nguyên tấn)
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
                        'Xe bồn Silo',
                        0,
                        f"Import từ SILO {sheet_name}",
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


def test_silo_importer():
    """Test function"""
    importer = SiloImporter()
    
    print("=== Test SiloImporter ===")
    
    print("\n1. Lấy danh sách sheets:")
    sheets = importer.get_available_sheets()
    print(f"   Sheets: {sheets}")
    
    print("\n2. Preview sheet cuối:")
    preview = importer.preview_data(limit=5)
    print(preview)
    
    print("\n=== Test hoàn tất ===")


if __name__ == "__main__":
    test_silo_importer()
