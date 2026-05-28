"""피드백 데이터 분석 스크립트.

사용법:
    python notebooks/analyze_feedback.py
    python notebooks/analyze_feedback.py --date-from 2026-05-01 --date-to 2026-05-31
    python notebooks/analyze_feedback.py --export-dataset retrain_data.jsonl

출력:
    - 전체 통계 (총 건수, 동의율, 오탐율)
    - fileType별 집계
    - AI grade별 집계
    - 불일치 케이스 목록 (aiGrade != userGrade)
    - 재학습 데이터셋 (JSONL, --export-dataset 지정 시)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# 프로젝트 루트 기준 경로 설정 (src/api/ → src/ → project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FEEDBACK_DIR = PROJECT_ROOT / "feedback_data"


# ── 데이터 로드 ────────────────────────────────────────────────

def load_feedbacks(date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """피드백 JSON 파일을 날짜 범위로 로드한다."""
    files = sorted(FEEDBACK_DIR.glob("feedback_*.json"))
    if not files:
        return []

    result = []
    for f in files:
        date_str = f.stem.replace("feedback_", "")  # "2026-05-26"
        if date_from and date_str < date_from:
            continue
        if date_to and date_str > date_to:
            continue
        try:
            items = json.loads(f.read_text(encoding="utf-8"))
            for item in items:
                item["_date"] = date_str
            result.extend(items)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  [경고] {f.name} 읽기 실패: {exc}", file=sys.stderr)

    return result


# ── 통계 계산 ──────────────────────────────────────────────────

def compute_stats(feedbacks: list[dict]) -> dict:
    """전체 통계, fileType별, aiGrade별 집계를 반환한다."""
    total = len(feedbacks)
    if total == 0:
        return {"total": 0}

    agreements = sum(1 for f in feedbacks if f.get("isAgreement"))
    false_positives = sum(1 for f in feedbacks if f.get("isFalsePositive"))
    mismatches = total - agreements  # 불일치 = 동의하지 않은 건수

    # fileType별
    by_file_type: dict[str, dict] = defaultdict(lambda: {"total": 0, "agreement": 0, "fp": 0})
    for fb in feedbacks:
        ft = fb.get("fileType") or "unknown"
        by_file_type[ft]["total"] += 1
        if fb.get("isAgreement"):
            by_file_type[ft]["agreement"] += 1
        if fb.get("isFalsePositive"):
            by_file_type[ft]["fp"] += 1

    # aiGrade별
    by_ai_grade: dict[str, dict] = defaultdict(lambda: {"total": 0, "agreement": 0, "fp": 0})
    for fb in feedbacks:
        ag = fb.get("aiGrade") or "None"
        by_ai_grade[ag]["total"] += 1
        if fb.get("isAgreement"):
            by_ai_grade[ag]["agreement"] += 1
        if fb.get("isFalsePositive"):
            by_ai_grade[ag]["fp"] += 1

    # 날짜별 건수
    by_date: dict[str, int] = defaultdict(int)
    for fb in feedbacks:
        by_date[fb.get("_date", "unknown")] += 1

    return {
        "total": total,
        "agreements": agreements,
        "false_positives": false_positives,
        "mismatches": mismatches,
        "agreement_rate": round(agreements / total, 3),
        "false_positive_rate": round(false_positives / total, 3),
        "mismatch_rate": round(mismatches / total, 3),
        "by_file_type": dict(by_file_type),
        "by_ai_grade": dict(by_ai_grade),
        "by_date": dict(sorted(by_date.items())),
    }


def get_mismatch_cases(feedbacks: list[dict]) -> list[dict]:
    """AI 등급과 사용자 등급이 다른 케이스를 반환한다."""
    return [
        fb for fb in feedbacks
        if not fb.get("isAgreement")
    ]


def build_retrain_dataset(feedbacks: list[dict]) -> list[dict]:
    """재학습용 데이터셋을 구성한다.

    - 동의한 항목: aiGrade를 정답 레이블로 사용
    - 불일치 항목: userGrade를 정답 레이블로 사용
      - isFalsePositive=True (X): 오탐이므로 레이블을 "O"로 변환

    반환 형식: {"text": str, "label": str, "source": str, "meta": dict}
    """
    dataset = []
    for fb in feedbacks:
        context = (fb.get("context") or "").strip()
        if not context:
            continue

        ai_grade = fb.get("aiGrade")
        user_grade = fb.get("userGrade")
        is_agreement = fb.get("isAgreement", False)
        is_fp = fb.get("isFalsePositive", False)

        if is_agreement:
            label = ai_grade
            source = "agreement"
        elif is_fp:
            label = "O"          # 오탐 → Other
            source = "fp_correction"
        else:
            label = user_grade   # 사용자가 등급을 수정한 경우
            source = "grade_correction"

        if label not in ("C", "S", "O"):
            continue  # 유효하지 않은 레이블 제외

        dataset.append({
            "text": context,
            "label": label,
            "source": source,
            "meta": {
                "fileType": fb.get("fileType"),
                "locationLabel": fb.get("locationLabel"),
                "aiGrade": ai_grade,
                "userGrade": user_grade,
                "date": fb.get("_date"),
            },
        })

    return dataset


# ── 출력 헬퍼 ──────────────────────────────────────────────────

def _rate(count: int, total: int) -> str:
    if total == 0:
        return "N/A"
    return f"{count / total * 100:.1f}%"


def print_report(stats: dict, mismatches: list[dict]) -> None:
    """분석 결과를 콘솔에 출력한다."""
    total = stats["total"]
    if total == 0:
        print("피드백 데이터가 없습니다.")
        return

    print("=" * 60)
    print("피드백 분석 보고서")
    print("=" * 60)

    print(f"\n[전체 통계]")
    print(f"  총 피드백 수    : {total}건")
    print(f"  동의 (AI 정답)  : {stats['agreements']}건 ({_rate(stats['agreements'], total)})")
    print(f"  오탐 (X 선택)   : {stats['false_positives']}건 ({_rate(stats['false_positives'], total)})")
    print(f"  불일치          : {stats['mismatches']}건 ({_rate(stats['mismatches'], total)})")

    print(f"\n[날짜별 건수]")
    for date, count in stats["by_date"].items():
        print(f"  {date}: {count}건")

    print(f"\n[fileType별 집계]")
    for ft, s in sorted(stats["by_file_type"].items()):
        t = s["total"]
        print(
            f"  {ft:8s}: {t:4d}건 | "
            f"동의 {_rate(s['agreement'], t)} | "
            f"오탐 {_rate(s['fp'], t)}"
        )

    print(f"\n[AI grade별 집계]")
    for grade, s in sorted(stats["by_ai_grade"].items()):
        t = s["total"]
        print(
            f"  grade={grade}: {t:4d}건 | "
            f"동의 {_rate(s['agreement'], t)} | "
            f"오탐 {_rate(s['fp'], t)}"
        )

    if mismatches:
        print(f"\n[불일치 케이스 상위 10건]")
        print(f"  {'AI':>4} {'사용자':>6}  {'fileType':8}  {'context'}")
        print(f"  {'-'*4}  {'-'*6}  {'-'*8}  {'-'*30}")
        for fb in mismatches[:10]:
            ctx = (fb.get("context") or "")[:40].replace("\n", " ")
            print(
                f"  {fb.get('aiGrade') or '?':>4}  "
                f"{fb.get('userGrade') or '?':>6}  "
                f"{fb.get('fileType') or '?':8}  "
                f"{ctx}"
            )

    print()


def export_dataset(dataset: list[dict], output_path: Path) -> None:
    """재학습 데이터셋을 JSONL 형식으로 저장한다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    label_counts: dict[str, int] = defaultdict(int)
    source_counts: dict[str, int] = defaultdict(int)
    for item in dataset:
        label_counts[item["label"]] += 1
        source_counts[item["source"]] += 1

    print(f"재학습 데이터셋 저장 완료: {output_path}")
    print(f"  총 {len(dataset)}건")
    print(f"  레이블 분포: { {k: v for k, v in sorted(label_counts.items())} }")
    print(f"  소스 분포:   { {k: v for k, v in sorted(source_counts.items())} }")


# ── 메인 ──────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="피드백 데이터 분석")
    parser.add_argument("--date-from", metavar="YYYY-MM-DD", help="시작 날짜 (포함)")
    parser.add_argument("--date-to",   metavar="YYYY-MM-DD", help="종료 날짜 (포함)")
    parser.add_argument(
        "--export-dataset",
        metavar="PATH",
        help="재학습 데이터셋 출력 경로 (JSONL). 미지정 시 내보내지 않음.",
    )
    args = parser.parse_args()

    print(f"피드백 디렉토리: {FEEDBACK_DIR}")

    feedbacks = load_feedbacks(
        date_from=args.date_from,
        date_to=args.date_to,
    )
    print(f"로드된 피드백: {len(feedbacks)}건\n")

    stats = compute_stats(feedbacks)
    mismatches = get_mismatch_cases(feedbacks)
    print_report(stats, mismatches)

    if args.export_dataset:
        dataset = build_retrain_dataset(feedbacks)
        export_dataset(dataset, Path(args.export_dataset))


if __name__ == "__main__":
    main()
