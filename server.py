"""
Entry point cho Render (Start Command mặc định: python server.py).
Trên Render, sử dụng gunicorn nếu có; fallback Flask dev server cho local.
"""
import os
from app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Render set RENDER=true; nếu có gunicorn nên dùng gunicorn,
    # nhưng vì Render đang gọi 'python server.py' thì ta dùng waitress/flask.
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port)
    except ImportError:
        # Fallback cuối cùng — Flask built-in (không tối ưu cho production)
        app.run(host='0.0.0.0', port=port, debug=False)
