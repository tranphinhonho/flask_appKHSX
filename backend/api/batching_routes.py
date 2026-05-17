"""
API routes cho module Batching (Mixer)
Quản lý dữ liệu Batching: danh sách, import CSV/XLSM, nhập thủ công
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import login_required
from backend import db
from backend.utils import get_vietnam_time
import os
import sys
import tempfile

batching_bp = Blueprint('batching', __name__)

# Constants
BATCH_SIZES = [8000, 8400]
DICH_DEN_OPTIONS = ['Pellet', 'Packing']
SO_MAY_OPTIONS = ['Pellet 1', 'Pellet 2', 'Pellet 3', 'Pellet 4',
                  'Pellet 5', 'Pellet 6', 'Pellet 7', 'Packing 3']
CA_SAN_XUAT = ['Ca 1', 'Ca 2', 'Ca 3']


def _setup_utils_path():
    api_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(api_dir)
    flask_app_dir = os.path.dirname(backend_dir)
    project_dir = os.path.dirname(flask_app_dir)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    return project_dir


def _get_production_importer():
    _setup_utils_path()
    from utils.production_importer import ProductionImporter
    # Pass db.connect_db as connection factory for PostgreSQL compatibility
    return ProductionImporter(conn_factory=db.connect_db)


# ==================== Danh sách Batching ====================

@batching_bp.route('/api/batching', methods=['GET'])
@login_required
def get_batching_list():
    """Lấy danh sách batching có lọc"""
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    dich_den = request.args.get('dich_den')
    ca = request.args.get('ca')
    per_page = request.args.get('per_page', 200, type=int)

    conn = db.connect_db()
    cursor = conn.cursor()

    conditions = ["m.[Đã xóa] = 0"]
    params = []

    if date_from and date_to:
        conditions.append("m.[Ngày trộn] BETWEEN ? AND ?")
        params.extend([date_from, date_to])
    elif date_from:
        conditions.append("m.[Ngày trộn] >= ?")
        params.append(date_from)

    if dich_den and dich_den != 'Tất cả':
        conditions.append("m.[Đích đến] = ?")
        params.append(dich_den)
    if ca and ca != 'Tất cả':
        conditions.append("m.[Ca sản xuất] = ?")
        params.append(ca)

    where = " AND ".join(conditions)

    cursor.execute(f"SELECT COUNT(*) FROM Mixer m WHERE {where}", params)
    total = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT m.ID, m.[Mã mixer], m.[Ngày trộn], m.[ID sản phẩm],
               sp.[Code cám], sp.[Tên cám],
               m.[Batch size], m.[Số lượng thực tế],
               m.[Loss (kg)], m.[Loss (%)],
               m.[Đích đến], m.[Số máy], m.[Ca sản xuất],
               m.[Ghi chú], m.[Người tạo], m.[Thời gian tạo]
        FROM Mixer m
        LEFT JOIN SanPham sp ON m.[ID sản phẩm] = sp.ID
        WHERE {where}
        ORDER BY m.[Ngày trộn] DESC, m.ID DESC
        LIMIT ?
    """, params + [per_page])

    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    data = [dict(zip(cols, row)) for row in rows]

    conn.close()
    return jsonify({'success': True, 'data': data, 'total': total})


@batching_bp.route('/api/batching/latest-date', methods=['GET'])
@login_required
def get_latest_date():
    """Get latest date with data"""
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX([Ngày trộn]) FROM Mixer WHERE [Đã xóa] = 0")
    result = cursor.fetchone()
    conn.close()
    return jsonify({'success': True, 'latest_date': result[0] if result else None})


@batching_bp.route('/api/batching/days-in-month', methods=['GET'])
@login_required
def get_days_in_month():
    """Trả về danh sách ngày (1-31) có dữ liệu Batching trong tháng/năm"""
    year  = request.args.get('year',  type=int)
    month = request.args.get('month', type=int)
    if not year or not month:
        return jsonify({'success': False, 'message': 'Thiếu year/month'}), 400

    month_str = f"{year}-{month:02d}"
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT CAST([Ngày trộn] AS TEXT) as ngay_str
        FROM Mixer
        WHERE [Đã xóa] = 0
          AND CAST([Ngày trộn] AS TEXT) LIKE ?
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




@batching_bp.route('/api/batching/stats', methods=['GET'])
@login_required
def get_batching_stats():
    """Get statistics for batching"""
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    conn = db.connect_db()
    cursor = conn.cursor()

    date_cond = ""
    params = []
    if date_from and date_to:
        date_cond = "AND [Ngày trộn] BETWEEN ? AND ?"
        params.extend([date_from, date_to])
    elif date_from:
        date_cond = "AND [Ngày trộn] >= ?"
        params.append(date_from)

    cursor.execute(f"""
        SELECT COUNT(*) as total_batches,
               COALESCE(SUM([Batch size]), 0) as total_input,
               COALESCE(SUM([Số lượng thực tế]), 0) as total_output,
               COALESCE(SUM([Loss (kg)]), 0) as total_loss,
               COALESCE(AVG([Loss (%)]), 0) as avg_loss_percent
        FROM Mixer WHERE [Đã xóa] = 0 {date_cond}
    """, params)

    row = cursor.fetchone()
    conn.close()

    return jsonify({
        'success': True,
        'stats': {
            'total_batches': row[0],
            'total_input': row[1],
            'total_output': row[2],
            'total_loss': row[3],
            'avg_loss_percent': round(row[4], 2) if row[4] else 0
        }
    })


# ==================== Nhập thủ công ====================

@batching_bp.route('/api/batching/create', methods=['POST'])
@login_required
def create_batching():
    """Nhập thủ công 1 dòng batching"""
    data = request.get_json()

    id_sp = data.get('id_sanpham')
    batch_size = data.get('batch_size', 8400)
    so_luong = data.get('so_luong_thuc_te', 0)
    dich_den = data.get('dich_den', 'Pellet')
    so_may = data.get('so_may', '')
    ca_sx = data.get('ca_sx', 'Ca 1')
    ngay_tron = data.get('ngay_tron')
    ghi_chu = data.get('ghi_chu', '')

    if not id_sp or so_luong <= 0:
        return jsonify({'success': False, 'message': 'Thiếu sản phẩm hoặc số lượng'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time()

    # Calculate loss
    loss_kg = batch_size - so_luong
    loss_percent = round((loss_kg / batch_size) * 100, 2) if batch_size > 0 else 0

    ma_mixer = db.generate_next_code('Mixer', 'Mã mixer', 'MX', 5)

    conn = db.connect_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO Mixer
            ([Mã mixer], [Ngày trộn], [ID sản phẩm], [Batch size],
             [Số lượng thực tế], [Loss (kg)], [Loss (%)],
             [Đích đến], [Số máy], [Ca sản xuất],
             [Ghi chú], [Người tạo], [Thời gian tạo], [Đã xóa])
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (ma_mixer, ngay_tron, id_sp, batch_size, so_luong,
              loss_kg, loss_percent, dich_den, so_may, ca_sx,
              ghi_chu, username, now.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'Đã lưu! Mã mixer: {ma_mixer}',
            'ma_mixer': ma_mixer,
            'loss_kg': loss_kg,
            'loss_percent': loss_percent
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 400


@batching_bp.route('/api/batching/delete', methods=['POST'])
@login_required
def delete_batching():
    """Soft delete batching record"""
    data = request.get_json()
    item_id = data.get('id')

    if not item_id:
        return jsonify({'success': False, 'message': 'Thiếu ID'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE Mixer SET [Đã xóa] = 1, [Người sửa] = ?, [Thời gian sửa] = ? WHERE ID = ?",
        (username, now, item_id)
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Đã xóa'})


# ==================== Import Excel / CSV ====================

@batching_bp.route('/api/batching/upload-preview', methods=['POST'])
@login_required
def upload_preview_batching():
    """Upload file and preview data before import"""
    file = request.files.get('file')
    if not file:
        return jsonify({'success': False, 'message': 'Không có file'}), 400

    file_ext = file.filename.rsplit('.', 1)[-1].lower()

    # Save temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}')
    file.save(tmp.name)
    tmp_path = tmp.name

    try:
        if file_ext == 'csv':
            import pandas as pd
            # PRODUCTION CSV files have irregular header lines - try with error handling
            try:
                df = pd.read_csv(tmp_path, header=None, encoding='utf-8-sig', 
                                sep=',', on_bad_lines='skip')
            except TypeError:
                # Older pandas versions
                df = pd.read_csv(tmp_path, header=None, encoding='utf-8-sig',
                                sep=',', error_bad_lines=False)
            data = df.head(30).fillna('').values.tolist()
            return jsonify({
                'success': True,
                'type': 'csv',
                'data': data,
                'total_rows': len(df),
                'total_cols': len(df.columns),
                'tmp_path': tmp_path,
                'filename': file.filename
            })
        else:
            # XLSM/XLSX - use ProductionImporter preview
            importer = _get_production_importer()
            df = importer.preview_production_xlsm(tmp_path)

            if len(df) > 0:
                return jsonify({
                    'success': True,
                    'type': 'xlsm',
                    'data': df.fillna('').to_dict('records'),
                    'total_rows': len(df),
                    'tmp_path': tmp_path,
                    'filename': file.filename
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Không tìm thấy dữ liệu ở cột CA-CF. Đảm bảo đã chạy VBA TransposeReport!',
                    'tmp_path': tmp_path
                })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@batching_bp.route('/api/batching/import', methods=['POST'])
@login_required
def import_batching():
    """Import batching data from previously uploaded temp file"""
    data = request.get_json()
    tmp_path = data.get('tmp_path')
    file_type = data.get('file_type', 'csv')
    ngay_sx = data.get('ngay_san_xuat')
    overwrite = data.get('overwrite', False)

    if not tmp_path or not os.path.exists(tmp_path):
        return jsonify({'success': False, 'message': 'File tạm không tồn tại. Vui lòng upload lại.'}), 400

    username = session.get('username', 'system')

    try:
        importer = _get_production_importer()

        if file_type == 'csv':
            result = importer.import_production(
                file_path=tmp_path,
                nguoi_import=username,
                ngay_san_xuat=ngay_sx,
                overwrite=overwrite
            )
        else:
            result = importer.import_production_xlsm(
                file_path=tmp_path,
                nguoi_import=username,
                ngay_san_xuat=ngay_sx,
                overwrite=overwrite
            )

        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except:
            pass

        return jsonify(result)

    except Exception as e:
        return jsonify({'success': 0, 'errors': [str(e)]}), 400
