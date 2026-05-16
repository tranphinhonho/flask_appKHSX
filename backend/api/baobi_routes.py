"""
API routes cho module Bao bì (BaoBi)
Quản lý tồn kho bao bì: BagStock từ email, cảnh báo, cập nhật thủ công, lịch sử
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import login_required
from backend import db
from backend.utils import get_vietnam_time
import os
import sys

baobi_bp = Blueprint('baobi', __name__)

BAG_SIZES = [50, 40, 25, 20, 10, 5]
LOAI_BAO = ['Bao PP', 'Bao PE', 'Bao Kraft', 'Bao Jumbo']
VAT_NUOI_LABELS = {'H': 'HEO', 'G': 'GÀ', 'B': 'BÒ', 'V': 'VỊT', 'C': 'CÚT', 'D': 'DÊ'}
VAT_NUOI_COLORS = {'H': '#FF6B6B', 'G': '#4ECDC4', 'B': '#45B7D1', 'V': '#96CEB4', 'C': '#FFEAA7', 'D': '#DDA0DD'}


def _xac_dinh_muc_canh_bao(ton_kho, nhu_cau):
    chenh_lech = ton_kho - nhu_cau
    if chenh_lech < 0:
        return "Mức 1 🚨 Thiếu hàng"
    elif ton_kho <= 500:
        return "Mức 2 ⚠️ Tồn kho thấp"
    elif ton_kho <= 2000:
        return "Mức 3 🟡 Tồn kho trung bình"
    else:
        return "Mức 4 ✅ An toàn"


# ==================== BagStock từ Email ====================

@baobi_bp.route('/api/baobi/bagstock', methods=['GET'])
@login_required
def get_bagstock():
    """Lấy dữ liệu BagStock (từ BAG REPORT import) - hỗ trợ lọc theo vật nuôi"""
    ngay = request.args.get('ngay')
    search = request.args.get('search', '')
    vatnuoi = request.args.get('vatnuoi', '')

    conn = db.connect_db()
    cursor = conn.cursor()

    try:
        # Base query with LEFT JOIN to SanPham to get VatNuoi
        # Note: BagStock.TenCam = SanPham.[Tên cám] (not Code cám)
        # Use bracket-quoted columns for proper PostgreSQL translation
        base_sql = """
            SELECT b.[TenCam] as ten_cam, b.[KichCoDongBao] as kich_co,
                   b.[SoLuongBaoBi] as so_luong, b.[NgayStock] as ngay_stock,
                   b.[TenFile] as ten_file, b.[ThoiGianTao] as thoi_gian,
                   sp.[Vật nuôi] as vat_nuoi
            FROM BagStock b
            LEFT JOIN SanPham sp ON TRIM(b.[TenCam]) = TRIM(sp.[Tên cám]) AND sp.[Đã xóa] = 0
            WHERE b.[NgayStock] = ? AND b.[DaXoa] = 0
        """
        params = [ngay]

        if search:
            base_sql += " AND b.[TenCam] LIKE ?"
            params.append(f"%{search}%")

        if vatnuoi and vatnuoi != 'Tất cả':
            base_sql += " AND sp.[Vật nuôi] = ?"
            params.append(vatnuoi)

        base_sql += " ORDER BY b.[TenCam]"

        cursor.execute(base_sql, params)

        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        data = [dict(zip(cols, row)) for row in rows]

        # Stats
        total_bao = sum(int(r.get('so_luong', 0) or 0) for r in data)
        kich_co_set = set(r.get('kich_co', '') for r in data)

        conn.close()
        return jsonify({
            'success': True,
            'data': data,
            'total': len(data),
            'total_bao': total_bao,
            'so_kich_co': len(kich_co_set)
        })
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@baobi_bp.route('/api/baobi/bagstock/latest-date', methods=['GET'])
@login_required
def get_bagstock_latest():
    """Get latest date in BagStock"""
    conn = db.connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT MAX(NgayStock) FROM BagStock WHERE DaXoa = 0")
        result = cursor.fetchone()
        conn.close()
        return jsonify({'success': True, 'latest_date': result[0] if result else None})
    except:
        conn.close()
        return jsonify({'success': True, 'latest_date': None})


# ==================== Cảnh báo tồn kho ====================

@baobi_bp.route('/api/baobi/canh-bao', methods=['GET'])
@login_required
def kiem_tra_canh_bao():
    """Kiểm tra tồn kho bao bì vs nhu cầu packing"""
    ngay = request.args.get('ngay')
    if not ngay:
        return jsonify({'success': False, 'message': 'Thiếu ngày'}), 400

    conn = db.connect_db()
    cursor = conn.cursor()

    # Get BagStock data (latest date <= ngay)
    try:
        cursor.execute("""
            SELECT KichCoDongBao, SUM(CAST(SoLuongBaoBi AS INTEGER)) as tong
            FROM BagStock WHERE NgayStock <= ? AND DaXoa = 0
            GROUP BY KichCoDongBao, NgayStock
            HAVING NgayStock = (SELECT MAX(NgayStock) FROM BagStock WHERE NgayStock <= ? AND DaXoa = 0)
        """, (ngay, ngay))
        stock_rows = cursor.fetchall()
    except:
        stock_rows = []

    stock_dict = {}
    for row in stock_rows:
        stock_dict[row[0]] = row[1]

    # Get PackingPlan needs
    try:
        cursor.execute("""
            SELECT [Kích cỡ bao (kg)], SUM(CAST([Số bao] AS INTEGER)) as tong
            FROM PackingPlan WHERE [Ngày đóng bao] >= ? AND [Đã xóa] = 0
            GROUP BY [Kích cỡ bao (kg)]
        """, (ngay,))
        packing_rows = cursor.fetchall()
    except:
        packing_rows = []

    packing_dict = {}
    for row in packing_rows:
        if row[0]:
            packing_dict[str(int(float(row[0])))] = int(row[1])

    conn.close()

    # Build comparison result
    all_sizes = set(list(stock_dict.keys()) + list(packing_dict.keys()))
    results = []
    muc_counts = {'muc_1': 0, 'muc_2': 0, 'muc_3': 0, 'muc_4': 0}

    for size in sorted(all_sizes):
        ton_kho = int(stock_dict.get(size, 0))
        nhu_cau = int(packing_dict.get(str(size).split('.')[0], 0))
        thieu = max(0, nhu_cau - ton_kho)
        muc = _xac_dinh_muc_canh_bao(ton_kho, nhu_cau)

        if 'Mức 1' in muc: muc_counts['muc_1'] += 1
        elif 'Mức 2' in muc: muc_counts['muc_2'] += 1
        elif 'Mức 3' in muc: muc_counts['muc_3'] += 1
        elif 'Mức 4' in muc: muc_counts['muc_4'] += 1

        results.append({
            'kich_co': size,
            'ton_kho': ton_kho,
            'nhu_cau': nhu_cau,
            'thieu': thieu,
            'muc_canh_bao': muc
        })

    return jsonify({
        'success': True,
        'data': results,
        'muc_counts': muc_counts
    })


@baobi_bp.route('/api/baobi/nhu-cau-packing', methods=['GET'])
@login_required
def tinh_nhu_cau():
    """Tính nhu cầu bao bì từ Packing Plan"""
    ngay = request.args.get('ngay')

    conn = db.connect_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT [Kích cỡ bao (kg)], SUM(CAST([Số bao] AS INTEGER)) as tong
            FROM PackingPlan WHERE [Ngày đóng bao] = ? AND [Đã xóa] = 0
            GROUP BY [Kích cỡ bao (kg)]
        """, (ngay,))
        rows = cursor.fetchall()
    except:
        rows = []

    conn.close()

    nhu_cau = {}
    for row in rows:
        if row[0]:
            nhu_cau[f"Bao {int(float(row[0]))}kg"] = int(row[1])

    return jsonify({'success': True, 'nhu_cau': nhu_cau})


# ==================== Cập nhật / Lưu thủ công ====================

@baobi_bp.route('/api/baobi/save', methods=['POST'])
@login_required
def save_baobi():
    """Lưu tồn kho bao bì (nhập thủ công)"""
    data = request.get_json()
    items = data.get('items', [])
    ngay = data.get('ngay')

    if not items:
        return jsonify({'success': False, 'message': 'Không có dữ liệu'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()
    saved = 0

    try:
        for item in items:
            ton_kho = int(item.get('ton_kho', 0))
            nhu_cau = int(item.get('nhu_cau', 0))
            thieu = max(0, nhu_cau - ton_kho)
            muc = _xac_dinh_muc_canh_bao(ton_kho, nhu_cau)

            cursor.execute("""
                INSERT INTO BaoBi
                ([Ngày kiểm tra], [Loại bao], [Kích cỡ (kg)],
                 [Tồn kho hiện tại], [Nhu cầu dự kiến], [Số lượng thiếu],
                 [Mức cảnh báo], [Ghi chú], [Người tạo], [Thời gian tạo], [Đã xóa])
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (ngay, item.get('loai_bao', 'Bao PP'), item.get('kich_co', 50),
                  ton_kho, nhu_cau, thieu, muc,
                  item.get('ghi_chu', ''), username, now))
            saved += 1

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Đã lưu {saved} dòng', 'count': saved})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 400


# ==================== Lịch sử ====================

@baobi_bp.route('/api/baobi/history', methods=['GET'])
@login_required
def get_baobi_history():
    """Lấy lịch sử tồn kho bao bì"""
    per_page = request.args.get('per_page', 100, type=int)

    conn = db.connect_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT ID, [Ngày kiểm tra], [Loại bao], [Kích cỡ (kg)],
                   [Tồn kho hiện tại], [Nhu cầu dự kiến], [Mức cảnh báo],
                   [Số lượng thiếu], [Ghi chú], [Người tạo], [Thời gian tạo]
            FROM BaoBi WHERE [Đã xóa] = 0
            ORDER BY ID DESC
            LIMIT ?
        """, (per_page,))

        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        data = [dict(zip(cols, row)) for row in rows]

        conn.close()
        return jsonify({'success': True, 'data': data, 'total': len(data)})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@baobi_bp.route('/api/baobi/delete', methods=['POST'])
@login_required
def delete_baobi():
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
        "UPDATE BaoBi SET [Đã xóa] = 1, [Người sửa] = ?, [Thời gian sửa] = ? WHERE ID = ?",
        (username, now, item_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đã xóa'})
