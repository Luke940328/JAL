"""
OCR 엔진 모듈
- EasyOCR 기반 한국어 텍스트 추출
- 이미지 전처리 (대비 향상, 그레이스케일)
- 정규식 기반 자동차 등록증 필드 파싱
"""

import os
import re
import easyocr
import fitz  # PyMuPDF
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np

# EasyOCR reader (싱글톤 - 모델 로딩은 한 번만)
_reader = None


def get_reader():
    """EasyOCR reader를 가져옵니다 (최초 호출 시 모델 로딩)."""
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(['ko', 'en'], gpu=False)
    return _reader


def preprocess_image(image_path: str) -> list[np.ndarray]:
    """
    OCR 정확도를 높이기 위해 이미지를 전처리합니다. (PDF 지원)
    
    Args:
        image_path: 이미지 또는 PDF 파일 경로
        
    Returns:
        전처리된 이미지 numpy 배열 리스트 (여러 페이지 지원)
    """
    _, ext = os.path.splitext(image_path)
    images = []
    
    if ext.lower() == '.pdf':
        doc = fitz.open(image_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            # 해상도를 높이기 위해 2배 확대 (약 144 DPI)
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            mode = "RGBA" if pix.alpha else "RGB"
            img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
            if mode == "RGBA":
                img = img.convert("RGB")
            images.append(img)
    else:
        img = Image.open(image_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        images.append(img)
    
    processed_images = []
    for img in images:
        # 이미지가 너무 작으면 확대
        width, height = img.size
        if width < 1500:
            scale = 1500 / width
            img = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
        
        # 대비 향상
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)
        
        # 선명도 향상
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(2.0)
        
        processed_images.append(np.array(img))
        
    return processed_images


def extract_text_from_image(image_path: str) -> list[str]:
    """
    이미지 또는 PDF에서 텍스트를 추출합니다.
    
    Args:
        image_path: 이미지 또는 PDF 파일 경로
        
    Returns:
        추출된 텍스트 줄 리스트
    """
    reader = get_reader()
    processed_imgs = preprocess_image(image_path)
    
    all_texts = []
    for processed_img in processed_imgs:
        # OCR 실행
        results = reader.readtext(processed_img, detail=1, paragraph=False)
        
        # 바운딩 박스 y좌표 기준으로 정렬 (위에서 아래로)
        results.sort(key=lambda r: (r[0][0][1], r[0][0][0]))
        
        # 텍스트만 추출
        texts = [result[1] for result in results]
        all_texts.extend(texts)
    
    return all_texts


def parse_registration_fields(texts: list[str]) -> dict:
    """
    OCR 텍스트에서 자동차 등록증 필드를 추출합니다.
    
    Args:
        texts: OCR로 추출된 텍스트 리스트
        
    Returns:
        필드 딕셔너리 {등록번호, 차종, 차대번호, 소유자, 생년월일}
    """
    result = {
        '자동차 등록번호': '',
        '차종': '',
        '차대번호': '',
        '소유자': '',
        '생년월일(법인등록번호)': ''
    }
    
    # 모든 텍스트를 하나의 문자열로 합침 (줄 구분)
    full_text = '\n'.join(texts)
    # 연속 텍스트 (공백 포함)
    joined_text = ' '.join(texts)
    
    # === 1. 자동차 등록번호 ===
    # 패턴: "서울82바6009" 등 (지역명 + 숫자 + 한글 + 숫자)
    reg_number = _find_registration_number(texts, joined_text)
    if reg_number:
        result['자동차 등록번호'] = reg_number
    
    # === 2. 차종 ===
    car_type = _find_car_type(texts, joined_text)
    if car_type:
        result['차종'] = car_type
    
    # === 3. 차대번호 ===
    vin = _find_vin(texts, joined_text)
    if vin:
        result['차대번호'] = vin
    
    # === 4. 소유자 ===
    owner = _find_owner(texts, joined_text)
    if owner:
        result['소유자'] = owner
    
    # === 5. 생년월일(법인등록번호) ===
    birth = _find_birth_or_corp_number(texts, joined_text)
    if birth:
        result['생년월일(법인등록번호)'] = birth
    
    return result


def _find_registration_number(texts: list[str], joined: str) -> str:
    """자동차 등록번호를 찾습니다."""
    # 패턴: 지역명 + 숫자 + 한글 + 숫자 (예: 서울82바6009)
    pattern = r'([가-힣]{2,4}\s*\d{2,3}\s*[가-힣]\s*\d{4})'
    
    for text in texts:
        match = re.search(pattern, text.replace(' ', ''))
        if match:
            return match.group(1)
    
    # joined에서도 시도
    match = re.search(pattern, joined.replace(' ', ''))
    if match:
        return match.group(1)
    
    # 등록번호 라벨 뒤의 값 찾기
    for i, text in enumerate(texts):
        if '등록번호' in text.replace(' ', '') and i + 1 < len(texts):
            # 다음 텍스트에서 번호 패턴 찾기
            next_text = texts[i + 1].replace(' ', '')
            match = re.search(pattern, next_text)
            if match:
                return match.group(1)
            # 번호판 패턴이 없으면 그냥 다음 텍스트 반환
            if re.search(r'\d', next_text):
                return texts[i + 1].strip()
    
    return ''


def _find_car_type(texts: list[str], joined: str) -> str:
    """차종을 찾습니다."""
    # "차종" 라벨 뒤의 값
    for i, text in enumerate(texts):
        cleaned = text.replace(' ', '')
        if '차종' in cleaned:
            # 같은 텍스트에서 차종 뒤의 값
            idx = cleaned.find('차종')
            after = cleaned[idx + 2:].strip()
            if after:
                return after
            # 다음 텍스트
            if i + 1 < len(texts):
                return texts[i + 1].strip()
    
    # "대형" "화물" 등 키워드 조합 찾기
    car_types = ['대형화물', '소형승용', '중형승용', '대형승용', '소형화물', 
                 '중형화물', '소형승합', '중형승합', '대형승합', '특수']
    for ct in car_types:
        if ct in joined.replace(' ', ''):
            return ct
    
    return ''


def _find_vin(texts: list[str], joined: str) -> str:
    """차대번호(VIN)를 찾습니다."""
    # VIN은 17자리 영숫자 (일반적)
    vin_pattern = r'[A-HJ-NPR-Z0-9]{17}'
    
    for text in texts:
        cleaned = text.replace(' ', '').replace('-', '').upper()
        match = re.search(vin_pattern, cleaned)
        if match:
            return match.group(0)
    
    # "차대번호" 라벨 뒤에서 찾기
    for i, text in enumerate(texts):
        cleaned = text.replace(' ', '')
        if '차대번호' in cleaned or ('차' in cleaned and '번호' in cleaned and '대' in cleaned):
            # 같은 텍스트에서 값 추출
            match = re.search(vin_pattern, cleaned.upper())
            if match:
                return match.group(0)
            # 다음 텍스트들에서 찾기
            for j in range(i + 1, min(i + 3, len(texts))):
                next_cleaned = texts[j].replace(' ', '').replace('-', '').upper()
                match = re.search(vin_pattern, next_cleaned)
                if match:
                    return match.group(0)
    
    # VIN이 정확히 17자리가 아닐 수도 있으므로 긴 영숫자 패턴도 시도
    long_pattern = r'[A-HJ-NPR-Z0-9]{10,}'
    for text in texts:
        cleaned = text.replace(' ', '').replace('-', '').upper()
        match = re.search(long_pattern, cleaned)
        if match and len(match.group(0)) >= 12:
            return match.group(0)
    
    return ''


def _find_owner(texts: list[str], joined: str) -> str:
    """소유자를 찾습니다."""
    # "소유자" 라벨 근처에서 성명 찾기
    for i, text in enumerate(texts):
        cleaned = text.replace(' ', '')
        if '소유자' in cleaned:
            # "성명" 라벨 찾기
            for j in range(i, min(i + 5, len(texts))):
                if '성명' in texts[j].replace(' ', ''):
                    # 성명 다음 텍스트
                    for k in range(j + 1, min(j + 3, len(texts))):
                        candidate = texts[k].strip()
                        # 한글 이름 또는 회사명 (2글자 이상)
                        if re.search(r'[가-힣]{2,}', candidate) and '생년' not in candidate and '법인' not in candidate:
                            return candidate
            
            # 성명 라벨 없으면 소유자 다음 텍스트에서 한글 이름 찾기
            for j in range(i + 1, min(i + 4, len(texts))):
                candidate = texts[j].strip()
                if re.search(r'[가-힣]{2,}', candidate) and not any(
                    kw in candidate for kw in ['성명', '생년', '법인', '주소', '사용', '본거지']
                ):
                    return candidate
    
    return ''


def _find_birth_or_corp_number(texts: list[str], joined: str) -> str:
    """생년월일 또는 법인등록번호를 찾습니다."""
    # "생년월일" 또는 "법인등록번호" 라벨 근처에서 값 찾기
    for i, text in enumerate(texts):
        cleaned = text.replace(' ', '')
        if '생년월일' in cleaned or '법인등록번호' in cleaned:
            # 같은 텍스트의 숫자 부분
            numbers = re.findall(r'\d[\d-]+\d', cleaned)
            if numbers:
                return numbers[-1]
            
            # 다음 텍스트들에서 숫자 패턴 찾기
            for j in range(i + 1, min(i + 3, len(texts))):
                next_text = texts[j].strip()
                # 주민번호 패턴 (6자리-7자리) 또는 법인등록번호 (6자리-7자리)
                match = re.search(r'(\d{6}\s*[-–]\s*\d{7})', next_text)
                if match:
                    return match.group(1).replace(' ', '')
                # 숫자만 있는 경우
                numbers = re.findall(r'\d[\d-]+\d', next_text)
                if numbers:
                    return numbers[0]
    
    return ''


def process_single_image(image_path: str) -> dict:
    """
    단일 이미지를 처리하여 자동차 등록증 정보를 추출합니다.
    
    Args:
        image_path: 이미지 파일 경로
        
    Returns:
        추출된 필드 딕셔너리
    """
    try:
        texts = extract_text_from_image(image_path)
        fields = parse_registration_fields(texts)
        return fields
    except Exception as e:
        return {
            '자동차 등록번호': f'[오류: {str(e)}]',
            '차종': '',
            '차대번호': '',
            '소유자': '',
            '생년월일(법인등록번호)': ''
        }
