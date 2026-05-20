"""
11주차 텍스트 단위 비식별화 Apply 테스트 스크립트

실행:
    python notebooks/12_test_deidentify_apply_text.py
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from deidentify_apply import apply_plan_to_contexts, apply_targets_to_text
from deidentify_target_builder import DeidentifyPlan, DeidentifyTarget


def make_target(
    label: str,
    matched: str,
    start,
    end,
    *,
    action: str = "마스킹",
    source: str = "regex",
    grade: str = "S",
    context: str = "",
    location_label: str = "1번째 문단",
    location_meta: dict | None = None,
) -> DeidentifyTarget:
    return DeidentifyTarget(
        label=label,
        matched=matched,
        action=action,
        location_label=location_label,
        location_meta=location_meta or {"fileType": "txt", "paragraphNo": 1},
        start=start,
        end=end,
        source=source,
        reason="테스트 target",
        grade=grade,
        sensitive_type="개인정보",
        sensitive_category=label,
        context=context,
        order=0,
    )


def print_result(title: str, text: str, targets: list[DeidentifyTarget], *, deletion_mode: str = "delete") -> None:
    print(f"\n=== {title} ===")
    print(f"deletion_mode: {deletion_mode}")
    print(f"원문: {text}")

    result = apply_targets_to_text(text, targets, deletion_mode=deletion_mode)

    print(f"적용 결과: {result.applied_text}")
    print(f"applied_targets: {len(result.applied_targets)}")
    for target in result.applied_targets:
        print(
            f"  - {target.label} / {target.matched} "
            f"({target.start},{target.end}) / action={target.action}"
        )

    print(f"skipped_targets: {len(result.skipped_targets)}")
    for skipped in result.skipped_targets:
        target = skipped.target
        print(
            f"  - {target.label} / {target.matched} "
            f"({target.start},{target.end}) / reason={skipped.reason}"
        )

    print(f"warnings: {len(result.warnings)}")
    for warning in result.warnings:
        print(f"  - {warning}")


def print_plan_result(title: str, plan: DeidentifyPlan, *, deletion_mode: str = "delete") -> None:
    print(f"\n=== {title} ===")
    print(f"deletion_mode: {deletion_mode}")

    result = apply_plan_to_contexts(plan, deletion_mode=deletion_mode)

    print(f"text_results: {len(result.text_results)}")
    for index, text_result in enumerate(result.text_results, start=1):
        print(f"  [{index}] location_key: {text_result.location_key}")
        print(f"      original: {text_result.original_text}")
        print(f"      applied : {text_result.applied_text}")
        print(f"      applied_targets: {len(text_result.applied_targets)}")
        print(f"      skipped_targets: {len(text_result.skipped_targets)}")
        print(f"      warnings: {len(text_result.warnings)}")

    print(f"review_targets: {len(result.review_targets)}")
    for target in result.review_targets:
        print(f"  - review: {target.label} / {target.matched or '문장 전체'} / action={target.action}")

    print(f"plan warnings: {len(result.warnings)}")
    for warning in result.warnings:
        print(f"  - {warning}")


def main() -> None:
    print("=== 11주차 텍스트 단위 비식별화 Apply 테스트 ===")

    text1 = "직원 김도윤의 감봉 처분 결과를 확인했습니다."
    print_result(
        "TC1 성명 1개 마스킹",
        text1,
        [
            make_target("성명", "김도윤", 3, 6, source="ner", context=text1),
        ],
    )

    text2 = "담당자 이메일은 test@example.com입니다."
    print_result(
        "TC2 이메일 1개 마스킹",
        text2,
        [
            make_target("이메일 주소", "test@example.com", 9, 25, context=text2),
        ],
    )

    text3 = "담당자 김도윤의 이메일은 test@example.com입니다."
    print_result(
        "TC3 성명 + 이메일 동시 마스킹",
        text3,
        [
            make_target("성명", "김도윤", 4, 7, source="ner", context=text3),
            make_target("이메일 주소", "test@example.com", 14, 30, context=text3),
        ],
    )

    text4 = "서버 IP는 192.168.0.1입니다."
    print_result(
        "TC4-A 내부 IP 실제 삭제",
        text4,
        [
            make_target(
                "내부 IP 주소",
                "192.168.0.1",
                7,
                18,
                action="삭제",
                grade="C",
                context=text4,
            ),
        ],
        deletion_mode="delete",
    )

    print_result(
        "TC4-B 내부 IP preview 표시 삭제",
        text4,
        [
            make_target(
                "내부 IP 주소",
                "192.168.0.1",
                7,
                18,
                action="삭제",
                grade="C",
                context=text4,
            ),
        ],
        deletion_mode="mark",
    )

    text5 = "입찰 제안 평가표를 검토했습니다."
    print_result(
        "TC5 검토 필요 action 자동 적용 제외",
        text5,
        [
            make_target(
                "민감정보",
                "",
                None,
                None,
                action="검토 필요",
                source="ai",
                context=text5,
            ),
        ],
    )

    text6 = "담당자 이메일은 test@example.com입니다."
    print_result(
        "TC6 matched와 실제 slice 불일치",
        text6,
        [
            make_target("이메일 주소", "test@example.com", 9, 24, context=text6),
        ],
    )

    text7 = "직원 김도윤의 서류를 검토했습니다."
    print_result(
        "TC7-1 start < 0",
        text7,
        [
            make_target("성명", "김도윤", -1, 6, source="ner", context=text7),
        ],
    )

    print_result(
        "TC7-2 end > len(text)",
        text7,
        [
            make_target("성명", "김도윤", 3, 100, source="ner", context=text7),
        ],
    )

    print_result(
        "TC7-3 start >= end",
        text7,
        [
            make_target("성명", "김도윤", 6, 3, source="ner", context=text7),
        ],
    )

    print_result(
        "TC7-4 start/end None",
        text7,
        [
            make_target("성명", "김도윤", None, None, source="ner", context=text7),
        ],
    )

    text8 = "직원 김도윤의 감봉 처분 결과를 확인했습니다."
    print_result(
        "TC8 auto + review 공존 시 auto만 적용",
        text8,
        [
            make_target("성명", "김도윤", 3, 6, source="ner", context=text8),
            make_target(
                "민감정보",
                "",
                None,
                None,
                action="검토 필요",
                source="ai",
                context=text8,
            ),
        ],
    )

    text9 = "담당자 김도윤의 이메일은 test@example.com입니다."
    auto_targets = [
        make_target("성명", "김도윤", 4, 7, source="ner", context=text9),
        make_target("이메일 주소", "test@example.com", 14, 30, context=text9),
    ]
    review_targets = [
        make_target(
            "민감정보",
            "",
            None,
            None,
            action="검토 필요",
            source="ai",
            context=text9,
        )
    ]
    print_plan_result(
        "TC9 DeidentifyPlan 전체를 location/context 기준으로 적용",
        DeidentifyPlan(
            auto_targets=auto_targets,
            review_targets=review_targets,
            summary_grade="S",
        ),
    )

    print("\n=== 테스트 완료 ===")


if __name__ == "__main__":
    main()
