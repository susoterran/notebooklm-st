"""구독 채널 저장소.

연결과 스키마는 ``store`` 가 맡는다. ``questions`` 와 같은 모양이다 —
SQLite 만 알고 네트워크도 Streamlit 도 모른다.
"""

import datetime
import sqlite3

from notebooklm_st.core import models
from notebooklm_st.services import store

_COLUMNS = "id, channel_id, title, url, baseline, created_at"

_BASELINE_LENGTH = len("2026-09-23")


def list_channels(
    connection: sqlite3.Connection,
) -> list[models.Channel]:
    """등록된 채널을 이름순으로 돌려준다.

    등록 순서가 아니라 이름순이다. 채널은 이름으로 찾는다.

    Args:
        connection: 열린 커넥션.

    Returns:
        채널 목록.
    """
    rows = connection.execute(
        f"SELECT {_COLUMNS} FROM channels ORDER BY title"
    ).fetchall()
    return [_to_channel(row) for row in rows]


def add_channel(
    connection: sqlite3.Connection,
    channel_id: str,
    title: str,
    url: str,
    baseline: str,
) -> models.Channel:
    """채널을 등록한다.

    Args:
        connection: 열린 커넥션.
        channel_id: ``UC`` 로 시작하는 채널 ID. 중복을 허용하지
            않는다.
        title: 화면에 보여 줄 채널명.
        url: 사람이 누를 채널 주소.
        baseline: ``YYYY-MM-DD`` 형식의 기준일.

    Returns:
        저장된 채널.

    Raises:
        ValueError: 값이 공백뿐이거나, 기준일이 형식에 맞지 않거나,
            같은 채널이 이미 등록된 경우.
    """
    values = {
        "채널 ID": channel_id.strip(),
        "채널명": title.strip(),
        "채널 URL": url.strip(),
    }
    for subject, value in values.items():
        if not value:
            raise ValueError(f"{subject} 값이 비어 있습니다.")
    checked = _require_date(baseline)
    if _exists(connection, values["채널 ID"]):
        raise ValueError("이미 등록된 채널입니다.")
    row = connection.execute(
        "INSERT INTO channels"
        " (channel_id, title, url, baseline, created_at)"
        " VALUES (?, ?, ?, ?, ?)"
        f" RETURNING {_COLUMNS}",
        (
            values["채널 ID"],
            values["채널명"],
            values["채널 URL"],
            checked,
            store.now(),
        ),
    ).fetchone()
    connection.commit()
    return _to_channel(row)


def update_baseline(
    connection: sqlite3.Connection, channel_pk: int, baseline: str
) -> None:
    """채널의 기준일을 바꾼다.

    Args:
        connection: 열린 커넥션.
        channel_pk: 바꿀 채널의 행 ID.
        baseline: ``YYYY-MM-DD`` 형식의 새 기준일.

    Raises:
        ValueError: 기준일이 형식에 맞지 않거나 그 채널이 없는 경우.
    """
    checked = _require_date(baseline)
    cursor = connection.execute(
        "UPDATE channels SET baseline = ? WHERE id = ?",
        (checked, channel_pk),
    )
    connection.commit()
    if cursor.rowcount == 0:
        raise ValueError(f"채널 {channel_pk} 을 찾을 수 없습니다.")


def delete_channel(connection: sqlite3.Connection, channel_pk: int) -> None:
    """채널을 지운다. 이미 없으면 조용히 넘어간다.

    이미 만든 요약본과 실행 이력은 그대로 남는다.

    Args:
        connection: 열린 커넥션.
        channel_pk: 지울 채널의 행 ID.
    """
    connection.execute("DELETE FROM channels WHERE id = ?", (channel_pk,))
    connection.commit()


def _exists(connection: sqlite3.Connection, channel_id: str) -> bool:
    """같은 채널 ID 가 이미 있는지 알려준다.

    DB 의 ``UNIQUE`` 가 마지막 방어선이고, 화면에 보여 줄 문장은 이
    검사가 있어야 만들 수 있다.

    Args:
        connection: 열린 커넥션.
        channel_id: 이미 공백을 지운 채널 ID.

    Returns:
        있으면 참.
    """
    row = connection.execute(
        "SELECT 1 FROM channels WHERE channel_id = ? LIMIT 1",
        (channel_id,),
    ).fetchone()
    return row is not None


def _require_date(value: str) -> str:
    """``YYYY-MM-DD`` 형식인지 확인하고 공백을 지워 돌려준다.

    저장소가 형식을 지키면 ``core.new_videos`` 가 형식을 다시
    의심하지 않아도 된다. ``date.fromisoformat`` 은 ``20260923`` 같은
    다른 ISO 형식도 받으므로 길이를 함께 본다.

    Args:
        value: 검사할 기준일.

    Returns:
        공백을 지운 기준일.

    Raises:
        ValueError: 형식에 맞지 않는 경우.
    """
    stripped = value.strip()
    if len(stripped) != _BASELINE_LENGTH:
        raise ValueError(f"기준일이 YYYY-MM-DD 형식이 아닙니다: {stripped!r}")
    try:
        datetime.date.fromisoformat(stripped)
    except ValueError:
        raise ValueError(
            f"기준일이 YYYY-MM-DD 형식이 아닙니다: {stripped!r}"
        ) from None
    return stripped


def _to_channel(row: sqlite3.Row) -> models.Channel:
    """DB 행을 ``Channel`` 로 바꾼다."""
    return models.Channel(
        id=int(row["id"]),
        channel_id=row["channel_id"],
        title=row["title"],
        url=row["url"],
        baseline=row["baseline"],
        created_at=row["created_at"],
    )
