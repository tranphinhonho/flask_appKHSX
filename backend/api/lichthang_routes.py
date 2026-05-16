"""
API routes cho module Lịch tháng (LichThang)
Thống kê số record và Kg theo ngày: StockOld / Packing / Sale.
"""
from flask import Blueprint, request, jsonify
from backend.auth import login_required
from backend import db
from backend.utils import get_vietnam_time
import calendar
from datetime import datetime

lichthang_bp = Blueprint('lichthang', __name__)


# Cấu hình 3 nguồn dữ liệu được theo dõi trong lịch tháng
# (table, date_column, key, ma_column)
_SOURCES = [
    ('StockOld', 'Ngày stock old', 'stockold', 'Mã stock old'),
    ('Packing',  'Ngày packing',   'packing',  'Mã packing'),
    ('Sale',     'Ngày sale',      'sale',     'Mã sale'),
]


def _parse_year_month(default_now=True):
    """Lấy year, month từ query, fallback tháng hiện tại (VN)."""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    if (not year or not month) and default_now:
        now = get_vietnam_time()
        year = year or now.year
        month = month or now.month
    return year, month


def _extract_day(date_value):
    """Lấy số ngày (1-31) từ chuỗi 'YYYY-MM-DD' hoặc 'DD/MM/YYYY'. Trả None nếu sai."""
    if not date_value:
        return None
    s = str(date_value).strip()
    try:
        if '-' in s and len(s) >= 10:
            return int(s[8:10])
        if '/' in s:
            return int(s.split('/')[0])
    except Exception:
        return None
    return None


@lichthang_bp.route('/api/lichthang/daily-counts', methods=['GET'])
@login_required
def daily_counts():
    """
    Lấy số record và tổng kg theo từng ngày cho 1 tháng.
    Params: year, month
    """
    year, month = _parse_year_month()
    if not year or not month:
        return jsonify({'success': False, 'message': 'Thiếu year/month'}), 400

    _, last_day = calendar.monthrange(year, month)
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{last_day:02d}"

    # Khởi tạo structure trống cho toàn bộ ngày trong tháng
    by_day = {
        d: {
            'stockold': 0, 'stockold_kg': 0,
            'packing': 0,  'packing_kg': 0,
            'sale': 0,     'sale_kg': 0,
        }
        for d in range(1, last_day + 1)
    }

    conn = db.connect_db()
    cursor = conn.cursor()

    try:
        for table, date_col, key, _ma in _SOURCES:
            cursor.execute(
                f"""SELECT [{date_col}] AS ngay,
                           COUNT(*) AS cnt,
                           COALESCE(SUM(CAST([Số lượng] AS INTEGER)), 0) AS total_kg
                    FROM {table}
                    WHERE [Đã xóa] = 0
                      AND [{date_col}] >= ?
                      AND [{date_col}] <= ?
                    GROUP BY [{date_col}]""",
                (start_date, end_date),
            )
            for row in cursor.fetchall():
                day = _extract_day(row[0])
                if day is None or day not in by_day:
                    continue
                by_day[day][key] += int(row[1] or 0)
                by_day[day][f'{key}_kg'] += int(row[2] or 0)
    finally:
        conn.close()

    data = [{'day': d, **by_day[d]} for d in range(1, last_day + 1)]
    return jsonify({
        'success': True,
        'year': year, 'month': month,
        'days_in_month': last_day,
        'data': data,
    })


@lichthang_bp.route('/api/lichthang/detail', methods=['GET'])
@login_required
def detail():
    """
    Chi tiết các record của 1 ngày theo loại.
    Params: date=YYYY-MM-DD, type=stockold|packing|sale
    """
    selected_date = request.args.get('date')
    data_type = (request.args.get('type') or 'stockold').lower()

    if not selected_date:
        return jsonify({'success': False, 'message': 'Thiếu date'}), 400

    # Validate ngày
    try:
        datetime.strptime(selected_date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'success': False, 'message': 'date phải có dạng YYYY-MM-DD'}), 400

    source = next((s for s in _SOURCES if s[2] == data_type), None)
    if not source:
        return jsonify({'success': False, 'message': 'type không hợp lệ'}), 400

    table, date_col, _key, ma_col = source

    conn = db.connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""SELECT t.ID,
                       sp.[Code cám],
                       sp.[Tên cám],
                       t.[Số lượng],
                       t.[{ma_col}],
                       t.[{date_col}],
                       t.[Ghi chú],
                       t.[Người tạo],
                       t.[Thời gian tạo]
                FROM {table} t
                LEFT JOIN SanPham sp ON CAST(t.[ID sản phẩm] AS INTEGER) = sp.ID
                WHERE t.[Đã xóa] = 0 AND t.[{date_col}] = ?
                ORDER BY t.ID DESC""",
            (selected_date,),
        )
        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        items = [dict(zip(cols, r)) for r in rows]

        total_kg = sum(int(i.get('Số lượng') or 0) for i in items)
    finally:
        conn.close()

    return jsonify({
        'success': True,
        'date': selected_date,
        'type': data_type,
        'data': items,
        'total': len(items),
        'total_kg': total_kg,
    })


@lichthang_bp.route('/api/lichthang/stats', methods=['GET'])
@login_required
def stats():
    """
    Tổng kết tháng: tổng số record, tổng kg, số ngày có dữ liệu.
    Params: year, month
    """
    year, month = _parse_year_month()
    if not year or not month:
        return jsonify({'success': False, 'message': 'Thiếu year/month'}), 400

    _, last_day = calendar.monthrange(year, month)
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{last_day:02d}"

    conn = db.connect_db()
    cursor = conn.cursor()
    totals = {}
    days_set = set()

    try:
        for table, date_col, key, _ma in _SOURCES:
            cursor.execute(
                f"""SELECT COUNT(*), COALESCE(SUM(CAST([Số lượng] AS INTEGER)), 0)
                    FROM {table}
                    WHERE [Đã xóa] = 0
                      AND [{date_col}] >= ? AND [{date_col}] <= ?""",
                (start_date, end_date),
            )
            r = cursor.fetchone()
            totals[f'total_{key}'] = int((r[0] if r else 0) or 0)
            totals[f'total_{key}_kg'] = int((r[1] if r else 0) or 0)

            cursor.execute(
                f"""SELECT DISTINCT [{date_col}] FROM {table}
                    WHERE [Đã xóa] = 0
                      AND [{date_col}] >= ? AND [{date_col}] <= ?""",
                (start_date, end_date),
            )
            for row in cursor.fetchall():
                d = _extract_day(row[0])
                if d is not None:
                    days_set.add(d)
    finally:
        conn.close()

    return jsonify({
        'success': True,
        'year': year, 'month': month,
        'days_in_month': last_day,
        'days_with_data': len(days_set),
        **totals,
    })
