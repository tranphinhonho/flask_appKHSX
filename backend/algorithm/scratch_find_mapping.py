import openpyxl
from data_loader import load_forecast

forecast_file = r"D:\Kê hoạch sản xuât\FORECAST\W21.(18-23-05-) SALEFORECAST 2026.xlsx"
forecast = load_forecast(forecast_file)

# Recreate the brand_to_base construction from demand_calculator.py
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

print(f"Total mappings: {len(brand_to_base)}")
print("Mappings for 551:")
for k, v in brand_to_base.items():
    if v == '551':
        print(f"  {k} -> {v} ({brand_info[k]})")

print("\nHG16 or HG17 mappings:")
for k, v in brand_to_base.items():
    if "HG16" in k or "HG17" in k or "XS34" in k or "566" in v or "567" in v:
        print(f"  {k} -> {v} ({brand_info.get(k, 'N/A')})")
