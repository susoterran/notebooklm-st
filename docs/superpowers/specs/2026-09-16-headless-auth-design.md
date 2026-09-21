# 무인 갱신 인증 전환 설계 — 브라우저 로그인 제거

- **작성일**: 2026-09-16
- **상태**: 설계 (구현 계획 수립 전)
- **대상**: `services/auth.py`, `components/auth_gate.py`, `core/errors.py`,
  `pyproject.toml`. 질의 파이프라인(`services/nlm.py`)과 실행 모델
  (`services/runner.py`·`runs.py`)은 건드리지 않는다.
- **범위**: 릴리스 R1. 컨테이너 전환(R2)의 **선행 조건**이다. 인증의 주도권을
  앱에서 사람에게 넘긴다 — 앱이 인증을 **시작하는** 능력(브라우저 로그인)을
  덜어내고, 자격증명을 **받는** 능력(업로드)을 더한다.

---

## 1. 왜 바꾸는가

앱을 홈서버의 도커 컨테이너로 옮기기로 했다
(기획 `docs/requests/2026-09-16-summary-pipeline-v2.md`).
그런데 지금 앱은 **인증이 만료되면 브라우저 창을 띄워 사람의 로그인을
기다린다.**

```python
# services/auth.py:110
process = popen(
    [sys.executable, "-m", "notebooklm", "login"], ...
)
```

이 경로는 컨테이너에서 **무조건 실패한다.**

1. 컨테이너 이미지에 playwright 를 넣지 않는다. 넣어도 화면이 없어 브라우저를
   띄울 수 없다.
2. 이 자식 프로세스는 사람이 브라우저에서 로그인을 마칠 때까지 최대 300초를
   기다린다. 무인 환경에는 기다릴 사람이 없다.

따라서 **컨테이너로 가기 전에 인증 경로를 먼저 바꿔야 한다.** 이 릴리스를
건너뛰면 R2 에서 앱이 뜨지 않는다.

### 1.1 "무인 인증" 이 아니라 "무인 갱신" 이다

용어를 먼저 고정한다. 이 설계가 없애는 것은 **최초 로그인이 아니다.**

- **최초 로그인은 앞으로도 사람이 데스크톱에서 브라우저로 한다.** 없앨 수 없다.
- 없애는 것은 **"만료되면 앱이 스스로 브라우저를 띄우는 것"** 이다.
- 컨테이너가 무인으로 하는 것은 **갱신(refresh)** 이지 인증(login)이 아니다.

### 1.2 앱은 구글 인증을 하지 않는다

이 문서를 읽는 사람이 가장 먼저 묻는 질문이므로 앞에 못박아 둔다.

- **앱은 지금도 구글 인증을 하지 않는다.** `services/auth.py:110` 이 하는 일은
  `notebooklm` CLI 를 자식 프로세스로 띄우는 것뿐이다. 아이디도 비밀번호도
  만지지 않는다.
- **대시보드에 로그인 창을 만들지 않는다.** 만들어도 작동하지 않는다. 필요한
  것은 브라우저가 구글에 로그인한 결과로 생긴 웹 세션 쿠키이고, 그것은 실제
  브라우저에서만 나온다. 구글 OAuth/OIDC 가 주는 신원 토큰으로는 NotebookLM 을
  호출할 수 없다(2.1 — 공개 API 가 없다).
- `notebooklm login` 은 **로컬(데스크톱)에서만 돈다.** 컨테이너에서는 돌리지
  않으며 돌릴 수도 없다.
- 그 명령은 **notebooklm-st 가 아니라 `notebooklm-py` 라이브러리의 CLI** 다
  (`console_scripts: notebooklm -> notebooklm.notebooklm_cli:main`).
  `notebooklm-st` 에는 `[project.scripts]` 가 없다.

따라서 R1 이 바꾸는 것은 인증 방식이 아니라 **누가 그 버튼을 누르는가** 다.
앱이 대신 눌러 주던 것을 사람이 직접 누른다.

### 1.3 운영상 두 환경이 필요해진다

코드베이스는 하나지만, 자격증명을 만들려면 `notebooklm-py` 가 설치된 파이썬
환경이 어딘가에 있어야 한다. 이것은 R1 이 받아들이는 비용이다.

| | 개수 |
|---|---|
| 코드베이스 | 1 |
| 상시 도는 앱 | 1 (컨테이너) |
| **필요한 환경** | **2** (컨테이너 + 자격증명을 만드는 데스크톱) |

---

## 2. 조사로 확인한 사실

설계의 전제는 추측이 아니라 실제 코드와 실제 실행으로 확인했다.

### 2.1 브라우저는 쿠키를 얻는 수단일 뿐이다

NotebookLM 에는 공개 API 가 없다. `notebooklm-py` 는 브라우저가 쓰는 내부
엔드포인트를 **구글 웹 세션 쿠키**로 호출한다. `notebooklm login` 이 하는
일은 이것뿐이다.

```
크로미움 실행 → 사람이 구글 로그인
  → 그 브라우저의 쿠키를 storage_state.json 으로 저장 → 브라우저 종료
```

이후 모든 호출은 `httpx` 가 그 쿠키를 붙여 보낸다. **브라우저는 다시 쓰이지
않는다.**

### 2.2 쿠키 갱신에는 브라우저가 필요 없다

`notebooklm/_auth/headless_reauth.py` 가 복구 사다리를 문서화하고 있다.

| 층 | 수단 | 브라우저 |
|---|---|---|
| L1 | 홈페이지 GET 으로 CSRF 토큰(`SNlM0e`/`FdrFJe`) 재추출 | 불필요 |
| L2 | `RotateCookies` POST 로 `__Secure-1PSIDTS` 회전 | 불필요 |
| L3 | 저장된 브라우저 프로필로 무인 재인증 | **playwright 필요** |

**L1·L2 만으로 무인 갱신이 성립한다.** 둘 다 평범한 HTTP 요청이고, 요청이
나갈 때마다 라이브러리가 알아서 돈다(`_middleware/auth_refresh.py`,
`_auth/keepalive.py`).

L3 는 컨테이너에서 쓸 수 없다. playwright 가 없기 때문이고, 라이브러리
자신이 같은 모듈에서 이렇게 못박아 두었다.

> SECURITY — local-unattended-only. The persistent browser profile is an
> account-equivalent credential... L3 must NOT become the auth story for a
> remote / hosted MCP server.

### 2.3 마스터 토큰은 쓸 수 없다

라이브러리에는 `login --master-token` 이라는 네 번째 길이 있다. 브라우저 없이
쿠키를 재발급하는 durable 토큰이다. 그러나 라이브러리 자신의 경고가 이렇다.

> SECURITY: the master token is full-account, durable, infostealer-grade —
> use a dedicated/throwaway account only.

**전용 구글 계정을 만들 수 없다고 확인되었다.** 주 계정의 full-account 영구
토큰을 서버 디스크에 두는 선택지는 배제한다. 그래서 앱은 외부에 노출하지
않기로 했고(R2), 인증은 쿠키 기반 L1/L2 로 간다.

### 2.4 extras 없는 기본 패키지로 앱이 동작한다

R1·R2 전체가 이 전제에 선다. 깨끗한 격리 환경에서 실증했다.

```
설치된 패키지(14개): Pygments, anyio, certifi, click, filelock, h11,
  httpcore, httpx, idna, markdown-it-py, mdurl, notebooklm-py, rich,
  typing_extensions
playwright 있음? -> False

notebooklm import                                 -> OK
from_storage(allow_headless=True)                 -> OK
notebooklm._auth.extraction._LoginRedirectError   -> OK
exceptions.AuthError / HeadlessLoginRequiredError -> OK
```

`notebooklm-py` 의 기본 의존성은 `click`·`filelock`·`httpx`·`rich` 넷뿐이고
playwright 는 `[browser]` extras 에만 있다. `core/errors.py` 가 파고드는
private 경로도 extras 없이 접근된다.

### 2.5 확인은 곧 갱신이다

`is_authenticated()` 는 클라이언트를 열었다 닫을 뿐이지만, **여는 행위 자체가
L1/L2 를 태운다.** 기존 docstring 이 이미 그렇게 적고 있다.

> 여는 데 성공하면 라이브러리가 필요한 복구를 이미 마친 것이다.

따라서 앱 기동 시의 사전 확인은 단순 조회가 아니라 **쿠키 갱신 기회**다. 이
동작은 R1 에서 건드리지 않는다.

### 2.6 갱신된 쿠키는 파일에 되쓰인다

`notebooklm/_cookie_persistence.py` 의 `CookiePersistence` /
`SaveCookiesToStorage` 가 회전된 쿠키를 저장소에 다시 쓴다. 회전 상태와 락은
`storage_state.json` **옆에 형제 파일 4개**로 생긴다
(`_storage_state_lock_path`·`_rotation_lock_path`·`_refresh_lock_path`·
`_bootstrap_lock_path`).

R2 로 넘길 운영 조건 두 가지가 여기서 나온다.

- 자격증명 볼륨은 **쓰기 가능**해야 한다. `:ro` 로 마운트하면 회전이 저장되지
  않아 재시작마다 옛 쿠키로 되돌아가고 결국 죽는다.
- 파일 하나가 아니라 **프로필 디렉터리 전체**
  (`~/.notebooklm/profiles/default/`)를 마운트해야 한다.

### 2.7 컨테이너에서 만료는 어떤 예외로 오는가

`HeadlessLoginRequiredError` 의 docstring 은 "헤드리스 브라우저를 **실제로
띄웠는데** 구글 로그인 페이지로 튕겼을 때" 라고 적고 있다. 컨테이너에서는
L3 가 아예 실행되지 않으므로 **이 예외는 나오지 않는다.**

| 예외 | 컨테이너 | 로컬(dev) |
|---|---|---|
| `_LoginRedirectError` (private) | **주 신호** | 발생 |
| `exceptions.AuthError` | 발생 | 발생 |
| `HeadlessLoginRequiredError` | 안 나옴 | L3 가 돌고 실패했을 때 |

매핑(`core/errors.py:33`)은 셋 다 유지한다. 로컬에서 유효하고 컨테이너에서는
안 걸릴 뿐이다.

### 2.8 자격증명 반입은 공개 CLI 로만 해야 한다

`auth import-cookies` 는 쿠키 JSON 을 받아 도메인 필터·검증·원자적 쓰기·권한
설정까지 수행한다. 헬프 원문이 *"written atomically to the active profile's
`storage_state.json` ... with private file permissions"* 다. `-` 로 stdin 을
받는 것도 문서화된 용법이고, **extras 없는 기본 패키지로 동작함을 2.4 와 같은
격리 환경에서 확인했다.**

그런데 같은 일을 하는 **파이썬 함수는 공개 API 가 아니다.**

```
notebooklm.auth (공개)  → convert_rookiepy_cookies_to_storage_state,
                          도메인 상수뿐. import 함수 없음
import_cookie_payload   → notebooklm._app.login_cookie        (private)
                          협력자 2개를 주입받는데 그중 하나가
                          cli.services.playwright_login       (private)
```

함수를 직접 부르면 private 의존이 2~3개 늘어난다. 7.2 가 **이미 있는 private
의존 하나**(`_LoginRedirectError`)를 위험으로 다루고 방어 코드를 넣는 중이므로,
여기에 더 얹지 않는다. **자식 프로세스로 공개 CLI 를 부른다.**

---

## 3. 설계 결정

| 결정 | 선택 | 근거 |
|---|---|---|
| 브라우저 로그인 경로 | **완전 제거** | 컨테이너에서 불가능. 로컬에서도 사용자가 터미널에서 직접 하는 편이 명확하다. env 로 모드를 가르면 인증 경로가 둘이 되어 둘 다 테스트하고 둘 다 유지해야 한다 |
| 재시드 수단 | **`notebooklm login`** (데스크톱) | 새 세션으로 로그인하므로 평소 쓰는 브라우저의 세션과 분리된다. 서버 쪽 자격증명만 따로 폐기할 여지가 생긴다. 검토했다 제외한 대안은 13절에 있다 |
| 자격증명 반입 | **대시보드 업로드를 정본으로, 볼륨 직접 복사를 대체 경로로** | 사람이 매번 scp·공유 폴더로 디렉터리를 옮기고 권한까지 맞추는 것보다, 브라우저에서 JSON 하나를 올리는 편이 낫다. 업로드 → 반입 → 자동 재확인이 한 흐름으로 끝난다. **앱 비노출이 전제다**(13절) |
| 반입 구현 | **공개 CLI 를 자식 프로세스로** | 2.8. 라이브러리 함수는 private 이고 협력자까지 private 이다. `login` 자식 프로세스를 지우면서 다른 자식 프로세스를 넣는 모양이지만 성격이 다르다 — 브라우저 없음, 대화형 아님, 수 초 내 종료, **컨테이너에서 동작 확인됨** |
| 기동 시 사전 확인 | **유지** | 만료 시 사용자가 할 일(데스크톱 재로그인 + 프로필 복사)이 즉각적이지 않다. 질문을 고르고 실행을 누르기 전에 아는 값이 크다. 2.5 에 따라 갱신 기회이기도 하다 |
| `relogin()` 자리 | **`recheck()` 로 대체** | 프로필을 갈아 끼운 뒤 앱이 그것을 알아챌 경로가 필요하다. 없으면 컨테이너 재시작이 유일한 회복 수단이 된다 |
| 만료 문구 | **`core/errors.py` 로 단일화** | 지금 `errors._LOGIN_HINT` 와 `auth_gate._EXPIRED_HINT` 로 갈라져 있고 **둘 다 틀리게 된다.** 어차피 양쪽을 고쳐야 하므로 이번에 합친다 |
| Slack 알림 | **범위 밖 (R6)** | R5 까지는 무인으로 도는 것이 없다. 사용자가 버튼을 눌러야 NotebookLM 을 건드리고, 그러면 만료는 그 자리에서 화면에 보인다 |
| 인증 상태 값 객체 | **도입하지 않음** | 지금 필요 없는 구조다. R6 에서 필요해지면 그때 넣는다 |

---

## 4. 구조

R1 은 **새 모듈을 만들지 않는다.** 기존 파일에서 브라우저 로그인을 덜어내고,
그 자리에 자격증명 반입과 업로더를 넣는다. 흩어진 문구는 한 곳으로 모은다.

```
                              현재      R1 이후
services/auth.py              237줄  →  ~130줄   (−run_login, +import_credentials)
components/auth_gate.py        67줄  →   ~75줄   (−재인증, +다시 확인·업로더)
core/errors.py                101줄  →  ~105줄
pyproject.toml                        의존성 재배치
docs/how-to/...-auth-reseed.md     (신규)
```

### 4.1 경계

README 에 명시된 규칙(`core/` 와 `services/` 는 `import streamlit` 을 하지
않는다)을 그대로 지킨다.

| 모듈 | 책임 | Streamlit |
|---|---|---|
| `core/errors.py` | 만료 문구의 **유일한 정본** | 모름 |
| `services/auth.py` | 인증이 살아 있는지 **판정**만. 문구를 만들지 않음 | 모름 |
| `components/auth_gate.py` | 판정 결과를 **그림**. 문구는 `errors` 에서 | 앎 |

이 경계가 R6 에 그대로 쓰인다. 스케줄러는 `services/auth.py` 를 부르고 Slack
알림은 `core/errors.py` 의 같은 문구를 보낸다. 화면과 알림이 다른 말을 할 수
없다.

---

## 5. `services/auth.py`

### 5.1 덜어내는 것

| 대상 | 처분 |
|---|---|
| `ProcessLike` · `PopenLike` · `LoginLike` | 삭제 — 자식 프로세스가 사라진다 |
| `LOGIN_TIMEOUT` · `run_login()` | 삭제 |
| `CHECK_NOTICE` | 삭제 — 진행 문구를 흘릴 단계가 없다 |
| `import time` | 삭제 |
| `import subprocess` · `import sys` | **유지** — 5.4 의 자격증명 반입이 쓴다 |

### 5.2 남는 계약

```python
def is_authenticated(client_factory=nlm.default_client_factory) -> bool: ...


class AuthGate:
    def __init__(self, probe: ProbeLike = is_authenticated) -> None: ...

    @property
    def ok(self) -> bool: ...

    @property
    def tried(self) -> bool: ...

    @property
    def probe_error(self) -> Exception | None: ...  # 확인 자체가 실패한 경우

    def ensure(self) -> bool: ...   # 프로세스당 1회만 확인. 이후엔 캐시된 판정

    def recheck(self) -> bool: ...  # 캐시를 버리고 다시 확인
```

`on_progress` 콜백이 사라진다. 흘려보낼 자식 출력이 없고 남은 단계가 하나뿐
이라, 화면은 `st.spinner` 로 충분하다.

`is_authenticated()` 의 계약은 그대로 둔다 — **매핑하지 못한 예외는 삼키지
않고 올린다.** 진짜 버그를 숨기지 않기 위해서다.

`_lock`·`_tried`·`_ok` 는 남긴다. 원래 근거 중 "브라우저 창이 하나만 뜨게"는
사라지지만 "탭을 여러 개 열어도 느린 네트워크 확인이 한 번만 돈다"는 그대로
유효하다.

`ensure()` 와 `recheck()` 는 "아직 안 해봤으면 해라" / "무조건 해라" 차이뿐
이므로 공통 몸통은 `_verify()` 로 남긴다.

### 5.3 `probe_error` 가 필요한 이유

그 예외를 **게이트가 받아 보관한다.** 보관하지 않으면 상태가 한 번만 보이고
사라진다. `_verify()` 가 `_tried` 를 True 로 세우므로, Streamlit 이 스크립트를
재실행하면 `ensure()` 가 다시 돌지 않고 예외도 다시 올라오지 않는다. 그러면
두 번째 렌더부터는 "확인 불가" 가 아니라 **만료 배너가 뜬다.** 7.2 가 막으려던
바로 그 혼란이다.

```python
def _verify(self) -> bool:
    self._tried = True
    self._probe_error = None
    try:
        self._ok = self._probe()
    except Exception as error:
        # 게이트에서만 넓게 잡는다. 여기서 새면 화면에 트레이스백이 뜨고
        # 사용자는 무엇이 잘못됐는지 알 수 없다. runner._work 와 같은 근거다.
        self._ok = False
        self._probe_error = error
    return self._ok
```

경계는 유지된다. `services/auth.py` 는 예외를 **보관만** 하고 문구를 만들지
않는다. 문구는 `components/auth_gate.py` 가 그린다.

### 5.4 자격증명 반입 — `import_credentials()`

2.8 에 따라 공개 CLI 를 자식 프로세스로 부른다.

```python
IMPORT_TIMEOUT = 30.0
MAX_PAYLOAD_BYTES = 1 << 20   # storage_state.json 은 수 KB 다


@dataclasses.dataclass(frozen=True, slots=True)
class ImportResult:
    """반입 결과. 쿠키 값은 담지 않는다."""

    ok: bool
    detail: str


def import_credentials(
    payload: bytes,
    runner: RunnerLike = subprocess.run,
) -> ImportResult: ...
```

부르는 명령은 이것뿐이다.

```
sys.executable -m notebooklm auth import-cookies -      (stdin 으로 payload)
```

- `sys.executable` 을 쓴다. `uv` 는 PATH 에 없을 수 있고, 앱은 이미 패키지가
  설치된 인터프리터 안에서 돈다. 지워지는 `run_login` 이 같은 이유로 그렇게
  했다.
- `runner` 를 주입 가능하게 둔다. 사라지는 `popen` 주입과 같은 결이고, 테스트가
  실제 자식 프로세스를 띄우지 않게 한다.
- `MAX_PAYLOAD_BYTES` 를 넘으면 CLI 에 넘기기 전에 거절한다. 정상 입력은 수
  KB 라, 잘못 고른 파일을 일찍 걸러 낸다.
- 반입에 성공해도 이 함수는 **인증 상태를 바꾸지 않는다.** 호출자가 이어서
  `recheck()` 를 부른다. 판정은 `_verify()` 한 곳에서만 일어난다.

경계는 5.3 과 같다. 이 함수는 **성공 여부와 사유만** 돌려주고 화면 문구를
만들지 않는다.

---

## 6. `core/errors.py`

`_LOGIN_HINT` 를 공개 상수 `LOGIN_HINT` 로 승격하고 내용을 교체한다.

현재 문구는 이렇다.

```
인증이 만료되었습니다. 터미널에서 `uv run notebooklm login` 을 다시
실행하세요.
```

컨테이너에는 `uv` 도 터미널도 없다. 새 문구는 **데스크톱 재로그인 → 프로필
디렉터리 복사 → 다시 확인** 순서를 안내하고 상세는 how-to 문서로 넘긴다.

`MAPPED_ERRORS`·`_LOGIN_ERRORS`·`to_message()` 의 분기 구조는 바꾸지 않는다.
2.7 에 따라 세 예외 매핑을 모두 유지한다.

---

## 7. `components/auth_gate.py`

### 7.1 그리는 것

```python
gate = session.get_auth_gate()
if not gate.tried:
    with st.spinner("인증 상태 확인 중"):
        gate.ensure()
if gate.ok:
    return

if gate.probe_error is None:
    st.error(errors.LOGIN_HINT)
else:
    st.error(_probe_failed_text(gate.probe_error))

with st.expander("자격증명 올리기"):
    uploaded = st.file_uploader("storage_state.json", type="json")
    if uploaded is not None and st.button("반입"):
        result = auth.import_credentials(uploaded.getvalue())
        if not result.ok:
            st.error(f"반입하지 못했습니다: {result.detail}")
        elif gate.recheck():
            st.rerun()
        else:
            st.error("반입했지만 인증이 살아나지 않았습니다.")

if st.button("다시 확인"):
    with st.spinner("다시 확인 중"):
        if gate.recheck():
            st.rerun()
```

- `_EXPIRED_HINT` 삭제 — 문구는 `errors.LOGIN_HINT` 에서 온다
- `_run()` 삭제 — 자식 출력을 스트리밍할 일이 없으므로 `st.status` 대신
  `st.spinner`
- "재인증" 버튼 → **"다시 확인"** 버튼
- **업로더는 만료됐을 때만 그려진다.** `gate.ok` 면 이 코드에 닿지 않는다

### 7.1.1 업로드 경로에서 지키는 것

- `st.file_uploader` 가 주는 `UploadedFile` 은 메모리 버퍼다. `getvalue()` 를
  바로 stdin 으로 넘겨 **디스크에 임시 파일을 만들지 않는다.**
- **화면에 쿠키 내용을 절대 표시하지 않는다.** 성공/실패와 사유까지만 보여
  준다. 업로드된 바이트를 로그에도 남기지 않는다.
- 업로드 폼은 **쓰기 전용**이다. 저장된 자격증명을 읽어 가는 경로를 만들지
  않는다. 잘못 쓰였을 때 최악은 덮어쓰기로 인한 서비스 거부다.
- 볼륨에 직접 복사하는 길은 **막지 않는다.** 업로드가 안 될 때의 대체 경로로
  how-to 문서에 함께 적는다(10.1).

### 7.2 판정 실패와 만료를 구분한다

컨테이너의 주 신호인 `_LoginRedirectError` 는 private 이고,
`core/errors.py:17` 이 import 실패에 대비한 폴백을 갖고 있다. 그 폴백이
발동하면 `_LOGIN_REDIRECT_ERRORS` 가 비고, `_LoginRedirectError` 는
`ValueError` 하위라 `MAPPED_ERRORS` 에서 빠지는 순간 `is_authenticated()` 를
**뚫고 올라온다.** 지금은 브라우저 로그인이 덮어 주던 경로가 R1 이후에는 주
경로가 되므로 이 위험이 커진다.

그래서 `auth_gate.render()` 가 5.3 의 `probe_error` 를 보고 두 가지를 구분해
그린다.

| 상황 | 판별 | 화면 |
|---|---|---|
| 만료 | `ok == False`, `probe_error is None` | `errors.LOGIN_HINT` + "다시 확인" |
| 확인 불가 | `probe_error is not None` | `인증 상태를 확인하지 못했습니다({예외 타입})` + "다시 확인" |

**수정 (최종 리뷰, 2026-09-16).** 확인 불가 문구는 예외의 **타입 이름만**
보여 준다. 최초 설계는 `{예외 타입}: {메시지}` 로 메시지까지 이어 붙이는
안이었으나, 이 분기가 잡는 주 대상인 `_LoginRedirectError` 의 메시지 자체가
`"...Final URL: https://accounts.google.com/..."` 형태로 구글 리다이렉트
URL 을 담고 있어 6절이 막으려던 노출을 이 분기가 되살렸다. 메시지 전문은
화면 대신 로그로 보낸다 — `AuthGate._verify()` 가 이미 `logger.exception` 을
부르므로 정보가 사라지지 않는다.

**"다시 확인" 버튼은 두 경우 모두에 나온다.** 확인 불가는 일시적 원인(네트워크
단절)일 수도 있으므로 사용자가 재시도할 길을 막지 않는다.

확인 불가일 때는 `logger.exception` 으로 스택을 남긴다. 화면에는 예외 타입과
메시지만 보이고, 컨테이너 로그에 전체가 남는다.

어느 쪽이든 `st.stop()` 을 부르지 않는다. 라이브러리가 구조를 바꿔도 앱이
트레이스백을 토하지 않고, 원인이 화면과 로그에 남는다.

### 7.3 인증 실패가 앱을 막는 범위 — 변경 없음

`app.py` 의 근거가 그대로 유효하다.

> 인증이 안 돼도 페이지는 그대로 띄운다. 질문 관리와 이력은 로컬 DB 만
> 쓰므로 인증 없이도 쓸 수 있다.

`schema_gate` 와 대비된다. 스키마가 깨지면 모든 화면이 죽지만 인증 만료는
일부 화면만 못 쓴다. (R4 에서 이력이 Outline 을 읽게 되면 이 전제가 바뀐다.
그때 다시 본다.)

---

## 8. `pyproject.toml`

```toml
dependencies = [
    "notebooklm-py==0.8.1",           # [browser] 제거 → playwright 빠짐
    "streamlit>=1.62.0",
]

[dependency-groups]
dev = [
    "notebooklm-py[browser]==0.8.1",  # 데스크톱 재로그인용
    "mypy>=2.3.1",
    "pytest>=9.1.1",
    "ruff>=0.16.5",
]
```

`[browser]` 를 기본에서 빼면 **데스크톱에서도 `notebooklm login` 이 안 된다.**
재로그인 절차 자체가 막히므로 dev 그룹으로 옮긴다. 로컬은 `uv sync` 로
브라우저를 갖고, R2 의 이미지는 `uv sync --no-dev` 로 뺀다. dev 그룹에는 이미
`mypy`·`pytest`·`ruff` 가 있어 "이미지에서 빠져야 할 것" 과 성격이 같다.

---

## 9. 테스트

### 9.1 삭제

`tests/services/test_auth.py` 267줄 중 절반 이상이 브라우저 로그인 테스트다.

- 헬퍼 3개: `FakeStdout`, `FakeProcess`, `fake_popen_factory`
- `test_login_*` 7개: 인터프리터 경로, 출력 스트리밍, 종료 코드, 타임아웃 킬
- `test_gate_logs_in_when_check_fails`,
  `test_gate_reports_failure_when_login_also_fails`
- `test_relogin_rechecks_before_opening_a_browser`,
  `test_relogin_logs_in_when_the_recheck_also_fails`
- `test_gate_never_leaves_the_progress_box_empty` (`CHECK_NOTICE` 소멸)
- `tests/test_components.py` 의
  `test_auth_gate_offers_relogin_when_recovery_fails`,
  `test_auth_gate_relogins_when_the_button_is_pressed`

### 9.2 유지

- `test_probe_reports_authenticated_when_client_opens`
- `test_probe_reports_expired_on_login_redirect`
- **`test_probe_lets_unmapped_errors_through`** — 7.2 의 계약을 지키는 유일한
  테스트다. 새 배너 분기가 이 계약 위에 얹힌다
- `test_gate_checks_only_once`, `test_gate_reports_whether_it_has_run`
- `test_gate_skips_login_when_already_authenticated` →
  `test_gate_caches_the_probe_result` 로 개명
- `tests/test_components.py:test_auth_gate_stays_quiet_when_authenticated`

### 9.3 신규

```
tests/services/test_auth.py
  test_recheck_probes_again_ignoring_the_cache
  test_recheck_revives_a_failed_gate      ← 재시드 시나리오. R1 의 핵심 가치
                                            (프로필 교체 → 다시 확인 → 되살아남)
  test_gate_records_a_failed_probe        ← 5.3. probe 가 던진 예외가
                                            probe_error 에 담기고 ok 는 False
  test_gate_keeps_the_probe_error_cached  ← 5.3 의 이유 그 자체. ensure() 를
                                            두 번 불러도 probe_error 가 남아
                                            있는지 (재실행 시나리오)
  test_recheck_clears_a_stale_probe_error ← 되살아나면 probe_error 도 지워짐

  test_import_credentials_feeds_the_payload_to_stdin
                                          ← 5.4. sys.executable 로 부르고
                                            payload 가 stdin 으로 가는지
  test_import_credentials_reports_a_nonzero_exit
  test_import_credentials_rejects_an_oversized_payload
  test_import_credentials_leaves_the_gate_alone
                                          ← 판정은 recheck() 가 한다.
                                            반입 함수가 ok 를 건드리지 않는지

tests/test_components.py
  test_auth_gate_offers_recheck_when_expired
  test_auth_gate_rechecks_when_the_button_is_pressed
  test_auth_gate_separates_a_failed_probe_from_an_expiry
                                          ← 7.2. probe 가 매핑 안 된 예외를
                                            던지면 LOGIN_HINT 가 아니라
                                            "확인 불가" 문구가 나오고, 앱이
                                            트레이스백 없이 계속 뜨는지
  test_auth_gate_imports_an_uploaded_credential
                                          ← 업로드 → 반입 → recheck 한 흐름
  test_auth_gate_reports_a_failed_import
  test_auth_gate_hides_the_uploader_when_authenticated
                                          ← gate.ok 면 업로더를 그리지 않는지
```

### 9.4 딸려 바뀌는 곳

```
tests/conftest.py:30
  auth.AuthGate(probe=lambda: True, login=lambda on_progress: True)
  → auth.AuthGate(probe=lambda: True)

tests/core/test_errors.py
  test_auth_error_tells_user_to_log_in_again
  test_headless_login_required_tells_user_to_log_in_again
  test_login_redirect_tells_user_to_log_in_again
  → 문구 리터럴 대신 errors.LOGIN_HINT 를 참조하게 한다. 문구가 또 바뀌어도
    테스트가 따라온다.
```

`tests/test_app.py:test_app_boots_with_all_pages` 는 `stub_auth_gate` 를
거치므로 그대로 통과해야 한다. **회귀 감지선이다.**

### 9.5 순서

테스트를 먼저 쓴다.

1. `errors.LOGIN_HINT` 상수화 + 문구 교체 (test_errors 갱신 → 구현)
2. `AuthGate.recheck()` 와 `probe_error` (신규 테스트 → 구현)
3. `auth.py` 삭제 작업 (죽은 테스트 제거 → 코드 제거)
4. `import_credentials()` (신규 테스트 → 구현)
5. `auth_gate.py` 재작성 — 배너 · 다시 확인 · 업로더 (신규 테스트 → 구현)
6. `pyproject.toml` 의존성 재배치 (`uv sync --no-dev` 로 확인)
7. README · 신규 문서

3을 2 뒤에 두는 이유는, `recheck()` 가 먼저 서 있어야 `relogin()` 을 지울 때
대체재가 이미 검증된 상태이기 때문이다.

3에서는 `import subprocess`·`import sys` 까지 **일단 함께 지운다.** 5.1 이
"유지"라고 적은 것은 최종 상태를 말한다. 3 시점에는 쓰는 곳이 없어 ruff 가
unused import 로 잡으므로, 4에서 필요한 것만 다시 들여온다.

검증은 4단 그대로다.

```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

---

## 10. 문서

### 10.1 신규 — `docs/how-to/2026-09-16-auth-reseed.md`

두 경로를 적는다. **업로드가 정본이고, 볼륨 직접 복사는 대체 경로다.**

**정본 — 대시보드 업로드**

```
데스크톱   uv run notebooklm login          # 브라우저 로그인
             → ~/.notebooklm/profiles/default/storage_state.json

대시보드   만료 배너 → [자격증명 올리기] → 그 파일을 업로드 → [반입]
             → 자동으로 재확인까지 끝난다
```

**대체 — 볼륨 직접 복사** (업로드가 안 될 때)

2.6 에서 확인한 운영 조건을 명시한다.

- **디렉터리 전체를 복사할 것** (락·회전 상태가 형제 파일로 있다)
- **볼륨은 쓰기 가능할 것**

**복사 대상은 컨테이너 내부가 아니라 호스트의 볼륨 디렉터리다.** 바인드
마운트가 호스트 경로를 컨테이너 경로에 비춰 주므로, 사람은 호스트 쪽에 파일을
놓기만 하면 된다. 컨테이너는 건드리지 않는다. `docker cp` 로 컨테이너 안에
직접 넣으면 컨테이너를 다시 만들 때 사라진다.

```
호스트 (홈서버)                        컨테이너 내부
./data/notebooklm/              ←──→  /data/notebooklm/
      profiles/default/                     profiles/default/
```

경로는 R2 에서 확정되었다 — 호스트 `./data/notebooklm/`, 컨테이너
`/data/notebooklm/`. 설계는
`docs/superpowers/specs/2026-09-16-container-deploy-design.md` 에 있다.

### 10.2 README 수정 — 틀리게 되는 서술 4곳

| 위치 | 현재 | 변경 |
|---|---|---|
| 요구사항 표 | `notebooklm-py[browser]==0.8.1` | `notebooklm-py==0.8.1` + dev 그룹 설명 |
| `[browser]` extras 설명 | "크로미움을 함께 설치합니다" | dev 전용임을 명시 |
| "첫 실행 — 인증" | "크로미움 창이 자동으로 열립니다" | 사람이 직접 `notebooklm login` |
| 같은 절 | "화면에 재인증 버튼이 나타납니다" | "다시 확인" 버튼 + 재시드 문서 링크 |

---

## 11. 건드리는 파일

| 파일 | 변경 |
|---|---|
| `src/notebooklm_st/services/auth.py` | 브라우저 로그인 제거 + `recheck()`·`probe_error`·`import_credentials()` (237줄 → ~130줄) |
| `src/notebooklm_st/components/auth_gate.py` | 재작성 — 배너·다시 확인·업로더 (67줄 → ~75줄) |
| `src/notebooklm_st/core/errors.py` | `LOGIN_HINT` 상수화 + 문구 교체 |
| `pyproject.toml` | `[browser]` 를 dev 그룹으로 |
| `tests/services/test_auth.py` | 삭제·개명·신규 |
| `tests/test_components.py` | auth_gate 테스트 3개 교체 |
| `tests/core/test_errors.py` | 문구 assertion 을 상수 참조로 |
| `tests/conftest.py` | `stub_auth_gate` 에서 `login` 인자 제거 |
| `README.md` | 인증 관련 서술 4곳 |
| `docs/how-to/2026-09-16-auth-reseed.md` | 신규 |

건드리지 않는 것: `services/nlm.py`, `services/runner.py`, `services/runs.py`,
`services/store.py`, `services/questions.py`, `services/run_history.py`,
`pages/` 전체, `core/` 의 나머지.

`nlm.default_client_factory` 의 `allow_headless=True` 도 유지한다. 컨테이너
에서는 조용히 `UNAVAILABLE` 이 되고 로컬에서는 여전히 유효하다.

---

## 12. 미검증 가정

1. **쿠키 수명.** L1/L2 로 갱신되는 세션이 실제로 얼마나 버티는지는 코드로
   확정할 수 없다. 브라우저 로그인 세션과 같은 성질이라 몇 달일 수도, 구글이
   보안 이벤트(비밀번호 변경·비정상 접속)를 감지하면 며칠일 수도 있다.
   홈서버라 공인 IP 가 고정인 점은 유리하다. **재시드 절차와 명확한 만료
   안내가 이 불확실성에 대한 답이다.**
2. **`is_authenticated()` 의 실제 개통.** 2.4 는 컨텍스트 객체가 만들어지는
   것까지 확인했다. 실제 자격증명으로 여는 것은 확인하지 않았다. 다만 열기가
   실패하면 매핑된 예외로 `False` 가 되므로 설계가 기대하는 동작과 같다.
3. **`uv sync --no-dev` 가 playwright 를 확실히 뺀다는 것.** 구현 5단계에서
   실제로 확인한다.
4. ~~**`auth import-cookies` 의 실패 출력에 쿠키 값이 섞이지 않는다는
   것.**~~ **검증 완료 (최종 리뷰, 2026-09-16).** 5.4 가 stderr 를
   `ImportResult.detail` 에 담고 7.1 이 그것을 화면에 보여 준다. 설치된
   `notebooklm-py` 소스를 직접 읽어 확인했다.
   - `notebooklm/_app/login_cookie.py:90` — 실패를 나르는
     `BrowserCookieProbeFailure` 의 독스트링이 이미
     *"Cookie-probe failure without raw credential-bearing values"*
     라고 계약을 명시한다.
   - 같은 파일 `:311-320`(`EMPTY_REQUIRED`)과 `:366-372`
     (`REQUIRED_DROPPED`)의 실패 메시지는 쿠키 **이름**
     (`empty_required`, `outcome.missing_required`,
     `outcome.present_names`)만 문자열에 넣는다. `cookie["value"]`
     는 존재 여부를 부울로만 검사하고 메시지에 이어 붙이지 않는다.
   - `notebooklm/cli/_cookie_import.py:44-45` — JSON 파싱 실패는
     `f"Invalid JSON: {exc}"` 로, `json.JSONDecodeError` 의 문자열
     표현은 줄·열 위치만 담고 원문 내용은 담지 않는다.
   - 결론: 실패 경로 전체에서 화면에 닿는 문자열은 쿠키 이름과 파싱
     위치뿐이다. `detail` 을 종료 코드로 다시 가공할 필요는 없다.
5. **데스크톱 앱과 컨테이너 앱이 같은 프로필을 동시에 쓸 때.** 개발용으로
   데스크톱에서 앱을 띄우면 그 앱도 `~/.notebooklm/profiles/default/` 를 읽고
   **각자 쿠키를 회전시킨다.** 라이브러리가 락 파일 4개를 두지만 그것은 한
   파일 시스템 안의 이야기이고, 데스크톱과 홈서버는 별개다. 서로의 갱신을
   덮어써 양쪽이 함께 죽을 가능성이 있다. **둘을 동시에 오래 띄우지 않는 것을
   how-to 문서에 적는다.** 실제로 충돌하는지는 확인하지 않았다.

---

## 13. 범위 밖

- **Slack 알림** — R6. R5 까지는 무인으로 도는 것이 없다
- **Dockerfile · GitHub Actions · 볼륨 · TZ** — R2
- **yt-dlp · 메타데이터 · YAML frontmatter** — R3
- **Outline 저장** — R4
- **정리본** — R5
- **스케줄러 · 실행 큐** — R6
- 인증 만료 시 화면 차단 범위 변경 — 현재대로 배너만 그린다
- 마스터 토큰 (2.3) · L3 헤드리스 재인증 (2.2)
- **`login --browser-cookies` 기반 경량 재시드** — 평소 쓰는 브라우저의 세션
  쿠키를 그대로 가져오므로, 서버 쪽 자격증명을 폐기하려면 본인 브라우저까지
  함께 로그아웃된다. 윈도우 동작도 검증하지 못했다.
- **`AuthGate` 의 `ok → failed` 전이 (최종 리뷰, 2026-09-16 기록).**
  5.2 는 `ensure()`/`recheck()` 만 정의했고, 5.3 이 근거를 대는 상태
  전이는 `failed → ok`(재로그인 뒤 `recheck()`) 하나뿐이다. `ok` 가
  `True` 로 세워진 뒤 그걸 다시 `False` 로 되돌리는 경로가 없다 —
  `render()` 는 `gate.ok` 가 참이면 그대로 반환하고 끝나므로, 앱이
  뜬 뒤 첫 확인이 통과하면 그 프로세스가 사는 동안 배너·업로더·
  "다시 확인" 버튼은 다시 그려지지 않는다. 결과: 배너는 **기동
  판정**일 뿐이고, 떠 있는 도중에 세션이 죽으면(장기 실행 프로세스의
  일반적 경우) 재시드 경로에 닿으려면 먼저 **앱을 재시작**해야 한다
  (반영: `core/errors.py` 의 `LOGIN_HINT`,
  `docs/how-to/2026-09-16-auth-reseed.md`, `README.md`).
  이 전이를 제대로 닫으려면 실행 실패 경로(`services/runner.py`)가
  게이트를 알고 실패 시 `AuthGate.invalidate()` 같은 것을 불러야
  한다. 그건 이번 릴리스가 건드리지 않기로 한 `runner` 를 건드리는
  일이라 11절이 정한 경계 밖이다. **R2(컨테이너화) 작업으로 미룬다.**

### 13.1 업로드 UI 의 전제

5.4·7.1 의 자격증명 업로드는 **앱이 외부에 노출되지 않는다는 전제** 위에 있다.
비노출이면 업로드 폼은 홈 네트워크 안에서만 닿고, 폼 자체는 쓰기 전용이라
저장된 자격증명이 새어 나갈 경로가 아니다.

**이 전제가 깨지면 — 앱을 외부에 노출하기로 바꾸면 — 업로드 UI 를 제거하고
볼륨 직접 복사로 되돌린다.** 계정 동등 자격증명을 인터넷에서 닿는 웹 폼으로
받는 구조는 별도 검토 없이 두지 않는다.

같은 이유로, 앱과 대시보드 사이 구간이 평문 HTTP 라는 점을 how-to 문서에
적는다. 홈 네트워크 안이라도 같은 Wi-Fi 의 다른 기기에는 보인다. Tailscale 등
암호화된 경로로 접근하면 이 구간이 덮인다.
