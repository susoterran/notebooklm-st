"""질문 템플릿 저장소.

연결과 스키마는 ``store`` 가 맡는다.
"""

import sqlite3

from notebooklm_st.core import models
from notebooklm_st.services import store


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
        "SELECT id, title, text, created_at, updated_at FROM questions"
        " ORDER BY id"
    ).fetchall()
    return [_to_question(row) for row in rows]


def add_question(
    connection: sqlite3.Connection, title: str, text: str
) -> models.Question:
    """새 질문을 등록한다.

    제목은 질문을 목록과 답변 머리글에서 가리키는 이름이므로 중복을
    허용하지 않는다.

    Args:
        connection: 열린 커넥션.
        title: 목록에 보여 줄 제목. 앞뒤 공백은 지운다.
        text: 질문 본문. 앞뒤 공백은 지운다.

    Returns:
        저장된 질문.

    Raises:
        ValueError: 제목이나 본문이 공백만으로 이루어졌거나, 같은
            제목의 질문이 이미 있는 경우.
    """
    stripped_title = _require_text(title, "제목")
    stripped_text = _require_text(text, "질문")
    _require_unique_title(connection, stripped_title, None)
    now = store.now()
    row = connection.execute(
        "INSERT INTO questions (title, text, created_at, updated_at)"
        " VALUES (?, ?, ?, ?)"
        " RETURNING id, title, text, created_at, updated_at",
        (stripped_title, stripped_text, now, now),
    ).fetchone()
    connection.commit()
    return _to_question(row)


def update_question(
    connection: sqlite3.Connection,
    question_id: int,
    title: str,
    text: str,
) -> None:
    """질문의 제목과 본문을 바꾼다.

    Args:
        connection: 열린 커넥션.
        question_id: 바꿀 질문의 ID.
        title: 새 제목.
        text: 새 본문.

    Raises:
        ValueError: 제목이나 본문이 비었거나, 다른 질문이 이미 그
            제목을 쓰고 있거나, 그 ID 의 질문이 없는 경우.
    """
    stripped_title = _require_text(title, "제목")
    stripped_text = _require_text(text, "질문")
    _require_unique_title(connection, stripped_title, question_id)
    cursor = connection.execute(
        "UPDATE questions SET title = ?, text = ?, updated_at = ? WHERE id = ?",
        (stripped_title, stripped_text, store.now(), question_id),
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


def _require_unique_title(
    connection: sqlite3.Connection, title: str, question_id: int | None
) -> None:
    """같은 제목의 다른 질문이 있으면 예외를 던진다.

    ``id IS NOT ?`` 는 SQLite 의 NULL 안전 비교라, ``question_id`` 가
    ``None`` 이면 모든 행과 견주고 값이 있으면 그 행만 뺀다. 수정할 때
    자기 제목을 그대로 두는 것을 막지 않기 위해서다.

    Args:
        connection: 열린 커넥션.
        title: 이미 공백을 지운 제목.
        question_id: 수정 중인 질문의 ID. 새로 등록할 때는 ``None``.

    Raises:
        ValueError: 같은 제목의 다른 질문이 이미 있는 경우.
    """
    row = connection.execute(
        "SELECT id FROM questions WHERE title = ? AND id IS NOT ? LIMIT 1",
        (title, question_id),
    ).fetchone()
    if row is not None:
        raise ValueError(f"'{title}' 제목의 질문이 이미 있습니다.")


def _require_text(text: str, subject: str) -> str:
    """공백을 지운 값을 돌려주고, 비면 예외를 던진다.

    Args:
        text: 검사할 문자열.
        subject: 오류 문구에 넣을 항목 이름. 조사 "이"를 붙이므로
            받침이 있는 한글 명사여야 한다(예: "제목", "질문").

    Returns:
        앞뒤 공백을 지운 문자열.

    Raises:
        ValueError: 공백을 지우면 빈 문자열이 되는 경우.
    """
    stripped = text.strip()
    if not stripped:
        raise ValueError(f"{subject}이 비어 있습니다.")
    return stripped


def _to_question(row: sqlite3.Row) -> models.Question:
    """DB 행을 ``Question`` 으로 바꾼다."""
    return models.Question(
        id=int(row["id"]),
        title=row["title"],
        text=row["text"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
