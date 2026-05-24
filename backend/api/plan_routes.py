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

CONG_SUAT_TOI_DA = 2500000  # Max: 2500 Tons
CONG_SUAT_TOI_THIEU = 2100000  # Min: 2100 Tons
CONG_SUAT_CHO_PHEP = CONG_SUAT_TOI_DA * 1.05
MAX_SAN_PHAM = 35  # Max products updated to 35 to fit 35-item output


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
        'cong_suat': CONG_SUAT_TOI_DA,
        'cong_suat_min': CONG_SUAT_TOI_THIEU
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
    only_saved = data.get('only_saved', False)

    if not ngay:
        return jsonify({'success': False, 'message': 'Thiếu ngày'}), 400

    try:
        ngay_dt = datetime.strptime(ngay, '%Y-%m-%d')
    except Exception as e:
        return jsonify({'success': False, 'message': f'Ngày không hợp lệ: {e}'}), 400

    # Skip Sunday
    if skip_sunday:
        while ngay_dt.weekday() == 6:
            ngay_dt += timedelta(days=1)

    ngay_str     = ngay_dt.strftime('%Y-%m-%d')
    ngay_alt     = ngay_dt.strftime('%d/%m/%Y')
    ngay_lay     = (ngay_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    ngay_lay_alt = (ngay_dt + timedelta(days=1)).strftime('%d/%m/%Y')

    # Check if StockHomNay has data, fallback to StockOld (where FFStock is loaded)
    conn = db.connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(db.sql("SELECT COUNT(*) FROM [StockHomNay] WHERE [Đã xóa] = 0"))
        has_today_stock = cursor.fetchone()[0] > 0
    except Exception:
        has_today_stock = False
    finally:
        conn.close()

    if has_today_stock:
        SH_LATEST = """(
            SELECT sh2.[ID sản phẩm], MAX(sh2.[Số lượng]) as [Số lượng]
            FROM StockHomNay sh2
            WHERE sh2.[Đã xóa] = 0
              AND sh2.[Ngày stock] = (
                  SELECT MAX(sh3.[Ngày stock]) FROM StockHomNay sh3
                  WHERE sh3.[ID sản phẩm] = sh2.[ID sản phẩm] AND sh3.[Đã xóa] = 0
              )
            GROUP BY sh2.[ID sản phẩm]
        )"""
    else:
        SH_LATEST = """(
            SELECT so2.[ID sản phẩm], MAX(so2.[Số lượng]) as [Số lượng]
            FROM StockOld so2
            WHERE so2.[Đã xóa] = 0
              AND so2.[Ngày stock old] = (
                  SELECT MAX(so3.[Ngày stock old]) FROM StockOld so3
                  WHERE so3.[ID sản phẩm] = so2.[ID sản phẩm] AND so3.[Đã xóa] = 0
              )
            GROUP BY so2.[ID sản phẩm]
        )"""

    conn   = db.connect_db()
    cursor = conn.cursor()

    try:
        # Check manual plan first
        cursor.execute(f"""
            SELECT p.[ID sản phẩm], sp.[Code cám], sp.[Tên cám], p.[Số lượng],
                   p.[Ghi chú], p.[Mã plan], COALESCE(sh.[Số lượng], 0) as stock
            FROM Plan p
            JOIN SanPham sp ON p.[ID sản phẩm] = sp.ID
            LEFT JOIN {SH_LATEST} sh ON sp.ID = sh.[ID sản phẩm]
            WHERE (p.[Ngày plan] = ? OR p.[Ngày plan] = ?) AND p.[Đã xóa] = 0
            ORDER BY p.ID ASC
        """, (ngay_str, ngay_alt))

        manual_plans = cursor.fetchall()

        if manual_plans:
            danh_sach = []
            tong      = 0
            ma_plans  = set()
            for row in manual_plans:
                id_sp, code, ten, sl, gc, ma, stock = row
                sl = float(sl or 0)
                stock = float(stock or 0)
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
                'success': True, 'loai': 'manual', 'has_saved': True,
                'ngay': ngay_str, 'ngay_display': ngay_dt.strftime('%d/%m/%Y'),
                'danh_sach': danh_sach, 'tong': tong, 'ty_le': ty_le,
                'so_sp': len(danh_sach), 'ma_plan': ', '.join(ma_plans)
            })

        if only_saved:
            conn.close()
            return jsonify({
                'success': False,
                'has_saved': False,
                'message': 'Chưa có kế hoạch được lưu cho ngày này. Vui lòng bấm nút "Tính toán" màu đỏ để tạo kế hoạch tự động.'
            })

        # Auto calculate - Run original Excel-to-Web algorithm via khsx_json.py subprocess
        import subprocess
        import json
        import sys
        
        python_exe = sys.executable
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(backend_dir, "algorithm", "khsx_json.py")
        
        try:
            res = subprocess.run([python_exe, script_path, ngay_str], 
                                 capture_output=True, text=True, encoding='utf-8', errors='replace')
            stdout_str = res.stdout
            
            if "---JSON_START---" in stdout_str:
                json_part = stdout_str.split("---JSON_START---")[-1].strip()
                res_data = json.loads(json_part)
                
                if not res_data.get('success'):
                    conn.close()
                    return jsonify({'success': False, 'message': res_data.get('message', 'Lỗi tính toán')}), 400
                
                raw_danh_sach = res_data.get('danh_sach', [])
                
                # Fetch product mapping from DB
                cursor.execute("SELECT ID, [Code cám], [Tên cám] FROM SanPham WHERE [Đã xóa] = 0")
                products_db = cursor.fetchall()
                prod_map = {}
                for pid, code, name in products_db:
                    if code:
                        prod_map[str(code).strip().upper()] = pid
                    if name:
                        prod_map[str(name).strip().upper()] = pid
                        
                # Map codes to ID sản phẩm
                ke_hoach = []
                tong = 0
                for item in raw_danh_sach:
                    code_upper = str(item['code']).strip().upper()
                    pid = prod_map.get(code_upper)
                    if not pid:
                        # Fallback prefix/suffix matching
                        for c, p_id in prod_map.items():
                            if c.startswith(code_upper) or code_upper.startswith(c):
                                pid = p_id
                                break
                                
                    if pid:
                        item['id_sanpham'] = pid
                        ke_hoach.append(item)
                        tong += item['so_luong']
                    else:
                        item['id_sanpham'] = None
                        ke_hoach.append(item)
                        tong += item['so_luong']
                        
                conn.close()
                
                ty_le = round(tong / CONG_SUAT_TOI_DA * 100, 1)
                return jsonify({
                    'success': True,
                    'loai': 'auto',
                    'ngay': ngay_str,
                    'ngay_display': ngay_dt.strftime('%d/%m/%Y'),
                    'danh_sach': ke_hoach,
                    'tong': tong,
                    'ty_le': ty_le,
                    'so_sp': len(ke_hoach),
                    'warnings': res_data.get('warnings', [])
                })
            else:
                conn.close()
                return jsonify({'success': False, 'message': f'Subprocess didn\'t print expected delimiter. Stdout: {stdout_str[:500]}'}), 500
        except Exception as ex:
            conn.close()
            return jsonify({'success': False, 'message': f'Lỗi gọi subprocess thuật toán: {ex}'}), 500
    except Exception as e:
        try: conn.close()
        except: pass
        return jsonify({'success': False, 'message': f'Lỗi tính toán: {str(e)}'}), 500


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
