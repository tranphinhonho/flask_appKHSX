import sys
import os
import io
import datetime

# Reconfigure encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, r"D:\Kê hoạch sản xuât\laptrinh vao")
import config
from data_loader import load_all_data
from demand_calculator import calculate_daily_demand

today = datetime.datetime(2026, 5, 18)
data = load_all_data(config, target_date=today)

print("silo_plan contents:")
for day_idx, items in data['silo_plan'].items():
    print(f"Day {day_idx}: {items}")

print("\nbacang contents:")
for day_idx, items in data['bacang'].items():
    print(f"Day {day_idx}: {items}")

print("\nRunning calculate_daily_demand...")
demand_list = calculate_daily_demand(
    today_date=today,
    day_of_week=1, # Monday
    forecast=data['forecast'],
    silo_plan=data['silo_plan'],
    bacang=data['bacang'],
    walkin_orders=[],
    ffstock=data['ffstock'],
    tonbon=data['tonbon'],
    khsx_yesterday=data['khsx_yesterday'],
    congsuat=data['congsuat'],
    produced_this_week={},
    ffstock_details=data.get('ffstock_details', {}),
    adjustments=data.get('adjustments')
)

print("\ndemand_list contents:")
for item in demand_list:
    brand_demands_str = getattr(item, 'brand_demands', {})
    print(f"Product: {item.product_code} | Batches: {item.batches} | Tons: {item.tons} | Silo: {item.silo_truck} | Brand Demands: {brand_demands_str}")
