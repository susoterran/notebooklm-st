"""정리본 화면 테스트."""

import dataclasses
import sqlite3

import pytest
from streamlit.testing import v1

from notebooklm_st.core import models, youtube
from notebooklm_st.services import (
    nlm,
    outline,
    questions,
    run_history,
    run_history_sync,
    run_links,
)

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
    metadata: models.VideoMetadata | None = None,
) -> int:
    """Outline 에 저장까지 끝난 실행 하나를 만든다."""
    run_id = run_history.save_run(connection, make_result(), metadata)
    run_links.mark_exported(
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


def select_rows(
    app: v1.AppTest, connection: sqlite3.Connection, rows: list[int]
) -> None:
    """재료 표에서 행을 고른다.

    AppTest 는 표 클릭을 흉내 내지 못한다. 대신 Streamlit 이 허용하는
    세션 상태 주입을 쓴다. 브라우저가 선택을 되돌려 보내지 않으므로
    선택은 바로 다음 실행 한 번에만 반영된다.
    """
    from notebooklm_st.pages import _digest_materials

    key = _digest_materials.widget_key(
        run_history_sync.list_exported(connection)
    )
    app.session_state[key] = {
        "selection": {"rows": rows, "columns": [], "cells": []}
    }


def click_start(
    app: v1.AppTest, connection: sqlite3.Connection, rows: list[int]
) -> None:
    """재료를 고른 채로 정리 시작을 누른다.

    AppTest 는 직전 실행에서 잠긴 버튼을 누르지 못하게 막는다. 한 번
    골라 버튼을 풀고, 누르는 실행에서 다시 고른다 — 선택이 한 실행만
    가기 때문이다.
    """
    select_rows(app, connection, rows)
    app.run()
    select_rows(app, connection, rows)
    app.button[0].click().run()


def table_titles(app: v1.AppTest) -> list[str]:
    """재료 표에 나온 문서 제목을 위에서부터 돌려준다."""
    return list(app.dataframe[0].value["title"])


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
    assert len(app.dataframe) == 0
    assert "이력" in app.info[0].value


def test_saved_runs_are_listed_in_the_table(app_db, outline_env) -> None:
    """저장된 실행이 문서 제목과 Outline 링크로 표에 나온다."""
    save_exported(app_db)

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert table_titles(app) == ["밸류에이션 강의"]
    assert list(app.dataframe[0].value["url"]) == [f"{BASE_URL}/doc/doc-1"]


def test_saved_runs_are_listed_newest_first(app_db, outline_env) -> None:
    """최근에 저장한 요약본이 표의 맨 위에 온다."""
    save_exported(app_db, document_title="먼저 저장", document_id="doc-1")
    save_exported(app_db, document_title="나중 저장", document_id="doc-2")

    app = v1.AppTest.from_function(script).run()

    assert table_titles(app) == ["나중 저장", "먼저 저장"]


def test_unsaved_runs_are_not_offered(app_db, outline_env) -> None:
    """아직 저장하지 않은 실행은 재료가 될 수 없다."""
    save_exported(app_db, document_title="저장된 것")
    run_history.save_run(app_db, make_result(title="저장 안 된 것"))

    app = v1.AppTest.from_function(script).run()

    assert table_titles(app) == ["저장된 것"]


def test_saved_runs_older_than_the_recent_fifty_are_listed(
    app_db, outline_env
) -> None:
    """최근 실행 50건 밖으로 밀려난 요약본도 재료로 나온다.

    최근 실행 목록은 저장 여부와 상관없이 50건에서 끊긴다. 그
    목록에서 저장된 것만 추리면, 미저장 실행이 쌓인 뒤로는 옛
    요약본이 재료 후보에서 사라진다.
    """
    save_exported(app_db, document_title="오래된 요약본")
    for _ in range(50):
        run_history.save_run(app_db, make_result(title="미저장"))

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert table_titles(app) == ["오래된 요약본"]


def test_table_shows_the_channel_and_upload_date(app_db, outline_env) -> None:
    """저장한 요약본의 채널·업로드일이 표에 나온다."""
    save_exported(
        app_db,
        metadata=models.VideoMetadata(
            channel="어떤 채널", upload_date="2026-09-20"
        ),
    )

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    table = app.dataframe[0].value
    assert list(table["channel"]) == ["어떤 채널"]
    assert list(table["upload_date"]) == ["2026-09-20"]


def test_table_leaves_missing_metadata_blank(app_db, outline_env) -> None:
    """메타데이터가 없는 요약본은 두 칸이 빈다."""
    save_exported(app_db)

    app = v1.AppTest.from_function(script).run()

    table = app.dataframe[0].value
    assert table["channel"].isna().all()
    assert table["upload_date"].isna().all()
    assert app.dataframe[0].proto.HasField("placeholder")
    assert app.dataframe[0].proto.placeholder == ""


def test_table_columns_come_in_order(app_db, outline_env) -> None:
    """고르는 기준이 제목 다음에 오고 시각은 뒤로 간다."""
    save_exported(app_db)

    app = v1.AppTest.from_function(script).run()

    assert list(app.dataframe[0].value.columns) == [
        "title",
        "channel",
        "upload_date",
        "created_at",
        "url",
    ]


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
    select_rows(app, app_db, [0])
    app.run()

    assert app.button[0].disabled is False


def test_picked_materials_are_listed_under_the_table(
    app_db, outline_env
) -> None:
    """고른 재료의 제목과 개수를 표 아래에서 다시 확인할 수 있다."""
    save_exported(app_db, document_title="먼저 저장", document_id="doc-1")
    save_exported(app_db, document_title="나중 저장", document_id="doc-2")
    add_instruction(app_db)

    app = v1.AppTest.from_function(script).run()
    select_rows(app, app_db, [1])
    app.run()

    rendered = " ".join(element.value for element in app.markdown)
    assert "먼저 저장" in rendered
    assert "나중 저장" not in rendered
    assert f"1/{nlm.DIGEST_SOURCE_LIMIT}" in rendered


def test_running_query_blocks_the_start(app_db, outline_env) -> None:
    """질의가 돌고 있으면 정리를 시작할 수 없다."""
    from notebooklm_st import session

    save_exported(app_db)
    add_instruction(app_db)
    question = models.Question(
        id=1, title="질문", text="질문?", created_at="", updated_at=""
    )
    registry = session.get_registry()
    registry.enqueue("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", (question,))
    registry.acquire_worker()
    registry.claim_next()

    app = v1.AppTest.from_function(script).run()
    select_rows(app, app_db, [0])
    app.run()

    assert app.button[0].disabled is True
    assert any("질의" in element.value for element in app.info)


def test_start_hands_the_selection_to_the_runner(
    app_db, outline_env, monkeypatch
) -> None:
    """시작을 누르면 표에서 고른 행의 실행이 러너로 넘어간다."""
    from notebooklm_st.pages import digest as digest_page

    save_exported(app_db, document_title="먼저 저장", document_id="doc-1")
    save_exported(app_db, document_title="나중 저장", document_id="doc-2")
    add_instruction(app_db)
    received: dict[str, object] = {}

    def fake_start(registry, config, summaries, instruction, **kwargs):
        """넘어온 인자를 기록한다."""
        received["summaries"] = list(summaries)
        received["instruction"] = instruction
        return True

    monkeypatch.setattr(digest_page.digest_runner, "start_digest", fake_start)

    app = v1.AppTest.from_function(script).run()
    # 표는 새 것부터다. 1행은 먼저 저장한 doc-1 이다.
    click_start(app, app_db, [1])

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
    app.selectbox[0].select(second).run()
    click_start(app, app_db, [0])

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
    select_rows(app, app_db, list(range(nlm.DIGEST_SOURCE_LIMIT + 1)))
    app.run()

    assert app.button[0].disabled is True
    assert len(app.warning) == 1


def summary(run_id: int) -> models.RunSummary:
    """재료 표에 오를 저장된 실행 요약 하나를 만든다."""
    return models.RunSummary(
        id=run_id,
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        title="영상 제목",
        created_at="2026-09-20T14:02:11",
        answer_count=0,
        outline_id=f"doc-{run_id}",
        outline_url=f"{BASE_URL}/doc/doc-{run_id}",
        outline_title=f"강의 {run_id}",
        exported_at="2026-09-20T15:00:00",
    )


def test_table_key_is_stable_for_the_same_materials() -> None:
    """재료가 그대로면 표의 key 도 그대로다.

    행을 누를 때마다 화면이 다시 그려진다. 그때 key 가 바뀌면
    Streamlit 이 새 표로 보고 방금 고른 선택을 비운다.
    """
    from notebooklm_st.pages import _digest_materials

    first = _digest_materials.widget_key([summary(2), summary(1)])
    second = _digest_materials.widget_key([summary(2), summary(1)])

    assert first == second


def test_table_key_changes_when_the_materials_change() -> None:
    """재료 목록이 바뀌면 표의 key 가 달라진다.

    선택은 행 번호로 돌아온다. key 가 같은 채로 맨 위에 새 재료가
    끼면 고른 번호가 한 칸 밀린 다른 글을 가리킨다. key 가 바뀌면
    Streamlit 이 새 표로 보고 선택을 비운다.
    """
    from notebooklm_st.pages import _digest_materials

    before = _digest_materials.widget_key([summary(2), summary(1)])
    after = _digest_materials.widget_key([summary(3), summary(2), summary(1)])

    assert before != after


def test_table_key_ignores_the_metadata() -> None:
    """메타데이터만 바뀌면 표의 key 는 그대로다.

    다른 탭에서 동기화로 채널·업로드일이 채워져도 고른 재료가 비워지면
    안 된다.
    """
    from notebooklm_st.pages import _digest_materials

    filled = dataclasses.replace(
        summary(1),
        metadata=models.VideoMetadata(
            channel="어떤 채널", upload_date="2026-09-20"
        ),
    )

    assert _digest_materials.widget_key([summary(1)]) == (
        _digest_materials.widget_key([filled])
    )


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
