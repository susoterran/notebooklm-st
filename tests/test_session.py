"""공유 자원 접근자 테스트."""

from streamlit.testing import v1


def test_registry_is_shared_across_sessions(app_db) -> None:
    """서로 다른 세션이 같은 레지스트리 인스턴스를 본다."""

    def script():
        """AppTest 진입점 — 레지스트리에 실행을 하나 등록한다."""
        import streamlit as st

        from notebooklm_st import session

        registry = session.get_registry()
        registry.create("https://youtu.be/x", "x", ("질문",))
        st.write(f"count={len(registry.list_all())}")

    first = v1.AppTest.from_function(script).run()
    second = v1.AppTest.from_function(script).run()

    assert not first.exception
    assert not second.exception
    assert [element.value for element in first.markdown] == ["count=1"]
    assert [element.value for element in second.markdown] == ["count=2"]


def test_registry_cache_is_cleared_between_tests(app_db) -> None:
    """Fixture 가 캐시를 비우므로 앞선 테스트의 실행이 남지 않는다."""

    def script():
        """AppTest 진입점 — 레지스트리 크기를 보고한다."""
        import streamlit as st

        from notebooklm_st import session

        st.write(f"count={len(session.get_registry().list_all())}")

    app = v1.AppTest.from_function(script).run()
    assert [element.value for element in app.markdown] == ["count=0"]
