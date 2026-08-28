"""SQLite 연결과 스키마.

질문 템플릿 CRUD 는 ``questions``, 실행 이력 CRUD 는
``run_history`` 에 있다. 이 모듈은 두 모듈이 함께 쓰는 연결·스키마·
시각 헬퍼만 담는다.
"""

import datetime
import os
import pathlib
import sqlite3

DB_PATH_ENV_VAR = "NOTEBOOKLM_ST_DB"

_DEFAULT_DB_NAME = "questions.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id         INTEGER PRIMARY KEY,
    title      TEXT NOT NULL,
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
    id             INTEGER PRIMARY KEY,
    run_id         INTEGER NOT NULL REFERENCES runs(id)
                   ON DELETE CASCADE,
    question_title TEXT NOT NULL,
    question_text  TEXT NOT NULL,
    answer         TEXT,
    citations      TEXT,
    error          TEXT
);
"""

# 이 프로젝트는 마이그레이션을 지원하지 않는다(의도된 결정). 예전
# 스키마의 DB 파일은 지우고 새로 만드는 것이 유일한 해법이므로,
# connect() 는 이 상수와 실제 컬럼을 비교해 빠진 컬럼이 있으면 바로
# 실패한다.
#
# 테이블 이름은 이 상수의 리터럴 키에서만 온다. 사용자 입력이 여기에
# 섞일 일이 없으므로 아래 PRAGMA 호출에 그대로 넣어도 안전하다.
_EXPECTED_COLUMNS: dict[str, frozenset[str]] = {
    "questions": frozenset({"id", "title", "text", "created_at", "updated_at"}),
    "runs": frozenset({"id", "url", "video_id", "created_at"}),
    "answers": frozenset(
        {
            "id",
            "run_id",
            "question_title",
            "question_text",
            "answer",
            "citations",
            "error",
        }
    ),
}


class StaleSchemaError(RuntimeError):
    """DB 파일의 스키마가 현재 코드가 기대하는 컬럼과 맞지 않는다.

    이 프로젝트는 마이그레이션 경로를 두지 않기로 했다(의도된
    결정). 스키마가 바뀌면 예전 DB 파일을 지우고 새로 만드는 것이
    유일한 해법이며, 이 예외의 메시지가 그 안내를 담는다.
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

    Raises:
        StaleSchemaError: 기존 DB 파일에 현재 코드가 기대하는
            컬럼이 없는 경우.
    """
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(_SCHEMA)
    connection.commit()
    _verify_schema(connection, db_path)
    return connection


def _verify_schema(
    connection: sqlite3.Connection, db_path: pathlib.Path
) -> None:
    """모든 테이블에 기대하는 컬럼이 있는지 확인한다.

    ``CREATE TABLE IF NOT EXISTS`` 는 이미 있는 테이블을 건드리지
    않으므로, 예전 스키마의 DB 파일이 조용히 통과해 버린다. 이
    함수가 그 틈을 막는다.

    Args:
        connection: 열린 커넥션.
        db_path: 오류 메시지에 넣을 DB 파일 경로.

    Raises:
        StaleSchemaError: 어떤 테이블에 기대하는 컬럼이 빠져
            있는 경우.
    """
    for table, expected in _EXPECTED_COLUMNS.items():
        # table 은 _EXPECTED_COLUMNS 의 리터럴 키에서만 온다.
        rows = connection.execute(f"PRAGMA table_info({table})")
        actual = {row["name"] for row in rows.fetchall()}
        missing = expected - actual
        if missing:
            raise StaleSchemaError(
                f"{db_path} 의 {table} 테이블이 오래된 스키마입니다"
                f"(없는 컬럼: {sorted(missing)}). 이 파일을 지우고"
                " 다시 실행하세요."
            )


def now() -> str:
    """현재 로컬 시각을 초 단위 ISO 문자열로 돌려준다.

    Returns:
        ``2026-08-28T10:00:00`` 형식의 문자열.
    """
    return datetime.datetime.now().isoformat(timespec="seconds")
