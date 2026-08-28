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
                            question_title="핵심 주장",
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


def test_real_background_run_reaches_the_dashboard(app_db) -> None:
    """진짜 스레드로 실행한 결과가 대시보드에 답변으로 나타난다."""

    def script():
        """AppTest 진입점 — 실제 실행을 띄우고 끝난 뒤 현황을 그린다."""
        from notebooklm_st import session
        from notebooklm_st.core import models
        from notebooklm_st.pages import dashboard
        from notebooklm_st.services import runner, store

        async def fake_pipeline(url, questions, on_progress, **kwargs):
            """진행 문구를 남기고 결과를 돌려주는 가짜 파이프라인."""
            on_progress("자막 인덱싱 중")
            return models.RunResult(
                url=url,
                video_id="dQw4w9WgXcQ",
                items=(
                    models.AnswerItem(
                        question_title="핵심 주장",
                        question_text="핵심 주장은?",
                        answer="세 가지다.",
                        citations=(),
                        error=None,
                    ),
                ),
            )

        registry = session.get_registry()
        if not registry.list_all():
            questions = [
                models.Question(
                    id=1,
                    title="핵심 주장",
                    text="핵심 주장은?",
                    created_at="2026-08-28T10:00:00",
                    updated_at="2026-08-28T10:00:00",
                )
            ]
            runner.start_run(
                registry,
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                questions,
                store.default_db_path(),
                pipeline=fake_pipeline,
            )
            runner.join_all(timeout=5.0)
        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert [element.value for element in app.subheader] == ["핵심 주장은?"]
    rendered = " ".join(element.value for element in app.markdown)
    assert "세 가지다." in rendered
