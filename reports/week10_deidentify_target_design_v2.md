# 10주차 비식별화 대상 계획 수립 설계 및 테스트 결과 v2

## 1. 목적

10주차의 목적은 regex, ner, ai 탐지 결과를 문서 위치 기준으로 정리하여 실제 비식별화 작업에 사용할 계획을 만드는 것이다.

10주차에서는 실제 문서 원문을 수정하지 않는다.

```text
10주차:
비식별화 계획 수립, Plan

11주차 이후:
계획에 따른 원문 수정, Apply
```

따라서 10주차의 핵심 산출물은 문서 전체 등급이 아니라 다음이다.

```text
어디를
무엇으로 보고
어떤 방식으로
비식별화해야 하는가
```

---

## 2. 입력과 출력

입력은 이미 생성된 Detection 목록이다.

예:

```python
{
    "label": "이메일 주소",
    "matched": "test@example.com",
    "grade": "S",
    "action": "마스킹",
    "source": "regex",
    "context": "담당자 이메일은 test@example.com입니다.",
    "locationLabel": "계약내역 탭 B12 셀",
    "locationMeta": {
        "fileType": "xlsx",
        "sheetName": "계약내역",
        "cellRef": "B12",
        "row": 12,
        "col": 2
    },
    "start": 9,
    "end": 25,
    "reason": "직접 식별 가능한 개인정보"
}
```

출력은 `DeidentifyPlan`이다.

```python
DeidentifyPlan(
    auto_targets=[...],
    review_targets=[...],
    summary_grade="C"
)
```

다만 `summary_grade`는 부가 요약값이다. 핵심은 `auto_targets`와 `review_targets`이다.

---

## 3. DeidentifyTarget

`DeidentifyTarget`은 실제 비식별화 계획 단위이다.

구현 파일:

```text
src/deidentify_target_builder.py
```

구조:

```python
@dataclass
class DeidentifyTarget:
    label: str
    matched: str
    action: str
    location_label: str | None
    location_meta: dict
    start: int | None
    end: int | None
    source: str
    reason: str
    grade: str | None = None
    sensitive_type: str | None = None
    sensitive_category: str | None = None
    context: str | None = None
    order: int = 0
```

Detection과 DeidentifyTarget의 차이는 다음과 같다.

| 구조 | 역할 |
|---|---|
| Detection | 탐지 결과 전체 |
| DeidentifyTarget | 실제 비식별화 또는 검토 대상 |

---

## 4. DeidentifyPlan

10주차 결과는 단일 리스트가 아니라 `DeidentifyPlan`으로 반환한다.

```python
@dataclass
class DeidentifyPlan:
    auto_targets: list[DeidentifyTarget]
    review_targets: list[DeidentifyTarget]
    summary_grade: str | None = None
```

구분 기준:

| 구분 | 의미 |
|---|---|
| `auto_targets` | start/end와 matched가 있어 자동 비식별화 가능한 대상 |
| `review_targets` | AI 문장판단 등 자동 수정 전에 검토가 필요한 대상 |
| `summary_grade` | 부가 요약값. 핵심 산출물은 아님 |

`summary_grade`는 입력 Detection 전체가 아니라, 최종 `auto_targets`와 `review_targets`에 남은 target 기준으로 계산한다. `grade=None`인 target은 summary 계산에서 제외한다.

---

## 5. 자동 비식별화 대상과 검토 필요 대상

### 자동 비식별화 대상

다음 조건을 만족하면 `auto_targets`로 분류한다.

```text
matched가 있음
start/end가 있음
source가 regex 또는 ner
```

예:

```text
이메일
전화번호
성명
사번
내부 IP
VLAN
```

### 검토 필요 대상

다음 조건은 `review_targets`로 분류한다.

```text
start/end가 없음
matched가 없거나 문장 전체 판단임
source가 ai
```

예:

```text
입찰 평가표를 검토했습니다.
계약 단가 비교표를 첨부했습니다.
특정 역 사고 이력 원자료를 첨부했습니다.
```

---

## 6. 탐지 source 우선순위

중복 탐지 또는 겹침 탐지가 발생하면 다음 우선순위를 적용한다.

```text
regex > ner > ai
```

| 우선순위 | source | 역할 |
|---|---|---|
| 1 | regex | 이메일, 전화번호, 사번, IP, VLAN 등 패턴형 정보 |
| 2 | ner | 성명 등 개체형 정보 |
| 3 | ai | 문장 전체 문맥형 판단 |

---

## 7. 위치 겹침 판정

위치 겹침은 `start`, `end`를 기준으로 판단한다.

```python
def spans_overlap(a_start, a_end, b_start, b_end) -> bool:
    if a_start is None or b_start is None:
        return False
    return a_start < b_end and b_start < a_end
```

중요한 점:

```text
인접한 구간은 겹침이 아니다.
예: (3, 6)과 (6, 10)은 겹치지 않음
```

겹침 케이스:

| 케이스 | 예시 | 처리 |
|---|---|---|
| 완전 동일 | regex 김도윤 (3,6), ner 김도윤 (3,6) | 우선순위 높은 source 유지 |
| 부분 겹침 | regex test@example.com (9,25), ner test (9,13) | regex 유지 |
| 포함 관계 | ner 홍가람 민원인 (0,8) | 10주차에서는 그대로 두고 향후 후처리 과제 |
| 인접 | ner 김도윤 (3,6), regex email (6,20) | 둘 다 유지 |

AI Detection은 `start/end=None`일 수 있으므로 위치 겹침 판정 대상에서 제외한다.

### 위치 동일성 판정 기준

같은 위치인지 판단할 때는 `locationLabel`보다 `locationMeta`를 우선 사용한다.

`locationLabel`은 사용자 표시용 문자열이므로, 문서 파서 또는 UI 표현 방식이 바뀌면 동일 위치 비교가 흔들릴 수 있다. 반면 `locationMeta`는 11주차 Apply 단계에서 실제 원문 위치를 찾아가는 기준이므로, 겹침 판정에서도 우선 사용한다.

판정 순서는 다음과 같다.

```python
def same_location(a, b):
    a_meta = a.get("locationMeta")
    b_meta = b.get("locationMeta")

    if a_meta and b_meta:
        return a_meta == b_meta

    a_location = a.get("locationLabel")
    b_location = b.get("locationLabel")

    if a_location is not None or b_location is not None:
        return a_location == b_location

    return a.get("context") == b.get("context")
```

즉, 위치 비교 우선순위는 다음과 같다.

```text
locationMeta → locationLabel → context
```

---

## 8. 겹침 Detection 선택 기준

겹침 Detection이 발생하면 다음 통합 우선순위를 적용한다.

```text
1. source 우선순위
   regex > ner > ai

2. grade 우선순위
   C > S > O

3. matched 길이
   긴 쪽 우선

4. 입력 순서
   먼저 들어온 Detection 우선
```

이 기준은 서로 다른 source 간 겹침과 같은 source 내 겹침에 모두 적용한다.

예를 들어 regex와 ner가 같은 위치를 탐지하면 source 우선순위에 따라 regex를 유지한다.

```text
regex: test@example.com (9,25)
ner:   test (9,13)

결과:
regex 유지
ner 흡수
```

같은 source 안에서 겹침이 발생하면 source 우선순위가 같으므로 grade, matched 길이, 입력 순서 순으로 비교한다.

---

## 9. reason 누적 정책

겹친 Detection을 제거할 때 완전히 버리지 않고, 유지되는 target의 reason에 흡수 정보를 남긴다.

예:

```text
정규식 이메일 탐지 / 중복 탐지 흡수: source=ner, label=성명 후보, matched=test
```

이렇게 하면 나중에 왜 특정 탐지 결과만 남았는지 추적하기 쉽다.

TC4, TC9 테스트에서 이 정책이 정상 동작하는 것을 확인했다.

---

## 10. 정렬 규칙

10주차의 정렬은 사용자 표시와 계획 검토를 위한 정렬이다.

정렬 기준은 다음과 같다.

```text
1. location의 첫 등장 순서
2. 같은 location 내부에서는 start 오름차순
3. start가 None인 target은 같은 location의 뒤쪽
```

location을 묶는 기준은 `same_location()`과 동일하게 `locationMeta → locationLabel → context` 순서를 따른다.

예를 들어 입력 순서가 다음과 같더라도:

```text
[0] location=A, start=10
[1] location=B, start=5
[2] location=A, start=3
```

표시 순서는 다음과 같이 정리한다.

```text
location=A, start=3
location=A, start=10
location=B, start=5
```

다만 11주차 Apply 단계에서 실제 문자열 치환을 수행할 때는 같은 location 내부에서 `start 내림차순`으로 적용해야 한다. 앞쪽 문자열을 먼저 치환하면 뒤쪽 start/end 위치가 어긋날 수 있기 때문이다.

```text
10주차 표시 정렬:
location 순서 → start 오름차순

11주차 적용 순서:
같은 location 내부 → start 내림차순
```

---

## 11. 구현 파일

10주차 구현 파일은 다음이다.

```text
src/deidentify_target_builder.py
notebooks/11_test_deidentify_target_builder.py
```

`src/deidentify_target_builder.py`의 주요 구성은 다음과 같다.

```text
DeidentifyTarget dataclass
DeidentifyPlan dataclass
spans_overlap()
same_location()
source_priority()
grade_priority()
choose_better_detection()
deduplicate_auto_detections()
detection_to_target()
sort_targets()
calculate_summary_grade_from_targets()
build_deidentify_plan()
```

`notebooks/11_test_deidentify_target_builder.py`는 TC1~TC10 시나리오를 검증한다.

테스트 헬퍼 함수명은 의미가 드러나도록 다음과 같이 정리했다.

```python
make_detection()
make_ai_detection()
```

---

## 12. 테스트 케이스와 결과 요약

10주차 테스트 스크립트는 다음 시나리오를 확인했다.

| ID | 시나리오 | 기대 결과 | 결과 |
|---|---|---|---|
| TC1 | regex만 있는 TextUnit | auto_targets 1개 | 정상 |
| TC2 | ner만 있는 TextUnit | auto_targets 1개 | 정상 |
| TC3 | ai만 있는 TextUnit | review_targets 1개 | 정상 |
| TC4 | regex + ner 같은 위치 | regex만 auto_targets 1개 | 정상 |
| TC5 | regex + ai 같은 TextUnit | auto 1개, review 1개 | 정상 |
| TC6 | ner + ai 같은 TextUnit | auto 1개, review 1개 | 정상 |
| TC7 | 빈 Detection 목록 | 빈 결과 | 정상 |
| TC8 | 같은 TextUnit에 regex 2개 | auto_targets 2개 | 정상 |
| TC9 | 부분 겹침 regex 이메일 + ner 오탐 | regex만 auto_targets 1개 | 정상 |
| TC10 | 같은 location에 regex 2개가 start 역순으로 입력됨 | start 오름차순으로 출력 | 정상 |

---

## 13. 주요 테스트 결과

### TC1. regex만 있는 TextUnit

```text
summary_grade: S
auto_targets: 1
  - [regex] 이메일 주소 / test@example.com (9,25)
review_targets: 0
```

regex 기반 탐지는 start/end와 matched가 있으므로 자동 비식별화 대상으로 분류되었다.

### TC2. ner만 있는 TextUnit

```text
summary_grade: S
auto_targets: 1
  - [ner] 성명 / 김도윤 (3,6)
review_targets: 0
```

NER 기반 성명 탐지도 start/end와 matched가 있으므로 자동 비식별화 대상으로 분류되었다.

### TC3. ai만 있는 TextUnit

```text
summary_grade: S
auto_targets: 0
review_targets: 1
  - [ai] 민감정보 / 문장 전체 (None,None)
```

AI Detection은 문장 전체 판단이며 start/end가 없으므로 검토 필요 대상으로 분류되었다.

### TC4. regex + ner 같은 위치

```text
summary_grade: S
auto_targets: 1
  - [regex] 이름 패턴 / 김도윤 (3,6)
    reason=정규식 탐지 / 중복 탐지 흡수: source=ner, label=성명 후보, matched=김도윤
review_targets: 0
```

같은 위치에서 regex와 ner가 동시에 탐지된 경우, source 우선순위에 따라 regex를 유지하고 ner를 흡수했다.

### TC5. regex + ai 같은 TextUnit

```text
auto_targets: 1
  - [regex] 이메일 주소 / test@example.com
review_targets: 1
  - [ai] 민감정보 / 문장 전체
```

regex는 자동 비식별화 대상, ai는 검토 필요 대상으로 분리되었다.

### TC6. ner + ai 같은 TextUnit

```text
auto_targets: 1
  - [ner] 성명 / 김도윤
review_targets: 1
  - [ai] 민감정보 / 문장 전체
```

NER 성명 탐지는 자동 비식별화 대상, AI 문장 판단은 검토 필요 대상으로 분리되었다.

### TC7. 빈 Detection 목록

```text
summary_grade: None
auto_targets: 0
review_targets: 0
```

탐지 결과가 없으면 빈 계획을 생성한다.

### TC8. 같은 TextUnit에 regex 2개

```text
summary_grade: C
auto_targets: 2
  - [regex] 이메일 주소 / test@example.com (9,25)
  - [regex] 내부 IP 주소 / 192.168.0.1 (35,46)
review_targets: 0
```

서로 위치가 겹치지 않는 regex 탐지는 모두 유지된다.

### TC9. 부분 겹침 regex 이메일 + ner PERSON 일부 오탐

```text
summary_grade: S
auto_targets: 1
  - [regex] 이메일 주소 / test@example.com (9,25)
    reason=정규식 이메일 탐지 / 중복 탐지 흡수: source=ner, label=성명 후보, matched=test
review_targets: 0
```

부분 겹침이 발생한 경우에도 source 우선순위에 따라 regex를 유지하고 ner 오탐을 제거했다.

### TC10. 같은 location에 regex 2개가 start 역순으로 입력

```text
입력 순서:
1. 내부 IP 주소 / 192.168.0.1 (35,46)
2. 이메일 주소 / test@example.com (9,25)

출력 순서:
1. 이메일 주소 / test@example.com (9,25)
2. 내부 IP 주소 / 192.168.0.1 (35,46)
```

같은 location 내부에서는 입력 순서가 아니라 start 오름차순으로 정렬되는 것을 확인했다.

---

## 14. 구현 중 수정한 사항

초기 구현에서는 TC4와 TC9에서 중복 제거 후에도 동일한 regex target이 두 번 출력되는 문제가 있었다.

원인은 `deduplicate_auto_detections()`에서 겹침이 발생했음에도 candidate를 다시 append하는 흐름이 남아 있었기 때문이다.

수정 후 로직은 다음과 같다.

```text
겹침 없음
→ candidate append

겹침 있음
→ current와 candidate 중 더 적절한 Detection만 kept에 유지
→ candidate를 새로 append하지 않음
```

수정 후 TC4와 TC9 모두 `auto_targets: 1`로 정상 동작했다.

또한 테스트 헬퍼 함수명도 명확하게 변경했다.

```text
d() → make_detection()
ai_detection() → make_ai_detection()
```

추가 보완 사항은 다음과 같다.

```text
1. same_location()에서 locationMeta를 우선 비교하도록 수정했다.
2. sort_targets()를 location 첫 등장 순서 + 같은 location 내 start 오름차순 기준으로 수정했다.
3. summary_grade를 입력 Detection 전체가 아니라 최종 auto/review target 기준으로 계산하도록 수정했다.
4. 겹침 Detection 선택 기준을 source → grade → matched 길이 → 입력 순서의 통합 우선순위로 정리했다.
5. TC10을 추가하여 같은 location 내 정렬이 정상 동작하는지 검증했다.
```

---

## 15. 현재 10주차 완료 범위

완료된 범위는 다음과 같다.

```text
1. Detection 목록 입력
2. auto_targets / review_targets 분리
3. regex > ner > ai 우선순위 적용
4. start/end 겹침 제거
5. 같은 source 내 겹침 처리 기준 구현
6. reason 누적 정책 구현
7. locationMeta 우선 위치 비교
8. 같은 location 내 start 오름차순 정렬
9. 최종 target 기준 summary_grade 계산
10. TC1~TC10 테스트 통과
```

아직 하지 않은 것:

```text
1. 실제 문서 원문 수정
2. xlsx/docx/pptx/hwpx 파일에 마스킹 적용
3. App.jsx 문서 파서와 직접 연결
4. 프론트엔드 표시 UI 구현
```

이 작업들은 11주차 이후의 Apply 단계에서 다루는 것이 적절하다.

---

## 16. 결론

10주차의 핵심은 문서 전체 등급 산정이 아니다.

핵심은 다음이다.

```text
비식별화해야 하는 데이터의 위치와 조치 방식을 확정하는 것
```

최종 흐름:

```text
Detection 목록
→ 중복/겹침 정리
→ 자동 비식별화 대상과 검토 필요 대상 분리
→ DeidentifyPlan 생성
```

이번 주차를 통해 regex, ner, ai 탐지 결과를 실제 비식별화 작업 전 단계에서 사용할 수 있는 계획 구조로 정리할 수 있게 되었다.

---

## 17. 다음 단계

다음 단계는 실제 비식별화 적용, 즉 Apply 단계이다.

검토할 작업은 다음과 같다.

```text
1. DeidentifyPlan을 기반으로 원문 문자열 마스킹
2. start/end 기준 문자열 치환
3. xlsx 셀 단위 마스킹 적용
4. docx 문단 단위 마스킹 적용
5. pptx 텍스트 단위 마스킹 적용
6. locationMeta를 이용한 원문 위치 추적
7. 자동 비식별화 대상과 검토 필요 대상을 UI에서 분리 표시
```

11주차 Apply 단계에서 주의할 점은 다음과 같다.

```text
1. 같은 TextUnit 또는 같은 location 내 target은 start 내림차순으로 적용한다.
2. 같은 TextUnit 내 모든 auto_target을 한 번에 처리한다.
3. review_targets는 자동 적용하지 않고 사용자 검토 대상으로 분리한다.
4. xlsx, docx, pptx, hwpx는 파일 구조가 다르므로 fileType별 Apply 함수를 분리한다.
5. 우선 단일 문자열 또는 단일 파일 형식부터 PoC로 구현한 뒤 확장한다.
```

특히 문자열 치환은 앞쪽부터 적용하면 뒤쪽 target의 start/end가 어긋날 수 있으므로, 같은 location 내부에서는 반드시 뒤쪽 target부터 적용해야 한다.

11주차 이후의 핵심은 다음이다.

```text
DeidentifyPlan
→ 실제 문서 원문 수정
→ 비식별화된 문서 생성
```
