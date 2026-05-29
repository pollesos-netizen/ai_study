#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_text_for_training.py
검수 완료된 후보 CSV의 text 컬럼을 AI 학습용으로 정제한다.

정제 대상 (AI 학습을 방해하는 노이즈):
    1. 원문자 글머리 기호: ① ② ③ ... ⑮, ⓐ ⓑ ⓒ, ◯ ○ ● ▪ ■ □ 등
    2. PUA(사제영역) 깨진 문자: 한글 워드 글머리 기호가 깨진 \uF000~\uF0FF
    3. 슬래시(/)로 표현된 줄바꿈/셀구분 → 공백으로 (단, 의미있는 슬래시는 보존 시도)
    4. 중복 공백 정규화, 앞뒤 공백 제거
    5. #NAME? 같은 엑셀 수식 오류 행 → 표시(원본 복구 필요)

원칙:
    - 원본 text는 'text_raw'로 보존하고, 정제 결과를 'text'에 넣는다(되돌릴 수 있게).
    - 의미 손실 최소화: 슬래시는 무조건 삭제가 아니라 "공백+슬래시+공백"이나
      "줄바꿈성 슬래시"만 공백으로. 약어 슬래시(S/S, A/S, I/O 등)는 보존.

사용법:
    python clean_text_for_training.py 입력.csv
    python clean_text_for_training.py 입력.csv -o 출력.csv
    python clean_text_for_training.py 입력.csv --col text   # 정제할 컬럼명 지정
"""

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

# 1) 원문자/글머리 기호 — 공백으로 치환 후 정리
#    원문자 유니코드 영역: U+2460~U+24FF (①②③...⑮⓪ⓐⓑ...)
#    기타 글머리: ◯○●◦▪▫■□◆◇★☆※·∙•
BULLET_CHARS = "◯○●◦▪▫■□◆◇★☆※·∙•‣⁃◈◐◑"
ENCLOSED_RANGE = (0x2460, 0x24FF)   # 원문자
PUA_RANGE = (0xF000, 0xF0FF)        # 사제영역(깨진 글머리)

# 보존할 약어 슬래시 (이 패턴의 슬래시는 지우지 않음)
#  - 영문약어/숫자 사이: S/S, A/S, I/O, R/n, TX/RX, 1/2 등
ABBREV_SLASH = re.compile(r'(?<=[A-Za-z0-9가-힣])/(?=[A-Za-z0-9가-힣])')


def strip_bullets(text: str) -> str:
    """원문자·PUA·글머리기호를 공백으로 치환."""
    out = []
    for ch in text:
        cp = ord(ch)
        if ENCLOSED_RANGE[0] <= cp <= ENCLOSED_RANGE[1]:
            out.append(" ")
        elif PUA_RANGE[0] <= cp <= PUA_RANGE[1]:
            out.append(" ")
        elif ch in BULLET_CHARS:
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def normalize_slashes(text: str) -> str:
    """
    줄바꿈/셀구분으로 쓰인 슬래시만 공백으로.
    약어성 슬래시(S/S, R/n 등)는 임시 토큰으로 보호한 뒤 복원.
    """
    # 약어 슬래시를 임시 토큰으로 보호
    protected = []
    def _protect(m):
        protected.append(m.group(0))
        return f"\x00{len(protected)-1}\x00"
    tmp = ABBREV_SLASH.sub(_protect, text)

    # 남은 슬래시(= 줄바꿈/구분용)는 공백으로
    tmp = tmp.replace("/", " ")

    # 보호 토큰 복원
    def _restore(m):
        return protected[int(m.group(1))]
    tmp = re.sub(r"\x00(\d+)\x00", _restore, tmp)
    return tmp


def clean_text(text: str) -> str:
    if text is None:
        return ""
    # 엑셀 수식 오류 — 복구 불가, 표시만
    if text.strip() in ("#NAME?", "#REF!", "#VALUE!", "#DIV/0!", "#N/A"):
        return "[CORRUPTED_EXCEL_FORMULA]"

    t = unicodedata.normalize("NFC", text)   # 유니코드 정규화
    t = strip_bullets(t)                     # 원문자/글머리 제거
    t = normalize_slashes(t)                 # 슬래시 정리
    t = t.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    # 괄호 안 빈칸 정리: "( )" → 제거, "(  내용 )" → "(내용)"
    t = re.sub(r"\(\s+", "(", t)
    t = re.sub(r"\s+\)", ")", t)
    t = re.sub(r"\(\s*\)", "", t)            # 빈 괄호 제거
    # 중복 공백 → 1칸, 앞뒤 정리
    t = re.sub(r"\s+", " ", t).strip()
    # 문장 끝 고립된 구두점 정리
    t = re.sub(r"\s+([.,)])", r"\1", t)
    return t


def main():
    ap = argparse.ArgumentParser(description="후보 CSV text를 AI 학습용으로 정제")
    ap.add_argument("input", help="입력 CSV")
    ap.add_argument("-o", "--output", help="출력 CSV (기본: 입력명_cleaned.csv)")
    ap.add_argument("--col", default="text", help="정제할 컬럼명 (기본: text)")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output) if args.output else in_path.with_name(in_path.stem + "_cleaned.csv")

    rows = list(csv.DictReader(open(in_path, encoding="utf-8-sig")))
    if not rows:
        print("[오류] 빈 파일", file=sys.stderr); sys.exit(1)
    if args.col not in rows[0]:
        print(f"[오류] '{args.col}' 컬럼 없음. 컬럼: {list(rows[0].keys())}", file=sys.stderr); sys.exit(1)

    fieldnames = list(rows[0].keys())
    # text_raw 컬럼을 text 바로 뒤에 추가(원본 보존)
    if "text_raw" not in fieldnames:
        idx = fieldnames.index(args.col)
        fieldnames.insert(idx + 1, "text_raw")

    n_changed = 0
    n_corrupted = 0
    for r in rows:
        raw = r[args.col]
        r["text_raw"] = raw
        cleaned = clean_text(raw)
        if cleaned == "[CORRUPTED_EXCEL_FORMULA]":
            n_corrupted += 1
        if cleaned != raw:
            n_changed += 1
        r[args.col] = cleaned

    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"[완료] {out_path}")
    print(f"  전체 {len(rows)}행 / 정제됨 {n_changed}행 / 엑셀오류(복구필요) {n_corrupted}행")
    print(f"  원본은 'text_raw' 컬럼에 보존. 학습 시 '{args.col}' 컬럼 사용.")
    if n_corrupted:
        print(f"  ⚠️ [CORRUPTED_EXCEL_FORMULA] {n_corrupted}행은 원본이 손실됨 "
              f"— 원본 CSV(candidates_ai.csv)에서 text를 다시 가져오거나 학습에서 제외.")


if __name__ == "__main__":
    main()
