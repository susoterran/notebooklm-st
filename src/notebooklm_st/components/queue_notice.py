"""대기열 안내 — 질의 화면과 채널 화면이 같은 문구를 쓴다.

넣으면 언제 도는지 미리 알리고, 넣은 뒤의 결과를 한 문장으로
만든다. 문장을 만드는 ``enqueued_text`` 는 순수 함수라 Streamlit
없이 테스트한다.
"""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.services import run_registry, runs


def count_ahead(registry: run_registry.RunRegistry) -> int:
    """지금 넣으면 앞에 설 질의 수. 멈춤과 상관없이 센다."""
    return sum(
        1 for handle in registry.list_all() if handle.status in runs.PENDING
    )


def render(registry: run_registry.RunRegistry) -> None:
    """넣으면 언제 돌지 알리는 안내를 그린다.

    앞선 질의·정리본·멈춤 셋을 각각 한 줄로 알린다. 어느 것도
    넣기를 막지 않는다. 한 번에 하나는 워커가 지킨다.

    Args:
        registry: 실행 레지스트리.
    """
    ahead = count_ahead(registry)
    if ahead > 0:
        st.info(
            f"실행 중이거나 대기 중인 질의가 {ahead}건 있습니다."
            " 넣으면 그 뒤에 실행됩니다."
        )
    if session.get_digest_registry().is_running():
        st.info(
            "정리본을 작성 중입니다. 넣은 질의는 정리본이 끝난 뒤 시작합니다."
        )
    if registry.paused_reason() is not None:
        st.warning(
            "대기열이 멈춰 있습니다. 넣은 질의는 실행 현황에서 재개할"
            " 때까지 기다립니다."
        )


def enqueued_text(
    *, added: int, skipped: int, ahead: int, paused: bool, digesting: bool
) -> str:
    """넣은 뒤 한 번 보일 문구. 위에서부터 처음 맞는 줄을 쓴다.

    한 건이면 건수를 적지 않는다. 질의 화면은 늘 한 건이라 그
    문구가 그대로 남는다.

    Args:
        added: 넣은 질의 수. 1 이상이다.
        skipped: 이미 대기 중이거나 실행 중이라 뺀 수.
        ahead: 넣기 직전에 센 앞선 질의 수.
        paused: 대기열이 멈춰 있었는가.
        digesting: 정리본을 작성 중이었는가.

    Returns:
        화면에 한 번 보일 문구.
    """
    if added == 1:
        put = "대기열에 넣었습니다"
    else:
        put = f"{added}건을 대기열에 넣었습니다"
    if paused:
        text = f"{put}. 대기열이 멈춰 있어 재개할 때까지 기다립니다."
    elif ahead > 0:
        text = f"{put} — 앞에 {ahead}건. 실행 현황 화면에서 확인하세요."
    elif digesting:
        text = f"{put}. 정리본이 끝나면 시작합니다."
    elif added == 1:
        text = "실행을 시작했습니다. 실행 현황 화면에서 확인하세요."
    else:
        text = (
            f"{added}건을 넣고 첫 영상부터 시작했습니다."
            " 실행 현황 화면에서 확인하세요."
        )
    if skipped > 0:
        text += f" 이미 대기 중이거나 실행 중인 {skipped}건은 뺐습니다."
    return text
