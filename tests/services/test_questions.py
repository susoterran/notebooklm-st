"""질문 저장소 테스트."""


import pytest

from notebooklm_st.services import questions, store


@pytest.fixture
def connection(tmp_path):
    """임시 DB에 연결한 커넥션을 제공한다."""
    conn = store.connect(tmp_path / "test.db")
    yield conn
    conn.close()


def test_new_database_has_no_questions(connection) -> None:
    """새 DB는 질문이 없다."""
    assert questions.list_questions(connection) == []


def test_add_question_returns_saved_row(connection) -> None:
    """등록한 질문이 그대로 저장되어 돌아온다."""
    saved = questions.add_question(
        connection, "핵심 주장", "핵심 주장 3가지 정리"
    )
    assert saved.id > 0
    assert saved.title == "핵심 주장"
    assert saved.text == "핵심 주장 3가지 정리"
    assert saved.created_at
    assert saved.created_at == saved.updated_at


def test_add_question_strips_whitespace(connection) -> None:
    """앞뒤 공백을 지운다."""
    saved = questions.add_question(connection, "결론", "  발표자의 결론은?  ")
    assert saved.text == "발표자의 결론은?"


def test_add_question_rejects_blank(connection) -> None:
    """빈 질문을 거부한다."""
    with pytest.raises(ValueError):
        questions.add_question(connection, "제목", "   ")


def test_list_questions_returns_insertion_order(connection) -> None:
    """등록 순서대로 돌려준다."""
    questions.add_question(connection, "첫째 제목", "첫째")
    questions.add_question(connection, "둘째 제목", "둘째")
    texts = [q.text for q in questions.list_questions(connection)]
    assert texts == ["첫째", "둘째"]


def test_update_question_changes_text(connection) -> None:
    """질문 본문을 바꾼다."""
    saved = questions.add_question(connection, "옛 제목", "옛 질문")
    questions.update_question(connection, saved.id, "새 제목", "새 질문")
    assert questions.list_questions(connection)[0].text == "새 질문"


def test_update_question_rejects_missing_id(connection) -> None:
    """없는 ID는 거부한다."""
    with pytest.raises(ValueError):
        questions.update_question(connection, 999, "제목", "아무거나")


def test_update_question_rejects_blank(connection) -> None:
    """빈 본문을 거부한다."""
    saved = questions.add_question(connection, "옛 제목", "옛 질문")
    with pytest.raises(ValueError):
        questions.update_question(connection, saved.id, "제목", "  ")


def test_delete_question_removes_row(connection) -> None:
    """질문을 지운다."""
    saved = questions.add_question(connection, "지울 제목", "지울 질문")
    questions.delete_question(connection, saved.id)
    assert questions.list_questions(connection) == []


def test_delete_question_is_silent_when_missing(connection) -> None:
    """없는 ID는 조용히 넘어간다."""
    questions.delete_question(connection, 999)


def test_add_question_stores_title(connection) -> None:
    """제목과 본문을 함께 저장한다."""
    saved = questions.add_question(connection, "핵심 주장", "3가지로 정리해줘")
    assert saved.title == "핵심 주장"
    assert saved.text == "3가지로 정리해줘"


def test_add_question_strips_title_whitespace(connection) -> None:
    """제목의 앞뒤 공백을 지운다."""
    saved = questions.add_question(connection, "  핵심 주장  ", "본문")
    assert saved.title == "핵심 주장"


def test_add_question_rejects_blank_title(connection) -> None:
    """제목이 비면 거부한다."""
    with pytest.raises(ValueError):
        questions.add_question(connection, "   ", "본문")


def test_update_question_changes_title_and_text(connection) -> None:
    """제목과 본문을 함께 바꾼다."""
    saved = questions.add_question(connection, "옛 제목", "옛 본문")
    questions.update_question(connection, saved.id, "새 제목", "새 본문")
    changed = questions.list_questions(connection)[0]
    assert changed.title == "새 제목"
    assert changed.text == "새 본문"


def test_update_question_rejects_blank_title(connection) -> None:
    """제목이 비면 거부한다."""
    saved = questions.add_question(connection, "제목", "본문")
    with pytest.raises(ValueError):
        questions.update_question(connection, saved.id, "  ", "본문")


def test_add_question_rejects_duplicate_title(connection) -> None:
    """같은 제목의 질문을 두 번 등록할 수 없다."""
    questions.add_question(connection, "핵심 주장", "첫째 본문")
    with pytest.raises(ValueError):
        questions.add_question(connection, "핵심 주장", "둘째 본문")


def test_add_question_compares_titles_after_stripping(connection) -> None:
    """앞뒤 공백만 다른 제목도 중복으로 본다."""
    questions.add_question(connection, "핵심 주장", "첫째 본문")
    with pytest.raises(ValueError):
        questions.add_question(connection, "  핵심 주장  ", "둘째 본문")


def test_update_question_rejects_another_questions_title(connection) -> None:
    """다른 질문이 이미 쓰는 제목으로는 바꿀 수 없다."""
    questions.add_question(connection, "첫째 제목", "첫째 본문")
    second = questions.add_question(connection, "둘째 제목", "둘째 본문")
    with pytest.raises(ValueError):
        questions.update_question(
            connection, second.id, "첫째 제목", "둘째 본문"
        )


def test_update_question_allows_keeping_its_own_title(connection) -> None:
    """자기 제목을 그대로 두고 본문만 고칠 수 있다."""
    saved = questions.add_question(connection, "그대로 제목", "옛 본문")
    questions.update_question(connection, saved.id, "그대로 제목", "새 본문")
    changed = questions.list_questions(connection)[0]
    assert (changed.title, changed.text) == ("그대로 제목", "새 본문")
