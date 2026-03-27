#!/bin/bash
# 자동차 등록증 변환기 - 실무자 배포용 독립 실행 앱 빌드 스크립트

echo "필요한 빌드 도구를 설치합니다..."
./venv/bin/pip install pyinstaller

echo "라이브러리 경로를 가져옵니다..."
CTK_PATH=$(./venv/bin/python3.12 -c "import customtkinter, os; print(os.path.dirname(customtkinter.__file__))")
EASYOCR_PATH=$(./venv/bin/python3.12 -c "import easyocr, os; print(os.path.dirname(easyocr.__file__))")

echo "PyInstaller를 사용해 macOS 앱(.app)으로 번들링합니다..."
./venv/bin/pyinstaller --noconfirm --onedir --windowed \
    --name "AutoOCR_App" \
    --add-data "$CTK_PATH:customtkinter/" \
    --add-data "$EASYOCR_PATH:easyocr/" \
    main.py

echo "======================================"
echo "빌드가 완료되었습니다!"
echo "생성된 앱 위치: dist/AutoOCR_App.app"
echo "이 폴더를 압축해서 실무자에게 전달하세요."
echo "======================================"
