"""이력 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st.core import models
from notebooklm_st.services import run_history


def script():
    """AppTest 진입점 — 이력 화면을 렌더한다."""
    from notebooklm_st.pages import history

    history.render()


def make_result(
    url: str = "https://youtu.be/dQw4w9WgXcQ",
    title: str | None = None,
) -> models.RunResult:
    """테스트용 실행 결과를 만든다."""
    return models.RunResult(
        url=url,
        video_id="dQw4w9WgXcQ",
        title=title,
        items=(
            models.AnswerItem(
                question_title="핵심 주장",
                question_text="핵심 주장은?",
                answer="세 가지다.",
                citations=(
                    models.Citation(number=1, text="근거 구절", score=0.9),
                ),
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
    run_history.save_run(app_db, make_result())
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.selectbox) == 1
    assert len(app.selectbox[0].options) == 1


def test_selected_run_shows_its_answers(app_db) -> None:
    """선택한 실행의 답변들을 보여 준다."""
    run_history.save_run(app_db, make_result())
    app = v1.AppTest.from_function(script).run()
    headers = [element.value for element in app.subheader]
    assert headers == ["핵심 주장"]
    assert not app.exception
    rendered = " ".join(element.value for element in app.markdown)
    assert "세 가지다." in rendered
    assert "근거 구절" in rendered


def test_run_label_leads_with_the_video_title(app_db) -> None:
    """목록 라벨이 영상 제목으로 시작한다."""
    run_history.save_run(app_db, make_result(title="밸류에이션 강의"))

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert app.selectbox[0].options[0].startswith("밸류에이션 강의 · ")


def test_run_label_falls_back_to_the_video_id(app_db) -> None:
    """제목이 없으면 영상 ID 로 대신한다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert app.selectbox[0].options[0].startswith("dQw4w9WgXcQ · ")


def test_run_label_shortens_a_long_title(app_db) -> None:
    """제목이 길면 잘라서 한 줄에 담는다."""
    run_history.save_run(app_db, make_result(title="가" * 100))

    app = v1.AppTest.from_function(script).run()

    label = app.selectbox[0].options[0]
    assert label.startswith("가" * 59 + "… · ")
