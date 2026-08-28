"""질문 저장소 테스트."""

import sqlite3

import pytest

from notebooklm_st.services import store


@pytest.fixture
def connection(tmp_path):
    """임시 DB에 연결한 커넥션을 제공한다."""
    conn = store.connect(tmp_path / "test.db")
    yield conn
    conn.close()


def test_new_database_has_no_questions(connection) -> None:
    """새 DB는 질문이 없다."""
    assert store.list_questions(connection) == []


def test_add_question_returns_saved_row(connection) -> None:
    """등록한 질문이 그대로 저장되어 돌아온다."""
    saved = store.add_question(connection, "핵심 주장", "핵심 주장 3가지 정리")
    assert saved.id > 0
    assert saved.title == "핵심 주장"
    assert saved.text == "핵심 주장 3가지 정리"
    assert saved.created_at
    assert saved.created_at == saved.updated_at


def test_add_question_strips_whitespace(connection) -> None:
    """앞뒤 공백을 지운다."""
    saved = store.add_question(connection, "결론", "  발표자의 결론은?  ")
    assert saved.text == "발표자의 결론은?"


def test_add_question_rejects_blank(connection) -> None:
    """빈 질문을 거부한다."""
    with pytest.raises(ValueError):
        store.add_question(connection, "제목", "   ")


def test_list_questions_returns_insertion_order(connection) -> None:
    """등록 순서대로 돌려준다."""
    store.add_question(connection, "첫째 제목", "첫째")
    store.add_question(connection, "둘째 제목", "둘째")
    texts = [q.text for q in store.list_questions(connection)]
    assert texts == ["첫째", "둘째"]


def test_update_question_changes_text(connection) -> None:
    """질문 본문을 바꾼다."""
    saved = store.add_question(connection, "옛 제목", "옛 질문")
    store.update_question(connection, saved.id, "새 제목", "새 질문")
    assert store.list_questions(connection)[0].text == "새 질문"


def test_update_question_rejects_missing_id(connection) -> None:
    """없는 ID는 거부한다."""
    with pytest.raises(ValueError):
        store.update_question(connection, 999, "제목", "아무거나")


def test_update_question_rejects_blank(connection) -> None:
    """빈 본문을 거부한다."""
    saved = store.add_question(connection, "옛 제목", "옛 질문")
    with pytest.raises(ValueError):
        store.update_question(connection, saved.id, "제목", "  ")


def test_delete_question_removes_row(connection) -> None:
    """질문을 지운다."""
    saved = store.add_question(connection, "지울 제목", "지울 질문")
    store.delete_question(connection, saved.id)
    assert store.list_questions(connection) == []


def test_delete_question_is_silent_when_missing(connection) -> None:
    """없는 ID는 조용히 넘어간다."""
    store.delete_question(connection, 999)


def test_default_db_path_honors_env_override(monkeypatch, tmp_path) -> None:
    """환경 변수로 경로를 덮어쓸 수 있다."""
    target = tmp_path / "custom.db"
    monkeypatch.setenv(store.DB_PATH_ENV_VAR, str(target))
    assert store.default_db_path() == target


def test_default_db_path_falls_back_to_cwd(monkeypatch) -> None:
    """환경 변수가 없으면 current directory의 questions.db."""
    monkeypatch.delenv(store.DB_PATH_ENV_VAR, raising=False)
    assert store.default_db_path().name == "questions.db"


def test_add_question_stores_title(connection) -> None:
    """제목과 본문을 함께 저장한다."""
    saved = store.add_question(connection, "핵심 주장", "3가지로 정리해줘")
    assert saved.title == "핵심 주장"
    assert saved.text == "3가지로 정리해줘"


def test_add_question_strips_title_whitespace(connection) -> None:
    """제목의 앞뒤 공백을 지운다."""
    saved = store.add_question(connection, "  핵심 주장  ", "본문")
    assert saved.title == "핵심 주장"


def test_add_question_rejects_blank_title(connection) -> None:
    """제목이 비면 거부한다."""
    with pytest.raises(ValueError):
        store.add_question(connection, "   ", "본문")


def test_update_question_changes_title_and_text(connection) -> None:
    """제목과 본문을 함께 바꾼다."""
    saved = store.add_question(connection, "옛 제목", "옛 본문")
    store.update_question(connection, saved.id, "새 제목", "새 본문")
    changed = store.list_questions(connection)[0]
    assert changed.title == "새 제목"
    assert changed.text == "새 본문"


def test_update_question_rejects_blank_title(connection) -> None:
    """제목이 비면 거부한다."""
    saved = store.add_question(connection, "제목", "본문")
    with pytest.raises(ValueError):
        store.update_question(connection, saved.id, "  ", "본문")


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


def test_add_question_rejects_duplicate_title(connection) -> None:
    """같은 제목의 질문을 두 번 등록할 수 없다."""
    store.add_question(connection, "핵심 주장", "첫째 본문")
    with pytest.raises(ValueError):
        store.add_question(connection, "핵심 주장", "둘째 본문")


def test_add_question_compares_titles_after_stripping(connection) -> None:
    """앞뒤 공백만 다른 제목도 중복으로 본다."""
    store.add_question(connection, "핵심 주장", "첫째 본문")
    with pytest.raises(ValueError):
        store.add_question(connection, "  핵심 주장  ", "둘째 본문")


def test_update_question_rejects_another_questions_title(connection) -> None:
    """다른 질문이 이미 쓰는 제목으로는 바꿀 수 없다."""
    store.add_question(connection, "첫째 제목", "첫째 본문")
    second = store.add_question(connection, "둘째 제목", "둘째 본문")
    with pytest.raises(ValueError):
        store.update_question(connection, second.id, "첫째 제목", "둘째 본문")


def test_update_question_allows_keeping_its_own_title(connection) -> None:
    """자기 제목을 그대로 두고 본문만 고칠 수 있다."""
    saved = store.add_question(connection, "그대로 제목", "옛 본문")
    store.update_question(connection, saved.id, "그대로 제목", "새 본문")
    changed = store.list_questions(connection)[0]
    assert (changed.title, changed.text) == ("그대로 제목", "새 본문")
