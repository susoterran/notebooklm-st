"""이력 화면 테스트."""

import sqlite3

from streamlit.testing import v1

from notebooklm_st.core import models, youtube
from notebooklm_st.services import outline, run_history


def script():
    """AppTest 진입점 — 이력 화면을 렌더한다."""
    from notebooklm_st.pages import history

    history.render()


def make_result(
    url: str = "https://youtu.be/dQw4w9WgXcQ",
    title: str | None = None,
    answer: str = "세 가지다.",
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
                answer=answer,
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


ANSWER_WITH_CITATIONS = "세 가지다 [1].\n\n---\n💡 **다음으로?**\n제안 문단"


def test_citations_are_shown_by_default(app_db) -> None:
    """기본 상태에서는 인용을 그대로 보여 준다."""
    run_history.save_run(app_db, make_result(answer=ANSWER_WITH_CITATIONS))

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    labels = [element.label for element in app.expander]
    assert any(label.startswith("인용") for label in labels)
    rendered = " ".join(element.value for element in app.markdown)
    assert "[1]" in rendered


def test_excluding_citations_strips_markers_and_the_tail(app_db) -> None:
    """체크박스를 끄면 인용 번호와 후속 제안이 사라진다."""
    run_history.save_run(app_db, make_result(answer=ANSWER_WITH_CITATIONS))

    app = v1.AppTest.from_function(script)
    app.run()
    app.checkbox[0].uncheck().run()

    assert not app.exception
    rendered = " ".join(element.value for element in app.markdown)
    assert "[1]" not in rendered
    assert "제안 문단" not in rendered
    assert "근거 구절" not in rendered


def test_excluding_citations_keeps_the_question_expander(app_db) -> None:
    """꺼도 질문 원문은 남는다. 인용이 아니라 기록이다."""
    run_history.save_run(app_db, make_result(answer=ANSWER_WITH_CITATIONS))

    app = v1.AppTest.from_function(script)
    app.run()
    app.checkbox[0].uncheck().run()

    labels = [element.label for element in app.expander]
    assert "질문 원문" in labels
    assert not any(label.startswith("인용") for label in labels)


def test_delete_needs_two_steps(app_db) -> None:
    """첫 번째 누름은 확인만 요청하고 지우지 않는다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[0].click().run()

    assert not app.exception
    assert len(run_history.list_runs(app_db)) == 1


def test_delete_removes_the_run_after_confirming(app_db) -> None:
    """확인 버튼까지 누르면 실제로 지운다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[0].click().run()
    app.button(key="history_delete_confirm").click().run()

    assert not app.exception
    assert run_history.list_runs(app_db) == []
    assert len(app.info) == 1


def test_delete_can_be_cancelled(app_db) -> None:
    """취소하면 아무것도 지우지 않는다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[0].click().run()
    app.button(key="history_delete_cancel").click().run()

    assert not app.exception
    assert len(run_history.list_runs(app_db)) == 1


def test_delete_keeps_the_other_runs(app_db) -> None:
    """고른 실행만 지우고 나머지는 남긴다."""
    run_history.save_run(app_db, make_result("https://youtu.be/aaaaaaaaaaa"))
    run_history.save_run(app_db, make_result("https://youtu.be/bbbbbbbbbbb"))

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[0].click().run()
    app.button(key="history_delete_confirm").click().run()

    assert not app.exception
    remaining = run_history.list_runs(app_db)
    assert [run.url for run in remaining] == ["https://youtu.be/aaaaaaaaaaa"]


def export(app_db, run_id: int) -> None:
    """실행 하나를 저장된 상태로 만든다."""
    run_history.mark_exported(
        app_db,
        run_id,
        document_id="doc-1",
        document_title="정리한 제목",
        document_url="http://192.168.0.10:3000/doc/x",
    )


def test_exported_run_shows_the_document_link(app_db) -> None:
    """저장된 실행은 문서명과 링크만 보여 준다."""
    run_id = run_history.save_run(app_db, make_result(title="밸류에이션 강의"))
    export(app_db, run_id)

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    rendered = " ".join(element.value for element in app.markdown)
    assert "정리한 제목" in rendered
    links = app.get("link_button")
    assert len(links) == 1
    assert links[0].proto.url == "http://192.168.0.10:3000/doc/x"


def test_exported_run_draws_no_answer_cards(app_db) -> None:
    """저장된 실행은 답변 갈래로 넘어가지 않고 일찍 돌아간다.

    ``app.subheader`` 만으로는 이른 반환과 "빈 목록을 그렸을 뿐"을
    구분하지 못한다(``mark_exported`` 가 답변을 지우므로 둘 다 0건).
    "인용 포함" 체크박스는 이른 반환 다음에만 그려지므로, 그것이
    없다는 사실이 반환이 실제로 일어났다는 증거가 된다.
    """
    run_id = run_history.save_run(app_db, make_result())
    export(app_db, run_id)

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.subheader) == 0
    assert len(app.checkbox) == 0


def test_exported_run_label_uses_the_document_title(app_db) -> None:
    """목록에서는 위키에 있는 이름으로 찾는다."""
    run_id = run_history.save_run(app_db, make_result(title="밸류에이션 강의"))
    export(app_db, run_id)

    app = v1.AppTest.from_function(script).run()

    label = app.selectbox[0].options[0]
    assert label.startswith("정리한 제목 · ")
    assert label.endswith(" · 문서")


def test_unexported_run_label_says_so(app_db) -> None:
    """미저장 실행은 그렇게 적어 둔다."""
    run_history.save_run(app_db, make_result(title="밸류에이션 강의"))

    app = v1.AppTest.from_function(script).run()

    assert app.selectbox[0].options[0].endswith(" · 미저장 · 답변 1건")


def test_deleting_an_exported_run_warns_about_the_document(app_db) -> None:
    """지우면 링크만 사라진다는 것을 알려 준다."""
    run_id = run_history.save_run(app_db, make_result())
    export(app_db, run_id)

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[0].click().run()

    assert not app.exception
    assert "Outline 문서는 그대로 남습니다" in app.warning[0].value


def set_outline_env(monkeypatch) -> None:
    """저장 버튼이 나오도록 설정을 채운다."""
    monkeypatch.setenv(outline.URL_ENV_VAR, "http://192.168.0.10:3000")
    monkeypatch.setenv(outline.TOKEN_ENV_VAR, "ol_secret")
    monkeypatch.setenv(outline.COLLECTION_ENV_VAR, "col-1")


def fake_create(calls, document=None):
    """create_document 를 대신해 호출을 기록한다."""

    def create(config, title, markdown, **kwargs):
        """호출 인자를 기록하고 만들어진 문서를 돌려준다."""
        calls.append((config, title, markdown))
        return document or outline.SavedDocument(
            id="doc-1",
            title=title,
            url="http://192.168.0.10:3000/doc/x",
        )

    return create


def test_export_button_is_hidden_without_configuration(app_db) -> None:
    """설정이 없으면 저장 버튼 대신 안내를 낸다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert "history_export_1" not in [element.key for element in app.button]
    messages = " ".join(element.value for element in app.info)
    assert outline.URL_ENV_VAR in messages


def test_export_button_appears_with_configuration(app_db, monkeypatch) -> None:
    """설정이 있으면 제목 입력과 저장 버튼이 나온다."""
    set_outline_env(monkeypatch)
    run_history.save_run(app_db, make_result(title="밸류에이션 강의"))

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert app.text_input[0].value == "밸류에이션 강의"
    assert not app.button(key="history_export_1").disabled


def test_export_title_falls_back_to_the_video_id(app_db, monkeypatch) -> None:
    """저장된 영상 제목이 없으면 영상 ID 를 기본값으로 쓴다."""
    set_outline_env(monkeypatch)
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script).run()

    assert app.text_input[0].value == "dQw4w9WgXcQ"


def test_export_sends_the_confirmed_title_and_body(app_db, monkeypatch) -> None:
    """확인한 제목과 화면에 보이는 본문이 그대로 올라간다."""
    set_outline_env(monkeypatch)
    calls: list[tuple[object, str, str]] = []
    monkeypatch.setattr(outline, "create_document", fake_create(calls))
    run_history.save_run(app_db, make_result(title="밸류에이션 강의"))

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value("사람이 고친 제목").run()
    app.button(key="history_export_1").click().run()

    assert not app.exception
    assert len(calls) == 1
    _, title, markdown = calls[0]
    assert title == "사람이 고친 제목"
    assert 'title: "사람이 고친 제목"' in markdown
    assert "세 가지다." in markdown


def test_export_records_the_link_and_drops_the_body(
    app_db, monkeypatch
) -> None:
    """성공하면 링크가 남고 로컬 본문이 사라진다."""
    set_outline_env(monkeypatch)
    monkeypatch.setattr(outline, "create_document", fake_create([]))
    run_id = run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_export_1").click().run()

    assert not app.exception
    run = run_history.list_runs(app_db)[0]
    assert run.outline_url == "http://192.168.0.10:3000/doc/x"
    assert run_history.load_run_items(app_db, run_id) == []


def test_export_can_leave_the_citations_out(app_db, monkeypatch) -> None:
    """체크박스를 끄면 걸러진 본문이 올라간다."""
    set_outline_env(monkeypatch)
    calls: list[tuple[object, str, str]] = []
    monkeypatch.setattr(outline, "create_document", fake_create(calls))
    run_history.save_run(app_db, make_result(answer=ANSWER_WITH_CITATIONS))

    app = v1.AppTest.from_function(script)
    app.run()
    app.checkbox[0].uncheck().run()
    app.button(key="history_export_1").click().run()

    markdown = calls[0][2]
    assert "[1]" not in markdown
    assert "제안 문단" not in markdown


def test_include_citations_defaults_on_for_each_run(app_db) -> None:
    """체크박스 키가 실행별이라 다른 실행에서는 기본값(켬)으로 돌아온다.

    한 키를 모든 실행이 같이 쓰면, 한 실행에서 꺼 둔 상태가 다른
    실행을 고를 때도 그대로 남는다. 목록 순서는 최신순이라 두 번째로
    저장한 실행이 먼저 선택된다.
    """
    run_history.save_run(
        app_db, make_result(url="https://youtu.be/aaaaaaaaaaa")
    )
    run_history.save_run(
        app_db, make_result(url="https://youtu.be/bbbbbbbbbbb")
    )

    app = v1.AppTest.from_function(script)
    app.run()
    app.checkbox[0].uncheck().run()
    app.selectbox[0].select_index(1).run()

    assert not app.exception
    assert app.checkbox[0].value is True


def test_export_button_is_disabled_with_a_blank_title(
    app_db, monkeypatch
) -> None:
    """제목이 공백뿐이면 저장 버튼을 누를 수 없다."""
    set_outline_env(monkeypatch)
    run_history.save_run(app_db, make_result(title="밸류에이션 강의"))

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value("   ").run()

    assert not app.exception
    assert app.button(key="history_export_1").disabled


def failing_create(message: str):
    """create_document 대신 OutlineError 를 던진다."""

    def create(config, title, markdown, **kwargs):
        """항상 실패한다."""
        raise outline.OutlineError(message)

    return create


def test_export_failure_shows_the_message(app_db, monkeypatch) -> None:
    """실패 사유를 사람이 읽을 수 있게 보여 준다."""
    set_outline_env(monkeypatch)
    monkeypatch.setattr(
        outline,
        "create_document",
        failing_create("Outline 에 연결하지 못했습니다(ConnectError)."),
    )
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_export_1").click().run()

    assert not app.exception
    assert "연결하지 못했습니다" in app.error[0].value


def test_export_failure_keeps_the_local_copy(app_db, monkeypatch) -> None:
    """실패하면 로컬을 손대지 않는다. 고친 뒤 다시 누르면 된다."""
    set_outline_env(monkeypatch)
    monkeypatch.setattr(
        outline, "create_document", failing_create("토큰이 거부되었습니다.")
    )
    run_id = run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_export_1").click().run()

    assert not app.exception
    assert len(run_history.load_run_items(app_db, run_id)) == 1
    assert run_history.list_runs(app_db)[0].exported_at is None


def test_export_reports_a_created_document_it_could_not_record(
    app_db, monkeypatch
) -> None:
    """문서는 만들어졌는데 기록이 실패하면 URL 을 그대로 보여 준다.

    되돌리려면 방금 만든 문서를 지워야 하는데 그 삭제도 실패할 수
    있어 틈이 한 겹 더 생길 뿐이다. 사람이 링크를 들고 판단한다.
    """
    set_outline_env(monkeypatch)
    monkeypatch.setattr(outline, "create_document", fake_create([]))

    def boom(*args, **kwargs):
        """mark_exported 가 실패하는 상황을 만든다."""
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(run_history, "mark_exported", boom)
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_export_1").click().run()

    assert not app.exception
    message = app.error[0].value
    assert "http://192.168.0.10:3000/doc/x" in message
    assert "둘이 됩니다" in message


def test_exporting_an_older_run_redraws_that_same_run(
    app_db, monkeypatch
) -> None:
    """저장한 실행이 링크 한 줄로 그 자리에 다시 그려진다.

    선택이 최신 실행으로 튀면 저장이 실패한 것처럼 보인다. 사람이
    같은 버튼을 다시 누르면 위키에 다른 요약이 하나 더 생기고 그
    본문까지 로컬에서 사라진다.
    """
    set_outline_env(monkeypatch)
    monkeypatch.setattr(outline, "create_document", fake_create([]))
    older = run_history.save_run(
        app_db, make_result(url="https://youtu.be/aaaaaaaaaaa")
    )
    run_history.save_run(
        app_db, make_result(url="https://youtu.be/bbbbbbbbbbb")
    )

    app = v1.AppTest.from_function(script)
    app.run()
    app.selectbox[0].select_index(1).run()
    app.button(key=f"history_export_{older}").click().run()

    assert not app.exception
    assert "Outline 에 저장됨" in app.success[0].value
    links = app.get("link_button")
    assert len(links) == 1
    assert links[0].proto.id.endswith(f"history_open_{older}")


def test_export_does_not_swallow_a_programming_error(
    app_db, monkeypatch
) -> None:
    """기록 단계의 프로그래밍 오류는 감추지 않고 드러낸다.

    넓게 잡으면 리팩터링이 남긴 AttributeError 까지 "문서가 둘이
    됩니다" 라는 안내로 둔갑해, 진짜 버그가 영영 보이지 않는다.
    """
    set_outline_env(monkeypatch)
    monkeypatch.setattr(outline, "create_document", fake_create([]))

    def boom(*args, **kwargs):
        """리팩터링이 남긴 버그를 흉내 낸다."""
        raise AttributeError("no attribute 'mark_exported'")

    monkeypatch.setattr(run_history, "mark_exported", boom)
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_export_1").click().run()

    assert len(app.exception) == 1
    assert "둘이 됩니다" not in " ".join(element.value for element in app.error)
