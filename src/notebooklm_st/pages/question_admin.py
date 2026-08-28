"""질문 관리 화면."""

import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import models
from notebooklm_st.services import store

_NEW_KEY = "admin_new"


def render() -> None:
    """질문 등록 입력과 편집 가능한 목록을 그린다.

    등록 후에도 입력란의 글이 남는다. 위젯이 만들어진 뒤에
    ``st.session_state`` 의 위젯 키를 건드리면 Streamlit 이 예외를
    던지므로, 비우려 애쓰는 대신 그대로 둔다.
    """
    st.title("질문 관리")
    connection = session.get_connection()

    text = st.text_area("새 질문", key=_NEW_KEY)
    if st.button("등록", key="admin_add"):
        _add(connection, text)

    for question in store.list_questions(connection):
        _render_row(connection, question)


def _add(connection: sqlite3.Connection, text: str) -> None:
    """새 질문을 저장하고 화면을 다시 그린다."""
    try:
        store.add_question(connection, text)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()


def _render_row(
    connection: sqlite3.Connection, question: models.Question
) -> None:
    """질문 하나를 수정·삭제 버튼과 함께 그린다."""
    with st.expander(question.text):
        edited = st.text_area(
            "내용",
            value=question.text,
            key=f"admin_text_{question.id}",
        )
        left, right = st.columns(2)
        if left.button("수정", key=f"admin_update_{question.id}"):
            _update(connection, question.id, edited)
        if right.button("삭제", key=f"admin_delete_{question.id}"):
            store.delete_question(connection, question.id)
            st.rerun()


def _update(
    connection: sqlite3.Connection, question_id: int, text: str
) -> None:
    """질문 본문을 고치고 화면을 다시 그린다."""
    try:
        store.update_question(connection, question_id, text)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()
