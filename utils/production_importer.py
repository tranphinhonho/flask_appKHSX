# -*- coding: utf-8 -*-
"""
Module import dữ liệu từ file PRODUCTION CSV (Batching report) vào database
File format:
- Row 7: Period (Production Report 1/13/2026 6:00 AM - 1/14/2026 6:00 AM)
- Row 10: Formula ID (code sản phẩm)
- Row 11: Description (tên sản phẩm)
- Row 12: Required (kgs) - số lượng cần sản xuất = Batch size
- Row 13: Actual (kgs) - số lượng thực tế
- Row 14: Deviation (kgs) - chênh lệch
- Row 15: % Deviation
"""

from __future__ import annotations
import sqlite3
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import re
from utils import get_db_connection, is_postgres, q, ph, adapt_create_sql


class ProductionImporter:
    """Class xử lý import PRODUCTION CSV vào database Mixer"""
    
    # Danh sách mã sản phẩm bỏ qua (không báo lỗi khi không tìm thấy)
    IGNORED_CODES = ['026903']
    
    def __init__(self, db_path: str = "database_new.db", conn_factory=None):
        self.db_path = db_path
        self._conn_factory = conn_factory
        self._is_pg = is_postgres(db_path)
    
    def _get_connection(self):
        if self._conn_factory:
            return self._conn_factory()
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
    
    def _ensure_import_log_table(self):
        """Tạo bảng EmailImportLog nếu chưa có"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            sql = """
                CREATE TABLE IF NOT EXISTS EmailImportLog (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    TenFile TEXT NOT NULL UNIQUE,
                    NgayEmail DATE,
                    LoaiFile TEXT NOT NULL,
                    SoLuongDong INTEGER DEFAULT 0,
                    ThoiGianImport DATETIME DEFAULT CURRENT_TIMESTAMP,
                    NguoiImport TEXT
                )
            """
            cursor.execute(adapt_create_sql(sql, self.db_path))
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except:
                pass
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
        
        _p = self._ph()
        cursor.execute(
            f'SELECT "ID" FROM "EmailImportLog" WHERE "TenFile" = {_p}',
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
    
    def _delete_old_import(self, filename: str, ngay_san_xuat: str):
        """
        Xóa dữ liệu import cũ trước khi import lại
        
        Args:
            filename: Tên file đã import
            ngay_san_xuat: Ngày sản xuất
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        _p = self._ph()
        da_xoa_val = "'1'" if self._is_pg else "1"
        now_func = "NOW()" if self._is_pg else "datetime('now')"
        cursor.execute(f"""
            UPDATE {self._q('Mixer')} 
            SET {self._q('Đã xóa')} = {da_xoa_val}, 
                {self._q('Người sửa')} = 'system_reimport',
                {self._q('Thời gian sửa')} = {now_func}
            WHERE {self._q('Ngày trộn')} = {_p}
        """, (ngay_san_xuat,))
        
        deleted_count = cursor.rowcount
        print(f"🗑️ Đã xóa mềm {deleted_count} record Mixer cũ (ngày {ngay_san_xuat})")
        
        cursor.execute(f"""
            DELETE FROM "EmailImportLog" WHERE "TenFile" = {_p}
        """, (filename,))
        
        conn.commit()
        conn.close()
    
    def _get_product_id(self, cursor, code_cam: str, ten_cam: str = None) -> Optional[int]:
        """Tìm ID sản phẩm từ Code cám và Tên cám
        
        Ưu tiên tìm kiếm:
        1. Khớp chính xác cả Code cám VÀ Tên cám (cho trường hợp nhiều SP cùng Code)
        2. Khớp theo Tên cám
        3. Khớp theo Code cám
        """
        cleaned_code = code_cam.strip().rstrip('*') if code_cam else ""
        cleaned_ten = ten_cam.strip() if ten_cam else ""
        _p = self._ph()
        
        if cleaned_code and cleaned_ten:
            cursor.execute(f"""
                SELECT {self._q('ID')} 
                FROM {self._q('SanPham')} 
                WHERE TRIM({self._q('Code cám')}) = {_p} AND UPPER(TRIM({self._q('Tên cám')})) = UPPER({_p}) AND {self._da_xoa_check()}
            """, (cleaned_code, cleaned_ten))
            result = cursor.fetchone()
            if result:
                return result[0]
        
        if cleaned_ten:
            cursor.execute(f"""
                SELECT {self._q('ID')} 
                FROM {self._q('SanPham')} 
                WHERE UPPER(TRIM({self._q('Tên cám')})) = UPPER({_p}) AND {self._da_xoa_check()}
            """, (cleaned_ten,))
            result = cursor.fetchone()
            if result:
                return result[0]
        
        if cleaned_code:
            cursor.execute(f"""
                SELECT {self._q('ID')} 
                FROM {self._q('SanPham')} 
                WHERE TRIM({self._q('Code cám')}) = {_p} AND {self._da_xoa_check()}
            """, (cleaned_code,))
            result = cursor.fetchone()
            if result:
                return result[0]
        
        return None
    
    def _generate_mixer_code(self, cursor) -> str:
        cursor.execute(f"""
            SELECT MAX({self._q('Mã mixer')}) 
            FROM {self._q('Mixer')} 
            WHERE {self._q('Mã mixer')} LIKE 'MX%%'
        """)
        result = cursor.fetchone()[0]
        if result:
            last_num = int(result[2:])
            next_num = last_num + 1
        else:
            next_num = 1
        return f"MX{next_num:05d}"
    
    def _extract_date_from_filename(self, filename: str) -> Optional[str]:
        """
        Trích xuất ngày từ tên file
        Ví dụ: PRODUCTION 13.csv → 13
        
        Returns:
            Day number hoặc None
        """
        match = re.search(r'PRODUCTION\s*(\d+)', filename, re.IGNORECASE)
        if match:
            return match.group(1)
        return None
    
    def _extract_date_from_content(self, df: pd.DataFrame) -> Optional[str]:
        """
        Trích xuất ngày từ nội dung file
        Row 7: Production Report 1/13/2026 6:00 AM - 1/14/2026 6:00 AM
        
        Returns:
            Date string format YYYY-MM-DD (ngày bắt đầu)
        """
        try:
            # Đọc hàng 7 (index 6)
            if len(df) > 6:
                period_text = str(df.iloc[6, 0])  # Cột A, hàng 7
                
                # Pattern: m/d/yyyy
                match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})\s+\d+:\d+\s*[AP]M\s*-', period_text)
                if match:
                    month, day, year = match.groups()
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        except Exception as e:
            print(f"Lỗi trích xuất ngày: {e}")
        
        return None
    
    def _parse_production_csv(self, file_path: Path) -> Dict:
        """
        Parse file PRODUCTION CSV
        
        File format: compact CSV with data in rows, comma-separated
        - Line contains "Production Report" with date range
        - Line "Formula ID" followed by comma-separated codes
        - Line "Description" followed by comma-separated descriptions
        - Line "Required" followed by comma-separated kg values
        - Line "Actual" followed by comma-separated kg values
        - Line "Deviation" followed by comma-separated kg values
        - Line "% Deviation" followed by comma-separated percentages
        
        Returns:
            Dict với data và metadata
        """
        # Đọc raw content
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            raw_content = f.read()
        
        # Trích xuất ngày sản xuất từ content
        ngay_san_xuat = None
        date_match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})\s+\d+:\d+\s*[AP]M\s*-', raw_content)
        if date_match:
            month, day, year = date_match.groups()
            ngay_san_xuat = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # Parse các dòng quan trọng
        lines = raw_content.split('\n')
        
        formula_ids = []
        descriptions = []
        required_kgs = []
        actual_kgs = []
        deviation_kgs = []
        deviation_pcts = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split(',')
            
            # Tìm dòng Formula ID
            if 'Formula ID' in line or 'Formula' in parts[0]:
                formula_ids = [p.strip() for p in parts[1:] if p.strip()]
            
            # Tìm dòng Description
            elif 'Description' in parts[0]:
                descriptions = [p.strip() for p in parts[1:] if p.strip() or True][:len(formula_ids)]
            
            # Tìm dòng Required (chứa Kgs hoặc Required)
            elif 'Required' in parts[0] or ('Kgs' in line and 'Actual' not in line and 'Deviation' not in line):
                vals = []
                for p in parts[1:]:
                    try:
                        vals.append(float(p.strip()) if p.strip() else 0)
                    except:
                        pass
                if vals and not required_kgs:
                    required_kgs = vals
            
            # Tìm dòng Actual
            elif 'Actual' in parts[0]:
                vals = []
                for p in parts[1:]:
                    try:
                        vals.append(float(p.strip()) if p.strip() else 0)
                    except:
                        pass
                actual_kgs = vals
            
            # Tìm dòng Deviation (kgs) - không phải % Deviation
            elif 'Deviation' in parts[0] and '%' not in parts[0]:
                vals = []
                for p in parts[1:]:
                    try:
                        vals.append(float(p.strip()) if p.strip() else 0)
                    except:
                        pass
                if vals:
                    deviation_kgs = vals
            
            # Tìm dòng % Deviation
            elif '% Deviation' in parts[0] or 'Deviation' in parts[0] and line.count(',') > 1:
                vals = []
                for p in parts[1:]:
                    try:
                        vals.append(float(p.strip()) if p.strip() else 0)
                    except:
                        pass
                if vals and not deviation_pcts:
                    deviation_pcts = vals
        
        # Nếu không tìm được bằng cách trên, thử cách khác - parse toàn bộ số
        if not formula_ids:
            # Tìm pattern số 6 chữ số (formula ID)
            all_codes = re.findall(r'\b(\d{6})\b', raw_content)
            # Loại bỏ các số trông giống ngày tháng
            formula_ids = [c for c in all_codes if not c.startswith('20')]
        
        # Build products list (raw, chưa gộp)
        raw_products = []
        
        for i, code in enumerate(formula_ids):
            if not code.strip():
                continue
            
            try:
                code_cam = str(code).strip()
                # Loại bỏ dấu * để chuẩn hóa mã (ví dụ: 312101* -> 312101)
                cleaned_code = code_cam.rstrip('*')
                
                description = descriptions[i] if i < len(descriptions) else ''
                batch_size = required_kgs[i] if i < len(required_kgs) else 0
                actual = actual_kgs[i] if i < len(actual_kgs) else 0
                loss_kg = deviation_kgs[i] if i < len(deviation_kgs) else 0
                loss_pct = deviation_pcts[i] if i < len(deviation_pcts) else 0
                
                # Bỏ qua nếu batch_size = 0
                if batch_size == 0:
                    continue
                
                # Lấy giá trị tuyệt đối của loss
                loss_kg = abs(loss_kg)
                loss_pct = abs(loss_pct)
                
                raw_products.append({
                    'code_cam': cleaned_code,  # Sử dụng mã đã chuẩn hóa
                    'original_code': code_cam,  # Giữ mã gốc để tham khảo
                    'description': description,
                    'batch_size': batch_size,
                    'actual': actual,
                    'loss_kg': loss_kg,
                    'loss_pct': loss_pct
                })
                
            except Exception as e:
                print(f"Lỗi parse mã {code}: {e}")
                continue
        
        # Gộp sản lượng cho các mã giống nhau (ví dụ: 312101 và 312101* -> 1 record)
        aggregated = {}
        for item in raw_products:
            code = item['code_cam']
            if code in aggregated:
                # Cộng dồn sản lượng
                aggregated[code]['batch_size'] += item['batch_size']
                aggregated[code]['actual'] += item['actual']
                aggregated[code]['loss_kg'] += item['loss_kg']
                # Ghi nhận có gộp
                aggregated[code]['merged_count'] += 1
            else:
                aggregated[code] = {
                    'code_cam': code,
                    'description': item['description'],
                    'batch_size': item['batch_size'],
                    'actual': item['actual'],
                    'loss_kg': item['loss_kg'],
                    'loss_pct': 0,  # Sẽ tính lại sau
                    'merged_count': 1
                }
        
        # Tính lại loss_pct sau khi gộp
        products = []
        for code, data in aggregated.items():
            if data['batch_size'] > 0:
                data['loss_pct'] = abs(data['loss_kg'] / data['batch_size'] * 100)
            products.append(data)
        
        # Log thông tin gộp
        merged_codes = [p['code_cam'] for p in products if p.get('merged_count', 1) > 1]
        if merged_codes:
            print(f"🔗 Đã gộp sản lượng cho các mã: {', '.join(merged_codes)}")
        
        print(f"📊 CSV Parser found: {len(formula_ids)} codes → {len(products)} products (sau khi gộp)")
        
        return {
            'ngay_san_xuat': ngay_san_xuat,
            'products': products,
            'total_products': len(products)
        }
    
    def import_production(
        self,
        file_path: str | Path,
        nguoi_import: str = "system",
        ngay_san_xuat: Optional[str] = None,
        overwrite: bool = False
    ) -> Dict:
        """
        Import file PRODUCTION CSV vào database Mixer
        
        Args:
            file_path: Đường dẫn file CSV
            nguoi_import: Username người import
            ngay_san_xuat: Ngày sản xuất (YYYY-MM-DD), mặc định trích từ file
            overwrite: Nếu True, xóa dữ liệu cũ trước khi import lại
            
        Returns:
            Dict kết quả: {success, not_found, errors, skipped}
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
                'skipped': True
            }
        
        # Parse file
        try:
            parsed = self._parse_production_csv(file_path)
        except Exception as e:
            return {
                'success': 0,
                'not_found': [],
                'errors': [f"Lỗi đọc file CSV: {e}"],
                'skipped': False
            }
        
        # Sử dụng ngày từ file hoặc tham số
        ngay_sx = ngay_san_xuat or parsed['ngay_san_xuat'] or datetime.now().strftime('%Y-%m-%d')
        
        # Nếu overwrite, xóa dữ liệu cũ
        if is_duplicate and overwrite:
            self._delete_old_import(filename, ngay_sx)
        
        products = parsed['products']
        
        if not products:
            return {
                'success': 0,
                'not_found': [],
                'errors': ["Không tìm thấy dữ liệu sản phẩm trong file"],
                'skipped': False
            }
        
        print(f"📊 Tổng cộng: {len(products)} sản phẩm cần import")
        
        # Import vào database
        conn = self._get_connection()
        cursor = conn.cursor()
        
        thoi_gian_tao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        success_count = 0
        not_found = []
        errors = []
        
        for item in products:
            try:
                # Tìm ID sản phẩm - truyền cả code_cam và description
                id_sanpham = self._get_product_id(cursor, item['code_cam'], item.get('description', ''))
                
                if not id_sanpham:
                    # Bỏ qua mã trong danh sách IGNORED_CODES
                    if item['code_cam'] not in self.IGNORED_CODES:
                        not_found.append(item['code_cam'])
                    continue
                
                # Tạo mã Mixer
                ma_mixer = self._generate_mixer_code(cursor)
                
                # Xác định đích đến dựa trên description
                # Mặc định là Pellet, nếu có chữ M trong description -> Packing
                description_upper = item['description'].upper()
                if ' M ' in description_upper or description_upper.endswith(' M'):
                    dich_den = 'Packing'
                    so_may = 'Packing 3'
                else:
                    dich_den = 'Pellet'
                    so_may = 'Pellet 1'  # Mặc định
                
                # Insert vào Mixer
                _p = self._ph()
                da_xoa_val = "'0'" if self._is_pg else "0"
                cursor.execute(f"""
                    INSERT INTO {self._q('Mixer')} 
                    ({self._q('Mã mixer')}, {self._q('Ngày trộn')}, {self._q('ID sản phẩm')}, {self._q('Batch size')}, 
                     {self._q('Số lượng thực tế')}, {self._q('Loss (kg)')}, "Loss (%%)",
                     {self._q('Đích đến')}, {self._q('Số máy')}, {self._q('Ca sản xuất')}, {self._q('Ghi chú')},
                     {self._q('Người tạo')}, {self._q('Thời gian tạo')}, {self._q('Đã xóa')})
                    VALUES ({_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {da_xoa_val})
                """, (
                    ma_mixer,
                    ngay_sx,
                    id_sanpham,
                    item['batch_size'],
                    item['actual'],
                    item['loss_kg'],
                    item['loss_pct'],
                    dich_den,
                    so_may,
                    'Import',
                    f"Import từ {filename}",
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
                loai_file='PRODUCTION',
                so_luong=success_count,
                ngay_email=ngay_sx,
                nguoi_import=nguoi_import
            )
        
        return {
            'success': success_count,
            'not_found': not_found,
            'errors': errors,
            'ngay_san_xuat': ngay_sx,
            'skipped': False
        }
    
    def _parse_production_xlsm(self, file_path: Path, ngay_san_xuat: Optional[str] = None) -> Dict:
        """
        Parse file PRODUCTION XLSM (đã chạy VBA TransposeReport)
        
        Cấu trúc sau VBA:
        - Cột CA (index 78): Code cám (Formula ID)
        - Cột CB (index 79): Description (mô tả gốc)
        - Cột CC (index 80): Khối lượng yêu cầu (Required kgs)
        - Cột CD (index 81): Khối lượng thực tế (Actual kgs)
        - Cột CE (index 82): Sai lệch kg (Deviation kgs)
        - Cột CF (index 83): % sai lệch (% Deviation)
        
        Returns:
            Dict với data và metadata
        """
        # Đọc file Excel
        df = pd.read_excel(file_path, header=None, sheet_name=0)
        
        products = []
        
        # Cột CA-CF tương ứng index 78-83
        # Bắt đầu từ hàng 2 (index 1) vì hàng 1 là header
        for idx in range(1, len(df)):
            try:
                row = df.iloc[idx]
                
                # Code cám (cột CA, index 78)
                code_cam = row.iloc[78] if len(row) > 78 else None
                if pd.isna(code_cam) or str(code_cam).strip() == '':
                    continue
                
                code_cam = str(code_cam).strip()
                
                # Description (cột CB, index 79)
                description = str(row.iloc[79]).strip() if len(row) > 79 and not pd.isna(row.iloc[79]) else ''
                
                # Tính tên cám từ description (phần đầu trước space)
                ten_cam = description.split(' ')[0] if description else code_cam
                
                # Tính ngày công thức từ description (phần thứ 2 sau space)
                parts = description.split()
                ngay_cong_thuc = parts[1] if len(parts) > 1 else None
                
                # Required kgs (cột CC, index 80)
                try:
                    batch_size = float(row.iloc[80]) if len(row) > 80 and not pd.isna(row.iloc[80]) else 0
                except:
                    batch_size = 0
                
                # Actual kgs (cột CD, index 81)
                try:
                    actual = float(row.iloc[81]) if len(row) > 81 and not pd.isna(row.iloc[81]) else 0
                except:
                    actual = 0
                
                # Deviation kgs (cột CE, index 82)
                try:
                    loss_kg = float(row.iloc[82]) if len(row) > 82 and not pd.isna(row.iloc[82]) else 0
                except:
                    loss_kg = 0
                
                # % Deviation (cột CF, index 83)
                try:
                    loss_pct = float(row.iloc[83]) if len(row) > 83 and not pd.isna(row.iloc[83]) else 0
                except:
                    loss_pct = 0
                
                # Bỏ qua nếu batch_size = 0
                if batch_size == 0:
                    continue
                
                # Đảo dấu loss (thường âm trong Excel)
                loss_kg = abs(loss_kg)
                loss_pct = abs(loss_pct)
                
                products.append({
                    'code_cam': code_cam,
                    'ten_cam': ten_cam,
                    'ngay_cong_thuc': ngay_cong_thuc,
                    'description': description,
                    'batch_size': batch_size,
                    'actual': actual,
                    'loss_kg': loss_kg,
                    'loss_pct': loss_pct
                })
                
            except Exception as e:
                print(f"Lỗi parse hàng {idx}: {e}")
                continue
        
        return {
            'ngay_san_xuat': ngay_san_xuat,
            'products': products,
            'total_products': len(products)
        }
    
    def preview_production_xlsm(self, file_path: str | Path) -> pd.DataFrame:
        """
        Preview dữ liệu từ file PRODUCTION XLSM (đã chạy VBA)
        
        Returns:
            DataFrame với các cột: Code cám, Tên cám, Ngày CT, Required, Actual, Deviation, %
        """
        file_path = Path(file_path)
        
        try:
            parsed = self._parse_production_xlsm(file_path)
            products = parsed['products']
            
            if not products:
                return pd.DataFrame()
            
            # Tạo DataFrame để preview
            df = pd.DataFrame([
                {
                    'Code cám': p['code_cam'],
                    'Tên cám': p['ten_cam'],
                    'Ngày CT': p['ngay_cong_thuc'] or '',
                    'Required (kg)': p['batch_size'],
                    'Actual (kg)': p['actual'],
                    'Deviation (kg)': p['loss_kg'],
                    'Deviation (%)': p['loss_pct']
                }
                for p in products
            ])
            
            return df
            
        except Exception as e:
            print(f"Lỗi preview XLSM: {e}")
            return pd.DataFrame()
    
    def import_production_xlsm(
        self,
        file_path: str | Path,
        nguoi_import: str = "system",
        ngay_san_xuat: Optional[str] = None,
        overwrite: bool = False
    ) -> Dict:
        """
        Import file PRODUCTION XLSM (đã chạy VBA) vào database Mixer
        
        Args:
            file_path: Đường dẫn file XLSM
            nguoi_import: Username người import
            ngay_san_xuat: Ngày sản xuất (YYYY-MM-DD)
            overwrite: Nếu True, xóa dữ liệu cũ trước khi import lại
            
        Returns:
            Dict kết quả: {success, not_found, errors, skipped}
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
                'skipped': True
            }
        
        # Parse file
        try:
            parsed = self._parse_production_xlsm(file_path, ngay_san_xuat)
        except Exception as e:
            return {
                'success': 0,
                'not_found': [],
                'errors': [f"Lỗi đọc file XLSM: {e}"],
                'skipped': False
            }
        
        # Sử dụng ngày từ tham số hoặc hôm nay
        ngay_sx = ngay_san_xuat or datetime.now().strftime('%Y-%m-%d')
        
        # Nếu overwrite, xóa dữ liệu cũ
        if is_duplicate and overwrite:
            self._delete_old_import(filename, ngay_sx)
        
        products = parsed['products']
        
        if not products:
            return {
                'success': 0,
                'not_found': [],
                'errors': ["Không tìm thấy dữ liệu sản phẩm trong file"],
                'skipped': False
            }
        
        print(f"📊 XLSM: Tổng cộng {len(products)} sản phẩm cần import")
        
        # Import vào database
        conn = self._get_connection()
        cursor = conn.cursor()
        
        thoi_gian_tao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        success_count = 0
        not_found = []
        errors = []
        
        for item in products:
            try:
                # Tìm ID sản phẩm - truyền cả code_cam và ten_cam
                id_sanpham = self._get_product_id(cursor, item['code_cam'], item.get('ten_cam', ''))
                
                if not id_sanpham:
                    # Bỏ qua mã trong danh sách IGNORED_CODES
                    if item['code_cam'] not in self.IGNORED_CODES:
                        not_found.append(item['code_cam'])
                    continue
                
                # Tạo mã Mixer
                ma_mixer = self._generate_mixer_code(cursor)
                
                # Xác định đích đến dựa trên description
                description_upper = item['description'].upper()
                if ' M ' in description_upper or description_upper.endswith(' M'):
                    dich_den = 'Packing'
                    so_may = 'Packing 3'
                else:
                    dich_den = 'Pellet'
                    so_may = 'Pellet 1'
                
                # Insert vào Mixer
                _p = self._ph()
                da_xoa_val = "'0'" if self._is_pg else "0"
                cursor.execute(f"""
                    INSERT INTO {self._q('Mixer')} 
                    ({self._q('Mã mixer')}, {self._q('Ngày trộn')}, {self._q('ID sản phẩm')}, {self._q('Batch size')}, 
                     {self._q('Số lượng thực tế')}, {self._q('Loss (kg)')}, {self._q('Loss (%)')},
                     {self._q('Đích đến')}, {self._q('Số máy')}, {self._q('Ca sản xuất')}, {self._q('Ghi chú')},
                     {self._q('Người tạo')}, {self._q('Thời gian tạo')}, {self._q('Đã xóa')})
                    VALUES ({_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {_p}, {da_xoa_val})
                """, (
                    ma_mixer,
                    ngay_sx,
                    id_sanpham,
                    item['batch_size'],
                    item['actual'],
                    item['loss_kg'],
                    item['loss_pct'],
                    dich_den,
                    so_may,
                    'Import',
                    f"Import XLSM từ {filename}",
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
                loai_file='PRODUCTION_XLSM',
                so_luong=success_count,
                ngay_email=ngay_sx,
                nguoi_import=nguoi_import
            )
        
        return {
            'success': success_count,
            'not_found': not_found,
            'errors': errors,
            'ngay_san_xuat': ngay_sx,
            'skipped': False
        }
    
    def get_import_history(self, limit: int = 20) -> List[Dict]:
        """Lấy lịch sử import PRODUCTION"""
        self._ensure_import_log_table()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        _p = self._ph()
        cursor.execute(f"""
            SELECT ID, TenFile, NgayEmail, LoaiFile, SoLuongDong, 
                   ThoiGianImport, NguoiImport
            FROM EmailImportLog
            WHERE LoaiFile = 'PRODUCTION'
            ORDER BY ThoiGianImport DESC
            LIMIT {_p}
        """, (limit,))
        
        columns = ['ID', 'TenFile', 'NgayEmail', 'LoaiFile', 
                   'SoLuongDong', 'ThoiGianImport', 'NguoiImport']
        
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        conn.close()
        return results


def test_production_importer():
    """Test function"""
    print("=" * 60)
    print("🔍 TEST PRODUCTION IMPORTER")
    print("=" * 60)
    
    importer = ProductionImporter()
    
    # Test với file mẫu
    test_file = Path("D:/PYTHON/B7KHSX/downloads/PRODUCTION 13.csv")
    
    if not test_file.exists():
        print(f"❌ File test không tồn tại: {test_file}")
        return
    
    print(f"\n📁 File: {test_file}")
    
    # Kiểm tra duplicate
    if importer.check_duplicate(test_file.name):
        print(f"\n⚠️ File đã được import trước đó!")
        return
    
    print("\n🚀 Bắt đầu import...")
    result = importer.import_production(
        file_path=test_file,
        nguoi_import="test_user"
    )
    
    print(f"\n📊 KẾT QUẢ:")
    print(f"   ✅ Thành công: {result['success']}")
    print(f"   ⚠️ Không tìm thấy: {len(result['not_found'])}")
    print(f"   ❌ Lỗi: {len(result['errors'])}")
    print(f"   📅 Ngày SX: {result.get('ngay_san_xuat')}")
    
    if result['not_found']:
        print(f"\n   Code không tìm thấy:")
        for code in result['not_found'][:20]:
            print(f"      - {code}")


if __name__ == "__main__":
    test_production_importer()
