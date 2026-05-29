# 비식별화 도구 (De-identification Tool)

사내 문서(xlsx, docx, pptx, hwpx, pdf)에 포함된 개인정보·민감정보를 탐지하고 비식별화 처리를 안내하는 FastAPI 기반 도구입니다.

---

## 빠른 시작

```bash
# 의존성 설치 (루트의 requirements.txt 아님 — src/api/ 것 사용)
pip install -r src/api/requirements.txt

# 서버 실행
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

브라우저에서 `http://127.0.0.1:8000` 접속 → HTML UI  
`http://127.0.0.1:8000/docs` → Swagger UI (API 테스트)

---

## 등급 체계

| 등급 | 의미 | 처리 원칙 |
|------|------|-----------|
| **C** | 기밀 (Confidential) | 외부 AI 사용 불가. 삭제 또는 비식별화 필수 |
| **S** | 민감 (Sensitive) | 비식별화 후 제한적 사용 가능 |
| **O** | 일반 (Open) | 그대로 사용 가능 |

---

## 폴더 구조

```
(프로젝트 루트)/
│
├── src/                        # 서버 소스 코드
│   ├── api/                    # FastAPI 엔드포인트
│   ├── feedback/               # 피드백 저장 모듈
│   ├── regex_detector.py       # 정규식 탐지
│   ├── docx_detector.py        # docx 탐지
│   ├── pptx_detector.py        # pptx 탐지
│   ├── hwpx_detector.py        # hwpx 탐지
│   ├── pdf_detector.py         # pdf 탐지
│   ├── xlsx_deidentify_apply.py # xlsx 비식별화 적용
│   ├── deidentify_target_builder.py
│   ├── deidentify_apply.py
│   ├── document_units.py
│   ├── common_apply_result.py
│   ├── common_apply_utils.py
│   ├── korean_ner_adapter.py
│   ├── ner_units.py
│   └── ner_detection_converter.py
│
├── static/
│   └── index.html              # HTML UI
│
├── models/                     # 모델 파일 (별도 전달)
│   ├── privacy_sentence_model_v3.pkl       # AI 분류 모델 (sklearn)
│   ├── privacy_cso_char_keras_model.keras  # AI 분류 모델 (keras, 선택)
│   └── hf/KoELECTRA-small-v3-modu-ner/    # NER 성명 탐지 모델 (선택)
│
├── data/                       # 학습 데이터 및 테스트 샘플
├── notebooks/                  # 모델 학습·실험 스크립트
├── feedback_data/              # 사용자 피드백 JSON (서버 운영 중 자동 생성)
├── logs/                       # 서버 로그 (자동 생성)
├── reports/                    # 주차별 개발 보고서
│
├── .env                        # 환경 변수 설정
└── src/api/requirements.txt    # 의존성 목록
```

---

## src/ 파일별 역할

### API 레이어 (`src/api/`)

| 파일 | 역할 |
|------|------|
| `main.py` | FastAPI 앱 진입점. 라우터 등록, 로깅 설정, 서버 시작 시 모델 상주 로딩(lifespan) |
| `detect_router.py` | `POST /api/detect` 엔드포인트. 파일 형식 판별 후 detector로 분기. NER/AI 모델 전역 캐시 관리 |
| `feedback_router.py` | `POST /api/feedback`, `GET /api/feedback/stats|list` 엔드포인트 |
| `analyze_feedback.py` | 피드백 데이터 분석 CLI 스크립트. 오탐율·동의율 집계, 재학습 데이터셋 추출 |
| `errors.py` | API 공통 에러 응답 모델 |
| `files.py` | 업로드 임시 파일 관리, xlsx downloadToken 생성·조회·만료 처리 |

### 피드백 모듈 (`src/feedback/`)

| 파일 | 역할 |
|------|------|
| `models.py` | 피드백 데이터 모델 (`UserFeedback`) |
| `store.py` | 피드백 JSON 날짜별 파일 저장소. `threading.Lock`으로 동시 접근 방지 |

### 탐지 엔진 (`src/`)

| 파일 | 역할 |
|------|------|
| `regex_detector.py` | 이메일, 전화번호, IP, VLAN, 사번 등 정규식 패턴 탐지. `detect_patterns(text)` → Detection 목록 반환 |
| `docx_detector.py` | docx 파일 단락·표 셀 순회 → regex/NER/AI 탐지 → `DeidentifyPlan` 생성 |
| `pptx_detector.py` | pptx 슬라이드·도형·표 셀 순회 → 탐지 → `DeidentifyPlan` 생성 |
| `hwpx_detector.py` | hwpx(한글) XML 파싱 → 단락·표 셀 순회 → 탐지 → `DeidentifyPlan` 생성 |
| `pdf_detector.py` | pdfplumber로 줄 단위 추출 → 탐지 → `DeidentifyPlan` 생성 |
| `xlsx_deidentify_apply.py` | xlsx 셀 탐지 후 `DeidentifyPlan`을 실제 파일에 적용해 비식별화된 xlsx 생성 |

### 비식별화 처리 (`src/`)

| 파일 | 역할 |
|------|------|
| `deidentify_target_builder.py` | regex/NER/AI Detection 목록을 받아 `DeidentifyPlan`(auto_targets + review_targets) 생성 |
| `deidentify_apply.py` | `DeidentifyTarget`을 원문 문자열에 적용해 비식별화 문자열 반환. 마스킹·삭제 처리 |

### 공통 자료구조 (`src/`)

| 파일 | 역할 |
|------|------|
| `document_units.py` | 파일 형식 공통 자료구조. `TextParagraph`, `DeidentifyTarget`, `DeidentifyPlan` 등 |
| `common_apply_result.py` | API 응답용 결과 구조. `CommonApplyItem`(autoResults), `CommonReviewItem`(reviewTargets) |
| `common_apply_utils.py` | 파일 형식별 Apply 공통 유틸리티. warning 타입 상수, 위치 매칭 헬퍼 |

### NER 관련 (`src/`)

| 파일 | 역할 |
|------|------|
| `ner_units.py` | NER 공통 자료구조. `EntitySpan` (탐지된 개체 구간) |
| `korean_ner_adapter.py` | HuggingFace NER 모델 출력 → `EntitySpan` 변환 어댑터 |
| `ner_detection_converter.py` | `EntitySpan` → Detection dict 변환. detector에서 NER 결과를 regex 결과와 같은 형태로 통합 |

---

## 처리 흐름

```
POST /api/detect (파일 + 옵션)
        │
        ▼
  detect_router.py
  ├── 파일 형식 판별 (xlsx → applied, 나머지 → guide)
  │
  ├── [xlsx] xlsx_deidentify_apply.py
  │     regex → NER → AI 탐지 후 셀 직접 수정 → 결과 파일 생성
  │
  └── [docx/pptx/hwpx/pdf] *_detector.py
        단락/줄 순회
        ├── regex_detector     → Detection 목록
        ├── korean_ner_adapter → EntitySpan → Detection (NER)
        └── AI 모델            → grade/confidence (regex 미탐 시만)
              │
              ▼
        deidentify_target_builder.py
              │  Detection 목록 → DeidentifyPlan
              ▼
        common_apply_result.py
              autoResults + reviewTargets 구조로 변환
              │
              ▼
        JSON 응답
```

---

## 환경 변수 (.env)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `AI_MODEL_TYPE` | `keras` | `sklearn` \| `keras` |
| `SKLEARN_MODEL_PATH` | `models/privacy_sentence_model_v3.pkl` | sklearn 모델 경로 |
| `AI_MODEL_PATH` | `models/privacy_cso_char_keras_model.keras` | Keras 모델 경로 |
| `NER_MODEL_PATH` | (없음) | NER 모델 경로. 미설정 시 NER 비활성 |
| `NER_THRESHOLD` | `0.8` | NER 탐지 신뢰도 임계값 |
| `AI_THRESHOLD` | `0.5` | AI 탐지 신뢰도 임계값 |
| `FEEDBACK_DIR` | `feedback_data/` | 피드백 저장 디렉토리 |
| `LOG_DIR` | `logs/` | 로그 저장 디렉토리 |

---

## 관련 문서

| 문서 | 설명 |
|------|------|
| `src/api/README.md` | 서버 실행 상세 가이드 |
| `reports/api_usage_guide.md` | API 응답 구조 및 활용 가이드 |
| `reports/week17_detector_policy.md` | 탐지 소스 역할 분담 정책 |
| `data/labeling_guide_v3.md` | AI 모델 학습 데이터 라벨링 기준 |
