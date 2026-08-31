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
