"""
API routes cho module Stock đầu ngày (StockHomNay)
Tính toán tự động, nhập thủ công, danh sách với Aver/DOH/Plan/Day5
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import login_required
from backend import db
from backend.utils import get_vietnam_time
from datetime import datetime, timedelta
import math

stockhomnay_bp = Blueprint('stockhomnay', __name__)

VAT_NUOI_LABELS = {'H': 'HEO', 'G': 'GÀ', 'B': 'BÒ', 'V': 'VỊT', 'C': 'CÚT', 'D': 'DÊ'}
VAT_NUOI_COLORS = {'H': '#FF6B6B', 'G': '#4ECDC4', 'B': '#45B7D1', 'V': '#96CEB4', 'C': '#FFEAA7', 'D': '#DDA0DD'}


@stockhomnay_bp.route('/api/stockhomnay/latest-date', methods=['GET'])
@login_required
def get_latest_date():
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX([Ngày stock]) FROM StockHomNay WHERE [Đã xóa] = 0")
    result = cursor.fetchone()
    conn.close()
    return jsonify({'success': True, 'latest_date': result[0] if result else None})


@stockhomnay_bp.route('/api/stockhomnay/days-in-month', methods=['GET'])
@login_required
def get_days_in_month():
    """Trả về danh sách ngày (1-31) có dữ liệu StockHomNay trong tháng/năm"""
    year  = request.args.get('year',  type=int)
    month = request.args.get('month', type=int)
    if not year or not month:
        now = get_vietnam_time()
        year  = year  or now.year
        month = month or now.month

    month_str = f"{year}-{month:02d}"
    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT CAST([Ngày stock] AS TEXT) as ngay_str
        FROM StockHomNay
        WHERE [Đã xóa] = 0
          AND CAST([Ngày stock] AS TEXT) LIKE ?
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




@stockhomnay_bp.route('/api/stockhomnay', methods=['GET'])
@login_required
def get_list():
    """Danh sách với computed Aver, DOH, Plan, Day5"""
    ngay = request.args.get('ngay')
    vatnuoi = request.args.get('vatnuoi')
    per_page = request.args.get('per_page', 300, type=int)

    conds = ["s.[Đã xóa] = 0"]
    params = []

    if ngay:
        conds.append("s.[Ngày stock] = ?")
        params.append(ngay)
    if vatnuoi and vatnuoi != 'Tất cả':
        conds.append("sp.[Vật nuôi] = ?")
        params.append(vatnuoi)

    where = " AND ".join(conds)
    conn = db.connect_db()
    cursor = conn.cursor()

    cursor.execute(f"SELECT COUNT(*) FROM StockHomNay s LEFT JOIN SanPham sp ON s.[ID sản phẩm] = sp.ID WHERE {where}", params)
    total = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT s.ID, s.[ID sản phẩm], sp.[Code cám], sp.[Tên cám],
               sp.[Vật nuôi], sp.[Batch size],
               s.[Số lượng], s.[Ngày stock], s.[Ghi chú],
               s.[Ghi chú 2], s.[Kết quả GC2],
               s.[Ghi chú 2 A], s.[Kết quả GC2 A],
               s.[Ghi chú 2 B], s.[Kết quả GC2 B],
               s.[Người tạo]
        FROM StockHomNay s
        LEFT JOIN SanPham sp ON s.[ID sản phẩm] = sp.ID
        WHERE {where}
        ORDER BY s.[Kết quả GC2] ASC LIMIT ?
    """, params + [per_page])

    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]

    # Compute Aver, DOH, Plan, Day5
    today = get_vietnam_time().date()
    date_5ago = (today - timedelta(days=5)).strftime('%Y-%m-%d')

    data = []
    pet_order = {'H': 1, 'G': 2, 'V': 3, 'B': 4, 'C': 5, 'D': 6}

    for row in rows:
        d = dict(zip(cols, row))
        id_sp = d['ID sản phẩm']
        stock = d['Số lượng'] or 0
        batch_size = d['Batch size'] or 2800
        kq = d['Kết quả GC2'] or 0

        # Aver
        cursor.execute("""
            SELECT COALESCE(SUM([Số lượng]),0), COUNT(DISTINCT [Ngày sale])
            FROM Sale WHERE [ID sản phẩm] = ? AND [Đã xóa] = 0
        """, (id_sp,))
        sr = cursor.fetchone()
        aver = (sr[0] / sr[1]) if sr[1] > 0 else 0

        # DOH
        doh = round(stock / aver, 1) if aver > 0 else 0

        # Plan = min(Aver*3, |KQ|) rounded up by batch_size, only if DOH<3 & KQ<0
        plan_val = 0
        if doh < 3 and kq < 0 and aver > 0:
            plan_raw = min(aver * 3, abs(kq))
            if plan_raw > 0 and batch_size > 0:
                plan_val = int(math.ceil(plan_raw / batch_size) * batch_size)

        # Day5
        cursor.execute("""
            SELECT COALESCE(SUM([Số lượng]),0) FROM Packing
            WHERE [ID sản phẩm] = ? AND [Đã xóa] = 0 AND [Ngày packing] >= ?
        """, (id_sp, date_5ago))
        day5_pk = cursor.fetchone()[0]
        day5 = min(stock, day5_pk)

        d['Aver'] = int(aver)
        d['DOH'] = doh
        d['Plan'] = plan_val
        d['Day5'] = int(day5)
        d['_pet_order'] = pet_order.get(d.get('Vật nuôi', ''), 99)
        data.append(d)

    conn.close()

    # Sort by pet order then KQ
    data.sort(key=lambda x: (x['_pet_order'], x.get('Kết quả GC2') or 0))
    for d in data:
        del d['_pet_order']

    return jsonify({'success': True, 'data': data, 'total': total})


# ==================== Tính toán tự động ====================

@stockhomnay_bp.route('/api/stockhomnay/calculate', methods=['POST'])
@login_required
def calculate():
    """Stock(N) = StockOld(N-2) + Packing(N-1) - Sale(N-1)"""
    body = request.get_json()
    ngay = body.get('ngay')  # YYYY-MM-DD
    ngay_stock_old = body.get('ngay_stock_old')
    ngay_packing   = body.get('ngay_packing')
    ngay_sale      = body.get('ngay_sale')

    if not ngay:
        return jsonify({'success': False, 'message': 'Thiếu ngày'}), 400

    ngay_dt = datetime.strptime(ngay, '%Y-%m-%d')

    if not ngay_stock_old:
        ngay_stock_old = (ngay_dt - timedelta(days=2)).strftime('%Y-%m-%d')
    if not ngay_packing:
        ngay_packing = (ngay_dt - timedelta(days=1)).strftime('%Y-%m-%d')
    if not ngay_sale:
        ngay_sale = (ngay_dt - timedelta(days=1)).strftime('%Y-%m-%d')

    # GC2 week calculation
    is_saturday = ngay_dt.weekday() == 5
    days_since_sat = (ngay_dt.weekday() + 2) % 7
    if days_since_sat == 0:
        days_since_sat = 7
    sat_B = ngay_dt if is_saturday else ngay_dt - timedelta(days=days_since_sat)
    fri_B = sat_B + timedelta(days=6)
    sat_A = sat_B - timedelta(days=7)
    fri_A = sat_A + timedelta(days=6)

    conn   = db.connect_db()
    cursor = conn.cursor()

    # ---- BATCH queries thay vi loop tung SP ----

    # 1. Danh sach san pham
    cursor.execute("SELECT ID, [Code cám], [Tên cám] FROM SanPham WHERE [Đã xóa] = 0")
    products = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

    # 2. StockOld N-2 (batch)
    cursor.execute(
        "SELECT [ID sản phẩm], COALESCE(SUM([Số lượng]),0) FROM StockOld "
        "WHERE [Đã xóa]=0 AND [Ngày stock old]=? GROUP BY [ID sản phẩm]",
        (ngay_stock_old,)
    )
    so_map = {int(row[0]): row[1] for row in cursor.fetchall()}

    # 3. Packing N-1 (batch)
    cursor.execute(
        "SELECT [ID sản phẩm], COALESCE(SUM([Số lượng]),0) FROM Packing "
        "WHERE [Đã xóa]=0 AND [Ngày packing]=? GROUP BY [ID sản phẩm]",
        (ngay_packing,)
    )
    pk_map = {int(row[0]): row[1] for row in cursor.fetchall()}

    # 4. Sale N-1 (batch)
    cursor.execute(
        "SELECT [ID sản phẩm], COALESCE(SUM([Số lượng]),0) FROM Sale "
        "WHERE [Đã xóa]=0 AND [Ngày sale]=? GROUP BY [ID sản phẩm]",
        (ngay_sale,)
    )
    sl_map = {int(row[0]): row[1] for row in cursor.fetchall()}

    # 5. GC2 Week B - StockHomNay T7
    cursor.execute(
        "SELECT [ID sản phẩm], COALESCE(SUM([Số lượng]),0) FROM StockHomNay "
        "WHERE [Đã xóa]=0 AND [Ngày stock]=? GROUP BY [ID sản phẩm]",
        (sat_B.strftime('%Y-%m-%d'),)
    )
    st_B_map = {int(row[0]): row[1] for row in cursor.fetchall()}

    # 6. GC2 Week B - Mixer Batching
    cursor.execute(
        "SELECT [ID sản phẩm], COALESCE(SUM([Số lượng thực tế]),0) FROM Mixer "
        "WHERE [Đã xóa]=0 AND [Ngày trộn]>=? AND [Ngày trộn]<=? GROUP BY [ID sản phẩm]",
        (sat_B.strftime('%Y-%m-%d'), fri_B.strftime('%Y-%m-%d'))
    )
    bat_B_map = {int(row[0]): row[1] for row in cursor.fetchall()}

    # 7. GC2 Week B - Forecast
    cursor.execute(
        "SELECT [ID sản phẩm], COALESCE(SUM([Số lượng]),0) FROM DatHang "
        "WHERE [Đã xóa]=0 AND [Loại đặt hàng]='Forecast hàng tuần' "
        "AND [Ngày đặt]>=? AND [Ngày đặt]<=? GROUP BY [ID sản phẩm]",
        (sat_B.strftime('%Y-%m-%d'), fri_B.strftime('%Y-%m-%d'))
    )
    fc_B_map = {int(row[0]): row[1] for row in cursor.fetchall()}

    # 8. GC2 Week B - KVL
    cursor.execute(
        "SELECT [ID sản phẩm], COALESCE(SUM([Số lượng]),0) FROM DatHang "
        "WHERE [Đã xóa]=0 AND [Loại đặt hàng]='Khách vãng lai' "
        "AND [Ngày lấy]>=? AND [Ngày lấy]<=? GROUP BY [ID sản phẩm]",
        (sat_B.strftime('%Y-%m-%d'), fri_B.strftime('%Y-%m-%d'))
    )
    kvl_B_map = {int(row[0]): row[1] for row in cursor.fetchall()}

    # 9. GC2 Week A (chỉ cần khi is_saturday)
    st_A_map = bat_A_map = fc_A_map = kvl_A_map = {}
    if is_saturday:
        cursor.execute(
            "SELECT [ID sản phẩm], COALESCE(SUM([Số lượng]),0) FROM StockHomNay "
            "WHERE [Đã xóa]=0 AND [Ngày stock]=? GROUP BY [ID sản phẩm]",
            (sat_A.strftime('%Y-%m-%d'),)
        )
        st_A_map = {int(row[0]): row[1] for row in cursor.fetchall()}

        cursor.execute(
            "SELECT [ID sản phẩm], COALESCE(SUM([Số lượng thực tế]),0) FROM Mixer "
            "WHERE [Đã xóa]=0 AND [Ngày trộn]>=? AND [Ngày trộn]<=? GROUP BY [ID sản phẩm]",
            (sat_A.strftime('%Y-%m-%d'), fri_A.strftime('%Y-%m-%d'))
        )
        bat_A_map = {int(row[0]): row[1] for row in cursor.fetchall()}

        cursor.execute(
            "SELECT [ID sản phẩm], COALESCE(SUM([Số lượng]),0) FROM DatHang "
            "WHERE [Đã xóa]=0 AND [Loại đặt hàng]='Forecast hàng tuần' "
            "AND [Ngày đặt]>=? AND [Ngày đặt]<=? GROUP BY [ID sản phẩm]",
            (sat_A.strftime('%Y-%m-%d'), fri_A.strftime('%Y-%m-%d'))
        )
        fc_A_map = {int(row[0]): row[1] for row in cursor.fetchall()}

        cursor.execute(
            "SELECT [ID sản phẩm], COALESCE(SUM([Số lượng]),0) FROM DatHang "
            "WHERE [Đã xóa]=0 AND [Loại đặt hàng]='Khách vãng lai' "
            "AND [Ngày lấy]>=? AND [Ngày lấy]<=? GROUP BY [ID sản phẩm]",
            (sat_A.strftime('%Y-%m-%d'), fri_A.strftime('%Y-%m-%d'))
        )
        kvl_A_map = {int(row[0]): row[1] for row in cursor.fetchall()}

    conn.close()

    # ---- Tinh toan tung SP tu cac map ----
    results = []
    for id_sp, (code, ten) in products.items():
        so    = so_map.get(id_sp, 0)
        pk    = pk_map.get(id_sp, 0)
        sl    = sl_map.get(id_sp, 0)
        stock = so + pk - sl
        if stock <= 0:
            continue

        st_B  = st_B_map.get(id_sp, 0)
        bat_B = bat_B_map.get(id_sp, 0)
        fc_B  = fc_B_map.get(id_sp, 0)
        kvl_B = kvl_B_map.get(id_sp, 0)
        gc2_B = st_B + bat_B - (fc_B + kvl_B)

        gc2_A      = 0
        gc2_text_A = ''
        if is_saturday:
            st_A  = st_A_map.get(id_sp, 0)
            bat_A = bat_A_map.get(id_sp, 0)
            fc_A  = fc_A_map.get(id_sp, 0)
            kvl_A = kvl_A_map.get(id_sp, 0)
            gc2_A      = st_A + bat_A - (fc_A + kvl_A)
            gc2_text_A = f"T7({st_A:,.0f})+Bat({bat_A:,.0f})-FC({fc_A:,.0f})-KVL({kvl_A:,.0f})={gc2_A:,.0f}"

        results.append({
            'id_sanpham': id_sp, 'code': code, 'ten': ten,
            'stock_old': so, 'packing': pk, 'sale': sl, 'stock': stock,
            'gc2_B': gc2_B,
            'gc2_text_B': f"T7({st_B:,.0f})+Bat({bat_B:,.0f})-FC({fc_B:,.0f})-KVL({kvl_B:,.0f})={gc2_B:,.0f}",
            'gc2_A': gc2_A, 'gc2_text_A': gc2_text_A
        })

    return jsonify({
        'success': True, 'count': len(results), 'results': results,
        'ngay': ngay, 'is_saturday': is_saturday,
        'formula': f"StockOld({ngay_stock_old}) + Packing({ngay_packing}) - Sale({ngay_sale})"
    })


@stockhomnay_bp.route('/api/stockhomnay/save-calculated', methods=['POST'])
@login_required
def save_calculated():
    """Lưu kết quả tính toán"""
    body = request.get_json()
    results = body.get('results', [])
    ngay = body.get('ngay')

    if not results or not ngay:
        return jsonify({'success': False, 'message': 'Thiếu dữ liệu'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()

    # Soft delete old data for this date
    cursor.execute("UPDATE StockHomNay SET [Đã xóa] = 1 WHERE [Đã xóa] = 0 AND [Ngày stock] = ?", (ngay,))

    # Gen code
    cursor.execute("SELECT MAX([Mã stock]) FROM StockHomNay WHERE [Mã stock] LIKE 'ST%'")
    r = cursor.fetchone()[0]
    next_num = int(r[2:]) + 1 if r else 1
    ma = f"ST{next_num:05d}"

    saved = 0
    for item in results:
        cursor.execute("""
            INSERT INTO StockHomNay
            ([ID sản phẩm], [Mã stock], [Số lượng], [Ngày stock],
             [Ghi chú], [Ghi chú 2], [Kết quả GC2],
             [Ghi chú 2 A], [Kết quả GC2 A], [Ghi chú 2 B], [Kết quả GC2 B],
             [Người tạo], [Thời gian tạo], [Đã xóa])
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            item['id_sanpham'], ma, item['stock'], ngay,
            f"SO({item['stock_old']}) + Pk({item['packing']}) - Sale({item['sale']})",
            item.get('gc2_text_B', ''), item.get('gc2_B', 0),
            item.get('gc2_text_A', ''), item.get('gc2_A', 0),
            item.get('gc2_text_B', ''), item.get('gc2_B', 0),
            username, now
        ))
        saved += 1

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Đã lưu {saved} SP (Mã: {ma})', 'ma': ma, 'count': saved})


# ==================== Manual ====================

@stockhomnay_bp.route('/api/stockhomnay/create', methods=['POST'])
@login_required
def create():
    data = request.get_json()
    items = data.get('items', [])
    if not items:
        return jsonify({'success': False, 'message': 'Không có dữ liệu'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')
    ngay = get_vietnam_time().strftime('%Y-%m-%d')

    conn = db.connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT MAX([Mã stock]) FROM StockHomNay WHERE [Mã stock] LIKE 'ST%'")
    r = cursor.fetchone()[0]
    next_num = int(r[2:]) + 1 if r else 1
    ma = f"ST{next_num:05d}"

    saved = 0
    for item in items:
        cursor.execute("""
            INSERT INTO StockHomNay
            ([ID sản phẩm], [Mã stock], [Số lượng], [Ngày stock],
             [Ghi chú], [Người tạo], [Thời gian tạo], [Đã xóa])
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (item.get('id_sanpham'), ma, int(item.get('so_luong', 0)),
              item.get('ngay_stock', ngay), item.get('ghi_chu', ''), username, now))
        saved += 1

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Đã lưu {saved} dòng (Mã: {ma})', 'ma': ma})


@stockhomnay_bp.route('/api/stockhomnay/delete', methods=['POST'])
@login_required
def delete():
    data = request.get_json()
    item_id = data.get('id')
    if not item_id:
        return jsonify({'success': False, 'message': 'Thiếu ID'}), 400

    username = session.get('username', 'system')
    now = get_vietnam_time().strftime('%Y-%m-%d %H:%M:%S')

    conn = db.connect_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE StockHomNay SET [Đã xóa]=1, [Người sửa]=?, [Thời gian sửa]=? WHERE ID=?", (username, now, item_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Đã xóa'})
