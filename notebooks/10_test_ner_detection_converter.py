"""
9주차 NER Detection 변환 테스트 스크립트

목적:
- EntitySpan(PERSON)을 Detection dict로 변환하는 흐름을 테스트합니다.
- confidence threshold=0.8 정책을 확인합니다.

실행:
    python notebooks/10_test_ner_detection_converter.py
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from korean_ner_adapter import adapt_hf_outputs
from ner_detection_converter import (
    NER_CONFIDENCE_THRESHOLD,
    entity_spans_to_detections,
)


def print_detection(detection: dict) -> None:
    print(f"  - 탐지 항목: {detection['label']}")
    print(f"  - 탐지 값: {detection['matched']}")
    print(f"  - 등급: {detection['grade']}")
    print(f"  - 조치: {detection['action']}")
    print(f"  - 탐지 방식: {detection['source']}")
    print(f"  - 위치: {detection['locationLabel']}")
    print(f"  - start/end: {detection['start']}/{detection['end']}")
    print(f"  - 판단 근거: {detection['reason']}")


def run_case(
    title: str,
    context: str,
    raw_outputs: list[dict],
    location_label: str,
    location_meta: dict,
) -> None:
    print(f"\n=== {title} ===")
    print(f"문장: {context}")

    spans = adapt_hf_outputs(raw_outputs)
    print(f"EntitySpan 수: {len(spans)}")

    for span in spans:
        print(
            f"  EntitySpan(label={span.label}, text={span.text}, "
            f"start={span.start}, end={span.end}, "
            f"confidence={span.confidence}, original_label={span.original_label})"
        )

    detections = entity_spans_to_detections(
        spans=spans,
        context=context,
        location_label=location_label,
        location_meta=location_meta,
    )

    print(f"Detection 수: {len(detections)}")

    if not detections:
        print("Detection 생성 없음")
        return

    for detection in detections:
        print_detection(detection)


def main() -> None:
    print("=== 9주차 NER Detection 변환 테스트 ===")
    print(f"NER confidence threshold: {NER_CONFIDENCE_THRESHOLD}")

    run_case(
        title="고신뢰도 성명 탐지",
        context="직원 김도윤의 감봉 처분 결과를 확인했습니다.",
        raw_outputs=[
            {
                "entity_group": "PS",
                "word": "김도윤",
                "start": 3,
                "end": 6,
                "score": 0.9812,
            }
        ],
        location_label="17번째 문단",
        location_meta={"fileType": "docx", "paragraphNo": 17},
    )

    run_case(
        title="threshold 통과 경계 사례",
        context="홍가람 민원인의 휴대전화 번호를 확인했습니다.",
        raw_outputs=[
            {
                "entity_group": "PS",
                "word": "홍가람",
                "start": 0,
                "end": 3,
                "score": 0.8124,
            },
            {
                "entity_group": "TM",
                "word": "휴대전화",
                "start": 9,
                "end": 13,
                "score": 0.8562,
            },
        ],
        location_label="민원대장 탭 A4 셀",
        location_meta={
            "fileType": "xlsx",
            "sheetName": "민원대장",
            "cellRef": "A4",
            "row": 4,
            "col": 1,
        },
    )

    run_case(
        title="threshold 미만 성명 후보",
        context="민원인 이가온의 연락 요청이 있었습니다.",
        raw_outputs=[
            {
                "entity_group": "PS",
                "word": "이가온",
                "start": 4,
                "end": 7,
                "score": 0.7321,
            }
        ],
        location_label="5번째 문단",
        location_meta={"fileType": "docx", "paragraphNo": 5},
    )

    run_case(
        title="비지원 라벨 무시",
        context="인천교통공사 정보화기획팀에서 검토했습니다.",
        raw_outputs=[
            {
                "entity_group": "OG",
                "word": "인천교통공사",
                "start": 0,
                "end": 6,
                "score": 0.9661,
            }
        ],
        location_label="2번째 문단",
        location_meta={"fileType": "docx", "paragraphNo": 2},
    )

    print("\n=== 테스트 완료 ===")


if __name__ == "__main__":
    main()
