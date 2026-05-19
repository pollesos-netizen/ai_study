"""
8주차 scikit-learn 모델과 TensorFlow/Keras 모델 비교 스크립트

목적:
- 같은 데이터셋(data/privacy_sentence_sample_v4.csv)을 기준으로
  scikit-learn TF-IDF + LogisticRegression 모델과
  TensorFlow/Keras char 모델의 C/S/O 예측 결과를 비교합니다.

비교 방식:
1. CSV에서 text, cso_grade를 읽습니다.
2. 05_train_tensorflow_cso_model.py와 동일한 seed/ratio로 검증 데이터를 분리합니다.
3. scikit-learn 모델은 학습 데이터로 새로 학습합니다.
4. Keras 모델은 models/privacy_cso_char_keras_model.keras에서 불러옵니다.
5. 같은 검증 데이터에 대해 정확도, 혼동행렬, 등급별 재현율, 오분류 목록을 비교합니다.

입력:
- data/privacy_sentence_sample_v4.csv
- models/privacy_cso_char_keras_model.keras

출력:
- reports/week8_compare_model_summary.csv
- reports/week8_compare_misclassified.csv

실행:
    python notebooks/07_compare_sklearn_tensorflow.py
"""

from __future__ import annotations

import csv
import os
import random
from collections import Counter
from pathlib import Path
from typing import Iterable

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import numpy as np
import tensorflow as tf
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix


keras = tf.keras


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "privacy_sentence_sample_v4.csv"
KERAS_MODEL_PATH = PROJECT_ROOT / "models" / "privacy_cso_char_keras_model.keras"

REPORT_DIR = PROJECT_ROOT / "reports"
SUMMARY_PATH = REPORT_DIR / "week8_compare_model_summary.csv"
MISCLASSIFIED_PATH = REPORT_DIR / "week8_compare_misclassified.csv"

RANDOM_SEED = 42
VALIDATION_RATIO = 0.2

GRADE_TO_ID = {
    "C": 0,
    "S": 1,
    "O": 2,
}

ID_TO_GRADE = {
    0: "C",
    1: "S",
    2: "O",
}

GRADES = ["C", "S", "O"]


def load_dataset(path: Path) -> tuple[list[str], list[int]]:
    """
    CSV에서 text와 cso_grade를 읽습니다.
    """
    if not path.exists():
        raise FileNotFoundError(f"데이터 파일을 찾을 수 없습니다: {path}")

    texts: list[str] = []
    labels: list[int] = []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        required_columns = {"text", "cso_grade"}
        missing_columns = required_columns - set(reader.fieldnames or [])

        if missing_columns:
            raise ValueError(f"필수 컬럼이 없습니다: {sorted(missing_columns)}")

        for row in reader:
            text = row["text"].strip()
            grade = row["cso_grade"].strip()

            if not text:
                continue

            if grade not in GRADE_TO_ID:
                raise ValueError(f"알 수 없는 cso_grade 값입니다: {grade}")

            texts.append(text)
            labels.append(GRADE_TO_ID[grade])

    return texts, labels


def train_test_split(
    texts: list[str],
    labels: list[int],
    validation_ratio: float = VALIDATION_RATIO,
    seed: int = RANDOM_SEED,
) -> tuple[list[str], list[int], list[str], list[int]]:
    """
    05_train_tensorflow_cso_model.py와 같은 방식으로 train/validation을 분리합니다.
    """
    if len(texts) != len(labels):
        raise ValueError("texts와 labels 길이가 다릅니다.")

    indices = list(range(len(texts)))
    random.Random(seed).shuffle(indices)

    validation_size = max(1, int(len(indices) * validation_ratio))
    validation_indices = set(indices[:validation_size])

    train_texts: list[str] = []
    train_labels: list[int] = []
    validation_texts: list[str] = []
    validation_labels: list[int] = []

    for idx in indices:
        if idx in validation_indices:
            validation_texts.append(texts[idx])
            validation_labels.append(labels[idx])
        else:
            train_texts.append(texts[idx])
            train_labels.append(labels[idx])

    return train_texts, train_labels, validation_texts, validation_labels


def print_label_distribution(title: str, labels: Iterable[int]) -> None:
    """
    라벨 분포를 출력합니다.
    """
    counter = Counter(ID_TO_GRADE[int(label)] for label in labels)
    print(title)
    for grade in GRADES:
        print(f"  - {grade}: {counter.get(grade, 0)}")


def train_sklearn_model(train_texts: list[str], train_labels: list[int]):
    """
    scikit-learn TF-IDF + LogisticRegression 모델을 학습합니다.
    """
    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=(2, 5),
        min_df=1,
    )

    train_x = vectorizer.fit_transform(train_texts)

    model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=RANDOM_SEED,
    )

    model.fit(train_x, train_labels)

    return vectorizer, model


def predict_sklearn(
    vectorizer: TfidfVectorizer,
    model: LogisticRegression,
    texts: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """
    scikit-learn 모델로 예측합니다.

    Returns:
        preds:
            예측 라벨 ID
        probs:
            각 등급 확률 배열
    """
    x = vectorizer.transform(texts)
    preds = model.predict(x)

    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(x)

        # LogisticRegression의 classes_ 순서가 [0,1,2]가 아닐 가능성에 대비
        ordered_probs = np.zeros((len(texts), len(GRADES)))
        for col_idx, class_id in enumerate(model.classes_):
            ordered_probs[:, int(class_id)] = probs[:, col_idx]
        probs = ordered_probs
    else:
        probs = np.zeros((len(texts), len(GRADES)))

    return preds, probs


def load_keras_model(path: Path = KERAS_MODEL_PATH) -> keras.Model:
    """
    저장된 Keras 모델을 불러옵니다.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Keras 모델 파일을 찾을 수 없습니다: {path}\n"
            "먼저 notebooks/05_train_tensorflow_cso_model.py를 실행해 모델을 저장하세요."
        )

    return keras.models.load_model(path)


def predict_keras(model: keras.Model, texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """
    Keras 모델로 예측합니다.
    """
    x = np.array(texts, dtype=object)
    probs = model.predict(x, verbose=0)
    preds = np.argmax(probs, axis=1)
    return preds, probs


def build_confusion(true_labels: list[int], pred_labels: Iterable[int]) -> np.ndarray:
    """
    C/S/O 순서의 혼동행렬을 반환합니다.
    """
    return confusion_matrix(true_labels, list(pred_labels), labels=[0, 1, 2])


def grade_recalls(confusion: np.ndarray) -> dict[str, float]:
    """
    등급별 재현율을 계산합니다.
    """
    recalls: dict[str, float] = {}

    for idx, grade in enumerate(GRADES):
        total = int(confusion[idx].sum())
        correct = int(confusion[idx, idx])
        recalls[grade] = correct / total if total else 0.0

    return recalls


def print_confusion(title: str, confusion: np.ndarray) -> None:
    """
    혼동행렬을 출력합니다.
    """
    print(f"\n{title}")
    print("실제\예측 | " + " | ".join(GRADES))
    print("-" * 32)

    for idx, grade in enumerate(GRADES):
        values = [str(int(value)) for value in confusion[idx]]
        print(f"{grade:^9} | " + " | ".join(f"{value:^3}" for value in values))


def print_model_summary(
    model_name: str,
    true_labels: list[int],
    pred_labels: Iterable[int],
) -> dict[str, str]:
    """
    모델별 요약 지표를 출력하고 dict로 반환합니다.
    """
    pred_labels = np.array(list(pred_labels))
    accuracy = accuracy_score(true_labels, pred_labels)
    confusion = build_confusion(true_labels, pred_labels)
    recalls = grade_recalls(confusion)

    print(f"\n=== {model_name} 결과 ===")
    print(f"정확도: {accuracy:.4f}")
    print_confusion("혼동행렬", confusion)

    print("\n등급별 재현율")
    for grade in GRADES:
        print(f"- {grade}: {recalls[grade]:.4f}")

    pred_counter = Counter(ID_TO_GRADE[int(label)] for label in pred_labels)
    print("\n예측 등급 분포")
    for grade in GRADES:
        print(f"- {grade}: {pred_counter.get(grade, 0)}")

    return {
        "model": model_name,
        "accuracy": f"{accuracy:.6f}",
        "recall_C": f"{recalls['C']:.6f}",
        "recall_S": f"{recalls['S']:.6f}",
        "recall_O": f"{recalls['O']:.6f}",
        "pred_C": str(pred_counter.get("C", 0)),
        "pred_S": str(pred_counter.get("S", 0)),
        "pred_O": str(pred_counter.get("O", 0)),
    }


def save_summary(rows: list[dict[str, str]], path: Path = SUMMARY_PATH) -> None:
    """
    모델 비교 요약 CSV를 저장합니다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = [
            "model",
            "accuracy",
            "recall_C",
            "recall_S",
            "recall_O",
            "pred_C",
            "pred_S",
            "pred_O",
        ]

        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n모델 비교 요약 저장 완료: {path}")


def save_misclassified_comparison(
    texts: list[str],
    true_labels: list[int],
    sklearn_preds: Iterable[int],
    sklearn_probs: np.ndarray,
    keras_preds: Iterable[int],
    keras_probs: np.ndarray,
    path: Path = MISCLASSIFIED_PATH,
) -> None:
    """
    scikit-learn 또는 Keras 중 하나라도 오분류한 문장을 CSV로 저장합니다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    sklearn_preds = list(sklearn_preds)
    keras_preds = list(keras_preds)

    rows: list[dict[str, str]] = []

    for index, (text, true_id, sk_pred, ke_pred) in enumerate(
        zip(texts, true_labels, sklearn_preds, keras_preds),
        start=1,
    ):
        sklearn_wrong = int(true_id) != int(sk_pred)
        keras_wrong = int(true_id) != int(ke_pred)

        if not sklearn_wrong and not keras_wrong:
            continue

        row = {
            "index": str(index),
            "text": text,
            "true_grade": ID_TO_GRADE[int(true_id)],
            "sklearn_pred": ID_TO_GRADE[int(sk_pred)],
            "keras_pred": ID_TO_GRADE[int(ke_pred)],
            "sklearn_wrong": "Y" if sklearn_wrong else "N",
            "keras_wrong": "Y" if keras_wrong else "N",
            "sklearn_prob_C": f"{sklearn_probs[index - 1][GRADE_TO_ID['C']]:.6f}",
            "sklearn_prob_S": f"{sklearn_probs[index - 1][GRADE_TO_ID['S']]:.6f}",
            "sklearn_prob_O": f"{sklearn_probs[index - 1][GRADE_TO_ID['O']]:.6f}",
            "keras_prob_C": f"{keras_probs[index - 1][GRADE_TO_ID['C']]:.6f}",
            "keras_prob_S": f"{keras_probs[index - 1][GRADE_TO_ID['S']]:.6f}",
            "keras_prob_O": f"{keras_probs[index - 1][GRADE_TO_ID['O']]:.6f}",
        }

        rows.append(row)

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = [
            "index",
            "text",
            "true_grade",
            "sklearn_pred",
            "keras_pred",
            "sklearn_wrong",
            "keras_wrong",
            "sklearn_prob_C",
            "sklearn_prob_S",
            "sklearn_prob_O",
            "keras_prob_C",
            "keras_prob_S",
            "keras_prob_O",
        ]

        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"오분류 비교 저장 완료: {path}")
    print(f"오분류 비교 행 수: {len(rows)}")


def print_side_by_side_examples(
    texts: list[str],
    true_labels: list[int],
    sklearn_preds: Iterable[int],
    keras_preds: Iterable[int],
    limit: int = 20,
) -> None:
    """
    두 모델의 예측을 나란히 출력합니다.
    """
    print("\n=== 모델별 예측 비교 예시 ===")

    count = 0

    for text, true_id, sk_pred, ke_pred in zip(texts, true_labels, sklearn_preds, keras_preds):
        sk_wrong = int(true_id) != int(sk_pred)
        ke_wrong = int(true_id) != int(ke_pred)

        if not sk_wrong and not ke_wrong:
            continue

        count += 1
        print(f"\n[{count}]")
        print(f"문장: {text}")
        print(f"실제 등급: {ID_TO_GRADE[int(true_id)]}")
        print(f"scikit-learn 예측: {ID_TO_GRADE[int(sk_pred)]} {'(오분류)' if sk_wrong else '(정분류)'}")
        print(f"Keras 예측: {ID_TO_GRADE[int(ke_pred)]} {'(오분류)' if ke_wrong else '(정분류)'}")

        if count >= limit:
            break

    if count == 0:
        print("두 모델 모두 오분류한 예시가 없습니다.")


def main() -> None:
    print("=== 8주차 scikit-learn vs TensorFlow/Keras 비교 ===")
    print(f"데이터 경로: {DATA_PATH}")
    print(f"Keras 모델 경로: {KERAS_MODEL_PATH}")

    texts, labels = load_dataset(DATA_PATH)

    print(f"\n전체 데이터 수: {len(texts)}")
    print_label_distribution("전체 라벨 분포:", labels)

    train_texts, train_labels, validation_texts, validation_labels = train_test_split(
        texts,
        labels,
    )

    print(f"\n학습 데이터 수: {len(train_texts)}")
    print(f"검증 데이터 수: {len(validation_texts)}")
    print_label_distribution("검증 라벨 분포:", validation_labels)

    print("\n=== scikit-learn 모델 학습 ===")
    sklearn_vectorizer, sklearn_model = train_sklearn_model(train_texts, train_labels)

    sklearn_preds, sklearn_probs = predict_sklearn(
        sklearn_vectorizer,
        sklearn_model,
        validation_texts,
    )

    print("\n=== Keras 모델 로드 ===")
    keras_model = load_keras_model(KERAS_MODEL_PATH)

    keras_preds, keras_probs = predict_keras(
        keras_model,
        validation_texts,
    )

    summary_rows = [
        print_model_summary("scikit-learn TF-IDF LogisticRegression", validation_labels, sklearn_preds),
        print_model_summary("TensorFlow Keras char model", validation_labels, keras_preds),
    ]

    save_summary(summary_rows)

    print_side_by_side_examples(
        validation_texts,
        validation_labels,
        sklearn_preds,
        keras_preds,
    )

    save_misclassified_comparison(
        validation_texts,
        validation_labels,
        sklearn_preds,
        sklearn_probs,
        keras_preds,
        keras_probs,
    )

    print("\n=== 비교 완료 ===")


if __name__ == "__main__":
    main()
