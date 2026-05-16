"""
API routes cho module Plan
Kế hoạch sản xuất: tính toán tự động, nhập thủ công, import Excel, danh sách, xóa, chuyển Pellet
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import login_required
from backend import db
from backend.utils import get_vietnam_time
from datetime import datetime, timedelta
import pandas as pd
import os, tempfile

plan_bp = Blueprint('plan', __name__)

CONG_SUAT_TOI_DA = 2100000
CONG_SUAT_CHO_PHEP = CONG_SUAT_TOI_DA * 1.05
MAX_SAN_PHAM = 25


@plan_bp.route('/api/plan/latest-date', methods=['GET'])
@login_required
def get_latest_date():
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX([Ngày plan]) FROM Plan WHERE [Đã xóa] = 0")
    result = cursor.fetchone()
    conn.close()
    return jsonify({'success': True, 'latest_date': result[0] if result else None})


@plan_bp.route('/api/plan', methods=['GET'])
@login_required
def get_plan_list():
    """Danh sách Plan"""
    ngay = request.args.get('ngay')
    per_page = request.args.get('per_page', 200, type=int)

    conds = ["p.[Đã xóa] = 0"]
    params = []

    if ngay:
        conds.append("(p.[Ngày plan] = ? OR p.[Ngày plan] = ?)")
        # Support both YYYY-MM-DD and DD/MM/YYYY
        try:
            dt = datetime.strptime(ngay, '%Y-%m-%d')
            params.extend([ngay, dt.strftime('%d/%m/%Y')])
        except:
            params.extend([ngay, ngay])

    where = " AND ".join(conds)
    conn = db.connect_db()
    cursor = conn.cursor()

    cursor.execute(f"SELECT COUNT(*) FROM Plan p WHERE {where}", params)
    total = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT p.ID, p.[Mã plan], sp.[Code cám], sp.[Tên cám],
               sp.[Dạng ép viên], sp.[Kích cỡ ép viên],
               p.[Số lượng], p.[Ngày plan], p.[Ghi chú],
               p.[Người tạo], p.[Thời gian tạo]
        FROM Plan p
        LEFT JOIN SanPham sp ON p.[ID sản phẩm] = sp.ID
        WHERE {where}
        ORDER BY p.ID DESC LIMIT ?
    """, params + [per_page])

    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    data = [dict(zip(cols, row)) for row in rows]
    conn.close()

    return jsonify({'success': True, 'data': data, 'total': total})


@plan_bp.route('/api/plan/stats', methods=['GET'])
@login_required
def get_plan_stats():
    """Thống kê theo ngày"""
    ngay = request.args.get('ngay')
    if not ngay:
        return jsonify({'success': True, 'so_sp': 0, 'tong': 0})

    conn = db.connect_db()
    cursor = conn.cursor()

    try:
        dt = datetime.strptime(ngay, '%Y-%m-%d')
        ngay_alt = dt.strftime('%d/%m/%Y')
    except:
        ngay_alt = ngay

    cursor.execute("""
        SELECT COUNT(DISTINCT [ID sản phẩm]) as so_sp,
               COUNT(*) as so_dong,
               COALESCE(SUM([Số lượng]), 0) as tong
        FROM Plan
        WHERE ([Ngày plan] = ? OR [Ngày plan] = ?) AND [Đã xóa] = 0
    """, (ngay, ngay_alt))

    result = cursor.fetchone()
    conn.close()

    so_sp, so_dong, tong = result if result else (0, 0, 0)
    ty_le = (tong / CONG_SUAT_TOI_DA * 100) if tong > 0 else 0

    return jsonify({
        'success': True, 'so_sp': so_sp, 'so_dong': so_dong,
        'tong': tong, 'ty_le': round(ty_le, 1),
        'cong_suat': CONG_SUAT_TOI_DA
    })


@plan_bp.route('/api/plan/ma-plan-list', methods=['GET'])
@login_required
def get_ma_plan_list():
    """Danh sách Mã plan theo ngày"""
    ngay = request.args.get('ngay')
    if not ngay:
        return jsonify({'success': True, 'data': []})

    conn = db.connect_db()
    cursor = conn.cursor()

    try:
        dt = datetime.strptime(ngay, '%Y-%m-%d')
        ngay_alt = dt.strftime('%d/%m/%Y')
    except:
        ngay_alt = ngay

    cursor.execute("""
        SELECT DISTINCT [Mã plan], COUNT(*) as cnt, SUM([Số lượng]) as tong
        FROM Plan
        WHERE ([Ngày plan] = ? OR [Ngày plan] = ?) AND [Đã xóa] = 0
        GROUP BY [Mã plan]
        ORDER BY [Mã plan] DESC
    """, (ngay, ngay_alt))

    rows = cursor.fetchall()
    conn.close()

    data = [{'ma': r[0], 'count': r[1], 'tong': r[2]} for r in rows]
    return jsonify({'success': True, 'data': data})


# ==================== Tính toán kế hoạch ====================

@plan_bp.route('/api/plan/calculate', methods=['POST'])
@login_required
def calculate_plan():
    """Tính toán kế hoạch tự động"""
    data = request.get_json()
    ngay = data.get('ngay')
    skip_sunday = data.get('skip_sunday', True)

    if not ngay:
        return jsonify({'success': False, 'message': 'Thiếu ngày'}), 400

    ngay_dt = datetime.strptime(ngay, '%Y-%m-%d')

    # Skip Sunday
    if skip_sunday:
        while ngay_dt.weekday() == 6:
            ngay_dt += timedelta(days=1)

    ngay_str = ngay_dt.strftime('%Y-%m-%d')
    ngay_alt = ngay_dt.strftime('%d/%m/%Y')
    ngay_lay = (ngay_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    ngay_lay_alt = (ngay_dt + timedelta(days=1)).strftime('%d/%m/%Y')

    conn = db.connect_db()
    cursor = conn.cursor()

    # Check manual plan first
    cursor.execute("""
        SELECT p.[ID sản phẩm], sp.[Code cám], sp.[Tên cám], p.[Số lượng],
               p.[Ghi chú], p.[Mã plan], COALESCE(sh.[Số lượng], 0) as stock
        FROM Plan p
        JOIN SanPham sp ON p.[ID sản phẩm] = sp.ID
        LEFT JOIN StockHomNay sh ON sp.ID = sh.[ID sản phẩm] AND sh.[Đã xóa] = 0
        WHERE (p.[Ngày plan] = ? OR p.[Ngày plan] = ?) AND p.[Đã xóa] = 0
        ORDER BY p.ID ASC
    """, (ngay_str, ngay_alt))

    manual_plans = cursor.fetchall()

    if manual_plans:
        danh_sach = []
        tong = 0
        ma_plans = set()
        for row in manual_plans:
            id_sp, code, ten, sl, gc, ma, stock = row
            danh_sach.append({
                'id_sanpham': id_sp, 'code': code, 'ten': ten,
                'so_luong': sl, 'stock': stock, 'doh': 999,
                'ghi_chu': gc or 'Kế hoạch thủ công', 'loai': 'Thủ công'
            })
            tong += sl
            ma_plans.add(ma)

        conn.close()
        ty_le = round(tong / CONG_SUAT_TOI_DA * 100, 1)
        return jsonify({
            'success': True, 'loai': 'manual',
            'ngay': ngay_str, 'ngay_display': ngay_dt.strftime('%d/%m/%Y'),
            'danh_sach': danh_sach, 'tong': tong, 'ty_le': ty_le,
            'so_sp': len(danh_sach), 'ma_plan': ', '.join(ma_plans)
        })

    # Auto calculate
    danh_sach_uu_tien = []
    ngay_thu = ngay_dt.weekday()

    # Forecast tuần — bao 50kg
    if ngay_thu < 5:
        cursor.execute("""
            SELECT sp.ID, sp.[Code cám], sp.[Tên cám], fc.[Số lượng],
                   COALESCE(sh.[Số lượng], 0) as stock
            FROM SanPham sp
            JOIN (SELECT [ID sản phẩm], SUM([Số lượng]) as [Số lượng]
                  FROM DatHang WHERE [Loại đặt hàng] = 'Forecast tuần' AND [Đã xóa] = 0
                  GROUP BY [ID sản phẩm]) fc ON sp.ID = fc.[ID sản phẩm]
            LEFT JOIN StockHomNay sh ON sp.ID = sh.[ID sản phẩm] AND sh.[Đã xóa] = 0
            WHERE sp.[Đã xóa] = 0 AND sp.[Kích cỡ đóng bao] = 50
        """)
        for row in cursor.fetchall():
            id_sp, code, ten, fc_tuan, stock = row
            sl = fc_tuan / 5
            fc_ngay = fc_tuan / 7
            doh = stock / fc_ngay if fc_ngay > 0 else 999
            gc = f"Bao 50kg - Chia đều 5 ngày (ngày {ngay_thu+1}/5)"
            danh_sach_uu_tien.append({
                'id_sanpham': id_sp, 'code': code, 'ten': ten,
                'so_luong': sl, 'stock': stock, 'doh': round(doh, 1),
                'ghi_chu': gc, 'uu_tien': 3, 'loai': 'Bao 50kg'
            })

    # Đơn Bá Cang
    cursor.execute("""
        SELECT dh.[ID sản phẩm], sp.[Code cám], sp.[Tên cám],
               SUM(dh.[Số lượng]) as tong, COALESCE(sh.[Số lượng], 0) as stock
        FROM DatHang dh
        JOIN SanPham sp ON dh.[ID sản phẩm] = sp.ID
        LEFT JOIN StockHomNay sh ON sp.ID = sh.[ID sản phẩm] AND sh.[Đã xóa] = 0
        WHERE dh.[Loại đặt hàng] = 'Đại lý Bá Cang'
        AND (dh.[Ngày lấy] = ? OR dh.[Ngày lấy] = ?)
        AND dh.[Đã xóa] = 0
        GROUP BY dh.[ID sản phẩm], sp.[Code cám], sp.[Tên cám]
    """, (ngay_lay, ngay_lay_alt))
    for row in cursor.fetchall():
        id_sp, code, ten, sl, stock = row
        danh_sach_uu_tien.append({
            'id_sanpham': id_sp, 'code': code, 'ten': ten,
            'so_luong': sl, 'stock': stock, 'doh': 0,
            'ghi_chu': f'Đơn Bá Cang - Giao {ngay_lay}', 'uu_tien': 1, 'loai': 'Đơn hàng'
        })

    # Xe bồn Silo
    cursor.execute("""
        SELECT dh.[ID sản phẩm], sp.[Code cám], sp.[Tên cám],
               SUM(dh.[Số lượng]) as tong, COALESCE(sh.[Số lượng], 0) as stock
        FROM DatHang dh
        JOIN SanPham sp ON dh.[ID sản phẩm] = sp.ID
        LEFT JOIN StockHomNay sh ON sp.ID = sh.[ID sản phẩm] AND sh.[Đã xóa] = 0
        WHERE dh.[Loại đặt hàng] = 'Xe bồn Silo'
        AND (dh.[Ngày lấy] = ? OR dh.[Ngày lấy] = ?)
        AND dh.[Đã xóa] = 0
        GROUP BY dh.[ID sản phẩm], sp.[Code cám], sp.[Tên cám]
    """, (ngay_lay, ngay_lay_alt))
    for row in cursor.fetchall():
        id_sp, code, ten, sl, stock = row
        danh_sach_uu_tien.append({
            'id_sanpham': id_sp, 'code': code, 'ten': ten,
            'so_luong': sl, 'stock': stock, 'doh': 0,
            'ghi_chu': f'Xe Silo - Lấy {ngay_lay}', 'uu_tien': 1, 'loai': 'Đơn hàng'
        })

    # DoH < 3 từ Forecast
    cursor.execute("""
        SELECT sp.ID, sp.[Code cám], sp.[Tên cám],
               COALESCE(sh.[Số lượng], 0) as stock,
               COALESCE(fc.[Số lượng], 0) as forecast
        FROM SanPham sp
        LEFT JOIN StockHomNay sh ON sp.ID = sh.[ID sản phẩm] AND sh.[Đã xóa] = 0
        LEFT JOIN (SELECT [ID sản phẩm], SUM([Số lượng]) as [Số lượng]
                   FROM DatHang WHERE [Loại đặt hàng] = 'Forecast tuần' AND [Đã xóa] = 0
                   GROUP BY [ID sản phẩm]) fc ON sp.ID = fc.[ID sản phẩm]
        WHERE sp.[Đã xóa] = 0
    """)
    for row in cursor.fetchall():
        id_sp, code, ten, stock, forecast = row
        if forecast > 0:
            fc_ngay = forecast / 7
            doh = stock / fc_ngay if fc_ngay > 0 else 999
            if doh < 3:
                sl = forecast if forecast < 50000 else fc_ngay * 3
                gc = f"DoH={doh:.1f}" + (" → Chạy 1 lần" if forecast < 50000 else " → SX 3 ngày")
                danh_sach_uu_tien.append({
                    'id_sanpham': id_sp, 'code': code, 'ten': ten,
                    'so_luong': sl, 'stock': stock, 'doh': round(doh, 1),
                    'ghi_chu': gc, 'uu_tien': 2, 'loai': 'Forecast'
                })

    conn.close()

    # Sort and apply capacity limit
    danh_sach_uu_tien.sort(key=lambda x: (x['uu_tien'], x['doh'], -x['so_luong']))
    ke_hoach = []
    tong = 0

    for item in danh_sach_uu_tien:
        if len(ke_hoach) >= MAX_SAN_PHAM or tong >= CONG_SUAT_CHO_PHEP:
            break
        sl = item['so_luong']
        if tong + sl > CONG_SUAT_CHO_PHEP:
            sl = CONG_SUAT_CHO_PHEP - tong
            if sl < 1000:
                break
            item['ghi_chu'] += f" (Điều chỉnh: {item['so_luong']:,.0f} → {sl:,.0f})"
            item['so_luong'] = sl
        ke_hoach.append(item)
        tong += sl

    if not ke_hoach:
        return jsonify({'success': False, 'message': 'Không có dữ liệu để lên kế hoạch'})

    ty_le = round(tong / CONG_SUAT_TOI_DA * 100, 1)
    return jsonify({
        'success': True, 'loai': 'auto',
        'ngay': ngay_str, 'ngay_display': ngay_dt.strftime('%d/%m/%Y'),
        'danh_sach': ke_hoach, 'tong': tong, 'ty_le': ty_le,
        'so_sp': len(ke_hoach)
    })


@plan_bp.route('/api/plan/save-calculated', methods=['POST'])
@login_required
def save_calculated():
    """Lưu kế hoạch đã tính toán"""
    data = request.get_json()
    danh_sach = data.get('danh_sach', [])
    ngay = data.get('ngay')

    if not danh_sach or not ngay:
        return jsonify({'success': False, 'message': 'Thiếu dữ liệu'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT MAX([Mã plan]) FROM Plan WHERE [Mã plan] LIKE 'PL%'")
    result = cursor.fetchone()[0]
    next_num = int(result[2:]) + 1 if result else 1
    ma = f"PL{next_num:05d}"

    saved = 0
    for item in danh_sach:
        cursor.execute("""
            INSERT INTO Plan ([ID sản phẩm], [Mã plan], [Số lượng], [Ngày plan],
                              [Ghi chú], [Người tạo], [Thời gian tạo], [Đã xóa])
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (item['id_sanpham'], ma, item['so_luong'], ngay,
              item.get('ghi_chu', ''), username, now))
        saved += 1

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Đã lưu {saved} SP (Mã: {ma})', 'ma': ma, 'count': saved})


# ==================== Nhập thủ công + Import Excel ====================

@plan_bp.route('/api/plan/create', methods=['POST'])
@login_required
def create_plan():
    """Nhập thủ công"""
    data = request.get_json()
    items = data.get('items', [])
    if not items:
        return jsonify({'success': False, 'message': 'Không có dữ liệu'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT MAX([Mã plan]) FROM Plan WHERE [Mã plan] LIKE 'PL%'")
    result = cursor.fetchone()[0]
    next_num = int(result[2:]) + 1 if result else 1
    ma = f"PL{next_num:05d}"

    saved = 0
    for item in items:
        cursor.execute("""
            INSERT INTO Plan ([ID sản phẩm], [Mã plan], [Số lượng], [Ngày plan],
                              [Ghi chú], [Người tạo], [Thời gian tạo], [Đã xóa])
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (item.get('id_sanpham'), ma, int(item.get('so_luong', 0)),
              item.get('ngay_plan', get_vietnam_time().strftime('%Y-%m-%d')),
              item.get('ghi_chu', ''), username, now))
        saved += 1

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Đã lưu {saved} dòng (Mã: {ma})', 'ma': ma, 'count': saved})


@plan_bp.route('/api/plan/import-excel', methods=['POST'])
@login_required
def import_excel():
    """Import từ Excel - cần cột 'Tên sản phẩm' + 'Số lượng'"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Không có file'}), 400

    file = request.files['file']
    ngay_plan = request.form.get('ngay_plan', get_vietnam_time().strftime('%Y-%m-%d'))

    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as f:
        file.save(f.name)
        temp_path = f.name

    try:
        df = pd.read_excel(temp_path)
        os.unlink(temp_path)

        if 'Tên sản phẩm' not in df.columns:
            return jsonify({'success': False, 'message': "File cần cột 'Tên sản phẩm'"}), 400
        if 'Số lượng' not in df.columns:
            return jsonify({'success': False, 'message': "File cần cột 'Số lượng'"}), 400

        username = session.get('username', 'system')
        now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

        conn = db.connect_db()
        cursor = conn.cursor()

        cursor.execute("SELECT MAX([Mã plan]) FROM Plan WHERE [Mã plan] LIKE 'PL%'")
        result = cursor.fetchone()[0]
        next_num = int(result[2:]) + 1 if result else 1
        ma = f"PL{next_num:05d}"

        saved = 0
        not_found = []

        for _, row in df.iterrows():
            ten = str(row['Tên sản phẩm']).strip()
            sl = row['Số lượng']
            gc = row.get('Ghi chú', row.get('Ghi chú (tùy chọn)', ''))
            np_ = row.get('Ngày plan', row.get('Ngày plan (tùy chọn)', ngay_plan))

            if pd.isna(sl) or sl <= 0:
                continue

            cursor.execute("SELECT ID FROM SanPham WHERE [Tên cám] = ? AND [Đã xóa] = 0", (ten,))
            sp = cursor.fetchone()
            if not sp:
                not_found.append(ten)
                continue

            cursor.execute("""
                INSERT INTO Plan ([ID sản phẩm], [Mã plan], [Số lượng], [Ngày plan],
                                  [Ghi chú], [Người tạo], [Thời gian tạo], [Đã xóa])
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (sp[0], ma, int(sl), np_ if not pd.isna(np_) else ngay_plan,
                  gc if not pd.isna(gc) else '', username, now))
            saved += 1

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'Import {saved} SP (Mã: {ma})',
            'ma': ma, 'count': saved,
            'not_found': not_found
        })
    except Exception as e:
        try: os.unlink(temp_path)
        except: pass
        return jsonify({'success': False, 'message': str(e)}), 400


# ==================== Delete ====================

@plan_bp.route('/api/plan/delete', methods=['POST'])
@login_required
def delete_plan():
    """Xóa theo ID"""
    data = request.get_json()
    item_id = data.get('id')
    if not item_id:
        return jsonify({'success': False, 'message': 'Thiếu ID'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE Plan SET [Đã xóa] = 1, [Người sửa] = ?, [Thời gian sửa] = ? WHERE ID = ?",
                   (username, now, item_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đã xóa'})


@plan_bp.route('/api/plan/delete-by-maplan', methods=['POST'])
@login_required
def delete_by_maplan():
    """Xóa theo Mã plan hoặc theo ngày"""
    data = request.get_json()
    ma_plan = data.get('ma_plan')
    ngay = data.get('ngay')

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()

    if ma_plan:
        cursor.execute(
            "UPDATE Plan SET [Đã xóa] = 1, [Người sửa] = ?, [Thời gian sửa] = ? WHERE [Mã plan] = ? AND [Đã xóa] = 0",
            (username, now, ma_plan))
    elif ngay:
        try:
            dt = datetime.strptime(ngay, '%Y-%m-%d')
            ngay_alt = dt.strftime('%d/%m/%Y')
        except:
            ngay_alt = ngay
        cursor.execute(
            "UPDATE Plan SET [Đã xóa] = 1, [Người sửa] = ?, [Thời gian sửa] = ? WHERE ([Ngày plan] = ? OR [Ngày plan] = ?) AND [Đã xóa] = 0",
            (username, now, ngay, ngay_alt))
    else:
        conn.close()
        return jsonify({'success': False, 'message': 'Cần Mã plan hoặc Ngày'}), 400

    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Đã xóa {deleted} dòng', 'deleted': deleted})
