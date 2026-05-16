"""
Admin API Routes - Users, Roles, Settings, Tables, Stats
Port từ Streamlit admin modules sang Flask API
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import login_required
from backend import db
from backend.utils import hashpw, get_vietnam_time

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    """Decorator yêu cầu quyền admin (phinho hoặc kde)"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        username = session.get('username', '')
        if username not in ['phinho', 'kde', 'admin']:
            return jsonify({"error": "Không có quyền truy cập"}), 403
        return f(*args, **kwargs)
    return decorated


# ==================== Dashboard Stats ====================

@admin_bp.route('/api/admin/stats', methods=['GET'])
@login_required
def get_stats():
    """Lấy thống kê tổng quan cho dashboard"""
    try:
        stats = {}

        # Số sản phẩm
        try:
            stats['products'] = db.get_total_count('tbdat_SanPham', col_where={'Đã xóa': ('=', 0)})
        except:
            stats['products'] = 0

        # Số đơn hàng
        try:
            stats['orders'] = db.get_total_count('tbdat_DatHang', col_where={'Đã xóa': ('=', 0)})
        except:
            stats['orders'] = 0

        # Số users
        try:
            stats['users'] = db.get_total_count('tbsys_Users', col_where={'Đã xóa': ('=', 0)})
        except:
            stats['users'] = 0

        # Số vai trò
        try:
            stats['roles'] = db.get_total_count('tbsys_VaiTro', col_where={'Đã xóa': ('=', 0)})
        except:
            stats['roles'] = 0

        # Số batching
        try:
            stats['batching'] = db.get_total_count('tbdat_Batching', col_where={'Đã xóa': ('=', 0)})
        except:
            stats['batching'] = 0

        # Số stock
        try:
            stats['stock'] = db.get_total_count('tbdat_StockHomNay', col_where={'Đã xóa': ('=', 0)})
        except:
            stats['stock'] = 0

        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ==================== Users Management ====================

@admin_bp.route('/api/admin/users', methods=['GET'])
@login_required
@admin_required
def get_users():
    """Lấy danh sách users"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '')

        search_columns = ['Username', 'Fullname', 'Email', 'Số điện thoại']

        total = db.get_total_count(
            'tbsys_Users',
            col_where={'Đã xóa': ('=', 0)},
            search_value=search if search else None,
            search_columns=search_columns if search else None
        )

        df = db.get_columns_data(
            table_name='tbsys_Users',
            columns=['ID', 'Username', 'Fullname', 'Email', 'Số điện thoại', 'Giới tính', 'ID_VaiTro', 'Địa chỉ', 'Người tạo', 'Thời gian tạo'],
            col_where={'Đã xóa': ('=', 0)},
            col_order={'ID': 'DESC'},
            page_number=page,
            rows_per_page=per_page,
            search_value=search if search else None,
            search_columns=search_columns if search else None,
            joins=[{
                'from_table': 'tbsys_Users',
                'table': 'tbsys_VaiTro',
                'alias': 'tbsys_VaiTro',
                'on': {'ID_VaiTro': 'ID'},
                'columns': ['Vai trò']
            }]
        )

        data = df.to_dict('records') if not df.empty else []
        # Rename join columns
        for row in data:
            if 'tbsys_VaiTro_Vai trò' in row:
                row['Vai trò'] = row.pop('tbsys_VaiTro_Vai trò')

        return jsonify({
            "data": data,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (total + per_page - 1) // per_page)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/api/admin/users', methods=['POST'])
@login_required
@admin_required
def add_user():
    """Thêm user mới"""
    try:
        data = request.get_json()
        username = data.get('Username', '').strip()
        password = data.get('Password', '').strip()
        fullname = data.get('Fullname', '').strip()

        if not username or not password or not fullname:
            return jsonify({"success": False, "message": "Username, Password, Họ tên là bắt buộc"}), 400

        cols = ['Username', 'Password', 'Fullname', 'Email', 'Số điện thoại', 'Giới tính', 'ID_VaiTro', 'Địa chỉ', 'Người tạo']
        vals = [
            username,
            hashpw(password),
            fullname,
            data.get('Email', ''),
            data.get('Số điện thoại', ''),
            data.get('Giới tính', 'Nam'),
            data.get('ID_VaiTro', '1'),
            data.get('Địa chỉ', ''),
            session.get('username', '')
        ]

        result = db.insert_data_to_table('tbsys_Users', cols, vals)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@admin_bp.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def update_user(user_id):
    """Cập nhật user"""
    try:
        data = request.get_json()
        allowed_fields = ['Username', 'Fullname', 'Email', 'Số điện thoại', 'Giới tính', 'ID_VaiTro', 'Địa chỉ']
        update_data = {k: v for k, v in data.items() if k in allowed_fields}

        if not update_data:
            return jsonify({"success": False, "message": "Không có dữ liệu để cập nhật"}), 400

        result = db.update_data_by_id('tbsys_Users', user_id, update_data, session.get('username', ''))
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@admin_bp.route('/api/admin/users/delete', methods=['POST'])
@login_required
@admin_required
def delete_users():
    """Soft delete users"""
    try:
        data = request.get_json()
        ids = data.get('ids', [])
        if not ids:
            return jsonify({"success": False, "message": "Chưa chọn user để xóa"}), 400

        result = db.delete_data_by_ids('tbsys_Users', ids, session.get('username', ''))
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@admin_bp.route('/api/admin/users/reset-password/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def reset_password(user_id):
    """Reset password cho user"""
    try:
        data = request.get_json()
        new_password = data.get('password', '').strip()
        if not new_password:
            return jsonify({"success": False, "message": "Password không được trống"}), 400

        result = db.update_data_by_id('tbsys_Users', user_id, {'Password': hashpw(new_password)}, session.get('username', ''))
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ==================== Roles Management ====================

@admin_bp.route('/api/admin/roles', methods=['GET'])
@login_required
@admin_required
def get_roles():
    """Lấy danh sách vai trò"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '')

        total = db.get_total_count(
            'tbsys_VaiTro',
            col_where={'Đã xóa': ('=', 0)},
            search_value=search if search else None,
            search_columns=['Vai trò'] if search else None
        )

        df = db.get_columns_data(
            table_name='tbsys_VaiTro',
            columns=['ID', 'Vai trò', 'Thứ tự ưu tiên', 'Người tạo', 'Thời gian tạo', 'Người sửa', 'Thời gian sửa'],
            col_where={'Đã xóa': ('=', 0)},
            col_order={'ID': 'ASC'},
            page_number=page,
            rows_per_page=per_page,
            search_value=search if search else None,
            search_columns=['Vai trò'] if search else None
        )

        data = df.to_dict('records') if not df.empty else []
        return jsonify({
            "data": data,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (total + per_page - 1) // per_page)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/api/admin/roles/list', methods=['GET'])
@login_required
def get_roles_list():
    """Lấy danh sách vai trò cho select box (không cần admin)"""
    try:
        df = db.get_columns_data(
            table_name='tbsys_VaiTro',
            columns=['ID', 'Vai trò'],
            col_where={'Đã xóa': ('=', 0)},
            col_order={'ID': 'ASC'}
        )
        data = df.to_dict('records') if not df.empty else []
        return jsonify({"roles": data})
    except Exception as e:
        return jsonify({"roles": []}), 500


@admin_bp.route('/api/admin/roles', methods=['POST'])
@login_required
@admin_required
def add_role():
    """Thêm vai trò mới"""
    try:
        data = request.get_json()
        name = data.get('Vai trò', '').strip()
        priority = data.get('Thứ tự ưu tiên', 1)

        if not name:
            return jsonify({"success": False, "message": "Tên vai trò là bắt buộc"}), 400

        cols = ['Vai trò', 'Thứ tự ưu tiên', 'Người tạo']
        vals = [name, priority, session.get('username', '')]

        result = db.insert_data_to_table('tbsys_VaiTro', cols, vals)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@admin_bp.route('/api/admin/roles/<int:role_id>', methods=['PUT'])
@login_required
@admin_required
def update_role(role_id):
    """Cập nhật vai trò"""
    try:
        data = request.get_json()
        allowed = ['Vai trò', 'Thứ tự ưu tiên']
        update_data = {k: v for k, v in data.items() if k in allowed}

        if not update_data:
            return jsonify({"success": False, "message": "Không có dữ liệu cập nhật"}), 400

        result = db.update_data_by_id('tbsys_VaiTro', role_id, update_data, session.get('username', ''))
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@admin_bp.route('/api/admin/roles/delete', methods=['POST'])
@login_required
@admin_required
def delete_roles():
    """Soft delete vai trò"""
    try:
        data = request.get_json()
        ids = data.get('ids', [])
        if not ids:
            return jsonify({"success": False, "message": "Chưa chọn vai trò để xóa"}), 400

        result = db.delete_data_by_ids('tbsys_VaiTro', ids, session.get('username', ''))
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ==================== Settings Management ====================

@admin_bp.route('/api/admin/settings', methods=['GET'])
@login_required
@admin_required
def get_settings():
    """Lấy tất cả cài đặt"""
    try:
        # Ensure config table exists
        _ensure_config_table()

        df = db.get_columns_data(
            table_name='tbsys_config',
            columns=['config_key', 'config_value']
        )
        if df.empty:
            return jsonify({"settings": {}})

        settings = {}
        for _, row in df.iterrows():
            settings[row['config_key']] = row['config_value']

        return jsonify({"settings": settings})
    except Exception as e:
        return jsonify({"settings": {}, "error": str(e)}), 500


@admin_bp.route('/api/admin/settings', methods=['POST'])
@login_required
@admin_required
def save_settings():
    """Lưu cài đặt"""
    try:
        data = request.get_json()
        settings = data.get('settings', {})

        success_count = 0
        error_count = 0

        for key, value in settings.items():
            try:
                # Check existing
                existing = db.query_database(
                    f"SELECT config_value FROM tbsys_config WHERE config_key = {db._ph()}",
                    data_type='value',
                    params=(key,)
                )

                if existing is not None:
                    db.query_database(
                        f"UPDATE tbsys_config SET config_value = {db._ph()} WHERE config_key = {db._ph()}",
                        params=(value, key)
                    )
                else:
                    db.query_database(
                        f"INSERT INTO tbsys_config (config_key, config_value) VALUES ({db._ph()}, {db._ph()})",
                        params=(key, value)
                    )
                success_count += 1
            except Exception:
                error_count += 1

        return jsonify({
            "success": True,
            "message": f"Đã cập nhật {success_count} cài đặt" + (f", {error_count} lỗi" if error_count else "")
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ==================== Tables Management ====================

@admin_bp.route('/api/admin/tables', methods=['GET'])
@login_required
@admin_required
def get_tables():
    """Lấy danh sách bảng trong database"""
    try:
        conn = db.connect_db()
        cursor = conn.cursor()

        if db._db_type == 'postgres':
            cursor.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
            )
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")

        rows = cursor.fetchall()
        tables = []
        for row in rows:
            table_name = row[0]
            if table_name.startswith('sqlite_'):
                continue
            # Get column count
            try:
                cols = db._get_column_names(cursor, table_name)
                col_count = len(cols)
            except:
                col_count = 0
                cols = []

            # Get row count
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {db._q(table_name)}")
                count_row = cursor.fetchone()
                row_count = count_row[0] if count_row else 0
            except:
                row_count = 0

            tables.append({
                'name': table_name,
                'columns': col_count,
                'rows': row_count,
                'column_names': cols
            })

        conn.close()
        return jsonify({"tables": tables})
    except Exception as e:
        return jsonify({"tables": [], "error": str(e)}), 500


@admin_bp.route('/api/admin/tables/<table_name>/columns', methods=['GET'])
@login_required
@admin_required
def get_table_columns(table_name):
    """Lấy thông tin cột của một bảng"""
    try:
        conn = db.connect_db()
        cursor = conn.cursor()
        col_info = db._get_table_columns_info(cursor, table_name)
        conn.close()
        columns = [{"name": name, "type": dtype} for name, dtype in col_info.items()]
        return jsonify({"columns": columns, "table": table_name})
    except Exception as e:
        return jsonify({"columns": [], "error": str(e)}), 500


def _ensure_config_table():
    """Đảm bảo bảng config tồn tại"""
    try:
        if db._db_type == 'sqlite':
            existing = db.query_database(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                data_type='value',
                params=('tbsys_config',)
            )
        else:
            existing = db.query_database(
                "SELECT table_name FROM information_schema.tables WHERE table_name = %s",
                data_type='value',
                params=('tbsys_config',)
            )

        if not existing:
            if db._db_type == 'sqlite':
                db.query_database("""
                    CREATE TABLE IF NOT EXISTS tbsys_config (
                        config_key TEXT PRIMARY KEY,
                        config_value TEXT
                    )
                """)
            else:
                db.query_database("""
                    CREATE TABLE IF NOT EXISTS tbsys_config (
                        config_key TEXT PRIMARY KEY,
                        config_value TEXT
                    )
                """)
            # Insert defaults
            defaults = {
                "project_name": "Kế hoạch Sản xuất",
                "style_container_bg": "#2E3440",
                "style_icon_color": "#88C0D0",
                "style_nav_link_selected_bg": "#81A1C1",
            }
            for key, val in defaults.items():
                db.query_database(
                    f"INSERT INTO tbsys_config (config_key, config_value) VALUES ({db._ph()}, {db._ph()})",
                    params=(key, val)
                )
    except Exception as e:
        print(f"Config table init error: {e}")
