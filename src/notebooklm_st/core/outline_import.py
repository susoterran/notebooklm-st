"""Outline 문서 본문에서 이력 복원에 필요한 값을 읽는 순수 함수들.

``markdown_export`` 가 문서 첫머리에 쓴 메타데이터 리스트를 거꾸로
읽는 짝이다. Streamlit 도 httpx 도 모른다.

Outline 은 문서를 ProseMirror 편집기에 담아 두었다가 읽을 때 다시
마크다운으로 직렬화한다. 그래서 우리가 쓴 줄이 글자 그대로 돌아온다고
보지 않는다 — 글머리표·링크 모양·역슬래시 이스케이프가 바뀐 줄도
받는다.
"""

import re

from notebooklm_st.core import markdown_export

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
    for line in markdown.splitlines():
        if _RULE.match(line):
            return None
        match = _SOURCE_LINE.match(line)
        if match:
            value = match["angle"] or match["link"] or match["bare"]
            return _ESCAPE.sub(r"\1", value)
    return None
