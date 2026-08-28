"""진입점 조립 테스트."""

from streamlit.testing import v1


def test_app_boots_with_all_pages(app_db) -> None:
    """다섯 페이지가 등록된 진입점이 예외 없이 부팅된다."""
    app = v1.AppTest.from_file("../src/notebooklm_st/app.py").run()
    assert not app.exception
