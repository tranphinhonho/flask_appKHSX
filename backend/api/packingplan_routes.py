"""
API routes cho module Packing Plan
Kế hoạch đóng bao: tạo từ Pellet, nhập thủ công, danh sách
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import login_required
from backend import db
from backend.utils import get_vietnam_time
from datetime import datetime, timedelta

packingplan_bp = Blueprint('packingplan', __name__)

# Pellet → Packing line mapping
PACKING_MAPPING = {
    'Cám bột': 'Packing 3',
    'Pellet 1': 'Packing 5',
    'Pellet 2': 'Packing 1',
    'Pellet 3': 'Packing 2',
    'Pellet 4': 'Packing 4',
    'Pellet 5': 'Packing 6',
    'Pellet 6': 'Packing 7',
    'Pellet 7': 'Packing 8'
}

BAG_SIZES = [50, 40, 25, 20, 10, 5]


# ==================== Danh sách ====================

@packingplan_bp.route('/api/packingplan', methods=['GET'])
@login_required
def get_packingplan_list():
    """Lấy danh sách kế hoạch đóng bao"""
    ngay = request.args.get('ngay')
    line = request.args.get('line')
    per_page = request.args.get('per_page', 200, type=int)

    conn = db.connect_db()
    cursor = conn.cursor()

    conditions = ["p.[Đã xóa] = 0"]
    params = []

    if ngay:
        conditions.append("p.[Ngày đóng bao] = ?")
        params.append(ngay)
    if line and line != 'Tất cả':
        conditions.append("p.[Line đóng bao] = ?")
        params.append(line)

    where = " AND ".join(conditions)

    cursor.execute(f"SELECT COUNT(*) FROM PackingPlan p WHERE {where}", params)
    total = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT p.ID, p.[Ngày đóng bao], p.[ID sản phẩm],
               sp.[Code cám], sp.[Tên cám],
               p.[Số lượng (tấn)], p.[Kích cỡ bao (kg)], p.[Số bao],
               p.[Line đóng bao], p.[Thời gian bắt đầu], p.[Thời gian kết thúc],
               p.[Ghi chú], p.[Người tạo], p.[Thời gian tạo]
        FROM PackingPlan p
        LEFT JOIN SanPham sp ON p.[ID sản phẩm] = sp.ID
        WHERE {where}
        ORDER BY p.[Ngày đóng bao] DESC, p.ID DESC
        LIMIT ?
    """, params + [per_page])

    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    data = [dict(zip(cols, row)) for row in rows]

    conn.close()
    return jsonify({'success': True, 'data': data, 'total': total})


@packingplan_bp.route('/api/packingplan/latest-date', methods=['GET'])
@login_required
def get_latest_date():
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX([Ngày đóng bao]) FROM PackingPlan WHERE [Đã xóa] = 0")
    result = cursor.fetchone()
    conn.close()
    return jsonify({'success': True, 'latest_date': result[0] if result else None})


# ==================== Tạo từ Pellet ====================

@packingplan_bp.route('/api/packingplan/generate', methods=['POST'])
@login_required
def generate_from_pellet():
    """Tạo kế hoạch đóng bao từ dữ liệu Pellet"""
    data = request.get_json()
    ngay = data.get('ngay')

    if not ngay:
        return jsonify({'success': False, 'message': 'Thiếu ngày'}), 400

    conn = db.connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT p.ID, p.[Ngày sản xuất], p.[ID sản phẩm],
               sp.[Tên cám], p.[Số lượng], p.[Số máy],
               sp.[Kích cỡ ép viên]
        FROM Pellet p
        LEFT JOIN SanPham sp ON p.[ID sản phẩm] = sp.ID
        WHERE p.[Ngày sản xuất] = ? AND p.[Đã xóa] = 0
        ORDER BY p.[Số máy]
    """, (ngay,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return jsonify({'success': False, 'message': 'Không có dữ liệu Pellet cho ngày này'})

    ke_hoach = []
    for row in rows:
        pellet_id, ngay_sx, id_sp, ten_cam, so_luong, so_may, kich_co_viên = row
        line_packing = PACKING_MAPPING.get(so_may, 'Packing 1')
        kich_co_bao = 50  # Default
        so_bao = int((so_luong * 1000) / kich_co_bao) if so_luong else 0

        ke_hoach.append({
            'id_pellet': pellet_id,
            'id_sanpham': id_sp,
            'ten_cam': ten_cam or '',
            'so_luong_tan': so_luong or 0,
            'so_may': so_may or '',
            'kich_co_bao': kich_co_bao,
            'so_bao': so_bao,
            'line_packing': line_packing
        })

    tong_sl = sum(i['so_luong_tan'] for i in ke_hoach)
    tong_bao = sum(i['so_bao'] for i in ke_hoach)
    lines_used = len(set(i['line_packing'] for i in ke_hoach))

    return jsonify({
        'success': True,
        'ke_hoach': ke_hoach,
        'tong_san_luong': round(tong_sl, 1),
        'tong_so_bao': tong_bao,
        'lines_used': lines_used
    })


@packingplan_bp.route('/api/packingplan/save-generated', methods=['POST'])
@login_required
def save_generated():
    """Lưu kế hoạch đã tạo từ Pellet"""
    data = request.get_json()
    ke_hoach = data.get('ke_hoach', [])
    ngay = data.get('ngay')

    if not ke_hoach or not ngay:
        return jsonify({'success': False, 'message': 'Thiếu dữ liệu'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()
    saved = 0

    try:
        start_time = datetime.strptime(ngay, '%Y-%m-%d').replace(hour=8)

        for item in ke_hoach:
            end_time = start_time + timedelta(hours=2)

            cursor.execute("""
                INSERT INTO PackingPlan
                ([Ngày đóng bao], [ID sản phẩm], [Số lượng (tấn)],
                 [Kích cỡ bao (kg)], [Số bao], [Line đóng bao],
                 [Thời gian bắt đầu], [Thời gian kết thúc],
                 [Ghi chú], [Người tạo], [Thời gian tạo], [Đã xóa])
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (ngay, item.get('id_sanpham'), item.get('so_luong_tan', 0),
                  item.get('kich_co_bao', 50), item.get('so_bao', 0),
                  item.get('line_packing', ''),
                  start_time.strftime('%Y-%m-%d %H:%M:%S'),
                  end_time.strftime('%Y-%m-%d %H:%M:%S'),
                  '', username, now))
            saved += 1

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Đã lưu {saved} dòng', 'count': saved})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 400


# ==================== Nhập thủ công ====================

@packingplan_bp.route('/api/packingplan/create', methods=['POST'])
@login_required
def create_packingplan():
    """Nhập thủ công"""
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
            so_luong = float(item.get('so_luong_tan', 0))
            kich_co = int(item.get('kich_co_bao', 50))
            so_bao = int((so_luong * 1000) / kich_co) if kich_co > 0 else 0

            cursor.execute("""
                INSERT INTO PackingPlan
                ([Ngày đóng bao], [ID sản phẩm], [Số lượng (tấn)],
                 [Kích cỡ bao (kg)], [Số bao], [Line đóng bao],
                 [Ghi chú], [Người tạo], [Thời gian tạo], [Đã xóa])
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (item.get('ngay'), item.get('id_sanpham'),
                  so_luong, kich_co, so_bao,
                  item.get('line', 'Packing 1'),
                  item.get('ghi_chu', ''), username, now))
            saved += 1

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Đã lưu {saved} dòng', 'count': saved})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 400


@packingplan_bp.route('/api/packingplan/delete', methods=['POST'])
@login_required
def delete_packingplan():
    """Soft delete"""
    data = request.get_json()
    item_id = data.get('id')
    if not item_id:
        return jsonify({'success': False, 'message': 'Thiếu ID'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE PackingPlan SET [Đã xóa] = 1, [Người sửa] = ?, [Thời gian sửa] = ? WHERE ID = ?",
        (username, now, item_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đã xóa'})
