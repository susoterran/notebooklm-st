"""실행 보관소 테스트."""

import itertools

from notebooklm_st.core import models
from notebooklm_st.services import run_registry, run_store, runs

QUESTIONS = (
    models.Question(
        id=1,
        title="핵심 주장",
        text="핵심 주장은?",
        created_at="2026-09-30T10:00:00",
        updated_at="2026-09-30T10:00:00",
    ),
)
"""보관소에 넣을 질문. 보관소는 질문을 들고 있기만 한다."""


def make_result() -> models.RunResult:
    """테스트용 실행 결과를 만든다."""
    return models.RunResult(
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        items=(
            models.AnswerItem(
                question_title="핵심 주장",
                question_text="핵심 주장은?",
                answer="세 가지다.",
                citations=(),
                error=None,
            ),
        ),
    )


def use_ticking_clock(monkeypatch) -> None:
    """``run_store._now`` 가 부를 때마다 1초 늦은 시각을 주게 한다.

    진짜 시계는 초 단위라 한 테스트 안의 호출이 모두 같은 시각이
    된다. 끝난 순서를 가려야 하는 테스트가 쓴다.
    """
    ticks = itertools.count()
    monkeypatch.setattr(
        run_store, "_now", lambda: f"2026-09-30T10:00:{next(ticks):02d}"
    )


def start(registry: run_registry.RunRegistry, video_id: str) -> runs.RunHandle:
    """실행 하나를 넣고 곧바로 진행 중으로 만든다.

    진행 중인 핸들은 레지스트리가 대기 항목을 가져갈 때만 생긴다.
    대기 항목이 없을 때 불러야 방금 넣은 것을 가져간다.
    """
    registry.enqueue(f"u-{video_id}", video_id, QUESTIONS)
    registry.acquire_worker()
    handle = registry.claim_next()
    assert handle is not None
    assert handle.video_id == video_id
    return handle


def test_enqueue_returns_a_queued_handle() -> None:
    """대기열에 넣은 실행은 아직 시작하지 않았다."""
    store = run_store.RunStore()

    handle = store.enqueue("u", "v", QUESTIONS, auto_save=True)

    assert handle.status == "queued"
    assert handle.queued_at
    assert handle.started_at is None
    assert handle.questions == QUESTIONS
    assert handle.auto_save is True
    assert handle.progress == []
    assert handle.result is None
    assert handle.save is None
    assert handle.error_message is None
    assert handle.finished_at is None
    assert store.get(handle.run_id) == handle


def test_enqueue_gives_each_run_a_distinct_id() -> None:
    """실행마다 서로 다른 ID 를 준다."""
    store = run_store.RunStore()
    first = store.enqueue("u1", "v1", QUESTIONS)
    second = store.enqueue("u2", "v2", QUESTIONS)
    assert first.run_id != second.run_id


def test_enqueue_leaves_auto_save_off_by_default() -> None:
    """자동 저장은 켜서 넣을 때만 켜진다. 기본은 끔이다."""
    handle = run_store.RunStore().enqueue("u", "v", QUESTIONS)

    assert handle.auto_save is False


def test_get_returns_none_for_unknown_id() -> None:
    """없는 ID 를 조회하면 None 을 돌려준다."""
    store = run_store.RunStore()
    assert store.get("없는-id") is None


def test_append_progress_accumulates_messages() -> None:
    """진행 문구가 순서대로 쌓인다."""
    store = run_store.RunStore()
    handle = store.enqueue("u", "v", QUESTIONS)
    store.append_progress(handle.run_id, "1단계")
    store.append_progress(handle.run_id, "2단계")
    stored = store.get(handle.run_id)
    assert stored is not None
    assert stored.progress == ["1단계", "2단계"]


def test_append_progress_ignores_unknown_id() -> None:
    """없는 ID 에 진행을 기록해도 예외를 던지지 않는다."""
    store = run_store.RunStore()
    store.append_progress("없는-id", "무시됨")


def test_finish_records_result_and_status() -> None:
    """완료하면 결과와 종료 시각이 남는다."""
    store = run_store.RunStore()
    handle = store.enqueue("u", "v", QUESTIONS)
    result = make_result()
    store.finish(handle.run_id, result)
    stored = store.get(handle.run_id)
    assert stored is not None
    assert stored.status == "done"
    assert stored.result == result
    assert stored.finished_at
    assert stored.error_message is None


def test_fail_records_message_and_level() -> None:
    """실패하면 사용자 문구와 표시 수준이 남는다."""
    store = run_store.RunStore()
    handle = store.enqueue("u", "v", QUESTIONS)
    store.fail(handle.run_id, "자막이 없습니다.", "info")
    stored = store.get(handle.run_id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_message == "자막이 없습니다."
    assert stored.error_level == "info"
    assert stored.result is None
    assert stored.finished_at


def test_list_all_puts_the_running_run_first(monkeypatch) -> None:
    """진행 중인 실행이 끝난 실행보다 먼저 온다."""
    use_ticking_clock(monkeypatch)
    registry = run_registry.RunRegistry()
    done = start(registry, "v0")
    registry.finish(done.run_id, make_result())
    running = start(registry, "v1")

    assert [item.run_id for item in registry.list_all()] == [
        running.run_id,
        done.run_id,
    ]


def test_list_all_puts_queued_runs_between_running_and_finished(
    monkeypatch,
) -> None:
    """대기 중인 실행은 진행 중인 실행 뒤, 끝난 실행 앞에 온다."""
    use_ticking_clock(monkeypatch)
    registry = run_registry.RunRegistry()
    done = start(registry, "v0")
    registry.finish(done.run_id, make_result())
    running = start(registry, "v1")
    first = registry.enqueue("u2", "v2", QUESTIONS)
    second = registry.enqueue("u3", "v3", QUESTIONS)

    assert [item.run_id for item in registry.list_all()] == [
        running.run_id,
        first.run_id,
        second.run_id,
        done.run_id,
    ]


def test_list_all_puts_the_latest_finished_run_first(monkeypatch) -> None:
    """끝난 실행은 넣은 순서가 아니라 최근에 끝난 것부터 온다."""
    use_ticking_clock(monkeypatch)
    store = run_store.RunStore()
    early = store.enqueue("u1", "v1", QUESTIONS)
    late = store.enqueue("u2", "v2", QUESTIONS)
    store.finish(late.run_id, make_result())
    store.fail(early.run_id, "실패", "error")

    assert [item.run_id for item in store.list_all()] == [
        early.run_id,
        late.run_id,
    ]


def test_list_all_puts_the_newer_run_first_on_a_finish_tie(
    monkeypatch,
) -> None:
    """끝난 시각이 같으면 나중에 넣은 실행이 앞에 온다."""
    monkeypatch.setattr(run_store, "_now", lambda: "2026-09-30T10:00:00")
    store = run_store.RunStore()
    older = store.enqueue("u1", "v1", QUESTIONS)
    newer = store.enqueue("u2", "v2", QUESTIONS)
    store.finish(older.run_id, make_result())
    store.finish(newer.run_id, make_result())

    assert [item.run_id for item in store.list_all()] == [
        newer.run_id,
        older.run_id,
    ]


def test_list_all_returns_copies() -> None:
    """목록이 돌려준 핸들을 바꿔도 보관소는 영향받지 않는다."""
    store = run_store.RunStore()
    handle = store.enqueue("u", "v", QUESTIONS)
    borrowed = store.list_all()[0]
    borrowed.progress.append("바깥에서 추가")
    borrowed.status = "done"
    stored = store.get(handle.run_id)
    assert stored is not None
    assert stored.progress == []
    assert stored.status == "queued"


def test_discard_removes_the_handle() -> None:
    """지운 실행은 목록에서 사라진다."""
    store = run_store.RunStore()
    handle = store.enqueue("u", "v", QUESTIONS)
    store.discard(handle.run_id)
    assert store.get(handle.run_id) is None
    assert store.list_all() == []


def test_discard_ignores_unknown_id() -> None:
    """없는 ID 를 지워도 예외를 던지지 않는다."""
    store = run_store.RunStore()
    store.discard("없는-id")


def test_discard_finished_keeps_unfinished_runs() -> None:
    """끝난 실행만 지우고 지운 수를 돌려준다."""
    store = run_store.RunStore()
    waiting = store.enqueue("u1", "v1", QUESTIONS)
    done = store.enqueue("u2", "v2", QUESTIONS)
    failed = store.enqueue("u3", "v3", QUESTIONS)
    store.finish(done.run_id, make_result())
    store.fail(failed.run_id, "실패", "error")

    assert store.discard_finished() == 2
    assert [item.run_id for item in store.list_all()] == [waiting.run_id]


def test_discard_finished_on_an_empty_store_returns_zero() -> None:
    """지울 것이 없으면 0 이다."""
    assert run_store.RunStore().discard_finished() == 0


def test_finish_keeps_the_save_outcome() -> None:
    """완료할 때 넘긴 자동 저장 결과가 핸들에 실린다."""
    store = run_store.RunStore()
    handle = store.enqueue("u", "v", QUESTIONS, auto_save=True)
    outcome = runs.SaveOutcome("saved", "저장됨", "http://wiki/doc/x")

    store.finish(handle.run_id, make_result(), outcome)

    finished = store.get(handle.run_id)
    assert finished is not None
    assert finished.save == outcome


def test_finish_without_a_save_leaves_it_empty() -> None:
    """자동 저장을 하지 않은 실행은 저장 결과가 없다."""
    store = run_store.RunStore()
    handle = store.enqueue("u", "v", QUESTIONS)

    store.finish(handle.run_id, make_result())

    finished = store.get(handle.run_id)
    assert finished is not None
    assert finished.save is None
