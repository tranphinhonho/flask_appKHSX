"""
Utility functions - Port từ admin/sys_functions.py
"""
import os
import bcrypt
import pytz
from datetime import datetime
from io import BytesIO


def get_vietnam_time(second=True):
    """Lấy thời gian Việt Nam"""
    tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.now(tz)
    return now


def get_timestamp(strf=None):
    """Lấy timestamp"""
    now = datetime.now()
    if strf:
        return now.strftime('%Y%m%d%H%M%S%f')
    return now.strftime('%Y-%m-%d %H:%M:%S')


def hashpw(password):
    """Hash password với bcrypt"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password, hashed_password):
    """Kiểm tra password"""
    try:
        return bcrypt.checkpw(password.encode(), hashed_password.encode())
    except Exception:
        return False


def get_project_folder():
    """Lấy tên thư mục project"""
    return os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
