"""비식별화 도구 HTTP API 메인 앱.

17주차 6단계: 기본 구조 + 헬스 체크/버전 엔드포인트만 구현.
이후 단계에서 5종 detector 엔드포인트, 다운로드, 피드백을 추가합니다.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

# src 디렉토리를 sys.path에 추가 (detector import용)
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from api.detect_router import router as detect_router
from api.feedback_router import router as feedback_router


# ── 메타데이터 ────────────────────────────────────────────────

API_TITLE = "비식별화 도구 API"
API_DESCRIPTION = """
사내 비식별화 도구의 HTTP API 입니다.

5종 파일 형식(xlsx, docx, pptx, hwpx, pdf)에 대해 개인정보/민감정보를 탐지하고,
사용자에게 위치와 조치 방법을 안내합니다.

## 통합 정책

- **xlsx**: applied 모드 (시스템이 자동 비식별화)
- **docx/pptx/hwpx/pdf**: guide 모드 (시스템은 안내만, 사용자가 직접 수정)

## 탐지 소스

- **regex**: 명확한 패턴 (이메일, IP, VLAN 등) → 자동 처리
- **NER**: 한국인 성명 → 자동 처리
- **AI**: 민감 후보 추천 → 사용자 검토 대상 (review_targets)
"""
API_VERSION = "0.1.0"


# ── 응답 모델 ──────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """헬스 체크 응답."""
    status: str
    service: str


class VersionResponse(BaseModel):
    """버전 정보 응답."""
    api_version: str
    python_version: str
    platform: str
    detectors: dict[str, str]
    models: dict[str, Any]


# ── 앱 인스턴스 ────────────────────────────────────────────────

app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# detect 라우터 등록
app.include_router(detect_router)

# feedback 라우터 등록 (no-op, 부서 협의 후 활성화)
app.include_router(feedback_router)


@app.on_event("startup")
async def on_startup() -> None:
    """서버 시작 시 만료 토큰 + 고아 파일 정리."""
    from api.detect_router import startup_cleanup
    startup_cleanup()


# ── 기본 엔드포인트 ────────────────────────────────────────────

@app.get(
    "/api/health",
    response_model=HealthResponse,
    summary="헬스 체크",
    description="서비스가 응답 가능한 상태인지 확인합니다. PHP 시스템에서 모니터링용으로 사용합니다.",
    tags=["system"],
)
async def health_check() -> HealthResponse:
    """단순 헬스 체크. 항상 200 OK 반환."""
    return HealthResponse(status="ok", service="deidentify-api")


@app.get(
    "/api/version",
    response_model=VersionResponse,
    summary="버전 정보",
    description="API, Python, detector, 모델 버전 정보를 반환합니다.",
    tags=["system"],
)
async def get_version() -> VersionResponse:
    """API 메타데이터와 의존성 버전 정보."""
    detectors_status: dict[str, str] = {}
    for module_name in (
        "xlsx_deidentify_apply",
        "docx_detector",
        "pptx_detector",
        "hwpx_detector",
        "pdf_detector",
    ):
        try:
            __import__(module_name)
            detectors_status[module_name] = "available"
        except ImportError as exc:
            detectors_status[module_name] = f"import_error: {exc}"

    # 환경 변수 기반 모델 상태 확인
    from api.detect_router import get_model_status
    models_status = get_model_status()

    return VersionResponse(
        api_version=API_VERSION,
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        detectors=detectors_status,
        models=models_status,
    )


def _check_optional_import(module_name: str) -> str:
    """optional 모듈 import 가능 여부 확인."""
    try:
        __import__(module_name)
        return "available"
    except ImportError:
        return "not_installed"


# ── 루트 엔드포인트 ─────────────────────────────────────────────

@app.get(
    "/",
    summary="API 루트",
    description="API 사용 안내를 표시합니다.",
    tags=["system"],
)
async def root() -> dict[str, Any]:
    """API 사용 안내."""
    return {
        "service": API_TITLE,
        "version": API_VERSION,
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc",
        },
        "endpoints": {
            "health": "/api/health",
            "version": "/api/version",
        },
        "message": (
            "이 API는 5종 파일 형식의 비식별화 처리를 제공합니다. "
            "/docs 에서 자세한 사용법을 확인하세요."
        ),
    }
