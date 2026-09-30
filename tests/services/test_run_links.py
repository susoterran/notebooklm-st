"""실행의 Outline 문서 링크 기록 테스트."""

import sqlite3
from collections.abc import Iterator

import pytest

from notebooklm_st.core import models
from notebooklm_st.services import run_history, run_links, store


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


def export(connection, run_id: int) -> None:
    """테스트용 저장 기록 한 번."""
    run_links.mark_exported(
        connection,
        run_id,
        document_id="doc-1",
        document_title="정리한 제목",
        document_url="http://192.168.0.10:3000/doc/x",
    )


def test_mark_exported_writes_the_document_link(connection) -> None:
    """문서 ID·제목·URL 과 저장 시각이 남는다."""
    run_id = run_history.save_run(connection, make_result())

    export(connection, run_id)

    run = run_history.list_runs(connection)[0]
    assert run.outline_id == "doc-1"
    assert run.outline_title == "정리한 제목"
    assert run.outline_url == "http://192.168.0.10:3000/doc/x"
    assert run.exported_at is not None


def test_mark_exported_deletes_the_local_answers(connection) -> None:
    """진실의 원천을 하나로 둔다 — 본문은 Outline 에만 남는다."""
    run_id = run_history.save_run(connection, make_result())

    export(connection, run_id)

    assert run_history.load_run_items(connection, run_id) == []


def test_mark_exported_keeps_the_local_metadata(connection) -> None:
    """메타데이터는 남긴다. 정리본 재료 표가 채널·업로드일을 쓴다."""
    metadata = models.VideoMetadata(
        channel="안될공학", upload_date="2026-09-15"
    )
    run_id = run_history.save_run(connection, make_result(), metadata)

    export(connection, run_id)

    assert run_history.load_metadata(connection, run_id) == metadata


def test_mark_exported_keeps_the_run_itself(connection) -> None:
    """실행 행은 남는다. 링크를 걸어 둘 자리가 필요하다."""
    run_id = run_history.save_run(connection, make_result())

    export(connection, run_id)

    runs = run_history.list_runs(connection)
    assert len(runs) == 1
    assert runs[0].id == run_id
    assert runs[0].answer_count == 0


def test_mark_exported_rejects_an_unknown_run(connection) -> None:
    """없는 실행에 링크를 걸지 않는다."""
    with pytest.raises(ValueError):
        export(connection, 999)


def test_mark_exported_keeps_the_answers_of_an_unknown_run(
    connection,
) -> None:
    """실패하면 아무것도 지우지 않는다."""
    run_id = run_history.save_run(connection, make_result())

    with pytest.raises(ValueError):
        export(connection, 999)

    assert len(run_history.load_run_items(connection, run_id)) == 2


def test_mark_exported_refuses_an_already_saved_run(connection) -> None:
    """이미 저장된 실행의 링크를 다른 문서로 덮지 않는다."""
    run_id = run_history.save_run(connection, make_result())
    export(connection, run_id)

    with pytest.raises(ValueError, match="이미 저장되었습니다"):
        run_links.mark_exported(
            connection,
            run_id,
            document_id="doc-2",
            document_title="다른 제목",
            document_url="http://192.168.0.10:3000/doc/y",
        )

    run = run_history.list_runs(connection)[0]
    assert run.outline_url == "http://192.168.0.10:3000/doc/x"


class FailingAnswerDelete:
    """답변 삭제 문장에서만 터지는 커넥션 대역.

    나머지 호출은 진짜 커넥션이 그대로 처리한다. 잠긴 DB·디스크
    오류처럼 두 문장 중 뒤의 것에서 죽는 상황을 재현한다.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """감쌀 진짜 커넥션을 받는다."""
        self._connection = connection

    def execute(self, sql, *args):
        """답변을 지우는 문장만 실패시킨다."""
        if "DELETE FROM answers" in sql:
            raise sqlite3.OperationalError("database is locked")
        return self._connection.execute(sql, *args)

    def __getattr__(self, name):
        """나머지 속성은 진짜 커넥션에 맡긴다."""
        return getattr(self._connection, name)


def test_mark_exported_rolls_back_a_failed_delete(connection) -> None:
    """중간에 실패하면 링크도 남기지 않는다.

    커넥션은 앱 전체가 함께 쓴다. UPDATE 만 걸린 채로 예외가 나가면
    다음 조회가 그 실행을 저장된 것으로 그리고, 다른 곳의 commit 이
    반쪽짜리 내보내기를 확정해 버린다.
    """
    run_id = run_history.save_run(connection, make_result())

    with pytest.raises(sqlite3.OperationalError):
        export(FailingAnswerDelete(connection), run_id)

    assert run_history.list_runs(connection)[0].exported_at is None
    assert len(run_history.load_run_items(connection, run_id)) == 2
