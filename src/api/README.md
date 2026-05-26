# 비식별화 도구 HTTP API

PHP 시스템 등 외부 클라이언트가 호출하는 백엔드 API입니다.

## 의존성

```bash
pip install -r requirements.txt
```

## 모델 경로 설정 (환경 변수)

```bash
# NER 모델 (한국인 성명 탐지)
export NER_MODEL_PATH=models/ner/KoELECTRA-small-v3-modu-ner

# AI 분류 모델 (민감 후보 추천)
export AI_MODEL_PATH=models/privacy_cso_char_keras_model.keras
```

미설정 시 `/api/version`에서 `not_configured`로 표시됩니다.
`useNer=true` 또는 `useAi=true`인데 경로가 없으면 HTTP 503 반환.

## 실행

### 개발 모드

```bash
uvicorn src.api.main:app --reload --port 8000
```

### ⚠️ 운영 모드 — 반드시 `--workers 1`

```bash
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

**`--workers 1` 이유:**
현재 `downloadToken` 저장소가 프로세스 메모리 기반이므로 멀티 워커 환경에서는
detect 요청과 download 요청이 다른 워커로 가면 토큰을 찾을 수 없습니다.

멀티 워커 운영이 필요한 경우 Redis, SQLite, DB 기반 저장소로 교체해야 합니다.

### PHP 연동 시 (localhost만 바인딩)

```bash
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

`127.0.0.1`로 바인딩하면 같은 서버 안에서만 접근 가능합니다.
PHP가 cURL로 내부 호출하는 구조에서 외부 노출을 방지합니다.

## 엔드포인트

| Method | Path                  | 설명                      |
|--------|-----------------------|---------------------------|
| GET    | `/`                   | API 사용 안내             |
| GET    | `/api/health`         | 헬스 체크                 |
| GET    | `/api/version`        | 버전 및 모델 상태         |
| POST   | `/api/detect`         | 파일 비식별화 (통합)      |
| GET    | `/api/download/{token}` | xlsx 결과 다운로드      |
| GET    | `/docs`               | Swagger UI                |
| GET    | `/redoc`              | ReDoc                     |

## POST /api/detect 요청

```
multipart/form-data:
  file          업로드 파일 (xlsx/docx/pptx/hwpx/pdf)
  deletionMode  delete | mark (기본: mark)
  useNer        true | false (기본: false)
  useAi         true | false (기본: false)
  userId        사용자 ID (선택, 로깅/피드백용)
```

## 응답 구조 (C안)

### 성공

```json
{
  "success": true,
  "fileType": "pdf",
  "applyMode": "guide",
  "downloadToken": null,
  "outputFilePath": null,
  "autoResults": [...],
  "reviewTargets": [...],
  "warnings": [],
  "summary": {...},
  "metadata": {
    "originalFilename": "test.pdf",
    "fileSize": 12345
  }
}
```

xlsx applied 시:
```json
{
  "success": true,
  "fileType": "xlsx",
  "applyMode": "applied",
  "downloadToken": "abc123",
  ...
}
```

### 에러

```json
{
  "success": false,
  "errorCode": "UNSUPPORTED_FILE_TYPE",
  "message": "지원하지 않는 파일 형식입니다.",
  "detail": {"filename": "test.txt"}
}
```

에러 코드:

| errorCode                  | HTTP | 설명                          |
|---------------------------|------|-------------------------------|
| UNSUPPORTED_FILE_TYPE      | 400  | 미지원 파일 형식              |
| NER_MODEL_NOT_CONFIGURED   | 503  | NER_MODEL_PATH 미설정         |
| AI_MODEL_NOT_CONFIGURED    | 503  | AI_MODEL_PATH 미설정          |
| INTERNAL_ERROR             | 500  | 처리 중 예외 발생             |

## PHP cURL 연동 예시

```php
$file = new CURLFile(
    $_FILES['file']['tmp_name'],
    $_FILES['file']['type'],
    $_FILES['file']['name']
);

$ch = curl_init('http://127.0.0.1:8000/api/detect');
curl_setopt_array($ch, [
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => [
        'file'         => $file,
        'deletionMode' => 'mark',
        'useNer'       => 'false',
        'useAi'        => 'false',
        'userId'       => $_SESSION['user_id'] ?? '',
    ],
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => 60,
]);

$response = curl_exec($ch);
$result = json_decode($response, true);
curl_close($ch);

if (!$result['success']) {
    // 에러 처리
    echo $result['message'];
    exit;
}

if ($result['applyMode'] === 'applied') {
    // xlsx: 다운로드 버튼 표시
    $token = $result['downloadToken'];
    echo "<a href='/api/download/{$token}'>비식별화 파일 다운로드</a>";
} else {
    // guide: 결과 표시
    foreach ($result['autoResults'] as $item) {
        echo $item['locationLabel'];
        echo $item['appliedText'];
    }
}
```

## downloadToken 제한 사항

- **단일 워커 전용**: 프로세스 메모리 기반 저장소
- **1회용**: 다운로드 후 즉시 만료
- **TTL**: 1시간 후 자동 만료
- **멀티 워커 운영 시**: Redis/SQLite/DB 기반 저장소로 교체 필요
