"""
Platform detection utilities
Xác định môi trường chạy (local Windows vs Cloud Linux)
"""

import platform
import os


def is_windows() -> bool:
    """Kiểm tra có phải Windows không"""
    return platform.system() == "Windows"


def is_cloud() -> bool:
    """Kiểm tra có phải chạy trên Streamlit Cloud không"""
    # Streamlit Cloud chạy trên Linux
    if platform.system() != "Windows":
        return True
    # Hoặc kiểm tra environment variable
    return os.environ.get("STREAMLIT_CLOUD", "").lower() == "true"


def is_outlook_available() -> bool:
    """Kiểm tra có thể sử dụng Outlook COM không"""
    if not is_windows():
        return False
    
    try:
        import win32com.client
        return True
    except ImportError:
        return False


def get_email_receiver():
    """
    Trả về email receiver phù hợp với platform
    - Windows với Outlook: EmailReceiver (COM)
    - Cloud/Linux: None (dùng file upload thay thế)
    """
    if is_outlook_available():
        from utils.email_receiver import EmailReceiver
        return EmailReceiver()
    else:
        print("⚠️ Outlook không khả dụng trên platform này")
        print("   Sử dụng file upload thay thế")
        return None


def get_onedrive_receiver():
    """
    Trả về OneDrive receiver
    - Windows: OneDriveSyncReceiver (đọc folder sync)
    - Cloud: None (dùng file upload)
    """
    if is_windows():
        try:
            from utils.onedrive_receiver import OneDriveSyncReceiver
            return OneDriveSyncReceiver()
        except Exception as e:
            print(f"⚠️ Không thể khởi tạo OneDrive receiver: {e}")
            return None
    else:
        return None
