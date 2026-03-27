"""
파일 입력 처리 모듈
- ZIP 파일 압축 해제
- 폴더 내 이미지 수집
- 개별 파일 필터링
- 임시 디렉토리 관리
"""

import os
import zipfile
import tempfile
import shutil

# 지원하는 파일 확장자
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.pdf'}


def extract_images_from_zip(zip_path: str) -> tuple[str, list[str]]:
    """
    ZIP 파일에서 이미지 파일들을 추출합니다.
    
    Args:
        zip_path: ZIP 파일 경로
        
    Returns:
        (임시 디렉토리 경로, 이미지 파일 경로 리스트) 튜플
        
    Raises:
        ValueError: ZIP 파일이 아닌 경우
        FileNotFoundError: 파일이 존재하지 않는 경우
    """
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {zip_path}")
    
    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"유효한 ZIP 파일이 아닙니다: {zip_path}")
    
    # 임시 디렉토리 생성
    temp_dir = tempfile.mkdtemp(prefix="jal_ocr_")
    
    image_paths = []
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for entry in zf.infolist():
                # 디렉토리는 건너뜀
                if entry.is_dir():
                    continue
                
                # __MACOSX 및 숨김 파일 건너뜀
                if '__MACOSX' in entry.filename or os.path.basename(entry.filename).startswith('.'):
                    continue
                
                # 이미지 파일만 추출
                _, ext = os.path.splitext(entry.filename)
                if ext.lower() in SUPPORTED_EXTENSIONS:
                    # 파일명만 사용 (디렉토리 구조 무시)
                    filename = os.path.basename(entry.filename)
                    
                    # 중복 파일명 처리
                    dest_path = os.path.join(temp_dir, filename)
                    counter = 1
                    while os.path.exists(dest_path):
                        name, ext_part = os.path.splitext(filename)
                        dest_path = os.path.join(temp_dir, f"{name}_{counter}{ext_part}")
                        counter += 1
                    
                    # 파일 추출
                    with zf.open(entry) as source, open(dest_path, 'wb') as target:
                        target.write(source.read())
                    
                    image_paths.append(dest_path)
        
        # 파일명 기준 정렬
        image_paths.sort(key=lambda p: os.path.basename(p))
        
    except Exception as e:
        # 에러 발생 시 임시 디렉토리 정리
        cleanup_temp_dir(temp_dir)
        raise e
    
    if not image_paths:
        cleanup_temp_dir(temp_dir)
        raise ValueError("ZIP 파일 내에 이미지 파일이 없습니다.")
    
    return temp_dir, image_paths


def collect_images_from_folder(folder_path: str) -> list[str]:
    """
    폴더에서 이미지 파일들을 수집합니다 (하위 폴더 포함).
    
    Args:
        folder_path: 폴더 경로
        
    Returns:
        이미지 파일 경로 리스트
        
    Raises:
        ValueError: 폴더가 아닌 경우 또는 이미지가 없는 경우
        FileNotFoundError: 폴더가 존재하지 않는 경우
    """
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"폴더를 찾을 수 없습니다: {folder_path}")
    
    if not os.path.isdir(folder_path):
        raise ValueError(f"유효한 폴더가 아닙니다: {folder_path}")
    
    image_paths = []
    
    for root, dirs, files in os.walk(folder_path):
        # 숨김 디렉토리 건너뜀
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__MACOSX']
        
        for filename in files:
            if filename.startswith('.'):
                continue
            _, ext = os.path.splitext(filename)
            if ext.lower() in SUPPORTED_EXTENSIONS:
                image_paths.append(os.path.join(root, filename))
    
    image_paths.sort(key=lambda p: os.path.basename(p))
    
    if not image_paths:
        raise ValueError("폴더 내에 이미지 파일이 없습니다.")
    
    return image_paths


def collect_image_files(file_paths: list[str]) -> list[str]:
    """
    파일 경로 리스트에서 이미지 파일만 필터링합니다.
    
    Args:
        file_paths: 파일 경로 리스트
        
    Returns:
        이미지 파일 경로 리스트
        
    Raises:
        ValueError: 이미지 파일이 없는 경우
    """
    image_paths = []
    
    for fp in file_paths:
        if not os.path.exists(fp):
            continue
        _, ext = os.path.splitext(fp)
        if ext.lower() in SUPPORTED_EXTENSIONS:
            image_paths.append(fp)
    
    image_paths.sort(key=lambda p: os.path.basename(p))
    
    if not image_paths:
        raise ValueError("선택한 파일 중 이미지 파일이 없습니다.")
    
    return image_paths


def cleanup_temp_dir(temp_dir: str):
    """임시 디렉토리를 삭제합니다."""
    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)

