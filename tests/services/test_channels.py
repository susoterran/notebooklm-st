"""구독 채널 저장소 테스트."""

import pytest

from notebooklm_st.services import categories, channels, store


@pytest.fixture
def connection(tmp_path):
    """임시 DB에 연결한 커넥션을 제공한다."""
    conn = store.connect(tmp_path / "test.db")
    yield conn
    conn.close()


def add(
    connection, channel_id="UC" + "a" * 22, title="어떤 채널", category_ids=()
):
    """테스트용 채널 하나를 등록한다."""
    return channels.add_channel(
        connection,
        channel_id,
        title,
        f"https://www.youtube.com/channel/{channel_id}",
        "2026-09-23",
        category_ids=category_ids,
    )


def test_new_database_has_no_channels(connection) -> None:
    """새 DB 는 채널이 없다."""
    assert channels.list_channels(connection) == []


def test_add_channel_returns_the_saved_row(connection) -> None:
    """등록한 채널이 그대로 저장되어 돌아온다."""
    saved = add(connection)

    assert saved.id > 0
    assert saved.channel_id == "UC" + "a" * 22
    assert saved.title == "어떤 채널"
    assert saved.baseline == "2026-09-23"
    assert saved.created_at


def test_channels_are_listed_by_title(connection) -> None:
    """목록은 이름순이다."""
    add(connection, channel_id="UC" + "b" * 22, title="나중 채널")
    add(connection, channel_id="UC" + "a" * 22, title="가장 먼저")

    titles = [item.title for item in channels.list_channels(connection)]

    assert titles == ["가장 먼저", "나중 채널"]


def test_the_same_channel_cannot_be_registered_twice(
    connection,
) -> None:
    """같은 채널 ID 는 한 번만 등록된다."""
    add(connection)

    with pytest.raises(ValueError) as error:
        add(connection, title="다른 이름")

    assert "이미 등록된" in str(error.value)


def test_blank_values_are_rejected(connection) -> None:
    """빈 값은 저장하지 않는다."""
    with pytest.raises(ValueError):
        channels.add_channel(
            connection,
            "  ",
            "이름",
            "https://example.com",
            "2026-09-23",
        )


def test_a_malformed_baseline_is_rejected(connection) -> None:
    """기준일 형식이 아니면 저장하지 않는다."""
    with pytest.raises(ValueError):
        channels.add_channel(
            connection,
            "UC" + "a" * 22,
            "이름",
            "https://example.com",
            "2026/09/23",
        )


def test_update_baseline_changes_the_date(connection) -> None:
    """기준일을 고칠 수 있다."""
    saved = add(connection)

    channels.update_baseline(connection, saved.id, "2026-01-01")

    assert channels.list_channels(connection)[0].baseline == "2026-01-01"


def test_update_baseline_rejects_an_unknown_channel(
    connection,
) -> None:
    """없는 채널의 기준일은 고칠 수 없다."""
    with pytest.raises(ValueError):
        channels.update_baseline(connection, 999, "2026-01-01")


def test_delete_channel_removes_it(connection) -> None:
    """지우면 목록에서 사라진다."""
    saved = add(connection)

    channels.delete_channel(connection, saved.id)

    assert channels.list_channels(connection) == []


def test_deleting_a_missing_channel_is_quiet(connection) -> None:
    """이미 없는 채널을 지워도 예외가 아니다."""
    channels.delete_channel(connection, 999)


def test_update_title_changes_the_name(connection) -> None:
    """채널명을 고칠 수 있다."""
    saved = add(connection)

    channels.update_title(connection, saved.id, "새 이름")

    assert channels.list_channels(connection)[0].title == "새 이름"


def test_update_title_trims_surrounding_space(connection) -> None:
    """앞뒤 공백은 지우고 저장한다."""
    saved = add(connection)

    channels.update_title(connection, saved.id, "  새 이름  ")

    assert channels.list_channels(connection)[0].title == "새 이름"


def test_update_title_rejects_a_blank_name(connection) -> None:
    """공백뿐인 채널명은 저장하지 않는다."""
    saved = add(connection)

    with pytest.raises(ValueError):
        channels.update_title(connection, saved.id, "   ")

    assert channels.list_channels(connection)[0].title == "어떤 채널"


def test_update_title_rejects_an_unknown_channel(connection) -> None:
    """없는 채널의 이름은 고칠 수 없다."""
    with pytest.raises(ValueError):
        channels.update_title(connection, 999, "새 이름")


def category_ids(connection, *names: str) -> list[int]:
    """카테고리를 등록하고 ID 를 넘긴 순서대로 돌려준다."""
    return [categories.add_category(connection, name).id for name in names]


def test_a_channel_has_no_default_categories_at_first(connection) -> None:
    """기본 카테고리 없이 등록하면 비어 있다."""
    channel = add(connection)

    assert channels.default_category_ids(connection, channel.id) == ()


def test_add_channel_saves_the_default_categories(connection) -> None:
    """등록할 때 준 기본 카테고리를 ID 순으로 돌려준다."""
    ids = category_ids(connection, "경제", "정치")

    channel = add(connection, category_ids=list(reversed(ids)))

    assert channels.default_category_ids(connection, channel.id) == tuple(ids)


def test_add_channel_skips_an_unknown_category(connection) -> None:
    """없는 카테고리 ID 는 조용히 뺀다."""
    [known] = category_ids(connection, "경제")

    channel = add(connection, category_ids=[known, 999])

    assert channels.default_category_ids(connection, channel.id) == (known,)


def test_set_default_categories_replaces_them(connection) -> None:
    """기본 카테고리를 통째로 바꾼다."""
    first, second = category_ids(connection, "경제", "정치")
    channel = add(connection, category_ids=[first])

    channels.set_default_categories(connection, channel.id, [second])

    assert channels.default_category_ids(connection, channel.id) == (second,)


def test_set_default_categories_can_clear_them(connection) -> None:
    """빈 목록을 주면 기본 카테고리가 없어진다."""
    [first] = category_ids(connection, "경제")
    channel = add(connection, category_ids=[first])

    channels.set_default_categories(connection, channel.id, [])

    assert channels.default_category_ids(connection, channel.id) == ()


def test_set_default_categories_rejects_an_unknown_channel(
    connection,
) -> None:
    """없는 채널이면 거부한다."""
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        channels.set_default_categories(connection, 99, [])
