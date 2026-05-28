# 비식별화 도구 API 활용 가이드

작성일: 2026-05  
버전: 0.1.0

---

## 1. 프로젝트 개요

사내 문서(xlsx, docx, pptx, hwpx, pdf)에 포함된 개인정보·민감정보를 자동으로 탐지하고 비식별화 처리를 안내하는 도구입니다.

### 탐지 방식 3종

| 소스 | 방식 | 처리 결과 |
|------|------|-----------|
| **regex** | 이메일, 전화번호, IP, VLAN, 사번 등 명확한 패턴 | 자동 비식별화 |
| **NER** | 한국인 성명 (KoELECTRA 모델) | 자동 비식별화 |
| **AI** | 문맥 기반 민감 문장 분류 (sklearn TF-IDF) | 사용자 검토 대상으로 제안 |

### 파일 형식별 처리 방식

| 형식 | 처리 방식 | 설명 |
|------|-----------|------|
| **xlsx** | `applied` | 시스템이 직접 비식별화 → 결과 파일 다운로드 |
| **docx / pptx / hwpx / pdf** | `guide` | 탐지 위치와 조치 방법 안내 → 사용자가 원본 직접 수정 |

### 등급 체계

| 등급 | 의미 | 처리 원칙 |
|------|------|-----------|
| **C** | 기밀 (Confidential) | 외부 AI 사용 불가. 삭제 또는 비식별화 필수 |
| **S** | 민감 (Sensitive) | 비식별화 후 제한적 사용 가능 |
| **O** | 일반 (Open) | 그대로 사용 가능 |

---

## 2. 서버 실행

```bash
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

> `--workers 1` 필수: xlsx 다운로드 토큰이 프로세스 메모리 기반이므로 멀티 워커 시 토큰을 찾지 못합니다.

접속 확인:
```bash
curl http://127.0.0.1:8000/api/health
# {"status":"ok","service":"deidentify-api"}
```

| URL | 설명 |
|-----|------|
| `http://127.0.0.1:8000/` | HTML UI (브라우저 직접 사용) |
| `http://127.0.0.1:8000/docs` | Swagger UI (API 테스트) |

---

## 3. API 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/health` | 서버 상태 확인 |
| GET | `/api/version` | 버전 및 모델 상태 |
| **POST** | **`/api/detect`** | **파일 비식별화 처리 (주요)** |
| GET | `/api/download/{token}` | xlsx 결과 파일 다운로드 |
| POST | `/api/feedback` | 사용자 판단 피드백 저장 |
| GET | `/api/feedback/stats` | 피드백 통계 조회 |
| GET | `/api/feedback/list` | 피드백 목록 조회 |

---

## 4. POST /api/detect — 요청

`multipart/form-data` 형식으로 파일과 옵션을 함께 전송합니다.

### 요청 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `file` | File | 필수 | xlsx / docx / pptx / hwpx / pdf |
| `deletionMode` | string | `mark` | `mark`: 삭제 대상을 `(삭제됨)`으로 표시 / `delete`: 빈 문자열로 제거 |
| `useNer` | bool | `false` | 성명 탐지 NER 모델 사용 여부 |
| `useAi` | bool | `false` | 문맥 기반 AI 탐지 사용 여부 |
| `userId` | string | 없음 | 사용자 식별자 (피드백 연계용) |

**deletionMode 권장**: `mark` — 사용자가 원문과 비교하며 검토하기 좋습니다.

### 요청 예시

```bash
# curl
curl -X POST http://127.0.0.1:8000/api/detect \
  -F "file=@report.pdf" \
  -F "deletionMode=mark" \
  -F "useAi=true"
```

```php
// PHP cURL
$ch = curl_init('http://127.0.0.1:8000/api/detect');
curl_setopt_array($ch, [
    CURLOPT_POST           => true,
    CURLOPT_POSTFIELDS     => [
        'file'         => new CURLFile($tmpPath, $mimeType, $fileName),
        'deletionMode' => 'mark',
        'useNer'       => 'false',
        'useAi'        => 'true',
        'userId'       => $sessionUserId,
    ],
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => 60,
]);
$json = curl_exec($ch);
$result = json_decode($json, true);
```

---

## 5. POST /api/detect — 응답 구조

### 5.1 공통 최상위 구조

```json
{
  "success": true,
  "fileType": "pdf",
  "applyMode": "guide",
  "downloadToken": null,
  "autoResults": [...],
  "reviewTargets": [...],
  "warnings": [...],
  "summary": {
    "totalLocations": 3,
    "autoTargetCount": 5,
    "appliedLocations": 2,
    "skippedLocations": 1
  },
  "metadata": {
    "originalFilename": "report.pdf",
    "fileSize": 210380
  }
}
```

| 필드 | 설명 |
|------|------|
| `success` | 처리 성공 여부 |
| `fileType` | 처리된 파일 형식 |
| `applyMode` | `applied`(xlsx) 또는 `guide`(그 외) |
| `downloadToken` | xlsx 결과 다운로드 토큰 (xlsx만 non-null) |
| `autoResults` | 자동 처리된 항목 목록 |
| `reviewTargets` | AI 추천 검토 항목 목록 |
| `warnings` | 처리 중 발생한 경고 |
| `summary` | 처리 결과 집계 |

### 5.2 summary 필드 의미

| 필드 | 설명 |
|------|------|
| `totalLocations` | 탐지된 위치 수 (중복 없음) |
| `autoTargetCount` | 자동 처리 대상 건수 (한 위치에 여러 건 가능) |
| `appliedLocations` | 실제 비식별화 처리된 위치 수 |
| `skippedLocations` | 처리 건너뛴 위치 수 (원문 불일치 등) |

---

## 6. autoResults — 자동 처리 항목

regex 또는 NER이 탐지하여 자동으로 비식별화 처리한 항목 목록입니다.
**guide 모드**에서는 실제 파일 수정은 안 되며, 사용자가 이 위치를 직접 찾아 수정해야 합니다.

### 항목 구조

```json
{
  "locationLabel": "1쪽 21번째 줄: - VLAN 301 : GI 1~12...",
  "locationMeta": {
    "fileType": "pdf",
    "section": "text_line",
    "pageNo": 0,
    "lineNo": 20
  },
  "status": "applied",
  "label": "IP/네트워크",
  "action": "삭제",
  "originalText": "VLAN 301",
  "appliedText": "(삭제됨)",
  "grade": "C",
  "source": "regex",
  "appliedTargetCount": 1,
  "skippedTargetCount": 0,
  "warnings": []
}
```

### 주요 필드 설명

| 필드 | 설명 |
|------|------|
| `locationLabel` | 사람이 읽을 수 있는 위치 문자열. UI에 그대로 표시 가능 |
| `locationMeta` | 위치 구조화 데이터 (파일 형식별로 다름, 아래 참고) |
| `label` | 탐지된 정보 유형 (예: "이메일 주소", "성명", "IP/네트워크") |
| `originalText` | 원문에서 탐지된 텍스트 |
| `appliedText` | 비식별화 결과 (마스킹: `***`, 삭제: `(삭제됨)`) |
| `grade` | 등급 `C` / `S` / `O` |
| `source` | 탐지 소스 `regex` / `ner` / `mixed` |
| `action` | 처리 방법 (`마스킹` / `삭제`) |
| `status` | `applied`(처리됨) / `skipped`(건너뜀) |

### locationMeta 형식별 구조

| fileType | 주요 필드 | 설명 |
|----------|-----------|------|
| `pdf` | `pageNo`, `lineNo` | 0-based |
| `docx` | `section`, `paragraphNo`, `tableNo`, `rowNo`, `colNo` | section: `body` / `table_cell` |
| `pptx` | `slideNo`, `shapeNo`, `paragraphNo` | section: `shape_text` / `table_cell` / `notes` |
| `hwpx` | `sectionNo`, `paragraphNo` | section: `body` / `table_cell` |
| `xlsx` | `sheetName`, `cellRef` | 예: `"Sheet1"`, `"B2"` |

> 일반적으로는 `locationLabel` 문자열만으로 UI 표시에 충분합니다.

### autoResults 활용 예시

```php
foreach ($result['autoResults'] as $item) {
    $grade  = $item['grade'];   // "C", "S", "O"
    $source = $item['source'];  // "regex", "ner", "mixed"

    // 등급별 배지 색상
    $color = match($grade) {
        'C'     => 'red',
        'S'     => 'orange',
        default => 'green',
    };

    echo "<span style='color:{$color}'>[{$grade}]</span> ";
    echo htmlspecialchars($item['locationLabel']);
    echo " | " . htmlspecialchars($item['originalText']);
    echo " → " . htmlspecialchars($item['appliedText']);
    echo "<br>";
}
```

---

## 7. reviewTargets — AI 추천 검토 항목

AI 모델이 민감정보로 추정했으나 **자동 처리하지 않고** 사용자 판단을 요청하는 항목입니다.
`useAi=true`일 때만 포함됩니다.

### 항목 구조

```json
{
  "locationLabel": "본문 5번째 단락: 입찰 평가표를...",
  "locationMeta": {
    "fileType": "docx",
    "section": "body",
    "paragraphNo": 4
  },
  "label": "민감정보",
  "action": "검토 필요",
  "context": "입찰 평가표를 검토했습니다. 향후 협상 전략은...",
  "grade": "S",
  "sensitiveType": "문맥 기반 민감정보",
  "sensitiveCategory": "AI_S",
  "source": "ai",
  "reason": "AI 문장분류 grade=S / confidence=0.7534 / threshold=0.50 / C=0.1231 / S=0.7534 / O=0.1235"
}
```

### 주요 필드 설명

| 필드 | 설명 |
|------|------|
| `context` | AI가 분석한 원문 문장 전체. UI에 표시해 사용자가 판단하도록 함 |
| `grade` | AI 추정 등급 (`C` / `S`). O등급은 reviewTargets에 포함되지 않음 |
| `sensitiveCategory` | AI 추정 카테고리 (`AI_C` / `AI_S`) |
| `reason` | AI 예측 근거 (confidence, 각 등급 확률 포함) |

### 사용자가 판단해야 할 선택지

| 선택 | 의미 |
|------|------|
| `C` | C급 기밀로 확인 — 외부 AI 사용 불가 |
| `S` | S급 민감정보로 확인 — 비식별화 후 사용 |
| `O` | 일반 정보 — 조치 불필요 |
| `X` | 오탐 — 민감정보가 아님 |

### reviewTargets 활용 예시

```php
foreach ($result['reviewTargets'] as $idx => $rv) {
    $aiGrade = $rv['grade'];  // AI 추정값 기본 선택

    echo "<p><strong>" . htmlspecialchars($rv['locationLabel']) . "</strong></p>";
    echo "<blockquote>" . htmlspecialchars($rv['context']) . "</blockquote>";
    echo "<p>AI 추정: {$aiGrade}급</p>";

    foreach (['C', 'S', 'O', 'X'] as $grade) {
        $checked = ($grade === $aiGrade) ? 'checked' : '';
        echo "<label>
            <input type='radio' name='grade[{$idx}]' value='{$grade}' {$checked}>
            {$grade}급
          </label>";
    }
}
```

---

## 8. xlsx 다운로드 흐름

xlsx는 `applied` 모드로 서버가 직접 비식별화 처리하고, 결과 파일을 다운로드 토큰으로 제공합니다.

### 흐름

```
1. POST /api/detect → 응답에 downloadToken 포함
2. GET  /api/download/{token} → 비식별화된 xlsx 파일 반환
```

### 주의사항

- 토큰은 **1회용** — 다운로드 후 즉시 만료
- 토큰 유효 시간: **1시간**
- 만료/없는 토큰: HTTP 404 반환

### 다운로드 예시

```bash
curl -O -J http://127.0.0.1:8000/api/download/{token}
```

```php
// PHP: FastAPI에서 파일을 받아 브라우저로 전달
$token = $result['downloadToken'];
$ch = curl_init("http://127.0.0.1:8000/api/download/{$token}");
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HEADER         => true,
    CURLOPT_TIMEOUT        => 30,
]);
$response   = curl_exec($ch);
$headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
$httpCode   = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($httpCode !== 200) {
    die('파일 다운로드 실패. 토큰이 만료되었거나 이미 사용됐습니다.');
}

$body = substr($response, $headerSize);
header('Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
header('Content-Disposition: attachment; filename="deidentified.xlsx"');
echo $body;
```

---

## 9. POST /api/feedback — 사용자 피드백 저장

reviewTargets에 대한 사용자의 최종 판단을 저장합니다.
이 데이터는 AI 모델 재학습에 활용됩니다.

### 요청 (JSON)

```json
{
  "locationLabel": "본문 5번째 단락: 입찰 평가표를...",
  "context": "입찰 평가표를 검토했습니다. 향후 협상 전략은...",
  "aiGrade": "S",
  "userGrade": "O",
  "fileType": "docx",
  "sensitiveCategory": "AI_S",
  "userId": "user123"
}
```

| 필드 | 설명 |
|------|------|
| `aiGrade` | AI가 예측한 등급 (`C` / `S`) |
| `userGrade` | 사용자가 최종 판단한 등급 (`C` / `S` / `O` / `X`) |

### 피드백 분류

| 조건 | 분류 |
|------|------|
| `userGrade == "X"` | 오탐 (false positive) |
| `aiGrade != userGrade` | 등급 불일치 |
| `aiGrade == userGrade` | 동의 |

### 저장 위치

```text
feedback_data/
  feedback_2026-05-28.json
  feedback_2026-05-29.json
  ...
```

---

## 10. 에러 응답

```json
{
  "success": false,
  "errorCode": "UNSUPPORTED_FILE_TYPE",
  "message": "지원하지 않는 파일 형식입니다.",
  "detail": {"filename": "test.txt"}
}
```

| errorCode | HTTP | 발생 조건 |
|-----------|------|-----------|
| `UNSUPPORTED_FILE_TYPE` | 400 | xlsx/docx/pptx/hwpx/pdf 외 파일 |
| `NER_MODEL_NOT_CONFIGURED` | 503 | `useNer=true`인데 NER 모델 미설정 |
| `AI_MODEL_NOT_CONFIGURED` | 503 | `useAi=true`인데 AI 모델 미설정 |
| `INTERNAL_ERROR` | 500 | 처리 중 예외 발생 |

---

## 11. 전체 처리 흐름 요약

```
[사용자 / 연동 시스템]
        │
        ▼
POST /api/detect  ──────────────────────────────────────┐
  file + options                                         │
        │                                                │
        ▼                                                │
  [탐지 엔진]                                            │
  regex → 패턴 매칭                                     │
  NER   → 성명 탐지 (useNer=true)                       │
  AI    → 문맥 분류 (useAi=true)                        │
        │                                                │
        ▼                                                │
  응답 JSON                                              │
  ├── autoResults   : 자동 처리 결과 (위치 + 원문 + 결과) │
  ├── reviewTargets : AI 추천 검토 대상 (사용자 판단 필요) │
  ├── summary       : 전체 집계                         │
  └── downloadToken : xlsx인 경우 결과 파일 토큰         │
        │                                                │
        ├─── guide 모드 (docx/pptx/hwpx/pdf)            │
        │     autoResults의 위치를 참고해 원본 직접 수정  │
        │                                                │
        └─── applied 모드 (xlsx)                        │
              GET /api/download/{token}                  │
              → 비식별화된 xlsx 파일 다운로드            │

[사용자가 reviewTargets 판단]
        │
        ▼
POST /api/feedback  (AI 모델 개선에 활용)
```

---

## 12. 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NER_MODEL_PATH` | (없음) | NER 모델 경로. 미설정 시 NER 비활성 |
| `AI_MODEL_TYPE` | `keras` | AI 모델 종류 (`keras` \| `sklearn`) |
| `AI_MODEL_PATH` | `models/privacy_cso_char_keras_model.keras` | Keras 모델 경로 |
| `SKLEARN_MODEL_PATH` | `models/privacy_sentence_model_v2.pkl` | sklearn 모델 경로 |
| `NER_THRESHOLD` | `0.8` | NER 탐지 신뢰도 임계값 |
| `AI_THRESHOLD` | `0.5` | AI 탐지 신뢰도 임계값 |
| `FEEDBACK_DIR` | `(프로젝트 루트)/feedback_data` | 피드백 저장 디렉토리 |
| `LOG_DIR` | `(프로젝트 루트)/logs` | 로그 저장 디렉토리 |
