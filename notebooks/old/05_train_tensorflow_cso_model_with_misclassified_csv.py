"""
8주차 TensorFlow/Keras C/S/O 등급 예측 모델 학습 스크립트

목적:
- data/privacy_sentence_sample_v4.csv 파일을 사용해 문장(text) 기준 C/S/O 등급을 예측하는
  TensorFlow/Keras 모델을 학습합니다.
- 한국어 형태소 분석기를 사용하지 않고, char 단위 TextVectorization을 사용합니다.

입력:
- data/privacy_sentence_sample_v4.csv

사용 컬럼:
- text
- cso_grade

출력:
- models/privacy_cso_char_keras_model.keras

실행:
    python notebooks/05_train_tensorflow_cso_model.py
"""

from __future__ import annotations

import csv
import random
from collections import Counter
from pathlib import Path
from typing import Iterable

import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "privacy_sentence_sample_v4.csv"
MODEL_DIR = PROJECT_ROOT / "models"
MODEL_PATH = MODEL_DIR / "privacy_cso_char_keras_model.keras"

REPORT_DIR = PROJECT_ROOT / "reports"
MISCLASSIFIED_PATH = REPORT_DIR / "week8_tensorflow_misclassified.csv"

RANDOM_SEED = 42

MAX_TOKENS = 3000
SEQUENCE_LENGTH = 120
EMBEDDING_DIM = 64
DENSE_UNITS = 64
DROPOUT_RATE = 0.3
BATCH_SIZE = 16
EPOCHS = 20
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


def set_seed(seed: int = RANDOM_SEED) -> None:
    """재현 가능한 실험을 위해 random seed를 고정합니다."""
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def load_dataset(path: Path) -> tuple[list[str], list[int]]:
    """
    CSV에서 text와 cso_grade를 읽어 학습용 입력/라벨로 변환합니다.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"데이터 파일을 찾을 수 없습니다: {path}\n"
            "data/privacy_sentence_sample_v4.csv 파일이 있는지 확인하세요."
        )

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
                raise ValueError(
                    f"알 수 없는 cso_grade 값입니다: {grade}\n"
                    "허용 값: C, S, O"
                )

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
    간단한 train/validation 분리 함수입니다.
    외부 라이브러리 의존을 줄이기 위해 직접 구현합니다.
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
    """라벨 분포를 출력합니다."""
    counter = Counter(ID_TO_GRADE[label] for label in labels)
    print(title)
    for grade in ["C", "S", "O"]:
        print(f"  - {grade}: {counter.get(grade, 0)}")


def build_model() -> keras.Model:
    """
    char 단위 TensorFlow/Keras C/S/O 분류 모델을 생성합니다.
    """
    vectorizer = layers.TextVectorization(
        max_tokens=MAX_TOKENS,
        output_mode="int",
        output_sequence_length=SEQUENCE_LENGTH,
        split="character",
        name="char_vectorizer",
    )

    model = keras.Sequential(
        [
            vectorizer,
            layers.Embedding(
                input_dim=MAX_TOKENS,
                output_dim=EMBEDDING_DIM,
                name="char_embedding",
            ),
            layers.GlobalAveragePooling1D(name="global_average_pooling"),
            layers.Dense(DENSE_UNITS, activation="relu", name="dense_hidden"),
            layers.Dropout(DROPOUT_RATE, name="dropout"),
            layers.Dense(3, activation="softmax", name="cso_output"),
        ],
        name="privacy_cso_char_classifier",
    )

    model.compile(
        optimizer="adam",
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    return model


def predict_samples(model: keras.Model, samples: list[str]) -> None:
    """학습된 모델로 샘플 문장 예측 결과를 출력합니다."""
    print("\n=== 샘플 예측 ===")

    sample_x = np.array(samples, dtype=object)
    predictions = model.predict(sample_x, verbose=0)

    for text, probs in zip(samples, predictions):
        pred_id = int(np.argmax(probs))
        pred_grade = ID_TO_GRADE[pred_id]

        prob_text = ", ".join(
            f"{ID_TO_GRADE[idx]}={prob:.3f}"
            for idx, prob in enumerate(probs)
        )

        print(f"\n문장: {text}")
        print(f"예측 등급: {pred_grade}")
        print(f"확률: {prob_text}")


def save_misclassified_samples(
    model: keras.Model,
    texts: list[str],
    labels: list[int],
    output_path: Path = MISCLASSIFIED_PATH,
) -> None:
    """
    검증 데이터의 오분류 결과를 CSV로 저장합니다.

    저장 컬럼:
    - text: 검증 문장
    - true_grade: 실제 등급
    - pred_grade: 예측 등급
    - prob_C: C 확률
    - prob_S: S 확률
    - prob_O: O 확률
    """
    print("\n=== 검증 데이터 오분류 목록 ===")

    x = np.array(texts, dtype=object)
    probs = model.predict(x, verbose=0)
    preds = np.argmax(probs, axis=1)

    misclassified_rows: list[dict[str, str]] = []

    for text, true_id, pred_id, prob in zip(texts, labels, preds, probs):
        if true_id == pred_id:
            continue

        row = {
            "text": text,
            "true_grade": ID_TO_GRADE[int(true_id)],
            "pred_grade": ID_TO_GRADE[int(pred_id)],
            "prob_C": f"{prob[GRADE_TO_ID['C']]:.6f}",
            "prob_S": f"{prob[GRADE_TO_ID['S']]:.6f}",
            "prob_O": f"{prob[GRADE_TO_ID['O']]:.6f}",
        }
        misclassified_rows.append(row)

    if not misclassified_rows:
        print("오분류 없음")
    else:
        for index, row in enumerate(misclassified_rows, start=1):
            print(f"\n[{index}]")
            print(f"문장: {row['text']}")
            print(f"실제 등급: {row['true_grade']}")
            print(f"예측 등급: {row['pred_grade']}")
            print(
                "확률: "
                f"C={float(row['prob_C']):.3f}, "
                f"S={float(row['prob_S']):.3f}, "
                f"O={float(row['prob_O']):.3f}"
            )

        print(f"\n오분류 수: {len(misclassified_rows)} / {len(texts)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = ["text", "true_grade", "pred_grade", "prob_C", "prob_S", "prob_O"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(misclassified_rows)

    print("\n=== 오분류 CSV 저장 완료 ===")
    print(output_path)


def main() -> None:
    set_seed()

    print("=== 8주차 TensorFlow/Keras C/S/O 모델 학습 ===")
    print(f"데이터 경로: {DATA_PATH}")
    print(f"모델 저장 경로: {MODEL_PATH}")

    texts, labels = load_dataset(DATA_PATH)

    print(f"\n전체 데이터 수: {len(texts)}")
    print_label_distribution("전체 라벨 분포:", labels)

    train_texts, train_labels, validation_texts, validation_labels = train_test_split(
        texts,
        labels,
    )

    print(f"\n학습 데이터 수: {len(train_texts)}")
    print(f"검증 데이터 수: {len(validation_texts)}")
    print_label_distribution("학습 라벨 분포:", train_labels)
    print_label_distribution("검증 라벨 분포:", validation_labels)

    model = build_model()

    # TextVectorization은 학습 데이터로 vocabulary를 먼저 구축해야 합니다.
    vectorizer = model.layers[0]
    vectorizer.adapt(train_texts)

    print("\n=== 모델 구조 ===")
    model.summary()

    train_x = np.array(train_texts, dtype=object)
    train_y = np.array(train_labels, dtype=np.int64)
    validation_x = np.array(validation_texts, dtype=object)
    validation_y = np.array(validation_labels, dtype=np.int64)

    print("\n=== 모델 학습 시작 ===")
    history = model.fit(
        train_x,
        train_y,
        validation_data=(validation_x, validation_y),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        verbose=1,
    )

    print("\n=== 최종 평가 ===")
    loss, accuracy = model.evaluate(validation_x, validation_y, verbose=0)
    print(f"검증 손실: {loss:.4f}")
    print(f"검증 정확도: {accuracy:.4f}")

    samples = [
        "회의 결과를 요약하여 공유드립니다.",
        "담당자 이메일은 test@example.com입니다.",
        "서버 IP는 192.168.0.1이고 VLAN 100을 사용합니다.",
        "입찰 제안 평가표를 검토했습니다.",
        "특정 역 사고 이력 원자료를 첨부했습니다.",
        "직원 김도윤의 감봉 처분 결과를 확인했습니다.",
        "외부 공개용 보도자료 문구를 검토했습니다.",
    ]

    predict_samples(model, samples)

    save_misclassified_samples(
        model,
        validation_texts,
        validation_labels,
    )

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model.save(MODEL_PATH)

    print("\n=== 모델 저장 완료 ===")
    print(MODEL_PATH)

    print("\n=== 마지막 epoch 지표 ===")
    for key, values in history.history.items():
        print(f"{key}: {values[-1]:.4f}")


if __name__ == "__main__":
    main()
