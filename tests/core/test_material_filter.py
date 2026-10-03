"""정리본 재료 거르기 테스트."""

from collections.abc import Sequence

from notebooklm_st.core import material_filter, models


def make_run(
    run_id: int, categories: tuple[str, ...] = (), channel: str | None = None
) -> models.RunSummary:
    """카테고리와 채널만 다른 저장된 요약본을 만든다."""
    metadata = None
    if channel is not None:
        metadata = models.VideoMetadata(channel=channel, upload_date=None)
    return models.RunSummary(
        id=run_id,
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        title=f"영상 {run_id}",
        created_at="2026-09-20T14:02:11",
        answer_count=0,
        metadata=metadata,
        categories=categories,
    )


RUNS = (
    make_run(1, ("경제",), "슈카월드"),
    make_run(2, ("경제", "인공지능"), "안될공학"),
    make_run(3, ("인공지능",)),
    make_run(4, (), "슈카월드"),
)
"""카테고리·채널이 섞인 재료 넷. 3 은 채널이, 4 는 카테고리가 없다."""


def ids(runs: Sequence[models.RunSummary]) -> list[int]:
    """남은 재료의 ID 를 순서대로."""
    return [run.id for run in runs]


def test_empty_filters_keep_every_run() -> None:
    """비운 필터는 거르지 않는다."""
    assert ids(material_filter.filter_runs(RUNS, [], [])) == [1, 2, 3, 4]


def test_a_category_filter_keeps_runs_with_any_chosen_name() -> None:
    """고른 카테고리 중 하나라도 붙은 재료를 남긴다."""
    kept = material_filter.filter_runs(RUNS, ["인공지능", "정치"], [])

    assert ids(kept) == [2, 3]


def test_a_channel_filter_keeps_runs_on_a_chosen_channel() -> None:
    """고른 채널 중 하나의 재료를 남긴다."""
    assert ids(material_filter.filter_runs(RUNS, [], ["슈카월드"])) == [1, 4]


def test_both_filters_must_match() -> None:
    """두 필터를 함께 주면 둘 다 맞아야 남는다."""
    kept = material_filter.filter_runs(RUNS, ["경제"], ["안될공학"])

    assert ids(kept) == [2]


def test_a_run_without_categories_drops_out_of_a_category_filter() -> None:
    """카테고리가 없는 재료는 카테고리 필터가 있으면 빠진다."""
    kept = material_filter.filter_runs(RUNS, ["경제", "인공지능"], [])

    assert ids(kept) == [1, 2, 3]


def test_a_run_without_a_channel_drops_out_of_a_channel_filter() -> None:
    """채널이 없는 재료는 채널 필터가 있으면 빠진다."""
    kept = material_filter.filter_runs(RUNS, [], ["슈카월드", "안될공학"])

    assert ids(kept) == [1, 2, 4]


def test_filtering_keeps_the_given_order() -> None:
    """남은 재료는 받은 순서를 지킨다."""
    kept = material_filter.filter_runs(list(reversed(RUNS)), ["경제"], [])

    assert ids(kept) == [2, 1]


def test_category_options_collect_the_names_in_order() -> None:
    """후보들에 붙은 카테고리를 중복 없이 이름 순으로 모은다."""
    assert material_filter.category_options(RUNS) == ("경제", "인공지능")


def test_channel_options_skip_runs_without_a_channel() -> None:
    """후보들의 채널을 중복 없이 정렬해 모으고 빈 값은 뺀다."""
    assert material_filter.channel_options(RUNS) == ("슈카월드", "안될공학")
