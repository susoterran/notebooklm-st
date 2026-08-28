# YouTube 영상 질의응답 도구 기획서

- **작성일**: 2026-08-28
- **상태**: 설계 승인 완료 (구현 계획 수립 전)
- **원본 아이디어 메모**: `request_spec.md`

---

## 1. 개요

### 1.1 목적

YouTube 영상 URL과 미리 저장해 둔 질문을 조합해, NotebookLM의 근거 기반
답변을 받아보는 개인용 로컬 도구를 만든다.

### 1.2 배경

자주 쓰는 질문("핵심 주장 3가지 정리", "발표자의 결론은?" 등)을 매번
타이핑하는 대신 등록해 두고 선택만 하면 되도록 한다. 영상마다 NotebookLM
웹 UI에서 노트북을 만들고 소스를 붙이는 반복 작업을 자동화하는 것이
핵심이다.

### 1.3 범위

**포함**

- 단일 YouTube 영상에 대한 1회성 질의응답
- 한 영상에 저장된 질문 여러 개를 골라 순차 실행
- 질문 템플릿 등록·조회·수정·삭제
- 답변에 딸린 인용 구절 표시
- 실행 이력 저장 및 재조회
- 남은 임시 노트북 정리

**제외**

- 다중 사용자 지원
- 대화형 후속 질문 — 선택한 질문들은 서로 문맥을 잇지 않는다(6.4 참조)
- 오디오·비디오 등 NotebookLM 스튜디오 아티팩트 생성
- YouTube 외 소스(일반 웹페이지, PDF, 텍스트 파일)
- 원격 배포·외부 노출

### 1.4 아이디어 메모에서 바뀐 점

| 항목 | 메모 | 확정 | 근거 |
|---|---|---|---|
| 질문 실행 단위 | 1회 1개 | 다중 선택 후 순차 실행 | 대기 시간의 대부분이 노트북 생성과 자막 인덱싱이다. 한 번 치른 비용을 여러 답변에 나눈다 |
| 결과 보존 | 미결 | SQLite 이력 저장(F-12를 MVP로 승격) | 질문 CRUD용 DB가 이미 있어 추가 비용이 작고, 세션이 끊겨도 답변이 남는다 |
| 인용 표시 | 선택(4단계) | MVP 포함(F-11 승격) | `AskResult.references`에 이미 실려 온다. 추가 API 호출이 없다 |
| 임시 노트북 정리 | 권장 | 수동 버튼 + 잔존 개수 경고 | 앱 시작 시 자동 삭제는 다른 창에서 진행 중인 작업을 지울 위험이 있다 |
| 파일 구성 | 평면 3파일 | src 레이아웃 계층 분리 | `.claude/rules/streamlit-implement.md` 준수 |

---

## 2. 사용 시나리오

1. 사용자가 브라우저에서 도구를 연다.
2. YouTube URL을 붙여넣는다. 형식이 맞지 않으면 실행 버튼이 막힌다.
3. 저장된 질문 목록에서 물어볼 질문을 하나 이상 고른다.
4. `실행`을 누른다.
5. 진행 표시가 단계별로 갱신된다: 노트북 생성 → 자막 인덱싱 → 질문 1/3
   → 질문 2/3 → …
6. 질문마다 답변 카드가 쌓인다. 각 카드에는 답변 본문과 접이식 인용
   목록이 있다.
7. 결과는 자동으로 이력에 저장된다. 나중에 `이력` 페이지에서 다시 본다.
8. 필요하면 `질문 관리`에서 질문을 추가·수정·삭제한다.
9. 비정상 종료로 임시 노트북이 남으면 `정리` 페이지가 개수를 알리고,
   사용자가 확인하면 일괄 삭제한다.

---

## 3. 기능 요구사항

| ID | 기능 | 설명 | 단계 |
|---|---|---|---|
| F-01 | YouTube URL 입력 | 단일 영상 URL. 형식 검증을 통과해야 실행 가능 | MVP |
| F-02 | 질문 다중 선택 | 저장된 질문 목록에서 1개 이상 선택 | MVP |
| F-03 | 질의 실행 | 노트북 생성 → 소스 추가 → 선택 질문 순차 실행 → 노트북 삭제 | MVP |
| F-04 | 답변 출력 | 질문별 답변 카드 표시 | MVP |
| F-05 | 질문 조회 | 저장된 질문 목록 표시 | MVP |
| F-06 | 질문 추가 | 새 질문 등록 | MVP |
| F-07 | 질문 수정 | 기존 질문 내용 변경 | MVP |
| F-08 | 질문 삭제 | 질문 제거 | MVP |
| F-09 | 진행 상태 표시 | 단계별 진행 상황 표시 | MVP |
| F-11 | 인용 출처 표시 | 답변별 인용 번호와 원문 구절 | MVP |
| F-12 | 결과 이력 저장 | 실행·답변 저장 및 재조회 | MVP |
| F-10 | 임시 노트북 정리 | 잔존 개수 경고 + 확인 후 일괄 삭제 | 3단계 |

ID는 원본 메모와 대응시키기 위해 유지했다. 표의 순서는 구현 순서를
따른다.

---

## 4. 비기능 요구사항

- **응답 시간**: 자막 인덱싱 때문에 수십 초가 걸릴 수 있다. 즉시 응답을
  전제하지 않고 대기 UI를 반드시 제공한다. 소스 대기 상한은 120초다.
- **인증**: 최초 1회 `uv run notebooklm login`으로 로컬에 쿠키를 저장한다.
  이후 별도 로그인 절차가 없다.
- **가용성**: 개인용이므로 무중단 요건이 없다. 필요할 때 실행한다.
- **보안**: 로컬에서만 동작하며 외부에 노출하지 않는다(127.0.0.1 바인딩).
  쿠키 파일과 `*.db`는 버전 관리에서 제외한다.
- **동시성**: 1인 1창 사용을 전제한다. 여러 창에서 동시에 실행하는 상황은
  막지 않되 보장하지도 않는다.

---

## 5. 기술 구성

### 5.1 스택

| 구분 | 선택 | 선정 이유 |
|---|---|---|
| UI | Streamlit | 다중 선택·진행 표시·페이지 전환이 기본 제공 |
| 언어 | Python 3.13 | 프로젝트 규칙 고정값 |
| 패키지 관리 | uv | 프로젝트 규칙 고정값. 현재 PC에 미설치이므로 1단계에서 설치 |
| NotebookLM 연동 | notebooklm-py **0.8.1 고정** | 비공식 API라 마이너 업데이트로도 깨질 수 있다 |
| 저장소 | SQLite | 파일 1개, 서버 불필요. 데이터 규모가 작다 |
| 검증 도구 | ruff, mypy, pytest | 프로젝트 규칙 고정값 |

의존성 설치:

```bash
uv add "notebooklm-py[browser]==0.8.1" streamlit
uv run playwright install chromium
uv run notebooklm login
```

`[browser]` extra가 Playwright를 끌어오고, `playwright install chromium`이
로그인 창을 띄울 브라우저를 내려받는다(수백 MB).

### 5.2 검증된 외부 API (notebooklm-py 0.8.1)

아래는 배포판 소스를 직접 확인한 시그니처다. 추측이 아니다.

| 호출 | 시그니처 | 비고 |
|---|---|---|
| 클라이언트 | `NotebookLMClient.from_storage()` | async context manager로 쓰는 것이 정식 경로 |
| 노트북 생성 | `notebooks.create(title) -> Notebook` | |
| 소스 추가 | `sources.add_url(notebook_id, url, *, wait=False, wait_timeout=120.0, title=None) -> Source` | YouTube URL을 자동 감지한다 |
| 질의 | `chat.ask(notebook_id, question, source_ids=None, conversation_id=None) -> AskResult` | `conversation_id`를 비우면 **직전 대화를 이어간다** |
| 대화 삭제 | `chat.delete_conversation(notebook_id, conversation_id) -> None` | 다음 `ask`가 새 대화로 시작하게 만드는 유일한 방법 |
| 노트북 삭제 | `notebooks.delete(notebook_id) -> None` | **멱등적** — 이미 없는 노트북을 지워도 성공한다 |
| 노트북 목록 | `notebooks.list() -> list[Notebook]` | 최근 조회 순 |

`AskResult` 주요 필드: `answer`, `conversation_id`, `turn_number`,
`is_follow_up`, `references`.

`ChatReference` 주요 필드: `citation_number`(답변 본문의 `[N]` 마커와
대응), `cited_text`(자막 원문 구절), `score`(0.0~1.0), `source_id`,
`start_char`/`end_char`.

라이브러리가 영상 ID를 뽑아내는 URL 형식: `watch?v=`, `youtu.be/`,
`shorts/`, `embed/`, `live/`, `v/`, `m.youtube.com`, `music.youtube.com`.
입력 검증기는 이 범위에 맞춘다.

### 5.3 디렉터리 구조

```
pyproject.toml
src/notebooklm_st/
├── app.py                    # st.navigation 페이지 등록만
├── pages/
│   ├── ask.py                # 질의
│   ├── question_admin.py     # 질문 관리
│   ├── history.py            # 이력
│   └── maintenance.py        # 임시 노트북 정리
├── components/
│   ├── answer_view.py        # 답변 + 인용 렌더
│   └── run_progress.py       # st.status ↔ 진행 콜백 어댑터
├── services/
│   ├── nlm.py                # NotebookLM 파이프라인 (asyncio)
│   └── store.py              # SQLite CRUD
└── core/
    ├── models.py             # frozen dataclass
    ├── youtube.py            # URL 검증·정규화 (순수 함수)
    └── errors.py             # 예외 → 사용자 메시지 (순수 함수)
tests/                        # 위 구조를 미러링
```

---

## 6. 아키텍처

### 6.1 실행 모델 — Streamlit과 asyncio를 잇는 방식

이 프로젝트의 핵심 난제다. Streamlit은 위젯 조작마다 스크립트를 위에서
아래로 재실행하는 동기 모델이고, notebooklm-py는 asyncio 기반이며
**클라이언트가 생성된 이벤트 루프에 묶인다**(`_loop_affinity.py`,
`assert_bound_loop()` — 다른 루프에서 쓰면 예외가 난다).

**채택: 실행 버튼 한 번에 `asyncio.run()` 한 번.**

```python
result = asyncio.run(nlm.run_pipeline(url, questions, on_progress))
```

파이프라인 전체(클라이언트 생성 → 노트북 생성 → 소스 추가 → 질문 N개 →
노트북 삭제)가 이 한 번의 호출 안에서 끝난다.

- 이벤트 루프가 Streamlit 스크립트와 **같은 스레드**에서 돌기 때문에,
  파이프라인이 부르는 진행 콜백 안에서 `st.status`를 갱신하면 화면에
  그대로 전달된다. 블로킹이어도 단계별 진행 표시가 된다.
- 클라이언트를 `st.session_state`나 `@st.cache_resource`에 **보관하지
  않는다.** 재실행마다 새 루프가 생기므로 보관된 클라이언트는 다음
  재실행에서 죽는다. 매번 새로 만들고 버리는 편이 옳다.
- 대가: 실행 중에는 그 탭이 묶이고 취소 버튼을 만들 수 없다. 1인용
  도구에서 감수할 만한 값으로 판단했다.

**기각한 대안**

- *백그라운드 스레드 + 폴링*: 취소 버튼과 살아있는 UI를 얻지만, 스레드에서
  `session_state`를 건드릴 때의 `ScriptRunContext` 경고와 경합, 테스트
  복잡도를 치러야 한다.
- *단계별 분할 실행*: 루프 바인딩 제약 때문에 사실상 동작하지 않는다.

### 6.2 계층 경계

- `core/`는 순수 계산만 한다. I/O도 Streamlit도 없다.
- `services/`는 외부 I/O를 담당하되 **`import streamlit`을 하지 않는다.**
  진행 상황은 `on_progress: Callable[[str], None]` 콜백으로 밖에 알린다.
- `components/run_progress.py`가 그 콜백을 `st.status`에 연결한다. UI
  의존성이 이 파일 안쪽에만 머문다.
- `pages/`는 호출과 렌더만 한다. 비즈니스 로직을 두지 않는다.

이 경계 덕분에 `services/nlm.py`를 Streamlit 없이 pytest로 검증할 수 있다.

### 6.3 질의 파이프라인

```python
async def run_pipeline(url, questions, on_progress, client_factory=...):
    async with client_factory() as client:
        notebook = await client.notebooks.create(f"tmp-{uuid4().hex[:8]}")
        try:
            await client.sources.add_url(notebook.id, url,
                                         wait=True, wait_timeout=120.0)
            previous_conversation = None
            for question in questions:
                if previous_conversation is not None:
                    await client.chat.delete_conversation(
                        notebook.id, previous_conversation)
                result = await client.chat.ask(notebook.id, question.text)
                previous_conversation = result.conversation_id
                # 답변 수집
        finally:
            await client.notebooks.delete(notebook.id)
```

```
[URL + 질문 N개]
      ↓
노트북 생성   notebooks.create("tmp-xxxxxxxx")
      ↓
소스 추가     sources.add_url(url, wait=True)   ← 자막 없으면 여기서 실패
      ↓
질문 1        chat.ask(...)
질문 2        delete_conversation → chat.ask(...)      질문마다 독립 대화
질문 N        delete_conversation → chat.ask(...)
      ↓
노트북 삭제   notebooks.delete()   ← 성패와 무관하게 항상 실행
```

**노트북을 매번 새로 만들고 지우는 이유**: 노트북당 소스 개수 상한에
도달하지 않고, 이전 영상 내용이 섞인 오염된 답변이 나오지 않으며, 소스
단위 삭제 API의 존재 여부를 확인할 필요가 없다.

**부분 실패 허용**: 질문 하나가 실패해도 그 항목에만 오류를 담고 다음
질문으로 넘어간다. 인덱싱 비용을 이미 치렀으므로 전부 버릴 이유가 없다.

**정리 보장**: `notebooks.delete`가 멱등적이므로 `finally`에서 안전하게
부를 수 있다. 다만 프로세스가 강제 종료되면 `finally`가 돌지 않으므로
F-10이 안전망 역할을 한다.

### 6.4 대화 격리

`chat.ask`에 `conversation_id`를 넘기지 않으면 라이브러리는 **그 노트북의
가장 최근 대화를 이어간다.** 즉 아무 조치 없이 질문 3개를 연속으로 물으면
2번 답변이 1번 답변을 문맥으로 삼고, 3번은 1·2번을 삼는다.

선택한 질문들은 서로 독립적인 템플릿이므로, 앞 답변이 뒤 답변을 물들이지
않는 편이 예측 가능하다. 따라서 **두 번째 질문부터는 직전 대화를 삭제한 뒤
묻는다.** 라이브러리 문서가 명시한 유일한 방법이다. 첫 질문은 노트북이
갓 생성된 상태라 이어갈 대화가 없어 자동으로 새 대화가 된다.

비용은 질문당 `delete_conversation` 호출 1회다.

### 6.5 임시 노트북 수명

임시 노트북 제목에는 `tmp-` 접두어를 붙여 정리 기능이 대상을 식별할 수
있게 한다. 정리는 `notebooks.list()`에서 제목이 `tmp-`로 시작하는 것만
고른다.

정리는 **자동으로 하지 않는다.** 앱 시작 시 일괄 삭제하면 다른 창에서
진행 중인 실행의 노트북까지 지울 수 있다. 대신 잔존 개수를 화면에 알리고,
사용자가 버튼을 눌러 확인했을 때만 삭제한다.

---

## 7. 데이터 모델

```sql
CREATE TABLE questions (
    id         INTEGER PRIMARY KEY,
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE runs (
    id         INTEGER PRIMARY KEY,
    url        TEXT NOT NULL,
    video_id   TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE answers (
    id            INTEGER PRIMARY KEY,
    run_id        INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    answer        TEXT,
    citations     TEXT,
    error         TEXT
);
```

- 이력을 `runs`와 `answers`로 나눈 이유: 한 번 실행에 답변이 여러 개다.
- `answers.question_text`는 **질문 텍스트의 스냅샷**이다. `questions.id`
  외래키를 쓰면 질문을 수정하거나 지웠을 때 과거 이력이 무의미해진다.
- `citations`는 `[{"n": 1, "text": "...", "score": 0.82}, ...]` 형태의
  JSON 문자열로 저장한다. 인용은 값이지 핸들이 아니므로 정규화할 이유가
  없다.
- `answers.answer`와 `answers.error`는 배타적이다. 성공한 항목은 `error`가
  NULL이고, 실패한 항목은 `answer`가 NULL이다.
- 파일 위치는 프로젝트 루트의 `questions.db`이며 `.gitignore` 대상이다.

---

## 8. 화면 구성

`st.navigation`으로 4개 페이지를 등록한다.

### 8.1 질의

- YouTube URL 입력란 (형식 오류 시 실행 버튼 비활성)
- 질문 다중 선택 위젯 (하나도 고르지 않으면 실행 버튼 비활성)
- 실행 버튼
- 진행 표시 영역 (`st.status` — 현재 단계와 `질문 2/3` 형태의 진척)
- 답변 카드 N개

**답변 카드** = 질문 제목 + 답변 본문(마크다운) + `인용 N건` 접이식 영역.
접이식 안에는 항목마다 `[번호] 원문 구절`을 나열한다.

### 8.2 질문 관리

- 질문 목록
- 추가 입력란 + 등록 버튼
- 항목별 수정 / 삭제 버튼

### 8.3 이력

- 실행 목록 (영상 URL, 실행 시각, 답변 개수)
- 항목을 펼치면 그 실행의 답변 카드들을 질의 화면과 같은 형태로 표시

### 8.4 정리

- 잔존 `tmp-` 노트북 개수 표시
- 목록과 일괄 삭제 버튼 (확인 후 실행)

---

## 9. 오류 처리

`core/errors.py`가 라이브러리 예외를 사용자 메시지로 변환한다. 순수
함수이므로 단위 테스트로 전수 검증할 수 있다.

| 예외 | 표시 | 성격 |
|---|---|---|
| `SourceAddError` · `SourceProcessingError` | "자막이 없거나 소스로 쓸 수 없는 영상입니다" | 오류가 아닌 정상 결과로 취급(`st.info`) |
| `SourceTimeoutError` | "인덱싱이 120초 안에 끝나지 않았습니다. 잠시 후 다시 시도하세요" | 재시도 안내 |
| `AuthError` · `HeadlessLoginRequiredError` | "인증이 만료되었습니다. 터미널에서 `uv run notebooklm login`을 다시 실행하세요" | |
| `RateLimitError` | "요청 한도를 초과했습니다. 잠시 후 다시 시도하세요" | |
| `NotebookLimitError` | "노트북 개수 상한에 도달했습니다. 정리 페이지에서 임시 노트북을 삭제하세요" | |
| `NetworkError` · `RPCTimeoutError` | "네트워크 오류가 발생했습니다" | |
| `ChatError` · `ChatResponseParseError` | 해당 질문만 실패로 표시하고 나머지 질문을 계속 진행 | 부분 실패 |
| 잘못된 URL 형식 | 요청 전 입력 단계에서 차단 | |

원칙:

- 예외를 화면에 그대로 노출하지 않는다. 항상 `st.error`/`st.info`로
  변환한다.
- 어떤 경로로 실패하든 임시 노트북 삭제를 먼저 하고 오류를 표시한다.
- `except Exception:`을 쓰지 않는다. 위 표의 구체적 예외만 잡고, 예상 못 한
  예외는 그대로 올려 보내 Streamlit이 표시하게 둔다 — 조용히 삼키는
  것보다 낫다.

---

## 10. 테스트 전략

| 대상 | 방식 |
|---|---|
| `core/youtube.py` | 순수 단위 테스트. 8가지 URL 형식과 거부 케이스 |
| `core/errors.py` | 예외 인스턴스 → 메시지 매핑 전수 검증 |
| `services/store.py` | 임시 파일 DB로 CRUD·이력 저장 검증 |
| `services/nlm.py` | 가짜 클라이언트를 `client_factory`로 주입해 **호출 순서**, **`finally` 삭제**, **부분 실패**, **대화 격리**를 검증 |
| `pages/` | `AppTest`로 렌더와 상호작용 |

- 실제 네트워크를 타는 테스트는 만들지 않는다.
- 진행 콜백은 호출 기록을 남기는 가짜 함수로 검증한다.
- 버그를 고칠 때는 먼저 재현하는 실패 테스트를 쓴다.

작업 완료 전 다음 4개가 전부 통과해야 한다.

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

---

## 11. 제약사항 및 리스크

- **비공식 API 의존**: notebooklm-py는 Google이 문서화하지 않은 내부
  엔드포인트를 쓴다. 예고 없이 멈출 수 있으므로 버전을 `0.8.1`로 고정하고,
  올릴 때는 동작을 다시 확인한다.
- **자막 의존**: NotebookLM은 영상이 아니라 자막을 읽는다. 자막 품질이
  답변 품질을 좌우한다.
- **약관**: 자동화 접근은 Google 약관상 회색지대다. 개인 용도의 소량
  사용으로 제한한다.
- **답변 정확도**: 인용이 붙어도 오류가 있을 수 있다. 중요한 내용은 원본
  영상으로 확인한다.
- **임시 노트북 누적**: 프로세스가 비정상 종료되면 정리되지 않은 노트북이
  남는다. F-10으로 대응한다.
- **실행 중 탭 점유**: 채택한 실행 모델의 대가다. 실행 중에는 그 탭에서
  다른 조작을 할 수 없고 취소도 되지 않는다.
- **Playwright 설치 부담**: 로그인 한 번을 위해 Chromium을 내려받아야
  한다. 부담이 크면 `notebooklm login --browser-cookies chrome`으로 이미
  로그인된 브라우저의 쿠키를 읽는 경로가 대안으로 있다.

---

## 12. 개발 단계

### 1단계 — 셋업과 동작 확인

- `uv` 설치(`winget install astral-sh.uv`), `git init`, `uv init`
- 의존성 추가와 `notebooklm login`
- `services/nlm.py`를 스크립트로 실행해 **실제 영상 1개**에 대해
  생성 → 인덱싱 → 질의 → 삭제가 끝까지 도는지 확인
- 13장의 실측 항목을 여기서 확정한다

### 2단계 — MVP

F-01 ~ F-09, F-11, F-12 구현. 이 시점부터 실사용 가능하다.

### 3단계 — 안정화

F-10 정리 기능, 예외 메시지 다듬기.

---

## 13. 1단계에서 실측으로 확정할 항목

추측으로 채우지 않고 실제로 돌려 보고 정하는 것들이다.

1. **자막 없는 영상이 던지는 예외의 정확한 종류.** `SourceAddError`인지
   `SourceProcessingError`인지, 아니면 소스는 붙되 답변이 비어서 오는지.
   9장 표의 첫 줄은 이 결과에 따라 확정한다.
2. **`ChatReference.cited_text`의 실제 길이와 유용성.** 라이브러리 문서에
   "블록의 일부만 담길 수 있다"는 언급이 있다. 너무 짧아 쓸모가 없으면
   인용 표시 형식을 다시 정한다.
3. **인덱싱 실소요 시간.** 120초 상한이 적절한지 확인하고 필요하면
   조정한다.
4. **`delete_conversation` 후 `ask`가 실제로 새 대화를 시작하는지.**
   6.4의 전제를 실측으로 확인한다.
