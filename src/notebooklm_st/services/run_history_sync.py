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

from notebooklm_st.core import models
from notebooklm_st.services import run_history


def list_exported(connection: sqlite3.Connection) -> list[models.RunSummary]:
    """Outline 에 저장된 실행을 전부, 새 것부터 돌려준다.

    상한을 두지 않는다. 동기화는 목록 전체를 봐야 한다.

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
    connection: sqlite3.Connection, create: models.SyncCreate
) -> int | None:
    """Outline 문서에서 되살린 저장된 행을 넣는다.

    **커밋하지 않는다.** 트랜잭션은 ``history_sync.apply`` 가 소유한다.
    같은 문서를 가리키는 행이 이미 있으면 넣지 않는다 — 미리보기와
    적용 사이에 다른 탭이 먼저 저장했을 수 있다.

    ``answers``·``run_metadata`` 행은 만들지 않는다. 저장된 실행은
    원래 본문이 없다.

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
    return int(row["id"])


def delete_runs(connection: sqlite3.Connection, run_ids: Sequence[int]) -> int:
    """실행 여럿을 한 문장으로 지운다.

    **커밋하지 않는다.** 트랜잭션은 ``history_sync.apply`` 가 소유한다.
    없는 ID 는 무시한다. 딸린 답변은 외래키가 함께 지운다.

    Args:
        connection: 열린 커넥션.
        run_ids: 지울 실행 ID 들. 비어 있으면 아무것도 하지 않는다.

    Returns:
        실제로 지운 행 수.
    """
    if not run_ids:
        return 0
    # 자리표시자만 이어 붙인다. 값은 전부 파라미터로 넘긴다.
    placeholders = ", ".join("?" for _ in run_ids)
    cursor = connection.execute(
        f"DELETE FROM runs WHERE id IN ({placeholders})", tuple(run_ids)
    )
    return int(cursor.rowcount)
