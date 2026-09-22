"""이력을 마크다운으로 옮기는 순수 함수 테스트."""

from notebooklm_st.core import markdown_export, models


def make_summary(
    title: str | None = "어떻게 AI는 생각하는가",
    video_id: str = "dQw4w9WgXcQ",
) -> models.RunSummary:
    """테스트용 실행 요약을 만든다."""
    return models.RunSummary(
        id=1,
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id=video_id,
        title=title,
        created_at="2026-08-31T14:02:11",
        answer_count=1,
    )


def make_item(
    answer: str | None = "세 가지다.",
    citations: tuple[models.Citation, ...] = (),
    error: str | None = None,
) -> models.AnswerItem:
    """테스트용 답변 항목을 만든다."""
    return models.AnswerItem(
        question_title="핵심 주장",
        question_text="핵심 주장은?",
        answer=answer,
        citations=citations,
        error=error,
    )


DEFAULT_TITLE = "어떻게 AI는 생각하는가"


def export(
    summary=None,
    items=None,
    title=DEFAULT_TITLE,
    metadata=None,
) -> str:
    """새 시그니처로 문서를 만든다."""
    return markdown_export.to_markdown(
        summary if summary is not None else make_summary(),
        items if items is not None else [make_item()],
        title,
        metadata,
    )


def test_to_markdown_opens_with_the_metadata_list() -> None:
    """문서는 메타데이터 리스트로 시작한다.

    YAML frontmatter 를 쓰지 않는다. CommonMark 에서 문단 바로 뒤의
    ``---`` 는 구분선이 아니라 setext H2 밑줄이라, Outline 이 네 줄을
    통째로 머리글 하나로 뭉쳐 버린다(실측).
    """
    lines = export().splitlines()

    assert lines[0] == "- 제목: 어떻게 AI는 생각하는가"
    assert lines[1] == "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_to_markdown_separates_metadata_from_the_body() -> None:
    """메타데이터와 본문 사이에 구분선을 둔다.

    앞이 문단이 아니라 리스트이고 빈 줄이 끼어 있어, 이 ``---`` 는
    setext 밑줄이 될 수 없고 구분선으로 렌더된다.
    """
    lines = export().splitlines()
    rule = lines.index("---")

    assert lines[rule - 1] == ""
    assert lines[rule + 1] == ""
    assert lines[rule + 2].startswith("## ")


def test_to_markdown_writes_the_confirmed_title() -> None:
    """확인한 제목이 리스트에 들어간다. 저장된 옛 제목은 쓰지 않는다."""
    text = export(
        summary=make_summary(title="저장된 옛 제목"), title="사람이 고친 제목"
    )

    assert "- 제목: 사람이 고친 제목" in text
    assert "저장된 옛 제목" not in text


def test_to_markdown_writes_no_heading_for_the_document_title() -> None:
    """H1 을 넣지 않는다. Outline 이 문서 제목을 따로 가진다."""
    assert "# 어떻게 AI는 생각하는가" not in export()


def test_to_markdown_writes_the_question_title_and_answer() -> None:
    """질문 제목은 머리글로, 답변 본문은 그대로 쓴다."""
    text = export()

    assert "## 핵심 주장" in text
    assert "세 가지다." in text


def test_to_markdown_leaves_the_question_text_out() -> None:
    """질문 원문은 문서에 싣지 않는다.

    화면의 접은 영역에는 그대로 남는다. 위키에 올리는 것은 답변이지
    무엇을 물었는지의 기록이 아니다.
    """
    item = models.AnswerItem(
        question_title="핵심 주장",
        question_text="핵심 주장은 무엇인가요?",
        answer="세 가지다.",
        citations=(),
        error=None,
    )

    text = export(items=[item])

    assert "핵심 주장은 무엇인가요?" not in text
    assert ">" not in text


def test_to_markdown_writes_no_source_block() -> None:
    """출처·실행 줄을 따로 두지 않는다. URL 은 리스트에 이미 있다."""
    text = export()

    assert "- 출처:" not in text
    assert "- 실행:" not in text
    assert "2026-08-31T14:02:11" not in text


def test_to_markdown_lists_citations() -> None:
    """인용이 있으면 건수를 단 절로 모아 적는다."""
    item = make_item(
        citations=(models.Citation(number=1, text="근거 구절", score=0.9),)
    )

    text = export(items=[item])

    assert "### 인용 1건" in text
    assert "- **[1]** 근거 구절" in text


def test_to_markdown_omits_the_citation_section_when_empty() -> None:
    """인용이 없으면 인용 절 자체를 쓰지 않는다."""
    assert "인용" not in export()


def test_to_markdown_marks_a_failed_item() -> None:
    """답변을 못 받은 항목은 사유를 적는다."""
    item = make_item(answer=None, error="응답이 비어 있습니다.")

    text = export(items=[item])

    assert "**답변을 받지 못했습니다:** 응답이 비어 있습니다." in text


def test_to_markdown_ends_with_a_single_newline() -> None:
    """파일 끝은 줄바꿈 하나로 정리한다."""
    text = export()

    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_to_markdown_lists_only_what_it_knows() -> None:
    """메타데이터가 없으면 제목과 URL 두 줄만 나온다."""
    lines = export().splitlines()

    assert lines[:2] == [
        "- 제목: 어떻게 AI는 생각하는가",
        "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ]
    assert lines[2] == ""


def test_to_markdown_lists_all_four_when_known() -> None:
    """채널명과 업로드일자가 있으면 네 줄이 된다."""
    metadata = models.VideoMetadata(
        channel="안될공학", upload_date="2026-09-15"
    )

    lines = export(metadata=metadata).splitlines()

    assert lines[:4] == [
        "- 제목: 어떻게 AI는 생각하는가",
        "- 채널: 안될공학",
        "- 업로드 일자: 2026-09-15",
        "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ]


def test_to_markdown_omits_items_without_values() -> None:
    """값이 없는 항목은 줄째 빠진다. "모름" 을 지어내지 않는다."""
    metadata = models.VideoMetadata(channel=None, upload_date="2026-09-15")

    text = export(metadata=metadata)

    assert "- 채널:" not in text
    assert "- 업로드 일자: 2026-09-15" in text


def test_to_markdown_writes_values_without_quotes() -> None:
    """따옴표로 감싸지 않는다. YAML 이 아니라 읽으라고 적는 리스트다."""
    text = export(title='그는 "생각"한다')

    assert '- 제목: 그는 "생각"한다' in text


def test_to_markdown_strips_del_and_c1_controls() -> None:
    """DEL 과 C1 제어문자는 지운다.

    영상 제목은 제3자 문자열이라 이 범위가 섞여 들어올 수 있다.
    """
    text = export(title="제목\x7f안\x85녕")

    assert text.splitlines()[0] == "- 제목: 제목안녕"


def test_to_markdown_folds_a_newline_into_a_space() -> None:
    """개행이 든 값은 한 줄로 접는다. 그대로 두면 리스트가 깨진다."""
    metadata = models.VideoMetadata(channel="안될\n공학", upload_date=None)

    text = export(metadata=metadata)

    assert "- 채널: 안될 공학" in text


def test_to_markdown_keeps_a_raw_url_without_a_video_id() -> None:
    """영상 ID 가 없는 옛 이력은 저장된 URL 을 그대로 쓴다."""
    text = export(summary=make_summary(video_id=""))

    assert "- 영상 URL: https://youtu.be/dQw4w9WgXcQ" in text
