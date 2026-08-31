"""SQLite 연결과 스키마 테스트."""

import sqlite3

import pytest

from notebooklm_st.services import store


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
