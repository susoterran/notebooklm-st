"""채널 화면의 "새 영상 확인" 탭 — 신규를 골라 대기열에 넣는다.

``pages/channels.py`` 가 이 모듈을 부른다. 네비게이션에 직접 등록되지
않으므로 이름 앞에 밑줄을 둔다.

**확인 대상은 채널 하나다.** 기준일이 그 채널 하나에만 적용되므로
"이 기준일이 무엇에 걸리는가" 가 애매해지지 않는다. 고른 기준일은
확인할 때 그 채널에 저장되어, 기준일을 정하는 자리가 화면에 하나만
남는다.

신규는 표에서 여러 건을 골라 한 번에 질의 대기열에 넣는다. 표는
``pages/_channel_videos.py``, 넣기는 ``pages/_channel_enqueue.py`` 가
맡는다. 진행 상황과 결과는 실행 현황 화면에서 본다.
"""

import dataclasses
import datetime
import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import auto_save_toggle, queue_notice
from notebooklm_st.core import models, new_videos
from notebooklm_st.pages import _channel_enqueue, _channel_videos
from notebooklm_st.services import (
    channel_feed,
    channels,
    questions,
    run_history,
)

_TARGET_KEY = "channels_target"
_QUESTIONS_KEY = "channels_questions"
_FOUND_KEY = "channels_found"
_AUTO_SAVE_KEY = "channels_auto_save"
_AUTO_SAVE_LOCKED_KEY = "channels_auto_save_locked"


@dataclasses.dataclass(frozen=True, slots=True)
class _Checked:
    """채널 하나의 확인 결과.

    세션에 담는 화면 전용 값이다. 채널 제목을 복사해 두므로 확인
    뒤에 채널을 지워도 목록이 그대로 보인다. ``channel_pk`` 는 지금
    고른 채널의 결과인지 가리는 데 쓴다.
    """

    channel_pk: int
    title: str
    entries: tuple[models.FeedEntry, ...]
    error: str | None


def render(
    connection: sqlite3.Connection, channel_list: list[models.Channel]
) -> None:
    """대상 채널과 기준일을 받아 신규를 찾고 대기열에 넣게 한다.

    Args:
        connection: 열린 커넥션.
        channel_list: 등록된 채널들. 비어 있지 않다.
    """
    target = st.selectbox(
        "대상 채널",
        options=channel_list,
        format_func=lambda channel: channel.title,
        key=_TARGET_KEY,
    )
    baseline = st.date_input(
        # 위젯 key 에 채널 id 를 넣는다. key 가 같으면 Streamlit 이
        # 세션 값을 우선해, 채널을 바꿔도 앞 채널의 날짜가 남는다.
        "이 채널의 기준일",
        value=datetime.date.fromisoformat(target.baseline),
        key=f"channels_check_baseline_{target.id}",
        help="이 날짜 이후 업로드된 영상만 새 영상으로 봅니다."
        " 확인을 누르면 이 채널의 기준일로 저장됩니다. 피드가 최신"
        " 15건까지만 주므로 그보다 거슬러 올라가지는 못합니다.",
    )
    if st.button("새 영상 확인", key="channels_check"):
        _start_check(connection, target, baseline)
    found = st.session_state.get(_FOUND_KEY)
    if found is None or found.channel_pk != target.id:
        # 다른 채널의 결과가 남아 있으면 무엇을 보고 있는지 알 수
        # 없다. 대상이 바뀌면 그리지 않는다.
        return
    _render_found(connection, found)


def _start_check(
    connection: sqlite3.Connection,
    target: models.Channel,
    baseline: object,
) -> None:
    """기준일을 저장하고 그 채널을 조회한다.

    Args:
        connection: 열린 커넥션.
        target: 확인할 채널.
        baseline: ``st.date_input`` 이 돌려준 값. 범위 선택이면
            날짜가 아니므로 막는다.
    """
    if not isinstance(baseline, datetime.date):
        st.error("기준일을 하나 고르세요.")
        return
    try:
        channels.update_baseline(connection, target.id, baseline.isoformat())
    except ValueError as error:
        st.error(str(error))
        return
    st.session_state[_FOUND_KEY] = _check(connection, target, baseline)


def _check(
    connection: sqlite3.Connection,
    target: models.Channel,
    baseline: datetime.date,
) -> _Checked:
    """피드를 읽어 신규를 고른다.

    방금 고른 기준일을 쓴다. ``target.baseline`` 은 이번 실행에서
    읽어 온 값이라 아직 옛 날짜다.

    Args:
        connection: 열린 커넥션.
        target: 확인할 채널.
        baseline: 방금 저장한 기준일.

    Returns:
        신규 목록 또는 사람에게 보여 줄 실패 사유.
    """
    known = run_history.list_video_ids(connection)
    with st.spinner("새 영상을 확인하는 중"):
        feed = channel_feed.fetch(target.channel_id)
    if feed.error is not None:
        return _Checked(target.id, target.title, (), feed.error)
    return _Checked(
        target.id,
        target.title,
        new_videos.select(feed.entries, baseline.isoformat(), known),
        None,
    )


def _render_found(connection: sqlite3.Connection, found: _Checked) -> None:
    """확인 결과를 표로 그리고 고른 영상을 넣을 수 있게 한다.

    질문 선택은 결과보다 먼저 그린다. 결과가 오류나 빈 목록이어도
    위젯이 그려져야 고른 질문이 남는다.
    """
    question_list = questions.list_questions(connection)
    chosen: list[models.Question] = []
    if not question_list:
        st.info("질문 관리 화면에서 질문을 먼저 등록하세요.")
    else:
        chosen = st.multiselect(
            "질문 선택",
            options=question_list,
            format_func=lambda question: question.title,
            key=_QUESTIONS_KEY,
            help="고른 질문을 이번에 넣는 영상 모두에 씁니다.",
        )
    if found.error is not None:
        st.error(f"{found.title}: {found.error}")
        return
    if not found.entries:
        st.info("새 영상이 없습니다.")
        return
    registry = session.get_registry()
    auto_save = False
    if question_list:
        auto_save = auto_save_toggle.render(
            connection, _AUTO_SAVE_KEY, _AUTO_SAVE_LOCKED_KEY
        )
        queue_notice.render(registry)
    st.subheader(found.title)
    key = _channel_videos.widget_key(
        found.entries, _channel_enqueue.generation()
    )
    selected = _channel_videos.render(found.entries, registry.list_all(), key)
    if question_list:
        _channel_enqueue.render(
            registry,
            found.entries,
            key,
            _QUESTIONS_KEY,
            selected,
            chosen,
            auto_save,
        )
