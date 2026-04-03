"""
자동차 등록증 변환기 GUI
- CustomTkinter 기반 모던 UI (다크/라이트 모드 지원)
- ZIP 파일 / 폴더 / 개별 이미지 및 PDF 파일 → OCR 처리 → Excel 저장
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime
import customtkinter as ctk
import unicodedata

from zip_handler import (
    extract_images_from_zip, collect_images_from_folder,
    collect_image_files, cleanup_temp_dir
)
from ocr_engine import process_single_image, get_reader
from excel_writer import create_excel

# 입력 모드
MODE_NONE = 0
MODE_ZIP = 1
MODE_FOLDER = 2
MODE_FILES = 3

# CustomTkinter 테마 설정
ctk.set_appearance_mode("System")  # 시스템 설정 지정 ("Dark", "Light", "System")
ctk.set_default_color_theme("blue")  # 기본 색상 테마 ("blue", "green", "dark-blue")

class VehicleRegistrationApp:
    """자동차 등록증 OCR 데스크톱 앱 (CustomTkinter)"""
    
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("자동차 등록증 변환기")
        self.root.geometry("750x740")
        self.root.resizable(False, False)
        
        # 상태 변수
        self.input_display = tk.StringVar(value="")
        self.status_text = tk.StringVar(value="파일 또는 폴더를 선택해주세요.")
        self.progress_var = tk.DoubleVar(value=0.0)
        
        self.is_processing = False
        self.input_mode = MODE_NONE
        self.input_data = None
        
        self._build_ui()
        self._center_window()
        
    def _center_window(self):
        """윈도우를 화면 중앙에 배치합니다."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'+{x}+{y}')
        
    def _build_ui(self):
        """UI 구성"""
        # --- 전체 여백 프레임 ---
        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=30, pady=20)
        
        # --- 헤더 구역 ---
        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))
        
        title = ctk.CTkLabel(
            header_frame, text="🚗 자동차 등록증 변환기", 
            font=ctk.CTkFont(family="맑은 고딕", size=24, weight="bold")
        )
        title.pack(anchor="w")
        
        desc = ctk.CTkLabel(
            header_frame, text="이미지 및 PDF 파일을 읽어 주요 항목을 Excel로 자동 추출합니다.",
            font=ctk.CTkFont(family="맑은 고딕", size=13), text_color="gray"
        )
        desc.pack(anchor="w", pady=(5, 0))
        
        # --- 소스 선택 구역 ---
        input_frame = ctk.CTkFrame(main_frame, corner_radius=10)
        input_frame.pack(fill="x", pady=(0, 20))
        
        input_title = ctk.CTkLabel(
            input_frame, text="📁 소스 선택", 
            font=ctk.CTkFont(family="맑은 고딕", size=14, weight="bold")
        )
        input_title.pack(anchor="w", padx=20, pady=(15, 10))
        
        btn_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        self.zip_btn = ctk.CTkButton(
            btn_frame, text="📦 ZIP 파일", command=self._select_zip,
            font=ctk.CTkFont(size=14, weight="bold"), height=45, corner_radius=8
        )
        self.zip_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.folder_btn = ctk.CTkButton(
            btn_frame, text="📂 폴더 선택", command=self._select_folder,
            font=ctk.CTkFont(size=14, weight="bold"), height=45, corner_radius=8,
            fg_color="#2E8B57", hover_color="#27704A"
        )
        self.folder_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.files_btn = ctk.CTkButton(
            btn_frame, text="📄 개별 파일", command=self._select_files,
            font=ctk.CTkFont(size=14, weight="bold"), height=45, corner_radius=8,
            fg_color="#555555", hover_color="#444444"
        )
        self.files_btn.pack(side="left", fill="x", expand=True)
        
        self.path_entry = ctk.CTkEntry(
            input_frame, textvariable=self.input_display, state="readonly",
            font=ctk.CTkFont(size=13), height=40, border_width=1, corner_radius=8
        )
        self.path_entry.pack(fill="x", padx=20, pady=(0, 20))
        
        # --- 안내 문구 구역 ---
        info_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        info_frame.pack(fill="x", pady=(0, 20))
        
        info_text = "✨ 1️⃣ 자동차 등록번호    2️⃣ 차종    3️⃣ 차대번호    4️⃣ 소유자    5️⃣ 생년월일(법인등록번호)"
        ctk.CTkLabel(info_frame, text=info_text, font=ctk.CTkFont(family="맑은 고딕", size=12), text_color="gray").pack()
        
        # --- 진행 상황 구역 ---
        progress_frame = ctk.CTkFrame(main_frame, corner_radius=10)
        progress_frame.pack(fill="x", pady=(0, 20))
        
        progress_title = ctk.CTkLabel(
            progress_frame, text="⏳ 진행 상황", 
            font=ctk.CTkFont(family="맑은 고딕", size=14, weight="bold")
        )
        progress_title.pack(anchor="w", padx=20, pady=(15, 5))
        
        self.status_label = ctk.CTkLabel(
            progress_frame, textvariable=self.status_text,
            font=ctk.CTkFont(family="맑은 고딕", size=12)
        )
        self.status_label.pack(anchor="w", padx=20)
        
        self.progress_bar = ctk.CTkProgressBar(progress_frame, height=12, corner_radius=6)
        self.progress_bar.pack(fill="x", padx=20, pady=(10, 20))
        self.progress_bar.set(0)
        
        # --- 로그 구역 ---
        log_title = ctk.CTkLabel(main_frame, text="📝 처리 로그", font=ctk.CTkFont(size=12, weight="bold"))
        log_title.pack(anchor="w", padx=5)
        
        self.log_text = ctk.CTkTextbox(
            main_frame, height=120, font=ctk.CTkFont(family="Courier", size=12),
            wrap="word", state="disabled", corner_radius=8, border_width=1
        )
        self.log_text.pack(fill="both", expand=True, pady=(5, 20))
        
        # --- 변환 시작 버튼 ---
        self.convert_btn = ctk.CTkButton(
            main_frame, text="🔄 Excel로 변환 시작", command=self._start_conversion,
            font=ctk.CTkFont(size=17, weight="bold"), height=55, corner_radius=10,
            fg_color="#006400", hover_color="#004d00"
        )
        self.convert_btn.pack(fill="x")
        
    def _log(self, message: str):
        """로그 추가"""
        self.log_text.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ─── 입력 선택 핸들러 ───
    def _select_zip(self):
        if self.is_processing: return
        filepath = filedialog.askopenfilename(
            title="ZIP 파일 선택",
            filetypes=[("ZIP 파일", "*.zip"), ("모든 파일", "*.*")]
        )
        if filepath:
            self.input_mode = MODE_ZIP
            self.input_data = filepath
            self.input_display.set(f"[ZIP] {os.path.basename(filepath)}")
            self.status_text.set(f"ZIP 파일이 선택되었습니다.")
            self._log(f"선택: {filepath}")
            
    def _select_folder(self):
        if self.is_processing: return
        folder = filedialog.askdirectory(title="이미지/PDF 폴더 선택")
        if folder:
            self.input_mode = MODE_FOLDER
            self.input_data = folder
            self.input_display.set(f"[폴더] {folder}")
            self.status_text.set(f"폴더가 선택되었습니다.")
            self._log(f"선택: {folder}")
            
    def _select_files(self):
        if self.is_processing: return
        files = filedialog.askopenfilenames(
            title="파일 선택 (이미지/PDF 여러 개 지원)",
            filetypes=[
                ("지원 파일", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.pdf"),
                ("모든 파일", "*.*")
            ]
        )
        if files:
            file_list = list(files)
            self.input_mode = MODE_FILES
            self.input_data = file_list
            self.input_display.set(f"[파일] {len(file_list)}개 선택됨")
            self.status_text.set(f"{len(file_list)}개 파일이 선택되었습니다.")
            self._log(f"개별 파일 {len(file_list)}개 선택됨")

    # ─── 변환 처리 로직 ───
    def _start_conversion(self):
        if self.is_processing:
            messagebox.showwarning("알림", "이미 처리 중입니다.")
            return
            
        if self.input_mode == MODE_NONE or not self.input_data:
            messagebox.showwarning("알림", "소스(ZIP, 폴더, 파일)를 먼저 선택해주세요.")
            return
            
        self.is_processing = True
        self._set_buttons_state("disabled")
        self.progress_bar.set(0)
        
        thread = threading.Thread(target=self._process_images, daemon=True)
        thread.start()
        
    def _set_buttons_state(self, state: str):
        self.convert_btn.configure(state=state)
        self.zip_btn.configure(state=state)
        self.folder_btn.configure(state=state)
        self.files_btn.configure(state=state)
        
    def _process_images(self):
        temp_dir = None
        try:
            self._update_status("OCR 모델 로딩 준비 중... (최초 실행 시 1~2분 소요)")
            self._log("OCR 프레임워크 초기화 중...")
            get_reader()
            self._log("OCR 프레임워크 초기화 성공.")
            
            self._update_status("입력 소스에서 데이터 수집 중...")
            
            if self.input_mode == MODE_ZIP:
                self._log("ZIP 압축 해제 중...")
                temp_dir, image_paths = extract_images_from_zip(self.input_data)
            elif self.input_mode == MODE_FOLDER:
                self._log("폴더 재귀 검색 중...")
                image_paths = collect_images_from_folder(self.input_data)
            elif self.input_mode == MODE_FILES:
                self._log("파일 포맷 검사 중...")
                image_paths = collect_image_files(self.input_data)
            else:
                raise ValueError("입력 모드 오류")
                
            total = len(image_paths)
            self._log(f"총 {total}개의 유효한 문서를 발견했습니다.")
            
            results = []
            for idx, img_path in enumerate(image_paths):
                raw_filename = os.path.basename(img_path)
                filename = unicodedata.normalize('NFC', raw_filename)
                
                progress = ((idx + 1) / total)
                
                self._update_status(f"문서 처리 중... ({idx + 1}/{total}) - {filename}")
                self._update_progress(progress * 0.9)  # 90퍼센터 상한
                self._log(f"처리 중 [{idx + 1}/{total}]: {filename}")
                
                fields = process_single_image(img_path)
                results.append({'filename': filename, 'fields': fields})
                
                reg = fields.get('자동차 등록번호', '')
                owner = fields.get('소유자', '')
                self._log(f" ┗ 등록번호: {reg or '미인식'} / 소유자: {owner or '미인식'}")
                
            self._update_status("데이터 취합 및 Excel 파일 생성 중...")
            self._update_progress(0.95)
            
            output_path = self._ask_save_path()
            if output_path:
                create_excel(results, output_path)
                self._update_progress(1.0)
                self._update_status("✨ 모든 처리 완료!")
                self._log(f"저장 성공: {output_path}")
                
                self.root.after(0, lambda: messagebox.showinfo(
                    "완료", f"데이터 변환이 성공적으로 완료되었습니다.\n\n총 {total}건 처리됨.\n{output_path}"
                ))
            else:
                self._update_status("Excel 저장이 취소되었습니다.")
                self._log("사용자가 저장을 건너뛰었습니다.")
                
        except Exception as e:
            self._update_status(f"❌ 오류: {str(e)}")
            self._log(f"오류 발생: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("오류", str(e)))
            
        finally:
            if temp_dir:
                cleanup_temp_dir(temp_dir)
            self.root.after(0, self._reset_ui_state)
            
    def _ask_save_path(self) -> str:
        """저장 경로 다이얼로그 (메인 스레드 대기)"""
        result = [None]
        event = threading.Event()
        
        def ask():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"등록증_OCR결과_{timestamp}.xlsx"
            path = filedialog.asksaveasfilename(
                title="결과 Excel 저장",
                defaultextension=".xlsx",
                initialfile=default_name,
                filetypes=[("Excel 파일", "*.xlsx")]
            )
            result[0] = path
            event.set()
            
        self.root.after(0, ask)
        event.wait()
        return result[0]
        
    def _update_status(self, msg: str):
        self.root.after(0, lambda: self.status_text.set(msg))
        
    def _update_progress(self, val: float):
        # ctk progress range is 0 to 1
        self.root.after(0, lambda: self.progress_bar.set(val))
        
    def _reset_ui_state(self):
        self.is_processing = False
        self._set_buttons_state("normal")
        
    def run(self):
        self.root.mainloop()

