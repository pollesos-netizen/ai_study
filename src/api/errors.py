"""API 공통 에러 응답 모델."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """API 에러 응답."""
    error: str
    detail: str
    fileType: str | None = None


# 지원 확장자 → 내부 fileType 매핑
SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".xlsx": "xlsx",
    ".docx": "docx",
    ".pptx": "pptx",
    ".hwpx": "hwpx",
    ".pdf":  "pdf",
    ".csv":  "csv",
}


def detect_file_type(filename: str) -> str | None:
    """파일명에서 fileType을 감지한다. 미지원이면 None."""
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return SUPPORTED_EXTENSIONS.get(suffix)
