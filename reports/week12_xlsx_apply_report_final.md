# 12주차 xlsx 파일 단위 비식별화 Apply 결과 정리

## 1. 목적

12주차의 목표는 11주차에서 만든 문자열 단위 Apply 엔진을 실제 `xlsx` 파일에 연결하는 것이었다.

```text
11주차:
DeidentifyTarget → apply_targets_to_text() → applied_text

12주차:
xlsx 파일 → 셀 단위 Detection/Target → apply_plan_to_xlsx() → 비식별화된 xlsx 파일
```

12주차에서는 `xlsx`만 실제 파일 Apply 대상으로 구현했다. `docx`, `pptx`, `hwpx`는 이후 주차에서 순차적으로 확장한다. `pdf`, `hwp`는 향후 parsing 대상에는 포함하지만, 원본 파일 비식별화 Apply는 필수 목표로 두지 않는다.

---

## 2. 구현 산출물

12주차 구현 산출물은 다음과 같다.

```text
src/common_apply_result.py
src/xlsx_deidentify_apply.py
notebooks/13_test_xlsx_deidentify_apply.py
notebooks/14_test_real_xlsx_detection_apply.py
reports/week12_xlsx_deidentify_apply.md
```

각 파일의 역할은 다음과 같다.

| 파일 | 역할 |
|---|---|
| `common_apply_result.py` | 파일 형식 공통 Apply 결과 구조 정의 |
| `xlsx_deidentify_apply.py` | xlsx 파일 셀 단위 Apply 구현 |
| `13_test_xlsx_deidentify_apply.py` | TC 기반 xlsx Apply 단위 테스트 |
| `14_test_real_xlsx_detection_apply.py` | 실제 xlsx 파일 대상 regex + NER + AI 통합 테스트 |
| `week12_xlsx_deidentify_apply.md` | 설계 및 테스트 결과 정리 |

---

## 3. 주요 설계 정책

### 3.1 xlsx 처리 라이브러리

xlsx 파일 처리는 `openpyxl`을 사용한다.

```python
openpyxl.load_workbook(input_path, data_only=False)
```

`data_only=False`를 사용하는 이유는 수식 보존 때문이다. `data_only=True`로 열면 수식 셀의 계산 결과값을 읽게 되어 저장 시 수식이 값으로 굳어질 위험이 있다.

### 3.2 셀 타입 정책

문자열 셀만 자동 Apply 대상으로 처리한다.

```text
문자열 셀 → Apply 가능
숫자/날짜/boolean/빈 셀 → skip + warning
수식 셀 → skip + warning
```

수식 셀은 문자열처럼 보일 수 있지만, 수식을 직접 마스킹하면 엑셀 수식이 깨질 수 있으므로 자동 적용하지 않는다.

### 3.3 병합 셀 정책

병합 셀은 좌상단 셀만 Apply 대상으로 본다.

```text
병합 범위 좌상단 셀 → Apply 가능
병합 범위 내부의 비좌상단 셀 → skip + warning
```

12주차에서는 병합 셀 cellRef를 자동으로 좌상단으로 보정하지 않는다. 이후 parser 단계에서 병합 셀의 위치를 좌상단 cellRef로 정규화하는 방향을 검토한다.

### 3.4 문자열 비교 정책

실제 Apply는 반드시 원본 셀 값 기준으로 수행한다.

```text
cell_value[start:end] == target.matched
→ Apply 가능

cell_value[start:end] != target.matched
→ skip + warning
```

NFC 정규화는 비교 보조 용도로만 사용한다. NFC 정규화 후에만 일치하는 경우는 인덱스 기준이 어긋났을 가능성이 있으므로 자동 Apply하지 않는다.

### 3.5 context 불일치 정책

`target.context`와 실제 `cell_value`가 다를 수 있다. 이 경우 context 전체 불일치만으로 바로 skip하지 않는다.

```text
target.context != cell_value
cell_value[start:end] == target.matched
→ 적용 + warning

cell_value[start:end] != target.matched
→ skip + warning
```

즉, 실제 적용 가능 여부는 `target.context`가 아니라 현재 파일에서 읽은 `cell_value[start:end]`를 기준으로 판단한다.

### 3.6 삭제 표시 정책

삭제 action은 두 모드로 분리했다.

```text
deletion_mode="delete"
→ 실제 삭제. 빈 문자열로 제거.

deletion_mode="mark"
→ 사용자 확인용 preview. "(삭제됨)"으로 표시.
```

운영 저장용은 `delete`, 사용자 검토용 preview는 `mark`를 사용한다.

---

## 4. CommonApplyResult 구조

프론트엔드가 xlsx 전용 구조에 의존하지 않도록 공통 결과 구조를 정의했다.

```text
CommonApplyResult
├─ fileType
├─ inputFilePath
├─ outputFilePath
├─ autoResults: list[CommonApplyItem]
├─ reviewTargets: list[CommonReviewItem]
├─ warnings
└─ summary: CommonApplySummary
```

`CommonApplyItem.originalText`와 `appliedText`는 target 조각이 아니라 **location 단위의 전체 텍스트**를 의미한다.

xlsx에서는 location 단위가 셀이므로 다음과 같이 해석한다.

```text
originalText = 셀 값 전체
appliedText = 비식별화 적용 후 셀 값 전체
```

이 기준은 이후 docx, pptx, hwpx에도 유지한다.

```text
docx: 문단 단위로 잡으면 문단 전체
pptx: shape 또는 텍스트 박스 단위로 잡으면 해당 shape 텍스트 전체
hwpx: XML 텍스트 노드 또는 문단 단위로 잡으면 해당 단위 텍스트 전체
```

---

## 5. 공통 Apply 함수 인터페이스

향후 파일 형식별 Apply 함수는 다음 공통 인터페이스를 따른다.

```python
def apply_plan_to_<format>(
    input_path: str,
    plan: DeidentifyPlan,
    output_path: str | None = None,
    deletion_mode: str = "delete",
) -> CommonApplyResult:
    ...
```

12주차의 `apply_plan_to_xlsx()`는 이 공통 인터페이스의 첫 구현체이다.

```text
apply_plan_to_xlsx()
apply_plan_to_docx()
apply_plan_to_pptx()
apply_plan_to_hwpx()
```

---

## 6. TC 기반 xlsx Apply 테스트 결과

`notebooks/13_test_xlsx_deidentify_apply.py`에서 TC1~TC16을 구성하여 xlsx Apply 모듈을 검증했다.

검증 범위는 다음과 같다.

```text
TC1: 문자열 셀 이메일 마스킹
TC2: 문자열 셀 성명 마스킹
TC3: 한 셀의 성명 + 이메일 동시 마스킹
TC4: 내부 IP 삭제
TC5: review_targets 미적용
TC6: sheetName 없음 skip + warning
TC7: cellRef 없음 skip + warning
TC8: context 불일치, slice 일치 시 적용 + warning
TC9: slice 불일치 skip + warning
TC10: 숫자 셀 skip + warning
TC11: 수식 셀 skip + warning
TC12: 병합 셀 비좌상단 skip + warning
TC13: 한글 시트명 NFC 정규화
TC14: 원본 파일 유지, output 파일 생성
TC15: 같은 시트 여러 셀 적용
TC16: summary 정합성 검증
```

핵심 확인 결과는 다음과 같다.

```text
문자열 셀 Apply 정상
비문자열/수식/병합 비좌상단 셀 skip 정상
sheetName/cellRef 누락 warning 정상
원본 파일 유지 정상
output 파일 생성 정상
summary 정합성 정상
```

---

## 7. openpyxl 병합 셀 처리 수정 이력

테스트 중 openpyxl 버전 차이로 병합 셀 처리 오류가 발생했다.

### 7.1 tuple in merged_range 오류

초기 코드에서는 다음 방식으로 병합 범위 포함 여부를 확인했다.

```python
if (row, col) in merged_range:
    ...
```

일부 openpyxl 환경에서 `MergedCellRange.__contains__`가 튜플을 받지 않아 오류가 발생했다.

수정 후에는 행/열 범위를 직접 비교한다.

```python
in_range = (
    merged_range.min_row <= row <= merged_range.max_row
    and merged_range.min_col <= col <= merged_range.max_col
)
```

### 7.2 min_col_letter 속성 오류

`MergedCellRange` 객체에 `min_col_letter` 속성이 없어 오류가 발생했다.

초기 코드:

```python
top_left = f"{merged_range.min_col_letter}{merged_range.min_row}"
```

수정 코드:

```python
from openpyxl.utils import get_column_letter

top_left = f"{get_column_letter(merged_range.min_col)}{merged_range.min_row}"
```

---

## 8. 실제 xlsx 통합 테스트

`notebooks/14_test_real_xlsx_detection_apply.py`를 작성하여 실제 xlsx 파일에서 다음 전체 흐름을 검증했다.

```text
실제 xlsx 파일
→ 문자열 셀 순회
→ regex 탐지
→ NER 탐지
→ AI 문장분류
→ DeidentifyPlan 생성
→ apply_plan_to_xlsx()
→ 비식별화된 xlsx 저장
```

실행 예시:

```bash
python notebooks/14_test_real_xlsx_detection_apply.py "data\xlsx_test1.xlsx" \
  --ner-model-path "models\hf\KoELECTRA-small-v3-modu-ner" \
  --ai-model-path "models\privacy_cso_char_keras_model.keras"
```

삭제 위치를 사용자에게 표시하려면 preview 모드를 사용한다.

```bash
python notebooks/14_test_real_xlsx_detection_apply.py "data\xlsx_test1.xlsx" \
  --ner-model-path "models\hf\KoELECTRA-small-v3-modu-ner" \
  --ai-model-path "models\privacy_cso_char_keras_model.keras" \
  --deletion-mode mark
```

---

## 9. 실제 xlsx 통합 테스트 결과

실제 xlsx 파일 통합 테스트 결과는 다음과 같았다.

```text
stringCellCount: 12
regexTargetCount: 5
nerTargetCount: 5
aiReviewTargetCount: 0
autoTargetCount: 10
reviewTargetCount: 0
```

Apply 결과 요약:

```text
totalLocations: 9
appliedLocations: 9
partialLocations: 0
skippedLocations: 0
totalWarnings: 0
autoTargetCount: 10
reviewTargetCount: 0
```

의미:

```text
문자열 셀 12개 순회
regex target 5건 탐지
NER 성명 target 5건 탐지
AI review target 0건 생성
auto target 10건이 9개 location에 적용
모든 auto target 적용 성공
```

한 셀에 target이 2개 있는 경우가 있어 `autoTargetCount`와 `totalLocations`는 다르다.

예:

```text
민원처리 탭 A3 셀
→ 이메일 주소 + 성명
→ appliedTargetCount = 2
```

---

## 10. 실제 적용 예시

실제 xlsx 통합 테스트에서 확인된 적용 예시는 다음과 같다.

```text
민원처리 탭 A1 셀
원문: 담당자 이메일은 test@example.com입니다.
결과: 담당자 이메일은 ****************입니다.
```

```text
민원처리 탭 A2 셀
원문: 직원 김도윤의 서류를 검토했습니다.
결과: 직원 ***의 서류를 검토했습니다.
```

```text
민원처리 탭 A3 셀
원문: 담당자 김도윤의 이메일은 test@example.com입니다.
결과: 담당자 ***의 이메일은 ****************입니다.
```

```text
민원처리 탭 A4 셀
원문: 서버 IP는 192.168.0.1입니다.
결과(delete): 서버 IP는 입니다.
결과(mark): 서버 IP는 (삭제됨)입니다.
```

```text
계약내역 탭 A1 셀
원문: 계약 담당자 김도윤
결과: 계약 담당자 ***
```

---

## 11. regex_detector.py 단일 소스 사용

초기 `14_test_real_xlsx_detection_apply.py`에는 스크립트 내부에 별도 `REGEX_RULES`가 하드코딩되어 있었다. 이 방식은 `src/regex_detector.py`와 규칙이 불일치할 수 있어 위험하다.

실제로 내부 IP 주소 `192.168.0.1` 탐지에서 문제가 확인되었다.

원인:

```text
regex_detector.py에는 개선된 IP 패턴이 있음
14_test_real_xlsx_detection_apply.py는 별도 REGEX_RULES를 사용함
두 규칙이 불일치하여 실제 통합 테스트에서 IP 탐지가 누락될 수 있음
```

수정 방향:

```text
14_test_real_xlsx_detection_apply.py 내부 REGEX_RULES 제거
src/regex_detector.py를 import하여 공통 정규식 탐지기를 사용
regex_detector.py 반환값을 DeidentifyTarget으로 변환하는 adapter 추가
```

수정 후에는 정규식 규칙의 단일 소스가 `regex_detector.py`가 된다.

```text
정규식 패턴 수정 위치:
src/regex_detector.py
```

`14_test_real_xlsx_detection_apply.py`는 더 이상 자체 정규식 목록을 관리하지 않는다.

---

## 12. IP 탐지 및 삭제 표시 확인

`regex_detector.py`의 내부 IP 패턴은 다음 구조를 사용한다.

```python
r"(?<![\d.])"
r"(10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
r"|192\.168\.\d{1,3}\.\d{1,3})"
r"(?![\d.])"
```

이 패턴은 한글 조사나 문장 어미가 뒤에 붙어도 IP를 탐지할 수 있다.

예:

```text
서버 IP는 192.168.0.1입니다.
→ 192.168.0.1 탐지
```

통합 테스트에서 `192.168.0.1` 탐지 및 삭제 동작을 확인했다.

```text
delete 모드:
서버 IP는 192.168.0.1입니다.
→ 서버 IP는 입니다.

mark 모드:
서버 IP는 192.168.0.1입니다.
→ 서버 IP는 (삭제됨)입니다.
```

삭제 표시가 필요한 사용자 검토/preview 단계에서는 `--deletion-mode mark`를 사용한다.

---

## 13. debug-cells 옵션 추가

실제 xlsx 통합 테스트에서는 탐지 결과가 없는 셀은 `autoResults`나 `reviewTargets`에 표시되지 않는다. 따라서 셀이 순회되었는지, 탐지가 0건이었는지 확인하기 어렵다.

이를 보완하기 위해 `--debug-cells` 옵션을 추가했다.

실행 예:

```bash
python notebooks/14_test_real_xlsx_detection_apply.py "data\xlsx_test1.xlsx" \
  --ner-model-path "models\hf\KoELECTRA-small-v3-modu-ner" \
  --ai-model-path "models\privacy_cso_char_keras_model.keras" \
  --debug-cells
```

예상 출력:

```text
[Cell] 민원처리 탭 A4 셀: '서버 IP는 192.168.0.1입니다.'
  regex=1, ner=0, ai=0
    - regex/내부 IP 주소: 192.168.0.1 (7,18)
```

이 옵션은 순회 누락과 탐지 미발생을 구분하는 데 유용하다.

---

## 14. AI review 결과 해석

실제 통합 테스트에서 AI review target은 0건이었다.

```text
aiReviewTargetCount: 0
reviewTargetCount: 0
```

이는 AI 모델이 모든 셀을 `O`로 판단했거나, `C/S` 확률이 `ai_threshold` 기본값인 0.6 미만이었다는 뜻이다.

8주차 Keras 모델은 확신도가 낮고 등급별 경계가 불안정한 상태였으므로, 이 결과는 이상 동작으로 보지 않는다.

AI review 생성 흐름만 확인하려면 threshold를 낮춰 테스트할 수 있다.

```bash
python notebooks/14_test_real_xlsx_detection_apply.py "data\xlsx_test1.xlsx" \
  --ner-model-path "models\hf\KoELECTRA-small-v3-modu-ner" \
  --ai-model-path "models\privacy_cso_char_keras_model.keras" \
  --ai-threshold 0.4
```

다만 이 테스트의 목적은 모델 성능 평가가 아니라 파이프라인 연결 검증이다.

---

## 15. 12주차 완료 범위

12주차에서 완료한 범위는 다음과 같다.

```text
1. xlsx Apply 설계 문서 작성
2. CommonApplyResult 구조 구현
3. xlsx 파일 셀 단위 Apply 구현
4. TC 기반 xlsx Apply 테스트 작성 및 통과
5. 실제 xlsx 파일 기반 regex + NER + AI 통합 테스트 작성
6. regex_detector.py를 단일 정규식 소스로 사용하도록 수정
7. IP 탐지 및 삭제/표시 동작 확인
8. deletion_mode delete/mark 분리 확인
9. 병합 셀 처리 오류 수정
10. summary 정합성 검증
```

---

## 16. 12주차 범위 밖 작업

12주차에서는 다음 작업은 하지 않았다.

```text
docx Apply
pptx Apply
hwpx Apply
pdf/hwp Apply
프론트엔드 실제 연결
reviewTargets 사용자 승인 후 재적용
파일 diff 편집 UI
```

`pdf`, `hwp`는 향후 parsing 대상에는 포함하지만, 원본 파일 비식별화 Apply는 선택 과제로 둔다.

---

## 17. 다음 단계

다음 단계는 `docx` Apply PoC이다.

추천 진행 방향:

```text
13주차:
docx 문단 단위 Apply PoC

14주차:
pptx shape/text 단위 Apply PoC

15주차 이후:
hwpx Apply 검토
pdf/hwp parsing 가능성 검토
```

파일 형식별 Apply 방식은 다르지만, 최종 결과는 모두 `CommonApplyResult`로 통일한다.

```text
apply_plan_to_xlsx() → CommonApplyResult
apply_plan_to_docx() → CommonApplyResult
apply_plan_to_pptx() → CommonApplyResult
apply_plan_to_hwpx() → CommonApplyResult
```

이 구조를 유지하면 프론트엔드는 파일 형식별 내부 구조에 크게 의존하지 않아도 된다.

---

## 18. 결론

12주차에서는 xlsx 파일에 대한 실제 비식별화 Apply PoC를 완료했다.

핵심 성과는 다음과 같다.

```text
실제 xlsx 파일
→ regex + NER + AI 탐지
→ DeidentifyPlan 생성
→ xlsx Apply
→ 비식별화된 xlsx 파일 저장
```

또한 정규식 탐지는 `regex_detector.py`를 단일 소스로 사용하도록 정리했다. 이로써 이후 정규식 패턴 보완 시 한 파일만 수정하면 된다.

삭제 action은 실제 저장용과 사용자 확인용을 분리했다.

```text
delete: 실제 삭제
mark: (삭제됨) 표시
```

현재 기준으로 12주차 목표는 완료되었다.
