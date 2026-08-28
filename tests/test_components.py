"""UI 조각 렌더 테스트."""

from streamlit.testing import v1


def test_progress_status_renders_without_error() -> None:
    """진행 상자가 예외 없이 렌더된다."""

    def script():
        from notebooklm_st.components import run_progress

        with run_progress.progress_status("시작") as report:
            report("1단계")
            report("2단계")

    app = v1.AppTest.from_function(script).run()
    assert not app.exception


def test_answer_view_renders_success_and_failure() -> None:
    """성공 항목과 실패 항목을 모두 예외 없이 렌더한다."""

    def script():
        from notebooklm_st.components import answer_view
        from notebooklm_st.core import models

        answer_view.render_items(
            [
                models.AnswerItem(
                    question_text="핵심 주장은?",
                    answer="세 가지다.",
                    citations=(
                        models.Citation(number=1, text="근거 구절", score=0.9),
                    ),
                    error=None,
                ),
                models.AnswerItem(
                    question_text="결론은?",
                    answer=None,
                    citations=(),
                    error="답변을 받지 못했습니다.",
                ),
            ]
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    headers = [element.value for element in app.subheader]
    assert headers == ["핵심 주장은?", "결론은?"]
    assert len(app.error) == 1


def test_answer_view_handles_empty_list() -> None:
    """빈 목록을 넘기면 예외 없이 아무것도 그리지 않는다."""

    def script():
        from notebooklm_st.components import answer_view

        answer_view.render_items([])

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
