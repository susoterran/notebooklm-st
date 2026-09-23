"""정리본 제목 지시와 파싱 테스트."""

from notebooklm_st.core import digest_title

INSTRUCTION = "공통 주장과 엇갈리는 지점을 정리해 줘"


def test_wrap_keeps_the_instruction_first():
    """사람이 고른 지시가 프롬프트 맨 앞에 그대로 남는다."""
    assert digest_title.wrap(INSTRUCTION).startswith(INSTRUCTION)


def test_wrap_appends_the_title_directive():
    """제목을 요구하는 지시가 뒤에 붙는다."""
    assert digest_title.DIRECTIVE in digest_title.wrap(INSTRUCTION)


def test_split_reads_the_first_line_as_the_topic():
    """첫 줄의 제목 표시를 주제로 읽고 본문과 가른다."""
    topic, body = digest_title.split("제목: 밸류에이션 세 강의\n\n본문이다.")

    assert topic == "밸류에이션 세 강의"
    assert body == "본문이다."


def test_split_tolerates_bold_markers():
    """굵게 쓴 제목 줄도 읽는다."""
    topic, body = digest_title.split("**제목:** 주제다\n\n본문이다.")

    assert topic == "주제다"
    assert body == "본문이다."


def test_split_tolerates_a_heading_marker():
    """머리글로 쓴 제목 줄도 읽는다."""
    topic, _ = digest_title.split("## 제목: 주제다\n\n본문이다.")

    assert topic == "주제다"


def test_split_tolerates_a_full_width_colon():
    """전각 콜론도 받는다."""
    # 전각 콜론이 이 테스트의 대상이다.
    topic, _ = digest_title.split("제목： 주제다\n\n본문이다.")  # noqa: RUF001

    assert topic == "주제다"


def test_split_strips_quotes_around_the_topic():
    """주제를 감싼 따옴표를 벗긴다."""
    topic, _ = digest_title.split('제목: "주제다"\n\n본문이다.')

    assert topic == "주제다"


def test_split_skips_leading_blank_lines():
    """앞에 빈 줄이 있어도 제목 줄을 찾는다."""
    topic, body = digest_title.split("\n\n제목: 주제다\n\n본문이다.")

    assert topic == "주제다"
    assert body == "본문이다."


def test_split_returns_the_text_untouched_without_a_title_line():
    """제목 표시가 없으면 본문을 손대지 않는다."""
    text = "핵심은 셋이다.\n\n둘째 문단."

    assert digest_title.split(text) == (None, text)


def test_split_drops_an_empty_title_line():
    """제목 표시만 있고 주제가 비면 그 줄을 버린다."""
    topic, body = digest_title.split("제목:\n\n본문이다.")

    assert topic is None
    assert body == "본문이다."


def test_split_keeps_the_text_when_only_a_title_line_came():
    """본문이 남지 않으면 아무것도 자르지 않는다.

    제목만 받고 본문을 잃는 것보다, 받은 글을 그대로 보여 주고
    제목을 날짜로 떨어뜨리는 쪽이 낫다.
    """
    assert digest_title.split("제목: 주제다") == (None, "제목: 주제다")


def test_compose_prefixes_the_topic():
    """주제가 있으면 접두어를 붙인다."""
    assert (
        digest_title.compose("밸류에이션 비교", "2026-09-23")
        == "[정리] 밸류에이션 비교"
    )


def test_compose_falls_back_to_the_date():
    """주제를 받지 못하면 날짜로 떨어진다.

    접두어는 그대로 붙여 Outline 에서 정리본을 한 번에 찾게 한다.
    """
    assert digest_title.compose(None, "2026-09-23") == "[정리] 2026-09-23"


def test_compose_treats_a_blank_topic_as_missing():
    """공백만 남은 주제는 없는 것으로 본다."""
    assert digest_title.compose("   ", "2026-09-23") == "[정리] 2026-09-23"


def test_compose_folds_a_multiline_topic_into_one_line():
    """개행이 섞인 주제를 한 줄로 접는다."""
    assert (
        digest_title.compose("주제다\n둘째 줄", "2026-09-23")
        == "[정리] 주제다 둘째 줄"
    )


def test_compose_shortens_a_long_topic():
    """긴 주제를 상한까지 자른다."""
    result = digest_title.compose("가" * 200, "2026-09-23")

    assert result.endswith("…")
    assert len(result) == len("[정리] ") + digest_title.TOPIC_MAX_CHARS
