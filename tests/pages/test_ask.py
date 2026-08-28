"""질의 화면 테스트."""

from notebooklm import exceptions
from streamlit.testing import v1

from notebooklm_st.core import models
from notebooklm_st.services import nlm, store


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


def test_execute_saves_history_and_shows_answers(app_db, monkeypatch) -> None:
    """실행에 성공하면 답변을 보여 주고 이력에 남긴다."""
    store.add_question(app_db, "핵심 주장은?")

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """진행 문구를 한 번 보고하고 성공 결과를 돌려주는 가짜."""
        on_progress("진행 중")
        return models.RunResult(
            url=url,
            video_id="dQw4w9WgXcQ",
            items=(
                models.AnswerItem(
                    question_text=questions[0].text,
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                ),
            ),
        )

    monkeypatch.setattr(nlm, "run_pipeline", fake_pipeline)

    def script():
        """AppTest 진입점 — 질의 화면을 렌더한다."""
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ).run()
    app.multiselect[0].set_value(store.list_questions(app_db)).run()
    app.button[0].click().run()

    assert not app.exception
    assert len(store.list_runs(app_db)) == 1


def test_execute_shows_info_for_a_video_without_captions(
    app_db, monkeypatch
) -> None:
    """자막 없는 영상은 오류가 아니라 안내로 표시하고 이력에 남기지 않는다."""
    store.add_question(app_db, "핵심 주장은?")

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """항상 자막 없음 예외를 던지는 가짜."""
        raise exceptions.SourceAddError(url)

    monkeypatch.setattr(nlm, "run_pipeline", fake_pipeline)

    def script():
        """AppTest 진입점 — 질의 화면을 렌더한다."""
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ).run()
    app.multiselect[0].set_value(store.list_questions(app_db)).run()
    app.button[0].click().run()

    assert not app.exception
    assert len(app.info) == 1
    assert store.list_runs(app_db) == []
