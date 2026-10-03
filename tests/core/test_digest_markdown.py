"""정리본을 문서 본문으로 옮기는 순수 함수 테스트."""

from notebooklm_st.core import digest_markdown, models

INSTRUCTION = "공통 주장과 엇갈리는 지점을 정리해 줘"

WATCH_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def make_source(
    run_id: int = 1,
    outline_title: str | None = "AI 에이전트의 미래",
    title: str | None = "영상 제목",
    video_id: str = "dQw4w9WgXcQ",
    url: str = "https://youtu.be/dQw4w9WgXcQ?si=share",
    categories: tuple[str, ...] = (),
) -> models.RunSummary:
    """저장된 요약본 하나를 만든다."""
    return models.RunSummary(
        id=run_id,
        url=url,
        video_id=video_id,
        title=title,
        created_at="2026-09-20T14:02:11",
        answer_count=0,
        outline_id=f"doc-{run_id}",
        outline_url=f"https://wiki.example.com/doc/summary-{run_id}",
        outline_title=outline_title,
        exported_at="2026-09-20T15:00:00",
        categories=categories,
    )


def make_draft(
    body: str = "## 공통 주장\n\n셋 다 같은 말을 한다.",
    sources=None,
) -> models.DigestDraft:
    """테스트용 초안을 만든다."""
    return models.DigestDraft(
        body=body,
        sources=tuple(sources if sources is not None else [make_source()]),
        instruction=INSTRUCTION,
        created_on="2026-09-23",
    )


def test_document_has_no_h1() -> None:
    """Outline 이 제목을 따로 가지므로 H1 을 넣지 않는다."""
    document = digest_markdown.to_markdown(make_draft())

    assert not any(line.startswith("# ") for line in document.splitlines())


def test_metadata_lists_kind_date_and_sources() -> None:
    """맨 앞이 종류·작성일자·출처 리스트이고 바로 빈 줄이 온다."""
    draft = make_draft(
        sources=[
            make_source(),
            make_source(
                run_id=2, outline_title="두 번째 글", video_id="9bZkp7q19f0"
            ),
        ]
    )

    lines = digest_markdown.to_markdown(draft).splitlines()

    assert lines[:6] == [
        "- 종류: 정리본",
        "- 작성일자: 2026-09-23",
        "- 출처:",
        f"    1. [AI 에이전트의 미래]({WATCH_URL})",
        "    2. [두 번째 글](https://www.youtube.com/watch?v=9bZkp7q19f0)",
        "",
    ]


def test_sources_have_no_heading() -> None:
    """출처는 메타데이터 항목이라 따로 머리글을 두지 않는다."""
    document = digest_markdown.to_markdown(make_draft())

    assert "## 출처" not in document


def test_sources_do_not_link_to_the_wiki() -> None:
    """요약본을 지우면 깨지므로 위키 문서로 잇지 않는다."""
    document = digest_markdown.to_markdown(make_draft())

    assert "wiki.example.com" not in document


def test_source_without_a_video_id_uses_the_stored_url() -> None:
    """영상 ID 가 없는 옛 기록은 저장된 URL 로 잇는다."""
    draft = make_draft(
        sources=[make_source(video_id="", url="https://youtu.be/old")]
    )

    lines = digest_markdown.to_markdown(draft).splitlines()

    assert "    1. [AI 에이전트의 미래](https://youtu.be/old)" in lines


def test_instruction_is_not_written() -> None:
    """정리 지시는 문서 어디에도 적지 않는다."""
    document = digest_markdown.to_markdown(make_draft())

    assert "정리 지시" not in document
    assert INSTRUCTION not in document


def test_source_uses_video_title_when_no_outline() -> None:
    """문서 제목이 없으면 영상 제목으로 대신한다."""
    draft = make_draft(sources=[make_source(outline_title=None)])

    lines = digest_markdown.to_markdown(draft).splitlines()

    assert f"    1. [영상 제목]({WATCH_URL})" in lines


def test_source_falls_back_to_the_video_id() -> None:
    """둘 다 없으면 영상 ID 로 대신한다."""
    draft = make_draft(sources=[make_source(outline_title=None, title=None)])

    lines = digest_markdown.to_markdown(draft).splitlines()

    assert f"    1. [dQw4w9WgXcQ]({WATCH_URL})" in lines


def test_rule_is_preceded_by_a_blank_line() -> None:
    """구분선 앞에 빈 줄이 있어야 setext 밑줄로 먹히지 않는다."""
    lines = digest_markdown.to_markdown(make_draft()).splitlines()

    index = lines.index("---")
    assert lines[index - 1] == ""


def test_body_comes_last() -> None:
    """정리 본문이 구분선 뒤에 온다."""
    document = digest_markdown.to_markdown(make_draft())

    head, _, tail = document.partition("\n---\n")
    assert "## 공통" not in head
    assert "셋 다 같은 말을 한다." in tail
    assert document.endswith("\n")


def test_the_categories_of_the_sources_follow_the_date() -> None:
    """재료들의 카테고리를 합쳐 중복을 빼고 이름 순으로 적는다."""
    draft = make_draft(
        sources=[
            make_source(categories=("인공지능", "경제")),
            make_source(run_id=2, categories=("경제", "정치")),
        ]
    )

    lines = digest_markdown.to_markdown(draft).splitlines()

    assert lines[:4] == [
        "- 종류: 정리본",
        "- 작성일자: 2026-09-23",
        "- 카테고리: 경제, 인공지능, 정치",
        "- 출처:",
    ]


def test_no_category_line_without_categories() -> None:
    """재료에 카테고리가 하나도 없으면 줄째 뺀다."""
    document = digest_markdown.to_markdown(make_draft())

    assert "- 카테고리:" not in document
