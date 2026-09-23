"""앱 전체가 공유하는 자원.

``@st.cache_resource`` 로 감싼 커넥션과 레지스트리는 Streamlit 의존이라
``services/`` 에 둘 수 없고, 여러 페이지가 함께 쓰므로 특정 페이지에도
둘 수 없다. 그래서 최상위 모듈로 둔다.
"""

import sqlite3

import streamlit as st

from notebooklm_st.services import auth, digest_runner, runs, store


@st.cache_resource
def get_connection() -> sqlite3.Connection:
    """앱 전체가 함께 쓰는 SQLite 커넥션을 돌려준다.

    Returns:
        스키마가 보장된 커넥션. 재실행되어도 같은 객체를 준다.
    """
    return store.connect(store.default_db_path())


@st.cache_resource
def get_registry() -> runs.RunRegistry:
    """앱 전체가 공유하는 실행 레지스트리를 돌려준다.

    ``@st.cache_resource`` 로 감싼 객체는 모든 세션·브라우저 탭에서 같은
    인스턴스다. 그래야 질의 화면에서 시작한 실행을 대시보드 화면에서
    조회할 수 있다. ``st.session_state`` 는 탭마다 별개라 쓸 수 없다.

    Returns:
        재실행되어도 같은 레지스트리 객체.
    """
    return runs.RunRegistry()


@st.cache_resource
def get_auth_gate() -> auth.AuthGate:
    """앱 전체가 공유하는 인증 게이트를 돌려준다.

    ``@st.cache_resource`` 로 감싸 모든 세션·탭이 같은 게이트를 본다.
    그래야 느린 네트워크 확인이 프로세스당 한 번만 돌고, 잠금 덕에
    탭 두 개가 동시에 확인을 시작하지 않는다.

    Returns:
        재실행되어도 같은 게이트 객체.
    """
    return auth.AuthGate()


@st.cache_resource
def get_digest_registry() -> digest_runner.DigestRegistry:
    """앱 전체가 공유하는 정리본 레지스트리를 돌려준다.

    질의 레지스트리와 같은 이유로 ``@st.cache_resource`` 를 쓴다 —
    탭이 달라도 같은 것을 봐야 정리 화면과 가드가 어긋나지 않는다.

    Returns:
        재실행되어도 같은 레지스트리 객체.
    """
    return digest_runner.DigestRegistry()
