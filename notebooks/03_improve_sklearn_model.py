import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

df = pd.read_csv("data/privacy_sentence_sample_v3.csv")

# ## 데이터 확인
# print(df.shape)
# print(df["label"].value_counts())
# print(df["category"].value_counts())
# print(df["cso_grade"].value_counts())

# ## 결측치, 중복확인, note는 상관없음
# print(df.isna().sum())
# print(df[df.duplicated("text")])

##
X = df["text"]
y = df["label"]

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

## 모델
model_v2 = Pipeline([
    ("tfidf", TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4)
    )),
    ("clf", LogisticRegression(
        max_iter=1000,
        class_weight="balanced"
    ))
])

## 학습
model_v2.fit(X_train, y_train)
joblib.dump(model_v2, "models/privacy_sentence_model_v2.pkl")

## 예측
y_pred = model_v2.predict(X_test)

## 평가
print("Accuracy:", accuracy_score(y_test, y_pred))
print(classification_report(y_test, y_pred, zero_division=0))

## 결과표
result_df = pd.DataFrame({
    "text": X_test.values,
    "actual": y_test.values,
    "predicted": y_pred
})

## 틀린 예측 확인
wrong_df = result_df[result_df["actual"] != result_df["predicted"]]
print(wrong_df)

## 미탐 확인
missed_df = result_df[
    (result_df["actual"].isin(["개인정보", "민감정보"])) &
    (result_df["predicted"] == "일반")
]

print(missed_df)

## 오탐 확인
false_alarm_df = result_df[
    (result_df["actual"] == "일반") &
    (result_df["predicted"].isin(["개인정보", "민감정보"]))
]

print(false_alarm_df)

## 성명 기반 문장 별도 테스트
name_test_samples = [
    "최지연 씨의 서류가 접수되었습니다",
    "박민호 님의 신청서가 처리되었습니다",
    "이서연 고객의 자료를 확인했습니다",
    "정우진 민원인의 접수 내역을 검토했습니다",
    "김하늘 담당자의 연락처가 변경되었습니다"
]

print(model_v2.predict(name_test_samples))

## 일반/민감정보 혼동 테스트
ambiguous_samples = [
    "교육 신청서가 접수되었습니다",
    "회의 자료 제출 서류를 확인했습니다",
    "진단서가 접수되었습니다",
    "장애인 등록 신청서가 접수되었습니다",
    "징계위원회 출석 통보서가 접수되었습니다"
]

print(model_v2.predict(ambiguous_samples))