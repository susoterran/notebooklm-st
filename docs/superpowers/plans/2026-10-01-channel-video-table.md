# 채널 신규 영상 표 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 채널 화면 "새 영상 확인" 탭의 신규 목록을 표로 바꾸고, 표에서 여러 영상을 골라 버튼 하나로 질의 대기열에 넣으며, 질의 화면과 같은 자동 저장 설정을 쓰게 한다.

**Architecture:** 질의 화면에만 있던 자동 저장 체크와 대기열 안내를 `components/` 의 공유 조각 둘로 떼어 두 화면이 같은 글자를 그리게 한다(질의 화면 동작 불변). 신규 영상 표는 `pages/_channel_videos.py`(`st.dataframe` 다중 행 선택, 상태 칸은 레지스트리에서 읽음), 넣기 버튼·콜백·결과 문구는 `pages/_channel_enqueue.py` 가 맡고, `pages/_channel_check.py` 는 확인 흐름과 이 넷을 잇기만 한다. 넣기는 버튼 `on_click` 콜백이 누른 순간의 표 선택을 세션에서 읽어 목록 순서로 `runner.enqueue` 에 넘기고, 넣기 횟수를 표 key 에 섞어 선택을 비운다.

**Tech Stack:** Python 3.13 · Streamlit 1.64 · SQLite · pytest + `streamlit.testing.v1.AppTest` · uv · ruff · mypy

**Spec:** `docs/superpowers/specs/2026-10-01-channel-video-table-design.md` — 이 계획은 설계서 전부를 구현한다. 구현자는 설계서와 이 계획을 둘 다 읽는다.

## Global Constraints

- 브랜치는 `develop`. 에이전트는 커밋만 하고 **`git push` 하지 않는다.** `--no-verify`·force 금지. worktree 를 만들지 않고 저장소 그 자리에서 일한다.
- 커밋 메시지: `<gitmoji> <type>(<scope>): <한국어 명령형 제목, 50자 이내, 마침표 없음>`, 빈 줄, 본문(무엇을·왜, 72칸에서 줄바꿈), 빈 줄, 마지막 줄 `Assisted-by: <커밋하는 에이전트 자신의 모델 ID>`. AI 를 `Co-Authored-By:` 로 적지 않는다.
- **커밋은 Git Bash 에서 메시지 파일로 넣는다**(각 Task 의 커밋 단계 모양 그대로: `mktemp` 파일에 쓰고 `git commit -F`). PowerShell here-string(`@'…'@`) 금지 — 메시지에 `@` 줄이 남는다. 커밋 뒤 `git log -1 --format=%B | grep -c "^@$"` 가 `0` 이어야 한다.
- 명령 가드 훅이 `rm -f`·`rm -r`, `cd /…`·`cd ..`, `curl` 등을 막는다. 임시 파일은 플래그 없는 `rm` 으로 지우고, 디렉터리는 옮기지 말고 저장소 루트에서 상대·절대 경로로 부른다. 명령 문자열에 `secret` 같은 낱말이 들어가면 시크릿 가드가 막으므로, 그런 글자가 든 코드는 셸 heredoc 이 아니라 파일 편집 도구로 쓴다.
- `uv` 는 에이전트 셸 PATH 에 없다. 모든 명령은 `/c/Users/susot/.local/bin/uv.exe run …` 로 부른다.
- 완료 전 네 검사를 이 순서로 통과한다: `ruff format .` → `ruff check --fix .` → `mypy src tests` → `pytest`. 이 계획을 시작하기 전 기준은 `820 passed, 1 skipped` 이고, 끝나면 `837 passed, 1 skipped` 다(Task 마다 기대 수를 적었다). 새 가상환경에서 처음 돌릴 때 `tests/pages/test_dashboard.py::test_dashboard_shows_notice_when_no_runs` 가 AppTest 제한 시간으로 한 번 실패한 적이 있다(예행 실측, 다시 돌리면 통과). 같은 테스트만 그렇게 실패하면 한 번 더 돌려 확인하고, 그래도 실패하면 보고한다.
- `core/`·`services/` 에서 `import streamlit` 금지.
- import 는 모듈 단위(`from notebooklm_st.pages import _channel_videos`)로만. 함수·클래스를 직접 import 하지 않는다. 예외는 `typing`·`collections.abc`.
- 모든 모듈·클래스·함수·테스트 함수에 한국어 Google 형식 독스트링. 코드 80칸, 독스트링·주석 72칸. **ruff 는 표시 폭으로 재므로 한글 한 자가 2칸이다.** 독스트링 72칸은 ruff 가 검사하지 않으니 직접 지킨다(아래 코드는 모두 지켜져 있다).
- `from __future__ import annotations` 를 쓰지 않는다.
- 바꾸지 않는 파일: `services/runner.py`, `services/run_registry.py`, `services/runs.py`, `services/channel_feed.py`, `services/channels.py`, `services/channel_lookup.py`, `services/settings.py`, `services/store.py`, `core/new_videos.py`, `pages/channels.py`, `pages/dashboard.py`, 배포 파일(`docker-compose.yml`·`Dockerfile`·`pyproject.toml`). `services/run_store.py` 는 독스트링 두 줄만 고친다(Task 4). 새 의존성은 없다. 스키마는 바뀌지 않는다.
- **`tests/pages/test_ask.py` 는 고치지 않는다.** 그대로 통과하는 것이 공유 조각으로 옮긴 것이 질의 화면 동작을 바꾸지 않았다는 증거다.
- 화면 문구는 글자 그대로(설계서 §6·§8):
  - 표 위 캡션 `행 왼쪽 칸을 눌러 고릅니다.`, 열 머리글 `제목`·`업로드일`·`상태`·`영상`, 링크 글자 `열기`
  - 상태 칸 `대기 중`·`실행 중`·`끝남`·`실패`(실행이 없으면 빈칸)
  - 버튼 `선택한 영상 요약 ({n}건)`(key `channels_enqueue`), 질문 미선택 안내 `질문을 하나 이상 고르세요.`
  - 넣은 뒤(위에서 처음 맞는 것, n 이 1 이면 건수 없이): `{n}건을 대기열에 넣었습니다. 대기열이 멈춰 있어 재개할 때까지 기다립니다.` · `{n}건을 대기열에 넣었습니다 — 앞에 {m}건. 실행 현황 화면에서 확인하세요.` · `{n}건을 대기열에 넣었습니다. 정리본이 끝나면 시작합니다.` · `{n}건을 넣고 첫 영상부터 시작했습니다. 실행 현황 화면에서 확인하세요.` / 한 건이면 `대기열에 넣었습니다…`·`실행을 시작했습니다. 실행 현황 화면에서 확인하세요.` — 뺀 것이 있으면 끝에 ` 이미 대기 중이거나 실행 중인 {k}건은 뺐습니다.`
  - 모두 뺐을 때(`st.info`) `고른 영상은 모두 이미 대기 중이거나 실행 중입니다.`
  - 대기열 안내(질의 화면과 같은 글자): `실행 중이거나 대기 중인 질의가 {m}건 있습니다. 넣으면 그 뒤에 실행됩니다.` · `정리본을 작성 중입니다. 넣은 질의는 정리본이 끝난 뒤 시작합니다.`(info) · `대기열이 멈춰 있습니다. 넣은 질의는 실행 현황에서 재개할 때까지 기다립니다.`(warning)
  - 자동 저장 체크 라벨 `자동 저장`, 잠겼을 때 캡션 `Outline 연결이 설정되지 않아 자동 저장을 쓸 수 없습니다.`
- 설계·명세 문서(`docs/superpowers/specs/*`)는 최종 상태만 담는다. 경위("원래는·바뀌었다")는 본문에 적지 않고 커밋 메시지에 적는다.
- 계획에 적힌 테스트 단언이 쓰인 그대로는 통과할 수 없으면, **구현을 비틀어 통과시키지 말고** 그 사실과 이유를 보고한다.
- 이 계획의 코드는 격리된 worktree 에서 Task 1~5 를 차례로 적용해 Task 마다 네 검사를 통과한 글자다. `ruff format` 뒤의 모양 그대로 옮겼다(포매터가 한 줄에 들어가는 문자열 조각을 합친 자리도 그대로다). 문서 자리의 "지금" 글자는 모두 그 파일에 정확히 한 번 나오는 것을 기계로 대조했다.

## 설계서에 없어 이 계획이 정한 것

- 세션 key 이름: 넣기 횟수 `channels_generation`, 넣은 뒤 결과 `channels_enqueued`, 자동 저장 체크 `channels_auto_save`·`channels_auto_save_locked`. 넣은 뒤 결과는 `_channel_enqueue._Enqueued(text, added)` 로 담아, 하나라도 넣었으면 `st.success`, 모두 뺐으면 `st.info` 로 그린다.
- `_channel_check` 의 질문 선택 도움말을 `고른 질문을 이번에 넣는 영상 모두에 씁니다.` 로 바꾼다(전에는 "이 목록의 모든 요약").
- `_channel_enqueue.generation()` 은 세션 값을 `int` 로 주석한 지역 변수에 받아 돌려준다. `st.session_state.get` 은 `Any` 를 돌려준다.
- 테스트의 가짜 러너(`record_enqueue`)는 스레드를 띄우지 않고 `registry.enqueue` 로 대기에만 넣는다. 같은 영상 판정과 상태 칸이 실제처럼 돈다. 질의 화면 테스트의 가짜와 같은 방식이다.
- 테스트 도우미 `checked(app_db, monkeypatch, *entries, choose=True)` 가 채널·질문 등록, 피드 가짜, 확인 누르기, 질문 고르기를 한 번에 한다. 신규 영상 둘은 `NEWER`·`OLDER`(`BOTH`)로 둔다 — 표는 업로드가 늦은 것부터라 그 순서로 오른다.
- 예행에서 넣기 콜백이 실제 브라우저에서 표 선택을 읽는 것을 이미 확인했다(설계서 §2.9). Task 6 의 브라우저 확인은 구현된 코드로 같은 것을 다시 보고, 정렬 뒤 선택과 상태 변화 중 선택 유지를 더 본다.

## Review Focus

1. **머리글을 눌러 표를 정렬한 뒤 고름** — 선택은 원래 목록의 위치 번호로 오므로 고른 영상이 맞아야 하고, 대기열에는 누른 순서나 정렬 순서가 아니라 목록 순서로 서야 한다. → Task 3 `test_selected_entries_keep_the_list_order`, Task 4 `test_enqueue_puts_the_picked_videos_in_list_order`(거꾸로 고르기), Task 6 Step 3 의 정렬 확인
2. **이미 대기 중인 영상을 섞어 고름** — 그 영상만 빼고 넣고, 뺀 수를 결과 끝에 알려야 한다. 전부 대기 중이면 아무것도 넣지 않고 안내만 한다. → Task 4 `test_a_pending_video_is_left_out`, `test_only_pending_videos_add_nothing`
3. **넣은 직후 같은 줄로 또 넣으려 함** — 선택이 비고, 넣기 전 key 로 남은 선택이 새 표에 붙지 않아야 한다. 다시 골라도 대기 중이라 빠진다(2번). → Task 4 `test_enqueue_reports_and_clears_the_selection`
4. **고르는 사이 실행이 끝나 상태 칸이 바뀜** — 상태 칸만 바뀌고 고른 체크는 남아야 한다. 표 key 는 영상 목록과 넣기 횟수로만 만든다. → Task 3 `test_widget_key_follows_the_list_and_the_generation`, Task 6 Step 3 의 상태 변화 확인
5. **Outline 설정이 없는 기기** — 자동 저장 체크가 꺼진 채 잠기고 `auto_save=False` 로 넣어야 하며, DB 에 켜 둔 값은 남아야 한다. → Task 4 `test_enqueue_without_outline_hands_no_auto_save`

---

## File Structure

| 파일 | 책임 | Task |
|---|---|---|
| `src/notebooklm_st/components/auto_save_toggle.py` (새) | 자동 저장 체크 — DB 설정 하나, 위젯 key 는 화면마다 | 1 |
| `src/notebooklm_st/components/queue_notice.py` (새) | 대기열 안내 셋, 앞선 질의 수, 넣은 뒤 결과 문구 | 2 |
| `src/notebooklm_st/pages/ask.py` | 위 둘을 부르게만 바꾼다(동작 불변) | 1, 2 |
| `src/notebooklm_st/pages/_channel_videos.py` (새) | 신규 영상 표 — 행·상태 라벨·고른 행 옮기기·표 key | 3 |
| `src/notebooklm_st/pages/_channel_enqueue.py` (새) | 넣기 — 질문 안내·버튼·결과 문구·콜백·넣기 횟수 | 4 |
| `src/notebooklm_st/pages/_channel_check.py` | 확인 흐름과 위 넷 잇기. 한 줄 목록·잠금 지우기 | 4 |
| `src/notebooklm_st/services/run_store.py` | `enqueue` 독스트링 두 줄 | 4 |
| `tests/test_components.py` | 공유 조각 둘 | 1, 2 |
| `tests/pages/test_channels.py` | 표·넣기·자동 저장·건너뛰기·잠그지 않음 | 3, 4 |
| `README.md`, `docs/ONBOARDING.md`, 설계 문서 둘 | 사용법·모듈 표·설계서 자리 맞추기 | 5 |
| 새 설계서 상태 | 구현 완료 표시 | 6 |

각 Task 가 끝난 시점에도 앱은 온전히 돈다. Task 1·2 는 질의 화면 동작을 바꾸지 않는 옮기기이고, Task 3 의 표 모듈은 Task 4 가 잇기 전까지 아무도 부르지 않는다.

---

### Task 1: 자동 저장 체크를 공유 컴포넌트로 떼기

**Files:**
- Create: `src/notebooklm_st/components/auto_save_toggle.py`
- Modify: `src/notebooklm_st/pages/ask.py`(파일 전체를 아래 내용으로)
- Test: `tests/test_components.py`

**Interfaces:**
- Consumes: `services.outline.config_from_env()`, `services.settings.auto_save(connection)`·`set_auto_save(connection, value)`
- Produces: `auto_save_toggle.render(connection: sqlite3.Connection, key: str, locked_key: str) -> bool`, `auto_save_toggle.HELP: str`. Task 4 의 채널 화면이 `render(connection, "channels_auto_save", "channels_auto_save_locked")` 로 부른다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_components.py` 의 import 한 줄을 바꾼다.

```python
from notebooklm_st.services import auth, runs, store
```

→

```python
from notebooklm_st.services import auth, outline, runs, settings, store
```

파일 끝에 붙인다.

```python
def test_auto_save_toggle_shares_one_setting_across_keys(
    app_db, monkeypatch
) -> None:
    """두 화면이 위젯 key 를 달리 해도 자동 저장 설정은 하나다.

    한 화면에서 켜면 DB 에 남고, 다른 key 로 처음 그린 체크도 켜진
    채로 시작한다.
    """
    monkeypatch.setenv(outline.URL_ENV_VAR, "http://192.168.0.10:3000")
    monkeypatch.setenv(outline.TOKEN_ENV_VAR, "ol_secret")
    monkeypatch.setenv(outline.COLLECTION_ENV_VAR, "col-1")

    def first():
        """AppTest 진입점 — 첫 화면의 key 로 체크를 그린다."""
        from notebooklm_st import session
        from notebooklm_st.components import auto_save_toggle

        auto_save_toggle.render(
            session.get_connection(), "first_auto_save", "first_locked"
        )

    def second():
        """AppTest 진입점 — 다른 화면의 key 로 체크를 그린다."""
        from notebooklm_st import session
        from notebooklm_st.components import auto_save_toggle

        auto_save_toggle.render(
            session.get_connection(), "second_auto_save", "second_locked"
        )

    app = v1.AppTest.from_function(first).run()
    app.checkbox(key="first_auto_save").check().run()

    assert not app.exception
    assert settings.auto_save(app_db) is True
    other = v1.AppTest.from_function(second).run()
    assert other.checkbox(key="second_auto_save").value is True
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest -q tests/test_components.py::test_auto_save_toggle_shares_one_setting_across_keys
```

Expected: FAIL — `KeyError: 'first_auto_save'`(스크립트 안에서 `ImportError: cannot import name 'auto_save_toggle'` 이 나 체크가 그려지지 않는다).

- [ ] **Step 3: 공유 컴포넌트를 만든다**

`src/notebooklm_st/components/auto_save_toggle.py`:

```python
"""자동 저장 체크 — 질의 화면과 채널 화면이 같은 설정을 쓴다.

값은 DB 에 하나만 기억한다(``services.settings``). 위젯 key 는
화면마다 따로 받는다. 같은 key 를 두 화면에 쓰면 위젯 상태가
부딪친다.
"""

import sqlite3

import streamlit as st

from notebooklm_st.services import outline, settings

HELP = (
    "켜면 답변을 받은 뒤 인용을 빼고 곧바로 Outline 에 올립니다."
    " 제목이 없거나 답변 일부가 실패하면 올리지 않고 이력에 미저장으로"
    " 남깁니다."
)
"""자동 저장 체크의 도움말."""


def render(connection: sqlite3.Connection, key: str, locked_key: str) -> bool:
    """자동 저장 체크를 그리고, 넣을 실행에 줄 값을 돌려준다.

    값은 DB 에 기억한다. 재시작하거나 다른 기기에서 열어도 켜 둔
    그대로여야 한다. 세션에 키가 없을 때만 DB 값으로 채우고, 사람이
    바꿀 때만 콜백이 DB 에 적는다. 다른 화면에 다녀오면 위젯 값이
    버려지므로 DB 값으로 다시 시작한다.

    key 없는 체크에 DB 값을 초기값으로 주는 방식은 쓰지 않는다. DB 에
    적는 순간 위젯 ID 가 바뀌어 바로 다음 조작이 버려진다.

    Args:
        connection: 열린 커넥션.
        key: 체크의 위젯 key. 화면마다 다르게 준다.
        locked_key: Outline 설정이 없을 때 그리는 잠긴 체크의 key.

    Returns:
        화면에 보이는 값. Outline 설정이 없으면 거짓.
    """
    if outline.config_from_env() is None:
        # 켜 둔 값을 잠긴 채 보이지 않도록 다른 위젯으로 그린다. DB
        # 값은 건드리지 않는다. 설정을 되살리면 켜 둔 값이 돌아온다.
        st.checkbox(
            "자동 저장",
            value=False,
            key=locked_key,
            disabled=True,
            help=HELP,
        )
        st.caption("Outline 연결이 설정되지 않아 자동 저장을 쓸 수 없습니다.")
        return False
    if key not in st.session_state:
        st.session_state[key] = settings.auto_save(connection)
    return st.checkbox(
        "자동 저장",
        key=key,
        help=HELP,
        on_change=_remember,
        args=(connection, key),
    )


def _remember(connection: sqlite3.Connection, key: str) -> None:
    """사람이 바꾼 자동 저장 값을 DB 에 적는다.

    체크의 ``on_change`` 콜백이다. 사람이 바꿀 때만 쓰므로 다른
    기기에서 바꾼 값을 이 화면이 되덮지 않는다.

    Args:
        connection: 열린 커넥션.
        key: 바뀐 체크의 위젯 key.
    """
    settings.set_auto_save(connection, st.session_state[key])
```

- [ ] **Step 4: 질의 화면이 그것을 부르게 한다**

`src/notebooklm_st/pages/ask.py` 를 처음부터 끝까지 읽은 뒤 이 내용으로 바꾼다. 바뀌는 것은 import 셋(`sqlite3`·`outline`·`settings` 를 빼고 `components.auto_save_toggle` 을 더함), `_AUTO_SAVE_HELP` 삭제, `render` 안의 자동 저장 호출, 끝의 `_render_auto_save`·`_remember_auto_save` 삭제뿐이다.

```python
"""질의 화면 — 질의를 대기열에 넣는 입구."""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import auto_save_toggle
from notebooklm_st.core import youtube
from notebooklm_st.services import questions, run_registry, runner, runs, store

_URL_KEY = "ask_url"
_SELECTED_KEY = "ask_selected"
_AUTO_SAVE_KEY = "ask_auto_save"
_AUTO_SAVE_LOCKED_KEY = "ask_auto_save_locked"
_ENQUEUED_KEY = "ask_enqueued"


def render() -> None:
    """URL 입력, 질문 선택, 자동 저장 여부, 대기열에 넣기를 그린다.

    실행은 백그라운드 워커가 넣은 순서대로 맡는다. 이 화면은 넣기만
    하고 즉시 반환하므로, 앞 실행을 기다리지 않고 다음 영상을 넣을 수
    있다. 진행 상황과 답변은 실행 현황 화면에서 본다.
    """
    st.title("영상 질의")
    connection = session.get_connection()
    registry = session.get_registry()
    question_list = questions.list_questions(connection)

    url = st.text_input(
        "YouTube 영상 URL",
        key=_URL_KEY,
        placeholder="https://www.youtube.com/watch?v=...",
    )
    url_ok = youtube.is_valid(url)
    if url and not url_ok:
        st.error("단일 YouTube 영상 URL 이 아닙니다.")

    if not question_list:
        st.info("질문 관리 화면에서 질문을 먼저 등록하세요.")
        return

    selected = st.multiselect(
        "질문 선택",
        options=question_list,
        format_func=lambda question: question.title,
        key=_SELECTED_KEY,
    )
    auto_save = auto_save_toggle.render(
        connection, _AUTO_SAVE_KEY, _AUTO_SAVE_LOCKED_KEY
    )

    duplicate = _render_queue_notices(
        registry, youtube.extract_video_id(url) if url_ok else None
    )
    st.button(
        "실행",
        key="ask_run",
        disabled=duplicate or not (url_ok and selected),
        on_click=_enqueue,
        args=(registry, auto_save),
    )
    enqueued = st.session_state.pop(_ENQUEUED_KEY, None)
    if enqueued is not None:
        st.success(enqueued)


def _render_queue_notices(
    registry: run_registry.RunRegistry, video_id: str | None
) -> bool:
    """넣으면 언제 돌지 알리고, 같은 영상이 이미 들어 있는지 본다.

    Args:
        registry: 실행 레지스트리.
        video_id: 입력한 URL 의 영상 ID. URL 이 틀렸으면 ``None``.

    Returns:
        그 영상이 이미 대기 중이거나 실행 중이면 참. 버튼을 잠근다.
    """
    ahead = _count_ahead(registry)
    if ahead > 0:
        st.info(
            f"실행 중이거나 대기 중인 질의가 {ahead}건 있습니다."
            " 넣으면 그 뒤에 실행됩니다."
        )
    if session.get_digest_registry().is_running():
        st.info(
            "정리본을 작성 중입니다. 넣은 질의는 정리본이 끝난 뒤 시작합니다."
        )
    if registry.paused_reason() is not None:
        st.warning(
            "대기열이 멈춰 있습니다. 넣은 질의는 실행 현황에서 재개할"
            " 때까지 기다립니다."
        )
    duplicate = video_id is not None and registry.is_pending(video_id)
    if duplicate:
        st.info("이 영상은 이미 대기 중이거나 실행 중입니다.")
    return duplicate


def _enqueue(registry: run_registry.RunRegistry, auto_save: bool) -> None:
    """입력한 영상을 대기열에 넣고 URL 칸을 비운다.

    실행 버튼의 ``on_click`` 콜백이다. 콜백은 재실행 전에 돌므로 URL
    위젯의 키를 바꿔도 예외가 없다. URL·질문은 버튼을 그릴 때가 아니라
    누른 순간의 세션 값을 읽는다. 질문 선택은 남겨 다음 영상을 바로
    붙여 넣게 한다. 결과 문구는 세션에 적어 다음 그림에서 한 번
    보인다.

    Args:
        registry: 실행 레지스트리.
        auto_save: 화면에 보이는 자동 저장 값.
    """
    url = st.session_state.get(_URL_KEY, "")
    selected = st.session_state.get(_SELECTED_KEY, [])
    video_id = youtube.extract_video_id(url)
    if video_id is None or not selected or registry.is_pending(video_id):
        return
    ahead = _count_ahead(registry)
    paused = registry.paused_reason() is not None
    digests = session.get_digest_registry()
    digesting = digests.is_running()
    runner.enqueue(
        registry,
        url,
        selected,
        store.default_db_path(),
        auto_save=auto_save,
        is_blocked=digests.is_running,
    )
    st.session_state[_URL_KEY] = ""
    st.session_state[_ENQUEUED_KEY] = _enqueued_text(ahead, paused, digesting)


def _count_ahead(registry: run_registry.RunRegistry) -> int:
    """지금 넣으면 앞에 설 질의 수. 멈춤과 상관없이 센다."""
    return sum(
        1 for handle in registry.list_all() if handle.status in runs.PENDING
    )


def _enqueued_text(ahead: int, paused: bool, digesting: bool) -> str:
    """넣은 뒤 보일 문구. 위에서부터 처음 맞는 것을 쓴다.

    Args:
        ahead: 넣기 직전에 센 앞선 질의 수.
        paused: 대기열이 멈춰 있었는가.
        digesting: 정리본을 작성 중이었는가.

    Returns:
        화면에 한 번 보일 문구.
    """
    if paused:
        return (
            "대기열에 넣었습니다. 대기열이 멈춰 있어 재개할 때까지 기다립니다."
        )
    if ahead > 0:
        return (
            f"대기열에 넣었습니다 — 앞에 {ahead}건. 실행 현황 화면에서"
            " 확인하세요."
        )
    if digesting:
        return "대기열에 넣었습니다. 정리본이 끝나면 시작합니다."
    return "실행을 시작했습니다. 실행 현황 화면에서 확인하세요."
```

- [ ] **Step 5: 테스트가 통과하는지 본다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest -q tests/test_components.py tests/pages/test_ask.py
```

Expected: `58 passed`. `test_ask.py` 는 손대지 않았다.

- [ ] **Step 6: 네 검사를 돌린다**

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

Expected: 포맷 변경 없음, `All checks passed!`, `Success: no issues found`, `821 passed, 1 skipped`.

- [ ] **Step 7: 커밋한다**

```bash
msg="$(mktemp)"
cat > "$msg" <<'EOF'
♻️ refactor(ask): 자동 저장 체크를 공유 컴포넌트로 떼기

채널 화면도 질의 화면과 같은 자동 저장 체크를 그리게 되므로,
체크와 DB 기억 방식을 components/auto_save_toggle.py 로 옮긴다.
설정은 DB 에 하나이고 위젯 key 만 화면마다 받는다. 같은 key 를
두 화면에 쓰면 위젯 상태가 부딪친다. 질의 화면은 지금 key 를
그대로 넘겨 동작이 바뀌지 않는다.

Assisted-by: <모델 ID>
EOF
git add src/notebooklm_st/components/auto_save_toggle.py src/notebooklm_st/pages/ask.py tests/test_components.py
git commit -F "$msg"
rm "$msg"
```

---

### Task 2: 대기열 안내를 공유 컴포넌트로 떼기

**Files:**
- Create: `src/notebooklm_st/components/queue_notice.py`
- Modify: `src/notebooklm_st/pages/ask.py`(파일 전체를 아래 내용으로)
- Test: `tests/test_components.py`

**Interfaces:**
- Consumes: `session.get_digest_registry().is_running()`, `run_registry.RunRegistry.list_all()`·`paused_reason()`, `runs.PENDING`
- Produces: `queue_notice.count_ahead(registry: run_registry.RunRegistry) -> int`, `queue_notice.render(registry: run_registry.RunRegistry) -> None`, `queue_notice.enqueued_text(*, added: int, skipped: int, ahead: int, paused: bool, digesting: bool) -> str`(이름 인자만, `added` 는 1 이상). Task 4 의 넣기가 셋 다 쓴다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_components.py` 끝에 붙인다.

```python
def test_enqueued_text_for_one_keeps_the_ask_page_words() -> None:
    """한 건이면 질의 화면이 써 오던 문구와 글자 하나 다르지 않다.

    위에서부터 처음 맞는 줄을 쓴다 — 멈춤이 앞선 질의보다, 앞선
    질의가 정리본보다 먼저다.
    """
    from notebooklm_st.components import queue_notice

    assert queue_notice.enqueued_text(
        added=1, skipped=0, ahead=2, paused=True, digesting=True
    ) == ("대기열에 넣었습니다. 대기열이 멈춰 있어 재개할 때까지 기다립니다.")
    assert queue_notice.enqueued_text(
        added=1, skipped=0, ahead=2, paused=False, digesting=True
    ) == ("대기열에 넣었습니다 — 앞에 2건. 실행 현황 화면에서 확인하세요.")
    assert queue_notice.enqueued_text(
        added=1, skipped=0, ahead=0, paused=False, digesting=True
    ) == ("대기열에 넣었습니다. 정리본이 끝나면 시작합니다.")
    assert queue_notice.enqueued_text(
        added=1, skipped=0, ahead=0, paused=False, digesting=False
    ) == ("실행을 시작했습니다. 실행 현황 화면에서 확인하세요.")


def test_enqueued_text_counts_many() -> None:
    """여러 건이면 문구 앞에 건수를 적는다."""
    from notebooklm_st.components import queue_notice

    assert queue_notice.enqueued_text(
        added=3, skipped=0, ahead=1, paused=True, digesting=False
    ) == (
        "3건을 대기열에 넣었습니다. 대기열이 멈춰 있어 재개할 때까지"
        " 기다립니다."
    )
    assert queue_notice.enqueued_text(
        added=3, skipped=0, ahead=1, paused=False, digesting=False
    ) == (
        "3건을 대기열에 넣었습니다 — 앞에 1건. 실행 현황 화면에서 확인하세요."
    )
    assert queue_notice.enqueued_text(
        added=3, skipped=0, ahead=0, paused=False, digesting=True
    ) == ("3건을 대기열에 넣었습니다. 정리본이 끝나면 시작합니다.")
    assert queue_notice.enqueued_text(
        added=3, skipped=0, ahead=0, paused=False, digesting=False
    ) == ("3건을 넣고 첫 영상부터 시작했습니다. 실행 현황 화면에서 확인하세요.")


def test_enqueued_text_adds_the_skipped_tail() -> None:
    """뺀 영상이 있으면 문구 끝에 그 수를 붙인다."""
    from notebooklm_st.components import queue_notice

    assert queue_notice.enqueued_text(
        added=2, skipped=1, ahead=0, paused=False, digesting=False
    ) == (
        "2건을 넣고 첫 영상부터 시작했습니다. 실행 현황 화면에서"
        " 확인하세요. 이미 대기 중이거나 실행 중인 1건은 뺐습니다."
    )


def test_queue_notice_is_silent_when_nothing_waits(app_db) -> None:
    """앞선 질의도 정리본도 멈춤도 없으면 아무 안내도 그리지 않는다."""

    def script():
        """AppTest 진입점 — 빈 레지스트리로 안내를 그린다."""
        from notebooklm_st import session
        from notebooklm_st.components import queue_notice

        queue_notice.render(session.get_registry())

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.info) == 0
    assert len(app.warning) == 0
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest -q tests/test_components.py -k "enqueued_text or silent"
```

Expected: `4 failed` — `ImportError: cannot import name 'queue_notice'`.

- [ ] **Step 3: 공유 컴포넌트를 만든다**

`src/notebooklm_st/components/queue_notice.py`:

```python
"""대기열 안내 — 질의 화면과 채널 화면이 같은 문구를 쓴다.

넣으면 언제 도는지 미리 알리고, 넣은 뒤의 결과를 한 문장으로
만든다. 문장을 만드는 ``enqueued_text`` 는 순수 함수라 Streamlit
없이 테스트한다.
"""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.services import run_registry, runs


def count_ahead(registry: run_registry.RunRegistry) -> int:
    """지금 넣으면 앞에 설 질의 수. 멈춤과 상관없이 센다."""
    return sum(
        1 for handle in registry.list_all() if handle.status in runs.PENDING
    )


def render(registry: run_registry.RunRegistry) -> None:
    """넣으면 언제 돌지 알리는 안내를 그린다.

    앞선 질의·정리본·멈춤 셋을 각각 한 줄로 알린다. 어느 것도
    넣기를 막지 않는다. 한 번에 하나는 워커가 지킨다.

    Args:
        registry: 실행 레지스트리.
    """
    ahead = count_ahead(registry)
    if ahead > 0:
        st.info(
            f"실행 중이거나 대기 중인 질의가 {ahead}건 있습니다."
            " 넣으면 그 뒤에 실행됩니다."
        )
    if session.get_digest_registry().is_running():
        st.info(
            "정리본을 작성 중입니다. 넣은 질의는 정리본이 끝난 뒤 시작합니다."
        )
    if registry.paused_reason() is not None:
        st.warning(
            "대기열이 멈춰 있습니다. 넣은 질의는 실행 현황에서 재개할"
            " 때까지 기다립니다."
        )


def enqueued_text(
    *, added: int, skipped: int, ahead: int, paused: bool, digesting: bool
) -> str:
    """넣은 뒤 한 번 보일 문구. 위에서부터 처음 맞는 줄을 쓴다.

    한 건이면 건수를 적지 않는다. 질의 화면은 늘 한 건이라 그
    문구가 그대로 남는다.

    Args:
        added: 넣은 질의 수. 1 이상이다.
        skipped: 이미 대기 중이거나 실행 중이라 뺀 수.
        ahead: 넣기 직전에 센 앞선 질의 수.
        paused: 대기열이 멈춰 있었는가.
        digesting: 정리본을 작성 중이었는가.

    Returns:
        화면에 한 번 보일 문구.
    """
    if added == 1:
        put = "대기열에 넣었습니다"
    else:
        put = f"{added}건을 대기열에 넣었습니다"
    if paused:
        text = f"{put}. 대기열이 멈춰 있어 재개할 때까지 기다립니다."
    elif ahead > 0:
        text = f"{put} — 앞에 {ahead}건. 실행 현황 화면에서 확인하세요."
    elif digesting:
        text = f"{put}. 정리본이 끝나면 시작합니다."
    elif added == 1:
        text = "실행을 시작했습니다. 실행 현황 화면에서 확인하세요."
    else:
        text = (
            f"{added}건을 넣고 첫 영상부터 시작했습니다."
            " 실행 현황 화면에서 확인하세요."
        )
    if skipped > 0:
        text += f" 이미 대기 중이거나 실행 중인 {skipped}건은 뺐습니다."
    return text
```

- [ ] **Step 4: 질의 화면이 그것을 부르게 한다**

`src/notebooklm_st/pages/ask.py` 를 다시 읽은 뒤 이 내용으로 바꾼다. Task 1 결과에서 바뀌는 것은 import(`runs` 를 빼고 `components.queue_notice` 를 더함), `_render_queue_notices` 의 안내 세 줄이 `queue_notice.render(registry)` 로, `_enqueue` 의 `_count_ahead`·`_enqueued_text` 가 `queue_notice.count_ahead`·`queue_notice.enqueued_text(added=1, skipped=0, …)` 로, 끝의 `_count_ahead`·`_enqueued_text` 삭제뿐이다.

```python
"""질의 화면 — 질의를 대기열에 넣는 입구."""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import auto_save_toggle, queue_notice
from notebooklm_st.core import youtube
from notebooklm_st.services import questions, run_registry, runner, store

_URL_KEY = "ask_url"
_SELECTED_KEY = "ask_selected"
_AUTO_SAVE_KEY = "ask_auto_save"
_AUTO_SAVE_LOCKED_KEY = "ask_auto_save_locked"
_ENQUEUED_KEY = "ask_enqueued"


def render() -> None:
    """URL 입력, 질문 선택, 자동 저장 여부, 대기열에 넣기를 그린다.

    실행은 백그라운드 워커가 넣은 순서대로 맡는다. 이 화면은 넣기만
    하고 즉시 반환하므로, 앞 실행을 기다리지 않고 다음 영상을 넣을 수
    있다. 진행 상황과 답변은 실행 현황 화면에서 본다.
    """
    st.title("영상 질의")
    connection = session.get_connection()
    registry = session.get_registry()
    question_list = questions.list_questions(connection)

    url = st.text_input(
        "YouTube 영상 URL",
        key=_URL_KEY,
        placeholder="https://www.youtube.com/watch?v=...",
    )
    url_ok = youtube.is_valid(url)
    if url and not url_ok:
        st.error("단일 YouTube 영상 URL 이 아닙니다.")

    if not question_list:
        st.info("질문 관리 화면에서 질문을 먼저 등록하세요.")
        return

    selected = st.multiselect(
        "질문 선택",
        options=question_list,
        format_func=lambda question: question.title,
        key=_SELECTED_KEY,
    )
    auto_save = auto_save_toggle.render(
        connection, _AUTO_SAVE_KEY, _AUTO_SAVE_LOCKED_KEY
    )

    duplicate = _render_queue_notices(
        registry, youtube.extract_video_id(url) if url_ok else None
    )
    st.button(
        "실행",
        key="ask_run",
        disabled=duplicate or not (url_ok and selected),
        on_click=_enqueue,
        args=(registry, auto_save),
    )
    enqueued = st.session_state.pop(_ENQUEUED_KEY, None)
    if enqueued is not None:
        st.success(enqueued)


def _render_queue_notices(
    registry: run_registry.RunRegistry, video_id: str | None
) -> bool:
    """넣으면 언제 돌지 알리고, 같은 영상이 이미 들어 있는지 본다.

    Args:
        registry: 실행 레지스트리.
        video_id: 입력한 URL 의 영상 ID. URL 이 틀렸으면 ``None``.

    Returns:
        그 영상이 이미 대기 중이거나 실행 중이면 참. 버튼을 잠근다.
    """
    queue_notice.render(registry)
    duplicate = video_id is not None and registry.is_pending(video_id)
    if duplicate:
        st.info("이 영상은 이미 대기 중이거나 실행 중입니다.")
    return duplicate


def _enqueue(registry: run_registry.RunRegistry, auto_save: bool) -> None:
    """입력한 영상을 대기열에 넣고 URL 칸을 비운다.

    실행 버튼의 ``on_click`` 콜백이다. 콜백은 재실행 전에 돌므로 URL
    위젯의 키를 바꿔도 예외가 없다. URL·질문은 버튼을 그릴 때가 아니라
    누른 순간의 세션 값을 읽는다. 질문 선택은 남겨 다음 영상을 바로
    붙여 넣게 한다. 결과 문구는 세션에 적어 다음 그림에서 한 번
    보인다.

    Args:
        registry: 실행 레지스트리.
        auto_save: 화면에 보이는 자동 저장 값.
    """
    url = st.session_state.get(_URL_KEY, "")
    selected = st.session_state.get(_SELECTED_KEY, [])
    video_id = youtube.extract_video_id(url)
    if video_id is None or not selected or registry.is_pending(video_id):
        return
    ahead = queue_notice.count_ahead(registry)
    paused = registry.paused_reason() is not None
    digests = session.get_digest_registry()
    digesting = digests.is_running()
    runner.enqueue(
        registry,
        url,
        selected,
        store.default_db_path(),
        auto_save=auto_save,
        is_blocked=digests.is_running,
    )
    st.session_state[_URL_KEY] = ""
    st.session_state[_ENQUEUED_KEY] = queue_notice.enqueued_text(
        added=1, skipped=0, ahead=ahead, paused=paused, digesting=digesting
    )
```

- [ ] **Step 5: 테스트가 통과하는지 본다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest -q tests/test_components.py tests/pages/test_ask.py
```

Expected: `62 passed`. 질의 화면의 안내·결과 문구 테스트가 그대로 통과한다.

- [ ] **Step 6: 네 검사를 돌린다**

Task 1 Step 6 의 네 명령. Expected: 포맷 변경 없음, `All checks passed!`, `Success: no issues found`, `825 passed, 1 skipped`.

- [ ] **Step 7: 커밋한다**

```bash
msg="$(mktemp)"
cat > "$msg" <<'EOF'
♻️ refactor(ask): 대기열 안내를 공유 컴포넌트로 떼기

채널 화면도 넣기 전에 앞선 질의·정리본·멈춤을 알리고 넣은 뒤
결과를 한 문장으로 보이게 되므로, 안내 셋과 앞선 질의 수와 결과
문구를 components/queue_notice.py 로 옮긴다. 결과 문구는 넣은
수와 뺀 수를 이름 인자로 받는다. 한 건이면 질의 화면 문구와
글자 하나 다르지 않아 질의 화면 동작이 바뀌지 않는다.

Assisted-by: <모델 ID>
EOF
git add src/notebooklm_st/components/queue_notice.py src/notebooklm_st/pages/ask.py tests/test_components.py
git commit -F "$msg"
rm "$msg"
```

---

### Task 3: 신규 영상 표 모듈

**Files:**
- Create: `src/notebooklm_st/pages/_channel_videos.py`
- Test: `tests/pages/test_channels.py`(끝에 붙이기)

**Interfaces:**
- Consumes: `models.FeedEntry`, `runs.RunHandle`·`runs.RunStatus`, `youtube.watch_url(video_id)`
- Produces(Task 4 가 쓴다):
  - `_channel_videos.render(entries: Sequence[models.FeedEntry], handles: Sequence[runs.RunHandle], key: str) -> list[models.FeedEntry]`
  - `_channel_videos.selected_entries(entries: Sequence[models.FeedEntry], rows: Sequence[int]) -> list[models.FeedEntry]`
  - `_channel_videos.widget_key(entries: Sequence[models.FeedEntry], generation: int) -> str` — `channels_videos_` 로 시작
  - `_channel_videos.status_label(video_id: str, handles: Sequence[runs.RunHandle]) -> str | None`, `_channel_videos.STATUS_LABELS`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_channels.py` 끝에 붙인다. `make_entry` 는 이 파일에 이미 있다.

```python
def run_handle(video_id, status):
    """상태 칸을 시험할 실행 핸들 하나를 만든다."""
    from notebooklm_st.services import runs

    return runs.RunHandle(
        run_id=f"run-{video_id}-{status}",
        url=f"https://www.youtube.com/watch?v={video_id}",
        video_id=video_id,
        questions=(),
        auto_save=False,
        queued_at="2026-10-01T10:00:00",
        started_at=None,
        status=status,
        progress=[],
        result=None,
        save=None,
        error_message=None,
        error_level=None,
        finished_at=None,
    )


def test_status_label_names_each_state() -> None:
    """실행 상태 넷을 표에 적을 말로 옮기고, 실행이 없으면 비운다."""
    from notebooklm_st.pages import _channel_videos

    labels = [
        _channel_videos.status_label(
            "TbkUKCm3CHQ", [run_handle("TbkUKCm3CHQ", s)]
        )
        for s in ("queued", "running", "done", "failed")
    ]

    assert labels == ["대기 중", "실행 중", "끝남", "실패"]
    assert _channel_videos.status_label("TbkUKCm3CHQ", []) is None
    assert (
        _channel_videos.status_label(
            "TbkUKCm3CHQ", [run_handle("aaaaaaaaaaa", "queued")]
        )
        is None
    )


def test_status_label_takes_the_first_handle_of_the_video() -> None:
    """같은 영상의 실행이 여럿이면 목록에서 처음 만난 것을 쓴다.

    ``list_all`` 은 진행 중 → 대기 → 최근 끝난 순서다. 다시 넣어 도는
    영상이 지난 실패 때문에 "실패" 로 보이면 안 된다.
    """
    from notebooklm_st.pages import _channel_videos

    handles = [
        run_handle("TbkUKCm3CHQ", "running"),
        run_handle("TbkUKCm3CHQ", "failed"),
    ]

    assert _channel_videos.status_label("TbkUKCm3CHQ", handles) == "실행 중"


def test_widget_key_follows_the_list_and_the_generation() -> None:
    """같은 목록·같은 넣기 횟수는 같은 key, 하나라도 바뀌면 다른 key."""
    from notebooklm_st.pages import _channel_videos

    first = (make_entry("aaaaaaaaaaa"), make_entry("bbbbbbbbbbb"))
    other = (make_entry("aaaaaaaaaaa"),)

    key = _channel_videos.widget_key(first, 0)

    assert key == _channel_videos.widget_key(first, 0)
    assert key.startswith("channels_videos_")
    assert key != _channel_videos.widget_key(first, 1)
    assert key != _channel_videos.widget_key(other, 0)


def test_selected_entries_keep_the_list_order() -> None:
    """고른 행은 누른 순서가 아니라 목록 순서로, 낡은 번호는 버린다."""
    from notebooklm_st.pages import _channel_videos

    entries = (
        make_entry("aaaaaaaaaaa"),
        make_entry("bbbbbbbbbbb"),
        make_entry("ccccccccccc"),
    )

    picked = _channel_videos.selected_entries(entries, [2, 0, 9])

    assert [entry.video_id for entry in picked] == [
        "aaaaaaaaaaa",
        "ccccccccccc",
    ]


def video_table():
    """AppTest 진입점 — 신규 영상 둘로 표를 그리고 고른 것을 적는다."""
    import datetime

    import streamlit as st

    from notebooklm_st.core import models
    from notebooklm_st.pages import _channel_videos

    entries = (
        models.FeedEntry(
            video_id="aaaaaaaaaaa",
            title="둘째 영상",
            published=datetime.datetime.fromisoformat(
                "2026-09-26T01:00:00+00:00"
            ),
        ),
        models.FeedEntry(
            video_id="bbbbbbbbbbb",
            title="첫째 영상",
            published=datetime.datetime.fromisoformat(
                "2026-09-25T01:00:00+00:00"
            ),
        ),
    )
    key = _channel_videos.widget_key(entries, 0)
    picked = _channel_videos.render(entries, [], key)
    st.markdown("고른 영상: " + ",".join(e.video_id for e in picked))


def test_video_table_shows_the_entries(app_db) -> None:
    """표 하나에 제목·업로드일·상태·영상 링크가 목록 순서로 나온다."""
    app = v1.AppTest.from_function(video_table).run()

    assert not app.exception
    table = app.dataframe[0].value
    assert list(table.columns) == ["title", "published", "status", "url"]
    assert list(table["title"]) == ["둘째 영상", "첫째 영상"]
    local = [
        datetime.datetime.fromisoformat(value).astimezone()
        for value in ("2026-09-26T01:00:00+00:00", "2026-09-25T01:00:00+00:00")
    ]
    assert list(table["published"]) == [
        f"{moment:%Y-%m-%d %H:%M}" for moment in local
    ]
    assert table["status"].isna().all()
    assert list(table["url"]) == [
        "https://www.youtube.com/watch?v=aaaaaaaaaaa",
        "https://www.youtube.com/watch?v=bbbbbbbbbbb",
    ]
    assert app.caption[0].value == "행 왼쪽 칸을 눌러 고릅니다."


def test_video_table_returns_the_picked_entries(app_db) -> None:
    """표에서 고른 행의 영상을 목록 순서로 돌려준다."""
    from notebooklm_st.pages import _channel_videos

    app = v1.AppTest.from_function(video_table).run()
    entries = (make_entry("aaaaaaaaaaa"), make_entry("bbbbbbbbbbb"))
    app.session_state[_channel_videos.widget_key(entries, 0)] = {
        "selection": {"rows": [1, 0], "columns": [], "cells": []}
    }
    app.run()

    assert not app.exception
    assert "고른 영상: aaaaaaaaaaa,bbbbbbbbbbb" in [
        item.value for item in app.markdown
    ]
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest -q tests/pages/test_channels.py -k "status_label or widget_key or selected_entries or video_table"
```

Expected: `6 failed` — `ImportError: cannot import name '_channel_videos'`.

- [ ] **Step 3: 표 모듈을 만든다**

`src/notebooklm_st/pages/_channel_videos.py`:

```python
"""채널 화면의 신규 영상 표.

``pages/_channel_check.py`` 가 이 모듈을 부른다. 네비게이션에 직접
등록되지 않으므로 이름 앞에 밑줄을 둔다.

신규 영상을 표 하나로 보여 주고 행을 골라 대기열에 넣게 한다. 표는
선택을 **행 번호**로 돌려준다. 그래서 표의 key 를 영상 목록과 넣기
횟수에서 만들어, 목록이 바뀌거나 한 번 넣으면 선택이 비워지게 한다
(``widget_key`` 참고).
"""

import hashlib
from collections.abc import Sequence

import streamlit as st

from notebooklm_st.core import models, youtube
from notebooklm_st.services import runs

STATUS_LABELS: dict[runs.RunStatus, str] = {
    "queued": "대기 중",
    "running": "실행 중",
    "done": "끝남",
    "failed": "실패",
}
"""실행 상태를 표의 상태 칸에 적을 말."""

_KEY_PREFIX = "channels_videos_"


def render(
    entries: Sequence[models.FeedEntry],
    handles: Sequence[runs.RunHandle],
    key: str,
) -> list[models.FeedEntry]:
    """신규 영상 표를 그리고 고른 영상을 돌려준다.

    Args:
        entries: 신규 영상. 표에 이 순서대로 나온다.
        handles: 상태를 읽을 실행들. ``registry.list_all()`` 의
            순서 그대로다.
        key: 표의 위젯 key. ``widget_key`` 로 만든다.

    Returns:
        고른 영상. 누른 순서나 정렬과 상관없이 ``entries`` 의 순서를
        따른다.
    """
    st.caption("행 왼쪽 칸을 눌러 고릅니다.")
    event = st.dataframe(
        [
            _row(entry, status_label(entry.video_id, handles))
            for entry in entries
        ],
        key=key,
        on_select="rerun",
        selection_mode="multi-row",
        hide_index=True,
        placeholder="",
        column_config={
            "title": st.column_config.TextColumn("제목"),
            "published": st.column_config.TextColumn("업로드일"),
            "status": st.column_config.TextColumn("상태"),
            "url": st.column_config.LinkColumn("영상", display_text="열기"),
        },
    )
    return selected_entries(entries, event.selection.rows)


def selected_entries(
    entries: Sequence[models.FeedEntry], rows: Sequence[int]
) -> list[models.FeedEntry]:
    """고른 행 번호를 영상으로 옮긴다.

    표는 정렬해도 원래 목록의 위치 번호를 돌려준다. 번호를 정렬해
    목록 순서로 돌려주고, 목록 밖의 번호는 버린다.

    Args:
        entries: 표에 그린 신규 영상.
        rows: 고른 행의 위치 번호.

    Returns:
        고른 영상. ``entries`` 의 순서를 따른다.
    """
    return [entries[row] for row in sorted(rows) if 0 <= row < len(entries)]


def widget_key(entries: Sequence[models.FeedEntry], generation: int) -> str:
    """표의 위젯 key 를 영상 ID 구성과 넣기 횟수에서 만든다.

    key 를 준 표는 데이터가 바뀌어도 같은 위젯으로 남고, 고른 행
    번호도 그대로 남는다. 확인을 다시 눌러 목록이 바뀌면 그 번호가
    다른 영상을 가리킨다. 넣은 뒤에는 같은 영상을 다시 넣는 클릭을
    막으려고 선택을 비운다. 둘 다 key 가 바뀌면 Streamlit 이 새 표로
    보고 선택을 비운다.

    상태 칸은 key 에 넣지 않는다. 고르는 사이 실행이 끝나기만 해도
    고른 것이 사라지면 안 된다.

    Args:
        entries: 표에 오를 신규 영상. 순서까지 key 에 반영된다.
        generation: 이 화면에서 넣기를 한 횟수.

    Returns:
        같은 목록·같은 횟수에는 늘 같은 문자열.
    """
    ids = ",".join(entry.video_id for entry in entries)
    digest = hashlib.sha256(f"{ids}#{generation}".encode()).hexdigest()[:16]
    return f"{_KEY_PREFIX}{digest}"


def status_label(
    video_id: str, handles: Sequence[runs.RunHandle]
) -> str | None:
    """그 영상의 실행 상태를 표에 적을 말로 옮긴다.

    ``handles`` 는 진행 중 → 대기 → 최근 끝난 순서라 처음 만나는
    핸들이 지금 가장 의미 있는 상태다. 취소했거나 실행 현황에서 지운
    실행은 목록에 없으므로 빈칸으로 돌아온다.

    Args:
        video_id: 상태를 볼 영상 ID.
        handles: 레지스트리의 실행들.

    Returns:
        상태 라벨. 그 영상의 실행이 없으면 ``None``.
    """
    for handle in handles:
        if handle.video_id == video_id:
            return STATUS_LABELS[handle.status]
    return None


def _row(entry: models.FeedEntry, status: str | None) -> dict[str, str | None]:
    """영상 하나를 표의 한 행으로 만든다.

    열 순서가 곧 표의 열 순서다. 업로드일은 로컬 시각
    ``YYYY-MM-DD HH:MM`` 문자열이라 머리글 정렬이 시간 순서와 같다.
    표 칸은 일반 글자라 제목의 마크다운 글자를 걷을 필요가 없다.
    """
    return {
        "title": entry.title,
        "published": f"{entry.published.astimezone():%Y-%m-%d %H:%M}",
        "status": status,
        "url": youtube.watch_url(entry.video_id),
    }
```

- [ ] **Step 4: 테스트가 통과하는지 본다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest -q tests/pages/test_channels.py
```

Expected: `27 passed`. 상태 칸이 비면 표에서 결측(`isna`)으로 읽힌다.

- [ ] **Step 5: 네 검사를 돌린다**

Task 1 Step 6 의 네 명령. Expected: 포맷 변경 없음, `All checks passed!`, `Success: no issues found`, `831 passed, 1 skipped`.

- [ ] **Step 6: 커밋한다**

```bash
msg="$(mktemp)"
cat > "$msg" <<'EOF'
✨ feat(channels): 신규 영상 표 모듈 추가

채널 화면의 신규 영상을 st.dataframe 다중 행 선택 표로 그릴
pages/_channel_videos.py 를 더한다. 열은 제목·업로드일·상태·영상
링크다. 상태는 레지스트리의 같은 영상 첫 핸들에서 읽는다. 표는
선택을 원래 목록의 위치 번호로 돌려주므로 고른 행을 목록 순서의
영상으로 옮기고, 표 key 를 영상 목록과 넣기 횟수에서 만들어 목록이
바뀌거나 넣은 뒤에는 선택이 비게 한다. 화면에 잇는 일은 다음
커밋이 한다.

Assisted-by: <모델 ID>
EOF
git add src/notebooklm_st/pages/_channel_videos.py tests/pages/test_channels.py
git commit -F "$msg"
rm "$msg"
```

---

### Task 4: 표에서 고른 신규 영상을 한 번에 대기열에 넣기

**Files:**
- Create: `src/notebooklm_st/pages/_channel_enqueue.py`
- Modify: `src/notebooklm_st/pages/_channel_check.py`(파일 전체를 아래 내용으로)
- Modify: `src/notebooklm_st/services/run_store.py`(독스트링 두 줄)
- Test: `tests/pages/test_channels.py`

**Interfaces:**
- Consumes: Task 1 `auto_save_toggle.render`, Task 2 `queue_notice.render`·`count_ahead`·`enqueued_text`, Task 3 `_channel_videos.render`·`selected_entries`·`widget_key`, `runner.enqueue(registry, url, questions, db_path, auto_save=…, is_blocked=…)`, `registry.is_pending(video_id)`·`paused_reason()`·`list_all()`
- Produces: `_channel_enqueue.generation() -> int`, `_channel_enqueue.render(registry, entries, table_key, questions_key, selected, chosen, auto_save) -> None`. 버튼 key `channels_enqueue`. 테스트는 `_channel_enqueue.runner.enqueue` 를 가짜로 바꾼다.

- [ ] **Step 1: 테스트를 고친다**

`tests/pages/test_channels.py` 를 처음부터 끝까지 읽고 여섯 군데를 고친다.

(가) import 절을 이렇게 만든다(`session` 과 `youtube` 가 늘어난다).

```python
import datetime

import pytest
from streamlit.testing import v1

from notebooklm_st import session
from notebooklm_st.core import models, youtube
from notebooklm_st.services import (
    channel_feed,
    channel_lookup,
    channels,
    outline,
    questions,
    run_history,
    settings,
)
```

(나) `fake_sources` fixture 바로 뒤, `test_no_channels_shows_a_notice` 앞에 도우미를 넣는다.

```python
NEWER = make_entry("aaaaaaaaaaa", "2026-09-26T01:00:00+00:00")
OLDER = make_entry("bbbbbbbbbbb", "2026-09-25T01:00:00+00:00")
BOTH = (NEWER, OLDER)
"""신규 영상 둘. 표는 업로드가 늦은 것부터라 이 순서로 오른다."""


def set_outline_env(monkeypatch) -> None:
    """자동 저장 체크가 열리도록 Outline 설정을 채운다."""
    monkeypatch.setenv(outline.URL_ENV_VAR, "http://192.168.0.10:3000")
    monkeypatch.setenv(outline.TOKEN_ENV_VAR, "ol_secret")
    monkeypatch.setenv(outline.COLLECTION_ENV_VAR, "col-1")


def record_enqueue(monkeypatch) -> list[tuple[str, list[str], bool]]:
    """``runner.enqueue`` 를 막고 넘어온 값을 기록한다.

    스레드를 띄우지 않고 레지스트리에 대기로만 넣는다. 그래야 같은
    영상 판정(``is_pending``)과 상태 칸이 실제처럼 돈다.

    Returns:
        부른 순서대로 (URL, 질문 제목들, 자동 저장).
    """
    from notebooklm_st.pages import _channel_enqueue

    calls: list[tuple[str, list[str], bool]] = []

    def fake_enqueue(registry, url, question_list, db_path, **kwargs):
        """넘어온 값을 기록하고 대기로만 넣는다."""
        titles = [question.title for question in question_list]
        calls.append((url, titles, kwargs["auto_save"]))
        return registry.enqueue(
            url, youtube.extract_video_id(url) or "", tuple(question_list)
        )

    monkeypatch.setattr(_channel_enqueue.runner, "enqueue", fake_enqueue)
    return calls


def put_pending(connection, video_id) -> None:
    """그 영상을 대기열에 넣어 둔다. 워커는 띄우지 않는다."""
    session.get_registry().enqueue(
        youtube.watch_url(video_id),
        video_id,
        tuple(questions.list_questions(connection)),
    )


def checked(app_db, monkeypatch, *entries, choose=True):
    """채널과 질문을 하나씩 두고 확인을 눌러 신규를 띄운다.

    Args:
        app_db: 앱이 쓰는 임시 DB.
        monkeypatch: 피드를 막을 pytest 도구.
        *entries: 피드가 줄 항목들.
        choose: 참이면 등록한 질문을 고른다.

    Returns:
        확인을 마친 AppTest.
    """
    registered(app_db)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    check_feed(monkeypatch, feed_with(*entries))
    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    if choose:
        app.multiselect[0].select(questions.list_questions(app_db)[0]).run()
    return app


def select_videos(app, entries, rows, generation=0) -> None:
    """신규 영상 표에서 행을 고른다.

    AppTest 는 표 클릭을 흉내 내지 못한다. 대신 Streamlit 이 허용하는
    세션 상태 주입을 쓴다. 브라우저가 선택을 되돌려 보내지 않으므로
    선택은 바로 다음 실행 한 번에만 반영된다.

    Args:
        app: 확인을 마친 AppTest.
        entries: 표에 오른 순서 그대로의 신규 영상.
        rows: 고를 행의 위치 번호.
        generation: 이 화면에서 넣기를 한 횟수.
    """
    from notebooklm_st.pages import _channel_videos

    key = _channel_videos.widget_key(entries, generation)
    app.session_state[key] = {
        "selection": {"rows": rows, "columns": [], "cells": []}
    }


def click_enqueue(app, entries, rows) -> None:
    """영상을 고른 채로 넣기 버튼을 누른다.

    AppTest 는 직전 실행에서 잠긴 버튼을 누르지 못하게 막는다. 한 번
    골라 버튼을 풀고, 누르는 실행에서 다시 고른다 — 선택이 한 실행만
    가기 때문이다.
    """
    select_videos(app, entries, rows)
    app.run()
    select_videos(app, entries, rows)
    app.button(key="channels_enqueue").click().run()
```

(다) `test_checking_lists_new_videos` 를 통째로 이것으로 바꾼다. 제목은 이제 마크다운이 아니라 표에 있다.

```python
def test_checking_lists_new_videos(app_db, monkeypatch) -> None:
    """확인을 누르면 신규 영상이 채널 이름 아래 표로 나온다."""
    app = checked(app_db, monkeypatch, make_entry())

    assert not app.exception
    assert [item.value for item in app.subheader] == ["Fireship"]
    assert list(app.dataframe[0].value["title"]) == ["새 영상"]
```

(라) `test_switching_the_target_channel_clears_the_result` 를 통째로 이것으로 바꾼다.

```python
def test_switching_the_target_channel_clears_the_result(
    app_db, monkeypatch
) -> None:
    """대상 채널을 바꾸면 앞서 확인한 결과가 사라진다.

    다른 채널의 목록이 남아 있으면 무엇을 보고 있는지 알 수 없다.
    """
    registered(app_db, title="가 채널")
    registered(app_db, title="나 채널", channel_id=OTHER_CHANNEL_ID)
    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
    check_feed(monkeypatch, feed_with(make_entry()))

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()
    assert len(app.dataframe) == 1

    second = channels.list_channels(app_db)[1]
    app.selectbox[0].set_value(second).run()

    assert not app.exception
    assert len(app.dataframe) == 0
```

(마) 다음 여섯 테스트를 지운다. 바뀐 정책과 맞지 않는다(설계서 §11).

- `test_no_questions_blocks_the_summary`
- `test_summary_hands_the_video_to_the_runner`
- `test_summary_never_auto_saves`
- `test_a_queued_query_blocks_the_summary`
- `test_a_paused_queue_blocks_the_summary`
- `test_a_running_query_blocks_the_summary`

(바) 지운 자리(`test_a_feed_failure_on_the_target_shows_the_reason` 뒤, Task 3 의 `run_handle` 앞)에 넣는다.

```python
def test_no_questions_shows_the_table_without_a_button(
    app_db, monkeypatch
) -> None:
    """질문이 없으면 안내와 표만 그리고 넣기 쪽은 그리지 않는다."""
    registered(app_db)
    check_feed(monkeypatch, feed_with(make_entry()))

    app = v1.AppTest.from_function(script)
    app.run()
    button_by(app, "새 영상 확인").click().run()

    assert not app.exception
    assert any("질문 관리" in item.value for item in app.info)
    assert len(app.dataframe) == 1
    assert len(app.checkbox) == 0
    assert all(item.key != "channels_enqueue" for item in app.button)


def test_enqueue_waits_for_a_question_and_a_row(app_db, monkeypatch) -> None:
    """질문을 고르지 않았거나 행을 고르지 않았으면 버튼이 잠긴다."""
    app = checked(app_db, monkeypatch, make_entry(), choose=False)

    assert "질문을 하나 이상 고르세요." in [item.value for item in app.info]
    assert app.button(key="channels_enqueue").disabled is True

    app.multiselect[0].select(questions.list_questions(app_db)[0]).run()

    button = app.button(key="channels_enqueue")
    assert button.label == "선택한 영상 요약 (0건)"
    assert button.disabled is True


def test_enqueue_puts_the_picked_videos_in_list_order(
    app_db, monkeypatch
) -> None:
    """고른 영상을 누른 순서가 아니라 목록 순서로 넣는다."""
    calls = record_enqueue(monkeypatch)
    app = checked(app_db, monkeypatch, *BOTH)
    select_videos(app, BOTH, [1, 0])
    app.run()

    assert app.button(key="channels_enqueue").label == (
        "선택한 영상 요약 (2건)"
    )
    click_enqueue(app, BOTH, [1, 0])

    assert not app.exception
    assert calls == [
        ("https://www.youtube.com/watch?v=aaaaaaaaaaa", ["핵심 주장"], False),
        ("https://www.youtube.com/watch?v=bbbbbbbbbbb", ["핵심 주장"], False),
    ]


def test_enqueue_reports_and_clears_the_selection(app_db, monkeypatch) -> None:
    """넣으면 결과를 한 번 알리고, 넣기 전 선택은 새 표에 안 붙는다."""
    record_enqueue(monkeypatch)
    app = checked(app_db, monkeypatch, *BOTH)
    click_enqueue(app, BOTH, [0, 1])

    assert not app.exception
    assert [item.value for item in app.success] == [
        "2건을 넣고 첫 영상부터 시작했습니다. 실행 현황 화면에서 확인하세요."
    ]
    assert list(app.dataframe[0].value["status"]) == ["대기 중", "대기 중"]

    select_videos(app, BOTH, [0, 1])
    app.run()

    assert app.button(key="channels_enqueue").label == (
        "선택한 영상 요약 (0건)"
    )
    assert len(app.success) == 0


def test_a_pending_video_is_left_out(app_db, monkeypatch) -> None:
    """대기 중인 영상은 다시 넣지 않고, 뺀 수를 결과 끝에 적는다."""
    calls = record_enqueue(monkeypatch)
    app = checked(app_db, monkeypatch, *BOTH)
    put_pending(app_db, "aaaaaaaaaaa")
    app.run()

    assert app.dataframe[0].value["status"].iloc[0] == "대기 중"
    click_enqueue(app, BOTH, [0, 1])

    assert not app.exception
    assert [call[0] for call in calls] == [
        "https://www.youtube.com/watch?v=bbbbbbbbbbb"
    ]
    assert [item.value for item in app.success] == [
        "대기열에 넣었습니다 — 앞에 1건. 실행 현황 화면에서 확인하세요."
        " 이미 대기 중이거나 실행 중인 1건은 뺐습니다."
    ]


def test_only_pending_videos_add_nothing(app_db, monkeypatch) -> None:
    """고른 영상이 모두 대기 중이면 아무것도 넣지 않고 그렇게 알린다."""
    calls = record_enqueue(monkeypatch)
    app = checked(app_db, monkeypatch, make_entry())
    put_pending(app_db, "TbkUKCm3CHQ")
    click_enqueue(app, (make_entry(),), [0])

    assert not app.exception
    assert calls == []
    assert len(app.success) == 0
    assert "고른 영상은 모두 이미 대기 중이거나 실행 중입니다." in [
        item.value for item in app.info
    ]


def test_a_running_query_does_not_lock_the_enqueue(app_db, monkeypatch) -> None:
    """질의가 돌고 있어도 넣을 수 있고, 몇 번째인지 알린다."""
    record_enqueue(monkeypatch)
    app = checked(app_db, monkeypatch, make_entry())
    registry = session.get_registry()
    put_pending(app_db, "dQw4w9WgXcQ")
    registry.acquire_worker()
    registry.claim_next()
    select_videos(app, (make_entry(),), [0])
    app.run()

    assert app.button(key="channels_enqueue").disabled is False
    assert (
        "실행 중이거나 대기 중인 질의가 1건 있습니다. 넣으면 그 뒤에"
        " 실행됩니다."
    ) in [item.value for item in app.info]
    click_enqueue(app, (make_entry(),), [0])

    assert not app.exception
    assert [item.value for item in app.success] == [
        "대기열에 넣었습니다 — 앞에 1건. 실행 현황 화면에서 확인하세요."
    ]


def test_a_paused_queue_still_takes_videos(app_db, monkeypatch) -> None:
    """멈춘 대기열에도 넣고, 재개할 때까지 기다린다고 알린다."""
    record_enqueue(monkeypatch)
    app = checked(app_db, monkeypatch, make_entry())
    put_pending(app_db, "dQw4w9WgXcQ")
    session.get_registry().pause("요청 한도를 초과했습니다.")
    click_enqueue(app, (make_entry(),), [0])

    assert not app.exception
    assert [item.value for item in app.warning] == [
        "대기열이 멈춰 있습니다. 넣은 질의는 실행 현황에서 재개할 때까지"
        " 기다립니다."
    ]
    assert [item.value for item in app.success] == [
        "대기열에 넣었습니다. 대기열이 멈춰 있어 재개할 때까지 기다립니다."
    ]


def test_a_digest_does_not_lock_the_enqueue(app_db, monkeypatch) -> None:
    """정리본을 작성 중이어도 넣고, 끝난 뒤 시작한다고 알린다."""
    record_enqueue(monkeypatch)
    app = checked(app_db, monkeypatch, make_entry())
    session.get_digest_registry().start()
    click_enqueue(app, (make_entry(),), [0])

    assert not app.exception
    assert (
        "정리본을 작성 중입니다. 넣은 질의는 정리본이 끝난 뒤 시작합니다."
    ) in [item.value for item in app.info]
    assert [item.value for item in app.success] == [
        "대기열에 넣었습니다. 정리본이 끝나면 시작합니다."
    ]


def test_enqueue_follows_the_auto_save_setting(app_db, monkeypatch) -> None:
    """자동 저장은 질의 화면과 같은 설정에서 시작해 그 값으로 넣는다."""
    set_outline_env(monkeypatch)
    settings.set_auto_save(app_db, True)
    calls = record_enqueue(monkeypatch)
    app = checked(app_db, monkeypatch, make_entry())

    assert app.checkbox(key="channels_auto_save").value is True
    click_enqueue(app, (make_entry(),), [0])

    assert not app.exception
    assert [call[2] for call in calls] == [True]


def test_enqueue_hands_the_shown_auto_save(app_db, monkeypatch) -> None:
    """방금 끈 체크 값이 그대로 넘어가고 설정에도 남는다."""
    set_outline_env(monkeypatch)
    settings.set_auto_save(app_db, True)
    calls = record_enqueue(monkeypatch)
    app = checked(app_db, monkeypatch, make_entry())
    app.checkbox(key="channels_auto_save").uncheck().run()
    click_enqueue(app, (make_entry(),), [0])

    assert not app.exception
    assert [call[2] for call in calls] == [False]
    assert settings.auto_save(app_db) is False


def test_enqueue_without_outline_hands_no_auto_save(
    app_db, monkeypatch
) -> None:
    """Outline 설정이 없으면 체크가 잠기고 자동 저장 없이 넣는다."""
    settings.set_auto_save(app_db, True)
    calls = record_enqueue(monkeypatch)
    app = checked(app_db, monkeypatch, make_entry())

    box = app.checkbox(key="channels_auto_save_locked")
    assert box.disabled is True
    assert box.value is False
    click_enqueue(app, (make_entry(),), [0])

    assert not app.exception
    assert [call[2] for call in calls] == [False]
    assert settings.auto_save(app_db) is True
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest -q tests/pages/test_channels.py
```

Expected: `14 failed, 19 passed`. 새로 쓴 열네 건이 실패한다(`_channel_enqueue` 가 없거나, 표·넣기 버튼이 아직 없다).

- [ ] **Step 3: 넣기 모듈을 만든다**

`src/notebooklm_st/pages/_channel_enqueue.py`:

```python
"""채널 화면의 넣기 — 표에서 고른 신규 영상을 질의 대기열에 넣는다.

``pages/_channel_check.py`` 가 이 모듈을 부른다. 네비게이션에 직접
등록되지 않으므로 이름 앞에 밑줄을 둔다.

넣기는 버튼의 ``on_click`` 콜백이 한다. 콜백은 재실행 전에 돌므로,
넣기 횟수를 올리면 다음 그림의 표가 새 key 로 그려져 선택이
비워진다(``pages/_channel_videos.widget_key``).
"""

import dataclasses

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import queue_notice
from notebooklm_st.core import models, youtube
from notebooklm_st.pages import _channel_videos
from notebooklm_st.services import run_registry, runner, store

_GENERATION_KEY = "channels_generation"
_ENQUEUED_KEY = "channels_enqueued"

_ALL_PENDING = "고른 영상은 모두 이미 대기 중이거나 실행 중입니다."


@dataclasses.dataclass(frozen=True, slots=True)
class _Enqueued:
    """넣은 뒤 한 번 보일 결과. 세션에 담는 화면 전용 값이다."""

    text: str
    added: bool
    """하나라도 넣었는가. 거짓이면 성공이 아니라 안내로 보인다."""


def generation() -> int:
    """이 화면에서 넣기를 한 횟수. 표의 key 에 섞는다."""
    count: int = st.session_state.get(_GENERATION_KEY, 0)
    return count


def render(
    registry: run_registry.RunRegistry,
    entries: tuple[models.FeedEntry, ...],
    table_key: str,
    questions_key: str,
    selected: list[models.FeedEntry],
    chosen: list[models.Question],
    auto_save: bool,
) -> None:
    """질문 안내, 넣기 버튼, 넣은 뒤의 결과를 그린다.

    Args:
        registry: 실행 레지스트리.
        entries: 표에 그린 신규 영상.
        table_key: 표의 위젯 key. 콜백이 누른 순간의 선택을 읽는다.
        questions_key: 질문 선택의 위젯 key. 콜백이 누른 순간의
            질문을 읽는다.
        selected: 지금 표에서 고른 영상. 버튼 라벨과 잠금에 쓴다.
        chosen: 지금 고른 질문들. 버튼 잠금에 쓴다.
        auto_save: 화면에 보이는 자동 저장 값.
    """
    if not chosen:
        st.info("질문을 하나 이상 고르세요.")
    st.button(
        f"선택한 영상 요약 ({len(selected)}건)",
        key="channels_enqueue",
        disabled=not selected or not chosen,
        on_click=_enqueue_selected,
        args=(registry, entries, table_key, questions_key, auto_save),
    )
    _render_result()


def _enqueue_selected(
    registry: run_registry.RunRegistry,
    entries: tuple[models.FeedEntry, ...],
    table_key: str,
    questions_key: str,
    auto_save: bool,
) -> None:
    """고른 영상을 목록 순서로 대기열에 넣고 표의 선택을 비운다.

    넣기 버튼의 ``on_click`` 콜백이다. 표 선택과 질문은 버튼을 그릴
    때가 아니라 누른 순간의 세션 값을 읽는다. 결과 문구는 세션에
    적어 다음 그림에서 한 번 보인다.

    Args:
        registry: 실행 레지스트리.
        entries: 표에 그린 신규 영상.
        table_key: 표의 위젯 key.
        questions_key: 질문 선택의 위젯 key.
        auto_save: 화면에 보이는 자동 저장 값. 넣은 실행마다 고정된다.
    """
    state = st.session_state.get(table_key) or {}
    rows = state.get("selection", {}).get("rows", [])
    chosen = st.session_state.get(questions_key, [])
    targets = _channel_videos.selected_entries(entries, rows)
    if not targets or not chosen:
        return
    ahead = queue_notice.count_ahead(registry)
    paused = registry.paused_reason() is not None
    digesting = session.get_digest_registry().is_running()
    added = _enqueue_each(registry, targets, chosen, auto_save)
    st.session_state[_GENERATION_KEY] = generation() + 1
    if added == 0:
        st.session_state[_ENQUEUED_KEY] = _Enqueued(_ALL_PENDING, added=False)
        return
    text = queue_notice.enqueued_text(
        added=added,
        skipped=len(targets) - added,
        ahead=ahead,
        paused=paused,
        digesting=digesting,
    )
    st.session_state[_ENQUEUED_KEY] = _Enqueued(text, added=True)


def _enqueue_each(
    registry: run_registry.RunRegistry,
    targets: list[models.FeedEntry],
    chosen: list[models.Question],
    auto_save: bool,
) -> int:
    """대기·실행 중이 아닌 영상을 차례로 넣고 넣은 수를 돌려준다.

    질의 화면과 같은 기준으로 거른다. 끝났거나 실패한 영상은 다시
    넣는다.

    Args:
        registry: 실행 레지스트리.
        targets: 넣을 영상. 이 순서대로 대기열에 선다.
        chosen: 모든 영상에 쓸 질문들.
        auto_save: 넣은 실행에 고정할 자동 저장 값.

    Returns:
        넣은 수.
    """
    digests = session.get_digest_registry()
    added = 0
    for entry in targets:
        if registry.is_pending(entry.video_id):
            continue
        runner.enqueue(
            registry,
            youtube.watch_url(entry.video_id),
            chosen,
            store.default_db_path(),
            auto_save=auto_save,
            is_blocked=digests.is_running,
        )
        added += 1
    return added


def _render_result() -> None:
    """넣은 뒤의 결과를 한 번 보인다."""
    result = st.session_state.pop(_ENQUEUED_KEY, None)
    if result is None:
        return
    if result.added:
        st.success(result.text)
    else:
        st.info(result.text)
```

- [ ] **Step 4: 확인 탭이 표와 넣기를 잇게 한다**

`src/notebooklm_st/pages/_channel_check.py` 를 처음부터 끝까지 읽은 뒤 이 내용으로 바꾼다. `render`·`_start_check`·`_check` 는 그대로이고(`_start_check` 의 `_STARTED_KEY` 초기화 한 줄만 빠진다), `_render_found` 가 공유 조각·표·넣기를 부르게 바뀌며, `_blocked_reason`·`_render_entry`·`_STARTED_KEY` 가 사라진다.

```python
"""채널 화면의 "새 영상 확인" 탭 — 신규를 골라 대기열에 넣는다.

``pages/channels.py`` 가 이 모듈을 부른다. 네비게이션에 직접 등록되지
않으므로 이름 앞에 밑줄을 둔다.

**확인 대상은 채널 하나다.** 기준일이 그 채널 하나에만 적용되므로
"이 기준일이 무엇에 걸리는가" 가 애매해지지 않는다. 고른 기준일은
확인할 때 그 채널에 저장되어, 기준일을 정하는 자리가 화면에 하나만
남는다.

신규는 표에서 여러 건을 골라 한 번에 질의 대기열에 넣는다. 표는
``pages/_channel_videos.py``, 넣기는 ``pages/_channel_enqueue.py`` 가
맡는다. 진행 상황과 결과는 실행 현황 화면에서 본다.
"""

import dataclasses
import datetime
import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import auto_save_toggle, queue_notice
from notebooklm_st.core import models, new_videos
from notebooklm_st.pages import _channel_enqueue, _channel_videos
from notebooklm_st.services import (
    channel_feed,
    channels,
    questions,
    run_history,
)

_TARGET_KEY = "channels_target"
_QUESTIONS_KEY = "channels_questions"
_FOUND_KEY = "channels_found"
_AUTO_SAVE_KEY = "channels_auto_save"
_AUTO_SAVE_LOCKED_KEY = "channels_auto_save_locked"


@dataclasses.dataclass(frozen=True, slots=True)
class _Checked:
    """채널 하나의 확인 결과.

    세션에 담는 화면 전용 값이다. 채널 제목을 복사해 두므로 확인
    뒤에 채널을 지워도 목록이 그대로 보인다. ``channel_pk`` 는 지금
    고른 채널의 결과인지 가리는 데 쓴다.
    """

    channel_pk: int
    title: str
    entries: tuple[models.FeedEntry, ...]
    error: str | None


def render(
    connection: sqlite3.Connection, channel_list: list[models.Channel]
) -> None:
    """대상 채널과 기준일을 받아 신규를 찾고 대기열에 넣게 한다.

    Args:
        connection: 열린 커넥션.
        channel_list: 등록된 채널들. 비어 있지 않다.
    """
    target = st.selectbox(
        "대상 채널",
        options=channel_list,
        format_func=lambda channel: channel.title,
        key=_TARGET_KEY,
    )
    baseline = st.date_input(
        # 위젯 key 에 채널 id 를 넣는다. key 가 같으면 Streamlit 이
        # 세션 값을 우선해, 채널을 바꿔도 앞 채널의 날짜가 남는다.
        "이 채널의 기준일",
        value=datetime.date.fromisoformat(target.baseline),
        key=f"channels_check_baseline_{target.id}",
        help="이 날짜 이후 업로드된 영상만 새 영상으로 봅니다."
        " 확인을 누르면 이 채널의 기준일로 저장됩니다. 피드가 최신"
        " 15건까지만 주므로 그보다 거슬러 올라가지는 못합니다.",
    )
    if st.button("새 영상 확인", key="channels_check"):
        _start_check(connection, target, baseline)
    found = st.session_state.get(_FOUND_KEY)
    if found is None or found.channel_pk != target.id:
        # 다른 채널의 결과가 남아 있으면 무엇을 보고 있는지 알 수
        # 없다. 대상이 바뀌면 그리지 않는다.
        return
    _render_found(connection, found)


def _start_check(
    connection: sqlite3.Connection,
    target: models.Channel,
    baseline: object,
) -> None:
    """기준일을 저장하고 그 채널을 조회한다.

    Args:
        connection: 열린 커넥션.
        target: 확인할 채널.
        baseline: ``st.date_input`` 이 돌려준 값. 범위 선택이면
            날짜가 아니므로 막는다.
    """
    if not isinstance(baseline, datetime.date):
        st.error("기준일을 하나 고르세요.")
        return
    try:
        channels.update_baseline(connection, target.id, baseline.isoformat())
    except ValueError as error:
        st.error(str(error))
        return
    st.session_state[_FOUND_KEY] = _check(connection, target, baseline)


def _check(
    connection: sqlite3.Connection,
    target: models.Channel,
    baseline: datetime.date,
) -> _Checked:
    """피드를 읽어 신규를 고른다.

    방금 고른 기준일을 쓴다. ``target.baseline`` 은 이번 실행에서
    읽어 온 값이라 아직 옛 날짜다.

    Args:
        connection: 열린 커넥션.
        target: 확인할 채널.
        baseline: 방금 저장한 기준일.

    Returns:
        신규 목록 또는 사람에게 보여 줄 실패 사유.
    """
    known = run_history.list_video_ids(connection)
    with st.spinner("새 영상을 확인하는 중"):
        feed = channel_feed.fetch(target.channel_id)
    if feed.error is not None:
        return _Checked(target.id, target.title, (), feed.error)
    return _Checked(
        target.id,
        target.title,
        new_videos.select(feed.entries, baseline.isoformat(), known),
        None,
    )


def _render_found(connection: sqlite3.Connection, found: _Checked) -> None:
    """확인 결과를 표로 그리고 고른 영상을 넣을 수 있게 한다.

    질문 선택은 결과보다 먼저 그린다. 결과가 오류나 빈 목록이어도
    위젯이 그려져야 고른 질문이 남는다.
    """
    question_list = questions.list_questions(connection)
    chosen: list[models.Question] = []
    if not question_list:
        st.info("질문 관리 화면에서 질문을 먼저 등록하세요.")
    else:
        chosen = st.multiselect(
            "질문 선택",
            options=question_list,
            format_func=lambda question: question.title,
            key=_QUESTIONS_KEY,
            help="고른 질문을 이번에 넣는 영상 모두에 씁니다.",
        )
    if found.error is not None:
        st.error(f"{found.title}: {found.error}")
        return
    if not found.entries:
        st.info("새 영상이 없습니다.")
        return
    registry = session.get_registry()
    auto_save = False
    if question_list:
        auto_save = auto_save_toggle.render(
            connection, _AUTO_SAVE_KEY, _AUTO_SAVE_LOCKED_KEY
        )
        queue_notice.render(registry)
    st.subheader(found.title)
    key = _channel_videos.widget_key(
        found.entries, _channel_enqueue.generation()
    )
    selected = _channel_videos.render(found.entries, registry.list_all(), key)
    if question_list:
        _channel_enqueue.render(
            registry,
            found.entries,
            key,
            _QUESTIONS_KEY,
            selected,
            chosen,
            auto_save,
        )
```

- [ ] **Step 5: 보관소 독스트링을 사실에 맞춘다**

`src/notebooklm_st/services/run_store.py` 의 `RunStore.enqueue` 독스트링에서:

```python
            auto_save: 답변을 받자마자 Outline 에 올릴지. 사람이
                저장하는 입구(채널 화면)는 기본값을 쓴다.
```

→

```python
            auto_save: 답변을 받자마자 Outline 에 올릴지. 러너는 늘
                값을 넘긴다. 기본값은 테스트가 핸들을 만들 때 쓴다.
```

- [ ] **Step 6: 테스트가 통과하는지 본다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest -q tests/pages/test_channels.py tests/pages/test_ask.py tests/test_components.py
grep -rn -E "_STARTED_KEY|_blocked_reason|_render_entry|채널 화면\)는 기본값" src
```

Expected: `95 passed`. grep 은 아무것도 찍지 않는다.

- [ ] **Step 7: 네 검사와 줄 수를 본다**

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
wc -l src/notebooklm_st/pages/_channel_check.py src/notebooklm_st/pages/_channel_enqueue.py src/notebooklm_st/pages/_channel_videos.py src/notebooklm_st/pages/ask.py src/notebooklm_st/components/auto_save_toggle.py src/notebooklm_st/components/queue_notice.py
```

Expected: 포맷 변경 없음, `All checks passed!`, `Success: no issues found`, `837 passed, 1 skipped`. 줄 수는 190·164·145·119·74·84 로 모두 300 이하.

- [ ] **Step 8: 커밋한다**

```bash
msg="$(mktemp)"
cat > "$msg" <<'EOF'
✨ feat(channels): 표에서 고른 신규 영상을 한 번에 대기열에 넣기

채널 화면의 신규 목록을 표로 바꾸고, 행을 골라 버튼 하나로 질의
대기열에 넣는다. 지금까지는 영상마다 요약 버튼이 있고 하나를
누르면 끝날 때까지 나머지가 모두 잠겨, 여러 건을 요약하려면 한
건씩 돌아와야 했다.

질의 화면과 규칙을 맞춘다. 앞선 질의·정리본·멈춘 대기열이 있어도
막지 않고 안내만 하며, 대기·실행 중인 영상만 빼고 그 수를
알린다. 자동 저장은 질의 화면과 같은 설정을 쓴다. 넣기는 버튼
콜백이 누른 순간의 표 선택을 읽어 목록 순서로 넣고, 넣기 횟수를
표 key 에 섞어 선택을 비운다. 확인 탭이 300줄을 넘지 않도록
넣기는 pages/_channel_enqueue.py 로 뗀다.

러너만 RunStore.enqueue 를 부르고 늘 값을 넘기므로, 채널 화면이
기본값을 쓴다던 독스트링 두 줄을 사실에 맞춘다.

Assisted-by: <모델 ID>
EOF
git add src/notebooklm_st/pages/_channel_enqueue.py src/notebooklm_st/pages/_channel_check.py src/notebooklm_st/services/run_store.py tests/pages/test_channels.py
git commit -F "$msg"
rm "$msg"
```

---

### Task 5: 안내 문서와 설계 문서 둘

**Files:**
- Modify: `README.md`, `docs/ONBOARDING.md`
- Rewrite: `docs/superpowers/specs/2026-09-23-channel-watch-design.md`, `docs/superpowers/specs/2026-09-30-run-queue-and-auto-save-design.md`(각각 통째로 다시 쓰기, 한 문서에 커밋 하나)

**Interfaces:**
- Consumes: Task 1~4 의 최종 동작과 이름
- Produces: 없음(문서)

설계서 §12 가 고를 자리를 정했다. 자리마다 "지금" 글자는 그 문서에서 정확히 한 번 나온다(기계로 대조했다). "바꾼 뒤" 가 "지금" 을 앞에 그대로 품으면 그 뒤에 새 글을 넣는 것이다. "지운다" 는 그 덩어리를 통째로 지우고 앞뒤 줄은 그대로 둔다. 경위("원래는·바뀌었다")를 본문에 넣지 않는다.

그대로 두는 자리(틀리지 않는다): 대기열 설계서 §2.1 의 가드 표(대기열을 설계할 때 조사한 사실), §13 표의 대기열 줄에 적힌 `pages/_channel_check.py`(그 단계가 고친 파일), 채널 감시 설계서 §2.6 "서로를 막는다", §11 의 피드 404·5xx 줄(피드 처리는 이번 범위 밖).

- [ ] **Step 1: 안내 문서 둘을 고친다**

`README.md` 와 `docs/ONBOARDING.md` 에서 네 자리. README 의 두 자리는 한 줄 안의 문장이다.

(R1 채널 사용법)

````markdown
아직 요약하지 않은 영상만 모입니다. 목록에서 바로 요약을 시작합니다.
````

→

````markdown
아직 요약하지 않은 영상만 표로 모입니다. 표에서 행을 골라 **선택한 영상 요약**을 누르면 고른 영상이 질의 대기열에 차례로 들어갑니다. 질의 화면과 같은 **자동 저장** 체크를 쓰고, 이미 대기 중이거나 실행 중인 영상은 빠집니다.
````

(R2 Outline 설정이 없을 때)

````markdown
질의 화면의 **자동 저장** 체크가 잠깁니다.
````

→

````markdown
질의 화면과 채널 화면의 **자동 저장** 체크가 잠깁니다.
````

(O1 채널 화면 줄)

````markdown
| `pages/ask.py` | moderate | 질의 화면. URL 입력·질문 선택 후 대기열에 넣고 반환. 실행 중이어도 넣고, 같은 영상이 대기·실행 중이면 막는다. 넣기는 버튼 콜백이 한다 |
````

→

````markdown
| `pages/ask.py` | moderate | 질의 화면. URL 입력·질문 선택 후 대기열에 넣고 반환. 실행 중이어도 넣고, 같은 영상이 대기·실행 중이면 막는다. 넣기는 버튼 콜백이 한다 |
| `pages/channels.py`·`_channel_check.py`·`_channel_videos.py`·`_channel_enqueue.py` | moderate | 채널 화면. 등록·목록 탭과 "새 영상 확인" 탭. 확인한 신규를 표로 보이고, 행을 골라 버튼 하나로 질의 대기열에 넣는다. 대기·실행 중인 영상은 뺀다. 넣기는 버튼 콜백이 한다 |
````

(O2 공유 컴포넌트 줄)

````markdown
| `components/run_progress.py` | simple | 실행 표의 머리글과 한 줄(queued/running/failed/done). 대기 줄은 차례 배지와 취소 버튼. 칸 글자는 순수 함수가 만든다. 완료 시 답변 수만, 상세는 이력 화면으로 |
````

→

````markdown
| `components/run_progress.py` | simple | 실행 표의 머리글과 한 줄(queued/running/failed/done). 대기 줄은 차례 배지와 취소 버튼. 칸 글자는 순수 함수가 만든다. 완료 시 답변 수만, 상세는 이력 화면으로 |
| `components/auto_save_toggle.py` | simple | 자동 저장 체크. 질의·채널 화면이 위젯 key 만 달리해 DB 설정 하나를 함께 쓴다 |
| `components/queue_notice.py` | simple | 넣으면 언제 도는지 알리는 안내 셋과 넣은 뒤의 결과 문구. 질의·채널 화면이 함께 쓴다 |
````

확인:

```bash
grep -c "목록에서 바로 요약을 시작합니다" README.md
grep -c "선택한 영상 요약" README.md
grep -c "components/queue_notice.py" docs/ONBOARDING.md
```

Expected: `0`, `1`, `1`.

```bash
msg="$(mktemp)"
cat > "$msg" <<'EOF'
📝 docs: 채널 화면의 표와 여러 건 넣기를 안내 문서에 반영

README 의 채널 사용법을 표에서 골라 대기열에 넣는 흐름으로
고치고, Outline 설정이 없을 때 채널 화면의 자동 저장 체크도
잠긴다고 적는다. ONBOARDING 의 UI 레이어 표에 채널 화면과 공유
컴포넌트 둘을 더한다.

Assisted-by: <모델 ID>
EOF
git add README.md docs/ONBOARDING.md
git commit -F "$msg"
rm "$msg"
```

- [ ] **Step 2: 채널 감시 설계서를 다시 쓴다**

`docs/superpowers/specs/2026-09-23-channel-watch-design.md` 를 처음부터 끝까지 읽은 뒤, 아래 열일곱 자리만 바꿔 Write 로 통째로 다시 쓴다.

(C1 머리의 대상)

````markdown
  건드리지 않는다. 대기열이 채널 화면의 러너 호출과 가드에 더하는
  것은 `2026-09-30-run-queue-and-auto-save-design.md` 가 다룬다.
````

→

````markdown
  건드리지 않는다. 대기열이 채널 화면의 러너 호출과 가드에 더하는
  것은 `2026-09-30-run-queue-and-auto-save-design.md` 가, 신규 영상
  표와 여러 건 넣기는 `2026-10-01-channel-video-table-design.md` 가
  다룬다.
````

(C2 §1 찾는 일)

````markdown
"아직 요약하지 않은 새 영상" 목록을 받고, 거기서 바로 요약을
시작한다. 지금은 사람이 유튜브를 뒤져 URL 을 복사해 오는 일을 이
화면이 대신한다.
````

→

````markdown
"아직 요약하지 않은 새 영상" 표를 받고, 거기서 고른 영상을 질의
대기열에 넣는다. 지금은 사람이 유튜브를 뒤져 URL 을 복사해 오는 일을
이 화면이 대신한다.
````

(C3 §1.1 여러 건)

````markdown
- **여러 건을 한 번에 돌리지 않는다.** 질의 대기열이 비어 있을 때만
  한 건을 시작하고, 채널 화면에서 대기열에 쌓지 않는다(→ 3.1).
````

→

````markdown
- **대기열을 따로 두지 않는다.** 고른 영상은 질의 화면과 같은
  대기열에 같은 규칙으로 선다(→ 10.3).
````

(C4 §3 실행 결정)

````markdown
| 실행은 **한 건씩, 기존 러너 그대로** | 질의 화면과 같은 `runner.enqueue` 를 `auto_save=False` 로 부르고, 질의 대기열이 비어 있을 때만 시작한다. R1~R5 가 기대는 실행 모델을 건드리지 않는다 |
````

→

````markdown
| 실행은 **질의 화면과 같은 대기열** | 표에서 고른 영상을 목록 순서로 질의 화면과 같은 `runner.enqueue` 에 넣고, 자동 저장도 질의 화면과 같은 설정을 쓴다. 대기·실행 중인 영상만 건너뛴다. R1~R5 가 기대는 실행 모델을 건드리지 않는다(→ 10.3) |
````

(C5 §3.1 여러 건 대기열)

````markdown
- **여러 건 대기열** — 질의 화면의 대기열
  (`2026-09-30-run-queue-and-auto-save-design.md` §8)에 채널 화면의
  요약도 태울 수 있지만, 사람이 한 건씩 시작하는 흐름으로 충분하다.
````

→

````markdown
- **행마다 `[요약]` 버튼** — 한 건씩 넣는 것은 여러 건을 고르는 것의
  특수한 경우다. 두 길을 두면 버튼만 는다
  (`2026-10-01-channel-video-table-design.md` §3.1).
````

(C6 §4 구조 그림)

````markdown
            ├──► services/questions.py      list_questions (읽기만)
            └──► services/runner.py         enqueue (자동 저장 없이)
````

→

````markdown
            ├──► services/questions.py      list_questions (읽기만)
            ├──► components/auto_save_toggle.py  자동 저장 체크 (질의 화면과 공유)
            ├──► components/queue_notice.py      대기열 안내 (질의 화면과 공유)
            ├──► pages/_channel_videos.py   신규 영상 표
            └──► pages/_channel_enqueue.py  넣기 → services/runner.py enqueue
````

(C7 §4 나눈 이유)

````markdown
화면을 두 파일로 나눈 이유는 크기다. 한 파일이 300줄을 넘으면
쪼개는 것이 이 저장소의 규약이고, 등록·목록과 확인·요약은 서로를
부르지 않는 두 덩어리다. `_channel_check` 는 네비게이션에 등록되지
않으므로 이름 앞에 밑줄을 둔다.
````

→

````markdown
화면을 네 파일로 나눈 이유는 크기다. 한 파일이 300줄을 넘으면
쪼개는 것이 이 저장소의 규약이다. 등록·목록과 확인은 서로를 부르지
않는 두 덩어리이고, 확인 탭 안에서 표(`_channel_videos`)와 넣기
(`_channel_enqueue`)를 다시 뗀다. 밑줄로 시작하는 파일은
네비게이션에 등록되지 않는다.
````

(C8 §10 제목)

````markdown
## 10. 화면 — `pages/channels.py` · `pages/_channel_check.py`
````

→

````markdown
## 10. 화면 — `pages/channels.py` · `pages/_channel_*.py`
````

(C9 §10 화면 그림)

````markdown
│                     질문 선택(multiselect) · 신규 목록 · [요약]
````

→

````markdown
│                     질문 선택(multiselect) · 자동 저장 · 신규 표 · [선택한 영상 요약 (n건)]
````

(C10 §10.3 전체)

````markdown
### 10.3 신규 목록과 실행

- 조회 결과는 **세션에만** 둔다. 화면을 떠났다 오면 다시 확인한다.
- 결과에 **채널 id 를 함께 담는다.** 지금 고른 채널의 것이 아니면
  그리지 않는다 — 대상을 바꿨는데 앞 채널의 목록이 남아 있으면
  무엇을 보고 있는지 알 수 없다.
- 질문은 목록 위에서 한 번 고른다. 등록된 질문이 없으면 안내만 내고
  `[요약]` 을 그리지 않는다(정리본 화면과 같은 패턴).
- `[요약]` 은 `runner.enqueue` 를 `auto_save=False` 로 부른다. 질의
  화면과 **같은 입구**다. 자동 저장을 쓰지 않으므로 결과는 이력에
  미저장으로 남는다.
- 다음 넷 중 하나라도 참이면 `[요약]` 이 잠기고 이유가 보인다 —
  질의 실행·대기 중(`active_count() > 0`), 대기열 멈춤
  (`paused_reason()` 이 있음), 정리 실행 중, 질문 미선택. 그래서
  채널 화면은 대기열이 비어 있을 때만 시작한다. 멈춘 대기열을
  잠그는 것은 거기 넣으면 돌지 않고 서 있기 때문이다
  (`2026-09-30-run-queue-and-auto-save-design.md` §8.5).
- 시작한 영상은 그 줄에 "실행 중" 을 적고 그 줄의 버튼만 잠근다.
  실행이 끝나야 `runs` 에 들어가므로 목록에서 즉시 사라지지 않으며,
  이 표시가 같은 영상을 두 번 시작하는 것도 막는다. 세션에 이번에
  시작한 `video_id` 집합을 둔다.
- 진행 상황과 결과는 **실행 현황 화면**에서 본다. 이 화면은 시작만
  한다.
````

→

````markdown
### 10.3 신규 표와 넣기

- 조회 결과는 **세션에만** 둔다. 화면을 떠났다 오면 다시 확인한다.
- 결과에 **채널 id 를 함께 담는다.** 지금 고른 채널의 것이 아니면
  그리지 않는다 — 대상을 바꿨는데 앞 채널의 목록이 남아 있으면
  무엇을 보고 있는지 알 수 없다.
- 질문은 표 위에서 한 번 고르고, 이번에 넣는 영상 모두에 쓴다.
  등록된 질문이 없으면 안내와 표만 그리고 넣기 버튼은 그리지 않는다
  (정리본 화면과 같은 패턴).
- 신규는 **표 하나**로 보인다 — 제목 · 업로드일 · 상태 · 영상 링크.
  행 왼쪽 칸을 체크해 여러 건을 고르고 `[선택한 영상 요약 (n건)]` 으로
  한 번에 질의 대기열에 넣는다. 질의 화면과 **같은 입구**
  (`runner.enqueue`)와 같은 자동 저장 설정을 쓴다.
- 앞선 질의·정리본 작성·멈춘 대기열은 넣기를 막지 않는다. 언제
  도는지는 질의 화면과 같은 안내가 미리 알린다. 한 번에 하나는
  워커가 지킨다.
- 대기 중이거나 실행 중인 영상은 넣지 않고 뺀 수를 알린다. 끝났거나
  실패한 영상은 다시 넣을 수 있다. 표의 상태 칸이 레지스트리에서 그
  영상의 상태를 읽어 보여 준다.
- 넣은 뒤에는 표의 선택을 비운다. 실행이 끝나 `runs` 에 들어간
  영상은 다음 확인에서 목록에서 빠진다.
- 표와 넣기의 자세한 규칙은 `2026-10-01-channel-video-table-design.md`
  가 적는다. 진행 상황과 결과는 **실행 현황 화면**에서 본다.
````

(C11 §11 질문·잠금 줄)

````markdown
| 등록된 질문 없음 | 질문 관리로 안내. `[요약]` 없음 |
| 질의 실행·대기 중, 대기열 멈춤, 정리 실행 중 | `[요약]` 잠금 + 이유 |
````

→

````markdown
| 등록된 질문 없음 | 질문 관리로 안내. 표는 그리고 넣기 버튼은 없음 |
| 질의 실행·대기 중, 대기열 멈춤, 정리 실행 중 | 막지 않는다. 넣고 언제 도는지 안내 |
| 고른 영상이 대기·실행 중 | 그 영상만 빼고 넣는다. 뺀 수를 알린다 |
````

(C12 §12 화면 테스트 줄)

````markdown
| `pages/_channel_check` | 확인 후 신규 목록 · 신규 없음 · **고른 채널만 조회** · **확인이 기준일을 저장** · **대상을 바꾸면 결과가 사라짐** · 피드 실패 사유 · 질문 없음 · 실행 중 잠금 · `[요약]` 이 러너에 URL·질문을 넘김 |
````

→

````markdown
| `pages/_channel_check`·`_channel_videos`·`_channel_enqueue` | 확인 후 신규 표 · 신규 없음 · **고른 채널만 조회** · **확인이 기준일을 저장** · **대상을 바꾸면 결과가 사라짐** · 피드 실패 사유 · 질문 없음 · 고른 영상을 목록 순서로 러너에 넘김 · 대기·실행 중인 영상 건너뜀 · 잠그지 않고 안내 · 자동 저장 설정을 따름 · 넣은 뒤 선택이 빔 |
````

(C13 §12 AppTest 메모 수)

````markdown
`AppTest` 로 확인한 것 셋(실물 확인):
````

→

````markdown
`AppTest` 로 확인한 것 넷(실물 확인):
````

(C14 §12 AppTest 메모 넷째)

````markdown
- `AppTest.from_function` 은 함수 본문만 떼어 돌린다. 그 안에서 쓰는
  것은 **함수 안에서 import** 해야 한다.
````

→

````markdown
- `AppTest.from_function` 은 함수 본문만 떼어 돌린다. 그 안에서 쓰는
  것은 **함수 안에서 import** 해야 한다.
- **표 클릭은 흉내 내지 못한다.** 표의 key 에 선택을 세션 상태로
  넣는다. 선택은 바로 다음 실행 한 번에만 간다.
````

(C15 §13 다른 설계 가리키기)

````markdown
대기열이 채널 화면의 러너 호출과 가드를 바꾸는 파일은
`2026-09-30-run-queue-and-auto-save-design.md` §13 이 적는다.
````

→

````markdown
대기열이 채널 화면의 러너 호출과 가드를 바꾸는 파일은
`2026-09-30-run-queue-and-auto-save-design.md` §13 이, 신규 영상 표와
여러 건 넣기가 더하는 파일은 `2026-10-01-channel-video-table-design.md`
§12 가 적는다.
````

(C16 §15 여러 건 한 번에 요약(지운다))

````markdown
- **여러 건 한 번에 요약** — 채널 화면은 질의 대기열에 쌓지 않고 한
  건씩 시작한다(→ 3.1)
````

→ **지운다**(앞뒤 줄은 그대로).

(C17 §15 자동 저장(지운다))

````markdown
- **신규 영상을 Outline 에 자동 저장** — 채널 화면이 시작한 요약은
  이력에 미저장으로 남고, 사람이 이력 화면에서 제목을 확인해 올린다.
  질의 화면의 자동 저장(`2026-09-30-run-queue-and-auto-save-design.md`
  §7)은 채널 화면에 붙이지 않는다
````

→ **지운다**(앞뒤 줄은 그대로).

확인:

```bash
grep -n -E 'auto_save=False|비어 있을 때만|`\[요약\]`' docs/superpowers/specs/2026-09-23-channel-watch-design.md
grep -c "2026-10-01-channel-video-table-design.md" docs/superpowers/specs/2026-09-23-channel-watch-design.md
```

Expected: 첫 줄은 C5 가 넣은 `- **행마다 \`[요약]\` 버튼** — …` 한 줄만 찍는다. 둘째 줄은 `4`.

```bash
msg="$(mktemp)"
cat > "$msg" <<'EOF'
📝 docs(spec): 채널 확인 설계를 신규 표 기준으로 다시 쓰기

채널 화면이 신규를 표로 보이고 고른 영상을 한 번에 질의 대기열에
넣게 되면서, 대기열이 비어 있을 때만 한 건 시작한다는 결정과
auto_save=False·[요약] 잠금, 여러 건 대기열 기각, 범위 밖의 자동
저장이 틀리게 되었다. 실행 결정·구조 그림·화면 그림·§10.3·엣지·
테스트를 지금 동작에 맞추고, 표와 넣기의 자세한 규칙은
2026-10-01 설계서를 가리킨다.

Assisted-by: <모델 ID>
EOF
git add docs/superpowers/specs/2026-09-23-channel-watch-design.md
git commit -F "$msg"
rm "$msg"
```

- [ ] **Step 3: 대기열 설계서를 바로잡는다**

`docs/superpowers/specs/2026-09-30-run-queue-and-auto-save-design.md` 를 처음부터 끝까지 읽은 뒤, 아래 일곱 자리만 바꿔 Write 로 통째로 다시 쓴다.

(Q1 머리의 범위)

````markdown
  채널 화면의 "요약" 버튼은 새 러너 입구를 쓰지만 동작(비어 있을
  때만 시작, 수동 저장)은 그대로다.
````

→

````markdown
  채널 화면의 신규 영상도 같은 대기열·같은 자동 저장 설정을 쓴다.
  그 화면의 표와 여러 건 넣기는
  `2026-10-01-channel-video-table-design.md` 가 적는다.
````

(Q2 §3.1 채널 화면 기각(지운다))

````markdown
- **채널 화면의 "요약" 도 대기열·자동 저장에 태우기** — 이번 범위가
  아니다. 뒤에 붙일 수 있도록 러너 입구를 하나로 둔다(→ 6.1).
````

→ **지운다**(앞뒤 줄은 그대로).

(Q3 §6.3 채널 화면의 자동 저장)

````markdown
- 질의 화면과 채널 화면이 모두 `enqueue` 를 부른다. 채널 화면은
  `auto_save=False` 를 넘긴다.
````

→

````markdown
- 질의 화면과 채널 화면이 모두 `enqueue` 를 부른다. 두 화면 모두
  자동 저장 체크의 값을 넘긴다. 설정은 하나다.
````

(Q4 §8.5 가드 표의 채널 줄)

````markdown
| `pages/_channel_check.py` | `active_count() > 0` 이거나 `paused_reason()` 이 있으면 "요약" 을 잠근다. 멈춘 대기열에 넣으면 돌지 않고 서 있기 때문이다 |
````

→

````markdown
| `pages/_channel_enqueue.py` | 질의 화면처럼 **막지 않는다.** 고른 영상 가운데 대기·실행 중인 것(`is_pending`)만 뺀다(`2026-10-01-channel-video-table-design.md` §8.2) |
````

(Q5 §8.5 채널 화면 멈춤 안내)

````markdown
잠글 때의 안내 문구는 "실행 중" 을 "실행 중이거나 대기 중" 으로 바꾼다.
채널 화면의 멈춤 안내는 `대기열이 멈춰 있습니다. 실행 현황에서
재개하거나 대기 항목을 취소한 뒤 시작하세요.` 다.
````

→

````markdown
잠글 때의 안내 문구는 "실행 중" 을 "실행 중이거나 대기 중" 으로 바꾼다.
````

(Q6 §13 channel-watch 줄)

````markdown
  "대기열을 만들지 않는다" 가 틀리게 된다. 채널 화면이 대기열·자동
  저장을 쓰지 않는다는 사실은 그대로 적는다.
````

→

````markdown
  "대기열을 만들지 않는다" 가 틀리게 된다.
````

(Q7 §15 채널 화면(지운다))

````markdown
- **채널 화면의 대기열·자동 저장** — 나중에 붙인다. 러너 입구
  `enqueue` 가 이미 `auto_save` 를 받는다.
````

→ **지운다**(앞뒤 줄은 그대로).

확인:

```bash
grep -c -E 'auto_save=False|비어 있을 때만' docs/superpowers/specs/2026-09-30-run-queue-and-auto-save-design.md
grep -c "2026-10-01-channel-video-table-design.md" docs/superpowers/specs/2026-09-30-run-queue-and-auto-save-design.md
```

Expected: `0`, `2`.

```bash
msg="$(mktemp)"
cat > "$msg" <<'EOF'
📝 docs(spec): 대기열 설계의 채널 화면 문장 바로잡기

채널 화면도 같은 대기열과 같은 자동 저장 설정을 쓰게 되어, 채널
화면은 비어 있을 때만 시작하고 수동 저장한다는 범위, 채널 화면을
대기열에 태우지 않는다는 기각과 범위 밖, auto_save=False, 채널
화면의 잠금 가드와 멈춤 안내가 틀리게 되었다. 지금 동작에 맞추고
채널 화면의 규칙은 2026-10-01 설계서를 가리킨다. §2.1 의 가드 표는
대기열을 설계할 때 조사한 사실이라 그대로 둔다.

Assisted-by: <모델 ID>
EOF
git add docs/superpowers/specs/2026-09-30-run-queue-and-auto-save-design.md
git commit -F "$msg"
rm "$msg"
```

---

### Task 6: 전체 검증과 브라우저 확인

**Files:** `docs/superpowers/specs/2026-10-01-channel-video-table-design.md`(상태 한 줄). 그 밖에는 세션 스크래치 폴더의 임시 스크립트만. 아래에서 `$SCR` 는 그 폴더다.

- [ ] **Step 1: 네 검사를 돌린다**

Task 4 Step 7 의 명령. Expected: 포맷 변경 없음, `All checks passed!`, `Success: no issues found`, `837 passed, 1 skipped`(기준 820 + 이 계획이 더한 23 − 지운 6). 줄 수는 190·164·145·119·74·84. 수가 다르면 어느 Task 의 테스트가 빠지거나 늘었는지 확인해 보고한다. 실패가 있으면 완료라고 말하지 말고 출력을 그대로 보고한다.

- [ ] **Step 2: 가짜 피드·가짜 파이프라인으로 앱을 띄운다**

실제 YouTube·NotebookLM 을 부르지 않도록 채널 해석·피드·러너 입구를 가짜로 감싸고 앱 진입점을 그대로 실행하는 스크립트를 스크래치 폴더에 만든다. 저장소 안에 만들지 않는다.

`$SCR/channel_demo.py`:

```python
"""채널 표 확인용 진입점. 가짜 피드·가짜 파이프라인으로 앱을 그린다.

등록은 어떤 URL 이든 고정된 채널 하나로 해석한다. 피드는 지금부터
한 시간 간격으로 거슬러 올라간 영상 넷을 준다. 실행 하나는
``DEMO_SECONDS``(기본 20초) 걸린다. 실제 NotebookLM·YouTube 를 부르지
않는다.
"""

import asyncio
import datetime
import os
import pathlib
import runpy

from notebooklm_st.core import models
from notebooklm_st.services import (
    channel_feed,
    channel_lookup,
    runner,
    video_metadata,
)

APP = pathlib.Path(os.environ["DEMO_APP"])
SECONDS = float(os.environ.get("DEMO_SECONDS", "20"))
CHANNEL_ID = "UC" + "d" * 22


async def fake_pipeline(url, questions, on_progress, **kwargs):
    """진행 문구를 남기며 기다렸다가 답변 하나를 돌려준다."""
    video_id = url[-11:]
    for step in ("자막 인덱싱 중", "질문 1/1"):
        on_progress(step)
        await asyncio.sleep(SECONDS / 2)
    item = models.AnswerItem(
        question_title=questions[0].title,
        question_text=questions[0].text,
        answer="답이다.",
        citations=(),
        error=None,
    )
    return models.RunResult(
        url=url, video_id=video_id, title=f"영상 {video_id}", items=(item,)
    )


def fake_lookup(url, **kwargs):
    """어떤 URL 이든 데모 채널로 해석한다."""
    return channel_lookup.LookupResult(
        channel_id=CHANNEL_ID,
        title="데모 채널",
        url=f"https://www.youtube.com/channel/{CHANNEL_ID}",
        error=None,
    )


def fake_fetch(channel_id, **kwargs):
    """지금부터 한 시간씩 거슬러 올라간 영상 넷을 준다."""
    now = datetime.datetime.now(datetime.UTC)
    entries = tuple(
        models.FeedEntry(
            video_id=f"demo{number:07d}",
            title=f"데모 영상 {number} [제목에 대괄호]",
            published=now - datetime.timedelta(hours=number),
        )
        for number in range(1, 5)
    )
    return channel_feed.FeedResult(entries, None)


if not getattr(runner, "_demo_patched", False):
    real_enqueue, real_resume = runner.enqueue, runner.resume

    def enqueue(
        registry, url, questions, db_path, auto_save, is_blocked, pipeline=None
    ):
        """가짜 파이프라인으로 넣는다."""
        return real_enqueue(
            registry,
            url,
            questions,
            db_path,
            auto_save,
            is_blocked,
            fake_pipeline,
        )

    def resume(registry, db_path, is_blocked, pipeline=None):
        """가짜 파이프라인으로 재개한다."""
        real_resume(registry, db_path, is_blocked, fake_pipeline)

    runner.enqueue, runner.resume = enqueue, resume
    channel_lookup.lookup = fake_lookup
    channel_feed.fetch = fake_fetch
    video_metadata.fetch = lambda url, **kwargs: video_metadata.MetadataResult(
        models.VideoMetadata(channel=None, upload_date=None), None
    )
    runner._demo_patched = True

runpy.run_path(str(APP), run_name="__main__")
```

저장소 루트에서 백그라운드로 띄운다. Outline 설정은 넣지 않는다(자동 저장 체크는 잠긴다). 실행 하나를 60초로 두어 확인할 틈을 넉넉히 둔다.

```bash
mkdir -p "$SCR/nlm-home"
DEMO_APP="$PWD/src/notebooklm_st/app.py" DEMO_SECONDS=60 \
NOTEBOOKLM_ST_DB="$SCR/channel_demo.db" NOTEBOOKLM_HOME="$SCR/nlm-home" \
.venv/Scripts/python.exe -m streamlit run "$SCR/channel_demo.py" \
  --server.port 8699 --server.headless true                 # 백그라운드
```

`NOTEBOOKLM_HOME` 은 빈 폴더다. 실제 자격증명을 건드리지 않으려는 것이고, 화면 위의 인증 오류 배너는 그래서 뜨는 것이다.

- [ ] **Step 3: 브라우저로 표와 넣기를 확인한다**

- 창 크기를 1920×950 으로 맞춘다. **루트(`http://127.0.0.1:8699/`)를 연 뒤 사이드바로 옮긴다.**
- 표는 캔버스라 접근성 트리에 행이 없다. 행 왼쪽 체크 칸은 표(`[data-testid="stDataFrame"]`)의 위치에서 머리글 한 줄(약 35px) 아래로 줄마다 약 35px 씩 내려가며 x 는 표 왼쪽에서 약 17px 이다. 예행에서 이 좌표 클릭으로 골랐다.

1. "질문 관리" 에서 질문을 하나 등록한다.
2. "채널" → **채널 등록** 탭에서 아무 채널 URL(예: `https://www.youtube.com/@demo`)을 넣고 **등록** → "데모 채널" 이 등록된다.
3. **새 영상 확인** 탭에서 **새 영상 확인** → 질문 선택, 꺼진 채 잠긴 `자동 저장` 체크와 그 캡션, 소제목 "데모 채널", 캡션 `행 왼쪽 칸을 눌러 고릅니다.`, 넷 줄 표(제목 `데모 영상 1 [제목에 대괄호]`…, 대괄호가 글자 그대로 보인다), `질문을 하나 이상 고르세요.`, 잠긴 `선택한 영상 요약 (0건)` 이 보인다.
4. 질문을 고른다 → 안내가 사라지고 버튼은 여전히 `(0건)` 으로 잠겨 있다.
5. **업로드일** 머리글을 눌러 오래된 것이 위로 오게 정렬한다(맨 위가 영상 4). 맨 위 줄(영상 4)과 맨 아래 줄(영상 1)을 체크 → 버튼이 `(2건)`.
6. 버튼을 누른다 → `2건을 넣고 첫 영상부터 시작했습니다. 실행 현황 화면에서 확인하세요.` 가 보이고 버튼이 `(0건)`, 체크가 모두 풀린다. 상태 칸은 영상 1 `실행 중`, 영상 4 `대기 중` — **정렬해 고른 순서가 아니라 목록 순서로 들어갔다.**
7. 60초 안에 영상 1(실행 중)과 영상 2 를 체크해 누른다 → `대기열에 넣었습니다 — 앞에 2건. 실행 현황 화면에서 확인하세요. 이미 대기 중이거나 실행 중인 1건은 뺐습니다.`
8. 영상 3 을 체크해 둔 채, 영상 1 이 끝날 때(6번에서 60초)까지 기다린 뒤 페이지 빈 곳을 누르고 `R` 키로 다시 실행한다 → 영상 1 상태가 `끝남` 으로 바뀌고 **영상 3 의 체크는 남아 있다**(버튼 `(1건)`). 체크가 풀리면 Review Focus 4번이 깨진 것이니 보고한다.
9. "실행 현황" 으로 간다 → 영상 1 `완료`, 영상 4 가 실행 중이거나 `대기 1`, 영상 2 가 그 뒤에 선다.
10. 스크린샷을 찍어 눈으로 본다.

기대와 다르면 스크린샷과 함께 보고한다.

- [ ] **Step 4: 치운다**

- 스트림릿 백그라운드 작업을 멈춘다.
- 브라우저 도구가 저장소 루트에 만든 `.playwright-mcp/` 와 스크린샷이 있으면 스크래치 폴더로 옮긴다.
- `git status --short` 가 비어 있어야 한다.

- [ ] **Step 5: 설계서 상태를 구현 완료로 바꾼다**

`docs/superpowers/specs/2026-10-01-channel-video-table-design.md` 의 머리에서:

````markdown
- **상태**: 구현 계획 수립 (계획:
  `docs/superpowers/plans/2026-10-01-channel-video-table.md`)
````

→ (`YYYY-MM-DD` 는 이 Step 을 하는 날. `date +%F` 로 얻는다)

````markdown
- **상태**: 구현 완료 (YYYY-MM-DD, 계획:
  `docs/superpowers/plans/2026-10-01-channel-video-table.md`)
````

```bash
msg="$(mktemp)"
cat > "$msg" <<'EOF'
📝 docs(spec): 채널 표 설계를 구현 완료로 표시

구현 계획의 Task 1~5 를 마치고 네 검사와 가짜 피드·가짜
파이프라인 브라우저 확인(정렬 뒤 선택, 목록 순서 넣기, 대기 중
영상 빼기, 상태가 바뀌어도 선택 유지)을 통과했다.

Assisted-by: <모델 ID>
EOF
git add docs/superpowers/specs/2026-10-01-channel-video-table-design.md
git commit -F "$msg"
rm "$msg"
```

- [ ] **Step 6: 사람에게 넘길 확인 항목을 보고에 적는다**

실제 YouTube 피드와 NotebookLM·Outline 으로 하는 확인은 자격증명이 필요해 사람이 한다. 보고 끝에 아래를 그대로 적는다.

- 실제 채널에서 **새 영상 확인** → 표에서 두 건을 골라 넣는다 → 실행 현황에서 하나씩 차례로 돌고 모두 `완료` 가 되는지 본다.
- Outline 설정을 넣고 채널 화면의 **자동 저장**을 켠 채 두 건을 넣는다 → 두 건 모두 저장 칸이 `저장됨` 링크가 되고, 질의 화면을 열면 그 체크도 켜져 있다(설정 하나).
- 넣은 뒤 다시 **새 영상 확인** → 끝나 이력에 남은 영상은 표에서 빠진다.
