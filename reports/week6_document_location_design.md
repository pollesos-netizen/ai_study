# 6주차 문서 위치 추적 구조 설계

## 1. 목적

6주차의 목적은 기존 문장 단위 개인정보/민감정보 탐지기를 문서 위치 기반 탐지 구조로 확장하는 것이다.

기존 구조는 다음과 같았다.

```text
문장 입력
→ 정규식 탐지
→ AI 문장분류
→ C/S/O 등급 판단
```

6주차에서는 이를 다음 구조로 확장한다.

```text
문서 입력
→ 문서 유형별 파싱
→ 위치 정보가 포함된 TextUnit 생성
→ TextUnit별 정규식/AI 탐지
→ Detection 결과 생성
→ 사용자에게 탐지 위치 표시
→ 필요 시 문서 전체 최고 등급 계산
```

중요한 점은 문서 전체 등급 판단이 주목적이 아니라는 것이다.

```text
핵심 목적:
개인정보, 법령상 민감정보, 업무상 민감정보가
문서의 어느 위치에서 탐지되었는지 사용자에게 알려주는 것
```

---

## 2. 기존 구조의 한계

5주차까지 구현한 하이브리드 탐지 구조는 문장 하나를 입력받아 정규식 탐지와 AI 문장분류를 수행했다.

예시:

```python
hybrid_classify("담당자 이메일은 test@example.com입니다.", ai_model)
```

이 구조는 문장 자체의 등급 판단에는 사용할 수 있지만, 실제 문서 파일에서는 다음 문제가 있다.

```text
1. 탐지된 정보가 문서 어디에 있는지 알기 어렵다.
2. XLSX 파일의 경우 시트명과 셀 주소가 필요하다.
3. PPTX 파일의 경우 몇 번째 슬라이드인지 알아야 한다.
4. DOCX/HWPX 파일의 경우 몇 번째 문단인지 알아야 한다.
5. PDF 파일의 경우 몇 페이지에서 탐지되었는지 알아야 한다.
6. 향후 비식별화를 하려면 내부 위치 메타데이터가 필요하다.
```

따라서 텍스트와 위치 정보를 함께 보관하는 공통 구조가 필요하다.

---

## 3. TextUnit 개념

TextUnit은 문서 파서가 생성하는 분석 단위이다.

문서 전체를 한 번에 분석하지 않고, 문서 유형별로 의미 있는 단위로 나누어 분석한다.

```text
PPTX → 슬라이드 단위
XLSX → 셀 단위
HWPX → 문단 단위
DOCX → 문단 단위
PDF → 페이지 또는 줄 단위
```

TextUnit 기본 구조는 다음과 같다.

```python
TextUnit(
    text="담당자 이메일은 test@example.com입니다.",
    location_label="계약내역 탭 B12 셀",
    location_meta={
        "fileType": "xlsx",
        "sheetName": "계약내역",
        "cellRef": "B12",
        "row": 12,
        "col": 2,
    },
)
```

각 필드의 의미는 다음과 같다.

| 필드 | 의미 |
|---|---|
| `text` | 정규식/AI 탐지 대상 텍스트 |
| `location_label` | 사용자에게 보여줄 위치 정보 |
| `location_meta` | 비식별화 또는 원문 수정 시 사용할 내부 위치 정보 |

Python 코드에서는 `location_label`, `location_meta`처럼 snake_case를 사용한다.

다만 프론트엔드나 API 응답에서는 다음처럼 camelCase 형태로 변환할 수 있다.

```json
{
  "text": "담당자 이메일은 test@example.com입니다.",
  "locationLabel": "계약내역 탭 B12 셀",
  "locationMeta": {
    "fileType": "xlsx",
    "sheetName": "계약내역",
    "cellRef": "B12",
    "row": 12,
    "col": 2
  }
}
```

---

## 4. locationLabel과 locationMeta 분리

위치 정보는 사용자 표시용과 내부 처리용으로 분리한다.

### locationLabel

사용자가 문서를 열고 찾아갈 수 있는 수준의 위치 정보이다.

예시:

```text
3번째 슬라이드
계약내역 탭 B12 셀
17번째 문단
5페이지
```

### locationMeta

프로그램이 비식별화하거나 원본 문서를 수정할 때 사용할 내부 위치 정보이다.

예시:

```python
{
    "fileType": "xlsx",
    "sheetName": "계약내역",
    "cellRef": "B12",
    "row": 12,
    "col": 2
}
```

사용자 화면에는 기본적으로 `locationLabel`만 표시하고, `locationMeta`는 숨겨서 보관한다.

이렇게 분리하는 이유는 다음과 같다.

```text
1. 사용자에게는 찾기 쉬운 위치만 보여주는 것이 좋다.
2. 프로그램은 원문 수정과 비식별화를 위해 더 세밀한 위치 정보가 필요하다.
3. PPTX의 shapeIndex, PDF의 bbox처럼 사용자에게는 의미가 낮은 정보도 내부 처리에는 필요할 수 있다.
```

---

## 5. 파일 형식별 위치 정책

파일 형식별 위치 표시 정책은 다음과 같다.

| 파일 형식 | 사용자 표시 위치 | 내부 메타데이터 |
|---|---|---|
| PPTX | 3번째 슬라이드 | `slideIndex`, `slideNo`, 필요 시 `shapeIndex`, `paragraphIndex` |
| XLSX | 계약내역 탭 B12 셀 | `sheetName`, `cellRef`, `row`, `col` |
| HWPX | 17번째 문단 | `sectionIndex`, `paragraphIndex`, `paragraphNo`, `xmlPath` |
| DOCX | 17번째 문단 | `paragraphIndex`, `paragraphNo`, 필요 시 `tableIndex` |
| PDF | 5페이지 | `pageIndex`, `pageNo`, 필요 시 `lineIndex`, `bbox` |
| HWP | 추출된 문단/구간 | 파싱 가능 범위에 따라 별도 관리 |

중요 판단은 다음과 같다.

```text
PPTX의 텍스트박스 번호,
DOCX/HWPX의 표 번호,
PDF 좌표값은 일반 사용자에게는 의미가 낮을 수 있다.

다만 향후 자동 비식별화에는 필요할 수 있으므로
locationMeta에 숨겨서 보관한다.
```

XLSX는 예외적으로 위치를 정밀하게 표시해야 한다.

```text
XLSX는 사용자가 실제 조치하려면
시트명 + 셀 주소가 필요하다.
```

예시:

```text
계약내역 탭 B12 셀
```

---

## 6. Detection 결과 구조

Detection은 TextUnit을 분석한 결과이다.

정규식 또는 AI가 탐지한 결과를 다음 구조로 통일한다.

```python
Detection(
    label="이메일 주소",
    matched="test@example.com",
    grade="S",
    action="마스킹",
    source="regex",
    context="담당자 이메일은 test@example.com입니다.",
    location_label="계약내역 탭 B12 셀",
    location_meta={
        "fileType": "xlsx",
        "sheetName": "계약내역",
        "cellRef": "B12",
        "row": 12,
        "col": 2,
    },
    start=9,
    end=25,
    reason="직접 식별 가능한 개인정보",
)
```

각 필드의 의미는 다음과 같다.

| 필드 | 의미 |
|---|---|
| `label` | 탐지 항목명 |
| `matched` | 실제 탐지 문자열 |
| `grade` | C/S/O 등급 |
| `action` | 권장 조치 |
| `source` | `regex`, `ai`, `rule` |
| `context` | 탐지 문맥 |
| `location_label` | 사용자 표시 위치 |
| `location_meta` | 내부 처리 위치 |
| `start`, `end` | `TextUnit.text` 안에서의 위치 |
| `sensitive_type` | 법령상 민감정보 / 업무상 민감정보 등 |
| `sensitive_category` | 입찰평가, 계약정보, 건강정보 등 세부 분류 |
| `reason` | 판단 근거 |

AI 탐지 결과는 정규식 탐지처럼 특정 문자열이 없을 수 있으므로 `matched`는 빈 문자열로 둘 수 있다.

예시:

```python
Detection(
    label="민감정보",
    matched="",
    grade="S",
    action="검토 필요",
    source="ai",
    context="입찰 제안 평가표를 검토했습니다.",
    location_label="17번째 문단",
    location_meta={
        "fileType": "docx",
        "paragraphNo": 17,
    },
    reason="정규식 탐지 없음 — AI 문장분류 결과 적용",
)
```

---

## 7. document_units.py 역할

6주차에서는 공통 자료구조를 담당하는 파일을 추가했다.

```text
src/document_units.py
```

주요 역할은 다음과 같다.

```text
1. TextUnit 구조 정의
2. Detection 구조 정의
3. TextUnit을 dict로 변환
4. Detection을 dict로 변환
5. 정규식 탐지 결과를 Detection으로 변환
6. AI 탐지 결과를 Detection으로 변환
7. 문서 전체 최고 등급 계산
```

주요 클래스는 다음과 같다.

```python
@dataclass
class TextUnit:
    text: str
    location_label: str
    location_meta: dict[str, Any]
```

```python
@dataclass
class Detection:
    label: str
    matched: str
    grade: Grade
    action: str
    source: DetectionSource
    context: str
    location_label: str
    location_meta: dict[str, Any]
    start: int | None = None
    end: int | None = None
    sensitive_type: str | None = None
    sensitive_category: str | None = None
    reason: str | None = None
```

6주차에서는 `sensitive_type`, `sensitive_category`를 필수로 사용하지 않는다.

다만 7주차 다중 속성 라벨 구조에서 업무상 민감정보를 세분화할 수 있도록 미리 확장 필드로 둔다.

---

## 8. TextUnit 기반 탐지 흐름

기존 함수는 문자열만 입력받았다.

```python
hybrid_classify(text, ai_model)
```

6주차에서는 TextUnit을 입력받는 함수를 추가했다.

```python
hybrid_classify_text_unit(text_unit, ai_model)
```

처리 흐름은 다음과 같다.

```text
TextUnit 입력
→ text_unit.text를 hybrid_classify에 전달
→ 정규식/AI 탐지 수행
→ 탐지 결과에 location_label, location_meta 추가
→ Detection 목록 반환
```

여러 TextUnit을 분석하기 위해 다음 함수도 추가했다.

```python
analyze_text_units(text_units, ai_model)
```

처리 흐름은 다음과 같다.

```text
TextUnit 목록 입력
→ 각 TextUnit별 hybrid_classify_text_unit 실행
→ Detection 목록 병합
→ 전체 Detection 목록 반환
```

---

## 9. 테스트 결과

TextUnit 기반 탐지 테스트 결과는 다음과 같다.

```text
=== TextUnit 기반 탐지 테스트 ===

탐지 결과:

[1] 계약내역 탭 B12 셀
  - 탐지 항목: 이메일 주소
  - 탐지 값: test@example.com
  - 등급: S
  - 조치: 마스킹
  - 탐지 방식: regex
  - 문맥: 담당자 이메일은 test@example.com입니다.
  - 판단 근거: 직접 식별 가능한 개인정보

[2] 시스템정보 탭 C3 셀
  - 탐지 항목: 내부 IP 주소
  - 탐지 값: 192.168.0.1
  - 등급: C
  - 조치: 삭제
  - 탐지 방식: regex
  - 문맥: 서버 IP는 192.168.0.1이고 VLAN 100을 사용합니다.
  - 판단 근거: 내부 네트워크 정보 — 사이버 공격 악용 위험

[3] 시스템정보 탭 C3 셀
  - 탐지 항목: VLAN/포트 정보
  - 탐지 값: VLAN 100
  - 등급: C
  - 조치: 삭제
  - 탐지 방식: regex
  - 문맥: 서버 IP는 192.168.0.1이고 VLAN 100을 사용합니다.
  - 판단 근거: 내부 네트워크 구성 정보

[4] 17번째 문단
  - 탐지 항목: 민감정보
  - 탐지 값: 문장 전체 판단
  - 등급: S
  - 조치: 검토 필요
  - 탐지 방식: ai
  - 문맥: 입찰 제안 평가표를 검토했습니다.
  - 판단 근거: 정규식 탐지 없음 — AI 문장분류 결과 적용

문서 전체 최고 등급: C
```

이 결과를 통해 다음을 확인했다.

```text
1. TextUnit 위치 정보가 Detection 결과에 정상 반영된다.
2. XLSX의 시트명 + 셀 주소가 정상 표시된다.
3. 정규식 탐지 결과와 AI 탐지 결과가 같은 Detection 구조로 출력된다.
4. AI 탐지 결과는 특정 matched 문자열이 없어도 context와 locationLabel로 위치 확인이 가능하다.
5. 문서 전체 등급은 Detection 목록에서 부가적으로 계산할 수 있다.
```

---

## 10. 문서 전체 등급 산정 방식

문서 전체 등급은 Detection 목록에서 최고 등급을 선택해 계산한다.

```python
document_grade = get_document_grade(detections)
```

등급 우선순위는 다음과 같다.

```text
O < S < C
```

다만 문서 전체 등급은 부가 기능이다.

우선순위는 다음과 같다.

```text
1순위: 어디에서 무엇이 탐지되었는가
2순위: 해당 탐지 항목의 등급과 조치 방식은 무엇인가
3순위: 문서 전체 최고 등급은 무엇인가
```

즉, 문서 전체 등급은 탐지 결과 목록을 요약하는 보조 정보로 사용한다.

---

## 11. 업무상 민감정보 반영 방향

이번 설계에서는 민감정보를 법령상 민감정보에만 한정하지 않는다.

```text
민감정보에는 법령상 민감정보와 업무상 민감정보가 모두 포함된다.
```

업무상 민감정보 예시는 다음과 같다.

```text
계약정보
입찰정보
평가자료
인사·징계 정보
내부 운영정보
보안 운영정보
장애·사고 대응 정보
```

업무상 민감정보도 최종 Detection 결과에서는 C/S/O 등급으로 표현되어야 한다.

예시:

```python
Detection(
    label="입찰 평가자료",
    matched="",
    grade="S",
    action="검토 필요",
    source="ai",
    context="입찰 제안 평가표를 검토했습니다.",
    location_label="17번째 문단",
    sensitive_type="업무상 민감정보",
    sensitive_category="입찰평가",
)
```

다만 업무상 민감정보의 세부 라벨 구조는 7주차 다중 속성 라벨 설계에서 구체화한다.

6주차에서는 다음 원칙만 반영한다.

```text
업무상 민감정보도 Detection 구조에 담길 수 있어야 한다.
업무상 민감정보도 최종적으로 C/S/O 등급으로 연결되어야 한다.
```

---

## 12. App.jsx 적용 방향

현재 6주차 구현은 Python 구조를 먼저 설계한다.

App.jsx는 향후 다음 방향으로 수정한다.

기존 구조:

```js
{ text, location }
```

수정 구조:

```js
{
  text,
  locationLabel,
  locationMeta
}
```

특히 XLSX 파서는 다음 위치 표시가 가능해야 한다.

```js
locationLabel: `${sheetName} 탭 ${cellRef} 셀`
```

다만 App.jsx 수정은 별도 단계로 진행한다.

현재 단계에서는 Python의 `TextUnit`, `Detection` 구조를 먼저 고정한다.

---

## 13. 결론

6주차에서는 문장 단위 탐지기를 문서 위치 기반 탐지 구조로 확장했다.

핵심 성과는 다음과 같다.

```text
1. TextUnit 구조를 정의했다.
2. Detection 구조를 정의했다.
3. locationLabel과 locationMeta를 분리했다.
4. 정규식 탐지 결과와 AI 탐지 결과를 같은 Detection 구조로 통일했다.
5. TextUnit 기반 탐지 함수 hybrid_classify_text_unit을 추가했다.
6. 여러 TextUnit을 분석하는 analyze_text_units 함수를 추가했다.
7. 탐지 결과를 사용자 친화적으로 출력하는 print_detections 함수를 추가했다.
8. 문서 전체 최고 등급은 부가 기능으로 분리했다.
9. 업무상 민감정보도 C/S/O 등급으로 연결될 수 있도록 구조를 열어두었다.
```

6주차의 핵심 결론은 다음이다.

```text
탐지기는 이제 단순히 문장이 민감한지 판단하는 도구가 아니라,
문서 안의 어느 위치에서 어떤 정보가 탐지되었는지 알려주는 구조로 확장되었다.
```

---

## 14. 다음 단계

6주차의 남은 작업은 코드와 문서의 용어를 맞추고, 최종 점검하는 것이다.

점검 항목은 다음과 같다.

```text
1. document_units.py의 TextUnit, Detection 필드명이 문서와 일치하는가
2. hybrid_detector_v2.py의 hybrid_classify_text_unit이 Detection 목록을 반환하는가
3. analyze_text_units가 여러 TextUnit을 처리하는가
4. print_detections 출력이 사용자에게 이해 가능한가
5. 문서 전체 최고 등급이 Detection 목록에서 계산되는가
6. 업무상 민감정보도 C/S/O 등급으로 연결될 수 있도록 구조가 열려 있는가
7. App.jsx 수정은 별도 단계로 분리되어 있는가
```

이후 7주차에서는 다중 속성 라벨 구조를 설계한다.

```text
개인정보 포함 여부
법령상 민감정보 포함 여부
업무상 민감정보 포함 여부
C/S/O 등급
조치 방식
세부 민감정보 유형
```
