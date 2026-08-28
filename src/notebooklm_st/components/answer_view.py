"""답변 카드 렌더."""

from collections.abc import Sequence

import streamlit as st

from notebooklm_st.core import models


def render_items(items: Sequence[models.AnswerItem]) -> None:
    """답변 목록을 위에서 아래로 카드처럼 그린다.

    항목 사이에만 구분자를 넣는다. 마지막 뒤에도 넣으면 실행 현황
    화면에서 실행 간 구분자와 겹쳐 줄이 두 개가 된다.

    Args:
        items: 그릴 답변 목록. 비어 있으면 아무것도 그리지 않는다.
    """
    for index, item in enumerate(items):
        if index > 0:
            st.divider()
        _render_item(item)


def _render_item(item: models.AnswerItem) -> None:
    """답변 하나를 제목, 접은 질문, 본문, 인용 순으로 그린다.

    질문 원문은 접어 둔다. 바로 확인할 필요가 없고, 마크다운 문법이
    섞여 있으면 머리글 자리에서 서식으로 렌더되어 읽기 어렵기
    때문이다. ``st.expander`` 의 라벨도 마크다운을 렌더하므로 라벨은
    고정 문구로 두고, 원문은 마크다운을 파싱하지 않는 ``st.text`` 로
    출력한다. 답변 본문은 서식이 살아야 읽히므로 그대로 렌더한다.
    """
    st.subheader(item.question_title)
    with st.expander("질문 원문"):
        st.text(item.question_text)
    if item.error is not None:
        st.error(item.error)
        return
    st.markdown(item.answer or "")
    if not item.citations:
        return
    with st.expander(f"인용 {len(item.citations)}건"):
        for citation in item.citations:
            st.markdown(f"**[{citation.number}]** {citation.text}")
