import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\Github\flask_appKHSX')
os.environ['DATABASE_URL'] = (
    'postgresql://neondb_owner:npg_MBpyCtcL27vm'
    '@ep-small-bar-a1bpplnk-pooler.ap-southeast-1.aws.neon.tech'
    '/neondb?sslmode=require'
)
import config
from utils.packing_importer import PackingImporter

PACKING_FILE = r'D:\Github\flask_appKHSX\update flask app khsx\DAILY PACKING THANG 5.2026.xlsm'
importer = PackingImporter(db_path=config.DATABASE_PATH)

for day in [16, 17]:
    r = importer.import_packing_data(
        file_path=PACKING_FILE, sheet_name=str(day),
        nguoi_import='phinho', year=2026, month=5
    )
    ok  = r['success']
    del_= r['deleted']
    nf  = r['not_found']
    err = r['errors']
    print(f"Ngay {day}/5: thanh_cong={ok}, xoa_cu={del_}, not_found={nf}, errors={err}")
