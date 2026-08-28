"""SQLite 저장소 — 질문 템플릿과 실행 이력."""

import datetime
import os
import pathlib
import sqlite3

from notebooklm_st.core import models

DB_PATH_ENV_VAR = "NOTEBOOKLM_ST_DB"

_DEFAULT_DB_NAME = "questions.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id         INTEGER PRIMARY KEY,
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY,
    url        TEXT NOT NULL,
    video_id   TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS answers (
    id            INTEGER PRIMARY KEY,
    run_id        INTEGER NOT NULL REFERENCES runs(id)
                  ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    answer        TEXT,
    citations     TEXT,
    error         TEXT
);
"""


def default_db_path() -> pathlib.Path:
    """쓸 DB 파일 경로를 정한다.

    환경 변수로 덮어쓸 수 있게 해 두면 테스트가 임시 디렉터리를
    가리킬 수 있다.

    Returns:
        ``NOTEBOOKLM_ST_DB`` 가 있으면 그 경로, 없으면 현재
        작업 디렉터리의 ``questions.db``.
    """
    override = os.environ.get(DB_PATH_ENV_VAR)
    if override:
        return pathlib.Path(override)
    return pathlib.Path.cwd() / _DEFAULT_DB_NAME


def connect(db_path: pathlib.Path) -> sqlite3.Connection:
    """DB 에 연결하고 스키마가 있는지 보장한다.

    Streamlit 이 스크립트를 다른 스레드에서 재실행할 수 있으므로
    ``check_same_thread`` 를 끈다.

    Args:
        db_path: DB 파일 경로. 없으면 새로 만든다.

    Returns:
        행을 ``sqlite3.Row`` 로 돌려주는 커넥션.
    """
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(_SCHEMA)
    connection.commit()
    return connection


def list_questions(
    connection: sqlite3.Connection,
) -> list[models.Question]:
    """등록된 질문을 등록 순서대로 돌려준다.

    Args:
        connection: 열린 커넥션.

    Returns:
        질문 목록.
    """
    rows = connection.execute(
        "SELECT id, text, created_at, updated_at FROM questions ORDER BY id"
    ).fetchall()
    return [_to_question(row) for row in rows]


def add_question(connection: sqlite3.Connection, text: str) -> models.Question:
    """새 질문을 등록한다.

    Args:
        connection: 열린 커넥션.
        text: 질문 본문. 앞뒤 공백은 지운다.

    Returns:
        저장된 질문.

    Raises:
        ValueError: 공백을 지우면 빈 문자열이 되는 경우.
    """
    stripped = _require_text(text)
    now = _now()
    row = connection.execute(
        "INSERT INTO questions (text, created_at, updated_at)"
        " VALUES (?, ?, ?)"
        " RETURNING id, text, created_at, updated_at",
        (stripped, now, now),
    ).fetchone()
    connection.commit()
    return _to_question(row)


def update_question(
    connection: sqlite3.Connection, question_id: int, text: str
) -> None:
    """질문 본문을 바꾼다.

    Args:
        connection: 열린 커넥션.
        question_id: 바꿀 질문의 ID.
        text: 새 본문.

    Raises:
        ValueError: 본문이 비었거나 그 ID 의 질문이 없는 경우.
    """
    stripped = _require_text(text)
    cursor = connection.execute(
        "UPDATE questions SET text = ?, updated_at = ? WHERE id = ?",
        (stripped, _now(), question_id),
    )
    connection.commit()
    if cursor.rowcount == 0:
        raise ValueError(f"질문 {question_id} 을 찾을 수 없습니다.")


def delete_question(connection: sqlite3.Connection, question_id: int) -> None:
    """질문을 지운다. 이미 없으면 조용히 넘어간다.

    Args:
        connection: 열린 커넥션.
        question_id: 지울 질문의 ID.
    """
    connection.execute("DELETE FROM questions WHERE id = ?", (question_id,))
    connection.commit()


def save_run(connection: sqlite3.Connection, result: models.RunResult) -> int:
    """실행 결과를 이력으로 저장한다.

    질문 본문을 ``questions`` 테이블 외래키가 아니라 문자열로 복사해
    둔다. 나중에 질문을 고치거나 지워도 과거 이력이 그대로 남는다.

    Args:
        connection: 열린 커넥션.
        result: 저장할 실행 결과.

    Returns:
        저장된 실행의 ID.
    """
    row = connection.execute(
        "INSERT INTO runs (url, video_id, created_at)"
        " VALUES (?, ?, ?)"
        " RETURNING id",
        (result.url, result.video_id, _now()),
    ).fetchone()
    run_id = int(row["id"])
    connection.executemany(
        "INSERT INTO answers"
        " (run_id, question_text, answer, citations, error)"
        " VALUES (?, ?, ?, ?, ?)",
        [
            (
                run_id,
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
        "SELECT r.id, r.url, r.video_id, r.created_at,"
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
        답변 목록. 그런 실행이 없으면 빈 목록.
    """
    rows = connection.execute(
        "SELECT question_text, answer, citations, error FROM answers"
        " WHERE run_id = ? ORDER BY id",
        (run_id,),
    ).fetchall()
    return [
        models.AnswerItem(
            question_text=row["question_text"],
            answer=row["answer"],
            citations=models.citations_from_json(row["citations"]),
            error=row["error"],
        )
        for row in rows
    ]


def _require_text(text: str) -> str:
    """공백을 지운 본문을 돌려주고, 비면 예외를 던진다."""
    stripped = text.strip()
    if not stripped:
        raise ValueError("질문이 비어 있습니다.")
    return stripped


def _now() -> str:
    """현재 로컬 시각을 초 단위 ISO 문자열로 돌려준다."""
    return datetime.datetime.now().isoformat(timespec="seconds")


def _to_question(row: sqlite3.Row) -> models.Question:
    """DB 행을 ``Question`` 으로 바꾼다."""
    return models.Question(
        id=int(row["id"]),
        text=row["text"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
