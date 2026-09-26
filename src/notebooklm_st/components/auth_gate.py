"""인증 상태를 확인하고 만료를 알리는 배너.

앱이 뜰 때 한 번 돌고, 인증이 만료된 동안에만 화면에 남는다. 되살리는
수단(구글 로그인·다시 확인·자격증명 올리기)은 모두 「인증」 페이지에
있다. 여기서는 안내와 그 페이지로 가는 링크만 그린다.
"""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import errors
from notebooklm_st.pages import auth as auth_page


def render() -> bool:
    """인증을 확인하고 만료면 안내를 그린다.

    앱이 뜬 뒤 첫 실행에서만 확인한다. 확인 자체가 라이브러리의 토큰
    재추출과 쿠키 회전을 태우므로, 대개는 사용자가 아무것도 하지
    않아도 여기서 끝난다.

    만료와 "확인 자체가 실패" 를 구분해 그린다. 앞은 사람이 다시
    로그인해 풀 수 있고, 뒤는 원인이 다르다.

    Returns:
        인증을 쓸 수 있으면 ``True``.
    """
    gate = session.get_auth_gate()
    if not gate.tried:
        with st.spinner("인증 상태 확인 중"):
            gate.ensure()
    if gate.ok:
        return True
    if gate.probe_error is None:
        st.error(errors.LOGIN_HINT)
    else:
        st.error(errors.probe_failed_text(gate.probe_error))
    st.page_link(auth_page.as_page(), label="「인증」 페이지로 가기")
    return False
