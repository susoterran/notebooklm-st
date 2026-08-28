"""백그라운드 실행 시작 테스트."""

import pathlib
import sqlite3
from collections.abc import Iterator

import pytest
from notebooklm import exceptions
from notebooklm._auth import extraction as _auth_extraction

from notebooklm_st.core import models
from notebooklm_st.services import runner, runs, store

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture
def db_path(tmp_path) -> Iterator[pathlib.Path]:
    """스키마가 준비된 임시 DB 경로를 준다."""
    path = tmp_path / "runner.db"
    connection = store.connect(path)
    connection.close()
    yield path


def make_questions(*texts: str) -> list[models.Question]:
    """테스트용 질문 목록을 만든다."""
    return [
        models.Question(
            id=index,
            title=f"제목{index}",
            text=text,
            created_at="2026-08-28T10:00:00",
            updated_at="2026-08-28T10:00:00",
        )
        for index, text in enumerate(texts, start=1)
    ]


def wait_for(registry: runs.RunRegistry, run_id: str) -> runs.RunHandle:
    """실행이 끝날 때까지 기다렸다가 핸들을 돌려준다."""
    runner.join_all(timeout=5.0)
    handle = registry.get(run_id)
    assert handle is not None
    assert handle.status != "running"
    return handle


def test_successful_run_saves_history_and_marks_done(db_path) -> None:
    """성공하면 이력에 저장하고 done 으로 표시한다."""
    registry = runs.RunRegistry()

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """진행 문구를 남기고 결과를 돌려주는 가짜."""
        on_progress("자막 인덱싱 중")
        return models.RunResult(
            url=url,
            video_id="dQw4w9WgXcQ",
            items=(
                models.AnswerItem(
                    question_title=questions[0].title,
                    question_text=questions[0].text,
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                ),
            ),
        )

    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        pipeline=fake_pipeline,
    )
    handle = wait_for(registry, started.run_id)

    assert handle.status == "done"
    assert handle.result is not None
    assert handle.progress == ["자막 인덱싱 중"]
    connection = sqlite3.connect(db_path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    finally:
        connection.close()
    assert count == 1


def test_library_error_is_recorded_as_user_message(db_path) -> None:
    """라이브러리 예외는 사용자 문구로 바뀌어 기록된다."""
    registry = runs.RunRegistry()

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """항상 자막 없음 예외를 던지는 가짜."""
        raise exceptions.SourceAddError(url)

    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        pipeline=fake_pipeline,
    )
    handle = wait_for(registry, started.run_id)

    assert handle.status == "failed"
    assert handle.error_level == "info"
    assert "자막" in (handle.error_message or "")


def test_unexpected_error_does_not_leave_the_run_running(db_path) -> None:
    """예상 못 한 예외가 나도 실행이 running 에 머물지 않는다."""
    registry = runs.RunRegistry()

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """라이브러리 예외가 아닌 오류를 던지는 가짜."""
        raise RuntimeError("예상 못 한 오류")

    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        pipeline=fake_pipeline,
    )
    handle = wait_for(registry, started.run_id)

    assert handle.status == "failed"
    assert handle.error_level == "error"
    assert handle.error_message


def test_failed_run_is_not_saved_to_history(db_path) -> None:
    """실패한 실행은 이력에 남기지 않는다."""
    registry = runs.RunRegistry()

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """항상 실패하는 가짜."""
        raise exceptions.SourceAddError(url)

    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        pipeline=fake_pipeline,
    )
    wait_for(registry, started.run_id)

    connection = sqlite3.connect(db_path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    finally:
        connection.close()
    assert count == 0


def test_video_id_is_extracted_from_the_url(db_path) -> None:
    """핸들에 URL 에서 뽑은 영상 ID 가 담긴다."""
    registry = runs.RunRegistry()

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """즉시 빈 결과를 돌려주는 가짜."""
        return models.RunResult(url=url, video_id="", items=())

    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        pipeline=fake_pipeline,
    )
    wait_for(registry, started.run_id)
    assert started.video_id == "dQw4w9WgXcQ"


def test_save_failure_marks_the_run_as_failed(db_path, monkeypatch) -> None:
    """이력 저장이 실패해도 실행이 running 에 머물지 않는다."""
    registry = runs.RunRegistry()

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """정상 결과를 돌려주는 가짜."""
        return models.RunResult(url=url, video_id="dQw4w9WgXcQ", items=())

    def broken_save(connection, result):
        """항상 실패하는 가짜 저장."""
        raise sqlite3.OperationalError("disk is full")

    monkeypatch.setattr(store, "save_run", broken_save)

    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        pipeline=fake_pipeline,
    )
    handle = wait_for(registry, started.run_id)

    assert handle.status == "failed"
    assert handle.error_level == "error"
    assert "이력 저장" in (handle.error_message or "")


def test_login_redirect_is_reported_as_a_login_hint(db_path) -> None:
    """로그인 리다이렉트는 재로그인 안내로 보여 준다.

    라이브러리가 이 예외를 ``NotebookLMError`` 로 감싸지 않으므로 넓은
    핸들러로 새면 "예상 못 한 오류" 와 함께 구글 URL 이 화면에 노출된다.
    """
    registry = runs.RunRegistry()

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """토큰 조회가 로그인 화면으로 튕긴 상황을 흉내 내는 가짜."""
        raise _auth_extraction._LoginRedirectError(
            "Authentication expired or invalid."
            " Final URL: https://accounts.google.com/x"
        )

    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        pipeline=fake_pipeline,
    )
    handle = wait_for(registry, started.run_id)

    assert handle.status == "failed"
    assert handle.error_level == "error"
    assert "notebooklm login" in (handle.error_message or "")
    assert "accounts.google.com" not in (handle.error_message or "")
