"""앱 전체가 공유하는 자원.

``@st.cache_resource`` 로 감싼 커넥션은 Streamlit 의존이라
``services/`` 에 둘 수 없고, 여러 페이지가 함께 쓰므로 특정 페이지에도
둘 수 없다. 그래서 최상위 모듈로 둔다.
"""

import sqlite3

import streamlit as st

from notebooklm_st.services import store


@st.cache_resource
def get_connection() -> sqlite3.Connection:
    """앱 전체가 함께 쓰는 SQLite 커넥션을 돌려준다.

    Returns:
        스키마가 보장된 커넥션. 재실행되어도 같은 객체를 준다.
    """
    return store.connect(store.default_db_path())
