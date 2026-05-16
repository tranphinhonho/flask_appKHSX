"""
Module import dữ liệu từ file FFSTOCK Excel vào database
Parse theo logic VBA: BRAN (hàng 13+) và INTGRATE (hàng 10+)
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
from utils import get_db_connection, is_postgres, q, ph


class StockImporter:
    """Class xử lý import FFSTOCK Excel vào database"""
    
    # Cấu hình sheet nguồn
    SHEET_BRAN = "BRAN"
    SHEET_INTGRATE = "INTGRATE"
    
    # Hàng bắt đầu dữ liệu (0-indexed)
    START_ROW_BRAN = 12       # Hàng 13 trong Excel
    START_ROW_INTGRATE = 9    # Hàng 10 trong Excel
    
    # Mapping cột cho sheet BRAN (0-indexed: A=0, B=1, ...)
    # Code cám ở cột W=22
    COL_MAPPING_BRAN = {
        'code_cam': 22,       # Cột W - Code cám
        'ten_cam': 1,         # Cột B - Tên cám
        'kich_co_ep': 2,      # Cột C - Kích cỡ ép viên
        'kich_co_bao': 3,     # Cột D - Kích cỡ đóng bao (25/40/50)
        'ton_kho_bao': 12,    # Cột M - Tồn kho (bao)
        'ton_kho_kg': 13,     # Cột N - Tồn kho (kg)
        'day_on_hand': 18,    # Cột S - Day on hand
    }
    
    # Mapping cột cho sheet INTGRATE (khác với BRAN!)
    # Code cám ở cột Z=25, Tồn kho ở cột O=14 (bao) và P=15 (kg)
    COL_MAPPING_INTGRATE = {
        'code_cam': 25,       # Cột Z - Code cám (khác với BRAN!)
        'ten_cam': 1,         # Cột B - Tên cám
        'kich_co_ep': 2,      # Cột C - Kích cỡ ép viên
        'kich_co_bao': 3,     # Cột D - Kích cỡ đóng bao (25/40/50)
        'ton_kho_bao': 14,    # Cột O - Tồn kho (bao) - KHÁC BRAN!
        'ton_kho_kg': 15,     # Cột P - Tồn kho (kg) - KHÁC BRAN!
        'day_on_hand': 20,    # Cột U - Day on hand
    }
    
    # Kích cỡ bao hợp lệ
    VALID_PACK_SIZES = [25, 40, 50]
    
    def __init__(self, db_path: str = "database_new.db"):
        """
        Khởi tạo StockImporter
        
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
        self._ensure_import_log_table()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            f'SELECT "ID" FROM "EmailImportLog" WHERE "TenFile" = {self._ph()}',
            (filename,)
        )
        
        result = cursor.fetchone()
        conn.close()
        
        return result is not None
    
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
        
        _p = self._ph()
        cursor.execute(f"""
            INSERT INTO "EmailImportLog" 
            ("TenFile", "NgayEmail", "LoaiFile", "SoLuongDong", "NguoiImport")
            VALUES ({_p}, {_p}, {_p}, {_p}, {_p})
        """, (filename, ngay_email, loai_file, so_luong, nguoi_import))
        
        conn.commit()
        conn.close()
    
    def _delete_old_import(self, filename: str):
        """
        Xóa dữ liệu import cũ trước khi import lại
        
        Args:
            filename: Tên file đã import
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Lấy thông tin log cũ
        cursor.execute(f"""
            SELECT "NgayEmail" FROM "EmailImportLog" WHERE "TenFile" = {self._ph()}
        """, (filename,))
        result = cursor.fetchone()
        
        if result:
            ngay_email = result[0]
            
            # Xóa các record StockOld theo ngày
            # Lưu ý: Xóa mềm (set Đã xóa = 1)
            cursor.execute(f"""
                UPDATE {self._q('StockOld')} 
                SET {self._q('Đã xóa')} = '1', 
                    {self._q('Người sửa')} = 'system_reimport',
                    {self._q('Thời gian sửa')} = {self._now_func()}
                WHERE {self._q('Ngày stock old')} = {self._ph()}
            """, (ngay_email,))
            
            deleted_count = cursor.rowcount
            print(f"[DEL] Da xoa mem {deleted_count} record StockOld cu (ngay {ngay_email})")
            
            # Xóa log import cũ
            cursor.execute(f"""
                DELETE FROM "EmailImportLog" WHERE "TenFile" = {self._ph()}
            """, (filename,))
            print(f"[DEL] Da xoa log import cu: {filename}")
        
        conn.commit()
        conn.close()
    
    def _get_product_id(self, cursor, code_cam: str, ten_cam: str = None) -> Optional[int]:
        """Tìm ID sản phẩm từ Code cám và Tên cám
        
        Ưu tiên tìm kiếm:
        1. Khớp chính xác cả Code cám VÀ Tên cám (cho trường hợp nhiều SP cùng Code)
        2. Khớp theo Code cám
        3. Khớp theo Tên cám
        """
        code = code_cam.strip() if code_cam else ""
        ten = ten_cam.strip() if ten_cam else ""
        
        # 1. Thử tìm theo cả Code cám VÀ Tên cám (ưu tiên cao nhất)
        if code and ten:
            _p = self._ph()
            cursor.execute(f"""
                SELECT {self._q('ID')} 
                FROM {self._q('SanPham')} 
                WHERE TRIM({self._q('Code cám')}) = {_p} AND UPPER(TRIM({self._q('Tên cám')})) = UPPER({_p}) AND {self._da_xoa_check()}
            """, (code, ten))
            result = cursor.fetchone()
            if result:
                return result[0]
        
        # 2. Thử tìm theo Tên cám trước (vì nhiều SP có thể cùng Code)
        if ten:
            cursor.execute(f"""
                SELECT {self._q('ID')} 
                FROM {self._q('SanPham')} 
                WHERE UPPER(TRIM({self._q('Tên cám')})) = UPPER({self._ph()}) AND {self._da_xoa_check()}
            """, (ten,))
            result = cursor.fetchone()
            if result:
                return result[0]
        
        # 3. Fallback: Tìm theo Code cám
        if code:
            cursor.execute(f"""
                SELECT {self._q('ID')} 
                FROM {self._q('SanPham')} 
                WHERE TRIM({self._q('Code cám')}) = {self._ph()} AND {self._da_xoa_check()}
            """, (code,))
            result = cursor.fetchone()
            if result:
                return result[0]
        
        return None
    
    def _add_missing_product(
        self, 
        cursor, 
        code_cam: str, 
        ten_cam: str, 
        kich_co_ep: str, 
        kich_co_bao: int,
        nguoi_tao: str = "system_auto"
    ) -> Optional[int]:
        """
        Tự động thêm sản phẩm thiếu vào database
        
        Returns:
            ID của sản phẩm vừa thêm, hoặc None nếu lỗi
        """
        try:
            _p = self._ph()
            if self._is_pg:
                cursor.execute(f"""
                    INSERT INTO "SanPham" 
                    ("Code cám", "Tên cám", "Kích cỡ ép viên", "Kích cỡ đóng bao",
                     "Người tạo", "Thời gian tạo", "Đã xóa")
                    VALUES ({_p}, {_p}, {_p}, {_p}, {_p}, NOW(), '0')
                    RETURNING "ID"
                """, (code_cam, ten_cam, kich_co_ep, kich_co_bao, nguoi_tao))
                result = cursor.fetchone()
                return result[0] if result else None
            else:
                cursor.execute(f"""
                    INSERT INTO SanPham 
                    ([Code cám], [Tên cám], [Kích cỡ ép viên], [Kích cỡ đóng bao],
                     [Người tạo], [Thời gian tạo], [Đã xóa])
                    VALUES ({_p}, {_p}, {_p}, {_p}, {_p}, datetime('now'), 0)
                """, (code_cam, ten_cam, kich_co_ep, kich_co_bao, nguoi_tao))
            
            # Lấy ID vừa insert
            return cursor.lastrowid
            
        except Exception as e:
            print(f"❌ Lỗi thêm sản phẩm {code_cam}: {e}")
            return None
    
    def _generate_stock_code(self, cursor) -> str:
        """Tạo mã Stock Old tự động (SO00001, SO00002...)"""
        cursor.execute(f"""
            SELECT MAX({self._q('Mã stock old')}) 
            FROM {self._q('StockOld')} 
            WHERE {self._q('Mã stock old')} LIKE 'SO%'
        """)
        
        result = cursor.fetchone()[0]
        
        if result:
            last_num = int(result[2:])
            next_num = last_num + 1
        else:
            next_num = 1
        
        return f"SO{next_num:05d}"
    
    def _clean_pellet_size(self, value) -> str:
        """Làm sạch kích cỡ ép viên (loại bỏ P và khoảng trắng)"""
        if pd.isna(value):
            return ""
        s = str(value)
        s = s.replace(" ", "").replace("P", "").replace("p", "")
        return s
    
    def preview_data(
        self, 
        file_path: str | Path,
        limit: int = 20
    ) -> Optional[pd.DataFrame]:
        """
        Preview dữ liệu trong file FFSTOCK trước khi import
        
        Args:
            file_path: Đường dẫn file Excel
            limit: Số dòng tối đa hiển thị
            
        Returns:
            DataFrame preview hoặc None nếu lỗi
        """
        file_path = Path(file_path)
        
        try:
            all_data = []
            
            # Đọc sheet BRAN
            try:
                df_bran = pd.read_excel(
                    file_path, 
                    sheet_name=self.SHEET_BRAN,
                    header=None,
                    skiprows=self.START_ROW_BRAN
                )
                data_bran = self._parse_sheet(df_bran, self.SHEET_BRAN)
                all_data.extend(data_bran)
            except:
                pass
            
            # Đọc sheet INTGRATE
            try:
                df_int = pd.read_excel(
                    file_path,
                    sheet_name=self.SHEET_INTGRATE,
                    header=None,
                    skiprows=self.START_ROW_INTGRATE
                )
                data_int = self._parse_sheet(df_int, self.SHEET_INTGRATE)
                all_data.extend(data_int)
            except:
                pass
            
            if not all_data:
                return None
            
            # Tạo DataFrame để hiển thị
            df = pd.DataFrame(all_data[:limit])
            
            # Đổi tên cột và chọn cột quan trọng nhất
            df = df.rename(columns={
                'code_cam': 'Code',
                'ten_cam': 'Tên cám',
                'kich_co_ep': 'Ép viên',
                'kich_co_bao': 'Bao (kg)',
                'ton_kho_kg': 'Tồn (kg)',
                'day_on_hand': 'DOH'
            })
            
            # Chỉ giữ các cột quan trọng và sắp xếp thứ tự
            columns_order = ['Tên cám', 'Bao (kg)', 'Tồn (kg)', 'DOH']
            df = df[[col for col in columns_order if col in df.columns]]
            
            return df
            
        except Exception as e:
            print(f"❌ Lỗi preview: {e}")
            return None
    
    def _parse_sheet(self, df: pd.DataFrame, sheet_name: str) -> List[Dict]:
        """
        Parse dữ liệu từ một sheet
        
        Returns:
            List các dict chứa dữ liệu sản phẩm
        """
        data = []
        
        # Chọn column mapping dựa vào sheet name
        if sheet_name == self.SHEET_INTGRATE:
            col_map = self.COL_MAPPING_INTGRATE
        else:
            col_map = self.COL_MAPPING_BRAN
        
        for idx, row in df.iterrows():
            try:
                # Lấy kích cỡ đóng bao (cột D)
                kich_co_bao = row.iloc[col_map['kich_co_bao']]
                
                # Lọc chỉ lấy 25, 40, 50
                try:
                    kich_co_bao = int(float(kich_co_bao))
                except:
                    continue
                
                if kich_co_bao not in self.VALID_PACK_SIZES:
                    continue
                
                # Lấy tồn kho (kg) - cột N
                ton_kho_kg = row.iloc[col_map['ton_kho_kg']]
                try:
                    ton_kho_kg = int(float(ton_kho_kg))
                except:
                    ton_kho_kg = 0
                
                # Lấy tồn kho bao trước để kiểm tra
                ton_kho_bao = row.iloc[col_map['ton_kho_bao']]
                try:
                    ton_kho_bao_check = int(float(ton_kho_bao))
                except:
                    ton_kho_bao_check = 0
                
                # Bỏ qua nếu cả tồn kho kg và bao đều = 0
                if ton_kho_kg == 0 and ton_kho_bao_check == 0:
                    continue
                
                # Lấy các thông tin khác
                code_cam = row.iloc[col_map['code_cam']]
                if pd.isna(code_cam) or str(code_cam).strip() == "":
                    continue
                code_cam = str(code_cam).strip()
                
                # Lấy tên cám trước để kiểm tra điều kiện loại bỏ
                ten_cam_raw = row.iloc[col_map['ten_cam']]
                ten_cam = str(ten_cam_raw).strip() if not pd.isna(ten_cam_raw) else ""
                
                # Loại bỏ sản phẩm có (5*5)
                if "(5*5)" in ten_cam:
                    continue
                
                kich_co_ep = self._clean_pellet_size(
                    row.iloc[col_map['kich_co_ep']]
                )
                
                ton_kho_bao = row.iloc[col_map['ton_kho_bao']]
                try:
                    ton_kho_bao = int(float(ton_kho_bao))
                except:
                    ton_kho_bao = 0
                
                day_on_hand = row.iloc[col_map['day_on_hand']]
                try:
                    day_on_hand = float(day_on_hand)
                except:
                    day_on_hand = 0.0
                
                data.append({
                    'code_cam': code_cam,
                    'ten_cam': ten_cam,
                    'kich_co_ep': kich_co_ep,
                    'kich_co_bao': kich_co_bao,
                    'ton_kho_bao': ton_kho_bao,
                    'ton_kho_kg': ton_kho_kg,
                    'day_on_hand': day_on_hand,
                    'sheet': sheet_name
                })
                
            except Exception as e:
                print(f"Lỗi parse row {idx}: {e}")
                continue
        
        return data
    
    def import_ffstock(
        self,
        file_path: str | Path,
        nguoi_import: str = "system",
        ngay_stock: Optional[str] = None,
        overwrite: bool = False,
        auto_add_missing: bool = True
    ) -> Dict:
        """
        Import file FFSTOCK vào database StockOld
        
        Args:
            file_path: Đường dẫn file Excel
            nguoi_import: Username người import
            ngay_stock: Ngày stock (YYYY-MM-DD), mặc định là hôm nay
            overwrite: Nếu True, xóa dữ liệu cũ trước khi import lại
            auto_add_missing: Nếu True, tự động thêm sản phẩm thiếu vào database
            
        Returns:
            Dict kết quả: {success, not_found, errors, ma_stock_old, auto_added}
        """
        file_path = Path(file_path)
        filename = file_path.name
        
        # Kiểm tra trùng lặp
        is_duplicate = self.check_duplicate(filename)
        
        if is_duplicate and not overwrite:
            return {
                'success': 0,
                'not_found': [],
                'errors': [f"File '{filename}' đã được import trước đó"],
                'ma_stock_old': None,
                'skipped': True
            }
        
        # Nếu overwrite, xóa dữ liệu cũ
        if is_duplicate and overwrite:
            self._delete_old_import(filename)
        
        # Đọc dữ liệu từ cả 2 sheet
        all_data = []
        
        try:
            # Đọc sheet BRAN
            try:
                df_bran = pd.read_excel(
                    file_path, 
                    sheet_name=self.SHEET_BRAN,
                    header=None,
                    skiprows=self.START_ROW_BRAN
                )
                data_bran = self._parse_sheet(df_bran, self.SHEET_BRAN)
                all_data.extend(data_bran)
                print(f"✅ BRAN: {len(data_bran)} sản phẩm")
            except Exception as e:
                print(f"⚠️ Không đọc được sheet BRAN: {e}")
            
            # Đọc sheet INTGRATE
            try:
                df_int = pd.read_excel(
                    file_path,
                    sheet_name=self.SHEET_INTGRATE,
                    header=None,
                    skiprows=self.START_ROW_INTGRATE
                )
                data_int = self._parse_sheet(df_int, self.SHEET_INTGRATE)
                all_data.extend(data_int)
                print(f"✅ INTGRATE: {len(data_int)} sản phẩm")
            except Exception as e:
                print(f"⚠️ Không đọc được sheet INTGRATE: {e}")
                
        except Exception as e:
            return {
                'success': 0,
                'not_found': [],
                'errors': [f"Lỗi đọc file Excel: {e}"],
                'ma_stock_old': None,
                'skipped': False
            }
        
        if not all_data:
            return {
                'success': 0,
                'not_found': [],
                'errors': ["Không tìm thấy dữ liệu hợp lệ trong file"],
                'ma_stock_old': None,
                'skipped': False
            }
        
        print(f"📊 Tổng cộng: {len(all_data)} sản phẩm cần import")
        
        # Import vào database
        conn = self._get_connection()
        cursor = conn.cursor()
        
        ma_stock_old = self._generate_stock_code(cursor)
        ngay_stock_old = ngay_stock or datetime.now().strftime('%Y-%m-%d')
        thoi_gian_tao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        success_count = 0
        not_found = []
        auto_added = []
        errors = []
        
        for item in all_data:
            try:
                # Tìm ID sản phẩm - truyền cả code_cam và ten_cam
                id_sanpham = self._get_product_id(cursor, item['code_cam'], item['ten_cam'])
                
                # Debug log cho VT products
                if 'VT' in str(item['ten_cam']).upper():
                    print(f"[VT] code={item['code_cam']}, ten={item['ten_cam']}, id={id_sanpham}, kg={item['ton_kho_kg']}")
                
                if not id_sanpham:
                    # Nếu bật auto_add_missing, tự động thêm sản phẩm
                    if auto_add_missing:
                        id_sanpham = self._add_missing_product(
                            cursor,
                            code_cam=item['code_cam'],
                            ten_cam=item['ten_cam'],
                            kich_co_ep=item['kich_co_ep'],
                            kich_co_bao=item['kich_co_bao'],
                            nguoi_tao=nguoi_import
                        )
                        
                        if id_sanpham:
                            auto_added.append({
                                'code': item['code_cam'],
                                'ten': item['ten_cam'],
                                'kich_co_ep': item['kich_co_ep'],
                                'kich_co_bao': item['kich_co_bao']
                            })
                            print(f"✅ Tự động thêm sản phẩm: {item['code_cam']} - {item['ten_cam']}")
                        else:
                            not_found.append(item['code_cam'])
                            continue
                    else:
                        not_found.append(item['code_cam'])
                        continue
                
                # Insert vào StockOld
                _p = self._ph()
                cursor.execute(f"""
                    INSERT INTO {self._q('StockOld')} 
                    ({self._q('ID sản phẩm')}, {self._q('Mã stock old')}, {self._q('Số lượng')}, {self._q('Ngày stock old')}, 
                     {self._q('Ghi chú')}, {self._q('Người tạo')}, {self._q('Thời gian tạo')}, {self._q('Đã xóa')})
                    VALUES ({_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, '0')
                """, (
                    id_sanpham,
                    ma_stock_old,
                    item['ton_kho_kg'],
                    ngay_stock_old,
                    f"Day On Hand: {item['day_on_hand']:.1f} | Bao: {item['ton_kho_bao']}",
                    nguoi_import,
                    thoi_gian_tao
                ))
                
                success_count += 1
                
            except Exception as e:
                errors.append(f"{item['code_cam']}: {e}")
        
        conn.commit()
        conn.close()
        
        # Ghi log import
        if success_count > 0:
            self._log_import(
                filename=filename,
                loai_file='FFSTOCK',
                so_luong=success_count,
                ngay_email=ngay_stock_old,
                nguoi_import=nguoi_import
            )
        
        return {
            'success': success_count,
            'not_found': not_found,
            'auto_added': auto_added,
            'errors': errors,
            'ma_stock_old': ma_stock_old,
            'skipped': False
        }
    
    def get_import_history(self, limit: int = 20) -> List[Dict]:
        """Lấy lịch sử import"""
        self._ensure_import_log_table()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(f"""
            SELECT "ID", "TenFile", "NgayEmail", "LoaiFile", "SoLuongDong", 
                   "ThoiGianImport", "NguoiImport"
            FROM "EmailImportLog"
            ORDER BY "ThoiGianImport" DESC
            LIMIT {self._ph()}
        """, (limit,))
        
        columns = ['ID', 'TenFile', 'NgayEmail', 'LoaiFile', 
                   'SoLuongDong', 'ThoiGianImport', 'NguoiImport']
        
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        conn.close()
        return results


def test_stock_importer():
    """Test function"""
    print("=" * 60)
    print("🔍 TEST STOCK IMPORTER")
    print("=" * 60)
    
    importer = StockImporter()
    
    # Test với file mẫu
    test_file = Path("D:/PYTHON/B7KHSX/EXCEL/FFSTOCK 31-12-2025.xlsm")
    
    if not test_file.exists():
        print(f"❌ File test không tồn tại: {test_file}")
        return
    
    print(f"\n📁 File: {test_file}")
    print(f"📊 Database: {importer.db_path}")
    
    # Kiểm tra duplicate
    if importer.check_duplicate(test_file.name):
        print(f"\n⚠️ File đã được import trước đó!")
        return
    
    print("\n🚀 Bắt đầu import...")
    result = importer.import_ffstock(
        file_path=test_file,
        nguoi_import="test_user"
    )
    
    print(f"\n📊 KẾT QUẢ:")
    print(f"   ✅ Thành công: {result['success']}")
    print(f"   ⚠️ Không tìm thấy: {len(result['not_found'])}")
    print(f"   ❌ Lỗi: {len(result['errors'])}")
    print(f"   📦 Mã Stock Old: {result['ma_stock_old']}")
    
    if result['not_found']:
        print(f"\n   Code không tìm thấy (top 10):")
        for code in result['not_found'][:10]:
            print(f"      - {code}")


if __name__ == "__main__":
    test_stock_importer()
