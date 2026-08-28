"""질문 저장소 테스트."""

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
    saved = store.add_question(connection, "핵심 주장 3가지 정리")
    assert saved.id > 0
    assert saved.text == "핵심 주장 3가지 정리"
    assert saved.created_at
    assert saved.created_at == saved.updated_at


def test_add_question_strips_whitespace(connection) -> None:
    """앞뒤 공백을 지운다."""
    saved = store.add_question(connection, "  발표자의 결론은?  ")
    assert saved.text == "발표자의 결론은?"


def test_add_question_rejects_blank(connection) -> None:
    """빈 질문을 거부한다."""
    with pytest.raises(ValueError):
        store.add_question(connection, "   ")


def test_list_questions_returns_insertion_order(connection) -> None:
    """등록 순서대로 돌려준다."""
    store.add_question(connection, "첫째")
    store.add_question(connection, "둘째")
    texts = [q.text for q in store.list_questions(connection)]
    assert texts == ["첫째", "둘째"]


def test_update_question_changes_text(connection) -> None:
    """질문 본문을 바꾼다."""
    saved = store.add_question(connection, "옛 질문")
    store.update_question(connection, saved.id, "새 질문")
    assert store.list_questions(connection)[0].text == "새 질문"


def test_update_question_rejects_missing_id(connection) -> None:
    """없는 ID는 거부한다."""
    with pytest.raises(ValueError):
        store.update_question(connection, 999, "아무거나")


def test_update_question_rejects_blank(connection) -> None:
    """빈 본문을 거부한다."""
    saved = store.add_question(connection, "옛 질문")
    with pytest.raises(ValueError):
        store.update_question(connection, saved.id, "  ")


def test_delete_question_removes_row(connection) -> None:
    """질문을 지운다."""
    saved = store.add_question(connection, "지울 질문")
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
