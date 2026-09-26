# 원격 구글 로그인 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** uv·Playwright 가 깔린 PC 없이도, 어느 PC·휴대폰에서든 notebooklm-st 의 「인증」 페이지 안에서 구글 로그인을 마쳐 NotebookLM 인증을 되살린다.

**Architecture:** 홈서버에 `login-browser` 사이드카 컨테이너를 더한다. 사이드카는 요청이 오면 Xvfb 위에 `notebooklm login` 을 띄우고 x11vnc+websockify(noVNC)로 화면을 중계한다. 앱은 그 화면을 새 「인증」 페이지의 iframe 으로 보여 준다. 두 컨테이너는 공유 볼륨 `/data/login/` 의 파일 세 개(`request.json`·`status.json`·`heartbeat`)로만 신호를 주고받는다. CLI 는 결과 쿠키를 앱과 같은 프로필(`/data/notebooklm/profiles/default/`)에 직접 저장하므로, 앱은 끝난 뒤 `AuthGate.recheck()` 만 부른다.

**Tech Stack:** Python 3.13, Streamlit 1.64(`st.iframe`·`st.fragment`·`st.page_link`), notebooklm-py 0.8.1(`[browser]` 는 사이드카만), Docker Compose, Xvfb·x11vnc·noVNC·websockify(Debian bookworm 패키지), pytest + `streamlit.testing.v1.AppTest`.

**Spec:** `docs/superpowers/specs/2026-09-26-remote-login-design.md`

## Global Constraints

- `notebooklm-py==0.8.1` 을 쓴다. 사이드카는 새 의존성 그룹 `login-browser` 로 **같은 `uv.lock`** 에서 설치한다.
- `core/` 와 `services/` 는 `import streamlit` 을 하지 않는다.
- `core/login_protocol.py` 와 `login_browser/` 는 **표준 라이브러리와 `notebooklm_st.core.login_protocol` 외에는 import 하지 않는다.**
- 앱 이미지에는 playwright 가 없어야 한다. `build.yml` 의 `import playwright` 실패 단언은 그대로 둔다.
- 포트: 앱 `9004→8611`, 뷰어 `9005→6080`. 둘 다 홈 LAN 에만 연다.
- 세션 시한 `300`초(사이드카가 소유), CLI `--browser-timeout 900`, heartbeat 판정 `10`초, 감시 주기 `1`초.
- 세션 비밀번호는 `secrets.token_urlsafe(6)` — 8자. VNC 인증은 8자까지만 쓴다.
- 경로: 신호 디렉터리 `/data/login`(`NOTEBOOKLM_ST_LOGIN_DIR`), `NOTEBOOKLM_HOME=/data/notebooklm`, 프로필 `/data/notebooklm/profiles/default`.
- 환경변수: `NOTEBOOKLM_ST_LOGIN_VIEWER_URL`(앱), `NOTEBOOKLM_ST_LOGIN_DIR`(앱·사이드카).
- 신호 파일은 같은 디렉터리의 임시 파일에 쓴 뒤 `os.replace` 로 바꾸고 권한은 `0600` 이다.
- 비밀번호·쿠키·뷰어 주소의 해시 부분은 화면 문구·로그에 남기지 않는다(iframe `src` 만 예외).
- 독스트링은 한국어 Google 스타일, `line-length = 80`. 주변 코드의 주석 밀도를 따른다.
- **uv 는 에이전트 셸 PATH 에 없다.** `C:\Users\susot\.local\bin\uv.exe`(Git Bash: `/c/Users/susot/.local/bin/uv`)로 부른다. 아래 명령의 `uv` 는 모두 이 경로다.
- **docker 도 에이전트 셸 PATH 에 없다.** Docker Desktop 이 설치돼 있고 데몬이 돈다. `C:\Users\susot\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe`(Git Bash: `/c/Users/susot/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe`)로 부른다. `command not found` 로 Docker 가 없다고 단정하지 않는다.
- 스파이크·수동 확인에서 생기는 자격증명(쿠키·크로미움 프로필)은 **저장소 밖**에만 둔다. 저장소의 `data/` 는 `.gitignore` 에 없다.
- 검증 4단: `uv run ruff format .` → `uv run ruff check --fix .` → `uv run mypy src tests` → `uv run pytest`. 이 계획의 코드 블록이 E501(줄 길이)에 걸리면 문자열을 나누는 식으로만 고친다. 동작은 바꾸지 않는다.
- 커밋: `develop` 에만, `.claude/rules/commit-strategy.md` 형식(gitmoji + Conventional Commits, 한국어 제목 ≤50자, 마지막 줄 `Assisted-by: <커밋하는 에이전트의 모델 ID>`). `git push` 금지.

## Review Focus

1. **새 탭이 며칠 전의 `succeeded` 를 본다** — "인증되었습니다" 라고 말하거나 `recheck()` 를 부르면 안 되고, "마지막 로그인: 성공" 한 줄만 보여야 한다. → Task 7 `test_an_unwatched_success_is_only_reported`
2. **세션 도중 사이드카가 재시작된다** — `status.json` 이 `failed` 로 정리되고, 재시작 전의 `start` 요청이 사람 없이 다시 실행되면 안 된다. → Task 4 `test_recover_marks_a_leftover_session_failed`, `test_recover_does_not_replay_the_last_request`
3. **세션이 없을 때 `cancel` 요청이 남는다** — 앱이 영원히 "준비하는 중" 에 머물면 안 되고 시작 버튼이 보여야 한다. → Task 7 `test_a_leftover_cancel_does_not_look_pending`
4. **자식이 SIGTERM 을 무시하거나, 세션이 뜨다 만다** — 결국 죽여야 하고, 어느 경로로 끝나든 `browser_profile/` 이 지워져야 한다. → Task 4 `test_a_stubborn_process_is_killed`, `test_a_launch_failure_cleans_up_what_started`
5. **`status.json`·`request.json` 이 깨지거나 반쯤 쓰였다** — 앱은 `idle` 로 보고 트레이스백 없이 그리고, 사이드카는 넘어가야 한다. → Task 3 `test_read_status_treats_a_broken_file_as_idle`, Task 4 `test_a_broken_request_is_ignored`, Task 7 `test_a_broken_status_file_still_offers_the_start_button`

---

## 파일 구조

| 파일 | 책임 | 태스크 |
|---|---|---|
| `pyproject.toml`, `uv.lock` | `login-browser` 그룹, mypy 대상 | 1, 4 |
| `deploy/login-browser/Dockerfile` | 사이드카 이미지 | 1, 5 |
| `deploy/login-browser/spike.sh` | 감시 루프 없이 세션을 손으로 띄우는 스파이크 | 1 |
| `src/notebooklm_st/core/login_protocol.py` | 두 컨테이너의 유일한 계약 | 2 |
| `src/notebooklm_st/services/login_session.py` | 앱 쪽 요청 쓰기·상태 읽기·판정 | 3 |
| `src/notebooklm_st/login_browser/supervisor.py` | 사이드카 감시 루프·세션 수명 | 4, 5 |
| `docker-compose.yml`, `Dockerfile`, `.github/workflows/build.yml` | 배포 | 5 |
| `src/notebooklm_st/core/errors.py` | `LOGIN_HINT`, `probe_failed_text()` | 6 |
| `src/notebooklm_st/pages/auth.py` | 「인증」 페이지 | 6, 7 |
| `src/notebooklm_st/components/auth_gate.py` | 배너: 안내 + 링크 | 6 |
| `src/notebooklm_st/app.py` | 페이지 등록 | 6 |
| `src/notebooklm_st/pages/_remote_login.py` | 원격 로그인 영역 | 7 |
| `README.md`, `docs/how-to/*.md` | 문서 | 8 |

---

### Task 1: 사이드카 기반 이미지와 스파이크

설계서 §13 의 가정 1·2·5 를 닫는다. 스파이크는 **이 PC 의 Docker Desktop** 에서 한다. 사이드카가 나중에 할 일을 감시 루프 없이 스크립트로 똑같이 재현한다.

- **에이전트가 확인한다** — 빌드, 버전, 앱 의존성 부재, 비root·read_only 기동(D), 해시 비밀번호 자동 접속(A), 틀린 비밀번호 거부, x11vnc 비노출.
- **사람이 확인한다** — 실제 구글 로그인(B·C), 휴대폰(E, 선택). 계정 비밀번호가 필요하므로 에이전트가 대신 입력하지 않는다.
- B 또는 C 가 "막힘" 이면 여기서 멈추고 보고한다. 이후 태스크를 진행하지 않는다.

홈서버는 **x86_64, Docker 26.1.4** 다(사용자 확인). 이 PC 의 Docker Desktop(linux/amd64, 29.8.0)과 아키텍처가 같아 이미지·크로미움 바이너리가 그대로 맞는다. 이 계획이 쓰는 compose 설정(`build.dockerfile`·`read_only`·`tmpfs`·`shm_size`·`user`)은 모두 Docker 26 이전부터 있던 것이다. 남는 홈서버 고유 조건(볼륨 권한·LAN 접근)은 Task 9 의 홈서버 E2E 에서 본다. 그 전에 따로 확인하고 싶으면 홈서버에서 같은 스크립트를 `deploy/login-browser/spike.sh up ~/notebooklm-spike` 로 돌리면 된다.

**Files:**
- Modify: `pyproject.toml` (`[dependency-groups]`)
- Modify: `uv.lock`
- Create: `deploy/login-browser/Dockerfile`
- Create: `deploy/login-browser/spike.sh`

**Interfaces:**
- Produces: 의존성 그룹 `login-browser`, 이미지 `notebooklm-st-login-browser` (감시 루프 없이 도구만 든 상태), `deploy/login-browser/spike.sh up|check|down`

**Docker 경로.** 에이전트 셸 PATH 에 `docker` 가 없다. 이 태스크의 명령은 모두 아래 변수를 쓴다(Git Bash).

```bash
export DOCKER=/c/Users/susot/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe
```

- [ ] **Step 1: 의존성 그룹을 나눈다**

`pyproject.toml` 의 `[dependency-groups]` 를 이렇게 바꾼다.

```toml
[dependency-groups]
# 원격 로그인 사이드카가 쓴다(deploy/login-browser/Dockerfile).
# 앱과 같은 락에서 설치되므로 notebooklm-py 버전이 어긋나지 않는다.
login-browser = ["notebooklm-py[browser]==0.8.1"]
dev = [
    # 데스크톱에서 notebooklm login 을 돌리는 데 필요하다. 컨테이너
    # 이미지는 uv sync --no-dev 로 이것을 뺀다.
    { include-group = "login-browser" },
    "mypy>=2.3.1",
    "pytest>=9.1.1",
    "ruff>=0.16.5",
]
```

- [ ] **Step 2: 락을 갱신하고 데스크톱 환경이 그대로인지 본다**

Run: `uv lock && uv sync && uv run python -c "import playwright, notebooklm; print('ok')"`
Expected: `ok`. `uv.lock` 의 diff 는 그룹 메타데이터만 바뀌고 패키지 버전은 그대로다(`git diff --stat uv.lock` 로 확인).

- [ ] **Step 3: 사이드카 Dockerfile 을 만든다**

`deploy/login-browser/Dockerfile`:

```dockerfile
# 원격 구글 로그인 사이드카 이미지.
#
# 앱 이미지와 따로 굽는다. 크로미움·가상 화면·화면 중계를 앱 이미지에
# 넣으면 수백 MB 가 늘고, 앱 이미지에 playwright 가 없다는 불변식이
# 깨진다(build.yml 이 단언한다).
#
# 설계: docs/superpowers/specs/2026-09-26-remote-login-design.md §6

# ── builder ────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
# 앱과 같은 락, login-browser 그룹만. streamlit 등 앱 의존성은 들어오지
# 않는다.
RUN uv sync --frozen --only-group login-browser --no-install-project

# ── runtime ────────────────────────────────────────────────
# 빌더와 같은 계열이어야 한다. /app/.venv 가 빌더의 인터프리터 경로를
# 절대 경로로 참조한다.
FROM python:3.13-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY --from=builder /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH
# playwright install --with-deps 는 apt 로 크로미움의 공유 라이브러리를
# 받으므로 root 인 이 단계에서 돈다. 브라우저는 /ms-playwright 에 두어
# 비root 사용자도 읽게 한다.
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify tzdata \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 1000 app \
 && useradd -u 1000 -g 1000 -M -s /usr/sbin/nologin app
# HOME 은 tmpfs(/tmp)다. 루트 파일시스템이 read_only 라 크로미움과
# x11vnc 가 쓸 곳이 필요하다. 프로필 경로는 앱 이미지와 같아야 한다.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    NOTEBOOKLM_HOME=/data/notebooklm \
    NOTEBOOKLM_ST_LOGIN_DIR=/data/login \
    TZ=Asia/Seoul
USER app
EXPOSE 6080
```

- [ ] **Step 4: 스파이크 스크립트를 만든다**

`deploy/login-browser/spike.sh` (실행 권한: `git update-index --chmod=+x deploy/login-browser/spike.sh`):

```bash
#!/usr/bin/env bash
# 원격 로그인 스파이크 — 사이드카 이미지만으로 구글 로그인이 되는지 본다.
#
# 감시 루프 없이, 사이드카가 세션마다 띄울 것(Xvfb → x11vnc →
# websockify → notebooklm login)을 운영과 같은 조건(비root 1000,
# read_only, /tmp tmpfs, shm 1GB)으로 손수 띄운다.
#
#   spike.sh up <데이터 디렉터리>     이미지를 굽고 세션을 띄운다
#   spike.sh check                    프로세스·포트·결과를 본다
#   spike.sh down <데이터 디렉터리>   내리고 스파이크 자격증명을 지운다
#
# 데이터 디렉터리에는 계정 동등 자격증명이 생긴다. 저장소 밖만 받는다.
# Docker 가 PATH 에 없으면 DOCKER 에 전체 경로를 준다.
#
# 설계: docs/superpowers/specs/2026-09-26-remote-login-design.md §13
set -euo pipefail

DOCKER="${DOCKER:-docker}"
IMAGE=notebooklm-st-login-browser:spike
NAME=notebooklm-st-login-spike
PORT="${SPIKE_PORT:-9005}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"

# Git Bash 가 /data 같은 컨테이너 경로를 윈도우 경로로 바꾸지 않게 한다.
export MSYS_NO_PATHCONV=1

usage() {
  sed -n '8,10p' "$0" >&2
  exit 2
}

# 데이터 디렉터리를 만들고, docker -v 에 넘길 호스트 경로를 출력한다.
data_dir() {
  [ -n "${1:-}" ] || usage
  mkdir -p "$1"
  local dir
  dir="$(cd "$1" && pwd)"
  case "$dir/" in
    "$REPO"/*)
      echo "저장소 안에는 둘 수 없습니다: $dir" >&2
      exit 2
      ;;
  esac
  # Docker Desktop(윈도우)은 윈도우 경로를 받는다.
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$dir"
  else
    echo "$dir"
  fi
}

up() {
  local data password
  data="$(data_dir "${1:-}")"
  "$DOCKER" build -f "$REPO/deploy/login-browser/Dockerfile" \
    -t "$IMAGE" "$REPO"
  # 호스트에서 sudo chown 하지 않아도 되게, 컨테이너의 root 로 맞춘다.
  "$DOCKER" run --rm --user 0:0 -v "$data:/data" "$IMAGE" \
    chown 1000:1000 /data
  password="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 8)"
  "$DOCKER" run -d --name "$NAME" -p "$PORT:6080" -v "$data:/data" \
    --shm-size=1g --read-only --tmpfs /tmp --user 1000:1000 \
    -e SPIKE_PASSWORD="$password" "$IMAGE" bash -c '
      Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
      for _ in $(seq 50); do
        [ -S /tmp/.X11-unix/X99 ] && break
        sleep 0.1
      done
      printf "%s\n" "$SPIKE_PASSWORD" > /tmp/vncpass
      chmod 600 /tmp/vncpass
      x11vnc -display :99 -localhost -rfbport 5900 \
        -passwdfile rm:/tmp/vncpass -forever -shared -quiet &
      websockify --web /usr/share/novnc 6080 localhost:5900 &
      DISPLAY=:99 NO_COLOR=1 python -m notebooklm login --fresh \
        --browser-timeout 900 > /tmp/login.log 2>&1
      echo $? > /tmp/exit
      sleep infinity'
  echo
  echo "뷰어: http://localhost:$PORT/vnc.html#autoconnect=1&resize=scale&password=$password"
  echo "다른 기기에서는 localhost 대신 이 기기의 LAN 주소를 쓴다."
}

check() {
  "$DOCKER" exec -i "$NAME" python - <<'EOF'
import os
from pathlib import Path

procs = sorted(
    {
        p.joinpath("comm").read_text().strip()
        for p in Path("/proc").glob("[0-9]*")
        if p.joinpath("comm").exists()
    }
)
print("uid:", os.getuid())
print("processes:", ", ".join(procs))


def listening(table):
    for line in Path(table).read_text().splitlines()[1:]:
        cols = line.split()
        if cols[3] != "0A":  # LISTEN
            continue
        host, port = cols[1].split(":")
        yield host, int(port, 16)


for host, port in sorted(set(listening("/proc/net/tcp"))):
    addr = ".".join(str(int(host[i : i + 2], 16)) for i in (6, 4, 2, 0))
    print(f"listen: {addr}:{port}")

try:
    Path("/etc/spike-write-test").write_text("x")
    print("rootfs: WRITABLE")
except OSError:
    print("rootfs: read-only")

exit_file = Path("/tmp/exit")
code = exit_file.read_text().strip() if exit_file.exists() else "(running)"
print("login exit:", code)
log_file = Path("/tmp/login.log")
text = log_file.read_text(errors="replace") if log_file.exists() else ""
lines = [line.strip() for line in text.splitlines() if line.strip()]
print("login log last line:", lines[-1] if lines else "(empty)")

# 파일 이름만 보인다. 내용은 자격증명이다.
profile = Path("/data/notebooklm/profiles/default")
names = sorted(p.name for p in profile.iterdir()) if profile.exists() else []
print("profile files:", ", ".join(names) or "(none)")
EOF
}

down() {
  local data
  data="$(data_dir "${1:-}")"
  "$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
  # 1000 소유 파일을 sudo 없이 지운다. find 로 /data 자체는 남긴다.
  "$DOCKER" run --rm --user 0:0 -v "$data:/data" "$IMAGE" \
    sh -c 'find /data -mindepth 1 -delete && ls -A /data'
  echo "스파이크 컨테이너와 자격증명을 지웠습니다."
}

case "${1:-}" in
  up) up "${2:-}" ;;
  check) check ;;
  down) down "${2:-}" ;;
  *) usage ;;
esac
```

- [ ] **Step 5: 이미지 자체를 확인한다 (에이전트)**

스파이크 데이터는 **저장소 밖** 세션 scratchpad 아래 `spike-data` 에 둔다(아래 `$SPIKE`). 저장소의 `data/` 는 `.gitignore` 에 없어 크로미움 프로필이 커밋될 수 있다.

Run: `"$DOCKER" build -f deploy/login-browser/Dockerfile -t notebooklm-st-login-browser:spike .`
Expected: 성공

Run: `"$DOCKER" run --rm notebooklm-st-login-browser:spike python -c "import importlib.metadata as m; print(m.version('notebooklm-py'))"`
Expected: `0.8.1`

Run: `"$DOCKER" run --rm notebooklm-st-login-browser:spike python -c "import streamlit"`
Expected: `ModuleNotFoundError: No module named 'streamlit'`

- [ ] **Step 6: 세션을 띄우고 기동 조건을 확인한다 (에이전트 — D)**

Run: `DOCKER="$DOCKER" deploy/login-browser/spike.sh up "$SPIKE"`
출력된 뷰어 주소를 기록한다. 비밀번호가 담겨 있으므로 보고에서는 비밀번호를 가린다.

5초 뒤 Run: `DOCKER="$DOCKER" deploy/login-browser/spike.sh check`
Expected:
- `uid: 1000`, `rootfs: read-only`
- `processes:` 에 `Xvfb`·`x11vnc`·websockify(`websockify` 또는 `python3`)·크로미움(`chrome`)
- `listen: 127.0.0.1:5900`(x11vnc 는 밖에 열리지 않는다), `listen: 0.0.0.0:6080`
- `login exit: (running)` — CLI 가 사람의 로그인을 기다리는 중

크로미움이 없거나 CLI 가 곧바로 끝났으면 `login log last line` 을 보고 원인을 찾는다. 추가 옵션(예: 크로미움 샌드박스, `/dev/shm`)이 필요하면 **그 옵션과 이유를 기록**하고 `spike.sh` 에 넣어 다시 띄운다. Step 9 에서 쓴다.

- [ ] **Step 7: 해시 비밀번호와 거부를 확인한다 (에이전트 — A)**

Playwright MCP 브라우저로 한다.

1. `browser_navigate` → Step 6 의 뷰어 주소(해시에 올바른 비밀번호).
2. `browser_wait_for` 3초 → `browser_take_screenshot`.
   Expected: 비밀번호 대화상자 없이 크로미움 화면(구글 로그인 페이지)이 보인다.
   `browser_evaluate`: `() => document.querySelector('#noVNC_credentials_dlg')?.classList.contains('noVNC_open') ?? false` → `false`
3. 같은 주소에서 `password=` 값만 `wrongpw1` 로 바꿔 다시 연다.
   Expected: 화면이 붙지 않는다(인증 실패 문구 또는 비밀번호 대화상자).
4. `browser_close`.

2 가 실패하면 `#&autoconnect=1&resize=scale&password=...`(해시 바로 뒤에 `&`) 형태로 한 번 더 시도하고 결과를 기록한다. noVNC 판에 따라 `[?&]` 뒤의 값만 읽을 수 있다.

**구글 로그인 화면에서 아무것도 입력하지 않는다.** 이메일 입력도 사람의 몫이다.

- [ ] **Step 8: 사람에게 로그인을 요청하고 멈춘다 (사람 — B·C·E)**

세션을 띄워 둔 채, 사용자에게 아래를 전달하고 **결과를 받을 때까지 멈춘다.**

> 이 PC 브라우저에서 아래 주소를 열어 구글 로그인을 끝까지 해 주세요. 5분 안에 끝내 주시면 됩니다.
> `<Step 6 의 뷰어 주소>`
> (선택) 휴대폰으로도 보시려면 같은 Wi-Fi 에서 `localhost` 를 이 PC 의 LAN 주소로 바꿔 여세요. 로그인은 한 번이면 되므로 휴대폰은 화면이 붙고 입력이 되는지만 봐도 됩니다. Windows 방화벽이 막으면 E 는 Task 9 로 미룹니다.
> 끝나면 "끝" 이라고, 막히면 화면에 나온 문구를 알려 주세요.

답을 받으면 Run: `DOCKER="$DOCKER" deploy/login-browser/spike.sh check`
Expected(성공): `login exit: 0`, `profile files:` 에 `storage_state.json` 이 있다.

| # | 질문 | 확인 주체 | 기록 |
|---|---|---|---|
| A | 해시 비밀번호로 바로 붙는가 | 에이전트(Step 7) | 예/아니오/`#&` 형태만 |
| B | 구글 로그인이 차단 없이 끝나는가 | 사람 | 예/아니오(문구) |
| C | `exit 0` 이고 `storage_state.json` 이 생겼는가 | 에이전트(check) | 예/아니오 |
| D | 비root·read_only 로 추가 옵션 없이 떴는가 | 에이전트(Step 6) | 예/아니오(옵션) |
| E | 휴대폰에서 화면이 붙고 입력이 되는가 | 사람 | 예/아니오/미시도 |

그 뒤 **반드시** Run: `DOCKER="$DOCKER" deploy/login-browser/spike.sh down "$SPIKE"`
Expected: `ls -A /data` 가 아무것도 출력하지 않고 "지웠습니다" 가 찍힌다. 스파이크 자격증명(쿠키·크로미움 프로필)이 남지 않았음을 사용자에게 알린다. 이 단계는 B·C 결과와 무관하게 한다.

- [ ] **Step 9: 결과를 반영하고 커밋한다**

- **B 또는 C 가 "아니오"** → 멈추고 사용자에게 보고한다. 이 설계는 성립하지 않는다. 이후 태스크를 진행하지 않으며, 이미지·스크립트를 커밋할지도 사용자에게 묻는다.
- **A 가 `#&` 형태로만 됐으면** → Task 3 의 `viewer_link()` 와 그 테스트 기대값, Task 7 의 iframe 기대값을 `#&autoconnect=...` 로 바꾸고 설계서 §7.3 을 다시 쓴다.
- **A 가 "아니오"** → 설계서 §7.3·§10 을 "비밀번호를 쿼리 문자열로 넘기고 websockify 요청 로그를 끈다(`--log-file /dev/null`)" 로 다시 쓰고, Task 3 의 `viewer_link()` 와 Task 4 의 websockify 명령을 그에 맞춰 바꾼다.
- **D 에서 옵션이 필요했으면** → 그 옵션을 Task 4 의 명령과 Task 5 의 compose 에 넣고 설계서 §6·§9.2 에 반영한다.
- 확인된 항목은 설계서 §13(미검증 가정)에서 §2(확인한 사실)로 옮겨 **그 절을 다시 쓴다.** 확인 환경이 데스크톱 Docker Desktop 이었음을 적고, 홈서버 확인은 Task 9 로 남긴다. 수정 이력은 남기지 않는다.

```bash
git add pyproject.toml uv.lock deploy/login-browser/Dockerfile deploy/login-browser/spike.sh docs/superpowers/specs/2026-09-26-remote-login-design.md
git commit   # 📦️ build(login-browser): 원격 로그인 사이드카 이미지와 스파이크 추가
```

---

### Task 2: 신호 프로토콜 — `core/login_protocol.py`

**Files:**
- Create: `src/notebooklm_st/core/login_protocol.py`
- Test: `tests/core/test_login_protocol.py`

**Interfaces:**
- Produces:
  - `DIR_ENV_VAR = "NOTEBOOKLM_ST_LOGIN_DIR"`, `REQUEST_FILE = "request.json"`, `STATUS_FILE = "status.json"`, `HEARTBEAT_FILE = "heartbeat"`
  - `class State(enum.StrEnum)`: `IDLE STARTING RUNNING SUCCEEDED FAILED TIMEOUT CANCELLED`
  - `ACTIVE_STATES: frozenset[State]` = `{STARTING, RUNNING}`
  - `class Action(enum.StrEnum)`: `START CANCEL`
  - `class ProtocolError(ValueError)`
  - `@dataclass(frozen=True) Request(id: str, action: Action, requested_at: str)` + `to_json() -> str`, `from_json(text) -> Request`
  - `@dataclass(frozen=True) Status(state: State, request_id: str|None=None, password: str|None=None, deadline: str|None=None, detail: str|None=None, updated_at: str|None=None)` + `to_json()`, `from_json()`
  - `IDLE: Status`
  - `now_iso() -> str`, `write_atomic(path: Path, text: str) -> None`
  - `read_request(directory: Path) -> Request | None`, `read_status(directory: Path) -> Status`
  - `write_request(directory: Path, request: Request) -> None`, `write_status(directory: Path, status: Status) -> None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/core/test_login_protocol.py`:

```python
"""원격 로그인 신호 파일 계약 테스트."""

import stat
import sys

import pytest

from notebooklm_st.core import login_protocol
from notebooklm_st.core.login_protocol import Action, State


def test_request_round_trips_through_json() -> None:
    """요청은 JSON 으로 갔다 와도 같다."""
    request = login_protocol.Request(
        id="r1", action=Action.START, requested_at="2026-09-26T12:00:00+00:00"
    )

    assert login_protocol.Request.from_json(request.to_json()) == request


def test_status_round_trips_through_json() -> None:
    """상태는 JSON 으로 갔다 와도 같다."""
    status = login_protocol.Status(
        state=State.RUNNING,
        request_id="r1",
        password="pw123456",
        deadline="2026-09-26T12:05:00+00:00",
        updated_at="2026-09-26T12:00:00+00:00",
    )

    assert login_protocol.Status.from_json(status.to_json()) == status


@pytest.mark.parametrize(
    "text",
    [
        "{",
        "[]",
        '{"action": "start", "requested_at": "x"}',
        '{"id": "r1", "action": "jump", "requested_at": "x"}',
        '{"id": "r1", "action": "start", "requested_at": 3}',
    ],
)
def test_a_malformed_request_raises_a_protocol_error(text: str) -> None:
    """계약과 다른 요청은 ProtocolError 로 알린다."""
    with pytest.raises(login_protocol.ProtocolError):
        login_protocol.Request.from_json(text)


@pytest.mark.parametrize(
    "text",
    ["{", '{"state": "flying"}', '{"state": "running", "password": 1}'],
)
def test_a_malformed_status_raises_a_protocol_error(text: str) -> None:
    """계약과 다른 상태는 ProtocolError 로 알린다."""
    with pytest.raises(login_protocol.ProtocolError):
        login_protocol.Status.from_json(text)


def test_missing_files_read_as_nothing(tmp_path) -> None:
    """아직 아무도 쓰지 않았으면 요청은 없고 상태는 idle 이다."""
    assert login_protocol.read_request(tmp_path) is None
    assert login_protocol.read_status(tmp_path) == login_protocol.IDLE


def test_written_files_read_back(tmp_path) -> None:
    """쓴 것을 그대로 읽는다. 디렉터리가 없으면 만든다."""
    directory = tmp_path / "login"
    request = login_protocol.Request(
        id="r1", action=Action.CANCEL, requested_at="t"
    )
    status = login_protocol.Status(state=State.FAILED, detail="끝")

    login_protocol.write_request(directory, request)
    login_protocol.write_status(directory, status)

    assert login_protocol.read_request(directory) == request
    assert login_protocol.read_status(directory) == status


def test_write_atomic_leaves_no_temporary_file(tmp_path) -> None:
    """바꿔치기가 끝나면 임시 파일이 남지 않는다."""
    login_protocol.write_atomic(tmp_path / "status.json", "{}")

    assert [path.name for path in tmp_path.iterdir()] == ["status.json"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX 권한만 확인한다")
def test_write_atomic_keeps_the_file_private(tmp_path) -> None:
    """세션 비밀번호를 담으므로 소유자만 읽는다."""
    path = tmp_path / "status.json"

    login_protocol.write_atomic(path, "{}")

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_active_states_are_the_ones_with_a_live_session() -> None:
    """세션이 떠 있는 상태는 starting 과 running 뿐이다."""
    assert login_protocol.ACTIVE_STATES == {State.STARTING, State.RUNNING}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/core/test_login_protocol.py -v`
Expected: FAIL — `ImportError: cannot import name 'login_protocol'`

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/core/login_protocol.py`:

```python
"""원격 로그인 사이드카와 앱이 주고받는 파일의 계약.

두 컨테이너는 공유 볼륨의 파일 세 개로만 신호를 주고받는다. 파일마다
쓰는 쪽이 하나라 잠금이 필요 없다.

- ``request.json`` — 앱만 쓴다. 로그인 시작·취소 요청
- ``status.json`` — 사이드카만 쓴다. 세션 상태와 마지막 결과
- ``heartbeat`` — 사이드카만 쓴다. 수정 시각만 의미가 있다

표준 라이브러리만 쓴다. 사이드카 이미지에는 앱의 의존성이 없다.

설계: docs/superpowers/specs/2026-09-26-remote-login-design.md §5
"""

import dataclasses
import datetime as dt
import enum
import json
import os
import tempfile
from pathlib import Path

DIR_ENV_VAR = "NOTEBOOKLM_ST_LOGIN_DIR"
REQUEST_FILE = "request.json"
STATUS_FILE = "status.json"
HEARTBEAT_FILE = "heartbeat"


class State(enum.StrEnum):
    """로그인 세션의 상태."""

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


ACTIVE_STATES = frozenset({State.STARTING, State.RUNNING})
"""세션이 떠 있는 상태. 나머지는 대기이거나 마지막 결과다."""


class Action(enum.StrEnum):
    """앱이 사이드카에 보내는 요청의 종류."""

    START = "start"
    CANCEL = "cancel"


class ProtocolError(ValueError):
    """파일 내용이 계약과 다르다."""


@dataclasses.dataclass(frozen=True, slots=True)
class Request:
    """앱이 쓰는 요청.

    ``id`` 는 요청마다 새로 만든다. 사이드카는 같은 ``id`` 를 두 번
    처리하지 않는다.
    """

    id: str
    action: Action
    requested_at: str

    def to_json(self) -> str:
        """JSON 문자열로 바꾼다."""
        return json.dumps(dataclasses.asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "Request":
        """JSON 문자열을 읽는다.

        Raises:
            ProtocolError: 계약과 다른 내용일 때.
        """
        data = _load_object(text)
        try:
            action = Action(_required_str(data, "action"))
        except ValueError as error:
            raise ProtocolError(f"알 수 없는 요청입니다: {error}") from error
        return cls(
            id=_required_str(data, "id"),
            action=action,
            requested_at=_required_str(data, "requested_at"),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Status:
    """사이드카가 쓰는 세션 상태.

    ``password`` 와 ``deadline`` 은 ``running`` 일 때만 값이 있다.
    """

    state: State
    request_id: str | None = None
    password: str | None = None
    deadline: str | None = None
    detail: str | None = None
    updated_at: str | None = None

    def to_json(self) -> str:
        """JSON 문자열로 바꾼다."""
        return json.dumps(dataclasses.asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "Status":
        """JSON 문자열을 읽는다.

        Raises:
            ProtocolError: 계약과 다른 내용일 때.
        """
        data = _load_object(text)
        try:
            state = State(_required_str(data, "state"))
        except ValueError as error:
            raise ProtocolError(f"알 수 없는 상태입니다: {error}") from error
        return cls(
            state=state,
            request_id=_optional_str(data, "request_id"),
            password=_optional_str(data, "password"),
            deadline=_optional_str(data, "deadline"),
            detail=_optional_str(data, "detail"),
            updated_at=_optional_str(data, "updated_at"),
        )


IDLE = Status(state=State.IDLE)
"""아직 아무도 상태를 쓰지 않았을 때."""


def now_iso() -> str:
    """지금 시각을 UTC ISO 8601 로 돌려준다.

    두 컨테이너의 시간대 설정과 무관하게 비교할 수 있게 UTC 로 둔다.
    """
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def write_atomic(path: Path, text: str) -> None:
    """읽는 쪽이 반쯤 쓰인 파일을 보지 않게 쓴다.

    같은 디렉터리의 임시 파일에 쓴 뒤 ``os.replace`` 로 바꾼다. 권한은
    ``0600`` 이다. 상태 파일이 세션 비밀번호를 담는다.

    Args:
        path: 쓸 파일.
        text: 내용.
    """
    fd, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def read_request(directory: Path) -> Request | None:
    """요청 파일을 읽는다.

    Returns:
        요청. 파일이 없으면 ``None``.

    Raises:
        ProtocolError: 계약과 다른 내용일 때.
    """
    try:
        text = (directory / REQUEST_FILE).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return Request.from_json(text)


def read_status(directory: Path) -> Status:
    """상태 파일을 읽는다.

    Returns:
        상태. 파일이 없으면 ``IDLE``.

    Raises:
        ProtocolError: 계약과 다른 내용일 때.
    """
    try:
        text = (directory / STATUS_FILE).read_text(encoding="utf-8")
    except FileNotFoundError:
        return IDLE
    return Status.from_json(text)


def write_request(directory: Path, request: Request) -> None:
    """요청 파일을 쓴다. 디렉터리가 없으면 만든다."""
    directory.mkdir(parents=True, exist_ok=True)
    write_atomic(directory / REQUEST_FILE, request.to_json())


def write_status(directory: Path, status: Status) -> None:
    """상태 파일을 쓴다. 디렉터리가 없으면 만든다."""
    directory.mkdir(parents=True, exist_ok=True)
    write_atomic(directory / STATUS_FILE, status.to_json())


def _load_object(text: str) -> dict[str, object]:
    """JSON 객체를 읽는다."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProtocolError(f"JSON 이 아닙니다: {error}") from error
    if not isinstance(data, dict):
        raise ProtocolError("JSON 객체가 아닙니다")
    return data


def _required_str(data: dict[str, object], key: str) -> str:
    """비어 있지 않은 문자열 필드를 꺼낸다."""
    value = data.get(key)
    if isinstance(value, str) and value:
        return value
    raise ProtocolError(f"{key} 가 없거나 문자열이 아닙니다")


def _optional_str(data: dict[str, object], key: str) -> str | None:
    """없어도 되는 문자열 필드를 꺼낸다."""
    value = data.get(key)
    if value is None or isinstance(value, str):
        return value
    raise ProtocolError(f"{key} 는 문자열이어야 합니다")
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/core/test_login_protocol.py -v`
Expected: PASS (윈도우에서는 권한 테스트 1개 SKIP)

- [ ] **Step 5: 검증 4단을 돌리고 커밋한다**

Run: 검증 4단 (Global Constraints)
Expected: 모두 통과

```bash
git add src/notebooklm_st/core/login_protocol.py tests/core/test_login_protocol.py
git commit   # ✨ feat(login): 원격 로그인 신호 파일 계약 추가
```

---

### Task 3: 앱 쪽 세션 조회 — `services/login_session.py`

**Files:**
- Create: `src/notebooklm_st/services/login_session.py`
- Modify: `tests/conftest.py` (env 격리 fixture 추가)
- Test: `tests/services/test_login_session.py`

**Interfaces:**
- Consumes: Task 2 의 `login_protocol` 전체
- Produces:
  - `VIEWER_URL_ENV_VAR = "NOTEBOOKLM_ST_LOGIN_VIEWER_URL"`, `HEARTBEAT_STALE_AFTER = 10.0`
  - `viewer_url() -> str | None` — 끝의 `/` 제거, 비었으면 `None`
  - `login_dir() -> Path | None`
  - `read_status(directory: Path) -> login_protocol.Status` — 없음·깨짐·읽기 실패 → `IDLE`
  - `sidecar_alive(directory: Path, now: float) -> bool`
  - `pending_request(directory: Path) -> login_protocol.Request | None` — 깨짐 → `None`
  - `request_start(directory: Path) -> str`, `request_cancel(directory: Path) -> str` — 새 요청 `id`
  - `busy(registry: runs.RunRegistry, digests: digest_runner.DigestRegistry) -> bool`
  - `viewer_link(base: str, password: str) -> str`
  - `remaining_seconds(status: login_protocol.Status, now: dt.datetime) -> int | None`

- [ ] **Step 1: 테스트가 개발 기기의 설정을 보지 않게 막는다**

`tests/conftest.py` 끝에 더한다. import 에 `login_session` 과 `login_protocol` 을 추가한다.

```python
from notebooklm_st.core import login_protocol
from notebooklm_st.services import auth, login_session, outline, store
```

```python
@pytest.fixture(autouse=True)
def clear_login_env(monkeypatch) -> None:
    """개발 기기의 원격 로그인 설정이 테스트에 새지 않게 막는다.

    필요한 테스트가 직접 채워 쓴다.
    """
    monkeypatch.delenv(login_session.VIEWER_URL_ENV_VAR, raising=False)
    monkeypatch.delenv(login_protocol.DIR_ENV_VAR, raising=False)
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/services/test_login_session.py`:

```python
"""앱 쪽 원격 로그인 세션 조회 테스트."""

import datetime as dt
import logging
import os

from notebooklm_st.core import login_protocol
from notebooklm_st.core.login_protocol import Action, State
from notebooklm_st.services import digest_runner, login_session, runs


def test_viewer_url_is_none_when_unset() -> None:
    """설정이 없으면 원격 로그인을 끈다."""
    assert login_session.viewer_url() is None


def test_viewer_url_drops_a_trailing_slash(monkeypatch) -> None:
    """끝의 / 를 떼어 경로를 이어 붙이기 쉽게 한다."""
    monkeypatch.setenv(
        login_session.VIEWER_URL_ENV_VAR, " http://192.168.0.10:9005/ "
    )

    assert login_session.viewer_url() == "http://192.168.0.10:9005"


def test_login_dir_follows_the_environment(monkeypatch, tmp_path) -> None:
    """신호 디렉터리는 환경변수가 정한다."""
    assert login_session.login_dir() is None

    monkeypatch.setenv(login_protocol.DIR_ENV_VAR, str(tmp_path))

    assert login_session.login_dir() == tmp_path


def test_read_status_treats_a_missing_file_as_idle(tmp_path) -> None:
    """사이드카가 아직 아무것도 쓰지 않았으면 idle 이다."""
    assert login_session.read_status(tmp_path).state is State.IDLE


def test_read_status_treats_a_broken_file_as_idle(tmp_path, caplog) -> None:
    """깨진 상태 파일은 idle 로 보고 경고만 남긴다."""
    (tmp_path / login_protocol.STATUS_FILE).write_text("{", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        status = login_session.read_status(tmp_path)

    assert status.state is State.IDLE
    assert "상태 파일" in caplog.text


def test_sidecar_alive_checks_the_heartbeat_age(tmp_path) -> None:
    """heartbeat 가 10초 안에 갱신됐으면 살아 있다."""
    heartbeat = tmp_path / login_protocol.HEARTBEAT_FILE
    assert login_session.sidecar_alive(tmp_path, now=1000.0) is False

    heartbeat.touch()
    os.utime(heartbeat, (1000.0, 1000.0))

    assert login_session.sidecar_alive(tmp_path, now=1010.0) is True
    assert login_session.sidecar_alive(tmp_path, now=1010.5) is False


def test_request_start_writes_a_fresh_request(tmp_path) -> None:
    """시작 요청은 매번 새 id 로 쓴다."""
    directory = tmp_path / "login"

    first = login_session.request_start(directory)
    second = login_session.request_start(directory)

    request = login_session.pending_request(directory)
    assert first != second
    assert request is not None
    assert request.id == second
    assert request.action is Action.START


def test_request_cancel_writes_a_cancel(tmp_path) -> None:
    """취소 요청도 새 id 를 갖는다."""
    request_id = login_session.request_cancel(tmp_path)

    request = login_session.pending_request(tmp_path)
    assert request is not None
    assert request.id == request_id
    assert request.action is Action.CANCEL


def test_pending_request_ignores_a_broken_file(tmp_path) -> None:
    """깨진 요청 파일은 없는 것으로 본다."""
    (tmp_path / login_protocol.REQUEST_FILE).write_text("[", encoding="utf-8")

    assert login_session.pending_request(tmp_path) is None


def test_busy_sees_a_running_query() -> None:
    """질의가 돌고 있으면 바쁘다."""
    registry = runs.RunRegistry()
    registry.create("https://youtu.be/x", "x", ("q",))

    assert login_session.busy(registry, digest_runner.DigestRegistry())


def test_busy_sees_a_running_digest() -> None:
    """정리본을 쓰고 있으면 바쁘다."""
    digests = digest_runner.DigestRegistry()
    digests.start()

    assert login_session.busy(runs.RunRegistry(), digests)


def test_not_busy_when_nothing_runs() -> None:
    """아무것도 돌지 않으면 한가하다."""
    assert not login_session.busy(
        runs.RunRegistry(), digest_runner.DigestRegistry()
    )


def test_viewer_link_puts_the_password_in_the_hash() -> None:
    """비밀번호는 서버로 가지 않는 해시에 둔다."""
    link = login_session.viewer_link("http://h:9005", "pw123456")

    assert link == (
        "http://h:9005/vnc.html#autoconnect=1&resize=scale&password=pw123456"
    )


def test_remaining_seconds_counts_down_to_the_deadline() -> None:
    """마감까지 남은 초. 지났으면 0, 마감이 없으면 None."""
    now = dt.datetime(2026, 9, 26, 12, 0, tzinfo=dt.UTC)
    status = login_protocol.Status(
        state=State.RUNNING, deadline="2026-09-26T12:01:30+00:00"
    )

    assert login_session.remaining_seconds(status, now) == 90
    assert (
        login_session.remaining_seconds(
            status, now + dt.timedelta(minutes=5)
        )
        == 0
    )
    assert login_session.remaining_seconds(login_protocol.IDLE, now) is None```

- [ ] **Step 3: 실패를 확인한다**

Run: `uv run pytest tests/services/test_login_session.py -v`
Expected: FAIL — `ImportError: cannot import name 'login_session'`

- [ ] **Step 4: 구현한다**

`src/notebooklm_st/services/login_session.py`:

```python
"""앱 쪽에서 원격 로그인 사이드카와 이야기한다.

사이드카와는 공유 볼륨의 파일로만 주고받는다(``core.login_protocol``).
이 모듈은 요청을 쓰고 상태를 읽을 뿐 화면 문구를 만들지 않는다.

설계: docs/superpowers/specs/2026-09-26-remote-login-design.md §8
"""

import datetime as dt
import logging
import os
import urllib.parse
import uuid
from pathlib import Path

from notebooklm_st.core import login_protocol
from notebooklm_st.services import digest_runner, runs

logger = logging.getLogger(__name__)

VIEWER_URL_ENV_VAR = "NOTEBOOKLM_ST_LOGIN_VIEWER_URL"

HEARTBEAT_STALE_AFTER = 10.0
"""heartbeat 가 이보다 오래 멈춰 있으면 사이드카가 꺼진 것으로 본다(초).

사이드카는 1초마다 갱신한다. 세션을 띄우는 동안 몇 초 멈출 수 있어
넉넉히 잡는다.
"""


def viewer_url() -> str | None:
    """사용자 브라우저가 닿는 noVNC 주소.

    컨테이너는 홈서버의 LAN 주소를 모르므로 설정으로 받는다.

    Returns:
        끝의 ``/`` 를 뗀 주소. 설정이 없으면 ``None`` — 원격 로그인을
        쓰지 않는다.
    """
    value = os.environ.get(VIEWER_URL_ENV_VAR, "").strip().rstrip("/")
    return value or None


def login_dir() -> Path | None:
    """신호 파일을 두는 디렉터리.

    Returns:
        디렉터리. 설정이 없으면 ``None``.
    """
    value = os.environ.get(login_protocol.DIR_ENV_VAR, "").strip()
    return Path(value) if value else None


def read_status(directory: Path) -> login_protocol.Status:
    """사이드카의 상태를 읽는다.

    파일이 깨졌거나 읽히지 않으면 ``idle`` 로 본다. 화면이 트레이스백
    대신 시작 버튼을 그리게 하려는 것이다. 사이드카가 다음에 쓸 때
    바로잡힌다.

    Returns:
        상태.
    """
    try:
        return login_protocol.read_status(directory)
    except (OSError, login_protocol.ProtocolError) as error:
        logger.warning("원격 로그인 상태 파일을 읽지 못했습니다: %s", error)
        return login_protocol.IDLE


def sidecar_alive(directory: Path, now: float) -> bool:
    """사이드카가 떠 있는지 heartbeat 로 판정한다.

    Args:
        directory: 신호 디렉터리.
        now: 지금 시각(``time.time()``).

    Returns:
        heartbeat 가 ``HEARTBEAT_STALE_AFTER`` 초 안에 갱신됐으면 ``True``.
    """
    heartbeat = directory / login_protocol.HEARTBEAT_FILE
    try:
        modified = heartbeat.stat().st_mtime
    except OSError:
        return False
    return now - modified <= HEARTBEAT_STALE_AFTER


def pending_request(directory: Path) -> login_protocol.Request | None:
    """앱이 마지막으로 쓴 요청.

    상태의 ``request_id`` 와 비교해 사이드카가 아직 받지 않은 요청을
    가린다.

    Returns:
        요청. 없거나 깨졌으면 ``None``.
    """
    try:
        return login_protocol.read_request(directory)
    except (OSError, login_protocol.ProtocolError):
        return None


def request_start(directory: Path) -> str:
    """로그인 시작을 요청한다.

    Returns:
        새 요청의 ``id``. 화면이 이 요청을 지켜보는 데 쓴다.
    """
    return _write_request(directory, login_protocol.Action.START)


def request_cancel(directory: Path) -> str:
    """진행 중인 로그인의 취소를 요청한다.

    Returns:
        새 요청의 ``id``.
    """
    return _write_request(directory, login_protocol.Action.CANCEL)


def busy(
    registry: runs.RunRegistry, digests: digest_runner.DigestRegistry
) -> bool:
    """질의나 정리본이 돌고 있는지.

    돌고 있는 작업은 옛 쿠키를 들고 있다가 회전할 때 파일에 되쓴다.
    새 로그인 직후 그 되쓰기가 일어나면 새 쿠키가 덮일 수 있어 시작을
    막는 데 쓴다.

    Returns:
        하나라도 돌고 있으면 ``True``.
    """
    return registry.running_count() > 0 or digests.is_running()


def viewer_link(base: str, password: str) -> str:
    """iframe 에 넣을 noVNC 주소.

    비밀번호는 해시에 둔다. 해시는 서버로 전송되지 않아 요청 로그에
    남지 않는다.

    Args:
        base: ``viewer_url()`` 의 값.
        password: 이번 세션의 비밀번호.

    Returns:
        자동 접속·화면 맞춤이 켜진 주소.
    """
    secret = urllib.parse.quote(password, safe="")
    return f"{base}/vnc.html#autoconnect=1&resize=scale&password={secret}"


def remaining_seconds(
    status: login_protocol.Status, now: dt.datetime
) -> int | None:
    """세션 마감까지 남은 초.

    Args:
        status: 사이드카의 상태.
        now: 지금 시각(UTC, aware).

    Returns:
        남은 초. 지났으면 0, 마감이 없으면 ``None``.
    """
    if status.deadline is None:
        return None
    deadline = dt.datetime.fromisoformat(status.deadline)
    return max(0, int((deadline - now).total_seconds()))


def _write_request(directory: Path, action: login_protocol.Action) -> str:
    """새 요청을 쓴다."""
    request = login_protocol.Request(
        id=uuid.uuid4().hex,
        action=action,
        requested_at=login_protocol.now_iso(),
    )
    login_protocol.write_request(directory, request)
    return request.id
```

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/services/test_login_session.py -v`
Expected: PASS

- [ ] **Step 6: 검증 4단을 돌리고 커밋한다**

```bash
git add src/notebooklm_st/services/login_session.py tests/services/test_login_session.py tests/conftest.py
git commit   # ✨ feat(login): 앱 쪽 원격 로그인 세션 조회 추가
```

---

### Task 4: 사이드카 감시 루프 — 상태 기계

실제 프로세스는 Task 5 에서 붙인다. 여기서는 주입한 가짜로 세션 수명 전체를 검증한다.

**Files:**
- Create: `src/notebooklm_st/login_browser/__init__.py`
- Create: `src/notebooklm_st/login_browser/supervisor.py`
- Modify: `pyproject.toml` (`[[tool.mypy.overrides]]` 의 `module`)
- Test: `tests/login_browser/__init__.py`, `tests/login_browser/test_supervisor.py`, `tests/login_browser/test_isolation.py`

**Interfaces:**
- Consumes: Task 2 의 `login_protocol`
- Produces (Task 5 가 쓴다):
  - `class ProcessLike(Protocol)`: `poll() -> int | None`, `terminate() -> None`, `kill() -> None`, `wait(timeout: float) -> int` (시간 초과 시 `subprocess.TimeoutExpired`)
  - `Launcher = Callable[[Sequence[str], Mapping[str, str], Path | None], ProcessLike]` — `(argv, env, log_path)`. `log_path` 가 있으면 stdout·stderr 를 그 파일로
  - `class Supervisor(*, login_dir, profile_dir, work_dir, launch, clock, wait_ready, env, make_password=_password)` + `recover()`, `tick()`, `shutdown()`
  - 상수 `SESSION_SECONDS = 300`, `CLI_BROWSER_TIMEOUT = 900`, `DISPLAY = ":99"`, `VNC_PORT = 5900`, `WEB_PORT = 6080`, `NOVNC_WEB = "/usr/share/novnc"`, `PASSWORD_FILE = "vncpass"`, `LOG_FILE = "login.log"`, `TICK_SECONDS = 1.0`, `STOP_GRACE = 5.0`
  - 문구 `DETAIL_RESTARTED`, `DETAIL_STOPPED`, `DETAIL_RELAY`

- [ ] **Step 1: mypy 대상에 넣는다**

`pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = [
    "notebooklm_st.core.*",
    "notebooklm_st.services.*",
    "notebooklm_st.login_browser.*",
]
disallow_untyped_defs = true
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/login_browser/__init__.py` 는 빈 파일이다.

`tests/login_browser/test_supervisor.py`:

```python
"""원격 로그인 사이드카 감시 루프 테스트.

실제 Xvfb·크로미움 없이, 프로세스 실행기와 시계를 가짜로 끼워 상태
기계 전체를 검증한다.
"""

import dataclasses
import datetime as dt
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from notebooklm_st.core import login_protocol
from notebooklm_st.core.login_protocol import Action, State
from notebooklm_st.login_browser import supervisor

PASSWORD = "pw123456"


class FakeProcess:
    """자식 프로세스 흉내. 종료 코드를 테스트가 정한다."""

    def __init__(self, argv: Sequence[str]) -> None:
        self.argv = list(argv)
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False
        self.ignore_term = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        if not self.ignore_term and self.returncode is None:
            self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float) -> int:
        if self.returncode is None:
            raise subprocess.TimeoutExpired(self.argv, timeout)
        return self.returncode


class FakeLauncher:
    """띄운 프로세스를 기록한다. 이름이 ``fail_on`` 이면 실패한다."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.processes: list[FakeProcess] = []
        self.envs: list[dict[str, str]] = []
        self.logs: list[Path | None] = []

    def __call__(
        self,
        argv: Sequence[str],
        env: Mapping[str, str],
        log_path: Path | None,
    ) -> FakeProcess:
        if argv[0] == self.fail_on:
            raise FileNotFoundError(argv[0])
        process = FakeProcess(argv)
        self.processes.append(process)
        self.envs.append(dict(env))
        self.logs.append(log_path)
        return process

    def named(self, name: str) -> FakeProcess:
        return next(p for p in self.processes if p.argv[0] == name)

    @property
    def cli(self) -> FakeProcess:
        return next(p for p in self.processes if p.argv[1:3] == ["-m", "notebooklm"])


class Clock:
    """테스트가 돌리는 시계."""

    def __init__(self) -> None:
        self.now = dt.datetime(2026, 9, 26, 12, 0, tzinfo=dt.UTC)

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += dt.timedelta(seconds=seconds)


@dataclasses.dataclass
class Rig:
    """감시 루프와 그 주변."""

    sup: supervisor.Supervisor
    launcher: FakeLauncher
    clock: Clock
    login_dir: Path
    browser_profile: Path
    work_dir: Path

    def request(self, request_id: str, action: Action = Action.START) -> None:
        login_protocol.write_request(
            self.login_dir,
            login_protocol.Request(
                id=request_id, action=action, requested_at="t"
            ),
        )

    def status(self) -> login_protocol.Status:
        return login_protocol.read_status(self.login_dir)


def make_rig(
    tmp_path: Path, *, fail_on: str | None = None, ready: bool = True
) -> Rig:
    login_dir = tmp_path / "login"
    profile_dir = tmp_path / "notebooklm" / "profiles" / "default"
    browser_profile = profile_dir / "browser_profile"
    browser_profile.mkdir(parents=True)
    (browser_profile / "Cookies").write_text("secret", encoding="utf-8")
    work_dir = tmp_path / "work"
    launcher = FakeLauncher(fail_on=fail_on)
    clock = Clock()
    sup = supervisor.Supervisor(
        login_dir=login_dir,
        profile_dir=profile_dir,
        work_dir=work_dir,
        launch=launcher,
        clock=clock,
        wait_ready=lambda: ready,
        env={"PATH": "/usr/bin"},
        make_password=lambda: PASSWORD,
    )
    return Rig(sup, launcher, clock, login_dir, browser_profile, work_dir)


@pytest.fixture
def rig(tmp_path) -> Rig:
    return make_rig(tmp_path)


def test_a_start_request_opens_a_session(rig: Rig) -> None:
    """시작 요청을 받으면 네 프로세스를 순서대로 띄우고 running 을 쓴다."""
    rig.request("r1")

    rig.sup.tick()

    names = [p.argv[0] for p in rig.launcher.processes]
    assert names == ["Xvfb", "x11vnc", "websockify", sys.executable]
    status = rig.status()
    assert status.state is State.RUNNING
    assert status.request_id == "r1"
    assert status.password == PASSWORD
    assert status.deadline == "2026-09-26T12:05:00+00:00"


def test_the_cli_logs_in_fresh_on_the_virtual_display(rig: Rig) -> None:
    """CLI 는 깨끗한 프로필로, 가상 화면 위에서, 긴 시한으로 돈다."""
    rig.request("r1")

    rig.sup.tick()

    cli = rig.launcher.cli
    assert cli.argv[3:] == ["login", "--fresh", "--browser-timeout", "900"]
    index = rig.launcher.processes.index(cli)
    assert rig.launcher.envs[index]["DISPLAY"] == ":99"
    assert rig.launcher.logs[index] == rig.work_dir / supervisor.LOG_FILE


def test_x11vnc_reads_the_password_from_a_private_file(rig: Rig) -> None:
    """비밀번호는 명령줄이 아니라 파일로 넘기고, 밖에서 닿지 않게 연다."""
    rig.request("r1")

    rig.sup.tick()

    argv = rig.launcher.named("x11vnc").argv
    password_file = rig.work_dir / supervisor.PASSWORD_FILE
    assert f"rm:{password_file}" in argv
    assert "-localhost" in argv
    assert PASSWORD not in argv
    assert password_file.read_text(encoding="utf-8") == PASSWORD + "\n"


def test_the_same_request_is_handled_once(rig: Rig) -> None:
    """같은 요청을 여러 번 읽어도 세션은 하나다."""
    rig.request("r1")

    rig.sup.tick()
    rig.sup.tick()

    assert len(rig.launcher.processes) == 4


def test_a_second_start_during_a_session_is_ignored(rig: Rig) -> None:
    """세션 중의 새 시작 요청은 무시한다."""
    rig.request("r1")
    rig.sup.tick()

    rig.request("r2")
    rig.sup.tick()

    assert len(rig.launcher.processes) == 4
    assert rig.status().request_id == "r1"


def test_a_successful_login_is_reported_and_cleaned_up(rig: Rig) -> None:
    """CLI 가 0 으로 끝나면 성공이고, 흔적을 모두 지운다."""
    rig.request("r1")
    rig.sup.tick()

    rig.launcher.cli.returncode = 0
    rig.sup.tick()

    status = rig.status()
    assert status.state is State.SUCCEEDED
    assert status.request_id == "r1"
    assert status.password is None
    assert status.deadline is None
    assert all(p.poll() is not None for p in rig.launcher.processes)
    assert not rig.browser_profile.exists()
    assert not (rig.work_dir / supervisor.PASSWORD_FILE).exists()


def test_a_failed_login_reports_the_last_log_line(rig: Rig) -> None:
    """CLI 가 실패하면 로그 마지막 줄을 사유로 남기고 로그를 지운다."""
    rig.request("r1")
    rig.sup.tick()
    log = rig.work_dir / supervisor.LOG_FILE
    log.write_text("시작\n\nError: boom  \n\n", encoding="utf-8")

    rig.launcher.cli.returncode = 1
    rig.sup.tick()

    status = rig.status()
    assert status.state is State.FAILED
    assert status.detail == "Error: boom"
    assert not log.exists()
    assert not rig.browser_profile.exists()


def test_a_failed_login_without_output_reports_the_exit_code(rig: Rig) -> None:
    """로그가 비었으면 종료 코드를 사유로 쓴다."""
    rig.request("r1")
    rig.sup.tick()

    rig.launcher.cli.returncode = 2
    rig.sup.tick()

    assert rig.status().detail == "종료 코드 2"


def test_the_session_times_out_at_the_deadline(rig: Rig) -> None:
    """300초가 지나면 사이드카가 끝낸다."""
    rig.request("r1")
    rig.sup.tick()

    rig.clock.advance(299)
    rig.sup.tick()
    assert rig.status().state is State.RUNNING

    rig.clock.advance(1)
    rig.sup.tick()

    assert rig.status().state is State.TIMEOUT
    assert rig.launcher.cli.terminated
    assert not rig.browser_profile.exists()


def test_a_cancel_request_ends_the_session(rig: Rig) -> None:
    """취소 요청을 받으면 세션을 끝내고 cancelled 를 쓴다."""
    rig.request("r1")
    rig.sup.tick()

    rig.request("r2", Action.CANCEL)
    rig.sup.tick()

    status = rig.status()
    assert status.state is State.CANCELLED
    assert status.request_id == "r1"
    assert not rig.browser_profile.exists()


def test_a_cancel_without_a_session_is_ignored(rig: Rig) -> None:
    """세션이 없을 때의 취소는 아무 일도 하지 않는다."""
    rig.request("r1", Action.CANCEL)

    rig.sup.tick()

    assert rig.launcher.processes == []
    assert rig.status() == login_protocol.IDLE


def test_a_dead_relay_fails_the_session(rig: Rig) -> None:
    """화면 중계가 죽으면 사람이 로그인할 수 없으므로 실패로 끝낸다."""
    rig.request("r1")
    rig.sup.tick()

    rig.launcher.named("websockify").returncode = 1
    rig.sup.tick()

    status = rig.status()
    assert status.state is State.FAILED
    assert status.detail == supervisor.DETAIL_RELAY
    assert rig.launcher.cli.terminated


def test_a_launch_failure_cleans_up_what_started(tmp_path) -> None:
    """하나라도 못 띄우면 이미 뜬 것을 내리고 실패를 쓴다."""
    rig = make_rig(tmp_path, fail_on="websockify")
    rig.request("r1")

    rig.sup.tick()

    status = rig.status()
    assert status.state is State.FAILED
    assert "websockify" in (status.detail or "")
    assert status.password is None
    assert rig.launcher.named("Xvfb").terminated
    assert rig.launcher.named("x11vnc").terminated
    assert not rig.browser_profile.exists()
    assert not (rig.work_dir / supervisor.PASSWORD_FILE).exists()


def test_a_display_that_never_comes_up_fails_the_session(tmp_path) -> None:
    """가상 화면이 뜨지 않으면 나머지를 띄우지 않는다."""
    rig = make_rig(tmp_path, ready=False)
    rig.request("r1")

    rig.sup.tick()

    status = rig.status()
    assert status.state is State.FAILED
    assert "가상 화면" in (status.detail or "")
    assert [p.argv[0] for p in rig.launcher.processes] == ["Xvfb"]
    assert rig.launcher.named("Xvfb").terminated


def test_a_stubborn_process_is_killed(rig: Rig) -> None:
    """SIGTERM 을 무시하는 자식은 SIGKILL 로 끝낸다."""
    rig.request("r1")
    rig.sup.tick()
    rig.launcher.cli.ignore_term = True

    rig.request("r2", Action.CANCEL)
    rig.sup.tick()

    assert rig.launcher.cli.killed
    assert rig.status().state is State.CANCELLED


def test_recover_marks_a_leftover_session_failed(rig: Rig) -> None:
    """재시작 전의 세션이 남아 있으면 정리하고 실패로 쓴다."""
    login_protocol.write_status(
        rig.login_dir,
        login_protocol.Status(
            state=State.RUNNING, request_id="r0", password="old"
        ),
    )

    rig.sup.recover()

    status = rig.status()
    assert status.state is State.FAILED
    assert status.request_id == "r0"
    assert status.detail == supervisor.DETAIL_RESTARTED
    assert status.password is None
    assert not rig.browser_profile.exists()


def test_recover_leaves_a_finished_result_alone(rig: Rig) -> None:
    """이미 끝난 결과는 그대로 둔다."""
    finished = login_protocol.Status(state=State.SUCCEEDED, request_id="r0")
    login_protocol.write_status(rig.login_dir, finished)

    rig.sup.recover()

    assert rig.status() == finished


def test_recover_does_not_replay_the_last_request(rig: Rig) -> None:
    """재시작 전의 시작 요청이 사람 없이 다시 실행되지 않는다."""
    rig.request("r0")

    rig.sup.recover()
    rig.sup.tick()

    assert rig.launcher.processes == []


def test_every_tick_refreshes_the_heartbeat(rig: Rig) -> None:
    """앱이 사이드카의 생사를 알 수 있게 매 틱 heartbeat 를 갱신한다."""
    heartbeat = rig.login_dir / login_protocol.HEARTBEAT_FILE

    rig.sup.tick()
    os.utime(heartbeat, (0, 0))
    rig.sup.tick()

    assert heartbeat.stat().st_mtime > 0


def test_a_broken_request_is_ignored(rig: Rig) -> None:
    """반쯤 쓰였거나 깨진 요청은 넘어간다."""
    rig.login_dir.mkdir(parents=True, exist_ok=True)
    (rig.login_dir / login_protocol.REQUEST_FILE).write_text(
        "{", encoding="utf-8"
    )

    rig.sup.tick()

    assert rig.launcher.processes == []


def test_shutdown_ends_a_live_session(rig: Rig) -> None:
    """컨테이너가 내려가면 세션을 정리하고 실패로 남긴다."""
    rig.request("r1")
    rig.sup.tick()

    rig.sup.shutdown()

    status = rig.status()
    assert status.state is State.FAILED
    assert status.detail == supervisor.DETAIL_STOPPED
    assert not rig.browser_profile.exists()
```

`tests/login_browser/test_isolation.py`:

```python
"""사이드카 모듈이 앱 의존성을 끌어오지 않는지."""

import subprocess
import sys


def test_sidecar_modules_import_nothing_from_the_app() -> None:
    """사이드카 이미지에는 streamlit·notebooklm_st 의 나머지가 없다."""
    code = (
        "import sys\n"
        "import notebooklm_st.login_browser.supervisor\n"
        "roots = {'notebooklm_st', 'streamlit', 'notebooklm'}\n"
        "names = sorted(m for m in sys.modules"
        " if m.split('.')[0] in roots)\n"
        "print(','.join(names))\n"
    )

    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert set(out.split(",")) == {
        "notebooklm_st",
        "notebooklm_st.core",
        "notebooklm_st.core.login_protocol",
        "notebooklm_st.login_browser",
        "notebooklm_st.login_browser.supervisor",
    }
```

- [ ] **Step 3: 실패를 확인한다**

Run: `uv run pytest tests/login_browser -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'notebooklm_st.login_browser'`

- [ ] **Step 4: 구현한다**

`src/notebooklm_st/login_browser/__init__.py`:

```python
"""원격 로그인 사이드카. 앱은 이 패키지를 import 하지 않는다."""
```

`src/notebooklm_st/login_browser/supervisor.py`:

```python
"""원격 로그인 사이드카의 감시 루프.

앱이 공유 볼륨에 쓴 요청을 보고, 가상 화면 위에 ``notebooklm login``
을 띄워 사람이 앱 화면 안에서 구글 로그인을 하게 한다. 결과 쿠키는
CLI 가 앱과 같은 프로필에 직접 저장한다.

표준 라이브러리와 ``core.login_protocol`` 만 쓴다. 이 이미지에는 앱의
의존성(streamlit 등)이 없다.

설계: docs/superpowers/specs/2026-09-26-remote-login-design.md §6
"""

import dataclasses
import datetime as dt
import logging
import secrets
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from notebooklm_st.core import login_protocol
from notebooklm_st.core.login_protocol import Action, State

logger = logging.getLogger(__name__)

SESSION_SECONDS = 300
"""사람이 로그인을 마칠 때까지 기다리는 시간(초). 사이드카가 소유한다."""

CLI_BROWSER_TIMEOUT = 900
"""CLI 에 주는 시한(초). 사이드카의 시한이 항상 먼저 오게 더 길게 둔다.

둘이 겹치면 누가 끝냈는지 모호해져 timeout 과 failed 가 섞인다.
"""

TICK_SECONDS = 1.0
STOP_GRACE = 5.0
"""SIGTERM 뒤 SIGKILL 까지 기다리는 시간(초)."""

DISPLAY = ":99"
VNC_PORT = 5900
WEB_PORT = 6080
NOVNC_WEB = "/usr/share/novnc"
PASSWORD_FILE = "vncpass"
LOG_FILE = "login.log"
DETAIL_MAX = 200

DETAIL_RESTARTED = "로그인 브라우저가 재시작되었습니다"
DETAIL_STOPPED = "로그인 브라우저가 멈췄습니다"
DETAIL_RELAY = "화면 중계가 멈췄습니다"


class ProcessLike(Protocol):
    """자식 프로세스에서 이 모듈이 쓰는 부분."""

    def poll(self) -> int | None:
        """끝났으면 종료 코드, 아니면 ``None``."""

    def terminate(self) -> None:
        """SIGTERM 을 보낸다."""

    def kill(self) -> None:
        """SIGKILL 을 보낸다."""

    def wait(self, timeout: float) -> int:
        """끝날 때까지 기다린다. 넘기면 ``TimeoutExpired``."""


Launcher = Callable[[Sequence[str], Mapping[str, str], Path | None], ProcessLike]
"""``(argv, env, log_path)`` 로 자식을 띄운다.

``log_path`` 가 있으면 stdout·stderr 를 그 파일로 보낸다.
"""


class _StartError(Exception):
    """세션을 이루는 프로세스 하나를 띄우지 못했다. 인자는 단계 이름."""


@dataclasses.dataclass
class _Session:
    """떠 있는 로그인 세션."""

    request_id: str
    processes: list[ProcessLike]
    deadline: dt.datetime

    @property
    def cli(self) -> ProcessLike:
        """마지막에 띄운 ``notebooklm login``."""
        return self.processes[-1]

    @property
    def helpers(self) -> list[ProcessLike]:
        """가상 화면과 화면 중계."""
        return self.processes[:-1]


def _password() -> str:
    """세션 비밀번호. VNC 인증은 8자까지만 쓰므로 8자로 만든다."""
    return secrets.token_urlsafe(6)


class Supervisor:
    """요청을 받아 로그인 세션을 하나씩 띄우고 거둔다."""

    def __init__(
        self,
        *,
        login_dir: Path,
        profile_dir: Path,
        work_dir: Path,
        launch: Launcher,
        clock: Callable[[], dt.datetime],
        wait_ready: Callable[[], bool],
        env: Mapping[str, str],
        make_password: Callable[[], str] = _password,
    ) -> None:
        """주변을 받아 둔다.

        Args:
            login_dir: 신호 파일 디렉터리.
            profile_dir: CLI 가 저장하는 notebooklm 프로필 디렉터리.
            work_dir: 비밀번호 파일과 CLI 로그를 두는 임시 디렉터리.
            launch: 자식을 띄우는 함수.
            clock: 지금 시각(UTC, aware).
            wait_ready: 가상 화면이 뜰 때까지 기다린다. 못 뜨면 ``False``.
            env: 자식에게 줄 환경변수의 바탕.
            make_password: 세션 비밀번호를 만든다.
        """
        self._login_dir = login_dir
        self._browser_profile = profile_dir / "browser_profile"
        self._work_dir = work_dir
        self._launch = launch
        self._clock = clock
        self._wait_ready = wait_ready
        self._env = dict(env)
        self._make_password = make_password
        self._session: _Session | None = None
        self._last_request_id: str | None = None

    def recover(self) -> None:
        """기동 직후 한 번 부른다.

        재시작 전의 세션이 남아 있으면 정리하고 실패로 쓴다. 그때 있던
        요청은 처리한 것으로 기록해, 사람 없이 다시 실행되지 않게 한다.
        """
        status = self._read_status()
        if status.state in login_protocol.ACTIVE_STATES:
            self._cleanup_files()
            self._write_status(State.FAILED, status.request_id, DETAIL_RESTARTED)
        request = self._read_request()
        if request is not None:
            self._last_request_id = request.id

    def tick(self) -> None:
        """감시 한 주기. 1초마다 부른다."""
        self._beat()
        request = self._read_request()
        if request is not None and request.id != self._last_request_id:
            self._last_request_id = request.id
            self._handle(request)
        if self._session is not None:
            self._check(self._session)

    def shutdown(self) -> None:
        """컨테이너가 내려갈 때 떠 있는 세션을 정리한다."""
        if self._session is not None:
            self._finish(State.FAILED, DETAIL_STOPPED)

    def _handle(self, request: login_protocol.Request) -> None:
        """새 요청 하나를 처리한다."""
        if request.action is Action.START and self._session is None:
            self._start(request.id)
        elif request.action is Action.CANCEL and self._session is not None:
            self._finish(State.CANCELLED, None)

    def _start(self, request_id: str) -> None:
        """가상 화면·화면 중계·CLI 를 차례로 띄운다."""
        self._write_status(State.STARTING, request_id, None)
        password = self._make_password()
        self._work_dir.mkdir(parents=True, exist_ok=True)
        password_file = self._work_dir / PASSWORD_FILE
        login_protocol.write_atomic(password_file, password + "\n")
        processes: list[ProcessLike] = []
        try:
            processes.append(
                self._spawn(
                    "Xvfb",
                    ["Xvfb", DISPLAY, "-screen", "0", "1280x800x24"]
                    + ["-nolisten", "tcp"],
                    None,
                )
            )
            if not self._wait_ready():
                raise _StartError("가상 화면")
            processes.append(
                self._spawn(
                    "x11vnc",
                    ["x11vnc", "-display", DISPLAY, "-localhost"]
                    + ["-rfbport", str(VNC_PORT)]
                    + ["-passwdfile", f"rm:{password_file}"]
                    + ["-forever", "-shared", "-quiet"],
                    None,
                )
            )
            processes.append(
                self._spawn(
                    "websockify",
                    ["websockify", "--web", NOVNC_WEB, str(WEB_PORT)]
                    + [f"localhost:{VNC_PORT}"],
                    None,
                )
            )
            processes.append(
                self._spawn(
                    "notebooklm login",
                    [sys.executable, "-m", "notebooklm", "login", "--fresh"]
                    + ["--browser-timeout", str(CLI_BROWSER_TIMEOUT)],
                    self._work_dir / LOG_FILE,
                )
            )
        except _StartError as error:
            for process in reversed(processes):
                _stop(process)
            self._cleanup_files()
            self._write_status(
                State.FAILED,
                request_id,
                f"로그인 브라우저를 띄우지 못했습니다({error})",
            )
            return
        deadline = self._clock() + dt.timedelta(seconds=SESSION_SECONDS)
        self._session = _Session(request_id, processes, deadline)
        self._write_status(
            State.RUNNING,
            request_id,
            None,
            password=password,
            deadline=deadline,
        )
        logger.info("로그인 세션을 열었습니다: %s", request_id)

    def _spawn(
        self, stage: str, argv: list[str], log_path: Path | None
    ) -> ProcessLike:
        """자식 하나를 띄운다. 못 띄우면 단계 이름으로 알린다."""
        env = {**self._env, "DISPLAY": DISPLAY}
        try:
            return self._launch(argv, env, log_path)
        except OSError as error:
            logger.warning("%s 를 띄우지 못했습니다: %s", stage, error)
            raise _StartError(stage) from error

    def _check(self, session: _Session) -> None:
        """떠 있는 세션이 끝났는지 본다."""
        code = session.cli.poll()
        if code is not None:
            if code == 0:
                self._finish(State.SUCCEEDED, None)
            else:
                detail = self._last_log_line() or f"종료 코드 {code}"
                self._finish(State.FAILED, detail)
            return
        if any(helper.poll() is not None for helper in session.helpers):
            self._finish(State.FAILED, DETAIL_RELAY)
            return
        if self._clock() >= session.deadline:
            self._finish(State.TIMEOUT, None)

    def _finish(self, state: State, detail: str | None) -> None:
        """세션을 내리고 흔적을 지운 뒤 결과를 쓴다."""
        session = self._session
        if session is None:
            return
        self._session = None
        for process in reversed(session.processes):
            _stop(process)
        self._cleanup_files()
        self._write_status(state, session.request_id, detail)
        logger.info("로그인 세션을 닫았습니다: %s %s", session.request_id, state)

    def _cleanup_files(self) -> None:
        """비밀번호 파일·CLI 로그·크로미움 프로필을 지운다.

        크로미움 프로필은 계정 동등 자격증명이다. 공유 볼륨에 남기지
        않는다.
        """
        (self._work_dir / PASSWORD_FILE).unlink(missing_ok=True)
        (self._work_dir / LOG_FILE).unlink(missing_ok=True)
        shutil.rmtree(self._browser_profile, ignore_errors=True)
        if self._browser_profile.exists():
            logger.error("브라우저 프로필을 지우지 못했습니다")

    def _last_log_line(self) -> str | None:
        """CLI 로그의 비어 있지 않은 마지막 줄."""
        try:
            text = (self._work_dir / LOG_FILE).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            return None
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines[-1][:DETAIL_MAX] if lines else None

    def _beat(self) -> None:
        """heartbeat 의 수정 시각을 갱신한다."""
        self._login_dir.mkdir(parents=True, exist_ok=True)
        (self._login_dir / login_protocol.HEARTBEAT_FILE).touch()

    def _read_request(self) -> login_protocol.Request | None:
        """요청을 읽는다. 깨졌으면 넘어간다."""
        try:
            return login_protocol.read_request(self._login_dir)
        except (OSError, login_protocol.ProtocolError) as error:
            logger.warning("요청 파일을 읽지 못했습니다: %s", error)
            return None

    def _read_status(self) -> login_protocol.Status:
        """자기가 쓴 상태를 읽는다. 깨졌으면 idle 로 본다."""
        try:
            return login_protocol.read_status(self._login_dir)
        except (OSError, login_protocol.ProtocolError) as error:
            logger.warning("상태 파일을 읽지 못했습니다: %s", error)
            return login_protocol.IDLE

    def _write_status(
        self,
        state: State,
        request_id: str | None,
        detail: str | None,
        *,
        password: str | None = None,
        deadline: dt.datetime | None = None,
    ) -> None:
        """상태를 쓴다. 비밀번호와 마감은 running 일 때만 넘긴다."""
        login_protocol.write_status(
            self._login_dir,
            login_protocol.Status(
                state=state,
                request_id=request_id,
                password=password,
                deadline=(
                    None
                    if deadline is None
                    else deadline.isoformat(timespec="seconds")
                ),
                detail=detail,
                updated_at=self._clock().isoformat(timespec="seconds"),
            ),
        )


def _stop(process: ProcessLike) -> None:
    """SIGTERM 으로 끝내 보고, 안 끝나면 SIGKILL 한다."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(STOP_GRACE)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(STOP_GRACE)
        except subprocess.TimeoutExpired:
            logger.error("자식 프로세스가 끝나지 않습니다")
```

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/login_browser -v`
Expected: PASS

- [ ] **Step 6: 검증 4단을 돌리고 커밋한다**

```bash
git add pyproject.toml src/notebooklm_st/login_browser tests/login_browser
git commit   # ✨ feat(login-browser): 로그인 세션 감시 루프 추가
```

---

### Task 5: 사이드카를 실제로 띄우기 — 실행기·진입점·compose·CI

**Files:**
- Modify: `src/notebooklm_st/login_browser/supervisor.py` (실제 실행기, `main()`)
- Modify: `deploy/login-browser/Dockerfile` (소스 복사, `CMD`)
- Modify: `docker-compose.yml` (`login-browser` 서비스, 앱 환경변수)
- Modify: `Dockerfile` (`NOTEBOOKLM_ST_LOGIN_DIR`)
- Modify: `.github/workflows/build.yml` (사이드카 빌드·단언)
- Test: `tests/login_browser/test_supervisor.py` (진입점 조립 테스트 추가)

**Interfaces:**
- Consumes: Task 4 의 `Supervisor`, `ProcessLike`, 상수
- Produces: `python -m notebooklm_st.login_browser.supervisor`, compose 서비스 `login-browser`(컨테이너명 `notebooklm-st-login-browser`), 앱 환경변수 `NOTEBOOKLM_ST_LOGIN_VIEWER_URL`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/login_browser/test_supervisor.py` 끝에 더한다.

```python
def test_build_wires_the_container_paths(monkeypatch) -> None:
    """진입점은 이미지의 환경변수에서 경로를 잡는다."""
    monkeypatch.setenv(login_protocol.DIR_ENV_VAR, "/data/login")
    monkeypatch.setenv("NOTEBOOKLM_HOME", "/data/notebooklm")

    built = supervisor.build()

    assert built._login_dir == Path("/data/login")
    assert built._browser_profile == Path(
        "/data/notebooklm/profiles/default/browser_profile"
    )
    assert built._env["NO_COLOR"] == "1"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/login_browser/test_supervisor.py::test_build_wires_the_container_paths -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'build'`

- [ ] **Step 3: 실제 실행기와 진입점을 더한다**

`supervisor.py` 의 import 에 `os`, `signal`, `time`, `types` 를 더하고, 파일 끝에 붙인다.

```python
X_SOCKET = Path("/tmp/.X11-unix/X99")
READY_TIMEOUT = 5.0
WORK_DIR = Path("/tmp/login-browser")


class _GroupProcess:
    """자식과 그 자손을 한 프로세스 그룹으로 다룬다.

    크로미움은 CLI 의 자손이다. CLI 에만 신호를 보내면 크로미움이
    남는다.
    """

    def __init__(self, popen: subprocess.Popen[bytes]) -> None:
        self._popen = popen

    def poll(self) -> int | None:
        return self._popen.poll()

    def wait(self, timeout: float) -> int:
        return self._popen.wait(timeout)

    def terminate(self) -> None:
        if sys.platform == "win32":
            self._popen.terminate()
        else:
            try:
                os.killpg(self._popen.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def kill(self) -> None:
        if sys.platform == "win32":
            self._popen.kill()
        else:
            try:
                os.killpg(self._popen.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _launch(
    argv: Sequence[str], env: Mapping[str, str], log_path: Path | None
) -> ProcessLike:
    """자식을 새 세션(프로세스 그룹)으로 띄운다."""
    if log_path is None:
        popen = subprocess.Popen(
            list(argv),
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    else:
        with log_path.open("wb") as log:
            popen = subprocess.Popen(
                list(argv),
                env=dict(env),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    return _GroupProcess(popen)


def _wait_for_display() -> bool:
    """Xvfb 의 소켓이 생길 때까지 기다린다."""
    deadline = time.monotonic() + READY_TIMEOUT
    while time.monotonic() < deadline:
        if X_SOCKET.exists():
            return True
        time.sleep(0.1)
    return False


def _utc_now() -> dt.datetime:
    """지금 시각(UTC)."""
    return dt.datetime.now(dt.UTC)


def build() -> Supervisor:
    """이미지의 환경변수로 감시 루프를 조립한다."""
    home = Path(os.environ["NOTEBOOKLM_HOME"])
    return Supervisor(
        login_dir=Path(os.environ[login_protocol.DIR_ENV_VAR]),
        profile_dir=home / "profiles" / "default",
        work_dir=WORK_DIR,
        launch=_launch,
        clock=_utc_now,
        wait_ready=_wait_for_display,
        # rich 의 색 코드가 CLI 로그 마지막 줄(화면에 보이는 사유)에
        # 섞이지 않게 한다.
        env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"},
    )


def _exit_on_signal(signum: int, frame: types.FrameType | None) -> None:
    """docker stop 의 SIGTERM 을 정상 종료로 바꾼다."""
    raise SystemExit(0)


def main() -> None:
    """감시 루프를 돈다. 컨테이너의 진입점이다."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    supervisor = build()
    signal.signal(signal.SIGTERM, _exit_on_signal)
    supervisor.recover()
    logger.info("원격 로그인 요청을 기다립니다")
    try:
        while True:
            try:
                supervisor.tick()
            except Exception:
                # 한 주기가 실패해도 루프는 산다. 죽으면 앱이 "꺼져
                # 있음" 만 보여 주고 사람은 원인을 모른다.
                logger.exception("감시 주기가 실패했습니다")
            time.sleep(TICK_SECONDS)
    finally:
        supervisor.shutdown()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/login_browser -v`
Expected: PASS. `mypy` 가 `os.killpg`·`signal.SIGKILL` 을 윈도우에서 잡지 않는지는 Step 9 의 검증 4단에서 본다(`sys.platform` 분기가 막는다).

- [ ] **Step 5: 사이드카 이미지에 감시 루프를 싣는다**

`deploy/login-browser/Dockerfile` 의 `USER app` 앞에 넣는다.

```dockerfile
# 앱 패키지 중 감시 루프와 신호 계약만 싣는다. 두 __init__.py 는
# docstring 뿐이라 다른 모듈을 끌어오지 않는다.
COPY src/notebooklm_st/__init__.py /app/src/notebooklm_st/__init__.py
COPY src/notebooklm_st/core/__init__.py /app/src/notebooklm_st/core/__init__.py
COPY src/notebooklm_st/core/login_protocol.py /app/src/notebooklm_st/core/login_protocol.py
COPY src/notebooklm_st/login_browser/ /app/src/notebooklm_st/login_browser/
ENV PYTHONPATH=/app/src
```

`EXPOSE 6080` 뒤에 넣는다.

```dockerfile
CMD ["python", "-m", "notebooklm_st.login_browser.supervisor"]
```

- [ ] **Step 6: 앱 이미지에 신호 디렉터리를 굽는다**

`Dockerfile` 의 앱 환경변수 블록에 한 줄 더한다.

```dockerfile
ENV HOME=/data \
    NOTEBOOKLM_HOME=/data/notebooklm \
    NOTEBOOKLM_ST_DB=/data/questions.db \
    NOTEBOOKLM_ST_LOGIN_DIR=/data/login \
    TZ=Asia/Seoul \
```

(나머지 줄은 그대로)

- [ ] **Step 7: compose 에 사이드카를 더한다**

`docker-compose.yml` 의 `app.environment` 끝에 더한다.

```yaml
      # 선택. 원격 구글 로그인 화면(login-browser)의 주소. 사용자
      # 브라우저가 닿는 홈서버 주소여야 한다(예: http://192.168.0.10:9005).
      # 비우면 인증 페이지에 원격 로그인 영역이 나오지 않는다.
      NOTEBOOKLM_ST_LOGIN_VIEWER_URL: "${NOTEBOOKLM_ST_LOGIN_VIEWER_URL:-}"
```

`services:` 아래 `app` 다음에 더한다.

```yaml
  # 원격 구글 로그인 사이드카. 평소에는 감시 루프만 돌고, 인증
  # 페이지에서 로그인을 시작하면 크로미움과 화면 중계를 띄운다.
  # 설계: docs/superpowers/specs/2026-09-26-remote-login-design.md
  login-browser:
    build:
      context: .
      dockerfile: deploy/login-browser/Dockerfile
    image: notebooklm-st-login-browser:local
    container_name: notebooklm-st-login-browser
    user: "${PUID:-1000}:${PGID:-1000}"
    ports:
      # 호스트 9005 → noVNC 6080. 홈 LAN 에만 연다. 로그인 세션 중에만
      # 무언가가 이 포트를 듣는다. 인터넷에 포워딩하지 않는다.
      - "9005:6080"
    volumes:
      # 앱과 같은 볼륨. 로그인 결과가 앱의 프로필에 바로 떨어진다.
      - ./data:/data
    restart: unless-stopped
    read_only: true
    tmpfs: ["/tmp"]
    # 크로미움은 공유 메모리를 많이 쓴다. 기본 64MB 면 탭이 죽는다.
    shm_size: "1gb"
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

Run: `docker compose config --quiet`
Expected: 오류 없음 (Docker 가 없으면 건너뛰고 보고에 적는다)

- [ ] **Step 8: CI 에 사이드카 게이트를 더한다**

`.github/workflows/build.yml` 에서 `- name: 기동과 헬스체크` **바로 앞**에 넣는다.

```yaml
      # ── 사이드카 게이트 ───────────────────────────────────────────────────
      # 사이드카는 게시하지 않는다. compose 가 홈서버에서 로컬로 굽는다.
      # 여기서는 굽히는지, 감시 루프가 서는지, 앱과 notebooklm-py 버전이
      # 같은지만 본다. 아래 기동 단계의 compose up 이 이 이미지를 쓴다.
      - name: 사이드카 이미지 빌드
        run: docker compose build login-browser

      - name: 사이드카가 감시 루프를 임포트하는지
        run: |
          docker compose run --rm --no-deps -T login-browser python -c \
            "import notebooklm_st.login_browser.supervisor"

      - name: 사이드카에 앱 의존성이 없는지 — import 가 실패해야 정상
        run: |
          set +e
          out=$(docker compose run --rm --no-deps -T login-browser python -c "import streamlit" 2>&1)
          rc=$?
          set -e
          if [ "$rc" -ne 1 ] || ! echo "$out" | grep -q "No module named 'streamlit'"; then
            echo "예상 밖 결과 (종료코드 $rc)" >&2
            echo "$out" >&2
            exit 1
          fi

      - name: 사이드카의 notebooklm-py 가 앱과 같은 버전인지
        run: |
          probe='import importlib.metadata as m; print(m.version("notebooklm-py"))'
          app=$(docker compose run --rm --no-deps -T app python -c "$probe" | tr -d '\r')
          side=$(docker compose run --rm --no-deps -T login-browser python -c "$probe" | tr -d '\r')
          echo "app=$app login-browser=$side"
          test -n "$app" && test "$app" = "$side"
```

- [ ] **Step 9: 검증 4단을 돌리고 커밋한다**

```bash
git add src/notebooklm_st/login_browser/supervisor.py tests/login_browser/test_supervisor.py deploy/login-browser/Dockerfile docker-compose.yml Dockerfile .github/workflows/build.yml
git commit   # ✨ feat(login-browser): 사이드카를 compose 로 띄우기
```

---

### Task 6: 「인증」 페이지와 가벼운 배너

배너에 있던 다시 확인·업로더를 새 페이지로 옮긴다. 원격 로그인 영역은 Task 7 에서 더한다.

**Files:**
- Modify: `src/notebooklm_st/core/errors.py` (`LOGIN_HINT`, `probe_failed_text()`)
- Create: `src/notebooklm_st/pages/auth.py`
- Modify: `src/notebooklm_st/components/auth_gate.py` (전체 재작성)
- Modify: `src/notebooklm_st/app.py`
- Test: `tests/core/test_errors.py`, `tests/pages/test_auth.py`(신규), `tests/test_components.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `session.get_auth_gate()`, `auth.AuthGate`(`ok`·`tried`·`probe_error`·`ensure()`·`recheck()`), `auth.import_credentials(payload) -> ImportResult`
- Produces:
  - `errors.probe_failed_text(error: Exception) -> str`
  - `pages.auth.TITLE = "인증"`, `pages.auth.URL_PATH = "auth"`, `pages.auth.as_page() -> StreamlitPage`, `pages.auth.render() -> None`
  - 위젯 키 `auth_page_recheck`, `auth_page_upload`, `auth_page_import`

- [ ] **Step 1: 문구 테스트를 먼저 바꾼다**

`tests/core/test_errors.py` 끝에 더한다.

```python
def test_login_hint_points_at_the_auth_page() -> None:
    """만료 안내는 언제든 닿는 인증 페이지로 보낸다. 재시작은 필요 없다."""
    assert "「인증」 페이지" in errors.LOGIN_HINT
    assert "재시작" not in errors.LOGIN_HINT


def test_probe_failed_text_shows_only_the_exception_type() -> None:
    """확인 불가 문구는 예외 타입만 보여 준다. 메시지에 구글 URL 이 있다."""
    text = errors.probe_failed_text(
        RuntimeError("https://accounts.google.com/secret")
    )

    assert "RuntimeError" in text
    assert "accounts.google.com" not in text
    assert "확인하지 못했습니다" in text
```

Run: `uv run pytest tests/core/test_errors.py -v`
Expected: 새 테스트 2개 FAIL

- [ ] **Step 2: `core/errors.py` 를 고친다**

`LOGIN_HINT` 와 그 독스트링을 바꾼다.

```python
LOGIN_HINT = (
    "인증이 만료되었습니다. 「인증」 페이지에서 구글 로그인을 다시"
    " 하세요. 원격 로그인을 쓸 수 없으면 데스크톱에서"
    " `uv run notebooklm login` 으로 자격증명을 만들어 같은 페이지에서"
    " 올립니다. 절차: docs/how-to/2026-09-16-auth-reseed.md"
)
"""만료 안내 문구의 정본.

화면(``components/auth_gate.py``)과 실행 실패 메시지
(``services/runner.py``)가 같은 문구를 쓴다. 인증 페이지는 인증 상태와
상관없이 언제나 열리므로, 실행 도중 만료된 경우에도 이 안내만으로
되살릴 수 있다. 두 곳에 따로 두면 한쪽만 고쳐져 어긋난다.
"""
```

`to_message()` 정의 앞에 더한다.

```python
def probe_failed_text(error: Exception) -> str:
    """인증 확인 **자체**가 실패했을 때의 안내 문구.

    예외 메시지는 담지 않는다. ``_LoginRedirectError`` 처럼 매핑을
    빠져나온 예외는 메시지 안에 구글 리다이렉트 URL 을 담고 있을 수
    있다. 타입 이름만 보여 주고 나머지는 로그(``AuthGate._verify`` 의
    ``logger.exception``)에 맡긴다. 배너와 인증 페이지가 함께 쓴다.

    Args:
        error: 확인이 던진 예외.

    Returns:
        화면 문구.
    """
    return (
        "인증 상태를 확인하지 못했습니다"
        f"({type(error).__name__}). 자세한 사유는 앱 로그에 남습니다."
    )
```

Run: `uv run pytest tests/core/test_errors.py -v`
Expected: PASS

- [ ] **Step 3: 페이지 테스트를 쓴다**

`tests/pages/test_auth.py` (배너에 있던 반입 테스트 셋을 페이지 키로 옮긴 것 포함):

```python
"""인증 페이지 테스트."""

from streamlit.testing import v1

from notebooklm_st import session
from notebooklm_st.services import auth


def _script():
    """AppTest 진입점 — 인증 페이지를 그린다."""
    from notebooklm_st.pages import auth as auth_page

    auth_page.render()


def test_page_says_so_when_authenticated(stub_auth_gate) -> None:
    """인증이 살아 있으면 그렇다고 알린다."""
    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert any("인증되어 있습니다" in box.value for box in app.success)


def test_page_reports_an_expiry(monkeypatch) -> None:
    """만료되면 경고로 알린다."""
    gate = auth.AuthGate(probe=lambda: False)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert any("만료" in box.value for box in app.warning)


def test_page_separates_a_failed_probe(monkeypatch) -> None:
    """확인 자체가 실패하면 타입 이름만 담아 알린다."""

    def probe() -> bool:
        """매핑되지 않은 예외를 던진다."""
        raise RuntimeError("https://accounts.google.com/secret")

    gate = auth.AuthGate(probe=probe)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert len(app.error) == 1
    assert "RuntimeError" in app.error[0].value
    assert "accounts.google.com" not in app.error[0].value


def test_recheck_probes_again(monkeypatch) -> None:
    """다시 확인은 판정을 새로 돌린다."""
    calls = []

    def probe() -> bool:
        """호출을 세고 계속 만료로 답한다."""
        calls.append(1)
        return False

    gate = auth.AuthGate(probe=probe)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    app = v1.AppTest.from_function(_script)
    app.run()
    app.button(key="auth_page_recheck").click().run()

    assert not app.exception
    assert len(calls) == 2


def test_the_page_imports_an_uploaded_credential(monkeypatch) -> None:
    """올린 자격증명을 반입하고 곧바로 다시 확인한다."""
    seen: list[bytes] = []
    results = iter([False, True])

    def fake_import(payload: bytes) -> auth.ImportResult:
        """반입 호출을 기록하고 성공으로 답한다."""
        seen.append(payload)
        return auth.ImportResult(ok=True, detail="반입했습니다")

    gate = auth.AuthGate(probe=lambda: next(results, True))
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)
    monkeypatch.setattr(auth, "import_credentials", fake_import)

    app = v1.AppTest.from_function(_script)
    app.run()
    app.file_uploader(key="auth_page_upload").set_value(
        ("storage_state.json", b'{"cookies": []}', "application/json")
    )
    app.run()
    app.button(key="auth_page_import").click().run()

    assert not app.exception
    assert seen == [b'{"cookies": []}']
    assert gate.ok is True


def test_an_import_that_stays_expired_is_not_a_success(monkeypatch) -> None:
    """반입은 성공해도 다시 확인이 실패하면 성공 취급하지 않는다.

    ``st.rerun()`` 은 ``NoReturn`` 이라 타입 체커가 이 분기 순서를
    지켜 주지 않는다. 분기가 뒤집히면 이 테스트만 잡아낸다.
    """

    def fake_import(payload: bytes) -> auth.ImportResult:
        """성공으로 답한다."""
        return auth.ImportResult(ok=True, detail="반입했습니다")

    gate = auth.AuthGate(probe=lambda: False)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)
    monkeypatch.setattr(auth, "import_credentials", fake_import)

    app = v1.AppTest.from_function(_script)
    app.run()
    app.file_uploader(key="auth_page_upload").set_value(
        ("storage_state.json", b"{}", "application/json")
    )
    app.run()
    app.button(key="auth_page_import").click().run()

    assert not app.exception
    assert any("살아나지 않았습니다" in box.value for box in app.error)
    assert gate.ok is False


def test_a_failed_import_is_reported(monkeypatch) -> None:
    """반입이 실패하면 사유를 보여 주고 판정을 바꾸지 않는다."""

    def fake_import(payload: bytes) -> auth.ImportResult:
        """실패로 답한다."""
        return auth.ImportResult(ok=False, detail="쿠키가 모자랍니다")

    gate = auth.AuthGate(probe=lambda: False)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)
    monkeypatch.setattr(auth, "import_credentials", fake_import)

    app = v1.AppTest.from_function(_script)
    app.run()
    app.file_uploader(key="auth_page_upload").set_value(
        ("storage_state.json", b"{}", "application/json")
    )
    app.run()
    app.button(key="auth_page_import").click().run()

    assert not app.exception
    assert any("쿠키가 모자랍니다" in box.value for box in app.error)
    assert gate.ok is False
```

- [ ] **Step 4: 배너 테스트를 바꾼다**

`tests/test_components.py` 에서 다음 다섯 개를 **지운다** — 페이지로 옮겨 갔다.

- `test_auth_gate_offers_recheck_when_expired`
- `test_auth_gate_rechecks_when_the_button_is_pressed`
- `test_auth_gate_imports_an_uploaded_credential`
- `test_auth_gate_reports_a_successful_import_that_stays_expired`
- `test_auth_gate_reports_a_failed_import`

`test_auth_gate_hides_the_uploader_when_authenticated` 는 이름과 독스트링을 바꾸고 몸통은 그대로 둔다.

```python
def test_auth_gate_never_draws_the_uploader(stub_auth_gate) -> None:
    """배너는 업로더를 그리지 않는다. 업로더는 인증 페이지에 있다."""
```

그리고 더한다.

```python
def test_auth_gate_links_to_the_auth_page_when_expired(monkeypatch) -> None:
    """만료되면 안내와 인증 페이지 링크만 그린다."""
    gate = auth.AuthGate(probe=lambda: False)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    def script():
        """AppTest 진입점 — 인증 게이트를 그린다."""
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert [box.value for box in app.error] == [errors.LOGIN_HINT]
    assert [link.proto.page for link in app.get("page_link")] == ["auth"]
    assert len(app.button) == 0
    assert len(app.file_uploader) == 0


def test_auth_gate_draws_no_link_when_authenticated(stub_auth_gate) -> None:
    """인증이 살아 있으면 링크도 그리지 않는다."""

    def script():
        """AppTest 진입점 — 인증 게이트를 그린다."""
        from notebooklm_st.components import auth_gate

        auth_gate.render()

    app = v1.AppTest.from_function(script).run()

    assert not app.exception
    assert len(app.get("page_link")) == 0
```

`tests/test_app.py` 의 독스트링을 고친다.

```python
    """여덟 페이지가 등록된 진입점이 예외 없이 부팅된다."""
```

Run: `uv run pytest tests/pages/test_auth.py tests/test_components.py -v`
Expected: 새 테스트 FAIL — `pages.auth` 없음, 배너에 링크 없음

- [ ] **Step 5: 인증 페이지를 만든다**

`src/notebooklm_st/pages/auth.py`:

```python
"""인증 페이지.

인증 상태와 상관없이 언제나 열 수 있다. 배너는 앱이 뜰 때 한 번만
판정하므로, 떠 있는 도중 세션이 죽으면 사람이 여기로 와서 되살린다.

업로더는 앱이 외부에 노출되지 않는다는 전제 위에 있다(R1 스펙
§13.1). 노출로 바꾸면 이 기능을 빼고 볼륨 직접 복사로 되돌린다.
"""

import streamlit as st
from streamlit.navigation.page import StreamlitPage

from notebooklm_st import session
from notebooklm_st.core import errors
from notebooklm_st.services import auth

TITLE = "인증"
URL_PATH = "auth"

_RECHECK_KEY = "auth_page_recheck"
_UPLOAD_KEY = "auth_page_upload"
_IMPORT_KEY = "auth_page_import"


def as_page() -> StreamlitPage:
    """내비게이션과 배너 링크가 함께 쓰는 페이지 객체.

    두 곳이 같은 ``url_path`` 를 봐야 링크가 이 페이지로 간다.
    """
    return st.Page(render, title=TITLE, url_path=URL_PATH)


def render() -> None:
    """인증 상태와 되살리는 수단을 그린다."""
    st.title("인증")
    gate = session.get_auth_gate()
    if not gate.tried:
        with st.spinner("인증 상태 확인 중"):
            gate.ensure()
    if st.button("다시 확인", key=_RECHECK_KEY):
        with st.spinner("다시 확인 중"):
            if gate.recheck():
                # 배너는 페이지보다 먼저 그려졌다. 새 판정으로 다시
                # 그리게 한다.
                st.rerun()
    # 버튼 처리(위) 뒤에 그려야 다시 확인이 바꾼 판정을 반영한다.
    _render_state(gate)
    _render_upload(gate)


def _render_state(gate: auth.AuthGate) -> None:
    """지금 판정을 한 줄로 그린다."""
    if gate.ok:
        st.success("인증되어 있습니다.")
    elif gate.probe_error is not None:
        st.error(errors.probe_failed_text(gate.probe_error))
    else:
        st.warning("인증이 만료되었습니다. 아래에서 다시 로그인하세요.")


def _render_upload(gate: auth.AuthGate) -> None:
    """자격증명 파일을 올려 반입하는 접은 영역을 그린다.

    반입에 성공하면 곧바로 다시 확인까지 하고 화면을 새로 그린다.
    업로드된 내용은 화면에도 로그에도 남기지 않는다. 계정 동등
    자격증명이기 때문이다.

    Args:
        gate: 반입 뒤 다시 확인할 게이트.
    """
    with st.expander("자격증명 파일 올리기 (대체 경로)"):
        st.caption(
            "데스크톱에서 `uv run notebooklm login` 으로 만든"
            " storage_state.json 을 올립니다. 절차는"
            " docs/how-to/2026-09-16-auth-reseed.md 에 있습니다."
        )
        uploaded = st.file_uploader(
            "storage_state.json", type="json", key=_UPLOAD_KEY
        )
        if not st.button("반입", key=_IMPORT_KEY, disabled=uploaded is None):
            return
        # 버튼이 ``disabled=uploaded is None`` 이라 눌렸으면 런타임엔
        # 항상 uploaded 가 있다. mypy 의 None 좁히기를 위해 남겨 둔다.
        if uploaded is None:
            return
        with st.spinner("반입 중"):
            result = auth.import_credentials(uploaded.getvalue())
        if not result.ok:
            st.error(f"반입하지 못했습니다: {result.detail}")
            return
        # ``st.rerun()`` 은 ``NoReturn`` 이다. 실패를 먼저 걸러 반환하고
        # 성공은 마지막에 둔다.
        if not gate.recheck():
            st.error("반입했지만 인증이 살아나지 않았습니다.")
            return
        st.rerun()
```

- [ ] **Step 6: 배너를 다시 쓴다**

`src/notebooklm_st/components/auth_gate.py` 전체:

```python
"""인증 상태를 확인하고 만료를 알리는 배너.

앱이 뜰 때 한 번 돌고, 인증이 만료된 동안에만 화면에 남는다. 되살리는
수단(구글 로그인·다시 확인·자격증명 올리기)은 모두 「인증」 페이지에
있다. 여기서는 안내와 그 페이지로 가는 링크만 그린다.
"""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import errors
from notebooklm_st.pages import auth as auth_page


def render() -> bool:
    """인증을 확인하고 만료면 안내를 그린다.

    앱이 뜬 뒤 첫 실행에서만 확인한다. 확인 자체가 라이브러리의 토큰
    재추출과 쿠키 회전을 태우므로, 대개는 사용자가 아무것도 하지
    않아도 여기서 끝난다.

    만료와 "확인 자체가 실패" 를 구분해 그린다. 앞은 사람이 다시
    로그인해 풀 수 있고, 뒤는 원인이 다르다.

    Returns:
        인증을 쓸 수 있으면 ``True``.
    """
    gate = session.get_auth_gate()
    if not gate.tried:
        with st.spinner("인증 상태 확인 중"):
            gate.ensure()
    if gate.ok:
        return True
    if gate.probe_error is None:
        st.error(errors.LOGIN_HINT)
    else:
        st.error(errors.probe_failed_text(gate.probe_error))
    st.page_link(auth_page.as_page(), label="「인증」 페이지로 가기")
    return False
```

- [ ] **Step 7: 페이지를 등록한다**

`src/notebooklm_st/app.py` 의 import 에 `auth` 를 더한다(알파벳 순서).

```python
from notebooklm_st.pages import (
    ask,
    auth,
    channels,
    dashboard,
    digest,
    history,
    maintenance,
    question_admin,
)
```

`st.navigation([...])` 목록의 마지막(정리 다음)에 더한다.

```python
            st.Page(maintenance.render, title="정리", url_path="maintenance"),
            auth.as_page(),
```

- [ ] **Step 8: 통과를 확인한다**

Run: `uv run pytest tests/pages/test_auth.py tests/test_components.py tests/test_app.py tests/core/test_errors.py -v`
Expected: PASS

- [ ] **Step 9: 검증 4단을 돌리고 커밋한다**

```bash
git add src/notebooklm_st/core/errors.py src/notebooklm_st/pages/auth.py src/notebooklm_st/components/auth_gate.py src/notebooklm_st/app.py tests/core/test_errors.py tests/pages/test_auth.py tests/test_components.py tests/test_app.py
git commit   # ✨ feat(auth): 언제나 열리는 인증 페이지로 되살리기 모으기
```

---

### Task 7: 인증 페이지의 원격 구글 로그인 영역

**Files:**
- Create: `src/notebooklm_st/pages/_remote_login.py`
- Modify: `src/notebooklm_st/pages/auth.py` (`render()` 에서 호출)
- Test: `tests/pages/test_remote_login.py`

**Interfaces:**
- Consumes: Task 3 의 `login_session` 전체, Task 2 의 `login_protocol.State`·`ACTIVE_STATES`·`write_status`·`read_request`, `session.get_registry()`·`get_digest_registry()`, `AuthGate.recheck()`
- Produces: `pages._remote_login.render(gate: auth.AuthGate) -> None`, 위젯 키 `remote_login_start`, `remote_login_cancel`, 세션 키 `remote_login_watching`, `remote_login_outcome`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_remote_login.py`:

```python
"""인증 페이지의 원격 구글 로그인 영역 테스트."""

import datetime as dt
import os
from pathlib import Path

import pytest
from streamlit.testing import v1

from notebooklm_st import session
from notebooklm_st.core import login_protocol
from notebooklm_st.core.login_protocol import Action, State
from notebooklm_st.services import auth, login_session

VIEWER = "http://192.168.0.10:9005"


def _script():
    """AppTest 진입점 — 원격 로그인 영역만 그린다."""
    from notebooklm_st import session
    from notebooklm_st.pages import _remote_login

    _remote_login.render(session.get_auth_gate())


@pytest.fixture
def login_dir(monkeypatch, tmp_path) -> Path:
    """원격 로그인을 켜고, 살아 있는 사이드카를 흉내 낸다."""
    directory = tmp_path / "login"
    directory.mkdir()
    monkeypatch.setenv(login_session.VIEWER_URL_ENV_VAR, VIEWER)
    monkeypatch.setenv(login_protocol.DIR_ENV_VAR, str(directory))
    (directory / login_protocol.HEARTBEAT_FILE).touch()
    return directory


def _write(directory: Path, **fields) -> None:
    """사이드카 대신 상태를 쓴다."""
    login_protocol.write_status(directory, login_protocol.Status(**fields))


def test_nothing_is_drawn_without_a_viewer_url() -> None:
    """설정이 없으면 영역 자체를 그리지 않는다."""
    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert len(app.subheader) == 0
    assert len(app.button) == 0


def test_a_silent_sidecar_is_reported(login_dir) -> None:
    """heartbeat 가 멈췄으면 꺼져 있다고 알리고 시작 버튼을 숨긴다."""
    os.utime(login_dir / login_protocol.HEARTBEAT_FILE, (0, 0))

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert any("꺼져 있습니다" in box.value for box in app.warning)
    assert len(app.button) == 0


def test_idle_offers_the_start_button(login_dir) -> None:
    """대기 중이면 시작 버튼을 켠다."""
    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert app.button(key="remote_login_start").disabled is False


def test_a_busy_app_disables_the_start_button(login_dir, monkeypatch) -> None:
    """질의·정리본이 돌고 있으면 시작을 막는다."""
    monkeypatch.setattr(login_session, "busy", lambda *args: True)

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert app.button(key="remote_login_start").disabled is True
    assert any("끝난 뒤" in text.value for text in app.caption)


def test_start_writes_a_request_and_waits(login_dir) -> None:
    """시작을 누르면 요청을 쓰고 준비 중으로 바뀐다."""
    app = v1.AppTest.from_function(_script)
    app.run()
    app.button(key="remote_login_start").click().run()

    request = login_protocol.read_request(login_dir)
    assert not app.exception
    assert request is not None
    assert request.action is Action.START
    assert any("준비하는 중" in box.value for box in app.info)


def test_a_running_session_shows_the_viewer(login_dir) -> None:
    """세션이 뜨면 비밀번호를 해시에 담은 iframe 과 취소 버튼을 그린다."""
    deadline = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=2)
    _write(
        login_dir,
        state=State.RUNNING,
        request_id="r1",
        password="pw123456",
        deadline=deadline.isoformat(timespec="seconds"),
    )

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    frames = [frame.proto.src for frame in app.get("iframe")]
    assert frames == [
        f"{VIEWER}/vnc.html#autoconnect=1&resize=scale&password=pw123456"
    ]
    assert app.button(key="remote_login_cancel") is not None
    shown = " ".join(
        element.value for element in [*app.caption, *app.info, *app.markdown]
    )
    assert "pw123456" not in shown


def test_cancel_writes_a_cancel_request(login_dir) -> None:
    """취소를 누르면 취소 요청을 쓴다."""
    _write(login_dir, state=State.RUNNING, request_id="r1", password="pw")

    app = v1.AppTest.from_function(_script)
    app.run()
    app.button(key="remote_login_cancel").click().run()

    request = login_protocol.read_request(login_dir)
    assert not app.exception
    assert request is not None
    assert request.action is Action.CANCEL


def test_a_watched_success_rechecks_once(login_dir, monkeypatch) -> None:
    """지켜보던 로그인이 성공하면 한 번만 다시 확인하고 알린다."""
    calls = []

    def probe() -> bool:
        """호출을 세고 살아 있다고 답한다."""
        calls.append(1)
        return True

    gate = auth.AuthGate(probe=probe)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)
    app = v1.AppTest.from_function(_script)
    app.run()
    app.button(key="remote_login_start").click().run()
    request = login_protocol.read_request(login_dir)
    assert request is not None

    _write(login_dir, state=State.SUCCEEDED, request_id=request.id)
    app.run()

    assert not app.exception
    assert len(calls) == 1
    assert any("인증되었습니다" in box.value for box in app.success)

    app.run()

    assert len(calls) == 1


def test_a_watched_failure_shows_the_reason(login_dir) -> None:
    """지켜보던 로그인이 실패하면 사유를 보여 준다."""
    app = v1.AppTest.from_function(_script)
    app.run()
    app.button(key="remote_login_start").click().run()
    request = login_protocol.read_request(login_dir)
    assert request is not None

    _write(
        login_dir,
        state=State.FAILED,
        request_id=request.id,
        detail="Error: boom",
    )
    app.run()

    assert not app.exception
    assert any("Error: boom" in box.value for box in app.error)


def test_an_unwatched_success_is_only_reported(login_dir, monkeypatch) -> None:
    """지켜보지 않던 결과는 한 줄로만 보여 주고 다시 확인하지 않는다."""
    calls = []

    def probe() -> bool:
        """호출을 세고 살아 있다고 답한다."""
        calls.append(1)
        return True

    gate = auth.AuthGate(probe=probe)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)
    _write(login_dir, state=State.SUCCEEDED, request_id="old")

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert calls == []
    assert len(app.success) == 0
    assert any("마지막 로그인: 성공" in text.value for text in app.caption)


def test_a_leftover_cancel_does_not_look_pending(login_dir) -> None:
    """세션 없이 남은 취소 요청은 준비 중으로 보이지 않는다."""
    login_session.request_cancel(login_dir)

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert len(app.info) == 0
    assert app.button(key="remote_login_start") is not None


def test_a_broken_status_file_still_offers_the_start_button(login_dir) -> None:
    """상태 파일이 깨져도 트레이스백 없이 시작 버튼을 그린다."""
    (login_dir / login_protocol.STATUS_FILE).write_text("{", encoding="utf-8")

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert app.button(key="remote_login_start") is not None
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/pages/test_remote_login.py -v`
Expected: FAIL — `ImportError: cannot import name '_remote_login'`

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/pages/_remote_login.py`:

```python
"""인증 페이지의 원격 구글 로그인 영역.

홈서버의 사이드카(login-browser)가 띄운 크로미움 화면을 iframe 으로
보여 준다. 사람은 앱 화면 안에서 구글 로그인을 하고, CLI 가 결과를
앱의 프로필에 직접 저장한다. 사이드카와는 공유 볼륨의 파일로만
이야기한다(``core.login_protocol``).

설계: docs/superpowers/specs/2026-09-26-remote-login-design.md §7
"""

import datetime as dt
import time
from pathlib import Path

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import login_protocol
from notebooklm_st.core.login_protocol import State
from notebooklm_st.services import auth, login_session

_START_KEY = "remote_login_start"
_CANCEL_KEY = "remote_login_cancel"
_WATCHING_KEY = "remote_login_watching"
"""이 탭이 결과를 기다리는 요청의 ``id``.

지켜보던 요청의 결과만 처리한다. 며칠 전의 ``succeeded`` 를 새 탭이
"인증되었습니다" 로 오해하지 않게 한다.
"""
_OUTCOME_KEY = "remote_login_outcome"

IFRAME_HEIGHT = 700

_RESULT_TEXT = {
    State.SUCCEEDED: "성공",
    State.FAILED: "실패",
    State.TIMEOUT: "시간 초과",
    State.CANCELLED: "취소됨",
}


def render(gate: auth.AuthGate) -> None:
    """원격 로그인 영역을 그린다. 설정이 없으면 아무것도 그리지 않는다.

    사이드카를 기다리는 동안에만 1초마다 영역을 다시 그린다. 평소에는
    폴링하지 않는다.

    Args:
        gate: 로그인이 끝나면 다시 확인할 게이트.
    """
    base = login_session.viewer_url()
    directory = login_session.login_dir()
    if base is None or directory is None:
        return
    st.subheader("구글 로그인")
    polling = _waiting(directory)
    st.fragment(run_every=1 if polling else None)(_area)(gate, base, directory)


def _waiting(directory: Path) -> bool:
    """사이드카의 응답을 기다리는 중인지."""
    if not login_session.sidecar_alive(directory, time.time()):
        return False
    status = login_session.read_status(directory)
    if status.state in login_protocol.ACTIVE_STATES:
        return True
    return _unaccepted(login_session.pending_request(directory), status)


def _unaccepted(
    request: login_protocol.Request | None, status: login_protocol.Status
) -> bool:
    """사이드카가 아직 받지 않은 시작 요청이 있는지.

    취소는 넣지 않는다. 사이드카는 세션이 없으면 취소를 무시하므로,
    넣으면 영원히 "준비 중" 으로 보인다.
    """
    return (
        request is not None
        and request.action is login_protocol.Action.START
        and request.id != status.request_id
    )


def _area(gate: auth.AuthGate, base: str, directory: Path) -> None:
    """상태에 맞는 화면을 그린다. 기다리는 동안 1초마다 다시 돈다."""
    _show_outcome()
    if not login_session.sidecar_alive(directory, time.time()):
        st.warning(
            "로그인 브라우저가 꺼져 있습니다. 홈서버에서"
            " notebooklm-st-login-browser 컨테이너가 떠 있는지 확인하세요."
        )
        return
    status = login_session.read_status(directory)
    if status.state is State.RUNNING and status.password:
        _render_running(base, directory, status)
        return
    if status.state is State.STARTING or _unaccepted(
        login_session.pending_request(directory), status
    ):
        st.info("로그인 브라우저를 준비하는 중입니다.")
        return
    if _finish_watched(gate, status):
        # 배너와 페이지 상태 줄까지 새 판정으로 다시 그리고, 폴링을
        # 멈춘다.
        st.rerun(scope="app")
    _render_idle(directory, status)


def _render_running(
    base: str, directory: Path, status: login_protocol.Status
) -> None:
    """떠 있는 세션의 화면을 iframe 으로 그린다."""
    if status.request_id is not None:
        st.session_state.setdefault(_WATCHING_KEY, status.request_id)
    # RUNNING 이면 비밀번호가 있다(호출 조건). mypy 좁히기용.
    link = login_session.viewer_link(base, status.password or "")
    remaining = login_session.remaining_seconds(
        status, dt.datetime.now(dt.UTC)
    )
    if remaining is not None:
        st.caption(
            f"남은 시간 {remaining // 60}:{remaining % 60:02d}"
            " · 로그인을 마치면 이 창은 자동으로 닫힙니다."
        )
    st.iframe(link, height=IFRAME_HEIGHT)
    left, right = st.columns(2)
    left.link_button("새 탭에서 열기", link)
    if right.button("취소", key=_CANCEL_KEY):
        login_session.request_cancel(directory)
        st.rerun(scope="app")


def _render_idle(directory: Path, status: login_protocol.Status) -> None:
    """마지막 결과 한 줄과 시작 버튼을 그린다."""
    if status.state in _RESULT_TEXT:
        line = f"마지막 로그인: {_RESULT_TEXT[status.state]}"
        if status.detail:
            line += f" — {status.detail}"
        st.caption(line)
    busy = login_session.busy(
        session.get_registry(), session.get_digest_registry()
    )
    if busy:
        st.caption(
            "진행 중인 질의·정리본이 끝난 뒤 로그인하세요. 실행 중인"
            " 작업이 옛 자격증명을 되써 새 로그인을 덮을 수 있습니다."
        )
    if st.button("구글 로그인 시작", key=_START_KEY, disabled=busy):
        st.session_state[_WATCHING_KEY] = login_session.request_start(
            directory
        )
        st.rerun(scope="app")


def _finish_watched(gate: auth.AuthGate, status: login_protocol.Status) -> bool:
    """이 탭이 지켜보던 요청이 끝났으면 결과를 처리한다.

    Returns:
        처리했으면 ``True``. 호출자가 앱 전체를 다시 그린다.
    """
    if status.state not in _RESULT_TEXT:
        # 아직 결과가 아니다(running 인데 비밀번호가 없는 순간 등).
        return False
    watching = st.session_state.get(_WATCHING_KEY)
    if watching is None or status.request_id != watching:
        return False
    del st.session_state[_WATCHING_KEY]
    if status.state is State.SUCCEEDED:
        if gate.recheck():
            outcome = ("success", "인증되었습니다.")
        else:
            outcome = (
                "error",
                "로그인은 끝났지만 인증이 살아나지 않았습니다."
                " 다시 시작하세요.",
            )
    else:
        reason = _RESULT_TEXT.get(status.state, str(status.state))
        if status.detail:
            reason += f" — {status.detail}"
        outcome = ("error", f"로그인하지 못했습니다: {reason}")
    st.session_state[_OUTCOME_KEY] = outcome
    return True


def _show_outcome() -> None:
    """직전에 처리한 결과를 한 번 보여 준다."""
    outcome = st.session_state.pop(_OUTCOME_KEY, None)
    if outcome is None:
        return
    level, text = outcome
    if level == "success":
        st.success(text)
    else:
        st.error(text)
```

`src/notebooklm_st/pages/auth.py` 에서 import 와 호출을 더한다.

```python
from notebooklm_st.pages import _remote_login
```

`render()` 의 `_render_state(gate)` 와 `_render_upload(gate)` 사이:

```python
    _render_state(gate)
    _remote_login.render(gate)
    _render_upload(gate)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/pages/test_remote_login.py tests/pages/test_auth.py -v`
Expected: PASS

`test_a_watched_success_rechecks_once` 가 성공 문구를 찾지 못하면, `st.rerun(scope="app")` 뒤 AppTest 가 재실행을 마쳤는지 먼저 본다. 결과 문구는 `_OUTCOME_KEY` 를 거쳐 **다음 실행**에서 그려진다. 테스트를 고치지 말고 흐름을 바로잡는다.

- [ ] **Step 5: 검증 4단을 돌리고 커밋한다**

```bash
git add src/notebooklm_st/pages/_remote_login.py src/notebooklm_st/pages/auth.py tests/pages/test_remote_login.py
git commit   # ✨ feat(auth): 인증 페이지 안에서 구글 로그인하기
```

---

### Task 8: 문서

**Files:**
- Rewrite: `docs/how-to/2026-09-16-auth-reseed.md`
- Modify: `docs/how-to/2026-09-16-homeserver-deploy.md`
- Modify: `README.md`

- [ ] **Step 1: 재시드 문서를 통째로 다시 쓴다**

`docs/how-to/2026-09-16-auth-reseed.md` 전체:

````markdown
# 인증이 만료됐을 때 되살리기

앱이 "인증이 만료되었습니다" 라고 알리거나, 질의가 인증 오류로
실패하면 이 절차를 따른다. 앱을 재시작할 필요는 없다 — 「인증」
페이지는 언제든 열린다.

## 왜 사람이 해야 하나

NotebookLM 에는 공개 API 가 없다. `notebooklm-py` 는 브라우저가 쓰는
내부 엔드포인트를 **구글 웹 세션 쿠키**로 호출한다. 그 쿠키는 실제
브라우저에서 실제로 로그인해야 나온다.

앱은 요청이 나갈 때마다 토큰을 재추출하고 쿠키를 회전시켜 세션을
살려 둔다. 브라우저 없이 되는 일이다. 그런데 그 갱신으로도 못 살릴
만큼 세션이 죽으면 **사람이 다시 로그인해야 한다.**

## 정본 — 앱 화면에서 구글 로그인

홈서버에 `login-browser` 사이드카가 떠 있고 앱에
`NOTEBOOKLM_ST_LOGIN_VIEWER_URL` 이 설정돼 있으면 쓸 수 있다
([홈서버에 배포하기](2026-09-16-homeserver-deploy.md) 2절). PC·휴대폰
어느 기기든 된다.

1. 앱에서 **인증** 페이지를 연다. 만료 배너의 링크로도 간다.
2. **구글 로그인 시작** 을 누른다.
3. 몇 초 뒤 페이지 안에 구글 로그인 화면이 뜬다. 평소처럼 로그인한다.
   - 화면이 좁으면 **새 탭에서 열기** 를 쓴다.
   - 휴대폰에서는 화면을 한 번 누른 뒤, 왼쪽에 접힌 noVNC 막대의
     키보드 버튼으로 화면 키보드를 띄운다.
4. 로그인을 마치면 창이 닫히고, 앱이 다시 확인까지 한 뒤
   "인증되었습니다" 를 보여 준다.

알아 둘 것:

- **5분** 안에 끝내지 않으면 시간 초과로 닫힌다. 다시 시작하면 된다.
- 질의·정리본이 진행 중이면 시작 버튼이 막힌다. 실행 중인 작업이 옛
  자격증명을 되써 새 로그인을 덮을 수 있어서다. **실행 현황**이 빈 뒤
  한다.
- "로그인 브라우저가 꺼져 있습니다" 가 뜨면 홈서버에서
  `docker compose ps` 로 `notebooklm-st-login-browser` 를 확인한다.
- 로그인에 쓴 크로미움 프로필은 세션이 끝나면 지워진다. 매번 새
  세션으로 로그인하므로 평소 쓰는 브라우저의 세션과 섞이지 않는다.

## 대체 1 — 데스크톱에서 로그인해 올리기

사이드카를 쓸 수 없거나 구글이 사이드카 로그인을 막을 때 쓴다. `uv`
가 깔린 데스크톱이 필요하다.

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

(`NOTEBOOKLM_HOME` 환경 변수를 설정했다면 그 경로 아래
`profiles/default/` 다. 옛 `notebooklm-py` 에서 업그레이드한
데스크톱은 프로필 도입 이전 레이아웃이 남아 있을 수 있다 — 그때는
한 단계 위인 `~/.notebooklm/storage_state.json` 을 대신 찾는다.)

### 2. 앱에서 올리기

1. 앱에서 **인증** 페이지를 연다.
2. **자격증명 파일 올리기 (대체 경로)** 를 편다.
3. 위 `storage_state.json` 을 고른다.
4. **반입** 을 누른다.

반입에 성공하면 앱이 곧바로 다시 확인까지 하고 화면을 새로 그린다.

## 대체 2 — 볼륨에 직접 복사

업로드도 안 될 때만 쓴다.

**컨테이너 안이 아니라 호스트의 볼륨 디렉터리에 놓는다.** 바인드
마운트가 호스트 경로를 컨테이너 경로에 비춰 주므로, 호스트 쪽에
파일을 놓기만 하면 된다. `docker cp` 로 컨테이너 안에 직접 넣으면
컨테이너를 다시 만들 때 사라진다.

```
호스트 (홈서버)                        컨테이너 내부
./data/notebooklm/              ←──→  /data/notebooklm/
      profiles/default/                     profiles/default/
```

호스트 쪽 `./data` 는 `docker-compose.yml` 을 둔 디렉터리 기준이다.
컨테이너 쪽 경로는 이미지의 `NOTEBOOKLM_HOME` 이 정한다.

두 가지를 지킨다.

- **프로필 디렉터리 전체를 복사한다.** `storage_state.json` 옆에 락과
  회전 상태가 형제 파일로 생긴다. 파일 하나만 옮기면 어긋난다.
- **볼륨은 쓰기 가능해야 한다.** 앱이 회전된 쿠키를 그 파일에 다시
  쓴다. `:ro` 로 마운트하면 갱신이 저장되지 않아 재시작마다 옛
  쿠키로 돌아가고 결국 죽는다.

복사한 뒤 **인증** 페이지에서 **다시 확인** 을 누른다.

## 자격증명 취급 수칙

`storage_state.json` 은 **계정 동등 자격증명**이다. 이 파일을 가진
사람은 해당 구글 계정의 웹 세션을 쓸 수 있다.

- 원격 로그인 화면과 업로드 폼은 **앱이 인터넷에 노출되지 않는다는
  전제** 위에 있다(스펙 `2026-09-26-remote-login-design.md` §10). 이
  전제가 깨져 앱을 외부에 노출하기로 바꾸면 사이드카를 끄고 업로드
  폼을 제거하며, 반입은 볼륨에 직접 복사하는 방식으로 되돌아간다.
- **앱과 로그인 화면은 평문 HTTP 다.** 로그인 화면에 치는 **구글
  비밀번호의 키 입력이 LAN 위를 암호화 없이 지나간다.** 같은 Wi-Fi 의
  다른 기기에는 보인다. **Tailscale 처럼 암호화된 경로로 접속하기를
  강하게 권장한다.** 올리는 자격증명 파일도 같은 구간을 지난다.
- 파일을 옮길 때는 scp·SSH 같은 **암호화된 경로**로 한다. 평문
  채널이나 공용 클라우드 드라이브에 올리지 않는다.
- 옮긴 뒤 **데스크톱에 남은 복사본을 지운다.** 원본
  (`~/.notebooklm/profiles/default/`)은 그대로 둬도 된다. 같은
  이유로 `notebooklm auth import-cookies` 가 반입 직전 프로필
  디렉터리에 남기는 `storage_state.json.bak`(직전 자격증명의
  백업)도 함께 지운다 — 반입에 성공해도 이 파일 안에 못 쓰게 된
  옛 자격증명이 그대로 남는다.
- 저장소에 커밋하지 않는다. `.gitignore` 에 `storage_state.json` 이
  이미 들어 있다.
- 유출이 의심되면 **구글 계정 → 보안 → 기기에서 로그아웃** 으로 즉시
  폐기한다.

## 주의 — 데스크톱 앱과 컨테이너 앱을 동시에 오래 띄우지 않는다

둘 다 같은 계정의 쿠키를 각자 회전시킨다. 서로의 갱신을 덮어써 양쪽이
함께 죽을 수 있다. 개발용으로 데스크톱에서 앱을 띄울 때는 짧게 쓴다.

앱 컨테이너 이미지에는 Playwright(`[browser]` extras)가 없다. 브라우저는
`login-browser` 사이드카에만 있다. 직접 확인하려면 다음이 **실패**해야
한다.

```bash
docker compose run --rm app python -c "import playwright"
```

이미지를 굽는 워크플로가 게시 전에 같은 것을 단언한다
(`.github/workflows/build.yml`).
````

- [ ] **Step 2: 배포 문서를 고친다**

`docs/how-to/2026-09-16-homeserver-deploy.md`:

(a) 첫 문단의 설계 근거에 한 줄 더한다.

```markdown
앱을 홈서버의 도커 컨테이너로 띄우는 절차다. 설계 근거는
`docs/superpowers/specs/2026-09-16-container-deploy-design.md` 와
`docs/superpowers/specs/2026-09-26-remote-login-design.md`(원격 로그인)
에 있다.
```

(b) 「준비물」의 두 번째 줄을 바꾼다.

```markdown
- (선택) 데스크톱에 이 저장소와 `uv` — 원격 로그인을 쓸 수 없을 때만
  자격증명을 만드는 데 쓴다
```

(c) 「1. 저장소와 데이터 디렉터리」의 `printf` 줄 다음에 한 줄 더하고, 설명 문단을 덧붙인다.

```bash
printf 'NOTEBOOKLM_ST_LOGIN_VIEWER_URL=http://%s:9005\n' "<홈서버IP>" >> .env
```

```markdown
`NOTEBOOKLM_ST_LOGIN_VIEWER_URL` 은 원격 로그인 화면의 주소다. **다른
기기의 브라우저가 닿는 주소**여야 한다(컨테이너 안의 주소가 아니다).
비워 두면 인증 페이지에 원격 로그인 영역이 나오지 않는다.
```

(d) 「2. 띄우기」의 마지막 문단을 바꾼다.

```markdown
컨테이너가 둘 뜬다.

| 컨테이너 | 주소 | 하는 일 |
|---|---|---|
| `notebooklm-st` | **http://<홈서버IP>:9004** | 앱. 컨테이너 안 8611 |
| `notebooklm-st-login-browser` | `http://<홈서버IP>:9005` | 원격 로그인 화면 중계. 로그인 세션 중에만 이 포트를 듣는다. 사람이 직접 열 일은 없다 — 앱의 인증 페이지가 끼워 보여 준다 |

사이드카 이미지는 크로미움을 담아 처음 빌드가 몇 분 걸린다.
```

(e) 「3. 자격증명 넣기」 전체를 바꾼다.

```markdown
## 3. 자격증명 넣기

1. 아무 기기(PC·휴대폰)의 브라우저로 앱을 연다.
2. **인증** 페이지에서 **구글 로그인 시작** 을 누른다.
3. 페이지 안에 뜬 구글 로그인 화면에서 로그인한다.
4. "인증되었습니다" 가 뜨면 끝이다.

원격 로그인을 쓸 수 없을 때의 대체 경로(데스크톱 로그인 → 업로드,
볼륨 직접 복사)와 자격증명 취급 수칙은
[인증이 만료됐을 때 되살리기](2026-09-16-auth-reseed.md) 에 있다.
```

(f) 「5. 검증」 표의 7번 줄을 바꾸고 두 줄을 더한다.

```markdown
| 7 | 인증 페이지에서 구글 로그인 | "인증되었습니다", 배너가 사라진다 |
| 7a | 로그인 뒤 `ls data/notebooklm/profiles/default/` | `browser_profile` 이 **없다** |
| 7b | `docker compose run --rm login-browser python -c "import streamlit"` | **실패해야 정상** |
```

(g) 「운영 규칙」의 첫 항목을 바꾼다.

```markdown
- **인터넷에 내놓지 않는다.** 원격 로그인 화면(9005)과 자격증명 업로드
  폼은 앱이 외부에 노출되지 않는다는 전제 위에 있다. 포트포워딩·리버스
  프록시·터널로 9004·9005 를 인터넷에 열려면 먼저 사이드카를 끄고
  업로드 폼을 제거해야 한다. 홈 LAN 안에서도 구간은 평문 HTTP 다 —
  로그인 화면에 치는 구글 비밀번호가 같은 Wi-Fi 의 다른 기기에 보인다.
  Tailscale 같은 암호화 경로로 접속하기를 권장한다. **방화벽으로
  막았다고 안심하지 않는다** — 도커는 iptables 에 직접 규칙을 넣어
  `ufw` 같은 호스트 방화벽을 우회한다. 라우터에서 9004·9005 를
  포워딩하지 않는 것이 유일한 방어선이다.
```

(h) 「인증이 만료되면」 절 전체를 바꾼다.

```markdown
## 인증이 만료되면

**인증** 페이지에서 구글 로그인을 다시 한다. 앱을 재시작할 필요는
없다. 절차는 3절과 같다.
```

- [ ] **Step 3: README 를 고친다**

`README.md`:

(a) 「홈서버 (Docker)」 절에서 `접속 주소는 **http://<홈서버IP>:9004** ...` 문단 다음에 더한다.

```markdown
원격 구글 로그인을 쓰려면 배포 디렉터리의 `.env` 에
`NOTEBOOKLM_ST_LOGIN_VIEWER_URL=http://<홈서버IP>:9005` 를 적습니다.
로그인 화면은 `login-browser` 사이드카가 9005 에서 중계하고, 앱의
**인증** 페이지가 그 화면을 끼워 보여 줍니다.
```

그 절의 경고 문구를 바꾼다.

```markdown
> **인터넷에 노출하지 마세요.** 원격 로그인 화면(9005)과 자격증명 업로드 폼은 앱이 외부에 노출되지 않는다는 전제 위에 있습니다. 홈 LAN 안에서도 평문 HTTP 이므로 Tailscale 같은 암호화 경로로 접속하기를 권장합니다.
```

(b) 「첫 실행 — 인증」 절의 본문 전체(제목 아래부터 다음 `###` 앞까지)를 바꾼다.

```markdown
**인증** 페이지에서 합니다. 인증 상태와 상관없이 언제든 열립니다.

- **홈서버** — **구글 로그인 시작** 을 누르면 페이지 안에 구글 로그인
  화면이 뜹니다. PC·휴대폰 어느 기기에서든 됩니다. 로그인을 마치면
  앱이 스스로 다시 확인합니다.
- **데스크톱 실행** 이나 원격 로그인을 쓸 수 없을 때 — 터미널에서
  `uv run notebooklm login` 으로 로그인한 뒤, 인증 페이지의
  **자격증명 파일 올리기** 로 `storage_state.json` 을 올립니다.
  데스크톱 실행은 같은 프로필을 바로 읽으므로 **다시 확인** 만 눌러도
  됩니다.

앱은 뜰 때 저장된 인증을 확인하고, 요청이 나갈 때마다 토큰과 쿠키를
자동으로 갱신합니다. 갱신으로도 못 살릴 만큼 세션이 죽으면 배너나
실행 실패 메시지가 인증 페이지로 안내합니다. 재시작은 필요 없습니다.
절차 전체는
[인증이 만료됐을 때 되살리기](docs/how-to/2026-09-16-auth-reseed.md)
에 있습니다.
```

(c) 「사용 순서」 목록 끝에 더한다.

```markdown
8. **인증** 화면에서 인증 상태를 봅니다. 만료되면 여기서 구글 로그인을 다시 합니다.
```

(d) 「프로젝트 구조」 블록을 바꾼다.

```
src/notebooklm_st/
├── app.py           # 진입점. st.navigation 으로 페이지 등록
├── session.py       # @st.cache_resource 로 공유하는 커넥션·레지스트리·인증 게이트
├── pages/           # 질의 · 채널 · 실행 현황 · 질문 관리 · 이력 · 정리본 · 정리 · 인증
├── components/      # 답변 카드, 인증 배너, 스키마 게이트, 진행 표시
├── services/        # 외부 I/O — NotebookLM API, SQLite, 인증, 원격 로그인 신호, 백그라운드 러너
├── core/            # 순수 로직 — URL 파싱, 답변 정제, 마크다운 변환, 오류 매핑, 값 객체, 원격 로그인 계약
└── login_browser/   # 원격 로그인 사이드카의 감시 루프. 앱은 import 하지 않는다
deploy/login-browser/  # 사이드카 이미지
tests/               # src 구조를 미러링
scripts/             # smoke_check.py
docs/                # 온보딩 문서
```

(e) 「테스트」 절의 mypy 줄을 바꾼다.

```markdown
- mypy 는 `core/`·`services/`·`login_browser/` 에 `disallow_untyped_defs` 를 적용합니다.
```

- [ ] **Step 4: 문서의 사실을 코드와 대조한다**

Run: `grep -n "재시작" README.md docs/how-to/2026-09-16-auth-reseed.md docs/how-to/2026-09-16-homeserver-deploy.md`
Expected: "재시작할 필요는 없다"·"재시작은 필요 없습니다" 류와, 배포 문서 「운영 규칙」의 "실행 중일 때 재시작하지 않는다" 만 남는다. 인증을 되살리려고 재시작하라는 문장이 없어야 한다.

Run: `grep -n "NOTEBOOKLM_ST_LOGIN_VIEWER_URL\|9005" docker-compose.yml README.md docs/how-to/2026-09-16-homeserver-deploy.md`
Expected: 세 파일 모두에 나온다.

- [ ] **Step 5: 커밋한다**

```bash
git add README.md docs/how-to/2026-09-16-auth-reseed.md docs/how-to/2026-09-16-homeserver-deploy.md
git commit   # 📝 docs(auth): 원격 로그인을 정본 재시드 절차로 적기
```

---

### Task 9: 홈서버 E2E (사람)

에이전트는 아래 절차를 사용자에게 전달하고 결과를 받는다. **push 는 사람이 한다.**

- [ ] **Step 1: 사용자에게 E2E 를 요청한다**

사용자가 `develop` 을 push 하고 홈서버에서:

```bash
git pull
docker compose up -d --build
docker compose ps    # 두 컨테이너 모두 Up, 앱은 healthy
```

| # | 확인 | 통과 기준 |
|---|---|---|
| 1 | PC 브라우저 → 인증 페이지 → 구글 로그인 시작 → 로그인 | "인증되었습니다" |
| 2 | 휴대폰(iOS) 으로 1 | 같음 |
| 3 | 휴대폰(Android) 으로 1 | 같음 |
| 4 | 시작 후 취소 | "마지막 로그인: 취소됨", iframe 사라짐 |
| 5 | 시작 후 5분 방치 | "시간 초과" |
| 6 | 세션 중 `docker restart notebooklm-st-login-browser` | 재시작 뒤 "실패 — 로그인 브라우저가 재시작되었습니다", 자동으로 다시 뜨지 않음 |
| 7 | 각 경우 뒤 `ls data/notebooklm/profiles/default/` | `browser_profile` 없음 |
| 8 | 질의 실행 중 인증 페이지 | 시작 버튼 비활성 |
| 9 | 로그인 뒤 질의 하나 실행 | 답변을 받는다 |

- [ ] **Step 2: 결과를 반영한다**

- 통과하지 못한 항목은 `superpowers:systematic-debugging` 으로 원인을 찾아 고친다(새 태스크로).
- 설계서 §13 의 남은 가정(3·4)에 결과가 나왔으면 §2 로 옮겨 그 절을 다시 쓰고 커밋한다.

```bash
git add docs/superpowers/specs/2026-09-26-remote-login-design.md
git commit   # 📝 docs(spec): 원격 로그인 E2E 결과 반영
```
