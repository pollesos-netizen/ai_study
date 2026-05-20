"""
비식별화 대상 계획 수립기

목적:
- regex, ner, ai Detection 목록을 입력받아 비식별화 계획(DeidentifyPlan)을 생성합니다.
- 10주차에서는 실제 원문을 수정하지 않고, 어디를 어떻게 비식별화할지 계획만 만듭니다.

핵심 정책:
- 자동 비식별화 대상: regex/ner 기반이며 matched와 start/end가 있는 Detection
- 검토 필요 대상: ai 기반 문장 전체 판단 또는 위치가 없는 Detection
- source 우선순위: regex > ner > ai
- 같은 source 내 겹침: 등급 높은 쪽 > matched 길이 긴 쪽 > 입력순서
- 겹쳐 제거된 Detection 정보는 유지된 target의 reason에 누적합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SOURCE_PRIORITY = {
    "regex": 1,
    "ner": 2,
    "ai": 3,
}

GRADE_PRIORITY = {
    "C": 3,
    "S": 2,
    "O": 1,
}


@dataclass
class DeidentifyTarget:
    label: str
    matched: str
    action: str
    location_label: str | None
    location_meta: dict[str, Any]
    start: int | None
    end: int | None
    source: str
    reason: str
    grade: str | None = None
    sensitive_type: str | None = None
    sensitive_category: str | None = None
    context: str | None = None
    order: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "matched": self.matched,
            "action": self.action,
            "locationLabel": self.location_label,
            "locationMeta": self.location_meta,
            "start": self.start,
            "end": self.end,
            "source": self.source,
            "reason": self.reason,
            "grade": self.grade,
            "sensitiveType": self.sensitive_type,
            "sensitiveCategory": self.sensitive_category,
            "context": self.context,
            "order": self.order,
        }


@dataclass
class DeidentifyPlan:
    auto_targets: list[DeidentifyTarget]
    review_targets: list[DeidentifyTarget]
    summary_grade: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "autoTargets": [target.to_dict() for target in self.auto_targets],
            "reviewTargets": [target.to_dict() for target in self.review_targets],
            "summaryGrade": self.summary_grade,
        }


def spans_overlap(
    a_start: int | None,
    a_end: int | None,
    b_start: int | None,
    b_end: int | None,
) -> bool:
    """
    두 구간이 겹치는지 판정합니다.

    인접한 구간은 겹침이 아닙니다.
    예: (3, 6)과 (6, 10)은 겹치지 않음
    """
    if a_start is None or a_end is None or b_start is None or b_end is None:
        return False

    return a_start < b_end and b_start < a_end


def source_priority(source: str | None) -> int:
    """
    source 우선순위를 반환합니다.

    숫자가 작을수록 우선순위가 높습니다.
    """
    return SOURCE_PRIORITY.get(str(source or "").lower(), 99)


def grade_priority(grade: str | None) -> int:
    """
    등급 우선순위를 반환합니다.

    숫자가 클수록 우선순위가 높습니다.
    """
    return GRADE_PRIORITY.get(str(grade or "").upper(), 0)


def matched_length(detection: dict[str, Any]) -> int:
    matched = detection.get("matched") or ""
    return len(str(matched))


def detection_order(detection: dict[str, Any]) -> int:
    return int(detection.get("_order", 0))


def same_location(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """
    같은 TextUnit 또는 같은 위치인지 판정합니다.

    locationMeta가 있으면 locationMeta를 우선 비교합니다.
    locationMeta는 11주차 Apply 단계에서 실제 원문 위치를 찾아가는 기준이므로,
    겹침 판정에서도 locationMeta를 우선 사용합니다.

    locationMeta가 없으면 locationLabel, context 순서로 fallback합니다.
    """
    a_meta = a.get("locationMeta")
    b_meta = b.get("locationMeta")

    if a_meta and b_meta:
        return a_meta == b_meta

    a_location = a.get("locationLabel")
    b_location = b.get("locationLabel")

    if a_location is not None or b_location is not None:
        return a_location == b_location

    return a.get("context") == b.get("context")


def choose_better_detection(
    current: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    두 Detection이 겹칠 때 유지할 Detection과 흡수될 Detection을 반환합니다.

    기준:
    1. source 우선순위
    2. 같은 source이면 등급 우선순위
    3. 등급도 같으면 matched 길이
    4. 그래도 같으면 입력 순서
    """
    current_source_priority = source_priority(current.get("source"))
    candidate_source_priority = source_priority(candidate.get("source"))

    if current_source_priority != candidate_source_priority:
        if current_source_priority < candidate_source_priority:
            return current, candidate
        return candidate, current

    current_grade_priority = grade_priority(current.get("grade"))
    candidate_grade_priority = grade_priority(candidate.get("grade"))

    if current_grade_priority != candidate_grade_priority:
        if current_grade_priority > candidate_grade_priority:
            return current, candidate
        return candidate, current

    current_length = matched_length(current)
    candidate_length = matched_length(candidate)

    if current_length != candidate_length:
        if current_length > candidate_length:
            return current, candidate
        return candidate, current

    if detection_order(current) <= detection_order(candidate):
        return current, candidate

    return candidate, current


def append_absorbed_reason(
    kept: dict[str, Any],
    absorbed: dict[str, Any],
) -> None:
    """
    흡수된 Detection 정보를 유지된 Detection의 reason에 누적합니다.
    """
    original_reason = str(kept.get("reason") or "")

    absorbed_info = (
        "중복 탐지 흡수: "
        f"source={absorbed.get('source')}, "
        f"label={absorbed.get('label')}, "
        f"matched={absorbed.get('matched')}"
    )

    if original_reason:
        kept["reason"] = f"{original_reason} / {absorbed_info}"
    else:
        kept["reason"] = absorbed_info


def detection_has_span(detection: dict[str, Any]) -> bool:
    return detection.get("start") is not None and detection.get("end") is not None


def is_auto_detection(detection: dict[str, Any]) -> bool:
    """
    자동 비식별화 대상 여부를 판단합니다.
    """
    source = str(detection.get("source") or "").lower()
    matched = detection.get("matched")

    return (
        source in {"regex", "ner"}
        and matched not in {None, ""}
        and detection_has_span(detection)
    )


def is_review_detection(detection: dict[str, Any]) -> bool:
    """
    검토 필요 대상 여부를 판단합니다.
    """
    source = str(detection.get("source") or "").lower()

    if source == "ai":
        return True

    return not is_auto_detection(detection)


def deduplicate_auto_detections(
    detections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    자동 비식별화 후보 Detection 목록에서 위치 겹침을 제거합니다.

    AI Detection은 이 함수에 들어오지 않는 것을 전제로 합니다.

    겹침이 발생하면 current와 candidate 중 더 적절한 Detection만 kept에 남기고,
    candidate를 새로 append하지 않습니다.
    """
    kept: list[dict[str, Any]] = []

    for candidate in detections:
        merged = False

        for index, current in enumerate(kept):
            if not same_location(current, candidate):
                continue

            if not spans_overlap(
                current.get("start"),
                current.get("end"),
                candidate.get("start"),
                candidate.get("end"),
            ):
                continue

            better, absorbed = choose_better_detection(current, candidate)
            append_absorbed_reason(better, absorbed)

            kept[index] = better
            merged = True
            break

        if not merged:
            kept.append(candidate)

    return kept


def detection_to_target(detection: dict[str, Any]) -> DeidentifyTarget:
    """
    Detection dict를 DeidentifyTarget으로 변환합니다.
    """
    return DeidentifyTarget(
        label=str(detection.get("label") or ""),
        matched=str(detection.get("matched") or ""),
        action=str(detection.get("action") or "검토 필요"),
        location_label=detection.get("locationLabel"),
        location_meta=detection.get("locationMeta") or {},
        start=detection.get("start"),
        end=detection.get("end"),
        source=str(detection.get("source") or ""),
        reason=str(detection.get("reason") or ""),
        grade=detection.get("grade"),
        sensitive_type=detection.get("sensitiveType"),
        sensitive_category=detection.get("sensitiveCategory"),
        context=detection.get("context"),
        order=detection_order(detection),
    )


def location_key_for_target(target: DeidentifyTarget) -> str:
    """
    정렬 및 묶음 처리를 위한 위치 키를 생성합니다.

    locationMeta를 우선 사용하고, 없으면 locationLabel, context 순서로 fallback합니다.
    """
    if target.location_meta:
        return repr(sorted(target.location_meta.items()))

    if target.location_label is not None:
        return f"label:{target.location_label}"

    if target.context is not None:
        return f"context:{target.context}"

    return f"order:{target.order}"


def sort_targets(targets: list[DeidentifyTarget]) -> list[DeidentifyTarget]:
    """
    DeidentifyTarget 목록을 표시 순서대로 정렬합니다.

    1. location의 첫 등장 순서
    2. 같은 location 내부에서는 start 오름차순
    3. start가 None인 target은 같은 location의 뒤쪽

    실제 Apply 단계에서는 같은 location 내부에서 start 내림차순으로 적용해야 합니다.
    이 정렬은 사용자 표시와 계획 검토용 정렬입니다.
    """
    first_order_by_location: dict[str, int] = {}

    for target in targets:
        key = location_key_for_target(target)

        if key not in first_order_by_location:
            first_order_by_location[key] = target.order

    return sorted(
        targets,
        key=lambda target: (
            first_order_by_location.get(location_key_for_target(target), target.order),
            target.start is None,
            target.start if target.start is not None else 10**9,
        ),
    )


def calculate_summary_grade_from_targets(
    auto_targets: list[DeidentifyTarget],
    review_targets: list[DeidentifyTarget],
) -> str | None:
    """
    부가 요약값으로 최고 등급을 계산합니다.

    입력 Detection 전체가 아니라, 최종 DeidentifyPlan에 남은 target 기준으로 계산합니다.
    grade가 None인 target은 제외합니다.
    """
    grades = [
        target.grade
        for target in [*auto_targets, *review_targets]
        if target.grade
    ]

    if not grades:
        return None

    return max(grades, key=grade_priority)


def build_deidentify_plan(
    detections: list[dict[str, Any]],
) -> DeidentifyPlan:
    """
    Detection 목록을 DeidentifyPlan으로 변환합니다.
    """
    ordered_detections: list[dict[str, Any]] = []

    for order, detection in enumerate(detections):
        copied = dict(detection)
        copied["_order"] = order
        ordered_detections.append(copied)

    auto_candidates = [
        detection
        for detection in ordered_detections
        if is_auto_detection(detection)
    ]

    review_candidates = [
        detection
        for detection in ordered_detections
        if is_review_detection(detection)
    ]

    deduplicated_auto = deduplicate_auto_detections(auto_candidates)

    auto_targets = sort_targets(
        [detection_to_target(detection) for detection in deduplicated_auto]
    )

    review_targets = sort_targets(
        [detection_to_target(detection) for detection in review_candidates]
    )

    return DeidentifyPlan(
        auto_targets=auto_targets,
        review_targets=review_targets,
        summary_grade=calculate_summary_grade_from_targets(
            auto_targets,
            review_targets,
        ),
    )
