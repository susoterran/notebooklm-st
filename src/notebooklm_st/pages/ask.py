"""질의 화면."""

import asyncio
import sqlite3
from collections.abc import Sequence

import streamlit as st
from notebooklm import exceptions

from notebooklm_st import session
from notebooklm_st.components import answer_view, run_progress
from notebooklm_st.core import errors, models, youtube
from notebooklm_st.services import nlm, store

_URL_KEY = "ask_url"
_SELECTED_KEY = "ask_selected"
_RESULT_KEY = "ask_result"


def render() -> None:
    """URL 입력, 질문 선택, 실행, 답변 표시를 그린다."""
    st.title("영상 질의")
    connection = session.get_connection()
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

    if st.button(
        "실행",
        key="ask_run",
        disabled=not (url_ok and selected),
    ):
        _execute(connection, url, selected)

    result = st.session_state.get(_RESULT_KEY)
    if result is not None:
        st.caption(result.url)
        answer_view.render_items(result.items)


def _execute(
    connection: sqlite3.Connection,
    url: str,
    questions: Sequence[models.Question],
) -> None:
    """파이프라인을 돌리고 결과를 이력과 세션에 남긴다.

    실행 중에는 이 탭이 묶인다. 이벤트 루프가 스크립트와 같은
    스레드에서 돌기 때문에 진행 문구는 그대로 화면에 전달된다.
    """
    try:
        with run_progress.progress_status("실행 준비 중") as report:
            result = asyncio.run(nlm.run_pipeline(url, questions, report))
    except exceptions.NotebookLMError as error:
        st.session_state.pop(_RESULT_KEY, None)
        message = errors.to_message(error)
        if message.level == "info":
            st.info(message.text)
        else:
            st.error(message.text)
        return

    store.save_run(connection, result)
    st.session_state[_RESULT_KEY] = result
