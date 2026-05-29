"""
CSV 파일 탐지 + 비식별화 적용 (applied 모드)

행×열 단위로 순회하며 regex/NER/AI로 탐지하고,
auto_targets를 직접 마스킹/삭제 처리한 결과 CSV 파일을 저장한다.
"""

from __future__ import annotations

import csv
import io
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

_logger = logging.getLogger(__name__)

try:
    from src.common_apply_result import (
        APPLY_MODE_APPLIED,
        CommonApplyItem,
        CommonApplyResult,
        build_summary,
        grade_for_targets,
        make_review_items,
        source_for_targets,
    )
    from src.deidentify_apply import apply_targets_to_text
    from src.deidentify_target_builder import build_deidentify_plan
except ModuleNotFoundError:
    from common_apply_result import (
        APPLY_MODE_APPLIED,
        CommonApplyItem,
        CommonApplyResult,
        build_summary,
        grade_for_targets,
        make_review_items,
        source_for_targets,
    )
    from deidentify_apply import apply_targets_to_text
    from deidentify_target_builder import build_deidentify_plan


_ENCODINGS = ["utf-8-sig", "utf-8", "cp949"]


def _should_skip_ai(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 10:
        return True
    korean = sum(1 for c in stripped if "가" <= c <= "힣")
    return korean / len(stripped) < 0.20


def _read_csv(path: str) -> tuple[list[list[str]], str, str]:
    """인코딩 + 구분자 자동 감지로 CSV 읽기.

    Returns:
        (rows, encoding, delimiter)
    """
    raw = Path(path).read_bytes()
    text = None
    used_enc = "utf-8"
    for enc in _ENCODINGS:
        try:
            text = raw.decode(enc)
            used_enc = enc
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    return rows, used_enc, delimiter


def _g(obj: Any, *names: str, default: Any = None) -> Any:
    """dict 또는 object에서 속성값 추출 (xlsx 인라인 코드와 동일 헬퍼)."""
    for n in names:
        if isinstance(obj, dict) and n in obj:
            return obj[n]
        if hasattr(obj, n):
            return getattr(obj, n)
    return default


def detect_and_apply_csv(
    input_path: str,
    output_path: str,
    *,
    regex_detect_func: Callable | None = None,
    ner_detect_func: Callable | None = None,
    ai_predict_func: Callable | None = None,
    ner_threshold: float = 0.8,
    ai_threshold: float = 0.5,
    deletion_mode: str = "mark",
) -> CommonApplyResult:
    """CSV 파일을 읽어 탐지 + 비식별화 적용 후 결과 파일을 저장한다."""

    if regex_detect_func is None:
        try:
            from src.regex_detector import detect_patterns as _dp
        except ModuleNotFoundError:
            from regex_detector import detect_patterns as _dp
        regex_detect_func = _dp

    rows, _enc, delimiter = _read_csv(input_path)
    if not rows:
        return CommonApplyResult(
            fileType="csv",
            inputFilePath=input_path,
            outputFilePath=output_path,
            autoResults=[],
            reviewTargets=[],
            warnings=["CSV 파일이 비어 있습니다."],
            summary=build_summary([], [], ["CSV 파일이 비어 있습니다."]),
            applyMode=APPLY_MODE_APPLIED,
        )

    # 첫 행을 헤더로 간주해 컬럼명 저장
    headers: list[str] = rows[0] if rows else []

    detections: list[dict[str, Any]] = []
    order = 0

    for row_no, row in enumerate(rows, start=1):
        for col_no, text in enumerate(row, start=1):
            if not isinstance(text, str) or not text.strip():
                continue

            # 위치 정보
            header_name = headers[col_no - 1] if col_no - 1 < len(headers) else f"{col_no}열"
            if row_no == 1:
                location_label = f"헤더 {col_no}열 ({text})"
            else:
                location_label = f"{row_no}행 {header_name}열"
            location_meta: dict[str, Any] = {
                "fileType":   "csv",
                "rowNo":      row_no,
                "colNo":      col_no,
                "headerName": header_name,
            }

            # regex
            raw_regex = regex_detect_func(text) or []
            for raw in raw_regex:
                detections.append({
                    "label":             _g(raw, "label", default=""),
                    "matched":           _g(raw, "value", "matched", default=""),
                    "grade":             _g(raw, "grade", default="S"),
                    "action":            _g(raw, "action", default="마스킹"),
                    "source":            "regex",
                    "context":           text,
                    "locationLabel":     location_label,
                    "locationMeta":      location_meta,
                    "start":             _g(raw, "start"),
                    "end":               _g(raw, "end"),
                    "sensitiveType":     _g(raw, "sensitive_type", "sensitiveType"),
                    "sensitiveCategory": _g(raw, "sensitive_category", "sensitiveCategory",
                                            default=_g(raw, "label", default="")),
                    "reason":            f"정규식 탐지: {_g(raw, 'label', default='')}",
                    "_order":            order,
                })
                order += 1

            # NER
            if ner_detect_func:
                try:
                    raw_ner = ner_detect_func(text) or []
                except Exception as exc:
                    _logger.warning("[NER] csv %s 탐지 실패: %s", location_label, exc)
                    raw_ner = []
                for raw in raw_ner:
                    entity = (
                        raw.get("entity_group") or raw.get("entity") or ""
                    ).upper().replace("B-", "").replace("I-", "")
                    if entity not in {"PERSON", "PER", "PS", "인명"}:
                        continue
                    if float(raw.get("score", 0)) < ner_threshold:
                        continue
                    s, e = int(raw.get("start", 0)), int(raw.get("end", 0))
                    if e - s <= 2:
                        continue
                    detections.append({
                        "label": "성명", "matched": text[s:e],
                        "grade": "S", "action": "마스킹", "source": "ner",
                        "context": text, "locationLabel": location_label,
                        "locationMeta": location_meta,
                        "start": s, "end": e,
                        "sensitiveType": "개인정보", "sensitiveCategory": "성명",
                        "reason": "NER 탐지: PERSON",
                        "_order": order,
                    })
                    order += 1

            # AI (regex가 이미 탐지한 셀 또는 짧은/비한국어 텍스트는 건너뜀)
            if ai_predict_func and not raw_regex and not _should_skip_ai(text):
                try:
                    grade, confidence, prob_map = ai_predict_func(text)
                    if grade != "O" and confidence >= ai_threshold:
                        prob_text = " / ".join(
                            f"{k}={v:.4f}" for k, v in prob_map.items()
                        )
                        detections.append({
                            "label": "민감정보", "matched": "",
                            "grade": grade, "action": "검토 필요", "source": "ai",
                            "context": text, "locationLabel": location_label,
                            "locationMeta": location_meta,
                            "start": None, "end": None,
                            "sensitiveType": "문맥 기반 민감정보",
                            "sensitiveCategory": f"AI_{grade}",
                            "reason": (
                                f"AI 문장분류 grade={grade} / "
                                f"confidence={confidence:.4f} / "
                                f"threshold={ai_threshold:.2f} / {prob_text}"
                            ),
                            "_order": order,
                        })
                        order += 1
                except Exception as exc:
                    _logger.warning("[AI] csv %s 예측 실패: %s", location_label, exc)

    plan = build_deidentify_plan(detections)

    # auto_targets를 (rowNo, colNo) 단위로 그룹화
    cell_targets: dict[tuple[int, int], list] = defaultdict(list)
    for target in plan.auto_targets:
        meta = target.location_meta or {}
        key = (int(meta.get("rowNo", 0)), int(meta.get("colNo", 0)))
        cell_targets[key].append(target)

    # 출력 행 생성 (원본 복사 후 apply)
    output_rows = [list(row) for row in rows]
    auto_results: list[CommonApplyItem] = []

    for (row_no, col_no), targets in sorted(cell_targets.items()):
        if row_no < 1 or row_no > len(output_rows):
            continue
        if col_no < 1 or col_no > len(output_rows[row_no - 1]):
            continue

        original_text = output_rows[row_no - 1][col_no - 1]
        apply_result = apply_targets_to_text(
            original_text, targets, deletion_mode=deletion_mode
        )
        applied_text = apply_result.applied_text
        item_warnings = apply_result.warnings

        output_rows[row_no - 1][col_no - 1] = applied_text

        location_label = targets[0].location_label or f"{row_no}행 {col_no}열"
        location_meta  = targets[0].location_meta  or {
            "fileType": "csv", "rowNo": row_no, "colNo": col_no,
        }

        auto_results.append(CommonApplyItem(
            locationLabel=location_label,
            locationMeta=location_meta,
            label=", ".join(dict.fromkeys(t.label for t in targets if t.label)),
            action=", ".join(dict.fromkeys(t.action for t in targets if t.action)),
            originalText=original_text,
            appliedText=applied_text,
            status="applied" if applied_text != original_text else "skipped",
            appliedTargetCount=len(apply_result.applied_targets),
            skippedTargetCount=len(apply_result.skipped_targets),
            warnings=item_warnings,
            grade=grade_for_targets(targets),
            source=source_for_targets(targets),
        ))

    review_targets = make_review_items(plan.review_targets)

    # 출력 파일 저장
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerows(output_rows)

    return CommonApplyResult(
        fileType="csv",
        inputFilePath=input_path,
        outputFilePath=output_path,
        autoResults=auto_results,
        reviewTargets=review_targets,
        warnings=[],
        summary=build_summary(auto_results, review_targets, []),
        applyMode=APPLY_MODE_APPLIED,
    )
