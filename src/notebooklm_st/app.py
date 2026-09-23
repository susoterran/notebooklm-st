"""Streamlit 진입점.

실행 경로가 둘이다.

데스크톱 — ``uv run streamlit run src/notebooklm_st/app.py``.
``.streamlit/config.toml`` 이 서버를 ``127.0.0.1:8611`` 에만
바인딩하므로 같은 네트워크의 다른 기기에서는 접속할 수 없다.
기본 포트 8501 을 쓰지 않는 것은 다른 Streamlit 프로젝트와
충돌하지 않게 하기 위해서다.

컨테이너 — ``docker compose up -d``. 이미지에는
``.streamlit/config.toml`` 이 들어가지 않는다. 주소와 포트는
이미지의 환경 변수가 정하고(``0.0.0.0:8611``), 홈 LAN 에 열리는
포트는 ``docker-compose.yml`` 의 ``9004`` 다. 절차는
docs/how-to/2026-09-16-homeserver-deploy.md 에 있다.
"""

import streamlit as st

from notebooklm_st.components import auth_gate, schema_gate
from notebooklm_st.pages import (
    ask,
    channels,
    dashboard,
    digest,
    history,
    maintenance,
    question_admin,
)


def main() -> None:
    """인증을 확인하고, 페이지를 등록해 선택된 페이지를 실행한다.

    인증이 안 돼도 페이지는 그대로 띄운다. 질문 관리와 이력은 로컬 DB
    만 쓰므로 인증 없이도 쓸 수 있다.

    DB 스키마부터 확인한다. 어긋난 채로 페이지를 등록하면 어느 화면을
    열든 커넥션을 여는 순간 트레이스백이 노출된다.
    """
    st.set_page_config(page_title="YouTube 질의응답", layout="wide")
    schema_gate.render()
    navigation = st.navigation(
        [
            st.Page(ask.render, title="질의", url_path="ask", default=True),
            st.Page(channels.render, title="채널", url_path="channels"),
            st.Page(dashboard.render, title="실행 현황", url_path="dashboard"),
            st.Page(
                question_admin.render,
                title="질문 관리",
                url_path="questions",
            ),
            st.Page(history.render, title="이력", url_path="history"),
            st.Page(digest.render, title="정리본", url_path="digest"),
            st.Page(maintenance.render, title="정리", url_path="maintenance"),
        ]
    )
    auth_gate.render()
    navigation.run()


main()
