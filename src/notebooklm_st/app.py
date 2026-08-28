"""Streamlit 진입점.

실행:
    uv run streamlit run src/notebooklm_st/app.py

``.streamlit/config.toml`` 이 서버를 ``127.0.0.1:8611`` 에만
바인딩하므로 같은 네트워크의 다른 기기에서는 접속할 수 없다.
기본 포트 8501 을 쓰지 않는 것은 다른 Streamlit 프로젝트와
충돌하지 않게 하기 위해서다.
"""

import streamlit as st

from notebooklm_st.components import auth_gate
from notebooklm_st.pages import (
    ask,
    dashboard,
    history,
    maintenance,
    question_admin,
)


def main() -> None:
    """인증을 확인하고, 페이지를 등록해 선택된 페이지를 실행한다.

    인증이 안 돼도 페이지는 그대로 띄운다. 질문 관리와 이력은 로컬 DB
    만 쓰므로 인증 없이도 쓸 수 있다.
    """
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
    auth_gate.render()
    navigation.run()


main()
