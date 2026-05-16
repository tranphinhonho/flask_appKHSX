# -*- coding: utf-8 -*-
"""
Module import dữ liệu Tồn bồn hàng ngày từ file Excel
Đọc dữ liệu từ cột O (Code cám) và P (Số lượng kg) sau khi chạy VBA TongHopBaoCaoCam()
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import time
from utils import get_db_connection, is_postgres, q, ph

try:
    import win32com.client as win32
    HAS_WIN32COM = True
except ImportError:
    win32 = None
    HAS_WIN32COM = False


class TonBonImporter:
    """Class xử lý import dữ liệu Tồn bồn từ file Excel"""
    
    # File mặc định
    DEFAULT_FILE = "EXCEL/Báo cáo tồn bồn thành phẩm 01.2026.xlsm"
    
    # Vị trí cột sau khi chạy VBA
    COL_CODE_CAM = 14  # Cột O (index 14)
    COL_SO_LUONG = 15  # Cột P (index 15)
    START_ROW = 2      # Bắt đầu từ dòng 2 (dòng 1 là header)
    
    # Tên VBA macro
    VBA_MACRO_NAME = "TongHopBaoCaoCam"
    
    def __init__(self, db_path: str = "database_new.db"):
        """
        Khởi tạo TonBonImporter
        
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
    
    def _ensure_import_log_table(self):
        """Tạo bảng EmailImportLog nếu chưa có"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if self._is_pg:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS "EmailImportLog" (
                    "ID" SERIAL PRIMARY KEY,
                    "TenFile" TEXT NOT NULL,
                    "NgayEmail" DATE,
                    "LoaiFile" TEXT NOT NULL,
                    "SoLuongDong" INTEGER DEFAULT 0,
                    "ThoiGianImport" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    "NguoiImport" TEXT
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS EmailImportLog (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    TenFile TEXT NOT NULL,
                    NgayEmail DATE,
                    LoaiFile TEXT NOT NULL,
                    SoLuongDong INTEGER DEFAULT 0,
                    ThoiGianImport DATETIME DEFAULT CURRENT_TIMESTAMP,
                    NguoiImport TEXT
                )
            """)
        
        conn.commit()
        conn.close()
    
    def _run_excel_macro(self, file_path: Path, macro_name: str = None) -> bool:
        """
        Mở Excel, chạy VBA macro, lưu file
        
        Args:
            file_path: Đường dẫn file Excel (absolute path)
            macro_name: Tên macro VBA cần chạy
            
        Returns:
            True nếu thành công
        """
        if not HAS_WIN32COM:
            print("❌ Không có win32com - cần cài pywin32")
            return False
        
        macro_name = macro_name or self.VBA_MACRO_NAME
        excel = None
        workbook = None
        
        try:
            # Khởi tạo Excel application
            excel = win32.gencache.EnsureDispatch('Excel.Application')
            excel.Visible = False  # Ẩn Excel
            excel.DisplayAlerts = False  # Tắt cảnh báo
            
            # Mở file (cần đường dẫn tuyệt đối)
            abs_path = str(file_path.resolve())
            print(f"📂 Đang mở file: {abs_path}")
            workbook = excel.Workbooks.Open(abs_path)
            
            # Chạy macro
            print(f"🚀 Đang chạy VBA: {macro_name}...")
            excel.Application.Run(macro_name)
            
            # Lưu file
            workbook.Save()
            print("💾 Đã lưu file")
            
            # Đóng workbook
            workbook.Close(SaveChanges=True)
            workbook = None
            
            return True
            
        except Exception as e:
            print(f"❌ Lỗi chạy VBA: {e}")
            return False
            
        finally:
            # Cleanup
            try:
                if workbook:
                    workbook.Close(SaveChanges=False)
            except:
                pass
            try:
                if excel:
                    excel.Quit()
            except:
                pass
    
    def read_direct_from_cells(
        self, 
        file_path: str | Path = None,
        sheet_index: int = 1
    ) -> pd.DataFrame:
        """
        Đọc trực tiếp dữ liệu từ các vùng cell ở Sheet cụ thể
        
        Cấu trúc file:
        - Cột A (A1:A50) và cột E (E1:E50): Số bồn
          + Bồn 86-98: Bán thành phẩm
          + Bồn 99-134: Thành phẩm
        - Cột B và F: Mã số cám (code)
        - Cột C và G: Khối lượng (kg)
        
        Args:
            file_path: Đường dẫn file Excel
            sheet_index: Index của sheet (0-based), hoặc tên sheet
            
        Returns:
            DataFrame với các cột: Code cám, Số lượng (kg), Số bồn, Loại bồn
        """
        file_path = Path(file_path or self.DEFAULT_FILE)
        
        # Danh sách số bồn hợp lệ
        BON_BAN_THANH_PHAM = set(range(86, 99))  # 86-98
        BON_THANH_PHAM = set(range(99, 135))     # 99-134
        ALL_VALID_BONS = BON_BAN_THANH_PHAM | BON_THANH_PHAM
        
        try:
            # Đọc sheet theo index hoặc tên
            df = pd.read_excel(file_path, sheet_name=sheet_index, header=None, engine='openpyxl')
            
            data = []
            
            # Quét 2 vùng: A1:C50 và E1:G50 (row index 0-49)
            # A=0, B=1, C=2, E=4, F=5, G=6
            column_sets = [
                (0, 1, 2),   # Cột A, B, C (trái)
                (4, 5, 6),   # Cột E, F, G (phải)
            ]
            
            for bon_col, code_col, kg_col in column_sets:
                # Quét từ row 0-49 (A1:A50)
                for row_idx in range(min(50, len(df))):
                    try:
                        bon_val = df.iloc[row_idx, bon_col]
                        code_val = df.iloc[row_idx, code_col] if code_col < len(df.columns) else None
                        kg_val = df.iloc[row_idx, kg_col] if kg_col < len(df.columns) else None
                        
                        # Kiểm tra số bồn hợp lệ
                        if pd.isna(bon_val):
                            continue
                        
                        try:
                            so_bon = int(float(bon_val))
                        except (ValueError, TypeError):
                            continue
                        
                        # Chỉ xử lý nếu là số bồn hợp lệ (86-134)
                        if so_bon not in ALL_VALID_BONS:
                            continue
                        
                        # Xác định loại bồn
                        loai_bon = "Bán thành phẩm" if so_bon in BON_BAN_THANH_PHAM else "Thành phẩm"
                        
                        # Kiểm tra code cám
                        if pd.isna(code_val) or str(code_val).strip() == '':
                            continue
                        
                        # Chuyển code về string (hỗ trợ 6 hoặc 8 chữ số)
                        # Loại bỏ ký tự * và các ký tự không phải số
                        code_raw = str(code_val).strip().replace('*', '').replace(' ', '')
                        try:
                            code_str = str(int(float(code_raw))).strip()
                        except (ValueError, TypeError):
                            continue
                        
                        if len(code_str) in [6, 8] and code_str.isdigit():
                            kg = float(kg_val) if not pd.isna(kg_val) else 0
                            
                            if kg > 0:  # Chỉ lấy khi có số lượng
                                data.append({
                                    'Code cám': code_str,
                                    'Số lượng (kg)': kg,
                                    'Số bồn': str(so_bon),
                                    'Loại bồn': loai_bon
                                })
                    except Exception:
                        continue
            
            # Gộp các mã giống nhau (cộng kg, nối số bồn)
            if data:
                df_result = pd.DataFrame(data)
                # Group và aggregate
                df_grouped = df_result.groupby('Code cám', as_index=False).agg({
                    'Số lượng (kg)': 'sum',
                    'Số bồn': lambda x: ', '.join(sorted(set(str(v) for v in x if v))),  # Nối các bồn
                    'Loại bồn': 'first'  # Lấy loại bồn đầu tiên
                })
                return df_grouped
            
            return pd.DataFrame()
            
        except Exception as e:
            print(f"Lỗi đọc sheet {sheet_index}: {e}")
            return pd.DataFrame()
    
    def _extract_month_year_from_filename(self, filename: str) -> tuple:
        """
        Trích xuất tháng và năm từ tên file
        Ví dụ: "Bao cao ton bon thanh pham 01.2026.xlsx" → (1, 2026)
        """
        import re
        # Tìm pattern XX.YYYY hoặc XX-YYYY
        match = re.search(r'(\d{1,2})[.\-](\d{4})', filename)
        if match:
            month = int(match.group(1))
            year = int(match.group(2))
            return (month, year)
        return (None, None)
    
    def read_all_sheets_with_dates(
        self, 
        file_path: str | Path = None
    ) -> pd.DataFrame:
        """
        Đọc dữ liệu từ TẤT CẢ các sheet (1-31), mỗi sheet tương ứng 1 ngày.
        Tự động xác định ngày từ tên sheet + tháng/năm từ tên file.
        
        Args:
            file_path: Đường dẫn file Excel
            
        Returns:
            DataFrame với các cột: Ngày, Code cám, Số lượng (kg), Số bồn
        """
        file_path = Path(file_path or self.DEFAULT_FILE)
        filename = file_path.name
        
        # Lấy tháng/năm từ tên file
        month, year = self._extract_month_year_from_filename(filename)
        if not month or not year:
            print(f"⚠️ Không thể xác định tháng/năm từ tên file: {filename}")
            # Fallback: dùng tháng/năm hiện tại
            from datetime import datetime
            now = datetime.now()
            month, year = now.month, now.year
        
        print(f"📅 File tháng {month:02d}/{year}")
        
        # Lấy danh sách sheet
        try:
            xl = pd.ExcelFile(file_path, engine='openpyxl')
            sheet_names = xl.sheet_names
        except Exception as e:
            print(f"❌ Lỗi mở file: {e}")
            return pd.DataFrame()
        
        all_data = []
        valid_days = 0
        
        # Duyệt qua các sheet có tên là số (1-31)
        for sheet_name in sheet_names:
            try:
                day = int(sheet_name.strip())
                if day < 1 or day > 31:
                    continue
            except ValueError:
                continue  # Sheet không phải số, bỏ qua
            
            # Kiểm tra ngày hợp lệ
            from datetime import date
            try:
                ngay = date(year, month, day)
            except ValueError:
                continue  # Ngày không hợp lệ (ví dụ 31/02)
            
            # Đọc dữ liệu từ sheet này
            df_sheet = self.read_direct_from_cells(file_path, sheet_index=sheet_name)
            
            if len(df_sheet) > 0:
                df_sheet['Ngày'] = ngay.strftime('%Y-%m-%d')
                all_data.append(df_sheet)
                valid_days += 1
                print(f"  ✓ Ngày {day:02d}: {len(df_sheet)} mã sản phẩm")
        
        if all_data:
            df_combined = pd.concat(all_data, ignore_index=True)
            print(f"📊 Tổng cộng: {len(df_combined)} dòng từ {valid_days} ngày")
            return df_combined
        
        return pd.DataFrame()
    
    def run_vba_and_read(
        self, 
        file_path: str | Path = None, 
        limit: int = 50
    ) -> pd.DataFrame:
        """
        Chạy VBA TongHopBaoCaoCam rồi đọc dữ liệu từ cột O-P
        
        Args:
            file_path: Đường dẫn file Excel
            limit: Số dòng tối đa
            
        Returns:
            DataFrame với các cột: Code cám, Số lượng (kg)
        """
        file_path = Path(file_path or self.DEFAULT_FILE)
        
        # Bước 1: Chạy VBA macro
        if not self._run_excel_macro(file_path):
            return pd.DataFrame()
        
        # Đợi Excel đóng hoàn toàn
        time.sleep(1)
        
        # Bước 2: Đọc dữ liệu
        return self.preview_data(file_path, limit=limit)
    
    def get_available_sheets(self, file_path: str | Path = None) -> List[str]:
        """
        Lấy danh sách các sheet có sẵn trong file Excel
        """
        file_path = Path(file_path or self.DEFAULT_FILE)
        
        try:
            xl = pd.ExcelFile(file_path, engine='openpyxl')
            return xl.sheet_names
        except Exception as e:
            print(f"Lỗi đọc file: {e}")
            return []
    
    def preview_data(
        self, 
        file_path: str | Path = None, 
        sheet_name: str = None,
        limit: int = 20
    ) -> pd.DataFrame:
        """
        Xem trước dữ liệu từ file Excel (sau khi chạy VBA)
        
        Args:
            file_path: Đường dẫn file Excel
            sheet_name: Tên sheet (mặc định là sheet đầu tiên)
            limit: Số dòng tối đa
            
        Returns:
            DataFrame với các cột: Code cám, Số lượng (kg)
        """
        file_path = Path(file_path or self.DEFAULT_FILE)
        
        try:
            # Đọc sheet
            if sheet_name:
                df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine='openpyxl')
            else:
                df = pd.read_excel(file_path, header=None, engine='openpyxl')
            
            # Lấy dữ liệu từ cột O và P (index 14, 15)
            if len(df.columns) <= self.COL_SO_LUONG:
                print(f"File không đủ cột (cần ít nhất {self.COL_SO_LUONG + 1} cột)")
                return pd.DataFrame()
            
            data = []
            for idx in range(self.START_ROW - 1, min(len(df), self.START_ROW - 1 + limit)):
                row = df.iloc[idx]
                
                code_cam = row.iloc[self.COL_CODE_CAM] if not pd.isna(row.iloc[self.COL_CODE_CAM]) else None
                so_luong = row.iloc[self.COL_SO_LUONG] if not pd.isna(row.iloc[self.COL_SO_LUONG]) else 0
                
                # Chỉ lấy dòng có code hợp lệ (số 6 chữ số)
                if code_cam and str(code_cam).strip():
                    try:
                        # Chuyển về string và làm sạch
                        code_str = str(int(float(code_cam))).strip()
                        if len(code_str) == 6 and code_str.isdigit():
                            data.append({
                                'Code cám': code_str,
                                'Số lượng (kg)': float(so_luong) if so_luong else 0
                            })
                    except:
                        pass
            
            return pd.DataFrame(data)
            
        except Exception as e:
            print(f"Lỗi preview: {e}")
            return pd.DataFrame()
    
    def _read_all_data(self, file_path: Path, sheet_name: str = None) -> List[Dict]:
        """
        Đọc toàn bộ dữ liệu từ cột O-P
        
        Returns:
            List các dict: {code_cam, so_luong}
        """
        try:
            if sheet_name:
                df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine='openpyxl')
            else:
                df = pd.read_excel(file_path, header=None, engine='openpyxl')
            
            if len(df.columns) <= self.COL_SO_LUONG:
                return []
            
            data = []
            for idx in range(self.START_ROW - 1, len(df)):
                row = df.iloc[idx]
                
                code_cam = row.iloc[self.COL_CODE_CAM] if not pd.isna(row.iloc[self.COL_CODE_CAM]) else None
                so_luong = row.iloc[self.COL_SO_LUONG] if not pd.isna(row.iloc[self.COL_SO_LUONG]) else 0
                
                if code_cam and str(code_cam).strip():
                    try:
                        code_str = str(int(float(code_cam))).strip()
                        if len(code_str) == 6 and code_str.isdigit():
                            data.append({
                                'code_cam': code_str,
                                'so_luong': float(so_luong) if so_luong else 0
                            })
                    except:
                        pass
            
            return data
            
        except Exception as e:
            print(f"Lỗi đọc dữ liệu: {e}")
            return []
    
    def _get_product_id(self, cursor, code_cam: str) -> Optional[int]:
        """Tìm ID sản phẩm từ Code cám"""
        _p = self._ph()
        cursor.execute(f"""
            SELECT {self._q('ID')} 
            FROM {self._q('SanPham')} 
            WHERE TRIM({self._q('Code cám')}) = {_p} AND {self._da_xoa_check()}
        """, (code_cam.strip(),))
        
        result = cursor.fetchone()
        return result[0] if result else None
    
    def _generate_tonbon_code(self, cursor) -> str:
        """Tạo mã Tồn bồn tự động (TB00001, TB00002...)"""
        cursor.execute(f"""
            SELECT MAX({self._q('Mã tồn bồn')}) 
            FROM {self._q('TonBon')} 
            WHERE {self._q('Mã tồn bồn')} LIKE 'TB%%'
        """)
        
        result = cursor.fetchone()[0]
        
        if result:
            try:
                last_num = int(result[2:])
                next_num = last_num + 1
            except:
                next_num = 1
        else:
            next_num = 1
        
        return f"TB{next_num:05d}"
    
    def _delete_old_import(self, cursor, ngay_kiem: str):
        """
        Xóa mềm dữ liệu tồn bồn cũ theo ngày (để import lại)
        
        Args:
            cursor: Database cursor
            ngay_kiem: Ngày kiểm kho (YYYY-MM-DD)
        """
        _p = self._ph()
        da_xoa_val = "'1'" if self._is_pg else "1"
        cursor.execute(f"""
            UPDATE {self._q('TonBon')} 
            SET {self._q('Đã xóa')} = {da_xoa_val}, 
                {self._q('Người sửa')} = 'system_reimport',
                {self._q('Thời gian sửa')} = {self._now_func()}
            WHERE {self._q('Ngày kiểm kho')} = {_p} AND {self._da_xoa_check()}
              AND {self._q('Ghi chú')} LIKE '%%Import từ%%'
        """, (ngay_kiem,))
        
        return cursor.rowcount
    
    def _log_import(
        self, 
        filename: str, 
        loai_file: str,
        so_luong: int,
        ngay_email: Optional[str] = None,
        nguoi_import: Optional[str] = None
    ):
        """Ghi log import vào database"""
        self._ensure_import_log_table()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Thêm timestamp để tránh trùng tên file
        timestamp = datetime.now().strftime('%H%M%S')
        unique_filename = f"{filename}_{timestamp}"
        
        _p = self._ph()
        cursor.execute(f"""
            INSERT INTO {self._q('EmailImportLog')} 
            ({self._q('TenFile')}, {self._q('NgayEmail')}, {self._q('LoaiFile')}, {self._q('SoLuongDong')}, {self._q('NguoiImport')})
            VALUES ({_p}, {_p}, {_p}, {_p}, {_p})
        """, (unique_filename, ngay_email, loai_file, so_luong, nguoi_import))
        
        conn.commit()
        conn.close()
    
    def import_all_days(
        self,
        file_path: str | Path = None,
        nguoi_import: str = "system",
        loai_san_pham: str = "Thành phẩm",
        overwrite: bool = False
    ) -> Dict:
        """
        Import dữ liệu Tồn bồn từ TẤT CẢ các sheet (1-31 ngày) vào database.
        Tự động xác định ngày từ tên sheet + tháng/năm từ tên file.
        
        Args:
            file_path: Đường dẫn file Excel
            nguoi_import: Username người import
            loai_san_pham: Loại sản phẩm (Thành phẩm / Bán thành phẩm)
            overwrite: Nếu True, xóa dữ liệu cũ trước khi import
            
        Returns:
            Dict kết quả: {success, not_found, errors, total, days_imported}
        """
        file_path = Path(file_path or self.DEFAULT_FILE)
        filename = file_path.name
        
        # Đọc tất cả sheets với ngày
        df = self.read_all_sheets_with_dates(file_path)
        
        if len(df) == 0:
            return {
                'success': 0,
                'not_found': [],
                'errors': ["Không tìm thấy dữ liệu trong file"],
                'total': 0,
                'days_imported': 0
            }
        
        # Đếm số ngày
        unique_days = df['Ngày'].nunique()
        print(f"📊 Đọc được {len(df)} dòng từ {unique_days} ngày")
        
        # Xóa dữ liệu cũ nếu overwrite
        if overwrite:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Lấy danh sách các ngày sẽ import
            days_to_delete = df['Ngày'].unique().tolist()
            deleted_total = 0
            
            for ngay in days_to_delete:
                deleted = self._delete_old_import(cursor, ngay)
                deleted_total += deleted
            
            conn.commit()
            conn.close()
            
            if deleted_total > 0:
                print(f"🗑️ Đã xóa mềm {deleted_total} record cũ")
        
        # Import dữ liệu (có cột Ngày trong df)
        result = self.import_tonbon(
            file_path=file_path,
            ngay_kiem=None,  # Không dùng, lấy từ df
            nguoi_import=nguoi_import,
            loai_san_pham=loai_san_pham,
            overwrite=False,  # Đã xóa ở trên
            _df_override=df  # Pass df đã có Ngày
        )
        
        result['days_imported'] = unique_days
        return result
    
    def import_tonbon(
        self,
        file_path: str | Path = None,
        sheet_name: str = None,
        ngay_kiem: str = None,
        nguoi_import: str = "system",
        loai_san_pham: str = "Thành phẩm",
        overwrite: bool = False,
        _df_override: pd.DataFrame = None  # Internal: dữ liệu đã đọc sẵn
    ) -> Dict:
        """
        Import dữ liệu Tồn bồn từ Excel vào database
        
        Args:
            file_path: Đường dẫn file Excel
            sheet_name: Tên sheet (không dùng - đọc từ các sheet số)
            ngay_kiem: Ngày kiểm kho (YYYY-MM-DD), nếu None sẽ lấy từ dữ liệu
            nguoi_import: Username người import
            loai_san_pham: Loại sản phẩm (Thành phẩm / Bán thành phẩm)
            overwrite: Nếu True, xóa dữ liệu cũ trước khi import
            _df_override: DataFrame đã đọc sẵn (internal use)
            
        Returns:
            Dict kết quả: {success, not_found, errors, total}
        """
        file_path = Path(file_path or self.DEFAULT_FILE)
        filename = file_path.name
        
        # Sử dụng df đã có hoặc đọc mới
        if _df_override is not None:
            df = _df_override
        else:
            # Nếu không có ngày_kiem và không có df_override → đọc all sheets
            if not ngay_kiem:
                df = self.read_all_sheets_with_dates(file_path)
            else:
                # Đọc từ 1 sheet cụ thể (legacy mode)
                df = self.read_direct_from_cells(file_path)
                if len(df) > 0:
                    df['Ngày'] = ngay_kiem
        
        if len(df) == 0:
            return {
                'success': 0,
                'not_found': [],
                'errors': ["Không tìm thấy dữ liệu trong file"],
                'total': 0
            }
        
        print(f"📊 Đọc được {len(df)} mã sản phẩm từ file")
        
        # Ngày mặc định nếu không có trong df
        if 'Ngày' not in df.columns:
            if not ngay_kiem:
                ngay_kiem = datetime.now().strftime('%Y-%m-%d')
            df['Ngày'] = ngay_kiem
        
        # Kết nối database
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Xóa dữ liệu cũ nếu overwrite
        if overwrite:
            unique_days = df['Ngày'].unique()
            for day in unique_days:
                deleted = self._delete_old_import(cursor, day)
                if deleted > 0:
                    print(f"🗑️ Đã xóa mềm {deleted} record cũ (ngày {day})")
        
        thoi_gian_tao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        success_count = 0
        not_found = []
        errors = []
        
        # Lặp qua DataFrame
        for _, row in df.iterrows():
            try:
                code_cam = row['Code cám']
                so_luong = row['Số lượng (kg)']
                so_bon = row.get('Số bồn', 'Import')
                ngay_row = row.get('Ngày', ngay_kiem or datetime.now().strftime('%Y-%m-%d'))
                
                # Tìm ID sản phẩm
                id_sanpham = self._get_product_id(cursor, code_cam)
                
                if not id_sanpham:
                    if code_cam not in not_found:
                        not_found.append(code_cam)
                    continue
                
                # Bỏ qua nếu số lượng = 0
                if so_luong <= 0:
                    continue
                
                # Tạo mã tự động
                ma_tonbon = self._generate_tonbon_code(cursor)
                
                # Insert vào TonBon
                _p = self._ph()
                da_xoa_val = "'0'" if self._is_pg else "0"
                cursor.execute(f"""
                    INSERT INTO {self._q('TonBon')} 
                    ({self._q('Mã tồn bồn')}, {self._q('Ngày kiểm kho')}, {self._q('ID sản phẩm')}, 
                     {self._q('Loại sản phẩm')}, {self._q('Số lượng (kg)')}, {self._q('Số bồn')},
                     {self._q('Trạng thái')}, {self._q('Kích cỡ đóng bao')}, {self._q('Ca sản xuất')},
                     {self._q('Ghi chú')}, {self._q('Người tạo')}, {self._q('Thời gian tạo')}, {self._q('Đã xóa')})
                    VALUES ({_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {da_xoa_val})
                """, (
                    ma_tonbon,
                    ngay_row,
                    id_sanpham,
                    loai_san_pham,
                    so_luong,
                    so_bon if so_bon else 'N/A',
                    'Chờ xử lý',
                    'N/A',
                    'Import',
                    f"Import từ {filename}",
                    nguoi_import,
                    thoi_gian_tao
                ))
                
                success_count += 1
                
            except Exception as e:
                errors.append(f"{code_cam}: {e}")
        
        conn.commit()
        conn.close()
        
        # Ghi log
        if success_count > 0:
            unique_days = df['Ngày'].nunique() if 'Ngày' in df.columns else 1
            self._log_import(
                filename=f"TONBON_{unique_days}days_{filename}",
                loai_file='TONBON',
                so_luong=success_count,
                ngay_email=df['Ngày'].max() if 'Ngày' in df.columns else ngay_kiem,
                nguoi_import=nguoi_import
            )
        
        print(f"✅ Import thành công: {success_count}/{len(df)} sản phẩm")
        if not_found:
            print(f"⚠️ Không tìm thấy {len(not_found)} mã: {', '.join(not_found[:5])}...")
        
        return {
            'success': success_count,
            'not_found': list(set(not_found)),  # Unique
            'errors': errors,
            'total': len(df)
        }


def test_tonbon_importer():
    """Test function"""
    print("=" * 60)
    print("🔍 TEST TONBON IMPORTER")
    print("=" * 60)
    
    importer = TonBonImporter()
    
    # Test preview
    print("\n1. Preview dữ liệu...")
    df = importer.preview_data()
    
    if len(df) > 0:
        print(f"   ✅ Đọc được {len(df)} dòng dữ liệu")
        print(df.head(10))
    else:
        print("   ⚠️ Không có dữ liệu (chạy VBA TongHopBaoCaoCam() trước)")


if __name__ == "__main__":
    test_tonbon_importer()
