"""
packaging_allocator.py - Phân bổ bao bì theo tỷ lệ Forecast kết hợp quy tắc nhà máy
C.P. Vietnam - Chi nhánh Bình Dương

QUY TẮC CỐT LÕI:
  - Cám trại (Farm) chắc chắn 100% đóng vào bao WHITE BAG 50kg.
  - Cám đại lý (Dealer) không bao giờ sử dụng bao trắng, chỉ đóng bao thương hiệu tương ứng (Higro, CP, Star, Nuvo, Nasa, Bell) theo quy cách 25kg hoặc 40kg.
  - Mỗi dòng KHSX có thể vừa SILO vừa đóng bao.
  - Tấn SILO đã được gán sẵn (item.silo_truck) từ demand_calculator.
  - Phần đóng bao = Tổng tấn - SILO tấn.
"""
from models import DemandItem, ForecastItem


def _build_forecast_lookup(forecast):
    """
    Tạo dict lookup: {product_code → ForecastItem}
    Ưu tiên dòng có dealer_total > 0
    """
    lookup = {}
    for fc in forecast:
        code = fc.product_code
        if code not in lookup:
            lookup[code] = fc
        elif fc.dealer_total > (lookup[code].dealer_total or 0):
            lookup[code] = fc
    return lookup


def _find_forecast(product_code, fc_lookup):
    """Tìm ForecastItem, thử exact match rồi prefix match"""
    if product_code in fc_lookup:
        return fc_lookup[product_code]
    # Prefix match
    for key, val in fc_lookup.items():
        if product_code.startswith(key) or key.startswith(product_code):
            return val
    return None


def _detect_brand_and_packing_fallback(product_code):
    """
    Tự động nhận diện thương hiệu, quy cách đóng bao và kênh phân phối (Farm/Dealer)
    dựa trên quy luật đặt tên mã cám của nhà máy C.P. Bình Dương khi không có Forecast.
    
    Returns:
        is_farm: bool
        brand: str ('CP', 'HIGRO', 'STAR', 'NUVO', 'NASA', 'BELL')
        packing_size: str ('25', '40', '50')
    """
    p_code = str(product_code).strip().upper()
    
    # 1. Nhận diện kênh phân phối (Farm vs Dealer)
    # Các dòng cám có hậu tố F, SF, FS, GPF, ANF, PF... đại diện cho Farm
    is_farm = False
    farm_keywords = ['SF', 'FS', 'ANF', 'GPF', 'PF']
    if p_code.endswith('F') or any(kw in p_code for kw in farm_keywords):
        is_farm = True
        
    # 2. Nhận diện thương hiệu (Brand) dựa trên hậu tố/tên mã
    brand = 'CP'  # Mặc định là C.P.
    
    if any(p_code.startswith(pre) for pre in ['HT', 'HS', 'VT', 'VD', 'CD', 'GD', 'ST', 'HG1']) or 'STAR' in p_code:
        brand = 'STAR'
    elif 'HIGRO' in p_code or p_code.endswith('H') or 'HG' in p_code:
        brand = 'HIGRO'
    elif 'NUVO' in p_code or 'NV' in p_code or p_code.startswith('96'):
        brand = 'NUVO'
    elif 'NASA' in p_code or 'NS' in p_code:
        brand = 'NASA'
    elif 'BELL' in p_code or p_code.endswith('B'):
        # Loại trừ mã 511B (đại lý CP)
        if p_code == '511B':
            brand = 'CP'
        else:
            brand = 'BELL'
    elif p_code.endswith('S'):
        # Loại trừ hậu tố 'S' trong '567S' (nái đại lý)
        if p_code.startswith('567S') and not 'SF' in p_code:
            brand = 'CP'
        else:
            brand = 'STAR'
            
    # 3. Nhận diện quy cách đóng gói (Packing Size)
    packing_size = '25'  # Mặc định bao đại lý 25kg
    
    if is_farm:
        packing_size = '50'  # 100% cám trại đóng bao 50kg
    else:
        # Cám đại lý: kiểm tra xem có chỉ định 40kg không
        if '40' in p_code:
            packing_size = '40'
            
    return is_farm, brand, packing_size


def _allocate_brand_direct(item, tons, brand, packing_size):
    """Gán trực tiếp tấn đóng bao vào thương hiệu đại lý tương ứng"""
    p_size = str(packing_size).strip()
    val = round(tons, 1)
    
    if p_size == '40':
        if brand == 'HIGRO': item.higro_40 = val
        elif brand == 'CP': item.cp_40 = val
        elif brand == 'STAR': item.star_40 = val
        elif brand == 'NUVO': item.nuvo_40 = val
        elif brand == 'NASA': item.nasa_40 = val
        elif brand == 'BELL': item.bell_40 = val
        else: item.cp_40 = val
    else:  # Mặc định bao 25kg
        if brand == 'HIGRO': item.higro_25 = val
        elif brand == 'CP': item.cp_25 = val
        elif brand == 'STAR': item.star_25 = val
        elif brand == 'NUVO': item.nuvo_25 = val
        elif brand == 'NASA': item.nasa_25 = val
        elif brand == 'BELL': item.bell_25 = val
        else: item.cp_25 = val


def _add_to_brand_column(item, tons, brand, packing_size):
    """Cộng thêm tấn đóng bao vào thương hiệu và quy cách tương ứng"""
    p_size = str(packing_size).strip()
    val = round(tons, 1)
    
    if brand == 'WHITE BAG':
        if p_size == '50': item.white_bag_50 = round((item.white_bag_50 or 0.0) + val, 1)
        elif p_size == '40': item.white_bag_40 = round((item.white_bag_40 or 0.0) + val, 1)
        else: item.white_bag_25 = round((item.white_bag_25 or 0.0) + val, 1)
    elif p_size == '40':
        if brand == 'HIGRO': item.higro_40 = round((item.higro_40 or 0.0) + val, 1)
        elif brand == 'CP': item.cp_40 = round((item.cp_40 or 0.0) + val, 1)
        elif brand == 'STAR': item.star_40 = round((item.star_40 or 0.0) + val, 1)
        elif brand == 'NUVO': item.nuvo_40 = round((item.nuvo_40 or 0.0) + val, 1)
        elif brand == 'NASA': item.nasa_40 = round((item.nasa_40 or 0.0) + val, 1)
        elif brand == 'BELL': item.bell_40 = round((item.bell_40 or 0.0) + val, 1)
        else: item.cp_40 = round((item.cp_40 or 0.0) + val, 1)
    else:  # Mặc định bao 25kg
        if brand == 'HIGRO': item.higro_25 = round((item.higro_25 or 0.0) + val, 1)
        elif brand == 'CP': item.cp_25 = round((item.cp_25 or 0.0) + val, 1)
        elif brand == 'STAR': item.star_25 = round((item.star_25 or 0.0) + val, 1)
        elif brand == 'NUVO': item.nuvo_25 = round((item.nuvo_25 or 0.0) + val, 1)
        elif brand == 'NASA': item.nasa_25 = round((item.nasa_25 or 0.0) + val, 1)
        elif brand == 'BELL': item.bell_25 = round((item.bell_25 or 0.0) + val, 1)
        else: item.cp_25 = round((item.cp_25 or 0.0) + val, 1)


BRAND_ATTRS = {
    ('HIGRO', '25'): 'higro_25',
    ('CP', '25'): 'cp_25',
    ('STAR', '25'): 'star_25',
    ('NUVO', '25'): 'nuvo_25',
    ('NASA', '25'): 'nasa_25',
    ('BELL', '25'): 'bell_25',
    ('HIGRO', '40'): 'higro_40',
    ('CP', '40'): 'cp_40',
    ('STAR', '40'): 'star_40',
    ('NUVO', '40'): 'nuvo_40',
    ('NASA', '40'): 'nasa_40',
    ('BELL', '40'): 'bell_40',
    ('WHITE BAG', '25'): 'white_bag_25',
    ('WHITE BAG', '40'): 'white_bag_40',
    ('WHITE BAG', '50'): 'white_bag_50',
}


def _resolve_replacement_brand_and_packing(repl_brand, packing_size):
    brand_upper = str(repl_brand).strip().upper()
    if brand_upper in {'WHITE BAG', 'WHITE_BAG', 'TRANG', 'TRẮNG', 'WHITE'}:
        # Bao trắng (WHITE BAG) luôn luôn là 50kg — nhà máy không có bao trắng 25kg hay 40kg
        return 'WHITE BAG', '50'
        
    # Check if it matches a standard brand
    for b in ['HIGRO', 'CP', 'STAR', 'NUVO', 'NASA', 'BELL']:
        if b in brand_upper:
            return b, packing_size
            
    # Otherwise, it might be a product code, detect its brand
    _, detected_brand, detected_packing = _detect_brand_and_packing_fallback(repl_brand)
    return detected_brand, detected_packing


def allocate_packaging(demand_list, forecast, adjustments=None):
    """
    Phân bổ bao bì cho từng DemandItem theo quy định nghiêm ngặt:
      - Cám trại (Farm) -> 100% WHITE BAG 50kg
      - Cám đại lý (Dealer) -> Quy trình 2 bước:
        * Bước A: Phân bổ trực tiếp theo đơn đặt hàng thực tế (Bá Cang, Walkin) thông qua `brand_demands`.
        * Bước B: Phân bổ phần chênh lệch còn lại dựa trên tỷ lệ Forecast tuần (hoặc JSON lịch sử / Fallback).
        * Bước C: Sửa sai số làm tròn để đảm bảo tổng bao bì khớp 100% lượng tấn đóng bao.
    """
    import json
    import os
    
    fc_lookup = _build_forecast_lookup(forecast)
    
    # Tải quy tắc bao bì lịch sử từ JSON
    historical_rules = {}
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'extracted_packaging_rules.json')
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                historical_rules = json.load(f)
            print(f"  📂 Tải thành công {len(historical_rules)} quy tắc đóng bao từ extracted_packaging_rules.json")
        except Exception as ex:
            print(f"  ⚠️ Lỗi đọc file quy tắc bao bì lịch sử: {ex}")
    else:
        print(f"  ⚠️ Không tìm thấy file {json_path}. Sẽ sử dụng phân bổ fallback mặc định.")
    
    print(f"\n{'─'*50}")
    print(f"📦 PHÂN BỔ BAO BÌ THEO QUY TẮC NHÀ MÁY (NÂNG CẤP 2 BƯỚC)")
    print(f"  - Cám trại -> WHITE BAG 50kg")
    print(f"  - Cám đại lý -> Phân bổ trực tiếp theo brand_demands + Forecast phần dư")
    print(f"{'─'*50}")
    
    allocated = 0
    silo_only = 0
    mixed = 0
    direct_allocated_count = 0
    forecast_ratio_allocated_count = 0
    historical_allocated = 0
    fallback_allocated = 0
    
    for item in demand_list:
        silo_tons = item.silo_truck or 0.0
        bag_tons = item.tons - silo_tons  # Phần cần đóng bao
        
        # ─── TRƯỜNG HỢP 1: 100% SILO (không đóng bao) ───
        if bag_tons <= 0.01:
            item.silo_truck = item.tons
            item.packing_size = 'SILO'
            silo_only += 1
            allocated += 1
            continue
        
        # ─── TRƯỜNG HỢP 2: Có đóng bao ───
        if silo_tons > 0:
            mixed += 1
            
        # Tự động phân tích sản phẩm (fallback)
        is_farm_code, detected_brand, detected_packing = _detect_brand_and_packing_fallback(item.product_code)
        
        fc = _find_forecast(item.product_code, fc_lookup)
        
        # Quyết định kênh phân phối tuyệt đối dựa trên is_farm_code
        if is_farm_code:
            # CÁM TRẠI: 100% vào bao WHITE BAG 50kg
            item.white_bag_50 = round(bag_tons, 1)
            item.packing_size = '50'
            
            # Đảm bảo các cột bao đại lý và bao trắng khác đều bằng 0
            item.white_bag_25 = 0.0
            item.white_bag_40 = 0.0
            item.higro_25 = 0.0; item.higro_40 = 0.0
            item.cp_25 = 0.0; item.cp_40 = 0.0
            item.star_25 = 0.0; item.star_40 = 0.0
            item.nuvo_25 = 0.0; item.nuvo_40 = 0.0
            item.nasa_25 = 0.0; item.nasa_40 = 0.0
            item.bell_25 = 0.0; item.bell_40 = 0.0
        else:
            # CÁM ĐẠI LÝ: Tuyệt đối không bao trắng, chỉ bao thương hiệu
            item.white_bag_25 = 0.0
            item.white_bag_40 = 0.0
            item.white_bag_50 = 0.0
            
            # Xác định packing size đại lý (25 hoặc 40)
            dealer_packing = detected_packing
            if fc and fc.packing_size:
                if fc.packing_size in {'25', '40'}:
                    dealer_packing = fc.packing_size
            item.packing_size = dealer_packing
            
            # Khởi tạo các cột bao thương hiệu về 0
            item.higro_25 = 0.0; item.higro_40 = 0.0
            item.cp_25 = 0.0; item.cp_40 = 0.0
            item.star_25 = 0.0; item.star_40 = 0.0
            item.nuvo_25 = 0.0; item.nuvo_40 = 0.0
            item.nasa_25 = 0.0; item.nasa_40 = 0.0
            item.bell_25 = 0.0; item.bell_40 = 0.0
            
            # ───────── BƯỚC A: PHÂN BỔ TRỰC TIẾP TỪ ĐƠN HÀNG THỰC TẾ ─────────
            # Chỉ áp dụng khi brand_demands chứa mã brand thực tế (khác base code)
            # Nếu chỉ chứa base code → để Bước B (Forecast ratio) phân bổ chính xác hơn
            brand_demands = getattr(item, 'brand_demands', {})
            allocated_from_orders = 0.0
            
            # Lọc: chỉ phân bổ trực tiếp cho các đơn có mã brand cụ thể
            has_real_brand_orders = any(k != item.product_code for k in brand_demands.keys())
            
            if brand_demands and has_real_brand_orders:
                print(f"  🔍 Phát hiện brand_demands cho mã cám nền '{item.product_code}': {brand_demands}")
                for orig_prod, orig_tons in brand_demands.items():
                    if orig_tons <= 0.01:
                        continue
                    
                    # Skip base code entries → sẽ được xử lý ở Bước B
                    if orig_prod == item.product_code:
                        continue
                    
                    # Phân tích mã cám gốc (như HT11) để nhận diện thương hiệu và quy cách bao
                    orig_is_farm, orig_brand, orig_packing = _detect_brand_and_packing_fallback(orig_prod)
                    
                    if orig_is_farm:
                        orig_brand = 'WHITE BAG'
                        orig_packing = '50'
                    
                    # Giới hạn lượng phân bổ để không vượt quá bag_tons
                    tons_to_alloc = min(orig_tons, bag_tons - allocated_from_orders)
                    if tons_to_alloc <= 0.01:
                        break
                        
                    _add_to_brand_column(item, tons_to_alloc, orig_brand, orig_packing)
                    allocated_from_orders += tons_to_alloc
                    direct_allocated_count += 1
                    print(f"    * Phân bổ trực tiếp từ đơn '{orig_prod}' ➔ {orig_brand} {orig_packing}kg: {tons_to_alloc:.1f} Tấn")
            
            # ───────── BƯỚC B: PHÂN BỔ PHẦN CHÊNH LỆCH CÒN LẠI ─────────
            remaining_tons = bag_tons - allocated_from_orders
            if remaining_tons > 0.01:
                # 1. Phân bổ theo Forecast tỷ lệ tuần nếu có dealer_total > 0
                fc_dealer_tons = fc.dealer_total if (fc and fc.dealer_total) else 0.0
                if fc and fc_dealer_tons > 0.01:
                    val_higro = remaining_tons * (fc.dealer_higro or 0) / fc_dealer_tons
                    val_cp = remaining_tons * (fc.dealer_cp or 0) / fc_dealer_tons
                    val_star = remaining_tons * (fc.dealer_star or 0) / fc_dealer_tons
                    val_nuvo = remaining_tons * (fc.dealer_nuvo or 0) / fc_dealer_tons
                    val_nasa = remaining_tons * (fc.dealer_nasa or 0) / fc_dealer_tons
                    
                    _add_to_brand_column(item, val_higro, 'HIGRO', dealer_packing)
                    _add_to_brand_column(item, val_cp, 'CP', dealer_packing)
                    _add_to_brand_column(item, val_star, 'STAR', dealer_packing)
                    _add_to_brand_column(item, val_nuvo, 'NUVO', dealer_packing)
                    _add_to_brand_column(item, val_nasa, 'NASA', dealer_packing)
                    forecast_ratio_allocated_count += 1
                    print(f"    * Phân bổ phần dư {remaining_tons:.1f} Tấn theo tỷ lệ Forecast của nền '{item.product_code}'")
                
                # 2. Phân bổ theo quy tắc lịch sử trong JSON
                elif item.product_code in historical_rules:
                    rules = historical_rules[item.product_code]
                    brand_rules = {}
                    total_brand_tons = 0.0
                    
                    brand_map_keys = {
                        'HIGRO 25kg': ('HIGRO', '25'),
                        'CP 25kg': ('CP', '25'),
                        'STAR 25kg': ('STAR', '25'),
                        'NUVO 25kg': ('NUVO', '25'),
                        'NASA 25kg': ('NASA', '25'),
                        'BELL 25kg': ('BELL', '25'),
                        'HIGRO 40kg': ('HIGRO', '40'),
                        'CP 40kg': ('CP', '40'),
                        'STAR 40kg': ('STAR', '40'),
                        'NUVO 40kg': ('NUVO', '40'),
                        'NASA 40kg': ('NASA', '40'),
                        'BELL 40kg': ('BELL', '40'),
                    }
                    
                    for k, v in rules.items():
                        if k in brand_map_keys and v > 0:
                            brand_rules[k] = v
                            total_brand_tons += v
                            
                    if total_brand_tons > 0.01:
                        historical_allocated += 1
                        for k, v in brand_rules.items():
                            brand, size = brand_map_keys[k]
                            val = remaining_tons * v / total_brand_tons
                            _add_to_brand_column(item, val, brand, size)
                        print(f"    * Phân bổ phần dư {remaining_tons:.1f} Tấn theo tỷ lệ JSON lịch sử")
                    else:
                        # Fallback direct
                        _add_to_brand_column(item, remaining_tons, detected_brand, dealer_packing)
                        fallback_allocated += 1
                        print(f"    * Phân bổ phần dư {remaining_tons:.1f} Tấn theo Fallback tên mã ➔ {detected_brand} {dealer_packing}kg")
                else:
                    # Fallback direct
                    _add_to_brand_column(item, remaining_tons, detected_brand, dealer_packing)
                    fallback_allocated += 1
                    print(f"    * Phân bổ phần dư {remaining_tons:.1f} Tấn theo Fallback tên mã ➔ {detected_brand} {dealer_packing}kg")
            
            # ───────── BƯỚC C: SỬA LỖI LÀM TRÒN ĐỂ KHỚP 100% ─────────
            total_packed = (
                item.higro_25 + item.higro_40 +
                item.cp_25 + item.cp_40 +
                item.star_25 + item.star_40 +
                item.nuvo_25 + item.nuvo_40 +
                item.nasa_25 + item.nasa_40 +
                item.bell_25 + item.bell_40
            )
            diff = bag_tons - total_packed
            if abs(diff) > 0.01:
                # Tìm thương hiệu có lượng phân bổ lớn nhất hiện tại để bù vào
                brand_allocations = {
                    'HIGRO': item.higro_25 if dealer_packing == '25' else item.higro_40,
                    'CP': item.cp_25 if dealer_packing == '25' else item.cp_40,
                    'STAR': item.star_25 if dealer_packing == '25' else item.star_40,
                    'NUVO': item.nuvo_25 if dealer_packing == '25' else item.nuvo_40,
                    'NASA': item.nasa_25 if dealer_packing == '25' else item.nasa_40,
                    'BELL': item.bell_25 if dealer_packing == '25' else item.bell_40,
                }
                
                # Sắp xếp thương hiệu có lượng phân bổ giảm dần
                sorted_brands = sorted(brand_allocations.items(), key=lambda x: x[1], reverse=True)
                target_brand = sorted_brands[0][0]
                
                # Nếu tất cả các thương hiệu đều bằng 0, bù vào detected_brand mặc định
                if sorted_brands[0][1] <= 0.01:
                    target_brand = detected_brand
                    
                _add_to_brand_column(item, diff, target_brand, dealer_packing)
                print(f"    * Bù sai số làm tròn {diff:+.2f} Tấn vào cột '{target_brand.lower()}_{dealer_packing}'")
                
        allocated += 1
        
    # ─── BƯỚC D: ÁP DỤNG THAY THẾ BAO BÌ ĐỘT XUẤT (THAY_THE_BAO_BI) ───
    bag_substitutions = adjustments.get('bag_substitutions', {}) if adjustments else {}
    if bag_substitutions:
        print(f"\n🎒 ÁP DỤNG THAY THẾ BAO BÌ ĐỘT XUẤT:")
        for product, rules in bag_substitutions.items():
            target_items = [it for it in demand_list if it.product_code == product]
            if not target_items:
                continue
                
            for item in target_items:
                print(f"  - Áp dụng thay thế bao bì cho mã cám {product}:")
                for orig_brand, repl_brand in rules.items():
                    print(f"    + Đổi từ bao bì '{orig_brand}' ➔ '{repl_brand}'")
                    
                    current_values = {}
                    for (brand, size), attr in BRAND_ATTRS.items():
                        val = getattr(item, attr, 0.0)
                        if val > 0.01:
                            current_values[(brand, size)] = val
                            
                    for (brand, size), val in current_values.items():
                        match = False
                        if orig_brand == 'ALL' or orig_brand == '*':
                            match = True
                        elif orig_brand == brand:
                            match = True
                        elif orig_brand == product:
                            match = True
                        elif orig_brand in BRAND_ATTRS:
                            match = True
                            
                        if match:
                            old_attr = BRAND_ATTRS[(brand, size)]
                            setattr(item, old_attr, 0.0)
                            
                            target_brand, target_size = _resolve_replacement_brand_and_packing(repl_brand, size)
                            new_key = (target_brand, target_size)
                            if new_key in BRAND_ATTRS:
                                new_attr = BRAND_ATTRS[new_key]
                                current_new_val = getattr(item, new_attr, 0.0)
                                setattr(item, new_attr, round(current_new_val + val, 1))
                                print(f"      * Chuyển {val:.1f}T từ '{old_attr}' ➔ '{new_attr}'")
                                if target_size != item.packing_size:
                                    item.packing_size = target_size
                            else:
                                print(f"      ⚠️ Cảnh báo: Không tìm thấy cột cho bao bì '{target_brand}' quy cách '{target_size}'")
                                
    print(f"  ✅ Phân bổ thành công: {allocated} sản phẩm.")
    print(f"     100% SILO: {silo_only} | Vừa SILO vừa bao: {mixed} | Chỉ đóng bao: {allocated - silo_only - mixed}")
    print(f"     Thống kê phân bổ đại lý: {direct_allocated_count} lượt Đơn trực tiếp | {forecast_ratio_allocated_count} lượt Forecast | {historical_allocated} lượt JSON | {fallback_allocated} lượt Fallback")

