# 18주차 결과 보고서

## 1. 목적

17주차에 구축한 FastAPI 백엔드를 기반으로 사내 독립 배포를 위한 HTML 웹 UI를 구현했다.
PHP 시스템과 별개로 FastAPI가 UI까지 서빙하는 완결된 서비스 구조를 목표로 했다.

---

## 2. 주요 변경 사항

### 2.1 FastAPI static 서빙 + CORS

**`src/api/main.py`**

```python
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# CORS (브라우저 직접 접근 허용)
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

# static 서빙
app.mount("/static", StaticFiles(directory="static"), name="static")

# 루트 → index.html
@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")
```

브라우저에서 `http://서버IP:8000`으로 직접 접속 가능.

### 2.2 단일 페이지 HTML (`static/index.html`)

순수 HTML + vanilla JS로 구현. 빌드 과정 없이 FastAPI static으로 바로 서빙.

**구현된 기능:**

| 기능 | 설명 |
|---|---|
| 파일 업로드 | 드래그 앤 드롭 + 클릭 선택 |
| 옵션 설정 | deletionMode / useNer / useAi |
| 요약 | 탐지 위치 / 처리 완료 / 자동 탐지 / 검토 필요 |
| autoResults 테이블 | 등급 배지(C/S/O) + 소스(regex/ner/ai/mixed) |
| reviewTargets UI | AI 추정값 기본 선택, C/S/O/오탐 선택 |
| xlsx 다운로드 | applied 모드 시 다운로드 버튼 |
| PDF 안내 | PDF 직접 편집 어려움 안내 |
| 에러 처리 | 서버 오류, 미지원 형식 등 |
| 피드백 저장 | 판단 저장 버튼 → /api/feedback |

### 2.3 로깅 설정

**`src/api/main.py`**

AI 예측 실패 등 경고 메시지를 터미널 대신 파일로 저장.

```text
logs/app.log
  - RotatingFileHandler: 최대 5MB × 3개
  - 형식: YYYY-MM-DD HH:MM:SS [LEVEL] 모듈명: 메시지
  - 터미널: WARNING 이상만 표시
  - 환경변수 LOG_DIR로 경로 변경 가능
```

서버 시작 시 로그 파일 경로를 터미널에 출력:
```text
[logging] 로그 파일: C:\...\logs\app.log
```

### 2.4 AI 예측 실패 print → logging

4개 detector(`docx/pptx/hwpx/pdf_detector.py`)에서 `print()` → `logging.warning()`으로 교체.

```python
# 변경 전
print(f"[AI] {location} 예측 실패: {exc}")

# 변경 후
logging.getLogger(__name__).warning("[AI] %s 예측 실패: %s", location, exc)
```

### 2.5 AI 입력 형식 수정

**`src/api/detect_router.py`**

Keras 모델이 `list` 입력을 받지 못하는 문제 수정.

```python
# 변경 전 (오류)
model.predict([text], verbose=0)
# → Invalid dtype: str960

# 변경 후 (정상)
import tensorflow as tf
model.predict(tf.constant([text]), verbose=0)
# → [[0.16, 0.45, 0.39]]  (C/S/O 확률)
```

### 2.6 threshold 환경변수 관리

**`src/api/detect_router.py`**

NER/AI threshold를 `detect_router.py`에서 중앙 관리. 코드 변경 없이 `.env`로 조절 가능.

```python
def _get_ner_threshold() -> float:
    return float(os.environ.get("NER_THRESHOLD", "0.8"))

def _get_ai_threshold() -> float:
    return float(os.environ.get("AI_THRESHOLD", "0.5"))
```

```text
# .env
NER_THRESHOLD=0.8   # 낮추면 더 많이 탐지 (오탐 증가)
AI_THRESHOLD=0.5    # 낮추면 review_targets 더 많이 포함
```

기본값 변경: AI threshold `0.6` → `0.5` (모델 예측값 분포 반영).

`/api/version` 응답에 현재 threshold 값 포함:
```json
"models": {
  "ner": "available",
  "ai": "available",
  "ner_threshold": 0.8,
  "ai_threshold": 0.5
}
```

### 2.7 xlsx AI 탐지 추가

**`src/api/detect_router.py`**

`_run_xlsx()`에 AI 탐지 블록 추가. (NER은 이미 구현됨)

```text
셀 텍스트 → AI 예측 → grade != "O" and confidence >= AI_THRESHOLD
  → review_targets에 추가 (auto 적용 안 됨, 사용자 확인 필요)
```

### 2.8 CommonApplyItem grade/source 추가

**`src/common_apply_result.py`**

`autoResults`의 각 항목에도 등급/소스 정보 추가.

```json
{
  "label": "VLAN/포트 정보",
  "action": "삭제",
  "originalText": "VLAN 301",
  "appliedText": "(삭제됨)",
  "grade": "C",
  "source": "regex"
}
```

집계 정책:
- `grade`: C > S > O 우선순위 (한 위치에 여러 등급이면 가장 높은 것)
- `source`: 단일 소스면 그 이름, 여러 소스면 `"mixed"`

### 2.9 피드백 저장 JSON 구현

**`src/feedback/store.py`**

`FeedbackStore.enabled=True`, JSON 날짜별 파일 방식으로 활성화.

```text
feedback_data/
  feedback_2026-05-26.json
  feedback_2026-05-27.json
  ...
```

```json
[
  {
    "locationLabel": "3쪽 5번째 줄",
    "context": "입찰 평가표를 검토했습니다.",
    "aiGrade": "S",
    "userGrade": "S",
    "fileType": "pdf",
    "sensitiveCategory": "AI_S",
    "isAgreement": true,
    "isFalsePositive": false,
    "timestamp": 1779779422.9
  }
]
```

동시 접근 방지: `threading.Lock` (파일별)

추가된 엔드포인트:
```text
GET /api/feedback/stats   → 전체 통계 (동의율, 오탐율, 날짜별 집계)
GET /api/feedback/list    → 목록 조회 (date, limit 파라미터)
```

환경 변수:
```text
FEEDBACK_DIR=C:\...\feedback_data
```

---

## 3. 배포 구조

```text
[사내 서버 또는 개발 PC]
├── src/
│   ├── api/         FastAPI 엔드포인트
│   ├── feedback/    피드백 저장소
│   └── *.py         5종 detector
├── static/
│   └── index.html   단일 페이지 UI
├── models/
│   ├── hf/KoELECTRA-small-v3-modu-ner
│   └── privacy_cso_char_keras_model.keras
├── logs/
│   └── app.log
├── feedback_data/
│   └── feedback_YYYY-MM-DD.json
└── .env             환경 변수 설정
```

```bash
# 서버 실행
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 1

# 브라우저 접속
http://localhost:8000
```

---

## 4. 환경 변수 전체 목록

| 변수 | 기본값 | 설명 |
|---|---|---|
| `NER_MODEL_PATH` | (없음) | NER 모델 디렉토리 경로 |
| `AI_MODEL_PATH` | `models/privacy_cso_char_keras_model.keras` | AI 모델 파일 경로 |
| `NER_THRESHOLD` | `0.8` | NER 탐지 신뢰도 임계값 |
| `AI_THRESHOLD` | `0.5` | AI 탐지 신뢰도 임계값 |
| `LOG_DIR` | `(프로젝트 루트)/logs` | 로그 저장 디렉토리 |
| `FEEDBACK_DIR` | `(프로젝트 루트)/feedback_data` | 피드백 저장 디렉토리 |
| `DEIDENTIFY_TMP_DIR` | 시스템 임시 디렉토리 | 업로드 임시 파일 저장 위치 |

---

## 5. 전체 엔드포인트 (18주차 완료 시점)

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 메인 HTML 페이지 |
| GET | `/api/health` | 헬스 체크 |
| GET | `/api/version` | 버전 + 모델 상태 + threshold |
| POST | `/api/detect` | 파일 비식별화 (5종 통합) |
| GET | `/api/download/{token}` | xlsx 결과 다운로드 |
| POST | `/api/feedback` | 사용자 피드백 저장 |
| GET | `/api/feedback/stats` | 피드백 통계 |
| GET | `/api/feedback/list` | 피드백 목록 조회 |
| GET | `/static/*` | 정적 파일 |
| GET | `/docs` | Swagger UI |

---

## 6. AI 추론 현황 및 한계

### 6.1 현재 동작

```text
NER (KoELECTRA-small-v3-modu-ner):
  - 한국인 성명 탐지 → auto_targets
  - threshold=0.8 적용
  - 일부 오탐 발생 (예: "장 소" → 성명으로 인식)

AI (privacy_cso_char_keras_model.keras):
  - 문장 단위 C/S/O 분류 → review_targets
  - tf.constant([text]) 입력 방식
  - threshold=0.5 적용
  - 예측 확신도가 낮은 경향 (0.4~0.6 분포)
```

### 6.2 한계 및 개선 필요

```text
- AI 추론 정확도 낮음 → 사내 배포 불가 수준
- 오탐률 높음 (NER "장 소" 등)
- 모델 학습 데이터 부족
```

### 6.3 19주차 개선 방향

```text
A. 모델 상주 (서버 시작 시 로드 → 응답 속도 개선)
D. 피드백 데이터 활용 (오탐률 분석, 재학습 데이터셋 추출)
```

---

## 7. 18주차 산출물 목록

### 신규 파일

| 파일 | 설명 |
|---|---|
| `static/index.html` | 단일 페이지 HTML UI |

### 변경 파일

| 파일 | 변경 내용 |
|---|---|
| `src/api/main.py` | CORS + static 서빙 + 로깅 설정 |
| `src/api/detect_router.py` | AI 입력 형식 수정, threshold 환경변수화, xlsx AI 탐지 추가 |
| `src/api/feedback_router.py` | /api/feedback/list 엔드포인트 추가 |
| `src/feedback/store.py` | JSON 날짜별 파일 저장 구현 (enabled=True) |
| `src/common_apply_result.py` | CommonApplyItem grade/source 필드 추가 |
| `src/docx_detector.py` | AI 예측 실패 print → logging |
| `src/pptx_detector.py` | AI 예측 실패 print → logging |
| `src/hwpx_detector.py` | AI 예측 실패 print → logging |
| `src/pdf_detector.py` | AI 예측 실패 print → logging |

---

## 8. 19주차 예정 작업

```text
A. 모델 상주 구현
   - 서버 시작 시 NER/AI 모델 1회 로드
   - 요청마다 로드하지 않도록 개선
   - 응답 속도 측정 (before/after)

D. 피드백 데이터 활용
   - 오탐률 분석 스크립트
   - AI 동의율 / 오탐율 통계
   - 재학습 데이터셋 추출 (aiGrade != userGrade 항목)
   - 향후 모델 개선 방향 정리
```
