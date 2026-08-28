"""임시 노트북 정리 화면 테스트."""

from notebooklm import exceptions
from streamlit.testing import v1

from notebooklm_st.core import models
from notebooklm_st.services import nlm


def test_initial_render_asks_for_refresh(app_db) -> None:
    """처음 열면 목록 새로 고침을 안내한다."""

    def script():
        from notebooklm_st.pages import maintenance

        maintenance.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.info) == 1


def test_leftover_notebooks_are_warned_about(app_db) -> None:
    """남은 임시 노트북이 있으면 개수를 경고한다."""

    def script():
        import streamlit as st

        from notebooklm_st.core import models
        from notebooklm_st.pages import maintenance

        st.session_state["maintenance_notebooks"] = [
            models.TempNotebook(id="nb-1", title="tmp-abc12345"),
            models.TempNotebook(id="nb-2", title="tmp-def67890"),
        ]
        maintenance.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.warning) == 1
    assert "2" in app.warning[0].value


def test_clean_state_reports_success(app_db) -> None:
    """남은 임시 노트북이 없으면 성공 문구를 보여준다."""

    def script():
        import streamlit as st

        from notebooklm_st.pages import maintenance

        st.session_state["maintenance_notebooks"] = []
        maintenance.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.success) == 1


def test_load_lists_leftover_notebooks(app_db, monkeypatch) -> None:
    """새로 고침을 누르면 남은 임시 노트북을 세션에 담는다."""

    async def fake_list(**kwargs):
        """임시 노트북 한 개를 돌려주는 가짜."""
        return [models.TempNotebook(id="nb-1", title="tmp-abc12345")]

    monkeypatch.setattr(nlm, "list_temp_notebooks", fake_list)

    def script():
        """AppTest 진입점 — 정리 화면을 렌더한다."""
        from notebooklm_st.pages import maintenance

        maintenance.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[0].click().run()

    assert not app.exception
    assert len(app.warning) == 1


def test_load_shows_error_message_on_failure(app_db, monkeypatch) -> None:
    """조회가 실패하면 사용자 문구로 안내한다."""

    async def fake_list(**kwargs):
        """항상 인증 만료 예외를 던지는 가짜."""
        raise exceptions.AuthError("expired")

    monkeypatch.setattr(nlm, "list_temp_notebooks", fake_list)

    def script():
        """AppTest 진입점 — 정리 화면을 렌더한다."""
        from notebooklm_st.pages import maintenance

        maintenance.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[0].click().run()

    assert not app.exception
    assert len(app.error) == 1
