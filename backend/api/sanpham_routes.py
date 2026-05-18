"""
SanPham API Routes - CRUD cho bảng Sản phẩm
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import login_required
from backend import db
from backend.utils import get_vietnam_time
import pandas as pd

sanpham_bp = Blueprint('sanpham', __name__)


@sanpham_bp.route('/api/sanpham', methods=['GET'])
@login_required
def get_sanpham_list():
    """Lấy danh sách sản phẩm (phân trang + tìm kiếm)"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '', type=str)

    col_where = {'Đã xóa': ('=', 0)}
    search_columns = ['Code cám', 'Tên cám', 'Vật nuôi'] if search else None

    columns = [
        'ID', 'Code cám', 'Tên cám', 'Kích cỡ ép viên', 'Dạng ép viên',
        'Kích cỡ đóng bao', 'Pellet', 'Packing', 'Batch size', 'Vật nuôi',
        'Người tạo', 'Thời gian tạo', 'Người sửa', 'Thời gian sửa'
    ]

    # Tổng records
    total = db.get_total_count(
        table_name='SanPham',
        col_where=col_where,
        search_value=search if search else None,
        search_columns=search_columns
    )

    # Dữ liệu phân trang
    df = db.get_columns_data(
        table_name='SanPham',
        columns=columns,
        col_where=col_where,
        col_order={'ID': 'DESC'},
        page_number=page,
        rows_per_page=per_page,
        search_value=search if search else None,
        search_columns=search_columns
    )

    # Chuyển DataFrame sang JSON-safe
    data = df.fillna('').to_dict(orient='records')

    return jsonify({
        "data": data,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if per_page > 0 else 1
    })


@sanpham_bp.route('/api/sanpham/lookup', methods=['GET'])
@login_required
def sanpham_lookup():
    """Lookup danh sách sản phẩm cho dropdown (ID, Code cám, Tên cám)"""
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ID, [Code cám], [Tên cám] FROM SanPham WHERE [Đã xóa] = 0 ORDER BY [Code cám]"
    )
    rows = cursor.fetchall()
    conn.close()

    data = [{'ID': r[0], 'Code cám': r[1], 'Tên cám': r[2]} for r in rows]
    return jsonify({'success': True, 'data': data})


@sanpham_bp.route('/api/sanpham', methods=['POST'])
@login_required
def add_sanpham():
    """Thêm sản phẩm mới"""
    data = request.get_json()

    required = ['Code cám', 'Tên cám']
    for field in required:
        if not data.get(field, '').strip():
            return jsonify({"success": False, "message": f"Vui lòng nhập {field}"}), 400

    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')
    username = session.get('username', '')

    columns = [
        'Code cám', 'Tên cám', 'Kích cỡ ép viên', 'Dạng ép viên',
        'Kích cỡ đóng bao', 'Pellet', 'Packing', 'Batch size',
        'Vật nuôi', 'Người tạo', 'Thời gian tạo'
    ]
    values = [
        data.get('Code cám', ''),
        data.get('Tên cám', ''),
        data.get('Kích cỡ ép viên', ''),
        data.get('Dạng ép viên', ''),
        data.get('Kích cỡ đóng bao'),
        data.get('Pellet', ''),
        data.get('Packing', ''),
        data.get('Batch size'),
        data.get('Vật nuôi', ''),
        username,
        now
    ]

    result = db.insert_data_to_table('SanPham', columns, values)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@sanpham_bp.route('/api/sanpham/<int:id>', methods=['PUT'])
@login_required
def update_sanpham(id):
    """Cập nhật sản phẩm"""
    data = request.get_json()
    username = session.get('username', '')

    # Loại bỏ các trường hệ thống
    update_data = {}
    editable_fields = [
        'Code cám', 'Tên cám', 'Kích cỡ ép viên', 'Dạng ép viên',
        'Kích cỡ đóng bao', 'Pellet', 'Packing', 'Batch size', 'Vật nuôi'
    ]
    for field in editable_fields:
        if field in data:
            update_data[field] = data[field]

    if not update_data:
        return jsonify({"success": False, "message": "Không có dữ liệu để cập nhật"}), 400

    result = db.update_data_by_id('SanPham', id, update_data, username)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@sanpham_bp.route('/api/sanpham/delete', methods=['POST'])
@login_required
def delete_sanpham():
    """Xóa sản phẩm (soft delete)"""
    data = request.get_json()
    ids = data.get('ids', [])

    if not ids:
        return jsonify({"success": False, "message": "Chưa chọn sản phẩm để xóa"}), 400

    username = session.get('username', '')
    result = db.delete_data_by_ids('SanPham', ids, username)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@sanpham_bp.route('/api/sanpham/import', methods=['POST'])
@login_required
def import_sanpham():
    """Import sản phẩm từ file Excel"""
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "Chưa chọn file"}), 400

    file = request.files['file']
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({"success": False, "message": "File phải là định dạng Excel (.xlsx, .xls)"}), 400

    try:
        dtype = {
            'Code cám': str,
            'Tên cám': str,
            'Kích cỡ ép viên': str,
            'Dạng ép viên': str,
            'Kích cỡ đóng bao': str,
            'Pellet': str,
            'Packing': str,
            'Batch size': float,
            'Vật nuôi': str
        }
        df = pd.read_excel(file, dtype=dtype)

        username = session.get('username', '')
        result = db.insert_dataframe_to_table(
            'SanPham',
            df,
            created_by=username,
            delete_by_ids=['Code cám', 'Tên cám']
        )

        return jsonify(result), 200 if result.get('success') else 400

    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi đọc file: {str(e)}"}), 400
