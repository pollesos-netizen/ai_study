"""피드백 저장소 인터페이스.

17주차: no-op 구현.
enabled=False이면 save()가 아무것도 하지 않는다.

향후 활성화 시 enabled=True로 변경하고
_save_impl()에 실제 저장 로직을 구현한다.

저장 방식 옵션 (부서 협의 후 결정):
  A. SQLite  — 단일 파일, 별도 DB 서버 불필요, 소규모 적합
  B. PostgreSQL — 대용량, 멀티 워커, 통계 쿼리 용이
  C. JSON 파일  — 단순, 재학습 스크립트 연계 쉬움
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from feedback.models import UserFeedback


class FeedbackStore:
    """피드백 저장소.

    enabled=False(기본): save() 호출 시 no-op.
    enabled=True:        _save_impl() 구현 필요.
    """

    # 부서 협의 완료 전까지 False 유지
    enabled: bool = False

    def save(self, feedback: "UserFeedback") -> bool:
        """피드백을 저장한다.

        Returns:
            저장 성공 여부 (enabled=False이면 항상 False)
        """
        if not self.enabled:
            return False

        try:
            self._save_impl(feedback)
            return True
        except Exception as exc:
            print(
                f"[FeedbackStore] 저장 실패: {exc}",
                file=sys.stderr,
            )
            return False

    def _save_impl(self, feedback: "UserFeedback") -> None:
        """실제 저장 로직. 활성화 시 구현.

        구현 예시 (SQLite):
            import sqlite3, json
            conn = sqlite3.connect("feedback.db")
            conn.execute(
                "INSERT INTO feedback VALUES (?, ?, ?, ?, ?, ?)",
                (feedback.location_label, feedback.context,
                 feedback.ai_grade, feedback.user_grade,
                 feedback.user_id, feedback.timestamp)
            )
            conn.commit()
            conn.close()
        """
        raise NotImplementedError(
            "FeedbackStore._save_impl()이 구현되지 않았습니다. "
            "저장 방식을 결정한 후 구현하거나 enabled=False로 유지하세요."
        )

    def stats(self) -> dict:
        """저장된 피드백 통계. 활성화 시 구현."""
        return {
            "enabled": self.enabled,
            "total": 0,
            "agreements": 0,
            "false_positives": 0,
            "note": "피드백 저장소가 비활성 상태입니다.",
        }


# 싱글턴 인스턴스 (API 계층에서 공유)
_store = FeedbackStore()


def get_store() -> FeedbackStore:
    """전역 FeedbackStore 인스턴스를 반환한다."""
    return _store
