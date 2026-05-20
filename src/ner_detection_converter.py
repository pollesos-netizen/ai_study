"""
NER EntitySpan → Detection 변환기

목적:
- korean_ner_adapter.py에서 생성된 EntitySpan을 최종 탐지 결과 형태의 Detection dict로 변환합니다.
- 9주차에서는 PERSON EntitySpan만 성명 Detection으로 변환합니다.

정책:
- NER_CONFIDENCE_THRESHOLD = 0.8
- confidence가 None이면 통과합니다.
- confidence가 0.8 미만이면 Detection을 생성하지 않습니다.
- Detection 병합(regex > ner > ai)은 이 파일에서 수행하지 않습니다.
"""

from __future__ import annotations

from typing import Any

try:
    from src.ner_units import EntitySpan
except ModuleNotFoundError:
    from ner_units import EntitySpan


NER_CONFIDENCE_THRESHOLD = 0.8


def should_convert_span(
    span: EntitySpan,
    threshold: float = NER_CONFIDENCE_THRESHOLD,
) -> bool:
    """
    EntitySpan을 Detection으로 변환할지 판단합니다.

    9주차 정책:
    - PERSON만 변환합니다.
    - confidence가 None이면 통과합니다.
    - confidence가 threshold 이상이면 통과합니다.
    - confidence가 threshold 미만이면 보류합니다.
    """
    if span.label != "PERSON":
        return False

    if span.confidence is None:
        return True

    return span.confidence >= threshold


def entity_span_to_detection(
    span: EntitySpan,
    context: str,
    location_label: str | None = None,
    location_meta: dict[str, Any] | None = None,
    threshold: float = NER_CONFIDENCE_THRESHOLD,
) -> dict[str, Any] | None:
    """
    PERSON EntitySpan을 성명 Detection dict로 변환합니다.

    Args:
        span:
            NER 어댑터가 생성한 EntitySpan
        context:
            원문 문장
        location_label:
            사용자에게 보여줄 위치 라벨
        location_meta:
            문서 파서가 보관하는 위치 메타데이터
        threshold:
            NER confidence 임계값

    Returns:
        Detection dict 또는 None
    """
    if not should_convert_span(span, threshold=threshold):
        return None

    confidence_text = (
        "없음"
        if span.confidence is None
        else f"{span.confidence:.4f}"
    )

    return {
        "label": "성명",
        "matched": span.text,
        "grade": "S",
        "action": "마스킹",
        "source": "ner",
        "context": context,
        "locationLabel": location_label,
        "locationMeta": location_meta or {},
        "start": span.start,
        "end": span.end,
        "sensitiveType": "개인정보",
        "sensitiveCategory": "성명",
        "reason": (
            "NER 모델이 PERSON 개체로 탐지"
            f" / original_label={span.original_label}"
            f" / confidence={confidence_text}"
            f" / threshold={threshold:.2f}"
        ),
    }


def entity_spans_to_detections(
    spans: list[EntitySpan],
    context: str,
    location_label: str | None = None,
    location_meta: dict[str, Any] | None = None,
    threshold: float = NER_CONFIDENCE_THRESHOLD,
) -> list[dict[str, Any]]:
    """
    EntitySpan 목록을 Detection dict 목록으로 변환합니다.
    """
    detections: list[dict[str, Any]] = []

    for span in spans:
        detection = entity_span_to_detection(
            span=span,
            context=context,
            location_label=location_label,
            location_meta=location_meta,
            threshold=threshold,
        )

        if detection is not None:
            detections.append(detection)

    return detections
