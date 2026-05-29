"""
tools/extract_candidates.py

사내 업무 민감정보 C/S/O 분류 후보 추출 스크립트 v2

핵심 원칙:
    1. IP/VLAN/포트/계정/비밀번호/전화번호/이메일/사번 등 결정론적 식별자류는
       regex_identifier 경로로 분리하고, AI 학습 후보에서는 제외한다.
    2. AI 후보는 '서술형 업무 민감 문장'으로 좁힌다.
    3. weak 키워드는 단독/weak끼리 후보를 만들 수 없다.
    4. ambiguous_action은 operational_anchor와 함께 있을 때만 AI 후보가 된다.
    5. 목차/개정이력/표 구분선/페이지 주석 등 noise TextUnit은 제외한다.

사용:
    python tools/extract_candidates.py
    python tools/extract_candidates.py --manuals-dir data/manuals_md --output data/candidates.csv

출력:
    --output data/candidates.csv 를 지정하면 아래 3개 파일을 생성한다.
      - data/candidates.csv        전체 후보
      - data/candidates_ai.csv     AI 검수/학습 후보(ai_procedural_sensitive)
      - data/candidates_regex.csv  regex 식별자 후보(regex_identifier)
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
try:
    from regex_detector import detect_patterns as _base_detect_patterns
except Exception:  # pragma: no cover - 단독 검토 시 src가 없을 수 있음
    _base_detect_patterns = None

KEYWORDS_FILE = Path(__file__).resolve().parent / "keywords.yaml"

CSV_FIELDS = [
    "sourceFile", "unitId", "text", "headingPath", "precedingText",
    "candidateType", "candidateReason", "regexOnly",
    "suggestedGrade", "priorityScore",
    "strongKeywordCount", "ambiguousActionCount", "anchorKeywordCount",
    "weakKeywordCount", "regexIdentifierCount", "noiseFlag",
    "userGrade", "memo",
]


# ── 추가 regex 패턴 ──────────────────────────────────────────────────────
# regex_detector.py에 없는 표현을 보강한다. 식별자류는 AI 후보가 아니라
# regex_identifier 후보로만 분리한다.

_EXTRA_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("ip_masked",          "마스킹 IP",            re.compile(r"\d+\*\.\d+\*(?:\.\d+\*?)*")),
    ("ip_any",             "IP 주소",              re.compile(r"(?<!\d)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\d.])")),
    ("phone_repr",         "대표번호",             re.compile(r"(?<!\d)1[0-9]{3}[-–]\d{4}(?!\d)")),
    ("phone_area_bracket", "지역번호 괄호식 전화", re.compile(r"(?<!\d)0\d{1,2}\)\s*\d{3,4}[-–]\d{4}(?!\d)")),
    ("account_like",       "계정 후보",            re.compile(r"(?i)(?:계정|ID|아이디)\s*[:：=]\s*[A-Za-z][A-Za-z0-9_.-]{2,}")),
    ("password_like",      "비밀번호 후보",        re.compile(r"(?i)(?:비밀번호|password|passwd|pwd)\s*[:：=]\s*\S+")),
]


def detect_identifiers(text: str) -> list[dict[str, str]]:
    """regex_detector 기본 패턴 + 추가 패턴으로 식별자 목록 반환."""
    results: list[dict[str, str]] = []
    occupied_spans: set[tuple[int, int]] = set()

    if _base_detect_patterns is not None:
        for r in _base_detect_patterns(text):
            start = getattr(r, "start", None)
            end = getattr(r, "end", None)
            if isinstance(start, int) and isinstance(end, int):
                occupied_spans.add((start, end))
            results.append({
                "id": getattr(r, "id", "regex"),
                "label": getattr(r, "label", "정규식 탐지"),
                "value": getattr(r, "value", ""),
            })

    for pat_id, label, pat in _EXTRA_PATTERNS:
        for m in pat.finditer(text):
            span = (m.start(), m.end())
            # 기존 regex_detector와 같은 span이면 중복 추가하지 않음
            if span in occupied_spans:
                continue
            occupied_spans.add(span)
            results.append({"id": pat_id, "label": label, "value": m.group()})

    return results


# ── 키워드 로드 ───────────────────────────────────────────────────────────

def load_keywords(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


# ── 정규화 및 키워드 매칭 ────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """공백 제거 + 소문자 + 전각→반각 변환."""
    result = []
    for c in s:
        cp = ord(c)
        if 0xFF01 <= cp <= 0xFF5E:
            result.append(chr(cp - 0xFEE0))
        elif c == "　":
            result.append(" ")
        else:
            result.append(c)
    return re.sub(r"\s+", "", "".join(result)).lower()


def _keyword_matches(norm_text: str, keywords: list[str], *, role: str, track: str, group: str) -> list[dict]:
    matches: list[dict] = []
    seen: set[str] = set()
    # 긴 키워드 우선. 예: "수동 절체"가 먼저 잡히도록 정렬
    for kw in sorted(keywords or [], key=lambda x: len(_normalize(x)), reverse=True):
        norm_kw = _normalize(kw)
        if not norm_kw or norm_kw in seen:
            continue
        if norm_kw in norm_text:
            seen.add(norm_kw)
            matches.append({"kw": kw, "track": track, "group": group, "role": role})
    return matches


def match_keywords(text: str, kw_config: dict) -> dict[str, list[dict]]:
    """새 keywords.yaml 구조에 따라 키워드를 역할별로 분리 매칭."""
    norm_text = _normalize(text)
    tracks = kw_config.get("ai_tracks", {}) or {}

    strong_cfg = tracks.get("strong_procedural", {}) or {}
    amb_cfg = tracks.get("ambiguous_action", {}) or {}
    anchor_cfg = tracks.get("operational_anchor", {}) or {}
    s_cfg = tracks.get("s_business_sensitive", {}) or {}
    weak_cfg = kw_config.get("weak", {}) or {}

    return {
        "strong_procedural": _keyword_matches(
            norm_text, strong_cfg.get("keywords", []),
            role="strong_procedural", track="C", group="strong_procedural",
        ),
        "ambiguous_action": _keyword_matches(
            norm_text, amb_cfg.get("keywords", []),
            role="ambiguous_action", track="ambiguous", group="ambiguous_action",
        ),
        "operational_anchor": _keyword_matches(
            norm_text, anchor_cfg.get("keywords", []),
            role="operational_anchor", track="anchor", group="operational_anchor",
        ),
        "s_business_sensitive": _keyword_matches(
            norm_text, s_cfg.get("keywords", []),
            role="s_business_sensitive", track="S", group="s_business_sensitive",
        ),
        "weak": _keyword_matches(
            norm_text, weak_cfg.get("keywords", []),
            role="weak", track="weak", group="weak",
        ),
    }


# ── noise / O급 자동 제외 ───────────────────────────────────────────────

_O_EXCLUDE_PAT = re.compile(
    r"목\s*차|차\s*례|개정\s*이력|제\s*개정\s*이력|문서\s*목적|적용\s*범위|"
    r"용어\s*설명|용어의\s*정의|머리말|꼬리말|표\s*지"
)

_MD_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_PAGE_ONLY_RE = re.compile(r"^\s*<!--\s*page\s+\d+\s*-->\s*$", re.I)


def is_markdown_table_separator(line: str) -> bool:
    return bool(_MD_TABLE_SEP_RE.match(line.strip()))


def is_probable_table_header(row_text: str) -> bool:
    """마크다운 표 헤더처럼 보이는 짧은 행을 제거한다."""
    text = re.sub(r"[|\s]", "", row_text)
    if len(text) > 60:
        return False
    header_terms = ("구분", "항목", "내용", "비고", "설비명", "점검항목", "검사항목", "확인사항")
    return sum(1 for t in header_terms if t in text) >= 2


def is_noise_unit(text: str, heading_path: str = "") -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if _PAGE_ONLY_RE.fullmatch(stripped):
        return True
    if _MD_TABLE_SEP_RE.search(stripped):
        return True
    if re.search(r"개정\s*일\s*[:：]", stripped):
        return True
    if _O_EXCLUDE_PAT.search(f"{heading_path} {stripped}"):
        # 단, 본문이 충분히 길고 실제 절차 표현이 있으면 뒤의 후보 규칙에서 살릴 수 있으나
        # 목차/개정이력 계열은 후보 밀도를 크게 낮추기 위해 noise로 제외한다.
        return True
    if is_probable_table_header(stripped):
        return True
    # 제목/표지 단독 줄
    if len(stripped) <= 40 and re.fullmatch(r"[#\s\-*]*(?:[\w가-힣]+\s*){1,6}(?:매뉴얼|목록|현황|표준)[#\s\-*]*", stripped):
        return True
    return False


# ── TextUnit 분할 ───────────────────────────────────────────────────────

_RE_H2 = re.compile(r"^##\s+(.+)$")
_RE_H3 = re.compile(r"^###\s+(.+)$")
_RE_BOLD_TITLE = re.compile(r"^\*\*([^*\n]+)\*\*\s*[：:]?\s*$")
_RE_PAGE = re.compile(r"<!--\s*page\s+\d+\s*-->", re.I)


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _clean_table_row(line: str) -> str:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    cells = [c for c in cells if c]
    return " / ".join(cells)


def split_text_units(content: str) -> list[dict[str, str]]:
    """
    마크다운 내용을 TextUnit 목록으로 분할.

    - ##, ###, 독립 굵은 제목, page 주석은 경계
    - 마크다운 표는 separator/header를 제거하고 row 단위 TextUnit으로 분리
    - 일반 본문은 기존처럼 넓게 묶되, noise unit은 후단에서 제외
    """
    lines = content.splitlines()
    units: list[dict[str, str]] = []
    h2 = h3 = bold = ""
    buf: list[str] = []

    def heading_path() -> str:
        return " > ".join(p for p in (h2, h3, bold) if p)

    def add_unit(text: str) -> None:
        text = text.strip()
        if text:
            units.append({"text": text, "headingPath": heading_path()})

    def flush() -> None:
        text = "\n".join(buf).strip()
        if text:
            add_unit(text)
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

        if _is_table_row(line):
            flush()
            if is_markdown_table_separator(line):
                continue
            row_text = _clean_table_row(line)
            if row_text and not is_probable_table_header(row_text):
                add_unit(row_text)
            continue

        # 일반 본문은 한 줄을 하나의 TextUnit으로 둔다.
        # 매뉴얼 변환 결과가 줄/항목 단위로 의미를 갖는 경우가 많고,
        # 과도하게 넓은 TextUnit은 O급 설명과 C급 절차를 섞어 검수 밀도를 낮춘다.
        if not line.strip():
            flush()
            continue
        flush()
        add_unit(line)

    flush()
    return units


# ── unitId 생성 ─────────────────────────────────────────────────────────

def make_unit_id(source_file: str, heading_path: str, text: str) -> str:
    digest = hashlib.sha256(
        f"{source_file}|{heading_path}|{text}".encode("utf-8")
    ).hexdigest()[:10]
    stem = Path(source_file).stem[:20].replace(" ", "_")
    return f"{stem}_{digest}"


# ── 후보 판정 ───────────────────────────────────────────────────────────

def build_candidate_decision(matches: dict[str, list[dict]], ident_hits: list[dict]) -> dict[str, Any]:
    strong = matches["strong_procedural"]
    s_business = matches["s_business_sensitive"]
    ambiguous = matches["ambiguous_action"]
    anchors = matches["operational_anchor"]
    weak = matches["weak"]

    has_strong = bool(strong)
    has_s = bool(s_business)
    has_ambiguous_with_anchor = bool(ambiguous) and bool(anchors)
    has_ai_candidate = has_strong or has_s or has_ambiguous_with_anchor
    has_regex_candidate = bool(ident_hits)

    candidate_types: list[str] = []
    if has_ai_candidate:
        candidate_types.append("ai_procedural_sensitive")
    if has_regex_candidate:
        candidate_types.append("regex_identifier")

    # reason: AI 후보일 때만 weak를 보조 정보로 포함한다.
    reason: list[dict] = []
    reason.extend(strong)
    reason.extend(s_business)
    if has_ambiguous_with_anchor:
        reason.extend(ambiguous)
        reason.extend(anchors)
    if has_ai_candidate and weak:
        reason.extend(weak)
    for hit in ident_hits:
        reason.append({
            "kw": hit["value"],
            "label": hit["label"],
            "track": "regex",
            "group": hit["id"],
            "role": "regex_identifier",
        })

    suggested_grade = ""
    if strong or has_ambiguous_with_anchor:
        suggested_grade = "C"
    elif s_business:
        suggested_grade = "S"

    strong_count = len(strong) + len(s_business)
    ambiguous_count = len(ambiguous)
    anchor_count = len(anchors)
    weak_count = len(weak)
    regex_count = len(ident_hits)

    priority = 0
    priority += len(strong) * 3
    priority += len(s_business) * 2
    if has_ambiguous_with_anchor:
        priority += min(len(ambiguous), len(anchors)) * 2
    # regex 식별자는 AI 검수 우선순위를 높이지 않음. 별도 regex 파일에서 확인.
    if has_ai_candidate and weak_count:
        priority += min(weak_count, 3) * 0.2

    return {
        "candidate_types": candidate_types,
        "reason": reason,
        "regex_only": has_regex_candidate and not has_ai_candidate,
        "suggested_grade": suggested_grade,
        "priority_score": round(priority, 2),
        "strong_count": strong_count,
        "ambiguous_count": ambiguous_count,
        "anchor_count": anchor_count,
        "weak_count": weak_count,
        "regex_count": regex_count,
    }


# ── 파일 처리 ───────────────────────────────────────────────────────────

def process_file(md_path: Path, kw_config: dict) -> tuple[list[dict[str, Any]], dict[str, int]]:
    content = md_path.read_text(encoding="utf-8", errors="replace")
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    units = split_text_units(content)
    source_file = md_path.name
    rows: list[dict[str, Any]] = []
    prev_text = ""
    stats = {
        "units": len(units),
        "noise": 0,
        "ai": 0,
        "regex": 0,
        "regexOnly": 0,
    }

    for unit in units:
        text = unit["text"]
        heading_path = unit["headingPath"]

        if is_noise_unit(text, heading_path):
            stats["noise"] += 1
            prev_text = text
            continue

        ident_hits = detect_identifiers(text)
        matches = match_keywords(text, kw_config)
        decision = build_candidate_decision(matches, ident_hits)

        if not decision["candidate_types"]:
            prev_text = text
            continue

        if "ai_procedural_sensitive" in decision["candidate_types"]:
            stats["ai"] += 1
        if "regex_identifier" in decision["candidate_types"]:
            stats["regex"] += 1
        if decision["regex_only"]:
            stats["regexOnly"] += 1

        rows.append({
            "sourceFile": source_file,
            "unitId": make_unit_id(source_file, heading_path, text),
            "text": text,
            "headingPath": heading_path,
            "precedingText": prev_text[:400] if prev_text else "",
            "candidateType": json.dumps(decision["candidate_types"], ensure_ascii=False),
            "candidateReason": json.dumps(decision["reason"], ensure_ascii=False),
            "regexOnly": "true" if decision["regex_only"] else "false",
            "suggestedGrade": decision["suggested_grade"],
            "priorityScore": decision["priority_score"],
            "strongKeywordCount": decision["strong_count"],
            "ambiguousActionCount": decision["ambiguous_count"],
            "anchorKeywordCount": decision["anchor_count"],
            "weakKeywordCount": decision["weak_count"],
            "regexIdentifierCount": decision["regex_count"],
            "noiseFlag": "false",
            "userGrade": "",
            "memo": "",
        })

        prev_text = text

    return rows, stats


# ── CSV 저장 ────────────────────────────────────────────────────────────

def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def output_paths(output_csv: Path) -> tuple[Path, Path, Path]:
    if output_csv.stem.endswith("_all"):
        base = output_csv.with_name(output_csv.stem[:-4])
    else:
        base = output_csv.with_suffix("")
    all_path = output_csv
    ai_path = base.with_name(base.name + "_ai").with_suffix(".csv")
    regex_path = base.with_name(base.name + "_regex").with_suffix(".csv")
    return all_path, ai_path, regex_path


# ── CLI ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="민감정보 후보 추출 스크립트 v2")
    parser.add_argument(
        "--manuals-dir",
        default=str(_PROJECT_ROOT / "data" / "manuals_md"),
        help="입력 .md 파일 디렉토리 (기본: data/manuals_md)",
    )
    parser.add_argument(
        "--output",
        default=str(_PROJECT_ROOT / "data" / "candidates.csv"),
        help="전체 후보 CSV 경로 (기본: data/candidates.csv)",
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
    total_stats = {"units": 0, "noise": 0, "ai": 0, "regex": 0, "regexOnly": 0}

    for md_path in md_files:
        rows, stats = process_file(md_path, kw_config)
        for k, v in stats.items():
            total_stats[k] += v
        print(
            f"  {md_path.name:40s}  후보 {len(rows):4d}건 "
            f"(AI {stats['ai']:4d}, regex {stats['regex']:4d}, noise {stats['noise']:4d})"
        )
        all_rows.extend(rows)

    # 검수 우선순위: AI 후보를 priorityScore 내림차순으로 볼 수 있게 전체도 정렬
    all_rows.sort(key=lambda r: (float(r["priorityScore"]), int(r["strongKeywordCount"])), reverse=True)

    ai_rows = [r for r in all_rows if "ai_procedural_sensitive" in r["candidateType"]]
    regex_rows = [r for r in all_rows if "regex_identifier" in r["candidateType"]]

    all_path, ai_path, regex_path = output_paths(output_csv)
    write_csv(all_path, all_rows)
    write_csv(ai_path, ai_rows)
    write_csv(regex_path, regex_rows)

    top400 = ai_rows[:400]
    print(f"\n저장: {all_path}")
    print(f"저장: {ai_path}")
    print(f"저장: {regex_path}")
    print(f"전체 TextUnit      : {total_stats['units']:5d}건")
    print(f"noise 제외         : {total_stats['noise']:5d}건")
    print(f"전체 후보          : {len(all_rows):5d}건")
    print(f"  ai_procedural_sensitive : {len(ai_rows):5d}건")
    print(f"  regex_identifier        : {len(regex_rows):5d}건")
    print(f"  regexOnly=true          : {total_stats['regexOnly']:5d}건")
    if top400:
        min_score = top400[-1]["priorityScore"]
        print(f"AI 후보 상위 400건 기준 최소 priorityScore: {min_score}")


if __name__ == "__main__":
    main()
