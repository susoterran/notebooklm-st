# 채널 구독·신규 감지 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 즐겨찾기 채널을 등록해 두고, 버튼 한 번으로 "아직 요약하지
않은 새 영상" 목록을 받아 그 자리에서 요약을 시작한다.

**Architecture:** 감지 소스가 둘로 갈린다 — 등록할 때 한 번 yt-dlp 로
채널 URL 을 `channel_id` 로 해석하고, 확인할 때마다 채널 RSS 피드를
HTTP 한 번으로 읽는다. 신규 판정은 I/O 를 모르는 순수 함수
(`core/new_videos.py`)가 하고, 실행은 기존 `runner.start_run` 을 그대로
부른다. 실행 모델(`RunRegistry`·가드)은 건드리지 않는다.

**Tech Stack:** Python 3.13 · Streamlit · SQLite(sqlite3) · httpx ·
yt-dlp(자식 프로세스) · `xml.etree.ElementTree` · pytest ·
`streamlit.testing.v1.AppTest` · ruff · mypy. **새 의존성 없음.**

**Spec:** `docs/superpowers/specs/2026-09-23-channel-watch-design.md`

## Global Constraints

- 줄 길이 최대 **80자**. 들여쓰기 스페이스 4칸.
- 모든 모듈·클래스·함수에 **한국어 Google 형식 독스트링**. 독스트링과
  주석은 72자에서 줄바꿈.
- **모듈 단위 import 만** 쓴다. `from x import name` 금지(예외:
  `typing`·`collections.abc`).
- `core/` 와 `services/` 에서 **`import streamlit` 금지**. `core/` 는
  `services/` 를 import 하지 않는다.
- 모든 함수에 타입 힌트. 반환 없으면 `-> None`. `list[str]`·`str |
  None` 형식(구 `typing.List`·`Optional` 금지).
- 값 묶음은 `@dataclasses.dataclass(frozen=True, slots=True)`.
- 테스트는 `tests/` 에 `src/notebooklm_st` 구조를 미러링.
- 외부 네트워크·DB·자식 프로세스는 **반드시 가짜로** 대체. 실제 호출을
  하는 테스트를 추가하지 않는다.
- 새 의존성을 추가하지 않는다.
- **검증 4단을 순서대로 통과해야 완료다.**
  ```
  uv run ruff format .
  uv run ruff check --fix .
  uv run mypy src tests
  uv run pytest
  ```
  `uv` 가 PATH 에 없으면 전체 경로로 부른다(이 기기에서는
  `~/.local/bin/uv.exe`).
- 커밋은 gitmoji + Conventional Commits, 제목은 한국어 명령형 50자
  이내, 마지막 줄에 `Assisted-by: <모델 ID>`. `git push` 하지 않는다.

## 파일 구조

| 파일 | 책임 |
| --- | --- |
| `core/youtube.py`(수정) | 영상 ID → 시청 URL 짓기를 한 곳으로 |
| `core/models.py`(수정) | 값 객체 `Channel`·`FeedEntry` |
| `core/new_videos.py`(신규) | 신규 판정. I/O 를 모른다 |
| `services/store.py`(수정) | `channels` 스키마와 기대 컬럼 |
| `services/channels.py`(신규) | 구독 CRUD. SQLite 만 안다 |
| `services/run_history.py`(수정) | 이미 요약한 영상 ID 집합 |
| `services/channel_feed.py`(신규) | RSS 피드. httpx 만 안다 |
| `services/channel_lookup.py`(신규) | 채널 URL 해석. yt-dlp 만 안다 |
| `pages/channels.py`(신규) | 화면. 위의 것들을 잇고 렌더만 한다 |
| `app.py`(수정) | 네비게이션에 채널 페이지 |
| `README.md`(수정) | 사용 순서에 채널 화면 |

**모듈 이름이 겹친다.** `pages/channels.py` 안에서 `channels` 는
`services/channels` 를 가리킨다(페이지는 자기 자신을 import 하지
않는다). `app.py` 안에서 `channels` 는 `pages/channels` 다. 헷갈리지
말 것.

---

### Task 1: 시청 URL 짓기를 한 곳으로

**Files:**
- Modify: `src/notebooklm_st/core/youtube.py`
- Modify: `src/notebooklm_st/core/markdown_export.py`(`_source_url` 본문)
- Test: `tests/core/test_youtube.py`

**Interfaces:**
- Consumes: 없음
- Produces: `youtube.watch_url(video_id: str) -> str`

신규 목록이 영상 URL 을 지어야 한다. 같은 f-string 이
`markdown_export._source_url` 에 이미 있으므로 세 번째를 만들지 않고
여기로 모은다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/core/test_youtube.py` 끝에 더한다.

```python
def test_watch_url_builds_the_canonical_form():
    """영상 ID 로 정규 시청 URL 을 짓는다."""
    assert (
        youtube.watch_url("dQw4w9WgXcQ")
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/core/test_youtube.py -q`
Expected: FAIL — `AttributeError: module 'notebooklm_st.core.youtube' has
no attribute 'watch_url'`

- [ ] **Step 3: 함수를 더한다**

`src/notebooklm_st/core/youtube.py` 의 `is_valid` 다음, `_validated`
앞에 넣는다.

```python
def watch_url(video_id: str) -> str:
    """영상 ID 로 정규 시청 URL 을 짓는다.

    저장된 원문 URL 에는 재생목록·추적 파라미터가 붙어 있을 수 있다.
    문서에 적을 링크와 화면에 보여 줄 링크가 같은 모양이어야 하므로
    ID 로 다시 짓는다.

    Args:
        video_id: 11자리 영상 ID.

    Returns:
        ``https://www.youtube.com/watch?v=<ID>`` 형식의 URL.
    """
    return f"https://www.youtube.com/watch?v={video_id}"
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/core/test_youtube.py -q`
Expected: PASS

- [ ] **Step 5: 기존 중복을 이 함수로 바꾼다**

`src/notebooklm_st/core/markdown_export.py` 의 import 줄을 바꾼다.

```python
from notebooklm_st.core import models, youtube
```

같은 파일 `_source_url` 의 본문을 바꾼다. 바꾸기 전 모습은 이렇다.

```python
    if summary.video_id:
        return f"https://www.youtube.com/watch?v={summary.video_id}"
    return one_line(summary.url)
```

바꾼 뒤.

```python
    if summary.video_id:
        return youtube.watch_url(summary.video_id)
    return one_line(summary.url)
```

- [ ] **Step 6: 기존 테스트가 그대로 통과하는지 확인한다**

Run: `uv run pytest tests/core/test_markdown_export.py -q`
Expected: PASS — 이 파일이 URL 문자열을 이미 단언하고 있어 회귀
방지 역할을 한다. 새 테스트를 더하지 않는다.

- [ ] **Step 7: 검증 4단**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
```

- [ ] **Step 8: 커밋**

```bash
git add src/notebooklm_st/core/youtube.py \
        src/notebooklm_st/core/markdown_export.py \
        tests/core/test_youtube.py
git commit -m "♻️ refactor(youtube): 시청 URL 짓기를 한 곳으로 모으기"
```

---

### Task 2: 신규 판정 순수 함수

**Files:**
- Modify: `src/notebooklm_st/core/models.py`
- Create: `src/notebooklm_st/core/new_videos.py`
- Test: `tests/core/test_new_videos.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `models.Channel(id: int, channel_id: str, title: str, url: str,
    baseline: str, created_at: str)`
  - `models.FeedEntry(video_id: str, title: str,
    published: datetime.datetime)`
  - `new_videos.select(entries: Sequence[models.FeedEntry],
    baseline: str, known_ids: Container[str],
    tz: datetime.tzinfo | None = None) -> tuple[models.FeedEntry, ...]`

이 함수가 이 기능의 심장이다. **타임존 경계가 요점이다** — 피드는
UTC 로 주고 사람은 로컬 날짜로 생각한다.

- [ ] **Step 1: 값 객체를 더한다**

`src/notebooklm_st/core/models.py` 맨 위 import 에 `datetime` 을
더한다. 현재는 이렇다.

```python
import dataclasses
import json
from collections.abc import Sequence
```

바꾼 뒤.

```python
import dataclasses
import datetime
import json
from collections.abc import Sequence
```

같은 파일에서 `Question` 클래스 **바로 뒤**에 두 클래스를 더한다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class Channel:
    """구독 중인 채널 하나."""

    id: int
    channel_id: str
    """``UC`` 로 시작하는 YouTube 채널 ID."""
    title: str
    url: str
    baseline: str
    """``YYYY-MM-DD``. 이 날짜 이후 업로드만 신규로 본다."""
    created_at: str


@dataclasses.dataclass(frozen=True, slots=True)
class FeedEntry:
    """채널 피드의 항목 하나.

    채널이 어느 것인지는 담지 않는다. 호출자가 채널마다 따로 읽어
    쓰므로 중복이 된다.
    """

    video_id: str
    title: str
    published: datetime.datetime
    """타임존이 붙은 시각. 피드가 UTC 로 준다."""
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/core/test_new_videos.py` 를 만든다.

```python
"""신규 영상 판정 테스트."""

import datetime

import pytest

from notebooklm_st.core import models, new_videos

KST = datetime.timezone(datetime.timedelta(hours=9))


def entry(video_id: str, published: str, title: str = "영상") -> models.FeedEntry:
    """피드 항목 하나를 만든다. ``published`` 는 ISO 문자열이다."""
    return models.FeedEntry(
        video_id=video_id,
        title=title,
        published=datetime.datetime.fromisoformat(published),
    )


def test_keeps_an_entry_uploaded_after_the_baseline():
    """기준일보다 나중에 올라온 영상은 신규다."""
    entries = [entry("aaaaaaaaaaa", "2026-09-24T01:00:00+00:00")]

    picked = new_videos.select(entries, "2026-09-23", set(), KST)

    assert [item.video_id for item in picked] == ["aaaaaaaaaaa"]


def test_drops_an_entry_uploaded_before_the_baseline():
    """기준일보다 먼저 올라온 영상은 신규가 아니다."""
    entries = [entry("aaaaaaaaaaa", "2026-09-20T01:00:00+00:00")]

    assert new_videos.select(entries, "2026-09-23", set(), KST) == ()


def test_the_baseline_starts_at_midnight_in_the_given_zone():
    """기준일 00:00 은 주어진 타임존의 자정이다.

    KST 기준일 2026-09-23 의 시작은 UTC 2026-09-22T15:00 이다. 그
    직후에 올라온 영상은 한국 시각으로 그날 새벽이므로 신규다.
    """
    entries = [entry("aaaaaaaaaaa", "2026-09-22T15:30:00+00:00")]

    picked = new_videos.select(entries, "2026-09-23", set(), KST)

    assert [item.video_id for item in picked] == ["aaaaaaaaaaa"]


def test_an_entry_just_before_the_zone_midnight_is_dropped():
    """그 자정 직전에 올라온 것은 전날이라 신규가 아니다."""
    entries = [entry("aaaaaaaaaaa", "2026-09-22T14:30:00+00:00")]

    assert new_videos.select(entries, "2026-09-23", set(), KST) == ()


def test_drops_an_entry_already_summarized():
    """이미 요약한 영상은 빠진다."""
    entries = [entry("aaaaaaaaaaa", "2026-09-24T01:00:00+00:00")]

    picked = new_videos.select(entries, "2026-09-23", {"aaaaaaaaaaa"}, KST)

    assert picked == ()


def test_sorts_newest_first():
    """업로드가 늦은 것부터 나온다."""
    entries = [
        entry("aaaaaaaaaaa", "2026-09-24T01:00:00+00:00"),
        entry("ccccccccccc", "2026-09-26T01:00:00+00:00"),
        entry("bbbbbbbbbbb", "2026-09-25T01:00:00+00:00"),
    ]

    picked = new_videos.select(entries, "2026-09-23", set(), KST)

    assert [item.video_id for item in picked] == [
        "ccccccccccc",
        "bbbbbbbbbbb",
        "aaaaaaaaaaa",
    ]


def test_empty_entries_give_nothing():
    """항목이 없으면 빈 결과다."""
    assert new_videos.select([], "2026-09-23", set(), KST) == ()


def test_rejects_a_baseline_that_is_not_a_date():
    """기준일 형식이 아니면 예외다."""
    with pytest.raises(ValueError):
        new_videos.select([], "2026/09/23", set(), KST)
```

- [ ] **Step 3: 실패를 확인한다**

Run: `uv run pytest tests/core/test_new_videos.py -q`
Expected: 수집 단계에서 FAIL — `ImportError: cannot import name
'new_videos' from 'notebooklm_st.core'`

- [ ] **Step 4: 최소 구현을 쓴다**

`src/notebooklm_st/core/new_videos.py` 를 만든다.

```python
"""새 영상을 고르는 순수 함수.

피드에서 온 항목과 기준일과 이미 요약한 영상 ID 를 받아 거르고
정렬한다. 네트워크도 DB 도 Streamlit 도 모른다 — 그래서 경계 조건을
가짜 없이 테스트할 수 있다.
"""

import datetime
from collections.abc import Container, Sequence

from notebooklm_st.core import models


def select(
    entries: Sequence[models.FeedEntry],
    baseline: str,
    known_ids: Container[str],
    tz: datetime.tzinfo | None = None,
) -> tuple[models.FeedEntry, ...]:
    """기준일 이후 올라왔고 아직 요약하지 않은 항목만 고른다.

    Args:
        entries: 채널 피드에서 온 항목들.
        baseline: ``YYYY-MM-DD`` 형식의 기준일. 저장소가 형식을
            보장한다(→ ``services.channels``).
        known_ids: 이미 요약한 영상 ID 들.
        tz: 기준일을 읽을 타임존. ``None`` 이면 시스템 로컬을 쓴다 —
            컨테이너는 ``TZ=Asia/Seoul`` 로 돈다.

    Returns:
        업로드가 늦은 것부터 정렬한 항목들.

    Raises:
        ValueError: ``baseline`` 이 날짜로 읽히지 않는 경우.
    """
    start = _start_of_day(baseline, tz)
    picked = [
        item
        for item in entries
        if item.published >= start and item.video_id not in known_ids
    ]
    picked.sort(key=lambda item: item.published, reverse=True)
    return tuple(picked)


def _start_of_day(
    baseline: str, tz: datetime.tzinfo | None
) -> datetime.datetime:
    """기준일의 자정을 타임존이 붙은 시각으로 만든다.

    피드는 UTC 로 오고 사람은 로컬 날짜로 생각한다. naive 로
    비교하면 그 차이만큼 경계가 밀려, 한국 시각 새벽에 올라온 영상이
    하루 어긋나 잡힌다. 문자열을 자르는 비교도 같은 이유로 쓰지
    않는다.

    Args:
        baseline: ``YYYY-MM-DD`` 형식의 기준일.
        tz: 읽을 타임존. ``None`` 이면 시스템 로컬.

    Returns:
        타임존이 붙은 그날 00:00.

    Raises:
        ValueError: 날짜로 읽히지 않는 경우.
    """
    day = datetime.date.fromisoformat(baseline)
    naive = datetime.datetime.combine(day, datetime.time())
    if tz is None:
        # naive.astimezone() 은 시스템 로컬로 읽어 aware 로 바꾼다.
        return naive.astimezone()
    return naive.replace(tzinfo=tz)
```

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/core/test_new_videos.py -q`
Expected: PASS (8건)

- [ ] **Step 6: 검증 4단**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
```

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/core/models.py \
        src/notebooklm_st/core/new_videos.py \
        tests/core/test_new_videos.py
git commit -m "✨ feat(channels): 새 영상 판정 순수 함수 더하기"
```

---

### Task 3: 구독 저장소와 스키마

**Files:**
- Modify: `src/notebooklm_st/services/store.py:17-91`
- Create: `src/notebooklm_st/services/channels.py`
- Test: `tests/services/test_channels.py`
- Test: `tests/services/test_store.py`

**Interfaces:**
- Consumes: `models.Channel`(Task 2)
- Produces:
  - `channels.list_channels(connection) -> list[models.Channel]`
  - `channels.add_channel(connection, channel_id: str, title: str,
    url: str, baseline: str) -> models.Channel`
  - `channels.update_baseline(connection, channel_pk: int,
    baseline: str) -> None`
  - `channels.delete_channel(connection, channel_pk: int) -> None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_channels.py` 를 만든다.

```python
"""구독 채널 저장소 테스트."""

import pytest

from notebooklm_st.services import channels, store


@pytest.fixture
def connection(tmp_path):
    """임시 DB에 연결한 커넥션을 제공한다."""
    conn = store.connect(tmp_path / "test.db")
    yield conn
    conn.close()


def add(connection, channel_id="UC" + "a" * 22, title="어떤 채널"):
    """테스트용 채널 하나를 등록한다."""
    return channels.add_channel(
        connection,
        channel_id,
        title,
        f"https://www.youtube.com/channel/{channel_id}",
        "2026-09-23",
    )


def test_new_database_has_no_channels(connection) -> None:
    """새 DB 는 채널이 없다."""
    assert channels.list_channels(connection) == []


def test_add_channel_returns_the_saved_row(connection) -> None:
    """등록한 채널이 그대로 저장되어 돌아온다."""
    saved = add(connection)

    assert saved.id > 0
    assert saved.channel_id == "UC" + "a" * 22
    assert saved.title == "어떤 채널"
    assert saved.baseline == "2026-09-23"
    assert saved.created_at


def test_channels_are_listed_by_title(connection) -> None:
    """목록은 이름순이다."""
    add(connection, channel_id="UC" + "b" * 22, title="나중 채널")
    add(connection, channel_id="UC" + "a" * 22, title="가장 먼저")

    titles = [item.title for item in channels.list_channels(connection)]

    assert titles == ["가장 먼저", "나중 채널"]


def test_the_same_channel_cannot_be_registered_twice(connection) -> None:
    """같은 채널 ID 는 한 번만 등록된다."""
    add(connection)

    with pytest.raises(ValueError) as error:
        add(connection, title="다른 이름")

    assert "이미 등록된" in str(error.value)


def test_blank_values_are_rejected(connection) -> None:
    """빈 값은 저장하지 않는다."""
    with pytest.raises(ValueError):
        channels.add_channel(
            connection, "  ", "이름", "https://example.com", "2026-09-23"
        )


def test_a_malformed_baseline_is_rejected(connection) -> None:
    """기준일 형식이 아니면 저장하지 않는다."""
    with pytest.raises(ValueError):
        channels.add_channel(
            connection,
            "UC" + "a" * 22,
            "이름",
            "https://example.com",
            "2026/09/23",
        )


def test_update_baseline_changes_the_date(connection) -> None:
    """기준일을 고칠 수 있다."""
    saved = add(connection)

    channels.update_baseline(connection, saved.id, "2026-01-01")

    assert channels.list_channels(connection)[0].baseline == "2026-01-01"


def test_update_baseline_rejects_an_unknown_channel(connection) -> None:
    """없는 채널의 기준일은 고칠 수 없다."""
    with pytest.raises(ValueError):
        channels.update_baseline(connection, 999, "2026-01-01")


def test_delete_channel_removes_it(connection) -> None:
    """지우면 목록에서 사라진다."""
    saved = add(connection)

    channels.delete_channel(connection, saved.id)

    assert channels.list_channels(connection) == []


def test_deleting_a_missing_channel_is_quiet(connection) -> None:
    """이미 없는 채널을 지워도 예외가 아니다."""
    channels.delete_channel(connection, 999)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/services/test_channels.py -q`
Expected: 수집 단계에서 FAIL — `ImportError: cannot import name
'channels' from 'notebooklm_st.services'`

- [ ] **Step 3: 스키마를 더한다**

`src/notebooklm_st/services/store.py` 의 `_SCHEMA` 안, `run_metadata`
블록 **뒤**(닫는 `"""` 앞)에 더한다.

```sql
CREATE TABLE IF NOT EXISTS channels (
    id         INTEGER PRIMARY KEY,
    channel_id TEXT NOT NULL UNIQUE,
    title      TEXT NOT NULL,
    url        TEXT NOT NULL,
    baseline   TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

같은 파일 `_EXPECTED_COLUMNS` 의 `"run_metadata"` 항목 뒤에 더한다.

```python
    "channels": frozenset(
        {"id", "channel_id", "title", "url", "baseline", "created_at"}
    ),
```

- [ ] **Step 4: 저장소를 쓴다**

`src/notebooklm_st/services/channels.py` 를 만든다.

```python
"""구독 채널 저장소.

연결과 스키마는 ``store`` 가 맡는다. ``questions`` 와 같은 모양이다 —
SQLite 만 알고 네트워크도 Streamlit 도 모른다.
"""

import datetime
import sqlite3

from notebooklm_st.core import models
from notebooklm_st.services import store

_COLUMNS = "id, channel_id, title, url, baseline, created_at"

_BASELINE_LENGTH = len("2026-09-23")


def list_channels(connection: sqlite3.Connection) -> list[models.Channel]:
    """등록된 채널을 이름순으로 돌려준다.

    등록 순서가 아니라 이름순이다. 채널은 이름으로 찾는다.

    Args:
        connection: 열린 커넥션.

    Returns:
        채널 목록.
    """
    rows = connection.execute(
        f"SELECT {_COLUMNS} FROM channels ORDER BY title"
    ).fetchall()
    return [_to_channel(row) for row in rows]


def add_channel(
    connection: sqlite3.Connection,
    channel_id: str,
    title: str,
    url: str,
    baseline: str,
) -> models.Channel:
    """채널을 등록한다.

    Args:
        connection: 열린 커넥션.
        channel_id: ``UC`` 로 시작하는 채널 ID. 중복을 허용하지
            않는다.
        title: 화면에 보여 줄 채널명.
        url: 사람이 누를 채널 주소.
        baseline: ``YYYY-MM-DD`` 형식의 기준일.

    Returns:
        저장된 채널.

    Raises:
        ValueError: 값이 공백뿐이거나, 기준일이 형식에 맞지 않거나,
            같은 채널이 이미 등록된 경우.
    """
    values = {
        "채널 ID": channel_id.strip(),
        "채널명": title.strip(),
        "채널 URL": url.strip(),
    }
    for subject, value in values.items():
        if not value:
            raise ValueError(f"{subject} 값이 비어 있습니다.")
    checked = _require_date(baseline)
    if _exists(connection, values["채널 ID"]):
        raise ValueError("이미 등록된 채널입니다.")
    row = connection.execute(
        "INSERT INTO channels"
        " (channel_id, title, url, baseline, created_at)"
        " VALUES (?, ?, ?, ?, ?)"
        f" RETURNING {_COLUMNS}",
        (
            values["채널 ID"],
            values["채널명"],
            values["채널 URL"],
            checked,
            store.now(),
        ),
    ).fetchone()
    connection.commit()
    return _to_channel(row)


def update_baseline(
    connection: sqlite3.Connection, channel_pk: int, baseline: str
) -> None:
    """채널의 기준일을 바꾼다.

    Args:
        connection: 열린 커넥션.
        channel_pk: 바꿀 채널의 행 ID.
        baseline: ``YYYY-MM-DD`` 형식의 새 기준일.

    Raises:
        ValueError: 기준일이 형식에 맞지 않거나 그 채널이 없는 경우.
    """
    checked = _require_date(baseline)
    cursor = connection.execute(
        "UPDATE channels SET baseline = ? WHERE id = ?",
        (checked, channel_pk),
    )
    connection.commit()
    if cursor.rowcount == 0:
        raise ValueError(f"채널 {channel_pk} 을 찾을 수 없습니다.")


def delete_channel(connection: sqlite3.Connection, channel_pk: int) -> None:
    """채널을 지운다. 이미 없으면 조용히 넘어간다.

    이미 만든 요약본과 실행 이력은 그대로 남는다.

    Args:
        connection: 열린 커넥션.
        channel_pk: 지울 채널의 행 ID.
    """
    connection.execute("DELETE FROM channels WHERE id = ?", (channel_pk,))
    connection.commit()


def _exists(connection: sqlite3.Connection, channel_id: str) -> bool:
    """같은 채널 ID 가 이미 있는지 알려준다.

    DB 의 ``UNIQUE`` 가 마지막 방어선이고, 화면에 보여 줄 문장은 이
    검사가 있어야 만들 수 있다.

    Args:
        connection: 열린 커넥션.
        channel_id: 이미 공백을 지운 채널 ID.

    Returns:
        있으면 참.
    """
    row = connection.execute(
        "SELECT 1 FROM channels WHERE channel_id = ? LIMIT 1",
        (channel_id,),
    ).fetchone()
    return row is not None


def _require_date(value: str) -> str:
    """``YYYY-MM-DD`` 형식인지 확인하고 공백을 지워 돌려준다.

    저장소가 형식을 지키면 ``core.new_videos`` 가 형식을 다시
    의심하지 않아도 된다. ``date.fromisoformat`` 은 ``20260923`` 같은
    다른 ISO 형식도 받으므로 길이를 함께 본다.

    Args:
        value: 검사할 기준일.

    Returns:
        공백을 지운 기준일.

    Raises:
        ValueError: 형식에 맞지 않는 경우.
    """
    stripped = value.strip()
    if len(stripped) != _BASELINE_LENGTH:
        raise ValueError(f"기준일이 YYYY-MM-DD 형식이 아닙니다: {stripped!r}")
    try:
        datetime.date.fromisoformat(stripped)
    except ValueError:
        raise ValueError(
            f"기준일이 YYYY-MM-DD 형식이 아닙니다: {stripped!r}"
        ) from None
    return stripped


def _to_channel(row: sqlite3.Row) -> models.Channel:
    """DB 행을 ``Channel`` 로 바꾼다."""
    return models.Channel(
        id=int(row["id"]),
        channel_id=row["channel_id"],
        title=row["title"],
        url=row["url"],
        baseline=row["baseline"],
        created_at=row["created_at"],
    )
```

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/services/test_channels.py -q`
Expected: PASS (10건)

- [ ] **Step 6: 옛 DB 가 그대로 열린다는 테스트를 더한다**

새 테이블이 DB 삭제를 부르지 않는다는 것이 이 릴리스의 전제다
(스펙 §2.3). `tests/services/test_store.py` 끝에 더한다.

```python
def test_a_database_without_channels_still_opens(tmp_path) -> None:
    """channels 가 없는 옛 DB 도 그대로 열린다.

    새 테이블은 CREATE TABLE IF NOT EXISTS 가 만들어 주므로 사용자가
    questions.db 를 지울 필요가 없다. 기존 테이블에 컬럼을 더할 때만
    삭제가 강제된다.
    """
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE questions ("
        " id INTEGER PRIMARY KEY, title TEXT NOT NULL, text TEXT NOT NULL,"
        " created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
    )
    old.commit()
    old.close()

    connection = store.connect(path)
    try:
        assert channels.list_channels(connection) == []
    finally:
        connection.close()
```

`tests/services/test_store.py` 는 이미 `import sqlite3` 를 하고 있고
import 줄이 `from notebooklm_st.services import store` 다. 그 줄을
바꾼다.

```python
from notebooklm_st.services import channels, store
```

- [ ] **Step 7: 통과를 확인한다**

Run: `uv run pytest tests/services/test_store.py -q`
Expected: PASS

- [ ] **Step 8: 검증 4단**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
```

- [ ] **Step 9: 커밋**

```bash
git add src/notebooklm_st/services/store.py \
        src/notebooklm_st/services/channels.py \
        tests/services/test_channels.py tests/services/test_store.py
git commit -m "✨ feat(channels): 구독 채널 저장소와 스키마 더하기"
```

---

### Task 4: 이미 요약한 영상 ID 집합

**Files:**
- Modify: `src/notebooklm_st/services/run_history.py`
- Test: `tests/services/test_run_history.py`

**Interfaces:**
- Consumes: 없음
- Produces: `run_history.list_video_ids(connection) -> set[str]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_run_history.py` 끝에 더한다. 이 파일에는 이미
`connection` fixture 와 `make_result(url, title)` 헬퍼가 있고
`models`·`run_history`·`store` 를 import 한다. 그것을 그대로 쓴다
(`make_result` 는 `video_id` 를 `"dQw4w9WgXcQ"` 로 박아 두므로, 빈 ID
가 필요한 테스트만 `models.RunResult` 를 직접 만든다).

```python
def test_list_video_ids_returns_saved_ids(connection) -> None:
    """저장된 영상 ID 를 모두 돌려준다."""
    run_history.save_run(connection, make_result(title="하나"))

    assert run_history.list_video_ids(connection) == {"dQw4w9WgXcQ"}


def test_list_video_ids_drops_empty_ids(connection) -> None:
    """ID 를 못 뽑은 옛 실행의 빈 문자열은 빠진다.

    빈 문자열이 집합에 섞이면 ID 가 빈 피드 항목과 엉뚱하게
    맞부딪힌다.
    """
    run_history.save_run(
        connection,
        models.RunResult(
            url="https://example.com/not-youtube",
            video_id="",
            title="옛 실행",
            items=(),
        ),
    )

    assert run_history.list_video_ids(connection) == set()


def test_list_video_ids_deduplicates(connection) -> None:
    """같은 영상을 두 번 요약해도 하나로 온다."""
    for _ in range(2):
        run_history.save_run(connection, make_result(title="둘"))

    assert run_history.list_video_ids(connection) == {"dQw4w9WgXcQ"}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/services/test_run_history.py -q`
Expected: FAIL — `AttributeError: module
'notebooklm_st.services.run_history' has no attribute 'list_video_ids'`

- [ ] **Step 3: 함수를 더한다**

`src/notebooklm_st/services/run_history.py` 의 `save_run` **앞**,
import 다음에 넣는다.

```python
def list_video_ids(connection: sqlite3.Connection) -> set[str]:
    """이력에 남은 영상 ID 를 모두 돌려준다.

    빈 문자열은 뺀다. ``video_id`` 는
    ``youtube.extract_video_id(url) or ""`` 로 채워지므로 ID 를 못
    뽑은 옛 실행은 빈 문자열을 가진다. 그것이 집합에 섞이면 ID 가
    빈 피드 항목과 엉뚱하게 맞부딪힌다.

    Args:
        connection: 열린 커넥션.

    Returns:
        요약한 적이 있는 영상 ID 집합.
    """
    rows = connection.execute(
        "SELECT DISTINCT video_id FROM runs WHERE video_id <> ''"
    ).fetchall()
    return {row["video_id"] for row in rows}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/services/test_run_history.py -q`
Expected: PASS

- [ ] **Step 5: 검증 4단 + 커밋**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
git add src/notebooklm_st/services/run_history.py \
        tests/services/test_run_history.py
git commit -m "✨ feat(history): 요약한 영상 ID 집합 조회 더하기"
```

---

### Task 5: 채널 RSS 피드 읽기

**Files:**
- Create: `src/notebooklm_st/services/channel_feed.py`
- Test: `tests/services/test_channel_feed.py`

**Interfaces:**
- Consumes: `models.FeedEntry`(Task 2)
- Produces:
  - `channel_feed.FeedResult(entries: tuple[models.FeedEntry, ...],
    error: str | None)`
  - `channel_feed.fetch(channel_id: str, getter: GetLike = httpx.get,
    timeout: float = FETCH_TIMEOUT) -> FeedResult`
  - 상수 `FEED_URL`, `FETCH_TIMEOUT`, `MAX_FEED_BYTES`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_channel_feed.py` 를 만든다.

```python
"""채널 RSS 피드 읽기 테스트 — 실제 네트워크를 타지 않는다."""

import datetime

import httpx

from notebooklm_st.services import channel_feed

CHANNEL_ID = "UCsBjURrPoezykLs9EqgamOA"

FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Fireship</title>
  <entry>
    <yt:videoId>TbkUKCm3CHQ</yt:videoId>
    <title>첫 영상</title>
    <published>2026-09-21T17:52:29+00:00</published>
  </entry>
  <entry>
    <yt:videoId>LoLYw--s-5w</yt:videoId>
    <title>둘째 영상</title>
    <published>2026-09-17T20:33:55+00:00</published>
  </entry>
</feed>
"""


def responder(status=200, text=FEED_XML):
    """고정 응답을 돌려주는 가짜 getter 를 만든다."""

    def getter(url, **kwargs):
        """호출을 기록하지 않고 준비된 응답만 돌려준다."""
        return httpx.Response(status, text=text)

    return getter


def test_entries_come_back_with_id_title_and_time():
    """항목마다 ID·제목·시각을 읽는다."""
    result = channel_feed.fetch(CHANNEL_ID, getter=responder())

    assert result.error is None
    assert [item.video_id for item in result.entries] == [
        "TbkUKCm3CHQ",
        "LoLYw--s-5w",
    ]
    assert result.entries[0].title == "첫 영상"
    assert result.entries[0].published == datetime.datetime(
        2026, 9, 21, 17, 52, 29, tzinfo=datetime.timezone.utc
    )


def test_the_channel_id_goes_into_the_query():
    """채널 ID 를 질의 파라미터로 넘긴다."""
    seen = {}

    def getter(url, **kwargs):
        """넘어온 URL 과 파라미터를 기록한다."""
        seen["url"] = url
        seen["params"] = kwargs.get("params")
        return httpx.Response(200, text=FEED_XML)

    channel_feed.fetch(CHANNEL_ID, getter=getter)

    assert seen["url"] == channel_feed.FEED_URL
    assert seen["params"] == {"channel_id": CHANNEL_ID}


def test_missing_feed_says_the_channel_has_none():
    """404 는 피드가 없는 채널이라고 말한다."""
    result = channel_feed.fetch(CHANNEL_ID, getter=responder(status=404))

    assert result.entries == ()
    assert "피드가 없습니다" in (result.error or "")


def test_server_error_asks_to_retry():
    """5xx 는 다시 시도하라고 말한다.

    실측에서 같은 URL 이 500 과 404 를 번갈아 냈다. 둘을 한 문구로
    묶으면 멀쩡한 채널을 포기하게 된다.
    """
    result = channel_feed.fetch(CHANNEL_ID, getter=responder(status=503))

    assert "다시 시도" in (result.error or "")


def test_other_status_is_reported_with_the_code():
    """그 밖의 상태는 코드를 그대로 알린다."""
    result = channel_feed.fetch(CHANNEL_ID, getter=responder(status=418))

    assert "418" in (result.error or "")


def test_broken_xml_is_reported():
    """XML 이 깨졌으면 사유를 돌려준다."""
    result = channel_feed.fetch(CHANNEL_ID, getter=responder(text="<feed"))

    assert result.entries == ()
    assert "해석하지 못했습니다" in (result.error or "")


def test_an_empty_feed_is_a_success():
    """항목이 없는 피드는 성공이다.

    아직 영상을 올리지 않은 채널도 등록할 수 있어야 한다.
    """
    empty = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom"><title>빈 채널</title>'
        "</feed>"
    )

    result = channel_feed.fetch(CHANNEL_ID, getter=responder(text=empty))

    assert result.entries == ()
    assert result.error is None


def test_an_entry_missing_a_field_is_skipped():
    """필드가 빠진 항목만 건너뛰고 나머지는 살린다."""
    partial = FEED_XML.replace("<yt:videoId>LoLYw--s-5w</yt:videoId>", "")

    result = channel_feed.fetch(CHANNEL_ID, getter=responder(text=partial))

    assert [item.video_id for item in result.entries] == ["TbkUKCm3CHQ"]
    assert result.error is None


def test_a_naive_timestamp_is_skipped():
    """타임존이 없는 시각은 건너뛴다.

    naive 와 aware 를 섞어 비교하면 TypeError 가 난다.
    """
    naive = FEED_XML.replace("2026-09-21T17:52:29+00:00", "2026-09-21T17:52:29")

    result = channel_feed.fetch(CHANNEL_ID, getter=responder(text=naive))

    assert [item.video_id for item in result.entries] == ["LoLYw--s-5w"]


def test_a_huge_feed_is_refused():
    """상한을 넘는 본문은 파싱하지 않는다."""
    huge = "<feed>" + "a" * (channel_feed.MAX_FEED_BYTES + 1) + "</feed>"

    result = channel_feed.fetch(CHANNEL_ID, getter=responder(text=huge))

    assert result.entries == ()
    assert "너무 큽니다" in (result.error or "")


def test_a_transport_error_is_reported():
    """요청 자체가 실패하면 사유를 돌려준다."""

    def getter(url, **kwargs):
        """연결 실패를 만든다."""
        raise httpx.ConnectError("연결 실패")

    result = channel_feed.fetch(CHANNEL_ID, getter=getter)

    assert result.entries == ()
    assert "가져오지 못했습니다" in (result.error or "")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/services/test_channel_feed.py -q`
Expected: 수집 단계에서 FAIL — `ImportError: cannot import name
'channel_feed' from 'notebooklm_st.services'`

- [ ] **Step 3: 최소 구현을 쓴다**

`src/notebooklm_st/services/channel_feed.py` 를 만든다.

```python
"""채널 RSS 피드를 읽어 최근 영상을 돌려준다.

피드를 아는 유일한 모듈이다. SQLite 도 Streamlit 도 모른다.

**실패를 예외가 아니라 값으로 돌려준다.** 화면이 채널 여러 개를
차례로 읽으면서 하나의 실패로 멈추지 않아야 한다.

채널 목록(`yt-dlp --flat-playlist`)을 쓰지 않는 이유가 있다. 거기엔
업로드 시각이 오지 않아(``timestamp`` 가 ``None``) "기준일 이후" 를
판정할 수 없다. 피드는 그 값을 주고 비용이 HTTP 한 번이다.
"""

import dataclasses
import datetime
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable

import httpx

from notebooklm_st.core import models

FEED_URL = "https://www.youtube.com/feeds/videos.xml"
"""채널 피드 주소. 채널 ID 를 질의 파라미터로 붙인다."""

FETCH_TIMEOUT = 20.0
"""요청에 주는 최대 초. ``outline`` 과 같은 값이다."""

MAX_FEED_BYTES = 1 << 20
"""받아들일 피드 본문의 최대 크기.

``ElementTree`` 는 엔티티 확장 공격("billion laughs")에 취약하고, 이
모듈은 제3자가 주는 XML 을 읽는다. 실측한 피드가 24 KB 이므로 1 MiB
는 넉넉하다.
"""

_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}

GetLike = Callable[..., httpx.Response]
"""``httpx.get`` 자리에 넣을 수 있는 것.

키워드 인자가 많아 Protocol 로 적으면 길기만 하다(``outline`` 의
``PostLike`` 와 같은 이유).
"""


@dataclasses.dataclass(frozen=True, slots=True)
class FeedResult:
    """피드 조회 결과.

    ``error`` 가 있으면 ``entries`` 는 비어 있다. 항목이 없는 성공과
    실패를 구분해야 하므로 둘을 함께 담는다.
    """

    entries: tuple[models.FeedEntry, ...]
    error: str | None


def fetch(
    channel_id: str,
    getter: GetLike = httpx.get,
    timeout: float = FETCH_TIMEOUT,
) -> FeedResult:
    """채널의 최근 영상을 피드에서 읽는다.

    Args:
        channel_id: ``UC`` 로 시작하는 채널 ID.
        getter: 요청을 보내는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.
        timeout: 요청에 주는 최대 초.

    Returns:
        읽은 항목들 또는 사람에게 보여 줄 실패 사유. 피드는 최신
        15건까지만 준다.
    """
    try:
        response = getter(
            FEED_URL,
            params={"channel_id": channel_id},
            timeout=timeout,
            follow_redirects=True,
        )
    except httpx.HTTPError as error:
        return FeedResult((), f"피드를 가져오지 못했습니다: {error}")
    if response.status_code != 200:
        return FeedResult((), _status_message(response.status_code))
    if len(response.content) > MAX_FEED_BYTES:
        return FeedResult(
            (), f"피드가 너무 큽니다({len(response.content)} 바이트)."
        )
    return _read(response.text)


def _status_message(status: int) -> str:
    """상태 코드를 사람이 읽을 안내로 옮긴다.

    **404 와 5xx 를 가른다.** 404 는 이 채널에 피드가 없다는 뜻이라
    등록할 수 없고, 5xx 는 일시적일 수 있어 다시 시도하면 된다.
    실측에서 같은 URL 이 두 답을 다 냈다.

    Args:
        status: 응답 상태 코드.

    Returns:
        화면에 그대로 보여 줄 문장.
    """
    if status == 404:
        return (
            "이 채널에는 RSS 피드가 없습니다. 채널 URL 을 확인하세요."
            " 피드가 없는 채널은 등록할 수 없습니다."
        )
    if 500 <= status < 600:
        return (
            f"YouTube 가 일시적인 오류를 냈습니다(HTTP {status})."
            " 잠시 뒤 다시 시도하세요."
        )
    return f"YouTube 가 오류를 냈습니다(HTTP {status})."


def _read(text: str) -> FeedResult:
    """피드 본문을 항목들로 옮긴다.

    Args:
        text: 응답 본문.

    Returns:
        읽을 수 있던 항목들. 본문 자체가 깨졌으면 사유.
    """
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return FeedResult((), "피드를 해석하지 못했습니다.")
    entries = []
    for element in root.findall("atom:entry", _NAMESPACES):
        entry = _to_entry(element)
        if entry is not None:
            entries.append(entry)
    return FeedResult(tuple(entries), None)


def _to_entry(element: ElementTree.Element) -> models.FeedEntry | None:
    """항목 하나를 값 객체로 옮긴다.

    **쓸 수 없는 항목은 건너뛴다.** 피드 하나의 흠집이 채널 전체를
    실패로 만들 이유가 없다.

    Args:
        element: ``atom:entry`` 요소.

    Returns:
        값 객체. 필드가 빠졌거나 시각에 타임존이 없으면 ``None``.
    """
    video_id = element.findtext("yt:videoId", namespaces=_NAMESPACES)
    title = element.findtext("atom:title", namespaces=_NAMESPACES)
    published = element.findtext("atom:published", namespaces=_NAMESPACES)
    if not video_id or not title or not published:
        return None
    try:
        moment = datetime.datetime.fromisoformat(published)
    except ValueError:
        return None
    if moment.tzinfo is None:
        # naive 와 aware 를 섞어 비교하면 TypeError 가 난다.
        return None
    return models.FeedEntry(
        video_id=video_id, title=title, published=moment
    )
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/services/test_channel_feed.py -q`
Expected: PASS (11건)

- [ ] **Step 5: 검증 4단 + 커밋**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
git add src/notebooklm_st/services/channel_feed.py \
        tests/services/test_channel_feed.py
git commit -m "✨ feat(channels): 채널 RSS 피드에서 최근 영상 읽기"
```

---

### Task 6: 채널 URL 해석

**Files:**
- Create: `src/notebooklm_st/services/channel_lookup.py`
- Test: `tests/services/test_channel_lookup.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `channel_lookup.LookupResult(channel_id: str | None,
    title: str | None, url: str | None, error: str | None)`
  - `channel_lookup.lookup(url: str, runner: RunnerLike = subprocess.run,
    timeout: float = LOOKUP_TIMEOUT) -> LookupResult`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_channel_lookup.py` 를 만든다.

```python
"""채널 URL 해석 테스트 — 실제 yt-dlp 를 부르지 않는다."""

import json
import subprocess

from notebooklm_st.services import channel_lookup

CHANNEL_ID = "UCsBjURrPoezykLs9EqgamOA"
HANDLE_URL = "https://www.youtube.com/@Fireship"

PAYLOAD = {
    "_type": "playlist",
    "channel": "Fireship",
    "channel_id": CHANNEL_ID,
    "channel_url": f"https://www.youtube.com/channel/{CHANNEL_ID}",
    "entries": [{"id": "TbkUKCm3CHQ"}],
}


def completed(returncode=0, stdout=None, stderr=b""):
    """가짜 자식 프로세스 결과를 만든다."""
    if stdout is None:
        stdout = json.dumps(PAYLOAD).encode("utf-8")
    return subprocess.CompletedProcess(
        args=["yt-dlp"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def runner_for(result):
    """준비된 결과를 돌려주는 가짜 runner 를 만든다."""

    def runner(argv, **kwargs):
        """호출을 무시하고 준비된 결과만 돌려준다."""
        return result

    return runner


def test_lookup_reads_the_channel_id_and_title():
    """채널 ID 와 이름을 읽는다."""
    found = channel_lookup.lookup(HANDLE_URL, runner=runner_for(completed()))

    assert found.error is None
    assert found.channel_id == CHANNEL_ID
    assert found.title == "Fireship"
    assert found.url == f"https://www.youtube.com/channel/{CHANNEL_ID}"


def test_lookup_asks_for_only_one_entry():
    """목록은 한 건만 받는다. 쓰는 것은 최상위 필드뿐이다."""
    seen = {}

    def runner(argv, **kwargs):
        """넘어온 명령줄을 기록한다."""
        seen["argv"] = argv
        return completed()

    channel_lookup.lookup(HANDLE_URL, runner=runner)

    assert "--flat-playlist" in seen["argv"]
    assert "--playlist-end" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--playlist-end") + 1] == "1"
    assert seen["argv"][-1] == HANDLE_URL


def test_a_url_without_a_channel_is_refused():
    """채널 ID 가 없으면 채널 URL 이 아니라고 말한다."""
    payload = json.dumps({"_type": "video", "id": "abc"}).encode("utf-8")

    found = channel_lookup.lookup(
        "https://youtu.be/dQw4w9WgXcQ",
        runner=runner_for(completed(stdout=payload)),
    )

    assert found.channel_id is None
    assert "채널 URL 이 아닙니다" in (found.error or "")


def test_a_blank_url_is_refused_without_running_yt_dlp():
    """빈 URL 이면 자식 프로세스를 부르지 않는다."""
    called = []

    def runner(argv, **kwargs):
        """불리면 기록을 남긴다."""
        called.append(True)
        return completed()

    found = channel_lookup.lookup("   ", runner=runner)

    assert called == []
    assert found.error is not None


def test_a_failing_exit_code_is_reported():
    """0 이 아닌 종료 코드는 자식의 출력을 사유로 옮긴다."""
    found = channel_lookup.lookup(
        HANDLE_URL,
        runner=runner_for(
            completed(returncode=1, stdout=b"", stderr=b"ERROR: not found")
        ),
    )

    assert found.channel_id is None
    assert "not found" in (found.error or "")


def test_a_timeout_is_reported():
    """타임아웃은 사유로 돌아온다."""

    def runner(argv, **kwargs):
        """타임아웃을 만든다."""
        raise subprocess.TimeoutExpired(cmd="yt-dlp", timeout=30.0)

    found = channel_lookup.lookup(HANDLE_URL, runner=runner)

    assert "넘겨 중단했습니다" in (found.error or "")


def test_a_missing_executable_is_reported():
    """yt-dlp 를 실행할 수 없으면 사유로 돌아온다."""

    def runner(argv, **kwargs):
        """실행 실패를 만든다."""
        raise OSError("실행 파일 없음")

    found = channel_lookup.lookup(HANDLE_URL, runner=runner)

    assert "실행하지 못했습니다" in (found.error or "")


def test_broken_json_is_reported():
    """출력이 JSON 이 아니면 사유로 돌아온다."""
    found = channel_lookup.lookup(
        HANDLE_URL, runner=runner_for(completed(stdout=b"not json"))
    )

    assert "해석하지 못했습니다" in (found.error or "")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/services/test_channel_lookup.py -q`
Expected: 수집 단계에서 FAIL — `ImportError: cannot import name
'channel_lookup' from 'notebooklm_st.services'`

- [ ] **Step 3: 최소 구현을 쓴다**

`src/notebooklm_st/services/channel_lookup.py` 를 만든다.

```python
"""채널 URL 을 채널 ID 로 해석한다.

**등록할 때 한 번만 부른다.** 그 뒤의 확인은 피드만 읽는다
(→ ``services.channel_feed``).

``video_metadata`` 와 같은 방식이다 — yt-dlp 를 자식 프로세스로
부르고, 실패를 예외가 아니라 값으로 돌려준다.
"""

import dataclasses
import json
import subprocess
import sys
from collections.abc import Callable

LOOKUP_TIMEOUT = 30.0
"""자식 프로세스에 주는 최대 초.

``video_metadata.FETCH_TIMEOUT``(20초)보다 길다. 채널 페이지 해석이
영상 하나보다 무겁고, 등록은 사람이 기다리는 한 번뿐이다.
"""

DETAIL_LIMIT = 500
"""실패 사유로 남길 최대 글자 수."""

RunnerLike = Callable[..., subprocess.CompletedProcess[bytes]]
"""``subprocess.run`` 자리에 넣을 수 있는 것."""


@dataclasses.dataclass(frozen=True, slots=True)
class LookupResult:
    """채널 해석 결과.

    ``error`` 가 있으면 나머지는 모두 ``None`` 이다.
    """

    channel_id: str | None
    title: str | None
    url: str | None
    error: str | None


def lookup(
    url: str,
    runner: RunnerLike = subprocess.run,
    timeout: float = LOOKUP_TIMEOUT,
) -> LookupResult:
    """채널 URL 에서 채널 ID 와 이름을 얻는다.

    ``uv`` 로 부르지 않는다. ``uv`` 는 PATH 에 없을 수 있고, 앱은
    이미 yt-dlp 가 설치된 인터프리터 안에서 돌고 있다.

    Args:
        url: 채널 URL. ``@handle`` 과 ``/channel/UC…`` 를 받는다.
            ``/videos`` 를 붙이지 않아도 된다.
        runner: 자식을 돌리는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.
        timeout: 자식에게 주는 최대 초.

    Returns:
        채널 ID·이름·주소, 또는 사람에게 보여 줄 실패 사유.
    """
    cleaned = url.strip()
    if not cleaned:
        return _failed("채널 URL 을 입력하세요.")
    try:
        completed = runner(
            [
                sys.executable,
                "-m",
                "yt_dlp",
                "--flat-playlist",
                "-J",
                "--playlist-end",
                "1",
                cleaned,
            ],
            capture_output=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return _failed(
            f"채널 조회가 {int(timeout)}초를 넘겨 중단했습니다."
        )
    except OSError as error:
        return _failed(f"yt-dlp 를 실행하지 못했습니다: {error}")
    if completed.returncode != 0:
        return _failed(_detail(completed.stderr, completed.stdout))
    return _read(completed.stdout)


def _read(stdout: bytes) -> LookupResult:
    """자식의 출력에서 채널 세 값을 꺼낸다.

    ``channel_url`` 이 없으면 채널 ID 로 짓는다. 저장할 주소가 항상
    한 모양이어야 화면의 링크도 한 모양이 된다.

    Args:
        stdout: 자식의 표준 출력.

    Returns:
        해석 결과.
    """
    try:
        info = json.loads(stdout)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _failed("yt-dlp 출력을 해석하지 못했습니다.")
    if not isinstance(info, dict):
        return _failed("yt-dlp 출력을 해석하지 못했습니다.")
    channel_id = info.get("channel_id")
    if not isinstance(channel_id, str) or not channel_id:
        return _failed(
            "채널 URL 이 아닙니다. 채널 주소를 넣으세요"
            "(예: https://www.youtube.com/@handle)."
        )
    title = info.get("channel")
    url = info.get("channel_url")
    return LookupResult(
        channel_id=channel_id,
        title=title if isinstance(title, str) and title else channel_id,
        url=url
        if isinstance(url, str) and url
        else f"https://www.youtube.com/channel/{channel_id}",
        error=None,
    )


def _failed(detail: str) -> LookupResult:
    """실패 결과를 만든다.

    Args:
        detail: 사람에게 보여 줄 사유.

    Returns:
        ``error`` 만 채운 결과.
    """
    return LookupResult(
        channel_id=None, title=None, url=None, error=detail
    )


def _detail(stderr: bytes, stdout: bytes) -> str:
    """자식의 실패 출력을 짧은 문자열로 만든다.

    Args:
        stderr: 자식의 표준 오류.
        stdout: 자식의 표준 출력. stderr 가 비었을 때 대신 쓴다.

    Returns:
        끝에서 ``DETAIL_LIMIT`` 글자. 아무 말도 없으면 대체 문구.
    """
    raw = stderr or stdout or b""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return "채널을 확인하지 못했습니다."
    return text[-DETAIL_LIMIT:]
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/services/test_channel_lookup.py -q`
Expected: PASS (8건)

- [ ] **Step 5: 검증 4단 + 커밋**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
git add src/notebooklm_st/services/channel_lookup.py \
        tests/services/test_channel_lookup.py
git commit -m "✨ feat(channels): 채널 URL 을 채널 ID 로 해석하기"
```

---

### Task 7: 채널 화면 — 등록과 목록

**Files:**
- Create: `src/notebooklm_st/pages/channels.py`
- Modify: `src/notebooklm_st/app.py:21-55`
- Test: `tests/pages/test_channels.py`

**Interfaces:**
- Consumes: `channels.*`(Task 3), `channel_lookup.lookup`(Task 6),
  `channel_feed.fetch`(Task 5)
- Produces: `channels_page.render() -> None`(Streamlit 페이지 진입점),
  세션 키 `channels_url`·`channels_baseline`

이 태스크가 끝나면 화면이 뜨고 채널을 등록·수정·삭제할 수 있다.
새 영상 확인은 Task 8 이 붙인다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_channels.py` 를 만든다.

```python
"""채널 화면 테스트."""

import datetime

import pytest
from streamlit.testing import v1

from notebooklm_st.services import channel_feed, channel_lookup, channels

CHANNEL_ID = "UCsBjURrPoezykLs9EqgamOA"
HANDLE_URL = "https://www.youtube.com/@Fireship"


def script():
    """AppTest 진입점 — 채널 화면을 렌더한다."""
    from notebooklm_st.pages import channels as channels_page

    channels_page.render()


def button_by(app, label):
    """라벨로 버튼을 찾는다.

    인덱스로 찾으면 화면에 버튼이 하나 늘 때마다 이 파일의 테스트가
    통째로 깨진다(다음 태스크가 확인 버튼을 더한다).
    """
    return [item for item in app.button if item.label == label][0]


def date_input_by(app, label):
    """라벨로 날짜 입력을 찾는다. 같은 이유로 인덱스를 쓰지 않는다."""
    return [item for item in app.date_input if item.label == label][0]


@pytest.fixture
def fake_sources(monkeypatch):
    """해석과 피드를 성공하는 가짜로 바꾼다."""
    from notebooklm_st.pages import channels as channels_page

    def lookup(url, **kwargs):
        """고정된 채널을 돌려준다."""
        return channel_lookup.LookupResult(
            channel_id=CHANNEL_ID,
            title="Fireship",
            url=f"https://www.youtube.com/channel/{CHANNEL_ID}",
            error=None,
        )

    def fetch(channel_id, **kwargs):
        """빈 피드를 성공으로 돌려준다."""
        return channel_feed.FeedResult((), None)

    monkeypatch.setattr(channels_page.channel_lookup, "lookup", lookup)
    monkeypatch.setattr(channels_page.channel_feed, "fetch", fetch)


def test_no_channels_shows_a_notice(app_db) -> None:
    """등록된 채널이 없으면 안내를 보여 준다."""
    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert any("등록된 채널이 없습니다" in item.value for item in app.info)


def test_registering_saves_the_channel(app_db, fake_sources) -> None:
    """URL 을 넣고 등록하면 채널이 저장된다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value(HANDLE_URL).run()
    button_by(app, "등록").click().run()

    assert not app.exception
    saved = channels.list_channels(app_db)
    assert [item.channel_id for item in saved] == [CHANNEL_ID]
    assert saved[0].title == "Fireship"


def test_a_lookup_failure_shows_the_reason(app_db, monkeypatch) -> None:
    """해석이 실패하면 사유를 보여 주고 저장하지 않는다."""
    from notebooklm_st.pages import channels as channels_page

    def lookup(url, **kwargs):
        """실패를 돌려준다."""
        return channel_lookup.LookupResult(
            channel_id=None,
            title=None,
            url=None,
            error="채널 URL 이 아닙니다.",
        )

    monkeypatch.setattr(channels_page.channel_lookup, "lookup", lookup)

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value("https://example.com").run()
    button_by(app, "등록").click().run()

    assert any("채널 URL 이 아닙니다" in item.value for item in app.error)
    assert channels.list_channels(app_db) == []


def test_a_feed_failure_blocks_registration(app_db, monkeypatch) -> None:
    """피드가 없는 채널은 등록하지 않는다.

    매 확인마다 실패할 채널을 등록해 두지 않는다.
    """
    from notebooklm_st.pages import channels as channels_page

    def lookup(url, **kwargs):
        """성공을 돌려준다."""
        return channel_lookup.LookupResult(
            channel_id=CHANNEL_ID,
            title="Fireship",
            url=HANDLE_URL,
            error=None,
        )

    def fetch(channel_id, **kwargs):
        """피드 없음을 돌려준다."""
        return channel_feed.FeedResult((), "이 채널에는 RSS 피드가 없습니다.")

    monkeypatch.setattr(channels_page.channel_lookup, "lookup", lookup)
    monkeypatch.setattr(channels_page.channel_feed, "fetch", fetch)

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value(HANDLE_URL).run()
    button_by(app, "등록").click().run()

    assert any("피드가 없습니다" in item.value for item in app.error)
    assert channels.list_channels(app_db) == []


def test_a_duplicate_channel_shows_the_reason(
    app_db, fake_sources
) -> None:
    """이미 등록된 채널은 사유를 보여 준다."""
    channels.add_channel(
        app_db, CHANNEL_ID, "Fireship", HANDLE_URL, "2026-09-23"
    )

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value(HANDLE_URL).run()
    button_by(app, "등록").click().run()

    assert any("이미 등록된" in item.value for item in app.error)


def test_registered_channels_are_listed(app_db) -> None:
    """등록된 채널이 목록에 나온다."""
    channels.add_channel(
        app_db, CHANNEL_ID, "Fireship", HANDLE_URL, "2026-09-23"
    )

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    rendered = " ".join(item.value for item in app.markdown)
    assert "Fireship" in rendered


def test_the_baseline_can_be_changed(app_db) -> None:
    """목록에서 기준일을 고칠 수 있다."""
    saved = channels.add_channel(
        app_db, CHANNEL_ID, "Fireship", HANDLE_URL, "2026-09-23"
    )

    app = v1.AppTest.from_function(script)
    app.run()
    date_input_by(app, "이 채널의 기준일").set_value(
        datetime.date(2026, 1, 1)
    ).run()
    button_by(app, "기준일 저장").click().run()

    assert not app.exception
    assert channels.list_channels(app_db)[0].baseline == "2026-01-01"
    assert saved.baseline == "2026-09-23"


def test_deleting_removes_the_channel(app_db) -> None:
    """목록에서 채널을 지울 수 있다."""
    channels.add_channel(
        app_db, CHANNEL_ID, "Fireship", HANDLE_URL, "2026-09-23"
    )

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "삭제").click().run()

    assert not app.exception
    assert channels.list_channels(app_db) == []
```

**위젯을 인덱스로 찾지 않는다.** 다음 태스크가 "새 영상 확인" 버튼을
등록 칸 뒤에 끼우므로, 인덱스로 쓴 테스트는 그때 통째로 깨진다.
라벨로 찾는 두 헬퍼를 쓴다. 그래서 채널 행의 날짜 입력 라벨이
등록 칸의 "기준일" 과 달라야 한다(구현은 "이 채널의 기준일" 을 쓴다).

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/pages/test_channels.py -q`
Expected: 수집 단계에서 FAIL — `ModuleNotFoundError: No module named
'notebooklm_st.pages.channels'`

- [ ] **Step 3: 화면을 쓴다**

`src/notebooklm_st/pages/channels.py` 를 만든다.

```python
"""채널 화면 — 즐겨찾기 채널을 등록하고 새 영상을 찾는다.

이 파일 안에서 ``channels`` 는 **저장소**(``services.channels``)다.
페이지는 자기 자신을 import 하지 않는다.
"""

import datetime
import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import models
from notebooklm_st.services import channel_feed, channel_lookup, channels

_URL_KEY = "channels_url"
_BASELINE_KEY = "channels_baseline"


def render() -> None:
    """채널 등록과 구독 목록을 그린다."""
    st.title("채널")
    connection = session.get_connection()
    _render_register(connection)
    channel_list = channels.list_channels(connection)
    if not channel_list:
        st.info(
            "등록된 채널이 없습니다. 위에서 채널 URL 을 등록하세요."
        )
        return
    _render_list(connection, channel_list)


def _render_register(connection: sqlite3.Connection) -> None:
    """채널 URL 과 기준일을 받아 등록한다."""
    url = st.text_input(
        "채널 URL",
        key=_URL_KEY,
        placeholder="https://www.youtube.com/@handle",
    )
    baseline = st.date_input(
        "기준일",
        value=datetime.date.today(),
        key=_BASELINE_KEY,
        help="이 날짜 이후 업로드된 영상만 새 영상으로 봅니다."
        " 피드가 최신 15건까지만 주므로 그보다 거슬러 올라가지는"
        " 못합니다.",
    )
    if st.button(
        "등록", key="channels_add", disabled=not url.strip()
    ):
        _add(connection, url, baseline)


def _add(
    connection: sqlite3.Connection, url: str, baseline: object
) -> None:
    """해석 · 피드 확인 · 저장을 차례로 한다.

    **피드를 등록 시점에 한 번 찔러 본다.** 피드가 없는 채널을
    등록해 두면 확인할 때마다 실패한다. 실패를 매일 겪는 자리가
    아니라 한 번 겪는 자리로 당긴다.

    Args:
        connection: 열린 커넥션.
        baseline: ``st.date_input`` 이 돌려준 값. 범위 선택이면
            날짜가 아니므로 막는다.
    """
    if not isinstance(baseline, datetime.date):
        st.error("기준일을 하나 고르세요.")
        return
    with st.spinner("채널을 확인하는 중"):
        found = channel_lookup.lookup(url)
        if (
            found.error is not None
            or found.channel_id is None
            or found.title is None
            or found.url is None
        ):
            st.error(found.error or "채널을 해석하지 못했습니다.")
            return
        feed = channel_feed.fetch(found.channel_id)
    if feed.error is not None:
        st.error(feed.error)
        return
    try:
        channels.add_channel(
            connection,
            found.channel_id,
            found.title,
            found.url,
            baseline.isoformat(),
        )
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()


def _render_list(
    connection: sqlite3.Connection, channel_list: list[models.Channel]
) -> None:
    """등록된 채널을 수정·삭제 버튼과 함께 그린다."""
    st.subheader("등록된 채널")
    for channel in channel_list:
        _render_row(connection, channel)


def _render_row(
    connection: sqlite3.Connection, channel: models.Channel
) -> None:
    """채널 하나를 그린다.

    접힌 상태에서는 이름만 보인다(질문 관리와 같은 모양).
    """
    with st.expander(channel.title):
        st.markdown(f"[{channel.title}]({channel.url})")
        st.caption(f"채널 ID: {channel.channel_id}")
        edited = st.date_input(
            # 등록 칸의 "기준일" 과 라벨이 겹치지 않게 한다. 겹치면
            # 테스트가 라벨로 위젯을 찾을 수 없다.
            "이 채널의 기준일",
            value=datetime.date.fromisoformat(channel.baseline),
            key=f"channels_baseline_{channel.id}",
            help="고쳐도 화면에 떠 있는 새 영상 목록은 바뀌지"
            " 않습니다. 새 기준일로 보려면 확인을 다시 누르세요.",
        )
        left, right = st.columns(2)
        if left.button("기준일 저장", key=f"channels_save_{channel.id}"):
            _save_baseline(connection, channel.id, edited)
        if right.button("삭제", key=f"channels_delete_{channel.id}"):
            channels.delete_channel(connection, channel.id)
            st.rerun()


def _save_baseline(
    connection: sqlite3.Connection, channel_pk: int, baseline: object
) -> None:
    """고친 기준일을 저장한다."""
    if not isinstance(baseline, datetime.date):
        st.error("기준일을 하나 고르세요.")
        return
    try:
        channels.update_baseline(
            connection, channel_pk, baseline.isoformat()
        )
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()
```

- [ ] **Step 4: 네비게이션에 페이지를 더한다**

`src/notebooklm_st/app.py` 의 pages import 에 `channels` 를 더한다.
현재는 이렇다.

```python
from notebooklm_st.pages import (
    ask,
    dashboard,
    digest,
    history,
    maintenance,
    question_admin,
)
```

바꾼 뒤.

```python
from notebooklm_st.pages import (
    ask,
    channels,
    dashboard,
    digest,
    history,
    maintenance,
    question_admin,
)
```

같은 파일 `st.navigation` 목록에서 질의 **다음 줄**에 더한다.

```python
            st.Page(ask.render, title="질의", url_path="ask", default=True),
            st.Page(channels.render, title="채널", url_path="channels"),
```

- [ ] **Step 5: 통과를 확인한다**

`tests/test_app.py` 는 페이지 수를 단언하지 않고 부팅만 확인한다
(`assert not app.exception`). 단언은 그대로 두고 독스트링의 수만
고친다.

```python
    """일곱 페이지가 등록된 진입점이 예외 없이 부팅된다."""
```

Run: `uv run pytest tests/pages/test_channels.py tests/test_app.py -q`
Expected: PASS

- [ ] **Step 6: 검증 4단 + 커밋**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
git add src/notebooklm_st/pages/channels.py src/notebooklm_st/app.py \
        tests/pages/test_channels.py tests/test_app.py
git commit -m "✨ feat(channels): 채널을 등록·관리하는 화면 더하기"
```

---

### Task 8: 새 영상 확인과 요약 시작

**Files:**
- Modify: `src/notebooklm_st/pages/channels.py`
- Modify: `tests/pages/test_channels.py`
- Modify: `README.md:98-105`

**Interfaces:**
- Consumes: `new_videos.select`(Task 2),
  `run_history.list_video_ids`(Task 4), `channel_feed.fetch`(Task 5),
  `youtube.watch_url`(Task 1), `runner.start_run`(기존),
  `questions.list_questions`(기존)
- Produces: 세션 키 `channels_found`·`channels_started`·
  `channels_questions`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_channels.py` 에 더한다. 먼저 헬퍼와 import 를
보강한다.

```python
from notebooklm_st.core import models
from notebooklm_st.services import questions, run_history


def make_entry(video_id="TbkUKCm3CHQ", published="2026-09-25T01:00:00+00:00"):
    """피드 항목 하나를 만든다."""
    return models.FeedEntry(
        video_id=video_id,
        title="새 영상",
        published=datetime.datetime.fromisoformat(published),
    )


def feed_with(*entries, error=None):
    """준비된 피드를 돌려주는 가짜 fetch 를 만든다."""

    def fetch(channel_id, **kwargs):
        """채널 ID 를 무시하고 준비된 결과를 돌려준다."""
        return channel_feed.FeedResult(tuple(entries), error)

    return fetch


def registered(connection, title="Fireship"):
    """기준일이 지난 채널 하나를 등록한다."""
    return channels.add_channel(
        connection, CHANNEL_ID, title, HANDLE_URL, "2026-09-01"
    )
```

그리고 테스트를 더한다.

```python
def test_checking_lists_new_videos(app_db, monkeypatch) -> None:
    """확인을 누르면 신규 영상이 목록에 나온다."""
    from notebooklm_st.pages import channels as channels_page

    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    monkeypatch.setattr(
        channels_page.channel_feed, "fetch", feed_with(make_entry())
    )

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()

    assert not app.exception
    rendered = " ".join(item.value for item in app.markdown)
    assert "새 영상" in rendered


def test_an_already_summarized_video_is_not_listed(
    app_db, monkeypatch
) -> None:
    """이미 요약한 영상은 신규로 뜨지 않는다."""
    from notebooklm_st.pages import channels as channels_page

    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    run_history.save_run(
        app_db,
        models.RunResult(
            url="https://youtu.be/TbkUKCm3CHQ",
            video_id="TbkUKCm3CHQ",
            title="이미 한 것",
            items=(),
        ),
    )
    monkeypatch.setattr(
        channels_page.channel_feed, "fetch", feed_with(make_entry())
    )

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()

    assert any("새 영상이 없습니다" in item.value for item in app.info)


def test_a_channel_failure_does_not_stop_the_others(
    app_db, monkeypatch
) -> None:
    """채널 하나가 실패해도 나머지는 보인다."""
    from notebooklm_st.pages import channels as channels_page

    registered(app_db, title="되는 채널")
    channels.add_channel(
        app_db, "UC" + "z" * 22, "안 되는 채널", HANDLE_URL, "2026-09-01"
    )

    def fetch(channel_id, **kwargs):
        """한 채널만 실패시킨다."""
        if channel_id == CHANNEL_ID:
            return channel_feed.FeedResult((make_entry(),), None)
        return channel_feed.FeedResult((), "일시적인 오류입니다.")

    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    monkeypatch.setattr(channels_page.channel_feed, "fetch", fetch)

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()

    assert not app.exception
    rendered = " ".join(item.value for item in app.markdown)
    assert "새 영상" in rendered
    assert any("일시적인 오류" in item.value for item in app.error)


def test_no_questions_blocks_the_summary(app_db, monkeypatch) -> None:
    """질문이 없으면 요약 버튼을 그리지 않는다."""
    from notebooklm_st.pages import channels as channels_page

    registered(app_db)
    monkeypatch.setattr(
        channels_page.channel_feed, "fetch", feed_with(make_entry())
    )

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()

    assert any("질문 관리" in item.value for item in app.info)
    assert all("요약" != item.label for item in app.button)


def test_summary_hands_the_video_to_the_runner(
    app_db, monkeypatch
) -> None:
    """요약을 누르면 그 영상 URL 과 고른 질문이 러너로 넘어간다."""
    from notebooklm_st.pages import channels as channels_page

    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    monkeypatch.setattr(
        channels_page.channel_feed, "fetch", feed_with(make_entry())
    )
    received: dict[str, object] = {}

    def fake_start(registry, url, question_list, db_path, **kwargs):
        """넘어온 인자를 기록한다."""
        received["url"] = url
        received["questions"] = [item.title for item in question_list]
        return None

    monkeypatch.setattr(channels_page.runner, "start_run", fake_start)

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    app.multiselect[0].select(questions.list_questions(app_db)[0]).run()
    summary = [item for item in app.button if item.label == "요약"][0]
    summary.click().run()

    assert received["url"] == (
        "https://www.youtube.com/watch?v=TbkUKCm3CHQ"
    )
    assert received["questions"] == ["핵심 주장"]


def test_a_running_query_blocks_the_summary(app_db, monkeypatch) -> None:
    """질의가 돌고 있으면 요약을 시작할 수 없다."""
    from notebooklm_st import session
    from notebooklm_st.pages import channels as channels_page

    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    monkeypatch.setattr(
        channels_page.channel_feed, "fetch", feed_with(make_entry())
    )
    session.get_registry().create(
        "https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", ("질문",)
    )

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    app.multiselect[0].select(questions.list_questions(app_db)[0]).run()

    summary = [item for item in app.button if item.label == "요약"][0]
    assert summary.disabled is True
    assert any("질의" in item.value for item in app.info)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/pages/test_channels.py -q`
Expected: FAIL — "새 영상 확인" 버튼이 없어 `button_by` 가
IndexError 를 낸다.

- [ ] **Step 3: 확인과 실행을 붙인다**

`src/notebooklm_st/pages/channels.py` 의 import 를 보강한다.

```python
import dataclasses
import datetime
import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import labels, models, new_videos, youtube
from notebooklm_st.services import (
    channel_feed,
    channel_lookup,
    channels,
    questions,
    run_history,
    runner,
    store,
)
```

세션 키 상수를 더한다.

```python
_QUESTIONS_KEY = "channels_questions"
_FOUND_KEY = "channels_found"
_STARTED_KEY = "channels_started"
```

확인 결과를 담을 값 객체를 더한다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class _Checked:
    """채널 하나의 확인 결과.

    세션에 담는 화면 전용 값이다. 채널 제목을 복사해 두므로 확인
    뒤에 채널을 지워도 목록이 그대로 보인다.
    """

    title: str
    entries: tuple[models.FeedEntry, ...]
    error: str | None
```

`render()` 를 바꿔 확인을 끼운다. 바꾸기 전 모습은 이렇다.

```python
    if not channel_list:
        st.info(
            "등록된 채널이 없습니다. 위에서 채널 URL 을 등록하세요."
        )
        return
    _render_list(connection, channel_list)
```

바꾼 뒤.

```python
    if not channel_list:
        st.info(
            "등록된 채널이 없습니다. 위에서 채널 URL 을 등록하세요."
        )
        return
    _render_check(connection, channel_list)
    _render_list(connection, channel_list)
```

그리고 함수들을 파일 끝에 더한다.

```python
def _render_check(
    connection: sqlite3.Connection, channel_list: list[models.Channel]
) -> None:
    """확인 버튼과 그 결과를 그린다."""
    if st.button("새 영상 확인", key="channels_check"):
        st.session_state[_FOUND_KEY] = _check(connection, channel_list)
        st.session_state[_STARTED_KEY] = set()
    found = st.session_state.get(_FOUND_KEY)
    if found is None:
        return
    _render_found(connection, found)


def _check(
    connection: sqlite3.Connection, channel_list: list[models.Channel]
) -> list[_Checked]:
    """채널마다 피드를 읽어 신규를 고른다.

    **한 채널이 실패해도 멈추지 않는다.** 부분 목록임이 화면에
    드러나고 실패한 채널이 사유와 함께 남는다. 정리본이 멈추는
    이유(부분 결과가 완전해 보인다)가 여기엔 없다.

    Args:
        connection: 열린 커넥션.
        channel_list: 확인할 채널들.

    Returns:
        채널 순서대로의 확인 결과.
    """
    known = run_history.list_video_ids(connection)
    results: list[_Checked] = []
    with st.spinner("새 영상을 확인하는 중"):
        for channel in channel_list:
            feed = channel_feed.fetch(channel.channel_id)
            if feed.error is not None:
                results.append(_Checked(channel.title, (), feed.error))
                continue
            results.append(
                _Checked(
                    channel.title,
                    new_videos.select(
                        feed.entries, channel.baseline, known
                    ),
                    None,
                )
            )
    return results


def _render_found(
    connection: sqlite3.Connection, found: list[_Checked]
) -> None:
    """확인 결과를 그리고 요약을 시작할 수 있게 한다."""
    question_list = questions.list_questions(connection)
    selected: list[models.Question] = []
    if not question_list:
        st.info("질문 관리 화면에서 질문을 먼저 등록하세요.")
    else:
        selected = st.multiselect(
            "질문 선택",
            options=question_list,
            format_func=lambda question: question.title,
            key=_QUESTIONS_KEY,
            help="고른 질문을 이 목록의 모든 요약에 씁니다.",
        )
    for item in found:
        if item.error is not None:
            st.error(f"{item.title}: {item.error}")
    total = sum(len(item.entries) for item in found)
    if total == 0:
        if all(item.error is None for item in found):
            st.info("새 영상이 없습니다.")
        return
    reason = _blocked_reason(selected)
    if reason is not None:
        # 영상마다 그리면 같은 문장이 목록을 도배한다. 한 번만 적는다.
        st.info(reason)
    for item in found:
        if item.entries:
            st.subheader(item.title)
            for entry in item.entries:
                _render_entry(entry, selected, reason)


def _blocked_reason(selected: list[models.Question]) -> str | None:
    """요약을 막을 이유를 찾아 문장으로 돌려준다.

    질의와 정리는 같은 쿠키로 NotebookLM 에 붙으므로 동시에 돌리지
    않는다. 질의 화면과 같은 가드다.

    Args:
        selected: 고른 질문들.

    Returns:
        막을 이유. 없으면 ``None``.
    """
    if session.get_registry().running_count() > 0:
        return (
            "이미 실행 중인 질의가 있습니다. 실행 현황 화면에서"
            " 완료를 확인한 뒤 시작하세요."
        )
    if session.get_digest_registry().is_running():
        return (
            "정리본을 작성 중입니다. 정리본 화면에서 완료를 확인한 뒤"
            " 시작하세요."
        )
    if not selected:
        return "질문을 하나 이상 고르세요."
    return None


def _render_entry(
    entry: models.FeedEntry,
    selected: list[models.Question],
    reason: str | None,
) -> None:
    """신규 영상 한 줄과 요약 버튼을 그린다."""
    url = youtube.watch_url(entry.video_id)
    started = st.session_state.get(_STARTED_KEY, set())
    left, right = st.columns([4, 1])
    left.markdown(
        f"[{labels.shorten(entry.title)}]({url})"
        f" · {entry.published.astimezone():%Y-%m-%d %H:%M}"
    )
    if entry.video_id in started:
        right.caption("실행 중")
        return
    if right.button(
        "요약",
        key=f"channels_run_{entry.video_id}",
        disabled=reason is not None,
    ):
        runner.start_run(
            session.get_registry(),
            url,
            selected,
            store.default_db_path(),
        )
        st.session_state[_STARTED_KEY] = started | {entry.video_id}
        st.rerun()
```

**진행 상황은 실행 현황 화면에서 본다.** 이 화면은 시작만 한다.

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/pages/test_channels.py -q`
Expected: PASS

- [ ] **Step 5: README 를 갱신한다**

`README.md` 의 "사용 순서" 목록을 아래로 **통째로** 바꾼다(항목이
하나 늘어 번호가 밀린다).

```markdown
1. **질문 관리** 화면에서 질문 템플릿을 먼저 등록합니다. (제목은 중복 불가) 이 목록은 **질의와 정리본 지시가 함께 씁니다.**
2. **질의** 화면에서 YouTube URL 을 입력하고 질문을 선택한 뒤 실행합니다.
3. **채널** 화면에서 즐겨찾기 채널을 등록해 두면, **새 영상 확인**으로 아직 요약하지 않은 영상만 모아 볼 수 있습니다. 목록에서 바로 요약을 시작합니다. (기준일 이후 업로드분만 보이며, 채널 피드는 최신 15건까지 줍니다)
4. **실행 현황** 화면에서 진행 상황을 봅니다. (1초마다 자동 갱신)
5. **이력** 화면에서 답변을 확인하고, 제목을 정한 뒤 **Outline 에 저장**합니다. 저장하면 로컬에는 문서명과 링크만 남고 수정·삭제·검색은 Outline 에서 합니다.
6. **정리본** 화면에서 저장된 요약본 여럿을 골라 하나의 글로 정리합니다. 정리 지시는 질문 관리에 등록된 질문 중 하나를 골라 씁니다. 제목은 NotebookLM 이 정리와 함께 지은 주제로 `[정리] <주제>` 가 기본값이며 고쳐 쓸 수 있습니다. 저장하면 Outline 에 문서가 생기며, 정리본은 로컬에 남지 않습니다.
7. **정리** 화면에서 삭제되지 않고 남은 임시 노트북(`tmp-` 접두사)을 지웁니다.
```

같은 파일에서 화면 목록을 적은 줄(`├── pages/` 주석)에 `채널` 을
더한다. 현재는 이렇다.

```
├── pages/           # 질의 · 실행 현황 · 질문 관리 · 이력 · 정리본 · 정리
```

바꾼 뒤.

```
├── pages/           # 질의 · 채널 · 실행 현황 · 질문 관리 · 이력 · 정리본 · 정리
```

- [ ] **Step 6: 검증 4단**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run mypy src tests && uv run pytest -q
```

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/pages/channels.py tests/pages/test_channels.py \
        README.md
git commit -m "✨ feat(channels): 새 영상을 찾아 요약을 시작하기"
```

---

## 완료 확인

모든 태스크가 끝나면 아래를 확인한다.

- [ ] `uv run ruff format --check .` · `uv run ruff check .` ·
      `uv run mypy src tests` · `uv run pytest` 전부 통과
- [ ] `git status` 가 깨끗하고, 커밋이 태스크별로 나뉘어 있다
- [ ] 앱을 띄워 화면을 눈으로 본다:
      `uv run streamlit run src/notebooklm_st/app.py`
      채널을 하나 등록하고(실제 채널 URL) 새 영상 확인을 눌러 본다.
      이때 처음으로 **실제 피드와 yt-dlp** 를 탄다 — 테스트는 전부
      가짜를 쓴다.
- [ ] `git push` 는 하지 않는다. 사람이 한다.

## 스펙과의 대응

| 스펙 절 | 태스크 |
| --- | --- |
| §5 값 객체 | Task 2 |
| §6 `channel_lookup` | Task 6 |
| §7 `channel_feed` | Task 5 |
| §8 `new_videos` | Task 2 |
| §9 `channels`·스키마·`list_video_ids` | Task 3, Task 4 |
| §10 화면 | Task 7, Task 8 |
| §11 실패와 엣지 | Task 5·6 의 사유 문구, Task 7·8 의 안내 |
| §12 테스트 | 각 태스크의 테스트 단계 |
| §13 건드리는 파일 | 위 "파일 구조" |
