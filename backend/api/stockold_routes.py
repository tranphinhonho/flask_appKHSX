"""
API routes cho module Stock Old
Quản lý tồn kho cũ: biểu đồ theo vật nuôi, import Excel, nhập thủ công, danh sách
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import login_required
from backend import db
from backend.utils import get_vietnam_time
import os, tempfile

stockold_bp = Blueprint('stockold', __name__)

VAT_NUOI_LABELS = {'H': 'HEO', 'G': 'GÀ', 'B': 'BÒ', 'V': 'VỊT', 'C': 'CÚT', 'D': 'DÊ'}
VAT_NUOI_COLORS = {'H': '#FF6B6B', 'G': '#4ECDC4', 'B': '#45B7D1', 'V': '#96CEB4', 'C': '#FFEAA7', 'D': '#DDA0DD'}


@stockold_bp.route('/api/stockold/latest-date', methods=['GET'])
@login_required
def get_latest_date():
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX([Ngày stock old]) FROM StockOld WHERE [Đã xóa] = 0")
    result = cursor.fetchone()
    conn.close()
    return jsonify({'success': True, 'latest_date': result[0] if result else None})


@stockold_bp.route('/api/stockold/days-in-month', methods=['GET'])
@login_required
def get_days_in_month():
    """Trả về danh sách ngày (1-31) có dữ liệu trong tháng/năm cho trước"""
    year  = request.args.get('year',  type=int)
    month = request.args.get('month', type=int)
    if not year or not month:
        return jsonify({'success': False, 'message': 'Thiếu year/month'}), 400

    month_str = f"{year}-{month:02d}"
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT CAST([Ngày stock old] AS TEXT) as ngay_str
        FROM StockOld
        WHERE [Đã xóa] = 0
          AND CAST([Ngày stock old] AS TEXT) LIKE ?
        ORDER BY ngay_str
    """, (month_str + '%',))
    rows = cursor.fetchall()
    conn.close()

    # Lấy số ngày từ chuỗi 'YYYY-MM-DD'
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





@stockold_bp.route('/api/stockold/chart', methods=['GET'])
@login_required
def get_chart_data():
    """Dữ liệu biểu đồ tồn kho theo vật nuôi"""
    ngay = request.args.get('ngay')
    conn = db.connect_db()
    cursor = conn.cursor()

    date_cond = "AND s.[Ngày stock old] = ?" if ngay else ""
    params = (ngay,) if ngay else ()

    cursor.execute(f"""
        SELECT sp.[Vật nuôi], SUM(CAST(s.[Số lượng] AS INTEGER)) as tong
        FROM StockOld s
        LEFT JOIN SanPham sp ON CAST(s.[ID sản phẩm] AS INTEGER) = sp.ID
        WHERE s.[Đã xóa] = 0 AND sp.[Vật nuôi] IS NOT NULL
        {date_cond}
        GROUP BY sp.[Vật nuôi]
        ORDER BY SUM(CAST(s.[Số lượng] AS INTEGER)) DESC
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
            'code': code,
            'label': VAT_NUOI_LABELS.get(code, code),
            'color': VAT_NUOI_COLORS.get(code, '#999'),
            'kg': kg
        })

    for d in data:
        d['pct'] = round((d['kg'] / total * 100), 1) if total > 0 else 0

    return jsonify({'success': True, 'data': data, 'total': total})


@stockold_bp.route('/api/stockold', methods=['GET'])
@login_required
def get_stockold_list():
    """Danh sách Stock Old"""
    ngay = request.args.get('ngay')
    vatnuoi = request.args.get('vatnuoi')
    per_page = request.args.get('per_page', 200, type=int)

    conds = ["s.[Đã xóa] = 0"]
    params = []

    if ngay:
        conds.append("s.[Ngày stock old] = ?")
        params.append(ngay)
    if vatnuoi and vatnuoi != 'Tất cả':
        conds.append("sp.[Vật nuôi] = ?")
        params.append(vatnuoi)

    where = " AND ".join(conds)

    conn = db.connect_db()
    cursor = conn.cursor()

    cursor.execute(f"SELECT COUNT(*) FROM StockOld s LEFT JOIN SanPham sp ON CAST(s.[ID sản phẩm] AS INTEGER) = sp.ID WHERE {where}", params)
    total = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT s.ID, s.[Mã stock old], sp.[Code cám], sp.[Tên cám],
               sp.[Dạng ép viên], sp.[Kích cỡ ép viên], sp.[Vật nuôi],
               s.[Số lượng], s.[Ngày stock old], s.[Ghi chú],
               s.[Người tạo], s.[Thời gian tạo]
        FROM StockOld s
        LEFT JOIN SanPham sp ON CAST(s.[ID sản phẩm] AS INTEGER) = sp.ID
        WHERE {where}
        ORDER BY s.ID DESC LIMIT ?
    """, params + [per_page])

    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    data = [dict(zip(cols, row)) for row in rows]
    conn.close()

    return jsonify({'success': True, 'data': data, 'total': total})


@stockold_bp.route('/api/stockold/create', methods=['POST'])
@login_required
def create_stockold():
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

    # Generate mã stock old
    cursor.execute("SELECT MAX([Mã stock old]) FROM StockOld WHERE [Mã stock old] LIKE 'SO%'")
    result = cursor.fetchone()[0]
    next_num = int(result[2:]) + 1 if result else 1
    ma = f"SO{next_num:05d}"

    saved = 0
    try:
        for item in items:
            cursor.execute("""
                INSERT INTO StockOld
                ([ID sản phẩm], [Mã stock old], [Số lượng], [Ngày stock old],
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


@stockold_bp.route('/api/stockold/upload-import', methods=['POST'])
@login_required
def upload_import():
    """Import Stock Old từ file Excel"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Không có file'}), 400

    file = request.files['file']
    col_code = request.form.get('col_code', '0')
    col_tonkho = request.form.get('col_tonkho', '5')
    col_doh = request.form.get('col_doh', '6')

    import pandas as pd

    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as f:
        file.save(f.name)
        temp_path = f.name

    try:
        df = pd.read_excel(temp_path)

        col_code_idx = int(col_code)
        col_tonkho_idx = int(col_tonkho)
        col_doh_idx = int(col_doh)

        col_names = df.columns.tolist()

        username = session.get('username', 'system')
        now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')
        ngay = get_vietnam_time().strftime('%Y-%m-%d')

        conn = db.connect_db()
        cursor = conn.cursor()

        # Gen mã
        cursor.execute("SELECT MAX([Mã stock old]) FROM StockOld WHERE [Mã stock old] LIKE 'SO%'")
        result = cursor.fetchone()[0]
        next_num = int(result[2:]) + 1 if result else 1
        ma = f"SO{next_num:05d}"

        saved = 0
        not_found = []

        for _, row in df.iterrows():
            code_cam = str(row.iloc[col_code_idx]).strip() if pd.notna(row.iloc[col_code_idx]) else ''
            try:
                ton_kho = int(float(row.iloc[col_tonkho_idx])) if pd.notna(row.iloc[col_tonkho_idx]) else 0
            except:
                ton_kho = 0
            try:
                doh = float(row.iloc[col_doh_idx]) if pd.notna(row.iloc[col_doh_idx]) else 0
            except:
                doh = 0

            if not code_cam or ton_kho <= 0:
                continue

            cursor.execute(
                "SELECT ID FROM SanPham WHERE TRIM([Code cám]) = ? AND [Đã xóa] = 0", (code_cam,)
            )
            sp = cursor.fetchone()
            if not sp:
                not_found.append(code_cam)
                continue

            cursor.execute("""
                INSERT INTO StockOld
                ([ID sản phẩm], [Mã stock old], [Số lượng], [Ngày stock old],
                 [Ghi chú], [Người tạo], [Thời gian tạo], [Đã xóa])
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (sp[0], ma, ton_kho, ngay, f"Day On Hand: {doh:.1f}", username, now))
            saved += 1

        conn.commit()
        conn.close()
        os.unlink(temp_path)

        return jsonify({
            'success': True,
            'message': f'Import thành công {saved} SP (Mã: {ma})',
            'count': saved, 'ma': ma,
            'not_found': not_found,
            'columns': col_names
        })
    except Exception as e:
        try: os.unlink(temp_path)
        except: pass
        return jsonify({'success': False, 'message': str(e)}), 400


@stockold_bp.route('/api/stockold/preview-excel', methods=['POST'])
@login_required
def preview_excel():
    """Preview file Excel trước khi import"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Không có file'}), 400

    import pandas as pd
    file = request.files['file']

    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as f:
        file.save(f.name)
        temp_path = f.name

    try:
        df = pd.read_excel(temp_path)
        columns = df.columns.tolist()
        preview = df.head(10).fillna('').values.tolist()
        os.unlink(temp_path)

        return jsonify({
            'success': True,
            'columns': columns,
            'preview': preview,
            'total_rows': len(df),
            'tmp_path': temp_path
        })
    except Exception as e:
        try: os.unlink(temp_path)
        except: pass
        return jsonify({'success': False, 'message': str(e)}), 400


@stockold_bp.route('/api/stockold/delete', methods=['POST'])
@login_required
def delete_stockold():
    data = request.get_json()
    item_id = data.get('id')
    if not item_id:
        return jsonify({'success': False, 'message': 'Thiếu ID'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE StockOld SET [Đã xóa] = 1, [Người sửa] = ?, [Thời gian sửa] = ? WHERE ID = ?",
        (username, now, item_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đã xóa'})
