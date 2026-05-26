"""비식별화 도구 HTTP API.

PHP 시스템 등 외부 클라이언트가 호출하는 백엔드 API를 제공합니다.
detector 5종(xlsx, docx, pptx, hwpx, pdf)을 HTTP 인터페이스로 노출하고,
사용자 피드백을 수집할 endpoint를 제공합니다.

서버 실행:
    uvicorn src.api.main:app --host 0.0.0.0 --port 8000

또는 개발 모드 (코드 변경 시 자동 재시작):
    uvicorn src.api.main:app --reload --port 8000

자동 생성된 OpenAPI 문서:
    http://localhost:8000/docs    (Swagger UI)
    http://localhost:8000/redoc   (ReDoc)
"""

__version__ = "0.1.0"
