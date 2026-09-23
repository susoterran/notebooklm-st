"""채널 화면 테스트."""

import datetime

import pytest
from streamlit.testing import v1

from notebooklm_st.services import channel_feed, channel_lookup, channels

CHANNEL_ID = "UCsBjURrPoezykLs9EqgamOA"
HANDLE_URL = "https://www.youtube.com/@Fireship"


def script():
    """AppTest 진입점 — 채널 화면을 렌더한다."""
    from notebooklm_st.pages import channels as channels_page

    channels_page.render()


def button_by(app, label):
    """라벨로 버튼을 찾는다.

    인덱스로 찾으면 화면에 버튼이 하나 늘 때마다 이 파일의 테스트가
    통째로 깨진다(다음 태스크가 확인 버튼을 더한다).
    """
    return next(item for item in app.button if item.label == label)


def date_input_by(app, label):
    """라벨로 날짜 입력을 찾는다. 같은 이유로 인덱스를 쓰지 않는다."""
    return next(item for item in app.date_input if item.label == label)


@pytest.fixture
def fake_sources(monkeypatch):
    """해석과 피드를 성공하는 가짜로 바꾼다."""
    from notebooklm_st.pages import channels as channels_page

    def lookup(url, **kwargs):
        """고정된 채널을 돌려준다."""
        return channel_lookup.LookupResult(
            channel_id=CHANNEL_ID,
            title="Fireship",
            url=f"https://www.youtube.com/channel/{CHANNEL_ID}",
            error=None,
        )

    def fetch(channel_id, **kwargs):
        """빈 피드를 성공으로 돌려준다."""
        return channel_feed.FeedResult((), None)

    monkeypatch.setattr(channels_page.channel_lookup, "lookup", lookup)
    monkeypatch.setattr(channels_page.channel_feed, "fetch", fetch)


def test_no_channels_shows_a_notice(app_db) -> None:
    """등록된 채널이 없으면 안내를 보여 준다."""
    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert any("등록된 채널이 없습니다" in item.value for item in app.info)


def test_registering_saves_the_channel(app_db, fake_sources) -> None:
    """URL 을 넣고 등록하면 채널이 저장된다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value(HANDLE_URL).run()
    button_by(app, "등록").click().run()

    assert not app.exception
    saved = channels.list_channels(app_db)
    assert [item.channel_id for item in saved] == [CHANNEL_ID]
    assert saved[0].title == "Fireship"


def test_a_lookup_failure_shows_the_reason(app_db, monkeypatch) -> None:
    """해석이 실패하면 사유를 보여 주고 저장하지 않는다."""
    from notebooklm_st.pages import channels as channels_page

    def lookup(url, **kwargs):
        """실패를 돌려준다."""
        return channel_lookup.LookupResult(
            channel_id=None,
            title=None,
            url=None,
            error="채널 URL 이 아닙니다.",
        )

    monkeypatch.setattr(channels_page.channel_lookup, "lookup", lookup)

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value("https://example.com").run()
    button_by(app, "등록").click().run()

    assert any("채널 URL 이 아닙니다" in item.value for item in app.error)
    assert channels.list_channels(app_db) == []


def test_a_feed_failure_blocks_registration(app_db, monkeypatch) -> None:
    """피드가 없는 채널은 등록하지 않는다.

    매 확인마다 실패할 채널을 등록해 두지 않는다.
    """
    from notebooklm_st.pages import channels as channels_page

    def lookup(url, **kwargs):
        """성공을 돌려준다."""
        return channel_lookup.LookupResult(
            channel_id=CHANNEL_ID,
            title="Fireship",
            url=HANDLE_URL,
            error=None,
        )

    def fetch(channel_id, **kwargs):
        """피드 없음을 돌려준다."""
        return channel_feed.FeedResult((), "이 채널에는 RSS 피드가 없습니다.")

    monkeypatch.setattr(channels_page.channel_lookup, "lookup", lookup)
    monkeypatch.setattr(channels_page.channel_feed, "fetch", fetch)

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value(HANDLE_URL).run()
    button_by(app, "등록").click().run()

    assert any("피드가 없습니다" in item.value for item in app.error)
    assert channels.list_channels(app_db) == []


def test_a_duplicate_channel_shows_the_reason(app_db, fake_sources) -> None:
    """이미 등록된 채널은 사유를 보여 준다."""
    channels.add_channel(
        app_db, CHANNEL_ID, "Fireship", HANDLE_URL, "2026-09-23"
    )

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value(HANDLE_URL).run()
    button_by(app, "등록").click().run()

    assert any("이미 등록된" in item.value for item in app.error)
    assert len(channels.list_channels(app_db)) == 1


def test_registered_channels_are_listed(app_db) -> None:
    """등록된 채널이 목록에 나온다."""
    channels.add_channel(
        app_db, CHANNEL_ID, "Fireship", HANDLE_URL, "2026-09-23"
    )

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    rendered = " ".join(item.value for item in app.markdown)
    assert "Fireship" in rendered


def test_the_baseline_can_be_changed(app_db) -> None:
    """목록에서 기준일을 고칠 수 있다."""
    saved = channels.add_channel(
        app_db, CHANNEL_ID, "Fireship", HANDLE_URL, "2026-09-23"
    )

    app = v1.AppTest.from_function(script)
    app.run()
    date_input_by(app, "이 채널의 기준일").set_value(
        datetime.date(2026, 1, 1)
    ).run()
    button_by(app, "기준일 저장").click().run()

    assert not app.exception
    assert channels.list_channels(app_db)[0].baseline == "2026-01-01"
    assert saved.baseline == "2026-09-23"


def test_deleting_removes_the_channel(app_db) -> None:
    """목록에서 채널을 지울 수 있다."""
    channels.add_channel(
        app_db, CHANNEL_ID, "Fireship", HANDLE_URL, "2026-09-23"
    )

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "삭제").click().run()

    assert not app.exception
    assert channels.list_channels(app_db) == []
