"""답변 카드 렌더."""

from collections.abc import Sequence

import streamlit as st

from notebooklm_st.core import models


def render_items(items: Sequence[models.AnswerItem]) -> None:
    """답변 목록을 위에서 아래로 카드처럼 그린다.

    Args:
        items: 그릴 답변 목록. 비어 있으면 아무것도 그리지 않는다.
    """
    for item in items:
        _render_item(item)


def _render_item(item: models.AnswerItem) -> None:
    """답변 하나를 질문 제목, 본문, 인용 순으로 그린다."""
    st.subheader(item.question_text)
    if item.error is not None:
        st.error(item.error)
        return
    st.markdown(item.answer or "")
    if not item.citations:
        return
    with st.expander(f"인용 {len(item.citations)}건"):
        for citation in item.citations:
            st.markdown(f"**[{citation.number}]** {citation.text}")
