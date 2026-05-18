import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

import joblib

df = pd.read_csv("data/privacy_sentence_sample.csv")
## df.head()

## 라벨 분포 확인
x = df["text"]
y = df["label"]

x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42, stratify=y)   
# print("학습 라벨 분포")
# print(y_train.value_counts())

# print("테스트 라벨 분포")
# print(y_test.value_counts())

## 모델 생성
model = Pipeline([
    ("tfidf", TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
    )),
    ("clf", LogisticRegression(max_iter=1000, class_weight="balanced"))
])

## 학습
model.fit(x_train, y_train)
## 예측
y_pred = model.predict(x_test)

## 모델 평가

## 정확도 확인
accuracy = accuracy_score(y_test, y_pred)
print("Accuracy:", accuracy)

## 상세 평가
print(classification_report(y_test, y_pred, zero_division=0))

# pd. Series(y_pred).value_counts()

# result_df = pd.DataFrame({
#     "text": x_test.values,
#     "actual": y_test.values,
#     "predicted": y_pred
# })

# print("전체 예측 결과")
# print(result_df)

# print("\n실제 개인정보인 문장")
# print(result_df[result_df["actual"] == "개인정보"])

# print("\n틀린 예측")
# wrong_df = result_df[result_df["actual"] != result_df["predicted"]]
# print(wrong_df)

# print("\n미탐: 개인정보/민감정보인데 일반으로 예측")
# missed_df = result_df[
#     (result_df["actual"].isin(["개인정보", "민감정보"])) &
#     (result_df["predicted"] == "일반")
# ]
# print(missed_df)

# print("\n오탐: 일반인데 개인정보/민감정보로 예측")
# false_alarm_df = result_df[
#     (result_df["actual"] == "일반") &
#     (result_df["predicted"].isin(["개인정보", "민감정보"]))
# ]
# print(false_alarm_df)

# joblib.dump(model, "models/privacy_sentence_model.pkl")

# loaded_model = joblib.load("models/privacy_sentence_model.pkl")   

# samples = [
#     "회의는 오후 3시에 진행됩니다",
#     "김민수 고객에게 연락 바랍니다",
#     "진단서 사본이 첨부되었습니다",
#     "네트워크 장애 진단 결과를 공유합니다",
#     "장애인 등록 관련 서류를 제출했습니다",
#     "근무평정 D등급으로 조정되었습니다"
# ]

# print(loaded_model.predict(samples))

