"""앱 설정 저장소 테스트."""

import sqlite3
from collections.abc import Iterator

import pytest

from notebooklm_st.services import settings, store


@pytest.fixture
def connection(tmp_path) -> Iterator[sqlite3.Connection]:
    """임시 파일 DB 커넥션을 열고 테스트 후 닫는다."""
    conn = store.connect(tmp_path / "settings.db")
    yield conn
    conn.close()


def test_auto_save_is_off_until_set(connection) -> None:
    """한 번도 정한 적이 없으면 자동 저장은 꺼져 있다."""
    assert settings.auto_save(connection) is False


def test_auto_save_can_be_turned_on_and_off(connection) -> None:
    """켜고 끈 값이 그대로 읽힌다. 같은 키를 덮어쓴다."""
    settings.set_auto_save(connection, True)
    assert settings.auto_save(connection) is True

    settings.set_auto_save(connection, False)
    assert settings.auto_save(connection) is False
    count = connection.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
    assert count == 1


def test_auto_save_survives_a_new_connection(tmp_path) -> None:
    """다른 커넥션에서도 같은 값이 보인다. 재시작을 흉내 낸다."""
    path = tmp_path / "settings.db"
    first = store.connect(path)
    settings.set_auto_save(first, True)
    first.close()

    second = store.connect(path)
    try:
        assert settings.auto_save(second) is True
    finally:
        second.close()
