"""카테고리 이름 규칙 테스트."""

import pytest

from notebooklm_st.core import category_names


def test_validate_trims_and_folds_whitespace() -> None:
    """앞뒤 공백을 자르고 겹친 공백을 하나로 접는다."""
    assert category_names.validate("  인공 \t 지능 ") == "인공 지능"


def test_validate_drops_control_characters() -> None:
    """제어문자를 지운다."""
    assert category_names.validate("경\x00제") == "경제"


@pytest.mark.parametrize("name", ["", "   ", "\x00"])
def test_validate_rejects_an_empty_name(name: str) -> None:
    """다듬은 뒤 비었으면 거부한다."""
    with pytest.raises(ValueError, match="비어 있습니다"):
        category_names.validate(name)


def test_validate_accepts_thirty_characters() -> None:
    """30자까지 받는다."""
    name = "가" * 30

    assert category_names.validate(name) == name


def test_validate_rejects_thirty_one_characters() -> None:
    """31자는 거부한다."""
    with pytest.raises(ValueError, match="30자"):
        category_names.validate("가" * 31)


@pytest.mark.parametrize(
    "char", [",", "*", "_", "`", "[", "]", "~", "=", "<", "#", "|", "\\"]
)
def test_validate_rejects_separator_and_markdown_characters(
    char: str,
) -> None:
    """쉼표와 마크다운 서식에 쓰이는 글자는 거부한다."""
    with pytest.raises(ValueError, match="쓸 수 있습니다"):
        category_names.validate(f"경제{char}정책")


@pytest.mark.parametrize(
    "name",
    [
        "경제",
        "AI",
        "Web3",
        "R&D",
        "C++",
        "A/B 테스트",
        "경제(거시)",
        "v1.2",
        "AI·데이터",
        "인공-지능",
    ],
)
def test_validate_accepts_letters_digits_and_allowed_symbols(
    name: str,
) -> None:
    """글자·숫자·공백과 허용한 기호는 그대로 받는다."""
    assert category_names.validate(name) == name


def test_is_valid_follows_validate() -> None:
    """``validate`` 가 받으면 참, 거부하면 거짓이다."""
    assert category_names.is_valid("경제")
    assert not category_names.is_valid("경제,정책")


def test_ordered_removes_duplicates_and_sorts() -> None:
    """중복을 빼고 파이썬 기본 문자열 순서로 늘어놓는다."""
    names = ["인공지능", "경제", "AI", "경제"]

    assert category_names.ordered(names) == ("AI", "경제", "인공지능")


def test_split_reads_comma_separated_names() -> None:
    """쉼표로 이은 값을 이름들로 나눈다."""
    assert category_names.split("인공지능, 경제") == ("경제", "인공지능")


def test_split_drops_empty_and_blank_pieces() -> None:
    """빈 조각과 공백뿐인 조각은 버린다."""
    assert category_names.split(" , 경제,, ") == ("경제",)


def test_split_drops_only_the_invalid_pieces() -> None:
    """규칙에 맞지 않는 조각만 버리고 나머지는 살린다."""
    value = "경제, *강조*, 인공지능"

    assert category_names.split(value) == ("경제", "인공지능")


def test_split_removes_duplicates() -> None:
    """같은 이름이 두 번 나오면 한 번만 남긴다."""
    assert category_names.split("경제, 경제") == ("경제",)


def test_split_of_an_empty_value_is_empty() -> None:
    """빈 값은 빈 결과다."""
    assert category_names.split("") == ()
