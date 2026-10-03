"""Outline 문서 본문에서 이력 복원에 필요한 값을 읽는 순수 함수들.

``markdown_export`` 가 문서 첫머리에 쓴 메타데이터 리스트를 거꾸로
읽는 짝이다. Streamlit 도 httpx 도 모른다.

Outline 은 문서를 ProseMirror 편집기에 담아 두었다가 읽을 때 다시
마크다운으로 직렬화한다. 그래서 우리가 쓴 줄이 글자 그대로 돌아온다고
보지 않는다 — 글머리표·링크 모양·역슬래시 이스케이프가 바뀐 줄도
받는다.
"""

import datetime
import re
from collections.abc import Iterator

from notebooklm_st.core import category_names, markdown_export, models

_RULE = re.compile(r"^\s*---\s*$")
"""머리 블록을 끝내는 구분선."""

_SOURCE_LINE = re.compile(
    r"^\s*[-*+]\s*"
    + re.escape(markdown_export.SOURCE_URL_LABEL)
    + r":\s*(?:"
    + r"<(?P<angle>[^>\s]+)>"
    + r"|\[[^\]]*\]\((?P<link>[^)\s]+)\)"
    + r"|(?P<bare>\S+)"
    + r")\s*$"
)
"""영상 URL 줄.

글머리표는 ``-``·``*``·``+`` 중 하나다. 값은 ``<URL>``(자동 링크),
``[글](URL)``(링크), 맨 URL 셋 중 하나이며, 주소는 공백이 없는 한
덩어리다. 링크면 글이 아니라 주소 쪽을 쓴다.
"""

_ESCAPE = re.compile(r"\\([_\-*#])")
"""직렬화기가 값 안에 넣을 수 있는 역슬래시 이스케이프."""

_PUNCTUATION_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")
"""CommonMark 가 이스케이프로 인정하는 ASCII 문장부호 앞의 역슬래시.

채널명에는 URL 에 나올 수 없는 문장부호(``[``·``!`` 등)도 나온다.
그래서 영상 URL 줄의 ``_ESCAPE`` 보다 넓다.
"""

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
"""업로드 일자의 모양.

``datetime.date.fromisoformat`` 은 ``20260920`` 도 받으므로 모양을
먼저 본다.
"""


def _labeled_line(label: str) -> re.Pattern[str]:
    """라벨 하나의 메타데이터 줄 패턴을 만든다.

    글머리표는 ``-``·``*``·``+`` 중 하나다. 값은 비어 있어도 맞는다 —
    빈 값을 건너뛰고 뒤의 줄을 찾지 않기 위해서다(``_first_value``).
    """
    return re.compile(
        r"^\s*[-*+]\s*" + re.escape(label) + r":\s*(?P<value>.*?)\s*$"
    )


_CHANNEL_LINE = _labeled_line(markdown_export.CHANNEL_LABEL)
_UPLOAD_DATE_LINE = _labeled_line(markdown_export.UPLOAD_DATE_LABEL)
_CATEGORY_LINE = _labeled_line(markdown_export.CATEGORY_LABEL)


def find_source_url(markdown: str) -> str | None:
    """문서 머리 블록에서 영상 URL 을 찾는다.

    첫 구분선(``---``) 앞까지만 본다. 답변 본문에 같은 문구가 인용될
    수 있어서다. 구분선이 없으면 전체가 머리 블록이다.

    Outline 의 재직렬화 변형을 받는다. 글머리표가 ``*``·``+`` 여도,
    값이 ``<URL>`` 이나 ``[글](URL)`` 로 감싸여 있어도 주소만 꺼낸다.
    꺼낸 값의 밑줄·하이픈·별표·샵 앞 역슬래시는 걷어 낸다.

    Args:
        markdown: Outline 이 돌려준 문서 본문.

    Returns:
        첫 영상 URL 줄의 값. 줄이 없거나 값이 비었으면 ``None``.
    """
    for line in _head_lines(markdown):
        match = _SOURCE_LINE.match(line)
        if match:
            value = match["angle"] or match["link"] or match["bare"]
            return _ESCAPE.sub(r"\1", value)
    return None


def find_metadata(markdown: str) -> models.VideoMetadata | None:
    """문서 머리 블록에서 채널과 업로드 일자를 찾는다.

    머리 블록의 범위와 글머리표 변형은 ``find_source_url`` 과 같다.
    라벨마다 라벨이 맞는 첫 줄만 본다. 그 값이 비었거나 날짜로 읽히지
    않아도 뒤의 같은 라벨 줄로 넘어가지 않고 그 칸을 비운다 — 우리는
    라벨마다 한 줄만 쓰므로 둘째 줄은 사람이 고친 흔적이고, 어느 줄이
    맞는지 고를 근거가 없다.

    Args:
        markdown: Outline 이 돌려준 문서 본문.

    Returns:
        읽은 값. 못 읽은 칸은 ``None`` 이다. 두 칸 모두 못 읽으면
        ``None`` — 두 값이 빈 메타데이터 행을 만들지 않게 한다.
    """
    channel = _first_value(markdown, _CHANNEL_LINE) or None
    upload_date = _as_date(_first_value(markdown, _UPLOAD_DATE_LINE))
    if channel is None and upload_date is None:
        return None
    return models.VideoMetadata(channel=channel, upload_date=upload_date)


def find_categories(markdown: str) -> tuple[str, ...] | None:
    """문서 머리 블록에서 카테고리 이름들을 찾는다.

    머리 블록의 범위, 글머리표 변형, 역슬래시 걷기, 라벨마다 첫 줄만
    보는 것은 채널 줄과 같다(``find_metadata``). 값은
    ``category_names.split`` 으로 나눈다 — 규칙에 맞지 않는 이름은
    버린다.

    Args:
        markdown: Outline 이 돌려준 문서 본문.

    Returns:
        읽은 이름들. 이름 순이다. 줄이 없거나 읽을 이름이 하나도
        없으면 ``None`` — 읽지 못한 것이다. 동기화는 그 행을 손대지
        않는다.
    """
    value = _first_value(markdown, _CATEGORY_LINE)
    if value is None:
        return None
    return category_names.split(value) or None


def _head_lines(markdown: str) -> Iterator[str]:
    """머리 블록의 줄을 차례로 내준다.

    첫 구분선에서 멈춘다. 구분선이 없으면 전체를 내준다.
    """
    for line in markdown.splitlines():
        if _RULE.match(line):
            return
        yield line


def _first_value(markdown: str, pattern: re.Pattern[str]) -> str | None:
    """패턴에 맞는 첫 줄의 값을 이스케이프를 걷어 돌려준다.

    Returns:
        그 값. 비어 있을 수 있다. 맞는 줄이 없으면 ``None``.
    """
    for line in _head_lines(markdown):
        match = pattern.match(line)
        if match:
            return _PUNCTUATION_ESCAPE.sub(r"\1", match["value"])
    return None


def _as_date(value: str | None) -> str | None:
    """``YYYY-MM-DD`` 로 읽히는 날짜만 받는다."""
    if value is None or not _DATE.fullmatch(value):
        return None
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return None
    return value
