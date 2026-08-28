"""질의 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st.services import questions, runner


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
    questions.add_question(app_db, "핵심 주장", "핵심 주장 3가지 정리")
    questions.add_question(app_db, "결론", "발표자의 결론은?")

    def script():
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.multiselect) == 1
    assert len(app.multiselect[0].options) == 2
    assert app.multiselect[0].options == ["핵심 주장", "결론"]


def test_ask_rejects_a_non_youtube_url(app_db) -> None:
    """YouTube 영상 URL 이 아니면 오류 문구를 보여준다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장 3가지 정리")

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
    questions.add_question(app_db, "핵심 주장", "핵심 주장 3가지 정리")

    def script():
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script).run()
    assert app.button[0].disabled is True


def test_run_button_starts_a_background_run(app_db, monkeypatch) -> None:
    """실행 버튼을 누르면 백그라운드 실행을 시작한다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    started: list[str] = []

    def fake_start_run(registry, url, questions, db_path, **kwargs):
        """스레드를 띄우지 않고 호출만 기록하는 가짜."""
        started.append(url)
        return registry.create(url, "dQw4w9WgXcQ", ("핵심 주장은?",))

    monkeypatch.setattr(runner, "start_run", fake_start_run)

    def script():
        """AppTest 진입점 — 질의 화면을 렌더한다."""
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ).run()
    app.multiselect[0].set_value(questions.list_questions(app_db)).run()
    app.button[0].click().run()

    assert not app.exception
    assert started == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
    assert len(app.success) == 1


def test_run_button_is_locked_while_another_run_is_active(app_db) -> None:
    """이미 실행 중이면 버튼을 잠그고 안내를 보여준다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")

    def script():
        """AppTest 진입점 — 실행 중인 상태를 만들고 질의 화면을 그린다."""
        from notebooklm_st import session
        from notebooklm_st.pages import ask

        registry = session.get_registry()
        if not registry.list_all():
            registry.create("https://youtu.be/x", "x", ("질문",))
        ask.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert app.button[0].disabled is True
    assert any("실행 중" in element.value for element in app.info)
