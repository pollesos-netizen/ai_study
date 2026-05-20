"""
10주차 비식별화 대상 계획 수립 테스트 스크립트

실행:
    python notebooks/11_test_deidentify_target_builder.py
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from deidentify_target_builder import build_deidentify_plan


def make_detection(
    label: str,
    matched: str,
    source: str,
    start,
    end,
    *,
    grade: str = "S",
    action: str = "마스킹",
    context: str = "담당자 이메일은 test@example.com입니다.",
    location_label: str = "1번째 문단",
    reason: str = "테스트 탐지",
):
    return {
        "label": label,
        "matched": matched,
        "grade": grade,
        "action": action,
        "source": source,
        "context": context,
        "locationLabel": location_label,
        "locationMeta": {"fileType": "docx", "paragraphNo": 1},
        "start": start,
        "end": end,
        "sensitiveType": "개인정보",
        "sensitiveCategory": label,
        "reason": reason,
    }


def make_ai_detection(
    *,
    context: str = "입찰 제안 평가표를 검토했습니다.",
    location_label: str = "2번째 문단",
):
    return {
        "label": "민감정보",
        "matched": "",
        "grade": "S",
        "action": "검토 필요",
        "source": "ai",
        "context": context,
        "locationLabel": location_label,
        "locationMeta": {"fileType": "docx", "paragraphNo": 2},
        "start": None,
        "end": None,
        "sensitiveType": "업무상 민감정보",
        "sensitiveCategory": "입찰정보",
        "reason": "AI 문장분류 결과",
    }


def print_plan(title: str, detections: list[dict]) -> None:
    print(f"\n=== {title} ===")
    plan = build_deidentify_plan(detections)

    print(f"summary_grade: {plan.summary_grade}")
    print(f"auto_targets: {len(plan.auto_targets)}")
    for target in plan.auto_targets:
        print(
            f"  - [{target.source}] {target.label} / {target.matched} "
            f"({target.start},{target.end}) / action={target.action} / reason={target.reason}"
        )

    print(f"review_targets: {len(plan.review_targets)}")
    for target in plan.review_targets:
        print(
            f"  - [{target.source}] {target.label} / {target.matched or '문장 전체'} "
            f"({target.start},{target.end}) / action={target.action} / reason={target.reason}"
        )


def main() -> None:
    print("=== 10주차 비식별화 대상 계획 수립 테스트 ===")

    print_plan(
        "TC1 regex만 있는 TextUnit",
        [
            make_detection("이메일 주소", "test@example.com", "regex", 9, 25),
        ],
    )

    print_plan(
        "TC2 ner만 있는 TextUnit",
        [
            make_detection(
                "성명",
                "김도윤",
                "ner",
                3,
                6,
                context="직원 김도윤의 감봉 처분 결과를 확인했습니다.",
                reason="NER 모델이 PERSON 개체로 탐지",
            ),
        ],
    )

    print_plan(
        "TC3 ai만 있는 TextUnit",
        [
            make_ai_detection(),
        ],
    )

    print_plan(
        "TC4 regex + ner 같은 위치",
        [
            make_detection("성명 후보", "김도윤", "ner", 3, 6, reason="NER 탐지"),
            make_detection("이름 패턴", "김도윤", "regex", 3, 6, reason="정규식 탐지"),
        ],
    )

    print_plan(
        "TC5 regex + ai 같은 TextUnit",
        [
            make_detection("이메일 주소", "test@example.com", "regex", 9, 25),
            make_ai_detection(context="담당자 이메일은 test@example.com입니다.", location_label="1번째 문단"),
        ],
    )

    print_plan(
        "TC6 ner + ai 같은 TextUnit",
        [
            make_detection(
                "성명",
                "김도윤",
                "ner",
                3,
                6,
                context="직원 김도윤의 감봉 처분 결과를 확인했습니다.",
                reason="NER 모델이 PERSON 개체로 탐지",
            ),
            make_ai_detection(
                context="직원 김도윤의 감봉 처분 결과를 확인했습니다.",
                location_label="1번째 문단",
            ),
        ],
    )

    print_plan(
        "TC7 빈 Detection 목록",
        [],
    )

    print_plan(
        "TC8 같은 TextUnit에 regex 2개",
        [
            make_detection(
                "이메일 주소",
                "test@example.com",
                "regex",
                9,
                25,
                context="담당자 이메일은 test@example.com이고 서버 IP는 192.168.0.1입니다.",
            ),
            make_detection(
                "내부 IP 주소",
                "192.168.0.1",
                "regex",
                35,
                46,
                grade="C",
                action="삭제",
                context="담당자 이메일은 test@example.com이고 서버 IP는 192.168.0.1입니다.",
            ),
        ],
    )

    print_plan(
        "TC9 부분 겹침 regex 이메일 + ner PERSON 일부 오탐",
        [
            make_detection("성명 후보", "test", "ner", 9, 13, reason="NER 오탐"),
            make_detection("이메일 주소", "test@example.com", "regex", 9, 25, reason="정규식 이메일 탐지"),
        ],
    )

    print("\n=== 테스트 완료 ===")


if __name__ == "__main__":
    main()
