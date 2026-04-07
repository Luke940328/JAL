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
import base64
import json
import requests
import io

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
    # 패턴: (지역명 2자리)? + 숫자 2~3자리 + 한글 1자리(또는 OCR오류 숫자) + 숫자 4자리
    # "등록번호"가 지역명으로 잡히는 것을 방지
    pattern = r'((?:[가-힣]{2}\s*)?\d{2,3}\s*[가-힣0-9]\s*\d{4})'
    
    # 1) "자동차등록번호" 라벨 근처에서 우선 탐색
    for i, text in enumerate(texts):
        cleaned = text.replace(' ', '')
        if '자동차등록번호' in cleaned and '전' not in cleaned and '이전' not in cleaned:
            # 같은 텍스트에서
            match = re.search(pattern, cleaned)
            if match:
                return match.group(1)
            # 주변 텍스트 (앞뒤 5개 - 줄바꿈 잦음 감안)
            for j in range(max(0, i - 2), min(i + 6, len(texts))):
                if j == i:
                    continue
                match = re.search(pattern, texts[j].replace(' ', ''))
                if match:
                    return match.group(1)
    
    # 2) 전체에서 찾기
    for text in texts:
        match = re.search(pattern, text.replace(' ', ''))
        if match:
            return match.group(1)
    
    # 3) joined에서도 시도
    match = re.search(pattern, joined.replace(' ', ''))
    if match:
        return match.group(1)
    
    return ''


def _find_car_type(texts: list[str], joined: str) -> str:
    """차종을 찾습니다."""
    # 차종 키워드 목록
    car_type_keywords = [
        '대형화물', '중형화물', '소형화물', 
        '대형승용', '중형승용', '소형승용',
        '대형승합', '중형승합', '소형승합',
        '대형특수', '중형특수', '소형특수',
        '특수', '경형'
    ]
    
    # 1) "차종" 또는 "차 종" 라벨 근처에서 찾기
    for i, text in enumerate(texts):
        cleaned = text.replace(' ', '')
        is_car_type_label = False
        
        # "차종"이 포함된 경우 (단, "자동차종합" 등은 제외)
        if '차종' in cleaned and '자동차종' not in cleaned:
            is_car_type_label = True
            # 같은 텍스트에서 값 추출 (예: "종 | 중형 화물")
            idx = cleaned.find('차종')
            after = cleaned[idx + 2:].strip()
            # 파이프, 구두점 제거
            after = re.sub(r'[|｜\s]', '', after)
            if after:
                # 차종 키워드 매칭
                for ct in car_type_keywords:
                    if ct in after:
                        return ct
                if re.search(r'[가-힣]{2,}', after):
                    return after
        
        # "차"와 "종"이 분리되어 있는 경우 (@차 ... 종)
        if cleaned in ['차', '@차'] and i + 1 < len(texts) and '종' in texts[i + 1].replace(' ', ''):
            is_car_type_label = True
        
        if is_car_type_label:
            # 주변 텍스트에서 차종 키워드 찾기
            for j in range(max(0, i - 2), min(i + 5, len(texts))):
                if j == i:
                    continue
                nearby = texts[j].replace(' ', '')
                for ct in car_type_keywords:
                    if ct in nearby:
                        return ct
                # "대형 화물" 같이 분리된 형태
                nearby_with_space = texts[j].strip()
                parts = nearby_with_space.split()
                if len(parts) >= 2:
                    combined = ''.join(parts)
                    for ct in car_type_keywords:
                        if ct in combined:
                            return ct
    
    # 2) 전체에서 키워드 조합 찾기
    joined_no_space = joined.replace(' ', '')
    for ct in car_type_keywords:
        if ct in joined_no_space:
            return ct
    
    return ''


def _is_vin_candidate(text: str) -> bool:
    """텍스트가 VIN 후보로 적합한지 확인합니다."""
    # 하이픈이 2개 이상이면 제원관리번호일 가능성 높음
    if text.count('-') >= 2:
        return False
    
    cleaned = text.replace(' ', '').replace('-', '').upper()
    
    # 순수 숫자만이면 VIN이 아님 (문서확인번호, 제 번호 등)
    if cleaned.isdigit():
        return False
    
    # VIN은 반드시 알파벳을 포함해야 함 (최소 1개, OCR 오류 감안 전체 알파벳 허용)
    if not re.search(r'[A-Z]', cleaned):
        return False
    
    return True


def _find_vin(texts: list[str], joined: str) -> str:
    """차대번호(VIN)를 찾습니다."""
    vin_pattern = r'[A-Z0-9]{17}'
    
    def clean_vin(vin_str: str) -> str:
        # VIN 표준상 I, O, Q는 사용되지 않음 (숫자 1, 0과 혼동 방지)
        # OCR에서 이 문자들이 발견되면 숫자로 교정
        cleaned = vin_str.replace('I', '1').replace('O', '0').replace('Q', '0')
        
        # 10번째 자리 (제작연도)에는 추가로 U, Z, 0 이 사용되지 않음
        if len(cleaned) == 17:
            chars = list(cleaned)
            # 인덱스 9는 10번째 자리
            if chars[9] == 'U':
                chars[9] = 'V'  # U -> V 오인식 교정
            elif chars[9] == 'Z':
                chars[9] = '2'  # Z -> 2 오인식 교정
            elif chars[9] == '0':
                chars[9] = 'D'  # 0(또는 원래 O/Q) -> D 오인식 교정
            cleaned = ''.join(chars)
            
        return cleaned
    
    # 제외 라벨들 (이 라벨 자체이거나 직접적 연관 텍스트는 건너뛰기)
    skip_labels = ['원동기형식', '원동기', '형식', '사용본거지', '사용본', '본거지', 
                   '제원관리', '형식승인', '제작연월', '모델연도']
    
    # 1. "차대번호" 라벨 근처에서 우선적으로 찾기
    for i, text in enumerate(texts):
        cleaned = text.replace(' ', '')
        # "차대번호", "차 대번호", "차 대 번 호" 등 
        if '차대번호' in cleaned or '차대번' in cleaned:
            # 같은 텍스트에서 값 추출
            val_cleaned = cleaned.upper().replace('-', '')
            match = re.search(vin_pattern, val_cleaned)
            if match:
                return clean_vin(match.group(0))
            
            # 다음 텍스트들에서 찾기 (원동기형식 라벨 전까지)
            for j in range(i + 1, min(i + 5, len(texts))):
                next_text = texts[j]
                next_cleaned_raw = next_text.replace(' ', '')
                
                # 다른 라벨을 만나면 중단
                if any(sl in next_cleaned_raw for sl in skip_labels):
                    # 하지만 이 라벨 텍스트에 VIN이 함께 있을 수 있음
                    # (예: "원동기형식D4GB" 는 아닌데 "원 동 기 형 식D4GA" 같은 경우)
                    continue
                
                if not _is_vin_candidate(next_text):
                    continue
                
                next_cleaned = next_text.replace(' ', '').replace('-', '').upper()
                match = re.search(vin_pattern, next_cleaned)
                if match:
                    return clean_vin(match.group(0))
                
                # 17자리가 안되더라도 12자리 이상이면 반환 (OCR 인식 오류 감안)
                long_match = re.search(r'[A-Z][A-Z0-9]{11,}', next_cleaned)
                if long_match:
                    return clean_vin(long_match.group(0))

    # 2. 라벨로 못 찾은 경우 전체 텍스트에서 17자리 패턴 검색
    for text in texts:
        if not _is_vin_candidate(text):
            continue
        
        cleaned = text.replace(' ', '').replace('-', '').upper()
        match = re.search(vin_pattern, cleaned)
        if match:
            # VIN은 반드시 알파벳으로 시작
            vin_val = match.group(0)
            if re.search(r'[A-Z]', vin_val):
                return clean_vin(vin_val)
    
    # 3. 최후의 수단: 알파벳으로 시작하는 12자리 이상 영숫자
    long_pattern = r'[A-Z][A-Z0-9]{11,}'
    for text in texts:
        if not _is_vin_candidate(text):
            continue
        cleaned = text.replace(' ', '').replace('-', '').upper()
        match = re.search(long_pattern, cleaned)
        if match:
            return clean_vin(match.group(0))
    
    return ''


def _is_owner_candidate(text: str) -> str:
    """텍스트가 소유자 이름/회사명 후보로 적합한지 확인합니다."""
    cleaned = text.strip()
    if not cleaned:
        return ''
    
    # 제외 키워드 (라벨이거나 관련 없는 텍스트)
    exclude_keywords = [
        '성명', '명칭', '소유자', '생년월일', '법인등록번호', '법인', 
        '주소', '사용', '본거지', '자동차관리법', '증명합니다', '등록하',
        '유의사항', '전기자동차', '수소전기', '원동기', '구동전동기', '등록번호',
        '차종', '차대번호', '형식', '제작연월', '용도', '영업용', '자가용',
        '최초등록일', '이전', '번호변경', '시장', '구청', '장인', '장안',
        '서울특별시', '경기도', '인천', '부산', '울산', '제주',
        '검사', '제원', '자동차등록', '차등록증', '규칙', '별지', '개정',
        '문서확인', '호서식', '면중', '자동', '차관리',
        '변경', '과태료', '범칙금', '이내', '최고', '만원', '상회', '등록증'
    ]
    
    for kw in exclude_keywords:
        if kw in cleaned.replace(' ', ''):
            return ''
    
    # 날짜 패턴 제외
    if re.search(r'\d{4}\s*년|\d{2}\s*월|\d{2}\s*일', cleaned):
        return ''
    
    # 순수 숫자/기호만이면 제외
    if re.match(r'^[\d\s\-\.\,\(\)\[\]@#*]+$', cleaned):
        return ''
    
    # 한 글자만이면 제외
    korean_chars = re.findall(r'[가-힣]', cleaned)
    if len(korean_chars) < 2:
        return ''
    
    # 한글 이름(2~5글자) 또는 회사명(한글 2글자 이상 포함)
    if re.search(r'[가-힣]{2,}', cleaned):
        return cleaned
    
    return ''


def _find_owner(texts: list[str], joined: str) -> str:
    """소유자를 찾습니다."""
    
    # 1) "성명(명칭)" 또는 "성명" 라벨 기반 탐색
    for i, text in enumerate(texts):
        cleaned = text.replace(' ', '')
        
        # "소유자 @성명(명칭)" 같이 합쳐진 패턴
        if '소유자' in cleaned and ('성명' in cleaned or '명칭' in cleaned):
            if any(kw in cleaned for kw in ['변경', '이내', '최고', '만원', '과태료']):
                continue
            
            # 같은 줄에서 먼저 추출 시도
            val_cleaned = re.sub(r'소유자|성명|명칭|@|\(|\)', '', texts[i]).strip()
            candidate = _is_owner_candidate(val_cleaned)
            if candidate:
                return candidate
                
            # 주변 텍스트에서 이름 찾기 (앞뒤 탐색)
            for j in range(max(0, i - 3), min(i + 4, len(texts))):
                if j == i:
                    continue
                candidate = _is_owner_candidate(texts[j])
                if candidate:
                    return candidate
        
        # "성명(명칭)" 또는 "성명" 라벨
        if '성명' in cleaned or '명칭' in cleaned:
            if any(kw in cleaned for kw in ['변경', '이내', '최고', '만원', '과태료']):
                continue
            
            # 같은 줄에서 추출 시도
            val_cleaned = re.sub(r'성명|명칭|@|\(|\)', '', texts[i]).strip()
            candidate = _is_owner_candidate(val_cleaned)
            if candidate:
                return candidate
                
            # 라벨 주변(앞뒤)에서 이름 찾기
            # OCR에서 이름이 라벨 앞에 올 수도 있고 뒤에 올 수도 있음
            for j in range(max(0, i - 3), min(i + 4, len(texts))):
                if j == i:
                    continue
                candidate = _is_owner_candidate(texts[j])
                if candidate:
                    return candidate
    
    # 2) "소유자" 라벨 기반 탐색
    for i, text in enumerate(texts):
        cleaned = text.replace(' ', '')
        if '소유자' in cleaned:
            for j in range(max(0, i - 3), min(i + 5, len(texts))):
                if j == i:
                    continue
                candidate = _is_owner_candidate(texts[j])
                if candidate:
                    return candidate
    
    return ''


def _find_birth_or_corp_number(texts: list[str], joined: str) -> str:
    """생년월일 또는 법인등록번호를 찾습니다."""
    def clean_digits(text: str) -> str:
        # 이 필드는 반드시 숫자와 하이픈만 포함해야 하므로
        # 숫자로 자주 오인식되는 알파벳 문자를 숫자로 강제 교정합니다.
        mapping = str.maketrans('IlOoSsZzBG', '1100552286')
        return text.translate(mapping)
        
    # 주민번호/법인등록번호 패턴: 6자리-7자리
    id_pattern = r'(\d{6}\s*[-–]\s*\d{7})'
    
    # 1) "생년월일" 또는 "법인등록번호" 또는 "(법인등록번호)" 라벨 기반 탐색
    label_indices = []
    for i, text in enumerate(texts):
        cleaned = text.replace(' ', '')
        if '생년월일' in cleaned or '법인등록번호' in cleaned or '법인등록' in cleaned:
            label_indices.append(i)
    
    for li in label_indices:
        # 라벨 주변(앞뒤)에서 번호 패턴 찾기
        for j in range(max(0, li - 4), min(li + 5, len(texts))):
            if j == li:
                continue
            next_text = clean_digits(texts[j].strip())
            # 6자리-7자리 패턴
            match = re.search(id_pattern, next_text)
            if match:
                return match.group(1).replace(' ', '')
    
    # 2) 라벨 주변에서 6자리-7자리가 아닌 숫자-숫자 패턴(날짜 등 제외)도 시도
    for li in label_indices:
        for j in range(max(0, li - 4), min(li + 5, len(texts))):
            if j == li:
                continue
            next_text = clean_digits(texts[j].strip())
            # 13자리 연속 숫자 (하이픈 없이 인식된 경우)
            match = re.search(r'(\d{13})', next_text.replace(' ', '').replace('-', ''))
            if match:
                num = match.group(1)
                return f"{num[:6]}-{num[6:]}"
            # 숫자-숫자 형태 (다양한 패턴)
            numbers = re.findall(r'\d[\d-]+\d', next_text)
            for num in numbers:
                # 날짜 패턴 제외 (YYYY-MM-DD)
                if re.match(r'^\d{4}-\d{2}-\d{2}$', num):
                    continue
                # 최소 10자리 이상의 숫자 패턴
                digits_only = num.replace('-', '')
                if len(digits_only) >= 10:
                    return num
    
    # 3) 전체에서 주민번호/법인번호 패턴 검색 (최후의 수단)
    for text in texts:
        cleaned_text = clean_digits(text)
        match = re.search(id_pattern, cleaned_text)
        if match:
            val = match.group(1).replace(' ', '')
            # 날짜가 아닌지 확인
            if not re.match(r'^\d{4}-\d{2}', val):
                return val
    
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
