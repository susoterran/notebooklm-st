# 영상 메타데이터 frontmatter (R3) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 요약본 맨 앞에 YAML frontmatter 를 붙이고, 채널명과 업로드일자를 yt-dlp 로 가져와 채운다.

**Architecture:** yt-dlp 를 아는 모듈은 `services/video_metadata.py` 하나뿐이다. 자식 프로세스로 CLI 를 부르고 실패를 예외가 아니라 값으로 돌려준다. 저장은 `runs` 를 건드리지 않고 새 테이블 `run_metadata` 로 한다. 출력은 `core/markdown_export.py` 가 frontmatter 블록을 앞에 얹는다 — 그 아래 본문은 한 글자도 바뀌지 않는다.

**Tech Stack:** Python 3.13, Streamlit 1.63, notebooklm-py 0.8.1, yt-dlp, pytest, mypy, ruff, uv

**Spec:** `docs/superpowers/specs/2026-09-22-video-metadata-design.md`

## Global Constraints

- **Python** `>=3.13` (`pyproject.toml` `requires-python`)
- **ruff**: `line-length = 80`, `target-version = "py313"`,
  `select = ["E","W","F","I","N","D","UP","B","SIM","ANN","RUF"]`,
  `ignore = ["ANN401"]`, `pydocstyle convention = "google"`
- **docstring 필수** — `D` 규칙이 켜져 있어 **테스트 함수·헬퍼 클래스·메서드에도 docstring 이 있어야 한다.** 한국어로 쓴다.
- **mypy**: `notebooklm_st.core.*` 와 `notebooklm_st.services.*` 는 `disallow_untyped_defs = true`. 이 두 곳의 모든 함수에 타입 주석을 붙인다.
- **`tests/**` 는 `ANN` 만 면제**된다(`per-file-ignores`). 타입 주석은 생략해도 되지만 docstring 은 필요하다. 기존 테스트가 `-> None` 을 붙이는 관례를 따르므로 그대로 따른다.
- **경계 규칙**: `core/` 와 `services/` 는 `import streamlit` 을 하지 않는다.
- **import 는 모듈 단위로** (`.claude/rules/streamlit-implement.md` §4.1) — 모듈을 import 해 정규화된 이름으로 쓴다. `import dataclasses` 뒤 `@dataclasses.dataclass`, `from notebooklm_st.services import video_metadata` 뒤 `video_metadata.fetch`. **예외로 허용**: `typing`, `collections.abc` 에서의 심볼 import. **ruff 가 검사하지 않으므로 사람이 지킨다.**
- **독스트링과 주석은 72자**에서 줄바꿈한다(코드는 80자). 같은 규칙 §4.2.
- **`# noqa` 는 규칙 코드를 반드시 명시**한다(`# noqa: E501`).
- **`except:` 와 맨 `except Exception:` 은 금지**한다(같은 규칙 §4, 파일 75행). 구체적인 예외를 잡고 `try` 블록에는 예외가 날 수 있는 최소한의 코드만 둔다. **이 계획에는 넓은 `except` 가 필요한 자리가 없다.**
- **의존성 조작은 `uv add` · `uv remove` 로만** 한다(§1). `uv.lock` 은 커밋 대상이며 손으로 편집하지 않는다.
- 함수가 40줄을 넘으면 분리를 검토한다.
- **검증 4단** — 모든 커밋 전에 순서대로 돌린다.
  ```
  uv run ruff format .
  uv run ruff check --fix .
  uv run mypy src tests
  uv run pytest
  ```
- **`uv` 가 PATH 에 없을 수 있다.** 그럴 때는 전체 경로로 부른다: `C:\Users\susot\.local\bin\uv.exe run ...`
- **커밋 규약** (`.claude/rules/commit-strategy.md`): 헤더는 `<emoji> <type>(<scope>): <subject>`, subject 는 **한국어·명령형·마침표 없음·≤50자**. 마지막 줄에 `Assisted-by: <자기 모델 ID>`. `Co-Authored-By:` 는 붙이지 않는다.
- **`git push` 금지.** 커밋만 한다. push 와 PR 은 사람이 한다.
- 현재 브랜치는 `develop` 이다. `master` 에 직접 커밋하지 않는다.

---

## File Structure

| 파일 | 책임 | 이 계획에서 |
|---|---|---|
| `src/notebooklm_st/core/models.py` | 화면과 저장소가 함께 쓰는 값 객체 | Task 1 |
| `src/notebooklm_st/services/store.py` | 커넥션·스키마. **스키마의 정본** | Task 1 |
| `src/notebooklm_st/services/run_history.py` | 끝난 실행을 DB 에 남기고 읽는다 | Task 2 |
| `src/notebooklm_st/services/video_metadata.py` | **yt-dlp 를 아는 유일한 모듈.** 조회하고 실패를 값으로 돌려준다 | Task 3 (신규) |
| `src/notebooklm_st/core/markdown_export.py` | 이력 한 건을 마크다운으로 옮긴다 | Task 4 |
| `src/notebooklm_st/services/runner.py` | 백그라운드 실행 | Task 5 |
| `src/notebooklm_st/pages/history.py` | 이력 화면과 다운로드 버튼 | Task 5 |
| `pyproject.toml` · `uv.lock` | 의존성 | Task 3 |
| `README.md` | 프로젝트 개요 | Task 5 |

**Task 순서의 이유.** Task 1 이 `models.VideoMetadata` 를 만들고, Task 2·3·4 가 그것을 각각 저장·생산·소비한다. Task 5 는 셋을 실제 흐름에 잇는다. **각 Task 가 끝날 때마다 테스트가 전부 초록이어야 한다** — Task 1~4 는 기존 호출자를 깨지 않도록 전부 기본값 인자로 붙인다.

---

### Task 1: `run_metadata` 테이블과 값 객체

**Files:**
- Modify: `src/notebooklm_st/core/models.py`
- Modify: `src/notebooklm_st/services/store.py`
- Test: `tests/services/test_store.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `models.VideoMetadata(channel: str | None, upload_date: str | None)`
  - `run_metadata` 테이블 — `run_id INTEGER PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE`, `channel TEXT`, `upload_date TEXT`

**배경.** 이 프로젝트는 마이그레이션을 두지 않기로 했다(`services/store.py` 의 `_EXPECTED_COLUMNS` 위 주석). `runs` 에 컬럼을 더하면 `_verify_schema` 가 기존 DB 를 `StaleSchemaError` 로 막고 사용자는 파일을 지워야 한다 — 질문 템플릿과 실행 이력이 함께 사라진다. 새 테이블은 `executescript(_SCHEMA)` 가 옛 파일에도 만들어 주므로 그 문제가 없다. **이 Task 의 테스트가 그 사실을 고정한다.**

- [ ] **Step 1: 실패하는 테스트 쓰기**

`tests/services/test_store.py` 맨 끝에 추가한다.

```python
def test_connect_adds_run_metadata_to_an_older_database(tmp_path) -> None:
    """run_metadata 가 없는 DB 는 거부되지 않고 테이블만 생긴다."""
    db_path = tmp_path / "before_metadata.db"
    raw = sqlite3.connect(db_path)
    raw.executescript(
        """
        CREATE TABLE questions (
            id         INTEGER PRIMARY KEY,
            title      TEXT NOT NULL,
            text       TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE runs (
            id         INTEGER PRIMARY KEY,
            url        TEXT NOT NULL,
            video_id   TEXT NOT NULL,
            title      TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE answers (
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
    )
    raw.execute(
        "INSERT INTO runs (id, url, video_id, title, created_at)"
        " VALUES (1, 'https://youtu.be/dQw4w9WgXcQ', 'dQw4w9WgXcQ',"
        " '옛 실행', '2026-09-01T10:00:00')"
    )
    raw.commit()
    raw.close()

    connection = store.connect(db_path)
    try:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(run_metadata)")
        }
        survivor = connection.execute(
            "SELECT title FROM runs WHERE id = 1"
        ).fetchone()
    finally:
        connection.close()

    assert columns == {"run_id", "channel", "upload_date"}
    assert survivor["title"] == "옛 실행"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/services/test_store.py::test_connect_adds_run_metadata_to_an_older_database -v`

Expected: FAIL — `assert set() == {'run_id', 'channel', 'upload_date'}`.
`StaleSchemaError` 는 나지 않는다. 기존 세 테이블의 컬럼은 그대로이기 때문이다.

- [ ] **Step 3: 스키마와 값 객체 추가**

`src/notebooklm_st/services/store.py` 의 `_SCHEMA` 끝(`answers` 블록 뒤, 닫는 `"""` 앞)에 넣는다.

```sql

CREATE TABLE IF NOT EXISTS run_metadata (
    run_id      INTEGER PRIMARY KEY REFERENCES runs(id)
                ON DELETE CASCADE,
    channel     TEXT,
    upload_date TEXT
);
```

같은 파일 `_EXPECTED_COLUMNS` 에 항목을 더한다.

```python
    "run_metadata": frozenset({"run_id", "channel", "upload_date"}),
```

`src/notebooklm_st/core/models.py` 에 값 객체를 더한다. 놓는 자리는 `RunSummary` 바로 뒤다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class VideoMetadata:
    """영상에서 뽑아 온 메타데이터.

    영상명과 URL 은 담지 않는다. ``RunSummary`` 에 이미 있어
    중복이 된다.
    """

    channel: str | None
    upload_date: str | None
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/services/test_store.py -v`
Expected: PASS — 새 테스트를 포함해 전부 통과.

- [ ] **Step 5: 검증 4단**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

Expected: 전부 통과. 기존 테스트 수가 줄지 않는다.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/store.py src/notebooklm_st/core/models.py tests/services/test_store.py
git commit -m "$(cat <<'MSG'
✨ feat(store): 영상 메타데이터 테이블 추가

runs 에 컬럼을 더하면 마이그레이션이 없는 이 프로젝트
에서는 기존 DB 를 버려야 한다. 새 테이블은 옛 파일에도
그냥 생기므로 이력과 질문 템플릿이 살아남는다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

### Task 2: 이력에 메타데이터를 저장하고 읽기

**Files:**
- Modify: `src/notebooklm_st/services/run_history.py`
- Test: `tests/services/test_run_history.py`

**Interfaces:**
- Consumes: `models.VideoMetadata`, `run_metadata` 테이블 (Task 1)
- Produces:
  - `run_history.save_run(connection, result, metadata=None) -> int`
  - `run_history.load_metadata(connection, run_id) -> models.VideoMetadata | None`

**배경.** `metadata` 는 **기본값이 있는 세 번째 인자**다. 기존 호출자(`services/runner.py`)를 이 Task 에서 고치지 않아도 테스트가 전부 초록으로 남는다. 연결은 Task 5 가 한다.

- [ ] **Step 1: 실패하는 테스트 쓰기**

`tests/services/test_run_history.py` 맨 끝에 추가한다. `connection` fixture 와 `make_result` 헬퍼는 이미 파일 위쪽에 있다.

```python
def test_save_run_stores_the_metadata(connection) -> None:
    """넘긴 메타데이터가 그대로 돌아온다."""
    metadata = models.VideoMetadata(
        channel="안될공학", upload_date="2026-09-15"
    )

    run_id = run_history.save_run(connection, make_result(), metadata)

    assert run_history.load_metadata(connection, run_id) == metadata


def test_save_run_without_metadata_stores_no_row(connection) -> None:
    """메타데이터를 안 넘기면 행을 만들지 않는다."""
    run_id = run_history.save_run(connection, make_result())

    assert run_history.load_metadata(connection, run_id) is None
    count = connection.execute(
        "SELECT COUNT(*) AS n FROM run_metadata"
    ).fetchone()
    assert count["n"] == 0


def test_load_metadata_is_silent_for_an_unknown_run(connection) -> None:
    """없는 실행 ID 로 물으면 None 이다."""
    assert run_history.load_metadata(connection, 9999) is None


def test_delete_run_removes_its_metadata_too(connection) -> None:
    """실행을 지우면 메타데이터도 함께 사라진다."""
    metadata = models.VideoMetadata(
        channel="안될공학", upload_date="2026-09-15"
    )
    run_id = run_history.save_run(connection, make_result(), metadata)

    run_history.delete_run(connection, run_id)

    assert run_history.load_metadata(connection, run_id) is None
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/services/test_run_history.py -v -k metadata`

Expected: FAIL — `AttributeError: module 'notebooklm_st.services.run_history' has no attribute 'load_metadata'`, 그리고 `save_run()` 이 인자를 3개 받지 못한다는 `TypeError`.

- [ ] **Step 3: 구현**

`src/notebooklm_st/services/run_history.py` 의 `save_run` 시그니처와 본문을 고친다. `connection.commit()` **앞에** 삽입을 넣어 한 커밋에 묶는다.

```python
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
```

본문의 `connection.executemany(...)` 뒤, `connection.commit()` 앞에 넣는다.

```python
    if metadata is not None:
        connection.execute(
            "INSERT INTO run_metadata (run_id, channel, upload_date)"
            " VALUES (?, ?, ?)",
            (run_id, metadata.channel, metadata.upload_date),
        )
```

같은 파일에 조회 함수를 더한다. 자리는 `load_run_items` 뒤다.

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/services/test_run_history.py -v`
Expected: PASS — 새 테스트 4개를 포함해 전부 통과.

`test_delete_run_removes_its_metadata_too` 가 통과하는 것은 `store.connect()` 가 `PRAGMA foreign_keys = ON` 을 켜기 때문이다. 이 테스트가 그 설정의 회귀 감시를 겸한다.

- [ ] **Step 5: 검증 4단**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

Expected: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/run_history.py tests/services/test_run_history.py
git commit -m "$(cat <<'MSG'
✨ feat(history): 영상 메타데이터 저장과 조회 추가

save_run 의 세 번째 인자로 받아 runs·answers 와 같은
커밋에 넣는다. 기존 호출자는 기본값으로 그대로 돈다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

### Task 3: yt-dlp 로 메타데이터 가져오기

**Files:**
- Create: `src/notebooklm_st/services/video_metadata.py`
- Modify: `pyproject.toml` · `uv.lock` (`uv add yt-dlp`)
- Test: `tests/services/test_video_metadata.py` (신규)

**Interfaces:**
- Consumes: `models.VideoMetadata` (Task 1), `core.youtube.extract_video_id`
- Produces:
  - `video_metadata.MetadataResult(metadata: models.VideoMetadata | None, error: str | None)`
  - `video_metadata.fetch(url, runner=subprocess.run, timeout=FETCH_TIMEOUT, tz=None) -> MetadataResult`
  - `video_metadata.RunnerLike = Callable[..., subprocess.CompletedProcess[bytes]]`

**배경 세 가지.**

1. **`fetch` 는 예외를 던지지 않는다.** 호출자는 `runner._work` 의 백그라운드 스레드이고 거기서 예외가 새면 요약 실행 전체가 죽는다. 모든 실패는 `error` 로 수렴한다.
2. **`runner` 를 인자로 뚫는다.** `services/auth.py` 의 `import_credentials` 가 같은 방식이고, 테스트가 자식 프로세스를 실제로 띄우지 않게 한다.
3. **`tz` 를 인자로 뚫는다.** `datetime.fromtimestamp` 는 시스템 로컬 타임존을 쓰는데, 테스트가 그것을 고정할 표준 수단(`time.tzset`)이 **윈도우에 없다.** 운영 코드는 `tz=None`(로컬)로 부르고 테스트만 명시적 타임존을 넣는다.

- [ ] **Step 1: 의존성 추가**

```bash
uv add yt-dlp
```

버전을 좁게 고정하지 않는다. yt-dlp 는 유튜브 변경에 맞춰 자주 릴리스되므로 다시 구울 때 최신을 받는 편이 낫고, 재현성은 `uv.lock` 이 맡는다.

Expected: `pyproject.toml` 의 `dependencies` 에 `yt-dlp>=...` 가 생기고 `uv.lock` 이 갱신된다.

- [ ] **Step 2: 실패하는 테스트 쓰기**

`tests/services/test_video_metadata.py` 를 새로 만든다.

```python
"""영상 메타데이터 조회 테스트."""

import datetime
import json
import subprocess
import sys

from notebooklm_st.services import video_metadata

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxxxxx"
KST = datetime.timezone(datetime.timedelta(hours=9))


class FakeCompleted:
    """``subprocess.run`` 의 반환값을 흉내낸다."""

    def __init__(self, returncode, stdout=b"", stderr=b""):
        """종료 코드와 출력을 저장한다."""
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def fake_runner(result, calls):
    """호출 인자를 기록하고 준비된 결과를 돌려주는 러너를 만든다."""

    def run(args, **kwargs):
        """subprocess.run 을 대신한다."""
        calls.append((args, kwargs))
        if isinstance(result, Exception):
            raise result
        return result

    return run


def payload(**fields) -> bytes:
    """yt-dlp 가 찍을 JSON 한 덩어리를 만든다."""
    return json.dumps(fields).encode("utf-8")


def test_fetch_calls_yt_dlp_with_a_normalized_url() -> None:
    """자기 인터프리터로 부르고 재생목록 파라미터를 떼어 낸다."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    runner = fake_runner(FakeCompleted(0, payload(channel="안될공학")), calls)

    result = video_metadata.fetch(URL, runner=runner)

    assert result.error is None
    args, kwargs = calls[0]
    assert args[0] == sys.executable
    assert args[1:] == [
        "-m",
        "yt_dlp",
        "--no-playlist",
        "-J",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ]
    assert kwargs["capture_output"] is True


def test_fetch_reads_the_channel() -> None:
    """channel 필드를 그대로 가져온다."""
    runner = fake_runner(FakeCompleted(0, payload(channel="안될공학")), [])

    result = video_metadata.fetch(URL, runner=runner)

    assert result.metadata is not None
    assert result.metadata.channel == "안될공학"


def test_fetch_converts_the_timestamp_to_the_given_timezone() -> None:
    """UTC 로는 전날인 시각이 KST 날짜로 나온다."""
    # 1789428600 = 2026-09-14 23:30 UTC = 2026-09-15 08:30 KST
    runner = fake_runner(
        FakeCompleted(
            0, payload(timestamp=1789428600, upload_date="20260914")
        ),
        [],
    )

    result = video_metadata.fetch(URL, runner=runner, tz=KST)

    assert result.metadata is not None
    assert result.metadata.upload_date == "2026-09-15"


def test_fetch_falls_back_to_upload_date_without_a_timestamp() -> None:
    """timestamp 가 없으면 upload_date 의 모양만 바꾼다."""
    runner = fake_runner(
        FakeCompleted(0, payload(upload_date="20260914")), []
    )

    result = video_metadata.fetch(URL, runner=runner, tz=KST)

    assert result.metadata is not None
    assert result.metadata.upload_date == "2026-09-14"


def test_fetch_folds_missing_fields_to_none() -> None:
    """빈 문자열과 없는 키를 모두 None 으로 접는다."""
    runner = fake_runner(FakeCompleted(0, payload(channel="")), [])

    result = video_metadata.fetch(URL, runner=runner)

    assert result.metadata is not None
    assert result.metadata.channel is None
    assert result.metadata.upload_date is None


def test_fetch_reports_a_nonzero_exit() -> None:
    """종료 코드가 0 이 아니면 stderr 끝부분을 사유로 남긴다."""
    runner = fake_runner(
        FakeCompleted(1, b"", b"ERROR: Video unavailable"), []
    )

    result = video_metadata.fetch(URL, runner=runner)

    assert result.metadata is None
    assert "Video unavailable" in result.error


def test_fetch_reports_unparsable_output() -> None:
    """JSON 이 아니면 해석 실패로 남긴다."""
    runner = fake_runner(FakeCompleted(0, b"not json at all"), [])

    result = video_metadata.fetch(URL, runner=runner)

    assert result.metadata is None
    assert "해석하지 못했습니다" in result.error


def test_fetch_reports_a_timeout() -> None:
    """제한 시간을 넘기면 사유에 초가 들어간다."""
    runner = fake_runner(
        subprocess.TimeoutExpired(cmd="yt-dlp", timeout=20.0), []
    )

    result = video_metadata.fetch(URL, runner=runner)

    assert result.metadata is None
    assert "20초" in result.error


def test_fetch_rejects_a_non_video_url() -> None:
    """영상 URL 이 아니면 프로세스를 띄우지 않는다."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    runner = fake_runner(FakeCompleted(0, payload()), calls)

    result = video_metadata.fetch("https://example.com/", runner=runner)

    assert result.metadata is None
    assert result.error == "영상 URL 이 아닙니다."
    assert calls == []
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/services/test_video_metadata.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.services.video_metadata'` (수집 단계에서 파일 전체가 실패한다).

- [ ] **Step 4: 구현**

`src/notebooklm_st/services/video_metadata.py` 를 새로 만든다.

```python
"""영상 메타데이터를 yt-dlp 로 가져온다.

yt-dlp 를 아는 유일한 모듈이다. 파이썬 API 대신 자식 프로세스로
CLI 를 부른다 — ``YoutubeDL`` 에는 전체 시간을 막는 수단이 없어
느린 응답 하나가 요약 실행을 붙잡을 수 있다.

실패를 예외가 아니라 값으로 돌려준다. 호출자가 백그라운드
스레드라 예외가 새면 요약 실행 전체가 죽는다.
"""

import dataclasses
import datetime
import json
import subprocess
import sys
from collections.abc import Callable

from notebooklm_st.core import models, youtube

FETCH_TIMEOUT = 20.0
"""자식 프로세스에 주는 최대 초."""

DETAIL_LIMIT = 500
"""실패 사유로 남길 최대 글자 수."""

RunnerLike = Callable[..., subprocess.CompletedProcess[bytes]]
"""``subprocess.run`` 자리에 넣을 수 있는 것.

키워드 인자가 많아 Protocol 로 적으면 길기만 하다.
"""


@dataclasses.dataclass(frozen=True, slots=True)
class MetadataResult:
    """메타데이터 조회 결과.

    ``metadata`` 와 ``error`` 중 하나만 채워진다.
    """

    metadata: models.VideoMetadata | None
    error: str | None


def fetch(
    url: str,
    runner: RunnerLike = subprocess.run,
    timeout: float = FETCH_TIMEOUT,
    tz: datetime.tzinfo | None = None,
) -> MetadataResult:
    """영상 URL 에서 채널명과 업로드일자를 가져온다.

    ``uv`` 로 부르지 않는다. ``uv`` 는 PATH 에 없을 수 있고, 앱은
    이미 yt-dlp 가 설치된 인터프리터 안에서 돌고 있다.

    Args:
        url: 조회할 영상 URL. 재생목록·추적 파라미터가 붙어 있어도
            영상 ID 만 뽑아 정규 URL 을 다시 짓는다.
        runner: 자식을 돌리는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.
        timeout: 자식에게 주는 최대 초.
        tz: 업로드 시각을 옮길 타임존. ``None`` 이면 시스템 로컬을
            쓴다. 컨테이너는 ``TZ=Asia/Seoul`` 로 돈다.

    Returns:
        메타데이터 또는 사람에게 보여 줄 실패 사유.
    """
    video_id = youtube.extract_video_id(url)
    if video_id is None:
        return MetadataResult(None, "영상 URL 이 아닙니다.")
    try:
        completed = runner(
            [
                sys.executable,
                "-m",
                "yt_dlp",
                "--no-playlist",
                "-J",
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return MetadataResult(
            None,
            f"영상 정보 조회가 {int(timeout)}초를 넘겨 중단했습니다.",
        )
    except OSError as error:
        return MetadataResult(None, f"yt-dlp 를 실행하지 못했습니다: {error}")
    if completed.returncode != 0:
        return MetadataResult(None, _failure_detail(completed.stderr))
    return _read(completed.stdout, tz)


def _read(stdout: bytes, tz: datetime.tzinfo | None) -> MetadataResult:
    """자식의 표준 출력에서 필요한 두 값을 꺼낸다."""
    try:
        info = json.loads(stdout)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return MetadataResult(None, "yt-dlp 출력을 해석하지 못했습니다.")
    if not isinstance(info, dict):
        return MetadataResult(None, "yt-dlp 출력을 해석하지 못했습니다.")
    return MetadataResult(
        models.VideoMetadata(
            channel=_clean(info.get("channel")),
            upload_date=_to_date(
                info.get("timestamp"), info.get("upload_date"), tz
            ),
        ),
        None,
    )


def _clean(value: object) -> str | None:
    """문자열이면 앞뒤 공백을 떼고, 비면 ``None`` 으로 접는다.

    yt-dlp 는 값을 모를 때 키를 빼기도 하고 빈 문자열을 주기도
    한다. 한쪽으로 모아 둔다.
    """
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _to_date(
    timestamp: object, upload_date: object, tz: datetime.tzinfo | None
) -> str | None:
    """업로드 시각을 ``YYYY-MM-DD`` 로 만든다.

    ``timestamp`` 를 먼저 쓴다. yt-dlp 의 ``upload_date`` 는 UTC 라
    한국 시각 이른 아침에 올라온 영상이 전날로 찍히기 때문이다.
    """
    if isinstance(timestamp, int | float) and not isinstance(timestamp, bool):
        try:
            moment = datetime.datetime.fromtimestamp(timestamp, tz)
        except (OSError, OverflowError, ValueError):
            return None
        return moment.strftime("%Y-%m-%d")
    raw = _clean(upload_date)
    if raw is None or len(raw) != 8 or not raw.isdigit():
        return None
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"


def _failure_detail(stderr: bytes, limit: int = DETAIL_LIMIT) -> str:
    """자식의 실패 출력을 화면에 쓸 짧은 문자열로 만든다.

    끝에서 자른다. 실제 원인은 마지막 줄에 있고 앞쪽은 경고로
    채워지는 일이 많다.
    """
    text = stderr.decode("utf-8", errors="replace").strip()
    if not text:
        return "자세한 사유를 알 수 없습니다."
    return text[-limit:]
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/services/test_video_metadata.py -v`
Expected: PASS — 9개 전부 통과.

- [ ] **Step 6: 실제 호출을 눈으로 한 번 확인**

설계 §12-1 이 미검증으로 남긴 것을 여기서 확인한다. **실제 영상 하나로 돌린다.**

```bash
uv run python -c "from notebooklm_st.services import video_metadata as m; r = m.fetch('https://www.youtube.com/watch?v=dQw4w9WgXcQ'); print(r)"
```

Expected: `MetadataResult(metadata=VideoMetadata(channel='...', upload_date='...'), error=None)`.

- **채널명과 날짜가 실제로 채워지는지** 본다. 비어 있으면 `-J` 응답에 그 키가 없다는 뜻이므로 **멈추고 보고한다.**
- 네트워크가 막혀 있거나 yt-dlp 가 낡아 실패하면 `error` 에 사유가 담긴다. 그 경우도 **설계대로 동작한 것**이므로 출력 그대로 기록하고 넘어간다.

- [ ] **Step 7: 검증 4단**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

Expected: 전부 통과.

- [ ] **Step 8: 커밋**

```bash
git add src/notebooklm_st/services/video_metadata.py tests/services/test_video_metadata.py pyproject.toml uv.lock
git commit -m "$(cat <<'MSG'
✨ feat(metadata): yt-dlp 로 영상 정보 가져오기

자식 프로세스로 부른다. 파이썬 API 에는 전체 시간을
막는 수단이 없어 느린 응답이 요약 실행을 붙잡는다.
실패는 예외가 아니라 값으로 돌려준다.

업로드일자는 UTC 가 아니라 로컬 시각으로 옮긴다.
한국 시각 이른 아침 영상이 전날로 찍히기 때문이다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

### Task 4: 요약본에 frontmatter 붙이기

**Files:**
- Modify: `src/notebooklm_st/core/markdown_export.py`
- Test: `tests/core/test_markdown_export.py`

**Interfaces:**
- Consumes: `models.VideoMetadata` (Task 1)
- Produces: `markdown_export.to_markdown(summary, items, metadata=None) -> str`

**배경.** frontmatter 아래 본문은 **한 글자도 바뀌지 않는다.** 기존 테스트 9개가 그 계약을 지키는데, 그중 `test_to_markdown_opens_with_the_title_and_source` 가 `lines[0]` 을 보므로 **그 테스트는 고쳐야 한다** — 이제 0번 줄이 `---` 이다. 나머지는 손대지 않는다.

`url` 값에 주의한다. `make_summary()` 의 `url` 은 `https://youtu.be/dQw4w9WgXcQ` 이고 `video_id` 는 `dQw4w9WgXcQ` 다. frontmatter 는 **정규 URL** 을, 본문 "출처" 줄은 **저장된 원문**을 쓴다. 둘이 다른 것이 정상이다.

- [ ] **Step 1: 기존 테스트 하나를 고치고 새 테스트를 쓴다**

먼저 `tests/core/test_markdown_export.py` 의 기존 테스트를 고친다.

```python
def test_to_markdown_opens_with_the_title_and_source() -> None:
    """frontmatter 다음에 제목을 두고 출처와 실행 시각을 잇는다."""
    text = markdown_export.to_markdown(make_summary(), [make_item()])
    body = text.split("---\n", 2)[2]
    lines = body.splitlines()
    assert lines[1] == "# 어떻게 AI는 생각하는가"
```

`body` 는 두 번째 `---\n` 뒤부터다. `lines[0]` 은 빈 줄이고 `lines[1]` 이 제목이다.

같은 파일 끝에 새 테스트를 추가한다.

```python
def test_to_markdown_writes_frontmatter_without_metadata() -> None:
    """메타데이터가 없어도 title 과 url 은 나온다."""
    text = markdown_export.to_markdown(make_summary(), [make_item()])
    lines = text.splitlines()
    assert lines[0] == "---"
    assert lines[1] == 'title: "어떻게 AI는 생각하는가"'
    assert lines[2] == "url: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert lines[3] == "---"


def test_to_markdown_writes_all_metadata_keys() -> None:
    """채널명과 업로드일자가 있으면 네 줄이 된다."""
    metadata = models.VideoMetadata(
        channel="안될공학", upload_date="2026-09-15"
    )

    text = markdown_export.to_markdown(
        make_summary(), [make_item()], metadata
    )

    assert text.splitlines()[:6] == [
        "---",
        'title: "어떻게 AI는 생각하는가"',
        'channel: "안될공학"',
        "upload_date: 2026-09-15",
        "url: https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "---",
    ]


def test_to_markdown_omits_keys_without_values() -> None:
    """값이 없는 키는 null 이 아니라 아예 빠진다."""
    metadata = models.VideoMetadata(channel=None, upload_date="2026-09-15")

    text = markdown_export.to_markdown(
        make_summary(), [make_item()], metadata
    )

    assert "channel" not in text
    assert "upload_date: 2026-09-15" in text


def test_to_markdown_escapes_quotes_and_backslashes_in_the_title() -> None:
    """제목의 따옴표와 역슬래시가 YAML 을 깨뜨리지 않는다."""
    summary = make_summary(title='그는 "생각"한다 \\ 아마도')

    text = markdown_export.to_markdown(summary, [make_item()])

    assert text.splitlines()[1] == (
        'title: "그는 \\"생각\\"한다 \\\\ 아마도"'
    )


def test_to_markdown_escapes_newlines_in_the_channel() -> None:
    """개행이 든 값도 한 줄로 접힌다."""
    metadata = models.VideoMetadata(
        channel="안될\n공학", upload_date=None
    )

    text = markdown_export.to_markdown(
        make_summary(), [make_item()], metadata
    )

    assert 'channel: "안될\\n공학"' in text


def test_to_markdown_quotes_the_url_without_a_video_id() -> None:
    """영상 ID 가 없는 옛 이력은 저장된 URL 을 따옴표로 감싼다."""
    summary = make_summary(video_id="")

    text = markdown_export.to_markdown(summary, [make_item()])

    assert 'url: "https://youtu.be/dQw4w9WgXcQ"' in text


def test_to_markdown_keeps_the_body_unchanged() -> None:
    """frontmatter 아래 본문은 출처 줄부터 그대로다."""
    text = markdown_export.to_markdown(make_summary(), [make_item()])

    assert "- 출처: https://youtu.be/dQw4w9WgXcQ" in text
    assert "- 실행: 2026-08-31T14:02:11" in text
    assert "## 핵심 주장" in text
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/core/test_markdown_export.py -v`

Expected: FAIL — 새 테스트 7개가 전부 실패한다(`lines[0]` 이 `# 어떻게...` 이고 `---` 가 없다). `to_markdown` 이 세 번째 인자를 받지 못한다는 `TypeError` 도 난다.

- [ ] **Step 3: 구현**

`src/notebooklm_st/core/markdown_export.py` 의 `to_markdown` 을 고친다.

```python
def to_markdown(
    summary: models.RunSummary,
    items: Sequence[models.AnswerItem],
    metadata: models.VideoMetadata | None = None,
) -> str:
    """실행 하나를 마크다운 문서 한 장으로 만든다.

    Args:
        summary: 머리글과 출처에 쓸 실행 요약.
        items: 문서에 담을 답변 목록. 화면이 그리는 것과 같은 목록을
            받으므로 인용을 숨긴 상태면 인용이 비어 들어온다.
        metadata: 영상에서 뽑아 온 메타데이터. 없으면 frontmatter 에
            ``title`` 과 ``url`` 만 남는다.

    Returns:
        YAML frontmatter 로 시작하고 줄바꿈 하나로 끝나는 마크다운
        문서.
    """
    blocks = [
        _frontmatter(summary, metadata),
        f"# {summary.title or summary.video_id}",
        f"- 출처: {summary.url}\n- 실행: {summary.created_at}",
    ]
    blocks.extend(_item_block(item) for item in items)
    return "\n\n".join(blocks) + "\n"
```

같은 파일의 `_REPEATED_SPACE` 아래에 상수를 더한다.

```python
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
"""YAML 문자열에서 지울 제어문자.

탭·개행·캐리지리턴은 이스케이프해서 살리므로 여기서 뺀다.
"""
```

`_item_block` 위에 헬퍼 셋을 더한다.

```python
def _frontmatter(
    summary: models.RunSummary, metadata: models.VideoMetadata | None
) -> str:
    """문서 맨 앞에 둘 YAML 블록을 만든다.

    값이 없는 키는 ``null`` 로 적지 않고 아예 뺀다. ``null`` 을
    적으면 읽는 쪽이 "값이 null 인 채널" 과 "모르는 채널" 을
    구분하지 못한다.
    """
    lines = [f"title: {_yaml_string(summary.title or summary.video_id)}"]
    if metadata is not None and metadata.channel:
        lines.append(f"channel: {_yaml_string(metadata.channel)}")
    if metadata is not None and metadata.upload_date:
        lines.append(f"upload_date: {metadata.upload_date}")
    lines.append(f"url: {_source_url(summary)}")
    return "---\n" + "\n".join(lines) + "\n---"


def _source_url(summary: models.RunSummary) -> str:
    """frontmatter 에 적을 URL 을 고른다.

    저장된 원문에는 재생목록·추적 파라미터나 ``#`` 이 붙어 있을 수
    있어 따옴표 없는 YAML 값으로 쓰기 위험하다. 검증된 영상 ID 로
    정규 URL 을 다시 짓고, ID 가 없는 옛 이력만 원문을 따옴표로
    감싼다.
    """
    if summary.video_id:
        return f"https://www.youtube.com/watch?v={summary.video_id}"
    return _yaml_string(summary.url)


def _yaml_string(value: str) -> str:
    """큰따옴표로 감싼 YAML 스칼라로 만든다.

    역슬래시를 먼저 바꾼다. 나중에 바꾸면 앞서 넣은 이스케이프까지
    다시 이스케이프된다.
    """
    escaped = (
        _CONTROL.sub("", value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/core/test_markdown_export.py -v`
Expected: PASS — 기존 것과 새것 전부 통과.

- [ ] **Step 5: 검증 4단**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

Expected: 전부 통과. `tests/pages/test_history.py` 도 그대로 통과한다 — `to_markdown` 의 새 인자에 기본값이 있기 때문이다.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/core/markdown_export.py tests/core/test_markdown_export.py
git commit -m "$(cat <<'MSG'
✨ feat(export): 요약본에 YAML frontmatter 붙이기

title 과 url 은 늘 나오고, 채널명과 업로드일자는 값이
있을 때만 줄이 생긴다. 값이 없는 키를 null 로 적으면
읽는 쪽이 모르는 값과 구분하지 못한다.

url 은 저장된 원문이 아니라 영상 ID 로 다시 지은 정규
URL 이다. 원문에 붙은 파라미터가 따옴표 없는 YAML 값을
깨뜨릴 수 있다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

### Task 5: 실행과 화면에 잇기

**Files:**
- Modify: `src/notebooklm_st/services/runner.py`
- Modify: `src/notebooklm_st/pages/history.py`
- Modify: `README.md`
- Test: `tests/services/test_runner_start.py`, `tests/pages/test_history.py`

**Interfaces:**
- Consumes: `video_metadata.fetch` (Task 3), `run_history.save_run`·`load_metadata` (Task 2), `markdown_export.to_markdown` (Task 4)
- Produces: 없음 — 마지막 Task 다

**배경.** 조회는 파이프라인 **앞**에서 한다. 이미 백그라운드 스레드 안이므로 화면이 멈추지 않는다. **실패해도 `return` 하지 않는다** — 메타데이터는 부가물이고 요약이 본체다.

- [ ] **Step 1: 실패하는 테스트 쓰기**

`tests/services/test_runner_start.py` 맨 끝에 추가한다. 이 파일에는 `db_path` fixture, `make_questions`, `wait_for`, `URL` 이 이미 있다.

```python
def test_start_run_saves_the_fetched_metadata(db_path, monkeypatch) -> None:
    """조회한 메타데이터가 이력과 함께 저장된다."""
    monkeypatch.setattr(
        runner.video_metadata,
        "fetch",
        lambda url, **kwargs: runner.video_metadata.MetadataResult(
            models.VideoMetadata(channel="안될공학", upload_date="2026-09-15"),
            None,
        ),
    )
    registry = runs.RunRegistry()

    async def pipeline(url, questions, on_progress, **kwargs):
        """답변 하나를 돌려주는 가짜 파이프라인."""
        return models.RunResult(
            url=url,
            video_id="dQw4w9WgXcQ",
            title="어떤 영상",
            items=(
                models.AnswerItem(
                    question_title="제목1",
                    question_text="질문1",
                    answer="답",
                    citations=(),
                    error=None,
                ),
            ),
        )

    handle = runner.start_run(
        registry, URL, make_questions("질문1"), db_path, pipeline
    )
    wait_for(registry, handle.run_id)

    connection = store.connect(db_path)
    try:
        saved = run_history.list_runs(connection)
        metadata = run_history.load_metadata(connection, saved[0].id)
    finally:
        connection.close()
    assert metadata is not None
    assert metadata.channel == "안될공학"


def test_start_run_survives_a_metadata_failure(db_path, monkeypatch) -> None:
    """메타데이터 조회가 실패해도 요약은 끝까지 간다."""
    monkeypatch.setattr(
        runner.video_metadata,
        "fetch",
        lambda url, **kwargs: runner.video_metadata.MetadataResult(
            None, "영상 정보를 못 가져왔습니다."
        ),
    )
    registry = runs.RunRegistry()

    async def pipeline(url, questions, on_progress, **kwargs):
        """답변 하나를 돌려주는 가짜 파이프라인."""
        return models.RunResult(
            url=url,
            video_id="dQw4w9WgXcQ",
            title="어떤 영상",
            items=(
                models.AnswerItem(
                    question_title="제목1",
                    question_text="질문1",
                    answer="답",
                    citations=(),
                    error=None,
                ),
            ),
        )

    handle = runner.start_run(
        registry, URL, make_questions("질문1"), db_path, pipeline
    )
    finished = wait_for(registry, handle.run_id)

    assert finished.status == "done"
    connection = store.connect(db_path)
    try:
        saved = run_history.list_runs(connection)
        metadata = run_history.load_metadata(connection, saved[0].id)
    finally:
        connection.close()
    assert len(saved) == 1
    assert metadata is None
    assert any("못 가져왔습니다" in line for line in finished.progress)
```

`tests/pages/test_history.py` 맨 끝에도 하나 추가한다. 이 파일에는
`script`, `make_result`, `app_db` fixture 가 이미 있다.

```python
def test_download_works_for_a_run_with_metadata(app_db) -> None:
    """메타데이터가 있는 실행도 내려받기 버튼이 그대로 나온다."""
    run_history.save_run(
        app_db,
        make_result(title="밸류에이션 강의"),
        models.VideoMetadata(channel="안될공학", upload_date="2026-09-15"),
    )

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.get("download_button")) == 1
```

**이 테스트는 frontmatter 내용을 보지 않는다.** Streamlit 의
`download_button` 은 proto 에 엔드포인트 URL 만 담고 실제 바이트는 서버가
들고 있어서, `AppTest` 로 내려받을 데이터를 읽을 수 없다(기존
`test_selected_run_offers_a_markdown_download` 도 `proto.url` 의 확장자만
본다). 여기서 확인하는 것은 **화면이 메타데이터를 읽어 넘기는 경로가 예외
없이 돈다는 것**이고, frontmatter 내용 자체는 Task 4 의 `to_markdown` 단위
테스트가 못 박는다.

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/services/test_runner_start.py -v -k metadata`

Expected: FAIL — `AttributeError: module 'notebooklm_st.services.runner' has no attribute 'video_metadata'`.

- [ ] **Step 3: `runner.py` 구현**

`src/notebooklm_st/services/runner.py` 의 import 줄에 모듈을 더한다.

```python
from notebooklm_st.services import (
    nlm,
    run_history,
    runs,
    store,
    video_metadata,
)
```

`_work` 의 `on_progress` 정의 **뒤**, `try:` **앞**에 넣는다.

```python
    on_progress("영상 정보 확인 중")
    meta = video_metadata.fetch(url)
    if meta.error is not None:
        # 메타데이터는 부가물이다. 못 가져와도 요약은 끝까지 간다.
        logger.info("실행 %s 메타데이터 실패: %s", run_id, meta.error)
        on_progress(f"영상 정보를 가져오지 못했습니다: {meta.error}")
```

같은 함수 아래쪽 저장부를 고친다.

```python
            run_history.save_run(connection, result, meta.metadata)
```

- [ ] **Step 4: `history.py` 구현**

`src/notebooklm_st/pages/history.py` 의 `_render_download` 호출부를 고친다.

```python
    metadata = run_history.load_metadata(connection, selected.id)
    _render_download(selected, items, metadata)
```

`_render_download` 의 시그니처와 본문을 고친다.

```python
def _render_download(
    selected: models.RunSummary,
    items: Sequence[models.AnswerItem],
    metadata: models.VideoMetadata | None,
) -> None:
    """지금 화면에 그리는 목록을 마크다운 파일로 내준다.

    답변 목록을 렌더와 나눠 쓴다. 인용을 숨긴 상태면 걸러진 사본이
    그대로 넘어오므로 화면과 내려받은 파일이 어긋날 수 없다.
    """
    st.download_button(
        "마크다운 내려받기",
        data=markdown_export.to_markdown(selected, items, metadata),
        file_name=markdown_export.to_filename(
            selected.title, selected.video_id
        ),
        mime="text/markdown",
        key=f"history_download_{selected.id}",
        help="지금 보이는 그대로 내려받습니다."
        " 인용을 숨긴 동안에는 숨긴 상태로 담깁니다.",
    )
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/services/test_runner_start.py tests/pages/test_history.py -v`
Expected: PASS — 새 테스트 3개를 포함해 전부 통과.

- [ ] **Step 6: README 갱신**

`README.md` 에서 마크다운 내려받기를 설명하는 대목을 찾는다.

```bash
grep -n "마크다운\|내려받" README.md
```

찾은 자리에 한 문단을 더한다. 문구는 아래를 쓴다.

```markdown
내려받은 문서 맨 앞에는 YAML frontmatter 가 붙는다. 영상명과 URL 은
항상 들어가고, 채널명과 업로드일자는 실행 시점에 yt-dlp 로 가져와
저장해 둔 값이 있을 때만 들어간다. 조회에 실패했거나 그 기능이
없던 때의 이력이면 두 줄이 빠진 채로 나온다.
```

`grep` 이 아무것도 찾지 못하면 **멈추고 보고한다.** 임의의 자리에 넣지 않는다.

- [ ] **Step 7: 검증 4단**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

Expected: 전부 통과.

- [ ] **Step 8: 커밋**

```bash
git add src/notebooklm_st/services/runner.py src/notebooklm_st/pages/history.py tests/services/test_runner_start.py tests/pages/test_history.py README.md
git commit -m "$(cat <<'MSG'
✨ feat(runner): 실행할 때 영상 정보를 함께 가져오기

파이프라인 앞에서 조회한다. 이미 백그라운드 스레드
안이라 화면이 멈추지 않는다. 실패하면 진행 문구로
알리고 요약은 그대로 진행한다.

이력 화면은 저장된 메타데이터를 읽어 내려받는 문서의
frontmatter 에 싣는다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

## 완료 조건

R3 이 끝나면 아래가 모두 참이어야 한다.

- [ ] 요약을 새로 실행하면 진행 문구에 "영상 정보 확인 중" 이 보인다
- [ ] 그 실행을 이력에서 내려받으면 맨 앞에 `---` 로 시작하는 frontmatter 가 있고 `title`·`channel`·`upload_date`·`url` 네 줄이 들어 있다
- [ ] R3 이전에 만들어진 옛 이력을 내려받으면 `title`·`url` 두 줄만 있는 frontmatter 가 나오고 **오류가 나지 않는다**
- [ ] 홈서버의 기존 `questions.db` 를 그대로 열 수 있다 — 질문 템플릿과 실행 이력이 남아 있다
- [ ] 네트워크를 끊고 요약을 실행해도 요약이 끝까지 간다
- [ ] `uv run pytest` 가 전부 통과하고 테스트 수가 R2 종료 시점보다 늘었다

## R4 로 넘기는 것

| 것 | 상태 |
|---|---|
| frontmatter 형식 | 확정. outline 에 실을 때 그대로 쓴다 |
| `run_metadata` 테이블 | R4 가 저장소를 outline 으로 옮길 때 이 테이블의 운명을 정한다 |
| 본문 "개요" 의 "모름" | 남아 있다. 고치려면 질의 파이프라인을 건드려야 한다 |
| 옛 이력의 메타데이터 소급 채우기 | 하지 않았다. 필요해지면 별도로 다룬다 |
