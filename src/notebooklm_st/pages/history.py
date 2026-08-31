"""실행 이력 화면."""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import answer_view
from notebooklm_st.core import models
from notebooklm_st.services import run_history

_SELECTED_KEY = "history_selected"

# 목록은 한 줄로 읽혀야 값을 한다. 질문 관리 화면과 같은 상한을
# 쓴다.
_TITLE_MAX_CHARS = 60


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
