# 원격 구글 로그인 설계 — 앱 화면 안에서 재인증

- **작성일**: 2026-09-26
- **상태**: 구현 중 (계획: `docs/superpowers/plans/2026-09-26-remote-login.md`)
- **기획**: `docs/requests/requests_spec.md`
- **대상**: 신규 사이드카 컨테이너(`login-browser`), 신규 「인증」 페이지,
  `components/auth_gate.py`, `docker-compose.yml`, `pyproject.toml`,
  재시드 문서. 질의 파이프라인(`services/nlm.py`)과 실행 모델
  (`services/runner.py`·`runs.py`·`digest_runner.py`)은 읽기만 하고
  바꾸지 않는다.
- **선행 설계**: `2026-09-16-headless-auth-design.md`(R1),
  `2026-09-16-container-deploy-design.md`(R2)

---

## 1. 왜 바꾸는가

지금 자격증명을 만드는 길은 하나다.

```
데스크톱   uv run notebooklm login   (Playwright 크로미움, 사람이 구글 로그인)
             → storage_state.json
대시보드   자격증명 올리기 → 반입 → 다시 확인
```

첫 줄이 병목이다. **uv·파이썬·Playwright 가 깔린 PC 한 대**가 있어야
한다. 기획의 요구는 그 PC 를 뺀 **모든 PC 와 모바일**에서 인증을 마칠
수 있는 것이다.

사용자 경험의 목표는 이렇다. 어느 기기에서든 notebooklm-st 화면을 열고,
**버튼 하나 → 앱 화면 안에 뜬 구글 로그인 → 로그인 → 끝.** 파일을
만들거나 옮기거나 올리는 단계가 없다. 별도 뷰어 프로그램도 없다.

### 1.1 앱이 구글 로그인 폼을 직접 그릴 수는 없다

가장 먼저 나올 질문이라 앞에 못박는다.

- 필요한 것은 **구글에 로그인한 브라우저의 웹 세션 쿠키**다. NotebookLM
  에는 공개 API 가 없다(R1 §2.1).
- 구글 로그인 페이지는 봇 탐지 스크립트·2단계 인증·보안 확인을 거친다.
  앱이 아이디·비밀번호를 받아 HTTP 로 보내는 방식은 통과하지 못하고,
  통과하더라도 앱이 사용자의 구글 비밀번호를 다루게 된다.
- "Google 로 로그인"(OAuth)은 API 토큰을 줄 뿐 웹 세션 쿠키를 주지 않는다.

따라서 **진짜 브라우저 안에서 구글 로그인이 일어나야 한다.** 이 설계는
그 브라우저를 **홈서버에서 돌리고, 그 화면을 앱 페이지 안에 끼워 넣는다.**

---

## 2. 조사로 확인한 사실

| 사실 | 근거 | 설계에 주는 영향 |
|---|---|---|
| 구글 세션 쿠키는 HttpOnly 다 | 브라우저 쿠키 속성 | 페이지 JS·북마클릿으로 사용자 기기에서 쿠키를 꺼낼 수 없다. 확장을 못 까는 iOS 는 "사용자 기기에서 쿠키를 만들어 오는" 어떤 방식으로도 덮이지 않는다 → 서버 쪽 브라우저가 필요하다 |
| `notebooklm login` 은 로그인이 감지되면 스스로 저장하고 끝난다 | `notebooklm login --help`: *"Authentication is saved automatically once login is detected"* | 사이드카는 CLI 를 띄우고 종료만 기다리면 된다. 새 인증 로직을 만들지 않는다 |
| 저장 위치는 활성 프로필이고 `NOTEBOOKLM_HOME` 을 따른다 | R2 §2 (`notebooklm/paths.py:127`) | 사이드카에 앱과 같은 `NOTEBOOKLM_HOME=/data/notebooklm` 을 주면 결과가 앱의 프로필에 바로 떨어진다. 업로드·반입 단계가 사라진다 |
| 로그인에 쓴 크로미움 프로필이 `profiles/default/browser_profile/` 에 남는다 | `notebooklm/paths.py:500` | 라이브러리가 계정 동등 자격증명으로 다루는 것(R1 §2.2 L3 경고)이 공유 볼륨에 남는다 → 세션이 끝나면 지운다(6.4) |
| `--fresh` 는 캐시된 브라우저 프로필을 지우고 시작한다 | `notebooklm login --help` | 매 세션을 깨끗한 상태로 시작한다 |
| `--browser-timeout` 으로 사람을 기다리는 시간을 정한다(기본 300초) | `notebooklm login --help` | 시한은 사이드카가 정하고 CLI 에는 더 긴 값을 준다(6.4) |
| 실행 중인 질의·정리본을 알 수 있다 | `RunRegistry.running_count()`(`services/runs.py:106`), `DigestRegistry.is_running()`(`services/digest_runner.py:95`) | 실행 중에는 로그인 시작을 막는다(8.2) |
| 공개 주소를 환경변수로 받는 선례가 있다 | `NOTEBOOKLM_ST_OUTLINE_PUBLIC_URL`(`services/outline.py:17`) | 뷰어 주소도 같은 방식으로 받는다(7.4) |
| 앱 이미지에는 playwright 가 없고 CI 가 이를 단언한다 | R2 §3, `.github/workflows/build.yml` | 브라우저는 **별도 컨테이너**에 둔다. 앱 이미지는 건드리지 않는다 |
| 구글은 컨테이너 안 가상 화면(Xvfb)의 비루트 크로미움 로그인을 막지 않는다 | Task 1 스파이크(이 PC 의 Docker Desktop, linux/amd64) — 사람이 noVNC 로 실제 구글 계정 로그인을 끝까지 마쳤고 차단 문구가 없었다 | 1.1 절이 우려한 "안전하지 않은 브라우저" 차단은 이 환경에서 현실화되지 않았다. 홈서버는 같은 아키텍처(x86_64, 4절)라 같은 결과를 기대하며, 그 확인은 Task 9 의 홈서버 E2E 로 남긴다 |
| noVNC 는 URL 해시(`#autoconnect=1&resize=scale&password=...`)의 `password` 를 그대로 읽어 자동 인증하고, 틀린 값은 명확히 거부한다 | Task 1 스파이크 — 올바른 비밀번호는 대화상자 없이 곧바로 붙었고, 틀린 비밀번호는 "password check failed!" 배너와 함께 붙지 않았다 | 7.3 의 해시 설계를 그대로 쓴다. 쿼리 문자열로 바꾸는 대안은 필요 없다 |
| 사이드카의 크로미움은 비루트(uid 1000)·`read_only` 루트파일시스템·tmpfs `/tmp`·`shm_size=1g` 만으로 추가 옵션 없이 뜬다 | Task 1 스파이크 — `--shm-size=1g --read-only --tmpfs /tmp --user 1000:1000` 만으로 Xvfb·x11vnc·websockify·크로미움이 모두 기동했고 `rootfs: read-only`·`uid: 1000` 을 확인했다 | 9.2 의 compose 설정을 그대로 쓴다. 크로미움 샌드박스 플래그 등 추가 조정이 필요 없다 |

위 스파이크 확인 세 건은 **이 PC 의 Docker Desktop(linux/amd64, 29.8.0)** 에서 했다.
홈서버는 x86_64·Docker 26.1.4 로 아키텍처가 같아 그대로 맞을 것으로 본다.
홈서버 자체에서의 재확인(볼륨 권한·LAN 접근 포함)과 휴대폰 입력 확인(13절)은
Task 9 의 홈서버 E2E 로 남긴다.

---

## 3. 설계 결정

| 결정 | 선택 | 근거 |
|---|---|---|
| 브라우저를 돌리는 곳 | **홈서버의 별도 사이드카 컨테이너** | 모바일까지 덮는 유일한 길(2절 첫 줄). 앱 이미지의 playwright 부재 불변식과 `read_only`·UID 1000 설정을 지킨다. 사이드카만 끄면 원격 로그인 전체가 사라진다 |
| 사용자에게 보이는 방식 | **앱 페이지 안 iframe** | 별도 뷰어를 여는 것은 사용자에게 너무 복잡하다. 화면 중계는 noVNC 가 하지만 사용자는 그것을 의식하지 않는다 |
| 로그인 수단 | **기존 `notebooklm login` 을 그대로** | 새 세션으로 로그인한다는 R1 의 결정(평소 브라우저 세션과 분리)을 유지한다. 인증 로직을 새로 만들지 않는다 |
| 앱 ↔ 사이드카 신호 | **공유 볼륨의 파일** | docker 소켓을 앱에 주지 않는다. 컨테이너 간 네트워크 API 도 만들지 않는다. 파일마다 쓰는 쪽이 하나라 잠금이 필요 없다 |
| 진입점 | **항상 열 수 있는 「인증」 페이지** | 배너는 기동 시 판정이라(R1 §13) 앱이 떠 있는 도중 세션이 죽으면 보이지 않는다. 모바일에서는 `docker restart` 를 할 수 없다. `runner` 를 고쳐 게이트를 무효화하는 대신 사람이 언제든 닿는 곳을 둔다 |
| 배너 | **안내 + 인증 페이지 링크만** | 다시 확인·업로더를 두 곳에 두면 둘 다 테스트하고 유지해야 한다 |
| 기존 업로더 | **인증 페이지의 대체 경로로 유지** | 사이드카가 없거나 구글이 막을 때 돌아갈 길 |
| 기능 스위치 | **`NOTEBOOKLM_ST_LOGIN_VIEWER_URL` 하나** | 컨테이너는 사용자가 닿는 홈서버 주소를 모른다. 비어 있으면 원격 로그인 영역을 숨긴다 — 사이드카 없는 데스크톱 실행은 지금과 같다 |
| 시한 | **사이드카가 300초로 소유** | CLI 의 시한과 사이드카의 시한이 겹치면 누가 끝냈는지 모호하다. CLI 에는 더 긴 값을 주고 사이드카가 자른다 |
| 사이드카의 `notebooklm-py` 버전 | **`uv.lock` 에서 온다** | 앱과 버전이 어긋나면 저장 형식이 어긋날 수 있다. 전용 의존성 그룹을 두고 같은 락으로 설치하면 일치가 구조로 보장된다(9.1) |

---

## 4. 구조

```
홈서버 docker-compose.yml
┌──────────────────────────┐        ┌────────────────────────────────┐
│ app (기존)                │        │ login-browser (신규 사이드카)    │
│  Streamlit :8611 → 9004  │        │  supervisor (평소엔 이것만 돎)    │
│  「인증」 페이지에 iframe  │        │  세션 중: Xvfb + x11vnc          │
│                          │        │    + 크로미움(notebooklm login)  │
│                          │        │    + websockify/noVNC :6080→9005 │
└────────────┬─────────────┘        └──────────────┬─────────────────┘
             │          ./data (공유 볼륨)           │
             ├──► /data/notebooklm/profiles/default/ ◄┤  로그인 결과
             └──► /data/login/ request·status·heartbeat ◄┘  신호
```

### 4.1 모듈과 경계

README 의 규칙(`core/` 와 `services/` 는 `import streamlit` 을 하지 않는다)을
지킨다. 사이드카는 앱 패키지 중 **표준 라이브러리만 쓰는 두 모듈**만 쓴다.

| 모듈 | 책임 | Streamlit | 쓰는 곳 |
|---|---|---|---|
| `core/login_protocol.py` (신규) | 파일 이름·상태 값·JSON 직렬화·원자적 쓰기. 두 컨테이너의 **유일한 계약** | 모름 | 앱·사이드카 |
| `login_browser/supervisor.py` (신규) | 감시 루프와 세션 수명 | 모름 | 사이드카 |
| `services/login_session.py` (신규) | 요청 쓰기, 상태·heartbeat 읽기, 시작 가능 판정 | 모름 | 앱 |
| `pages/auth.py` (신규) | 「인증」 페이지 | 앎 | 앱 |
| `components/auth_gate.py` | 배너: 안내 + 페이지 링크 | 앎 | 앱 |

`core/login_protocol.py` 와 `login_browser/` 는 `notebooklm_st` 의 다른
모듈을 import 하지 않는다. 사이드카 이미지가 앱의 의존성(streamlit 등)
없이 돌아야 하기 때문이다. 테스트가 이를 단언한다(11.1).

---

## 5. 신호 프로토콜 — `core/login_protocol.py`

### 5.1 파일

디렉터리는 환경변수 `NOTEBOOKLM_ST_LOGIN_DIR` 이 정하고, 두 이미지 모두
`/data/login` 으로 굽는다.

| 파일 | 쓰는 쪽 | 내용 |
|---|---|---|
| `request.json` | **앱만** | `{"id": str, "action": "start" \| "cancel", "requested_at": ISO8601}` |
| `status.json` | **사이드카만** | `{"request_id": str \| null, "state": State, "password": str \| null, "deadline": ISO8601 \| null, "detail": str \| null, "updated_at": ISO8601}` |
| `heartbeat` | **사이드카만** | 내용 없음. 수정 시각만 의미가 있다 |

- 모든 쓰기는 같은 디렉터리의 임시 파일에 쓴 뒤 `os.replace` 로 바꾼다.
  읽는 쪽은 반쯤 쓰인 파일을 보지 않는다.
- 파일 권한은 `0600` 이다. `status.json` 이 세션 비밀번호를 담기 때문이다.
- `id` 는 `uuid4().hex` 다. `cancel` 요청은 새 `id` 를 갖는다.

### 5.2 상태

```
idle ──start──► starting ──► running ──┬─► succeeded
                   │                    ├─► failed
                   └──► failed          ├─► timeout
                                        └─► cancelled
```

`succeeded`·`failed`·`timeout`·`cancelled` 는 **마지막 결과**로 남는다.
다음 `start` 가 오면 `starting` 으로 넘어간다. `idle` 은 파일이 한 번도
쓰이지 않은 상태다.

`password` 와 `deadline` 은 `running` 일 때만 값이 있다. 다른 상태로 넘어갈
때 `null` 로 지운다.

---

## 6. 사이드카 — `login_browser/supervisor.py`

### 6.1 이미지

`deploy/login-browser/Dockerfile` 을 따로 둔다.

- 빌더에서 `uv sync --frozen --only-group login-browser --no-install-project`
  로 `notebooklm-py[browser]` 를 **앱과 같은 락 버전으로** 설치한다(9.1).
- `playwright install --with-deps chromium`, 그리고 apt 로 `xvfb`·`x11vnc`·
  `novnc`·`websockify` 를 넣는다.
- `src/notebooklm_st/__init__.py`, `core/__init__.py`, `core/login_protocol.py`,
  `login_browser/` 만 복사한다(4.1). 두 `__init__.py` 는 docstring 뿐이라
  다른 모듈을 끌어오지 않는다.
- `USER 1000`, `ENV NOTEBOOKLM_HOME=/data/notebooklm NOTEBOOKLM_ST_LOGIN_DIR=/data/login HOME=/tmp`.
- `CMD ["python", "-m", "notebooklm_st.login_browser.supervisor"]`.

### 6.2 감시 루프

1초마다 다음을 한다.

1. `heartbeat` 의 수정 시각을 갱신한다.
2. `request.json` 을 읽는다. 없거나 깨졌으면 넘어간다.
3. **이미 처리한 `id` 면 무시한다.** 처리한 마지막 `id` 는 메모리에 둔다.
4. `start` 이고 세션이 없으면 세션을 시작한다. 세션이 이미 있으면 무시한다.
5. `cancel` 이고 세션이 있으면 `cancelled` 로 정리한다.
6. 세션이 있으면 CLI 종료와 시한을 확인한다(6.4).

### 6.3 기동 시 복구

사이드카가 뜰 때 다음을 차례로 한다. 재시작 사유는 모두 `detail`
"로그인 브라우저가 재시작되었습니다" 다.

1. **흔적을 상태와 상관없이 지운다**(6.4 정리의 2·3단계). `browser_profile/`
   은 계정 동등 자격증명이고, 지우기는 멱등하고 싸다. 끝난 결과만 남아
   있어도 지운다. `status.json` 은 이 단계에서 건드리지 않는다.
2. `status.json` 이 `starting`/`running` 이면 그 `request_id` 로 `failed` 를
   쓴다. 반쯤 열린 세션을 남기지 않는다.
3. **그때 있는 `request.json` 의 `id` 를 처리한 것으로 기록한다.** 재시작
   전의 `start` 요청이 사람 없이 다시 실행되지 않게 한다.
4. 그 요청이 `start` 이고 그 `id` 가 (2 를 거친) `status.json` 의
   `request_id` 와 다르면, **그 `id` 로 `failed` 를 써서 답한다.** 다시
   실행하지는 않는다. 답하지 않으면 그 요청을 지켜보는 탭이 결과를 받지
   못한다. `cancel` 이 남아 있거나 이미 그 `id` 로 결과를 썼으면 상태를
   바꾸지 않는다.

### 6.4 세션 한 번의 수명

```
시작
 1. status = starting
 2. password = secrets.token_urlsafe(6)   (8자 — VNC 인증은 8자까지만 쓴다)
    비밀번호 파일을 /tmp 에 0600 으로 쓰고 x11vnc 에 `-passwdfile rm:<파일>`
    로 넘긴다. x11vnc 가 읽은 뒤 지운다
 3. 남은 X 소켓(/tmp/.X11-unix/X99)을 지운 뒤 Xvfb :99 -screen 0 1280x800x24
    를 띄우고, 소켓이 생길 때까지 기다린다(5초)
 4. x11vnc -display :99 -localhost -passwdfile rm:<파일> -forever -shared
 5. websockify --web <novnc 경로> 6080 localhost:5900
 6. DISPLAY=:99 python -m notebooklm login --fresh --browser-timeout 900
 7. status = running (password, deadline = 지금 + 300초)

종료 — 다음 중 먼저 오는 것
 · CLI 종료        → 종료 코드 0 이면 succeeded, 아니면 failed
 · cancel 요청      → cancelled
 · deadline 초과    → timeout

정리 (어느 종료든 같다)
 1. CLI · websockify · x11vnc · Xvfb 순으로 종료 (SIGTERM, 5초 뒤 SIGKILL)
 2. 비밀번호 파일 삭제
 3. /data/notebooklm/profiles/default/browser_profile/ 삭제
 4. status = 결과 (password·deadline 은 null)
```

- 3~6 중 하나라도 뜨지 못하면 정리 후 `failed`(`detail` 에 어느 단계인지).
- 시작 도중의 **예상 밖 파일 오류**(`OSError` — 비밀번호 파일·임시
  디렉터리·`running` 상태 쓰기 등)도 같은 정리 후 `failed`(`detail`
  "로그인 브라우저를 띄우지 못했습니다(파일 오류)")로 끝낸다. 잡지 않으면
  상태가 `starting` 에 남고 띄운 프로세스가 샌다.
- 정리는 파일 하나를 지우지 못해도 나머지(특히 `browser_profile/`)를 마저
  지운다.
- 이전 Xvfb 가 SIGKILL 되면 X 소켓이 남는다. 3단계에서 먼저 지우지 않으면
  새 Xvfb 가 뜨기도 전에 떴다고 판정한다.
- `failed` 의 `detail` 에는 CLI stderr 의 **마지막 한 줄**만 담는다. 화면이
  이 문자열을 그대로 보여 준다.
- x11vnc 는 `-localhost` 라 컨테이너 밖에서 닿지 않는다. 밖에서 닿는 것은
  websockify(6080) 하나다.
- CLI 에 900초를 주는 것은 사이드카의 300초가 항상 먼저 오게 하기 위해서다.
  `timeout` 과 `failed` 가 섞이지 않는다.

### 6.5 주입점

`supervisor` 는 테스트할 수 있도록 **프로세스를 띄우는 함수·시계·디렉터리
경로·X 소켓 경로를 주입받는다.** 실제 Xvfb·크로미움 없이, 실제 `/tmp` 를
건드리지 않고 상태 기계 전체를 검증한다.

---

## 7. 앱 — 화면

### 7.1 「인증」 페이지 — `pages/auth.py`

내비게이션에 `st.Page(auth.render, title="인증", url_path="auth")` 를 더한다.
인증 상태와 상관없이 언제나 열 수 있다.

```
인증
 상태: ✅ 인증됨                              [다시 확인]

 ── 구글 로그인 ─────────────────────────────
 (7.2 의 상태별 화면)

 ▸ 자격증명 파일 올리기 (대체 경로)          ← 기존 업로더
```

- 상태 줄은 `AuthGate` 의 판정을 그린다. 만료와 확인 불가의 구분(R1 §7.2)은
  그대로다. 확인 불가 문구는 배너와 이 페이지가 함께 쓰므로
  `errors.probe_failed_text()` 로 `core/errors.py` 에 둔다.
- **다시 확인**은 `gate.recheck()` 를 부른다.
- 업로더는 기존 `auth_gate._render_upload()` 를 이 페이지로 옮긴 것이다.
  동작은 바꾸지 않는다.

### 7.2 구글 로그인 영역의 상태별 화면

| 조건 | 화면 |
|---|---|
| 뷰어 주소 미설정 | 영역을 그리지 않는다 |
| 사이드카 꺼짐 (heartbeat 10초 초과 또는 없음) | "로그인 브라우저가 꺼져 있습니다" |
| 실행 중인 질의·정리본 있음 | 시작 버튼 비활성 + "진행 중인 실행이 끝난 뒤 로그인하세요" (8.2) |
| `idle`·마지막 결과 | 마지막 결과 한 줄(있으면) + **구글 로그인 시작** |
| 앱이 30초 안에 `start` 요청을 썼고 사이드카가 아직 받지 않음 | "로그인 브라우저를 준비하는 중" |
| `starting` | "로그인 브라우저를 준비하는 중" |
| `running` | iframe + 남은 시간 + **취소** + **새 탭에서 열기** |
| 이 탭이 지켜보던 요청이 결과로 끝남 | `succeeded` 면 `gate.recheck()` → 성공이면 "인증되었습니다" / 실패면 "로그인은 끝났지만 인증이 살아나지 않았습니다". 그 밖의 결과는 "로그인하지 못했습니다: <결과> — <detail>" |

화면은 위에서 아래로 이 순서로 판정한다: 사이드카 꺼짐 → `running`
(비밀번호 있음) → **지켜보던 요청의 결과 처리** → 준비 중(`starting` 또는
받지 않은 `start`) → `idle`·마지막 결과.

- "요청을 썼지만 받지 않음" 은 `request.json` 이 `start` 이고, 그 `id` 가
  `status.json` 의 `request_id` 와 다르고, **`requested_at` 이 30초
  (`START_ACK_TIMEOUT`) 안일 때만**이다. 사이드카는 1초마다 요청을 보고
  받자마자 `starting` 을 쓰므로 30초면 넉넉하다. 그보다 오래된 `start` 는
  사이드카가 처리하지 않은 것이다(재시작 직전에 쓰였거나 다른 탭의 세션
  중에 쓰였다). 계속 기다리면 영원히 "준비 중" 이고 시작 버튼이 돌아오지
  않는다. `requested_at` 을 읽지 못해도 오래된 것으로 본다.
- `cancel` 은 사이드카가 세션이 없으면 무시하므로 이 판정에 넣지 않는다 —
  넣으면 영원히 "준비 중" 이다.
- **결과 처리는 준비 중 판정보다 먼저 한다.** 이 탭이 지켜보던 요청이
  결과로 끝났으면, 다른 탭이 새 `start` 를 써 두어 준비 중으로 보일 때도
  이 탭은 `recheck()` 와 결과 문구를 처리한다. 순서가 반대면 실제로 로그인한
  탭이 `recheck()` 를 부르지 못한다.
- 결과 처리(성공 시 `recheck()`, 결과 문구)는 **이 탭이 그 요청을 지켜보던
  경우에만** 한다. 지켜보지 않던 탭은 마지막 결과를 한 줄로만 보여 준다.
  며칠 전의 `succeeded` 를 새 탭이 "인증되었습니다" 로 오해하지 않게 한다.
- 받지 않은 `start`(위와 같은 30초 판정)·`starting`·`running` 동안만
  `st.fragment(run_every=1)` 로 갱신한다. 평소에는 폴링하지 않는다.
- 지켜보는 요청의 `id` 는 `st.session_state` 에 둔다. 결과를 처리하면
  지운다. 그래서 `recheck()` 는 요청 하나에 한 번만 불린다. 다른 탭에서
  먼저 확인했으면 게이트가 이미 `ok` 라 결과는 같다.

### 7.3 iframe

- 주소: `{VIEWER_URL}/vnc.html#autoconnect=1&resize=scale&password={password}`
- 비밀번호를 **해시**에 둔다. 해시는 서버로 전송되지 않아 요청 로그에
  남지 않는다.
- 높이 700px, 폭은 컨테이너 전체. `resize=scale` 로 화면에 맞춘다.
- **새 탭에서 열기** 는 같은 주소다. 작은 화면에서 iframe 이 답답할 때 쓴다.
- iframe 은 `running` 일 때만 그린다.

### 7.4 설정 — `NOTEBOOKLM_ST_LOGIN_VIEWER_URL`

사용자 브라우저가 닿는 noVNC 주소다(예: `http://192.168.0.10:9005`).
컨테이너는 홈서버의 LAN 주소를 알 수 없어 받아야 한다. 끝의 `/` 는 떼고
쓴다.

`docker-compose.yml` 의 `app.environment` 에 Outline 값처럼
`"${NOTEBOOKLM_ST_LOGIN_VIEWER_URL:-}"` 로 둔다.

### 7.5 배너 — `components/auth_gate.py`

만료·확인 불가일 때 **안내 문구 + 「인증」 페이지 링크**(`st.page_link`)만
그린다. 다시 확인 버튼과 업로더는 7.1 로 옮겨 가므로 여기서 지운다.
인증이 살아 있으면 지금처럼 아무것도 그리지 않는다.

`errors.LOGIN_HINT` 의 문구를 바꾼다. 지금 문구는 "데스크톱에서
`uv run notebooklm login` … 배너가 보이지 않으면 앱을 재시작하세요" 다.
새 문구는 **"「인증」 페이지에서 다시 로그인하세요"** 를 앞에 두고, 재시드
how-to 링크를 남긴다. "앱을 재시작하세요" 는 뺀다 — 인증 페이지가 항상
닿으므로 더는 필요 없다.

이 상수는 배너만 쓰는 것이 아니다. `errors.to_message()`(`core/errors.py:97`)
가 인증 예외를 이 문구로 바꾸므로, **실행 도중 세션이 죽었을 때 실행 현황
화면에 뜨는 실패 메시지도 인증 페이지를 가리키게 된다.** R1 §13 이 남긴
"실행 중 만료" 의 안내가 `runner` 를 건드리지 않고 이 경로로 닫힌다.

---

## 8. 앱 — `services/login_session.py`

### 8.1 계약

```python
VIEWER_URL_ENV_VAR = "NOTEBOOKLM_ST_LOGIN_VIEWER_URL"
LOGIN_DIR_ENV_VAR = "NOTEBOOKLM_ST_LOGIN_DIR"
HEARTBEAT_STALE_AFTER = 10.0   # 초
START_ACK_TIMEOUT = 30.0       # 초. 이보다 오래 받지 않은 start 는 기다리지 않는다(7.2)


def viewer_url() -> str | None: ...           # 비었으면 None
def login_dir() -> Path | None: ...           # 비었으면 None

def read_status(directory: Path) -> login_protocol.Status: ...
    # 없거나 깨졌으면 idle. 깨졌으면 경고 로그

def sidecar_alive(directory: Path, now: float) -> bool: ...

def pending_request(directory: Path) -> login_protocol.Request | None: ...
    # request.json. status 의 request_id 와 비교해 "받지 않음" 을 가린다(7.2)

def start_is_stale(request: login_protocol.Request, now: datetime) -> bool: ...
    # requested_at 이 START_ACK_TIMEOUT 을 넘겼거나 읽히지 않으면 True

def request_start(directory: Path) -> str: ...      # 새 id 를 돌려준다
def request_cancel(directory: Path) -> str: ...

def busy(registry: runs.RunRegistry, digests: digest_runner.DigestRegistry) -> bool: ...
    # running_count() > 0 or is_running()
```

원격 로그인 영역은 `viewer_url()` 과 `login_dir()` 이 **둘 다** 값이 있을
때만 그린다.

### 8.2 실행 중에는 시작을 막는 이유

실행 중인 질의·정리본은 연 클라이언트에 **옛 쿠키를 들고 있다가 회전할
때 파일에 되쓴다**(R1 §2.6). 새 로그인 직후 그 되쓰기가 일어나면 새 쿠키가
옛 쿠키로 덮일 수 있다. 실제로 덮이는지는 확인하지 않았다(13절). 확인하는
비용보다 막는 비용이 싸다.

막는 것은 **시작**뿐이다. 이미 진행 중인 로그인 세션 중에 사용자가 질의를
시작하는 것은 막지 않는다 — 5분 안에 끝나는 드문 일이고, 막으려면 질의
화면들을 건드려야 한다.

---

## 9. 배포

### 9.1 `pyproject.toml`

```toml
[dependency-groups]
login-browser = ["notebooklm-py[browser]==0.8.1"]
dev = [
    { include-group = "login-browser" },   # 데스크톱 재로그인용 (지금과 같음)
    "mypy>=2.3.1",
    "pytest>=9.1.1",
    "ruff>=0.16.5",
]
```

지금 dev 그룹에 직접 있는 `notebooklm-py[browser]` 를 새 그룹으로 옮기고
dev 가 포함한다. 데스크톱의 `uv sync` 결과는 달라지지 않는다. 앱 이미지의
`uv sync --no-dev` 도 달라지지 않는다.

### 9.2 `docker-compose.yml`

```yaml
  login-browser:
    build:
      context: .
      dockerfile: deploy/login-browser/Dockerfile
    image: notebooklm-st-login-browser:local
    container_name: notebooklm-st-login-browser
    user: "${PUID:-1000}:${PGID:-1000}"
    ports:
      # 호스트 9005 → noVNC 6080. 홈 LAN 에만 연다. 로그인 세션 중에만
      # 무언가가 이 포트를 듣는다.
      - "9005:6080"
    volumes:
      - ./data:/data
    restart: unless-stopped
    stop_grace_period: 30s     # 종료 정리가 끝날 시간(아래)
    read_only: true
    tmpfs: ["/tmp"]
    shm_size: "1gb"            # 크로미움 공유 메모리
    logging: { driver: json-file, options: { max-size: "10m", max-file: "3" } }
```

`stop_grace_period` 를 30초로 둔다. 내려갈 때 사이드카는 떠 있는 세션을
정리하는데(6.4), 프로세스 그룹 4개를 SIGTERM·SIGKILL 로 각각 5초씩 기다릴
수 있다. 도커 기본 유예 10초면 정리 도중 SIGKILL 되어 `browser_profile/`
(자격증명)이 볼륨에 남을 수 있다. 남더라도 다음 기동의 복구(6.3)가 지운다.

`app` 서비스에는 `NOTEBOOKLM_ST_LOGIN_VIEWER_URL` 한 줄만 더한다.
`NOTEBOOKLM_ST_LOGIN_DIR` 은 두 이미지 모두 Dockerfile 이 굽는다.

### 9.3 CI

`.github/workflows/build.yml` 의 `image` 잡에 사이드카 이미지 **빌드**를
더한다. 게시는 하지 않는다 — compose 가 홈서버에서 로컬로 빌드한다.
빌드한 이미지에서 다음을 단언한다.

```bash
docker compose run --rm --no-deps -T login-browser python -c "import notebooklm_st.login_browser.supervisor"
docker compose run --rm --no-deps -T login-browser python -c "import streamlit"   # 실패해야 한다
# 사이드카와 앱의 notebooklm-py 버전이 같다
```

import 만으로는 감시 루프가 도는지 모른다. 그래서 기존 `기동과 헬스체크`
단계(`compose up -d` 뒤 앱 헬스 루프) **다음에**, 컨테이너 안에서
`$NOTEBOOKLM_ST_LOGIN_DIR/heartbeat` 가 생기고 수정 시각이 10초 안인지
(앱의 "꺼져 있음" 판정과 같은 기준, 8.1) 몇 초 기다리며 확인한다.
컨테이너 안에서 재야 볼륨 권한과 호스트 시계에 흔들리지 않는다. 실패하면
`docker compose logs login-browser` 를 찍고 실패한다.

앱 이미지의 `import playwright` 실패 단언은 그대로 둔다.

---

## 10. 보안

- **비노출 전제를 유지한다.** 앱(9004)과 뷰어(9005) 모두 홈 LAN 에만 연다.
  R1 §13.1 의 조건 — 노출로 바꾸면 업로드 UI 를 걷는다 — 은 뷰어에도 똑같이
  적용된다. 노출로 바꾸면 사이드카를 끈다.
- **세션 비밀번호.** 세션마다 새로 만들고, 세션이 끝나면 x11vnc 와 함께
  사라지며 `status.json` 에서도 지운다. 파일은 `0600` 이다. iframe 주소의
  해시로만 넘긴다(7.3).
- **평소에는 아무것도 듣지 않는다.** websockify 는 세션 중에만 뜬다.
- **브라우저 프로필을 남기지 않는다.** `--fresh` 로 시작하고, 끝나면
  `browser_profile/` 을 지운다(6.4). 기동할 때도 상태와 상관없이 지우고
  (6.3), 종료 정리가 끝날 유예를 compose 에 둔다(9.2).
- **평문 구간.** 앱과 뷰어는 모두 HTTP 다. 로그인 화면에 치는 **구글
  비밀번호의 키 입력이 LAN 위를 암호화 없이 지나간다.** 업로드하던 쿠키
  파일도 같은 구간을 지났지만, 비밀번호는 한 단계 더 민감하다. how-to
  문서에 Tailscale 같은 암호화 경로를 **강하게 권장**한다고 적는다.
- **로그에 남기지 않는 것.** 비밀번호, 쿠키, 뷰어 주소의 해시 부분.

---

## 11. 테스트

### 11.1 단위

```
tests/core/test_login_protocol.py
  상태·요청 JSON 왕복, 깨진 JSON 은 예외, 원자적 쓰기가 0600 으로 남는지,
  notebooklm_st 의 다른 모듈을 import 하지 않는지(4.1)

tests/login_browser/test_supervisor.py   (가짜 프로세스 실행기·시계 주입)
  start 요청 → starting → running, password 와 deadline 이 채워짐
  같은 id 를 두 번 읽어도 세션은 하나
  세션 중의 두 번째 start 는 무시
  CLI 종료 코드 0 → succeeded, 그 밖 → failed + stderr 마지막 줄
  deadline 초과 → timeout
  cancel → cancelled
  어느 종료든 모든 자식이 종료되고 browser_profile/ 이 지워지고 password 가 지워짐
  자식 하나가 뜨지 못함 → failed, 이미 뜬 것은 정리됨
  시작 도중 OSError(가상 화면 확인 오류, 임시 디렉터리 실패) → 정리 후 failed
  Xvfb 를 띄우기 전에 남은 X 소켓이 지워짐
  기동 시 running 이 남아 있으면 → 정리 후 failed
  기동 시 결과와 상관없이 browser_profile/ 이 지워짐
  기동 시 있던 request 는 다시 실행하지 않음
  기동 시 답하지 않은 start 는 그 id 로 failed(재시작), cancel·답한 start 는 그대로
  매 틱 heartbeat 가 갱신됨

tests/services/test_login_session.py   (tmp_path)
  viewer_url / login_dir: 비었으면 None, 끝의 / 제거
  read_status: 없음 → idle, 깨짐 → idle + 경고
  sidecar_alive: 10초 경계
  request_start / request_cancel: 새 id, 원자적 쓰기
  start_is_stale: 29초 아님 / 31초 stale / 요청 시각을 읽지 못하면 stale
  busy: 질의만 / 정리본만 / 둘 다 없음
```

### 11.2 화면 (AppTest, `tests/test_components.py`·`tests/pages/`)

```
배너
  인증됨이면 아무것도 그리지 않음
  만료면 LOGIN_HINT + 인증 페이지 링크, 업로더·다시 확인 없음
  확인 불가면 예외 타입 문구 + 링크

인증 페이지
  다시 확인이 recheck 를 부름
  업로더가 옮겨 와서도 동작함 (기존 반입 테스트를 옮김)
  뷰어 주소 미설정 → 구글 로그인 영역 없음
  사이드카 꺼짐 → 꺼짐 안내, 시작 버튼 없음
  busy → 시작 버튼 비활성
  시작 → request.json 이 써짐
  running → iframe 주소에 해시로 password, 취소 버튼
  succeeded → recheck 를 한 번만 부름, 결과 문구
  30초 넘은 받지 않은 start → 준비 중 아님, 시작 버튼
  지켜보던 요청이 끝났고 다른 탭의 새 start 가 있음 → recheck 한 번, 결과 문구
```

`tests/test_app.py:test_app_boots_with_all_pages` 는 페이지가 하나 늘어난
채로 통과해야 한다.

### 11.3 수동 검증

계획의 첫 작업(스파이크)과 마지막 작업(E2E)이다.

- **스파이크**: 사이드카 이미지만 먼저 만들어 이 PC 의 Docker Desktop 에서
  띄우고, noVNC 로 구글 로그인이 통과해 `storage_state.json` 이
  생기는지, 같은 자리에서 noVNC 가 해시의 `password` 를 읽는지, 크로미움이
  비루트·`read_only` 로 추가 옵션 없이 뜨는지 확인했다 — 결과는 2절.
- **E2E(홈서버)**: PC 브라우저와 휴대폰(iOS·Android 각 하나)에서 인증 페이지 →
  시작 → 로그인 → 인증됨. 취소, 시한 초과, 사이드카 재시작 중 복구. 스파이크가
  데스크톱 Docker Desktop 에서 닫은 가정의 홈서버 자체 재확인도 겸한다.
  끝난 뒤 `browser_profile/` 이 없는지.

검증 명령은 기존 4단 그대로다.

```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

---

## 12. 건드리는 파일

| 파일 | 변경 |
|---|---|
| `src/notebooklm_st/core/login_protocol.py` | 신규 |
| `src/notebooklm_st/login_browser/__init__.py`, `supervisor.py` | 신규 |
| `src/notebooklm_st/services/login_session.py` | 신규 |
| `src/notebooklm_st/pages/auth.py` | 신규 |
| `src/notebooklm_st/app.py` | 인증 페이지 등록 |
| `src/notebooklm_st/components/auth_gate.py` | 배너만 남기고 다시 확인·업로더를 옮김 |
| `src/notebooklm_st/core/errors.py` | `LOGIN_HINT` 문구 |
| `deploy/login-browser/Dockerfile` | 신규 |
| `docker-compose.yml` | `login-browser` 서비스, 앱에 뷰어 주소 |
| `Dockerfile` | `NOTEBOOKLM_ST_LOGIN_DIR` |
| `pyproject.toml`, `uv.lock` | `login-browser` 그룹, mypy `disallow_untyped_defs` 대상에 `notebooklm_st.login_browser.*` |
| `.github/workflows/build.yml` | 사이드카 빌드·단언 |
| 테스트 | 11절 |
| `README.md` | 첫 실행 — 인증, 홈서버 절, 사용 순서에 인증 페이지 |
| `docs/how-to/2026-09-16-auth-reseed.md` | 원격 로그인을 정본으로, 데스크톱 로그인·업로드·볼륨 복사를 대체 경로로 다시 쓴다 |
| `docs/how-to/2026-09-16-homeserver-deploy.md` | 사이드카, 포트 9005, 뷰어 주소 |

건드리지 않는 것: `services/nlm.py`, `services/runner.py`, `services/runs.py`,
`services/digest_runner.py`, `services/auth.py` 의 판정 로직.

---

## 13. 미검증 가정

구글 로그인 허용·noVNC 해시 비밀번호·비루트/read_only 기동은 Task 1
스파이크로 확인했다 — 결과는 2절에 있다. 남은 가정은 아래 두 가지뿐이다.

1. **실행 중 쿠키 되쓰기가 새 쿠키를 덮는가(8.2).** 확인하지 않고 막는 쪽을
   택했다.
2. **모바일에서의 입력 편의.** 원격 화면이라 휴대폰에서는 화면 키보드를 따로
   띄워야 하고 확대가 어색할 수 있다. 가끔 하는 재인증이라 감수한다. E2E 에서
   실제로 로그인을 끝낼 수 있는지만 확인한다.

이 두 가지와, 스파이크가 이 PC 의 Docker Desktop 에서 닫은 세 가지의
홈서버 자체 재확인은 모두 Task 9 의 홈서버 E2E 로 남긴다.

---

## 14. 범위 밖

- **쿠키 내보내기 확장 경로** — iOS 를 덮지 못하고, 평소 브라우저 세션을
  가져오는 문제가 R1 이 `--browser-cookies` 를 뺀 이유와 같다
- **마스터 토큰** — R1 §2.3 의 배제 사유가 그대로다
- **실행 실패 시 게이트 자동 무효화** — `runner` 를 고치는 일이다. 항상 닿는
  인증 페이지로 대신한다
- **HTTPS·인터넷 노출** — 비노출 전제 위의 설계다
- **다중 계정·프로필** — `default` 프로필 하나만 다룬다
- **사이드카 이미지의 GHCR 게시** — compose 가 로컬로 빌드한다
- **앱이 사이드카를 켜고 끄기** — 사이드카는 상시 떠 있고 평소에는 감시
  루프만 돈다
