# 9주차 한국어 NER 어댑터 설계

## 1. 목적

9주차의 목적은 공개 한국어 NER 모델의 출력 결과를 우리 개인정보/민감정보 탐지 프로그램에서 사용할 수 있는 공통 구조로 표준화하는 것이다.

8주차까지는 문장 전체를 입력받아 C/S/O 등급을 예측했다.

```text
문장 입력
→ 문장 전체 C/S/O 등급 예측
```

9주차부터는 문장 안의 특정 구간을 탐지하는 방향으로 확장한다.

```text
문장 입력
→ NER 모델 또는 규칙 기반 탐지
→ 성명 등 개체 구간 탐지
→ EntitySpan 표준 구조로 변환
→ Detection 구조와 연결
```

9주차에서는 여러 NER 개체를 모두 활용하지 않는다.

이번 주차의 핵심 목적은 다음이다.

```text
공개 한국어 NER 모델이 탐지한 사람 이름 후보를
우리 프로그램 내부 표준 라벨 PERSON으로 통합한다.
```

---

## 2. NER의 역할

NER은 Named Entity Recognition의 약자로, 문장 안에서 사람 이름, 기관명, 장소명 같은 개체를 찾아내는 작업이다.

예시:

```text
직원 김도윤의 감봉 처분 결과를 확인했습니다.
```

NER 결과:

```text
김도윤 → PERSON
```

문장분류와 NER의 차이는 다음과 같다.

| 구분 | 역할 |
|---|---|
| 문장분류 | 문장 전체가 C/S/O 중 어느 등급인지 판단 |
| NER | 문장 안의 특정 문자열이 어떤 개체인지 탐지 |

우리 프로그램에서 NER의 핵심 역할은 문장 전체 등급 판단이 아니라, 성명 후보의 위치를 찾는 것이다.

---

## 3. 9주차 지원 범위

9주차에서는 내부 표준 NER 라벨을 `PERSON` 하나로 제한한다.

```python
SUPPORTED_LABELS = {"PERSON"}
```

지원하는 것:

```text
성명 후보
```

지원하지 않는 것:

```text
기관명
장소명
조직명
부서명
직책
날짜
시간
```

기관명, 장소명, 조직명은 공개 NER 모델이 탐지할 수 있지만, 현재 프로그램의 비식별화 목적과 직접 연결되는 경우가 제한적이다.

예를 들어:

```text
인천교통공사에서 회의를 진행했습니다.
```

이 문장에서 `인천교통공사`를 기관명으로 탐지하더라도, 그것만으로 개인정보나 민감정보 조치 대상이라고 보기 어렵다.

따라서 9주차에서는 `ORG`, `LOC`, `DEPARTMENT` 등은 `EntitySpan`으로 만들지 않고 무시한다.

추후 필요성이 확인되면 확장한다.

---

## 4. 모델별 라벨 차이 문제

한국어 NER 모델마다 사람 이름 라벨이 다를 수 있다.

예시:

```text
PERSON
PER
PS
B-PER
I-PER
B-PS
I-PS
인명
```

우리 프로그램에서는 이 라벨들을 모두 내부 표준 라벨로 통합한다.

```text
PERSON
```

예:

```text
PER → PERSON
PS → PERSON
B-PS → PERSON
I-PS → PERSON
```

이 변환은 `korean_ner_adapter.py`에서 담당한다.

---

## 5. BIO 태그와 토큰 병합

NER 모델은 BIO 태그를 사용할 수 있다.

예를 들어 `김도윤`이 다음처럼 쪼개질 수 있다.

```text
김 → B-PS
도 → I-PS
윤 → I-PS
```

이 결과를 그대로 `EntitySpan` 3개로 만들면 안 된다.

올바른 결과는 다음처럼 하나의 구간이어야 한다.

```text
김도윤 → PERSON
```

Hugging Face `pipeline()`에서는 다음 옵션을 사용하면 토큰 병합을 자동으로 수행할 수 있다.

```python
aggregation_strategy="simple"
```

따라서 9주차 어댑터의 기본 입력 가정은 다음과 같다.

```text
Hugging Face pipeline 출력은 aggregation_strategy="simple" 이상을 사용해
이미 병합된 결과라고 가정한다.
```

예상 입력:

```python
{
    "entity_group": "PS",
    "word": "김도윤",
    "start": 3,
    "end": 6,
    "score": 0.98,
}
```

다만 raw 모델 출력을 직접 처리할 가능성에 대비해 `B-`, `I-` 접두사 제거와 라벨 매핑은 유지한다.

---

## 6. EntitySpan 역할

`EntitySpan`은 여러 NER 모델의 서로 다른 출력 결과를 우리 프로그램에서 공통으로 다루기 위한 표준 중간 구조이다.

예상 구조:

```python
@dataclass
class EntitySpan:
    label: str
    text: str
    start: int
    end: int
    source: str
    confidence: float | None = None
    original_label: str | None = None
```

각 필드의 의미는 다음과 같다.

| 필드 | 의미 |
|---|---|
| `label` | 우리 내부 표준 라벨. 9주차에서는 `PERSON` |
| `text` | 탐지된 문자열 |
| `start` | 원문 내 시작 위치 |
| `end` | 원문 내 끝 위치 |
| `source` | 탐지 출처. 예: `hf_ner`, `rule_ner` |
| `confidence` | 모델 신뢰도 |
| `original_label` | 모델 원본 라벨. 예: `PS`, `B-PER` |

예:

```python
EntitySpan(
    label="PERSON",
    text="김도윤",
    start=3,
    end=6,
    source="hf_ner",
    confidence=0.98,
    original_label="PS",
)
```

`EntitySpan`은 최종 보안 판단 결과가 아니다.

```text
EntitySpan
→ 모델이 무엇을 어디에서 찾았는가

Detection
→ 이것을 개인정보/민감정보로 보고 어떤 등급과 조치를 적용할 것인가
```

---

## 7. 어댑터 역할

`korean_ner_adapter.py`는 모델별 출력 차이를 `EntitySpan`으로 바꾸는 역할을 한다.

처리 흐름:

```text
Hugging Face NER 원본 출력
→ 원본 라벨 추출
→ PERSON 계열인지 확인
→ 내부 표준 라벨 PERSON으로 변환
→ EntitySpan 생성
```

라벨 매핑 예:

```python
PERSON_LABEL_ALIASES = {
    "PERSON",
    "PER",
    "PS",
    "인명",
}
```

`B-PER`, `I-PER`, `B-PS`, `I-PS`처럼 BIO 접두사가 있는 경우에는 접두사를 제거한 뒤 매핑한다.

지원하지 않는 라벨은 `None`을 반환한다.

```python
normalize_label("ORG")  # None
normalize_label("LOC")  # None
normalize_label("PS")   # "PERSON"
```

---

## 8. confidence 임계값 정책

`EntitySpan.confidence`는 모델 신뢰도를 보존하기 위한 필드이다.

9주차에서는 어댑터 단계에서 confidence 임계값을 적용하지 않는다.

즉, confidence가 낮아도 `PERSON` 라벨로 정규화 가능하면 `EntitySpan`으로 변환한다.

임계값은 Detection 변환 단계에서 적용한다.

초기 정책:

```python
NER_CONFIDENCE_THRESHOLD = 0.85
```

정책:

```text
어댑터:
confidence를 보존한다.

Detection 변환 단계:
confidence가 threshold 미만이면 Detection 생성 보류 또는 검토 필요 처리
```

이렇게 분리하는 이유는 다음과 같다.

```text
1. threshold를 바꿔도 NER 모델을 다시 실행할 필요가 없다.
2. 낮은 confidence 결과도 분석용으로 남길 수 있다.
3. 모델별 confidence 경향을 비교할 수 있다.
```

---

## 9. 탐지 우선순위

9주차 이후 탐지 결과 병합 시 다음 우선순위를 적용한다.

```text
1순위: regex
2순위: ner
3순위: ai
```

| 우선순위 | source | 역할 |
|---|---|---|
| 1 | `regex` | 이메일, 전화번호, 사번, IP, VLAN 등 패턴형 정보 |
| 2 | `ner` | 성명 등 개체형 정보 |
| 3 | `ai` | 문장 전체 문맥형 판단 |

동일하거나 겹치는 위치에서 탐지가 발생하면 상위 tier를 우선한다.

예:

```text
regex와 ner가 같은 위치를 탐지
→ regex 우선

ner가 성명을 탐지하고 ai가 문장 전체를 S로 판단
→ ner 결과는 성명 Detection으로 유지
→ ai 결과는 문맥 판단으로 보조 사용
```

이 정책은 10주차 Detection 병합 단계에서 활용한다.

---

## 10. EntitySpan에서 Detection으로의 연결

NER 결과가 `PERSON`이면 이후 Detection으로 변환할 수 있다.

예:

```python
EntitySpan(
    label="PERSON",
    text="김도윤",
    start=3,
    end=6,
    source="hf_ner",
    confidence=0.98,
    original_label="PS",
)
```

Detection 변환 예:

```python
Detection(
    label="성명",
    matched="김도윤",
    grade="S",
    action="마스킹",
    source="ner",
    context=text_unit.text,
    location_label=text_unit.location_label,
    location_meta=text_unit.location_meta,
    start=3,
    end=6,
    reason="NER 모델이 PERSON 개체로 탐지",
)
```

즉, NER은 “찾는 역할”을 하고, C/S/O 등급과 조치 방식은 우리 규칙 엔진이 결정한다.

---

## 11. 9주차 산출물

9주차 산출물은 다음과 같다.

```text
reports/week9_korean_ner_adapter_design.md
src/ner_units.py
src/korean_ner_adapter.py
notebooks/08_test_korean_ner_adapter.py
```

각 파일의 역할:

| 파일 | 역할 |
|---|---|
| `week9_korean_ner_adapter_design.md` | 9주차 설계 결정사항 정리 |
| `ner_units.py` | `EntitySpan` 표준 구조 정의 |
| `korean_ner_adapter.py` | 모델별 라벨을 PERSON으로 정규화 |
| `08_test_korean_ner_adapter.py` | 가짜 Hugging Face NER 출력으로 어댑터 테스트 |

실제 Hugging Face 모델 연결은 어댑터 구조가 안정된 뒤 선택적으로 진행한다.

---

## 12. 결론

9주차에서는 한국어 NER 모델 전체를 개인정보 탐지기로 사용하지 않는다.

핵심은 다음이다.

```text
공개 NER 모델의 PERSON 탐지 결과만 성명 후보로 활용한다.
모델별 라벨 차이는 korean_ner_adapter.py에서 통합한다.
통합 결과는 EntitySpan으로 표준화한다.
EntitySpan은 이후 Detection으로 변환된다.
```

최종 구조:

```text
모델별 NER 출력
→ korean_ner_adapter.py
→ EntitySpan
→ Detection
```

이 구조를 통해 공개 NER 모델을 우리 프로그램에 안정적으로 연결할 수 있다.
