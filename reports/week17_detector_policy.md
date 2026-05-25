# detector 역할 분담 정책 (17주차)

## 1. 목적

12~16주차에 걸쳐 구현된 5종 detector(xlsx, docx, pptx, hwpx, pdf)는 모두 **regex / NER / AI 세 가지 탐지 소스**를 주입형으로 받는 구조다. 이 세 소스가 각각 어떤 역할을 담당하는지, 사용자 비식별화 가이드라인(C/S/O 등급)과 어떻게 매핑되는지 명문화한다.

이 문서는 detector 코드 변경 없이 **이미 구현된 동작에 대한 정책 명시**다.

---

## 2. 탐지 소스별 역할

### 2.1 regex_detector — 명확한 패턴

```text
대상:       형식이 정해진 패턴
탐지 방식:  정규식
처리 결과:  auto_targets (자동 비식별화 대상)
신뢰도:     높음 (False positive 거의 없음)
```

**대상 항목 예시**:

| 항목 | 패턴 | 등급 | 조치 |
|---|---|---|---|
| 이메일 주소 | `[\w.-]+@[\w.-]+` | S | 마스킹 |
| 휴대전화 번호 | `010-\d{4}-\d{4}` | S | 마스킹 |
| 주민등록번호 | `\d{6}-\d{7}` | **C** | 삭제 |
| IP 주소 | `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}` | C | 삭제 |
| VLAN ID | `VLAN\s+\d+` | C | 삭제 |
| 사번 | `[A-Z]{2}\d{6}` 등 회사 규칙 | S | 마스킹 |
| 카드/계좌번호 | 회사 규칙 | C | 삭제 |

**적합한 이유**:
- 패턴이 명확해 정규식으로 100% 가까이 잡힘
- AI 학습 데이터 부족과 무관하게 안정적
- 사용자 피드백 없이도 동작

### 2.2 NER 모델 — 한국인 성명 추정

```text
모델:       KoELECTRA-small-v3-modu-ner
대상:       한국인 성명 (PERSON 엔티티)
탐지 방식:  딥러닝 기반 개체명 인식
처리 결과:  auto_targets
신뢰도:     중간~높음 (학습 데이터로 검증된 성능)
threshold:  0.8 (기본값)
```

**왜 성명만**:
- KoELECTRA는 일반 도메인에서 학습됨
- 회사 도메인의 다른 엔티티(부서명, 직책 등)는 학습 부족
- 한국인 성명은 일반 도메인에서도 안정적으로 잡힘 (검증 완료)

**다른 엔티티는 사용하지 않음**:
```text
LOCATION (지명):    회사 도메인 특수성으로 부정확
ORGANIZATION:        회사명/부서명 구분 어려움
DATE/TIME:           formatted 패턴은 regex가 더 정확
```

향후 확장 가능성:
- 회사 도메인 데이터로 fine-tuning 시 다른 엔티티도 활용 검토
- 17주차 시점에는 PERSON만 사용

### 2.3 AI 분류 모델 — 민감 후보 추천

```text
모델:       privacy_cso_char_keras_model.keras
대상:       문장 단위 민감 정보 추정
탐지 방식:  딥러닝 기반 문장 분류
처리 결과:  review_targets (사용자 검토 대상)
신뢰도:     낮음~중간 (학습 데이터 부족)
threshold:  0.6 (기본값)
```

**역할 정책 (사용자 협의 결정사항)**:

```text
✓ AI는 "민감해 보이는 문장"을 추천만 한다.
✓ C/S/O 등급 자동 분류는 하지 않는다.
✗ 사용자가 최종 등급 판단.
```

**이유**:

1. **학습 데이터 부족**: 회사 도메인 라벨링 데이터가 충분하지 않아 등급 분류 정확도가 낮음
2. **회사 가이드라인 원칙과 부합**: 
   > "불확실하면 상위 등급 유지가 보안의 표준" (가이드라인 8쪽)
   > AI가 자의적으로 등급을 정하지 않고 사용자 판단을 우선
3. **review_targets로 사용자 검토 흐름 유지**: auto 적용은 안 함

**향후 개선 방향**:
- 사용자 피드백 학습 (HITL)으로 점진 개선 (10절 참조)

---

## 3. 회사 C/S/O 등급 가이드라인과의 매핑

회사 비식별화 가이드라인(test2.pdf, 사용자 메모리)의 C/S/O 등급 체계와 detector의 역할 매핑:

### 3.1 C급 (기밀 정보)

```text
가이드라인 정의:
  - 시스템 계정/비밀번호
  - 내부 IP, VLAN, 포트, 호스트명
  - 네트워크 구성도, 방화벽 정책
  - 중요시설 위치/도면

detector 매핑:
  - regex: IP, VLAN 패턴 → 자동 탐지 (auto)
  - NER:   해당 없음
  - AI:    C급 가능성 추천 (review)
```

처리 정책: **C급은 자동 삭제(`action="삭제"`) + AI는 추가 검토 추천**

### 3.2 S급 (민감 정보)

```text
가이드라인 정의:
  - 개인정보 (성명, 사번, 연락처, 이메일, 주소)
  - 사내 민감정보 (인사기록, 업무 지침, 미발표 기획안)
  - 영업비밀, 계약 정보

detector 매핑:
  - regex: 이메일, 휴대전화, 사번 패턴 → 자동 탐지 (auto)
  - NER:   한국인 성명 → 자동 탐지 (auto)
  - AI:    S급 가능성 추천 (review)
```

처리 정책: **S급은 마스킹(`action="마스킹"`) + AI 추천은 사용자 검토**

### 3.3 O급 (공개 정보)

```text
가이드라인 정의:
  - C/S 외 모든 정보
  - 식별자 제거가 완료된 데이터

detector 매핑:
  - 시스템이 별도로 처리하지 않음
  - 사용자가 "이건 O급이다" 판단 시 review 대상에서 제외
```

처리 정책: **시스템 개입 없음**

### 3.4 등급별 detector 역할 종합

```text
┌─────────┬─────────────────┬────────────────┬────────────────┐
│  등급    │  regex          │  NER (성명)    │  AI (분류)     │
├─────────┼─────────────────┼────────────────┼────────────────┤
│  C급    │  auto (삭제)    │  -              │  review        │
│  S급    │  auto (마스킹)  │  auto (마스킹) │  review        │
│  O급    │  -              │  -              │  -              │
└─────────┴─────────────────┴────────────────┴────────────────┘
```

---

## 4. detector 코드의 구조 매핑

각 detector(`docx_detector.py`, `pdf_detector.py` 등)는 3개 어댑터를 가진다.

```python
def detect_in_xxx(
    input_path,
    *,
    regex_detect_func=None,    # → auto_targets
    ner_detect_func=None,      # → auto_targets (성명만)
    ai_predict_func=None,      # → review_targets
    ner_threshold=0.8,
    ai_threshold=0.6,
) -> DeidentifyPlan
```

### 4.1 어댑터별 처리 흐름

```text
regex_detect_func(text)
  → DetectionResult / dict 반환
  → _make_target_dict_from_regex() 변환
  → action 그대로 (가이드라인: 마스킹/삭제)
  → auto_targets

ner_detect_func(text)
  → HF NER pipeline 출력 (entity_group, score, start, end)
  → _make_target_dict_from_ner() 변환
  → entity_group이 PERSON인 것만 필터
  → action="마스킹" 고정
  → auto_targets

ai_predict_func(text)
  → (grade, confidence, prob_map) 반환
  → _make_target_dict_from_ai() 변환
  → action="검토 필요" 고정
  → review_targets (build_deidentify_plan에서 분리)
```

### 4.2 build_deidentify_plan()의 분리

```python
# deidentify_target_builder.py
def build_deidentify_plan(detections) -> DeidentifyPlan:
    auto_targets = [d for d in detections if d["action"] != "검토 필요"]
    review_targets = [d for d in detections if d["action"] == "검토 필요"]
    return DeidentifyPlan(auto_targets=auto_targets, review_targets=review_targets)
```

`action="검토 필요"`인 AI 결과만 review_targets로 분리되는 구조가 이미 구현되어 있다. 17주차에 코드 변경 없이 정책 명문화만 필요.

---

## 5. CommonApplyResult에서의 표현

### 5.1 autoResults — 자동 비식별화 안내

```text
- regex/NER로 탐지된 항목
- 시스템이 권장 결과(appliedText) 미리 보여줌
- 사용자는 그대로 받아들이거나 수정
```

```text
예: 1쪽 7번째 줄: 오상현(4257) 신동석(4251)
    label="성명, 사번"
    action="마스킹"
    originalText="오상현(4257) 신동석(4251)"
    appliedText="*********  *********"
```

### 5.2 reviewTargets — AI 추천 (사용자 검토 필요)

```text
- AI가 "민감해 보인다"고 추천한 문장
- 시스템은 등급/조치 결정하지 않음
- 사용자가 등급(C/S/O) 판단 후 처리
```

```text
예: 3쪽 5번째 줄: 입찰 평가표를 검토했습니다...
    label="민감정보"
    action="검토 필요"
    context="입찰 평가표를 검토했습니다. 향후 협상 전략은..."
    reason="AI 문장분류 grade=S / confidence=0.7534 / threshold=0.60"
```

---

## 6. 프론트엔드 표시 정책 (PHP 팀 협의 필요)

### 6.1 autoResults 표시

```text
[자동 안내]
  위치:      1쪽 7번째 줄
  내용:      성명, 사번
  조치:      마스킹
  원문:      오상현(4257) 신동석(4251)
  권장 결과: *********  *********
  [받아들이기] [원본 유지]
```

### 6.2 reviewTargets 표시

```text
[AI 추천 검토]
  위치:    3쪽 5번째 줄
  문장:    "입찰 평가표를 검토했습니다. 향후 협상 전략은..."
  추천:    AI가 민감(S/C급) 가능성 추정 (확신도 75%)
  
  판단:
  ⚪ C급 (기밀)
  ⚪ S급 (민감)
  ⚪ O급 (공개)
  ⚪ 잘못된 추천
  
  [저장]
```

---

## 7. 사용자 피드백 학습 정책 (틀만 명시)

### 7.1 정책

```text
AI 추천에 대한 사용자 판단을 학습 데이터로 활용한다.

조건:
1. 사용자가 review_target에 대해 C/S/O 또는 "잘못된 추천"을 선택
2. 시스템이 (문장, AI 추정, 사용자 판단)을 누적 저장
3. 일정 누적량 도달 시 모델 재학습
4. 회사 도메인 특화 데이터로 점진 개선
```

### 7.2 17주차 구현 범위

```text
✓ 데이터 모델 정의 (src/feedback/models.py)
✓ 저장소 인터페이스 정의 (src/feedback/store.py, no-op)
✓ /api/feedback 엔드포인트 추가 (no-op)
✗ 실제 저장 구현 (부서 협의 후)
✗ 재학습 파이프라인 (협의 후)
```

### 7.3 협의 필요 항목

부서 협의 시 결정해야 할 항목:

```text
1. 저장 방식 (SQLite / PostgreSQL / JSON)
2. 사용자 식별 (익명 / 사번 / 부서)
3. 보존 기간
4. 접근 권한
5. 보안 등급 (원본 문서와 동일하게 처리)
6. 재학습 정책 (수동 / 자동 / 검수 거쳐)
7. 모델 사용 범위 (사내만)
8. 감사 로그
```

---

## 8. 누적 detector 동작 요약

### 8.1 5종 detector 공통 구조

```text
detect_and_build_guide_for_X(input_path)
  ├─ iter_X_paragraphs() / iter_X_lines() / iter_X_cells()
  │   → ParsedX 목록 (텍스트 + 위치 메타데이터)
  │
  ├─ detect_in_X(input_path, regex/NER/AI 어댑터)
  │   ├─ regex_detect_func() → auto_targets
  │   ├─ ner_detect_func() → auto_targets (성명만)
  │   └─ ai_predict_func() → review_targets
  │
  ├─ build_deidentify_plan() → DeidentifyPlan
  │
  └─ build_guide_for_X(input_path, plan)
      → CommonApplyResult(applyMode="guide" 또는 "applied")
```

### 8.2 5종 detector의 차이

| 형식 | applyMode | 위치 단위 | 주요 section |
|---|---|---|---|
| xlsx | applied | 셀 (cellRef) | (없음) |
| docx | guide | paragraph | body, table_cell |
| pptx | guide | paragraph | shape_text, table_cell, notes, group_* |
| hwpx | guide | paragraph | body, table_cell |
| pdf | guide | line | text_line |

---

## 9. 정책 일관성 검증 (17주차 부채 정리에서 확정)

17주차 부채 정리(1~4단계)에서 다음 일관성을 확보:

```text
1. WARNING_MISSING_PARAGRAPH_NO
   → 5종 detector 모두 paragraphNo/lineNo 누락 시 사용
   
2. WARNING_MISSING_TABLE_CELL_LOCATION
   → docx, hwpx의 표 셀 보조 필드 누락 시 사용
   
3. WARNING_MISSING_SHAPE_LOCATION (신규)
   → pptx의 shape/cell 보조 필드 누락 시 사용
   
4. WARNING_UNSUPPORTED_DOCX_SECTION (분리됨)
   → 이전 paragraph_not_in_body를 정확한 의미로 분리
```

---

## 10. 결론

17주차 시점의 detector 역할 분담:

```text
1. regex_detector: 명확한 패턴 → 자동 비식별화 (모든 등급)
2. NER (KoELECTRA): 한국인 성명 → 자동 마스킹
3. AI (privacy_cso_char_keras_model): 민감 후보 추천 → 사용자 검토
```

핵심 원칙:

```text
✓ 명확한 것은 자동 (regex, NER 성명)
✓ 불확실한 것은 사용자 판단 (AI 추천)
✓ 사용자 판단을 데이터로 누적해 모델 점진 개선 (피드백 학습)
✓ 회사 가이드라인 "불확실하면 상위 등급 유지" 정신 부합
```

코드는 이미 위 정책을 반영한 구조로 구현되어 있으며, 17주차에는 정책 명문화와 부채 정리만 수행했다.
