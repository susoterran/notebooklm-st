"""Outline 문서 본문에서 영상 URL 을 되읽는 함수 테스트."""

from notebooklm_st.core import outline_import

SUMMARY = (
    "- 제목: 밸류에이션 강의\n"
    "- 채널: 어떤 채널\n"
    "- 업로드 일자: 2026-09-20\n"
    "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
    "\n"
    "---\n"
    "\n"
    "## 핵심 주장\n"
    "\n"
    "세 가지다.\n"
)

DIGEST = (
    "- 종류: 정리본\n"
    "- 만든 날: 2026-09-23\n"
    "- 정리 지시: 공통점을 뽑아라\n"
    "\n"
    "---\n"
    "\n"
    "## 정리\n"
)


def test_finds_the_source_url_in_the_head_block() -> None:
    """메타데이터 리스트의 영상 URL 줄을 찾는다."""
    assert (
        outline_import.find_source_url(SUMMARY)
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )


def test_returns_none_without_a_source_line() -> None:
    """영상 URL 줄이 없으면 이력 문서가 아니다."""
    assert outline_import.find_source_url("## 그냥 글\n\n본문.\n") is None


def test_ignores_a_source_line_after_the_rule() -> None:
    """첫 구분선 뒤의 같은 문구는 본문이지 메타데이터가 아니다."""
    text = "- 제목: 글\n\n---\n\n- 영상 URL: https://youtu.be/dQw4w9WgXcQ\n"

    assert outline_import.find_source_url(text) is None


def test_searches_the_whole_text_without_a_rule() -> None:
    """구분선이 없으면 전체가 머리 블록이다."""
    text = "- 제목: 글\n- 영상 URL: https://youtu.be/dQw4w9WgXcQ\n"

    assert (
        outline_import.find_source_url(text) == "https://youtu.be/dQw4w9WgXcQ"
    )


def test_a_digest_body_is_not_a_summary() -> None:
    """정리본 본문은 만든 날·정리 지시만 있고 영상 URL 이 없다."""
    assert outline_import.find_source_url(DIGEST) is None


def test_tolerates_surrounding_whitespace() -> None:
    """앞뒤 공백과 라벨 뒤 공백을 허용한다."""
    text = "  -   영상 URL:   https://youtu.be/dQw4w9WgXcQ   \n"

    assert (
        outline_import.find_source_url(text) == "https://youtu.be/dQw4w9WgXcQ"
    )


def test_takes_the_first_source_line() -> None:
    """같은 줄이 둘이면 첫 줄을 쓴다."""
    text = (
        "- 영상 URL: https://youtu.be/aaaaaaaaaaa\n"
        "- 영상 URL: https://youtu.be/bbbbbbbbbbb\n"
    )

    assert (
        outline_import.find_source_url(text) == "https://youtu.be/aaaaaaaaaaa"
    )


def test_returns_none_for_an_empty_value() -> None:
    """라벨만 있고 값이 없으면 없는 것이다."""
    assert outline_import.find_source_url("- 영상 URL:\n") is None
