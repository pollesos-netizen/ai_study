# 11주차 텍스트 단위 비식별화 Apply 설계 및 테스트 결과

## 1. 목적

11주차의 목적은 10주차에서 만든 `DeidentifyPlan`의 `auto_targets`를 실제 문자열에 적용하는 최소 Apply 엔진을 구현하는 것이다.

10주차까지는 비식별화 계획을 만들었다.

```text
Detection 목록
→ DeidentifyPlan
→ auto_targets / review_targets
```

11주차에서는 계획 중 자동 적용 가능한 대상만 실제 텍스트에 적용한다.

```text
DeidentifyPlan.auto_targets
→ start/end 기준 문자열 수정
→ 비식별화된 텍스트 생성
```

단, 11주차에서는 아직 실제 `xlsx`, `docx`, `pptx`, `hwpx` 파일을 직접 수정하지 않는다.

```text
11주차:
문자열 단위 Apply PoC

12주차 이후:
파일 형식별 Apply
```

---

## 2. 구현 파일

11주차 산출물은 다음과 같다.

```text
src/deidentify_apply.py
notebooks/12_test_deidentify_apply_text.py
reports/week11_deidentify_apply_text.md
```

각 파일의 역할은 다음과 같다.

| 파일 | 역할 |
|---|---|
| `deidentify_apply.py` | `DeidentifyTarget`을 원문 문자열에 적용하는 Apply 엔진 |
| `12_test_deidentify_apply_text.py` | 문자열 단위 마스킹/삭제/skip 테스트 |
| `week11_deidentify_apply_text.md` | 11주차 설계 및 테스트 결과 정리 |

---

## 3. 핵심 원칙

11주차 Apply의 핵심 원칙은 다음과 같다.

```text
1. auto_targets만 자동 적용한다.
2. review_targets는 자동 적용하지 않는다.
3. 같은 문자열 안에서는 start 내림차순으로 적용한다.
4. 마스킹 길이는 matched 길이가 아니라 text[start:end] 길이를 기준으로 한다.
5. start/end 범위가 잘못된 target은 조용히 보정하지 않고 skip + warning 처리한다.
6. matched와 실제 text[start:end]가 다르면 warning을 남긴다.
7. 삭제 action은 기본적으로 빈 문자열("")로 제거한다. 사용자 확인용 preview가 필요할 때만 `deletion_mode="mark"`로 "(삭제됨)"을 표시한다.
8. 검토 필요 action은 start/end 검증보다 먼저 자동 적용 제외 처리한다.
```

---

## 4. 마스킹 길이 기준

마스킹 길이는 `matched`가 아니라 실제 원문 구간인 `text[start:end]` 길이를 기준으로 한다.

```text
mask_length = end - start
```

이유는 `matched`와 실제 원문 구간이 다를 수 있기 때문이다.

예:

```text
matched = test@example.com
text[start:end] = test@example.co
```

이 경우 `matched`를 기준으로 마스킹하면 실제 치환 구간과 길이가 맞지 않는다.

따라서 정책은 다음과 같다.

```text
1. 실제 치환 대상은 text[start:end]
2. 마스킹 길이는 end - start
3. matched는 검증과 로그용으로 사용
4. matched와 text[start:end]가 다르면 warning 기록
```

---

## 5. start/end 범위 오류 처리

잘못된 start/end는 조용히 클리핑하지 않는다.

즉, 다음과 같은 처리는 하지 않는다.

```python
end = min(end, len(text))
```

대신 자동 적용을 건너뛰고 warning을 남긴다.

오류 처리 대상:

```text
start < 0
end > len(text)
start >= end
start is None
end is None
```

정책:

```text
범위 오류 target은 skipped_targets로 이동
warnings에 사유 기록
원문은 변경하지 않음
```

---

## 6. action 처리 기준

11주차 action 처리 기준은 다음과 같다.

| action | 처리 |
|---|---|
| `마스킹` | `*` 반복 문자열로 치환 |
| `삭제` | 기본(`deletion_mode="delete"`): 빈 문자열로 제거 |
| `삭제` (preview) | `deletion_mode="mark"` 지정 시: `(삭제됨)`으로 표시 |
| `검토 필요` | 자동 적용하지 않음 |
| 기타 | 기본 마스킹 |

초기에는 `삭제`를 `(삭제됨)` 고정 문자열로 처리했으나, `(삭제됨)`은 5자 고정이므로 같은 문자열 안에 삭제 대상과 다른 target이 공존할 때 start/end가 어긋날 수 있다는 문제가 있었다.

따라서 삭제 action은 기본적으로 실제 삭제(`""`)를 수행하도록 변경했다. 사용자 검토 및 디버깅용 preview가 필요한 경우에만 `deletion_mode="mark"`를 명시해 `(삭제됨)`을 표시한다.

```text
# deletion_mode="delete" (기본)
서버 IP는 192.168.0.1입니다.
→ 서버 IP는 입니다.

# deletion_mode="mark" (preview용)
서버 IP는 192.168.0.1입니다.
→ 서버 IP는 (삭제됨)입니다.
```

`(삭제됨)` 표시는 파일 저장 전 단계에서만 유효한 임시 표시이며, 실제 파일 Apply 전에 제거되어야 한다.

---

## 7. start 내림차순 적용

같은 문자열에 여러 target이 있을 때는 반드시 start 내림차순으로 적용한다.

예:

```text
담당자 김도윤의 이메일은 test@example.com입니다.
```

target:

```text
김도윤: 4~7
test@example.com: 14~30
```

앞쪽 `김도윤`을 먼저 마스킹하면 뒤쪽 이메일의 start/end가 어긋날 수 있다.

따라서 적용 순서는 다음이다.

```text
1. test@example.com
2. 김도윤
```

즉:

```text
10주차 표시 정렬:
location 순서 → start 오름차순

11주차 Apply 정렬:
같은 문자열 내부 → start 내림차순
```

---

## 8. auto_targets와 review_targets 공존 정책

`review_targets`는 자동 적용하지 않는다.

같은 location에 auto_target과 review_target이 공존할 수 있다.

예:

```text
직원 김도윤의 감봉 처분 결과를 확인했습니다.
```

auto_target:

```text
김도윤 → 성명 → 마스킹
```

review_target:

```text
문장 전체 → 인사정보 문맥 → 검토 필요
```

정책:

```text
auto_targets:
문자열에 자동 적용

review_targets:
원본 context 기준 검토 대상으로 유지
```

review_target은 자동 적용된 텍스트 기준으로 start/end를 재해석하지 않는다.

이유는 review_target이 보통 문장 전체 판단이거나 start/end가 없기 때문이다.

---

## 9. 검토 필요 action 처리 순서

초기 구현에서는 `검토 필요` target이 `start/end=None`을 가지고 있을 경우, 범위 오류로 먼저 처리되었다.

예:

```text
reason=start 또는 end가 None입니다.
```

그러나 `검토 필요` target의 본질은 범위 오류가 아니라 자동 적용 제외 대상이라는 점이다.  
따라서 `apply_single_target()`에서 `start/end` 검증보다 먼저 `검토 필요` action을 처리하도록 수정했다.

수정 후 결과:

```text
reason=검토 필요 action은 자동 적용하지 않습니다.
```

이 방식이 정책과 더 잘 맞는다.

---

## 10. 결과 구조

11주차 Apply 결과는 다음 구조로 정리한다.

```python
@dataclass
class SkippedTarget:
    target: DeidentifyTarget
    reason: str

@dataclass
class ApplyResult:
    original_text: str
    applied_text: str
    applied_targets: list[DeidentifyTarget]
    skipped_targets: list[SkippedTarget]
    warnings: list[str]
```

필드 의미:

| 필드 | 의미 |
|---|---|
| `original_text` | 원본 문자열 |
| `applied_text` | 비식별화 적용 후 문자열 |
| `applied_targets` | 실제 적용된 target |
| `skipped_targets` | 범위 오류 또는 검토 필요 등으로 적용 제외된 target |
| `warnings` | matched 불일치, 범위 오류, 자동 적용 제외 사유 등 |

---

## 11. 주요 함수

`src/deidentify_apply.py`의 주요 함수는 다음과 같다.

```text
mask_text()
location_key_for_target()
validate_target_range()
replacement_for_target()
apply_single_target()
split_applicable_targets()
apply_targets_to_text()
group_targets_by_location()
get_context_for_targets()
apply_plan_to_contexts()
```

각 함수 역할:

| 함수 | 역할 |
|---|---|
| `mask_text(length)` | 지정 길이만큼 `*` 생성 |
| `location_key_for_target(target)` | locationMeta → locationLabel → context 순서로 위치 키 생성 |
| `validate_target_range(text, target)` | start/end 유효성 검사 |
| `replacement_for_target(actual_text, target, deletion_mode)` | action에 따른 치환 문자열 생성 |
| `apply_single_target(text, target, deletion_mode)` | target 1개를 문자열에 적용 |
| `split_applicable_targets(targets)` | 자동 적용 가능 target과 제외 target을 사전 분리 |
| `apply_targets_to_text(text, targets, deletion_mode)` | target 목록을 start 내림차순으로 적용 |
| `group_targets_by_location(targets)` | location key 기준으로 target 묶기 |
| `get_context_for_targets(targets)` | 같은 location의 target에서 Apply용 원문 context 결정 |
| `apply_plan_to_contexts(plan, deletion_mode)` | DeidentifyPlan 전체를 location별로 묶어 문자열 Apply 수행 |

---

## 12. 테스트 케이스

테스트 스크립트:

```text
notebooks/12_test_deidentify_apply_text.py
```

테스트 케이스는 다음과 같다.

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC1 | 성명 1개 마스킹 | 해당 이름이 `*`로 마스킹 |
| TC2 | 이메일 1개 마스킹 | 이메일이 `*`로 마스킹 |
| TC3 | 성명 + 이메일 동시 마스킹 | start 내림차순 적용 |
| TC4 | 내부 IP 삭제 | `(삭제됨)`으로 표시 |
| TC5 | 검토 필요 action | 자동 적용 제외 |
| TC6 | matched와 text[start:end] 불일치 | 적용은 하되 warning 기록 |
| TC7-1 | start < 0 | skip + warning |
| TC7-2 | end > len(text) | skip + warning |
| TC7-3 | start >= end | skip + warning |
| TC7-4 | start/end None | skip + warning |
| TC8 | auto + review 공존 | auto만 적용, review는 자동 적용 제외 |

---

## 13. 테스트 결과 요약

### TC1. 성명 1개 마스킹

```text
원문:
직원 김도윤의 감봉 처분 결과를 확인했습니다.

적용 결과:
직원 ***의 감봉 처분 결과를 확인했습니다.
```

결과:

```text
applied_targets: 1
skipped_targets: 0
warnings: 0
```

성명 `김도윤`이 정상적으로 마스킹되었다.

---

### TC2. 이메일 1개 마스킹

```text
원문:
담당자 이메일은 test@example.com입니다.

적용 결과:
담당자 이메일은 ****************입니다.
```

결과:

```text
applied_targets: 1
skipped_targets: 0
warnings: 0
```

이메일 주소가 실제 구간 길이에 맞춰 마스킹되었다.

---

### TC3. 성명 + 이메일 동시 마스킹

```text
원문:
담당자 김도윤의 이메일은 test@example.com입니다.

적용 결과:
담당자 ***의 이메일은 ****************입니다.
```

결과:

```text
applied_targets: 2
warnings: 0
```

이메일 target을 먼저 적용하고, 이후 성명 target을 적용했다.  
같은 문자열 내 start 내림차순 적용이 정상 동작했다.

---

### TC4. 내부 IP 삭제

```text
원문:
서버 IP는 192.168.0.1입니다.

적용 결과 (deletion_mode="delete", 기본):
서버 IP는 입니다.

적용 결과 (deletion_mode="mark", preview용):
서버 IP는 (삭제됨)입니다.
```

결과:

```text
applied_targets: 1
warnings: 0
```

삭제 action은 기본적으로 빈 문자열로 제거된다. `deletion_mode="mark"` 지정 시 `(삭제됨)`으로 표시된다.

---

### TC5. 검토 필요 action 자동 적용 제외

```text
원문:
입찰 제안 평가표를 검토했습니다.

적용 결과:
입찰 제안 평가표를 검토했습니다.
```

결과:

```text
applied_targets: 0
skipped_targets: 1
reason=검토 필요 action은 자동 적용하지 않습니다.
```

`검토 필요` action은 start/end 검증보다 먼저 자동 적용 제외 처리되었다.

---

### TC6. matched와 실제 slice 불일치

```text
원문:
담당자 이메일은 test@example.com입니다.

적용 결과:
담당자 이메일은 ***************m입니다.
```

결과:

```text
applied_targets: 1
warnings: 1
```

warning:

```text
matched와 실제 text[start:end]가 다릅니다:
matched='test@example.com',
actual='test@example.co',
start=9,
end=24
```

start/end가 유효하면 적용은 수행하되, matched와 실제 slice가 다르면 warning을 남긴다.  
이 케이스는 잘못된 start/end를 탐지하기 위한 방어 테스트이다.

---

### TC7-1. start < 0

```text
reason=start가 0보다 작습니다: start=-1
```

결과:

```text
applied_targets: 0
skipped_targets: 1
warnings: 1
```

---

### TC7-2. end > len(text)

```text
reason=end가 원문 길이를 초과합니다: end=100, text_len=19
```

결과:

```text
applied_targets: 0
skipped_targets: 1
warnings: 1
```

---

### TC7-3. start >= end

```text
reason=start가 end보다 크거나 같습니다: start=6, end=3
```

결과:

```text
applied_targets: 0
skipped_targets: 1
warnings: 1
```

---

### TC7-4. start/end None

```text
reason=start 또는 end가 None입니다.
```

결과:

```text
applied_targets: 0
skipped_targets: 1
warnings: 1
```

---

### TC8. auto + review 공존 시 auto만 적용

```text
원문:
직원 김도윤의 감봉 처분 결과를 확인했습니다.

적용 결과:
직원 ***의 감봉 처분 결과를 확인했습니다.
```

결과:

```text
applied_targets: 1
skipped_targets: 1
```

auto target인 성명은 마스킹되었고, review target인 문장 전체 민감정보 판단은 자동 적용 제외되었다.

```text
reason=검토 필요 action은 자동 적용하지 않습니다.
```

---

## 14. 구현 중 수정한 사항

### 14-1. 삭제 action 처리 변경

초기에는 `삭제` action을 `(삭제됨)` 고정 문자열로 처리했다.

```text
서버 IP는 192.168.0.1입니다.
→ 서버 IP는 (삭제됨)입니다.
```

그러나 `(삭제됨)`은 5자 고정이므로, 같은 문자열 안에 삭제 대상과 다른 target이 공존할 때 start 내림차순 적용 후에도 최종 텍스트에서 위치 어긋남이 발생할 수 있다. 또한 파일 Apply 단계에서 이 표시가 남아 있으면 혼란이 생긴다.

따라서 삭제 action은 `deletion_mode` 파라미터로 분리했다.

```text
deletion_mode="delete" (기본): 빈 문자열로 실제 제거
deletion_mode="mark" (preview용): "(삭제됨)"으로 표시
```

`(삭제됨)` 표시는 파일 저장 전 단계에서만 유효한 임시 표시이며, 실제 파일 Apply 전에 제거되어야 한다.

### 14-2. 검토 필요 action 처리 순서 변경

초기에는 `검토 필요` target이 `start/end=None`인 경우 범위 오류로 처리되었다.

```text
start 또는 end가 None입니다.
```

이후 정책에 맞게 `검토 필요` action을 범위 검증보다 먼저 처리하도록 수정했다.

```text
검토 필요 action은 자동 적용하지 않습니다.
```

### 14-3. TC3 start/end 수정

TC3의 이메일 target 위치가 잘못되어 warning이 발생했다.

초기 위치:

```text
start=13, end=29
```

실제 이메일 구간은 다음이었다.

```text
start=14, end=30
```

수정 후 warning 없이 성명과 이메일이 정상 마스킹되었다.

---

## 15. 현재 11주차 완료 범위

완료된 범위는 다음과 같다.

```text
1. 텍스트 단위 Apply 엔진 구현
2. 마스킹 처리 구현
3. 삭제 처리 구현 (deletion_mode 파라미터로 실제 삭제/preview 분리)
4. 검토 필요 자동 적용 제외 처리
5. start 내림차순 적용 구현
6. start/end 오류 skip + warning 처리
7. matched 불일치 warning 처리
8. split_applicable_targets()로 None target 사전 필터링
9. location별 묶음 Apply 구조 구현 (apply_plan_to_contexts)
10. ApplyPlanResult로 review_targets 원본 보존
11. TC1~TC8 테스트 통과
```

아직 하지 않은 것:

```text
1. xlsx 파일 직접 수정
2. docx 파일 직접 수정
3. pptx 파일 직접 수정
4. hwpx 파일 직접 수정
5. App.jsx 프론트엔드 연결
6. review_targets 사용자 승인 후 적용
```

---

## 16. 11주차 범위 밖 작업

11주차에서는 다음 작업은 하지 않는다.

```text
xlsx 파일 직접 저장
docx 파일 직접 저장
pptx 파일 직접 저장
hwpx 파일 직접 저장
프론트엔드 UI 연결
```

이유는 파일 형식별 원문 수정 방식이 다르기 때문이다.

파일 형식별 Apply는 이후 단계에서 분리한다.

```text
xlsx:
sheetName + cellRef 기준 셀 값 수정

docx:
paragraphNo 기준 문단 텍스트 수정

pptx:
slideIndex + shape/run 기준 텍스트 수정

hwpx:
XML 텍스트 노드 기준 수정
```

---

## 17. 결론

11주차의 핵심은 실제 파일 수정이 아니라, start/end 기반 문자열 치환을 안전하게 수행하는 최소 엔진을 만드는 것이다.

이번 주차를 통해 다음 흐름을 검증했다.

```text
DeidentifyTarget
→ apply_targets_to_text()
→ ApplyResult
→ applied_text
```

핵심 결론은 다음과 같다.

```text
1. 자동 적용 대상은 start/end가 있는 auto_targets로 제한한다.
2. review_targets는 자동 적용하지 않는다.
3. 같은 문자열 안에서는 start 내림차순으로 적용해야 한다.
4. 마스킹 길이는 matched가 아니라 실제 text[start:end] 기준으로 잡는다.
5. 삭제는 기본적으로 빈 문자열("")로 제거하고, 사용자 preview가 필요할 때만 `deletion_mode="mark"`로 "(삭제됨)"을 표시한다.
6. 잘못된 start/end는 자동 보정하지 않고 skip + warning 처리한다.
```

이 단계가 안정화되어야 이후 xlsx, docx, pptx, hwpx 파일 형식별 비식별화 적용으로 확장할 수 있다.

---

## 18. 다음 단계

다음 단계는 파일 형식별 Apply 확장이다.

권장 순서는 다음과 같다.

```text
1. 단일 문자열 Apply 안정화 유지
2. xlsx 셀 단위 Apply PoC
3. docx 문단 단위 Apply PoC
4. pptx 텍스트 단위 Apply PoC
5. hwpx XML 텍스트 단위 Apply 검토
6. review_targets UI 표시 및 승인 흐름 설계
```

파일 형식별 Apply에서는 `locationMeta`가 중요하다.

예:

```text
xlsx:
sheetName + cellRef

docx:
paragraphNo

pptx:
slideIndex + shape/run 정보

hwpx:
XML 내부 텍스트 노드 위치
```

따라서 다음 단계에서는 `locationMeta`를 기준으로 실제 파일 내부 위치를 찾아가고, 해당 위치의 텍스트에 `apply_targets_to_text()`를 적용하는 구조로 확장한다.

## 추가 보완 사항

### context 불일치 warning 정책

`apply_plan_to_contexts()`는 같은 location에 속한 target들을 묶은 뒤, 해당 target들의 `context`를 사용해 문자열 Apply를 수행한다.

같은 location 안에서 context가 서로 다른 경우, 11주차 PoC에서는 첫 번째 context를 기준으로 Apply를 수행하고 warning을 1회만 기록한다.

이는 11주차가 실제 파일 수정 단계가 아니라 문자열 Apply 구조를 검증하는 단계이기 때문이다. 실제 파일 Apply 단계에서는 `context`가 아니라 `locationMeta`를 기준으로 원문을 다시 조회하는 방식이 필요하다.

### location_key 표시 한계

현재 `location_key`는 `locationMeta → locationLabel → context` 순서로 생성되는 내부 그룹화용 키이다. `locationMeta`가 있는 경우 `repr(sorted(locationMeta.items()))` 형태가 사용되므로 warning 메시지나 테스트 출력에서 길게 보일 수 있다.

이는 내부 디버깅에는 충분하지만, 사용자 표시용으로는 적합하지 않다. 향후 UI 또는 로그 표시 단계에서는 `locationLabel` 기반의 별도 display key를 두는 것이 적절하다.

### review_targets 보존 기준

`review_targets`는 자동 적용하지 않고 `ApplyPlanResult.review_targets`에 원본 기준으로 보존한다.

같은 location에 auto target과 review target이 함께 있는 경우에도, auto target만 `applied_text`에 적용하고 review target은 원본 context 기준 검토 대상으로 유지한다.

따라서 review target을 나중에 사용자가 승인하더라도, auto 적용 후의 `applied_text` 기준으로 바로 적용하지 않는다. 승인 시에는 원본 파일 또는 원본 context 기준으로 별도 target을 생성한 뒤 적용하는 방식이 필요하다.