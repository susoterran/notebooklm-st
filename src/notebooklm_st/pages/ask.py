"""질의 화면 — 질의를 대기열에 넣는 입구."""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import auto_save_toggle, queue_notice
from notebooklm_st.core import youtube
from notebooklm_st.services import questions, run_registry, runner, store

_URL_KEY = "ask_url"
_SELECTED_KEY = "ask_selected"
_AUTO_SAVE_KEY = "ask_auto_save"
_AUTO_SAVE_LOCKED_KEY = "ask_auto_save_locked"
_ENQUEUED_KEY = "ask_enqueued"


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
    auto_save = auto_save_toggle.render(
        connection, _AUTO_SAVE_KEY, _AUTO_SAVE_LOCKED_KEY
    )

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
    queue_notice.render(registry)
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
    ahead = queue_notice.count_ahead(registry)
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
    st.session_state[_ENQUEUED_KEY] = queue_notice.enqueued_text(
        added=1, skipped=0, ahead=ahead, paused=paused, digesting=digesting
    )
