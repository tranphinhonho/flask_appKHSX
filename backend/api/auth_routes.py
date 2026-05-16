"""
Auth API Routes - Login/Logout/User Info
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import authenticate_user, get_user_menu, login_required

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/login', methods=['POST'])
def login():
    """Đăng nhập"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({"success": False, "message": "Vui lòng nhập username và password"}), 400

    user = authenticate_user(username, password)
    if user:
        session['username'] = user['username'].lower()
        session['fullname'] = user['fullname']
        session['id_vaitro'] = user['id_vaitro']
        session.permanent = True
        return jsonify({
            "success": True,
            "user": {
                "username": user['username'],
                "fullname": user['fullname']
            }
        })
    else:
        return jsonify({"success": False, "message": "Username hoặc password không đúng"}), 401


@auth_bp.route('/api/logout', methods=['POST'])
@login_required
def logout():
    """Đăng xuất"""
    session.clear()
    return jsonify({"success": True, "message": "Đã đăng xuất"})


@auth_bp.route('/api/me', methods=['GET'])
@login_required
def get_current_user():
    """Lấy thông tin user hiện tại"""
    return jsonify({
        "username": session.get('username'),
        "fullname": session.get('fullname'),
        "id_vaitro": session.get('id_vaitro')
    })


@auth_bp.route('/api/menu', methods=['GET'])
@login_required
def get_menu():
    """Lấy menu theo vai trò"""
    username = session.get('username')
    menu = get_user_menu(username)

    # Thêm Admin KDE cho admin users
    if username in ['phinho', 'kde', 'admin']:
        menu.append({
            'name': 'Admin KDE',
            'icon': 'person-gear',
            'sub_functions': [
                {'name': 'Tạo bảng', 'module_path': 'Admin.TaoBang'},
                {'name': 'Thêm users', 'module_path': 'Admin.Users'},
                {'name': 'Vai trò', 'module_path': 'Admin.VaiTro'},
                {'name': 'Cài đặt', 'module_path': 'Admin.Settings'},
            ]
        })

    return jsonify({"menu": menu})


@auth_bp.route('/api/debug/menu', methods=['GET'])
@login_required
def debug_menu():
    """Debug endpoint tạm - kiểm tra từng bước load menu"""
    import traceback
    from backend import db
    debug = {}
    username = session.get('username')
    debug['username'] = username
    debug['db_type'] = db._db_type

    try:
        # Step 1: Check tbsys_Users
        vaitro = db.get_columns_data(
            table_name='tbsys_Users',
            columns=['ID_VaiTro'],
            data_type='value',
            col_where={'Username': ('=', username), 'Đã xóa': ('=', 0)}
        )
        debug['step1_vaitro'] = str(vaitro)
        debug['step1_vaitro_type'] = type(vaitro).__name__

        if vaitro is None:
            debug['error'] = 'vaitro is None - user not found or deleted'
            return jsonify(debug)

        # Step 2: Check tbsys_ChucNangTheoVaiTro
        df_cnvt = db.get_columns_data(
            table_name='tbsys_ChucNangTheoVaiTro',
            columns=['ID Vai trò', 'ID Danh sách chức năng'],
            data_type='dataframe',
            col_where={'Đã xóa': ('=', 0), 'ID Vai trò': ('=', vaitro)}
        )
        debug['step2_shape'] = str(df_cnvt.shape)
        debug['step2_columns'] = list(df_cnvt.columns)
        debug['step2_data'] = df_cnvt.head(5).to_dict('records') if not df_cnvt.empty else []

        if df_cnvt.empty:
            # Also check: what's actually in the table?
            df_all = db.get_columns_data(
                table_name='tbsys_ChucNangTheoVaiTro',
                columns=['ID Vai trò', 'ID Danh sách chức năng', 'Đã xóa'],
                data_type='dataframe'
            )
            debug['step2_all_data'] = df_all.head(10).to_dict('records') if not df_all.empty else []
            debug['step2_all_shape'] = str(df_all.shape)
            debug['error'] = 'df_chucnangvaitro is empty'
            return jsonify(debug)

        # Step 3: Check tbsys_DanhSachChucNang
        df_dscn = db.get_columns_data(
            table_name='tbsys_DanhSachChucNang',
            columns=['ID', 'ID Chức năng chính', 'Chức năng con', 'Thứ tự ưu tiên'],
            data_type='dataframe',
            col_where={'Đã xóa': ('=', 0)}
        )
        debug['step3_dscn_shape'] = str(df_dscn.shape)
        debug['step3_dscn_data'] = df_dscn.head(10).to_dict('records') if not df_dscn.empty else []

        # Step 4: Check tbsys_ChucNangChinh
        df_cnc = db.get_columns_data(
            table_name='tbsys_ChucNangChinh',
            columns=['ID', 'Chức năng chính', 'Thứ tự ưu tiên', 'Icon'],
            data_type='dataframe',
            col_where={'Đã xóa': ('=', 0)}
        )
        debug['step4_cnc_shape'] = str(df_cnc.shape)
        debug['step4_cnc_data'] = df_cnc.head(10).to_dict('records') if not df_cnc.empty else []

        # Step 5: Check tbsys_ModuleChucNang
        df_module = db.get_columns_data(
            table_name='tbsys_ModuleChucNang',
            data_type='dataframe',
            col_where={'Đã xóa': ('=', 0)}
        )
        debug['step5_module_shape'] = str(df_module.shape)
        debug['step5_module_data'] = df_module.head(10).to_dict('records') if not df_module.empty else []

        # Step 6: Get final menu
        from backend.auth import get_user_menu
        menu = get_user_menu(username)
        debug['final_menu'] = menu

    except Exception as e:
        debug['error'] = str(e)
        debug['traceback'] = traceback.format_exc()

    return jsonify(debug)
