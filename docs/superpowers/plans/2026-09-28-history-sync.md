# 이력 동기화 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이력 화면의 "Outline 과 동기화" 버튼 한 번으로 로컬 `runs`
의 저장된 행과 Outline 컬렉션 문서 목록을 미리 본 뒤 맞춘다.

**Architecture:** Outline 목록 호출(`services/outline.list_documents`)과
DB 쓰기(`services/run_history`)는 각자 자기 I/O 만 알고, 두 목록을
비교해 계획을 세우는 것은 순수 함수(`services/history_sync.plan`)가
한다. 문서 본문에서 영상 URL 을 되읽는 것도 순수 함수
(`core/outline_import.find_source_url`)다. 화면 조각
(`pages/_history_sync.py`)은 계획을 세션에 담아 미리보기를 그리고,
적용은 삭제·삽입을 커밋 하나로 묶는 `history_sync.apply` 가 한다.
스키마는 바뀌지 않는다.

**Tech Stack:** Python 3.13 · Streamlit 1.64 · SQLite(sqlite3) · httpx ·
pytest · `streamlit.testing.v1.AppTest` · ruff · mypy. **새 의존성 없음.**

**Spec:** `docs/superpowers/specs/2026-09-28-history-sync-design.md`

## Global Constraints

- 줄 길이 최대 **80자**. 들여쓰기 스페이스 4칸.
- 모든 모듈·클래스·함수에 **한국어 Google 형식 독스트링**. 독스트링과
  주석은 72자에서 줄바꿈.
- **모듈 단위 import 만** 쓴다. `from x import name` 금지(예외:
  `typing`·`collections.abc`).
- `core/` 와 `services/` 에서 **`import streamlit` 금지**. `core/` 는
  `services/` 를 import 하지 않는다.
- 모든 함수에 타입 힌트. 반환 없으면 `-> None`. `list[str]`·`str |
  None` 형식.
- 값 묶음은 `@dataclasses.dataclass(frozen=True, slots=True)`.
- 테스트는 `tests/` 에 `src/notebooklm_st` 구조를 미러링.
- 외부 네트워크·DB 는 **반드시 가짜로** 대체. 실제 호출을 하는 테스트를
  추가하지 않는다.
- 새 의존성을 추가하지 않는다. 스키마(`services/store.py`)를 바꾸지
  않는다.
- 위젯에는 `key=` 를 명시한다. 세션 키는 모듈 상수로 둔다.
- **검증 4단을 순서대로 통과해야 완료다.**
  ```
  uv run ruff format .
  uv run ruff check --fix .
  uv run mypy src tests
  uv run pytest
  ```
  `uv` 가 PATH 에 없으면 전체 경로로 부른다(이 기기에서는
  `/c/Users/susot/.local/bin/uv.exe`).
- 커밋은 gitmoji + Conventional Commits, 제목은 한국어 명령형 50자
  이내, 마지막 줄에 `Assisted-by: <모델 ID>`. `git push` 하지 않는다.
  브랜치는 `develop`.

## Review Focus

명세가 말하지 않지만 실제 사용에서 만날 입력들이다. 각 줄의 테스트는
그 코드를 소유한 Task 에 들어 있다.

1. **컬렉션이 비어 있는데 저장된 행이 있다** — 저장된 행 전부가 삭제
   대상으로 미리보기에 올라야 하고, 적용 전에는 아무것도 지워지면 안
   된다. → Task 2 `test_plan_deletes_everything_when_outline_is_empty`.
2. **`createdAt` 이 없거나 날짜로 읽히지 않는 문서** — 목록 전체가
   "응답을 이해하지 못했습니다" 로 실패해야 한다. 그 문서만 조용히
   빠지면 다음 동기화가 그 행을 지운다. → Task 6
   `test_list_documents_rejects_an_unreadable_created_at`.
3. **영상 URL 줄은 있는데 YouTube 가 아닌 URL** (사람이 손으로 쓴
   문서) — "영상 URL 인식 불가" 로 건너뛰고 미리보기에 사유가 보여야
   한다. → Task 2 `test_plan_skips_a_document_whose_url_is_not_youtube`.
4. **적용 직전에 다른 탭이 같은 문서를 먼저 저장했다** — 같은
   `outline_id` 행이 이미 있으면 삽입을 건너뛰고 결과 개수에 세지 않아야
   한다. → Task 4 `test_apply_skips_a_document_that_is_already_linked`.
5. **Outline 설정 없이 DB 를 막 지운 직후** (저장된 실행 0건) — 동기화
   영역이 그려지고 설정 안내가 나와야 한다. 지금 코드는 실행 0건이면
   화면을 일찍 끝낸다. → Task 7
   `test_sync_area_is_drawn_without_any_run`.

## 파일 구조

| 파일 | 책임 |
| --- | --- |
| `core/markdown_export.py`(수정) | 영상 URL 라벨 상수를 공개 |
| `core/outline_import.py`(신규) | 문서 본문 → 영상 URL. I/O 를 모른다 |
| `core/models.py`(수정) | `ListedDocument`·`SyncCreate`·`SyncSkip`·`SyncPlan` |
| `services/history_sync.py`(신규) | `plan`(순수 비교)·`apply`(한 커밋) |
| `services/run_history.py`(수정) | `list_exported`·`insert_exported`·`delete_runs` |
| `services/outline_messages.py`(신규) | 상태 코드 → 안내 문구. `outline.py` 에서 분리 |
| `services/outline.py`(수정) | `list_documents`. 문구 함수는 위로 이동 |
| `pages/_history_sync.py`(신규) | 확인·미리보기·적용·취소 |
| `pages/history.py`(수정) | 동기화 영역 호출, 실행 0건 분기 위치 |
| `README.md`(수정) | 사용 순서와 한계 |

**`services/outline_messages.py` 는 Task 5 의 순수 리팩터다.** 공개
동작이 바뀌지 않으며 `tests/services/test_outline.py` 는 그대로 통과해야
한다. 명세 7.1 이 정한 분리이며, 그 뒤 Task 6 이 목록용 문구를 거기에
더한다.

---

### Task 1: 문서 본문에서 영상 URL 되읽기

**Files:**
- Modify: `src/notebooklm_st/core/markdown_export.py`
- Create: `src/notebooklm_st/core/outline_import.py`
- Test: `tests/core/test_outline_import.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `markdown_export.SOURCE_URL_LABEL: str` (`"영상 URL"`)
  - `outline_import.find_source_url(markdown: str) -> str | None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/core/test_outline_import.py` 를 새로 만든다.

```python
"""Outline 문서 본문에서 영상 URL 을 되읽는 함수 테스트."""

from notebooklm_st.core import outline_import

SUMMARY = (
    "- 제목: 밸류에이션 강의\n"
    "- 채널: 어떤 채널\n"
    "- 업로드 일자: 2026-09-20\n"
    "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
    "\n"
    "---\n"
    "\n"
    "## 핵심 주장\n"
    "\n"
    "세 가지다.\n"
)

DIGEST = (
    "- 종류: 정리본\n"
    "- 만든 날: 2026-09-23\n"
    "- 정리 지시: 공통점을 뽑아라\n"
    "\n"
    "---\n"
    "\n"
    "## 정리\n"
)


def test_finds_the_source_url_in_the_head_block() -> None:
    """메타데이터 리스트의 영상 URL 줄을 찾는다."""
    assert (
        outline_import.find_source_url(SUMMARY)
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )


def test_returns_none_without_a_source_line() -> None:
    """영상 URL 줄이 없으면 이력 문서가 아니다."""
    assert outline_import.find_source_url("## 그냥 글\n\n본문.\n") is None


def test_ignores_a_source_line_after_the_rule() -> None:
    """첫 구분선 뒤의 같은 문구는 본문이지 메타데이터가 아니다."""
    text = "- 제목: 글\n\n---\n\n- 영상 URL: https://youtu.be/dQw4w9WgXcQ\n"

    assert outline_import.find_source_url(text) is None


def test_searches_the_whole_text_without_a_rule() -> None:
    """구분선이 없으면 전체가 머리 블록이다."""
    text = "- 제목: 글\n- 영상 URL: https://youtu.be/dQw4w9WgXcQ\n"

    assert (
        outline_import.find_source_url(text)
        == "https://youtu.be/dQw4w9WgXcQ"
    )


def test_a_digest_body_is_not_a_summary() -> None:
    """정리본 본문은 만든 날·정리 지시만 있고 영상 URL 이 없다."""
    assert outline_import.find_source_url(DIGEST) is None


def test_tolerates_surrounding_whitespace() -> None:
    """앞뒤 공백과 라벨 뒤 공백을 허용한다."""
    text = "  -   영상 URL:   https://youtu.be/dQw4w9WgXcQ   \n"

    assert (
        outline_import.find_source_url(text)
        == "https://youtu.be/dQw4w9WgXcQ"
    )


def test_takes_the_first_source_line() -> None:
    """같은 줄이 둘이면 첫 줄을 쓴다."""
    text = (
        "- 영상 URL: https://youtu.be/aaaaaaaaaaa\n"
        "- 영상 URL: https://youtu.be/bbbbbbbbbbb\n"
    )

    assert (
        outline_import.find_source_url(text)
        == "https://youtu.be/aaaaaaaaaaa"
    )


def test_returns_none_for_an_empty_value() -> None:
    """라벨만 있고 값이 없으면 없는 것이다."""
    assert outline_import.find_source_url("- 영상 URL:\n") is None
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/core/test_outline_import.py -q`
Expected: FAIL — `ImportError: cannot import name 'outline_import'`

- [ ] **Step 3: 라벨 상수를 공개한다**

`src/notebooklm_st/core/markdown_export.py` 에서 `_WHITESPACE` 정의
바로 아래에 더한다.

```python
SOURCE_URL_LABEL = "영상 URL"
"""메타데이터 리스트에서 영상 URL 줄의 라벨.

``outline_import`` 가 같은 줄을 거꾸로 읽는다. 두 곳에 따로 적으면
한쪽만 바뀌어 동기화가 조용히 모든 문서를 건너뛴다.
"""
```

같은 파일 `_metadata_block` 의 마지막 `lines.append` 를 바꾼다. 바꾸기
전 모습은 이렇다.

```python
    lines.append(f"- 영상 URL: {_source_url(summary)}")
```

바꾼 뒤.

```python
    lines.append(f"- {SOURCE_URL_LABEL}: {_source_url(summary)}")
```

- [ ] **Step 4: 되읽기 모듈을 만든다**

`src/notebooklm_st/core/outline_import.py` 를 새로 만든다.

```python
"""Outline 문서 본문에서 이력 복원에 필요한 값을 읽는 순수 함수들.

``markdown_export`` 가 문서 첫머리에 쓴 메타데이터 리스트를 거꾸로
읽는 짝이다. Streamlit 도 httpx 도 모른다.
"""

import re

from notebooklm_st.core import markdown_export

_RULE = re.compile(r"^\s*---\s*$")
"""머리 블록을 끝내는 구분선."""

_SOURCE_LINE = re.compile(
    r"^\s*-\s*"
    + re.escape(markdown_export.SOURCE_URL_LABEL)
    + r":\s*(\S+)\s*$"
)
"""``- 영상 URL: <값>`` 줄. 값은 공백이 없는 한 덩어리다."""


def find_source_url(markdown: str) -> str | None:
    """문서 머리 블록에서 영상 URL 을 찾는다.

    첫 구분선(``---``) 앞까지만 본다. 답변 본문에 같은 문구가 인용될
    수 있어서다. 구분선이 없으면 전체가 머리 블록이다.

    Args:
        markdown: Outline 이 돌려준 문서 본문.

    Returns:
        첫 영상 URL 줄의 값. 줄이 없으면 ``None``.
    """
    for line in markdown.splitlines():
        if _RULE.match(line):
            return None
        match = _SOURCE_LINE.match(line)
        if match:
            return match.group(1)
    return None
```

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/core/test_outline_import.py tests/core/test_markdown_export.py -q`
Expected: PASS — `test_markdown_export.py` 가 `- 영상 URL: ...` 문자열을
이미 단언하고 있어 상수 도입의 회귀 방지가 된다.

- [ ] **Step 6: 검증 4단**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
```

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/core/markdown_export.py \
        src/notebooklm_st/core/outline_import.py \
        tests/core/test_outline_import.py
git commit -m "✨ feat(core): Outline 문서 본문에서 영상 URL 되읽기"
```

---

### Task 2: 값 객체와 비교 계획

**Files:**
- Modify: `src/notebooklm_st/core/models.py`
- Create: `src/notebooklm_st/services/history_sync.py`
- Test: `tests/services/test_history_sync.py`

**Interfaces:**
- Consumes: `outline_import.find_source_url`, `youtube.extract_video_id`
- Produces:
  - `models.ListedDocument(id: str, title: str, url: str,
    created_at: str, markdown: str)`
  - `models.SyncCreate(document: ListedDocument, url: str, video_id: str)`
  - `models.SyncSkip(document: ListedDocument, reason: str)`
  - `models.SyncPlan(deletes: tuple[RunSummary, ...],
    creates: tuple[SyncCreate, ...], skips: tuple[SyncSkip, ...])` 와
    `SyncPlan.is_empty: bool`
  - `history_sync.SKIP_NO_SOURCE_URL: str`, `history_sync.SKIP_BAD_SOURCE_URL: str`
  - `history_sync.plan(exported: Sequence[models.RunSummary],
    documents: Sequence[models.ListedDocument]) -> models.SyncPlan`

- [ ] **Step 1: 값 객체를 더한다**

`src/notebooklm_st/core/models.py` 에서 `VideoMetadata` 클래스 **바로
앞**(즉 `RunSummary` 클래스 뒤)에 네 클래스를 더한다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class ListedDocument:
    """Outline 목록에서 읽어 온 문서 하나.

    정리본이 쓰는 ``services.outline.OutlineDocument`` 와 다르다.
    동기화는 링크와 생성 시각도 필요하다.
    """

    id: str
    title: str
    url: str
    """절대 URL. 상대 경로는 ``services.outline`` 이 붙여서 넘긴다."""
    created_at: str
    """로컬 시각의 초 단위 ISO 문자열. ``store.now()`` 와 같은 형식."""
    markdown: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyncCreate:
    """동기화가 새로 만들 이력 한 건."""

    document: ListedDocument
    url: str
    """본문에서 읽은 영상 URL."""
    video_id: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyncSkip:
    """동기화가 건너뛴 문서 한 건과 그 사유."""

    document: ListedDocument
    reason: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyncPlan:
    """미리보기와 적용이 함께 쓰는 동기화 계획.

    기존 행 중 손대지 않는 것은 담지 않는다. 화면이 보여 줄 것은
    바뀌는 것뿐이다.
    """

    deletes: tuple[RunSummary, ...]
    creates: tuple[SyncCreate, ...]
    skips: tuple[SyncSkip, ...]

    @property
    def is_empty(self) -> bool:
        """지울 것도 만들 것도 없다."""
        return not self.deletes and not self.creates
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/services/test_history_sync.py` 를 새로 만든다.

```python
"""이력 동기화 계획·적용 테스트."""

from notebooklm_st.core import models
from notebooklm_st.services import history_sync

SUMMARY_BODY = (
    "- 제목: 밸류에이션 강의\n"
    "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
    "\n---\n\n## 핵심 주장\n\n세 가지다.\n"
)


def make_run(run_id: int, outline_id: str) -> models.RunSummary:
    """저장된 실행 요약을 만든다."""
    return models.RunSummary(
        id=run_id,
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        title="밸류에이션 강의",
        created_at="2026-09-22T15:00:00",
        answer_count=0,
        outline_id=outline_id,
        outline_url=f"https://wiki.example.com/doc/{outline_id}",
        outline_title="정리한 제목",
        exported_at="2026-09-22T15:00:00",
    )


def make_document(
    doc_id: str,
    markdown: str = SUMMARY_BODY,
    title: str = "정리한 제목",
) -> models.ListedDocument:
    """목록에서 읽어 온 문서를 만든다."""
    return models.ListedDocument(
        id=doc_id,
        title=title,
        url=f"https://wiki.example.com/doc/{doc_id}",
        created_at="2026-09-25T10:00:00",
        markdown=markdown,
    )


def test_plan_deletes_a_run_whose_document_is_gone() -> None:
    """문서 목록에 없는 행은 삭제 대상이다."""
    result = history_sync.plan([make_run(1, "doc-1")], [])

    assert [run.id for run in result.deletes] == [1]
    assert result.creates == ()


def test_plan_creates_a_run_for_an_unlinked_summary() -> None:
    """영상 URL 줄이 있고 가리키는 행이 없는 문서는 생성 대상이다."""
    document = make_document("doc-9")

    result = history_sync.plan([], [document])

    assert len(result.creates) == 1
    create = result.creates[0]
    assert create.document is document
    assert create.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert create.video_id == "dQw4w9WgXcQ"
    assert result.deletes == ()


def test_plan_skips_a_document_without_a_source_url() -> None:
    """정리본·손으로 쓴 문서는 사유와 함께 건너뛴다."""
    document = make_document("doc-2", markdown="- 종류: 정리본\n")

    result = history_sync.plan([], [document])

    assert result.creates == ()
    assert [skip.reason for skip in result.skips] == [
        history_sync.SKIP_NO_SOURCE_URL
    ]
    assert result.skips[0].document is document


def test_plan_skips_a_document_whose_url_is_not_youtube() -> None:
    """영상 URL 줄은 있는데 ID 를 못 뽑으면 인식 불가다."""
    document = make_document(
        "doc-3", markdown="- 영상 URL: https://example.com/watch\n"
    )

    result = history_sync.plan([], [document])

    assert result.creates == ()
    assert [skip.reason for skip in result.skips] == [
        history_sync.SKIP_BAD_SOURCE_URL
    ]


def test_plan_leaves_a_matched_pair_alone() -> None:
    """행과 문서가 모두 있으면 아무것도 하지 않는다."""
    result = history_sync.plan(
        [make_run(1, "doc-1")], [make_document("doc-1")]
    )

    assert result.is_empty
    assert result.skips == ()


def test_plan_deletes_everything_when_outline_is_empty() -> None:
    """컬렉션이 비면 저장된 행 전부가 삭제 대상이다."""
    runs = [make_run(1, "doc-1"), make_run(2, "doc-2")]

    result = history_sync.plan(runs, [])

    assert [run.id for run in result.deletes] == [1, 2]


def test_plan_creates_both_documents_of_the_same_video() -> None:
    """같은 영상의 문서가 둘이면 둘 다 만든다. 합치지 않는다."""
    result = history_sync.plan(
        [], [make_document("doc-a"), make_document("doc-b")]
    )

    assert [create.document.id for create in result.creates] == [
        "doc-a",
        "doc-b",
    ]


def test_plan_leaves_two_runs_pointing_at_one_document_alone() -> None:
    """같은 문서를 가리키는 행이 둘이어도 정리하지 않는다."""
    runs = [make_run(1, "doc-1"), make_run(2, "doc-1")]

    result = history_sync.plan(runs, [make_document("doc-1")])

    assert result.is_empty


def test_plan_keeps_the_input_order() -> None:
    """삭제·생성·건너뜀 모두 입력 순서를 지킨다."""
    runs = [make_run(3, "gone-3"), make_run(1, "gone-1")]
    documents = [
        make_document("new-b"),
        make_document("skip-1", markdown="본문만\n"),
        make_document("new-a"),
    ]

    result = history_sync.plan(runs, documents)

    assert [run.id for run in result.deletes] == [3, 1]
    assert [c.document.id for c in result.creates] == ["new-b", "new-a"]
    assert [s.document.id for s in result.skips] == ["skip-1"]


def test_an_empty_plan_says_so() -> None:
    """건너뛴 것만 있어도 비어 있는 계획이다."""
    plan = models.SyncPlan(
        deletes=(),
        creates=(),
        skips=(
            models.SyncSkip(
                document=make_document("x", markdown="본문\n"),
                reason=history_sync.SKIP_NO_SOURCE_URL,
            ),
        ),
    )

    assert plan.is_empty
```

- [ ] **Step 3: 실패를 확인한다**

Run: `uv run pytest tests/services/test_history_sync.py -q`
Expected: FAIL — `ImportError: cannot import name 'history_sync'`

- [ ] **Step 4: 계획 함수를 만든다**

`src/notebooklm_st/services/history_sync.py` 를 새로 만든다. `apply`
는 Task 4 에서 더한다.

```python
"""저장된 이력과 Outline 문서 목록을 맞춘다.

``plan`` 은 두 목록을 받아 무엇을 지우고 만들지 정하는 순수 함수다.
httpx 도 Streamlit 도 모른다. 목록을 읽는 것은 ``services.outline``,
DB 를 읽는 것은 ``services.run_history`` 가 한다.
"""

from collections.abc import Sequence

from notebooklm_st.core import models, outline_import, youtube

SKIP_NO_SOURCE_URL = "영상 URL 없음"
"""정리본이나 손으로 쓴 문서. 이력 문서가 아니다."""

SKIP_BAD_SOURCE_URL = "영상 URL 인식 불가"
"""영상 URL 줄은 있는데 YouTube 영상 ID 를 뽑지 못했다."""


def plan(
    exported: Sequence[models.RunSummary],
    documents: Sequence[models.ListedDocument],
) -> models.SyncPlan:
    """두 목록을 문서 ID 로 맞춰 동기화 계획을 세운다.

    문서 목록에 없는 행은 지우고, 어떤 행도 가리키지 않는 문서는
    본문에 영상 URL 이 있을 때만 만든다. 같은 문서를 가리키는 행이
    둘이어도, 같은 영상의 문서가 둘이어도 정리하지 않는다 — 동기화는
    중복을 만들지 않을 뿐이다.

    Args:
        exported: ``exported_at`` 이 있는 행들. 미저장 실행은 여기
            들어오지 않으므로 삭제될 수 없다.
        documents: 컬렉션의 문서 전부.

    Returns:
        입력 순서를 지킨 계획.
    """
    known_ids = {run.outline_id for run in exported}
    listed_ids = {document.id for document in documents}
    deletes = tuple(
        run for run in exported if run.outline_id not in listed_ids
    )
    creates: list[models.SyncCreate] = []
    skips: list[models.SyncSkip] = []
    for document in documents:
        if document.id in known_ids:
            continue
        url = outline_import.find_source_url(document.markdown)
        if url is None:
            skips.append(
                models.SyncSkip(document=document, reason=SKIP_NO_SOURCE_URL)
            )
            continue
        video_id = youtube.extract_video_id(url)
        if video_id is None:
            skips.append(
                models.SyncSkip(
                    document=document, reason=SKIP_BAD_SOURCE_URL
                )
            )
            continue
        creates.append(
            models.SyncCreate(document=document, url=url, video_id=video_id)
        )
    return models.SyncPlan(
        deletes=deletes, creates=tuple(creates), skips=tuple(skips)
    )
```

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/services/test_history_sync.py -q`
Expected: PASS

- [ ] **Step 6: 검증 4단**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
```

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/core/models.py \
        src/notebooklm_st/services/history_sync.py \
        tests/services/test_history_sync.py
git commit -m "✨ feat(history-sync): 이력과 문서 목록의 차이 계산"
```

---

### Task 3: 저장소 — 저장된 행 조회·삽입·일괄 삭제

**Files:**
- Modify: `src/notebooklm_st/services/run_history.py`
- Test: `tests/services/test_run_history.py`

**Interfaces:**
- Consumes: `models.SyncCreate`, `models.ListedDocument` (Task 2)
- Produces:
  - `run_history.list_exported(connection) -> list[models.RunSummary]`
  - `run_history.insert_exported(connection, create: models.SyncCreate)
    -> int | None` — **커밋하지 않는다**
  - `run_history.delete_runs(connection, run_ids: Sequence[int]) -> int`
    — **커밋하지 않는다**

세 함수가 커밋하지 않는 이유는 트랜잭션을 `history_sync.apply`(Task 4)가
소유하기 때문이다. 기존 `save_run`·`mark_exported`·`delete_run` 은 각자
커밋하는 채로 둔다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_run_history.py` 끝에 더한다. 파일 상단 import 는
이미 `models`·`run_history`·`store`·`sqlite3`·`pytest` 를 갖고 있다.

```python
def make_create(
    doc_id: str = "doc-9",
    video_id: str = "dQw4w9WgXcQ",
) -> models.SyncCreate:
    """동기화가 만들 이력 한 건."""
    document = models.ListedDocument(
        id=doc_id,
        title="되살린 제목",
        url=f"https://wiki.example.com/doc/{doc_id}",
        created_at="2026-09-25T10:00:00",
        markdown="- 영상 URL: x\n",
    )
    return models.SyncCreate(
        document=document,
        url=f"https://www.youtube.com/watch?v={video_id}",
        video_id=video_id,
    )


def test_list_exported_returns_only_exported_runs(connection) -> None:
    """미저장 실행은 빠진다. 삭제 대상이 될 수 없어야 한다."""
    run_history.save_run(connection, make_result(title="미저장"))
    exported_id = run_history.save_run(connection, make_result(title="저장"))
    export(connection, exported_id)

    result = run_history.list_exported(connection)

    assert [run.id for run in result] == [exported_id]
    assert result[0].outline_id == "doc-1"


def test_list_exported_has_no_limit(connection) -> None:
    """동기화는 전부 봐야 한다. ``list_runs`` 의 50건 상한이 없다."""
    for _ in range(51):
        run_id = run_history.save_run(connection, make_result())
        export(connection, run_id)

    assert len(run_history.list_exported(connection)) == 51


def test_insert_exported_fills_the_link_columns(connection) -> None:
    """여덟 컬럼이 채워진 저장된 행이 생긴다."""
    run_id = run_history.insert_exported(connection, make_create())
    connection.commit()

    assert run_id is not None
    run = run_history.list_exported(connection)[0]
    assert run.id == run_id
    assert run.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert run.video_id == "dQw4w9WgXcQ"
    assert run.title == "되살린 제목"
    assert run.created_at == "2026-09-25T10:00:00"
    assert run.outline_id == "doc-9"
    assert run.outline_url == "https://wiki.example.com/doc/doc-9"
    assert run.outline_title == "되살린 제목"
    assert run.exported_at == "2026-09-25T10:00:00"
    assert run.answer_count == 0


def test_insert_exported_writes_no_answers(connection) -> None:
    """저장된 실행은 본문이 없다."""
    run_id = run_history.insert_exported(connection, make_create())
    connection.commit()

    assert run_id is not None
    assert run_history.load_run_items(connection, run_id) == []
    assert run_history.load_metadata(connection, run_id) is None


def test_insert_exported_skips_an_existing_document(connection) -> None:
    """같은 문서를 가리키는 행이 이미 있으면 넣지 않는다."""
    run_id = run_history.save_run(connection, make_result())
    export(connection, run_id)

    result = run_history.insert_exported(connection, make_create("doc-1"))
    connection.commit()

    assert result is None
    assert len(run_history.list_exported(connection)) == 1


def test_insert_exported_does_not_commit(connection) -> None:
    """트랜잭션은 호출자가 소유한다."""
    run_history.insert_exported(connection, make_create())
    connection.rollback()

    assert run_history.list_exported(connection) == []


def test_delete_runs_removes_several_at_once(connection) -> None:
    """여러 ID 를 한 문장으로 지우고 개수를 돌려준다."""
    first = run_history.save_run(connection, make_result())
    second = run_history.save_run(connection, make_result())
    third = run_history.save_run(connection, make_result())

    deleted = run_history.delete_runs(connection, [first, third])
    connection.commit()

    assert deleted == 2
    assert [run.id for run in run_history.list_runs(connection)] == [second]


def test_delete_runs_ignores_unknown_ids(connection) -> None:
    """없는 ID 는 세지 않는다. 다른 탭이 먼저 지웠을 수 있다."""
    run_id = run_history.save_run(connection, make_result())

    deleted = run_history.delete_runs(connection, [run_id, 999])
    connection.commit()

    assert deleted == 1


def test_delete_runs_with_nothing_is_a_no_op(connection) -> None:
    """빈 목록은 0 이다."""
    run_history.save_run(connection, make_result())

    assert run_history.delete_runs(connection, []) == 0
    assert len(run_history.list_runs(connection)) == 1


def test_delete_runs_does_not_commit(connection) -> None:
    """트랜잭션은 호출자가 소유한다."""
    run_id = run_history.save_run(connection, make_result())

    run_history.delete_runs(connection, [run_id])
    connection.rollback()

    assert len(run_history.list_runs(connection)) == 1


def test_list_video_ids_includes_a_revived_run(connection) -> None:
    """되살린 행의 영상 ID 도 채널 감시가 걸러야 한다."""
    run_history.insert_exported(
        connection, make_create(video_id="aaaaaaaaaaa")
    )
    connection.commit()

    assert run_history.list_video_ids(connection) == {"aaaaaaaaaaa"}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/services/test_run_history.py -q`
Expected: FAIL — `AttributeError: module 'notebooklm_st.services.run_history'
has no attribute 'list_exported'` (와 나머지 둘)

- [ ] **Step 3: 행 → 요약 변환을 한 곳으로 모은다**

`src/notebooklm_st/services/run_history.py` 의 `list_runs` 는 지금
`sqlite3.Row` 를 `RunSummary` 로 바꾸는 리스트 컴프리헨션을 갖고 있다.
그것을 함수로 뽑는다. 파일 상단 import 를 바꾼다. 바꾸기 전.

```python
import sqlite3

from notebooklm_st.core import models
from notebooklm_st.services import store
```

바꾼 뒤.

```python
import sqlite3
from collections.abc import Sequence

from notebooklm_st.core import models
from notebooklm_st.services import store
```

`list_video_ids` 와 `save_run` 사이에 상수와 변환 함수를 더한다.
`list_runs` 보다 위에 있어야 한다.

```python
_SUMMARY_SELECT = (
    "SELECT r.id, r.url, r.video_id, r.title, r.created_at,"
    " r.outline_id, r.outline_url, r.outline_title, r.exported_at,"
    " COUNT(a.id) AS answer_count"
    " FROM runs AS r"
    " LEFT JOIN answers AS a ON a.run_id = r.id"
)
"""``list_runs`` 와 ``list_exported`` 가 함께 쓰는 SELECT 머리."""


def _summary(row: sqlite3.Row) -> models.RunSummary:
    """``_SUMMARY_SELECT`` 의 행 하나를 요약으로 바꾼다."""
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
    )
```

`list_runs` 의 본문을 바꾼다. 바꾸기 전에는 SELECT 문자열 전체와
`return [ models.RunSummary( ... ) for row in rows ]` 가 있다. 바꾼 뒤
본문은 이것뿐이다(독스트링은 그대로).

```python
    rows = connection.execute(
        _SUMMARY_SELECT + " GROUP BY r.id ORDER BY r.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_summary(row) for row in rows]
```

`list_runs` 바로 뒤에 더한다.

```python
def list_exported(connection: sqlite3.Connection) -> list[models.RunSummary]:
    """Outline 에 저장된 실행을 전부, 새 것부터 돌려준다.

    상한을 두지 않는다. 동기화는 목록 전체를 봐야 한다.

    Args:
        connection: 열린 커넥션.

    Returns:
        ``exported_at`` 이 있는 실행 요약 목록.
    """
    rows = connection.execute(
        _SUMMARY_SELECT
        + " WHERE r.exported_at IS NOT NULL"
        + " GROUP BY r.id"
        + " ORDER BY r.id DESC"
    ).fetchall()
    return [_summary(row) for row in rows]
```

- [ ] **Step 4: 삽입과 일괄 삭제를 더한다**

같은 파일 `delete_run` 바로 뒤에 더한다.

```python
def insert_exported(
    connection: sqlite3.Connection, create: models.SyncCreate
) -> int | None:
    """Outline 문서에서 되살린 저장된 행을 넣는다.

    **커밋하지 않는다.** 트랜잭션은 ``history_sync.apply`` 가 소유한다.
    같은 문서를 가리키는 행이 이미 있으면 넣지 않는다 — 미리보기와
    적용 사이에 다른 탭이 먼저 저장했을 수 있다.

    ``answers``·``run_metadata`` 행은 만들지 않는다. 저장된 실행은
    원래 본문이 없다.

    Args:
        connection: 열린 커넥션.
        create: 만들 행의 값들.

    Returns:
        새 행의 ID. 이미 있어 넣지 않았으면 ``None``.
    """
    existing = connection.execute(
        "SELECT id FROM runs WHERE outline_id = ?", (create.document.id,)
    ).fetchone()
    if existing is not None:
        return None
    row = connection.execute(
        "INSERT INTO runs (url, video_id, title, created_at,"
        " outline_id, outline_url, outline_title, exported_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        " RETURNING id",
        (
            create.url,
            create.video_id,
            create.document.title,
            create.document.created_at,
            create.document.id,
            create.document.url,
            create.document.title,
            create.document.created_at,
        ),
    ).fetchone()
    return int(row["id"])


def delete_runs(
    connection: sqlite3.Connection, run_ids: Sequence[int]
) -> int:
    """실행 여럿을 한 문장으로 지운다.

    **커밋하지 않는다.** 트랜잭션은 ``history_sync.apply`` 가 소유한다.
    없는 ID 는 무시한다. 딸린 답변은 외래키가 함께 지운다.

    Args:
        connection: 열린 커넥션.
        run_ids: 지울 실행 ID 들. 비어 있으면 아무것도 하지 않는다.

    Returns:
        실제로 지운 행 수.
    """
    if not run_ids:
        return 0
    # 자리표시자만 이어 붙인다. 값은 전부 파라미터로 넘긴다.
    placeholders = ", ".join("?" for _ in run_ids)
    cursor = connection.execute(
        f"DELETE FROM runs WHERE id IN ({placeholders})", tuple(run_ids)
    )
    return int(cursor.rowcount)
```

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/services/test_run_history.py -q`
Expected: PASS — 기존 `list_runs` 테스트들이 `_summary` 추출의 회귀
방지가 된다.

- [ ] **Step 6: 검증 4단**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
```

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/services/run_history.py \
        tests/services/test_run_history.py
git commit -m "✨ feat(run-history): 저장된 행 조회·삽입·일괄 삭제"
```

---

### Task 4: 계획 적용 — 한 커밋

**Files:**
- Modify: `src/notebooklm_st/services/history_sync.py`
- Test: `tests/services/test_history_sync.py`

**Interfaces:**
- Consumes: `run_history.delete_runs`, `run_history.insert_exported`
  (Task 3)
- Produces:
  - `history_sync.SyncResult(deleted: int, created: int)`
  - `history_sync.apply(connection: sqlite3.Connection,
    sync_plan: models.SyncPlan) -> SyncResult`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_history_sync.py` 의 import 를 바꾼다. 바꾸기 전.

```python
from notebooklm_st.core import models
from notebooklm_st.services import history_sync
```

바꾼 뒤.

```python
import sqlite3
from collections.abc import Iterator

import pytest

from notebooklm_st.core import models
from notebooklm_st.services import history_sync, run_history, store
```

파일 끝에 더한다.

```python
@pytest.fixture
def connection(tmp_path) -> Iterator[sqlite3.Connection]:
    """임시 파일 DB 커넥션을 열고 테스트 후 닫는다."""
    conn = store.connect(tmp_path / "test.db")
    yield conn
    conn.close()


def save_exported(connection: sqlite3.Connection, doc_id: str) -> int:
    """저장된 실행 하나를 DB 에 만든다."""
    run_id = run_history.save_run(
        connection,
        models.RunResult(
            url="https://youtu.be/dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
            title="원래 제목",
            items=(),
        ),
    )
    run_history.mark_exported(
        connection,
        run_id,
        document_id=doc_id,
        document_title="정리한 제목",
        document_url=f"https://wiki.example.com/doc/{doc_id}",
    )
    return run_id


def create_for(doc_id: str) -> models.SyncCreate:
    """문서 하나를 만들 계획 항목."""
    return models.SyncCreate(
        document=make_document(doc_id),
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
    )


def test_apply_deletes_and_creates_in_one_commit(connection) -> None:
    """삭제와 삽입이 함께 확정된다."""
    gone = save_exported(connection, "gone")
    kept = save_exported(connection, "kept")
    plan = models.SyncPlan(
        deletes=(make_run(gone, "gone"),),
        creates=(create_for("new-1"),),
        skips=(),
    )

    result = history_sync.apply(connection, plan)

    assert result == history_sync.SyncResult(deleted=1, created=1)
    ids = {run.outline_id for run in run_history.list_exported(connection)}
    assert ids == {"kept", "new-1"}
    assert kept in [run.id for run in run_history.list_exported(connection)]


class FailingRunInsert:
    """실행 삽입 문장에서만 터지는 커넥션 대역.

    나머지 호출은 진짜 커넥션이 그대로 처리한다. 삭제는 됐는데 삽입이
    죽는 상황을 재현한다.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """감쌀 진짜 커넥션을 받는다."""
        self._connection = connection

    def execute(self, sql, *args):
        """실행을 넣는 문장만 실패시킨다."""
        if "INSERT INTO runs" in sql:
            raise sqlite3.OperationalError("database is locked")
        return self._connection.execute(sql, *args)

    def __getattr__(self, name):
        """나머지 속성은 진짜 커넥션에 맡긴다."""
        return getattr(self._connection, name)


def test_apply_rolls_back_the_deletes_when_an_insert_fails(
    connection,
) -> None:
    """삽입이 죽으면 삭제도 되돌린다. 반쪽짜리 동기화는 없다."""
    gone = save_exported(connection, "gone")
    plan = models.SyncPlan(
        deletes=(make_run(gone, "gone"),),
        creates=(create_for("new-1"),),
        skips=(),
    )

    with pytest.raises(sqlite3.OperationalError):
        history_sync.apply(FailingRunInsert(connection), plan)

    ids = [run.outline_id for run in run_history.list_exported(connection)]
    assert ids == ["gone"]


def test_apply_skips_a_document_that_is_already_linked(connection) -> None:
    """다른 탭이 먼저 저장한 문서는 만들지 않고 세지도 않는다."""
    save_exported(connection, "doc-1")
    plan = models.SyncPlan(
        deletes=(), creates=(create_for("doc-1"),), skips=()
    )

    result = history_sync.apply(connection, plan)

    assert result.created == 0
    assert len(run_history.list_exported(connection)) == 1


def test_apply_does_not_count_a_run_that_is_already_gone(
    connection,
) -> None:
    """다른 탭이 먼저 지운 행은 개수에 들어가지 않는다."""
    plan = models.SyncPlan(
        deletes=(make_run(999, "gone"),), creates=(), skips=()
    )

    result = history_sync.apply(connection, plan)

    assert result.deleted == 0


def test_apply_with_an_empty_plan_changes_nothing(connection) -> None:
    """빈 계획은 0·0 이다."""
    save_exported(connection, "doc-1")
    plan = models.SyncPlan(deletes=(), creates=(), skips=())

    result = history_sync.apply(connection, plan)

    assert result == history_sync.SyncResult(deleted=0, created=0)
    assert len(run_history.list_exported(connection)) == 1
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/services/test_history_sync.py -q`
Expected: FAIL — `AttributeError: module 'notebooklm_st.services.history_sync'
has no attribute 'apply'`

- [ ] **Step 3: 적용 함수를 더한다**

`src/notebooklm_st/services/history_sync.py` 의 import 를 바꾼다.
바꾸기 전.

```python
from collections.abc import Sequence

from notebooklm_st.core import models, outline_import, youtube
```

바꾼 뒤.

```python
import dataclasses
import sqlite3
from collections.abc import Sequence

from notebooklm_st.core import models, outline_import, youtube
from notebooklm_st.services import run_history
```

모듈 독스트링의 첫 문단 뒤에 한 문장을 더한다.

```python
"""저장된 이력과 Outline 문서 목록을 맞춘다.

``plan`` 은 두 목록을 받아 무엇을 지우고 만들지 정하는 순수 함수이고,
``apply`` 는 그 계획을 DB 에 쓴다. httpx 도 Streamlit 도 모른다.
목록을 읽는 것은 ``services.outline``, DB 를 읽는 것은
``services.run_history`` 가 한다.
"""
```

파일 끝에 더한다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class SyncResult:
    """적용이 실제로 바꾼 개수.

    계획의 개수와 다를 수 있다. 미리보기와 적용 사이에 다른 탭이
    먼저 지우거나 저장했을 수 있다.
    """

    deleted: int
    created: int


def apply(
    connection: sqlite3.Connection, sync_plan: models.SyncPlan
) -> SyncResult:
    """계획을 DB 에 쓴다. 삭제와 삽입을 커밋 하나로 묶는다.

    어느 쪽이든 실패하면 전부 되돌리고 다시 던진다. 커넥션은 앱
    전체가 함께 쓰므로 반쪽만 걸린 채 나가면 다른 곳의 commit 이
    그것을 확정해 버린다(``run_history.mark_exported`` 와 같은 이유).

    Args:
        connection: 열린 커넥션.
        sync_plan: ``plan`` 이 세운 계획.

    Returns:
        실제로 지운 개수와 만든 개수.

    Raises:
        sqlite3.Error: 삭제나 삽입이 실패한 경우. 되돌린 뒤 던진다.
    """
    try:
        deleted = run_history.delete_runs(
            connection, [run.id for run in sync_plan.deletes]
        )
        created = 0
        for create in sync_plan.creates:
            if run_history.insert_exported(connection, create) is not None:
                created += 1
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return SyncResult(deleted=deleted, created=created)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/services/test_history_sync.py -q`
Expected: PASS

- [ ] **Step 5: 검증 4단**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
```

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/history_sync.py \
        tests/services/test_history_sync.py
git commit -m "✨ feat(history-sync): 계획을 커밋 하나로 적용"
```

---

### Task 5: Outline 안내 문구를 별도 모듈로 옮기기

**Files:**
- Create: `src/notebooklm_st/services/outline_messages.py`
- Modify: `src/notebooklm_st/services/outline.py`
- Test: `tests/services/test_outline.py` (변경 없음 — 그대로 통과해야 한다)

**Interfaces:**
- Consumes: 없음
- Produces:
  - `outline_messages.DETAIL_LIMIT: int`
  - `outline_messages.StatusMessage` (`Callable[[int], str]`)
  - `outline_messages.failure_message(response: httpx.Response,
    token: str, status: int, status_message: StatusMessage) -> str`
  - `outline_messages.create_status_message(status: int) -> str`
  - `outline_messages.read_status_message(status: int) -> str`

순수 리팩터다. `outline.py` 는 429줄이라 목록 호출을 더하기 전에 문구
함수를 뺀다. **동작이 바뀌면 안 된다.** 테스트 파일은 `outline.` 공개
이름만 쓰므로 손대지 않는다.

- [ ] **Step 1: 새 모듈을 만든다**

`src/notebooklm_st/services/outline_messages.py` 를 새로 만든다. 본문은
`outline.py` 의 `_failure_message`·`_status_message`·
`_read_status_message`·`_detail` 과 `DETAIL_LIMIT`·`StatusMessage` 를
옮긴 것이며, 이름에서 앞 밑줄만 뗀다. 문장은 한 글자도 바꾸지 않는다
— 기존 테스트가 그 문장을 단언한다. 전체 모습은 이렇다.

```python
"""Outline 의 실패 응답을 사람이 읽고 고칠 수 있는 문장으로 옮긴다.

호출 경로(생성·조회·목록)마다 "무엇부터 확인하라" 가 다르다. 그
차이를 여기 모아 ``services.outline`` 은 호출만 남긴다.
"""

from collections.abc import Callable

import httpx

DETAIL_LIMIT = 200
"""Outline 이 보낸 설명에서 화면에 옮길 최대 글자 수.

`st.error` 한 칸에 들어가야 한다. 더 길면 정작 우리가 쓴 안내 문장이
밀려 안 읽힌다.
"""

StatusMessage = Callable[[int], str]
"""상태 코드를 안내 문장으로 옮기는 함수.

읽기와 쓰기가 서로 다른 것을 쓴다.
"""


def failure_message(
    response: httpx.Response,
    token: str,
    status: int,
    status_message: StatusMessage,
) -> str:
    """실패 응답을 사람이 읽고 고칠 수 있는 한 문장으로 만든다.

    우리가 지은 안내 뒤에 **Outline 이 보낸 설명**을 붙인다. 설명을
    버리고 상태 코드만 남기면, 서버가 무엇이 틀렸는지 정확히 말해
    줬는데도 사람이 추측으로 파게 된다. 실제로 그렇게 됐다.

    Args:
        response: 오류 응답.
        token: 화면에 오르면 안 되는 값. 본문에 섞여 있으면 설명째
            버린다.
        status: HTTP 상태 코드.
        status_message: 이 호출 경로의 안내를 만드는 함수.

    Returns:
        화면에 그대로 나갈 한국어 문장.
    """
    text = detail(response, token)
    if not text:
        return status_message(status)
    return f"{status_message(status)} Outline 이 말한 것: {text}"


def create_status_message(status: int) -> str:
    """오류 상태 코드를 "무엇부터 확인하라" 는 안내로 옮긴다.

    순서가 중요하다. 실측해 보니 **없는 컬렉션 ID** 가 404 가 아니라
    403 으로 온다 — Outline 이 "없다" 와 "권한 없다" 를 한 응답으로
    뭉치기 때문이다. 그래서 403 에서 토큰을 먼저 의심하게 하면 멀쩡한
    토큰을 파게 된다.

    Args:
        status: HTTP 상태 코드.

    Returns:
        화면에 그대로 나갈 한국어 문장.
    """
    if status == 400:
        return (
            "Outline 이 값을 받아들이지 않았습니다."
            " 컬렉션 ID 가 UUID 인지 확인하세요 — 컬렉션 이름은"
            " 받지 않습니다."
        )
    if status == 401:
        return (
            "Outline 이 API 토큰을 받아들이지 않았습니다."
            " 토큰이 맞는지, 만료되지 않았는지 확인하세요."
        )
    if status == 403:
        return (
            "Outline 이 요청을 거부했습니다."
            " 컬렉션 ID 가 이 토큰의 계정이 쓸 수 있는 컬렉션인지"
            " 먼저 확인하세요 — 없는 컬렉션도 이 오류로 옵니다."
            " 그다음 토큰 scope(documents.create)를 봅니다."
        )
    if status == 404:
        return "Outline 이 대상을 찾지 못했습니다. 주소를 확인하세요."
    return f"Outline 이 오류를 냈습니다(HTTP {status})."


def read_status_message(status: int) -> str:
    """읽기 실패를 "무엇부터 확인하라" 는 안내로 옮긴다.

    쓰기와 문구를 나눈다. ``create_status_message`` 는 403 에서 컬렉션
    ID 를 먼저 의심하게 하는데, 그것은 ``documents.create`` 의 실측에서
    나온 순서다. 읽기에 그 안내를 내면 멀쩡한 컬렉션을 파게 된다.

    **401 에서 scope 를 먼저 짚는 것도 실측에서 나왔다.** scope 밖
    엔드포인트를 부르면 권한 오류(403)가 아니라 인증 오류(401)가
    오고, 본문은 ``Authentication required`` 다. Outline 의 현재
    소스는 이 경우 403 을 내므로 배포판에 따라 다르며, 그래서 401 과
    403 양쪽이 scope 를 짚는다. 토큰을 먼저 의심하게 하면 멀쩡한
    토큰을 파게 된다 — 저장은 되는데 정리본만 안 되는 상황이 정확히
    이것이다.

    Args:
        status: HTTP 상태 코드.

    Returns:
        화면에 그대로 나갈 한국어 문장.
    """
    if status == 401:
        return (
            "Outline 이 읽기 요청을 인증하지 못했습니다."
            " API 키 scope 에 documents.info 가 있는지 먼저"
            " 확인하세요 — 저장만 하던 키에는 없고, 그때 403 이"
            " 아니라 이 오류로 옵니다."
            " 그다음 토큰이 맞는지, 만료되지 않았는지 봅니다."
        )
    if status == 403:
        return (
            "Outline 이 문서 읽기를 거부했습니다."
            " API 키 scope 에 읽기 권한이 있는지 확인하세요 —"
            " 저장만 하던 키에는 없습니다."
        )
    if status == 404:
        return (
            "Outline 에서 문서를 찾지 못했습니다."
            " 위키에서 지워졌을 수 있습니다."
            " 그 이력을 선택에서 빼고 다시 시도하세요."
        )
    return f"Outline 이 오류를 냈습니다(HTTP {status})."


def detail(response: httpx.Response, token: str) -> str:
    """응답 본문에서 사람에게 보여 줄 한 줄을 뽑는다.

    토큰은 헤더에 있지 본문에 없으므로 본문을 보여 줘도 샐 것이 없다.
    그래도 서버가 무엇을 돌려주든 화면에 무엇이 실리는지는 우리가
    통제해야 하므로, 토큰이 섞여 있으면 설명째 버린다.

    Args:
        response: 오류 응답.
        token: 본문에 있으면 안 되는 값.

    Returns:
        한 줄로 접고 길이를 자른 설명. 읽을 것이 없으면 빈 문자열.
    """
    try:
        body = response.json()
        text = str(body.get("message") or body.get("error") or "")
    except (ValueError, AttributeError):
        text = response.text
    text = " ".join(text.split())[:DETAIL_LIMIT]
    if not text or token in text:
        return ""
    return text
```

옮기며 바뀐 것은 셋뿐이다. `failure_message` 안의 지역 변수 이름이
`detail` 에서 `text` 로 바뀌었다(같은 이름의 함수와 겹치지 않게).
`read_status_message` 독스트링의 ``_status_message`` 참조가
``create_status_message`` 로 바뀌었다. 나머지는 원본과 같다.

- [ ] **Step 2: `outline.py` 에서 옮긴 것을 지우고 새 이름을 쓴다**

`src/notebooklm_st/services/outline.py` 에서 다음을 지운다.

- `DETAIL_LIMIT` 상수와 그 독스트링
- `StatusMessage` 별칭과 그 독스트링
- 함수 `_failure_message`, `_status_message`, `_read_status_message`,
  `_detail` 전체

import 를 바꾼다. 바꾸기 전.

```python
import dataclasses
import os
from collections.abc import Callable

import httpx
```

바꾼 뒤.

```python
import dataclasses
import os
from collections.abc import Callable

import httpx

from notebooklm_st.services import outline_messages
```

`Callable` 은 `PostLike` 가 아직 쓰므로 남긴다.

`create_document` 안의 호출을 바꾼다. 바꾸기 전.

```python
    if response.status_code >= 400:
        raise OutlineError(
            _failure_message(
                response,
                config.token,
                response.status_code,
                _status_message,
            )
        )
```

바꾼 뒤.

```python
    if response.status_code >= 400:
        raise OutlineError(
            outline_messages.failure_message(
                response,
                config.token,
                response.status_code,
                outline_messages.create_status_message,
            )
        )
```

`fetch_document` 안의 호출을 바꾼다. 바꾸기 전.

```python
    if response.status_code >= 400:
        raise OutlineError(
            _failure_message(
                response,
                config.token,
                response.status_code,
                _read_status_message,
            )
        )
```

바꾼 뒤.

```python
    if response.status_code >= 400:
        raise OutlineError(
            outline_messages.failure_message(
                response,
                config.token,
                response.status_code,
                outline_messages.read_status_message,
            )
        )
```

모듈 독스트링 첫 문단 뒤에 한 줄을 더한다.

```
안내 문구는 ``outline_messages`` 에 있다.
```

- [ ] **Step 3: 기존 테스트가 그대로 통과하는지 확인한다**

Run: `uv run pytest tests/services/test_outline.py tests/pages -q`
Expected: PASS — 문구 단언(`"토큰" in ...`, `"documents.info"` 등)이 전부
그대로 통과한다. 하나라도 실패하면 옮기며 문장을 바꾼 것이다.

- [ ] **Step 4: 남은 참조가 없는지 확인한다**

Run: `grep -n "_failure_message\|_status_message\|_read_status_message\|_detail(" src/notebooklm_st/services/outline.py`
Expected: 출력 없음.

- [ ] **Step 5: 검증 4단**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
```

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/outline.py \
        src/notebooklm_st/services/outline_messages.py
git commit -m "♻️ refactor(outline): 안내 문구 함수를 별도 모듈로 옮기기"
```

---

### Task 6: Outline 문서 목록 호출

**Files:**
- Modify: `src/notebooklm_st/services/outline.py`
- Modify: `src/notebooklm_st/services/outline_messages.py`
- Modify: `docs/superpowers/specs/2026-09-28-history-sync-design.md`
  (7.1 과 13 의 페이지네이션 문장)
- Test: `tests/services/test_outline.py`

**Interfaces:**
- Consumes: `models.ListedDocument` (Task 2),
  `outline_messages.failure_message` (Task 5)
- Produces:
  - `outline.LIST_PAGE_SIZE: int` (100), `outline.LIST_PAGE_LIMIT: int` (50)
  - `outline.list_documents(config: OutlineConfig,
    timeout: float = FETCH_TIMEOUT, poster: PostLike = httpx.post)
    -> list[models.ListedDocument]`
  - `outline_messages.list_status_message(status: int) -> str`

**페이지네이션은 `offset` 으로 직접 넘긴다.** 명세 7.1 은 `nextPath` 를
따라가라고 했지만, 명세 13 이 그 모양을 미검증으로 남겼다. Outline 은
마지막 페이지에도 `nextPath` 를 실어 보낼 수 있어 그것으로는 끝을 알 수
없다. 대신 요청 본문의 `offset` 을 `LIST_PAGE_SIZE` 씩 올리고, 한 페이지가
`LIST_PAGE_SIZE` 보다 짧게 오면 끝으로 본다. 이 결정을 명세에 되반영한다
(Step 7).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_outline.py` 의 import 에 `datetime` 을 더한다.
바꾸기 전.

```python
import httpx
import pytest
```

바꾼 뒤.

```python
import datetime

import httpx
import pytest
```

파일 끝에 더한다. 파일은 이미 `outline` 을 import 하고 `BASE_URL`·
`TOKEN`·`COLLECTION`·`PUBLIC_URL`·`make_config`·`fake_poster` 를 갖고
있다.

```python
def listed_item(doc_id: str, text: str = "- 영상 URL: x\n") -> dict:
    """documents.list 응답의 문서 하나."""
    return {
        "id": doc_id,
        "title": f"제목 {doc_id}",
        "url": f"/doc/{doc_id}",
        "createdAt": "2026-09-25T01:00:00.000Z",
        "text": text,
    }


def page(items: list[dict]) -> httpx.Response:
    """documents.list 가 돌려주는 200 응답."""
    return httpx.Response(
        200,
        json={
            "data": items,
            "pagination": {"limit": 100, "offset": 0, "nextPath": "/x"},
        },
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.list"),
    )


def paged_poster(responses, calls):
    """호출마다 준비된 응답을 차례로 돌려주는 poster 를 만든다."""
    queue = list(responses)

    def post(url, **kwargs):
        """httpx.post 를 대신한다."""
        calls.append((url, kwargs))
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    return post


def test_list_documents_posts_the_collection_filter() -> None:
    """주소·헤더·본문이 API 계약대로 나간다."""
    calls: list[tuple[str, dict[str, object]]] = []

    outline.list_documents(
        make_config(), poster=fake_poster(page([]), calls)
    )

    url, kwargs = calls[0]
    assert url == f"{BASE_URL}/api/documents.list"
    assert kwargs["headers"] == {"Authorization": f"Bearer {TOKEN}"}
    assert kwargs["json"] == {
        "filters": [
            {"field": "collectionId", "operator": "eq", "value": COLLECTION}
        ],
        "sort": "createdAt",
        "direction": "DESC",
        "limit": outline.LIST_PAGE_SIZE,
        "offset": 0,
    }
    assert kwargs["timeout"] == outline.FETCH_TIMEOUT


def test_list_documents_returns_listed_documents() -> None:
    """응답의 다섯 값을 꺼내 온다. URL 은 공개 주소로 절대화한다."""
    documents = outline.list_documents(
        make_config(public_url=PUBLIC_URL),
        poster=fake_poster(page([listed_item("doc-1", "본문\n")]), []),
    )

    assert len(documents) == 1
    document = documents[0]
    assert document.id == "doc-1"
    assert document.title == "제목 doc-1"
    assert document.url == f"{PUBLIC_URL}/doc/doc-1"
    assert document.markdown == "본문\n"


def test_list_documents_converts_created_at_to_local_time() -> None:
    """``createdAt`` 이 ``store.now()`` 와 같은 로컬 초 단위 ISO 가 된다."""
    documents = outline.list_documents(
        make_config(), poster=fake_poster(page([listed_item("doc-1")]), [])
    )

    expected = (
        datetime.datetime(2026, 9, 25, 1, 0, 0, tzinfo=datetime.UTC)
        .astimezone()
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )
    assert documents[0].created_at == expected
    assert "+" not in documents[0].created_at
    assert "Z" not in documents[0].created_at


def test_list_documents_follows_offsets_until_a_short_page() -> None:
    """가득 찬 페이지 뒤에는 다음 offset 으로 다시 부른다."""
    full = [listed_item(f"doc-{i}") for i in range(outline.LIST_PAGE_SIZE)]
    calls: list[tuple[str, dict[str, object]]] = []

    documents = outline.list_documents(
        make_config(),
        poster=paged_poster(
            [page(full), page([listed_item("last")])], calls
        ),
    )

    assert len(documents) == outline.LIST_PAGE_SIZE + 1
    assert documents[-1].id == "last"
    assert [c[1]["json"]["offset"] for c in calls] == [
        0,
        outline.LIST_PAGE_SIZE,
    ]


def test_list_documents_stops_after_an_empty_page() -> None:
    """빈 페이지가 오면 더 부르지 않는다."""
    calls: list[tuple[str, dict[str, object]]] = []

    documents = outline.list_documents(
        make_config(), poster=paged_poster([page([])], calls)
    )

    assert documents == []
    assert len(calls) == 1


def test_list_documents_gives_up_past_the_page_limit() -> None:
    """가득 찬 페이지가 상한만큼 이어지면 오류다. 무한히 돌지 않는다."""
    full = [listed_item(f"doc-{i}") for i in range(outline.LIST_PAGE_SIZE)]
    responses = [page(full)] * (outline.LIST_PAGE_LIMIT + 1)

    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(
            make_config(), poster=paged_poster(responses, [])
        )

    assert "너무" in str(excinfo.value)


def test_list_documents_drops_a_partial_list_when_a_page_fails() -> None:
    """두 번째 페이지가 죽으면 첫 페이지도 버린다. 반쪽 목록으로 지우지
    않는다."""
    full = [listed_item(f"doc-{i}") for i in range(outline.LIST_PAGE_SIZE)]
    failure = httpx.Response(
        500,
        json={"message": "boom"},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.list"),
    )

    with pytest.raises(outline.OutlineError):
        outline.list_documents(
            make_config(), poster=paged_poster([page(full), failure], [])
        )


def test_list_documents_rejects_a_response_without_data() -> None:
    """``data`` 가 없으면 이해하지 못한 것이다."""
    response = httpx.Response(
        200,
        json={"ok": True},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.list"),
    )

    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(make_config(), poster=fake_poster(response, []))

    assert "이해하지 못했습니다" in str(excinfo.value)


def test_list_documents_rejects_an_item_without_text() -> None:
    """본문이 빠진 문서가 하나라도 있으면 목록 전체가 실패다."""
    item = listed_item("doc-1")
    del item["text"]

    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(
            make_config(), poster=fake_poster(page([item]), [])
        )

    assert "이해하지 못했습니다" in str(excinfo.value)


def test_list_documents_rejects_an_unreadable_created_at() -> None:
    """날짜로 읽히지 않는 ``createdAt`` 도 목록 전체를 실패시킨다.

    그 문서만 조용히 빠지면 다음 동기화가 그 행을 지운다.
    """
    item = listed_item("doc-1")
    item["createdAt"] = "어제"

    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(
            make_config(), poster=fake_poster(page([item]), [])
        )

    assert "이해하지 못했습니다" in str(excinfo.value)


def test_list_documents_accepts_a_created_at_without_a_zone() -> None:
    """접미가 없으면 UTC 로 본다."""
    item = listed_item("doc-1")
    item["createdAt"] = "2026-09-25T01:00:00"

    documents = outline.list_documents(
        make_config(), poster=fake_poster(page([item]), [])
    )

    assert documents[0].created_at.startswith("2026-09-2")


def test_list_documents_reports_a_connection_failure() -> None:
    """연결 실패는 사람이 읽을 문장으로 온다."""
    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(
            make_config(),
            poster=fake_poster(httpx.ConnectError("refused"), []),
        )

    assert "연결하지 못했습니다" in str(excinfo.value)


def list_with(status: int) -> str:
    """오류 상태 코드로 목록을 시도하고 문구를 돌려준다."""
    response = httpx.Response(
        status,
        json={},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.list"),
    )
    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(make_config(), poster=fake_poster(response, []))
    return str(excinfo.value)


def test_list_documents_401_points_at_the_list_scope() -> None:
    """저장·조회만 하던 키에는 목록 scope 가 없다."""
    message = list_with(401)

    assert "documents.list" in message
    assert "documents.info" not in message


def test_list_documents_403_points_at_the_list_scope() -> None:
    """403 도 scope 를 짚는다."""
    assert "documents.list" in list_with(403)


def test_list_documents_404_points_at_the_address() -> None:
    """목록 엔드포인트의 404 는 주소 문제다."""
    assert "주소" in list_with(404)


def test_list_documents_429_asks_to_wait() -> None:
    """요청 한도는 잠시 뒤 다시 시도하라고 한다."""
    assert "잠시" in list_with(429)


def test_list_documents_5xx_carries_the_status() -> None:
    """나머지는 상태 코드를 그대로 보여 준다."""
    assert "502" in list_with(502)


def test_list_documents_never_leaks_the_token() -> None:
    """토큰이 어떤 문구에도 실리지 않는다."""
    response = httpx.Response(
        403,
        json={"message": f"bad token {TOKEN}"},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.list"),
    )

    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(make_config(), poster=fake_poster(response, []))

    assert TOKEN not in str(excinfo.value)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/services/test_outline.py -q -k list_documents`
Expected: FAIL — `AttributeError: module 'notebooklm_st.services.outline'
has no attribute 'list_documents'`

- [ ] **Step 3: 목록용 안내 문구를 더한다**

`src/notebooklm_st/services/outline_messages.py` 의 `read_status_message`
바로 뒤에 더한다.

```python
def list_status_message(status: int) -> str:
    """목록 조회 실패를 "무엇부터 확인하라" 는 안내로 옮긴다.

    ``read_status_message`` 와 같은 순서로 scope 를 먼저 짚되, 이름이
    ``documents.list`` 다. 429 를 따로 두는 이유는 목록이 여러 페이지를
    연달아 부르기 때문이다 — 요청 한도에 걸릴 수 있는 유일한 경로다.

    Args:
        status: HTTP 상태 코드.

    Returns:
        화면에 그대로 나갈 한국어 문장.
    """
    if status == 401:
        return (
            "Outline 이 목록 요청을 인증하지 못했습니다."
            " API 키 scope 에 documents.list 가 있는지 먼저"
            " 확인하세요 — 저장·조회만 하던 키에는 없고, 그때 403 이"
            " 아니라 이 오류로 옵니다."
            " 그다음 토큰이 맞는지, 만료되지 않았는지 봅니다."
        )
    if status == 403:
        return (
            "Outline 이 문서 목록을 거부했습니다."
            " API 키 scope 에 documents.list 가 있는지 확인하세요 —"
            " 저장·조회만 하던 키에는 없습니다."
        )
    if status == 404:
        return "Outline 이 대상을 찾지 못했습니다. 주소를 확인하세요."
    if status == 429:
        return (
            "Outline 이 요청 한도에 걸렸습니다."
            " 잠시 뒤 다시 시도하세요."
        )
    return f"Outline 이 오류를 냈습니다(HTTP {status})."
```

- [ ] **Step 4: 목록 호출을 더한다**

`src/notebooklm_st/services/outline.py` 의 import 를 바꾼다. 바꾸기 전.

```python
import dataclasses
import os
from collections.abc import Callable

import httpx

from notebooklm_st.services import outline_messages
```

바꾼 뒤.

```python
import dataclasses
import datetime
import os
from collections.abc import Callable

import httpx

from notebooklm_st.core import models
from notebooklm_st.services import outline_messages
```

`_INFO_PATH` 정의 바로 아래에 더한다.

```python
_LIST_PATH = "/api/documents.list"

LIST_PAGE_SIZE = 100
"""목록 한 페이지에 청할 문서 수."""

LIST_PAGE_LIMIT = 50
"""목록을 이어 부를 최대 페이지 수.

응답이 이상해 끝이 오지 않아도 무한히 돌지 않게 한다. 5,000 건이면
개인 위키의 요약본으로는 충분하다.
"""
```

`fetch_document` 바로 뒤에 더한다.

```python
def list_documents(
    config: OutlineConfig,
    timeout: float = FETCH_TIMEOUT,
    poster: PostLike = httpx.post,
) -> list[models.ListedDocument]:
    """컬렉션의 문서를 전부 읽어 온다.

    ``offset`` 을 ``LIST_PAGE_SIZE`` 씩 올리며 이어 부르고, 한 페이지가
    그보다 짧게 오면 끝으로 본다. 어느 페이지든 실패하면 지금까지
    모은 것을 버리고 실패한다 — 반쪽 목록으로 이력을 지우면 멀쩡한
    행이 사라진다.

    **연결 주소로 나간다.** 공개 주소는 문서 URL 을 절대화할 때만
    쓴다.

    Args:
        config: 주소·토큰·컬렉션 ID.
        timeout: 요청 하나에 주는 최대 초.
        poster: 요청을 보내는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.

    Returns:
        생성 시각 내림차순의 문서 목록.

    Raises:
        OutlineError: 연결이 안 되거나, 거부당했거나, 응답이 기대한
            모양이 아니거나, 페이지가 상한을 넘긴 경우.
    """
    documents: list[models.ListedDocument] = []
    for page_index in range(LIST_PAGE_LIMIT):
        page = _list_page(
            config, page_index * LIST_PAGE_SIZE, timeout, poster
        )
        documents.extend(page)
        if len(page) < LIST_PAGE_SIZE:
            return documents
    raise OutlineError(
        "Outline 문서 목록이 너무 길거나 목록 응답이 이상합니다"
        f"(페이지 상한 {LIST_PAGE_LIMIT})."
    )


def _list_page(
    config: OutlineConfig,
    offset: int,
    timeout: float,
    poster: PostLike,
) -> list[models.ListedDocument]:
    """목록 한 페이지를 읽는다.

    Args:
        config: 주소·토큰·컬렉션 ID.
        offset: 건너뛸 문서 수.
        timeout: 요청에 주는 최대 초.
        poster: 요청을 보내는 함수.

    Returns:
        이 페이지의 문서들.

    Raises:
        OutlineError: 연결·거부·응답 모양 문제.
    """
    try:
        response = poster(
            f"{config.base_url}{_LIST_PATH}",
            headers={"Authorization": f"Bearer {config.token}"},
            json={
                "filters": [
                    {
                        "field": "collectionId",
                        "operator": "eq",
                        "value": config.collection_id,
                    }
                ],
                "sort": "createdAt",
                "direction": "DESC",
                "limit": LIST_PAGE_SIZE,
                "offset": offset,
            },
            timeout=timeout,
        )
    except (httpx.HTTPError, httpx.InvalidURL) as error:
        raise OutlineError(
            f"Outline 에 연결하지 못했습니다({type(error).__name__})."
        ) from error
    if response.status_code >= 400:
        raise OutlineError(
            outline_messages.failure_message(
                response,
                config.token,
                response.status_code,
                outline_messages.list_status_message,
            )
        )
    return _parse_page(config, response)


def _parse_page(
    config: OutlineConfig, response: httpx.Response
) -> list[models.ListedDocument]:
    """응답 본문에서 문서들을 꺼낸다.

    한 항목이라도 기대한 키가 없거나 시각이 읽히지 않으면 페이지
    전체가 실패다. 그 항목만 조용히 빼면 다음 동기화가 그 행을 지운다.

    Args:
        config: 상대 URL 앞에 붙일 공개 주소를 가진 설정.
        response: ``documents.list`` 의 응답.

    Returns:
        이 페이지의 문서들.

    Raises:
        OutlineError: JSON 이 아니거나 기대한 키가 없는 경우.
    """
    try:
        data = response.json()["data"]
        return [
            models.ListedDocument(
                id=str(item["id"]),
                title=str(item["title"]),
                url=_absolute(config.public_url, str(item["url"])),
                created_at=_to_local_time(str(item["createdAt"])),
                markdown=str(item["text"]),
            )
            for item in data
        ]
    except (ValueError, KeyError, TypeError) as error:
        raise OutlineError("Outline 의 응답을 이해하지 못했습니다.") from error


def _to_local_time(stamp: str) -> str:
    """Outline 의 UTC 시각을 ``store.now()`` 와 같은 모양으로 바꾼다.

    ``2026-09-25T01:00:00.000Z`` → 로컬 시각의 ``2026-09-25T10:00:00``.
    접미가 없으면 UTC 로 본다.

    Args:
        stamp: ISO 8601 문자열.

    Returns:
        타임존 접미가 없는 초 단위 ISO 문자열.

    Raises:
        ValueError: 날짜로 읽히지 않는 경우.
    """
    moment = datetime.datetime.fromisoformat(stamp)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.UTC)
    return (
        moment.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    )
```

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/services/test_outline.py -q`
Expected: PASS

- [ ] **Step 6: `outline.py` 길이를 확인한다**

Run: `wc -l src/notebooklm_st/services/outline.py`
Expected: Task 5 의 분리 덕에 목록 호출을 더하고도 Task 5 이전(429줄)
보다 길지 않다. 그보다 길면 `_parse`·`_parse_document`·`_parse_page`·
`_absolute` 를 `services/outline_parse.py` 로 뽑는다(선택).

- [ ] **Step 7: 명세의 페이지네이션 문장을 되반영한다**

`docs/superpowers/specs/2026-09-28-history-sync-design.md` 7.1 의 첫
글머리를 바꾼다. 바꾸기 전.

```
- `_LIST_PATH = "/api/documents.list"` 를 `filters` 컬렉션 조건과
  `limit: LIST_PAGE_SIZE`, `sort: "createdAt"`, `direction: "DESC"` 로
  부른다. 응답 `pagination.nextPath` 가 있으면 `base_url` 에 붙여 계속
  부른다.
```

바꾼 뒤.

```
- `_LIST_PATH = "/api/documents.list"` 를 `filters` 컬렉션 조건과
  `limit: LIST_PAGE_SIZE`, `sort: "createdAt"`, `direction: "DESC"`,
  `offset` 으로 부른다. `offset` 을 `LIST_PAGE_SIZE` 씩 올리며 이어
  부르고, 한 페이지가 그보다 짧게 오면 끝으로 본다. 응답의
  `pagination.nextPath` 는 쓰지 않는다 — 마지막 페이지에도 실려 올 수
  있어 끝을 알려 주지 못한다.
```

같은 파일 13장에서 `nextPath` 글머리를 통째로 지운다. 지울 글머리는
"**`nextPath` 의 모양.**" 으로 시작하는 것이다.

- [ ] **Step 8: 검증 4단**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
```

- [ ] **Step 9: 커밋**

```bash
git add src/notebooklm_st/services/outline.py \
        src/notebooklm_st/services/outline_messages.py \
        tests/services/test_outline.py \
        docs/superpowers/specs/2026-09-28-history-sync-design.md
git commit -m "✨ feat(outline): 컬렉션 문서 목록을 페이지 단위로 읽기"
```

---

### Task 7: 화면 — 확인·미리보기·적용

**Files:**
- Create: `src/notebooklm_st/pages/_history_sync.py`
- Modify: `src/notebooklm_st/pages/history.py`
- Test: `tests/pages/test_history.py`

**Interfaces:**
- Consumes: `outline.config_from_env`, `outline.list_documents`,
  `outline.OutlineError`, `run_history.list_exported`,
  `history_sync.plan`, `history_sync.apply`, `history_sync.SyncResult`,
  `labels.shorten`
- Produces: `_history_sync.render(connection: sqlite3.Connection) -> None`

**Streamlit 제약.** `st.expander` 는 중첩할 수 없다. 동기화 영역이
expander 이므로 그 안의 세 목록은 `st.markdown` 으로 그린다.

**기존 테스트 둘을 고쳐야 한다.** `test_empty_history_shows_notice` 와
`test_delete_removes_the_run_after_confirming` 이 `len(app.info) == 1` 을
단언하는데, 설정 없는 동기화 영역이 `st.info` 를 하나 더 그린다. 개수
대신 문구를 단언하도록 바꾼다(Step 1).

- [ ] **Step 1: 기존 테스트 둘의 단언을 바꾼다**

`tests/pages/test_history.py` 의 `test_empty_history_shows_notice` 에서
바꾸기 전.

```python
    assert not app.exception
    assert len(app.info) == 1
```

바꾼 뒤.

```python
    assert not app.exception
    notices = [element.value for element in app.info]
    assert "아직 저장된 실행이 없습니다." in notices
```

`test_delete_removes_the_run_after_confirming` 에서 바꾸기 전.

```python
    assert run_history.list_runs(app_db) == []
    assert len(app.info) == 1
```

바꾼 뒤.

```python
    assert run_history.list_runs(app_db) == []
    notices = [element.value for element in app.info]
    assert "아직 저장된 실행이 없습니다." in notices
```

Run: `uv run pytest tests/pages/test_history.py -q`
Expected: PASS — 아직 화면을 바꾸지 않았으므로 그대로 통과한다.

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/pages/test_history.py` 끝에 더한다. 파일은 이미 `sqlite3`·`v1`·
`models`·`youtube`·`outline`·`run_history`·`script`·`make_result`·
`export`·`set_outline_env` 를 갖고 있다. import 에 `history_sync` 를
더한다. 바꾸기 전.

```python
from notebooklm_st.services import outline, run_history
```

바꾼 뒤.

```python
from notebooklm_st.services import history_sync, outline, run_history
```

```python
SYNC_BODY = (
    "- 제목: 되살릴 문서\n"
    "- 영상 URL: https://www.youtube.com/watch?v=aaaaaaaaaaa\n"
    "\n---\n\n## 핵심 주장\n\n세 가지다.\n"
)


def listed(doc_id: str, markdown: str = SYNC_BODY) -> models.ListedDocument:
    """목록에서 읽어 온 문서 하나."""
    return models.ListedDocument(
        id=doc_id,
        title=f"문서 {doc_id}",
        url=f"http://192.168.0.10:3000/doc/{doc_id}",
        created_at="2026-09-25T10:00:00",
        markdown=markdown,
    )


def fake_list(documents):
    """list_documents 를 대신해 준비된 목록을 돌려준다."""

    def list_documents(config, **kwargs):
        """준비된 목록을 돌려준다."""
        return list(documents)

    return list_documents


def failing_list(message: str):
    """list_documents 대신 OutlineError 를 던진다."""

    def list_documents(config, **kwargs):
        """항상 실패한다."""
        raise outline.OutlineError(message)

    return list_documents


def rendered_markdown(app) -> str:
    """화면의 markdown 요소를 한 문자열로 잇는다."""
    return " ".join(element.value for element in app.markdown)


def test_sync_area_is_drawn_without_any_run(app_db) -> None:
    """저장된 실행이 0건이어도 동기화 영역과 설정 안내가 나온다.

    DB 를 막 지운 직후가 이 기능이 가장 필요한 순간이다.
    """
    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    labels = [element.label for element in app.expander]
    assert "Outline 과 동기화" in labels
    messages = " ".join(element.value for element in app.info)
    assert outline.COLLECTION_ENV_VAR in messages
    assert "history_sync_check" not in [e.key for e in app.button]


def test_sync_check_button_appears_with_configuration(
    app_db, monkeypatch
) -> None:
    """설정이 있으면 확인 버튼이 나온다."""
    set_outline_env(monkeypatch)

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert "history_sync_check" in [e.key for e in app.button]


def test_sync_check_previews_the_counts_and_lists(
    app_db, monkeypatch
) -> None:
    """확인하면 개수 한 줄과 세 목록이 보이고 DB 는 그대로다."""
    set_outline_env(monkeypatch)
    gone = run_history.save_run(app_db, make_result())
    export(app_db, gone)
    monkeypatch.setattr(
        outline,
        "list_documents",
        fake_list([listed("new-1"), listed("skip-1", "본문만\n")]),
    )

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_sync_check").click().run()

    assert not app.exception
    text = rendered_markdown(app)
    assert "지울 이력 1건 · 만들 문서 1건 · 건너뛴 문서 1건" in text
    assert "정리한 제목" in text
    assert "문서 new-1" in text
    assert "문서 skip-1" in text
    assert history_sync.SKIP_NO_SOURCE_URL in text
    assert [run.id for run in run_history.list_exported(app_db)] == [gone]


def test_sync_apply_changes_the_db_and_reports(app_db, monkeypatch) -> None:
    """적용하면 지우고 만든 뒤 결과 문구를 낸다."""
    set_outline_env(monkeypatch)
    gone = run_history.save_run(app_db, make_result())
    export(app_db, gone)
    monkeypatch.setattr(outline, "list_documents", fake_list([listed("new-1")]))

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_sync_check").click().run()
    app.button(key="history_sync_apply").click().run()

    assert not app.exception
    ids = [run.outline_id for run in run_history.list_exported(app_db)]
    assert ids == ["new-1"]
    assert "지움 1건 · 만듦 1건" in app.success[0].value
    assert "history_sync_apply" not in [e.key for e in app.button]


def test_sync_cancel_drops_the_plan_only(app_db, monkeypatch) -> None:
    """취소하면 계획만 사라지고 DB 는 그대로다."""
    set_outline_env(monkeypatch)
    gone = run_history.save_run(app_db, make_result())
    export(app_db, gone)
    monkeypatch.setattr(outline, "list_documents", fake_list([]))

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_sync_check").click().run()
    app.button(key="history_sync_cancel").click().run()

    assert not app.exception
    assert "history_sync_apply" not in [e.key for e in app.button]
    assert [run.id for run in run_history.list_exported(app_db)] == [gone]


def test_sync_with_nothing_to_do_hides_the_apply_button(
    app_db, monkeypatch
) -> None:
    """이미 맞으면 적용 버튼이 없고 건너뛴 문서만 보인다."""
    set_outline_env(monkeypatch)
    run_id = run_history.save_run(app_db, make_result())
    export(app_db, run_id)
    monkeypatch.setattr(
        outline,
        "list_documents",
        fake_list([listed("doc-1"), listed("skip-1", "본문만\n")]),
    )

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_sync_check").click().run()

    assert not app.exception
    assert "history_sync_apply" not in [e.key for e in app.button]
    messages = " ".join(element.value for element in app.info)
    assert "이미 맞습니다" in messages
    assert "문서 skip-1" in rendered_markdown(app)


def test_sync_list_failure_shows_the_message(app_db, monkeypatch) -> None:
    """목록을 못 읽으면 문구만 내고 계획을 남기지 않는다."""
    set_outline_env(monkeypatch)
    monkeypatch.setattr(
        outline,
        "list_documents",
        failing_list("Outline 에 연결하지 못했습니다(ConnectError)."),
    )

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_sync_check").click().run()

    assert not app.exception
    assert "연결하지 못했습니다" in app.error[0].value
    assert "history_sync_apply" not in [e.key for e in app.button]


def test_sync_apply_failure_keeps_the_plan(app_db, monkeypatch) -> None:
    """적용이 죽으면 문구를 내고 계획은 남겨 다시 적용할 수 있다."""
    set_outline_env(monkeypatch)
    monkeypatch.setattr(outline, "list_documents", fake_list([listed("new-1")]))

    def boom(*args, **kwargs):
        """apply 가 실패하는 상황을 만든다."""
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(history_sync, "apply", boom)

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_sync_check").click().run()
    app.button(key="history_sync_apply").click().run()

    assert not app.exception
    assert "실패" in app.error[0].value
    assert "history_sync_apply" in [e.key for e in app.button]


def test_sync_apply_keeps_the_selected_run(app_db, monkeypatch) -> None:
    """지워지지 않은 실행을 고르고 있었으면 적용 뒤에도 그대로다.

    목록은 최신순이므로 나중에 만든 ``gone`` 이 0번, ``kept`` 가
    1번이다. 1번을 골라 두고 0번을 지운다.
    """
    set_outline_env(monkeypatch)
    kept = run_history.save_run(app_db, make_result(title="남는 실행"))
    gone = run_history.save_run(app_db, make_result())
    export(app_db, gone)
    monkeypatch.setattr(outline, "list_documents", fake_list([]))

    app = v1.AppTest.from_function(script)
    app.run()
    app.selectbox[0].select_index(1).run()
    assert app.selectbox[0].value == kept
    app.button(key="history_sync_check").click().run()
    app.button(key="history_sync_apply").click().run()

    assert not app.exception
    assert app.selectbox[0].value == kept
    assert [run.id for run in run_history.list_runs(app_db)] == [kept]


def test_sync_preview_survives_a_rerun(app_db, monkeypatch) -> None:
    """확인 뒤 다른 위젯을 건드려도 미리보기가 남아 있다."""
    set_outline_env(monkeypatch)
    run_history.save_run(app_db, make_result())
    monkeypatch.setattr(outline, "list_documents", fake_list([listed("new-1")]))

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_sync_check").click().run()
    app.checkbox[0].uncheck().run()

    assert not app.exception
    assert "history_sync_apply" in [e.key for e in app.button]
```

- [ ] **Step 3: 실패를 확인한다**

Run: `uv run pytest tests/pages/test_history.py -q -k sync`
Expected: FAIL — `test_sync_area_is_drawn_without_any_run` 은 expander
라벨이 없어 실패하고, 나머지는 `history_sync_check` 키의 버튼이 없어
실패한다.

- [ ] **Step 4: 화면 조각을 만든다**

`src/notebooklm_st/pages/_history_sync.py` 를 새로 만든다.

```python
"""이력 화면의 "Outline 과 동기화" 영역.

``pages/history.py`` 가 이 모듈을 부른다. 네비게이션에 직접 등록되지
않으므로 이름 앞에 밑줄을 둔다.

확인 → 미리보기 → 적용의 2단계다. 계획은 우리가 소유한 세션 키에
두고, 적용·취소 뒤 지운다. Outline 은 사람이 확인을 눌렀을 때만
읽는다 — Outline 이 죽어도 이력 화면은 뜬다.
"""

import sqlite3

import streamlit as st

from notebooklm_st.core import labels, models
from notebooklm_st.services import history_sync, outline, run_history

_PLAN_KEY = "history_sync_plan"
_RESULT_KEY = "history_sync_result"


def render(connection: sqlite3.Connection) -> None:
    """동기화 영역을 그린다.

    Args:
        connection: 열린 커넥션.
    """
    result = st.session_state.pop(_RESULT_KEY, None)
    if result is not None:
        st.success(result)
    with st.expander("Outline 과 동기화"):
        st.caption(
            "Outline 컬렉션의 문서 목록과 저장된 이력을 맞춥니다."
            " Outline 에 없는 이력은 지우고, 이력에 없는 문서는 새로"
            " 만듭니다."
        )
        config = outline.config_from_env()
        if config is None:
            st.info(
                "Outline 연결이 설정되지 않았습니다."
                f" {outline.URL_ENV_VAR}·{outline.TOKEN_ENV_VAR}"
                f"·{outline.COLLECTION_ENV_VAR} 를 설정하세요."
            )
            return
        if st.button("확인", key="history_sync_check"):
            _check(connection, config)
        sync_plan = st.session_state.get(_PLAN_KEY)
        if sync_plan is not None:
            _render_plan(connection, sync_plan)


def _check(
    connection: sqlite3.Connection, config: outline.OutlineConfig
) -> None:
    """목록을 읽어 계획을 세우고 세션에 담는다.

    실패하면 문구만 내고 계획은 남기지 않는다. 지난 계획이 남아 있으면
    실패한 뒤에도 적용 버튼이 보이게 되므로 함께 지운다.
    """
    try:
        documents = outline.list_documents(config)
    except outline.OutlineError as error:
        st.session_state.pop(_PLAN_KEY, None)
        st.error(str(error))
        return
    exported = run_history.list_exported(connection)
    st.session_state[_PLAN_KEY] = history_sync.plan(exported, documents)


def _render_plan(
    connection: sqlite3.Connection, sync_plan: models.SyncPlan
) -> None:
    """미리보기와 적용·취소 버튼을 그린다.

    expander 는 중첩할 수 없으므로 세 목록은 마크다운으로 그린다.
    """
    st.markdown(
        f"지울 이력 {len(sync_plan.deletes)}건"
        f" · 만들 문서 {len(sync_plan.creates)}건"
        f" · 건너뛴 문서 {len(sync_plan.skips)}건"
    )
    if sync_plan.deletes:
        st.markdown(
            "**지울 이력**\n"
            + "\n".join(
                f"- {labels.shorten(run.outline_title or run.video_id)}"
                f" · {run.created_at}"
                for run in sync_plan.deletes
            )
        )
    if sync_plan.creates:
        st.markdown(
            "**만들 문서**\n"
            + "\n".join(
                f"- {labels.shorten(create.document.title)}"
                f" · {create.document.created_at} · {create.url}"
                for create in sync_plan.creates
            )
        )
    if sync_plan.skips:
        st.markdown(
            "**건너뛴 문서**\n"
            + "\n".join(
                f"- {labels.shorten(skip.document.title)} · {skip.reason}"
                for skip in sync_plan.skips
            )
        )
    if sync_plan.is_empty:
        st.info(f"이미 맞습니다. 건너뛴 문서 {len(sync_plan.skips)}건.")
        return
    left, right = st.columns(2)
    if left.button("적용", key="history_sync_apply"):
        _apply(connection, sync_plan)
    if right.button("취소", key="history_sync_cancel"):
        st.session_state.pop(_PLAN_KEY, None)
        st.rerun()


def _apply(
    connection: sqlite3.Connection, sync_plan: models.SyncPlan
) -> None:
    """계획을 적용하고 결과 문구를 남긴 뒤 다시 그린다.

    실패하면 계획을 남긴다. 원인을 고친 뒤 같은 버튼을 다시 누르면
    된다.
    """
    try:
        result = history_sync.apply(connection, sync_plan)
    except sqlite3.Error as error:
        st.error(
            f"적용에 실패했습니다({type(error).__name__})."
            " 다시 적용할 수 있습니다."
        )
        return
    st.session_state.pop(_PLAN_KEY, None)
    st.session_state[_RESULT_KEY] = (
        f"동기화 완료 · 지움 {result.deleted}건 · 만듦 {result.created}건"
    )
    st.rerun()
```

- [ ] **Step 5: 이력 화면에 잇는다**

`src/notebooklm_st/pages/history.py` 의 import 를 바꾼다. 바꾸기 전.

```python
from notebooklm_st import session
from notebooklm_st.components import answer_view
from notebooklm_st.core import answer_text, labels, markdown_export, models
from notebooklm_st.services import outline, run_history
```

바꾼 뒤.

```python
from notebooklm_st import session
from notebooklm_st.components import answer_view
from notebooklm_st.core import answer_text, labels, markdown_export, models
from notebooklm_st.pages import _history_sync
from notebooklm_st.services import outline, run_history
```

`render` 의 앞부분을 바꾼다. 바꾸기 전.

```python
    st.title("이력")
    connection = session.get_connection()
    runs = run_history.list_runs(connection)
    if not runs:
        st.info("아직 저장된 실행이 없습니다.")
        return
```

바꾼 뒤.

```python
    st.title("이력")
    connection = session.get_connection()
    # 동기화는 "아직 저장된 실행이 없습니다" 보다 앞에 둔다. DB 를 막
    # 지운 직후가 이 기능이 가장 필요한 순간이다.
    _history_sync.render(connection)
    runs = run_history.list_runs(connection)
    if not runs:
        st.info("아직 저장된 실행이 없습니다.")
        return
```

- [ ] **Step 6: 통과를 확인한다**

Run: `uv run pytest tests/pages/test_history.py -q`
Expected: PASS — 새 테스트와 기존 테스트 모두. 기존 삭제 테스트들은
`app.button[0]` 을 쓰는데, 설정이 없으면 동기화 영역에 버튼이 없어
순서가 그대로다.

- [ ] **Step 7: 파일 길이를 확인한다**

Run: `wc -l src/notebooklm_st/pages/history.py src/notebooklm_st/pages/_history_sync.py`
Expected: 둘 다 300줄 이하.

- [ ] **Step 8: 검증 4단**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
```

- [ ] **Step 9: 커밋**

```bash
git add src/notebooklm_st/pages/_history_sync.py \
        src/notebooklm_st/pages/history.py \
        tests/pages/test_history.py
git commit -m "✨ feat(history): Outline 과 동기화 버튼과 미리보기"
```

---

### Task 8: README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: 없음
- Produces: 없음

- [ ] **Step 1: 사용 순서에 동기화를 더한다**

`README.md` "사용 순서" 의 5번 항목을 바꾼다. 바꾸기 전.

```
5. **이력** 화면에서 답변을 확인하고, 제목을 정한 뒤 **Outline 에 저장**합니다. 저장하면 로컬에는 문서명과 링크만 남고 수정·삭제·검색은 Outline 에서 합니다.
```

바꾼 뒤.

```
5. **이력** 화면에서 답변을 확인하고, 제목을 정한 뒤 **Outline 에 저장**합니다. 저장하면 로컬에는 문서명과 링크만 남고 수정·삭제·검색은 Outline 에서 합니다. 화면 위의 **Outline 과 동기화**는 저장된 이력과 Outline 컬렉션의 문서 목록을 맞춥니다. **확인**을 누르면 지울 이력·만들 문서·건너뛴 문서를 먼저 보여 주고, **적용**을 눌러야 바뀝니다. Outline 에 없는 이력은 링크만 지우고, 이력에 없는 문서는 본문의 영상 URL 로 이력을 되살립니다. 영상 URL 줄이 없는 문서(정리본, 직접 쓴 글)는 건너뜁니다. Outline 휴지통에 있는 문서는 없는 것으로 봅니다. 같은 영상의 문서가 둘이면 둘 다 이력이 되며 합치지 않습니다.
```

- [ ] **Step 2: DB 삭제 주의 문구를 보완한다**

"데이터 저장 위치" 의 주의 문단을 바꾼다. 바꾸기 전.

```
> **주의**: 이 프로젝트는 DB 마이그레이션을 지원하지 않습니다(의도된 결정). 스키마가 바뀌면 앱이 연결 시점에 안내와 함께 멈추며, 해결책은 DB 파일을 지우고 새로 만드는 것뿐입니다. 이때 질문 템플릿과 실행 이력이 함께 사라집니다. Outline 에 이미 올린 문서는 영향을 받지 않습니다.
```

바꾼 뒤.

```
> **주의**: 이 프로젝트는 DB 마이그레이션을 지원하지 않습니다(의도된 결정). 스키마가 바뀌면 앱이 연결 시점에 안내와 함께 멈추며, 해결책은 DB 파일을 지우고 새로 만드는 것뿐입니다. 이때 질문 템플릿·채널 등록·실행 이력이 함께 사라집니다. Outline 에 이미 올린 문서는 영향을 받지 않으며, 저장된 이력은 이력 화면의 **Outline 과 동기화**로 되살릴 수 있습니다. 미저장 실행·질문 템플릿·채널 등록은 되살릴 수 없습니다.
```

- [ ] **Step 3: 커밋**

```bash
git add README.md
git commit -m "📝 docs(readme): 이력 동기화의 쓰임과 한계 적기"
```

---

## 마무리 확인

모든 Task 뒤에 한 번 더 전체를 돌린다.

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
```

그리고 명세 12장의 "변경 없음" 목록이 지켜졌는지 본다.

```bash
git diff --stat fc0919a..HEAD -- src/notebooklm_st/services/store.py \
    src/notebooklm_st/services/runner.py \
    src/notebooklm_st/services/digest.py \
    src/notebooklm_st/services/channels.py \
    docker-compose.yml Dockerfile pyproject.toml
```

Expected: 출력 없음.
