"""실행 현황 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st.core import models
from notebooklm_st.services import video_metadata


def rendered(app: v1.AppTest) -> str:
    """화면의 마크다운을 한 문자열로 모은다."""
    return " ".join(element.value for element in app.markdown)


def labels_of(app: v1.AppTest) -> list[str]:
    """화면의 버튼 라벨을 모은다."""
    return [button.label for button in app.button]


def test_dashboard_shows_notice_when_no_runs(app_db) -> None:
    """실행이 하나도 없으면 안내만 보여 준다."""

    def script():
        """AppTest 진입점 — 실행 현황을 그린다."""
        from notebooklm_st.pages import dashboard

        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.info) == 1
    assert len(app.button) == 0


def test_dashboard_draws_a_running_run_as_a_row(app_db) -> None:
    """진행 중인 실행은 배지·최신 진행 문구·숨기기 버튼의 한 줄이다."""

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
    text = rendered(app)
    assert "**상태**" in text
    assert ":blue-badge[실행 중]" in text
    assert "자막 인덱싱 중" in text
    assert "숨기기" in labels_of(app)
    assert app.button(key="dashboard_discard_finished").disabled is True
    assert len(app.info) == 0


def test_dashboard_numbers_queued_runs_after_the_running_one(app_db) -> None:
    """대기 줄은 실행 중인 줄 아래에 넣은 순서대로 차례를 단다."""

    def script():
        """AppTest 진입점 — 실행 중 하나와 대기 둘을 넣고 그린다."""
        from notebooklm_st import session
        from notebooklm_st.core import models
        from notebooklm_st.pages import dashboard

        registry = session.get_registry()
        if not registry.list_all():
            question = models.Question(
                id=1, title="질문", text="질문?", created_at="", updated_at=""
            )
            for video_id in ("queued00001", "queued00002"):
                registry.enqueue(
                    f"https://youtu.be/{video_id}", video_id, (question,)
                )
            registry.create(
                "https://youtu.be/runrunrun01", "runrunrun01", (question,)
            )
        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    cells = [element.value for element in app.markdown]
    badges = [cell for cell in cells if "-badge[" in cell]
    assert badges == [
        ":blue-badge[실행 중]",
        ":gray-badge[대기 1]",
        ":gray-badge[대기 2]",
    ]
    videos = [cell for cell in cells if "youtube.com" in cell]
    assert "runrunrun01" in videos[0]
    assert "queued00001" in videos[1]
    assert "queued00002" in videos[2]
    assert labels_of(app).count("취소") == 2


def test_cancel_removes_only_its_queued_run(app_db) -> None:
    """대기 줄의 취소는 그 실행만 지우고 남은 줄의 차례를 당긴다."""

    def script():
        """AppTest 진입점 — 대기 둘을 넣고 현황을 그린다."""
        import streamlit as st

        from notebooklm_st import session
        from notebooklm_st.core import models
        from notebooklm_st.pages import dashboard

        registry = session.get_registry()
        if "ids" not in st.session_state:
            question = models.Question(
                id=1, title="질문", text="질문?", created_at="", updated_at=""
            )
            st.session_state["ids"] = [
                registry.enqueue(
                    f"https://youtu.be/{video_id}", video_id, (question,)
                ).run_id
                for video_id in ("queued00001", "queued00002")
            ]
        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    first = app.session_state["ids"][0]

    app.button(key=f"dashboard_cancel_{first}").click().run()

    assert not app.exception
    text = rendered(app)
    assert "queued00001" not in text
    assert "queued00002" in text
    assert ":gray-badge[대기 1]" in text


def test_dashboard_draws_a_finished_run_without_the_answer(app_db) -> None:
    """완료된 실행은 답변 수만 보이고 본문은 그리지 않는다."""

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
    text = rendered(app)
    assert ":green-badge[완료]" in text
    assert "답변 1건" in text
    assert "세 가지다." not in text
    assert "지우기" in labels_of(app)
    assert app.button(key="dashboard_discard_finished").disabled is False


def test_dashboard_draws_failed_and_partial_failure_rows(app_db) -> None:
    """실패한 실행과 일부 질문이 실패한 완료 실행이 각자 결과를 그린다."""

    def script():
        """AppTest 진입점 — 실패·부분 실패 실행을 넣고 현황을 그린다."""
        from notebooklm_st import session
        from notebooklm_st.core import models
        from notebooklm_st.pages import dashboard

        registry = session.get_registry()
        if not registry.list_all():
            failed = registry.create(
                "https://youtu.be/aaaaaaaaaaa", "aaaaaaaaaaa", ("질문",)
            )
            registry.fail(
                failed.run_id, "네트워크 오류가 발생했습니다.", "error"
            )
            done = registry.create(
                "https://youtu.be/dQw4w9WgXcQ",
                "dQw4w9WgXcQ",
                ("핵심 주장은?", "요약해줘"),
            )
            registry.finish(
                done.run_id,
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
                        models.AnswerItem(
                            question_title="요약",
                            question_text="요약해줘",
                            answer="",
                            citations=(),
                            error="응답이 비어 있습니다.",
                        ),
                    ),
                ),
            )
        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    text = rendered(app)
    assert ":red-badge[실패]" in text
    assert ":red[네트워크 오류가 발생했습니다.]" in text
    assert ":green-badge[완료]" in text
    assert "1건 실패: 요약" in text


def test_dashboard_draws_the_four_save_cells(app_db) -> None:
    """저장 칸이 끔·진행 중·저장됨·미저장 네 모양을 그린다."""

    def script():
        """AppTest 진입점 — 저장 칸이 다른 실행 넷을 넣고 그린다."""
        from notebooklm_st import session
        from notebooklm_st.core import models
        from notebooklm_st.pages import dashboard
        from notebooklm_st.services import runs

        registry = session.get_registry()
        if not registry.list_all():
            registry.create(
                "https://youtu.be/runrunrun01",
                "runrunrun01",
                ("질문",),
                auto_save=True,
            )
            saved = runs.SaveOutcome(
                "saved", "저장됨", "http://192.168.0.10:3000/doc/x"
            )
            skipped = runs.SaveOutcome("skipped", "미저장 · 제목 없음", None)
            for video_id, auto_save, save in (
                ("offoffoff01", False, None),
                ("savedsaved1", True, saved),
                ("skippedskip", True, skipped),
            ):
                url = f"https://youtu.be/{video_id}"
                handle = registry.create(
                    url, video_id, ("질문",), auto_save=auto_save
                )
                registry.finish(
                    handle.run_id,
                    models.RunResult(url=url, video_id=video_id, items=()),
                    save,
                )
        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    cells = [element.value for element in app.markdown]
    assert "**저장**" in cells
    assert "자동" in cells
    assert "—" in cells
    assert "[저장됨](http://192.168.0.10:3000/doc/x)" in cells
    assert "미저장 · 제목 없음" in cells


def test_discard_removes_only_its_run(app_db) -> None:
    """한 줄의 지우기는 그 실행만 치운다."""

    def script():
        """AppTest 진입점 — 끝난 실행 둘을 넣고 현황을 그린다."""
        import streamlit as st

        from notebooklm_st import session
        from notebooklm_st.core import models
        from notebooklm_st.pages import dashboard

        registry = session.get_registry()
        if not registry.list_all():
            ids = []
            for video_id, title in (
                ("aaaaaaaaaaa", "첫 영상"),
                ("bbbbbbbbbbb", "둘째 영상"),
            ):
                url = f"https://youtu.be/{video_id}"
                handle = registry.create(url, video_id, ("질문",))
                registry.finish(
                    handle.run_id,
                    models.RunResult(
                        url=url, video_id=video_id, items=(), title=title
                    ),
                )
                ids.append(handle.run_id)
            st.session_state["ids"] = ids
        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    first = app.session_state["ids"][0]

    app.button(key=f"dashboard_discard_{first}").click().run()

    assert not app.exception
    text = rendered(app)
    assert "첫 영상" not in text
    assert "둘째 영상" in text


def test_discard_targets_its_run_after_a_new_run_arrives(app_db) -> None:
    """표를 본 뒤 새 실행이 맨 위에 끼어도 누른 행의 실행만 치운다."""

    def script():
        """AppTest 진입점 — 끝난 실행 둘, 신호가 오면 새 실행 하나."""
        import streamlit as st

        from notebooklm_st import session
        from notebooklm_st.core import models
        from notebooklm_st.pages import dashboard

        registry = session.get_registry()
        if not registry.list_all():
            ids = []
            for video_id, title in (
                ("aaaaaaaaaaa", "첫 영상"),
                ("bbbbbbbbbbb", "둘째 영상"),
            ):
                url = f"https://youtu.be/{video_id}"
                handle = registry.create(url, video_id, ("질문",))
                registry.finish(
                    handle.run_id,
                    models.RunResult(
                        url=url, video_id=video_id, items=(), title=title
                    ),
                )
                ids.append(handle.run_id)
            st.session_state["ids"] = ids
        if st.session_state.get("arrive") and (
            "arrived" not in st.session_state
        ):
            registry.create(
                "https://youtu.be/ccccccccccc", "ccccccccccc", ("질문",)
            )
            st.session_state["arrived"] = True
        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    first = app.session_state["ids"][0]
    app.session_state["arrive"] = True
    app.run()

    app.button(key=f"dashboard_discard_{first}").click().run()

    assert not app.exception
    text = rendered(app)
    assert "첫 영상" not in text
    assert "둘째 영상" in text
    assert "ccccccccccc" in text


def test_discard_finished_keeps_the_running_run(app_db) -> None:
    """끝난 항목 모두 지우기는 진행 중인 실행을 남긴다."""

    def script():
        """AppTest 진입점 — 진행 중 하나, 끝난 것 하나를 넣는다."""
        from notebooklm_st import session
        from notebooklm_st.core import models
        from notebooklm_st.pages import dashboard

        registry = session.get_registry()
        if not registry.list_all():
            registry.create(
                "https://youtu.be/runrunrun01", "runrunrun01", ("질문",)
            )
            url = "https://youtu.be/aaaaaaaaaaa"
            done = registry.create(url, "aaaaaaaaaaa", ("질문",))
            registry.finish(
                done.run_id,
                models.RunResult(
                    url=url,
                    video_id="aaaaaaaaaaa",
                    items=(),
                    title="끝난 영상",
                ),
            )
        dashboard.render()

    app = v1.AppTest.from_function(script).run()

    app.button(key="dashboard_discard_finished").click().run()

    assert not app.exception
    text = rendered(app)
    assert "끝난 영상" not in text
    assert "runrunrun01" in text
    assert app.button(key="dashboard_discard_finished").disabled is True


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


def test_real_background_run_reaches_the_dashboard(app_db, monkeypatch) -> None:
    """진짜 스레드로 실행한 결과가 대시보드에 완료 줄로 나타난다."""
    monkeypatch.setattr(
        video_metadata,
        "fetch",
        lambda url, **kwargs: video_metadata.MetadataResult(
            models.VideoMetadata(channel=None, upload_date=None), None
        ),
    )

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
    text = rendered(app)
    assert ":green-badge[완료]" in text
    assert "답변 1건" in text
    assert "세 가지다." not in text
