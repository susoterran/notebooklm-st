"""동기화가 쓰는 이력 저장소 함수들.

Outline 문서 목록과 비교해 세운 동기화 계획을 적용할 때 쓰는
조회·삽입·일괄 삭제를 모은다. ``insert_exported`` 와
``delete_runs`` 는 **커밋하지 않는다** — 트랜잭션은
``history_sync.apply`` 가 소유하고, 계획을 전부 적용했을 때만 한
번에 커밋하거나 실패하면 통째로 되돌린다.

행 → 요약 변환은 ``run_history`` 의 ``SUMMARY_SELECT`` 와
``row_to_summary`` 를 그대로 가져와 쓴다. 같은 SQL 을 두 모듈에
중복해 두지 않으려는 것이다.
"""

import sqlite3
from collections.abc import Sequence

from notebooklm_st.core import models, sync_models
from notebooklm_st.services import run_history


def list_exported(connection: sqlite3.Connection) -> list[models.RunSummary]:
    """Outline 에 저장된 실행을 전부, 새 것부터 돌려준다.

    상한을 두지 않는다. 동기화도, 정리본의 재료 표도 목록 전체를
    봐야 한다.

    Args:
        connection: 열린 커넥션.

    Returns:
        ``exported_at`` 이 있는 실행 요약 목록.
    """
    rows = connection.execute(
        run_history.SUMMARY_SELECT
        + " WHERE r.exported_at IS NOT NULL"
        + " GROUP BY r.id"
        + " ORDER BY r.id DESC"
    ).fetchall()
    return [run_history.row_to_summary(row) for row in rows]


def insert_exported(
    connection: sqlite3.Connection, create: sync_models.SyncCreate
) -> int | None:
    """Outline 문서에서 되살린 저장된 행을 넣는다.

    **커밋하지 않는다.** 트랜잭션은 ``history_sync.apply`` 가 소유한다.
    같은 문서를 가리키는 행이 이미 있으면 넣지 않는다 — 미리보기와
    적용 사이에 다른 탭이 먼저 저장했을 수 있다.

    ``answers`` 행은 만들지 않는다. 저장된 실행은 원래 본문이 없다.
    문서 머리에서 읽은 메타데이터가 있으면 ``run_metadata`` 행을 함께
    만들고, 카테고리는 이름으로 잇는다. 이름은 ``history_sync.apply``
    가 먼저 등록해 둔다.

    Args:
        connection: 열린 커넥션.
        create: 만들 행의 값들.

    Returns:
        새 행의 ID. 이미 있어 넣지 않았으면 ``None``.
    """
    existing = connection.execute(
        "SELECT id FROM runs WHERE outline_id = ?", (create.document.id,)
    ).fetchone()
    if existing is not None:
        return None
    row = connection.execute(
        "INSERT INTO runs (url, video_id, title, created_at,"
        " outline_id, outline_url, outline_title, exported_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        " RETURNING id",
        (
            create.url,
            create.video_id,
            create.document.title,
            create.document.created_at,
            create.document.id,
            create.document.url,
            create.document.title,
            create.document.created_at,
        ),
    ).fetchone()
    run_id = int(row["id"])
    if create.metadata is not None:
        connection.execute(
            "INSERT INTO run_metadata (run_id, channel, upload_date)"
            " VALUES (?, ?, ?)",
            (run_id, create.metadata.channel, create.metadata.upload_date),
        )
    _link_by_name(connection, run_id, create.categories)
    return run_id


def delete_runs(
    connection: sqlite3.Connection, keys: Sequence[tuple[int, str]]
) -> int:
    """실행 여럿을 실행 ID 와 문서 ID 가 둘 다 맞을 때만 지운다.

    **커밋하지 않는다.** 트랜잭션은 ``history_sync.apply`` 가 소유한다.
    맞는 행이 없는 쌍은 무시한다. 딸린 답변은 외래키가 함께 지운다.

    ID 만으로 지우지 않는 이유는 SQLite 가 ID 를 다시 쓰기 때문이다.
    ``runs.id`` 에는 AUTOINCREMENT 가 없어, 가장 큰 ID 의 행이
    지워지면 다음 삽입이 그 ID 를 다시 받는다. 계획은 적용·취소
    전까지 세션에 남으므로, 그사이 사람이 그 행을 지우고 새로
    실행하면 같은 ID 의 미저장 실행이 생긴다. 문서 ID 까지 맞춰야 그
    실행이 지워지지 않는다 — 미저장 실행은 ``outline_id`` 가 비어
    있어 어떤 쌍과도 맞지 않는다.

    Args:
        connection: 열린 커넥션.
        keys: 지울 ``(실행 ID, 문서 ID)`` 쌍들. 비어 있으면 아무것도
            하지 않는다.

    Returns:
        실제로 지운 행 수.
    """
    if not keys:
        return 0
    cursor = connection.executemany(
        "DELETE FROM runs WHERE id = ? AND outline_id = ?", keys
    )
    # executemany 의 DML rowcount 는 sqlite3 가 문장마다 더해 준다.
    return int(cursor.rowcount)


def write_metadata(
    connection: sqlite3.Connection,
    run_id: int,
    outline_id: str,
    metadata: models.VideoMetadata,
) -> bool:
    """저장된 행 하나의 메타데이터를 넣거나 덮는다.

    **커밋하지 않는다.** 트랜잭션은 ``history_sync.apply`` 가 소유한다.
    실행 ID 와 문서 ID 가 둘 다 맞는 행에만 쓴다 — ``delete_runs`` 와
    같은 이유로, 다시 쓰인 ID 의 미저장 실행을 건드리지 않는다.

    값이 이미 같으면 덮지 않는다. 적용 결과의 갱신 건수가 실제로
    바뀐 행만 세게 한다.

    SQLite 는 ``INSERT … SELECT`` 에 ``WHERE`` 가 있어야 뒤의
    ``ON CONFLICT`` 를 upsert 절로 읽는다. 두 조건이 그 ``WHERE`` 다.

    Args:
        connection: 열린 커넥션.
        run_id: 쓸 실행의 ID.
        outline_id: 그 실행이 가리켜야 할 문서 ID.
        metadata: 쓸 값.

    Returns:
        새로 넣었거나 값을 바꿨으면 ``True``. 맞는 행이 없거나 값이
        이미 같으면 ``False``.
    """
    cursor = connection.execute(
        "INSERT INTO run_metadata (run_id, channel, upload_date)"
        " SELECT id, ?, ? FROM runs WHERE id = ? AND outline_id = ?"
        " ON CONFLICT(run_id) DO UPDATE SET"
        " channel = excluded.channel,"
        " upload_date = excluded.upload_date"
        " WHERE channel IS NOT excluded.channel"
        " OR upload_date IS NOT excluded.upload_date",
        (metadata.channel, metadata.upload_date, run_id, outline_id),
    )
    return cursor.rowcount > 0


def replace_categories(
    connection: sqlite3.Connection,
    run_id: int,
    outline_id: str,
    names: Sequence[str],
) -> bool:
    """저장된 행 하나의 카테고리를 이름들로 바꾼다.

    **커밋하지 않는다.** 트랜잭션은 ``history_sync.apply`` 가 소유한다.
    실행 ID 와 문서 ID 가 둘 다 맞는 행에만 쓴다 — ``write_metadata``
    와 같은 이유로, 다시 쓰인 ID 의 미저장 실행을 건드리지 않는다.

    Args:
        connection: 열린 커넥션.
        run_id: 바꿀 실행의 ID.
        outline_id: 그 실행이 가리켜야 할 문서 ID.
        names: 새 카테고리 이름. 등록되지 않은 이름은 빠진다.

    Returns:
        바꿨으면 ``True``. 맞는 행이 없거나 이름 집합이 이미 같으면
        ``False``.
    """
    found = connection.execute(
        "SELECT 1 FROM runs WHERE id = ? AND outline_id = ?",
        (run_id, outline_id),
    ).fetchone()
    if found is None:
        return False
    rows = connection.execute(
        "SELECT c.name FROM run_categories AS rc"
        " JOIN categories AS c ON c.id = rc.category_id"
        " WHERE rc.run_id = ?",
        (run_id,),
    ).fetchall()
    if {row["name"] for row in rows} == set(names):
        return False
    connection.execute("DELETE FROM run_categories WHERE run_id = ?", (run_id,))
    _link_by_name(connection, run_id, names)
    return True


def _link_by_name(
    connection: sqlite3.Connection, run_id: int, names: Sequence[str]
) -> None:
    """실행 하나에 카테고리를 이름으로 잇는다. 커밋하지 않는다.

    ``categories`` 에서 골라 넣으므로 등록되지 않은 이름은 빠진다.
    """
    connection.executemany(
        "INSERT OR IGNORE INTO run_categories (run_id, category_id)"
        " SELECT ?, id FROM categories WHERE name = ?",
        [(run_id, name) for name in names],
    )
