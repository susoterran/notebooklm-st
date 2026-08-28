"""질의 화면 — 백그라운드 실행을 시작하는 트리거."""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import youtube
from notebooklm_st.services import runner, store

_URL_KEY = "ask_url"
_SELECTED_KEY = "ask_selected"


def render() -> None:
    """URL 입력, 질문 선택, 실행 시작을 그린다.

    실행은 백그라운드 스레드가 맡는다. 이 화면은 시작만 하고 즉시
    반환하므로 페이지를 이동해도 작업이 중단되지 않는다. 진행 상황과
    답변은 실행 현황 화면에서 본다.
    """
    st.title("영상 질의")
    connection = session.get_connection()
    registry = session.get_registry()
    questions = store.list_questions(connection)

    url = st.text_input(
        "YouTube 영상 URL",
        key=_URL_KEY,
        placeholder="https://www.youtube.com/watch?v=...",
    )
    url_ok = youtube.is_valid(url)
    if url and not url_ok:
        st.error("단일 YouTube 영상 URL 이 아닙니다.")

    if not questions:
        st.info("질문 관리 화면에서 질문을 먼저 등록하세요.")
        return

    selected = st.multiselect(
        "질문 선택",
        options=questions,
        format_func=lambda question: question.text,
        key=_SELECTED_KEY,
    )

    busy = registry.running_count() > 0
    if busy:
        st.info(
            "이미 실행 중인 작업이 있습니다. 실행 현황 화면에서 확인하세요."
        )

    if st.button(
        "실행",
        key="ask_run",
        disabled=busy or not (url_ok and selected),
    ):
        runner.start_run(registry, url, selected, store.default_db_path())
        st.success("실행을 시작했습니다. 실행 현황 화면에서 확인하세요.")
