# YouTube 영상 질의응답 도구 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** YouTube 영상 URL과 저장해 둔 질문 여러 개를 골라 NotebookLM의 근거 기반 답변을 받아보는 로컬 Streamlit 앱을 만든다.

**Architecture:** `core/`(순수 계산) → `services/`(외부 I/O) → `components/`·`pages/`(UI) 3계층. 실행 버튼 한 번이 `asyncio.run()` 한 번을 호출해 [노트북 생성 → 자막 인덱싱 → 질문 N개 → 노트북 삭제]를 끝까지 돌린다. 클라이언트는 이벤트 루프에 묶이므로 세션에 보관하지 않고 매번 새로 만든다.

**Tech Stack:** Python 3.13, Streamlit, notebooklm-py 0.8.1, SQLite, uv / ruff / mypy / pytest

**Spec:** `docs/superpowers/specs/2026-08-28-youtube-qa-design.md`

## Global Constraints

프로젝트 규칙 `.claude/rules/streamlit-implement.md`에서 온 제약이다. 모든 태스크의 요구사항에 암묵적으로 포함된다.

- Python **3.13**. `from __future__ import annotations`를 넣지 않는다.
- 줄 길이 **최대 80자**. 들여쓰기는 스페이스 4칸.
- 모든 명령에 `uv run`을 붙인다. 가상환경을 직접 activate 하지 않는다.
- 의존성 조작은 `uv add` / `uv add --dev`만 쓴다. `pip install` 금지.
- **`core/`와 `services/`에서 `import streamlit`을 금지한다.**
- **개별 클래스·함수를 import 하지 않는다.** 모듈이나 패키지를 import 한 뒤 정규화된 이름으로 접근한다. 예외로 허용: `typing`, `collections.abc`에서의 심볼 import.
- `from x import *`와 상대 import를 금지한다. 항상 절대 import.
- 모든 함수·메서드에 인자와 반환 타입을 붙인다. 반환이 없으면 `-> None`.
- 모든 모듈·클래스·함수에 Google 형식 `"""` 독스트링을 단다. 타입은 `Args:`에 다시 적지 않는다.
- `except:`와 맨 `except Exception:`을 금지한다. 구체적인 예외만 잡는다.
- 내장 제네릭과 유니온을 쓴다: `list[str]`, `str | None`. `typing.List`, `Optional` 금지.
- 값 묶음은 `@dataclasses.dataclass(frozen=True, slots=True)`.
- 위젯에는 `key=`를 명시한다. `st.session_state` 키는 모듈 상수로 정의한다.
- notebooklm-py는 **`0.8.1`로 고정**한다. 비공식 API라 마이너 업데이트로 깨진다.
- **작업을 끝내기 전 아래 4개를 순서대로 실행하고 전부 통과해야 완료로 보고한다.**
  ```bash
  uv run ruff format .
  uv run ruff check --fix .
  uv run mypy src tests
  uv run pytest
  ```
- 커밋 메시지는 `<emoji> <type>(<scope>): <한국어 명령형 제목 50자 이내>` 형식이며 끝에 트레일러를 붙인다:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`
- 요청받지 않은 `push`, `--force`, `--no-verify`를 하지 않는다. 브랜치는 `master` 하나뿐이다.

## 확인이 필요한 외부 API

이 계획을 쓰는 시점에 context7 MCP 서버가 연결에 실패해 Streamlit 최신 문서를 조회하지 못했다. **Task 1의 Step 9가 아래 세 가지를 실측으로 확인한다.** 확인 결과가 다르면 그 태스크에서 멈추고 보고한다.

| API | 계획이 전제하는 것 | 쓰이는 곳 |
|---|---|---|
| `st.navigation([st.Page(...)])` | 함수를 `st.Page(func, title=, icon=, default=)`로 등록하고 `.run()` | Task 10 (`app.py`) |
| `st.status(label, expanded=)` | 컨텍스트 매니저이며 `.update(label=, state=)` 지원 | Task 9 |
| `AppTest.from_function(func)` | 함수를 스크립트로 실행하는 테스트 진입점 | Task 10~13 |

notebooklm-py 0.8.1 API는 배포판 소스에서 직접 확인했으므로 추가 조회가 필요 없다. 다음 사실이 계획에 반영되어 있다.

- `HeadlessLoginRequiredError`는 `notebooklm` 최상위로 re-export되지 **않는다.** `from notebooklm import exceptions` 후 `exceptions.HeadlessLoginRequiredError`로 접근한다. 다른 예외도 일관성을 위해 같은 경로로 쓴다.
- `notebooks.delete()`는 멱등적이다. 이미 없는 노트북을 지워도 예외가 없다.
- `chat.ask()`에 `conversation_id`를 넘기지 않으면 **직전 대화를 이어간다.** 질문마다 독립 답변을 받으려면 앞 대화를 지워야 한다.

## 파일 구조

| 파일 | 책임 | 태스크 |
|---|---|---|
| `pyproject.toml` | 의존성, ruff·mypy·pytest 설정 | 1 |
| `src/notebooklm_st/core/youtube.py` | YouTube URL 검증과 영상 ID 추출 (순수) | 2 |
| `src/notebooklm_st/core/models.py` | 값 객체와 인용 JSON 직렬화 (순수) | 3 |
| `src/notebooklm_st/core/errors.py` | 라이브러리 예외 → 화면 문구 (순수) | 4 |
| `src/notebooklm_st/services/store.py` | SQLite 스키마·질문 CRUD·이력 | 5, 6 |
| `src/notebooklm_st/services/nlm.py` | 질의 파이프라인, 임시 노트북 정리 | 7, 13 |
| `src/notebooklm_st/session.py` | 앱 전역 SQLite 커넥션(캐시) | 9 |
| `src/notebooklm_st/components/run_progress.py` | 진행 콜백 ↔ `st.status` 어댑터 | 9 |
| `src/notebooklm_st/components/answer_view.py` | 답변 카드와 인용 렌더 | 9 |
| `src/notebooklm_st/app.py` | 페이지 등록 진입점 | 10 |
| `src/notebooklm_st/pages/ask.py` | 질의 화면 | 10 |
| `src/notebooklm_st/pages/question_admin.py` | 질문 관리 화면 | 11 |
| `src/notebooklm_st/pages/history.py` | 이력 화면 | 12 |
| `src/notebooklm_st/pages/maintenance.py` | 임시 노트북 정리 화면 | 13 |
| `scripts/smoke_check.py` | 실제 계정으로 도는 1회성 실측 스크립트 | 8 |

`session.py`가 최상위에 있는 이유: `@st.cache_resource`로 감싼 커넥션은 UI 계층 자원이라 `services/`에 둘 수 없고(Streamlit 의존), 여러 페이지가 공유하므로 특정 페이지에도 둘 수 없다.

---

### Task 1: 프로젝트 셋업과 툴체인 검증

이 태스크의 산출물은 "4종 검증 명령이 끝까지 도는 빈 프로젝트"다.

**Files:**
- Create: `pyproject.toml`
- Create: `src/notebooklm_st/__init__.py`
- Create: `src/notebooklm_st/core/__init__.py`
- Create: `src/notebooklm_st/services/__init__.py`
- Create: `src/notebooklm_st/components/__init__.py`
- Create: `src/notebooklm_st/pages/__init__.py`
- Test: `tests/test_package.py`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: `notebooklm_st` 패키지가 `uv run python -c "import notebooklm_st"`로 import 가능한 상태. 이후 모든 태스크가 이 환경 위에서 돈다.

- [ ] **Step 1: uv 설치**

이 PC에 `uv`가 없다. 설치한다.

```bash
winget install --id=astral-sh.uv -e --source winget
```

설치 후 새 셸에서 확인한다. `uv: command not found`가 나오면 PATH가 갱신되지 않은 것이니 터미널을 다시 연다.

```bash
uv --version
```

기대: `uv 0.x.x` 형태의 버전 출력.

- [ ] **Step 2: 기존 .venv 정리 안내**

프로젝트에 `pip`으로 만든 `.venv`가 이미 있다. `uv sync`가 이 디렉터리를 그대로 쓰려다 충돌할 수 있다. 충돌하면 **사용자에게 `.venv` 삭제를 요청한다.** 이 계획의 실행자는 `rm`/`Remove-Item`이 차단되어 있으므로 직접 지우지 않는다.

먼저 Step 4까지 그대로 진행하고, `uv sync`가 실패할 때만 이 단계로 돌아온다.

- [ ] **Step 3: pyproject.toml 작성**

`pyproject.toml`을 만든다.

```toml
[project]
name = "notebooklm-st"
version = "0.1.0"
description = "YouTube 영상 질의응답 도구"
requires-python = ">=3.13"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/notebooklm_st"]

[tool.ruff]
target-version = "py313"
line-length = 80

[tool.ruff.lint]
select = ["E", "W", "F", "I", "N", "D", "UP", "B", "SIM", "ANN", "RUF"]
ignore = ["ANN401"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["ANN"]

[tool.mypy]
python_version = "3.13"
warn_unused_ignores = true
warn_redundant_casts = true
no_implicit_optional = true

[[tool.mypy.overrides]]
module = ["notebooklm_st.core.*", "notebooklm_st.services.*"]
disallow_untyped_defs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: 패키지 디렉터리와 `__init__.py` 생성**

다섯 개의 `__init__.py`를 만든다. 각각 한 줄짜리 독스트링만 담는다 (`D104` 규칙이 패키지 독스트링을 요구한다).

`src/notebooklm_st/__init__.py`:
```python
"""YouTube 영상 질의응답 도구."""
```

`src/notebooklm_st/core/__init__.py`:
```python
"""Streamlit 에 의존하지 않는 순수 도메인 로직."""
```

`src/notebooklm_st/services/__init__.py`:
```python
"""외부 I/O — NotebookLM 연동과 SQLite 저장소."""
```

`src/notebooklm_st/components/__init__.py`:
```python
"""재사용 UI 조각."""
```

`src/notebooklm_st/pages/__init__.py`:
```python
"""페이지별 렌더 함수."""
```

- [ ] **Step 5: 의존성 추가**

```bash
uv add "notebooklm-py[browser]==0.8.1" streamlit
uv add --dev pytest mypy ruff
```

기대: `uv.lock`이 생기고 `.venv`가 채워진다. 실패하면 Step 2로 돌아가 `.venv` 삭제를 요청한다.

- [ ] **Step 6: 실패하는 테스트 작성**

`tests/test_package.py`:

```python
"""패키지가 import 가능한지 확인한다."""

import notebooklm_st


def test_package_has_docstring():
    assert notebooklm_st.__doc__
```

- [ ] **Step 7: 테스트 실행**

```bash
uv run pytest tests/test_package.py -v
```

기대: PASS. 실패하면 `src` 레이아웃이 설치되지 않은 것이므로 `uv sync`를 다시 실행한다.

- [ ] **Step 8: 4종 검증 실행**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

mypy가 `notebooklm` 또는 `streamlit` 스텁 없음을 보고하면 `pyproject.toml`에 아래를 **추가**한다 (기존 overrides 블록 아래에 붙인다).

```toml
[[tool.mypy.overrides]]
module = ["notebooklm.*", "streamlit.*"]
ignore_missing_imports = true
```

추가한 뒤 `uv run mypy src tests`를 다시 돌려 통과를 확인한다. 전역 `ignore_missing_imports`는 켜지 않는다.

- [ ] **Step 9: 전제한 Streamlit API 실측 확인**

계획 상단 "확인이 필요한 외부 API" 표를 검증한다.

```bash
uv run python -c "import streamlit as st; print(st.__version__, hasattr(st, 'navigation'), hasattr(st, 'Page'), hasattr(st, 'status'))"
uv run python -c "from streamlit.testing import v1; print(hasattr(v1.AppTest, 'from_function'))"
```

기대: 첫 줄이 버전과 `True True True`, 둘째 줄이 `True`.

`False`가 하나라도 나오면 **여기서 멈추고 사용자에게 보고한다.** 대안은 있다. `st.navigation`이 없으면 `pages/` 디렉터리 관례로 바꾸고, `AppTest.from_function`이 없으면 각 페이지를 부르는 한 줄짜리 스크립트를 `tests/harness/`에 만들어 `AppTest.from_file`로 여는 방식으로 Task 10~13을 조정해야 하며, 이는 계획 수정이 필요한 변경이다.

- [ ] **Step 10: 커밋**

```bash
git add pyproject.toml uv.lock src tests
git commit -m "🔧 chore: uv 프로젝트 초기화 및 툴체인 설정" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

`.venv/`는 `.gitignore`에 이미 들어 있어 스테이징되지 않는다. `git status --short`로 확인한다.

---

### Task 2: YouTube URL 검증 (`core/youtube.py`)

**Files:**
- Create: `src/notebooklm_st/core/youtube.py`
- Test: `tests/core/test_youtube.py`

**Interfaces:**
- Consumes: Task 1의 패키지 구조
- Produces:
  - `youtube.extract_video_id(url: str) -> str | None`
  - `youtube.is_valid(url: str) -> bool`

  Task 7이 `extract_video_id`를, Task 10이 `is_valid`를 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/core/test_youtube.py`:

```python
"""YouTube URL 파싱 테스트."""

import pytest

from notebooklm_st.core import youtube

VIDEO_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
        "https://www.youtube.com/v/dQw4w9WgXcQ",
        "https://www.youtube.com/watch?list=PL1&v=dQw4w9WgXcQ&t=42",
        "  https://youtu.be/dQw4w9WgXcQ  ",
        "https://youtu.be/dQw4w9WgXcQ?t=30",
    ],
)
def test_extract_video_id_accepts_single_video_urls(url):
    assert youtube.extract_video_id(url) == VIDEO_ID


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not a url",
        "https://evil.com/youtube.com/watch?v=dQw4w9WgXcQ",
        "https://notyoutube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/playlist?list=PL1",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/@channel",
        "https://youtu.be/",
    ],
)
def test_extract_video_id_rejects_other_urls(url):
    assert youtube.extract_video_id(url) is None


def test_is_valid_mirrors_extract():
    assert youtube.is_valid("https://youtu.be/dQw4w9WgXcQ") is True
    assert youtube.is_valid("https://example.com") is False
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
uv run pytest tests/core/test_youtube.py -v
```

기대: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.core.youtube'`

- [ ] **Step 3: 최소 구현 작성**

`src/notebooklm_st/core/youtube.py`:

```python
"""YouTube URL 검증과 영상 ID 추출."""

import re
import urllib.parse

_VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ALLOWED_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
)
_PATH_PREFIXES = ("/shorts/", "/embed/", "/live/", "/v/")


def extract_video_id(url: str) -> str | None:
    """단일 YouTube 영상 URL 에서 영상 ID 를 뽑는다.

    호스트 이름을 파싱해서 비교하므로 ``evil.com/youtube.com/...``
    같은 부분 문자열 위장은 통과하지 못한다. 재생목록 파라미터가
    붙어 있으면 무시하고 영상 ID 만 돌려준다.

    Args:
        url: 검사할 URL. 앞뒤 공백은 무시한다.

    Returns:
        11자리 영상 ID. 단일 영상 URL 이 아니면 ``None``.
    """
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except ValueError:
        return None

    hostname = (parsed.hostname or "").lower()
    if hostname not in _ALLOWED_HOSTS:
        return None

    if hostname == "youtu.be":
        return _validated(parsed.path.lstrip("/").split("/")[0])

    if parsed.path == "/watch":
        values = urllib.parse.parse_qs(parsed.query).get("v", [])
        return _validated(values[0]) if values else None

    for prefix in _PATH_PREFIXES:
        if parsed.path.startswith(prefix):
            rest = parsed.path[len(prefix) :]
            return _validated(rest.split("/")[0])

    return None


def is_valid(url: str) -> bool:
    """URL 이 단일 YouTube 영상을 가리키는지 알려준다.

    Args:
        url: 검사할 URL.

    Returns:
        영상 ID 를 뽑아낼 수 있으면 참.
    """
    return extract_video_id(url) is not None


def _validated(candidate: str) -> str | None:
    """11자리 영상 ID 형식이면 그대로, 아니면 ``None`` 을 돌려준다."""
    return candidate if _VIDEO_ID_PATTERN.match(candidate) else None
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
uv run pytest tests/core/test_youtube.py -v
```

기대: PASS (23 passed)

- [ ] **Step 5: 4종 검증 실행**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

기대: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/core/youtube.py tests/core/test_youtube.py
git commit -m "✨ feat(core): YouTube URL 검증 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 도메인 값 객체 (`core/models.py`)

**Files:**
- Create: `src/notebooklm_st/core/models.py`
- Test: `tests/core/test_models.py`

**Interfaces:**
- Consumes: Task 1의 패키지 구조
- Produces: 이후 모든 태스크가 쓰는 값 객체와 직렬화 함수.
  - `models.Question(id: int, text: str, created_at: str, updated_at: str)`
  - `models.Citation(number: int, text: str, score: float)`
  - `models.AnswerItem(question_text: str, answer: str | None, citations: tuple[Citation, ...], error: str | None)` — 프로퍼티 `succeeded: bool`
  - `models.RunResult(url: str, video_id: str, items: tuple[AnswerItem, ...])`
  - `models.RunSummary(id: int, url: str, video_id: str, created_at: str, answer_count: int)`
  - `models.TempNotebook(id: str, title: str)`
  - `models.citations_to_json(citations: Sequence[Citation]) -> str`
  - `models.citations_from_json(payload: str | None) -> tuple[Citation, ...]`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/core/test_models.py`:

```python
"""도메인 값 객체 테스트."""

import dataclasses

import pytest

from notebooklm_st.core import models


def test_answer_item_succeeded_when_no_error():
    item = models.AnswerItem(
        question_text="핵심 주장은?",
        answer="세 가지다.",
        citations=(),
        error=None,
    )
    assert item.succeeded is True


def test_answer_item_not_succeeded_when_error_present():
    item = models.AnswerItem(
        question_text="핵심 주장은?",
        answer=None,
        citations=(),
        error="답변을 받지 못했습니다.",
    )
    assert item.succeeded is False


def test_value_objects_are_frozen():
    citation = models.Citation(number=1, text="인용", score=0.5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        citation.number = 2


def test_citations_round_trip():
    citations = (
        models.Citation(number=1, text="첫 구절", score=0.82),
        models.Citation(number=2, text="둘째 구절", score=0.41),
    )
    payload = models.citations_to_json(citations)
    assert models.citations_from_json(payload) == citations


def test_citations_json_keeps_hangul_readable():
    payload = models.citations_to_json(
        (models.Citation(number=1, text="한글", score=1.0),)
    )
    assert "한글" in payload


def test_citations_from_json_handles_empty():
    assert models.citations_from_json(None) == ()
    assert models.citations_from_json("") == ()
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
uv run pytest tests/core/test_models.py -v
```

기대: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.core.models'`

- [ ] **Step 3: 최소 구현 작성**

`src/notebooklm_st/core/models.py`:

```python
"""화면과 저장소가 함께 쓰는 값 객체."""

import dataclasses
import json
from collections.abc import Sequence


@dataclasses.dataclass(frozen=True, slots=True)
class Question:
    """저장된 질문 템플릿."""

    id: int
    text: str
    created_at: str
    updated_at: str


@dataclasses.dataclass(frozen=True, slots=True)
class Citation:
    """답변이 근거로 든 자막 구절."""

    number: int
    text: str
    score: float


@dataclasses.dataclass(frozen=True, slots=True)
class AnswerItem:
    """질문 하나에 대한 실행 결과.

    ``answer`` 와 ``error`` 는 배타적이다. 성공한 항목은 ``error`` 가
    ``None`` 이고, 실패한 항목은 ``answer`` 가 ``None`` 이다.
    """

    question_text: str
    answer: str | None
    citations: tuple[Citation, ...]
    error: str | None

    @property
    def succeeded(self) -> bool:
        """실패 메시지가 없으면 참."""
        return self.error is None


@dataclasses.dataclass(frozen=True, slots=True)
class RunResult:
    """영상 하나에 질문들을 던진 결과 전체."""

    url: str
    video_id: str
    items: tuple[AnswerItem, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class RunSummary:
    """이력 목록에 한 줄로 보여 줄 실행 요약."""

    id: int
    url: str
    video_id: str
    created_at: str
    answer_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class TempNotebook:
    """정리 대상인 임시 노트북."""

    id: str
    title: str


def citations_to_json(citations: Sequence[Citation]) -> str:
    """인용 목록을 저장용 JSON 문자열로 바꾼다.

    한글이 이스케이프되면 DB 를 직접 들여다볼 때 읽기 어려우므로
    ``ensure_ascii`` 를 끈다.

    Args:
        citations: 저장할 인용 목록.

    Returns:
        JSON 배열 문자열.
    """
    payload = [
        {"n": item.number, "text": item.text, "score": item.score}
        for item in citations
    ]
    return json.dumps(payload, ensure_ascii=False)


def citations_from_json(payload: str | None) -> tuple[Citation, ...]:
    """저장된 JSON 문자열을 인용 목록으로 되돌린다.

    Args:
        payload: ``citations_to_json`` 이 만든 문자열. 비어 있거나
            ``None`` 이면 빈 결과를 돌려준다.

    Returns:
        인용 목록.
    """
    if not payload:
        return ()
    raw = json.loads(payload)
    return tuple(
        Citation(number=row["n"], text=row["text"], score=row["score"])
        for row in raw
    )
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
uv run pytest tests/core/test_models.py -v
```

기대: PASS (6 passed)

- [ ] **Step 5: 4종 검증 실행**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

기대: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/core/models.py tests/core/test_models.py
git commit -m "✨ feat(core): 도메인 값 객체 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```
---

### Task 4: 예외 메시지 변환 (`core/errors.py`)

**Files:**
- Create: `src/notebooklm_st/core/errors.py`
- Test: `tests/core/test_errors.py`

**Interfaces:**
- Consumes: Task 1의 패키지 구조, `notebooklm.exceptions`
- Produces:
  - `errors.UserMessage(text: str, level: Literal["info", "error"])`
  - `errors.to_message(error: exceptions.NotebookLMError) -> UserMessage`

  Task 7이 질문 단위 실패 문구를 만들 때, Task 10이 파이프라인 전체 실패를 표시할 때 쓴다.

**주의:** `HeadlessLoginRequiredError`는 `notebooklm` 최상위로 re-export되지 않는다. 반드시 `from notebooklm import exceptions`로 가져와 `exceptions.HeadlessLoginRequiredError`로 접근한다. 일관성을 위해 다른 예외도 같은 경로로 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/core/test_errors.py`:

```python
"""라이브러리 예외 → 화면 문구 변환 테스트."""

from notebooklm import exceptions

from notebooklm_st.core import errors


def test_source_timeout_is_error():
    message = errors.to_message(
        exceptions.SourceTimeoutError("source-1", 120.0)
    )
    assert message.level == "error"
    assert "제한 시간" in message.text


def test_source_add_failure_is_info_not_error():
    message = errors.to_message(
        exceptions.SourceAddError("https://youtu.be/dQw4w9WgXcQ")
    )
    assert message.level == "info"
    assert "자막" in message.text


def test_source_processing_failure_is_info():
    message = errors.to_message(exceptions.SourceProcessingError("source-1"))
    assert message.level == "info"
    assert "자막" in message.text


def test_auth_error_tells_user_to_log_in_again():
    message = errors.to_message(exceptions.AuthError("expired"))
    assert message.level == "error"
    assert "notebooklm login" in message.text


def test_headless_login_required_tells_user_to_log_in_again():
    message = errors.to_message(
        exceptions.HeadlessLoginRequiredError("dead session")
    )
    assert message.level == "error"
    assert "notebooklm login" in message.text


def test_rate_limit_error():
    message = errors.to_message(exceptions.RateLimitError("too many"))
    assert message.level == "error"
    assert "한도" in message.text


def test_notebook_limit_error_points_at_cleanup_page():
    message = errors.to_message(exceptions.NotebookLimitError(100))
    assert message.level == "error"
    assert "정리" in message.text


def test_network_error():
    message = errors.to_message(exceptions.NetworkError("boom"))
    assert message.level == "error"
    assert "네트워크" in message.text


def test_rpc_timeout_is_treated_as_network_error():
    message = errors.to_message(exceptions.RPCTimeoutError("slow"))
    assert message.level == "error"
    assert "네트워크" in message.text


def test_chat_error():
    message = errors.to_message(exceptions.ChatError("bad response"))
    assert message.level == "error"
    assert "답변" in message.text


def test_unmapped_library_error_falls_back():
    message = errors.to_message(exceptions.NotebookLMError("무슨 일이지"))
    assert message.level == "error"
    assert message.text
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
uv run pytest tests/core/test_errors.py -v
```

기대: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.core.errors'`

- [ ] **Step 3: 최소 구현 작성**

`src/notebooklm_st/core/errors.py`:

```python
"""notebooklm-py 예외를 화면에 보여 줄 문구로 바꾼다."""

import dataclasses
from typing import Literal

from notebooklm import exceptions

_LOGIN_HINT = (
    "인증이 만료되었습니다. 터미널에서 "
    "`uv run notebooklm login` 을 다시 실행하세요."
)


@dataclasses.dataclass(frozen=True, slots=True)
class UserMessage:
    """화면에 표시할 문구와 표시 수준."""

    text: str
    level: Literal["info", "error"]


def to_message(error: exceptions.NotebookLMError) -> UserMessage:
    """라이브러리 예외를 화면 문구로 바꾼다.

    자막이 없는 영상은 도구의 오류가 아니라 그 영상의 성질이므로
    ``info`` 수준으로 돌려준다. 나머지는 ``error`` 다.

    검사 순서가 중요하다. ``SourceTimeoutError`` 는 ``SourceError`` 의
    하위 클래스라서 뒤에 두면 "자막 없음" 으로 잘못 잡힌다.

    Args:
        error: notebooklm-py 가 올린 예외.

    Returns:
        표시할 문구와 수준.
    """
    if isinstance(error, exceptions.SourceTimeoutError):
        return UserMessage(
            "자막 인덱싱이 제한 시간 안에 끝나지 않았습니다."
            " 잠시 후 다시 시도하세요.",
            "error",
        )
    if isinstance(
        error,
        exceptions.SourceAddError | exceptions.SourceProcessingError,
    ):
        return UserMessage(
            "자막이 없거나 소스로 쓸 수 없는 영상입니다.", "info"
        )
    if isinstance(
        error,
        exceptions.AuthError | exceptions.HeadlessLoginRequiredError,
    ):
        return UserMessage(_LOGIN_HINT, "error")
    if isinstance(error, exceptions.RateLimitError):
        return UserMessage(
            "요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.", "error"
        )
    if isinstance(error, exceptions.NotebookLimitError):
        return UserMessage(
            "노트북 개수 상한에 도달했습니다."
            " 정리 페이지에서 임시 노트북을 삭제하세요.",
            "error",
        )
    if isinstance(error, exceptions.NetworkError):
        return UserMessage("네트워크 오류가 발생했습니다.", "error")
    if isinstance(error, exceptions.ChatError):
        return UserMessage("답변을 받지 못했습니다.", "error")
    return UserMessage("NotebookLM 요청이 실패했습니다.", "error")
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
uv run pytest tests/core/test_errors.py -v
```

기대: PASS (11 passed)

- [ ] **Step 5: 4종 검증 실행**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

기대: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/core/errors.py tests/core/test_errors.py
git commit -m "✨ feat(core): 예외 메시지 변환 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: 질문 저장소 (`services/store.py`)

**Files:**
- Create: `src/notebooklm_st/services/store.py`
- Test: `tests/services/test_store_questions.py`

**Interfaces:**
- Consumes: `models.Question` (Task 3)
- Produces:
  - `store.DB_PATH_ENV_VAR: str` — 값은 `"NOTEBOOKLM_ST_DB"`
  - `store.default_db_path() -> pathlib.Path`
  - `store.connect(db_path: pathlib.Path) -> sqlite3.Connection`
  - `store.list_questions(connection) -> list[models.Question]`
  - `store.add_question(connection, text: str) -> models.Question`
  - `store.update_question(connection, question_id: int, text: str) -> None`
  - `store.delete_question(connection, question_id: int) -> None`

  Task 6이 같은 파일에 이력 함수를 덧붙인다. Task 9의 `session.py`가 `connect`와 `default_db_path`를 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/services/test_store_questions.py`:

```python
"""질문 저장소 테스트."""

import pytest

from notebooklm_st.services import store


@pytest.fixture
def connection(tmp_path):
    conn = store.connect(tmp_path / "test.db")
    yield conn
    conn.close()


def test_new_database_has_no_questions(connection):
    assert store.list_questions(connection) == []


def test_add_question_returns_saved_row(connection):
    saved = store.add_question(connection, "핵심 주장 3가지 정리")
    assert saved.id > 0
    assert saved.text == "핵심 주장 3가지 정리"
    assert saved.created_at
    assert saved.created_at == saved.updated_at


def test_add_question_strips_whitespace(connection):
    saved = store.add_question(connection, "  발표자의 결론은?  ")
    assert saved.text == "발표자의 결론은?"


def test_add_question_rejects_blank(connection):
    with pytest.raises(ValueError):
        store.add_question(connection, "   ")


def test_list_questions_returns_insertion_order(connection):
    store.add_question(connection, "첫째")
    store.add_question(connection, "둘째")
    texts = [q.text for q in store.list_questions(connection)]
    assert texts == ["첫째", "둘째"]


def test_update_question_changes_text(connection):
    saved = store.add_question(connection, "옛 질문")
    store.update_question(connection, saved.id, "새 질문")
    assert store.list_questions(connection)[0].text == "새 질문"


def test_update_question_rejects_missing_id(connection):
    with pytest.raises(ValueError):
        store.update_question(connection, 999, "아무거나")


def test_update_question_rejects_blank(connection):
    saved = store.add_question(connection, "옛 질문")
    with pytest.raises(ValueError):
        store.update_question(connection, saved.id, "  ")


def test_delete_question_removes_row(connection):
    saved = store.add_question(connection, "지울 질문")
    store.delete_question(connection, saved.id)
    assert store.list_questions(connection) == []


def test_delete_question_is_silent_when_missing(connection):
    store.delete_question(connection, 999)


def test_default_db_path_honors_env_override(monkeypatch, tmp_path):
    target = tmp_path / "custom.db"
    monkeypatch.setenv(store.DB_PATH_ENV_VAR, str(target))
    assert store.default_db_path() == target


def test_default_db_path_falls_back_to_cwd(monkeypatch):
    monkeypatch.delenv(store.DB_PATH_ENV_VAR, raising=False)
    assert store.default_db_path().name == "questions.db"
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
uv run pytest tests/services/test_store_questions.py -v
```

기대: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.services.store'`

- [ ] **Step 3: 최소 구현 작성**

`src/notebooklm_st/services/store.py`:

```python
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
    run_id        INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
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


def list_questions(connection: sqlite3.Connection) -> list[models.Question]:
    """등록된 질문을 등록 순서대로 돌려준다.

    Args:
        connection: 열린 커넥션.

    Returns:
        질문 목록.
    """
    rows = connection.execute(
        "SELECT id, text, created_at, updated_at FROM questions"
        " ORDER BY id"
    ).fetchall()
    return [_to_question(row) for row in rows]


def add_question(
    connection: sqlite3.Connection, text: str
) -> models.Question:
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


def delete_question(
    connection: sqlite3.Connection, question_id: int
) -> None:
    """질문을 지운다. 이미 없으면 조용히 넘어간다.

    Args:
        connection: 열린 커넥션.
        question_id: 지울 질문의 ID.
    """
    connection.execute(
        "DELETE FROM questions WHERE id = ?", (question_id,)
    )
    connection.commit()


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
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
uv run pytest tests/services/test_store_questions.py -v
```

기대: PASS (12 passed)

`RETURNING` 절은 SQLite 3.35 이상이 필요하다. `sqlite3.OperationalError: near "RETURNING"` 이 나오면 아래로 확인한다.

```bash
uv run python -c "import sqlite3; print(sqlite3.sqlite_version)"
```

3.35 미만이면 `add_question` 을 INSERT 후 `SELECT ... WHERE id = last_insert_rowid()` 로 바꾼다.

- [ ] **Step 5: 4종 검증 실행**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

기대: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/store.py tests/services/test_store_questions.py
git commit -m "✨ feat(services): 질문 저장소 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: 실행 이력 저장소 (`services/store.py`)

**Files:**
- Modify: `src/notebooklm_st/services/store.py` (파일 끝의 비공개 헬퍼 `_require_text` 바로 앞에 공개 함수 3개를 추가)
- Test: `tests/services/test_store_history.py`

**Interfaces:**
- Consumes: Task 5의 `store.connect`, Task 3의 `models.RunResult` / `models.AnswerItem` / `models.RunSummary` / `models.citations_to_json` / `models.citations_from_json`
- Produces:
  - `store.save_run(connection, result: models.RunResult) -> int`
  - `store.list_runs(connection, limit: int = 50) -> list[models.RunSummary]`
  - `store.load_run_items(connection, run_id: int) -> list[models.AnswerItem]`

  Task 10이 `save_run`을, Task 12가 나머지 둘을 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/services/test_store_history.py`:

```python
"""실행 이력 저장소 테스트."""

import pytest

from notebooklm_st.core import models
from notebooklm_st.services import store


@pytest.fixture
def connection(tmp_path):
    conn = store.connect(tmp_path / "test.db")
    yield conn
    conn.close()


def make_result(url="https://youtu.be/dQw4w9WgXcQ"):
    return models.RunResult(
        url=url,
        video_id="dQw4w9WgXcQ",
        items=(
            models.AnswerItem(
                question_text="핵심 주장은?",
                answer="세 가지다.",
                citations=(
                    models.Citation(number=1, text="근거 구절", score=0.9),
                ),
                error=None,
            ),
            models.AnswerItem(
                question_text="결론은?",
                answer=None,
                citations=(),
                error="답변을 받지 못했습니다.",
            ),
        ),
    )


def test_save_run_returns_run_id(connection):
    run_id = store.save_run(connection, make_result())
    assert run_id > 0


def test_list_runs_counts_answers(connection):
    store.save_run(connection, make_result())
    runs = store.list_runs(connection)
    assert len(runs) == 1
    assert runs[0].answer_count == 2
    assert runs[0].video_id == "dQw4w9WgXcQ"
    assert runs[0].created_at


def test_list_runs_returns_newest_first(connection):
    store.save_run(connection, make_result("https://youtu.be/aaaaaaaaaaa"))
    store.save_run(connection, make_result("https://youtu.be/bbbbbbbbbbb"))
    urls = [run.url for run in store.list_runs(connection)]
    assert urls == [
        "https://youtu.be/bbbbbbbbbbb",
        "https://youtu.be/aaaaaaaaaaa",
    ]


def test_list_runs_honors_limit(connection):
    for _ in range(3):
        store.save_run(connection, make_result())
    assert len(store.list_runs(connection, limit=2)) == 2


def test_load_run_items_round_trips_answers_and_citations(connection):
    run_id = store.save_run(connection, make_result())
    items = store.load_run_items(connection, run_id)
    assert [item.question_text for item in items] == ["핵심 주장은?", "결론은?"]
    assert items[0].answer == "세 가지다."
    assert items[0].citations == (
        models.Citation(number=1, text="근거 구절", score=0.9),
    )
    assert items[0].succeeded is True
    assert items[1].answer is None
    assert items[1].error == "답변을 받지 못했습니다."
    assert items[1].citations == ()


def test_load_run_items_is_empty_for_unknown_run(connection):
    assert store.load_run_items(connection, 999) == []


def test_run_with_no_answers_is_still_saved(connection):
    empty = models.RunResult(
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        items=(),
    )
    run_id = store.save_run(connection, empty)
    assert store.load_run_items(connection, run_id) == []
    assert store.list_runs(connection)[0].answer_count == 0
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
uv run pytest tests/services/test_store_history.py -v
```

기대: FAIL — `AttributeError: module 'notebooklm_st.services.store' has no attribute 'save_run'`

- [ ] **Step 3: 최소 구현 작성**

`src/notebooklm_st/services/store.py`의 `_require_text` 정의 **바로 위**에 세 함수를 넣는다. 공개 함수를 비공개 헬퍼보다 앞에 두는 기존 배치를 지킨다.

```python
def save_run(
    connection: sqlite3.Connection, result: models.RunResult
) -> int:
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
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
uv run pytest tests/services/test_store_history.py -v
```

기대: PASS (7 passed)

- [ ] **Step 5: 4종 검증 실행**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

기대: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/store.py tests/services/test_store_history.py
git commit -m "✨ feat(services): 실행 이력 저장소 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: 질의 파이프라인 (`services/nlm.py`)

이 계획의 중심 태스크다. 노트북을 만들고, 자막을 인덱싱하고, 질문들을 던지고, 무슨 일이 있어도 노트북을 지운다.

**Files:**
- Create: `src/notebooklm_st/services/nlm.py`
- Test: `tests/services/test_nlm.py`

**Interfaces:**
- Consumes: `models` (Task 3), `errors.to_message` (Task 4), `youtube.extract_video_id` (Task 2)
- Produces:
  - `nlm.SOURCE_WAIT_TIMEOUT: float` — 값은 `120.0`
  - `nlm.TEMP_TITLE_PREFIX: str` — 값은 `"tmp-"`
  - `nlm.ClientLike` — 테스트 가짜 객체가 만족해야 하는 Protocol
  - `nlm.ClientFactory` — `Callable[[], AbstractAsyncContextManager[ClientLike]]`
  - `nlm.run_pipeline(url, questions, on_progress, client_factory=...) -> models.RunResult` (코루틴)

  Task 10이 `asyncio.run(nlm.run_pipeline(...))`으로 부른다. Task 13이 같은 파일에 정리 함수를 덧붙인다.

**설계 근거 (스펙 6.3, 6.4):**
- 노트북 삭제는 `finally`에 둔다. `notebooks.delete`는 멱등적이라 안전하다.
- 두 번째 질문부터 `delete_conversation`을 먼저 부른다. 안 그러면 라이브러리가 직전 대화를 이어가 앞 답변이 뒤 답변의 문맥이 된다.
- 질문 단위 실패(`ChatError`)는 그 항목에만 담고 다음 질문으로 넘어간다. 인덱싱 비용을 이미 치렀기 때문이다. 그 외 예외는 올려 보낸다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/services/test_nlm.py`:

```python
"""질의 파이프라인 테스트 — 실제 네트워크를 타지 않는다."""

import asyncio

import pytest
from notebooklm import exceptions

from notebooklm_st.core import models
from notebooklm_st.services import nlm

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class FakeReference:
    def __init__(self, number, text, score):
        self.citation_number = number
        self.cited_text = text
        self.score = score


class FakeAskResult:
    def __init__(self, answer, conversation_id, references=()):
        self.answer = answer
        self.conversation_id = conversation_id
        self.references = list(references)


class FakeNotebook:
    def __init__(self, notebook_id, title):
        self.id = notebook_id
        self.title = title


class FakeNotebooks:
    def __init__(self, calls):
        self._calls = calls

    async def create(self, title):
        self._calls.append(("create", title))
        return FakeNotebook("nb-1", title)

    async def delete(self, notebook_id):
        self._calls.append(("delete", notebook_id))

    async def list(self):
        self._calls.append(("list",))
        return []


class FakeSources:
    def __init__(self, calls, error=None):
        self._calls = calls
        self._error = error

    async def add_url(self, notebook_id, url, *, wait, wait_timeout):
        self._calls.append(("add_url", notebook_id, url, wait, wait_timeout))
        if self._error is not None:
            raise self._error


class FakeChat:
    def __init__(self, calls, results=None, errors=None):
        self._calls = calls
        self._results = list(results or [])
        self._errors = dict(errors or {})
        self._index = 0

    async def ask(self, notebook_id, question):
        self._calls.append(("ask", notebook_id, question))
        index = self._index
        self._index += 1
        if question in self._errors:
            raise self._errors[question]
        if index < len(self._results):
            return self._results[index]
        return FakeAskResult(f"답변: {question}", f"conv-{index}")

    async def delete_conversation(self, notebook_id, conversation_id):
        self._calls.append(
            ("delete_conversation", notebook_id, conversation_id)
        )


class FakeClient:
    def __init__(self, calls, *, chat=None, sources=None):
        self.notebooks = FakeNotebooks(calls)
        self.sources = sources or FakeSources(calls)
        self.chat = chat or FakeChat(calls)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def make_questions(*texts):
    return [
        models.Question(
            id=index,
            text=text,
            created_at="2026-08-28T10:00:00",
            updated_at="2026-08-28T10:00:00",
        )
        for index, text in enumerate(texts, start=1)
    ]


def run(url, questions, client, progress=None):
    messages = progress if progress is not None else []
    return asyncio.run(
        nlm.run_pipeline(
            url,
            questions,
            messages.append,
            client_factory=lambda: client,
        )
    )


def test_pipeline_creates_indexes_asks_and_deletes():
    calls = []
    client = FakeClient(calls)
    run(URL, make_questions("핵심 주장은?"), client)
    names = [call[0] for call in calls]
    assert names == ["create", "add_url", "ask", "delete"]


def test_notebook_title_is_temporary():
    calls = []
    run(URL, make_questions("핵심 주장은?"), FakeClient(calls))
    title = calls[0][1]
    assert title.startswith(nlm.TEMP_TITLE_PREFIX)
    assert len(title) > len(nlm.TEMP_TITLE_PREFIX)


def test_source_is_added_with_wait_and_timeout():
    calls = []
    run(URL, make_questions("핵심 주장은?"), FakeClient(calls))
    _, notebook_id, url, wait, timeout = calls[1]
    assert notebook_id == "nb-1"
    assert url == URL
    assert wait is True
    assert timeout == nlm.SOURCE_WAIT_TIMEOUT


def test_first_question_does_not_delete_a_conversation():
    calls = []
    run(URL, make_questions("하나"), FakeClient(calls))
    assert "delete_conversation" not in [call[0] for call in calls]


def test_later_questions_start_a_fresh_conversation():
    calls = []
    run(URL, make_questions("하나", "둘", "셋"), FakeClient(calls))
    names = [call[0] for call in calls]
    assert names == [
        "create",
        "add_url",
        "ask",
        "delete_conversation",
        "ask",
        "delete_conversation",
        "ask",
        "delete",
    ]
    assert calls[3][2] == "conv-0"
    assert calls[5][2] == "conv-1"


def test_answers_carry_citations():
    calls = []
    chat = FakeChat(
        calls,
        results=[
            FakeAskResult(
                "세 가지다.",
                "conv-0",
                references=[FakeReference(1, "근거 구절", 0.9)],
            )
        ],
    )
    result = run(URL, make_questions("핵심 주장은?"), FakeClient(calls, chat=chat))
    item = result.items[0]
    assert item.answer == "세 가지다."
    assert item.citations == (
        models.Citation(number=1, text="근거 구절", score=0.9),
    )
    assert item.succeeded is True


def test_result_carries_url_and_video_id():
    calls = []
    result = run(URL, make_questions("하나"), FakeClient(calls))
    assert result.url == URL
    assert result.video_id == "dQw4w9WgXcQ"


def test_chat_failure_affects_only_that_question():
    calls = []
    chat = FakeChat(calls, errors={"둘": exceptions.ChatError("깨짐")})
    result = run(
        URL, make_questions("하나", "둘", "셋"), FakeClient(calls, chat=chat)
    )
    assert [item.succeeded for item in result.items] == [True, False, True]
    assert result.items[1].answer is None
    assert result.items[1].error
    assert [call[0] for call in calls].count("ask") == 3
    assert calls[-1][0] == "delete"


def test_failed_question_does_not_break_conversation_isolation():
    calls = []
    chat = FakeChat(calls, errors={"하나": exceptions.ChatError("깨짐")})
    run(URL, make_questions("하나", "둘"), FakeClient(calls, chat=chat))
    assert "delete_conversation" not in [call[0] for call in calls]


def test_source_failure_still_deletes_the_notebook():
    calls = []
    sources = FakeSources(
        calls, error=exceptions.SourceAddError("https://youtu.be/x")
    )
    with pytest.raises(exceptions.SourceAddError):
        run(URL, make_questions("하나"), FakeClient(calls, sources=sources))
    assert [call[0] for call in calls] == ["create", "add_url", "delete"]


def test_progress_callback_reports_each_stage():
    calls = []
    messages = []
    run(URL, make_questions("하나", "둘"), FakeClient(calls), messages)
    assert any("노트북" in text for text in messages)
    assert any("인덱싱" in text for text in messages)
    assert "질문 1/2" in " ".join(messages)
    assert "질문 2/2" in " ".join(messages)
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
uv run pytest tests/services/test_nlm.py -v
```

기대: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.services.nlm'`

- [ ] **Step 3: 최소 구현 작성**

`src/notebooklm_st/services/nlm.py`:

```python
"""NotebookLM 질의 파이프라인."""

import contextlib
import typing
import uuid
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import notebooklm
from notebooklm import exceptions

from notebooklm_st.core import errors, models, youtube

SOURCE_WAIT_TIMEOUT = 120.0
TEMP_TITLE_PREFIX = "tmp-"


class ReferenceLike(Protocol):
    """답변에 딸려 오는 인용 한 건."""

    citation_number: int
    cited_text: str
    score: float


class AskResultLike(Protocol):
    """``chat.ask`` 의 응답."""

    answer: str
    conversation_id: str
    references: Sequence[ReferenceLike]


class NotebookLike(Protocol):
    """노트북 한 권."""

    id: str
    title: str


class ChatLike(Protocol):
    """대화 API."""

    async def ask(
        self, notebook_id: str, question: str
    ) -> AskResultLike: ...

    async def delete_conversation(
        self, notebook_id: str, conversation_id: str
    ) -> None: ...


class NotebooksLike(Protocol):
    """노트북 API."""

    async def create(self, title: str) -> NotebookLike: ...

    async def delete(self, notebook_id: str) -> None: ...

    async def list(self) -> Sequence[NotebookLike]: ...


class SourcesLike(Protocol):
    """소스 API."""

    async def add_url(
        self,
        notebook_id: str,
        url: str,
        *,
        wait: bool,
        wait_timeout: float,
    ) -> Any: ...


class ClientLike(Protocol):
    """파이프라인이 쓰는 클라이언트의 최소 모양."""

    chat: ChatLike
    notebooks: NotebooksLike
    sources: SourcesLike


ClientFactory = Callable[
    [], contextlib.AbstractAsyncContextManager[ClientLike]
]


def default_client_factory() -> (
    contextlib.AbstractAsyncContextManager[ClientLike]
):
    """저장된 쿠키로 NotebookLM 클라이언트를 연다.

    Returns:
        ``async with`` 로 열 수 있는 클라이언트 컨텍스트.
    """
    # 라이브러리 클래스는 위 Protocol 을 선언하지 않으므로 경계에서
    # 한 번만 캐스팅한다. 파이프라인 내부는 Protocol 로 검사된다.
    return typing.cast(
        contextlib.AbstractAsyncContextManager[ClientLike],
        notebooklm.NotebookLMClient.from_storage(),
    )


async def run_pipeline(
    url: str,
    questions: Sequence[models.Question],
    on_progress: Callable[[str], None],
    client_factory: ClientFactory = default_client_factory,
) -> models.RunResult:
    """영상 하나에 질문들을 던지고 결과를 모은다.

    임시 노트북을 만들어 쓰고 반드시 지운다. 질문마다 앞 대화를 끊어
    답변이 서로 물들지 않게 한다.

    Args:
        url: 검증을 통과한 단일 YouTube 영상 URL.
        questions: 물어볼 질문 목록.
        on_progress: 진행 문구를 받는 콜백.
        client_factory: 클라이언트 컨텍스트를 여는 팩토리. 테스트가
            가짜 클라이언트를 넣을 수 있게 뚫어 둔다.

    Returns:
        질문별 결과를 담은 ``RunResult``.

    Raises:
        exceptions.NotebookLMError: 노트북 생성이나 자막 인덱싱처럼
            질문 이전 단계가 실패한 경우. 질문 단위 실패는 예외가
            아니라 결과 안에 담긴다.
    """
    items: list[models.AnswerItem] = []
    async with client_factory() as client:
        on_progress("임시 노트북 생성 중")
        notebook = await client.notebooks.create(
            f"{TEMP_TITLE_PREFIX}{uuid.uuid4().hex[:8]}"
        )
        try:
            on_progress(
                f"자막 인덱싱 중 (최대 {int(SOURCE_WAIT_TIMEOUT)}초)"
            )
            await client.sources.add_url(
                notebook.id,
                url,
                wait=True,
                wait_timeout=SOURCE_WAIT_TIMEOUT,
            )
            previous_conversation: str | None = None
            total = len(questions)
            for index, question in enumerate(questions, start=1):
                on_progress(f"질문 {index}/{total}")
                if previous_conversation is not None:
                    await client.chat.delete_conversation(
                        notebook.id, previous_conversation
                    )
                item, previous_conversation = await _ask_one(
                    client, notebook.id, question
                )
                items.append(item)
        finally:
            on_progress("임시 노트북 삭제 중")
            await client.notebooks.delete(notebook.id)

    return models.RunResult(
        url=url,
        video_id=youtube.extract_video_id(url) or "",
        items=tuple(items),
    )


async def _ask_one(
    client: ClientLike, notebook_id: str, question: models.Question
) -> tuple[models.AnswerItem, str | None]:
    """질문 하나를 던지고 결과와 이어 갈 대화 ID 를 돌려준다.

    실패하면 대화 ID 로 ``None`` 을 돌려준다. 끊을 대화가 없으므로
    다음 질문이 헛되이 삭제를 시도하지 않는다.
    """
    try:
        result = await client.chat.ask(notebook_id, question.text)
    except exceptions.ChatError as error:
        return (
            models.AnswerItem(
                question_text=question.text,
                answer=None,
                citations=(),
                error=errors.to_message(error).text,
            ),
            None,
        )
    citations = tuple(
        models.Citation(
            number=reference.citation_number,
            text=reference.cited_text,
            score=reference.score,
        )
        for reference in result.references
    )
    return (
        models.AnswerItem(
            question_text=question.text,
            answer=result.answer,
            citations=citations,
            error=None,
        ),
        result.conversation_id,
    )
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
uv run pytest tests/services/test_nlm.py -v
```

기대: PASS (11 passed)

- [ ] **Step 5: 4종 검증 실행**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

기대: 전부 통과. mypy가 `default_client_factory`의 `cast`를 불필요하다고 하면(`warn_redundant_casts`) 그 캐스팅을 지운다.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/nlm.py tests/services/test_nlm.py
git commit -m "✨ feat(services): NotebookLM 질의 파이프라인 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```
---

### Task 8: 실측 점검 — 스펙 13장 확정

이 태스크만 TDD가 아니다. **실제 Google 계정과 네트워크가 필요하다.** 스펙이 "추측으로 채우지 않고 실제로 돌려 보고 정한다"고 남겨 둔 네 가지를 여기서 확정한다.

**Files:**
- Create: `scripts/smoke_check.py`
- Modify: `docs/superpowers/specs/2026-08-28-youtube-qa-design.md` (9장 표 첫 줄, 13장 전체)

**Interfaces:**
- Consumes: `nlm.run_pipeline` (Task 7), `models.Question` (Task 3)
- Produces: 확정된 사실. 9장 예외 표가 실제 예외 종류로 바뀌고, 13장이 측정값으로 교체된다.

- [ ] **Step 1: 로그인**

```bash
uv run playwright install chromium
uv run notebooklm login
```

브라우저 창이 뜨면 구글 계정으로 로그인한다. 창이 닫히고 쿠키가 저장되면 끝이다.

- [ ] **Step 2: 점검 스크립트 작성**

`scripts/smoke_check.py`:

```python
"""실제 계정으로 파이프라인을 한 번 돌려 보는 점검 스크립트.

사용법:
    uv run python scripts/smoke_check.py <YouTube URL>
"""

import asyncio
import sys
import time
from collections.abc import Callable

from notebooklm_st.core import models
from notebooklm_st.services import nlm

_QUESTIONS = (
    "이 영상의 핵심 주장을 3가지로 정리해 주세요.",
    "발표자의 결론은 무엇인가요?",
)


def main() -> int:
    """점검을 실행하고 결과를 표준 출력에 찍는다.

    Returns:
        정상 종료면 0, 사용법이 틀리면 1.
    """
    if len(sys.argv) != 2:
        print("사용법: uv run python scripts/smoke_check.py <YouTube URL>")
        return 1

    url = sys.argv[1]
    questions = [
        models.Question(
            id=index,
            text=text,
            created_at="",
            updated_at="",
        )
        for index, text in enumerate(_QUESTIONS, start=1)
    ]

    started = time.monotonic()
    result = asyncio.run(
        nlm.run_pipeline(url, questions, _report(started))
    )
    print(f"\n총 소요 {time.monotonic() - started:.1f}초")

    for item in result.items:
        print("=" * 60)
        print("질문:", item.question_text)
        print("오류:", item.error)
        print("답변:", item.answer)
        print("인용:", len(item.citations), "건")
        for citation in item.citations:
            preview = citation.text[:120]
            print(
                f"  [{citation.number}] score={citation.score:.2f}"
                f" 길이={len(citation.text)}자"
            )
            print(f"      {preview}")
    return 0


def _report(started: float) -> Callable[[str], None]:
    """경과 시간을 함께 찍는 진행 콜백을 만든다."""

    def report(message: str) -> None:
        """진행 문구 앞에 경과 초를 붙여 찍는다."""
        print(f"[{time.monotonic() - started:6.1f}s] {message}")

    return report


if __name__ == "__main__":
    raise SystemExit(main())
```

`scripts/`는 `mypy src tests` 대상 밖이지만 `ruff check .` 대상에는 들어간다. 그래서 독스트링과 타입 힌트를 갖춰 둔다.

- [ ] **Step 3: 자막이 있는 영상으로 실행**

자막이 확실히 있는 영상(예: 공식 컨퍼런스 발표 영상)의 URL로 실행한다.

```bash
uv run python scripts/smoke_check.py "https://www.youtube.com/watch?v=<자막 있는 영상>"
```

**기록할 것:**
1. `자막 인덱싱 중` 단계에 실제로 걸린 초 — 120초 상한이 적절한지 판단한다.
2. 인용의 `길이=` 값 — `cited_text`가 실용적인 길이인지 본다.
3. 두 번째 답변이 첫 번째 답변을 가리키는 표현("앞서 말한", "위 답변의")을 쓰는지 — 쓰면 대화 격리(스펙 6.4)가 실패한 것이다.

- [ ] **Step 4: 자막이 없는 영상으로 실행**

자막이 없는 영상(개인 브이로그, 음악 영상 등)으로 같은 명령을 돌린다.

```bash
uv run python scripts/smoke_check.py "https://www.youtube.com/watch?v=<자막 없는 영상>"
```

**기록할 것:** traceback 마지막 줄의 예외 클래스 이름. 셋 중 하나일 것이다.
- `notebooklm.exceptions.SourceAddError` → 스펙 9장 표 첫 줄 그대로 맞다.
- `notebooklm.exceptions.SourceProcessingError` → 역시 맞다.
- 예외 없이 통과하고 답변만 비어 있음 → **표가 틀렸다.** `core/errors.py`가 아니라 `nlm.run_pipeline`이 빈 답변을 감지해 안내 문구를 넣도록 고쳐야 하며, 이는 Task 7 수정을 부르는 변경이므로 사용자에게 보고한다.

- [ ] **Step 5: 스펙 문서 갱신**

`docs/superpowers/specs/2026-08-28-youtube-qa-design.md`를 고친다.

- 9장 표 첫 줄의 예외 이름을 Step 4에서 실제로 나온 것으로 좁힌다.
- 13장 네 항목을 각각 측정값으로 바꾼다. 예: "인덱싱 실소요 시간" → "실측 42초 (2026-08-28, 20분 분량 영상). 120초 상한 유지."
- 13장 제목을 `## 13. 실측으로 확정한 사항`으로 바꾼다.

- [ ] **Step 6: 임시 노트북이 남지 않았는지 확인**

```bash
uv run notebooklm notebook list
```

`tmp-`로 시작하는 노트북이 보이면 `finally` 삭제가 동작하지 않은 것이다. 남아 있으면 이름을 기록해 두고 Task 13에서 정리 기능으로 지운다.

- [ ] **Step 7: 커밋**

```bash
git add scripts/smoke_check.py docs/superpowers/specs/2026-08-28-youtube-qa-design.md
git commit -m "📝 docs: 실측 결과로 기획서 미결 항목 확정" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: 공유 커넥션과 UI 조각

**Files:**
- Create: `src/notebooklm_st/session.py`
- Create: `src/notebooklm_st/components/run_progress.py`
- Create: `src/notebooklm_st/components/answer_view.py`
- Test: `tests/test_components.py`

**Interfaces:**
- Consumes: `store.connect` / `store.default_db_path` (Task 5), `models.AnswerItem` (Task 3)
- Produces:
  - `session.get_connection() -> sqlite3.Connection` — `@st.cache_resource`로 감쌌으므로 테스트에서 `session.get_connection.clear()`로 비울 수 있다.
  - `run_progress.progress_status(label: str)` — 컨텍스트 매니저. `Callable[[str], None]`을 넘긴다.
  - `answer_view.render_items(items: Sequence[models.AnswerItem]) -> None`

  Task 10~13의 모든 페이지가 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_components.py`:

```python
"""UI 조각 렌더 테스트."""

from streamlit.testing import v1


def test_progress_status_renders_without_error():
    def script():
        from notebooklm_st.components import run_progress

        with run_progress.progress_status("시작") as report:
            report("1단계")
            report("2단계")

    app = v1.AppTest.from_function(script).run()
    assert not app.exception


def test_answer_view_renders_success_and_failure():
    def script():
        from notebooklm_st.components import answer_view
        from notebooklm_st.core import models

        answer_view.render_items(
            [
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
                models.AnswerItem(
                    question_text="결론은?",
                    answer=None,
                    citations=(),
                    error="답변을 받지 못했습니다.",
                ),
            ]
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    headers = [element.value for element in app.subheader]
    assert headers == ["핵심 주장은?", "결론은?"]
    assert len(app.error) == 1


def test_answer_view_handles_empty_list():
    def script():
        from notebooklm_st.components import answer_view

        answer_view.render_items([])

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
uv run pytest tests/test_components.py -v
```

기대: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.components.run_progress'`

- [ ] **Step 3: 세 파일 작성**

`src/notebooklm_st/session.py`:

```python
"""앱 전체가 공유하는 자원.

``@st.cache_resource`` 로 감싼 커넥션은 Streamlit 의존이라
``services/`` 에 둘 수 없고, 여러 페이지가 함께 쓰므로 특정 페이지에도
둘 수 없다. 그래서 최상위 모듈로 둔다.
"""

import sqlite3

import streamlit as st

from notebooklm_st.services import store


@st.cache_resource
def get_connection() -> sqlite3.Connection:
    """앱 전체가 함께 쓰는 SQLite 커넥션을 돌려준다.

    Returns:
        스키마가 보장된 커넥션. 재실행되어도 같은 객체를 준다.
    """
    return store.connect(store.default_db_path())
```

`src/notebooklm_st/components/run_progress.py`:

```python
"""진행 콜백을 화면 진행 상자에 연결한다."""

import contextlib
from collections.abc import Callable, Iterator

import streamlit as st


@contextlib.contextmanager
def progress_status(label: str) -> Iterator[Callable[[str], None]]:
    """진행 상자를 열고 문구 갱신 콜백을 넘긴다.

    ``services`` 계층은 Streamlit 을 모른 채 이 콜백만 부른다.
    파이프라인이 스크립트와 같은 스레드에서 돌기 때문에 콜백 안에서
    화면을 갱신해도 그대로 전달된다.

    Args:
        label: 상자에 처음 표시할 문구.

    Yields:
        진행 문구를 받는 콜백.
    """
    with st.status(label, expanded=True) as status:

        def report(message: str) -> None:
            """진행 문구를 갱신하고 로그 줄을 남긴다."""
            status.update(label=message)
            st.write(message)

        yield report
        status.update(label="완료", state="complete")
```

`src/notebooklm_st/components/answer_view.py`:

```python
"""답변 카드 렌더."""

from collections.abc import Sequence

import streamlit as st

from notebooklm_st.core import models


def render_items(items: Sequence[models.AnswerItem]) -> None:
    """답변 목록을 위에서 아래로 카드처럼 그린다.

    Args:
        items: 그릴 답변 목록. 비어 있으면 아무것도 그리지 않는다.
    """
    for item in items:
        _render_item(item)


def _render_item(item: models.AnswerItem) -> None:
    """답변 하나를 질문 제목, 본문, 인용 순으로 그린다."""
    st.subheader(item.question_text)
    if item.error is not None:
        st.error(item.error)
        return
    st.markdown(item.answer or "")
    if not item.citations:
        return
    with st.expander(f"인용 {len(item.citations)}건"):
        for citation in item.citations:
            st.markdown(f"**[{citation.number}]** {citation.text}")
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

```bash
uv run pytest tests/test_components.py -v
```

기대: PASS (3 passed)

- [ ] **Step 5: 4종 검증 실행**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

기대: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/session.py src/notebooklm_st/components tests/test_components.py
git commit -m "✨ feat(components): 진행 표시와 답변 렌더 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: 질의 화면과 진입점

**Files:**
- Create: `src/notebooklm_st/app.py`
- Create: `src/notebooklm_st/pages/ask.py`
- Create: `tests/conftest.py`
- Test: `tests/pages/test_ask.py`

**Interfaces:**
- Consumes: `session.get_connection` / `run_progress.progress_status` / `answer_view.render_items` (Task 9), `youtube.is_valid` (Task 2), `errors.to_message` (Task 4), `nlm.run_pipeline` (Task 7), `store.list_questions` / `store.save_run` (Task 5, 6)
- Produces:
  - `ask.render() -> None`
  - `app.main() -> None` — Task 11~13이 여기에 페이지를 덧붙인다.
  - `tests/conftest.py`의 `app_db` fixture — Task 11~13의 페이지 테스트가 재사용한다.

- [ ] **Step 1: 공용 fixture 작성**

`tests/conftest.py`:

```python
"""페이지 테스트가 공유하는 fixture."""

import pytest

from notebooklm_st import session
from notebooklm_st.services import store


@pytest.fixture
def app_db(monkeypatch, tmp_path):
    """앱이 임시 DB 를 쓰게 하고 캐시된 커넥션을 비운다."""
    monkeypatch.setenv(store.DB_PATH_ENV_VAR, str(tmp_path / "app.db"))
    session.get_connection.clear()
    yield store.connect(tmp_path / "app.db")
    session.get_connection.clear()
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/pages/test_ask.py`:

```python
"""질의 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st.services import store


def test_ask_asks_user_to_register_questions_first(app_db):
    def script():
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert any("질문 관리" in element.value for element in app.info)


def test_ask_shows_question_multiselect(app_db):
    store.add_question(app_db, "핵심 주장 3가지 정리")
    store.add_question(app_db, "발표자의 결론은?")

    def script():
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.multiselect) == 1
    assert len(app.multiselect[0].options) == 2


def test_ask_rejects_a_non_youtube_url(app_db):
    store.add_question(app_db, "핵심 주장 3가지 정리")

    def script():
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value("https://example.com/watch?v=x").run()
    assert not app.exception
    assert len(app.error) == 1


def test_ask_run_button_is_disabled_without_input(app_db):
    store.add_question(app_db, "핵심 주장 3가지 정리")

    def script():
        from notebooklm_st.pages import ask

        ask.render()

    app = v1.AppTest.from_function(script).run()
    assert app.button[0].disabled is True
```

- [ ] **Step 3: 테스트 실행해 실패 확인**

```bash
uv run pytest tests/pages/test_ask.py -v
```

기대: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.pages.ask'`

- [ ] **Step 4: 질의 화면 구현**

`src/notebooklm_st/pages/ask.py`:

```python
"""질의 화면."""

import asyncio
import sqlite3
from collections.abc import Sequence

import streamlit as st
from notebooklm import exceptions

from notebooklm_st import session
from notebooklm_st.components import answer_view, run_progress
from notebooklm_st.core import errors, models, youtube
from notebooklm_st.services import nlm, store

_URL_KEY = "ask_url"
_SELECTED_KEY = "ask_selected"
_RESULT_KEY = "ask_result"


def render() -> None:
    """URL 입력, 질문 선택, 실행, 답변 표시를 그린다."""
    st.title("영상 질의")
    connection = session.get_connection()
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

    if st.button(
        "실행",
        key="ask_run",
        disabled=not (url_ok and selected),
    ):
        _execute(connection, url, selected)

    result = st.session_state.get(_RESULT_KEY)
    if result is not None:
        answer_view.render_items(result.items)


def _execute(
    connection: sqlite3.Connection,
    url: str,
    questions: Sequence[models.Question],
) -> None:
    """파이프라인을 돌리고 결과를 이력과 세션에 남긴다.

    실행 중에는 이 탭이 묶인다. 이벤트 루프가 스크립트와 같은
    스레드에서 돌기 때문에 진행 문구는 그대로 화면에 전달된다.
    """
    try:
        with run_progress.progress_status("실행 준비 중") as report:
            result = asyncio.run(nlm.run_pipeline(url, questions, report))
    except exceptions.NotebookLMError as error:
        message = errors.to_message(error)
        if message.level == "info":
            st.info(message.text)
        else:
            st.error(message.text)
        return

    store.save_run(connection, result)
    st.session_state[_RESULT_KEY] = result
```

- [ ] **Step 5: 진입점 구현**

`src/notebooklm_st/app.py`:

```python
"""Streamlit 진입점.

실행:
    uv run streamlit run src/notebooklm_st/app.py
"""

import streamlit as st

from notebooklm_st.pages import ask


def main() -> None:
    """페이지를 등록하고 선택된 페이지를 실행한다."""
    st.set_page_config(page_title="YouTube 질의응답", layout="wide")
    navigation = st.navigation(
        [
            st.Page(ask.render, title="질의", default=True),
        ]
    )
    navigation.run()


main()
```

- [ ] **Step 6: 테스트 실행해 통과 확인**

```bash
uv run pytest tests/pages/test_ask.py -v
```

기대: PASS (4 passed)

- [ ] **Step 7: 앱을 실제로 띄워 확인**

```bash
uv run streamlit run src/notebooklm_st/app.py
```

브라우저가 열리면 확인한다: 제목이 보이고, 질문이 없으면 안내 문구가 뜨고, 아무 URL이나 넣으면 오류 문구가 뜬다. 확인 후 `Ctrl+C`로 종료한다.

- [ ] **Step 8: 4종 검증 실행**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

기대: 전부 통과.

- [ ] **Step 9: 커밋**

```bash
git add src/notebooklm_st/app.py src/notebooklm_st/pages/ask.py tests/conftest.py tests/pages/test_ask.py
git commit -m "✨ feat(pages): 질의 화면과 진입점 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: 질문 관리 화면

**Files:**
- Create: `src/notebooklm_st/pages/question_admin.py`
- Modify: `src/notebooklm_st/app.py` (페이지 목록에 한 줄 추가)
- Test: `tests/pages/test_question_admin.py`

**Interfaces:**
- Consumes: `session.get_connection` (Task 9), `store.list_questions` / `add_question` / `update_question` / `delete_question` (Task 5), `tests/conftest.py`의 `app_db` fixture (Task 10)
- Produces: `question_admin.render() -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/pages/test_question_admin.py`:

```python
"""질문 관리 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st.services import store


def script():
    from notebooklm_st.pages import question_admin

    question_admin.render()


def test_empty_list_renders(app_db):
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.text_area) == 1


def test_existing_questions_are_listed(app_db):
    store.add_question(app_db, "핵심 주장 3가지 정리")
    store.add_question(app_db, "발표자의 결론은?")
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    labels = [element.label for element in app.expander]
    assert labels == ["핵심 주장 3가지 정리", "발표자의 결론은?"]


def test_adding_a_question_saves_it(app_db):
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_area[0].set_value("새 질문").run()
    app.button[0].click().run()
    assert not app.exception
    texts = [q.text for q in store.list_questions(app_db)]
    assert texts == ["새 질문"]


def test_blank_question_is_rejected(app_db):
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_area[0].set_value("   ").run()
    app.button[0].click().run()
    assert len(app.error) == 1
    assert store.list_questions(app_db) == []
```

위젯 인덱스는 렌더 순서를 따른다. `app.button[0]`이 "등록"이고, 질문이 있으면 그 뒤로 질문마다 수정·삭제 버튼이 붙는다. 인덱스가 어긋나면 `key`로 골라 쓴다(`app.button(key="admin_add")`).

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
uv run pytest tests/pages/test_question_admin.py -v
```

기대: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.pages.question_admin'`

- [ ] **Step 3: 구현**

`src/notebooklm_st/pages/question_admin.py`:

```python
"""질문 관리 화면."""

import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import models
from notebooklm_st.services import store

_NEW_KEY = "admin_new"


def render() -> None:
    """질문 등록 입력과 편집 가능한 목록을 그린다.

    등록 후에도 입력란의 글이 남는다. 위젯이 만들어진 뒤에
    ``st.session_state`` 의 위젯 키를 건드리면 Streamlit 이 예외를
    던지므로, 비우려 애쓰는 대신 그대로 둔다.
    """
    st.title("질문 관리")
    connection = session.get_connection()

    text = st.text_area("새 질문", key=_NEW_KEY)
    if st.button("등록", key="admin_add"):
        _add(connection, text)

    for question in store.list_questions(connection):
        _render_row(connection, question)


def _add(connection: sqlite3.Connection, text: str) -> None:
    """새 질문을 저장하고 화면을 다시 그린다."""
    try:
        store.add_question(connection, text)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()


def _render_row(
    connection: sqlite3.Connection, question: models.Question
) -> None:
    """질문 하나를 수정·삭제 버튼과 함께 그린다."""
    with st.expander(question.text):
        edited = st.text_area(
            "내용",
            value=question.text,
            key=f"admin_text_{question.id}",
        )
        left, right = st.columns(2)
        if left.button("수정", key=f"admin_update_{question.id}"):
            _update(connection, question.id, edited)
        if right.button("삭제", key=f"admin_delete_{question.id}"):
            store.delete_question(connection, question.id)
            st.rerun()


def _update(
    connection: sqlite3.Connection, question_id: int, text: str
) -> None:
    """질문 본문을 고치고 화면을 다시 그린다."""
    try:
        store.update_question(connection, question_id, text)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()
```

- [ ] **Step 4: 진입점에 페이지 등록**

`src/notebooklm_st/app.py`의 import와 페이지 목록을 고친다.

```python
from notebooklm_st.pages import ask, question_admin
```

```python
    navigation = st.navigation(
        [
            st.Page(ask.render, title="질의", default=True),
            st.Page(question_admin.render, title="질문 관리"),
        ]
    )
```

- [ ] **Step 5: 테스트 실행해 통과 확인**

```bash
uv run pytest tests/pages/test_question_admin.py -v
```

기대: PASS (4 passed)

- [ ] **Step 6: 4종 검증 실행**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

기대: 전부 통과.

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/pages/question_admin.py src/notebooklm_st/app.py tests/pages/test_question_admin.py
git commit -m "✨ feat(pages): 질문 관리 화면 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: 이력 화면

**Files:**
- Create: `src/notebooklm_st/pages/history.py`
- Modify: `src/notebooklm_st/app.py` (페이지 목록에 한 줄 추가)
- Test: `tests/pages/test_history.py`

**Interfaces:**
- Consumes: `store.list_runs` / `load_run_items` (Task 6), `answer_view.render_items` (Task 9), `session.get_connection` (Task 9)
- Produces: `history.render() -> None`

**설계 주의:** Streamlit은 `st.expander` 안에 또 다른 `st.expander`를 넣지 못한다. `answer_view.render_items`가 인용을 expander로 그리므로, 이력 목록은 expander가 아니라 `st.selectbox`로 실행을 고르는 방식이어야 한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/pages/test_history.py`:

```python
"""이력 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st.core import models
from notebooklm_st.services import store


def script():
    from notebooklm_st.pages import history

    history.render()


def make_result(url="https://youtu.be/dQw4w9WgXcQ"):
    return models.RunResult(
        url=url,
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


def test_empty_history_shows_notice(app_db):
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.info) == 1


def test_saved_run_is_selectable(app_db):
    store.save_run(app_db, make_result())
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.selectbox) == 1
    assert len(app.selectbox[0].options) == 1


def test_selected_run_shows_its_answers(app_db):
    store.save_run(app_db, make_result())
    app = v1.AppTest.from_function(script).run()
    headers = [element.value for element in app.subheader]
    assert headers == ["핵심 주장은?"]
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
uv run pytest tests/pages/test_history.py -v
```

기대: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.pages.history'`

- [ ] **Step 3: 구현**

`src/notebooklm_st/pages/history.py`:

```python
"""실행 이력 화면."""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import answer_view
from notebooklm_st.core import models
from notebooklm_st.services import store

_SELECTED_KEY = "history_selected"


def render() -> None:
    """최근 실행을 고르고 그 답변들을 보여 준다."""
    st.title("이력")
    connection = session.get_connection()
    runs = store.list_runs(connection)
    if not runs:
        st.info("아직 저장된 실행이 없습니다.")
        return

    selected = st.selectbox(
        "실행 선택",
        options=runs,
        format_func=_format_run,
        key=_SELECTED_KEY,
    )
    if selected is None:
        return
    st.caption(selected.url)
    answer_view.render_items(store.load_run_items(connection, selected.id))


def _format_run(run: models.RunSummary) -> str:
    """실행 하나를 목록에 보여 줄 한 줄로 만든다."""
    return f"{run.created_at} · {run.video_id} · 답변 {run.answer_count}건"
```

- [ ] **Step 4: 진입점에 페이지 등록**

`src/notebooklm_st/app.py`의 import와 페이지 목록을 고친다.

```python
from notebooklm_st.pages import ask, history, question_admin
```

```python
    navigation = st.navigation(
        [
            st.Page(ask.render, title="질의", default=True),
            st.Page(question_admin.render, title="질문 관리"),
            st.Page(history.render, title="이력"),
        ]
    )
```

- [ ] **Step 5: 테스트 실행해 통과 확인**

```bash
uv run pytest tests/pages/test_history.py -v
```

기대: PASS (3 passed)

- [ ] **Step 6: 4종 검증 실행**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

기대: 전부 통과.

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/pages/history.py src/notebooklm_st/app.py tests/pages/test_history.py
git commit -m "✨ feat(pages): 이력 화면 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: 임시 노트북 정리 (F-10)

**Files:**
- Modify: `src/notebooklm_st/services/nlm.py` (파일 끝의 `_ask_one` **앞**에 공개 함수 2개 추가)
- Create: `src/notebooklm_st/pages/maintenance.py`
- Modify: `src/notebooklm_st/app.py` (페이지 목록에 한 줄 추가)
- Test: `tests/services/test_nlm_cleanup.py`
- Test: `tests/pages/test_maintenance.py`

**Interfaces:**
- Consumes: `nlm.ClientFactory` / `nlm.default_client_factory` / `nlm.TEMP_TITLE_PREFIX` (Task 7), `models.TempNotebook` (Task 3), `errors.to_message` (Task 4)
- Produces:
  - `nlm.list_temp_notebooks(client_factory=...) -> list[models.TempNotebook]` (코루틴)
  - `nlm.delete_notebooks(notebook_ids: Sequence[str], client_factory=...) -> int` (코루틴)
  - `maintenance.render() -> None`

**설계 근거 (스펙 6.5):** 자동 삭제를 하지 않는다. 앱 시작 시 일괄 삭제하면 다른 창에서 진행 중인 실행의 노트북까지 지운다. 새로 고침 → 확인 → 삭제, 세 동작을 사용자가 밟는다.

- [ ] **Step 1: 정리 함수의 실패하는 테스트 작성**

`tests/services/test_nlm_cleanup.py`:

```python
"""임시 노트북 정리 테스트."""

import asyncio

from notebooklm_st.services import nlm


class FakeNotebook:
    def __init__(self, notebook_id, title):
        self.id = notebook_id
        self.title = title


class FakeNotebooks:
    def __init__(self, calls, existing):
        self._calls = calls
        self._existing = existing

    async def create(self, title):
        self._calls.append(("create", title))
        return FakeNotebook("nb-new", title)

    async def delete(self, notebook_id):
        self._calls.append(("delete", notebook_id))

    async def list(self):
        self._calls.append(("list",))
        return list(self._existing)


class FakeClient:
    def __init__(self, calls, existing=()):
        self.notebooks = FakeNotebooks(calls, list(existing))
        self.sources = None
        self.chat = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def test_list_temp_notebooks_keeps_only_the_prefixed_ones():
    calls = []
    client = FakeClient(
        calls,
        existing=[
            FakeNotebook("nb-1", "tmp-abc12345"),
            FakeNotebook("nb-2", "내 연구 노트"),
            FakeNotebook("nb-3", "tmp-def67890"),
        ],
    )
    found = asyncio.run(nlm.list_temp_notebooks(lambda: client))
    assert [item.id for item in found] == ["nb-1", "nb-3"]
    assert [item.title for item in found] == ["tmp-abc12345", "tmp-def67890"]


def test_list_temp_notebooks_is_empty_when_nothing_matches():
    calls = []
    client = FakeClient(
        calls, existing=[FakeNotebook("nb-2", "내 연구 노트")]
    )
    assert asyncio.run(nlm.list_temp_notebooks(lambda: client)) == []


def test_delete_notebooks_deletes_each_and_counts():
    calls = []
    client = FakeClient(calls)
    deleted = asyncio.run(
        nlm.delete_notebooks(["nb-1", "nb-3"], lambda: client)
    )
    assert deleted == 2
    assert calls == [("delete", "nb-1"), ("delete", "nb-3")]


def test_delete_notebooks_handles_an_empty_list():
    calls = []
    assert asyncio.run(nlm.delete_notebooks([], lambda: FakeClient(calls))) == 0
    assert calls == []
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
uv run pytest tests/services/test_nlm_cleanup.py -v
```

기대: FAIL — `AttributeError: module 'notebooklm_st.services.nlm' has no attribute 'list_temp_notebooks'`

- [ ] **Step 3: 정리 함수 구현**

`src/notebooklm_st/services/nlm.py`의 `_ask_one` 정의 **바로 위**에 넣는다. 공개 함수를 비공개 헬퍼보다 앞에 두는 기존 배치를 지킨다.

```python
async def list_temp_notebooks(
    client_factory: ClientFactory = default_client_factory,
) -> list[models.TempNotebook]:
    """정리 대상으로 남아 있는 임시 노트북을 찾는다.

    제목이 ``tmp-`` 로 시작하는 것만 고른다. 사용자가 손으로 만든
    노트북은 건드리지 않는다.

    Args:
        client_factory: 클라이언트 컨텍스트를 여는 팩토리.

    Returns:
        임시 노트북 목록.
    """
    async with client_factory() as client:
        notebooks = await client.notebooks.list()
    return [
        models.TempNotebook(id=item.id, title=item.title)
        for item in notebooks
        if item.title.startswith(TEMP_TITLE_PREFIX)
    ]


async def delete_notebooks(
    notebook_ids: Sequence[str],
    client_factory: ClientFactory = default_client_factory,
) -> int:
    """주어진 노트북들을 지운다.

    ``notebooks.delete`` 는 멱등적이라 이미 없는 노트북을 지워도
    예외가 나지 않는다.

    Args:
        notebook_ids: 지울 노트북 ID 목록.
        client_factory: 클라이언트 컨텍스트를 여는 팩토리.

    Returns:
        삭제를 시도한 개수.
    """
    if not notebook_ids:
        return 0
    async with client_factory() as client:
        for notebook_id in notebook_ids:
            await client.notebooks.delete(notebook_id)
    return len(notebook_ids)
```

- [ ] **Step 4: 정리 함수 테스트 통과 확인**

```bash
uv run pytest tests/services/test_nlm_cleanup.py -v
```

기대: PASS (4 passed)

- [ ] **Step 5: 화면의 실패하는 테스트 작성**

`tests/pages/test_maintenance.py`:

```python
"""임시 노트북 정리 화면 테스트."""

from streamlit.testing import v1


def test_initial_render_asks_for_refresh(app_db):
    def script():
        from notebooklm_st.pages import maintenance

        maintenance.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.info) == 1


def test_leftover_notebooks_are_warned_about(app_db):
    def script():
        import streamlit as st

        from notebooklm_st.core import models
        from notebooklm_st.pages import maintenance

        st.session_state["maintenance_notebooks"] = [
            models.TempNotebook(id="nb-1", title="tmp-abc12345"),
            models.TempNotebook(id="nb-2", title="tmp-def67890"),
        ]
        maintenance.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.warning) == 1
    assert "2" in app.warning[0].value


def test_clean_state_reports_success(app_db):
    def script():
        import streamlit as st

        from notebooklm_st.pages import maintenance

        st.session_state["maintenance_notebooks"] = []
        maintenance.render()

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.success) == 1
```

- [ ] **Step 6: 화면 구현**

`src/notebooklm_st/pages/maintenance.py`:

```python
"""임시 노트북 정리 화면."""

import asyncio
from collections.abc import Sequence

import streamlit as st
from notebooklm import exceptions

from notebooklm_st.core import errors
from notebooklm_st.services import nlm

_NOTEBOOKS_KEY = "maintenance_notebooks"
_CONFIRM_KEY = "maintenance_confirm"


def render() -> None:
    """남은 임시 노트북을 보여 주고 확인 후 삭제한다."""
    st.title("임시 노트북 정리")
    st.caption(
        "실행이 비정상 종료되면 tmp- 노트북이 남습니다."
        " 다른 창에서 실행 중인 작업이 없을 때만 지우세요."
    )

    if st.button("목록 새로 고침", key="maintenance_refresh"):
        _load()

    notebooks = st.session_state.get(_NOTEBOOKS_KEY)
    if notebooks is None:
        st.info("목록 새로 고침을 눌러 남은 노트북을 확인하세요.")
        return
    if not notebooks:
        st.success("남은 임시 노트북이 없습니다.")
        return

    st.warning(f"남은 임시 노트북 {len(notebooks)}개")
    for notebook in notebooks:
        st.write(f"- {notebook.title}")

    confirmed = st.checkbox("삭제에 동의합니다", key=_CONFIRM_KEY)
    if st.button(
        f"{len(notebooks)}개 모두 삭제",
        key="maintenance_delete",
        disabled=not confirmed,
    ):
        _delete([notebook.id for notebook in notebooks])


def _load() -> None:
    """목록을 조회해 세션에 담는다."""
    try:
        with st.spinner("조회 중"):
            st.session_state[_NOTEBOOKS_KEY] = asyncio.run(
                nlm.list_temp_notebooks()
            )
    except exceptions.NotebookLMError as error:
        st.error(errors.to_message(error).text)


def _delete(notebook_ids: Sequence[str]) -> None:
    """노트북을 지우고 목록을 비운다."""
    try:
        with st.spinner("삭제 중"):
            deleted = asyncio.run(nlm.delete_notebooks(notebook_ids))
    except exceptions.NotebookLMError as error:
        st.error(errors.to_message(error).text)
        return
    st.session_state[_NOTEBOOKS_KEY] = []
    st.success(f"{deleted}개를 삭제했습니다.")
```

- [ ] **Step 7: 진입점에 페이지 등록**

`src/notebooklm_st/app.py`의 import와 페이지 목록을 고친다.

```python
from notebooklm_st.pages import ask, history, maintenance, question_admin
```

```python
    navigation = st.navigation(
        [
            st.Page(ask.render, title="질의", default=True),
            st.Page(question_admin.render, title="질문 관리"),
            st.Page(history.render, title="이력"),
            st.Page(maintenance.render, title="정리"),
        ]
    )
```

- [ ] **Step 8: 화면 테스트 통과 확인**

```bash
uv run pytest tests/pages/test_maintenance.py -v
```

기대: PASS (3 passed)

- [ ] **Step 9: 앱 전체를 띄워 네 화면을 모두 확인**

```bash
uv run streamlit run src/notebooklm_st/app.py
```

확인 목록:
1. 질문 관리에서 질문 두 개를 등록한다.
2. 질의 화면에서 자막 있는 영상 URL을 넣고 질문 두 개를 골라 실행한다. 진행 문구가 단계별로 바뀌고 답변 두 개가 인용과 함께 나온다.
3. 이력 화면에서 방금 실행이 보이고, 고르면 같은 답변이 나온다.
4. 정리 화면에서 새로 고침을 누른다. 방금 실행이 정상 종료됐다면 "남은 임시 노트북이 없습니다"가 나와야 한다.

확인 후 `Ctrl+C`로 종료한다.

- [ ] **Step 10: 4종 검증 실행**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

기대: 전부 통과.

- [ ] **Step 11: 커밋**

```bash
git add src/notebooklm_st/services/nlm.py src/notebooklm_st/pages/maintenance.py src/notebooklm_st/app.py tests/services/test_nlm_cleanup.py tests/pages/test_maintenance.py
git commit -m "✨ feat(pages): 임시 노트북 정리 화면 추가" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## 스펙 요구사항 대응표

| 스펙 요구 | 태스크 |
|---|---|
| F-01 YouTube URL 입력·검증 | 2, 10 |
| F-02 질문 다중 선택 | 10 |
| F-03 질의 실행 | 7, 10 |
| F-04 답변 출력 | 9, 10 |
| F-05~F-08 질문 CRUD | 5, 11 |
| F-09 진행 상태 표시 | 9, 10 |
| F-10 임시 노트북 정리 | 13 |
| F-11 인용 출처 표시 | 3, 7, 9 |
| F-12 결과 이력 저장 | 6, 12 |
| 6.1 실행 모델 (`asyncio.run` 한 번, 클라이언트 비보관) | 7, 10 |
| 6.2 계층 경계 (`core`/`services`에 Streamlit 없음) | 2~7 |
| 6.3 파이프라인 + `finally` 삭제 + 부분 실패 | 7 |
| 6.4 대화 격리 | 7 |
| 6.5 임시 노트북 수명 | 7, 13 |
| 7장 데이터 모델 | 5, 6 |
| 8장 화면 구성 (4개 페이지) | 10~13 |
| 9장 오류 처리 | 4, 10, 13 |
| 10장 테스트 전략 | 모든 태스크 |
| 13장 실측 확정 | 8 |

## 테스트의 가짜 객체와 mypy

Task 7과 13의 가짜 클라이언트는 `nlm.ClientLike` Protocol을 명시적으로 구현하지 않는다. mypy가 이를 문제 삼지 않는 이유는 테스트 함수에 타입 힌트가 없어(`def test_...(app_db):`) mypy가 그 본문을 검사하지 않기 때문이다. 이 상태를 유지한다. 테스트에 반환 타입을 붙이면 갑자기 Protocol 적합성 검사가 시작되어 가짜 객체를 전부 고쳐야 한다.

Protocol의 값어치는 다른 데 있다. `src/` 안의 파이프라인 코드가 `client.notebooks.create(...)` 같은 호출을 오타 없이 쓰는지 mypy가 검사해 준다.
