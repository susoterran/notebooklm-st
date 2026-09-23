"""채널 화면 테스트.

화면이 탭 셋으로 갈린다 — 새 영상 확인 · 채널 등록 · 등록된 채널.
``AppTest`` 는 탭을 넘어 모든 위젯을 한 목록으로 모으므로, 위젯은
탭이 아니라 **라벨**로 찾는다.

가짜를 끼우는 자리가 둘이다. 등록 시점의 피드 확인은
``pages.channels`` 가 부르고, 새 영상 확인은
``pages._channel_check`` 가 부른다. 어느 쪽을 막을지 테스트마다
명시한다.
"""

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
OTHER_CHANNEL_ID = "UC" + "z" * 22
HANDLE_URL = "https://www.youtube.com/@Fireship"


def script():
    """AppTest 진입점 — 채널 화면을 렌더한다."""
    from notebooklm_st.pages import channels as channels_page

    channels_page.render()


def button_by(app, label):
    """라벨로 버튼을 찾는다.

    인덱스로 찾으면 화면에 버튼이 하나 늘 때마다 이 파일의 테스트가
    통째로 깨진다.
    """
    return next(item for item in app.button if item.label == label)


def date_input_by(app, label):
    """라벨로 날짜 입력을 찾는다. 같은 이유로 인덱스를 쓰지 않는다."""
    return next(item for item in app.date_input if item.label == label)


def text_input_by(app, label):
    """라벨로 글자 입력을 찾는다.

    등록 탭의 채널 URL 과 목록 탭의 채널명이 같은 목록에 섞여 오므로
    인덱스로는 가릴 수 없다.
    """
    return next(item for item in app.text_input if item.label == label)


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


def registered(connection, title="Fireship", channel_id=CHANNEL_ID):
    """기준일이 지난 채널 하나를 등록한다."""
    return channels.add_channel(
        connection, channel_id, title, HANDLE_URL, "2026-09-01"
    )


def check_feed(monkeypatch, fetch):
    """새 영상 확인이 부르는 피드를 가짜로 바꾼다."""
    from notebooklm_st.pages import _channel_check

    monkeypatch.setattr(_channel_check.channel_feed, "fetch", fetch)


@pytest.fixture
def fake_sources(monkeypatch):
    """등록 경로의 해석과 피드 확인을 성공하는 가짜로 바꾼다."""
    from notebooklm_st.pages import channels as channels_page

    def lookup(url, **kwargs):
        """고정된 채널을 돌려준다."""
        return channel_lookup.LookupResult(
            channel_id=CHANNEL_ID,
            title="Fireship",
            url=f"https://www.youtube.com/channel/{CHANNEL_ID}",
            error=None,
        )

    monkeypatch.setattr(channels_page.channel_lookup, "lookup", lookup)
    monkeypatch.setattr(channels_page.channel_feed, "fetch", feed_with())


def test_no_channels_shows_a_notice(app_db) -> None:
    """등록된 채널이 없으면 등록 탭으로 안내한다."""
    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert any("채널 등록 탭" in item.value for item in app.info)


def test_registering_saves_the_channel(app_db, fake_sources) -> None:
    """URL 을 넣고 등록하면 채널이 저장된다."""
    app = v1.AppTest.from_function(script)
    app.run()
    text_input_by(app, "채널 URL").set_value(HANDLE_URL).run()
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
            channel_id=None, title=None, url=None, error="채널 URL 이 아닙니다."
        )

    monkeypatch.setattr(channels_page.channel_lookup, "lookup", lookup)

    app = v1.AppTest.from_function(script)
    app.run()
    text_input_by(app, "채널 URL").set_value("https://example.com").run()
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
            channel_id=CHANNEL_ID, title="Fireship", url=HANDLE_URL, error=None
        )

    monkeypatch.setattr(channels_page.channel_lookup, "lookup", lookup)
    monkeypatch.setattr(
        channels_page.channel_feed,
        "fetch",
        feed_with(error="이 채널에는 RSS 피드가 없습니다."),
    )

    app = v1.AppTest.from_function(script)
    app.run()
    text_input_by(app, "채널 URL").set_value(HANDLE_URL).run()
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
    text_input_by(app, "채널 URL").set_value(HANDLE_URL).run()
    button_by(app, "등록").click().run()

    assert any("이미 등록된" in item.value for item in app.error)
    assert len(channels.list_channels(app_db)) == 1


def test_registered_channels_are_listed(app_db) -> None:
    """등록된 채널이 목록에 나온다."""
    registered(app_db)

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    rendered = " ".join(item.value for item in app.markdown)
    assert "Fireship" in rendered


def test_the_channel_name_can_be_changed(app_db) -> None:
    """목록에서 채널명을 고칠 수 있다."""
    registered(app_db)

    app = v1.AppTest.from_function(script)
    app.run()
    text_input_by(app, "채널명").set_value("파이어십").run()
    button_by(app, "이름 저장").click().run()

    assert not app.exception
    assert channels.list_channels(app_db)[0].title == "파이어십"


def test_a_blank_channel_name_is_rejected(app_db) -> None:
    """공백뿐인 채널명은 저장하지 않고 사유를 보여 준다."""
    registered(app_db)

    app = v1.AppTest.from_function(script)
    app.run()
    text_input_by(app, "채널명").set_value("   ").run()
    button_by(app, "이름 저장").click().run()

    assert len(app.error) == 1
    assert channels.list_channels(app_db)[0].title == "Fireship"


def test_deleting_removes_the_channel(app_db) -> None:
    """목록에서 채널을 지울 수 있다."""
    registered(app_db)

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "삭제").click().run()

    assert not app.exception
    assert channels.list_channels(app_db) == []


def test_checking_lists_new_videos(app_db, monkeypatch) -> None:
    """확인을 누르면 신규 영상이 목록에 나온다."""
    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    check_feed(monkeypatch, feed_with(make_entry()))

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()

    assert not app.exception
    rendered = " ".join(item.value for item in app.markdown)
    assert "새 영상" in rendered


def test_an_already_summarized_video_is_not_listed(app_db, monkeypatch) -> None:
    """이미 요약한 영상은 신규로 뜨지 않는다."""
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
    check_feed(monkeypatch, feed_with(make_entry()))

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()

    assert any("새 영상이 없습니다" in item.value for item in app.info)


def test_only_the_selected_channel_is_checked(app_db, monkeypatch) -> None:
    """고른 채널의 피드만 읽는다. 등록된 나머지는 건드리지 않는다."""
    registered(app_db, title="가 채널")
    registered(app_db, title="나 채널", channel_id=OTHER_CHANNEL_ID)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    asked = []

    def fetch(channel_id, **kwargs):
        """어느 채널을 물었는지 기록한다."""
        asked.append(channel_id)
        return channel_feed.FeedResult((make_entry(),), None)

    check_feed(monkeypatch, fetch)
    second = channels.list_channels(app_db)[1]

    app = v1.AppTest.from_function(script)
    app.run()
    app.selectbox[0].set_value(second).run()
    button_by(app, "새 영상 확인").click().run()

    assert not app.exception
    assert asked == [OTHER_CHANNEL_ID]


def test_checking_saves_the_baseline_to_the_channel(
    app_db, monkeypatch
) -> None:
    """확인을 누르면 고른 기준일이 그 채널에 저장된다."""
    registered(app_db)
    check_feed(monkeypatch, feed_with())

    app = v1.AppTest.from_function(script)
    app.run()
    date_input_by(app, "이 채널의 기준일").set_value(
        datetime.date(2026, 9, 10)
    ).run()
    button_by(app, "새 영상 확인").click().run()

    assert not app.exception
    assert channels.list_channels(app_db)[0].baseline == "2026-09-10"


def test_switching_the_target_channel_clears_the_result(
    app_db, monkeypatch
) -> None:
    """대상 채널을 바꾸면 앞서 확인한 결과가 사라진다.

    다른 채널의 목록이 남아 있으면 무엇을 보고 있는지 알 수 없다.
    """
    registered(app_db, title="가 채널")
    registered(app_db, title="나 채널", channel_id=OTHER_CHANNEL_ID)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    check_feed(monkeypatch, feed_with(make_entry()))

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    assert "새 영상" in " ".join(item.value for item in app.markdown)

    second = channels.list_channels(app_db)[1]
    app.selectbox[0].set_value(second).run()

    assert not app.exception
    assert "새 영상" not in " ".join(item.value for item in app.markdown)


def test_a_feed_failure_on_the_target_shows_the_reason(
    app_db, monkeypatch
) -> None:
    """고른 채널의 피드가 실패하면 사유를 보여 준다."""
    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    check_feed(monkeypatch, feed_with(error="일시적인 오류입니다."))

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()

    assert not app.exception
    assert any("일시적인 오류" in item.value for item in app.error)


def test_no_questions_blocks_the_summary(app_db, monkeypatch) -> None:
    """질문이 없으면 요약 버튼을 그리지 않는다."""
    registered(app_db)
    check_feed(monkeypatch, feed_with(make_entry()))

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()

    assert any("질문 관리" in item.value for item in app.info)
    assert all(item.label != "요약" for item in app.button)


def test_summary_hands_the_video_to_the_runner(app_db, monkeypatch) -> None:
    """요약을 누르면 그 영상 URL 과 고른 질문이 러너로 넘어간다."""
    from notebooklm_st.pages import _channel_check

    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    check_feed(monkeypatch, feed_with(make_entry()))
    received: dict[str, object] = {}

    def fake_start(registry, url, question_list, db_path, **kwargs):
        """넘어온 인자를 기록한다."""
        received["url"] = url
        received["questions"] = [item.title for item in question_list]
        return None

    monkeypatch.setattr(_channel_check.runner, "start_run", fake_start)

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    app.multiselect[0].select(questions.list_questions(app_db)[0]).run()
    button_by(app, "요약").click().run()

    assert received["url"] == "https://www.youtube.com/watch?v=TbkUKCm3CHQ"
    assert received["questions"] == ["핵심 주장"]


def test_a_running_query_blocks_the_summary(app_db, monkeypatch) -> None:
    """질의가 돌고 있으면 요약을 시작할 수 없다."""
    from notebooklm_st import session

    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    check_feed(monkeypatch, feed_with(make_entry()))
    session.get_registry().create(
        "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", ("질문",)
    )

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    app.multiselect[0].select(questions.list_questions(app_db)[0]).run()

    assert button_by(app, "요약").disabled is True
    assert any("질의" in item.value for item in app.info)
