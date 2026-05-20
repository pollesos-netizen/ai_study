"""
9주차 한국어 NER 어댑터 테스트 스크립트

목적:
- 실제 Hugging Face 모델을 연결하기 전에, Hugging Face NER 출력처럼 생긴
  가짜 결과를 사용해 korean_ner_adapter.py가 정상 동작하는지 확인합니다.

실행:
    python notebooks/08_test_korean_ner_adapter.py
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from korean_ner_adapter import adapt_hf_outputs, normalize_label


def print_spans(title: str, raw_outputs: list[dict]) -> None:
    print(f"\n=== {title} ===")

    spans = adapt_hf_outputs(raw_outputs)

    if not spans:
        print("EntitySpan 생성 결과 없음")
        return

    for index, span in enumerate(spans, start=1):
        print(f"\n[{index}]")
        print(f"label: {span.label}")
        print(f"text: {span.text}")
        print(f"start/end: {span.start}/{span.end}")
        print(f"source: {span.source}")
        print(f"confidence: {span.confidence}")
        print(f"original_label: {span.original_label}")


def main() -> None:
    print("=== 9주차 한국어 NER 어댑터 테스트 ===")

    print("\n라벨 정규화 테스트")
    for raw_label in ["PERSON", "PER", "PS", "B-PER", "I-PER", "B-PS", "I-PS", "인명", "ORG", "LOC"]:
        print(f"{raw_label} -> {normalize_label(raw_label)}")

    merged_outputs = [
        {
            "entity_group": "PER",
            "word": "김도윤",
            "start": 3,
            "end": 6,
            "score": 0.98,
        },
        {
            "entity_group": "PS",
            "word": "안서현",
            "start": 0,
            "end": 3,
            "score": 0.95,
        },
        {
            "entity_group": "ORG",
            "word": "인천교통공사",
            "start": 0,
            "end": 7,
            "score": 0.99,
        },
    ]

    print_spans("aggregation_strategy=simple 형태 출력 테스트", merged_outputs)

    raw_bio_like_outputs = [
        {
            "entity": "B-PS",
            "word": "조민재",
            "start": 0,
            "end": 3,
            "score": 0.91,
        },
        {
            "entity": "B-ORG",
            "word": "정보화기획팀",
            "start": 10,
            "end": 16,
            "score": 0.88,
        },
    ]

    print_spans("BIO 라벨 포함 출력 테스트", raw_bio_like_outputs)

    print("\n=== 테스트 완료 ===")


if __name__ == "__main__":
    main()
