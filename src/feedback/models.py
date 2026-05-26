"""피드백 데이터 모델.

AI review_target에 대한 사용자 판단을 구조화하는 dataclass.
저장소 구현과 독립적으로 데이터 형식만 정의한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# 사용자가 선택할 수 있는 등급
GradeChoice = Literal["C", "S", "O", "X"]
# X = "잘못된 탐지 (오탐)"


@dataclass
class UserFeedback:
    """AI review_target에 대한 사용자 피드백.

    PHP 프론트엔드에서 사용자가 C/S/O/X를 선택하면
    POST /api/feedback로 전송되는 데이터.
    """

    # 필수 필드
    location_label: str        # 탐지 위치 (예: "3쪽 5번째 줄")
    context: str               # 탐지된 문장 원문
    ai_grade: str | None       # AI가 추정한 등급 ("C"/"S"/"O"/None)
    user_grade: GradeChoice    # 사용자가 선택한 등급

    # 선택 필드
    file_type: str | None = None          # 파일 형식 (pdf/docx/pptx/hwpx/xlsx)
    sensitive_category: str | None = None # AI 탐지 카테고리 (예: "AI_S")
    reason: str | None = None             # AI reason 문자열 (디버그용)
    user_id: str | None = None            # 사용자 식별자 (부서 협의 후 결정)
    timestamp: float = field(
        default_factory=lambda: __import__("time").time()
    )

    def is_agreement(self) -> bool:
        """사용자가 AI 추정 등급에 동의했는지 여부."""
        return self.user_grade == self.ai_grade

    def is_false_positive(self) -> bool:
        """사용자가 오탐(X)으로 표시했는지 여부."""
        return self.user_grade == "X"

    def to_dict(self) -> dict:
        return {
            "locationLabel": self.location_label,
            "context": self.context,
            "aiGrade": self.ai_grade,
            "userGrade": self.user_grade,
            "fileType": self.file_type,
            "sensitiveCategory": self.sensitive_category,
            "reason": self.reason,
            "userId": self.user_id,
            "timestamp": self.timestamp,
            "isAgreement": self.is_agreement(),
            "isFalsePositive": self.is_false_positive(),
        }


@dataclass
class FeedbackRequest:
    """POST /api/feedback 요청 데이터.

    PHP에서 JSON으로 전송하는 형식.
    """

    location_label: str
    context: str
    ai_grade: str | None
    user_grade: GradeChoice
    file_type: str | None = None
    sensitive_category: str | None = None
    reason: str | None = None
    user_id: str | None = None

    def to_feedback(self) -> UserFeedback:
        return UserFeedback(
            location_label=self.location_label,
            context=self.context,
            ai_grade=self.ai_grade,
            user_grade=self.user_grade,
            file_type=self.file_type,
            sensitive_category=self.sensitive_category,
            reason=self.reason,
            user_id=self.user_id,
        )
