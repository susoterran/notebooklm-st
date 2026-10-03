"""카테고리 저장소 테스트."""

import sqlite3
from collections.abc import Iterator

import pytest

from notebooklm_st.core import models
from notebooklm_st.services import categories, channels, run_history, store


@pytest.fixture
def connection(tmp_path) -> Iterator[sqlite3.Connection]:
    """임시 파일 DB 커넥션을 열고 테스트 후 닫는다."""
    conn = store.connect(tmp_path / "test.db")
    yield conn
    conn.close()


def use_on_run(connection: sqlite3.Connection, category_id: int) -> int:
    """실행 하나를 만들어 그 카테고리를 SQL 로 잇는다.

    Returns:
        만든 실행의 ID.
    """
    run_id = run_history.save_run(
        connection,
        models.RunResult(
            url="https://youtu.be/dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
            items=(),
        ),
    )
    connection.execute(
        "INSERT INTO run_categories (run_id, category_id) VALUES (?, ?)",
        (run_id, category_id),
    )
    connection.commit()
    return run_id


def use_on_channel(connection: sqlite3.Connection, category_id: int) -> int:
    """채널 하나를 등록해 그 카테고리를 SQL 로 기본값에 잇는다.

    Returns:
        만든 채널의 행 ID.
    """
    channel = channels.add_channel(
        connection,
        "UC" + "a" * 22,
        "채널",
        "https://www.youtube.com/@channel",
        "2026-09-01",
    )
    connection.execute(
        "INSERT INTO channel_categories (channel_pk, category_id)"
        " VALUES (?, ?)",
        (channel.id, category_id),
    )
    connection.commit()
    return channel.id


def names(connection: sqlite3.Connection) -> list[str]:
    """등록된 이름을 목록 순서로."""
    return [item.name for item in categories.list_categories(connection)]


def test_add_category_returns_the_cleaned_name(connection) -> None:
    """앞뒤 공백을 잘라 저장하고 저장한 카테고리를 돌려준다."""
    category = categories.add_category(connection, "  경제  ")

    assert category.name == "경제"
    assert categories.list_categories(connection) == [category]


def test_list_categories_is_ordered_by_name(connection) -> None:
    """목록은 등록 순서가 아니라 이름 순서다."""
    for name in ("인공지능", "경제", "AI"):
        categories.add_category(connection, name)

    assert names(connection) == ["AI", "경제", "인공지능"]


def test_add_category_rejects_a_duplicate_name(connection) -> None:
    """같은 이름은 두 번 등록하지 않는다."""
    categories.add_category(connection, "경제")

    with pytest.raises(ValueError, match="'경제' 카테고리가 이미 있습니다"):
        categories.add_category(connection, " 경제 ")
    assert names(connection) == ["경제"]


def test_add_category_rejects_an_invalid_name(connection) -> None:
    """이름 규칙에 맞지 않으면 저장하지 않는다."""
    with pytest.raises(ValueError, match="쓸 수 있습니다"):
        categories.add_category(connection, "경제,정책")
    assert names(connection) == []


def test_rename_category_changes_the_name(connection) -> None:
    """이름을 바꾸고 고친 시각을 새로 적는다."""
    category = categories.add_category(connection, "경제")
    connection.execute(
        "UPDATE categories SET updated_at = '2000-01-01T00:00:00'"
    )
    connection.commit()

    categories.rename_category(connection, category.id, "거시경제")

    [renamed] = categories.list_categories(connection)
    assert renamed.name == "거시경제"
    assert renamed.updated_at != "2000-01-01T00:00:00"


def test_rename_category_to_its_own_name_is_allowed(connection) -> None:
    """자기 이름 그대로 저장해도 중복으로 보지 않는다."""
    category = categories.add_category(connection, "경제")

    categories.rename_category(connection, category.id, "경제")

    assert names(connection) == ["경제"]


def test_rename_category_rejects_another_category_name(connection) -> None:
    """다른 카테고리가 쓰는 이름으로는 바꾸지 않는다."""
    categories.add_category(connection, "경제")
    other = categories.add_category(connection, "정치")

    with pytest.raises(ValueError, match="이미 있습니다"):
        categories.rename_category(connection, other.id, "경제")
    assert names(connection) == ["경제", "정치"]


def test_rename_category_rejects_an_unknown_id(connection) -> None:
    """없는 카테고리는 바꿀 수 없다."""
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        categories.rename_category(connection, 99, "경제")


def test_rename_category_refuses_one_used_by_a_run(connection) -> None:
    """이력에서 쓰는 카테고리는 이름을 바꾸지 않는다.

    이미 Outline 문서 머리에 적힌 이름과 어긋나기 때문이다.
    """
    category = categories.add_category(connection, "경제")
    use_on_run(connection, category.id)

    with pytest.raises(ValueError, match="이력에서 쓰는 카테고리"):
        categories.rename_category(connection, category.id, "거시경제")
    assert names(connection) == ["경제"]


def test_delete_category_removes_it(connection) -> None:
    """쓰지 않는 카테고리는 지운다."""
    category = categories.add_category(connection, "경제")

    categories.delete_category(connection, category.id)

    assert names(connection) == []


def test_delete_category_refuses_one_used_by_a_run(connection) -> None:
    """이력에서 쓰는 카테고리는 지우지 않는다."""
    category = categories.add_category(connection, "경제")
    use_on_run(connection, category.id)

    with pytest.raises(ValueError, match="이력에서 쓰는 카테고리"):
        categories.delete_category(connection, category.id)
    assert names(connection) == ["경제"]


def test_delete_category_used_only_by_a_channel(connection) -> None:
    """채널 기본값으로만 쓰이면 지울 수 있고, 그 연결도 사라진다."""
    category = categories.add_category(connection, "경제")
    use_on_channel(connection, category.id)

    categories.delete_category(connection, category.id)

    assert names(connection) == []
    row = connection.execute(
        "SELECT COUNT(*) AS n FROM channel_categories"
    ).fetchone()
    assert row["n"] == 0


def test_usage_counts_runs_and_channels(connection) -> None:
    """이 카테고리를 쓰는 이력 수와 채널 수를 센다."""
    category = categories.add_category(connection, "경제")
    unused = categories.add_category(connection, "정치")
    use_on_run(connection, category.id)
    use_on_run(connection, category.id)
    use_on_channel(connection, category.id)

    assert categories.usage(connection, category.id) == (
        categories.CategoryUsage(runs=2, channels=1)
    )
    assert categories.usage(connection, unused.id) == (
        categories.CategoryUsage(runs=0, channels=0)
    )


def test_ensure_adds_only_new_names(connection) -> None:
    """없는 이름만 넣고 새로 넣은 수를 돌려준다."""
    categories.add_category(connection, "경제")

    added = categories.ensure(connection, ["경제", "인공지능", "정치"])
    connection.commit()

    assert added == 2
    assert names(connection) == ["경제", "인공지능", "정치"]


def test_ensure_does_not_commit(connection) -> None:
    """트랜잭션은 호출자가 소유한다."""
    categories.ensure(connection, ["경제"])
    connection.rollback()

    assert names(connection) == []
