"""
SanPham Backup Utility
Tự động backup bảng SanPham trước mỗi thay đổi (thêm/sửa/xóa/import)
Lưu snapshot JSON vào bảng SanPham_Backup trên PostgreSQL
"""
import json
from datetime import datetime
from backend import db


def _ensure_backup_table():
    """Tạo bảng SanPham_Backup nếu chưa có"""
    conn = db.connect_db()
    cursor = conn.cursor()
    try:
        if db._db_type == 'postgres':
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS "SanPham_Backup" (
                    "ID" SERIAL PRIMARY KEY,
                    "Thời gian" TEXT NOT NULL,
                    "Người thực hiện" TEXT,
                    "Hành động" TEXT,
                    "Số lượng SP" TEXT,
                    "Dữ liệu" TEXT,
                    "Ghi chú" TEXT
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS [SanPham_Backup] (
                    [ID] INTEGER PRIMARY KEY AUTOINCREMENT,
                    [Thời gian] TEXT NOT NULL,
                    [Người thực hiện] TEXT,
                    [Hành động] TEXT,
                    [Số lượng SP] TEXT,
                    [Dữ liệu] TEXT,
                    [Ghi chú] TEXT
                )
            ''')
        conn.commit()
    except Exception as e:
        print(f"[Backup] Error creating table: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()


def backup_sanpham(username, action, ghi_chu=""):
    """
    Backup toàn bộ bảng SanPham active vào SanPham_Backup.
    
    Args:
        username: Người thực hiện thay đổi
        action: Loại hành động (Thêm/Sửa/Xóa/Import)
        ghi_chu: Ghi chú bổ sung
    """
    try:
        _ensure_backup_table()
        
        # Lấy toàn bộ SanPham active
        df = db.get_columns_data(
            table_name='SanPham',
            columns=[
                'ID', 'Code cám', 'Tên cám', 'Kích cỡ ép viên', 'Dạng ép viên',
                'Kích cỡ đóng bao', 'Pellet', 'Packing', 'Batch size', 'Vật nuôi',
                'Người tạo', 'Thời gian tạo', 'Người sửa', 'Thời gian sửa'
            ],
            col_where={'Đã xóa': ('=', 0)},
            col_order={'ID': 'ASC'}
        )
        
        # Chuyển sang JSON
        data_json = df.fillna('').to_json(orient='records', force_ascii=False)
        so_luong = str(len(df))
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Insert backup record
        db.insert_data_to_table(
            'SanPham_Backup',
            ['Thời gian', 'Người thực hiện', 'Hành động', 'Số lượng SP', 'Dữ liệu', 'Ghi chú'],
            [now, username, action, so_luong, data_json, ghi_chu]
        )
        
        print(f"[Backup] ✅ Đã backup {so_luong} SP trước khi {action} bởi {username}")
        return True
        
    except Exception as e:
        print(f"[Backup] ❌ Lỗi backup SanPham: {e}")
        return False


def get_backup_list():
    """Lấy danh sách các bản backup (không kèm dữ liệu chi tiết)"""
    try:
        _ensure_backup_table()
        df = db.get_columns_data(
            table_name='SanPham_Backup',
            columns=['ID', 'Thời gian', 'Người thực hiện', 'Hành động', 'Số lượng SP', 'Ghi chú'],
            col_order={'ID': 'DESC'}
        )
        return df.fillna('').to_dict(orient='records')
    except Exception:
        return []


def get_backup_data(backup_id):
    """Lấy dữ liệu chi tiết của một bản backup"""
    try:
        result = db.get_columns_data(
            table_name='SanPham_Backup',
            columns=['Dữ liệu'],
            data_type='value',
            col_where={'ID': ('=', backup_id)}
        )
        if result:
            return json.loads(result)
        return None
    except Exception:
        return None


def restore_backup(backup_id, username):
    """
    Khôi phục SanPham từ bản backup.
    1. Backup trạng thái hiện tại trước khi restore
    2. Xóa toàn bộ SanPham hiện tại
    3. Insert lại từ backup data
    """
    try:
        # Lấy dữ liệu backup
        data = get_backup_data(backup_id)
        if not data:
            return {"success": False, "message": "Không tìm thấy bản backup"}
        
        # Backup trạng thái hiện tại trước khi restore
        backup_sanpham(username, "Trước khôi phục", f"Khôi phục từ backup #{backup_id}")
        
        # Soft-delete tất cả SP hiện tại
        conn = db.connect_db()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if db._db_type == 'postgres':
            cursor.execute(
                'UPDATE "SanPham" SET "Đã xóa" = \'1\', "Người sửa" = %s, "Thời gian sửa" = %s WHERE "Đã xóa" = \'0\'',
                (username, now)
            )
        else:
            cursor.execute(
                'UPDATE [SanPham] SET [Đã xóa] = 1, [Người sửa] = ?, [Thời gian sửa] = ? WHERE [Đã xóa] = 0',
                (username, now)
            )
        conn.commit()
        conn.close()
        
        # Insert lại từ backup
        import pandas as pd
        df = pd.DataFrame(data)
        
        # Bỏ cột ID (sẽ auto-generate)
        if 'ID' in df.columns:
            df = df.drop(columns=['ID'])
        
        result = db.insert_dataframe_to_table('SanPham', df, created_by=username)
        
        return {
            "success": True, 
            "message": f"Đã khôi phục {len(data)} sản phẩm từ backup #{backup_id}"
        }
        
    except Exception as e:
        return {"success": False, "message": f"Lỗi khôi phục: {str(e)}"}
