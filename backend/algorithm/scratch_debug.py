import os
import sys
sys.path.insert(0, r"D:\Kê hoạch sản xuât\laptrinh vao")
import config
from data_loader import _find_latest_file, load_forecast, load_silo_plan, load_bacang

with open("scratch_debug.txt", "w", encoding="utf-8") as f:
    forecast_file = _find_latest_file(config.FORECAST_DIR, '*FORECAST*.xlsx')
    f.write(f"Forecast file: {forecast_file}\n")
    forecast = load_forecast(forecast_file)

    f.write("\nFirst 30 forecast items:\n")
    for i, fc in enumerate(forecast[:30]):
        f.write(f"{i+1}. Product code: {fc.product_code} | Formular: {fc.feed_code_higro} | CP: {fc.feed_code_cp} | STAR: {fc.feed_code_star} | NUVO: {fc.feed_code_nuvo}\n")

    f.write("\nAll brand codes to base codes mapping in calculate_daily_demand:\n")
    brand_to_base = {}
    brand_info = {}
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
                brand_info[c] = (brand, fc.packing_size)

    f.write(f"HT11 mapped to: {brand_to_base.get('HT11')}\n")
    f.write(f"951 mapped to: {brand_to_base.get('951')}\n")
    f.write(f"9651 mapped to: {brand_to_base.get('9651')}\n")
    f.write(f"551 mapped to: {brand_to_base.get('551')}\n")
