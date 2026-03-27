#!/usr/bin/env python3
"""
자동차 등록증 OCR → Excel 변환 데스크톱 앱
메인 엔트리포인트
"""

import sys
import os

# 현재 디렉토리를 모듈 검색 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui import VehicleRegistrationApp


def main():
    app = VehicleRegistrationApp()
    app.run()


if __name__ == '__main__':
    main()
