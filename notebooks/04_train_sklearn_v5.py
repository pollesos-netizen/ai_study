"""privacy_sentence_sample_v5.csv로 sklearn 모델 재학습 → privacy_sentence_model_v3.pkl"""

import pandas as pd
import joblib
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix

PROJECT_ROOT = Path(__file__).resolve().parent.parent

df = pd.read_csv(PROJECT_ROOT / "data" / "privacy_sentence_sample_v5.csv")

# cso_grade → label 변환  (C→민감정보, S→개인정보, O→일반)
GRADE_TO_LABEL = {"C": "민감정보", "S": "개인정보", "O": "일반"}
df["label"] = df["cso_grade"].map(GRADE_TO_LABEL)

print("데이터 분포:")
print(df["label"].value_counts())
print()

X = df["text"]
y = df["label"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

model_v3 = Pipeline([
    ("tfidf", TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4)
    )),
    ("clf", LogisticRegression(
        max_iter=1000,
        class_weight="balanced"
    ))
])

model_v3.fit(X_train, y_train)

out_path = PROJECT_ROOT / "models" / "privacy_sentence_model_v3.pkl"
joblib.dump(model_v3, out_path)
print(f"모델 저장: {out_path}")

y_pred = model_v3.predict(X_test)

print(f"\nAccuracy: {accuracy_score(y_test, y_pred):.4f}")
print(classification_report(y_test, y_pred, zero_division=0))

# 오탐 피드백 패턴 테스트
false_positive_samples = [
    "기간의 경과 등으로 비공개 필요성이 소멸된 정보",
    "O 등급 C 등급",
    "S 등급",
    "(비식별화 조치 내역 및 결과)",
    "5) S등급 데이터 비식별화 조치 결과 검토 및 승인",
    "C등급은 외부 공개 시 기관에 중대한 피해를 줄 수 있는 기밀 정보입니다",
    "비공개 분류 기준 검토서를 제출했습니다",
    "정보 등급별 외부 AI 활용 가능 여부를 확인하시기 바랍니다",
]

print("\n[오탐 패턴 예측] (정답: 일반/O)")
classes = list(model_v3.classes_)
for text in false_positive_samples:
    pred = model_v3.predict([text])[0]
    probs = model_v3.predict_proba([text])[0]
    prob_str = "  ".join(f"{c}={p:.3f}" for c, p in zip(classes, probs))
    mark = "OK" if pred == "일반" else "NG"
    print(f"[{mark}] {pred:6s}  {prob_str}  | {text[:40]}")
