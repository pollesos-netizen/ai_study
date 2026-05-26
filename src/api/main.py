"""비식별화 도구 HTTP API 메인 앱."""

from __future__ import annotations

import logging
import logging.handlers
import platform
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# src 디렉토리를 sys.path에 추가 (detector import용)
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ── 로깅 설정 ──────────────────────────────────────────────────
import os as _os

# 환경변수 LOG_DIR로 로그 경로 지정 가능. 미설정 시 프로젝트 루트/logs
_log_dir_env = _os.environ.get("LOG_DIR", "").strip()
LOG_DIR = Path(_log_dir_env) if _log_dir_env else SRC_DIR.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

print(f"[logging] 로그 파일: {LOG_FILE}", file=sys.stderr)

_file_handler = logging.handlers.RotatingFileHandler(
    str(LOG_FILE),
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=3,
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))

# 루트 로거 설정
_root = logging.getLogger()
_root.setLevel(logging.INFO)
_root.addHandler(_file_handler)

# 터미널에는 WARNING 이상만 표시 (AI 예측 실패 등은 파일에만)
_console = logging.StreamHandler(sys.stderr)
_console.setLevel(logging.WARNING)
_console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
_root.addHandler(_console)

# uvicorn 로거는 파일에도 기록
logging.getLogger("uvicorn").addHandler(_file_handler)
logging.getLogger("uvicorn.access").addHandler(_file_handler)

# .env 파일 자동 로드 (python-dotenv 설치 시)
# 프로젝트 루트의 .env 파일에서 NER_MODEL_PATH, AI_MODEL_PATH 등을 읽어온다
try:
    from dotenv import load_dotenv
    _env_path = SRC_DIR.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
        print(f"[startup] .env 로드: {_env_path}", file=sys.stderr)
    else:
        load_dotenv()  # 현재 디렉토리 .env 시도
except ImportError:
    pass  # python-dotenv 미설치 시 환경변수 직접 설정 필요

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

# CORS 설정 (사내망 배포용 — 브라우저 직접 접근 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 사내망이므로 전체 허용, 운영 시 도메인 지정
    allow_methods=["*"],
    allow_headers=["*"],
)

# detect 라우터 등록
app.include_router(detect_router)

# feedback 라우터 등록 (no-op, 부서 협의 후 활성화)
app.include_router(feedback_router)

# static 파일 서빙 (HTML/JS/CSS)
STATIC_DIR = SRC_DIR.parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_index():
    """메인 HTML 페이지 서빙."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "index.html이 없습니다. static/index.html을 배치하세요."}


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
    from api.detect_router import get_model_status, _get_ner_threshold, _get_ai_threshold
    models_status = get_model_status()
    models_status["ner_threshold"] = _get_ner_threshold()
    models_status["ai_threshold"] = _get_ai_threshold()

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