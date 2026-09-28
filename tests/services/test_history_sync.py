"""이력 동기화 계획·적용 테스트."""

import sqlite3
from collections.abc import Iterator

import pytest

from notebooklm_st.core import models
from notebooklm_st.services import (
    history_sync,
    run_history,
    run_history_sync,
    store,
)

SUMMARY_BODY = (
    "- 제목: 밸류에이션 강의\n"
    "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
    "\n---\n\n## 핵심 주장\n\n세 가지다.\n"
)


def make_run(run_id: int, outline_id: str) -> models.RunSummary:
    """저장된 실행 요약을 만든다."""
    return models.RunSummary(
        id=run_id,
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        title="밸류에이션 강의",
        created_at="2026-09-22T15:00:00",
        answer_count=0,
        outline_id=outline_id,
        outline_url=f"https://wiki.example.com/doc/{outline_id}",
        outline_title="정리한 제목",
        exported_at="2026-09-22T15:00:00",
    )


def make_document(
    doc_id: str,
    markdown: str = SUMMARY_BODY,
    title: str = "정리한 제목",
) -> models.ListedDocument:
    """목록에서 읽어 온 문서를 만든다."""
    return models.ListedDocument(
        id=doc_id,
        title=title,
        url=f"https://wiki.example.com/doc/{doc_id}",
        created_at="2026-09-25T10:00:00",
        markdown=markdown,
    )


def test_plan_deletes_a_run_whose_document_is_gone() -> None:
    """문서 목록에 없는 행은 삭제 대상이다."""
    result = history_sync.plan([make_run(1, "doc-1")], [])

    assert [run.id for run in result.deletes] == [1]
    assert result.creates == ()


def test_plan_creates_a_run_for_an_unlinked_summary() -> None:
    """영상 URL 줄이 있고 가리키는 행이 없는 문서는 생성 대상이다."""
    document = make_document("doc-9")

    result = history_sync.plan([], [document])

    assert len(result.creates) == 1
    create = result.creates[0]
    assert create.document is document
    assert create.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert create.video_id == "dQw4w9WgXcQ"
    assert result.deletes == ()


def test_plan_skips_a_document_without_a_source_url() -> None:
    """정리본·손으로 쓴 문서는 사유와 함께 건너뛴다."""
    document = make_document("doc-2", markdown="- 종류: 정리본\n")

    result = history_sync.plan([], [document])

    assert result.creates == ()
    assert [skip.reason for skip in result.skips] == [
        history_sync.SKIP_NO_SOURCE_URL
    ]
    assert result.skips[0].document is document


def test_plan_skips_a_document_whose_url_is_not_youtube() -> None:
    """영상 URL 줄은 있는데 ID 를 못 뽑으면 인식 불가다."""
    document = make_document(
        "doc-3", markdown="- 영상 URL: https://example.com/watch\n"
    )

    result = history_sync.plan([], [document])

    assert result.creates == ()
    assert [skip.reason for skip in result.skips] == [
        history_sync.SKIP_BAD_SOURCE_URL
    ]


def test_plan_leaves_a_matched_pair_alone() -> None:
    """행과 문서가 모두 있으면 아무것도 하지 않는다."""
    result = history_sync.plan([make_run(1, "doc-1")], [make_document("doc-1")])

    assert result.is_empty
    assert result.skips == ()


def test_plan_deletes_everything_when_outline_is_empty() -> None:
    """컬렉션이 비면 저장된 행 전부가 삭제 대상이다."""
    runs = [make_run(1, "doc-1"), make_run(2, "doc-2")]

    result = history_sync.plan(runs, [])

    assert [run.id for run in result.deletes] == [1, 2]


def test_plan_creates_both_documents_of_the_same_video() -> None:
    """같은 영상의 문서가 둘이면 둘 다 만든다. 합치지 않는다."""
    result = history_sync.plan(
        [], [make_document("doc-a"), make_document("doc-b")]
    )

    assert [create.document.id for create in result.creates] == [
        "doc-a",
        "doc-b",
    ]


def test_plan_leaves_two_runs_pointing_at_one_document_alone() -> None:
    """같은 문서를 가리키는 행이 둘이어도 정리하지 않는다."""
    runs = [make_run(1, "doc-1"), make_run(2, "doc-1")]

    result = history_sync.plan(runs, [make_document("doc-1")])

    assert result.is_empty


def test_plan_keeps_the_input_order() -> None:
    """삭제·생성·건너뜀 모두 입력 순서를 지킨다."""
    runs = [make_run(3, "gone-3"), make_run(1, "gone-1")]
    documents = [
        make_document("new-b"),
        make_document("skip-1", markdown="본문만\n"),
        make_document("new-a"),
    ]

    result = history_sync.plan(runs, documents)

    assert [run.id for run in result.deletes] == [3, 1]
    assert [c.document.id for c in result.creates] == ["new-b", "new-a"]
    assert [s.document.id for s in result.skips] == ["skip-1"]


def test_an_empty_plan_says_so() -> None:
    """건너뛴 것만 있어도 비어 있는 계획이다."""
    plan = models.SyncPlan(
        deletes=(),
        creates=(),
        skips=(
            models.SyncSkip(
                document=make_document("x", markdown="본문\n"),
                reason=history_sync.SKIP_NO_SOURCE_URL,
            ),
        ),
    )

    assert plan.is_empty


@pytest.fixture
def connection(tmp_path) -> Iterator[sqlite3.Connection]:
    """임시 파일 DB 커넥션을 열고 테스트 후 닫는다."""
    conn = store.connect(tmp_path / "test.db")
    yield conn
    conn.close()


def save_exported(connection: sqlite3.Connection, doc_id: str) -> int:
    """저장된 실행 하나를 DB 에 만든다."""
    run_id = run_history.save_run(
        connection,
        models.RunResult(
            url="https://youtu.be/dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
            title="원래 제목",
            items=(),
        ),
    )
    run_history.mark_exported(
        connection,
        run_id,
        document_id=doc_id,
        document_title="정리한 제목",
        document_url=f"https://wiki.example.com/doc/{doc_id}",
    )
    return run_id


def create_for(doc_id: str) -> models.SyncCreate:
    """문서 하나를 만들 계획 항목."""
    return models.SyncCreate(
        document=make_document(doc_id),
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
    )


def test_apply_deletes_and_creates_in_one_commit(connection) -> None:
    """삭제와 삽입이 함께 확정된다."""
    gone = save_exported(connection, "gone")
    kept = save_exported(connection, "kept")
    plan = models.SyncPlan(
        deletes=(make_run(gone, "gone"),),
        creates=(create_for("new-1"),),
        skips=(),
    )

    result = history_sync.apply(connection, plan)

    assert not connection.in_transaction
    assert result == history_sync.SyncResult(deleted=1, created=1)
    ids = {run.outline_id for run in run_history_sync.list_exported(connection)}
    assert ids == {"kept", "new-1"}
    assert kept in [
        run.id for run in run_history_sync.list_exported(connection)
    ]


class FailingRunInsert:
    """실행 삽입 문장에서만 터지는 커넥션 대역.

    나머지 호출은 진짜 커넥션이 그대로 처리한다. 삭제는 됐는데 삽입이
    죽는 상황을 재현한다.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """감쌀 진짜 커넥션을 받는다."""
        self._connection = connection

    def execute(self, sql, *args):
        """실행을 넣는 문장만 실패시킨다."""
        if "INSERT INTO runs" in sql:
            raise sqlite3.OperationalError("database is locked")
        return self._connection.execute(sql, *args)

    def __getattr__(self, name):
        """나머지 속성은 진짜 커넥션에 맡긴다."""
        return getattr(self._connection, name)


def test_apply_rolls_back_the_deletes_when_an_insert_fails(
    connection,
) -> None:
    """삽입이 죽으면 삭제도 되돌린다. 반쪽짜리 동기화는 없다."""
    gone = save_exported(connection, "gone")
    plan = models.SyncPlan(
        deletes=(make_run(gone, "gone"),),
        creates=(create_for("new-1"),),
        skips=(),
    )

    with pytest.raises(sqlite3.OperationalError):
        # FailingRunInsert 는 진짜 Connection 이 아니라 일부 호출만
        # 가로채는 대역이다. 구조적으로는 호환되지만 nominal 타입은
        # 아니므로 억제한다.
        failing = FailingRunInsert(connection)
        history_sync.apply(failing, plan)  # type: ignore[arg-type]

    ids = [run.outline_id for run in run_history_sync.list_exported(connection)]
    assert ids == ["gone"]


def test_apply_skips_a_document_that_is_already_linked(connection) -> None:
    """다른 탭이 먼저 저장한 문서는 만들지 않고 세지도 않는다."""
    save_exported(connection, "doc-1")
    plan = models.SyncPlan(deletes=(), creates=(create_for("doc-1"),), skips=())

    result = history_sync.apply(connection, plan)

    assert result.created == 0
    assert len(run_history_sync.list_exported(connection)) == 1


def test_apply_does_not_count_a_run_that_is_already_gone(
    connection,
) -> None:
    """다른 탭이 먼저 지운 행은 개수에 들어가지 않는다."""
    plan = models.SyncPlan(
        deletes=(make_run(999, "gone"),), creates=(), skips=()
    )

    result = history_sync.apply(connection, plan)

    assert result.deleted == 0


def test_apply_keeps_a_new_run_that_reused_a_deleted_id(
    connection,
) -> None:
    """낡은 계획은 같은 ID 를 다시 받은 미저장 실행을 지우지 않는다.

    ``runs.id`` 에는 AUTOINCREMENT 가 없어, 가장 큰 ID 의 행을 지우면
    다음 삽입이 그 ID 를 다시 받는다. 계획은 적용·취소 전까지 세션에
    남으므로, 그사이 사람이 그 행을 손으로 지우고 새로 실행할 수
    있다. 미저장 실행은 어떤 경우에도 지워지면 안 된다.
    """
    gone = save_exported(connection, "gone")
    stale = history_sync.plan(run_history_sync.list_exported(connection), [])
    assert [run.id for run in stale.deletes] == [gone]
    run_history.delete_run(connection, gone)
    reused = run_history.save_run(
        connection,
        models.RunResult(
            url="https://youtu.be/dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
            title="새 실행",
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
    assert reused == gone

    result = history_sync.apply(connection, stale)

    assert result.deleted == 0
    assert [run.id for run in run_history.list_runs(connection)] == [reused]
    items = run_history.load_run_items(connection, reused)
    assert [item.answer for item in items] == ["세 가지다."]


def test_apply_with_an_empty_plan_changes_nothing(connection) -> None:
    """빈 계획은 0·0 이다."""
    save_exported(connection, "doc-1")
    plan = models.SyncPlan(deletes=(), creates=(), skips=())

    result = history_sync.apply(connection, plan)

    assert result == history_sync.SyncResult(deleted=0, created=0)
    assert len(run_history_sync.list_exported(connection)) == 1
