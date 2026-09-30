# 저장된 이력의 채널·업로드일 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 정리본 재료 표에 채널·업로드일 열을 더하고, 그 값을 저장된 이력에 캐시로 남기며, 이력 동기화가 Outline 문서 머리에서 읽어 채우게 한다.

**Architecture:** `mark_exported` 가 `run_metadata` 를 지우지 않게 하고, `SUMMARY_SELECT` 가 그 행을 LEFT JOIN 해 `RunSummary.metadata` 에 싣는다. 이력 동기화는 `core/outline_import.find_metadata` 로 문서 머리의 두 줄을 읽어, 새로 만드는 행에는 함께 넣고 기존 행은 값이 다를 때만 갱신한다(`SyncPlan.updates`). 재료 표는 `RunSummary.metadata` 에서 두 열을 그린다.

**Tech Stack:** Python 3.13 · Streamlit 1.64 · SQLite(stdlib `sqlite3`) · pytest + `streamlit.testing.v1.AppTest` · uv · ruff · mypy

**Spec:** `docs/superpowers/specs/2026-09-30-saved-run-metadata-design.md` — 계획은 이 설계서를 근거로 한다. 구현자는 둘 다 읽는다.

## Global Constraints

- 브랜치는 `develop`. 에이전트는 커밋만 하고 **`git push` 하지 않는다.** `--no-verify`·force 금지.
- 커밋 메시지: `<gitmoji> <type>(<scope>): <한국어 명령형 제목, 50자 이내, 마침표 없음>`, 빈 줄, 본문(무엇을·왜, 72칸에서 줄바꿈), 빈 줄, 마지막 줄 `Assisted-by: <커밋하는 에이전트 자신의 모델 ID>`. AI 를 `Co-Authored-By:` 로 적지 않는다.
- `uv` 는 에이전트 셸 PATH 에 없다. 모든 명령은 `/c/Users/susot/.local/bin/uv.exe run …` 로 부른다.
- 완료 전 네 검사를 이 순서로 통과한다: `ruff format .` → `ruff check --fix .` → `mypy src tests` → `pytest`.
- `core/`·`services/` 에서 `import streamlit` 금지.
- import 는 모듈 단위(`from notebooklm_st.core import models`)로만. 함수·클래스를 직접 import 하지 않는다. 예외는 `typing`·`collections.abc`.
- 모든 모듈·클래스·함수·테스트 함수에 한국어 Google 형식 독스트링. 코드 80칸, 독스트링·주석 72칸.
- `from __future__ import annotations` 를 쓰지 않는다. 그래서 **주석에 쓰는 클래스는 먼저 정의돼 있어야 한다**(설계서 §2.6).
- 스키마(`services/store.py`)는 바꾸지 않는다. 새 의존성은 없다.
- 문서에 나가는 라벨은 글자 그대로 `채널`·`업로드 일자`. 표의 열 이름은 `채널`·`업로드일`.
- 화면 문구는 글자 그대로:
  - 동기화 설명 셋째 문장: `채널·업로드일은 문서 머리에서 읽어 채웁니다.`
  - 개수 한 줄의 새 칸: `채널·업로드일 갱신 {n}건` (`만들 문서` 와 `건너뛴 문서` 사이)
  - 결과: `동기화 완료 · 지움 {d}건 · 만듦 {c}건 · 갱신 {u}건`
  - 저장 버튼 도움말: `지금 보이는 그대로 올립니다. 올린 뒤에는 로컬에 링크와 채널·업로드일만 남습니다.`
- 설계·명세 문서(`docs/superpowers/specs/*`)는 최종 상태만 담는다. 고칠 때는 **파일 전체를 다시 쓰고** "원래는·바뀌었다·이제는" 같은 경위를 적지 않는다. 경위는 커밋 메시지에 적는다.
- 계획에 적힌 테스트 단언이 쓰인 그대로는 통과할 수 없으면, **구현을 비틀어 통과시키지 말고** 그 사실과 이유를 보고한다.

## Review Focus

1. **Outline 이 채널명의 짝 기호를 강조로 바꿔 돌려줌**(`- 채널: *투자* 연구소`) — 예외 없이 기호가 남은 값으로 읽히고 업로드 일자는 영향받지 않아야 한다. → Task 1 `test_reads_an_emphasized_channel_without_failing`
2. **문서 본문이 CRLF 줄끝으로 옴** — 두 값을 그대로 읽어야 한다. → Task 1 `test_reads_crlf_line_endings`
3. **로컬 채널명에 겹친 공백이 있고 문서는 접힌 값**(yt-dlp `_clean` vs `one_line`) — 첫 동기화에서 한 번 갱신되고, 다시 계획하면 갱신이 없어야 한다. → Task 4 `test_a_channel_with_doubled_spaces_settles_after_one_apply`
4. **두 값이 모두 빈 옛 `run_metadata` 행**(`VideoMetadata(None, None)`)에 문서 값이 있음 — 갱신으로 채워져야 한다. → Task 4 `test_plan_fills_a_row_whose_values_are_empty`
5. **다른 탭에서 동기화를 적용하는 사이 재료 표에서 골라 둔 재료** — 메타데이터만 바뀌므로 선택이 남아야 한다. → Task 6 `test_table_key_ignores_the_metadata` + Task 8 브라우저 두 탭 확인

---

## File Structure

| 파일 | 책임 | Task |
|---|---|---|
| `src/notebooklm_st/core/markdown_export.py` | 라벨 상수 `CHANNEL_LABEL`·`UPLOAD_DATE_LABEL` | 1 |
| `src/notebooklm_st/core/outline_import.py` | 머리 블록에서 영상 URL 과 메타데이터를 읽는 순수 함수 | 1 |
| `src/notebooklm_st/core/models.py` | `VideoMetadata` 위치 · `RunSummary.metadata` (2) · `SyncCreate.metadata` (3) · `SyncUpdate`·`SyncPlan.updates` (4) | 2·3·4 |
| `src/notebooklm_st/services/run_history.py` | 조회에 메타데이터 조인 · 저장 시 메타데이터 유지 | 2 |
| `src/notebooklm_st/pages/history.py` | 저장 버튼 도움말 한 줄 | 2 |
| `src/notebooklm_st/services/run_history_sync.py` | 되살린 행에 메타데이터 · 기존 행 메타데이터 쓰기 | 3 |
| `src/notebooklm_st/services/history_sync.py` | 계획에 갱신 · 적용에 갱신 · `SyncResult.updated` | 4 |
| `src/notebooklm_st/pages/_history_sync.py` | 설명·개수·결과 문구 | 5 |
| `src/notebooklm_st/pages/_digest_materials.py` | 재료 표 두 열 | 6 |
| `README.md`, 명세 넷 | 문서 | 7 |

---

### Task 1: 문서 머리에서 채널·업로드 일자 읽기

**Files:**
- Modify: `src/notebooklm_st/core/markdown_export.py:25-30` (상수 추가), `:92-95` (`_metadata_block` 두 줄)
- Modify: `src/notebooklm_st/core/outline_import.py` (전체 다시 쓰기)
- Test: `tests/core/test_outline_import.py`

**Interfaces:**
- Consumes: `models.VideoMetadata(channel: str | None, upload_date: str | None)` (이미 있음)
- Produces:
  - `markdown_export.CHANNEL_LABEL: str = "채널"`
  - `markdown_export.UPLOAD_DATE_LABEL: str = "업로드 일자"`
  - `outline_import.find_metadata(markdown: str) -> models.VideoMetadata | None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/core/test_outline_import.py` 의 import 두 줄을 바꾼다.

```python
"""Outline 문서 본문에서 영상 URL 과 메타데이터를 되읽는 함수 테스트."""

import pytest

from notebooklm_st.core import markdown_export, models, outline_import
```

파일 끝에 붙인다. `SUMMARY` 와 `DIGEST` 는 파일 위쪽에 이미 있는 상수다.

```python
def test_finds_the_channel_and_upload_date() -> None:
    """메타데이터 리스트의 채널·업로드 일자 줄을 읽는다."""
    assert outline_import.find_metadata(SUMMARY) == models.VideoMetadata(
        channel="어떤 채널", upload_date="2026-09-20"
    )


def test_metadata_is_none_without_either_line() -> None:
    """두 줄이 다 없으면 빈 메타데이터가 아니라 ``None`` 이다."""
    text = "- 제목: 글\n- 영상 URL: https://youtu.be/dQw4w9WgXcQ\n"

    assert outline_import.find_metadata(text) is None


def test_metadata_keeps_the_one_line_it_found() -> None:
    """한 줄만 있으면 다른 칸은 비운다."""
    assert outline_import.find_metadata(
        "- 채널: 어떤 채널\n"
    ) == models.VideoMetadata(channel="어떤 채널", upload_date=None)


def test_a_digest_body_has_no_metadata() -> None:
    """정리본 본문은 만든 날·정리 지시만 있다."""
    assert outline_import.find_metadata(DIGEST) is None


def test_ignores_metadata_after_the_rule() -> None:
    """첫 구분선 뒤의 같은 줄은 본문이다."""
    text = "- 제목: 글\n\n---\n\n- 채널: 본문 속 채널\n"

    assert outline_import.find_metadata(text) is None


def test_metadata_accepts_star_and_plus_bullets() -> None:
    """Outline 이 글머리표를 ``*``·``+`` 로 다시 쓸 수 있다."""
    text = "* 채널: 어떤 채널\n+ 업로드 일자: 2026-09-20\n"

    assert outline_import.find_metadata(text) == models.VideoMetadata(
        channel="어떤 채널", upload_date="2026-09-20"
    )


def test_unescapes_punctuation_in_the_channel() -> None:
    """채널명 안의 문장부호 이스케이프를 걷는다."""
    text = r"- 채널: 투자\_연구소 \[KR\] 와\!" + "\n"

    found = outline_import.find_metadata(text)

    assert found is not None
    assert found.channel == "투자_연구소 [KR] 와!"


def test_reads_an_escaped_upload_date() -> None:
    """하이픈 앞 역슬래시를 걷고 날짜로 읽는다."""
    text = r"- 업로드 일자: 2026\-09\-20" + "\n"

    assert outline_import.find_metadata(text) == models.VideoMetadata(
        channel=None, upload_date="2026-09-20"
    )


@pytest.mark.parametrize("raw", ["2026-13-40", "20260920", "2026-9-20", "어제"])
def test_an_unreadable_upload_date_is_none(raw: str) -> None:
    """날짜로 읽히지 않는 업로드 일자는 그 칸만 비운다."""
    text = f"- 채널: 어떤 채널\n- 업로드 일자: {raw}\n"

    assert outline_import.find_metadata(text) == models.VideoMetadata(
        channel="어떤 채널", upload_date=None
    )


def test_an_empty_channel_is_none() -> None:
    """라벨만 있고 값이 없으면 그 칸은 없는 것이다."""
    text = "- 채널:\n- 업로드 일자: 2026-09-20\n"

    assert outline_import.find_metadata(text) == models.VideoMetadata(
        channel=None, upload_date="2026-09-20"
    )


def test_a_label_inside_another_value_is_not_read() -> None:
    """다른 라벨의 값 안에 나온 글자는 채널 줄이 아니다."""
    assert outline_import.find_metadata("- 제목: 채널: 가짜\n") is None


def test_takes_the_first_line_of_each_label() -> None:
    """같은 라벨이 둘이면 첫 줄을 쓴다."""
    text = "- 채널: 첫 채널\n- 채널: 둘째 채널\n"

    found = outline_import.find_metadata(text)

    assert found is not None
    assert found.channel == "첫 채널"


def test_a_bad_first_line_is_not_replaced_by_a_later_one() -> None:
    """첫 줄이 비었거나 날짜가 아니면 뒤의 멀쩡한 줄로 넘어가지 않는다."""
    text = (
        "- 채널:\n"
        "- 채널: 둘째 채널\n"
        "- 업로드 일자: 어제\n"
        "- 업로드 일자: 2026-09-20\n"
    )

    assert outline_import.find_metadata(text) is None


def test_reads_an_emphasized_channel_without_failing() -> None:
    """Outline 이 짝 기호를 강조로 바꿔 돌려줘도 기호째 읽는다."""
    text = "- 채널: *투자* 연구소\n- 업로드 일자: 2026-09-20\n"

    assert outline_import.find_metadata(text) == models.VideoMetadata(
        channel="*투자* 연구소", upload_date="2026-09-20"
    )


def test_reads_crlf_line_endings() -> None:
    """CRLF 줄끝이어도 두 값을 읽는다."""
    text = "- 채널: 어떤 채널\r\n- 업로드 일자: 2026-09-20\r\n\r\n---\r\n"

    assert outline_import.find_metadata(text) == models.VideoMetadata(
        channel="어떤 채널", upload_date="2026-09-20"
    )


def test_reads_back_what_the_export_wrote() -> None:
    """저장이 쓴 문서를 같은 값으로 되읽는다.

    쓰는 쪽과 읽는 쪽이 라벨 상수를 함께 쓴다. 한쪽만 바뀌면
    모든 문서의 두 칸이 조용히 빈다.
    """
    summary = models.RunSummary(
        id=1,
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        title="강의",
        created_at="2026-09-20T10:00:00",
        answer_count=0,
    )
    metadata = models.VideoMetadata(
        channel="투자_연구소 [KR]", upload_date="2026-09-20"
    )

    text = markdown_export.to_markdown(summary, [], "강의", metadata)

    assert outline_import.find_metadata(text) == metadata
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/c/Users/susot/.local/bin/uv.exe run pytest tests/core/test_outline_import.py -q`
Expected: 새 테스트 19건(함수 16개, 매개변수 넷 포함)이 `AttributeError: module 'notebooklm_st.core.outline_import' has no attribute 'find_metadata'` 로 FAIL. 기존 테스트는 PASS.

- [ ] **Step 3: 라벨 상수를 만든다**

`src/notebooklm_st/core/markdown_export.py` 의 `SOURCE_URL_LABEL` 독스트링 바로 아래에 더한다.

```python
CHANNEL_LABEL = "채널"
"""메타데이터 리스트에서 채널 줄의 라벨.

``outline_import.find_metadata`` 가 같은 줄을 거꾸로 읽는다.
"""

UPLOAD_DATE_LABEL = "업로드 일자"
"""메타데이터 리스트에서 업로드 일자 줄의 라벨. 읽는 쪽은 채널과 같다."""
```

`_metadata_block` 의 두 줄을 상수로 바꾼다. 나가는 글자는 같다.

```python
    if metadata is not None and metadata.channel:
        lines.append(f"- {CHANNEL_LABEL}: {one_line(metadata.channel)}")
    if metadata is not None and metadata.upload_date:
        lines.append(f"- {UPLOAD_DATE_LABEL}: {metadata.upload_date}")
```

- [ ] **Step 4: `outline_import.py` 를 다시 쓴다**

`find_source_url` 의 동작과 독스트링은 그대로이고, 머리 블록 순회만 `_head_lines` 로 옮긴다. 파일 전체:

```python
"""Outline 문서 본문에서 이력 복원에 필요한 값을 읽는 순수 함수들.

``markdown_export`` 가 문서 첫머리에 쓴 메타데이터 리스트를 거꾸로
읽는 짝이다. Streamlit 도 httpx 도 모른다.

Outline 은 문서를 ProseMirror 편집기에 담아 두었다가 읽을 때 다시
마크다운으로 직렬화한다. 그래서 우리가 쓴 줄이 글자 그대로 돌아온다고
보지 않는다 — 글머리표·링크 모양·역슬래시 이스케이프가 바뀐 줄도
받는다.
"""

import datetime
import re
from collections.abc import Iterator

from notebooklm_st.core import markdown_export, models

_RULE = re.compile(r"^\s*---\s*$")
"""머리 블록을 끝내는 구분선."""

_SOURCE_LINE = re.compile(
    r"^\s*[-*+]\s*"
    + re.escape(markdown_export.SOURCE_URL_LABEL)
    + r":\s*(?:"
    + r"<(?P<angle>[^>\s]+)>"
    + r"|\[[^\]]*\]\((?P<link>[^)\s]+)\)"
    + r"|(?P<bare>\S+)"
    + r")\s*$"
)
"""영상 URL 줄.

글머리표는 ``-``·``*``·``+`` 중 하나다. 값은 ``<URL>``(자동 링크),
``[글](URL)``(링크), 맨 URL 셋 중 하나이며, 주소는 공백이 없는 한
덩어리다. 링크면 글이 아니라 주소 쪽을 쓴다.
"""

_ESCAPE = re.compile(r"\\([_\-*#])")
"""직렬화기가 값 안에 넣을 수 있는 역슬래시 이스케이프."""

_PUNCTUATION_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")
"""CommonMark 가 이스케이프로 인정하는 ASCII 문장부호 앞의 역슬래시.

채널명에는 URL 에 나올 수 없는 문장부호(``[``·``!`` 등)도 나온다.
그래서 영상 URL 줄의 ``_ESCAPE`` 보다 넓다.
"""

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
"""업로드 일자의 모양.

``datetime.date.fromisoformat`` 은 ``20260920`` 도 받으므로 모양을
먼저 본다.
"""


def _labeled_line(label: str) -> re.Pattern[str]:
    """라벨 하나의 메타데이터 줄 패턴을 만든다.

    글머리표는 ``-``·``*``·``+`` 중 하나다. 값은 비어 있어도 맞는다 —
    빈 값을 건너뛰고 뒤의 줄을 찾지 않기 위해서다(``_first_value``).
    """
    return re.compile(
        r"^\s*[-*+]\s*" + re.escape(label) + r":\s*(?P<value>.*?)\s*$"
    )


_CHANNEL_LINE = _labeled_line(markdown_export.CHANNEL_LABEL)
_UPLOAD_DATE_LINE = _labeled_line(markdown_export.UPLOAD_DATE_LABEL)


def find_source_url(markdown: str) -> str | None:
    """문서 머리 블록에서 영상 URL 을 찾는다.

    첫 구분선(``---``) 앞까지만 본다. 답변 본문에 같은 문구가 인용될
    수 있어서다. 구분선이 없으면 전체가 머리 블록이다.

    Outline 의 재직렬화 변형을 받는다. 글머리표가 ``*``·``+`` 여도,
    값이 ``<URL>`` 이나 ``[글](URL)`` 로 감싸여 있어도 주소만 꺼낸다.
    꺼낸 값의 밑줄·하이픈·별표·샵 앞 역슬래시는 걷어 낸다.

    Args:
        markdown: Outline 이 돌려준 문서 본문.

    Returns:
        첫 영상 URL 줄의 값. 줄이 없거나 값이 비었으면 ``None``.
    """
    for line in _head_lines(markdown):
        match = _SOURCE_LINE.match(line)
        if match:
            value = match["angle"] or match["link"] or match["bare"]
            return _ESCAPE.sub(r"\1", value)
    return None


def find_metadata(markdown: str) -> models.VideoMetadata | None:
    """문서 머리 블록에서 채널과 업로드 일자를 찾는다.

    머리 블록의 범위와 글머리표 변형은 ``find_source_url`` 과 같다.
    라벨마다 라벨이 맞는 첫 줄만 본다. 그 값이 비었거나 날짜로 읽히지
    않아도 뒤의 같은 라벨 줄로 넘어가지 않고 그 칸을 비운다 — 우리는
    라벨마다 한 줄만 쓰므로 둘째 줄은 사람이 고친 흔적이고, 어느 줄이
    맞는지 고를 근거가 없다.

    Args:
        markdown: Outline 이 돌려준 문서 본문.

    Returns:
        읽은 값. 못 읽은 칸은 ``None`` 이다. 두 칸 모두 못 읽으면
        ``None`` — 두 값이 빈 메타데이터 행을 만들지 않게 한다.
    """
    channel = _first_value(markdown, _CHANNEL_LINE) or None
    upload_date = _as_date(_first_value(markdown, _UPLOAD_DATE_LINE))
    if channel is None and upload_date is None:
        return None
    return models.VideoMetadata(channel=channel, upload_date=upload_date)


def _head_lines(markdown: str) -> Iterator[str]:
    """머리 블록의 줄을 차례로 내준다.

    첫 구분선에서 멈춘다. 구분선이 없으면 전체를 내준다.
    """
    for line in markdown.splitlines():
        if _RULE.match(line):
            return
        yield line


def _first_value(markdown: str, pattern: re.Pattern[str]) -> str | None:
    """패턴에 맞는 첫 줄의 값을 이스케이프를 걷어 돌려준다.

    Returns:
        그 값. 비어 있을 수 있다. 맞는 줄이 없으면 ``None``.
    """
    for line in _head_lines(markdown):
        match = pattern.match(line)
        if match:
            return _PUNCTUATION_ESCAPE.sub(r"\1", match["value"])
    return None


def _as_date(value: str | None) -> str | None:
    """``YYYY-MM-DD`` 로 읽히는 날짜만 받는다."""
    if value is None or not _DATE.fullmatch(value):
        return None
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return None
    return value
```

- [ ] **Step 5: 통과를 확인한다**

Run: `/c/Users/susot/.local/bin/uv.exe run pytest tests/core/test_outline_import.py tests/core/test_markdown_export.py tests/services/test_history_sync.py -q`
Expected: 전부 PASS. (`test_markdown_export.py` 는 나가는 글자가 같은지, `test_history_sync.py` 는 `find_source_url` 리팩터가 계획을 바꾸지 않는지 본다.)

- [ ] **Step 6: 커밋한다**

```bash
git add src/notebooklm_st/core/markdown_export.py src/notebooklm_st/core/outline_import.py tests/core/test_outline_import.py
git commit -F - <<'EOF'
✨ feat(sync): 문서 머리에서 채널·업로드 일자 읽기

이력 동기화가 저장된 요약본의 채널·업로드일을 채우려면 Outline
문서 머리 블록의 두 줄을 되읽어야 한다. 쓰는 쪽과 읽는 쪽이
라벨 상수를 함께 쓰고, Outline 의 재직렬화 변형(글머리표,
문장부호 이스케이프, CRLF)을 받는다. 첫 줄이 이상하면 그 칸을
비우고 뒤의 줄로 넘어가지 않는다.

Assisted-by: <모델 ID>
EOF
```

---

### Task 2: 저장 뒤에도 메타데이터를 남기고 조회에 싣기

**Files:**
- Modify: `src/notebooklm_st/core/models.py:100-118` (`VideoMetadata` 를 `RunSummary` 위로, `RunSummary.metadata`), `:175-184` (옛 `VideoMetadata` 자리 삭제)
- Modify: `src/notebooklm_st/services/run_history.py:33-62` (`SUMMARY_SELECT`·`row_to_summary`), `:193-245` (`mark_exported`)
- Modify: `src/notebooklm_st/pages/history.py:164` (도움말)
- Test: `tests/services/test_run_history.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `models.RunSummary.metadata: models.VideoMetadata | None = None` — `run_metadata` 행이 없으면 `None`, 있으면 두 값이 비어 있어도 `VideoMetadata`
  - `run_history.list_runs(...)` 와 `run_history_sync.list_exported(...)` 가 돌려주는 요약에 `metadata` 가 실림
  - `run_history.mark_exported(...)` 가 `run_metadata` 를 지우지 않음

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_run_history.py` 의 `test_mark_exported_deletes_the_local_metadata`(307행 근처) **전체를 아래로 바꾼다.**

```python
def test_mark_exported_keeps_the_local_metadata(connection) -> None:
    """메타데이터는 남긴다. 정리본 재료 표가 채널·업로드일을 쓴다."""
    metadata = models.VideoMetadata(
        channel="안될공학", upload_date="2026-09-15"
    )
    run_id = run_history.save_run(connection, make_result(), metadata)

    export(connection, run_id)

    assert run_history.load_metadata(connection, run_id) == metadata
```

`test_list_runs_carries_the_document_link` 바로 아래에 더한다.

```python
def test_list_runs_carries_the_metadata(connection) -> None:
    """메타데이터 행이 요약에 실려 온다."""
    metadata = models.VideoMetadata(
        channel="안될공학", upload_date="2026-09-15"
    )
    run_history.save_run(connection, make_result(), metadata)

    assert run_history.list_runs(connection)[0].metadata == metadata


def test_list_runs_reports_no_metadata_without_a_row(connection) -> None:
    """메타데이터 행이 없으면 ``None`` 이다."""
    run_history.save_run(connection, make_result())

    assert run_history.list_runs(connection)[0].metadata is None


def test_list_runs_keeps_an_empty_metadata_row_apart(connection) -> None:
    """두 값이 빈 행은 행이 없는 것과 다르다."""
    empty = models.VideoMetadata(channel=None, upload_date=None)
    run_history.save_run(connection, make_result(), empty)

    assert run_history.list_runs(connection)[0].metadata == empty


def test_metadata_join_does_not_inflate_the_answer_count(connection) -> None:
    """메타데이터를 조인해도 답변 수가 불지 않는다."""
    run_history.save_run(
        connection,
        make_result(),
        models.VideoMetadata(channel="안될공학", upload_date="2026-09-15"),
    )

    assert run_history.list_runs(connection)[0].answer_count == 2
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/c/Users/susot/.local/bin/uv.exe run pytest tests/services/test_run_history.py -q`
Expected: `test_mark_exported_keeps_the_local_metadata` 가 `assert None == VideoMetadata(...)` 로, 조회 테스트 셋(`carries_the_metadata`·`reports_no_metadata_without_a_row`·`keeps_an_empty_metadata_row_apart`)이 `AttributeError: 'RunSummary' object has no attribute 'metadata'` 로 FAIL. `test_metadata_join_does_not_inflate_the_answer_count` 는 **지금도 PASS** 한다 — 조인을 넣은 뒤에도 PASS 해야 하는 회귀 방지다.

- [ ] **Step 3: 모델을 고친다**

`src/notebooklm_st/core/models.py` 에서 `VideoMetadata` 클래스 블록(데코레이터부터 `upload_date: str | None` 까지)을 잘라 `RunSummary` 의 데코레이터 **바로 위**에 붙인다. 내용은 그대로다. 그다음 `RunSummary` 를 이렇게 바꾼다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class RunSummary:
    """이력 목록에 한 줄로 보여 줄 실행 요약.

    ``exported_at`` 이 채워져 있으면 이 실행은 Outline 으로 넘어갔고
    로컬에는 링크와 영상 메타데이터만 남아 있다. 링크 넷은 항상 함께
    채워지거나 함께 비어 있다.
    """

    id: int
    url: str
    video_id: str
    title: str | None
    created_at: str
    answer_count: int
    outline_id: str | None = None
    outline_url: str | None = None
    outline_title: str | None = None
    exported_at: str | None = None
    metadata: VideoMetadata | None = None
    """``run_metadata`` 행. 행이 없으면 ``None`` — 두 값이 빈 행과
    구분된다."""
```

- [ ] **Step 4: 조회와 저장을 고친다**

`src/notebooklm_st/services/run_history.py` 의 `SUMMARY_SELECT` 를 바꾼다.

```python
SUMMARY_SELECT = (
    "SELECT r.id, r.url, r.video_id, r.title, r.created_at,"
    " r.outline_id, r.outline_url, r.outline_title, r.exported_at,"
    " m.run_id AS metadata_run_id, m.channel, m.upload_date,"
    " COUNT(a.id) AS answer_count"
    " FROM runs AS r"
    " LEFT JOIN answers AS a ON a.run_id = r.id"
    " LEFT JOIN run_metadata AS m ON m.run_id = r.id"
)
"""``list_runs`` 와 ``run_history_sync.list_exported`` 가 함께 쓰는
SELECT 머리.

``run_metadata`` 는 실행 하나에 많아야 한 행이라 조인이 답변 행을
불리지 않는다."""
```

`row_to_summary` 의 `return` 앞에 메타데이터를 만들고 인자에 넘긴다.

```python
    metadata = None
    if row["metadata_run_id"] is not None:
        metadata = models.VideoMetadata(
            channel=row["channel"], upload_date=row["upload_date"]
        )
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
        metadata=metadata,
    )
```

`mark_exported` 에서 `run_metadata` DELETE 세 줄을 지우고 독스트링 앞부분을 바꾼다.

```python
    """문서 링크를 적고 로컬 답변을 지운다.

    두 문장을 커밋 하나로 묶는다. 중간에 죽어도 "본문은 사라졌는데
    링크는 없는" 상태가 생기지 않는다.

    영상 메타데이터(``run_metadata``)는 지우지 않는다. 문서 머리에
    적은 채널·업로드 일자와 같은 값의 캐시로 남아 정리본 재료 표가
    쓴다. 정본은 Outline 이고, 이력 동기화가 문서에서 다시 읽어
    맞춘다.

    Outline 의 자료형을 받지 않고 문자열 셋을 받는다. 저장소가 외부
    서비스를 알 이유가 없다.
```

(`Args:`·`Raises:` 이하는 그대로.) 지우는 코드는 이것이다.

```python
        connection.execute(
            "DELETE FROM run_metadata WHERE run_id = ?", (run_id,)
        )
```

- [ ] **Step 5: 저장 버튼 도움말을 고친다**

`src/notebooklm_st/pages/history.py` 의 `_render_export` 안 `help=` 를 바꾼다.

```python
        help="지금 보이는 그대로 올립니다. 올린 뒤에는 로컬에 링크와"
        " 채널·업로드일만 남습니다.",
```

- [ ] **Step 6: 통과를 확인한다**

Run: `/c/Users/susot/.local/bin/uv.exe run pytest tests/services tests/pages -q`
Expected: 전부 PASS. 특히 `test_mark_exported_rolls_back_a_failed_delete` 가 그대로 PASS 해야 한다.

- [ ] **Step 7: 커밋한다**

```bash
git add src/notebooklm_st/core/models.py src/notebooklm_st/services/run_history.py src/notebooklm_st/pages/history.py tests/services/test_run_history.py
git commit -F - <<'EOF'
✨ feat(history): 저장 뒤에도 영상 메타데이터 남기기

Outline 에 저장할 때 run_metadata 를 지워, 정리본 재료 표에 채널·
업로드일을 그릴 값이 없었다. 메타데이터는 문서 머리와 같은 값의
캐시로 남기고, 요약 조회가 LEFT JOIN 해 RunSummary.metadata 에
싣는다. 행이 없는 것과 두 값이 빈 행은 계속 구분한다. 저장 버튼
도움말도 사실에 맞게 고친다.

Assisted-by: <모델 ID>
EOF
```

---

### Task 3: 되살린 행과 기존 행에 메타데이터 쓰기

**Files:**
- Modify: `src/notebooklm_st/core/models.py` (`SyncCreate`)
- Modify: `src/notebooklm_st/services/run_history_sync.py:42-82` (`insert_exported`), 끝에 `write_metadata` 추가
- Test: `tests/services/test_run_history_sync.py`

**Interfaces:**
- Consumes: `models.RunSummary.metadata` (Task 2), `run_history.mark_exported` 가 메타데이터를 남김 (Task 2)
- Produces:
  - `models.SyncCreate.metadata: models.VideoMetadata | None = None`
  - `run_history_sync.write_metadata(connection: sqlite3.Connection, run_id: int, outline_id: str, metadata: models.VideoMetadata) -> bool` — 새로 넣었거나 값을 바꿨으면 `True`, 맞는 행이 없거나 값이 이미 같으면 `False`. 커밋하지 않음.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_run_history_sync.py` 의 `make_create` 를 바꾼다.

```python
def make_create(
    doc_id: str = "doc-9",
    video_id: str = "dQw4w9WgXcQ",
    metadata: models.VideoMetadata | None = None,
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
        metadata=metadata,
    )
```

`make_create` 아래에 상수와 도우미를 더한다.

```python
METADATA = models.VideoMetadata(channel="안될공학", upload_date="2026-09-15")


def exported_run(
    connection: sqlite3.Connection,
    metadata: models.VideoMetadata | None = None,
) -> int:
    """``doc-1`` 에 저장된 실행 하나를 만든다."""
    run_id = run_history.save_run(connection, make_result(), metadata)
    export(connection, run_id)
    return run_id
```

파일 끝에 붙인다.

```python
def test_list_exported_carries_the_metadata(connection) -> None:
    """저장된 행의 메타데이터가 요약에 실려 온다."""
    exported_run(connection, METADATA)

    assert run_history_sync.list_exported(connection)[0].metadata == METADATA


def test_insert_exported_writes_the_metadata_it_read(connection) -> None:
    """문서에서 읽은 메타데이터로 ``run_metadata`` 행도 만든다."""
    run_id = run_history_sync.insert_exported(
        connection, make_create(metadata=METADATA)
    )
    connection.commit()

    assert run_id is not None
    assert run_history.load_metadata(connection, run_id) == METADATA


def test_insert_exported_writes_nothing_for_an_existing_document(
    connection,
) -> None:
    """이미 있는 문서면 메타데이터도 쓰지 않는다."""
    run_id = exported_run(connection)

    result = run_history_sync.insert_exported(
        connection, make_create("doc-1", metadata=METADATA)
    )
    connection.commit()

    assert result is None
    assert run_history.load_metadata(connection, run_id) is None


def test_write_metadata_inserts_a_missing_row(connection) -> None:
    """행이 없으면 넣고 ``True`` 다."""
    run_id = exported_run(connection)

    written = run_history_sync.write_metadata(
        connection, run_id, "doc-1", METADATA
    )
    connection.commit()

    assert written is True
    assert run_history.load_metadata(connection, run_id) == METADATA


def test_write_metadata_overwrites_a_different_row(connection) -> None:
    """값이 다르면 덮고 ``True`` 다."""
    run_id = exported_run(
        connection, models.VideoMetadata(channel="옛 채널", upload_date=None)
    )

    written = run_history_sync.write_metadata(
        connection, run_id, "doc-1", METADATA
    )
    connection.commit()

    assert written is True
    assert run_history.load_metadata(connection, run_id) == METADATA


def test_write_metadata_reports_an_unchanged_row(connection) -> None:
    """값이 이미 같으면 덮지 않고 ``False`` 다."""
    run_id = exported_run(connection, METADATA)

    written = run_history_sync.write_metadata(
        connection, run_id, "doc-1", METADATA
    )

    assert written is False
    assert run_history.load_metadata(connection, run_id) == METADATA


def test_write_metadata_needs_the_document_id_to_match(connection) -> None:
    """실행 ID 와 문서 ID 가 둘 다 맞아야 쓴다.

    SQLite 는 지워진 가장 큰 ID 를 다음 삽입에 다시 준다. 그 ID 를
    받은 미저장 실행에 남의 메타데이터가 쓰이면 안 된다.
    """
    exported = exported_run(connection)
    unexported = run_history.save_run(connection, make_result())

    wrong_document = run_history_sync.write_metadata(
        connection, exported, "doc-other", METADATA
    )
    unsaved = run_history_sync.write_metadata(
        connection, unexported, "doc-1", METADATA
    )
    connection.commit()

    assert wrong_document is False
    assert unsaved is False
    assert run_history.load_metadata(connection, exported) is None
    assert run_history.load_metadata(connection, unexported) is None


def test_write_metadata_does_not_commit(connection) -> None:
    """트랜잭션은 호출자가 소유한다."""
    run_id = exported_run(connection)

    run_history_sync.write_metadata(connection, run_id, "doc-1", METADATA)
    connection.rollback()

    assert run_history.load_metadata(connection, run_id) is None
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/c/Users/susot/.local/bin/uv.exe run pytest tests/services/test_run_history_sync.py -q`
Expected: `make_create` 를 쓰는 테스트(기존 `insert_exported` 넷·`list_video_ids` 하나와 새 둘)가 `TypeError: SyncCreate.__init__() got an unexpected keyword argument 'metadata'` 로, `write_metadata` 테스트 다섯이 `AttributeError: … has no attribute 'write_metadata'` 로 FAIL. `test_list_exported_carries_the_metadata` 와 `delete_runs` 테스트는 PASS.

- [ ] **Step 3: `SyncCreate` 에 필드를 더한다**

`src/notebooklm_st/core/models.py` 의 `SyncCreate`:

```python
@dataclasses.dataclass(frozen=True, slots=True)
class SyncCreate:
    """동기화가 새로 만들 이력 한 건."""

    document: ListedDocument
    url: str
    """본문에서 읽은 영상 URL."""
    video_id: str
    metadata: VideoMetadata | None = None
    """문서 머리에서 읽은 채널·업로드 일자. 두 줄이 다 없으면 ``None``."""
```

(`VideoMetadata` 는 Task 2 에서 `RunSummary` 위로 옮겼으므로 여기서 쓸 수 있다.)

- [ ] **Step 4: `insert_exported` 를 고치고 `write_metadata` 를 더한다**

`src/notebooklm_st/services/run_history_sync.py` 의 `insert_exported` 에서 독스트링 셋째 문단과 마지막 `return` 을 바꾼다.

```python
    ``answers`` 행은 만들지 않는다. 저장된 실행은 원래 본문이 없다.
    문서 머리에서 읽은 메타데이터가 있으면 ``run_metadata`` 행을 함께
    만든다.
```

```python
    run_id = int(row["id"])
    if create.metadata is not None:
        connection.execute(
            "INSERT INTO run_metadata (run_id, channel, upload_date)"
            " VALUES (?, ?, ?)",
            (run_id, create.metadata.channel, create.metadata.upload_date),
        )
    return run_id
```

파일 끝(`delete_runs` 아래)에 더한다.

```python
def write_metadata(
    connection: sqlite3.Connection,
    run_id: int,
    outline_id: str,
    metadata: models.VideoMetadata,
) -> bool:
    """저장된 행 하나의 메타데이터를 넣거나 덮는다.

    **커밋하지 않는다.** 트랜잭션은 ``history_sync.apply`` 가 소유한다.
    실행 ID 와 문서 ID 가 둘 다 맞는 행에만 쓴다 — ``delete_runs`` 와
    같은 이유로, 다시 쓰인 ID 의 미저장 실행을 건드리지 않는다.

    값이 이미 같으면 덮지 않는다. 적용 결과의 갱신 건수가 실제로
    바뀐 행만 세게 한다.

    SQLite 는 ``INSERT … SELECT`` 에 ``WHERE`` 가 있어야 뒤의
    ``ON CONFLICT`` 를 upsert 절로 읽는다. 두 조건이 그 ``WHERE`` 다.

    Args:
        connection: 열린 커넥션.
        run_id: 쓸 실행의 ID.
        outline_id: 그 실행이 가리켜야 할 문서 ID.
        metadata: 쓸 값.

    Returns:
        새로 넣었거나 값을 바꿨으면 ``True``. 맞는 행이 없거나 값이
        이미 같으면 ``False``.
    """
    cursor = connection.execute(
        "INSERT INTO run_metadata (run_id, channel, upload_date)"
        " SELECT id, ?, ? FROM runs WHERE id = ? AND outline_id = ?"
        " ON CONFLICT(run_id) DO UPDATE SET"
        " channel = excluded.channel,"
        " upload_date = excluded.upload_date"
        " WHERE channel IS NOT excluded.channel"
        " OR upload_date IS NOT excluded.upload_date",
        (metadata.channel, metadata.upload_date, run_id, outline_id),
    )
    return cursor.rowcount > 0
```

- [ ] **Step 5: 통과를 확인한다**

Run: `/c/Users/susot/.local/bin/uv.exe run pytest tests/services -q`
Expected: 전부 PASS.

- [ ] **Step 6: 커밋한다**

```bash
git add src/notebooklm_st/core/models.py src/notebooklm_st/services/run_history_sync.py tests/services/test_run_history_sync.py
git commit -F - <<'EOF'
✨ feat(sync): 되살린 행과 기존 행에 메타데이터 쓰기

동기화가 문서에서 읽은 채널·업로드일을 DB 에 쓸 자리를 만든다.
되살리는 행은 run_metadata 를 함께 넣고, 기존 행은 실행 ID 와
문서 ID 가 둘 다 맞을 때만 upsert 한다. 값이 같으면 덮지 않아
갱신 건수가 실제로 바뀐 행만 센다.

Assisted-by: <모델 ID>
EOF
```

---

### Task 4: 동기화 계획과 적용에 메타데이터 갱신 더하기

**Files:**
- Modify: `src/notebooklm_st/core/models.py` (`SyncUpdate` 추가, `SyncPlan`)
- Modify: `src/notebooklm_st/services/history_sync.py` (`plan`, `_updates`, `_merge`, `SyncResult`, `apply`)
- Test: `tests/services/test_history_sync.py`

**Interfaces:**
- Consumes: `outline_import.find_metadata` (Task 1), `RunSummary.metadata` (Task 2), `SyncCreate.metadata`·`run_history_sync.write_metadata` (Task 3)
- Produces:
  - `models.SyncUpdate(run: RunSummary, metadata: VideoMetadata)`
  - `models.SyncPlan.updates: tuple[SyncUpdate, ...] = ()`, `is_empty` 는 셋 다 비었을 때만 참
  - `history_sync.SyncResult.updated: int = 0`
  - `history_sync.plan(...)` 이 `creates[*].metadata` 와 `updates` 를 채움

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_history_sync.py` 의 `SUMMARY_BODY` 아래에 더한다.

```python
METADATA_BODY = (
    "- 제목: 밸류에이션 강의\n"
    "- 채널: 어떤 채널\n"
    "- 업로드 일자: 2026-09-20\n"
    "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
    "\n---\n\n## 핵심 주장\n\n세 가지다.\n"
)

DOC_METADATA = models.VideoMetadata(
    channel="어떤 채널", upload_date="2026-09-20"
)
```

`make_run` 에 인자를 더한다.

```python
def make_run(
    run_id: int,
    outline_id: str,
    metadata: models.VideoMetadata | None = None,
) -> models.RunSummary:
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
        metadata=metadata,
    )
```

`test_an_empty_plan_says_so` 아래(커넥션 fixture 위)에 계획 테스트를 더한다.

```python
def test_plan_carries_the_metadata_of_a_new_document() -> None:
    """생성 대상에 문서 머리의 메타데이터가 실린다."""
    result = history_sync.plan([], [make_document("doc-9", METADATA_BODY)])

    assert result.creates[0].metadata == DOC_METADATA


def test_plan_creates_without_metadata_when_the_head_has_none() -> None:
    """두 줄이 없으면 생성 대상의 메타데이터는 ``None`` 이다."""
    result = history_sync.plan([], [make_document("doc-9")])

    assert result.creates[0].metadata is None


def test_plan_updates_a_run_without_metadata() -> None:
    """로컬에 메타데이터가 없고 문서가 주면 갱신 대상이다."""
    run = make_run(1, "doc-1")

    result = history_sync.plan([run], [make_document("doc-1", METADATA_BODY)])

    assert result.updates == (
        models.SyncUpdate(run=run, metadata=DOC_METADATA),
    )
    assert result.deletes == ()
    assert result.creates == ()
    assert not result.is_empty


def test_plan_leaves_equal_metadata_alone() -> None:
    """합친 값이 로컬과 같으면 손대지 않는다."""
    run = make_run(1, "doc-1", DOC_METADATA)

    result = history_sync.plan([run], [make_document("doc-1", METADATA_BODY)])

    assert result.updates == ()
    assert result.is_empty


def test_plan_overwrites_a_different_value() -> None:
    """문서 값이 로컬과 다르면 문서 값으로 덮는다."""
    run = make_run(
        1,
        "doc-1",
        models.VideoMetadata(channel="옛 채널", upload_date="2026-09-20"),
    )

    result = history_sync.plan([run], [make_document("doc-1", METADATA_BODY)])

    assert [update.metadata for update in result.updates] == [DOC_METADATA]


def test_plan_never_clears_local_metadata() -> None:
    """문서에서 두 값을 못 읽으면 로컬 값을 그대로 둔다."""
    run = make_run(1, "doc-1", DOC_METADATA)

    result = history_sync.plan([run], [make_document("doc-1")])

    assert result.updates == ()


def test_plan_merges_field_by_field() -> None:
    """문서가 준 칸은 문서 값, 주지 않은 칸은 로컬 값이다."""
    run = make_run(
        1, "doc-1", models.VideoMetadata(channel="A", upload_date=None)
    )
    body = (
        "- 업로드 일자: 2026-09-20\n"
        "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
    )

    result = history_sync.plan([run], [make_document("doc-1", body)])

    assert [update.metadata for update in result.updates] == [
        models.VideoMetadata(channel="A", upload_date="2026-09-20")
    ]


def test_plan_fills_a_row_whose_values_are_empty() -> None:
    """두 값이 빈 옛 행도 문서 값으로 채운다."""
    run = make_run(
        1, "doc-1", models.VideoMetadata(channel=None, upload_date=None)
    )

    result = history_sync.plan([run], [make_document("doc-1", METADATA_BODY)])

    assert [update.metadata for update in result.updates] == [DOC_METADATA]


def test_plan_judges_two_runs_on_one_document_separately() -> None:
    """같은 문서를 가리키는 행 둘은 따로 판정한다."""
    runs = [make_run(1, "doc-1", DOC_METADATA), make_run(2, "doc-1")]

    result = history_sync.plan(runs, [make_document("doc-1", METADATA_BODY)])

    assert [update.run.id for update in result.updates] == [2]


def test_plan_does_not_update_a_run_being_deleted() -> None:
    """문서가 없는 행은 지울 뿐 갱신하지 않는다."""
    result = history_sync.plan([make_run(1, "gone")], [])

    assert [run.id for run in result.deletes] == [1]
    assert result.updates == ()


def test_an_update_only_plan_is_not_empty() -> None:
    """갱신만 있어도 적용할 것이 있다."""
    plan = models.SyncPlan(
        deletes=(),
        creates=(),
        skips=(),
        updates=(
            models.SyncUpdate(
                run=make_run(1, "doc-1"), metadata=DOC_METADATA
            ),
        ),
    )

    assert not plan.is_empty
```

`save_exported` 에 인자를 더한다.

```python
def save_exported(
    connection: sqlite3.Connection,
    doc_id: str,
    metadata: models.VideoMetadata | None = None,
) -> int:
    """저장된 실행 하나를 DB 에 만든다."""
    run_id = run_history.save_run(
        connection,
        models.RunResult(
            url="https://youtu.be/dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
            title="원래 제목",
            items=(),
        ),
        metadata,
    )
    run_history.mark_exported(
        connection,
        run_id,
        document_id=doc_id,
        document_title="정리한 제목",
        document_url=f"https://wiki.example.com/doc/{doc_id}",
    )
    return run_id
```

파일 끝에 적용 테스트를 더한다.

```python
class FailingMetadataWrite:
    """메타데이터 쓰기 문장에서만 터지는 커넥션 대역.

    나머지 호출은 진짜 커넥션이 그대로 처리한다. 삭제·삽입은 됐는데
    갱신이 죽는 상황을 재현한다.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """감쌀 진짜 커넥션을 받는다."""
        self._connection = connection

    def execute(self, sql, *args):
        """메타데이터를 넣는 문장만 실패시킨다."""
        if "INSERT INTO run_metadata" in sql:
            raise sqlite3.OperationalError("database is locked")
        return self._connection.execute(sql, *args)

    def __getattr__(self, name):
        """나머지 속성은 진짜 커넥션에 맡긴다."""
        return getattr(self._connection, name)


def test_apply_writes_updates_in_the_same_commit(connection) -> None:
    """갱신이 확정되고 건수가 결과에 실린다."""
    run_id = save_exported(connection, "doc-1")
    plan = models.SyncPlan(
        deletes=(),
        creates=(),
        skips=(),
        updates=(
            models.SyncUpdate(
                run=make_run(run_id, "doc-1"), metadata=DOC_METADATA
            ),
        ),
    )

    result = history_sync.apply(connection, plan)

    assert not connection.in_transaction
    assert result == history_sync.SyncResult(deleted=0, created=0, updated=1)
    assert run_history_sync.list_exported(connection)[0].metadata == (
        DOC_METADATA
    )


def test_apply_rolls_back_everything_when_an_update_fails(
    connection,
) -> None:
    """갱신이 죽으면 삭제와 삽입도 되돌린다."""
    gone = save_exported(connection, "gone")
    kept = save_exported(connection, "kept")
    plan = models.SyncPlan(
        deletes=(make_run(gone, "gone"),),
        creates=(create_for("new-1"),),
        skips=(),
        updates=(
            models.SyncUpdate(
                run=make_run(kept, "kept"), metadata=DOC_METADATA
            ),
        ),
    )

    with pytest.raises(sqlite3.OperationalError):
        # FailingMetadataWrite 는 진짜 Connection 이 아니라 일부 호출만
        # 가로채는 대역이다. 구조적으로는 호환되지만 nominal 타입은
        # 아니므로 억제한다.
        failing = FailingMetadataWrite(connection)
        history_sync.apply(failing, plan)  # type: ignore[arg-type]

    runs = run_history_sync.list_exported(connection)
    assert [run.outline_id for run in runs] == ["kept", "gone"]
    assert [run.metadata for run in runs] == [None, None]


def test_apply_does_not_write_an_update_to_a_reused_id(connection) -> None:
    """낡은 계획의 갱신은 같은 ID 를 다시 받은 미저장 실행에 쓰지 않는다."""
    gone = save_exported(connection, "doc-1")
    stale = history_sync.plan(
        run_history_sync.list_exported(connection),
        [make_document("doc-1", METADATA_BODY)],
    )
    assert [update.run.id for update in stale.updates] == [gone]
    run_history.delete_run(connection, gone)
    reused = run_history.save_run(
        connection,
        models.RunResult(
            url="https://youtu.be/dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
            title="새 실행",
            items=(),
        ),
    )
    assert reused == gone

    result = history_sync.apply(connection, stale)

    assert result.updated == 0
    assert run_history.load_metadata(connection, reused) is None


def test_applying_the_same_plan_twice_updates_once(connection) -> None:
    """다른 탭이 같은 계획을 먼저 적용했으면 두 번째는 0 건이다."""
    save_exported(connection, "doc-1")
    plan = history_sync.plan(
        run_history_sync.list_exported(connection),
        [make_document("doc-1", METADATA_BODY)],
    )

    first = history_sync.apply(connection, plan)
    second = history_sync.apply(connection, plan)

    assert first.updated == 1
    assert second.updated == 0


def test_a_second_plan_after_apply_has_no_updates(connection) -> None:
    """적용한 뒤 다시 계획하면 갱신할 것이 없다(갱신 경로)."""
    save_exported(connection, "doc-1")
    documents = [make_document("doc-1", METADATA_BODY)]
    history_sync.apply(
        connection,
        history_sync.plan(
            run_history_sync.list_exported(connection), documents
        ),
    )

    again = history_sync.plan(
        run_history_sync.list_exported(connection), documents
    )

    assert again.updates == ()
    assert again.is_empty


def test_a_revived_run_needs_no_update_on_the_next_plan(connection) -> None:
    """메타데이터를 실어 되살린 행은 다음 계획에 오르지 않는다."""
    documents = [make_document("new-1", METADATA_BODY)]
    history_sync.apply(
        connection,
        history_sync.plan(
            run_history_sync.list_exported(connection), documents
        ),
    )

    again = history_sync.plan(
        run_history_sync.list_exported(connection), documents
    )

    assert again.is_empty
    assert run_history_sync.list_exported(connection)[0].metadata == (
        DOC_METADATA
    )


def test_a_channel_with_doubled_spaces_settles_after_one_apply(
    connection,
) -> None:
    """로컬 값과 문서 값의 공백 차이는 한 번 갱신하면 사라진다.

    로컬은 yt-dlp 값의 앞뒤 공백만 뗀 것이고, 문서는 ``one_line`` 으로
    공백을 접은 것이다.
    """
    save_exported(
        connection,
        "doc-1",
        models.VideoMetadata(channel="투자  연구소", upload_date="2026-09-20"),
    )
    body = (
        "- 채널: 투자 연구소\n"
        "- 업로드 일자: 2026-09-20\n"
        "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
    )
    documents = [make_document("doc-1", body)]

    first = history_sync.plan(
        run_history_sync.list_exported(connection), documents
    )
    history_sync.apply(connection, first)
    second = history_sync.plan(
        run_history_sync.list_exported(connection), documents
    )

    assert [update.metadata.channel for update in first.updates] == [
        "투자 연구소"
    ]
    assert second.updates == ()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/c/Users/susot/.local/bin/uv.exe run pytest tests/services/test_history_sync.py -q`
Expected: `make_run` 이 `metadata=` 를 넘기므로 Task 2 덕에 기존 테스트는 PASS. 새 계획 테스트는 `AttributeError: 'SyncPlan' object has no attribute 'updates'` 또는 `module 'notebooklm_st.core.models' has no attribute 'SyncUpdate'` 로 FAIL. 새 적용 테스트도 같은 이유로 FAIL. `test_plan_carries_the_metadata_of_a_new_document` 는 `assert None == VideoMetadata(...)` 로 FAIL.

- [ ] **Step 3: 모델을 더한다**

`src/notebooklm_st/core/models.py` 에서 `SyncSkip` 과 `SyncPlan` **사이**에 넣는다(`SyncPlan` 이 주석에 쓰므로 위에 있어야 한다).

```python
@dataclasses.dataclass(frozen=True, slots=True)
class SyncUpdate:
    """동기화가 메타데이터를 갱신할 기존 행 한 건."""

    run: RunSummary
    metadata: VideoMetadata
    """쓸 값. 문서가 준 칸과 로컬에 남길 칸을 합친 결과다."""
```

`SyncPlan` 을 바꾼다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class SyncPlan:
    """미리보기와 적용이 함께 쓰는 동기화 계획.

    기존 행 중 손대지 않는 것은 담지 않는다. 화면이
    보여 줄 것은 바뀌는 것뿐이다.
    """

    deletes: tuple[RunSummary, ...]
    creates: tuple[SyncCreate, ...]
    skips: tuple[SyncSkip, ...]
    updates: tuple[SyncUpdate, ...] = ()

    @property
    def is_empty(self) -> bool:
        """지울 것도 만들 것도 갱신할 것도 없다."""
        return not self.deletes and not self.creates and not self.updates
```

- [ ] **Step 4: 계획과 적용을 고친다**

`src/notebooklm_st/services/history_sync.py` 의 import 를 바꾼다.

```python
from collections.abc import Iterator, Mapping, Sequence
```

`plan` 전체를 바꾼다.

```python
def plan(
    exported: Sequence[models.RunSummary],
    documents: Sequence[models.ListedDocument],
) -> models.SyncPlan:
    """두 목록을 문서 ID 로 맞춰 동기화 계획을 세운다.

    문서 목록에 없는 행은 지우고, 어떤 행도 가리키지 않는
    문서는 본문에 영상 URL 이 있을 때만 만든다. 둘 다 있는 행은
    문서 머리의 채널·업로드 일자가 로컬과 다를 때만 메타데이터를
    갱신한다. 같은 문서를 가리키는 행이 둘이어도, 같은 영상의 문서가
    둘이어도 정리하지 않는다 — 동기화는 중복을 만들지 않을 뿐이다.

    Args:
        exported: ``exported_at`` 이 있는 행들. 미저장
            실행은 여기 들어오지 않으므로 삭제될 수 없다.
        documents: 컬렉션의 문서 전부.

    Returns:
        입력 순서를 지킨 계획.
    """
    known_ids = {run.outline_id for run in exported}
    listed = {document.id: document for document in documents}
    deletes = tuple(run for run in exported if run.outline_id not in listed)
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
                models.SyncSkip(document=document, reason=SKIP_BAD_SOURCE_URL)
            )
            continue
        creates.append(
            models.SyncCreate(
                document=document,
                url=url,
                video_id=video_id,
                metadata=outline_import.find_metadata(document.markdown),
            )
        )
    return models.SyncPlan(
        deletes=deletes,
        creates=tuple(creates),
        skips=tuple(skips),
        updates=tuple(_updates(exported, listed)),
    )


def _updates(
    exported: Sequence[models.RunSummary],
    listed: Mapping[str, models.ListedDocument],
) -> Iterator[models.SyncUpdate]:
    """문서 머리의 메타데이터가 로컬과 다른 기존 행을 입력 순서로 고른다.

    문서에서 두 값을 모두 못 읽으면 그 행은 건드리지 않는다.
    직렬화가 바뀌어 파싱이 실패할 때 멀쩡한 로컬 값이 한꺼번에 비지
    않게 한다.
    """
    for run in exported:
        document = listed.get(run.outline_id or "")
        if document is None:
            continue
        found = outline_import.find_metadata(document.markdown)
        if found is None:
            continue
        merged = _merge(run.metadata, found)
        if merged != run.metadata:
            yield models.SyncUpdate(run=run, metadata=merged)


def _merge(
    local: models.VideoMetadata | None, found: models.VideoMetadata
) -> models.VideoMetadata:
    """문서가 준 칸은 문서 값, 주지 않은 칸은 로컬 값으로 합친다."""
    kept = local or models.VideoMetadata(channel=None, upload_date=None)
    return models.VideoMetadata(
        channel=found.channel if found.channel is not None else kept.channel,
        upload_date=(
            found.upload_date
            if found.upload_date is not None
            else kept.upload_date
        ),
    )
```

`SyncResult` 에 필드를 더한다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class SyncResult:
    """적용이 실제로 바꾼 개수.

    계획의 개수와 다를 수 있다. 미리보기와 적용 사이에 다른 탭이
    먼저 지우거나 저장했을 수 있다.
    """

    deleted: int
    created: int
    updated: int = 0
    """메타데이터를 새로 넣거나 값을 바꾼 행 수."""
```

`apply` 의 독스트링 첫 줄과 `Returns:`, 그리고 본문을 바꾼다.

```python
    """계획을 DB 에 쓴다. 삭제·삽입·갱신을 커밋 하나로 묶는다.
```

```python
    Returns:
        실제로 지운·만든·갱신한 개수.
```

```python
    try:
        deleted = run_history_sync.delete_runs(
            connection,
            [(run.id, run.outline_id or "") for run in sync_plan.deletes],
        )
        created = 0
        for create in sync_plan.creates:
            inserted = run_history_sync.insert_exported(connection, create)
            if inserted is not None:
                created += 1
        updated = 0
        for update in sync_plan.updates:
            if run_history_sync.write_metadata(
                connection,
                update.run.id,
                update.run.outline_id or "",
                update.metadata,
            ):
                updated += 1
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return SyncResult(deleted=deleted, created=created, updated=updated)
```

(`Raises:` 의 "삭제나 삽입이" 는 "삭제·삽입·갱신이" 로 고친다.)

- [ ] **Step 5: 통과를 확인한다**

Run: `/c/Users/susot/.local/bin/uv.exe run pytest tests/services tests/core -q`
Expected: 전부 PASS. 기존 `SyncResult(deleted=1, created=1)` 비교는 기본값 덕에 그대로 PASS.

- [ ] **Step 6: 커밋한다**

```bash
git add src/notebooklm_st/core/models.py src/notebooklm_st/services/history_sync.py tests/services/test_history_sync.py
git commit -F - <<'EOF'
✨ feat(sync): 동기화 계획에 메타데이터 갱신 더하기

이미 저장된 요약본의 채널·업로드일은 동기화만 채울 수 있다. 계획이
문서 머리의 값을 칸별로 로컬과 합쳐, 다르면 갱신 대상으로 올린다.
문서에서 못 읽은 칸은 로컬 값을 지우지 않는다. 적용은 삭제·삽입과
같은 커밋에서 갱신하고 실제로 바뀐 건수를 돌려준다.

Assisted-by: <모델 ID>
EOF
```

---

### Task 5: 동기화 화면에 갱신 건수 보이기

**Files:**
- Modify: `src/notebooklm_st/pages/_history_sync.py:32-36` (설명), `:72-83` (`_render_plan`), `:136-138` (결과)
- Test: `tests/pages/test_history.py`

**Interfaces:**
- Consumes: `SyncPlan.updates`·`is_empty`, `SyncResult.updated` (Task 4)
- Produces: 화면 문구(Global Constraints)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_history.py` 648행의 단언을 바꾼다.

```python
    assert (
        "지울 이력 1건 · 만들 문서 1건 · 채널·업로드일 갱신 0건"
        " · 건너뛴 문서 1건"
    ) in text
```

`SYNC_BODY` 아래에 더한다.

```python
SYNC_META_BODY = (
    "- 제목: 되살릴 문서\n"
    "- 채널: 어떤 채널\n"
    "- 업로드 일자: 2026-09-20\n"
    "- 영상 URL: https://www.youtube.com/watch?v=aaaaaaaaaaa\n"
    "\n---\n\n## 핵심 주장\n\n세 가지다.\n"
)
```

`test_sync_with_nothing_to_do_hides_the_apply_button` 아래에 더한다. (`export` 는 `doc-1` 로 저장하는 이 파일의 도우미다.)

```python
def test_sync_previews_a_metadata_update(app_db, monkeypatch) -> None:
    """갱신만 있어도 건수가 보이고 적용 버튼이 나온다."""
    set_outline_env(monkeypatch)
    run_id = run_history.save_run(app_db, make_result())
    export(app_db, run_id)
    monkeypatch.setattr(
        outline, "list_documents", fake_list([listed("doc-1", SYNC_META_BODY)])
    )

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_sync_check").click().run()

    assert not app.exception
    assert "채널·업로드일 갱신 1건" in rendered_markdown(app)
    assert "history_sync_apply" in [e.key for e in app.button]


def test_sync_apply_fills_the_metadata(app_db, monkeypatch) -> None:
    """적용하면 메타데이터가 채워지고 결과 문구에 갱신 건수가 나온다."""
    set_outline_env(monkeypatch)
    run_id = run_history.save_run(app_db, make_result())
    export(app_db, run_id)
    monkeypatch.setattr(
        outline, "list_documents", fake_list([listed("doc-1", SYNC_META_BODY)])
    )

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_sync_check").click().run()
    app.button(key="history_sync_apply").click().run()

    assert not app.exception
    assert "갱신 1건" in app.success[0].value
    assert run_history_sync.list_exported(app_db)[0].metadata == (
        models.VideoMetadata(channel="어떤 채널", upload_date="2026-09-20")
    )


def test_sync_with_equal_metadata_is_already_in_step(
    app_db, monkeypatch
) -> None:
    """메타데이터까지 같으면 이미 맞다."""
    set_outline_env(monkeypatch)
    run_id = run_history.save_run(
        app_db,
        make_result(),
        models.VideoMetadata(channel="어떤 채널", upload_date="2026-09-20"),
    )
    export(app_db, run_id)
    monkeypatch.setattr(
        outline, "list_documents", fake_list([listed("doc-1", SYNC_META_BODY)])
    )

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_sync_check").click().run()

    assert not app.exception
    assert "history_sync_apply" not in [e.key for e in app.button]
    messages = " ".join(element.value for element in app.info)
    assert "이미 맞습니다" in messages
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/c/Users/susot/.local/bin/uv.exe run pytest tests/pages/test_history.py -q`
Expected: `test_sync_check_previews_the_counts_and_lists` 와 `test_sync_previews_a_metadata_update`(문구 없음), `test_sync_apply_fills_the_metadata`(`"갱신 1건"` 없음)가 FAIL. `test_sync_with_equal_metadata_is_already_in_step` 은 Task 4 덕에 이미 PASS 할 수 있다 — 회귀 방지다.

- [ ] **Step 3: 화면을 고친다**

`src/notebooklm_st/pages/_history_sync.py` 의 설명 문구:

```python
        st.caption(
            "Outline 컬렉션의 문서 목록과 저장된 이력을 맞춥니다."
            " Outline 에 없는 이력은 지우고, 이력에 없는 문서는 새로"
            " 만듭니다. 채널·업로드일은 문서 머리에서 읽어 채웁니다."
        )
```

`_render_plan` 의 독스트링과 개수 한 줄:

```python
    """미리보기와 적용·취소 버튼을 그린다.

    expander 는 중첩할 수 없으므로 세 목록은 마크다운으로 그린다.
    채널·업로드일 갱신은 개수만 그린다. 처음 채울 때는 저장된 요약본
    전부가 대상이라 목록이 길다.
    """
    st.markdown(
        f"지울 이력 {len(sync_plan.deletes)}건"
        f" · 만들 문서 {len(sync_plan.creates)}건"
        f" · 채널·업로드일 갱신 {len(sync_plan.updates)}건"
        f" · 건너뛴 문서 {len(sync_plan.skips)}건"
    )
```

`_apply` 의 결과 문구:

```python
    st.session_state[_RESULT_KEY] = (
        f"동기화 완료 · 지움 {result.deleted}건 · 만듦 {result.created}건"
        f" · 갱신 {result.updated}건"
    )
```

- [ ] **Step 4: 통과를 확인한다**

Run: `/c/Users/susot/.local/bin/uv.exe run pytest tests/pages/test_history.py -q`
Expected: 전부 PASS. 기존 `"지움 1건 · 만듦 1건" in app.success[0].value` 도 그대로 PASS.

- [ ] **Step 5: 커밋한다**

```bash
git add src/notebooklm_st/pages/_history_sync.py tests/pages/test_history.py
git commit -F - <<'EOF'
✨ feat(history): 동기화 미리보기에 갱신 건수 표시

동기화가 채널·업로드일을 채운다는 사실과 그 건수를 적용 전에
보여 준다. 갱신만 있어도 적용 버튼이 나오고, 결과 문구에 실제
갱신 건수를 더한다. 첫 동기화는 저장본 전부가 대상이라 목록은
그리지 않는다.

Assisted-by: <모델 ID>
EOF
```

---

### Task 6: 재료 표에 채널·업로드일 열 더하기

**Files:**
- Modify: `src/notebooklm_st/pages/_digest_materials.py:38-50` (`column_config`), `:74-80` (`_row`)
- Test: `tests/pages/test_digest.py`

**Interfaces:**
- Consumes: `RunSummary.metadata` (Task 2), `mark_exported` 가 메타데이터를 남김 (Task 2)
- Produces: 표 열 키 `title`·`channel`·`upload_date`·`created_at`·`url` (이 순서)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_digest.py` 맨 위 import 에 `import dataclasses` 를 더한다(`import sqlite3` 위).

`save_exported` 에 인자를 더한다.

```python
def save_exported(
    connection: sqlite3.Connection,
    document_title: str = "밸류에이션 강의",
    document_id: str = "doc-1",
    metadata: models.VideoMetadata | None = None,
) -> int:
    """Outline 에 저장까지 끝난 실행 하나를 만든다."""
    run_id = run_history.save_run(connection, make_result(), metadata)
    run_history.mark_exported(
        connection,
        run_id,
        document_id=document_id,
        document_title=document_title,
        document_url=f"{BASE_URL}/doc/{document_id}",
    )
    return run_id
```

`test_saved_runs_older_than_the_recent_fifty_are_listed` 아래에 더한다.

```python
def test_table_shows_the_channel_and_upload_date(app_db, outline_env) -> None:
    """저장한 요약본의 채널·업로드일이 표에 나온다."""
    save_exported(
        app_db,
        metadata=models.VideoMetadata(
            channel="어떤 채널", upload_date="2026-09-20"
        ),
    )

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    table = app.dataframe[0].value
    assert list(table["channel"]) == ["어떤 채널"]
    assert list(table["upload_date"]) == ["2026-09-20"]


def test_table_leaves_missing_metadata_blank(app_db, outline_env) -> None:
    """메타데이터가 없는 요약본은 두 칸이 빈다."""
    save_exported(app_db)

    app = v1.AppTest.from_function(script).run()

    table = app.dataframe[0].value
    assert table["channel"].isna().all()
    assert table["upload_date"].isna().all()


def test_table_columns_come_in_order(app_db, outline_env) -> None:
    """고르는 기준이 제목 다음에 오고 시각은 뒤로 간다."""
    save_exported(app_db)

    app = v1.AppTest.from_function(script).run()

    assert list(app.dataframe[0].value.columns) == [
        "title",
        "channel",
        "upload_date",
        "created_at",
        "url",
    ]
```

`test_table_key_changes_when_the_materials_change` 아래에 더한다.

```python
def test_table_key_ignores_the_metadata() -> None:
    """메타데이터만 바뀌면 표의 key 는 그대로다.

    다른 탭에서 동기화로 채널·업로드일이 채워져도 고른 재료가 비워지면
    안 된다.
    """
    from notebooklm_st.pages import _digest_materials

    filled = dataclasses.replace(
        summary(1),
        metadata=models.VideoMetadata(
            channel="어떤 채널", upload_date="2026-09-20"
        ),
    )

    assert _digest_materials.widget_key([summary(1)]) == (
        _digest_materials.widget_key([filled])
    )
```

- [ ] **Step 2: 실패를 확인한다**

Run: `/c/Users/susot/.local/bin/uv.exe run pytest tests/pages/test_digest.py -q`
Expected: 새 표 테스트 셋이 `KeyError: 'channel'` 또는 열 목록 불일치로 FAIL. `test_table_key_ignores_the_metadata` 는 **지금도 PASS** 한다 — key 가 이미 ID 로만 만들어지므로 회귀 방지다.

- [ ] **Step 3: 표를 고친다**

`src/notebooklm_st/pages/_digest_materials.py` 의 `column_config`:

```python
        column_config={
            "title": st.column_config.TextColumn("문서 제목"),
            "channel": st.column_config.TextColumn("채널"),
            "upload_date": st.column_config.TextColumn("업로드일"),
            "created_at": st.column_config.TextColumn("시각"),
            "url": st.column_config.LinkColumn("Outline", display_text="열기"),
        },
```

`_row`:

```python
def _row(run: models.RunSummary) -> dict[str, str | None]:
    """재료 하나를 표의 한 행으로 만든다.

    열 순서가 곧 표의 열 순서다. 채널·업로드일은 고르는 기준이라
    제목 바로 뒤에 둔다. 업로드일은 ``YYYY-MM-DD`` 문자열이라 머리글
    정렬이 날짜 순서와 같다.
    """
    metadata = run.metadata
    return {
        "title": _title(run),
        "channel": metadata.channel if metadata else None,
        "upload_date": metadata.upload_date if metadata else None,
        "created_at": run.created_at,
        "url": run.outline_url,
    }
```

- [ ] **Step 4: 통과를 확인한다**

Run: `/c/Users/susot/.local/bin/uv.exe run pytest tests/pages/test_digest.py -q`
Expected: 전부 PASS.

- [ ] **Step 5: 커밋한다**

```bash
git add src/notebooklm_st/pages/_digest_materials.py tests/pages/test_digest.py
git commit -F - <<'EOF'
✨ feat(digest): 재료 표에 채널·업로드일 열 추가

같은 주제의 요약본이 쌓이면 어느 채널의 언제 영상인지가 재료를
고르는 기준이 된다. 저장된 이력에 남긴 메타데이터로 두 열을 제목
바로 뒤에 그린다. 값이 없으면 빈칸이고, 표의 key 는 실행 ID 로만
만들어 메타데이터가 채워져도 고른 재료가 남는다.

Assisted-by: <모델 ID>
EOF
```

---

### Task 7: README 와 명세를 최종 상태로 맞추기

**Files:**
- Modify: `README.md:11`, `README.md:114`
- Rewrite: `docs/superpowers/specs/2026-09-22-outline-storage-design.md`
- Rewrite: `docs/superpowers/specs/2026-09-28-history-sync-design.md`
- Rewrite: `docs/superpowers/specs/2026-09-23-digest-design.md`
- Modify: `docs/superpowers/specs/2026-09-30-saved-run-metadata-design.md:4` (상태)

**Interfaces:**
- Consumes: Task 1~6 의 최종 동작
- Produces: 없음(문서)

명세를 고칠 때는 Edit 으로 줄만 바꾸지 말고 **Write 로 파일 전체를 다시 쓴다.** 아래 목록은 바뀌어야 할 사실이다. 다시 쓴 문서는 그 사실이 처음부터 그랬던 것처럼 읽혀야 한다. "원래는·바뀌었다·이제는·이전에는" 같은 말과 수정 이력 절을 넣지 않는다. 나머지 절은 글자 그대로 둔다.

- [ ] **Step 1: README 를 고친다**

11행(처리 순서 한 줄) 끝의 `로컬에는 링크만 남음` 을 `로컬에는 링크와 채널·업로드일만 남음` 으로 바꾼다. 줄의 나머지는 그대로다.

114행의 사용 순서 5 를 이 문단으로 바꾼다.

```
5. **이력** 화면에서 답변을 확인하고, 제목을 정한 뒤 **Outline 에 저장**합니다. 저장하면 로컬에는 문서명·링크·채널·업로드일만 남고 수정·삭제·검색은 Outline 에서 합니다. 화면 위의 **Outline 과 동기화**는 저장된 이력과 Outline 컬렉션의 문서 목록을 맞춥니다. **확인**을 누르면 지울 이력·만들 문서·채널·업로드일 갱신·건너뛴 문서를 먼저 보여 주고, **적용**을 눌러야 바뀝니다. Outline 에 없는 이력은 링크만 지우고, 이력에 없는 문서는 본문의 영상 URL 로 이력을 되살립니다. 채널·업로드일은 문서 머리의 `채널`·`업로드 일자` 줄에서 읽어 채우며, 줄이 없는 문서는 빈칸으로 둡니다. 이 기능 전에 저장한 요약본은 동기화를 한 번 적용해야 정리본 재료 표에 채널·업로드일이 나옵니다. 영상 URL 줄이 없는 문서(정리본, 직접 쓴 글)는 건너뜁니다. Outline 휴지통이나 보관함에 있는 문서는 없는 것으로 보며, 복원하면 다음 동기화가 다시 만듭니다. 같은 영상의 문서가 둘이면 둘 다 이력이 되며 합치지 않습니다.
```

- [ ] **Step 2: Outline 저장 명세를 다시 쓴다**

`2026-09-22-outline-storage-design.md` 에서 바뀌는 사실:

- 32행 근처 "앱에는 문서명과 링크만 남는다" → 앱에는 문서명·링크와 영상 메타데이터(채널·업로드일)만 남는다.
- 126행 설계 결정 "저장에 성공하면 **본문을 지우고 링크만 남긴다**" → **답변을 지우고 링크와 영상 메타데이터를 남긴다.** 이유: 답변은 진실의 원천이 하나여야 한다(기존 문장 유지). 메타데이터는 문서 머리에 적은 값과 같은 캐시이고, 로컬에서 고치는 화면이 없어 흐름이 Outline → 로컬 한 방향이며, 이력 동기화가 문서에서 다시 맞춘다(`2026-09-30-saved-run-metadata-design.md`).
- 165행 데이터 흐름 "runs 행에 링크 기록 + answers·run_metadata 행 삭제 (커밋 하나)" → "runs 행에 링크 기록 + answers 행 삭제 (커밋 하나)".
- 410행 `mark_exported` 설명 "`runs` UPDATE + `answers` DELETE + `run_metadata` DELETE 를 **커밋 하나로**" → "`runs` UPDATE + `answers` DELETE 를 **커밋 하나로**", 그리고 `run_metadata` 는 남긴다는 문장.
- 662행 테스트 표 "`answers`·`run_metadata` 를 지우는지" → "`answers` 를 지우고 `run_metadata` 는 남기는지".
- 424행·536행의 "로컬의 링크만"·"로컬 링크만 지웁니다" 는 이력 **삭제** 이야기라 그대로 둔다.

- [ ] **Step 3: 이력 동기화 명세를 다시 쓴다**

`2026-09-28-history-sync-design.md` 에서 바뀌는 사실. 합치기·지우지 않기 규칙의 자세한 이유는 옮겨 적지 말고 `2026-09-30-saved-run-metadata-design.md` 를 가리킨다.

- 23행 "로컬 `runs` 에는 문서 ID·URL·제목·저장 시각만 남는다" → 문서 ID·URL·제목·저장 시각이 남고, `run_metadata` 에 채널·업로드일이 캐시로 남는다.
- §3 "기존 행 | **손대지 않는다**" → **`runs` 행은 손대지 않는다. 메타데이터만 문서 값으로 갱신한다.** 이유에 "메타데이터를 쓰는 것은 ID 도 실행 시각도 바꾸지 않는다" 를 더한다.
- §5 판정 표에 "행과 문서가 모두 있음" 을 둘로 나눈다: 문서 머리 값을 합친 결과가 로컬과 다름 → **갱신 대상** / 같거나 두 값을 못 읽음 → 손대지 않음.
- 261행 "`answers`·`run_metadata` 행은 만들지 않는다" → `answers` 행은 만들지 않는다. 문서 머리에서 채널·업로드 일자를 읽었으면 `run_metadata` 행을 함께 만든다.
- §6 데이터 모델: `SyncCreate.metadata`, `SyncUpdate`, `SyncPlan.updates`, `is_empty` 가 셋을 봄.
- §7.2: `insert_exported` 의 메타데이터, `write_metadata`(쌍이 맞고 값이 다를 때만 씀, 커밋하지 않음).
- §7.3: `plan` 의 갱신, `apply` 의 삭제·삽입·갱신 한 커밋, `SyncResult.updated`.
- §8: `find_metadata`(라벨 상수, 첫 줄 규칙, 문장부호 이스케이프, `YYYY-MM-DD`).
- §9.2: 화면 그림과 문구 — 설명 셋째 문장, 개수 한 줄의 `채널·업로드일 갱신 K건`, 결과 문구 `… · 갱신 K건`, 갱신은 개수만.
- §11 테스트 표·§12 파일 목록에 Task 1~5 의 변경을 넣는다. 572행의 "`answers`·`run_metadata` 를 만들지 않으며" 는 "`answers` 를 만들지 않고 메타데이터가 있으면 `run_metadata` 를 만들며" 가 된다.

- [ ] **Step 4: 정리본 명세를 다시 쓴다**

`2026-09-23-digest-design.md` 에서 바뀌는 사실:

- §10.2 첫 항목 "열은 셋이다" → 열은 다섯이다. **문서 제목** · **채널**(`metadata.channel`) · **업로드일**(`metadata.upload_date`) · **시각** · **Outline**. 행 번호는 숨긴다.
- §10.2 둘째 항목에서 "채널 열도 두지 않는다. 동기화로 되살린 이력에는 `run_metadata` 행이 없어 빈칸이 섞인다" 를 지우고, "채널·업로드일은 `RunSummary.metadata` 에서 온다. 저장할 때 남고 이력 동기화가 문서에서 채운다(`2026-09-30-saved-run-metadata-design.md`). 값이 없는 요약본은 빈칸이다" 를 넣는다. 영상 제목 열을 두지 않는 이유 문장은 그대로 둔다.
- §10.2 `widget_key` 항목에 "메타데이터가 바뀌어도 key 는 그대로라 고른 재료가 남는다" 를 더한다.
- §14 "재료 표" 행에 "채널·업로드일 열과 빈칸 · 열 순서 · 메타데이터만 다른 목록의 key 가 같음" 을 더한다.
- §17 "재료 거르기(날짜·채널)" 항목에서 "채널은 동기화로 되살린 이력에 없다" 를 지운다.

- [ ] **Step 5: 새 설계서의 상태를 고친다**

`docs/superpowers/specs/2026-09-30-saved-run-metadata-design.md` 4행:

```
- **상태**: 구현 완료 (<오늘 날짜 YYYY-MM-DD>)
```

- [ ] **Step 6: 지워야 할 문구가 남지 않았는지 본다**

아래 여섯 줄은 이 계획을 쓸 때 실제 파일에 있는 것을 확인했다. 전부 출력이 없어야 한다.

```bash
grep -n "로컬에는 링크만 남음" README.md
grep -n "문서명과 링크만 남고" README.md
grep -n "answers·run_metadata 행 삭제" docs/superpowers/specs/2026-09-22-outline-storage-design.md
grep -n "저장 시각만 남는다" docs/superpowers/specs/2026-09-28-history-sync-design.md
grep -n "행이 없어 빈칸이 섞인다" docs/superpowers/specs/2026-09-23-digest-design.md
grep -n "되살린 이력에 없다" docs/superpowers/specs/2026-09-23-digest-design.md
```

경위 문구가 들어가지 않았는지도 본다. 출력이 있으면 그 줄을 읽고, 경위를 적은 문장이면 고친다.

```bash
grep -n "원래는\|바뀌었다\|이제는\|이전에는" docs/superpowers/specs/2026-09-22-outline-storage-design.md docs/superpowers/specs/2026-09-28-history-sync-design.md docs/superpowers/specs/2026-09-23-digest-design.md
```

- [ ] **Step 7: 커밋한다(둘로 나눈다)**

```bash
git add README.md
git commit -F - <<'EOF'
📝 docs(readme): 저장 뒤 남는 값과 동기화 갱신 안내

저장 뒤 로컬에 채널·업로드일이 남고, 동기화가 문서 머리에서 그
값을 채운다는 사실을 적는다. 기능 전에 저장한 요약본은 동기화를
한 번 적용해야 재료 표에 나온다는 점도 적는다.

Assisted-by: <모델 ID>
EOF
git add docs/superpowers/specs/2026-09-22-outline-storage-design.md docs/superpowers/specs/2026-09-28-history-sync-design.md docs/superpowers/specs/2026-09-23-digest-design.md docs/superpowers/specs/2026-09-30-saved-run-metadata-design.md
git commit -F - <<'EOF'
📝 docs(spec): 명세 셋을 메타데이터 캐시 기준으로 다시 쓰기

저장이 run_metadata 를 남기고, 이력 동기화가 문서 머리에서 채널·
업로드일을 읽어 채우며, 재료 표가 두 열을 그리게 됐다. Outline
저장·이력 동기화·정리본 명세를 그 최종 상태로 통째로 다시 쓰고,
새 설계서의 상태를 구현 완료로 바꾼다.

Assisted-by: <모델 ID>
EOF
```

---

### Task 8: 전체 검증과 브라우저 확인

**Files:** 없음(스크래치 폴더의 임시 스크립트만)

- [ ] **Step 1: 네 검사를 돌린다**

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

Expected: 포맷 변경 없음(있으면 그 파일을 확인하고 커밋), `All checks passed!`, `Success: no issues found`, 실패 0. 실패가 있으면 완료라고 말하지 말고 출력을 그대로 보고한다.

- [ ] **Step 2: 가짜 Outline 과 임시 DB 를 준비한다**

아래 두 파일을 세션 스크래치 폴더(`$SCR`)에 만든다. 저장소 안에 만들지 않는다.

`$SCR/fake_outline.py`:

```python
"""브라우저 확인용 가짜 Outline. documents.list 한 페이지만 돌려준다."""

import http.server
import json

ITEMS = [
    ("금리와 주가", "경제 채널"),
    ("반도체 사이클 전망", "산업 채널"),
    ("배당주 고르는 법", "투자_연구소 [KR]"),
]
DOCUMENTS = [
    {
        "id": f"doc-{index}",
        "title": title,
        "url": f"/doc/doc-{index}",
        "createdAt": "2026-09-25T01:00:00.000Z",
        "text": (
            f"- 제목: {title}\n"
            f"- 채널: {channel}\n"
            f"- 업로드 일자: 2026-09-{10 + index:02d}\n"
            f"- 영상 URL: https://www.youtube.com/watch?v=vid{index:08d}\n"
            "\n---\n\n## 요약\n\n본문.\n"
        ),
    }
    for index, (title, channel) in enumerate(ITEMS)
]


class Handler(http.server.BaseHTTPRequestHandler):
    """documents.list 만 받는 처리기."""

    def do_POST(self) -> None:
        """목록 요청이면 문서 셋을, 아니면 404 를 돌려준다."""
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path != "/api/documents.list":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps({"data": DOCUMENTS}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


http.server.HTTPServer(("127.0.0.1", 8698), Handler).serve_forever()
```

`$SCR/seed.py`:

```python
"""가짜 Outline 의 세 문서를 가리키는 저장된 실행을 메타데이터 없이 넣는다."""

import pathlib
import sys

from notebooklm_st.core import models
from notebooklm_st.services import run_history, store

connection = store.connect(pathlib.Path(sys.argv[1]))
for index, title in enumerate(
    ["금리와 주가", "반도체 사이클 전망", "배당주 고르는 법"]
):
    run_id = run_history.save_run(
        connection,
        models.RunResult(
            url=f"https://www.youtube.com/watch?v=vid{index:08d}",
            video_id=f"vid{index:08d}",
            title=title,
            items=(),
        ),
    )
    run_history.mark_exported(
        connection,
        run_id,
        document_id=f"doc-{index}",
        document_title=title,
        document_url=f"http://127.0.0.1:8698/doc/doc-{index}",
    )
print(len(run_history.list_runs(connection)), "saved runs")
```

실행한다(가짜 Outline 은 백그라운드).

```bash
.venv/Scripts/python.exe "$SCR/seed.py" "$SCR/meta.db"
.venv/Scripts/python.exe "$SCR/fake_outline.py"            # 백그라운드
NOTEBOOKLM_ST_DB="$SCR/meta.db" NOTEBOOKLM_HOME="$SCR/nlm-home" \
NOTEBOOKLM_ST_OUTLINE_URL="http://127.0.0.1:8698" \
NOTEBOOKLM_ST_OUTLINE_TOKEN="dummy" NOTEBOOKLM_ST_OUTLINE_COLLECTION="dummy" \
.venv/Scripts/python.exe -m streamlit run src/notebooklm_st/app.py \
  --server.port 8699 --server.headless true                 # 백그라운드
```

`NOTEBOOKLM_HOME` 은 빈 폴더다. 실제 자격증명을 건드리지 않으려는 것이고, 화면 위의 인증 오류 배너는 그래서 뜨는 것이다.

- [ ] **Step 3: 브라우저 탭 둘로 확인한다**

- 새 세션에서 `http://127.0.0.1:8699/digest` 로 바로 들어가면 빈 화면이 뜬다. **루트(`/`)를 연 뒤 사이드바에서 들어간다.**
- 재료 표는 canvas 라 접근성 트리에 행이 없다. 체크박스는 스크린샷의 좌표로 누른다.

1. 탭 A: 루트 → 사이드바 **정리본**. 표에 세 행, 채널·업로드일 칸이 비어 있다. 두 행의 체크박스를 누르면 "고른 재료 2/10".
2. 탭 B(새 탭): 루트 → **이력** → "Outline 과 동기화" 펼치기 → **확인**. 개수 한 줄에 `채널·업로드일 갱신 3건`, 설명에 셋째 문장. **적용** → `동기화 완료 · 지움 0건 · 만듦 0건 · 갱신 3건`.
3. 탭 A: 셋째 행의 체크박스를 누른다. "고른 재료 3/10" 이어야 한다 — 앞서 고른 둘이 남았다. 표의 채널·업로드일 칸이 채워졌고, `배당주 고르는 법` 의 채널이 `투자_연구소 [KR]` 로 보인다.
4. 탭 B 에서 다시 **확인** → "이미 맞습니다".

기대와 다르면 스크린샷과 함께 보고한다.

- [ ] **Step 4: 치운다**

- 스트림릿과 가짜 Outline 백그라운드 작업을 멈춘다.
- 브라우저 도구가 저장소 루트에 만든 `.playwright-mcp/` 가 있으면 스크래치 폴더로 옮긴다.
- `git status --short` 가 비어 있어야 한다.
