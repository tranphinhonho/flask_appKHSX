"""
API routes cho module Đặt hàng (DatHang)
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import login_required
from backend import db
from backend.utils import get_vietnam_time
import pandas as pd

dathang_bp = Blueprint('dathang', __name__)


@dathang_bp.route('/api/dathang', methods=['GET'])
@login_required
def get_dathang_list():
    """Lấy danh sách đơn đặt hàng với phân trang, tìm kiếm, lọc theo ngày lấy"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    ngay_lay = request.args.get('ngay_lay', '').strip()

    col_where = {'Đã xóa': ('=', 0)}
    if ngay_lay and ngay_lay != 'all':
        col_where['Ngày lấy'] = ('=', ngay_lay)

    # JOIN SanPham để lấy Code cám, Tên cám
    joins = [{
        'table': 'SanPham',
        'on': {'ID sản phẩm': 'ID'},
        'columns': ['Code cám', 'Tên cám', 'Dạng ép viên', 'Kích cỡ ép viên']
    }]

    search_columns = ['Mã đặt hàng', 'SanPham.Tên cám', 'SanPham.Code cám', 'Loại đặt hàng'] if search else None

    # Get total count (without join, just base table)
    total = db.get_total_count(
        table_name='DatHang',
        col_where=col_where,
        search_value=search if search else None,
        search_columns=['Mã đặt hàng', 'Loại đặt hàng'] if search else None
    )

    # Get paginated data with JOIN
    df = db.get_columns_data(
        table_name='DatHang',
        columns=['ID', 'ID sản phẩm', 'Mã đặt hàng', 'Loại đặt hàng', 'Số lượng',
                 'Ngày đặt', 'Ngày lấy', 'Khách vãng lai', 'Ghi chú',
                 'Người tạo', 'Thời gian tạo'],
        col_where=col_where,
        col_order={'ID': 'DESC'},
        page_number=page,
        rows_per_page=per_page,
        search_value=search if search else None,
        search_columns=['Mã đặt hàng', 'Loại đặt hàng'] if search else None,
        joins=joins
    )

    data = df.to_dict('records') if not df.empty else []

    # Rename join columns
    for row in data:
        row['Code cám'] = row.pop('SanPham_Code cám', '')
        row['Tên cám'] = row.pop('SanPham_Tên cám', '')
        row['Dạng ép viên'] = row.pop('SanPham_Dạng ép viên', '')
        row['Kích cỡ ép viên'] = row.pop('SanPham_Kích cỡ ép viên', '')

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    return jsonify({
        'data': data,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages
    })


@dathang_bp.route('/api/dathang/ngay-lay', methods=['GET'])
@login_required
def get_ngay_lay_list():
    """Lấy danh sách các ngày lấy có trong database"""
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT [Ngày lấy]
        FROM DatHang
        WHERE [Đã xóa] = 0 AND [Ngày lấy] IS NOT NULL
        ORDER BY [Ngày lấy] DESC
    """)
    result = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()
    return jsonify({'ngay_lay': result})


@dathang_bp.route('/api/dathang/next-code', methods=['GET'])
@login_required
def get_next_code():
    """Lấy mã đặt hàng tiếp theo"""
    code = db.generate_next_code('DatHang', 'Mã đặt hàng', 'DH', 5)
    return jsonify({'code': code})


@dathang_bp.route('/api/dathang/products', methods=['GET'])
@login_required
def get_products_for_select():
    """Lấy danh sách sản phẩm cho dropdown chọn"""
    search = request.args.get('search', '').strip()

    col_where = {'Đã xóa': ('=', 0)}
    df = db.get_columns_data(
        table_name='SanPham',
        columns=['ID', 'Code cám', 'Tên cám', 'Kích cỡ ép viên', 'Dạng ép viên'],
        col_where=col_where,
        col_order={'Tên cám': 'ASC'},
        page_number=1,
        rows_per_page=1000,
        search_value=search if search else None,
        search_columns=['Code cám', 'Tên cám'] if search else None
    )

    data = df.to_dict('records') if not df.empty else []
    return jsonify({'products': data})


@dathang_bp.route('/api/dathang', methods=['POST'])
@login_required
def add_dathang():
    """Thêm đơn đặt hàng mới (hỗ trợ nhiều sản phẩm trong 1 đơn)"""
    payload = request.get_json()
    items = payload.get('items', [])
    loai = payload.get('loai_dathang', 'Khách vãng lai')
    khach_vang_lai = 1 if loai == 'Khách vãng lai' else 0

    if not items:
        return jsonify({'success': False, 'message': 'Không có sản phẩm'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time()
    ma_dathang = db.generate_next_code('DatHang', 'Mã đặt hàng', 'DH', 5)

    success_count = 0
    errors = []

    for item in items:
        id_sp = item.get('id_sanpham')
        so_luong = item.get('so_luong', 0)
        ngay_lay = item.get('ngay_lay')
        ghi_chu = item.get('ghi_chu', '')

        if not id_sp or so_luong <= 0:
            continue

        cols = ['ID sản phẩm', 'Số lượng', 'Ngày lấy', 'Ghi chú',
                'Loại đặt hàng', 'Khách vãng lai', 'Mã đặt hàng',
                'Ngày đặt', 'Người tạo', 'Thời gian tạo']
        vals = [id_sp, so_luong, ngay_lay, ghi_chu,
                loai, khach_vang_lai, ma_dathang,
                now.strftime('%Y-%m-%d'), username, now.strftime('%Y-%m-%d %H:%M:%S')]

        result = db.insert_data_to_table('DatHang', cols, vals)
        if result.get('success'):
            success_count += 1
        else:
            errors.append(result.get('message', 'Lỗi'))

    if success_count > 0:
        return jsonify({
            'success': True,
            'message': f'Đã thêm {success_count} sản phẩm - Mã: {ma_dathang}',
            'ma_dathang': ma_dathang,
            'count': success_count
        })
    else:
        return jsonify({
            'success': False,
            'message': f'Lỗi: {", ".join(errors)}'
        }), 400


@dathang_bp.route('/api/dathang/<int:id>', methods=['PUT'])
@login_required
def update_dathang(id):
    """Cập nhật đơn đặt hàng"""
    data = request.get_json()
    username = session.get('username', 'system')
    result = db.update_data_by_id('DatHang', id, data, username)
    if result.get('success'):
        return jsonify(result)
    return jsonify(result), 400


@dathang_bp.route('/api/dathang/delete', methods=['POST'])
@login_required
def delete_dathang():
    """Xóa (soft delete) đơn đặt hàng"""
    data = request.get_json()
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'success': False, 'message': 'Không có ID'}), 400

    username = session.get('username', 'system')
    result = db.delete_data_by_ids('DatHang', ids, username)
    if result.get('success'):
        return jsonify(result)
    return jsonify(result), 400


@dathang_bp.route('/api/dathang/delete-by-ngaylay', methods=['POST'])
@login_required
def delete_by_ngaylay():
    """Xóa tất cả đơn hàng theo ngày lấy"""
    data = request.get_json()
    ngay_lay = data.get('ngay_lay')
    if not ngay_lay:
        return jsonify({'success': False, 'message': 'Thiếu ngày lấy'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE DatHang
        SET [Đã xóa] = 1, [Người sửa] = ?, [Thời gian sửa] = ?
        WHERE [Đã xóa] = 0 AND [Ngày lấy] = ?
    """, (username, now, ngay_lay))
    count = cursor.rowcount
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': f'Đã xóa {count} đơn hàng có Ngày lấy = {ngay_lay}',
        'count': count
    })


@dathang_bp.route('/api/dathang/import', methods=['POST'])
@login_required
def import_dathang():
    """Import đơn đặt hàng từ Excel"""
    file = request.files.get('file')
    loai = request.form.get('loai_dathang', 'Khách vãng lai')
    
    if not file:
        return jsonify({'success': False, 'message': 'Không có file'}), 400

    try:
        df = pd.read_excel(file)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi đọc file: {e}'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time()
    khach_vang_lai = 1 if loai == 'Khách vãng lai' else 0
    ma_dathang = db.generate_next_code('DatHang', 'Mã đặt hàng', 'DH', 5)

    # Determine format
    conn = db.connect_db()
    success_count = 0
    not_found = []

    if 'Tên sản phẩm' in df.columns and 'Số lượng' in df.columns:
        for _, row in df.iterrows():
            ten_sp = str(row['Tên sản phẩm']).strip()
            so_luong = row['Số lượng']
            cursor = conn.cursor()
            cursor.execute("SELECT ID FROM SanPham WHERE [Tên cám]=? AND [Đã xóa]=0", (ten_sp,))
            result = cursor.fetchone()
            if result:
                cols = ['ID sản phẩm', 'Số lượng', 'Ngày lấy', 'Ghi chú',
                        'Loại đặt hàng', 'Khách vãng lai', 'Mã đặt hàng',
                        'Ngày đặt', 'Người tạo', 'Thời gian tạo']
                vals = [result[0], so_luong, row.get('Ngày lấy'), row.get('Ghi chú', ''),
                        loai, khach_vang_lai, ma_dathang,
                        now.strftime('%Y-%m-%d'), username, now.strftime('%Y-%m-%d %H:%M:%S')]
                db.insert_data_to_table('DatHang', cols, vals)
                success_count += 1
            else:
                not_found.append(ten_sp)

    elif 'Code cám' in df.columns and 'Số lượng' in df.columns:
        for _, row in df.iterrows():
            code = str(row['Code cám']).strip()
            so_luong = row['Số lượng']
            cursor = conn.cursor()
            cursor.execute("SELECT ID FROM SanPham WHERE [Code cám]=? AND [Đã xóa]=0", (code,))
            result = cursor.fetchone()
            if result:
                cols = ['ID sản phẩm', 'Số lượng', 'Ngày lấy', 'Ghi chú',
                        'Loại đặt hàng', 'Khách vãng lai', 'Mã đặt hàng',
                        'Ngày đặt', 'Người tạo', 'Thời gian tạo']
                vals = [result[0], so_luong, row.get('Ngày lấy'), row.get('Ghi chú', ''),
                        loai, khach_vang_lai, ma_dathang,
                        now.strftime('%Y-%m-%d'), username, now.strftime('%Y-%m-%d %H:%M:%S')]
                db.insert_data_to_table('DatHang', cols, vals)
                success_count += 1
            else:
                not_found.append(code)
    else:
        conn.close()
        return jsonify({'success': False, 'message': "File Excel phải có cột 'Tên sản phẩm' hoặc 'Code cám' và 'Số lượng'"}), 400

    conn.close()

    msg = f'Đã import {success_count} sản phẩm - Mã: {ma_dathang}'
    if not_found:
        msg += f'. Không tìm thấy: {", ".join(not_found[:10])}'

    return jsonify({
        'success': success_count > 0,
        'message': msg,
        'ma_dathang': ma_dathang,
        'count': success_count,
        'not_found': not_found
    })


# ==================== BaCang Importer API ====================

def _get_bacang_importer():
    """Create BaCangImporter with correct db path"""
    import sys, os
    # flask_app/backend/api/ → go up 3 levels to project root (B7KHSX/)
    api_dir = os.path.dirname(os.path.abspath(__file__))         # backend/api/
    backend_dir = os.path.dirname(api_dir)                        # backend/
    flask_app_dir = os.path.dirname(backend_dir)                  # flask_app/
    project_dir = os.path.dirname(flask_app_dir)                  # B7KHSX/
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    from utils.bacang_importer import BaCangImporter
    import config
    return BaCangImporter(db_path=config.DATABASE_PATH)


@dathang_bp.route('/api/bacang/upload', methods=['POST'])
@login_required
def bacang_upload():
    """Upload file Bá Cang và trả về danh sách sheets"""
    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'message': 'Không có file'}), 400

    import os, tempfile, config
    # On PostgreSQL, DATABASE_PATH is a URL, use tempfile dir
    if config.DATABASE_PATH.startswith('postgresql'):
        excel_dir = os.path.join(tempfile.gettempdir(), 'EXCEL')
    else:
        excel_dir = os.path.join(os.path.dirname(config.DATABASE_PATH), 'EXCEL')
    os.makedirs(excel_dir, exist_ok=True)
    saved_path = os.path.join(excel_dir, file.filename)

    try:
        file.save(saved_path)
    except PermissionError:
        ext = os.path.splitext(file.filename)[1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=excel_dir)
        file.save(tmp.name)
        saved_path = tmp.name

    try:
        importer = _get_bacang_importer()
        sheets = importer.get_available_sheets(saved_path)
        return jsonify({
            'success': True,
            'file_path': saved_path,
            'file_name': file.filename,
            'sheets': sheets
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi đọc file: {e}'}), 400


@dathang_bp.route('/api/bacang/preview', methods=['POST'])
@login_required
def bacang_preview():
    """Preview dữ liệu từ sheet Bá Cang (2 bảng)"""
    data = request.get_json()
    file_path = data.get('file_path')
    sheet_name = data.get('sheet_name')

    if not file_path or not sheet_name:
        return jsonify({'success': False, 'message': 'Thiếu file_path hoặc sheet_name'}), 400

    try:
        importer = _get_bacang_importer()
        df1, df2 = importer.preview_data(file_path, sheet_name, limit=500)

        return jsonify({
            'success': True,
            'table1': df1.to_dict('records') if not df1.empty else [],
            'table2': df2.to_dict('records') if not df2.empty else [],
            'count1': len(df1),
            'count2': len(df2)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {e}'}), 400


@dathang_bp.route('/api/bacang/import', methods=['POST'])
@login_required
def bacang_import():
    """Import dữ liệu Bá Cang vào database"""
    data = request.get_json()
    file_path = data.get('file_path')
    sheet_name = data.get('sheet_name')

    if not file_path or not sheet_name:
        return jsonify({'success': False, 'message': 'Thiếu thông tin'}), 400

    username = session.get('username', 'system')

    try:
        importer = _get_bacang_importer()
        result = importer.import_bacang_data(
            file_path=file_path,
            sheet_name=sheet_name,
            nguoi_import=username
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': 0, 'errors': [str(e)]}), 400


@dathang_bp.route('/api/bacang/delete-all', methods=['POST'])
@login_required
def bacang_delete_all():
    """Xóa tất cả dữ liệu Bá Cang"""
    try:
        importer = _get_bacang_importer()
        result = importer.delete_all_bacang_data()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


# ==================== Silo Importer API ====================

def _get_silo_importer():
    """Create SiloImporter with correct db path"""
    import sys, os
    api_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(api_dir)
    flask_app_dir = os.path.dirname(backend_dir)
    project_dir = os.path.dirname(flask_app_dir)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    from utils.silo_importer import SiloImporter
    import config
    return SiloImporter(db_path=config.DATABASE_PATH)


@dathang_bp.route('/api/silo/upload', methods=['POST'])
@login_required
def silo_upload():
    """Upload file Silo và trả về danh sách sheets"""
    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'message': 'Không có file'}), 400

    import os, tempfile, config
    if config.DATABASE_PATH.startswith('postgresql'):
        excel_dir = os.path.join(tempfile.gettempdir(), 'EXCEL')
    else:
        excel_dir = os.path.join(os.path.dirname(config.DATABASE_PATH), 'EXCEL')
    os.makedirs(excel_dir, exist_ok=True)
    saved_path = os.path.join(excel_dir, file.filename)

    try:
        file.save(saved_path)
    except PermissionError:
        ext = os.path.splitext(file.filename)[1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=excel_dir)
        file.save(tmp.name)
        saved_path = tmp.name

    try:
        importer = _get_silo_importer()
        sheets = importer.get_available_sheets(saved_path)
        return jsonify({
            'success': True,
            'file_path': saved_path,
            'file_name': file.filename,
            'sheets': sheets
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi đọc file: {e}'}), 400


@dathang_bp.route('/api/silo/preview', methods=['POST'])
@login_required
def silo_preview():
    """Preview dữ liệu từ sheet Silo"""
    data = request.get_json()
    file_path = data.get('file_path')
    sheet_name = data.get('sheet_name')

    if not file_path or not sheet_name:
        return jsonify({'success': False, 'message': 'Thiếu file_path hoặc sheet_name'}), 400

    try:
        importer = _get_silo_importer()
        df = importer.preview_data(file_path, sheet_name, limit=500)

        return jsonify({
            'success': True,
            'data': df.to_dict('records') if not df.empty else [],
            'count': len(df)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {e}'}), 400


@dathang_bp.route('/api/silo/import', methods=['POST'])
@login_required
def silo_import():
    """Import dữ liệu Silo vào database"""
    data = request.get_json()
    file_path = data.get('file_path')
    sheet_name = data.get('sheet_name')

    if not file_path or not sheet_name:
        return jsonify({'success': False, 'message': 'Thiếu thông tin'}), 400

    username = session.get('username', 'system')

    try:
        importer = _get_silo_importer()
        result = importer.import_silo_data(
            file_path=file_path,
            sheet_name=sheet_name,
            nguoi_import=username
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': 0, 'errors': [str(e)]}), 400


# ==================== Forecast Importer API ====================

def _get_forecast_importer():
    """Create ForecastImporter with correct db path"""
    import sys, os
    api_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(api_dir)
    flask_app_dir = os.path.dirname(backend_dir)
    project_dir = os.path.dirname(flask_app_dir)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    from utils.forecast_importer import ForecastImporter
    import config
    return ForecastImporter(db_path=config.DATABASE_PATH)


@dathang_bp.route('/api/forecast/upload', methods=['POST'])
@login_required
def forecast_upload():
    """Upload file SALEFORECAST và trả về danh sách sheets"""
    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'message': 'Không có file'}), 400

    import os, tempfile, config
    if config.DATABASE_PATH.startswith('postgresql'):
        excel_dir = os.path.join(tempfile.gettempdir(), 'EXCEL')
    else:
        excel_dir = os.path.join(os.path.dirname(config.DATABASE_PATH), 'EXCEL')
    os.makedirs(excel_dir, exist_ok=True)
    saved_path = os.path.join(excel_dir, file.filename)

    try:
        file.save(saved_path)
    except PermissionError:
        ext = os.path.splitext(file.filename)[1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=excel_dir)
        file.save(tmp.name)
        saved_path = tmp.name

    try:
        importer = _get_forecast_importer()
        sheets = importer.get_available_sheets(saved_path)
        return jsonify({
            'success': True,
            'file_path': saved_path,
            'file_name': file.filename,
            'sheets': sheets
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi đọc file: {e}'}), 400


@dathang_bp.route('/api/forecast/preview', methods=['POST'])
@login_required
def forecast_preview():
    """Preview dữ liệu từ sheet Forecast"""
    data = request.get_json()
    file_path = data.get('file_path')
    sheet_name = data.get('sheet_name')

    if not file_path or not sheet_name:
        return jsonify({'success': False, 'message': 'Thiếu file_path hoặc sheet_name'}), 400

    try:
        importer = _get_forecast_importer()
        df = importer.preview_data(file_path, sheet_name, limit=500)

        # Get grand total from Excel
        grand_total = importer.get_grand_total_from_excel(file_path, sheet_name)

        return jsonify({
            'success': True,
            'data': df.to_dict('records') if not df.empty else [],
            'count': len(df),
            'grand_total': grand_total
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {e}'}), 400


@dathang_bp.route('/api/forecast/import', methods=['POST'])
@login_required
def forecast_import():
    """Import dữ liệu Forecast vào bảng Forecast"""
    data = request.get_json()
    file_path = data.get('file_path')
    sheet_name = data.get('sheet_name')

    if not file_path or not sheet_name:
        return jsonify({'success': False, 'message': 'Thiếu thông tin'}), 400

    username = session.get('username', 'system')

    try:
        importer = _get_forecast_importer()
        result = importer.import_forecast_data(
            file_path=file_path,
            sheet_name=sheet_name,
            nguoi_import=username
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': 0, 'errors': [str(e)]}), 400


@dathang_bp.route('/api/forecast/import-to-dathang', methods=['POST'])
@login_required
def forecast_import_to_dathang():
    """Import Forecast vào bảng DatHang (trừ đi đã có từ Bá Cang/Silo)"""
    data = request.get_json()
    file_path = data.get('file_path')
    sheet_name = data.get('sheet_name')

    if not file_path or not sheet_name:
        return jsonify({'success': False, 'message': 'Thiếu thông tin'}), 400

    username = session.get('username', 'system')

    try:
        importer = _get_forecast_importer()
        result = importer.import_forecast_to_dathang(
            file_path=file_path,
            sheet_name=sheet_name,
            nguoi_import=username
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': 0, 'errors': [str(e)]}), 400


# ==================== Chuyển qua Plan API ====================

@dathang_bp.route('/api/dathang/transfer-preview', methods=['POST'])
@login_required
def transfer_to_plan_preview():
    """Preview dữ liệu DatHang cho một ngày lấy, merge by Tên cám, tính Batch"""
    data = request.get_json()
    ngay_lay = data.get('ngay_lay')

    if not ngay_lay:
        return jsonify({'success': False, 'message': 'Thiếu ngày lấy'}), 400

    conn = db.connect_db()
    cursor = conn.cursor()

    try:
        # Query all DatHang for this ngay_lay, join SanPham
        cursor.execute("""
            SELECT
                dh.[ID sản phẩm],
                sp.[Code cám],
                sp.[Tên cám],
                sp.[Batch size],
                dh.[Số lượng],
                dh.[Loại đặt hàng],
                dh.[Ghi chú]
            FROM DatHang dh
            JOIN SanPham sp ON dh.[ID sản phẩm] = sp.ID
            WHERE dh.[Đã xóa] = 0
            AND sp.[Đã xóa] = 0
            AND (dh.[Ngày lấy] = ? OR dh.[Ngày lấy] = ?)
        """, (ngay_lay, ngay_lay))

        rows = cursor.fetchall()

        if not rows:
            conn.close()
            return jsonify({'success': True, 'data': [], 'count': 0,
                            'message': f'Không có đơn hàng cho ngày lấy {ngay_lay}'})

        # Merge by ID sản phẩm (keep sum of qty)
        merged = {}
        for row in rows:
            id_sp, code_cam, ten_cam, batch_size, so_luong, loai, ghi_chu = row
            batch_size = batch_size or 2800

            if id_sp in merged:
                merged[id_sp]['so_luong'] += (so_luong or 0)
                if loai and loai not in merged[id_sp]['nguon']:
                    merged[id_sp]['nguon'].append(loai)
            else:
                merged[id_sp] = {
                    'id_sanpham': id_sp,
                    'code_cam': code_cam,
                    'ten_cam': ten_cam,
                    'batch_size': batch_size,
                    'so_luong': so_luong or 0,
                    'nguon': [loai] if loai else []
                }

        # Build result with batch calculation
        result_data = []
        for item in merged.values():
            batch_size = item['batch_size']
            so_batch = round(item['so_luong'] / batch_size, 1) if batch_size > 0 else 0

            # ngày plan = ngày lấy - 1 (SX trước 1 ngày)
            from datetime import datetime, timedelta
            try:
                ngay_lay_dt = datetime.strptime(ngay_lay, '%Y-%m-%d')
                ngay_plan = (ngay_lay_dt - timedelta(days=1)).strftime('%Y-%m-%d')
            except:
                ngay_plan = ngay_lay

            result_data.append({
                'id_sanpham': item['id_sanpham'],
                'code_cam': item['code_cam'],
                'ten_cam': item['ten_cam'],
                'batch_size': item['batch_size'],
                'batch': so_batch,
                'so_luong': item['so_luong'],
                'ngay_plan': ngay_plan,
                'nguon': ', '.join(item['nguon']),
                'ghi_chu': f"{', '.join(item['nguon'])} - Ngày lấy {ngay_lay}"
            })

        # Sort by số lượng descending
        result_data.sort(key=lambda x: -x['so_luong'])

        total_kg = sum(item['so_luong'] for item in result_data)

        conn.close()
        return jsonify({
            'success': True,
            'data': result_data,
            'count': len(result_data),
            'total_kg': total_kg,
            'ngay_lay': ngay_lay,
            'ngay_plan': result_data[0]['ngay_plan'] if result_data else ngay_lay
        })

    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 400


@dathang_bp.route('/api/dathang/transfer-save', methods=['POST'])
@login_required
def transfer_to_plan_save():
    """Lưu dữ liệu đã merge vào bảng Plan"""
    payload = request.get_json()
    items = payload.get('items', [])
    ngay_plan = payload.get('ngay_plan')

    if not items:
        return jsonify({'success': False, 'message': 'Không có dữ liệu'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time()

    conn = db.connect_db()
    cursor = conn.cursor()

    try:
        # Ensure Plan table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Plan (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                [ID sản phẩm] INTEGER,
                [Mã plan] TEXT,
                [Số lượng] REAL,
                [Ngày plan] TEXT,
                [Ghi chú] TEXT,
                [Người tạo] TEXT,
                [Thời gian tạo] DATETIME DEFAULT CURRENT_TIMESTAMP,
                [Người sửa] TEXT,
                [Thời gian sửa] DATETIME,
                [Đã xóa] INTEGER DEFAULT 0
            )
        """)

        # Generate Plan code
        ma_plan = db.generate_next_code('Plan', 'Mã plan', 'PL', 5)
        thoi_gian_tao = now.strftime('%Y-%m-%d %H:%M:%S')

        success_count = 0
        for item in items:
            id_sp = item.get('id_sanpham')
            so_luong = item.get('so_luong', 0)
            item_ngay_plan = item.get('ngay_plan', ngay_plan)
            ghi_chu = item.get('ghi_chu', '')

            if not id_sp or so_luong <= 0:
                continue

            cursor.execute("""
                INSERT INTO Plan
                ([ID sản phẩm], [Mã plan], [Số lượng], [Ngày plan], [Ghi chú],
                 [Người tạo], [Thời gian tạo], [Đã xóa])
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (id_sp, ma_plan, so_luong, item_ngay_plan, ghi_chu,
                  username, thoi_gian_tao))
            success_count += 1

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'Đã lưu {success_count} sản phẩm vào Plan - Mã: {ma_plan}',
            'ma_plan': ma_plan,
            'count': success_count
        })

    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 400
