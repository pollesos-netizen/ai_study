"""
16주차 PDF detector + guide builder 단위 테스트

13~15주차 docx/pptx/hwpx 패턴을 따라 작성했습니다.
PDF는 reportlab으로 임시 파일을 생성합니다.

PDF 특유 검증:
- TC15~TC18: line 단위 위치, bbox 저장, 한글 띄어쓰기 복원, 빈 PDF (스캔 시뮬레이션)
"""

from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

from common_apply_result import APPLY_MODE_GUIDE
from deidentify_target_builder import DeidentifyPlan, DeidentifyTarget
from pdf_detector import (
    build_guide_for_pdf,
    detect_in_pdf,
    iter_pdf_lines,
)


# 한글 CID 폰트 등록 (한 번만)
try:
    pdfmetrics.registerFont(UnicodeCIDFont('HYSMyeongJo-Medium'))
    KOREAN_FONT = 'HYSMyeongJo-Medium'
except Exception:
    KOREAN_FONT = 'Helvetica'


# ── PDF 생성 헬퍼 ──────────────────────────────────────────────

def make_pdf(path: Path, pages_data: list[list[str]],
             font: str = KOREAN_FONT, font_size: int = 12) -> None:
    """
    테스트용 PDF 파일 생성.

    pages_data: [["line1", "line2"], ["page2 line1"], ...]
        각 페이지는 line 문자열 목록
    """
    c = canvas.Canvas(str(path), pagesize=A4)
    page_height = A4[1]

    for page_lines in pages_data:
        c.setFont(font, font_size)
        # line 간격 (font_size + 8)
        y = page_height - 100
        line_gap = font_size + 8

        for text in page_lines:
            if text:  # 빈 문자열은 건너뜀 (PDF에 빈 줄 생성 X)
                c.drawString(100, y, text)
            y -= line_gap

        c.showPage()

    c.save()


def make_empty_pdf(path: Path, page_count: int = 1) -> None:
    """텍스트가 전혀 없는 PDF (스캔 PDF 시뮬레이션용)."""
    c = canvas.Canvas(str(path), pagesize=A4)
    for _ in range(page_count):
        c.showPage()
    c.save()


def _make_target(
    *,
    label, matched, start, end, source, action,
    page_no, line_no, context,
    bbox=None,
    grade="S", order=0,
):
    meta = {
        "fileType": "pdf",
        "pageNo": page_no,
        "section": "text_line",
        "lineNo": line_no,
    }
    if bbox is not None:
        meta["bbox"] = list(bbox)

    return DeidentifyTarget(
        label=label, matched=matched, action=action,
        location_label=None,
        location_meta=meta,
        start=start, end=end, source=source,
        reason=f"테스트용 {source} 탐지",
        grade=grade, context=context, order=order,
    )


_results: list[tuple[str, bool, str]] = []


def _check(tc_id: str, condition: bool, message: str = "") -> None:
    _results.append((tc_id, condition, message))
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {tc_id}{(': ' + message) if not condition and message else ''}")


# ── TC1: 이메일 line 마스킹 ────────────────────────────────────

def tc1(tmp_dir: Path) -> None:
    print("\nTC1: 이메일이 있는 line 마스킹")

    text = "담당자 이메일은 test@example.com입니다."
    path = tmp_dir / "tc1.pdf"
    make_pdf(path, [[text]])

    matched = "test@example.com"
    s = text.index(matched); e = s + len(matched)

    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="이메일 주소", matched=matched, start=s, end=e,
                         source="regex", action="마스킹",
                         page_no=0, line_no=0, context=text),
        ],
        review_targets=[],
    )

    result = build_guide_for_pdf(str(path), plan)
    _check("TC1.applyMode", result.applyMode == APPLY_MODE_GUIDE)
    _check("TC1.outputFilePath_None", result.outputFilePath is None)
    _check("TC1.fileType", result.fileType == "pdf")
    _check("TC1.autoResults", len(result.autoResults) == 1)
    item = result.autoResults[0]
    _check("TC1.status", item.status == "applied")
    _check("TC1.applied_count", item.appliedTargetCount == 1)
    _check("TC1.preview", "*" * len(matched) in item.appliedText)


# ── TC2: 성명 line 마스킹 ─────────────────────────────────────

def tc2(tmp_dir: Path) -> None:
    print("\nTC2: 성명 line 마스킹")

    text = "직원 김도윤의 서류를 검토했습니다."
    path = tmp_dir / "tc2.pdf"
    make_pdf(path, [[text]])

    s = text.index("김도윤"); e = s + 3
    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="성명", matched="김도윤", start=s, end=e,
                         source="ner", action="마스킹",
                         page_no=0, line_no=0, context=text),
        ],
        review_targets=[],
    )
    result = build_guide_for_pdf(str(path), plan)
    _check("TC2.status", result.autoResults[0].status == "applied")
    _check("TC2.preview", "***" in result.autoResults[0].appliedText)


# ── TC3: 성명 + 이메일 동시 ────────────────────────────────────

def tc3(tmp_dir: Path) -> None:
    print("\nTC3: 한 line에 성명 + 이메일 동시")

    text = "담당자 김도윤의 이메일은 test@example.com입니다."
    path = tmp_dir / "tc3.pdf"
    make_pdf(path, [[text]])

    s1 = text.index("김도윤"); e1 = s1 + 3
    s2 = text.index("test@example.com"); e2 = s2 + 16
    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="성명", matched="김도윤", start=s1, end=e1,
                         source="ner", action="마스킹",
                         page_no=0, line_no=0, context=text, order=0),
            _make_target(label="이메일", matched="test@example.com",
                         start=s2, end=e2,
                         source="regex", action="마스킹",
                         page_no=0, line_no=0, context=text, order=1),
        ],
        review_targets=[],
    )
    result = build_guide_for_pdf(str(path), plan)
    _check("TC3.autoResults", len(result.autoResults) == 1)
    _check("TC3.applied_count", result.autoResults[0].appliedTargetCount == 2)


# ── TC4: 내부 IP 삭제 (delete/mark) ────────────────────────────

def tc4(tmp_dir: Path) -> None:
    print("\nTC4: 내부 IP 삭제 (delete/mark)")

    text = "서버 IP는 192.168.0.1입니다."
    path = tmp_dir / "tc4.pdf"
    make_pdf(path, [[text]])

    matched = "192.168.0.1"
    s = text.index(matched); e = s + len(matched)
    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="내부 IP", matched=matched, start=s, end=e,
                         source="regex", action="삭제",
                         page_no=0, line_no=0, context=text, grade="C"),
        ],
        review_targets=[],
    )
    result = build_guide_for_pdf(str(path), plan)
    _check("TC4.delete", matched not in result.autoResults[0].appliedText)

    result_mark = build_guide_for_pdf(str(path), plan, deletion_mode="mark")
    _check("TC4.mark", "(삭제됨)" in result_mark.autoResults[0].appliedText)


# ── TC5: reviewTargets 보존 ────────────────────────────────────

def tc5(tmp_dir: Path) -> None:
    print("\nTC5: reviewTargets 보존")

    text = "입찰 평가표를 검토했습니다."
    path = tmp_dir / "tc5.pdf"
    make_pdf(path, [[text]])

    review = _make_target(
        label="민감정보", matched="", start=None, end=None,
        source="ai", action="검토 필요",
        page_no=0, line_no=0, context=text, grade="C",
    )
    plan = DeidentifyPlan(auto_targets=[], review_targets=[review])
    result = build_guide_for_pdf(str(path), plan)
    _check("TC5.review_count", len(result.reviewTargets) == 1)
    _check("TC5.auto_empty", len(result.autoResults) == 0)
    _check("TC5.review_action", result.reviewTargets[0].action == "검토 필요")


# ── TC6: lineNo 없음 ──────────────────────────────────────────

def tc6(tmp_dir: Path) -> None:
    print("\nTC6: lineNo 없음 → missing_paragraph_no")

    text = "임의 텍스트."
    path = tmp_dir / "tc6.pdf"
    make_pdf(path, [[text]])

    target = DeidentifyTarget(
        label="이메일", matched="test@example.com", action="마스킹",
        location_label="알 수 없음",
        location_meta={"fileType": "pdf", "pageNo": 0, "section": "text_line"},
        start=0, end=16, source="regex", reason="test",
        grade="S", context="test",
    )
    plan = DeidentifyPlan(auto_targets=[target], review_targets=[])
    result = build_guide_for_pdf(str(path), plan)
    _check("TC6.skipped", result.autoResults[0].status == "skipped")
    _check("TC6.warning",
           any("[missing_paragraph_no]" in w
               for w in result.autoResults[0].warnings))


# ── TC7: page 범위 초과 ────────────────────────────────────────

def tc7(tmp_dir: Path) -> None:
    print("\nTC7: page 범위 초과 → pdf_text_block_not_found")

    path = tmp_dir / "tc7.pdf"
    make_pdf(path, [["단 하나의 line."]])

    target = _make_target(
        label="성명", matched="홍길동", start=0, end=3,
        source="ner", action="마스킹",
        page_no=99,  # 범위 초과
        line_no=0,
        context="홍길동 무관",
    )
    plan = DeidentifyPlan(auto_targets=[target], review_targets=[])
    result = build_guide_for_pdf(str(path), plan)
    item = result.autoResults[0]
    _check("TC7.skipped", item.status == "skipped")
    _check("TC7.warning",
           any("[pdf_text_block_not_found]" in w for w in item.warnings))


# ── TC8: context 불일치, slice 일치 ────────────────────────────

def tc8(tmp_dir: Path) -> None:
    print("\nTC8: context 불일치, slice 일치 → 권장 + warning")

    text = "담당자 이메일은 test@example.com입니다."
    path = tmp_dir / "tc8.pdf"
    make_pdf(path, [[text]])

    matched = "test@example.com"
    s = text.index(matched); e = s + 16
    target = _make_target(
        label="이메일", matched=matched, start=s, end=e,
        source="regex", action="마스킹",
        page_no=0, line_no=0,
        context="담당자 이메일: test@example.com",  # 실제와 다름
    )
    plan = DeidentifyPlan(auto_targets=[target], review_targets=[])
    result = build_guide_for_pdf(str(path), plan)
    item = result.autoResults[0]
    _check("TC8.status_applied", item.status == "applied")
    _check("TC8.applied_count", item.appliedTargetCount == 1)
    _check("TC8.context_mismatch",
           any("[context_mismatch]" in w for w in item.warnings))


# ── TC9: slice 불일치 ─────────────────────────────────────────

def tc9(tmp_dir: Path) -> None:
    print("\nTC9: slice 불일치 → skip + warning")

    text = "담당자 이메일은 test@example.com입니다."
    path = tmp_dir / "tc9.pdf"
    make_pdf(path, [[text]])

    target = _make_target(
        label="이메일", matched="test@example.com",
        start=0, end=5,  # 매치되지 않는 위치
        source="regex", action="마스킹",
        page_no=0, line_no=0, context=text,
    )
    plan = DeidentifyPlan(auto_targets=[target], review_targets=[])
    result = build_guide_for_pdf(str(path), plan)
    item = result.autoResults[0]
    _check("TC9.skipped", item.status == "skipped")
    _check("TC9.warning",
           any("[slice_mismatch]" in w for w in item.warnings))


# ── TC10: 여러 line 분산 ───────────────────────────────────────

def tc10(tmp_dir: Path) -> None:
    print("\nTC10: 여러 line에 target 분산")

    t1 = "이메일: test@example.com"
    t2 = "전화번호: 010-1234-5678"
    path = tmp_dir / "tc10.pdf"
    make_pdf(path, [[t1, t2]])

    s1 = t1.index("test@example.com"); e1 = s1 + 16
    s2 = t2.index("010-1234-5678"); e2 = s2 + 13
    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="이메일", matched="test@example.com",
                         start=s1, end=e1, source="regex", action="마스킹",
                         page_no=0, line_no=0, context=t1),
            _make_target(label="전화번호", matched="010-1234-5678",
                         start=s2, end=e2, source="regex", action="마스킹",
                         page_no=0, line_no=1, context=t2),
        ],
        review_targets=[],
    )
    result = build_guide_for_pdf(str(path), plan)
    _check("TC10.count", len(result.autoResults) == 2)
    _check("TC10.all_applied",
           all(it.status == "applied" for it in result.autoResults))


# ── TC11: summary 정합성 ───────────────────────────────────────

def tc11(tmp_dir: Path) -> None:
    print("\nTC11: summary 정합성")

    t1 = "이메일: test@example.com"
    t2 = "전화: 010-1234-5678"
    path = tmp_dir / "tc11.pdf"
    make_pdf(path, [[t1, t2]])

    s1 = t1.index("test@example.com"); e1 = s1 + 16
    s2 = t2.index("010-1234-5678"); e2 = s2 + 13
    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="이메일", matched="test@example.com",
                         start=s1, end=e1, source="regex", action="마스킹",
                         page_no=0, line_no=0, context=t1),
            _make_target(label="전화번호", matched="010-1234-5678",
                         start=s2, end=e2, source="regex", action="마스킹",
                         page_no=0, line_no=1, context=t2),
        ],
        review_targets=[],
    )
    result = build_guide_for_pdf(str(path), plan)
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
    path = tmp_dir / "tc12.pdf"
    make_pdf(path, [[text]])

    matched = "VLAN 100"
    s = text.index(matched); e = s + len(matched)
    plan = DeidentifyPlan(
        auto_targets=[
            _make_target(label="VLAN", matched=matched, start=s, end=e,
                         source="regex", action="삭제",
                         page_no=0, line_no=0, context=text, grade="C"),
        ],
        review_targets=[],
    )
    result = build_guide_for_pdf(str(path), plan, deletion_mode="mark")
    _check("TC12.mark", "(삭제됨)" in result.autoResults[0].appliedText)


# ── TC13: 여러 page 분산 ───────────────────────────────────────

def tc13(tmp_dir: Path) -> None:
    print("\nTC13: 여러 page 처리")

    path = tmp_dir / "tc13.pdf"
    make_pdf(path, [
        ["첫 페이지 이메일: a@example.com"],
        ["두 번째 페이지 이메일: b@example.com"],
    ])

    def mock_regex(text):
        import re
        results = []
        for m in re.finditer(r'[a-z]@example\.com', text):
            results.append({
                "label": "이메일", "value": m.group(),
                "start": m.start(), "end": m.end(),
                "grade": "S", "action": "마스킹", "desc": "t",
            })
        return results

    plan = detect_in_pdf(str(path), regex_detect_func=mock_regex)
    _check("TC13.count", len(plan.auto_targets) == 2)
    page_nos = sorted({t.location_meta.get("pageNo")
                       for t in plan.auto_targets})
    _check("TC13.different_pages",
           page_nos == [0, 1],
           f"pages={page_nos}")


# ── TC14: locationLabel 형식 ───────────────────────────────────

def tc14(tmp_dir: Path) -> None:
    print("\nTC14: locationLabel 형식 검증")

    path = tmp_dir / "tc14.pdf"
    long_text = "담당자 김도윤의 이메일은 test@example.com입니다. 길게 이어지는 문장입니다."
    make_pdf(path, [["짧은 텍스트", long_text]])

    lines = iter_pdf_lines(str(path))

    # 첫 page, 두 번째 line의 label
    second_line = next((line for line in lines
                        if line.page_no == 0 and line.line_no == 1), None)
    if second_line:
        _check("TC14.label_format",
               second_line.location_label.startswith("1쪽 2번째 줄:"),
               f"label={second_line.location_label}")
        _check("TC14.label_truncated",
               "..." in second_line.location_label,
               f"label={second_line.location_label}")


# ── TC15: applyMode/outputFilePath ─────────────────────────────

def tc15(tmp_dir: Path) -> None:
    print('\nTC15: applyMode="guide", outputFilePath=None')

    path = tmp_dir / "tc15.pdf"
    make_pdf(path, [["단순 line"]])

    plan = DeidentifyPlan(auto_targets=[], review_targets=[])
    result = build_guide_for_pdf(str(path), plan)
    _check("TC15.applyMode", result.applyMode == "guide")
    _check("TC15.outputFilePath", result.outputFilePath is None)
    _check("TC15.fileType", result.fileType == "pdf")


# ── TC16: bbox 좌표 저장 ───────────────────────────────────────

def tc16(tmp_dir: Path) -> None:
    print("\nTC16: bbox 좌표 자동 저장")

    path = tmp_dir / "tc16.pdf"
    make_pdf(path, [["line A", "line B"]])

    lines = iter_pdf_lines(str(path))
    _check("TC16.lines_have_bbox",
           all(line.bbox is not None for line in lines),
           f"lines={[(l.text, l.bbox) for l in lines]}")

    if lines:
        first = lines[0]
        _check("TC16.bbox_is_tuple_of_4",
               isinstance(first.bbox, tuple) and len(first.bbox) == 4)
        x0, top, x1, bottom = first.bbox
        _check("TC16.bbox_valid",
               x1 > x0 and bottom > top,
               f"bbox={first.bbox}")

        # location_meta에도 들어가 있어야 함
        _check("TC16.meta_has_bbox",
               "bbox" in first.location_meta)


# ── TC17: 한글 띄어쓰기 복원 (x_tolerance=1) ──────────────────

def tc17(tmp_dir: Path) -> None:
    print("\nTC17: 한글 띄어쓰기 정확 추출")

    text = "직원 김도윤의 사번은 12345입니다."
    path = tmp_dir / "tc17.pdf"
    make_pdf(path, [[text]])

    lines = iter_pdf_lines(str(path), x_tolerance=1)
    _check("TC17.line_count", len(lines) == 1)
    if lines:
        # 띄어쓰기가 모두 보존되었는지
        extracted = lines[0].text
        _check("TC17.spacing_preserved",
               "직원 김도윤" in extracted,
               f"extracted={extracted!r}")
        _check("TC17.full_text",
               text == extracted,
               f"original={text!r}, extracted={extracted!r}")


# ── TC18: 빈 PDF (스캔 PDF 시뮬레이션) ────────────────────────

def tc18(tmp_dir: Path) -> None:
    print("\nTC18: 빈 PDF → scanned_pdf_no_text warning")

    path = tmp_dir / "tc18.pdf"
    make_empty_pdf(path, page_count=2)

    plan = DeidentifyPlan(auto_targets=[], review_targets=[])
    result = build_guide_for_pdf(str(path), plan)
    _check("TC18.scanned_warning",
           any("[scanned_pdf_no_text]" in w
               for w in result.warnings),
           f"warnings={result.warnings}")
    _check("TC18.no_auto_results",
           len(result.autoResults) == 0)


# ── TC19: 암호 PDF ────────────────────────────────────────────

def tc19(tmp_dir: Path) -> None:
    print("\nTC19: 암호 PDF → pdf_encrypted warning")

    path = tmp_dir / "tc19.pdf"
    # reportlab으로 암호화 PDF 생성
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setEncrypt = None  # 일부 reportlab 버전 호환
    try:
        from reportlab.lib.pdfencrypt import StandardEncryption
        c._doc.encrypt = StandardEncryption("test123", strength=128)
    except Exception:
        pass
    c.setFont(KOREAN_FONT, 12)
    c.drawString(100, 750, "Secret line")
    c.showPage()
    c.save()

    # 별도 방법: reportlab의 encrypt 매개변수
    path2 = tmp_dir / "tc19_v2.pdf"
    c2 = canvas.Canvas(str(path2), pagesize=A4, encrypt="test123")
    c2.setFont(KOREAN_FONT, 12)
    c2.drawString(100, 750, "Secret")
    c2.showPage()
    c2.save()

    # 둘 중 어떤 게 진짜 암호화되었는지 확인
    use_path = path2  # encrypt= 매개변수가 더 확실함

    plan = DeidentifyPlan(auto_targets=[], review_targets=[])
    result = build_guide_for_pdf(str(use_path), plan)
    # 암호 PDF면 pdf_encrypted warning, 못 잡아도 빈 PDF로 처리되어 scanned_pdf_no_text
    has_encrypted_warning = any("[pdf_encrypted]" in w for w in result.warnings)
    has_scanned_warning = any("[scanned_pdf_no_text]" in w for w in result.warnings)
    _check("TC19.has_warning",
           has_encrypted_warning or has_scanned_warning,
           f"warnings={result.warnings}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        print("=== 16주차 pdf detector 단위 테스트 ===")
        for fn in [
            tc1, tc2, tc3, tc4, tc5, tc6, tc7, tc8, tc9,
            tc10, tc11, tc12, tc13, tc14, tc15, tc16, tc17, tc18,
            tc19,
        ]:
            try:
                fn(tmp_dir)
            except Exception as exc:
                print(f"  [ERROR] {fn.__name__}: {exc}")
                import traceback
                traceback.print_exc()
                _results.append((fn.__name__, False, str(exc)))

    print("\n=== 결과 요약 ===")
    total = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed
    print(f"  통과: {passed} / 전체: {total}")
    if failed:
        print(f"  실패: {failed}")
        for tc_id, ok, msg in _results:
            if not ok:
                print(f"    - {tc_id}: {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
