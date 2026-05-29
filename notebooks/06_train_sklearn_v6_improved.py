"""
notebooks/06_train_sklearn_v6_improved.py

v5(LR+char) 대비 두 가지 개선 적용:
  개선2: LinearSVC (LR보다 고차원 sparse feature에서 유리)
  개선3: char_wb(2,4) + word(1,2) FeatureUnion

세 모델을 같은 train/test split으로 비교 후 최고 모델을 저장한다.
저장 경로: models/privacy_sentence_model_v5.pkl
"""

import joblib
import pandas as pd
from pathlib import Path
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_CSV  = PROJECT_ROOT / "data" / "privacy_sentence_sample_v6_merged.csv"
OUT_MODEL = PROJECT_ROOT / "models" / "privacy_sentence_model_v5.pkl"

LABEL_TO_SKL = {"C": "민감정보", "S": "개인정보", "O": "일반"}
SKL_TO_LABEL = {v: k for k, v in LABEL_TO_SKL.items()}
SKL_LABELS   = ["민감정보", "개인정보", "일반"]  # confusion matrix 순서


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

def build_baseline():
    """기존 v4: LR + char_wb(2,4)  (비교 기준)"""
    return Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))),
        ("clf",   LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])


def build_svc_char():
    """개선2: LinearSVC + char_wb(2,4)"""
    return Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))),
        ("clf",   CalibratedClassifierCV(
            LinearSVC(max_iter=2000, class_weight="balanced")
        )),
    ])


def build_svc_char_word():
    """개선2+3: LinearSVC + char_wb(2,4) & word(1,2) FeatureUnion"""
    return Pipeline([
        ("features", FeatureUnion([
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))),
            ("word", TfidfVectorizer(analyzer="word",    ngram_range=(1, 2),
                                     min_df=1)),
        ])),
        ("clf", CalibratedClassifierCV(
            LinearSVC(max_iter=2000, class_weight="balanced")
        )),
    ])


# ── 평가 ─────────────────────────────────────────────────────────────────

def evaluate(name: str, model, test_df: pd.DataFrame) -> float:
    y_true = test_df["skl_label"]
    y_pred = model.predict(test_df["text"])
    acc = accuracy_score(y_true, y_pred)

    print(f"\n{'='*52}")
    print(f"[{name}]  Accuracy: {acc:.4f}")
    print(classification_report(y_true, y_pred,
                                labels=SKL_LABELS, zero_division=0))

    print("Confusion matrix (행=실제, 열=예측):")
    cm = confusion_matrix(y_true, y_pred, labels=SKL_LABELS)
    header = "          " + "  ".join(f"{l:6s}" for l in SKL_LABELS)
    print(header)
    for label, row in zip(SKL_LABELS, cm):
        print(f"  {label:6s}  " + "  ".join(f"{v:6d}" for v in row))

    return acc


def test_false_positive_patterns(model) -> None:
    samples = [
        ("기간의 경과 등으로 비공개 필요성이 소멸된 정보",                         "O"),
        ("O 등급 C 등급",                                                           "O"),
        ("S 등급",                                                                   "O"),
        ("(비식별화 조치 내역 및 결과)",                                             "O"),
        ("5) S등급 데이터 비식별화 조치 결과 검토 및 승인",                         "O"),
        ("C등급은 외부 공개 시 기관에 중대한 피해를 줄 수 있는 기밀 정보입니다",   "O"),
        ("정보 등급별 외부 AI 활용 가능 여부를 확인하시기 바랍니다",               "O"),
        ("비공개 분류 기준 검토서를 제출했습니다",                                  "O"),
    ]
    print("\n[오탐 패턴 검증] (정답: O)")
    all_ok = True
    for text, expected in samples:
        pred_skl = model.predict([text])[0]
        pred_cso = SKL_TO_LABEL.get(pred_skl, pred_skl)
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
        ("기준 (LR + char)",              build_baseline),
        ("개선2 (SVC + char)",            build_svc_char),
        ("개선2+3 (SVC + char+word)",     build_svc_char_word),
    ]

    results: list[tuple[str, float, object]] = []
    for name, builder in configs:
        model = builder()
        model.fit(train_df["text"], train_df["skl_label"])
        acc = evaluate(name, model, test_df)
        results.append((name, acc, model))

    # 최고 모델 저장
    best_name, best_acc, best_model = max(results, key=lambda x: x[1])
    print(f"\n{'='*52}")
    print(f"최고 모델: [{best_name}]  Accuracy: {best_acc:.4f}")
    OUT_MODEL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, OUT_MODEL)
    print(f"저장: {OUT_MODEL}")

    print(f"\n{'='*52}")
    print("비교 요약:")
    for name, acc, _ in results:
        bar = "#" * int(acc * 40)
        marker = " ← 최고" if name == best_name else ""
        print(f"  {name:28s}  {acc:.4f}  {bar}{marker}")

    test_false_positive_patterns(best_model)


if __name__ == "__main__":
    main()
