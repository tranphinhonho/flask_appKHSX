"""
API routes cho module Pellet Plan
Quản lý Pellet: phân bổ tự động, nhập thủ công, danh sách, T/h capacity
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import login_required
from backend import db
from backend.utils import get_vietnam_time
from datetime import datetime, timedelta
import config
import os, sys

pellet_bp = Blueprint('pellet', __name__)

DEFAULT_MACHINES = {
    'PL1': 10, 'PL2': 10, 'PL3': 9,
    'PL4': 9, 'PL5': 8, 'PL6': 8, 'PL7': 8
}

MACHINE_DISPLAY = {
    'PL1': 'Pellet 1', 'PL2': 'Pellet 2', 'PL3': 'Pellet 3',
    'PL4': 'Pellet 4', 'PL5': 'Pellet 5', 'PL6': 'Pellet 6', 'PL7': 'Pellet 7'
}


# ==================== Danh sách Pellet ====================

@pellet_bp.route('/api/pellet', methods=['GET'])
@login_required
def get_pellet_list():
    """Lấy danh sách Pellet"""
    ngay = request.args.get('ngay')
    so_may = request.args.get('so_may')
    per_page = request.args.get('per_page', 200, type=int)

    conn = db.connect_db()
    cursor = conn.cursor()

    conds = ["p.[Đã xóa] = 0"]
    params = []

    if ngay:
        conds.append("p.[Ngày sản xuất] = ?")
        params.append(ngay)
    if so_may and so_may != 'Tất cả':
        conds.append("p.[Số máy] = ?")
        params.append(so_may)

    where = " AND ".join(conds)

    cursor.execute(f"SELECT COUNT(*) FROM Pellet p WHERE {where}", params)
    total = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT p.ID, p.[Ngày sản xuất], p.[ID sản phẩm],
               sp.[Code cám], sp.[Tên cám],
               p.[Số lượng], p.[Số máy],
               p.[Thời gian bắt đầu], p.[Thời gian kết thúc],
               p.[Thời gian chạy (giờ)], p.[Công suất máy (tấn/giờ)],
               p.[T/h], p.[Kwh/T],
               p.[Ghi chú], p.[Người tạo], p.[Thời gian tạo]
        FROM Pellet p
        LEFT JOIN SanPham sp ON p.[ID sản phẩm] = sp.ID
        WHERE {where}
        ORDER BY p.[Ngày sản xuất] DESC, p.ID DESC
        LIMIT ?
    """, params + [per_page])

    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    data = [dict(zip(cols, row)) for row in rows]

    conn.close()
    return jsonify({'success': True, 'data': data, 'total': total})


@pellet_bp.route('/api/pellet/latest-date', methods=['GET'])
@login_required
def get_pellet_latest():
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX([Ngày sản xuất]) FROM Pellet WHERE [Đã xóa] = 0")
    result = cursor.fetchone()
    conn.close()
    return jsonify({'success': True, 'latest_date': result[0] if result else None})


# ==================== Phân bổ tự động ====================

@pellet_bp.route('/api/pellet/auto-allocate', methods=['POST'])
@login_required
def auto_allocate():
    """Phân bổ tự động 7 máy Pellet từ Plan data"""
    data = request.get_json()
    ngay = data.get('ngay')
    if not ngay:
        return jsonify({'success': False, 'message': 'Thiếu ngày'}), 400

    conn = db.connect_db()
    cursor = conn.cursor()

    # Lấy Plan data
    cursor.execute("""
        SELECT p.ID, p.[Mã plan], sp.[Code cám], sp.[Tên cám],
               p.[Số lượng], sp.[Dạng ép viên]
        FROM Plan p
        LEFT JOIN SanPham sp ON p.[ID sản phẩm] = sp.ID
        WHERE p.[Ngày plan] = ? AND p.[Đã xóa] = 0
        ORDER BY p.[Số lượng] DESC
    """, (ngay,))

    plan_rows = cursor.fetchall()
    if not plan_rows:
        conn.close()
        return jsonify({'success': False, 'message': 'Không có kế hoạch Plan cho ngày này'})

    # Get PelletCapacity T/h data
    capacity_data = {}
    try:
        cursor.execute("""
            SELECT [Code cám], [Số máy], MAX([T/h]) as max_th, AVG([Kwh/T]) as avg_kwh
            FROM PelletCapacity WHERE [Đã xóa] = 0 AND [T/h] > 0
            GROUP BY [Code cám], [Số máy]
            ORDER BY MAX([T/h]) DESC
        """)
        for row in cursor.fetchall():
            code = row[0]
            if code not in capacity_data:
                capacity_data[code] = []
            capacity_data[code].append({
                'so_may': row[1], 'th': row[2], 'kwh_t': row[3]
            })
    except:
        pass

    conn.close()

    # Allocate
    machines = {m: {'hours_used': 0, 'jobs': []} for m in DEFAULT_MACHINES}
    phan_bo = []
    warnings = []

    for row in plan_rows:
        plan_id, ma_plan, code_cam, ten_cam, so_luong, dang_ep = row

        # Find capacity data
        cap_list = capacity_data.get(code_cam, [])
        # Also try matching by Tên cám
        if not cap_list and ten_cam:
            cap_list = capacity_data.get(ten_cam, [])

        allocated = False

        if cap_list:
            for cap in cap_list:
                mc = cap['so_may']
                th = cap['th']
                kwh = cap.get('kwh_t', 0)

                if mc in machines:
                    hours_needed = so_luong / th if th > 0 else so_luong / DEFAULT_MACHINES.get(mc, 8)
                    if machines[mc]['hours_used'] + hours_needed <= 24:
                        phan_bo.append({
                            'plan_id': plan_id, 'ma_plan': ma_plan,
                            'code_cam': code_cam, 'ten_cam': ten_cam or '',
                            'so_luong': so_luong, 'so_may': mc,
                            'th': round(th, 2), 'kwh_t': round(kwh, 2) if kwh else None,
                            'hours': round(hours_needed, 2),
                            'nguon': 'Từ dữ liệu thực tế'
                        })
                        machines[mc]['hours_used'] += hours_needed
                        allocated = True
                        break

        if not allocated:
            # Fallback: use default capacity
            if not cap_list:
                warnings.append(f'📢 {code_cam or ten_cam}: Không có dữ liệu T/h, dùng mặc định')

            best_mc = None
            best_cap = 0
            for mc, info in machines.items():
                if info['hours_used'] < 24 and DEFAULT_MACHINES[mc] > best_cap:
                    best_cap = DEFAULT_MACHINES[mc]
                    best_mc = mc

            if best_mc:
                hours_needed = so_luong / best_cap
                if machines[best_mc]['hours_used'] + hours_needed <= 24:
                    phan_bo.append({
                        'plan_id': plan_id, 'ma_plan': ma_plan,
                        'code_cam': code_cam, 'ten_cam': ten_cam or '',
                        'so_luong': so_luong, 'so_may': best_mc,
                        'th': best_cap, 'kwh_t': None,
                        'hours': round(hours_needed, 2),
                        'nguon': 'Mặc định'
                    })
                    machines[best_mc]['hours_used'] += hours_needed
                else:
                    warnings.append(f'⚠️ {code_cam}: Tất cả máy đã đầy')

    tong = sum(i['so_luong'] for i in phan_bo)
    machines_summary = {m: round(info['hours_used'], 1) for m, info in machines.items()}

    return jsonify({
        'success': True,
        'phan_bo': phan_bo,
        'machines': machines_summary,
        'tong_san_luong': round(tong, 1),
        'warnings': warnings,
        'machines_used': sum(1 for v in machines_summary.values() if v > 0)
    })


@pellet_bp.route('/api/pellet/save-allocation', methods=['POST'])
@login_required
def save_allocation():
    """Lưu phân bổ tự động vào Pellet"""
    data = request.get_json()
    phan_bo = data.get('phan_bo', [])
    ngay = data.get('ngay')

    if not phan_bo or not ngay:
        return jsonify({'success': False, 'message': 'Thiếu dữ liệu'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()
    saved = 0

    try:
        start_time = datetime.strptime(ngay, '%Y-%m-%d').replace(hour=7)

        for item in phan_bo:
            so_may_display = MACHINE_DISPLAY.get(item.get('so_may', ''), item.get('so_may', ''))
            hours = item.get('hours', 0)
            end_time = start_time + timedelta(hours=hours)

            # Get ID sản phẩm from Code cám
            id_sp = None
            code_cam = item.get('code_cam', '')
            if code_cam:
                cursor.execute(
                    "SELECT ID FROM SanPham WHERE ([Code cám] = ? OR [Tên cám] = ?) AND [Đã xóa] = 0 LIMIT 1",
                    (code_cam, code_cam)
                )
                row = cursor.fetchone()
                if row:
                    id_sp = row[0]

            cursor.execute("""
                INSERT INTO Pellet
                ([Ngày sản xuất], [ID sản phẩm], [Số lượng], [Số máy],
                 [Công suất máy (tấn/giờ)], [T/h], [Kwh/T], [Thời gian chạy (giờ)],
                 [Thời gian bắt đầu], [Thời gian kết thúc],
                 [Ghi chú], [Người tạo], [Thời gian tạo], [Đã xóa])
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (ngay, id_sp, item.get('so_luong', 0), so_may_display,
                  item.get('th', 0), item.get('th', 0), item.get('kwh_t'),
                  hours,
                  start_time.strftime('%Y-%m-%d %H:%M:%S'),
                  end_time.strftime('%Y-%m-%d %H:%M:%S'),
                  f"Plan: {item.get('ma_plan', '')}", username, now))
            saved += 1

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Đã lưu {saved} dòng', 'count': saved})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 400


# ==================== Nhập thủ công ====================

@pellet_bp.route('/api/pellet/create', methods=['POST'])
@login_required
def create_pellet():
    data = request.get_json()
    items = data.get('items', [])
    if not items:
        return jsonify({'success': False, 'message': 'Không có dữ liệu'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()
    saved = 0

    try:
        for item in items:
            so_luong = float(item.get('so_luong', 0))
            so_may = item.get('so_may', 'Pellet 1')

            # Get default capacity for machine
            reverse_display = {v: k for k, v in MACHINE_DISPLAY.items()}
            mc = reverse_display.get(so_may, 'PL1')
            capacity = DEFAULT_MACHINES.get(mc, 8)
            hours = round(so_luong / capacity, 2) if capacity > 0 else 0

            cursor.execute("""
                INSERT INTO Pellet
                ([Ngày sản xuất], [ID sản phẩm], [Số lượng], [Số máy],
                 [Công suất máy (tấn/giờ)], [Thời gian chạy (giờ)],
                 [Ghi chú], [Người tạo], [Thời gian tạo], [Đã xóa])
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (item.get('ngay'), item.get('id_sanpham'),
                  so_luong, so_may, capacity, hours,
                  item.get('ghi_chu', ''), username, now))
            saved += 1

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Đã lưu {saved} dòng', 'count': saved})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 400


@pellet_bp.route('/api/pellet/delete', methods=['POST'])
@login_required
def delete_pellet():
    data = request.get_json()
    item_id = data.get('id')
    if not item_id:
        return jsonify({'success': False, 'message': 'Thiếu ID'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE Pellet SET [Đã xóa] = 1, [Người sửa] = ?, [Thời gian sửa] = ? WHERE ID = ?",
        (username, now, item_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đã xóa'})


# ==================== PelletCapacity (T/h data) ====================

@pellet_bp.route('/api/pellet/capacity-stats', methods=['GET'])
@login_required
def get_capacity_stats():
    """Thống kê T/h theo máy"""
    conn = db.connect_db()
    cursor = conn.cursor()

    try:
        cursor.execute(db._translate_sql("""
            SELECT [Số máy],
                   COUNT(DISTINCT [Code cám]) as so_loai,
                   AVG([T/h]) as th_tb, MAX([T/h]) as th_max, MIN([T/h]) as th_min,
                   AVG([Kwh/T]) as kwh_tb, MAX([Kwh/T]) as kwh_max, MIN([Kwh/T]) as kwh_min,
                   SUM([Số lô]) as tong_lo, MAX([Ngày]) as ngay_cn
            FROM PelletCapacity WHERE [Đã xóa] = 0
            GROUP BY [Số máy] ORDER BY [Số máy]
        """))
        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        data = [dict(zip(cols, row)) for row in rows]
        conn.close()

        return jsonify({'success': True, 'data': data, 'total_machines': len(data)})
    except Exception as e:
        conn.close()
        return jsonify({'success': True, 'data': [], 'total_machines': 0, 'error': str(e)})


@pellet_bp.route('/api/pellet/capacity-detail', methods=['GET'])
@login_required
def get_capacity_detail():
    """Chi tiết T/h theo máy hoặc ngày"""
    so_may = request.args.get('so_may')
    ngay = request.args.get('ngay')

    conn = db.connect_db()
    cursor = conn.cursor()

    try:
        if ngay:
            cursor.execute(db._translate_sql("""
                SELECT pc.[Số máy], pc.[Code cám], pc.[T/h], pc.[Kwh/T], pc.[Số lô], pc.[Ngày],
                       sp.[Tên cám], sp.[Vật nuôi], sp.[Kích cỡ ép viên], pc.[Thông số khuôn]
                FROM PelletCapacity pc
                LEFT JOIN SanPham sp ON (pc.[Code cám] = sp.[Code cám] OR pc.[Code cám] = sp.[Tên cám])
                WHERE pc.[Ngày] = ? AND pc.[Đã xóa] = 0
                ORDER BY pc.[Số máy], pc.[T/h] DESC
            """), (ngay,))
        elif so_may:
            cursor.execute(db._translate_sql("""
                SELECT pc.[Số máy], pc.[Code cám], pc.[T/h], pc.[Kwh/T], pc.[Số lô], pc.[Ngày],
                       sp.[Tên cám], sp.[Vật nuôi], sp.[Kích cỡ ép viên], pc.[Thông số khuôn]
                FROM PelletCapacity pc
                LEFT JOIN SanPham sp ON (pc.[Code cám] = sp.[Code cám] OR pc.[Code cám] = sp.[Tên cám])
                WHERE pc.[Số máy] = ? AND pc.[Đã xóa] = 0
                ORDER BY pc.[T/h] DESC
            """), (so_may,))
        else:
            conn.close()
            return jsonify({'success': True, 'data': []})

        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        data = [dict(zip(cols, row)) for row in rows]

        # Compute quality ratings
        if data:
            mean_th = sum(r.get('T/h', 0) or 0 for r in data) / len(data)
            mean_kwh = sum(r.get('Kwh/T', 0) or 0 for r in data if r.get('Kwh/T'))
            kwh_count = sum(1 for r in data if r.get('Kwh/T'))
            mean_kwh = mean_kwh / kwh_count if kwh_count else 0

            for r in data:
                th = r.get('T/h', 0) or 0
                kwh = r.get('Kwh/T', 0) or 0
                score = 0
                if th >= mean_th: score += 1
                if kwh_count > 0 and kwh <= mean_kwh: score += 1
                r['danh_gia'] = '🟢 Tốt' if score == 2 else ('🟡 TB' if score == 1 else '🔴 Cần cải thiện')

        conn.close()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        conn.close()
        return jsonify({'success': True, 'data': [], 'error': str(e)})


@pellet_bp.route('/api/pellet/capacity-dates', methods=['GET'])
@login_required
def get_capacity_dates():
    """Danh sách ngày có dữ liệu PelletCapacity"""
    conn = db.connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(db._translate_sql("SELECT DISTINCT [Ngày] FROM PelletCapacity WHERE [Đã xóa] = 0 ORDER BY [Ngày] DESC"))
        dates = [r[0] for r in cursor.fetchall()]
        conn.close()
        return jsonify({'success': True, 'dates': dates})
    except Exception as e:
        conn.close()
        return jsonify({'success': True, 'dates': [], 'error': str(e)})


@pellet_bp.route('/api/pellet/upload-capacity', methods=['POST'])
@login_required
def upload_capacity():
    """Upload file vận hành cám viên (PL*.xlsx)"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Không có file'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'success': False, 'message': 'File trống'}), 400

    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as f:
        file.save(f.name)
        temp_path = f.name

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        from utils.pellet_capacity_importer import PelletCapacityImporter
        importer = PelletCapacityImporter(db_path=config.DATABASE_PATH)
        result = importer.import_file(
            temp_path,
            nguoi_import=session.get('username', 'system'),
            overwrite=True,
            original_filename=file.filename   # <-- truyền tên gốc để parse máy
        )

        if result.get('success'):
            return jsonify({
                'success': True,
                'message': f"Import thành công! Máy: {result.get('machine')}, "
                           f"Records: {result.get('imported')}, "
                           f"Đã xóa cũ: {result.get('deleted', 0)}",
                'imported': result.get('imported', 0),
                'not_found': result.get('not_found', [])
            })
        else:
            return jsonify({'success': False, 'message': result.get('error', 'Lỗi')}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass
