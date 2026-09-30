"""앱 설정을 DB 에 기억한다.

지금은 자동 저장 하나뿐이다. 재시작하거나 다른 기기에서 열어도 켜 둔
그대로여야 하므로 세션이 아니라 DB 에 둔다. 범용 설정 API 는 만들지
않는다 — 설정이 하나뿐인데 키·타입을 일반화하면 읽는 쪽만 늘어난다.
"""

import sqlite3

_AUTO_SAVE_KEY = "auto_save"


def auto_save(connection: sqlite3.Connection) -> bool:
    """자동 저장이 켜져 있는지 읽는다.

    Args:
        connection: 열린 커넥션.

    Returns:
        켜 두었으면 참. 한 번도 정한 적이 없으면 거짓.
    """
    row = connection.execute(
        "SELECT value FROM settings WHERE key = ?", (_AUTO_SAVE_KEY,)
    ).fetchone()
    return row is not None and row["value"] == "1"


def set_auto_save(connection: sqlite3.Connection, enabled: bool) -> None:
    """자동 저장을 켜거나 끈다.

    Args:
        connection: 열린 커넥션.
        enabled: 켤지.
    """
    connection.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (_AUTO_SAVE_KEY, "1" if enabled else "0"),
    )
    connection.commit()
