# 15주차 hwpx 탐지 + 안내(guide) 모드 구현 결과

## 1. 목적

15주차의 목적은 hwpx 파일에서 개인정보/민감정보를 탐지하고, 사용자에게 위치와 조치 방법을 안내하는 것이었다.

13주차 docx, 14주차 pptx와 동일한 탐지 + 안내 방식을 hwpx에도 적용한다.

```text
hwpx 파일 → paragraph 순회 → regex/NER/AI 탐지 → DeidentifyPlan
         → build_guide_for_hwpx() → CommonApplyResult (applyMode="guide")
```

xlsx만 자동 Apply 유지, docx/pptx/hwpx는 guide 모드로 통일된다.

---

## 2. docx/pptx와의 공통점

13~14주차에서 정립한 구조를 그대로 재사용한다.

```text
1. CommonApplyResult.applyMode = "guide"
2. outputFilePath = None
3. 11주차 apply_targets_to_text()로 권장 결과(appliedText) preview 생성
4. validate_slice_against_text()로 slice 검증
5. context 불일치 시 warning, slice 불일치 시 skip
6. 코드화된 warning type 접두어
7. deletion_mode delete/mark 정책 동일
8. reviewTargets 자동 적용 없이 별도 보존
9. 빈 paragraph(strip 기준) 탐지 대상 제외, paragraphNo 원문 인덱스 유지
10. 탐지 함수 주입형 (regex/NER/AI 어댑터)
```

`src/common_apply_utils.py`의 공통 함수는 그대로 사용한다.

---

## 3. docx/pptx와의 차이점

hwpx는 다음 점에서 다르다.

### 3.1 외부 라이브러리 없음

docx는 python-docx, pptx는 python-pptx를 사용하지만 hwpx는 표준 한국어 라이브러리가 부족하다. 자체 구현 + kordoc은 막힐 때 참고하는 방식으로 결정했다.

python 표준 라이브러리(zipfile, xml.etree.ElementTree)만 사용한다.

### 3.2 ZIP 컨테이너 + 여러 section XML

```text
hwpx (ZIP 아카이브)
├── mimetype                    (application/hwp+zip)
├── Contents/section0.xml       (본문 1)
├── Contents/section1.xml       (본문 2, 선택)
├── ...
└── ...
```

여러 section을 가질 수 있으나, 분석한 두 hwpx는 모두 `section0.xml` 1개만 가졌다. 코드는 다중 section을 지원한다.

### 3.3 표가 paragraph 안에 인라인 포함

docx와 pptx는 표를 paragraph와 동등한 별도 요소로 다룬다. hwpx는 다르다.

```xml
<hp:p>                    <!-- paragraph -->
  <hp:run>
    <hp:t>본문 텍스트</hp:t>
    <hp:tbl>...</hp:tbl>  <!-- 표가 paragraph 안에 들어감 -->
  </hp:run>
</hp:p>
```

이 구조 때문에 한 paragraph 안에 표가 여러 개 들어갈 수 있다. 실제 분석한 hwpx에서 paragraph[72]에 표 5개가 들어 있는 케이스를 발견했다.

### 3.4 본문 paragraph 텍스트와 표 셀 텍스트 분리

paragraph 안의 모든 `hp:t` 노드를 단순 추출하면 표 안의 셀 텍스트까지 본문에 섞인다. 본문 텍스트는 `p > hp:run > hp:t` 경로만(직속 자식만) 추출해야 표 안 텍스트가 누출되지 않는다.

```python
def get_paragraph_own_text(p: ET.Element) -> str:
    texts = []
    for run in p.findall(f"{HP}run"):
        for child in run:
            if child.tag == f"{HP}t" and child.text:
                texts.append(child.text)
    return "".join(texts)
```

### 3.5 표 셀 위치 식별 — A안 + 앞 paragraph context

같은 paragraph 안에 표가 5개 있는 케이스에서, 사용자가 한글에서 표를 정확히 찾기 위해 두 가지 정보를 결합한다.

```text
1. paragraphNo: 표가 들어있는 본문 paragraph 인덱스
2. tableIndex:  해당 paragraph 내 표 순번 (0-based)
3. preceding_text: 표가 들어있는 paragraph 직전의 본문 paragraph 텍스트
```

회사 보고서는 보통 표 제목이 표 직전 본문 paragraph에 들어가는 패턴이다 (예: `"❍ 추진단계(안)"` 다음 줄에 5단계 표). preceding_text를 locationLabel에 함께 표시해 사용자가 시각적으로 위치를 찾기 쉽게 한다.

---

## 4. 구현 산출물

```text
src/hwpx_detector.py                       (신규)
src/common_apply_utils.py                  (hwpx 전용 warning type 2개 추가)
notebooks/19_test_hwpx_detector.py         (TC1~TC22 단위 테스트)
notebooks/20_test_real_hwpx_detection.py   (실제 hwpx 통합 테스트)
reports/week15_hwpx_detection_guide.md     (본 문서)
```

기존 파일 변경:

```text
src/common_apply_utils.py: hwpx 전용 warning type 2개 추가
  - WARNING_MISSING_SECTION_NO
  - WARNING_SECTION_OUT_OF_RANGE
```

13~14주차 공통 인프라(`common_apply_result.py`, `deidentify_apply.py`, `deidentify_target_builder.py`, `regex_detector.py`)는 변경 없이 그대로 재사용한다.

---

## 5. hwpx 위치 정책

### 5.1 location_meta 구조

section 값에 따라 필드 구성이 다르다.

```python
# body (본문 paragraph)
{
    "fileType": "hwpx",
    "sectionNo": 0,
    "section": "body",
    "paragraphNo": 13,
}

# table_cell (표 셀)
{
    "fileType": "hwpx",
    "sectionNo": 0,
    "section": "table_cell",
    "paragraphNo": 72,         # 표가 들어있는 본문 paragraph 인덱스
    "tableIndex": 2,           # paragraph 내 표 순번 (0-based)
    "rowNo": 1,                # 0-based
    "colNo": 0,                # 0-based
    "cellParagraphNo": 0,      # 셀 내부 paragraph 인덱스
}
```

`tableIndex`는 **paragraph 내** 표 순번이다. pptx는 슬라이드 단위 표 순번이었던 반면, hwpx는 표가 paragraph 안에 인라인으로 들어가므로 paragraph 단위로 부여한다.

### 5.2 paragraphNo 의미 분리

```text
section="body":        hs:sec 직속 hp:p 인덱스 (빈 paragraph 포함 원문 인덱스 유지)
section="table_cell":  표를 포함하는 본문 paragraph 인덱스 (location 식별용)
```

표 셀의 `paragraphNo`는 셀 내부 paragraph 인덱스가 아닌, **표가 들어있는 본문 paragraph** 인덱스다. 셀 내부 paragraph는 별도 필드 `cellParagraphNo`로 저장한다.

### 5.3 1-based / 0-based 표시 규칙

```text
location_meta의 모든 *No 필드: 0-based로 저장
locationLabel: 사용자 표시용이며 1-based로 표시
```

```python
# location_meta
{"sectionNo": 0, "paragraphNo": 72, "tableIndex": 2, "rowNo": 1, "colNo": 0}

# locationLabel
"1번 본문 73번째 문단 표 3번 2행 1열: ..."
```

---

## 6. locationLabel 형식

section별로 형식이 다르다.

| section | 형식 |
|---|---|
| `body` | `"{sectionNo + 1}번 본문 {paragraphNo + 1}번째 문단: context..."` |
| `table_cell` | `"{sectionNo + 1}번 본문 {paragraphNo + 1}번째 문단 표 {tableIndex + 1}번 {rowNo + 1}행 {colNo + 1}열: 셀텍스트 (앞 문단: ...)"` |

예:

```text
1번 본문 14번째 문단: 담당자 김도윤의 이메일은 test@example.c...
1번 본문 73번째 문단 표 3번 2행 1열: 3단계 (앞 문단: ❍ 추진단계(안))
```

### 6.1 표 셀의 앞 paragraph context (A안)

표 셀 텍스트가 짧고(예: `"3단계"`) 같은 paragraph에 표가 여러 개일 수 있으므로, 표가 들어있는 paragraph 직전의 본문 paragraph 텍스트를 보조 정보로 추가한다.

```text
1번 본문 73번째 문단 표 3번 2행 1열: 3단계 (앞 문단: ❍ 추진단계(안))
```

이 정책은 hwpx 특유의 표 표시 패턴(표 제목이 표 직전 본문에 위치)에 잘 맞는다. 사용자가 한글에서 `"❍ 추진단계(안)"`을 검색하면 위치를 빠르게 찾을 수 있다.

`preceding_text`는 hwpx_detector 내부에서만 처리한다. 공통 인프라(common_apply_utils.py)에 별도 함수를 만들지 않고 hwpx_detector 안에 응집시켰다. docx/pptx에서는 효용이 작아 도입하지 않았다.

---

## 7. paragraph 순회 정책

### 7.1 처리 대상

```text
- 본문 paragraph:   hs:sec > hp:p (빈 paragraph strip 기준 제외)
- 표 셀 paragraph:  hp:tbl > hp:tr > hp:tc > hp:subList > hp:p
                    (셀 내부 paragraph도 빈 paragraph는 strip 기준 제외)
- 한 paragraph에 표 여러 개:  tableIndex로 구분 (paragraph 단위 카운터)
- 여러 section:               sectionNo 오름차순으로 순회
```

### 7.2 처리 제외

```text
- header / footer / footnote / endnote / 메모
- 중첩 표 (표 안의 표) - 15주차 PoC 범위 외
- 이미지 캡션, OLE 객체
```

### 7.3 본문/표 텍스트 분리

`get_paragraph_own_text()`는 `p > hp:run > hp:t`만 추출해 표 안 텍스트를 제외한다. 표 셀은 별도로 `_iter_cell_paragraphs_for_table()`로 처리한다.

---

## 8. 코드화된 warning type

13~14주차 type에 hwpx 전용 2개를 추가했다.

| type 코드 | 의미 |
|---|---|
| `context_mismatch` | (공통) target.context와 현재 텍스트가 다름 |
| `slice_mismatch` | (공통) text[start:end]가 matched와 다름 |
| `unicode_normalization_mismatch` | (공통) NFC 정규화 후에만 일치 |
| `empty_paragraph_target` | (공통) 빈 paragraph를 가리키는 target |
| `missing_paragraph_no` | (공통) paragraphNo 또는 필수 위치 필드 누락 |
| `unknown_section` | (공통, pptx에서 도입) 알 수 없는 section 값 |
| `missing_section_no` | (hwpx) sectionNo가 없음 |
| `section_out_of_range` | (hwpx) section/paragraph 위치를 찾을 수 없음 |

저장 형식은 문자열 접두어 방식이다.

```text
[section_out_of_range] 100번 본문 1번째 문단: 위치가 현재 hwpx에서 발견되지 않습니다.
[unknown_section] 알 수 없는 위치: section='footnote'이므로 안내를 생성하지 않습니다.
```

---

## 9. 핵심 함수

### 9.1 detect_in_hwpx()

```python
def detect_in_hwpx(
    input_path: str,
    *,
    regex_detect_func: Callable | None = None,
    ner_detect_func: Callable | None = None,
    ai_predict_func: Callable | None = None,
    ner_threshold: float = 0.8,
    ai_threshold: float = 0.6,
) -> DeidentifyPlan
```

13~14주차 `detect_in_docx()` / `detect_in_pptx()`와 동일한 시그니처.

### 9.2 build_guide_for_hwpx()

```python
def build_guide_for_hwpx(
    input_path: str,
    plan: DeidentifyPlan,
    *,
    deletion_mode: str = "delete",
) -> CommonApplyResult
```

- 실제 파일을 수정하지 않는다.
- `applyMode="guide"`, `outputFilePath=None`을 설정한다.

### 9.3 detect_and_build_guide_for_hwpx()

위 두 함수를 묶은 편의 wrapper.

### 9.4 보조 함수

```text
load_hwpx_sections()          - ZIP에서 section XML 목록 로드
get_paragraph_own_text()      - paragraph 자체 텍스트만 추출 (표 안 텍스트 제외)
find_tables_in_paragraph()    - paragraph 내 hp:tbl 목록
iter_hwpx_paragraphs()        - 모든 paragraph 순회 (본문 + 표 셀)
_iter_section_paragraphs()    - 단일 section 내 순회 + preceding_text 추적
_iter_cell_paragraphs_for_table()  - 단일 표의 셀 paragraph 순회
_make_hwpx_location_key()     - 위치 그룹화 키
_index_hwpx_paragraphs()      - 위치 키 → text 매핑 사전 생성
_group_targets_by_location()  - auto target 위치별 그룹화
_build_guide_item_for_location()  - guide 모드 CommonApplyItem 생성
```

---

## 10. 단위 테스트 결과 (TC1~TC22)

`notebooks/19_test_hwpx_detector.py`에서 22개 테스트 케이스를 검증했다. **61/61 모두 통과**했다.

hwpx 임시 파일은 python 표준 라이브러리만 사용해 헬퍼 함수(`make_hwpx_file`, `make_multi_section_hwpx`)로 직접 생성했다. 외부 라이브러리에 의존하지 않는다.

| ID | 시나리오 | 결과 |
|---|---|---|
| TC1 | 이메일 본문 paragraph 마스킹 | PASS |
| TC2 | 성명 본문 paragraph 마스킹 | PASS |
| TC3 | 성명 + 이메일 동시 | PASS |
| TC4 | 내부 IP 삭제 (delete/mark) | PASS |
| TC5 | reviewTargets 보존 | PASS |
| TC6 | paragraphNo 없음 → missing_paragraph_no | PASS |
| TC7 | section 범위 초과 → section_out_of_range | PASS |
| TC8 | context 불일치, slice 일치 → 권장 + warning | PASS |
| TC9 | slice 불일치 → skip + warning | PASS |
| TC10 | 여러 paragraph 분산 | PASS |
| TC11 | summary 정합성 | PASS |
| TC12 | deletion_mode=mark | PASS |
| TC13 | 빈 paragraph 제외, paragraphNo 원문 인덱스 유지 | PASS |
| TC14 | locationLabel 형식 (body, table_cell) | PASS |
| TC15 | applyMode="guide", outputFilePath=None | PASS |
| TC16 | 표 셀 paragraph 탐지 (section/tableIndex/rowNo/colNo) | PASS |
| TC17 | 한 paragraph에 표 여러 개 → tableIndex 구분 | PASS |
| TC18 | 본문 paragraph 텍스트에 표 안 텍스트가 섞이지 않음 | PASS |
| TC19 | 표 셀의 preceding_text가 앞 본문으로 채워짐 | PASS |
| TC20 | 표가 첫 paragraph일 때 preceding_text=None | PASS |
| TC21 | 알 수 없는 section → unknown_section warning | PASS |
| TC22 | 다중 section 처리 (section0 + section1) | PASS |

### 10.1 핵심 hwpx 특유 검증 (TC17~TC22)

**TC17 한 paragraph에 표 여러 개**:

paragraph[1]에 표 3개를 만들고 각각 다른 첫 셀(`"1단계"`, `"2단계"`, `"3단계"`)을 두었다. `tableIndex`로 구분되어 위치 키가 충돌하지 않고 6개 셀 paragraph가 모두 보존됨을 확인했다.

**TC18 본문/표 텍스트 분리**:

```python
paragraph = {"text": "본문 텍스트입니다", "tables": [[["표 안 셀A", "표 안 셀B"]]]}
```

이 paragraph에서 본문 텍스트는 `"본문 텍스트입니다"`만 추출되고, 표 안 텍스트(`"표 안 셀A"`, `"표 안 셀B"`)는 별도로 `table_cell` section paragraph로 잡힌다.

**TC19 preceding_text 채움**:

```text
paragraph[0]: "❍ 추진단계"  ← 직전 본문
paragraph[1]: ""             ← 빈 paragraph (preceding_text 갱신 안 함)
paragraph[2]: 표 포함
```

표 셀의 `preceding_text`는 `"❍ 추진단계"`로 채워진다. 빈 paragraph는 last_non_empty_text를 갱신하지 않으므로 가장 가까운 본문 paragraph가 정확히 사용된다.

**TC20 preceding_text 없음**:

표가 문서의 첫 paragraph일 때 `preceding_text=None`이고 locationLabel에 `"(앞 문단: ...)"`이 표시되지 않는다.

**TC22 다중 section**:

`section0.xml`과 `section1.xml`을 가진 hwpx를 만들어 두 section에서 모두 탐지가 동작함을 확인했다.

---

## 11. 실제 hwpx 통합 테스트 결과

### 11.1 test.hwpx (작은 보고서)

```text
slide_count: 1 section
paragraph_count: 98 (body 19 + table_cell 79)
원본 hwpx: 31개 paragraph, 4개 표
```

- 본문 paragraph 19개 (빈 paragraph 제외, paragraphNo 원문 인덱스 유지)
- 표 셀 paragraph 79개 (4개 표의 셀 합계)
- regex 탐지: 0건 (정규식이 잡을 패턴이 보고서에 없음)
- `--force-mock-review`로 reviewTargets 1건 확인

### 11.2 AI혁신TF단_운영계획_안_.hwpx (큰 운영계획서)

```text
paragraph_count: 343 (body 159 + table_cell 184)
원본 hwpx: 230개 paragraph, 38개 표
```

- 본문 paragraph 159개
- 표 셀 paragraph 184개 (38개 표 합계)
- paragraph[72]의 표 5개가 `tableIndex` 0~4로 모두 정상 구분되어 셀이 보존됨 (1단계~5단계)
- paragraph[18]의 표 2개도 정상 구분
- regex 탐지: 0건 (운영계획서에 정규식 패턴이 없음)

### 11.3 탐지 결과가 적은 이유

두 문서는 회사 내부 보고서/운영계획으로, 직접적인 개인정보/민감정보 패턴(주민등록번호, 전화번호, 이메일, IP 등)이 거의 없다. 이는 문서 자체의 특성이고 detector의 동작에는 문제가 없다.

NER 모델을 연결하면 본문에 등장하는 성명을 추가 탐지할 수 있다 (mock 테스트로 검증). AI 모델을 연결하면 문맥 기반 민감정보를 review target으로 받을 수 있다. 15주차 시점에서는 모델 연결 없이 파이프라인 동작 검증을 우선했다.

---

## 12. 누적 회귀 테스트 결과

| 주차 | 테스트 | 결과 |
|---|---|---|
| 12주차 | xlsx 회귀 | 13/13 |
| 13주차 | TC1~TC18 docx | 52/52 |
| 14주차 | TC1~TC23 pptx | 67/67 |
| 15주차 | TC1~TC22 hwpx | 61/61 |
| **합계** | | **193/193** |

`common_apply_utils.py`에 hwpx 전용 warning type 2개를 추가했지만 기존 type은 변경 없어 docx/pptx/xlsx 회귀가 발생하지 않았다.

---

## 13. 사용자 시나리오

```text
1. 사용자가 hwpx 파일을 업로드한다.
2. 시스템이 본문 paragraph와 표 셀 paragraph를 순회하며 탐지한다.
3. 시스템이 guide 모드 CommonApplyResult를 반환한다.
4. 프론트엔드가 위치별로 안내 목록을 표시한다.
   - 위치: "1번 본문 73번째 문단 표 3번 2행 1열: 3단계 (앞 문단: ❍ 추진단계(안))"
   - 항목: "성명"
   - 조치: "마스킹"
   - 원문: "3단계"
   - 권장 결과: "***"
5. 사용자가 원본 hwpx에서 직접 위치를 찾는다.
   - "❍ 추진단계(안)"을 한글 검색(Ctrl+F)으로 찾고
   - 그 다음 표 5개 중 3번째 표의 2행 1열 셀에서 수정
6. 사용자가 hwpx를 사용한다.
```

---

## 14. 15주차 완료 범위

```text
1. hwpx_detector.py 구현 (python 표준 라이브러리만 사용)
2. ZIP 컨테이너 + 다중 section XML 파싱
3. 본문 paragraph + 표 셀 paragraph 순회
4. 본문/표 텍스트 분리 (p > run > t 직속 자식만 본문)
5. 한 paragraph에 표 여러 개 처리 (tableIndex로 구분)
6. 표 셀 preceding_text로 앞 본문 paragraph context 보강 (A안)
7. detect_in_hwpx() — regex/NER/AI 어댑터 (주입형)
8. build_guide_for_hwpx() — applyMode="guide" CommonApplyResult 생성
9. detect_and_build_guide_for_hwpx() — 편의 wrapper
10. locationLabel 2가지 형식 (body, table_cell)
11. location_meta section 분리 + paragraphNo 의미 명시
12. 1-based 표시 / 0-based 저장 규칙
13. hwpx 전용 warning type 2개 추가
14. TC1~TC22 단위 테스트 (61/61 통과)
15. 실제 test.hwpx + AI혁신TF hwpx 통합 테스트
16. --force-mock-review 옵션으로 reviewTargets 실증
```

---

## 15. 15주차 범위 밖 작업

```text
1. hwpx 파일 자동 수정/저장 (B안 결정에 따라 영구 미수행)
2. header / footer / footnote / endnote / 메모 탐지
3. 중첩 표 (표 안의 표) 처리
4. 이미지 캡션, OLE 객체 텍스트
5. 마스터 페이지, 스타일 관련 텍스트
6. 14주차에서 미룬 warning 분리 (slide_out_of_range, missing_pptx_location 등)
7. 프론트엔드 guide 모드 UI 실제 연결
```

6번 (14주차 후속 warning 정리)은 15주차에서 함께 진행하기로 14주차 보고서에서 언급했으나, 15주차 PoC에서는 기존 호환성을 유지하기 위해 미루었다. 향후 프론트엔드 연결 단계에서 warning UI 표시 정책과 함께 정리하는 것이 자연스럽다.

---

## 16. 결론

15주차는 hwpx 비식별화에 대해 docx/pptx와 동일한 탐지 + 안내 방식을 채택해 다음을 달성했다.

```text
1. 서식 100% 보존 (사용자가 직접 수정하므로 시스템이 깨뜨릴 일 없음)
2. 외부 라이브러리 의존성 없음 (python 표준 라이브러리만 사용)
   - 회사 SSL 환경에서 추가 패키지 설치 부담 없음
3. 13~14주차 공통 인프라(common_apply_utils, applyMode, CommonApplyItem) 재사용
4. hwpx 특유의 본문/표 텍스트 분리 정확 처리
5. 한 paragraph에 표 여러 개도 tableIndex로 구분 (위치 키 충돌 방지)
6. 앞 paragraph context 보강(A안)으로 사용자가 한글에서 위치 찾기 용이
7. TC1~TC22 단위 테스트 67/67 통과 (실제로는 61개 assertion)
8. 실제 두 hwpx 파일로 파이프라인 동작 검증 완료
9. 누적 회귀 테스트 193/193 통과
```

xlsx 자동 Apply, docx 안내, pptx 안내, hwpx 안내 4가지가 모두 `CommonApplyResult.applyMode`로 구분되어, 프론트엔드는 동일한 구조로 처리할 수 있다.

13~15주차의 통합 패턴이 확립되었으므로 향후 다른 파일 형식 추가(예: rtf, odt) 시에도 같은 방식으로 빠르게 확장 가능하다.
