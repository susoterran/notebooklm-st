"""실행 하나를 상태에 맞게 그리는 카드."""

import streamlit as st

from notebooklm_st.components import answer_view
from notebooklm_st.services import runs


def render_run(handle: runs.RunHandle) -> None:
    """실행 하나를 상태에 맞게 그린다.

    Args:
        handle: 그릴 실행 핸들.
    """
    st.markdown(f"**{handle.url}**")
    st.caption(
        f"시작 {handle.started_at} · 질문 {len(handle.question_texts)}개"
    )

    if handle.status == "running":
        _render_running(handle)
        return
    if handle.status == "failed":
        _render_failed(handle)
        return
    _render_done(handle)


def _render_running(handle: runs.RunHandle) -> None:
    """진행 중인 실행의 최신 문구를 보여준다."""
    latest = handle.progress[-1] if handle.progress else "시작하는 중"
    st.info(f"실행 중 — {latest}")


def _render_failed(handle: runs.RunHandle) -> None:
    """실패한 실행의 사유를 표시 수준에 맞춰 보여준다."""
    text = handle.error_message or "알 수 없는 오류로 실패했습니다."
    if handle.error_level == "info":
        st.info(text)
        return
    st.error(text)


def _render_done(handle: runs.RunHandle) -> None:
    """완료된 실행의 답변을 보여준다."""
    if handle.result is None:
        st.warning("완료되었지만 결과가 비어 있습니다.")
        return
    answer_view.render_items(handle.result.items)
