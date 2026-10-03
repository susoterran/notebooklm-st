"""정리본 재료를 카테고리와 채널로 거르는 순수 함수.

재료 표 위의 두 필터가 쓴다. Streamlit 도 DB 도 모른다.
"""

from collections.abc import Collection, Sequence

from notebooklm_st.core import category_names, models


def category_options(runs: Sequence[models.RunSummary]) -> tuple[str, ...]:
    """후보들에 붙은 카테고리를 중복 없이 이름 순으로 모은다.

    Args:
        runs: 재료 후보.

    Returns:
        필터에 보일 이름들. 고르면 빈 표가 되는 이름은 없다.
    """
    return category_names.ordered(
        name for run in runs for name in run.categories
    )


def channel_options(runs: Sequence[models.RunSummary]) -> tuple[str, ...]:
    """후보들의 채널을 중복 없이 정렬해 모은다. 빈 값은 뺀다.

    Args:
        runs: 재료 후보.

    Returns:
        필터에 보일 채널들.
    """
    return tuple(
        sorted(
            {
                run.metadata.channel
                for run in runs
                if run.metadata is not None and run.metadata.channel
            }
        )
    )


def filter_runs(
    runs: Sequence[models.RunSummary],
    categories: Collection[str],
    channels: Collection[str],
) -> list[models.RunSummary]:
    """두 필터에 맞는 재료만 받은 순서대로 남긴다.

    각 필터 안은 하나라도 맞으면, 두 필터 사이는 둘 다 맞아야
    남긴다. 비운 필터는 거르지 않는다. 카테고리가 없는 재료는 카테고리
    필터가 있으면 빠지고, 채널이 없는 재료는 채널 필터가 있으면
    빠진다.

    Args:
        runs: 재료 후보.
        categories: 고른 카테고리 이름.
        channels: 고른 채널.

    Returns:
        남은 재료.
    """
    return [
        run
        for run in runs
        if _has_category(run, categories) and _on_channel(run, channels)
    ]


def _has_category(run: models.RunSummary, categories: Collection[str]) -> bool:
    """카테고리 필터가 비었거나, 고른 이름 중 하나가 붙었는가."""
    return not categories or any(name in categories for name in run.categories)


def _on_channel(run: models.RunSummary, channels: Collection[str]) -> bool:
    """채널 필터가 비었거나, 고른 채널 중 하나의 재료인가."""
    if not channels:
        return True
    channel = run.metadata.channel if run.metadata is not None else None
    return channel is not None and channel in channels
