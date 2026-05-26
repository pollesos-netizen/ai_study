# 17주차 부채 정리 + FastAPI 백엔드 기초 결과 보고서

## 1. 목적

17주차는 12~16주차 구현 과정에서 발생한 부채를 정리하고, FastAPI 백엔드의 기초 구조를 구축하는 것을 목표로 했다.

주요 작업:
1. docx 표 탐지 동기화 (사용자 작업본 반영)
2. warning type 일관성 정리
3. 테스트 헬퍼 공통화
4. 통합 회귀 테스트 스크립트
5. detector 역할 분담 정책 명문화
6. FastAPI 백엔드 기초 구조
7. CommonReviewItem 필드 보완 (검토 중 발견)

---

## 2. 1단계: docx 표 탐지 동기화

### 2.1 배경

사용자가 13주차 이후 `docx_detector.py`에 표 탐지 기능을 추가했다. 사용자 작업본(최신본)과 우리 작업본(13주차 초기 버전) 사이에 다음 차이가 있었다.

| 항목 | 13주차 초기 | 사용자 최신본 |
|---|---|---|
| 표 탐지 | 없음 | `iter_table_cell_paragraphs()` 구현 |
| warning type | `paragraph_not_in_body` | `unsupported_docx_section`, `missing_table_cell_location` 분리 |
| 병합 셀 처리 | 해당 없음 | `seen_cells` 로직 추가 |
| import 경로 | `from common_apply_utils` | `from src.common_apply_utils` |

### 2.2 결정 사항

**seen_cells 제거 (13주차 정책 복원)**

사용자 작업본에는 병합 셀 중복 제거용 `seen_cells` 로직이 포함되어 있었으나, 13주차 보고서(`week13_docx_detection_guide.md`)에 다음이 명시되어 있었다:

> "초기 구현에서 seen_cells를 사용했으나 복잡한 표 구조에서 실제 셀 paragraph가 누락되는 문제가 확인되어 제거했다."
> "guide 모드에서는 중복 안내보다 탐지 누락 방지를 우선한다."

또한 `id()` 기반 중복 제거는 가비지 컬렉션으로 인해 ID가 재사용될 수 있어 다중 표에서 실제 셀이 누락되는 버그가 확인되었다. 13주차 정책에 따라 `seen_cells`를 완전히 제거했다.

**warning type 분리**

사용자 작업본에서 `unsupported_docx_section`과 `missing_table_cell_location`을 정의했으나, 실제 사용 코드에서는 `missing_paragraph_no`를 그대로 사용하는 불일치가 있었다. 이를 정확히 분리했다.

```text
section이 body/table_cell이 아닌 경우 → unsupported_docx_section
table_cell 보조 필드 누락           → missing_table_cell_location
paragraphNo 누락                     → missing_paragraph_no (유지)
```

### 2.3 common_apply_utils.py 변경

| 변경 | 내용 |
|---|---|
| 삭제 | `WARNING_PARAGRAPH_NOT_IN_BODY = "paragraph_not_in_body"` |
| 추가 | `WARNING_UNSUPPORTED_DOCX_SECTION = "unsupported_docx_section"` |
| 추가 | `WARNING_MISSING_TABLE_CELL_LOCATION = "missing_table_cell_location"` |

### 2.4 docx 표 탐지 TC 추가

표 탐지 기능이 추가되었으므로 TC19~TC22를 신규 추가했다.

| TC | 시나리오 |
|---|---|
| TC19 | 표 셀 단일 탐지 (이메일 마스킹) |
| TC20 | 본문 + 표 셀 동시 탐지 |
| TC21 | 표 2개, 각 표의 여러 셀 탐지 |
| TC22 | 병합 셀이 있어도 일반 셀 누락 없음 (13주차 정책 검증) |

**결과**: docx 52/52 → 67/67 (+15)

---

## 3. 2단계: warning type 일관성 정리

hwpx와 pptx에서도 광의로 `WARNING_MISSING_PARAGRAPH_NO`를 사용하던 부분을 형식별로 분리했다.

### 3.1 hwpx

표 셀 보조 필드(`tableIndex/rowNo/colNo/cellParagraphNo`) 누락 시:
- 변경 전: `WARNING_MISSING_PARAGRAPH_NO`
- 변경 후: `WARNING_MISSING_TABLE_CELL_LOCATION` (docx와 동일, 의미 일치)

### 3.2 pptx

shape/cell 보조 필드(`shapeNo/rowNo/colNo` 등) 누락 시:
- 변경 전: `WARNING_MISSING_PARAGRAPH_NO`
- 변경 후: `WARNING_MISSING_SHAPE_LOCATION` (pptx 전용 신규 추가)

pptx의 shape는 표 셀이 아니므로 docx/hwpx와 이름을 공유하지 않고 별도 정의.

### 3.3 warning type 체계 정리

```text
공통:
  context_mismatch          — target.context와 실제 텍스트 불일치
  slice_mismatch            — text[start:end]와 matched 불일치
  unicode_normalization_mismatch
  paragraph_out_of_range    — 위치 범위 초과
  missing_paragraph_no      — paragraphNo/lineNo 누락 (5종 공통)
  empty_paragraph_target    — 빈 paragraph/line
  overlap_target            — 중복 target 흡수
  unknown_section           — 알 수 없는 section

xlsx 전용:
  missing_sheet_name, missing_cell_ref,
  merged_cell_not_top_left, formula_cell, non_string_cell,
  empty_cell, sheet_not_found

docx 전용:
  unsupported_docx_section  — body/table_cell 외 section
  missing_table_cell_location — 표 셀 보조 필드 누락

pptx 전용:
  missing_slide_no, slide_out_of_range, shape_not_found,
  unknown_section, missing_shape_location (신규)

hwpx 전용:
  missing_section_no, section_out_of_range
  (표 셀 보조 필드 누락은 missing_table_cell_location 사용)

pdf 전용:
  missing_page_no, pdf_page_out_of_range,
  pdf_text_block_not_found, scanned_pdf_no_text,
  pdf_encrypted
```

---

## 4. 3단계: 테스트 헬퍼 공통화

각 detector 테스트 파일에서 중복되던 `_check()`와 결과 집계 로직을 `notebooks/test_helpers.py`로 분리했다.

### 4.1 신규 파일

**`notebooks/test_helpers.py`**

```python
class TestRunner:
    def check(tc_id, condition, message="") → bool
    def report(exit_on_fail=True) → bool
    def record_error(fn_name, exc) → None

def run_test_functions(runner, test_functions, *args, **kwargs) → None
```

### 4.2 마이그레이션 결과

5개 테스트 파일 모두 `TestRunner` 기반으로 마이그레이션. 각 파일 약 12~15줄 절감.

---

## 5. 4단계: 통합 회귀 테스트 스크립트

**`notebooks/run_all_tests.py`**: 5개 detector를 subprocess로 격리 실행하는 통합 회귀 스크립트.

```bash
# 실행
python notebooks/run_all_tests.py

# 옵션
python notebooks/run_all_tests.py --verbose    # 전체 출력
python notebooks/run_all_tests.py --fail-fast  # 첫 실패 시 중단

# 결과 예시
  ✓ xlsx  :   13/  13  (0.3초)
  ✓ docx  :   67/  67  (0.8초)
  ✓ pptx  :   67/  67  (0.5초)
  ✓ hwpx  :   61/  61  (0.1초)
  ✓ pdf   :   48/  48  (0.4초)
  합계: 256/256 (2.1초)
```

subprocess 격리를 통해 한 detector의 import 충돌이 다른 detector에 영향을 주지 않는다. 종료 코드로 CI/CD 연동도 가능하다.

---

## 6. 5단계: detector 역할 분담 정책 명문화

**`reports/week17_detector_policy.md`** (397줄)

### 6.1 탐지 소스 역할 정책

```text
regex_detector:  명확한 패턴 (이메일, IP, VLAN, 사번 등) → auto_targets (자동 비식별화)
NER 모델:        한국인 성명 (KoELECTRA PERSON 엔티티) → auto_targets
AI 분류 모델:    민감 후보 추천 → review_targets (등급은 사용자 판단)
```

**AI 정책 근거**:
- 학습 데이터 부족으로 C/S/O 등급 자동 분류 정확도 낮음
- 회사 가이드라인 정신: "불확실하면 상위 등급 유지가 보안의 표준"
- AI는 "민감해 보이는 문장" 추천만 담당, 최종 판단은 사용자

### 6.2 회사 C/S/O 등급과 매핑

```text
C급 → regex(IP, VLAN 자동 삭제) + AI(추천)
S급 → regex(이메일, 사번 자동 마스킹) + NER(성명 자동 마스킹) + AI(추천)
O급 → 시스템 개입 없음
```

### 6.3 피드백 학습 정책 (틀만 명시)

사용자 피드백(C/S/O 선택)을 학습 데이터로 활용하는 HITL 구조를 설계했으나, 부서 협의 전까지 no-op으로 운영. `src/feedback/` 모듈은 이후 단계에서 구현 예정.

---

## 7. 6단계: FastAPI 백엔드 기초 구조

### 7.1 구조

```text
src/
└── api/
    ├── __init__.py   (패키지 정보)
    ├── main.py       (FastAPI 앱)
    └── README.md     (실행 가이드)
requirements.txt
```

### 7.2 구현된 엔드포인트 (6단계 시점)

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | API 사용 안내 |
| GET | `/api/health` | 헬스 체크 |
| GET | `/api/version` | 버전 및 detector 가용성 정보 |
| GET | `/docs` | Swagger UI (자동 생성) |
| GET | `/redoc` | ReDoc (자동 생성) |
| GET | `/openapi.json` | OpenAPI 스펙 |

### 7.3 동작 검증

```bash
$ curl http://localhost:8000/api/health
{"status":"ok","service":"deidentify-api"}

$ curl http://localhost:8000/api/version
{
  "api_version": "0.1.0",
  "python_version": "3.12.3",
  "detectors": {
    "xlsx_deidentify_apply": "available",
    "docx_detector": "available",
    "pptx_detector": "available",
    "hwpx_detector": "available",
    "pdf_detector": "available"
  },
  "models": {
    "regex": "available",
    "ner": "not_installed",
    "ai": "not_installed"
  }
}
```

### 7.4 서버 실행

```bash
# 개발 모드
uvicorn src.api.main:app --reload --port 8000

# 운영 모드 (멀티 워커)
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4

# PHP 연동 시 (localhost만)
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

uvicorn은 PoC용 서버가 아니라 FastAPI의 표준 ASGI 서버이며, 개발/운영 환경 모두에서 사용한다.

---

## 8. 추가 보완: CommonReviewItem 필드 확장

17주차 검토 중 `CommonReviewItem`이 AI 탐지 결과의 구조적 정보를 `reason` 문자열에만 포함하고 있음을 발견했다. PHP 팀이 C/S/O 선택 UI를 구현할 때 문자열 파싱이 필요해 취약하므로 필드를 추가했다.

### 8.1 추가된 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `grade` | `str \| None` | "C" / "S" / "O" |
| `sensitiveType` | `str \| None` | 민감정보 유형 |
| `sensitiveCategory` | `str \| None` | 카테고리 (예: "성명", "AI_S") |
| `source` | `str \| None` | 탐지 소스 ("regex" / "ner" / "ai") |

### 8.2 변경 전후 JSON 비교

```json
// 변경 전
{
  "label": "민감정보",
  "action": "검토 필요",
  "reason": "AI 문장분류 grade=S / confidence=0.7534 / threshold=0.60"
}

// 변경 후
{
  "label": "민감정보",
  "action": "검토 필요",
  "reason": "AI 문장분류 grade=S / confidence=0.7534 / threshold=0.60",
  "grade": "S",
  "sensitiveType": "문맥 기반 민감정보",
  "sensitiveCategory": "AI_S",
  "source": "ai"
}
```

### 8.3 PHP 측 활용 예시

```php
$reviewItem = $result['reviewTargets'][0];

// grade 바로 사용 가능 (reason 파싱 불필요)
$grade = $reviewItem['grade'];  // "S"
$source = $reviewItem['source']; // "ai"

// C/S/O 선택 UI
if ($grade === 'C') {
    // C급 기본 선택
} elseif ($grade === 'S') {
    // S급 기본 선택
}
```

### 8.4 피드백 학습과의 연계

향후 `POST /api/feedback` 활성화 시 `grade` 필드가 구조적으로 있어 사용자 판단과 AI 추정을 직접 비교 가능하다.

---

## 9. 누적 회귀 테스트 결과

### 9.1 단계별 변화

| 주차 | 이벤트 | 결과 |
|---|---|---|
| 12주차 | xlsx 최초 | 13/13 |
| 13주차 | docx 최초 | 13 + 52 = 65 |
| 14주차 | pptx 추가 | 65 + 67 = 132 |
| 15주차 | hwpx 추가 | 132 + 61 = 193 |
| 16주차 | pdf 추가 | 193 + 48 = 241 |
| **17주차** | **표 탐지 TC + 필드 보완** | **241 + 31 = 272** |

### 9.2 최종 결과

```text
  ✓ xlsx :   13/  13  (0.3초)
  ✓ docx :   71/  71  (0.8초)  (+19: TC19~TC22 + TC5 보완)
  ✓ pptx :   71/  71  (0.5초)  (+4: TC5 보완)
  ✓ hwpx :   65/  65  (0.1초)  (+4: TC5 보완)
  ✓ pdf  :   52/  52  (0.4초)  (+4: TC5 보완)
  합계: 272/272 (2.1초)
```

---

## 10. 17주차 산출물 목록

### 신규 파일

| 파일 | 설명 |
|---|---|
| `src/api/__init__.py` | API 패키지 |
| `src/api/main.py` | FastAPI 앱 (health, version 엔드포인트) |
| `src/api/README.md` | 서버 실행 가이드 |
| `notebooks/test_helpers.py` | TestRunner 공통 헬퍼 |
| `notebooks/run_all_tests.py` | 5종 통합 회귀 테스트 스크립트 |
| `requirements.txt` | Python 의존성 정리 |
| `reports/week17_detector_policy.md` | detector 역할 분담 정책 |

### 변경 파일

| 파일 | 변경 내용 |
|---|---|
| `src/common_apply_utils.py` | `WARNING_PARAGRAPH_NOT_IN_BODY` 제거, 3개 추가 |
| `src/common_apply_result.py` | `CommonReviewItem` 필드 4개 추가 |
| `src/docx_detector.py` | 사용자 작업본 채택 + seen_cells 제거 + warning 분리 |
| `src/hwpx_detector.py` | 표 셀 보조 필드 누락 warning 분리 |
| `src/pptx_detector.py` | shape/cell 보조 필드 누락 warning 분리 |
| `notebooks/13_test_xlsx_regression.py` | TestRunner 마이그레이션 |
| `notebooks/15_test_docx_detector.py` | TestRunner + TC19~TC22 + TC5 보완 |
| `notebooks/17_test_pptx_detector.py` | TestRunner + TC5 보완 |
| `notebooks/19_test_hwpx_detector.py` | TestRunner + TC5 보완 |
| `notebooks/21_test_pdf_detector.py` | TestRunner + TC5 보완 |

### 영향 범위이나 코드 변경 없는 파일

| 파일 | 사유 |
|---|---|
| `src/deidentify_target_builder.py` | `CommonReviewItem` 필드 추가의 데이터 공급원. `DeidentifyTarget`에 이미 `grade`, `sensitive_type`, `sensitive_category`, `source` 필드가 정의되어 있고, `build_deidentify_plan()`도 이를 올바르게 채운다. `make_review_items()`가 `getattr`로 접근하므로 추가 변경 없이 자동 연결됨. |

---

## 10. CommonApplyItem grade/source 추가 (테스트 중 발견)

13절에 상세 내용 기록.

---

## 11. 다음 단계 예정 작업

```text
✓ 7단계: POST /api/detect 통합 엔드포인트
✓ 8단계: 피드백 학습 틀 (no-op)
✓ 9단계: API 스펙 문서 + PHP 팀 협의 자료
```

---

## 12. 9단계: PHP 팀 협의 자료 (week17_php_integration_guide.md)

---

## 13. 추가 보완: CommonApplyItem grade/source 필드 추가

### 13.1 배경

테스트 중 `autoResults`의 각 항목에 C/S/O 등급 정보가 없음을 발견했다.
`reviewTargets`는 17주차에 `grade`를 추가했지만, `autoResults`(`CommonApplyItem`)는 누락되어 있었다.

PHP 팀이 등급별 배지, 필터링, 집계 등 UI를 구현하려면 `autoResults`에도 등급 정보가 필요하다.

### 13.2 변경 내용

**`src/common_apply_result.py`**

`CommonApplyItem`에 필드 2개 추가:

| 필드 | 타입 | 설명 |
|---|---|---|
| `grade` | `str \| None` | "C" / "S" / "O" |
| `source` | `str \| None` | "regex" / "ner" / "ai" / "mixed" |

집계 헬퍼 2개 추가:

```python
grade_for_targets(targets)   # C > S > O 우선순위로 대표 등급 반환
source_for_targets(targets)  # 단일 소스면 그 소스, 여러 소스면 "mixed"
```

**5종 detector 변경** (`docx/pptx/hwpx/pdf_detector.py`, `xlsx_deidentify_apply.py`):
- `grade_for_targets`, `source_for_targets` import 추가
- 최종 `CommonApplyItem` 생성 시 두 필드 채움

### 13.3 집계 정책

**grade (C > S > O 우선순위):**
```text
같은 위치에 C급(VLAN)과 S급(성명)이 함께 있으면 → grade: "C"
S급만 있으면 → grade: "S"
등급 없으면 → grade: null
```

**source:**
```text
regex만 탐지 → source: "regex"
ner만 탐지   → source: "ner"
regex + ner  → source: "mixed"
없으면       → source: null
```

### 13.4 변경 전후 비교

```json
// 변경 전
{
  "label": "VLAN/포트 정보",
  "action": "삭제",
  "originalText": "VLAN 301",
  "appliedText": "(삭제됨)"
}

// 변경 후
{
  "label": "VLAN/포트 정보",
  "action": "삭제",
  "originalText": "VLAN 301",
  "appliedText": "(삭제됨)",
  "grade": "C",
  "source": "regex"
}
```

### 13.5 PHP 팀 활용 예시

```php
foreach ($result['autoResults'] as $item) {
    $grade = $item['grade'];   // "C", "S", "O", null

    // 등급별 배지 색상
    $badgeColor = match($grade) {
        'C' => 'red',
        'S' => 'orange',
        'O' => 'green',
        default => 'gray',
    };

    echo "<span class='badge' style='color:{$badgeColor}'>{$grade}급</span>";
    echo $item['locationLabel'];
}
```

### 13.6 회귀 결과

272/272 통과 (변경 영향 없음)
