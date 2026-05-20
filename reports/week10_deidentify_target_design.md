# 10주차 비식별화 대상 계획 수립 설계

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

---

## 8. 같은 source 내 겹침 처리

같은 source 안에서도 겹침이 생길 수 있다.

예:

```text
phone 패턴과 다른 숫자 패턴이 같은 구간을 잡는 경우
```

같은 source 내 겹침은 다음 기준으로 처리한다.

```text
1. 등급이 높은 Detection 유지
2. 등급이 같으면 matched 길이가 긴 Detection 유지
3. 그래도 같으면 먼저 들어온 Detection 유지
```

등급 우선순위:

```text
C > S > O
```

---

## 9. reason 누적 정책

겹친 Detection을 제거할 때 완전히 버리지 않고, 유지되는 target의 reason에 흡수 정보를 남긴다.

예:

```text
직접 식별 가능한 개인정보 / 중복 탐지 흡수: source=ner, label=성명, matched=김도윤
```

이렇게 하면 나중에 왜 특정 탐지 결과만 남았는지 추적하기 쉽다.

---

## 10. 정렬 규칙

10주차에서는 별도 문서 순서 계산을 새로 만들지 않는다.

정렬 정책은 다음과 같다.

```text
1. 입력 Detection 순서, 즉 TextUnit 처리 순서를 우선한다.
2. 같은 location에서는 start 오름차순으로 정렬한다.
3. start가 None인 AI Detection은 해당 TextUnit의 뒤쪽에 둔다.
```

이를 위해 `order` 필드를 둔다.

---

## 11. 테스트 케이스

10주차 테스트 스크립트에서는 다음 시나리오를 확인한다.

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC1 | regex만 있는 TextUnit | auto_targets 1개 |
| TC2 | ner만 있는 TextUnit | auto_targets 1개 |
| TC3 | ai만 있는 TextUnit | review_targets 1개 |
| TC4 | regex + ner 같은 위치 | regex만 auto_targets 1개 |
| TC5 | regex + ai 같은 TextUnit | auto 1개, review 1개 |
| TC6 | ner + ai 같은 TextUnit | auto 1개, review 1개 |
| TC7 | 빈 Detection 목록 | 빈 결과 |
| TC8 | 같은 TextUnit에 regex 2개 | auto_targets 2개 |
| TC9 | 부분 겹침 regex 이메일 + ner 오탐 | regex만 유지 |

---

## 12. 산출물

10주차 산출물은 다음과 같다.

```text
reports/week10_deidentify_target_design.md
src/deidentify_target_builder.py
notebooks/11_test_deidentify_target_builder.py
```

---

## 13. 결론

10주차의 핵심은 문서 전체 등급이 아니다.

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
