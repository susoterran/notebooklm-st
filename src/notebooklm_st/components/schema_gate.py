"""DB 스키마가 코드와 맞는지 확인하는 조각.

앱이 뜰 때 가장 먼저 돈다. 스키마가 어긋나면 아래에서 어떤 화면을
그리든 커넥션을 여는 순간 예외가 터지므로, 여기서 한 번 잡아 사람이
읽을 수 있는 안내로 바꾸고 멈춘다.
"""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.services import store


def render() -> None:
    """커넥션을 한 번 열어 보고, 스키마가 어긋나면 안내 후 멈춘다.

    이 프로젝트는 마이그레이션 경로를 두지 않기로 했으므로(→
    ``services.store``) 사용자가 할 일은 예전 DB 파일을 지우는 것뿐
    이다. 예외 메시지가 이미 파일 경로와 그 안내를 담고 있어 그대로
    보여 준다.
    """
    try:
        session.get_connection()
    except store.StaleSchemaError as error:
        st.error(str(error))
        st.stop()
