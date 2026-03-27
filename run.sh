#!/bin/bash
# 자동차 등록증 OCR 변환기 실행 스크립트
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/venv/bin/python3.12" "$SCRIPT_DIR/main.py"
