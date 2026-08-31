"""UI 조각 렌더 테스트."""

from streamlit.testing import v1

from notebooklm_st import session
from notebooklm_st.services import auth


def test_answer_view_renders_success_and_failure() -> None:
    """성공 항목과 실패 항목을 모두 예외 없이 렌더한다."""

    def script():
        from notebooklm_st.components import answer_view
        from notebooklm_st.core import models

        answer_view.render_items(
            [
                models.AnswerItem(
                    question_title="핵심 주장",
                    question_text="핵심 주장은?",
                    answer="세 가지다.",
                    citations=(
                        models.Citation(number=1, text="근거 구절", score=0.9),
                    ),
                    error=None,
                ),
                models.AnswerItem(
                    question_title="결론",
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
    assert headers == ["핵심 주장", "결론"]
    assert len(app.error) == 1
    rendered = " ".join(element.value for element in app.markdown)
    assert "세 가지다." in rendered
    assert "근거 구절" in rendered


def test_answer_view_handles_empty_list() -> None:
    """빈 목록을 받으면 아무 카드도 그리지 않는다."""

    def script():
        from notebooklm_st.components import answer_view

        answer_view.render_items([])

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.subheader) == 0
    assert len(app.error) == 0


def test_answer_view_folds_the_question_without_markdown() -> None:
    """질문 원문을 접어서 마크다운 없이 그대로 보여준다."""

    def script():
        """AppTest 진입점 — 마크다운이 든 질문을 그린다."""
        from notebooklm_st.components import answer_view
        from notebooklm_st.core import models

        answer_view.render_items(
            [
                models.AnswerItem(
                    question_title="핵심 주장",
                    question_text="**굵게** 와 # 헤딩이 든 질문",
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                )
            ]
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert [element.value for element in app.subheader] == ["핵심 주장"]
    assert "질문 원문" in [element.label for element in app.expander]
    assert [element.value for element in app.text] == [
        "**굵게** 와 # 헤딩이 든 질문"
    ]
    rendered = " ".join(element.value for element in app.markdown)
    assert "**굵게**" not in rendered
    assert len(app.divider) == 0


def test_answer_view_separates_items_with_a_divider() -> None:
    """항목이 여러 개면 사이에 구분자를 넣는다."""

    def script():
        """AppTest 진입점 — 답변 두 개를 그린다."""
        from notebooklm_st.components import answer_view
        from notebooklm_st.core import models

        answer_view.render_items(
            [
                models.AnswerItem(
                    question_title="핵심 주장",
                    question_text="핵심 주장은?",
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                ),
                models.AnswerItem(
                    question_title="결론",
                    question_text="결론은?",
                    answer="하나다.",
                    citations=(),
                    error=None,
                ),
            ]
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.divider) == 1
    labels = [element.label for element in app.expander]
    assert labels.count("질문 원문") == 2


def test_render_run_shows_latest_progress_while_running() -> None:
    """진행 중인 실행은 가장 최근 진행 문구를 보여준다."""

    def script():
        """AppTest 진입점 — 진행 중인 실행 카드를 그린다."""
        from notebooklm_st.components import run_progress
        from notebooklm_st.services import runs

        run_progress.render_run(
            runs.RunHandle(
                run_id="abc12345",
                url="https://youtu.be/dQw4w9WgXcQ",
                video_id="dQw4w9WgXcQ",
                question_texts=("핵심 주장은?",),
                started_at="2026-08-28T10:00:00",
                status="running",
                progress=["임시 노트북 생성 중", "자막 인덱싱 중"],
                result=None,
                error_message=None,
                error_level=None,
                finished_at=None,
            )
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    rendered = " ".join(element.value for element in app.info)
    assert "자막 인덱싱 중" in rendered
    assert "임시 노트북 생성 중" not in rendered


def test_render_run_shows_answers_when_done() -> None:
    """완료된 실행은 답변과 인용을 보여준다."""

    def script():
        """AppTest 진입점 — 완료된 실행 카드를 그린다."""
        from notebooklm_st.components import run_progress
        from notebooklm_st.core import models
        from notebooklm_st.services import runs

        run_progress.render_run(
            runs.RunHandle(
                run_id="abc12345",
                url="https://youtu.be/dQw4w9WgXcQ",
                video_id="dQw4w9WgXcQ",
                question_texts=("핵심 주장은?",),
                started_at="2026-08-28T10:00:00",
                status="done",
                progress=[],
                result=models.RunResult(
                    url="https://youtu.be/dQw4w9WgXcQ",
                    video_id="dQw4w9WgXcQ",
                    items=(
                        models.AnswerItem(
                            question_title="핵심 주장",
                            question_text="핵심 주장은?",
                            answer="세 가지다.",
                            citations=(
                                models.Citation(
                                    number=1, text="근거 구절", score=0.9
                                ),
                            ),
                            error=None,
                        ),
                    ),
                ),
                error_message=None,
                error_level=None,
                finished_at="2026-08-28T10:01:00",
            )
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert [element.value for element in app.subheader] == ["핵심 주장"]
    rendered = " ".join(element.value for element in app.markdown)
    assert "세 가지다." in rendered
    assert "근거 구절" in rendered


def test_render_run_uses_info_box_for_a_video_without_captions() -> None:
    """자막 없음 같은 정상 결과는 오류가 아니라 안내로 보여준다."""

    def script():
        """AppTest 진입점 — info 수준으로 실패한 실행을 그린다."""
        from notebooklm_st.components import run_progress
        from notebooklm_st.services import runs

        run_progress.render_run(
            runs.RunHandle(
                run_id="abc12345",
                url="https://youtu.be/dQw4w9WgXcQ",
                video_id="dQw4w9WgXcQ",
                question_texts=("핵심 주장은?",),
                started_at="2026-08-28T10:00:00",
                status="failed",
                progress=[],
                result=None,
                error_message="자막이 없거나 소스로 쓸 수 없는 영상입니다.",
                error_level="info",
                finished_at="2026-08-28T10:01:00",
            )
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.info) == 1
    assert len(app.error) == 0


def test_render_run_uses_error_box_for_a_real_failure() -> None:
    """진짜 오류는 오류 상자로 보여준다."""

    def script():
        """AppTest 진입점 — error 수준으로 실패한 실행을 그린다."""
        from notebooklm_st.components import run_progress
        from notebooklm_st.services import runs

        run_progress.render_run(
            runs.RunHandle(
                run_id="abc12345",
                url="https://youtu.be/dQw4w9WgXcQ",
                video_id="dQw4w9WgXcQ",
                question_texts=("핵심 주장은?",),
                started_at="2026-08-28T10:00:00",
                status="failed",
                progress=[],
                result=None,
                error_message="네트워크 오류가 발생했습니다.",
                error_level="error",
                finished_at="2026-08-28T10:01:00",
            )
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.error) == 1
    assert len(app.info) == 0


def test_auth_gate_stays_quiet_when_authenticated(stub_auth_gate) -> None:
    """인증이 살아 있으면 아무 경고도 내지 않는다."""

    def script():
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert not app.error


def test_auth_gate_offers_relogin_when_recovery_fails(monkeypatch) -> None:
    """자동 복구까지 실패하면 재인증 버튼을 보여 준다."""
    gate = auth.AuthGate(probe=lambda: False, login=lambda on_progress: False)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    def script():
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.error) == 1
    assert len(app.button) == 1


def test_auth_gate_relogins_when_the_button_is_pressed(monkeypatch) -> None:
    """재인증 버튼을 누르면 브라우저 로그인을 다시 돌린다."""
    calls: list = []

    def login(on_progress):
        """로그인 호출을 기록하고 실패로 답한다."""
        calls.append(on_progress)
        return False

    gate = auth.AuthGate(probe=lambda: False, login=login)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    def script():
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[0].click().run()

    assert not app.exception
    assert len(calls) == 2


def test_answer_view_stays_read_only_without_a_save_hook() -> None:
    """저장 훅이 없으면 편집 상자를 그리지 않는다."""

    def script():
        """AppTest 진입점 — 훅 없이 답변을 그린다."""
        from notebooklm_st.components import answer_view
        from notebooklm_st.core import models

        answer_view.render_items(
            [
                models.AnswerItem(
                    question_title="핵심 주장",
                    question_text="핵심 주장은?",
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                    id=7,
                )
            ]
        )

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.text_area) == 0
    rendered = " ".join(element.value for element in app.markdown)
    assert "세 가지다." in rendered


def test_answer_view_stays_read_only_for_an_item_without_an_id() -> None:
    """저장 훅이 있어도 ID 가 없으면 편집하지 않는다."""

    def script():
        """AppTest 진입점 — ID 없는 항목에 훅을 준다."""
        import streamlit as st

        from notebooklm_st.components import answer_view
        from notebooklm_st.core import models

        if "saved" not in st.session_state:
            st.session_state["saved"] = []
        saved = st.session_state["saved"]
        answer_view.render_items(
            [
                models.AnswerItem(
                    question_title="핵심 주장",
                    question_text="핵심 주장은?",
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                )
            ],
            on_save=lambda answer_id, text: saved.append((answer_id, text)),
        )

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.text_area) == 0


def test_answer_view_saves_the_edited_body() -> None:
    """편집 상자에 고친 본문을 저장 훅으로 넘긴다."""

    def script():
        """AppTest 진입점 — 편집 가능한 답변을 그린다."""
        import streamlit as st

        from notebooklm_st.components import answer_view
        from notebooklm_st.core import models

        if "saved" not in st.session_state:
            st.session_state["saved"] = []
        saved = st.session_state["saved"]
        answer_view.render_items(
            [
                models.AnswerItem(
                    question_title="핵심 주장",
                    question_text="핵심 주장은?",
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                    id=7,
                )
            ],
            on_save=lambda answer_id, text: saved.append((answer_id, text)),
        )

    app = v1.AppTest.from_function(script)
    app.run()
    assert len(app.text_area) == 1

    app.text_area[0].set_value("고친 답변").run()
    app.button[0].click().run()

    assert not app.exception
    assert app.session_state["saved"] == [(7, "고친 답변")]
