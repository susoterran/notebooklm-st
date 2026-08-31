"""이력 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st.core import models, youtube
from notebooklm_st.services import run_history


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
    assert app.text_area[0].value == "세 가지다."
    rendered = " ".join(element.value for element in app.markdown)
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


def test_hiding_citations_strips_markers_and_the_tail(app_db) -> None:
    """체크박스를 켜면 인용 번호와 후속 제안이 사라진다."""
    run_history.save_run(app_db, make_result(answer=ANSWER_WITH_CITATIONS))

    app = v1.AppTest.from_function(script)
    app.run()
    app.checkbox[0].check().run()

    assert not app.exception
    rendered = " ".join(element.value for element in app.markdown)
    assert "[1]" not in rendered
    assert "제안 문단" not in rendered
    assert "근거 구절" not in rendered


def test_hiding_citations_keeps_the_question_expander(app_db) -> None:
    """숨겨도 질문 원문은 남는다. 인용이 아니라 기록이다."""
    run_history.save_run(app_db, make_result(answer=ANSWER_WITH_CITATIONS))

    app = v1.AppTest.from_function(script)
    app.run()
    app.checkbox[0].check().run()

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


def test_answer_is_editable_when_citations_are_shown(app_db) -> None:
    """기본 상태에서는 답변을 고칠 수 있다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.text_area) == 1


def test_editing_saves_the_new_body(app_db) -> None:
    """고친 본문이 이력에 저장된다."""
    run_id = run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_area[0].set_value("고친 답변").run()
    app.button(key="answer_save_1").click().run()

    assert not app.exception
    items = run_history.load_run_items(app_db, run_id)
    assert items[0].answer == "고친 답변"


def test_editing_rejects_an_empty_body(app_db) -> None:
    """빈 본문으로 저장하면 오류를 보여 주고 원본을 지킨다."""
    run_id = run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_area[0].set_value("   ").run()
    app.button(key="answer_save_1").click().run()

    assert not app.exception
    assert len(app.error) == 1
    items = run_history.load_run_items(app_db, run_id)
    assert items[0].answer == "세 가지다."


def test_hiding_citations_locks_editing(app_db) -> None:
    """인용을 숨기는 동안에는 편집 상자를 그리지 않는다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.checkbox[0].check().run()

    assert not app.exception
    assert len(app.text_area) == 0
