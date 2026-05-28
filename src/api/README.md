# 비식별화 도구 서버 실행 가이드

사내 문서(xlsx, docx, pptx, hwpx, pdf)의 개인정보·민감정보를 탐지하고 비식별화를 안내하는 FastAPI 서버입니다.

---

## 1. 사전 요구사항

- Python 3.10 이상
- 의존성 설치:

```bash
pip install -r src/api/requirements.txt
```

---

## 2. 모델 파일 준비

모델 파일은 별도로 전달받아 `models/` 폴더에 배치합니다.

```
models/
├── privacy_sentence_model_v3.pkl          ← AI 분류 모델 (sklearn, 필수)
├── privacy_cso_char_keras_model.keras     ← AI 분류 모델 (keras, 선택)
└── hf/
    └── KoELECTRA-small-v3-modu-ner/       ← NER 성명 탐지 모델 (선택)
```

---

## 3. 환경 변수 설정 (.env)

프로젝트 루트에 `.env` 파일을 생성합니다.

```env
# AI 모델 종류 선택: sklearn (권장) | keras
AI_MODEL_TYPE=sklearn

# sklearn 모델 경로 (AI_MODEL_TYPE=sklearn 시 사용)
SKLEARN_MODEL_PATH=C:\경로\models\privacy_sentence_model_v3.pkl

# Keras 모델 경로 (AI_MODEL_TYPE=keras 시 사용)
AI_MODEL_PATH=C:\경로\models\privacy_cso_char_keras_model.keras

# NER 모델 경로 (useNer=true 사용 시 필요, 미설정 시 NER 비활성)
NER_MODEL_PATH=C:\경로\models\hf\KoELECTRA-small-v3-modu-ner

# 탐지 임계값 (기본값 그대로 사용 권장)
NER_THRESHOLD=0.8
AI_THRESHOLD=0.5
```

> 모델 없이 실행해도 됩니다. regex 탐지만 동작하며, `useNer=true` / `useAi=true` 요청 시 503을 반환합니다.

---

## 4. 서버 실행

```bash
# 운영 모드 (필수: --workers 1)
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 1

# 개발 모드 (코드 변경 시 자동 재시작)
uvicorn src.api.main:app --reload --port 8000
```

> **`--workers 1` 필수**: xlsx 다운로드 토큰이 프로세스 메모리 기반이므로 멀티 워커 시 토큰을 찾지 못합니다.

---

## 5. 동작 확인

```bash
# 서버 상태
curl http://127.0.0.1:8000/api/health
# {"status":"ok","service":"deidentify-api"}

# 모델 로드 상태 확인
curl http://127.0.0.1:8000/api/version
```

브라우저에서 `http://127.0.0.1:8000` 접속 시 HTML UI가 표시됩니다.  
`http://127.0.0.1:8000/docs` 에서 Swagger UI로 API를 직접 테스트할 수 있습니다.

---

## 6. 디렉토리 구조

```
(프로젝트 루트)/
├── src/
│   ├── api/
│   │   ├── main.py              # FastAPI 앱 진입점
│   │   ├── detect_router.py     # 탐지 엔드포인트
│   │   ├── feedback_router.py   # 피드백 엔드포인트
│   │   └── requirements.txt     # 의존성
│   ├── regex_detector.py        # 정규식 탐지
│   ├── docx_detector.py
│   ├── pptx_detector.py
│   ├── hwpx_detector.py
│   ├── pdf_detector.py
│   └── xlsx_deidentify_apply.py
├── models/                      # 모델 파일 (별도 전달)
├── static/
│   └── index.html               # HTML UI
├── feedback_data/               # 피드백 저장 (자동 생성)
├── logs/                        # 로그 파일 (자동 생성)
└── .env                         # 환경 변수
```

---

## 7. API 활용

자세한 API 사용법은 `reports/api_usage_guide.md` 를 참고하세요.

| URL | 설명 |
|-----|------|
| `POST /api/detect` | 파일 비식별화 처리 (주요) |
| `GET /api/download/{token}` | xlsx 결과 다운로드 |
| `POST /api/feedback` | 사용자 판단 피드백 저장 |
| `GET /api/health` | 서버 상태 확인 |
| `GET /docs` | Swagger UI |
