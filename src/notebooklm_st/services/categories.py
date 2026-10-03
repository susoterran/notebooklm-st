"""카테고리 저장소.

연결과 스키마는 ``store`` 가 맡고, 이름 규칙은
``core.category_names`` 가 맡는다. 실행과 채널에 잇는 일은 그 행을
쓰는 저장소(``run_history``·``channels``)가 한다.

**이력에서 쓰는 카테고리는 이름을 바꾸거나 지우지 않는다.** 이미
Outline 문서 머리에 적힌 이름과 어긋나기 때문이다. 대기 중인 질의가
쥔 카테고리는 레지스트리를 아는 화면이 따로 막는다.
"""

import dataclasses
import sqlite3
from collections.abc import Sequence

from notebooklm_st.core import category_names, models
from notebooklm_st.services import store

_IN_USE = "이력에서 쓰는 카테고리는 이름을 바꾸거나 지울 수 없습니다."


@dataclasses.dataclass(frozen=True, slots=True)
class CategoryUsage:
    """카테고리 하나를 쓰는 곳의 수."""

    runs: int
    """이 카테고리가 붙은 이력 행 수."""

    channels: int
    """이 카테고리를 기본값으로 둔 채널 수."""


def list_categories(
    connection: sqlite3.Connection,
) -> list[models.Category]:
    """등록된 카테고리를 이름 순서로 돌려준다.

    SQLite 의 기본 비교는 바이트 순이고, UTF-8 에서는 코드 포인트
    순과 같다. ``category_names.ordered`` 와 같은 순서다.

    Args:
        connection: 열린 커넥션.

    Returns:
        카테고리 목록.
    """
    rows = connection.execute(
        "SELECT id, name, created_at, updated_at FROM categories ORDER BY name"
    ).fetchall()
    return [_to_category(row) for row in rows]


def add_category(connection: sqlite3.Connection, name: str) -> models.Category:
    """새 카테고리를 등록한다.

    Args:
        connection: 열린 커넥션.
        name: 이름. ``category_names.validate`` 로 다듬는다.

    Returns:
        저장된 카테고리.

    Raises:
        ValueError: 이름이 규칙에 맞지 않거나 같은 이름이 이미 있는
            경우.
    """
    cleaned = category_names.validate(name)
    _require_unique_name(connection, cleaned, None)
    now = store.now()
    row = connection.execute(
        "INSERT INTO categories (name, created_at, updated_at)"
        " VALUES (?, ?, ?)"
        " RETURNING id, name, created_at, updated_at",
        (cleaned, now, now),
    ).fetchone()
    connection.commit()
    return _to_category(row)


def rename_category(
    connection: sqlite3.Connection, category_id: int, name: str
) -> None:
    """카테고리의 이름을 바꾼다.

    Args:
        connection: 열린 커넥션.
        category_id: 바꿀 카테고리의 ID.
        name: 새 이름. ``category_names.validate`` 로 다듬는다.

    Raises:
        ValueError: 이름이 규칙에 맞지 않거나, 다른 카테고리가 그
            이름을 쓰거나, 이력에서 쓰는 카테고리이거나, 그 ID 의
            카테고리가 없는 경우.
    """
    cleaned = category_names.validate(name)
    if usage(connection, category_id).runs > 0:
        raise ValueError(_IN_USE)
    _require_unique_name(connection, cleaned, category_id)
    cursor = connection.execute(
        "UPDATE categories SET name = ?, updated_at = ? WHERE id = ?",
        (cleaned, store.now(), category_id),
    )
    connection.commit()
    if cursor.rowcount == 0:
        raise ValueError(f"카테고리 {category_id} 을 찾을 수 없습니다.")


def delete_category(connection: sqlite3.Connection, category_id: int) -> None:
    """카테고리를 지운다. 이미 없으면 조용히 넘어간다.

    채널 기본값으로 둔 연결은 외래키가 함께 지운다.

    Args:
        connection: 열린 커넥션.
        category_id: 지울 카테고리의 ID.

    Raises:
        ValueError: 이력에서 쓰는 카테고리인 경우.
    """
    if usage(connection, category_id).runs > 0:
        raise ValueError(_IN_USE)
    connection.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    connection.commit()


def usage(connection: sqlite3.Connection, category_id: int) -> CategoryUsage:
    """카테고리 하나를 쓰는 이력과 채널의 수를 센다.

    Args:
        connection: 열린 커넥션.
        category_id: 셀 카테고리의 ID.

    Returns:
        이력 행 수와 채널 수.
    """
    row = connection.execute(
        "SELECT"
        " (SELECT COUNT(*) FROM run_categories WHERE category_id = ?)"
        " AS runs,"
        " (SELECT COUNT(*) FROM channel_categories WHERE category_id = ?)"
        " AS channels",
        (category_id, category_id),
    ).fetchone()
    return CategoryUsage(runs=int(row["runs"]), channels=int(row["channels"]))


def ensure(connection: sqlite3.Connection, names: Sequence[str]) -> int:
    """없는 이름만 카테고리로 넣는다.

    **커밋하지 않는다.** 이력 동기화가 쓰며, 트랜잭션은
    ``history_sync.apply`` 가 소유한다. 이름은 문서에서 읽을 때 이미
    규칙을 통과했다(``outline_import.find_categories``).

    Args:
        connection: 열린 커넥션.
        names: 넣을 이름들.

    Returns:
        새로 넣은 수.
    """
    now = store.now()
    added = 0
    for name in names:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO categories (name, created_at, updated_at)"
            " VALUES (?, ?, ?)",
            (name, now, now),
        )
        added += cursor.rowcount
    return added


def _require_unique_name(
    connection: sqlite3.Connection, name: str, category_id: int | None
) -> None:
    """같은 이름의 다른 카테고리가 있으면 예외를 던진다.

    ``id IS NOT ?`` 는 NULL 안전 비교라, ``category_id`` 가 ``None``
    이면 모든 행과 견주고 값이 있으면 그 행만 뺀다(질문과 같다).

    Raises:
        ValueError: 같은 이름의 다른 카테고리가 이미 있는 경우.
    """
    row = connection.execute(
        "SELECT id FROM categories WHERE name = ? AND id IS NOT ? LIMIT 1",
        (name, category_id),
    ).fetchone()
    if row is not None:
        raise ValueError(f"'{name}' 카테고리가 이미 있습니다.")


def _to_category(row: sqlite3.Row) -> models.Category:
    """DB 행을 ``Category`` 로 바꾼다."""
    return models.Category(
        id=int(row["id"]),
        name=row["name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
