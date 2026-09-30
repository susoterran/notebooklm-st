"""질의 화면 — 질의를 대기열에 넣는 입구."""

import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import youtube
from notebooklm_st.services import (
    outline,
    questions,
    run_registry,
    runner,
    runs,
    settings,
    store,
)

_URL_KEY = "ask_url"
_SELECTED_KEY = "ask_selected"
_AUTO_SAVE_KEY = "ask_auto_save"
_AUTO_SAVE_LOCKED_KEY = "ask_auto_save_locked"
_ENQUEUED_KEY = "ask_enqueued"

_AUTO_SAVE_HELP = (
    "켜면 답변을 받은 뒤 인용을 빼고 곧바로 Outline 에 올립니다."
    " 제목이 없거나 답변 일부가 실패하면 올리지 않고 이력에 미저장으로"
    " 남깁니다."
)
"""자동 저장 체크의 도움말."""


def render() -> None:
    """URL 입력, 질문 선택, 자동 저장 여부, 대기열에 넣기를 그린다.

    실행은 백그라운드 워커가 넣은 순서대로 맡는다. 이 화면은 넣기만
    하고 즉시 반환하므로, 앞 실행을 기다리지 않고 다음 영상을 넣을 수
    있다. 진행 상황과 답변은 실행 현황 화면에서 본다.
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

    duplicate = _render_queue_notices(
        registry, youtube.extract_video_id(url) if url_ok else None
    )
    st.button(
        "실행",
        key="ask_run",
        disabled=duplicate or not (url_ok and selected),
        on_click=_enqueue,
        args=(registry, auto_save),
    )
    enqueued = st.session_state.pop(_ENQUEUED_KEY, None)
    if enqueued is not None:
        st.success(enqueued)


def _render_queue_notices(
    registry: run_registry.RunRegistry, video_id: str | None
) -> bool:
    """넣으면 언제 돌지 알리고, 같은 영상이 이미 들어 있는지 본다.

    Args:
        registry: 실행 레지스트리.
        video_id: 입력한 URL 의 영상 ID. URL 이 틀렸으면 ``None``.

    Returns:
        그 영상이 이미 대기 중이거나 실행 중이면 참. 버튼을 잠근다.
    """
    ahead = _count_ahead(registry)
    if ahead > 0:
        st.info(
            f"실행 중이거나 대기 중인 질의가 {ahead}건 있습니다."
            " 넣으면 그 뒤에 실행됩니다."
        )
    if session.get_digest_registry().is_running():
        st.info(
            "정리본을 작성 중입니다. 넣은 질의는 정리본이 끝난 뒤 시작합니다."
        )
    if registry.paused_reason() is not None:
        st.warning(
            "대기열이 멈춰 있습니다. 넣은 질의는 실행 현황에서 재개할"
            " 때까지 기다립니다."
        )
    duplicate = video_id is not None and registry.is_pending(video_id)
    if duplicate:
        st.info("이 영상은 이미 대기 중이거나 실행 중입니다.")
    return duplicate


def _enqueue(registry: run_registry.RunRegistry, auto_save: bool) -> None:
    """입력한 영상을 대기열에 넣고 URL 칸을 비운다.

    실행 버튼의 ``on_click`` 콜백이다. 콜백은 재실행 전에 돌므로 URL
    위젯의 키를 바꿔도 예외가 없다. URL·질문은 버튼을 그릴 때가 아니라
    누른 순간의 세션 값을 읽는다. 질문 선택은 남겨 다음 영상을 바로
    붙여 넣게 한다. 결과 문구는 세션에 적어 다음 그림에서 한 번
    보인다.

    Args:
        registry: 실행 레지스트리.
        auto_save: 화면에 보이는 자동 저장 값.
    """
    url = st.session_state.get(_URL_KEY, "")
    selected = st.session_state.get(_SELECTED_KEY, [])
    video_id = youtube.extract_video_id(url)
    if video_id is None or not selected or registry.is_pending(video_id):
        return
    ahead = _count_ahead(registry)
    paused = registry.paused_reason() is not None
    digests = session.get_digest_registry()
    digesting = digests.is_running()
    runner.enqueue(
        registry,
        url,
        selected,
        store.default_db_path(),
        auto_save=auto_save,
        is_blocked=digests.is_running,
    )
    st.session_state[_URL_KEY] = ""
    st.session_state[_ENQUEUED_KEY] = _enqueued_text(ahead, paused, digesting)


def _count_ahead(registry: run_registry.RunRegistry) -> int:
    """지금 넣으면 앞에 설 질의 수. 멈춤과 상관없이 센다."""
    return sum(
        1 for handle in registry.list_all() if handle.status in runs.PENDING
    )


def _enqueued_text(ahead: int, paused: bool, digesting: bool) -> str:
    """넣은 뒤 보일 문구. 위에서부터 처음 맞는 것을 쓴다.

    Args:
        ahead: 넣기 직전에 센 앞선 질의 수.
        paused: 대기열이 멈춰 있었는가.
        digesting: 정리본을 작성 중이었는가.

    Returns:
        화면에 한 번 보일 문구.
    """
    if paused:
        return (
            "대기열에 넣었습니다. 대기열이 멈춰 있어 재개할 때까지 기다립니다."
        )
    if ahead > 0:
        return (
            f"대기열에 넣었습니다 — 앞에 {ahead}건. 실행 현황 화면에서"
            " 확인하세요."
        )
    if digesting:
        return "대기열에 넣었습니다. 정리본이 끝나면 시작합니다."
    return "실행을 시작했습니다. 실행 현황 화면에서 확인하세요."


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
