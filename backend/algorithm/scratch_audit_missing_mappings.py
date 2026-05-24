import sys
import os
import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, r"D:\Kê hoạch sản xuât\laptrinh vao")
import config
from data_loader import load_all_data

today = datetime.datetime(2026, 5, 18)
data = load_all_data(config, target_date=today)

# Build brand_to_base mapping like demand_calculator.py
brand_to_base = {}
for fc in data['forecast']:
    base = fc.product_code
    brands_mapping = [
        ('HIGRO', fc.feed_code_higro),
        ('CP', fc.feed_code_cp),
        ('STAR', fc.feed_code_star),
        ('NUVO', fc.feed_code_nuvo),
        ('NASA', fc.feed_code_nasa),
        ('FARM', fc.feed_code_farm)
    ]
    for brand, code in brands_mapping:
        if code:
            c = str(code).strip().upper()
            brand_to_base[c] = base

# Collect all unique codes in silo_plan
silo_codes = set()
for day_idx, items in data['silo_plan'].items():
    for code in items:
        silo_codes.add(code.strip().upper())

# Collect all unique codes in bacang
bacang_codes = set()
for day_idx, items in data['bacang'].items():
    for code in items:
        bacang_codes.add(code.strip().upper())

print("SILO codes:")
for c in sorted(silo_codes):
    mapped = brand_to_base.get(c, None)
    print(f"  {c:<15} -> Mapped to: {mapped}")

print("\nBACANG codes:")
for c in sorted(bacang_codes):
    mapped = brand_to_base.get(c, None)
    print(f"  {c:<15} -> Mapped to: {mapped}")
