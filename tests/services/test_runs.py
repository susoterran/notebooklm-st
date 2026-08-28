"""실행 레지스트리 테스트."""

from notebooklm_st.core import models
from notebooklm_st.services import runs


def make_result() -> models.RunResult:
    """테스트용 실행 결과를 만든다."""
    return models.RunResult(
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        items=(
            models.AnswerItem(
                question_text="핵심 주장은?",
                answer="세 가지다.",
                citations=(),
                error=None,
            ),
        ),
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


def test_list_all_is_newest_first() -> None:
    """가장 최근에 만든 실행이 목록 앞에 온다."""
    registry = runs.RunRegistry()
    first = registry.create("u1", "v1", ("q",))
    second = registry.create("u2", "v2", ("q",))
    assert [item.run_id for item in registry.list_all()] == [
        second.run_id,
        first.run_id,
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
