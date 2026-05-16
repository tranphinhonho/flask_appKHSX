"""
Authentication module - Flask session-based auth
Thay thế streamlit_authenticator
"""
from functools import wraps
from flask import session, redirect, url_for, request, jsonify
from backend import db
from backend.utils import check_password


def login_required(f):
    """Decorator yêu cầu đăng nhập"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({"error": "Chưa đăng nhập"}), 401
            return redirect(url_for('main.login_page'))
        return f(*args, **kwargs)
    return decorated_function


def authenticate_user(username, password):
    """
    Xác thực user từ database.
    Returns: dict với thông tin user hoặc None
    """
    try:
        df = db.get_columns_data(
            table_name='tbsys_Users',
            columns=['Username', 'Password', 'Fullname', 'ID_VaiTro'],
            col_where={'Đã xóa': ('=', 0)}
        )

        if df.empty:
            return None

        user_row = df[df['Username'].str.lower() == username.lower()]
        if user_row.empty:
            return None

        user = user_row.iloc[0]
        stored_password = str(user['Password'])

        # Kiểm tra password (bcrypt hash)
        if check_password(password, stored_password):
            return {
                'username': user['Username'],
                'fullname': user['Fullname'],
                'id_vaitro': str(user['ID_VaiTro'])
            }
        return None

    except Exception as e:
        print(f"Auth error: {e}")
        return None


def get_user_menu(username):
    """
    Lấy menu theo vai trò của user.
    Port logic từ main.py (dòng 144-183)
    Returns: list of {main_function, icon, sub_functions: [...]}
    """
    def _debug(msg):
        """Safe print that won't crash on Windows cp1252"""
        try:
            print(msg)
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                print(msg.encode('utf-8', errors='replace').decode('ascii', errors='replace'))
            except Exception:
                pass

    try:
        import traceback
        _debug(f"[MENU DEBUG] === Loading menu for user: '{username}' ===")

        # Lấy vai trò
        vaitro = db.get_columns_data(
            table_name='tbsys_Users',
            columns=['ID_VaiTro'],
            data_type='value',
            col_where={'Username': ('=', username), 'Đã xóa': ('=', 0)}
        )

        _debug(f"[MENU DEBUG] Step 1 - vaitro = {vaitro} (type: {type(vaitro).__name__})")

        if vaitro is None:
            _debug("[MENU DEBUG] vaitro is None -> returning empty menu")
            return []

        # Lấy danh sách chức năng theo vai trò
        df_chucnangvaitro = db.get_columns_data(
            table_name='tbsys_ChucNangTheoVaiTro',
            columns=['ID Vai trò', 'ID Danh sách chức năng'],
            data_type='dataframe',
            col_where={'Đã xóa': ('=', 0), 'ID Vai trò': ('=', vaitro)}
        )

        _debug(f"[MENU DEBUG] Step 2 - df_chucnangvaitro shape: {df_chucnangvaitro.shape}")

        if df_chucnangvaitro.empty:
            _debug("[MENU DEBUG] df_chucnangvaitro is empty -> returning empty menu")
            return []

        # Lấy thông tin chức năng con
        df = db.get_info(
            df_chucnangvaitro,
            table_name='tbsys_DanhSachChucNang',
            columns_name=['ID', 'ID Chức năng chính', 'Chức năng con', 'Thứ tự ưu tiên'],
            columns_map=['ID Danh sách chức năng'],
            columns_key=['ID'],
            columns_output=['ID', 'ID Chức năng chính', 'Chức năng con', 'Thứ tự ưu tiên con'],
            columns_position=['ID Chức năng chính', 'Chức năng con', 'Thứ tự ưu tiên con']
        )

        _debug(f"[MENU DEBUG] Step 3 - df (sub funcs) shape: {df.shape}")

        # Lấy thông tin chức năng chính
        df_full = db.get_info(
            df,
            table_name='tbsys_ChucNangChinh',
            columns_name=['ID', 'Chức năng chính', 'Thứ tự ưu tiên', 'Icon'],
            columns_map=['ID Chức năng chính'],
            columns_key=['ID'],
            columns_position=['ID Chức năng chính', 'Chức năng chính', 'Thứ tự ưu tiên', 'Chức năng con', 'Thứ tự ưu tiên con', 'Icon']
        )

        _debug(f"[MENU DEBUG] Step 4 - df_full shape: {df_full.shape}")

        df_full = df_full.sort_values(by=['Thứ tự ưu tiên', 'Thứ tự ưu tiên con'], ascending=[True, True])

        # Xây dựng cấu trúc menu
        import math
        menu = []
        seen_main = set()

        for _, row in df_full.iterrows():
            main_func = row.get('Chức năng chính')
            if main_func is None or (isinstance(main_func, float) and math.isnan(main_func)):
                continue

            sub_func = row.get('Chức năng con')
            icon = row.get('Icon', 'circle')

            if isinstance(icon, float) and math.isnan(icon):
                icon = 'circle'

            if main_func not in seen_main:
                seen_main.add(main_func)
                menu.append({
                    'name': main_func,
                    'icon': icon,
                    'sub_functions': []
                })

            # Tìm menu item và thêm sub function
            for m in menu:
                if m['name'] == main_func:
                    if sub_func and not (isinstance(sub_func, float) and math.isnan(sub_func)):
                        # Lấy module path cho sub function
                        module_path = db.query_database(
                            f"""SELECT T2.[ModulePath]
                                FROM [tbsys_DanhSachChucNang] AS T1
                                LEFT JOIN [tbsys_ModuleChucNang] AS T2 ON CAST(T1.[ID] AS TEXT) = T2.[ID_DanhSachChucNang] AND T2.[Đã xóa] = '0'
                                WHERE TRIM(T1.[Chức năng con]) = ? AND T1.[Đã xóa] = '0'
                                ORDER BY T2.[ModulePath] DESC LIMIT 1""",
                            data_type='value',
                            params=(sub_func.strip(),)
                        )
                        m['sub_functions'].append({
                            'name': sub_func,
                            'module_path': module_path
                        })
                    break

        _debug(f"[MENU DEBUG] Step 5 - Final menu: {len(menu)} groups")

        return menu

    except Exception as e:
        import traceback
        _debug(f"[MENU DEBUG] ERROR: {e}")
        _debug(f"[MENU DEBUG] Traceback:\n{traceback.format_exc()}")
        return []

