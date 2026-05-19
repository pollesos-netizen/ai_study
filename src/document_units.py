from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Grade = Literal["C", "S", "O"]
DetectionSource = Literal["regex", "ai", "rule"]


@dataclass
class TextUnit:
    """
    문서 파서가 생성하는 분석 단위입니다.

    예:
    - PPTX: 슬라이드 단위
    - XLSX: 셀 단위
    - DOCX/HWPX: 문단 단위
    - PDF: 페이지 또는 줄 단위

    text:
        정규식/AI 탐지 대상 텍스트입니다.

    location_label:
        사용자에게 보여줄 위치 정보입니다.
        예: "3번째 슬라이드", "계약내역 탭 B12 셀", "17번째 문단"

    location_meta:
        비식별화나 원문 수정 시 사용할 내부 위치 정보입니다.
        예: {"fileType": "xlsx", "sheetName": "계약내역", "cellRef": "B12"}
    """

    text: str
    location_label: str
    location_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Python 내부 구조를 dict로 변환합니다.

        내부 Python 코드에서는 snake_case를 사용하고,
        화면/API로 넘길 때는 locationLabel/locationMeta 형태로 변환합니다.
        """
        return {
            "text": self.text,
            "locationLabel": self.location_label,
            "locationMeta": self.location_meta,
        }


@dataclass
class Detection:
    """
    TextUnit을 분석한 결과입니다.

    개인정보, 법령상 민감정보, 업무상 민감정보가 탐지되었을 때
    탐지 항목, 등급, 조치 방식, 위치 정보를 함께 보관합니다.
    """

    label: str
    matched: str
    grade: Grade
    action: str
    source: DetectionSource
    context: str
    location_label: str
    location_meta: dict[str, Any] = field(default_factory=dict)
    start: int | None = None
    end: int | None = None

    # 7주차 다중 속성 라벨 구조를 위한 확장 필드입니다.
    # 6주차에서는 필수로 사용하지 않아도 됩니다.
    sensitive_type: str | None = None
    sensitive_category: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        화면/API 전달용 dict로 변환합니다.

        프론트엔드에서 사용하기 쉽도록 locationLabel, locationMeta처럼
        camelCase 필드명을 사용합니다.
        """
        return {
            "label": self.label,
            "matched": self.matched,
            "grade": self.grade,
            "action": self.action,
            "source": self.source,
            "context": self.context,
            "locationLabel": self.location_label,
            "locationMeta": self.location_meta,
            "start": self.start,
            "end": self.end,
            "sensitiveType": self.sensitive_type,
            "sensitiveCategory": self.sensitive_category,
            "reason": self.reason,
        }


def text_unit_from_dict(data: dict[str, Any]) -> TextUnit:
    """
    dict 형태의 데이터를 TextUnit으로 변환합니다.

    App.jsx나 외부 파서에서 넘어온 데이터가
    locationLabel/locationMeta 구조일 때 사용할 수 있습니다.
    """
    return TextUnit(
        text=data["text"],
        location_label=data.get("locationLabel") or data.get("location_label", "위치 정보 없음"),
        location_meta=data.get("locationMeta") or data.get("location_meta", {}),
    )


def detection_from_regex_result(
    regex_result: Any,
    text_unit: TextUnit,
) -> Detection:
    """
    regex_detector.DetectionResult를 6주차 Detection 구조로 변환합니다.

    regex_detector.py의 DetectionResult는 value 필드를 사용하고,
    6주차 Detection은 matched 필드를 사용합니다.
    """
    return Detection(
        label=regex_result.label,
        matched=regex_result.value,
        grade=regex_result.grade,
        action=regex_result.action,
        source="regex",
        context=text_unit.text,
        location_label=text_unit.location_label,
        location_meta=text_unit.location_meta,
        start=regex_result.start,
        end=regex_result.end,
        reason=regex_result.desc,
    )


def detection_from_ai_result(
    label: str,
    grade: Grade,
    text_unit: TextUnit,
    action: str = "검토 필요",
    sensitive_type: str | None = None,
    sensitive_category: str | None = None,
    reason: str | None = None,
) -> Detection:
    """
    AI 문장분류 결과를 6주차 Detection 구조로 변환합니다.

    AI 결과는 이메일, 주민등록번호처럼 특정 matched 문자열이 없을 수 있으므로
    matched는 빈 문자열로 둡니다.
    """
    return Detection(
        label=label,
        matched="",
        grade=grade,
        action=action,
        source="ai",
        context=text_unit.text,
        location_label=text_unit.location_label,
        location_meta=text_unit.location_meta,
        start=None,
        end=None,
        sensitive_type=sensitive_type,
        sensitive_category=sensitive_category,
        reason=reason,
    )


GRADE_PRIORITY = {
    "O": 0,
    "S": 1,
    "C": 2,
}


def select_highest_grade(grades: list[str]) -> str:
    """
    여러 등급 중 가장 높은 등급을 반환합니다.

    문서 전체 등급 산정 시 사용합니다.
    단, 문서 전체 등급은 부가 기능이고,
    핵심은 Detection 목록의 위치 정보입니다.
    """
    if not grades:
        return "O"

    return max(grades, key=lambda grade: GRADE_PRIORITY.get(grade, 0))


def get_document_grade(detections: list[Detection]) -> str:
    """
    Detection 목록에서 문서 전체 최고 등급을 계산합니다.
    """
    return select_highest_grade([detection.grade for detection in detections])


def detections_to_dicts(detections: list[Detection]) -> list[dict[str, Any]]:
    """
    Detection 목록을 화면/API 전달용 dict 목록으로 변환합니다.
    """
    return [detection.to_dict() for detection in detections]


if __name__ == "__main__":
    # 간단한 구조 확인용 샘플입니다.
    sample_unit = TextUnit(
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

    sample_detection = Detection(
        label="이메일 주소",
        matched="test@example.com",
        grade="S",
        action="마스킹",
        source="regex",
        context=sample_unit.text,
        location_label=sample_unit.location_label,
        location_meta=sample_unit.location_meta,
        start=8,
        end=24,
        reason="직접 식별 가능한 개인정보",
    )

    print(sample_unit.to_dict())
    print(sample_detection.to_dict())
    print("문서 전체 등급:", get_document_grade([sample_detection]))