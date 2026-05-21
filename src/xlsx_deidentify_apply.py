"""
xlsx 파일 단위 비식별화 Apply

목적:
- DeidentifyPlan의 xlsx auto_targets를 실제 xlsx 파일 셀 값에 적용합니다.
- 결과는 파일 형식 공통 구조인 CommonApplyResult로 반환합니다.

13주차 리팩토링:
- common_apply_utils.py의 공통 함수를 사용합니다.
- CommonApplyResult.applyMode="applied"를 명시합니다.
- 빈 문자열 셀 처리 분기를 추가했습니다.
- Apply 후 cell.data_type="s"로 문자열 셀 유지합니다.
- 코드화된 warning type을 사용합니다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import coordinate_to_tuple

try:
    from src.common_apply_result import (
        APPLY_MODE_APPLIED,
        CommonApplyItem,
        CommonApplyResult,
        build_summary,
        make_review_items,
    )
    from src.common_apply_utils import (
        WARNING_CONTEXT_MISMATCH,
        WARNING_EMPTY_CELL,
        WARNING_FORMULA_CELL,
        WARNING_MERGED_CELL_NOT_TOP_LEFT,
        WARNING_MISSING_CELL_REF,
        WARNING_MISSING_SHEET_NAME,
        WARNING_NON_STRING_CELL,
        WARNING_SHEET_NOT_FOUND,
        actions_for_targets,
        format_warning,
        labels_for_targets,
        make_output_path,
        make_status,
        normalize_nfc,
        validate_slice_against_text,
    )
    from src.deidentify_apply import apply_targets_to_text
    from src.deidentify_target_builder import DeidentifyPlan, DeidentifyTarget
except ModuleNotFoundError:
    from common_apply_result import (
        APPLY_MODE_APPLIED,
        CommonApplyItem,
        CommonApplyResult,
        build_summary,
        make_review_items,
    )
    from common_apply_utils import (
        WARNING_CONTEXT_MISMATCH,
        WARNING_EMPTY_CELL,
        WARNING_FORMULA_CELL,
        WARNING_MERGED_CELL_NOT_TOP_LEFT,
        WARNING_MISSING_CELL_REF,
        WARNING_MISSING_SHEET_NAME,
        WARNING_NON_STRING_CELL,
        WARNING_SHEET_NOT_FOUND,
        actions_for_targets,
        format_warning,
        labels_for_targets,
        make_output_path,
        make_status,
        normalize_nfc,
        validate_slice_against_text,
    )
    from deidentify_apply import apply_targets_to_text
    from deidentify_target_builder import DeidentifyPlan, DeidentifyTarget


def target_file_type(target: DeidentifyTarget) -> str:
    return str((target.location_meta or {}).get("fileType") or "").lower()


def filter_xlsx_targets(plan: DeidentifyPlan) -> list[DeidentifyTarget]:
    """
    fileType이 xlsx인 auto target만 선별합니다.
    """
    return [
        target
        for target in plan.auto_targets
        if target_file_type(target) == "xlsx"
    ]


def normalize_sheet_name(name: Any) -> str:
    return normalize_nfc(name)


def find_worksheet(workbook, sheet_name: str):
    """
    NFC 정규화된 sheetName으로 worksheet를 찾습니다.
    실제 접근은 workbook에 존재하는 원본 sheetName으로 수행합니다.
    """
    normalized_target = normalize_sheet_name(sheet_name)

    for actual_name in workbook.sheetnames:
        if normalize_sheet_name(actual_name) == normalized_target:
            return workbook[actual_name]

    return None


def is_formula_cell(cell: Cell) -> bool:
    return cell.data_type == "f"


def is_string_cell(cell: Cell) -> bool:
    return isinstance(cell.value, str) and not is_formula_cell(cell)


def cell_type_name(cell: Cell) -> str:
    if cell.value is None:
        return "empty"
    if is_formula_cell(cell):
        return "formula"
    if isinstance(cell.value, bool):
        return "boolean"
    if isinstance(cell.value, (int, float)):
        return "number"
    if isinstance(cell.value, str):
        return "string"
    return type(cell.value).__name__


def get_sheet_and_cell(target: DeidentifyTarget) -> tuple[str | None, str | None]:
    meta = target.location_meta or {}
    return meta.get("sheetName"), meta.get("cellRef")


def merged_cell_status(ws, cell_ref: str) -> tuple[bool, bool, str | None, str | None]:
    """
    병합 셀 여부를 확인합니다.

    Returns:
        (is_merged, is_top_left, merged_range_str, top_left_ref)
    """
    row, col = coordinate_to_tuple(cell_ref)

    for merged_range in ws.merged_cells.ranges:
        in_range = (
            merged_range.min_row <= row <= merged_range.max_row
            and merged_range.min_col <= col <= merged_range.max_col
        )

        if not in_range:
            continue

        top_left = f"{get_column_letter(merged_range.min_col)}{merged_range.min_row}"
        return True, cell_ref == top_left, str(merged_range), top_left

    return False, False, None, None


def _make_skipped_item(
    target: DeidentifyTarget,
    warning: str,
    target_count: int = 1,
) -> CommonApplyItem:
    """
    sheetName/cellRef 누락 등 사전 검증 단계에서 skip되는 target에 대한 CommonApplyItem.
    """
    return CommonApplyItem(
        locationLabel=target.location_label,
        locationMeta=target.location_meta or {},
        label=target.label or "",
        action=target.action,
        originalText=target.context or "",
        appliedText=target.context or "",
        status="skipped",
        appliedTargetCount=0,
        skippedTargetCount=target_count,
        warnings=[warning],
    )


def group_targets_by_sheet_cell(
    targets: list[DeidentifyTarget],
) -> tuple[dict[tuple[str, str], list[DeidentifyTarget]], list[CommonApplyItem], list[str]]:
    """
    xlsx target을 (sheetName, cellRef) 기준으로 묶습니다.

    sheetName/cellRef가 없으면 skipped CommonApplyItem으로 변환합니다.
    """
    grouped: dict[tuple[str, str], list[DeidentifyTarget]] = {}
    skipped_items: list[CommonApplyItem] = []
    warnings: list[str] = []

    for target in targets:
        sheet_name, cell_ref = get_sheet_and_cell(target)

        if not sheet_name:
            warning = format_warning(
                WARNING_MISSING_SHEET_NAME,
                f"{target.location_label}: sheetName이 없어 자동 적용을 건너뛰었습니다.",
            )
            warnings.append(warning)
            skipped_items.append(_make_skipped_item(target, warning))
            continue

        if not cell_ref:
            warning = format_warning(
                WARNING_MISSING_CELL_REF,
                f"{target.location_label}: cellRef가 없어 자동 적용을 건너뛰었습니다.",
            )
            warnings.append(warning)
            skipped_items.append(_make_skipped_item(target, warning))
            continue

        grouped.setdefault((str(sheet_name), str(cell_ref)), []).append(target)

    return grouped, skipped_items, warnings


def _make_cell_skipped_item(
    location_label: str,
    location_meta: dict[str, Any],
    targets: list[DeidentifyTarget],
    original_text: str,
    warnings: list[str],
) -> CommonApplyItem:
    """
    셀 단위 사전 검증(병합셀/수식/비문자열/빈 셀)에서 skip되는 CommonApplyItem.
    """
    return CommonApplyItem(
        locationLabel=location_label,
        locationMeta=location_meta,
        label=labels_for_targets(targets),
        action=actions_for_targets(targets),
        originalText=original_text,
        appliedText=original_text,
        status="skipped",
        appliedTargetCount=0,
        skippedTargetCount=len(targets),
        warnings=warnings,
    )


def apply_targets_to_cell(
    ws,
    sheet_name: str,
    cell_ref: str,
    targets: list[DeidentifyTarget],
    *,
    deletion_mode: str,
) -> CommonApplyItem:
    """
    특정 셀에 속한 target 목록을 셀 값에 적용합니다.
    """
    representative = targets[0]
    location_label = representative.location_label or f"{sheet_name} 탭 {cell_ref} 셀"
    location_meta = representative.location_meta or {
        "fileType": "xlsx",
        "sheetName": sheet_name,
        "cellRef": cell_ref,
    }

    warnings: list[str] = []

    cell = ws[cell_ref]

    # 병합 셀: ws[cell_ref]가 MergedCell이면 좌상단이 아님
    if isinstance(cell, MergedCell):
        warning = format_warning(
            WARNING_MERGED_CELL_NOT_TOP_LEFT,
            f"{location_label}: 병합 셀의 좌상단 셀이 아니므로 자동 적용을 건너뛰었습니다. "
            f"cellRef={cell_ref}",
        )
        warnings.append(warning)
        return _make_cell_skipped_item(
            location_label, location_meta, targets, "", warnings,
        )

    # 병합 셀: 좌상단이라도 명시적으로 확인
    is_merged, is_top_left, merged_range, top_left = merged_cell_status(ws, cell_ref)
    if is_merged and not is_top_left:
        warning = format_warning(
            WARNING_MERGED_CELL_NOT_TOP_LEFT,
            f"{location_label}: 병합 셀의 좌상단 셀이 아니므로 자동 적용을 건너뛰었습니다. "
            f"mergedRange={merged_range}, topLeft={top_left}",
        )
        warnings.append(warning)
        return _make_cell_skipped_item(
            location_label, location_meta, targets, str(cell.value or ""), warnings,
        )

    # 빈 셀 처리 (None 또는 빈 문자열)
    # openpyxl에서 빈 문자열로 저장된 셀은 다시 읽을 때 None이 될 수 있으므로
    # 두 케이스를 함께 처리합니다.
    if cell.value is None or cell.value == "":
        warning = format_warning(
            WARNING_EMPTY_CELL,
            f"{location_label}: 빈 셀에 detection이 있어 자동 적용을 건너뛰었습니다.",
        )
        warnings.append(warning)
        return _make_cell_skipped_item(
            location_label, location_meta, targets, "", warnings,
        )

    # 수식 셀
    if is_formula_cell(cell):
        warning = format_warning(
            WARNING_FORMULA_CELL,
            f"{location_label}: 수식 셀에 detection이 있어 자동 적용을 건너뛰었습니다. "
            f"cellType=formula, formula={cell.value}",
        )
        warnings.append(warning)
        return _make_cell_skipped_item(
            location_label, location_meta, targets, str(cell.value or ""), warnings,
        )

    # 비문자열 셀
    if not is_string_cell(cell):
        warning = format_warning(
            WARNING_NON_STRING_CELL,
            f"{location_label}: 비문자열 셀에 detection이 있어 자동 적용을 건너뛰었습니다. "
            f"cellType={cell_type_name(cell)}, cellValue={cell.value}",
        )
        warnings.append(warning)
        return _make_cell_skipped_item(
            location_label, location_meta, targets, str(cell.value or ""), warnings,
        )

    cell_value = cell.value

    # context 불일치 warning (적용은 진행)
    if any(
        target.context is not None
        and normalize_nfc(target.context) != normalize_nfc(cell_value)
        for target in targets
    ):
        warnings.append(
            format_warning(
                WARNING_CONTEXT_MISMATCH,
                f"{location_label}: target.context와 실제 셀 값이 다릅니다. "
                "cell_value 기준으로 slice 검증 후 적용 여부를 판단합니다.",
            )
        )

    valid_targets: list[DeidentifyTarget] = []
    skipped_count = 0

    for target in targets:
        warning_type, slice_error = validate_slice_against_text(cell_value, target)
        if slice_error is not None:
            warnings.append(
                format_warning(warning_type, f"{location_label}: {slice_error}")
            )
            skipped_count += 1
            continue

        valid_targets.append(target)

    if valid_targets:
        apply_result = apply_targets_to_text(
            cell_value,
            valid_targets,
            deletion_mode=deletion_mode,
        )
        cell.value = apply_result.applied_text
        cell.data_type = "s"  # 13주차 보완: 문자열 셀 타입 명시 유지
        warnings.extend(apply_result.warnings)
        applied_count = len(apply_result.applied_targets)
        skipped_count += len(apply_result.skipped_targets)
        applied_text = apply_result.applied_text
    else:
        applied_count = 0
        applied_text = cell_value

    return CommonApplyItem(
        locationLabel=location_label,
        locationMeta=location_meta,
        label=labels_for_targets(targets),
        action=actions_for_targets(targets),
        originalText=cell_value,
        appliedText=applied_text,
        status=make_status(applied_count, skipped_count),
        appliedTargetCount=applied_count,
        skippedTargetCount=skipped_count,
        warnings=warnings,
    )


def apply_plan_to_xlsx(
    input_path: str,
    plan: DeidentifyPlan,
    output_path: str | None = None,
    deletion_mode: str = "delete",
) -> CommonApplyResult:
    """
    DeidentifyPlan을 xlsx 파일에 적용합니다.

    모든 파일 형식별 Apply 함수는 이 공통 시그니처 패턴을 따릅니다.
    """
    resolved_output_path = make_output_path(input_path, output_path)

    wb = load_workbook(input_path, data_only=False)

    xlsx_targets = filter_xlsx_targets(plan)
    grouped, skipped_items, global_warnings = group_targets_by_sheet_cell(xlsx_targets)

    auto_results: list[CommonApplyItem] = []
    auto_results.extend(skipped_items)

    for (sheet_name, cell_ref), targets in grouped.items():
        ws = find_worksheet(wb, sheet_name)

        if ws is None:
            warning = format_warning(
                WARNING_SHEET_NOT_FOUND,
                f"{sheet_name} 시트를 찾을 수 없어 자동 적용을 건너뛰었습니다.",
            )
            global_warnings.append(warning)
            auto_results.append(
                CommonApplyItem(
                    locationLabel=targets[0].location_label,
                    locationMeta=targets[0].location_meta or {},
                    label=labels_for_targets(targets),
                    action=actions_for_targets(targets),
                    originalText=targets[0].context or "",
                    appliedText=targets[0].context or "",
                    status="skipped",
                    appliedTargetCount=0,
                    skippedTargetCount=len(targets),
                    warnings=[warning],
                )
            )
            continue

        item = apply_targets_to_cell(
            ws,
            sheet_name,
            cell_ref,
            targets,
            deletion_mode=deletion_mode,
        )
        auto_results.append(item)

    wb.save(resolved_output_path)

    review_items = make_review_items(plan.review_targets)
    summary = build_summary(auto_results, review_items, global_warnings)

    return CommonApplyResult(
        fileType="xlsx",
        applyMode=APPLY_MODE_APPLIED,
        inputFilePath=str(input_path),
        outputFilePath=resolved_output_path,
        autoResults=auto_results,
        reviewTargets=review_items,
        warnings=global_warnings,
        summary=summary,
    )
