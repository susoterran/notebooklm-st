"""카테고리 관리 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st import session
from notebooklm_st.core import models
from notebooklm_st.services import categories, channels, run_history


def script():
    """AppTest 진입점 — 카테고리 관리 화면을 렌더한다."""
    from notebooklm_st.pages import category_admin

    category_admin.render()


def names(connection) -> list[str]:
    """등록된 이름을 목록 순서로."""
    return [item.name for item in categories.list_categories(connection)]


def captions(app) -> list[str]:
    """화면의 캡션 글자들."""
    return [item.value for item in app.caption]


def used_by_a_run(connection, category_id: int) -> None:
    """그 카테고리를 단 이력 하나를 남긴다."""
    run_history.save_run(
        connection,
        models.RunResult(
            url="https://youtu.be/dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
            items=(),
        ),
        category_ids=[category_id],
    )


def test_adding_a_category_lists_it(app_db) -> None:
    """이름을 넣고 등록하면 저장되고 목록에 나온다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input(key="category_new_name").set_value("경제").run()
    app.button(key="category_add").click().run()

    assert not app.exception
    assert names(app_db) == ["경제"]
    assert [item.label for item in app.expander] == ["경제"]


def test_a_duplicate_name_shows_the_reason(app_db) -> None:
    """같은 이름이면 오류를 보이고 저장하지 않는다."""
    categories.add_category(app_db, "경제")
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input(key="category_new_name").set_value("경제").run()
    app.button(key="category_add").click().run()

    assert any("이미 있습니다" in item.value for item in app.error)
    assert names(app_db) == ["경제"]


def test_an_invalid_name_shows_the_reason(app_db) -> None:
    """규칙에 맞지 않는 이름이면 쓸 수 있는 글자를 알린다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input(key="category_new_name").set_value("경제,정치").run()
    app.button(key="category_add").click().run()

    assert any("쓸 수 있습니다" in item.value for item in app.error)
    assert names(app_db) == []


def test_renaming_a_category(app_db) -> None:
    """이름 칸을 고치고 수정을 누르면 이름이 바뀐다."""
    category = categories.add_category(app_db, "경제")
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input(key=f"category_name_{category.id}").set_value(
        "거시경제"
    ).run()
    app.button(key=f"category_rename_{category.id}").click().run()

    assert not app.exception
    assert names(app_db) == ["거시경제"]


def test_deleting_a_category(app_db) -> None:
    """삭제를 누르면 지워진다."""
    category = categories.add_category(app_db, "경제")
    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key=f"category_delete_{category.id}").click().run()

    assert not app.exception
    assert names(app_db) == []


def test_an_unused_category_says_so(app_db) -> None:
    """쓰는 곳이 없으면 그렇다고 적고 잠그지 않는다."""
    category = categories.add_category(app_db, "경제")
    app = v1.AppTest.from_function(script).run()

    assert "아직 쓰는 곳이 없습니다." in captions(app)
    assert app.button(key=f"category_delete_{category.id}").disabled is False


def test_a_category_used_by_a_run_is_locked(app_db) -> None:
    """이력에서 쓰는 카테고리는 칸과 버튼이 잠기고 이유가 보인다."""
    category = categories.add_category(app_db, "경제")
    used_by_a_run(app_db, category.id)
    app = v1.AppTest.from_function(script).run()

    assert app.text_input(key=f"category_name_{category.id}").disabled
    assert app.button(key=f"category_rename_{category.id}").disabled
    assert app.button(key=f"category_delete_{category.id}").disabled
    assert "이력 1건" in captions(app)
    assert any("이력에서 쓰는 카테고리라" in text for text in captions(app))


def test_a_category_held_by_a_queued_run_is_locked(app_db) -> None:
    """대기 중인 질의가 쥔 카테고리도 잠긴다. 아직 이력은 없다."""
    category = categories.add_category(app_db, "경제")
    session.get_registry().enqueue(
        "https://youtu.be/dQw4w9WgXcQ",
        "dQw4w9WgXcQ",
        (),
        category_ids=(category.id,),
    )
    app = v1.AppTest.from_function(script).run()

    assert app.button(key=f"category_delete_{category.id}").disabled
    assert any("대기 중이거나 실행 중인 질의" in text for text in captions(app))


def test_a_channel_default_only_warns_before_deleting(app_db) -> None:
    """채널 기본값으로만 쓰이면 경고하고 지울 수 있게 둔다."""
    category = categories.add_category(app_db, "경제")
    channel = channels.add_channel(
        app_db,
        "UC" + "a" * 22,
        "채널",
        "https://www.youtube.com/@channel",
        "2026-09-01",
    )
    app_db.execute(
        "INSERT INTO channel_categories (channel_pk, category_id)"
        " VALUES (?, ?)",
        (channel.id, category.id),
    )
    app_db.commit()
    app = v1.AppTest.from_function(script)
    app.run()

    assert "채널 1개의 기본 카테고리" in captions(app)
    assert "지우면 채널 1개의 기본 카테고리에서도 빠집니다." in captions(app)
    app.button(key=f"category_delete_{category.id}").click().run()
    assert names(app_db) == []
