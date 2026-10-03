"""정리본 화면의 재료 표.

``pages/digest.py`` 가 이 모듈을 부른다. 네비게이션에 직접 등록되지
않으므로 이름 앞에 밑줄을 둔다.

저장된 요약본 전체를 표 하나로 보여 주고 행을 골라 재료로 삼는다.
표 위의 카테고리·채널 필터로 후보를 좁힌다. 표는 선택을 **행
번호**로 돌려준다. 그래서 표의 key 를 표에 오른 재료 목록에서 만들어,
목록이 바뀌면 — 필터를 바꿔도 — 선택이 다른 글로 밀리는 대신
비워지게 한다(``widget_key`` 참고).
"""

import hashlib
from collections.abc import Sequence

import streamlit as st

from notebooklm_st.core import material_filter, models
from notebooklm_st.services import nlm

_KEY_PREFIX = "digest_materials_"
_CATEGORY_FILTER_KEY = "digest_filter_categories"
_CHANNEL_FILTER_KEY = "digest_filter_channels"


def render(runs: Sequence[models.RunSummary]) -> list[models.RunSummary]:
    """필터, 재료 표, 고른 재료 목록을 그린다.

    Args:
        runs: 재료 후보. 필터를 거친 뒤 표에 이 순서대로 나온다.

    Returns:
        고른 실행. 사람이 누른 순서가 아니라 표의 순서를 따른다.
        필터에 맞는 재료가 없으면 빈 목록이다.
    """
    st.markdown("**재료 선택**")
    shown = _render_filters(runs)
    st.caption(
        f"행 왼쪽 칸을 눌러 고릅니다(최대 {nlm.DIGEST_SOURCE_LIMIT}건)."
        " 머리글을 누르면 정렬되고, 표 위 도구 막대에서 제목을"
        " 검색합니다. 필터를 바꾸면 고른 재료가 풀립니다."
    )
    if not shown:
        st.info("고른 조건에 맞는 요약본이 없습니다.")
        return []
    event = st.dataframe(
        [_row(run) for run in shown],
        key=widget_key(shown),
        on_select="rerun",
        selection_mode="multi-row",
        hide_index=True,
        placeholder="",
        column_config={
            "title": st.column_config.TextColumn("문서 제목"),
            "categories": st.column_config.TextColumn("카테고리"),
            "channel": st.column_config.TextColumn("채널"),
            "upload_date": st.column_config.TextColumn("업로드일"),
            "created_at": st.column_config.TextColumn("시각"),
            "url": st.column_config.LinkColumn("Outline", display_text="열기"),
        },
    )
    selected = [shown[row] for row in sorted(event.selection.rows)]
    _render_picked(selected)
    return selected


def _render_filters(
    runs: Sequence[models.RunSummary],
) -> list[models.RunSummary]:
    """카테고리·채널 필터를 나란히 그리고 남은 재료를 돌려준다.

    선택지는 재료에 실제로 나오는 값뿐이다. 선택지가 없는 필터는
    그리지 않는다.

    Args:
        runs: 재료 후보.

    Returns:
        두 필터에 맞는 재료. 받은 순서를 지킨다.
    """
    category_choices = material_filter.category_options(runs)
    channel_choices = material_filter.channel_options(runs)
    left, right = st.columns(2)
    chosen_categories: list[str] = []
    chosen_channels: list[str] = []
    if category_choices:
        chosen_categories = left.multiselect(
            "카테고리",
            options=category_choices,
            key=_CATEGORY_FILTER_KEY,
            help="고른 카테고리 중 하나라도 붙은 요약본만 보입니다.",
        )
    if channel_choices:
        chosen_channels = right.multiselect(
            "채널",
            options=channel_choices,
            key=_CHANNEL_FILTER_KEY,
            help="고른 채널의 요약본만 보입니다.",
        )
    return material_filter.filter_runs(runs, chosen_categories, chosen_channels)


def widget_key(runs: Sequence[models.RunSummary]) -> str:
    """재료 표의 위젯 key 를 목록의 실행 ID 구성에서 만든다.

    key 를 준 표는 데이터가 바뀌어도 같은 위젯으로 남고, 고른 행
    번호도 그대로 남는다. 다른 탭에서 저장·동기화·삭제로 목록이
    바뀌면 그 번호가 다른 글을 가리킨다. 목록이 바뀔 때 key 도
    바뀌면 Streamlit 이 새 표로 보고 선택을 비운다.

    Args:
        runs: 표에 오를 재료. 순서까지 key 에 반영된다.

    Returns:
        같은 목록에는 늘 같은 문자열.
    """
    ids = ",".join(str(run.id) for run in runs)
    digest = hashlib.sha256(ids.encode()).hexdigest()[:16]
    return f"{_KEY_PREFIX}{digest}"


def _row(run: models.RunSummary) -> dict[str, str | None]:
    """재료 하나를 표의 한 행으로 만든다.

    열 순서가 곧 표의 열 순서다. 카테고리·채널·업로드일은 고르는
    기준이라 제목 바로 뒤에 둔다. 업로드일은 ``YYYY-MM-DD`` 문자열이라
    머리글 정렬이 날짜 순서와 같다. 값이 없는 칸은 ``None`` 이라
    빈칸으로 보인다.
    """
    metadata = run.metadata
    return {
        "title": _title(run),
        "categories": ", ".join(run.categories) or None,
        "channel": metadata.channel if metadata else None,
        "upload_date": metadata.upload_date if metadata else None,
        "created_at": run.created_at,
        "url": run.outline_url,
    }


def _title(run: models.RunSummary) -> str:
    """재료를 부를 이름.

    위키에 붙은 문서 제목을 쓴다. 고르는 사람이 찾는 이름이 그것이다.
    """
    return run.outline_title or run.title or run.video_id


def _render_picked(selected: Sequence[models.RunSummary]) -> None:
    """고른 재료를 개수와 제목으로 다시 보여 준다.

    표에서 체크한 행은 스크롤하면 보이지 않는다. 시작하기 전에 무엇을
    넘기는지 한곳에서 확인하게 한다.
    """
    if not selected:
        return
    lines = [f"**고른 재료 {len(selected)}/{nlm.DIGEST_SOURCE_LIMIT}**", ""]
    lines.extend(f"- {_title(run)}" for run in selected)
    st.markdown("\n".join(lines))
