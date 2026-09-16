# 컨테이너 전환 설계 — 홈서버 도커 배포

- **작성일**: 2026-09-16
- **상태**: 설계 (구현 계획 수립 전)
- **대상**: `Dockerfile`, `docker-compose.yml`, `.dockerignore`,
  `.github/workflows/build.yml`, 배포·재시드 문서, `README.md`
- **범위**: 릴리스 R2. **배포만 한다.** 앱의 동작은 바꾸지 않는다.
  선행 조건인 R1(무인 갱신 인증 전환)은 완료되었다
  (`docs/superpowers/specs/2026-09-16-headless-auth-design.md`).

---

## 1. 무엇을 하고, 무엇을 하지 않는가

R1 이 앱에서 브라우저 로그인을 걷어내 컨테이너에서 뜰 수 있게 만들었다.
R2 는 **실제로 띄운다.** 이미지를 굽고, 볼륨을 붙이고, 홈서버에서
돌린다.

왜 지금인가. 기획 `request_spec_2.md` 의 요구 5 — 즐겨찾기 채널을
주기적으로 확인해 요약본을 자동 생성한다 — 는 **사람이 데스크톱을 켜
두지 않아도 도는 서버** 없이는 성립하지 않는다. R3~R6 이 얹힐 바닥을
먼저 놓는 릴리스다.

**소스 코드의 동작은 바꾸지 않는다.** `src/` 아래에서 손대는 것은
컨테이너에서 사실과 어긋나게 되는 독스트링 한 문단뿐이고(9.3), 실행
결과에는 영향이 없다.

`AuthGate` 의 `ok → failed` 전이도 하지 않는다. 그 항목은 `runner` 를
고쳐야 하고, 그 순간 이 릴리스는 배포가 아니라 기능 변경이 된다.
따라서 인증 배너는 이 릴리스에서도 **기동 시 판정**이다 — 떠 있는
도중에 세션이 죽으면 앱을 재시작해야 배너와 업로더가 다시 보인다.
컨테이너에서 그 재시작은 `docker restart notebooklm-st` 한 줄이고,
`restart: unless-stopped` 덕분에 호스트 재부팅 뒤에도 같은 경로로
회복된다.

---

## 2. 코드를 안 바꾸고 되는 근거

코드와 라이브러리를 읽어 다섯 가지를 확인했다. 이 절이 1절의
"동작을 바꾸지 않는다" 를 떠받친다.

| 확인한 것 | 근거 | 설계에 주는 영향 |
|---|---|---|
| `NOTEBOOKLM_HOME` 환경변수로 프로필 위치를 정할 수 있다 | `notebooklm/paths.py:127` | 자격증명이 `HOME`·`/root` 에 묶이지 않는다. 볼륨 하나로 합칠 수 있다 |
| `NOTEBOOKLM_ST_DB` 환경변수로 DB 경로를 정할 수 있다 | `services/store.py` 의 `DB_PATH_ENV_VAR` | 이력이 컨테이너 안이 아니라 볼륨에 남는다 |
| playwright 부재는 L3 에서 `UNAVAILABLE` 로 처리된다 | `notebooklm/_auth/headless_reauth.py:686` — 예외가 아니라 상태값을 돌려준다 | `allow_headless=True`(`services/nlm.py:129`)를 그대로 둬도 컨테이너에서 안전하다 |
| `notebooklm/__main__.py` 가 존재한다 | 패키지 파일 | 자격증명 업로드 반입이 부르는 `sys.executable -m notebooklm`(`services/auth.py`)이 컨테이너에서도 그대로 돈다 |
| `server.address` 의 기본값은 비어 있다 | `streamlit/config.py:1016` | 설정을 주지 않으면 전 인터페이스에 바인딩한다. 컨테이너에서 원하는 기본값이다 |
| `/_stcore/health` 가 헬스체크 라우트다 | `streamlit/web/server/starlette/starlette_routes.py:438` 의 `create_health_routes`, `starlette_static_routes.py:45` 의 예약 경로 | Dockerfile 의 `HEALTHCHECK` 와 동작 게이트가 이 경로를 쓴다 |

반대로, 환경변수를 **안 주면 조용히 깨지는 것** 두 가지가 여기서
나온다. 둘 다 앱이 정상으로 보이기 때문에 8절의 동작 게이트가 명시적으로
확인한다.

- `NOTEBOOKLM_ST_DB` 를 안 주면 `store.default_db_path()` 가 현재 작업
  디렉터리(`/app`)에 `questions.db` 를 만든다. 컨테이너를 다시 만드는
  순간 질문 템플릿과 실행 이력이 **통째로 사라진다.**
- `TZ` 를 안 주면 컨테이너 기본 시간대(UTC)가 적용된다. `store.now()`
  는 시간대 정보 없는 로컬 시각을 쓰므로(`services/store.py` 끝),
  이력의 시각이 **9시간 어긋난 채로 저장된다.**

---

## 3. 이미지

멀티스테이지로 굽고, **런타임 단계에는 `uv` 를 넣지 않는다.**

`uv sync --no-dev` 로 playwright 를 뺀 뒤에도 그냥 `uv run` 을 쓰면
uv 가 dev 그룹을 조용히 다시 동기화해 playwright 가 돌아온다. 런타임에
uv 가 없으면 그 함정은 **성립할 수 없다.** `--no-dev` 를 매번 기억해서
붙이는 규율 대신 구조로 막는다.

```dockerfile
# ── builder ────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── runtime ────────────────────────────────────────────────
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

### 3.1 결정과 근거

**프로젝트를 설치하지 않고 `PYTHONPATH=/app/src` 로 쓴다.**
`--no-install-project` 로 의존성만 받고 소스는 그대로 얹는다. 설치까지
하면 site-packages 와 `/app/src` 에 **코드가 두 벌** 생기고,
`streamlit run` 은 스크립트가 든 디렉터리(`/app/src/notebooklm_st`)만
`sys.path` 에 넣으므로 실제 임포트되는 것은 설치본이 된다. 헷갈리는
상태를 만들 이유가 없다. 덤으로 의존성 레이어가 `pyproject.toml` 과
`uv.lock` 에만 의존하게 되어 소스 수정 시 재빌드가 싸다.

**두 스테이지의 베이스를 같은 계열로 맞춘다.** 빌더가 만든
`/app/.venv` 는 빌더의 인터프리터 경로를 절대 경로로 참조한다. uv 의
`python3.13-bookworm-slim` 이미지는 `python:3.13-slim-bookworm` 위에
uv 를 얹은 것이라 경로와 ABI 가 일치한다. 베이스를 갈아탈 때는 **두
줄을 함께** 바꾼다.

**uv 버전은 태그로만 핀하고 정확한 버전을 박지 않는다.** 재현성의
정본은 `uv.lock` 이고 `--frozen` 이 그것을 강제한다. uv 자신의 버전은
잠금 파일이 있는 한 결과에 영향을 주지 않는다.

**`uv sync --frozen`.** `uv.lock` 이 `pyproject.toml` 과 어긋나면 빌드가
**실패한다.** 이미지가 조용히 다른 의존성으로 구워지는 것보다 낫다.

**`.streamlit/config.toml` 은 이미지에 들어가지 않는다.** `COPY` 대상이
`src/` 뿐이라 자동으로 빠진다. 그래서 컨테이너는 데스크톱용
`127.0.0.1` 바인딩을 물려받지 않고, "환경변수가 프로젝트 설정 파일을
덮는가" 라는 **검증하지 않은 전제를 아예 만들지 않는다.** 주소와
포트는 이미지의 `ENV` 가 정한다. 데스크톱은 `config.toml` 을 그대로
쓴다 — 두 환경이 각자의 정본을 갖는다.

**앱 환경변수는 compose 가 아니라 이미지에 둔다.** 값의 정본을 한
군데로 모은다. compose 에만 두면 `docker run` 으로 이미지를 직접
띄웠을 때 DB 가 `/app` 에 생기고(2절) 포트가 8501 이 되는데, 그건
이미지가 혼자서는 틀리게 선다는 뜻이다. 양쪽에 적으면 두 곳이
어긋난다. compose 는 **호스트마다 달라지는 것**(포트 바인딩·볼륨
경로·UID·재시작·로그)만 맡는다.

**비root `app`(UID/GID 1000).** 이 컨테이너는 계정 동등 자격증명을
들고 있다. 홈서버 사용자의 UID 가 1000 이 아니면 5절의 `user:` 로
덮는다(재빌드 불필요).

**`PYTHONDONTWRITEBYTECODE=1`.** 루트 파일시스템을 읽기 전용으로
걸기 때문에(5절) `/app/src` 옆에 `.pyc` 를 쓰려는 시도가 매 기동마다
실패한다. 파이썬이 조용히 넘어가긴 하지만 할 이유가 없는 일이다.
의존성 쪽 바이트코드는 빌드 시 `UV_COMPILE_BYTECODE=1` 로 이미 굽혀
있다.

---

## 4. 볼륨과 환경변수

**컨테이너가 쓰는 곳은 `/data` 한 군데다.** 바인드 마운트 하나로
백업이 디렉터리 하나가 되고, 나머지 파일시스템은 건드릴 이유가 없다.

```
호스트  ./data/                          컨테이너  /data/
    questions.db                             questions.db
    notebooklm/                              notebooklm/     ← NOTEBOOKLM_HOME
        profiles/default/                        profiles/default/
            storage_state.json                       storage_state.json
            (락·회전 형제 파일 4개)                     (같음)
    .streamlit/                              .streamlit/     ← HOME=/data 부산물
```

값의 정본은 이미지다(3절의 두 번째 `ENV`).

| 환경변수 | 값 | 근거 |
|---|---|---|
| `NOTEBOOKLM_HOME` | `/data/notebooklm` | `notebooklm/paths.py:127` |
| `NOTEBOOKLM_ST_DB` | `/data/questions.db` | `services/store.py`. 없으면 이력이 컨테이너와 함께 사라진다(2절) |
| `TZ` | `Asia/Seoul` | `store.now()` 가 naive 로컬 시각. 없으면 9시간 어긋난다(2절) |
| `HOME` | `/data` | 비root 사용자에게 홈이 없다. 쓰기 대상을 한 군데로 모은다 |
| `STREAMLIT_SERVER_PORT` | `8611` | 이미지에 `config.toml` 이 없으므로 명시하지 않으면 기본값 8501 이 된다 |
| `STREAMLIT_SERVER_ADDRESS` | `0.0.0.0` | 컨테이너 밖에서 닿으려면 필수. **노출 범위는 이 값이 아니라 포트 바인딩이 정한다**(6절) |
| `STREAMLIT_SERVER_HEADLESS` | `true` | 브라우저 자동 열기와 이메일 프롬프트를 막는다 |
| `STREAMLIT_BROWSER_GATHER_USAGE_STATS` | `false` | 외부 통신을 줄인다 |
| `STREAMLIT_SERVER_FILE_WATCHER_TYPE` | `none` | 컨테이너에서 소스 감시는 불필요한 inotify 소비다 |

R1 스펙 §2.6 이 확인해 둔 운영 조건 두 가지를 그대로 받는다.

- **볼륨은 쓰기 가능해야 한다.** `:ro` 로 걸면 라이브러리가 회전시킨
  쿠키를 되쓰지 못해 재시작마다 옛 쿠키로 돌아가고 결국 죽는다.
- **파일 하나가 아니라 프로필 디렉터리 전체**를 마운트한다. 락과 회전
  상태가 `storage_state.json` 옆 형제 파일 4개로 존재한다.

`NOTEBOOKLM_HOME` 은 `import_credentials` 가 띄우는
`python -m notebooklm auth import-cookies -` 자식 프로세스에 **그대로
상속된다.** 업로드로 반입한 자격증명이 앱이 읽는 바로 그 프로필에
기록된다 — 코드 변경 없이 성립한다.

---

## 5. 오케스트레이션

```yaml
# docker-compose.yml
services:
  app:
    build: .
    image: notebooklm-st:local
    container_name: notebooklm-st
    user: "${PUID:-1000}:${PGID:-1000}"
    ports:
      - "9004:8611"          # 호스트 9004 → 컨테이너 8611
    volumes:
      - ./data:/data         # 쓰기 가능해야 한다 (:ro 금지)
    # 앱 환경변수는 이미지에 박혀 있다(3절). 여기서는 호스트마다
    # 달라지는 것만 덮는다. 예: 시간대가 다르면 TZ 한 줄.
    restart: unless-stopped
    read_only: true
    tmpfs: ["/tmp"]
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

**포트.** 호스트 `9004`, 컨테이너 `8611`. Dockerfile 의 `EXPOSE` 는
정의상 컨테이너가 listen 하는 포트를 적는 자리이므로 거기엔 `8611` 이
남고, `9004` 는 이 파일의 `ports:` 에만 나타난다.

**`restart: unless-stopped`.** 홈서버 재부팅 뒤 자동 기동한다. 인증
판정이 기동 시 한 번뿐이므로(1절) 재시작이 곧 배너 회복 경로다.

**`read_only: true` + `tmpfs: /tmp`.** 계정 동등 자격증명을 들고 있는
컨테이너라 쓰기 가능한 곳을 `/data` 와 `/tmp` 로만 남긴다. 4절에서
`HOME=/data` 로 모아 둔 것이 이것을 가능하게 한다. 파일 업로더는
`streamlit/web/server/server.py` 의
`MemoryUploadedFileManager` 를 쓰므로 업로드 내용이 메모리에 남고,
멀티파트가 큰 본문을 스풀하더라도 `/tmp` 가 tmpfs 라 쓸 수 있다.

**로그 회전.** 몇 주씩 도는 컨테이너다. 화면 문구 "자세한 사유는 앱
로그에 남습니다"(`components/auth_gate.py`)가 가리키는 실제 목적지가
`docker logs notebooklm-st` 이므로, 그 로그가 디스크를 먹지 않게
한다.

---

## 6. 노출 정책

`9004:8611` 은 호스트의 모든 인터페이스에 열린다 — **홈 LAN 전체에서
접근 가능하다.** 이것이 이 도구의 목적에 맞는다. 폰이나 노트북에서
대시보드를 여는 것이 홈서버로 옮기는 이유다.

R1 스펙 §13.1 이 말하는 "외부 노출" 은 **인터넷**이고, 그 선은
지킨다.

> 5.4·7.1 의 자격증명 업로드는 **앱이 외부에 노출되지 않는다는 전제**
> 위에 있다. … 이 전제가 깨지면 업로드 UI 를 제거하고 볼륨 직접
> 복사로 되돌린다.

따라서 **포트포워딩·리버스 프록시·터널로 9004 를 인터넷에 내놓지
않는다.** 내놓기로 결정하는 순간 그것은 R2 의 결정이 아니라 업로드
UI 를 제거하는 별도 작업이다. 이 조건을 배포 문서에 못박는다.

홈 LAN 안에서도 구간은 평문 HTTP 다. 같은 Wi-Fi 의 다른 기기에는
보인다. 호스트 자신만 쓰고 Tailscale 등 암호화된 경로로 접근하려면
`127.0.0.1:9004:8611` 로 바꾼다.

---

## 7. 운영 한계

**진행 중인 질의는 재시작에서 유실된다.** 질의는 daemon 스레드에서
돌고(`services/runner.py`), 이력은 파이프라인이 끝난 뒤에 저장된다.
`docker stop`·`docker restart` 하면 그 스레드는 결과를 남기지 못하고
사라진다 — 화면에서도 이력에서도 흔적이 없다.

코드를 바꾸지 않는 이 릴리스에서는 고칠 수 없다. 운영 규칙으로
적는다: **실행 현황이 비어 있을 때 재시작한다.**

**인증 배너는 기동 시 판정이다**(1절). 떠 있는 도중에 세션이 죽으면
`docker restart notebooklm-st` 로 다시 띄워야 배너와 업로더가 보인다.

---

## 8. 이미지 배포 워크플로

이 릴리스가 도커 빌드를 들여오면서 **조용히 틀리는 검사** 두 개가
생긴다 — playwright 가 이미지에 딸려 들어와도, 시간대가 UTC 로 서도
앱은 멀쩡히 돈다. 사람이 손으로 도는 체크리스트는 릴리스 두세 번이면
안 돌게 되므로 기계에 맡긴다.

워크플로는 하나다. 트리거·권한·액션 핀·게시 방식은 다른 프로젝트와
같은 규약을 쓴다 — 정식 릴리스에서 배포 이미지를, 수동 실행에서
`devel` 이미지를 GHCR(`ghcr.io/susoterran/notebooklm-st`)에 올린다.

```yaml
# .github/workflows/build.yml
name: build
on:
  release:
    types: [released]   # 정식 릴리스 → 배포 이미지
  workflow_dispatch:    # 수동 실행 → devel 이미지

permissions:            # 최소권한 기본값
  contents: read

jobs:
  verify:               # 검증 4단. image 의 needs
  image:
    needs: [verify]
    permissions:
      contents: read
      packages: write   # 이 잡만 승격
    # 1. buildx 로 로컬 빌드 (load: true, push: false)
    # 2. 취약점 게이트 — trivy HIGH·CRITICAL, ignore-unfixed
    # 3. 동작 게이트 — 스캔한 그 이미지를 compose 설정으로 돌린다
    # 4. 게시 — sbom, provenance
```

### 8.1 게이트 두 개

**취약점 게이트.** push 전에 로컬로만 굽고 스캔한다. 여기서 걸리면
GHCR 에 아무것도 올라가지 않는다. push 를 먼저 하면 스캔이 실패해도
`latest`·`devel` 롤링 태그가 이미 취약한 이미지를 가리키게 되어 게이트
역할을 하지 못한다.

**동작 게이트.** 취약하지 않은 것과 실제로 도는 것은 다른 질문이다.
`/_stcore/health` 는 Streamlit **서버**가 답하므로, `PYTHONPATH` 가
틀렸거나 런타임에 의존성이 빠졌거나 `/data` 에 쓰지 못해도 헬스체크는
200 을 돌려준다. 그래서 다섯 가지를 따로 단언한다.

| 단언 | 무엇을 막나 |
|---|---|
| 앱 모듈 임포트 | `PYTHONPATH` 오류, 런타임에 빠진 의존성 |
| `/data` 에 DB 생성 | DB 가 `/app` 에 생기는 사고(2절), `read_only` 아래 볼륨 쓰기 |
| `import playwright` 가 `ModuleNotFoundError` 로 실패 | extras 혼입 |
| UTC 오프셋이 32400 | 시간대가 UTC 로 서는 것(2절) |
| `/_stcore/health` 응답 | 기동 실패 |

playwright 단언은 **종료 코드가 정확히 1 이고 사유가
`ModuleNotFoundError`** 일 때만 통과한다. "0 이 아니면 통과" 로 두면
컨테이너가 못 뜨거나(125) `python` 이 없어도(127) "extras 가 잘
빠졌다" 로 읽힌다.

스캔 빌드가 만든 **바로 그 이미지**에 compose 태그를 붙여 돌린다.
태그를 먼저 붙이므로 compose 는 다시 굽지 않고, 검사 대상과 게시
대상이 같은 아티팩트가 된다. 홈서버와 같은 설정(비root·`read_only`·
tmpfs·볼륨)으로 도는 것도 여기서 확인된다.

### 8.2 결정과 근거

**검증 명령은 개발 중 쓰는 것과 같게 두되 변형하지 않는 형태로
바꾼다.** 로컬은 `ruff format .` · `ruff check --fix .` 로 고치면서
돌지만, 워크플로는 `--check` · `--fix` 없이 돌려 **고치는 대신
실패**한다.

**서드파티 액션은 커밋 SHA 로 핀한다.** uv 만 예외로 공식 설치
스크립트를 쓴다 — 액션의 메이저 버전은 시간이 지나면 바뀌고, 이
저장소는 워크플로를 자주 손볼 곳이 아니다. 설치 스크립트는 고정할
버전이 없다.

**`data/` 를 미리 만들고 `1000:1000` 으로 넘긴다.** compose 의 `user:`
기본값과 맞춘다. 이걸 빼면 러너 사용자가 만든 디렉터리에 컨테이너가
쓰지 못해 기동이 실패한다 — 홈서버에서 사람이 겪을 실패와 같은
것이고, 워크플로가 이 절차를 먼저 밟는 것 자체가 배포 문서의 `chown`
단계가 옳다는 확인이 된다.

### 8.3 워크플로가 잡지 못하는 것

**push 에는 아무것도 돌지 않는다.** 트리거가 릴리스와 수동 실행뿐이라
`develop` 에 쌓이는 커밋은 자동 검증을 받지 않는다. 검증 4단은 사람이
커밋 전에 로컬에서 돌린다.

10절 검증 항목 중 5~8 번(LAN 접근, 호스트 쪽 소유권, 자격증명 반입
왕복, 재시작 후 지속성)은 실제 홈서버와 구글 계정이 필요하다. 러너는
amd64 라 홈서버가 ARM 이면 **아키텍처 고유 문제는 잡지 못한다.** 이
둘은 사람이 도는 체크리스트로 남는다.

---

## 9. 문서

### 9.1 새로 쓰는 것

`docs/how-to/2026-09-16-homeserver-deploy.md` — 홈서버 배포 절차서.

- 사전 준비: 호스트 디렉터리 생성과 `chown 1000:1000 ./data`
- 데스크톱에서 `uv run notebooklm login` 으로 자격증명 만들기
- `docker compose up -d --build`
- 업로드 UI 로 자격증명 반입 → `http://<홈서버IP>:9004` 확인
- 기존 데스크톱 `questions.db` 이전(선택)
- **운영 규칙 네 줄**: 인터넷에 내놓지 않는다(6절) · 볼륨에 `:ro` 를
  걸지 않는다(4절) · 실행 중일 때 재시작하지 않는다(7절) · UID 가
  1000 이 아니면 `PUID`/`PGID` 로 덮는다(3.1)
- 10절의 검증 체크리스트

### 9.2 고치는 것

| 파일 | 왜 |
|---|---|
| `docs/how-to/2026-09-16-auth-reseed.md` | 컨테이너 경로가 `/root/.notebooklm/` 로 적혀 있다 → `/data/notebooklm/`, 호스트 쪽은 `./data/notebooklm/`. `docker restart` 에 컨테이너 이름을 넣어 구체화 |
| `README.md` | 컨테이너 실행 절 신설, 접속 주소를 두 갈래(데스크톱 8611 / 홈서버 9004)로, 요구사항 표에 Docker 추가 |
| `docs/superpowers/specs/2026-09-16-headless-auth-design.md` §10.1 | "실제 경로는 R2 가 정한다" 로 비워 둔 자리에 `/data/notebooklm/` 을 채운다 |

### 9.3 코드 파일 한 곳

`src/notebooklm_st/app.py` 의 모듈 독스트링이 이렇게 적고 있다.

> `.streamlit/config.toml` 이 서버를 `127.0.0.1:8611` 에만
> 바인딩하므로 같은 네트워크의 다른 기기에서는 접속할 수 없다.

컨테이너에서는 거짓이다(3.1 — 이미지에 `config.toml` 이 없다).
**독스트링 한 문단만** 고쳐 두 실행 경로를 모두 적는다. 실행 결과에
영향이 없으므로 1절의 "동작을 바꾸지 않는다" 를 지킨다. 이 릴리스가
스스로 만드는 거짓 서술을 남겨 두지 않기 위한 유일한 예외다.

---

## 10. 검증

| # | 확인 | 통과 기준 | 누가 |
|---|---|---|---|
| 1 | `docker compose build` | 성공. `--frozen` 이 잠금 파일 불일치를 여기서 잡는다 | 워크플로 |
| 2 | `import playwright` | **실패해야 정상.** extras 가 빠졌다는 증거 | 워크플로 |
| 3 | `datetime.now()` 의 UTC 오프셋 | `+09:00`. UTC 면 이력이 9시간 어긋난다 | 워크플로 |
| 4 | `/_stcore/health` | 응답한다. 곧 Streamlit 이 떴다는 뜻 | 워크플로 |
| 5 | 다른 기기에서 `http://<홈서버IP>:9004` | 화면이 뜬다 | 사람 |
| 6 | 호스트에서 `ls -l data/` | `questions.db` 와 `notebooklm/` 이 `user:` 가 가리키는 UID(기본 `1000:1000`) 소유로 생성된다 | 사람 |
| 7 | 업로드 UI 로 자격증명 반입 | 배너가 사라진다. `read_only: true` 아래서 파일 업로더가 도는지도 함께 확인된다 | 사람 |
| 8 | `docker compose down && docker compose up -d` | 질문·이력·인증이 보존된다 | 사람 |

5~8 번은 배포 절차서(9.1)에 체크리스트로 싣고 홈서버에서 한 번 돈다.

---

## 11. 건드리는 파일

| 파일 | 변경 |
|---|---|
| `Dockerfile` | 신규 (3절) |
| `docker-compose.yml` | 신규 (5절) |
| `.dockerignore` | 신규 — `.venv`·`.git`·`*.db`·`.streamlit`·도구 캐시·`.claude`·`.superpowers`·`.ua` |
| `.github/workflows/build.yml` | 신규 (8절) |
| `docs/how-to/2026-09-16-homeserver-deploy.md` | 신규 (9.1) |
| `docs/how-to/2026-09-16-auth-reseed.md` | 경로 정정 (9.2) |
| `README.md` | 컨테이너 절 (9.2) |
| `docs/superpowers/specs/2026-09-16-headless-auth-design.md` | §10.1 경로 확정 (9.2) |
| `src/notebooklm_st/app.py` | 모듈 독스트링 한 문단 (9.3) |

건드리지 않는 것: `services/` 전체, `core/` 전체, `components/` 전체,
`pages/` 전체, `tests/` 전체, `pyproject.toml`, `uv.lock`,
`.streamlit/config.toml`, `run.ps1`, `run.bat`.

---

## 12. 미검증 가정

- **Streamlit 이 `HOME=/data` 아래 정확히 무엇을 쓰는지 확인하지
  않았다.** headless 라 이메일 프롬프트는 뜨지 않는다. 파일이 생기면
  볼륨에 남을 뿐 무해하다.
- **홈서버의 아키텍처·도커 버전·사용자 UID 를 모른다.** 이미지를
  홈서버에서 직접 빌드하므로 아키텍처는 문제되지 않고, UID 는
  `PUID`/`PGID` 로 덮는다. 도커 버전이 아주 낮으면 `tmpfs:` 의 리스트
  표기나 `compose` 서브커맨드가 안 먹을 수 있다.
- **CI 러너에서 dev 그룹 설치가 성공하는지 확인하지 않았다.** dev
  그룹의 `notebooklm-py[browser]` 는 playwright 파이썬 패키지를 끌어
  오지만 브라우저 바이너리는 받지 않는다. R1 이 브라우저 로그인
  테스트를 전부 지웠으므로 테스트가 브라우저를 띄우지 않는다.

---

## 13. 범위 밖

- **`AuthGate` 의 `ok → failed` 전이** — `runner` 가 게이트를 알고 실패
  시 `invalidate()` 를 부르는 것이 정답이다. 코드 변경이므로 이
  릴리스에서 하지 않는다. 그때까지 1절·7절의 서술이 유효하다.
- **GHCR·멀티아치 이미지** — 홈서버에서 직접 빌드하면 레지스트리 인증도
  아키텍처 추측도 필요 없다. 배포 대상이 둘 이상이 될 때 다시 본다.
- **`render()` 반환값 무시**, **`recheck()` 가 락을 쥔 채 네트워크
  프로브**, **`runner.py` 의 넓은 `except`** — 모두 코드 변경이다.
- **`store.now()` 의 timezone-aware 전환** — 저장 형식이 바뀌어 기존
  행과 섞인다. `TZ` 환경변수로 충분하다.
- **진행 중 질의의 재시작 생존** — 7절의 한계를 없애려면 실행 모델을
  바꿔야 한다.
- **인터넷 노출·리버스 프록시·TLS** — 6절에서 명시적으로 배제했다.
