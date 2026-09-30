"""실행 레지스트리 테스트."""

from notebooklm_st.core import models
from notebooklm_st.services import run_registry, runs

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


def start(registry: run_registry.RunRegistry, video_id: str) -> runs.RunHandle:
    """실행 하나를 넣고 곧바로 진행 중으로 만든다.

    대기 항목이 없을 때 불러야 방금 넣은 것을 가져간다.
    """
    registry.enqueue(f"u-{video_id}", video_id, QUESTIONS)
    registry.acquire_worker()
    handle = registry.claim_next()
    assert handle is not None
    assert handle.video_id == video_id
    return handle


def queued_registry(count: int) -> run_registry.RunRegistry:
    """대기 항목을 ``count`` 개 넣은 레지스트리를 만든다."""
    registry = run_registry.RunRegistry()
    for index in range(count):
        registry.enqueue(f"u{index}", f"v{index}", QUESTIONS)
    return registry


def test_acquire_worker_takes_the_only_slot() -> None:
    """대기 항목이 있으면 자리를 잡고, 자리가 찼으면 거절한다."""
    registry = queued_registry(2)

    assert registry.acquire_worker() is True
    assert registry.acquire_worker() is False


def test_acquire_worker_needs_a_queued_run() -> None:
    """대기 항목이 없으면 워커를 띄울 까닭이 없다."""
    assert run_registry.RunRegistry().acquire_worker() is False


def test_acquire_worker_refuses_while_paused() -> None:
    """멈춘 대기열에는 워커를 띄우지 않는다."""
    registry = queued_registry(1)
    registry.pause("요청 한도를 초과했습니다.")

    assert registry.acquire_worker() is False


def test_claim_next_takes_runs_in_enqueue_order() -> None:
    """먼저 넣은 것부터 진행 중으로 바꿔 돌려준다."""
    registry = run_registry.RunRegistry()
    first = registry.enqueue("u1", "v1", QUESTIONS)
    second = registry.enqueue("u2", "v2", QUESTIONS)
    registry.acquire_worker()

    claimed = registry.claim_next()
    assert claimed is not None
    assert claimed.run_id == first.run_id
    assert claimed.status == "running"
    assert claimed.started_at
    stored = registry.get(second.run_id)
    assert stored is not None
    assert stored.status == "queued"
    again = registry.claim_next()
    assert again is not None
    assert again.run_id == second.run_id


def test_claim_next_frees_the_slot_when_nothing_is_left() -> None:
    """돌려줄 것이 없으면 자리를 비워 다음 넣기가 워커를 띄운다."""
    registry = queued_registry(1)
    registry.acquire_worker()
    registry.claim_next()

    assert registry.claim_next() is None
    registry.enqueue("u9", "v9", QUESTIONS)
    assert registry.acquire_worker() is True


def test_claim_next_stops_while_paused() -> None:
    """멈추면 대기 항목을 남긴 채 None 을 주고 자리를 비운다."""
    registry = queued_registry(2)
    registry.acquire_worker()
    registry.claim_next()
    registry.pause("인증이 만료되었습니다.")

    assert registry.claim_next() is None
    assert [item.status for item in registry.list_all()] == [
        "running",
        "queued",
    ]
    assert registry.resume() is True


def test_release_worker_frees_the_slot() -> None:
    """워커가 예외로 끝나 자리를 비우면 다음 워커를 띄울 수 있다."""
    registry = queued_registry(1)
    registry.acquire_worker()

    registry.release_worker()

    assert registry.acquire_worker() is True


def test_pause_records_the_reason() -> None:
    """멈춘 이유를 그대로 돌려준다."""
    registry = queued_registry(1)

    registry.pause("요청 한도를 초과했습니다.")

    assert registry.paused_reason() == "요청 한도를 초과했습니다."


def test_pause_without_queued_runs_does_nothing() -> None:
    """남은 대기 항목이 없으면 멈추지 않는다."""
    registry = run_registry.RunRegistry()
    start(registry, "v")

    registry.pause("인증이 만료되었습니다.")

    assert registry.paused_reason() is None


def test_resume_clears_the_pause_and_asks_for_a_worker() -> None:
    """재개하면 멈춤이 풀리고, 자리가 비었으면 워커를 띄우라고 한다."""
    registry = queued_registry(1)
    registry.pause("요청 한도를 초과했습니다.")

    assert registry.resume() is True
    assert registry.paused_reason() is None


def test_resume_does_not_ask_for_a_second_worker() -> None:
    """워커가 아직 자리를 쥐고 있으면 새 워커를 띄우지 않는다."""
    registry = queued_registry(2)
    registry.acquire_worker()
    registry.pause("요청 한도를 초과했습니다.")

    assert registry.resume() is False
    assert registry.paused_reason() is None


def test_cancelling_the_last_queued_run_clears_the_pause() -> None:
    """대기 항목이 남아 있는 동안만 멈춤이 남는다."""
    registry = run_registry.RunRegistry()
    first = registry.enqueue("u1", "v1", QUESTIONS)
    second = registry.enqueue("u2", "v2", QUESTIONS)
    registry.pause("인증이 만료되었습니다.")

    registry.cancel(first.run_id)
    assert registry.paused_reason() == "인증이 만료되었습니다."
    registry.cancel(second.run_id)
    assert registry.paused_reason() is None


def test_active_count_skips_queued_runs_while_paused() -> None:
    """멈춘 대기열의 항목은 곧 돌지 않으므로 세지 않는다."""
    registry = run_registry.RunRegistry()
    start(registry, "v0")
    done = start(registry, "v1")
    registry.finish(done.run_id, make_result())
    registry.enqueue("u2", "v2", QUESTIONS)

    assert registry.active_count() == 2
    registry.pause("요청 한도를 초과했습니다.")
    assert registry.active_count() == 1


def test_is_pending_sees_queued_and_running_runs_only() -> None:
    """대기·진행 중인 영상만 걸린다. 끝난 영상은 다시 넣을 수 있다."""
    registry = run_registry.RunRegistry()
    start(registry, "running")
    done = start(registry, "done")
    registry.finish(done.run_id, make_result())
    registry.enqueue("u", "queued", QUESTIONS)

    assert registry.is_pending("queued") is True
    assert registry.is_pending("running") is True
    assert registry.is_pending("done") is False
    assert registry.is_pending("unknown") is False
