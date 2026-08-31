"""실행 이력 화면."""

import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import answer_view
from notebooklm_st.core import answer_text, models
from notebooklm_st.services import run_history

_SELECTED_KEY = "history_selected"

# 목록은 한 줄로 읽혀야 값을 한다. 질문 관리 화면과 같은 상한을
# 쓴다.
_TITLE_MAX_CHARS = 60

_HIDE_CITATIONS_KEY = "history_hide_citations"

# 위젯 키가 아니라 우리가 소유한 세션 키다. 위젯이 만들어진 뒤 그
# 위젯의 키를 건드리면 Streamlit 이 예외를 던지므로, 삭제 후 상태를
# 되돌리려면 우리 것이어야 한다.
_DELETE_ARMED_KEY = "history_delete_armed"


def render() -> None:
    """최근 실행을 고르고 그 답변들을 보여 준다."""
    st.title("이력")
    connection = session.get_connection()
    runs = run_history.list_runs(connection)
    if not runs:
        st.info("아직 저장된 실행이 없습니다.")
        return

    selected = st.selectbox(
        "실행 선택",
        options=runs,
        format_func=_format_run,
        key=_SELECTED_KEY,
    )
    if selected is None:
        return
    st.caption(selected.url)
    _render_delete(connection, selected)
    hidden = st.checkbox(
        "인용 숨기기",
        key=_HIDE_CITATIONS_KEY,
        help="인용 번호와 인용 본문, 맨 아래 후속 제안을 감춥니다."
        " 숨기는 동안에는 답변을 수정할 수 없습니다.",
    )
    items = run_history.load_run_items(connection, selected.id)
    if hidden:
        answer_view.render_items(
            [answer_text.for_display(item) for item in items]
        )
        return
    answer_view.render_items(items)


def _format_run(run: models.RunSummary) -> str:
    """실행 하나를 목록에 보여 줄 한 줄로 만든다.

    제목을 앞에 둔다. 목록에서 고르는 사람이 먼저 알고 싶은 것은
    시각이 아니라 어떤 영상이었는지다. 목록은 최신순으로 고정되어
    있으므로 시각은 뒤에 있어도 읽는 데 지장이 없다.
    """
    label = _shorten(run.title) if run.title else run.video_id
    return f"{label} · {run.created_at} · 답변 {run.answer_count}건"


def _shorten(title: str) -> str:
    """목록 한 줄에 들어가도록 제목을 자른다.

    자르기는 라벨을 만드는 이 자리에서만 한다. 저장된 제목은 그대로
    둔다.
    """
    if len(title) <= _TITLE_MAX_CHARS:
        return title
    return f"{title[: _TITLE_MAX_CHARS - 1]}…"


def _render_delete(
    connection: sqlite3.Connection, selected: models.RunSummary
) -> None:
    """접은 영역 안에 2단계 삭제를 그린다.

    첫 누름은 지우려는 실행 ID 를 세션에 적어 둘 뿐이다. 다시 그려진
    화면에서 확인을 눌러야 실제로 지운다. 선택한 실행이 바뀌면 적어
    둔 ID 와 어긋나므로 확인이 저절로 풀린다.
    """
    with st.expander("이 이력 삭제"):
        if st.session_state.get(_DELETE_ARMED_KEY) != selected.id:
            if st.button("이 이력 삭제", key="history_delete"):
                st.session_state[_DELETE_ARMED_KEY] = selected.id
                st.rerun()
            return
        st.warning("딸린 답변도 함께 사라집니다. 되돌릴 수 없습니다.")
        left, right = st.columns(2)
        if left.button("정말 삭제", key="history_delete_confirm"):
            _delete(connection, selected.id)
        if right.button("취소", key="history_delete_cancel"):
            _disarm()
            st.rerun()


def _delete(connection: sqlite3.Connection, run_id: int) -> None:
    """실행을 지우고 확인 상태를 풀고 화면을 다시 그린다.

    선택 위젯의 키는 건드리지 않는다. 고른 항목이 목록에서 사라져도
    Streamlit 은 예외 없이 남은 첫 항목으로 되돌린다.
    """
    run_history.delete_run(connection, run_id)
    _disarm()
    st.rerun()


def _disarm() -> None:
    """적어 둔 삭제 대상을 지운다."""
    st.session_state.pop(_DELETE_ARMED_KEY, None)
