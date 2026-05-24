"""
Module import dữ liệu Forecast hàng tuần từ file Excel SALEFORECAST
Parse dữ liệu từ các sheet theo tuần (W1, W2, W3, ...)
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import re
from utils import get_db_connection, is_postgres, q, ph, adapt_create_sql


class ForecastImporter:
    """Class xử lý import dữ liệu Forecast từ file Excel SALEFORECAST"""
    
    # Default file path
    DEFAULT_FILE = "EXCEL/W3.(12-17-01-) SALEFORECAST 2026.xlsm"
    
    # ===== Column mapping for .XLSM files (with VBA macro) =====
    # These columns are populated by VBA macro
    COL_TEN_CAM = 31      # Cột AF - Tên cám
    COL_KICH_CO_EP = 32   # Cột AG - Kích cỡ ép viên
    COL_KICH_CO_BAO = 33  # Cột AH - Kích cỡ đóng bao
    COL_SO_LUONG_TAN = 34 # Cột AI - Số lượng tấn đặt hàng
    
    # Start row for .xlsm (0-indexed, data starts from row 1 in Excel = row 0 in pandas)
    START_ROW = 0
    
    # ===== Column mapping for .XLSX files (without VBA macro) =====
    # Sản lượng luôn ở cột U
    XLSX_COL_SO_LUONG = 20       # Cột U - Số lượng (tấn)
    XLSX_COL_KICH_CO_EP = 1      # Cột B - Kích cỡ ép viên
    XLSX_COL_KICH_CO_BAO = 2     # Cột C - Kích cỡ đóng bao
    
    # Logic lấy Tên cám từ file .xlsx (giống VBA logic)
    # Thứ tự ưu tiên: I → D → E → F → G → H (kiểm tra không rỗng)
    XLSX_TEN_CAM_PRIORITY = [8, 3, 4, 5, 6, 7]  # Cột I, D, E, F, G, H (0-indexed)
    
    # Start row for .xlsx (0-indexed, data starts from row 10 in Excel = row 9 in pandas)
    XLSX_START_ROW = 9
    
    # End markers for .xlsx (cột A chứa một trong các giá trị này thì dừng)
    XLSX_END_MARKERS = ['***GOAT***', '***GRAND***', '***Laboratory***']
    
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
    
    def _get_ten_cam_from_xlsx_row(self, row) -> Optional[str]:
        """
        Xác định tên cám từ một dòng trong file .xlsx dựa trên logic VBA:
        - Cột U > 0 là điều kiện tiên quyết
        - Kiểm tra thứ tự ưu tiên: I → D → E → F → G → H (lấy cell không rỗng đầu tiên)
        """
        # Kiểm tra cột U (sản lượng) > 0
        so_luong = row[self.XLSX_COL_SO_LUONG] if self.XLSX_COL_SO_LUONG < len(row) else None
        
        try:
            so_luong_val = float(so_luong) if pd.notna(so_luong) else 0
        except (ValueError, TypeError):
            return None
        
        if so_luong_val <= 0:
            return None
        
        # Duyệt theo thứ tự ưu tiên I → D → E → F → G → H (giống VBA)
        for cot_ten_cam in self.XLSX_TEN_CAM_PRIORITY:
            if cot_ten_cam < len(row):
                ten_cam = row[cot_ten_cam]
                if pd.notna(ten_cam):
                    ten_cam_str = str(ten_cam).strip()
                    if ten_cam_str:  # Không rỗng
                        return ten_cam_str
        
        return None
    
    def _is_end_marker(self, row) -> bool:
        """Kiểm tra dòng có phải là dòng kết thúc (dựa trên cột A)"""
        if len(row) == 0:
            return False
        col_a = row[0]
        if pd.isna(col_a):
            return False
        return str(col_a).strip() in self.XLSX_END_MARKERS
    
    def get_grand_total_from_excel(
        self, 
        file_path: str | Path = None, 
        sheet_name: str = None
    ) -> Optional[float]:
        """
        Lấy giá trị GRAND TOTAL từ file Excel
        - File .xlsx: Tìm trong cột A, lấy giá trị từ cột U
        - File .xlsm: Tìm trong cột AF, lấy giá trị từ cột AI
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
        
        if sheet_name is None:
            sheets = self.get_available_sheets(file_path)
            sheet_name = sheets[-1] if sheets else None
            
        if not sheet_name:
            return None
        
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        except Exception:
            return None
        
        is_xlsx = self._is_xlsx_file(file_path)
        
        if is_xlsx:
            # File .xlsx: Tìm trong cột A, lấy giá trị từ cột U
            search_col = 0  # Cột A
            value_col = self.XLSX_COL_SO_LUONG  # Cột U (index 20)
        else:
            # File .xlsm: Tìm trong cột AF (index 31), lấy giá trị từ cột AI (index 34)
            search_col = self.COL_TEN_CAM  # Cột AF (index 31)
            value_col = self.COL_SO_LUONG_TAN  # Cột AI (index 34)
        
        # Tìm dòng GRAND TOTAL
        for idx in range(len(df)):
            row = df.iloc[idx]
            if search_col >= len(row):
                continue
            
            cell_val = row[search_col]
            if pd.isna(cell_val):
                continue
            
            cell_str = str(cell_val).strip().upper()
            if 'GRAND TOTAL' in cell_str or '***GRAND***' in cell_str or 'TỔNG CỘNG' in cell_str:
                # Lấy giá trị từ cột value
                if value_col < len(row):
                    val = row[value_col]
                    if pd.notna(val):
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            pass
        
        # Fallback: Tìm trong cột A cho cả 2 loại file
        for idx in range(len(df)):
            row = df.iloc[idx]
            if len(row) == 0:
                continue
            col_a = row[0]
            if pd.isna(col_a):
                continue
            col_a_str = str(col_a).strip().upper()
            if 'GRAND TOTAL' in col_a_str or '***GRAND***' in col_a_str:
                if value_col < len(row):
                    val = row[value_col]
                    if pd.notna(val):
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            pass
        
        return None
    
    def get_available_sheets(self, file_path: str | Path = None) -> List[str]:
        """
        Lấy danh sách các sheet (tuần) có sẵn trong file Excel
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
            
        xl = pd.ExcelFile(file_path)
        # Lấy các sheet bắt đầu bằng W
        week_sheets = [s for s in xl.sheet_names if s.startswith('W')]
        return week_sheets
    
    def preview_data(
        self, 
        file_path: str | Path = None, 
        sheet_name: str = None,
        limit: int = 15
    ) -> pd.DataFrame:
        """
        Xem trước dữ liệu từ một sheet
        Tự động detect loại file (.xlsm hoặc .xlsx) và áp dụng logic phù hợp
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
        
        # Xác định dòng bắt đầu
        start_row = self.XLSX_START_ROW if is_xlsx else self.START_ROW
        
        # Debug info
        print(f"[DEBUG] File: {file_path}")
        print(f"[DEBUG] Sheet: {sheet_name}")
        print(f"[DEBUG] Is XLSX: {is_xlsx}")
        print(f"[DEBUG] Total rows: {len(df)}, columns: {len(df.columns)}")
        print(f"[DEBUG] Start row: {start_row+1} (0-indexed: {start_row})")
        
        rows_checked = 0
        rows_with_quantity = 0
        rows_with_name = 0
        
        for idx in range(start_row, min(len(df), start_row + limit * 3)):
            row = df.iloc[idx]
            rows_checked += 1
            
            # Kiểm tra end marker cho file .xlsx
            if is_xlsx and self._is_end_marker(row):
                print(f"[DEBUG] End marker found at row {idx+1}")
                break
            
            if is_xlsx:
                # Debug: Kiểm tra sản lượng cột U
                col_u = row[self.XLSX_COL_SO_LUONG] if self.XLSX_COL_SO_LUONG < len(row) else None
                try:
                    col_u_val = float(col_u) if pd.notna(col_u) else 0
                    if col_u_val > 0:
                        rows_with_quantity += 1
                except:
                    pass
                
                # Logic cho file .xlsx (không VBA)
                ten_cam = self._get_ten_cam_from_xlsx_row(row)
                if ten_cam is None:
                    continue
                
                rows_with_name += 1
                kich_co_ep = row[self.XLSX_COL_KICH_CO_EP] if self.XLSX_COL_KICH_CO_EP < len(row) else None
                kich_co_bao = row[self.XLSX_COL_KICH_CO_BAO] if self.XLSX_COL_KICH_CO_BAO < len(row) else None
                so_luong_tan = row[self.XLSX_COL_SO_LUONG] if self.XLSX_COL_SO_LUONG < len(row) else None
            else:
                # Logic cho file .xlsm (có VBA)
                ten_cam = row[self.COL_TEN_CAM] if self.COL_TEN_CAM < len(row) else None
                kich_co_ep = row[self.COL_KICH_CO_EP] if self.COL_KICH_CO_EP < len(row) else None
                kich_co_bao = row[self.COL_KICH_CO_BAO] if self.COL_KICH_CO_BAO < len(row) else None
                so_luong_tan = row[self.COL_SO_LUONG_TAN] if self.COL_SO_LUONG_TAN < len(row) else None
                
                # Bỏ qua dòng trống
                if pd.isna(ten_cam) or pd.isna(so_luong_tan):
                    continue
                ten_cam = str(ten_cam).strip()
            
            # Xử lý số lượng
            try:
                so_luong_val = float(so_luong_tan) if pd.notna(so_luong_tan) else 0
            except (ValueError, TypeError):
                continue
            
            if so_luong_val <= 0:
                continue
                
            data.append({
                'Tên cám': ten_cam,
                'Kích cỡ ép viên': kich_co_ep,
                'Kích cỡ bao (kg)': kich_co_bao,
                'Số lượng (tấn)': so_luong_val
            })
            
            if len(data) >= limit:
                break
        
        print(f"[DEBUG] Rows checked: {rows_checked}")
        print(f"[DEBUG] Rows with U > 0: {rows_with_quantity}")
        print(f"[DEBUG] Rows with valid name: {rows_with_name}")
        print(f"[DEBUG] Data found: {len(data)}")
        
        return pd.DataFrame(data)
    
    def _read_sheet_data(
        self, 
        file_path: str | Path, 
        sheet_name: str
    ) -> List[Dict]:
        """
        Đọc toàn bộ dữ liệu từ một sheet và gộp các dòng cùng tên cám
        Tự động detect loại file và áp dụng logic phù hợp
        """
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        except Exception:
            return []
        
        is_xlsx = self._is_xlsx_file(file_path)
        
        # Xác định dòng bắt đầu
        start_row = self.XLSX_START_ROW if is_xlsx else self.START_ROW
        
        # Dictionary để gộp dữ liệu theo tên cám
        aggregated = {}
        
        for idx in range(start_row, len(df)):
            row = df.iloc[idx]
            
            # Kiểm tra end marker cho file .xlsx
            if is_xlsx and self._is_end_marker(row):
                break
            
            if is_xlsx:
                # Logic cho file .xlsx (không VBA)
                ten_cam = self._get_ten_cam_from_xlsx_row(row)
                if ten_cam is None:
                    continue
                
                kich_co_ep = row[self.XLSX_COL_KICH_CO_EP] if self.XLSX_COL_KICH_CO_EP < len(row) else None
                kich_co_bao = row[self.XLSX_COL_KICH_CO_BAO] if self.XLSX_COL_KICH_CO_BAO < len(row) else None
                so_luong_tan = row[self.XLSX_COL_SO_LUONG] if self.XLSX_COL_SO_LUONG < len(row) else None
                
                # Parse số lượng
                try:
                    so_luong_val = float(so_luong_tan) if pd.notna(so_luong_tan) else 0
                except (ValueError, TypeError):
                    continue
            else:
                # Logic cho file .xlsm (có VBA)
                ten_cam = row[self.COL_TEN_CAM] if self.COL_TEN_CAM < len(row) else None
                kich_co_ep = row[self.COL_KICH_CO_EP] if self.COL_KICH_CO_EP < len(row) else None
                kich_co_bao = row[self.COL_KICH_CO_BAO] if self.COL_KICH_CO_BAO < len(row) else None
                so_luong_tan = row[self.COL_SO_LUONG_TAN] if self.COL_SO_LUONG_TAN < len(row) else None
                
                # Bỏ qua dòng trống
                if pd.isna(ten_cam) or pd.isna(so_luong_tan):
                    continue
                
                ten_cam = str(ten_cam).strip()
                
                # Parse số lượng
                try:
                    so_luong_val = float(so_luong_tan) if pd.notna(so_luong_tan) else 0
                except (ValueError, TypeError):
                    continue
            
            if so_luong_val <= 0:
                continue
            
            # Gộp vào dictionary
            if ten_cam in aggregated:
                aggregated[ten_cam]['so_luong_tan'] += so_luong_val
            else:
                aggregated[ten_cam] = {
                    'ten_cam': ten_cam,
                    'kich_co_ep': kich_co_ep,
                    'kich_co_bao': kich_co_bao,
                    'so_luong_tan': so_luong_val
                }
        
        return list(aggregated.values())
    
    def _get_product_id(self, cursor, ten_cam: str) -> Optional[int]:
        _p = self._ph()
        # 1. Exact match (TRIM)
        cursor.execute(f"""
            SELECT {self._q('ID')} 
            FROM {self._q('SanPham')} 
            WHERE TRIM({self._q('Tên cám')}) = {_p} AND {self._da_xoa_check()}
        """, (ten_cam,))
        result = cursor.fetchone()
        if result:
            return result[0]
        
        # 2. Fallback: normalize spaces before parentheses
        # "550S(5*5)" should match "550S (5*5)" and vice versa
        import re
        normalized = re.sub(r'\s*\(', '(', ten_cam.strip())
        if self._is_pg:
            cursor.execute(f"""
                SELECT {self._q('ID')} 
                FROM {self._q('SanPham')} 
                WHERE REGEXP_REPLACE(TRIM({self._q('Tên cám')}), '\\s*\\(', '(', 'g') = {_p} 
                AND {self._da_xoa_check()}
            """, (normalized,))
        else:
            cursor.execute(f"""
                SELECT {self._q('ID')} 
                FROM {self._q('SanPham')} 
                WHERE REPLACE(TRIM({self._q('Tên cám')}), ' (', '(') = {_p} 
                AND {self._da_xoa_check()}
            """, (normalized,))
        result = cursor.fetchone()
        return result[0] if result else None
    
    def _generate_forecast_code(self, cursor) -> str:
        cursor.execute(f"""
            SELECT MAX({self._q('Mã forecast')}) 
            FROM {self._q('Forecast')} 
            WHERE {self._q('Mã forecast')} LIKE 'FC%%'
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
        return f"FC{next_num:05d}"
    
    def _parse_week_info(self, sheet_name: str) -> tuple:
        """
        Parse thông tin tuần từ tên sheet
        VD: "W3.12-17-01-2026" -> (3, "2026-01-12", "2026-01-17")
        """
        # Tìm số tuần
        week_match = re.search(r'W(\d+)', sheet_name)
        week_num = int(week_match.group(1)) if week_match else 1
        
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
            
        return week_num, date_start, date_end
    
    def _delete_forecast_by_week(self, cursor, sheet_name: str) -> int:
        _p = self._ph()
        cursor.execute(f"""
            SELECT COUNT(*) FROM {self._q('Forecast')} 
            WHERE {self._q('Ghi chú')} LIKE {_p} 
            AND {self._da_xoa_check()}
        """, (f'%{sheet_name}%',))
        count = cursor.fetchone()[0]
        
        da_xoa_val = "'1'" if self._is_pg else "1"
        cursor.execute(f"""
            UPDATE {self._q('Forecast')} 
            SET {self._q('Đã xóa')} = {da_xoa_val} 
            WHERE {self._q('Ghi chú')} LIKE {_p} 
            AND {self._da_xoa_check()}
        """, (f'%{sheet_name}%',))
        
        return count
    
    def _ensure_forecast_table(self, cursor):
        """Tạo bảng Forecast nếu chưa có"""
        sql = """
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
        """
        cursor.execute(adapt_create_sql(sql, self.db_path))
    
    def import_forecast_data(
        self,
        file_path: str | Path = None,
        sheet_name: str = None,
        nguoi_import: str = "system"
    ) -> Dict:
        """
        Import dữ liệu Forecast từ Excel vào database
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
            'ma_forecast': None,
            'week_info': None,
            'deleted': 0
        }
        
        if not sheet_name:
            result['errors'].append("Không tìm thấy sheet hợp lệ")
            return result
        
        try:
            # Parse thông tin tuần
            week_num, date_start, date_end = self._parse_week_info(sheet_name)
            result['week_info'] = f"Tuần {week_num}: {date_start} đến {date_end}"
            
            # Đọc dữ liệu từ sheet
            data = self._read_sheet_data(file_path, sheet_name)
            
            if not data:
                result['errors'].append("Không có dữ liệu hợp lệ trong sheet")
                return result
            
            # Kết nối database
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                # Tạo bảng nếu chưa có
                self._ensure_forecast_table(cursor)
                
                # Xóa dữ liệu cũ
                deleted_count = self._delete_forecast_by_week(cursor, sheet_name)
                result['deleted'] = deleted_count
                
                # Tạo mã forecast
                ma_forecast = self._generate_forecast_code(cursor)
                result['ma_forecast'] = ma_forecast
                
                thoi_gian_tao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Import từng dòng
                for item in data:
                    product_id = self._get_product_id(cursor, item['ten_cam'])
                    
                    if not product_id:
                        result['not_found'].append(item['ten_cam'])
                        continue
                    
                    _p = self._ph()
                    da_xoa_val = "'0'" if self._is_pg else "0"
                    cursor.execute(f"""
                        INSERT INTO {self._q('Forecast')} 
                        ({self._q('ID sản phẩm')}, {self._q('Mã forecast')}, {self._q('Số lượng tấn')}, {self._q('Tuần')},
                         {self._q('Ngày bắt đầu')}, {self._q('Ngày kết thúc')}, {self._q('Ghi chú')}, 
                         {self._q('Người tạo')}, {self._q('Thời gian tạo')}, {self._q('Đã xóa')})
                        VALUES ({_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {da_xoa_val})
                    """, (
                        product_id,
                        ma_forecast,
                        item['so_luong_tan'],
                        week_num,
                        date_start,
                        date_end,
                        f"Import từ SALEFORECAST {sheet_name}",
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
    
    def _get_existing_orders(self, cursor, product_id: int, date_start: str, date_end: str) -> float:
        _p = self._ph()
        qty_col = f"CAST({self._q('Số lượng')} AS NUMERIC)" if self._is_pg else self._q('Số lượng')
        cursor.execute(f"""
            SELECT COALESCE(SUM({qty_col}), 0)
            FROM {self._q('DatHang')}
            WHERE {self._q('ID sản phẩm')} = {_p}
            AND {self._q('Ngày lấy')} BETWEEN {_p} AND {_p}
            AND {self._q('Loại đặt hàng')} IN ('Đại lý Bá Cang', 'Xe bồn Silo')
            AND {self._da_xoa_check()}
        """, (product_id, date_start, date_end))
        result = cursor.fetchone()
        return float(result[0]) if result and result[0] else 0.0
    
    def _delete_forecast_in_dathang(self, cursor, sheet_name: str) -> int:
        _p = self._ph()
        cursor.execute(f"""
            SELECT COUNT(*) FROM {self._q('DatHang')} 
            WHERE {self._q('Ghi chú')} LIKE {_p} 
            AND {self._q('Loại đặt hàng')} = 'Forecast hàng tuần'
            AND {self._da_xoa_check()}
        """, (f'%{sheet_name}%',))
        count = cursor.fetchone()[0]
        
        da_xoa_val = "'1'" if self._is_pg else "1"
        cursor.execute(f"""
            UPDATE {self._q('DatHang')} 
            SET {self._q('Đã xóa')} = {da_xoa_val} 
            WHERE {self._q('Ghi chú')} LIKE {_p} 
            AND {self._q('Loại đặt hàng')} = 'Forecast hàng tuần'
            AND {self._da_xoa_check()}
        """, (f'%{sheet_name}%',))
        
        return count
    
    def import_forecast_to_dathang(
        self,
        file_path: str | Path = None,
        sheet_name: str = None,
        nguoi_import: str = "system"
    ) -> Dict:
        """
        Import dữ liệu Forecast từ Excel vào bảng DatHang
        Tính chênh lệch với dữ liệu đã import từ Bá Cang/Silo
        Chỉ import phần còn lại (nếu > 0)
        """
        if file_path is None:
            file_path = self.DEFAULT_FILE
            
        if sheet_name is None:
            sheets = self.get_available_sheets(file_path)
            sheet_name = sheets[-1] if sheets else None
            
        result = {
            'success': 0,
            'skipped': 0,  # Sản phẩm đã có đủ từ nguồn khác
            'partial': 0,  # Sản phẩm import một phần
            'errors': [],
            'not_found': [],
            'ma_dathang': None,
            'week_info': None,
            'sheet_name': sheet_name,
            'deleted': 0,
            'details': []  # Chi tiết từng sản phẩm
        }
        
        if not sheet_name:
            result['errors'].append("Không tìm thấy sheet hợp lệ")
            return result
        
        try:
            # Parse thông tin tuần
            week_num, date_start, date_end = self._parse_week_info(sheet_name)
            result['week_info'] = f"Tuần {week_num}: {date_start} đến {date_end}"
            
            # Đọc dữ liệu từ sheet
            data = self._read_sheet_data(file_path, sheet_name)
            
            if not data:
                result['errors'].append("Không có dữ liệu hợp lệ trong sheet")
                return result
            
            # Kết nối database
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                # Xóa dữ liệu Forecast cũ trong DatHang
                deleted_count = self._delete_forecast_in_dathang(cursor, sheet_name)
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
                    
                    # Tính số lượng từ Forecast (tấn -> kg)
                    forecast_kg = item['so_luong_tan'] * 1000
                    
                    # Lấy số lượng đã đặt từ Bá Cang/Silo
                    existing_kg = self._get_existing_orders(cursor, product_id, date_start, date_end)
                    
                    # Tính số lượng còn lại cần import
                    remaining_kg = forecast_kg - existing_kg
                    
                    detail = {
                        'ten_cam': item['ten_cam'],
                        'forecast_kg': forecast_kg,
                        'existing_kg': existing_kg,
                        'remaining_kg': remaining_kg,
                        'status': ''
                    }
                    
                    if remaining_kg <= 0:
                        # Đã có đủ hoặc vượt từ nguồn khác
                        detail['status'] = 'Đã có đủ từ Bá Cang/Silo'
                        result['skipped'] += 1
                    else:
                        # Insert phần còn lại vào DatHang
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
                            remaining_kg,
                            ngay_dat,
                            date_start,
                            'Forecast hàng tuần',
                            0,
                            f"Import từ SALEFORECAST {sheet_name} (Forecast: {forecast_kg:,.0f}kg - Đã có: {existing_kg:,.0f}kg)",
                            nguoi_import,
                            thoi_gian_tao
                        ))
                        
                        if existing_kg > 0:
                            detail['status'] = f'Import {remaining_kg:,.0f}kg (đã trừ {existing_kg:,.0f}kg từ nguồn khác)'
                            result['partial'] += 1
                        else:
                            detail['status'] = f'Import {remaining_kg:,.0f}kg'
                            result['success'] += 1
                    
                    result['details'].append(detail)
                
                conn.commit()
                
            finally:
                conn.close()
                
        except Exception as e:
            result['errors'].append(str(e))
            
        return result

def test_forecast_importer():
    """Test function"""
    importer = ForecastImporter()
    
    print("=== Test ForecastImporter ===")
    
    print("\n1. Lấy danh sách sheets:")
    sheets = importer.get_available_sheets()
    print(f"   Sheets: {sheets}")
    
    print("\n2. Preview sheet cuối:")
    preview = importer.preview_data(limit=5)
    print(preview)
    
    print("\n=== Test hoàn tất ===")


if __name__ == "__main__":
    test_forecast_importer()
