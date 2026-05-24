import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from backend import db

print("DATABASE_PATH used by Flask app:", config.DATABASE_PATH)
db.init_db(config.DATABASE_PATH)

tables = [
    'StockOld', 'StockHomNay', 'SanPham', 'DatHang', 'DonViTinh',
    'EmailImportLog', 'PackingPlan', 'BagStock', 'BaoBi', 'Packing',
    'Pellet', 'PelletCapacity', 'Plan', 'Sale', 'Mixer', 'TonBon', 'tbsys_Users', 'GhiChu'
]

for tbl in tables:
    try:
        count = db.query_database(f"SELECT COUNT(*) FROM [{tbl}]", data_type='value')
        print(f"Table {tbl}: {count} rows")
    except Exception as e:
        try:
            count = db.query_database(f'SELECT COUNT(*) FROM "{tbl}"', data_type='value')
            print(f"Table {tbl} (quoted): {count} rows")
        except Exception as e2:
            print(f"Table {tbl} Error: {e2}")
