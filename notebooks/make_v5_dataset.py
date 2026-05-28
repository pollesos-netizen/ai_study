"""privacy_sentence_sample_v4.csv에 49건을 추가해 v5를 생성한다.

추가 내용:
  - 오탐 피드백  9건 (O): feedback_2026-05-28.json의 오탐 문장
  - 메타 문장   20건 (O): 비식별화 기준·절차 설명 문장 (AI 오탐 방지용)
  - C급 보강   20건 (C): 보안/계약/운용 등 기밀 문장
"""

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "data" / "privacy_sentence_sample_v4.csv"
DST = PROJECT_ROOT / "data" / "privacy_sentence_sample_v5.csv"

# ── 기존 데이터 로드 ──────────────────────────────────────────
rows = list(csv.DictReader(SRC.open(encoding="utf-8-sig")))
fieldnames = list(rows[0].keys())
next_id = len(rows) + 1  # 190

# ── 행 생성 헬퍼 ──────────────────────────────────────────────
def o_meta(id_, text, note):
    return {
        "id": id_, "text": text,
        "has_personal": "N", "has_sensitive_legal": "N", "has_sensitive_business": "N",
        "sensitive_category": "분류설명",
        "cso_grade": "O",
        "deidentify_method": "해당 없음",
        "is_direct_sensitive_text": "N",
        "is_document_sensitive_signal": "N",
        "indicated_sensitive_category": "해당 없음",
        "note": note,
    }

def c_biz(id_, text, category, method, note):
    return {
        "id": id_, "text": text,
        "has_personal": "N", "has_sensitive_legal": "N", "has_sensitive_business": "Y",
        "sensitive_category": category,
        "cso_grade": "C",
        "deidentify_method": method,
        "is_direct_sensitive_text": "Y",
        "is_document_sensitive_signal": "N",
        "indicated_sensitive_category": "해당 없음",
        "note": note,
    }

fp_note = "AI 오탐 피드백 직접 변환 / 비식별화 기준 설명 문장 / 메타 문장 음성 샘플"
meta_note = "비식별화 기준·절차 설명 합성 문장 / AI 오탐 방지용 음성 샘플"
c_note = "업무상 민감정보 / is_direct_sensitive_text 정의 재정의에 따라 직접 보호 대상"

# ── 1. 오탐 피드백 9건 → O ────────────────────────────────────
feedback_texts = [
    "기간의 경과 등으로 비공개 필요성이 소멸된 정보",
    "특정 법령이나 지침에서 비공개로 명시된 대테러 계획, 국가 중요시설 보호계획 원문 등",
    "O 등급 C 등급",
    "벤더 계약서 부속 설계/기술자료, 외주 유지보수 용역사가 제공한 독점적 점검 매뉴얼, 부품 단가 및 원가 내역, 제안서 원문",
    "관제 지시 및 운전 취급 기록 상세 위치 정밀도 하향(예: 특정 좌표 → 구간 단위 제공)",
    "모델명, 네트워크 IP, 포트 노출되어 위험 모델명 등 장비식별자 삭제",
    "5) S등급 데이터 비식별화 조치 결과 검토 및 승인",
    "S 등급",
    "(비식별화 조치 내역 및 결과)",
]

new_rows = []
for text in feedback_texts:
    new_rows.append(o_meta(next_id, text, fp_note))
    next_id += 1

# ── 2. 메타 문장 합성 20건 → O ───────────────────────────────
meta_texts = [
    "C등급은 외부 공개 시 기관에 중대한 피해를 줄 수 있는 기밀 정보입니다",
    "S등급 정보는 비식별화 처리 후 제한적으로 공유할 수 있습니다",
    "O등급 정보는 일반 업무에 활용 가능한 공개 수준의 정보입니다",
    "비공개 정보의 등급별 처리 기준을 안내드립니다",
    "C급 정보의 외부 유출 시 법적 제재를 받을 수 있습니다",
    "개인정보 보호 조치 결과를 검토했습니다",
    "민감정보 분류 기준에 따라 등급을 부여합니다",
    "비식별화 대상 항목을 확인하여 조치 방법을 선택해 주세요",
    "정보 등급별 외부 AI 활용 가능 여부를 확인하시기 바랍니다",
    "C등급 항목은 삭제 또는 비식별화 처리가 필요합니다",
    "개인정보 및 민감정보 처리 방침에 따라 조치합니다",
    "S등급 정보의 마스킹 처리 기준을 검토했습니다",
    "비공개 분류 기준 검토서를 제출했습니다",
    "정보 보호 등급 분류 지침을 공유드립니다",
    "C급 기밀 정보의 보존 기간 기준을 안내드립니다",
    "민감정보 비식별화 절차 안내서를 첨부합니다",
    "개인정보 삭제 또는 마스킹 처리 방법을 안내드립니다",
    "정보 등급 분류표를 참고하여 처리 바랍니다",
    "비공개 정보 취급 지침에 따라 처리했습니다",
    "S급 데이터 처리 절차에 따라 비식별화 조치를 완료했습니다",
]

for text in meta_texts:
    new_rows.append(o_meta(next_id, text, meta_note))
    next_id += 1

# ── 3. C급 보강 20건 ─────────────────────────────────────────
c_additions = [
    # 보안정보 5건
    ("내부망 구성도 및 서버 IP 목록을 첨부합니다",           "보안정보", "삭제 또는 비식별화"),
    ("방화벽 정책 설정값을 공유드립니다",                     "보안정보", "삭제 또는 비식별화"),
    ("시스템 침해 탐지 이력을 보고드립니다",                  "보안정보", "삭제 또는 요약"),
    ("네트워크 취약점 점검 결과 상세 내역을 전달했습니다",    "보안정보", "삭제 또는 비식별화"),
    ("보안 시스템 접근 권한 목록을 첨부합니다",               "보안정보", "삭제 또는 비식별화"),
    # 계약/원가정보 5건
    ("외주업체 협상 최저가 기준을 내부 검토했습니다",         "계약정보", "삭제 또는 범주화"),
    ("예비가격 산정 결과를 부서장에게 보고했습니다",          "예산/원가정보", "삭제 또는 범주화"),
    ("계약 단가 인상 협의 내용을 기록했습니다",               "계약정보", "삭제 또는 범주화"),
    ("하도급 계약 원가 명세서를 첨부합니다",                  "계약정보", "삭제 또는 범주화"),
    ("입찰 예정 가격 산출 근거를 검토했습니다",               "예산/원가정보", "삭제 또는 범주화"),
    # 운용/사고 5건
    ("관제실 비상 대응 매뉴얼 원본을 공유드립니다",           "운영/유지보수정보", "삭제 또는 요약"),
    ("사고 처리 전말서 원본을 첨부합니다",                    "장애/사고대응", "삭제 또는 요약"),
    ("역사 CCTV 설치 위치 상세도를 전달했습니다",             "보안정보", "삭제 또는 비식별화"),
    ("비상 시 운영 통제 기준을 공유합니다",                   "운영/유지보수정보", "삭제 또는 요약"),
    ("내부 보안 감사 결과 상세 내역을 검토했습니다",          "감사/법무정보", "삭제 또는 요약"),
    # 인사/기타 5건
    ("이사회 비공개 안건 자료를 배포했습니다",                "계획/전략정보", "삭제 또는 요약"),
    ("임직원 급여 테이블 원본을 인사팀에 전달했습니다",       "인사정보", "삭제 또는 비식별화"),
    ("기관 미공개 중장기 발전 계획서를 검토했습니다",         "계획/전략정보", "삭제 또는 요약"),
    ("위기 대응 시나리오 원문을 공유드립니다",                "운영/유지보수정보", "삭제 또는 요약"),
    ("노선 운행 중단 결정 관련 내부 검토안을 전달했습니다",   "계획/전략정보", "삭제 또는 요약"),
]

for text, cat, method in c_additions:
    new_rows.append(c_biz(next_id, text, cat, method, c_note))
    next_id += 1

# ── 저장 ─────────────────────────────────────────────────────
all_rows = rows + new_rows

with DST.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)

from collections import Counter
grades = Counter(r["cso_grade"] for r in all_rows)
print(f"저장 완료: {DST}")
print(f"총 {len(all_rows)}건  C:{grades['C']}  S:{grades['S']}  O:{grades['O']}")
print(f"추가: {len(new_rows)}건 (오탐피드백 9 + 메타문장 20 + C급보강 20)")
