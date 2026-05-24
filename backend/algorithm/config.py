"""
config.py - Cấu hình đường dẫn file và hằng số
"""
import os

# ============================================
# THƯ MỤC GỐC
# ============================================
ALGO_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.dirname(os.path.dirname(ALGO_DIR))
DATA_DIR = os.path.dirname(WEB_DIR)

# ============================================
# ĐƯỜNG DẪN FILE INPUT
# ============================================
FORECAST_DIR = os.path.join(DATA_DIR, 'FORECAST')
SILO_DIR = os.path.join(DATA_DIR, 'SILO')
BACANG_DIR = os.path.join(DATA_DIR, 'BACANG')
FSTOCK_DIR = os.path.join(DATA_DIR, 'FSTOCK-BAG')
TONBON_DIR = os.path.join(DATA_DIR, 'BATCHING-TONBON')
PLAN_DIR = os.path.join(DATA_DIR, 'plan')

# File cố định (ít thay đổi)
KHSX_FILE = os.path.join(DATA_DIR, 'KHSX THANG 5-20261.xlsm')
PLAN_FILE = os.path.join(PLAN_DIR, 'Plan.xlsm')
QUICK_ADJUST_FILE = os.path.join(DATA_DIR, 'DIEU_CHINH_NHANH.xlsx')


# ============================================
# HẰNG SỐ SẢN XUẤT
# ============================================
MIN_DAILY_TONS = 2100    # Công suất tối thiểu (tấn/ngày)
MAX_DAILY_TONS = 2500    # Công suất tối đa (tấn/ngày)
TARGET_DAILY_TONS = 2250 # Mục tiêu (tấn/ngày)

# Trọng lượng mẻ mặc định
DEFAULT_TON_PER_BATCH = 8.4
SMALL_DIE_TON_PER_BATCH = 8.0  # Cho sản phẩm DIE nhỏ (55x)
CDIE_TON_PER_BATCH = 5.0       # Chuyển khuôn

# Ngưỡng hoàn thành (%) để không cần bù
COMPLETION_THRESHOLD = 95

# Số ngày làm việc trong tuần (Thứ 2 → Thứ 7)
WORKING_DAYS_PER_WEEK = 6

# ============================================
# THƯ MỤC OUTPUT
# ============================================
OUTPUT_DIR = os.path.join(ALGO_DIR, 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)
