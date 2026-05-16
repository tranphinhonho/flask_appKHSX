"""
Module nhận email từ Outlook qua COM
Lọc email từ dinhnguyen@cp.com.vn với file đính kèm FFSTOCK
"""

from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import re

try:
    import win32com.client as win32
except ImportError as e:
    win32 = None
    _IMPORT_ERROR = e


class EmailReceiver:
    """Class xử lý nhận email từ Outlook"""
    
    # Sender filter - email hoặc tên người gửi
    SENDER_FILTERS = [
        "dinhnguyen@cp.com.vn",
        "tran dinh thao nguyen",
        "dinhnguyen"
    ]
    
    # Sender cho PRODUCTION (email gửi đi)
    SENDER_PRODUCTION = [
        "mixer2@cp.com.vn",
        "phinho@cp.com.vn"
    ]
    
    # Sender cho TONBON (báo cáo tồn bồn)
    SENDER_TONBON = [
        "mixer2@cp.com.vn",
        "ankhuong@cp.com.vn",
        "triphuong@cp.com.vn",
        "tronghuan@cp.com.vn",
        "phinho@cp.com.vn"
    ]
    
    # Sender cho PELLET (vận hành cám viên PL1-PL7)
    # Thêm tất cả email có khả năng gửi file pellet
    SENDER_PELLET = [
        "phinho@cp.com.vn",
        "mixer2@cp.com.vn",
        "nguyentram@cp.com.vn",
        "tanhoc@cp.com.vn",
        "hobao@cp.com.vn",
        "vanngoc@cp.com.vn",
        "phuong.van@cp.com.vn",
        "hoanghuu@cp.com.vn",
        "vanphuong@cp.com.vn",   # Pham Van Phuong
        "phamvanphuong@cp.com.vn",  # Pham Van Phuong (alternative)
        "ngocbao@cp.com.vn",    # Ho Ngoc Bao
        "hongocbao@cp.com.vn"   # Ho Ngoc Bao (alternative)
    ]
    
    # Thư mục lưu file download
    DOWNLOAD_FOLDER = Path("D:/PYTHON/B7KHSX/downloads")
    
    # Pattern file cần lọc
    FILE_PATTERNS = {
        'FFSTOCK': r'FFSTOCK.*\.xlsm?$',
        'BAG_REPORT': r'DAILY STOCK EMPTY BAG REPORT.*\.xlsm?$',
        # Match file bắt đầu bằng 'pro' (không phân biệt hoa/thường) và đuôi .csv
        # Ví dụ: PRODUCTION 13.csv, product 9.csv, Pro123.csv
        'PRODUCTION': r'^pro.*\.csv$',
        # Match file báo cáo tồn bồn - cả có dấu và không dấu
        # Ví dụ: "Báo cáo tồn bồn thành phẩm 01.2026.xlsx" hoặc "Bao cao ton bon thanh pham 01.2026.xlsx"
        'TONBON': r'[Bb][áa]o c[áa]o t[ồo]n b[ồo]n.*\.xlsx?$',
        # Match file vận hành cám viên: PLx M.YYYY.xlsx hoặc PLx MM.YYYY.xlsx
        # Ví dụ: "PL1 1.2026.xlsx", "PL7 12.2025.xlsx", "PL3 1.2026.xlsx"
        # Dùng [.] thay vì \. để tránh escape issues
        'PELLET': r'PL[1-7] [0-9]{1,2}[.][0-9]{4}[.](xlsx|xlsm)'
    }
    
    def __init__(self, download_folder: Optional[Path] = None):
        """
        Khởi tạo EmailReceiver
        
        Args:
            download_folder: Thư mục lưu file, mặc định D:/PYTHON/B7KHSX/downloads
        """
        if win32 is None:
            raise ImportError(
                "pywin32 không được cài đặt. Cài bằng: pip install pywin32"
            ) from _IMPORT_ERROR
        
        self.download_folder = download_folder or self.DOWNLOAD_FOLDER
        self.download_folder.mkdir(parents=True, exist_ok=True)
        
        self.outlook = None
        self.namespace = None
        self.inbox = None
    
    def connect(self) -> bool:
        """
        Kết nối với Outlook
        
        Returns:
            True nếu kết nối thành công
        """
        try:
            self.outlook = win32.Dispatch("Outlook.Application")
            self.namespace = self.outlook.GetNamespace("MAPI")
            self.inbox = self.namespace.GetDefaultFolder(6)  # 6 = olFolderInbox
            return True
        except Exception as e:
            print(f"Lỗi kết nối Outlook: {e}")
            return False
    
    def _find_folder_by_name(self, parent_folder, folder_name: str):
        """Tìm subfolder theo tên (recursive)"""
        try:
            for folder in parent_folder.Folders:
                if folder_name.lower() in folder.Name.lower():
                    return folder
                # Tìm trong subfolder
                found = self._find_folder_by_name(folder, folder_name)
                if found:
                    return found
        except:
            pass
        return None
    
    def get_all_folders(self) -> List[str]:
        """Lấy danh sách tất cả folder trong Inbox"""
        folders = []
        try:
            if not self.inbox:
                self.connect()
            
            def list_folders(parent, prefix=""):
                for folder in parent.Folders:
                    folders.append(f"{prefix}{folder.Name}")
                    list_folders(folder, prefix + "  ")
            
            folders.append(f"📥 {self.inbox.Name}")
            list_folders(self.inbox, "  ")
        except Exception as e:
            print(f"Lỗi lấy danh sách folder: {e}")
        
        return folders
    
    def _match_sender(self, email_address: str) -> bool:
        """Kiểm tra email có match với sender filter không"""
        email_lower = email_address.lower()
        for filter_str in self.SENDER_FILTERS:
            if filter_str.lower() in email_lower:
                return True
        return False
    
    def _match_file_pattern(self, filename: str, pattern_key: str) -> bool:
        """Kiểm tra filename có match với pattern không"""
        pattern = self.FILE_PATTERNS.get(pattern_key)
        if not pattern:
            return False
        return bool(re.search(pattern, filename, re.IGNORECASE))
    
    def get_stock_emails(
        self, 
        days_back: int = 7,
        unread_only: bool = False,
        folder_name: Optional[str] = None,
        search_subfolders: bool = True
    ) -> List[Dict]:
        """
        Lấy danh sách email có file FFSTOCK hoặc BAG_REPORT
        Tìm trong Favorites trước (Nguyen KTP) cho nhanh
        
        Args:
            days_back: Số ngày lùi lại để tìm email
            unread_only: Chỉ lấy email chưa đọc
            folder_name: Tên folder cụ thể (mặc định: Nguyen KTP)
            search_subfolders: Tìm trong cả subfolder của Inbox
            
        Returns:
            List các dict chứa thông tin email và attachments
        """
        if not self.inbox:
            if not self.connect():
                return []
        
        results = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        # Xác định các folder cần tìm - ưu tiên Favorites
        folders_to_search = []
        target_folder_name = folder_name or "Nguyen KTP"  # Mặc định tìm trong folder dinhnguyen
        
        print(f"🔍 Tìm nhanh folder '{target_folder_name}'...")
        
        # Bước 1: Tìm trong các folder cấp 1 (Favorites) của tất cả account
        try:
            for account in self.namespace.Folders:
                try:
                    for folder in account.Folders:
                        if folder.Name == target_folder_name:
                            folders_to_search.append(folder)
                            print(f"✅ Tìm thấy '{target_folder_name}' trong Favorites!")
                            break
                    if folders_to_search:
                        break
                except:
                    continue
        except Exception as e:
            print(f"⚠️ Lỗi tìm trong Favorites: {e}")
        
        # Bước 2: Nếu không tìm thấy, fallback về Inbox
        if not folders_to_search:
            print(f"🔄 Fallback: Tìm trong Inbox...")
            
            if folder_name:
                # Tìm folder cụ thể trong Inbox
                found = self._find_folder_by_name(self.inbox, folder_name)
                if found:
                    folders_to_search.append(found)
                else:
                    print(f"⚠️ Không tìm thấy folder '{folder_name}'")
            
            # Thêm Inbox chính
            folders_to_search.append(self.inbox)
            
            # Thêm các subfolder nếu cần
            if search_subfolders:
                try:
                    for subfolder in self.inbox.Folders:
                        if subfolder not in folders_to_search:
                            folders_to_search.append(subfolder)
                except:
                    pass
        
        print(f"📂 Đang tìm trong {len(folders_to_search)} folder(s)...")
        
        # Tìm trong tất cả folder
        for folder in folders_to_search:
            try:
                folder_results = self._search_folder(folder, cutoff_date, unread_only)
                results.extend(folder_results)
            except Exception as e:
                print(f"Lỗi tìm trong folder {folder.Name}: {e}")
        
        print(f"✅ Tìm thấy {len(results)} email có file FFSTOCK/BAG_REPORT")
        
        return results
    
    def _search_folder(
        self, 
        folder, 
        cutoff_date: datetime,
        unread_only: bool
    ) -> List[Dict]:
        """Tìm email trong một folder cụ thể"""
        results = []
        max_results = 10  # Giới hạn tối đa 10 email để tăng tốc
        
        try:
            items = folder.Items
            items.Sort("[ReceivedTime]", True)  # Mới nhất trước
            
            for i in range(min(50, items.Count)):  # Quét tối đa 50 email
                try:
                    item = items.Item(i + 1)
                    
                    # Lọc theo thời gian
                    received_time = item.ReceivedTime
                    if hasattr(received_time, 'year'):
                        # Convert to naive datetime for comparison
                        try:
                            # COM datetime may be timezone-aware
                            received_naive = datetime(
                                received_time.year, received_time.month, received_time.day,
                                received_time.hour, received_time.minute, received_time.second
                            )
                            if received_naive < cutoff_date:
                                continue
                        except:
                            pass
                    
                    # Lọc theo trạng thái đọc
                    if unread_only and not item.UnRead:
                        continue
                    
                    # Lọc theo người gửi
                    sender = item.SenderEmailAddress or ""
                    sender_name = item.SenderName or ""
                    
                    if not (self._match_sender(sender) or self._match_sender(sender_name)):
                        continue
                    
                    # Kiểm tra attachments
                    stock_files = []
                    bag_files = []
                    
                    if item.Attachments.Count > 0:
                        for j in range(1, item.Attachments.Count + 1):
                            att = item.Attachments.Item(j)
                            filename = att.FileName
                            
                            if self._match_file_pattern(filename, 'FFSTOCK'):
                                stock_files.append({
                                    'filename': filename,
                                    'size': att.Size,
                                    'index': j
                                })
                            elif self._match_file_pattern(filename, 'BAG_REPORT'):
                                bag_files.append({
                                    'filename': filename,
                                    'size': att.Size,
                                    'index': j
                                })
                    
                    # Thêm email nếu có FFSTOCK hoặc BAG_REPORT
                    if stock_files or bag_files:
                        results.append({
                            'subject': item.Subject,
                            'sender': sender_name or sender,
                            'sender_email': sender,
                            'received_time': received_time,
                            'unread': item.UnRead,
                            'entry_id': item.EntryID,
                            'stock_files': stock_files,
                            'bag_files': bag_files,
                            '_item': item  # Reference để download sau
                        })
                        
                        # Dừng sớm nếu đã đủ số lượng
                        if len(results) >= max_results:
                            return results
                        
                except Exception as e:
                    print(f"Lỗi đọc email {i+1}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Lỗi lấy danh sách email: {e}")
        
        return results
    
    def get_production_emails(
        self, 
        days_back: int = 7
    ) -> List[Dict]:
        """
        Lấy danh sách email có file PRODUCTION CSV từ folder Sent Items
        Email được gửi từ mixer2@cp.com.vn hoặc phinho@cp.com.vn
        
        Args:
            days_back: Số ngày lùi lại để tìm email
            
        Returns:
            List các dict chứa thông tin email và attachments
        """
        if not self.outlook:
            if not self.connect():
                return []
        
        results = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        try:
            # Lấy folder Sent Items (5 = olFolderSentMail)
            sent_folder = self.namespace.GetDefaultFolder(5)
            
            items = sent_folder.Items
            items.Sort("[SentOn]", True)  # Mới nhất trước
            
            max_results = 10  # Giới hạn tối đa 10 email
            
            for i in range(min(50, items.Count)):  # Quét tối đa 50 email
                try:
                    item = items.Item(i + 1)
                    
                    # Lọc theo thời gian gửi
                    sent_time = item.SentOn
                    if hasattr(sent_time, 'year'):
                        try:
                            sent_naive = datetime(
                                sent_time.year, sent_time.month, sent_time.day,
                                sent_time.hour, sent_time.minute, sent_time.second
                            )
                            if sent_naive < cutoff_date:
                                continue
                        except:
                            pass
                    
                    # Kiểm tra attachments có PRODUCTION CSV không
                    production_files = []
                    
                    if item.Attachments.Count > 0:
                        for j in range(1, item.Attachments.Count + 1):
                            att = item.Attachments.Item(j)
                            filename = att.FileName
                            
                            if self._match_file_pattern(filename, 'PRODUCTION'):
                                production_files.append({
                                    'filename': filename,
                                    'size': att.Size,
                                    'index': j
                                })
                    
                    # Thêm email nếu có PRODUCTION file
                    if production_files:
                        results.append({
                            'subject': item.Subject,
                            'sender': 'Bạn (Sent)',
                            'sender_email': '',
                            'received_time': sent_time,
                            'unread': False,
                            'entry_id': item.EntryID,
                            'production_files': production_files,
                            'stock_files': [],
                            'bag_files': [],
                            '_item': item
                        })
                        
                        # Dừng sớm nếu đã đủ số lượng
                        if len(results) >= max_results:
                            break
                        
                except Exception as e:
                    print(f"Lỗi đọc email sent {i+1}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Lỗi lấy Sent Items: {e}")
        
        return results
    
    def get_tonbon_emails(
        self, 
        days_back: int = 7,
        folder_name: str = "Tồn bồn"
    ) -> List[Dict]:
        """
        Lấy danh sách email có file Báo cáo tồn bồn từ folder "Tồn bồn"
        Tìm trong Favorites trước cho nhanh, nếu không có thì tìm trong mailbox
        
        Args:
            days_back: Số ngày lùi lại để tìm email
            folder_name: Tên folder (mặc định: Tồn bồn)
            
        Returns:
            List các dict chứa thông tin email và attachments
        """
        if not self.outlook:
            if not self.connect():
                return []
        
        results = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        target_folder = None
        
        try:
            # Bước 1: Tìm trong Favorites trước (nhanh hơn)
            print(f"🔍 Tìm nhanh folder '{folder_name}' trong Favorites...")
            
            try:
                # Favorites là một folder đặc biệt có thể truy cập trực tiếp
                for account in self.namespace.Folders:
                    try:
                        # Tìm trong các folder cấp 1 của mỗi account
                        for folder in account.Folders:
                            if folder.Name == folder_name:
                                target_folder = folder
                                print(f"✅ Tìm thấy '{folder_name}' trực tiếp!")
                                break
                        if target_folder:
                            break
                    except:
                        continue
            except Exception as e:
                print(f"⚠️ Không tìm được trong Favorites: {e}")
            
            # Bước 2: Nếu không tìm thấy trong Favorites, tìm trong mailbox mixer2
            if not target_folder:
                print(f"🔄 Tìm trong mailbox mixer2...")
                
                for account in self.namespace.Folders:
                    account_name = account.Name.lower()
                    
                    # Chỉ tìm trong mailbox mixer2 (không phải Archive)
                    if "mixer2" in account_name and "archive" not in account_name:
                        print(f"📧 Đang tìm trong: {account.Name}")
                        
                        # Tìm folder Tồn bồn trong tất cả subfolder (2 cấp)
                        try:
                            for folder in account.Folders:
                                # Kiểm tra folder cấp 1
                                if folder.Name == folder_name:
                                    target_folder = folder
                                    print(f"✅ Tìm thấy ở cấp 1: {folder.Name}")
                                    break
                                
                                # Tìm trong subfolder cấp 2
                                try:
                                    for subfolder in folder.Folders:
                                        if subfolder.Name == folder_name:
                                            target_folder = subfolder
                                            print(f"✅ Tìm thấy trong {folder.Name}/{folder_name}")
                                            break
                                    if target_folder:
                                        break
                                except:
                                    continue
                                    
                            if target_folder:
                                break
                        except Exception as e:
                            print(f"⚠️ Lỗi tìm folder: {e}")
                        
                        if target_folder:
                            break
            
            if not target_folder:
                print(f"❌ Không tìm thấy folder '{folder_name}'")
                return results
            
            print(f"📂 Đang đọc email từ folder: {target_folder.Name}")
            
            items = target_folder.Items
            items.Sort("[ReceivedTime]", True)  # Mới nhất trước
            
            for i in range(min(50, items.Count)):
                try:
                    item = items.Item(i + 1)
                    
                    # Lọc theo thời gian nhận
                    received_time = item.ReceivedTime
                    if hasattr(received_time, 'year'):
                        try:
                            received_naive = datetime(
                                received_time.year, received_time.month, received_time.day,
                                received_time.hour, received_time.minute, received_time.second
                            )
                            if received_naive < cutoff_date:
                                continue
                        except:
                            pass
                    
                    # Kiểm tra attachments có TONBON file không
                    tonbon_files = []
                    
                    if item.Attachments.Count > 0:
                        for j in range(1, item.Attachments.Count + 1):
                            att = item.Attachments.Item(j)
                            filename = att.FileName
                            
                            if self._match_file_pattern(filename, 'TONBON'):
                                tonbon_files.append({
                                    'filename': filename,
                                    'size': att.Size,
                                    'index': j
                                })
                    
                    # Thêm email nếu có TONBON file
                    if tonbon_files:
                        # Lấy thông tin sender
                        try:
                            sender_email = item.SenderEmailAddress
                        except:
                            sender_email = ""
                        
                        # Format thời gian đúng (local time)
                        try:
                            received_time_str = datetime(
                                received_time.year, received_time.month, received_time.day,
                                received_time.hour, received_time.minute, received_time.second
                            ).strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            received_time_str = str(received_time)
                        
                        results.append({
                            'subject': item.Subject,
                            'sender': item.SenderName,
                            'sender_email': sender_email,
                            'received_time': received_time_str,
                            'unread': item.UnRead,
                            'entry_id': item.EntryID,
                            'tonbon_files': tonbon_files,
                            'stock_files': [],
                            'bag_files': [],
                            'production_files': [],
                            '_item': item
                        })
                        
                except Exception as e:
                    print(f"Lỗi đọc email tonbon {i+1}: {e}")
                    continue
            
            print(f"✅ Tìm thấy {len(results)} email có file báo cáo tồn bồn")
                    
        except Exception as e:
            print(f"Lỗi lấy email tồn bồn: {e}")
        
        return results
    
    def get_pellet_emails(
        self, 
        days_back: int = 30,
        folder_name: str = "Pellet"
    ) -> List[Dict]:
        """
        Lấy danh sách email có file vận hành cám viên (PL1-PL7) từ folder "Pellet"
        File có pattern: PLx M.YYYY.xlsx hoặc PLx MM.YYYY.xlsx
        
        Args:
            days_back: Số ngày lùi lại để tìm email (mặc định 30 ngày vì file theo tháng)
            folder_name: Tên folder (mặc định: Pellet)
            
        Returns:
            List các dict chứa thông tin email và attachments
        """
        if not self.outlook:
            if not self.connect():
                return []
        
        results = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        target_folder = None
        
        try:
            # Bước 1: Tìm folder "Pellet" trong Favorites trước
            print(f"🔍 Tìm nhanh folder '{folder_name}' trong Favorites...")
            
            try:
                for account in self.namespace.Folders:
                    try:
                        for folder in account.Folders:
                            if folder.Name.lower() == folder_name.lower():
                                target_folder = folder
                                print(f"✅ Tìm thấy '{folder_name}' trực tiếp!")
                                break
                        if target_folder:
                            break
                    except:
                        continue
            except Exception as e:
                print(f"⚠️ Không tìm được trong Favorites: {e}")
            
            # Bước 2: Nếu không tìm thấy, tìm trong mailbox
            if not target_folder:
                print(f"🔄 Tìm trong mailbox...")
                
                for account in self.namespace.Folders:
                    account_name = account.Name.lower()
                    
                    if "archive" not in account_name:
                        try:
                            for folder in account.Folders:
                                if folder.Name.lower() == folder_name.lower():
                                    target_folder = folder
                                    print(f"✅ Tìm thấy ở cấp 1: {folder.Name}")
                                    break
                                
                                try:
                                    for subfolder in folder.Folders:
                                        if subfolder.Name.lower() == folder_name.lower():
                                            target_folder = subfolder
                                            print(f"✅ Tìm thấy trong {folder.Name}/{folder_name}")
                                            break
                                    if target_folder:
                                        break
                                except:
                                    continue
                                    
                            if target_folder:
                                break
                        except:
                            continue
            
            if not target_folder:
                print(f"❌ Không tìm thấy folder '{folder_name}'")
                return results
            
            print(f"📂 Đang đọc email từ folder: {target_folder.Name}")
            
            items = target_folder.Items
            items.Sort("[ReceivedTime]", True)
            
            for i in range(min(100, items.Count)):
                try:
                    item = items.Item(i + 1)
                    
                    received_time = item.ReceivedTime
                    if hasattr(received_time, 'year'):
                        try:
                            received_naive = datetime(
                                received_time.year, received_time.month, received_time.day,
                                received_time.hour, received_time.minute, received_time.second
                            )
                            if received_naive < cutoff_date:
                                continue
                        except:
                            pass
                    
                    # Không filter sender vì đã trong folder Pellet (được lọc sẵn)
                    # Lấy thông tin sender để hiển thị
                    try:
                        sender_email = item.SenderEmailAddress.lower() if item.SenderEmailAddress else ""
                    except:
                        sender_email = ""
                    
                    pellet_files = []
                    
                    if item.Attachments.Count > 0:
                        for j in range(1, item.Attachments.Count + 1):
                            att = item.Attachments.Item(j)
                            filename = att.FileName
                            
                            if self._match_file_pattern(filename, 'PELLET'):
                                pellet_files.append({
                                    'filename': filename,
                                    'size': att.Size,
                                    'index': j
                                })
                    
                    if pellet_files:
                        try:
                            received_time_str = datetime(
                                received_time.year, received_time.month, received_time.day,
                                received_time.hour, received_time.minute, received_time.second
                            ).strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            received_time_str = str(received_time)
                        
                        results.append({
                            'subject': item.Subject,
                            'sender': item.SenderName,
                            'sender_email': sender_email,
                            'received_time': received_time_str,
                            'unread': item.UnRead,
                            'entry_id': item.EntryID,
                            'pellet_files': pellet_files,
                            '_item': item
                        })
                        
                except Exception as e:
                    print(f"Lỗi đọc email pellet {i+1}: {e}")
                    continue
            
            print(f"✅ Tìm thấy {len(results)} email có file vận hành cám viên")
                    
        except Exception as e:
            print(f"Lỗi lấy email pellet: {e}")
        
        return results
    
    def download_attachment(
        self, 
        email_info: Dict, 
        file_info: Dict,
        subfolder: Optional[str] = None
    ) -> Optional[Path]:
        """
        Download file đính kèm từ email
        
        Args:
            email_info: Dict thông tin email từ get_stock_emails()
            file_info: Dict thông tin file (filename, index)
            subfolder: Thư mục con (optional)
            
        Returns:
            Path đến file đã download, hoặc None nếu lỗi
        """
        try:
            item = email_info.get('_item')
            att_index = file_info.get('index')
            
            if not att_index:
                print("Không tìm thấy index attachment")
                return None
            
            # Thử dùng _item trước, nếu lỗi (stale COM object) thì dùng entry_id
            try:
                if item:
                    att = item.Attachments.Item(att_index)
                else:
                    raise Exception("No _item reference")
            except Exception as e:
                print(f"⚠️ _item stale, thử dùng entry_id: {e}")
                
                # Fallback: dùng entry_id để lấy lại email
                entry_id = email_info.get('entry_id')
                if not entry_id:
                    print("❌ Không có entry_id để fallback")
                    return None
                
                # Kết nối lại nếu cần
                if not self.namespace:
                    if not self.connect():
                        print("❌ Không thể kết nối Outlook")
                        return None
                
                try:
                    item = self.namespace.GetItemFromID(entry_id)
                    att = item.Attachments.Item(att_index)
                    print(f"✅ Lấy lại email thành công qua entry_id")
                except Exception as e2:
                    print(f"❌ Không thể lấy email qua entry_id: {e2}")
                    return None
            
            # Xác định thư mục lưu
            save_folder = self.download_folder
            if subfolder:
                save_folder = save_folder / subfolder
                save_folder.mkdir(parents=True, exist_ok=True)
            
            # Tạo đường dẫn file
            save_path = save_folder / file_info['filename']
            
            # Download
            att.SaveAsFile(str(save_path))
            
            print(f"✅ Đã download: {save_path}")
            return save_path
            
        except Exception as e:
            print(f"❌ Lỗi download: {e}")
            return None
    
    def mark_as_read(self, email_info: Dict) -> bool:
        """Đánh dấu email đã đọc"""
        try:
            item = email_info.get('_item')
            if item:
                item.UnRead = False
                return True
        except Exception as e:
            print(f"Lỗi đánh dấu đã đọc: {e}")
        return False
    
    def extract_date_from_filename(self, filename: str) -> Optional[str]:
        """
        Trích xuất ngày từ tên file
        Ví dụ: FFSTOCK 10-01-2026.xlsm → 2026-01-10
        
        Returns:
            Date string format YYYY-MM-DD hoặc None
        """
        # Pattern: dd-mm-yyyy
        match = re.search(r'(\d{1,2})-(\d{1,2})-(\d{4})', filename)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return None


def test_email_receiver():
    """Test function"""
    print("=" * 60)
    print("🔍 TEST EMAIL RECEIVER")
    print("=" * 60)
    
    try:
        receiver = EmailReceiver()
        
        print("\n1. Kết nối Outlook...")
        if receiver.connect():
            print("   ✅ Kết nối thành công!")
        else:
            print("   ❌ Kết nối thất bại!")
            return
        
        print("\n2. Tìm email FFSTOCK trong 7 ngày qua...")
        emails = receiver.get_stock_emails(days_back=7)
        
        if not emails:
            print("   ⚠️ Không tìm thấy email nào")
            return
        
        print(f"   ✅ Tìm thấy {len(emails)} email\n")
        
        for idx, email in enumerate(emails, 1):
            print(f"   [{idx}] {email['sender']}")
            print(f"       Subject: {email['subject']}")
            print(f"       Time: {email['received_time']}")
            print(f"       FFSTOCK files: {len(email['stock_files'])}")
            for f in email['stock_files']:
                print(f"         - {f['filename']} ({f['size']} bytes)")
            print()
            
    except Exception as e:
        print(f"❌ Lỗi: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_email_receiver()
