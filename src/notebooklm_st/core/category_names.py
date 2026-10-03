"""카테고리 이름의 규칙.

관리 화면(``services.categories``)과 문서 읽기
(``core.outline_import``)가 같은 규칙을 쓴다. 그래야 앱이 받지 않는
이름이 동기화로 들어오지 않는다.

이름은 Outline 문서 머리의 한 줄에 쉼표로 이어 적힌다. 그래서 쉼표를
쓰지 못하고, Outline 이 서식으로 읽을 수 있는 마크다운 글자도 쓰지
못한다. 막을 글자를 늘어놓는 대신 쓸 수 있는 글자를 정한다 — 모르는
서식 글자가 새로 생겨도 새지 않는다.
"""

from collections.abc import Iterable

from notebooklm_st.core import markdown_export

MAX_LENGTH = 30
"""이름의 최대 글자 수."""

ALLOWED_SYMBOLS = frozenset(" -.&+/()·")
"""글자·숫자 말고 이름에 쓸 수 있는 글자. 공백을 포함한다."""


def validate(name: str) -> str:
    """이름을 다듬고 규칙에 맞는지 확인한다.

    제어문자를 지우고 공백을 접는다(``markdown_export.one_line``).
    글자·숫자는 ``str.isalnum`` 으로 가린다. 밑줄은 여기서 거짓이라
    막힌다.

    Args:
        name: 사람이 입력했거나 문서에서 읽은 이름.

    Returns:
        다듬은 이름.

    Raises:
        ValueError: 비었거나, 길거나, 쓸 수 없는 글자가 있는 경우.
    """
    cleaned = markdown_export.one_line(name)
    if not cleaned:
        raise ValueError("카테고리 이름이 비어 있습니다.")
    if len(cleaned) > MAX_LENGTH:
        raise ValueError(f"카테고리 이름은 {MAX_LENGTH}자까지입니다.")
    if not all(char.isalnum() or char in ALLOWED_SYMBOLS for char in cleaned):
        raise ValueError(
            "카테고리 이름에는 글자·숫자·공백과 - . & + / ( ) · 만"
            " 쓸 수 있습니다."
        )
    return cleaned


def is_valid(name: str) -> bool:
    """이름이 규칙에 맞는지 알려 준다.

    Args:
        name: 검사할 이름.

    Returns:
        ``validate`` 가 받으면 참.
    """
    try:
        validate(name)
    except ValueError:
        return False
    return True


def ordered(names: Iterable[str]) -> tuple[str, ...]:
    """중복을 빼고 파이썬 기본 문자열 순서로 늘어놓는다.

    저장·동기화·표가 모두 이 순서를 쓴다. SQL 로 정하지 않는 것은
    운영 이미지의 SQLite 가 집계 함수 안의 정렬을 모르기 때문이다
    (설계서 §2.9).

    Args:
        names: 늘어놓을 이름들.

    Returns:
        정렬한 이름들.
    """
    return tuple(sorted(set(names)))


def split(value: str) -> tuple[str, ...]:
    """문서 머리 줄의 값을 이름들로 나눈다.

    조각마다 ``validate`` 와 같게 다듬고, 비었거나 규칙에 맞지 않는
    조각은 버린다. 사람이 Outline 에서 줄을 고치며 섞어 넣은 것까지
    받지는 않는다.

    Args:
        value: ``- 카테고리:`` 뒤의 값. 역슬래시 이스케이프는 부르는
            쪽이 이미 걷었다.

    Returns:
        규칙에 맞는 이름들. 중복을 빼고 정렬했다.
    """
    pieces = value.split(markdown_export.CATEGORY_SEPARATOR)
    cleaned = (markdown_export.one_line(piece) for piece in pieces)
    return ordered(name for name in cleaned if is_valid(name))
