"""동기화용 이력 저장소 함수 테스트."""

import sqlite3
from collections.abc import Iterator

import pytest

from notebooklm_st.core import models
from notebooklm_st.services import (
    run_history,
    run_history_sync,
    run_links,
    store,
)


@pytest.fixture
def connection(tmp_path) -> Iterator[sqlite3.Connection]:
    """임시 파일 DB 커넥션을 열고 테스트 후 닫는다."""
    conn = store.connect(tmp_path / "test.db")
    yield conn
    conn.close()


def make_result(
    url: str = "https://youtu.be/dQw4w9WgXcQ",
    title: str | None = None,
) -> models.RunResult:
    """테스트용 실행 결과를 만든다."""
    return models.RunResult(
        url=url,
        video_id="dQw4w9WgXcQ",
        title=title,
        items=(
            models.AnswerItem(
                question_title="핵심 주장",
                question_text="핵심 주장은?",
                answer="세 가지다.",
                citations=(
                    models.Citation(number=1, text="근거 구절", score=0.9),
                ),
                error=None,
            ),
            models.AnswerItem(
                question_title="결론",
                question_text="결론은?",
                answer=None,
                citations=(),
                error="답변을 받지 못했습니다.",
            ),
        ),
    )


def export(
    connection: sqlite3.Connection, run_id: int, document_id: str = "doc-1"
) -> None:
    """테스트용 저장 기록 한 번."""
    run_links.mark_exported(
        connection,
        run_id,
        document_id=document_id,
        document_title="정리한 제목",
        document_url="http://192.168.0.10:3000/doc/x",
    )


def make_create(
    doc_id: str = "doc-9",
    video_id: str = "dQw4w9WgXcQ",
    metadata: models.VideoMetadata | None = None,
) -> models.SyncCreate:
    """동기화가 만들 이력 한 건."""
    document = models.ListedDocument(
        id=doc_id,
        title="되살린 제목",
        url=f"https://wiki.example.com/doc/{doc_id}",
        created_at="2026-09-25T10:00:00",
        markdown="- 영상 URL: x\n",
    )
    return models.SyncCreate(
        document=document,
        url=f"https://www.youtube.com/watch?v={video_id}",
        video_id=video_id,
        metadata=metadata,
    )


METADATA = models.VideoMetadata(channel="안될공학", upload_date="2026-09-15")


def exported_run(
    connection: sqlite3.Connection,
    metadata: models.VideoMetadata | None = None,
) -> int:
    """``doc-1`` 에 저장된 실행 하나를 만든다."""
    run_id = run_history.save_run(connection, make_result(), metadata)
    export(connection, run_id)
    return run_id


def test_list_exported_returns_only_exported_runs(connection) -> None:
    """미저장 실행은 빠진다. 삭제 대상이 될 수 없어야 한다."""
    run_history.save_run(connection, make_result(title="미저장"))
    exported_id = run_history.save_run(connection, make_result(title="저장"))
    export(connection, exported_id)

    result = run_history_sync.list_exported(connection)

    assert [run.id for run in result] == [exported_id]
    assert result[0].outline_id == "doc-1"


def test_list_exported_has_no_limit(connection) -> None:
    """동기화는 전부 봐야 한다. ``list_runs`` 의 50건 상한이 없다."""
    for _ in range(51):
        run_id = run_history.save_run(connection, make_result())
        export(connection, run_id)

    assert len(run_history_sync.list_exported(connection)) == 51


def test_insert_exported_fills_the_link_columns(connection) -> None:
    """여덟 컬럼이 채워진 저장된 행이 생긴다."""
    run_id = run_history_sync.insert_exported(connection, make_create())
    connection.commit()

    assert run_id is not None
    run = run_history_sync.list_exported(connection)[0]
    assert run.id == run_id
    assert run.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert run.video_id == "dQw4w9WgXcQ"
    assert run.title == "되살린 제목"
    assert run.created_at == "2026-09-25T10:00:00"
    assert run.outline_id == "doc-9"
    assert run.outline_url == "https://wiki.example.com/doc/doc-9"
    assert run.outline_title == "되살린 제목"
    assert run.exported_at == "2026-09-25T10:00:00"
    assert run.answer_count == 0


def test_insert_exported_writes_no_answers(connection) -> None:
    """저장된 실행은 본문이 없다."""
    run_id = run_history_sync.insert_exported(connection, make_create())
    connection.commit()

    assert run_id is not None
    assert run_history.load_run_items(connection, run_id) == []
    assert run_history.load_metadata(connection, run_id) is None


def test_insert_exported_skips_an_existing_document(connection) -> None:
    """같은 문서를 가리키는 행이 이미 있으면 넣지 않는다."""
    run_id = run_history.save_run(connection, make_result())
    export(connection, run_id)

    result = run_history_sync.insert_exported(connection, make_create("doc-1"))
    connection.commit()

    assert result is None
    assert len(run_history_sync.list_exported(connection)) == 1


def test_insert_exported_does_not_commit(connection) -> None:
    """트랜잭션은 호출자가 소유한다."""
    run_history_sync.insert_exported(connection, make_create())
    connection.rollback()

    assert run_history_sync.list_exported(connection) == []


def test_delete_runs_removes_several_at_once(connection) -> None:
    """여러 쌍을 한 번에 지우고 개수를 돌려준다."""
    first = run_history.save_run(connection, make_result())
    second = run_history.save_run(connection, make_result())
    third = run_history.save_run(connection, make_result())
    export(connection, first, "doc-1")
    export(connection, second, "doc-2")
    export(connection, third, "doc-3")

    deleted = run_history_sync.delete_runs(
        connection, [(first, "doc-1"), (third, "doc-3")]
    )
    connection.commit()

    assert deleted == 2
    assert [run.id for run in run_history.list_runs(connection)] == [second]


def test_delete_runs_ignores_unknown_ids(connection) -> None:
    """없는 ID 는 세지 않는다. 다른 탭이 먼저 지웠을 수 있다."""
    run_id = run_history.save_run(connection, make_result())
    export(connection, run_id)

    deleted = run_history_sync.delete_runs(
        connection, [(run_id, "doc-1"), (999, "doc-9")]
    )
    connection.commit()

    assert deleted == 1


def test_delete_runs_needs_the_document_id_to_match(connection) -> None:
    """ID 가 같아도 문서 ID 가 다르면 지우지 않는다.

    SQLite 는 지워진 가장 큰 ID 를 다음 삽입에 다시 준다. ID 만
    맞으면 지우면 그 ID 를 받은 다른 실행이 지워진다.
    """
    exported = run_history.save_run(connection, make_result())
    export(connection, exported, "doc-1")
    unexported = run_history.save_run(connection, make_result())

    deleted = run_history_sync.delete_runs(
        connection, [(exported, "doc-other"), (unexported, "doc-1")]
    )
    connection.commit()

    assert deleted == 0
    assert len(run_history.list_runs(connection)) == 2


def test_delete_runs_with_nothing_is_a_no_op(connection) -> None:
    """빈 목록은 0 이다."""
    run_history.save_run(connection, make_result())

    assert run_history_sync.delete_runs(connection, []) == 0
    assert len(run_history.list_runs(connection)) == 1


def test_delete_runs_does_not_commit(connection) -> None:
    """트랜잭션은 호출자가 소유한다."""
    run_id = run_history.save_run(connection, make_result())
    export(connection, run_id)

    run_history_sync.delete_runs(connection, [(run_id, "doc-1")])
    connection.rollback()

    assert len(run_history.list_runs(connection)) == 1


def test_list_video_ids_includes_a_revived_run(connection) -> None:
    """되살린 행의 영상 ID 도 채널 감시가 걸러야 한다."""
    run_history_sync.insert_exported(
        connection, make_create(video_id="aaaaaaaaaaa")
    )
    connection.commit()

    assert run_history.list_video_ids(connection) == {"aaaaaaaaaaa"}


def test_list_exported_carries_the_metadata(connection) -> None:
    """저장된 행의 메타데이터가 요약에 실려 온다."""
    exported_run(connection, METADATA)

    assert run_history_sync.list_exported(connection)[0].metadata == METADATA


def test_insert_exported_writes_the_metadata_it_read(connection) -> None:
    """문서에서 읽은 메타데이터로 ``run_metadata`` 행도 만든다."""
    run_id = run_history_sync.insert_exported(
        connection, make_create(metadata=METADATA)
    )
    connection.commit()

    assert run_id is not None
    assert run_history.load_metadata(connection, run_id) == METADATA


def test_insert_exported_writes_nothing_for_an_existing_document(
    connection,
) -> None:
    """이미 있는 문서면 메타데이터도 쓰지 않는다."""
    run_id = exported_run(connection)

    result = run_history_sync.insert_exported(
        connection, make_create("doc-1", metadata=METADATA)
    )
    connection.commit()

    assert result is None
    assert run_history.load_metadata(connection, run_id) is None


def test_write_metadata_inserts_a_missing_row(connection) -> None:
    """행이 없으면 넣고 ``True`` 다."""
    run_id = exported_run(connection)

    written = run_history_sync.write_metadata(
        connection, run_id, "doc-1", METADATA
    )
    connection.commit()

    assert written is True
    assert run_history.load_metadata(connection, run_id) == METADATA


def test_write_metadata_overwrites_a_different_row(connection) -> None:
    """값이 다르면 덮고 ``True`` 다."""
    run_id = exported_run(
        connection, models.VideoMetadata(channel="옛 채널", upload_date=None)
    )

    written = run_history_sync.write_metadata(
        connection, run_id, "doc-1", METADATA
    )
    connection.commit()

    assert written is True
    assert run_history.load_metadata(connection, run_id) == METADATA


def test_write_metadata_reports_an_unchanged_row(connection) -> None:
    """값이 이미 같으면 덮지 않고 ``False`` 다."""
    run_id = exported_run(connection, METADATA)

    written = run_history_sync.write_metadata(
        connection, run_id, "doc-1", METADATA
    )

    assert written is False
    assert run_history.load_metadata(connection, run_id) == METADATA


def test_write_metadata_needs_the_document_id_to_match(connection) -> None:
    """실행 ID 와 문서 ID 가 둘 다 맞아야 쓴다.

    SQLite 는 지워진 가장 큰 ID 를 다음 삽입에 다시 준다. 그 ID 를
    받은 미저장 실행에 남의 메타데이터가 쓰이면 안 된다.
    """
    exported = exported_run(connection)
    unexported = run_history.save_run(connection, make_result())

    wrong_document = run_history_sync.write_metadata(
        connection, exported, "doc-other", METADATA
    )
    unsaved = run_history_sync.write_metadata(
        connection, unexported, "doc-1", METADATA
    )
    connection.commit()

    assert wrong_document is False
    assert unsaved is False
    assert run_history.load_metadata(connection, exported) is None
    assert run_history.load_metadata(connection, unexported) is None


def test_write_metadata_does_not_commit(connection) -> None:
    """트랜잭션은 호출자가 소유한다."""
    run_id = exported_run(connection)

    run_history_sync.write_metadata(connection, run_id, "doc-1", METADATA)
    connection.rollback()

    assert run_history.load_metadata(connection, run_id) is None
