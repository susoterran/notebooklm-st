# 컨테이너 배포 (R2) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 앱을 홈서버의 도커 컨테이너에서 무인으로 띄우는 데 필요한
이미지·오케스트레이션·CI·문서를 만든다. 앱의 동작은 바꾸지 않는다.

**Architecture:** 멀티스테이지 Dockerfile 이 의존성만 든 가상환경을
굽고 런타임 단계에는 `uv` 를 넣지 않는다. 앱 환경변수의 정본은
이미지에 두고, `docker-compose.yml` 은 호스트마다 달라지는 것(포트
바인딩·볼륨·UID·재시작·로그)만 맡는다. 조용히 틀리는 검사(playwright
혼입, UTC 시간대)는 GitHub Actions 가 단언한다.

**Tech Stack:** Docker, Docker Compose v2, GitHub Actions, uv, Python
3.13, Streamlit, notebooklm-py 0.8.1

**Spec:** `docs/superpowers/specs/2026-09-16-container-deploy-design.md`

## Global Constraints

- **이 개발 머신에는 도커가 없다.** PATH 에도 기본 설치 경로에도 없다.
  따라서 Task 1~3 은 **로컬에서 `docker build`·`docker compose up` 을
  돌릴 수 없다.** 각 태스크는 파일 내용에 대한 **실행 가능한 grep 단언**
  으로 로컬 검증을 하고, 실제 빌드·기동 검증은 push 후의 CI 와
  홈서버가 맡는다(계획 끝의 「사람이 도는 검증」).
  **돌리지 않은 것을 돌렸다고 적지 않는다.** 도커 명령을 흉내 낸
  가짜 통과를 만들지 않는다.
- **브랜치는 `develop`.** `master` 에 직접 커밋하지 않는다.
- **`git push` 금지.** 커밋만 한다. push 와 PR 은 사람이 한다
  (`.claude/rules/branch-strategy.md`).
- **커밋 규약** (`.claude/rules/commit-strategy.md`): 헤더는
  `<emoji> <type>(<scope>): <subject>`, subject 는 **한국어·명령형·
  마침표 없음·≤50자**. 마지막 줄에
  `Assisted-by: <이 커밋을 수행하는 에이전트 자신의 모델 ID>` 를 붙인다.
  **이 계획서에 모델 ID 를 적지 않는다** — 적으면 다른 모델이 실행할 때
  틀린 값이 박힌다. `Co-Authored-By:` 는 붙이지 않는다.
- **검증 4단** — 모든 커밋 전에 순서대로 돌린다. 이 릴리스는 파이썬
  동작을 바꾸지 않으므로 **전부 그대로 통과해야 한다.** 하나라도
  깨지면 범위를 넘은 것이다.
  ```
  uv run ruff format .
  uv run ruff check --fix .
  uv run mypy src tests
  uv run pytest
  ```
- **`uv` 가 PATH 에 없을 수 있다.** 그럴 때는 전체 경로로 부른다:
  `C:\Users\susot\.local\bin\uv.exe run ...`
- **문서는 한국어.** 산문은 터미널 표시 폭 80칸에서 줄바꿈한다(한글은
  한 자가 2칸이므로 약 40자).
- **독스트링·주석은 72칸**에서 줄바꿈한다(코드는 80칸). ruff
  `line-length = 80`, Google 스타일 독스트링(`D` 규칙)이 켜져 있다.
- **줄끝은 신경 쓰지 않아도 된다.** 작업 복사본이 CRLF 로 보여도 git 이
  LF 로 저장하므로, 리눅스(CI·홈서버) 체크아웃에는 LF 로 내려간다.
- **`pyproject.toml`·`uv.lock` 을 건드리지 않는다.** 의존성은 이
  릴리스의 범위가 아니다.
- **스펙이 정본이다.** 파일 내용이 스펙과 어긋나면 스펙을 따르고,
  스펙이 틀렸다고 판단되면 고치지 말고 보고한다.

---

## File Structure

새로 만드는 파일은 각각 책임이 하나다.

| 파일 | 책임 |
|---|---|
| `Dockerfile` | 런타임 한 벌을 정의한다. 앱 환경변수의 정본 |
| `.dockerignore` | 빌드 컨텍스트에서 뺄 것을 정한다 |
| `docker-compose.yml` | 이미지를 **이 호스트**에 붙인다 — 포트·볼륨·UID·재시작·로그 |
| `.github/workflows/ci.yml` | 파이썬 검증과 이미지 검증 |
| `docs/how-to/2026-09-16-homeserver-deploy.md` | 사람이 홈서버에서 밟는 절차 |

고치는 파일.

| 파일 | 무엇을 |
|---|---|
| `docs/how-to/2026-09-16-auth-reseed.md` | 컨테이너 경로를 확정하고, 이미지 확인 방법을 도커 기준으로 바꾼다 |
| `docs/superpowers/specs/2026-09-16-headless-auth-design.md` | §10.1 의 빈 경로를 채운다 |
| `README.md` | 컨테이너 실행 절, 접속 주소 두 갈래, 요구사항 표 |
| `src/notebooklm_st/app.py` | 모듈 독스트링 한 문단 (동작 무변경) |

---

### Task 1: 이미지 정의

**Files:**
- Create: `.dockerignore`
- Create: `Dockerfile`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: 컨테이너가 **8611** 에서 listen 한다. 실행 사용자는
  **UID/GID 1000**(`app`). 앱이 쓰는 디렉터리는 **`/data`** 하나.
  이미지가 정의하는 환경변수 9개: `HOME`, `NOTEBOOKLM_HOME`,
  `NOTEBOOKLM_ST_DB`, `TZ`, `STREAMLIT_SERVER_PORT`,
  `STREAMLIT_SERVER_ADDRESS`, `STREAMLIT_SERVER_HEADLESS`,
  `STREAMLIT_BROWSER_GATHER_USAGE_STATS`,
  `STREAMLIT_SERVER_FILE_WATCHER_TYPE`. Task 2 는 이 값들을 **다시
  적지 않는다.**

- [ ] **Step 1: `.dockerignore` 를 만든다**

```
.git
.venv
.claude
.superpowers
.ua
.streamlit
.mypy_cache
.pytest_cache
.ruff_cache
__pycache__
*.py[cod]
*.db
*.db-journal
*.sqlite3
.env
.env.*
storage_state.json
data
docs
tests
scripts
run.ps1
run.bat
```

`.streamlit` 을 빼는 것이 중요하다. 데스크톱용 `config.toml` 이
`127.0.0.1` 을 고정하는데, 이미지에 들어가면 컨테이너가 밖에서 닿지
않는다. `Dockerfile` 이 `src/` 만 `COPY` 하므로 이중 안전장치다.

- [ ] **Step 2: `Dockerfile` 을 만든다**

```dockerfile
# 앱을 홈서버 컨테이너에서 돌리기 위한 이미지.
#
# 런타임 단계에는 uv 를 넣지 않는다. uv 가 있으면 `uv run` 이 dev
# 그룹을 조용히 다시 동기화해 playwright 가 되살아난다. 없으면 그
# 함정이 성립하지 않는다.

# ── builder ────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── runtime ────────────────────────────────────────────────
# 베이스는 빌더와 같은 계열이어야 한다. /app/.venv 가 빌더의
# 인터프리터 경로를 절대 경로로 참조한다.
FROM python:3.13-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 1000 app \
 && useradd -u 1000 -g 1000 -M -s /usr/sbin/nologin app
COPY --from=builder /app/.venv /app/.venv
COPY src/ /app/src/
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
# 앱 환경변수의 정본. compose 가 아니라 여기에 둔다 — 이미지가
# 단독으로도 옳게 서야 한다.
ENV HOME=/data \
    NOTEBOOKLM_HOME=/data/notebooklm \
    NOTEBOOKLM_ST_DB=/data/questions.db \
    TZ=Asia/Seoul \
    STREAMLIT_SERVER_PORT=8611 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none
WORKDIR /app
USER app
EXPOSE 8611
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8611/_stcore/health', timeout=4).read()"
CMD ["streamlit", "run", "/app/src/notebooklm_st/app.py"]
```

- [ ] **Step 3: 환경변수 9개가 다 있는지 단언한다**

Run:
```bash
for k in HOME NOTEBOOKLM_HOME NOTEBOOKLM_ST_DB TZ \
         STREAMLIT_SERVER_PORT STREAMLIT_SERVER_ADDRESS \
         STREAMLIT_SERVER_HEADLESS STREAMLIT_BROWSER_GATHER_USAGE_STATS \
         STREAMLIT_SERVER_FILE_WATCHER_TYPE; do
  grep -q "${k}=" Dockerfile || echo "빠짐: ${k}"
done; echo "단언 끝"
```
Expected: `단언 끝` 만 출력. "빠짐:" 이 한 줄이라도 나오면 Step 2 로
돌아간다.

- [ ] **Step 4: 나머지 불변식을 단언한다**

Run:
```bash
grep -q '^EXPOSE 8611$' Dockerfile && echo "포트 OK"
grep -q '^USER app$' Dockerfile && echo "비root OK"
grep -q 'no-install-project' Dockerfile && echo "미설치 OK"
grep -q -- '--frozen' Dockerfile && echo "frozen OK"
grep -c 'uv' Dockerfile
grep -q '^\.streamlit$' .dockerignore && echo "config 제외 OK"
```
Expected: `포트 OK` / `비root OK` / `미설치 OK` / `frozen OK` /
숫자 / `config 제외 OK`.
`grep -c 'uv'` 가 세는 줄은 **전부 builder 단계**여야 한다. 출력된
숫자만큼 `grep -n 'uv' Dockerfile` 로 눈으로 확인하고, runtime 단계
(`FROM python:3.13-slim-bookworm` 아래)에 `uv` 가 한 줄이라도 있으면
지운다.

- [ ] **Step 5: 검증 4단을 돌린다**

Run:
```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```
Expected: 전부 통과. 파이썬을 건드리지 않았으므로 R1 종료 시점과 같은
결과여야 한다.

- [ ] **Step 6: 커밋**

```bash
git add Dockerfile .dockerignore
git commit
```
메시지 예: `📦️ build(docker): 런타임 이미지 정의 추가`

---

### Task 2: 오케스트레이션

**Files:**
- Create: `docker-compose.yml`

**Interfaces:**
- Consumes: Task 1 의 이미지 — 컨테이너 포트 **8611**, 실행 사용자
  **1000:1000**, 쓰기 대상 **`/data`**, 환경변수 9개는 **이미 이미지에
  있다.**
- Produces: 서비스명 **`app`**, 컨테이너명 **`notebooklm-st`**, 호스트
  포트 **9004**, 호스트 볼륨 **`./data`**. Task 3 의 CI 가 이 이름들을
  그대로 쓴다.

- [ ] **Step 1: `docker-compose.yml` 을 만든다**

```yaml
# 이미지를 이 호스트에 붙인다. 앱 환경변수는 이미지에 있으므로
# 여기서 다시 적지 않는다 — 두 곳에 적으면 어긋난다.
services:
  app:
    build: .
    image: notebooklm-st:local
    container_name: notebooklm-st
    # 홈서버 사용자의 UID 가 1000 이 아니면 PUID/PGID 로 덮는다.
    user: "${PUID:-1000}:${PGID:-1000}"
    ports:
      # 호스트 9004 → 컨테이너 8611. 홈 LAN 에만 연다.
      # 인터넷에 포워딩하지 않는다(스펙 6절).
      - "9004:8611"
    volumes:
      # 쿠키 회전이 여기에 되쓰인다. :ro 를 걸면 재시작마다 옛
      # 쿠키로 돌아가고 결국 죽는다.
      - ./data:/data
    restart: unless-stopped
    read_only: true
    tmpfs: ["/tmp"]
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

- [ ] **Step 2: 불변식을 단언한다**

Run:
```bash
grep -q '"9004:8611"' docker-compose.yml && echo "포트 OK"
grep -q './data:/data$' docker-compose.yml && echo "볼륨 OK"
grep -q 'read_only: true' docker-compose.yml && echo "읽기전용 OK"
grep -q 'tmpfs' docker-compose.yml && echo "tmpfs OK"
grep -q 'restart: unless-stopped' docker-compose.yml && echo "재시작 OK"
grep -q 'container_name: notebooklm-st' docker-compose.yml && echo "이름 OK"
```
Expected: 여섯 줄 모두 출력.

- [ ] **Step 3: 이미지 환경변수가 중복되지 않았는지 단언한다**

Run:
```bash
grep -E 'NOTEBOOKLM_|STREAMLIT_|^\s+TZ:|^\s+HOME:' docker-compose.yml
```
Expected: **아무 출력 없음.** 한 줄이라도 나오면 값의 정본이 두
군데가 된 것이다. 지우고 Dockerfile 에만 남긴다.

- [ ] **Step 4: 볼륨에 `:ro` 가 없는지 단언한다**

Run:
```bash
grep -n ':ro' docker-compose.yml; echo "종료코드 $?"
```
Expected: 일치 없음(`종료코드 1`). `:ro` 가 붙으면 인증이 재시작마다
죽는다.

- [ ] **Step 5: 검증 4단을 돌린다**

Run:
```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```
Expected: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add docker-compose.yml
git commit
```
메시지 예: `📦️ build(docker): compose 로 볼륨과 포트 붙이기`

---

### Task 3: 검증 워크플로

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: Task 2 의 서비스명 `app`, 호스트 포트 `9004`, 볼륨 경로
  `./data`. Task 1 의 UID `1000`.
- Produces: 없음(최종 소비자)

- [ ] **Step 1: 워크플로를 만든다**

```yaml
name: ci

on:
  push:
    branches: [master, develop]
  pull_request:

jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # 서드파티 액션의 메이저 버전을 추측하지 않는다. 공식 설치
      # 스크립트에는 고정할 버전이 없다.
      - run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - run: echo "$HOME/.local/bin" >> "$GITHUB_PATH"
      - run: uv sync --frozen
      # 로컬은 고치면서 돌지만 CI 는 고치는 대신 실패해야 한다.
      - run: uv run ruff format --check .
      - run: uv run ruff check .
      - run: uv run mypy src tests
      - run: uv run pytest

  image:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # compose 의 user: 기본값과 맞춘다. 홈서버에서 사람이 밟는
      # chown 절차와 같은 것이다.
      - run: mkdir -p data && sudo chown 1000:1000 data
      - run: docker compose build

      - name: extras 가 빠졌는지 — import 가 실패해야 정상
        run: |
          if docker compose run --rm app python -c "import playwright"; then
            echo "playwright 가 런타임 이미지에 들어 있다" >&2
            exit 1
          fi

      - name: 시간대가 KST 인지
        run: |
          docker compose run --rm app python -c \
            "import datetime, sys; \
             off = datetime.datetime.now().astimezone().utcoffset(); \
             sys.exit(0 if off.total_seconds() == 32400 else 1)"

      - name: 기동과 헬스체크
        run: |
          docker compose up -d
          for _ in $(seq 1 30); do
            if curl -fsS http://127.0.0.1:9004/_stcore/health; then
              exit 0
            fi
            sleep 2
          done
          docker compose logs
          exit 1
```

- [ ] **Step 2: 아무것도 push 하지 않는지 단언한다**

Run:
```bash
grep -nE 'docker push|ghcr\.io|registry|login-action' \
  .github/workflows/ci.yml; echo "종료코드 $?"
```
Expected: 일치 없음(`종료코드 1`). 이 워크플로는 검증만 한다.

- [ ] **Step 3: 검증 명령 네 개가 다 있는지 단언한다**

Run:
```bash
for c in "ruff format --check" "ruff check ." "mypy src tests" "pytest"; do
  grep -q -- "$c" .github/workflows/ci.yml || echo "빠짐: $c"
done; echo "단언 끝"
```
Expected: `단언 끝` 만 출력.

- [ ] **Step 4: 이미지 단언 세 개가 다 있는지 확인한다**

Run:
```bash
grep -q 'import playwright' .github/workflows/ci.yml && echo "extras OK"
grep -q '32400' .github/workflows/ci.yml && echo "시간대 OK"
grep -q '_stcore/health' .github/workflows/ci.yml && echo "헬스 OK"
```
Expected: 세 줄 모두 출력.

- [ ] **Step 5: 검증 4단을 돌린다**

Run:
```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```
Expected: 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add .github/workflows/ci.yml
git commit
```
메시지 예: `👷 ci: 파이썬·이미지 검증 워크플로 추가`

---

### Task 4: 재시드 문서의 경로 확정

**Files:**
- Modify: `docs/how-to/2026-09-16-auth-reseed.md` (7-8행, 64-70행,
  112-116행)
- Modify: `docs/superpowers/specs/2026-09-16-headless-auth-design.md`
  (§10.1 의 "실제 경로는 R2 가 정한다" 문단)

**Interfaces:**
- Consumes: Task 1 의 `NOTEBOOKLM_HOME=/data/notebooklm`, Task 2 의
  호스트 볼륨 `./data`, 컨테이너명 `notebooklm-st`
- Produces: 없음

R1 이 "경로는 R2 가 정한다" 며 비워 둔 자리들이다. 이제 정해졌다.

- [ ] **Step 1: 재시작 명령을 구체화한다 (7-8행)**

찾을 문자열:
```
죽으면 배너는 다시 그려지지 않는다 — 먼저 앱을 재시작해(컨테이너면
`docker restart`) 배너부터 다시 띄운 뒤 아래 절차를 따른다.
```
바꿀 문자열:
```
죽으면 배너는 다시 그려지지 않는다 — 먼저 앱을 재시작해(컨테이너면
`docker restart notebooklm-st`) 배너부터 다시 띄운 뒤 아래 절차를
따른다.
```

- [ ] **Step 2: 볼륨 경로를 채운다 (64-70행)**

찾을 문자열:
````
```
호스트 (홈서버)                        컨테이너 내부
<볼륨 경로>/notebooklm/         ←──→  /root/.notebooklm/
      profiles/default/                     profiles/default/
```

실제 볼륨 경로는 R2(컨테이너화)에서 정한다.
````
바꿀 문자열:
````
```
호스트 (홈서버)                        컨테이너 내부
./data/notebooklm/              ←──→  /data/notebooklm/
      profiles/default/                     profiles/default/
```

호스트 쪽 `./data` 는 `docker-compose.yml` 을 둔 디렉터리 기준이다.
컨테이너 쪽 경로는 이미지의 `NOTEBOOKLM_HOME` 이 정한다.
````

- [ ] **Step 3: 이미지 확인 방법을 도커 기준으로 바꾼다 (112-116행)**

찾을 문자열:
````
컨테이너 이미지는 `uv sync --no-dev` 로 Playwright(`[browser]`
extras)를 뺀다. 이미지에 Playwright 가 정말 없는지 확인할 때는
`uv run --no-dev ...` 로 실행해야 한다. 그냥 `uv run ...` 을 쓰면
uv 가 dev 그룹을 조용히 다시 동기화해 Playwright 가 되살아나
검사가 거짓 통과를 낸다.
````
바꿀 문자열:
````
컨테이너 이미지에는 Playwright(`[browser]` extras)가 없다. 런타임
단계에 `uv` 자체를 넣지 않으므로 dev 그룹이 되살아날 경로가 없다.
직접 확인하려면 다음이 **실패**해야 한다.

```bash
docker compose run --rm app python -c "import playwright"
```

CI 가 매 push 마다 같은 것을 단언한다
(`.github/workflows/ci.yml`).
````

- [ ] **Step 4: R1 스펙 §10.1 의 빈 자리를 채운다**

찾을 문자열:
```
실제 경로는 R2 가 정한다. 이 문서는 "호스트 쪽에 놓는다" 는 원칙만 적고, 경로가
정해지면 R2 에서 채운다.

R2 가 이 문서를 이어받는다.
```
바꿀 문자열:
```
경로는 R2 에서 확정되었다 — 호스트 `./data/notebooklm/`, 컨테이너
`/data/notebooklm/`. 설계는
`docs/superpowers/specs/2026-09-16-container-deploy-design.md` 에 있다.
```

같은 절의 도식(`<볼륨 경로>/notebooklm/` ←→ `/root/.notebooklm/`)도
Step 2 와 같은 값으로 바꾼다.

- [ ] **Step 5: 옛 경로가 남지 않았는지 단언한다**

Run:
```bash
grep -rn '/root/.notebooklm' docs/ README.md; echo "종료코드 $?"
grep -rn 'R2 가 정한다\|R2(컨테이너화)에서 정한다' docs/; echo "종료코드 $?"
grep -rn 'uv run --no-dev' docs/; echo "종료코드 $?"
```
Expected: 세 번 모두 일치 없음(`종료코드 1`).

- [ ] **Step 6: 커밋**

```bash
git add docs/how-to/2026-09-16-auth-reseed.md \
        docs/superpowers/specs/2026-09-16-headless-auth-design.md
git commit
```
메시지 예: `📝 docs: 재시드 문서에 컨테이너 경로 확정`

---

### Task 5: 홈서버 배포 절차서

**Files:**
- Create: `docs/how-to/2026-09-16-homeserver-deploy.md`

**Interfaces:**
- Consumes: Task 1~3 의 모든 값 — 포트 9004/8611, 볼륨 `./data`,
  UID 1000, 컨테이너명 `notebooklm-st`, CI 파일 경로
- Produces: Task 6 의 README 가 이 문서를 링크한다

- [ ] **Step 1: 문서를 만든다**

````markdown
# 홈서버에 배포하기

앱을 홈서버의 도커 컨테이너로 띄우는 절차다. 설계 근거는
`docs/superpowers/specs/2026-09-16-container-deploy-design.md` 에 있다.

## 준비물

- 홈서버에 Docker Engine 과 Compose v2
- 데스크톱에 이 저장소와 `uv` (자격증명을 만들 때 쓴다)
- NotebookLM 에 접근 가능한 구글 계정

## 1. 저장소와 데이터 디렉터리

홈서버에서.

```bash
git clone <저장소 URL> notebooklm-st
cd notebooklm-st
mkdir -p data
sudo chown 1000:1000 data
```

`chown` 을 빼먹으면 컨테이너가 `/data` 에 쓰지 못해 기동이 실패한다.
홈서버 사용자의 UID 가 1000 이 아니면 그 값으로 바꾸고, 같은 값을
2단계에서 `PUID`/`PGID` 로 넘긴다.

```bash
id -u; id -g   # 내 UID/GID 확인
```

## 2. 띄우기

```bash
docker compose up -d --build
```

UID 가 1000 이 아니라면:

```bash
PUID=$(id -u) PGID=$(id -g) docker compose up -d --build
```

상태 확인.

```bash
docker compose ps        # STATUS 가 healthy 가 될 때까지 기다린다
docker compose logs -f   # 기동 로그
```

접속 주소는 **http://<홈서버IP>:9004** 다. 컨테이너 안에서는 8611 에서
돌고 `docker-compose.yml` 이 호스트 9004 에 붙인다.

## 3. 자격증명 넣기

앱은 브라우저를 띄우지 않는다. 최초 로그인은 사람이 데스크톱에서 한다.

데스크톱에서.

```bash
cd notebooklm-st
uv sync
uv run notebooklm login
```

크로미움이 열린다. 구글 로그인을 마치면 CLI 가
`~/.notebooklm/profiles/default/storage_state.json` 에 저장한다
(윈도우는 `C:\Users\<사용자>\.notebooklm\profiles\default\`).

홈서버 대시보드에서.

1. 만료 배너 아래 **자격증명 올리기** 를 편다.
2. 그 `storage_state.json` 을 고른다.
3. **반입** 을 누른다.

반입에 성공하면 앱이 곧바로 다시 확인까지 하고 화면을 새로 그린다.
업로드가 안 될 때의 대체 경로와 자격증명 취급 수칙은
[인증이 만료됐을 때 되살리기](2026-09-16-auth-reseed.md) 에 있다.

## 4. 기존 데이터 옮기기 (선택)

데스크톱에서 쓰던 질문 템플릿과 이력을 가져오려면 앱을 내린 뒤
`questions.db` 를 복사한다.

```bash
docker compose down
scp <데스크톱>/notebooklm-st/questions.db ./data/questions.db
sudo chown 1000:1000 data/questions.db
docker compose up -d
```

스키마가 다르면 앱이 연결 시점에 안내와 함께 멈춘다. 이 프로젝트는
마이그레이션을 지원하지 않으므로, 그때는 파일을 지우고 새로 시작한다.

## 5. 검증

배포 뒤 한 번 돈다. 1~4 번은 CI 가 매 push 마다 자동으로 하지만,
5~8 번은 실제 홈서버와 계정이 있어야 해서 사람이 한다.

| # | 확인 | 통과 기준 |
|---|---|---|
| 1 | `docker compose build` | 성공 |
| 2 | `docker compose run --rm app python -c "import playwright"` | **실패해야 정상** |
| 3 | `docker compose run --rm app python -c "import datetime; print(datetime.datetime.now().astimezone())"` | `+09:00` |
| 4 | `docker compose ps` | `healthy` |
| 5 | 다른 기기에서 `http://<홈서버IP>:9004` | 화면이 뜬다 |
| 6 | `ls -l data/` | `questions.db`·`notebooklm/` 이 내 UID 소유 |
| 7 | 업로드 UI 로 자격증명 반입 | 배너가 사라진다 |
| 8 | `docker compose down && docker compose up -d` | 질문·이력·인증이 보존된다 |

## 운영 규칙

- **인터넷에 내놓지 않는다.** 대시보드의 자격증명 업로드 폼은 앱이
  외부에 노출되지 않는다는 전제 위에 있다. 포트포워딩·리버스
  프록시·터널로 9004 를 인터넷에 열려면 먼저 업로드 폼을 제거해야
  한다. 홈 LAN 안에서도 구간은 평문 HTTP 다 — 같은 Wi-Fi 의 다른
  기기에는 보인다.
- **볼륨에 `:ro` 를 걸지 않는다.** 앱이 회전된 쿠키를 되쓴다. 읽기
  전용으로 마운트하면 재시작마다 옛 쿠키로 돌아가고 결국 죽는다.
- **실행 중일 때 재시작하지 않는다.** 질의는 백그라운드 스레드에서
  돌고 이력은 끝난 뒤에 저장된다. 진행 중에 내리면 그 실행은 결과를
  남기지 못한다. **실행 현황** 화면이 비었을 때 내린다.
- **UID 가 1000 이 아니면 `PUID`/`PGID` 로 덮는다.** 재빌드는 필요
  없다.

## 인증이 만료되면

인증 판정은 **앱이 뜰 때 한 번만** 한다. 떠 있는 도중에 세션이 죽으면
배너는 다시 그려지지 않는다.

```bash
docker restart notebooklm-st
```

배너가 다시 뜨면 3단계의 반입 절차를 따른다.

## 로그 보기

화면이 "자세한 사유는 앱 로그에 남습니다" 라고 안내할 때 볼 곳이다.

```bash
docker logs notebooklm-st
docker compose logs -f app
```

로그는 10MB 씩 3개까지만 보관한다(`docker-compose.yml`).
````

- [ ] **Step 2: 링크 대상이 실재하는지 단언한다**

Run:
```bash
ls docs/how-to/2026-09-16-auth-reseed.md
ls docs/superpowers/specs/2026-09-16-container-deploy-design.md
ls docker-compose.yml .github/workflows/ci.yml
```
Expected: 네 경로 모두 존재. 하나라도 없으면 앞 태스크가 덜 끝난
것이다.

- [ ] **Step 3: 운영 규칙 네 줄과 검증 8행이 다 있는지 단언한다**

Run:
```bash
f=docs/how-to/2026-09-16-homeserver-deploy.md
grep -c '^| [0-8] |' "$f"
for s in "인터넷에 내놓지 않는다" ":ro" "실행 중일 때 재시작하지" PUID; do
  grep -q "$s" "$f" || echo "빠짐: $s"
done; echo "단언 끝"
```
Expected: 첫 줄이 `8`, 그다음 `단언 끝` 만 출력.

- [ ] **Step 4: 검증 4단을 돌린다**

Run:
```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```
Expected: 전부 통과.

- [ ] **Step 5: 커밋**

```bash
git add docs/how-to/2026-09-16-homeserver-deploy.md
git commit
```
메시지 예: `📝 docs: 홈서버 배포 절차서 추가`

---

### Task 6: README 와 진입점 독스트링

**Files:**
- Modify: `README.md` (요구사항 표, 사용법 절, 데이터 저장 위치 절)
- Modify: `src/notebooklm_st/app.py` (모듈 독스트링)

**Interfaces:**
- Consumes: Task 5 의 문서 경로, Task 2 의 포트 9004
- Produces: 없음(마지막 태스크)

- [ ] **Step 1: README 요구사항 표에 행을 더한다**

찾을 문자열:
```
| 계정 | 구글 계정 (NotebookLM 접근 권한) | 첫 로그인은 사람이 CLI 로 한 번 |
```
바꿀 문자열:
```
| 계정 | 구글 계정 (NotebookLM 접근 권한) | 첫 로그인은 사람이 CLI 로 한 번 |
| 컨테이너 | Docker Engine + Compose v2 | 홈서버 배포 시에만. `docker-compose.yml` |
```

- [ ] **Step 2: README 접속 주소를 데스크톱 한정으로 명시한다**

찾을 문자열:
```
접속 주소는 **http://127.0.0.1:8611** 입니다. 주소와 포트의 정본은 `.streamlit/config.toml` 이며, 실행 스크립트가 이 파일을 읽어 안내합니다.
```
바꿀 문자열:
```
데스크톱 접속 주소는 **http://127.0.0.1:8611** 입니다. 주소와 포트의 정본은 `.streamlit/config.toml` 이며, 실행 스크립트가 이 파일을 읽어 안내합니다. 컨테이너는 이 파일을 쓰지 않습니다(아래 「홈서버 (Docker)」).
```

- [ ] **Step 3: README 에 컨테이너 실행 절을 넣는다**

Step 2 에서 고친 문단 **바로 다음**, `### 첫 실행 — 인증` **앞**에
넣는다.

````markdown
### 홈서버 (Docker)

```bash
mkdir -p data && sudo chown 1000:1000 data
docker compose up -d --build
```

접속 주소는 **http://<홈서버IP>:9004** 입니다. 컨테이너 안에서는 8611 에서 돌고, `docker-compose.yml` 이 호스트 9004 에 붙입니다.

절차와 운영 규칙은 [홈서버에 배포하기](docs/how-to/2026-09-16-homeserver-deploy.md) 에 있습니다.

> **인터넷에 노출하지 마세요.** 대시보드의 자격증명 업로드 폼은 앱이 외부에 노출되지 않는다는 전제 위에 있습니다.
````

- [ ] **Step 4: README 데이터 저장 위치에 컨테이너 경로를 적는다**

찾을 문자열:
```
기본값은 실행 디렉터리의 `questions.db` (SQLite) 입니다. 환경 변수로 바꿀 수 있습니다.
```
바꿀 문자열:
```
기본값은 실행 디렉터리의 `questions.db` (SQLite) 입니다. 환경 변수로 바꿀 수 있습니다. 컨테이너는 이미지가 `NOTEBOOKLM_ST_DB=/data/questions.db` 를 정해 두므로 호스트의 `./data/questions.db` 에 남습니다.
```

- [ ] **Step 5: `app.py` 모듈 독스트링을 바꾼다**

찾을 문자열:
```python
"""Streamlit 진입점.

실행:
    uv run streamlit run src/notebooklm_st/app.py

``.streamlit/config.toml`` 이 서버를 ``127.0.0.1:8611`` 에만
바인딩하므로 같은 네트워크의 다른 기기에서는 접속할 수 없다.
기본 포트 8501 을 쓰지 않는 것은 다른 Streamlit 프로젝트와
충돌하지 않게 하기 위해서다.
"""
```
바꿀 문자열:
```python
"""Streamlit 진입점.

실행 경로가 둘이다.

데스크톱 — ``uv run streamlit run src/notebooklm_st/app.py``.
``.streamlit/config.toml`` 이 서버를 ``127.0.0.1:8611`` 에만
바인딩하므로 같은 네트워크의 다른 기기에서는 접속할 수 없다.
기본 포트 8501 을 쓰지 않는 것은 다른 Streamlit 프로젝트와
충돌하지 않게 하기 위해서다.

컨테이너 — ``docker compose up -d``. 이미지에는
``.streamlit/config.toml`` 이 들어가지 않는다. 주소와 포트는
이미지의 환경 변수가 정하고(``0.0.0.0:8611``), 홈 LAN 에 열리는
포트는 ``docker-compose.yml`` 의 ``9004`` 다. 절차는
docs/how-to/2026-09-16-homeserver-deploy.md 에 있다.
"""
```

- [ ] **Step 6: 검증 4단을 돌린다**

Run:
```
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```
Expected: 전부 통과. 독스트링만 바꿨으므로 테스트 수가 R1 종료
시점과 같아야 한다. `D` 규칙(Google 스타일)에 걸리면 줄바꿈 위치를
조정한다 — 요약 줄 다음 빈 줄은 유지한다.

- [ ] **Step 7: 서술이 일관되는지 단언한다**

Run:
```bash
grep -n '9004' README.md src/notebooklm_st/app.py
grep -rn '127.0.0.1:8611 에만' src/notebooklm_st/app.py
```
Expected: 첫 명령은 README 와 `app.py` 양쪽에서 `9004` 를 찾는다.
둘째 명령은 그 문장이 **데스크톱 절 안에** 있는지 눈으로 확인한다.

- [ ] **Step 8: 커밋**

```bash
git add README.md src/notebooklm_st/app.py
git commit
```
메시지 예: `📝 docs: README 와 진입점에 컨테이너 실행 경로 반영`

---

## 완료 확인

모든 태스크가 끝난 뒤 컨트롤러가 직접 돌린다.

```bash
# 옛 경로·미확정 표현이 남지 않았는지
grep -rn '/root/.notebooklm' . --exclude-dir=.git; echo "종료코드 $?"
grep -rn 'R2 가 정한다' docs/; echo "종료코드 $?"

# 이미지 환경변수의 정본이 한 곳인지
grep -E 'NOTEBOOKLM_|STREAMLIT_' docker-compose.yml; echo "종료코드 $?"

# 파이썬이 그대로인지
uv run ruff check .
uv run mypy src tests
uv run pytest
```
Expected: 앞의 세 grep 은 전부 일치 없음, 검증은 전부 통과.

---

## 사람이 도는 검증 (push 이후)

**이 개발 머신에는 도커가 없다.** 아래는 에이전트가 할 수 없는 일이고,
순서대로 사람이 한다.

1. `git push` — 이 시점에 CI 가 처음 돈다. 파이썬 job 과 이미지 job 이
   모두 초록이어야 한다. 이미지 job 이 여기서 처음으로 실제
   `docker compose build` 를 돌린다.
2. CI 가 빨간 경우, 로그를 보고 계획으로 돌아온다. 가장 가능성이 높은
   실패는 스펙 12절의 미검증 가정 셋이다 — `read_only: true` 아래
   파일 업로더, `/_stcore/health` 경로 존재, `tmpfs` 표기의 도커 버전
   호환.
3. 홈서버에서 배포 절차서
   (`docs/how-to/2026-09-16-homeserver-deploy.md`)의 5절 검증 5~8 번을
   돈다.
4. `develop → master` PR 을 사람이 GitHub 웹에서 만든다.
