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


def test_to_markdown_opens_with_the_title_and_source() -> None:
    """Frontmatter 다음에 제목을 두고 출처와 실행 시각을 잇는다."""
    text = markdown_export.to_markdown(make_summary(), [make_item()])
    body = text.split("---\n", 2)[2]
    lines = body.splitlines()
    assert lines[1] == "# 어떻게 AI는 생각하는가"


def test_to_markdown_falls_back_to_video_id_without_a_title() -> None:
    """제목이 없으면 영상 ID 를 머리글로 쓴다."""
    text = markdown_export.to_markdown(make_summary(title=None), [make_item()])
    body = text.split("---\n", 2)[2]
    assert body.splitlines()[1] == "# dQw4w9WgXcQ"


def test_to_markdown_writes_question_and_answer() -> None:
    """질문 제목은 머리글로, 원문은 인용 블록으로, 본문은 그대로 쓴다."""
    text = markdown_export.to_markdown(make_summary(), [make_item()])
    assert "## 핵심 주장" in text
    assert "> 핵심 주장은?" in text
    assert "세 가지다." in text


def test_to_markdown_quotes_every_line_of_a_multiline_question() -> None:
    """여러 줄 질문 원문은 줄마다 인용 기호를 붙인다."""
    item = models.AnswerItem(
        question_title="핵심 주장",
        question_text="첫 줄\n둘째 줄",
        answer="답",
        citations=(),
        error=None,
    )
    text = markdown_export.to_markdown(make_summary(), [item])
    assert "> 첫 줄" in text
    assert "> 둘째 줄" in text


def test_to_markdown_lists_citations() -> None:
    """인용이 있으면 건수를 단 절로 모아 적는다."""
    item = make_item(
        citations=(models.Citation(number=1, text="근거 구절", score=0.9),)
    )
    text = markdown_export.to_markdown(make_summary(), [item])
    assert "### 인용 1건" in text
    assert "- **[1]** 근거 구절" in text


def test_to_markdown_omits_the_citation_section_when_empty() -> None:
    """인용이 없으면 인용 절 자체를 쓰지 않는다."""
    text = markdown_export.to_markdown(make_summary(), [make_item()])
    assert "인용" not in text


def test_to_markdown_marks_a_failed_item() -> None:
    """답변을 못 받은 항목은 사유를 적는다."""
    item = make_item(answer=None, error="응답이 비어 있습니다.")
    text = markdown_export.to_markdown(make_summary(), [item])
    assert "**답변을 받지 못했습니다:** 응답이 비어 있습니다." in text


def test_to_markdown_ends_with_a_single_newline() -> None:
    """파일 끝은 줄바꿈 하나로 정리한다."""
    text = markdown_export.to_markdown(make_summary(), [make_item()])
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_to_markdown_writes_frontmatter_without_metadata() -> None:
    """메타데이터가 없어도 title 과 url 은 나온다."""
    text = markdown_export.to_markdown(make_summary(), [make_item()])
    lines = text.splitlines()
    assert lines[0] == "---"
    assert lines[1] == 'title: "어떻게 AI는 생각하는가"'
    assert lines[2] == "url: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert lines[3] == "---"


def test_to_markdown_writes_all_metadata_keys() -> None:
    """채널명과 업로드일자가 있으면 네 줄이 된다."""
    metadata = models.VideoMetadata(
        channel="안될공학", upload_date="2026-09-15"
    )

    text = markdown_export.to_markdown(make_summary(), [make_item()], metadata)

    assert text.splitlines()[:6] == [
        "---",
        'title: "어떻게 AI는 생각하는가"',
        'channel: "안될공학"',
        "upload_date: 2026-09-15",
        "url: https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "---",
    ]


def test_to_markdown_omits_keys_without_values() -> None:
    """값이 없는 키는 null 이 아니라 아예 빠진다."""
    metadata = models.VideoMetadata(channel=None, upload_date="2026-09-15")

    text = markdown_export.to_markdown(make_summary(), [make_item()], metadata)

    assert "channel" not in text
    assert "upload_date: 2026-09-15" in text


def test_to_markdown_escapes_quotes_and_backslashes_in_the_title() -> None:
    """제목의 따옴표와 역슬래시가 YAML 을 깨뜨리지 않는다."""
    summary = make_summary(title='그는 "생각"한다 \\ 아마도')

    text = markdown_export.to_markdown(summary, [make_item()])

    assert text.splitlines()[1] == ('title: "그는 \\"생각\\"한다 \\\\ 아마도"')


def test_to_markdown_strips_del_and_c1_controls_from_the_title() -> None:
    """DEL 과 C1 제어문자도 YAML 스칼라에서 지워진다.

    PyYAML 은 DEL(0x7f)과 C1(0x80-0x9f) 대부분을 인쇄 불가로 보아
    ReaderError 를 던지고 0x85 는 줄바꿈으로 해석한다. 영상 제목은
    제3자 문자열이라 이 범위가 섞여 들어올 수 있다.
    """
    summary = make_summary(title="제목\x7f안\x85녕")

    text = markdown_export.to_markdown(summary, [make_item()])

    title_line = text.splitlines()[1]
    assert title_line == 'title: "제목안녕"'
    assert "\x7f" not in title_line
    assert "\x85" not in title_line


def test_to_markdown_escapes_newlines_in_the_channel() -> None:
    """개행이 든 값도 한 줄로 접힌다."""
    metadata = models.VideoMetadata(channel="안될\n공학", upload_date=None)

    text = markdown_export.to_markdown(make_summary(), [make_item()], metadata)

    assert 'channel: "안될\\n공학"' in text


def test_to_markdown_quotes_the_url_without_a_video_id() -> None:
    """영상 ID 가 없는 옛 이력은 저장된 URL 을 따옴표로 감싼다."""
    summary = make_summary(video_id="")

    text = markdown_export.to_markdown(summary, [make_item()])

    assert 'url: "https://youtu.be/dQw4w9WgXcQ"' in text


def test_to_markdown_keeps_the_body_unchanged() -> None:
    """Frontmatter 아래 본문은 출처 줄부터 그대로다."""
    text = markdown_export.to_markdown(make_summary(), [make_item()])

    assert "- 출처: https://youtu.be/dQw4w9WgXcQ" in text
    assert "- 실행: 2026-08-31T14:02:11" in text
    assert "## 핵심 주장" in text


def test_to_filename_uses_the_title() -> None:
    """제목에 확장자를 붙여 파일명으로 쓴다."""
    name = markdown_export.to_filename("밸류에이션 강의", "dQw4w9WgXcQ")
    assert name == "밸류에이션 강의.md"


def test_to_filename_replaces_forbidden_characters() -> None:
    """파일명에 못 쓰는 문자는 공백으로 바꾸고 겹친 공백을 접는다."""
    name = markdown_export.to_filename('어떻게? AI는: "생각"/판단', "vid")
    assert name == "어떻게 AI는 생각 판단.md"


def test_to_filename_strips_trailing_dots_and_spaces() -> None:
    """윈도우가 싫어하는 끝 마침표와 공백을 떼어 낸다."""
    name = markdown_export.to_filename("제목입니다... ", "vid")
    assert name == "제목입니다.md"


def test_to_filename_truncates_a_long_title() -> None:
    """제목이 아주 길면 잘라서 파일 시스템 한계를 넘지 않는다."""
    name = markdown_export.to_filename("가" * 300, "vid")
    assert len(name) == markdown_export.MAX_STEM_CHARS + len(".md")


def test_to_filename_falls_back_to_video_id_without_a_title() -> None:
    """제목이 없으면 영상 ID 를 쓴다."""
    assert markdown_export.to_filename(None, "dQw4w9WgXcQ") == (
        "dQw4w9WgXcQ.md"
    )


def test_to_filename_falls_back_when_nothing_survives() -> None:
    """금지 문자만 있던 제목은 남는 게 없으므로 영상 ID 로 돌아간다."""
    assert markdown_export.to_filename("///???", "dQw4w9WgXcQ") == (
        "dQw4w9WgXcQ.md"
    )
