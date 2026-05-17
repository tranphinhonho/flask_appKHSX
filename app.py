"""
Flask App - Kế hoạch Sản xuất B7KHSX
Entry point
"""
import os
import sys

# Thêm flask_app vào path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, redirect, url_for, session, send_from_directory, jsonify
from flask_cors import CORS
import config
from backend import db
from backend.auth import login_required

# API Blueprints
from backend.api.auth_routes import auth_bp
from backend.api.sanpham_routes import sanpham_bp
from backend.api.dathang_routes import dathang_bp
from backend.api.email_routes import email_bp
from backend.api.tonbon_routes import tonbon_bp
from backend.api.batching_routes import batching_bp
from backend.api.baobi_routes import baobi_bp
from backend.api.packingplan_routes import packingplan_bp
from backend.api.pellet_routes import pellet_bp
from backend.api.stockold_routes import stockold_bp
from backend.api.packing_routes import packing_bp
from backend.api.sale_routes import sale_bp
from backend.api.plan_routes import plan_bp
from backend.api.stockhomnay_routes import stockhomnay_bp
from backend.api.lichthang_routes import lichthang_bp
from backend.api.admin_routes import admin_bp
from backend.api.ghichu_routes import ghichu_bp


def create_app():
    app = Flask(
        __name__,
        static_folder=config.STATIC_FOLDER,
        template_folder=config.TEMPLATE_FOLDER
    )

    # Config
    app.secret_key = config.SECRET_KEY
    app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
    app.config['SESSION_PERMANENT'] = config.SESSION_PERMANENT

    # CORS
    CORS(app, supports_credentials=True)

    # Init database
    db.init_db(config.DATABASE_PATH)

    # Ensure GhiChu table exists
    try:
        from backend.api.ghichu_routes import _ensure_table
        _ensure_table()
    except Exception:
        pass

    # Fix NULL 'Đã xóa' values (PostgreSQL tables may lack DEFAULT 0)
    try:
        conn = db.connect_db()
        cursor = conn.cursor()
        tables_with_da_xoa = [
            'SanPham', 'DatHang', 'Plan', 'Sale', 'Packing', 'Mixer',
            'StockOld', 'StockHomNay', 'TonBon', 'BaoBi', 'Forecast',
            'PelletCapacity', 'PelletPlan', 'EmailImportLog', 'PackingPlan'
        ]
        for tbl in tables_with_da_xoa:
            try:
                cursor.execute(db.sql(f"UPDATE [{tbl}] SET [Đã xóa] = 0 WHERE [Đã xóa] IS NULL"))
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: migration fix_null_da_xoa failed: {e}")

    # Tạo thư mục uploads nếu chưa có
    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

    # Register API Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(sanpham_bp)
    app.register_blueprint(dathang_bp)
    app.register_blueprint(email_bp)
    app.register_blueprint(tonbon_bp)
    app.register_blueprint(batching_bp)
    app.register_blueprint(baobi_bp)
    app.register_blueprint(packingplan_bp)
    app.register_blueprint(pellet_bp)
    app.register_blueprint(stockold_bp)
    app.register_blueprint(packing_bp)
    app.register_blueprint(sale_bp)
    app.register_blueprint(plan_bp)
    app.register_blueprint(stockhomnay_bp)
    app.register_blueprint(lichthang_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ghichu_bp)

    # ========== Health Check (for cron-job.org keep-alive) ==========

    @app.route('/healthz')
    def healthz():
        return jsonify({"status": "ok"}), 200

    # ========== Page Routes ==========

    @app.route('/')
    def index():
        if 'username' in session:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login_page'))

    @app.route('/login')
    def login_page():
        if 'username' in session:
            return redirect(url_for('dashboard'))
        return render_template('login.html')

    @app.route('/dashboard')
    @login_required
    def dashboard():
        return render_template('dashboard.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/sanpham')
    @login_required
    def page_sanpham():
        return render_template('sanpham.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/dathang')
    @login_required
    def page_dathang():
        return render_template('dathang.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/nhanemail')
    @login_required
    def page_nhanemail():
        return render_template('email_import.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/tonbon')
    @login_required
    def page_tonbon():
        return render_template('tonbon.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/batching')
    @login_required
    def page_batching():
        return render_template('batching.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/baobi')
    @login_required
    def page_baobi():
        return render_template('baobi.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/packingplan')
    @login_required
    def page_packingplan():
        return render_template('packingplan.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/pellet')
    @login_required
    def page_pellet():
        return render_template('pellet.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/stockold')
    @login_required
    def page_stockold():
        return render_template('stockold.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/packing')
    @login_required
    def page_packing():
        return render_template('packing.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/sale')
    @login_required
    def page_sale():
        return render_template('sale.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/plan')
    @login_required
    def page_plan():
        return render_template('plan.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/stockhomnay')
    @login_required
    def page_stockhomnay():
        return render_template('stockhomnay.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/lichthang')
    @login_required
    def page_lichthang():
        return render_template('lichthang.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/page/ghichu')
    @login_required
    def page_ghichu():
        return render_template('ghichu.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    # ========== Admin Page Routes ==========

    @app.route('/admin/users')
    @login_required
    def admin_users():
        if session.get('username') not in ['phinho', 'kde', 'admin']:
            return redirect(url_for('dashboard'))
        return render_template('admin_users.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/admin/roles')
    @login_required
    def admin_roles():
        if session.get('username') not in ['phinho', 'kde', 'admin']:
            return redirect(url_for('dashboard'))
        return render_template('admin_roles.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/admin/settings')
    @login_required
    def admin_settings():
        if session.get('username') not in ['phinho', 'kde', 'admin']:
            return redirect(url_for('dashboard'))
        return render_template('admin_settings.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    @app.route('/admin/tables')
    @login_required
    def admin_tables():
        if session.get('username') not in ['phinho', 'kde', 'admin']:
            return redirect(url_for('dashboard'))
        return render_template('admin_tables.html',
                               username=session.get('username'),
                               fullname=session.get('fullname'))

    # Serve images từ thư mục project gốc
    @app.route('/project-images/<path:filename>')
    def project_images(filename):
        return send_from_directory(config.IMAGES_DIR, filename)

    # Serve template files (Excel templates cho download)
    @app.route('/templates/<path:filename>')
    def template_files(filename):
        return send_from_directory(config.TEMPLATE_DIR, filename)

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        if 'username' in session:
            return render_template('dashboard.html',
                                   username=session.get('username'),
                                   fullname=session.get('fullname')), 404
        return redirect(url_for('login_page'))

    return app


# Tạo app ở module level cho gunicorn (production)
app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
