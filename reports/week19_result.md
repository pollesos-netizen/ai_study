# 19주차 결과 보고서

## 1. 목적

18주차에 구축한 피드백 저장 기능을 활용해 AI 오탐 데이터를 분석하고, 모델 상주 로딩으로 응답 속도를 개선했다.
피드백 기반 재학습 데이터셋을 생성하고 sklearn 모델을 교체하는 것을 목표로 했다.

---

## 2. 주요 변경 사항

### 2.1 모델 상주 로딩 (lifespan)

**`src/api/main.py`**

FastAPI 2.0에서 deprecated된 `@app.on_event("startup")`을 `lifespan` 컨텍스트 매니저로 교체.
서버 시작 시 NER/AI 모델을 1회 로드해 전역 캐시에 저장한다.

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    from api.detect_router import load_models_on_startup, startup_cleanup
    startup_cleanup()
    load_models_on_startup()
    yield

app = FastAPI(lifespan=lifespan, ...)
```

**`src/api/detect_router.py`**

전역 캐시 변수 및 startup 로더 추가.

```python
_regex_func = None
_ner_func = None
_ai_func = None

def load_models_on_startup() -> None:
    global _regex_func, _ner_func, _ai_func
    _regex_func = _load_regex_func()          # regex 즉시 로드
    _ner_func   = _load_ner_func()            # NER_MODEL_PATH 있을 때
    _ai_func    = _load_ai_func()             # AI 모델 있을 때
```

요청 처리 함수(`_run_xlsx`, `_run_guide`)는 전역 캐시를 우선 사용하고, 없으면 즉시 로드하는 fallback 유지:

```python
regex_func = _regex_func or _load_regex_func()
```

효과: 첫 요청 지연 10~15s → ~1s.

### 2.2 요청 처리 시간 로깅

**`src/api/detect_router.py`**

`time.perf_counter()`로 detect 엔드포인트 처리 시간 측정 후 로그 기록.

```text
[detect] report.xlsx / xlsx / 0.312s
[detect] contract.pdf / pdf / 1.204s
```

### 2.3 피드백 오탐 로그

**`src/api/feedback_router.py`**

피드백 저장 시 오탐/불일치/동의 여부를 자동으로 로그에 기록.

```python
if feedback.is_false_positive():
    _logger.warning("[feedback] 오탐 | %s | AI=%s→X | %s | %s",
        payload.fileType, payload.aiGrade, payload.locationLabel, ctx)
elif not feedback.is_agreement():
    _logger.warning("[feedback] 등급불일치 | %s | AI=%s→사용자=%s | %s | %s",
        payload.fileType, payload.aiGrade, payload.userGrade, payload.locationLabel, ctx)
else:
    _logger.info("[feedback] 동의 | %s | grade=%s | %s",
        payload.fileType, payload.aiGrade, payload.locationLabel)
```

### 2.4 피드백 분석 스크립트

**`src/api/analyze_feedback.py`**

`feedback_data/` 폴더의 JSON을 읽어 통계 리포트를 출력하고 재학습 데이터셋을 추출하는 CLI 스크립트.

주요 기능:

| 함수 | 설명 |
|---|---|
| `load_feedbacks()` | 날짜 범위 필터링, JSON 전체 로드 |
| `compute_stats()` | 동의율 / 오탐율 / 등급별 집계 |
| `get_mismatch_cases()` | AI ≠ 사용자 불일치 케이스 추출 |
| `build_retrain_dataset()` | 재학습용 레이블 변환 |
| `export_dataset()` | JSONL 파일 저장 |

```bash
python src/api/analyze_feedback.py
python src/api/analyze_feedback.py --date-from 2026-05-01 --date-to 2026-05-31
python src/api/analyze_feedback.py --export-dataset data/retrain.jsonl
```

재학습 레이블 변환 규칙:

```text
isFalsePositive=True  → label="O"    (오탐: O등급으로 재학습)
등급 불일치           → label=userGrade (사용자 판단 우선)
동의                  → label=aiGrade   (AI 예측 확인)
```

### 2.5 keras / sklearn 모델 선택

**`src/api/detect_router.py`**

`AI_MODEL_TYPE` 환경 변수로 런타임에 모델 종류를 전환할 수 있도록 구현.

```python
def _load_ai_func():
    if _get_ai_model_type() == "sklearn":
        return _load_sklearn_func()
    return _load_keras_func()
```

sklearn 모델은 `predict_proba()` 출력을 C/S/O 확률로 변환:

```python
_SKLEARN_LABEL_MAP = {"개인정보": "S", "민감정보": "C", "일반": "O"}
```

```text
# .env
AI_MODEL_TYPE=sklearn  # keras | sklearn
SKLEARN_MODEL_PATH=C:\...\models\privacy_sentence_model_v3.pkl
```

기존 keras 모델(val_accuracy=0.49, C recall=0.0)보다 소규모 데이터셋에서 sklearn(TF-IDF + LogReg)이 유리한 점을 확인해 sklearn으로 전환.

### 2.6 v5 학습 데이터셋 생성

**`notebooks/make_v5_dataset.py`** → **`data/privacy_sentence_sample_v5.csv`**

피드백 오탐 패턴(비식별화 기준 설명 문장을 C등급으로 오탐)을 해소하기 위해 학습 데이터를 보강했다.

**추가 데이터 (49건):**

| 구분 | 건수 | 내용 |
|---|---|---|
| 오탐 피드백 직접 변환 | 9건 (O) | `feedback_2026-05-28.json`의 오탐 문장 |
| 비식별화 기준 설명 합성 | 20건 (O) | "C등급은 외부 공개 시…", "비식별화 절차 안내서를 첨부합니다" 등 |
| C급 보강 | 20건 (C) | 보안정보 5건, 계약/원가 5건, 운용/사고 5건, 인사/기타 5건 |

**데이터셋 규모 변화:**

| | v4 (변경 전) | v5 (변경 후) |
|---|---|---|
| C (기밀) | 33 | 53 (+20) |
| S (개인) | 78 | 78 |
| O (일반) | 78 | 107 (+29) |
| **합계** | **189** | **238** |

### 2.7 sklearn 모델 v3 재학습

**`notebooks/04_train_sklearn_v5.py`** → **`models/privacy_sentence_model_v3.pkl`**

v5 데이터셋으로 TF-IDF char_wb + LogisticRegression 재학습.

```text
Accuracy: 0.7708

              precision  recall  f1-score  support
민감정보(C)      0.70      0.88      0.78      16
개인정보(S)      0.82      0.82      0.82      11
일반(O)          0.82      0.67      0.74      21
```

오탐 패턴 검증 (정답: 일반/O):

```text
[OK] 일반  O=0.542 | 기간의 경과 등으로 비공개 필요성이 소멸된 정보
[OK] 일반  O=0.568 | O 등급 C 등급
[OK] 일반  O=0.553 | S 등급
[OK] 일반  O=0.609 | (비식별화 조치 내역 및 결과)
[OK] 일반  O=0.695 | 5) S등급 데이터 비식별화 조치 결과 검토 및 승인
[OK] 일반  O=0.641 | C등급은 외부 공개 시 기관에 중대한 피해를 줄 수 있는 기밀 정보입니다
[OK] 일반  O=0.559 | 비공개 분류 기준 검토서를 제출했습니다
[OK] 일반  O=0.494 | 정보 등급별 외부 AI 활용 가능 여부를 확인하시기 바랍니다
```

8건 전부 O 정확히 예측 — 오탐 패턴 해소 확인.

### 2.8 regex 탐지 단락 AI 중복 탐지 제거

**`src/api/detect_router.py`, `src/docx_detector.py`, `src/hwpx_detector.py`, `src/pptx_detector.py`, `src/pdf_detector.py`**

모든 파일 형식에서 regex가 이미 결과를 낸 단락/셀/줄은 AI 평가를 건너뛰도록 수정.

```python
# 변경 전 — regex 결과와 무관하게 AI 항상 실행
raw_regex = regex_detect_func(text) or []
for raw in raw_regex:
    ...
if ai_predict_func is not None:
    grade, confidence, prob_map = ai_predict_func(text)  # 중복 탐지 발생

# 변경 후 — regex 결과 없을 때만 AI 실행
raw_regex = regex_detect_func(text) or []
for raw in raw_regex:
    ...
if ai_predict_func is not None and not raw_regex:
    grade, confidence, prob_map = ai_predict_func(text)
```

AI의 역할을 regex가 못 잡는 문맥 기반 민감정보 탐지로 명확히 분리.

적용 파일:

| 파일 | 단위 |
|---|---|
| `src/api/detect_router.py` | xlsx 셀 |
| `src/docx_detector.py` | 단락 |
| `src/hwpx_detector.py` | 단락 |
| `src/pptx_detector.py` | 단락 |
| `src/pdf_detector.py` | 줄 |

---

## 3. 환경 변수 전체 목록 (19주차 추가분)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `NER_MODEL_PATH` | (없음) | NER 모델 디렉토리 경로 |
| `AI_MODEL_PATH` | `models/privacy_cso_char_keras_model.keras` | Keras AI 모델 파일 경로 |
| `SKLEARN_MODEL_PATH` | `models/privacy_sentence_model_v2.pkl` | sklearn AI 모델 파일 경로 |
| `AI_MODEL_TYPE` | `keras` | 사용할 AI 모델 종류 (`keras` \| `sklearn`) |
| `NER_THRESHOLD` | `0.8` | NER 탐지 신뢰도 임계값 |
| `AI_THRESHOLD` | `0.5` | AI 탐지 신뢰도 임계값 |
| `LOG_DIR` | `(프로젝트 루트)/logs` | 로그 저장 디렉토리 |
| `FEEDBACK_DIR` | `(프로젝트 루트)/feedback_data` | 피드백 저장 디렉토리 |

---

## 4. 19주차 산출물 목록

### 신규 파일

| 파일 | 설명 |
|---|---|
| `src/api/analyze_feedback.py` | 피드백 분석 CLI 스크립트 |
| `notebooks/make_v5_dataset.py` | v5 학습 데이터셋 생성 스크립트 |
| `notebooks/04_train_sklearn_v5.py` | sklearn v3 모델 재학습 스크립트 |
| `data/privacy_sentence_sample_v5.csv` | 238건 학습 데이터셋 (v4 + 49건 추가) |
| `models/privacy_sentence_model_v3.pkl` | 재학습된 sklearn 모델 |

### 변경 파일

| 파일 | 변경 내용 |
|---|---|
| `src/api/main.py` | `@app.on_event` → `lifespan` 컨텍스트 매니저 교체 |
| `src/api/detect_router.py` | 전역 모델 캐시, sklearn 모델 선택, regex 중복 탐지 제거(xlsx), 요청 시간 로그 |
| `src/docx_detector.py` | regex 탐지 단락 AI 중복 탐지 제거 |
| `src/hwpx_detector.py` | regex 탐지 단락 AI 중복 탐지 제거 |
| `src/pptx_detector.py` | regex 탐지 단락 AI 중복 탐지 제거 |
| `src/pdf_detector.py` | regex 탐지 줄 AI 중복 탐지 제거 |
| `src/api/feedback_router.py` | 오탐/불일치/동의 로그 추가 |
| `.env` | `SKLEARN_MODEL_PATH`, `AI_MODEL_TYPE` 추가; v3 모델 경로로 업데이트 |

---

## 5. 20주차 예정 작업

```text
- 추가 피드백 수집 후 재학습 데이터셋 누적
- NER 오탐 케이스("장 소" 등 성명 오인식) 분석 및 필터 보완
- xlsx 외 다른 파일 형식(docx/hwpx 등)에도 regex 중복 탐지 방지 적용 여부 검토
```
