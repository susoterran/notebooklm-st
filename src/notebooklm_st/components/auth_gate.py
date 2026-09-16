"""인증 상태를 확인하고 만료를 안내하는 조각.

앱이 뜰 때 한 번 돌고, 인증이 만료된 동안에만 화면에 남는다.
브라우저 로그인은 하지 않는다. 자격증명은 사람이 데스크톱에서
만들어 온다(→ ``core.errors.LOGIN_HINT``).
"""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import errors

_RECHECK_KEY = "auth_gate_recheck"


def render() -> bool:
    """인증을 확인하고 결과를 그린다.

    앱이 뜬 뒤 첫 실행에서만 확인한다. 확인 자체가 라이브러리의 토큰
    재추출과 쿠키 회전을 태우므로, 대개는 사용자가 아무것도 하지
    않아도 여기서 끝난다.

    만료와 "확인 자체가 실패" 를 구분해 그린다. 앞은 사람이 재시드로
    풀 수 있고, 뒤는 원인이 다르다.

    Returns:
        인증을 쓸 수 있으면 ``True``.
    """
    gate = session.get_auth_gate()
    if not gate.tried:
        with st.spinner("인증 상태 확인 중"):
            gate.ensure()
    if gate.ok:
        return True

    _render_notice(gate.probe_error)
    if st.button("다시 확인", key=_RECHECK_KEY):
        with st.spinner("다시 확인 중"):
            if gate.recheck():
                st.rerun()
    return gate.ok


def _render_notice(probe_error: Exception | None) -> None:
    """만료인지 확인 불가인지 가려 안내를 그린다.

    Args:
        probe_error: 확인 자체가 실패했을 때 그 예외. 만료면 ``None``.
    """
    if probe_error is None:
        st.error(errors.LOGIN_HINT)
        return
    st.error(
        "인증 상태를 확인하지 못했습니다"
        f"({type(probe_error).__name__}: {probe_error})"
    )
