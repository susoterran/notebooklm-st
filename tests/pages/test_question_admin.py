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
    assert len(app.text_area) == 1


def test_existing_questions_are_listed(app_db) -> None:
    """등록된 질문마다 확장 패널이 등록 순서대로 나온다."""
    store.add_question(app_db, "핵심 주장 3가지 정리")
    store.add_question(app_db, "발표자의 결론은?")
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    labels = [element.label for element in app.expander]
    assert labels == ["핵심 주장 3가지 정리", "발표자의 결론은?"]


def test_adding_a_question_saves_it(app_db) -> None:
    """등록 버튼을 누르면 입력한 질문이 DB 에 저장된다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_area[0].set_value("새 질문").run()
    app.button[0].click().run()
    assert not app.exception
    texts = [q.text for q in store.list_questions(app_db)]
    assert texts == ["새 질문"]


def test_blank_question_is_rejected(app_db) -> None:
    """공백만 있는 질문은 오류로 표시되고 저장되지 않는다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_area[0].set_value("   ").run()
    app.button[0].click().run()
    assert len(app.error) == 1
    assert store.list_questions(app_db) == []


def test_duplicate_question_text_does_not_crash(app_db) -> None:
    """같은 내용의 질문이 둘이어도 관리 화면이 죽지 않는다."""
    store.add_question(app_db, "같은 질문")
    store.add_question(app_db, "같은 질문")
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
