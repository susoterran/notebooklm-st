"""Streamlit 진입점.

실행:
    uv run streamlit run src/notebooklm_st/app.py

``.streamlit/config.toml`` 이 서버를 ``127.0.0.1`` 에만 바인딩하므로
같은 네트워크의 다른 기기에서는 접속할 수 없다.
"""

import streamlit as st

from notebooklm_st.pages import (
    ask,
    dashboard,
    history,
    maintenance,
    question_admin,
)


def main() -> None:
    """페이지를 등록하고 선택된 페이지를 실행한다."""
    st.set_page_config(page_title="YouTube 질의응답", layout="wide")
    navigation = st.navigation(
        [
            st.Page(ask.render, title="질의", url_path="ask", default=True),
            st.Page(dashboard.render, title="실행 현황", url_path="dashboard"),
            st.Page(
                question_admin.render,
                title="질문 관리",
                url_path="questions",
            ),
            st.Page(history.render, title="이력", url_path="history"),
            st.Page(maintenance.render, title="정리", url_path="maintenance"),
        ]
    )
    navigation.run()


main()
