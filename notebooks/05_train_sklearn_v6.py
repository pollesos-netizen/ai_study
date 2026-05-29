"""
notebooks/05_train_sklearn_v6.py

v6 merged 데이터셋으로 sklearn 모델 재학습 → models/privacy_sentence_model_v4.pkl

학습 규칙:
  - augmented=1 행은 train 전용, test 세트에서 제외 (성능 부풀림 방지)
  - class_weight='balanced' (S 과다 보정)
  - TF-IDF char_wb ngram(2,4) + LogisticRegression (v3 구조 유지)
"""

import joblib
import pandas as pd
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_CSV  = PROJECT_ROOT / "data" / "privacy_sentence_sample_v6_merged.csv"
OUT_MODEL = PROJECT_ROOT / "models" / "privacy_sentence_model_v4.pkl"

# sklearn 레이블 (학습용) ↔ C/S/O (API용) 매핑
LABEL_TO_SKL = {"C": "민감정보", "S": "개인정보", "O": "일반"}
SKL_TO_LABEL = {v: k for k, v in LABEL_TO_SKL.items()}


def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_CSV, encoding="utf-8-sig")
    df["augmented"] = df["augmented"].fillna("0").astype(str).str.strip()
    df["label"] = df["label"].str.strip().str.upper()
    # sklearn 학습용 레이블 컬럼
    df["skl_label"] = df["label"].map(LABEL_TO_SKL)
    return df


def split_data(df: pd.DataFrame):
    """
    원본(augmented=0)을 train/test로 분리하고,
    train에만 증강(augmented=1)을 합친다.
    """
    original = df[df["augmented"] == "0"].copy()
    augmented = df[df["augmented"] == "1"].copy()

    orig_train, orig_test = train_test_split(
        original,
        test_size=0.2,
        random_state=42,
        stratify=original["skl_label"],
    )

    train = pd.concat([orig_train, augmented], ignore_index=True)
    test = orig_test  # 원본만

    print(f"train: {len(train)}건 (원본 {len(orig_train)} + 증강 {len(augmented)})")
    print(f"test : {len(test)}건 (원본만)")
    print(f"train 분포: {dict(train['label'].value_counts())}")
    print(f"test  분포: {dict(test['label'].value_counts())}")
    return train, test


def train(train_df: pd.DataFrame) -> Pipeline:
    model = Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
        )),
        ("clf", LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
        )),
    ])
    model.fit(train_df["text"], train_df["skl_label"])
    return model


def evaluate(model: Pipeline, test_df: pd.DataFrame) -> None:
    y_true = test_df["skl_label"]
    y_pred = model.predict(test_df["text"])

    print(f"\nAccuracy: {accuracy_score(y_true, y_pred):.4f}")
    print(classification_report(y_true, y_pred, zero_division=0))

    print("Confusion matrix (행=실제, 열=예측):")
    labels = ["민감정보", "개인정보", "일반"]
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    header = "          " + "  ".join(f"{l:6s}" for l in labels)
    print(header)
    for label, row in zip(labels, cm):
        print(f"  {label:6s}  " + "  ".join(f"{v:6d}" for v in row))


def test_false_positive_patterns(model: Pipeline) -> None:
    """v5 오탐 패턴이 v4 모델에서도 해소됐는지 확인."""
    samples = [
        ("기간의 경과 등으로 비공개 필요성이 소멸된 정보",     "O"),
        ("O 등급 C 등급",                                       "O"),
        ("S 등급",                                               "O"),
        ("(비식별화 조치 내역 및 결과)",                         "O"),
        ("5) S등급 데이터 비식별화 조치 결과 검토 및 승인",     "O"),
        ("C등급은 외부 공개 시 기관에 중대한 피해를 줄 수 있는 기밀 정보입니다", "O"),
        ("정보 등급별 외부 AI 활용 가능 여부를 확인하시기 바랍니다", "O"),
        ("비공개 분류 기준 검토서를 제출했습니다",              "O"),
    ]

    print("\n[오탐 패턴 검증] (정답: O)")
    classes = list(model.classes_)
    all_ok = True
    for text, expected_cso in samples:
        skl_pred = model.predict([text])[0]
        cso_pred = SKL_TO_LABEL.get(skl_pred, skl_pred)
        probs = model.predict_proba([text])[0]
        prob_str = "  ".join(f"{c}={p:.3f}" for c, p in zip(classes, probs))
        mark = "OK" if cso_pred == expected_cso else "NG"
        print(f"  [{mark}] {cso_pred}  {prob_str}  | {text[:45]}")
        if cso_pred != expected_cso:
            all_ok = False
    if all_ok:
        print("  오탐 패턴 전부 O로 정확히 예측")


def main() -> None:
    print(f"데이터: {DATA_CSV}")
    df = load_data()
    print(f"전체: {len(df)}건  C:{(df['label']=='C').sum()}  "
          f"S:{(df['label']=='S').sum()}  O:{(df['label']=='O').sum()}")
    print(f"augmented 분포: {dict(df['augmented'].value_counts())}")

    train_df, test_df = split_data(df)
    model = train(train_df)

    OUT_MODEL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, OUT_MODEL)
    print(f"\n모델 저장: {OUT_MODEL}")

    evaluate(model, test_df)
    test_false_positive_patterns(model)


if __name__ == "__main__":
    main()
