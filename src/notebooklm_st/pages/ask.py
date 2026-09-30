"""질의 화면 — 백그라운드 실행을 시작하는 트리거."""

import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import youtube
from notebooklm_st.services import outline, questions, runner, settings, store

_URL_KEY = "ask_url"
_SELECTED_KEY = "ask_selected"
_AUTO_SAVE_KEY = "ask_auto_save"
_AUTO_SAVE_LOCKED_KEY = "ask_auto_save_locked"

_AUTO_SAVE_HELP = (
    "켜면 답변을 받은 뒤 인용을 빼고 곧바로 Outline 에 올립니다."
    " 제목이 없거나 답변 일부가 실패하면 올리지 않고 이력에 미저장으로"
    " 남깁니다."
)
"""자동 저장 체크의 도움말."""


def render() -> None:
    """URL 입력, 질문 선택, 자동 저장 여부, 실행 시작을 그린다.

    실행은 백그라운드 스레드가 맡는다. 이 화면은 시작만 하고 즉시
    반환하므로 페이지를 이동해도 작업이 중단되지 않는다. 진행 상황과
    답변은 실행 현황 화면에서 본다.
    """
    st.title("영상 질의")
    connection = session.get_connection()
    registry = session.get_registry()
    question_list = questions.list_questions(connection)

    url = st.text_input(
        "YouTube 영상 URL",
        key=_URL_KEY,
        placeholder="https://www.youtube.com/watch?v=...",
    )
    url_ok = youtube.is_valid(url)
    if url and not url_ok:
        st.error("단일 YouTube 영상 URL 이 아닙니다.")

    if not question_list:
        st.info("질문 관리 화면에서 질문을 먼저 등록하세요.")
        return

    selected = st.multiselect(
        "질문 선택",
        options=question_list,
        format_func=lambda question: question.title,
        key=_SELECTED_KEY,
    )
    auto_save = _render_auto_save(connection)

    busy = registry.running_count() > 0
    if busy:
        st.info(
            "이미 실행 중인 작업이 있습니다. 실행 현황 화면에서 확인하세요."
        )
    digesting = session.get_digest_registry().is_running()
    if digesting:
        st.info(
            "정리본을 작성 중입니다. 둘이 같은 자격증명으로 NotebookLM"
            " 을 동시에 쓰지 않도록 막았습니다. 정리본 화면에서 완료를"
            " 확인하세요."
        )

    if st.button(
        "실행",
        key="ask_run",
        disabled=busy or digesting or not (url_ok and selected),
    ):
        runner.enqueue(
            registry,
            url,
            selected,
            store.default_db_path(),
            auto_save=auto_save,
            is_blocked=session.get_digest_registry().is_running,
        )
        st.success("실행을 시작했습니다. 실행 현황 화면에서 확인하세요.")


def _render_auto_save(connection: sqlite3.Connection) -> bool:
    """자동 저장 체크를 그리고, 넣을 실행에 줄 값을 돌려준다.

    값은 DB 에 기억한다. 재시작하거나 다른 기기에서 열어도 켜 둔
    그대로여야 한다. 세션에 키가 없을 때만 DB 값으로 채우고, 사람이
    바꿀 때만 콜백이 DB 에 적는다. 다른 화면에 다녀오면 위젯 값이
    버려지므로 DB 값으로 다시 시작한다.

    key 없는 체크에 DB 값을 초기값으로 주는 방식은 쓰지 않는다. DB 에
    적는 순간 위젯 ID 가 바뀌어 바로 다음 조작이 버려진다.

    Args:
        connection: 열린 커넥션.

    Returns:
        화면에 보이는 값. Outline 설정이 없으면 거짓.
    """
    if outline.config_from_env() is None:
        # 켜 둔 값을 잠긴 채 보이지 않도록 다른 위젯으로 그린다. DB
        # 값은 건드리지 않는다. 설정을 되살리면 켜 둔 값이 돌아온다.
        st.checkbox(
            "자동 저장",
            value=False,
            key=_AUTO_SAVE_LOCKED_KEY,
            disabled=True,
            help=_AUTO_SAVE_HELP,
        )
        st.caption("Outline 연결이 설정되지 않아 자동 저장을 쓸 수 없습니다.")
        return False
    if _AUTO_SAVE_KEY not in st.session_state:
        st.session_state[_AUTO_SAVE_KEY] = settings.auto_save(connection)
    return st.checkbox(
        "자동 저장",
        key=_AUTO_SAVE_KEY,
        help=_AUTO_SAVE_HELP,
        on_change=_remember_auto_save,
        args=(connection,),
    )


def _remember_auto_save(connection: sqlite3.Connection) -> None:
    """사람이 바꾼 자동 저장 값을 DB 에 적는다.

    체크의 ``on_change`` 콜백이다. 사람이 바꿀 때만 쓰므로 다른
    기기에서 바꾼 값을 이 화면이 되덮지 않는다.

    Args:
        connection: 열린 커넥션.
    """
    settings.set_auto_save(connection, st.session_state[_AUTO_SAVE_KEY])
