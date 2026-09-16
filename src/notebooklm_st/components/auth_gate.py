"""인증 상태를 확인하고 만료를 안내하는 조각.

앱이 뜰 때 한 번 돌고, 인증이 만료된 동안에만 화면에 남는다.
브라우저 로그인은 하지 않는다. 자격증명은 사람이 데스크톱에서
만들어 온다(→ ``core.errors.LOGIN_HINT``).

업로더는 앱이 외부에 노출되지 않는다는 전제 위에 있다(스펙
§13.1). 노출로 바꾸면 이 기능을 빼고 볼륨 직접 복사로 되돌린다.
"""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import errors
from notebooklm_st.services import auth

_RECHECK_KEY = "auth_gate_recheck"
_UPLOAD_KEY = "auth_gate_upload"
_IMPORT_KEY = "auth_gate_import"


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
    _render_upload(gate)
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


def _render_upload(gate: auth.AuthGate) -> None:
    """자격증명을 올려 반입하는 접은 영역을 그린다.

    반입에 성공하면 곧바로 다시 확인까지 하고 화면을 새로 그린다.
    사용자가 버튼을 두 번 누르지 않아도 된다.

    업로드된 내용은 화면에도 로그에도 남기지 않는다. 계정 동등
    자격증명이기 때문이다.

    Args:
        gate: 반입 뒤 다시 확인할 게이트.
    """
    with st.expander("자격증명 올리기"):
        st.caption(
            "데스크톱에서 만든 storage_state.json 을 올립니다."
            " 절차는 docs/how-to/2026-09-16-auth-reseed.md 에 있습니다."
        )
        uploaded = st.file_uploader(
            "storage_state.json", type="json", key=_UPLOAD_KEY
        )
        if not st.button("반입", key=_IMPORT_KEY, disabled=uploaded is None):
            return
        if uploaded is None:
            return
        with st.spinner("반입 중"):
            result = auth.import_credentials(uploaded.getvalue())
        if not result.ok:
            st.error(f"반입하지 못했습니다: {result.detail}")
            return
        if gate.recheck():
            st.rerun()
        st.error("반입했지만 인증이 살아나지 않았습니다.")
