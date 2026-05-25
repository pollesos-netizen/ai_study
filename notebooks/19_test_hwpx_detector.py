"""
15주차 hwpx detector + guide builder 단위 테스트 (TC1~TC22)

13주차 docx, 14주차 pptx 테스트 패턴을 따라 작성했습니다.
hwpx 특유 케이스 추가:
- TC18~TC22: 본문/표 셀 텍스트 분리, 한 paragraph에 표 여러 개, 앞 paragraph context

hwpx는 외부 라이브러리(python-docx/python-pptx 같은) 없이 직접 ZIP+XML로 생성합니다.
"""

from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from common_apply_result import APPLY_MODE_GUIDE
from deidentify_target_builder import DeidentifyPlan, DeidentifyTarget
from hwpx_detector import (
    build_guide_for_hwpx,
    detect_in_hwpx,
    iter_hwpx_paragraphs,
)


# ── hwpx 생성 헬퍼 ─────────────────────────────────────────────

HWPX_NS_HEADER = (
    'xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"'
)


def make_paragraph_xml(text: str, tables: list[list[list[str]]] | None = None) -> str:
    """
    paragraph XML 조각 생성.

    Args:
        text: paragraph 본문 텍스트 (빈 문자열 가능)
        tables: paragraph 안에 들어갈 표 목록.
                각 표는 [["셀00", "셀01"], ["셀10", "셀11"]] 형식
    """
    runs_xml = ""

    # 본문 텍스트가 있으면 run에 hp:t로 추가
    if text:
        runs_xml += f'<hp:run><hp:t>{escape(text)}</hp:t></hp:run>'

    # 표가 있으면 run 안에 hp:tbl로 추가
    if tables:
        for table in tables:
            rows_xml = ""
            for row in table:
                cells_xml = ""
                for cell_text in row:
                    # 셀 안에 paragraph 1개만 넣음
                    cell_para = (
                        f'<hp:p><hp:run><hp:t>{escape(cell_text)}</hp:t></hp:run></hp:p>'
                    )
                    cells_xml += (
                        f'<hp:tc>'
                        f'<hp:subList>{cell_para}</hp:subList>'
                        f'</hp:tc>'
                    )
                rows_xml += f'<hp:tr>{cells_xml}</hp:tr>'
            runs_xml += f'<hp:run><hp:tbl>{rows_xml}</hp:tbl></hp:run>'

    if not runs_xml:
        # 빈 paragraph는 빈 run 하나
        runs_xml = '<hp:run/>'

    return f'<hp:p>{runs_xml}</hp:p>'


def make_section_xml(paragraphs_xml: list[str]) -> str:
    """section XML 전체 생성."""
    inner = "".join(paragraphs_xml)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        f'<hs:sec {HWPX_NS_HEADER}>{inner}</hs:sec>'
    )


def make_hwpx_file(path: Path, paragraphs_data: list[dict]) -> None:
    """
    테스트용 hwpx 파일 생성.

    paragraphs_data: [{"text": "본문", "tables": [[["A","B"]]]}, ...]
    """
    para_xmls = [
        make_paragraph_xml(pd.get("text", ""), pd.get("tables"))
        for pd in paragraphs_data
    ]
    section_xml = make_section_xml(para_xmls)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", section_xml)


def make_multi_section_hwpx(path: Path, sections_data: list[list[dict]]) -> None:
    """
    여러 section을 가진 hwpx 생성.

    sections_data[i]는 i번째 section의 paragraphs_data.
    """
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        for idx, paragraphs_data in enumerate(sections_data):
            para_xmls = [
                make_paragraph_xml(pd.get("text", ""), pd.get("tables"))
                for pd in paragraphs_data
            ]
            section_xml = make_section_xml(para_xmls)
            zf.writestr(f"Contents/section{idx}.xml", section_xml)


def _make_target(
    *,
    label, matched, start, end, source, action,
    section_no, section, paragraph_no, context,
    table_index=None, row_no=None, col_no=None, cell_paragraph_no=None,
    grade="S", order=0,
):
    meta = {
        "fileType": "hwpx",
        "sectionNo": section_no,
        "section": section,
        "paragraphNo": paragraph_no,
    }
    if table_index is not None:
        meta["tableIndex"] = table_index
    if row_no is not None:
        meta["rowNo"] = row_no
    if col_no is not None:
        meta["colNo"] = col_no
    if cell_paragraph_no is not None:
        meta["cellParagraphNo"] = cell_paragraph_no

    return DeidentifyTarget(
        label=label, matched=matched, action=action,
        location_label=None,
        location_meta=meta,
        start=start, end=end, source=source,
        reason=f"테스트용 {source} 탐지",
        grade=grade, context=context, order=order,
    )


_runner_path = str(Path(__file__).resolve().parent)
if _runner_path not in sys.path:
    sys.path.insert(0, _runner_path)
from test_helpers import TestRunner, run_test_functions

_runner = TestRunner("15주차 hwpx detector 단위 테스트")


def _check(tc_id: str, condition: bool, message: str = "") -> None:
    _runner.check(tc_id, condition, message)


# ── TC1: 이메일 본문 paragraph ─────────────────────────────────

def tc1(tmp_dir: Path) -> None:
    print("\nTC1: 이메일이 있는 본문 paragraph 마스킹")

    text = "담당자 이메일은 test@example.com입니다."
    path = tmp_dir / "tc1.hwpx"
    make_hwpx_file(path, [{"text": text}])

    matched = "test@example.com"
    s = text.index(matched); e = s + len(matched)
    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="이메일 주소", matched=matched, start=s, end=e,
                         source="regex", action="마스킹",
                         section_no=0, section="body", paragraph_no=0,
                         context=text),
        ],
        review_targets=[],
    )

    result = build_guide_for_hwpx(str(path), plan)
    _check("TC1.applyMode", result.applyMode == APPLY_MODE_GUIDE)
    _check("TC1.outputFilePath_None", result.outputFilePath is None)
    _check("TC1.autoResults", len(result.autoResults) == 1)
    item = result.autoResults[0]
    _check("TC1.status", item.status == "applied")
    _check("TC1.applied_count", item.appliedTargetCount == 1)
    _check("TC1.preview", "*" * len(matched) in item.appliedText)


# ── TC2: 성명 본문 paragraph ──────────────────────────────────

def tc2(tmp_dir: Path) -> None:
    print("\nTC2: 성명 본문 paragraph 마스킹")

    text = "직원 김도윤의 서류를 검토했습니다."
    path = tmp_dir / "tc2.hwpx"
    make_hwpx_file(path, [{"text": text}])

    s = text.index("김도윤"); e = s + 3
    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="성명", matched="김도윤", start=s, end=e,
                         source="ner", action="마스킹",
                         section_no=0, section="body", paragraph_no=0,
                         context=text),
        ],
        review_targets=[],
    )
    result = build_guide_for_hwpx(str(path), plan)
    _check("TC2.status", result.autoResults[0].status == "applied")
    _check("TC2.preview", "***" in result.autoResults[0].appliedText)


# ── TC3: 성명 + 이메일 동시 ────────────────────────────────────

def tc3(tmp_dir: Path) -> None:
    print("\nTC3: 한 paragraph에 성명 + 이메일 동시")

    text = "담당자 김도윤의 이메일은 test@example.com입니다."
    path = tmp_dir / "tc3.hwpx"
    make_hwpx_file(path, [{"text": text}])

    s1 = text.index("김도윤"); e1 = s1 + 3
    s2 = text.index("test@example.com"); e2 = s2 + 16
    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="성명", matched="김도윤", start=s1, end=e1,
                         source="ner", action="마스킹",
                         section_no=0, section="body", paragraph_no=0,
                         context=text, order=0),
            _make_target(label="이메일 주소", matched="test@example.com",
                         start=s2, end=e2,
                         source="regex", action="마스킹",
                         section_no=0, section="body", paragraph_no=0,
                         context=text, order=1),
        ],
        review_targets=[],
    )
    result = build_guide_for_hwpx(str(path), plan)
    _check("TC3.autoResults", len(result.autoResults) == 1)
    _check("TC3.applied_count", result.autoResults[0].appliedTargetCount == 2)


# ── TC4: 내부 IP 삭제 (delete/mark) ────────────────────────────

def tc4(tmp_dir: Path) -> None:
    print("\nTC4: 내부 IP 삭제 (delete/mark)")

    text = "서버 IP는 192.168.0.1입니다."
    path = tmp_dir / "tc4.hwpx"
    make_hwpx_file(path, [{"text": text}])

    matched = "192.168.0.1"
    s = text.index(matched); e = s + len(matched)
    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="내부 IP 주소", matched=matched, start=s, end=e,
                         source="regex", action="삭제",
                         section_no=0, section="body", paragraph_no=0,
                         context=text, grade="C"),
        ],
        review_targets=[],
    )
    result = build_guide_for_hwpx(str(path), plan)
    _check("TC4.delete", matched not in result.autoResults[0].appliedText)

    result_mark = build_guide_for_hwpx(str(path), plan, deletion_mode="mark")
    _check("TC4.mark", "(삭제됨)" in result_mark.autoResults[0].appliedText)


# ── TC5: reviewTargets 보존 ────────────────────────────────────

def tc5(tmp_dir: Path) -> None:
    print("\nTC5: reviewTargets 보존")

    text = "입찰 평가표를 검토했습니다."
    path = tmp_dir / "tc5.hwpx"
    make_hwpx_file(path, [{"text": text}])

    review = _make_target(
        label="민감정보", matched="", start=None, end=None,
        source="ai", action="검토 필요",
        section_no=0, section="body", paragraph_no=0,
        context=text, grade="C",
    )
    plan = DeidentifyPlan(auto_targets=[], review_targets=[review])
    result = build_guide_for_hwpx(str(path), plan)
    _check("TC5.review_count", len(result.reviewTargets) == 1)
    _check("TC5.auto_empty", len(result.autoResults) == 0)
    _check("TC5.review_action", result.reviewTargets[0].action == "검토 필요")


# ── TC6: paragraphNo 없음 ──────────────────────────────────────

def tc6(tmp_dir: Path) -> None:
    print("\nTC6: paragraphNo 없음 → missing_paragraph_no")

    text = "임의 텍스트."
    path = tmp_dir / "tc6.hwpx"
    make_hwpx_file(path, [{"text": text}])

    target = DeidentifyTarget(
        label="이메일", matched="test@example.com", action="마스킹",
        location_label="알 수 없음",
        location_meta={"fileType": "hwpx", "sectionNo": 0, "section": "body"},
        start=0, end=16, source="regex", reason="test",
        grade="S", context="test",
    )
    plan = DeidentifyPlan(auto_targets=[target], review_targets=[])
    result = build_guide_for_hwpx(str(path), plan)
    _check("TC6.skipped", result.autoResults[0].status == "skipped")
    _check("TC6.warning",
           any("[missing_paragraph_no]" in w
               for w in result.autoResults[0].warnings))


# ── TC7: section 범위 초과 ─────────────────────────────────────

def tc7(tmp_dir: Path) -> None:
    print("\nTC7: section 범위 초과 → section_out_of_range")

    path = tmp_dir / "tc7.hwpx"
    make_hwpx_file(path, [{"text": "단 하나의 paragraph."}])

    target = _make_target(
        label="성명", matched="홍길동", start=0, end=3,
        source="ner", action="마스킹",
        section_no=99,  # 범위 초과
        section="body", paragraph_no=0,
        context="홍길동 무관",
    )
    plan = DeidentifyPlan(auto_targets=[target], review_targets=[])
    result = build_guide_for_hwpx(str(path), plan)
    item = result.autoResults[0]
    _check("TC7.skipped", item.status == "skipped")
    _check("TC7.warning",
           any("[section_out_of_range]" in w for w in item.warnings))


# ── TC8: context 불일치, slice 일치 ────────────────────────────

def tc8(tmp_dir: Path) -> None:
    print("\nTC8: context 불일치, slice 일치 → 권장 + warning")

    text = "담당자 이메일은 test@example.com입니다."
    path = tmp_dir / "tc8.hwpx"
    make_hwpx_file(path, [{"text": text}])

    matched = "test@example.com"
    s = text.index(matched); e = s + 16
    target = _make_target(
        label="이메일", matched=matched, start=s, end=e,
        source="regex", action="마스킹",
        section_no=0, section="body", paragraph_no=0,
        context="담당자 이메일: test@example.com",  # 실제와 다름
    )
    plan = DeidentifyPlan(auto_targets=[target], review_targets=[])
    result = build_guide_for_hwpx(str(path), plan)
    item = result.autoResults[0]
    _check("TC8.status_applied", item.status == "applied")
    _check("TC8.applied_count", item.appliedTargetCount == 1)
    _check("TC8.context_mismatch",
           any("[context_mismatch]" in w for w in item.warnings))


# ── TC9: slice 불일치 ─────────────────────────────────────────

def tc9(tmp_dir: Path) -> None:
    print("\nTC9: slice 불일치 → skip + warning")

    text = "담당자 이메일은 test@example.com입니다."
    path = tmp_dir / "tc9.hwpx"
    make_hwpx_file(path, [{"text": text}])

    target = _make_target(
        label="이메일", matched="test@example.com",
        start=0, end=5,  # 매치되지 않는 위치
        source="regex", action="마스킹",
        section_no=0, section="body", paragraph_no=0,
        context=text,
    )
    plan = DeidentifyPlan(auto_targets=[target], review_targets=[])
    result = build_guide_for_hwpx(str(path), plan)
    item = result.autoResults[0]
    _check("TC9.skipped", item.status == "skipped")
    _check("TC9.warning",
           any("[slice_mismatch]" in w for w in item.warnings))


# ── TC10: 여러 paragraph 분산 ──────────────────────────────────

def tc10(tmp_dir: Path) -> None:
    print("\nTC10: 여러 paragraph에 target 분산")

    t1 = "이메일: test@example.com"
    t2 = "전화번호: 010-1234-5678"
    path = tmp_dir / "tc10.hwpx"
    make_hwpx_file(path, [{"text": t1}, {"text": t2}])

    s1 = t1.index("test@example.com"); e1 = s1 + 16
    s2 = t2.index("010-1234-5678"); e2 = s2 + 13
    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="이메일", matched="test@example.com",
                         start=s1, end=e1, source="regex", action="마스킹",
                         section_no=0, section="body", paragraph_no=0,
                         context=t1),
            _make_target(label="전화번호", matched="010-1234-5678",
                         start=s2, end=e2, source="regex", action="마스킹",
                         section_no=0, section="body", paragraph_no=1,
                         context=t2),
        ],
        review_targets=[],
    )
    result = build_guide_for_hwpx(str(path), plan)
    _check("TC10.count", len(result.autoResults) == 2)
    _check("TC10.all_applied",
           all(it.status == "applied" for it in result.autoResults))


# ── TC11: summary 정합성 ───────────────────────────────────────

def tc11(tmp_dir: Path) -> None:
    print("\nTC11: summary 정합성")

    t1 = "이메일: test@example.com"
    t2 = "전화: 010-1234-5678"
    path = tmp_dir / "tc11.hwpx"
    make_hwpx_file(path, [{"text": t1}, {"text": t2}])

    s1 = t1.index("test@example.com"); e1 = s1 + 16
    s2 = t2.index("010-1234-5678"); e2 = s2 + 13
    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="이메일", matched="test@example.com",
                         start=s1, end=e1, source="regex", action="마스킹",
                         section_no=0, section="body", paragraph_no=0,
                         context=t1),
            _make_target(label="전화번호", matched="010-1234-5678",
                         start=s2, end=e2, source="regex", action="마스킹",
                         section_no=0, section="body", paragraph_no=1,
                         context=t2),
        ],
        review_targets=[],
    )
    result = build_guide_for_hwpx(str(path), plan)
    s = result.summary
    _check("TC11.total", s.totalLocations == len(result.autoResults))
    _check("TC11.breakdown",
           s.appliedLocations + s.partialLocations + s.skippedLocations
           == s.totalLocations)
    sum_targets = sum(it.appliedTargetCount + it.skippedTargetCount
                      for it in result.autoResults)
    _check("TC11.autoTargetCount", s.autoTargetCount == sum_targets)


# ── TC12: deletion_mode=mark ──────────────────────────────────

def tc12(tmp_dir: Path) -> None:
    print("\nTC12: deletion_mode=mark")

    text = "VLAN 100을 사용합니다."
    path = tmp_dir / "tc12.hwpx"
    make_hwpx_file(path, [{"text": text}])

    matched = "VLAN 100"
    s = text.index(matched); e = s + len(matched)
    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="VLAN", matched=matched, start=s, end=e,
                         source="regex", action="삭제",
                         section_no=0, section="body", paragraph_no=0,
                         context=text, grade="C"),
        ],
        review_targets=[],
    )
    result = build_guide_for_hwpx(str(path), plan, deletion_mode="mark")
    _check("TC12.mark", "(삭제됨)" in result.autoResults[0].appliedText)


# ── TC13: 빈 paragraph 제외 ────────────────────────────────────

def tc13(tmp_dir: Path) -> None:
    print("\nTC13: 빈 paragraph 제외, paragraphNo 원문 인덱스 유지")

    path = tmp_dir / "tc13.hwpx"
    make_hwpx_file(path, [
        {"text": ""},  # 빈 paragraph (제외, paragraphNo=0)
        {"text": "담당자 이메일은 test@example.com입니다."},  # paragraphNo=1
        {"text": "   "},  # 공백만 (제외, paragraphNo=2)
    ])

    def mock_regex(text: str):
        if "test@example.com" in text:
            idx = text.index("test@example.com")
            return [{
                "label": "이메일 주소", "value": "test@example.com",
                "start": idx, "end": idx + 16,
                "grade": "S", "action": "마스킹", "desc": "test",
            }]
        return []

    plan = detect_in_hwpx(str(path), regex_detect_func=mock_regex)
    _check("TC13.count", len(plan.auto_targets) == 1)
    _check("TC13.paragraphNo_preserved",
           plan.auto_targets[0].location_meta.get("paragraphNo") == 1,
           f"paragraphNo={plan.auto_targets[0].location_meta.get('paragraphNo')}")


# ── TC14: locationLabel 형식 ───────────────────────────────────

def tc14(tmp_dir: Path) -> None:
    print("\nTC14: locationLabel 형식 검증")

    path = tmp_dir / "tc14.hwpx"
    long_text = "담당자 김도윤의 이메일은 test@example.com입니다. 길게 이어지는 문장."
    make_hwpx_file(path, [
        {"text": "❍ 위 본문 paragraph (앞 context)"},
        {"text": long_text},
        {"text": "❍ 표 직전 본문"},
        {"text": "", "tables": [[["셀A", "셀B"]]]},  # 표 셀
    ])

    paragraphs = iter_hwpx_paragraphs(str(path))
    by_section: dict[str, list] = {}
    for p in paragraphs:
        by_section.setdefault(p.section, []).append(p)

    # body: "1번 본문 N번째 문단:" 형식
    body = by_section.get("body", [])
    # paragraphNo=1 (긴 텍스트) 라벨
    body_p1 = next((p for p in body if p.paragraph_no == 1), None)
    if body_p1:
        _check("TC14.body_prefix",
               body_p1.location_label.startswith("1번 본문 2번째 문단:"),
               f"label={body_p1.location_label}")
        _check("TC14.body_truncate", "..." in body_p1.location_label)

    # table_cell: "1번 본문 N번째 문단 표 N번 R행 C열:"
    table_cells = by_section.get("table_cell", [])
    if table_cells:
        tc = table_cells[0]
        _check("TC14.table_format",
               "표 1번" in tc.location_label
               and "1행 1열" in tc.location_label,
               f"label={tc.location_label}")
        # 앞 paragraph context 포함 검증
        _check("TC14.table_preceding",
               "앞 문단" in tc.location_label,
               f"label={tc.location_label}")


# ── TC15: applyMode/outputFilePath ─────────────────────────────

def tc15(tmp_dir: Path) -> None:
    print('\nTC15: applyMode="guide", outputFilePath=None')

    path = tmp_dir / "tc15.hwpx"
    make_hwpx_file(path, [{"text": "단순 paragraph."}])

    plan = DeidentifyPlan(auto_targets=[], review_targets=[])
    result = build_guide_for_hwpx(str(path), plan)
    _check("TC15.applyMode", result.applyMode == "guide")
    _check("TC15.outputFilePath", result.outputFilePath is None)
    _check("TC15.fileType", result.fileType == "hwpx")


# ── TC16: 표 셀 paragraph 탐지 ─────────────────────────────────

def tc16(tmp_dir: Path) -> None:
    print("\nTC16: 표 셀 paragraph 탐지")

    path = tmp_dir / "tc16.hwpx"
    make_hwpx_file(path, [
        {"text": "❍ 직원 명단"},  # 앞 paragraph
        {
            "text": "",  # 표만 있는 paragraph
            "tables": [[
                ["이름", "이메일"],
                ["홍길동", "hong@example.com"],
            ]],
        },
    ])

    def mock_regex(text: str):
        if "@example.com" in text:
            idx = text.index("hong@example.com")
            return [{
                "label": "이메일", "value": "hong@example.com",
                "start": idx, "end": idx + 16,
                "grade": "S", "action": "마스킹", "desc": "t",
            }]
        return []

    plan = detect_in_hwpx(str(path), regex_detect_func=mock_regex)
    _check("TC16.detected", len(plan.auto_targets) == 1)
    if plan.auto_targets:
        meta = plan.auto_targets[0].location_meta
        _check("TC16.section", meta.get("section") == "table_cell")
        _check("TC16.tableIndex", meta.get("tableIndex") == 0)
        _check("TC16.rowNo", meta.get("rowNo") == 1)
        _check("TC16.colNo", meta.get("colNo") == 1)


# ── TC17: 한 paragraph에 표 여러 개 (paragraphNo + tableIndex) ──

def tc17(tmp_dir: Path) -> None:
    print("\nTC17: 한 paragraph에 표 여러 개 → tableIndex로 구분")

    path = tmp_dir / "tc17.hwpx"
    make_hwpx_file(path, [
        {"text": "❍ 단계별 진행"},
        {
            "text": "",
            "tables": [
                [["1단계", "준비"]],
                [["2단계", "실행"]],
                [["3단계", "마무리"]],
            ],
        },
    ])

    paragraphs = iter_hwpx_paragraphs(str(path))
    table_paras = [p for p in paragraphs if p.section == "table_cell"]

    # 표 3개 × 2 셀 = 6
    _check("TC17.cell_count", len(table_paras) == 6,
           f"count={len(table_paras)}")

    # tableIndex 0, 1, 2
    indices = sorted({p.table_index for p in table_paras})
    _check("TC17.tableIndices", indices == [0, 1, 2],
           f"indices={indices}")

    # 각 표의 첫 셀 텍스트 (위치 키 충돌 없음 확인)
    first_cells = {}
    for p in table_paras:
        if p.row_no == 0 and p.col_no == 0:
            first_cells[p.table_index] = p.text

    _check("TC17.distinct_first_cells",
           first_cells == {0: "1단계", 1: "2단계", 2: "3단계"},
           f"first_cells={first_cells}")


# ── TC18: 본문/표 셀 텍스트 분리 (paragraph 자체 텍스트에 표 텍스트 안 섞임) ──

def tc18(tmp_dir: Path) -> None:
    print("\nTC18: 본문 paragraph 텍스트에 표 안 텍스트가 섞이지 않음")

    path = tmp_dir / "tc18.hwpx"
    make_hwpx_file(path, [
        {
            "text": "본문 텍스트입니다",
            "tables": [[["표 안 셀A", "표 안 셀B"]]],
        },
    ])

    paragraphs = iter_hwpx_paragraphs(str(path))
    body_paras = [p for p in paragraphs if p.section == "body"]
    table_paras = [p for p in paragraphs if p.section == "table_cell"]

    _check("TC18.body_text",
           body_paras[0].text == "본문 텍스트입니다",
           f"body_text={body_paras[0].text!r}")
    _check("TC18.body_no_cell_text",
           "셀A" not in body_paras[0].text
           and "셀B" not in body_paras[0].text)

    # 표 셀은 별도로 잡힘
    cell_texts = sorted([p.text for p in table_paras])
    _check("TC18.cell_texts",
           cell_texts == ["표 안 셀A", "표 안 셀B"],
           f"cell_texts={cell_texts}")


# ── TC19: 앞 paragraph context (preceding_text) ───────────────

def tc19(tmp_dir: Path) -> None:
    print("\nTC19: 표 셀의 preceding_text가 앞 본문 paragraph로 채워짐")

    path = tmp_dir / "tc19.hwpx"
    make_hwpx_file(path, [
        {"text": "❍ 추진단계"},   # 직전 본문
        {"text": ""},               # 빈 paragraph
        {"text": "", "tables": [[["1단계", "준비"]]]},
    ])

    paragraphs = iter_hwpx_paragraphs(str(path))
    table_paras = [p for p in paragraphs if p.section == "table_cell"]

    _check("TC19.has_table_cells", len(table_paras) >= 1)
    if table_paras:
        cell = table_paras[0]
        _check("TC19.preceding_text",
               cell.preceding_text == "❍ 추진단계",
               f"preceding_text={cell.preceding_text!r}")
        _check("TC19.label_includes_preceding",
               "앞 문단: ❍ 추진단계" in cell.location_label,
               f"label={cell.location_label}")


# ── TC20: 앞 paragraph가 없으면 preceding_text는 None ─────────

def tc20(tmp_dir: Path) -> None:
    print("\nTC20: 표가 문서 첫 paragraph일 때 preceding_text=None")

    path = tmp_dir / "tc20.hwpx"
    make_hwpx_file(path, [
        {"text": "", "tables": [[["A", "B"]]]},  # 첫 paragraph가 표
    ])

    paragraphs = iter_hwpx_paragraphs(str(path))
    table_paras = [p for p in paragraphs if p.section == "table_cell"]

    if table_paras:
        cell = table_paras[0]
        _check("TC20.preceding_none", cell.preceding_text is None)
        _check("TC20.label_no_preceding",
               "앞 문단" not in cell.location_label,
               f"label={cell.location_label}")


# ── TC21: 알 수 없는 section ───────────────────────────────────

def tc21(tmp_dir: Path) -> None:
    print("\nTC21: 알 수 없는 section → unknown_section warning")

    path = tmp_dir / "tc21.hwpx"
    make_hwpx_file(path, [{"text": "단순 paragraph."}])

    target = DeidentifyTarget(
        label="가짜", matched="x", action="마스킹",
        location_label="알 수 없는 위치",
        location_meta={
            "fileType": "hwpx",
            "sectionNo": 0,
            "section": "footnote",  # 15주차 범위 외
            "paragraphNo": 0,
        },
        start=0, end=1, source="regex", reason="test",
        grade="S", context="x",
    )
    plan = DeidentifyPlan(auto_targets=[target], review_targets=[])
    result = build_guide_for_hwpx(str(path), plan)

    _check("TC21.skipped", result.autoResults[0].status == "skipped")
    _check("TC21.warning_type",
           any("[unknown_section]" in w
               for w in result.autoResults[0].warnings),
           f"warnings={result.autoResults[0].warnings}")


# ── TC22: 다중 section ────────────────────────────────────────

def tc22(tmp_dir: Path) -> None:
    print("\nTC22: 다중 section 처리 (section0 + section1)")

    path = tmp_dir / "tc22.hwpx"
    make_multi_section_hwpx(path, [
        [{"text": "첫번째 본문 이메일: a@example.com"}],
        [{"text": "두번째 본문 이메일: b@example.com"}],
    ])

    def mock_regex(text: str):
        results = []
        for needle in ["a@example.com", "b@example.com"]:
            if needle in text:
                idx = text.index(needle)
                results.append({
                    "label": "이메일", "value": needle,
                    "start": idx, "end": idx + len(needle),
                    "grade": "S", "action": "마스킹", "desc": "t",
                })
        return results

    plan = detect_in_hwpx(str(path), regex_detect_func=mock_regex)
    _check("TC22.count", len(plan.auto_targets) == 2,
           f"count={len(plan.auto_targets)}")

    # 두 target의 sectionNo가 0, 1로 다름
    section_nos = sorted({t.location_meta.get("sectionNo")
                          for t in plan.auto_targets})
    _check("TC22.different_sections",
           section_nos == [0, 1],
           f"sections={section_nos}")

    result = build_guide_for_hwpx(str(path), plan)
    _check("TC22.guide_two_items", len(result.autoResults) == 2)
    # locationLabel에 1번 본문, 2번 본문이 표시되어야 함
    labels = sorted([it.locationLabel for it in result.autoResults])
    _check("TC22.label_sections",
           "1번 본문" in labels[0] and "2번 본문" in labels[1],
           f"labels={labels}")


# ── 실행 ──────────────────────────────────────────────────────

def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        print("=== 15주차 hwpx detector 단위 테스트 ===")
        test_fns = [
            tc1, tc2, tc3, tc4, tc5, tc6, tc7, tc8, tc9,
            tc10, tc11, tc12, tc13, tc14, tc15, tc16, tc17,
            tc18, tc19, tc20, tc21, tc22,
        ]
        run_test_functions(_runner, test_fns, tmp_dir)

    _runner.report()


if __name__ == "__main__":
    main()
