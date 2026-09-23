"""신규 영상 판정 테스트."""

import datetime

import pytest

from notebooklm_st.core import models, new_videos

KST = datetime.timezone(datetime.timedelta(hours=9))


def entry(
    video_id: str, published: str, title: str = "영상"
) -> models.FeedEntry:
    """피드 항목 하나를 만든다. ``published`` 는 ISO 문자열이다."""
    return models.FeedEntry(
        video_id=video_id,
        title=title,
        published=datetime.datetime.fromisoformat(published),
    )


def test_keeps_an_entry_uploaded_after_the_baseline() -> None:
    """기준일보다 나중에 올라온 영상은 신규다."""
    entries = [entry("aaaaaaaaaaa", "2026-09-24T01:00:00+00:00")]

    picked = new_videos.select(entries, "2026-09-23", set(), KST)

    assert [item.video_id for item in picked] == ["aaaaaaaaaaa"]


def test_drops_an_entry_uploaded_before_the_baseline() -> None:
    """기준일보다 먼저 올라온 영상은 신규가 아니다."""
    entries = [entry("aaaaaaaaaaa", "2026-09-20T01:00:00+00:00")]

    assert new_videos.select(entries, "2026-09-23", set(), KST) == ()


def test_the_baseline_starts_at_midnight_in_the_given_zone() -> None:
    """기준일 00:00 은 주어진 타임존의 자정이다.

    KST 기준일 2026-09-23 의 시작은 UTC 2026-09-22T15:00 이다. 그
    직후에 올라온 영상은 한국 시각으로 그날 새벽이므로 신규다.
    """
    entries = [entry("aaaaaaaaaaa", "2026-09-22T15:30:00+00:00")]

    picked = new_videos.select(entries, "2026-09-23", set(), KST)

    assert [item.video_id for item in picked] == ["aaaaaaaaaaa"]


def test_an_entry_just_before_the_zone_midnight_is_dropped() -> None:
    """그 자정 직전에 올라온 것은 전날이라 신규가 아니다."""
    entries = [entry("aaaaaaaaaaa", "2026-09-22T14:30:00+00:00")]

    assert new_videos.select(entries, "2026-09-23", set(), KST) == ()


def test_drops_an_entry_already_summarized() -> None:
    """이미 요약한 영상은 빠진다."""
    entries = [entry("aaaaaaaaaaa", "2026-09-24T01:00:00+00:00")]

    picked = new_videos.select(entries, "2026-09-23", {"aaaaaaaaaaa"}, KST)

    assert picked == ()


def test_sorts_newest_first() -> None:
    """업로드가 늦은 것부터 나온다."""
    entries = [
        entry("aaaaaaaaaaa", "2026-09-24T01:00:00+00:00"),
        entry("ccccccccccc", "2026-09-26T01:00:00+00:00"),
        entry("bbbbbbbbbbb", "2026-09-25T01:00:00+00:00"),
    ]

    picked = new_videos.select(entries, "2026-09-23", set(), KST)

    assert [item.video_id for item in picked] == [
        "ccccccccccc",
        "bbbbbbbbbbb",
        "aaaaaaaaaaa",
    ]


def test_empty_entries_give_nothing() -> None:
    """항목이 없으면 빈 결과다."""
    assert new_videos.select([], "2026-09-23", set(), KST) == ()


def test_rejects_a_baseline_that_is_not_a_date() -> None:
    """기준일 형식이 아니면 예외다."""
    with pytest.raises(ValueError):
        new_videos.select([], "2026/09/23", set(), KST)
