"""채널 화면 테스트."""

import datetime

import pytest
from streamlit.testing import v1

from notebooklm_st.core import models
from notebooklm_st.services import (
    channel_feed,
    channel_lookup,
    channels,
    questions,
    run_history,
)

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


def make_entry(video_id="TbkUKCm3CHQ", published="2026-09-25T01:00:00+00:00"):
    """피드 항목 하나를 만든다."""
    return models.FeedEntry(
        video_id=video_id,
        title="새 영상",
        published=datetime.datetime.fromisoformat(published),
    )


def feed_with(*entries, error=None):
    """준비된 피드를 돌려주는 가짜 fetch 를 만든다."""

    def fetch(channel_id, **kwargs):
        """채널 ID 를 무시하고 준비된 결과를 돌려준다."""
        return channel_feed.FeedResult(tuple(entries), error)

    return fetch


def registered(connection, title="Fireship"):
    """기준일이 지난 채널 하나를 등록한다."""
    return channels.add_channel(
        connection, CHANNEL_ID, title, HANDLE_URL, "2026-09-01"
    )


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


def test_checking_lists_new_videos(app_db, monkeypatch) -> None:
    """확인을 누르면 신규 영상이 목록에 나온다."""
    from notebooklm_st.pages import channels as channels_page

    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    monkeypatch.setattr(
        channels_page.channel_feed, "fetch", feed_with(make_entry())
    )

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()

    assert not app.exception
    rendered = " ".join(item.value for item in app.markdown)
    assert "새 영상" in rendered


def test_an_already_summarized_video_is_not_listed(app_db, monkeypatch) -> None:
    """이미 요약한 영상은 신규로 뜨지 않는다."""
    from notebooklm_st.pages import channels as channels_page

    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    run_history.save_run(
        app_db,
        models.RunResult(
            url="https://youtu.be/TbkUKCm3CHQ",
            video_id="TbkUKCm3CHQ",
            title="이미 한 것",
            items=(),
        ),
    )
    monkeypatch.setattr(
        channels_page.channel_feed, "fetch", feed_with(make_entry())
    )

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()

    assert any("새 영상이 없습니다" in item.value for item in app.info)


def test_a_channel_failure_does_not_stop_the_others(
    app_db, monkeypatch
) -> None:
    """채널 하나가 실패해도 나머지는 보인다."""
    from notebooklm_st.pages import channels as channels_page

    registered(app_db, title="되는 채널")
    channels.add_channel(
        app_db, "UC" + "z" * 22, "안 되는 채널", HANDLE_URL, "2026-09-01"
    )

    def fetch(channel_id, **kwargs):
        """한 채널만 실패시킨다."""
        if channel_id == CHANNEL_ID:
            return channel_feed.FeedResult((make_entry(),), None)
        return channel_feed.FeedResult((), "일시적인 오류입니다.")

    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    monkeypatch.setattr(channels_page.channel_feed, "fetch", fetch)

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()

    assert not app.exception
    rendered = " ".join(item.value for item in app.markdown)
    assert "새 영상" in rendered
    assert any("일시적인 오류" in item.value for item in app.error)


def test_no_questions_blocks_the_summary(app_db, monkeypatch) -> None:
    """질문이 없으면 요약 버튼을 그리지 않는다."""
    from notebooklm_st.pages import channels as channels_page

    registered(app_db)
    monkeypatch.setattr(
        channels_page.channel_feed, "fetch", feed_with(make_entry())
    )

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()

    assert any("질문 관리" in item.value for item in app.info)
    assert all(item.label != "요약" for item in app.button)


def test_summary_hands_the_video_to_the_runner(app_db, monkeypatch) -> None:
    """요약을 누르면 그 영상 URL 과 고른 질문이 러너로 넘어간다."""
    from notebooklm_st.pages import channels as channels_page

    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    monkeypatch.setattr(
        channels_page.channel_feed, "fetch", feed_with(make_entry())
    )
    received: dict[str, object] = {}

    def fake_start(registry, url, question_list, db_path, **kwargs):
        """넘어온 인자를 기록한다."""
        received["url"] = url
        received["questions"] = [item.title for item in question_list]
        return None

    monkeypatch.setattr(channels_page.runner, "start_run", fake_start)

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    app.multiselect[0].select(questions.list_questions(app_db)[0]).run()
    summary = next(item for item in app.button if item.label == "요약")
    summary.click().run()

    assert received["url"] == ("https://www.youtube.com/watch?v=TbkUKCm3CHQ")
    assert received["questions"] == ["핵심 주장"]


def test_a_running_query_blocks_the_summary(app_db, monkeypatch) -> None:
    """질의가 돌고 있으면 요약을 시작할 수 없다."""
    from notebooklm_st import session
    from notebooklm_st.pages import channels as channels_page

    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    monkeypatch.setattr(
        channels_page.channel_feed, "fetch", feed_with(make_entry())
    )
    session.get_registry().create(
        "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", ("질문",)
    )

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    app.multiselect[0].select(questions.list_questions(app_db)[0]).run()

    summary = next(item for item in app.button if item.label == "요약")
    assert summary.disabled is True
    assert any("질의" in item.value for item in app.info)
