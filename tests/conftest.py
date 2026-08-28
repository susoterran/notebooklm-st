"""페이지 테스트가 공유하는 fixture."""

import sqlite3
from collections.abc import Iterator

import pytest

from notebooklm_st import session
from notebooklm_st.services import auth, store


@pytest.fixture
def app_db(monkeypatch, tmp_path) -> Iterator[sqlite3.Connection]:
    """앱이 임시 DB 를 쓰게 하고 캐시된 공유 자원을 비운다."""
    monkeypatch.setenv(store.DB_PATH_ENV_VAR, str(tmp_path / "app.db"))
    session.get_connection.clear()
    session.get_registry.clear()
    yield store.connect(tmp_path / "app.db")
    session.get_connection.clear()
    session.get_registry.clear()


@pytest.fixture(autouse=True)
def stub_auth_gate(monkeypatch) -> auth.AuthGate:
    """테스트가 실제 인증이나 브라우저를 건드리지 않게 막는다.

    화면 테스트는 앱 진입점을 그대로 돌린다. 막지 않으면 인증 확인이
    네트워크를 타고, 실패하면 브라우저 창까지 뜬다.
    """
    gate = auth.AuthGate(probe=lambda: True, login=lambda on_progress: True)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)
    return gate
