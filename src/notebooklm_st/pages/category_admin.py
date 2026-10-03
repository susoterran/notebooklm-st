"""카테고리 관리 화면.

질문 관리와 같은 모양이다. 이름을 바꾸거나 지울 수 없는 카테고리는
이름 칸과 버튼을 잠그고 이유를 적는다. 이력에서 쓰는 카테고리는
Outline 문서 머리에 적힌 이름과 어긋나게 되고, 대기 중인 질의가 쥔
카테고리는 곧 이력에 붙는다.
"""

import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import category_names, models
from notebooklm_st.services import categories, run_registry, runs

_NEW_NAME_KEY = "category_new_name"


def render() -> None:
    """새 카테고리 입력과 편집할 수 있는 목록을 그린다.

    등록 뒤에도 입력란의 글이 남는다. 질문 관리와 같은 이유로, 위젯이
    만들어진 뒤에 그 키를 건드리지 않는다.
    """
    st.title("카테고리 관리")
    st.caption(
        "카테고리는 질의할 때 하나 이상 골라야 합니다. Outline 문서"
        " 머리에 적히고, 정리본 재료를 거르는 데 쓰입니다."
    )
    connection = session.get_connection()
    name = st.text_input(
        "새 카테고리 이름",
        key=_NEW_NAME_KEY,
        max_chars=category_names.MAX_LENGTH,
    )
    if st.button("등록", key="category_add"):
        _add(connection, name)
    registry = session.get_registry()
    for category in categories.list_categories(connection):
        _render_row(connection, registry, category)


def _add(connection: sqlite3.Connection, name: str) -> None:
    """새 카테고리를 저장하고 화면을 다시 그린다."""
    try:
        categories.add_category(connection, name)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()


def _render_row(
    connection: sqlite3.Connection,
    registry: run_registry.RunRegistry,
    category: models.Category,
) -> None:
    """카테고리 하나를 쓰는 곳과 함께 그린다.

    잠그는 판정은 화면이 먼저 하고, 서비스가 한 번 더 막는다. 그사이
    다른 탭에서 이력이 생겨도 서비스가 거절한다.
    """
    usage = categories.usage(connection, category.id)
    queued = _is_queued(registry, category.id)
    locked = usage.runs > 0 or queued
    with st.expander(category.name):
        edited = st.text_input(
            "이름",
            value=category.name,
            key=f"category_name_{category.id}",
            max_chars=category_names.MAX_LENGTH,
            disabled=locked,
        )
        st.caption(_usage_text(usage))
        if locked:
            st.caption(_lock_reason(usage))
        elif usage.channels:
            st.caption(
                f"지우면 채널 {usage.channels}개의 기본 카테고리에서도"
                " 빠집니다."
            )
        left, right = st.columns(2)
        if left.button(
            "수정", key=f"category_rename_{category.id}", disabled=locked
        ):
            _rename(connection, category.id, edited)
        if right.button(
            "삭제", key=f"category_delete_{category.id}", disabled=locked
        ):
            _delete(connection, category.id)


def _is_queued(registry: run_registry.RunRegistry, category_id: int) -> bool:
    """대기 중이거나 실행 중인 질의가 그 카테고리를 쥐었는가."""
    return any(
        handle.status in runs.PENDING and category_id in handle.category_ids
        for handle in registry.list_all()
    )


def _usage_text(usage: categories.CategoryUsage) -> str:
    """쓰는 곳을 한 줄로 적는다."""
    parts = []
    if usage.runs:
        parts.append(f"이력 {usage.runs}건")
    if usage.channels:
        parts.append(f"채널 {usage.channels}개의 기본 카테고리")
    return " · ".join(parts) or "아직 쓰는 곳이 없습니다."


def _lock_reason(usage: categories.CategoryUsage) -> str:
    """잠근 이유. 이력이 있으면 그쪽을 먼저 적는다.

    잠긴 행에만 부른다. 이력이 없으면 대기·실행 중인 질의가 쥔 것이다.
    """
    holder = (
        "이력에서 쓰는 카테고리라"
        if usage.runs
        else "대기 중이거나 실행 중인 질의가 쓰는 카테고리라"
    )
    return f"{holder} 이름을 바꾸거나 지울 수 없습니다."


def _rename(
    connection: sqlite3.Connection, category_id: int, name: str
) -> None:
    """이름을 바꾸고 화면을 다시 그린다."""
    try:
        categories.rename_category(connection, category_id, name)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()


def _delete(connection: sqlite3.Connection, category_id: int) -> None:
    """카테고리를 지우고 화면을 다시 그린다."""
    try:
        categories.delete_category(connection, category_id)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()
