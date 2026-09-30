"""실행 레지스트리 테스트."""

import itertools

from notebooklm_st.core import models
from notebooklm_st.services import runs


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
    """``runs._now`` 가 부를 때마다 1초 늦은 시각을 주게 한다.

    진짜 시계는 초 단위라 한 테스트 안의 호출이 모두 같은 시각이
    된다. 끝난 순서를 가려야 하는 테스트가 쓴다.
    """
    ticks = itertools.count()
    monkeypatch.setattr(
        runs, "_now", lambda: f"2026-09-30T10:00:{next(ticks):02d}"
    )


def test_create_returns_a_running_handle() -> None:
    """새로 만든 실행은 running 상태로 시작한다."""
    registry = runs.RunRegistry()
    handle = registry.create(
        "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", ("핵심 주장은?",)
    )
    assert handle.status == "running"
    assert handle.progress == []
    assert handle.result is None
    assert handle.error_message is None
    assert handle.finished_at is None
    assert handle.started_at


def test_create_gives_each_run_a_distinct_id() -> None:
    """실행마다 서로 다른 ID 를 준다."""
    registry = runs.RunRegistry()
    first = registry.create("u1", "v1", ("q",))
    second = registry.create("u2", "v2", ("q",))
    assert first.run_id != second.run_id


def test_get_returns_none_for_unknown_id() -> None:
    """없는 ID 를 조회하면 None 을 돌려준다."""
    registry = runs.RunRegistry()
    assert registry.get("없는-id") is None


def test_append_progress_accumulates_messages() -> None:
    """진행 문구가 순서대로 쌓인다."""
    registry = runs.RunRegistry()
    handle = registry.create("u", "v", ("q",))
    registry.append_progress(handle.run_id, "1단계")
    registry.append_progress(handle.run_id, "2단계")
    stored = registry.get(handle.run_id)
    assert stored is not None
    assert stored.progress == ["1단계", "2단계"]


def test_append_progress_ignores_unknown_id() -> None:
    """없는 ID 에 진행을 기록해도 예외를 던지지 않는다."""
    registry = runs.RunRegistry()
    registry.append_progress("없는-id", "무시됨")


def test_finish_records_result_and_status() -> None:
    """완료하면 결과와 종료 시각이 남는다."""
    registry = runs.RunRegistry()
    handle = registry.create("u", "v", ("q",))
    result = make_result()
    registry.finish(handle.run_id, result)
    stored = registry.get(handle.run_id)
    assert stored is not None
    assert stored.status == "done"
    assert stored.result == result
    assert stored.finished_at
    assert stored.error_message is None


def test_fail_records_message_and_level() -> None:
    """실패하면 사용자 문구와 표시 수준이 남는다."""
    registry = runs.RunRegistry()
    handle = registry.create("u", "v", ("q",))
    registry.fail(handle.run_id, "자막이 없습니다.", "info")
    stored = registry.get(handle.run_id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_message == "자막이 없습니다."
    assert stored.error_level == "info"
    assert stored.result is None
    assert stored.finished_at


def test_running_count_counts_only_running_runs() -> None:
    """진행 중인 실행만 센다."""
    registry = runs.RunRegistry()
    first = registry.create("u1", "v1", ("q",))
    registry.create("u2", "v2", ("q",))
    assert registry.running_count() == 2
    registry.finish(first.run_id, make_result())
    assert registry.running_count() == 1


def test_list_all_puts_running_runs_first_in_start_order(
    monkeypatch,
) -> None:
    """진행 중인 실행이 끝난 실행보다 먼저, 넣은 순서대로 온다."""
    use_ticking_clock(monkeypatch)
    registry = runs.RunRegistry()
    done = registry.create("u0", "v0", ("q",))
    registry.finish(done.run_id, make_result())
    first = registry.create("u1", "v1", ("q",))
    second = registry.create("u2", "v2", ("q",))

    assert [item.run_id for item in registry.list_all()] == [
        first.run_id,
        second.run_id,
        done.run_id,
    ]


def test_list_all_puts_the_latest_finished_run_first(monkeypatch) -> None:
    """끝난 실행은 만든 순서가 아니라 최근에 끝난 것부터 온다."""
    use_ticking_clock(monkeypatch)
    registry = runs.RunRegistry()
    early = registry.create("u1", "v1", ("q",))
    late = registry.create("u2", "v2", ("q",))
    registry.finish(late.run_id, make_result())
    registry.fail(early.run_id, "실패", "error")

    assert [item.run_id for item in registry.list_all()] == [
        early.run_id,
        late.run_id,
    ]


def test_list_all_puts_the_newer_run_first_on_a_finish_tie(
    monkeypatch,
) -> None:
    """끝난 시각이 같으면 나중에 만든 실행이 앞에 온다."""
    monkeypatch.setattr(runs, "_now", lambda: "2026-09-30T10:00:00")
    registry = runs.RunRegistry()
    older = registry.create("u1", "v1", ("q",))
    newer = registry.create("u2", "v2", ("q",))
    registry.finish(older.run_id, make_result())
    registry.finish(newer.run_id, make_result())

    assert [item.run_id for item in registry.list_all()] == [
        newer.run_id,
        older.run_id,
    ]


def test_list_all_returns_copies() -> None:
    """목록이 돌려준 핸들을 바꿔도 레지스트리는 영향받지 않는다."""
    registry = runs.RunRegistry()
    handle = registry.create("u", "v", ("q",))
    borrowed = registry.list_all()[0]
    borrowed.progress.append("바깥에서 추가")
    borrowed.status = "done"
    stored = registry.get(handle.run_id)
    assert stored is not None
    assert stored.progress == []
    assert stored.status == "running"


def test_discard_removes_the_handle() -> None:
    """지운 실행은 목록에서 사라진다."""
    registry = runs.RunRegistry()
    handle = registry.create("u", "v", ("q",))
    registry.discard(handle.run_id)
    assert registry.get(handle.run_id) is None
    assert registry.list_all() == []


def test_discard_ignores_unknown_id() -> None:
    """없는 ID 를 지워도 예외를 던지지 않는다."""
    registry = runs.RunRegistry()
    registry.discard("없는-id")


def test_discard_finished_keeps_running_runs() -> None:
    """끝난 실행만 지우고 지운 수를 돌려준다."""
    registry = runs.RunRegistry()
    running = registry.create("u1", "v1", ("q",))
    done = registry.create("u2", "v2", ("q",))
    failed = registry.create("u3", "v3", ("q",))
    registry.finish(done.run_id, make_result())
    registry.fail(failed.run_id, "실패", "error")

    assert registry.discard_finished() == 2
    assert [item.run_id for item in registry.list_all()] == [running.run_id]


def test_discard_finished_on_an_empty_registry_returns_zero() -> None:
    """지울 것이 없으면 0 이다."""
    assert runs.RunRegistry().discard_finished() == 0


def test_finished_names_done_and_failed() -> None:
    """끝난 상태는 done 과 failed 둘이다."""
    assert frozenset({"done", "failed"}) == runs.FINISHED
