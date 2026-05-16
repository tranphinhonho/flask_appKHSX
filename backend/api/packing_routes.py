"""
API routes cho module Packing
Quản lý sản lượng đóng bao: import DAILY PACKING, nhập thủ công, danh sách
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import login_required
from backend import db
from backend.utils import get_vietnam_time
import config
import os, sys, re, tempfile

packing_bp = Blueprint('packing', __name__)

VAT_NUOI_LABELS = {'H': 'HEO', 'G': 'GÀ', 'B': 'BÒ', 'V': 'VỊT', 'C': 'CÚT', 'D': 'DÊ'}
VAT_NUOI_COLORS = {'H': '#FF6B6B', 'G': '#4ECDC4', 'B': '#45B7D1', 'V': '#96CEB4', 'C': '#FFEAA7', 'D': '#DDA0DD'}


def _extract_month_year(filename):
    match = re.search(r'THANG\s*(\d{1,2})[.\s]*(\d{4})', filename, re.IGNORECASE)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


@packing_bp.route('/api/packing/latest-date', methods=['GET'])
@login_required
def get_latest_date():
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX([Ngày packing]) FROM Packing WHERE [Đã xóa] = 0")
    result = cursor.fetchone()
    conn.close()
    return jsonify({'success': True, 'latest_date': result[0] if result else None})


@packing_bp.route('/api/packing', methods=['GET'])
@login_required
def get_packing_list():
    """Danh sách Packing"""
    ngay = request.args.get('ngay')
    vatnuoi = request.args.get('vatnuoi')
    per_page = request.args.get('per_page', 200, type=int)

    conds = ["p.[Đã xóa] = 0"]
    params = []

    if ngay:
        conds.append("p.[Ngày packing] = ?")
        params.append(ngay)
    if vatnuoi and vatnuoi != 'Tất cả':
        conds.append("sp.[Vật nuôi] = ?")
        params.append(vatnuoi)

    where = " AND ".join(conds)

    conn = db.connect_db()
    cursor = conn.cursor()

    cursor.execute(f"SELECT COUNT(*) FROM Packing p LEFT JOIN SanPham sp ON p.[ID sản phẩm] = sp.ID WHERE {where}", params)
    total = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT p.ID, p.[Mã packing], sp.[Code cám], sp.[Tên cám],
               sp.[Dạng ép viên], sp.[Kích cỡ ép viên], sp.[Vật nuôi],
               p.[Số lượng], p.[Ngày packing], p.[Ghi chú],
               p.[Người tạo], p.[Thời gian tạo]
        FROM Packing p
        LEFT JOIN SanPham sp ON p.[ID sản phẩm] = sp.ID
        WHERE {where}
        ORDER BY p.ID DESC LIMIT ?
    """, params + [per_page])

    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    data = [dict(zip(cols, row)) for row in rows]
    conn.close()

    return jsonify({'success': True, 'data': data, 'total': total})


@packing_bp.route('/api/packing/stats', methods=['GET'])
@login_required
def get_packing_stats():
    """Thống kê tổng sản lượng theo vật nuôi"""
    ngay = request.args.get('ngay')
    conn = db.connect_db()
    cursor = conn.cursor()

    date_cond = "AND p.[Ngày packing] = ?" if ngay else ""
    params = (ngay,) if ngay else ()

    cursor.execute(f"""
        SELECT sp.[Vật nuôi], SUM(p.[Số lượng]) as tong
        FROM Packing p
        LEFT JOIN SanPham sp ON p.[ID sản phẩm] = sp.ID
        WHERE p.[Đã xóa] = 0 AND sp.[Vật nuôi] IS NOT NULL
        {date_cond}
        GROUP BY sp.[Vật nuôi]
        ORDER BY SUM(p.[Số lượng]) DESC
    """, params)

    rows = cursor.fetchall()
    conn.close()

    data = []
    total = 0
    for row in rows:
        code = row[0]
        kg = row[1] or 0
        total += kg
        data.append({
            'code': code, 'label': VAT_NUOI_LABELS.get(code, code),
            'color': VAT_NUOI_COLORS.get(code, '#999'), 'kg': kg
        })
    for d in data:
        d['pct'] = round((d['kg'] / total * 100), 1) if total > 0 else 0

    return jsonify({'success': True, 'data': data, 'total': total})


@packing_bp.route('/api/packing/create', methods=['POST'])
@login_required
def create_packing():
    """Nhập thủ công"""
    data = request.get_json()
    items = data.get('items', [])
    if not items:
        return jsonify({'success': False, 'message': 'Không có dữ liệu'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')
    ngay = get_vietnam_time().strftime('%Y-%m-%d')

    conn = db.connect_db()
    cursor = conn.cursor()

    # Generate mã packing
    cursor.execute("SELECT MAX([Mã packing]) FROM Packing WHERE [Mã packing] LIKE 'PK%'")
    result = cursor.fetchone()[0]
    next_num = int(result[2:]) + 1 if result else 1
    ma = f"PK{next_num:05d}"

    saved = 0
    try:
        for item in items:
            cursor.execute("""
                INSERT INTO Packing
                ([ID sản phẩm], [Mã packing], [Số lượng], [Ngày packing],
                 [Ghi chú], [Người tạo], [Thời gian tạo], [Đã xóa])
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (item.get('id_sanpham'), ma, int(item.get('so_luong', 0)),
                  ngay, item.get('ghi_chu', ''), username, now))
            saved += 1

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Đã lưu {saved} dòng (Mã: {ma})', 'ma': ma, 'count': saved})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 400


@packing_bp.route('/api/packing/delete', methods=['POST'])
@login_required
def delete_packing():
    data = request.get_json()
    item_id = data.get('id')
    if not item_id:
        return jsonify({'success': False, 'message': 'Thiếu ID'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE Packing SET [Đã xóa] = 1, [Người sửa] = ?, [Thời gian sửa] = ? WHERE ID = ?",
        (username, now, item_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đã xóa'})


# ==================== Import DAILY PACKING ====================

@packing_bp.route('/api/packing/scan-files', methods=['GET'])
@login_required
def scan_packing_files():
    """Tìm file DAILY PACKING trong folder EXCEL"""
    from pathlib import Path
    excel_folder = Path("EXCEL")
    if not excel_folder.exists():
        # Try project root
        excel_folder = Path(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'EXCEL'))

    files = []
    if excel_folder.exists():
        for f in sorted(excel_folder.glob("DAILY PACKING*.xls*"), reverse=True):
            month, year = _extract_month_year(f.name)
            files.append({
                'name': f.name, 'path': str(f),
                'month': month, 'year': year,
                'size': f.stat().st_size
            })

    return jsonify({'success': True, 'files': files})


@packing_bp.route('/api/packing/get-sheets', methods=['POST'])
@login_required
def get_sheets():
    """Lấy danh sách sheets (ngày) trong file"""
    data = request.get_json()
    file_path = data.get('file_path')

    if not file_path or not os.path.exists(file_path):
        return jsonify({'success': False, 'message': 'File không tồn tại'}), 400

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        from utils.packing_importer import PackingImporter
        importer = PackingImporter(db_path=config.DATABASE_PATH)
        sheets = importer.get_available_sheets(file_path)
        return jsonify({'success': True, 'sheets': sheets})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@packing_bp.route('/api/packing/preview-sheet', methods=['POST'])
@login_required
def preview_sheet():
    """Preview dữ liệu của 1 sheet"""
    data = request.get_json()
    file_path = data.get('file_path')
    sheet = data.get('sheet')

    if not file_path or not sheet:
        return jsonify({'success': False, 'message': 'Thiếu thông tin'}), 400

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        from utils.packing_importer import PackingImporter
        importer = PackingImporter(db_path=config.DATABASE_PATH)

        preview_df = importer.preview_data(file_path=file_path, sheet_name=sheet, limit=None)

        if len(preview_df) == 0:
            return jsonify({'success': True, 'data': [], 'total_rows': 0, 'total_kg': 0})

        total_kg = float(preview_df['Số lượng (kg)'].sum()) if 'Số lượng (kg)' in preview_df.columns else 0

        # Get Excel total from P2
        excel_total = None
        try:
            excel_total = importer.get_excel_total(file_path=file_path, sheet_name=sheet)
            if excel_total:
                excel_total = float(excel_total)
        except:
            pass

        records = preview_df.fillna('').to_dict('records')

        return jsonify({
            'success': True, 'data': records,
            'total_rows': len(preview_df), 'total_kg': total_kg,
            'excel_total': excel_total
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@packing_bp.route('/api/packing/import-sheet', methods=['POST'])
@login_required
def import_sheet():
    """Import dữ liệu từ 1 sheet"""
    data = request.get_json()
    file_path = data.get('file_path')
    sheet = data.get('sheet')
    filename = data.get('filename', '')

    if not file_path or not sheet:
        return jsonify({'success': False, 'message': 'Thiếu thông tin'}), 400

    month, year = _extract_month_year(filename or os.path.basename(file_path))
    if not month or not year:
        return jsonify({'success': False, 'message': 'Không thể trích xuất tháng/năm từ tên file'}), 400

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        from utils.packing_importer import PackingImporter
        importer = PackingImporter(db_path=config.DATABASE_PATH)

        result = importer.import_packing_data(
            file_path=file_path, sheet_name=sheet,
            nguoi_import=session.get('username', 'system'),
            year=year, month=month
        )

        if result['success'] > 0:
            return jsonify({
                'success': True,
                'message': f"Import thành công {result['success']} SP (Mã: {result['ma_packing']})",
                'count': result['success'],
                'ma': result.get('ma_packing', ''),
                'ngay': result.get('ngay_packing', ''),
                'deleted': result.get('deleted', 0),
                'not_found': result.get('not_found', []),
                'errors': result.get('errors', [])
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Không import được sản phẩm nào',
                'not_found': result.get('not_found', []),
                'errors': result.get('errors', [])
            }), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@packing_bp.route('/api/packing/upload-import', methods=['POST'])
@login_required
def upload_import():
    """Upload file rồi import"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Không có file'}), 400

    file = request.files['file']
    sheet = request.form.get('sheet', '1')

    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsm') as f:
        file.save(f.name)
        temp_path = f.name

    month, year = _extract_month_year(file.filename)
    if not month or not year:
        os.unlink(temp_path)
        return jsonify({'success': False, 'message': 'Không thể trích xuất tháng/năm từ tên file'}), 400

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        from utils.packing_importer import PackingImporter
        importer = PackingImporter(db_path=config.DATABASE_PATH)

        result = importer.import_packing_data(
            file_path=temp_path, sheet_name=sheet,
            nguoi_import=session.get('username', 'system'),
            year=year, month=month
        )
        os.unlink(temp_path)

        if result['success'] > 0:
            return jsonify({
                'success': True,
                'message': f"Import thành công {result['success']} SP",
                'count': result['success'],
                'not_found': result.get('not_found', [])
            })
        else:
            return jsonify({'success': False, 'message': 'Không import được', 'not_found': result.get('not_found', [])}), 400
    except Exception as e:
        try: os.unlink(temp_path)
        except: pass
        return jsonify({'success': False, 'message': str(e)}), 400
