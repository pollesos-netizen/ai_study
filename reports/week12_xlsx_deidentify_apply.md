# 12주차 xlsx 파일 단위 비식별화 Apply 설계

## 1. 목적

12주차의 목적은 11주차에서 구현한 문자열 단위 Apply 엔진을 실제 `xlsx` 파일의 셀 단위 수정에 연결하는 것이다.

11주차까지의 흐름은 다음과 같다.

```text
DeidentifyTarget
→ apply_targets_to_text()
→ ApplyResult
→ applied_text
```

12주차에서는 이 흐름을 `xlsx` 파일에 적용한다.

```text
xlsx 파일
→ locationMeta.sheetName + locationMeta.cellRef
→ 셀 값 조회
→ apply_targets_to_text()
→ 셀 값 수정
→ 비식별화된 xlsx 파일 저장
```

단, 12주차에서도 모든 문서 형식을 다루지 않는다.  
실제 파일 Apply의 첫 번째 PoC로 `xlsx`만 다룬다.

```text
12주차:
xlsx Apply PoC

13주차 이후:
docx / pptx / hwpx Apply 순차 확장
```

---

## 2. 12주차 핵심 목표

12주차의 핵심 목표는 다음과 같다.

```text
1. xlsx 파일을 열어 셀 단위로 비식별화 적용
2. 원본 파일은 유지하고 output 파일을 별도로 생성
3. 문자열 셀에만 자동 Apply 수행
4. 비문자열 셀, 수식 셀, 병합 셀 예외 처리
5. 공통 Apply 결과 구조(CommonApplyResult) 설계
6. 프론트엔드가 xlsx 전용 구조에 의존하지 않도록 결과를 공통화
```

---

## 3. 구현 파일

12주차 산출물은 다음으로 한다.

```text
src/common_apply_result.py
src/xlsx_deidentify_apply.py
notebooks/13_test_xlsx_deidentify_apply.py
reports/week12_xlsx_deidentify_apply.md
```

각 파일의 역할은 다음과 같다.

| 파일 | 역할 |
|---|---|
| `common_apply_result.py` | 파일 형식 공통 Apply 결과 구조 정의 |
| `xlsx_deidentify_apply.py` | xlsx 파일을 열고 셀 단위 Apply 수행 |
| `13_test_xlsx_deidentify_apply.py` | 샘플 xlsx 생성 및 Apply 테스트 |
| `week12_xlsx_deidentify_apply.md` | 12주차 설계 및 테스트 결과 정리 |

---

## 4. 사용 라이브러리

xlsx Apply에는 `openpyxl`을 사용한다.

선택 이유:

```text
1. 기존 xlsx 파일을 열 수 있다.
2. 셀 단위 수정 후 저장할 수 있다.
3. 서식, 시트 구조를 비교적 잘 보존한다.
4. xlsxwriter나 pandas보다 기존 파일 수정에 적합하다.
```

사용하지 않는 방식:

| 방식 | 제외 이유 |
|---|---|
| `xlsxwriter` | 신규 작성 중심. 기존 파일 수정에 부적합 |
| `pandas` | 데이터프레임 중심. 서식 손실 위험 큼 |

단, `openpyxl`에도 한계가 있다.

```text
openpyxl로 기존 파일을 다시 저장하면 차트, 일부 조건부 서식,
VBA 매크로, 외부 연결, 고급 개체 등이 손실되거나 변경될 수 있다.
```

따라서 12주차는 일반 셀 중심 PoC로 진행하고, 실제 운영 전에는 회사 문서 샘플로 보존성 테스트를 수행해야 한다.

---

## 5. workbook 로드 정책

수식 보존을 위해 반드시 `data_only=False`로 연다.

```python
openpyxl.load_workbook(input_path, data_only=False)
```

정책:

```text
data_only=False:
수식 셀은 =A1+B1 같은 수식 문자열로 읽힌다.
저장 시 수식 보존 가능성이 높다.

data_only=True:
수식의 마지막 계산 결과를 읽는다.
저장 시 수식이 값으로 굳어질 위험이 있다.
```

따라서 xlsx Apply에서는 `data_only=False`를 사용한다.

수식 셀은 자동 Apply 대상에서 제외한다.

```text
수식 셀
→ skip + warning
```

---

## 6. 셀 타입 처리 정책

xlsx 셀에는 문자열뿐 아니라 숫자, 날짜, boolean, 수식 등이 들어갈 수 있다.

11주차의 `apply_targets_to_text()`는 문자열 입력을 전제로 하므로, 12주차에서는 문자열 셀만 자동 Apply 대상으로 처리한다.

정책:

```text
1. 문자열 타입 셀만 Apply 대상으로 처리한다.
2. 비문자열 셀에 Detection이 있으면 skip + warning 처리한다.
3. 셀 타입은 임의로 변경하지 않는다.
4. 수식 셀도 skip + warning 처리한다.
```

예:

```text
[민원대장 탭 B3 셀]:
비문자열 셀에 detection이 있어 자동 적용을 건너뛰었습니다.
cellType=number, cellValue=01012345678
```

수식 셀 warning은 일반 비문자열 셀과 구분한다.

```text
[시트 탭 C5 셀]:
수식 셀에 detection이 있어 자동 적용을 건너뛰었습니다.
cellType=formula, formula==A1+B1
```

PoC 단계에서는 warning이 다소 많더라도 원인을 명확히 드러내는 것이 더 중요하므로, 수식 셀도 warning을 남긴다.

---

## 7. 문자열 셀 판정 기준

openpyxl의 셀 값과 data_type을 기준으로 판정한다.

예상 처리:

```python
cell.value is str
cell.data_type == "s"
```

다만 일부 셀은 값이 문자열이어도 data_type이 다르게 표시될 수 있으므로, 최종적으로는 다음을 기준으로 한다.

```text
isinstance(cell.value, str) 이고
cell.data_type != "f"
```

즉:

```text
문자열 값 → Apply 가능
수식 셀 → skip
숫자/날짜/boolean/None → skip
```

빈 셀에 Detection이 있는 경우도 skip + warning 처리한다.

---

## 8. 병합 셀 처리 정책

xlsx에는 병합 셀이 존재할 수 있다.

openpyxl에서는 병합 셀의 값이 보통 병합 범위의 좌상단 셀에만 저장되고, 나머지는 `MergedCell`로 처리된다.

정책:

```text
1. cellRef가 병합 범위의 좌상단 셀이면 적용 가능
2. cellRef가 병합 범위 내부이지만 좌상단 셀이 아니면 skip + warning
3. 12주차에서는 병합 셀 cellRef를 자동 보정하지 않는다.
4. 향후 Detection/Parser 단계에서 병합 셀은 좌상단 cellRef로 정규화하는 방향을 검토한다.
```

예:

```text
[민원대장 탭 C4 셀]:
병합 셀의 좌상단 셀이 아니므로 자동 적용을 건너뛰었습니다.
mergedRange=B4:D4, topLeft=B4
```

만약 Detection이 `C4`로 들어왔는데 실제 값은 `B4`에 있는 경우, 자동으로 `B4`를 수정하는 것은 위험하다.  
따라서 12주차 PoC에서는 skip + warning으로 처리한다.

---

## 9. 위치 정보 정책

xlsx Apply는 `locationMeta`의 다음 값을 사용한다.

```text
fileType
sheetName
cellRef
```

필수 조건:

```text
locationMeta.fileType == "xlsx"
locationMeta.sheetName 존재
locationMeta.cellRef 존재
```

조건을 만족하지 않으면 자동 Apply하지 않는다.

예:

```text
sheetName 없음 → skip + warning
cellRef 없음 → skip + warning
fileType이 xlsx가 아님 → xlsx Apply 대상에서 제외
```

`locationLabel`은 사용자 표시용이며, 실제 파일 위치를 찾는 기준은 `locationMeta`이다.

---

## 10. 한글 시트명 정규화 정책

회사 문서에는 한글 시트명이 자주 등장한다.

예:

```text
계약내역
민원처리
시스템정보
```

Mac/Windows 환경에 따라 한글 자모 정규화 형태가 달라질 수 있으므로, 시트명 비교에는 NFC 정규화를 적용한다.

```python
unicodedata.normalize("NFC", sheet_name)
```

정책:

```text
1. workbook의 sheetnames를 NFC 정규화한다.
2. locationMeta.sheetName도 NFC 정규화한다.
3. 정규화된 값끼리 비교한다.
4. 실제 worksheet 접근은 workbook에 존재하는 원본 sheetName으로 수행한다.
```

---

## 11. 문자열 비교와 NFC 정규화

`target.context`, `target.matched`, `cell_value` 비교에도 NFC 정규화를 보조적으로 사용한다.

다만 실제 Apply는 원본 `cell_value[start:end]` 기준으로 수행한다.

중요한 정책:

```text
1. NFC 정규화는 비교 보조 용도이다.
2. 실제 Apply는 원본 cell_value의 start/end 기준으로 수행한다.
3. 원본 cell_value[start:end]와 target.matched가 직접 일치해야 Apply 가능하다.
4. NFC 정규화 후에만 일치하는 경우는 자동 적용하지 않는다.
5. 이 경우 정규화 형태 차이 또는 인덱스 기준 불일치 가능성으로 skip + warning 처리한다.
```

이유는 정규화 형태가 다르면 문자열 길이와 인덱스가 달라질 수 있기 때문이다.

예:

```text
cell_value = NFD 형태의 "김도윤 담당자"
target.matched = NFC 형태의 "김도윤"
target.start/end = NFC 기준 0~3
```

이 경우 원본 `cell_value[0:3]`이 실제 `김도윤` 전체를 가리키지 않을 수 있다.  
따라서 정규화 후에는 같더라도 원본 slice가 다르면 적용하지 않는다.

---

## 12. context 불일치 정책

xlsx Apply에서 실제 기준은 파일에서 읽은 셀 값이다.

```text
cell_value = 실제 xlsx 파일에서 읽은 셀 값
target.context = Detection 생성 당시 문맥
```

정책:

```text
1. cell_value와 target.context가 다르면 warning을 남긴다.
2. 실제 적용 가능 여부는 cell_value[start:end]와 target.matched 비교로 판단한다.
3. cell_value[start:end] == target.matched이면 적용한다.
4. cell_value[start:end] != target.matched이면 skip + warning 처리한다.
```

즉, 여기서 `text`는 반드시 `cell_value`를 의미한다.

예:

```text
target.context:
담당자 이메일은 test@example.com입니다.

cell_value:
담당자 이메일: test@example.com

cell_value[start:end] == target.matched
→ 적용 + context 불일치 warning
```

반대로:

```text
cell_value[start:end] != target.matched
→ 위치가 어긋난 것으로 보고 skip + warning
```

이 검증은 `xlsx_deidentify_apply.py` 내부에서 사전 검증으로 수행한다.

`apply_targets_to_text()`에 `strict=True` 같은 옵션을 추가하지 않는다.  
11주차 문자열 Apply 엔진은 일반 용도로 유지하고, xlsx 파일 Apply의 보수적 정책은 xlsx 모듈에 격리한다.

---

## 13. output 파일명 정책

원본 파일은 절대 덮어쓰지 않는다.

기본 output 파일명 규칙:

```text
original.xlsx
→ original_deidentified.xlsx
```

동일한 파일명이 이미 있으면 번호 suffix를 붙인다.

```text
original_deidentified.xlsx
original_deidentified_1.xlsx
original_deidentified_2.xlsx
```

정책:

```text
1. output_path가 명시되면 해당 경로를 사용한다.
2. output_path가 없으면 input 파일명 + _deidentified 규칙으로 생성한다.
3. 기존 파일이 있으면 _1, _2 suffix를 붙인다.
4. 12주차 PoC에서는 overwrite를 허용하지 않는다.
```

실제 배포 단계에서는 `overwrite=True` 옵션 또는 파일 관리 정책을 별도로 검토한다.

---

## 14. CommonApplyResult 설계

프론트엔드가 xlsx 전용 구조에 의존하지 않도록, 파일 형식별 Apply 결과는 공통 구조로 변환한다.

12주차에서는 다음 파일을 작성한다.

```text
src/common_apply_result.py
```

### 14-1. CommonApplyItem

```python
@dataclass
class CommonApplyItem:
    locationLabel: str | None
    locationMeta: dict
    label: str
    action: str
    originalText: str
    appliedText: str
    status: str
    appliedTargetCount: int
    skippedTargetCount: int
    warnings: list[str]
```

`status` 값은 다음으로 제한한다.

```text
applied
partial
skipped
```

의미:

| status | 의미 |
|---|---|
| `applied` | 해당 location의 target이 모두 적용됨 |
| `partial` | 일부 target은 적용되고 일부 target은 skip됨 |
| `skipped` | 적용된 target이 없고 전부 skip됨 |

warning 여부는 `status`로 표현하지 않고 `warnings` 필드로 판단한다.

---

### 14-2. label 필드 정책

한 셀에 여러 target이 있을 수 있다.

예:

```text
성명 + 이메일 주소
```

12주차 PoC에서는 `label`을 콤마 결합 문자열로 제공한다.

```text
label = "성명, 이메일 주소"
```

다만 향후 프론트엔드에서 target 단위 승인/거부, 개별 상세 표시가 필요하면 다음 구조로 확장한다.

```text
appliedTargets: list[dict]
skippedTargets: list[dict]
```

12주차에서는 단순 preview를 목표로 하므로 label 결합 방식으로 시작한다.

---

### 14-3. CommonReviewItem

`reviewTargets`도 dict가 아니라 dataclass로 구조화한다.

```python
@dataclass
class CommonReviewItem:
    locationLabel: str | None
    locationMeta: dict
    label: str
    action: str
    context: str
    reason: str | None = None
```

이렇게 해야 프론트엔드에서 review target도 안정적으로 렌더링할 수 있다.

---

### 14-4. CommonApplySummary

프론트엔드 표시를 위해 요약 정보를 포함한다.

```python
@dataclass
class CommonApplySummary:
    totalLocations: int
    appliedLocations: int
    partialLocations: int
    skippedLocations: int
    totalWarnings: int
    autoTargetCount: int
    reviewTargetCount: int
```

---

### 14-5. CommonApplyResult

최종 공통 결과 구조는 다음과 같다.

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
```

이 구조를 사용하면 xlsx뿐 아니라 docx, pptx, hwpx Apply 결과도 같은 방식으로 프론트엔드에 전달할 수 있다.

---

## 15. xlsx Apply 처리 흐름

전체 처리 흐름은 다음과 같다.

```text
1. input xlsx 로드
2. output 경로 결정
3. DeidentifyPlan.auto_targets 중 fileType=xlsx만 필터링
4. sheetName / cellRef 검증
5. sheetName NFC 정규화 후 worksheet 찾기
6. 병합 셀 여부 확인
7. 셀 타입 확인
8. 문자열 셀이 아니면 skip + warning
9. 수식 셀이면 skip + warning
10. cell_value와 target.context 비교
11. cell_value[start:end]와 target.matched 직접 비교
12. 유효 target만 apply_targets_to_text()로 적용
13. 셀 값 수정
14. output xlsx 저장
15. CommonApplyResult 반환
```

---

## 16. xlsx Apply 주요 함수

`src/xlsx_deidentify_apply.py`에는 다음 함수를 작성한다.

```python
apply_plan_to_xlsx(
    input_path: str,
    plan: DeidentifyPlan,
    output_path: str | None = None,
    deletion_mode: str = "delete",
) -> CommonApplyResult
```

보조 함수:

```text
make_output_path()
filter_xlsx_targets()
normalize_sheet_name()
find_worksheet()
is_formula_cell()
is_string_cell()
check_merged_cell()
validate_xlsx_target()
group_targets_by_sheet_cell()
apply_targets_to_cell()
```

---

## 17. 테스트 케이스

테스트 스크립트:

```text
notebooks/13_test_xlsx_deidentify_apply.py
```

테스트 케이스는 다음과 같다.

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC1 | 문자열 셀 이메일 마스킹 | 적용 |
| TC2 | 문자열 셀 성명 마스킹 | 적용 |
| TC3 | 한 셀에 성명 + 이메일 동시 마스킹 | 적용 |
| TC4 | 내부 IP 삭제 | 적용, 실제 삭제 |
| TC5 | review_targets 미적용 | reviewTargets로 보존 |
| TC6 | sheetName 없음 | skip + warning |
| TC7 | cellRef 없음 | skip + warning |
| TC8 | context 불일치, slice 일치 | 적용 + warning |
| TC9 | cell_value[start:end]와 matched 불일치 | skip + warning |
| TC10 | 숫자 셀 | skip + warning |
| TC11 | 수식 셀 | skip + warning |
| TC12 | 병합 셀 비좌상단 | skip + warning |
| TC13 | 한글 시트명 NFC 정규화 | 적용 |
| TC14 | 원본 파일 유지, output 파일 생성 | 확인 |

---

## 18. 프론트엔드 연결 방향

12주차에서 프론트엔드를 연결한다면 xlsx 전용 UI로 만들지 않는다.

프론트엔드는 `CommonApplyResult`만 바라보도록 한다.

표시 항목:

```text
fileType
inputFilePath
outputFilePath
autoResults
reviewTargets
warnings
summary
```

autoResults 표시 컬럼:

| 컬럼 | 데이터 |
|---|---|
| 위치 | locationLabel |
| 항목 | label |
| 조치 | action |
| 원문 | originalText |
| 적용 결과 | appliedText |
| 상태 | status |
| 경고 | warnings |

`locationMeta`는 내부 데이터로 보관하고, 기본 UI에서는 숨긴다.  
필요하면 상세 보기에서만 표시한다.

---

## 19. 12주차에서 하지 않을 것

12주차에서는 다음은 하지 않는다.

```text
docx Apply
pptx Apply
hwpx Apply
review_targets 사용자 승인 후 재적용
파일 diff 편집 UI
xlsx 고급 개체 보존성 검증 전체
```

12주차는 xlsx 셀 단위 Apply PoC와 공통 결과 구조 설계에 집중한다.

---

## 20. 13주차 이후 확장 계획

13주차 이후에는 파일 형식별 Apply를 순차 확장한다.

```text
13주차:
docx Apply PoC

14주차:
pptx Apply PoC

15주차 이후:
hwpx Apply 검토
```

각 파일 형식의 Apply 방식은 다르지만, 최종 결과는 `CommonApplyResult`로 맞춘다.

```text
apply_plan_to_xlsx()
→ CommonApplyResult

apply_plan_to_docx()
→ CommonApplyResult

apply_plan_to_pptx()
→ CommonApplyResult

apply_plan_to_hwpx()
→ CommonApplyResult
```

이 구조를 유지하면 프론트엔드를 파일 형식별로 크게 수정하지 않아도 된다.

---

## 21. 결론

12주차는 실제 파일 Apply의 첫 번째 단계이다.

핵심은 다음이다.

```text
1. xlsx 파일에서 locationMeta.sheetName + cellRef로 셀을 찾는다.
2. 문자열 셀에만 11주차 Apply 엔진을 적용한다.
3. 비문자열, 수식, 병합 셀 예외는 skip + warning 처리한다.
4. 원본 파일은 유지하고 output 파일을 별도로 생성한다.
5. 결과는 CommonApplyResult로 통일한다.
```

이를 통해 이후 docx, pptx, hwpx Apply도 같은 프론트엔드 구조에 연결할 수 있다.
