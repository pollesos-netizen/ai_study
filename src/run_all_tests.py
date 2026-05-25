"""
5개 detector 단위 테스트를 모두 실행하는 통합 회귀 스크립트.

각 detector 테스트를 subprocess로 독립 실행하여 격리된 환경을 보장합니다.
한 detector에서 import 충돌이 나도 다른 detector는 영향받지 않습니다.

실행:
    python notebooks/run_all_tests.py

옵션:
    --verbose  각 detector 테스트의 전체 출력 표시
    --fail-fast 첫 실패 발생 시 즉시 중단

종료 코드:
    0: 모두 통과
    1: 하나 이상 실패
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path


# detector 테스트 파일 목록 (실행 순서대로)
TEST_FILES = [
    ("xlsx", "13_test_xlsx_regression.py"),
    ("docx", "15_test_docx_detector.py"),
    ("pptx", "17_test_pptx_detector.py"),
    ("hwpx", "19_test_hwpx_detector.py"),
    ("pdf",  "21_test_pdf_detector.py"),
]


def _extract_summary(output: str) -> tuple[int, int]:
    """
    테스트 출력에서 '통과: N / 전체: M' 패턴을 추출합니다.

    Returns:
        (passed, total)
    """
    # "통과: 67 / 전체: 67" 형태
    match = re.search(r"통과:\s*(\d+)\s*/\s*전체:\s*(\d+)", output)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 0, 0


def _run_one_test(
    test_path: Path,
    verbose: bool = False,
) -> tuple[int, int, float, str]:
    """
    단일 테스트 파일을 subprocess로 실행합니다.

    Returns:
        (passed, total, elapsed_seconds, output)
    """
    start = time.time()
    proc = subprocess.run(
        [sys.executable, str(test_path)],
        capture_output=True,
        text=True,
        timeout=600,  # 각 테스트 최대 10분
    )
    elapsed = time.time() - start

    output = proc.stdout + (proc.stderr if proc.returncode != 0 else "")
    passed, total = _extract_summary(output)

    if verbose:
        print(output)

    return passed, total, elapsed, output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="각 테스트의 전체 출력 표시")
    parser.add_argument("--fail-fast", action="store_true",
                        help="첫 실패 시 즉시 중단")
    args = parser.parse_args()

    notebooks_dir = Path(__file__).resolve().parent

    print("=" * 60)
    print("5개 detector 통합 회귀 테스트")
    print("=" * 60)

    results: list[tuple[str, int, int, float, bool]] = []
    overall_failed = False

    for detector_name, file_name in TEST_FILES:
        test_path = notebooks_dir / file_name
        if not test_path.exists():
            print(f"\n[SKIP] {detector_name}: {file_name} 없음")
            results.append((detector_name, 0, 0, 0.0, False))
            overall_failed = True
            continue

        print(f"\n--- {detector_name} ({file_name}) ---")

        try:
            passed, total, elapsed, output = _run_one_test(test_path, args.verbose)
        except subprocess.TimeoutExpired:
            print(f"  [TIMEOUT] {detector_name}: 600초 초과")
            results.append((detector_name, 0, 0, 600.0, False))
            overall_failed = True
            if args.fail_fast:
                break
            continue
        except Exception as exc:
            print(f"  [ERROR] {detector_name}: {type(exc).__name__}: {exc}")
            results.append((detector_name, 0, 0, 0.0, False))
            overall_failed = True
            if args.fail_fast:
                break
            continue

        passed_all = (total > 0 and passed == total)
        status = "PASS" if passed_all else "FAIL"
        print(f"  [{status}] {detector_name}: {passed}/{total} ({elapsed:.1f}초)")

        if not passed_all:
            overall_failed = True
            # verbose 아니어도 실패 시 출력 일부 표시
            if not args.verbose:
                fail_lines = [
                    line for line in output.splitlines()
                    if "FAIL" in line or "ERROR" in line or "실패" in line
                ]
                for line in fail_lines[:15]:
                    print(f"    {line}")
                if len(fail_lines) > 15:
                    print(f"    ... 이외 {len(fail_lines) - 15}건 생략")

            if args.fail_fast:
                results.append((detector_name, passed, total, elapsed, passed_all))
                break

        results.append((detector_name, passed, total, elapsed, passed_all))

    # 전체 요약
    print()
    print("=" * 60)
    print("통합 결과 요약")
    print("=" * 60)

    total_passed = sum(p for _, p, _, _, _ in results)
    total_count = sum(t for _, _, t, _, _ in results)
    total_elapsed = sum(e for _, _, _, e, _ in results)

    for name, passed, total, elapsed, ok in results:
        marker = "✓" if ok else "✗"
        print(f"  {marker} {name:6s}: {passed:4d}/{total:4d}  ({elapsed:5.1f}초)")

    print("-" * 60)
    print(f"  합계: {total_passed}/{total_count} ({total_elapsed:.1f}초)")

    if overall_failed:
        print("\n실패한 detector가 있습니다.")
        return 1
    print("\n모두 통과.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
