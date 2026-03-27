# 자동차 등록증 OCR → Excel 변환기

ZIP 파일 내 자동차 등록증 이미지를 OCR로 읽어 Excel 파일로 정리하는 macOS 데스크톱 앱입니다.

## 추출 항목
1. 자동차 등록번호
2. 차종
3. 차대번호
4. 소유자
5. 생년월일(법인등록번호)

## 설치 방법

```bash
# 가상환경 생성 (최초 1회)
/opt/homebrew/bin/python3.12 -m venv venv

# 의존성 설치
./venv/bin/pip install -r requirements.txt
```

## 실행 방법

```bash
# 방법 1: 실행 스크립트
./run.sh

# 방법 2: 직접 실행
./venv/bin/python3.12 main.py
```

## 사용법
1. 앱을 실행합니다.
2. "파일 선택" 버튼으로 자동차 등록증 이미지가 포함된 ZIP 파일을 선택합니다.
3. "변환 시작" 버튼을 눌러 OCR 처리를 시작합니다.
4. 처리 완료 후 Excel 파일 저장 위치를 선택합니다.

> **참고**: 최초 실행 시 EasyOCR 모델 다운로드로 인해 시간이 걸릴 수 있습니다.

## 지원 이미지 형식
- JPG / JPEG
- PNG
- BMP
- TIFF
