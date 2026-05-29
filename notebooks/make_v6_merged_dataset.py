"""
notebooks/make_v6_merged_dataset.py

privacy_sentence_sample_v5.csv + trainset.csv → privacy_sentence_sample_v6_merged.csv

v5 행은 grading_rubric.md 기준으로 cso_grade를 newGrade로 재매핑한다.
trainset 행의 userGrade는 대문자 변환만 한다.
최종 학습 라벨은 label 컬럼(C/S/O).
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
V5_CSV    = PROJECT_ROOT / "data" / "privacy_sentence_sample_v5.csv"
TRAIN_CSV = PROJECT_ROOT / "data" / "trainset.csv"
OUT_CSV   = PROJECT_ROOT / "data" / "privacy_sentence_sample_v6_merged.csv"

OUT_FIELDS = [
    "text", "label", "augmented", "source", "sourceFile",
    "originalGrade", "hasPersonal", "hasSensitiveLegal", "hasSensitiveBusiness",
    "sensitiveCategory", "remapReason", "memo",
]

# ── 재매핑 규칙 ───────────────────────────────────────────────────────────

# O로 유지하는 카테고리 (등급 기준 설명 문장 포함)
_O_CATS = {"일반업무", "분류설명"}

# 법령상 민감정보 → C 유지 (has_sensitive_legal=Y와 대부분 일치하나 명시적으로도 처리)
_LEGAL_SENSITIVE_CATS = {"건강정보", "복지정보"}

# C → S 강제 재분류 카테고리
# 공격 악용도가 낮고 "내부 업무 정보" 성격이 강한 카테고리
_S_RECLASSIFY_CATS = {
    "계약정보",
    "예산/원가정보",
    "계획/전략정보",
    "감사/법무정보",
    "입찰평가",
    "입찰정보",
    "인사정보",
    "인사/조직정보",
    "운영/유지보수정보",   # 단순 점검·결과 → S
    "장애/사고대응",       # 보고성 문장 → S
    "운용데이터",          # 내부 운영 데이터 → S
    "단속/민원정보",
    "민원처리정보",
    "보안운영정보",        # 운영 관리 정보 → S
}

# 보안정보 + 아래 키워드 포함 시 C 유지
_SECURITY_KWS = [
    "내부망", "서버 IP", "서버IP", "방화벽 정책", "방화벽",
    "취약점", "접근 권한", "접근권한", "계정", "비밀번호",
    "인증", "침해 탐지", "침해탐지",
]


def remap_v5_grade(row: dict) -> tuple[str, str]:
    """
    v5 행의 cso_grade를 재매핑한다.

    Returns:
        (newGrade, remapReason)  newGrade ∈ {"C", "S", "O"}
    """
    cat   = row["sensitive_category"].strip()
    orig  = row["cso_grade"].strip().upper()
    text  = row["text"]
    legal = row["has_sensitive_legal"] == "Y"
    personal = row["has_personal"] == "Y"
    biz   = row["has_sensitive_business"] == "Y"

    # ── O: 카테고리 우선 ──────────────────────────────────────────────────
    if cat in _O_CATS:
        return "O", f"O유지: 카테고리={cat}"

    # ── O: 모든 민감 플래그 N ─────────────────────────────────────────────
    if not legal and not personal and not biz:
        return "O", "O자동: 민감 플래그 모두 N"

    # ── C: has_sensitive_legal=Y ──────────────────────────────────────────
    if legal:
        return "C", f"C유지: has_sensitive_legal=Y (cat={cat})"

    # ── C: 법령상 민감정보 카테고리 (건강정보, 복지정보) ──────────────────
    if cat in _LEGAL_SENSITIVE_CATS:
        return "C", f"C유지: 법령상 민감정보 (cat={cat})"

    # ── 보안정보: 공격 악용 키워드 유무로 C/S 분기 ───────────────────────
    if cat == "보안정보":
        matched = [kw for kw in _SECURITY_KWS if kw in text]
        if matched:
            return "C", f"C유지: 보안정보+키워드({', '.join(matched[:3])})"
        return "S", "S재분류: 보안정보(공격악용키워드없음)"

    # ── S 강제 재분류 카테고리 ────────────────────────────────────────────
    if cat in _S_RECLASSIFY_CATS:
        changed = f"(기존={orig})" if orig != "S" else ""
        return "S", f"S재분류: {cat}{changed}"

    # ── 기본: 원본 등급 유지 ──────────────────────────────────────────────
    return orig, f"원본유지: (cat={cat})"


# ── 데이터 로드 ───────────────────────────────────────────────────────────

def load_v5() -> list[dict]:
    with V5_CSV.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_trainset() -> list[dict]:
    with TRAIN_CSV.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ── 변환 ─────────────────────────────────────────────────────────────────

def build_v5_rows(v5_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """v5 행을 out 컬럼으로 변환. (출력행 목록, 재분류된 행 목록) 반환."""
    out: list[dict] = []
    remapped: list[dict] = []

    for r in v5_rows:
        orig = r["cso_grade"].strip().upper()
        new_grade, reason = remap_v5_grade(r)
        out.append({
            "text":               r["text"],
            "label":              new_grade,
            "augmented":          "0",
            "source":             "privacy_v5",
            "sourceFile":         "privacy_sentence_sample_v5.csv",
            "originalGrade":      orig,
            "hasPersonal":        r["has_personal"],
            "hasSensitiveLegal":  r["has_sensitive_legal"],
            "hasSensitiveBusiness": r["has_sensitive_business"],
            "sensitiveCategory":  r["sensitive_category"],
            "remapReason":        reason,
            "memo":               r.get("note", ""),
        })
        if new_grade != orig:
            remapped.append({
                "orig": orig, "new": new_grade,
                "cat": r["sensitive_category"], "reason": reason,
                "text": r["text"],
            })

    return out, remapped


def build_trainset_rows(train_rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in train_rows:
        grade = r.get("userGrade", "").strip().upper()
        if grade not in {"C", "S", "O"}:
            continue  # 오탐(X) 등 제외
        out.append({
            "text":               r["text"],
            "label":              grade,
            "augmented":          r.get("augmented", "0"),
            "source":             "trainset",
            "sourceFile":         r.get("sourceFile", ""),
            "originalGrade":      grade,
            "hasPersonal":        "",
            "hasSensitiveLegal":  "",
            "hasSensitiveBusiness": "",
            "sensitiveCategory":  "",
            "remapReason":        "trainset_label",
            "memo":               r.get("memo", ""),
        })
    return out


# ── assert 검증 ───────────────────────────────────────────────────────────

def verify_asserts(all_rows: list[dict]) -> None:
    label_map = {r["text"]: r["label"] for r in all_rows}

    cases = [
        ("납품 단가 협의 결과를 공유드립니다",                           "S"),
        ("내년도 예산편성안이 첨부되었습니다",                          "S"),
        ("내부 감사 보고서 초안을 공유드립니다",                        "S"),
        ("우울증 치료 이력이 기록되어 있습니다",                        "C"),
        ("당뇨 진단을 받아 식이요법 중인 것으로 확인됩니다",            "C"),
        ("내부망 구성도 및 서버 IP 목록을 첨부합니다",                  "C"),
        ("회의는 오후 3시에 진행됩니다",                                "O"),
        ("C등급은 외부 공개 시 기관에 중대한 피해를 줄 수 있는 기밀 정보입니다", "O"),
    ]

    print("\n-- assert --")
    all_ok = True
    for text, expected in cases:
        actual = label_map.get(text)
        ok = actual == expected
        mark = "OK" if ok else "FAIL"
        print(f"  [{mark}] {expected} | actual={actual} | {text[:55]}")
        if not ok:
            all_ok = False

    if all_ok:
        print("  모든 assert 통과")
    else:
        raise AssertionError("일부 assert 실패 — 위 FAIL 항목을 확인하세요.")


# ── 통계 출력 ─────────────────────────────────────────────────────────────

def print_stats(
    v5_rows: list[dict],
    out_v5: list[dict],
    train_out: list[dict],
    remapped: list[dict],
    merged: list[dict],
) -> None:
    v5_orig = Counter(r["cso_grade"].strip().upper() for r in v5_rows)
    v5_new  = Counter(r["label"] for r in out_v5)
    train_dist = Counter(r["label"] for r in train_out)
    merged_dist = Counter(r["label"] for r in merged)
    c_to_s = sum(1 for r in remapped if r["orig"] == "C" and r["new"] == "S")

    print("\n" + "="*58)
    print("1. trainset 라벨 분포")
    for g in "CSO":
        print(f"   {g}: {train_dist[g]:4d}건")

    print("\n2. privacy_v5 기존 cso_grade 분포")
    for g in "CSO":
        print(f"   {g}: {v5_orig[g]:4d}건")

    print("\n3. privacy_v5 newGrade 분포 (재매핑 후)")
    for g in "CSO":
        print(f"   {g}: {v5_new[g]:4d}건")

    print(f"\n4. C→S 재분류 건수: {c_to_s}건")

    print("\n5. 전체 merged label 분포")
    total = sum(merged_dist.values())
    for g in "CSO":
        print(f"   {g}: {merged_dist[g]:4d}건  ({merged_dist[g]/total*100:.1f}%)")
    print(f"   합계: {total}건")

    print("\n6. 재분류된 행 샘플 20건 (originalGrade ≠ label)")
    for i, r in enumerate(remapped[:20], 1):
        print(f"  {i:2d}. {r['orig']}→{r['new']}  [{r['cat']}]  {r['text'][:55]}")
    if len(remapped) > 20:
        print(f"  ... 외 {len(remapped)-20}건")
    print("="*58)


# ── 메인 ─────────────────────────────────────────────────────────────────

def main() -> None:
    v5_rows   = load_v5()
    train_rows = load_trainset()

    out_v5, remapped = build_v5_rows(v5_rows)
    train_out        = build_trainset_rows(train_rows)

    merged = out_v5 + train_out

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        writer.writeheader()
        writer.writerows(merged)

    print(f"저장: {OUT_CSV}  ({len(merged)}건)")

    print_stats(v5_rows, out_v5, train_out, remapped, merged)
    verify_asserts(merged)


if __name__ == "__main__":
    main()
