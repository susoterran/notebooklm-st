"""실행 이력 저장소.

연결과 스키마는 ``store`` 가 맡는다. 진행 중인 실행을 메모리에 담는
``runs`` 와 달리 이 모듈은 끝난 실행을 DB 에 남긴다.
"""

import sqlite3

from notebooklm_st.core import models
from notebooklm_st.services import store


def list_video_ids(connection: sqlite3.Connection) -> set[str]:
    """이력에 남은 영상 ID 를 모두 돌려준다.

    빈 문자열은 뺀다. ``video_id`` 는
    ``youtube.extract_video_id(url) or ""`` 로 채워지므로 ID 를 못
    뽑은 옛 실행은 빈 문자열을 가진다. 그것이 집합에 섞이면 ID 가
    빈 피드 항목과 엉뚱하게 맞부딪힌다.

    Args:
        connection: 열린 커넥션.

    Returns:
        요약한 적이 있는 영상 ID 집합.
    """
    rows = connection.execute(
        "SELECT DISTINCT video_id FROM runs WHERE video_id <> ''"
    ).fetchall()
    return {row["video_id"] for row in rows}


SUMMARY_SELECT = (
    "SELECT r.id, r.url, r.video_id, r.title, r.created_at,"
    " r.outline_id, r.outline_url, r.outline_title, r.exported_at,"
    " m.run_id AS metadata_run_id, m.channel, m.upload_date,"
    " COUNT(a.id) AS answer_count"
    " FROM runs AS r"
    " LEFT JOIN answers AS a ON a.run_id = r.id"
    " LEFT JOIN run_metadata AS m ON m.run_id = r.id"
)
"""``list_runs``·``load_run``·``run_history_sync.list_exported`` 가
함께 쓰는 SELECT 머리.

``run_metadata`` 는 실행 하나에 많아야 한 행이라 조인이 답변 행을
불리지 않는다."""


def row_to_summary(row: sqlite3.Row) -> models.RunSummary:
    """``SUMMARY_SELECT`` 의 행 하나를 요약으로 바꾼다.

    ``run_history_sync`` 도 이 함수를 그대로 가져다 쓴다. SQL 을
    두 모듈에 중복해 두지 않으려는 것이다.
    """
    metadata = None
    if row["metadata_run_id"] is not None:
        metadata = models.VideoMetadata(
            channel=row["channel"], upload_date=row["upload_date"]
        )
    return models.RunSummary(
        id=int(row["id"]),
        url=row["url"],
        video_id=row["video_id"],
        title=row["title"],
        created_at=row["created_at"],
        answer_count=int(row["answer_count"]),
        outline_id=row["outline_id"],
        outline_url=row["outline_url"],
        outline_title=row["outline_title"],
        exported_at=row["exported_at"],
        metadata=metadata,
    )


def save_run(
    connection: sqlite3.Connection,
    result: models.RunResult,
    metadata: models.VideoMetadata | None = None,
) -> int:
    """실행 결과를 이력으로 저장한다.

    질문 제목과 본문을 ``questions`` 테이블 외래키가 아니라 문자열로
    복사해 둔다. 나중에 질문을 고치거나 지워도 과거 이력이 그대로
    남는다.

    Args:
        connection: 열린 커넥션.
        result: 저장할 실행 결과.
        metadata: 영상에서 뽑아 온 메타데이터. 없으면 행을 만들지
            않는다 — 빈 행과 없는 행이 같은 뜻이 되면 나중에
            구분하지 못한다.

    Returns:
        저장된 실행의 ID.
    """
    row = connection.execute(
        "INSERT INTO runs (url, video_id, title, created_at)"
        " VALUES (?, ?, ?, ?)"
        " RETURNING id",
        (result.url, result.video_id, result.title, store.now()),
    ).fetchone()
    run_id = int(row["id"])
    connection.executemany(
        "INSERT INTO answers"
        " (run_id, question_title, question_text, answer, citations,"
        " error)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                run_id,
                item.question_title,
                item.question_text,
                item.answer,
                models.citations_to_json(item.citations),
                item.error,
            )
            for item in result.items
        ],
    )
    if metadata is not None:
        connection.execute(
            "INSERT INTO run_metadata (run_id, channel, upload_date)"
            " VALUES (?, ?, ?)",
            (run_id, metadata.channel, metadata.upload_date),
        )
    connection.commit()
    return run_id


def list_runs(
    connection: sqlite3.Connection, limit: int = 50
) -> list[models.RunSummary]:
    """최근 실행을 새 것부터 돌려준다.

    Args:
        connection: 열린 커넥션.
        limit: 가져올 최대 개수.

    Returns:
        실행 요약 목록. Outline 으로 넘어간 실행은 문서 링크를 싣고
        오며 ``answer_count`` 가 0 이다.
    """
    rows = connection.execute(
        SUMMARY_SELECT + " GROUP BY r.id ORDER BY r.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [row_to_summary(row) for row in rows]


def load_run(
    connection: sqlite3.Connection, run_id: int
) -> models.RunSummary | None:
    """실행 하나의 요약을 읽는다.

    ``list_runs`` 의 한 건짜리다. 자동 저장이 문서 본문을 만들 때
    쓴다.

    Args:
        connection: 열린 커넥션.
        run_id: 찾을 실행 ID.

    Returns:
        요약. 그런 실행이 없으면 ``None``.
    """
    # GROUP BY 를 빼면 집계 함수(COUNT) 때문에 없는 ID 에도 빈 칸으로
    # 찬 행이 하나 온다.
    row = connection.execute(
        SUMMARY_SELECT + " WHERE r.id = ? GROUP BY r.id", (run_id,)
    ).fetchone()
    if row is None:
        return None
    return row_to_summary(row)


def load_run_items(
    connection: sqlite3.Connection, run_id: int
) -> list[models.AnswerItem]:
    """한 실행에 속한 답변들을 저장 순서대로 돌려준다.

    Args:
        connection: 열린 커넥션.
        run_id: 실행 ID.

    Returns:
        답변 목록. 각 항목은 자기 ``id`` 를 들고 온다. 그런 실행이
        없으면 빈 목록.
    """
    rows = connection.execute(
        "SELECT id, question_title, question_text, answer, citations,"
        " error FROM answers WHERE run_id = ? ORDER BY id",
        (run_id,),
    ).fetchall()
    return [
        models.AnswerItem(
            question_title=row["question_title"],
            question_text=row["question_text"],
            answer=row["answer"],
            citations=models.citations_from_json(row["citations"]),
            error=row["error"],
            id=int(row["id"]),
        )
        for row in rows
    ]


def load_metadata(
    connection: sqlite3.Connection, run_id: int
) -> models.VideoMetadata | None:
    """실행 하나의 영상 메타데이터를 읽는다.

    Args:
        connection: 열린 커넥션.
        run_id: 찾을 실행 ID.

    Returns:
        저장된 메타데이터. 없으면 ``None``.
    """
    row = connection.execute(
        "SELECT channel, upload_date FROM run_metadata WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    return models.VideoMetadata(
        channel=row["channel"], upload_date=row["upload_date"]
    )


def mark_exported(
    connection: sqlite3.Connection,
    run_id: int,
    *,
    document_id: str,
    document_title: str,
    document_url: str,
) -> None:
    """문서 링크를 적고 로컬 답변을 지운다.

    두 문장을 커밋 하나로 묶는다. 중간에 죽어도 "본문은 사라졌는데
    링크는 없는" 상태가 생기지 않는다.

    영상 메타데이터(``run_metadata``)는 지우지 않는다. 문서 머리에
    적은 채널·업로드 일자와 같은 값의 캐시로 남아 정리본 재료 표가
    쓴다. 정본은 Outline 이고, 이력 동기화가 문서에서 다시 읽어
    맞춘다.

    Outline 의 자료형을 받지 않고 문자열 셋을 받는다. 저장소가 외부
    서비스를 알 이유가 없다.

    Args:
        connection: 열린 커넥션.
        run_id: 링크를 걸 실행 ID.
        document_id: Outline 문서 ID. 나중에 문서를 다시 읽을 때 쓴다.
        document_title: Outline 에 붙은 문서 제목.
        document_url: 사람이 열 수 있는 절대 URL.

    Raises:
        ValueError: 그 ID 의 실행이 없는 경우. 이때는 아무것도 지우지
            않는다.
    """
    # 커넥션은 앱 전체가 함께 쓴다. UPDATE 만 걸린 채로 예외가 빠져
    # 나가면 다음 조회가 그 실행을 저장된 것으로 그리고, 다른 곳의
    # commit 이 반쪽짜리 내보내기를 확정해 버린다. 그래서 어떤 실패든
    # 여기서 되돌리고 다시 던진다.
    try:
        cursor = connection.execute(
            "UPDATE runs SET outline_id = ?, outline_url = ?,"
            " outline_title = ?, exported_at = ? WHERE id = ?",
            (
                document_id,
                document_url,
                document_title,
                store.now(),
                run_id,
            ),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"실행 {run_id} 을 찾을 수 없습니다.")
        connection.execute("DELETE FROM answers WHERE run_id = ?", (run_id,))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def delete_run(connection: sqlite3.Connection, run_id: int) -> None:
    """실행 하나를 이력에서 지운다. 이미 없으면 조용히 넘어간다.

    딸린 답변은 외래키의 ``ON DELETE CASCADE`` 가 함께 지운다.
    ``store.connect`` 가 ``PRAGMA foreign_keys`` 를 켜 두므로 실제로
    동작한다.

    Args:
        connection: 열린 커넥션.
        run_id: 지울 실행의 ID.
    """
    connection.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    connection.commit()
