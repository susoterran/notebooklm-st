"""Streamlit 진입점.

실행:
    uv run streamlit run src/notebooklm_st/app.py
"""

import streamlit as st

from notebooklm_st.pages import ask, question_admin


def main() -> None:
    """페이지를 등록하고 선택된 페이지를 실행한다."""
    st.set_page_config(page_title="YouTube 질의응답", layout="wide")
    navigation = st.navigation(
        [
            st.Page(ask.render, title="질의", default=True),
            st.Page(question_admin.render, title="질문 관리"),
        ]
    )
    navigation.run()


main()
