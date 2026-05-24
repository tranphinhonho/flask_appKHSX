"""
constraint_solver.py - Kiểm tra và điều chỉnh kế hoạch theo ràng buộc
"""
from models import Priority, DemandItem


def _merge_same_product(demand_list):
    """
    Gộp các dòng cùng mã cám.
    Giữ priority cao nhất (số nhỏ nhất).
    """
    merged = {}
    for item in demand_list:
        code = item.product_code
        if code in merged:
            existing = merged[code]
            existing.batches += item.batches
            existing.tons += item.tons
            existing.silo_truck = (existing.silo_truck or 0.0) + (item.silo_truck or 0.0)
            # Giữ priority cao hơn (số nhỏ hơn)
            if item.priority.value < existing.priority.value:
                existing.priority = item.priority
                existing.source = item.source
            # Nếu item có packing_size không phải SILO, giữ lại packing_size đó làm đại diện đóng bao
            if item.packing_size and item.packing_size != 'SILO':
                existing.packing_size = item.packing_size
            # Gộp brand_demands của các mã phụ
            if hasattr(item, 'brand_demands'):
                if not hasattr(existing, 'brand_demands'):
                    existing.brand_demands = {}
                for k, v in item.brand_demands.items():
                    existing.brand_demands[k] = existing.brand_demands.get(k, 0.0) + v
        else:
            new_item = DemandItem(
                product_code=item.product_code,
                batches=item.batches,
                tons=item.tons,
                priority=item.priority,
                source=item.source,
                packing_size=item.packing_size,
                silo_truck=item.silo_truck or 0.0,
            )
            if hasattr(item, 'brand_demands'):
                new_item.brand_demands = item.brand_demands.copy()
            merged[code] = new_item
    
    return list(merged.values())


def solve_constraints(demand_list, empty_bag, congsuat,
                      min_tons=2100, max_tons=2500, target_tons=2250,
                      max_products=35, ffstock_details=None):
    """
    Kiểm tra ràng buộc và điều chỉnh kế hoạch.
    
    Args:
        demand_list: list[DemandItem] - Nhu cầu đã tính
        empty_bag: dict - Tồn kho bao bì
        congsuat: dict - Công suất sản phẩm
        min_tons: Công suất tối thiểu (tấn/ngày)
        max_tons: Công suất tối đa (tấn/ngày)
        target_tons: Mục tiêu (tấn/ngày)
        max_products: Số mã cám tối đa trong 1 ngày
        ffstock_details: dict - Chi tiết tồn kho DOH của các mã
    
    Returns:
        (list[DemandItem], list[str]) - KH đã điều chỉnh + Cảnh báo
    """
    warnings = []
    
    total_tons_before = sum(item.tons for item in demand_list)
    count_before = len(demand_list)
    
    print(f"\n{'─'*50}")
    print(f"🔧 KIỂM TRA RÀNG BUỘC")
    print(f"   Trước điều chỉnh: {count_before} mã cám, {total_tons_before:.1f} tấn")
    print(f"   Giới hạn: tối đa {max_products} mã cám, {min_tons}-{max_tons} tấn")
    print(f"{'─'*50}")
    
    # ============================================
    # BƯỚC 0: GỘP SẢN PHẨM TRÙNG
    # ============================================
    demand_list = _merge_same_product(demand_list)
    if len(demand_list) < count_before:
        print(f"  🔄 Gộp SP trùng: {count_before} → {len(demand_list)} mã cám")
    
    # Sắp xếp theo ưu tiên, trong cùng ưu tiên thì tấn lớn trước
    demand_list.sort(key=lambda x: (x.priority.value, -x.tons))
    
    # ============================================
    # BƯỚC 1: GIỚI HẠN SỐ MÃ CÁM (max_products)
    # ============================================
    if len(demand_list) > max_products:
        # Tách theo ưu tiên
        must_keep = []       # SILO_BACANG (P1) + WALKIN (P2): KHÔNG được bỏ
        shortfall = []       # Bù thiếu (P3): ưu tiên giữ cao
        urgent_stockout = [] # Nguy cơ đứt hàng DOH < 3 (P4): ưu tiên giữ trung bình
        forecast = []        # Forecast thường (P5): ưu tiên thấp nhất, có thể cắt trước

        for item in demand_list:
            if item.priority in (Priority.SILO_BACANG, Priority.WALKIN):
                must_keep.append(item)
            elif item.priority == Priority.SHORTFALL:
                shortfall.append(item)
            elif item.priority == Priority.URGENT_STOCKOUT:
                urgent_stockout.append(item)
            else:
                forecast.append(item)
        
        # Nhận diện ffstock_details
        if ffstock_details is None:
            ffstock_details = {}
            
        # Sắp xếp các danh sách:
        # Bù thiếu: giữ các mã nhiều tấn hơn trước
        shortfall.sort(key=lambda x: -x.tons)
        
        # Nguy cơ đứt hàng DOH < 3: Ưu tiên giữ các mã có DOH thấp hơn trước (thiếu hàng hơn)
        # Trong cùng mức DOH, giữ mã có sản lượng lớn hơn trước
        urgent_stockout.sort(key=lambda x: (ffstock_details.get(x.product_code, {}).get('doh', 99.0), -x.tons))
        
        # Forecast thường: Ưu tiên giữ các mã có DOH thấp hơn trước (thiếu hàng hơn)
        # Trong cùng mức DOH, giữ mã có sản lượng lớn hơn trước
        forecast.sort(key=lambda x: (ffstock_details.get(x.product_code, {}).get('doh', 99.0), -x.tons))
        
        # Tính số slot còn trống
        slots_remaining = max_products - len(must_keep)
        
        if slots_remaining < 0:
            # Quá nhiều SILO/BaCang/Walkin → giữ hết, cảnh báo
            selected = must_keep
            warnings.append(
                f"⚠️ Riêng SILO+BáCang+Vãng lai đã {len(must_keep)} mã > {max_products}!"
            )
        else:
            # Lấy Shortfall trước
            selected_shortfall = shortfall[:slots_remaining]
            slots_remaining -= len(selected_shortfall)
            
            # Lấy Urgent Stockout tiếp theo
            selected_urgent = urgent_stockout[:slots_remaining]
            slots_remaining -= len(selected_urgent)
            
            # Lấy Forecast còn lại
            selected_forecast = forecast[:max(0, slots_remaining)]
            
            selected = must_keep + selected_shortfall + selected_urgent + selected_forecast
        
        removed = len(demand_list) - len(selected)
        demand_list = selected
        
        if removed > 0:
            warnings.append(
                f"✂️ Cắt {removed} mã cám (giữ {len(demand_list)}/{max_products})"
            )
            print(f"  ✂️ Giới hạn mã cám: cắt {removed} → giữ {len(demand_list)} mã")
    
    # Sắp xếp lại
    demand_list.sort(key=lambda x: (x.priority.value, -x.tons))
    
    total_tons = sum(item.tons for item in demand_list)
    
    # ============================================
    # BƯỚC 2: Điều chỉnh tổng công suất
    # ============================================
    
    # 2a. Nếu THIẾU → Tăng mẻ cho Forecast (hoặc Urgent_Stockout nếu không có Forecast)
    if total_tons < min_tons:
        deficit = min_tons - total_tons
        forecast_items = [item for item in demand_list 
                         if item.priority == Priority.FORECAST]
        
        if not forecast_items:
            # Fallback sang tăng Urgent_Stockout nếu không có Forecast thường
            forecast_items = [item for item in demand_list 
                             if item.priority == Priority.URGENT_STOCKOUT]
            
        if forecast_items:
            # Sắp xếp theo sản lượng hiện tại giảm dần
            forecast_items.sort(key=lambda x: x.tons, reverse=True)
            
            idx = 0
            while deficit > 0:
                item = forecast_items[idx % len(forecast_items)]
                tpb = item.tons / item.batches if item.batches > 0 else 8.4
                
                item.batches += 1
                item.tons += tpb
                deficit -= tpb
                
                idx += 1
            
            total_tons = sum(item.tons for item in demand_list)
            warnings.append(
                f"⬆️ Tăng sản lượng để đạt {min_tons} tấn tối thiểu"
            )
        else:
            warnings.append(
                f"⚠️ Tổng {total_tons:.1f} tấn < {min_tons} tấn nhưng không có sản phẩm phù hợp để tăng!"
            )
    
    # 2b. Nếu THỪA → Giảm mẻ (ưu tiên thấp trước: Forecast -> Urgent Stockout -> Shortfall)
    if total_tons > max_tons:
        surplus = total_tons - max_tons
        
        # 1. Giảm Forecast trước (Priority.FORECAST)
        forecast_items = [item for item in demand_list 
                         if item.priority == Priority.FORECAST]
        
        if forecast_items:
            # Nhỏ nhất trước để tránh ảnh hưởng đến các mã cám lớn
            forecast_items.sort(key=lambda x: x.tons)
            
            idx = 0
            stuck_count = 0
            while surplus > 0 and stuck_count < len(forecast_items):
                item = forecast_items[idx % len(forecast_items)]
                tpb = item.tons / item.batches if item.batches > 0 else 8.4
                
                if item.batches > 1:
                    item.batches -= 1
                    item.tons -= tpb
                    surplus -= tpb
                    stuck_count = 0
                else:
                    stuck_count += 1
                
                idx += 1
        
        # 2. Nếu vẫn thừa → Giảm Urgent Stockout (Priority.URGENT_STOCKOUT)
        if surplus > 0:
            urgent_items = [item for item in demand_list 
                            if item.priority == Priority.URGENT_STOCKOUT]
            if urgent_items:
                urgent_items.sort(key=lambda x: x.tons)
                
                idx = 0
                stuck_count = 0
                while surplus > 0 and stuck_count < len(urgent_items):
                    item = urgent_items[idx % len(urgent_items)]
                    tpb = item.tons / item.batches if item.batches > 0 else 8.4
                    
                    if item.batches > 1:
                        item.batches -= 1
                        item.tons -= tpb
                        surplus -= tpb
                        stuck_count = 0
                    else:
                        stuck_count += 1
                    
                    idx += 1
        
        # 3. Nếu vẫn thừa → Giảm Shortfall (Priority.SHORTFALL)
        if surplus > 0:
            shortfall_items = [item for item in demand_list 
                              if item.priority == Priority.SHORTFALL]
            if shortfall_items:
                shortfall_items.sort(key=lambda x: x.tons)
                
                idx = 0
                stuck_count = 0
                while surplus > 0 and stuck_count < len(shortfall_items):
                    item = shortfall_items[idx % len(shortfall_items)]
                    tpb = item.tons / item.batches if item.batches > 0 else 8.4
                    
                    if item.batches > 1:
                        item.batches -= 1
                        item.tons -= tpb
                        surplus -= tpb
                        stuck_count = 0
                    else:
                        stuck_count += 1
                    
                    idx += 1
        
        # KHÔNG BAO GIỜ giảm SILO_BACANG và WALKIN
        if surplus > 0:
            warnings.append(
                f"⚠️ Vẫn vượt {surplus:.1f} tấn sau khi giảm. "
                f"Không thể giảm SILO/BáCang/Khách vãng lai!"
            )
        
        total_tons = sum(item.tons for item in demand_list)
        warnings.append(
            f"⬇️ Giảm sản lượng để không vượt {max_tons} tấn"
        )
    
    # ============================================
    # BƯỚC 3: Loại bỏ item có 0 mẻ
    # ============================================
    demand_list = [item for item in demand_list if item.batches > 0]
    
    # ============================================
    # BƯỚC 4: Kiểm tra LINE máy (cảnh báo)
    # ============================================
    line_load = {}
    for item in demand_list:
        if item.line_cv:
            line_load[item.line_cv] = line_load.get(item.line_cv, 0) + item.batches
    
    for line, total_batches in line_load.items():
        if total_batches > 80:
            warnings.append(
                f"⚠️ LINE {line} có thể quá tải: {total_batches} mẻ"
            )
    
    # ============================================
    # TỔNG KẾT
    # ============================================
    total_tons = sum(item.tons for item in demand_list)
    status = "✅" if min_tons <= total_tons <= max_tons else "⚠️"
    product_status = "✅" if len(demand_list) <= max_products else "⚠️"
    
    print(f"\n  {product_status} Mã cám: {len(demand_list)}/{max_products}")
    print(f"  {status} Tổng tấn: {total_tons:.1f} ({min_tons}-{max_tons})")
    print(f"  📝 Cảnh báo: {len(warnings)}")
    for w in warnings:
        print(f"     {w}")
    
    return demand_list, warnings

