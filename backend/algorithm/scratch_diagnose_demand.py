import sys
import os
from datetime import datetime

sys.path.insert(0, r"D:\Kê hoạch sản xuât\laptrinh vao")
import config
from data_loader import load_all_data
from demand_calculator import calculate_daily_demand

def main():
    today = datetime(2026, 5, 18) # 18-05-2026
    day_of_week = 1 # Thứ 2
    
    print("Loading all data...")
    data = load_all_data(config, target_date=today)
    
    forecast = data['forecast']
    
    # Replicate brand_to_base logic
    brand_to_base = {}
    for fc in forecast:
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
                
    print("\nMapping verification:")
    for code in ['HT11', 'HT13S', 'HG17S', 'HG16XS34', 'HG17SXS34']:
        print(f"{code} -> base: {brand_to_base.get(code)}")

    # Let's see if they are in silo_plan or bacang for Monday (which corresponds to tomorrow = Tuesday, day_of_week + 1 = 2)
    tomorrow = 2
    print(f"\nTomorrow (Day {tomorrow}) demands in Silo Plan:")
    for prod, tons in data['silo_plan'].get(tomorrow, {}).items():
        if prod in ['HT11', 'HT13S', 'HG17S', 'HG16XS34', 'HG17SXS34'] or '551' in prod or '553' in prod:
            print(f"  {prod}: {tons} tons")
            
    print(f"\nTomorrow (Day {tomorrow}) demands in Ba Cang:")
    for prod, tons in data['bacang'].get(tomorrow, {}).items():
        if prod in ['HT11', 'HT13S', 'HG17S', 'HG16XS34', 'HG17SXS34'] or '551' in prod or '553' in prod:
            print(f"  {prod}: {tons} tons")
            
    print("\nRunning calculate_daily_demand...")
    demand_list = calculate_daily_demand(
        today_date=today,
        day_of_week=day_of_week,
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
        adjustments=data.get('adjustments'),
    )
    
    print("\nChecking generated DemandItem for HT11/551, HT13S/553S, etc.:")
    for item in demand_list:
        if item.product_code in ['HT11', 'HT13S', 'HG17S', 'HG16XS34', 'HG17SXS34', '551', '553S', '567S', '566XS34', '567SXS34']:
            print(f"  Code: {item.product_code} | Tons: {item.tons} | Silo: {item.silo_truck} | Source: {item.source} | Brand Demands: {getattr(item, 'brand_demands', {})}")

if __name__ == '__main__':
    main()
