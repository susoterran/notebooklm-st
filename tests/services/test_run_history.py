"""실행 이력 저장소 테스트."""

import sqlite3
from collections.abc import Iterator

import pytest

from notebooklm_st.core import models
from notebooklm_st.services import run_history, store


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


def test_load_run_items_round_trips_question_title(connection) -> None:
    """답변에 저장한 질문 제목이 그대로 돌아온다."""
    run_id = run_history.save_run(connection, make_result())
    items = run_history.load_run_items(connection, run_id)
    titles = [item.question_title for item in items]
    assert titles == ["핵심 주장", "결론"]


def test_save_run_returns_run_id(connection) -> None:
    """실행을 저장하면 양수 ID 를 돌려준다."""
    run_id = run_history.save_run(connection, make_result())
    assert run_id > 0


def test_list_runs_counts_answers(connection) -> None:
    """실행 목록이 답변 개수를 센다."""
    run_history.save_run(connection, make_result())
    runs = run_history.list_runs(connection)
    assert len(runs) == 1
    assert runs[0].answer_count == 2
    assert runs[0].video_id == "dQw4w9WgXcQ"
    assert runs[0].created_at


def test_list_runs_returns_newest_first(connection) -> None:
    """실행 목록이 최신 것부터 돌려준다."""
    run_history.save_run(
        connection, make_result("https://youtu.be/aaaaaaaaaaa")
    )
    run_history.save_run(
        connection, make_result("https://youtu.be/bbbbbbbbbbb")
    )
    urls = [run.url for run in run_history.list_runs(connection)]
    assert urls == [
        "https://youtu.be/bbbbbbbbbbb",
        "https://youtu.be/aaaaaaaaaaa",
    ]


def test_list_runs_honors_limit(connection) -> None:
    """실행 목록이 limit 을 지킨다."""
    for _ in range(3):
        run_history.save_run(connection, make_result())
    assert len(run_history.list_runs(connection, limit=2)) == 2


def test_load_run_items_round_trips_answers_and_citations(
    connection,
) -> None:
    """실행의 답변과 인용을 왕복 저장한다."""
    run_id = run_history.save_run(connection, make_result())
    items = run_history.load_run_items(connection, run_id)
    assert [item.question_text for item in items] == [
        "핵심 주장은?",
        "결론은?",
    ]
    assert items[0].answer == "세 가지다."
    assert items[0].citations == (
        models.Citation(number=1, text="근거 구절", score=0.9),
    )
    assert items[0].succeeded is True
    assert items[1].answer is None
    assert items[1].error == "답변을 받지 못했습니다."
    assert items[1].citations == ()


def test_load_run_items_is_empty_for_unknown_run(connection) -> None:
    """알 수 없는 실행 ID 에 대해 빈 목록을 돌려준다."""
    assert run_history.load_run_items(connection, 999) == []


def test_run_with_no_answers_is_still_saved(connection) -> None:
    """답변이 없는 실행도 저장된다."""
    empty = models.RunResult(
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        items=(),
    )
    run_id = run_history.save_run(connection, empty)
    assert run_history.load_run_items(connection, run_id) == []
    assert run_history.list_runs(connection)[0].answer_count == 0


def test_list_runs_round_trips_the_video_title(connection) -> None:
    """저장한 영상 제목이 목록에 그대로 돌아온다."""
    run_history.save_run(connection, make_result(title="밸류에이션 강의"))
    assert run_history.list_runs(connection)[0].title == "밸류에이션 강의"


def test_list_runs_reports_a_missing_title_as_none(connection) -> None:
    """제목을 못 얻은 실행은 제목이 없는 채로 돌아온다."""
    run_history.save_run(connection, make_result())
    assert run_history.list_runs(connection)[0].title is None


def test_load_run_items_carries_the_answer_id(connection) -> None:
    """이력에서 읽은 답변은 자기 ID 를 들고 온다."""
    run_id = run_history.save_run(connection, make_result())

    items = run_history.load_run_items(connection, run_id)

    assert [item.id for item in items] == [1, 2]


def test_a_fresh_answer_item_has_no_id() -> None:
    """파이프라인이 갓 만든 항목은 아직 ID 가 없다."""
    item = models.AnswerItem(
        question_title="핵심 주장",
        question_text="핵심 주장은?",
        answer="세 가지다.",
        citations=(),
        error=None,
    )

    assert item.id is None


def test_delete_run_removes_its_answers_too(connection) -> None:
    """실행을 지우면 딸린 답변도 함께 사라진다."""
    run_id = run_history.save_run(connection, make_result())

    run_history.delete_run(connection, run_id)

    assert run_history.list_runs(connection) == []
    remaining = connection.execute(
        "SELECT COUNT(*) AS n FROM answers WHERE run_id = ?", (run_id,)
    ).fetchone()
    assert remaining["n"] == 0


def test_delete_run_keeps_other_runs(connection) -> None:
    """지정한 실행만 지운다."""
    kept = run_history.save_run(
        connection, make_result("https://youtu.be/aaaaaaaaaaa")
    )
    doomed = run_history.save_run(
        connection, make_result("https://youtu.be/bbbbbbbbbbb")
    )

    run_history.delete_run(connection, doomed)

    assert [run.id for run in run_history.list_runs(connection)] == [kept]


def test_delete_run_is_silent_for_an_unknown_id(connection) -> None:
    """이미 없는 실행을 지워도 조용히 넘어간다."""
    run_history.delete_run(connection, 999)


def test_save_run_stores_the_metadata(connection) -> None:
    """넘긴 메타데이터가 그대로 돌아온다."""
    metadata = models.VideoMetadata(
        channel="안될공학", upload_date="2026-09-15"
    )

    run_id = run_history.save_run(connection, make_result(), metadata)

    assert run_history.load_metadata(connection, run_id) == metadata


def test_save_run_without_metadata_stores_no_row(connection) -> None:
    """메타데이터를 안 넘기면 행을 만들지 않는다."""
    run_id = run_history.save_run(connection, make_result())

    assert run_history.load_metadata(connection, run_id) is None
    count = connection.execute(
        "SELECT COUNT(*) AS n FROM run_metadata"
    ).fetchone()
    assert count["n"] == 0


def test_load_metadata_is_silent_for_an_unknown_run(connection) -> None:
    """없는 실행 ID 로 물으면 None 이다."""
    assert run_history.load_metadata(connection, 9999) is None


def test_delete_run_removes_its_metadata_too(connection) -> None:
    """실행을 지우면 메타데이터도 함께 사라진다."""
    metadata = models.VideoMetadata(
        channel="안될공학", upload_date="2026-09-15"
    )
    run_id = run_history.save_run(connection, make_result(), metadata)

    run_history.delete_run(connection, run_id)

    assert run_history.load_metadata(connection, run_id) is None


def test_list_runs_reports_a_fresh_run_as_unexported(connection) -> None:
    """갓 저장한 실행에는 Outline 자리가 비어 있다."""
    run_history.save_run(connection, make_result())

    run = run_history.list_runs(connection)[0]

    assert run.exported_at is None
    assert run.outline_id is None
    assert run.outline_url is None
    assert run.outline_title is None


def test_list_runs_carries_the_document_link(connection) -> None:
    """DB 에 적힌 문서 링크가 요약에 실려 온다."""
    run_id = run_history.save_run(connection, make_result())
    connection.execute(
        "UPDATE runs SET outline_id = ?, outline_url = ?,"
        " outline_title = ?, exported_at = ? WHERE id = ?",
        (
            "doc-1",
            "http://192.168.0.10:3000/doc/x",
            "정리한 제목",
            "2026-09-22T15:00:00",
            run_id,
        ),
    )
    connection.commit()

    run = run_history.list_runs(connection)[0]

    assert run.outline_id == "doc-1"
    assert run.outline_url == "http://192.168.0.10:3000/doc/x"
    assert run.outline_title == "정리한 제목"
    assert run.exported_at == "2026-09-22T15:00:00"


def export(connection, run_id: int) -> None:
    """테스트용 저장 기록 한 번."""
    run_history.mark_exported(
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


def test_mark_exported_deletes_the_local_metadata(connection) -> None:
    """메타데이터도 문서 frontmatter 로 옮겨 갔으므로 지운다."""
    run_id = run_history.save_run(
        connection,
        make_result(),
        models.VideoMetadata(channel="안될공학", upload_date="2026-09-15"),
    )

    export(connection, run_id)

    assert run_history.load_metadata(connection, run_id) is None


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


class FailingAnswerDelete:
    """답변 삭제 문장에서만 터지는 커넥션 대역.

    나머지 호출은 진짜 커넥션이 그대로 처리한다. 잠긴 DB·디스크
    오류처럼 세 문장 중 가운데에서 죽는 상황을 재현한다.
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


def test_list_video_ids_returns_saved_ids(connection) -> None:
    """저장된 영상 ID 를 모두 돌려준다."""
    run_history.save_run(connection, make_result(title="하나"))

    assert run_history.list_video_ids(connection) == {"dQw4w9WgXcQ"}


def test_list_video_ids_drops_empty_ids(connection) -> None:
    """ID 를 못 뽑은 옛 실행의 빈 문자열은 빠진다.

    빈 문자열이 집합에 섞이면 ID 가 빈 피드 항목과 엉뚱하게
    맞부딪힌다.
    """
    run_history.save_run(
        connection,
        models.RunResult(
            url="https://example.com/not-youtube",
            video_id="",
            title="옛 실행",
            items=(),
        ),
    )

    assert run_history.list_video_ids(connection) == set()


def test_list_video_ids_deduplicates(connection) -> None:
    """같은 영상을 두 번 요약해도 하나로 온다."""
    for _ in range(2):
        run_history.save_run(connection, make_result(title="둘"))

    assert run_history.list_video_ids(connection) == {"dQw4w9WgXcQ"}
