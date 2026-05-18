from dataclasses import asdict
from pathlib import Path
from typing import Any

import joblib

from regex_detector import DetectionResult, detect_patterns, get_max_grade


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


def select_highest_grade(grades: list[str]) -> str:
    """
    여러 등급 중 가장 높은 등급을 반환합니다.

    사용 목적:
    - 문서 전체 등급 산정
    - 여러 문장 등급 중 최고 등급 산정
    - 여러 정규식 탐지 결과 중 최고 등급 산정

    주의:
    - 한 문장 안에서 정규식 결과와 AI 결과를 결합할 때는
      decide_final_grade()를 사용합니다.
    """
    if not grades:
        return "O"

    return max(grades, key=lambda grade: GRADE_PRIORITY.get(grade, 0))


def decide_final_grade(regex_grade: str | None, ai_grade: str) -> tuple[str, str]:
    """
    한 문장에 대한 최종 C/S/O 등급을 결정합니다.

    원칙:
    1. 정규식 탐지 결과가 있으면 정규식 등급을 우선 적용합니다.
       - 정규식 대상은 주민등록번호, 이메일, 내부 IP, VLAN 등
         형태가 명확한 패턴형 정보이므로 AI보다 신뢰합니다.
    2. 정규식 탐지 결과가 없을 때만 AI 문장분류 결과를 적용합니다.
       - AI는 성명, 건강정보, 복지정보, 계약정보 등
         문맥형 정보를 보완하는 역할입니다.

    중요:
    - regex_grade가 "O"라는 뜻은 쓰지 않습니다.
    - 정규식 탐지가 없으면 regex_grade는 None이어야 합니다.
    """
    if regex_grade is not None:
        return regex_grade, "정규식 탐지 결과 우선 적용"

    return ai_grade, "정규식 탐지 없음 — AI 문장분류 결과 적용"


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


def get_regex_grade_or_none(regex_results: list[DetectionResult]) -> str | None:
    """
    정규식 탐지 결과가 있으면 최고 등급을 반환하고,
    탐지 결과가 없으면 None을 반환합니다.

    이유:
    - 정규식 탐지 없음과 O등급은 다른 의미입니다.
    - 정규식 탐지 없음: 패턴형 정보가 발견되지 않음
    - O등급: 최종적으로 공개 가능하다고 판단됨
    """
    if not regex_results:
        return None

    return get_max_grade(regex_results)


def hybrid_classify(text: str, ai_model) -> dict[str, Any]:
    """
    정규식 탐지 결과와 AI 문장분류 결과를 결합해 최종 C/S/O 등급을 산정합니다.

    기본 규칙:
    1. 정규식 탐지 결과가 있으면 정규식 기준 등급을 최종 등급으로 사용
    2. 정규식 탐지 결과가 없으면 AI 문장분류 결과를 등급으로 변환해 사용
    3. AI 예측은 최종 등급과 별개로 참고 근거로 함께 반환
    """
    regex_results = detect_patterns(text)
    regex_grade = get_regex_grade_or_none(regex_results)

    ai_label = ai_model.predict([text])[0]
    ai_grade = AI_LABEL_TO_GRADE.get(ai_label, "O")

    final_grade, decision_reason = decide_final_grade(regex_grade, ai_grade)

    return {
        "text": text,
        "regex_grade": regex_grade,
        "ai_label": ai_label,
        "ai_grade": ai_grade,
        "final_cso_grade": final_grade,
        "decision_reason": decision_reason,
        "regex_results": summarize_regex_results(regex_results),
    }


def format_regex_grade(regex_grade: str | None) -> str:
    """출력용 정규식 등급 문구를 반환합니다."""
    return regex_grade if regex_grade is not None else "해당 없음"


def print_hybrid_result(result: dict[str, Any]) -> None:
    """hybrid_classify 결과를 콘솔에서 보기 좋게 출력합니다."""
    regex_grade_display = format_regex_grade(result["regex_grade"])

    print(f"\n문장: {result['text']}")
    print(f"AI 예측: {result['ai_label']} → {result['ai_grade']}")
    print(f"정규식 기준 등급: {regex_grade_display}")
    print(f"최종 C/S/O 등급: {result['final_cso_grade']}")
    print(f"판단 근거: {result['decision_reason']}")

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
    project_root = Path(__file__).resolve().parent.parent
    model_path = project_root / "models" / "privacy_sentence_model_v2.pkl"

    print("사용 모델 경로:", model_path)

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
