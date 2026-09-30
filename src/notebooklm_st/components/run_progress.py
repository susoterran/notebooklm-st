"""실행 현황 표의 머리글과 한 줄을 그린다.

칸마다 들어갈 글자는 순수 함수가 만들고, ``render_row`` 는 그것을
``st.columns`` 한 줄에 놓기만 한다. 순수 함수는 Streamlit 없이
테스트한다.
"""

import datetime
import re
from collections.abc import Callable
from typing import Literal, assert_never

import streamlit as st

from notebooklm_st.core import labels, youtube
from notebooklm_st.services import runs

BadgeColor = Literal["blue", "green", "red"]
"""상태 배지에 쓰는 색. ``st.badge`` 가 받는 색의 일부다."""

TITLE_MAX_CHARS = 40
"""영상 칸에 넣을 제목의 최대 글자 수.

결과 칸과 한 줄을 나눠 쓰므로 목록 라벨
(``labels.LIST_LABEL_MAX_CHARS``)보다 짧다.
"""

HIDE_HELP = "목록에서만 치웁니다. 실행은 계속됩니다."
"""진행 중인 실행의 숨기기 버튼 도움말."""

_COLUMNS: tuple[tuple[str, float], ...] = (
    ("상태", 1.1),
    ("영상", 3.4),
    ("시작", 1.3),
    ("질문", 0.8),
    ("결과", 3.4),
    ("저장", 2.0),
    ("동작", 1.0),
)
"""칸 이름과 상대 폭.

머리글과 모든 행이 이 폭을 함께 써야 칸이 위아래로 맞는다.
"""

_WIDTHS = [width for _, width in _COLUMNS]

_MARKDOWN_SPECIAL = re.compile(r"([\\`*_\[\]$<>~|#])")
"""마크다운에서 서식으로 읽히는 글자.

영상 제목·오류 문구·질문 제목은 우리가 고른 문자열이 아니다. 대괄호
하나가 링크를 깨고 ``$`` 둘이 수식을 만든다. 앞에 역슬래시를 붙여
글자 그대로 보이게 한다.
"""

_NO_SAVE = "—"
"""저장 칸에 적을 것이 없을 때의 표시."""


def status_badge(handle: runs.RunHandle) -> tuple[str, BadgeColor]:
    """상태 칸의 배지 글자와 색을 고른다.

    Args:
        handle: 그릴 실행.

    Returns:
        배지 글자와 색.
    """
    match handle.status:
        case "running":
            return "실행 중", "blue"
        case "failed":
            return "실패", "red"
        case "done":
            return "완료", "green"
        case _:
            assert_never(handle.status)


def video_label(handle: runs.RunHandle) -> str:
    """영상 칸의 링크 글자를 고른다.

    제목은 파이프라인이 끝나야 생긴다. 그래서 결과가 있는 실행만
    제목을 쓰고, 그 전에는 영상 ID 를, 그것마저 없으면 URL 을 쓴다.

    Args:
        handle: 그릴 실행.

    Returns:
        마크다운으로 거르기 전의 링크 글자.
    """
    if handle.result is not None and handle.result.title:
        return labels.shorten(handle.result.title, TITLE_MAX_CHARS)
    return handle.video_id or handle.url


def short_time(value: str) -> str:
    """ISO 시각을 표에 맞게 줄인다.

    Args:
        value: ``2026-09-30T17:12:46`` 형식의 시각.

    Returns:
        ``09-30 17:12`` 형식의 문자열.
    """
    return datetime.datetime.fromisoformat(value).strftime("%m-%d %H:%M")


def result_markdown(handle: runs.RunHandle) -> str:
    """결과 칸의 마크다운을 만든다.

    답변 본문은 그리지 않는다. ``runner`` 는 이력을 DB 에 저장한
    뒤에야 실행을 done 으로 표시하므로, 완료된 실행은 이력 화면에
    반드시 있다. 본문 확인과 수정은 거기서 한다.

    Args:
        handle: 그릴 실행.

    Returns:
        칸 하나에 넣을 한 문단짜리 마크다운.
    """
    match handle.status:
        case "running":
            latest = handle.progress[-1] if handle.progress else "시작하는 중"
            return _escape(latest)
        case "failed":
            text = _escape(
                handle.error_message or "알 수 없는 오류로 실패했습니다."
            )
            if handle.error_level == "info":
                return text
            return f":red[{text}]"
        case "done":
            return _done_markdown(handle)
        case _:
            assert_never(handle.status)


def _done_markdown(handle: runs.RunHandle) -> str:
    """완료된 실행의 결과 칸 마크다운을 만든다."""
    if handle.result is None:
        return ":orange[완료되었지만 결과가 비어 있습니다.]"
    items = handle.result.items
    summary = f"답변 {len(items)}건"
    failed = [item for item in items if item.error is not None]
    if not failed:
        return summary
    titles = _escape(", ".join(item.question_title for item in failed))
    return f"{summary} · :orange[{len(failed)}건 실패: {titles}]"


def save_markdown(handle: runs.RunHandle) -> str:
    """저장 칸의 마크다운을 만든다.

    자동 저장을 끈 실행과, 실행이 실패해 올릴 이력이 없는 실행은
    ``—`` 다. 문서가 만들어졌으면 문구를 그 문서로 가는 링크로 건다.
    문서는 만들었는데 로컬 기록에 실패한 경우도 링크가 걸린다. 사람이
    그 문서를 열어 보고 다시 올릴지 정해야 하기 때문이다.

    Args:
        handle: 그릴 실행.

    Returns:
        칸 하나에 넣을 한 문단짜리 마크다운.
    """
    if not handle.auto_save:
        return _NO_SAVE
    match handle.status:
        case "running":
            return "자동"
        case "failed":
            return _NO_SAVE
        case "done":
            if handle.save is None:
                return _NO_SAVE
            text = _escape(handle.save.message)
            if handle.save.url is None:
                return text
            return f"[{text}]({handle.save.url})"
        case _:
            assert_never(handle.status)


def render_header() -> None:
    """표의 머리글 한 줄을 그린다."""
    cells = st.columns(_WIDTHS, gap="small", vertical_alignment="center")
    for cell, (name, _) in zip(cells, _COLUMNS, strict=True):
        cell.markdown(f"**{name}**")


def render_row(
    handle: runs.RunHandle, on_remove: Callable[[str], None]
) -> None:
    """실행 하나를 표의 한 줄로 그린다.

    버튼은 누른 순간 ``on_remove(run_id)`` 를 콜백으로 부른다. 콜백은
    재실행 전에 돌아 치운 결과가 다음 그림에 바로 보인다. 버튼 키에
    실행 ID 가 들어가므로 그 사이 표에 행이 끼어도 누른 행의 실행만
    치운다.

    Args:
        handle: 그릴 실행.
        on_remove: 실행 ID 를 받아 목록에서 치우는 함수.
    """
    (
        status_cell,
        video_cell,
        time_cell,
        count_cell,
        result_cell,
        save_cell,
        action,
    ) = st.columns(_WIDTHS, gap="small", vertical_alignment="center")
    label, color = status_badge(handle)
    status_cell.badge(label, color=color)
    target = (
        youtube.watch_url(handle.video_id) if handle.video_id else handle.url
    )
    video_cell.markdown(f"[{_escape(video_label(handle))}]({target})")
    time_cell.markdown(short_time(handle.started_at))
    count_cell.markdown(f"{len(handle.question_texts)}개")
    result_cell.markdown(result_markdown(handle))
    save_cell.markdown(save_markdown(handle))
    match handle.status:
        case "running":
            action.button(
                "숨기기",
                key=f"dashboard_hide_{handle.run_id}",
                type="tertiary",
                help=HIDE_HELP,
                on_click=on_remove,
                args=(handle.run_id,),
            )
        case "done" | "failed":
            action.button(
                "지우기",
                key=f"dashboard_discard_{handle.run_id}",
                type="tertiary",
                on_click=on_remove,
                args=(handle.run_id,),
            )
        case _:
            assert_never(handle.status)


def _escape(text: str) -> str:
    """마크다운 서식 글자를 걷어 글자 그대로 보이게 한다.

    줄바꿈과 겹친 공백은 공백 하나로 접는다. 표의 한 칸을 한 문단으로
    둔다.
    """
    return _MARKDOWN_SPECIAL.sub(r"\\\1", " ".join(text.split()))
