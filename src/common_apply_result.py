"""
파일 형식 공통 Apply 결과 구조

목적:
- xlsx, docx, pptx, hwpx 등 파일 형식별 Apply 결과를 프론트엔드가 동일한 구조로 받을 수 있게 합니다.

applyMode:
- "applied": 시스템이 실제 파일을 수정해 결과 파일을 생성한 경우 (예: xlsx)
- "guide":   시스템은 탐지/위치/조치 안내만 제공하고 사용자가 직접 수정하는 경우 (예: docx, pptx, hwpx)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


APPLY_MODE_APPLIED = "applied"
APPLY_MODE_GUIDE = "guide"


@dataclass
class CommonApplyItem:
    """
    파일 형식 공통 Apply 결과의 단위 항목.

    중요:
    - applyMode="applied" 모드에서는 appliedText가 실제 적용 결과를 의미합니다.
    - applyMode="guide" 모드에서는 appliedText가 실제 적용 결과가 아니라
      권장 preview 문자열을 의미합니다.
    - guide 모드에서 appliedTargetCount는 "권장 가능 target 수",
      skippedTargetCount는 "권장 불가 target 수"로 해석합니다.

    프론트엔드 표시 규칙:
    - applied 모드: "적용 결과", "적용된 항목"
    - guide 모드:   "권장 결과", "권장 항목", "권장 불가"
    """

    locationLabel: str | None
    locationMeta: dict[str, Any]
    label: str
    action: str
    originalText: str
    appliedText: str
    status: str
    appliedTargetCount: int
    skippedTargetCount: int
    warnings: list[str] = field(default_factory=list)
    # 등급/탐지 소스 (PHP 팀 UI 구성용 — 등급별 배지, 필터링, 집계에 활용)
    grade: str | None = None    # "C" | "S" | "O" | None
    source: str | None = None   # "regex" | "ner" | "ai" | "mixed" | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "locationLabel": self.locationLabel,
            "locationMeta": self.locationMeta,
            "label": self.label,
            "action": self.action,
            "originalText": self.originalText,
            "appliedText": self.appliedText,
            "status": self.status,
            "appliedTargetCount": self.appliedTargetCount,
            "skippedTargetCount": self.skippedTargetCount,
            "warnings": self.warnings,
            "grade": self.grade,
            "source": self.source,
        }


@dataclass
class CommonReviewItem:
    locationLabel: str | None
    locationMeta: dict[str, Any]
    label: str
    action: str
    context: str
    reason: str | None = None
    # AI 탐지 결과의 구조적 필드 (reason 문자열 파싱 없이 직접 사용 가능)
    # PHP 팀이 C/S/O 선택 UI를 만들 때 활용, 피드백 학습 시 grade 활용
    grade: str | None = None              # "C" | "S" | "O" | None
    sensitiveType: str | None = None      # 민감정보 유형 (예: "개인정보", "문맥 기반 민감정보")
    sensitiveCategory: str | None = None  # 카테고리 (예: "성명", "AI_S")
    source: str | None = None             # "regex" | "ner" | "ai"

    def to_dict(self) -> dict[str, Any]:
        return {
            "locationLabel": self.locationLabel,
            "locationMeta": self.locationMeta,
            "label": self.label,
            "action": self.action,
            "context": self.context,
            "reason": self.reason,
            "grade": self.grade,
            "sensitiveType": self.sensitiveType,
            "sensitiveCategory": self.sensitiveCategory,
            "source": self.source,
        }


@dataclass
class CommonApplySummary:
    totalLocations: int = 0
    appliedLocations: int = 0
    partialLocations: int = 0
    skippedLocations: int = 0
    totalWarnings: int = 0
    autoTargetCount: int = 0
    reviewTargetCount: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "totalLocations": self.totalLocations,
            "appliedLocations": self.appliedLocations,
            "partialLocations": self.partialLocations,
            "skippedLocations": self.skippedLocations,
            "totalWarnings": self.totalWarnings,
            "autoTargetCount": self.autoTargetCount,
            "reviewTargetCount": self.reviewTargetCount,
        }


@dataclass
class CommonApplyResult:
    """
    파일 형식 공통 Apply 결과.

    applyMode:
    - "applied": outputFilePath에 실제 비식별화된 파일이 저장됨
    - "guide":   outputFilePath는 None. 사용자가 원본 파일을 직접 수정해야 함
    """

    fileType: str
    inputFilePath: str
    outputFilePath: str | None
    autoResults: list[CommonApplyItem]
    reviewTargets: list[CommonReviewItem]
    warnings: list[str]
    summary: CommonApplySummary
    applyMode: str = APPLY_MODE_APPLIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "fileType": self.fileType,
            "applyMode": self.applyMode,
            "inputFilePath": self.inputFilePath,
            "outputFilePath": self.outputFilePath,
            "autoResults": [item.to_dict() for item in self.autoResults],
            "reviewTargets": [item.to_dict() for item in self.reviewTargets],
            "warnings": self.warnings,
            "summary": self.summary.to_dict(),
        }


def make_review_items(review_targets: list[Any]) -> list[CommonReviewItem]:
    """
    DeidentifyTarget 목록을 CommonReviewItem 목록으로 변환합니다.

    Any를 받는 이유:
    - 이 모듈은 공통 결과 구조 전용이므로 특정 target 모듈 의존성을 낮춥니다.
    """
    items: list[CommonReviewItem] = []

    for target in review_targets:
        items.append(
            CommonReviewItem(
                locationLabel=getattr(target, "location_label", None),
                locationMeta=getattr(target, "location_meta", {}) or {},
                label=getattr(target, "label", "") or "",
                action=getattr(target, "action", "") or "",
                context=getattr(target, "context", "") or "",
                reason=getattr(target, "reason", None),
                grade=getattr(target, "grade", None),
                sensitiveType=getattr(target, "sensitive_type", None),
                sensitiveCategory=getattr(target, "sensitive_category", None),
                source=getattr(target, "source", None),
            )
        )

    return items


def grade_for_targets(targets: list[Any]) -> str | None:
    """targets 목록에서 대표 등급을 결정한다.

    C > S > O 우선순위로 가장 높은 등급을 반환한다.
    등급이 없으면 None.
    """
    priority = {"C": 0, "S": 1, "O": 2}
    grades = [
        getattr(t, "grade", None)
        for t in targets
        if getattr(t, "grade", None) in priority
    ]
    if not grades:
        return None
    return min(grades, key=lambda g: priority[g])


def source_for_targets(targets: list[Any]) -> str | None:
    """targets 목록에서 대표 탐지 소스를 결정한다.

    단일 소스면 그 소스를, 여러 소스면 'mixed'를 반환한다.
    """
    sources = {
        getattr(t, "source", None)
        for t in targets
        if getattr(t, "source", None)
    }
    if not sources:
        return None
    if len(sources) == 1:
        return next(iter(sources))
    return "mixed"


def build_summary(
    auto_results: list[CommonApplyItem],
    review_targets: list[CommonReviewItem],
    global_warnings: list[str],
) -> CommonApplySummary:
    """
    CommonApplyItem 목록을 기준으로 요약 정보를 계산합니다.
    """
    applied = sum(1 for item in auto_results if item.status == "applied")
    partial = sum(1 for item in auto_results if item.status == "partial")
    skipped = sum(1 for item in auto_results if item.status == "skipped")

    item_warning_count = sum(len(item.warnings) for item in auto_results)

    return CommonApplySummary(
        totalLocations=len(auto_results),
        appliedLocations=applied,
        partialLocations=partial,
        skippedLocations=skipped,
        totalWarnings=item_warning_count + len(global_warnings),
        autoTargetCount=sum(
            item.appliedTargetCount + item.skippedTargetCount
            for item in auto_results
        ),
        reviewTargetCount=len(review_targets),
    )
