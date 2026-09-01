# notebooklm-st 온보딩 가이드

> 이 문서는 `/understand` 가 만든 지식 그래프(`.ua/knowledge-graph.json`)에서 생성했다.
> 기준 커밋 `38a390fa` · 분석 시각 2026-09-01 · 파일 82개 / 노드 242개 / 엣지 571개

---

## 1. 프로젝트 개요

YouTube 영상 URL과 미리 등록해 둔 질문을 조합해 **NotebookLM(Gemini Notebook)의 근거 기반 답변**을 받아보는 개인용 Streamlit 도구다. 노트북 생성 · 자막 소스 추가 · 질의 · 삭제까지의 반복 작업을 asyncio 로 자동화하고, 실행 이력을 SQLite 에 저장한다.

| 항목 | 값 |
|---|---|
| 이름 | `notebooklm-st` (v0.1.0) |
| 언어 | Python 3.13 (+ markdown, powershell, shell, json, toml, batch) |
| 프레임워크 | Streamlit, notebooklm-py `==0.8.1` (버전 고정), pytest |
| 저장소 | SQLite 파일 1개 — `questions.db` |
| 실행 | `.\run.ps1` → `http://127.0.0.1:8611` |
| 범위 밖 | 다중 사용자, 대화형 후속 질문, 오디오/비디오 아티팩트 생성 |

**README 가 없다.** 도구의 정체를 알려 주는 문서는 한국어 기획서 [`request_spec.md`](../request_spec.md) 이며, 코드를 열기 전 이 문서를 먼저 읽어야 한다. (`CLAUDE.md` 는 빈 파일이다.)

---

## 2. 아키텍처 레이어

파일 레벨 노드 85개가 9개 레이어에 정확히 한 번씩 배정되어 있다. **import 그래프에 역방향 엣지가 0개** — 아래 화살표 방향이 코드로 강제된다.

```
app.py  →  pages/ · components/  →  session.py · services/  →  core/
                                          ↓
                                    SQLite (3 tables) · NotebookLM API
```

| 레이어 | 파일 수 | 설명 |
|---|---|---|
| **앱 진입점** | 3 | `streamlit run` 으로 기동되는 `app.py` 와 `@st.cache_resource` 싱글턴을 묶어 페이지 라우팅과 공용 의존성을 조립하는 최상단 조립부 |
| **UI 레이어** | 11 | 질의·실행 현황·이력·질문 관리·정리 화면과 답변 카드·인증 게이트·진행 표시 컴포넌트 |
| **서비스 레이어** | 8 | NotebookLM HTTP API 호출, SQLite 저장소, `notebooklm login` 자식 프로세스까지 **외부 I/O 를 전담하는 유일한 레이어** |
| **코어 도메인** | 6 | 프로젝트 내부 의존성 없이 순수 함수와 frozen dataclass 만 — URL 파싱, 답변 텍스트 정제, 마크다운 내보내기, 오류 매핑 |
| **데이터 레이어** | 3 | `store.py` 가 생성하는 SQLite 테이블 스키마 (`questions` · `runs` · `answers`) |
| **테스트 레이어** | 27 | `core`·`services`·`pages` 구조를 그대로 미러링한 pytest 스위트 + smoke check |
| **빌드·실행 설정** | 4 | `pyproject.toml`, `.streamlit/config.toml`, `run.ps1`, `run.bat` |
| **개발 도구·거버넌스** | 14 | 브랜치·커밋 규칙 문서, 명령·시크릿 가드 hook, MCP 및 지식 그래프 도구 설정 |
| **문서** | 9 | 원본 제품 사양과 기능별 설계 스펙·구현 계획 |

---

## 3. 핵심 개념 — 이 프로젝트가 내린 다섯 가지 결정

### 3.1 노트북은 일회용이다

`services/nlm.py` 는 영상마다 `tmp-<hex>` 이름의 노트북을 **새로 만들었다가 반드시 버린다.**

```
임시 노트북 생성 → 영상 붙이고 자막 색인 대기(≤120초)
                → 질문마다 앞 대화 삭제 후 질의
                → finally: 노트북 삭제
```

- **왜 매번 새로 만드나** — 노트북당 소스 개수 상한에 닿지 않고, 이전 영상 내용이 섞인 오염된 답변이 나오지 않는다.
- **왜 질문 사이에 대화를 지우나** — 앞 질문의 답이 뒤 질문의 맥락으로 새어 들어가는 것을 막는다.
- **왜 `finally` 인가** — 성공 경로 끝에만 삭제를 두면 실패할 때마다 원격에 쓰레기가 쌓인다. 그래도 남는 것을 위해 정리 화면이 따로 있다.

### 3.2 화면과 실행은 분리되어 있다

Streamlit 은 **상호작용마다 스크립트를 처음부터 다시 실행한다.** 수 분짜리 파이프라인을 화면 함수 안에 두면, 사용자가 페이지를 옮기는 순간 작업이 죽는다.

| 파일 | 역할 |
|---|---|
| `pages/ask.py` | 실행을 **시작만** 하고 즉시 반환 |
| `services/runner.py` | `threading.Thread` 에서 파이프라인을 돌리고, 진행 상황을 레지스트리에 기록, 결과를 SQLite 에 저장 |
| `services/runs.py` | `RunHandle` / `RunRegistry` — 스레드와 화면이 만나는 **유일한 접점**, 잠금으로 보호 |
| `session.py` | 레지스트리를 `@st.cache_resource` 싱글턴으로 감싸 **모든 탭이 같은 인스턴스**를 보게 함 |
| `pages/dashboard.py` | `@st.fragment(run_every="1s")` 로 레지스트리를 1초마다 폴링 |

> **불변 규칙: 백그라운드 스레드는 Streamlit API 를 절대 호출하지 않는다.**
> 호출하면 사용자가 페이지를 이동한 순간 스레드가 중단되어 임시 노트북이 남는다.

### 3.3 이력은 질문을 참조하지 않고 복사한다

`answers` 행에 `question_title` · `question_text` 를 **값으로 복사**해 넣는다 — 외래 키가 아니다.
질문 템플릿을 나중에 고치거나 지워도 과거 이력이 소급해서 바뀌지 않는다.

### 3.4 마이그레이션 경로는 의도적으로 없다

`services/store.py` 는 기대 컬럼과 `PRAGMA table_info` 결과를 비교해 어긋나면 `StaleSchemaError` 로 **즉시 실패**한다. `components/schema_gate.py` 가 앱 기동 직후 이 예외를 받아 "이 파일을 지우고 다시 실행하세요" 라는 안내로 바꾸고 `st.stop()` 한다. 스키마가 바뀌면 DB 파일을 지우는 것이 유일한 해법이다.

### 3.5 자막 없는 영상은 오류가 아니다

`core/errors.py` 는 `notebooklm` 라이브러리 예외를 한국어 문구로 옮기면서 **표시 수준(`info` / `error`)까지 함께 결정**한다. 자막이 없거나 소스로 쓸 수 없는 영상은 도구의 실패가 아니라 그 영상의 성질이므로 `info` 로 안내한다. 라이브러리가 private 으로 올리는 로그인 리다이렉트 예외까지 방어적으로 흡수해 내부 클래스명이 사용자에게 노출되지 않게 막는다.

---

## 4. 가이드 투어 — 12단계

지식 그래프가 BFS 깊이와 fan-in 순위로 도출한 읽기 순서다. 순서대로 따라가면 질문 하나가 끝에서 끝까지 흐르는 경로를 추적할 수 있다.

| # | 단계 | 파일 |
|---|---|---|
| 1 | **제품 기획서 읽기** — 목적·범위·사용 시나리오·예외 처리 | `request_spec.md` |
| 2 | **앱을 띄우는 방법** — 코드보다 먼저 굴려 본다 | `pyproject.toml`, `.streamlit/config.toml`, `run.ps1`, `run.bat` |
| 3 | **진입점과 스키마 게이트** — 파일 순서가 곧 부팅 절차 | `app.py`, `components/schema_gate.py` |
| 4 | **다섯 개 화면 둘러보기** — '시작' 과 '관찰' 이 갈라진 것이 첫 단서 | `pages/*.py` |
| 5 | **코어 순수 도메인 계층** — 위를 절대 import 하지 않는 안쪽 | `core/*.py` |
| 6 | **SQLite 저장소와 세 테이블** | `services/store.py` + `questions`·`runs`·`answers` |
| 7 | **질문 템플릿과 이력 CRUD** | `services/questions.py`, `services/run_history.py` |
| 8 | **NotebookLM 파이프라인의 핵심 트릭** | `services/nlm.py` |
| 9 | **백그라운드 실행과 공유 레지스트리** — 가장 어려운 제약 | `services/runner.py`, `services/runs.py`, `session.py` |
| 10 | **진행 표시와 답변 카드** | `components/run_progress.py`, `components/answer_view.py` |
| 11 | **인증 게이트와 최후 수단 로그인** | `services/auth.py`, `components/auth_gate.py` |
| 12 | **테스트로 흐름 되짚기** | `tests/conftest.py`, `tests/test_components.py`, `scripts/smoke_check.py` |

### 알아 두면 좋은 언어·프레임워크 관용구

- **`@st.cache_resource` vs `@st.cache_data`** — 전자는 프로세스 전역에 하나만 만들어 모든 세션이 공유한다(DB 커넥션, 스레드 간 공유 상태용). 후자는 세션별로 복사된다. 공유 객체이므로 내부 뮤테이션은 `threading.Lock` 으로 직접 지켜야 한다.
- **`@st.fragment(run_every="1s")`** — 페이지 전체가 아니라 그 함수 영역만 주기적으로 다시 그린다. 입력값이 초기화되지 않고, 무거운 상단 로직이 매 초 다시 돌지 않는다.
- **`@dataclass(frozen=True)`** — `__setattr__` 을 막아 불변으로 만들고 `__hash__` 를 자동 생성한다. 값 객체가 스레드와 화면 사이를 오가는 이 앱에서 "누가 어디서 필드를 바꿀까" 걱정을 원천 제거한다.
- **`PRAGMA foreign_keys = ON`** — SQLite 는 외래 키 강제를 **기본으로 끈다.** 커넥션마다 켜 주지 않으면 `ON DELETE CASCADE` 가 동작하지 않고 고아 행이 쌓인다.
- **`sys.executable`** — 자식 파이썬 프로세스를 띄울 때 `"python"` 대신 이걸 쓴다. 가상환경 안에서 PATH 의 `python` 은 전혀 다른 인터프리터일 수 있다.
- **`try/finally`** — 외부 서비스에 자원을 만들어 두는 코드는 정리 로직을 반드시 `finally` 나 contextmanager 에 둔다.
- **`conftest.py` + `autouse=True`** — 테스트가 요청하지 않아도 항상 적용된다. 여기서는 "실제 인증을 절대 타지 않게 막는" 안전장치로 쓴다.

---

## 5. 파일 지도

### 앱 진입점

| 파일 | 복잡도 | 역할 |
|---|---|---|
| `src/notebooklm_st/app.py` | simple | 스키마 게이트 → 화면 5개 `st.navigation` 등록 → 인증 게이트 → 선택된 페이지 실행. 모듈 최상단에서 `main()` 호출 |
| `src/notebooklm_st/session.py` | simple | 앱 전역 싱글턴 3개(SQLite 커넥션, 실행 레지스트리, 인증 게이트) |

### UI 레이어

| 파일 | 복잡도 | 역할 |
|---|---|---|
| `pages/ask.py` | simple | 질의 화면. URL 입력·질문 선택 후 백그라운드 실행을 시작만 하고 반환 |
| `pages/dashboard.py` | simple | 실행 현황. 레지스트리를 1초 fragment 로 폴링 |
| `pages/question_admin.py` | moderate | 질문 템플릿 CRUD. 검증 오류는 `st.error`, 성공 시 `st.rerun` |
| `pages/history.py` | **complex** | 이력 조회·답변 수정·삭제·마크다운 내려받기. 인용 숨기기와 2단계 삭제 확인을 세션 키로 직접 관리 |
| `pages/maintenance.py` | moderate | 남은 `tmp-` 노트북 조회·삭제. 실행 중이면 경고 |
| `components/answer_view.py` | moderate | 답변 카드. 저장 콜백과 항목 ID 가 **둘 다** 있을 때만 편집 상자를 연다 |
| `components/run_progress.py` | simple | 실행 카드(running/failed/done). 완료 시 요약 한 줄만, 상세는 이력 화면으로 |
| `components/auth_gate.py` | simple | 자동 복구 실패 동안에만 재인증 안내 상자를 남긴다 |
| `components/schema_gate.py` | simple | 기동 직후 커넥션을 열어 보고 스키마 불일치면 안내 후 `st.stop()` |

### 서비스 레이어 — 외부 I/O 전담

| 파일 | 복잡도 | 역할 |
|---|---|---|
| `services/nlm.py` | **complex** | NotebookLM 파이프라인. 임시 노트북 생성 → 자막 색인 대기 → 질문별 질의(앞 대화 삭제) → `finally` 삭제. `tmp-` 노트북 조회·삭제도 제공 |
| `services/auth.py` | **complex** | 쿠키 확인 → 무인 복구 → 최후 수단으로 `sys.executable -m notebooklm login` 자식 프로세스. `AuthGate` 가 앱 수명 동안 한 번만 타게 통제 |
| `services/run_history.py` | **complex** | `runs`·`answers` CRUD. 저장·목록·상세·답변 수정·삭제 |
| `services/runner.py` | moderate | 파이프라인을 백그라운드 스레드에서 실행. 모든 실패 경로에서 레지스트리를 실패로 마감 |
| `services/runs.py` | moderate | `RunHandle` 값 객체 + 스레드 안전 `RunRegistry` |
| `services/store.py` | moderate | 커넥션과 전체 스키마 소유. 마이그레이션 없이 즉시 실패 |
| `services/questions.py` | moderate | 질문 템플릿 CRUD. 제목 중복·빈 값을 `ValueError` 로 강제 |

### 코어 도메인 — 순수, I/O 없음

| 파일 | 복잡도 | 역할 |
|---|---|---|
| `core/models.py` | moderate | 불변 값 객체 6종 + 인용 JSON 직렬화. **프로젝트 전체의 데이터 계약** (fan-in 21 로 1위) |
| `core/errors.py` | moderate | 라이브러리 예외 → 한국어 `UserMessage`(문구 + 표시 수준) |
| `core/answer_text.py` | moderate | 인용 번호와 후속 제안 블록 제거. 표시 직전에만 호출, 원문 불변 |
| `core/markdown_export.py` | moderate | 이력 1건 → 마크다운 문서 + 파일명 |
| `core/youtube.py` | simple | `youtu.be` · `watch?v=` · `/shorts/` 세 형태에서 11자 영상 id 추출 |

### 데이터 — SQLite 3테이블

| 테이블 | 내용 |
|---|---|
| `questions` | 재사용할 질문 템플릿 (제목 중복 불가) |
| `runs` | 한 번의 영상 질의 실행 — 원본 URL · video_id · 영상 제목 · 실행 시각 |
| `answers` | 실행별 질문·답변·인용(JSON TEXT)·오류. `runs(id)` 를 `ON DELETE CASCADE` 로 참조 |

---

## 6. 복잡도 핫스팟 — 조심해서 접근할 곳

파일 레벨 노드 85개 중 **complex 15개**(simple 37 · moderate 33). 소스 코드는 그중 4개다.

| 파일 | 왜 어려운가 | 먼저 읽을 것 |
|---|---|---|
| `services/nlm.py` (320줄) | 이 도구의 심장. Protocol 로 라이브러리 경계를 추상화하고, 임시 노트북 수명·대화 격리·`finally` 정리가 한 함수에 얽혀 있다 | `docs/superpowers/specs/2026-08-28-youtube-qa-design.md` |
| `services/auth.py` (237줄) | 4단계 인증 폴백 + 자식 프로세스 + 스레드 잠금. 실패 경로가 가장 많다 | `tests/services/test_auth.py` |
| `pages/history.py` (169줄) | 인용 숨기기·편집 잠금·2단계 삭제 확인이 Streamlit 세션 키로 얽혀 있다. 위젯 키를 만든 뒤 건드리면 예외가 나는 제약이 설계를 지배한다 | `docs/superpowers/specs/2026-08-31-history-management-design.md` |
| `services/run_history.py` (161줄) | 행↔모델 변환 + CASCADE 삭제 + 답변 부분 수정 | `tests/services/test_run_history.py` |

**연결 중심(fan-in) 상위** — 고치면 파급이 큰 곳:
`core/models.py` (21) → `session.py` (12) → `services/store.py` (12) → `services/runs.py` (6) → `services/nlm.py` (5)

**의존이 가장 많은 곳(fan-out)** — 전체 흐름을 조립하는 곳:
`pages/history.py` (10) · `services/runner.py` (10) · `app.py` (9) · `pages/ask.py` (8)

나머지 complex 11개는 `docs/superpowers/` 의 설계 스펙·구현 계획 7개와 대형 테스트 4개(`test_components.py` 587줄, `test_nlm.py` 379줄, `test_auth.py` 267줄, `test_history.py` 263줄)다. **설계 스펙은 "왜 이렇게 만들었나" 의 정본**이므로, 해당 영역 코드를 고치기 전에 짝이 되는 스펙을 먼저 읽는 편이 빠르다.

---

## 7. 처음 30분 체크리스트

1. `request_spec.md` 를 읽는다 (10분)
2. `.\run.ps1` 로 앱을 띄우고 `http://127.0.0.1:8611` 접속
3. 질문 관리에서 질문을 하나 등록한다
4. 질의 화면에서 영상 하나에 그 질문을 던지고, 실행 현황 → 이력 순으로 결과를 따라간다
5. `uv run pytest` 로 테스트를 돌려 본다
6. 투어 3 → 8 → 9 순서로 `app.py` · `nlm.py` · `runner.py` 를 읽는다

**작업 규칙**은 `.claude/rules/` 에 있다 — 브랜치 전략(`develop` 에서 작업, `push`/PR 은 사람이), 커밋 규약(gitmoji + Conventional Commits, 한국어 제목 ≤50자), Streamlit 구현 컨벤션.
