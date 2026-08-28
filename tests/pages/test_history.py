"""이력 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st.core import models
from notebooklm_st.services import store


def script():
    """AppTest 진입점 — 이력 화면을 렌더한다."""
    from notebooklm_st.pages import history

    history.render()


def make_result(
    url: str = "https://youtu.be/dQw4w9WgXcQ",
) -> models.RunResult:
    """테스트용 실행 결과를 만든다."""
    return models.RunResult(
        url=url,
        video_id="dQw4w9WgXcQ",
        items=(
            models.AnswerItem(
                question_text="핵심 주장은?",
                answer="세 가지다.",
                citations=(),
                error=None,
            ),
        ),
    )


def test_empty_history_shows_notice(app_db) -> None:
    """저장된 실행이 없으면 안내를 보여 준다."""
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.info) == 1


def test_saved_run_is_selectable(app_db) -> None:
    """저장된 실행을 선택 목록에서 고를 수 있다."""
    store.save_run(app_db, make_result())
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.selectbox) == 1
    assert len(app.selectbox[0].options) == 1


def test_selected_run_shows_its_answers(app_db) -> None:
    """선택한 실행의 답변들을 보여 준다."""
    store.save_run(app_db, make_result())
    app = v1.AppTest.from_function(script).run()
    headers = [element.value for element in app.subheader]
    assert headers == ["핵심 주장은?"]
