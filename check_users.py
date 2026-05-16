import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def _translate_sql(sql):
    result = re.sub(r'\[([^\]]+)\]', r'"\1"', sql)
    _TABLES = ['StockOld','StockHomNay','SanPham','DatHang','DonViTinh','EmailImportLog','MasterdataLoss','PackingPlan','BagStock','BaoBi','Packing','Pellet','PelletCapacity','Plan','Sale','TestCan_Reports','Testcan','Mixer','TonBon']
    for tbl in _TABLES:
        result = re.sub(r'(?<!")(?<!\w)\b' + re.escape(tbl) + r'\b(?!")', f'"{tbl}"', result)
    _COLUMNS = ['NgayStock','TenCam','KichCoDongBao','SoLuongBaoBi','TenFile','NguoiTao','ThoiGianTao','DaXoa','NgayEmail','LoaiFile','SoLuongDong','ThoiGianImport','NguoiImport']
    for col in _COLUMNS:
        result = re.sub(r'(?<!")(?<!\w)(?<!\.)' + re.escape(col) + r'(?!")', f'"{col}"', result)
    result = re.sub(r'\.ID\b(?!")', '."ID"', result)
    result = result.replace('?', '%s')
    result = re.sub(r'"Đã xóa"\s*=\s*0\b', '"Đã xóa" = \'0\'', result)
    result = re.sub(r'"Đã xóa"\s*=\s*1\b', '"Đã xóa" = \'1\'', result)
    result = re.sub(r'"DaXoa"\s*=\s*0\b', '"DaXoa" = \'0\'', result)
    result = re.sub(r'"DaXoa"\s*=\s*1\b', '"DaXoa" = \'1\'', result)
    return result

# Test bagstock queries
tests = [
    "SELECT MAX(NgayStock) FROM BagStock WHERE DaXoa = 0",
    "SELECT TenCam, SoLuongBaoBi FROM BagStock WHERE NgayStock = ? AND DaXoa = 0 ORDER BY TenCam",
]
for sql in tests:
    translated = _translate_sql(sql)
    print(f"IN:  {sql}")
    print(f"OUT: {translated}")
    print()

import psycopg2
conn = psycopg2.connect("postgresql://neondb_owner:npg_MBpyCtcL27vm@ep-small-bar-a1bpplnk-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require")
cursor = conn.cursor()
cursor.execute(_translate_sql("SELECT MAX(NgayStock) FROM BagStock WHERE DaXoa = 0"))
print(f"Latest BagStock: {cursor.fetchone()}")
cursor.execute(_translate_sql("SELECT COUNT(*) FROM BagStock WHERE NgayStock = %s AND DaXoa = 0"), ('2026-05-14',))
print(f"Count 2026-05-14: {cursor.fetchone()}")
conn.close()
