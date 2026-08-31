"""실행 이력 저장소.

연결과 스키마는 ``store`` 가 맡는다. 진행 중인 실행을 메모리에 담는
``runs`` 와 달리 이 모듈은 끝난 실행을 DB 에 남긴다.
"""

import sqlite3

from notebooklm_st.core import models
from notebooklm_st.services import store


def save_run(connection: sqlite3.Connection, result: models.RunResult) -> int:
    """실행 결과를 이력으로 저장한다.

    질문 제목과 본문을 ``questions`` 테이블 외래키가 아니라 문자열로
    복사해 둔다. 나중에 질문을 고치거나 지워도 과거 이력이 그대로
    남는다.

    Args:
        connection: 열린 커넥션.
        result: 저장할 실행 결과.

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
        실행 요약 목록.
    """
    rows = connection.execute(
        "SELECT r.id, r.url, r.video_id, r.title, r.created_at,"
        " COUNT(a.id) AS answer_count"
        " FROM runs AS r"
        " LEFT JOIN answers AS a ON a.run_id = r.id"
        " GROUP BY r.id"
        " ORDER BY r.id DESC"
        " LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        models.RunSummary(
            id=int(row["id"]),
            url=row["url"],
            video_id=row["video_id"],
            title=row["title"],
            created_at=row["created_at"],
            answer_count=int(row["answer_count"]),
        )
        for row in rows
    ]


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


def update_answer(
    connection: sqlite3.Connection, answer_id: int, answer: str
) -> None:
    """저장된 답변 본문을 바꾼다.

    본문만 바꾼다. 질문 제목·원문과 인용은 "무엇을 물어서 이 답이
    나왔는가" 의 기록이므로 손대지 않는다.

    Args:
        connection: 열린 커넥션.
        answer_id: 바꿀 답변의 ID.
        answer: 새 본문. 앞뒤 공백은 지운다.

    Raises:
        ValueError: 본문이 비었거나 그 ID 의 답변이 없는 경우.
    """
    stripped = answer.strip()
    if not stripped:
        raise ValueError("답변을 비울 수 없습니다.")
    cursor = connection.execute(
        "UPDATE answers SET answer = ? WHERE id = ?",
        (stripped, answer_id),
    )
    connection.commit()
    if cursor.rowcount == 0:
        raise ValueError(f"답변 {answer_id} 을 찾을 수 없습니다.")


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
