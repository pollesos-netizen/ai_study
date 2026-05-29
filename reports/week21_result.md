# 21주차 결과 보고서

## 1. 목적

20주차에 구축한 사내 업무 매뉴얼 코퍼스(26개 파일, 약 12만 줄)를 기반으로
민감정보 후보 추출 파이프라인을 구현하고, v6 학습 데이터셋을 생성해 모델을 개선했다.
이와 함께 OOD 입력 오탐, NER 오탐, regex 커버리지 부족 등 실제 탐지 검증에서 발견된
품질 이슈를 수정했다.

---

## 2. 주요 변경 사항

### 2.1 민감정보 후보 추출 파이프라인

**`tools/keywords.yaml`** (신규)

C/S/O 분류 키워드를 역할별로 분리한 설정 파일.
스크립트 코드를 수정하지 않고 키워드만 추가·제거할 수 있다.

```yaml
ai_tracks:
  strong_procedural:   # 단독 매칭 가능 (C 후보)
  ambiguous_action:    # 단독 매칭 금지, 가점으로만 사용
  operational_anchor:  # 단독 매칭 금지, 가점으로만 사용
  s_business_sensitive: # 단독 매칭 가능 (S 후보)
weak:                  # 단독 매칭 금지, 공출현 시 보조 신호
```

**`tools/extract_candidates.py`** (신규)

`data/manuals_md/`의 `.md` 파일을 읽어 검수용 후보 CSV를 생성하는 CLI 스크립트.

주요 기능:

| 기능 | 설명 |
|---|---|
| TextUnit 분할 | `##`/`###` 헤딩, `**굵은 소제목**`, `<!-- page N -->` 경계 |
| 키워드 매칭 | `keywords.yaml` 기반, 공백 제거 + 전각/반각 정규화 |
| Noise 제거 | 목차·개정이력·표 구분행·15자 미만·한글비율 30% 초과 등 |
| ambiguous+anchor 오탐 방지 | 단독 조합은 후보 승격 금지, `strong` 키워드 있을 때만 가점 |
| regex 식별자 탐지 | `regex_detector.py` 재사용 + 마스킹 IP·지역번호 괄호식 전화 추가 |
| regexOnly 플래그 | 식별자만 있고 서술형 키워드 없는 경우 `true` (AI 골든셋 제외) |

```bash
python tools/extract_candidates.py
python tools/extract_candidates.py --manuals-dir data/manuals_md --output data/candidates.csv
```

**출력 결과 (26개 파일):**

```text
전체 TextUnit  : 96,670건
noise 제외     : 76,194건
전체 후보      :    634건
  ai_procedural_sensitive :  340건
  regex_identifier        :  294건
  regexOnly=true          :    6건
```

출력 CSV 3종: `candidates.csv` / `candidates_ai.csv` / `candidates_regex.csv`

---

### 2.2 v6 학습 데이터셋 생성

**`notebooks/make_v6_merged_dataset.py`** (신규)  
**`data/privacy_sentence_sample_v6_merged.csv`** (신규)

`privacy_sentence_sample_v5.csv` + `trainset.csv` 병합.
v5의 `cso_grade`는 `grading_rubric.md` 기준으로 재매핑했다.

**재매핑 규칙 핵심:**

| 조건 | newGrade |
|---|---|
| `has_sensitive_legal=Y` 또는 건강정보·복지정보 | C 유지 |
| `보안정보` + 내부망·IP·방화벽 등 키워드 | C 유지 |
| 계약정보·예산/원가·계획/전략·감사/법무·인사 등 | S 재분류 |
| `일반업무` / `분류설명` / 모든 플래그 N | O |

**데이터셋 규모:**

| 구분 | C | S | O | 합계 |
|---|---|---|---|---|
| trainset | 103 | 143 | 90 | 336 |
| privacy_v5 (재매핑 후) | 37 | 94 | 107 | 238 |
| **v6 merged** | **140** | **237** | **197** | **574** |
| (원본/증강) | 495 | 79 | — | 574 |

C→S 재분류: 37건 (계약·예산·계획·감사·인사 카테고리)

---

### 2.3 sklearn 모델 개선

세 가지 구성을 같은 train/test split으로 비교했다.

**train/test 분리 원칙:**
- `augmented=1`(증강) 행은 train 전용 → test 세트 오염 방지
- test 세트: 원본(`augmented=0`) 99건만 사용

**비교 결과:**

| 모델 | Accuracy | C recall | S recall | O recall |
|---|---|---|---|---|
| v4: LR + char_wb(2,4) | 0.616 | 0.67 | 0.55 | 0.68 |
| v5: SVC + char_wb(2,4) | **0.657** | 0.61 | 0.62 | 0.74 |
| v6: SVC + char+word+keyword | 0.647 | **0.67** | 0.64 | 0.65 |

**키워드 피처라이저 (`KeywordFeaturizer`):**

```python
class KeywordFeaturizer(BaseEstimator, TransformerMixin):
    """keywords.yaml 그룹별 매칭 수 → 수치 피처 4개
      0: strong_procedural 수  → C 신호
      1: s_business_sensitive 수 → S 신호
      2: ambiguous_action 수
      3: weak 수
    """
```

전체 accuracy 기준 v5 최고, C recall 기준 v6 최고.
비식별화 도구 특성상 C 미탐이 더 위험하므로 **v6를 운영 모델로 채택**.

저장 경로: `models/privacy_sentence_model_v6.pkl`

**관련 스크립트:**

| 파일 | 역할 |
|---|---|
| `notebooks/05_train_sklearn_v6.py` | 기본 학습 (v4) |
| `notebooks/06_train_sklearn_v6_improved.py` | v4 vs v5 비교 |
| `notebooks/07_train_sklearn_v6_keyword_features.py` | v4 vs v5 vs v6 비교, 최고 모델 저장 |

---

### 2.4 AI 사전 필터 (`_should_skip_ai`)

**`src/api/detect_router.py`, `src/docx_detector.py`, `src/hwpx_detector.py`, `src/pptx_detector.py`, `src/pdf_detector.py`**

"Step 1", "Step 2" 같은 짧은 영문 목록 라벨이 AI에서 높은 확신도(0.85)로 오탐되는 문제 수정.

**원인:** char n-gram 모델이 OOD(Out-of-Distribution) 입력에서 피처 벡터가 거의 0임에도
CalibratedClassifierCV가 특정 클래스로 높은 확신도를 출력하는 실패 패턴.

```python
def _should_skip_ai(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 10:          # 목록 라벨·단어 1~2개 수준
        return True
    korean = sum(1 for c in stripped if "가" <= c <= "힣")
    return korean / len(stripped) < 0.20  # 영문 위주 텍스트
```

적용 위치:
```python
if ai_func and not regex_hits and not _should_skip_ai(text):
    ...
```

검증:

```text
[OK] SKIP  | Step 1
[OK] SKIP  | Step 2
[OK] SKIP  | Step 1. verify      (한글 0%)
[OK] RUN   | SSH 접속 후 설정파일을 확인합니다
[OK] RUN   | Step 1. 카드 재부팅 절차를 수행합니다
```

---

### 2.5 Regex 패턴 보강

**`src/regex_detector.py`**

기존 regex 패턴에서 누락된 2가지 추가.

| 패턴 ID | 라벨 | 등급 | 예시 |
|---|---|---|---|
| `credit_card` | 신용카드번호 | C (삭제) | `1234-5678-9012-3456` |
| `driver_license` | 운전면허번호 | S (삭제) | `11-22-345678-90` |

```python
# 신용카드번호: 4×4자리 (하이픈 또는 공백 구분)
r"(?<!\d)\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}(?!\d)"

# 운전면허번호: 시도코드-연도-일련번호-검증
r"(?<!\d)\d{2}-\d{2}-\d{6}-\d{2}(?!\d)"
```

---

### 2.6 NER 오탐 필터

**`src/api/detect_router.py`, `src/docx_detector.py`, `src/hwpx_detector.py`, `src/pptx_detector.py`, `src/pdf_detector.py`**

"장 소", "박 사" 등 성(姓) + 공백 + 직함 조합을 KoELECTRA NER이 성명으로 오인식하는 문제.
매칭 구간 길이 2자 이하인 경우 결과에서 제외.

```python
s, e = int(raw.get("start", 0)), int(raw.get("end", 0))
if e - s <= 2:  # "장 소", "박 사" 등 성+직함 오인식 방지
    continue
```

---

## 3. 환경 변수 변경 (`.env`)

| 변수 | 변경 전 | 변경 후 | 설명 |
|---|---|---|---|
| `SKLEARN_MODEL_PATH` | `...v3.pkl` | `...v6.pkl` | v6 모델로 교체 |
| `AI_THRESHOLD` | `0.5` | `0.8` | 오탐 과다로 상향 조정 |

---

## 4. 21주차 산출물 목록

### 신규 파일

| 파일 | 설명 |
|---|---|
| `tools/keywords.yaml` | C/S/O 분류 키워드 설정 (v3) |
| `tools/extract_candidates.py` | 매뉴얼 후보 추출 스크립트 |
| `data/candidates.csv` | 전체 후보 634건 |
| `data/candidates_ai.csv` | AI 검수 후보 340건 |
| `data/candidates_regex.csv` | regex 식별자 후보 294건 |
| `notebooks/make_v6_merged_dataset.py` | v5 + trainset 병합·재매핑 스크립트 |
| `data/privacy_sentence_sample_v6_merged.csv` | 574건 학습 데이터셋 |
| `notebooks/05_train_sklearn_v6.py` | v4(LR+char) 학습 스크립트 |
| `notebooks/06_train_sklearn_v6_improved.py` | v4 vs v5 비교 스크립트 |
| `notebooks/07_train_sklearn_v6_keyword_features.py` | v4 vs v5 vs v6 비교 스크립트 |
| `models/privacy_sentence_model_v4.pkl` | LR + char_wb (Accuracy 0.616) |
| `models/privacy_sentence_model_v5.pkl` | SVC + char_wb (Accuracy 0.657) |
| `models/privacy_sentence_model_v6.pkl` | SVC + char+word+keyword (C recall 0.67) |

### 변경 파일

| 파일 | 변경 내용 |
|---|---|
| `src/regex_detector.py` | 신용카드번호·운전면허번호 패턴 추가 |
| `src/api/detect_router.py` | `_should_skip_ai()` 추가, NER 2자 이하 필터, AI 호출 조건 업데이트 |
| `src/docx_detector.py` | `_should_skip_ai()`, NER 2자 이하 필터 추가 |
| `src/hwpx_detector.py` | 동일 |
| `src/pptx_detector.py` | 동일 |
| `src/pdf_detector.py` | 동일 |
| `.env` | `SKLEARN_MODEL_PATH` v6 경로로 업데이트, `AI_THRESHOLD=0.8` |

---

## 5. 모델 성능 현황 및 한계

```text
현재 데이터 574건 기준 Accuracy 상한: ~0.65~0.70
주요 오류: S↔C 혼동 (공격 악용 가능 여부라는 의미론적 경계)
char n-gram + word n-gram + keyword 피처로 이 경계 일부 보완

더 높은 성능을 위해서는:
  1. 골든셋 1,000건 이상 확보
  2. ko-sroberta 등 한국어 사전학습 임베딩 모델 전환
  3. candidates_ai_out.csv 추가는 88% 중복으로 효과 없음 확인
```

---

## 6. 22주차 예정 작업

```text
- 피드백 데이터 누적 (현재 11건 → 충분한 양 확보 후 재학습)
- week20 taxonomy 미결 사항
  · TextUnit 분할 기준 확정 (장애 항목 단위 블록화)
  · C4 보호계전 설정치 처리 (수치 regex + 맥락 AI 하이브리드)
- 파일 크기 제한 추가 (운영 안정성)
- 다운로드 토큰 SQLite 전환 검토
```
