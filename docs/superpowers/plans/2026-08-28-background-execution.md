# 백그라운드 실행 전환 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 질의 실행을 백그라운드 스레드로 옮겨, 사용자가 페이지를 이동해도 작업이 중단되지 않고 결과가 이력에 남게 한다.

**Architecture:** 질의 페이지는 실행을 시작만 하고 즉시 반환한다. 실행 상태는 `@st.cache_resource` 로 감싼 레지스트리에 두어 모든 세션·탭이 공유하고, 백그라운드 스레드가 완료 시 DB 에 직접 저장한다. 대시보드 페이지가 1초 간격 프래그먼트로 레지스트리를 읽어 진행 상황을 보여준다.

**Tech Stack:** Python 3.13, Streamlit 1.62, notebooklm-py 0.8.1, SQLite, uv / ruff / mypy / pytest

**Spec:** `docs/superpowers/specs/2026-08-28-background-execution-design.md`

## Global Constraints

프로젝트 규칙 `.claude/rules/streamlit-implement.md` 에서 온 제약이다. 모든 태스크에 암묵적으로 적용된다.

- Python **3.13**. `from __future__ import annotations` 를 넣지 않는다.
- 줄 길이 **최대 80자**. 들여쓰기는 스페이스 4칸.
- 모든 명령에 `uv run` 을 붙인다. **`uv` 는 PATH 에 없다.** 전체 경로를 쓴다:
  ```bash
  UV="/c/Users/susot/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe"
  ```
- 모든 모듈·클래스·함수에 Google 형식 `"""` 독스트링. `src/` 와 `tests/` 양쪽 모두. 예외를 던지면 `Raises:` 절을 추가한다.
- 모든 함수에 인자·반환 타입. **단 `tests/services/test_nlm.py` 와 `test_nlm_cleanup.py` 의 테스트 함수에는 `-> None` 을 붙이지 않는다**(mypy `var-annotated` 때문에 그 두 파일만 예외). 새로 만드는 테스트에는 붙인다.
- `AppTest.from_function` 에 넘기는 `script()` 에는 한 줄 독스트링을 붙이되 타입 힌트는 붙이지 않는다.
- **`core/` 와 `services/` 에서 `import streamlit` 을 금지한다.**
- 개별 클래스·함수 import 금지. `typing`, `collections.abc` 심볼은 허용. `import streamlit as st` 는 허용.
- `except:` 와 맨 `except Exception:` 금지 — **단 이 계획의 Task 2 스레드 최상위는 예외로 허용한다**(설계 문서 9장). 사유 주석을 반드시 단다.
- 위젯에는 `key=` 를 명시한다. `st.session_state` 키는 모듈 상수로 정의한다.
- 한 파일이 300줄을 넘으면 분리를 검토한다.
- 커밋 메시지: `<emoji> <type>(<scope>): <한국어 명령형 제목 50자 이내>` + 빈 줄 + 트레일러. 트레일러는 아래를 **그대로 복사**한다.
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  ```
- `push` 금지, `--force`/`--no-verify` 금지. 브랜치는 `master` 하나뿐이다.
- 작업 완료 전 4종 검증이 전부 통과해야 한다.
  ```bash
  "$UV" run ruff format .
  "$UV" run ruff check --fix .
  "$UV" run mypy src tests
  "$UV" run pytest
  ```

## 이 계획에만 적용되는 제약 — 실측으로 확인한 사실

착수 전 실험으로 확정한 내용이다. 추측이 아니다.

| 사실 | 근거 | 영향 |
|---|---|---|
| `@st.cache_resource` 객체는 **세션 간 공유**된다 | 서로 다른 두 `AppTest` 세션이 같은 `id` 를 받고 값이 누적됨 | 레지스트리를 여기 둔다 |
| `@st.fragment(run_every=)` 는 `AppTest` 에서 **렌더된다** | 예외 없이 통과 | 대시보드 테스트가 가능하다 |
| `AppTest` 는 `run_every` 로 **자동 재실행하지 않는다** | 1초 대기 후에도 호출 횟수 1회 유지 | 폴링은 `app.run()` 반복으로 시뮬레이션한다 |
| `app.run()` 을 다시 부르면 프래그먼트가 **다시 실행된다** | 호출 횟수 1 → 2 | 테스트가 결정적으로 유지된다 |
| **프래그먼트가 상태를 바꾸면 무한 재실행 → 타임아웃** | `session_state` 증가 코드에서 `AppTest script run timed out` | **대시보드 프래그먼트는 레지스트리를 읽기만 한다** |

마지막 줄이 가장 중요하다. 대시보드에서 자동 정리·자동 갱신 같은 상태 변경을 넣으면 앱이 멈춘다. 사용자 클릭으로만 상태를 바꾼다.

## 파일 구조

| 파일 | 책임 | 태스크 |
|---|---|---|
| `src/notebooklm_st/services/runner.py` | 실행 핸들·레지스트리 (순수 자료구조 + 락) | 1 |
| `src/notebooklm_st/services/runner.py` | 백그라운드 스레드 시작·워커 | 2 |
| `src/notebooklm_st/session.py` | 레지스트리 접근자 추가 | 3 |
| `src/notebooklm_st/components/run_progress.py` | 폐기 후 재작성 — 실행 카드 렌더 | 4 |
| `src/notebooklm_st/pages/dashboard.py` | 실행 현황 화면 | 5 |
| `src/notebooklm_st/app.py` | 대시보드 페이지 등록 | 5 |
| `src/notebooklm_st/pages/ask.py` | 트리거 전용으로 단순화 | 6 |

**바뀌지 않는 것**: `services/nlm.py`, `services/store.py`, `core/` 전체, `components/answer_view.py`, `pages/question_admin.py`, `pages/history.py`, `pages/maintenance.py`.

파이프라인이 이미 Streamlit 을 모르고 `on_progress` 콜백만 받기 때문에, 그 콜백이 `st.write` 대신 레지스트리에 append 하면 파이프라인 코드는 한 줄도 바뀌지 않는다.

---

### Task 1: 실행 핸들과 레지스트리

스레드는 아직 없다. 순수 자료구조와 락만 만든다. Streamlit 을 모르므로 결정적으로 테스트할 수 있다.

**Files:**
- Create: `src/notebooklm_st/services/runner.py`
- Test: `tests/services/test_runner.py`

**Interfaces:**
- Consumes: `models.RunResult` (`core/models.py`)
- Produces:
  - `runner.RunHandle` — 필드: `run_id: str`, `url: str`, `video_id: str`, `question_texts: tuple[str, ...]`, `started_at: str`, `status: Literal["running", "done", "failed"]`, `progress: list[str]`, `result: models.RunResult | None`, `error_message: str | None`, `error_level: Literal["info", "error"] | None`, `finished_at: str | None`
  - `runner.RunRegistry` — `create(url, video_id, question_texts) -> RunHandle`, `get(run_id) -> RunHandle | None`, `list_all() -> list[RunHandle]`, `running_count() -> int`, `append_progress(run_id, message) -> None`, `finish(run_id, result) -> None`, `fail(run_id, message, level) -> None`, `discard(run_id) -> None`

  Task 2~6 이 전부 이 이름에 의존한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/services/test_runner.py`:

```python
"""실행 레지스트리 테스트."""

from notebooklm_st.core import models
from notebooklm_st.services import runner


def make_result() -> models.RunResult:
    """테스트용 실행 결과를 만든다."""
    return models.RunResult(
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        items=(
            models.AnswerItem(
                question_text="핵심 주장은?",
                answer="세 가지다.",
                citations=(),
                error=None,
            ),
        ),
    )


def test_create_returns_a_running_handle() -> None:
    """새로 만든 실행은 running 상태로 시작한다."""
    registry = runner.RunRegistry()
    handle = registry.create(
        "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", ("핵심 주장은?",)
    )
    assert handle.status == "running"
    assert handle.progress == []
    assert handle.result is None
    assert handle.error_message is None
    assert handle.finished_at is None
    assert handle.started_at


def test_create_gives_each_run_a_distinct_id() -> None:
    """실행마다 서로 다른 ID 를 준다."""
    registry = runner.RunRegistry()
    first = registry.create("u1", "v1", ("q",))
    second = registry.create("u2", "v2", ("q",))
    assert first.run_id != second.run_id


def test_get_returns_none_for_unknown_id() -> None:
    """없는 ID 를 조회하면 None 을 돌려준다."""
    registry = runner.RunRegistry()
    assert registry.get("없는-id") is None


def test_append_progress_accumulates_messages() -> None:
    """진행 문구가 순서대로 쌓인다."""
    registry = runner.RunRegistry()
    handle = registry.create("u", "v", ("q",))
    registry.append_progress(handle.run_id, "1단계")
    registry.append_progress(handle.run_id, "2단계")
    stored = registry.get(handle.run_id)
    assert stored is not None
    assert stored.progress == ["1단계", "2단계"]


def test_append_progress_ignores_unknown_id() -> None:
    """없는 ID 에 진행을 기록해도 예외를 던지지 않는다."""
    registry = runner.RunRegistry()
    registry.append_progress("없는-id", "무시됨")


def test_finish_records_result_and_status() -> None:
    """완료하면 결과와 종료 시각이 남는다."""
    registry = runner.RunRegistry()
    handle = registry.create("u", "v", ("q",))
    result = make_result()
    registry.finish(handle.run_id, result)
    stored = registry.get(handle.run_id)
    assert stored is not None
    assert stored.status == "done"
    assert stored.result == result
    assert stored.finished_at
    assert stored.error_message is None


def test_fail_records_message_and_level() -> None:
    """실패하면 사용자 문구와 표시 수준이 남는다."""
    registry = runner.RunRegistry()
    handle = registry.create("u", "v", ("q",))
    registry.fail(handle.run_id, "자막이 없습니다.", "info")
    stored = registry.get(handle.run_id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error_message == "자막이 없습니다."
    assert stored.error_level == "info"
    assert stored.result is None
    assert stored.finished_at


def test_running_count_counts_only_running_runs() -> None:
    """진행 중인 실행만 센다."""
    registry = runner.RunRegistry()
    first = registry.create("u1", "v1", ("q",))
    registry.create("u2", "v2", ("q",))
    assert registry.running_count() == 2
    registry.finish(first.run_id, make_result())
    assert registry.running_count() == 1


def test_list_all_is_newest_first() -> None:
    """가장 최근에 만든 실행이 목록 앞에 온다."""
    registry = runner.RunRegistry()
    first = registry.create("u1", "v1", ("q",))
    second = registry.create("u2", "v2", ("q",))
    assert [item.run_id for item in registry.list_all()] == [
        second.run_id,
        first.run_id,
    ]


def test_list_all_returns_copies() -> None:
    """목록이 돌려준 핸들을 바꿔도 레지스트리는 영향받지 않는다."""
    registry = runner.RunRegistry()
    handle = registry.create("u", "v", ("q",))
    borrowed = registry.list_all()[0]
    borrowed.progress.append("바깥에서 추가")
    borrowed.status = "done"
    stored = registry.get(handle.run_id)
    assert stored is not None
    assert stored.progress == []
    assert stored.status == "running"


def test_discard_removes_the_handle() -> None:
    """지운 실행은 목록에서 사라진다."""
    registry = runner.RunRegistry()
    handle = registry.create("u", "v", ("q",))
    registry.discard(handle.run_id)
    assert registry.get(handle.run_id) is None
    assert registry.list_all() == []


def test_discard_ignores_unknown_id() -> None:
    """없는 ID 를 지워도 예외를 던지지 않는다."""
    registry = runner.RunRegistry()
    registry.discard("없는-id")
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
"$UV" run pytest tests/services/test_runner.py -v
```

기대: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.services.runner'`

- [ ] **Step 3: 최소 구현 작성**

`src/notebooklm_st/services/runner.py`:

```python
"""질의 실행을 백그라운드로 돌리고 그 상태를 보관한다."""

import dataclasses
import datetime
import threading
import uuid
from typing import Literal

from notebooklm_st.core import models

RunStatus = Literal["running", "done", "failed"]
MessageLevel = Literal["info", "error"]


@dataclasses.dataclass
class RunHandle:
    """진행 중이거나 끝난 실행 하나.

    다른 값 객체와 달리 frozen 이 아니다. 백그라운드 스레드가 상태를
    갱신하며, 동시 접근은 ``RunRegistry`` 의 락이 막는다.
    """

    run_id: str
    url: str
    video_id: str
    question_texts: tuple[str, ...]
    started_at: str
    status: RunStatus
    progress: list[str]
    result: models.RunResult | None
    error_message: str | None
    error_level: MessageLevel | None
    finished_at: str | None


class RunRegistry:
    """실행 핸들을 세션 간에 공유하는 보관소.

    모든 공개 메서드가 락 안에서 동작한다. 화면과 스레드가 동시에
    접근하므로 밖에서 락을 잡을 필요가 없다.
    """

    def __init__(self) -> None:
        """빈 보관소를 만든다."""
        self._lock = threading.Lock()
        self._handles: dict[str, RunHandle] = {}

    def create(
        self,
        url: str,
        video_id: str,
        question_texts: tuple[str, ...],
    ) -> RunHandle:
        """새 실행을 running 상태로 등록한다.

        Args:
            url: 질의할 영상 URL.
            video_id: URL 에서 뽑은 영상 ID.
            question_texts: 물어볼 질문 본문들.

        Returns:
            등록된 핸들. 레지스트리가 보관하는 것과 같은 객체가 아니라
            호출자가 ``run_id`` 를 얻는 용도다.
        """
        handle = RunHandle(
            run_id=uuid.uuid4().hex[:8],
            url=url,
            video_id=video_id,
            question_texts=question_texts,
            started_at=_now(),
            status="running",
            progress=[],
            result=None,
            error_message=None,
            error_level=None,
            finished_at=None,
        )
        with self._lock:
            self._handles[handle.run_id] = handle
        return _copy(handle)

    def get(self, run_id: str) -> RunHandle | None:
        """실행 하나를 조회한다.

        Args:
            run_id: 조회할 실행 ID.

        Returns:
            복사본. 그런 실행이 없으면 ``None``.
        """
        with self._lock:
            handle = self._handles.get(run_id)
            return _copy(handle) if handle is not None else None

    def list_all(self) -> list[RunHandle]:
        """모든 실행을 최근 것부터 돌려준다.

        Returns:
            복사본 목록. 화면이 순회하는 동안 스레드가 바꿔도 안전하다.
        """
        with self._lock:
            return [_copy(handle) for handle in reversed(self._handles.values())]

    def running_count(self) -> int:
        """진행 중인 실행 개수를 센다.

        Returns:
            ``status`` 가 running 인 실행 수.
        """
        with self._lock:
            return sum(
                1
                for handle in self._handles.values()
                if handle.status == "running"
            )

    def append_progress(self, run_id: str, message: str) -> None:
        """진행 문구를 덧붙인다. 없는 ID 면 조용히 넘어간다.

        Args:
            run_id: 대상 실행 ID.
            message: 기록할 진행 문구.
        """
        with self._lock:
            handle = self._handles.get(run_id)
            if handle is not None:
                handle.progress.append(message)

    def finish(self, run_id: str, result: models.RunResult) -> None:
        """실행을 완료로 표시한다. 없는 ID 면 조용히 넘어간다.

        Args:
            run_id: 대상 실행 ID.
            result: 파이프라인이 돌려준 결과.
        """
        with self._lock:
            handle = self._handles.get(run_id)
            if handle is not None:
                handle.status = "done"
                handle.result = result
                handle.finished_at = _now()

    def fail(
        self, run_id: str, message: str, level: MessageLevel
    ) -> None:
        """실행을 실패로 표시한다. 없는 ID 면 조용히 넘어간다.

        Args:
            run_id: 대상 실행 ID.
            message: 화면에 보여 줄 사용자 문구.
            level: 표시 수준. 자막 없는 영상 같은 정상 결과는 info 다.
        """
        with self._lock:
            handle = self._handles.get(run_id)
            if handle is not None:
                handle.status = "failed"
                handle.error_message = message
                handle.error_level = level
                handle.finished_at = _now()

    def discard(self, run_id: str) -> None:
        """실행을 목록에서 지운다. 없는 ID 면 조용히 넘어간다.

        이력은 DB 에 남으므로 여기서 지워도 기록이 사라지지 않는다.

        Args:
            run_id: 지울 실행 ID.
        """
        with self._lock:
            self._handles.pop(run_id, None)


def _copy(handle: RunHandle) -> RunHandle:
    """진행 목록까지 새로 만든 복사본을 돌려준다."""
    return dataclasses.replace(handle, progress=list(handle.progress))


def _now() -> str:
    """현재 로컬 시각을 초 단위 ISO 문자열로 돌려준다."""
    return datetime.datetime.now().isoformat(timespec="seconds")
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
"$UV" run pytest tests/services/test_runner.py -v
```

기대: PASS (12 passed)

- [ ] **Step 5: 4종 검증 실행**

```bash
"$UV" run ruff format .
"$UV" run ruff check --fix .
"$UV" run mypy src tests
"$UV" run pytest
```

기대: 전부 통과. `pytest` 는 기존 101개도 함께 도니 전체 통과를 확인한다.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/runner.py tests/services/test_runner.py
git commit -m "✨ feat(services): 실행 레지스트리 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: 백그라운드 실행 시작

Task 1 의 레지스트리 위에 스레드를 얹는다. 파이프라인을 주입받게 만들어 실제 API 없이 검증한다.

**Files:**
- Modify: `src/notebooklm_st/services/runner.py` (`_copy` 정의 **바로 위**에 공개 함수와 워커를 추가)
- Test: `tests/services/test_runner_start.py`

**Interfaces:**
- Consumes: Task 1 의 `RunRegistry`, `nlm.run_pipeline`, `store.connect` / `store.save_run`, `errors.to_message`, `youtube.extract_video_id`
- Produces:
  - `runner.PipelineCallable` — `Callable[..., Awaitable[models.RunResult]]`
  - `runner.start_run(registry, url, questions, db_path, pipeline=nlm.run_pipeline) -> RunHandle`

  Task 6 이 `start_run` 을 부른다.

**설계 근거 (설계 문서 5.2):** 스레드는 Streamlit API 를 부르지 않는다. DB 커넥션을 새로 열고 닫는다. `save_run` 을 먼저 하고 `finish` 를 나중에 한다 — 순서가 뒤바뀌면 화면이 "완료" 를 본 직후 이력을 조회했을 때 아직 없을 수 있다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/services/test_runner_start.py`:

```python
"""백그라운드 실행 시작 테스트."""

import pathlib
import sqlite3
from collections.abc import Iterator

import pytest
from notebooklm import exceptions

from notebooklm_st.core import models
from notebooklm_st.services import runner, store

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture
def db_path(tmp_path) -> Iterator[pathlib.Path]:
    """스키마가 준비된 임시 DB 경로를 준다."""
    path = tmp_path / "runner.db"
    connection = store.connect(path)
    connection.close()
    yield path


def make_questions(*texts: str) -> list[models.Question]:
    """테스트용 질문 목록을 만든다."""
    return [
        models.Question(
            id=index,
            text=text,
            created_at="2026-08-28T10:00:00",
            updated_at="2026-08-28T10:00:00",
        )
        for index, text in enumerate(texts, start=1)
    ]


def wait_for(registry: runner.RunRegistry, run_id: str) -> runner.RunHandle:
    """실행이 끝날 때까지 기다렸다가 핸들을 돌려준다."""
    runner.join_all(timeout=5.0)
    handle = registry.get(run_id)
    assert handle is not None
    assert handle.status != "running"
    return handle


def test_successful_run_saves_history_and_marks_done(db_path) -> None:
    """성공하면 이력에 저장하고 done 으로 표시한다."""
    registry = runner.RunRegistry()

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """진행 문구를 남기고 결과를 돌려주는 가짜."""
        on_progress("자막 인덱싱 중")
        return models.RunResult(
            url=url,
            video_id="dQw4w9WgXcQ",
            items=(
                models.AnswerItem(
                    question_text=questions[0].text,
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                ),
            ),
        )

    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        pipeline=fake_pipeline,
    )
    handle = wait_for(registry, started.run_id)

    assert handle.status == "done"
    assert handle.result is not None
    assert handle.progress == ["자막 인덱싱 중"]
    connection = sqlite3.connect(db_path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    finally:
        connection.close()
    assert count == 1


def test_library_error_is_recorded_as_user_message(db_path) -> None:
    """라이브러리 예외는 사용자 문구로 바뀌어 기록된다."""
    registry = runner.RunRegistry()

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """항상 자막 없음 예외를 던지는 가짜."""
        raise exceptions.SourceAddError(url)

    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        pipeline=fake_pipeline,
    )
    handle = wait_for(registry, started.run_id)

    assert handle.status == "failed"
    assert handle.error_level == "info"
    assert "자막" in (handle.error_message or "")


def test_unexpected_error_does_not_leave_the_run_running(db_path) -> None:
    """예상 못 한 예외가 나도 실행이 running 에 머물지 않는다."""
    registry = runner.RunRegistry()

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """라이브러리 예외가 아닌 오류를 던지는 가짜."""
        raise RuntimeError("예상 못 한 오류")

    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        pipeline=fake_pipeline,
    )
    handle = wait_for(registry, started.run_id)

    assert handle.status == "failed"
    assert handle.error_level == "error"
    assert handle.error_message


def test_failed_run_is_not_saved_to_history(db_path) -> None:
    """실패한 실행은 이력에 남기지 않는다."""
    registry = runner.RunRegistry()

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """항상 실패하는 가짜."""
        raise exceptions.SourceAddError(url)

    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        pipeline=fake_pipeline,
    )
    wait_for(registry, started.run_id)

    connection = sqlite3.connect(db_path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    finally:
        connection.close()
    assert count == 0


def test_video_id_is_extracted_from_the_url(db_path) -> None:
    """핸들에 URL 에서 뽑은 영상 ID 가 담긴다."""
    registry = runner.RunRegistry()

    async def fake_pipeline(url, questions, on_progress, **kwargs):
        """즉시 빈 결과를 돌려주는 가짜."""
        return models.RunResult(url=url, video_id="", items=())

    started = runner.start_run(
        registry,
        URL,
        make_questions("핵심 주장은?"),
        db_path,
        pipeline=fake_pipeline,
    )
    wait_for(registry, started.run_id)
    assert started.video_id == "dQw4w9WgXcQ"
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
"$UV" run pytest tests/services/test_runner_start.py -v
```

기대: FAIL — `AttributeError: module 'notebooklm_st.services.runner' has no attribute 'start_run'`

- [ ] **Step 3: 최소 구현 작성**

`src/notebooklm_st/services/runner.py` 의 `_copy` 정의 **바로 위**에 넣는다. 그리고 파일 상단 import 에 다음을 추가한다.

```python
import asyncio
import pathlib
from collections.abc import Awaitable, Callable, Sequence

from notebooklm import exceptions

from notebooklm_st.core import errors, models, youtube
from notebooklm_st.services import nlm, store
```

본문:

```python
PipelineCallable = Callable[..., Awaitable[models.RunResult]]

_threads: list[threading.Thread] = []


def start_run(
    registry: RunRegistry,
    url: str,
    questions: Sequence[models.Question],
    db_path: pathlib.Path,
    pipeline: PipelineCallable = nlm.run_pipeline,
) -> RunHandle:
    """질의 실행을 백그라운드 스레드에서 시작한다.

    즉시 반환하므로 호출한 화면이 파이프라인에 묶이지 않는다. 진행
    상황과 결과는 레지스트리에서 조회한다.

    Args:
        registry: 실행 상태를 보관할 레지스트리.
        url: 질의할 영상 URL.
        questions: 물어볼 질문 목록.
        db_path: 완료 시 이력을 저장할 DB 경로.
        pipeline: 실행할 파이프라인. 테스트가 가짜를 넣을 수 있게 뚫어 둔다.

    Returns:
        시작된 실행의 핸들.
    """
    handle = registry.create(
        url,
        youtube.extract_video_id(url) or "",
        tuple(question.text for question in questions),
    )
    thread = threading.Thread(
        target=_work,
        args=(registry, handle.run_id, url, list(questions), db_path, pipeline),
        daemon=True,
    )
    _threads.append(thread)
    thread.start()
    return handle


def join_all(timeout: float = 5.0) -> None:
    """시작된 스레드가 모두 끝날 때까지 기다린다.

    테스트가 결과를 확인하기 전에 쓴다. 운영 코드는 부르지 않는다.

    Args:
        timeout: 스레드 하나당 최대 대기 초.
    """
    for thread in list(_threads):
        thread.join(timeout=timeout)
    _threads.clear()


def _work(
    registry: RunRegistry,
    run_id: str,
    url: str,
    questions: list[models.Question],
    db_path: pathlib.Path,
    pipeline: PipelineCallable,
) -> None:
    """스레드 본체 — 파이프라인을 돌리고 결과를 남긴다.

    Streamlit API 를 부르지 않는다. 콜백이 화면을 건드리면 사용자가
    페이지를 이동한 순간 이 스레드가 중단되기 때문이다.
    """

    def on_progress(message: str) -> None:
        """진행 문구를 레지스트리에 기록한다."""
        registry.append_progress(run_id, message)

    try:
        result = asyncio.run(pipeline(url, questions, on_progress))
    except exceptions.NotebookLMError as error:
        message = errors.to_message(error)
        registry.fail(run_id, message.text, message.level)
        return
    except Exception as error:  # noqa: BLE001
        # 스레드 최상위에서만 넓게 잡는다. 여기서 예외가 새면 화면이
        # 영원히 "실행 중" 에 머물러 사용자가 원인을 알 수 없다.
        registry.fail(run_id, f"예상 못 한 오류: {error}", "error")
        return

    connection = store.connect(db_path)
    try:
        store.save_run(connection, result)
    finally:
        connection.close()
    registry.finish(run_id, result)
```

`# noqa: BLE001` 은 `select` 에 `BLE` 가 없어 없어도 통과하지만, 의도를 남기기 위해 붙이고 사유를 주석으로 적는다.

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
"$UV" run pytest tests/services/test_runner_start.py -v
```

기대: PASS (5 passed)

- [ ] **Step 5: 4종 검증 실행**

```bash
"$UV" run ruff format .
"$UV" run ruff check --fix .
"$UV" run mypy src tests
"$UV" run pytest
```

기대: 전부 통과. `runner.py` 가 몇 줄이 됐는지 보고에 적는다(300줄 기준).

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/runner.py tests/services/test_runner_start.py
git commit -m "✨ feat(services): 백그라운드 실행 시작 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```
---

### Task 3: 레지스트리 접근자

레지스트리를 `@st.cache_resource` 로 감싸 모든 세션이 같은 인스턴스를 보게 한다. 테스트 격리를 위해 기존 fixture 도 함께 손본다.

**Files:**
- Modify: `src/notebooklm_st/session.py` (`get_connection` 정의 **아래**에 추가)
- Modify: `tests/conftest.py` (`app_db` fixture 가 레지스트리 캐시도 비우게 한다)
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: Task 1 의 `runner.RunRegistry`
- Produces: `session.get_registry() -> runner.RunRegistry` — `@st.cache_resource` 로 감쌌으므로 테스트에서 `session.get_registry.clear()` 로 비울 수 있다. Task 5·6 이 쓴다.

**설계 근거 (설계 문서 2.1):** `st.session_state` 는 브라우저 탭마다 별개라 이 용도로 쓸 수 없다. `@st.cache_resource` 객체만 세션 간에 공유된다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_session.py`:

```python
"""공유 자원 접근자 테스트."""

from streamlit.testing import v1


def test_registry_is_shared_across_sessions(app_db) -> None:
    """서로 다른 세션이 같은 레지스트리 인스턴스를 본다."""

    def script():
        """AppTest 진입점 — 레지스트리에 실행을 하나 등록한다."""
        import streamlit as st

        from notebooklm_st import session

        registry = session.get_registry()
        registry.create("https://youtu.be/x", "x", ("질문",))
        st.write(f"count={len(registry.list_all())}")

    first = v1.AppTest.from_function(script).run()
    second = v1.AppTest.from_function(script).run()

    assert not first.exception
    assert not second.exception
    assert [element.value for element in first.markdown] == ["count=1"]
    assert [element.value for element in second.markdown] == ["count=2"]


def test_registry_cache_is_cleared_between_tests(app_db) -> None:
    """fixture 가 캐시를 비우므로 앞선 테스트의 실행이 남지 않는다."""

    def script():
        """AppTest 진입점 — 레지스트리 크기를 보고한다."""
        import streamlit as st

        from notebooklm_st import session

        st.write(f"count={len(session.get_registry().list_all())}")

    app = v1.AppTest.from_function(script).run()
    assert [element.value for element in app.markdown] == ["count=0"]
```

두 번째 테스트가 핵심이다. 첫 테스트가 레지스트리에 2건을 남기는데, fixture 가 비우지 않으면 여기서 `count=2` 가 되어 실패한다.

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
"$UV" run pytest tests/test_session.py -v
```

기대: FAIL — `AttributeError: module 'notebooklm_st.session' has no attribute 'get_registry'`

- [ ] **Step 3: 접근자 추가**

`src/notebooklm_st/session.py` 의 `get_connection` **아래**에 추가한다. 파일 상단 import 에 `from notebooklm_st.services import runner, store` 로 `runner` 를 더한다.

```python
@st.cache_resource
def get_registry() -> runner.RunRegistry:
    """앱 전체가 공유하는 실행 레지스트리를 돌려준다.

    ``@st.cache_resource`` 로 감싼 객체는 모든 세션·브라우저 탭에서 같은
    인스턴스다. 그래야 질의 화면에서 시작한 실행을 대시보드 화면에서
    조회할 수 있다. ``st.session_state`` 는 탭마다 별개라 쓸 수 없다.

    Returns:
        재실행되어도 같은 레지스트리 객체.
    """
    return runner.RunRegistry()
```

- [ ] **Step 4: fixture 가 레지스트리도 비우게 한다**

`tests/conftest.py` 의 `app_db` fixture 를 아래로 바꾼다. 독스트링 문구도 함께 고친다.

```python
@pytest.fixture
def app_db(monkeypatch, tmp_path) -> Iterator[sqlite3.Connection]:
    """앱이 임시 DB 를 쓰게 하고 캐시된 공유 자원을 비운다."""
    monkeypatch.setenv(store.DB_PATH_ENV_VAR, str(tmp_path / "app.db"))
    session.get_connection.clear()
    session.get_registry.clear()
    yield store.connect(tmp_path / "app.db")
    session.get_connection.clear()
    session.get_registry.clear()
```

- [ ] **Step 5: 테스트 실행해 통과 확인**

```bash
"$UV" run pytest tests/test_session.py -v
```

기대: PASS (2 passed)

- [ ] **Step 6: 4종 검증 실행**

```bash
"$UV" run ruff format .
"$UV" run ruff check --fix .
"$UV" run mypy src tests
"$UV" run pytest
```

기대: 전부 통과. **`conftest.py` 를 고쳤으므로 기존 화면 테스트가 깨지지 않았는지 특히 확인한다.**

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/session.py tests/conftest.py tests/test_session.py
git commit -m "✨ feat: 실행 레지스트리 접근자 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 실행 카드 렌더

`components/run_progress.py` 를 **폐기하고 다시 쓴다.** 기존 `progress_status` 는 동기 실행 전용이라 더 이상 쓰이지 않는다.

**Files:**
- Rewrite: `src/notebooklm_st/components/run_progress.py` (전체 교체)
- Modify: `tests/test_components.py` (`test_progress_status_renders_without_error` 제거, 새 테스트 추가)

**Interfaces:**
- Consumes: Task 1 의 `runner.RunHandle`, 기존 `answer_view.render_items`
- Produces: `run_progress.render_run(handle: runner.RunHandle) -> None` — Task 5 가 쓴다.
- **제거**: `run_progress.progress_status` — Task 6 에서 `pages/ask.py` 가 이 함수를 더 이상 쓰지 않게 되므로, 이 태스크 시점에는 아직 `ask.py` 가 import 하고 있다. **따라서 Task 4 와 Task 6 사이에는 앱이 깨진 상태다.** Task 6 을 반드시 이어서 수행한다.

> **주의:** `progress_status` 를 지우면 `pages/ask.py` 의 import 가 깨져 기존 `test_ask.py` 가 실패한다. 이 태스크의 4종 검증에서 그 실패는 **예상된 것**이며, Task 6 이 해소한다. Step 5 에서 실패 목록을 확인해 `test_ask.py` 외의 것이 깨지지 않았는지만 본다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_components.py` 에서 `test_progress_status_renders_without_error` 를 **삭제**하고, 파일 끝에 아래를 추가한다. 나머지 두 테스트(`test_answer_view_renders_success_and_failure`, `test_answer_view_handles_empty_list`)는 그대로 둔다.

```python
def test_render_run_shows_latest_progress_while_running() -> None:
    """진행 중인 실행은 가장 최근 진행 문구를 보여준다."""

    def script():
        """AppTest 진입점 — 진행 중인 실행 카드를 그린다."""
        from notebooklm_st.components import run_progress
        from notebooklm_st.services import runner

        run_progress.render_run(
            runner.RunHandle(
                run_id="abc12345",
                url="https://youtu.be/dQw4w9WgXcQ",
                video_id="dQw4w9WgXcQ",
                question_texts=("핵심 주장은?",),
                started_at="2026-08-28T10:00:00",
                status="running",
                progress=["임시 노트북 생성 중", "자막 인덱싱 중"],
                result=None,
                error_message=None,
                error_level=None,
                finished_at=None,
            )
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    rendered = " ".join(element.value for element in app.info)
    assert "자막 인덱싱 중" in rendered
    assert "임시 노트북 생성 중" not in rendered


def test_render_run_shows_answers_when_done() -> None:
    """완료된 실행은 답변과 인용을 보여준다."""

    def script():
        """AppTest 진입점 — 완료된 실행 카드를 그린다."""
        from notebooklm_st.components import run_progress
        from notebooklm_st.core import models
        from notebooklm_st.services import runner

        run_progress.render_run(
            runner.RunHandle(
                run_id="abc12345",
                url="https://youtu.be/dQw4w9WgXcQ",
                video_id="dQw4w9WgXcQ",
                question_texts=("핵심 주장은?",),
                started_at="2026-08-28T10:00:00",
                status="done",
                progress=[],
                result=models.RunResult(
                    url="https://youtu.be/dQw4w9WgXcQ",
                    video_id="dQw4w9WgXcQ",
                    items=(
                        models.AnswerItem(
                            question_text="핵심 주장은?",
                            answer="세 가지다.",
                            citations=(
                                models.Citation(
                                    number=1, text="근거 구절", score=0.9
                                ),
                            ),
                            error=None,
                        ),
                    ),
                ),
                error_message=None,
                error_level=None,
                finished_at="2026-08-28T10:01:00",
            )
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert [element.value for element in app.subheader] == ["핵심 주장은?"]
    rendered = " ".join(element.value for element in app.markdown)
    assert "세 가지다." in rendered
    assert "근거 구절" in rendered


def test_render_run_uses_info_box_for_a_video_without_captions() -> None:
    """자막 없음 같은 정상 결과는 오류가 아니라 안내로 보여준다."""

    def script():
        """AppTest 진입점 — info 수준으로 실패한 실행을 그린다."""
        from notebooklm_st.components import run_progress
        from notebooklm_st.services import runner

        run_progress.render_run(
            runner.RunHandle(
                run_id="abc12345",
                url="https://youtu.be/dQw4w9WgXcQ",
                video_id="dQw4w9WgXcQ",
                question_texts=("핵심 주장은?",),
                started_at="2026-08-28T10:00:00",
                status="failed",
                progress=[],
                result=None,
                error_message="자막이 없거나 소스로 쓸 수 없는 영상입니다.",
                error_level="info",
                finished_at="2026-08-28T10:01:00",
            )
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.info) == 1
    assert len(app.error) == 0


def test_render_run_uses_error_box_for_a_real_failure() -> None:
    """진짜 오류는 오류 상자로 보여준다."""

    def script():
        """AppTest 진입점 — error 수준으로 실패한 실행을 그린다."""
        from notebooklm_st.components import run_progress
        from notebooklm_st.services import runner

        run_progress.render_run(
            runner.RunHandle(
                run_id="abc12345",
                url="https://youtu.be/dQw4w9WgXcQ",
                video_id="dQw4w9WgXcQ",
                question_texts=("핵심 주장은?",),
                started_at="2026-08-28T10:00:00",
                status="failed",
                progress=[],
                result=None,
                error_message="네트워크 오류가 발생했습니다.",
                error_level="error",
                finished_at="2026-08-28T10:01:00",
            )
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.error) == 1
    assert len(app.info) == 0
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
"$UV" run pytest tests/test_components.py -v
```

기대: 새 테스트 4개가 FAIL — `AttributeError: module ... has no attribute 'render_run'`

- [ ] **Step 3: 파일 전체를 다시 쓴다**

`src/notebooklm_st/components/run_progress.py` 를 아래 내용으로 **완전히 교체**한다.

```python
"""실행 하나를 상태에 맞게 그리는 카드."""

import streamlit as st

from notebooklm_st.components import answer_view
from notebooklm_st.services import runner


def render_run(handle: runner.RunHandle) -> None:
    """실행 하나를 상태에 맞게 그린다.

    Args:
        handle: 그릴 실행 핸들.
    """
    st.markdown(f"**{handle.url}**")
    st.caption(
        f"시작 {handle.started_at} · 질문 {len(handle.question_texts)}개"
    )

    if handle.status == "running":
        _render_running(handle)
        return
    if handle.status == "failed":
        _render_failed(handle)
        return
    _render_done(handle)


def _render_running(handle: runner.RunHandle) -> None:
    """진행 중인 실행의 최신 문구를 보여준다."""
    latest = handle.progress[-1] if handle.progress else "시작하는 중"
    st.info(f"실행 중 — {latest}")


def _render_failed(handle: runner.RunHandle) -> None:
    """실패한 실행의 사유를 표시 수준에 맞춰 보여준다."""
    text = handle.error_message or "알 수 없는 오류로 실패했습니다."
    if handle.error_level == "info":
        st.info(text)
        return
    st.error(text)


def _render_done(handle: runner.RunHandle) -> None:
    """완료된 실행의 답변을 보여준다."""
    if handle.result is None:
        st.warning("완료되었지만 결과가 비어 있습니다.")
        return
    answer_view.render_items(handle.result.items)
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
"$UV" run pytest tests/test_components.py -v
```

기대: PASS (6 passed — 기존 2개 + 신규 4개)

- [ ] **Step 5: 4종 검증 실행**

```bash
"$UV" run ruff format .
"$UV" run ruff check --fix .
"$UV" run mypy src tests
"$UV" run pytest
```

**`pytest` 는 실패한다.** `pages/ask.py` 가 아직 `run_progress.progress_status` 를 import 하기 때문이다. 실패 목록을 확인해 **`tests/pages/test_ask.py` 만 깨졌는지** 보고, 다른 테스트가 함께 깨졌다면 그것은 이 태스크의 문제이므로 고친다.

`mypy` 도 `ask.py` 에서 오류를 낼 수 있다. 같은 이유이며 Task 6 이 해소한다.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/components/run_progress.py tests/test_components.py
git commit -m "♻️ refactor(components): 진행 상자를 실행 카드로 교체" -m "동기 실행 전용 progress_status 를 걷어내고 실행 핸들을 상태별로 그리는
render_run 을 넣는다. pages/ask.py 는 다음 커밋에서 맞춘다." -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```
---

### Task 5: 대시보드 화면

실행 현황을 1초 간격으로 보여주는 페이지를 만들고 진입점에 등록한다.

**Files:**
- Create: `src/notebooklm_st/pages/dashboard.py`
- Modify: `src/notebooklm_st/app.py` (import 와 페이지 목록에 한 줄씩 추가)
- Test: `tests/pages/test_dashboard.py`

**Interfaces:**
- Consumes: `session.get_registry` (Task 3), `run_progress.render_run` (Task 4)
- Produces: `dashboard.render() -> None`

**설계 근거 (실측 사실):** `@st.fragment(run_every=)` 는 `AppTest` 에서 렌더되지만 자동 재실행되지는 않는다. 테스트는 `app.run()` 한 번으로 렌더 결과만 본다. **프래그먼트 안에서 상태를 바꾸면 무한 재실행으로 타임아웃**되므로, 레지스트리는 읽기만 하고 변경은 사용자 클릭에서만 한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/pages/test_dashboard.py`:

```python
"""실행 현황 화면 테스트."""

from streamlit.testing import v1


def test_dashboard_shows_notice_when_no_runs(app_db) -> None:
    """실행이 하나도 없으면 안내를 보여준다."""

    def script():
        """AppTest 진입점 — 실행 현황을 그린다."""
        from notebooklm_st.pages import dashboard

        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.info) == 1


def test_dashboard_shows_a_running_run(app_db) -> None:
    """진행 중인 실행의 최신 문구를 보여준다."""

    def script():
        """AppTest 진입점 — 실행을 하나 등록하고 현황을 그린다."""
        from notebooklm_st import session
        from notebooklm_st.pages import dashboard

        registry = session.get_registry()
        if not registry.list_all():
            handle = registry.create(
                "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", ("질문",)
            )
            registry.append_progress(handle.run_id, "자막 인덱싱 중")
        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    rendered = " ".join(element.value for element in app.info)
    assert "자막 인덱싱 중" in rendered


def test_dashboard_shows_answers_of_a_finished_run(app_db) -> None:
    """완료된 실행의 답변을 보여준다."""

    def script():
        """AppTest 진입점 — 완료된 실행을 넣고 현황을 그린다."""
        from notebooklm_st import session
        from notebooklm_st.core import models
        from notebooklm_st.pages import dashboard

        registry = session.get_registry()
        if not registry.list_all():
            handle = registry.create(
                "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", ("핵심 주장은?",)
            )
            registry.finish(
                handle.run_id,
                models.RunResult(
                    url="https://youtu.be/dQw4w9WgXcQ",
                    video_id="dQw4w9WgXcQ",
                    items=(
                        models.AnswerItem(
                            question_text="핵심 주장은?",
                            answer="세 가지다.",
                            citations=(),
                            error=None,
                        ),
                    ),
                ),
            )
        dashboard.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert [element.value for element in app.subheader] == ["핵심 주장은?"]
    rendered = " ".join(element.value for element in app.markdown)
    assert "세 가지다." in rendered


def test_dashboard_polls_without_error_on_repeated_runs(app_db) -> None:
    """폴링을 흉내내 여러 번 실행해도 예외가 나지 않는다."""

    def script():
        """AppTest 진입점 — 실행 현황을 그린다."""
        from notebooklm_st.pages import dashboard

        dashboard.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.run()
    app.run()
    assert not app.exception
```

마지막 테스트가 `run_every` 폴링을 대신한다. `AppTest` 는 자동 재실행하지 않으므로 `app.run()` 을 반복해 같은 효과를 낸다.

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
"$UV" run pytest tests/pages/test_dashboard.py -v
```

기대: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.pages.dashboard'`

- [ ] **Step 3: 대시보드 작성**

`src/notebooklm_st/pages/dashboard.py`:

```python
"""실행 현황 화면."""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import run_progress

_POLL_INTERVAL = "1s"


def render() -> None:
    """실행 현황을 그린다."""
    st.title("실행 현황")
    st.caption(
        "질의는 백그라운드에서 돕니다. 이 화면을 닫거나 다른 화면으로"
        " 이동해도 실행은 계속됩니다."
    )
    _render_runs()


@st.fragment(run_every=_POLL_INTERVAL)
def _render_runs() -> None:
    """레지스트리를 읽어 실행 카드를 그린다.

    **이 프래그먼트는 레지스트리를 읽기만 한다.** 안에서 상태를 바꾸면
    그 변경이 다음 재실행을 부르고 다시 상태를 바꿔 무한 루프가 된다.
    지우기는 사용자 클릭에서만 일어나므로 안전하다.
    """
    registry = session.get_registry()
    handles = registry.list_all()
    if not handles:
        st.info(
            "아직 실행한 질의가 없습니다. 영상 질의 화면에서 시작하세요."
        )
        return

    for handle in handles:
        run_progress.render_run(handle)
        if handle.status != "running" and st.button(
            "지우기", key=f"dashboard_discard_{handle.run_id}"
        ):
            registry.discard(handle.run_id)
        st.divider()
```

- [ ] **Step 4: 진입점에 등록**

`src/notebooklm_st/app.py` 의 import 를 고친다.

```python
from notebooklm_st.pages import (
    ask,
    dashboard,
    history,
    maintenance,
    question_admin,
)
```

그리고 페이지 목록의 `ask` **바로 다음**에 한 줄을 넣는다. 기존 등록의 순서와 값을 바꾸지 않는다.

```python
            st.Page(ask.render, title="질의", url_path="ask", default=True),
            st.Page(
                dashboard.render, title="실행 현황", url_path="dashboard"
            ),
```

- [ ] **Step 5: 테스트 실행해 통과 확인**

```bash
"$UV" run pytest tests/pages/test_dashboard.py -v
```

기대: PASS (4 passed)

- [ ] **Step 6: 4종 검증 실행**

```bash
"$UV" run ruff format .
"$UV" run ruff check --fix .
"$UV" run mypy src tests
"$UV" run pytest
```

`tests/pages/test_ask.py` 는 여전히 실패한다(Task 4 에서 `progress_status` 를 지웠기 때문). Task 6 이 해소한다. **그 외 테스트가 깨지지 않았는지 확인한다.** 특히 `tests/test_app.py`(진입점 부팅)가 통과해야 한다 — 새 페이지의 `url_path` 가 기존 것과 충돌하면 여기서 잡힌다.

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/pages/dashboard.py src/notebooklm_st/app.py tests/pages/test_dashboard.py
git commit -m "✨ feat(pages): 실행 현황 화면 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: 질의 화면을 트리거로 단순화

마지막 태스크다. 이 태스크가 끝나야 앱이 다시 온전해진다.

**Files:**
- Rewrite: `src/notebooklm_st/pages/ask.py` (전체 교체)
- Modify: `tests/pages/test_ask.py` (동기 실행을 전제한 테스트 2개를 교체)

**Interfaces:**
- Consumes: `session.get_connection` / `session.get_registry` (Task 3), `runner.start_run` (Task 2), `store.list_questions` / `store.default_db_path`, `youtube.is_valid`
- Produces: `ask.render() -> None` (시그니처 유지)

**변경 요지:** `_execute` 를 없앤다. `asyncio.run`, `progress_status`, `answer_view`, `_RESULT_KEY`, 예외 처리가 모두 사라진다 — 그 책임이 `runner` 와 대시보드로 옮겨갔다. 실행 중이면 버튼을 잠근다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/pages/test_ask.py` 에서 **`test_execute_saves_history_and_shows_answers` 와 `test_execute_shows_info_for_a_video_without_captions` 두 개를 삭제**하고, 그 자리에 아래 두 개를 넣는다. 앞의 네 테스트는 그대로 둔다.

파일 상단 import 도 정리한다 — `exceptions` 와 `models`, `nlm` 은 더 이상 쓰지 않으므로 지우고 `runner` 를 넣는다.

```python
"""질의 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st.services import runner, store
```

새 테스트:

```python
def test_run_button_starts_a_background_run(app_db, monkeypatch) -> None:
    """실행 버튼을 누르면 백그라운드 실행을 시작한다."""
    store.add_question(app_db, "핵심 주장은?")
    started: list[str] = []

    def fake_start_run(registry, url, questions, db_path, **kwargs):
        """스레드를 띄우지 않고 호출만 기록하는 가짜."""
        started.append(url)
        return registry.create(url, "dQw4w9WgXcQ", ("핵심 주장은?",))

    monkeypatch.setattr(runner, "start_run", fake_start_run)

    def script():
        """AppTest 진입점 — 질의 화면을 렌더한다."""
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ).run()
    app.multiselect[0].set_value(store.list_questions(app_db)).run()
    app.button[0].click().run()

    assert not app.exception
    assert started == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
    assert len(app.success) == 1


def test_run_button_is_locked_while_another_run_is_active(app_db) -> None:
    """이미 실행 중이면 버튼을 잠그고 안내를 보여준다."""
    store.add_question(app_db, "핵심 주장은?")

    def script():
        """AppTest 진입점 — 실행 중인 상태를 만들고 질의 화면을 그린다."""
        from notebooklm_st import session
        from notebooklm_st.pages import ask

        registry = session.get_registry()
        if not registry.list_all():
            registry.create("https://youtu.be/x", "x", ("질문",))
        ask.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert app.button[0].disabled is True
    assert any("실행 중" in element.value for element in app.info)
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
"$UV" run pytest tests/pages/test_ask.py -v
```

기대: FAIL — `ask.py` 가 아직 `run_progress.progress_status` 를 import 하므로 `ImportError` 또는 `AttributeError` 로 전부 실패한다.

- [ ] **Step 3: 질의 화면을 다시 쓴다**

`src/notebooklm_st/pages/ask.py` 를 아래 내용으로 **완전히 교체**한다.

```python
"""질의 화면 — 백그라운드 실행을 시작하는 트리거."""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import youtube
from notebooklm_st.services import runner, store

_URL_KEY = "ask_url"
_SELECTED_KEY = "ask_selected"


def render() -> None:
    """URL 입력, 질문 선택, 실행 시작을 그린다.

    실행은 백그라운드 스레드가 맡는다. 이 화면은 시작만 하고 즉시
    반환하므로 페이지를 이동해도 작업이 중단되지 않는다. 진행 상황과
    답변은 실행 현황 화면에서 본다.
    """
    st.title("영상 질의")
    connection = session.get_connection()
    registry = session.get_registry()
    questions = store.list_questions(connection)

    url = st.text_input(
        "YouTube 영상 URL",
        key=_URL_KEY,
        placeholder="https://www.youtube.com/watch?v=...",
    )
    url_ok = youtube.is_valid(url)
    if url and not url_ok:
        st.error("단일 YouTube 영상 URL 이 아닙니다.")

    if not questions:
        st.info("질문 관리 화면에서 질문을 먼저 등록하세요.")
        return

    selected = st.multiselect(
        "질문 선택",
        options=questions,
        format_func=lambda question: question.text,
        key=_SELECTED_KEY,
    )

    busy = registry.running_count() > 0
    if busy:
        st.info(
            "이미 실행 중인 작업이 있습니다. 실행 현황 화면에서 확인하세요."
        )

    if st.button(
        "실행",
        key="ask_run",
        disabled=busy or not (url_ok and selected),
    ):
        runner.start_run(registry, url, selected, store.default_db_path())
        st.success("실행을 시작했습니다. 실행 현황 화면에서 확인하세요.")
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
"$UV" run pytest tests/pages/test_ask.py -v
```

기대: PASS (6 passed — 기존 4개 + 신규 2개)

- [ ] **Step 5: 4종 검증 실행**

```bash
"$UV" run ruff format .
"$UV" run ruff check --fix .
"$UV" run mypy src tests
"$UV" run pytest
```

**이번에는 전부 통과해야 한다.** Task 4 에서 예상했던 실패가 여기서 해소된다. 통과하지 않으면 남은 실패를 그대로 보고한다.

- [ ] **Step 6: 앱이 뜨는지 확인**

`streamlit run` 으로 띄우지 말고 아래로 확인한다.

```bash
"$UV" run python -c "import ast,pathlib; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8')) for p in ['src/notebooklm_st/app.py','src/notebooklm_st/pages/ask.py','src/notebooklm_st/pages/dashboard.py','src/notebooklm_st/services/runner.py']]; print('syntax ok')"
"$UV" run python -c "from notebooklm_st.pages import ask, dashboard; from notebooklm_st.services import runner; print('import ok', callable(ask.render), callable(dashboard.render), callable(runner.start_run))"
```

`tests/test_app.py` 가 이미 진입점 부팅을 검증하므로 `pytest` 통과로 갈음된다.

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/pages/ask.py tests/pages/test_ask.py
git commit -m "♻️ refactor(pages): 질의 화면을 실행 트리거로 단순화" -m "실행을 백그라운드 스레드에 넘기고 진행 표시·답변 렌더를 실행 현황
화면으로 옮긴다. 페이지를 이동해도 작업이 중단되지 않는다." -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## 설계 문서 요구사항 대응표

| 설계 문서 항목 | 태스크 |
|---|---|
| 2. 채택 구조 — 트리거 / 레지스트리 / 스레드 DB 저장 | 1·2·5·6 |
| 2.1 레지스트리 세션 간 공유 | 3 |
| 2.2 스레드가 Streamlit API 를 부르지 않음 | 2 |
| 3.2 파일별 변경 | 1~6 전부 |
| 4.1 `RunHandle` 필드 | 1 |
| 4.2 `RunRegistry` 메서드 | 1 |
| 5.1 실행 시작 흐름 | 6 |
| 5.2 스레드 동작 (Streamlit 금지·전용 커넥션·save 후 finish) | 2 |
| 5.3 대시보드 폴링 | 5 |
| 6. 동시성 규칙 (락·복사본·daemon·동시 1개) | 1·2·6 |
| 7.1 질의 화면 (트리거) | 6 |
| 7.2 대시보드 화면 | 5 |
| 8.1 runner 결정적 테스트 | 1·2 |
| 8.2 UI 얕은 검증 | 4·5·6 |
| 9. 위험 — 스레드 예외 누락 대응 | 2 |
| 10. 작업 단계 순서 | 태스크 순서 그대로 |

**범위 밖(설계 문서 10장에 명시)**: 완료 알림, 실행 취소, 레지스트리 영속화, `maintenance.py` 백그라운드화.

## 실행 순서가 중요한 이유

Task 4 가 `progress_status` 를 지우고 Task 6 이 `ask.py` 를 고치므로, **그 사이에는 앱이 깨진 상태**다. 두 태스크를 반드시 이어서 수행한다. Task 5 를 사이에 둔 것은 대시보드가 있어야 Task 6 의 안내 문구("실행 현황 화면에서 확인하세요")가 실제로 갈 곳이 생기기 때문이다.

## 자체 검토 결과

계획을 설계 문서와 대조해 확인한 사항이다.

- **설계 커버리지**: 위 대응표대로 빠진 항목이 없다.
- **타입 일관성**: `RunHandle` 의 11개 필드가 Task 1 정의 → Task 4 테스트의 생성자 호출 → Task 5 의 `registry.create` 사용까지 이름과 순서가 일치한다. `RunStatus`/`MessageLevel` Literal 값(`"running"`/`"done"`/`"failed"`, `"info"`/`"error"`)이 `errors.UserMessage.level` 과 같은 문자열이다.
- **`start_run` 시그니처**: Task 2 정의 `(registry, url, questions, db_path, pipeline=...)` 와 Task 6 호출 `runner.start_run(registry, url, selected, store.default_db_path())`, Task 6 테스트의 가짜 `(registry, url, questions, db_path, **kwargs)` 가 모두 맞는다.
- **`join_all`**: 테스트 전용 함수이며 운영 코드에서 부르지 않는다는 것을 독스트링에 적었다.
- **fixture 영향**: Task 3 이 `conftest.py` 를 고치므로 기존 화면 테스트가 함께 도는지 각 태스크의 4종 검증에서 확인한다.
- **알려진 중간 실패**: Task 4·5 의 `pytest` 가 `test_ask.py` 에서 실패하는 것은 의도된 것이며 Task 6 이 해소한다. 각 태스크에 명시했다.
