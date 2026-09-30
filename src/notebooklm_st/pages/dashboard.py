"""실행 현황 화면."""

import functools

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import run_progress
from notebooklm_st.services import run_registry, runs

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
    """레지스트리를 읽어 실행 표를 그린다.

    **이 프래그먼트는 레지스트리를 읽기만 한다.** 안에서 상태를 바꾸면
    그 변경이 다음 재실행을 부르고 다시 상태를 바꿔 무한 루프가 된다.
    지우기는 버튼의 ``on_click`` 콜백이 한다. 콜백은 사용자 클릭에서만,
    재실행 전에 돌므로 안전하고, 치운 결과가 그 재실행의 표에 바로
    보인다.
    """
    registry = session.get_registry()
    handles = registry.list_all()
    if not handles:
        st.info("아직 실행한 질의가 없습니다. 영상 질의 화면에서 시작하세요.")
        return

    st.button(
        "끝난 항목 모두 지우기",
        key="dashboard_discard_finished",
        disabled=not any(handle.status in runs.FINISHED for handle in handles),
        on_click=_discard_finished,
        args=(registry,),
    )
    run_progress.render_header()
    places = _queue_places(handles)
    for handle in handles:
        run_progress.render_row(
            handle,
            places.get(handle.run_id),
            registry.discard,
            functools.partial(_cancel, registry),
        )


def _queue_places(handles: list[runs.RunHandle]) -> dict[str, int]:
    """대기 중인 실행마다 몇 번째로 시작할지 매긴다.

    ``list_all`` 은 대기 줄을 워커가 가져갈 순서로 놓는다.

    Args:
        handles: ``list_all`` 이 돌려준 순서의 실행들.

    Returns:
        실행 ID 에서 차례(1부터)로 가는 사전. 대기 줄만 들어 있다.
    """
    queued = [handle.run_id for handle in handles if handle.status == "queued"]
    return {run_id: place for place, run_id in enumerate(queued, start=1)}


def _cancel(registry: run_registry.RunRegistry, run_id: str) -> None:
    """대기 중인 실행을 취소한다.

    버튼 콜백으로 쓴다. 누르기 직전에 워커가 가져갔으면 ``cancel`` 이
    거짓을 돌려주고 아무것도 지우지 않는다. 그 줄은 다음 그림에서 실행
    중으로 보인다.

    Args:
        registry: 실행 레지스트리.
        run_id: 취소할 실행 ID.
    """
    registry.cancel(run_id)


def _discard_finished(registry: run_registry.RunRegistry) -> None:
    """끝난 실행을 모두 지운다.

    버튼 콜백으로 쓴다. ``discard_finished`` 가 돌려주는 지운 수는
    화면에 쓸 곳이 없어 버린다.

    Args:
        registry: 실행 레지스트리.
    """
    registry.discard_finished()
