# 개인정보/민감정보 데이터셋 라벨링 가이드

> 대상 파일: `privacy_sentence_sample_v3_multilabel_restructured_v2.csv`  
> 목적: AI 모델 학습용 문장 데이터셋의 멀티라벨 컬럼 정의 및 라벨링 기준 통일

---

## 0. 이번 수정의 핵심

이번 라벨링 가이드는 다음 두 가지 이슈를 반영한다.

### 0-1. `is_direct_sensitive_text` 의미 재정의

기존에는 `is_direct_sensitive_text`를 “문장 안에 마스킹·삭제할 구체적인 값이 있는지”에 가깝게 해석했다.

그러나 실제 라벨링에서는 다음과 같은 문장도 보호 대상이 될 수 있다.

```text
납품 단가 협의 결과를 공유드립니다.
개찰 전 예정가격 검토자료를 공유했습니다.
```

이 문장들은 이메일, 전화번호처럼 마스킹할 특정 값이 있는 것은 아니지만, 문장 자체의 내용이 업무상 민감정보에 해당할 수 있다.

따라서 `is_direct_sensitive_text`는 다음 의미로 재정의한다.

```text
문장 자체가 C/S/O 등급 판단상 보호 대상 정보를 직접 포함하는가?
```

즉, `is_direct_sensitive_text=Y`는 두 경우를 모두 포함한다.

```text
1. 값 보호 대상
   - 이메일, 전화번호, 사번, 내부 IP 등 구체적인 값이 있음

2. 내용 보호 대상
   - 구체적인 값은 없지만 문장 내용 자체가 계약정보, 입찰정보, 인사정보 등 보호 대상임
```

반대로 `is_direct_sensitive_text=N`이면 원칙적으로 문장 자체에는 비식별화 조치가 필요하지 않다.

따라서 다음 규칙을 적용한다.

```text
is_direct_sensitive_text=N
→ deidentify_method=해당 없음
```

다만 문서나 첨부 안에 민감정보가 있을 가능성을 알려주는 문장은 다음 컬럼으로 별도 표시한다.

```text
is_document_sensitive_signal=Y
indicated_sensitive_category=구체 카테고리
```

---

### 0-2. `has_personal=Y`인데 `sensitive_category`가 개인정보 카테고리가 아닌 경우

한 문장에 개인정보와 다른 민감정보가 동시에 포함될 수 있다.

예시:

```text
직원 김도윤의 감봉 처분 결과를 확인했습니다.
```

이 문장은 다음 요소를 동시에 가진다.

```text
김도윤 → 개인정보
감봉 처분 결과 → 업무상 민감정보 / 인사정보
```

이 경우 `has_personal=Y`로 표시하되, `sensitive_category`는 더 큰 의미의 주된 카테고리인 `인사정보`로 둔다.

즉, `sensitive_category`는 모든 포함 요소를 나열하는 컬럼이 아니라 **주된 정보 유형**을 나타내는 컬럼이다.

카테고리 우선순위는 다음과 같다.

```text
법령상 민감정보
→ 업무상 민감정보
→ 개인정보
→ 일반업무
```

따라서 다음 조합은 정상이다.

```csv
has_personal=Y, has_sensitive_business=Y, sensitive_category=인사정보
```

개인정보 포함 여부는 `has_personal` 컬럼에서 보존되므로, `sensitive_category`가 개인정보 계열이 아니더라도 멀티라벨 정보는 손실되지 않는다.

---
## 1. 컬럼 정의

| 컬럼명 | 의미 | 값 예시 | 설명 |
|---|---|---|---|
| `id` | 문장 ID | `1`, `2`, `189` | 각 학습 문장을 구분하기 위한 고유 번호 |
| `text` | 학습 문장 | `담당자 이메일은 test@example.com입니다.` | AI 모델이 입력으로 받는 실제 문장 |
| `has_personal` | 개인정보 포함 여부 | `Y`, `N` | 문장에 성명, 전화번호, 이메일, 사번 등 개인정보가 직접 포함되어 있는지 |
| `has_sensitive_legal` | 법령상 민감정보 포함 여부 | `Y`, `N` | 문장에 건강정보, 복지정보, 장애정보 등 법령상 민감정보 성격의 내용이 포함되어 있는지 |
| `has_sensitive_business` | 업무상 민감정보 직접 포함 여부 | `Y`, `N` | 문장에 계약 단가, 평가 결과, 인사 조치, 보안정보 등 업무상 민감정보가 직접 들어 있는지 |
| `sensitive_category` | 문장의 주된 정보 유형 | `이메일`, `건강정보`, `계약정보`, `일반업무` | 문장의 주제 분류 |
| `cso_grade` | 문장 자체 기준 C/S/O 등급 | `C`, `S`, `O` | 문장 단위 보안 등급 (문서 전체 등급이 아님) |
| `deidentify_method` | 권장 조치 | `마스킹`, `삭제 또는 비식별화`, `삭제 또는 요약`, `범주화 또는 요약`, `해당 없음` | 문장에 대한 비식별화/재작성 방식 |
| `is_direct_sensitive_text` | 문장 자체가 직접 보호 대상인지 | `Y`, `N` | 문장이 등급 이상 정보를 포함하는지 (§3 참고) |
| `is_document_sensitive_signal` | 문서/첨부 확인 신호 여부 | `Y`, `N` | 문서나 첨부 내에 민감정보가 있을 가능성을 알려주는 신호 문장인지 |
| `indicated_sensitive_category` | 신호가 가리키는 민감정보 유형 | `계약정보`, `운용데이터`, `해당 없음` | `is_document_sensitive_signal=Y`일 때만 부여 |
| `note` | 라벨링 메모 | 자유 텍스트 | 판단 근거, 주의사항, 데이터 생성 의도 |

---

## 2. 등급(`cso_grade`) 기준

| 등급 | 설명 | 외부 AI 입력 |
|---|---|---|
| **C** | 기밀 (Confidential). 유출 시 법적 제재·심각한 업무 피해 우려 | ❌ 불가 |
| **S** | 민감 (Sensitive). 직접 식별 가능한 개인정보 또는 업무상 민감 정보 | ⚠️ 비식별화 + 부서장 승인 후 검토 |
| **O** | 일반 (Open). 식별 정보나 민감한 업무 내용이 없는 일반 정보 | ✅ 가능 |

**원칙**
- 확실할 때만 O급으로 분류한다.
- 불확실하면 상위 등급을 유지한다.
- 한 문장에 여러 등급 요소가 섞이면 가장 높은 등급을 따른다.

---

## 3. `is_direct_sensitive_text` 정의 (중요)

### 3-1. 정의

**"문장 자체가 등급 이상 정보를 직접 포함하는가"**

- `Y`: 문장 안에 마스킹·삭제·재작성이 필요한 보호 대상 정보가 직접 들어 있음
- `N`: 문장은 일반 업무 문장이거나, 문서/첨부 안에 민감정보가 있을 가능성만 시사함

### 3-2. 보호 대상의 두 가지 유형

`is_direct_sensitive_text=Y`는 다음 두 유형을 모두 포함한다.

| 유형 | 보호 대상 형태 | 권장 조치 예시 | 예시 문장 |
|---|---|---|---|
| **값 보호 대상** | 문장에 마스킹·삭제할 구체적인 값이 존재 | 마스킹, 삭제 또는 비식별화 | `담당자 이메일은 test@example.com입니다` |
| **내용 보호 대상** | 구체적 값은 없지만 문장의 내용 자체가 민감 주제 | 삭제 또는 요약, 범주화 또는 요약 | `납품 단가 협의 결과를 공유드립니다` |

### 3-3. 판단 흐름

```
문장에 보호 대상 값이 있는가?
  ├─ Y → is_direct_sensitive_text = Y (값 보호)
  └─ N → 문장 내용 자체가 민감 주제인가?
            ├─ Y → is_direct_sensitive_text = Y (내용 보호)
            └─ N → is_direct_sensitive_text = N
```

### 3-4. 권장 조치(`deidentify_method`)와의 관계

| 유형 | `is_direct_sensitive_text` | `deidentify_method` 예시 |
|---|---|---|
| 값 보호 대상 | Y | `마스킹`, `삭제 또는 비식별화` |
| 내용 보호 대상 | Y | `삭제 또는 요약`, `범주화 또는 요약`, `비식별화 또는 요약` |
| 보호 대상 아님 | N | `해당 없음` |
| 신호 문장 (값 보호 없음) | N | `해당 없음` (다만 `is_document_sensitive_signal=Y` 권장) |

> **주의**: `is_direct_sensitive_text=Y`이면 `deidentify_method`는 반드시 `해당 없음`이 아니어야 한다.

---

## 4. `sensitive_category` 우선순위 규칙

한 문장에 여러 카테고리 요소가 동시에 포함될 수 있다.  
이때는 다음 우선순위로 **주된 카테고리**를 선택한다.

### 4-1. 우선순위

1. **법령상 민감정보** (건강정보, 복지정보 등)
2. **업무상 민감정보** (계약정보, 인사정보, 운용데이터 등)
3. **개인정보** (성명, 연락처, 이메일, 사번 등)
4. **일반업무**

### 4-2. 적용 예시

| 문장 | 포함 요소 | `sensitive_category` 선택 |
|---|---|---|
| 직원 김도윤의 감봉 처분 결과를 확인했습니다 | 성명 + 인사정보 | **인사정보** (업무상 민감정보 우선) |
| 직원 건강검진 재검 대상자 명단이 첨부되었습니다 | 성명(암묵) + 건강정보 | **건강정보** (법령상 민감정보 우선) |
| 김민수 고객에게 연락 바랍니다 | 성명만 | **성명** (개인정보) |
| 회의 결과를 공유드립니다 | 없음 | **일반업무** |

### 4-3. 보조 컬럼과의 관계

`sensitive_category`가 주된 카테고리만 표시하더라도, **각 플래그 컬럼**(`has_personal`, `has_sensitive_legal`, `has_sensitive_business`)은 **모두 정확히 표기**한다.

| 문장 | sensitive_category | has_personal | has_sensitive_business |
|---|---|---|---|
| 직원 김도윤의 감봉 처분 결과를 확인했습니다 | 인사정보 | Y | Y |

이 방식으로 멀티라벨 정보를 손실 없이 표현한다.

---

## 5. `is_document_sensitive_signal` 정의

### 5-1. 정의

문장 자체는 민감하지 않거나 부분적으로만 민감하지만, **문서 또는 첨부 안에 추가 민감정보가 있을 가능성을 알려주는 신호 문장**인지 표시한다.

### 5-2. 예시

| 문장 | is_direct | is_signal | indicated_category |
|---|---|---|---|
| 진단서 사본이 첨부되었습니다 | N | Y | 건강정보 |
| 계약서 초안을 검토해 주세요 | N | Y | 계약정보 |
| CD789012 사번 직원의 출입 기록을 확인해 주세요 | Y | Y | 사번/출입기록 |

> 마지막 예시처럼 **직접 보호 대상 + 신호**가 동시에 성립할 수 있다.

### 5-3. 짝 규칙

- `is_document_sensitive_signal=Y` → `indicated_sensitive_category`는 반드시 구체 카테고리 부여
- `is_document_sensitive_signal=N` → `indicated_sensitive_category=해당 없음`

---

## 6. 일관성 검증 규칙

라벨링 후 반드시 다음 규칙을 만족해야 한다.

| 규칙 | 조건 | 결과 |
|---|---|---|
| R1 | 모든 `has_*=N` | `cso_grade=O` |
| R2 | `cso_grade=O` | 모든 `has_*=N` |
| R3 | `is_direct_sensitive_text=Y` | `deidentify_method≠해당 없음` |
| R4 | `is_direct_sensitive_text=N` AND 신호 아님 | `deidentify_method=해당 없음` |
| R5 | `is_document_sensitive_signal=Y` | `indicated_sensitive_category≠해당 없음` |
| R6 | `is_document_sensitive_signal=N` | `indicated_sensitive_category=해당 없음` |
| R7 | `has_personal=Y` 단독 | `sensitive_category`는 개인정보 계열 (성명, 연락처, 이메일, 사번 등) |
| R8 | `has_personal=Y` AND 다른 민감 플래그도 Y | `sensitive_category`는 §4 우선순위에 따름 |

---

## 7. 작성 원칙

- 실제 개인정보, 내부 문서, 사내 보안정보는 학습용 샘플에 사용하지 않는다.
- 모든 샘플 문장은 가명·가상 상황으로 작성한다.
- 외부 AI 또는 Colab에는 실제 개인정보나 사내 민감정보를 업로드하지 않는다.
- 실제 데이터 기반 학습은 사내 승인된 폐쇄망 또는 사내 GPU 서버 환경에서만 수행한다.
- 애매한 경우 상위 등급을 유지하고, `note`에 판단 근거를 기록한다.

---

## 8. 변경 이력

| 버전 | 일자 | 변경 내용 |
|---|---|---|
| v1 | 초기 작성 | 기본 컬럼 정의 |
| v2 | 현재 | `is_direct_sensitive_text` 정의 명확화 (값 보호 + 내용 보호로 확장), `sensitive_category` 우선순위 규칙 추가, 일관성 검증 규칙 명문화 |
