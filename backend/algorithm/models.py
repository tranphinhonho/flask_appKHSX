"""
models.py - Data classes cho hệ thống KHSX
"""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class Priority(Enum):
    """Mức ưu tiên sản xuất"""
    SILO_BACANG = 1      # Xe bồn + Bá Cang (ngày mai)
    WALKIN = 2           # Khách vãng lai
    SHORTFALL = 3        # Bù hàng thiếu hôm qua
    URGENT_STOCKOUT = 4  # Cám nguy cơ đứt hàng (DOH < 3 ngày)
    FORECAST = 5         # Theo forecast tuần


class PackingType(Enum):
    """Loại đóng gói"""
    SILO = 'SILO'       # Xe bồn (bulk)
    BAG_50 = '50'        # Bao 50kg (Farm)
    BAG_40 = '40'        # Bao 40kg
    BAG_25 = '25'        # Bao 25kg (Dealer)
    BAG_5 = '5'          # Bao 5kg (cám con)
    MASH = 'M'           # Cám bột (không ép viên)


@dataclass
class ProductSpec:
    """Thông số kỹ thuật sản phẩm (từ CONG SUAT + FEEDCODE)"""
    product_code: str           # Mã cám (VD: 552SF, 566F)
    formular_code: str = ''     # Mã công thức
    die_size: float = 0.0       # Kích cỡ khuôn (2.5, 2.8, 4.0)
    ton_per_batch: float = 8.4  # Tấn/mẻ
    line_cv: str = ''           # LINE cám viên (PL1-PL7, M)
    line_pk: str = ''           # LINE đóng bao (1-8, SILO)
    ks_code: str = ''           # Mã kháng sinh


@dataclass
class ForecastItem:
    """Nhu cầu forecast tuần cho 1 sản phẩm"""
    product_code: str
    packing_size: str           # '25', '50', 'SILO', '40', '5'
    die_size: float = 0.0
    
    # Tấn - kênh Dealer (theo thương hiệu)
    dealer_higro: float = 0.0
    dealer_cp: float = 0.0
    dealer_star: float = 0.0
    dealer_nuvo: float = 0.0
    dealer_nasa: float = 0.0
    dealer_total: float = 0.0
    
    # Tấn - kênh Farm
    farm_swine: float = 0.0
    farm_integrate: float = 0.0
    farm_total: float = 0.0
    
    # Tổng
    grand_total_tons: float = 0.0
    silo_tons: float = 0.0
    total_with_silo: float = 0.0
    
    # Bao bì (đơn vị: bao)
    bag_higro: int = 0
    bag_cp: int = 0
    bag_star: int = 0
    bag_nuvo: int = 0
    bag_nasa: int = 0
    bag_dealer_total: int = 0
    bag_farm: int = 0
    bag_grand_total: int = 0
    
    # Feed codes theo thương hiệu
    feed_code_higro: str = ''    # Cột D
    feed_code_cp: str = ''       # Cột E
    feed_code_star: str = ''     # Cột F
    feed_code_nuvo: str = ''     # Cột G
    feed_code_nasa: str = ''     # Cột H
    feed_code_farm: str = ''     # Cột I


@dataclass
class DemandItem:
    """Một dòng nhu cầu sản xuất trong KHSX"""
    product_code: str
    batches: int                 # Số mẻ
    tons: float                  # Tổng tấn
    priority: Priority           # Mức ưu tiên
    source: str                  # Nguồn: 'SILO', 'BACANG', 'WALKIN', 'SHORTFALL', 'FORECAST'
    packing_size: str = ''       # '25', '50', 'SILO'
    
    # Phân bổ bao bì (tấn)
    higro_25: float = 0.0
    cp_25: float = 0.0
    star_25: float = 0.0
    nuvo_25: float = 0.0
    nasa_25: float = 0.0
    bell_25: float = 0.0
    higro_40: float = 0.0
    cp_40: float = 0.0
    star_40: float = 0.0
    nuvo_40: float = 0.0
    nasa_40: float = 0.0
    bell_40: float = 0.0
    white_bag_25: float = 0.0
    white_bag_40: float = 0.0
    white_bag_50: float = 0.0
    silo_truck: float = 0.0
    
    # Thông tin bổ sung
    line_cv: str = ''            # LINE cám viên
    line_pk: str = ''            # LINE đóng bao
    ks_code: str = ''            # Mã kháng sinh
    ks_level: int = 1            # Mức độ kháng sinh (1-26, mặc định = 1 là cám sạch)
    warning: str = ''            # Cảnh báo (nếu có)
    
    @property
    def total_packed(self) -> float:
        """Tổng tấn đã phân bổ bao bì"""
        return (self.higro_25 + self.cp_25 + self.star_25 + self.nuvo_25 + 
                self.nasa_25 + self.bell_25 + self.higro_40 + self.cp_40 + 
                self.star_40 + self.nuvo_40 + self.nasa_40 + self.bell_40 +
                self.white_bag_25 + self.white_bag_40 + self.white_bag_50 + 
                self.silo_truck)


@dataclass 
class KHSXResult:
    """Kết quả kế hoạch sản xuất 1 ngày"""
    date: str                            # Ngày lập KH
    items: list = field(default_factory=list)  # List[DemandItem]
    warnings: list = field(default_factory=list)  # List[str]
    
    @property
    def total_tons(self) -> float:
        return sum(item.tons for item in self.items)
    
    @property
    def total_batches(self) -> int:
        return sum(item.batches for item in self.items)
    
    @property
    def product_count(self) -> int:
        return len(self.items)
    
    def summary(self) -> str:
        lines = [
            f"═══ KHSX NGÀY {self.date} ═══",
            f"Tổng sản phẩm: {self.product_count}",
            f"Tổng mẻ: {self.total_batches}",
            f"Tổng tấn: {self.total_tons:.1f}",
            f"Cảnh báo: {len(self.warnings)}"
        ]
        return "\n".join(lines)
