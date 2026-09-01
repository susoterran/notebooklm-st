# notebooklm-st

YouTube 영상 하나에 미리 등록해 둔 질문들을 던져, NotebookLM 의 **자막 근거 기반 답변**을 한 번에 받아 오는 로컬 Streamlit 도구입니다.

## 소개

영상을 볼 시간은 없는데 내용은 알아야 할 때, 매번 NotebookLM 에 들어가 노트북을 만들고 영상을 붙이고 같은 질문을 반복해서 입력하는 작업을 자동화합니다.

URL 하나와 질문 목록을 넣으면 다음을 대신 처리합니다.

1. 임시 노트북 생성 → 2. 영상 자막을 소스로 추가하고 인덱싱 대기 → 3. 질문마다 질의(앞 대화를 끊어 답변이 서로 물들지 않게 함) → 4. 임시 노트북 삭제 → 5. 결과를 SQLite 에 저장

질의는 백그라운드 스레드에서 돌기 때문에 **페이지를 옮기거나 창을 닫아도 실행이 계속됩니다.**

**개인용 로컬 도구입니다.** 서버는 `127.0.0.1` 에만 바인딩되며, 다중 사용자·대화형 후속 질문·오디오 생성은 범위 밖입니다.

## 요구사항

| 항목 | 값 | 근거 |
|---|---|---|
| Python | 3.13 이상 | `pyproject.toml` `requires-python` |
| 패키지 매니저 | [uv](https://docs.astral.sh/uv/) | `run.ps1` 이 `uv` 를 요구 |
| 주요 의존성 | `notebooklm-py[browser]==0.8.1`, `streamlit>=1.62.0` | `pyproject.toml` |
| 계정 | 구글 계정 (NotebookLM 접근 권한) | 첫 실행 시 브라우저 로그인 |

`[browser]` extras 가 브라우저 로그인용 크로미움을 함께 설치합니다.

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

접속 주소는 **http://127.0.0.1:8611** 입니다. 주소와 포트의 정본은 `.streamlit/config.toml` 이며, 실행 스크립트가 이 파일을 읽어 안내합니다.

### 첫 실행 — 인증

로그인 화면은 없습니다. 앱이 뜨면 저장된 인증을 먼저 확인하고, 없거나 만료됐으면 **크로미움 창이 자동으로 열립니다.** 구글 로그인을 마치면 앱이 이어서 진행합니다. 터미널 입력은 필요 없습니다.

자동 복구에 실패하면 화면에 재인증 버튼이 나타납니다. 터미널에서 직접 로그인할 수도 있습니다.

```bash
uv run notebooklm login
```

### 사용 순서

1. **질문 관리** 화면에서 질문 템플릿을 먼저 등록합니다. (제목은 중복 불가)
2. **질의** 화면에서 YouTube URL 을 입력하고 질문을 선택한 뒤 실행합니다.
3. **실행 현황** 화면에서 진행 상황을 봅니다. (1초마다 자동 갱신)
4. **이력** 화면에서 답변을 확인·수정하거나 마크다운으로 내려받습니다.
5. **정리** 화면에서 삭제되지 않고 남은 임시 노트북(`tmp-` 접두사)을 지웁니다.

### 데이터 저장 위치

기본값은 실행 디렉터리의 `questions.db` (SQLite) 입니다. 환경 변수로 바꿀 수 있습니다.

```bash
NOTEBOOKLM_ST_DB=/path/to/my.db uv run streamlit run src/notebooklm_st/app.py
```

> **주의**: 이 프로젝트는 DB 마이그레이션을 지원하지 않습니다(의도된 결정). 스키마가 바뀌면 앱이 연결 시점에 안내와 함께 멈추며, 해결책은 DB 파일을 지우고 새로 만드는 것뿐입니다. 이때 질문 템플릿과 실행 이력이 함께 사라집니다.

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
├── pages/           # 질의 · 실행 현황 · 질문 관리 · 이력 · 정리
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
