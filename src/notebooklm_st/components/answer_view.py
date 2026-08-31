"""답변 카드 렌더."""

from collections.abc import Callable, Sequence

import streamlit as st

from notebooklm_st.core import models

# st.text_area 의 height 는 픽셀이다. 라벨 있는 기본값 122px 가 3줄이고
# 줄당 24px 이므로 20줄은 122 + 17 * 24 = 530px 이다. 답변은 길어서
# 질문 관리 화면보다 넉넉해야 고칠 자리를 찾을 수 있다.
_EDIT_HEIGHT = 530

SaveCallback = Callable[[int, str], None]


def render_items(
    items: Sequence[models.AnswerItem],
    *,
    on_save: SaveCallback | None = None,
) -> None:
    """답변 목록을 위에서 아래로 카드처럼 그린다.

    항목 사이에만 구분자를 넣는다. 마지막 뒤에도 넣으면 실행 현황
    화면에서 실행 간 구분자와 겹쳐 줄이 두 개가 된다.

    Args:
        items: 그릴 답변 목록. 비어 있으면 아무것도 그리지 않는다.
        on_save: 고친 본문을 받을 콜백. 답변 ID 와 새 본문을 받는다.
            주지 않으면 카드는 읽기 전용이다.
    """
    for index, item in enumerate(items):
        if index > 0:
            st.divider()
        _render_item(item, on_save)


def _render_item(item: models.AnswerItem, on_save: SaveCallback | None) -> None:
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
    _render_answer(item, on_save)
    if not item.citations:
        return
    with st.expander(f"인용 {len(item.citations)}건"):
        for citation in item.citations:
            st.markdown(f"**[{citation.number}]** {citation.text}")


def _render_answer(
    item: models.AnswerItem, on_save: SaveCallback | None
) -> None:
    """편집이 열려 있으면 입력 상자로, 아니면 본문 그대로 그린다.

    두 조건을 모두 만족해야 편집을 연다. 호출자가 저장 콜백을 줬고,
    항목이 DB 에서 온 것이어서 지목할 ID 가 있어야 한다. 파이프라인이
    갓 만든 항목은 ID 가 없으므로 실행 현황 화면에는 편집 상자가
    나타나지 않는다.
    """
    if on_save is None or item.id is None:
        st.markdown(item.answer or "")
        return
    edited = st.text_area(
        "답변",
        value=item.answer or "",
        key=f"answer_edit_{item.id}",
        height=_EDIT_HEIGHT,
    )
    if st.button("저장", key=f"answer_save_{item.id}"):
        on_save(item.id, edited)
