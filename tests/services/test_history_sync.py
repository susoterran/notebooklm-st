"""이력 동기화 계획·적용 테스트."""

from notebooklm_st.core import models
from notebooklm_st.services import history_sync

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
