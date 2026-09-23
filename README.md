# notebooklm-st

YouTube 영상 하나에 미리 등록해 둔 질문들을 던져, NotebookLM 의 **자막 근거 기반 답변**을 한 번에 받아 오는 로컬 Streamlit 도구입니다.

## 소개

영상을 볼 시간은 없는데 내용은 알아야 할 때, 매번 NotebookLM 에 들어가 노트북을 만들고 영상을 붙이고 같은 질문을 반복해서 입력하는 작업을 자동화합니다.

URL 하나와 질문 목록을 넣으면 다음을 대신 처리합니다.

1. 임시 노트북 생성 → 2. 영상 자막을 소스로 추가하고 인덱싱 대기 → 3. 질문마다 질의(앞 대화를 끊어 답변이 서로 물들지 않게 함) → 4. 임시 노트북 삭제 → 5. 결과를 SQLite 에 저장 → 6. 사람이 확인하고 Outline 에 올리면 로컬에는 링크만 남음

질의는 백그라운드 스레드에서 돌기 때문에 **페이지를 옮기거나 창을 닫아도 실행이 계속됩니다.**

**개인용 도구입니다.** 데스크톱 실행은 `127.0.0.1` 에만 바인딩되고, 홈서버 컨테이너는 홈 LAN 에만 엽니다(인터넷 노출 금지 — 아래 「홈서버 (Docker)」). 다중 사용자·대화형 후속 질문·오디오 생성은 범위 밖입니다.

## 요구사항

| 항목 | 값 | 근거 |
|---|---|---|
| Python | 3.13 이상 | `pyproject.toml` `requires-python` |
| 패키지 매니저 | [uv](https://docs.astral.sh/uv/) | `run.ps1` 이 `uv` 를 요구 |
| 주요 의존성 | `notebooklm-py==0.8.1` (+ 브라우저 로그인용 `[browser]` 는 dev 그룹), `streamlit>=1.63.0` | `pyproject.toml` |
| 계정 | 구글 계정 (NotebookLM 접근 권한) | 첫 로그인은 사람이 CLI 로 한 번 |
| 컨테이너 | Docker Engine + Compose v2 | 홈서버 배포 시에만. `docker-compose.yml` |

`[browser]` extras 는 dev 그룹에 있습니다. `uv sync` 하면 따라오고,
컨테이너 이미지는 `uv sync --no-dev` 로 뺍니다.

## 설치

```bash
git clone <repository-url>
cd notebooklm-st
uv sync
```

`uv sync` 는 `run.ps1` 이 실행 시 자동으로 호출하므로 생략해도 됩니다.

## 사용법

### 빠른 시작 (Windows)

```powershell
.\run.bat
```

`run.bat` 을 더블클릭해도 됩니다. 의존성을 동기화하고 서버를 띄운 뒤, 포트가 열리면 기본 브라우저를 자동으로 엽니다.

### 직접 실행

```bash
uv run streamlit run src/notebooklm_st/app.py
```

```powershell
.\run.ps1                              # 동기화 후 실행
.\run.ps1 -NoSync                      # 동기화 건너뛰기
.\run.ps1 -NoSync -- --server.port 8612  # streamlit 인자 전달
```

데스크톱 접속 주소는 **http://127.0.0.1:8611** 입니다. 주소와 포트의 정본은 `.streamlit/config.toml` 이며, 실행 스크립트가 이 파일을 읽어 안내합니다. 컨테이너는 이 파일을 쓰지 않습니다(아래 「홈서버 (Docker)」).

### 홈서버 (Docker)

```bash
mkdir -p data && sudo chown 1000:1000 data
docker compose up -d --build
```

접속 주소는 **http://<홈서버IP>:9004** 입니다. 컨테이너 안에서는 8611 에서 돌고, `docker-compose.yml` 이 호스트 9004 에 붙입니다.

절차와 운영 규칙은 [홈서버에 배포하기](docs/how-to/2026-09-16-homeserver-deploy.md) 에 있습니다.

> **인터넷에 노출하지 마세요.** 대시보드의 자격증명 업로드 폼은 앱이 외부에 노출되지 않는다는 전제 위에 있습니다.

### 첫 실행 — 인증

로그인 화면은 없습니다. 앱은 브라우저를 띄우지 않습니다.

처음 쓸 때는 터미널에서 한 번 로그인합니다.

```bash
uv run notebooklm login
```

크로미움이 열립니다. 구글 로그인을 마치면 CLI 가 스스로 저장합니다.

앱은 뜰 때 저장된 인증을 확인하고, 요청이 나갈 때마다 토큰과 쿠키를
자동으로 갱신합니다. 이 판정은 **뜰 때 한 번만** 합니다. 갱신으로도
못 살릴 만큼 세션이 죽은 채로 앱이 뜨면 화면에 만료 안내와
**다시 확인** 버튼이 나타나지만, 떠 있는 도중에 세션이 죽으면
배너는 다시 그려지지 않습니다 — 이때는 앱을 재시작해야(컨테이너면
`docker restart notebooklm-st`) 배너를 다시 볼 수 있습니다. 되살리는 절차는
[인증이 만료됐을 때 되살리기](docs/how-to/2026-09-16-auth-reseed.md)
에 있습니다.

### 사용 순서

1. **질문 관리** 화면에서 질문 템플릿을 먼저 등록합니다. (제목은 중복 불가) 이 목록은 **질의와 정리본 지시가 함께 씁니다.**
2. **질의** 화면에서 YouTube URL 을 입력하고 질문을 선택한 뒤 실행합니다.
3. **채널** 화면에서 즐겨찾기 채널을 등록해 두면, **새 영상 확인**으로 아직 요약하지 않은 영상만 모아 볼 수 있습니다. 목록에서 바로 요약을 시작합니다. (기준일 이후 업로드분만 보이며, 채널 피드는 최신 15건까지 줍니다)
4. **실행 현황** 화면에서 진행 상황을 봅니다. (1초마다 자동 갱신)
5. **이력** 화면에서 답변을 확인하고, 제목을 정한 뒤 **Outline 에 저장**합니다. 저장하면 로컬에는 문서명과 링크만 남고 수정·삭제·검색은 Outline 에서 합니다.
6. **정리본** 화면에서 저장된 요약본 여럿을 골라 하나의 글로 정리합니다. 정리 지시는 질문 관리에 등록된 질문 중 하나를 골라 씁니다. 제목은 NotebookLM 이 정리와 함께 지은 주제로 `[정리] <주제>` 가 기본값이며 고쳐 쓸 수 있습니다. 저장하면 Outline 에 문서가 생기며, 정리본은 로컬에 남지 않습니다.
7. **정리** 화면에서 삭제되지 않고 남은 임시 노트북(`tmp-` 접두사)을 지웁니다.

Outline 문서는 메타데이터 리스트로 시작하고 구분선 아래에 답변이
이어집니다.

```markdown
- 제목: '매수' 의견 믿으면 안 되는 이유 | 증권사 리포트 읽는 법
- 채널: 어피티 UPPITY
- 업로드 일자: 2026-08-14
- 영상 URL: https://www.youtube.com/watch?v=j2R_dgayplU

---

## 첫 질문

답변 본문…
```

제목과 영상 URL 은 항상 들어가고, 채널명과 업로드일자는 실행 시점에
yt-dlp 로 가져와 저장해 둔 값이 있을 때만 들어갑니다. 값이 없으면 그
줄 자체가 빠집니다.

질문 원문은 문서에 싣지 않습니다. 이력 화면의 접은 영역에는 그대로
남습니다.

### Outline 연결

| 환경변수 | 필수 | 값 |
|---|---|---|
| `NOTEBOOKLM_ST_OUTLINE_URL` | ✅ | **앱이 붙을** Outline 주소 (예: `http://192.168.0.10:3000`) |
| `NOTEBOOKLM_ST_OUTLINE_TOKEN` | ✅ | API 토큰. scope 는 아래 **API 토큰 발급** 을 보세요 |
| `NOTEBOOKLM_ST_OUTLINE_COLLECTION` | ✅ | 문서를 넣을 컬렉션 ID (**UUID**. 컬렉션 이름이 아닙니다) |
| `NOTEBOOKLM_ST_OUTLINE_PUBLIC_URL` | | **사람이 브라우저로 열** Outline 주소. 비우면 위 주소를 그대로 씁니다 |

필수 셋 중 하나라도 비면 이력 화면의 저장 버튼 자리에 안내가 나옵니다.
앱은 그대로 뜨고 지난 실행도 읽을 수 있습니다. 배포 절차 전체는
`docs/how-to/2026-09-16-homeserver-deploy.md` 에 있습니다.

**API 토큰 발급.** Outline 웹에서 프로필 → **Settings → API Keys → New API Key**.

**Scopes** 칸은 자유 입력이고 **공백으로 구분**합니다. 한 줄로 이렇게 적습니다.

```
documents.create documents.info
```

- 앞의 것은 요약본을 **올릴 때**, 뒤의 것은 정리본이 재료를 **읽을 때** 씁니다. 하나만 넣으면 그쪽 기능만 돌고 다른 쪽이 막힙니다.
- 쉼표로 구분해도 받습니다(`documents.create, documents.info`). 칸 아래 안내문이 "Space-separated scopes…" 라고 알려 줍니다.
- **비워 두면 전체 권한**이 됩니다 — 키를 만든 사용자가 할 수 있는 모든 것이 열립니다. 비우지 마세요.
- 키 값은 만든 직후 **한 번만** 보입니다. 바로 복사해 `NOTEBOOKLM_ST_OUTLINE_TOKEN` 에 넣으세요.

> **저장은 되는데 정리본만 안 된다면 scope 입니다.** 저장만 하던 키(`documents.create` 하나)로 정리를 시작하면 권한 오류(403)가 아니라 **인증 오류(401)** 와 `Authentication required` 가 옵니다. 토큰이 죽은 것처럼 보이지만, 저장이 되고 있다면 토큰은 멀쩡하고 `documents.info` 가 빠진 것입니다. 키를 새로 만들어 바꾸면 됩니다.

**공개 주소는 언제 필요한가.** 앱은 저장할 때 API 를 한 번 부르고, 문서
링크를 문자열로 적어 둡니다. 나중에 그 링크를 여는 것은 **브라우저**이지
앱이 아닙니다. 둘이 같은 주소로 Outline 에 닿을 수 있으면 이 변수는
필요 없습니다.

다른 경우가 있습니다. 예를 들어 Outline 이 `https://wiki.example.com`
으로 서비스되는데 같은 홈서버의 컨테이너가 그 공인 주소로 되돌아 나가지
못하면(NAT 헤어핀), 앱은 호스트 주소로 붙어야 합니다. 그런데 그 호스트
주소에는 사용자의 Outline 세션 쿠키가 없어서 링크로 쓰면 로그인 화면만
나옵니다. 이때 둘을 나눕니다.

```
NOTEBOOKLM_ST_OUTLINE_URL=http://192.168.0.10:4000          # 앱이 붙을 곳
NOTEBOOKLM_ST_OUTLINE_PUBLIC_URL=https://wiki.example.com   # 링크에 적을 곳
```

### 데이터 저장 위치

기본값은 실행 디렉터리의 `questions.db` (SQLite) 입니다. 환경 변수로 바꿀 수 있습니다. 컨테이너는 이미지가 `NOTEBOOKLM_ST_DB=/data/questions.db` 를 정해 두므로 호스트의 `./data/questions.db` 에 남습니다.

```bash
NOTEBOOKLM_ST_DB=/path/to/my.db uv run streamlit run src/notebooklm_st/app.py
```

> **주의**: 이 프로젝트는 DB 마이그레이션을 지원하지 않습니다(의도된 결정). 스키마가 바뀌면 앱이 연결 시점에 안내와 함께 멈추며, 해결책은 DB 파일을 지우고 새로 만드는 것뿐입니다. 이때 질문 템플릿과 실행 이력이 함께 사라집니다. Outline 에 이미 올린 문서는 영향을 받지 않습니다.

### 실계정 스모크 체크

```bash
uv run python scripts/smoke_check.py "https://www.youtube.com/watch?v=..."
```

실제 계정으로 파이프라인을 한 번 돌려 봅니다.

## 프로젝트 구조

```
src/notebooklm_st/
├── app.py           # 진입점. st.navigation 으로 페이지 등록
├── session.py       # @st.cache_resource 로 공유하는 커넥션·레지스트리·인증 게이트
├── pages/           # 질의 · 채널 · 실행 현황 · 질문 관리 · 이력 · 정리본 · 정리
├── components/      # 답변 카드, 인증 게이트, 스키마 게이트, 진행 표시
├── services/        # 외부 I/O — NotebookLM API, SQLite, 인증, 백그라운드 러너
└── core/            # 순수 로직 — URL 파싱, 답변 정제, 마크다운 변환, 오류 매핑, 값 객체
tests/               # src 구조를 미러링
scripts/             # smoke_check.py
docs/                # 온보딩 문서
```

**`core/` 와 `services/` 는 `import streamlit` 을 하지 않습니다.** 덕분에 파이프라인·저장소·URL 파싱이 UI 없이 테스트됩니다.

## 테스트

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

- 테스트 경로는 `pyproject.toml` 의 `testpaths = ["tests"]` 로 고정되어 있어 `uv run pytest` 만으로 전체가 돕니다.
- 외부 네트워크와 DB 는 전부 가짜 객체로 대체되므로 **실제 NotebookLM 계정 없이 돕니다.**
- 화면 동작은 `streamlit.testing.v1.AppTest` 로 검증합니다.
- ruff 는 `line-length = 80`, Google 스타일 독스트링(`D` 규칙)을 강제합니다.
- mypy 는 `core/` 와 `services/` 에 `disallow_untyped_defs` 를 적용합니다.

## 라이선스

TODO: 확인 필요 — 저장소에 `LICENSE` 파일이 없고 `pyproject.toml` 에도 `license` 필드가 없습니다.
