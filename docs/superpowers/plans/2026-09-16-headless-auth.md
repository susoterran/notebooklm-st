# 무인 갱신 인증 전환 (R1) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 앱이 인증을 시작하는 능력(브라우저 로그인)을 걷어내고, 자격증명을 받는 능력(업로드)을 넣어 컨테이너에서 동작할 수 있게 만든다.

**Architecture:** `services/auth.py` 의 `AuthGate` 를 확인 전용으로 축소하고 `recheck()`·`probe_error` 를 더한다. 자격증명 반입은 공개 CLI(`notebooklm auth import-cookies -`)를 자식 프로세스로 부른다. 만료 문구는 `core/errors.py` 한 곳을 정본으로 삼고, `components/auth_gate.py` 가 배너·다시 확인·업로더를 그린다.

**Tech Stack:** Python 3.13, Streamlit 1.62, notebooklm-py 0.8.1, pytest, mypy, ruff, uv

**Spec:** `docs/superpowers/specs/2026-09-16-headless-auth-design.md`

## Global Constraints

- **Python** `>=3.13` (`pyproject.toml` `requires-python`)
- **ruff**: `line-length = 80`, `select = ["E","W","F","I","N","D","UP","B","SIM","ANN","RUF"]`, `pydocstyle convention = "google"`
- **docstring 필수** — `D` 규칙이 켜져 있어 **테스트 함수·헬퍼 클래스·메서드에도 docstring 이 있어야 한다.** 기존 테스트가 전부 그렇게 되어 있다. 한국어로 쓴다.
- **mypy**: `notebooklm_st.core.*` 와 `notebooklm_st.services.*` 는 `disallow_untyped_defs = true`. 이 두 곳의 모든 함수에 타입 주석을 붙인다.
- **`tests/**` 는 `ANN` 만 면제**된다(`per-file-ignores`). 타입 주석은 생략해도 되지만 docstring 은 필요하다. 기존 테스트는 `-> None` 을 붙이는 관례를 따르므로 그대로 따른다.
- **경계 규칙**: `core/` 와 `services/` 는 `import streamlit` 을 하지 않는다 (README 에 명시된 이 프로젝트의 규칙).
- **import 는 모듈 단위로** (`.claude/rules/streamlit-implement.md` §4.1) — 개별 클래스·함수를 import 하지 않고 모듈을 import 해 정규화된 이름으로 쓴다. `import dataclasses` 뒤 `@dataclasses.dataclass`, `from notebooklm_st.services import auth` 뒤 `auth.import_credentials`. **예외로 허용**: `typing`, `collections.abc`, `typing_extensions` 에서의 심볼 import(`from collections.abc import Callable` 는 괜찮다). **ruff 가 검사하지 않으므로 사람이 지킨다.**
- **독스트링과 주석은 72자**에서 줄바꿈한다(코드는 80자). 같은 규칙 §4.2.
- **`# noqa` 는 규칙 코드를 반드시 명시**한다(`# noqa: E501`). 맨 `# noqa` 금지.
- **의존성 조작은 `uv add` · `uv add --dev` · `uv remove` 로만** 한다(§1). `uv.lock` 은 커밋 대상이며 손으로 편집하지 않는다.
- **`except Exception:` 은 원칙적으로 금지**(§4.4). 이 계획에서 딱 한 곳 예외를 둔다 — Task 2 의 `AuthGate._verify()`. 근거와 판단은 Task 2 배경에 적었다.
- 함수가 40줄을 넘으면 분리를 검토한다. 한 파일이 300줄을 넘으면 경계를 기준으로 나눈다.
- **검증 4단** — 모든 커밋 전에 순서대로 돌린다.
  ```
  uv run ruff format .
  uv run ruff check --fix .
  uv run mypy src tests
  uv run pytest
  ```
- **`uv` 가 PATH 에 없을 수 있다.** 그럴 때는 전체 경로로 부른다: `C:\Users\susot\.local\bin\uv.exe run ...`
- **커밋 규약** (`.claude/rules/commit-strategy.md`): 헤더는 `<emoji> <type>(<scope>): <subject>`, subject 는 **한국어·명령형·마침표 없음·≤50자**. 마지막 줄에 `Assisted-by: claude-opus-5`. `Co-Authored-By:` 는 붙이지 않는다.
- **`git push` 금지.** 커밋만 한다. push 와 PR 은 사람이 한다.
- 현재 브랜치는 `develop` 이다. `master` 에 직접 커밋하지 않는다.

---

## File Structure

| 파일 | 책임 | 이 계획에서 |
|---|---|---|
| `src/notebooklm_st/core/errors.py` | 라이브러리 예외 → 화면 문구. **만료 문구의 정본** | Task 1 |
| `src/notebooklm_st/services/auth.py` | 인증이 살아 있는지 **판정**. 자격증명 **반입**. 문구를 만들지 않음 | Task 2·3·4 |
| `src/notebooklm_st/components/auth_gate.py` | 판정 결과를 **그림**. 문구는 `errors` 에서 | Task 2·5 |
| `tests/conftest.py` | `stub_auth_gate` fixture | Task 2 |
| `tests/services/test_auth.py` | 판정·반입 테스트 | Task 2·3·4 |
| `tests/test_components.py` | 게이트 화면 테스트 | Task 2·5 |
| `tests/core/test_errors.py` | 문구 매핑 테스트 | Task 1 |
| `pyproject.toml` | `[browser]` 를 dev 그룹으로 | Task 6 |
| `README.md` | 인증 서술 4곳 | Task 7 |
| `docs/how-to/2026-09-16-auth-reseed.md` | 재시드 절차서 (신규) | Task 7 |

**스펙 §9.5 와의 차이 하나.** 스펙은 "2. recheck 추가 → 3. 삭제" 순서였다. 그런데 `AuthGate` 에서 `login` 인자를 빼는 순간 `components/auth_gate.py` 와 `tests/conftest.py` 가 함께 깨진다. 그래서 **Task 2 가 그 셋을 한 번에 처리**하고, Task 3 은 그 뒤에 남는 순수한 죽은 코드(`run_login` 일가)만 지운다. 각 Task 가 끝날 때마다 테스트가 전부 초록이어야 한다는 원칙을 지키기 위한 조정이다.

---

### Task 1: 만료 문구를 `core/errors.py` 한 곳으로

**Files:**
- Modify: `src/notebooklm_st/core/errors.py:44-47`
- Test: `tests/core/test_errors.py`

**Interfaces:**
- Consumes: 없음 (첫 작업)
- Produces: `notebooklm_st.core.errors.LOGIN_HINT: str` — 만료 안내 문구의 정본. Task 2·5 의 `components/auth_gate.py` 가 이것을 그린다.

**배경:** 지금 만료 안내가 두 곳에 있고 **둘 다 틀리게 된다.**
- `core/errors.py:44` `_LOGIN_HINT` — "터미널에서 `uv run notebooklm login`". 컨테이너에는 터미널도 `uv` 도 없다.
- `components/auth_gate.py:15` `_EXPIRED_HINT` — "브라우저 창이 열립니다". 더 이상 안 열린다.

이 Task 는 앞의 것을 공개 상수로 올리고 문구를 바꾼다. 뒤의 것은 Task 2 에서 지운다.

- [ ] **Step 1: 실패하는 테스트로 바꾸기**

`tests/core/test_errors.py` 의 세 테스트를 문구 리터럴 대신 상수를 참조하게 고친다. 문구가 또 바뀌어도 테스트가 따라온다.

```python
def test_auth_error_tells_user_to_log_in_again() -> None:
    """인증 오류는 재로그인 안내 정본을 그대로 쓴다."""
    message = errors.to_message(exceptions.AuthError("expired"))
    assert message.level == "error"
    assert message.text == errors.LOGIN_HINT


def test_headless_login_required_tells_user_to_log_in_again() -> None:
    """헤드리스 로그인 필요 오류도 같은 정본을 쓴다."""
    message = errors.to_message(
        exceptions.HeadlessLoginRequiredError("dead session")
    )
    assert message.level == "error"
    assert message.text == errors.LOGIN_HINT


def test_login_redirect_tells_user_to_log_in_again() -> None:
    """로그인 리다이렉트도 같은 정본을 쓴다."""
    message = errors.to_message(
        _auth_extraction._LoginRedirectError("https://accounts.google.com/...")
    )
    assert message.level == "error"
    assert message.text == errors.LOGIN_HINT
```

세 번째 테스트는 파일에 이미 있다(`tests/core/test_errors.py:92`). 기존 본문을 위 내용으로 교체한다 — 예외 생성 인자는 기존 파일에 적힌 것을 그대로 쓰고, `assert` 두 줄만 바꾼다.

새 테스트를 하나 더 추가한다.

```python
def test_login_hint_points_at_the_reseed_document() -> None:
    """만료 안내는 절차 문서를 가리킨다."""
    assert "auth-reseed" in errors.LOGIN_HINT
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/core/test_errors.py -v`
Expected: FAIL — `AttributeError: module 'notebooklm_st.core.errors' has no attribute 'LOGIN_HINT'`

- [ ] **Step 3: 상수 승격과 문구 교체**

`src/notebooklm_st/core/errors.py` 에서 `_LOGIN_HINT` 정의(44-47행)를 아래로 교체한다.

```python
LOGIN_HINT = (
    "인증이 만료되었습니다. 데스크톱에서"
    " `uv run notebooklm login` 으로 다시 로그인한 뒤, 만들어진"
    " storage_state.json 을 인증 배너에서 올리세요."
    " 절차: docs/how-to/2026-09-16-auth-reseed.md"
)
"""만료 안내 문구의 정본.

화면(``components/auth_gate.py``)과 실행 실패 메시지가 같은 문구를
쓴다. 두 곳에 따로 두면 한쪽만 고쳐져 어긋난다.
"""
```

같은 파일에서 `_LOGIN_HINT` 를 참조하는 곳(`to_message` 안의 `return UserMessage(_LOGIN_HINT, "error")`)을 `LOGIN_HINT` 로 바꾼다.

> 문구가 `components/auth_gate.py` 가 아니라 실행 현황 화면에서도 보인다. 그래서 "아래에서 올리세요" 가 아니라 **"인증 배너에서 올리세요"** 로 쓴다. 어느 화면에서 읽어도 갈 곳을 알 수 있다.

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/core/test_errors.py -v`
Expected: PASS (12개)

- [ ] **Step 5: 검증 4단**

```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```
Expected: 전부 통과. 이 시점에는 `components/auth_gate.py` 가 아직 자기 문구를 쓰므로 전체 테스트가 초록이어야 한다.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/core/errors.py tests/core/test_errors.py
git commit -m "$(cat <<'EOF'
♻️ refactor(errors): 만료 안내 문구를 정본 상수로 승격

터미널에서 uv 를 실행하라는 안내는 컨테이너에서 틀린
지시가 된다. 데스크톱 재로그인과 업로드를 가리키도록
바꾸고, 화면과 실행 실패가 같은 문구를 쓰도록 공개
상수로 올렸다.

Assisted-by: claude-opus-5
EOF
)"
```

---

### Task 2: `AuthGate` 를 확인 전용으로 바꾸기

**Files:**
- Modify: `src/notebooklm_st/services/auth.py:143-237` (`AuthGate` 클래스)
- Modify: `src/notebooklm_st/components/auth_gate.py` (전체 재작성)
- Modify: `tests/conftest.py:30`
- Test: `tests/services/test_auth.py:176-267`, `tests/test_components.py:326-381`

**Interfaces:**
- Consumes: `notebooklm_st.core.errors.LOGIN_HINT` (Task 1)
- Produces:
  - `AuthGate.__init__(self, probe: ProbeLike = is_authenticated) -> None` — `login` 인자 없음
  - `AuthGate.ensure(self) -> bool` — 인자 없음. 프로세스당 1회만 확인
  - `AuthGate.recheck(self) -> bool` — 인자 없음. 캐시를 버리고 다시 확인
  - `AuthGate.probe_error` (property) `-> Exception | None`
  - `components.auth_gate.render() -> bool`

**배경:** `relogin()` 을 그냥 지우면 안 된다. 그 docstring 이 적어 둔 역할 — *"그 사이 다른 경로로 인증이 되살아날 수 있다(터미널 로그인…)"* — 이 **재시드 절차 그 자체**다. 프로필을 갈아 끼운 뒤 앱이 알아챌 경로가 없으면 컨테이너 재시작이 유일한 회복 수단이 된다. `recheck()` 가 그 자리를 대신한다.

`probe_error` 가 필요한 이유는 스펙 §5.3 이다. 보관하지 않으면 "확인 불가" 가 첫 렌더에만 보이고, 재실행 후에는 `_tried` 가 True 라 예외가 다시 안 올라와 **만료 배너로 바뀐다.**

**`except Exception` 에 대한 판단.** `.claude/rules/streamlit-implement.md` §4.4 는 맨 `except Exception:` 을 금지한다. `_verify()` 는 이 계획에서 유일한 예외다. 근거 셋:

1. `is_authenticated()` 는 **매핑하지 못한 예외를 일부러 올린다.** 그 집합은 열려 있어 좁게 잡을 수 없다. 좁게 잡으려 하면 `probe_error` 라는 장치 자체가 성립하지 않는다.
2. **같은 패턴이 이미 코드베이스에 있다.** `services/runner.py:96` 이 스레드 최상위에서 `except Exception as error:` 를 쓰고, "여기서 예외가 새면 화면이 영원히 '실행 중' 에 머문다" 는 주석을 달아 두었다. `_verify()` 도 같은 성질의 경계다 — 새면 화면에 트레이스백이 뜬다.
3. 스펙 §5.3 이 이 코드를 그대로 명시하고 사용자 검토를 통과했다.

**반드시 지킬 것:** `runner.py` 와 같이 **바로 위에 이유를 적은 주석**을 단다. 주석 없는 광범위 catch 는 규칙 위반이다.

- [ ] **Step 1: 게이트 테스트 재작성**

`tests/services/test_auth.py` 의 176행부터 끝까지(`Recorder` 클래스 이후 전부)를 아래로 교체한다. `Recorder` 와 `make_gate` 도 함께 바뀐다.

```python
class Recorder:
    """호출 횟수를 세는 가짜 probe.

    결과 목록에 예외를 섞어 두면 그 차례에 그 예외를 던진다.
    """

    def __init__(self, results):
        """돌려줄 결과 목록을 저장한다."""
        self._results = list(results)
        self.calls = 0

    def __call__(self):
        """다음 결과를 돌려주거나 던지고 호출을 센다."""
        self.calls += 1
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_gate(probe_results):
    """정해진 결과를 내는 게이트와 그 가짜 probe 를 만든다."""
    probe = Recorder(probe_results)
    return auth.AuthGate(probe=probe), probe


def test_gate_checks_only_once() -> None:
    """앱이 떠 있는 동안 자동 확인은 한 번만 돈다."""
    gate, probe = make_gate([True])

    gate.ensure()
    gate.ensure()

    assert probe.calls == 1


def test_gate_caches_the_probe_result() -> None:
    """두 번째 ensure 는 캐시된 판정을 그대로 돌려준다."""
    gate, _ = make_gate([True])

    assert gate.ensure() is True
    assert gate.ensure() is True
    assert gate.ok is True


def test_gate_reports_whether_it_has_run() -> None:
    """자동 확인을 이미 돌렸는지 알려 준다."""
    gate, _ = make_gate([True])

    assert gate.tried is False
    gate.ensure()
    assert gate.tried is True


def test_recheck_probes_again_ignoring_the_cache() -> None:
    """다시 확인은 캐시를 무시하고 probe 를 또 부른다."""
    gate, probe = make_gate([False, False])
    gate.ensure()

    gate.recheck()

    assert probe.calls == 2


def test_recheck_revives_a_failed_gate() -> None:
    """프로필을 갈아 끼운 뒤 다시 확인하면 인증이 되살아난다."""
    gate, _ = make_gate([False, True])
    assert gate.ensure() is False

    assert gate.recheck() is True
    assert gate.ok is True


def test_gate_records_a_failed_probe() -> None:
    """확인 자체가 실패하면 예외를 보관하고 만료로 본다."""
    boom = RuntimeError("boom")
    gate, _ = make_gate([boom])

    assert gate.ensure() is False
    assert gate.probe_error is boom


def test_gate_keeps_the_probe_error_cached() -> None:
    """재실행으로 ensure 를 또 불러도 확인 불가 상태가 남는다."""
    boom = RuntimeError("boom")
    gate, probe = make_gate([boom])
    gate.ensure()

    gate.ensure()

    assert probe.calls == 1
    assert gate.probe_error is boom


def test_recheck_clears_a_stale_probe_error() -> None:
    """되살아나면 보관하던 예외도 지운다."""
    gate, _ = make_gate([RuntimeError("boom"), True])
    gate.ensure()

    assert gate.recheck() is True
    assert gate.probe_error is None
```

`tests/services/test_auth.py` 의 175행까지(모듈 docstring, import, `FakeStdout`, `FakeProcess`, `fake_popen_factory`, `factory_yielding_client`, `factory_raising`, `test_probe_*` 3개, `test_login_*` 7개)는 **이 Task 에서 건드리지 않는다.** Task 3 이 지운다.

- [ ] **Step 2: 컴포넌트 테스트 재작성**

`tests/test_components.py:340-381` 의 두 테스트(`test_auth_gate_offers_relogin_when_recovery_fails`, `test_auth_gate_relogins_when_the_button_is_pressed`)를 아래 셋으로 교체한다.

```python
def test_auth_gate_offers_recheck_when_expired(monkeypatch) -> None:
    """만료되면 안내와 다시 확인 버튼을 보여 준다."""
    gate = auth.AuthGate(probe=lambda: False)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    def script():
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.error) == 1
    assert app.button(key="auth_gate_recheck") is not None


def test_auth_gate_rechecks_when_the_button_is_pressed(monkeypatch) -> None:
    """다시 확인 버튼은 브라우저 없이 판정만 다시 돌린다."""
    calls = []

    def probe() -> bool:
        """호출을 세고 계속 만료로 답한다."""
        calls.append(1)
        return False

    gate = auth.AuthGate(probe=probe)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    def script():
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key="auth_gate_recheck").click().run()

    assert not app.exception
    assert len(calls) == 2


def test_auth_gate_separates_a_failed_probe_from_an_expiry(monkeypatch):
    """확인 자체가 실패하면 만료가 아니라 확인 불가로 알린다."""

    def probe() -> bool:
        """매핑되지 않은 예외를 던진다."""
        raise RuntimeError("boom")

    gate = auth.AuthGate(probe=probe)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    def script():
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.error) == 1
    assert "확인하지 못했습니다" in app.error[0].value
    assert errors.LOGIN_HINT not in app.error[0].value
```

세 번째 테스트는 `errors` 를 쓰므로 `tests/test_components.py` 상단 import 에 `from notebooklm_st.core import errors` 를 추가한다(이미 있으면 그대로 둔다).

- [ ] **Step 3: conftest fixture 고치기**

`tests/conftest.py:30` 의 한 줄을 바꾼다.

```python
    gate = auth.AuthGate(probe=lambda: True)
```

같은 fixture 의 docstring 에서 "실패하면 브라우저 창까지 뜬다" 는 더 이상 사실이 아니다. 아래로 바꾼다.

```python
    """테스트가 실제 인증을 건드리지 않게 막는다.

    화면 테스트는 앱 진입점을 그대로 돌린다. 막지 않으면 인증 확인이
    네트워크를 탄다.
    """
```

- [ ] **Step 4: 실패 확인**

Run: `uv run pytest tests/services/test_auth.py tests/test_components.py -v`
Expected: FAIL. 두 가지 오류가 섞여 나온다.
- `TypeError: ensure() missing 1 required positional argument: 'on_progress'` — 새 테스트가 인자 없이 부른다
- `AttributeError: 'AuthGate' object has no attribute 'recheck'`

- [ ] **Step 5: `AuthGate` 구현**

`src/notebooklm_st/services/auth.py` 의 `AuthGate` 클래스(143행부터 `_verify` 끝까지)를 아래로 교체한다.

```python
class AuthGate:
    """앱이 떠 있는 동안 인증 확인을 한 번만 돌리기 위한 표식.

    Streamlit 은 세션마다 다른 스레드에서 스크립트를 돌리고, 스크립트는
    상호작용마다 처음부터 다시 실행된다. 표식이 없으면 재실행마다
    느린 네트워크 확인이 돌고, 잠금이 없으면 탭 두 개가 동시에 확인을
    시작한다.
    """

    def __init__(self, probe: ProbeLike = is_authenticated) -> None:
        """확인 함수를 받아 둔다.

        Args:
            probe: 인증이 살아 있는지 확인하는 함수.
        """
        self._probe = probe
        self._lock = threading.Lock()
        self._tried = False
        self._ok = False
        self._probe_error: Exception | None = None

    @property
    def ok(self) -> bool:
        """마지막 확인 결과. 한 번도 확인하지 않았으면 ``False``."""
        return self._ok

    @property
    def tried(self) -> bool:
        """자동 확인을 이미 돌렸는지 여부.

        화면이 이 값을 보고 진행 표시를 그릴지 정한다. 재실행마다 다시
        그리면 아무 일도 없는데 화면이 깜빡인다.
        """
        return self._tried

    @property
    def probe_error(self) -> Exception | None:
        """확인 **자체**가 실패했을 때 그 예외.

        만료(``ok`` 가 ``False``)와 구분된다. 만료는 사람이 재시드로
        풀 수 있지만, 확인 불가는 라이브러리 구조 변경 같은 다른
        원인이라 안내가 달라야 한다. 보관해 두지 않으면 재실행 뒤
        ``_tried`` 때문에 예외가 다시 올라오지 않아 만료로 오인된다.
        """
        return self._probe_error

    def ensure(self) -> bool:
        """처음 한 번만 인증을 확인한다.

        Returns:
            인증이 쓸 수 있는 상태면 ``True``.
        """
        with self._lock:
            if self._tried:
                return self._ok
            return self._verify()

    def recheck(self) -> bool:
        """캐시를 버리고 다시 확인한다.

        사용자가 데스크톱에서 재로그인해 자격증명을 갈아 끼운 뒤
        부른다. 실패 판정은 이 객체가 프로세스가 끝날 때까지 들고
        있으므로, 이 경로가 없으면 회복하는 유일한 방법이 프로세스
        재시작이 된다.

        Returns:
            인증이 쓸 수 있는 상태면 ``True``.
        """
        with self._lock:
            return self._verify()

    def _verify(self) -> bool:
        """확인하고 결과를 기록한다.

        호출자가 ``self._lock`` 을 쥔 채로 불러야 한다.

        Returns:
            인증이 쓸 수 있는 상태면 ``True``.
        """
        self._tried = True
        self._probe_error = None
        try:
            self._ok = self._probe()
        except Exception as error:
            # 게이트에서만 넓게 잡는다. 여기서 새면 화면에 트레이스백이
            # 뜨고 사용자는 무엇이 잘못됐는지 알 수 없다.
            # runner._work 와 같은 근거다.
            logger.exception("인증 확인 실패")
            self._ok = False
            self._probe_error = error
        return self._ok
```

파일 상단에 로거를 추가한다(아직 없다).

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 6: `components/auth_gate.py` 재작성**

파일 전체를 아래로 교체한다. 업로더는 아직 넣지 않는다 — Task 5 가 넣는다.

```python
"""인증 상태를 확인하고 만료를 안내하는 조각.

앱이 뜰 때 한 번 돌고, 인증이 만료된 동안에만 화면에 남는다.
브라우저 로그인은 하지 않는다. 자격증명은 사람이 데스크톱에서
만들어 온다(→ ``core.errors.LOGIN_HINT``).
"""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import errors

_RECHECK_KEY = "auth_gate_recheck"


def render() -> bool:
    """인증을 확인하고 결과를 그린다.

    앱이 뜬 뒤 첫 실행에서만 확인한다. 확인 자체가 라이브러리의 토큰
    재추출과 쿠키 회전을 태우므로, 대개는 사용자가 아무것도 하지
    않아도 여기서 끝난다.

    만료와 "확인 자체가 실패" 를 구분해 그린다. 앞은 사람이 재시드로
    풀 수 있고, 뒤는 원인이 다르다.

    Returns:
        인증을 쓸 수 있으면 ``True``.
    """
    gate = session.get_auth_gate()
    if not gate.tried:
        with st.spinner("인증 상태 확인 중"):
            gate.ensure()
    if gate.ok:
        return True

    _render_notice(gate.probe_error)
    if st.button("다시 확인", key=_RECHECK_KEY):
        with st.spinner("다시 확인 중"):
            if gate.recheck():
                st.rerun()
    return gate.ok


def _render_notice(probe_error: Exception | None) -> None:
    """만료인지 확인 불가인지 가려 안내를 그린다.

    Args:
        probe_error: 확인 자체가 실패했을 때 그 예외. 만료면 ``None``.
    """
    if probe_error is None:
        st.error(errors.LOGIN_HINT)
        return
    st.error(
        "인증 상태를 확인하지 못했습니다"
        f"({type(probe_error).__name__}: {probe_error})"
    )
```

- [ ] **Step 7: 통과 확인**

Run: `uv run pytest tests/services/test_auth.py tests/test_components.py -v`
Expected: PASS. `test_login_*` 7개는 아직 남아 있고 그대로 통과한다(`run_login` 을 아직 안 지웠다).

- [ ] **Step 8: 검증 4단**

```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```
Expected: 전부 통과.

- [ ] **Step 9: 커밋**

```bash
git add src/notebooklm_st/services/auth.py \
        src/notebooklm_st/components/auth_gate.py \
        tests/conftest.py tests/services/test_auth.py tests/test_components.py
git commit -m "$(cat <<'EOF'
♻️ refactor(auth): 게이트를 확인 전용으로 바꾸기

브라우저 로그인 대신 다시 확인을 둔다. 데스크톱에서
자격증명을 갈아 끼운 뒤 앱이 알아챌 경로가 없으면
프로세스 재시작이 유일한 회복 수단이 되기 때문이다.

확인 자체가 실패한 경우를 probe_error 로 보관해
만료와 구분한다. 보관하지 않으면 재실행 뒤 만료로
오인된다.

Assisted-by: claude-opus-5
EOF
)"
```

---

### Task 3: 브라우저 로그인 기계 걷어내기

**Files:**
- Modify: `src/notebooklm_st/services/auth.py:1-141` (상단 전부)
- Test: `tests/services/test_auth.py:1-174`

**Interfaces:**
- Consumes: Task 2 의 `AuthGate` (이제 `login` 을 받지 않으므로 `run_login` 에 호출자가 없다)
- Produces: 없음 (순수 삭제)

**배경:** Task 2 로 `run_login` 의 마지막 호출자가 사라졌다. 이제 아무도 안 쓰는 코드와 그 테스트를 지운다. `import subprocess`·`import sys` 도 **여기서는 함께 지운다** — 이 시점에 쓰는 곳이 없어 ruff 가 `F401` 로 잡는다. Task 4 가 필요한 것만 다시 들여온다.

- [ ] **Step 1: 죽은 테스트 지우기**

`tests/services/test_auth.py` 에서 아래를 지운다.

| 대상 | 위치 |
|---|---|
| `FakeStdout` 클래스 | 13행 |
| `FakeProcess` 클래스 | 25행 |
| `fake_popen_factory` 함수 | 48행 |
| `test_login_runs_current_interpreter` | 105행 |
| `test_login_reports_each_output_line` | 116행 |
| `test_login_succeeds_on_zero_exit` | 127행 |
| `test_login_fails_on_nonzero_exit` | 134행 |
| `test_login_kills_child_on_timeout` | 141행 |
| `test_login_reports_the_exit_code_when_the_child_says_nothing` | 153행 |
| `test_login_reports_the_timeout` | 164행 |

상단 import 에서 `import subprocess` 와 `import sys` 를 지운다.

**남는 것:** 모듈 docstring, `import contextlib`, `import pytest`, `from notebooklm._auth import extraction as auth_extraction`, `from notebooklm_st.services import auth`, `factory_yielding_client`, `factory_raising`, `test_probe_*` 3개, 그리고 Task 2 가 쓴 게이트 테스트 전부.

- [ ] **Step 2: 실패 확인**

Run: `uv run ruff check tests/services/test_auth.py`
Expected: 통과(지운 것만 있으므로). 아직 `src` 는 안 건드렸으니 `uv run pytest tests/services/test_auth.py -v` 도 PASS 여야 한다. 이 단계는 "지워도 초록"을 확인하는 것이다.

- [ ] **Step 3: 죽은 코드 지우기**

`src/notebooklm_st/services/auth.py` 에서 아래를 지운다.

| 대상 | 이유 |
|---|---|
| `LOGIN_TIMEOUT` 상수 + docstring | 기다릴 자식이 없다 |
| `CHECK_NOTICE` 상수 + docstring | 진행 문구를 흘릴 단계가 없다 |
| `ProcessLike` Protocol | 자식 프로세스가 없다 |
| `PopenLike` 타입 별칭 | 〃 |
| `LoginLike` 타입 별칭 | `AuthGate` 가 안 받는다 |
| `run_login()` 함수 전체 | 호출자가 없다 |
| `import subprocess`, `import sys`, `import time` | 쓰는 곳이 없다 |
| `from collections.abc import ... Iterable` | `ProcessLike` 만 썼다 |
| `from typing import Protocol` | `ProcessLike` 만 썼다 |

모듈 docstring 도 고친다. 현재 내용이 브라우저 로그인을 설명한다.

```python
"""인증 상태 확인.

라이브러리는 만료된 인증을 스스로 되살리려 토큰 재추출과 쿠키 회전을
시도한다. 클라이언트를 여는 것만으로 그 복구가 돌기 때문에, 이 모듈은
열어 보는 것으로 확인을 대신한다.

그 복구가 실패하면 사람이 데스크톱에서 다시 로그인해 자격증명을
가져와야 한다. 앱은 브라우저를 띄우지 않는다.
"""
```

**남는 것:** `asyncio`, `logging`, `threading` import, `Callable` import, `ProbeLike`, `is_authenticated`, `AuthGate`, `_open_once`, `logger`.

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest -v`
Expected: PASS 전부.

- [ ] **Step 5: 검증 4단**

```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```
Expected: 전부 통과. `ruff check` 가 남은 unused import 를 잡으면 지운다.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/services/auth.py tests/services/test_auth.py
git commit -m "$(cat <<'EOF'
🔥 remove(auth): 브라우저 로그인 경로 삭제

컨테이너에는 playwright 도 화면도 로그인을 마칠
사람도 없어 이 경로는 무조건 실패한다. 게이트가
쓰지 않게 된 run_login 과 자식 프로세스 기계를
테스트까지 함께 지웠다.

Assisted-by: claude-opus-5
EOF
)"
```

---

### Task 4: 자격증명 반입 — `import_credentials()`

**Files:**
- Modify: `src/notebooklm_st/services/auth.py` (함수 추가)
- Test: `tests/services/test_auth.py` (테스트 추가)

**Interfaces:**
- Consumes: 없음 (독립 함수)
- Produces:
  - `auth.ImportResult` — `frozen` dataclass, 필드 `ok: bool`, `detail: str`
  - `auth.import_credentials(payload: bytes, runner: RunnerLike = subprocess.run) -> ImportResult`
  - `auth.RunnerLike = Callable[..., subprocess.CompletedProcess[bytes]]`
  - `auth.IMPORT_TIMEOUT: float`, `auth.MAX_PAYLOAD_BYTES: int`

  Task 5 의 `components/auth_gate.py` 가 `auth.import_credentials(...)` 를 부르고 `ImportResult.ok` / `.detail` 을 읽는다.

**배경 (스펙 §2.8):** 같은 일을 하는 파이썬 함수 `import_cookie_payload` 는 `notebooklm._app.login_cookie` 에 있고, 협력자 하나가 또 `cli.services.playwright_login` 이다. 둘 다 private 이다. 이 프로젝트는 이미 private 의존 하나(`_LoginRedirectError`)를 안고 방어 코드를 넣는 중이므로 더 얹지 않는다. **공개 CLI 를 자식 프로세스로 부른다.**

`notebooklm auth import-cookies -` 는 stdin 으로 JSON 을 받아 도메인 필터·검증·원자적 쓰기·권한 설정까지 수행한다. extras 없는 기본 패키지로 동작함이 확인되어 있다.

- [ ] **Step 1: 실패하는 테스트 쓰기**

`tests/services/test_auth.py` 끝에 추가한다. 상단 import 에 **`import subprocess` 와 `import sys` 를 다시 들인다** — 앞은 `TimeoutExpired`, 뒤는 인터프리터 경로 확인에 쓴다. Task 3 이 지웠던 둘이다.

```python
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


def test_import_credentials_feeds_the_payload_to_stdin() -> None:
    """자기 인터프리터로 CLI 를 부르고 payload 를 stdin 으로 넘긴다."""
    calls = []
    runner = fake_runner(FakeCompleted(0), calls)

    result = auth.import_credentials(b'{"cookies": []}', runner=runner)

    assert result.ok is True
    args, kwargs = calls[0]
    assert args[0] == sys.executable
    assert args[1:] == [
        "-m",
        "notebooklm",
        "auth",
        "import-cookies",
        "-",
    ]
    assert kwargs["input"] == b'{"cookies": []}'


def test_import_credentials_reports_a_nonzero_exit() -> None:
    """종료 코드가 0 이 아니면 실패로 보고 사유를 담는다."""
    runner = fake_runner(
        FakeCompleted(1, stderr="쿠키가 모자랍니다".encode()), []
    )

    result = auth.import_credentials(b"{}", runner=runner)

    assert result.ok is False
    assert "쿠키가 모자랍니다" in result.detail


def test_import_credentials_reports_a_timeout() -> None:
    """제한 시간 안에 안 끝나면 그 사실을 알린다."""
    runner = fake_runner(
        subprocess.TimeoutExpired(cmd="notebooklm", timeout=30.0), []
    )

    result = auth.import_credentials(b"{}", runner=runner)

    assert result.ok is False
    assert "30" in result.detail


def test_import_credentials_rejects_an_oversized_payload() -> None:
    """상한을 넘는 입력은 CLI 에 넘기기 전에 거절한다."""
    calls = []
    runner = fake_runner(FakeCompleted(0), calls)
    payload = b"x" * (auth.MAX_PAYLOAD_BYTES + 1)

    result = auth.import_credentials(payload, runner=runner)

    assert result.ok is False
    assert not calls


def test_import_credentials_rejects_an_empty_payload() -> None:
    """빈 파일은 CLI 에 넘기지 않는다."""
    calls = []
    runner = fake_runner(FakeCompleted(0), calls)

    result = auth.import_credentials(b"", runner=runner)

    assert result.ok is False
    assert not calls


def test_import_credentials_leaves_the_gate_alone() -> None:
    """반입은 판정을 바꾸지 않는다. 판정은 recheck 가 한다."""
    gate, probe = make_gate([False])
    gate.ensure()

    auth.import_credentials(b"{}", runner=fake_runner(FakeCompleted(0), []))

    assert gate.ok is False
    assert probe.calls == 1
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/services/test_auth.py -k import_credentials -v`
Expected: FAIL — `AttributeError: module 'notebooklm_st.services.auth' has no attribute 'import_credentials'`

- [ ] **Step 3: 구현**

`src/notebooklm_st/services/auth.py` 상단 import 에 `dataclasses`, `subprocess`, `sys` 를 다시 들인다. **상수·`RunnerLike`·`ImportResult` 는 `ProbeLike` 바로 아래**(모듈 상단)에, **`import_credentials` 와 `_failure_detail` 은 `AuthGate` 다음, `_open_once` 앞**에 둔다. 상수를 위에 모아 두는 것이 이 파일의 기존 배치다.

```python
IMPORT_TIMEOUT = 30.0
"""반입 자식 프로세스를 기다리는 최대 초.

JSON 을 읽고 파일 하나를 쓰는 일이라 보통 1초 안에 끝난다. 이 값은
그게 동작하지 않았을 때를 위한 뒷받침이다.
"""

MAX_PAYLOAD_BYTES = 1 << 20
"""받아들일 자격증명 파일의 최대 크기.

``storage_state.json`` 은 수 KB 다. 넉넉히 잡아 두고, 잘못 고른 파일을
CLI 에 넘기기 전에 걸러 낸다.
"""

RunnerLike = Callable[..., subprocess.CompletedProcess[bytes]]
"""자식을 돌리는 함수의 모양.

``subprocess.run`` 의 키워드 인자가 많아 Protocol 로 적으면 길기만
하다. 테스트가 가짜를 끼우는 것이 목적이므로 느슨하게 둔다.
"""


@dataclasses.dataclass(frozen=True, slots=True)
class ImportResult:
    """자격증명 반입 결과.

    ``detail`` 에 쿠키 값을 담지 않는다. 화면이 이 문자열을 그대로
    보여 주기 때문이다.
    """

    ok: bool
    detail: str


def import_credentials(
    payload: bytes,
    runner: RunnerLike = subprocess.run,
) -> ImportResult:
    """업로드된 쿠키 JSON 을 활성 프로필에 기록한다.

    같은 일을 하는 라이브러리 함수는 private 이고 협력자까지 private
    이므로, 공개 CLI 를 자식 프로세스로 부른다. CLI 가 도메인 필터와
    검증, 원자적 쓰기, 파일 권한까지 맡는다.

    ``uv`` 로 부르지 않는다. ``uv`` 는 PATH 에 없을 수 있고, 앱은 이미
    notebooklm 이 설치된 인터프리터 안에서 돌고 있다.

    반입에 성공해도 인증 판정은 바꾸지 않는다. 호출자가 이어서
    ``AuthGate.recheck`` 를 부른다. 판정은 한 곳에서만 일어난다.

    Args:
        payload: 업로드된 파일의 내용.
        runner: 자식을 돌리는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.

    Returns:
        성공 여부와 사람에게 보여 줄 사유.
    """
    if not payload:
        return ImportResult(ok=False, detail="빈 파일입니다.")
    if len(payload) > MAX_PAYLOAD_BYTES:
        return ImportResult(
            ok=False,
            detail=f"파일이 너무 큽니다({len(payload)} 바이트).",
        )
    try:
        completed = runner(
            [
                sys.executable,
                "-m",
                "notebooklm",
                "auth",
                "import-cookies",
                "-",
            ],
            input=payload,
            capture_output=True,
            timeout=IMPORT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return ImportResult(
            ok=False,
            detail=f"{int(IMPORT_TIMEOUT)}초 안에 끝나지 않았습니다.",
        )
    if completed.returncode == 0:
        return ImportResult(ok=True, detail="자격증명을 반입했습니다.")
    return ImportResult(
        ok=False, detail=_failure_detail(completed.stderr, completed.stdout)
    )


def _failure_detail(stderr: bytes, stdout: bytes, limit: int = 300) -> str:
    """자식의 실패 출력을 화면에 쓸 짧은 문자열로 만든다.

    Args:
        stderr: 자식의 표준 오류.
        stdout: 자식의 표준 출력. stderr 가 비었을 때 대신 쓴다.
        limit: 남길 최대 글자 수.

    Returns:
        끝에서 ``limit`` 글자. 아무 말도 없으면 대체 문구.
    """
    raw = stderr or stdout or b""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return "자세한 사유를 알 수 없습니다."
    return text[-limit:]
```

> **스펙 §12.4 를 여기서 소비한다.** `_failure_detail` 이 자식의 출력을 화면에 흘린다. 라이브러리는 auth 로거에 대해서만 *"never logs a captured cookie value"* 를 보장하고, 이 CLI 의 오류 출력까지 보장하는지는 확인되지 않았다. **Step 4 다음에 실제 실패 출력을 한 번 눈으로 본다.** 쿠키 값이 섞여 나오면 `_failure_detail` 을 종료 코드만 담는 고정 문구로 바꾼다.

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/services/test_auth.py -v`
Expected: PASS 전부.

- [ ] **Step 5: 실제 실패 출력 눈으로 확인 (스펙 §12.4)**

일부러 잘못된 JSON 을 넣어 CLI 가 무엇을 뱉는지 본다.

```bash
echo '{"cookies": []}' | uv run python -m notebooklm auth import-cookies -
```

Expected: 필수 쿠키가 없다는 취지의 오류. **출력에 쿠키 값처럼 보이는 문자열이 있는지 확인한다.**
- 없으면: 그대로 둔다.
- 있으면: `_failure_detail` 을 `f"반입이 실패했습니다(종료 코드 {completed.returncode})."` 로 바꾸고, 전문은 `logger.warning` 으로만 남긴다. 테스트 `test_import_credentials_reports_a_nonzero_exit` 의 assert 도 종료 코드 확인으로 바꾼다.

- [ ] **Step 6: 검증 4단**

```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```
Expected: 전부 통과.

- [ ] **Step 7: 커밋**

```bash
git add src/notebooklm_st/services/auth.py tests/services/test_auth.py
git commit -m "$(cat <<'EOF'
✨ feat(auth): 자격증명 반입 함수 추가

업로드된 쿠키 JSON 을 활성 프로필에 기록한다. 같은
일을 하는 라이브러리 함수는 private 이고 협력자까지
private 이라, 공개 CLI 를 자식 프로세스로 부른다.

반입은 판정을 바꾸지 않는다. 판정은 recheck 한 곳에서만
일어난다.

Assisted-by: claude-opus-5
EOF
)"
```

---

### Task 5: 업로더 UI

**Files:**
- Modify: `src/notebooklm_st/components/auth_gate.py`
- Test: `tests/test_components.py`

**Interfaces:**
- Consumes: `auth.import_credentials(payload: bytes) -> auth.ImportResult` (Task 4), `AuthGate.recheck() -> bool` (Task 2), `errors.LOGIN_HINT` (Task 1)
- Produces: 없음 (마지막 소비자)

**배경:** 사람이 매번 scp·공유 폴더로 디렉터리를 옮기고 권한까지 맞추는 대신, 브라우저에서 JSON 하나를 올린다. 업로드 → 반입 → 자동 재확인이 한 흐름으로 끝난다.

**전제 (스펙 §13.1):** 이 UI 는 **앱이 외부에 노출되지 않는다는 전제** 위에 있다. 노출로 바꾸면 이 기능을 제거하고 볼륨 직접 복사로 되돌린다.

**지킬 것 (스펙 §7.1.1):**
- `UploadedFile` 은 메모리 버퍼다. `getvalue()` 를 바로 넘겨 **디스크에 임시 파일을 만들지 않는다.**
- **화면에 쿠키 내용을 절대 표시하지 않는다.**
- 업로드 폼은 **쓰기 전용**이다. 저장된 자격증명을 읽는 경로를 만들지 않는다.
- 업로더는 **만료됐을 때만** 그린다. `gate.ok` 면 이 코드에 닿지 않는다.

- [ ] **Step 1: 실패하는 테스트 쓰기**

`tests/test_components.py` 의 게이트 테스트 옆에 추가한다.

```python
def test_auth_gate_imports_an_uploaded_credential(monkeypatch) -> None:
    """업로드한 자격증명을 반입하고 곧바로 다시 확인한다."""
    seen = []
    results = iter([False, True])

    def probe() -> bool:
        """첫 확인은 만료, 반입 뒤에는 정상으로 답한다."""
        return next(results, True)

    def fake_import(payload):
        """반입 호출을 기록하고 성공으로 답한다."""
        seen.append(payload)
        return auth.ImportResult(ok=True, detail="반입했습니다")

    gate = auth.AuthGate(probe=probe)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)
    monkeypatch.setattr(auth, "import_credentials", fake_import)

    def script():
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.file_uploader(key="auth_gate_upload").set_value(
        ("storage_state.json", b'{"cookies": []}', "application/json")
    )
    app.run()
    app.button(key="auth_gate_import").click().run()

    assert not app.exception
    assert seen == [b'{"cookies": []}']
    assert gate.ok is True


def test_auth_gate_reports_a_failed_import(monkeypatch) -> None:
    """반입이 실패하면 사유를 보여 주고 판정을 바꾸지 않는다."""

    def fake_import(payload):
        """실패로 답한다."""
        return auth.ImportResult(ok=False, detail="쿠키가 모자랍니다")

    gate = auth.AuthGate(probe=lambda: False)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)
    monkeypatch.setattr(auth, "import_credentials", fake_import)

    def script():
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script)
    app.run()
    app.file_uploader(key="auth_gate_upload").set_value(
        ("storage_state.json", b"{}", "application/json")
    )
    app.run()
    app.button(key="auth_gate_import").click().run()

    assert not app.exception
    assert any("쿠키가 모자랍니다" in box.value for box in app.error)
    assert gate.ok is False


def test_auth_gate_hides_the_uploader_when_authenticated(
    stub_auth_gate,
) -> None:
    """인증이 살아 있으면 업로더를 그리지 않는다."""

    def script():
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.file_uploader) == 0
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_components.py -k auth_gate -v`
Expected: FAIL — `KeyError` 또는 `IndexError`. `auth_gate_upload` 키를 가진 파일 업로더가 없다.

- [ ] **Step 3: 구현**

`src/notebooklm_st/components/auth_gate.py` 에 업로더를 넣는다. `render()` 안의 `_render_notice(...)` 호출 다음, "다시 확인" 버튼 앞에 `_render_upload(gate)` 를 끼우고 아래 함수를 더한다. import 에 `from notebooklm_st.services import auth` 를 추가한다.

```python
_UPLOAD_KEY = "auth_gate_upload"
_IMPORT_KEY = "auth_gate_import"


def _render_upload(gate: auth.AuthGate) -> None:
    """자격증명을 올려 반입하는 접은 영역을 그린다.

    반입에 성공하면 곧바로 다시 확인까지 하고 화면을 새로 그린다.
    사용자가 버튼을 두 번 누르지 않아도 된다.

    업로드된 내용은 화면에도 로그에도 남기지 않는다. 계정 동등
    자격증명이기 때문이다.

    Args:
        gate: 반입 뒤 다시 확인할 게이트.
    """
    with st.expander("자격증명 올리기"):
        st.caption(
            "데스크톱에서 만든 storage_state.json 을 올립니다."
            " 절차는 docs/how-to/2026-09-16-auth-reseed.md 에 있습니다."
        )
        uploaded = st.file_uploader(
            "storage_state.json", type="json", key=_UPLOAD_KEY
        )
        if not st.button(
            "반입", key=_IMPORT_KEY, disabled=uploaded is None
        ):
            return
        if uploaded is None:
            return
        with st.spinner("반입 중"):
            result = auth.import_credentials(uploaded.getvalue())
        if not result.ok:
            st.error(f"반입하지 못했습니다: {result.detail}")
            return
        if gate.recheck():
            st.rerun()
        st.error("반입했지만 인증이 살아나지 않았습니다.")
```

`render()` 는 이렇게 된다.

```python
    _render_notice(gate.probe_error)
    _render_upload(gate)
    if st.button("다시 확인", key=_RECHECK_KEY):
        with st.spinner("다시 확인 중"):
            if gate.recheck():
                st.rerun()
    return gate.ok
```

모듈 docstring 에 한 문단을 더한다.

```
업로더는 앱이 외부에 노출되지 않는다는 전제 위에 있다(스펙 §13.1).
노출로 바꾸면 이 기능을 빼고 볼륨 직접 복사로 되돌린다.
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_components.py -k auth_gate -v`
Expected: PASS 6개.

- [ ] **Step 5: 검증 4단**

```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```
Expected: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add src/notebooklm_st/components/auth_gate.py tests/test_components.py
git commit -m "$(cat <<'EOF'
✨ feat(auth): 자격증명 업로드 UI 추가

만료 배너 옆에서 storage_state.json 을 올리면 반입과
다시 확인까지 한 흐름으로 끝난다. 볼륨에 디렉터리를
직접 복사하고 권한을 맞추는 수고가 사라진다.

앱 비노출을 전제로 한다. 노출로 바꾸면 빼야 한다.

Assisted-by: claude-opus-5
EOF
)"
```

---

### Task 6: `[browser]` 를 dev 그룹으로

**Files:**
- Modify: `pyproject.toml:6-9`, `pyproject.toml:39-44`

**Interfaces:**
- Consumes: 없음
- Produces: 없음 (의존성 재배치)

**배경:** 컨테이너 이미지에서 playwright 를 빼야 한다. 그런데 `[browser]` 를 기본에서 통째로 지우면 **데스크톱에서도 `notebooklm login` 이 안 된다** — 재시드 절차 자체가 막힌다. dev 그룹으로 옮겨 로컬은 `uv sync` 로 브라우저를 갖고, 이미지는 `uv sync --no-dev` 로 뺀다.

- [ ] **Step 1: 의존성 재배치 — `uv` 로만 한다**

`.claude/rules/streamlit-implement.md` §1 이 **의존성 조작은 `uv add`·`uv add --dev`·`uv remove` 로만** 하도록 정한다. `pyproject.toml` 의 `dependencies` 를 손으로 고치지 않는다. `uv.lock` 은 절대 손대지 않는다.

```bash
uv remove notebooklm-py
uv add "notebooklm-py==0.8.1"
uv add --dev "notebooklm-py[browser]==0.8.1"
```

첫 명령이 `[browser]` 가 붙은 기존 항목을 걷어내고, 둘째가 extras 없이 기본 의존성에 다시 넣고, 셋째가 dev 그룹에 브라우저판을 넣는다.

**결과를 확인한다.**

```bash
uv run python -c "
import tomllib, pathlib
data = tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))
print('deps:', data['project']['dependencies'])
print('dev :', data['dependency-groups']['dev'])
"
```

Expected: `deps` 에 `notebooklm-py==0.8.1`(extras 없음)과 `streamlit>=1.62.0`, `dev` 에 `notebooklm-py[browser]==0.8.1` 과 기존 `mypy`·`pytest`·`ruff`.

`uv` 가 기대와 다르게 배치했을 때만(예: extras 가 남았거나 dev 그룹이 아닌 곳에 들어갔을 때) `pyproject.toml` 을 최소한으로 손봐 위 모양으로 맞추고, 반드시 `uv lock` 으로 잠금 파일을 다시 만든다.

**마지막으로 dev 그룹의 `[browser]` 줄 위에 주석을 붙인다.** 이건 의존성 조작이 아니라 설명이므로 직접 편집해도 된다.

```toml
    # 데스크톱에서 notebooklm login 을 돌리는 데 필요하다. 컨테이너
    # 이미지는 uv sync --no-dev 로 이것을 뺀다.
```

- [ ] **Step 2: `--no-dev` 가 playwright 를 빼는지 확인 (스펙 §12.3)**

```bash
uv sync --no-dev
uv run python -c "import importlib.util; print(importlib.util.find_spec('playwright') is not None)"
```
Expected: `False`

`False` 가 아니면 멈추고 보고한다. 스펙 §12.3 의 미검증 가정이 깨진 것이다.

- [ ] **Step 3: 개발 환경 되돌리기**

```bash
uv sync
uv run python -c "import importlib.util; print(importlib.util.find_spec('playwright') is not None)"
```
Expected: `True` — dev 그룹이 다시 들어와 테스트와 로그인이 가능하다.

- [ ] **Step 4: 검증 4단**

```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```
Expected: 전부 통과.

- [ ] **Step 5: 커밋**

```bash
git add pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
📦️ build(deps): browser extras 를 dev 그룹으로 옮기기

컨테이너 이미지에서 playwright 를 빼기 위해서다.
기본 의존성에서 통째로 지우면 데스크톱에서도
notebooklm login 이 안 돼 재시드 절차가 막힌다.

로컬은 uv sync 로 브라우저를 갖고, 이미지는
uv sync --no-dev 로 뺀다.

Assisted-by: claude-opus-5
EOF
)"
```

---

### Task 7: 문서 — 재시드 절차서와 README

**Files:**
- Create: `docs/how-to/2026-09-16-auth-reseed.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1~6 의 결과 전부
- Produces: 없음

**배경:** R1 이 코드를 바꾸면서 README 의 기존 설명이 **거짓말이 된다.** "크로미움 창이 자동으로 열립니다" 와 "재인증 버튼이 나타납니다" 는 둘 다 더 이상 사실이 아니다.

- [ ] **Step 1: 재시드 절차서 쓰기**

`docs/how-to/` 디렉터리를 만들고 `docs/how-to/2026-09-16-auth-reseed.md` 를 쓴다. 아래 내용을 담는다.

```markdown
# 인증이 만료됐을 때 되살리기

앱이 "인증이 만료되었습니다" 배너를 띄우면 이 절차를 따른다.

## 왜 사람이 해야 하나

NotebookLM 에는 공개 API 가 없다. `notebooklm-py` 는 브라우저가 쓰는
내부 엔드포인트를 **구글 웹 세션 쿠키**로 호출한다. 그 쿠키는 실제
브라우저에서 실제로 로그인해야 나온다.

앱은 요청이 나갈 때마다 토큰을 재추출하고 쿠키를 회전시켜 세션을
살려 둔다. 브라우저 없이 되는 일이다. 그런데 그 갱신으로도 못 살릴
만큼 세션이 죽으면 **사람이 데스크톱에서 다시 로그인해야 한다.**

## 정본 — 대시보드 업로드

### 1. 데스크톱에서 로그인

```bash
cd notebooklm-st
uv sync
uv run notebooklm login
```

크로미움이 열린다. 구글 로그인을 마치면 CLI 가 스스로 저장하고
끝난다. 터미널 입력은 필요 없다.

만들어지는 파일:

```
~/.notebooklm/profiles/default/storage_state.json
```

윈도우에서는 `C:\Users\<사용자>\.notebooklm\profiles\default\` 다.

### 2. 대시보드에서 올리기

1. 앱을 연다.
2. 만료 배너 아래 **자격증명 올리기** 를 편다.
3. 위 `storage_state.json` 을 고른다.
4. **반입** 을 누른다.

반입에 성공하면 앱이 곧바로 다시 확인까지 하고 화면을 새로 그린다.

## 대체 — 볼륨에 직접 복사

업로드가 안 될 때만 쓴다.

**컨테이너 안이 아니라 호스트의 볼륨 디렉터리에 놓는다.** 바인드
마운트가 호스트 경로를 컨테이너 경로에 비춰 주므로, 호스트 쪽에
파일을 놓기만 하면 된다. `docker cp` 로 컨테이너 안에 직접 넣으면
컨테이너를 다시 만들 때 사라진다.

```
호스트 (홈서버)                        컨테이너 내부
<볼륨 경로>/notebooklm/         ←──→  /root/.notebooklm/
      profiles/default/                     profiles/default/
```

실제 볼륨 경로는 R2(컨테이너화)에서 정한다.

두 가지를 지킨다.

- **프로필 디렉터리 전체를 복사한다.** `storage_state.json` 옆에 락과
  회전 상태가 형제 파일로 생긴다. 파일 하나만 옮기면 어긋난다.
- **볼륨은 쓰기 가능해야 한다.** 앱이 회전된 쿠키를 그 파일에 다시
  쓴다. `:ro` 로 마운트하면 갱신이 저장되지 않아 재시작마다 옛
  쿠키로 돌아가고 결국 죽는다.

복사한 뒤 대시보드에서 **다시 확인** 을 누른다.

## 자격증명 취급 수칙

`storage_state.json` 은 **계정 동등 자격증명**이다. 이 파일을 가진
사람은 해당 구글 계정의 웹 세션을 쓸 수 있다.

- 전송은 scp·SSH 같은 **암호화된 경로**로 한다. 평문 채널이나 공용
  클라우드 드라이브에 올리지 않는다.
- 옮긴 뒤 **데스크톱에 남은 복사본을 지운다.** 원본
  (`~/.notebooklm/profiles/default/`)은 그대로 둬도 된다.
- 저장소에 커밋하지 않는다. `.gitignore` 에 `storage_state.json` 이
  이미 들어 있다.
- 유출이 의심되면 **구글 계정 → 보안 → 기기에서 로그아웃** 으로 즉시
  폐기한다.
- 앱과 브라우저 사이 구간은 평문 HTTP 다. 홈 네트워크 안이라도 같은
  Wi-Fi 의 다른 기기에는 보인다. Tailscale 처럼 암호화된 경로로
  접근하면 이 구간이 덮인다.

## 주의 — 데스크톱 앱과 컨테이너 앱을 동시에 오래 띄우지 않는다

둘 다 같은 계정의 쿠키를 각자 회전시킨다. 서로의 갱신을 덮어써 양쪽이
함께 죽을 수 있다. 개발용으로 데스크톱에서 앱을 띄울 때는 짧게 쓴다.
```

- [ ] **Step 2: README 고치기**

`README.md` 에서 네 곳을 고친다.

| 위치 | 현재 | 바꿀 내용 |
|---|---|---|
| 요구사항 표의 "주요 의존성" 행 | `notebooklm-py[browser]==0.8.1` | `notebooklm-py==0.8.1` (+ "브라우저 로그인용 `[browser]` 는 dev 그룹") |
| 그 표 아래 문장 | "`[browser]` extras 가 브라우저 로그인용 크로미움을 함께 설치합니다." | "`[browser]` extras 는 dev 그룹에 있습니다. `uv sync` 하면 따라오고, 컨테이너 이미지는 `uv sync --no-dev` 로 뺍니다." |
| "### 첫 실행 — 인증" 절 본문 | "앱이 뜨면 저장된 인증을 먼저 확인하고, 없거나 만료됐으면 **크로미움 창이 자동으로 열립니다.**" | 아래 새 본문 |
| 같은 절 끝 | "자동 복구에 실패하면 화면에 재인증 버튼이 나타납니다." | 아래 새 본문에 포함 |

"첫 실행 — 인증" 절의 본문을 아래로 교체한다.

```markdown
로그인 화면은 없습니다. 앱은 브라우저를 띄우지 않습니다.

처음 쓸 때는 터미널에서 한 번 로그인합니다.

```bash
uv run notebooklm login
```

크로미움이 열립니다. 구글 로그인을 마치면 CLI 가 스스로 저장합니다.

앱은 뜰 때 저장된 인증을 확인하고, 요청이 나갈 때마다 토큰과 쿠키를
자동으로 갱신합니다. 그 갱신으로도 못 살릴 만큼 세션이 죽으면 화면에
만료 안내와 **다시 확인** 버튼이 나타납니다. 되살리는 절차는
[인증이 만료됐을 때 되살리기](docs/how-to/2026-09-16-auth-reseed.md)
에 있습니다.
```

- [ ] **Step 3: 링크와 문구가 맞는지 확인**

```bash
uv run python -c "
import pathlib
doc = pathlib.Path('docs/how-to/2026-09-16-auth-reseed.md')
readme = pathlib.Path('README.md').read_text(encoding='utf-8')
print('문서 있음:', doc.exists())
print('README 가 링크함:', str(doc).replace(chr(92), '/') in readme)
print('옛 문구 남음:', '크로미움 창이 자동으로 열립니다' in readme)
print('옛 버튼 남음:', '재인증 버튼' in readme)
"
```
Expected:
```
문서 있음: True
README 가 링크함: True
옛 문구 남음: False
옛 버튼 남음: False
```

- [ ] **Step 4: 문구 정본이 문서를 가리키는지 확인**

Task 1 의 `LOGIN_HINT` 가 이 문서 경로를 담고 있다. 실제로 맞는지 본다.

```bash
uv run python -c "
from notebooklm_st.core import errors
print(errors.LOGIN_HINT)
"
```
Expected: 출력에 `docs/how-to/2026-09-16-auth-reseed.md` 가 있고, 그 경로에 파일이 실재한다.

- [ ] **Step 5: 검증 4단**

```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```
Expected: 전부 통과.

> `ruff` 는 `extend-exclude = ["*.md"]` 로 마크다운 안의 파이썬 코드 블록을 건드리지 않는다. 새 문서의 코드 블록이 포맷팅으로 바뀔 걱정은 없다.

- [ ] **Step 6: 커밋**

```bash
git add docs/how-to/2026-09-16-auth-reseed.md README.md
git commit -m "$(cat <<'EOF'
📝 docs: 재시드 절차서 추가와 README 인증 서술 수정

브라우저 로그인이 사라지면서 README 의 네 곳이 틀린
설명이 됐다. 크로미움 창이 자동으로 열린다는 서술과
재인증 버튼 안내를 바로잡았다.

되살리는 절차와 자격증명 취급 수칙을 how-to 문서로
따로 뽑았다. LOGIN_HINT 가 이 문서를 가리킨다.

Assisted-by: claude-opus-5
EOF
)"
```

---

## 완료 확인

R1 이 끝나면 아래가 모두 참이어야 한다.

- [ ] `uv run pytest` 전부 통과
- [ ] `uv run mypy src tests` 통과
- [ ] `uv run ruff check .` 통과
- [ ] `src/` 어디에도 `notebooklm login` 을 자식 프로세스로 띄우는 코드가 없다
  - 확인: `grep -rn "run_login\|LoginLike\|PopenLike" src/` 가 아무것도 찾지 못한다
  - 확인: `grep -rn "notebooklm\"" src/` 가 `import-cookies` 호출 한 곳만 찾는다
- [ ] `uv sync --no-dev` 한 환경에 playwright 가 없다
- [ ] 앱이 뜨고, 인증이 살아 있으면 배너가 안 보인다
  - 확인: `uv run streamlit run src/notebooklm_st/app.py`
- [ ] 만료 안내 문구가 화면과 실행 실패에서 같다 (둘 다 `errors.LOGIN_HINT`)
- [ ] README 에 "크로미움 창이 자동으로 열립니다" 가 없다

## R2 로 넘기는 것

이 계획이 만들어 두고 R2(컨테이너화)가 이어받을 것들이다.

| 항목 | 어디에 |
|---|---|
| 볼륨은 **쓰기 가능**해야 한다 (쿠키 회전이 파일에 되쓰임) | how-to 문서 |
| **프로필 디렉터리 전체**를 마운트한다 (락·회전 상태가 형제 파일) | how-to 문서 |
| 실제 볼륨 경로 | how-to 문서에 자리만 있음. R2 가 채운다 |
| `TZ=Asia/Seoul` — `store.now()` 가 로컬 시각이다 | 스펙 §13, R2 범위 |
| `uv sync --no-dev` 로 이미지를 만든다 | Task 6 에서 검증됨 |
| 업로드 UI 는 **앱 비노출이 전제**다 | 스펙 §13.1 |
