# 13주차 docx 탐지 + 안내(guide) 모드 설계

## 1. 목적

13주차의 목적은 docx 파일에서 개인정보/민감정보를 탐지하고, 사용자에게 위치와 조치 방법을 안내하는 것이다.

기존 계획에서는 docx 파일을 직접 수정하는 자동 Apply 방식을 검토했으나, 13주차 시작 전 검토를 통해 방향을 변경했다.

```text
변경 전:
docx 파일 → paragraph 단위 자동 Apply → 비식별화된 docx 저장

변경 후:
docx 파일 → 탐지 → 위치/조치 안내 → 사용자가 원본에서 직접 수정
```

---

## 2. 방향 전환 배경

docx 파일을 paragraph 단위로 자동 치환하면 다음 서식이 손실된다.

```text
1. 굵기, 색상, 폰트, 크기 등 character-level 서식
2. 같은 문단 내 부분 강조
3. 단락 정렬, 들여쓰기 등 일부 paragraph 속성
```

run 단위 보존으로 일부 해결할 수 있으나, 다음 케이스는 run 단위 보존으로도 해결되지 않거나 숨겨진 손실이 발생한다.

```text
1. 하이퍼링크 안의 텍스트와 URL 불일치
2. 필드 코드(MERGEFIELD, 날짜, 페이지 번호 등) 깨짐
3. SmartArt, 차트, 도형 안의 텍스트
4. 추적 변경, 주석 안의 텍스트
5. 섹션 break를 가진 paragraph
6. 표 셀의 vertical merge, 수직 정렬 영향
```

특히 **숨겨진 손실(필드 깨짐, 하이퍼링크 URL 불일치 등)이 사용자가 즉시 발견하기 어렵다**는 점이 가장 큰 위험이다.

회사 환경에서 docx 비식별화 대상은 주로 보고서, 공문, 계약서 등 서식이 중요한 문서이다. 자동 수정 후 사용자가 결과 파일을 다시 검토해야 한다면 자동화 효과가 크지 않다.

따라서 13주차부터는 다음 정책을 적용한다.

```text
xlsx: 자동 Apply 유지 (셀 단위 구조라 서식 손실 위험 낮음)
docx: 탐지 + 안내(guide) 방식
pptx: 13주차 결정에 따라 docx와 동일하게 안내 방식
hwpx: docx와 동일하게 안내 방식
```

이 방식은 10주차 `DeidentifyPlan`의 본질("어디를 어떻게 비식별화할지")과 더 잘 맞는다.

---

## 3. 13주차 핵심 목표

```text
1. docx 파일 paragraph 순회
2. regex + NER + AI 탐지 수행
3. DeidentifyPlan 생성
4. 사용자 안내용 CommonApplyResult 생성 (applyMode="guide")
5. xlsx Apply와 동일한 공통 결과 구조 유지
6. 12주차 코드에서 재사용 가능한 부분을 공통 모듈로 추출
```

---

## 4. 산출물

```text
src/common_apply_utils.py (신규)
src/docx_detector.py (신규)
notebooks/15_test_docx_detector.py
notebooks/16_test_real_docx_detection.py
reports/week13_docx_detection_guide.md
```

기존 파일 수정:

```text
src/common_apply_result.py: applyMode 필드 추가
src/xlsx_deidentify_apply.py: common_apply_utils 사용으로 리팩토링
```

각 파일 역할:

| 파일 | 역할 |
|---|---|
| `common_apply_utils.py` | xlsx/docx 등에서 공통으로 사용하는 유틸 |
| `docx_detector.py` | docx 파일에서 탐지 + guide 생성 |
| `15_test_docx_detector.py` | TC 기반 docx detector 단위 테스트 |
| `16_test_real_docx_detection.py` | 실제 docx 통합 테스트 |

---

## 5. applyMode 필드 추가

`CommonApplyResult`에 모드 표시 필드를 추가한다.

```python
@dataclass
class CommonApplyResult:
    fileType: str
    applyMode: str  # "applied" | "guide"
    inputFilePath: str
    outputFilePath: str | None
    autoResults: list[CommonApplyItem]
    reviewTargets: list[CommonReviewItem]
    warnings: list[str]
    summary: CommonApplySummary
```

값 의미:

| applyMode | 의미 | outputFilePath |
|---|---|---|
| `applied` | 시스템이 실제 파일을 수정해 결과 파일을 생성함 | 결과 파일 경로 |
| `guide` | 시스템은 위치/조치만 안내하고 사용자가 직접 수정 | None |

xlsx Apply는 `applyMode="applied"`로 설정한다.
docx/pptx/hwpx detector는 `applyMode="guide"`로 설정한다.

프론트엔드 동작:

```text
applied 모드:
- 결과 파일 다운로드 버튼 표시
- "이 파일은 자동 비식별화 처리되었습니다" 안내

guide 모드:
- 위치별 안내 목록 표시
- "원본 파일에서 다음 위치를 직접 수정하세요" 안내
- 다운로드 버튼 없음
```

---

## 6. guide 모드에서 CommonApplyItem 의미

guide 모드에서도 기존 `CommonApplyItem` 구조를 그대로 사용한다.

필드 의미 재정의:

| 필드 | applied 모드 | guide 모드 |
|---|---|---|
| `originalText` | 원본 셀 값 | 원본 paragraph 텍스트 |
| `appliedText` | 실제 적용된 결과 | **권장** 결과 (preview) |
| `status` | 실제 적용 결과 | 적용 가능 여부 |
| `appliedTargetCount` | 실제 적용된 target 수 | 권장 적용 가능 target 수 |
| `skippedTargetCount` | 실제 skip된 target 수 | 권장 불가 target 수 |
| `warnings` | 적용 중 발생한 경고 | 안내 생성 중 발생한 경고 |

guide 모드에서 `appliedText`는 11주차 `apply_targets_to_text()`를 통해 메모리에서만 생성된 preview 문자열이다. 실제 파일은 변경되지 않는다.

`status`는 guide 모드에서도 동일한 값을 사용한다.

```text
applied: 모든 target이 권장 가능
partial: 일부 target만 권장 가능 (위치 어긋남 등)
skipped: 권장 불가 (paragraph index 범위 초과 등)
```

### 6.1 필드 의미 혼동 방지

guide 모드에서 `appliedText`, `appliedTargetCount`, `skippedTargetCount`는 의미가 다르므로 코드와 프론트엔드 표시에서 혼동을 막아야 한다.

**코드 측 보완:**

`CommonApplyItem` 정의부에 다음 주석을 반드시 명시한다.

```python
@dataclass
class CommonApplyItem:
    ...
    # guide 모드에서는 appliedText가 실제 적용 결과가 아니라
    # 권장 preview 문자열을 의미한다.
    # appliedTargetCount는 "권장 가능 target 수",
    # skippedTargetCount는 "권장 불가 target 수"로 해석한다.
    appliedText: str
    appliedTargetCount: int
    skippedTargetCount: int
```

**프론트엔드 측 보완:**

`applyMode`에 따라 표시 문구를 다르게 사용한다.

```text
applied 모드:
- "적용 결과": appliedText
- "적용된 항목": appliedTargetCount건

guide 모드:
- "권장 결과": appliedText
- "권장 항목": appliedTargetCount건
- "권장 불가": skippedTargetCount건
```

13주차에서는 구조 변경을 최소화하기 위해 기존 필드명을 유지한다. 향후 명확성이 더 필요하면 `previewText` 필드를 별도로 추가하는 방향도 검토한다.

---

## 7. paragraph 위치 정책

### 7.1 paragraphIndex 범위 정의

```text
1. paragraphIndex는 doc.paragraphs (본문)만 가리킨다.
2. 표/헤더/푸터/각주 안의 paragraph는 13주차 PoC에서 인덱싱 대상에서 제외한다.
3. detection 단계에서 본문 외 위치를 가리키는 paragraphIndex가 들어오면
   skip + warning 처리한다.
```

13주차에서는 본문만 처리하고, 표/헤더/푸터 처리는 별도 주차에서 다룬다.

### 7.2 위치 메타데이터

기존 `document_units.py`의 `paragraphNo`를 유지하고, 향후 표/헤더/푸터 확장을 대비해 `section` 필드를 추가한다.

```python
location_meta = {
    "fileType": "docx",
    "section": "body",      # 13주차에서는 "body"만 사용
    "paragraphNo": para_index,  # 0-based, 빈 문단 포함 원문 인덱스 유지
}
```

`paragraphNo`로 통일하는 이유:

```text
1. 기존 코드 호환성 유지
2. paragraphIndex로 바꾸면 document_units.py 등 여러 파일 변경 필요
3. 이름 차이보다 의미 정의가 더 중요
```

`section` 필드를 추가하는 이유:

```text
1. 13주차 PoC는 "body"만 처리하지만, 14주차 이후 표/헤더/푸터 확장 예정
2. 향후 section="table_cell", "header", "footer", "footnote" 등으로 확장 가능
3. 13주차에 추가해두면 향후 location_meta 구조 변경 비용이 없음
4. detection 단계에서 본문 외 section 값이 들어오면 13주차에서는 skip + warning
```

`paragraphNo`는 빈 문단을 제외한 인덱스가 아니라, `doc.paragraphs` 기준 원문 인덱스를 그대로 사용한다. 빈 문단은 탐지 대상에서 제외하더라도 번호 체계는 원문 기준을 유지한다.

### 7.3 locationLabel 강화

guide 모드에서는 사용자가 docx 원본에서 해당 위치를 찾아야 한다. Word에는 paragraph index로 이동하는 기능이 없으므로, 사용자는 보통 Ctrl+F 검색으로 찾는다.

따라서 `locationLabel`은 section 표시 + paragraph 번호 + context 일부를 포함한다.

```python
# 변경 전
location_label = "17번째 문단"

# 변경 후
location_label = "본문 17번째 문단: 담당자 김도윤의 이메일은..."
```

`locationLabel` 생성 규칙:

```text
1. section 접두어 ("본문" 등)
2. paragraph 번호 (1-based로 표시)
3. ":" 구분자
4. paragraph 텍스트의 앞부분 (최대 30자, 초과 시 "...")
```

예:

```python
location_label = f"본문 {para_index + 1}번째 문단: {context_preview}"
```

```text
paragraph 0: "담당자 김도윤의 이메일은 test@example.com입니다."
→ locationLabel: "본문 1번째 문단: 담당자 김도윤의 이메일은 test@example.c..."

paragraph 16: "짧은 문단"
→ locationLabel: "본문 17번째 문단: 짧은 문단"
```

`section` 접두어를 명시하는 이유는, 향후 표/헤더/푸터 탐지가 추가될 때 위치 체계가 자연스럽게 확장될 수 있기 때문이다.

```text
14주차 이후 예시:
"본문 17번째 문단: ..."
"표 3행 2열 1번째 문단: ..."
"머리글 1번째 문단: ..."
"바닥글 1번째 문단: ..."
```

### 7.4 향후 개선: matched 주변 context 기반 locationLabel

현재 규칙은 paragraph 앞부분 30자를 보여준다. 그러나 긴 문단에서 detection이 뒤쪽에 있으면 사용자가 Ctrl+F 검색 시 위치를 빠르게 찾기 어렵다.

향후 개선 항목:

```text
locationLabel 또는 별도 필드에 matched 주변 context를 포함한다.

예:
"본문 17번째 문단: ...김도윤의 이메일은 test@example.com입니다..."
```

13주차 PoC에서는 구현 복잡도를 낮추기 위해 paragraph 앞부분 30자로 통일한다.

---

## 8. 빈 문단 처리

빈 문단 판단은 단순 `paragraph.text == ""`이 아니라 `strip()` 기준으로 한다.

```text
not paragraph.text.strip()
→ detection 자체가 생성되지 않음 (탐지 단계에서 제외)
```

이유:

```text
1. 실제 docx에는 공백, 탭, 줄바꿈만 있는 문단이 자주 존재한다.
2. 단순 == "" 비교로는 이런 문단을 걸러내지 못한다.
3. strip() 후 빈 문자열이면 탐지 의미가 없으므로 제외한다.
```

빈 문단 순회 시 paragraphNo 처리:

```python
for para_index, para in enumerate(doc.paragraphs):
    text = para.text
    if not text.strip():
        continue

    location_meta = {
        "fileType": "docx",
        "section": "body",
        "paragraphNo": para_index,  # 원문 인덱스 유지
    }
```

탐지 대상에서는 제외하지만, `paragraphNo`는 `doc.paragraphs` 기준 원문 인덱스를 유지한다. 이렇게 해야 사용자가 Word에서 위치를 찾을 때 일관된 번호를 사용할 수 있다.

탐지 함수는 빈 paragraph를 처음부터 순회 대상에서 제외하므로, detector 단계에서 빈 문단이 들어올 일이 없다.

다만 방어 코드로 guide builder에서도 빈 paragraph를 가리키는 target은 skip + warning 처리한다.

---

## 9. context 불일치 정책

xlsx와 동일한 정책을 적용한다.

```text
1. target.context와 paragraph.text가 다르면 warning을 남긴다.
2. paragraph.text[start:end] == target.matched이면 적용 가능으로 표시한다.
3. paragraph.text[start:end] != target.matched이면 권장 불가로 표시한다.
4. NFC 정규화 후에만 일치하는 경우도 권장 불가로 표시한다.
```

guide 모드에서는 "적용"이 "권장"으로 바뀔 뿐, 검증 로직은 동일하다.

### 9.1 코드화된 warning type

`warnings`는 사람이 읽는 문자열이지만, 프론트엔드에서 아이콘/필터를 사용할 수 있도록 코드화된 type을 함께 보존한다.

warning type 정의:

| type 코드 | 의미 |
|---|---|
| `context_mismatch` | target.context와 현재 문단 텍스트가 다름 |
| `slice_mismatch` | text[start:end]가 matched와 다름 |
| `unicode_normalization_mismatch` | NFC 정규화 후에만 일치 |
| `paragraph_out_of_range` | paragraphNo가 문서 범위를 벗어남 |
| `missing_paragraph_no` | paragraphNo가 없음 |
| `paragraph_not_in_body` | section이 body가 아님 (13주차 범위 외) |
| `empty_paragraph_target` | 빈 paragraph를 가리키는 target |

warning 저장 형식:

```python
# 사람이 읽는 문자열
warnings: list[str]

# 코드화된 type (병행 보존)
warning_types: list[str]
```

13주차에서는 두 가지를 함께 보존하는 가장 단순한 방식으로 `warnings` 문자열에 type 접두어를 포함한다.

```text
[context_mismatch] 본문 17번째 문단: target.context와 현재 문단 텍스트가 다릅니다.
[slice_mismatch] 본문 17번째 문단: text[12:28]이 matched와 다릅니다.
```

향후 프론트엔드 연결 시 type 코드를 별도 필드로 분리할 수 있다. 13주차에서는 문자열 접두어 방식으로 시작하고, 필요해지면 다음과 같이 확장한다.

```python
# 향후 확장 예시
@dataclass
class CommonApplyWarning:
    type: str           # "context_mismatch" 등
    message: str        # 사람이 읽는 메시지
    target_index: int   # 어느 target에서 발생했는지
```

13주차 구현 시점에는 `warnings: list[str]` 구조를 유지하면서 type 접두어만 추가한다.

---

## 10. 공통 모듈 추출

`src/common_apply_utils.py`를 신규 생성하고 다음 함수를 12주차 xlsx Apply에서 추출한다.

```python
# common_apply_utils.py
def normalize_nfc(value) -> str
def make_output_path(input_path, output_path=None, suffix="_deidentified") -> str
def validate_slice_against_text(text, target) -> str | None  # 일반화
def make_status(applied_count, skipped_count) -> str
def sort_targets_for_display(targets) -> list[DeidentifyTarget]
def labels_for_targets(targets) -> str
def actions_for_targets(targets) -> str
def make_location_label_with_context(base_label, context, max_length=30) -> str
```

xlsx_deidentify_apply.py는 이 모듈을 import하도록 수정한다.

`validate_slice_against_matched`는 `validate_slice_against_text`로 이름을 일반화한다. 함수 시그니처는 그대로 유지된다.

```python
# 변경 전 (xlsx 전용 이름)
validate_slice_against_matched(cell_value: str, target)

# 변경 후 (일반화)
validate_slice_against_text(text: str, target)
```

---

## 11. docx detector 처리 흐름

```text
1. input docx 로드 (python-docx 또는 docx2python)
2. doc.paragraphs 순회
3. 각 paragraph에 대해:
   a. paragraph.text가 비어있으면 skip
   b. TextUnit 생성 (location_meta에 fileType=docx, paragraphNo)
   c. locationLabel 강화 (context 일부 포함)
4. 모든 TextUnit에 대해 regex + NER + AI 탐지
5. DeidentifyPlan 생성
6. DeidentifyPlan을 guide 모드 CommonApplyResult로 변환
```

guide 변환 흐름:

```text
DeidentifyPlan.auto_targets
→ paragraphNo 기준으로 그룹화
→ paragraph.text 기준으로 slice 검증
→ apply_targets_to_text()로 preview 생성 (메모리만)
→ CommonApplyItem 생성 (applyMode="guide")

DeidentifyPlan.review_targets
→ CommonReviewItem 변환
```

---

## 12. 주요 함수

`src/docx_detector.py`:

```python
def detect_in_docx(
    input_path: str,
    *,
    ner_model_path: str | None = None,
    ai_model_path: str | None = None,
    ner_threshold: float = 0.8,
    ai_threshold: float = 0.6,
) -> DeidentifyPlan
```

```python
def build_guide_for_docx(
    input_path: str,
    plan: DeidentifyPlan,
    *,
    deletion_mode: str = "delete",
) -> CommonApplyResult
```

```python
def detect_and_build_guide_for_docx(
    input_path: str,
    *,
    ner_model_path: str | None = None,
    ai_model_path: str | None = None,
    ner_threshold: float = 0.8,
    ai_threshold: float = 0.6,
    deletion_mode: str = "delete",
) -> CommonApplyResult
```

`detect_and_build_guide_for_docx()`는 두 함수를 묶은 편의 함수다.

보조 함수:

```text
load_docx()
iter_paragraphs()
make_paragraph_text_unit()
group_targets_by_paragraph()
validate_paragraph_target()
build_guide_item_for_paragraph()
```

---

## 13. 함수 시그니처 결정

xlsx의 `apply_plan_to_xlsx()`와 docx의 `build_guide_for_docx()`는 시그니처가 다르다.

```python
# xlsx (applied 모드)
apply_plan_to_xlsx(
    input_path,
    plan,
    output_path=None,
    deletion_mode="delete",
) -> CommonApplyResult

# docx (guide 모드)
build_guide_for_docx(
    input_path,
    plan,
    deletion_mode="delete",
) -> CommonApplyResult
```

차이점:

```text
xlsx: output_path 파라미터 있음 (실제 파일 저장)
docx: output_path 없음 (저장하지 않음)
```

향후 pptx/hwpx도 guide 모드라면 동일한 시그니처를 따른다.

```python
build_guide_for_pptx(input_path, plan, deletion_mode="delete")
build_guide_for_hwpx(input_path, plan, deletion_mode="delete")
```

---

## 14. 테스트 케이스

`notebooks/15_test_docx_detector.py`:

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC1 | 이메일이 있는 paragraph 1개 | guide 1건, applied 권장 |
| TC2 | 성명이 있는 paragraph 1개 | guide 1건, applied 권장 |
| TC3 | 한 paragraph에 성명 + 이메일 동시 | guide 1건, target 2개 |
| TC4 | 내부 IP 삭제 권장 | guide 1건, action=삭제 |
| TC5 | reviewTargets 보존 | CommonReviewItem으로 변환 |
| TC6 | paragraphNo 없음 | skip + warning (missing_paragraph_no) |
| TC7 | paragraphNo 범위 초과 | skip + warning (paragraph_out_of_range) |
| TC8 | context 불일치, slice 일치 | applied 권장 + warning (context_mismatch) |
| TC9 | slice 불일치 | skipped + warning (slice_mismatch) |
| TC10 | 여러 paragraph에 target 분산 | 모두 guide 생성 |
| TC11 | summary 정합성 | 검증식 통과 |
| TC12 | deletion_mode=mark | (삭제됨) 표시 확인 |
| TC13 | 빈 paragraph는 detection 대상 제외 | TextUnit 생성 안 됨 |
| TC14 | locationLabel에 "본문 N번째 문단:" 형식 + context | 30자 + "..." |
| TC15 | applyMode="guide", outputFilePath=None | 확인 |
| TC16 | 공백/탭만 있는 paragraph | TextUnit 생성 안 됨 (strip() 기준) |
| TC17 | section이 body가 아닌 target | skip + warning (paragraph_not_in_body) |
| TC18 | 같은 paragraph 내 target 위치 겹침 | 충돌 처리 정책에 따른 결과 |

### 14.1 TC18 target 겹침 정책

같은 paragraph 안에서 NER 성명 탐지와 AI 탐지, 또는 regex와 NER이 같은 구간을 중복으로 잡는 경우가 발생할 수 있다.

이 케이스는 이미 10주차 `DeidentifyPlan` 생성 단계에서 source 우선순위(regex > ner > ai)로 처리된다. 즉, guide 단계로 들어오는 시점에는 겹침이 제거되어 있어야 한다.

guide builder의 정책:

```text
1. DeidentifyPlan.auto_targets 단계에서 이미 겹침이 제거되었다고 가정한다.
2. 그럼에도 같은 paragraph에 target span이 겹치는 경우(예: 다른 source 간 잔여 겹침),
   apply_targets_to_text()가 start 내림차순으로 적용하므로 후순위는 자연스럽게 처리된다.
3. 잔여 겹침이 감지되면 warning을 남긴다 (overlap_target).
```

TC18은 다음 두 케이스를 검증한다.

```text
케이스 A: 10주차 단계에서 정상 제거된 경우
→ guide 단계에서 겹침 없음, 정상 권장

케이스 B: 잔여 겹침이 남은 경우 (방어 코드 검증)
→ start 내림차순 적용 후 결과 확인
→ warning 발생 확인
```

---

## 15. 실제 docx 통합 테스트

`notebooks/16_test_real_docx_detection.py`:

```text
실제 docx 파일
→ 모든 paragraph 순회 (본문만)
→ regex_detector.py로 정규식 탐지
→ NER 성명 탐지
→ AI 문장분류
→ DeidentifyPlan 생성
→ build_guide_for_docx()
→ CommonApplyResult (applyMode="guide")
```

정규식 탐지는 12주차와 동일하게 `src/regex_detector.py`를 단일 소스로 사용한다.

CLI 옵션:

```bash
python notebooks/16_test_real_docx_detection.py "data\sample.docx" \
  --ner-model-path "models\hf\KoELECTRA-small-v3-modu-ner" \
  --ai-model-path "models\privacy_cso_char_keras_model.keras" \
  --deletion-mode mark \
  --force-mock-review
```

12주차에서 남긴 `--force-mock-review` 옵션도 함께 적용해 reviewTargets 흐름을 실증한다.

---

## 16. 12주차에서 가져오는 결정

12주차에서 결정한 다음 정책은 그대로 적용한다.

```text
1. regex_detector.py 단일 소스 사용
2. deletion_mode delete/mark 분리
3. NFC 정규화는 비교 보조용 (실제 적용은 원본 인덱스 기준)
4. validate_slice_against_text()로 slice 검증
5. context 불일치는 warning만, slice 불일치는 skip
6. label/action 표시 순서는 start 오름차순
7. summary.autoTargetCount는 appliedTargetCount + skippedTargetCount 합
```

---

## 17. 13주차에서 하지 않을 것

```text
1. docx 파일 자동 수정/저장
2. paragraph 단위 자동 치환
3. run 단위 서식 보존 자동 치환
4. 표 내부 paragraph 탐지
5. header/footer paragraph 탐지
6. comment/footnote paragraph 탐지
7. 하이퍼링크 URL 처리
8. 필드 코드 처리
9. SmartArt, 차트, 도형 안의 텍스트 처리
10. pptx, hwpx 탐지
```

4~6번은 별도 주차에서 detector 확장으로 추가한다. 1~3번은 B안 결정에 따라 향후에도 자동 수정은 수행하지 않는다.

---

## 18. 사용자 시나리오

13주차 결과물의 사용자 시나리오는 다음과 같다.

```text
1. 사용자가 docx 파일을 업로드한다.
2. 시스템이 paragraph 단위로 탐지 수행한다.
3. 시스템이 결과를 guide 모드 CommonApplyResult로 반환한다.
4. 프론트엔드가 위치별로 안내 목록을 표시한다.
   - 위치 (1번째 문단: 담당자 김도윤의 이메일은...)
   - 항목 (이메일 주소, 성명)
   - 조치 (마스킹, 삭제)
   - 원문 (담당자 김도윤의 이메일은 test@example.com입니다.)
   - 권장 결과 (담당자 ***의 이메일은 ****************입니다.)
5. 사용자가 원본 docx 파일에서 직접 해당 위치를 찾아 수정한다.
   - locationLabel의 context 일부를 검색 키워드로 사용
6. 사용자가 수정 완료 후 docx 파일을 사용한다.
```

reviewTargets는 별도 목록으로 표시한다.

```text
- 위치 (17번째 문단: 입찰 제안 평가표를 검토했습니다.)
- 항목 (민감정보)
- 조치 (검토 필요)
- 문맥 (입찰 제안 평가표를 검토했습니다.)
- 사유 (AI 문장분류 결과 grade=C / confidence=0.85)
```

---

## 19. 12주차 보고서 보완

12주차 보고서에 B안 전환 배경을 명시한다.

```text
12주차 xlsx Apply는 자동 Apply 방식을 유지한다.
이는 xlsx 셀 단위 구조가 서식 손실 위험이 낮기 때문이다.

이후 docx, pptx, hwpx는 13주차 검토 후 자동 Apply 대신
탐지 + 안내(guide) 방식으로 전환하기로 결정했다.

이는 paragraph/run 단위 텍스트 치환이 굵기, 색상, 폰트,
하이퍼링크, 필드 코드 등의 서식 손실을 유발할 수 있고,
숨겨진 손실(필드 깨짐, 하이퍼링크 URL 불일치 등)이
사용자가 즉시 발견하기 어렵기 때문이다.

따라서 13주차부터 docx Apply는 다음 정책을 따른다.

1. 시스템은 docx 파일을 직접 수정하지 않는다.
2. 시스템은 탐지 결과와 위치, 조치, 권장 preview를 제공한다.
3. 사용자가 원본 docx에서 직접 수정한다.
```

---

## 20. 13주차 이후 계획

```text
14주차:
pptx detector + guide PoC

15주차:
hwpx detector + guide PoC

16주차 이후:
- docx 표/헤더/푸터 탐지 확장
- 프론트엔드 guide 모드 UI 정식 연결
- DLP 도입 시점에 따른 도구 위치 재검토
```

xlsx Apply는 자동 처리를 유지하므로, 사용자 경험은 다음과 같이 분리된다.

```text
xlsx 업로드 → 자동 비식별화 → 결과 파일 다운로드
docx 업로드 → 탐지 + 안내 → 사용자 직접 수정
pptx 업로드 → 탐지 + 안내 → 사용자 직접 수정
hwpx 업로드 → 탐지 + 안내 → 사용자 직접 수정
```

프론트엔드는 `applyMode` 필드로 이 두 흐름을 구분한다.

---

## 20.1 13주차 구현 순서

디버깅 포인트를 최소화하기 위해 다음 순서로 진행한다.

```text
1. CommonApplyResult에 applyMode 필드 추가
2. src/common_apply_utils.py 생성 및 공통 함수 추출
3. src/xlsx_deidentify_apply.py 리팩토링 (공통 모듈 사용, applyMode="applied")
4. docx_detector.py에서 paragraph → TextUnit 생성 (본문만, strip() 기준)
5. regex 탐지만 먼저 연결해서 guide 구조 완성
6. build_guide_for_docx() 구현 (apply_targets_to_text() 재사용)
7. TC1~TC18 단위 테스트 통과
8. NER/AI 모델 연결
9. 실제 docx 통합 테스트 (16_test_real_docx_detection.py)
10. 보고서 작성 (week13_docx_detection_guide.md)
11. 12주차 보고서 보완 (B안 전환 배경 명시)
```

처음부터 regex/NER/AI를 동시에 붙이면 디버깅 포인트가 너무 많아진다. regex만 먼저 연결해서 guide 구조를 완성한 다음 NER/AI를 추가하는 방식이 안전하다.

xlsx 리팩토링을 먼저 하는 이유는, 공통 모듈 추출 후 기존 xlsx 테스트가 모두 통과해야 docx 구현의 안전 기반이 확보되기 때문이다.

---

## 21. 결론

13주차는 docx 비식별화에 대해 자동 수정이 아닌 탐지 + 안내 방식을 채택한다.

이 방식은 다음을 동시에 달성한다.

```text
1. 서식 100% 보존 (사용자가 직접 수정하므로 시스템이 깨뜨릴 일 없음)
2. 핵심 가치 유지 (위치 + 조치 안내는 10주차 DeidentifyPlan의 본질)
3. 구현 복잡도 감소 (run 단위 보존 및 XML 조작 불필요)
4. 회사 문서 형식에 강건 (docx/pptx/hwpx 모두 동일 패턴)
```

13주차 산출물은 다음이다.

```text
공통 모듈 추출 + docx detector + guide builder + applyMode 필드 추가
```

핵심 함수:

```text
detect_in_docx(input_path) -> DeidentifyPlan
build_guide_for_docx(input_path, plan) -> CommonApplyResult (applyMode="guide")
```

xlsx Apply 시그니처와 호환되는 형태로 유지하여, 프론트엔드가 두 흐름을 동일한 구조로 처리할 수 있다.

### 21.1 외부 검토 반영 사항

13주차 시작 전 외부 검토에서 받은 5가지 보완 사항을 반영했다.

```text
1. locationLabel을 "본문 N번째 문단: ..." 형식으로 변경 (섹션 7.3)
2. location_meta에 section="body" 필드 추가 (섹션 7.2)
3. 빈 문단 판단을 paragraph.text.strip() 기준으로 변경 (섹션 8)
4. warning을 코드화된 type 접두어로 남기기 (섹션 9.1)
5. target 겹침 테스트 케이스 TC18 추가 (섹션 14.1)
```

추가로 다음을 반영했다.

```text
6. CommonApplyItem 필드 의미 혼동 방지 주석 및 프론트엔드 표시 규칙 (섹션 6.1)
7. locationLabel matched 주변 context 기반 강화는 향후 개선으로 분리 (섹션 7.4)
8. 13주차 구현 순서 명시 (섹션 20.1)
```

