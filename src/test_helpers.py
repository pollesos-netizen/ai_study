"""
detector 단위 테스트용 공통 헬퍼.

13~16주차 각 detector 테스트 파일에서 중복되었던 _check / _results 패턴을
하나로 모은 모듈입니다.

사용법:
    from test_helpers import TestRunner

    runner = TestRunner("docx detector 단위 테스트")
    runner.check("TC1.applied", item.status == "applied")
    runner.check("TC1.preview", "***" in item.appliedText,
                 f"appliedText={item.appliedText!r}")
    ...
    runner.report()  # 통과/실패 요약 출력 + 실패 시 sys.exit(1)

각 detector의 _make_target 등 도메인 헬퍼는 각 파일에 그대로 둡니다.
location_meta 구조가 detector마다 다르기 때문입니다.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field


@dataclass
class TestRunner:
    """단위 테스트 결과 집계 + 출력."""

    title: str = "단위 테스트"
    results: list[tuple[str, bool, str]] = field(default_factory=list)

    def check(self, tc_id: str, condition: bool, message: str = "") -> bool:
        """
        단일 검증 항목을 기록하고 PASS/FAIL을 즉시 출력합니다.

        Args:
            tc_id: 식별자 (예: "TC1.applied")
            condition: 검증 조건 (True면 PASS)
            message: 실패 시 표시할 추가 정보

        Returns:
            condition 그대로 (체이닝용)
        """
        self.results.append((tc_id, condition, message))
        status = "PASS" if condition else "FAIL"
        suffix = f": {message}" if (not condition and message) else ""
        print(f"  [{status}] {tc_id}{suffix}")
        return condition

    def report(self, exit_on_fail: bool = True) -> bool:
        """
        결과 요약을 출력합니다. 실패가 있으면 종료 코드 1로 종료(옵션).

        Returns:
            전부 통과했는지 여부
        """
        total = len(self.results)
        passed = sum(1 for _, ok, _ in self.results if ok)
        failed = total - passed

        print("\n=== 결과 요약 ===")
        print(f"  통과: {passed} / 전체: {total}")

        if failed:
            print(f"  실패: {failed}")
            for tc_id, ok, msg in self.results:
                if not ok:
                    print(f"    - {tc_id}: {msg}")
            if exit_on_fail:
                sys.exit(1)
            return False

        return True

    def record_error(self, fn_name: str, exc: Exception) -> None:
        """TC 함수 자체가 예외를 던진 경우 기록."""
        self.results.append((fn_name, False, str(exc)))


def run_test_functions(
    runner: TestRunner,
    test_functions: list,
    *args,
    **kwargs,
) -> None:
    """
    TC 함수 목록을 순서대로 실행하고 예외를 처리합니다.

    각 함수의 인자(tmp_dir 등)는 *args/**kwargs로 그대로 전달됩니다.
    """
    import traceback

    for fn in test_functions:
        try:
            fn(*args, **kwargs)
        except Exception as exc:
            print(f"  [ERROR] {fn.__name__}: {exc}")
            traceback.print_exc()
            runner.record_error(fn.__name__, exc)
