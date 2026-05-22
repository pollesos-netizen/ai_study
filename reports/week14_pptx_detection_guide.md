# 14주차 pptx 탐지 + 안내(guide) 모드 구현 결과

## 1. 목적

14주차의 목적은 pptx 파일에서 개인정보/민감정보를 탐지하고, 사용자에게 위치와 조치 방법을 안내하는 것이었다.

13주차에서 docx에 대해 채택한 탐지 + 안내 방식을 pptx에도 동일하게 적용한다.

```text
docx 파일 → DeidentifyPlan → build_guide_for_docx() → CommonApplyResult (guide)
pptx 파일 → DeidentifyPlan → build_guide_for_pptx() → CommonApplyResult (guide)
```

xlsx만 자동 Apply를 유지하고, docx/pptx/hwpx는 guide 모드로 통일한다.

---

## 2. docx와의 공통점

13주차에서 정립한 구조를 그대로 재사용한다.

```text
1. CommonApplyResult.applyMode = "guide"
2. outputFilePath = None
3. 11주차 apply_targets_to_text()로 권장 결과(appliedText) preview 생성
4. validate_slice_against_text()로 slice 검증
5. context 불일치 시 warning, slice 불일치 시 skip
6. 코드화된 warning type 접두어 ([context_mismatch], [slice_mismatch] 등)
7. deletion_mode delete/mark 정책 동일
8. reviewTargets 자동 적용 없이 별도 보존
9. 빈 paragraph(strip 기준) 탐지 대상 제외
10. 탐지 함수 주입형 (regex/NER/AI 어댑터)
```

`src/common_apply_utils.py`의 공통 함수는 그대로 사용한다.

---

## 3. docx와의 차이점

pptx는 docx와 다음 점에서 다르다.

### 3.1 위치 단위가 더 복잡함

docx는 본문 paragraph와 표 셀이라는 두 가지 위치 단위로 충분했다.
pptx는 슬라이드를 기준으로 다음 4가지 위치 단위가 있다.

```text
1. shape_text:  일반 텍스트 shape (text_frame.paragraphs)
2. table_cell:  표 shape의 각 셀 (cell.text_frame.paragraphs)
3. notes:       발표자 노트 (notes_slide.notes_text_frame.paragraphs)
4. (그룹 내부): 그룹 shape 한 단계 재귀 분해 → 위 3가지 중 하나로 분류
```

### 3.2 shape 번호의 사용자 식별성이 낮음

docx의 paragraphNo는 사용자가 Word에서 셀 수 있지만, pptx의 shapeNo는 PowerPoint에서 사용자가 찾을 방법이 없다.

따라서 `shapeNo`는 `location_meta`에는 저장하되 `locationLabel`에는 노출하지 않는다.

```text
# docx
본문 17번째 문단: ...

# pptx (shape_text)
1번 슬라이드: ...        ← shapeNo를 라벨에 표시하지 않음
```

표 셀은 행/열이 시각적으로 명확하므로 그대로 표시한다.

```text
1번 슬라이드 표 N행 M열: ...
```

### 3.3 그룹 shape 처리

pptx에는 그룹 shape 개념이 있다. 그룹 shape 자체는 텍스트가 없지만, 그 안에 텍스트 shape이나 표 shape이 포함된다.

```text
처리 정책:
- 그룹 shape이 발견되면 한 단계 재귀 분해
- 그 안의 텍스트 shape, 표 shape 모두 정상 탐지
- 그룹 안의 그룹은 14주차 PoC 범위 외
```

### 3.4 발표자 노트 처리

docx에는 없는 위치 단위다. pptx에는 슬라이드별로 발표자 노트가 있다.

```text
slide.notes_slide.notes_text_frame
```

회사 ppt에서 발표자 노트에 개인정보가 들어가는 경우가 흔하므로 14주차 범위에 포함시켰다.

---

## 4. 구현 산출물

```text
src/pptx_detector.py                   (신규)
src/common_apply_utils.py              (pptx 전용 warning type 4개 추가)
notebooks/17_test_pptx_detector.py     (TC1~TC21 단위 테스트)
notebooks/18_test_real_pptx_detection.py (실제 pptx 통합 테스트)
reports/week14_pptx_detection_guide.md (본 문서)
```

기존 파일 변경:

```text
src/common_apply_utils.py: pptx 전용 warning type 4개 추가
  - WARNING_MISSING_SLIDE_NO
  - WARNING_SLIDE_OUT_OF_RANGE
  - WARNING_SHAPE_NOT_FOUND
  - WARNING_UNKNOWN_SECTION
```

13주차에 작성된 다음 파일은 변경 없이 재사용한다.

```text
src/common_apply_result.py
src/deidentify_apply.py
src/deidentify_target_builder.py
src/regex_detector.py
```

---

## 5. pptx 위치 정책

### 5.1 location_meta 구조

section 값에 따라 필드 구성이 다르다.

```python
# shape_text (일반 텍스트 shape)
{
    "fileType": "pptx",
    "slideNo": 0,
    "section": "shape_text",
    "shapeNo": 3,
    "paragraphNo": 0,
}

# table_cell (일반 표 셀)
{
    "fileType": "pptx",
    "slideNo": 0,
    "section": "table_cell",
    "shapeNo": 5,
    "rowNo": 1,
    "colNo": 2,
    "paragraphNo": 0,
    "tableIndex": 0,        # 슬라이드 내 표 순번 (0-based)
}

# notes (발표자 노트)
{
    "fileType": "pptx",
    "slideNo": 0,
    "section": "notes",
    "paragraphNo": 0,
}

# group_shape_text (그룹 내부 텍스트 shape)
{
    "fileType": "pptx",
    "slideNo": 0,
    "section": "group_shape_text",
    "shapeNo": 1,              # 그룹 내부 child shape 번호
    "groupShapeNo": 4,         # 부모 group의 shape 번호
    "paragraphNo": 0,
}

# group_table_cell (그룹 내부 표 셀)
{
    "fileType": "pptx",
    "slideNo": 0,
    "section": "group_table_cell",
    "shapeNo": 2,              # 그룹 내부 child shape 번호
    "groupShapeNo": 4,         # 부모 group의 shape 번호
    "rowNo": 0,
    "colNo": 1,
    "paragraphNo": 0,
    "tableIndex": 1,           # 슬라이드 내 표 순번 (그룹 외부 표와 합산)
}
```

`notes`는 슬라이드 단위로 한 개만 존재하므로 `shapeNo`가 없다.

`group_*` section의 `shapeNo`는 부모 group 내부의 child shape 번호다. 부모 group 자체의 shape 번호는 `groupShapeNo`에 별도 저장한다. 이렇게 분리하면 같은 group 안에 텍스트박스가 여러 개여도 위치 key가 충돌하지 않는다.

`tableIndex`는 슬라이드 단위 0-based 표 순번이며, 그룹 외부 표와 그룹 내부 표가 같은 카운터를 공유한다. 슬라이드 전체에서 N번째 표라는 일관된 의미를 가진다.

### 5.2 paragraphNo 의미 분리

`paragraphNo`는 section에 따라 다른 paragraph 모음의 인덱스를 가리킨다.

```text
section="shape_text" / "group_shape_text":  shape.text_frame.paragraphs 인덱스
section="table_cell" / "group_table_cell":  cell.text_frame.paragraphs 인덱스
section="notes":                              notes_text_frame.paragraphs 인덱스
```

section 값으로 구분되므로 동작 충돌은 없으나, 코드를 읽는 입장에서는 의미가 다르다는 점을 명시한다.

모든 `paragraphNo`는 빈 paragraph를 포함한 원문 인덱스를 유지한다. (탐지 대상에서는 제외하지만 번호 체계는 원문 기준)

### 5.3 1-based / 0-based 표시 규칙

```text
location_meta의 모든 *No 필드: 0-based로 저장
locationLabel: 사용자 표시용이며 1-based로 표시
```

```python
# location_meta
{"slideNo": 0, "rowNo": 1, "colNo": 2}

# locationLabel
"1번 슬라이드 표 2행 3열: ..."
```

---

## 6. locationLabel 형식

section별로 형식이 다르다.

| section | 형식 |
|---|---|
| `shape_text` | `"{slide_idx_1based}번 슬라이드: context..."` |
| `table_cell` | `"{slide_idx_1based}번 슬라이드 표 {table_1based}번 {row_1based}행 {col_1based}열: context..."` |
| `notes` | `"{slide_idx_1based}번 슬라이드 발표자 노트: context..."` |
| `group_shape_text` | `"{slide_idx_1based}번 슬라이드 (그룹 내부): context..."` |
| `group_table_cell` | `"{slide_idx_1based}번 슬라이드 (그룹 내부) 표 {table_1based}번 {row_1based}행 {col_1based}열: context..."` |

예:

```text
1번 슬라이드: 담당자 김도윤의 이메일은 test@example.c...
2번 슬라이드 표 1번 2행 3열: 010-1234-5678
2번 슬라이드 표 2번 1행 1열: 부서별 통계
1번 슬라이드 발표자 노트: 회의 후 담당자에게...
3번 슬라이드 (그룹 내부): 그룹으로 묶인 텍스트...
3번 슬라이드 (그룹 내부) 표 1번 1행 2열: 010-9876-5432
```

context는 최대 30자, 초과 시 `"..."` 표시 (13주차 docx와 동일).

### 6.1 shapeNo 비노출 정책

`shapeNo`는 `locationLabel`에 노출하지 않는다. PowerPoint에서 사용자가 shape 번호를 찾을 수단이 없기 때문이다. 대신 `location_meta`에 보관해서 향후 프론트엔드에서 직접 클릭 이동 기능을 추가할 때 활용한다.

### 6.2 표 순번 항상 표시 정책

표 셀의 `locationLabel`에는 **항상** `"표 N번"`을 표시한다 (표가 1개여도 1번이 붙는다).

이유:
- 슬라이드에 표가 여러 개 있을 때 사용자가 어떤 표인지 구분할 수 있어야 한다.
- 일관성을 유지하면 사용자가 라벨 형식을 학습하기 쉽다.

`tableIndex`는 슬라이드 내 0-based 카운터로 저장하고, 라벨에는 1-based로 표시한다. 그룹 외부 표와 그룹 내부 표는 같은 카운터를 공유한다.

### 6.3 그룹 내부 표시 정책

그룹 안에 있는 모든 텍스트/표 위치는 `"(그룹 내부)"` 접미어를 붙여 표시한다. 사용자가 PowerPoint에서 해당 위치를 찾을 때 그룹 진입이 필요함을 알리기 위해서다.

`groupShapeNo` 자체는 사용자에게 의미가 없으므로 라벨에 노출하지 않고 `location_meta`에만 보관한다.

---

## 7. shape 순회 정책

### 7.1 처리 대상

```text
- 일반 텍스트 shape:    shape.has_text_frame == True
- 표 shape:             shape.has_table == True
- 그룹 shape:           shape.shape_type == 6 → 한 단계 재귀
- 발표자 노트:           slide.notes_slide.notes_text_frame (슬라이드별)
```

### 7.2 처리 제외

```text
- 그림, 차트, SmartArt, OLE 객체
- 그룹 안의 그룹 (14주차 범위 외)
- 텍스트가 없는 도형 (직선 connector 등)
```

shape이 텍스트도 없고 표도 아니면 자동으로 순회 대상에서 제외된다. 별도 warning은 발생시키지 않는다 (정상 동작).

### 7.3 그룹 shape 재귀 및 위치 키 충돌 방지

```python
# 그룹 shape 발견 → 내부 shape 순회
for child_index, child in enumerate(group_shape.shapes):
    if hasattr(child, "shapes"):
        continue  # 그룹 안의 그룹은 무시 (14주차 범위 외)
    if child.has_table:
        # 표 셀 순회 (section="group_table_cell")
    elif child.has_text_frame:
        # 텍스트 frame 순회 (section="group_shape_text")
```

회사 ppt에서 그룹 안에 텍스트 shape이나 표 shape이 들어가는 경우가 흔하므로, 그룹 안의 텍스트와 표를 모두 정상 탐지한다.

**위치 키 충돌 방지 (중요):**

그룹 내부 child shape에는 child_index를 `shapeNo`로 부여하고, 부모 group의 shape 번호는 `groupShapeNo`에 별도 저장한다. 이 설계가 없으면 같은 그룹 안의 텍스트박스 2개가 모두 paragraphNo=0이고 같은 group shape에 속하므로 위치 key가 충돌하여 `_index_pptx_paragraphs()`의 dict에서 한 건이 덮어써질 수 있다.

```text
# 잘못된 설계 (충돌 발생)
그룹 안 텍스트박스 A: (slideNo, "shape_text", groupShapeNo, paragraphNo=0)
그룹 안 텍스트박스 B: (slideNo, "shape_text", groupShapeNo, paragraphNo=0)
→ 같은 key, 덮어쓰기 발생

# 현재 설계 (분리)
그룹 안 텍스트박스 A: (slideNo, "group_shape_text", groupShapeNo, childShapeNo=0, paragraphNo=0)
그룹 안 텍스트박스 B: (slideNo, "group_shape_text", groupShapeNo, childShapeNo=1, paragraphNo=0)
→ 서로 다른 key
```

TC22에서 이 분리를 검증한다.

---

## 8. 코드화된 warning type

13주차 type에 pptx 전용을 추가했다.

| type 코드 | 의미 |
|---|---|
| `context_mismatch` | (공통) target.context와 현재 텍스트가 다름 |
| `slice_mismatch` | (공통) text[start:end]가 matched와 다름 |
| `unicode_normalization_mismatch` | (공통) NFC 정규화 후에만 일치 |
| `empty_paragraph_target` | (공통) 빈 paragraph를 가리키는 target |
| `missing_paragraph_no` | (공통) paragraphNo 또는 필수 위치 필드 누락 |
| `missing_slide_no` | (pptx) slideNo가 없음 |
| `slide_out_of_range` | (pptx) pptx 위치를 찾을 수 없음 (통칭) |
| `shape_not_found` | (pptx) shape이 현재 pptx에 없음 (향후 확장용, 14주차 미사용) |
| `unknown_section` | (pptx) 알 수 없는 section 값 |

저장 형식은 문자열 접두어 방식이다 (13주차와 동일).

```text
[slide_out_of_range] 99번 슬라이드: 위치가 현재 pptx에서 발견되지 않습니다.
[unknown_section] 알 수 없는 위치: section='smart_art'이므로 안내를 생성하지 않습니다.
```

### 8.1 `slide_out_of_range`의 통칭 사용 (14주차 PoC)

`slide_out_of_range`는 본래 슬라이드 범위 초과를 의미하지만, 14주차 PoC에서는 다음을 모두 포함하는 통칭으로 사용한다.

```text
- slideNo 자체가 없거나 범위 초과
- 슬라이드는 있는데 shapeNo 위치를 찾을 수 없음
- shape은 있는데 cell/paragraph 위치를 찾을 수 없음
```

이는 `_index_pptx_paragraphs()`에서 paragraph 위치를 dict key로 일괄 인덱싱한 뒤, 매칭 실패 시 어느 단계에서 실패했는지 별도 검증 없이 한 가지 warning으로 처리하기 때문이다.

15주차 이후 hwpx 추가 시점에 공통 warning을 정리할 때 단계별 분리를 검토한다 (`shape_not_found`, `pptx_location_not_found` 등).

### 8.2 `missing_paragraph_no`의 광의 사용 (향후 분리 예정)

`_group_targets_by_location()`에서 `shapeNo` / `rowNo` / `colNo` / `groupShapeNo` 등 보조 위치 필드가 누락된 경우에도 `missing_paragraph_no` warning으로 처리한다. 이는 의미상 정확하지 않으나 14주차 PoC에서는 단순화를 위해 광의로 사용한다.

15주차 이후 공통 warning을 정리할 때 다음과 같이 분리할 예정이다.

```text
- paragraphNo 누락                              → missing_paragraph_no
- shapeNo / rowNo / colNo / groupShapeNo 누락   → missing_pptx_location (신규)
```

---

## 9. 핵심 함수

### 9.1 detect_in_pptx()

```python
def detect_in_pptx(
    input_path: str,
    *,
    regex_detect_func: Callable | None = None,
    ner_detect_func: Callable | None = None,
    ai_predict_func: Callable | None = None,
    ner_threshold: float = 0.8,
    ai_threshold: float = 0.6,
) -> DeidentifyPlan
```

13주차 `detect_in_docx()`와 동일한 시그니처. 탐지 함수를 주입형으로 받아 단위 테스트에서 모델 의존성을 끊는다.

### 9.2 build_guide_for_pptx()

```python
def build_guide_for_pptx(
    input_path: str,
    plan: DeidentifyPlan,
    *,
    deletion_mode: str = "delete",
) -> CommonApplyResult
```

- 실제 파일을 수정하지 않는다.
- `applyMode="guide"`, `outputFilePath=None`을 설정한다.

### 9.3 detect_and_build_guide_for_pptx()

위 두 함수를 묶은 편의 wrapper.

### 9.4 보조 함수

```text
load_pptx()
iter_pptx_paragraphs()
_iter_shape_text_paragraphs()
_iter_table_cell_paragraphs()
_iter_notes_paragraphs()
_iter_shape_recursive()    (그룹 shape 재귀)
_is_group_shape()
_make_pptx_location_key()  (slideNo+section+shapeNo+paragraphNo 기준 key)
_index_pptx_paragraphs()
_group_targets_by_location()
_build_guide_item_for_location()
```

---

## 10. 단위 테스트 결과 (TC1~TC23)

`notebooks/17_test_pptx_detector.py`에서 23개 테스트 케이스를 검증했다. **67/67 모두 통과**했다.

| ID | 시나리오 | 결과 |
|---|---|---|
| TC1 | 이메일 shape 마스킹 | PASS |
| TC2 | 성명 shape 마스킹 | PASS |
| TC3 | 성명 + 이메일 동시 | PASS |
| TC4 | 내부 IP 삭제 (delete/mark) | PASS |
| TC5 | reviewTargets 보존 | PASS |
| TC6 | paragraphNo 없음 → missing_paragraph_no | PASS |
| TC7 | 슬라이드 범위 초과 → slide_out_of_range | PASS |
| TC8 | context 불일치, slice 일치 → 권장 + warning | PASS |
| TC9 | slice 불일치 → skip + warning | PASS |
| TC10 | 여러 슬라이드/shape 분산 | PASS |
| TC11 | summary 정합성 | PASS |
| TC12 | deletion_mode=mark | PASS |
| TC13 | 빈 paragraph 제외, paragraphNo 원문 유지 | PASS |
| TC14 | locationLabel 형식 (3가지 section, 항상 "표 N번" 표시) | PASS |
| TC15 | applyMode="guide", outputFilePath=None | PASS |
| TC16 | 한 슬라이드의 여러 shape에 target 분산 | PASS |
| TC17 | 빈 text_frame(strip 기준) 제외 | PASS |
| TC18 | 표 shape 내부 셀 paragraph 탐지 | PASS |
| TC19 | 그룹 shape 내부 텍스트 탐지 (재귀 순회) | PASS |
| TC20 | 발표자 노트 탐지 | PASS |
| TC21 | 비텍스트 shape(connector 등) 제외 | PASS |
| **TC22** | **그룹 내부 위치 분리 (key 충돌 방지)** | **PASS** |
| **TC23** | **같은 슬라이드 내 표 2개 → tableIndex 구분** | **PASS** |

### 10.1 TC19 그룹 shape 검증 방법

python-pptx는 그룹 shape 생성 API를 직접 제공하지 않는다. 따라서 TC19에서는 lxml을 사용한 XML 조작으로 `p:grpSp` 요소를 만들어 그룹 shape을 생성했다.

```python
# 두 텍스트박스를 그룹으로 묶기
grpSp = spTree.makeelement(qn("p:grpSp"), {})
# nvGrpSpPr, grpSpPr 추가
grpSp.append(sp1)  # 첫 번째 텍스트박스
grpSp.append(sp2)  # 두 번째 텍스트박스
spTree.append(grpSp)
```

이렇게 만든 그룹 shape에 대해 `iter_pptx_paragraphs()`가 두 텍스트박스를 모두 정상 탐지하는 것을 확인했다.

### 10.2 TC22 그룹 내부 위치 분리 검증

같은 그룹 안에 텍스트박스 2개를 만들고, 각각 `paragraphNo=0`인 상태를 검증한다.

```text
그룹 내부 텍스트박스 1: section="group_shape_text", groupShapeNo=4, shapeNo=0, paragraphNo=0
그룹 내부 텍스트박스 2: section="group_shape_text", groupShapeNo=4, shapeNo=1, paragraphNo=0
```

`shapeNo`가 다르므로 location key가 충돌하지 않고, `_index_pptx_paragraphs()` dict에서도 두 건이 모두 보존된다. `build_guide_for_pptx()`까지 거쳐도 두 항목이 각각 분리되어 출력된다.

### 10.3 TC23 슬라이드 내 표 2개 검증

같은 슬라이드에 표 2개를 만들고, 각각 `tableIndex=0`, `tableIndex=1`이 부여되는지 확인한다. `locationLabel`에는 각각 `"표 1번"`, `"표 2번"`이 표시된다.

---

## 11. 실제 pptx 통합 테스트 결과

`notebooks/18_test_real_pptx_detection.py`에서 실제 회사 보안 가이드라인 pptx로 검증했다.

```text
input_path: data/test.pptx
slide_count: 20
paragraph_count: 357
section별: {shape_text: 300, table_cell: 57}
```

검증 결과:

```text
fileType: pptx
applyMode: guide
outputFilePath: None

summary:
  totalLocations: 1
  appliedLocations: 1
  partialLocations: 0
  skippedLocations: 0
  totalWarnings: 0
  autoTargetCount: 1
  reviewTargetCount: 1   (--force-mock-review 사용)

autoResults:
  - 19번 슬라이드: 스위치 VLAN 201에
    label=VLAN/포트 정보 / action=삭제 / status=applied
    original: 스위치 VLAN 201에
    권장   : 스위치 (삭제됨)에
```

확인 사항:

```text
1. 20개 슬라이드, 357개 paragraph 전체 순회 정상
2. 표 셀 57개 포함 (table_cell 정상 처리)
3. VLAN 패턴 정상 탐지 + (삭제됨) mark 표시 정상
4. --force-mock-review로 reviewTargets 흐름 실증 완료
5. context_mismatch, slice_mismatch 등 warning 0건
6. 원본 파일은 변경되지 않고 outputFilePath=None
```

### 11.1 탐지 결과가 적은 이유

이 pptx는 회사 데이터 보안 가이드라인 문서로, 보안 사례 외에 직접적인 개인정보/민감정보가 들어 있지 않다. 정규식이 잡을 수 있는 패턴이 거의 없는 문서 자체의 특성이다.

NER 모델을 연결하면 본문에 등장하는 성명을 추가로 탐지할 수 있다. AI 모델을 연결하면 문맥 기반 민감정보를 review target으로 받을 수 있다. 14주차 시점에서는 모델 연결 없이 파이프라인 동작 검증을 우선했다.

### 11.2 --force-mock-review 검증

13주차에서 추가한 mock review 흐름이 pptx에서도 정상 동작했다.

```text
DeidentifyPlan.review_targets (mock 1건)
→ make_review_items()
→ CommonReviewItem
→ CommonApplyResult.reviewTargets
```

---

## 12. 사용자 시나리오

14주차 결과물의 사용자 시나리오는 docx와 동일한 구조를 가진다.

```text
1. 사용자가 pptx 파일을 업로드한다.
2. 시스템이 슬라이드의 본문 shape / 표 셀 / 발표자 노트를 순회하며 탐지한다.
3. 시스템이 guide 모드 CommonApplyResult를 반환한다.
4. 프론트엔드가 위치별로 안내 목록을 표시한다.
   - 위치: "19번 슬라이드: 스위치 VLAN 201에"
   - 항목: "VLAN/포트 정보"
   - 조치: "삭제"
   - 원문: "스위치 VLAN 201에"
   - 권장 결과: "스위치 (삭제됨)에"
5. 사용자가 원본 pptx에서 직접 해당 위치를 찾아 수정한다.
   - locationLabel의 context 일부를 PowerPoint 검색(Ctrl+F)으로 활용
6. 수정 완료 후 pptx를 사용한다.
```

---

## 13. 14주차 완료 범위

```text
1. pptx_detector.py 구현
2. 5가지 paragraph 순회 (shape_text / table_cell / notes / group_shape_text / group_table_cell)
3. detect_in_pptx() — regex/NER/AI 어댑터 (주입형)
4. build_guide_for_pptx() — applyMode="guide" CommonApplyResult 생성
5. detect_and_build_guide_for_pptx() — 편의 wrapper
6. locationLabel 5가지 형식 (shape_text / table_cell / notes / group_shape_text / group_table_cell)
7. location_meta section 분리 + paragraphNo 의미 명시
8. groupShapeNo + child shapeNo 분리로 그룹 내부 위치 키 충돌 방지
9. tableIndex로 슬라이드 내 표 순번 부여 (그룹 외부/내부 표가 같은 카운터 공유)
10. 1-based 표시 / 0-based 저장 규칙
11. 표 셀 locationLabel에 "표 N번" 항상 표시
12. pptx 전용 warning type 4개 추가
13. TC1~TC23 단위 테스트 (67/67 통과)
14. 실제 test.pptx 통합 테스트
15. --force-mock-review 옵션으로 reviewTargets 실증
```

---

## 14. 14주차 범위 밖 작업

```text
1. pptx 파일 자동 수정/저장 (B안 결정에 따라 영구 미수행)
2. SmartArt 내부 텍스트 탐지
3. 차트 내부 텍스트 탐지
4. 그림 캡션, OLE 객체 텍스트 탐지
5. 그룹 안의 그룹 처리 (한 단계만 재귀)
6. 도형 좌표 기반 정밀 표시
7. 슬라이드 마스터/레이아웃 텍스트 탐지
8. 추적 변경, 주석 처리
9. hwpx detector (15주차)
10. 프론트엔드 guide 모드 UI 실제 연결
```

2~7번은 향후 detector 확장 단계에서 검토한다.

---

## 15. 다음 단계

```text
15주차: hwpx detector + guide PoC
```

hwpx는 docx/pptx와 달리 python 표준 라이브러리만으로 XML을 직접 파싱해야 한다. 그러나 다음은 그대로 재사용 가능하다.

```text
- common_apply_result.py (applyMode, CommonApplyItem 등)
- common_apply_utils.py (slice 검증, locationLabel 생성 등)
- deidentify_apply.py (apply_targets_to_text)
- deidentify_target_builder.py (DeidentifyPlan 생성)
- regex_detector.py (정규식)
```

15주차에는 hwpx XML 구조 분석과 paragraph 식별 로직만 새로 작성하면 된다.

---

## 16. 결론

14주차는 pptx 비식별화에 대해 docx와 동일한 탐지 + 안내 방식을 채택해 다음을 달성했다.

```text
1. 서식 100% 보존 (사용자가 직접 수정하므로 시스템이 깨뜨릴 일 없음)
2. 핵심 가치 유지 (위치 + 조치 안내는 10주차 DeidentifyPlan의 본질)
3. 13주차 공통 인프라(common_apply_utils, applyMode, CommonApplyItem) 재사용
4. 5가지 paragraph 단위 정상 처리 (shape_text / table_cell / notes / group_shape_text / group_table_cell)
5. 그룹 내부 위치 키 충돌 방지 (groupShapeNo + child shapeNo 분리)
6. 슬라이드 내 표 순번(tableIndex)으로 여러 표 구분 가능
7. pptx 특유 케이스 23개 단위 테스트 통과
8. 실제 회사 pptx로 파이프라인 동작 검증 완료
```

xlsx 자동 Apply, docx 안내, pptx 안내 모두 `CommonApplyResult.applyMode`로 구분되어, 프론트엔드는 동일한 구조로 세 가지 흐름을 처리할 수 있다.

15주차 hwpx detector는 14주차와 동일한 패턴을 따르며, XML 파싱 부분만 새로 작성하면 된다.
