"""새 영상을 고르는 순수 함수.

피드에서 온 항목과 기준일과 이미 요약한 영상 ID 를 받아 거르고
정렬한다. 네트워크도 DB 도 Streamlit 도 모른다 — 그래서 경계 조건을
가짜 없이 테스트할 수 있다.
"""

import datetime
from collections.abc import Container, Sequence

from notebooklm_st.core import models


def select(
    entries: Sequence[models.FeedEntry],
    baseline: str,
    known_ids: Container[str],
    tz: datetime.tzinfo | None = None,
) -> tuple[models.FeedEntry, ...]:
    """기준일 이후 올라왔고 아직 요약하지 않은 항목만 고른다.

    Args:
        entries: 채널 피드에서 온 항목들.
        baseline: ``YYYY-MM-DD`` 형식의 기준일. 저장소가 형식을
            보장한다(→ ``services.channels``).
        known_ids: 이미 요약한 영상 ID 들.
        tz: 기준일을 읽을 타임존. ``None`` 이면 시스템 로컬을 쓴다 —
            컨테이너는 ``TZ=Asia/Seoul`` 로 돈다.

    Returns:
        업로드가 늦은 것부터 정렬한 항목들.

    Raises:
        ValueError: ``baseline`` 이 날짜로 읽히지 않는 경우.
    """
    start = _start_of_day(baseline, tz)
    picked = [
        item
        for item in entries
        if item.published >= start and item.video_id not in known_ids
    ]
    picked.sort(key=lambda item: item.published, reverse=True)
    return tuple(picked)


def _start_of_day(
    baseline: str, tz: datetime.tzinfo | None
) -> datetime.datetime:
    """기준일의 자정을 타임존이 붙은 시각으로 만든다.

    피드는 UTC 로 오고 사람은 로컬 날짜로 생각한다. naive 로
    비교하면 그 차이만큼 경계가 밀려, 한국 시각 새벽에 올라온 영상이
    하루 어긋나 잡힌다. 문자열을 자르는 비교도 같은 이유로 쓰지
    않는다.

    Args:
        baseline: ``YYYY-MM-DD`` 형식의 기준일.
        tz: 읽을 타임존. ``None`` 이면 시스템 로컬.

    Returns:
        타임존이 붙은 그날 00:00.

    Raises:
        ValueError: 날짜로 읽히지 않는 경우.
    """
    day = datetime.date.fromisoformat(baseline)
    naive = datetime.datetime.combine(day, datetime.time())
    if tz is None:
        # naive.astimezone() 은 시스템 로컬로 읽어 aware 로 바꾼다.
        return naive.astimezone()
    return naive.replace(tzinfo=tz)
