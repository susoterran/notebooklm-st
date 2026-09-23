"""채널 화면 — 즐겨찾기 채널을 등록하고 새 영상을 찾는다.

이 파일 안에서 ``channels`` 는 **저장소**(``services.channels``)다.
페이지는 자기 자신을 import 하지 않는다.
"""

import dataclasses
import datetime
import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import labels, models, new_videos, youtube
from notebooklm_st.services import (
    channel_feed,
    channel_lookup,
    channels,
    questions,
    run_history,
    runner,
    store,
)

_URL_KEY = "channels_url"
_BASELINE_KEY = "channels_baseline"
_QUESTIONS_KEY = "channels_questions"
_FOUND_KEY = "channels_found"
_STARTED_KEY = "channels_started"


@dataclasses.dataclass(frozen=True, slots=True)
class _Checked:
    """채널 하나의 확인 결과.

    세션에 담는 화면 전용 값이다. 채널 제목을 복사해 두므로 확인
    뒤에 채널을 지워도 목록이 그대로 보인다.
    """

    title: str
    entries: tuple[models.FeedEntry, ...]
    error: str | None


def render() -> None:
    """채널 등록과 구독 목록을 그린다."""
    st.title("채널")
    connection = session.get_connection()
    _render_register(connection)
    channel_list = channels.list_channels(connection)
    if not channel_list:
        st.info("등록된 채널이 없습니다. 위에서 채널 URL 을 등록하세요.")
        return
    _render_check(connection, channel_list)
    _render_list(connection, channel_list)


def _render_register(connection: sqlite3.Connection) -> None:
    """채널 URL 과 기준일을 받아 등록한다."""
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
        " 피드가 최신 15건까지만 주므로 그보다 거슬러 올라가지는"
        " 못합니다.",
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
    """등록된 채널을 수정·삭제 버튼과 함께 그린다."""
    st.subheader("등록된 채널")
    for channel in channel_list:
        _render_row(connection, channel)


def _render_row(
    connection: sqlite3.Connection, channel: models.Channel
) -> None:
    """채널 하나를 그린다.

    접힌 상태에서는 이름만 보인다(질문 관리와 같은 모양).
    """
    with st.expander(channel.title):
        st.markdown(f"[{channel.title}]({channel.url})")
        st.caption(f"채널 ID: {channel.channel_id}")
        edited = st.date_input(
            # 등록 칸의 "기준일" 과 라벨이 겹치지 않게 한다. 겹치면
            # 테스트가 라벨로 위젯을 찾을 수 없다.
            "이 채널의 기준일",
            value=datetime.date.fromisoformat(channel.baseline),
            key=f"channels_baseline_{channel.id}",
            help="고쳐도 화면에 떠 있는 새 영상 목록은 바뀌지"
            " 않습니다. 새 기준일로 보려면 확인을 다시 누르세요.",
        )
        left, right = st.columns(2)
        if left.button("기준일 저장", key=f"channels_save_{channel.id}"):
            _save_baseline(connection, channel.id, edited)
        if right.button("삭제", key=f"channels_delete_{channel.id}"):
            channels.delete_channel(connection, channel.id)
            st.rerun()


def _save_baseline(
    connection: sqlite3.Connection, channel_pk: int, baseline: object
) -> None:
    """고친 기준일을 저장한다."""
    if not isinstance(baseline, datetime.date):
        st.error("기준일을 하나 고르세요.")
        return
    try:
        channels.update_baseline(connection, channel_pk, baseline.isoformat())
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()


def _render_check(
    connection: sqlite3.Connection, channel_list: list[models.Channel]
) -> None:
    """확인 버튼과 그 결과를 그린다."""
    if st.button("새 영상 확인", key="channels_check"):
        st.session_state[_FOUND_KEY] = _check(connection, channel_list)
        st.session_state[_STARTED_KEY] = set()
    found = st.session_state.get(_FOUND_KEY)
    if found is None:
        return
    _render_found(connection, found)


def _check(
    connection: sqlite3.Connection, channel_list: list[models.Channel]
) -> list[_Checked]:
    """채널마다 피드를 읽어 신규를 고른다.

    **한 채널이 실패해도 멈추지 않는다.** 부분 목록임이 화면에
    드러나고 실패한 채널이 사유와 함께 남는다. 정리본이 멈추는
    이유(부분 결과가 완전해 보인다)가 여기엔 없다.

    Args:
        connection: 열린 커넥션.
        channel_list: 확인할 채널들.

    Returns:
        채널 순서대로의 확인 결과.
    """
    known = run_history.list_video_ids(connection)
    results: list[_Checked] = []
    with st.spinner("새 영상을 확인하는 중"):
        for channel in channel_list:
            feed = channel_feed.fetch(channel.channel_id)
            if feed.error is not None:
                results.append(_Checked(channel.title, (), feed.error))
                continue
            results.append(
                _Checked(
                    channel.title,
                    new_videos.select(feed.entries, channel.baseline, known),
                    None,
                )
            )
    return results


def _render_found(
    connection: sqlite3.Connection, found: list[_Checked]
) -> None:
    """확인 결과를 그리고 요약을 시작할 수 있게 한다."""
    question_list = questions.list_questions(connection)
    selected: list[models.Question] = []
    if not question_list:
        st.info("질문 관리 화면에서 질문을 먼저 등록하세요.")
    else:
        selected = st.multiselect(
            "질문 선택",
            options=question_list,
            format_func=lambda question: question.title,
            key=_QUESTIONS_KEY,
            help="고른 질문을 이 목록의 모든 요약에 씁니다.",
        )
    for item in found:
        if item.error is not None:
            st.error(f"{item.title}: {item.error}")
    total = sum(len(item.entries) for item in found)
    if total == 0:
        if all(item.error is None for item in found):
            st.info("새 영상이 없습니다.")
        return
    # 등록된 질문이 아예 없으면 위에서 이미 안내를 냈다. 그 위에
    # "질문을 하나 이상 고르세요" 를 겹쳐 적지 않는다.
    reason = _blocked_reason(selected) if question_list else None
    if reason is not None:
        # 영상마다 그리면 같은 문장이 목록을 도배한다. 한 번만 적는다.
        st.info(reason)
    for item in found:
        if item.entries:
            st.subheader(item.title)
            for entry in item.entries:
                _render_entry(entry, selected, reason, bool(question_list))


def _blocked_reason(selected: list[models.Question]) -> str | None:
    """요약을 막을 이유를 찾아 문장으로 돌려준다.

    질의와 정리는 같은 쿠키로 NotebookLM 에 붙으므로 동시에 돌리지
    않는다. 질의 화면과 같은 가드다.

    Args:
        selected: 고른 질문들.

    Returns:
        막을 이유. 없으면 ``None``.
    """
    if session.get_registry().running_count() > 0:
        return (
            "이미 실행 중인 질의가 있습니다. 실행 현황 화면에서"
            " 완료를 확인한 뒤 시작하세요."
        )
    if session.get_digest_registry().is_running():
        return (
            "정리본을 작성 중입니다. 정리본 화면에서 완료를 확인한 뒤"
            " 시작하세요."
        )
    if not selected:
        return "질문을 하나 이상 고르세요."
    return None


def _render_entry(
    entry: models.FeedEntry,
    selected: list[models.Question],
    reason: str | None,
    can_run: bool,
) -> None:
    """신규 영상 한 줄과 요약 버튼을 그린다.

    Args:
        entry: 그릴 신규 영상.
        selected: 고른 질문들.
        reason: 요약을 막을 이유. 없으면 ``None``.
        can_run: 등록된 질문이 하나라도 있는가. 없으면 버튼 자체를
            그리지 않는다(→ 스펙 §10.3). 미선택·실행 중과 달리
            질문이 없으면 누를 길이 아예 없기 때문이다.
    """
    url = youtube.watch_url(entry.video_id)
    started = st.session_state.get(_STARTED_KEY, set())
    left, right = st.columns([4, 1])
    left.markdown(
        f"[{labels.shorten(entry.title)}]({url})"
        f" · {entry.published.astimezone():%Y-%m-%d %H:%M}"
    )
    if entry.video_id in started:
        right.caption("실행 중")
        return
    if not can_run:
        return
    if right.button(
        "요약",
        key=f"channels_run_{entry.video_id}",
        disabled=reason is not None,
    ):
        runner.start_run(
            session.get_registry(),
            url,
            selected,
            store.default_db_path(),
        )
        st.session_state[_STARTED_KEY] = started | {entry.video_id}
        st.rerun()
