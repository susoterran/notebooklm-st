"""질의 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st.services import store


def test_ask_asks_user_to_register_questions_first(app_db) -> None:
    """질문이 없으면 등록을 안내하는 문구를 보여준다."""

    def script():
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert any("질문 관리" in element.value for element in app.info)


def test_ask_shows_question_multiselect(app_db) -> None:
    """등록된 질문 개수만큼 선택지를 보여준다."""
    store.add_question(app_db, "핵심 주장 3가지 정리")
    store.add_question(app_db, "발표자의 결론은?")

    def script():
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.multiselect) == 1
    assert len(app.multiselect[0].options) == 2


def test_ask_rejects_a_non_youtube_url(app_db) -> None:
    """YouTube 영상 URL 이 아니면 오류 문구를 보여준다."""
    store.add_question(app_db, "핵심 주장 3가지 정리")

    def script():
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value("https://example.com/watch?v=x").run()
    assert not app.exception
    assert len(app.error) == 1


def test_ask_run_button_is_disabled_without_input(app_db) -> None:
    """URL 과 질문 선택이 없으면 실행 버튼이 비활성화된다."""
    store.add_question(app_db, "핵심 주장 3가지 정리")

    def script():
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script).run()
    assert app.button[0].disabled is True
