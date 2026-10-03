"""카테고리 선택 — 질의 화면과 채널 화면이 함께 쓴다.

값은 카테고리 ID 이고, 이름은 ``format_func`` 로 보인다. 객체를 값으로
쓰면 이름이 바뀐 카테고리가 선택지와 같지 않게 된다.
"""

from collections.abc import Callable, Sequence

import streamlit as st

from notebooklm_st.core import models

NO_CATEGORIES = (
    "카테고리 관리 화면에서 카테고리를 먼저 등록하세요."
    " 카테고리를 고르지 않으면 질의할 수 없습니다."
)
"""카테고리가 하나도 없을 때 질의를 넣는 화면이 보이는 안내."""

QUERY_HELP = (
    "Outline 문서 머리에 적히고 정리본 재료를 거르는 데 씁니다."
    " 하나 이상 고르세요."
)
"""질의를 넣는 화면의 카테고리 선택 도움말."""


def render(
    label: str,
    category_list: Sequence[models.Category],
    key: str,
    help_text: str,
    on_change: Callable[[], None] | None = None,
) -> list[int]:
    """카테고리 선택을 그리고 고른 ID 를 돌려준다.

    Args:
        label: 위젯 라벨.
        category_list: 선택지. 비어 있지 않다.
        key: 위젯 key. 화면마다 다르다.
        help_text: 위젯 도움말.
        on_change: 값이 바뀌면 부를 콜백. DB 에 기억하는 화면만 준다.

    Returns:
        고른 카테고리 ID.
    """
    names = {category.id: category.name for category in category_list}
    chosen: list[int] = st.multiselect(
        label,
        options=list(names),
        format_func=lambda category_id: names[category_id],
        key=key,
        help=help_text,
        on_change=on_change,
    )
    return chosen
