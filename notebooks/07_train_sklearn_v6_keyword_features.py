"""
notebooks/07_train_sklearn_v6_keyword_features.py

개선 내용:
  개선2  : LinearSVC (v5와 동일)
  개선3  : char_wb(2,4) + word(1,2) FeatureUnion (v5와 동일)
  개선4  : keywords.yaml 기반 키워드 지시자 피처 추가 (신규)
         → strong_procedural/s_business/ambiguous/weak 그룹별 매칭 수

세 모델을 같은 split으로 비교 후 최고 모델을 저장한다.
저장 경로: models/privacy_sentence_model_v6.pkl
"""

from __future__ import annotations

import re
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Any

import yaml
from scipy.sparse import hstack, csr_matrix
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_CSV     = PROJECT_ROOT / "data" / "privacy_sentence_sample_v6_merged.csv"
KEYWORDS_FILE = PROJECT_ROOT / "tools" / "keywords.yaml"
OUT_MODEL    = PROJECT_ROOT / "models" / "privacy_sentence_model_v6.pkl"

LABEL_TO_SKL = {"C": "민감정보", "S": "개인정보", "O": "일반"}
SKL_TO_LABEL = {v: k for k, v in LABEL_TO_SKL.items()}
SKL_LABELS   = ["민감정보", "개인정보", "일반"]


# ── 키워드 피처라이저 ──────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """공백 제거 + 소문자 + 전각→반각. extract_candidates.py와 동일 로직."""
    result = []
    for c in s:
        cp = ord(c)
        if 0xFF01 <= cp <= 0xFF5E:
            result.append(chr(cp - 0xFEE0))
        elif c == "　":
            result.append(" ")
        else:
            result.append(c)
    return re.sub(r"\s+", "", "".join(result)).lower()


def _count_matches(norm_text: str, keywords: list[str]) -> int:
    seen: set[str] = set()
    count = 0
    for kw in sorted(keywords or [], key=lambda x: len(_normalize(x)), reverse=True):
        nk = _normalize(kw)
        if nk and nk not in seen and nk in norm_text:
            seen.add(nk)
            count += 1
    return count


class KeywordFeaturizer(BaseEstimator, TransformerMixin):
    """
    keywords.yaml 그룹별 매칭 수를 밀집 수치 행렬로 변환.

    피처 4개 (출력 shape: n_samples × 4):
      0: strong_procedural 매칭 수  → C의 강한 신호
      1: s_business_sensitive 매칭 수 → S의 강한 신호
      2: ambiguous_action 매칭 수   → 맥락 의존 신호
      3: weak 매칭 수               → 약한 보조 신호
    """

    def __init__(self, keywords_path: Path = KEYWORDS_FILE):
        self.keywords_path = keywords_path
        self._kw: dict[str, list[str]] = {}

    def _load(self) -> None:
        if self._kw:
            return
        with self.keywords_path.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        tracks = cfg.get("ai_tracks", {})
        self._kw = {
            "strong":    tracks.get("strong_procedural", {}).get("keywords", []),
            "s_biz":     tracks.get("s_business_sensitive", {}).get("keywords", []),
            "ambiguous": tracks.get("ambiguous_action", {}).get("keywords", []),
            "weak":      cfg.get("weak", {}).get("keywords", []),
        }

    def fit(self, X, y=None):
        self._load()
        return self

    def transform(self, X) -> csr_matrix:
        self._load()
        rows = []
        for text in X:
            nt = _normalize(str(text))
            rows.append([
                _count_matches(nt, self._kw["strong"]),
                _count_matches(nt, self._kw["s_biz"]),
                _count_matches(nt, self._kw["ambiguous"]),
                _count_matches(nt, self._kw["weak"]),
            ])
        return csr_matrix(np.array(rows, dtype=float))


# ── 데이터 ────────────────────────────────────────────────────────────────

def load_and_split():
    df = pd.read_csv(DATA_CSV, encoding="utf-8-sig")
    df["augmented"] = df["augmented"].fillna("0").astype(str).str.strip()
    df["label"]     = df["label"].str.strip().str.upper()
    df["skl_label"] = df["label"].map(LABEL_TO_SKL)

    original  = df[df["augmented"] == "0"]
    augmented = df[df["augmented"] == "1"]

    orig_train, orig_test = train_test_split(
        original, test_size=0.2, random_state=42, stratify=original["skl_label"]
    )
    train = pd.concat([orig_train, augmented], ignore_index=True)
    test  = orig_test

    print(f"전체: {len(df)}건  C:{(df.label=='C').sum()}  S:{(df.label=='S').sum()}  O:{(df.label=='O').sum()}")
    print(f"train: {len(train)}건 (원본 {len(orig_train)} + 증강 {len(augmented)})")
    print(f"test : {len(test)}건 (원본만)")
    return train, test


# ── 모델 정의 ─────────────────────────────────────────────────────────────

def _svc():
    return CalibratedClassifierCV(LinearSVC(max_iter=2000, class_weight="balanced"))


def build_v4_baseline():
    """v4: LR + char_wb(2,4)"""
    return Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))),
        ("clf",   LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])


def build_v5_svc_char():
    """v5: SVC + char_wb(2,4)"""
    return Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))),
        ("clf",   _svc()),
    ])


def build_v6_keyword():
    """v6: SVC + char_wb + word + keyword 피처"""
    return Pipeline([
        ("features", FeatureUnion([
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))),
            ("word", TfidfVectorizer(analyzer="word",    ngram_range=(1, 2), min_df=1)),
            ("kw",   KeywordFeaturizer()),
        ])),
        ("clf", _svc()),
    ])


# ── 평가 ─────────────────────────────────────────────────────────────────

def evaluate(name: str, model, test_df: pd.DataFrame) -> float:
    y_true = test_df["skl_label"]
    y_pred = model.predict(test_df["text"])
    acc = accuracy_score(y_true, y_pred)

    print(f"\n{'='*54}")
    print(f"[{name}]  Accuracy: {acc:.4f}")
    print(classification_report(y_true, y_pred, labels=SKL_LABELS, zero_division=0))

    print("Confusion matrix (행=실제, 열=예측):")
    cm = confusion_matrix(y_true, y_pred, labels=SKL_LABELS)
    header = "          " + "  ".join(f"{l:6s}" for l in SKL_LABELS)
    print(header)
    for label, row in zip(SKL_LABELS, cm):
        print(f"  {label:6s}  " + "  ".join(f"{v:6d}" for v in row))
    return acc


def test_false_positive_patterns(model) -> None:
    samples = [
        ("기간의 경과 등으로 비공개 필요성이 소멸된 정보",                           "O"),
        ("O 등급 C 등급",                                                             "O"),
        ("S 등급",                                                                     "O"),
        ("(비식별화 조치 내역 및 결과)",                                               "O"),
        ("5) S등급 데이터 비식별화 조치 결과 검토 및 승인",                           "O"),
        ("C등급은 외부 공개 시 기관에 중대한 피해를 줄 수 있는 기밀 정보입니다",     "O"),
        ("정보 등급별 외부 AI 활용 가능 여부를 확인하시기 바랍니다",                 "O"),
        ("비공개 분류 기준 검토서를 제출했습니다",                                    "O"),
    ]
    print("\n[오탐 패턴 검증] (정답: O)")
    all_ok = True
    for text, expected in samples:
        pred_cso = SKL_TO_LABEL.get(model.predict([text])[0], "?")
        mark = "OK" if pred_cso == expected else "NG"
        if pred_cso != expected:
            all_ok = False
        print(f"  [{mark}] {pred_cso}  | {text[:50]}")
    if all_ok:
        print("  전부 O 정확히 예측")


# ── 메인 ─────────────────────────────────────────────────────────────────

def main():
    train_df, test_df = load_and_split()

    configs = [
        ("v4 기준 (LR + char)",           build_v4_baseline),
        ("v5 (SVC + char)",               build_v5_svc_char),
        ("v6 (SVC + char+word+keyword)",  build_v6_keyword),
    ]

    results: list[tuple[str, float, Any]] = []
    for name, builder in configs:
        model = builder()
        model.fit(train_df["text"], train_df["skl_label"])
        acc = evaluate(name, model, test_df)
        results.append((name, acc, model))

    best_name, best_acc, best_model = max(results, key=lambda x: x[1])

    print(f"\n{'='*54}")
    print("비교 요약:")
    for name, acc, _ in results:
        bar = "#" * int(acc * 40)
        marker = " <- 최고" if name == best_name else ""
        print(f"  {name:36s}  {acc:.4f}  {bar}{marker}")

    OUT_MODEL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, OUT_MODEL)
    print(f"\n최고 모델 저장: {OUT_MODEL}  [{best_name}  {best_acc:.4f}]")

    test_false_positive_patterns(best_model)


if __name__ == "__main__":
    main()
