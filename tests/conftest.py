"""페이지 테스트가 공유하는 fixture."""

import sqlite3
from collections.abc import Iterator

import pytest

from notebooklm_st import session
from notebooklm_st.services import store


@pytest.fixture
def app_db(monkeypatch, tmp_path) -> Iterator[sqlite3.Connection]:
    """앱이 임시 DB 를 쓰게 하고 캐시된 커넥션을 비운다."""
    monkeypatch.setenv(store.DB_PATH_ENV_VAR, str(tmp_path / "app.db"))
    session.get_connection.clear()
    yield store.connect(tmp_path / "app.db")
    session.get_connection.clear()
