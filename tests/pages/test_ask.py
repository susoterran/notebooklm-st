"""질의 화면 테스트."""

import pytest
from streamlit.testing import v1

from notebooklm_st import session
from notebooklm_st.core import models
from notebooklm_st.services import (
    categories,
    outline,
    questions,
    runner,
    settings,
)


@pytest.fixture
def category(app_db) -> models.Category:
    """질의에 고를 카테고리 하나를 등록한다.

    카테고리가 하나도 없으면 화면이 실행 버튼까지 그리지 않는다.
    """
    return categories.add_category(app_db, "경제")


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


def test_ask_run_button_is_disabled_without_input(app_db, category) -> None:
    """URL 과 질문 선택이 없으면 실행 버튼이 비활성화된다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장 3가지 정리")

    def script():
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script).run()
    assert app.button[0].disabled is True


def test_run_button_starts_a_background_run(
    app_db, monkeypatch, category
) -> None:
    """실행 버튼을 누르면 대기열에 넣고, URL 칸만 비운다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    started: list[str] = []

    def fake_enqueue(registry, url, questions, db_path, **kwargs):
        """스레드를 띄우지 않고 호출만 기록하는 가짜."""
        started.append(url)
        return registry.enqueue(url, "dQw4w9WgXcQ", tuple(questions))

    monkeypatch.setattr(runner, "enqueue", fake_enqueue)

    app = v1.AppTest.from_function(ask_page)
    app.run()
    fill_and_run(app, app_db)

    assert not app.exception
    assert started == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
    assert [item.value for item in app.success] == [
        "실행을 시작했습니다. 실행 현황 화면에서 확인하세요."
    ]
    assert app.text_input[0].value == ""
    assert app.multiselect[0].value == questions.list_questions(app_db)


def put_other_video(state: str = "queued") -> None:
    """다른 영상 하나를 넣는다. ``running`` 이면 시작까지 한다."""
    registry = session.get_registry()
    question = models.Question(
        id=1, title="질문", text="질문?", created_at="", updated_at=""
    )
    registry.enqueue("https://youtu.be/otherother1", "otherother1", (question,))
    if state == "running":
        registry.acquire_worker()
        registry.claim_next()


def test_a_running_query_does_not_lock_the_button(
    app_db, monkeypatch, category
) -> None:
    """실행 중인 질의가 있어도 넣을 수 있고, 몇 번째인지 알린다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    record_enqueue(monkeypatch)
    put_other_video("running")

    app = v1.AppTest.from_function(ask_page).run()
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ).run()
    app.multiselect[0].set_value(questions.list_questions(app_db)).run()
    choose_categories(app, app_db)

    assert app.button[0].disabled is False
    assert [item.value for item in app.info] == [
        "실행 중이거나 대기 중인 질의가 1건 있습니다. 넣으면 그 뒤에"
        " 실행됩니다."
    ]
    app.button[0].click().run()
    assert not app.exception
    assert [item.value for item in app.success] == [
        "대기열에 넣었습니다 — 앞에 1건. 실행 현황 화면에서 확인하세요."
    ]


def test_a_digest_does_not_lock_the_button(
    app_db, monkeypatch, category
) -> None:
    """정리본을 작성 중이어도 넣고, 끝난 뒤 시작한다고 알린다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장 3가지 정리")
    record_enqueue(monkeypatch)
    session.get_digest_registry().start()

    app = v1.AppTest.from_function(ask_page).run()
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ).run()
    app.multiselect[0].set_value(questions.list_questions(app_db)).run()
    choose_categories(app, app_db)

    assert app.button[0].disabled is False
    assert [item.value for item in app.info] == [
        "정리본을 작성 중입니다. 넣은 질의는 정리본이 끝난 뒤 시작합니다."
    ]
    app.button[0].click().run()
    assert not app.exception
    assert [item.value for item in app.success] == [
        "대기열에 넣었습니다. 정리본이 끝나면 시작합니다."
    ]


def test_a_paused_queue_still_takes_a_query(
    app_db, monkeypatch, category
) -> None:
    """멈춘 대기열에도 넣을 수 있고, 재개할 때까지 기다린다고 알린다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    record_enqueue(monkeypatch)
    put_other_video()
    session.get_registry().pause("요청 한도를 초과했습니다.")

    app = v1.AppTest.from_function(ask_page).run()
    fill_and_run(app, app_db)

    assert not app.exception
    assert [item.value for item in app.warning] == [
        "대기열이 멈춰 있습니다. 넣은 질의는 실행 현황에서 재개할 때까지"
        " 기다립니다."
    ]
    assert [item.value for item in app.success] == [
        "대기열에 넣었습니다. 대기열이 멈춰 있어 재개할 때까지 기다립니다."
    ]


def test_the_same_video_cannot_be_queued_twice(
    app_db, monkeypatch, category
) -> None:
    """대기 중이거나 실행 중인 영상을 다시 넣지 못한다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    received = record_enqueue(monkeypatch)
    question = questions.list_questions(app_db)[0]
    session.get_registry().enqueue(
        "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", (question,)
    )

    app = v1.AppTest.from_function(ask_page).run()
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30"
    ).run()
    app.multiselect[0].set_value(questions.list_questions(app_db)).run()

    assert not app.exception
    assert app.button[0].disabled is True
    assert "이 영상은 이미 대기 중이거나 실행 중입니다." in [
        item.value for item in app.info
    ]
    assert received == []


def test_a_press_after_the_video_was_queued_adds_nothing(
    app_db, monkeypatch, category
) -> None:
    """그린 뒤 같은 영상이 대기열에 들어가면 눌러도 넣지 않는다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    received = record_enqueue(monkeypatch)

    app = v1.AppTest.from_function(ask_page).run()
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ).run()
    app.multiselect[0].set_value(questions.list_questions(app_db)).run()
    choose_categories(app, app_db)
    assert app.button[0].disabled is False

    question = questions.list_questions(app_db)[0]
    session.get_registry().enqueue(
        "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", (question,)
    )
    app.button[0].click().run()

    assert not app.exception
    assert received == []
    assert len(session.get_registry().list_all()) == 1


def ask_page():
    """AppTest 진입점 — 질의 화면을 렌더한다."""
    from notebooklm_st.pages import ask

    ask.render()


def set_outline_env(monkeypatch) -> None:
    """자동 저장 체크가 열리도록 Outline 설정을 채운다."""
    monkeypatch.setenv(outline.URL_ENV_VAR, "http://192.168.0.10:3000")
    monkeypatch.setenv(outline.TOKEN_ENV_VAR, "ol_secret")
    monkeypatch.setenv(outline.COLLECTION_ENV_VAR, "col-1")


def record_enqueue(monkeypatch) -> list[bool]:
    """``runner.enqueue`` 를 막고 넘어온 자동 저장 값을 기록한다."""
    received: list[bool] = []

    def fake_enqueue(registry, url, questions, db_path, **kwargs):
        """스레드를 띄우지 않고 자동 저장 값만 기록하는 가짜."""
        received.append(kwargs["auto_save"])
        return registry.enqueue(url, "dQw4w9WgXcQ", tuple(questions))

    monkeypatch.setattr(runner, "enqueue", fake_enqueue)
    return received


def choose_categories(app: v1.AppTest, connection) -> None:
    """등록된 카테고리를 모두 고른다."""
    ids = [item.id for item in categories.list_categories(connection)]
    app.multiselect(key="ask_categories").set_value(ids).run()


def fill_and_run(app: v1.AppTest, connection) -> None:
    """URL 과 질문과 카테고리를 채우고 실행을 누른다."""
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ).run()
    app.multiselect[0].set_value(questions.list_questions(connection)).run()
    choose_categories(app, connection)
    app.button[0].click().run()


def test_auto_save_starts_from_the_stored_setting(
    app_db, monkeypatch, category
) -> None:
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


def test_auto_save_change_is_remembered(app_db, monkeypatch, category) -> None:
    """체크를 바꾸면 DB 에 남고, 새로 연 화면도 그 값으로 시작한다."""
    set_outline_env(monkeypatch)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")

    app = v1.AppTest.from_function(ask_page).run()
    app.checkbox(key="ask_auto_save").check().run()

    assert not app.exception
    assert settings.auto_save(app_db) is True
    fresh = v1.AppTest.from_function(ask_page).run()
    assert fresh.checkbox(key="ask_auto_save").value is True


def test_auto_save_survives_quick_toggles(
    app_db, monkeypatch, category
) -> None:
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


def test_auto_save_is_locked_without_outline(app_db, category) -> None:
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
    app_db, monkeypatch, category
) -> None:
    """방금 켠 체크 값이 그대로 러너로 넘어간다."""
    set_outline_env(monkeypatch)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    received = record_enqueue(monkeypatch)

    app = v1.AppTest.from_function(ask_page).run()
    app.checkbox(key="ask_auto_save").check().run()
    fill_and_run(app, app_db)

    assert not app.exception
    assert received == [True]


def test_run_without_outline_hands_no_auto_save(
    app_db, monkeypatch, category
) -> None:
    """Outline 설정이 없으면 DB 에 켜 두었어도 자동 저장 없이 넣는다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    settings.set_auto_save(app_db, True)
    received = record_enqueue(monkeypatch)

    app = v1.AppTest.from_function(ask_page).run()
    fill_and_run(app, app_db)

    assert not app.exception
    assert received == [False]


def record_categories(monkeypatch) -> list[tuple[int, ...]]:
    """``runner.enqueue`` 를 막고 넘어온 카테고리 ID 를 기록한다."""
    received: list[tuple[int, ...]] = []

    def fake_enqueue(registry, url, questions, db_path, **kwargs):
        """스레드를 띄우지 않고 카테고리 ID 만 기록하는 가짜."""
        received.append(tuple(kwargs["category_ids"]))
        return registry.enqueue(url, "dQw4w9WgXcQ", tuple(questions))

    monkeypatch.setattr(runner, "enqueue", fake_enqueue)
    return received


def test_without_categories_the_page_says_so(app_db) -> None:
    """카테고리가 없으면 안내하고 실행 버튼을 그리지 않는다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")

    app = v1.AppTest.from_function(ask_page).run()

    assert not app.exception
    assert [item.value for item in app.info] == [
        "카테고리 관리 화면에서 카테고리를 먼저 등록하세요. 카테고리를"
        " 고르지 않으면 질의할 수 없습니다."
    ]
    assert len(app.multiselect) == 1
    assert len(app.button) == 0


def test_category_options_show_names_in_order(app_db, category) -> None:
    """카테고리 선택지는 이름 순으로 이름을 보인다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    categories.add_category(app_db, "AI")

    app = v1.AppTest.from_function(ask_page).run()

    picker = app.multiselect(key="ask_categories")
    assert picker.label == "카테고리"
    assert picker.options == ["AI", "경제"]


def test_the_run_button_waits_for_a_category(app_db, category) -> None:
    """URL 과 질문이 있어도 카테고리를 고르기 전에는 잠겨 있다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")

    app = v1.AppTest.from_function(ask_page).run()
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ).run()
    app.multiselect[0].set_value(questions.list_questions(app_db)).run()

    assert app.button[0].disabled is True
    choose_categories(app, app_db)
    assert app.button[0].disabled is False


def test_run_hands_the_chosen_categories_to_the_runner(
    app_db, monkeypatch, category
) -> None:
    """고른 카테고리 ID 가 러너로 가고, 넣은 뒤에도 선택이 남는다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    received = record_categories(monkeypatch)

    app = v1.AppTest.from_function(ask_page).run()
    fill_and_run(app, app_db)

    assert not app.exception
    assert received == [(category.id,)]
    assert app.multiselect(key="ask_categories").value == [category.id]


def test_a_deleted_category_drops_out_of_the_choice(app_db, category) -> None:
    """고른 카테고리가 지워져도 화면이 깨지지 않고 선택에서 빠진다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    categories.add_category(app_db, "정치")
    app = v1.AppTest.from_function(ask_page).run()
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ).run()
    app.multiselect[0].set_value(questions.list_questions(app_db)).run()
    app.multiselect(key="ask_categories").set_value([category.id]).run()

    categories.delete_category(app_db, category.id)
    app.run()

    assert not app.exception
    assert app.multiselect(key="ask_categories").value == []
    assert app.button[0].disabled is True


def test_a_renamed_category_stays_chosen(app_db, category) -> None:
    """고른 카테고리 이름이 바뀌어도 선택이 남고 새 이름으로 보인다."""
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    app = v1.AppTest.from_function(ask_page).run()
    app.multiselect(key="ask_categories").set_value([category.id]).run()

    categories.rename_category(app_db, category.id, "거시경제")
    app.run()

    picker = app.multiselect(key="ask_categories")
    assert not app.exception
    assert picker.value == [category.id]
    assert picker.options == ["거시경제"]


def test_a_press_after_the_category_was_deleted_adds_nothing(
    app_db, monkeypatch, category
) -> None:
    """그린 뒤 고른 카테고리가 지워지면 눌러도 넣지 않는다.

    다른 탭이 지운 뒤 이 탭이 다시 그려지기 전에 누르면, 직전 그림의
    버튼이 열려 있어 콜백이 돈다. 지워진 ID 를 러너로 넘기지 않는다.
    """
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    received = record_categories(monkeypatch)

    app = v1.AppTest.from_function(ask_page).run()
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ).run()
    app.multiselect[0].set_value(questions.list_questions(app_db)).run()
    choose_categories(app, app_db)
    assert app.button[0].disabled is False

    categories.delete_category(app_db, category.id)
    app.button[0].click().run()

    assert not app.exception
    assert received == []
    assert session.get_registry().list_all() == []
