"""실행 현황 화면."""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import run_progress

_POLL_INTERVAL = "1s"


def render() -> None:
    """실행 현황을 그린다."""
    st.title("실행 현황")
    st.caption(
        "질의는 백그라운드에서 돕니다. 이 화면을 닫거나 다른 화면으로"
        " 이동해도 실행은 계속됩니다. 서버를 재시작하면 진행 중이던"
        " 실행은 추적할 수 없습니다. 남은 임시 노트북은 정리 화면에서"
        " 확인하세요."
    )
    _render_runs()


@st.fragment(run_every=_POLL_INTERVAL)
def _render_runs() -> None:
    """레지스트리를 읽어 실행 카드를 그린다.

    **이 프래그먼트는 레지스트리를 읽기만 한다.** 안에서 상태를 바꾸면
    그 변경이 다음 재실행을 부르고 다시 상태를 바꿔 무한 루프가 된다.
    지우기는 사용자 클릭에서만 일어나므로 안전하다.
    """
    registry = session.get_registry()
    handles = registry.list_all()
    if not handles:
        st.info("아직 실행한 질의가 없습니다. 영상 질의 화면에서 시작하세요.")
        return

    for handle in handles:
        run_progress.render_run(handle)
        if handle.status == "running":
            if st.button(
                "목록에서 제거 (실행은 계속됨)",
                key=f"dashboard_force_{handle.run_id}",
                help="응답이 없는 실행을 목록에서 치웁니다."
                " 백그라운드 작업 자체는 멈추지 않습니다.",
            ):
                registry.discard(handle.run_id)
        elif st.button("지우기", key=f"dashboard_discard_{handle.run_id}"):
            registry.discard(handle.run_id)
        st.divider()
