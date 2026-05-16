"""
Utilities for database operations - Test Cân Reports
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import base64


def get_db_connection(db_path: str = "database.db"):
    """Tạo kết nối đến database"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Trả về dict thay vì tuple
    return conn


def init_testcan_tables(db_path: str = "database.db"):
    """Khởi tạo bảng lưu báo cáo Test Cân"""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Tạo bảng báo cáo Test Cân
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS TestCan_Reports (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        Datetime TEXT NOT NULL,
        Value_502 TEXT,
        Value_505 TEXT,
        Value_508 TEXT,
        Value_574 TEXT,
        Image_Data TEXT,
        Image_Filename TEXT,
        Created_By TEXT,
        Created_At DATETIME DEFAULT CURRENT_TIMESTAMP,
        Notes TEXT,
        Email_Sent INTEGER DEFAULT 0,
        Email_Recipients TEXT,
        Is_Valid INTEGER DEFAULT 1
    )
    """)
    
    # Tạo index cho tìm kiếm nhanh
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_testcan_datetime 
    ON TestCan_Reports(Datetime)
    """)
    
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_testcan_created_at 
    ON TestCan_Reports(Created_At DESC)
    """)
    
    conn.commit()
    conn.close()


def save_testcan_report(
    datetime_value: str,
    value_502: str,
    value_505: str,
    value_508: str,
    value_574: str,
    image_bytes: bytes,
    image_filename: str,
    created_by: str = "system",
    notes: str = "",
    email_sent: bool = False,
    email_recipients: str = "",
    is_valid: bool = True,
    db_path: str = "database.db"
) -> int:
    """
    Lưu báo cáo Test Cân vào database
    
    Returns:
        ID của record vừa tạo
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Convert image bytes to base64 string
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    
    cursor.execute("""
    INSERT INTO TestCan_Reports (
        Datetime, Value_502, Value_505, Value_508, Value_574,
        Image_Data, Image_Filename, Created_By, Notes,
        Email_Sent, Email_Recipients, Is_Valid
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime_value, value_502, value_505, value_508, value_574,
        image_base64, image_filename, created_by, notes,
        1 if email_sent else 0, email_recipients, 1 if is_valid else 0
    ))
    
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return record_id


def get_testcan_reports(
    limit: int = 50,
    offset: int = 0,
    order_by: str = "Created_At DESC",
    db_path: str = "database.db"
) -> List[Dict]:
    """
    Lấy danh sách báo cáo Test Cân
    
    Args:
        limit: Số lượng record tối đa
        offset: Bỏ qua bao nhiêu record
        order_by: Sắp xếp theo cột nào
        
    Returns:
        List of dict records
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    query = f"""
    SELECT 
        ID, Datetime, Value_502, Value_505, Value_508, Value_574,
        Image_Filename, Created_By, Created_At, Notes,
        Email_Sent, Email_Recipients, Is_Valid
    FROM TestCan_Reports
    ORDER BY {order_by}
    LIMIT ? OFFSET ?
    """
    
    cursor.execute(query, (limit, offset))
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_testcan_report_by_id(report_id: int, db_path: str = "database.db") -> Optional[Dict]:
    """Lấy 1 báo cáo theo ID (bao gồm cả image data)"""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT * FROM TestCan_Reports WHERE ID = ?
    """, (report_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def get_testcan_image_bytes(report_id: int, db_path: str = "database.db") -> Optional[bytes]:
    """Lấy image bytes từ database"""
    report = get_testcan_report_by_id(report_id, db_path)
    if report and report.get('Image_Data'):
        return base64.b64decode(report['Image_Data'])
    return None


def delete_testcan_report(report_id: int, db_path: str = "database.db") -> bool:
    """Xóa báo cáo theo ID"""
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM TestCan_Reports WHERE ID = ?", (report_id,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def search_testcan_reports(
    datetime_from: str = None,
    datetime_to: str = None,
    created_by: str = None,
    is_valid: bool = None,
    limit: int = 50,
    db_path: str = "database.db"
) -> List[Dict]:
    """
    Tìm kiếm báo cáo với điều kiện
    
    Args:
        datetime_from: Từ thời gian (format: YYYY-MM-DD hoặc YYYY-MM-DD HH:MM:SS)
        datetime_to: Đến thời gian
        created_by: Người tạo
        is_valid: Chỉ lấy báo cáo hợp lệ
        limit: Số lượng tối đa
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    conditions = []
    params = []
    
    if datetime_from:
        conditions.append("Datetime >= ?")
        params.append(datetime_from)
    
    if datetime_to:
        conditions.append("Datetime <= ?")
        params.append(datetime_to)
    
    if created_by:
        conditions.append("Created_By = ?")
        params.append(created_by)
    
    if is_valid is not None:
        conditions.append("Is_Valid = ?")
        params.append(1 if is_valid else 0)
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    query = f"""
    SELECT 
        ID, Datetime, Value_502, Value_505, Value_508, Value_574,
        Image_Filename, Created_By, Created_At, Notes,
        Email_Sent, Email_Recipients, Is_Valid
    FROM TestCan_Reports
    WHERE {where_clause}
    ORDER BY Created_At DESC
    LIMIT ?
    """
    
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_testcan_stats(db_path: str = "database.db") -> Dict:
    """Lấy thống kê báo cáo"""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as total FROM TestCan_Reports")
    total = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as valid FROM TestCan_Reports WHERE Is_Valid = 1")
    valid = cursor.fetchone()['valid']
    
    cursor.execute("SELECT COUNT(*) as sent FROM TestCan_Reports WHERE Email_Sent = 1")
    sent = cursor.fetchone()['sent']
    
    cursor.execute("""
    SELECT Datetime FROM TestCan_Reports 
    ORDER BY Created_At DESC LIMIT 1
    """)
    latest = cursor.fetchone()
    latest_datetime = latest['Datetime'] if latest else None
    
    conn.close()
    
    return {
        'total_reports': total,
        'valid_reports': valid,
        'email_sent': sent,
        'latest_datetime': latest_datetime
    }
