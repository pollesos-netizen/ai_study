# 비식별화 도구 API 연동 가이드 (PHP 팀 협의 자료)

작성일: 2026-05  
버전: 0.1.0  
대상: PHP 백엔드 개발팀

---

## 1. 구조 개요

```
[사용자 브라우저]
     ↓ HTTP (파일 업로드 / 결과 확인)
[PHP 서버 (Apache)]
     ↓ cURL (내부 호출, 외부 노출 안 됨)
[Python FastAPI (127.0.0.1:8000)]
     ↓
[비식별화 detector 5종]
```

- PHP가 사용자 인증/세션/화면 렌더링을 담당합니다.
- FastAPI는 파일 분석 엔진으로만 동작하며 외부에서 접근 불가합니다.
- PHP와 FastAPI는 같은 서버 안에서 `127.0.0.1`로 통신합니다.

---

## 2. 역할 분담

### PHP 팀 담당

```text
- 사용자 인증 및 세션 관리
- 파일 업로드 UI (HTML 폼)
- FastAPI cURL 호출
- 결과 JSON → HTML 렌더링
- C/S/O 등급 선택 UI (reviewTargets)
- 피드백 제출 (POST /api/feedback)
- 이력 저장 (필요 시 사내 DB)
- xlsx 다운로드 흐름 처리
```

### Python 팀 담당

```text
- FastAPI 서버 운영 (uvicorn)
- 5종 detector 유지보수
- 탐지 정확도 개선
- NER/AI 모델 관리
- API 스펙 변경 시 공지
```

---

## 3. 서버 실행 (Python 팀 담당)

```bash
# 운영 실행 (반드시 --workers 1)
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 1

# 모델 경로 설정 (선택)
export NER_MODEL_PATH=models/hf/KoELECTRA-small-v3-modu-ner
export AI_MODEL_PATH=models/privacy_cso_char_keras_model.keras
```

**`--workers 1` 필수**: downloadToken이 프로세스 메모리 기반이므로
멀티 워커 시 detect/download 요청이 다른 워커로 분산되면 토큰을 못 찾습니다.

서버 상태 확인:
```bash
curl http://127.0.0.1:8000/api/health
# {"status":"ok","service":"deidentify-api"}
```

---

## 4. API 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/health` | 헬스 체크 |
| GET | `/api/version` | 버전 + 모델 상태 |
| **POST** | **`/api/detect`** | **파일 비식별화 (주요)** |
| GET | `/api/download/{token}` | xlsx 결과 다운로드 |
| POST | `/api/feedback` | 사용자 피드백 (no-op) |
| GET | `/docs` | Swagger UI (개발 참고용) |

---

## 5. POST /api/detect — 요청 형식

```
Content-Type: multipart/form-data

필드:
  file          파일 (xlsx / docx / pptx / hwpx / pdf)
  deletionMode  mark | delete  (기본: mark)
  useNer        true | false   (기본: false)
  useAi         true | false   (기본: false)
  userId        사용자 ID      (선택, 세션에서 전달)
```

**deletionMode 설명:**
- `mark`: 삭제 대상을 `(삭제됨)` 표시 → 사용자가 결과 확인하기 좋음 (**권장**)
- `delete`: 삭제 대상을 빈 문자열로 처리

---

## 6. 응답 구조

### 6.1 공통 구조

```json
{
  "success": true,
  "fileType": "pdf",
  "applyMode": "guide",
  "downloadToken": null,
  "outputFilePath": null,
  "autoResults": [...],
  "reviewTargets": [...],
  "warnings": [...],
  "summary": {
    "totalLocations": 3,
    "autoTargetCount": 5,
    "appliedLocations": 0,
    "skippedLocations": 0
  },
  "metadata": {
    "originalFilename": "report.pdf",
    "fileSize": 210380
  }
}
```

### 6.2 applyMode별 차이

| applyMode | fileType | downloadToken | 처리 방식 |
|-----------|----------|---------------|-----------|
| `guide` | docx/pptx/hwpx/pdf | `null` | 사용자가 원본 직접 수정 |
| `applied` | xlsx | 토큰 문자열 | 시스템이 자동 비식별화 → 다운로드 |

### 6.3 에러 응답

```json
{
  "success": false,
  "errorCode": "UNSUPPORTED_FILE_TYPE",
  "message": "지원하지 않는 파일 형식입니다.",
  "detail": {"filename": "test.txt"}
}
```

에러 코드:

| errorCode | HTTP | 설명 |
|-----------|------|------|
| `UNSUPPORTED_FILE_TYPE` | 400 | 미지원 형식 (xlsx/docx/pptx/hwpx/pdf 외) |
| `NER_MODEL_NOT_CONFIGURED` | 503 | useNer=true인데 NER 모델 미설정 |
| `AI_MODEL_NOT_CONFIGURED` | 503 | useAi=true인데 AI 모델 미설정 |
| `INTERNAL_ERROR` | 500 | 처리 중 예외 |

---

## 7. fileType별 응답 JSON 예시

### 7.1 pdf (guide 모드)

```json
{
  "success": true,
  "fileType": "pdf",
  "applyMode": "guide",
  "downloadToken": null,
  "outputFilePath": null,
  "autoResults": [
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
      "appliedTargetCount": 1,
      "skippedTargetCount": 0,
      "warnings": []
    }
  ],
  "reviewTargets": [],
  "warnings": [],
  "summary": {
    "totalLocations": 1,
    "autoTargetCount": 1,
    "appliedLocations": 1,
    "skippedLocations": 0
  },
  "metadata": {
    "originalFilename": "network_report.pdf",
    "fileSize": 210380
  }
}
```

### 7.2 docx (guide 모드)

```json
{
  "success": true,
  "fileType": "docx",
  "applyMode": "guide",
  "downloadToken": null,
  "autoResults": [
    {
      "locationLabel": "본문 2번째 단락: 담당자 홍길동 부장...",
      "locationMeta": {
        "fileType": "docx",
        "section": "body",
        "paragraphNo": 1
      },
      "status": "applied",
      "label": "성명",
      "action": "마스킹",
      "originalText": "홍길동",
      "appliedText": "***",
      "appliedTargetCount": 1,
      "skippedTargetCount": 0,
      "warnings": []
    }
  ],
  "reviewTargets": [
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
      "reason": "AI 문장분류 grade=S / confidence=0.7534",
      "grade": "S",
      "sensitiveType": "문맥 기반 민감정보",
      "sensitiveCategory": "AI_S",
      "source": "ai"
    }
  ],
  "warnings": [],
  "summary": {
    "totalLocations": 2,
    "autoTargetCount": 1,
    "appliedLocations": 1,
    "skippedLocations": 0
  },
  "metadata": {
    "originalFilename": "proposal.docx",
    "fileSize": 45678
  }
}
```

### 7.3 xlsx (applied 모드)

```json
{
  "success": true,
  "fileType": "xlsx",
  "applyMode": "applied",
  "downloadToken": "zg6-NNIG7r_KVJWnE1PH...",
  "outputFilePath": null,
  "autoResults": [
    {
      "locationLabel": "Sheet B2",
      "locationMeta": {
        "fileType": "xlsx",
        "sheetName": "Sheet",
        "cellRef": "B2"
      },
      "status": "applied",
      "label": "이메일 주소",
      "action": "마스킹",
      "originalText": "test@example.com",
      "appliedText": "****************",
      "appliedTargetCount": 1,
      "skippedTargetCount": 0,
      "warnings": []
    }
  ],
  "reviewTargets": [],
  "warnings": [],
  "summary": {
    "totalLocations": 1,
    "autoTargetCount": 1,
    "appliedLocations": 1,
    "skippedLocations": 0
  },
  "metadata": {
    "originalFilename": "members.xlsx",
    "fileSize": 4931
  }
}
```

### 7.4 pptx (guide 모드) — docx와 동일 구조, locationMeta만 다름

```json
{
  "locationMeta": {
    "fileType": "pptx",
    "section": "shape_text",
    "slideNo": 0,
    "shapeNo": 1,
    "paragraphNo": 0
  }
}
```

### 7.5 hwpx (guide 모드) — docx와 동일 구조, locationMeta만 다름

```json
{
  "locationMeta": {
    "fileType": "hwpx",
    "section": "body",
    "sectionNo": 0,
    "paragraphNo": 2
  }
}
```

---

## 8. PHP 연동 전체 흐름

```
[1] 사용자: 파일 선택 + [비식별화] 클릭
[2] 브라우저 → PHP upload.php (multipart/form-data)
[3] PHP: 파일 임시 저장 + 세션 확인
[4] PHP → FastAPI POST /api/detect (cURL)
[5] FastAPI: 탐지 + 결과 JSON 반환
[6] PHP: JSON 파싱 → HTML 렌더링
[7] 사용자: 결과 확인
    - guide 모드: 위치 안내 + 원본 수정
    - applied 모드(xlsx): 다운로드 버튼 클릭
[8] (xlsx) 사용자 클릭 → PHP → FastAPI GET /api/download/{token}
[9] PHP: 파일 스트림 → 브라우저 다운로드
[10] (선택) 사용자: reviewTargets에서 C/S/O 선택
[11] PHP → FastAPI POST /api/feedback
```

---

## 9. PHP 구현 예시

### 9.1 파일 업로드 + detect 호출

```php
<?php
// upload.php

session_start();
if (!isset($_SESSION['user_id'])) {
    header('Location: /login.php');
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    die('잘못된 요청입니다.');
}

$file = $_FILES['file'];

// 파일 유효성 검사
$allowedExt = ['xlsx', 'docx', 'pptx', 'hwpx', 'pdf'];
$ext = strtolower(pathinfo($file['name'], PATHINFO_EXTENSION));
if (!in_array($ext, $allowedExt)) {
    die('지원하지 않는 파일 형식입니다.');
}

// FastAPI 호출
$cfile = new CURLFile(
    $file['tmp_name'],
    $file['type'],
    $file['name']
);

$ch = curl_init('http://127.0.0.1:8000/api/detect');
curl_setopt_array($ch, [
    CURLOPT_POST           => true,
    CURLOPT_POSTFIELDS     => [
        'file'         => $cfile,
        'deletionMode' => 'mark',
        'useNer'       => 'false',
        'useAi'        => 'false',
        'userId'       => $_SESSION['user_id'],
    ],
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => 60,
]);

$response = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$result = json_decode($response, true);

if (!$result || !$result['success']) {
    $errMsg = $result['message'] ?? '알 수 없는 오류';
    die("비식별화 처리 실패: {$errMsg}");
}

// 결과 세션 저장 (다운로드 토큰 포함)
$_SESSION['detect_result'] = $result;

header('Location: /result.php');
```

### 9.2 결과 화면 렌더링

```php
<?php
// result.php

session_start();
$result = $_SESSION['detect_result'] ?? null;
if (!$result) {
    header('Location: /upload.php');
    exit;
}

$fileType   = $result['fileType'];
$applyMode  = $result['applyMode'];
$autoResults   = $result['autoResults'] ?? [];
$reviewTargets = $result['reviewTargets'] ?? [];
$summary    = $result['summary'];
$meta       = $result['metadata'];
?>
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><title>비식별화 결과</title></head>
<body>

<h1>비식별화 결과</h1>
<p>파일: <?= htmlspecialchars($meta['originalFilename']) ?></p>
<p>탐지: <?= $summary['autoTargetCount'] ?>건 / 위치: <?= $summary['totalLocations'] ?>건</p>

<?php if ($applyMode === 'applied'): ?>
  <!-- xlsx: 다운로드 버튼 -->
  <section>
    <h2>비식별화 완료</h2>
    <p>자동으로 비식별화된 파일을 다운로드하세요.</p>
    <?php
      $token = $result['downloadToken'];
      $dlUrl = "http://127.0.0.1:8000/api/download/{$token}";
    ?>
    <a href="/download.php?token=<?= urlencode($token) ?>">
      비식별화 파일 다운로드
    </a>
  </section>

<?php else: ?>
  <!-- guide 모드: 위치 안내 -->
  <section>
    <h2>자동 처리 항목</h2>
    <p>아래 위치의 정보를 원본 문서에서 직접 수정하세요.</p>

    <?php if ($fileType === 'pdf'): ?>
      <p class="notice">
        ⚠️ PDF는 직접 편집이 어려울 수 있습니다.<br>
        가능하면 원본 docx/hwpx 문서에서 수정 후 PDF로 다시 저장하세요.
      </p>
    <?php endif; ?>

    <table>
      <tr><th>위치</th><th>항목</th><th>원문</th><th>권장 결과</th></tr>
      <?php foreach ($autoResults as $item): ?>
        <tr>
          <td><?= htmlspecialchars($item['locationLabel']) ?></td>
          <td><?= htmlspecialchars($item['label']) ?></td>
          <td><?= htmlspecialchars($item['originalText'] ?? '') ?></td>
          <td><?= htmlspecialchars($item['appliedText'] ?? '') ?></td>
        </tr>
      <?php endforeach; ?>
    </table>
  </section>
<?php endif; ?>

<?php if (!empty($reviewTargets)): ?>
  <!-- AI 추천 검토 -->
  <section>
    <h2>AI 추천 검토 (<?= count($reviewTargets) ?>건)</h2>
    <p>아래 문장에 포함된 정보의 등급을 판단해주세요.</p>

    <form method="post" action="/feedback.php">
    <?php foreach ($reviewTargets as $idx => $rv): ?>
      <div class="review-item">
        <p><strong><?= htmlspecialchars($rv['locationLabel'] ?? '') ?></strong></p>
        <blockquote><?= htmlspecialchars($rv['context'] ?? '') ?></blockquote>
        <p>AI 추정: <strong><?= $rv['grade'] ?? '?' ?>급</strong>
           (<?= htmlspecialchars($rv['sensitiveCategory'] ?? '') ?>)</p>

        <?php
        $gradeOptions = [
            'C' => 'C급 (기밀) — 외부 AI 사용 불가',
            'S' => 'S급 (민감) — 비식별화 후 사용 가능',
            'O' => 'O급 (공개) — 그대로 사용 가능',
            'X' => '잘못된 탐지',
        ];
        foreach ($gradeOptions as $grade => $label):
            $checked   = ($grade === $rv['grade']) ? 'checked' : '';
            $isAi      = ($grade === $rv['grade']) ? ' (AI 추정)' : '';
            $gradeDesc = [
                'C' => '시스템 계정/비밀번호, IP/VLAN, 중요시설 도면 등',
                'S' => '개인정보, 입찰·계약·인사 관련 정보 등',
                'O' => 'C/S 외 모든 정보, 비식별화 완료 자료',
                'X' => '민감 정보가 없는 오탐지',
            ];
        ?>
          <label title="<?= $gradeDesc[$grade] ?>">
            <input type="radio"
                   name="grade[<?= $idx ?>]"
                   value="<?= $grade ?>"
                   <?= $checked ?>>
            <?= $label ?><?= $isAi ?>
          </label><br>
        <?php endforeach; ?>

        <!-- 피드백 전송용 hidden -->
        <input type="hidden" name="location[<?= $idx ?>]"
               value="<?= htmlspecialchars($rv['locationLabel'] ?? '') ?>">
        <input type="hidden" name="context[<?= $idx ?>]"
               value="<?= htmlspecialchars($rv['context'] ?? '') ?>">
        <input type="hidden" name="aiGrade[<?= $idx ?>]"
               value="<?= $rv['grade'] ?? '' ?>">
        <input type="hidden" name="fileType[<?= $idx ?>]"
               value="<?= $fileType ?>">
        <input type="hidden" name="category[<?= $idx ?>]"
               value="<?= htmlspecialchars($rv['sensitiveCategory'] ?? '') ?>">
      </div>
    <?php endforeach; ?>
      <button type="submit">판단 저장</button>
    </form>
  </section>
<?php endif; ?>

</body>
</html>
```

### 9.3 xlsx 다운로드 중계

```php
<?php
// download.php
// PHP가 FastAPI 파일을 받아 브라우저로 중계

session_start();
$token = $_GET['token'] ?? '';
if (!$token) die('토큰이 없습니다.');

$ch = curl_init("http://127.0.0.1:8000/api/download/{$token}");
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HEADER         => true,
    CURLOPT_TIMEOUT        => 30,
]);

$response  = curl_exec($ch);
$httpCode  = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
curl_close($ch);

if ($httpCode !== 200) {
    die('파일을 찾을 수 없습니다. 토큰이 만료되었거나 이미 다운로드했을 수 있습니다.');
}

$body = substr($response, $headerSize);

header('Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
header('Content-Disposition: attachment; filename="deidentified.xlsx"');
header('Content-Length: ' . strlen($body));
echo $body;
```

### 9.4 피드백 제출

```php
<?php
// feedback.php

session_start();
$grades    = $_POST['grade'] ?? [];
$locations = $_POST['location'] ?? [];
$contexts  = $_POST['context'] ?? [];
$aiGrades  = $_POST['aiGrade'] ?? [];
$fileTypes = $_POST['fileType'] ?? [];
$categories = $_POST['category'] ?? [];

foreach ($grades as $idx => $userGrade) {
    $payload = json_encode([
        'locationLabel'     => $locations[$idx] ?? '',
        'context'           => $contexts[$idx] ?? '',
        'aiGrade'           => $aiGrades[$idx] ?? null,
        'userGrade'         => $userGrade,
        'fileType'          => $fileTypes[$idx] ?? null,
        'sensitiveCategory' => $categories[$idx] ?? null,
        'userId'            => $_SESSION['user_id'] ?? null,
    ]);

    $ch = curl_init('http://127.0.0.1:8000/api/feedback');
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => $payload,
        CURLOPT_HTTPHEADER     => ['Content-Type: application/json'],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
    ]);
    curl_exec($ch);
    curl_close($ch);
}

header('Location: /complete.php');
```

---

## 10. 화면 UI 분기 정책

### guide 모드 (docx/pptx/hwpx/pdf)

```
원본 파일을 직접 수정해야 합니다.
아래 권장 결과를 참고해 원본 문서를 수정하세요.

[위치 목록 테이블]

[수정 완료로 표시]  [대상 아님]
```

### applied 모드 (xlsx)

```
자동으로 비식별화된 파일을 다운로드하세요.

[비식별화 파일 다운로드]
```

### PDF 추가 안내

```
⚠️ PDF는 직접 편집이 어려울 수 있습니다.
   가능하면 원본 docx/hwpx 문서에서 수정 후 PDF로 다시 저장하세요.
```

### reviewTargets (AI 추천 검토)

```
[AI 추천 검토] N건

위치: 3쪽 5번째 줄
문장: "입찰 평가표를 검토했습니다..."
AI 추정: S급 (AI_S)

⚪ C급 (기밀) — 외부 AI 사용 불가       → title로 설명 표시
🔵 S급 (민감) — 비식별화 후 사용 가능  (AI 추정)
⚪ O급 (공개) — 그대로 사용 가능
⚪ 잘못된 탐지

[판단 저장]
```

---

## 11. locationMeta 구조 (형식별)

PHP에서 위치를 직접 파싱해야 할 경우를 위한 참고 정보입니다.
일반적으로는 `locationLabel` 문자열로 표시하면 충분합니다.

| fileType | 주요 필드 |
|----------|-----------|
| pdf | `pageNo` (0-based), `lineNo` (0-based) |
| docx | `section` (body/table_cell), `paragraphNo`, `tableNo`, `rowNo`, `colNo` |
| pptx | `section` (shape_text/table_cell/notes), `slideNo`, `shapeNo`, `paragraphNo` |
| hwpx | `section` (body/table_cell), `sectionNo`, `paragraphNo` |
| xlsx | `sheetName`, `cellRef` (예: "B2") |

---

## 12. 협의 필요 사항

PHP 팀과 확인이 필요한 항목:

```text
□ FastAPI 서버 배포 위치 (같은 서버 vs 별도 서버)
□ 포트 번호 확정 (현재 8000)
□ 타임아웃 설정 (현재 60초, 대용량 파일 시 조정 필요)
□ 파일 크기 제한 (PHP upload_max_filesize와 맞춤)
□ 사용자 ID 전달 방식 (세션 키 이름)
□ 이력 저장 정책 (PHP DB에 저장 여부)
□ reviewTargets 피드백 저장 활성화 시점
□ 에러 화면 처리 방식
□ PDF 편집 안내 문구 확정
```
