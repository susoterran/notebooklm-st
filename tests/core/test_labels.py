"""목록 라벨 자르기 순수 함수 테스트."""

from notebooklm_st.core import labels


def test_short_title_is_kept_as_is() -> None:
    """상한 이하의 제목은 그대로 돌려준다."""
    title = "짧은 제목"
    assert labels.shorten(title) == title


def test_title_at_the_limit_is_not_cut() -> None:
    """길이가 정확히 상한이면 자르지 않는다."""
    title = "가" * labels.LIST_LABEL_MAX_CHARS
    assert labels.shorten(title) == title


def test_long_title_is_cut_with_ellipsis() -> None:
    """상한을 넘는 제목은 잘리고 말줄임표가 붙는다."""
    title = "가" * (labels.LIST_LABEL_MAX_CHARS + 10)

    result = labels.shorten(title)

    assert result.endswith("…")
    assert len(result) == labels.LIST_LABEL_MAX_CHARS


def test_limit_argument_overrides_the_default() -> None:
    """상한을 직접 넘기면 그 값을 따른다."""
    result = labels.shorten("가나다라마바사", limit=5)

    assert result == "가나다라…"
    assert len(result) == 5
