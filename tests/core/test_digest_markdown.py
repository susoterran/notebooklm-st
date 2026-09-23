"""정리본을 문서 본문으로 옮기는 순수 함수 테스트."""

from notebooklm_st.core import digest_markdown, models

INSTRUCTION = "공통 주장과 엇갈리는 지점을 정리해 줘"


def make_source(
    run_id: int = 1,
    outline_title: str | None = "AI 에이전트의 미래",
    outline_url: str | None = "https://wiki.example.com/doc/ai-abc",
) -> models.RunSummary:
    """저장된 요약본 하나를 만든다."""
    return models.RunSummary(
        id=run_id,
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        title="영상 제목",
        created_at="2026-09-20T14:02:11",
        answer_count=0,
        outline_id=f"doc-{run_id}",
        outline_url=outline_url,
        outline_title=outline_title,
        exported_at="2026-09-20T15:00:00",
    )


def make_draft(
    body: str = "## 공통 주장\n\n셋 다 같은 말을 한다.",
    sources=None,
    instruction: str = INSTRUCTION,
) -> models.DigestDraft:
    """테스트용 초안을 만든다."""
    return models.DigestDraft(
        body=body,
        sources=tuple(sources if sources is not None else [make_source()]),
        instruction=instruction,
        created_on="2026-09-23",
    )


def test_document_has_no_h1() -> None:
    """Outline 이 제목을 따로 가지므로 H1 을 넣지 않는다."""
    document = digest_markdown.to_markdown(make_draft())

    assert not any(line.startswith("# ") for line in document.splitlines())


def test_metadata_lists_kind_date_and_instruction() -> None:
    """맨 앞이 종류·만든 날·정리 지시 세 줄이다."""
    document = digest_markdown.to_markdown(make_draft())

    lines = document.splitlines()
    assert lines[0] == "- 종류: 정리본"
    assert lines[1] == "- 만든 날: 2026-09-23"
    assert lines[2] == f"- 정리 지시: {INSTRUCTION}"


def test_sources_are_links() -> None:
    """출처가 원본 요약본 링크로 달린다."""
    document = digest_markdown.to_markdown(make_draft())

    assert "## 출처" in document
    assert (
        "- [AI 에이전트의 미래](https://wiki.example.com/doc/ai-abc)"
        in document
    )


def test_source_without_a_link_is_plain_text() -> None:
    """링크가 없는 옛 기록은 제목만 적는다."""
    draft = make_draft(sources=[make_source(outline_url=None)])

    document = digest_markdown.to_markdown(draft)

    assert "- AI 에이전트의 미래" in document
    assert "](" not in document


def test_source_falls_back_to_the_video_id() -> None:
    """문서 제목이 없으면 영상 ID 로 대신한다."""
    draft = make_draft(
        sources=[make_source(outline_title=None, outline_url=None)]
    )

    document = digest_markdown.to_markdown(draft)

    assert "- 영상 제목" in document


def test_rule_is_preceded_by_a_blank_line() -> None:
    """구분선 앞에 빈 줄이 있어야 setext 밑줄로 먹히지 않는다."""
    lines = digest_markdown.to_markdown(make_draft()).splitlines()

    index = lines.index("---")
    assert lines[index - 1] == ""


def test_instruction_newlines_are_folded() -> None:
    """여러 줄 지시가 리스트 항목을 두 동강 내지 않는다."""
    draft = make_draft(instruction="첫 줄\n둘째 줄")

    document = digest_markdown.to_markdown(draft)

    assert "- 정리 지시: 첫 줄 둘째 줄" in document


def test_control_characters_are_dropped() -> None:
    """제3자 문자열의 제어문자를 지운다."""
    draft = make_draft(instruction="앞\x85뒤")

    document = digest_markdown.to_markdown(draft)

    assert "- 정리 지시: 앞뒤" in document


def test_body_comes_last() -> None:
    """정리 본문이 구분선 뒤에 온다."""
    document = digest_markdown.to_markdown(make_draft())

    head, _, tail = document.partition("\n---\n")
    assert "## 공통" not in head
    assert "셋 다 같은 말을 한다." in tail
    assert document.endswith("\n")
