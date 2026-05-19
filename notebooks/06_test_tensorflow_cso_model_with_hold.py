"""
8주차 TensorFlow/Keras C/S/O 등급 예측 모델 테스트 스크립트

목적:
- 05_train_tensorflow_cso_model.py에서 저장한 Keras 모델을 불러옵니다.
- 새 문장을 입력해 C/S/O 등급과 예측 확률을 확인합니다.
- 너무 짧은 입력이나 모델 확신도가 낮은 입력은 "판단 보류"로 처리합니다.

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
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
# oneDNN 안내까지 끄고 싶으면 아래 줄의 주석을 해제할 수 있습니다.
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

# 너무 짧은 입력은 모델이 의미 있는 판단을 하기 어렵기 때문에 예측하지 않습니다.
MIN_TEXT_LENGTH = 5

# 현재 모델은 확률이 전반적으로 낮게 나오는 편이므로,
# 최고 확률이 이 값보다 낮으면 최종 등급을 단정하지 않고 판단 보류로 처리합니다.
CONFIDENCE_THRESHOLD = 0.70


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


def make_hold_result(
    text: str,
    reason: str,
    probabilities: dict[str, float] | None = None,
) -> dict[str, object]:
    """
    판단 보류 결과를 생성합니다.
    """
    if probabilities is None:
        probabilities = {
            "C": 0.0,
            "S": 0.0,
            "O": 0.0,
        }

    return {
        "text": text,
        "pred_grade": "판단 보류",
        "reason": reason,
        "confidence": 0.0,
        "probabilities": probabilities,
    }


def predict_grade(model: keras.Model, text: str) -> dict[str, object]:
    """
    문장 하나에 대해 C/S/O 등급을 예측합니다.

    단, 다음 경우에는 C/S/O 등급을 단정하지 않고 "판단 보류"로 처리합니다.

    1. 입력 문장이 너무 짧은 경우
    2. 모델의 최고 확률이 CONFIDENCE_THRESHOLD보다 낮은 경우
    """
    text = text.strip()

    if len(text) < MIN_TEXT_LENGTH:
        return make_hold_result(
            text=text,
            reason=f"입력 문장이 너무 짧음: {len(text)}자",
        )

    x = np.array([text], dtype=object)
    probs = model.predict(x, verbose=0)[0]

    pred_id = int(np.argmax(probs))
    pred_grade = ID_TO_GRADE[pred_id]
    confidence = float(probs[pred_id])

    probabilities = {
        "C": float(probs[GRADE_TO_ID["C"]]),
        "S": float(probs[GRADE_TO_ID["S"]]),
        "O": float(probs[GRADE_TO_ID["O"]]),
    }

    if confidence < CONFIDENCE_THRESHOLD:
        return {
            "text": text,
            "pred_grade": "판단 보류",
            "reason": f"모델 확신도 낮음: {confidence:.3f}",
            "confidence": confidence,
            "suggested_grade": pred_grade,
            "probabilities": probabilities,
        }

    return {
        "text": text,
        "pred_grade": pred_grade,
        "reason": "정상 예측",
        "confidence": confidence,
        "probabilities": probabilities,
    }


def print_prediction(result: dict[str, object]) -> None:
    """
    예측 결과를 보기 좋게 출력합니다.
    """
    probabilities = result["probabilities"]

    print(f"\n문장: {result['text']}")
    print(f"예측 등급: {result['pred_grade']}")

    if "suggested_grade" in result:
        print(f"참고 등급: {result['suggested_grade']}")

    print(f"판단 사유: {result['reason']}")

    if result["confidence"]:
        print(f"확신도: {result['confidence']:.3f}")

    print(
        "확률: "
        f"C={probabilities['C']:.3f}, "
        f"S={probabilities['S']:.3f}, "
        f"O={probabilities['O']:.3f}"
    )


def predict_many(model: keras.Model, texts: list[str]) -> list[dict[str, object]]:
    """
    여러 문장을 예측합니다.

    짧은 입력과 확신도 낮은 입력은 각각 판단 보류로 처리합니다.
    """
    return [predict_grade(model, text) for text in texts]


def run_default_samples(model: keras.Model) -> None:
    """
    기본 샘플 문장으로 모델을 테스트합니다.
    """
    samples = [
        "ㅂ",
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
    print(f"최소 입력 길이: {MIN_TEXT_LENGTH}자")
    print(f"판단 보류 확신도 기준: {CONFIDENCE_THRESHOLD:.2f}")

    results = predict_many(model, samples)

    for result in results:
        print_prediction(result)


def run_interactive_mode(model: keras.Model) -> None:
    """
    사용자가 직접 문장을 입력해 예측하는 간단한 대화형 테스트 모드입니다.
    """
    print("\n=== 직접 입력 테스트 ===")
    print("문장을 입력하면 C/S/O 등급을 예측합니다.")
    print(f"{MIN_TEXT_LENGTH}자 미만 입력은 판단 보류로 처리합니다.")
    print(f"최고 확률이 {CONFIDENCE_THRESHOLD:.2f} 미만이면 판단 보류로 처리합니다.")
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
