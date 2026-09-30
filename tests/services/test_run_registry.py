"""실행 레지스트리 테스트."""

from notebooklm_st.core import models
from notebooklm_st.services import run_registry

QUESTIONS = (
    models.Question(
        id=1,
        title="핵심 주장",
        text="핵심 주장은?",
        created_at="2026-09-30T10:00:00",
        updated_at="2026-09-30T10:00:00",
    ),
)
"""레지스트리에 넣을 질문."""


def make_result() -> models.RunResult:
    """테스트용 실행 결과를 만든다."""
    return models.RunResult(
        url="https://youtu.be/dQw4w9WgXcQ", video_id="dQw4w9WgXcQ", items=()
    )


def test_running_count_counts_only_running_runs() -> None:
    """진행 중인 실행만 센다."""
    registry = run_registry.RunRegistry()
    first = registry.create("u1", "v1", QUESTIONS)
    registry.create("u2", "v2", QUESTIONS)
    assert registry.running_count() == 2
    registry.finish(first.run_id, make_result())
    assert registry.running_count() == 1


def test_cancel_removes_a_queued_run() -> None:
    """대기 중인 실행은 취소하면 목록에서 사라진다."""
    registry = run_registry.RunRegistry()
    handle = registry.enqueue("u", "v", QUESTIONS)

    assert registry.cancel(handle.run_id) is True
    assert registry.get(handle.run_id) is None


def test_cancel_leaves_a_started_or_finished_run() -> None:
    """이미 시작했거나 끝난 실행은 취소하지 않는다."""
    registry = run_registry.RunRegistry()
    running = registry.create("u1", "v1", QUESTIONS)
    done = registry.create("u2", "v2", QUESTIONS)
    registry.finish(done.run_id, make_result())

    assert registry.cancel(running.run_id) is False
    assert registry.cancel(done.run_id) is False
    assert registry.cancel("없는-id") is False
    assert len(registry.list_all()) == 2
