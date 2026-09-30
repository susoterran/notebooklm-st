"""대기열 워커 테스트 — 차례, 기다림, 멈춤과 재개."""

import asyncio
import pathlib
import threading
from collections.abc import Iterator

import pytest
from notebooklm import exceptions

from notebooklm_st.core import errors, models
from notebooklm_st.services import run_registry, runner, store

QUESTIONS = (
    models.Question(
        id=1,
        title="핵심 주장",
        text="핵심 주장은?",
        created_at="2026-09-30T10:00:00",
        updated_at="2026-09-30T10:00:00",
    ),
)

FIRST = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
SECOND = "https://www.youtube.com/watch?v=bbbbbbbbbbb"
THIRD = "https://www.youtube.com/watch?v=ccccccccccc"


@pytest.fixture
def db_path(tmp_path) -> Iterator[pathlib.Path]:
    """스키마가 준비된 임시 DB 경로를 준다."""
    path = tmp_path / "queue.db"
    store.connect(path).close()
    yield path


@pytest.fixture(autouse=True)
def _stub_metadata_fetch(monkeypatch) -> None:
    """``video_metadata.fetch`` 의 실호출(yt-dlp)을 막는다."""
    monkeypatch.setattr(
        runner.video_metadata,
        "fetch",
        lambda url, **kwargs: runner.video_metadata.MetadataResult(
            models.VideoMetadata(channel=None, upload_date=None), None
        ),
    )


def never_blocked() -> bool:
    """다른 일이 NotebookLM 을 쓰고 있지 않다."""
    return False


def answer(url: str) -> models.RunResult:
    """답변 하나가 든 결과를 만든다."""
    return models.RunResult(
        url=url,
        video_id=url[-11:],
        title=f"영상 {url[-11:]}",
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


def put(registry, db_path, url, pipeline, is_blocked=never_blocked):
    """자동 저장 없이 대기열에 넣는다."""
    return runner.enqueue(
        registry, url, QUESTIONS, db_path, False, is_blocked, pipeline
    )


def statuses(registry) -> dict[str, str]:
    """영상 ID 별 상태를 모은다."""
    return {item.video_id: item.status for item in registry.list_all()}


def test_queued_runs_take_turns_in_the_order_they_came(db_path) -> None:
    """연달아 넣어도 겹치지 않고 넣은 순서대로 하나씩 돈다."""
    registry = run_registry.RunRegistry()
    lock = threading.Lock()
    calls: list[str] = []
    inside = 0
    peak = 0

    async def pipeline(url, questions, on_progress, **kwargs):
        """동시에 몇 개가 안에 있는지 센다."""
        nonlocal inside, peak
        with lock:
            inside += 1
            peak = max(peak, inside)
            calls.append(url)
        await asyncio.sleep(0.05)
        with lock:
            inside -= 1
        return answer(url)

    for url in (FIRST, SECOND, THIRD):
        put(registry, db_path, url, pipeline)
    runner.join_all(timeout=5.0)

    assert calls == [FIRST, SECOND, THIRD]
    assert peak == 1
    assert set(statuses(registry).values()) == {"done"}


def test_a_later_run_waits_queued_while_one_runs(db_path) -> None:
    """앞 실행이 도는 동안 뒤에 넣은 실행은 대기로 선다."""
    registry = run_registry.RunRegistry()
    entered = threading.Event()
    release = threading.Event()

    async def pipeline(url, questions, on_progress, **kwargs):
        """첫 실행만 풀어 줄 때까지 붙잡는다."""
        if url == FIRST:
            entered.set()
            await asyncio.to_thread(release.wait, 5.0)
        return answer(url)

    put(registry, db_path, FIRST, pipeline)
    put(registry, db_path, SECOND, pipeline)
    assert entered.wait(5.0)

    assert statuses(registry) == {
        "aaaaaaaaaaa": "running",
        "bbbbbbbbbbb": "queued",
    }
    release.set()
    runner.join_all(timeout=5.0)
    assert set(statuses(registry).values()) == {"done"}


def test_the_worker_waits_while_something_else_uses_notebooklm(
    db_path, monkeypatch
) -> None:
    """정리본이 도는 동안에는 시작하지 않고 끝나면 이어 간다."""
    monkeypatch.setattr(runner, "_BLOCKED_POLL_SECONDS", 0.01)
    registry = run_registry.RunRegistry()
    blocked = threading.Event()
    blocked.set()
    polled = threading.Event()
    calls: list[str] = []

    def is_blocked() -> bool:
        """막혀 있는 동안 몇 번 물었는지 알린다."""
        polled.set()
        return blocked.is_set()

    async def pipeline(url, questions, on_progress, **kwargs):
        """호출을 기록한다."""
        calls.append(url)
        return answer(url)

    put(registry, db_path, FIRST, pipeline, is_blocked)
    assert polled.wait(5.0)

    assert calls == []
    assert statuses(registry) == {"aaaaaaaaaaa": "queued"}
    blocked.clear()
    runner.join_all(timeout=5.0)
    assert calls == [FIRST]
    assert statuses(registry) == {"aaaaaaaaaaa": "done"}


def failing_first(error: Exception, release: threading.Event):
    """첫 실행만 풀어 줄 때 ``error`` 로 실패하는 가짜를 만든다."""

    async def pipeline(url, questions, on_progress, **kwargs):
        """첫 실행은 뒤 항목이 다 들어올 때까지 기다렸다가 실패한다."""
        if url == FIRST:
            await asyncio.to_thread(release.wait, 5.0)
            raise error
        return answer(url)

    return pipeline


def test_a_login_failure_pauses_and_keeps_the_rest_queued(db_path) -> None:
    """다음 실행도 실패할 오류면 멈추고 남은 항목은 대기로 둔다."""
    registry = run_registry.RunRegistry()
    release = threading.Event()
    pipeline = failing_first(exceptions.AuthError("expired"), release)

    for url in (FIRST, SECOND, THIRD):
        put(registry, db_path, url, pipeline)
    release.set()
    runner.join_all(timeout=5.0)

    assert statuses(registry) == {
        "aaaaaaaaaaa": "failed",
        "bbbbbbbbbbb": "queued",
        "ccccccccccc": "queued",
    }
    assert registry.paused_reason() == errors.LOGIN_HINT
    assert registry.active_count() == 0


def test_resume_carries_on_with_the_waiting_runs(db_path) -> None:
    """원인을 푼 뒤 재개하면 남은 항목이 이어서 돈다."""
    registry = run_registry.RunRegistry()
    release = threading.Event()
    pipeline = failing_first(exceptions.RateLimitError("too many"), release)
    for url in (FIRST, SECOND, THIRD):
        put(registry, db_path, url, pipeline)
    release.set()
    runner.join_all(timeout=5.0)
    assert registry.paused_reason() is not None

    runner.resume(registry, db_path, never_blocked, pipeline)
    runner.join_all(timeout=5.0)

    assert statuses(registry) == {
        "aaaaaaaaaaa": "failed",
        "bbbbbbbbbbb": "done",
        "ccccccccccc": "done",
    }
    assert registry.paused_reason() is None


def test_a_failure_limited_to_one_video_does_not_pause(db_path) -> None:
    """그 영상에 한정된 실패는 멈추지 않고 다음 항목으로 간다."""
    registry = run_registry.RunRegistry()
    release = threading.Event()
    pipeline = failing_first(exceptions.SourceAddError(FIRST), release)

    for url in (FIRST, SECOND):
        put(registry, db_path, url, pipeline)
    release.set()
    runner.join_all(timeout=5.0)

    assert statuses(registry) == {
        "aaaaaaaaaaa": "failed",
        "bbbbbbbbbbb": "done",
    }
    assert registry.paused_reason() is None


class _Stop(BaseException):
    """워커 스레드를 죽이는 BaseException."""


@pytest.mark.filterwarnings(
    "ignore::pytest.PytestUnhandledThreadExceptionWarning"
)
def test_a_dead_worker_frees_its_slot(db_path) -> None:
    """워커가 BaseException 으로 죽어도 다음 넣기가 남은 것을 잇는다."""
    registry = run_registry.RunRegistry()
    release = threading.Event()
    calls: list[str] = []

    async def pipeline(url, questions, on_progress, **kwargs):
        """첫 실행은 뒤 항목이 들어온 뒤 워커를 죽인다."""
        calls.append(url)
        if url == FIRST:
            await asyncio.to_thread(release.wait, 5.0)
            raise _Stop()
        return answer(url)

    put(registry, db_path, FIRST, pipeline)
    put(registry, db_path, SECOND, pipeline)
    release.set()
    runner.join_all(timeout=5.0)
    assert statuses(registry) == {
        "aaaaaaaaaaa": "failed",
        "bbbbbbbbbbb": "queued",
    }

    put(registry, db_path, THIRD, pipeline)
    runner.join_all(timeout=5.0)

    assert calls == [FIRST, SECOND, THIRD]
    assert statuses(registry)["bbbbbbbbbbb"] == "done"
    assert statuses(registry)["ccccccccccc"] == "done"
