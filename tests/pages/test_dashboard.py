"""실행 현황 화면 테스트."""

from streamlit.testing import v1


def test_dashboard_shows_notice_when_no_runs(app_db) -> None:
    """실행이 하나도 없으면 안내를 보여준다."""

    def script():
        """AppTest 진입점 — 실행 현황을 그린다."""
        from notebooklm_st.pages import dashboard

        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.info) == 1


def test_dashboard_shows_a_running_run(app_db) -> None:
    """진행 중인 실행의 최신 문구를 보여준다."""

    def script():
        """AppTest 진입점 — 실행을 하나 등록하고 현황을 그린다."""
        from notebooklm_st import session
        from notebooklm_st.pages import dashboard

        registry = session.get_registry()
        if not registry.list_all():
            handle = registry.create(
                "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", ("질문",)
            )
            registry.append_progress(handle.run_id, "자막 인덱싱 중")
        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    rendered = " ".join(element.value for element in app.info)
    assert "자막 인덱싱 중" in rendered


def test_dashboard_shows_answers_of_a_finished_run(app_db) -> None:
    """완료된 실행의 답변을 보여준다."""

    def script():
        """AppTest 진입점 — 완료된 실행을 넣고 현황을 그린다."""
        from notebooklm_st import session
        from notebooklm_st.core import models
        from notebooklm_st.pages import dashboard

        registry = session.get_registry()
        if not registry.list_all():
            handle = registry.create(
                "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", ("핵심 주장은?",)
            )
            registry.finish(
                handle.run_id,
                models.RunResult(
                    url="https://youtu.be/dQw4w9WgXcQ",
                    video_id="dQw4w9WgXcQ",
                    items=(
                        models.AnswerItem(
                            question_text="핵심 주장은?",
                            answer="세 가지다.",
                            citations=(),
                            error=None,
                        ),
                    ),
                ),
            )
        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert [element.value for element in app.subheader] == ["핵심 주장은?"]
    rendered = " ".join(element.value for element in app.markdown)
    assert "세 가지다." in rendered


def test_dashboard_polls_without_error_on_repeated_runs(app_db) -> None:
    """폴링을 흉내내 여러 번 실행해도 예외가 나지 않는다."""

    def script():
        """AppTest 진입점 — 실행 현황을 그린다."""
        from notebooklm_st.pages import dashboard

        dashboard.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.run()
    app.run()
    assert not app.exception
