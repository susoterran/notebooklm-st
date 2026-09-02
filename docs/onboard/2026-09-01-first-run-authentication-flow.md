# 최초 실행 시 인증 과정

> 처음 이 프로젝트를 보는 동료를 위한 온보딩 문서.
> 대상 코드: `services/auth.py` · `components/auth_gate.py` · `session.py` ·
> `services/nlm.py` · `core/errors.py`
> 작성 2026-09-01 · 기준 커밋 `38a390f`

---

## 0. 30초 요약

이 앱은 **로그인 화면이 없다.** 아이디·비밀번호를 받지 않고, 세션 쿠키를 직접
저장하지도 않는다. 인증은 전부 **`notebooklm-py` 라이브러리와 그 CLI 에 위임**하고,
앱은 다음 세 가지만 한다.

1. **확인한다** — 저장된 인증으로 클라이언트가 열리는지 열어 본다.
2. **안 되면 브라우저를 띄운다** — `notebooklm login` 을 자식 프로세스로 실행한다.
3. **결과를 화면에 보여 준다** — 진행 문구를 흘리고, 실패하면 재인증 버튼을 남긴다.

`uv run streamlit run src/notebooklm_st/app.py` (또는 `.\run.ps1`) 로 처음 띄우면,
저장된 인증이 없으므로 **크로미움 창이 자동으로 뜬다.** 구글 로그인을 마치면
CLI 가 알아서 감지·저장하고 종료하며, 앱은 이어서 진행한다.
**터미널에 아무것도 입력할 필요가 없다.**

---

## 1. 핵심 구성요소와 역할

| # | 구성요소 | 위치 | 역할 |
|---|---|---|---|
| 1 | `main()` | `app.py:24` | 진입점. 스키마 게이트 → 페이지 등록 → **인증 게이트** → 페이지 실행 순으로 조립 |
| 2 | `auth_gate.render()` | `components/auth_gate.py:23` | **UI 담당.** 진행 상자를 그리고, 실패 시 안내와 재인증 버튼을 낸다 |
| 3 | `session.get_auth_gate()` | `session.py:39` | `@st.cache_resource` 싱글턴. **모든 탭·세션이 같은 게이트 하나**를 보게 한다 |
| 4 | `auth.AuthGate` | `services/auth.py:136` | **상태 담당.** "이미 확인했나"(`tried`) · "결과가 뭐였나"(`ok`) 를 프로세스 수명 동안 들고 있고, 락으로 동시 실행을 막는다 |
| 5 | `auth.is_authenticated()` | `services/auth.py:59` | **확인 담당.** 클라이언트를 열었다 닫아 본다. 열리면 인증 살아 있음 |
| 6 | `auth.run_login()` | `services/auth.py:81` | **복구 담당.** `notebooklm login` 을 자식 프로세스로 띄우고 출력을 중계 |
| 7 | `nlm.default_client_factory()` | `services/nlm.py:109` | 저장된 인증으로 클라이언트를 여는 팩토리. `allow_headless=True` 로 **라이브러리의 무인 복구를 켠다** |
| 8 | `errors.MAPPED_ERRORS` | `core/errors.py:23` | "인증 만료로 볼 예외" 목록. 이 목록에 없는 예외는 **삼키지 않는다** |

역할이 세 겹으로 나뉜 것이 이 설계의 핵심이다.

```
UI(auth_gate)  ─▶  상태(AuthGate)  ─▶  동작(is_authenticated / run_login)
   Streamlit 의존       Streamlit 무의존        Streamlit 무의존
```

`services/` 는 `import streamlit` 을 하지 않는다(프로젝트 규칙). 그래서 `AuthGate` 는
진행 문구를 직접 그리지 않고 **`on_progress` 콜백**으로 밖에 넘긴다. UI 쪽에서
`st.write` 를 그 콜백으로 꽂아 준다(`auth_gate.py:61`). 덕분에 인증 로직 전체가
Streamlit 없이 pytest 로 검증된다.

---

## 2. 전체 호출 순서

최초 실행(저장된 인증이 없는 상태) 기준이다.

```
uv run streamlit run src/notebooklm_st/app.py
  │
  └─ app.main()                                        app.py:24
       ├─ st.set_page_config(...)
       ├─ schema_gate.render()                         ← DB 검사 (인증과 무관)
       ├─ st.navigation([...])                         ← 페이지 등록만, 실행은 아직
       │
       ├─ auth_gate.render()                           auth_gate.py:23
       │    ├─ session.get_auth_gate()                 session.py:39  (싱글턴)
       │    ├─ if not gate.tried:
       │    │    └─ _run(gate.ensure, "인증 확인 중")   auth_gate.py:47
       │    │         └─ st.status(...) 상자 열기
       │    │              └─ gate.ensure(st.write)    auth.py:176
       │    │                   └─ with self._lock:    ← 탭 여러 개 동시 진입 차단
       │    │                        └─ _verify(...)   auth.py:211
       │    │                             ├─ self._tried = True
       │    │                             ├─ on_progress("인증 상태 확인 중")
       │    │                             ├─ ① is_authenticated()      auth.py:59
       │    │                             │     └─ asyncio.run(_open_once(...))
       │    │                             │          └─ nlm.default_client_factory()
       │    │                             │               └─ NotebookLMClient
       │    │                             │                    .from_storage(allow_headless=True)
       │    │                             │                        ├─ 토큰 재추출
       │    │                             │                        ├─ 쿠키 회전
       │    │                             │                        └─ 무인 재인증(headless)
       │    │                             │
       │    │                             └─ ② ①이 False 일 때만: run_login()  auth.py:81
       │    │                                   └─ subprocess.Popen(
       │    │                                        [sys.executable, "-m",
       │    │                                         "notebooklm", "login"])
       │    │                                        └─ 크로미움 창 → 구글 로그인
       │    │                                   └─ stdout 한 줄씩 → on_progress
       │    │                                   └─ process.wait() → 종료 코드
       │    │
       │    └─ gate.ok 이면 True 반환 / 아니면 st.error + 재인증 버튼
       │
       └─ navigation.run()                             ← 선택된 페이지 렌더
```

**중요한 점 두 가지.**

- `auth_gate.render()` 의 반환값을 `main()` 은 **쓰지 않는다.** 인증이 실패해도
  페이지는 그대로 뜬다. 질문 관리·이력 화면은 로컬 SQLite 만 쓰므로 인증 없이도
  동작하기 때문이다(`app.py:27-28`).
- `st.navigation(...)` 등록이 `auth_gate.render()` **앞**이다. 인증 상자가 도는 동안에도
  사이드바 메뉴가 보인다.

---

## 3. 단계별 입력 / 출력

### 단계 1 — 게이트 획득

| | |
|---|---|
| **호출** | `session.get_auth_gate()` — `session.py:39` |
| **입력** | 없음 |
| **출력** | `auth.AuthGate` 인스턴스 |
| **부수효과** | 없음 |

`@st.cache_resource` 라서 **프로세스에 하나만** 만들어진다. 탭을 세 개 열어도,
스크립트가 위젯 조작마다 재실행돼도 같은 객체다. `st.session_state` 는 탭마다
별개라 이 용도로 못 쓴다(`session.py:43-45`).

### 단계 2 — 이미 돌았는지 확인

| | |
|---|---|
| **호출** | `gate.tried` — `auth.py:167` |
| **입력** | 없음 |
| **출력** | `bool` |
| **분기** | `False` → 단계 3 진행 / `True` → 건너뛰고 단계 8 |

Streamlit 은 **버튼 하나 누를 때마다 스크립트를 처음부터 다시 실행**한다. 이 표식이
없으면 클릭할 때마다 인증을 확인하게 되고, 화면이 계속 깜빡인다.

### 단계 3 — 진행 상자 열기

| | |
|---|---|
| **호출** | `auth_gate._run(gate.ensure, "인증 확인 중")` — `auth_gate.py:47` |
| **입력** | 인증 동작 함수, 상자에 띄울 라벨 |
| **출력** | `bool` (성공 여부) |
| **부수효과** | `st.status` 상자를 그리고, 진행 문구를 그 안에 흘린다 |

`action(st.write)` 로 **`st.write` 자체를 콜백으로 넘긴다**(`auth_gate.py:61`).
자식 프로세스가 뱉는 줄이 그대로 상자 안에 쌓인다.

### 단계 4 — 락 잡고 검증 시작

| | |
|---|---|
| **호출** | `AuthGate.ensure(on_progress)` → `_verify(on_progress)` — `auth.py:176`, `auth.py:211` |
| **입력** | `Callable[[str], None]` 진행 콜백 |
| **출력** | `bool` |
| **부수효과** | `self._tried = True`, `self._ok` 갱신, `on_progress("인증 상태 확인 중")` |

```python
self._ok = self._probe() or self._login(on_progress)
```

**한 줄이 전부다.** `or` 의 단축 평가 덕분에 확인이 성공하면 로그인은 아예 부르지 않는다.

`on_progress(CHECK_NOTICE)` 를 먼저 부르는 이유는, 확인 단계가 콜백을 한 번도
부르지 않기 때문이다. 이 줄이 없으면 상자가 **빈 채로 몇 초 멈춰 있고**, 실패로
끝나면 단서가 한 줄도 안 남는다(`auth.py:29-34`).

### 단계 5 — 인증 확인 (프로브)

| | |
|---|---|
| **호출** | `auth.is_authenticated(client_factory)` — `auth.py:59` |
| **입력** | `nlm.ClientFactory` (기본값 `nlm.default_client_factory`) |
| **출력** | `True` = 인증 살아 있음 / `False` = 만료 |
| **예외** | `MAPPED_ERRORS` 에 **없는** 예외는 그대로 위로 던진다 |

```python
try:
    asyncio.run(_open_once(client_factory))
except errors.MAPPED_ERRORS:
    return False
return True
```

`_open_once()` 는 `async with client_factory():` 로 **열었다가 바로 닫는다**
(`auth.py:228`). 요청을 하나도 보내지 않는다 — **여는 순간 인증이 확인**되기 때문이다.

여기서 `except Exception:` 을 쓰지 않은 게 중요하다. 네트워크 설정 오류나 코드 버그까지
"인증 만료"로 오진하면, 앱은 멀쩡한 인증을 두고 브라우저를 띄우고 사용자는 원인을
영영 모른다. 그래서 **화면 문구로 번역 가능한 예외만** 만료로 본다.

`MAPPED_ERRORS` 에 `_LoginRedirectError` 가 섞여 있는 게 눈에 띄는데
(`core/errors.py:8-21`), 토큰 조회가 구글 로그인 화면으로 튕길 때 라이브러리가
이걸 **공개 예외가 아니라 private `ValueError` 하위 클래스**로 올리기 때문이다.
직접 잡지 않으면 화면에 내부 클래스명과 구글 URL 이 그대로 노출된다.
private 이라 위치가 바뀔 수 있어 `try/except ImportError` 로 감싸 뒀다.

### 단계 5-a — 라이브러리의 무인 복구 (앱 코드 밖)

| | |
|---|---|
| **호출** | `notebooklm.NotebookLMClient.from_storage(allow_headless=True)` — `nlm.py:129` |
| **입력** | 라이브러리가 관리하는 저장소의 쿠키·토큰 (앱은 이 파일을 직접 읽거나 쓰지 않는다) |
| **출력** | 열린 클라이언트 컨텍스트 / 또는 예외 |

라이브러리가 **3단계로 스스로 복구를 시도**한다.

| 순서 | 시도 | 기본 동작 |
|---|---|---|
| 1 | 토큰 재추출 | 항상 |
| 2 | 쿠키 회전 | 항상 |
| 3 | 저장된 브라우저 프로필로 **무인 재인증** | **기본 꺼짐 → 앱이 켠다** |

`allow_headless=True` 를 넘기는 게 이 앱의 선택이다. 대가는 **실패하는 경로가 몇 초
길어지는 것뿐**이고, 성공하면 사용자가 아무것도 하지 않아도 인증이 되살아난다
(`nlm.py:112-120`). 즉 **"인증 확인"이라는 이름의 이 단계가 사실상 복구까지 겸한다.**

> 최초 실행에서는 저장된 것이 아무것도 없으므로 세 시도가 모두 실패하고 단계 6 으로 간다.

### 단계 6 — 브라우저 로그인

| | |
|---|---|
| **호출** | `auth.run_login(on_progress, timeout=420.0, popen=subprocess.Popen)` — `auth.py:81` |
| **입력** | 진행 콜백, 제한 시간, Popen 함수(테스트 주입용) |
| **출력** | `True` = 종료 코드 0 / `False` = 그 외·타임아웃 |
| **부수효과** | 크로미움 창이 뜨고, 성공 시 라이브러리 저장소에 인증이 저장된다 |

```python
process = popen(
    [sys.executable, "-m", "notebooklm", "login"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,
    text=True, encoding="utf-8", errors="replace", bufsize=1,
)
```

인자 하나하나가 이유를 갖는다.

| 인자 | 이유 |
|---|---|
| `sys.executable -m notebooklm` | **`uv` 로 부르지 않는다.** `uv` 는 PATH 에 없을 수 있고, 앱은 이미 notebooklm 이 설치된 venv 안에서 돌고 있다. 자기 인터프리터가 가장 확실하다 |
| `stdin=DEVNULL` | 터미널 입력이 필요 없다. CLI 가 로그인을 **스스로 감지**하고 저장한 뒤 끝난다 |
| `stderr=STDOUT` | 오류도 같은 스트림으로 합쳐 한 상자에 보여 준다 |
| `bufsize=1` + `text=True` | 줄 단위 버퍼링. 실시간으로 흘려야 "멈춘 것처럼" 보이지 않는다 |
| `errors="replace"` | 자식 출력의 인코딩 문제로 앱이 죽지 않게 한다 |

읽기 루프는 `stdout` 을 한 줄씩 `on_progress` 로 넘기고, 매 줄마다 마감 시각을 본다.

**실패는 반드시 한 줄을 남긴다**(`auth.py:96-98`). 자식이 아무 말도 못 하고 죽으면
화면에 빈 상자와 "실패"만 남아 단서가 없기 때문에, 종료 코드(`auth.py:132`)나
타임아웃(`auth.py:129`)을 직접 문구로 만들어 넣는다.

`LOGIN_TIMEOUT = 420.0` 은 **뒷받침**이다. CLI 자신이 브라우저를 300초까지만
기다리므로 보통은 그쪽이 먼저 끝난다(`auth.py:22-27`).

### 단계 7 — 결과 기록

| | |
|---|---|
| **위치** | `_verify()` 의 `self._ok = ...` — `auth.py:224` |
| **출력** | `gate.ok`, `gate.tried` 갱신 후 락 해제 |

### 단계 8 — 화면 분기

| `gate.ok` | 화면 |
|---|---|
| `True` | 상자가 **"인증되었습니다"** 로 접히고(`expanded=False`) `render()` 가 `True` 반환 |
| `False` | 상자가 **"인증하지 못했습니다"** 로 펼쳐진 채 남고, `st.error(_EXPIRED_HINT)` 와 **재인증 버튼** 표시 |

실패 시 상자를 펼친 채 두는 것(`expanded=not ok`, `auth_gate.py:65`)은 의도적이다.
성공은 볼 것이 없지만 **실패는 자식 프로세스 출력이 유일한 단서**다.

---

## 4. 재인증 버튼 경로

실패 후 사용자가 **[재인증]** 을 누르면 자동 경로와 **다른 메서드**를 탄다.

```
st.button("재인증") → gate.relogin(st.write)   auth.py:193
                        └─ with self._lock:
                             └─ _verify(...)    ← tried 검사 없이 무조건 다시
                                  ├─ probe() 다시 확인      ← 핵심
                                  └─ 실패 시에만 run_login()
                      → 성공하면 st.rerun()
```

`ensure()` 와 `relogin()` 의 차이는 **`tried` 검사 유무 하나**다.

- `ensure()` — 이미 돌았으면 저장된 결과를 그대로 돌려준다(자동 1회용).
- `relogin()` — 검사를 건너뛰고 `_verify()` 를 다시 돈다(사용자 요청).

**`relogin()` 이 브라우저부터 띄우지 않고 확인을 먼저 하는 이유**가 중요하다
(`auth.py:196-200`). 실패 판정은 이 객체가 프로세스가 끝날 때까지 들고 있는데,
그 사이 **다른 경로로 인증이 되살아날 수 있다** — 사용자가 터미널에서 직접
로그인했거나, 구글 쪽 세션이 복구됐거나. 확인 없이 브라우저부터 띄우면
멀쩡한 인증을 두고 헛수고를 하고, **그 로그인마저 실패하면 앱은 영영 만료 상태로
남는다.** 확인은 몇 초면 끝난다.

성공 시 `st.rerun()` 을 부르는 건, 인증이 필요해서 못 그렸던 화면을 즉시 다시
그리기 위해서다.

---

## 5. 최초 실행에서 실제로 보이는 것

```
1. .\run.ps1 실행
2. 브라우저에서 http://127.0.0.1:8611 열림
3. 화면 위쪽에 상자: "인증 확인 중"
       인증 상태 확인 중                     ← CHECK_NOTICE
4. (몇 초) 저장된 인증이 없어 확인 실패
5. 크로미움 창이 자동으로 뜬다               ← run_login
       Opening Chromium for Google login...  ← 자식 출력이 상자에 흐른다
6. 구글 계정으로 로그인
7. CLI 가 감지 → 저장 → 종료 코드 0
8. 상자가 "인증되었습니다" 로 접힌다
9. 질의 화면 사용 가능
```

이미 로그인된 브라우저 프로필이 남아 있으면 **5~6 단계에서 사용자가 아무것도 하지
않아도 통과**한다(`auth.py:93-94`).

두 번째 실행부터는 3~8 이 통째로 생략된다. 단계 5-a 의 무인 복구가 조용히
성공하기 때문이다.

---

## 6. 알아 두면 헷갈리지 않는 것

**① 인증 실패해도 앱은 뜬다.** `main()` 이 `auth_gate.render()` 의 반환값을 무시한다.
질문 관리·이력은 로컬 DB 만 쓰므로 인증 없이 쓸 수 있다. 반면 `schema_gate` 는
`st.stop()` 으로 **정말 멈춘다** — DB 가 깨지면 어떤 화면도 못 그리기 때문이다.
두 게이트의 강도가 다른 건 의도된 차이다.

**② 만료 안내 문구가 두 곳에 있다.** 서로 다른 시점을 위한 것이다.

| 문구 | 위치 | 언제 |
|---|---|---|
| "재인증을 누르면 … 브라우저 창이 열립니다" | `auth_gate._EXPIRED_HINT` | **기동 시** 게이트가 실패했을 때 |
| "터미널에서 `uv run notebooklm login` 을 다시 실행하세요" | `errors._LOGIN_HINT` | **질의 파이프라인 도중** 만료됐을 때 |

**③ 락은 스레드용이지 프로세스용이 아니다.** `threading.Lock` 은 같은 프로세스 안의
Streamlit 세션 스레드들을 막는다. 앱을 두 번 띄우면 브라우저 창이 두 개 뜬다.

**④ 앱은 쿠키 파일을 모른다.** 저장·읽기·갱신이 전부 `notebooklm-py` 안에서 일어난다.
앱 코드에 인증 파일 경로가 등장하지 않는 것은 누락이 아니라 경계다.

---

## 7. 테스트 지도

인증 로직 전체가 **Streamlit 없이** 검증된다. `AuthGate` 가 `probe` · `login` 을
생성자 인자로 받고(`auth.py:145`), `run_login` 이 `popen` 을 인자로 받기 때문이다.

| 테스트 | 확인하는 것 |
|---|---|
| `test_auth.py:87` | 클라이언트가 열리면 인증된 것으로 본다 |
| `test_auth.py:92` | 로그인 리다이렉트(private 예외)를 만료로 본다 |
| `test_auth.py:99` | **매핑 안 되는 예외는 삼키지 않는다** |
| `test_auth.py:105` | `uv`·PATH 가 아니라 `sys.executable` 로 CLI 를 부른다 |
| `test_auth.py:116` | 자식 출력을 한 줄씩 콜백으로 넘긴다 |
| `test_auth.py:141` | 타임아웃 시 자식을 죽이고 실패로 돌려준다 |
| `test_auth.py:153` | **아무 말 없이 죽은 자식도 종료 코드는 알려 준다** |
| `test_auth.py:197` | 자동 확인은 한 번만 돈다 |
| `test_auth.py:207` | 인증이 살아 있으면 브라우저를 안 띄운다 |
| `test_auth.py:231` | **재인증은 브라우저 전에 다시 확인한다** |
| `test_auth.py:251` | 진행 상자를 빈 채로 두지 않는다 |

굵게 표시한 세 개가 이 모듈의 설계 의도를 그대로 박아 둔 테스트다. 인증 코드를
고칠 때 이 셋이 깨지면 설계를 되돌린 것이니 멈추고 다시 보는 게 좋다.

---

## 8. 정리

- 인증 **상태**는 `AuthGate` 하나가, **동작**은 `is_authenticated`/`run_login` 이,
  **표시**는 `auth_gate` 가 맡는다. 셋이 콜백 하나로 이어진다.
- `self._probe() or self._login(on_progress)` — 흐름 전체가 이 한 줄이다.
- "확인" 단계가 사실은 **복구까지 겸한다**(`allow_headless=True`). 브라우저까지 가는 건
  그 무인 복구가 전부 실패했을 때뿐이다.
- 최초 실행은 브라우저 로그인이 뜨는 게 **정상**이고, 터미널 입력은 필요 없다.
- 실패 경로는 항상 **한 줄이라도 단서를 남긴다**. 이게 이 모듈의 일관된 규칙이다.
