"""백그라운드 실행 시작 테스트."""

import pathlib
import sqlite3
from collections.abc import Iterator

import pytest
from notebooklm import exceptions
from notebooklm._auth import extraction as _auth_extraction

from notebooklm_st.core import models
from notebooklm_st.services import run_history, runner, runs, store

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


@pytest.fixture(autouse=True)
def _stub_metadata_fetch(monkeypatch) -> None:
    """``video_metadata.fetch`` 의 실호출을 막는다.

    메타데이터 동작 자체를 검증하는 테스트가 아니라면 실제 yt-dlp
    자식 프로세스를 부르지 않아야 한다. 메타데이터를 다루는 테스트는
    이 기본값을 자기 안에서 다시 ``monkeypatch.setattr`` 로 덮어쓴다.
    """
    monkeypatch.setattr(
        runner.video_metadata,
        "fetch",
        lambda url, **kwargs: runner.video_metadata.MetadataResult(
            models.VideoMetadata(channel=None, upload_date=None), None
        ),
    )


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
    assert handle.progress == ["영상 정보 확인 중", "자막 인덱싱 중"]
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

    monkeypatch.setattr(run_history, "save_run", broken_save)

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


def test_start_run_saves_the_fetched_metadata(db_path, monkeypatch) -> None:
    """조회한 메타데이터가 이력과 함께 저장된다."""
    monkeypatch.setattr(
        runner.video_metadata,
        "fetch",
        lambda url, **kwargs: runner.video_metadata.MetadataResult(
            models.VideoMetadata(channel="안될공학", upload_date="2026-09-15"),
            None,
        ),
    )
    registry = runs.RunRegistry()

    async def pipeline(url, questions, on_progress, **kwargs):
        """답변 하나를 돌려주는 가짜 파이프라인."""
        return models.RunResult(
            url=url,
            video_id="dQw4w9WgXcQ",
            title="어떤 영상",
            items=(
                models.AnswerItem(
                    question_title="제목1",
                    question_text="질문1",
                    answer="답",
                    citations=(),
                    error=None,
                ),
            ),
        )

    handle = runner.start_run(
        registry, URL, make_questions("질문1"), db_path, pipeline
    )
    wait_for(registry, handle.run_id)

    connection = store.connect(db_path)
    try:
        saved = run_history.list_runs(connection)
        metadata = run_history.load_metadata(connection, saved[0].id)
    finally:
        connection.close()
    assert metadata is not None
    assert metadata.channel == "안될공학"


def test_start_run_survives_a_metadata_failure(db_path, monkeypatch) -> None:
    """메타데이터 조회가 실패해도 요약은 끝까지 간다."""
    monkeypatch.setattr(
        runner.video_metadata,
        "fetch",
        lambda url, **kwargs: runner.video_metadata.MetadataResult(
            None, "영상 정보를 못 가져왔습니다."
        ),
    )
    registry = runs.RunRegistry()

    async def pipeline(url, questions, on_progress, **kwargs):
        """답변 하나를 돌려주는 가짜 파이프라인."""
        return models.RunResult(
            url=url,
            video_id="dQw4w9WgXcQ",
            title="어떤 영상",
            items=(
                models.AnswerItem(
                    question_title="제목1",
                    question_text="질문1",
                    answer="답",
                    citations=(),
                    error=None,
                ),
            ),
        )

    handle = runner.start_run(
        registry, URL, make_questions("질문1"), db_path, pipeline
    )
    finished = wait_for(registry, handle.run_id)

    assert finished.status == "done"
    connection = store.connect(db_path)
    try:
        saved = run_history.list_runs(connection)
        metadata = run_history.load_metadata(connection, saved[0].id)
    finally:
        connection.close()
    assert len(saved) == 1
    assert metadata is None
    assert any("못 가져왔습니다" in line for line in finished.progress)
