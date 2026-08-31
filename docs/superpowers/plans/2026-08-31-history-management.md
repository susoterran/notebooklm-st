# 이력 관리 기능 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이력 화면에서 답변을 고치고, 항목을 지우고, 목록에서 영상 제목으로 알아보고, 인용 흔적을 감출 수 있게 한다.

**Architecture:** 인용 필터는 Streamlit 을 모르는 순수 함수(`core/answer_text.py`)로 격리한다. 화면은 저장된 `AnswerItem` 을 필터된 사본으로 바꿔 기존 카드 컴포넌트에 넘긴다 — 카드가 이미 빈 인용을 건너뛰므로 인용 상자는 저절로 사라진다. 편집은 `answer_view.render_items` 에 `on_save` 훅 하나를 더해 열되, 훅이 없거나 항목에 DB ID 가 없으면 그리지 않아 실행 현황 화면에는 새어 나가지 않는다.

**Tech Stack:** Python 3.13, Streamlit, SQLite(sqlite3), uv, ruff, mypy, pytest

**Spec:** `docs/superpowers/specs/2026-08-31-history-management-design.md`

## Global Constraints

- 모든 명령은 `uv run` 을 거친다. 가상환경을 직접 activate 하지 않는다.
- 줄 길이 최대 **80자**, 들여쓰기 스페이스 4칸.
- **모듈 단위 import.** `from x import ClassName` 금지, `import x` 또는 `from pkg import module` 만. 예외는 `typing`·`collections.abc` 심볼.
- `src/` 와 `tests/` 의 모든 모듈·클래스·함수에 Google 형식 한국어 독스트링. 독스트링·주석은 72자에서 줄바꿈.
- 타입 힌트 필수. 내장 제네릭·유니온(`str | None`) 사용, `typing.Optional` 금지. `from __future__ import annotations` 넣지 않는다.
- `core/` 와 `services/` 에서 `import streamlit` 금지.
- 위젯에는 `key=` 를 명시한다.
- `except:` 와 맨 `except Exception:` 금지.
- 각 태스크 끝에서 커밋한다. 커밋 메시지는 `<emoji> <type>(<scope>): <한국어 제목 ≤50자>` 형식이며 마지막 줄에 `Assisted-by: <자신의 모델 ID>` 를 붙인다. `git push` 는 하지 않는다.
- **모든 태스크를 마친 뒤** 4종 검사를 순서대로 통과해야 한다: `uv run ruff format .` → `uv run ruff check --fix .` → `uv run mypy src tests` → `uv run pytest`.

---

### Task 1: 답변 텍스트 필터

**Files:**
- Create: `src/notebooklm_st/core/answer_text.py`
- Test: `tests/core/test_answer_text.py`

**Interfaces:**
- Consumes: `notebooklm_st.core.models.AnswerItem`(기존)
- Produces:
  - `answer_text.strip_trailing_block(text: str) -> str`
  - `answer_text.strip_citation_markers(text: str) -> str`
  - `answer_text.for_display(item: models.AnswerItem) -> models.AnswerItem`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/core/test_answer_text.py` 를 새로 만든다.

```python
"""답변 텍스트 필터 테스트."""

from notebooklm_st.core import answer_text, models


def test_strips_a_single_marker() -> None:
    """번호 하나짜리 인용을 앞 공백까지 지운다."""
    assert answer_text.strip_citation_markers("판단 기준 [1]") == "판단 기준"


def test_strips_a_list_marker() -> None:
    """쉼표로 나열된 인용을 지우고 문장부호를 남긴다."""
    assert (
        answer_text.strip_citation_markers("결정되며[2, 3], 멀티플은")
        == "결정되며, 멀티플은"
    )


def test_strips_a_range_marker() -> None:
    """하이픈 범위 인용을 지운다."""
    assert answer_text.strip_citation_markers("판단 기준 [1-3]") == "판단 기준"


def test_keeps_non_numeric_brackets() -> None:
    """[추론] 같은 표기는 인용이 아니므로 남긴다."""
    assert answer_text.strip_citation_markers("[추론] 전제") == "[추론] 전제"


def test_keeps_markdown_links() -> None:
    """[1](url) 은 마크다운 링크이므로 건드리지 않는다."""
    text = "출처 [1](https://example.com)"
    assert answer_text.strip_citation_markers(text) == text


def test_cuts_from_the_last_rule() -> None:
    """수평선부터 끝까지 버린다."""
    text = "## 태그\n#주식\n\n---\n💡 **다음으로?**\n제안 문단"
    assert answer_text.strip_trailing_block(text) == "## 태그\n#주식"


def test_cuts_only_the_last_rule() -> None:
    """수평선이 여러 개면 마지막 것만 기준으로 삼는다."""
    text = "앞\n\n---\n\n중간\n\n---\n꼬리"
    assert answer_text.strip_trailing_block(text) == "앞\n\n---\n\n중간"


def test_keeps_text_without_a_rule() -> None:
    """수평선이 없으면 원본 그대로 돌려준다."""
    assert answer_text.strip_trailing_block("본문뿐") == "본문뿐"


def test_keeps_the_original_when_cutting_empties_it() -> None:
    """잘라 봐야 남는 게 없으면 원본을 지킨다."""
    text = "---\n꼬리뿐"
    assert answer_text.strip_trailing_block(text) == text


def test_for_display_filters_and_empties_citations() -> None:
    """표시용 사본은 본문을 거르고 인용을 비운다."""
    item = models.AnswerItem(
        question_title="핵심 주장",
        question_text="핵심 주장은?",
        answer="세 가지다 [1, 2].\n\n---\n💡 다음으로?",
        citations=(models.Citation(number=1, text="근거", score=0.9),),
        error=None,
    )

    displayed = answer_text.for_display(item)

    assert displayed.answer == "세 가지다."
    assert displayed.citations == ()
    assert displayed.question_title == "핵심 주장"
    assert displayed.question_text == "핵심 주장은?"


def test_for_display_keeps_a_failed_item_intact() -> None:
    """본문이 없는 실패 항목은 오류 문구를 그대로 둔다."""
    item = models.AnswerItem(
        question_title="결론",
        question_text="결론은?",
        answer=None,
        citations=(),
        error="답변을 받지 못했습니다.",
    )

    displayed = answer_text.for_display(item)

    assert displayed.answer is None
    assert displayed.error == "답변을 받지 못했습니다."
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `uv run pytest tests/core/test_answer_text.py -q`
Expected: FAIL — `ImportError: cannot import name 'answer_text'`

- [ ] **Step 3: 모듈을 구현한다**

`src/notebooklm_st/core/answer_text.py` 를 새로 만든다.

```python
"""답변 본문에서 인용 흔적을 걷어내는 순수 함수들.

결과물만 뽑아 쓰려는 사용자를 위해 화면이 표시 직전에 부른다. 저장된
원문은 절대 바꾸지 않는다 — 여기서 만든 문자열이 DB 로 되돌아가는
경로가 있으면 안 된다.
"""

import dataclasses
import re

from notebooklm_st.core import models

_TRAILING_RULE = re.compile(r"^\s*---\s*$")
"""후속 제안 블록을 여는 수평선.

NotebookLM 은 답변 끝에 다음 할 일을 제안하는 블록을 붙이는데 그
문구가 매번 다르다. 실측한 두 건은 각각 ``💡 **다음으로 무엇을 하기를
원하시나요?**`` 와 ``📊 분석된 …`` 로 시작했다. 고정 문구로 자르면
한쪽을 놓치므로, 둘 앞에 공통으로 놓인 수평선을 기준으로 삼는다.
"""

_CITATION_MARKER = re.compile(r"[ \t]*\[\d+(?:\s*[-,]\s*\d+)*\](?!\()")
"""본문에 박힌 인용 번호.

``[1]`` ``[2, 3]`` ``[1-3]`` 세 형태를 모두 받는다. 숫자·쉼표·하이픈만
받으므로 답변이 쓰는 ``[추론]`` 같은 표기는 건드리지 않고, 뒤에 ``(``
가 오면 마크다운 링크이므로 비켜 간다. 앞 공백까지 먹어야 ``기준
[1-3]`` 이 ``기준`` 으로 깔끔하게 남는다.
"""


def strip_trailing_block(text: str) -> str:
    """``---`` 로 시작하는 마지막 블록을 버린다.

    Args:
        text: 답변 본문.

    Returns:
        마지막 수평선부터 끝까지 걷어낸 본문. 수평선이 없거나 걷어낸
        결과가 비면 원본 그대로.
    """
    lines = text.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if _TRAILING_RULE.match(lines[index]):
            kept = "\n".join(lines[:index]).rstrip()
            return kept or text
    return text


def strip_citation_markers(text: str) -> str:
    """본문에 박힌 인용 번호를 지운다.

    Args:
        text: 답변 본문.

    Returns:
        인용 번호를 지운 본문.
    """
    return _CITATION_MARKER.sub("", text)


def for_display(item: models.AnswerItem) -> models.AnswerItem:
    """인용 흔적을 걷어낸 표시용 사본을 만든다.

    ``citations`` 를 비우는 것만으로 인용 상자까지 사라진다. 답변 카드가
    빈 인용을 그리지 않기 때문이다(→ ``components.answer_view``).

    Args:
        item: 저장된 그대로의 답변 항목.

    Returns:
        본문을 거르고 인용을 비운 사본. 본문이 없는 실패 항목은 인용만
        비운다.
    """
    answer = item.answer
    if answer is not None:
        answer = strip_citation_markers(strip_trailing_block(answer))
    return dataclasses.replace(item, answer=answer, citations=())
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `uv run pytest tests/core/test_answer_text.py -q`
Expected: PASS — 11 passed

- [ ] **Step 5: 커밋한다**

```bash
git add src/notebooklm_st/core/answer_text.py tests/core/test_answer_text.py
git commit -m "$(cat <<'EOF'
✨ feat(core): 답변에서 인용 흔적을 걷어내는 필터 추가

결과물만 뽑아 쓰려면 본문에 박힌 [1] 같은 인용 번호와 맨 아래
후속 제안 블록을 손으로 지워야 했다.

꼬리는 고정 문구로 자를 수 없다. 실측한 두 답변이 각각 다른
문구로 시작했다. 둘 앞에 공통으로 놓인 수평선을 기준으로 삼는다.

인용 번호는 숫자·쉼표·하이픈만 받는다. 답변이 쓰는 [추론] 표기와
마크다운 링크를 건드리지 않기 위해서다.

Assisted-by: <자신의 모델 ID>
EOF
)"
```

---

### Task 2: `runs.title` 컬럼과 제목 왕복 저장

**Files:**
- Modify: `src/notebooklm_st/services/store.py`
- Modify: `src/notebooklm_st/core/models.py`
- Modify: `src/notebooklm_st/services/run_history.py`
- Test: `tests/services/test_store.py`, `tests/services/test_run_history.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `models.RunResult` 에 `title: str | None = None`
  - `models.RunSummary` 에 `title: str | None`(기본값 없음, `video_id` 와 `created_at` 사이)
  - `run_history.save_run` 이 `result.title` 을 저장하고 `list_runs` 가 `RunSummary.title` 을 채운다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_store.py` 맨 아래에 더한다.

```python
def test_connect_rejects_a_database_without_the_run_title(tmp_path) -> None:
    """runs.title 이 없는 예전 스키마 DB 는 연결 시점에 거부된다."""
    db_path = tmp_path / "no_title.db"
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
    raw.commit()
    raw.close()

    with pytest.raises(store.StaleSchemaError) as excinfo:
        store.connect(db_path)
    assert "runs" in str(excinfo.value)
    assert "title" in str(excinfo.value)
```

`tests/services/test_run_history.py` 의 `make_result` 를 제목을 받을 수 있게 바꾼다.

```python
def make_result(
    url: str = "https://youtu.be/dQw4w9WgXcQ",
    title: str | None = None,
) -> models.RunResult:
    """테스트용 실행 결과를 만든다."""
    return models.RunResult(
        url=url,
        video_id="dQw4w9WgXcQ",
        title=title,
        items=(
            models.AnswerItem(
                question_title="핵심 주장",
                question_text="핵심 주장은?",
                answer="세 가지다.",
                citations=(
                    models.Citation(number=1, text="근거 구절", score=0.9),
                ),
                error=None,
            ),
            models.AnswerItem(
                question_title="결론",
                question_text="결론은?",
                answer=None,
                citations=(),
                error="답변을 받지 못했습니다.",
            ),
        ),
    )
```

같은 파일 맨 아래에 더한다.

```python
def test_list_runs_round_trips_the_video_title(connection) -> None:
    """저장한 영상 제목이 목록에 그대로 돌아온다."""
    run_history.save_run(connection, make_result(title="밸류에이션 강의"))
    assert run_history.list_runs(connection)[0].title == "밸류에이션 강의"


def test_list_runs_reports_a_missing_title_as_none(connection) -> None:
    """제목을 못 얻은 실행은 제목이 없는 채로 돌아온다."""
    run_history.save_run(connection, make_result())
    assert run_history.list_runs(connection)[0].title is None
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `uv run pytest tests/services/test_store.py tests/services/test_run_history.py -q`
Expected: FAIL — `RunResult` 가 `title` 인자를 받지 못하고(`TypeError`), 새 스키마 테스트도 실패

- [ ] **Step 3: 스키마를 바꾼다**

`src/notebooklm_st/services/store.py` 의 `_SCHEMA` 안 `runs` 정의를 바꾼다.

```sql
CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY,
    url        TEXT NOT NULL,
    video_id   TEXT NOT NULL,
    title      TEXT,
    created_at TEXT NOT NULL
);
```

같은 파일의 `_EXPECTED_COLUMNS` 에서 `runs` 줄을 바꾼다.

```python
    "runs": frozenset({"id", "url", "video_id", "title", "created_at"}),
```

- [ ] **Step 4: 모델을 바꾼다**

`src/notebooklm_st/core/models.py` 의 `RunResult` 에 필드를 더한다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class RunResult:
    """영상 하나에 질문들을 던진 결과 전체.

    ``title`` 은 NotebookLM 이 소스에서 읽어 온 영상 제목이다. 못 얻는
    실행이 있으므로 없을 수 있고, 그때는 화면이 ``video_id`` 로
    대신한다.
    """

    url: str
    video_id: str
    items: tuple[AnswerItem, ...]
    title: str | None = None
```

같은 파일의 `RunSummary` 에 필드를 더한다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class RunSummary:
    """이력 목록에 한 줄로 보여 줄 실행 요약."""

    id: int
    url: str
    video_id: str
    title: str | None
    created_at: str
    answer_count: int
```

- [ ] **Step 5: 저장소를 바꾼다**

`src/notebooklm_st/services/run_history.py` 의 `save_run` 안 INSERT 를 바꾼다.

```python
    row = connection.execute(
        "INSERT INTO runs (url, video_id, title, created_at)"
        " VALUES (?, ?, ?, ?)"
        " RETURNING id",
        (result.url, result.video_id, result.title, store.now()),
    ).fetchone()
```

같은 파일의 `list_runs` 안 SELECT 와 결과 조립을 바꾼다.

```python
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
```

- [ ] **Step 6: 테스트가 통과하는지 확인한다**

Run: `uv run pytest tests/services/test_store.py tests/services/test_run_history.py -q`
Expected: PASS

- [ ] **Step 7: 기존 DB 파일을 지운다**

프로젝트 루트의 `questions.db` 는 새 스키마를 만족하지 않는다. 폐기하기로 결정한 파일이다(스펙 2.4). `.gitignore` 의 `*.db` 에 걸려 추적되지 않으므로 커밋할 것이 생기지 않는다.

```bash
rm -f questions.db
```

- [ ] **Step 8: 전체 테스트로 회귀를 확인한다**

Run: `uv run pytest -q`
Expected: PASS — `RunSummary` 에 필수 필드를 더했으므로 다른 곳에서 그 모델을 만들고 있으면 여기서 드러난다

- [ ] **Step 9: 커밋한다**

```bash
git add src/notebooklm_st/services/store.py src/notebooklm_st/core/models.py src/notebooklm_st/services/run_history.py tests/services/test_store.py tests/services/test_run_history.py
git commit -m "$(cat <<'EOF'
✨ feat(history): 실행 이력에 영상 제목 컬럼 추가

목록 라벨이 11자리 영상 ID 라 어떤 이력인지 추측해야 했다.

runs 에 title 을 더한다. 이 프로젝트는 마이그레이션을 두지
않기로 했으므로 예전 DB 파일은 폐기한다.

제목을 못 얻는 실행이 있으므로 NULL 을 허용한다. 그때는 화면이
영상 ID 로 대신한다.

Assisted-by: <자신의 모델 ID>
EOF
)"
```

---

### Task 3: 답변 ID 를 화면까지 나른다

**Files:**
- Modify: `src/notebooklm_st/core/models.py`
- Modify: `src/notebooklm_st/services/run_history.py`
- Test: `tests/services/test_run_history.py`

**Interfaces:**
- Consumes: Task 2 의 `run_history.load_run_items`
- Produces: `models.AnswerItem` 에 `id: int | None = None`(맨 끝 필드). `load_run_items` 가 이 값을 채운다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_run_history.py` 맨 아래에 더한다.

```python
def test_load_run_items_carries_the_answer_id(connection) -> None:
    """이력에서 읽은 답변은 자기 ID 를 들고 온다."""
    run_id = run_history.save_run(connection, make_result())

    items = run_history.load_run_items(connection, run_id)

    assert [item.id for item in items] == [1, 2]


def test_a_fresh_answer_item_has_no_id() -> None:
    """파이프라인이 갓 만든 항목은 아직 ID 가 없다."""
    item = models.AnswerItem(
        question_title="핵심 주장",
        question_text="핵심 주장은?",
        answer="세 가지다.",
        citations=(),
        error=None,
    )

    assert item.id is None
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `uv run pytest tests/services/test_run_history.py -q`
Expected: FAIL — `AttributeError: 'AnswerItem' object has no attribute 'id'`

- [ ] **Step 3: 모델에 필드를 더한다**

`src/notebooklm_st/core/models.py` 의 `AnswerItem` 을 바꾼다. 필드는 **맨 끝**에 두고 기본값을 준다. 파이프라인은 DB 를 거치지 않고 이 모델을 만들기 때문이다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class AnswerItem:
    """질문 하나에 대한 실행 결과.

    ``answer`` 와 ``error`` 는 배타적이다. 성공한 항목은 ``error`` 가
    ``None`` 이고, 실패한 항목은 ``answer`` 가 ``None`` 이다.

    ``question_title`` 과 ``question_text`` 를 둘 다 복사해 둔다.
    화면은 제목을 머리글로 쓰고 원문은 접어서 보여준다.

    ``id`` 는 이력에서 읽어온 항목만 가진다. 파이프라인이 갓 만든
    항목은 아직 저장되지 않아 ``None`` 이며, 화면은 이 값이 있을 때만
    편집 상자를 그린다.
    """

    question_title: str
    question_text: str
    answer: str | None
    citations: tuple[Citation, ...]
    error: str | None
    id: int | None = None
```

- [ ] **Step 4: 저장소가 ID 를 채우게 한다**

`src/notebooklm_st/services/run_history.py` 의 `load_run_items` 를 바꾼다.

```python
    rows = connection.execute(
        "SELECT id, question_title, question_text, answer, citations, error"
        " FROM answers WHERE run_id = ? ORDER BY id",
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
```

독스트링의 `Returns:` 절에 한 줄을 더한다.

```
    Returns:
        답변 목록. 각 항목은 자기 ``id`` 를 들고 온다. 그런 실행이
        없으면 빈 목록.
```

- [ ] **Step 5: 테스트가 통과하는지 확인한다**

Run: `uv run pytest tests/services/test_run_history.py -q`
Expected: PASS

- [ ] **Step 6: 커밋한다**

```bash
git add src/notebooklm_st/core/models.py src/notebooklm_st/services/run_history.py tests/services/test_run_history.py
git commit -m "$(cat <<'EOF'
✨ feat(history): 이력에서 읽은 답변에 ID 를 실어 준다

답변을 고치려면 어떤 행인지 지목할 키가 필요한데 화면까지
올라오는 값에 그게 없었다.

id 는 이력에서 읽어온 항목만 가진다. 파이프라인이 갓 만든
항목은 None 이므로, 화면이 이 값으로 편집 가능 여부를 가릴 수
있다. 실행 현황에 편집 상자가 새어 나가는 것을 타입 수준에서
막는 장치다.

Assisted-by: <자신의 모델 ID>
EOF
)"
```

---

### Task 4: 이력 수정·삭제 저장소 함수

**Files:**
- Modify: `src/notebooklm_st/services/run_history.py`
- Test: `tests/services/test_run_history.py`

**Interfaces:**
- Consumes: Task 3 의 `models.AnswerItem.id`
- Produces:
  - `run_history.update_answer(connection: sqlite3.Connection, answer_id: int, answer: str) -> None`
  - `run_history.delete_run(connection: sqlite3.Connection, run_id: int) -> None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_run_history.py` 맨 아래에 더한다.

```python
def test_update_answer_replaces_the_body(connection) -> None:
    """저장된 답변 본문을 바꾼다."""
    run_id = run_history.save_run(connection, make_result())
    first = run_history.load_run_items(connection, run_id)[0]
    assert first.id is not None

    run_history.update_answer(connection, first.id, "고친 답변")

    items = run_history.load_run_items(connection, run_id)
    assert items[0].answer == "고친 답변"
    assert items[0].citations == first.citations


def test_update_answer_trims_whitespace(connection) -> None:
    """앞뒤 공백은 지우고 저장한다."""
    run_id = run_history.save_run(connection, make_result())
    first = run_history.load_run_items(connection, run_id)[0]
    assert first.id is not None

    run_history.update_answer(connection, first.id, "  고친 답변  ")

    assert run_history.load_run_items(connection, run_id)[0].answer == (
        "고친 답변"
    )


def test_update_answer_rejects_an_empty_body(connection) -> None:
    """답변을 비우는 것은 고치기가 아니므로 거부한다."""
    run_id = run_history.save_run(connection, make_result())
    first = run_history.load_run_items(connection, run_id)[0]
    assert first.id is not None

    with pytest.raises(ValueError):
        run_history.update_answer(connection, first.id, "   ")


def test_update_answer_rejects_an_unknown_id(connection) -> None:
    """없는 답변을 고치려 하면 알린다."""
    with pytest.raises(ValueError):
        run_history.update_answer(connection, 999, "고친 답변")


def test_delete_run_removes_its_answers_too(connection) -> None:
    """실행을 지우면 딸린 답변도 함께 사라진다."""
    run_id = run_history.save_run(connection, make_result())

    run_history.delete_run(connection, run_id)

    assert run_history.list_runs(connection) == []
    remaining = connection.execute(
        "SELECT COUNT(*) AS n FROM answers WHERE run_id = ?", (run_id,)
    ).fetchone()
    assert remaining["n"] == 0


def test_delete_run_keeps_other_runs(connection) -> None:
    """지정한 실행만 지운다."""
    kept = run_history.save_run(
        connection, make_result("https://youtu.be/aaaaaaaaaaa")
    )
    doomed = run_history.save_run(
        connection, make_result("https://youtu.be/bbbbbbbbbbb")
    )

    run_history.delete_run(connection, doomed)

    assert [run.id for run in run_history.list_runs(connection)] == [kept]


def test_delete_run_is_silent_for_an_unknown_id(connection) -> None:
    """이미 없는 실행을 지워도 조용히 넘어간다."""
    run_history.delete_run(connection, 999)
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `uv run pytest tests/services/test_run_history.py -q`
Expected: FAIL — `module 'notebooklm_st.services.run_history' has no attribute 'update_answer'`

- [ ] **Step 3: 함수를 구현한다**

`src/notebooklm_st/services/run_history.py` 의 `load_run_items` 아래에 더한다.

```python
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
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `uv run pytest tests/services/test_run_history.py -q`
Expected: PASS

- [ ] **Step 5: 커밋한다**

```bash
git add src/notebooklm_st/services/run_history.py tests/services/test_run_history.py
git commit -m "$(cat <<'EOF'
✨ feat(history): 이력 수정·삭제 함수 추가

이력은 지금까지 추가 전용이었다. 잘못된 답변을 고치거나 중복
항목을 지우려면 DB 파일을 직접 여는 수밖에 없었다.

본문만 고칠 수 있게 한다. 질문 제목과 원문, 인용은 무엇을
물어서 이 답이 나왔는가의 기록이므로 손대지 않는다.

빈 본문은 거부한다. 답변을 비우는 것은 고치기가 아니라 지우기고,
지우기는 이력 단위로 따로 있다.

Assisted-by: <자신의 모델 ID>
EOF
)"
```

---

### Task 5: 파이프라인이 영상 제목을 받아 온다

**Files:**
- Modify: `src/notebooklm_st/services/nlm.py`
- Test: `tests/services/test_nlm.py`

**Interfaces:**
- Consumes: Task 2 의 `models.RunResult.title`
- Produces: `nlm.SourceLike` Protocol(`title: str | None`). `run_pipeline` 이 돌려주는 `RunResult` 의 `title` 이 채워진다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_nlm.py` 의 `FakeSources` 바로 위에 클래스를 더한다.

```python
class FakeSource:
    """가짜 소스 한 건. 파이프라인은 제목만 읽는다."""

    def __init__(self, title=None):
        """제목을 저장한다."""
        self.title = title
```

같은 파일의 `FakeSources` 를 제목을 돌려주도록 바꾼다.

```python
class FakeSources:
    """가짜 소스 API. 지정하면 소스 추가 시 오류를 던진다."""

    def __init__(self, calls, error=None, title=None):
        """호출 기록 리스트, 던질 오류, 돌려줄 제목을 받아 둔다."""
        self._calls = calls
        self._error = error
        self._title = title

    async def add_url(self, notebook_id, url, *, wait, wait_timeout):
        """URL 추가 호출을 기록하고 가짜 소스를 돌려준다."""
        self._calls.append(("add_url", notebook_id, url, wait, wait_timeout))
        if self._error is not None:
            raise self._error
        return FakeSource(self._title)
```

같은 파일 맨 아래에 테스트를 더한다.

```python
def test_pipeline_carries_the_source_title():
    """소스가 알려 준 영상 제목을 결과에 싣는다."""
    calls = []
    client = FakeClient(
        calls, sources=FakeSources(calls, title="밸류에이션 강의")
    )

    result = run(URL, make_questions("핵심 주장은?"), client)

    assert result.title == "밸류에이션 강의"


def test_pipeline_reports_a_blank_title_as_none():
    """제목이 비어 있으면 없는 것으로 본다."""
    calls = []
    client = FakeClient(calls, sources=FakeSources(calls, title=""))

    result = run(URL, make_questions("핵심 주장은?"), client)

    assert result.title is None
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `uv run pytest tests/services/test_nlm.py -q`
Expected: FAIL — `assert None == '밸류에이션 강의'`

- [ ] **Step 3: 소스 프로토콜을 더한다**

`src/notebooklm_st/services/nlm.py` 의 `SourcesLike` 정의 **바로 위**에 더한다.

```python
class SourceLike(Protocol):
    """노트북에 붙은 소스 한 건.

    라이브러리의 ``Source`` 는 필드가 많지만 파이프라인은 제목만 쓴다.
    유튜브 소스에서는 이 값이 영상 제목이다.
    """

    title: str | None
```

- [ ] **Step 4: `add_url` 의 반환 타입을 좁힌다**

먼저 파일 맨 위 import 에서 `Any` 를 뺀다. 아래에서 유일한 사용처가 사라지므로, 남겨 두면 `ruff` 가 미사용 import 로 잡는다.

```python
from typing import Protocol, cast
```

같은 파일의 `SourcesLike` 를 바꾼다. 기존의 `# 반환된 Source 를 파이프라인이 쓰지 않으므로 모양을 고정하지 않는다.` 주석은 지운다 — 이제 쓴다.

```python
class SourcesLike(Protocol):
    """소스 API."""

    async def add_url(
        self,
        notebook_id: str,
        url: str,
        *,
        wait: bool,
        wait_timeout: float,
    ) -> SourceLike:
        """URL 소스를 노트북에 추가하고 그 소스를 돌려준다."""
        ...
```

- [ ] **Step 5: 파이프라인이 제목을 싣게 한다**

같은 파일의 `run_pipeline` 을 바꾼다. `items` 를 만드는 줄 바로 아래에 제목 변수를 두고, `add_url` 결과에서 읽어, 마지막 `RunResult` 에 넘긴다.

```python
    items: list[models.AnswerItem] = []
    title: str | None = None
    async with client_factory() as client:
        on_progress("임시 노트북 생성 중")
        notebook = await client.notebooks.create(
            f"{TEMP_TITLE_PREFIX}{uuid.uuid4().hex[:8]}"
        )
        try:
            on_progress(f"자막 인덱싱 중 (최대 {int(SOURCE_WAIT_TIMEOUT)}초)")
            source = await client.sources.add_url(
                notebook.id,
                url,
                wait=True,
                wait_timeout=SOURCE_WAIT_TIMEOUT,
            )
            # 빈 제목은 없는 것으로 본다. 화면이 video_id 로 대신한다.
            title = source.title or None
```

같은 함수 마지막의 반환을 바꾼다.

```python
    return models.RunResult(
        url=url,
        video_id=youtube.extract_video_id(url) or "",
        items=tuple(items),
        title=title,
    )
```

`run_pipeline` 독스트링의 `Returns:` 절을 바꾼다.

```
    Returns:
        질문별 결과와 영상 제목을 담은 ``RunResult``.
```

- [ ] **Step 6: 테스트가 통과하는지 확인한다**

Run: `uv run pytest tests/services/test_nlm.py -q`
Expected: PASS

- [ ] **Step 7: 커밋한다**

```bash
git add src/notebooklm_st/services/nlm.py tests/services/test_nlm.py
git commit -m "$(cat <<'EOF'
✨ feat(nlm): 소스가 알려 준 영상 제목을 결과에 싣는다

이력 목록이 영상 ID 를 보여 주는 대신 제목을 쓰려면 제목을 어딘가
에서 얻어야 했다. 그런데 이미 손에 있었다 — 소스를 추가하고 받은
값을 파이프라인이 그냥 버리고 있었다.

새 의존성도 추가 네트워크 호출도 필요 없다. 반환 타입만 Any 에서
프로토콜로 좁혀 제목을 읽는다.

빈 제목은 없는 것으로 본다. 화면이 영상 ID 로 대신한다.

Assisted-by: <자신의 모델 ID>
EOF
)"
```

---

### Task 6: 답변 카드에 저장 훅을 연다

**Files:**
- Modify: `src/notebooklm_st/components/answer_view.py`
- Test: `tests/test_components.py`

**Interfaces:**
- Consumes: Task 3 의 `models.AnswerItem.id`
- Produces: `answer_view.render_items(items: Sequence[models.AnswerItem], *, on_save: Callable[[int, str], None] | None = None) -> None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_components.py` 맨 아래에 더한다.

```python
def test_answer_view_stays_read_only_without_a_save_hook() -> None:
    """저장 훅이 없으면 편집 상자를 그리지 않는다."""

    def script():
        """AppTest 진입점 — 훅 없이 답변을 그린다."""
        from notebooklm_st.components import answer_view
        from notebooklm_st.core import models

        answer_view.render_items(
            [
                models.AnswerItem(
                    question_title="핵심 주장",
                    question_text="핵심 주장은?",
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                    id=7,
                )
            ]
        )

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.text_area) == 0
    rendered = " ".join(element.value for element in app.markdown)
    assert "세 가지다." in rendered


def test_answer_view_stays_read_only_for_an_item_without_an_id() -> None:
    """저장 훅이 있어도 ID 가 없으면 편집하지 않는다."""

    def script():
        """AppTest 진입점 — ID 없는 항목에 훅을 준다."""
        import streamlit as st
        from notebooklm_st.components import answer_view
        from notebooklm_st.core import models

        if "saved" not in st.session_state:
            st.session_state["saved"] = []
        saved = st.session_state["saved"]
        answer_view.render_items(
            [
                models.AnswerItem(
                    question_title="핵심 주장",
                    question_text="핵심 주장은?",
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                )
            ],
            on_save=lambda answer_id, text: saved.append((answer_id, text)),
        )

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.text_area) == 0


def test_answer_view_saves_the_edited_body() -> None:
    """편집 상자에 고친 본문을 저장 훅으로 넘긴다."""

    def script():
        """AppTest 진입점 — 편집 가능한 답변을 그린다."""
        import streamlit as st
        from notebooklm_st.components import answer_view
        from notebooklm_st.core import models

        if "saved" not in st.session_state:
            st.session_state["saved"] = []
        saved = st.session_state["saved"]
        answer_view.render_items(
            [
                models.AnswerItem(
                    question_title="핵심 주장",
                    question_text="핵심 주장은?",
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                    id=7,
                )
            ],
            on_save=lambda answer_id, text: saved.append((answer_id, text)),
        )

    app = v1.AppTest.from_function(script)
    app.run()
    assert len(app.text_area) == 1

    app.text_area[0].set_value("고친 답변").run()
    app.button[0].click().run()

    assert not app.exception
    assert app.session_state["saved"] == [(7, "고친 답변")]
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `uv run pytest tests/test_components.py -q`
Expected: FAIL — `render_items() got an unexpected keyword argument 'on_save'`

- [ ] **Step 3: 컴포넌트를 바꾼다**

`src/notebooklm_st/components/answer_view.py` 를 통째로 바꾼다.

```python
"""답변 카드 렌더."""

from collections.abc import Callable, Sequence

import streamlit as st

from notebooklm_st.core import models

# st.text_area 의 height 는 픽셀이다. 라벨 있는 기본값 122px 가 3줄이고
# 줄당 24px 이므로 20줄은 122 + 17 * 24 = 530px 이다. 답변은 길어서
# 질문 관리 화면보다 넉넉해야 고칠 자리를 찾을 수 있다.
_EDIT_HEIGHT = 530

SaveCallback = Callable[[int, str], None]


def render_items(
    items: Sequence[models.AnswerItem],
    *,
    on_save: SaveCallback | None = None,
) -> None:
    """답변 목록을 위에서 아래로 카드처럼 그린다.

    항목 사이에만 구분자를 넣는다. 마지막 뒤에도 넣으면 실행 현황
    화면에서 실행 간 구분자와 겹쳐 줄이 두 개가 된다.

    Args:
        items: 그릴 답변 목록. 비어 있으면 아무것도 그리지 않는다.
        on_save: 고친 본문을 받을 콜백. 답변 ID 와 새 본문을 받는다.
            주지 않으면 카드는 읽기 전용이다.
    """
    for index, item in enumerate(items):
        if index > 0:
            st.divider()
        _render_item(item, on_save)


def _render_item(
    item: models.AnswerItem, on_save: SaveCallback | None
) -> None:
    """답변 하나를 제목, 접은 질문, 본문, 인용 순으로 그린다.

    질문 원문은 접어 둔다. 바로 확인할 필요가 없고, 마크다운 문법이
    섞여 있으면 머리글 자리에서 서식으로 렌더되어 읽기 어렵기
    때문이다. ``st.expander`` 의 라벨도 마크다운을 렌더하므로 라벨은
    고정 문구로 두고, 원문은 마크다운을 파싱하지 않는 ``st.text`` 로
    출력한다. 답변 본문은 서식이 살아야 읽히므로 그대로 렌더한다.
    """
    st.subheader(item.question_title)
    with st.expander("질문 원문"):
        st.text(item.question_text)
    if item.error is not None:
        st.error(item.error)
        return
    _render_answer(item, on_save)
    if not item.citations:
        return
    with st.expander(f"인용 {len(item.citations)}건"):
        for citation in item.citations:
            st.markdown(f"**[{citation.number}]** {citation.text}")


def _render_answer(
    item: models.AnswerItem, on_save: SaveCallback | None
) -> None:
    """편집이 열려 있으면 입력 상자로, 아니면 본문 그대로 그린다.

    두 조건을 모두 만족해야 편집을 연다. 호출자가 저장 콜백을 줬고,
    항목이 DB 에서 온 것이어서 지목할 ID 가 있어야 한다. 파이프라인이
    갓 만든 항목은 ID 가 없으므로 실행 현황 화면에는 편집 상자가
    나타나지 않는다.
    """
    if on_save is None or item.id is None:
        st.markdown(item.answer or "")
        return
    edited = st.text_area(
        "답변",
        value=item.answer or "",
        key=f"answer_edit_{item.id}",
        height=_EDIT_HEIGHT,
    )
    if st.button("저장", key=f"answer_save_{item.id}"):
        on_save(item.id, edited)
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `uv run pytest tests/test_components.py -q`
Expected: PASS

- [ ] **Step 5: 실행 현황 화면이 그대로인지 확인한다**

Run: `uv run pytest tests/pages/test_dashboard.py -q`
Expected: PASS — `on_save` 를 주지 않으므로 동작이 바뀌지 않아야 한다

- [ ] **Step 6: 커밋한다**

```bash
git add src/notebooklm_st/components/answer_view.py tests/test_components.py
git commit -m "$(cat <<'EOF'
✨ feat(components): 답변 카드에 저장 훅을 연다

이력 화면에서 답변을 고칠 수 있어야 하는데, 답변 카드는 이력과
실행 현황이 함께 쓴다. 편집을 통째로 넣으면 실행 현황에도 딸려
간다.

훅을 옵션으로 둔다. 주지 않으면 이전과 같은 읽기 전용이다.
게다가 항목에 DB ID 가 있어야만 편집을 여는데, 파이프라인이 갓
만든 항목은 ID 가 없으므로 두 겹으로 막힌다.

Assisted-by: <자신의 모델 ID>
EOF
)"
```

---

### Task 7: 스키마 게이트

**Files:**
- Create: `src/notebooklm_st/components/schema_gate.py`
- Modify: `src/notebooklm_st/app.py`
- Test: `tests/test_components.py`

**Interfaces:**
- Consumes: `notebooklm_st.session.get_connection`(기존), `notebooklm_st.services.store.StaleSchemaError`(기존)
- Produces: `schema_gate.render() -> None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_components.py` 맨 아래에 더한다. 파일 위쪽 import 에 `store` 를 더한다: `from notebooklm_st.services import auth, store`.

```python
def test_schema_gate_explains_a_stale_database(monkeypatch) -> None:
    """스키마가 어긋나면 트레이스백 대신 안내를 보여 준다."""

    def raise_stale():
        """낡은 스키마를 만난 커넥션을 흉내낸다."""
        raise store.StaleSchemaError(
            "app.db 의 runs 테이블이 오래된 스키마입니다."
            " 이 파일을 지우고 다시 실행하세요."
        )

    monkeypatch.setattr(session, "get_connection", raise_stale)

    def script():
        """AppTest 진입점 — 스키마 게이트를 그린다."""
        from notebooklm_st.components import schema_gate

        schema_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.error) == 1
    assert "지우고 다시 실행" in app.error[0].value


def test_schema_gate_stays_quiet_when_the_schema_matches(app_db) -> None:
    """스키마가 맞으면 아무것도 그리지 않는다."""

    def script():
        """AppTest 진입점 — 스키마 게이트를 그린다."""
        from notebooklm_st.components import schema_gate

        schema_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert not app.error
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `uv run pytest tests/test_components.py -k schema_gate -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.components.schema_gate'`

- [ ] **Step 3: 게이트를 구현한다**

`src/notebooklm_st/components/schema_gate.py` 를 새로 만든다.

```python
"""DB 스키마가 코드와 맞는지 확인하는 조각.

앱이 뜰 때 가장 먼저 돈다. 스키마가 어긋나면 아래에서 어떤 화면을
그리든 커넥션을 여는 순간 예외가 터지므로, 여기서 한 번 잡아 사람이
읽을 수 있는 안내로 바꾸고 멈춘다.
"""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.services import store


def render() -> None:
    """커넥션을 한 번 열어 보고, 스키마가 어긋나면 안내 후 멈춘다.

    이 프로젝트는 마이그레이션 경로를 두지 않기로 했으므로(→
    ``services.store``) 사용자가 할 일은 예전 DB 파일을 지우는 것뿐
    이다. 예외 메시지가 이미 파일 경로와 그 안내를 담고 있어 그대로
    보여 준다.
    """
    try:
        session.get_connection()
    except store.StaleSchemaError as error:
        st.error(str(error))
        st.stop()
```

- [ ] **Step 4: 진입점에서 부른다**

`src/notebooklm_st/app.py` 의 import 를 바꾼다.

```python
from notebooklm_st.components import auth_gate, schema_gate
```

같은 파일 `main()` 안에서 `st.set_page_config(...)` **바로 다음 줄**에 더한다.

```python
    schema_gate.render()
```

`main()` 독스트링에 한 줄을 더한다.

```
    DB 스키마부터 확인한다. 어긋난 채로 페이지를 등록하면 어느 화면을
    열든 커넥션을 여는 순간 트레이스백이 노출된다.
```

- [ ] **Step 5: 테스트가 통과하는지 확인한다**

Run: `uv run pytest tests/test_components.py -k schema_gate -q`
Expected: PASS

- [ ] **Step 6: 앱 테스트로 회귀를 확인한다**

Run: `uv run pytest tests/test_app.py -q`
Expected: PASS

- [ ] **Step 7: 커밋한다**

```bash
git add src/notebooklm_st/components/schema_gate.py src/notebooklm_st/app.py tests/test_components.py
git commit -m "$(cat <<'EOF'
🐛 fix(app): 낡은 스키마를 안내 문구로 바꾼다

StaleSchemaError 를 아무도 잡지 않아 사용자는 모든 화면에서 날것
의 파이썬 트레이스백을 보게 된다. 이 프로젝트는 마이그레이션을
두지 않기로 했으므로 스키마를 바꿀 때마다 반드시 겪는 길이다.

인증 게이트와 대칭으로 게이트를 하나 두고 진입점에서 가장 먼저
부른다. 예외 메시지가 이미 파일 경로와 해야 할 일을 담고 있으므로
그대로 보여 준다.

Assisted-by: <자신의 모델 ID>
EOF
)"
```

---

### Task 8: 이력 목록 라벨에 영상 제목

**Files:**
- Modify: `src/notebooklm_st/pages/history.py`
- Test: `tests/pages/test_history.py`

**Interfaces:**
- Consumes: Task 2 의 `models.RunSummary.title`
- Produces: 이력 selectbox 의 라벨이 `제목 · 시각 · 답변 N건` 형식이 된다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_history.py` 의 `make_result` 를 제목을 받을 수 있게 바꾼다.

```python
def make_result(
    url: str = "https://youtu.be/dQw4w9WgXcQ",
    title: str | None = None,
) -> models.RunResult:
    """테스트용 실행 결과를 만든다."""
    return models.RunResult(
        url=url,
        video_id="dQw4w9WgXcQ",
        title=title,
        items=(
            models.AnswerItem(
                question_title="핵심 주장",
                question_text="핵심 주장은?",
                answer="세 가지다.",
                citations=(
                    models.Citation(number=1, text="근거 구절", score=0.9),
                ),
                error=None,
            ),
        ),
    )
```

같은 파일 맨 아래에 더한다.

```python
def test_run_label_leads_with_the_video_title(app_db) -> None:
    """목록 라벨이 영상 제목으로 시작한다."""
    run_history.save_run(app_db, make_result(title="밸류에이션 강의"))

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert app.selectbox[0].options[0].startswith("밸류에이션 강의 · ")


def test_run_label_falls_back_to_the_video_id(app_db) -> None:
    """제목이 없으면 영상 ID 로 대신한다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert app.selectbox[0].options[0].startswith("dQw4w9WgXcQ · ")


def test_run_label_shortens_a_long_title(app_db) -> None:
    """제목이 길면 잘라서 한 줄에 담는다."""
    run_history.save_run(app_db, make_result(title="가" * 100))

    app = v1.AppTest.from_function(script).run()

    label = app.selectbox[0].options[0]
    assert label.startswith("가" * 59 + "… · ")
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `uv run pytest tests/pages/test_history.py -q`
Expected: FAIL — 라벨이 아직 `2026-…T…:… · dQw4w9WgXcQ · 답변 1건` 형식이다

- [ ] **Step 3: 라벨을 바꾼다**

`src/notebooklm_st/pages/history.py` 의 `_SELECTED_KEY` 아래에 상수를 더한다.

```python
# 목록은 한 줄로 읽혀야 값을 한다. 질문 관리 화면과 같은 상한을 쓴다.
_TITLE_MAX_CHARS = 60
```

같은 파일의 `_format_run` 을 바꾸고 `_shorten` 을 더한다.

```python
def _format_run(run: models.RunSummary) -> str:
    """실행 하나를 목록에 보여 줄 한 줄로 만든다.

    제목을 앞에 둔다. 목록에서 고르는 사람이 먼저 알고 싶은 것은
    시각이 아니라 어떤 영상이었는지다. 목록은 최신순으로 고정되어
    있으므로 시각은 뒤에 있어도 읽는 데 지장이 없다.
    """
    label = _shorten(run.title) if run.title else run.video_id
    return f"{label} · {run.created_at} · 답변 {run.answer_count}건"


def _shorten(title: str) -> str:
    """목록 한 줄에 들어가도록 제목을 자른다.

    자르기는 라벨을 만드는 이 자리에서만 한다. 저장된 제목은 그대로
    둔다.
    """
    if len(title) <= _TITLE_MAX_CHARS:
        return title
    return f"{title[: _TITLE_MAX_CHARS - 1]}…"
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `uv run pytest tests/pages/test_history.py -q`
Expected: PASS

- [ ] **Step 5: 커밋한다**

```bash
git add src/notebooklm_st/pages/history.py tests/pages/test_history.py
git commit -m "$(cat <<'EOF'
✨ feat(history): 목록 라벨을 영상 제목으로 바꾼다

라벨이 타임스탬프와 11자리 영상 ID 라, 어떤 이력인지 열어 보기
전에는 알 수 없었다.

제목을 앞에 둔다. 목록은 최신순으로 고정되어 있어 시각은 뒤에
있어도 읽는 데 지장이 없다. 제목을 못 얻은 실행은 영상 ID 로
대신한다.

Assisted-by: <자신의 모델 ID>
EOF
)"
```

---

### Task 9: 인용 숨기기 체크박스

**Files:**
- Modify: `src/notebooklm_st/pages/history.py`
- Test: `tests/pages/test_history.py`

**Interfaces:**
- Consumes: Task 1 의 `answer_text.for_display`
- Produces: 이력 화면에 `key="history_hide_citations"` 체크박스가 생긴다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_history.py` 의 `make_result` 에 본문을 바꿀 수 있는 인자를 더한다.

```python
def make_result(
    url: str = "https://youtu.be/dQw4w9WgXcQ",
    title: str | None = None,
    answer: str = "세 가지다.",
) -> models.RunResult:
    """테스트용 실행 결과를 만든다."""
    return models.RunResult(
        url=url,
        video_id="dQw4w9WgXcQ",
        title=title,
        items=(
            models.AnswerItem(
                question_title="핵심 주장",
                question_text="핵심 주장은?",
                answer=answer,
                citations=(
                    models.Citation(number=1, text="근거 구절", score=0.9),
                ),
                error=None,
            ),
        ),
    )
```

같은 파일 맨 아래에 더한다.

```python
ANSWER_WITH_CITATIONS = "세 가지다 [1].\n\n---\n💡 **다음으로?**\n제안 문단"


def test_citations_are_shown_by_default(app_db) -> None:
    """기본 상태에서는 인용을 그대로 보여 준다."""
    run_history.save_run(
        app_db, make_result(answer=ANSWER_WITH_CITATIONS)
    )

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    labels = [element.label for element in app.expander]
    assert any(label.startswith("인용") for label in labels)
    rendered = " ".join(element.value for element in app.markdown)
    assert "[1]" in rendered


def test_hiding_citations_strips_markers_and_the_tail(app_db) -> None:
    """체크박스를 켜면 인용 번호와 후속 제안이 사라진다."""
    run_history.save_run(
        app_db, make_result(answer=ANSWER_WITH_CITATIONS)
    )

    app = v1.AppTest.from_function(script)
    app.run()
    app.checkbox[0].check().run()

    assert not app.exception
    rendered = " ".join(element.value for element in app.markdown)
    assert "[1]" not in rendered
    assert "제안 문단" not in rendered
    assert "근거 구절" not in rendered


def test_hiding_citations_keeps_the_question_expander(app_db) -> None:
    """숨겨도 질문 원문은 남는다. 인용이 아니라 기록이다."""
    run_history.save_run(
        app_db, make_result(answer=ANSWER_WITH_CITATIONS)
    )

    app = v1.AppTest.from_function(script)
    app.run()
    app.checkbox[0].check().run()

    labels = [element.label for element in app.expander]
    assert "질문 원문" in labels
    assert not any(label.startswith("인용") for label in labels)
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `uv run pytest tests/pages/test_history.py -q`
Expected: FAIL — `IndexError: list index out of range` (체크박스가 없다)

- [ ] **Step 3: 체크박스를 단다**

`src/notebooklm_st/pages/history.py` 의 import 에 `answer_text` 를 더한다.

```python
from notebooklm_st.core import answer_text, models
```

같은 파일의 `_TITLE_MAX_CHARS` 아래에 상수를 더한다.

```python
_HIDE_CITATIONS_KEY = "history_hide_citations"
```

같은 파일 `render()` 의 `st.caption(selected.url)` 아래를 바꾼다.

```python
    st.caption(selected.url)
    hidden = st.checkbox(
        "인용 숨기기",
        key=_HIDE_CITATIONS_KEY,
        help="인용 번호와 인용 본문, 맨 아래 후속 제안을 감춥니다."
        " 숨기는 동안에는 답변을 수정할 수 없습니다.",
    )
    items = run_history.load_run_items(connection, selected.id)
    if hidden:
        answer_view.render_items(
            [answer_text.for_display(item) for item in items]
        )
        return
    answer_view.render_items(items)
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `uv run pytest tests/pages/test_history.py -q`
Expected: PASS

- [ ] **Step 5: 커밋한다**

```bash
git add src/notebooklm_st/pages/history.py tests/pages/test_history.py
git commit -m "$(cat <<'EOF'
✨ feat(history): 인용 숨기기 체크박스 추가

결과물만 확인하고 싶어도 본문에 박힌 [1] 같은 인용 번호와 맨
아래 후속 제안을 손으로 지워야 했다.

원문은 건드리지 않는다. 표시용 사본을 만들어 넘길 뿐이다. 인용
상자는 사본의 인용을 비우는 것만으로 사라진다 — 답변 카드가 빈
인용을 그리지 않기 때문이다.

질문 원문은 숨기지 않는다. 인용이 아니라 무엇을 물었는가의
기록이다.

Assisted-by: <자신의 모델 ID>
EOF
)"
```

---

### Task 10: 이력 항목 삭제

**Files:**
- Modify: `src/notebooklm_st/pages/history.py`
- Test: `tests/pages/test_history.py`

**Interfaces:**
- Consumes: Task 4 의 `run_history.delete_run`
- Produces: 이력 화면에 2단계 삭제 UI 가 생긴다. 확인 상태는 세션 키 `history_delete_armed` 에 실행 ID 로 적힌다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_history.py` 맨 아래에 더한다.

```python
def test_delete_needs_two_steps(app_db) -> None:
    """첫 번째 누름은 확인만 요청하고 지우지 않는다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[0].click().run()

    assert not app.exception
    assert len(run_history.list_runs(app_db)) == 1


def test_delete_removes_the_run_after_confirming(app_db) -> None:
    """확인 버튼까지 누르면 실제로 지운다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[0].click().run()
    app.button(key="history_delete_confirm").click().run()

    assert not app.exception
    assert run_history.list_runs(app_db) == []
    assert len(app.info) == 1


def test_delete_can_be_cancelled(app_db) -> None:
    """취소하면 아무것도 지우지 않는다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[0].click().run()
    app.button(key="history_delete_cancel").click().run()

    assert not app.exception
    assert len(run_history.list_runs(app_db)) == 1


def test_delete_keeps_the_other_runs(app_db) -> None:
    """고른 실행만 지우고 나머지는 남긴다."""
    run_history.save_run(app_db, make_result("https://youtu.be/aaaaaaaaaaa"))
    run_history.save_run(app_db, make_result("https://youtu.be/bbbbbbbbbbb"))

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[0].click().run()
    app.button(key="history_delete_confirm").click().run()

    assert not app.exception
    remaining = run_history.list_runs(app_db)
    assert [run.url for run in remaining] == [
        "https://youtu.be/aaaaaaaaaaa"
    ]
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `uv run pytest tests/pages/test_history.py -k delete -q`
Expected: FAIL — `IndexError: list index out of range` (버튼이 없다)

- [ ] **Step 3: 삭제 UI 를 단다**

`src/notebooklm_st/pages/history.py` 의 import 에 `sqlite3` 를 더한다(파일 맨 위, 표준 라이브러리 자리).

```python
import sqlite3
```

같은 파일의 `_HIDE_CITATIONS_KEY` 아래에 상수를 더한다.

```python
# 위젯 키가 아니라 우리가 소유한 세션 키다. 위젯이 만들어진 뒤 그
# 위젯의 키를 건드리면 Streamlit 이 예외를 던지므로, 삭제 후 상태를
# 되돌리려면 우리 것이어야 한다.
_DELETE_ARMED_KEY = "history_delete_armed"
```

같은 파일 `render()` 의 `hidden = st.checkbox(...)` **바로 위**에 더한다.

```python
    _render_delete(connection, selected)
```

같은 파일 맨 아래에 함수 세 개를 더한다.

```python
def _render_delete(
    connection: sqlite3.Connection, selected: models.RunSummary
) -> None:
    """접은 영역 안에 2단계 삭제를 그린다.

    첫 누름은 지우려는 실행 ID 를 세션에 적어 둘 뿐이다. 다시 그려진
    화면에서 확인을 눌러야 실제로 지운다. 선택한 실행이 바뀌면 적어
    둔 ID 와 어긋나므로 확인이 저절로 풀린다.
    """
    with st.expander("이 이력 삭제"):
        if st.session_state.get(_DELETE_ARMED_KEY) != selected.id:
            if st.button("이 이력 삭제", key="history_delete"):
                st.session_state[_DELETE_ARMED_KEY] = selected.id
                st.rerun()
            return
        st.warning("딸린 답변도 함께 사라집니다. 되돌릴 수 없습니다.")
        left, right = st.columns(2)
        if left.button("정말 삭제", key="history_delete_confirm"):
            _delete(connection, selected.id)
        if right.button("취소", key="history_delete_cancel"):
            _disarm()
            st.rerun()


def _delete(connection: sqlite3.Connection, run_id: int) -> None:
    """실행을 지우고 확인 상태를 풀고 화면을 다시 그린다.

    선택 위젯의 키는 건드리지 않는다. 고른 항목이 목록에서 사라져도
    Streamlit 은 예외 없이 남은 첫 항목으로 되돌린다.
    """
    run_history.delete_run(connection, run_id)
    _disarm()
    st.rerun()


def _disarm() -> None:
    """적어 둔 삭제 대상을 지운다."""
    st.session_state.pop(_DELETE_ARMED_KEY, None)
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `uv run pytest tests/pages/test_history.py -q`
Expected: PASS

- [ ] **Step 5: 커밋한다**

```bash
git add src/notebooklm_st/pages/history.py tests/pages/test_history.py
git commit -m "$(cat <<'EOF'
✨ feat(history): 이력 항목 삭제 추가

같은 영상을 두 번 돌리면 중복 항목이 영원히 남았다. 웹에서
지울 방법이 없어 DB 파일을 직접 열어야 했다.

되돌릴 수 없는 조작이므로 2단계를 거친다. 확인 상태는 위젯 키가
아니라 우리 세션 키에 실행 ID 로 적는다. 위젯이 만들어진 뒤 그
위젯의 키를 건드리면 Streamlit 이 예외를 던지기 때문이고, 덕분에
선택이 바뀌면 확인이 저절로 풀린다.

Assisted-by: <자신의 모델 ID>
EOF
)"
```

---

### Task 11: 이력 답변 수정 배선

**Files:**
- Modify: `src/notebooklm_st/pages/history.py`
- Test: `tests/pages/test_history.py`

**Interfaces:**
- Consumes: Task 4 의 `run_history.update_answer`, Task 6 의 `answer_view.render_items(..., on_save=...)`
- Produces: 인용 숨김이 꺼져 있을 때 답변마다 편집 상자와 저장 버튼이 생긴다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_history.py` 맨 아래에 더한다.

```python
def test_answer_is_editable_when_citations_are_shown(app_db) -> None:
    """기본 상태에서는 답변을 고칠 수 있다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.text_area) == 1


def test_editing_saves_the_new_body(app_db) -> None:
    """고친 본문이 이력에 저장된다."""
    run_id = run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_area[0].set_value("고친 답변").run()
    app.button(key="answer_save_1").click().run()

    assert not app.exception
    items = run_history.load_run_items(app_db, run_id)
    assert items[0].answer == "고친 답변"


def test_editing_rejects_an_empty_body(app_db) -> None:
    """빈 본문으로 저장하면 오류를 보여 주고 원본을 지킨다."""
    run_id = run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_area[0].set_value("   ").run()
    app.button(key="answer_save_1").click().run()

    assert not app.exception
    assert len(app.error) == 1
    items = run_history.load_run_items(app_db, run_id)
    assert items[0].answer == "세 가지다."


def test_hiding_citations_locks_editing(app_db) -> None:
    """인용을 숨기는 동안에는 편집 상자를 그리지 않는다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.checkbox[0].check().run()

    assert not app.exception
    assert len(app.text_area) == 0
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `uv run pytest tests/pages/test_history.py -k edit -q`
Expected: FAIL — `assert 0 == 1` (편집 상자가 없다)

- [ ] **Step 3: 저장 훅을 배선한다**

`src/notebooklm_st/pages/history.py` 의 `render()` 마지막 줄을 바꾼다.

```python
    answer_view.render_items(
        items,
        on_save=lambda answer_id, text: _save(
            connection, answer_id, text
        ),
    )
```

같은 파일 맨 아래에 함수를 더한다.

```python
def _save(
    connection: sqlite3.Connection, answer_id: int, answer: str
) -> None:
    """고친 답변을 저장하고 화면을 다시 그린다.

    저장 경로에는 필터를 거치지 않은 원문만 흐른다. 인용을 숨긴
    동안에는 편집 상자 자체를 그리지 않으므로, 걸러진 본문이 여기까지
    올 길이 없다.
    """
    try:
        run_history.update_answer(connection, answer_id, answer)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `uv run pytest tests/pages/test_history.py -q`
Expected: PASS

- [ ] **Step 5: 4종 검사를 순서대로 돌린다**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

Expected: 넷 다 통과. 실패가 남으면 완료로 보고하지 말고 실패 내용을 그대로 보고한다.

- [ ] **Step 6: 커밋한다**

```bash
git add src/notebooklm_st/pages/history.py tests/pages/test_history.py
git commit -m "$(cat <<'EOF'
✨ feat(history): 이력 답변 수정 배선

답변에 잘못된 내용이 들어가도 웹에서는 고칠 수 없었다.

인용을 숨긴 동안에는 편집 상자를 그리지 않는다. 걸러진 본문을
원본에 덮어쓰는 사고를 원천 차단한다. 결과물을 뽑아 쓰는 일과
잘못된 내용을 고치는 일은 동시에 할 일이 아니다.

Assisted-by: <자신의 모델 ID>
EOF
)"
```

---

### Task 12: 실제 영상으로 제목 확인

스펙 11장의 유일한 미검증 가정을 닫는다. **코드를 바꾸지 않는 검증 태스크**다.

**Files:** 없음(확인만)

- [ ] **Step 1: 앱을 띄운다**

```bash
uv run streamlit run src/notebooklm_st/app.py
```

- [ ] **Step 2: 질의를 한 번 돌린다**

질의 화면에서 유튜브 영상 URL 하나로 질문 한 개를 실행한다. 끝날 때까지 기다린다.

- [ ] **Step 3: 이력 목록의 라벨을 본다**

이력 화면을 연다. 방금 실행의 라벨을 확인한다.

- 라벨이 **영상 제목**으로 시작하면 가정이 확인된 것이다. 스펙 11장을 지우고 커밋한다.
- 라벨이 **영상 ID** 이거나 제목이 아닌 다른 값(파일명, URL 등)이면 **멈추고 보고한다.** 폴백이 동작하므로 화면은 깨지지 않지만, 제목을 다른 곳에서 얻어야 한다.

- [ ] **Step 4: 확인됐으면 스펙을 갱신하고 커밋한다**

`docs/superpowers/specs/2026-08-31-history-management-design.md` 의 11장을 다음으로 바꾼다.

```markdown
## 11. 검증 완료

유튜브 소스의 `Source.title` 이 영상 제목이라는 것을 실제 질의로
확인했다(2026-08-31).
```

```bash
git add docs/superpowers/specs/2026-08-31-history-management-design.md
git commit -m "$(cat <<'EOF'
📝 docs(specs): 영상 제목 가정을 검증 완료로 바꾼다

실제 질의를 한 번 돌려 소스가 알려 주는 제목이 영상 제목임을
확인했다.

Assisted-by: <자신의 모델 ID>
EOF
)"
```

---

## 완료 조건

- 이력 목록 라벨이 영상 제목으로 시작한다(없으면 영상 ID).
- 답변 본문을 고쳐 저장할 수 있고, 빈 본문은 거부된다.
- 이력 항목을 2단계 확인을 거쳐 지울 수 있고, 딸린 답변도 함께 사라진다.
- 인용 숨기기를 켜면 인용 번호·인용 상자·후속 제안이 사라지고 편집이 잠긴다.
- 실행 현황 화면의 동작이 바뀌지 않는다.
- 낡은 스키마의 DB 로 앱을 띄우면 트레이스백 대신 안내가 나온다.
- 4종 검사가 모두 통과한다.
