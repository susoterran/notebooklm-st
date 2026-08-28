"""질문 관리 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st.services import store


def script():
    """AppTest 진입점 — 질문 관리 화면을 렌더한다."""
    from notebooklm_st.pages import question_admin

    question_admin.render()


def test_empty_list_renders(app_db) -> None:
    """질문이 없어도 새 질문 입력란만 그린다."""
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.text_input) == 1
    assert len(app.text_area) == 1


def test_existing_questions_are_listed(app_db) -> None:
    """접힌 항목의 라벨이 본문이 아니라 제목이다."""
    store.add_question(app_db, "핵심 주장", "핵심 주장 3가지 정리")
    store.add_question(app_db, "결론", "발표자의 결론은?")
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    labels = [element.label for element in app.expander]
    assert labels == ["핵심 주장", "결론"]


def test_adding_a_question_saves_title_and_text(app_db) -> None:
    """등록 버튼을 누르면 제목과 본문이 함께 저장된다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value("새 제목").run()
    app.text_area[0].set_value("새 질문").run()
    app.button[0].click().run()
    assert not app.exception
    saved = store.list_questions(app_db)
    assert [(q.title, q.text) for q in saved] == [("새 제목", "새 질문")]


def test_blank_title_is_rejected(app_db) -> None:
    """제목이 공백뿐이면 오류로 표시되고 저장되지 않는다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value("   ").run()
    app.text_area[0].set_value("본문은 있다").run()
    app.button[0].click().run()
    assert len(app.error) == 1
    assert store.list_questions(app_db) == []


def test_blank_question_is_rejected(app_db) -> None:
    """본문이 공백뿐이면 오류로 표시되고 저장되지 않는다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value("제목은 있다").run()
    app.text_area[0].set_value("   ").run()
    app.button[0].click().run()
    assert len(app.error) == 1
    assert store.list_questions(app_db) == []


def test_duplicate_question_title_does_not_crash(app_db) -> None:
    """같은 제목의 질문이 둘이어도 관리 화면이 죽지 않는다."""
    store.add_question(app_db, "같은 제목", "첫째 본문")
    store.add_question(app_db, "같은 제목", "둘째 본문")
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.expander) == 2


def test_updating_a_question_saves_title_and_text_without_swap(
    app_db,
) -> None:
    """수정 버튼을 누르면 제목과 본문이 각자 자리에 저장된다."""
    store.add_question(app_db, "옛 제목", "옛 본문")
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[1].set_value("새 제목").run()
    app.text_area[1].set_value("새 본문").run()
    app.button[1].click().run()
    assert not app.exception
    saved = store.list_questions(app_db)
    assert [(q.title, q.text) for q in saved] == [("새 제목", "새 본문")]


def test_title_inputs_cap_their_length(app_db) -> None:
    """새 질문과 수정 양쪽의 제목 입력란이 길이를 제한한다."""
    store.add_question(app_db, "옛 제목", "옛 본문")
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert [element.max_chars for element in app.text_input] == [60, 60]
