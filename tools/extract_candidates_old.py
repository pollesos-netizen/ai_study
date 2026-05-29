"""
tools/extract_candidates.py

사내 업무 민감정보 C/S/O 분류 후보 추출 스크립트
명세: notebooks/week20_worktask_taxonomy.md

사용:
    python tools/extract_candidates.py
    python tools/extract_candidates.py --manuals-dir data/manuals_md --output data/candidates.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# src/regex_detector 재사용
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
from regex_detector import detect_patterns as _base_detect_patterns

KEYWORDS_FILE = Path(__file__).resolve().parent / "keywords.yaml"

CSV_FIELDS = [
    "sourceFile", "unitId", "text", "headingPath", "precedingText",
    "candidateType", "candidateReason", "regexOnly",
    "suggestedGrade", "userGrade", "memo",
]


# ── 추가 regex 패턴 (명세 2.1 — regex_detector.py에 없는 것) ─────────────
#
# regex_detector.py의 기존 패턴:
#   - 내부 IP(10.x, 172.16-31.x, 192.168.x), 전화(0xx-xxx-xxxx), 이메일,
#     사번, 계좌, 주민번호, VLAN/포트, 주파수, 위치 등
#
# 추가 필요:
#   - 마스킹 IP: 20*.23*.9*.71 형태 (비마스킹보다 먼저 체크)
#   - 공인 IP 포함 전체 IP: 내부망 외 IP도 매뉴얼에 출현
#   - 대표번호: 1588-xxxx, 1800-xxxx
#   - 지역번호 괄호식: 032) 451-3310

_EXTRA_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("ip_masked",          "마스킹 IP",          re.compile(r"\d+\*\.\d+\*(?:\.\d+\*?)*")),
    ("ip_any",             "IP 주소",            re.compile(r"(?<!\d)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\d.])")),
    ("phone_repr",         "대표번호",           re.compile(r"(?<!\d)1[0-9]{3}[-–]\d{4}(?!\d)")),
    ("phone_area_bracket", "지역번호 괄호식 전화", re.compile(r"(?<!\d)0\d{1,2}\)\s*\d{3,4}[-–]\d{4}(?!\d)")),
]


def detect_identifiers(text: str) -> list[dict[str, str]]:
    """regex_detector 기본 패턴 + 추가 패턴으로 식별자 목록 반환."""
    results: list[dict[str, str]] = []

    for r in _base_detect_patterns(text):
        results.append({"id": r.id, "label": r.label, "value": r.value})

    seen_spans: set[tuple[int, int]] = set()
    for pat_id, label, pat in _EXTRA_PATTERNS:
        for m in pat.finditer(text):
            span = (m.start(), m.end())
            if span not in seen_spans:
                seen_spans.add(span)
                results.append({"id": pat_id, "label": label, "value": m.group()})

    return results


# ── 키워드 로드 ───────────────────────────────────────────────────────────

def load_keywords(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── 정규화 및 키워드 매칭 (명세 3.4) ─────────────────────────────────────

def _normalize(s: str) -> str:
    """공백 제거 + 소문자 + 전각→반각 변환."""
    # 전각 알파벳·숫자·기호 → 반각
    result = []
    for c in s:
        cp = ord(c)
        if 0xFF01 <= cp <= 0xFF5E:
            result.append(chr(cp - 0xFEE0))
        elif c == '　':  # 전각 공백
            result.append(' ')
        else:
            result.append(c)
    return re.sub(r'\s+', '', ''.join(result)).lower()


def match_keywords(text: str, kw_config: dict) -> tuple[list[dict], list[dict]]:
    """
    강한 키워드와 약한 키워드를 분리하여 매칭.

    Returns:
        (strong_matches, weak_matches)
        각 항목: {"kw": str, "track": "C"/"S", "group": str}
    """
    norm_text = _normalize(text)
    strong: list[dict] = []
    weak: list[dict] = []

    # C-track
    for group_id, group_data in kw_config.get("c_track", {}).items():
        for kw in group_data.get("keywords", []):
            if _normalize(kw) in norm_text:
                strong.append({"kw": kw, "track": "C", "group": group_id})

    # S-track
    for kw in kw_config.get("s_track", {}).get("keywords", []):
        if _normalize(kw) in norm_text:
            strong.append({"kw": kw, "track": "S", "group": "S"})

    # 약한 키워드
    for kw in kw_config.get("weak", {}).get("keywords", []):
        if _normalize(kw) in norm_text:
            weak.append({"kw": kw, "track": "weak", "group": "weak"})

    return strong, weak


# ── O급 자동 제외 (명세 4장) ─────────────────────────────────────────────

_O_EXCLUDE_PAT = re.compile(
    r"목차|차례|개정\s*이력|제\s*개정\s*이력|문서\s*목적|적용\s*범위|"
    r"용어\s*설명|용어의\s*정의|머리말|꼬리말"
)


def is_o_exclude(text: str, heading_path: str) -> bool:
    """
    C/S 키워드·식별자가 없는 상태에서 O급 자동 제외 대상인지 확인.
    headingPath 또는 짧은 텍스트가 O급 패턴에 해당하면 True.
    """
    target = heading_path + " " + text
    return bool(_O_EXCLUDE_PAT.search(target))


# ── TextUnit 분할 (명세 8장) ─────────────────────────────────────────────

_RE_H2 = re.compile(r'^##\s+(.+)$')
_RE_H3 = re.compile(r'^###\s+(.+)$')
_RE_BOLD_TITLE = re.compile(r'^\*\*([^*\n]+)\*\*\s*[：:]?\s*$')
_RE_PAGE = re.compile(r'<!--\s*page\s+\d+\s*-->')


def split_text_units(content: str) -> list[dict[str, str]]:
    """
    마크다운 내용을 TextUnit 목록으로 분할.

    경계: ## 헤딩, ### 헤딩, 독립 굵은 소제목(**...**), <!-- page N -->
    장애조치 항목·검사 카드는 경계 없이 한 블록에 넓게 묶임 (명세 8장).

    Returns:
        [{"text": str, "headingPath": str}, ...]
    """
    lines = content.splitlines()
    units: list[dict[str, str]] = []
    h2 = h3 = bold = ""
    buf: list[str] = []

    def flush() -> None:
        text = "\n".join(buf).strip()
        if text:
            parts = [p for p in [h2, h3, bold] if p]
            units.append({
                "text": text,
                "headingPath": " > ".join(parts),
            })
        buf.clear()

    for line in lines:
        if _RE_PAGE.search(line):
            flush()
            continue

        m = _RE_H2.match(line)
        if m:
            flush()
            h2 = m.group(1).strip()
            h3 = bold = ""
            continue

        m = _RE_H3.match(line)
        if m:
            flush()
            h3 = m.group(1).strip()
            bold = ""
            continue

        m = _RE_BOLD_TITLE.match(line)
        if m:
            flush()
            bold = m.group(1).strip()
            continue

        buf.append(line)

    flush()
    return units


# ── unitId 생성 (명세 5장: 재실행 시 동일해야 병합 가능) ─────────────────

def make_unit_id(source_file: str, heading_path: str, text: str) -> str:
    digest = hashlib.sha256(
        f"{source_file}|{heading_path}|{text}".encode("utf-8")
    ).hexdigest()[:10]
    stem = Path(source_file).stem[:20].replace(" ", "_")
    return f"{stem}_{digest}"


# ── 파일 처리 ─────────────────────────────────────────────────────────────

def process_file(
    md_path: Path,
    kw_config: dict,
) -> list[dict[str, Any]]:
    # \r 정규화 (명세 8장 주의사항)
    content = md_path.read_text(encoding="utf-8", errors="replace")
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    units = split_text_units(content)
    source_file = md_path.name
    rows: list[dict[str, Any]] = []
    prev_text = ""

    for unit in units:
        text = unit["text"]
        heading_path = unit["headingPath"]

        # 식별자 탐지
        ident_hits = detect_identifiers(text)
        has_ident = bool(ident_hits)

        # 키워드 매칭
        strong, weak = match_keywords(text, kw_config)
        has_strong = bool(strong)
        has_weak = bool(weak)

        # 후보 조건 판정
        is_kw_candidate = has_strong        # 약한 키워드 단독은 후보 아님
        is_ident_candidate = has_ident

        if not is_kw_candidate and not is_ident_candidate:
            # O급 자동 제외 여부와 관계없이 후보 아님
            prev_text = text
            continue

        # O급 자동 제외 — 키워드·식별자 없는 경우는 위에서 이미 skip됨.
        # 식별자만 있는 경우도 제외 대상이면 skip (단, 이 경우 regexOnly=true이므로
        # 명세상 제외하지 않는다 — 식별자는 무조건 포착 대상)
        if not is_kw_candidate and is_ident_candidate:
            pass  # regex_identifier 후보는 O급 제외 대상에서 열외
        elif is_kw_candidate and is_o_exclude(text, heading_path):
            # C/S 키워드 있어도 제외 패턴? 명세: "C/S 키워드 출현하면 제외하지 않는다"
            pass  # 제외 안 함

        # candidateType
        candidate_types: list[str] = []
        if is_kw_candidate:
            candidate_types.append("ai_procedural_sensitive")
        if is_ident_candidate:
            candidate_types.append("regex_identifier")

        # candidateReason: 강한 키워드 + (강한 키워드가 있으면 약한 키워드도 포함)
        reason: list[dict] = list(strong)
        if has_strong and has_weak:
            reason.extend(weak)
        for hit in ident_hits:
            reason.append({"kw": hit["value"], "label": hit["label"], "track": "regex", "group": hit["id"]})

        # regexOnly: 식별자만 있고 서술형 키워드(강함+약함 모두) 전혀 없는 경우만
        regex_only = has_ident and not has_strong and not has_weak

        rows.append({
            "sourceFile": source_file,
            "unitId": make_unit_id(source_file, heading_path, text),
            "text": text,
            "headingPath": heading_path,
            "precedingText": prev_text[:400] if prev_text else "",
            "candidateType": json.dumps(candidate_types, ensure_ascii=False),
            "candidateReason": json.dumps(reason, ensure_ascii=False),
            "regexOnly": "true" if regex_only else "false",
            "suggestedGrade": "",
            "userGrade": "",
            "memo": "",
        })

        prev_text = text

    return rows


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="민감정보 후보 추출 스크립트")
    parser.add_argument(
        "--manuals-dir",
        default=str(_PROJECT_ROOT / "data" / "manuals_md"),
        help="입력 .md 파일 디렉토리 (기본: data/manuals_md)",
    )
    parser.add_argument(
        "--output",
        default=str(_PROJECT_ROOT / "data" / "candidates.csv"),
        help="출력 CSV 경로 (기본: data/candidates.csv)",
    )
    parser.add_argument(
        "--keywords",
        default=str(KEYWORDS_FILE),
        help="키워드 YAML 경로 (기본: tools/keywords.yaml)",
    )
    args = parser.parse_args()

    manuals_dir = Path(args.manuals_dir)
    output_csv = Path(args.output)
    kw_path = Path(args.keywords)

    if not manuals_dir.exists():
        print(f"[오류] 입력 폴더 없음: {manuals_dir}", file=sys.stderr)
        sys.exit(1)

    if not kw_path.exists():
        print(f"[오류] 키워드 파일 없음: {kw_path}", file=sys.stderr)
        sys.exit(1)

    kw_config = load_keywords(kw_path)
    md_files = sorted(manuals_dir.glob("*.md"))

    if not md_files:
        print(f"[경고] {manuals_dir} 에 .md 파일이 없습니다.", file=sys.stderr)
        sys.exit(0)

    print(f"입력: {manuals_dir} ({len(md_files)}개 파일)")
    all_rows: list[dict] = []

    for md_path in md_files:
        rows = process_file(md_path, kw_config)
        print(f"  {md_path.name:40s}  {len(rows):4d}건")
        all_rows.extend(rows)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    # 통계
    ai_cnt    = sum(1 for r in all_rows if "ai_procedural_sensitive" in r["candidateType"])
    re_cnt    = sum(1 for r in all_rows if "regex_identifier"        in r["candidateType"])
    ro_cnt    = sum(1 for r in all_rows if r["regexOnly"] == "true")
    both_cnt  = sum(1 for r in all_rows if "ai_procedural_sensitive" in r["candidateType"]
                                        and "regex_identifier"       in r["candidateType"])

    print(f"\n저장: {output_csv}")
    print(f"전체 후보      : {len(all_rows):5d}건")
    print(f"  ai_procedural_sensitive : {ai_cnt:5d}건")
    print(f"  regex_identifier        : {re_cnt:5d}건")
    print(f"  두 타입 모두            : {both_cnt:5d}건  (regexOnly=false)")
    print(f"  regexOnly=true          : {ro_cnt:5d}건")


if __name__ == "__main__":
    main()
