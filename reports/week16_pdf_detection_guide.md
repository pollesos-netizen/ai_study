# 16주차 PDF 탐지 + 안내(guide) 모드 구현 결과

## 1. 목적

16주차의 목적은 PDF 파일에서 개인정보/민감정보를 탐지하고, 사용자에게 위치와 조치 방법을 안내하는 것이었다.

13~15주차 docx/pptx/hwpx와 동일한 탐지 + 안내 방식을 PDF에도 적용한다.

```text
PDF 파일 → page/line 단위 텍스트 추출 → regex/NER/AI 탐지 → DeidentifyPlan
        → build_guide_for_pdf() → CommonApplyResult (applyMode="guide")
```

xlsx만 자동 Apply 유지, docx/pptx/hwpx/pdf는 guide 모드로 통일된다.

---

## 2. 라이브러리 선택 — pdfplumber

### 2.1 후보 비교

| 라이브러리 | 라이선스 | block/bbox 지원 | 평가 |
|---|---|---|---|
| **pdfplumber** | **MIT** | ✓ (line + bbox) | **채택** |
| PyMuPDF | AGPL | ✓ | 회사 배포 시 라이선스 부담 |
| pypdfium2 | Apache 2.0/BSD | △ (line까지) | kordoc과 동일 엔진, 설치 복잡 |
| pypdf | BSD | ✗ | block/bbox 미지원으로 부적합 |

### 2.2 채택 사유

```text
1. 라이선스 부담 없음: MIT, 사내/외부 배포 자유
2. block/bbox 지원: line 단위 추출 + 좌표 정보
3. 회사 환경 설치 가능: pip install pdfplumber
4. 13~15주차 단일 언어 일관성 유지: Python만 사용
5. kordoc Node.js 연동 불필요: 단순한 아키텍처
```

PyMuPDF는 기능이 가장 좋지만 AGPL 라이선스가 사내 도구를 넘어 외부 배포(협력사/그룹사) 시점에 부담이 된다. kordoc은 텍스트 추출 모듈이 별도로 있지만 Node.js 도입이 단일 detector 한 가지를 위해 빌드/배포 복잡도를 늘리므로 채택하지 않았다.

---

## 3. docx/pptx/hwpx와의 공통점

13~15주차에서 정립한 구조를 그대로 재사용한다.

```text
1. CommonApplyResult.applyMode = "guide"
2. outputFilePath = None
3. apply_targets_to_text()로 권장 결과(appliedText) preview 생성
4. validate_slice_against_text()로 slice 검증
5. context 불일치 시 warning, slice 불일치 시 skip
6. 코드화된 warning type 접두어
7. deletion_mode delete/mark 정책 동일
8. reviewTargets 자동 적용 없이 별도 보존
9. 빈 line(strip 기준) 탐지 대상 제외, lineNo 원문 인덱스 유지
10. 탐지 함수 주입형 (regex/NER/AI 어댑터)
```

---

## 4. PDF 특유의 차이점

PDF는 다음 점에서 docx/pptx/hwpx와 다르다.

### 4.1 paragraph/표 구분이 명확하지 않음

PDF는 내부적으로 글자를 좌표 단위로 저장한다. 시각적인 paragraph, 표 셀, 본문 등의 구분이 내부 구조에 직접 표현되지 않는다. 따라서 line 단위로 통일 처리한다.

```text
docx:  section="body" | "table_cell"
pptx:  section="shape_text" | "table_cell" | "notes" | "group_*"
hwpx:  section="body" | "table_cell"
pdf:   section="text_line"  (단일)
```

### 4.2 한글 띄어쓰기 누락 문제 → x_tolerance=1 해결

pdfplumber 기본값(`x_tolerance=3`)은 영문 PDF에 맞춰져 있어 한글에서 띄어쓰기 누락이 자주 발생한다.

```text
default (x_tolerance=3):
  '입찰제안평가표, 세부평가의견서, 향후협상전략, ...'

x_tolerance=1:
  '입찰 제안 평가표, 세부 평가의견서, 향후 협상 전략, ...'
```

**1단계 검증 결과:**
- test2.pdf 전체 252 line 중 151 line에서 띄어쓰기 복원
- 글자 분리 등 부작용 0건
- 글자 크기와 무관 (단어 안 간격 ~0pt, 단어 사이 ~2pt 이상으로 명확히 구분됨)

### 4.3 bbox 좌표 함께 저장

향후 좌표 기반 안내/하이라이트 확장에 대비해 bbox를 location_meta에 저장한다.

```python
{
    "fileType": "pdf",
    "pageNo": 0,
    "section": "text_line",
    "lineNo": 5,
    "bbox": [50.0, 720.0, 540.0, 740.0],  # (x0, top, x1, bottom)
}
```

### 4.4 PDF 직접 편집의 어려움

PDF는 docx/한글 파일과 달리 일반 도구로 직접 편집하기 어렵다. 사용자 시나리오:

```text
권장: 원본 docx/한글 파일에서 비식별화 → PDF로 재저장
대안: PDF 편집 도구 (Adobe Acrobat 등) 사용
```

이 안내는 보고서와 향후 프론트엔드 UI에 명시한다.

### 4.5 스캔/암호 PDF 방어 처리

```text
스캔 PDF: 텍스트가 0인 PDF → WARNING_SCANNED_PDF_NO_TEXT 안내
암호 PDF: pdfplumber.open() 실패 → WARNING_PDF_ENCRYPTED 안내
```

OCR 및 암호 해제는 16주차 범위 외.

---

## 5. 구현 산출물

```text
src/pdf_detector.py                        (신규)
src/common_apply_utils.py                  (PDF 전용 warning type 5개 추가)
notebooks/21_test_pdf_detector.py          (TC1~TC19 단위 테스트)
notebooks/22_test_real_pdf_detection.py    (실제 PDF 통합 테스트)
reports/week16_pdf_detection_guide.md      (본 문서)
```

기존 파일 변경:

```text
src/common_apply_utils.py: PDF 전용 warning type 5개 추가
  - WARNING_MISSING_PAGE_NO
  - WARNING_PDF_PAGE_OUT_OF_RANGE
  - WARNING_PDF_TEXT_BLOCK_NOT_FOUND
  - WARNING_SCANNED_PDF_NO_TEXT
  - WARNING_PDF_ENCRYPTED
```

13~15주차 공통 인프라(`common_apply_result.py`, `deidentify_apply.py`, `deidentify_target_builder.py`, `regex_detector.py`)는 변경 없이 그대로 재사용한다.

---

## 6. PDF 위치 정책

### 6.1 location_meta 구조

```python
{
    "fileType": "pdf",
    "pageNo": 0,           # PDF 페이지 인덱스, 0-based
    "section": "text_line",  # 단일 section
    "lineNo": 5,           # 페이지 내 line 인덱스, 0-based
    "bbox": [50.0, 720.0, 540.0, 740.0],  # PDF 좌표계 (x0, top, x1, bottom)
}
```

### 6.2 1-based / 0-based 표시 규칙

```text
location_meta의 pageNo, lineNo: 0-based 저장
locationLabel: 사용자 표시용 1-based
```

### 6.3 locationLabel 형식

```text
"{page_no + 1}쪽 {line_no + 1}번째 줄: line text..."
```

예:

```text
1쪽 6번째 줄: 담당자 이메일은 test@example.com입니다.
3쪽 21번째 줄: - VLAN 301 : GI 1~12 port, VLAN 302 : GI 13~23 port
```

context는 최대 30자, 초과 시 `"..."` 표시 (13~15주차와 동일).

### 6.4 lineNo 원문 인덱스 유지

빈 line(strip 기준)은 탐지 대상에서 제외되지만, lineNo는 원문 인덱스를 유지한다. pdfplumber의 `extract_text_lines()`는 빈 line을 거의 생성하지 않으므로 실질적으로 거의 영향이 없으나, 일관성을 위해 정책을 명시한다.

---

## 7. line 순회 정책

### 7.1 처리 대상

```text
- 모든 page의 모든 line
- pdfplumber.Page.extract_text_lines(x_tolerance=1) 결과
- 빈 line(strip 기준) 제외
```

### 7.2 처리 제외

```text
- 스캔 PDF (이미지 안 텍스트) - OCR 미수행
- 암호화된 PDF - 열기 실패 시 warning만
- PDF 주석/첨부파일
- 폼 필드 (AcroForm/XFA)
- 다단 레이아웃의 좌우 컬럼 정밀 분리
```

---

## 8. 코드화된 warning type

13~15주차 type에 PDF 전용 5개를 추가했다.

| type 코드 | 의미 |
|---|---|
| `context_mismatch` | (공통) target.context와 현재 텍스트 불일치 |
| `slice_mismatch` | (공통) text[start:end]와 matched 불일치 |
| `unicode_normalization_mismatch` | (공통) NFC 정규화 후만 일치 |
| `empty_paragraph_target` | (공통) 빈 line/paragraph |
| `missing_paragraph_no` | (공통) lineNo 등 필수 위치 필드 누락 |
| `unknown_section` | (공통) 알 수 없는 section |
| `missing_page_no` | (PDF) pageNo 누락 |
| `pdf_page_out_of_range` | (PDF) page 범위 초과 |
| `pdf_text_block_not_found` | (PDF) line 위치를 PDF에서 찾을 수 없음 |
| `scanned_pdf_no_text` | (PDF) 텍스트 추출 0건 (스캔 가능성) |
| `pdf_encrypted` | (PDF) 암호화/손상 PDF |

저장 형식은 문자열 접두어 방식이다.

```text
[pdf_text_block_not_found] 99쪽 1번째 줄: 위치를 현재 PDF에서 찾을 수 없습니다.
[scanned_pdf_no_text] 이 PDF는 텍스트를 추출할 수 없는 스캔 PDF일 가능성이 있습니다.
[pdf_encrypted] PDF를 열 수 없습니다 (암호화 또는 손상 가능성).
```

---

## 9. 핵심 함수

### 9.1 detect_in_pdf()

```python
def detect_in_pdf(
    input_path: str,
    *,
    regex_detect_func: Callable | None = None,
    ner_detect_func: Callable | None = None,
    ai_predict_func: Callable | None = None,
    ner_threshold: float = 0.8,
    ai_threshold: float = 0.6,
    x_tolerance: float = 1.0,
) -> DeidentifyPlan
```

13~15주차 동일 시그니처. 탐지 함수 주입형.

### 9.2 build_guide_for_pdf()

```python
def build_guide_for_pdf(
    input_path: str,
    plan: DeidentifyPlan,
    *,
    deletion_mode: str = "delete",
    x_tolerance: float = 1.0,
) -> CommonApplyResult
```

- `applyMode="guide"`, `outputFilePath=None`
- 암호 PDF: PDF 열기 실패 시 PDF_ENCRYPTED warning
- 스캔 PDF: 추출 텍스트 0이면 SCANNED_PDF_NO_TEXT warning

### 9.3 detect_and_build_guide_for_pdf()

위 두 함수의 편의 wrapper.

### 9.4 보조 함수

```text
iter_pdf_lines()              - 모든 page의 line 순회
get_pdf_metadata()            - PDF 메타데이터 + 처리 가능 여부
_make_pdf_location_key()      - 위치 그룹화 키
_index_pdf_lines()            - 위치 키 → text 사전
_group_targets_by_location()  - auto target 위치별 그룹화
_build_guide_item_for_location()  - guide 모드 CommonApplyItem 생성
```

---

## 10. 단위 테스트 결과 (TC1~TC19)

`notebooks/21_test_pdf_detector.py`에서 19개 테스트 케이스를 검증했다. **48/48 모두 통과**했다.

임시 PDF는 reportlab으로 직접 생성한다. 한글 PDF는 reportlab CID 폰트(`HYSMyeongJo-Medium`)를 사용해 외부 폰트 없이 생성 가능.

| ID | 시나리오 | 결과 |
|---|---|---|
| TC1 | 이메일 line 마스킹 | PASS |
| TC2 | 성명 line 마스킹 | PASS |
| TC3 | 성명 + 이메일 동시 | PASS |
| TC4 | 내부 IP 삭제 (delete/mark) | PASS |
| TC5 | reviewTargets 보존 | PASS |
| TC6 | lineNo 없음 → missing_paragraph_no | PASS |
| TC7 | page 범위 초과 → pdf_text_block_not_found | PASS |
| TC8 | context 불일치, slice 일치 → 권장 + warning | PASS |
| TC9 | slice 불일치 → skip + warning | PASS |
| TC10 | 여러 line 분산 | PASS |
| TC11 | summary 정합성 | PASS |
| TC12 | deletion_mode=mark | PASS |
| TC13 | 여러 page 분산 | PASS |
| TC14 | locationLabel 형식 (1쪽 6번째 줄) | PASS |
| TC15 | applyMode="guide", outputFilePath=None | PASS |
| TC16 | bbox 좌표 자동 저장 | PASS |
| TC17 | 한글 띄어쓰기 정확 추출 (x_tolerance=1) | PASS |
| TC18 | 빈 PDF → scanned_pdf_no_text warning | PASS |
| TC19 | 암호 PDF → pdf_encrypted 또는 scanned warning | PASS |

---

## 11. 실제 PDF 통합 테스트 결과

### 11.1 test.pdf (업무보고, 2 page)

```text
pageCount: 2
totalLines: 28
totalCharsExtracted: 818
isEncrypted: False
```

mock regex(성명/사번/VLAN)로 9건 탐지:
- 1쪽 7번째 줄: 오상현(4257), 신동석(4251) (성명 2 + 사번 2 = 4건)
- 1쪽 13번째 줄: 노병우 (성명 1건)
- 1쪽 21번째 줄: VLAN 301, VLAN 302 (2건)
- 1쪽 22번째 줄: VLAN 301, VLAN 302 (2건)

mark 모드 권장 결과 예:
```text
original: - VLAN 301 : GI 1~12 port, VLAN 302 : GI 13~23 port
권장   : - (삭제됨) : GI 1~12 port, (삭제됨) : GI 13~23 port
```

### 11.2 test2.pdf (보안 가이드라인, 20 page)

```text
pageCount: 20
totalLines: 251
totalCharsExtracted: 7181
isEncrypted: False
emptyPages: []
```

src/regex_detector.py로 자동 탐지 시 VLAN 201 (19쪽 15번째 줄) 1건 탐지.

### 11.3 한글 띄어쓰기 검증

```text
default (x_tolerance=3):
  '입찰제안평가표, 세부평가의견서, 향후협상전략, ...'

x_tolerance=1:
  '입찰 제안 평가표, 세부 평가의견서, 향후 협상 전략, ...'
```

x_tolerance=1로 정확한 띄어쓰기 복원 확인.

---

## 12. 누적 회귀 테스트 결과

| 주차 | 테스트 | 결과 |
|---|---|---|
| 12주차 | xlsx 회귀 | 13/13 |
| 13주차 | TC1~TC18 docx | 52/52 |
| 14주차 | TC1~TC23 pptx | 67/67 |
| 15주차 | TC1~TC22 hwpx | 61/61 |
| **16주차** | **TC1~TC19 pdf** | **48/48** |
| **합계** | | **241/241** |

`common_apply_utils.py`에 PDF 전용 warning type 5개를 추가했지만 기존 type은 변경 없어 docx/pptx/hwpx/xlsx 회귀가 발생하지 않았다.

---

## 13. 사용자 시나리오

```text
1. 사용자가 PDF 파일을 업로드한다.
2. 시스템이 모든 page의 line을 순회하며 탐지한다.
3. 시스템이 guide 모드 CommonApplyResult를 반환한다.
4. 프론트엔드가 위치별로 안내 목록을 표시한다.
   - 위치: "1쪽 7번째 줄: 오상현(4257) 신동석(4251)"
   - 항목: "성명", "사번"
   - 조치: "마스킹"
   - 원문: "오상현(4257) 신동석(4251)"
   - 권장 결과: "*********  *********"
5. 사용자가 다음 중 하나로 수정한다:
   a. 원본 docx/한글 파일에서 비식별화 후 PDF로 재저장 (권장)
   b. PDF 편집 도구(Adobe Acrobat 등)로 직접 수정
6. 수정 완료 후 PDF를 사용한다.
```

PDF는 docx/pptx/hwpx와 달리 직접 편집이 어렵다는 점을 사용자에게 명확히 안내한다.

---

## 14. 16주차 완료 범위

```text
1. pdf_detector.py 구현 (pdfplumber 기반)
2. line 단위 텍스트 추출 (x_tolerance=1로 한글 띄어쓰기 정확 복원)
3. bbox 좌표 저장 (향후 좌표 기반 안내 확장 대비)
4. detect_in_pdf() — regex/NER/AI 어댑터 (주입형)
5. build_guide_for_pdf() — applyMode="guide" CommonApplyResult 생성
6. detect_and_build_guide_for_pdf() — 편의 wrapper
7. locationLabel 형식 ("1쪽 6번째 줄: ...")
8. 1-based 표시 / 0-based 저장 규칙
9. PDF 전용 warning type 5개 추가
10. 스캔 PDF 감지 + warning
11. 암호 PDF 방어 + warning
12. TC1~TC19 단위 테스트 (48/48 통과)
13. 실제 test.pdf + test2.pdf 통합 테스트
14. --force-mock-review 옵션으로 reviewTargets 실증
```

---

## 15. 16주차 범위 밖 작업

```text
1. PDF 파일 자동 수정/redaction
2. OCR (스캔 PDF의 텍스트 추출)
3. 좌표 기반 정밀 하이라이트 표시
4. PDF 주석/첨부파일 내부 탐지
5. 폼 필드(AcroForm/XFA) 탐지
6. 다단 레이아웃의 좌우 컬럼 정밀 분리
7. 표 셀 행/열 정밀 분리 (line 단위로 처리)
8. 암호 PDF 해제
9. 14주차에서 미룬 warning 분리 (slide_out_of_range 단계별 등)
10. 프론트엔드 guide 모드 UI 실제 연결
```

---

## 16. PDF 처리의 알려진 한계

### 16.1 다단 레이아웃의 좌우 컬럼 합쳐짐

```text
test2.pdf page 18 (2단 레이아웃):
  '기관사 홍길동 (사번 12345) 기관사 A'
  → 왼쪽 컬럼 "기관사 홍길동 (사번 12345)"과 오른쪽 컬럼 "기관사 A"가
     같은 line으로 묶임
```

PDF 구조상 좌우 컬럼이 같은 y 좌표에 있을 때 같은 line으로 인식됨. 비식별화 자체에는 영향 없음 (성명/사번 탐지 정상).

### 16.2 표 셀이 시각적으로 같은 줄에 있을 때 합쳐짐

```text
test2.pdf page 5 (표 페이지):
  'S급 민감정보 • 제7호:법인·단체·개인의경영상...'
  → "S급 민감정보" 셀과 "• 제7호:..." 셀이 같은 줄에 있어 합쳐짐
```

PoC 단계에서 허용. 향후 표 셀 정밀 분리는 별도 확장 단계에서 검토.

### 16.3 일부 한글 PDF에서 글자 깨짐

```text
test.pdf 첫 줄:
  '보 고 선 gfedc gfedc gfedc gfedcb gfedcb gfedc gfedcb'
  → 한글 단독 부호 ☐ ☑ 등이 CID 폰트 매핑상 'gfedc'로 출력
```

PDF 생성 도구(한컴오피스 등)의 폰트 매핑 문제. 비식별화 대상은 아니므로 처리 영향 없음.

---

## 17. 결론

16주차는 PDF 비식별화에 대해 docx/pptx/hwpx와 동일한 탐지 + 안내 방식을 채택해 다음을 달성했다.

```text
1. 서식 100% 보존 (사용자가 직접 수정하므로 시스템이 깨뜨릴 일 없음)
2. MIT 라이선스 pdfplumber로 배포 부담 없음
3. 13~15주차 공통 인프라(common_apply_utils, applyMode, CommonApplyItem) 재사용
4. 한글 띄어쓰기 정확 복원 (x_tolerance=1)
5. bbox 좌표 함께 저장으로 향후 좌표 기반 안내 확장 대비
6. 스캔/암호 PDF 방어 처리
7. TC1~TC19 단위 테스트 48/48 통과
8. 실제 두 PDF 파일로 파이프라인 동작 검증 완료
9. 누적 회귀 테스트 241/241 통과
```

xlsx 자동 Apply, docx/pptx/hwpx/pdf 안내 5가지가 모두 `CommonApplyResult.applyMode`로 구분되어, 프론트엔드는 동일한 구조로 처리할 수 있다.

12~16주차로 핵심 파일 형식 5가지(xlsx, docx, pptx, hwpx, pdf)의 detector 구현이 모두 완료되었다. 다음은 프론트엔드 연결과 NER/AI 모델 통합 단계가 자연스러운 진행이다.
