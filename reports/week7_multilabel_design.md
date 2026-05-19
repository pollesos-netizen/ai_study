# 7주차 다중 속성 라벨 구조 설계

## 1. 목적

7주차의 목적은 기존 단일 라벨 문장분류 구조를 실제 개인정보/민감정보 탐지 업무에 맞는 다중 속성 라벨 구조로 확장하는 것이다.

기존 데이터셋은 다음과 같은 단일 라벨 구조를 사용했다.

```csv
id,text,label,category,cso_grade,note
```

기존 라벨은 주로 다음 세 가지였다.

```text
일반
개인정보
민감정보
```

이 구조는 초기 문장분류 모델 학습에는 적합했지만, 실제 보안 탐지 업무에는 한계가 있다.

예를 들어 다음 문장을 보자.

```text
직원 김도윤의 감봉 처분 결과를 확인했습니다.
```

이 문장에는 다음 정보가 동시에 포함되어 있다.

```text
김도윤 → 개인정보
감봉 처분 결과 → 업무상 민감정보 / 인사정보
```

단일 라벨 구조에서는 이 문장을 개인정보로 볼지, 민감정보로 볼지 하나만 선택해야 한다.

따라서 7주차에서는 문장을 하나의 라벨로만 분류하지 않고, 다음 속성을 분리해서 기록하는 구조로 전환한다.

```text
개인정보 포함 여부
법령상 민감정보 포함 여부
업무상 민감정보 포함 여부
문장 자체 보호 대상 여부
문서/첨부 민감정보 신호 여부
대표 민감정보 카테고리
C/S/O 등급
권장 조치 방식
```

---

## 2. 기존 단일 라벨 구조의 한계

기존 단일 라벨 구조는 다음과 같은 장점이 있었다.

```text
1. 구조가 단순하다.
2. 처음 AI 문장분류 모델을 학습하기 쉽다.
3. 일반/개인정보/민감정보의 큰 구분을 빠르게 실험할 수 있다.
```

하지만 실제 탐지기에는 다음 한계가 있다.

```text
1. 한 문장에 개인정보와 민감정보가 동시에 포함될 수 있다.
2. 민감정보에는 법령상 민감정보와 업무상 민감정보가 모두 존재한다.
3. 업무상 민감정보는 문장 자체에 직접 포함될 수도 있고, 문서/첨부에 존재할 가능성만 시사할 수도 있다.
4. 단일 label만으로는 C/S/O 등급과 조치 방식을 충분히 설명하기 어렵다.
5. 문장 자체 비식별화 대상과 문서 추가 확인 신호를 구분하기 어렵다.
```

예시:

```text
특정 역 사고 이력 원자료를 첨부했습니다.
```

이 문장은 문장 자체를 비식별화할 대상은 아닐 수 있다.

그러나 이 문장이 포함된 문서나 첨부파일 안에는 사고 이력 원자료라는 업무상 민감정보가 있을 가능성이 있다.

따라서 이 문장은 다음처럼 해석해야 한다.

```text
문장 자체 보호 대상: 아님
문서/첨부 민감정보 신호: 맞음
확인해야 할 민감정보 유형: 운용데이터 또는 장애/사고대응 정보
```

---

## 3. 7주차 CSV 구조

7주차 기준 데이터셋 파일명은 다음과 같다.

```text
data/privacy_sentence_sample_v4.csv
```

CSV 컬럼 구조는 다음과 같다.

```csv
id,text,has_personal,has_sensitive_legal,has_sensitive_business,sensitive_category,cso_grade,deidentify_method,is_direct_sensitive_text,is_document_sensitive_signal,indicated_sensitive_category,note
```

각 컬럼의 의미는 다음과 같다.

| 컬럼명 | 의미 | 값 예시 |
|---|---|---|
| `id` | 문장 ID | `1`, `2`, `189` |
| `text` | AI 모델 입력 문장 | `담당자 이메일은 test@example.com입니다.` |
| `has_personal` | 문장에 개인정보가 포함되어 있는지 | `Y`, `N` |
| `has_sensitive_legal` | 문장에 법령상 민감정보가 포함되어 있는지 | `Y`, `N` |
| `has_sensitive_business` | 문장에 업무상 민감정보가 직접 포함되어 있는지 | `Y`, `N` |
| `sensitive_category` | 문장의 대표 정보 유형 | `이메일`, `건강정보`, `계약정보`, `일반업무` |
| `cso_grade` | 문장 자체 기준 C/S/O 등급 | `C`, `S`, `O` |
| `deidentify_method` | 문장 자체에 대한 권장 조치 | `마스킹`, `삭제 또는 비식별화`, `해당 없음` |
| `is_direct_sensitive_text` | 문장 자체가 보호 대상 정보를 직접 포함하는지 | `Y`, `N` |
| `is_document_sensitive_signal` | 문서/첨부 내 민감정보 가능성을 알려주는 신호인지 | `Y`, `N` |
| `indicated_sensitive_category` | 신호가 가리키는 민감정보 유형 | `계약정보`, `운용데이터`, `해당 없음` |
| `note` | 라벨링 판단 근거 또는 주의사항 | 자유 텍스트 |

---

## 4. `is_direct_sensitive_text` 재정의

7주차에서 가장 중요한 수정은 `is_direct_sensitive_text`의 의미 재정의이다.

기존에는 이 컬럼을 다음처럼 좁게 해석할 수 있었다.

```text
문장 안에 마스킹·삭제할 구체적인 값이 있는가?
```

그러나 실제 업무상 민감정보에서는 구체적인 값이 없더라도 문장 내용 자체가 보호 대상일 수 있다.

예시:

```text
납품 단가 협의 결과를 공유드립니다.
개찰 전 예정가격 검토자료를 공유했습니다.
```

따라서 `is_direct_sensitive_text`는 다음 의미로 재정의한다.

```text
문장 자체가 C/S/O 등급 판단상 보호 대상 정보를 직접 포함하는가?
```

이 컬럼이 `Y`가 되는 경우는 두 가지이다.

### 4-1. 값 보호 대상

문장 안에 마스킹·삭제할 구체적인 값이 있는 경우이다.

예시:

```text
담당자 이메일은 test@example.com입니다.
사번 EF345678 직원의 야간 출입기록을 검토했습니다.
서버 IP는 192.168.0.1이고 VLAN 100을 사용합니다.
```

이 경우 조치 방식은 보통 다음과 같다.

```text
마스킹
삭제
삭제 또는 비식별화
```

### 4-2. 내용 보호 대상

구체적인 값은 없지만 문장 내용 자체가 보호 대상인 경우이다.

예시:

```text
납품 단가 협의 결과를 공유드립니다.
개찰 전 예정가격 검토자료를 공유했습니다.
팀장급 보직 변경 검토안을 공유했습니다.
```

이 경우 조치 방식은 보통 다음과 같다.

```text
삭제 또는 요약
범주화 또는 요약
비식별화 또는 요약
검토 필요
```

정리하면 다음과 같다.

| 유형 | `is_direct_sensitive_text` | 설명 |
|---|---|---|
| 값 보호 대상 | `Y` | 이메일, 전화번호, 사번, 내부 IP 등 구체값 포함 |
| 내용 보호 대상 | `Y` | 계약정보, 입찰정보, 인사정보 등 문장 내용 자체가 보호 대상 |
| 보호 대상 아님 | `N` | 일반 문장 또는 문서/첨부 확인 신호만 존재 |

따라서 다음 규칙을 적용한다.

```text
is_direct_sensitive_text=Y → deidentify_method는 '해당 없음'이면 안 됨
is_direct_sensitive_text=N → deidentify_method는 '해당 없음'
```

---

## 5. 문장 자체 보호 대상과 문서/첨부 확인 신호 구분

업무상 민감정보에서는 문장 자체가 민감한 경우와, 문서 또는 첨부파일 안에 민감정보가 있을 가능성을 알려주는 경우를 구분해야 한다.

### 5-1. 문장 자체 보호 대상

예시:

```text
계약 단가 협의 결과를 공유드립니다.
직원 김도윤의 감봉 처분 결과를 확인했습니다.
서버 IP는 192.168.0.1이고 VLAN 100을 사용합니다.
```

이 경우 문장 자체가 보호 대상이다.

```csv
is_direct_sensitive_text=Y
is_document_sensitive_signal=N 또는 Y
deidentify_method=마스킹 / 삭제 또는 요약 / 검토 필요
```

### 5-2. 문서/첨부 확인 신호

예시:

```text
특정 역 사고 이력 원자료를 첨부했습니다.
계약 단가 비교표를 공유합니다.
제안서 평가 세부 배점표를 검토했습니다.
```

이 경우 문장 자체는 비식별화 대상이 아닐 수 있다.

다만 문서나 첨부파일 안에는 업무상 민감정보가 있을 수 있다.

```csv
is_direct_sensitive_text=N
deidentify_method=해당 없음
is_document_sensitive_signal=Y
indicated_sensitive_category=운용데이터 또는 계약정보 등
```

중요한 점은 `is_document_sensitive_signal=Y`라고 해서 문장 자체를 반드시 비식별화해야 하는 것은 아니라는 점이다.

이 컬럼은 다음 의미이다.

```text
이 문장 자체보다 문서/첨부 내부를 추가 분석해야 한다는 신호
```

---

## 6. `sensitive_category` 대표 카테고리 선택 기준

`sensitive_category`는 문장에 포함된 모든 정보 유형을 나열하는 컬럼이 아니다.

이 컬럼은 문장의 **대표 정보 유형**을 하나 선택하는 컬럼이다.

다중 속성 정보는 다음 플래그 컬럼에서 보존한다.

```text
has_personal
has_sensitive_legal
has_sensitive_business
```

한 문장에 여러 정보 유형이 동시에 포함되면 다음 우선순위로 대표 카테고리를 선택한다.

```text
법령상 민감정보 > 업무상 민감정보 > 개인정보 > 일반업무
```

주의할 점은 이 우선순위가 상하위 분류 체계가 아니라는 것이다.

즉, 다음 구조를 의미하지 않는다.

```text
법령상 민감정보
└─ 업무상 민감정보
   └─ 개인정보
      └─ 일반업무
```

이 우선순위는 한 문장에 여러 정보 유형이 동시에 포함될 때 `sensitive_category` 값을 하나로 정하기 위한 기준이다.

예시:

```text
직원 김도윤의 감봉 처분 결과를 확인했습니다.
```

라벨:

```csv
has_personal=Y
has_sensitive_business=Y
sensitive_category=인사정보
```

개인정보가 사라지는 것이 아니라 `has_personal=Y`에 보존된다.

예시:

```text
직원 건강검진 재검 대상자 명단이 첨부되었습니다.
```

라벨:

```csv
has_personal=Y
has_sensitive_legal=Y
sensitive_category=건강정보
```

법령상 민감정보가 대표 카테고리로 선택된다.

---

## 7. `cso_grade`와 `deidentify_method`

`cso_grade`는 문장 자체 기준 등급이다.

문서 전체 등급이 아니다.

| 등급 | 의미 | 기본 조치 |
|---|---|---|
| `C` | 기밀 정보 | 외부 AI 입력 금지, 삭제 또는 강한 비식별화 |
| `S` | 민감 정보 | 비식별화 후 제한적 활용 검토 |
| `O` | 일반 정보 | 보안정책 준수 시 활용 가능 |

`deidentify_method`는 문장 자체에 대한 권장 조치이다.

예시:

| 조치 방식 | 의미 |
|---|---|
| `마스킹` | 이메일, 전화번호, 사번 등 일부 가림 |
| `삭제` | 외부 AI 입력 금지 수준의 정보 제거 |
| `삭제 또는 비식별화` | 법령상 민감정보 등 강한 보호 필요 |
| `삭제 또는 요약` | 내용 자체가 민감한 업무정보를 제거하거나 추상화 |
| `범주화 또는 요약` | 단가, 원가, 운용데이터 등 세부값을 범위·요약으로 변환 |
| `비식별화 또는 요약` | 인사정보 등 개인·업무 맥락을 제거하거나 요약 |
| `해당 없음` | 문장 자체에는 조치 불필요 |

---

## 8. 6주차 Detection 구조와의 연결

6주차에서 정의한 `Detection` 구조는 다음 필드를 포함한다.

```python
Detection(
    label=...,
    matched=...,
    grade=...,
    action=...,
    source=...,
    context=...,
    location_label=...,
    location_meta=...,
    sensitive_type=...,
    sensitive_category=...,
    reason=...,
)
```

7주차 CSV의 각 컬럼은 Detection 구조와 다음처럼 연결될 수 있다.

| CSV 컬럼 | Detection 또는 처리 구조 |
|---|---|
| `text` | `context` |
| `cso_grade` | `grade` |
| `deidentify_method` | `action` |
| `sensitive_category` | `sensitive_category` |
| `has_sensitive_legal` | `sensitive_type=법령상 민감정보` |
| `has_sensitive_business` | `sensitive_type=업무상 민감정보` |
| `is_direct_sensitive_text` | 직접 Detection 생성 여부 판단 |
| `is_document_sensitive_signal` | 문서/첨부 추가 분석 신호 |
| `indicated_sensitive_category` | 추가 분석 대상 카테고리 |

즉, 7주차 CSV는 향후 탐지 결과를 더 정교하게 표현하기 위한 학습용 기준 데이터 역할을 한다.

---

## 9. 검증 스크립트

7주차에서는 라벨 일관성을 점검하기 위해 다음 스크립트를 추가했다.

```text
notebooks/04_multilabel_data_check.py
```

검증 대상 파일은 다음이다.

```text
data/privacy_sentence_sample_v4.csv
```

주요 검증 규칙은 다음과 같다.

```text
1. Y/N 컬럼은 Y 또는 N만 허용
2. cso_grade는 C/S/O만 허용
3. is_direct_sensitive_text=Y이면 deidentify_method는 '해당 없음'이면 안 됨
4. is_direct_sensitive_text=N이면 deidentify_method는 '해당 없음'
5. is_document_sensitive_signal=Y이면 indicated_sensitive_category는 구체 카테고리여야 함
6. is_document_sensitive_signal=N이면 indicated_sensitive_category=해당 없음
7. has_* 플래그 중 하나라도 Y이면 cso_grade는 O이면 안 됨
8. cso_grade=O이면 is_direct_sensitive_text는 N이어야 함
9. has_personal=Y 단독 문장은 sensitive_category가 개인정보 계열이어야 함
10. has_personal=Y와 다른 민감 플래그가 함께 있는 경우 sensitive_category는 대표 카테고리 우선순위에 따름
```

실행 결과:

```text
검증 이슈 수: 0건
```

---

## 10. 라벨링 가이드

7주차 기준 라벨링 가이드는 다음 파일에 정리한다.

```text
data/labeling_guide_v3.md
```

라벨링 가이드에는 다음 내용이 포함된다.

```text
1. 각 컬럼의 의미
2. C/S/O 등급 기준
3. is_direct_sensitive_text 정의
4. 값 보호 대상과 내용 보호 대상 구분
5. sensitive_category 대표 카테고리 선택 기준
6. is_document_sensitive_signal 정의
7. 일관성 검증 규칙
8. 작성 원칙
```

특히 이번 주차에서 중요한 수정 사항은 다음 두 가지이다.

```text
1. is_direct_sensitive_text는 값 보호뿐 아니라 내용 보호도 포함한다.
2. sensitive_category는 모든 포함 요소가 아니라 대표 정보 유형 하나를 선택한다.
```

---

## 11. 7주차 결과

7주차를 통해 단일 라벨 구조를 다중 속성 라벨 구조로 확장했다.

최종 데이터셋은 다음 파일이다.

```text
data/privacy_sentence_sample_v4.csv
```

최종 라벨 구조는 다음과 같다.

```csv
id,text,has_personal,has_sensitive_legal,has_sensitive_business,sensitive_category,cso_grade,deidentify_method,is_direct_sensitive_text,is_document_sensitive_signal,indicated_sensitive_category,note
```

검증 결과는 다음과 같다.

```text
검증 이슈 수: 0건
```

이를 통해 다음을 확인했다.

```text
1. 개인정보, 법령상 민감정보, 업무상 민감정보를 분리할 수 있다.
2. 문장 자체 보호 대상과 문서/첨부 확인 신호를 구분할 수 있다.
3. C/S/O 등급과 권장 조치 방식을 별도 필드로 관리할 수 있다.
4. sensitive_category를 대표 카테고리로 관리하면서도 플래그 컬럼으로 멀티라벨 정보를 보존할 수 있다.
```

---

## 12. 다음 단계

8주차에서는 기존 scikit-learn 문장분류 문제를 TensorFlow/Keras 방식으로 재구현한다.

다만 8주차 모델 학습은 단순히 기존 `label` 컬럼을 예측하는 구조가 아니라, 7주차에서 정리한 다중 속성 라벨 구조를 어떻게 활용할지 검토해야 한다.

가능한 방향은 다음과 같다.

```text
1. 우선 cso_grade 예측 모델로 단순화
2. has_personal / has_sensitive_legal / has_sensitive_business를 각각 이진 분류로 학습
3. is_direct_sensitive_text 예측 모델 별도 구성
4. is_document_sensitive_signal 예측 모델 별도 구성
5. 최종적으로 다중 출력 모델 또는 단계적 분류 구조 검토
```

8주차에서 바로 모든 다중 라벨 모델을 완성할 필요는 없다.

우선은 scikit-learn에서 학습했던 문장분류 문제를 TensorFlow/Keras로 재구현하고, 이후 다중 속성 구조로 확장하는 것이 적절하다.
