from dataclasses import asdict
from pathlib import Path
from typing import Any

import joblib

from regex_detector import DetectionResult, detect_patterns, get_max_grade

model_path = Path("models/privacy_sentence_model_v2.pkl")

GRADE_PRIORITY = {
    "O": 0,
    "S": 1,
    "C": 2,
}


AI_LABEL_TO_GRADE = {
    "일반": "O",
    "개인정보": "S",
    "민감정보": "S",
}


def merge_grades(grades: list[str]) -> str:
    """여러 등급 중 가장 높은 등급을 반환합니다."""
    if not grades:
        return "O"

    return max(grades, key=lambda grade: GRADE_PRIORITY.get(grade, 0))


def load_ai_model(model_path: str | Path):
    """4주차에서 저장한 scikit-learn 모델을 불러옵니다."""
    model_path = Path(model_path)

    if not model_path.exists():
        raise FileNotFoundError(
            f"AI 모델 파일을 찾을 수 없습니다: {model_path}\n"
            "먼저 4주차 개선 모델을 저장했는지 확인하세요."
        )

    return joblib.load(model_path)


def summarize_regex_results(regex_results: list[DetectionResult]) -> list[dict[str, Any]]:
    """DetectionResult 객체를 출력하기 쉬운 dict 목록으로 변환합니다."""
    return [asdict(result) for result in regex_results]


def hybrid_classify(text: str, ai_model) -> dict[str, Any]:
    """
    정규식 탐지 결과와 AI 문장분류 결과를 결합해 최종 C/S/O 등급을 산정합니다.

    기본 규칙:
    1. 정규식에서 C급 항목이 탐지되면 최종 C
    2. 정규식에서 S급 항목이 탐지되면 최소 S
    3. AI가 개인정보 또는 민감정보로 예측하면 최소 S
    4. 정규식 탐지 없음 + AI 일반이면 O
    5. 불확실하거나 충돌이 있으면 상위 등급 유지
    """
    regex_results = detect_patterns(text)
    regex_grade = get_max_grade(regex_results)

    ai_label = ai_model.predict([text])[0]
    ai_grade = AI_LABEL_TO_GRADE.get(ai_label, "O")

    final_grade = merge_grades([regex_grade, ai_grade])

    return {
        "text": text,
        "regex_grade": regex_grade,
        "ai_label": ai_label,
        "ai_grade": ai_grade,
        "final_cso_grade": final_grade,
        "regex_results": summarize_regex_results(regex_results),
    }


def print_hybrid_result(result: dict[str, Any]) -> None:
    """hybrid_classify 결과를 콘솔에서 보기 좋게 출력합니다."""
    print(f"\n문장: {result['text']}")
    print(f"AI 예측: {result['ai_label']} → {result['ai_grade']}")
    print(f"정규식 기준 등급: {result['regex_grade']}")
    print(f"최종 C/S/O 등급: {result['final_cso_grade']}")

    if result["regex_results"]:
        print("정규식 탐지 결과:")
        for item in result["regex_results"]:
            print(
                f"  - {item['label']}: {item['value']} "
                f"[{item['grade']}, {item['action']}] "
                f"위치={item['start']}:{item['end']}"
            )
    else:
        print("정규식 탐지 결과: 없음")


if __name__ == "__main__":
    # 프로젝트 루트에서 실행하는 경우:
    # python src/hybrid_detector.py
    #
    # 이 파일이 src 폴더 안에 있고, 모델은 models 폴더 안에 있다고 가정합니다.
    model_path = Path(__file__).resolve().parent.parent / "models" / "privacy_sentence_model_v2.pkl"

    ai_model = load_ai_model(model_path)

    samples = [
        "회의 결과를 요약하여 공유드립니다.",
        "최지연 씨의 서류가 접수되었습니다.",
        "test@example.com으로 자료를 보내드리겠습니다.",
        "주민등록번호 900101-1234567이 포함되어 있습니다.",
        "서버 IP는 192.168.0.1이고 VLAN 100, port 8080을 사용합니다.",
        "진단서가 접수되었습니다.",
        "장애인 등록 신청서가 접수되었습니다.",
        "입찰 제안 평가표를 검토했습니다.",
        "무선설비 주파수 75.450MHz가 기재되어 있습니다.",
        "보안 패치 적용은 02:05:30부터 시작됩니다.",
    ]

    for sample in samples:
        result = hybrid_classify(sample, ai_model)
        print_hybrid_result(result)
