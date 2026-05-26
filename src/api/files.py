"""
임시 파일 관리 + xlsx downloadToken 생성/조회.

업로드된 파일은 처리 후 즉시 삭제한다.
xlsx applied 결과 파일은 downloadToken으로 관리하며,
일정 시간 후 자동 만료된다.

설계 결정:
- 토큰 생성은 FastAPI 응답 레이어에서 담당 (관심사 분리)
- CommonApplyResult는 파일 처리 결과만 담당, 토큰 모름
- 임시 파일 디렉토리는 환경 변수 DEIDENTIFY_TMP_DIR로 변경 가능
"""

from __future__ import annotations

import secrets
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path


# ── 임시 디렉토리 ─────────────────────────────────────────────

def get_tmp_dir() -> Path:
    """임시 파일 저장 디렉토리.

    환경 변수 DEIDENTIFY_TMP_DIR 설정 시 해당 경로 사용.
    """
    import os
    override = os.environ.get("DEIDENTIFY_TMP_DIR", "").strip()
    if override:
        p = Path(override)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return Path(tempfile.gettempdir()) / "deidentify_api"


# ── downloadToken 저장소 ──────────────────────────────────────

@dataclass
class _TokenEntry:
    file_path: Path
    original_name: str
    created_at: float = field(default_factory=time.time)


# 프로세스 메모리에 보관 (단일 프로세스 기준)
# 멀티 워커 환경에서는 Redis 등으로 교체 필요 — 17주차 PoC에서는 단일 워커로 운영
_token_store: dict[str, _TokenEntry] = {}

# 토큰 유효 시간 (초), 기본 1시간
TOKEN_TTL_SECONDS = 3600


def create_download_token(file_path: Path, original_name: str) -> str:
    """xlsx 결과 파일에 대한 downloadToken을 생성하고 저장한다."""
    _purge_expired()
    token = secrets.token_urlsafe(32)
    _token_store[token] = _TokenEntry(
        file_path=file_path,
        original_name=original_name,
    )
    return token


def resolve_download_token(token: str) -> _TokenEntry | None:
    """토큰으로 파일 경로를 조회한다. 만료 또는 없으면 None."""
    _purge_expired()
    entry = _token_store.get(token)
    if entry is None:
        return None
    if time.time() - entry.created_at > TOKEN_TTL_SECONDS:
        _token_store.pop(token, None)
        return None
    return entry


def revoke_token(token: str) -> None:
    """토큰을 만료시키고 연결된 파일을 삭제한다."""
    entry = _token_store.pop(token, None)
    if entry and entry.file_path.exists():
        entry.file_path.unlink(missing_ok=True)


def _token_store_remove(token: str) -> None:
    """토큰만 제거한다. 파일은 삭제하지 않는다 (FileResponse background에서 처리)."""
    _token_store.pop(token, None)


def cleanup_expired_tokens() -> int:
    """만료된 토큰과 연결된 파일을 정리한다.

    서버 시작 시 또는 주기적으로 호출해 임시 파일이 누적되지 않도록 한다.

    Returns:
        정리된 토큰 수
    """
    now = time.time()
    expired = [
        t for t, e in list(_token_store.items())
        if now - e.created_at > TOKEN_TTL_SECONDS
    ]
    for token in expired:
        entry = _token_store.pop(token, None)
        if entry and entry.file_path.exists():
            entry.file_path.unlink(missing_ok=True)
    return len(expired)


def cleanup_orphan_files() -> int:
    """토큰 없이 남은 결과 파일(result_*.xlsx)을 정리한다.

    비정상 종료 등으로 토큰 저장소가 초기화되었지만
    파일은 남아있는 경우를 처리한다.

    Returns:
        삭제된 파일 수
    """
    tmp_dir = get_tmp_dir()
    if not tmp_dir.exists():
        return 0

    # 현재 유효한 토큰의 파일 경로 목록
    valid_paths = {str(e.file_path) for e in _token_store.values()}

    count = 0
    for path in tmp_dir.glob("result_*.xlsx"):
        if str(path) not in valid_paths:
            try:
                path.unlink(missing_ok=True)
                count += 1
            except Exception:
                pass
    return count


def _purge_expired() -> None:
    """만료된 토큰과 파일을 일괄 정리한다."""
    now = time.time()
    expired = [
        t for t, e in _token_store.items()
        if now - e.created_at > TOKEN_TTL_SECONDS
    ]
    for token in expired:
        entry = _token_store.pop(token)
        if entry.file_path.exists():
            entry.file_path.unlink(missing_ok=True)


# ── 임시 업로드 파일 관리 ─────────────────────────────────────

def save_upload_tmp(data: bytes, suffix: str) -> Path:
    """업로드 파일을 임시 디렉토리에 저장하고 경로를 반환한다."""
    tmp_dir = get_tmp_dir()
    tmp_dir.mkdir(parents=True, exist_ok=True)

    token = secrets.token_hex(8)
    path = tmp_dir / f"upload_{token}{suffix}"
    path.write_bytes(data)
    return path


def cleanup_upload(path: Path) -> None:
    """임시 업로드 파일을 삭제한다."""
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass
