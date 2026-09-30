"""실행 레지스트리 테스트."""

from notebooklm_st.core import models
from notebooklm_st.services import run_registry


def make_result() -> models.RunResult:
    """테스트용 실행 결과를 만든다."""
    return models.RunResult(
        url="https://youtu.be/dQw4w9WgXcQ", video_id="dQw4w9WgXcQ", items=()
    )


def test_running_count_counts_only_running_runs() -> None:
    """진행 중인 실행만 센다."""
    registry = run_registry.RunRegistry()
    first = registry.create("u1", "v1", ("q",))
    registry.create("u2", "v2", ("q",))
    assert registry.running_count() == 2
    registry.finish(first.run_id, make_result())
    assert registry.running_count() == 1
