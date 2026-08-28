"""실행 이력 화면."""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import answer_view
from notebooklm_st.core import models
from notebooklm_st.services import run_history

_SELECTED_KEY = "history_selected"


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
    answer_view.render_items(
        run_history.load_run_items(connection, selected.id)
    )


def _format_run(run: models.RunSummary) -> str:
    """실행 하나를 목록에 보여 줄 한 줄로 만든다."""
    return f"{run.created_at} · {run.video_id} · 답변 {run.answer_count}건"
