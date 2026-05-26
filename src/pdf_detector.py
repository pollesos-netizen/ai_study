"""
PDF 파일 탐지 + 안내(guide) 모드

16주차 1단계: 스켈레톤 + 데이터 구조 + line 순회

목적:
- PDF 파일에서 line 단위로 텍스트를 순회 가능한 구조로 변환합니다.
- pdfplumber(MIT 라이선스, pdfminer.six 기반)만 사용합니다.
- docx/pptx/hwpx와 동일한 guide 모드 패턴을 적용합니다.

처리 범위 (16주차 PoC):
- 텍스트 기반 PDF
- line 단위 텍스트 추출 (extract_text_lines)
- x_tolerance=1로 한글 띄어쓰기 정확 복원
- bbox 좌표 함께 저장 (향후 좌표 기반 안내 확장 대비)
- guide 모드 결과 생성

처리 범위 외:
- 스캔 PDF (텍스트 추출 불가 시 warning만 표시)
- 암호화된 PDF (열기 실패 시 warning)
- OCR
- 표 셀 행/열 정밀 분리 (line 단위로 처리)
- 좌표 기반 정밀 하이라이트
- 주석/첨부파일

PDF 구조와 처리 정책:
- docx/pptx/hwpx와 달리 paragraph/표 셀 구분이 명확하지 않음
- 모든 텍스트를 line 단위로 통일 (단일 section="text_line")
- pageNo: 0-based 저장, 1-based 표시 ("1쪽")
- lineNo: 페이지 내 line 인덱스, 0-based 저장, 1-based 표시 ("6번째 줄")
- bbox: PDF 좌표계 (x0, top, x1, bottom)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

try:
    from src.common_apply_utils import make_location_label_with_context
except ModuleNotFoundError:
    from common_apply_utils import make_location_label_with_context


# ── 상수 ───────────────────────────────────────────────────────

# pdfplumber extract_text_lines의 x_tolerance 값.
# 기본값 3은 영문 PDF에 맞춰져 있어 한글 PDF에서 띄어쓰기 누락 발생.
# 1단계 검증에서 1.0으로 설정 시 한글 띄어쓰기 정확 복원, 부작용 없음 확인.
DEFAULT_X_TOLERANCE = 1


# ── 데이터 구조 ────────────────────────────────────────────────

@dataclass
class ParsedPdfTextLine:
    """
    PDF의 단일 line을 탐지 단위로 변환한 구조.

    section 값:
    - "text_line":  유일한 section. PDF는 paragraph/표 구분 없이 line 단위로 통일.

    필드:
    - page_no:    PDF의 페이지 인덱스 (0-based)
    - line_no:    페이지 내 line 인덱스 (0-based, 빈 line 포함 원문 인덱스 유지)
    - text:       line 텍스트 (pdfplumber x_tolerance=1로 추출)
    - bbox:       (x0, top, x1, bottom) PDF 좌표계, 향후 좌표 기반 안내 대비

    빈 line(strip 기준)은 iter_pdf_lines에서 제외됩니다.
    line_no는 원문 인덱스를 유지하여 사용자가 PDF에서 위치를 찾는 데 사용합니다.
    """

    page_no: int
    section: str  # 항상 "text_line"
    text: str
    line_no: int
    bbox: tuple[float, float, float, float] | None = None

    @property
    def location_label(self) -> str:
        """
        사용자 표시용 라벨.

        형식: "{page_no + 1}쪽 {line_no + 1}번째 줄: text..."
        """
        page_disp = self.page_no + 1
        line_disp = self.line_no + 1

        if self.section == "text_line":
            base = f"{page_disp}쪽 {line_disp}번째 줄"
            return make_location_label_with_context(base, self.text, max_length=30)

        return f"{page_disp}쪽 {line_disp}번째 줄 ({self.section})"

    @property
    def location_meta(self) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "fileType": "pdf",
            "pageNo": self.page_no,
            "section": self.section,
            "lineNo": self.line_no,
        }

        if self.bbox is not None:
            meta["bbox"] = list(self.bbox)

        return meta


# ── PDF 로드 / line 순회 ──────────────────────────────────────

def iter_pdf_lines(
    input_path: str | Path,
    *,
    x_tolerance: float = DEFAULT_X_TOLERANCE,
) -> list[ParsedPdfTextLine]:
    """
    PDF 파일을 열어 모든 page의 line을 ParsedPdfTextLine 목록으로 반환합니다.

    순회 정책:
    - 페이지 인덱스(0-based) 오름차순
    - 페이지 내 line 인덱스(0-based) 오름차순
    - 빈 line(strip 기준)은 제외하되, line_no는 원문 인덱스 유지

    Args:
        input_path: PDF 파일 경로
        x_tolerance: pdfplumber의 글자 간격 임계값
                     기본값 1.0은 한글 띄어쓰기 정확 복원용 (1단계 검증)
                     영문 PDF만 처리한다면 3.0(pdfplumber 기본값)도 가능

    Returns:
        ParsedPdfTextLine 목록. 빈 line 제외.
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError(
            "pdf_detector는 pdfplumber를 필요로 합니다. "
            "`pip install pdfplumber`로 설치해주세요."
        ) from exc

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {input_path}")

    results: list[ParsedPdfTextLine] = []

    with pdfplumber.open(str(input_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            try:
                lines = page.extract_text_lines(x_tolerance=x_tolerance)
            except Exception as exc:
                # 한 페이지의 추출 실패가 전체 PDF 처리를 막지 않도록.
                # 단순히 해당 페이지를 건너뛰고 다음 페이지로 진행.
                # 추후 상위 호출자가 warning을 표시할 수 있도록 빈 결과로 처리.
                lines = []

            for line_idx, line in enumerate(lines):
                text = line.get("text", "") or ""
                if not text.strip():
                    # 빈 line 제외 (line_no는 다음 line에서 그대로 line_idx + 1 사용)
                    continue

                # bbox 추출 (pdfplumber는 x0, top, x1, bottom 키 사용)
                x0 = line.get("x0")
                top = line.get("top")
                x1 = line.get("x1")
                bottom = line.get("bottom")

                bbox: tuple[float, float, float, float] | None = None
                if all(v is not None for v in (x0, top, x1, bottom)):
                    bbox = (float(x0), float(top), float(x1), float(bottom))

                results.append(
                    ParsedPdfTextLine(
                        page_no=page_idx,
                        section="text_line",
                        text=text,
                        line_no=line_idx,
                        bbox=bbox,
                    )
                )

    return results


# ── 메타데이터 헬퍼 ────────────────────────────────────────────

def get_pdf_metadata(input_path: str | Path) -> dict[str, Any]:
    """
    PDF의 메타데이터와 처리 가능 여부를 반환합니다.

    Returns:
        {
            "pageCount": int,
            "isEncrypted": bool,
            "metadata": dict,  # PDF 자체 metadata (Creator, Producer 등)
            "totalLines": int,  # 전체 추출 가능한 line 수
            "totalCharsExtracted": int,  # 전체 추출 텍스트 길이
            "emptyPages": list[int],  # 텍스트 추출 0인 페이지 인덱스 (스캔 가능성)
        }
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError(
            "pdf_detector는 pdfplumber를 필요로 합니다."
        ) from exc

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {input_path}")

    info: dict[str, Any] = {
        "pageCount": 0,
        "isEncrypted": False,
        "metadata": {},
        "totalLines": 0,
        "totalCharsExtracted": 0,
        "emptyPages": [],
    }

    try:
        with pdfplumber.open(str(input_path)) as pdf:
            info["pageCount"] = len(pdf.pages)
            info["metadata"] = dict(pdf.metadata or {})

            # pdfplumber 자체의 is_encrypted 속성은 일관되지 않으므로
            # pdfminer 내부 doc 객체에서 확인
            try:
                info["isEncrypted"] = bool(getattr(pdf.doc, "is_encrypted", False))
            except Exception:
                info["isEncrypted"] = False

            for page_idx, page in enumerate(pdf.pages):
                try:
                    lines = page.extract_text_lines(x_tolerance=DEFAULT_X_TOLERANCE)
                except Exception:
                    lines = []

                non_empty = [
                    line for line in lines
                    if (line.get("text") or "").strip()
                ]

                info["totalLines"] += len(non_empty)

                page_chars = sum(len(line.get("text", "")) for line in non_empty)
                info["totalCharsExtracted"] += page_chars

                if page_chars == 0:
                    info["emptyPages"].append(page_idx)

    except Exception:
        # 암호화된 PDF는 열기 자체가 실패할 수 있음
        # 빈 결과 반환 (호출자가 isEncrypted=True를 기대하므로 별도 처리 필요)
        raise

    return info


# ── Detection 어댑터 ──────────────────────────────────────────

from typing import Callable

try:
    from src.deidentify_target_builder import DeidentifyPlan, build_deidentify_plan
except ModuleNotFoundError:
    from deidentify_target_builder import DeidentifyPlan, build_deidentify_plan


def _make_target_dict_from_regex(
    raw: Any,
    line: ParsedPdfTextLine,
    order: int,
) -> dict[str, Any] | None:
    """
    regex_detector의 결과(DetectionResult 또는 유사 dict)를 Detection dict로 변환합니다.

    docx_detector / pptx_detector / hwpx_detector의 동일 함수와 같은 패턴.
    """
    def _get(obj, *names, default=None):
        for name in names:
            if isinstance(obj, dict) and name in obj:
                return obj.get(name)
            if hasattr(obj, name):
                return getattr(obj, name)
        return default

    label = _get(raw, "label")
    value = _get(raw, "value", "matched", "match")
    start = _get(raw, "start")
    end = _get(raw, "end")
    grade = _get(raw, "grade", default="S")
    action = _get(raw, "action", default="마스킹")
    desc = _get(raw, "desc", "reason", default=None)

    if label is None or value is None or start is None or end is None:
        return None

    return {
        "label": str(label),
        "matched": str(value),
        "grade": str(grade),
        "action": str(action),
        "source": "regex",
        "context": line.text,
        "locationLabel": line.location_label,
        "locationMeta": line.location_meta,
        "start": int(start),
        "end": int(end),
        "sensitiveType": _get(raw, "sensitive_type", "sensitiveType", default=None),
        "sensitiveCategory": _get(raw, "sensitive_category", "sensitiveCategory", default=label),
        "reason": str(desc) if desc else f"정규식 탐지: {label}",
        "_order": order,
    }


def _make_target_dict_from_ner(
    raw: dict[str, Any],
    line: ParsedPdfTextLine,
    order: int,
    *,
    threshold: float,
) -> dict[str, Any] | None:
    """Hugging Face NER 출력(aggregation_strategy="simple" 기준)을 Detection dict로 변환."""
    entity_label = (raw.get("entity_group") or raw.get("entity") or "").upper()
    entity_label = entity_label.replace("B-", "").replace("I-", "")

    if entity_label not in {"PERSON", "PER", "PS", "인명"}:
        return None

    score = float(raw.get("score") or 0.0)
    if score < threshold:
        return None

    start = raw.get("start")
    end = raw.get("end")
    if start is None or end is None:
        return None

    start = int(start)
    end = int(end)

    matched = line.text[start:end] or raw.get("word") or ""

    return {
        "label": "성명",
        "matched": str(matched),
        "grade": "S",
        "action": "마스킹",
        "source": "ner",
        "context": line.text,
        "locationLabel": line.location_label,
        "locationMeta": line.location_meta,
        "start": start,
        "end": end,
        "sensitiveType": "개인정보",
        "sensitiveCategory": "성명",
        "reason": (
            f"NER 모델 PERSON 탐지 / original_label={raw.get('entity_group') or raw.get('entity')}"
            f" / confidence={score:.4f} / threshold={threshold:.2f}"
        ),
        "_order": order,
    }


def _make_target_dict_from_ai(
    grade: str,
    confidence: float,
    line: ParsedPdfTextLine,
    order: int,
    *,
    threshold: float,
    prob_map: dict[str, float] | None = None,
) -> dict[str, Any] | None:
    """AI 문장분류 결과를 review target dict로 변환."""
    if grade == "O" or confidence < threshold:
        return None

    prob_text = ""
    if prob_map:
        prob_text = " / probs=(" + ", ".join(
            f"{label}={prob:.3f}" for label, prob in prob_map.items()
        ) + ")"

    return {
        "label": "민감정보",
        "matched": "",
        "grade": grade,
        "action": "검토 필요",
        "source": "ai",
        "context": line.text,
        "locationLabel": line.location_label,
        "locationMeta": line.location_meta,
        "start": None,
        "end": None,
        "sensitiveType": "문맥 기반 민감정보",
        "sensitiveCategory": f"AI_{grade}",
        "reason": (
            f"AI 문장분류 grade={grade} / confidence={confidence:.4f}"
            f" / threshold={threshold:.2f}{prob_text}"
        ),
        "_order": order,
    }


# ── 탐지 파이프라인 ────────────────────────────────────────────

def detect_in_pdf(
    input_path: str,
    *,
    regex_detect_func: Callable[[str], list[Any]] | None = None,
    ner_detect_func: Callable[[str], list[dict[str, Any]]] | None = None,
    ai_predict_func: Callable[[str], tuple[str, float, dict[str, float]]] | None = None,
    ner_threshold: float = 0.8,
    ai_threshold: float = 0.6,
    x_tolerance: float = DEFAULT_X_TOLERANCE,
) -> DeidentifyPlan:
    """
    PDF 파일의 모든 line을 순회하며 탐지를 수행하고 DeidentifyPlan을 생성합니다.

    13주차 detect_in_docx() / 14주차 detect_in_pptx() / 15주차 detect_in_hwpx()와
    동일한 시그니처. 탐지 함수는 주입형으로 받아 단위 테스트에서 모델 의존성을 끊습니다.

    Args:
        input_path: PDF 파일 경로
        regex_detect_func: 정규식 탐지 함수. None이면 src.regex_detector 사용.
        ner_detect_func: NER 모델 탐지 함수. None이면 NER 탐지 건너뜀.
        ai_predict_func: AI 문장분류 함수. None이면 AI 분류 건너뜀.
        ner_threshold: NER confidence 임계값
        ai_threshold: AI 분류 confidence 임계값
        x_tolerance: pdfplumber line 추출 간격 임계값 (1.0이 한글 띄어쓰기 복원에 적합)

    Returns:
        DeidentifyPlan (auto_targets + review_targets)
    """
    if regex_detect_func is None:
        try:
            from src.regex_detector import detect_patterns as _detect_patterns
        except ModuleNotFoundError:
            from regex_detector import detect_patterns as _detect_patterns
        regex_detect_func = _detect_patterns

    lines = iter_pdf_lines(input_path, x_tolerance=x_tolerance)

    detections: list[dict[str, Any]] = []
    order = 0

    for line in lines:
        # regex
        raw_regex = regex_detect_func(line.text) or []
        for raw in raw_regex:
            detection = _make_target_dict_from_regex(raw, line, order)
            if detection is not None:
                detections.append(detection)
                order += 1

        # NER
        if ner_detect_func is not None:
            try:
                raw_ner = ner_detect_func(line.text) or []
            except Exception as exc:
                print(f"[NER] {line.location_label} 탐지 실패: {exc}")
                raw_ner = []

            for raw in raw_ner:
                detection = _make_target_dict_from_ner(
                    raw, line, order, threshold=ner_threshold,
                )
                if detection is not None:
                    detections.append(detection)
                    order += 1

        # AI
        if ai_predict_func is not None:
            try:
                grade, confidence, prob_map = ai_predict_func(line.text)
            except Exception as exc:
                import logging as _log
                _log.getLogger(__name__).warning(
                    "[AI] %s 예측 실패: %s", line.location_label, exc
                )
                grade, confidence, prob_map = "O", 0.0, {}

            if grade is not None and confidence is not None:
                detection = _make_target_dict_from_ai(
                    grade, confidence, line, order,
                    threshold=ai_threshold, prob_map=prob_map,
                )
                if detection is not None:
                    detections.append(detection)
                    order += 1

    return build_deidentify_plan(detections)


# ── guide 생성 ─────────────────────────────────────────────────

try:
    from src.common_apply_utils import (
        WARNING_MISSING_PAGE_NO,
        WARNING_PDF_PAGE_OUT_OF_RANGE,
        WARNING_PDF_TEXT_BLOCK_NOT_FOUND,
        WARNING_SCANNED_PDF_NO_TEXT,
        WARNING_PDF_ENCRYPTED,
    )
except ModuleNotFoundError:
    from common_apply_utils import (
        WARNING_MISSING_PAGE_NO,
        WARNING_PDF_PAGE_OUT_OF_RANGE,
        WARNING_PDF_TEXT_BLOCK_NOT_FOUND,
        WARNING_SCANNED_PDF_NO_TEXT,
        WARNING_PDF_ENCRYPTED,
    )


def _make_pdf_location_key(meta: dict[str, Any]) -> tuple | None:
    """
    PDF target의 위치 그룹화 키를 생성합니다.

    - text_line: (pageNo, "text_line", lineNo)

    필수 필드(pageNo, lineNo)가 누락되면 None을 반환합니다.
    """
    page_no = meta.get("pageNo")
    section = str(meta.get("section") or "")
    line_no = meta.get("lineNo")

    if page_no is None or line_no is None:
        return None

    if section == "text_line":
        return (int(page_no), "text_line", int(line_no))

    return None


def _format_pdf_location_for_label(meta: dict[str, Any]) -> str:
    """경고 메시지/locationLabel 보조용 간단 표현."""
    page_no = meta.get("pageNo")
    line_no = meta.get("lineNo")
    section = meta.get("section")

    page_disp = (page_no + 1) if page_no is not None else "?"
    line_disp = (line_no + 1) if line_no is not None else "?"

    if section == "text_line":
        return f"{page_disp}쪽 {line_disp}번째 줄"
    return f"{page_disp}쪽 {line_disp}번째 줄 ({section})"


def _index_pdf_lines(
    input_path: str | Path,
    *,
    x_tolerance: float = DEFAULT_X_TOLERANCE,
) -> dict[tuple, str]:
    """
    PDF 파일에서 line 위치 키 → text 매핑을 미리 생성합니다.

    빈 line은 iter_pdf_lines에서 제외되므로 자동으로 dict에 포함되지 않습니다.
    """
    index: dict[tuple, str] = {}

    for line in iter_pdf_lines(input_path, x_tolerance=x_tolerance):
        key = _make_pdf_location_key(line.location_meta)
        if key is None:
            continue
        index[key] = line.text

    return index


def _group_targets_by_location(targets):
    """
    auto target을 PDF location key 기준으로 묶습니다.

    fileType이 pdf가 아닌 target은 제외합니다.
    필수 필드가 누락되거나 알 수 없는 section이면 skipped item으로 처리합니다.
    """
    try:
        from src.common_apply_result import CommonApplyItem
        from src.common_apply_utils import (
            WARNING_MISSING_PARAGRAPH_NO,
            WARNING_UNKNOWN_SECTION,
            format_warning,
        )
    except ModuleNotFoundError:
        from common_apply_result import CommonApplyItem
        from common_apply_utils import (
            WARNING_MISSING_PARAGRAPH_NO,
            WARNING_UNKNOWN_SECTION,
            format_warning,
        )

    grouped: dict[tuple, list] = {}
    skipped_items: list = []
    warnings: list[str] = []

    for target in targets:
        meta = target.location_meta or {}

        if str(meta.get("fileType") or "").lower() != "pdf":
            continue

        section = str(meta.get("section") or "")
        key = _make_pdf_location_key(meta)

        if key is None:
            label = target.location_label or _format_pdf_location_for_label(meta)

            if section not in {"text_line"}:
                warning = format_warning(
                    WARNING_UNKNOWN_SECTION,
                    f"{label}: 알 수 없는 section={section!r}이므로 안내를 생성하지 않습니다.",
                )
            elif meta.get("pageNo") is None:
                warning = format_warning(
                    WARNING_MISSING_PAGE_NO,
                    f"{label}: pageNo가 없어 안내를 생성하지 못했습니다.",
                )
            else:
                # lineNo 누락
                warning = format_warning(
                    WARNING_MISSING_PARAGRAPH_NO,
                    f"{label}: lineNo가 누락되어 안내를 생성하지 못했습니다.",
                )

            warnings.append(warning)
            skipped_items.append(
                CommonApplyItem(
                    locationLabel=target.location_label or label,
                    locationMeta=meta,
                    label=target.label or "",
                    action=target.action,
                    originalText=target.context or "",
                    appliedText=target.context or "",
                    status="skipped",
                    appliedTargetCount=0,
                    skippedTargetCount=1,
                    warnings=[warning],
                )
            )
            continue

        grouped.setdefault(key, []).append(target)

    return grouped, skipped_items, warnings


def _build_guide_item_for_location(
    key: tuple,
    line_text: str | None,
    targets,
    *,
    deletion_mode: str,
):
    """
    한 location(PDF line)에 속한 target 목록에 대해 guide 모드 CommonApplyItem을 생성합니다.

    docx_detector / pptx_detector / hwpx_detector의 동일 함수와 같은 패턴.
    """
    try:
        from src.common_apply_result import (
            CommonApplyItem,
            grade_for_targets,
            source_for_targets,
        )
        from src.common_apply_utils import (
            WARNING_CONTEXT_MISMATCH,
            WARNING_EMPTY_PARAGRAPH_TARGET,
            actions_for_targets,
            format_warning,
            labels_for_targets,
            make_status,
            normalize_nfc,
            validate_slice_against_text,
        )
        from src.deidentify_apply import apply_targets_to_text
    except ModuleNotFoundError:
        from common_apply_result import (
            CommonApplyItem,
            grade_for_targets,
            source_for_targets,
        )
        from common_apply_utils import (
            WARNING_CONTEXT_MISMATCH,
            WARNING_EMPTY_PARAGRAPH_TARGET,
            actions_for_targets,
            format_warning,
            labels_for_targets,
            make_status,
            normalize_nfc,
            validate_slice_against_text,
        )
        from deidentify_apply import apply_targets_to_text

    representative = targets[0]
    location_label = representative.location_label or _format_pdf_location_for_label(
        representative.location_meta or {}
    )
    location_meta = representative.location_meta or {}

    warnings: list[str] = []

    # line_text가 None이면 PDF에서 해당 위치를 찾을 수 없음
    if line_text is None:
        warning = format_warning(
            WARNING_PDF_TEXT_BLOCK_NOT_FOUND,
            f"{location_label}: 위치가 현재 PDF에서 발견되지 않습니다 (key={key}).",
        )
        warnings.append(warning)
        return CommonApplyItem(
            locationLabel=location_label,
            locationMeta=location_meta,
            label=labels_for_targets(targets),
            action=actions_for_targets(targets),
            originalText="",
            appliedText="",
            status="skipped",
            appliedTargetCount=0,
            skippedTargetCount=len(targets),
            warnings=warnings,
        )

    # 빈 line 방어 (iter_pdf_lines에서 이미 제외되지만 안전 차원)
    if not line_text.strip():
        warning = format_warning(
            WARNING_EMPTY_PARAGRAPH_TARGET,
            f"{location_label}: 빈 line을 가리키는 target은 안내를 생성하지 않습니다.",
        )
        warnings.append(warning)
        return CommonApplyItem(
            locationLabel=location_label,
            locationMeta=location_meta,
            label=labels_for_targets(targets),
            action=actions_for_targets(targets),
            originalText="",
            appliedText="",
            status="skipped",
            appliedTargetCount=0,
            skippedTargetCount=len(targets),
            warnings=warnings,
        )

    # context 불일치 (적용은 진행)
    if any(
        target.context is not None
        and normalize_nfc(target.context) != normalize_nfc(line_text)
        for target in targets
    ):
        warnings.append(
            format_warning(
                WARNING_CONTEXT_MISMATCH,
                f"{location_label}: target.context와 실제 line 텍스트가 다릅니다. "
                "line 텍스트 기준으로 slice 검증 후 권장 여부를 판단합니다.",
            )
        )

    # slice 검증
    valid_targets = []
    skipped_count = 0

    for target in targets:
        warning_type, slice_error = validate_slice_against_text(line_text, target)
        if slice_error is not None:
            warnings.append(
                format_warning(warning_type, f"{location_label}: {slice_error}")
            )
            skipped_count += 1
            continue
        valid_targets.append(target)

    if valid_targets:
        apply_result = apply_targets_to_text(
            line_text,
            valid_targets,
            deletion_mode=deletion_mode,
        )
        applied_text = apply_result.applied_text
        warnings.extend(apply_result.warnings)
        applied_count = len(apply_result.applied_targets)
        skipped_count += len(apply_result.skipped_targets)
    else:
        applied_text = line_text
        applied_count = 0

    return CommonApplyItem(
        locationLabel=location_label,
        locationMeta=location_meta,
        label=labels_for_targets(targets),
        action=actions_for_targets(targets),
        originalText=line_text,
        appliedText=applied_text,
        status=make_status(applied_count, skipped_count),
        appliedTargetCount=applied_count,
        skippedTargetCount=skipped_count,
        warnings=warnings,
        grade=grade_for_targets(targets),
        source=source_for_targets(targets),
    )


def build_guide_for_pdf(
    input_path: str,
    plan: DeidentifyPlan,
    *,
    deletion_mode: str = "delete",
    x_tolerance: float = DEFAULT_X_TOLERANCE,
):
    """
    DeidentifyPlan을 받아 guide 모드 CommonApplyResult를 생성합니다.

    실제 파일을 수정하지 않으며, outputFilePath는 None입니다.

    스캔/암호 PDF 검출:
    - 암호 PDF: pdfplumber.open() 실패 시 PDF_ENCRYPTED global warning
    - 스캔 PDF: PDF는 열리는데 텍스트 추출 0이면 SCANNED_PDF_NO_TEXT global warning

    PDF는 직접 편집이 어려우므로 사용자는 원본 docx/한글 파일에서 수정 후
    PDF로 재저장하는 것을 권장합니다 (보고서에 명시).
    """
    try:
        from src.common_apply_result import (
            APPLY_MODE_GUIDE,
            CommonApplyResult,
            build_summary,
            make_review_items,
        )
        from src.common_apply_utils import format_warning
    except ModuleNotFoundError:
        from common_apply_result import (
            APPLY_MODE_GUIDE,
            CommonApplyResult,
            build_summary,
            make_review_items,
        )
        from common_apply_utils import format_warning

    # 암호 PDF는 _index_pdf_lines 호출 자체가 실패할 수 있음
    line_index: dict[tuple, str] = {}
    encrypted_or_corrupt = False
    try:
        line_index = _index_pdf_lines(input_path, x_tolerance=x_tolerance)
    except Exception as exc:
        encrypted_or_corrupt = True
        encrypted_warning = format_warning(
            WARNING_PDF_ENCRYPTED,
            f"PDF를 열 수 없습니다 (암호화 또는 손상 가능성). "
            f"파일: {input_path} / 원인: {type(exc).__name__}: {exc}",
        )

    grouped, skipped_items, global_warnings = _group_targets_by_location(plan.auto_targets)

    if encrypted_or_corrupt:
        global_warnings.append(encrypted_warning)
    elif len(line_index) == 0:
        # 스캔 PDF 감지: PDF는 열렸지만 line이 하나도 추출되지 않음
        scan_warning = format_warning(
            WARNING_SCANNED_PDF_NO_TEXT,
            f"이 PDF는 텍스트를 추출할 수 없는 스캔 PDF일 가능성이 있습니다. "
            f"16주차 PoC에서는 OCR을 수행하지 않아 자동 탐지가 불가능합니다. "
            f"파일: {input_path}",
        )
        global_warnings.append(scan_warning)

    auto_results = list(skipped_items)

    for key, targets in grouped.items():
        line_text = line_index.get(key)
        item = _build_guide_item_for_location(
            key,
            line_text,
            targets,
            deletion_mode=deletion_mode,
        )
        auto_results.append(item)

    review_items = make_review_items(plan.review_targets)
    summary = build_summary(auto_results, review_items, global_warnings)

    return CommonApplyResult(
        fileType="pdf",
        applyMode=APPLY_MODE_GUIDE,
        inputFilePath=str(input_path),
        outputFilePath=None,
        autoResults=auto_results,
        reviewTargets=review_items,
        warnings=global_warnings,
        summary=summary,
    )


def detect_and_build_guide_for_pdf(
    input_path: str,
    *,
    regex_detect_func: Callable[[str], list[Any]] | None = None,
    ner_detect_func: Callable[[str], list[dict[str, Any]]] | None = None,
    ai_predict_func: Callable[[str], tuple[str, float, dict[str, float]]] | None = None,
    ner_threshold: float = 0.8,
    ai_threshold: float = 0.6,
    deletion_mode: str = "delete",
    x_tolerance: float = DEFAULT_X_TOLERANCE,
):
    """detect_in_pdf + build_guide_for_pdf 편의 wrapper."""
    plan = detect_in_pdf(
        input_path,
        regex_detect_func=regex_detect_func,
        ner_detect_func=ner_detect_func,
        ai_predict_func=ai_predict_func,
        ner_threshold=ner_threshold,
        ai_threshold=ai_threshold,
        x_tolerance=x_tolerance,
    )
    return build_guide_for_pdf(
        input_path, plan, deletion_mode=deletion_mode, x_tolerance=x_tolerance,
    )
