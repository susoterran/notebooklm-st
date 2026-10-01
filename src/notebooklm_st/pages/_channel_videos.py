"""채널 화면의 신규 영상 표.

``pages/_channel_check.py`` 가 이 모듈을 부른다. 네비게이션에 직접
등록되지 않으므로 이름 앞에 밑줄을 둔다.

신규 영상을 표 하나로 보여 주고 행을 골라 대기열에 넣게 한다. 표는
선택을 **행 번호**로 돌려준다. 그래서 표의 key 를 영상 목록과 넣기
횟수에서 만들어, 목록이 바뀌거나 한 번 넣으면 선택이 비워지게 한다
(``widget_key`` 참고).
"""

import hashlib
from collections.abc import Sequence

import streamlit as st

from notebooklm_st.core import models, youtube
from notebooklm_st.services import runs

STATUS_LABELS: dict[runs.RunStatus, str] = {
    "queued": "대기 중",
    "running": "실행 중",
    "done": "끝남",
    "failed": "실패",
}
"""실행 상태를 표의 상태 칸에 적을 말."""

_KEY_PREFIX = "channels_videos_"


def render(
    entries: Sequence[models.FeedEntry],
    handles: Sequence[runs.RunHandle],
    key: str,
) -> list[models.FeedEntry]:
    """신규 영상 표를 그리고 고른 영상을 돌려준다.

    Args:
        entries: 신규 영상. 표에 이 순서대로 나온다.
        handles: 상태를 읽을 실행들. ``registry.list_all()`` 의
            순서 그대로다.
        key: 표의 위젯 key. ``widget_key`` 로 만든다.

    Returns:
        고른 영상. 누른 순서나 정렬과 상관없이 ``entries`` 의 순서를
        따른다.
    """
    st.caption("행 왼쪽 칸을 눌러 고릅니다.")
    event = st.dataframe(
        [
            _row(entry, status_label(entry.video_id, handles))
            for entry in entries
        ],
        key=key,
        on_select="rerun",
        selection_mode="multi-row",
        hide_index=True,
        placeholder="",
        column_config={
            "title": st.column_config.TextColumn("제목"),
            "published": st.column_config.TextColumn("업로드일"),
            "status": st.column_config.TextColumn("상태"),
            "url": st.column_config.LinkColumn("영상", display_text="열기"),
        },
    )
    return selected_entries(entries, event.selection.rows)


def selected_entries(
    entries: Sequence[models.FeedEntry], rows: Sequence[int]
) -> list[models.FeedEntry]:
    """고른 행 번호를 영상으로 옮긴다.

    표는 정렬해도 원래 목록의 위치 번호를 돌려준다. 번호를 정렬해
    목록 순서로 돌려주고, 목록 밖의 번호는 버린다.

    Args:
        entries: 표에 그린 신규 영상.
        rows: 고른 행의 위치 번호.

    Returns:
        고른 영상. ``entries`` 의 순서를 따른다.
    """
    return [entries[row] for row in sorted(rows) if 0 <= row < len(entries)]


def widget_key(entries: Sequence[models.FeedEntry], generation: int) -> str:
    """표의 위젯 key 를 영상 ID 구성과 넣기 횟수에서 만든다.

    key 를 준 표는 데이터가 바뀌어도 같은 위젯으로 남고, 고른 행
    번호도 그대로 남는다. 확인을 다시 눌러 목록이 바뀌면 그 번호가
    다른 영상을 가리킨다. 넣은 뒤에는 같은 영상을 다시 넣는 클릭을
    막으려고 선택을 비운다. 둘 다 key 가 바뀌면 Streamlit 이 새 표로
    보고 선택을 비운다.

    상태 칸은 key 에 넣지 않는다. 고르는 사이 실행이 끝나기만 해도
    고른 것이 사라지면 안 된다.

    Args:
        entries: 표에 오를 신규 영상. 순서까지 key 에 반영된다.
        generation: 이 화면에서 넣기를 한 횟수.

    Returns:
        같은 목록·같은 횟수에는 늘 같은 문자열.
    """
    ids = ",".join(entry.video_id for entry in entries)
    digest = hashlib.sha256(f"{ids}#{generation}".encode()).hexdigest()[:16]
    return f"{_KEY_PREFIX}{digest}"


def status_label(
    video_id: str, handles: Sequence[runs.RunHandle]
) -> str | None:
    """그 영상의 실행 상태를 표에 적을 말로 옮긴다.

    ``handles`` 는 진행 중 → 대기 → 최근 끝난 순서라 처음 만나는
    핸들이 지금 가장 의미 있는 상태다. 취소했거나 실행 현황에서 지운
    실행은 목록에 없으므로 빈칸으로 돌아온다.

    Args:
        video_id: 상태를 볼 영상 ID.
        handles: 레지스트리의 실행들.

    Returns:
        상태 라벨. 그 영상의 실행이 없으면 ``None``.
    """
    for handle in handles:
        if handle.video_id == video_id:
            return STATUS_LABELS[handle.status]
    return None


def _row(entry: models.FeedEntry, status: str | None) -> dict[str, str | None]:
    """영상 하나를 표의 한 행으로 만든다.

    열 순서가 곧 표의 열 순서다. 업로드일은 로컬 시각
    ``YYYY-MM-DD HH:MM`` 문자열이라 머리글 정렬이 시간 순서와 같다.
    표 칸은 일반 글자라 제목의 마크다운 글자를 걷을 필요가 없다.
    """
    return {
        "title": entry.title,
        "published": f"{entry.published.astimezone():%Y-%m-%d %H:%M}",
        "status": status,
        "url": youtube.watch_url(entry.video_id),
    }
