# 질문 제목 도입과 답변 표시 개선 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 질문에 제목을 도입해 목록과 답변 화면을 제목 중심으로 바꾸고, 답변 화면에서 질문 원문을 접어 마크다운이 서식으로 렌더되지 않게 한다.

**Architecture:** 기존 계층 구조를 그대로 둔다. `Question` 에 `title`, `AnswerItem` 에 `question_title` 필드를 더하고 그 값이 저장소 → 파이프라인 → 화면으로 흐르게 한다. 답변 렌더는 `components/answer_view.py` 한 곳에 모여 있어 실행 현황과 이력이 같은 코드를 쓴다. 두 화면의 표시 변경도 그 파일 하나로 끝난다.

**Tech Stack:** Python 3.13, Streamlit 1.62, notebooklm-py 0.8.1, SQLite, uv / ruff / mypy / pytest

**Spec:** 없음. 별도 설계 문서를 만들지 않았다. 아키텍처가 바뀌지 않고 미결정 사항이 사용자 확인으로 모두 닫혔기 때문이다. 요구사항 원문과 확정된 결정은 아래 "요구사항과 확정된 결정" 절에 그대로 옮겼다. **이 계획서가 곧 요구사항의 단일 출처다.**

## Global Constraints

프로젝트 규칙 `.claude/rules/streamlit-implement.md` 에서 온 제약이다. 모든 태스크에 암묵적으로 적용된다.

- Python **3.13**. `from __future__ import annotations` 를 넣지 않는다.
- 줄 길이 **최대 80자**. 들여쓰기는 스페이스 4칸.
- 모든 명령에 `uv run` 을 붙인다. **`uv` 는 PATH 에 없다.** 전체 경로를 쓴다:
  ```bash
  UV="/c/Users/susot/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe"
  ```
- 모든 모듈·클래스·함수에 Google 형식 `"""` 독스트링. `src/` 와 `tests/` 양쪽 모두. 예외를 던지면 `Raises:` 절을 추가한다. 독스트링과 주석은 72자 안에서 줄바꿈한다.
- 모든 함수에 인자·반환 타입. **단 `tests/services/test_nlm.py` 와 `test_nlm_cleanup.py` 의 테스트 함수에는 `-> None` 을 붙이지 않는다**(mypy `var-annotated` 때문에 그 두 파일만 예외). 새로 만드는 테스트에는 붙인다.
- `AppTest.from_function` 에 넘기는 `script()` 에는 한 줄 독스트링을 붙이되 타입 힌트는 붙이지 않는다.
- **`core/` 와 `services/` 에서 `import streamlit` 을 금지한다.**
- 개별 클래스·함수 import 금지. `typing`, `collections.abc` 심볼은 허용. `import streamlit as st` 는 허용.
- `except:` 와 맨 `except Exception:` 금지.
- 위젯에는 `key=` 를 명시한다. `st.session_state` 키는 모듈 상수로 정의한다.
- 한 파일이 300줄, 한 함수가 40줄을 넘으면 분리를 검토한다.
- 커밋 메시지: `<emoji> <type>(<scope>): <한국어 명령형 제목 50자 이내>` + 빈 줄 + 본문 + 빈 줄 + 트레일러. 트레일러는 아래를 **그대로 복사**한다.
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  ```
  > `.claude/rules/commit-strategy.md` 는 트레일러를 `Claude Opus 4.8` 로 적고 있으나 실제 커밋 기록과 직전 계획서는 모두 `Claude Opus 5` 를 쓴다. 기록과 일관되게 **`Claude Opus 5`** 를 쓴다.
- `push` 금지, `--force`/`--no-verify` 금지. 브랜치는 `master` 하나뿐이다.
- 작업 완료 전 4종 검증이 전부 통과해야 한다.
  ```bash
  "$UV" run ruff format .
  "$UV" run ruff check --fix .
  "$UV" run mypy src tests
  "$UV" run pytest
  ```
- 착수 시점 기준선: **131개 테스트 전부 통과.** 태스크가 끝날 때마다 이 수 이상이어야 한다.

---

## 요구사항과 확정된 결정

사용자가 실제 사용 후 정리한 5개 항목이다. 요약 없이 옮긴다.

| # | 중요도 | 현재 문제점 | 수정사항 |
|---|---|---|---|
| 1 | 중 | 실행 현황에서 어디까지가 질문이고 답변인지 구분이 안 된다. 질문에 마크다운이 있으면 출력 시 문법이 적용된다. | 출력 내용 간 구분자를 넣는다. 질문은 바로 확인할 필요가 없으므로 접어 넣는다. |
| 2 | 하 | 질문 관리의 새 질문 텍스트 박스가 4줄뿐이라 입력한 질문을 보기 불편하다. | 12줄로 늘린다. |
| 3 | 상 | 질문 목록 항목에 본문 전체가 나와 관리가 불편하다. 내용은 펼치면 확인된다. | 등록 시 제목도 받고, 접힌 항목에는 제목만 출력한다. |
| 4 | 하 | 질문 수정 시 텍스트 박스가 작다. | 12줄로 늘린다. |
| 5 | 중 | 이력 화면도 1번과 같은 문제. | 1번과 같은 수정. |

착수 전 확인해 확정한 결정이다. **구현 중에 이 결정을 다시 해석하지 않는다.**

- **A1. 제목은 필수다.** 비면 `ValueError` 로 거부한다. **제목 중복은 검사하지 않는다.**
- **A2. 기존 DB 를 새로 시작한다.** 마이그레이션 코드를 만들지 않는다. 개발용 `questions.db` 를 지우고 새 스키마로 다시 만든다.
- **A3. 답변 화면의 머리글에 제목을 쓴다.** 따라서 `answers` 테이블과 `AnswerItem` 에도 제목이 있어야 한다.
- **A4. 질의 화면의 질문 선택 목록도 제목만 보여준다.**
- **A5. 답변 본문은 지금처럼 마크다운으로 렌더한다.** 원문 출력은 질문에만 적용한다.

**범위 밖 — 이번에 하지 않는다.**

- 제목 중복 검사, 질문 정렬·검색·태그
- `runs`/`answers` 이력 마이그레이션 (A2 로 DB 를 새로 시작하므로 불필요)
- `pages/maintenance.py`, `core/youtube.py`, `core/errors.py`, `services/runner.py`, `services/runs.py`, `session.py`, `app.py` — 한 줄도 건드리지 않는다.

---

## 실측으로 확인한 사실

착수 전 설치된 Streamlit 1.62.0 소스와 `AppTest` 실행으로 확인했다. **추측이 아니다.** 특히 6~8행이 테스트 설계를 결정한다.

| 사실 | 근거 | 영향 |
|---|---|---|
| `st.subheader` 는 마크다운을 렌더한다 | `elements/heading.py` — body 가 GitHub-flavored Markdown | 질문 원문을 머리글에 넣으면 안 된다 |
| `st.expander` 의 **라벨도** 마크다운을 렌더한다 | `elements/layouts.py:1136-1148` — Bold·Italics·Code·Link 지원, 블록 요소는 unwrap | **접기만 해서는 문법 적용 문제가 안 풀린다** |
| `st.text` 는 마크다운을 파싱하지 않는다 | `elements/text.py:41` — *"Write text without Markdown or HTML parsing"* | 질문 원문은 `st.text` 로 출력한다 |
| `st.text_area(height=)` 는 **픽셀 단위**다 | `elements/widgets/text_widgets.py:861-867, 1111-1116` | 줄 수를 픽셀로 환산해야 한다 |
| 기본 높이(라벨 있음) = **122px = 3줄**, 최소 = **98px = 2줄** | 같은 파일 | 줄당 24px → **12줄 = 122 + 9 × 24 = 338px** |
| `AppTest` 는 `height` 를 **노출하지 않는다** | `TextAreaProto` 필드 목록에 height 없음. 실행해 확인 | **높이는 자동 테스트로 검증할 수 없다.** 수동 확인한다 |
| `AppTest` 에 `app.container` 가 **없다** | `dir(AppTest)` 실행해 확인 | **테두리 컨테이너는 관측 불가.** 구분자로 쓰지 않는다 |
| `app.divider` 는 **있다** | 같은 확인 | **구분자는 `st.divider()` 로 넣는다.** 테스트 가능하고 `dashboard.py:49` 가 이미 쓴다 |
| `app.text` 는 **있다** | `st.text("**굵게**")` → `app.text[0].value == "**굵게**"` | 원문 그대로 나왔는지 검증할 수 있다 |
| expander 안의 요소도 `app.*` 로 잡힌다 | 중첩 스크립트를 실행해 확인 | 접은 안쪽 내용도 테스트할 수 있다 |

**expander 를 중첩하지 않는다.** Streamlit 문서가 명시적으로 금지한다(`layouts.py:1130`). 이 계획의 `질문 원문` 과 `인용 N건` 은 형제 관계이지 중첩이 아니다.

---

## 파일 구조

| 파일 | 책임 | 태스크 |
|---|---|---|
| `src/notebooklm_st/pages/question_admin.py` | 입력란 높이 확대 | 1 |
| `src/notebooklm_st/core/models.py` | `Question.title` 추가 | 2 |
| `src/notebooklm_st/services/store.py` | `questions` 스키마·질문 API | 2 |
| `src/notebooklm_st/pages/question_admin.py` | 제목 입력·제목 라벨 | 2 |
| `src/notebooklm_st/pages/ask.py` | 선택 목록을 제목으로 | 2 |
| `scripts/smoke_check.py` | `Question` 생성부 보정 | 2 |
| `src/notebooklm_st/core/models.py` | `AnswerItem.question_title` 추가 | 3 |
| `src/notebooklm_st/services/store.py` | `answers` 스키마·이력 API | 3 |
| `src/notebooklm_st/services/nlm.py` | 답변에 제목 채우기 | 3 |
| `src/notebooklm_st/components/answer_view.py` | 구분자·질문 접기·원문 출력 | 4 |

**태스크 순서의 근거.** Task 1 은 어디에도 걸리지 않아 먼저 넣고 즉시 값을 낸다. Task 2 와 Task 3 은 서로 독립이지만 Task 3 의 `nlm.py` 가 `question.title` 을 읽어야 하므로 2 → 3 순서가 강제된다. Task 4 는 `AnswerItem.question_title` 이 있어야 하므로 3 뒤에 온다.

---

## 사전 작업 — 개발용 DB 삭제

Task 2 와 Task 3 이 스키마를 바꾼다. `store.connect()` 는 `CREATE TABLE IF NOT EXISTS` 만 실행하므로(`store.py:72`) **기존 파일이 남아 있으면 새 컬럼이 생기지 않고 `no such column` 으로 죽는다.** A2 에 따라 파일을 지운다.

```bash
rm -f questions.db questions.db-journal
```

- `questions.db` 는 `.gitignore` 의 `*.db` 에 걸려 **추적되지 않는다.** 커밋에 영향이 없다.
- 질문 1건과 실행 이력 1건이 사라진다. 사용자가 이미 동의했다(A2).
- 테스트는 `tmp_path` 를 쓰므로(`tests/conftest.py:15`) 이 파일과 무관하다.

Task 2 와 Task 3 각각의 스키마 변경 직후에 한 번씩 실행한다. 두 태스크 사이에 앱을 띄웠다면 옛 `answers` 가 다시 만들어져 있을 수 있다.

---

### Task 1: 질문 입력란을 12줄로 늘린다

요구사항 **2번·4번**. 다른 어떤 변경과도 얽히지 않는 표시 전용 수정이다.

**Files:**
- Modify: `src/notebooklm_st/pages/question_admin.py:11`, `:24`, `:47-51`

**Interfaces:**
- Consumes: 없음
- Produces: 모듈 상수 `_TEXT_AREA_HEIGHT = 338`. Task 2 가 텍스트 영역을 재구성할 때 같은 상수를 그대로 쓴다.

> **이 태스크에는 자동 테스트를 쓰지 않는다.** `AppTest` 가 `height` 를 노출하지 않는 것을 실행해 확인했다(위 표 6행). 값을 검증하는 테스트를 억지로 만들면 상수를 상수와 비교하는 무의미한 테스트가 된다. 기존 131개 테스트가 계속 통과하는 것으로 회귀를 막고, 높이 자체는 브라우저에서 눈으로 확인한다.

- [ ] **Step 1: 모듈 상수를 추가한다**

`src/notebooklm_st/pages/question_admin.py` 의 `_NEW_KEY` 아래에 넣는다.

```python
_NEW_KEY = "admin_new"
# st.text_area 의 height 는 픽셀이다. 라벨 있는 기본값 122px 가 3줄이고
# 줄당 24px 이므로 12줄은 122 + 9 * 24 = 338px 이다.
_TEXT_AREA_HEIGHT = 338
```

- [ ] **Step 2: 새 질문 입력란에 적용한다**

`render()` 안의 텍스트 영역(24행)을 바꾼다.

```python
    text = st.text_area("새 질문", key=_NEW_KEY, height=_TEXT_AREA_HEIGHT)
```

- [ ] **Step 3: 수정 입력란에 적용한다**

`_render_row()` 안의 텍스트 영역(47-51행)을 바꾼다.

```python
        edited = st.text_area(
            "내용",
            value=question.text,
            key=f"admin_text_{question.id}",
            height=_TEXT_AREA_HEIGHT,
        )
```

- [ ] **Step 4: 4종 검증을 돌린다**

```bash
UV="/c/Users/susot/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe"
"$UV" run ruff format .
"$UV" run ruff check --fix .
"$UV" run mypy src tests
"$UV" run pytest
```

Expected: `131 passed`. 기존 테스트는 `height` 를 보지 않으므로 하나도 깨지지 않는다.

- [ ] **Step 5: 눈으로 확인한다**

```bash
"$UV" run streamlit run src/notebooklm_st/app.py
```

`질문 관리` 화면에서 새 질문 입력란이 12줄 높이인지, 질문 항목을 펼쳤을 때 수정 입력란도 같은 높이인지 본다. 확인 후 서버를 끈다.

- [ ] **Step 6: 커밋**

커밋 메시지는 파일로 만들어 넘긴다. 중첩 heredoc 은 셸에서 깨지기 쉽다.

```bash
git add src/notebooklm_st/pages/question_admin.py
printf '%s\n' \
  '💄 style(pages): 질문 입력란을 12줄로 확대' \
  '' \
  '4줄짜리 입력란은 입력한 질문을 한눈에 보기 어려웠다. st.text_area 의' \
  'height 는 픽셀 단위이고 라벨 있는 기본값 122px 가 3줄이므로, 12줄에' \
  '해당하는 338px 을 모듈 상수로 두고 새 질문과 수정 양쪽에 적용한다.' \
  '' \
  'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>' \
  > .git/COMMIT_EDITMSG_TASK1
git commit -F .git/COMMIT_EDITMSG_TASK1
rm -f .git/COMMIT_EDITMSG_TASK1
```

---

### Task 2: 질문에 제목을 도입한다

요구사항 **3번** 전체와 **A4**. 값 객체부터 화면까지 한 번에 간다. 중간에서 끊으면 `add_question()` 시그니처가 맞지 않아 앱이 뜨지 않기 때문이다.

**Files:**
- Modify: `src/notebooklm_st/core/models.py:8-15`
- Modify: `src/notebooklm_st/services/store.py:14-38`, `:77-151`, `:254-274`
- Modify: `src/notebooklm_st/pages/question_admin.py` (전체)
- Modify: `src/notebooklm_st/pages/ask.py:38-43`
- Modify: `scripts/smoke_check.py:15-40`, `:46-51`
- Test: `tests/services/test_store_questions.py`, `tests/pages/test_question_admin.py`, `tests/pages/test_ask.py`, `tests/services/test_nlm.py:126-136`, `tests/services/test_runner_start.py:26-36`, `tests/pages/test_dashboard.py:123-131`

**Interfaces:**
- Consumes: Task 1 의 `_TEXT_AREA_HEIGHT = 338`
- Produces:
  - `models.Question(id: int, title: str, text: str, created_at: str, updated_at: str)` — `title` 이 `id` 다음, `text` 앞이다
  - `store.add_question(connection: sqlite3.Connection, title: str, text: str) -> models.Question`
  - `store.update_question(connection: sqlite3.Connection, question_id: int, title: str, text: str) -> None`
  - `store._require_text(text: str, subject: str) -> str`
  - Task 3 의 `nlm.py` 가 `question.title` 을 읽는다

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/services/test_store_questions.py` 에 5개를 추가한다. 기존 테스트는 아직 건드리지 않는다.

```python
def test_add_question_stores_title(connection) -> None:
    """제목과 본문을 함께 저장한다."""
    saved = store.add_question(connection, "핵심 주장", "3가지로 정리해줘")
    assert saved.title == "핵심 주장"
    assert saved.text == "3가지로 정리해줘"


def test_add_question_strips_title_whitespace(connection) -> None:
    """제목의 앞뒤 공백을 지운다."""
    saved = store.add_question(connection, "  핵심 주장  ", "본문")
    assert saved.title == "핵심 주장"


def test_add_question_rejects_blank_title(connection) -> None:
    """제목이 비면 거부한다."""
    with pytest.raises(ValueError):
        store.add_question(connection, "   ", "본문")


def test_update_question_changes_title_and_text(connection) -> None:
    """제목과 본문을 함께 바꾼다."""
    saved = store.add_question(connection, "옛 제목", "옛 본문")
    store.update_question(connection, saved.id, "새 제목", "새 본문")
    changed = store.list_questions(connection)[0]
    assert changed.title == "새 제목"
    assert changed.text == "새 본문"


def test_update_question_rejects_blank_title(connection) -> None:
    """제목이 비면 거부한다."""
    saved = store.add_question(connection, "제목", "본문")
    with pytest.raises(ValueError):
        store.update_question(connection, saved.id, "  ", "본문")
```

- [ ] **Step 2: 실패를 확인한다**

```bash
"$UV" run pytest tests/services/test_store_questions.py -k title -v
```

Expected: 5개 모두 FAIL. `TypeError: add_question() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: `core/models.py` 에 `title` 을 추가한다**

```python
@dataclasses.dataclass(frozen=True, slots=True)
class Question:
    """저장된 질문 템플릿."""

    id: int
    title: str
    text: str
    created_at: str
    updated_at: str
```

- [ ] **Step 4: `services/store.py` 의 스키마와 질문 API 를 바꾼다**

`_SCHEMA` 의 `questions` 테이블만 바꾼다. `runs` 와 `answers` 는 Task 3 에서 건드린다.

```python
CREATE TABLE IF NOT EXISTS questions (
    id         INTEGER PRIMARY KEY,
    title      TEXT NOT NULL,
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

`_require_text` 를 항목 이름을 받게 일반화한다. 제목과 본문의 오류 문구를 나누기 위해서다.

```python
def _require_text(text: str, subject: str) -> str:
    """공백을 지운 값을 돌려주고, 비면 예외를 던진다.

    Args:
        text: 검사할 문자열.
        subject: 오류 문구에 넣을 항목 이름.

    Returns:
        앞뒤 공백을 지운 문자열.

    Raises:
        ValueError: 공백을 지우면 빈 문자열이 되는 경우.
    """
    stripped = text.strip()
    if not stripped:
        raise ValueError(f"{subject}이 비어 있습니다.")
    return stripped
```

질문 API 세 곳을 바꾼다.

```python
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

    제목 중복은 검사하지 않는다. 같은 제목의 질문을 여러 개 두는 것을
    허용한다.

    Args:
        connection: 열린 커넥션.
        title: 목록에 보여 줄 제목. 앞뒤 공백은 지운다.
        text: 질문 본문. 앞뒤 공백은 지운다.

    Returns:
        저장된 질문.

    Raises:
        ValueError: 제목이나 본문이 공백만으로 이루어진 경우.
    """
    stripped_title = _require_text(title, "제목")
    stripped_text = _require_text(text, "질문")
    now = _now()
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
        ValueError: 제목이나 본문이 비었거나 그 ID 의 질문이 없는 경우.
    """
    stripped_title = _require_text(title, "제목")
    stripped_text = _require_text(text, "질문")
    cursor = connection.execute(
        "UPDATE questions SET title = ?, text = ?, updated_at = ?"
        " WHERE id = ?",
        (stripped_title, stripped_text, _now(), question_id),
    )
    connection.commit()
    if cursor.rowcount == 0:
        raise ValueError(f"질문 {question_id} 을 찾을 수 없습니다.")
```

`_to_question` 도 바꾼다.

```python
def _to_question(row: sqlite3.Row) -> models.Question:
    """DB 행을 ``Question`` 으로 바꾼다."""
    return models.Question(
        id=int(row["id"]),
        title=row["title"],
        text=row["text"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
```

- [ ] **Step 5: 새 테스트가 통과하는지 확인한다**

```bash
"$UV" run pytest tests/services/test_store_questions.py -k title -v
```

Expected: 5 passed.

- [ ] **Step 6: `pages/question_admin.py` 를 다시 쓴다**

파일 전체를 아래로 바꾼다. Task 1 의 `_TEXT_AREA_HEIGHT` 를 그대로 이어 쓴다.

```python
"""질문 관리 화면."""

import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import models
from notebooklm_st.services import store

_NEW_TITLE_KEY = "admin_new_title"
_NEW_TEXT_KEY = "admin_new_text"
# st.text_area 의 height 는 픽셀이다. 라벨 있는 기본값 122px 가 3줄이고
# 줄당 24px 이므로 12줄은 122 + 9 * 24 = 338px 이다.
_TEXT_AREA_HEIGHT = 338


def render() -> None:
    """질문 등록 입력과 편집 가능한 목록을 그린다.

    등록 후에도 입력란의 글이 남는다. 위젯이 만들어진 뒤에
    ``st.session_state`` 의 위젯 키를 건드리면 Streamlit 이 예외를
    던지므로, 비우려 애쓰는 대신 그대로 둔다.
    """
    st.title("질문 관리")
    connection = session.get_connection()

    title = st.text_input("새 질문 제목", key=_NEW_TITLE_KEY)
    text = st.text_area(
        "새 질문 내용", key=_NEW_TEXT_KEY, height=_TEXT_AREA_HEIGHT
    )
    if st.button("등록", key="admin_add"):
        _add(connection, title, text)

    for question in store.list_questions(connection):
        _render_row(connection, question)


def _add(connection: sqlite3.Connection, title: str, text: str) -> None:
    """새 질문을 저장하고 화면을 다시 그린다."""
    try:
        store.add_question(connection, title, text)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()


def _render_row(
    connection: sqlite3.Connection, question: models.Question
) -> None:
    """질문 하나를 수정·삭제 버튼과 함께 그린다.

    접힌 상태에서는 제목만 보인다. 본문 전체를 라벨에 넣으면 목록이
    길어져 관리하기 어렵다.
    """
    with st.expander(question.title):
        edited_title = st.text_input(
            "제목",
            value=question.title,
            key=f"admin_title_{question.id}",
        )
        edited_text = st.text_area(
            "내용",
            value=question.text,
            key=f"admin_text_{question.id}",
            height=_TEXT_AREA_HEIGHT,
        )
        left, right = st.columns(2)
        if left.button("수정", key=f"admin_update_{question.id}"):
            _update(connection, question.id, edited_title, edited_text)
        if right.button("삭제", key=f"admin_delete_{question.id}"):
            store.delete_question(connection, question.id)
            st.rerun()


def _update(
    connection: sqlite3.Connection,
    question_id: int,
    title: str,
    text: str,
) -> None:
    """질문의 제목과 본문을 고치고 화면을 다시 그린다."""
    try:
        store.update_question(connection, question_id, title, text)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()
```

- [ ] **Step 7: `pages/ask.py` 의 선택 목록을 제목으로 바꾼다 (A4)**

38-43행의 `format_func` 만 바꾼다. 다른 줄은 그대로 둔다.

```python
    selected = st.multiselect(
        "질문 선택",
        options=questions,
        format_func=lambda question: question.title,
        key=_SELECTED_KEY,
    )
```

- [ ] **Step 8: `scripts/smoke_check.py` 를 보정한다**

15-18행의 상수를 제목과 본문의 쌍으로 바꾼다.

```python
_QUESTIONS = (
    ("핵심 주장", "이 영상의 핵심 주장을 3가지로 정리해 주세요."),
    ("결론", "발표자의 결론은 무엇인가요?"),
)
```

32-40행의 생성부를 바꾼다.

```python
    questions = [
        models.Question(
            id=index,
            title=title,
            text=text,
            created_at="",
            updated_at="",
        )
        for index, (title, text) in enumerate(_QUESTIONS, start=1)
    ]
```

48행 위에 제목 출력을 더한다.

```python
        print("제목:", item.question_title)
        print("질문:", item.question_text)
```

> `question_title` 은 Task 3 에서 `AnswerItem` 에 생긴다. **이 줄은 Task 3 을 마친 뒤에 넣는다.** Task 2 에서는 `print("질문:", item.question_text)` 를 그대로 둔다.

- [ ] **Step 9: 기존 테스트의 호출부를 갱신한다**

`store.add_question(conn, text)` 을 `store.add_question(conn, title, text)` 로 고친다. 제목은 본문에서 자연스럽게 줄인 말을 쓴다.

`tests/services/test_store_questions.py` — 기존 11곳 (`add_question` 8 · `update_question` 3):

| 행 | 변경 후 |
|---|---|
| 23 | `store.add_question(connection, "핵심 주장", "핵심 주장 3가지 정리")` |
| 32 | `store.add_question(connection, "결론", "  발표자의 결론은?  ")` |
| 39 | `store.add_question(connection, "제목", "   ")` |
| 44 | `store.add_question(connection, "첫째 제목", "첫째")` |
| 45 | `store.add_question(connection, "둘째 제목", "둘째")` |
| 52 | `store.add_question(connection, "옛 제목", "옛 질문")` |
| 53 | `store.update_question(connection, saved.id, "새 제목", "새 질문")` |
| 60 | `store.update_question(connection, 999, "제목", "아무거나")` |
| 65 | `store.add_question(connection, "옛 제목", "옛 질문")` |
| 67 | `store.update_question(connection, saved.id, "제목", "  ")` |
| 72 | `store.add_question(connection, "지울 제목", "지울 질문")` |

`test_add_question_returns_saved_row`(21-27행) 에 제목 검증을 더한다.

```python
    assert saved.title == "핵심 주장"
```

`tests/pages/test_ask.py` — 6곳(23, 24, 39, 55, 68, 99행)에 제목을 넣는다.

```python
    store.add_question(app_db, "핵심 주장", "핵심 주장 3가지 정리")
    store.add_question(app_db, "결론", "발표자의 결론은?")
```

`test_ask_shows_question_multiselect`(21-34행) 에 제목만 나오는지 검증을 더한다.

```python
    assert app.multiselect[0].options == ["핵심 주장", "결론"]
```

`tests/services/test_nlm.py:126-136` 과 `tests/services/test_runner_start.py:26-36` 의 `make_questions` 헬퍼에 제목을 넣는다. 본문을 그대로 제목으로 써도 이 테스트들의 관심사가 아니다.

```python
def make_questions(*texts: str) -> list[models.Question]:
    """테스트용 질문 목록을 만든다."""
    return [
        models.Question(
            id=index,
            title=f"제목{index}",
            text=text,
            created_at="2026-08-28T10:00:00",
            updated_at="2026-08-28T10:00:00",
        )
        for index, text in enumerate(texts, start=1)
    ]
```

`tests/pages/test_dashboard.py:123-131` 의 `Question` 생성부에 `title="핵심 주장"` 을 넣는다.

- [ ] **Step 10: `tests/pages/test_question_admin.py` 를 갱신한다**

제목 입력이 생겨 위젯 구성이 바뀐다. 새 배치는 이렇다.

- `app.text_input[0]` = 새 질문 제목, 이후 질문마다 제목
- `app.text_area[0]` = 새 질문 내용, 이후 질문마다 내용
- `app.button[0]` = 등록, 이후 질문마다 수정·삭제

```python
"""질문 관리 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st.services import store


def script():
    """AppTest 진입점 — 질문 관리 화면을 렌더한다."""
    from notebooklm_st.pages import question_admin

    question_admin.render()


def test_empty_list_renders(app_db) -> None:
    """질문이 없어도 새 질문 입력란만 그린다."""
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.text_input) == 1
    assert len(app.text_area) == 1


def test_existing_questions_are_listed(app_db) -> None:
    """접힌 항목의 라벨이 본문이 아니라 제목이다."""
    store.add_question(app_db, "핵심 주장", "핵심 주장 3가지 정리")
    store.add_question(app_db, "결론", "발표자의 결론은?")
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    labels = [element.label for element in app.expander]
    assert labels == ["핵심 주장", "결론"]


def test_adding_a_question_saves_title_and_text(app_db) -> None:
    """등록 버튼을 누르면 제목과 본문이 함께 저장된다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value("새 제목").run()
    app.text_area[0].set_value("새 질문").run()
    app.button[0].click().run()
    assert not app.exception
    saved = store.list_questions(app_db)
    assert [(q.title, q.text) for q in saved] == [("새 제목", "새 질문")]


def test_blank_title_is_rejected(app_db) -> None:
    """제목이 공백뿐이면 오류로 표시되고 저장되지 않는다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value("   ").run()
    app.text_area[0].set_value("본문은 있다").run()
    app.button[0].click().run()
    assert len(app.error) == 1
    assert store.list_questions(app_db) == []


def test_blank_question_is_rejected(app_db) -> None:
    """본문이 공백뿐이면 오류로 표시되고 저장되지 않는다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value("제목은 있다").run()
    app.text_area[0].set_value("   ").run()
    app.button[0].click().run()
    assert len(app.error) == 1
    assert store.list_questions(app_db) == []


def test_duplicate_question_title_does_not_crash(app_db) -> None:
    """같은 제목의 질문이 둘이어도 관리 화면이 죽지 않는다."""
    store.add_question(app_db, "같은 제목", "첫째 본문")
    store.add_question(app_db, "같은 제목", "둘째 본문")
    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.expander) == 2
```

- [ ] **Step 11: 개발용 DB 를 지운다**

```bash
rm -f questions.db questions.db-journal
```

- [ ] **Step 12: 4종 검증을 돌린다**

```bash
"$UV" run ruff format .
"$UV" run ruff check --fix .
"$UV" run mypy src tests
"$UV" run pytest
```

Expected: 137 passed (기준선 131 + 신규 6). 실패가 남으면 완료로 보고하지 않는다.

- [ ] **Step 13: 눈으로 확인한다**

```bash
"$UV" run streamlit run src/notebooklm_st/app.py
```

`질문 관리` 에서 제목과 내용을 넣어 등록하고, 목록이 제목만 보이는지 본다. `질의` 화면의 선택 목록도 제목만 나오는지 본다. 확인 후 서버를 끈다.

- [ ] **Step 14: 커밋**

```bash
git add src/notebooklm_st/core/models.py \
        src/notebooklm_st/services/store.py \
        src/notebooklm_st/pages/question_admin.py \
        src/notebooklm_st/pages/ask.py \
        scripts/smoke_check.py \
        tests/
printf '%s\n' \
  '✨ feat(questions): 질문에 제목 추가' \
  '' \
  '목록 항목에 본문 전체가 나와 질문을 관리하기 어려웠다. 제목을 필수' \
  '필드로 받아 접힌 항목과 질의 화면 선택 목록에는 제목만 보이게 하고,' \
  '본문은 펼쳐야 나오게 한다. 제목 중복은 검사하지 않는다.' \
  '' \
  'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>' \
  > .git/COMMIT_EDITMSG_TASK2
git commit -F .git/COMMIT_EDITMSG_TASK2
rm -f .git/COMMIT_EDITMSG_TASK2
```

---

### Task 3: 답변에 질문 제목을 함께 저장한다

**A3** 의 전제 작업이다. 데이터만 흐르게 하고 화면은 Task 4 에서 바꾼다. 이 태스크가 끝나도 화면은 지금과 똑같이 보인다.

**Files:**
- Modify: `src/notebooklm_st/core/models.py:27-43`
- Modify: `src/notebooklm_st/services/store.py:29-37`, `:153-189`, `:226-251`
- Modify: `src/notebooklm_st/services/nlm.py:245-264`
- Modify: `scripts/smoke_check.py:48`
- Test: `tests/core/test_models.py`, `tests/services/test_store_history.py`, `tests/services/test_runs.py`, `tests/services/test_runner_start.py`, `tests/pages/test_dashboard.py`, `tests/pages/test_history.py`, `tests/test_components.py`

**Interfaces:**
- Consumes: Task 2 의 `models.Question.title`
- Produces:
  - `models.AnswerItem(question_title: str, question_text: str, answer: str | None, citations: tuple[Citation, ...], error: str | None)` — `question_title` 이 **맨 앞**이다
  - Task 4 의 `answer_view` 가 `item.question_title` 을 머리글로 쓴다

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/services/test_store_history.py` 의 `make_result` 헬퍼(20-43행)에 제목을 넣고, 왕복 검증을 추가한다.

```python
def make_result(
    url: str = "https://youtu.be/dQw4w9WgXcQ",
) -> models.RunResult:
    """테스트용 실행 결과를 만든다."""
    return models.RunResult(
        url=url,
        video_id="dQw4w9WgXcQ",
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


def test_load_run_items_round_trips_question_title(connection) -> None:
    """답변에 저장한 질문 제목이 그대로 돌아온다."""
    run_id = store.save_run(connection, make_result())
    items = store.load_run_items(connection, run_id)
    titles = [item.question_title for item in items]
    assert titles == ["핵심 주장", "결론"]
```

- [ ] **Step 2: 실패를 확인한다**

```bash
"$UV" run pytest tests/services/test_store_history.py -v
```

Expected: FAIL. `TypeError: AnswerItem.__init__() got an unexpected keyword argument 'question_title'`

- [ ] **Step 3: `core/models.py` 에 `question_title` 을 추가한다**

```python
@dataclasses.dataclass(frozen=True, slots=True)
class AnswerItem:
    """질문 하나에 대한 실행 결과.

    ``answer`` 와 ``error`` 는 배타적이다. 성공한 항목은 ``error`` 가
    ``None`` 이고, 실패한 항목은 ``answer`` 가 ``None`` 이다.

    ``question_title`` 과 ``question_text`` 를 둘 다 복사해 둔다.
    화면은 제목을 머리글로 쓰고 원문은 접어서 보여준다.
    """

    question_title: str
    question_text: str
    answer: str | None
    citations: tuple[Citation, ...]
    error: str | None

    @property
    def succeeded(self) -> bool:
        """실패 메시지가 없으면 참."""
        return self.error is None
```

- [ ] **Step 4: `services/store.py` 의 `answers` 스키마와 이력 API 를 바꾼다**

`_SCHEMA` 의 `answers` 테이블:

```python
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
```

`save_run` 의 `executemany` 부분(173-187행):

```python
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
```

`save_run` 의 독스트링에 한 줄 더한다. 왜 문자열로 복사하는지가 제목에도 적용되기 때문이다.

```python
    """실행 결과를 이력으로 저장한다.

    질문 제목과 본문을 ``questions`` 테이블 외래키가 아니라 문자열로
    복사해 둔다. 나중에 질문을 고치거나 지워도 과거 이력이 그대로
    남는다.
    ...
```

`load_run_items`(238-251행):

```python
    rows = connection.execute(
        "SELECT question_title, question_text, answer, citations, error"
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
        )
        for row in rows
    ]
```

- [ ] **Step 5: `services/nlm.py` 의 `_ask_one` 을 바꾼다**

245-264행의 `AnswerItem` 생성 두 곳에 제목을 넣는다.

```python
    try:
        result = await client.chat.ask(notebook_id, question.text)
    except exceptions.ChatError as error:
        return (
            models.AnswerItem(
                question_title=question.title,
                question_text=question.text,
                answer=None,
                citations=(),
                error=errors.to_message(error).text,
            ),
            None,
        )
    citations = _to_citations(result.references)
    return (
        models.AnswerItem(
            question_title=question.title,
            question_text=question.text,
            answer=result.answer,
            citations=citations,
            error=None,
        ),
        result.conversation_id,
    )
```

- [ ] **Step 6: 나머지 `AnswerItem` 생성부를 갱신한다**

`question_title` 은 필수 인자다. 아래 6개 파일 10곳이 모두 깨진다. 각 위치에 `question_title=` 을 첫 인자로 넣는다.

| 파일 | 행 | 넣을 제목 |
|---|---|---|
| `tests/core/test_models.py` | 12, 23 | `"핵심 주장"` |
| `tests/services/test_runs.py` | 14 | `"핵심 주장"` |
| `tests/services/test_runner_start.py` | 60 | `questions[0].title` |
| `tests/pages/test_dashboard.py` | 62, 113 | `"핵심 주장"` |
| `tests/pages/test_history.py` | 24 | `"핵심 주장"` |
| `tests/test_components.py` | 15, 23, 109 | `"핵심 주장"`, `"결론"`, `"핵심 주장"` |

예를 들어 `tests/services/test_runner_start.py:59-64` 는 이렇게 된다.

```python
                models.AnswerItem(
                    question_title=questions[0].title,
                    question_text=questions[0].text,
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                ),
```

- [ ] **Step 7: `scripts/smoke_check.py` 에 제목 출력을 더한다**

48행 위에 한 줄 넣는다. Task 2 Step 8 에서 미뤄 둔 줄이다.

```python
        print("제목:", item.question_title)
        print("질문:", item.question_text)
```

- [ ] **Step 8: 개발용 DB 를 지운다**

```bash
rm -f questions.db questions.db-journal
```

- [ ] **Step 9: 4종 검증을 돌린다**

```bash
"$UV" run ruff format .
"$UV" run ruff check --fix .
"$UV" run mypy src tests
"$UV" run pytest
```

Expected: 138 passed (Task 2 의 137 + 신규 1).

- [ ] **Step 10: 커밋**

```bash
git add src/notebooklm_st/core/models.py \
        src/notebooklm_st/services/store.py \
        src/notebooklm_st/services/nlm.py \
        scripts/smoke_check.py \
        tests/
printf '%s\n' \
  '✨ feat(history): 답변에 질문 제목 저장' \
  '' \
  '답변 화면이 제목을 머리글로 쓰려면 이력에도 제목이 남아야 한다.' \
  'AnswerItem 과 answers 테이블에 question_title 을 더하고 본문과' \
  '함께 문자열로 복사해, 원래 질문을 고쳐도 이력이 변하지 않게 한다.' \
  '' \
  'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>' \
  > .git/COMMIT_EDITMSG_TASK3
git commit -F .git/COMMIT_EDITMSG_TASK3
rm -f .git/COMMIT_EDITMSG_TASK3
```

---

### Task 4: 답변 카드에 구분자를 넣고 질문을 접는다

요구사항 **1번과 5번**. 두 화면이 `components/answer_view.py` 를 함께 쓰므로(`run_progress.py:49`, `history.py:31`) **이 파일 하나만 고치면 둘 다 해결된다.**

**Files:**
- Modify: `src/notebooklm_st/components/answer_view.py` (전체)
- Test: `tests/test_components.py`, `tests/pages/test_history.py`, `tests/pages/test_dashboard.py`

**Interfaces:**
- Consumes: Task 3 의 `models.AnswerItem.question_title`
- Produces: 없음. 화면 최말단이다

**표시 설계와 그 근거.**

| 결정 | 근거 |
|---|---|
| 항목 사이에 `st.divider()` | 요구사항이 말한 "구분자". `AppTest` 로 검증되고 `dashboard.py:49` 가 이미 쓰는 방식이다. 테두리 컨테이너는 `app.container` 가 없어 검증할 수 없다 |
| 머리글은 `st.subheader(item.question_title)` | A3. 제목은 짧게 쓰는 필드라 마크다운 렌더가 실질 문제를 일으키지 않는다 |
| 질문 원문은 `st.expander("질문 원문")` 안에 접는다 | 요구사항 1번. 라벨을 고정 문자열로 두어야 라벨의 마크다운 렌더에 걸리지 않는다 |
| 원문은 `st.text` 로 출력한다 | `st.text` 만 마크다운을 파싱하지 않는다. **접기만으로는 문법 적용이 안 고쳐진다** |
| 답변 본문은 `st.markdown` 유지 | A5 |
| 마지막 항목 뒤에는 구분자를 넣지 않는다 | 실행 현황에서 `dashboard.py:49` 의 실행 간 구분자와 겹쳐 두 줄이 되는 것을 막는다 |

- [ ] **Step 1: 실패 테스트를 쓴다**

`tests/test_components.py` 에 2개를 추가한다.

```python
def test_answer_view_folds_the_question_without_markdown() -> None:
    """질문 원문을 접어서 마크다운 없이 그대로 보여준다."""

    def script():
        """AppTest 진입점 — 마크다운이 든 질문을 그린다."""
        from notebooklm_st.components import answer_view
        from notebooklm_st.core import models

        answer_view.render_items(
            [
                models.AnswerItem(
                    question_title="핵심 주장",
                    question_text="**굵게** 와 # 헤딩이 든 질문",
                    answer="세 가지다.",
                    citations=(),
                    error=None,
                )
            ]
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert [element.value for element in app.subheader] == ["핵심 주장"]
    assert "질문 원문" in [element.label for element in app.expander]
    assert [element.value for element in app.text] == [
        "**굵게** 와 # 헤딩이 든 질문"
    ]
    rendered = " ".join(element.value for element in app.markdown)
    assert "**굵게**" not in rendered


def test_answer_view_separates_items_with_a_divider() -> None:
    """항목이 여러 개면 사이에 구분자를 넣는다."""

    def script():
        """AppTest 진입점 — 답변 두 개를 그린다."""
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
                ),
                models.AnswerItem(
                    question_title="결론",
                    question_text="결론은?",
                    answer="하나다.",
                    citations=(),
                    error=None,
                ),
            ]
        )

    app = v1.AppTest.from_function(script).run()
    assert not app.exception
    assert len(app.divider) == 1
    labels = [element.label for element in app.expander]
    assert labels.count("질문 원문") == 2
```

- [ ] **Step 2: 실패를 확인한다**

```bash
"$UV" run pytest tests/test_components.py -k "folds or divider" -v
```

Expected: 2개 모두 FAIL. 첫째는 `assert ['핵심 주장은?'] == ['핵심 주장']` 류의 머리글 불일치, 둘째는 `assert 0 == 1` 로 구분자 없음.

- [ ] **Step 3: `components/answer_view.py` 를 다시 쓴다**

파일 전체를 아래로 바꾼다.

```python
"""답변 카드 렌더."""

from collections.abc import Sequence

import streamlit as st

from notebooklm_st.core import models


def render_items(items: Sequence[models.AnswerItem]) -> None:
    """답변 목록을 위에서 아래로 카드처럼 그린다.

    항목 사이에만 구분자를 넣는다. 마지막 뒤에도 넣으면 실행 현황
    화면에서 실행 간 구분자와 겹쳐 줄이 두 개가 된다.

    Args:
        items: 그릴 답변 목록. 비어 있으면 아무것도 그리지 않는다.
    """
    for index, item in enumerate(items):
        if index > 0:
            st.divider()
        _render_item(item)


def _render_item(item: models.AnswerItem) -> None:
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
    st.markdown(item.answer or "")
    if not item.citations:
        return
    with st.expander(f"인용 {len(item.citations)}건"):
        for citation in item.citations:
            st.markdown(f"**[{citation.number}]** {citation.text}")
```

- [ ] **Step 4: 새 테스트가 통과하는지 확인한다**

```bash
"$UV" run pytest tests/test_components.py -k "folds or divider" -v
```

Expected: 2 passed.

- [ ] **Step 5: 머리글을 보는 기존 테스트를 갱신한다**

`item.question_text` 가 아니라 `item.question_title` 이 머리글이 되었다. 아래 3곳이 깨진다.

`tests/test_components.py:34-35` — `test_answer_view_renders_success_and_failure`:

```python
    headers = [element.value for element in app.subheader]
    assert headers == ["핵심 주장", "결론"]
```

`tests/test_components.py:129` — `test_render_run_shows_answers_when_done`:

```python
    assert [element.value for element in app.subheader] == ["핵심 주장"]
```

`tests/pages/test_history.py:56-57` — `test_selected_run_shows_its_answers`:

```python
    headers = [element.value for element in app.subheader]
    assert headers == ["핵심 주장"]
```

`tests/pages/test_dashboard.py` 는 **두 곳**이 머리글을 본다. 74행(`test_dashboard_shows_answers_of_a_finished_run`)과 144행(`test_real_background_run_reaches_the_dashboard`)이다. 둘 다 같은 한 줄이다.

```python
    assert [element.value for element in app.subheader] == ["핵심 주장은?"]
```

둘 다 아래로 바꾼다.

```python
    assert [element.value for element in app.subheader] == ["핵심 주장"]
```

- [ ] **Step 6: 4종 검증을 돌린다**

```bash
"$UV" run ruff format .
"$UV" run ruff check --fix .
"$UV" run mypy src tests
"$UV" run pytest
```

Expected: 140 passed (Task 3 의 138 + 신규 2).

- [ ] **Step 7: 눈으로 확인한다**

```bash
"$UV" run streamlit run src/notebooklm_st/app.py
```

`실행 현황` 과 `이력` 두 화면에서 확인한다.

1. 답변 항목 사이에 가로줄이 보이는가
2. 제목이 머리글로 나오는가
3. `질문 원문` 을 펼치면 마크다운이 적용되지 않은 원문이 나오는가
4. 답변 본문은 여전히 서식이 살아 있는가

`**굵게**` 같은 문법이 든 질문을 하나 등록해 실제로 돌려 본다. 확인 후 서버를 끈다.

- [ ] **Step 8: 커밋**

```bash
git add src/notebooklm_st/components/answer_view.py tests/
printf '%s\n' \
  '💄 style(components): 답변 카드에 구분자와 질문 접기 추가' \
  '' \
  '질문과 답변의 경계가 보이지 않고 질문 속 마크다운이 서식으로' \
  '렌더되어 읽기 어려웠다. 항목 사이에 구분자를 넣고 제목을 머리글로' \
  '올린 뒤, 원문은 마크다운을 파싱하지 않는 st.text 로 접어 둔다.' \
  '실행 현황과 이력이 같은 컴포넌트를 쓰므로 두 화면이 함께 바뀐다.' \
  '' \
  'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>' \
  > .git/COMMIT_EDITMSG_TASK4
git commit -F .git/COMMIT_EDITMSG_TASK4
rm -f .git/COMMIT_EDITMSG_TASK4
```

---

## 요구사항 대응표

| 요구사항 | 태스크 | 검증 방법 |
|---|---|---|
| 1. 실행 현황에 구분자를 넣는다 | Task 4 | `test_answer_view_separates_items_with_a_divider` |
| 1. 실행 현황에서 질문을 접는다 | Task 4 | `test_answer_view_folds_the_question_without_markdown` |
| 1. 질문의 마크다운이 적용되지 않게 한다 | Task 4 | 같은 테스트의 `app.text` 원문 일치 + `"**굵게**" not in rendered` |
| 2. 새 질문 입력란 12줄 | Task 1 | 수동 확인 (`AppTest` 가 height 를 노출하지 않음) |
| 3. 등록 시 제목을 받는다 | Task 2 | `test_adding_a_question_saves_title_and_text` |
| 3. 제목은 필수다 (A1) | Task 2 | `test_add_question_rejects_blank_title`, `test_blank_title_is_rejected` |
| 3. 접힌 항목에 제목만 출력 | Task 2 | `test_existing_questions_are_listed` |
| 4. 수정 입력란 12줄 | Task 1 | 수동 확인 |
| 5. 이력도 1번과 같이 | Task 4 | `test_selected_run_shows_its_answers` + 1번과 같은 컴포넌트를 쓴다는 사실 |
| A2. DB 를 새로 시작 | Task 2·3 | `rm -f questions.db` 후 앱 기동 확인 |
| A3. 답변 머리글에 제목 | Task 3·4 | `test_load_run_items_round_trips_question_title` |
| A4. 질의 선택 목록에 제목만 | Task 2 | `test_ask_shows_question_multiselect` |
| A5. 답변은 마크다운 유지 | Task 4 | `test_answer_view_renders_success_and_failure` 의 `"세 가지다."` 검증 |

## 자체 검토 결과

**1. 요구사항 누락.** 5개 항목과 5개 결정(A1~A5)이 모두 위 대응표에 태스크를 갖는다. 누락 없음.

**2. 플레이스홀더.** "TBD", "적절히 처리", "위와 비슷하게" 같은 표현을 쓰지 않았다. 모든 코드 단계에 실제 코드를 넣었다.

**3. 타입 일관성.** 태스크를 가로지르는 이름을 맞췄다.

- `Question.title` — Task 2 정의, Task 3 의 `nlm.py` 가 소비
- `AnswerItem.question_title` — Task 3 정의, Task 4 의 `answer_view` 가 소비
- `_TEXT_AREA_HEIGHT = 338` — Task 1 정의, Task 2 가 파일을 다시 쓰면서 그대로 유지
- `_require_text(text, subject)` — Task 2 에서 인자가 하나 늘어난다. Task 3 은 이 함수를 쓰지 않는다
- `add_question(connection, title, text)` — 제목이 본문보다 **앞**이다. 모든 호출부가 이 순서를 따른다

**4. 주의할 함정.**

- Task 2 Step 8 의 `print("제목:", ...)` 은 **Task 3 을 마친 뒤에 넣는다.** `question_title` 이 그때 생기기 때문이다. 순서를 지키지 않으면 `AttributeError` 가 난다.
- Task 2 는 `questions` 만, Task 3 은 `answers` 만 건드린다. 한 태스크에서 `_SCHEMA` 를 통째로 바꾸지 않는다.
- 스키마를 바꾼 뒤 `rm -f questions.db` 를 빠뜨리면 `no such column` 으로 앱이 죽는다. 테스트는 `tmp_path` 를 쓰므로 통과하는데 앱만 죽어 원인을 찾기 어렵다.
- `question_admin.py` 의 `_NEW_KEY` 가 Task 2 에서 `_NEW_TITLE_KEY` 와 `_NEW_TEXT_KEY` 로 갈라진다. 옛 키를 남기지 않는다.
