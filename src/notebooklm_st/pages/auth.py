"""인증 페이지.

인증 상태와 상관없이 언제나 열 수 있다. 배너는 앱이 뜰 때 한 번만
판정하므로, 떠 있는 도중 세션이 죽으면 사람이 여기로 와서 되살린다.

업로더는 앱이 외부에 노출되지 않는다는 전제 위에 있다(R1 스펙
§13.1). 노출로 바꾸면 이 기능을 빼고 볼륨 직접 복사로 되돌린다.
"""

import streamlit as st
from streamlit.navigation import page as st_page

from notebooklm_st import session
from notebooklm_st.core import errors
from notebooklm_st.pages import _remote_login
from notebooklm_st.services import auth

TITLE = "인증"
URL_PATH = "auth"

_RECHECK_KEY = "auth_page_recheck"
_UPLOAD_KEY = "auth_page_upload"
_IMPORT_KEY = "auth_page_import"


def as_page() -> st_page.StreamlitPage:
    """내비게이션과 배너 링크가 함께 쓰는 페이지 객체.

    두 곳이 같은 ``url_path`` 를 봐야 링크가 이 페이지로 간다.
    호출마다 새 ``Page`` 를 만들지만 Streamlit 은 ``url_path`` 로
    페이지를 맞추므로 내비게이션과 배너 링크가 같은 페이지를 가리킨다.
    """
    return st.Page(render, title=TITLE, url_path=URL_PATH)


def render() -> None:
    """인증 상태와 되살리는 수단을 그린다."""
    st.title("인증")
    gate = session.get_auth_gate()
    if not gate.tried:
        with st.spinner("인증 상태 확인 중"):
            gate.ensure()
    if st.button("다시 확인", key=_RECHECK_KEY):
        with st.spinner("다시 확인 중"):
            if gate.recheck():
                # 배너는 페이지보다 먼저 그려졌다. 새 판정으로 다시
                # 그리게 한다.
                st.rerun()
    # 버튼 처리(위) 뒤에 그려야 다시 확인이 바꾼 판정을 반영한다.
    _render_state(gate)
    _remote_login.render(gate)
    _render_upload(gate)


def _render_state(gate: auth.AuthGate) -> None:
    """지금 판정을 한 줄로 그린다."""
    if gate.ok:
        st.success("인증되어 있습니다.")
    elif gate.probe_error is not None:
        st.error(errors.probe_failed_text(gate.probe_error))
    else:
        st.warning("인증이 만료되었습니다. 아래에서 다시 로그인하세요.")


def _render_upload(gate: auth.AuthGate) -> None:
    """자격증명 파일을 올려 반입하는 접은 영역을 그린다.

    반입에 성공하면 곧바로 다시 확인까지 하고 화면을 새로 그린다.
    업로드된 내용은 화면에도 로그에도 남기지 않는다. 계정 동등
    자격증명이기 때문이다.

    Args:
        gate: 반입 뒤 다시 확인할 게이트.
    """
    with st.expander("자격증명 파일 올리기 (대체 경로)"):
        st.caption(
            "데스크톱에서 `uv run notebooklm login` 으로 만든"
            " storage_state.json 을 올립니다. 절차는"
            " docs/how-to/2026-09-16-auth-reseed.md 에 있습니다."
        )
        uploaded = st.file_uploader(
            "storage_state.json", type="json", key=_UPLOAD_KEY
        )
        if not st.button("반입", key=_IMPORT_KEY, disabled=uploaded is None):
            return
        # 버튼이 ``disabled=uploaded is None`` 이라 눌렸으면 런타임엔
        # 항상 uploaded 가 있다. mypy 의 None 좁히기를 위해 남겨 둔다.
        if uploaded is None:
            return
        with st.spinner("반입 중"):
            result = auth.import_credentials(uploaded.getvalue())
        if not result.ok:
            st.error(f"반입하지 못했습니다: {result.detail}")
            return
        # ``st.rerun()`` 은 ``NoReturn`` 이다. 실패를 먼저 걸러 반환하고
        # 성공은 마지막에 둔다.
        if not gate.recheck():
            st.error("반입했지만 인증이 살아나지 않았습니다.")
            return
        st.rerun()
