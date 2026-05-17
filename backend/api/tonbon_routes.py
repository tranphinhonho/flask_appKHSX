"""
API routes cho module Tồn bồn (TonBon)
Quản lý dữ liệu tồn bồn: danh sách, import Excel, nhập thủ công
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import login_required
from backend import db
from backend.utils import get_vietnam_time
import os
import sys
import glob

tonbon_bp = Blueprint('tonbon', __name__)

# Constants
LOAI_SAN_PHAM = ['Thành phẩm', 'Bán thành phẩm']
TRANG_THAI_OPTIONS = ['Chờ đóng bao 25kg', 'Chờ đóng bao 50kg', 'Chờ xe Silo', 'Chờ ép viên', 'Đang xử lý']
CA_SAN_XUAT = ['Ca 1', 'Ca 2', 'Ca 3']


def _setup_utils_path():
    api_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(api_dir)
    flask_app_dir = os.path.dirname(backend_dir)
    project_dir = os.path.dirname(flask_app_dir)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    return project_dir


def _get_tonbon_importer():
    project_dir = _setup_utils_path()
    from utils.tonbon_importer import TonBonImporter
    import config
    return TonBonImporter(db_path=config.DATABASE_PATH)


def _get_excel_folder():
    import config, tempfile
    if config.DATABASE_PATH.startswith('postgresql'):
        return os.path.join(tempfile.gettempdir(), 'EXCEL')
    return os.path.join(os.path.dirname(config.DATABASE_PATH), 'EXCEL')


# ==================== Danh sách Tồn bồn ====================

@tonbon_bp.route('/api/tonbon', methods=['GET'])
@login_required
def get_tonbon_list():
    """Lấy danh sách tồn bồn có lọc"""
    ngay = request.args.get('ngay')
    loai = request.args.get('loai')
    trang_thai = request.args.get('trang_thai')
    ca = request.args.get('ca')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 200, type=int)

    conn = db.connect_db()
    cursor = conn.cursor()

    conditions = ["tb.[Đã xóa] = 0"]
    params = []

    if ngay:
        conditions.append("tb.[Ngày kiểm kho] = ?")
        params.append(ngay)
    if loai and loai != 'Tất cả':
        conditions.append("tb.[Loại sản phẩm] = ?")
        params.append(loai)
    if trang_thai and trang_thai != 'Tất cả':
        conditions.append("tb.[Trạng thái] = ?")
        params.append(trang_thai)
    if ca and ca != 'Tất cả':
        conditions.append("tb.[Ca sản xuất] = ?")
        params.append(ca)

    where = " AND ".join(conditions)

    # Count
    cursor.execute(f"SELECT COUNT(*) FROM TonBon tb WHERE {where}", params)
    total = cursor.fetchone()[0]

    # Data with join
    offset = (page - 1) * per_page
    cursor.execute(f"""
        SELECT tb.ID, tb.[Mã tồn bồn], tb.[Ngày kiểm kho], tb.[ID sản phẩm],
               sp.[Code cám], sp.[Tên cám],
               tb.[Loại sản phẩm], tb.[Số lượng (kg)], tb.[Số bồn],
               tb.[Trạng thái], tb.[Kích cỡ đóng bao], tb.[Ca sản xuất],
               tb.[Ghi chú], tb.[Người tạo], tb.[Thời gian tạo]
        FROM TonBon tb
        LEFT JOIN SanPham sp ON tb.[ID sản phẩm] = sp.ID
        WHERE {where}
        ORDER BY tb.[Ngày kiểm kho] DESC, tb.ID DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])

    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]

    data = []
    for row in rows:
        data.append(dict(zip(cols, row)))

    conn.close()
    return jsonify({
        'success': True,
        'data': data,
        'total': total,
        'page': page,
        'per_page': per_page
    })


@tonbon_bp.route('/api/tonbon/latest-date', methods=['GET'])
@login_required
def get_latest_date():
    """Get the latest date that has data"""
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX([Ngày kiểm kho]) FROM TonBon WHERE [Đã xóa] = 0")
    result = cursor.fetchone()
    conn.close()
    return jsonify({'success': True, 'latest_date': result[0] if result else None})


@tonbon_bp.route('/api/tonbon/days-in-month', methods=['GET'])
@login_required
def get_days_in_month():
    """Trả về danh sách ngày (1-31) có dữ liệu TonBon trong tháng/năm"""
    year  = request.args.get('year',  type=int)
    month = request.args.get('month', type=int)
    if not year or not month:
        return jsonify({'success': False, 'message': 'Thiếu year/month'}), 400

    month_str = f"{year}-{month:02d}"
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT CAST([Ngày kiểm kho] AS TEXT) as ngay_str
        FROM TonBon
        WHERE [Đã xóa] = 0
          AND CAST([Ngày kiểm kho] AS TEXT) LIKE ?
        ORDER BY ngay_str
    """, (month_str + '%',))
    rows = cursor.fetchall()
    conn.close()

    days_with_data = []
    for row in rows:
        date_str = str(row[0]) if row[0] else ''
        if len(date_str) >= 10:
            try:
                day = int(date_str[8:10])
                if day not in days_with_data:
                    days_with_data.append(day)
            except ValueError:
                pass
    days_with_data.sort()
    return jsonify({'success': True, 'days': days_with_data, 'year': year, 'month': month})




@tonbon_bp.route('/api/tonbon/stats', methods=['GET'])
@login_required
def get_tonbon_stats():
    """Get statistics for thanh pham (bon 99-134) and ban thanh pham (bon 86-98)"""
    ngay = request.args.get('ngay')

    conn = db.connect_db()
    cursor = conn.cursor()

    date_cond = ""
    params = []
    if ngay:
        date_cond = "AND [Ngày kiểm kho] = ?"
        params.append(ngay)

    # Thành phẩm: bồn 99-134
    tp_like_conditions = " OR ".join([f"[Số bồn] LIKE '%{i}%'" for i in range(99, 135)])
    cursor.execute(f"""
        SELECT COALESCE(SUM([Số lượng (kg)]), 0) as tong_kg, COUNT(*) as so_dong
        FROM TonBon WHERE [Đã xóa] = 0 {date_cond} AND ({tp_like_conditions})
    """, params)
    tp = cursor.fetchone()

    # Bán thành phẩm: bồn 86-98
    btp_like_conditions = " OR ".join([f"[Số bồn] LIKE '%{i}%'" for i in range(86, 99)])
    cursor.execute(f"""
        SELECT COALESCE(SUM([Số lượng (kg)]), 0) as tong_kg, COUNT(*) as so_dong
        FROM TonBon WHERE [Đã xóa] = 0 {date_cond} AND ({btp_like_conditions})
    """, params)
    btp = cursor.fetchone()

    conn.close()
    return jsonify({
        'success': True,
        'thanh_pham': {'tong_kg': tp[0], 'so_dong': tp[1]},
        'ban_thanh_pham': {'tong_kg': btp[0], 'so_dong': btp[1]}
    })


# ==================== Nhập thủ công ====================

@tonbon_bp.route('/api/tonbon/create', methods=['POST'])
@login_required
def create_tonbon():
    """Nhập thủ công 1 dòng tồn bồn"""
    data = request.get_json()

    id_sp = data.get('id_sanpham')
    so_luong = data.get('so_luong', 0)
    so_bon = data.get('so_bon', '')
    loai_sp = data.get('loai_sp', 'Thành phẩm')
    trang_thai = data.get('trang_thai', '')
    ca_sx = data.get('ca_sx', 'Ca 1')
    ngay_kiem = data.get('ngay_kiem')
    ghi_chu = data.get('ghi_chu', '')

    if not id_sp or so_luong <= 0:
        return jsonify({'success': False, 'message': 'Thiếu sản phẩm hoặc số lượng'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time()

    # Determine kích cỡ đóng bao from trạng thái
    if '25kg' in trang_thai:
        kich_co = '25 kg'
    elif '50kg' in trang_thai:
        kich_co = '50 kg'
    elif 'Silo' in trang_thai:
        kich_co = 'Silo'
    else:
        kich_co = 'N/A'

    ma_tonbon = db.generate_next_code('TonBon', 'Mã tồn bồn', 'TB', 5)

    conn = db.connect_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO TonBon
            ([Mã tồn bồn], [Ngày kiểm kho], [ID sản phẩm], [Loại sản phẩm],
             [Số lượng (kg)], [Số bồn], [Trạng thái], [Kích cỡ đóng bao],
             [Ca sản xuất], [Ghi chú], [Người tạo], [Thời gian tạo], [Đã xóa])
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (ma_tonbon, ngay_kiem, id_sp, loai_sp, so_luong, so_bon,
              trang_thai, kich_co, ca_sx, ghi_chu, username,
              now.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'Đã lưu! Mã: {ma_tonbon}',
            'ma_tonbon': ma_tonbon
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 400


@tonbon_bp.route('/api/tonbon/delete', methods=['POST'])
@login_required
def delete_tonbon():
    """Soft delete tồn bồn"""
    data = request.get_json()
    item_id = data.get('id')

    if not item_id:
        return jsonify({'success': False, 'message': 'Thiếu ID'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE TonBon SET [Đã xóa] = 1, [Người sửa] = ?, [Thời gian sửa] = ? WHERE ID = ?",
        (username, now, item_id)
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Đã xóa'})


# ==================== Import Excel ====================

@tonbon_bp.route('/api/tonbon/scan-files', methods=['GET'])
@login_required
def scan_tonbon_files():
    """Scan folder EXCEL for tonbon report files"""
    excel_dir = _get_excel_folder()
    if not os.path.exists(excel_dir):
        return jsonify({'success': True, 'files': []})

    files = []
    for pattern in ['Báo cáo tồn bồn*.*', 'Bao cao ton bon*.*']:
        files.extend(glob.glob(os.path.join(excel_dir, pattern)))

    # Filter out copy/backup files
    files = [f for f in files if not os.path.basename(f).startswith('Copy')]
    files = sorted(files, key=lambda f: os.path.basename(f), reverse=True)

    result = []
    for fp in files:
        fname = os.path.basename(fp)
        result.append({
            'filename': fname,
            'filepath': fp,
            'size_kb': round(os.path.getsize(fp) / 1024, 1)
        })

    return jsonify({'success': True, 'files': result, 'excel_dir': excel_dir})


@tonbon_bp.route('/api/tonbon/preview', methods=['POST'])
@login_required
def preview_tonbon():
    """Preview tồn bồn data from Excel (1 day or all days)"""
    data = request.get_json()
    filepath = data.get('filepath')
    mode = data.get('mode', 'single')  # 'single' or 'all'
    day = data.get('day', 1)

    if not filepath or not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'File không tồn tại'}), 400

    try:
        importer = _get_tonbon_importer()

        if mode == 'all':
            df = importer.read_all_sheets_with_dates(filepath)
            if len(df) > 0:
                # Stats by day
                stats = df.groupby('Ngày')['Số lượng (kg)'].sum().reset_index()
                stats.columns = ['Ngày', 'Tổng kg']
                total_kg = df['Số lượng (kg)'].sum()
                unique_days = df['Ngày'].nunique()

                return jsonify({
                    'success': True,
                    'data': df.head(100).to_dict('records'),
                    'stats': stats.to_dict('records'),
                    'total_rows': len(df),
                    'total_kg': total_kg,
                    'unique_days': unique_days
                })
            else:
                return jsonify({'success': True, 'data': [], 'total_rows': 0})
        else:
            df = importer.read_direct_from_cells(filepath, sheet_index=str(day))
            if len(df) > 0:
                total_kg = df['Số lượng (kg)'].sum()
                return jsonify({
                    'success': True,
                    'data': df.to_dict('records'),
                    'total_rows': len(df),
                    'total_kg': total_kg
                })
            else:
                return jsonify({'success': True, 'data': [], 'total_rows': 0})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@tonbon_bp.route('/api/tonbon/import', methods=['POST'])
@login_required
def import_tonbon():
    """Import tồn bồn data from Excel"""
    data = request.get_json()
    filepath = data.get('filepath')
    mode = data.get('mode', 'single')
    ngay_kiem = data.get('ngay_kiem')
    loai_sp = data.get('loai_sp', 'Thành phẩm')
    overwrite = data.get('overwrite', True)

    if not filepath or not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'File không tồn tại'}), 400

    username = session.get('username', 'system')

    try:
        importer = _get_tonbon_importer()

        if mode == 'all':
            result = importer.import_all_days(
                file_path=filepath,
                nguoi_import=username,
                loai_san_pham=loai_sp,
                overwrite=overwrite
            )
        else:
            result = importer.import_tonbon(
                file_path=filepath,
                ngay_kiem=ngay_kiem,
                nguoi_import=username,
                loai_san_pham=loai_sp,
                overwrite=overwrite
            )

        return jsonify(result)

    except Exception as e:
        return jsonify({'success': 0, 'errors': [str(e)]}), 400


@tonbon_bp.route('/api/tonbon/upload-import', methods=['POST'])
@login_required
def upload_and_import_tonbon():
    """Upload file and import"""
    file = request.files.get('file')
    mode = request.form.get('mode', 'single')
    ngay_kiem = request.form.get('ngay_kiem')
    loai_sp = request.form.get('loai_sp', 'Thành phẩm')
    overwrite = request.form.get('overwrite', 'true') == 'true'

    if not file:
        return jsonify({'success': False, 'message': 'Không có file'}), 400

    excel_dir = _get_excel_folder()
    os.makedirs(excel_dir, exist_ok=True)
    saved_path = os.path.join(excel_dir, file.filename)

    try:
        file.save(saved_path)
    except PermissionError:
        import tempfile
        ext = os.path.splitext(file.filename)[1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=excel_dir)
        file.save(tmp.name)
        saved_path = tmp.name

    username = session.get('username', 'system')

    try:
        importer = _get_tonbon_importer()

        if mode == 'all':
            result = importer.import_all_days(
                file_path=saved_path,
                nguoi_import=username,
                loai_san_pham=loai_sp,
                overwrite=overwrite
            )
        else:
            result = importer.import_tonbon(
                file_path=saved_path,
                ngay_kiem=ngay_kiem,
                nguoi_import=username,
                loai_san_pham=loai_sp,
                overwrite=overwrite
            )

        result['filename'] = file.filename
        return jsonify(result)

    except Exception as e:
        return jsonify({'success': 0, 'errors': [str(e)]}), 400
