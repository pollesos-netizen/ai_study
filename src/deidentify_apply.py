"""
11주차 텍스트 단위 비식별화 Apply 엔진

목적:
- DeidentifyTarget 목록을 원문 문자열에 적용해 비식별화된 문자열을 생성합니다.
- 11주차에서는 실제 xlsx/docx/pptx/hwpx 파일을 수정하지 않고, 문자열 단위 PoC만 수행합니다.

핵심 정책:
- apply_targets_to_text()는 자동 적용 대상(auto_targets) 중심으로 동작합니다.
- 같은 문자열 내에서는 start 내림차순으로 적용합니다.
- 마스킹 길이는 matched 길이가 아니라 text[start:end] 길이를 기준으로 합니다.
- start/end 오류는 조용히 클리핑하지 않고 skip + warning 처리합니다.
- matched와 text[start:end]가 다르면 warning을 남기되, 범위가 유효하면 적용합니다.
- 삭제 action은 기본적으로 실제 삭제("")를 수행합니다.
- 사용자 확인용 preview가 필요할 때만 deletion_mode="mark"로 "(삭제됨)"을 표시합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from src.deidentify_target_builder import DeidentifyPlan, DeidentifyTarget
except ModuleNotFoundError:
    from deidentify_target_builder import DeidentifyPlan, DeidentifyTarget


DEFAULT_DELETION_MODE = "delete"
DELETE_MARKER = "(삭제됨)"


@dataclass
class SkippedTarget:
    target: DeidentifyTarget
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "reason": self.reason,
        }


@dataclass
class ApplyResult:
    original_text: str
    applied_text: str
    applied_targets: list[DeidentifyTarget]
    skipped_targets: list[SkippedTarget]
    warnings: list[str]
    location_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "locationKey": self.location_key,
            "originalText": self.original_text,
            "appliedText": self.applied_text,
            "appliedTargets": [target.to_dict() for target in self.applied_targets],
            "skippedTargets": [skipped.to_dict() for skipped in self.skipped_targets],
            "warnings": self.warnings,
        }


@dataclass
class ApplyPlanResult:
    text_results: list[ApplyResult]
    review_targets: list[DeidentifyTarget]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "textResults": [result.to_dict() for result in self.text_results],
            "reviewTargets": [target.to_dict() for target in self.review_targets],
            "warnings": self.warnings,
        }


def mask_text(length: int, mask_char: str = "*") -> str:
    """
    지정한 길이만큼 마스킹 문자열을 생성합니다.
    """
    return mask_char * max(length, 0)


def location_key_for_target(target: DeidentifyTarget) -> str:
    """
    locationMeta → locationLabel → context 순서로 위치 키를 생성합니다.
    """
    if target.location_meta:
        return repr(sorted(target.location_meta.items()))

    if target.location_label is not None:
        return f"label:{target.location_label}"

    if target.context is not None:
        return f"context:{target.context}"

    return f"order:{target.order}"


def validate_target_range(text: str, target: DeidentifyTarget) -> str | None:
    """
    target의 start/end 범위를 검증합니다.

    오류가 있으면 오류 메시지를 반환하고, 정상이라면 None을 반환합니다.
    """
    if target.start is None or target.end is None:
        return "start 또는 end가 None입니다."

    if target.start < 0:
        return f"start가 0보다 작습니다: start={target.start}"

    if target.end > len(text):
        return f"end가 원문 길이를 초과합니다: end={target.end}, text_len={len(text)}"

    if target.start >= target.end:
        return f"start가 end보다 크거나 같습니다: start={target.start}, end={target.end}"

    return None


def replacement_for_target(
    actual_text: str,
    target: DeidentifyTarget,
    *,
    deletion_mode: str = DEFAULT_DELETION_MODE,
) -> str | None:
    """
    target.action에 따른 치환 문자열을 반환합니다.

    None을 반환하면 자동 적용하지 않습니다.

    deletion_mode:
    - "delete": 삭제 action을 실제 삭제("")로 처리합니다. 기본값입니다.
    - "mark": 사용자 확인용 preview로 "(삭제됨)"을 표시합니다.
    """
    action = (target.action or "").strip()

    if action == "검토 필요":
        return None

    if action == "삭제":
        if deletion_mode == "mark":
            return DELETE_MARKER
        return ""

    # 11주차에서는 기타 action은 기본적으로 마스킹 처리합니다.
    # 마스킹 길이는 실제 slice 길이를 기준으로 합니다.
    return mask_text(len(actual_text))


def apply_single_target(
    text: str,
    target: DeidentifyTarget,
    *,
    deletion_mode: str = DEFAULT_DELETION_MODE,
) -> tuple[str, bool, list[str], str | None]:
    """
    문자열 하나에 target 하나를 적용합니다.

    Returns:
        updated_text:
            적용 후 문자열
        applied:
            실제 적용 여부
        warnings:
            경고 목록
        skip_reason:
            적용하지 않은 경우 사유
    """
    warnings: list[str] = []

    if (target.action or "").strip() == "검토 필요":
        reason = "검토 필요 action은 자동 적용하지 않습니다."
        return text, False, [reason], reason

    range_error = validate_target_range(text, target)
    if range_error is not None:
        return text, False, [range_error], range_error

    assert target.start is not None
    assert target.end is not None

    actual_text = text[target.start:target.end]
    matched = target.matched or ""

    if matched and matched != actual_text:
        warnings.append(
            "matched와 실제 text[start:end]가 다릅니다: "
            f"matched={matched!r}, actual={actual_text!r}, "
            f"start={target.start}, end={target.end}"
        )

    replacement = replacement_for_target(
        actual_text,
        target,
        deletion_mode=deletion_mode,
    )

    if replacement is None:
        reason = f"자동 적용 제외 action입니다: action={target.action}"
        return text, False, warnings + [reason], reason

    updated_text = text[: target.start] + replacement + text[target.end :]

    return updated_text, True, warnings, None


def split_applicable_targets(
    targets: list[DeidentifyTarget],
) -> tuple[list[DeidentifyTarget], list[SkippedTarget], list[str]]:
    """
    apply_targets_to_text() 진입 전에 자동 적용 가능한 target과 제외 target을 분리합니다.

    검토 필요 action 또는 start/end가 None인 target은 자동 적용 대상에서 제외합니다.
    """
    applicable: list[DeidentifyTarget] = []
    skipped: list[SkippedTarget] = []
    warnings: list[str] = []

    for target in targets:
        action = (target.action or "").strip()

        if action == "검토 필요":
            reason = "검토 필요 action은 자동 적용하지 않습니다."
            skipped.append(SkippedTarget(target=target, reason=reason))
            warnings.append(f"{target.label}/{target.matched}: {reason}")
            continue

        if target.start is None or target.end is None:
            reason = "start 또는 end가 None입니다."
            skipped.append(SkippedTarget(target=target, reason=reason))
            warnings.append(f"{target.label}/{target.matched}: {reason}")
            continue

        applicable.append(target)

    return applicable, skipped, warnings


def apply_targets_to_text(
    text: str,
    targets: list[DeidentifyTarget],
    *,
    deletion_mode: str = DEFAULT_DELETION_MODE,
    location_key: str | None = None,
) -> ApplyResult:
    """
    하나의 원문 문자열에 DeidentifyTarget 목록을 적용합니다.

    같은 문자열 내부에서는 start 내림차순으로 적용합니다.
    deletion_mode 기본값은 "delete"이며, 삭제 action은 실제 삭제("")로 처리합니다.
    사용자 preview가 필요하면 deletion_mode="mark"를 사용합니다.
    """
    applied_text = text
    applied_targets: list[DeidentifyTarget] = []
    skipped_targets: list[SkippedTarget] = []
    warnings: list[str] = []

    applicable_targets, pre_skipped, pre_warnings = split_applicable_targets(targets)
    skipped_targets.extend(pre_skipped)
    warnings.extend(pre_warnings)

    sorted_targets = sorted(
        applicable_targets,
        key=lambda target: -(target.start if target.start is not None else -1),
    )

    for target in sorted_targets:
        updated_text, applied, target_warnings, skip_reason = apply_single_target(
            applied_text,
            target,
            deletion_mode=deletion_mode,
        )

        warnings.extend(
            f"{target.label}/{target.matched}: {warning}"
            for warning in target_warnings
        )

        if applied:
            applied_text = updated_text
            applied_targets.append(target)
        else:
            skipped_targets.append(
                SkippedTarget(
                    target=target,
                    reason=skip_reason or "알 수 없는 사유로 적용되지 않았습니다.",
                )
            )

    return ApplyResult(
        original_text=text,
        applied_text=applied_text,
        applied_targets=applied_targets,
        skipped_targets=skipped_targets,
        warnings=warnings,
        location_key=location_key,
    )


def group_targets_by_location(
    targets: list[DeidentifyTarget],
) -> dict[str, list[DeidentifyTarget]]:
    """
    DeidentifyTarget 목록을 location key 기준으로 묶습니다.
    """
    grouped: dict[str, list[DeidentifyTarget]] = {}

    for target in targets:
        key = location_key_for_target(target)
        grouped.setdefault(key, []).append(target)

    return grouped


def get_context_for_targets(targets: list[DeidentifyTarget]) -> tuple[str, list[str]]:
    """
    같은 location에 속한 target 목록에서 Apply 원문 context를 결정합니다.

    11주차 PoC에서는 target.context를 원문 문자열로 사용합니다.
    context가 여러 개로 불일치하면 첫 번째 context를 사용하고 warning을 남깁니다.
    """
    warnings: list[str] = []

    contexts = [
        target.context
        for target in targets
        if target.context is not None
    ]

    if not contexts:
        return "", ["해당 location에 context가 없어 빈 문자열을 사용했습니다."]

    first_context = contexts[0]

    for context in contexts[1:]:
        if context != first_context:
            warnings.append("같은 location 내 target들의 context가 서로 다릅니다. 첫 번째 context를 사용합니다.")
            break

    return first_context, warnings


def apply_plan_to_contexts(
    plan: DeidentifyPlan,
    *,
    deletion_mode: str = DEFAULT_DELETION_MODE,
) -> ApplyPlanResult:
    """
    DeidentifyPlan 전체를 location/context 기준으로 묶어 문자열 Apply를 수행합니다.

    11주차 PoC에서는 실제 파일을 수정하지 않고, 각 target의 context 문자열에 적용합니다.
    review_targets는 자동 적용하지 않고 결과에 보존합니다.
    """
    text_results: list[ApplyResult] = []
    warnings: list[str] = []

    grouped = group_targets_by_location(plan.auto_targets)

    for location_key, targets in grouped.items():
        context, context_warnings = get_context_for_targets(targets)
        warnings.extend(f"{location_key}: {warning}" for warning in context_warnings)

        result = apply_targets_to_text(
            context,
            targets,
            deletion_mode=deletion_mode,
            location_key=location_key,
        )
        text_results.append(result)

    return ApplyPlanResult(
        text_results=text_results,
        review_targets=plan.review_targets,
        warnings=warnings,
    )
