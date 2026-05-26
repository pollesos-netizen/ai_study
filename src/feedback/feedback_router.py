"""POST /api/feedback — 사용자 피드백 수집 엔드포인트.

17주차: no-op 구현.
요청을 받아 데이터 모델로 변환하지만 저장은 하지 않는다.
FeedbackStore.enabled=True + _save_impl() 구현 후 활성화.

부서 협의 필요 항목:
  - 저장 방식 (SQLite / PostgreSQL / JSON)
  - 사용자 식별 (익명 / 사번 / 부서)
  - 보존 기간
  - 접근 권한
  - 재학습 정책
  - 보안 등급 (원본 문서와 동일)
  - 감사 로그
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

router = APIRouter()


# ── 요청/응답 모델 ─────────────────────────────────────────────

class FeedbackPayload(BaseModel):
    """POST /api/feedback 요청 본문."""

    locationLabel: str = Field(..., description="탐지 위치 (예: '3쪽 5번째 줄')")
    context: str = Field(..., description="탐지된 문장 원문")
    aiGrade: str | None = Field(None, description="AI 추정 등급 (C/S/O/None)")
    userGrade: Literal["C", "S", "O", "X"] = Field(
        ...,
        description="사용자 판단 (C=기밀, S=민감, O=공개, X=오탐)",
    )
    fileType: str | None = Field(None, description="파일 형식")
    sensitiveCategory: str | None = Field(None, description="AI 탐지 카테고리")
    reason: str | None = Field(None, description="AI reason 문자열 (디버그용)")
    userId: str | None = Field(None, description="사용자 식별자")


# ── 엔드포인트 ────────────────────────────────────────────────

@router.post(
    "/api/feedback",
    summary="사용자 피드백 제출",
    description="""
AI 추천(reviewTargets)에 대한 사용자 판단을 수집합니다.

**현재 상태: no-op** — 요청을 수신하지만 저장하지 않습니다.

부서 협의 완료 후 `FeedbackStore.enabled=True`로 활성화합니다.

**userGrade 값:**
- `C`: 기밀 (외부 AI 사용 불가)
- `S`: 민감 (비식별화 후 사용 가능)
- `O`: 공개 (그대로 사용 가능)
- `X`: 잘못된 탐지 (오탐)
    """,
    tags=["feedback"],
)
async def submit_feedback(payload: FeedbackPayload) -> JSONResponse:

    from feedback.models import UserFeedback
    from feedback.store import get_store

    feedback = UserFeedback(
        location_label=payload.locationLabel,
        context=payload.context,
        ai_grade=payload.aiGrade,
        user_grade=payload.userGrade,
        file_type=payload.fileType,
        sensitive_category=payload.sensitiveCategory,
        reason=payload.reason,
        user_id=payload.userId,
    )

    store = get_store()
    saved = store.save(feedback)

    return JSONResponse(content={
        "success": True,
        "saved": saved,
        "message": (
            "피드백이 저장되었습니다." if saved
            else "피드백을 수신했습니다. (저장소 비활성 상태 — 부서 협의 후 활성화 예정)"
        ),
        "isAgreement": feedback.is_agreement(),
        "isFalsePositive": feedback.is_false_positive(),
    })


@router.get(
    "/api/feedback/stats",
    summary="피드백 통계",
    description="오늘 수집된 피드백의 통계를 반환합니다.",
    tags=["feedback"],
)
async def feedback_stats() -> JSONResponse:
    from feedback.store import get_store
    return JSONResponse(content=get_store().stats())


@router.get(
    "/api/feedback/list",
    summary="피드백 목록 조회",
    description="저장된 피드백 목록을 조회합니다. date 미입력 시 오늘 (YYYY-MM-DD).",
    tags=["feedback"],
)
async def feedback_list(
    date: str | None = None,
    limit: int = 100,
) -> JSONResponse:
    from feedback.store import get_store
    from datetime import datetime
    items = get_store().list_feedbacks(date=date, limit=limit)
    return JSONResponse(content={
        "success": True,
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "count": len(items),
        "items": items,
    })


@router.get(
    "/api/feedback/files",
    summary="피드백 파일 목록",
    description="저장된 날짜별 피드백 파일 목록을 반환합니다.",
    tags=["feedback"],
)
async def feedback_files() -> JSONResponse:
    from feedback.store import get_store
    files = get_store().list_files()
    return JSONResponse(content={
        "files": [Path(f).name for f in files],
        "count": len(files),
    })
