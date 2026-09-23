"""정리본 화면 테스트."""

import sqlite3

import pytest
from streamlit.testing import v1

from notebooklm_st.core import models, youtube
from notebooklm_st.services import nlm, outline, questions, run_history

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


INSTRUCTION_TITLE = "비교표로 정리"
INSTRUCTION_TEXT = "공통 주장과 엇갈리는 지점을 비교표로 정리해 줘"


def add_instruction(
    connection: sqlite3.Connection,
    title: str = INSTRUCTION_TITLE,
    text: str = INSTRUCTION_TEXT,
) -> models.Question:
    """정리 지시로 쓸 질문 하나를 등록한다."""
    return questions.add_question(connection, title, text)


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


def test_no_questions_shows_a_notice(app_db, outline_env) -> None:
    """등록된 질문이 없으면 정리 지시를 고를 수 없다고 말한다."""
    save_exported(app_db)

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.selectbox) == 0
    assert len(app.button) == 0
    assert any("질문 관리" in element.value for element in app.info)


def test_the_instruction_is_chosen_from_the_questions(
    app_db, outline_env
) -> None:
    """등록된 질문의 제목이 정리 지시 선택지가 된다."""
    save_exported(app_db)
    add_instruction(app_db)

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert app.selectbox[0].options == [INSTRUCTION_TITLE]


def test_the_chosen_instruction_body_is_shown(app_db, outline_env) -> None:
    """고른 지시의 본문을 읽을 수 있게 보여 준다."""
    save_exported(app_db)
    add_instruction(app_db)

    app = v1.AppTest.from_function(script).run()

    rendered = " ".join(element.value for element in app.markdown)
    assert INSTRUCTION_TEXT in rendered


def test_a_deleted_instruction_does_not_break_the_form(
    app_db, outline_env
) -> None:
    """고른 뒤 다른 탭에서 지워진 질문이 화면을 깨뜨리지 않는다.

    Streamlit 이 남은 첫 선택지로 스스로 되돌린다. 따로 걸러 내는
    코드를 두지 않았으므로 그 동작에 의존한다는 사실을 여기서 못
    박는다.
    """
    save_exported(app_db)
    add_instruction(app_db)
    second = add_instruction(
        app_db, title="연표로 정리", text="연표로 정리해 줘"
    )

    app = v1.AppTest.from_function(script)
    app.run()
    app.selectbox[0].select(second).run()
    questions.delete_question(app_db, second.id)
    app.run()

    assert not app.exception
    remaining = app.selectbox[0].value
    assert remaining is not None
    assert remaining.title == INSTRUCTION_TITLE
    assert len(app.button) == 1


def test_start_is_disabled_without_a_selection(app_db, outline_env) -> None:
    """아무것도 고르지 않으면 시작할 수 없다."""
    save_exported(app_db)
    add_instruction(app_db)

    app = v1.AppTest.from_function(script).run()

    assert app.button[0].disabled is True


def test_selecting_a_run_enables_the_start(app_db, outline_env) -> None:
    """한 건만 골라도 시작할 수 있다."""
    save_exported(app_db)
    add_instruction(app_db)

    app = v1.AppTest.from_function(script).run()
    app.multiselect[0].select(app.multiselect[0].options[0]).run()

    assert app.button[0].disabled is False


def test_running_query_blocks_the_start(app_db, outline_env) -> None:
    """질의가 돌고 있으면 정리를 시작할 수 없다."""
    from notebooklm_st import session

    save_exported(app_db)
    add_instruction(app_db)
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
    add_instruction(app_db)
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
    assert received["instruction"] == INSTRUCTION_TEXT


def test_start_hands_the_chosen_instruction_to_the_runner(
    app_db, outline_env, monkeypatch
) -> None:
    """고른 질문의 본문이 정리 지시로 넘어간다."""
    from notebooklm_st.pages import digest as digest_page

    save_exported(app_db)
    add_instruction(app_db)
    second = add_instruction(
        app_db, title="연표로 정리", text="연표로 정리해 줘"
    )
    received: dict[str, object] = {}

    def fake_start(registry, config, summaries, instruction, **kwargs):
        """넘어온 지시를 기록한다."""
        received["instruction"] = instruction
        return True

    monkeypatch.setattr(digest_page.digest_runner, "start_digest", fake_start)

    app = v1.AppTest.from_function(script).run()
    app.multiselect[0].select(app.multiselect[0].options[0]).run()
    app.selectbox[0].select(second).run()
    app.button[0].click().run()

    assert received["instruction"] == "연표로 정리해 줘"


def test_too_many_materials_blocks_the_start(app_db, outline_env) -> None:
    """재료가 상한을 넘으면 경고가 뜨고 시작할 수 없다."""
    add_instruction(app_db)
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


def make_draft(instruction="정리해 줘", created_on="2026-09-23", topic=None):
    """세션에 얹을 초안을 만든다."""
    return models.DigestDraft(
        body="## 공통 주장\n\n셋 다 같은 말을 한다.",
        sources=(
            models.RunSummary(
                id=1,
                url="https://youtu.be/dQw4w9WgXcQ",
                video_id="dQw4w9WgXcQ",
                title="영상 제목",
                created_at="2026-09-20T14:02:11",
                answer_count=0,
                outline_id="doc-1",
                outline_url=f"{BASE_URL}/doc/doc-1",
                outline_title="밸류에이션 강의",
                exported_at="2026-09-20T15:00:00",
            ),
        ),
        instruction=instruction,
        created_on=created_on,
        topic=topic,
    )


def finished_registry(draft=None):
    """완료 상태의 레지스트리를 만들어 앱에 얹는다."""
    from notebooklm_st import session

    registry = session.get_digest_registry()
    registry.clear()
    registry.start()
    registry.finish(draft if draft is not None else make_draft())
    return registry


def failed_registry(message="'밸류에이션 강의' 을 읽지 못했습니다."):
    """실패 상태의 레지스트리를 만들어 앱에 얹는다."""
    from notebooklm_st import session

    registry = session.get_digest_registry()
    registry.clear()
    registry.start()
    registry.fail(message, "error")
    return registry


def test_finished_digest_shows_the_body(app_db, outline_env) -> None:
    """완료되면 정리 본문을 미리보기로 보여 준다."""
    finished_registry()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    rendered = " ".join(element.value for element in app.markdown)
    assert "셋 다 같은 말을 한다." in rendered


def test_title_uses_the_topic_from_the_pipeline(app_db, outline_env) -> None:
    """NotebookLM 이 지은 주제가 제목 기본값이 된다."""
    finished_registry(make_draft(topic="밸류에이션 세 강의"))

    app = v1.AppTest.from_function(script).run()

    assert app.text_input[0].value == "[정리] 밸류에이션 세 강의"


def test_title_falls_back_to_the_created_date(app_db, outline_env) -> None:
    """주제를 받지 못하면 날짜로 떨어진다."""
    finished_registry()

    app = v1.AppTest.from_function(script).run()

    assert app.text_input[0].value == "[정리] 2026-09-23"


def test_saving_creates_an_outline_document(
    app_db, outline_env, monkeypatch
) -> None:
    """저장을 누르면 문서를 만들고 링크를 보여 준다."""
    from notebooklm_st.pages import digest as digest_page

    finished_registry()
    received: dict[str, object] = {}

    def fake_create(config, title, markdown, **kwargs):
        """넘어온 제목과 본문을 기록한다."""
        received["title"] = title
        received["markdown"] = markdown
        return outline.SavedDocument(
            id="doc-9",
            title=title,
            url=f"{BASE_URL}/doc/doc-9",
        )

    monkeypatch.setattr(digest_page.outline, "create_document", fake_create)

    app = v1.AppTest.from_function(script).run()
    app.button[0].click().run()

    assert not app.exception
    assert received["title"] == "[정리] 2026-09-23"
    assert "## 출처" in str(received["markdown"])
    assert len(app.success) == 1


def test_saving_empties_the_slot(app_db, outline_env, monkeypatch) -> None:
    """저장하면 초안이 사라지고 새 정리를 시작할 수 있다."""
    from notebooklm_st import session
    from notebooklm_st.pages import digest as digest_page

    finished_registry()
    monkeypatch.setattr(
        digest_page.outline,
        "create_document",
        lambda config, title, markdown, **kwargs: outline.SavedDocument(
            id="doc-9", title=title, url=f"{BASE_URL}/doc/doc-9"
        ),
    )

    app = v1.AppTest.from_function(script).run()
    app.button[0].click().run()

    assert session.get_digest_registry().get() is None


def test_save_failure_keeps_the_draft(app_db, outline_env, monkeypatch) -> None:
    """저장이 실패해도 초안은 화면에 남는다."""
    from notebooklm_st import session
    from notebooklm_st.pages import digest as digest_page

    finished_registry()

    def boom(config, title, markdown, **kwargs):
        """저장 실패를 만든다."""
        raise outline.OutlineError("Outline 에 연결하지 못했습니다.")

    monkeypatch.setattr(digest_page.outline, "create_document", boom)

    app = v1.AppTest.from_function(script).run()
    app.button[0].click().run()

    assert len(app.error) == 1
    handle = session.get_digest_registry().get()
    assert handle is not None
    assert handle.draft is not None


def test_discarding_clears_the_slot(app_db, outline_env) -> None:
    """버리면 슬롯이 비고 재료 선택으로 돌아간다."""
    from notebooklm_st import session

    finished_registry()

    app = v1.AppTest.from_function(script).run()
    app.button[1].click().run()

    assert session.get_digest_registry().get() is None


def test_failed_digest_shows_the_error(app_db, outline_env) -> None:
    """실패하면 사유를 그대로 보여 준다."""
    failed_registry()

    app = v1.AppTest.from_function(script).run()

    assert len(app.error) == 1
    assert "읽지 못했습니다" in app.error[0].value


def test_second_draft_gets_a_fresh_title(
    app_db, outline_env, monkeypatch
) -> None:
    """한 세션에서 정리본을 두 번 만들면 제목 칸이 새로 시작한다.

    Streamlit 은 위젯의 ``value=`` 를 그 key 가 session_state 에
    처음 나타날 때만 반영한다. 첫 초안의 제목 key 를 지우지 않으면
    두 번째 초안에서도 첫 번째 제목이 그대로 남는다.
    """
    from notebooklm_st import session
    from notebooklm_st.pages import digest as digest_page

    finished_registry(make_draft(created_on="2026-09-23"))
    monkeypatch.setattr(
        digest_page.outline,
        "create_document",
        lambda config, title, markdown, **kwargs: outline.SavedDocument(
            id="doc-9", title=title, url=f"{BASE_URL}/doc/doc-9"
        ),
    )

    app = v1.AppTest.from_function(script)
    app.run()
    assert app.text_input[0].value == "[정리] 2026-09-23"
    app.button[0].click().run()  # 저장
    app.button[0].click().run()  # 새 정리본 만들기

    registry = session.get_digest_registry()
    registry.start()
    registry.finish(make_draft(created_on="2026-09-24"))
    app.run()

    assert not app.exception
    assert app.text_input[0].value == "[정리] 2026-09-24"


def test_discarded_draft_gets_a_fresh_title(app_db, outline_env) -> None:
    """버린 초안 다음에도 제목 칸이 새로 시작한다."""
    from notebooklm_st import session

    finished_registry(make_draft(created_on="2026-09-23"))

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[1].click().run()  # 버리기

    registry = session.get_digest_registry()
    registry.start()
    registry.finish(make_draft(created_on="2026-09-24"))
    app.run()

    assert not app.exception
    assert app.text_input[0].value == "[정리] 2026-09-24"
