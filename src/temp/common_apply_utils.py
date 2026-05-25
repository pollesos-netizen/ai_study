"""
파일 형식 공통 Apply 유틸리티

목적:
- xlsx/docx/pptx/hwpx 등 파일 형식별 Apply 모듈에서 공통으로 사용하는 함수를 모읍니다.
- 12주차 xlsx_deidentify_apply.py에서 추출한 함수와, 13주차 docx detector에서 사용할
  공통 함수를 함께 보관합니다.

이 모듈은 특정 파일 형식에 의존하지 않습니다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import unicodedata

try:
    from src.deidentify_target_builder import DeidentifyTarget
except ModuleNotFoundError:
    from deidentify_target_builder import DeidentifyTarget


# ── Warning type 코드 ──────────────────────────────────────────

WARNING_CONTEXT_MISMATCH = "context_mismatch"
WARNING_SLICE_MISMATCH = "slice_mismatch"
WARNING_UNICODE_NORMALIZATION_MISMATCH = "unicode_normalization_mismatch"
WARNING_PARAGRAPH_OUT_OF_RANGE = "paragraph_out_of_range"
WARNING_MISSING_PARAGRAPH_NO = "missing_paragraph_no"
WARNING_UNSUPPORTED_DOCX_SECTION = "unsupported_docx_section"
WARNING_MISSING_TABLE_CELL_LOCATION = "missing_table_cell_location"
WARNING_EMPTY_PARAGRAPH_TARGET = "empty_paragraph_target"
WARNING_OVERLAP_TARGET = "overlap_target"
WARNING_MISSING_SHEET_NAME = "missing_sheet_name"
WARNING_MISSING_CELL_REF = "missing_cell_ref"
WARNING_MERGED_CELL_NOT_TOP_LEFT = "merged_cell_not_top_left"
WARNING_FORMULA_CELL = "formula_cell"
WARNING_NON_STRING_CELL = "non_string_cell"
WARNING_EMPTY_CELL = "empty_cell"
WARNING_SHEET_NOT_FOUND = "sheet_not_found"
# pptx 전용
WARNING_MISSING_SLIDE_NO = "missing_slide_no"
WARNING_SLIDE_OUT_OF_RANGE = "slide_out_of_range"
WARNING_SHAPE_NOT_FOUND = "shape_not_found"
# pptx, hwpx 공통
WARNING_UNKNOWN_SECTION = "unknown_section"
# hwpx 전용
WARNING_MISSING_SECTION_NO = "missing_section_no"
WARNING_SECTION_OUT_OF_RANGE = "section_out_of_range"


def format_warning(warning_type: str, message: str) -> str:
    """
    코드화된 warning type 접두어와 메시지를 결합합니다.

    예:
    [context_mismatch] 본문 17번째 문단: target.context와 현재 문단 텍스트가 다릅니다.
    """
    return f"[{warning_type}] {message}"


# ── 문자열 정규화 ───────────────────────────────────────────────

def normalize_nfc(value: Any) -> str:
    """
    NFC 정규화된 문자열을 반환합니다.

    비교 보조 용도로만 사용합니다.
    실제 인덱스 적용에는 사용하지 않습니다.
    """
    return unicodedata.normalize("NFC", str(value))


# ── output 파일명 생성 ──────────────────────────────────────────

def make_output_path(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    suffix: str = "_deidentified",
    max_suffix_index: int = 1000,
) -> str:
    """
    output_path가 없으면 original{suffix}.ext 규칙으로 생성합니다.
    기존 파일이 있으면 _1, _2 suffix를 붙입니다.
    suffix 탐색은 max_suffix_index까지만 수행합니다.

    Args:
        input_path: 원본 파일 경로
        output_path: 명시적 output 경로 (있으면 그대로 사용)
        suffix: 기본 suffix (예: "_deidentified")
        max_suffix_index: suffix 번호 탐색 상한선

    Returns:
        output 파일 경로 문자열

    Raises:
        FileExistsError: max_suffix_index까지 모두 존재하는 경우
    """
    if output_path is not None:
        return str(output_path)

    input_path = Path(input_path)
    base = input_path.with_name(f"{input_path.stem}{suffix}{input_path.suffix}")

    if not base.exists():
        return str(base)

    for index in range(1, max_suffix_index + 1):
        candidate = input_path.with_name(
            f"{input_path.stem}{suffix}_{index}{input_path.suffix}"
        )
        if not candidate.exists():
            return str(candidate)

    raise FileExistsError(
        "사용 가능한 output 파일명을 찾지 못했습니다. "
        "output_path를 직접 지정하세요."
    )


# ── slice 검증 ─────────────────────────────────────────────────

def validate_slice_against_text(
    text: str,
    target: DeidentifyTarget,
) -> tuple[str | None, str | None]:
    """
    실제 text[start:end]와 target.matched가 직접 일치하는지 검증합니다.

    NFC 정규화 후에만 일치하는 경우도 자동 적용하지 않고 warning으로 처리합니다.

    Returns:
        (warning_type, message)
        - 둘 다 None이면 정상 (적용 가능)
        - warning_type이 있으면 적용 불가
    """
    if target.start is None or target.end is None:
        return (
            WARNING_SLICE_MISMATCH,
            "start 또는 end가 None입니다.",
        )

    if target.start < 0 or target.end > len(text) or target.start >= target.end:
        return (
            WARNING_SLICE_MISMATCH,
            "start/end 범위가 현재 텍스트에 유효하지 않습니다: "
            f"start={target.start}, end={target.end}, text_len={len(text)}",
        )

    actual = text[target.start:target.end]
    matched = target.matched or ""

    if actual == matched:
        return None, None

    if normalize_nfc(actual) == normalize_nfc(matched):
        return (
            WARNING_UNICODE_NORMALIZATION_MISMATCH,
            "text[start:end]와 matched가 원문 기준으로 일치하지 않습니다. "
            "NFC 정규화 후에만 일치하므로 인덱스 기준 불일치 가능성이 있어 자동 적용을 건너뜁니다: "
            f"actual={actual!r}, matched={matched!r}, start={target.start}, end={target.end}",
        )

    return (
        WARNING_SLICE_MISMATCH,
        "text[start:end]와 matched가 일치하지 않아 자동 적용을 건너뜁니다: "
        f"actual={actual!r}, matched={matched!r}, start={target.start}, end={target.end}",
    )


# ── status 결정 ────────────────────────────────────────────────

def make_status(applied_count: int, skipped_count: int) -> str:
    """
    CommonApplyItem.status 값을 결정합니다.

    값:
    - "applied": 모든 target이 적용/권장 가능
    - "partial": 일부만 적용/권장 가능
    - "skipped": 적용/권장된 target이 없음
    """
    if applied_count > 0 and skipped_count == 0:
        return "applied"
    if applied_count > 0 and skipped_count > 0:
        return "partial"
    return "skipped"


# ── target 표시용 정렬 ─────────────────────────────────────────

def sort_targets_for_display(
    targets: list[DeidentifyTarget],
) -> list[DeidentifyTarget]:
    """
    사용자 표시용 target 순서입니다.

    같은 location 안에서는 start 오름차순으로 정렬해
    문서 안의 자연스러운 읽기 순서와 맞춥니다.

    주의:
    - 실제 Apply는 start 내림차순으로 적용해야 합니다 (apply_targets_to_text).
    - 이 함수는 표시 정렬 전용입니다.
    """
    return sorted(
        targets,
        key=lambda target: (
            target.start is None,
            target.start if target.start is not None else 10**9,
            target.label or "",
        ),
    )


def labels_for_targets(targets: list[DeidentifyTarget]) -> str:
    """
    target 목록의 label을 콤마 결합 문자열로 반환합니다.

    표시 순서는 start 오름차순을 기준으로 합니다.
    중복 label은 한 번만 표시합니다.
    """
    labels: list[str] = []

    for target in sort_targets_for_display(targets):
        if target.label and target.label not in labels:
            labels.append(target.label)

    return ", ".join(labels)


def actions_for_targets(targets: list[DeidentifyTarget]) -> str:
    """
    target 목록의 action을 콤마 결합 문자열로 반환합니다.

    표시 순서는 start 오름차순을 기준으로 합니다.
    중복 action은 한 번만 표시합니다.
    """
    actions: list[str] = []

    for target in sort_targets_for_display(targets):
        if target.action and target.action not in actions:
            actions.append(target.action)

    return ", ".join(actions)


# ── location label 생성 ────────────────────────────────────────

def make_location_label_with_context(
    base_label: str,
    context: str,
    *,
    max_length: int = 30,
) -> str:
    """
    base_label과 context 일부를 결합한 사용자 표시용 locationLabel을 생성합니다.

    사용자가 Word/Excel 등에서 Ctrl+F로 찾을 수 있도록 context 일부를 포함합니다.

    예:
    - base_label="본문 17번째 문단"
    - context="담당자 김도윤의 이메일은 test@example.com입니다."
    - max_length=30
    → "본문 17번째 문단: 담당자 김도윤의 이메일은 test@example.c..."

    빈 context는 base_label만 반환합니다.
    """
    if not context:
        return base_label

    # 줄바꿈/탭은 한 줄로 만들어 표시
    flat_context = " ".join(context.split())

    if len(flat_context) <= max_length:
        return f"{base_label}: {flat_context}"

    return f"{base_label}: {flat_context[:max_length]}..."
