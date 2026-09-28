"""Outline 문서 본문에서 이력 복원에 필요한 값을 읽는 순수 함수들.

``markdown_export`` 가 문서 첫머리에 쓴 메타데이터 리스트를 거꾸로
읽는 짝이다. Streamlit 도 httpx 도 모른다.
"""

import re

from notebooklm_st.core import markdown_export

_RULE = re.compile(r"^\s*---\s*$")
"""머리 블록을 끝내는 구분선."""

_SOURCE_LINE = re.compile(
    r"^\s*-\s*" + re.escape(markdown_export.SOURCE_URL_LABEL) + r":\s*(\S+)\s*$"
)
"""``- 영상 URL: <값>`` 줄. 값은 공백이 없는 한 덩어리다."""


def find_source_url(markdown: str) -> str | None:
    """문서 머리 블록에서 영상 URL 을 찾는다.

    첫 구분선(``---``) 앞까지만 본다. 답변 본문에 같은 문구가 인용될
    수 있어서다. 구분선이 없으면 전체가 머리 블록이다.

    Args:
        markdown: Outline 이 돌려준 문서 본문.

    Returns:
        첫 영상 URL 줄의 값. 줄이 없으면 ``None``.
    """
    for line in markdown.splitlines():
        if _RULE.match(line):
            return None
        match = _SOURCE_LINE.match(line)
        if match:
            return match.group(1)
    return None
