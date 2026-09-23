"""채널 화면 — 즐겨찾기 채널을 등록하고 새 영상을 찾는다.

기능이 셋이라 **탭으로 가른다** — 새 영상 확인 · 채널 등록 · 등록된
채널. 한 번에 하나만 보이므로 등록 칸의 기준일을 확인용으로 오해할
길이 없다. 확인·요약은 분량이 커서 ``pages/_channel_check.py`` 가
맡는다.

이 파일 안에서 ``channels`` 는 **저장소**(``services.channels``)다.
페이지는 자기 자신을 import 하지 않는다.
"""

import datetime
import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import models
from notebooklm_st.pages import _channel_check
from notebooklm_st.services import channel_feed, channel_lookup, channels

_URL_KEY = "channels_url"
_BASELINE_KEY = "channels_baseline"

_EMPTY_NOTICE = "등록된 채널이 없습니다. 채널 등록 탭에서 먼저 등록하세요."


def render() -> None:
    """탭 셋으로 나눈 채널 화면을 그린다."""
    st.title("채널")
    connection = session.get_connection()
    channel_list = channels.list_channels(connection)
    check_tab, add_tab, list_tab = st.tabs(
        ["새 영상 확인", "채널 등록", "등록된 채널"]
    )
    with check_tab:
        if channel_list:
            _channel_check.render(connection, channel_list)
        else:
            st.info(_EMPTY_NOTICE)
    with add_tab:
        _render_register(connection)
    with list_tab:
        if channel_list:
            _render_list(connection, channel_list)
        else:
            st.info(_EMPTY_NOTICE)


def _render_register(connection: sqlite3.Connection) -> None:
    """채널 URL 과 처음 기준일을 받아 등록한다."""
    url = st.text_input(
        "채널 URL",
        key=_URL_KEY,
        placeholder="https://www.youtube.com/@handle",
    )
    baseline = st.date_input(
        "기준일",
        value=datetime.date.today(),
        key=_BASELINE_KEY,
        help="이 날짜 이후 업로드된 영상만 새 영상으로 봅니다."
        " 등록 뒤에는 새 영상 확인 탭에서 바꿉니다.",
    )
    if st.button("등록", key="channels_add", disabled=not url.strip()):
        _add(connection, url, baseline)


def _add(connection: sqlite3.Connection, url: str, baseline: object) -> None:
    """해석 · 피드 확인 · 저장을 차례로 한다.

    **피드를 등록 시점에 한 번 찔러 본다.** 피드가 없는 채널을
    등록해 두면 확인할 때마다 실패한다. 실패를 매일 겪는 자리가
    아니라 한 번 겪는 자리로 당긴다.

    Args:
        connection: 열린 커넥션.
        url: 등록할 채널의 URL.
        baseline: ``st.date_input`` 이 돌려준 값. 범위 선택이면
            날짜가 아니므로 막는다.
    """
    if not isinstance(baseline, datetime.date):
        st.error("기준일을 하나 고르세요.")
        return
    with st.spinner("채널을 확인하는 중"):
        found = channel_lookup.lookup(url)
        if (
            found.error is not None
            or found.channel_id is None
            or found.title is None
            or found.url is None
        ):
            st.error(found.error or "채널을 해석하지 못했습니다.")
            return
        feed = channel_feed.fetch(found.channel_id)
    if feed.error is not None:
        st.error(feed.error)
        return
    try:
        channels.add_channel(
            connection,
            found.channel_id,
            found.title,
            found.url,
            baseline.isoformat(),
        )
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()


def _render_list(
    connection: sqlite3.Connection, channel_list: list[models.Channel]
) -> None:
    """등록된 채널을 이름 수정·삭제와 함께 그린다."""
    for channel in channel_list:
        _render_row(connection, channel)


def _render_row(
    connection: sqlite3.Connection, channel: models.Channel
) -> None:
    """채널 하나를 그린다.

    접힌 상태에서는 이름만 보인다(질문 관리와 같은 모양). 기준일은
    읽기 전용이다 — 고치는 자리는 새 영상 확인 탭 하나뿐이다.
    """
    with st.expander(channel.title):
        st.markdown(f"[{channel.title}]({channel.url})")
        st.caption(f"채널 ID: {channel.channel_id}")
        st.caption(
            f"기준일: {channel.baseline} — 새 영상 확인 탭에서 바꿉니다."
        )
        edited = st.text_input(
            "채널명",
            value=channel.title,
            key=f"channels_title_{channel.id}",
            help="등록할 때 yt-dlp 가 준 이름입니다. 목록은 이 이름"
            " 순으로 정렬됩니다.",
        )
        left, right = st.columns(2)
        if left.button("이름 저장", key=f"channels_save_{channel.id}"):
            _save_title(connection, channel.id, edited)
        if right.button("삭제", key=f"channels_delete_{channel.id}"):
            channels.delete_channel(connection, channel.id)
            st.rerun()


def _save_title(
    connection: sqlite3.Connection, channel_pk: int, title: str
) -> None:
    """고친 채널명을 저장한다."""
    try:
        channels.update_title(connection, channel_pk, title)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()
