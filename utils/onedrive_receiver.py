"""
OneDrive Sync Receiver - Đọc file từ folder OneDrive đã sync về local
Phương pháp đơn giản, không cần Azure API

Yêu cầu: OneDrive desktop đang sync folder B7KHSX
"""

import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional


class OneDriveSyncReceiver:
    """Class đọc file từ OneDrive folder đã sync về local"""
    
    # Pattern file cần lọc
    FILE_PATTERNS = {
        'FFSTOCK': r'FFSTOCK.*\.xlsm?$',
        'BAG_REPORT': r'DAILY STOCK EMPTY BAG REPORT.*\.xlsm?$',
        'PRODUCTION': r'^pro.*\.csv$',
        'TONBON': r'[Bb][áa]o c[áa]o t[ồo]n b[ồo]n.*\.xlsx?$'
    }
    
    def __init__(self, onedrive_base_path: Optional[str] = None):
        """
        Khởi tạo receiver
        
        Args:
            onedrive_base_path: Đường dẫn gốc của OneDrive synced folder
                               Mặc định: C:/Users/{username}/OneDrive - Cong Ty Co Phan Chan Nuoi C.P. Viet Nam
        """
        if onedrive_base_path:
            self.base_path = Path(onedrive_base_path)
        else:
            # Auto-detect OneDrive path
            self.base_path = self._detect_onedrive_path()
        
        # Folder paths
        self.folders = {
            'FFSTOCK': self.base_path / 'B7KHSX' / 'FFSTOCK',
            'TonBon': self.base_path / 'B7KHSX' / 'TonBon',
            'Production': self.base_path / 'B7KHSX' / 'Production',
            'BagReport': self.base_path / 'B7KHSX' / 'BagReport'
        }
        
        # Download folder (copy file về đây để xử lý)
        self.download_folder = Path("D:/PYTHON/B7KHSX/downloads")
        self.download_folder.mkdir(parents=True, exist_ok=True)
    
    def _detect_onedrive_path(self) -> Path:
        """Tự động tìm đường dẫn OneDrive"""
        
        user_home = Path.home()
        
        # Các tên folder OneDrive phổ biến
        possible_names = [
            "OneDrive - Cong Ty Co Phan Chan Nuoi C.P. Viet Nam",
            "OneDrive - CP Vietnam",
            "OneDrive - cpvn",
            "OneDrive"
        ]
        
        for name in possible_names:
            path = user_home / name
            if path.exists():
                print(f"✅ Tìm thấy OneDrive: {path}")
                return path
        
        # Fallback
        default = user_home / "OneDrive"
        print(f"⚠️ Không tìm thấy OneDrive, sử dụng: {default}")
        return default
    
    def check_setup(self) -> Dict:
        """Kiểm tra OneDrive đã sync đúng chưa"""
        
        result = {
            'onedrive_exists': self.base_path.exists(),
            'base_path': str(self.base_path),
            'folders': {}
        }
        
        for name, path in self.folders.items():
            result['folders'][name] = {
                'path': str(path),
                'exists': path.exists(),
                'file_count': len(list(path.glob('*'))) if path.exists() else 0
            }
        
        return result
    
    def list_files(
        self, 
        folder_name: str,
        days_back: int = 7,
        pattern: Optional[str] = None
    ) -> List[Dict]:
        """
        Liệt kê files trong folder
        
        Args:
            folder_name: Tên folder (FFSTOCK, TonBon, Production, BagReport)
            days_back: Số ngày lùi lại để lọc file
            pattern: Regex pattern để lọc tên file
            
        Returns:
            List các dict chứa thông tin file
        """
        folder_path = self.folders.get(folder_name)
        
        if not folder_path or not folder_path.exists():
            print(f"❌ Folder không tồn tại: {folder_name}")
            return []
        
        files = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        for file_path in folder_path.iterdir():
            if file_path.is_file():
                # Lấy thời gian sửa đổi
                modified = datetime.fromtimestamp(file_path.stat().st_mtime)
                
                # Lọc theo thời gian
                if modified < cutoff_date:
                    continue
                
                # Lọc theo pattern
                if pattern:
                    if not re.search(pattern, file_path.name, re.IGNORECASE):
                        continue
                
                files.append({
                    'name': file_path.name,
                    'path': str(file_path),
                    'size': file_path.stat().st_size,
                    'modified': modified
                })
        
        # Sắp xếp theo ngày mới nhất
        files.sort(key=lambda x: x['modified'], reverse=True)
        
        print(f"📂 Tìm thấy {len(files)} file trong {folder_name}")
        return files
    
    def get_stock_files(self, days_back: int = 7) -> List[Dict]:
        """Lấy danh sách file FFSTOCK"""
        return self.list_files('FFSTOCK', days_back, self.FILE_PATTERNS['FFSTOCK'])
    
    def get_tonbon_files(self, days_back: int = 7) -> List[Dict]:
        """Lấy danh sách file Tồn bồn"""
        return self.list_files('TonBon', days_back, self.FILE_PATTERNS['TONBON'])
    
    def get_production_files(self, days_back: int = 7) -> List[Dict]:
        """Lấy danh sách file Production CSV"""
        return self.list_files('Production', days_back, self.FILE_PATTERNS['PRODUCTION'])
    
    def get_bagreport_files(self, days_back: int = 7) -> List[Dict]:
        """Lấy danh sách file BAG_REPORT"""
        return self.list_files('BagReport', days_back, self.FILE_PATTERNS['BAG_REPORT'])
    
    def copy_to_downloads(self, file_info: Dict, subfolder: str = "") -> Optional[Path]:
        """Copy file về folder downloads để xử lý"""
        import shutil
        
        source = Path(file_info['path'])
        
        if not source.exists():
            print(f"❌ File không tồn tại: {source}")
            return None
        
        dest_folder = self.download_folder
        if subfolder:
            dest_folder = dest_folder / subfolder
            dest_folder.mkdir(parents=True, exist_ok=True)
        
        dest = dest_folder / source.name
        
        try:
            shutil.copy2(source, dest)
            print(f"✅ Đã copy: {dest}")
            return dest
        except Exception as e:
            print(f"❌ Lỗi copy: {e}")
            return None


def test_setup():
    """Test OneDrive setup"""
    
    receiver = OneDriveSyncReceiver()
    
    print("\n" + "="*60)
    print("🔍 KIỂM TRA ONEDRIVE SYNC")
    print("="*60)
    
    result = receiver.check_setup()
    
    print(f"\n📁 OneDrive path: {result['base_path']}")
    print(f"   Exists: {'✅' if result['onedrive_exists'] else '❌'}")
    
    print(f"\n📂 Folders:")
    for name, info in result['folders'].items():
        status = '✅' if info['exists'] else '❌'
        print(f"   {status} {name}: {info['file_count']} files")
    
    print("\n" + "="*60)
    
    if not result['onedrive_exists']:
        print("""
⚠️ HƯỚNG DẪN:
1. Mở OneDrive desktop
2. Sync folder B7KHSX về máy
3. Chạy lại test này
""")


if __name__ == "__main__":
    test_setup()
