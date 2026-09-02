"""임시 노트북 정리 화면."""

import asyncio
from collections.abc import Sequence

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import errors
from notebooklm_st.services import nlm

_NOTEBOOKS_KEY = "maintenance_notebooks"
_CONFIRM_KEY = "maintenance_confirm"


def render() -> None:
    """남은 임시 노트북을 보여 주고 확인 후 삭제한다."""
    st.title("임시 노트북 정리")
    st.caption(
        "실행이 비정상 종료되면 tmp- 노트북이 남습니다."
        " 다른 창에서 실행 중인 작업이 없을 때만 지우세요."
    )

    if st.button("목록 새로 고침", key="maintenance_refresh"):
        _load()

    notebooks = st.session_state.get(_NOTEBOOKS_KEY)
    if notebooks is None:
        st.info("목록 새로 고침을 눌러 남은 노트북을 확인하세요.")
        return
    if not notebooks:
        st.success("남은 임시 노트북이 없습니다.")
        return

    st.warning(f"남은 임시 노트북 {len(notebooks)}개")
    for notebook in notebooks:
        st.write(f"- {notebook.title}")

    running = session.get_registry().running_count()
    if running > 0:
        st.warning(
            f"진행 중인 실행이 {running}건 있습니다. 그 노트북까지 지워질 수"
            " 있어 삭제를 막았습니다. 실행 현황에서 완료를 확인하세요."
        )

    confirmed = st.checkbox("삭제에 동의합니다", key=_CONFIRM_KEY)
    if st.button(
        f"{len(notebooks)}개 모두 삭제",
        key="maintenance_delete",
        disabled=not confirmed or running > 0,
    ):
        _delete([notebook.id for notebook in notebooks])


def _load() -> None:
    """목록을 조회해 세션에 담는다."""
    try:
        with st.spinner("조회 중"):
            st.session_state[_NOTEBOOKS_KEY] = asyncio.run(
                nlm.list_temp_notebooks()
            )
    except errors.MAPPED_ERRORS as error:
        st.error(errors.to_message(error).text)


def _delete(notebook_ids: Sequence[str]) -> None:
    """노트북을 지우고 목록을 비운다."""
    try:
        with st.spinner("삭제 중"):
            deleted = asyncio.run(nlm.delete_notebooks(notebook_ids))
    except errors.MAPPED_ERRORS as error:
        st.error(errors.to_message(error).text)
        return
    st.session_state[_NOTEBOOKS_KEY] = []
    st.success(f"{deleted}개를 삭제했습니다.")
