"""
한국어 NER 어댑터

목적:
- Hugging Face 한국어 NER 모델 등의 원본 출력을 우리 프로그램의 EntitySpan 구조로 변환합니다.
- 9주차에서는 성명 후보 탐지를 위해 PERSON 계열 라벨만 지원합니다.

중요 가정:
- Hugging Face pipeline 사용 시 aggregation_strategy="simple" 이상을 사용해
  BIO 토큰이 이미 병합된 결과를 입력으로 받는 것을 기본 가정으로 합니다.
- 예: {"entity_group": "PS", "word": "김도윤", "start": 3, "end": 6, "score": 0.98}
- 다만 raw 모델 출력을 직접 처리할 가능성에 대비해 B-/I- 접두사 제거와 라벨 매핑은 유지합니다.

정책:
- 지원 라벨은 PERSON 하나입니다.
- ORG, LOC, DEPARTMENT 등은 9주차에서는 EntitySpan으로 만들지 않고 무시합니다.
- confidence는 어댑터에서 자르지 않고 보존합니다.
- confidence threshold는 Detection 변환 단계에서 적용합니다.
"""

from __future__ import annotations

from typing import Any

try:
    from src.ner_units import EntitySpan
except ModuleNotFoundError:
    from ner_units import EntitySpan


SUPPORTED_LABELS = {"PERSON"}

PERSON_LABEL_ALIASES = {
    "PERSON",
    "PER",
    "PS",
    "인명",
}


def strip_bio_prefix(label: str) -> str:
    """
    B-PER, I-PS 같은 BIO 접두사를 제거합니다.
    """
    label = label.strip()

    if label.startswith("B-") or label.startswith("I-"):
        return label[2:]

    return label


def normalize_label(raw_label: str | None) -> str | None:
    """
    모델 원본 라벨을 내부 표준 라벨로 변환합니다.

    PERSON 계열 라벨만 PERSON으로 변환합니다.
    그 외 라벨은 None을 반환합니다.
    """
    if raw_label is None:
        return None

    cleaned = strip_bio_prefix(str(raw_label))

    if cleaned in PERSON_LABEL_ALIASES:
        return "PERSON"

    return None


def get_raw_label(raw: dict[str, Any]) -> str | None:
    """
    Hugging Face NER 출력에서 원본 라벨을 추출합니다.

    aggregation_strategy="simple"을 사용하면 보통 entity_group이 존재합니다.
    raw 출력에는 entity가 존재할 수 있습니다.
    """
    label = raw.get("entity_group")

    if label is None:
        label = raw.get("entity")

    return str(label) if label is not None else None


def get_raw_text(raw: dict[str, Any]) -> str:
    """
    Hugging Face NER 출력에서 탐지 문자열을 추출합니다.
    """
    text = raw.get("word")

    if text is None:
        text = raw.get("text")

    if text is None:
        return ""

    return str(text).strip()


def adapt_hf_output(
    raw: dict[str, Any],
    source: str = "hf_ner",
) -> EntitySpan | None:
    """
    Hugging Face NER 출력 1개를 EntitySpan으로 변환합니다.

    지원하지 않는 라벨은 None을 반환합니다.
    """
    original_label = get_raw_label(raw)
    normalized_label = normalize_label(original_label)

    if normalized_label not in SUPPORTED_LABELS:
        return None

    text = get_raw_text(raw)

    if not text:
        return None

    start = raw.get("start")
    end = raw.get("end")

    if start is None or end is None:
        return None

    score = raw.get("score")

    confidence = float(score) if score is not None else None

    return EntitySpan(
        label=normalized_label,
        text=text,
        start=int(start),
        end=int(end),
        source=source,
        confidence=confidence,
        original_label=original_label,
    )


def adapt_hf_outputs(
    raw_outputs: list[dict[str, Any]],
    source: str = "hf_ner",
) -> list[EntitySpan]:
    """
    Hugging Face NER 출력 목록을 EntitySpan 목록으로 변환합니다.

    PERSON 계열이 아닌 라벨은 무시합니다.
    """
    spans: list[EntitySpan] = []

    for raw in raw_outputs:
        span = adapt_hf_output(raw, source=source)

        if span is not None:
            spans.append(span)

    return spans


def spans_to_dicts(spans: list[EntitySpan]) -> list[dict[str, Any]]:
    """
    EntitySpan 목록을 dict 목록으로 변환합니다.
    """
    return [span.to_dict() for span in spans]
