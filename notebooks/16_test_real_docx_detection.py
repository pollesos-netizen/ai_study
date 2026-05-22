"""
실제 docx 파일 대상 regex + NER + AI 탐지 + guide 생성 통합 테스트

실행 예시:
    python notebooks/16_test_real_docx_detection.py "data/sample.docx"

    # NER 연결
    python notebooks/16_test_real_docx_detection.py "data/sample.docx" \
        --ner-model-path "models/hf/KoELECTRA-small-v3-modu-ner"

    # AI 연결
    python notebooks/16_test_real_docx_detection.py "data/sample.docx" \
        --ai-model-path "models/privacy_cso_char_keras_model.keras"

    # mock review (모델 무관, reviewTargets 흐름 검증)
    python notebooks/16_test_real_docx_detection.py "data/sample.docx" \
        --force-mock-review

설명:
- 실제 docx 본문 paragraph를 순회합니다.
- regex 탐지는 src/regex_detector.py를 단일 소스로 사용합니다.
- NER 모델 경로가 제공되면 성명 탐지를 수행합니다.
- AI 모델 경로가 제공되면 문장 단위 review target 후보를 생성합니다.
- --force-mock-review를 사용하면 AI 모델 상태와 무관하게 mock review target을 주입합니다.

주의:
- 이 스크립트는 모델 성능 평가가 아니라 파이프라인 연결 검증용입니다.
- 시스템은 docx 파일을 직접 수정하지 않습니다 (guide 모드).
"""

from __future__ import annotations

from pathlib import Path
import argparse
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from common_apply_result import APPLY_MODE_GUIDE
from deidentify_target_builder import DeidentifyPlan, DeidentifyTarget
from old.docx_detector_v2 import (
    build_guide_for_docx,
    detect_in_docx,
    iter_docx_paragraphs,
    load_docx,
)


DEFAULT_NER_THRESHOLD = 0.8
DEFAULT_AI_THRESHOLD = 0.6


# ── 모델 로더 ──────────────────────────────────────────────────

def load_ner_pipeline(model_path: str | None):
    if not model_path:
        return None

    try:
        from transformers import pipeline
    except ImportError:
        print("[NER] transformers가 설치되어 있지 않아 NER 탐지를 건너뜁니다.")
        return None

    print(f"[NER] 모델 로드: {model_path}")
    return pipeline(
        "ner",
        model=model_path,
        tokenizer=model_path,
        aggregation_strategy="simple",
    )


def load_ai_model(model_path: str | None):
    if not model_path:
        return None

    try:
        import tensorflow as tf
    except ImportError:
        print("[AI] tensorflow가 설치되어 있지 않아 AI 분류를 건너뜁니다.")
        return None

    print(f"[AI] 모델 로드: {model_path}")
    return tf.keras.models.load_model(model_path)


def make_ai_predict_func(ai_model):
    """
    AI 모델을 (grade, confidence, prob_map) 반환 함수로 감쌉니다.

    모델 출력 순서는 C, S, O로 가정합니다.
    """
    if ai_model is None:
        return None

    def predict(text: str):
        try:
            import tensorflow as tf
            inputs = tf.constant([text])
            predictions = ai_model.predict(inputs, verbose=0)
            probs = predictions[0].tolist()

            labels = ["C", "S", "O"]
            prob_map = {label: float(p) for label, p in zip(labels, probs)}
            best_idx = max(range(len(probs)), key=lambda i: probs[i])
            return labels[best_idx], float(probs[best_idx]), prob_map
        except Exception as exc:
            print(f"[AI] 예측 실패: {exc}")
            return "O", 0.0, {}

    return predict


# ── mock review target 주입 ────────────────────────────────────
def inject_mock_review_target(plan: DeidentifyPlan, docx_path: str) -> DeidentifyPlan:
    """
    첫 번째 탐지 가능 paragraph에 mock review target을 강제로 추가합니다.

    AI 모델 상태와 무관하게 reviewTargets 흐름을 검증할 때 사용합니다.
    본문 paragraph와 표 셀 paragraph를 모두 대상으로 합니다.
    """
    doc = load_docx(docx_path)
    paragraphs = iter_docx_paragraphs(doc)

    if not paragraphs:
        print("[mock-review] 탐지 가능한 paragraph가 없어 mock review를 주입하지 않습니다.")
        return plan

    first = paragraphs[0]
    mock = DeidentifyTarget(
        label="민감정보",
        matched="",
        action="검토 필요",
        location_label=first.location_label,
        location_meta=first.location_meta,
        start=None,
        end=None,
        source="ai",
        reason="mock review target 검증용 (AI 모델 상태 무관)",
        grade="S",
        sensitive_type="문맥 기반 민감정보",
        sensitive_category="AI_mock",
        context=first.text,
        order=10**6,
    )

    plan.review_targets.append(mock)
    print(f"[mock-review] {first.location_label}에 mock review target 1건을 추가했습니다.")
    return plan

# ── 출력 ───────────────────────────────────────────────────────

def print_result(result, *, show_limit: int = 20) -> None:
    print("\n=== guide 모드 결과 요약 ===")
    print(f"fileType: {result.fileType}")
    print(f"applyMode: {result.applyMode}")
    print(f"inputFilePath: {result.inputFilePath}")
    print(f"outputFilePath: {result.outputFilePath}")

    s = result.summary
    print(f"\nsummary:")
    print(f"  totalLocations: {s.totalLocations}")
    print(f"  appliedLocations: {s.appliedLocations}")
    print(f"  partialLocations: {s.partialLocations}")
    print(f"  skippedLocations: {s.skippedLocations}")
    print(f"  totalWarnings: {s.totalWarnings}")
    print(f"  autoTargetCount: {s.autoTargetCount}")
    print(f"  reviewTargetCount: {s.reviewTargetCount}")

    print(f"\nautoResults: {len(result.autoResults)}")
    for item in result.autoResults[:show_limit]:
        print(
            f"  - {item.locationLabel}\n"
            f"    label={item.label} / action={item.action} / status={item.status}\n"
            f"    applied={item.appliedTargetCount}, skipped={item.skippedTargetCount}"
        )
        print(f"    original: {item.originalText}")
        print(f"    권장   : {item.appliedText}")
        for w in item.warnings:
            print(f"    warning: {w}")

    if len(result.autoResults) > show_limit:
        print(f"  ... 이외 {len(result.autoResults) - show_limit}건 생략")

    print(f"\nreviewTargets: {len(result.reviewTargets)}")
    for rv in result.reviewTargets[:show_limit]:
        print(
            f"  - {rv.locationLabel} / {rv.label} / action={rv.action}\n"
            f"    context: {rv.context}\n"
            f"    reason: {rv.reason}"
        )

    if len(result.reviewTargets) > show_limit:
        print(f"  ... 이외 {len(result.reviewTargets) - show_limit}건 생략")

    print(f"\nglobal warnings: {len(result.warnings)}")
    for w in result.warnings:
        print(f"  - {w}")


# ── main ──────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path", help="실제 docx 파일 경로")
    parser.add_argument("--ner-model-path", default=None)
    parser.add_argument("--ai-model-path", default=None)
    parser.add_argument("--ner-threshold", type=float, default=DEFAULT_NER_THRESHOLD)
    parser.add_argument("--ai-threshold", type=float, default=DEFAULT_AI_THRESHOLD)
    parser.add_argument(
        "--deletion-mode",
        default="mark",
        choices=["delete", "mark"],
        help="guide 모드 preview용 삭제 표시 방식",
    )
    parser.add_argument(
        "--force-mock-review",
        action="store_true",
        help="첫 본문 paragraph에 mock review target을 강제로 추가합니다.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {input_path}")

    print("=== 실제 docx 탐지 + guide 통합 테스트 ===")
    print(f"input_path: {input_path}")
    print(f"ner_model_path: {args.ner_model_path}")
    print(f"ai_model_path: {args.ai_model_path}")
    print(f"ner_threshold: {args.ner_threshold}")
    print(f"ai_threshold: {args.ai_threshold}")
    print(f"deletion_mode: {args.deletion_mode}")
    print(f"force_mock_review: {args.force_mock_review}")

    # 모델 로드
    ner_pipe = load_ner_pipeline(args.ner_model_path)
    ai_model = load_ai_model(args.ai_model_path)

    ner_detect_func = (lambda text: ner_pipe(text)) if ner_pipe is not None else None
    ai_predict_func = make_ai_predict_func(ai_model)

    # 탐지
    plan = detect_in_docx(
        str(input_path),
        ner_detect_func=ner_detect_func,
        ai_predict_func=ai_predict_func,
        ner_threshold=args.ner_threshold,
        ai_threshold=args.ai_threshold,
    )

    if args.force_mock_review:
        plan = inject_mock_review_target(plan, str(input_path))

    # guide 생성
    result = build_guide_for_docx(
        str(input_path),
        plan,
        deletion_mode=args.deletion_mode,
    )

    assert result.applyMode == APPLY_MODE_GUIDE
    assert result.outputFilePath is None

    print_result(result)

    print("\n=== 통합 테스트 완료 ===")


if __name__ == "__main__":
    main()
