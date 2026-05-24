"""
Cấu hình ứng dụng Flask - Kế hoạch Sản xuất B7KHSX
Hỗ trợ dual mode: local (SQLite) và production (PostgreSQL)
"""
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

# ============ Database ============
# Ưu tiên DATABASE_URL (PostgreSQL trên Neon.tech) nếu có
# Nếu không có, fallback về SQLite local
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    DATABASE_PATH = DATABASE_URL
else:
    DATABASE_PATH = os.path.join(BASE_DIR, 'database_new.db')

# ============ Flask ============
SECRET_KEY = os.environ.get('SECRET_KEY', 'b7khsx-flask-secret-key-2026')
SESSION_TYPE = 'filesystem'
SESSION_PERMANENT = True
PERMANENT_SESSION_LIFETIME = 30 * 24 * 60 * 60  # 30 ngày

# ============ Static / Templates ============
STATIC_FOLDER = os.path.join(BASE_DIR, 'frontend', 'static')
TEMPLATE_FOLDER = os.path.join(BASE_DIR, 'frontend', 'templates')

# ============ Images & Templates ============
# Trên production (Render), dùng thư mục nội bộ flask_app
IMAGES_DIR = os.path.join(PROJECT_DIR, 'images') if os.path.exists(os.path.join(PROJECT_DIR, 'images')) else os.path.join(BASE_DIR, 'images')
TEMPLATE_DIR = os.path.join(PROJECT_DIR, 'Template') if os.path.exists(os.path.join(PROJECT_DIR, 'Template')) else os.path.join(BASE_DIR, 'templates_data')

# ============ Upload ============
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

# ============ Gemini AI ============
# Ưu tiên env var, fallback đọc từ admin/config.json nếu có
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
if not GEMINI_API_KEY:
    config_path = os.path.join(PROJECT_DIR, 'admin', 'config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                _config = json.load(f)
            GEMINI_API_KEY = _config.get('api_key_gemini', '')
        except Exception:
            pass
