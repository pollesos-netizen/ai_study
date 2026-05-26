"""피드백 저장소 — JSON 날짜별 파일 방식.

저장 위치: 프로젝트 루트/feedback_data/feedback_YYYY-MM-DD.json
형식: JSON 배열, 항목 추가 방식 (append)

동시 요청 처리:
  - 파일 단위 lock (threading.Lock) 으로 같은 날짜 파일 충돌 방지
  - 사내 소규모 사용 기준으로 단순 lock으로 충분

환경 변수:
  FEEDBACK_DIR: 저장 디렉토리 경로 (기본: 프로젝트 루트/feedback_data)
"""

from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from feedback.models import UserFeedback


# 파일별 lock (날짜별 파일 동시 접근 방지)
_file_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_file_lock(filepath: str) -> threading.Lock:
    """파일별 lock을 반환한다. 없으면 새로 생성."""
    with _locks_lock:
        if filepath not in _file_locks:
            _file_locks[filepath] = threading.Lock()
        return _file_locks[filepath]


def _get_feedback_dir() -> Path:
    """피드백 저장 디렉토리.

    환경 변수 FEEDBACK_DIR 설정 시 해당 경로 사용.
    미설정 시 프로젝트 루트/feedback_data.
    """
    override = os.environ.get("FEEDBACK_DIR", "").strip()
    if override:
        p = Path(override)
    else:
        # src/feedback/store.py → 프로젝트 루트
        p = Path(__file__).resolve().parent.parent.parent / "feedback_data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _get_today_file() -> Path:
    """오늘 날짜의 피드백 파일 경로."""
    today = datetime.now().strftime("%Y-%m-%d")
    return _get_feedback_dir() / f"feedback_{today}.json"


def _load_file(filepath: Path) -> list[dict]:
    """JSON 파일 읽기. 없거나 손상됐으면 빈 리스트 반환."""
    if not filepath.exists():
        return []
    try:
        text = filepath.read_text(encoding="utf-8").strip()
        if not text:
            return []
        return json.loads(text)
    except (json.JSONDecodeError, OSError):
        return []


def _save_file(filepath: Path, data: list[dict]) -> None:
    """JSON 파일 쓰기."""
    filepath.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class FeedbackStore:
    """JSON 날짜별 파일 피드백 저장소."""

    enabled: bool = True  # JSON 방식 활성화

    def save(self, feedback: "UserFeedback") -> bool:
        """피드백을 오늘 날짜 파일에 저장한다.

        Returns:
            저장 성공 여부
        """
        if not self.enabled:
            return False

        try:
            self._save_impl(feedback)
            return True
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(
                "피드백 저장 실패: %s", exc
            )
            return False

    def _save_impl(self, feedback: "UserFeedback") -> None:
        """JSON 파일에 피드백 항목을 추가한다."""
        filepath = _get_today_file()
        lock = _get_file_lock(str(filepath))

        with lock:
            data = _load_file(filepath)
            data.append(feedback.to_dict())
            _save_file(filepath, data)

    def stats(self) -> dict:
        """저장된 피드백 통계."""
        feedback_dir = _get_feedback_dir()
        files = sorted(feedback_dir.glob("feedback_*.json"))

        total = 0
        agreements = 0
        false_positives = 0
        by_date: dict[str, int] = {}

        for f in files:
            date = f.stem.replace("feedback_", "")
            items = _load_file(f)
            count = len(items)
            total += count
            by_date[date] = count
            agreements += sum(
                1 for item in items
                if item.get("isAgreement")
            )
            false_positives += sum(
                1 for item in items
                if item.get("isFalsePositive")
            )

        return {
            "enabled": self.enabled,
            "total": total,
            "agreements": agreements,
            "false_positives": false_positives,
            "agreement_rate": round(agreements / total, 3) if total else 0,
            "by_date": by_date,
            "storage": "json",
            "feedback_dir": str(feedback_dir),
        }

    def list_feedbacks(
        self,
        date: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """저장된 피드백 목록 조회.

        Args:
            date: "YYYY-MM-DD" 형식. None이면 오늘.
            limit: 최대 반환 수.
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        filepath = _get_feedback_dir() / f"feedback_{date}.json"
        items = _load_file(filepath)
        return items[-limit:]


# 싱글턴 인스턴스
_store = FeedbackStore()


def get_store() -> FeedbackStore:
    """전역 FeedbackStore 인스턴스를 반환한다."""
    return _store
