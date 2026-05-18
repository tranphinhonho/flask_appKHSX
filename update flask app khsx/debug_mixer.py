import sys, os
sys.path.insert(0, r'D:\Github\flask_appKHSX')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DATABASE_URL'] = (
    'postgresql://neondb_owner:npg_MBpyCtcL27vm'
    '@ep-small-bar-a1bpplnk-pooler.ap-southeast-1.aws.neon.tech'
    '/neondb?sslmode=require'
)
import config
from utils import get_db_connection
from utils.production_importer import ProductionImporter
from pathlib import Path

DB = config.DATABASE_PATH
fpath = Path(r'D:\Github\flask_appKHSX\update flask app khsx\BATCHING-TONBON\production 2.csv')
prod = ProductionImporter(db_path=DB)
parsed = prod._parse_production_csv(fpath)
item = parsed['products'][0]
print('First product:', item)

conn = get_db_connection(DB)
cur = conn.cursor()

# Check Mixer columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='Mixer' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print('Mixer columns:', cols)

# Try insert with correct columns
try:
    cur.execute(
        'INSERT INTO "Mixer" ("Mã mixer","Ngày trộn","ID sản phẩm","Batch size",'
        '"Số lượng thực tế","Loss (kg)","Loss (%)","Đích đến","Số máy","Ca sản xuất","Ghi chú","Người tạo","Thời gian tạo","Đã xóa")'
        ' VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        ('MX99999','2026-05-02', 1, 100.0, 100.0, 0.0, 0.0, 'Pellet','Pellet 1','Import','Test','phinho','2026-05-18 00:00:00','0')
    )
    print('Insert OK!')
except Exception as e:
    print('Insert ERR:', type(e).__name__, str(e)[:200])

conn.rollback()
conn.close()
