@echo off
chcp 65001 >nul
title 자동차 등록증 변환기

echo ==========================================
echo    자동차 등록증 변환기를 시작합니다...
echo ==========================================
echo.

:: 1. 파이썬 설치 여부 확인
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] PC에 파이썬(Python)이 설치되어 있지 않습니다.
    echo.
    echo 1. 마이크로소프트 스토어(Microsoft Store)를 엽니다.
    echo 2. 검색창에 "Python 3.12"를 검색하여 설치 버튼을 누릅니다.
    echo 3. 설치가 완료된 후 이 파일을 다시 더블클릭해주세요.
    echo.
    pause
    exit /b
)

:: 2. 가상환경(venv) 생성 및 라이브러리 설치 (최초 1회만 동작)
if not exist "venv" (
    echo [초기 설정 진행 중] (최초 실행 시 1~3분 정도 소요됩니다)
    echo 파이썬 개발 환경을 구축하고 있습니다...
    python -m venv venv
    
    echo.
    echo 딥러닝 및 그래픽 처리 라이브러리를 다운로드 중입니다... (잠시만 기다려주세요)
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip >nul 2>&1
    pip install -r requirements.txt
    echo 기초 설정이 끝났습니다!
    echo.
) else (
    call venv\Scripts\activate.bat
)

:: 3. 프로그램 실행
echo 프로그램 창을 띄우는 중입니다...
python main.py

:: 프로그램이 오류로 꺼질 경우를 대비해 콘솔이 잠시 유지되도록 함
pause
