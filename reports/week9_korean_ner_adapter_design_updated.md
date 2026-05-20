# 9주차 한국어 NER 어댑터 설계 및 Detection 변환

## 1. 목적

9주차의 목적은 공개 한국어 NER 모델의 출력 결과를 우리 개인정보/민감정보 탐지 프로그램에서 사용할 수 있는 공통 구조로 표준화하고, 성명 후보를 최종 Detection 형태로 변환하는 것이다.

8주차까지는 문장 전체를 입력받아 C/S/O 등급을 예측했다.

```text
문장 입력
→ 문장 전체 C/S/O 등급 예측
```

9주차에서는 문장 안의 특정 구간을 탐지하는 구조로 확장했다.

```text
문장 입력
→ 한국어 NER 모델
→ 성명 후보 탐지
→ EntitySpan 표준 구조로 변환
→ Detection dict로 변환
```

최종 흐름은 다음과 같다.

```text
Hugging Face NER output
→ korean_ner_adapter.py
→ EntitySpan
→ ner_detection_converter.py
→ Detection
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

우리 프로그램에서 NER의 핵심 역할은 문장 전체 등급 판단이 아니라, **성명 후보의 위치를 찾는 것**이다.

---

## 3. 9주차 지원 범위

9주차에서는 내부 표준 NER 라벨을 `PERSON` 하나로 제한했다.

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

따라서 9주차에서는 `ORG`, `LOC`, `OG`, `TM`, `QT` 등 PERSON이 아닌 라벨은 `EntitySpan`으로 만들지 않고 무시한다.

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

이 변환은 `src/korean_ner_adapter.py`에서 담당한다.

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

구현 파일:

```text
src/ner_units.py
```

구조:

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
    confidence=0.9812,
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

## 7. 한국어 NER 어댑터

구현 파일:

```text
src/korean_ner_adapter.py
```

역할:

```text
Hugging Face NER 원본 출력
→ 원본 라벨 추출
→ PERSON 계열인지 확인
→ 내부 표준 라벨 PERSON으로 변환
→ EntitySpan 생성
```

주요 정책:

```text
1. PERSON 계열 라벨만 변환한다.
2. ORG, LOC, OG, TM, QT 등은 무시한다.
3. confidence는 어댑터에서 자르지 않고 보존한다.
4. confidence threshold는 Detection 변환 단계에서 적용한다.
```

테스트 스크립트:

```text
notebooks/08_test_korean_ner_adapter.py
```

테스트 결과:

```text
PERSON → PERSON
PER → PERSON
PS → PERSON
B-PER → PERSON
I-PER → PERSON
B-PS → PERSON
I-PS → PERSON
인명 → PERSON
ORG → None
LOC → None
```

가짜 Hugging Face 출력 기반 테스트에서도 다음이 정상 확인되었다.

```text
PER → EntitySpan(label=PERSON, text=김도윤)
PS → EntitySpan(label=PERSON, text=안서현)
B-PS → EntitySpan(label=PERSON, text=조민재)
ORG → 무시
B-ORG → 무시
```

---

## 8. 실제 Hugging Face 한국어 NER 모델 테스트

실제 한국어 NER 모델 연결 테스트도 수행했다.

테스트 스크립트:

```text
notebooks/09_review_huggingface_korean_ner.py
```

사용 모델:

```text
Leo97/KoELECTRA-small-v3-modu-ner
```

SSL 인증 문제로 Hugging Face에서 직접 다운로드하지 않고, 모델 파일을 로컬에 수동 배치한 뒤 로컬 경로로 로드했다.

로컬 모델 경로 예:

```text
models/hf/KoELECTRA-small-v3-modu-ner
```

사용 설정:

```python
aggregation_strategy="simple"
```

### 8-1. 성명 탐지 결과

실제 모델 테스트 결과, 한국인 성명 후보는 `PS` 라벨로 탐지되었다.

| 문장 | 원본 라벨 | 탐지값 | confidence | EntitySpan 변환 |
|---|---|---|---:|---|
| 직원 김도윤의 감봉 처분 결과를 확인했습니다. | PS | 김도윤 | 0.9812 | PERSON |
| 안서현 담당자에게 해당 서류를 전달했습니다. | PS | 안서현 | 0.9766 | PERSON |
| 조민재 씨의 제출 서류를 검토했습니다. | PS | 조민재 | 0.9820 | PERSON |
| 홍가람 민원인의 휴대전화 번호를 확인했습니다. | PS | 홍가람 | 0.8124 | PERSON |

이 결과를 통해 공개 한국어 NER 모델이 성명 후보 탐지 보완에 활용 가능함을 확인했다.

### 8-2. 비지원 라벨 무시 결과

기관명과 기타 정보는 모델이 탐지했지만, 9주차 정책에 따라 EntitySpan으로 변환하지 않았다.

| 문장 | 원본 라벨 | 탐지값 | 처리 |
|---|---|---|---|
| 인천교통공사 정보화기획팀에서 검토했습니다. | OG | 인천교통공사 | 무시 |
| 담당자 이메일은 test@example.com입니다. | TM | test@example.com | 무시 |
| 서버 IP는 192.168.0.1이고 VLAN 100을 사용합니다. | QT | 192, .168.0.1 | 무시 |

이 결과는 역할 분담이 필요함을 보여준다.

```text
성명 후보
→ NER 활용 가능

이메일, IP, VLAN 등 패턴형 정보
→ 정규식 탐지가 더 적합

기관명, 조직명
→ 현재 단계에서는 조치 대상이 아니므로 무시
```

---

## 9. EntitySpan → Detection 변환

9주차에서는 `EntitySpan`을 최종 탐지 결과 형태인 Detection dict로 변환하는 단계까지 구현했다.

구현 파일:

```text
src/ner_detection_converter.py
```

테스트 스크립트:

```text
notebooks/10_test_ner_detection_converter.py
```

변환 정책:

```text
PERSON EntitySpan만 Detection으로 변환한다.
Detection label은 성명으로 지정한다.
grade는 S로 지정한다.
action은 마스킹으로 지정한다.
source는 ner로 지정한다.
```

변환 예:

```python
EntitySpan(
    label="PERSON",
    text="김도윤",
    start=3,
    end=6,
    source="hf_ner",
    confidence=0.9812,
    original_label="PS",
)
```

변환 결과:

```python
{
    "label": "성명",
    "matched": "김도윤",
    "grade": "S",
    "action": "마스킹",
    "source": "ner",
    "context": "직원 김도윤의 감봉 처분 결과를 확인했습니다.",
    "locationLabel": "17번째 문단",
    "locationMeta": {"fileType": "docx", "paragraphNo": 17},
    "start": 3,
    "end": 6,
    "sensitiveType": "개인정보",
    "sensitiveCategory": "성명",
    "reason": "NER 모델이 PERSON 개체로 탐지 / original_label=PS / confidence=0.9812 / threshold=0.80"
}
```

---

## 10. confidence threshold 정책

초기 설계에서는 threshold를 0.85로 검토했으나, 실제 모델 테스트에서 `홍가람`이 0.8124로 탐지되었다.

해당 결과는 성명 후보로 활용 가능하다고 판단하여 9주차 구현에서는 threshold를 0.8로 설정했다.

```python
NER_CONFIDENCE_THRESHOLD = 0.8
```

정책:

| 조건 | 처리 |
|---|---|
| `confidence is None` | Detection 생성 |
| `confidence >= 0.8` | Detection 생성 |
| `confidence < 0.8` | Detection 생성 보류 |

threshold는 어댑터 단계가 아니라 Detection 변환 단계에서 적용한다.

이유:

```text
1. threshold를 바꿔도 NER 모델을 다시 실행할 필요가 없다.
2. 낮은 confidence 결과도 분석용으로 남길 수 있다.
3. 모델별 confidence 경향을 비교할 수 있다.
```

---

## 11. Detection 변환 테스트 결과

`notebooks/10_test_ner_detection_converter.py` 실행 결과는 다음과 같다.

### 11-1. 고신뢰도 성명 탐지

```text
문장: 직원 김도윤의 감봉 처분 결과를 확인했습니다.
EntitySpan: 김도윤 / confidence=0.9812
Detection 생성: O
```

Detection:

```text
탐지 항목: 성명
탐지 값: 김도윤
등급: S
조치: 마스킹
탐지 방식: ner
위치: 17번째 문단
start/end: 3/6
```

### 11-2. threshold 통과 경계 사례

```text
문장: 홍가람 민원인의 휴대전화 번호를 확인했습니다.
EntitySpan: 홍가람 / confidence=0.8124
Detection 생성: O
```

threshold가 0.8이므로 Detection이 생성되었다.

### 11-3. threshold 미만 성명 후보

```text
문장: 민원인 이가온의 연락 요청이 있었습니다.
EntitySpan: 이가온 / confidence=0.7321
Detection 생성: X
```

confidence가 0.8 미만이므로 Detection을 생성하지 않았다.

### 11-4. 비지원 라벨 무시

```text
문장: 인천교통공사 정보화기획팀에서 검토했습니다.
원본 라벨: OG
EntitySpan 생성: X
Detection 생성: X
```

PERSON이 아닌 라벨은 어댑터 단계에서 무시되었다.

---

## 12. 탐지 우선순위

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

이 정책은 이후 Detection 병합 단계에서 활용한다.

---

## 13. 정규식, NER, AI의 역할 분담

9주차 결과를 바탕으로 역할 분담은 다음과 같이 정리한다.

| 탐지 방식 | 담당 영역 |
|---|---|
| regex | 이메일, 전화번호, 사번, 내부 IP, VLAN, 포트 등 패턴형 정보 |
| ner | 성명 후보 탐지 |
| ai | 문장 전체의 문맥형 민감정보 판단 |
| 업무 규칙 | 계약정보, 입찰정보, 인사정보, 보안운영정보 등 업무상 민감정보 판단 |

중요한 점은 NER 모델이 이메일이나 IP를 일부 탐지하더라도, 이를 개인정보 탐지의 주된 근거로 사용하지 않는다는 것이다.

실제 테스트에서 이메일은 `TM`, IP는 `QT`로 탐지되었고, IP는 조각나서 탐지되었다.

따라서 다음 원칙을 유지한다.

```text
패턴형 정보는 정규식이 우선이다.
성명 후보는 NER가 보완한다.
문맥형 민감정보는 AI/업무 규칙이 보완한다.
```

---

## 14. 9주차 산출물

9주차 산출물은 다음과 같다.

```text
reports/week9_korean_ner_adapter_design.md
src/ner_units.py
src/korean_ner_adapter.py
notebooks/08_test_korean_ner_adapter.py
notebooks/09_review_huggingface_korean_ner.py
src/ner_detection_converter.py
notebooks/10_test_ner_detection_converter.py
```

각 파일의 역할:

| 파일 | 역할 |
|---|---|
| `week9_korean_ner_adapter_design.md` | 9주차 설계 및 결과 정리 |
| `ner_units.py` | `EntitySpan` 표준 구조 정의 |
| `korean_ner_adapter.py` | 모델별 NER 라벨을 PERSON으로 정규화 |
| `08_test_korean_ner_adapter.py` | 가짜 Hugging Face 출력 기반 어댑터 테스트 |
| `09_review_huggingface_korean_ner.py` | 실제 Hugging Face 한국어 NER 모델 테스트 |
| `ner_detection_converter.py` | EntitySpan을 Detection dict로 변환 |
| `10_test_ner_detection_converter.py` | Detection 변환 테스트 |

---

## 15. 결론

9주차에서는 공개 한국어 NER 모델의 출력 결과를 우리 프로그램에 맞게 표준화하는 구조를 구현했다.

핵심 결과는 다음과 같다.

```text
1. 공개 한국어 NER 모델은 한국인 성명 후보를 PS 라벨로 탐지했다.
2. korean_ner_adapter.py에서 PS를 내부 표준 PERSON으로 변환했다.
3. ORG/LOC/OG/TM/QT 등은 현재 단계에서 무시했다.
4. EntitySpan을 통해 모델별 출력 차이를 흡수할 수 있었다.
5. threshold=0.8 기준으로 PERSON EntitySpan을 성명 Detection으로 변환했다.
6. 이메일, IP, VLAN 등 패턴형 정보는 NER보다 정규식이 적합함을 확인했다.
```

최종 구조:

```text
Hugging Face NER output
→ korean_ner_adapter.py
→ EntitySpan
→ ner_detection_converter.py
→ Detection
```

이 구조를 통해 공개 NER 모델을 성명 탐지 보완 도구로 사용할 수 있게 되었다.

다만 NER은 최종 판단기가 아니다.

C/S/O 등급과 조치 방식은 다음 요소를 결합해 결정해야 한다.

```text
regex
ner
ai
업무 규칙
문서 위치 정보
```

---

## 16. 다음 단계

다음 단계에서는 9주차에서 만든 NER Detection을 기존 하이브리드 탐지 흐름에 통합한다.

검토할 작업은 다음과 같다.

```text
1. regex Detection과 ner Detection 병합
2. start/end 겹침 구간 처리
3. regex > ner > ai 우선순위 적용
4. TextUnit 기반 문서 파서 결과와 연결
5. locationLabel, locationMeta를 포함한 최종 탐지 결과 생성
6. 문서 전체 최고 등급 산정에 ner Detection 반영
```

즉, 다음 단계의 핵심은 다음이다.

```text
regex + ner + ai 결과 병합
→ 최종 Detection 목록 생성
→ 문서 전체 등급 산정
```
