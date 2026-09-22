# Outline 저장 (R4) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 요약본의 집을 로컬 SQLite 에서 Outline 위키로 옮긴다. 사람이
제목을 확인하고 버튼을 눌러 문서를 만들며, 성공하면 로컬 본문을 지우고
문서명·URL 만 남긴다.

**Architecture:** `services/outline.py` 가 `documents.create` 를 한 번
부르는 얇은 HTTP 클라이언트로 새로 생긴다. `services/run_history.py` 는
Outline 을 모른 채 문자열 셋(문서 ID·제목·URL)을 받아 기록하고 본문을
지운다. 둘을 잇는 것은 `pages/history.py` 이고, 화면이 아는 것은
"만들고 → 기록한다" 는 순서뿐이다. 러너와 질의 파이프라인은 건드리지
않는다 — 실행 결과는 지금처럼 SQLite 에 먼저 도착한다.

**Tech Stack:** Python 3.13, Streamlit, SQLite(`sqlite3`), httpx, pytest,
`streamlit.testing.v1.AppTest`, ruff, mypy, uv.

**Spec:** `docs/superpowers/specs/2026-09-22-outline-storage-design.md`

## Global Constraints

- **작업 브랜치는 `develop`.** `master` 에 직접 커밋하지 않는다.
  `git push` 는 사람이 한다 — **에이전트는 실행하지 않는다.**
- **커밋 메시지**: `<emoji> <type>(<scope>): <한국어 제목>`. 제목은
  명령형·마침표 없음·50자 이내. 마지막 줄에 `Assisted-by: <자기 모델 ID>`
  를 붙인다. `Co-Authored-By:` 는 쓰지 않는다.
- **명령은 `uv` 로 돈다.** `uv` 가 PATH 에 없으면 `~/.local/bin/uv` 를
  전체 경로로 부른다. **검증은 CI 가 돌리는 네 명령과 같아야 한다**
  (`.github/workflows/`):

  ```bash
  uv run ruff format --check .
  uv run ruff check .
  uv run mypy src tests      # src 만이 아니다 — 테스트도 타입 검사한다
  uv run pytest
  ```
- **ruff**: `line-length = 80`, `select = ["E","W","F","I","N","D","UP","B","SIM","ANN","RUF"]`,
  docstring 은 **google convention**. `src/` 의 `core.*`·`services.*` 는
  mypy `disallow_untyped_defs = true` — **모든 함수에 타입 힌트와
  docstring 이 필요하다.** 테스트는 `ANN` 이 면제된다.
- **주석과 docstring 은 한국어**로 쓴다. 기존 파일의 밀도와 어투를
  따른다 — "무엇을·왜" 를 적고 "어떻게" 는 코드가 말하게 한다.
- **기준선**: 이 계획을 시작하는 시점에 `uv run pytest` 는 **268개
  통과**한다. 각 태스크는 그 수를 늘리거나(추가) 줄이는(삭제) 이유를
  본문에 적어 둔다. 끝났을 때 전부 통과해야 한다.
- **깨진 상태를 커밋하지 않는다.** 태스크 하나가 끝날 때마다 전체
  테스트가 통과해야 한다.
- 이 프로젝트는 **DB 마이그레이션을 지원하지 않는다.** 스키마가 바뀌면
  `StaleSchemaError` 로 거부하고 사용자가 파일을 지운다. 마이그레이션
  코드를 쓰지 않는다.

## 파일 구조

| 파일 | 책임 | 태스크 |
|---|---|---|
| `src/notebooklm_st/services/outline.py` (신규) | Outline 만 안다. 설정 읽기 + `documents.create` 한 번 | 1·2·3 |
| `src/notebooklm_st/core/models.py` | `RunSummary` 에 저장 상태 네 칸 | 4 |
| `src/notebooklm_st/services/store.py` | `runs` 스키마 네 칸 + 스키마 가드 | 4 |
| `src/notebooklm_st/services/run_history.py` | `list_runs` 확장, `mark_exported` 추가, `update_answer` 삭제 | 5·6·7 |
| `src/notebooklm_st/components/answer_view.py` | 읽기 전용 컴포넌트가 된다 | 7 |
| `src/notebooklm_st/core/markdown_export.py` | 확인한 제목을 받고 H1 을 뺀다. `to_filename` 삭제 | 8 |
| `src/notebooklm_st/pages/history.py` | 두 상태(미저장·저장됨)를 그리고 저장을 잇는다 | 7·8·9·10·11 |
| `pyproject.toml` | `httpx` 직접 의존 | 1 |
| `docker-compose.yml` | 환경변수 셋 주입 | 12 |
| 문서 넷 | README · how-to · R1 스펙 §7.3 | 12 |

---

## Task 1: `services/outline.py` — 설정 읽기

**Files:**
- Create: `src/notebooklm_st/services/outline.py`
- Create: `tests/services/test_outline.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces:
  - `outline.URL_ENV_VAR: str` = `"NOTEBOOKLM_ST_OUTLINE_URL"`
  - `outline.TOKEN_ENV_VAR: str` = `"NOTEBOOKLM_ST_OUTLINE_TOKEN"`
  - `outline.COLLECTION_ENV_VAR: str` = `"NOTEBOOKLM_ST_OUTLINE_COLLECTION"`
  - `outline.OutlineConfig` — frozen dataclass, 필드 `base_url: str`,
    `token: str`, `collection_id: str`
  - `outline.config_from_env() -> OutlineConfig | None`

`httpx` 를 이 태스크에서 함께 선언한다. 모듈이 태어나는 자리이고,
Task 2 가 바로 `import httpx` 를 한다. 의존성만 따로 커밋하면 아무것도
검증하지 못하는 커밋이 하나 생긴다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_outline.py` 를 새로 만든다.

```python
"""Outline 클라이언트 테스트."""

from notebooklm_st.services import outline

BASE_URL = "http://192.168.0.10:3000"
TOKEN = "ol_api_secret_value"
COLLECTION = "0f2c1a4e-0000-4000-8000-000000000001"


def set_env(monkeypatch, base_url=BASE_URL, token=TOKEN, collection=COLLECTION):
    """환경변수 셋을 채운다. 빈 문자열을 주면 그 변수는 지운다."""
    for name, value in (
        (outline.URL_ENV_VAR, base_url),
        (outline.TOKEN_ENV_VAR, token),
        (outline.COLLECTION_ENV_VAR, collection),
    ):
        if value:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)


def test_config_reads_all_three_variables(monkeypatch) -> None:
    """셋이 다 있으면 설정을 만든다."""
    set_env(monkeypatch)

    config = outline.config_from_env()

    assert config is not None
    assert config.base_url == BASE_URL
    assert config.token == TOKEN
    assert config.collection_id == COLLECTION


def test_config_is_none_without_any_variable(monkeypatch) -> None:
    """하나도 없으면 설정이 아니다."""
    set_env(monkeypatch, base_url="", token="", collection="")

    assert outline.config_from_env() is None


def test_config_is_none_when_only_the_token_is_missing(monkeypatch) -> None:
    """부분 설정은 설정이 아니다. 401 을 맞기 전에 막는다."""
    set_env(monkeypatch, token="")

    assert outline.config_from_env() is None


def test_config_is_none_for_a_blank_value(monkeypatch) -> None:
    """공백만 든 값은 비어 있는 것으로 본다."""
    set_env(monkeypatch, collection="   ")

    assert outline.config_from_env() is None


def test_config_drops_the_trailing_slash(monkeypatch) -> None:
    """끝 슬래시를 여기서 한 번 뗀다. 호출 지점마다 따지지 않는다."""
    set_env(monkeypatch, base_url="http://192.168.0.10:3000/")

    config = outline.config_from_env()

    assert config is not None
    assert config.base_url == "http://192.168.0.10:3000"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/services/test_outline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.services.outline'`

- [ ] **Step 3: 모듈을 만든다**

`src/notebooklm_st/services/outline.py`:

```python
"""Outline(개인 위키)에 요약본 문서를 만든다.

Outline 을 아는 유일한 모듈이다. SQLite 도 Streamlit 도 모른다.
앱은 Outline 을 읽지 않는다 — 문서를 만들고 그 링크를 돌려주는 것이
이 모듈의 전부다.
"""

import dataclasses
import os

URL_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_URL"
TOKEN_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_TOKEN"
COLLECTION_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_COLLECTION"


@dataclasses.dataclass(frozen=True, slots=True)
class OutlineConfig:
    """Outline 에 붙는 데 필요한 값 셋."""

    base_url: str
    token: str
    collection_id: str


def config_from_env() -> OutlineConfig | None:
    """환경변수에서 설정을 읽는다.

    셋 다 있을 때만 설정으로 친다. 토큰만 빠진 채로 호출해 401 을
    맞는 것보다, 처음부터 못 한다고 말하는 편이 진단하기 쉽다.

    Returns:
        설정. 하나라도 비어 있으면 ``None``.
    """
    base_url = os.environ.get(URL_ENV_VAR, "").strip()
    token = os.environ.get(TOKEN_ENV_VAR, "").strip()
    collection_id = os.environ.get(COLLECTION_ENV_VAR, "").strip()
    if not (base_url and token and collection_id):
        return None
    # 끝 슬래시는 여기서 한 번 뗀다. 붙이고 떼는 일이 호출 지점마다
    # 흩어지면 //api/... 같은 URL 이 언젠가 나온다.
    return OutlineConfig(
        base_url=base_url.rstrip("/"),
        token=token,
        collection_id=collection_id,
    )
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/services/test_outline.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: `httpx` 를 직접 의존으로 선언한다**

`pyproject.toml` 의 `[project].dependencies` 를 알파벳 순서를 지켜 고친다.

```toml
dependencies = [
    "httpx>=0.28",
    "notebooklm-py==0.8.1",
    "streamlit>=1.63.0",
    "yt-dlp>=2026.8.19",
]
```

`notebooklm-py` 가 이미 끌고 와 `uv.lock` 에 `0.28.1` 로 잠겨 있지만,
전이 의존을 코드가 직접 쓰는 것은 다른 얘기다 — 다음 버전에서 갈아타면
조용히 깨진다. 상한은 걸지 않는다.

- [ ] **Step 6: 락을 갱신하고 전체 테스트를 돌린다**

Run: `uv sync`
Expected: 새 패키지를 내려받지 않는다(이미 잠겨 있다). `uv.lock` 의
`notebooklm-st` 항목에 `httpx` 가 더해진다.

Run: `uv run pytest -q`
Expected: **273 passed** (268 + 5)

- [ ] **Step 7: 린트와 타입을 확인한다**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 전부 통과.

- [ ] **Step 8: 커밋**

```bash
git add src/notebooklm_st/services/outline.py tests/services/test_outline.py pyproject.toml uv.lock
git commit -m "$(cat <<'MSG'
✨ feat(outline): 환경변수에서 연결 설정 읽기

Outline 주소·토큰·컬렉션 ID 를 읽는다.
셋 다 있을 때만 설정으로 친다 — 부분 설정을
설정으로 치면 401 을 맞고 나서야 원인을
알게 된다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

## Task 2: `services/outline.py` — 문서 만들기 (성공 경로)

**Files:**
- Modify: `src/notebooklm_st/services/outline.py`
- Modify: `tests/services/test_outline.py`

**Interfaces:**
- Consumes: `outline.OutlineConfig` (Task 1)
- Produces:
  - `outline.SavedDocument` — frozen dataclass, 필드 `id: str`,
    `title: str`, `url: str`(절대 URL)
  - `outline.OutlineError(RuntimeError)`
  - `outline.CREATE_TIMEOUT: float` = `20.0`
  - `outline.PostLike = Callable[..., httpx.Response]`
  - `outline.create_document(config, title, markdown, timeout=CREATE_TIMEOUT, poster=httpx.post) -> SavedDocument`

`poster` 는 `video_metadata.fetch(runner=subprocess.run)` 와 같은 주입
구멍이다. 테스트가 가짜를 넣어 네트워크를 타지 않는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

먼저 `tests/services/test_outline.py` 맨 위의 import 를 늘린다. 파일
중간에 두면 ruff `E402` 에 걸린다.

```python
import httpx
import pytest

from notebooklm_st.services import outline
```

그다음 파일 맨 아래에 붙인다.

```python
def make_config() -> outline.OutlineConfig:
    """테스트용 설정."""
    return outline.OutlineConfig(
        base_url=BASE_URL, token=TOKEN, collection_id=COLLECTION
    )


def fake_poster(response, calls):
    """호출 인자를 기록하고 준비된 응답을 돌려주는 poster 를 만든다."""

    def post(url, **kwargs):
        """httpx.post 를 대신한다."""
        calls.append((url, kwargs))
        if isinstance(response, Exception):
            raise response
        return response

    return post


def made(url="/doc/ai-agents-abc123", doc_id="doc-1", title="AI 에이전트의 미래"):
    """documents.create 가 돌려주는 200 응답을 만든다."""
    return httpx.Response(
        200,
        json={"data": {"id": doc_id, "title": title, "url": url}},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.create"),
    )


def test_create_document_posts_to_the_create_endpoint() -> None:
    """주소·헤더·본문이 API 계약대로 나간다."""
    calls: list[tuple[str, dict[str, object]]] = []

    outline.create_document(
        make_config(),
        "AI 에이전트의 미래",
        "# 본문",
        poster=fake_poster(made(), calls),
    )

    url, kwargs = calls[0]
    assert url == f"{BASE_URL}/api/documents.create"
    assert kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert kwargs["json"] == {
        "title": "AI 에이전트의 미래",
        "text": "# 본문",
        "collectionId": COLLECTION,
        "publish": True,
    }
    assert kwargs["timeout"] == outline.CREATE_TIMEOUT


def test_create_document_returns_the_saved_document() -> None:
    """응답에서 ID·제목·URL 을 꺼낸다."""
    document = outline.create_document(
        make_config(),
        "AI 에이전트의 미래",
        "# 본문",
        poster=fake_poster(made(), []),
    )

    assert document.id == "doc-1"
    assert document.title == "AI 에이전트의 미래"
    assert document.url == f"{BASE_URL}/doc/ai-agents-abc123"


def test_create_document_keeps_an_absolute_url_as_is() -> None:
    """절대 URL 로 오는 배포판도 받는다(스펙 13.1)."""
    document = outline.create_document(
        make_config(),
        "제목",
        "# 본문",
        poster=fake_poster(made(url="https://wiki.example.com/doc/x"), []),
    )

    assert document.url == "https://wiki.example.com/doc/x"


def test_create_document_rejects_a_response_without_data() -> None:
    """기대한 모양이 아니면 OutlineError 다."""
    response = httpx.Response(
        200,
        json={"ok": True},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.create"),
    )

    with pytest.raises(outline.OutlineError) as excinfo:
        outline.create_document(
            make_config(), "제목", "# 본문", poster=fake_poster(response, [])
        )

    assert "이해하지 못했습니다" in str(excinfo.value)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/services/test_outline.py -v`
Expected: FAIL — `AttributeError: module 'notebooklm_st.services.outline' has no attribute 'create_document'`

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/services/outline.py` 의 import 와 상수를 늘리고 함수를
더한다.

```python
import dataclasses
import os
from collections.abc import Callable

import httpx

URL_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_URL"
TOKEN_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_TOKEN"
COLLECTION_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_COLLECTION"

CREATE_TIMEOUT = 20.0
"""문서 생성 요청에 주는 최대 초.

홈 LAN 안의 호출이라 넉넉하다. ``video_metadata`` 와 같은 값을 쓴다.
"""

_CREATE_PATH = "/api/documents.create"

PostLike = Callable[..., httpx.Response]
"""``httpx.post`` 자리에 넣을 수 있는 것.

키워드 인자가 많아 Protocol 로 적으면 길기만 하다.
"""
```

`OutlineConfig` 아래에 이어서.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class SavedDocument:
    """Outline 에 만들어진 문서."""

    id: str
    title: str
    url: str
    """사람이 브라우저에 붙여 넣을 수 있는 절대 URL."""


class OutlineError(RuntimeError):
    """Outline 에 문서를 만들지 못했다.

    메시지는 사람이 화면에서 읽는 문장이다. 토큰은 절대 담지 않는다.
    """


def create_document(
    config: OutlineConfig,
    title: str,
    markdown: str,
    timeout: float = CREATE_TIMEOUT,
    poster: PostLike = httpx.post,
) -> SavedDocument:
    """컬렉션에 문서를 하나 만든다.

    ``publish`` 를 켠다. 끄면 초안으로 남아 컬렉션에서 보이지 않는다.

    Args:
        config: 주소·토큰·컬렉션 ID.
        title: 문서 제목. 사람이 저장 직전에 확인한 값이다.
        markdown: 문서 본문.
        timeout: 요청에 주는 최대 초.
        poster: 요청을 보내는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.

    Returns:
        만들어진 문서의 ID·제목·절대 URL.

    Raises:
        OutlineError: 연결이 안 되거나, 거부당했거나, 응답이 기대한
            모양이 아닌 경우.
    """
    response = poster(
        f"{config.base_url}{_CREATE_PATH}",
        headers={"Authorization": f"Bearer {config.token}"},
        json={
            "title": title,
            "text": markdown,
            "collectionId": config.collection_id,
            "publish": True,
        },
        timeout=timeout,
    )
    return _parse(config, response)


def _parse(config: OutlineConfig, response: httpx.Response) -> SavedDocument:
    """응답 본문에서 문서를 꺼낸다.

    Args:
        config: 상대 URL 앞에 붙일 주소를 가진 설정.
        response: ``documents.create`` 의 응답.

    Returns:
        만들어진 문서.

    Raises:
        OutlineError: JSON 이 아니거나 기대한 키가 없는 경우.
    """
    try:
        data = response.json()["data"]
        document_id = str(data["id"])
        title = str(data["title"])
        url = str(data["url"])
    except (ValueError, KeyError, TypeError) as error:
        raise OutlineError("Outline 의 응답을 이해하지 못했습니다.") from error
    return SavedDocument(
        id=document_id, title=title, url=_absolute(config.base_url, url)
    )


def _absolute(base_url: str, url: str) -> str:
    """응답의 문서 URL 을 절대 URL 로 만든다.

    ``/doc/제목-슬러그`` 같은 상대 경로로 오는 것을 전제하되, 절대
    URL 로 오는 배포판도 그대로 받는다(스펙 13.1).
    """
    if url.startswith(("http://", "https://")):
        return url
    return f"{base_url}/{url.lstrip('/')}"
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/services/test_outline.py -v`
Expected: PASS — 9 passed

- [ ] **Step 5: 전체 테스트·린트·타입**

Run: `uv run pytest -q`
Expected: **277 passed**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/outline.py tests/services/test_outline.py
git commit -m "$(cat <<'MSG'
✨ feat(outline): 컬렉션에 문서 만들기

documents.create 를 한 번 부르고 문서 ID·
제목·절대 URL 을 돌려준다. 응답의 문서 URL 이
상대 경로로 오므로 주소를 앞에 붙이되, 절대
URL 로 오는 배포판도 그대로 받는다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

## Task 3: `services/outline.py` — 실패를 사람이 읽을 문장으로

**Files:**
- Modify: `src/notebooklm_st/services/outline.py`
- Modify: `tests/services/test_outline.py`

**Interfaces:**
- Consumes: `outline.create_document` (Task 2)
- Produces: 시그니처 변화 없음. `create_document` 가 4xx·5xx·연결 실패에
  `OutlineError` 를 던진다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_outline.py` 맨 아래에 붙인다.

```python
def failed(status: int):
    """오류 상태 코드의 응답을 만든다."""
    return httpx.Response(
        status,
        json={"message": "nope"},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.create"),
    )


def create_with(response) -> str:
    """준비된 응답(또는 예외)으로 저장을 시도하고 오류 문구를 돌려준다."""
    with pytest.raises(outline.OutlineError) as excinfo:
        outline.create_document(
            make_config(), "제목", "# 본문", poster=fake_poster(response, [])
        )
    return str(excinfo.value)


def test_rejected_token_says_so() -> None:
    """401 은 토큰 문제다."""
    assert "토큰" in create_with(failed(401))


def test_forbidden_is_also_a_token_problem() -> None:
    """403 도 같은 안내로 묶는다. scope 가 좁아도 여기로 온다."""
    assert "토큰" in create_with(failed(403))


def test_missing_collection_says_so() -> None:
    """404 는 컬렉션 ID 나 주소 문제다."""
    message = create_with(failed(404))
    assert "컬렉션" in message


def test_server_error_carries_the_status_code() -> None:
    """5xx 는 상태 코드를 그대로 보여 준다."""
    assert "503" in create_with(failed(503))


def test_timeout_reads_as_a_connection_failure() -> None:
    """응답이 없으면 연결 실패로 묶는다."""
    assert "연결하지 못했습니다" in create_with(
        httpx.TimeoutException("timed out")
    )


def test_connection_error_reads_as_a_connection_failure() -> None:
    """붙지 못한 경우도 같은 문장이다."""
    assert "연결하지 못했습니다" in create_with(
        httpx.ConnectError("refused")
    )


def test_the_token_never_appears_in_an_error_message() -> None:
    """어떤 실패 경로에서도 토큰이 새지 않는다."""
    for response in (
        failed(401),
        failed(500),
        httpx.TimeoutException("timed out"),
    ):
        assert TOKEN not in create_with(response)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/services/test_outline.py -v -k "token or collection or server_error or timeout or connection"`
Expected: FAIL — 오류 상태 응답이 `OutlineError` 대신 `_parse` 의
"이해하지 못했습니다" 로 가거나, 예외가 `httpx` 그대로 샌다.

- [ ] **Step 3: 구현한다**

`create_document` 의 호출부를 감싸고 상태 코드를 본다.

```python
    try:
        response = poster(
            f"{config.base_url}{_CREATE_PATH}",
            headers={"Authorization": f"Bearer {config.token}"},
            json={
                "title": title,
                "text": markdown,
                "collectionId": config.collection_id,
                "publish": True,
            },
            timeout=timeout,
        )
    except httpx.HTTPError as error:
        # httpx 의 원문 예외를 그대로 흘리지 않는다. 요청 정보가 따라
        # 나올 수 있고, 무엇보다 사람이 읽고 고칠 수 있는 문장이 아니다.
        raise OutlineError(
            "Outline 에 연결하지 못했습니다"
            f"({type(error).__name__})."
        ) from error
    if response.status_code >= 400:
        raise OutlineError(_status_message(response.status_code))
    return _parse(config, response)
```

`_absolute` 아래에 더한다.

```python
def _status_message(status: int) -> str:
    """오류 상태 코드를 사람이 읽고 고칠 수 있는 문장으로 옮긴다.

    Args:
        status: HTTP 상태 코드.

    Returns:
        화면에 그대로 나갈 한국어 문장.
    """
    if status in (401, 403):
        return (
            "Outline 이 API 토큰을 거부했습니다."
            " 토큰과 scope(documents.create)를 확인하세요."
        )
    if status == 404:
        return (
            "Outline 컬렉션을 찾지 못했습니다."
            " 컬렉션 ID 와 주소를 확인하세요."
        )
    return f"Outline 이 오류를 냈습니다(HTTP {status})."
```

`httpx.TimeoutException` 과 `httpx.ConnectError` 는 둘 다
`httpx.HTTPError` 의 자손이므로 한 갈래로 잡힌다.

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/services/test_outline.py -v`
Expected: PASS — 16 passed

- [ ] **Step 5: 전체 테스트·린트·타입**

Run: `uv run pytest -q`
Expected: **284 passed**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/outline.py tests/services/test_outline.py
git commit -m "$(cat <<'MSG'
✨ feat(outline): 실패를 읽을 수 있는 문장으로

401·404·5xx·연결 실패를 각각 무엇을 고쳐야
하는지 말하는 문장으로 옮긴다. httpx 의 원문
예외를 흘리면 요청 정보가 따라 나올 수 있어
우리가 지은 메시지만 내보낸다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

## Task 4: 저장 상태를 담을 자리 — 모델과 스키마

**Files:**
- Modify: `src/notebooklm_st/core/models.py`
- Modify: `src/notebooklm_st/services/store.py`
- Modify: `tests/services/test_store.py:114-160`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `models.RunSummary` 에 `outline_id: str | None = None`,
    `outline_url: str | None = None`, `outline_title: str | None = None`,
    `exported_at: str | None = None`
  - `runs` 테이블에 같은 이름의 네 컬럼

**주의 — 기존 테스트 하나가 깨진다.**
`tests/services/test_store.py` 의
`test_connect_adds_run_metadata_to_an_older_database` 는 **R4 이전의
`runs` 테이블**을 손으로 만들어 넣는다. 네 컬럼이 기대 목록에 들어가는
순간 그 DB 는 `StaleSchemaError` 로 거부되어 테스트가 실패한다. 그
테스트의 의도는 "새 **테이블**은 자동으로 생긴다" 이므로, fixture 의
`runs` 정의에 네 컬럼을 더해 의도를 살린다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_store.py` 맨 아래에 붙인다.

```python
def test_connect_rejects_a_database_without_the_outline_columns(
    tmp_path,
) -> None:
    """R4 이전 스키마의 DB 는 연결 시점에 거부된다.

    이 프로젝트는 마이그레이션을 두지 않는다. 옛 이력을 버리고 새로
    시작하는 것이 R4 의 결정이므로, 조용히 열리는 대신 안내와 함께
    멈춰야 한다.
    """
    db_path = tmp_path / "before_outline.db"
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
    raw.commit()
    raw.close()

    with pytest.raises(store.StaleSchemaError) as excinfo:
        store.connect(db_path)
    assert "runs" in str(excinfo.value)
    assert "exported_at" in str(excinfo.value)
```

같은 파일의 `test_connect_adds_run_metadata_to_an_older_database` 안에
있는 `CREATE TABLE runs (...)` 를 네 컬럼이 있는 형태로 바꾼다.

```python
        CREATE TABLE runs (
            id            INTEGER PRIMARY KEY,
            url           TEXT NOT NULL,
            video_id      TEXT NOT NULL,
            title         TEXT,
            created_at    TEXT NOT NULL,
            outline_id    TEXT,
            outline_url   TEXT,
            outline_title TEXT,
            exported_at   TEXT
        );
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/services/test_store.py -v`
Expected: FAIL — 새 테스트는 `StaleSchemaError` 가 안 나 실패하고,
고친 테스트는 `runs` 에 없는 컬럼 때문에 실패한다.

- [ ] **Step 3: 모델을 늘린다**

`src/notebooklm_st/core/models.py` 의 `RunSummary` 를 고친다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class RunSummary:
    """이력 목록에 한 줄로 보여 줄 실행 요약.

    ``exported_at`` 이 채워져 있으면 이 실행은 Outline 으로 넘어갔고
    로컬에는 링크만 남아 있다. 넷은 항상 함께 채워지거나 함께 비어
    있다.
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
```

기본값을 주므로 기존 생성 지점(테스트 포함)은 그대로 돈다.

- [ ] **Step 4: 스키마를 늘린다**

`src/notebooklm_st/services/store.py` 의 `_SCHEMA` 안 `runs` 정의를
바꾼다.

```sql
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY,
    url           TEXT NOT NULL,
    video_id      TEXT NOT NULL,
    title         TEXT,
    created_at    TEXT NOT NULL,
    outline_id    TEXT,
    outline_url   TEXT,
    outline_title TEXT,
    exported_at   TEXT
);
```

같은 파일의 `_EXPECTED_COLUMNS` 에서 `runs` 줄을 바꾼다.

```python
    "runs": frozenset(
        {
            "id",
            "url",
            "video_id",
            "title",
            "created_at",
            "outline_id",
            "outline_url",
            "outline_title",
            "exported_at",
        }
    ),
```

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/services/test_store.py -v`
Expected: PASS — 7 passed

- [ ] **Step 6: 전체 테스트·린트·타입**

Run: `uv run pytest -q`
Expected: **285 passed**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 전부 통과.

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/core/models.py src/notebooklm_st/services/store.py tests/services/test_store.py
git commit -m "$(cat <<'MSG'
✨ feat(store): 실행에 Outline 저장 상태 칸 더하기

문서 ID·제목·URL·저장 시각을 runs 에 둔다.
실행 하나당 문서 하나라 1:1 이고, exported_at
이 비었는지가 곧 미저장 여부다 — 해석이
하나뿐이라 별도 테이블을 두지 않는다.

옛 스키마의 DB 는 이제 열리지 않는다. 옛
이력을 버리고 새로 시작하는 것이 이 릴리스의
결정이다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

## Task 5: `list_runs` 가 저장 상태를 싣는다

**Files:**
- Modify: `src/notebooklm_st/services/run_history.py:66-104`
- Modify: `tests/services/test_run_history.py`

**Interfaces:**
- Consumes: `models.RunSummary` 의 네 필드 (Task 4)
- Produces: `run_history.list_runs` 가 돌려주는 `RunSummary` 에
  `outline_id`·`outline_url`·`outline_title`·`exported_at` 이 담긴다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_run_history.py` 맨 아래에 붙인다.

```python
def test_list_runs_reports_a_fresh_run_as_unexported(connection) -> None:
    """갓 저장한 실행에는 Outline 자리가 비어 있다."""
    run_history.save_run(connection, make_result())

    run = run_history.list_runs(connection)[0]

    assert run.exported_at is None
    assert run.outline_id is None
    assert run.outline_url is None
    assert run.outline_title is None


def test_list_runs_carries_the_document_link(connection) -> None:
    """DB 에 적힌 문서 링크가 요약에 실려 온다."""
    run_id = run_history.save_run(connection, make_result())
    connection.execute(
        "UPDATE runs SET outline_id = ?, outline_url = ?,"
        " outline_title = ?, exported_at = ? WHERE id = ?",
        (
            "doc-1",
            "http://192.168.0.10:3000/doc/x",
            "정리한 제목",
            "2026-09-22T15:00:00",
            run_id,
        ),
    )
    connection.commit()

    run = run_history.list_runs(connection)[0]

    assert run.outline_id == "doc-1"
    assert run.outline_url == "http://192.168.0.10:3000/doc/x"
    assert run.outline_title == "정리한 제목"
    assert run.exported_at == "2026-09-22T15:00:00"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/services/test_run_history.py -v -k "unexported or document_link"`
Expected: FAIL — `test_list_runs_carries_the_document_link` 가
`None == "doc-1"` 로 실패한다(SELECT 가 아직 네 컬럼을 읽지 않는다).

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/services/run_history.py` 의 `list_runs` 를 고친다.

```python
    rows = connection.execute(
        "SELECT r.id, r.url, r.video_id, r.title, r.created_at,"
        " r.outline_id, r.outline_url, r.outline_title, r.exported_at,"
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
            outline_id=row["outline_id"],
            outline_url=row["outline_url"],
            outline_title=row["outline_title"],
            exported_at=row["exported_at"],
        )
        for row in rows
    ]
```

docstring 의 `Returns:` 에 한 줄을 더한다.

```python
    Returns:
        실행 요약 목록. Outline 으로 넘어간 실행은 문서 링크를 싣고
        오며 ``answer_count`` 가 0 이다.
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/services/test_run_history.py -v`
Expected: PASS — 25 passed

- [ ] **Step 5: 전체 테스트·린트·타입**

Run: `uv run pytest -q`
Expected: **287 passed**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/run_history.py tests/services/test_run_history.py
git commit -m "$(cat <<'MSG'
✨ feat(history): 목록에 Outline 저장 상태 싣기

list_runs 가 문서 링크와 저장 시각을 함께
읽어 온다. 화면이 목록을 그리는 데 추가 조회가
없어야 Outline 이 죽어도 이력이 뜬다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

## Task 6: `mark_exported` — 링크를 적고 본문을 지운다

**Files:**
- Modify: `src/notebooklm_st/services/run_history.py`
- Modify: `tests/services/test_run_history.py`

**Interfaces:**
- Consumes: `store.now()`, Task 4 의 네 컬럼
- Produces:
  `run_history.mark_exported(connection, run_id, *, document_id: str, document_title: str, document_url: str) -> None`
  — 없는 `run_id` 면 `ValueError`

인자를 문자열로 받는다. `outline.SavedDocument` 를 받으면 저장소가
Outline 을 알게 된다(스펙 4절의 경계).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_run_history.py` 맨 아래에 붙인다.

```python
def export(connection, run_id: int) -> None:
    """테스트용 저장 기록 한 번."""
    run_history.mark_exported(
        connection,
        run_id,
        document_id="doc-1",
        document_title="정리한 제목",
        document_url="http://192.168.0.10:3000/doc/x",
    )


def test_mark_exported_writes_the_document_link(connection) -> None:
    """문서 ID·제목·URL 과 저장 시각이 남는다."""
    run_id = run_history.save_run(connection, make_result())

    export(connection, run_id)

    run = run_history.list_runs(connection)[0]
    assert run.outline_id == "doc-1"
    assert run.outline_title == "정리한 제목"
    assert run.outline_url == "http://192.168.0.10:3000/doc/x"
    assert run.exported_at is not None


def test_mark_exported_deletes_the_local_answers(connection) -> None:
    """진실의 원천을 하나로 둔다 — 본문은 Outline 에만 남는다."""
    run_id = run_history.save_run(connection, make_result())

    export(connection, run_id)

    assert run_history.load_run_items(connection, run_id) == []


def test_mark_exported_deletes_the_local_metadata(connection) -> None:
    """메타데이터도 문서 frontmatter 로 옮겨 갔으므로 지운다."""
    run_id = run_history.save_run(
        connection,
        make_result(),
        models.VideoMetadata(channel="안될공학", upload_date="2026-09-15"),
    )

    export(connection, run_id)

    assert run_history.load_metadata(connection, run_id) is None


def test_mark_exported_keeps_the_run_itself(connection) -> None:
    """실행 행은 남는다. 링크를 걸어 둘 자리가 필요하다."""
    run_id = run_history.save_run(connection, make_result())

    export(connection, run_id)

    runs = run_history.list_runs(connection)
    assert len(runs) == 1
    assert runs[0].id == run_id
    assert runs[0].answer_count == 0


def test_mark_exported_rejects_an_unknown_run(connection) -> None:
    """없는 실행에 링크를 걸지 않는다."""
    with pytest.raises(ValueError):
        export(connection, 999)


def test_mark_exported_keeps_the_answers_of_an_unknown_run(
    connection,
) -> None:
    """실패하면 아무것도 지우지 않는다."""
    run_id = run_history.save_run(connection, make_result())

    with pytest.raises(ValueError):
        export(connection, 999)

    assert len(run_history.load_run_items(connection, run_id)) == 2
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/services/test_run_history.py -v -k mark_exported`
Expected: FAIL — `AttributeError: module 'notebooklm_st.services.run_history' has no attribute 'mark_exported'`

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/services/run_history.py` 의 `load_metadata` 아래에
더한다.

```python
def mark_exported(
    connection: sqlite3.Connection,
    run_id: int,
    *,
    document_id: str,
    document_title: str,
    document_url: str,
) -> None:
    """문서 링크를 적고 로컬 본문을 지운다.

    세 문장을 커밋 하나로 묶는다. 중간에 죽어도 "본문은 사라졌는데
    링크는 없는" 상태가 생기지 않는다.

    Outline 의 자료형을 받지 않고 문자열 셋을 받는다. 저장소가 외부
    서비스를 알 이유가 없다.

    Args:
        connection: 열린 커넥션.
        run_id: 링크를 걸 실행 ID.
        document_id: Outline 문서 ID. 나중에 문서를 다시 읽을 때 쓴다.
        document_title: Outline 에 붙은 문서 제목.
        document_url: 사람이 열 수 있는 절대 URL.

    Raises:
        ValueError: 그 ID 의 실행이 없는 경우. 이때는 아무것도 지우지
            않는다.
    """
    cursor = connection.execute(
        "UPDATE runs SET outline_id = ?, outline_url = ?,"
        " outline_title = ?, exported_at = ? WHERE id = ?",
        (
            document_id,
            document_url,
            document_title,
            store.now(),
            run_id,
        ),
    )
    if cursor.rowcount == 0:
        connection.rollback()
        raise ValueError(f"실행 {run_id} 을 찾을 수 없습니다.")
    connection.execute("DELETE FROM answers WHERE run_id = ?", (run_id,))
    connection.execute(
        "DELETE FROM run_metadata WHERE run_id = ?", (run_id,)
    )
    connection.commit()
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/services/test_run_history.py -v`
Expected: PASS — 31 passed

- [ ] **Step 5: 전체 테스트·린트·타입**

Run: `uv run pytest -q`
Expected: **293 passed**

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/run_history.py tests/services/test_run_history.py
git commit -m "$(cat <<'MSG'
✨ feat(history): 저장된 실행의 본문을 링크로 바꾸기

문서 링크를 적고 답변과 메타데이터를 지우는
일을 커밋 하나로 묶는다. 중간에 죽어도 본문만
사라진 실행이 남지 않는다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

## Task 7: 본문 편집을 걷어낸다

**Files:**
- Modify: `src/notebooklm_st/services/run_history.py:157-186` (`update_answer` 삭제)
- Modify: `src/notebooklm_st/components/answer_view.py`
- Modify: `src/notebooklm_st/pages/history.py:60-71,160-172`
- Modify: `tests/services/test_run_history.py:167-207` (테스트 넷 삭제)
- Modify: `tests/test_components.py:536-633` (테스트 셋 삭제)
- Modify: `tests/pages/test_history.py` (테스트 넷 삭제, 하나 수정)

**Interfaces:**
- Consumes: 없음
- Produces:
  - `answer_view.render_items(items: Sequence[models.AnswerItem]) -> None`
    — `on_save` 키워드가 사라진다. 호출자는 목록 하나만 넘긴다.
  - `run_history.update_answer` 가 사라진다.

수정을 Outline 에 위임했으므로 앱 안에 같은 일을 하는 길을 남기지
않는다. 두 곳이 있으면 어느 쪽이 진짜인지 묻게 된다.

- [ ] **Step 1: 사라질 테스트를 지운다**

삭제 대상(이름으로 찾아 함수 전체를 지운다).

| 파일 | 함수 |
|---|---|
| `tests/services/test_run_history.py` | `test_update_answer_replaces_the_body`, `test_update_answer_trims_whitespace`, `test_update_answer_rejects_an_empty_body`, `test_update_answer_rejects_an_unknown_id` |
| `tests/test_components.py` | `test_answer_view_stays_read_only_for_an_item_without_an_id`, `test_answer_view_saves_the_edited_body` |
| `tests/pages/test_history.py` | `test_answer_is_editable_when_citations_are_shown`, `test_editing_saves_the_new_body`, `test_editing_rejects_an_empty_body`, `test_hiding_citations_locks_editing` |

`tests/test_components.py:539` 의
`test_answer_view_stays_read_only_without_a_save_hook` 은 **남긴다.**
이름이 전제("저장 훅이 없으면")를 잃었으므로 함께 고친다 — 함수 이름을
`test_answer_view_never_draws_an_editor` 로, docstring 을 "편집 상자를
그리지 않는다. 수정은 Outline 이 맡는다." 로 바꾸고, `render_items`
호출에서 사라진 인자가 없는지 확인한다(이 테스트는 원래 훅을 넘기지
않으므로 호출부는 그대로다).

- [ ] **Step 2: 남은 테스트 하나를 고친다**

`tests/pages/test_history.py` 의 `test_selected_run_shows_its_answers`
는 편집 상자를 전제로 본문을 읽고 있다. 마크다운에서 읽도록 바꾼다.

```python
def test_selected_run_shows_its_answers(app_db) -> None:
    """선택한 실행의 답변들을 보여 준다."""
    run_history.save_run(app_db, make_result())
    app = v1.AppTest.from_function(script).run()
    headers = [element.value for element in app.subheader]
    assert headers == ["핵심 주장"]
    assert not app.exception
    rendered = " ".join(element.value for element in app.markdown)
    assert "세 가지다." in rendered
    assert "근거 구절" in rendered
```

- [ ] **Step 3: 삭제가 다른 테스트를 깨뜨리지 않았는지 본다**

이 태스크는 기능을 더하는 것이 아니라 걷어내는 것이라 실패하는 테스트를
먼저 쓰지 않는다. 지우는 쪽이 먼저고, 남은 것이 그대로 도는지 확인한다.

Run: `uv run pytest -q`
Expected: **283 passed** — 지운 10개만큼 줄었고 나머지는 그대로 통과한다.
아직 구현 코드를 건드리지 않았으므로 여기서 실패가 나면 삭제 범위를
잘못 잡은 것이다.

- [ ] **Step 4: `update_answer` 를 지운다**

`src/notebooklm_st/services/run_history.py` 에서 `update_answer` 함수를
통째로 지운다.

- [ ] **Step 5: `answer_view` 를 읽기 전용으로 만든다**

`src/notebooklm_st/components/answer_view.py` 를 아래로 바꾼다.

```python
"""답변 카드 렌더."""

from collections.abc import Sequence

import streamlit as st

from notebooklm_st.core import models


def render_items(items: Sequence[models.AnswerItem]) -> None:
    """답변 목록을 위에서 아래로 카드처럼 그린다.

    항목 사이에만 구분자를 넣는다. 마지막 뒤에도 넣으면 화면 끝에
    가르는 것 없는 줄이 남는다.

    읽기만 한다. 요약본을 고치는 일은 Outline 이 맡는다.

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

`_EDIT_HEIGHT` 상수와 `SaveCallback` 타입 별칭, `Callable` import 가
함께 빠진다.

- [ ] **Step 6: 화면의 저장 경로를 걷어낸다**

`src/notebooklm_st/pages/history.py` 에서 `_save` 함수를 통째로 지우고,
`render()` 끝의 두 갈래 호출을 하나로 만든다.

```python
    items = run_history.load_run_items(connection, selected.id)
    if hidden:
        items = [answer_text.for_display(item) for item in items]
    metadata = run_history.load_metadata(connection, selected.id)
    _render_download(selected, items, metadata)
    answer_view.render_items(items)
```

`render()` 의 docstring 에서 편집을 설명하던 문장을 지운다. 인용
숨기기가 "편집도 함께 잠근다" 는 근거는 편집이 사라져 성립하지 않는다.

```python
    """최근 실행을 고르고 그 답변들을 보여 준다.

    인용 숨기기 체크박스를 켜면 ``answer_text.for_display`` 가 만든
    사본을 그린다. 내려받기는 화면에 그리는 목록을 그대로 받으므로
    이 상태를 따라간다.
    삭제는 실수로 한 번에 지워지지 않도록 확인 버튼을 한 번 더
    거치는 2단계로 되어 있다(``_render_delete`` 참고).
    """
```

- [ ] **Step 7: 통과를 확인한다**

Run: `uv run pytest -q`
Expected: **283 passed** (293 − 삭제한 10)

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 전부 통과. `sqlite3` import 가 `history.py` 에서 여전히
쓰이는지(`_render_delete`·`_delete` 의 타입 힌트) 확인한다 — 쓰이므로
남긴다.

- [ ] **Step 8: 커밋**

```bash
git add src/notebooklm_st/services/run_history.py src/notebooklm_st/components/answer_view.py src/notebooklm_st/pages/history.py tests/
git commit -m "$(cat <<'MSG'
🔥 remove(history): 앱 안의 답변 편집 걷어내기

수정은 Outline 이 맡는다. 앱에 같은 일을 하는
길을 남기면 어느 쪽이 진짜인지 묻게 된다.
답변 카드는 읽기 전용 컴포넌트가 되었다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

## Task 8: 내려받기를 걷어내고 문서 본문을 Outline 모양으로

**Files:**
- Modify: `src/notebooklm_st/core/markdown_export.py`
- Modify: `src/notebooklm_st/pages/history.py` (`_render_download` 삭제)
- Modify: `tests/core/test_markdown_export.py`
- Modify: `tests/pages/test_history.py` (내려받기 테스트 넷 삭제)

**Interfaces:**
- Consumes: 없음
- Produces:
  `markdown_export.to_markdown(summary: models.RunSummary, items: Sequence[models.AnswerItem], title: str, metadata: models.VideoMetadata | None) -> str`
  — 인자 넷 모두 필수. `to_filename` 이 사라진다.

Outline 이 문서 제목을 따로 가지므로 본문 `# 제목` 을 뺀다. 넣으면
제목이 두 번 보인다. "출처 · 실행" 블록은 **남긴다** — frontmatter 의
URL 은 구분선 사이 맨 텍스트로 렌더되어 클릭되지 않으므로, 사람이
누를 링크가 본문에 하나 있어야 한다.

- [ ] **Step 1: 테스트를 새 시그니처에 맞춘다**

`tests/core/test_markdown_export.py` 의 `make_item` 아래에 헬퍼를 더한다.

```python
DEFAULT_TITLE = "어떻게 AI는 생각하는가"


def export(
    summary=None,
    items=None,
    title=DEFAULT_TITLE,
    metadata=None,
) -> str:
    """새 시그니처로 문서를 만든다."""
    return markdown_export.to_markdown(
        summary if summary is not None else make_summary(),
        items if items is not None else [make_item()],
        title,
        metadata,
    )
```

`to_markdown(...)` 을 직접 부르는 기존 호출을 전부 `export(...)` 로
바꾼다. 인자 대응은 이렇다.

- `to_markdown(make_summary(), [make_item()])` → `export()`
- `to_markdown(make_summary(title=None), [make_item()])` →
  `export(summary=make_summary(title=None), title="dQw4w9WgXcQ")`
- `to_markdown(summary, items, metadata)` →
  `export(summary=summary, items=items, metadata=metadata)`

- [ ] **Step 2: 의미가 바뀌는 테스트 둘을 다시 쓴다**

`test_to_markdown_opens_with_the_title_and_source` 를 지우고 아래로
대체한다.

```python
def test_to_markdown_opens_with_the_source_block() -> None:
    """Frontmatter 다음 첫 블록은 출처와 실행 시각이다.

    H1 을 넣지 않는다. Outline 이 문서 제목을 따로 가지므로 넣으면
    제목이 두 번 보인다.
    """
    body = export().split("---\n", 2)[2]
    lines = body.splitlines()

    assert lines[1] == "- 출처: https://youtu.be/dQw4w9WgXcQ"
    assert lines[2] == "- 실행: 2026-08-31T14:02:11"
    assert "# 어떻게 AI는 생각하는가" not in body
```

`test_to_markdown_falls_back_to_video_id_without_a_title` 를 지우고
아래로 대체한다. 제목의 대체값 계산은 이제 화면이 하고, 이 함수는 받은
제목을 그대로 쓴다.

```python
def test_to_markdown_writes_the_given_title_into_frontmatter() -> None:
    """확인한 제목이 frontmatter 의 title 이 된다."""
    text = export(summary=make_summary(title="저장된 옛 제목"),
                  title="사람이 고친 제목")

    assert 'title: "사람이 고친 제목"' in text
    assert "저장된 옛 제목" not in text
```

- [ ] **Step 3: `to_filename` 테스트 여섯을 지운다**

`tests/core/test_markdown_export.py` 에서 아래 함수를 통째로 지운다.

`test_to_filename_uses_the_title`,
`test_to_filename_replaces_forbidden_characters`,
`test_to_filename_strips_trailing_dots_and_spaces`,
`test_to_filename_truncates_a_long_title`,
`test_to_filename_falls_back_to_video_id_without_a_title`,
`test_to_filename_falls_back_when_nothing_survives`

- [ ] **Step 4: 내려받기 화면 테스트 넷을 지운다**

`tests/pages/test_history.py` 에서 아래 함수를 통째로 지운다.

`test_selected_run_offers_a_markdown_download`,
`test_download_stays_available_while_citations_are_hidden`,
`test_download_works_for_a_run_with_metadata`,
`test_download_passes_the_stored_metadata_to_markdown_export`

이 파일 맨 위의 `markdown_export` import 가 쓰이지 않게 되면 함께
지운다.

- [ ] **Step 5: 실패를 확인한다**

Run: `uv run pytest tests/core/test_markdown_export.py -v`
Expected: FAIL — `to_markdown() takes 2 to 3 positional arguments but 4 were given`

- [ ] **Step 6: `to_markdown` 을 고친다**

`src/notebooklm_st/core/markdown_export.py` 의 모듈 docstring 을 새
역할에 맞게 바꾼다.

```python
"""이력 한 건을 Outline 문서 본문으로 옮기는 순수 함수들.

화면이 저장 버튼에 넘길 마크다운을 만든다. 저장된 답변은 손대지
않으며, 인용을 뺀 채로 올리는 경우에도 걸러진 사본이 여기로 들어올
뿐이다(→ ``core.answer_text``).
"""
```

`to_markdown` 을 바꾼다.

```python
def to_markdown(
    summary: models.RunSummary,
    items: Sequence[models.AnswerItem],
    title: str,
    metadata: models.VideoMetadata | None,
) -> str:
    """실행 하나를 Outline 문서 본문으로 만든다.

    ``# 제목`` 머리글을 넣지 않는다. Outline 이 문서 제목을 따로
    가지므로 넣으면 제목이 두 번 보인다. 대신 출처 블록은 남긴다 —
    frontmatter 의 URL 은 구분선 사이 맨 텍스트로 렌더되어 클릭되지
    않는다.

    Args:
        summary: 출처와 실행 시각에 쓸 실행 요약.
        items: 문서에 담을 답변 목록. 화면이 그리는 것과 같은 목록을
            받으므로 인용을 뺀 상태면 인용이 비어 들어온다.
        title: 사람이 저장 직전에 확인한 문서 제목. 같은 값이 Outline
            문서 제목이 되므로 여기서 다시 계산하지 않는다.
        metadata: 영상에서 뽑아 온 메타데이터. 없으면 frontmatter 에
            ``title`` 과 ``url`` 만 남는다.

    Returns:
        YAML frontmatter 로 시작하고 줄바꿈 하나로 끝나는 마크다운
        문서.
    """
    blocks = [
        _frontmatter(summary, title, metadata),
        f"- 출처: {summary.url}\n- 실행: {summary.created_at}",
    ]
    blocks.extend(_item_block(item) for item in items)
    return "\n\n".join(blocks) + "\n"
```

- [ ] **Step 7: `to_filename` 과 딸린 것들을 지운다**

같은 파일에서 아래를 통째로 지운다.

- `MAX_STEM_CHARS` 상수와 그 docstring
- `_FORBIDDEN` 상수와 그 docstring
- `_REPEATED_SPACE` 상수
- `to_filename` 함수
- `_sanitize` 함수

`_CONTROL` 과 `_yaml_string` 은 frontmatter 가 계속 쓰므로 **남긴다.**
`import re` 도 `_CONTROL` 이 쓰므로 남는다.

- [ ] **Step 8: 화면에서 내려받기를 걷어낸다**

`src/notebooklm_st/pages/history.py` 에서 `_render_download` 함수를
통째로 지우고, `render()` 의 호출 한 줄도 지운다. `Sequence` import 가
쓰이지 않게 되면 함께 지운다. `render()` docstring 의 내려받기 문장도
지운다.

```python
    """최근 실행을 고르고 그 답변들을 보여 준다.

    인용 숨기기 체크박스를 켜면 ``answer_text.for_display`` 가 만든
    사본을 그린다.
    삭제는 실수로 한 번에 지워지지 않도록 확인 버튼을 한 번 더
    거치는 2단계로 되어 있다(``_render_delete`` 참고).
    """
```

- [ ] **Step 9: 통과를 확인한다**

Run: `uv run pytest -q`
Expected: **273 passed** (283 − 삭제한 10)

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 전부 통과.

- [ ] **Step 10: 지운 것이 남아 있지 않은지 확인한다**

```bash
grep -rn "to_filename\|_render_download\|MAX_STEM_CHARS" src tests; echo "종료코드 $?"
```

Expected: 아무것도 찍히지 않고 `종료코드 1`.

- [ ] **Step 11: 커밋**

```bash
git add src/notebooklm_st/core/markdown_export.py src/notebooklm_st/pages/history.py tests/
git commit -m "$(cat <<'MSG'
🔥 remove(export): 마크다운 내려받기 걷어내기

문서를 밖으로 빼내는 일은 Outline 이 맡는다.
to_markdown 은 확인한 제목을 받아 H1 없이
본문을 만든다 — Outline 이 제목을 따로 가지고
있어 넣으면 두 번 보인다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

## Task 9: 이력 화면 — 저장된 실행은 링크 한 줄

**Files:**
- Modify: `src/notebooklm_st/pages/history.py`
- Modify: `tests/pages/test_history.py`

**Interfaces:**
- Consumes: `RunSummary.exported_at`·`outline_url`·`outline_title` (Task 5),
  `run_history.mark_exported` (Task 6, 테스트가 상태를 만드는 데 쓴다)
- Produces: `render()` 가 `exported_at` 으로 두 갈래로 갈린다. 저장된
  실행에서는 답변을 읽지 않는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_history.py` 맨 아래에 붙인다.

```python
def export(app_db, run_id: int) -> None:
    """실행 하나를 저장된 상태로 만든다."""
    run_history.mark_exported(
        app_db,
        run_id,
        document_id="doc-1",
        document_title="정리한 제목",
        document_url="http://192.168.0.10:3000/doc/x",
    )


def test_exported_run_shows_the_document_link(app_db) -> None:
    """저장된 실행은 문서명과 링크만 보여 준다."""
    run_id = run_history.save_run(app_db, make_result(title="밸류에이션 강의"))
    export(app_db, run_id)

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    rendered = " ".join(element.value for element in app.markdown)
    assert "정리한 제목" in rendered
    links = app.get("link_button")
    assert len(links) == 1
    assert links[0].proto.url == "http://192.168.0.10:3000/doc/x"


def test_exported_run_draws_no_answer_cards(app_db) -> None:
    """본문이 로컬에 없으므로 그릴 것도 없다."""
    run_id = run_history.save_run(app_db, make_result())
    export(app_db, run_id)

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.subheader) == 0


def test_exported_run_label_uses_the_document_title(app_db) -> None:
    """목록에서는 위키에 있는 이름으로 찾는다."""
    run_id = run_history.save_run(app_db, make_result(title="밸류에이션 강의"))
    export(app_db, run_id)

    app = v1.AppTest.from_function(script).run()

    label = app.selectbox[0].options[0]
    assert label.startswith("정리한 제목 · ")
    assert label.endswith(" · 문서")


def test_unexported_run_label_says_so(app_db) -> None:
    """미저장 실행은 그렇게 적어 둔다."""
    run_history.save_run(app_db, make_result(title="밸류에이션 강의"))

    app = v1.AppTest.from_function(script).run()

    assert app.selectbox[0].options[0].endswith(" · 미저장 · 답변 1건")


def test_deleting_an_exported_run_warns_about_the_document(app_db) -> None:
    """지우면 링크만 사라진다는 것을 알려 준다."""
    run_id = run_history.save_run(app_db, make_result())
    export(app_db, run_id)

    app = v1.AppTest.from_function(script)
    app.run()
    app.button[0].click().run()

    assert not app.exception
    assert "Outline 문서는 그대로 남습니다" in app.warning[0].value
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/pages/test_history.py -v -k "exported or unexported"`
Expected: FAIL — 라벨이 `· 문서` 로 끝나지 않고, `link_button` 이 없다.

- [ ] **Step 3: 목록 라벨을 고친다**

`src/notebooklm_st/pages/history.py` 의 `_format_run` 을 바꾼다.

```python
def _format_run(run: models.RunSummary) -> str:
    """실행 하나를 목록에 보여 줄 한 줄로 만든다.

    제목을 앞에 둔다. 목록에서 고르는 사람이 먼저 알고 싶은 것은
    시각이 아니라 어떤 영상이었는지다. 목록은 최신순으로 고정되어
    있으므로 시각은 뒤에 있어도 읽는 데 지장이 없다.

    저장된 실행은 위키에 붙은 이름으로 찾게 된다. 그래서 영상 제목이
    아니라 문서 제목을 쓴다.
    """
    if run.exported_at is not None:
        label = _shorten(run.outline_title or run.video_id)
        return f"{label} · {run.created_at} · 문서"
    label = _shorten(run.title) if run.title else run.video_id
    return f"{label} · {run.created_at} · 미저장 · 답변 {run.answer_count}건"
```

- [ ] **Step 4: 저장된 실행을 그리는 갈래를 더한다**

`_render_delete` 아래에 더한다.

```python
def _render_saved(selected: models.RunSummary) -> None:
    """저장된 실행을 문서명과 링크로 그린다.

    본문은 로컬에 없다. 수정·삭제·검색은 Outline 이 맡는다.
    """
    st.success(f"Outline 에 저장됨 · {selected.exported_at}")
    st.markdown(f"**{selected.outline_title}**")
    if selected.outline_url:
        st.link_button("Outline 에서 열기", selected.outline_url)
```

`render()` 의 `_render_delete` 호출 바로 뒤에 갈래를 넣는다.

```python
    _render_delete(connection, selected)
    if selected.exported_at is not None:
        _render_saved(selected)
        return
```

- [ ] **Step 5: 삭제 경고 문구를 상태에 맞춘다**

`_render_delete` 안의 `st.warning` 한 줄을 바꾼다.

```python
        if selected.exported_at is not None:
            st.warning(
                "로컬 링크만 지웁니다. Outline 문서는 그대로 남습니다."
            )
        else:
            st.warning("딸린 답변도 함께 사라집니다. 되돌릴 수 없습니다.")
```

- [ ] **Step 6: 통과를 확인한다**

Run: `uv run pytest tests/pages/test_history.py -v`
Expected: PASS

Run: `uv run pytest -q`
Expected: **278 passed** (273 + 5)

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 전부 통과.

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/pages/history.py tests/pages/test_history.py
git commit -m "$(cat <<'MSG'
✨ feat(history): 저장된 실행을 문서 링크로 보여주기

Outline 으로 넘어간 실행은 문서명과 링크만
그린다. 목록 라벨도 위키에 붙은 이름을 쓴다 —
저장한 뒤에 찾는 이름이 그쪽이다.

삭제 경고도 상태를 따라간다. 저장된 실행을
지우면 링크만 사라지고 문서는 남는다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

## Task 10: 이력 화면 — 저장 UI 와 성공 경로

**Files:**
- Modify: `src/notebooklm_st/pages/history.py`
- Modify: `tests/conftest.py`
- Modify: `tests/pages/test_history.py`

**Interfaces:**
- Consumes: `outline.config_from_env`, `outline.create_document`,
  `outline.SavedDocument` (Task 1·2), `run_history.mark_exported` (Task 6),
  `markdown_export.to_markdown` (Task 8)
- Produces: 미저장 실행에 제목 입력(`key=f"history_title_{run.id}"`),
  "인용 포함" 체크박스(`key="history_include_citations"`), 저장
  버튼(`key=f"history_export_{run.id}"`)

**체크박스가 뒤집힌다.** `_HIDE_CITATIONS_KEY`("인용 숨기기")가
`_INCLUDE_CITATIONS_KEY`("인용 포함", 기본 켬)이 된다. 기존 테스트 둘이
`.check()` 로 숨김을 켰으므로 `.uncheck()` 로 바꾼다.

- [ ] **Step 1: 테스트가 실제 환경변수를 보지 않게 막는다**

`tests/conftest.py` 에 autouse fixture 를 더한다.

```python
from notebooklm_st.services import auth, outline, store


@pytest.fixture(autouse=True)
def clear_outline_env(monkeypatch) -> None:
    """개발 기기의 Outline 설정이 테스트에 새지 않게 막는다.

    설정이 있는 기기와 없는 기기에서 결과가 달라지면 안 된다. 필요한
    테스트가 직접 채워 쓴다.
    """
    for name in (
        outline.URL_ENV_VAR,
        outline.TOKEN_ENV_VAR,
        outline.COLLECTION_ENV_VAR,
    ):
        monkeypatch.delenv(name, raising=False)
```

- [ ] **Step 2: 기존 체크박스 테스트 둘을 뒤집는다**

`tests/pages/test_history.py` 의
`test_hiding_citations_strips_markers_and_the_tail` 과
`test_hiding_citations_keeps_the_question_expander` 에서
`app.checkbox[0].check().run()` 을 `app.checkbox[0].uncheck().run()` 으로
바꾸고, 함수 이름을 각각
`test_excluding_citations_strips_markers_and_the_tail`,
`test_excluding_citations_keeps_the_question_expander` 로 바꾼다.
docstring 도 "체크박스를 끄면" 으로 고친다.

- [ ] **Step 3: 실패하는 테스트를 쓴다**

먼저 `tests/pages/test_history.py` 맨 위의 import 한 줄을 늘린다. 파일
중간에 두면 ruff `E402` 에 걸린다.

```python
from notebooklm_st.services import outline, run_history
```

그다음 파일 맨 아래에 붙인다.

```python
def set_outline_env(monkeypatch) -> None:
    """저장 버튼이 나오도록 설정을 채운다."""
    monkeypatch.setenv(outline.URL_ENV_VAR, "http://192.168.0.10:3000")
    monkeypatch.setenv(outline.TOKEN_ENV_VAR, "ol_secret")
    monkeypatch.setenv(outline.COLLECTION_ENV_VAR, "col-1")


def fake_create(calls, document=None):
    """create_document 를 대신해 호출을 기록한다."""

    def create(config, title, markdown, **kwargs):
        """호출 인자를 기록하고 만들어진 문서를 돌려준다."""
        calls.append((config, title, markdown))
        return document or outline.SavedDocument(
            id="doc-1",
            title=title,
            url="http://192.168.0.10:3000/doc/x",
        )

    return create


def test_export_button_is_hidden_without_configuration(app_db) -> None:
    """설정이 없으면 저장 버튼 대신 안내를 낸다."""
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert "history_export_1" not in [element.key for element in app.button]
    messages = " ".join(element.value for element in app.info)
    assert outline.URL_ENV_VAR in messages


def test_export_button_appears_with_configuration(
    app_db, monkeypatch
) -> None:
    """설정이 있으면 제목 입력과 저장 버튼이 나온다."""
    set_outline_env(monkeypatch)
    run_history.save_run(app_db, make_result(title="밸류에이션 강의"))

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert app.text_input[0].value == "밸류에이션 강의"


def test_export_title_falls_back_to_the_video_id(
    app_db, monkeypatch
) -> None:
    """저장된 영상 제목이 없으면 영상 ID 를 기본값으로 쓴다."""
    set_outline_env(monkeypatch)
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script).run()

    assert app.text_input[0].value == "dQw4w9WgXcQ"


def test_export_sends_the_confirmed_title_and_body(
    app_db, monkeypatch
) -> None:
    """확인한 제목과 화면에 보이는 본문이 그대로 올라간다."""
    set_outline_env(monkeypatch)
    calls: list[tuple[object, str, str]] = []
    monkeypatch.setattr(outline, "create_document", fake_create(calls))
    run_history.save_run(app_db, make_result(title="밸류에이션 강의"))

    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input[0].set_value("사람이 고친 제목").run()
    app.button(key="history_export_1").click().run()

    assert not app.exception
    assert len(calls) == 1
    _, title, markdown = calls[0]
    assert title == "사람이 고친 제목"
    assert 'title: "사람이 고친 제목"' in markdown
    assert "세 가지다." in markdown


def test_export_records_the_link_and_drops_the_body(
    app_db, monkeypatch
) -> None:
    """성공하면 링크가 남고 로컬 본문이 사라진다."""
    set_outline_env(monkeypatch)
    monkeypatch.setattr(outline, "create_document", fake_create([]))
    run_id = run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_export_1").click().run()

    assert not app.exception
    run = run_history.list_runs(app_db)[0]
    assert run.outline_url == "http://192.168.0.10:3000/doc/x"
    assert run_history.load_run_items(app_db, run_id) == []


def test_export_can_leave_the_citations_out(app_db, monkeypatch) -> None:
    """체크박스를 끄면 걸러진 본문이 올라간다."""
    set_outline_env(monkeypatch)
    calls: list[tuple[object, str, str]] = []
    monkeypatch.setattr(outline, "create_document", fake_create(calls))
    run_history.save_run(app_db, make_result(answer=ANSWER_WITH_CITATIONS))

    app = v1.AppTest.from_function(script)
    app.run()
    app.checkbox[0].uncheck().run()
    app.button(key="history_export_1").click().run()

    markdown = calls[0][2]
    assert "[1]" not in markdown
    assert "제안 문단" not in markdown
```

- [ ] **Step 4: 실패를 확인한다**

Run: `uv run pytest tests/pages/test_history.py -v -k export`
Expected: FAIL — `app.text_input` 이 비어 있고
`app.button(key="history_export_1")` 이 없다.

- [ ] **Step 5: 구현한다**

`src/notebooklm_st/pages/history.py` 의 import 와 상수를 고친다.

```python
from notebooklm_st.core import answer_text, markdown_export, models
from notebooklm_st.services import outline, run_history
```

```python
_INCLUDE_CITATIONS_KEY = "history_include_citations"
```

(`_HIDE_CITATIONS_KEY` 는 지운다.)

`render()` 의 뒷부분을 바꾼다.

```python
    title = st.text_input(
        "문서 제목",
        value=selected.title or selected.video_id,
        key=f"history_title_{selected.id}",
        help="Outline 문서의 제목이 됩니다.",
    )
    included = st.checkbox(
        "인용 포함",
        value=True,
        key=_INCLUDE_CITATIONS_KEY,
        help="끄면 인용 번호와 인용 본문, 맨 아래 후속 제안을 뺀 채로"
        " 올립니다. 화면도 같은 상태로 보입니다.",
    )
    items = run_history.load_run_items(connection, selected.id)
    if not included:
        items = [answer_text.for_display(item) for item in items]
    metadata = run_history.load_metadata(connection, selected.id)
    _render_export(connection, selected, title, items, metadata)
    answer_view.render_items(items)
```

`_render_saved` 아래에 더한다.

```python
def _render_export(
    connection: sqlite3.Connection,
    selected: models.RunSummary,
    title: str,
    items: Sequence[models.AnswerItem],
    metadata: models.VideoMetadata | None,
) -> None:
    """저장 버튼을 그린다. 설정이 없으면 안내로 대신한다.

    이력 열람 자체는 막지 않는다. Outline 을 아직 붙이지 않았어도
    지난 실행을 읽는 데에는 아무 문제가 없다.
    """
    config = outline.config_from_env()
    if config is None:
        st.info(
            "Outline 연결이 설정되지 않았습니다."
            f" {outline.URL_ENV_VAR}·{outline.TOKEN_ENV_VAR}"
            f"·{outline.COLLECTION_ENV_VAR} 를 설정하세요."
        )
        return
    if st.button(
        "Outline 에 저장",
        key=f"history_export_{selected.id}",
        disabled=not title.strip(),
        help="지금 보이는 그대로 올립니다."
        " 올린 뒤에는 로컬에 링크만 남습니다.",
    ):
        _export(connection, config, selected, title.strip(), items, metadata)


def _export(
    connection: sqlite3.Connection,
    config: outline.OutlineConfig,
    selected: models.RunSummary,
    title: str,
    items: Sequence[models.AnswerItem],
    metadata: models.VideoMetadata | None,
) -> None:
    """문서를 만들고 링크를 기록한다.

    실패하면 로컬을 손대지 않는다. 원인을 고친 뒤 같은 버튼을 다시
    누르면 된다.
    """
    with st.spinner("Outline 에 저장 중"):
        try:
            document = outline.create_document(
                config,
                title,
                markdown_export.to_markdown(selected, items, title, metadata),
            )
        except outline.OutlineError as error:
            st.error(str(error))
            return
        run_history.mark_exported(
            connection,
            selected.id,
            document_id=document.id,
            document_title=document.title,
            document_url=document.url,
        )
    st.rerun()
```

`Sequence` import 를 다시 살린다.

```python
from collections.abc import Sequence
```

- [ ] **Step 6: 통과를 확인한다**

Run: `uv run pytest tests/pages/test_history.py -v`
Expected: PASS

Run: `uv run pytest -q`
Expected: **284 passed** (278 + 6)

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 전부 통과.

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/pages/history.py tests/conftest.py tests/pages/test_history.py
git commit -m "$(cat <<'MSG'
✨ feat(history): 요약본을 Outline 에 올리기

제목을 확인하고 인용 포함 여부를 고른 뒤
버튼을 누르면 문서가 만들어진다. 성공하면 링크가
남고 로컬 본문은 사라진다.

화면에 보이는 것이 곧 올라가는 것이다 — 인용을
뺀 상태면 걸러진 사본이 화면과 문서 양쪽에
쓰인다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

## Task 11: 이력 화면 — 실패를 정직하게 보여 준다

**Files:**
- Modify: `src/notebooklm_st/pages/history.py:_export`
- Modify: `tests/pages/test_history.py`

**Interfaces:**
- Consumes: `outline.OutlineError` (Task 3)
- Produces: `_export` 가 두 실패를 각각 다르게 다룬다. 시그니처 변화
  없음.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_history.py` 맨 아래에 붙인다.

```python
def failing_create(message: str):
    """create_document 대신 OutlineError 를 던진다."""

    def create(config, title, markdown, **kwargs):
        """항상 실패한다."""
        raise outline.OutlineError(message)

    return create


def test_export_failure_shows_the_message(app_db, monkeypatch) -> None:
    """실패 사유를 사람이 읽을 수 있게 보여 준다."""
    set_outline_env(monkeypatch)
    monkeypatch.setattr(
        outline,
        "create_document",
        failing_create("Outline 에 연결하지 못했습니다(ConnectError)."),
    )
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_export_1").click().run()

    assert not app.exception
    assert "연결하지 못했습니다" in app.error[0].value


def test_export_failure_keeps_the_local_copy(app_db, monkeypatch) -> None:
    """실패하면 로컬을 손대지 않는다. 고친 뒤 다시 누르면 된다."""
    set_outline_env(monkeypatch)
    monkeypatch.setattr(
        outline, "create_document", failing_create("토큰이 거부되었습니다.")
    )
    run_id = run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_export_1").click().run()

    assert not app.exception
    assert len(run_history.load_run_items(app_db, run_id)) == 1
    assert run_history.list_runs(app_db)[0].exported_at is None


def test_export_reports_a_created_document_it_could_not_record(
    app_db, monkeypatch
) -> None:
    """문서는 만들어졌는데 기록이 실패하면 URL 을 그대로 보여 준다.

    되돌리려면 방금 만든 문서를 지워야 하는데 그 삭제도 실패할 수
    있어 틈이 한 겹 더 생길 뿐이다. 사람이 링크를 들고 판단한다.
    """
    set_outline_env(monkeypatch)
    monkeypatch.setattr(outline, "create_document", fake_create([]))

    def boom(*args, **kwargs):
        """mark_exported 가 실패하는 상황을 만든다."""
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(run_history, "mark_exported", boom)
    run_history.save_run(app_db, make_result())

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="history_export_1").click().run()

    assert not app.exception
    message = app.error[0].value
    assert "http://192.168.0.10:3000/doc/x" in message
    assert "둘이 됩니다" in message
```

파일 맨 위에 `import sqlite3` 를 더한다.

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/pages/test_history.py -v -k "failure or could_not_record"`
Expected: 앞의 둘은 통과하고(`OutlineError` 는 이미 잡고 있다),
`test_export_reports_a_created_document_it_could_not_record` 는
`app.exception` 이 생겨 FAIL.

- [ ] **Step 3: 구현한다**

`_export` 의 `mark_exported` 호출을 감싼다.

```python
        try:
            run_history.mark_exported(
                connection,
                selected.id,
                document_id=document.id,
                document_title=document.title,
                document_url=document.url,
            )
        except Exception as error:
            # 되돌리지 않는다. 방금 만든 문서를 지우려면 그 삭제도
            # 실패할 수 있어 틈이 한 겹 더 생길 뿐이다. 사실대로
            # 보여 주고 사람이 링크를 들고 판단하게 한다.
            st.error(
                f"문서는 만들어졌습니다: {document.url} —"
                " 로컬 기록에 실패했습니다"
                f"({type(error).__name__})."
                " 다시 저장하면 문서가 둘이 됩니다."
            )
            return
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/pages/test_history.py -v`
Expected: PASS

Run: `uv run pytest -q`
Expected: **287 passed** (284 + 3)

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 전부 통과.

- [ ] **Step 5: 커밋**

```bash
git add src/notebooklm_st/pages/history.py tests/pages/test_history.py
git commit -m "$(cat <<'MSG'
✨ feat(history): 저장 실패를 정직하게 알리기

Outline 이 거부하면 로컬을 손대지 않는다.
문서는 만들어졌는데 기록이 실패한 경우에는
되돌리는 대신 문서 URL 을 그대로 보여 준다 —
되돌리기도 실패할 수 있어 틈만 한 겹 는다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

## Task 12: 배포 설정과 문서

**Files:**
- Modify: `docker-compose.yml`
- Modify: `README.md:11,103-119`
- Modify: `docs/how-to/2026-09-16-homeserver-deploy.md`
- Modify: `docs/superpowers/specs/2026-09-16-headless-auth-design.md:528`

**Interfaces:**
- Consumes: Task 1 의 환경변수 이름 셋
- Produces: 없음 (코드 변경 없음)

- [ ] **Step 1: compose 에 환경변수를 더한다**

`docker-compose.yml` 의 `user:` 줄 아래에 넣는다.

```yaml
    environment:
      # 이미지에 굽지 않는다 — 토큰은 시크릿이다. 값은 배포
      # 디렉터리의 compose 환경 파일에서 온다. 비어 있으면 앱은
      # 뜨되 저장 버튼 자리에 안내가 나온다.
      NOTEBOOKLM_ST_OUTLINE_URL: "${NOTEBOOKLM_ST_OUTLINE_URL:-}"
      NOTEBOOKLM_ST_OUTLINE_TOKEN: "${NOTEBOOKLM_ST_OUTLINE_TOKEN:-}"
      NOTEBOOKLM_ST_OUTLINE_COLLECTION: "${NOTEBOOKLM_ST_OUTLINE_COLLECTION:-}"
```

파일 맨 위의 주석("앱 환경변수는 이미지에 있으므로 여기서 다시 적지
않는다")에 예외를 적는다.

```yaml
# 이미지를 이 호스트에 붙인다. 앱 환경변수는 이미지에 있으므로
# 여기서 다시 적지 않는다 — 두 곳에 적으면 어긋난다. 예외는
# Outline 연결값이다. 토큰이 시크릿이라 이미지에 구울 수 없다.
```

- [ ] **Step 2: 설정이 실제로 전달되는지 확인한다**

```bash
NOTEBOOKLM_ST_OUTLINE_URL=http://example:3000 \
NOTEBOOKLM_ST_OUTLINE_TOKEN=t \
NOTEBOOKLM_ST_OUTLINE_COLLECTION=c \
docker compose config | grep NOTEBOOKLM_ST_OUTLINE
```

Expected: 세 줄이 값과 함께 찍힌다. Docker 가 없는 기기라면 이 단계를
건너뛰고 홈서버 배포 때 확인한다고 적어 둔다.

- [ ] **Step 3: README 를 고친다**

11번 줄의 파이프라인 마지막 단계를 바꾼다.

```markdown
1. 임시 노트북 생성 → 2. 영상 자막을 소스로 추가하고 인덱싱 대기 → 3. 질문마다 질의(앞 대화를 끊어 답변이 서로 물들지 않게 함) → 4. 임시 노트북 삭제 → 5. 결과를 SQLite 에 저장 → 6. 사람이 확인하고 Outline 에 올리면 로컬에는 링크만 남음
```

103번 줄의 사용 흐름 4번을 바꾸고 그 아래 frontmatter 문단을 고친다.

```markdown
4. **이력** 화면에서 답변을 확인하고, 제목을 정한 뒤 **Outline 에 저장**합니다. 저장하면 로컬에는 문서명과 링크만 남고 수정·삭제·검색은 Outline 에서 합니다.

Outline 문서 맨 앞에는 YAML frontmatter 가 붙습니다. 영상명과 URL 은
항상 들어가고, 채널명과 업로드일자는 실행 시점에 yt-dlp 로 가져와
저장해 둔 값이 있을 때만 들어갑니다.

### Outline 연결

| 환경변수 | 값 |
|---|---|
| `NOTEBOOKLM_ST_OUTLINE_URL` | Outline 주소 (예: `http://192.168.0.10:3000`) |
| `NOTEBOOKLM_ST_OUTLINE_TOKEN` | API 토큰. scope 는 `documents.create` 하나면 됩니다 |
| `NOTEBOOKLM_ST_OUTLINE_COLLECTION` | 문서를 넣을 컬렉션 ID (UUID) |

셋 중 하나라도 비면 이력 화면의 저장 버튼 자리에 안내가 나옵니다. 앱은
그대로 뜨고 지난 실행도 읽을 수 있습니다. 발급 절차는
`docs/how-to/2026-09-16-homeserver-deploy.md` 에 있습니다.
```

119번 줄의 주의 문단에 한 줄을 더한다.

```markdown
> **주의**: 이 프로젝트는 DB 마이그레이션을 지원하지 않습니다(의도된 결정). 스키마가 바뀌면 앱이 연결 시점에 안내와 함께 멈추며, 해결책은 DB 파일을 지우고 새로 만드는 것뿐입니다. 이때 질문 템플릿과 실행 이력이 함께 사라집니다. Outline 에 이미 올린 문서는 영향을 받지 않습니다.
```

- [ ] **Step 4: 배포 문서에 "Outline 연결하기" 절을 더한다**

`docs/how-to/2026-09-16-homeserver-deploy.md` 의 "## 4. 기존 데이터 옮기기
(선택)" 를 통째로 아래로 바꾼다. R4 는 옛 이력을 버리므로 그 절은 더
이상 맞지 않는다.

````markdown
## 4. Outline 연결하기

요약본은 Outline 에 저장된다. 앱에는 문서명과 링크만 남는다.

### 4.1 API 키 만들기

Outline 웹에서 **프로필 → Settings → API Keys → New API Key**.

- **Scopes** 에 `documents.create` 만 넣는다. 앱이 부르는 엔드포인트는
  그것 하나뿐이라, 키가 새더라도 읽기·삭제·사용자 조회가 막힌다.
- 키 값은 만든 직후 한 번만 보인다. 바로 복사한다.

키는 **만든 사용자의 권한을 상속한다.** "이 컬렉션에만" 이라는 범위
지정은 없으므로, 컬렉션 단위로 가두려면 그 컬렉션에만 접근 가능한
사용자를 따로 만들어 그 사용자로 키를 발급해야 한다.

### 4.2 컬렉션 ID 찾기

`collectionId` 는 UUID 다. 화면 주소의 슬러그와 다르므로 API 로
확인한다. 이 조회에만 scope 를 넓힌 임시 키가 필요하고, 확인이 끝나면
지운다.

```bash
read -rs OUTLINE_TOKEN   # 화면에 안 찍히고 히스토리에도 안 남는다
curl -s -X POST http://localhost:3000/api/collections.list \
  -H "Authorization: Bearer $OUTLINE_TOKEN" \
  -H "Content-Type: application/json" -d '{}' \
  | python3 -c 'import json,sys; [print(c["id"], c["name"]) for c in json.load(sys.stdin)["data"]]'
```

### 4.3 값 넣기

1 절에서 만든 compose 환경 파일에 세 줄을 더한다. 이 파일은
`.gitignore` 와 `.dockerignore` 에 이미 들어 있어 저장소나 이미지로
새지 않는다.

```bash
cat >> .env <<'EOF'
NOTEBOOKLM_ST_OUTLINE_URL=http://192.168.0.10:3000
NOTEBOOKLM_ST_OUTLINE_TOKEN=<복사한 키>
NOTEBOOKLM_ST_OUTLINE_COLLECTION=<위에서 찾은 UUID>
EOF
docker compose up -d
```

셋 중 하나라도 비면 앱은 그대로 뜨고 이력 화면의 저장 버튼 자리에
안내만 나온다.

### 4.4 옛 DB 지우기

R4 는 `runs` 테이블에 컬럼을 넷 더한다. 이 프로젝트는 마이그레이션을
두지 않으므로 **R4 이전 `questions.db` 는 열리지 않는다.** 앱이 연결
시점에 안내와 함께 멈춘다.

```bash
docker compose down
rm data/questions.db
docker compose up -d
```

질문 템플릿도 함께 사라진다. 질문 관리 화면에서 다시 등록한다.
````

같은 파일 "## 5. 검증" 의 표에 줄 하나를 더한다.

```markdown
| 9 | 이력에서 실행 하나를 Outline 에 저장 | 문서가 컬렉션에 생기고, 이력이 링크 한 줄로 바뀐다 |
```

8번 줄의 통과 기준에서 "이력" 을 뺀다. 이력은 이제 링크 목록이다.

```markdown
| 8 | `docker compose down && docker compose up -d` | 질문·문서 링크·인증이 보존된다 |
```

- [ ] **Step 5: R1 스펙의 예고를 정정한다**

`docs/superpowers/specs/2026-09-16-headless-auth-design.md` 의 §7.3
마지막 괄호 문장을 바꾼다.

```markdown
`schema_gate` 와 대비된다. 스키마가 깨지면 모든 화면이 죽지만 인증 만료는
일부 화면만 못 쓴다. (R4 에서 이력이 Outline 을 읽게 되면 전제가 바뀔
것으로 보았으나, R4 는 문서명과 URL 을 로컬에 적어 두는 쪽을 택해 이력
목록에 Outline 호출이 없다. 전제는 그대로다.)
```

- [ ] **Step 6: 예고가 남아 있지 않은지 확인한다**

```bash
grep -rn "R4 에서 이력이 Outline 을 읽게 되면 이 전제가 바뀐다" docs/; echo "종료코드 $?"
```

Expected: 아무것도 찍히지 않고 `종료코드 1`.

- [ ] **Step 7: 전체 검증**

Run: `uv run pytest -q`
Expected: **287 passed** (문서만 고쳤으므로 Task 11 과 같다)

Run: `uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: 전부 통과. ruff 는 마크다운을 대상에서 빼므로 문서 변경이
포맷을 건드리지 않는다.

- [ ] **Step 8: 커밋**

```bash
git add docker-compose.yml README.md docs/
git commit -m "$(cat <<'MSG'
📝 docs: Outline 연결 절차와 저장 흐름 반영

compose 가 연결값 셋을 넘긴다. 토큰이 시크릿이라
이미지에 구울 수 없어, 환경변수를 이미지에만
둔다는 원칙에 예외를 하나 둔다.

배포 문서의 "기존 데이터 옮기기" 를 "Outline
연결하기" 로 바꾼다. R4 는 옛 이력을 버리므로
옮길 것이 없다.

Assisted-by: <자기 모델 ID>
MSG
)"
```

---

## 완료 조건

R4 가 끝나면 아래가 모두 참이어야 한다.

- [ ] 이력에서 미저장 실행을 고르면 **문서 제목 입력**과 **인용 포함**
      체크박스, **Outline 에 저장** 버튼이 보인다
- [ ] 저장을 누르면 Outline 컬렉션에 문서가 생기고, 그 문서의 맨 앞에
      `title`·`channel`·`upload_date`·`url` 이 든 frontmatter 가 있다
- [ ] 문서 본문에 **제목이 두 번 나오지 않는다**(H1 없음)
- [ ] 저장 뒤 같은 실행을 고르면 **문서명과 링크만** 보이고 답변 카드가
      없다
- [ ] 저장 뒤 목록 라벨이 `… · 문서` 로 끝난다
- [ ] Outline 을 끄고 저장을 누르면 **연결 실패 메시지**가 뜨고, 그
      실행은 여전히 미저장으로 남아 다시 시도할 수 있다
- [ ] Outline 을 끈 채로도 **이력 화면 자체는 뜬다**
- [ ] 환경변수 셋을 비우면 저장 버튼 대신 안내가 나오고 앱은 정상
      동작한다
- [ ] R4 이전 `questions.db` 를 열면 `StaleSchemaError` 안내가 뜬다
- [ ] 앱 어디에도 답변 편집 상자와 마크다운 내려받기 버튼이 없다
- [ ] `uv run pytest` 가 전부 통과하고 테스트 수가 **268개(R3 종료
      시점)보다 많다**
- [ ] `uv run ruff check .` 와 `uv run mypy src` 가 통과한다

## R5 로 넘기는 것

| 것 | 상태 |
|---|---|
| `outline_id` | `runs` 에 적힌다. `documents.info` 로 문서를 다시 읽을 때 쓴다 |
| `services/outline.py` | 쓰기만 있다. 읽기는 R5 가 더한다 |
| API 키 scope | `documents.create` 하나다. 읽기를 더하면 scope 도 넓혀야 한다 |
| 컬렉션 구조 | 평평하다. 정리본을 같은 컬렉션에 둘지는 R5 가 정한다 |
| frontmatter | 문서에 그대로 실린다. 정리본이 파싱할 자리다 |
| 미검증 가정 셋 | 스펙 13절. 첫 문서를 올릴 때 눈으로 확인한다 |
