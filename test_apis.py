import sys, os, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()
client = app.test_client()

# Mock session
with client.session_transaction() as sess:
    sess['username'] = 'phinho'
    sess['fullname'] = 'Phan Phin Ho'
    sess['id_vaitro'] = '1'

print("=== TESTING /api/sanpham ===")
res1 = client.get('/api/sanpham?page=1&per_page=5')
print("Status:", res1.status_code)
data1 = json.loads(res1.data.decode('utf-8'))
print("Total records:", data1.get('total', 0))
print("Sample keys of data:", list(data1.get('data', [{}])[0].keys()) if data1.get('data') else "No data")

print("\n=== TESTING /api/dathang ===")
res2 = client.get('/api/dathang?page=1&per_page=5')
print("Status:", res2.status_code)
data2 = json.loads(res2.data.decode('utf-8'))
print("Total records:", data2.get('total', 0))
print("Sample keys of data:", list(data2.get('data', [{}])[0].keys()) if data2.get('data') else "No data")

print("\n=== TESTING /api/tonbon/list ===")
res3 = client.get('/api/tonbon/list?page=1&per_page=5')
print("Status:", res3.status_code)
data3 = json.loads(res3.data.decode('utf-8'))
print("Total records:", data3.get('total', 0))
print("Sample keys of data:", list(data3.get('data', [{}])[0].keys()) if data3.get('data') else "No data")
