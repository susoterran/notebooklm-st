"""Outline 저장 한 벌 테스트."""

import dataclasses
import sqlite3
import threading
from collections.abc import Iterator

import pytest

from notebooklm_st.core import models
from notebooklm_st.services import outline, run_export, run_history, store

CONFIG = outline.OutlineConfig(
    base_url="http://192.168.0.10:3000",
    public_url="http://192.168.0.10:3000",
    token="ol_secret",
    collection_id="col-1",
)
DOC_URL = "http://192.168.0.10:3000/doc/x"


@pytest.fixture
def connection(tmp_path) -> Iterator[sqlite3.Connection]:
    """임시 파일 DB 커넥션을 열고 테스트 후 닫는다."""
    conn = store.connect(tmp_path / "export.db")
    yield conn
    conn.close()


def saved(connection: sqlite3.Connection) -> models.RunSummary:
    """답변 하나짜리 실행을 이력에 남기고 그 요약을 돌려준다."""
    run_history.save_run(
        connection,
        models.RunResult(
            url="https://youtu.be/dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
            title="어떤 영상",
            items=(
                models.AnswerItem(
                    question_title="핵심 주장",
                    question_text="핵심 주장은?",
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                ),
            ),
        ),
    )
    return run_history.list_runs(connection)[0]


def record_create(monkeypatch) -> list[tuple[str, str]]:
    """``outline.create_document`` 를 막고 제목과 본문을 기록한다."""
    calls: list[tuple[str, str]] = []

    def create(config, title, markdown, **kwargs):
        """호출을 기록하고 만들어진 문서를 돌려준다."""
        calls.append((title, markdown))
        return outline.SavedDocument(id="doc-1", title=title, url=DOC_URL)

    monkeypatch.setattr(outline, "create_document", create)
    return calls


def test_save_creates_the_document_and_drops_the_answers(
    connection, monkeypatch
) -> None:
    """문서를 만들고 링크를 적은 뒤 로컬 답변을 지운다."""
    calls = record_create(monkeypatch)
    summary = saved(connection)
    items = run_history.load_run_items(connection, summary.id)

    document = run_export.save(
        connection, CONFIG, summary, "고친 제목", items, None
    )

    assert document.url == DOC_URL
    [(title, markdown)] = calls
    assert title == "고친 제목"
    assert "- 제목: 고친 제목" in markdown
    assert "세 가지다." in markdown
    run = run_history.list_runs(connection)[0]
    assert run.outline_url == DOC_URL
    assert run.outline_title == "고친 제목"
    assert run_history.load_run_items(connection, summary.id) == []


def test_save_keeps_the_local_copy_when_outline_refuses(
    connection, monkeypatch
) -> None:
    """문서를 못 만들면 예외가 그대로 올라오고 로컬은 그대로다."""

    def refuse(config, title, markdown, **kwargs):
        """항상 거부한다."""
        raise outline.OutlineError("토큰이 거부되었습니다.")

    monkeypatch.setattr(outline, "create_document", refuse)
    summary = saved(connection)
    items = run_history.load_run_items(connection, summary.id)

    with pytest.raises(outline.OutlineError, match="토큰이 거부되었습니다"):
        run_export.save(connection, CONFIG, summary, "제목", items, None)

    assert run_history.list_runs(connection)[0].exported_at is None
    assert len(run_history.load_run_items(connection, summary.id)) == 1


def test_save_reports_a_document_it_could_not_record(
    connection, monkeypatch
) -> None:
    """기록이 실패하면 만들어진 문서를 담은 RecordError 가 난다."""
    record_create(monkeypatch)

    def boom(*args, **kwargs):
        """기록이 실패하는 상황을 만든다."""
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(run_history, "mark_exported", boom)
    summary = saved(connection)

    with pytest.raises(run_export.RecordError) as excinfo:
        run_export.save(connection, CONFIG, summary, "제목", [], None)

    assert excinfo.value.document.url == DOC_URL
    assert str(excinfo.value) == (
        f"문서는 만들어졌습니다: {DOC_URL} —"
        " 로컬 기록에 실패했습니다(OperationalError)."
        " 다시 저장하면 문서가 둘이 됩니다."
    )
    assert isinstance(excinfo.value.__cause__, sqlite3.OperationalError)


def test_save_wraps_an_unknown_run_as_a_record_error(
    connection, monkeypatch
) -> None:
    """이력에 없는 실행이면 기록의 ValueError 가 RecordError 가 된다."""
    record_create(monkeypatch)
    summary = dataclasses.replace(saved(connection), id=999)

    with pytest.raises(run_export.RecordError, match="ValueError"):
        run_export.save(connection, CONFIG, summary, "제목", [], None)


def test_save_does_not_swallow_a_programming_error(
    connection, monkeypatch
) -> None:
    """기록 단계의 프로그래밍 오류는 RecordError 로 감싸지 않는다.

    넓게 잡으면 리팩터링이 남긴 AttributeError 까지 "문서가 둘이
    됩니다" 로 둔갑해 진짜 버그가 드러나지 않는다.
    """
    record_create(monkeypatch)

    def boom(*args, **kwargs):
        """리팩터링이 남긴 버그를 흉내 낸다."""
        raise AttributeError("no attribute 'mark_exported'")

    monkeypatch.setattr(run_history, "mark_exported", boom)
    summary = saved(connection)

    with pytest.raises(AttributeError):
        run_export.save(connection, CONFIG, summary, "제목", [], None)


CONFLICT = (
    "이미 Outline 에 저장했거나 저장 중인 실행입니다."
    " 화면을 새로 고쳐 확인하세요."
)


def numbered_create(monkeypatch) -> list[str]:
    """``outline.create_document`` 를 막고 부를 때마다 새 문서를 만든다.

    문서마다 URL 이 달라 나중 쪽이 첫 링크를 덮었는지 가려낼 수 있다.
    """
    urls: list[str] = []

    def create(config, title, markdown, **kwargs):
        """번호 붙은 URL 로 문서를 만들고 그 URL 을 기록한다."""
        urls.append(f"{DOC_URL}{len(urls) + 1}")
        return outline.SavedDocument(id="doc-1", title=title, url=urls[-1])

    monkeypatch.setattr(outline, "create_document", create)
    return urls


def test_save_refuses_a_run_that_is_already_saved(
    connection, monkeypatch
) -> None:
    """이미 저장한 실행은 문서를 다시 만들지 않고 첫 링크를 지킨다.

    이력 화면이 들고 있는 요약은 저장 전의 것이다. 그래서 요약이 아니라
    DB 를 다시 읽어 가른다.
    """
    urls = numbered_create(monkeypatch)
    summary = saved(connection)
    run_export.save(connection, CONFIG, summary, "제목", [], None)

    with pytest.raises(run_export.SaveConflictError) as excinfo:
        run_export.save(connection, CONFIG, summary, "제목", [], None)

    assert str(excinfo.value) == CONFLICT
    assert urls == [f"{DOC_URL}1"]
    assert run_history.list_runs(connection)[0].outline_url == urls[0]


def test_save_refuses_a_second_save_while_the_first_is_uploading(
    connection, tmp_path, monkeypatch
) -> None:
    """먼저 올리는 쪽이 끝나기 전에 온 저장은 문서를 만들지 않는다.

    자동 저장(러너 스레드)이 올리는 동안 이력 화면의 버튼이 눌린
    경우다. 두 길은 커넥션이 따로라 첫 저장은 다른 스레드에서 자기
    커넥션으로 돌린다.
    """
    uploading = threading.Event()
    release = threading.Event()
    urls: list[str] = []

    def held_create(config, title, markdown, **kwargs):
        """첫 문서는 풀어 줄 때까지 붙잡아 둔다."""
        urls.append(f"{DOC_URL}{len(urls) + 1}")
        url = urls[-1]
        if len(urls) == 1:
            uploading.set()
            release.wait(timeout=5)
        return outline.SavedDocument(id="doc-1", title=title, url=url)

    monkeypatch.setattr(outline, "create_document", held_create)
    summary = saved(connection)
    documents: list[outline.SavedDocument] = []

    def first_save() -> None:
        """자기 커넥션을 열어 첫 저장을 돌린다."""
        own = store.connect(tmp_path / "export.db")
        try:
            documents.append(
                run_export.save(own, CONFIG, summary, "제목", [], None)
            )
        finally:
            own.close()

    thread = threading.Thread(target=first_save)
    thread.start()
    try:
        assert uploading.wait(timeout=5)
        with pytest.raises(run_export.SaveConflictError):
            run_export.save(connection, CONFIG, summary, "제목", [], None)
    finally:
        release.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert [document.url for document in documents] == [f"{DOC_URL}1"]
    assert urls == [f"{DOC_URL}1"]
    assert run_history.list_runs(connection)[0].outline_url == urls[0]


def test_save_releases_the_run_after_a_failure(connection, monkeypatch) -> None:
    """올리다 실패한 실행은 선점이 풀려 다시 저장할 수 있다."""

    def refuse(config, title, markdown, **kwargs):
        """항상 거부한다."""
        raise outline.OutlineError("토큰이 거부되었습니다.")

    monkeypatch.setattr(outline, "create_document", refuse)
    summary = saved(connection)
    with pytest.raises(outline.OutlineError):
        run_export.save(connection, CONFIG, summary, "제목", [], None)
    calls = record_create(monkeypatch)

    document = run_export.save(connection, CONFIG, summary, "제목", [], None)

    assert document.url == DOC_URL
    assert len(calls) == 1
