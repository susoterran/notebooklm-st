"""채널 RSS 피드 읽기 테스트 — 실제 네트워크를 타지 않는다."""

import datetime

import httpx

from notebooklm_st.services import channel_feed

CHANNEL_ID = "UCsBjURrPoezykLs9EqgamOA"

FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Fireship</title>
  <entry>
    <yt:videoId>TbkUKCm3CHQ</yt:videoId>
    <title>첫 영상</title>
    <published>2026-09-21T17:52:29+00:00</published>
  </entry>
  <entry>
    <yt:videoId>LoLYw--s-5w</yt:videoId>
    <title>둘째 영상</title>
    <published>2026-09-17T20:33:55+00:00</published>
  </entry>
</feed>
"""


def responder(status=200, text=FEED_XML):
    """고정 응답을 돌려주는 가짜 getter 를 만든다."""

    def getter(url, **kwargs):
        """호출을 기록하지 않고 준비된 응답만 돌려준다."""
        return httpx.Response(status, text=text)

    return getter


def test_entries_come_back_with_id_title_and_time():
    """항목마다 ID·제목·시각을 읽는다."""
    result = channel_feed.fetch(CHANNEL_ID, getter=responder())

    assert result.error is None
    assert [item.video_id for item in result.entries] == [
        "TbkUKCm3CHQ",
        "LoLYw--s-5w",
    ]
    assert result.entries[0].title == "첫 영상"
    assert result.entries[0].published == datetime.datetime(
        2026, 9, 21, 17, 52, 29, tzinfo=datetime.UTC
    )


def test_the_channel_id_goes_into_the_query():
    """채널 ID 를 질의 파라미터로 넘긴다."""
    seen = {}

    def getter(url, **kwargs):
        """넘어온 URL 과 파라미터를 기록한다."""
        seen["url"] = url
        seen["params"] = kwargs.get("params")
        return httpx.Response(200, text=FEED_XML)

    channel_feed.fetch(CHANNEL_ID, getter=getter)

    assert seen["url"] == channel_feed.FEED_URL
    assert seen["params"] == {"channel_id": CHANNEL_ID}


def test_missing_feed_says_the_channel_has_none():
    """404 는 피드가 없는 채널이라고 말한다."""
    result = channel_feed.fetch(CHANNEL_ID, getter=responder(status=404))

    assert result.entries == ()
    assert "피드가 없습니다" in (result.error or "")


def test_server_error_asks_to_retry():
    """5xx 는 다시 시도하라고 말한다.

    실측에서 같은 URL 이 500 과 404 를 번갈아 냈다. 둘을 한 문구로
    묶으면 멀쩡한 채널을 포기하게 된다.
    """
    result = channel_feed.fetch(CHANNEL_ID, getter=responder(status=503))

    assert "다시 시도" in (result.error or "")


def test_other_status_is_reported_with_the_code():
    """그 밖의 상태는 코드를 그대로 알린다."""
    result = channel_feed.fetch(CHANNEL_ID, getter=responder(status=418))

    assert "418" in (result.error or "")


def test_broken_xml_is_reported():
    """XML 이 깨졌으면 사유를 돌려준다."""
    result = channel_feed.fetch(CHANNEL_ID, getter=responder(text="<feed"))

    assert result.entries == ()
    assert "해석하지 못했습니다" in (result.error or "")


def test_an_empty_feed_is_a_success():
    """항목이 없는 피드는 성공이다.

    아직 영상을 올리지 않은 채널도 등록할 수 있어야 한다.
    """
    empty = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom"><title>빈 채널</title>'
        "</feed>"
    )

    result = channel_feed.fetch(CHANNEL_ID, getter=responder(text=empty))

    assert result.entries == ()
    assert result.error is None


def test_an_entry_missing_a_field_is_skipped():
    """필드가 빠진 항목만 건너뛰고 나머지는 살린다."""
    partial = FEED_XML.replace("<yt:videoId>LoLYw--s-5w</yt:videoId>", "")

    result = channel_feed.fetch(CHANNEL_ID, getter=responder(text=partial))

    assert [item.video_id for item in result.entries] == ["TbkUKCm3CHQ"]
    assert result.error is None


def test_a_naive_timestamp_is_skipped():
    """타임존이 없는 시각은 건너뛴다.

    naive 와 aware 를 섞어 비교하면 TypeError 가 난다.
    """
    naive = FEED_XML.replace("2026-09-21T17:52:29+00:00", "2026-09-21T17:52:29")

    result = channel_feed.fetch(CHANNEL_ID, getter=responder(text=naive))

    assert [item.video_id for item in result.entries] == ["LoLYw--s-5w"]


def test_a_huge_feed_is_refused():
    """상한을 넘는 본문은 파싱하지 않는다."""
    huge = "<feed>" + "a" * (channel_feed.MAX_FEED_BYTES + 1) + "</feed>"

    result = channel_feed.fetch(CHANNEL_ID, getter=responder(text=huge))

    assert result.entries == ()
    assert "너무 큽니다" in (result.error or "")


def test_a_transport_error_is_reported():
    """요청 자체가 실패하면 사유를 돌려준다."""

    def getter(url, **kwargs):
        """연결 실패를 만든다."""
        raise httpx.ConnectError("연결 실패")

    result = channel_feed.fetch(CHANNEL_ID, getter=getter)

    assert result.entries == ()
    assert "가져오지 못했습니다" in (result.error or "")
