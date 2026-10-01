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
    outline,
    questions,
    run_history,
    settings,
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

    monkeypatch.setattr(_channel_check.runner, "enqueue", fake_start)

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    app.multiselect[0].select(questions.list_questions(app_db)[0]).run()
    button_by(app, "요약").click().run()

    assert received["url"] == "https://www.youtube.com/watch?v=TbkUKCm3CHQ"
    assert received["questions"] == ["핵심 주장"]


def test_summary_never_auto_saves(app_db, monkeypatch) -> None:
    """자동 저장을 켜 두어도 채널 화면의 요약은 사람이 저장한다."""
    from notebooklm_st.pages import _channel_check

    monkeypatch.setenv(outline.URL_ENV_VAR, "http://192.168.0.10:3000")
    monkeypatch.setenv(outline.TOKEN_ENV_VAR, "ol_secret")
    monkeypatch.setenv(outline.COLLECTION_ENV_VAR, "col-1")
    settings.set_auto_save(app_db, True)
    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    check_feed(monkeypatch, feed_with(make_entry()))
    calls: list[dict[str, object]] = []

    def fake_start(registry, url, question_list, db_path, **kwargs):
        """넘어온 키워드 인자를 기록한다."""
        calls.append(kwargs)

    monkeypatch.setattr(_channel_check.runner, "enqueue", fake_start)

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    app.multiselect[0].select(questions.list_questions(app_db)[0]).run()
    button_by(app, "요약").click().run()

    assert len(calls) == 1
    assert calls[0]["auto_save"] is False


def test_a_queued_query_blocks_the_summary(app_db, monkeypatch) -> None:
    """채널 화면의 요약은 대기열을 기다리지 않고 비어 있을 때만 연다."""
    from notebooklm_st import session

    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    check_feed(monkeypatch, feed_with(make_entry()))
    session.get_registry().enqueue(
        "https://youtu.be/dQw4w9WgXcQ",
        "dQw4w9WgXcQ",
        tuple(questions.list_questions(app_db)),
    )

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    app.multiselect[0].select(questions.list_questions(app_db)[0]).run()

    assert button_by(app, "요약").disabled is True
    assert any("대기 중인 질의" in item.value for item in app.info)


def test_a_paused_queue_blocks_the_summary(app_db, monkeypatch) -> None:
    """멈춘 대기열에 넣으면 돌지 않으므로 재개나 취소를 먼저 권한다."""
    from notebooklm_st import session

    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    check_feed(monkeypatch, feed_with(make_entry()))
    registry = session.get_registry()
    registry.enqueue(
        "https://youtu.be/dQw4w9WgXcQ",
        "dQw4w9WgXcQ",
        tuple(questions.list_questions(app_db)),
    )
    registry.pause("요청 한도를 초과했습니다.")

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    app.multiselect[0].select(questions.list_questions(app_db)[0]).run()

    assert button_by(app, "요약").disabled is True
    assert [item.value for item in app.info] == [
        "대기열이 멈춰 있습니다. 실행 현황에서 재개하거나 대기 항목을"
        " 취소한 뒤 시작하세요."
    ]


def test_a_running_query_blocks_the_summary(app_db, monkeypatch) -> None:
    """질의가 돌고 있으면 요약을 시작할 수 없다."""
    from notebooklm_st import session

    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    check_feed(monkeypatch, feed_with(make_entry()))
    registry = session.get_registry()
    registry.enqueue(
        "https://youtu.be/dQw4w9WgXcQ",
        "dQw4w9WgXcQ",
        tuple(questions.list_questions(app_db)),
    )
    registry.acquire_worker()
    registry.claim_next()

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    app.multiselect[0].select(questions.list_questions(app_db)[0]).run()

    assert button_by(app, "요약").disabled is True
    assert any("질의" in item.value for item in app.info)


def run_handle(video_id, status):
    """상태 칸을 시험할 실행 핸들 하나를 만든다."""
    from notebooklm_st.services import runs

    return runs.RunHandle(
        run_id=f"run-{video_id}-{status}",
        url=f"https://www.youtube.com/watch?v={video_id}",
        video_id=video_id,
        questions=(),
        auto_save=False,
        queued_at="2026-10-01T10:00:00",
        started_at=None,
        status=status,
        progress=[],
        result=None,
        save=None,
        error_message=None,
        error_level=None,
        finished_at=None,
    )


def test_status_label_names_each_state() -> None:
    """실행 상태 넷을 표에 적을 말로 옮기고, 실행이 없으면 비운다."""
    from notebooklm_st.pages import _channel_videos

    labels = [
        _channel_videos.status_label(
            "TbkUKCm3CHQ", [run_handle("TbkUKCm3CHQ", s)]
        )
        for s in ("queued", "running", "done", "failed")
    ]

    assert labels == ["대기 중", "실행 중", "끝남", "실패"]
    assert _channel_videos.status_label("TbkUKCm3CHQ", []) is None
    assert (
        _channel_videos.status_label(
            "TbkUKCm3CHQ", [run_handle("aaaaaaaaaaa", "queued")]
        )
        is None
    )


def test_status_label_takes_the_first_handle_of_the_video() -> None:
    """같은 영상의 실행이 여럿이면 목록에서 처음 만난 것을 쓴다.

    ``list_all`` 은 진행 중 → 대기 → 최근 끝난 순서다. 다시 넣어 도는
    영상이 지난 실패 때문에 "실패" 로 보이면 안 된다.
    """
    from notebooklm_st.pages import _channel_videos

    handles = [
        run_handle("TbkUKCm3CHQ", "running"),
        run_handle("TbkUKCm3CHQ", "failed"),
    ]

    assert _channel_videos.status_label("TbkUKCm3CHQ", handles) == "실행 중"


def test_widget_key_follows_the_list_and_the_generation() -> None:
    """같은 목록·같은 넣기 횟수는 같은 key, 하나라도 바뀌면 다른 key."""
    from notebooklm_st.pages import _channel_videos

    first = (make_entry("aaaaaaaaaaa"), make_entry("bbbbbbbbbbb"))
    other = (make_entry("aaaaaaaaaaa"),)

    key = _channel_videos.widget_key(first, 0)

    assert key == _channel_videos.widget_key(first, 0)
    assert key.startswith("channels_videos_")
    assert key != _channel_videos.widget_key(first, 1)
    assert key != _channel_videos.widget_key(other, 0)


def test_selected_entries_keep_the_list_order() -> None:
    """고른 행은 누른 순서가 아니라 목록 순서로, 낡은 번호는 버린다."""
    from notebooklm_st.pages import _channel_videos

    entries = (
        make_entry("aaaaaaaaaaa"),
        make_entry("bbbbbbbbbbb"),
        make_entry("ccccccccccc"),
    )

    picked = _channel_videos.selected_entries(entries, [2, 0, 9])

    assert [entry.video_id for entry in picked] == [
        "aaaaaaaaaaa",
        "ccccccccccc",
    ]


def video_table():
    """AppTest 진입점 — 신규 영상 둘로 표를 그리고 고른 것을 적는다."""
    import datetime

    import streamlit as st

    from notebooklm_st.core import models
    from notebooklm_st.pages import _channel_videos

    entries = (
        models.FeedEntry(
            video_id="aaaaaaaaaaa",
            title="둘째 영상",
            published=datetime.datetime.fromisoformat(
                "2026-09-26T01:00:00+00:00"
            ),
        ),
        models.FeedEntry(
            video_id="bbbbbbbbbbb",
            title="첫째 영상",
            published=datetime.datetime.fromisoformat(
                "2026-09-25T01:00:00+00:00"
            ),
        ),
    )
    key = _channel_videos.widget_key(entries, 0)
    picked = _channel_videos.render(entries, [], key)
    st.markdown("고른 영상: " + ",".join(e.video_id for e in picked))


def test_video_table_shows_the_entries(app_db) -> None:
    """표 하나에 제목·업로드일·상태·영상 링크가 목록 순서로 나온다."""
    app = v1.AppTest.from_function(video_table).run()

    assert not app.exception
    table = app.dataframe[0].value
    assert list(table.columns) == ["title", "published", "status", "url"]
    assert list(table["title"]) == ["둘째 영상", "첫째 영상"]
    local = [
        datetime.datetime.fromisoformat(value).astimezone()
        for value in ("2026-09-26T01:00:00+00:00", "2026-09-25T01:00:00+00:00")
    ]
    assert list(table["published"]) == [
        f"{moment:%Y-%m-%d %H:%M}" for moment in local
    ]
    assert table["status"].isna().all()
    assert list(table["url"]) == [
        "https://www.youtube.com/watch?v=aaaaaaaaaaa",
        "https://www.youtube.com/watch?v=bbbbbbbbbbb",
    ]
    assert app.caption[0].value == "행 왼쪽 칸을 눌러 고릅니다."


def test_video_table_returns_the_picked_entries(app_db) -> None:
    """표에서 고른 행의 영상을 목록 순서로 돌려준다."""
    from notebooklm_st.pages import _channel_videos

    app = v1.AppTest.from_function(video_table).run()
    entries = (make_entry("aaaaaaaaaaa"), make_entry("bbbbbbbbbbb"))
    app.session_state[_channel_videos.widget_key(entries, 0)] = {
        "selection": {"rows": [1, 0], "columns": [], "cells": []}
    }
    app.run()

    assert not app.exception
    assert "고른 영상: aaaaaaaaaaa,bbbbbbbbbbb" in [
        item.value for item in app.markdown
    ]
