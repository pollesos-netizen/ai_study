"""
8주차 TensorFlow/Keras C/S/O 등급 예측 모델 테스트 스크립트

목적:
- 05_train_tensorflow_cso_model.py에서 저장한 Keras 모델을 불러옵니다.
- 새 문장을 입력해 C/S/O 등급과 예측 확률을 확인합니다.
- 학습 스크립트와 분리하여, 저장된 모델을 실제 탐지 흐름에서 어떻게 사용할 수 있는지 확인합니다.

입력:
- models/privacy_cso_char_keras_model.keras

출력:
- 콘솔 예측 결과

실행:
    python notebooks/06_test_tensorflow_cso_model.py
"""

from __future__ import annotations

import os

# TensorFlow 안내 로그를 줄입니다.
# oneDNN 관련 안내까지 끄고 싶으면 아래 줄의 주석을 해제할 수 있습니다.
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
# os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

from pathlib import Path

import numpy as np
import tensorflow as tf


keras = tf.keras


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = PROJECT_ROOT / "models" / "privacy_cso_char_keras_model.keras"

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


def load_model(model_path: Path = MODEL_PATH) -> keras.Model:
    """
    저장된 TensorFlow/Keras 모델을 불러옵니다.
    """
    if not model_path.exists():
        raise FileNotFoundError(
            f"모델 파일을 찾을 수 없습니다: {model_path}\n"
            "먼저 notebooks/05_train_tensorflow_cso_model.py를 실행해 모델을 저장하세요."
        )

    return keras.models.load_model(model_path)


def predict_grade(model: keras.Model, text: str) -> dict[str, object]:
    """
    문장 하나에 대해 C/S/O 등급을 예측합니다.

    Returns:
        {
            "text": 원문,
            "pred_grade": 예측 등급,
            "probabilities": {
                "C": 확률,
                "S": 확률,
                "O": 확률,
            }
        }
    """
    x = np.array([text], dtype=object)
    probs = model.predict(x, verbose=0)[0]

    pred_id = int(np.argmax(probs))
    pred_grade = ID_TO_GRADE[pred_id]

    return {
        "text": text,
        "pred_grade": pred_grade,
        "probabilities": {
            "C": float(probs[GRADE_TO_ID["C"]]),
            "S": float(probs[GRADE_TO_ID["S"]]),
            "O": float(probs[GRADE_TO_ID["O"]]),
        },
    }


def print_prediction(result: dict[str, object]) -> None:
    """
    예측 결과를 보기 좋게 출력합니다.
    """
    probabilities = result["probabilities"]

    print(f"\n문장: {result['text']}")
    print(f"예측 등급: {result['pred_grade']}")
    print(
        "확률: "
        f"C={probabilities['C']:.3f}, "
        f"S={probabilities['S']:.3f}, "
        f"O={probabilities['O']:.3f}"
    )


def predict_many(model: keras.Model, texts: list[str]) -> list[dict[str, object]]:
    """
    여러 문장을 한 번에 예측합니다.
    """
    if not texts:
        return []

    x = np.array(texts, dtype=object)
    probs_list = model.predict(x, verbose=0)

    results: list[dict[str, object]] = []

    for text, probs in zip(texts, probs_list):
        pred_id = int(np.argmax(probs))
        pred_grade = ID_TO_GRADE[pred_id]

        results.append(
            {
                "text": text,
                "pred_grade": pred_grade,
                "probabilities": {
                    "C": float(probs[GRADE_TO_ID["C"]]),
                    "S": float(probs[GRADE_TO_ID["S"]]),
                    "O": float(probs[GRADE_TO_ID["O"]]),
                },
            }
        )

    return results


def run_default_samples(model: keras.Model) -> None:
    """
    기본 샘플 문장으로 모델을 테스트합니다.
    """
    samples = [
        "회의 결과를 요약하여 공유드립니다.",
        "담당자 이메일은 test@example.com입니다.",
        "홍가람 민원인의 휴대전화 번호를 확인했습니다.",
        "서버 IP는 192.168.0.1이고 VLAN 100을 사용합니다.",
        "입찰 제안 평가표를 검토했습니다.",
        "특정 역 사고 이력 원자료를 첨부했습니다.",
        "직원 김도윤의 감봉 처분 결과를 확인했습니다.",
        "장애인 복지카드 사본을 제출했습니다.",
        "외부 공개용 보도자료 문구를 검토했습니다.",
    ]

    print("\n=== 기본 샘플 예측 ===")

    results = predict_many(model, samples)

    for result in results:
        print_prediction(result)


def run_interactive_mode(model: keras.Model) -> None:
    """
    사용자가 직접 문장을 입력해 예측하는 간단한 대화형 테스트 모드입니다.
    """
    print("\n=== 직접 입력 테스트 ===")
    print("문장을 입력하면 C/S/O 등급을 예측합니다.")
    print("종료하려면 q 또는 quit를 입력하세요.")

    while True:
        text = input("\n문장 입력: ").strip()

        if text.lower() in {"q", "quit", "exit"}:
            print("테스트를 종료합니다.")
            break

        if not text:
            print("빈 문장은 입력할 수 없습니다.")
            continue

        result = predict_grade(model, text)
        print_prediction(result)


def main() -> None:
    print("=== 8주차 TensorFlow/Keras C/S/O 모델 테스트 ===")
    print(f"모델 경로: {MODEL_PATH}")

    model = load_model(MODEL_PATH)

    run_default_samples(model)

    # 필요할 때만 직접 입력 테스트를 사용합니다.
    # 자동 실행이 불편하면 아래 줄을 주석 처리하세요.
    run_interactive_mode(model)


if __name__ == "__main__":
    main()
