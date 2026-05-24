"""
demand_calculator.py - Tính nhu cầu sản xuất hàng ngày theo 4 mức ưu tiên

QUY TẮC QUAN TRỌNG:
  - Mỗi mã cám chỉ xuất hiện 1 LẦN trong KHSX
  - Nếu cùng mã cám vừa SILO vừa đóng bao → gộp thành 1 dòng
  - SILO tấn và bao bì tấn nằm cùng 1 dòng
"""
import math
from models import Priority, DemandItem, ForecastItem


def _get_ton_per_batch(product_code, congsuat, quick_adjust_tpb=None):
    """Lấy trọng lượng mẻ từ bảng công suất kết hợp quy tắc nhà máy"""
    prod_upper = str(product_code).strip().upper()
    # Quy tắc cứng của nhà máy: họ 550, 551 và mã 325F chạy mẻ 8.0 tấn
    if prod_upper == '325F' or prod_upper.startswith('550') or prod_upper.startswith('551'):
        return 8.0
    return 8.4



def _get_available(product_code, ffstock, tonbon):
    """Tính tổng hàng có sẵn (tồn kho + tồn bồn)"""
    stock = ffstock.get(product_code, 0)
    bon = tonbon.get(product_code, 0)
    return stock + bon


def calculate_daily_demand(today_date, day_of_week, forecast, silo_plan, bacang,
                           walkin_orders, ffstock, tonbon, khsx_yesterday,
                           congsuat, produced_this_week=None, ffstock_details=None,
                           adjustments=None):
    """
    Tính nhu cầu sản xuất cho ngày hôm nay.
    
    QUY TẮC GỘP:
      Mỗi mã cám chỉ có 1 dòng duy nhất. Nếu 552SF cần cả SILO (250 tấn)
      lẫn Forecast (170 tấn đóng bao), thì gộp thành 1 dòng:
        552SF | 50 mẻ | 420 tấn | WH50=170 | SILO=250
    
    Priority được gán theo nguồn cao nhất:
      SILO_BACANG > WALKIN > SHORTFALL > FORECAST
    """
    if produced_this_week is None:
        produced_this_week = {}
        
    substitutions = adjustments.get('substitutions', {}) if adjustments else {}
    cancellations = adjustments.get('cancellations', {}) if adjustments else {}
    additions = adjustments.get('additions', []) if adjustments else []
    
    # ─── BƯỚC A: ÁP DỤNG THAY THẾ MÃ CÁM ĐỘT XUẤT ───
    def _sub_code(code):
        c = str(code).strip().upper()
        return substitutions.get(c, c)
        
    if substitutions:
        print(f"\n🔄 ÁP DỤNG THAY THẾ MÃ CÁM ĐỘT XUẤT:")
        for old, new in substitutions.items():
            print(f"  - Thay thế {old} ➔ {new}")
            
        # Áp dụng thay thế cho additions và cancellations để đồng bộ
        for add in additions:
            add['product_code'] = _sub_code(add['product_code'])
        cancellations = { _sub_code(k): v for k, v in cancellations.items() }
            
        # 1. Thay thế trong forecast
        for fc in forecast:
            fc.product_code = _sub_code(fc.product_code)
            
        # 2. Thay thế trong silo_plan
        new_silo_plan = {}
        for d, p_map in silo_plan.items():
            new_silo_plan[d] = {}
            for prod, tons in p_map.items():
                new_prod = _sub_code(prod)
                new_silo_plan[d][new_prod] = new_silo_plan[d].get(new_prod, 0.0) + tons
        silo_plan = new_silo_plan
        
        # 3. Thay thế trong bacang
        new_bacang = {}
        for d, p_map in bacang.items():
            new_bacang[d] = {}
            for prod, tons in p_map.items():
                new_prod = _sub_code(prod)
                new_bacang[d][new_prod] = new_bacang[d].get(new_prod, 0.0) + tons
        bacang = new_bacang
        
        # 4. Thay thế trong walkin_orders
        for order in (walkin_orders or []):
            if 'product' in order:
                order['product'] = _sub_code(order['product'])
                
        # 5. Thay thế trong ffstock
        new_ffstock = {}
        for prod, tons in ffstock.items():
            new_prod = _sub_code(prod)
            new_ffstock[new_prod] = new_ffstock.get(new_prod, 0.0) + tons
        ffstock = new_ffstock
        
        # 6. Thay thế trong tonbon
        new_tonbon = {}
        for prod, tons in tonbon.items():
            new_prod = _sub_code(prod)
            new_tonbon[new_prod] = new_tonbon.get(new_prod, 0.0) + tons
        tonbon = new_tonbon
        
        # 7. Thay thế trong khsx_yesterday
        new_yesterday = {}
        for prod, data_y in (khsx_yesterday or {}).items():
            new_prod = _sub_code(prod)
            if new_prod in new_yesterday:
                new_yesterday[new_prod]['planned'] += data_y.get('planned', 0)
                new_yesterday[new_prod]['actual'] += data_y.get('actual', 0)
                new_yesterday[new_prod]['shortfall'] += data_y.get('shortfall', 0)
                new_yesterday[new_prod]['pct'] = (new_yesterday[new_prod]['actual'] / new_yesterday[new_prod]['planned'] * 100.0) if new_yesterday[new_prod]['planned'] > 0 else 0.0
            else:
                new_yesterday[new_prod] = data_y.copy()
        khsx_yesterday = new_yesterday
        
        # 8. Thay thế trong ffstock_details
        if ffstock_details:
            new_details = {}
            for prod, details in ffstock_details.items():
                new_prod = _sub_code(prod)
                new_details[new_prod] = details
            ffstock_details = new_details

    # ─── BƯỚC A2: XÂY DỰNG MAPPING ĐỘNG TỪ FORECAST QUY ĐỔI VỀ CÁM NỀN ───
    brand_to_base = {}
    brand_info = {}  # {code: (brand, packing_size)}
    
    for fc in forecast:
        base = fc.product_code
        # Các cột thương hiệu
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
                
    def _get_base_code(code):
        c = str(code).strip().upper()
        # Áp dụng sub_code trước rồi mới quy đổi về base
        c_sub = _sub_code(c)
        if c_sub in brand_to_base:
            return brand_to_base[c_sub]
            
        # Systematic prefix translation rules for brand codes
        # 1. NUVO (starts with 96 and length >= 4)
        if c_sub.startswith('96') and len(c_sub) >= 4:
            return '5' + c_sub[2:]
            
        # 2. NUVO/CP/STAR special 94 (like 9401 -> 301)
        if c_sub.startswith('94') and len(c_sub) >= 4:
            return '3' + c_sub[2:]
            
        # 3. STAR HT1 -> 55
        if c_sub.startswith('HT1'):
            return '55' + c_sub[3:]
            
        # 4. STAR HS1 -> 550S (special case HS11 -> 550S)
        if c_sub == 'HS11':
            return '550S'
        if c_sub.startswith('HS1'):
            return '550S' + c_sub[3:]
            
        # 5. STAR HG1 -> 56
        if c_sub.startswith('HG1'):
            return '56' + c_sub[3:]
            
        # 6. STAR VT1 -> 548/549 (VT11 -> 548, VT12 -> 549)
        if c_sub == 'VT11':
            return '548'
        if c_sub == 'VT12':
            return '549'
        if c_sub.startswith('VT1'):
            if c_sub.endswith('1'):
                return '548'
            if c_sub.endswith('2'):
                return '549'
            return '548'
            
        # 7. STAR VD1 -> 54 (like VD14 -> 544)
        if c_sub.startswith('VD1'):
            return '54' + c_sub[3:]
            
        # 8. STAR CD0 -> 30 (like CD01 -> 301)
        if c_sub.startswith('CD0'):
            return '30' + c_sub[3:]
            
        # 9. STAR GD1 -> 52 (like GD14 -> 524)
        if c_sub.startswith('GD1'):
            return '52' + c_sub[3:]
            
        # 10. CP (starts with 9, 3 digits, or 3 digits plus suffix)
        if c_sub.startswith('9') and (len(c_sub) == 3 or (len(c_sub) > 3 and c_sub[3].isalpha())):
            return '5' + c_sub[1:]
            
        # 11. CP (starts with 8, 3 digits, or 3 digits plus suffix)
        if c_sub.startswith('8') and (len(c_sub) == 3 or (len(c_sub) > 3 and c_sub[3].isalpha())):
            return '3' + c_sub[1:]
            
        return c_sub

    # ─── BƯỚC A3: GỘP TỒN KHO & LŨY KẾ VỀ CÁM NỀN CHÍNH ───
    # 1. Tồn kho ffstock
    new_ffstock = {}
    for prod, tons in ffstock.items():
        base_prod = _get_base_code(prod)
        new_ffstock[base_prod] = new_ffstock.get(base_prod, 0.0) + tons
    ffstock = new_ffstock
    
    # 2. Tồn bồn tonbon
    new_tonbon = {}
    for prod, tons in tonbon.items():
        base_prod = _get_base_code(prod)
        new_tonbon[base_prod] = new_tonbon.get(base_prod, 0.0) + tons
    tonbon = new_tonbon
    
    # 3. KHSX hôm qua khsx_yesterday
    new_yesterday = {}
    for prod, data_y in (khsx_yesterday or {}).items():
        base_prod = _get_base_code(prod)
        if base_prod in new_yesterday:
            new_yesterday[base_prod]['planned'] += data_y.get('planned', 0)
            new_yesterday[base_prod]['actual'] += data_y.get('actual', 0)
            new_yesterday[base_prod]['shortfall'] += data_y.get('shortfall', 0)
            new_yesterday[base_prod]['pct'] = (new_yesterday[base_prod]['actual'] / new_yesterday[base_prod]['planned'] * 100.0) if new_yesterday[base_prod]['planned'] > 0 else 0.0
        else:
            new_yesterday[base_prod] = data_y.copy()
    khsx_yesterday = new_yesterday
    
    # 4. Đã sản xuất trong tuần produced_this_week
    new_produced = {}
    for prod, tons in (produced_this_week or {}).items():
        base_prod = _get_base_code(prod)
        new_produced[base_prod] = new_produced.get(base_prod, 0.0) + tons
    produced_this_week = new_produced
    
    # 5. Chi tiết tồn kho ffstock_details (Tính toán lại DOH cám nền chính xác)
    if ffstock_details:
        new_details = {}
        for prod, details in ffstock_details.items():
            base_prod = _get_base_code(prod)
            if base_prod in new_details:
                exist = new_details[base_prod]
                exist['stock_tons'] += details.get('stock_tons', 0.0)
                exist['sales_avg_kg'] += details.get('sales_avg_kg', 0.0)
                if exist['sales_avg_kg'] > 0:
                    exist['doh'] = (exist['stock_tons'] * 1000.0) / exist['sales_avg_kg']
                else:
                    exist['doh'] = 99.0
            else:
                new_details[base_prod] = details.copy()
        ffstock_details = new_details

    # Trích xuất cấu hình ép mẻ & tấn/mẻ
    quick_adjust_batches = {}
    quick_adjust_tpb = {}
    for add in additions:
        prod = add['product_code']
        if add.get('force_batches') is not None:
            quick_adjust_batches[prod] = add['force_batches']
        if add.get('force_tpb') is not None:
            quick_adjust_tpb[prod] = add['force_tpb']
    
    # Dict gộp: product_code → DemandItem
    merged = {}
    
    # ─── BƯỚC A4: XÁC ĐỊNH CÁC MÃ CÁM CHỈ CÓ XE BỒN (SILO-ONLY) TRONG FORECAST ───
    silo_only_products = set()
    all_fc_products = set()
    non_silo_fc_products = set()
    for fc in forecast:
        base = _get_base_code(fc.product_code)
        all_fc_products.add(base)
        if fc.packing_size == 'SILO':
            pass
        else:
            non_silo_fc_products.add(base)
    silo_only_products = all_fc_products - non_silo_fc_products
    if silo_only_products:
        print(f"\n📢 PHÁT HIỆN {len(silo_only_products)} MÃ CÁM CHỈ CÓ XE BỒN (SILO-ONLY) TRONG FORECAST:")
        print(f"  - {', '.join(sorted(silo_only_products))}")
    
    print(f"\n{'─'*50}")
    print(f"📋 TÍNH NHU CẦU SẢN XUẤT - Ngày {today_date.strftime('%d/%m/%Y')}")
    print(f"   Thứ {day_of_week + 1} trong tuần")
    print(f"{'─'*50}")
    
    def _add_demand(product, batches, tons, priority, source, packing_size='25',
                    silo_tons=0.0, original_product=None, original_tons=0.0):
        """Thêm hoặc gộp nhu cầu cho 1 sản phẩm"""
        if original_product is None:
            original_product = product
        if original_tons <= 0.01:
            original_tons = tons
            
        product = str(product).strip().upper()
        original_product = str(original_product).strip().upper()
        
        # Bắt buộc ép quy cách về SILO nếu sản phẩm chỉ có xe bồn (silo-only) trong forecast
        if product in silo_only_products:
            packing_size = 'SILO'
            silo_tons = tons
            
        if product in merged:
            item = merged[product]
            item.batches += batches
            item.tons += tons
            item.silo_truck = (item.silo_truck or 0) + silo_tons
            # Giữ priority cao nhất (số nhỏ hơn = ưu tiên hơn)
            if priority.value < item.priority.value:
                item.priority = priority
                item.source = source
        else:
            merged[product] = DemandItem(
                product_code=product,
                batches=batches,
                tons=tons,
                priority=priority,
                source=source,
                packing_size=packing_size,
                silo_truck=silo_tons,
            )
            
        # Ghi nhận thương hiệu gốc của đơn đặt hàng đóng bao
        # QUAN TRỌNG: Luôn trừ phần silo_tons vì brand_demands chỉ dùng cho phân bổ bao bì
        item = merged[product]
        if not hasattr(item, 'brand_demands'):
            item.brand_demands = {}
            
        # Chỉ ghi nhận phần lượng đóng bao (luôn loại trừ silo_tons)
        orig_bag_tons = max(0.0, original_tons - silo_tons)
            
        if orig_bag_tons > 0.01:
            item.brand_demands[original_product] = item.brand_demands.get(original_product, 0.0) + orig_bag_tons
    
    # ============================================
    # ƯU TIÊN 1: SILO xe bồn + Bá Cang (NGÀY MAI)
    # ============================================
    tomorrow = day_of_week + 1
    if tomorrow > 6:
        tomorrow = 1  # Quay lại Thứ 2 tuần sau
    
    # 1a. SILO xe bồn
    silo_tomorrow = silo_plan.get(tomorrow, {})
    silo_count = 0
    for product_orig, tons_needed in silo_tomorrow.items():
        product = _get_base_code(product_orig)
        available = _get_available(product, ffstock, tonbon)
        needed = max(0, tons_needed - available)
        
        if needed > 0:
            tpb = _get_ton_per_batch(product, congsuat, quick_adjust_tpb)
            if product in quick_adjust_batches:
                batches = quick_adjust_batches[product]
            else:
                batches = math.ceil(needed / tpb)
            actual_tons = batches * tpb
            
            _add_demand(product, batches, actual_tons,
                       Priority.SILO_BACANG, 'SILO',
                       packing_size='SILO',
                       silo_tons=actual_tons,
                       original_product=product_orig,
                       original_tons=actual_tons)
            silo_count += 1
    
    # 1b. Bá Cang
    bacang_tomorrow = bacang.get(tomorrow, {})
    bacang_count = 0
    for product_orig, tons_needed in bacang_tomorrow.items():
        product = _get_base_code(product_orig)
        available = _get_available(product, ffstock, tonbon)
        ap = merged[product].tons if product in merged else 0
        needed = max(0, tons_needed - available - ap)
        
        if needed > 0:
            tpb = _get_ton_per_batch(product, congsuat, quick_adjust_tpb)
            if product in quick_adjust_batches:
                batches = quick_adjust_batches[product]
            else:
                batches = math.ceil(needed / tpb)
            actual_tons = batches * tpb
            
            _add_demand(product, batches, actual_tons,
                       Priority.SILO_BACANG, 'BACANG',
                       packing_size='25',
                       original_product=product_orig,
                       original_tons=actual_tons)
            bacang_count += 1
    
    print(f"  🔴 Ưu tiên 1 - SILO: {silo_count} SP | Bá Cang: {bacang_count} SP")
    
    # ============================================
    # ƯU TIÊN 2: Khách vãng lai
    # ============================================
    walkin_count = 0
    for order in (walkin_orders or []):
        product_orig = order.get('product', '').upper().strip()
        tons_needed = order.get('tons', 0)
        packing = order.get('packing_size', '25')
        
        if not product_orig or tons_needed <= 0:
            continue
            
        product_orig = _sub_code(product_orig)
        product = _get_base_code(product_orig)
        
        available = _get_available(product, ffstock, tonbon)
        ap = merged[product].tons if product in merged else 0
        needed = max(0, tons_needed - available - ap)
        
        if needed > 0:
            tpb = _get_ton_per_batch(product, congsuat, quick_adjust_tpb)
            if product in quick_adjust_batches:
                batches = quick_adjust_batches[product]
            else:
                batches = math.ceil(needed / tpb)
            actual_tons = batches * tpb
            
            _add_demand(product, batches, actual_tons,
                       Priority.WALKIN, 'WALKIN',
                       packing_size=packing,
                       original_product=product_orig,
                       original_tons=actual_tons)
            walkin_count += 1
    
    print(f"  🟠 Ưu tiên 2 - Khách vãng lai: {walkin_count} SP")
    
    # ============================================
    # ƯU TIÊN 3: Bù hàng thiếu hôm qua
    # ============================================
    shortfall_count = 0
    for product, data in (khsx_yesterday or {}).items():
        pct = data.get('pct', 100)
        shortfall = data.get('shortfall', 0)
        
        if pct < 95 and shortfall > 0:
            tpb = _get_ton_per_batch(product, congsuat, quick_adjust_tpb)
            if product in quick_adjust_batches:
                batches = quick_adjust_batches[product]
                actual_tons = batches * tpb
            else:
                actual_tons = shortfall * tpb
                batches = shortfall
            
            _add_demand(product, batches, actual_tons,
                       Priority.SHORTFALL, 'SHORTFALL',
                       original_product=product,
                       original_tons=actual_tons)
            shortfall_count += 1
    
    print(f"  🟡 Ưu tiên 3 - Bù thiếu hôm qua: {shortfall_count} SP")
    
    # ============================================
    # ƯU TIÊN 4 & 5: DOH thấp (Ưu tiên 4) & Forecast (Ưu tiên 5)
    # ============================================
    days_remaining = max(1, 6 - day_of_week + 1)
    forecast_count = 0
    urgent_stockout_count = 0
    ff_details = ffstock_details if ffstock_details is not None else {}
    
    for fc in forecast:
        product = fc.product_code
        total_week = fc.total_with_silo
        
        if total_week <= 0:
            continue
        
        # Đã SX bao nhiêu trong tuần
        produced = produced_this_week.get(product, 0)
        # Đã lên KH trong ngày này (ưu tiên 1-3)
        ap = merged[product].tons if product in merged else 0
        
        # Còn thiếu bao nhiêu
        remaining = total_week - produced - ap
        
        # Mặc định daily_need tính theo Forecast chia đều
        daily_need = max(0.0, remaining / days_remaining) if remaining > 0 else 0.0
        
        # Kiểm tra DOH của sản phẩm trong FFSTOCK
        is_urgent = False
        needed_tons_for_doh = 0.0
        
        if product in ff_details:
            details = ff_details[product]
            doh = details.get('doh', 99.0)
            sales_avg_kg = details.get('sales_avg_kg', 0.0)
            stock_tons = details.get('stock_tons', 0.0)
            
            if doh < 3.0 and sales_avg_kg > 0:
                # Tính lượng cần thiết để đạt DOH = 4.0 ngày an toàn
                target_stock_tons = 4.0 * (sales_avg_kg / 1000.0)
                needed_tons_for_doh = max(0.0, target_stock_tons - stock_tons - ap)
                
                if needed_tons_for_doh > 0 or daily_need > 0:
                    is_urgent = True
        
        if not is_urgent and daily_need <= 0:
            continue
            
        # Tính sản lượng tấn cần sản xuất cuối cùng
        target_tons = max(daily_need, needed_tons_for_doh)
        
        tpb = _get_ton_per_batch(product, congsuat, quick_adjust_tpb)
        if product in quick_adjust_batches:
            batches = quick_adjust_batches[product]
        else:
            batches = math.ceil(target_tons / tpb)
        actual_tons = batches * tpb
        
        if is_urgent:
            # Ưu tiên 4 - Cám đứt hàng khẩn cấp (DOH < 3.0 ngày)
            # Nếu forecast packing = SILO → sản phẩm này chỉ bán xe bồn, gán silo_tons
            fc_silo = actual_tons if fc.packing_size == 'SILO' else 0
            _add_demand(product, batches, actual_tons,
                       Priority.URGENT_STOCKOUT, 'URGENT_STOCKOUT',
                       packing_size=fc.packing_size,
                       silo_tons=fc_silo,
                       original_product=product,
                       original_tons=actual_tons)
            urgent_stockout_count += 1
        else:
            # Ưu tiên 5 - Forecast thông thường
            fc_silo = actual_tons if fc.packing_size == 'SILO' else 0
            _add_demand(product, batches, actual_tons,
                       Priority.FORECAST, 'FORECAST',
                       packing_size=fc.packing_size,
                       silo_tons=fc_silo,
                       original_product=product,
                       original_tons=actual_tons)
            forecast_count += 1
            
    print(f"  ⚠️  Ưu tiên 4 - DOH thấp (<3.0d): {urgent_stockout_count} SP")
    print(f"  🟢 Ưu tiên 5 - Forecast: {forecast_count} SP")
    
    # ============================================
    # BỔ SUNG ĐƠN HÀNG GẤP / ÉP ĐƠN (THEM_MOI_HOAC_SUA)
    # ============================================
    if additions:
        print(f"\n➕ ÁP DỤNG ĐIỀU CHỈNH NHANH (THEM_MOI_HOAC_SUA):")
        for add in additions:
            product_orig = add['product_code']
            tons_needed = add['tons']
            packing = add['packing_size']
            priority_str = add['priority']
            
            product_orig = _sub_code(product_orig)
            product = _get_base_code(product_orig)
            
            p_enum = Priority.FORECAST
            if priority_str in {'SILO', 'BACANG', 'SILO_BACANG'}:
                p_enum = Priority.SILO_BACANG
            elif priority_str == 'WALKIN':
                p_enum = Priority.WALKIN
            elif priority_str == 'SHORTFALL':
                p_enum = Priority.SHORTFALL
            elif priority_str == 'URGENT_STOCKOUT':
                p_enum = Priority.URGENT_STOCKOUT
                
            tpb = _get_ton_per_batch(product, congsuat, quick_adjust_tpb)
            if product in quick_adjust_batches:
                batches = quick_adjust_batches[product]
            else:
                batches = math.ceil(tons_needed / tpb)
            actual_tons = batches * tpb
            
            silo_val = actual_tons if packing == 'SILO' else 0.0
            
            print(f"  - Thêm mới/Điều chỉnh {product_orig} (nền {product}): {actual_tons:.1f} Tấn | {batches} Mẻ | Quy cách: {packing} | Ưu tiên: {priority_str}")
            
            _add_demand(product, batches, actual_tons, p_enum, priority_str,
                       packing_size=packing, silo_tons=silo_val,
                       original_product=product_orig, original_tons=actual_tons)
                       
    # ============================================
    # ÁP DỤNG HỦY ĐƠN HÀNG (HUY_KHSX)
    # ============================================
    if cancellations:
        print(f"\n❌ ÁP DỤNG HỦY ĐƠN HÀNG (HUY_KHSX):")
        for product_orig, type_cancel in cancellations.items():
            product_orig = _sub_code(product_orig)
            product = _get_base_code(product_orig)
            if product in merged:
                if type_cancel == 'ALL':
                    print(f"  - Hủy HOÀN TOÀN mã cám: {product} (gốc: {product_orig})")
                    del merged[product]
                elif type_cancel == 'SILO':
                    print(f"  - Hủy xe bồn (SILO) cho mã cám: {product} (gốc: {product_orig})")
                    item = merged[product]
                    item.silo_truck = 0.0
                    bag_tons = max(0.0, item.tons - item.silo_truck)
                    if bag_tons <= 0.01:
                        del merged[product]
                    else:
                        tpb = _get_ton_per_batch(product, congsuat, quick_adjust_tpb)
                        if product in quick_adjust_batches:
                            item.batches = quick_adjust_batches[product]
                        else:
                            item.batches = math.ceil(bag_tons / tpb)
                        item.tons = item.batches * tpb
                        item.packing_size = '25'
                elif type_cancel == 'BAO':
                    print(f"  - Hủy đóng bao (BAO) cho mã cám: {product} (gốc: {product_orig})")
                    item = merged[product]
                    silo_tons = item.silo_truck or 0.0
                    if silo_tons <= 0.01:
                        del merged[product]
                    else:
                        tpb = _get_ton_per_batch(product, congsuat, quick_adjust_tpb)
                        if product in quick_adjust_batches:
                            item.batches = quick_adjust_batches[product]
                        else:
                            item.batches = math.ceil(silo_tons / tpb)
                        item.tons = item.batches * tpb
                        item.silo_truck = item.tons
                        item.packing_size = 'SILO'

    # ============================================
    # LÀM MỊN TẢI XE BỒN (SILO LOAD SMOOTHING / CAPPING)
    # ============================================
    MAX_SILO_DAILY_TONS = 750.0
    total_silo_tons = sum(item.silo_truck or 0.0 for item in merged.values())
    
    if total_silo_tons > MAX_SILO_DAILY_TONS:
        print(f"\n⚠️ TỔNG SILO ({total_silo_tons:.1f}T) VƯỢT QUÁ GIỚI HẠN CHO PHÉP ({MAX_SILO_DAILY_TONS:.1f}T)")
        print(f"   Tiến hành làm mịn tải silo (Silo Load Smoothing):")
        
        # Lọc các sản phẩm có nhu cầu silo
        silo_items = [item for item in merged.values() if (item.silo_truck or 0.0) > 0.0]
        # Sắp xếp theo thứ tự ưu tiên: Priority giá trị nhỏ hơn (ưu tiên cao hơn) lên trước.
        # Nếu cùng priority, ưu tiên mã cám có silo_truck lớn hơn.
        silo_items.sort(key=lambda x: (x.priority.value, -x.silo_truck))
        
        accumulated_silo = 0.0
        deferred_silo_list = []
        
        for item in silo_items:
            item_silo = item.silo_truck or 0.0
            if accumulated_silo + item_silo <= MAX_SILO_DAILY_TONS:
                accumulated_silo += item_silo
                print(f"  ✅ GIỮ LẠI: {item.product_code} ({item.priority.name}) - {item_silo:.1f}T Silo (Lũy kế: {accumulated_silo:.1f}T)")
            else:
                # Vượt quá giới hạn, tiến hành hoãn (defer)
                deferred_silo_list.append((item.product_code, item_silo, item.priority.name))
                
                # Cập nhật lại sản phẩm: đặt silo_truck về 0
                item.silo_truck = 0.0
                
                # Recalculate tons and batches for this item
                bag_tons = max(0.0, item.tons - item_silo)
                if bag_tons <= 0.01:
                    # Nếu không có nhu cầu đóng bao, xóa hoàn toàn khỏi KHSX ngày hôm nay
                    print(f"  ❌ HOÃN: {item.product_code} ({item.priority.name}) - {item_silo:.1f}T Silo (Silo-only ➔ Xóa khỏi KHSX hôm nay)")
                    del merged[item.product_code]
                else:
                    # Nếu có đóng bao, tính lại batches & tons dựa trên bag_tons
                    tpb = _get_ton_per_batch(item.product_code, congsuat, quick_adjust_tpb)
                    item.batches = math.ceil(bag_tons / tpb)
                    item.tons = item.batches * tpb
                    print(f"  ❌ HOÃN SILO: {item.product_code} ({item.priority.name}) - Giảm từ {item_silo:.1f}T Silo xuống 0T (Chỉ đóng bao: {item.tons:.1f}T, {item.batches} mẻ)")

    # ============================================
    # CHUYỂN SANG LIST + SẮP XẾP
    # ============================================
    demand_list = list(merged.values())
    
    # Sắp xếp theo priority rồi theo tấn giảm dần
    demand_list.sort(key=lambda x: (x.priority.value, -x.tons))
    
    total_tons = sum(item.tons for item in demand_list)
    total_batches = sum(item.batches for item in demand_list)
    unique_count = len(demand_list)
    print(f"\n  📊 TỔNG CUỐI CÙNG: {unique_count} SP (unique), {total_batches} mẻ, {total_tons:.1f} tấn")
    
    return demand_list

