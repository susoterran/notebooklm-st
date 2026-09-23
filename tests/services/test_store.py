"""SQLite 연결과 스키마 테스트."""

import sqlite3

import pytest

from notebooklm_st.services import channels, store


def test_default_db_path_honors_env_override(monkeypatch, tmp_path) -> None:
    """환경 변수로 경로를 덮어쓸 수 있다."""
    target = tmp_path / "custom.db"
    monkeypatch.setenv(store.DB_PATH_ENV_VAR, str(target))
    assert store.default_db_path() == target


def test_default_db_path_falls_back_to_cwd(monkeypatch) -> None:
    """환경 변수가 없으면 current directory의 questions.db."""
    monkeypatch.delenv(store.DB_PATH_ENV_VAR, raising=False)
    assert store.default_db_path().name == "questions.db"


def test_connect_rejects_a_database_with_a_stale_schema(tmp_path) -> None:
    """Title 컬럼이 없는 예전 스키마 DB는 연결 시점에 거부된다."""
    db_path = tmp_path / "stale.db"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE questions (
            id         INTEGER PRIMARY KEY,
            text       TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE runs (
            id         INTEGER PRIMARY KEY,
            url        TEXT NOT NULL,
            video_id   TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE answers (
            id             INTEGER PRIMARY KEY,
            run_id         INTEGER NOT NULL REFERENCES runs(id)
                           ON DELETE CASCADE,
            question_title TEXT NOT NULL,
            question_text  TEXT NOT NULL,
            answer         TEXT,
            citations      TEXT,
            error          TEXT
        );
        """
    )
    raw.commit()
    raw.close()

    with pytest.raises(store.StaleSchemaError) as excinfo:
        store.connect(db_path)
    assert str(db_path) in str(excinfo.value)
    assert "questions" in str(excinfo.value)


def test_connect_accepts_a_fresh_database(tmp_path) -> None:
    """새로 만든 DB는 스키마 검사를 그대로 통과한다."""
    db_path = tmp_path / "fresh.db"
    fresh_connection = store.connect(db_path)
    fresh_connection.close()


def test_connect_rejects_a_database_without_the_run_title(tmp_path) -> None:
    """runs.title 이 없는 예전 스키마 DB 는 연결 시점에 거부된다."""
    db_path = tmp_path / "no_title.db"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE questions (
            id         INTEGER PRIMARY KEY,
            title      TEXT NOT NULL,
            text       TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE runs (
            id         INTEGER PRIMARY KEY,
            url        TEXT NOT NULL,
            video_id   TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE answers (
            id             INTEGER PRIMARY KEY,
            run_id         INTEGER NOT NULL REFERENCES runs(id)
                           ON DELETE CASCADE,
            question_title TEXT NOT NULL,
            question_text  TEXT NOT NULL,
            answer         TEXT,
            citations      TEXT,
            error          TEXT
        );
        """
    )
    raw.commit()
    raw.close()

    with pytest.raises(store.StaleSchemaError) as excinfo:
        store.connect(db_path)
    assert "runs" in str(excinfo.value)
    assert "title" in str(excinfo.value)
    assert "질문 템플릿" in str(excinfo.value)


def test_connect_adds_run_metadata_to_an_older_database(tmp_path) -> None:
    """run_metadata 가 없는 DB 는 거부되지 않고 테이블만 생긴다."""
    db_path = tmp_path / "before_metadata.db"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE questions (
            id         INTEGER PRIMARY KEY,
            title      TEXT NOT NULL,
            text       TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE runs (
            id            INTEGER PRIMARY KEY,
            url           TEXT NOT NULL,
            video_id      TEXT NOT NULL,
            title         TEXT,
            created_at    TEXT NOT NULL,
            outline_id    TEXT,
            outline_url   TEXT,
            outline_title TEXT,
            exported_at   TEXT
        );

        CREATE TABLE answers (
            id             INTEGER PRIMARY KEY,
            run_id         INTEGER NOT NULL REFERENCES runs(id)
                           ON DELETE CASCADE,
            question_title TEXT NOT NULL,
            question_text  TEXT NOT NULL,
            answer         TEXT,
            citations      TEXT,
            error          TEXT
        );
        """
    )
    raw.execute(
        "INSERT INTO runs (id, url, video_id, title, created_at)"
        " VALUES (1, 'https://youtu.be/dQw4w9WgXcQ', 'dQw4w9WgXcQ',"
        " '옛 실행', '2026-09-01T10:00:00')"
    )
    raw.commit()
    raw.close()

    connection = store.connect(db_path)
    try:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(run_metadata)")
        }
        survivor = connection.execute(
            "SELECT title FROM runs WHERE id = 1"
        ).fetchone()
    finally:
        connection.close()

    assert columns == {"run_id", "channel", "upload_date"}
    assert survivor["title"] == "옛 실행"


def test_connect_rejects_a_database_without_the_outline_columns(
    tmp_path,
) -> None:
    """R4 이전 스키마의 DB 는 연결 시점에 거부된다.

    이 프로젝트는 마이그레이션을 두지 않는다. 옛 이력을 버리고 새로
    시작하는 것이 R4 의 결정이므로, 조용히 열리는 대신 안내와 함께
    멈춰야 한다.
    """
    db_path = tmp_path / "before_outline.db"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE questions (
            id         INTEGER PRIMARY KEY,
            title      TEXT NOT NULL,
            text       TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE runs (
            id         INTEGER PRIMARY KEY,
            url        TEXT NOT NULL,
            video_id   TEXT NOT NULL,
            title      TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE answers (
            id             INTEGER PRIMARY KEY,
            run_id         INTEGER NOT NULL REFERENCES runs(id)
                           ON DELETE CASCADE,
            question_title TEXT NOT NULL,
            question_text  TEXT NOT NULL,
            answer         TEXT,
            citations      TEXT,
            error          TEXT
        );
        """
    )
    raw.commit()
    raw.close()

    with pytest.raises(store.StaleSchemaError) as excinfo:
        store.connect(db_path)
    assert "runs" in str(excinfo.value)
    assert "exported_at" in str(excinfo.value)


def test_a_database_without_channels_still_opens(tmp_path) -> None:
    """Channels 가 없는 옛 DB 도 그대로 열린다.

    새 테이블은 CREATE TABLE IF NOT EXISTS 가 만들어 주므로 사용자가
    questions.db 를 지울 필요가 없다. 기존 테이블에 컬럼을 더할 때만
    삭제가 강제된다.
    """
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE questions ("
        " id INTEGER PRIMARY KEY, title TEXT NOT NULL, text TEXT NOT NULL,"
        " created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
    )
    old.commit()
    old.close()

    connection = store.connect(path)
    try:
        assert channels.list_channels(connection) == []
    finally:
        connection.close()
