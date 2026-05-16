from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import re
import io
import base64
import json

import numpy as np
from PIL import Image, ImageGrab, ImageFilter, ImageOps
import google.generativeai as genai

CROP_BOXES: Dict[str, Tuple[int, int, int, int]] = {
    "502": (256, 274, 391, 304),
    "505": (231, 572, 365, 617),
    "508": (536,274, 673, 306),
    "574": (536, 571, 674, 619),
    "DATE_TIME": (1797, 1040, 1867, 1078),
}

DEFAULT_DATE_ORDER = "mdy"
DATE_FORMAT_OPTIONS = ["mdy", "dmy", "ymd"]

# Đọc API key từ config.json
def _load_gemini_config():
    config_path = Path(__file__).parent.parent / "admin" / "config.json"
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get('api_key_gemini', ''), config.get('model-flash', 'gemini-1.5-flash')
    except Exception as e:
        print(f"Không thể đọc config.json: {e}")
        return '', 'gemini-1.5-flash'

GEMINI_API_KEY, GEMINI_MODEL_NAME = _load_gemini_config()

# Cấu hình Gemini API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    _GEMINI_MODEL = genai.GenerativeModel(GEMINI_MODEL_NAME)
else:
    _GEMINI_MODEL = None
    print("⚠️ Cảnh báo: Không có API key Gemini trong config.json")


def extract_text_from_image(image: Image.Image, is_datetime: bool = False) -> List[Tuple[str, float]]:
    """Sử dụng Gemini API để trích xuất text từ ảnh"""
    if _GEMINI_MODEL is None:
        print("❌ Lỗi: Gemini model chưa được khởi tạo. Kiểm tra API key trong config.json")
        return []
    
    try:
        # Phóng to ảnh lên 2 lần để AI dễ đọc hơn
        enlarged = image.resize((image.width * 2, image.height * 2), Image.BICUBIC)
        
        # Chuyển ảnh sang bytes
        img_byte_arr = io.BytesIO()
        enlarged.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        
        # Tạo prompt cho Gemini dựa vào loại dữ liệu
        if is_datetime:
            prompt = """Trích xuất NGÀY GIỜ từ ảnh này theo quy tắc:
            - Lấy cả GIỜ (HH:MM hoặc HH:MM:SS) và NGÀY (MM/DD/YYYY hoặc DD/MM/YYYY)
            - Trả về đầy đủ cả giờ và ngày trên cùng một dòng
            - Format: HH:MM hoặc HH:MM:SS và MM/DD/YYYY
            - Ví dụ: 09:15 11/17/2025
            - Không bỏ sót giờ hoặc ngày
            - Không thêm giải thích"""
        else:
            prompt = """Trích xuất văn bản từ ảnh này theo quy tắc:
            - Chỉ lấy số, KHÔNG lấy chữ
            - Nếu có nhiều số trong ảnh, CHỈ LẤY SỐ LỚN NHẤT hoặc SỐ NỔI BẬT NHẤT (thường là số có kích thước font lớn nhất, màu sắc nổi bật)
            - Trả về ĐÚNG 1 SỐ duy nhất, không liệt kê nhiều số
            - Giữ nguyên format số (bao gồm dấu âm -, dấu chấm thập phân .)
            - Không thêm giải thích, chỉ trả về số"""
        
        # Gọi Gemini API
        response = _GEMINI_MODEL.generate_content([prompt, {"mime_type": "image/png", "data": img_byte_arr}])
        
        # Xử lý kết quả
        texts: List[Tuple[str, float]] = []
        if response.text:
            lines = response.text.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line:
                    # Gemini không trả về confidence, dùng 0.95 mặc định
                    texts.append((line, 0.95))
        
        return texts
    except Exception as e:
        print(f"Lỗi khi gọi Gemini API: {str(e)}")
        return []


def _enhance_crop(crop: Image.Image) -> Image.Image:
    """Lightweight preprocessing to improve OCR on dim digits."""
    gray = crop.convert("L")
    resized = gray.resize((gray.width * 2, gray.height * 2), Image.BICUBIC)
    enhanced = ImageOps.autocontrast(resized)
    return enhanced.filter(ImageFilter.SHARPEN)


def ocr_regions_from_image(image: Image.Image) -> Dict[str, List[Tuple[str, float]]]:
    responses: Dict[str, List[Tuple[str, float]]] = {}
    for label, crop_box in CROP_BOXES.items():
        crop = image.crop(crop_box)
        processed = _enhance_crop(crop)
        # Sử dụng prompt riêng cho DATE_TIME
        is_datetime = (label == "DATE_TIME")
        responses[label] = extract_text_from_image(processed, is_datetime=is_datetime)
    return responses


def ocr_regions_from_path(image_path: Path | str) -> Dict[str, List[Tuple[str, float]]]:
    with Image.open(image_path) as image:
        return ocr_regions_from_image(image)


def _get_clipboard_image() -> Image.Image:
    data = ImageGrab.grabclipboard()
    if isinstance(data, Image.Image):
        return data
    if isinstance(data, Iterable):
        first = next(iter(data), None)
        if first:
            with Image.open(first) as img:
                return img.copy()
    raise RuntimeError("Clipboard does not contain image data.")


def ocr_regions_from_clipboard() -> Dict[str, List[Tuple[str, float]]]:
    image = _get_clipboard_image()
    return ocr_regions_from_image(image)


def _normalize_datetime_text(text: str) -> str:
    return " ".join(text.split())


def _parse_datetime(text: str, date_order: str) -> datetime | None:
    normalized = _normalize_datetime_text(text)
    time_match = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)", normalized)
    date_match = re.search(r"(\d{1,4}[/-]\d{1,2}[/-]\d{2,4})", normalized)
    if not time_match or not date_match:
        return None
    time_raw = time_match.group(1)
    date_raw = date_match.group(1).replace("-", "/")
    time_formats = ("%H:%M:%S", "%H:%M")
    date_formats = {
        "mdy": "%m/%d/%Y",
        "dmy": "%d/%m/%Y",
        "ymd": "%Y/%m/%d",
    }
    date_fmt = date_formats.get(date_order, date_formats[DEFAULT_DATE_ORDER])
    for time_fmt in time_formats:
        try:
            parsed_date = datetime.strptime(date_raw, date_fmt)
            parsed_time = datetime.strptime(time_raw, time_fmt)
            return parsed_date.replace(
                hour=parsed_time.hour,
                minute=parsed_time.minute,
                second=parsed_time.second,
            )
        except ValueError:
            continue
    return None


def _merge_datetime_entries(
    entries: List[Tuple[str, float]],
    date_order: str = DEFAULT_DATE_ORDER,
) -> List[Tuple[str, float]]:
    valid_entries = [(text.strip(), confidence) for text, confidence in entries if text.strip()]
    if not valid_entries:
        return []
    combined_text = " ".join(text for text, _ in valid_entries)
    parsed = _parse_datetime(combined_text, date_order)
    avg_confidence = sum(conf for _, conf in valid_entries) / len(valid_entries)
    if parsed is not None:
        formatted = parsed.strftime("%d/%m/%Y %H:%M:%S")
        return [(formatted, avg_confidence)]
    return [(combined_text, avg_confidence)]


def to_serializable(
    results: Dict[str, List[Tuple[str, float]]],
    date_order: str = DEFAULT_DATE_ORDER,
) -> Dict[str, List[Dict[str, float | str]]]:
    serializable: Dict[str, List[Dict[str, float | str]]] = {}
    for label, entries in results.items():
        if label == "DATE_TIME":
            entries = _merge_datetime_entries(entries, date_order)
        serializable[label] = [
            {"text": text, "confidence": float(confidence)} for text, confidence in entries
        ]
    return serializable


__all__ = [
    "CROP_BOXES",
    "DATE_FORMAT_OPTIONS",
    "DEFAULT_DATE_ORDER",
    "extract_text_from_image",
    "ocr_regions_from_image",
    "ocr_regions_from_path",
    "ocr_regions_from_clipboard",
    "to_serializable",
]
