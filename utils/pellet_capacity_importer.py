# -*- coding: utf-8 -*-
"""
Module import dữ liệu T/h và Kwh/T từ 7 file vận hành cám viên (PL1-PL7)

Cấu trúc file:
- Tên file: PLx MM.YYYY.xlsx (VD: PL1 1.2026.xlsx = máy Pellet 1, tháng 1/2026)
- Mỗi file có 31 sheets (1-31) tương ứng 31 ngày trong tháng
- Dữ liệu trong mỗi sheet:
  + Cột B (1): Code cám (B10:B44)
  + Cột D (3): Sản lượng (tấn)
  + Cột AU (46): Tổng Kwh tiêu thụ
  + Cột AW (48): T/h (AW10:AW44)
  + Cột AX (49): Kwh/T (AX10:AX44) - hoặc tính = AU/D
"""

from __future__ import annotations
import sqlite3
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
from utils import get_db_connection, is_postgres, q, ph


class PelletCapacityImporter:
    """Import dữ liệu T/h từ file vận hành cám viên PL1-PL7"""
    
    # Vị trí cột CHUNG cho PL1,2,4,5,6,7 (0-indexed)
    COL_CODE_CAM = 1    # Cột B - Code cám
    COL_SAN_LUONG = 3   # Cột D - Sản lượng (tấn)
    COL_THONG_SO_KHUON = 17  # Cột R - Thông số khuôn ép viên
    COL_TOTAL_KWH = 46  # Cột AU - Tổng Kwh tiêu thụ
    COL_T_H = 48        # Cột AW - T/h
    COL_KWH_T = 49      # Cột AX - Kwh/T (hoặc tính từ AU/D)
    
    # Vị trí cột RIÊNG cho PL3 (cấu trúc khác)
    COL_T_H_PL3 = 49        # Cột AX - T/h (thay vì AW)
    COL_KWH_T_PL3 = 50      # Cột AY - Kwh/T (thay vì AX)
    COL_THONG_SO_KHUON_PL3 = 17  # Cột R - Thông số khuôn (giống các máy khác)
    
    # Vùng dữ liệu (0-indexed)
    START_ROW = 9       # Row 10 trong Excel
    END_ROW = 44        # Row 45 trong Excel
    
    def __init__(self, db_path: str = "database_new.db"):
        self.db_path = db_path
        self._is_pg = is_postgres(db_path)
        self._ensure_table()
    
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
    
    def _ensure_table(self):
        """Đảm bảo bảng PelletCapacity tồn tại"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS PelletCapacity (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            [Ngày] DATE,
            [Số máy] TEXT,
            [Code cám] TEXT,
            [Tên cám] TEXT,
            [T/h] REAL,
            [Kwh/T] REAL,
            [Thông số khuôn] TEXT,
            [ID sản phẩm] INTEGER,
            [Số lô] INTEGER DEFAULT 1,
            [Nguồn file] TEXT,
            [Thời gian import] DATETIME,
            [Người import] TEXT,
            [Đã xóa] INTEGER DEFAULT 0
        )
        """)
        
        conn.commit()
        conn.close()
    
    def _extract_machine_and_date(self, filename: str) -> Tuple[str, int, int]:
        """
        Trích xuất số máy và tháng/năm từ tên file
        VD: "PL1 1.2026.xlsx" -> ("PL1", 1, 2026)
        """
        # Pattern: PLx M.YYYY or PLx MM.YYYY
        pattern = r'(PL\d)\s*(\d{1,2})\.(\d{4})'
        match = re.search(pattern, filename, re.IGNORECASE)
        
        if match:
            machine = match.group(1).upper()
            month = int(match.group(2))
            year = int(match.group(3))
            return machine, month, year
        
        raise ValueError(f"Cannot parse filename: {filename}")
    
    def _get_product_id(self, cursor, code_cam: str) -> Optional[int]:
        if not code_cam:
            return None
        code_cam = str(code_cam).strip()
        _p = self._ph()
        
        cursor.execute(f"""
            SELECT {self._q('ID')} FROM {self._q('SanPham')} 
            WHERE {self._q('Code cám')} = {_p} AND {self._da_xoa_check()}
        """, (code_cam,))
        result = cursor.fetchone()
        if result:
            return result[0]
        
        cursor.execute(f"""
            SELECT {self._q('ID')} FROM {self._q('SanPham')} 
            WHERE {self._q('Tên cám')} = {_p} AND {self._da_xoa_check()}
        """, (code_cam,))
        result = cursor.fetchone()
        if result:
            return result[0]
        
        return None
    
    def read_sheet(self, file_path: str | Path, sheet_name: str | int, machine: str = None) -> pd.DataFrame:
        """
        Đọc dữ liệu T/h từ 1 sheet
        
        Args:
            file_path: Đường dẫn file Excel
            sheet_name: Tên sheet (VD: "2" hoặc 2)
            machine: Mã máy (VD: "PL3"). Nếu None, sẽ tự detect từ file name
            
        Returns:
            DataFrame với các cột: Code cám, T/h, Kwh/T
        """
        file_path = Path(file_path)
        
        # Detect machine từ file name nếu không được truyền vào
        if machine is None:
            machine, _, _ = self._extract_machine_and_date(file_path.name)
        
        # Xác định vị trí cột dựa trên máy (PL3 có cấu trúc khác)
        is_pl3 = machine == 'PL3'
        col_t_h = self.COL_T_H_PL3 if is_pl3 else self.COL_T_H
        col_kwh_t = self.COL_KWH_T_PL3 if is_pl3 else self.COL_KWH_T
        col_thong_so_khuon = self.COL_THONG_SO_KHUON_PL3 if is_pl3 else self.COL_THONG_SO_KHUON
        
        try:
            df = pd.read_excel(
                file_path, 
                sheet_name=str(sheet_name), 
                header=None, 
                engine='openpyxl'
            )
        except Exception as e:
            print(f"Error reading sheet {sheet_name}: {e}")
            return pd.DataFrame()
        
        rows = []
        for row_idx in range(self.START_ROW, min(self.END_ROW + 1, len(df))):
            code_cam = df.iloc[row_idx, self.COL_CODE_CAM] if self.COL_CODE_CAM < len(df.columns) else None
            t_h = df.iloc[row_idx, col_t_h] if col_t_h < len(df.columns) else None
            
            # Đọc Kwh/T từ cột tương ứng (AX hoặc AY tùy máy)
            kwh_t = df.iloc[row_idx, col_kwh_t] if col_kwh_t < len(df.columns) else None
            
            # Đọc Thông số khuôn từ cột R (hoặc S cho PL3)
            thong_so_khuon = df.iloc[row_idx, col_thong_so_khuon] if col_thong_so_khuon < len(df.columns) else None
            
            # Nếu cột Kwh/T không có giá trị, tính từ AU/D (Tổng Kwh / Sản lượng)
            if pd.isna(kwh_t) or kwh_t == 0:
                total_kwh = df.iloc[row_idx, self.COL_TOTAL_KWH] if self.COL_TOTAL_KWH < len(df.columns) else None
                san_luong = df.iloc[row_idx, self.COL_SAN_LUONG] if self.COL_SAN_LUONG < len(df.columns) else None
                
                if pd.notna(total_kwh) and pd.notna(san_luong) and san_luong > 0:
                    kwh_t = total_kwh / san_luong
            
            # Chỉ lấy rows có T/h hợp lệ (> 0)
            if pd.notna(t_h) and t_h != 0 and pd.notna(code_cam):
                try:
                    t_h_val = float(t_h)
                    kwh_t_val = float(kwh_t) if pd.notna(kwh_t) else None
                    thong_so_khuon_val = str(thong_so_khuon).strip() if pd.notna(thong_so_khuon) else None
                    
                    if t_h_val > 0:
                        rows.append({
                            'Code cám': str(code_cam).strip(),
                            'T/h': t_h_val,
                            'Kwh/T': kwh_t_val,
                            'Thông số khuôn': thong_so_khuon_val
                        })
                except (ValueError, TypeError):
                    continue
        
        return pd.DataFrame(rows)
    
    def read_all_sheets(self, file_path: str | Path) -> pd.DataFrame:
        """
        Đọc dữ liệu từ tất cả 31 sheets (1-31)
        
        Args:
            file_path: Đường dẫn file Excel
            
        Returns:
            DataFrame với các cột: Ngày, Số máy, Code cám, T/h, Kwh/T
        """
        file_path = Path(file_path)
        machine, month, year = self._extract_machine_and_date(file_path.name)
        
        all_data = []
        
        for day in range(1, 32):
            try:
                df = self.read_sheet(file_path, str(day))
                
                if not df.empty:
                    df['Ngày'] = datetime(year, month, day).strftime('%Y-%m-%d')
                    df['Số máy'] = machine
                    df['Số lô'] = range(1, len(df) + 1)
                    all_data.append(df)
                    
            except Exception as e:
                # Sheet không tồn tại hoặc ngày không hợp lệ (VD: 31/2)
                continue
        
        if all_data:
            result = pd.concat(all_data, ignore_index=True)
            return result
        
        return pd.DataFrame()
    
    def import_file(
        self, 
        file_path: str | Path,
        overwrite: bool = True,
        nguoi_import: str = "System"
    ) -> Dict:
        """
        Import dữ liệu từ 1 file vào database
        
        Args:
            file_path: Đường dẫn file Excel
            overwrite: Nếu True, xóa dữ liệu cũ của tháng này trước khi import
            nguoi_import: Tên người import
            
        Returns:
            Dict với thông tin kết quả
        """
        file_path = Path(file_path)
        
        try:
            machine, month, year = self._extract_machine_and_date(file_path.name)
        except ValueError as e:
            return {
                'success': False,
                'error': str(e),
                'imported': 0
            }
        
        # Đọc dữ liệu
        df = self.read_all_sheets(file_path)
        
        if df.empty:
            return {
                'success': False,
                'error': 'No data found in file',
                'imported': 0
            }
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Xóa dữ liệu cũ nếu overwrite
            if overwrite:
                cursor.execute("""
                    DELETE FROM PelletCapacity 
                    WHERE [Số máy] = ? 
                    AND strftime('%Y-%m', [Ngày]) = ?
                """, (machine, f"{year:04d}-{month:02d}"))
                deleted = cursor.rowcount
            else:
                deleted = 0
            
            # Import dữ liệu mới
            imported = 0
            not_found = []
            
            for _, row in df.iterrows():
                # Tìm ID sản phẩm
                product_id = self._get_product_id(cursor, row['Code cám'])
                
                cursor.execute("""
                    INSERT INTO PelletCapacity 
                    ([Ngày], [Số máy], [Code cám], [T/h], [Kwh/T], 
                     [Thông số khuôn], [ID sản phẩm], [Số lô], [Nguồn file], 
                     [Thời gian import], [Người import])
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row['Ngày'],
                    row['Số máy'],
                    row['Code cám'],
                    row['T/h'],
                    row.get('Kwh/T'),
                    row.get('Thông số khuôn'),
                    product_id,
                    row.get('Số lô', 1),
                    file_path.name,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    nguoi_import
                ))
                imported += 1
                
                if not product_id and row['Code cám'] not in not_found:
                    not_found.append(row['Code cám'])
            
            conn.commit()
            
            return {
                'success': True,
                'machine': machine,
                'month': month,
                'year': year,
                'imported': imported,
                'deleted': deleted,
                'not_found': not_found
            }
            
        except Exception as e:
            conn.rollback()
            return {
                'success': False,
                'error': str(e),
                'imported': 0
            }
        finally:
            conn.close()
    
    def get_optimal_th(
        self, 
        code_cam: str, 
        so_may: str = None
    ) -> Optional[Dict]:
        """
        Lấy T/h tối ưu (cao nhất) và Kwh/T tương ứng cho 1 loại cám
        
        Args:
            code_cam: Code cám
            so_may: Số máy (VD: "PL1"). Nếu None, lấy từ tất cả máy
            
        Returns:
            Dict với T/h tối ưu và Kwh/T
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if so_may:
            cursor.execute("""
                SELECT [T/h], [Kwh/T], [Ngày], [Số máy]
                FROM PelletCapacity
                WHERE [Code cám] = ? AND [Số máy] = ? AND [Đã xóa] = 0
                ORDER BY [T/h] DESC
                LIMIT 1
            """, (code_cam, so_may))
        else:
            cursor.execute("""
                SELECT [T/h], [Kwh/T], [Ngày], [Số máy]
                FROM PelletCapacity
                WHERE [Code cám] = ? AND [Đã xóa] = 0
                ORDER BY [T/h] DESC
                LIMIT 1
            """, (code_cam,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'T/h': result[0],
                'Kwh/T': result[1],
                'Ngày': result[2],
                'Số máy': result[3]
            }
        return None
    
    def get_avg_th_by_machine(self, so_may: str) -> Optional[float]:
        """Lấy T/h trung bình của 1 máy"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT AVG([T/h])
            FROM PelletCapacity
            WHERE [Số máy] = ? AND [Đã xóa] = 0
        """, (so_may,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result and result[0] else None
    
    def get_summary_by_date(self, ngay: str = None) -> pd.DataFrame:
        """
        Lấy tổng hợp T/h theo ngày và máy
        
        Args:
            ngay: Ngày cần lấy (YYYY-MM-DD). Nếu None, lấy ngày gần nhất
        """
        conn = self._get_connection()
        
        if ngay:
            query = """
                SELECT [Số máy], [Code cám], AVG([T/h]) as [Avg T/h], 
                       AVG([Kwh/T]) as [Avg Kwh/T], COUNT(*) as [Số lô]
                FROM PelletCapacity
                WHERE [Ngày] = ? AND [Đã xóa] = 0
                GROUP BY [Số máy], [Code cám]
                ORDER BY [Số máy], [Code cám]
            """
            df = pd.read_sql_query(query, conn, params=(ngay,))
        else:
            query = """
                SELECT [Ngày], [Số máy], [Code cám], AVG([T/h]) as [Avg T/h],
                       AVG([Kwh/T]) as [Avg Kwh/T], COUNT(*) as [Số lô]
                FROM PelletCapacity
                WHERE [Đã xóa] = 0
                GROUP BY [Ngày], [Số máy], [Code cám]
                ORDER BY [Ngày] DESC, [Số máy], [Code cám]
            """
            df = pd.read_sql_query(query, conn)
        
        conn.close()
        return df
    
    def update_sanpham_optimal_th(self) -> Dict:
        """
        Cập nhật cột T/h và Kwh/T trong bảng SanPham 
        với giá trị tối ưu (T/h cao nhất) từ dữ liệu PelletCapacity
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Lấy T/h tối ưu cho từng Code cám
        cursor.execute("""
            SELECT [Code cám], MAX([T/h]) as [Max T/h]
            FROM PelletCapacity
            WHERE [Đã xóa] = 0
            GROUP BY [Code cám]
        """)
        
        optimal_data = cursor.fetchall()
        updated = 0
        
        for code_cam, max_th in optimal_data:
            # Lấy Kwh/T tương ứng với T/h cao nhất
            cursor.execute("""
                SELECT [Kwh/T] FROM PelletCapacity
                WHERE [Code cám] = ? AND [T/h] = ? AND [Đã xóa] = 0
                LIMIT 1
            """, (code_cam, max_th))
            
            kwh_result = cursor.fetchone()
            kwh_t = kwh_result[0] if kwh_result else None
            
            # Cập nhật SanPham
            cursor.execute("""
                UPDATE SanPham
                SET [T/h] = ?, [Kwh/T] = ?
                WHERE ([Code cám] = ? OR [Tên cám] = ?) AND [Đã xóa] = 0
            """, (max_th, kwh_t, code_cam, code_cam))
            
            if cursor.rowcount > 0:
                updated += 1
        
        conn.commit()
        conn.close()
        
        return {
            'success': True,
            'updated': updated,
            'total': len(optimal_data)
        }
    
    def get_all_data(self, limit: int = 500) -> pd.DataFrame:
        """Lấy tất cả dữ liệu PelletCapacity"""
        conn = self._get_connection()
        
        query = """
            SELECT pc.*, sp.[Tên cám] as [Tên sản phẩm]
            FROM PelletCapacity pc
            LEFT JOIN SanPham sp ON pc.[ID sản phẩm] = sp.ID
            WHERE pc.[Đã xóa] = 0
            ORDER BY pc.[Ngày] DESC, pc.[Số máy], pc.[Code cám]
            LIMIT ?
        """
        df = pd.read_sql_query(query, conn, params=(limit,))
        conn.close()
        
        return df
    
    def get_optimal_th_by_day(
        self, 
        code_cam: str, 
        so_may: str
    ) -> Optional[Dict]:
        """
        Lấy T/h tối ưu dựa trên NGÀY CÓ TỔNG T/H CAO NHẤT
        
        Logic:
        1. Tính SUM(T/h) theo từng ngày cho cặp (code_cam, so_may)
        2. Chọn ngày có tổng T/h cao nhất
        3. Trả về SUM(T/h) và AVG(Kwh/T) của ngày đó
        
        Args:
            code_cam: Code cám
            so_may: Số máy (VD: "PL1")
            
        Returns:
            Dict với T/h tổng của ngày tối ưu và Kwh/T trung bình
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Tìm ngày có T/h cao nhất (dùng MAX thay vì SUM)
        cursor.execute("""
            SELECT 
                [Ngày],
                MAX([T/h]) as [Max T/h],
                AVG([Kwh/T]) as [Avg Kwh/T],
                COUNT(*) as [Số lô]
            FROM PelletCapacity
            WHERE [Code cám] = ? AND [Số máy] = ? AND [Đã xóa] = 0
            GROUP BY [Ngày]
            ORDER BY [Max T/h] DESC
            LIMIT 1
        """, (code_cam, so_may))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'Ngày': result[0],
                'T/h': result[1],  # Tổng T/h của ngày tối ưu
                'Kwh/T': result[2],  # Avg Kwh/T của ngày đó
                'Số lô': result[3],
                'Số máy': so_may,
                'Code cám': code_cam
            }
        return None
    
    def get_all_optimal_by_machine(self) -> pd.DataFrame:
        """
        Lấy T/h tối ưu (ngày có tổng T/h cao nhất) cho TẤT CẢ các cặp (Code cám, Số máy)
        
        Returns:
            DataFrame với columns: Số máy, Code cám, T/h, Kwh/T, Ngày tối ưu, Số lô, Vật nuôi
        """
        conn = self._get_connection()
        
        # Subquery để tính tổng T/h theo ngày
        # Sau đó lấy ngày có tổng cao nhất cho mỗi cặp (Số máy, Code cám)
        query = """
            WITH DailyStats AS (
                SELECT 
                    [Số máy],
                    [Code cám],
                    [Ngày],
                    MAX([T/h]) as [Max T/h],
                    AVG([T/h]) as [Avg T/h],
                    AVG([Kwh/T]) as [Avg Kwh/T],
                    COUNT(*) as [Số lô]
                FROM PelletCapacity
                WHERE [Đã xóa] = 0
                GROUP BY [Số máy], [Code cám], [Ngày]
            ),
            BestDay AS (
                SELECT 
                    [Số máy],
                    [Code cám],
                    MAX([Max T/h]) as [Best T/h]
                FROM DailyStats
                GROUP BY [Số máy], [Code cám]
            )
            SELECT 
                ds.[Số máy],
                ds.[Code cám],
                ds.[Max T/h] as [T/h],
                ds.[Avg Kwh/T] as [Kwh/T],
                ds.[Ngày] as [Ngày tối ưu],
                ds.[Số lô],
                sp.[Vật nuôi]
            FROM DailyStats ds
            INNER JOIN BestDay bd 
                ON ds.[Số máy] = bd.[Số máy] 
                AND ds.[Code cám] = bd.[Code cám]
                AND ds.[Max T/h] = bd.[Best T/h]
            LEFT JOIN (
                SELECT DISTINCT [Tên cám], [Vật nuôi] FROM SanPham WHERE [Đã xóa] = 0 AND [Vật nuôi] IS NOT NULL
            ) sp 
                ON ds.[Code cám] = sp.[Tên cám]
            ORDER BY ds.[Số máy], ds.[Code cám]
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        return df
    
    def get_best_machine_for_feed(self, code_cam: str) -> Optional[Dict]:
        """
        Tìm máy tốt nhất cho 1 loại cám (dựa trên T/h cao nhất)
        
        Args:
            code_cam: Code cám
            
        Returns:
            Dict với thông tin máy tốt nhất: Số máy, T/h, Kwh/T, Ngày
        """
        conn = self._get_connection()
        
        query = """
            WITH DailyStats AS (
                SELECT 
                    [Số máy],
                    [Ngày],
                    MAX([T/h]) as [Max T/h],
                    AVG([Kwh/T]) as [Avg Kwh/T]
                FROM PelletCapacity
                WHERE [Code cám] = ? AND [Đã xóa] = 0
                GROUP BY [Số máy], [Ngày]
            )
            SELECT 
                [Số máy],
                [Ngày],
                [Max T/h] as [T/h],
                [Avg Kwh/T] as [Kwh/T]
            FROM DailyStats
            ORDER BY [Max T/h] DESC
            LIMIT 1
        """
        
        cursor = conn.cursor()
        cursor.execute(query, (code_cam,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'Số máy': result[0],
                'Ngày': result[1],
                'T/h': result[2],
                'Kwh/T': result[3]
            }
        return None
    
    def get_all_machines_for_feed(self, code_cam: str) -> pd.DataFrame:
        """
        Lấy T/h tối ưu của TẤT CẢ các máy cho 1 loại cám
        Dùng để fallback khi máy tốt nhất đã full
        
        Args:
            code_cam: Code cám
            
        Returns:
            DataFrame với columns: Số máy, T/h, Kwh/T, Ngày (sắp xếp theo T/h giảm dần)
        """
        conn = self._get_connection()
        
        query = """
            WITH DailyStats AS (
                SELECT 
                    [Số máy],
                    [Ngày],
                    MAX([T/h]) as [Max T/h],
                    AVG([Kwh/T]) as [Avg Kwh/T]
                FROM PelletCapacity
                WHERE [Code cám] = ? AND [Đã xóa] = 0
                GROUP BY [Số máy], [Ngày]
            ),
            BestByMachine AS (
                SELECT 
                    [Số máy],
                    MAX([Max T/h]) as [Best T/h]
                FROM DailyStats
                GROUP BY [Số máy]
            )
            SELECT 
                ds.[Số máy],
                ds.[Max T/h] as [T/h],
                ds.[Avg Kwh/T] as [Kwh/T],
                ds.[Ngày]
            FROM DailyStats ds
            INNER JOIN BestByMachine bm 
                ON ds.[Số máy] = bm.[Số máy] 
                AND ds.[Max T/h] = bm.[Best T/h]
            ORDER BY ds.[Max T/h] DESC
        """
        
        df = pd.read_sql_query(query, conn, params=(code_cam,))
        conn.close()
        
        return df



# Test function
if __name__ == '__main__':
    importer = PelletCapacityImporter()
    
    # Test đọc 1 file
    file_path = 'EXCEL/PL1 1.2026.xlsx'
    
    print("=== Test read sheet 2 ===")
    df = importer.read_sheet(file_path, '2')
    print(df)
    
    print("\n=== Test read all sheets ===")
    df_all = importer.read_all_sheets(file_path)
    print(f"Total records: {len(df_all)}")
    print(df_all.head(10))
