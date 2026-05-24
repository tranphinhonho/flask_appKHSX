import os
import sys
sys.path.insert(0, r"D:\Kê hoạch sản xuât\laptrinh vao")
import config
from data_loader import _find_latest_file, load_forecast, load_silo_plan, load_bacang

with open("scratch_debug2.txt", "w", encoding="utf-8") as f:
    silo_file = _find_latest_file(config.SILO_DIR, '*SILO*.xlsx')
    f.write(f"Silo file: {silo_file}\n")
    silo_plan = load_silo_plan(silo_file)
    f.write("\nSilo Plan raw loaded:\n")
    for d, p_map in silo_plan.items():
        f.write(f"Day {d}: {p_map}\n")

    bacang_file = _find_latest_file(config.BACANG_DIR, '*CANG*.xlsx')
    f.write(f"Ba Cang file: {bacang_file}\n")
    bacang = load_bacang(bacang_file)
    f.write("\nBa Cang raw loaded:\n")
    for d, p_map in bacang.items():
        f.write(f"Day {d}: {p_map}\n")
