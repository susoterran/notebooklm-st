"""백그라운드 실행 시작 테스트."""

import pathlib
import sqlite3
from collections.abc import Iterator

import pytest
from notebooklm import exceptions
from notebooklm._auth import extraction as _auth_extraction

from notebooklm_st.core import models
from notebooklm_st.services import (
    outline,
    run_export,
    run_history,
    run_links,
    run_registry,
    runner,
    runs,
    store,
)

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


def wait_for(registry: run_registry.RunRegistry, run_id: str) -> runs.RunHandle:
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
    registry = run_registry.RunRegistry()

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
    registry = run_registry.RunRegistry()

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
    registry = run_registry.RunRegistry()

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
    registry = run_registry.RunRegistry()

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
    registry = run_registry.RunRegistry()

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
    registry = run_registry.RunRegistry()

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
    registry = run_registry.RunRegistry()

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
    registry = run_registry.RunRegistry()

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


def test_start_run_survives_a_metadata_fetch_raising(
    db_path, monkeypatch
) -> None:
    """메타데이터 조회가 예외를 던져도 실행은 끝까지 간다.

    ``fetch`` 는 실패를 값으로 돌려주는 계약이지만, 그 계약이
    깨져 예외가 새는 경우까지 ``_fetch_metadata`` 가 막아 주는지
    이 테스트로 못박는다.
    """

    def raise_error(url, **kwargs):
        """예외를 던지는 가짜 조회 함수."""
        raise RuntimeError("boom")

    monkeypatch.setattr(runner.video_metadata, "fetch", raise_error)
    registry = run_registry.RunRegistry()

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
    finally:
        connection.close()
    assert len(saved) == 1


def test_start_run_survives_a_metadata_failure(db_path, monkeypatch) -> None:
    """메타데이터 조회가 실패해도 요약은 끝까지 간다."""
    monkeypatch.setattr(
        runner.video_metadata,
        "fetch",
        lambda url, **kwargs: runner.video_metadata.MetadataResult(
            None, "영상 정보를 못 가져왔습니다."
        ),
    )
    registry = run_registry.RunRegistry()

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


DOC_URL = "http://192.168.0.10:3000/doc/x"


def set_outline_env(monkeypatch) -> None:
    """자동 저장이 Outline 에 닿도록 설정을 채운다."""
    monkeypatch.setenv(outline.URL_ENV_VAR, "http://192.168.0.10:3000")
    monkeypatch.setenv(outline.TOKEN_ENV_VAR, "ol_secret")
    monkeypatch.setenv(outline.COLLECTION_ENV_VAR, "col-1")


def record_create(monkeypatch) -> list[tuple[str, str]]:
    """``outline.create_document`` 를 막고 제목과 본문을 기록한다."""
    calls: list[tuple[str, str]] = []

    def create(config, title, markdown, **kwargs):
        """호출을 기록하고 만들어진 문서를 돌려준다."""
        calls.append((title, markdown))
        return outline.SavedDocument(id="doc-1", title=title, url=DOC_URL)

    monkeypatch.setattr(outline, "create_document", create)
    return calls


def answering(title: str | None = "어떤 영상", error: str | None = None):
    """인용 달린 답변 하나를 돌려주는 가짜 파이프라인을 만든다.

    오류를 주면 그 답변이 실패한 결과를 돌려준다.
    """

    async def pipeline(url, questions, on_progress, **kwargs):
        """정해 둔 결과를 돌려준다."""
        citations = (models.Citation(number=1, text="근거 구절", score=0.9),)
        return models.RunResult(
            url=url,
            video_id="dQw4w9WgXcQ",
            title=title,
            items=(
                models.AnswerItem(
                    question_title=questions[0].title,
                    question_text=questions[0].text,
                    answer=None if error else "세 가지다 [1].",
                    citations=() if error else citations,
                    error=error,
                ),
            ),
        )

    return pipeline


def auto_saved(db_path, pipeline) -> runs.RunHandle:
    """자동 저장을 켜고 실행해 끝난 핸들을 돌려준다."""
    registry = run_registry.RunRegistry()
    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        pipeline,
        auto_save=True,
    )
    return wait_for(registry, started.run_id)


def saved_runs(db_path) -> list[models.RunSummary]:
    """이력 목록을 읽는다."""
    connection = store.connect(db_path)
    try:
        return run_history.list_runs(connection)
    finally:
        connection.close()


def test_auto_save_uploads_the_answer_without_citations(
    db_path, monkeypatch
) -> None:
    """켜면 인용을 뺀 본문이 올라가고 이력이 문서가 된다."""
    set_outline_env(monkeypatch)
    calls = record_create(monkeypatch)

    handle = auto_saved(db_path, answering())

    assert handle.status == "done"
    assert handle.save == runs.SaveOutcome("saved", "저장됨", DOC_URL)
    assert "Outline 에 저장 중" in handle.progress
    [(title, markdown)] = calls
    assert title == "어떤 영상"
    assert "세 가지다." in markdown
    assert "[1]" not in markdown
    assert "근거 구절" not in markdown
    run = saved_runs(db_path)[0]
    assert run.outline_url == DOC_URL
    assert run.answer_count == 0


def test_auto_save_strips_the_title(db_path, monkeypatch) -> None:
    """영상 제목의 앞뒤 공백은 문서 제목에서 빠진다."""
    set_outline_env(monkeypatch)
    calls = record_create(monkeypatch)

    auto_saved(db_path, answering(title="  어떤 영상  "))

    assert calls[0][0] == "어떤 영상"


def test_auto_save_skips_a_run_without_a_title(db_path, monkeypatch) -> None:
    """제목이 없으면 올리지 않고 이력에 미저장으로 남긴다."""
    set_outline_env(monkeypatch)
    calls = record_create(monkeypatch)

    handle = auto_saved(db_path, answering(title=None))

    assert handle.status == "done"
    assert handle.save == runs.SaveOutcome(
        "skipped", "미저장 · 제목 없음", None
    )
    assert calls == []
    run = saved_runs(db_path)[0]
    assert run.exported_at is None
    assert run.answer_count == 1


def test_auto_save_skips_a_partial_failure(db_path, monkeypatch) -> None:
    """답변 일부가 실패하면 올리지 않는다."""
    set_outline_env(monkeypatch)
    calls = record_create(monkeypatch)

    handle = auto_saved(db_path, answering(error="응답이 비어 있습니다."))

    assert handle.save == runs.SaveOutcome(
        "skipped", "미저장 · 답변 일부 실패", None
    )
    assert calls == []
    assert saved_runs(db_path)[0].exported_at is None


def test_auto_save_without_configuration_skips(db_path, monkeypatch) -> None:
    """Outline 설정이 없으면 건너뛰고 Outline 을 부르지 않는다."""
    calls = record_create(monkeypatch)

    handle = auto_saved(db_path, answering())

    assert handle.save == runs.SaveOutcome(
        "skipped", "미저장 · Outline 설정 없음", None
    )
    assert calls == []


def test_auto_save_reports_an_outline_failure(db_path, monkeypatch) -> None:
    """Outline 이 거부하면 실패로 적고 이력은 미저장으로 둔다."""
    set_outline_env(monkeypatch)

    def refuse(config, title, markdown, **kwargs):
        """항상 거부한다."""
        raise outline.OutlineError("토큰이 거부되었습니다.")

    monkeypatch.setattr(outline, "create_document", refuse)

    handle = auto_saved(db_path, answering())

    assert handle.status == "done"
    assert handle.save == runs.SaveOutcome(
        "failed", "미저장 · 저장 실패: 토큰이 거부되었습니다.", None
    )
    assert saved_runs(db_path)[0].exported_at is None


def test_auto_save_reports_a_document_it_could_not_record(
    db_path, monkeypatch
) -> None:
    """문서는 만들었는데 기록에 실패하면 링크와 경고를 싣는다."""
    set_outline_env(monkeypatch)
    record_create(monkeypatch)

    def boom(*args, **kwargs):
        """기록이 실패하는 상황을 만든다."""
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(run_links, "mark_exported", boom)

    handle = auto_saved(db_path, answering())

    assert handle.status == "done"
    assert handle.save is not None
    assert handle.save.state == "failed"
    assert handle.save.url == DOC_URL
    assert "다시 저장하면 문서가 둘이 됩니다." in handle.save.message
    assert saved_runs(db_path)[0].exported_at is None


def test_auto_save_skips_a_run_saved_elsewhere(db_path, monkeypatch) -> None:
    """이력 화면이 먼저 저장했거나 저장 중이면 건너뛴 것으로 적는다."""
    set_outline_env(monkeypatch)

    def conflict(*args, **kwargs):
        """이력 화면이 같은 실행을 올리고 있는 상황을 흉내 낸다."""
        raise run_export.SaveConflictError()

    monkeypatch.setattr(run_export, "save", conflict)

    handle = auto_saved(db_path, answering())

    assert handle.status == "done"
    assert handle.save == runs.SaveOutcome(
        "skipped", "이미 저장했거나 저장 중", None
    )


def test_auto_save_survives_an_unexpected_error(db_path, monkeypatch) -> None:
    """예상 못 한 예외가 나도 실행은 done 이고 이유가 남는다."""
    set_outline_env(monkeypatch)

    def broken(config, title, markdown, **kwargs):
        """응답 해석이 깨진 상황을 흉내 낸다."""
        raise KeyError("data")

    monkeypatch.setattr(outline, "create_document", broken)

    handle = auto_saved(db_path, answering())

    assert handle.status == "done"
    assert handle.save == runs.SaveOutcome(
        "failed", "미저장 · 예상 못 한 오류(KeyError)", None
    )


def test_run_without_auto_save_never_calls_outline(
    db_path, monkeypatch
) -> None:
    """끄면 Outline 을 부르지 않고 저장 결과도 없다."""
    set_outline_env(monkeypatch)
    calls = record_create(monkeypatch)
    registry = run_registry.RunRegistry()

    started = runner.start_run(
        registry, URL, make_questions("핵심 주장은?"), db_path, answering()
    )
    handle = wait_for(registry, started.run_id)

    assert handle.status == "done"
    assert handle.save is None
    assert calls == []
    assert "Outline 에 저장 중" not in handle.progress


def test_history_failure_skips_the_auto_save(db_path, monkeypatch) -> None:
    """이력 저장이 실패하면 올리지 않고 실행을 실패로 마감한다."""
    set_outline_env(monkeypatch)
    calls = record_create(monkeypatch)

    def broken_save(connection, result, metadata=None):
        """항상 실패하는 가짜 저장."""
        raise sqlite3.OperationalError("disk is full")

    monkeypatch.setattr(run_history, "save_run", broken_save)

    handle = auto_saved(db_path, answering())

    assert handle.status == "failed"
    assert handle.save is None
    assert calls == []


def test_a_hidden_run_is_still_auto_saved(db_path, monkeypatch) -> None:
    """도는 중에 목록에서 숨겨도 자동 저장은 끝까지 간다."""
    set_outline_env(monkeypatch)
    calls = record_create(monkeypatch)
    registry = run_registry.RunRegistry()
    answer = answering()

    async def hiding_pipeline(url, questions, on_progress, **kwargs):
        """돌던 중에 사람이 숨기기를 누른 것처럼 목록에서 지운다."""
        for handle in registry.list_all():
            registry.discard(handle.run_id)
        return await answer(url, questions, on_progress)

    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        hiding_pipeline,
        auto_save=True,
    )
    runner.join_all(timeout=5.0)

    assert registry.get(started.run_id) is None
    assert len(calls) == 1
    assert saved_runs(db_path)[0].outline_url == DOC_URL
