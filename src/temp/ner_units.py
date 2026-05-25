"""
9주차 NER 공통 자료구조

EntitySpan은 NER 모델 또는 규칙 기반 탐지기가 찾은 개체 구간을
우리 프로그램에서 공통으로 다루기 위한 표준 중간 구조입니다.

EntitySpan은 최종 보안 판단 결과가 아닙니다.

EntitySpan:
- 모델/규칙이 무엇을 어디에서 찾았는가

Detection:
- 이것을 개인정보/민감정보로 보고 어떤 등급과 조치를 적용할 것인가
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EntitySpan:
    """
    NER 탐지 결과의 표준 중간 구조입니다.

    9주차에서는 label='PERSON'만 지원합니다.
    """

    label: str
    text: str
    start: int
    end: int
    source: str
    confidence: float | None = None
    original_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        EntitySpan을 dict로 변환합니다.
        """
        return {
            "label": self.label,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "source": self.source,
            "confidence": self.confidence,
            "original_label": self.original_label,
        }
