"""
7주차 다중 속성 라벨 데이터셋 점검 스크립트

대상 파일:
- data/privacy_sentence_sample_v4.csv

목적:
- 멀티라벨 컬럼 값이 라벨링 가이드 기준과 일치하는지 점검합니다.
- 특히 다음 두 기준을 반영합니다.

1. is_direct_sensitive_text
   - 문장 자체가 C/S/O 등급 판단상 보호 대상 정보를 직접 포함하는지 여부입니다.
   - 값 보호 대상뿐 아니라 내용 보호 대상도 Y입니다.
   - Y이면 deidentify_method는 '해당 없음'이면 안 됩니다.
   - N이면 문장 자체 조치가 없으므로 deidentify_method는 '해당 없음'이어야 합니다.

2. sensitive_category
   - 문장의 주된 정보 유형입니다.
   - has_personal=Y이더라도 법령상 민감정보나 업무상 민감정보가 함께 있으면
     sensitive_category는 더 큰 범주의 카테고리를 따를 수 있습니다.
"""

import csv
from collections import Counter
from pathlib import Path


DATA_PATH = Path("data/privacy_sentence_sample_v4.csv")

REQUIRED_COLUMNS = [
    "id",
    "text",
    "has_personal",
    "has_sensitive_legal",
    "has_sensitive_business",
    "sensitive_category",
    "cso_grade",
    "deidentify_method",
    "is_direct_sensitive_text",
    "is_document_sensitive_signal",
    "indicated_sensitive_category",
    "note",
]

YN_COLUMNS = [
    "has_personal",
    "has_sensitive_legal",
    "has_sensitive_business",
    "is_direct_sensitive_text",
    "is_document_sensitive_signal",
]

PERSONAL_CATEGORIES = {
    "성명",
    "연락처",
    "이메일",
    "사번",
    "성명/연락처",
}

ALLOWED_GRADES = {"C", "S", "O"}


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def add_issue(issues: list[dict[str, str]], row: dict[str, str], rule: str, message: str) -> None:
    issues.append(
        {
            "id": row.get("id", ""),
            "rule": rule,
            "message": message,
            "text": row.get("text", ""),
        }
    )


def validate_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    if not rows:
        issues.append({"id": "", "rule": "FILE", "message": "데이터가 비어 있습니다.", "text": ""})
        return issues

    columns = set(rows[0].keys())
    for col in REQUIRED_COLUMNS:
        if col not in columns:
            issues.append({"id": "", "rule": "COLUMN", "message": f"필수 컬럼 누락: {col}", "text": ""})

    for row in rows:
        # R1. Y/N 컬럼 값 점검
        for col in YN_COLUMNS:
            if row[col] not in {"Y", "N"}:
                add_issue(issues, row, "R1", f"{col} 값은 Y 또는 N이어야 합니다: {row[col]}")

        # R2. C/S/O 등급 값 점검
        if row["cso_grade"] not in ALLOWED_GRADES:
            add_issue(issues, row, "R2", f"cso_grade 값은 C/S/O 중 하나여야 합니다: {row['cso_grade']}")

        # R3. 직접 보호 대상이면 조치 방식이 있어야 함
        if row["is_direct_sensitive_text"] == "Y" and row["deidentify_method"] == "해당 없음":
            add_issue(
                issues,
                row,
                "R3",
                "is_direct_sensitive_text=Y이면 deidentify_method는 '해당 없음'이면 안 됩니다.",
            )

        # R4. 직접 보호 대상이 아니면 문장 자체 조치 방식은 해당 없음
        if row["is_direct_sensitive_text"] == "N" and row["deidentify_method"] != "해당 없음":
            add_issue(
                issues,
                row,
                "R4",
                "is_direct_sensitive_text=N이면 deidentify_method는 '해당 없음'이어야 합니다.",
            )

        # R5. 문서/첨부 신호이면 indicated_sensitive_category가 있어야 함
        if row["is_document_sensitive_signal"] == "Y" and row["indicated_sensitive_category"] == "해당 없음":
            add_issue(
                issues,
                row,
                "R5",
                "is_document_sensitive_signal=Y이면 indicated_sensitive_category가 구체적으로 부여되어야 합니다.",
            )

        # R6. 문서/첨부 신호가 아니면 indicated_sensitive_category는 해당 없음
        if row["is_document_sensitive_signal"] == "N" and row["indicated_sensitive_category"] != "해당 없음":
            add_issue(
                issues,
                row,
                "R6",
                "is_document_sensitive_signal=N이면 indicated_sensitive_category는 '해당 없음'이어야 합니다.",
            )

        has_any_sensitive_flag = (
            row["has_personal"] == "Y"
            or row["has_sensitive_legal"] == "Y"
            or row["has_sensitive_business"] == "Y"
        )

        # R7. 플래그가 하나라도 Y이면 문장 등급은 O가 아니어야 함
        if has_any_sensitive_flag and row["cso_grade"] == "O":
            add_issue(
                issues,
                row,
                "R7",
                "has_* 플래그 중 하나라도 Y이면 cso_grade는 O이면 안 됩니다.",
            )

        # R8. cso_grade=O이면 직접 보호 대상은 아니어야 함
        if row["cso_grade"] == "O" and row["is_direct_sensitive_text"] == "Y":
            add_issue(
                issues,
                row,
                "R8",
                "cso_grade=O이면 is_direct_sensitive_text는 N이어야 합니다.",
            )

        # R9. 개인정보만 있는 문장은 개인정보 계열 카테고리여야 함
        only_personal = (
            row["has_personal"] == "Y"
            and row["has_sensitive_legal"] == "N"
            and row["has_sensitive_business"] == "N"
        )
        if only_personal and row["sensitive_category"] not in PERSONAL_CATEGORIES:
            add_issue(
                issues,
                row,
                "R9",
                "has_personal=Y 단독 문장은 sensitive_category가 개인정보 계열이어야 합니다.",
            )

        # R10. 개인정보 + 다른 민감정보가 함께 있는 경우는 category 우선순위에 따라 비개인정보 카테고리 허용
        # 이 경우는 오류가 아니므로 별도 issue를 만들지 않습니다.

    return issues


def print_summary(rows: list[dict[str, str]], issues: list[dict[str, str]]) -> None:
    print("=== 7주차 멀티라벨 데이터셋 점검 ===")
    print(f"전체 문장 수: {len(rows)}")
    print()

    for col in [
        "has_personal",
        "has_sensitive_legal",
        "has_sensitive_business",
        "is_direct_sensitive_text",
        "is_document_sensitive_signal",
        "cso_grade",
    ]:
        print(f"{col}: {dict(Counter(row[col] for row in rows))}")

    print()
    print("sensitive_category 상위 분포:")
    for category, count in Counter(row["sensitive_category"] for row in rows).most_common(20):
        print(f"- {category}: {count}")

    print()
    print(f"검증 이슈 수: {len(issues)}")

    if issues:
        print("\n검증 이슈 목록:")
        for issue in issues:
            print(f"- [{issue['rule']}] id={issue['id']} {issue['message']}")
            print(f"  문장: {issue['text']}")


def main() -> None:
    rows = load_rows(DATA_PATH)
    issues = validate_rows(rows)
    print_summary(rows, issues)


if __name__ == "__main__":
    main()
