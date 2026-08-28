"""인증을 확인하고 필요하면 재인증을 안내하는 조각.

앱이 뜰 때 한 번 돌고, 자동 복구가 실패한 동안에만 화면에 남는다.
"""

from collections.abc import Callable

import streamlit as st

from notebooklm_st import session

_RETRY_KEY = "auth_gate_retry"

_EXPIRED_HINT = (
    "인증이 만료되었고 자동 복구도 실패했습니다."
    " 재인증을 누르면 브라우저 창이 열립니다."
    " 구글 로그인을 마치면 앱이 이어서 진행합니다."
)

_ProgressAction = Callable[[Callable[[str], None]], bool]


def render() -> bool:
    """인증을 확인·복구하고 결과를 돌려준다.

    앱이 뜬 뒤 첫 실행에서만 확인 상자를 그린다. 확인 자체가 라이브러리
    의 무인 복구를 태우므로, 대개는 사용자가 아무것도 하지 않아도 여기서
    끝난다.

    Returns:
        인증을 쓸 수 있으면 ``True``.
    """
    gate = session.get_auth_gate()
    if not gate.tried:
        _run(gate.ensure, "인증 확인 중")
    if gate.ok:
        return True

    st.error(_EXPIRED_HINT)
    if st.button("재인증", key=_RETRY_KEY) and _run(
        gate.relogin, "브라우저에서 구글 로그인을 마쳐 주세요"
    ):
        st.rerun()
    return gate.ok


def _run(action: _ProgressAction, label: str) -> bool:
    """진행 문구를 보여 주면서 인증 동작을 돌린다.

    자식 프로세스의 출력을 그대로 상자 안에 흘려 보낸다. 브라우저가
    뜨기까지 몇 초 걸리므로 아무것도 안 보이면 멈춘 것처럼 느껴진다.

    Args:
        action: 진행 콜백을 받아 성공 여부를 돌려주는 인증 동작.
        label: 도는 동안 상자에 띄울 문구.

    Returns:
        동작이 성공하면 ``True``.
    """
    with st.status(label, expanded=True) as status:
        ok = action(st.write)
        status.update(
            label="인증되었습니다" if ok else "인증하지 못했습니다",
            state="complete" if ok else "error",
            expanded=not ok,
        )
    return ok
