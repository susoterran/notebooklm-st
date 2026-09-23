"""정리본 화면 테스트."""

import sqlite3

import pytest
from streamlit.testing import v1

from notebooklm_st.core import models, youtube
from notebooklm_st.services import nlm, outline, run_history

BASE_URL = "http://192.168.0.10:3000"
TOKEN = "ol_api_secret_value"
COLLECTION = "0f2c1a4e-0000-4000-8000-000000000001"


def script():
    """AppTest 진입점 — 정리본 화면을 렌더한다."""
    from notebooklm_st.pages import digest

    digest.render()


@pytest.fixture
def outline_env(monkeypatch):
    """Outline 설정을 채운다."""
    monkeypatch.setenv(outline.URL_ENV_VAR, BASE_URL)
    monkeypatch.setenv(outline.TOKEN_ENV_VAR, TOKEN)
    monkeypatch.setenv(outline.COLLECTION_ENV_VAR, COLLECTION)


def make_result(
    url: str = "https://youtu.be/dQw4w9WgXcQ",
    title: str | None = "밸류에이션 강의",
) -> models.RunResult:
    """테스트용 실행 결과를 만든다."""
    return models.RunResult(
        url=url,
        video_id=youtube.extract_video_id(url) or "",
        title=title,
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


def save_exported(
    connection: sqlite3.Connection,
    document_title: str = "밸류에이션 강의",
    document_id: str = "doc-1",
) -> int:
    """Outline 에 저장까지 끝난 실행 하나를 만든다."""
    run_id = run_history.save_run(connection, make_result())
    run_history.mark_exported(
        connection,
        run_id,
        document_id=document_id,
        document_title=document_title,
        document_url=f"{BASE_URL}/doc/{document_id}",
    )
    return run_id


def test_missing_config_shows_a_notice(app_db) -> None:
    """Outline 설정이 없으면 안내를 보여 준다."""
    save_exported(app_db)

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.info) == 1
    assert outline.URL_ENV_VAR in app.info[0].value


def test_no_saved_runs_shows_a_notice(app_db, outline_env) -> None:
    """저장된 요약본이 없으면 먼저 저장하라고 말한다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.multiselect) == 0
    assert "이력" in app.info[0].value


def test_saved_runs_are_selectable(app_db, outline_env) -> None:
    """저장된 실행이 재료 목록에 나온다."""
    save_exported(app_db)

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.multiselect) == 1
    assert app.multiselect[0].options[0].startswith("밸류에이션 강의 · ")


def test_unsaved_runs_are_not_offered(app_db, outline_env) -> None:
    """아직 저장하지 않은 실행은 재료가 될 수 없다."""
    save_exported(app_db, document_title="저장된 것")
    run_history.save_run(app_db, make_result(title="저장 안 된 것"))

    app = v1.AppTest.from_function(script).run()

    options = app.multiselect[0].options
    assert len(options) == 1
    assert "저장 안 된 것" not in options[0]


def test_start_is_disabled_without_a_selection(app_db, outline_env) -> None:
    """아무것도 고르지 않으면 시작할 수 없다."""
    save_exported(app_db)

    app = v1.AppTest.from_function(script).run()

    assert app.button[0].disabled is True


def test_selecting_a_run_enables_the_start(app_db, outline_env) -> None:
    """한 건만 골라도 시작할 수 있다."""
    save_exported(app_db)

    app = v1.AppTest.from_function(script).run()
    app.multiselect[0].select(app.multiselect[0].options[0]).run()

    assert app.button[0].disabled is False


def test_running_query_blocks_the_start(app_db, outline_env) -> None:
    """질의가 돌고 있으면 정리를 시작할 수 없다."""
    from notebooklm_st import session

    save_exported(app_db)
    session.get_registry().create(
        "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", ("질문",)
    )

    app = v1.AppTest.from_function(script).run()
    app.multiselect[0].select(app.multiselect[0].options[0]).run()

    assert app.button[0].disabled is True
    assert any("질의" in element.value for element in app.info)


def test_start_hands_the_selection_to_the_runner(
    app_db, outline_env, monkeypatch
) -> None:
    """시작을 누르면 고른 실행들이 러너로 넘어간다."""
    from notebooklm_st.pages import digest as digest_page

    save_exported(app_db)
    received: dict[str, object] = {}

    def fake_start(registry, config, summaries, instruction, **kwargs):
        """넘어온 인자를 기록한다."""
        received["summaries"] = list(summaries)
        received["instruction"] = instruction
        return True

    monkeypatch.setattr(digest_page.digest_runner, "start_digest", fake_start)

    app = v1.AppTest.from_function(script).run()
    app.multiselect[0].select(app.multiselect[0].options[0]).run()
    app.button[0].click().run()

    summaries = received["summaries"]
    assert isinstance(summaries, list)
    assert len(summaries) == 1
    assert summaries[0].outline_id == "doc-1"
    assert received["instruction"] == digest_page.DEFAULT_INSTRUCTION


def test_too_many_materials_blocks_the_start(app_db, outline_env) -> None:
    """재료가 상한을 넘으면 경고가 뜨고 시작할 수 없다."""
    for index in range(nlm.DIGEST_SOURCE_LIMIT + 1):
        save_exported(
            app_db,
            document_title=f"강의 {index}",
            document_id=f"doc-{index}",
        )

    app = v1.AppTest.from_function(script).run()
    app.multiselect[0].set_value(app.multiselect[0].options).run()

    assert app.button[0].disabled is True
    assert len(app.warning) == 1


def test_blank_instruction_blocks_the_start(app_db, outline_env) -> None:
    """정리 지시가 공백뿐이면 시작할 수 없다."""
    save_exported(app_db)

    app = v1.AppTest.from_function(script).run()
    app.multiselect[0].select(app.multiselect[0].options[0]).run()
    app.text_area[0].set_value("   ").run()

    assert app.button[0].disabled is True
