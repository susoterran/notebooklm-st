"""질의 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st import session
from notebooklm_st.services import outline, questions, runner, settings


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


def test_run_is_blocked_while_digesting(app_db) -> None:
    """정리본 작성 중에는 질의를 시작하지 못한다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장 3가지 정리")
    session.get_digest_registry().start()

    def script():
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ).run()
    app.multiselect[0].set_value(questions.list_questions(app_db)).run()

    assert not app.exception
    assert any("정리본" in element.value for element in app.info)
    assert app.button[0].disabled is True


def ask_page():
    """AppTest 진입점 — 질의 화면을 렌더한다."""
    from notebooklm_st.pages import ask

    ask.render()


def set_outline_env(monkeypatch) -> None:
    """자동 저장 체크가 열리도록 Outline 설정을 채운다."""
    monkeypatch.setenv(outline.URL_ENV_VAR, "http://192.168.0.10:3000")
    monkeypatch.setenv(outline.TOKEN_ENV_VAR, "ol_secret")
    monkeypatch.setenv(outline.COLLECTION_ENV_VAR, "col-1")


def record_start_run(monkeypatch) -> list[bool]:
    """``runner.start_run`` 을 막고 넘어온 자동 저장 값을 기록한다."""
    received: list[bool] = []

    def fake_start_run(registry, url, questions, db_path, **kwargs):
        """스레드를 띄우지 않고 자동 저장 값만 기록하는 가짜."""
        received.append(kwargs["auto_save"])
        return registry.create(url, "dQw4w9WgXcQ", ("핵심 주장은?",))

    monkeypatch.setattr(runner, "start_run", fake_start_run)
    return received


def fill_and_run(app: v1.AppTest, connection) -> None:
    """URL 과 질문을 채우고 실행을 누른다."""
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ).run()
    app.multiselect[0].set_value(questions.list_questions(connection)).run()
    app.button[0].click().run()


def test_auto_save_starts_from_the_stored_setting(app_db, monkeypatch) -> None:
    """자동 저장 체크는 DB 에 기억한 값으로 그려진다."""
    set_outline_env(monkeypatch)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    settings.set_auto_save(app_db, True)

    app = v1.AppTest.from_function(ask_page).run()

    assert not app.exception
    box = app.checkbox(key="ask_auto_save")
    assert box.label == "자동 저장"
    assert box.value is True
    assert box.disabled is False


def test_auto_save_change_is_remembered(app_db, monkeypatch) -> None:
    """체크를 바꾸면 DB 에 남고, 새로 연 화면도 그 값으로 시작한다."""
    set_outline_env(monkeypatch)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")

    app = v1.AppTest.from_function(ask_page).run()
    app.checkbox(key="ask_auto_save").check().run()

    assert not app.exception
    assert settings.auto_save(app_db) is True
    fresh = v1.AppTest.from_function(ask_page).run()
    assert fresh.checkbox(key="ask_auto_save").value is True


def test_auto_save_survives_quick_toggles(app_db, monkeypatch) -> None:
    """켜고 곧바로 끄고 다시 켜도 조작 하나 버려지지 않는다.

    key 없는 체크에 DB 값을 초기값으로 주면 DB 에 적는 순간 위젯
    ID 가 바뀌어, 바로 다음 조작이 옛 위젯으로 가서 버려진다.
    """
    set_outline_env(monkeypatch)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")

    app = v1.AppTest.from_function(ask_page).run()
    app.checkbox(key="ask_auto_save").check().run()
    app.checkbox(key="ask_auto_save").uncheck().run()

    assert app.checkbox(key="ask_auto_save").value is False
    assert settings.auto_save(app_db) is False

    app.checkbox(key="ask_auto_save").check().run()

    assert not app.exception
    assert app.checkbox(key="ask_auto_save").value is True
    assert settings.auto_save(app_db) is True


def test_auto_save_is_locked_without_outline(app_db) -> None:
    """Outline 설정이 없으면 체크를 꺼서 잠그고 DB 값은 그대로 둔다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    settings.set_auto_save(app_db, True)

    app = v1.AppTest.from_function(ask_page).run()

    assert not app.exception
    box = app.checkbox(key="ask_auto_save_locked")
    assert box.label == "자동 저장"
    assert box.disabled is True
    assert box.value is False
    assert all(item.key != "ask_auto_save" for item in app.checkbox)
    assert app.caption[0].value == (
        "Outline 연결이 설정되지 않아 자동 저장을 쓸 수 없습니다."
    )
    assert settings.auto_save(app_db) is True


def test_run_hands_the_shown_auto_save_to_the_runner(
    app_db, monkeypatch
) -> None:
    """방금 켠 체크 값이 그대로 러너로 넘어간다."""
    set_outline_env(monkeypatch)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    received = record_start_run(monkeypatch)

    app = v1.AppTest.from_function(ask_page).run()
    app.checkbox(key="ask_auto_save").check().run()
    fill_and_run(app, app_db)

    assert not app.exception
    assert received == [True]


def test_run_without_outline_hands_no_auto_save(app_db, monkeypatch) -> None:
    """Outline 설정이 없으면 DB 에 켜 두었어도 자동 저장 없이 넣는다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    settings.set_auto_save(app_db, True)
    received = record_start_run(monkeypatch)

    app = v1.AppTest.from_function(ask_page).run()
    fill_and_run(app, app_db)

    assert not app.exception
    assert received == [False]
