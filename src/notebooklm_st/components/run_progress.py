"""실행 하나를 상태에 맞게 그리는 카드."""

import streamlit as st

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
    """완료된 실행을 요약 한 줄로 보여준다.

    답변 본문은 그리지 않는다. ``runner`` 는 이력을 DB 에 저장한
    뒤에야 실행을 done 으로 표시하므로, 여기까지 온 실행은 이력
    화면에 반드시 있다. 본문 확인과 수정은 거기서 한다.
    """
    if handle.result is None:
        st.warning("완료되었지만 결과가 비어 있습니다.")
        return
    items = handle.result.items
    st.success(f"완료 — 답변 {len(items)}건. 이력 화면에서 확인하세요.")
    failed = [item for item in items if item.error is not None]
    if not failed:
        return
    titles = ", ".join(item.question_title for item in failed)
    st.warning(f"이 중 {len(failed)}건은 답변을 받지 못했습니다: {titles}")
