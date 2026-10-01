"""채널 화면의 넣기 — 표에서 고른 신규 영상을 질의 대기열에 넣는다.

``pages/_channel_check.py`` 가 이 모듈을 부른다. 네비게이션에 직접
등록되지 않으므로 이름 앞에 밑줄을 둔다.

넣기는 버튼의 ``on_click`` 콜백이 한다. 콜백은 재실행 전에 돌므로,
넣기 횟수를 올리면 다음 그림의 표가 새 key 로 그려져 선택이
비워진다(``pages/_channel_videos.widget_key``).
"""

import dataclasses

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import queue_notice
from notebooklm_st.core import models, youtube
from notebooklm_st.pages import _channel_videos
from notebooklm_st.services import run_registry, runner, store

_GENERATION_KEY = "channels_generation"
_ENQUEUED_KEY = "channels_enqueued"

_ALL_PENDING = "고른 영상은 모두 이미 대기 중이거나 실행 중입니다."


@dataclasses.dataclass(frozen=True, slots=True)
class _Enqueued:
    """넣은 뒤 한 번 보일 결과. 세션에 담는 화면 전용 값이다."""

    text: str
    added: bool
    """하나라도 넣었는가. 거짓이면 성공이 아니라 안내로 보인다."""


def generation() -> int:
    """이 화면에서 넣기를 한 횟수. 표의 key 에 섞는다."""
    count: int = st.session_state.get(_GENERATION_KEY, 0)
    return count


def render(
    registry: run_registry.RunRegistry,
    entries: tuple[models.FeedEntry, ...],
    table_key: str,
    questions_key: str,
    selected: list[models.FeedEntry],
    chosen: list[models.Question],
    auto_save: bool,
) -> None:
    """질문 안내, 넣기 버튼, 넣은 뒤의 결과를 그린다.

    Args:
        registry: 실행 레지스트리.
        entries: 표에 그린 신규 영상.
        table_key: 표의 위젯 key. 콜백이 누른 순간의 선택을 읽는다.
        questions_key: 질문 선택의 위젯 key. 콜백이 누른 순간의
            질문을 읽는다.
        selected: 지금 표에서 고른 영상. 버튼 라벨과 잠금에 쓴다.
        chosen: 지금 고른 질문들. 버튼 잠금에 쓴다.
        auto_save: 화면에 보이는 자동 저장 값.
    """
    if not chosen:
        st.info("질문을 하나 이상 고르세요.")
    st.button(
        f"선택한 영상 요약 ({len(selected)}건)",
        key="channels_enqueue",
        disabled=not selected or not chosen,
        on_click=_enqueue_selected,
        args=(registry, entries, table_key, questions_key, auto_save),
    )
    _render_result()


def _enqueue_selected(
    registry: run_registry.RunRegistry,
    entries: tuple[models.FeedEntry, ...],
    table_key: str,
    questions_key: str,
    auto_save: bool,
) -> None:
    """고른 영상을 목록 순서로 대기열에 넣고 표의 선택을 비운다.

    넣기 버튼의 ``on_click`` 콜백이다. 표 선택과 질문은 버튼을 그릴
    때가 아니라 누른 순간의 세션 값을 읽는다. 결과 문구는 세션에
    적어 다음 그림에서 한 번 보인다.

    Args:
        registry: 실행 레지스트리.
        entries: 표에 그린 신규 영상.
        table_key: 표의 위젯 key.
        questions_key: 질문 선택의 위젯 key.
        auto_save: 화면에 보이는 자동 저장 값. 넣은 실행마다 고정된다.
    """
    state = st.session_state.get(table_key) or {}
    rows = state.get("selection", {}).get("rows", [])
    chosen = st.session_state.get(questions_key, [])
    targets = _channel_videos.selected_entries(entries, rows)
    if not targets or not chosen:
        return
    ahead = queue_notice.count_ahead(registry)
    paused = registry.paused_reason() is not None
    digesting = session.get_digest_registry().is_running()
    added = _enqueue_each(registry, targets, chosen, auto_save)
    st.session_state[_GENERATION_KEY] = generation() + 1
    if added == 0:
        st.session_state[_ENQUEUED_KEY] = _Enqueued(_ALL_PENDING, added=False)
        return
    text = queue_notice.enqueued_text(
        added=added,
        skipped=len(targets) - added,
        ahead=ahead,
        paused=paused,
        digesting=digesting,
    )
    st.session_state[_ENQUEUED_KEY] = _Enqueued(text, added=True)


def _enqueue_each(
    registry: run_registry.RunRegistry,
    targets: list[models.FeedEntry],
    chosen: list[models.Question],
    auto_save: bool,
) -> int:
    """대기·실행 중이 아닌 영상을 차례로 넣고 넣은 수를 돌려준다.

    질의 화면과 같은 기준으로 거른다. 끝났거나 실패한 영상은 다시
    넣는다.

    Args:
        registry: 실행 레지스트리.
        targets: 넣을 영상. 이 순서대로 대기열에 선다.
        chosen: 모든 영상에 쓸 질문들.
        auto_save: 넣은 실행에 고정할 자동 저장 값.

    Returns:
        넣은 수.
    """
    digests = session.get_digest_registry()
    added = 0
    for entry in targets:
        if registry.is_pending(entry.video_id):
            continue
        runner.enqueue(
            registry,
            youtube.watch_url(entry.video_id),
            chosen,
            store.default_db_path(),
            auto_save=auto_save,
            is_blocked=digests.is_running,
        )
        added += 1
    return added


def _render_result() -> None:
    """넣은 뒤의 결과를 한 번 보인다."""
    result = st.session_state.pop(_ENQUEUED_KEY, None)
    if result is None:
        return
    if result.added:
        st.success(result.text)
    else:
        st.info(result.text)
