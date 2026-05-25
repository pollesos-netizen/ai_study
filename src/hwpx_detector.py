"""
hwpx 파일 탐지 + 안내(guide) 모드

15주차 1단계: 스켈레톤 + 데이터 구조 + ZIP/XML 로드

목적:
- hwpx 파일에서 본문 paragraph와 표 셀 paragraph를 순회 가능한 구조로 변환합니다.
- python 표준 라이브러리(zipfile, xml.etree.ElementTree)만 사용합니다.
- docx/pptx와 동일한 guide 모드 패턴을 적용합니다.

처리 범위 (15주차 PoC):
- 본문 paragraph (hs:sec > hp:p > hp:run > hp:t)
- 표 셀 paragraph (hp:tbl > hp:tr > hp:tc > hp:subList > hp:p > hp:run > hp:t)
- 한 paragraph 안에 표가 여러 개일 수 있음
- 여러 section (section0.xml, section1.xml, ...)

처리 범위 외:
- header / footer / footnote / endnote
- 메모 / 주석
- 중첩 표 (표 안의 표)
- 이미지 캡션, OLE 객체

hwpx XML 구조:
    hs:sec (루트)
    └── hp:p (paragraph) × N
        └── hp:run × M
            ├── hp:t (텍스트 노드)
            └── hp:tbl (표, 선택적)
                └── hp:tr (행)
                    └── hp:tc (셀)
                        └── hp:subList
                            └── hp:p (셀 내부 paragraph)
                                └── hp:run > hp:t
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
import xml.etree.ElementTree as ET
import zipfile

try:
    from src.common_apply_utils import make_location_label_with_context
except ModuleNotFoundError:
    from common_apply_utils import make_location_label_with_context


# ── hwpx XML namespace ─────────────────────────────────────────

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"
HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"

HP = f"{{{HP_NS}}}"
HS = f"{{{HS_NS}}}"
HC = f"{{{HC_NS}}}"


# ── 데이터 구조 ────────────────────────────────────────────────

@dataclass
class ParsedHwpxParagraph:
    """
    hwpx의 단일 paragraph를 탐지 단위로 변환한 구조.

    section 값:
    - "body":        본문 paragraph (hs:sec 직속 hp:p)
    - "table_cell":  표 셀 내부 paragraph (cell.subList 안의 hp:p)

    paragraphNo 의미 (section별):
    - body:        hs:sec 직속 hp:p의 인덱스 (빈 paragraph 포함 원문 인덱스 유지)
    - table_cell:  표를 포함하는 본문 paragraph의 인덱스 (location 식별용)

    필드 사용 여부:
    - section_no:           hwpx의 section 인덱스 (section0.xml은 0)
    - table_index:          table_cell에서만 사용 (paragraph 내 표 순번, 0-based)
    - row_no, col_no:       table_cell에서만 사용 (0-based)
    - cell_paragraph_no:    table_cell에서만 사용 (셀 내부 paragraph 인덱스)
    - preceding_text:       앞 paragraph 텍스트 (locationLabel 보조용, A안)

    표 셀 위치 정책:
    - paragraphNo: 표가 들어있는 본문 paragraph 인덱스
    - tableIndex:  해당 paragraph 내 표 순번 (한 paragraph에 표 여러 개 가능)
    - 같은 paragraph에 표 5개가 있어도 tableIndex로 구분됩니다.
    """

    section_no: int
    section: str
    text: str
    paragraph_no: int
    table_index: int | None = None
    row_no: int | None = None
    col_no: int | None = None
    cell_paragraph_no: int | None = None
    preceding_text: str | None = None  # 앞 paragraph 텍스트 (A안)

    @property
    def location_label(self) -> str:
        """
        사용자 표시용 라벨.

        형식:
        - body:        "1번 본문 14번째 문단: context..."
        - table_cell:  "1번 본문 14번째 문단 표 N번 R행 C열: 셀텍스트 (앞 문단: ...)"

        section_no는 1-based(예: "1번 본문"), paragraph_no도 1-based(예: "14번째 문단").
        table_index, row_no, col_no도 1-based 표시.

        표 셀의 경우 셀 텍스트가 짧고 어느 표인지 식별이 어려우므로,
        preceding_text가 있으면 보조 정보로 추가합니다 (A안).
        """
        section_disp = self.section_no + 1
        para_disp = self.paragraph_no + 1

        if self.section == "body":
            base = f"{section_disp}번 본문 {para_disp}번째 문단"
            return make_location_label_with_context(base, self.text, max_length=30)

        if self.section == "table_cell":
            table_disp = (self.table_index + 1) if self.table_index is not None else "?"
            row_disp = (self.row_no + 1) if self.row_no is not None else "?"
            col_disp = (self.col_no + 1) if self.col_no is not None else "?"
            base = (
                f"{section_disp}번 본문 {para_disp}번째 문단 "
                f"표 {table_disp}번 {row_disp}행 {col_disp}열"
            )
            label = make_location_label_with_context(base, self.text, max_length=30)

            # 앞 paragraph 텍스트 보강 (hwpx 특유 처리)
            if self.preceding_text and self.preceding_text.strip():
                preceding_short = self.preceding_text.strip()
                if len(preceding_short) > 20:
                    preceding_short = preceding_short[:20] + "..."
                label += f" (앞 문단: {preceding_short})"

            return label

        return f"{section_disp}번 본문 {para_disp}번째 문단 ({self.section})"

    @property
    def location_meta(self) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "fileType": "hwpx",
            "sectionNo": self.section_no,
            "section": self.section,
            "paragraphNo": self.paragraph_no,
        }

        if self.table_index is not None:
            meta["tableIndex"] = self.table_index

        if self.row_no is not None:
            meta["rowNo"] = self.row_no

        if self.col_no is not None:
            meta["colNo"] = self.col_no

        if self.cell_paragraph_no is not None:
            meta["cellParagraphNo"] = self.cell_paragraph_no

        return meta


# ── hwpx ZIP 로드 ──────────────────────────────────────────────

def load_hwpx_sections(input_path: str | Path) -> list[tuple[int, ET.Element]]:
    """
    hwpx 파일에서 모든 section XML을 로드합니다.

    Returns:
        [(section_no, root_element), ...]

    section_no는 파일명 (section0.xml → 0, section1.xml → 1, ...) 기준입니다.
    """
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"hwpx 파일을 찾을 수 없습니다: {input_path}")

    sections: list[tuple[int, ET.Element]] = []

    with zipfile.ZipFile(input_path, "r") as zf:
        # Contents/section{N}.xml 파일들을 찾아서 N 순으로 정렬
        section_names: list[tuple[int, str]] = []
        for name in zf.namelist():
            if not name.startswith("Contents/section"):
                continue
            if not name.endswith(".xml"):
                continue

            # "Contents/section0.xml" → "0" → 0
            stem = name[len("Contents/section"):-len(".xml")]
            try:
                section_no = int(stem)
            except ValueError:
                continue

            section_names.append((section_no, name))

        section_names.sort()

        if not section_names:
            raise ValueError(
                f"hwpx 파일 안에 Contents/section{{N}}.xml이 없습니다: {input_path}"
            )

        for section_no, name in section_names:
            with zf.open(name) as f:
                tree = ET.parse(f)
                root = tree.getroot()
                sections.append((section_no, root))

    return sections


# ── paragraph 텍스트 추출 ──────────────────────────────────────

def get_paragraph_own_text(p: ET.Element) -> str:
    """
    paragraph 자신의 텍스트만 추출합니다.

    경로: p > hp:run > hp:t (직속 자식만)

    표 안의 hp:t는 hp:run의 직속이 아니라 hp:tbl > hp:tr > hp:tc > hp:subList > hp:p > ... 안에 있으므로
    이 함수는 표 안 텍스트를 제외하고 paragraph 자체 텍스트만 가져옵니다.

    1단계 분석 결과 검증된 방식입니다.
    """
    texts: list[str] = []
    for run in p.findall(f"{HP}run"):
        for child in run:
            if child.tag == f"{HP}t" and child.text:
                texts.append(child.text)
    return "".join(texts)


def find_tables_in_paragraph(p: ET.Element) -> list[ET.Element]:
    """
    paragraph 내부의 hp:tbl 요소 목록을 paragraph 내 등장 순서대로 반환합니다.

    hp:tbl은 hp:run의 자식으로 들어가 있습니다.
    """
    tables: list[ET.Element] = []
    for run in p.findall(f"{HP}run"):
        for child in run:
            if child.tag == f"{HP}tbl":
                tables.append(child)
    return tables


# ── paragraph 순회 함수 ────────────────────────────────────────

def _iter_cell_paragraphs_for_table(
    table: ET.Element,
    section_no: int,
    paragraph_no: int,
    table_index: int,
    preceding_text: str | None,
) -> Iterator[ParsedHwpxParagraph]:
    """
    단일 표(hp:tbl)의 모든 셀 paragraph를 yield합니다.

    셀 내부 paragraph 인덱스(cell_paragraph_no)는 빈 paragraph를 포함한 원문 인덱스를 유지합니다.
    빈 paragraph(strip 기준)는 탐지 대상에서 제외합니다.

    Args:
        table: hp:tbl 요소
        section_no: hwpx의 section 인덱스
        paragraph_no: 표를 포함하는 본문 paragraph의 인덱스
        table_index: paragraph 내 표 순번 (0-based)
        preceding_text: 표를 포함하는 paragraph의 앞 paragraph 텍스트
    """
    for row_index, row in enumerate(table.findall(f"{HP}tr")):
        for col_index, cell in enumerate(row.findall(f"{HP}tc")):
            sublist = cell.find(f"{HP}subList")
            if sublist is None:
                continue

            # 셀 내부 paragraph 순회
            for cp_index, cp in enumerate(sublist.findall(f"{HP}p")):
                cp_text = get_paragraph_own_text(cp)

                if not cp_text.strip():
                    continue

                yield ParsedHwpxParagraph(
                    section_no=section_no,
                    section="table_cell",
                    text=cp_text,
                    paragraph_no=paragraph_no,
                    table_index=table_index,
                    row_no=row_index,
                    col_no=col_index,
                    cell_paragraph_no=cp_index,
                    preceding_text=preceding_text,
                )


def _iter_section_paragraphs(
    section_no: int,
    root: ET.Element,
) -> Iterator[ParsedHwpxParagraph]:
    """
    단일 section의 본문 paragraph와 표 셀 paragraph를 yield합니다.

    순회 방식:
    1. 본문 paragraph (hs:sec > hp:p)를 순서대로 순회
    2. paragraph 자체 텍스트가 있으면(strip 기준) body paragraph로 yield
    3. paragraph 안에 표가 있으면 표 셀 paragraph를 이어서 yield
       - table_cell의 preceding_text는 "직전 본문 paragraph의 텍스트"
       - 직전 paragraph가 비어 있으면 그 이전 paragraph를 찾음 (최대 5단계까지 거슬러 올라감)

    paragraph_no는 hs:sec 직속 hp:p 인덱스(빈 paragraph 포함 원문 인덱스)를 유지합니다.
    """
    body_paragraphs = list(root)

    # 직전 비어있지 않은 paragraph 텍스트 추적용
    last_non_empty_text: str | None = None

    for para_index, p in enumerate(body_paragraphs):
        own_text = get_paragraph_own_text(p)
        own_text_stripped = own_text.strip()

        # 본문 paragraph로 yield (텍스트가 있을 때만)
        if own_text_stripped:
            yield ParsedHwpxParagraph(
                section_no=section_no,
                section="body",
                text=own_text,
                paragraph_no=para_index,
            )

        # 표 셀 yield (paragraph 안에 표가 있으면)
        tables = find_tables_in_paragraph(p)
        if tables:
            # preceding_text는 직전 비어있지 않은 paragraph
            preceding_text = last_non_empty_text

            for tbl_index, tbl in enumerate(tables):
                yield from _iter_cell_paragraphs_for_table(
                    tbl,
                    section_no=section_no,
                    paragraph_no=para_index,
                    table_index=tbl_index,
                    preceding_text=preceding_text,
                )

        # last_non_empty_text 업데이트 (다음 표를 위한 context)
        # - 본문 paragraph가 비어있지 않으면 이걸로 갱신
        # - 표만 있고 본문은 비어있는 paragraph는 last_non_empty_text를 갱신하지 않음
        #   (다음 표가 나왔을 때 앞 본문 paragraph를 참조해야 자연스러움)
        if own_text_stripped:
            last_non_empty_text = own_text_stripped


def iter_hwpx_paragraphs(input_path: str | Path) -> list[ParsedHwpxParagraph]:
    """
    hwpx 파일의 모든 section을 순회하며 paragraph 목록을 반환합니다.

    순회 대상:
    - 본문 paragraph (hs:sec > hp:p, 빈 paragraph strip 기준 제외)
    - 표 셀 paragraph (cell.subList > hp:p, 빈 paragraph strip 기준 제외)

    순회 제외:
    - header / footer / footnote / endnote / 메모 (15주차 PoC 범위 외)
    - 중첩 표 (표 안의 표) - PoC에서는 처리하지 않음

    반환 순서:
    - section_no 오름차순
    - 같은 section 안에서는 본문 paragraph 순서대로
    - paragraph 안에 표가 있으면 본문 paragraph 다음에 표 셀들 (표 순번 → 행 → 열 → 셀 내부 paragraph 순)
    """
    results: list[ParsedHwpxParagraph] = []

    for section_no, root in load_hwpx_sections(input_path):
        results.extend(_iter_section_paragraphs(section_no, root))

    return results


# ── Detection 어댑터 ──────────────────────────────────────────

from typing import Callable

try:
    from src.deidentify_target_builder import DeidentifyPlan, build_deidentify_plan
except ModuleNotFoundError:
    from deidentify_target_builder import DeidentifyPlan, build_deidentify_plan


def _make_target_dict_from_regex(
    raw: Any,
    paragraph: ParsedHwpxParagraph,
    order: int,
) -> dict[str, Any] | None:
    """
    regex_detector의 결과(DetectionResult 또는 유사 dict)를 Detection dict로 변환합니다.

    docx_detector / pptx_detector의 동일 함수와 같은 패턴.
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
        "context": paragraph.text,
        "locationLabel": paragraph.location_label,
        "locationMeta": paragraph.location_meta,
        "start": int(start),
        "end": int(end),
        "sensitiveType": _get(raw, "sensitive_type", "sensitiveType", default=None),
        "sensitiveCategory": _get(raw, "sensitive_category", "sensitiveCategory", default=label),
        "reason": str(desc) if desc else f"정규식 탐지: {label}",
        "_order": order,
    }


def _make_target_dict_from_ner(
    raw: dict[str, Any],
    paragraph: ParsedHwpxParagraph,
    order: int,
    *,
    threshold: float,
) -> dict[str, Any] | None:
    """
    Hugging Face NER 출력(aggregation_strategy="simple" 기준)을 Detection dict로 변환합니다.
    """
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

    matched = paragraph.text[start:end] or raw.get("word") or ""

    return {
        "label": "성명",
        "matched": str(matched),
        "grade": "S",
        "action": "마스킹",
        "source": "ner",
        "context": paragraph.text,
        "locationLabel": paragraph.location_label,
        "locationMeta": paragraph.location_meta,
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
    paragraph: ParsedHwpxParagraph,
    order: int,
    *,
    threshold: float,
    prob_map: dict[str, float] | None = None,
) -> dict[str, Any] | None:
    """
    AI 문장분류 결과를 review target dict로 변환합니다.
    """
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
        "context": paragraph.text,
        "locationLabel": paragraph.location_label,
        "locationMeta": paragraph.location_meta,
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

def detect_in_hwpx(
    input_path: str,
    *,
    regex_detect_func: Callable[[str], list[Any]] | None = None,
    ner_detect_func: Callable[[str], list[dict[str, Any]]] | None = None,
    ai_predict_func: Callable[[str], tuple[str, float, dict[str, float]]] | None = None,
    ner_threshold: float = 0.8,
    ai_threshold: float = 0.6,
) -> DeidentifyPlan:
    """
    hwpx 파일의 모든 paragraph(본문 + 표 셀)를 순회하며 탐지를 수행하고 DeidentifyPlan을 생성합니다.

    13주차 detect_in_docx() / 14주차 detect_in_pptx()와 동일한 시그니처.
    탐지 함수는 주입형으로 받아 단위 테스트에서 모델 의존성을 끊습니다.
    """
    if regex_detect_func is None:
        try:
            from src.regex_detector import detect_patterns as _detect_patterns
        except ModuleNotFoundError:
            from regex_detector import detect_patterns as _detect_patterns
        regex_detect_func = _detect_patterns

    paragraphs = iter_hwpx_paragraphs(input_path)

    detections: list[dict[str, Any]] = []
    order = 0

    for paragraph in paragraphs:
        # regex
        raw_regex = regex_detect_func(paragraph.text) or []
        for raw in raw_regex:
            detection = _make_target_dict_from_regex(raw, paragraph, order)
            if detection is not None:
                detections.append(detection)
                order += 1

        # NER
        if ner_detect_func is not None:
            try:
                raw_ner = ner_detect_func(paragraph.text) or []
            except Exception as exc:
                print(f"[NER] {paragraph.location_label} 탐지 실패: {exc}")
                raw_ner = []

            for raw in raw_ner:
                detection = _make_target_dict_from_ner(
                    raw, paragraph, order, threshold=ner_threshold,
                )
                if detection is not None:
                    detections.append(detection)
                    order += 1

        # AI
        if ai_predict_func is not None:
            try:
                grade, confidence, prob_map = ai_predict_func(paragraph.text)
            except Exception as exc:
                print(f"[AI] {paragraph.location_label} 예측 실패: {exc}")
                grade, confidence, prob_map = "O", 0.0, {}

            if grade is not None and confidence is not None:
                detection = _make_target_dict_from_ai(
                    grade, confidence, paragraph, order,
                    threshold=ai_threshold, prob_map=prob_map,
                )
                if detection is not None:
                    detections.append(detection)
                    order += 1

    return build_deidentify_plan(detections)


# ── guide 생성 ─────────────────────────────────────────────────

# hwpx 전용 warning type은 common_apply_utils.py로 이전합니다.
try:
    from src.common_apply_utils import (
        WARNING_MISSING_SECTION_NO,
        WARNING_SECTION_OUT_OF_RANGE,
    )
except (ModuleNotFoundError, ImportError):
    try:
        from common_apply_utils import (
            WARNING_MISSING_SECTION_NO,
            WARNING_SECTION_OUT_OF_RANGE,
        )
    except ImportError:
        # 아직 추가되지 않은 경우 대비
        WARNING_MISSING_SECTION_NO = "missing_section_no"
        WARNING_SECTION_OUT_OF_RANGE = "section_out_of_range"


def _make_hwpx_location_key(meta: dict[str, Any]) -> tuple | None:
    """
    hwpx target의 위치 그룹화 키를 생성합니다.

    - body:        (sectionNo, "body", paragraphNo)
    - table_cell:  (sectionNo, "table_cell", paragraphNo, tableIndex, rowNo, colNo, cellParagraphNo)
    """
    section_no = meta.get("sectionNo")
    section = str(meta.get("section") or "")
    paragraph_no = meta.get("paragraphNo")

    if section_no is None or paragraph_no is None:
        return None

    if section == "body":
        return (int(section_no), "body", int(paragraph_no))

    if section == "table_cell":
        table_index = meta.get("tableIndex")
        row_no = meta.get("rowNo")
        col_no = meta.get("colNo")
        cell_paragraph_no = meta.get("cellParagraphNo")
        if (table_index is None or row_no is None
                or col_no is None or cell_paragraph_no is None):
            return None
        return (
            int(section_no), "table_cell", int(paragraph_no),
            int(table_index), int(row_no), int(col_no), int(cell_paragraph_no),
        )

    # 알 수 없는 section
    return None


def _format_hwpx_location_for_label(meta: dict[str, Any]) -> str:
    """경고 메시지/locationLabel 보조용 간단 표현."""
    section_no = meta.get("sectionNo")
    paragraph_no = meta.get("paragraphNo")
    section = meta.get("section")

    section_disp = (section_no + 1) if section_no is not None else "?"
    para_disp = (paragraph_no + 1) if paragraph_no is not None else "?"

    if section == "body":
        return f"{section_disp}번 본문 {para_disp}번째 문단"
    if section == "table_cell":
        table_idx = meta.get("tableIndex")
        row = meta.get("rowNo")
        col = meta.get("colNo")
        table_disp = (table_idx + 1) if table_idx is not None else "?"
        row_disp = (row + 1) if row is not None else "?"
        col_disp = (col + 1) if col is not None else "?"
        return (
            f"{section_disp}번 본문 {para_disp}번째 문단 "
            f"표 {table_disp}번 {row_disp}행 {col_disp}열"
        )
    return f"{section_disp}번 본문 {para_disp}번째 문단 ({section})"


def _index_hwpx_paragraphs(input_path: str | Path) -> dict[tuple, str]:
    """
    hwpx 파일에서 paragraph 위치 키 → text 매핑을 미리 생성합니다.

    빈 paragraph는 iter_hwpx_paragraphs에서 제외되므로 자동으로 dict에 포함되지 않습니다.
    """
    index: dict[tuple, str] = {}

    for paragraph in iter_hwpx_paragraphs(input_path):
        key = _make_hwpx_location_key(paragraph.location_meta)
        if key is None:
            continue
        index[key] = paragraph.text

    return index


def _group_targets_by_location(targets):
    """
    auto target을 hwpx location key 기준으로 묶습니다.

    fileType이 hwpx가 아닌 target은 제외합니다.
    필수 필드가 누락되거나 알 수 없는 section이면 skipped item으로 처리합니다.
    """
    try:
        from src.common_apply_result import CommonApplyItem
        from src.common_apply_utils import (
            WARNING_MISSING_PARAGRAPH_NO,
            WARNING_MISSING_TABLE_CELL_LOCATION,
            WARNING_UNKNOWN_SECTION,
            format_warning,
        )
    except ModuleNotFoundError:
        from common_apply_result import CommonApplyItem
        from common_apply_utils import (
            WARNING_MISSING_PARAGRAPH_NO,
            WARNING_MISSING_TABLE_CELL_LOCATION,
            WARNING_UNKNOWN_SECTION,
            format_warning,
        )

    grouped: dict[tuple, list] = {}
    skipped_items: list = []
    warnings: list[str] = []

    for target in targets:
        meta = target.location_meta or {}

        if str(meta.get("fileType") or "").lower() != "hwpx":
            continue

        section = str(meta.get("section") or "")
        key = _make_hwpx_location_key(meta)

        if key is None:
            label = target.location_label or _format_hwpx_location_for_label(meta)

            if section not in {"body", "table_cell"}:
                warning = format_warning(
                    WARNING_UNKNOWN_SECTION,
                    f"{label}: 알 수 없는 section={section!r}이므로 안내를 생성하지 않습니다.",
                )
            elif meta.get("sectionNo") is None:
                warning = format_warning(
                    WARNING_MISSING_SECTION_NO,
                    f"{label}: sectionNo가 없어 안내를 생성하지 못했습니다.",
                )
            elif meta.get("paragraphNo") is None:
                warning = format_warning(
                    WARNING_MISSING_PARAGRAPH_NO,
                    f"{label}: paragraphNo가 없어 안내를 생성하지 못했습니다.",
                )
            else:
                # section="table_cell"인데 보조 필드 누락
                # (tableIndex/rowNo/colNo/cellParagraphNo 중 하나 이상)
                missing_fields = [
                    field_name
                    for field_name in (
                        "tableIndex", "rowNo", "colNo", "cellParagraphNo",
                    )
                    if meta.get(field_name) is None
                ]
                warning = format_warning(
                    WARNING_MISSING_TABLE_CELL_LOCATION,
                    f"{label}: 표 셀 위치 필드가 누락되어 안내를 생성하지 못했습니다. "
                    f"missing={missing_fields}",
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
    paragraph_text: str | None,
    targets,
    *,
    deletion_mode: str,
):
    """
    한 location에 속한 target 목록에 대해 guide 모드 CommonApplyItem을 생성합니다.

    docx_detector._build_guide_item_for_paragraph / pptx_detector._build_guide_item_for_location
    과 동일한 패턴.
    """
    try:
        from src.common_apply_result import CommonApplyItem
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
        from common_apply_result import CommonApplyItem
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
    location_label = representative.location_label or _format_hwpx_location_for_label(
        representative.location_meta or {}
    )
    location_meta = representative.location_meta or {}

    warnings: list[str] = []

    # paragraph_text가 None이면 hwpx에서 해당 위치를 찾을 수 없음
    if paragraph_text is None:
        warning = format_warning(
            WARNING_SECTION_OUT_OF_RANGE,
            f"{location_label}: 위치가 현재 hwpx에서 발견되지 않습니다 (key={key}).",
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

    # 빈 paragraph 방어
    if not paragraph_text.strip():
        warning = format_warning(
            WARNING_EMPTY_PARAGRAPH_TARGET,
            f"{location_label}: 빈 paragraph를 가리키는 target은 안내를 생성하지 않습니다.",
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
        and normalize_nfc(target.context) != normalize_nfc(paragraph_text)
        for target in targets
    ):
        warnings.append(
            format_warning(
                WARNING_CONTEXT_MISMATCH,
                f"{location_label}: target.context와 실제 paragraph 텍스트가 다릅니다. "
                "paragraph 텍스트 기준으로 slice 검증 후 권장 여부를 판단합니다.",
            )
        )

    # slice 검증
    valid_targets = []
    skipped_count = 0

    for target in targets:
        warning_type, slice_error = validate_slice_against_text(paragraph_text, target)
        if slice_error is not None:
            warnings.append(
                format_warning(warning_type, f"{location_label}: {slice_error}")
            )
            skipped_count += 1
            continue
        valid_targets.append(target)

    if valid_targets:
        apply_result = apply_targets_to_text(
            paragraph_text,
            valid_targets,
            deletion_mode=deletion_mode,
        )
        applied_text = apply_result.applied_text
        warnings.extend(apply_result.warnings)
        applied_count = len(apply_result.applied_targets)
        skipped_count += len(apply_result.skipped_targets)
    else:
        applied_text = paragraph_text
        applied_count = 0

    return CommonApplyItem(
        locationLabel=location_label,
        locationMeta=location_meta,
        label=labels_for_targets(targets),
        action=actions_for_targets(targets),
        originalText=paragraph_text,
        appliedText=applied_text,
        status=make_status(applied_count, skipped_count),
        appliedTargetCount=applied_count,
        skippedTargetCount=skipped_count,
        warnings=warnings,
    )


def build_guide_for_hwpx(
    input_path: str,
    plan: DeidentifyPlan,
    *,
    deletion_mode: str = "delete",
):
    """
    DeidentifyPlan을 받아 guide 모드 CommonApplyResult를 생성합니다.

    실제 파일을 수정하지 않으며, outputFilePath는 None입니다.
    """
    try:
        from src.common_apply_result import (
            APPLY_MODE_GUIDE,
            CommonApplyResult,
            build_summary,
            make_review_items,
        )
    except ModuleNotFoundError:
        from common_apply_result import (
            APPLY_MODE_GUIDE,
            CommonApplyResult,
            build_summary,
            make_review_items,
        )

    paragraph_index = _index_hwpx_paragraphs(input_path)

    grouped, skipped_items, global_warnings = _group_targets_by_location(plan.auto_targets)

    auto_results = list(skipped_items)

    for key, targets in grouped.items():
        paragraph_text = paragraph_index.get(key)
        item = _build_guide_item_for_location(
            key,
            paragraph_text,
            targets,
            deletion_mode=deletion_mode,
        )
        auto_results.append(item)

    review_items = make_review_items(plan.review_targets)
    summary = build_summary(auto_results, review_items, global_warnings)

    return CommonApplyResult(
        fileType="hwpx",
        applyMode=APPLY_MODE_GUIDE,
        inputFilePath=str(input_path),
        outputFilePath=None,
        autoResults=auto_results,
        reviewTargets=review_items,
        warnings=global_warnings,
        summary=summary,
    )


def detect_and_build_guide_for_hwpx(
    input_path: str,
    *,
    regex_detect_func: Callable[[str], list[Any]] | None = None,
    ner_detect_func: Callable[[str], list[dict[str, Any]]] | None = None,
    ai_predict_func: Callable[[str], tuple[str, float, dict[str, float]]] | None = None,
    ner_threshold: float = 0.8,
    ai_threshold: float = 0.6,
    deletion_mode: str = "delete",
):
    """detect_in_hwpx + build_guide_for_hwpx 편의 wrapper."""
    plan = detect_in_hwpx(
        input_path,
        regex_detect_func=regex_detect_func,
        ner_detect_func=ner_detect_func,
        ai_predict_func=ai_predict_func,
        ner_threshold=ner_threshold,
        ai_threshold=ai_threshold,
    )
    return build_guide_for_hwpx(
        input_path, plan, deletion_mode=deletion_mode,
    )
