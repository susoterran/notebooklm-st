"""질문 관리 화면."""

import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import models
from notebooklm_st.services import questions

_NEW_TITLE_KEY = "admin_new_title"
_NEW_TEXT_KEY = "admin_new_text"
# 제목은 목록에서 한 줄로 읽혀야 값을 한다. 길이를 막지 않으면 본문을
# 그대로 붙여 넣어 목록이 다시 읽기 어려워진다.
_TITLE_MAX_CHARS = 60
# st.text_area 의 height 는 픽셀이다. 라벨 있는 기본값 122px 가 3줄이고
# 줄당 24px 이므로 12줄은 122 + 9 * 24 = 338px 이다.
_TEXT_AREA_HEIGHT = 338


def render() -> None:
    """질문 등록 입력과 편집 가능한 목록을 그린다.

    등록 후에도 입력란의 글이 남는다. 위젯이 만들어진 뒤에
    ``st.session_state`` 의 위젯 키를 건드리면 Streamlit 이 예외를
    던지므로, 비우려 애쓰는 대신 그대로 둔다.
    """
    st.title("질문 관리")
    connection = session.get_connection()

    title = st.text_input(
        "새 질문 제목", key=_NEW_TITLE_KEY, max_chars=_TITLE_MAX_CHARS
    )
    text = st.text_area(
        "새 질문 내용", key=_NEW_TEXT_KEY, height=_TEXT_AREA_HEIGHT
    )
    if st.button("등록", key="admin_add"):
        _add(connection, title, text)

    for question in questions.list_questions(connection):
        _render_row(connection, question)


def _add(connection: sqlite3.Connection, title: str, text: str) -> None:
    """새 질문을 저장하고 화면을 다시 그린다."""
    try:
        questions.add_question(connection, title, text)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()


def _render_row(
    connection: sqlite3.Connection, question: models.Question
) -> None:
    """질문 하나를 수정·삭제 버튼과 함께 그린다.

    접힌 상태에서는 제목만 보인다. 본문 전체를 라벨에 넣으면 목록이
    길어져 관리하기 어렵다.
    """
    with st.expander(question.title):
        edited_title = st.text_input(
            "제목",
            value=question.title,
            key=f"admin_title_{question.id}",
            max_chars=_TITLE_MAX_CHARS,
        )
        edited_text = st.text_area(
            "내용",
            value=question.text,
            key=f"admin_text_{question.id}",
            height=_TEXT_AREA_HEIGHT,
        )
        left, right = st.columns(2)
        if left.button("수정", key=f"admin_update_{question.id}"):
            _update(connection, question.id, edited_title, edited_text)
        if right.button("삭제", key=f"admin_delete_{question.id}"):
            questions.delete_question(connection, question.id)
            st.rerun()


def _update(
    connection: sqlite3.Connection,
    question_id: int,
    title: str,
    text: str,
) -> None:
    """질문의 제목과 본문을 고치고 화면을 다시 그린다."""
    try:
        questions.update_question(connection, question_id, title, text)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()
