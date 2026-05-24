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
from packaging_allocator import allocate_packaging
from constraint_solver import solve_constraints

today = datetime.datetime(2026, 5, 18)
data = load_all_data(config, target_date=today)

# Calculate produced_this_week like khsx_auto.py
produced_this_week = {} # Let's assume empty for this test or let's load it if we want, but let's check without it first

print("silo_plan contents:")
for day_idx, items in data['silo_plan'].items():
    print(f"Day {day_idx}: {items}")

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
    produced_this_week=produced_this_week,
    ffstock_details=data.get('ffstock_details', {}),
    adjustments=data.get('adjustments')
)

print("\nAfter calculate_daily_demand, check if HT11, HT13S, HG17S, HG16XS34, HG17SXS34 exist:")
for item in demand_list:
    if item.product_code in ['HT11', 'HT13S', 'HG17S', 'HG16XS34', 'HG17SXS34', '551', '552S', '567S', '566XS34', '567SXS34']:
        print(f"Product: {item.product_code} | Batches: {item.batches} | Tons: {item.tons} | Silo: {item.silo_truck} | Priority: {item.priority}")

# Now solve constraints
demand_list, warnings = solve_constraints(
    demand_list=demand_list,
    empty_bag=data['empty_bag'],
    congsuat=data['congsuat'],
    min_tons=config.MIN_DAILY_TONS,
    max_tons=config.MAX_DAILY_TONS,
    target_tons=config.TARGET_DAILY_TONS,
    ffstock_details=data.get('ffstock_details', {}),
)

print("\nAfter solve_constraints, check if they exist:")
for item in demand_list:
    if item.product_code in ['HT11', 'HT13S', 'HG17S', 'HG16XS34', 'HG17SXS34', '551', '552S', '567S', '566XS34', '567SXS34']:
        print(f"Product: {item.product_code} | Batches: {item.batches} | Tons: {item.tons} | Silo: {item.silo_truck} | Priority: {item.priority}")

# Now allocate packaging
allocate_packaging(demand_list, data['forecast'], adjustments=data.get('adjustments'))

print("\nAfter allocate_packaging, check packaging allocations:")
for item in demand_list:
    if item.product_code in ['HT11', 'HT13S', 'HG17S', 'HG16XS34', 'HG17SXS34', '551', '552S', '567S', '566XS34', '567SXS34']:
        print(f"Product: {item.product_code} | Star25: {item.star_25} | CP25: {item.cp_25} | Silo: {item.silo_truck}")
