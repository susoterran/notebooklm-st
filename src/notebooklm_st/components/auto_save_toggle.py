"""자동 저장 체크 — 질의 화면과 채널 화면이 같은 설정을 쓴다.

값은 DB 에 하나만 기억한다(``services.settings``). 위젯 key 는
화면마다 따로 받는다. 같은 key 를 두 화면에 쓰면 위젯 상태가
부딪친다.
"""

import sqlite3

import streamlit as st

from notebooklm_st.services import outline, settings

HELP = (
    "켜면 답변을 받은 뒤 인용을 빼고 곧바로 Outline 에 올립니다."
    " 제목이 없거나 답변 일부가 실패하면 올리지 않고 이력에 미저장으로"
    " 남깁니다."
)
"""자동 저장 체크의 도움말."""


def render(connection: sqlite3.Connection, key: str, locked_key: str) -> bool:
    """자동 저장 체크를 그리고, 넣을 실행에 줄 값을 돌려준다.

    값은 DB 에 기억한다. 재시작하거나 다른 기기에서 열어도 켜 둔
    그대로여야 한다. 세션에 키가 없을 때만 DB 값으로 채우고, 사람이
    바꿀 때만 콜백이 DB 에 적는다. 다른 화면에 다녀오면 위젯 값이
    버려지므로 DB 값으로 다시 시작한다.

    key 없는 체크에 DB 값을 초기값으로 주는 방식은 쓰지 않는다. DB 에
    적는 순간 위젯 ID 가 바뀌어 바로 다음 조작이 버려진다.

    Args:
        connection: 열린 커넥션.
        key: 체크의 위젯 key. 화면마다 다르게 준다.
        locked_key: Outline 설정이 없을 때 그리는 잠긴 체크의 key.

    Returns:
        화면에 보이는 값. Outline 설정이 없으면 거짓.
    """
    if outline.config_from_env() is None:
        # 켜 둔 값을 잠긴 채 보이지 않도록 다른 위젯으로 그린다. DB
        # 값은 건드리지 않는다. 설정을 되살리면 켜 둔 값이 돌아온다.
        st.checkbox(
            "자동 저장",
            value=False,
            key=locked_key,
            disabled=True,
            help=HELP,
        )
        st.caption("Outline 연결이 설정되지 않아 자동 저장을 쓸 수 없습니다.")
        return False
    if key not in st.session_state:
        st.session_state[key] = settings.auto_save(connection)
    return st.checkbox(
        "자동 저장",
        key=key,
        help=HELP,
        on_change=_remember,
        args=(connection, key),
    )


def _remember(connection: sqlite3.Connection, key: str) -> None:
    """사람이 바꾼 자동 저장 값을 DB 에 적는다.

    체크의 ``on_change`` 콜백이다. 사람이 바꿀 때만 쓰므로 다른
    기기에서 바꾼 값을 이 화면이 되덮지 않는다.

    Args:
        connection: 열린 커넥션.
        key: 바뀐 체크의 위젯 key.
    """
    settings.set_auto_save(connection, st.session_state[key])
