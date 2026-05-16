"""
API routes cho module Nhận email (EmailImport)
Quản lý import FFSTOCK, BAG REPORT từ folder EXCEL hoặc upload trực tiếp
"""
from flask import Blueprint, request, jsonify, session
from backend.auth import login_required
from backend.utils import get_vietnam_time
import os
import sys
import glob

email_bp = Blueprint('email', __name__)


def _setup_utils_path():
    """Ensure utils directory is in sys.path"""
    api_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(api_dir)
    flask_app_dir = os.path.dirname(backend_dir)
    project_dir = os.path.dirname(flask_app_dir)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    return project_dir


def _get_stock_importer():
    """Create StockImporter with correct db path"""
    _setup_utils_path()
    from utils.stock_importer import StockImporter
    import config
    return StockImporter(db_path=config.DATABASE_PATH)


def _get_bag_importer():
    """Create BagReportImporter with correct db path"""
    _setup_utils_path()
    from utils.bag_report_importer import BagReportImporter
    import config
    return BagReportImporter(db_path=config.DATABASE_PATH)


def _get_excel_folder():
    """Get the EXCEL folder path"""
    import config, tempfile
    if config.DATABASE_PATH.startswith('postgresql'):
        return os.path.join(tempfile.gettempdir(), 'EXCEL')
    return os.path.join(os.path.dirname(config.DATABASE_PATH), 'EXCEL')


def _extract_date_from_filename(filename):
    """Extract date from filename like FFSTOCK 10-01-2026.xlsm"""
    import re
    match = re.search(r'(\d{1,2})-(\d{1,2})-(\d{4})', filename)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return None


# ==================== Scan Files from EXCEL folder ====================

@email_bp.route('/api/email/scan-files', methods=['GET'])
@login_required
def scan_excel_files():
    """Scan EXCEL folder for FFSTOCK and BAG REPORT files"""
    try:
        excel_dir = _get_excel_folder()
        if not os.path.exists(excel_dir):
            return jsonify({'success': True, 'ffstock': [], 'bag_report': []})

        stock_importer = _get_stock_importer()
        bag_importer = _get_bag_importer()

        # Find FFSTOCK files
        ffstock_files = []
        for pattern in ['FFSTOCK*.xls', 'FFSTOCK*.xlsx', 'FFSTOCK*.xlsm']:
            ffstock_files.extend(glob.glob(os.path.join(excel_dir, pattern)))

        # Find BAG REPORT files
        bag_files = []
        for pattern in ['*STOCK EMPTY BAG*.xls', '*STOCK EMPTY BAG*.xlsx', '*STOCK EMPTY BAG*.xlsm']:
            bag_files.extend(glob.glob(os.path.join(excel_dir, pattern)))

        # Build result
        ffstock_result = []
        for fp in sorted(ffstock_files, reverse=True):
            fname = os.path.basename(fp)
            size_kb = os.path.getsize(fp) / 1024
            is_dup = stock_importer.check_duplicate(fname)
            ngay = _extract_date_from_filename(fname)
            ffstock_result.append({
                'filename': fname,
                'filepath': fp,
                'size_kb': round(size_kb, 1),
                'imported': is_dup,
                'ngay_stock': ngay
            })

        bag_result = []
        for fp in sorted(bag_files, reverse=True):
            fname = os.path.basename(fp)
            size_kb = os.path.getsize(fp) / 1024
            is_dup = bag_importer.check_duplicate(fname)
            ngay = _extract_date_from_filename(fname)
            bag_result.append({
                'filename': fname,
                'filepath': fp,
                'size_kb': round(size_kb, 1),
                'imported': is_dup,
                'ngay_stock': ngay
            })

        return jsonify({
            'success': True,
            'ffstock': ffstock_result,
            'bag_report': bag_result,
            'excel_dir': excel_dir
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


# ==================== Preview ====================

@email_bp.route('/api/email/preview-ffstock', methods=['POST'])
@login_required
def preview_ffstock():
    """Preview FFSTOCK file"""
    data = request.get_json()
    filepath = data.get('filepath')

    if not filepath or not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'File không tồn tại'}), 400

    try:
        importer = _get_stock_importer()
        df = importer.preview_data(file_path=filepath, limit=500)

        if df is not None and len(df) > 0:
            return jsonify({
                'success': True,
                'data': df.to_dict('records'),
                'count': len(df)
            })
        else:
            return jsonify({'success': True, 'data': [], 'count': 0})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@email_bp.route('/api/email/preview-bag', methods=['POST'])
@login_required
def preview_bag():
    """Preview BAG REPORT file"""
    data = request.get_json()
    filepath = data.get('filepath')

    if not filepath or not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'File không tồn tại'}), 400

    try:
        importer = _get_bag_importer()
        df = importer.preview_data(file_path=filepath, limit=500)

        if df is not None and len(df) > 0:
            return jsonify({
                'success': True,
                'data': df.to_dict('records'),
                'count': len(df)
            })
        else:
            return jsonify({'success': True, 'data': [], 'count': 0})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


# ==================== Import ====================

@email_bp.route('/api/email/import-ffstock', methods=['POST'])
@login_required
def import_ffstock():
    """Import FFSTOCK file vào database"""
    data = request.get_json()
    filepath = data.get('filepath')
    overwrite = data.get('overwrite', False)

    if not filepath or not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'File không tồn tại'}), 400

    username = session.get('username', 'system')
    filename = os.path.basename(filepath)
    ngay_stock = _extract_date_from_filename(filename)

    try:
        importer = _get_stock_importer()
        result = importer.import_ffstock(
            file_path=filepath,
            nguoi_import=username,
            ngay_stock=ngay_stock,
            overwrite=overwrite
        )
        result['filename'] = filename
        result['ngay_stock'] = ngay_stock
        return jsonify(result)

    except Exception as e:
        return jsonify({'success': 0, 'errors': [str(e)]}), 400


@email_bp.route('/api/email/import-bag', methods=['POST'])
@login_required
def import_bag():
    """Import BAG REPORT file vào database"""
    data = request.get_json()
    filepath = data.get('filepath')
    overwrite = data.get('overwrite', False)

    if not filepath or not os.path.exists(filepath):
        return jsonify({'success': False, 'message': 'File không tồn tại'}), 400

    username = session.get('username', 'system')
    filename = os.path.basename(filepath)
    ngay_stock = _extract_date_from_filename(filename)

    try:
        importer = _get_bag_importer()
        result = importer.import_bag_report(
            file_path=filepath,
            nguoi_import=username,
            ngay_stock=ngay_stock,
            overwrite=overwrite
        )
        result['filename'] = filename
        result['ngay_stock'] = ngay_stock
        return jsonify(result)

    except Exception as e:
        return jsonify({'success': 0, 'errors': [str(e)]}), 400


# ==================== Upload from browser ====================

@email_bp.route('/api/email/upload-import', methods=['POST'])
@login_required
def upload_and_import():
    """Upload file from browser and import immediately"""
    file = request.files.get('file')
    file_type = request.form.get('file_type', 'FFSTOCK')  # FFSTOCK or BAG_REPORT
    overwrite = request.form.get('overwrite', 'false') == 'true'

    if not file:
        return jsonify({'success': False, 'message': 'Không có file'}), 400

    import tempfile
    excel_dir = _get_excel_folder()
    os.makedirs(excel_dir, exist_ok=True)
    saved_path = os.path.join(excel_dir, file.filename)

    try:
        file.save(saved_path)
    except PermissionError:
        ext = os.path.splitext(file.filename)[1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=excel_dir)
        file.save(tmp.name)
        saved_path = tmp.name

    username = session.get('username', 'system')
    filename = file.filename
    ngay_stock = _extract_date_from_filename(filename)

    try:
        if file_type == 'BAG_REPORT':
            importer = _get_bag_importer()
            result = importer.import_bag_report(
                file_path=saved_path,
                nguoi_import=username,
                ngay_stock=ngay_stock,
                overwrite=overwrite
            )
        else:
            importer = _get_stock_importer()
            result = importer.import_ffstock(
                file_path=saved_path,
                nguoi_import=username,
                ngay_stock=ngay_stock,
                overwrite=overwrite
            )

        result['filename'] = filename
        result['ngay_stock'] = ngay_stock
        return jsonify(result)

    except Exception as e:
        return jsonify({'success': 0, 'errors': [str(e)]}), 400


# ==================== Import History ====================

@email_bp.route('/api/email/history', methods=['GET'])
@login_required
def get_import_history():
    """Get import history"""
    limit = request.args.get('limit', 30, type=int)

    try:
        stock_importer = _get_stock_importer()
        history = stock_importer.get_import_history(limit=limit)

        result = []
        for row in history:
            result.append({
                'id': row[0],
                'filename': row[1],
                'loai_file': row[2],
                'so_luong': row[3],
                'ngay_email': row[4],
                'nguoi_import': row[5],
                'thoi_gian_import': row[6]
            })

        return jsonify({'success': True, 'history': result})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


# ==================== Check Email (Outlook COM) ====================

@email_bp.route('/api/email/check-outlook', methods=['POST'])
@login_required
def check_outlook_emails():
    """Check Outlook for new FFSTOCK/BAG REPORT emails via COM"""
    data = request.get_json() or {}
    days_back = data.get('days_back', 4)

    try:
        _setup_utils_path()
        from utils.email_receiver import EmailReceiver

        receiver = EmailReceiver()
        if not receiver.connect():
            return jsonify({'success': False, 'message': 'Không thể kết nối Outlook'}), 400

        emails = receiver.get_stock_emails(days_back=days_back)

        result_emails = []
        for email in emails:
            email_data = {
                'subject': email.get('subject', ''),
                'sender': email.get('sender', ''),
                'sender_email': email.get('sender_email', ''),
                'received_time': str(email.get('received_time', '')),
                'unread': email.get('unread', False),
                'entry_id': email.get('entry_id', ''),
                'stock_files': email.get('stock_files', []),
                'bag_files': email.get('bag_files', [])
            }
            result_emails.append(email_data)

        return jsonify({
            'success': True,
            'emails': result_emails,
            'count': len(result_emails)
        })

    except ImportError:
        return jsonify({'success': False,
                        'message': 'pywin32 chưa được cài đặt. Dùng: pip install pywin32'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@email_bp.route('/api/email/download-and-import', methods=['POST'])
@login_required
def download_and_import():
    """Download attachment from Outlook email and import"""
    data = request.get_json()
    entry_id = data.get('entry_id')
    att_index = data.get('att_index')
    file_type = data.get('file_type', 'FFSTOCK')
    overwrite = data.get('overwrite', False)

    if not entry_id or not att_index:
        return jsonify({'success': False, 'message': 'Thiếu thông tin email'}), 400

    try:
        _setup_utils_path()
        from utils.email_receiver import EmailReceiver

        receiver = EmailReceiver()
        if not receiver.connect():
            return jsonify({'success': False, 'message': 'Không thể kết nối Outlook'}), 400

        # Get email item by entry_id
        item = receiver.namespace.GetItemFromID(entry_id)
        att = item.Attachments.Item(att_index)
        filename = att.FileName

        # Save to EXCEL folder
        excel_dir = _get_excel_folder()
        os.makedirs(excel_dir, exist_ok=True)
        saved_path = os.path.join(excel_dir, filename)
        att.SaveAsFile(saved_path)

        # Import
        username = session.get('username', 'system')
        ngay_stock = _extract_date_from_filename(filename)

        if file_type == 'BAG_REPORT':
            importer = _get_bag_importer()
            result = importer.import_bag_report(
                file_path=saved_path,
                nguoi_import=username,
                ngay_stock=ngay_stock,
                overwrite=overwrite
            )
        else:
            importer = _get_stock_importer()
            result = importer.import_ffstock(
                file_path=saved_path,
                nguoi_import=username,
                ngay_stock=ngay_stock,
                overwrite=overwrite
            )

        result['filename'] = filename
        result['ngay_stock'] = ngay_stock
        return jsonify(result)

    except Exception as e:
        return jsonify({'success': 0, 'errors': [str(e)]}), 400
