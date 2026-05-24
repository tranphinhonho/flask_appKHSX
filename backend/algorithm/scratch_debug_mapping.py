import os
import sys
from data_loader import load_forecast, _find_latest_file

def main():
    forecast_dir = r'D:\Kê hoạch sản xuât\FORECAST'
    forecast_file = _find_latest_file(forecast_dir, '*SALEFORECAST*.xlsx')
    if not forecast_file:
        print("Forecast file not found!")
        return
        
    forecast = load_forecast(forecast_file)
    print(f"Loaded {len(forecast)} forecast items.")
    
    print("\n--- MAPPING TABLE FROM FORECAST SHEET ---")
    print(f"{'Formular':<10} | {'Base':<12} | {'HIGRO':<10} | {'CP':<10} | {'STAR':<10} | {'NUVO':<10} | {'NASA':<10} | {'FARM':<10}")
    print("-" * 95)
    for fc in forecast:
        # We need to find the formular_code, wait, ForecastItem has no formular_code stored,
        # but let's print the base and brand codes we loaded.
        print(f"{fc.product_code:<12} | {fc.feed_code_higro or '':<10} | {fc.feed_code_cp or '':<10} | {fc.feed_code_star or '':<10} | {fc.feed_code_nuvo or '':<10} | {fc.feed_code_nasa or '':<10} | {fc.feed_code_farm or '':<10}")

if __name__ == '__main__':
    main()
