# 비식별화 도구 프로젝트 진행 현황 및 인수인계 문서

작성일: 2026-05-27  
작성: AI혁신TF단 빅데이터팀  
다음 세션 시작: 19주차

---

## 1. 프로젝트 개요

사내 문서의 개인정보/민감정보를 자동으로 탐지하고 비식별화를 안내하는 도구.

**최종 목표**: 사내 서버에 배포하는 독립 웹 서비스 (FastAPI + HTML)

**현재 상태**: 18주차 완료, 로컬 테스트 정상 동작 확인

---

## 2. 아키텍처

```text
[사용자 브라우저]
    ↓ http://서버:8000
[FastAPI (uvicorn)]
    ├── /           → static/index.html (HTML UI)
    ├── /api/detect → 5종 detector (xlsx/docx/pptx/hwpx/pdf)
    ├── /api/download/{token} → xlsx 결과 다운로드
    ├── /api/feedback → 사용자 피드백 저장
    └── /docs       → Swagger UI

[탐지 소스]
    ├── regex_detector   → auto_targets (이메일/IP/VLAN/사번 등)
    ├── NER (KoELECTRA)  → auto_targets (한국인 성명)
    └── AI (Keras 모델)  → review_targets (민감 후보 추천)

[저장소]
    ├── logs/app.log                         → 서버 로그
    └── feedback_data/feedback_YYYY-MM-DD.json → 피드백 누적
```

---

## 3. 프로젝트 디렉토리 구조

```text
C:\Users\user\Desktop\coding\ai study\
├── src/
│   ├── api/
│   │   ├── main.py             FastAPI 앱 (CORS, static, 로깅, startup)
│   │   ├── detect_router.py    POST /api/detect, GET /api/download
│   │   ├── feedback_router.py  POST /api/feedback, GET /api/feedback/*
│   │   ├── files.py            downloadToken 관리
│   │   ├── errors.py           에러 응답, 파일 형식 감지
│   │   └── README.md           API 실행 가이드
│   ├── feedback/
│   │   ├── models.py           UserFeedback dataclass
│   │   └── store.py            JSON 날짜별 파일 저장 (enabled=True)
│   ├── common_apply_result.py  CommonApplyItem/ReviewItem (grade/source 포함)
│   ├── common_apply_utils.py   warning type 상수, 공통 유틸
│   ├── deidentify_target_builder.py
│   ├── deidentify_apply.py
│   ├── regex_detector.py
│   ├── xlsx_deidentify_apply.py
│   ├── docx_detector.py
│   ├── pptx_detector.py
│   ├── hwpx_detector.py
│   └── pdf_detector.py
├── static/
│   └── index.html              단일 페이지 HTML UI
├── models/
│   ├── hf/
│   │   └── KoELECTRA-small-v3-modu-ner/
│   └── privacy_cso_char_keras_model.keras
├── notebooks/
│   ├── test_helpers.py         TestRunner 공통 헬퍼
│   ├── run_all_tests.py        통합 회귀 테스트
│   ├── 13_test_xlsx_regression.py
│   ├── 15_test_docx_detector.py
│   ├── 17_test_pptx_detector.py
│   ├── 19_test_hwpx_detector.py
│   └── 21_test_pdf_detector.py
├── reports/
│   ├── week17_result.md
│   ├── week17_detector_policy.md
│   ├── week17_php_integration_guide.md
│   └── week18_result.md
├── logs/
│   └── app.log                 서버 로그 (자동 생성)
├── feedback_data/
│   └── feedback_YYYY-MM-DD.json (자동 생성)
├── .env                        환경 변수 설정
└── requirements.txt
```

---

## 4. 환경 변수 (.env)

```text
# 모델 경로
NER_MODEL_PATH=C:\Users\user\Desktop\coding\ai study\models\hf\KoELECTRA-small-v3-modu-ner
AI_MODEL_PATH=C:\Users\user\Desktop\coding\ai study\models\privacy_cso_char_keras_model.keras

# 탐지 임계값
NER_THRESHOLD=0.8
AI_THRESHOLD=0.5

# 저장 경로 (미설정 시 프로젝트 루트 하위 자동 생성)
# LOG_DIR=
# FEEDBACK_DIR=
# DEIDENTIFY_TMP_DIR=
```

---

## 5. 서버 실행

```powershell
cd "C:\Users\user\Desktop\coding\ai study"
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

브라우저: `http://localhost:8000`  
Swagger: `http://localhost:8000/docs`

**`--workers 1` 필수**: downloadToken이 프로세스 메모리 기반이므로
멀티 워커 시 detect/download가 다른 워커로 분산되면 토큰을 못 찾음.

---

## 6. 회귀 테스트

```powershell
python notebooks/run_all_tests.py
```

```text
현재 기준:
  ✓ xlsx :   13/  13
  ✓ docx :   71/  71
  ✓ pptx :   71/  71
  ✓ hwpx :   65/  65
  ✓ pdf  :   52/  52
  합계: 272/272 (약 2초)
```

---

## 7. 주요 결정 사항 (누적)

### 탐지 정책
```text
- regex: 명확한 패턴 → auto_targets (자동 비식별화)
- NER (KoELECTRA): 한국인 성명만 → auto_targets
- AI (Keras): 민감 후보 추천 → review_targets (등급은 사용자 판단)
- threshold: detect_router.py에서 환경변수로 중앙 관리
```

### 파일 형식별 처리
```text
- xlsx: applied 모드 (시스템이 자동 비식별화 → 다운로드)
- docx/pptx/hwpx/pdf: guide 모드 (위치 안내 → 사용자 직접 수정)
```

### API 응답 구조 (C안)
```text
{
  "success": true/false,
  "fileType": "pdf",
  "applyMode": "guide",
  "downloadToken": null | "abc123",
  "autoResults": [...],   // grade, source 포함
  "reviewTargets": [...], // grade, source, sensitiveCategory 포함
  "warnings": [...],
  "summary": {...},
  "metadata": { "originalFilename": "...", "fileSize": 12345 }
}
```

### 피드백 저장
```text
- JSON 날짜별 파일 방식
- feedback_data/feedback_YYYY-MM-DD.json
- threading.Lock으로 동시 접근 방지
```

### downloadToken
```text
- 프로세스 메모리 기반 (단일 워커 전용)
- 1회용, TTL 1시간
- 멀티 워커 시 Redis/SQLite로 교체 필요
```

---

## 8. 알려진 이슈 및 한계

### AI 추론 품질
```text
- 예측 확신도 낮음 (0.4~0.6 분포)
- NER 오탐 존재 (예: "장 소" → 성명으로 인식)
- 학습 데이터 부족으로 사내 배포 불가 수준
- 19주차 D단계에서 피드백 데이터 분석 후 개선 방향 수립
```

### downloadToken 저장소
```text
- 단일 워커 전용 (프로세스 메모리)
- 멀티 워커 배포 시 Redis/SQLite로 교체 필요
```

### on_event deprecated
```text
- 현재 main.py에서 @app.on_event("startup") 사용 중
- FastAPI에서 deprecated 예정 → lifespan 방식으로 교체 필요
- 19주차 모델 상주 구현 시 함께 교체 예정
```

---

## 9. 19주차 예정 작업

### A. 모델 상주 (응답 속도 개선)

**현재 문제:**
```text
요청마다 모델 로드 → 첫 요청 10~15초 소요
```

**개선 방향:**
```text
1. detect_router.py
   - 전역 변수 _ner_func, _ai_func 추가
   - load_models_on_startup() 함수 구현

2. main.py
   - @app.on_event("startup") → lifespan 방식으로 교체
   - 서버 시작 시 모델 1회 로드
   - 로딩 시간 로그 출력

3. 응답 속도 측정
   - 요청 처리 시간을 app.log에 기록
   - before/after 비교
```

**예상 효과:**
```text
before: 첫 요청 ~10초 (모델 로드 포함)
after:  모든 요청 ~1초 (탐지만)
```

### D. 피드백 데이터 활용

**목적:** 누적된 피드백으로 AI 모델 품질 분석

**구현 내용:**
```text
1. 분석 스크립트 (notebooks/analyze_feedback.py)
   - 날짜 범위별 피드백 로드
   - 동의율 / 오탐율 계산
   - fileType별, grade별 집계
   - AI가 틀린 케이스 추출 (aiGrade != userGrade)

2. 재학습 데이터셋 추출
   - 사용자 판단이 있는 항목 → 학습 데이터 형식으로 변환
   - context, userGrade → (text, label) 쌍

3. 개선 방향 보고서
   - 오탐 패턴 분석
   - threshold 조정 권고
   - 모델 재학습 필요 여부 판단
```

---

## 10. 다음 세션 시작 방법

새 대화창에서 다음 내용을 붙여넣고 시작하세요:

```text
안녕하세요. 19주차 비식별화 도구 개발을 시작합니다.
현재까지의 진행 상황은 week18_handover.md 파일에 정리되어 있습니다.

프로젝트 위치: C:\Users\user\Desktop\coding\ai study
주요 파일:
- src/api/main.py, detect_router.py
- src/feedback/store.py
- static/index.html

19주차 작업:
A. 모델 상주 구현 (lifespan + 전역 변수)
D. 피드백 데이터 활용 (분석 스크립트 + 재학습 데이터셋)
```

---

## 11. 참고 문서

| 문서 | 위치 | 내용 |
|---|---|---|
| 17주차 결과 | `reports/week17_result.md` | FastAPI 구축 전체 내용 |
| detector 정책 | `reports/week17_detector_policy.md` | regex/NER/AI 역할 분담 |
| PHP 연동 가이드 | `reports/week17_php_integration_guide.md` | PHP 팀 협의 자료 |
| 18주차 결과 | `reports/week18_result.md` | HTML UI, 로깅, 피드백 저장 |
| 16주차 PDF 가이드 | `reports/week16_pdf_detection_guide.md` | PDF 탐지 한계 및 정책 |
