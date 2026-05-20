"""
9주차 Hugging Face 한국어 NER 모델 검토 스크립트

목적:
- 실제 Hugging Face 한국어 NER 모델을 로드합니다.
- 샘플 문장에 대해 NER 결과를 확인합니다.
- korean_ner_adapter.py를 사용해 모델별 원본 라벨을 EntitySpan으로 변환합니다.
- 9주차 기준으로 PERSON 계열만 우리 프로그램의 성명 후보로 사용합니다.

사용 모델:
- 기본값: Leo97/KoELECTRA-small-v3-modu-ner

선택 이유:
- KoELECTRA 계열 한국어 NER 모델입니다.
- PER, ORG, LOC 등 NER 라벨을 사용합니다.
- 우리 어댑터는 PER을 내부 표준 PERSON으로 변환합니다.

사전 설치:
    pip install transformers torch

실행:
    python notebooks/09_review_huggingface_korean_ner.py
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from transformers import pipeline


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from korean_ner_adapter import adapt_hf_outputs


# MODEL_NAME = "Leo97/KoELECTRA-small-v3-modu-ner"
MODEL_NAME = str(PROJECT_ROOT / "models" / "hf" / "KoELECTRA-small-v3-modu-ner")

# Hugging Face pipeline에서 토큰을 개체 단위로 병합하도록 설정합니다.
# 이 설정을 사용하면 B-PER/I-PER 같은 토큰 단위 결과가 PER entity_group으로 합쳐져 반환됩니다.
AGGREGATION_STRATEGY = "simple"


SAMPLES = [
    "직원 김도윤의 감봉 처분 결과를 확인했습니다.",
    "안서현 담당자에게 해당 서류를 전달했습니다.",
    "조민재 씨의 제출 서류를 검토했습니다.",
    "홍가람 민원인의 휴대전화 번호를 확인했습니다.",
    "인천교통공사 정보화기획팀에서 검토했습니다.",
    "담당자 이메일은 test@example.com입니다.",
    "서버 IP는 192.168.0.1이고 VLAN 100을 사용합니다.",
    "외부 공개용 보도자료 문구를 검토했습니다.",
]


def load_ner_pipeline(model_name: str = MODEL_NAME):
    """
    Hugging Face NER pipeline을 로드합니다.

    최초 실행 시 모델 다운로드가 발생할 수 있습니다.
    """
    print("=== Hugging Face 한국어 NER 모델 로드 ===")
    print(f"모델명: {model_name}")
    print(f"aggregation_strategy: {AGGREGATION_STRATEGY}")

    return pipeline(
        task="ner",
        model=model_name,
        tokenizer=model_name,
        aggregation_strategy=AGGREGATION_STRATEGY,
    )


def print_raw_outputs(raw_outputs: list[dict[str, Any]]) -> None:
    """
    Hugging Face 원본 출력을 출력합니다.
    """
    print("\n[Hugging Face 원본 출력]")

    if not raw_outputs:
        print("탐지 결과 없음")
        return

    for index, item in enumerate(raw_outputs, start=1):
        entity_group = item.get("entity_group", item.get("entity"))
        word = item.get("word")
        start = item.get("start")
        end = item.get("end")
        score = item.get("score")

        print(
            f"{index}. label={entity_group}, word={word}, "
            f"start={start}, end={end}, score={score:.4f}"
        )


def print_entity_spans(raw_outputs: list[dict[str, Any]]) -> None:
    """
    korean_ner_adapter.py를 사용해 EntitySpan으로 변환한 결과를 출력합니다.
    """
    spans = adapt_hf_outputs(raw_outputs, source="hf_ner")

    print("\n[EntitySpan 변환 결과]")

    if not spans:
        print("PERSON EntitySpan 없음")
        return

    for index, span in enumerate(spans, start=1):
        print(f"{index}. label={span.label}, text={span.text}, "
              f"start={span.start}, end={span.end}, "
              f"confidence={span.confidence}, original_label={span.original_label}")


def review_samples(ner_pipeline) -> None:
    """
    샘플 문장에 대해 NER 결과와 EntitySpan 변환 결과를 확인합니다.
    """
    print("\n=== 샘플 문장 NER 검토 ===")

    for index, text in enumerate(SAMPLES, start=1):
        print("\n" + "=" * 80)
        print(f"[{index}] 문장: {text}")

        raw_outputs = ner_pipeline(text)

        print_raw_outputs(raw_outputs)
        print_entity_spans(raw_outputs)


def main() -> None:
    ner_pipeline = load_ner_pipeline()
    review_samples(ner_pipeline)

    print("\n=== 검토 완료 ===")
    print("9주차 기준으로는 EntitySpan 변환 결과 중 PERSON만 성명 후보로 사용합니다.")
    print("ORG/LOC 등은 현재 단계에서 Detection으로 만들지 않습니다.")


if __name__ == "__main__":
    main()
