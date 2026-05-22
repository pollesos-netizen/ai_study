# 13주차 docx 탐지 + 안내(guide) 모드 구현 결과

## 1. 목적

13주차의 목적은 docx 파일에서 개인정보/민감정보를 탐지하고, 사용자에게 위치와 조치 방법을 안내하는 것이었다.

12주차까지의 흐름:

```text
xlsx 파일 → DeidentifyPlan → apply_plan_to_xlsx() → 비식별화된 xlsx 저장
```

13주차에서는 docx에 대해 자동 수정이 아닌 안내 방식을 채택했다.

```text
docx 파일 → DeidentifyPlan → build_guide_for_docx() → CommonApplyResult (guide 모드)
→ 사용자가 원본 docx에서 직접 수정
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

특히 숨겨진 손실(필드 깨짐, 하이퍼링크 URL 불일치 등)이 사용자가 즉시 발견하기 어렵다는 점이 가장 큰 위험이다.

회사 환경에서 docx 비식별화 대상은 주로 보고서, 공문, 계약서 등 서식이 중요한 문서이다. 따라서 13주차부터는 다음 정책을 적용했다.

```text
xlsx: 자동 Apply 유지 (셀 단위 구조라 서식 손실 위험 낮음)
docx: 탐지 + 안내(guide) 방식
pptx/hwpx: docx와 동일하게 안내 방식 (14주차 이후)
```

---

## 3. 구현 산출물

```text
src/common_apply_result.py     (CommonApplyItem 주석 강화, applyMode 필드 추가)
src/common_apply_utils.py      (신규 - 공통 유틸 추출)
src/xlsx_deidentify_apply.py   (공통 유틸 사용으로 리팩토링)
src/docx_detector.py           (신규 - docx 본문/표 셀 탐지 + guide 생성)
notebooks/13_test_xlsx_regression.py    (xlsx 회귀 테스트)
notebooks/15_test_docx_detector.py      (TC1~TC18 단위 테스트)
notebooks/16_test_real_docx_detection.py (실제 docx 통합 테스트)
reports/week13_docx_detection_guide.md  (본 문서)
```

---

## 4. CommonApplyResult.applyMode 필드 추가

```python
@dataclass
class CommonApplyResult:
    fileType: str
    inputFilePath: str
    outputFilePath: str | None
    autoResults: list[CommonApplyItem]
    reviewTargets: list[CommonReviewItem]
    warnings: list[str]
    summary: CommonApplySummary
    applyMode: str = "applied"  # "applied" | "guide"
```

값 의미:

| applyMode | 의미 | outputFilePath |
|---|---|---|
| `applied` | 시스템이 실제 파일을 수정해 결과 파일을 생성 (xlsx) | 결과 파일 경로 |
| `guide` | 시스템은 위치/조치만 안내, 사용자가 직접 수정 (docx 등) | None |

`CommonApplyItem`의 필드는 guide 모드에서 의미가 다르므로 주석으로 명시했다.

```python
# applyMode="guide" 모드에서는:
# - appliedText: 실제 적용 결과가 아니라 권장 preview 문자열
# - appliedTargetCount: 권장 가능 target 수
# - skippedTargetCount: 권장 불가 target 수
```

프론트엔드는 applyMode에 따라 표시 문구를 다르게 사용한다.

```text
applied 모드: "적용 결과", "적용된 항목"
guide 모드:   "권장 결과", "권장 항목", "권장 불가"
```

---

## 5. common_apply_utils.py 공통 유틸 추출

12주차 xlsx 모듈에서 docx에서도 재사용 가능한 함수를 분리했다.

```python
# 공통 함수
normalize_nfc(value)
make_output_path(input_path, output_path=None, suffix="_deidentified")
validate_slice_against_text(text, target)
make_status(applied_count, skipped_count)
sort_targets_for_display(targets)
labels_for_targets(targets)
actions_for_targets(targets)
make_location_label_with_context(base_label, context, max_length=30)
```

`validate_slice_against_text()`는 12주차 `validate_slice_against_matched()`를 일반화한 함수다. `cell_value` 전제를 풀어 임의 텍스트를 받을 수 있도록 했다.

또한 함수 시그니처를 `(warning_type, message)` 튜플 반환으로 변경해 코드화된 warning type을 제공한다.

```python
# 변경 전
slice_error: str | None = validate_slice_against_matched(cell_value, target)

# 변경 후
warning_type, slice_error = validate_slice_against_text(text, target)
```

---

## 6. 코드화된 warning type

warning은 사람이 읽는 문자열이지만, 프론트엔드에서 아이콘/필터를 사용할 수 있도록 코드화된 type 접두어를 포함했다.

정의된 warning type:

| type 코드 | 의미 |
|---|---|
| `context_mismatch` | target.context와 현재 텍스트가 다름 |
| `slice_mismatch` | text[start:end]가 matched와 다름 |
| `unicode_normalization_mismatch` | NFC 정규화 후에만 일치 |
| `paragraph_out_of_range` | paragraphNo가 문서 범위를 벗어남 |
| `missing_paragraph_no` | paragraphNo가 없음 |
| `paragraph_not_in_body` | section이 body가 아님 (13주차 범위 외) |
| `empty_paragraph_target` | 빈 paragraph를 가리키는 target |
| `missing_sheet_name` | sheetName이 없음 (xlsx) |
| `missing_cell_ref` | cellRef가 없음 (xlsx) |
| `merged_cell_not_top_left` | 병합 셀의 좌상단이 아님 (xlsx) |
| `formula_cell` | 수식 셀 (xlsx) |
| `non_string_cell` | 비문자열 셀 (xlsx) |
| `empty_cell` | 빈 셀 (xlsx) |
| `sheet_not_found` | 시트를 찾을 수 없음 (xlsx) |

저장 형식은 문자열 접두어 방식이다.

```text
[context_mismatch] 본문 17번째 문단: target.context와 현재 문단 텍스트가 다릅니다.
[slice_mismatch] 본문 17번째 문단: text[12:28]이 matched와 다릅니다.
```

향후 프론트엔드 연결 시 type 코드를 별도 필드로 분리할 수 있다.

---

## 7. docx detector 핵심 함수

### 7.1 detect_in_docx()

```python
def detect_in_docx(
    input_path: str,
    *,
    regex_detect_func: Callable | None = None,
    ner_detect_func: Callable | None = None,
    ai_predict_func: Callable | None = None,
    ner_threshold: float = 0.8,
    ai_threshold: float = 0.6,
) -> DeidentifyPlan
```

탐지 함수를 주입형으로 받는다.

- 단위 테스트에서 모델 의존성을 끊을 수 있다.
- 13주차 초반에는 regex만 연결해서 guide 구조를 우선 검증할 수 있다.
- 기본값에서는 `regex_detector.detect_patterns`를 사용한다.

### 7.2 build_guide_for_docx()

```python
def build_guide_for_docx(
    input_path: str,
    plan: DeidentifyPlan,
    *,
    deletion_mode: str = "delete",
) -> CommonApplyResult
```

- 실제 파일을 수정하지 않는다.
- `applyMode="guide"`, `outputFilePath=None`을 설정한다.
- 11주차 `apply_targets_to_text()`로 메모리에서 preview 문자열을 생성한다.

### 7.3 detect_and_build_guide_for_docx()

위 두 함수를 묶은 편의 wrapper.

---

## 8. paragraph 위치 정책

### 8.1 본문 + 표 셀 paragraph 처리

```text
13주차에서는 docx 본문 paragraph와 표 셀 내부 paragraph를 탐지 대상으로 포함한다.
자동 수정은 하지 않고 guide 모드로만 위치/조치/권장 결과를 안내한다.

헤더/푸터/각주/주석/도형/SmartArt/차트 내부 텍스트는 13주차 범위 외로 유지한다.
```

본문과 표는 location_meta.section으로 구분한다.

```python
# 본문 paragraph
location_meta = {
    "fileType": "docx",
    "section": "body",
    "paragraphNo": para_index,
}

# 표 셀 내부 paragraph
location_meta = {
    "fileType": "docx",
    "section": "table_cell",
    "tableNo": table_index,
    "rowNo": row_index,
    "colNo": col_index,
    "paragraphNo": para_index,
}
```

표 셀 내부 paragraph는 `doc.tables -> rows -> cells -> cell.paragraphs` 순서로 순회한다.
병합 셀 중복 제거를 위해 사용했던 `seen_cells` 로직은 실제 셀 누락을 유발할 수 있어 제거했다.
13주차 guide 모드에서는 중복 안내보다 탐지 누락 방지를 우선한다.

### 8.2 빈 문단 strip 기준 제외

```python
for para_index, paragraph in enumerate(doc.paragraphs):
    text = paragraph.text
    if not text.strip():
        continue
    ...
```

- 공백/탭/줄바꿈만 있는 문단도 탐지 대상에서 제외한다.
- `paragraphNo`는 `doc.paragraphs` 기준 원문 인덱스를 유지한다.

### 8.3 location_meta에 section 필드 추가

`section` 필드는 본문과 표 셀을 구분하는 기준으로 사용한다.

```python
# 본문
{"fileType": "docx", "section": "body", "paragraphNo": 13}

# 표 셀
{"fileType": "docx", "section": "table_cell", "tableNo": 0, "rowNo": 7, "colNo": 1, "paragraphNo": 0}
```
paragraphNo의 의미는 section에 따라 다르다.
- section="body": doc.paragraphs 인덱스
- section="table_cell": 해당 셀의 cell.paragraphs 인덱스

향후 헤더/푸터 확장 시 `section="header"`, `"footer"` 등으로 자연스럽게 확장할 수 있다.

### 8.4 locationLabel에 "본문" 접두어 + context 일부

```python
location_label = f"본문 {para_index + 1}번째 문단: {context_preview}"
```

예:

```text
본문 1번째 문단: 담당자 김도윤의 이메일은 test@example.c...
본문 17번째 문단: 짧은 문단
표 1번 8행 2열: 송영배 대리 휴대전화 번호 : 010-9498...
```

사용자가 Word에서 Ctrl+F로 찾을 수 있도록 context 일부를 포함한다.

---

## 9. context 불일치 정책

xlsx와 동일한 정책을 적용했다.

```text
1. target.context와 paragraph.text가 다르면 warning (context_mismatch)
2. paragraph.text[start:end] == target.matched이면 권장 가능
3. paragraph.text[start:end] != target.matched이면 권장 불가 (slice_mismatch)
4. NFC 정규화 후에만 일치하는 경우도 권장 불가 (unicode_normalization_mismatch)
```

guide 모드에서는 "적용"이 "권장"으로 바뀔 뿐, 검증 로직은 동일하다.

---

## 10. 단위 테스트 결과 (TC1~TC18)

`notebooks/15_test_docx_detector.py`에서 기존 본문 기준 테스트와 표 셀 paragraph 탐지 케이스를 검증했다. 기존 TC1~TC18은 **52/52 모두 통과**했고, 표 셀 내부 개인정보 탐지도 정상 동작을 확인했다.

| ID | 시나리오 | 결과 |
|---|---|---|
| TC1 | 이메일 paragraph 마스킹 | PASS |
| TC2 | 성명 paragraph 마스킹 | PASS |
| TC3 | 성명 + 이메일 동시 | PASS |
| TC4 | 내부 IP 삭제 (delete/mark) | PASS |
| TC5 | reviewTargets 보존 | PASS |
| TC6 | paragraphNo 없음 → missing_paragraph_no | PASS |
| TC7 | paragraphNo 범위 초과 → paragraph_out_of_range | PASS |
| TC8 | context 불일치, slice 일치 → 권장 + warning | PASS |
| TC9 | slice 불일치 → skip + warning | PASS |
| TC10 | 여러 paragraph 분산 | PASS |
| TC11 | summary 정합성 | PASS |
| TC12 | deletion_mode=mark | PASS |
| TC13 | 빈 paragraph 제외, paragraphNo 원문 인덱스 유지 | PASS |
| TC14 | locationLabel 형식 ("본문 N번째 문단: ...") | PASS |
| TC15 | applyMode="guide", outputFilePath=None | PASS |
| TC16 | 공백/탭만 있는 paragraph 제외 | PASS |
| TC17 | 지원하지 않는 section target → skip + unsupported_docx_section warning | PASS
| TC18 | 같은 paragraph target 겹침 | PASS |
| TC19 | 표 셀 내부 개인정보 탐지 | PASS |
| TC20 | 본문 + 표 셀 개인정보 동시 탐지 | PASS

### 10.1 TC18 target 겹침 결과

같은 paragraph에 regex와 NER이 동일한 구간 `김도윤 (start=4, end=7)`을 탐지한 경우:

```text
입력: regex 1건 + ner 1건 (같은 위치)
DeidentifyPlan 단계에서 source 우선순위(regex>ner)로 1건 제거
build_guide_for_docx() 입력: regex 1건만
결과: applied 1건, count=1
```

겹침은 10주차 `build_deidentify_plan()` 단계에서 정상 제거되었다.

---

## 11. xlsx 회귀 테스트 결과

`notebooks/13_test_xlsx_regression.py`에서 13개 검증을 모두 통과했다.

```text
- applyMode="applied" 정상
- outputFilePath 생성 정상
- cell.data_type="s" 명시 정상
- 빈 셀(None/"") 처리 정상 → empty_cell warning
- 비문자열 셀 → non_string_cell warning
- sheetName 누락 → missing_sheet_name warning
```

리팩토링 후에도 기존 xlsx Apply 동작에 회귀가 없음을 확인했다.

---

## 12. 실제 docx 통합 테스트 결과

`notebooks/16_test_real_docx_detection.py`에서 다음 흐름을 검증했다.

```text
실제 docx 파일
→ 본문 paragraph + 표 셀 paragraph 순회 (빈 문단 strip 기준 제외)
→ regex_detector.py로 정규식 탐지
→ NER 모델 (옵션)
→ AI 모델 (옵션)
→ DeidentifyPlan 생성
→ build_guide_for_docx()
→ CommonApplyResult (applyMode="guide")
```

샘플 docx 검증 결과:

```text
입력:
- 9개 paragraph (빈 문단 2개 포함)
- 사번 cd123456
- 이메일 test@example.com
- IP 192.168.0.1, VLAN 100
- 전화번호 010-1234-5678

summary:
  totalLocations: 4
  appliedLocations: 4
  partialLocations: 0
  skippedLocations: 0
  totalWarnings: 0
  autoTargetCount: 5
  reviewTargetCount: 1 (force-mock-review)

권장 결과:
  본문 3번째 문단: 담당자: 김도윤 (cd123456)
    → 담당자: 김도윤 (********)
  본문 4번째 문단: 이메일은 test@example.com 입니다.
    → 이메일은 **************** 입니다.
  본문 6번째 문단: 서버 IP는 192.168.0.1, VLAN 100을 사용합니다.
    → 서버 IP는 (삭제됨), (삭제됨)을 사용합니다.
  본문 7번째 문단: 연락처: 010-1234-5678
    → 연락처: *************
```

확인 사항:

```text
1. 빈 문단(2번, 5번)이 정상 제외되고 paragraphNo는 원문 인덱스 유지
2. 표 셀 내부 paragraph의 개인정보도 section="table_cell"로 정상 탐지
3. 같은 paragraph에 IP + VLAN 두 target이 있어도 정상 처리
4. deletion_mode=mark로 "(삭제됨)" 표시 동작
5. force-mock-review로 reviewTargets 흐름 실증 완료
6. 원본 파일은 변경되지 않고 outputFilePath=None
```


### 12.2 표 셀 내부 paragraph 탐지 확인

테스트용 `data/test.docx`에서 본문 개인정보와 표 내부 개인정보를 함께 배치해 검증했다.

```text
본문: 개인정보 테스트 : 송영배 대리 휴대전화 번호 010-9498-5940
표 내부: 송영배 대리 휴대전화 번호 : 010-9498-5940
```

초기 구현에서는 병합 셀 중복 제거를 위해 `seen_cells`를 사용했으나, 복잡한 표 구조에서 실제 셀 paragraph가 누락되는 문제가 확인되었다.
이에 따라 `iter_table_cell_paragraphs()`에서 `seen_cells` 로직을 제거했다.

최종 확인 결과 `iter_docx_paragraphs()`에서 본문과 표 셀의 개인정보가 모두 표시되었고, `16_test_real_docx_detection.py` 실행 결과에서도 표 내부 개인정보가 정상 탐지되었다.

13주차 정책은 다음과 같이 정리한다.

```text
- 표 셀 paragraph는 모두 순회한다.
- 빈 paragraph(strip 기준)만 제외한다.
- 병합 셀 중복 제거는 13주차에서 수행하지 않는다.
- guide 모드에서는 중복보다 탐지 누락 방지를 우선한다.
```

### 12.1 reviewTargets 실증 (--force-mock-review)

12주차에서 남긴 과제(reviewTargets가 비어 있지 않은 케이스 실증)를 13주차에 통합 테스트로 검증했다.

`--force-mock-review` 옵션은 AI 모델 상태와 무관하게 첫 본문 paragraph에 mock review target을 주입한다.

```bash
python notebooks/16_test_real_docx_detection.py "data/sample.docx" --force-mock-review
```

이 옵션으로 다음 흐름이 정상 동작함을 확인했다.

```text
DeidentifyPlan.review_targets
→ make_review_items()
→ CommonReviewItem
→ CommonApplyResult.reviewTargets (1건)
```

---

## 13. 사용자 시나리오

13주차 결과물의 사용자 시나리오:

```text
1. 사용자가 docx 파일을 업로드한다.
2. 시스템이 본문 paragraph를 순회하며 탐지를 수행한다.
3. 시스템이 결과를 guide 모드 CommonApplyResult로 반환한다.
4. 프론트엔드가 위치별로 안내 목록을 표시한다.
   - 위치: "본문 17번째 문단: 담당자 김도윤의 이메일은..."
   - 항목: "성명, 이메일 주소"
   - 조치: "마스킹"
   - 원문: "담당자 김도윤의 이메일은 test@example.com입니다."
   - 권장 결과: "담당자 ***의 이메일은 ****************입니다."
5. 사용자가 원본 docx에서 직접 해당 위치를 찾아 수정한다.
   - locationLabel의 context 일부를 검색 키워드로 사용
6. 사용자가 수정 완료 후 docx 파일을 사용한다.
```

---

## 14. 12주차 보고서 보완

B안 전환 결정을 12주차 보고서에도 명시해야 한다.

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

## 15. 13주차 완료 범위

```text
1. CommonApplyResult.applyMode 필드 추가
2. CommonApplyItem 필드 의미 혼동 방지 주석
3. common_apply_utils.py 공통 유틸 추출
4. xlsx_deidentify_apply.py 리팩토링 (공통 유틸 사용, 빈 셀 통합 처리, data_type="s")
5. 코드화된 warning type 도입
6. docx_detector.py 구현 (본문/표 셀 paragraph 순회, regex/NER/AI 어댑터)
7. build_guide_for_docx() 구현
8. locationLabel "본문 N번째 문단: context" 형식
9. location_meta에 section 필드 추가
10. 빈 paragraph strip() 기준 제외
11. TC1~TC18 단위 테스트 (52/52 통과)
12. xlsx 회귀 테스트 (13/13 통과)
13. 실제 docx 통합 테스트
14. --force-mock-review로 reviewTargets 실증
```

---

## 16. 13주차 범위 밖 작업

```text
1. docx 파일 자동 수정/저장 (B안 결정에 따라 영구 미수행)
2. 표 내부 paragraph 자동 수정
3. header/footer paragraph 탐지
4. comment/footnote paragraph 탐지
5. 하이퍼링크 URL 처리
6. 필드 코드 처리
7. SmartArt, 차트, 도형 안의 텍스트 처리
8. matched 주변 context 기반 locationLabel 강화
9. pptx/hwpx detector
10. 프론트엔드 guide 모드 UI 실제 연결
```

2~7번은 향후 detector 확장 또는 자동 수정 검토 단계에서 추가한다.
8번은 사용자 검색 편의성 개선 단계에서 검토한다.

---

## 17. 다음 단계

```text
14주차: pptx detector + guide PoC
15주차: hwpx detector + guide PoC
후속 개선: 표 병합 셀 중복 안내가 실제로 문제 되는 경우, 탐지 누락 없이 중복만 줄이는 후처리 방식 검토
```

각 파일 형식별 detector는 docx와 동일한 패턴을 따른다.

```python
detect_in_pptx() -> DeidentifyPlan
build_guide_for_pptx() -> CommonApplyResult (applyMode="guide")

detect_in_hwpx() -> DeidentifyPlan
build_guide_for_hwpx() -> CommonApplyResult (applyMode="guide")
```

이미 추출된 `common_apply_utils.py`를 그대로 재사용할 수 있어 14주차 이후 구현 부담이 작다.

---

## 18. 결론

13주차는 docx 비식별화에 대해 자동 수정이 아닌 탐지 + 안내 방식을 채택해 다음을 달성했다.

```text
1. 서식 100% 보존 (사용자가 직접 수정하므로 시스템이 깨뜨릴 일 없음)
2. 핵심 가치 유지 (위치 + 조치 안내는 10주차 DeidentifyPlan의 본질)
3. 구현 복잡도 감소 (run 단위 보존 및 XML 조작 불필요)
4. 회사 문서 형식에 강건 (docx/pptx/hwpx 모두 동일 패턴 적용 가능)
```

공통 유틸 추출과 applyMode 필드 도입으로 14주차 이후 pptx/hwpx 확장 시 코드 재사용성이 높아졌다.

xlsx 자동 Apply와 docx 안내 모드는 `CommonApplyResult.applyMode`로 구분되어, 프론트엔드는 동일한 구조로 두 흐름을 처리할 수 있다.
