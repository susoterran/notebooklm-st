"""UI 조각 렌더 테스트."""

import dataclasses
import sqlite3

from streamlit.testing import v1

from notebooklm_st import session
from notebooklm_st.components import run_progress
from notebooklm_st.core import errors, models
from notebooklm_st.services import auth, runs, store


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


def make_question(title: str) -> models.Question:
    """테스트용 질문을 만든다."""
    return models.Question(
        id=1,
        title=title,
        text=f"{title}?",
        created_at="2026-09-30T17:00:00",
        updated_at="2026-09-30T17:00:00",
    )


def make_handle(**changes) -> runs.RunHandle:
    """테스트용 실행 핸들을 만든다. 넘긴 칸만 바꾼다."""
    return dataclasses.replace(
        runs.RunHandle(
            run_id="abc12345",
            url="https://youtu.be/dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
            questions=(make_question("핵심 주장"),),
            auto_save=False,
            started_at="2026-09-30T17:12:46",
            status="running",
            progress=[],
            result=None,
            save=None,
            error_message=None,
            error_level=None,
            finished_at=None,
        ),
        **changes,
    )


def make_item(title: str, error: str | None = None) -> models.AnswerItem:
    """테스트용 답변 항목을 만든다. 오류가 있으면 답변을 비운다."""
    return models.AnswerItem(
        question_title=title,
        question_text=f"{title}?",
        answer=None if error else "답이다.",
        citations=(),
        error=error,
    )


def make_done(
    *items: models.AnswerItem, title: str | None = None
) -> runs.RunHandle:
    """완료된 실행 핸들을 만든다."""
    return make_handle(
        status="done",
        result=models.RunResult(
            url="https://youtu.be/dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
            items=items,
            title=title,
        ),
        finished_at="2026-09-30T17:14:00",
    )


def test_status_badge_names_each_status() -> None:
    """상태마다 배지 글자와 색이 정해져 있다."""
    failed = make_handle(
        status="failed", error_message="x", error_level="error"
    )

    assert run_progress.status_badge(make_handle()) == ("실행 중", "blue")
    assert run_progress.status_badge(make_done()) == ("완료", "green")
    assert run_progress.status_badge(failed) == ("실패", "red")


def test_video_label_uses_the_shortened_title_once_done() -> None:
    """완료된 실행은 제목을 40자로 줄여 쓴다."""
    label = run_progress.video_label(make_done(title="가" * 50))

    assert label == "가" * 39 + "…"


def test_video_label_falls_back_to_the_video_id() -> None:
    """제목이 없으면 영상 ID 를 쓴다. 진행 중에는 제목이 아직 없다."""
    assert run_progress.video_label(make_handle()) == "dQw4w9WgXcQ"
    assert run_progress.video_label(make_done()) == "dQw4w9WgXcQ"


def test_video_label_falls_back_to_the_url_without_a_video_id() -> None:
    """영상 ID 를 못 뽑은 실행은 URL 을 쓴다."""
    label = run_progress.video_label(make_handle(video_id=""))

    assert label == "https://youtu.be/dQw4w9WgXcQ"


def test_short_time_keeps_month_day_hour_minute() -> None:
    """ISO 시각을 ``MM-DD HH:MM`` 으로 줄인다."""
    assert run_progress.short_time("2026-09-30T17:12:46") == "09-30 17:12"


def test_result_shows_the_latest_progress_while_running() -> None:
    """진행 중이면 가장 최근 진행 문구만 보인다."""
    handle = make_handle(progress=["임시 노트북 생성 중", "자막 인덱싱 중"])

    assert run_progress.result_markdown(handle) == "자막 인덱싱 중"


def test_result_says_starting_before_any_progress() -> None:
    """진행 문구가 아직 없으면 시작하는 중이라고 한다."""
    assert run_progress.result_markdown(make_handle()) == "시작하는 중"


def test_result_paints_a_real_failure_red() -> None:
    """수준이 error 인 실패는 빨간 글자다."""
    handle = make_handle(
        status="failed",
        error_message="네트워크 오류가 발생했습니다.",
        error_level="error",
    )

    assert run_progress.result_markdown(handle) == (
        ":red[네트워크 오류가 발생했습니다.]"
    )


def test_result_leaves_an_info_failure_plain() -> None:
    """자막 없음 같은 info 수준 실패는 보통 글자다."""
    handle = make_handle(
        status="failed",
        error_message="자막이 없거나 소스로 쓸 수 없는 영상입니다.",
        error_level="info",
    )

    assert run_progress.result_markdown(handle) == (
        "자막이 없거나 소스로 쓸 수 없는 영상입니다."
    )


def test_result_escapes_and_flattens_an_unexpected_error() -> None:
    """예상 못 한 오류의 대괄호·``$``·줄바꿈이 서식이 되지 않는다."""
    handle = make_handle(
        status="failed",
        error_message="예상 못 한 오류(KeyError): 'a]b'\n$x$",
        error_level="error",
    )

    assert run_progress.result_markdown(handle) == (
        ":red[예상 못 한 오류(KeyError): 'a\\]b' \\$x\\$]"
    )


def test_result_says_unknown_when_a_failure_has_no_message() -> None:
    """실패 문구가 비었으면 알 수 없는 오류라고 한다."""
    handle = make_handle(status="failed", error_level="error")

    assert run_progress.result_markdown(handle) == (
        ":red[알 수 없는 오류로 실패했습니다.]"
    )


def test_result_counts_answers_when_done() -> None:
    """완료되면 답변 수만 보인다. 본문은 이력 화면에서 본다."""
    handle = make_done(make_item("핵심 주장"))

    assert run_progress.result_markdown(handle) == "답변 1건"


def test_result_names_failed_questions_when_done() -> None:
    """답변 못 받은 질문이 있으면 수와 제목을 주황 글자로 붙인다."""
    handle = make_done(
        make_item("핵심 주장"),
        make_item("요약*", error="응답이 비어 있습니다."),
    )

    assert run_progress.result_markdown(handle) == (
        "답변 2건 · :orange[1건 실패: 요약\\*]"
    )


def test_result_warns_when_a_done_run_has_no_result() -> None:
    """완료인데 결과가 비었으면 주황 경고 문구를 쓴다."""
    handle = make_handle(status="done", finished_at="2026-09-30T17:14:00")

    assert run_progress.result_markdown(handle) == (
        ":orange[완료되었지만 결과가 비어 있습니다.]"
    )


DOC_URL = "http://192.168.0.10:3000/doc/x"


def make_saved(outcome: runs.SaveOutcome) -> runs.RunHandle:
    """자동 저장을 켜고 끝난 실행 핸들을 만든다."""
    return dataclasses.replace(make_done(), auto_save=True, save=outcome)


def test_save_is_a_dash_without_auto_save() -> None:
    """자동 저장을 끈 실행은 상태와 상관없이 ``—`` 다."""
    assert run_progress.save_markdown(make_handle()) == "—"
    assert run_progress.save_markdown(make_done()) == "—"


def test_save_says_auto_before_the_run_ends() -> None:
    """자동 저장을 켠 실행이 도는 동안은 ``자동`` 이다."""
    handle = make_handle(auto_save=True)

    assert run_progress.save_markdown(handle) == "자동"


def test_save_is_a_dash_when_the_run_failed() -> None:
    """실행이 실패하면 올릴 이력이 없어 ``—`` 다."""
    handle = make_handle(
        auto_save=True,
        status="failed",
        error_message="x",
        error_level="error",
    )

    assert run_progress.save_markdown(handle) == "—"


def test_save_links_the_saved_document() -> None:
    """저장되면 문구를 그 문서로 가는 링크로 건다."""
    handle = make_saved(runs.SaveOutcome("saved", "저장됨", DOC_URL))

    assert run_progress.save_markdown(handle) == f"[저장됨]({DOC_URL})"


def test_save_shows_why_it_skipped() -> None:
    """건너뛰었으면 이유를 보통 글자로 보인다."""
    handle = make_saved(runs.SaveOutcome("skipped", "미저장 · 제목 없음", None))

    assert run_progress.save_markdown(handle) == "미저장 · 제목 없음"


def test_save_links_a_document_it_could_not_record() -> None:
    """문서는 만들었는데 기록에 실패하면 경고 문구를 그 문서로 건다."""
    message = (
        f"문서는 만들어졌습니다: {DOC_URL} —"
        " 로컬 기록에 실패했습니다(OperationalError)."
        " 다시 저장하면 문서가 둘이 됩니다."
    )
    handle = make_saved(runs.SaveOutcome("failed", message, DOC_URL))

    assert run_progress.save_markdown(handle) == f"[{message}]({DOC_URL})"


def test_save_escapes_an_outline_error() -> None:
    """Outline 이 준 문구의 서식 글자와 줄바꿈이 글자 그대로 보인다."""
    handle = make_saved(
        runs.SaveOutcome(
            "failed", "미저장 · 저장 실패: 거부됨 [title]\n$x$", None
        )
    )

    assert run_progress.save_markdown(handle) == (
        "미저장 · 저장 실패: 거부됨 \\[title\\] \\$x\\$"
    )


def test_render_row_draws_a_badge_link_and_remove_button() -> None:
    """완료된 실행 한 줄에 배지·영상 링크·지우기 버튼을 그린다."""

    def script():
        """AppTest 진입점 — 머리글과 완료된 실행 한 줄을 그린다."""
        import streamlit as st

        from notebooklm_st.components import run_progress
        from notebooklm_st.core import models
        from notebooklm_st.services import runs

        def remember(run_id: str) -> None:
            """지운 실행 ID 를 세션에 적는다."""
            st.session_state.setdefault("removed", []).append(run_id)

        run_progress.render_header()
        run_progress.render_row(
            runs.RunHandle(
                run_id="abc12345",
                url="https://youtu.be/dQw4w9WgXcQ",
                video_id="dQw4w9WgXcQ",
                questions=(
                    models.Question(
                        id=1,
                        title="핵심 주장",
                        text="핵심 주장은?",
                        created_at="",
                        updated_at="",
                    ),
                ),
                auto_save=False,
                started_at="2026-09-30T17:12:46",
                status="done",
                progress=[],
                result=models.RunResult(
                    url="https://youtu.be/dQw4w9WgXcQ",
                    video_id="dQw4w9WgXcQ",
                    items=(),
                    title="AI [실전] 가이드 $5",
                ),
                save=None,
                error_message=None,
                error_level=None,
                finished_at="2026-09-30T17:14:00",
            ),
            remember,
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    text = " ".join(element.value for element in app.markdown)
    for name in ("상태", "영상", "시작", "질문", "결과", "저장", "동작"):
        assert f"**{name}**" in text
    assert ":green-badge[완료]" in text
    assert (
        "[AI \\[실전\\] 가이드 \\$5]"
        "(https://www.youtube.com/watch?v=dQw4w9WgXcQ)"
    ) in text
    assert "09-30 17:12" in text
    assert "1개" in text
    button = app.button(key="dashboard_discard_abc12345")
    assert button.label == "지우기"

    button.click().run()

    assert app.session_state["removed"] == ["abc12345"]


def test_render_row_offers_hide_for_a_running_run() -> None:
    """진행 중인 실행은 지우기 대신 숨기기를 준다."""

    def script():
        """AppTest 진입점 — 진행 중인 실행 한 줄을 그린다."""
        from notebooklm_st.components import run_progress
        from notebooklm_st.core import models
        from notebooklm_st.services import runs

        def ignore(run_id: str) -> None:
            """누른 것을 무시한다."""

        question = models.Question(
            id=1, title="질문", text="질문?", created_at="", updated_at=""
        )
        run_progress.render_row(
            runs.RunHandle(
                run_id="abc12345",
                url="https://youtu.be/dQw4w9WgXcQ",
                video_id="dQw4w9WgXcQ",
                questions=(question, question),
                auto_save=False,
                started_at="2026-09-30T17:12:46",
                status="running",
                progress=["자막 인덱싱 중"],
                result=None,
                save=None,
                error_message=None,
                error_level=None,
                finished_at=None,
            ),
            ignore,
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    text = " ".join(element.value for element in app.markdown)
    assert ":blue-badge[실행 중]" in text
    assert "[dQw4w9WgXcQ](https://www.youtube.com/watch?v=dQw4w9WgXcQ)" in text
    assert "자막 인덱싱 중" in text
    assert "2개" in text
    button = app.button(key="dashboard_hide_abc12345")
    assert button.label == "숨기기"
    assert button.help == "목록에서만 치웁니다. 실행은 계속됩니다."
    assert all(item.key != "dashboard_discard_abc12345" for item in app.button)


def test_auth_gate_stays_quiet_when_authenticated(stub_auth_gate) -> None:
    """인증이 살아 있으면 아무 경고도 내지 않는다."""

    def script():
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert not app.error


def test_auth_gate_separates_a_failed_probe_from_an_expiry(monkeypatch):
    """확인 자체가 실패하면 만료가 아니라 확인 불가로 알린다."""
    secret_url = "https://accounts.google.com/secret"

    def probe() -> bool:
        """매핑되지 않은 예외를 던진다."""
        raise RuntimeError(secret_url)

    gate = auth.AuthGate(probe=probe)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    def script():
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.error) == 1
    assert "확인하지 못했습니다" in app.error[0].value
    assert errors.LOGIN_HINT not in app.error[0].value
    # 예외 메시지(구글 URL 포함)가 화면에 그대로 새면 안 된다.
    # errors.py 가 _LoginRedirectError 를 못 잡을 때를 대비한 게
    # 이 분기이므로, 예외 메시지 노출은 그 대비 자체를 무너뜨린다.
    assert secret_url not in app.error[0].value
    assert "RuntimeError" in app.error[0].value


def test_auth_gate_never_draws_the_uploader(stub_auth_gate) -> None:
    """배너는 업로더를 그리지 않는다. 업로더는 인증 페이지에 있다."""

    def script():
        """AppTest 진입점 — 인증 게이트를 그린다."""
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.file_uploader) == 0


def test_auth_gate_links_to_the_auth_page_when_expired(monkeypatch) -> None:
    """만료되면 안내와 인증 페이지 링크만 그린다."""
    gate = auth.AuthGate(probe=lambda: False)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    def script():
        """AppTest 진입점 — 인증 게이트를 그린다."""
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert [box.value for box in app.error] == [errors.LOGIN_HINT]
    assert [link.proto.page for link in app.get("page_link")] == ["auth"]
    assert len(app.button) == 0
    assert len(app.file_uploader) == 0


def test_auth_gate_draws_no_link_when_authenticated(stub_auth_gate) -> None:
    """인증이 살아 있으면 링크도 그리지 않는다."""

    def script():
        """AppTest 진입점 — 인증 게이트를 그린다."""
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.get("page_link")) == 0


def test_answer_view_never_draws_an_editor() -> None:
    """편집 상자를 그리지 않는다. 수정은 Outline 이 맡는다."""

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


def test_schema_gate_explains_a_stale_database(monkeypatch) -> None:
    """스키마가 어긋나면 트레이스백 대신 안내를 보여 준다."""

    def raise_stale():
        """낡은 스키마를 만난 커넥션을 흉내낸다."""
        raise store.StaleSchemaError(
            "app.db 의 runs 테이블이 오래된 스키마입니다."
            " 이 파일을 지우고 다시 실행하세요."
        )

    monkeypatch.setattr(session, "get_connection", raise_stale)

    def script():
        """AppTest 진입점 — 스키마 게이트를 그린다."""
        from notebooklm_st.components import schema_gate

        schema_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.error) == 1
    assert "지우고 다시 실행" in app.error[0].value


def test_schema_gate_stays_quiet_when_the_schema_matches(app_db) -> None:
    """스키마가 맞으면 아무것도 그리지 않는다."""

    def script():
        """AppTest 진입점 — 스키마 게이트를 그린다."""
        from notebooklm_st.components import schema_gate

        schema_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert not app.error


def test_schema_gate_keeps_firing_through_the_resource_cache(
    monkeypatch, tmp_path
) -> None:
    """캐시된 자원 함수를 우회하지 않고도 재실행마다 다시 발동한다.

    ``session.get_connection`` 은 ``st.cache_resource`` 로 감싸여
    있다. 함수 객체를 monkeypatch 로 통째로 바꿔치기하는 테스트만
    으로는 이 데코레이터가 예외를 캐싱하지 않고 재실행마다 다시
    던지는지 검증할 수 없다. 그래서 여기서는 진짜 낡은 스키마의 DB
    파일을 만들어 실제 캐시 경로를 태운다.
    """
    db_path = tmp_path / "stale.db"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE questions (
            id         INTEGER PRIMARY KEY,
            title      TEXT NOT NULL,
            text       TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE runs (
            id         INTEGER PRIMARY KEY,
            url        TEXT NOT NULL,
            video_id   TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE answers (
            id             INTEGER PRIMARY KEY,
            run_id         INTEGER NOT NULL REFERENCES runs(id)
                           ON DELETE CASCADE,
            question_title TEXT NOT NULL,
            question_text  TEXT NOT NULL,
            answer         TEXT,
            citations      TEXT,
            error          TEXT
        );
        """
    )
    raw.commit()
    raw.close()

    monkeypatch.setenv(store.DB_PATH_ENV_VAR, str(db_path))
    session.get_connection.clear()

    def script():
        """AppTest 진입점 — 스키마 게이트를 그린다."""
        from notebooklm_st.components import schema_gate

        schema_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.error) == 1
    assert str(db_path) in app.error[0].value

    app.run()

    assert not app.exception
    assert len(app.error) == 1
    assert str(db_path) in app.error[0].value

    session.get_connection.clear()


def test_render_row_links_the_raw_url_without_a_video_id() -> None:
    """영상 ID 가 없는 실행은 입력한 URL 그대로 링크한다."""

    def script():
        """AppTest 진입점 — 영상 ID 가 빈 실행 한 줄을 그린다."""
        from notebooklm_st.components import run_progress
        from notebooklm_st.core import models
        from notebooklm_st.services import runs

        def ignore(run_id: str) -> None:
            """누른 것을 무시한다."""

        question = models.Question(
            id=1, title="질문", text="질문?", created_at="", updated_at=""
        )
        run_progress.render_row(
            runs.RunHandle(
                run_id="abc12345",
                url="https://example.com/v",
                video_id="",
                questions=(question,),
                auto_save=False,
                started_at="2026-09-30T17:12:46",
                status="running",
                progress=[],
                result=None,
                save=None,
                error_message=None,
                error_level=None,
                finished_at=None,
            ),
            ignore,
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    text = " ".join(element.value for element in app.markdown)
    assert "(https://example.com/v)" in text
