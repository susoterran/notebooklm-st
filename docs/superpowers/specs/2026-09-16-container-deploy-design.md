# 컨테이너 전환 설계 — 홈서버 도커 배포

- **작성일**: 2026-09-16
- **상태**: 설계 (구현 계획 수립 전)
- **대상**: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, 배포·재시드
  문서, `README.md`
- **범위**: 릴리스 R2. **배포만 한다.** 앱의 동작은 바꾸지 않는다.
  선행 조건인 R1(무인 갱신 인증 전환)은 완료되었다
  (`docs/superpowers/specs/2026-09-16-headless-auth-design.md`).

---

## 1. 무엇을 하고, 무엇을 하지 않는가

R1 이 앱에서 브라우저 로그인을 걷어내 컨테이너에서 뜰 수 있게 만들었다.
R2 는 **실제로 띄운다.** 이미지를 굽고, 볼륨을 붙이고, 홈서버에서 돌린다.

왜 지금인가. 기획 `request_spec_2.md` 의 요구 5 — 즐겨찾기 채널을
주기적으로 확인해 요약본을 자동 생성한다 — 는 **사람이 데스크톱을 켜
두지 않아도 도는 서버** 없이는 성립하지 않는다. R3~R6 이 얹힐 바닥을
먼저 놓는 릴리스다.

하지 않는 것을 먼저 못박는다. **소스 코드의 동작을 바꾸지 않는다.**
`src/` 아래에서 손대는 것은 사실과 어긋나게 되는 독스트링 한 문단뿐이고
(8.3), 그것도 실행 결과에 영향이 없다.

특히 R1 스펙 §13 이 "R2 로 미룬다" 고 적었던 **`AuthGate` 의
`ok → failed` 전이는 이 릴리스에서도 하지 않는다.** 그 항목은 `runner`
를 고쳐야 하고, 그 순간 이 릴리스는 배포가 아니라 기능 변경이 된다.
결과적으로 R1 이 문서 세 곳에 적어 둔 서술 — 인증 배너는 **기동 시
판정**이며 떠 있는 도중에 세션이 죽으면 앱을 재시작해야 배너를 다시
본다 — 은 R2 에서도 **그대로 참**이다. 되돌릴 문서가 없다.

컨테이너에서 그 재시작은 `docker restart notebooklm-st` 한 줄이고,
`restart: unless-stopped` 덕분에 호스트 재부팅 뒤에도 같은 경로로
회복된다.

---

## 2. 코드를 안 바꾸고 되는 근거

설계에 앞서 코드와 라이브러리를 읽어 다섯 가지를 확인했다. 이 절이
1절의 "동작을 바꾸지 않는다" 를 떠받친다.

| 확인한 것 | 근거 | 설계에 주는 영향 |
|---|---|---|
| `NOTEBOOKLM_HOME` 환경변수로 프로필 위치를 정할 수 있다 | `notebooklm/paths.py:127` | 자격증명이 `HOME`·`/root` 에 묶이지 않는다. 볼륨 하나로 합칠 수 있다 |
| `NOTEBOOKLM_ST_DB` 환경변수로 DB 경로를 정할 수 있다 | `services/store.py` 의 `DB_PATH_ENV_VAR` | 이력이 컨테이너 안이 아니라 볼륨에 남는다 |
| playwright 부재는 L3 에서 `UNAVAILABLE` 로 처리된다 | `notebooklm/_auth/headless_reauth.py:686` — 예외가 아니라 상태값을 돌려준다 | `allow_headless=True`(`services/nlm.py:129`)를 그대로 둬도 컨테이너에서 안전하다. R1 스펙 §2.7 의 미검증 가정이 코드로 닫혔다 |
| `notebooklm/__main__.py` 가 존재한다 | 패키지 파일 | 자격증명 업로드 반입이 부르는 `sys.executable -m notebooklm`(`services/auth.py`)이 컨테이너에서도 그대로 돈다 |
| `server.address` 의 기본값은 비어 있다 | `streamlit/config.py:1016` | 설정을 주지 않으면 전 인터페이스에 바인딩한다. 컨테이너에서 원하는 기본값이다 |

반대로, 환경변수를 **안 주면 깨지는 것** 두 가지도 여기서 나온다.

- `NOTEBOOKLM_ST_DB` 를 안 주면 `store.default_db_path()` 가 현재 작업
  디렉터리(`/app`)에 `questions.db` 를 만든다. 컨테이너를 다시 만드는
  순간 질문 템플릿과 실행 이력이 **통째로 사라진다.**
- `TZ` 를 안 주면 컨테이너 기본 시간대(UTC)가 적용된다. `store.now()`
  는 시간대 정보 없는 로컬 시각을 쓰므로(`services/store.py` 끝),
  이력의 시각이 **9시간 어긋난 채로 저장된다.**

---

## 3. 이미지

멀티스테이지로 굽고, **런타임 단계에는 `uv` 를 넣지 않는다.**

R1 의 Task 6 이 함정 하나를 발견해 기록해 두었다 — `uv sync --no-dev`
로 playwright 를 뺀 뒤에도 그냥 `uv run` 을 쓰면 uv 가 dev 그룹을
조용히 다시 동기화해 playwright 가 돌아온다. 런타임에 uv 가 없으면
그 함정은 **성립할 수 없다.** `--no-dev` 를 매번 기억해서 붙이는
규율 대신 구조로 막는다.

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
# 앱 불변값 — 이미지가 단독으로도 옳게 서도록 여기에 둔다(3.1).
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
줄을 함께** 바꿔야 한다.

**uv 버전은 태그로만 핀하고 정확한 버전을 박지 않는다.** 재현성의
정본은 `uv.lock` 이고 `--frozen` 이 그것을 강제한다. uv 자신의 버전은
잠금 파일이 있는 한 결과에 영향을 주지 않는다.

**`uv sync --frozen`.** `uv.lock` 이 `pyproject.toml` 과 어긋나면 빌드가
**실패한다.** 이미지가 조용히 다른 의존성으로 구워지는 것보다 낫다.

**`.streamlit/config.toml` 은 이미지에 들어가지 않는다.** `COPY` 대상이
`src/` 뿐이라 자동으로 빠진다. 그래서 컨테이너는 데스크톱용
`127.0.0.1` 바인딩을 물려받지 않고, "환경변수가 프로젝트 설정 파일을
덮는가" 라는 **검증하지 않은 전제를 아예 만들지 않는다.** 주소와
포트는 4절의 환경변수가 정한다. 데스크톱은 `config.toml` 을 그대로
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

아래 값의 정본은 **이미지**다(3절의 두 번째 `ENV`). compose 는 이것들을
다시 적지 않는다(3.1).

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
판정이 기동 시 한 번뿐이라는 R1 의 성질이 여기서는 맞물린다 —
재시작이 곧 배너 회복 경로다(1절).

**`read_only: true` + `tmpfs: /tmp`.** 계정 동등 자격증명을 들고 있는
컨테이너라 쓰기 가능한 곳을 `/data` 와 `/tmp` 로만 남긴다. 4절에서
`HOME=/data` 로 모아 둔 것이 이것을 가능하게 한다. 파일 업로더가
걸리면 이 두 줄을 빼면 된다(11절).

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
보인다(R1 how-to 에 이미 적혀 있다). 호스트 자신만 쓰고 Tailscale 등
암호화된 경로로 접근하려면 `127.0.0.1:9004:8611` 로 바꾼다.

---

## 7. 운영 한계 — 정직하게 적어 둘 것

**진행 중인 질의는 재시작에서 유실된다.** 질의는 daemon 스레드에서
돌고(`services/runner.py`), 이력은 파이프라인이 끝난 뒤에 저장된다.
`docker stop`·`docker restart` 하면 그 스레드는 결과를 남기지 못하고
사라진다 — 화면에서도 이력에서도 흔적이 없다.

코드를 바꾸지 않는 이 릴리스에서는 고칠 수 없다. 운영 규칙으로
적는다: **실행 현황이 비어 있을 때 재시작한다.**

**인증 배너는 기동 시 판정이다**(1절). 떠 있는 도중에 세션이 죽으면
`docker restart notebooklm-st` 로 다시 띄워야 배너와 업로더가 보인다.

---

## 8. 문서

### 8.1 새로 쓰는 것

`docs/how-to/2026-09-16-homeserver-deploy.md` — 홈서버 배포 절차서.

- 사전 준비: 호스트 디렉터리 생성과 `chown 1000:1000 ./data`
- 데스크톱에서 `uv run notebooklm login` 으로 자격증명 만들기
- `docker compose up -d --build`
- 업로드 UI 로 자격증명 반입 → `http://<홈서버IP>:9004` 확인
- 기존 데스크톱 `questions.db` 이전(선택)
- **운영 규칙 네 줄**: 인터넷에 내놓지 않는다(6절) · 볼륨에 `:ro` 를
  걸지 않는다(4절) · 실행 중일 때 재시작하지 않는다(7절) · UID 가
  1000 이 아니면 `PUID`/`PGID` 로 덮는다(3.1)
- 9절의 검증 체크리스트

### 8.2 고치는 것

| 파일 | 왜 |
|---|---|
| `docs/how-to/2026-09-16-auth-reseed.md` | 컨테이너 경로가 `/root/.notebooklm/` 로 적혀 있다 → `/data/notebooklm/`, 호스트 쪽은 `./data/notebooklm/`. `docker restart` 에 컨테이너 이름을 넣어 구체화 |
| `README.md` | 컨테이너 실행 절 신설, 접속 주소를 두 갈래(데스크톱 8611 / 홈서버 9004)로, 요구사항 표에 Docker 추가 |
| `docs/superpowers/specs/2026-09-16-headless-auth-design.md` §10.1 | "실제 경로는 R2 가 정한다 … 경로가 정해지면 R2 에서 채운다" 로 비워 둔 자리에 `/data/notebooklm/` 을 채운다 |

### 8.3 코드 파일 한 곳

`src/notebooklm_st/app.py` 의 모듈 독스트링이 이렇게 적고 있다.

> `.streamlit/config.toml` 이 서버를 `127.0.0.1:8611` 에만
> 바인딩하므로 같은 네트워크의 다른 기기에서는 접속할 수 없다.

컨테이너에서는 거짓이다(3.1 — 이미지에 `config.toml` 이 없다).
**독스트링 한 문단만** 고쳐 두 실행 경로를 모두 적는다. 실행 결과에
영향이 없으므로 1절의 "동작을 바꾸지 않는다" 를 지킨다. 이 릴리스가
스스로 만드는 거짓 서술을 남겨 두지 않기 위한 유일한 예외다.

---

## 9. 검증

이미지와 컨테이너 계층이라 `pytest` 가 잡지 못한다. 배포 절차서에
체크리스트로 싣고 릴리스 전에 사람이 한 번 돈다.

| # | 확인 | 통과 기준 |
|---|---|---|
| 1 | `docker compose build` | 성공. `--frozen` 이 잠금 파일 불일치를 여기서 잡는다 |
| 2 | `docker compose run --rm app python -c "import playwright"` | **실패해야 정상.** extras 가 빠졌다는 증거 |
| 3 | `docker compose run --rm app python -c "import datetime; print(datetime.datetime.now())"` | KST. UTC 면 이력이 9시간 어긋난다 |
| 4 | `docker compose ps` | `healthy`. 헬스체크 통과가 곧 Streamlit 기동이다 |
| 5 | 다른 기기에서 `http://<홈서버IP>:9004` | 화면이 뜬다 |
| 6 | 호스트에서 `ls -l data/` | `questions.db` 와 `notebooklm/` 이 `user:` 가 가리키는 UID(기본 `1000:1000`) 소유로 생성된다 |
| 7 | 업로드 UI 로 자격증명 반입 | 배너가 사라진다. `read_only: true` 아래서 파일 업로더가 도는지도 함께 확인된다 |
| 8 | `docker compose down && docker compose up -d` | 질문·이력·인증이 보존된다 |

2·3 번은 R1 이 남긴 두 함정(dev 그룹 재동기화, naive 시각)에 대한
회귀 방지다. 이 둘은 조용히 틀리기 때문에 명시적으로 확인한다.

---

## 10. 건드리는 파일

| 파일 | 변경 |
|---|---|
| `Dockerfile` | 신규 (3절) |
| `docker-compose.yml` | 신규 (5절) |
| `.dockerignore` | 신규 — `.venv`·`.git`·`*.db`·`.streamlit`·도구 캐시·`.claude`·`.superpowers`·`.ua` |
| `docs/how-to/2026-09-16-homeserver-deploy.md` | 신규 (8.1) |
| `docs/how-to/2026-09-16-auth-reseed.md` | 경로 정정 (8.2) |
| `README.md` | 컨테이너 절 (8.2) |
| `docs/superpowers/specs/2026-09-16-headless-auth-design.md` | §10.1 경로 확정 (8.2) |
| `src/notebooklm_st/app.py` | 모듈 독스트링 한 문단 (8.3) |

건드리지 않는 것: `services/` 전체, `core/` 전체, `components/` 전체,
`pages/` 전체, `tests/` 전체, `pyproject.toml`, `uv.lock`,
`.streamlit/config.toml`, `run.ps1`, `run.bat`.

---

## 11. 미검증 가정

- **`read_only: true` 아래서 `st.file_uploader` 가 도는지 확인하지
  않았다.** 업로드 내용을 메모리에 두는지 임시 파일을 쓰는지, 쓴다면
  `/tmp` 인지 다른 경로인지 모른다. 검증 7 번이 이것을 잡는다. 깨지면
  `read_only` 와 `tmpfs` 두 줄을 뺀다 — 되돌리는 비용이 낮아서 먼저
  켠 채로 검증한다.
- **`/_stcore/health` 가 이 Streamlit 버전(≥1.63)에서 유효한지 실측하지
  않았다.** 검증 4 번이 잡는다. 없으면 헬스체크를 TCP 연결 확인으로
  낮춘다.
- **Streamlit 이 `HOME=/data` 아래 정확히 무엇을 쓰는지 확인하지
  않았다.** headless 라 이메일 프롬프트는 뜨지 않는다. 파일이 생기면
  볼륨에 남을 뿐 무해하다.
- **홈서버의 아키텍처·도커 버전·사용자 UID 를 모른다.** 이미지를
  홈서버에서 직접 빌드하므로 아키텍처는 문제되지 않고, UID 는
  `PUID`/`PGID` 로 덮는다. 도커 버전이 아주 낮으면 `tmpfs:` 의 리스트
  표기나 `compose` 서브커맨드가 안 먹을 수 있다.

---

## 12. 범위 밖

- **`AuthGate` 의 `ok → failed` 전이** — R1 스펙 §13 이 R2 로 미뤘으나,
  이 릴리스를 배포로 한정하기로 하여 **다시 미룬다.** `runner` 가
  게이트를 알고 실패 시 `invalidate()` 를 부르는 것이 정답이다.
  그때까지 1절·7절의 서술이 유효하다.
- **GitHub Actions** — R1 스펙 §13 의 R2 목록에 있었으나 뺀다. 저장소에
  `.github` 가 아직 없으므로 `ruff`·`mypy`·`pytest` 검증 워크플로는
  다음 릴리스의 독립된 값이다.
- **GHCR·멀티아치 이미지** — 홈서버에서 직접 빌드하면 레지스트리 인증도
  아키텍처 추측도 필요 없다. 배포 대상이 둘 이상이 될 때 다시 본다.
- **`render()` 반환값 무시**(R1 최종 리뷰 M4), **`recheck()` 가 락을 쥔
  채 네트워크 프로브**(M5), **`runner.py` 의 넓은 `except`** — 모두
  코드 변경이다.
- **`store.now()` 의 timezone-aware 전환** — 저장 형식이 바뀌어 기존
  행과 섞인다. `TZ` 환경변수로 충분하다.
- **진행 중 질의의 재시작 생존** — 7절의 한계를 없애려면 실행 모델을
  바꿔야 한다.
- **인터넷 노출·리버스 프록시·TLS** — 6절에서 명시적으로 배제했다.
