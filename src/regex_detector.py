import re
from dataclasses import dataclass
from typing import Pattern


@dataclass
class DetectionResult:
    id: str
    label: str
    value: str
    start: int
    end: int
    grade: str
    action: str
    desc: str


# 주의:
# Python 정규식의 \b는 한글 조사와 붙은 값에서 예상대로 동작하지 않을 수 있습니다.
# 예: "900101-1234567이", "test@example.com입니다"
# 따라서 숫자/영문 경계를 직접 지정하는 방식으로 작성합니다.


PATTERNS = [
    {
        "id": "rrn",
        "label": "주민등록번호",
        "grade": "C",
        "action": "삭제",
        "pattern": r"(?<!\d)\d{6}[-–]\d{7}(?!\d)",
        "flags": 0,
        "desc": "고유식별정보 — 외부 AI 입력 금지",
    },
    {
        "id": "passport",
        "label": "여권번호",
        "grade": "C",
        "action": "삭제",
        "pattern": r"(?<![A-Za-z0-9])[A-Z]{1,2}\d{7,9}(?![A-Za-z0-9])",
        "flags": 0,
        "desc": "고유식별정보",
    },
    {
        "id": "ip",
        "label": "내부 IP 주소",
        "grade": "C",
        "action": "삭제",
        "pattern": (
            r"(?<![\d.])"
            r"(10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
            r"|192\.168\.\d{1,3}\.\d{1,3})"
            r"(?![\d.])"
        ),
        "flags": 0,
        "desc": "내부 네트워크 정보 — 사이버 공격 악용 위험",
    },
    {
        "id": "phone",
        "label": "전화번호",
        "grade": "S",
        "action": "마스킹",
        "pattern": r"(?<!\d)0\d{1,2}[-–·]?\d{3,4}[-–·]?\d{4}(?!\d)",
        "flags": 0,
        "desc": "직접 식별 가능한 개인정보",
    },
    {
        "id": "email",
        "label": "이메일 주소",
        "grade": "S",
        "action": "마스킹",
        "pattern": (
            r"(?<![A-Za-z0-9._%+\-])"
            r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
            r"(?![A-Za-z0-9.\-])"
        ),
        "flags": re.IGNORECASE,
        "desc": "직접 식별 가능한 개인정보",
    },
    {
        "id": "empid",
        "label": "사번",
        "grade": "S",
        "action": "마스킹",
        "pattern": r"(?<![A-Za-z0-9])[A-Za-z]{2}\d{6}(?![A-Za-z0-9])",
        "flags": 0,
        "desc": "사번 — 개인 식별 가능 정보",
    },
    {
        "id": "account",
        "label": "계좌번호",
        "grade": "S",
        "action": "마스킹",
        "pattern": (
            r"(?<!\d)"
            r"(?:"
            r"\d{3}-\d{2}-\d{4}-\d{3}"
            r"|\d{4}-\d{3}-\d{6}"
            r"|\d{3}-\d{6}-\d{5}"
            r"|\d{3}-\d{2}-\d{6}"
            r"|\d{3}-\d{6}-\d{2}-\d{3}"
            r"|\d{3}-\d{4}-\d{4}-\d{2}"
            r"|\d{4}-\d{4}-\d{4}-\d{1}"
            r"|\d{6}-\d{2}-\d{6}"
            r"|\d{4}-\d{2}-\d{7}"
            r"|\d{3}-\d{6}-\d{3}"
            r"|\d{2}-\d{2}-\d{6}"
            r"|\d{3}-\d{2}-\d{6}-\d{1}"
            r"|\d{3}-\d{4}-\d{4}-\d{3}"
            r"|\d{10,14}"
            r")"
            r"(?!\d)"
        ),
        "flags": 0,
        "desc": "계좌번호 — 은행별 패턴 및 하이픈 없는 10~14자리 포함",
    },
    {
        "id": "freq",
        "label": "무선 주파수",
        "grade": "S",
        "action": "치환",
        "pattern": r"(?<!\d)\d{2,3}\.\d{3,4}\s*[MG]Hz(?![A-Za-z0-9])",
        "flags": re.IGNORECASE,
        "desc": "통신 보안 정보 — 도청·혼신 위험",
    },
    {
        "id": "coord",
        "label": "정밀 위치(키로정)",
        "grade": "S",
        "action": "범주화",
        "pattern": r"(?<![A-Za-z0-9])\d{1,3}K\d{3}(?![A-Za-z0-9])",
        "flags": re.IGNORECASE,
        "desc": "정밀 위치정보 — 범위로 범주화 권장",
    },
    {
        "id": "datetime_precise",
        "label": "정밀 시각",
        "grade": "S",
        "action": "범주화",
        "pattern": r"(?<!\d)([01]\d|2[0-3]):[0-5]\d:[0-5]\d(?!\d)",
        "flags": 0,
        "desc": "정밀 시각 — 보안 공백과 결합 시 범주화 권장",
    },
    {
        "id": "vlan_port",
        "label": "VLAN/포트 정보",
        "grade": "C",
        "action": "삭제",
        "pattern": (
            r"(?<![A-Za-z0-9])VLAN\s*\d+(?!\d)"
            r"|(?<![A-Za-z0-9])port\s*\d{2,5}(?!\d)"
        ),
        "flags": re.IGNORECASE,
        "desc": "내부 네트워크 구성 정보",
    },
]


def compile_pattern(item: dict) -> Pattern:
    return re.compile(item["pattern"], item.get("flags", 0))


def detect_patterns(text: str) -> list[DetectionResult]:
    results: list[DetectionResult] = []

    for item in PATTERNS:
        regex = compile_pattern(item)

        for match in regex.finditer(text):
            results.append(
                DetectionResult(
                    id=item["id"],
                    label=item["label"],
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                    grade=item["grade"],
                    action=item["action"],
                    desc=item["desc"],
                )
            )

    return results


def get_max_grade(results: list[DetectionResult]) -> str:
    priority = {
        "O": 0,
        "S": 1,
        "C": 2,
    }

    if not results:
        return "O"

    return max((r.grade for r in results), key=lambda grade: priority[grade])


def print_detection_result(text: str) -> None:
    print(f"\n문장: {text}")
    detections = detect_patterns(text)

    if not detections:
        print("탐지 없음")
        return

    for result in detections:
        print(
            f"- {result.label}: {result.value} "
            f"[{result.grade}, {result.action}] "
            f"위치={result.start}:{result.end}"
        )

    print("최고 등급:", get_max_grade(detections))


if __name__ == "__main__":
    samples = [
        "주민등록번호 900101-1234567이 포함되어 있습니다.",
        "여권번호 M12345678이 포함되어 있습니다.",
        "담당자 연락처는 010-1234-5678이고 이메일은 test@example.com입니다.",
        "CD789012 사번 직원의 출입 기록을 확인해 주세요.",
        "서버 IP는 192.168.0.1이고 VLAN 100, port 8080을 사용합니다.",
        "무선설비 주파수 75.450MHz가 기재되어 있습니다.",
        "보안 패치 적용은 02:05:30부터 시작됩니다.",
        "37K500 지점에 설비가 있습니다.",
        "최지연 씨의 서류가 접수되었습니다.",
    ]

    for sample in samples:
        print_detection_result(sample)
