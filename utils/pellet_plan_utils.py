"""
Pellet Plan Utilities
Tạo layout bảng PLAN PELLET MILL giống Excel
Với 7 máy (PL1-PL7) x 3 ca (CA1, CA2, CA3)
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# Default công suất máy (tấn/giờ)
DEFAULT_MACHINES = {
    'PL1': {'capacity': 10, 'die': '65-20'},
    'PL2': {'capacity': 10, 'die': '75-00'},
    'PL3': {'capacity': 9, 'die': '75-15'},
    'PL4': {'capacity': 9, 'die': '75-25'},
    'PL5': {'capacity': 8, 'die': '65-25'},
    'PL6': {'capacity': 8, 'die': '55-10'},
    'PL7': {'capacity': 8, 'die': '55-15'}
}

# Số giờ mỗi ca
HOURS_PER_SHIFT = 8
SHIFTS = ['CA 1', 'CA 2', 'CA 3']

def get_plan_data_for_date(ngay_plan):
    """
    Lấy dữ liệu Plan từ database theo ngày
    Returns: DataFrame với columns [ID sản phẩm, Code cám, Tên cám, Số lượng, Dạng ép viên]
    """
    conn = sqlite3.connect('database_new.db')
    
    # Format ngày
    if isinstance(ngay_plan, str):
        ngay_str = ngay_plan
        try:
            ngay_dt = datetime.strptime(ngay_plan, '%Y-%m-%d')
            ngay_str_alt = ngay_dt.strftime('%d/%m/%Y')
        except:
            ngay_str_alt = ngay_plan
    else:
        ngay_str = ngay_plan.strftime('%Y-%m-%d')
        ngay_str_alt = ngay_plan.strftime('%d/%m/%Y')
    
    query = """
        SELECT 
            p.[ID sản phẩm],
            sp.[Code cám],
            sp.[Tên cám],
            SUM(p.[Số lượng]) as [Số lượng],
            sp.[Dạng ép viên],
            sp.[Batch size],
            sp.[Kích cỡ ép viên]
        FROM Plan p
        LEFT JOIN SanPham sp ON p.[ID sản phẩm] = sp.ID
        WHERE p.[Đã xóa] = 0 AND (p.[Ngày plan] = ? OR p.[Ngày plan] = ?)
        GROUP BY p.[ID sản phẩm], sp.[Code cám], sp.[Tên cám], sp.[Dạng ép viên], sp.[Batch size], sp.[Kích cỡ ép viên]
        ORDER BY p.[Số lượng] DESC
    """
    
    df = pd.read_sql_query(query, conn, params=(ngay_str, ngay_str_alt))
    conn.close()
    
    return df


def get_pellet_capacity(code_cam=None):
    """
    Lấy T/h tối ưu từ bảng PelletCapacity
    Returns: Dict {machine: {code_cam: T/h}}
    """
    conn = sqlite3.connect('database_new.db')
    
    if code_cam:
        query = """
            SELECT [Số máy], [Code cám], [T/h]
            FROM PelletCapacity 
            WHERE [Đã xóa] = 0 AND [Code cám] = ?
            ORDER BY [T/h] DESC
        """
        df = pd.read_sql_query(query, conn, params=(code_cam,))
    else:
        query = """
            SELECT [Số máy], [Code cám], MAX([T/h]) as [T/h]
            FROM PelletCapacity 
            WHERE [Đã xóa] = 0
            GROUP BY [Số máy], [Code cám]
        """
        df = pd.read_sql_query(query, conn)
    
    conn.close()
    
    # Convert to nested dict
    capacity_map = {}
    for _, row in df.iterrows():
        machine = row['Số máy']
        code = row['Code cám']
        th = row['T/h']
        
        if machine not in capacity_map:
            capacity_map[machine] = {}
        capacity_map[machine][code] = th
    
    return capacity_map


def calculate_pellet_plan_layout(ngay_plan):
    """
    Tính toán layout bảng PLAN PELLET MILL
    Phân bổ sản phẩm vào 7 máy x 3 ca
    
    Returns: Dict với cấu trúc:
    {
        'date': ngay_plan,
        'week': week_number,
        'machines': {
            'PL1': {
                'TON_DAU': {'code': ..., 'me': ..., 'tons': ..., 'gio': ...},
                'CA1': [{'code': ..., 'me': ..., 'tons': ..., 'gio': ...}, ...],
                'TARGET_CA1': value,
                'CA2': [...],
                'TARGET_CA2': value,
                'CA3': [...],
                'TARGET_CA3': value,
                'NEXT': {...}
            },
            ...
        },
        'totals': {
            'TOTAL': ...,
            'TARGET': ...,
            'PLAN_PL': {'hours': ..., 'tons': ...},
            'KHSX': ...
        }
    }
    """
    # Lấy dữ liệu Plan
    df_plan = get_plan_data_for_date(ngay_plan)
    
    if len(df_plan) == 0:
        return None
    
    # Lấy dữ liệu T/h
    capacity_map = get_pellet_capacity()
    
    # Khởi tạo cấu trúc
    # Handle different date types: str, datetime, or date
    from datetime import date
    if isinstance(ngay_plan, str):
        date_str = ngay_plan
        week_num = datetime.strptime(ngay_plan, '%Y-%m-%d').isocalendar()[1]
    elif isinstance(ngay_plan, datetime):
        date_str = ngay_plan.strftime('%Y-%m-%d')
        week_num = ngay_plan.isocalendar()[1]
    elif isinstance(ngay_plan, date):
        date_str = ngay_plan.strftime('%Y-%m-%d')
        week_num = ngay_plan.isocalendar()[1]
    else:
        date_str = str(ngay_plan)
        week_num = 1
    
    result = {
        'date': date_str,
        'week': week_num,
        'machines': {},
        'totals': {
            'TOTAL': 0,
            'TARGET': 0,
            'PLAN_PL': {'hours': 0, 'tons': 0},
            'KHSX': 0
        }
    }
    
    # Khởi tạo machines

    for machine in DEFAULT_MACHINES.keys():
        result['machines'][machine] = {
            'die': DEFAULT_MACHINES[machine]['die'],
            'default_capacity': DEFAULT_MACHINES[machine]['capacity'],
            'TON_DAU': None,
            'CA1': [],
            'TARGET_CA1': 0,
            'CA2': [],
            'TARGET_CA2': 0,
            'CA3': [],
            'TARGET_CA3': 0,
            'NEXT': None,
            'total_hours': 0,
            'total_tons': 0
        }
    
    # Phân bổ sản phẩm vào máy
    machines_list = list(DEFAULT_MACHINES.keys())
    machine_hours = {m: 0 for m in machines_list}  # Số giờ đã dùng
    machine_index = 0
    
    for _, row in df_plan.iterrows():
        code_cam = row['Code cám']
        so_luong_kg = row['Số lượng']
        so_luong_tons = so_luong_kg / 1000
        batch_size = row['Batch size'] if pd.notna(row['Batch size']) else 2800
        so_me = so_luong_kg / batch_size if batch_size > 0 else 0
        
        # Tìm máy phù hợp (còn giờ trống)
        assigned = False
        attempts = 0
        
        while not assigned and attempts < len(machines_list):
            machine = machines_list[machine_index]
            
            # Lấy T/h cho code này trên máy này
            th = DEFAULT_MACHINES[machine]['capacity']  # Default
            if machine in capacity_map and code_cam in capacity_map.get(machine, {}):
                th = capacity_map[machine][code_cam]
            
            # Tính số giờ cần
            hours_needed = so_luong_tons / th if th > 0 else 0
            
            # Kiểm tra còn giờ trống không (max 24 giờ/ngày = 8h x 3 ca)
            max_hours = HOURS_PER_SHIFT * 3  # 24 giờ
            if machine_hours[machine] + hours_needed <= max_hours:
                # Gán vào ca phù hợp
                current_hours = machine_hours[machine]
                if current_hours < HOURS_PER_SHIFT:
                    ca = 'CA1'
                elif current_hours < HOURS_PER_SHIFT * 2:
                    ca = 'CA2'
                else:
                    ca = 'CA3'
                
                result['machines'][machine][ca].append({
                    'code': code_cam,
                    'me': round(so_me, 1),
                    'tons': round(so_luong_tons, 1),
                    'gio': round(hours_needed, 1),
                    'th': round(th, 1)
                })
                
                machine_hours[machine] += hours_needed
                result['machines'][machine]['total_hours'] += hours_needed
                result['machines'][machine]['total_tons'] += so_luong_tons
                
                assigned = True
            else:
                machine_index = (machine_index + 1) % len(machines_list)
                attempts += 1
        
        # Nếu không gán được vào máy nào, gán vào máy có ít giờ nhất
        if not assigned:
            min_machine = min(machine_hours, key=machine_hours.get)
            machine = min_machine
            
            th = DEFAULT_MACHINES[machine]['capacity']
            if machine in capacity_map and code_cam in capacity_map.get(machine, {}):
                th = capacity_map[machine][code_cam]
            
            hours_needed = so_luong_tons / th if th > 0 else 0
            
            # Gán vào CA3 (overflow)
            result['machines'][machine]['CA3'].append({
                'code': code_cam,
                'me': round(so_me, 1),
                'tons': round(so_luong_tons, 1),
                'gio': round(hours_needed, 1),
                'th': round(th, 1)
            })
            
            machine_hours[machine] += hours_needed
            result['machines'][machine]['total_hours'] += hours_needed
            result['machines'][machine]['total_tons'] += so_luong_tons
    
    # Tính totals
    total_tons = 0
    total_hours = 0
    
    for machine in machines_list:
        m_data = result['machines'][machine]
        
        # Tính TARGET cho mỗi ca
        for ca in ['CA1', 'CA2', 'CA3']:
            ca_tons = sum(item['tons'] for item in m_data[ca])
            m_data[f'TARGET_{ca}'] = round(ca_tons, 1)
        
        total_tons += m_data['total_tons']
        total_hours += m_data['total_hours']
    
    result['totals']['TOTAL'] = round(total_tons, 1)
    result['totals']['TARGET'] = round(total_tons, 1)
    result['totals']['PLAN_PL'] = {
        'hours': round(total_hours, 1),
        'tons': round(total_tons, 1)
    }
    result['totals']['KHSX'] = round(total_tons * 1.07, 1)  # +7% for mixer
    
    return result


def save_pellet_plan(plan_data, ngay_plan, nguoi_tao='system'):
    """
    Lưu phân bổ Pellet Plan vào database
    """
    conn = sqlite3.connect('database_new.db')
    cursor = conn.cursor()
    
    # Tạo bảng nếu chưa có
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS PelletPlan (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            [Ngày plan] DATE,
            [Số máy] TEXT,
            [Ca] TEXT,
            [Code cám] TEXT,
            [Số mẻ] REAL,
            [Số lượng (tons)] REAL,
            [Số giờ] REAL,
            [T/h] REAL,
            [Người tạo] TEXT,
            [Thời gian tạo] DATETIME,
            [Đã xóa] INTEGER DEFAULT 0
        )
    """)
    
    # Xóa dữ liệu cũ của ngày này
    ngay_str = ngay_plan if isinstance(ngay_plan, str) else ngay_plan.strftime('%Y-%m-%d')
    cursor.execute("UPDATE PelletPlan SET [Đã xóa] = 1 WHERE [Ngày plan] = ?", (ngay_str,))
    
    # Insert dữ liệu mới
    thoi_gian_tao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    count = 0
    
    for machine, m_data in plan_data['machines'].items():
        for ca in ['CA1', 'CA2', 'CA3']:
            for item in m_data[ca]:
                cursor.execute("""
                    INSERT INTO PelletPlan 
                    ([Ngày plan], [Số máy], [Ca], [Code cám], [Số mẻ], [Số lượng (tons)], [Số giờ], [T/h], [Người tạo], [Thời gian tạo])
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ngay_str, machine, ca, item['code'], item['me'], item['tons'], item['gio'], item['th'], nguoi_tao, thoi_gian_tao))
                count += 1
    
    conn.commit()
    conn.close()
    
    return count


def get_saved_pellet_plan(ngay_plan):
    """
    Lấy Pellet Plan đã lưu từ database
    """
    conn = sqlite3.connect('database_new.db')
    
    ngay_str = ngay_plan if isinstance(ngay_plan, str) else ngay_plan.strftime('%Y-%m-%d')
    
    query = """
        SELECT [Số máy], [Ca], [Code cám], [Số mẻ], [Số lượng (tons)], [Số giờ], [T/h]
        FROM PelletPlan
        WHERE [Ngày plan] = ? AND [Đã xóa] = 0
        ORDER BY [Số máy], [Ca]
    """
    
    try:
        df = pd.read_sql_query(query, conn, params=(ngay_str,))
        conn.close()
        return df
    except:
        conn.close()
        return pd.DataFrame()
