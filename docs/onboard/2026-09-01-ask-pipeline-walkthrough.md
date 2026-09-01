# 영상 질의 — URL 입력에서 답변 저장까지

> 처음 이 프로젝트를 보는 동료를 위한 온보딩 문서. 이 앱의 **주 기능**을 끝에서 끝까지 따라간다.
> 대상 코드: `pages/ask.py` · `services/runner.py` · `services/runs.py` ·
> `services/nlm.py` · `services/run_history.py` · `pages/dashboard.py`
> 작성 2026-09-01 · 기준 커밋 `38a390f`
>
> 인증 부분은 이 흐름의 **6-a 단계**에서 한 번 개입한다. 그 내부는
> [최초 실행 시 인증 과정](2026-09-01-first-run-authentication-flow.md) 문서에서 다룬다.

---

## 0. 30초 요약

YouTube URL 하나 + 미리 등록해 둔 질문 여러 개를 넣으면, NotebookLM 에게 **자막을 근거로 한
답변**을 질문마다 받아 온다.

핵심은 **버튼을 누른 화면과 실제 일하는 코드가 분리되어 있다**는 점이다.

```
[화면 스레드]  실행 버튼 → 스레드 하나 띄우고 즉시 반환 → 다른 페이지로 이동 가능
[작업 스레드]  노트북 생성 → 자막 인덱싱 → 질문 N개 → 노트북 삭제 → DB 저장
[화면 스레드]  1초마다 레지스트리를 읽어 진행 상황 표시
```

질의 한 건이 몇 분 걸리기 때문이다. 화면이 파이프라인에 묶여 있으면 사용자가 페이지를
옮기는 순간 작업이 끊긴다.

---

## 1. 핵심 구성요소와 역할

| # | 구성요소 | 위치 | 역할 |
|---|---|---|---|
| 1 | `ask.render()` | `pages/ask.py:13` | **입력 화면.** URL·질문을 받고 실행을 시작만 한다 |
| 2 | `youtube.is_valid()` | `core/youtube.py:59` | **입력 검증.** 단일 YouTube 영상 URL 인지 판정 |
| 3 | `runner.start_run()` | `services/runner.py:21` | **작업 시작.** 백그라운드 스레드를 띄우고 **즉시** 반환 |
| 4 | `runs.RunRegistry` | `services/runs.py:36` | **상태 공유.** 화면과 작업 스레드가 만나는 유일한 지점. 모든 메서드가 락 안에서 동작 |
| 5 | `runs.RunHandle` | `services/runs.py:16` | 실행 하나의 상태 (`running`/`done`/`failed` · 진행 문구 · 결과) |
| 6 | `runner._work()` | `services/runner.py:76` | **스레드 본체.** 파이프라인을 돌리고 결과·실패를 레지스트리에 남긴다 |
| 7 | `nlm.run_pipeline()` | `services/nlm.py:133` | **실제 작업.** 노트북 생성 → 자막 추가 → 질문 → 삭제 |
| 8 | `nlm._ask_one()` | `services/nlm.py:249` | 질문 하나를 던지고 `AnswerItem` 으로 만든다 |
| 9 | `run_history.save_run()` | `services/run_history.py:13` | **영속화.** 결과를 `runs`+`answers` 테이블에 저장 |
| 10 | `dashboard._render_runs()` | `pages/dashboard.py:24` | **진행 표시.** 1초마다 레지스트리를 폴링하는 프래그먼트 |
| 11 | `errors.to_message()` | `core/errors.py:54` | 라이브러리 예외를 한국어 안내 문구로 변환 |

### 계층 관계

```
pages/ask.py ──▶ services/runner.py ──▶ services/nlm.py ──▶ NotebookLM API
     │                   │                     │
     │                   └──▶ services/run_history.py ──▶ SQLite
     │                   │
     └───────────────────┴──▶ services/runs.py (RunRegistry)  ◀── pages/dashboard.py
```

`services/` 와 `core/` 는 `import streamlit` 을 하지 않는다(프로젝트 규칙). 그래서
파이프라인 전체가 UI 없이 pytest 로 검증된다.

---

## 2. 전체 호출 순서

**세 개의 실행 흐름**이 동시에 존재한다. 이걸 구분하는 게 이 기능을 이해하는 열쇠다.

```
━━━ ① 화면 스레드 (버튼을 누른 순간) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ask.render()                                        pages/ask.py:13
  ├─ session.get_connection()                       session.py:15
  ├─ session.get_registry()                         session.py:25
  ├─ questions.list_questions(connection)           services/questions.py:12
  ├─ st.text_input(...)          → url
  ├─ youtube.is_valid(url)                          core/youtube.py:59
  ├─ st.multiselect(...)         → selected
  ├─ registry.running_count()                       services/runs.py:106
  └─ st.button("실행") 클릭 시:
       └─ runner.start_run(registry, url, selected, db_path)   runner.py:21
            ├─ _threads[:] = [살아 있는 스레드만]      ← 죽은 스레드 정리
            ├─ youtube.extract_video_id(url)
            ├─ registry.create(url, video_id, texts)  runs.py:48
            │    └─ RunHandle(status="running", run_id=8자리 hex)
            ├─ threading.Thread(target=_work, daemon=True)
            └─ thread.start()  ──────┐
                                     │
       └─ st.success("실행을 시작했습니다")   ← 즉시 반환. 화면은 자유
                                     │
━━━ ② 작업 스레드 (백그라운드) ━━━━━━━━━━━━━━━━━━━━┘

_work(...)                                          runner.py:76
  ├─ on_progress = lambda msg: registry.append_progress(run_id, msg)
  │
  ├─ asyncio.run(pipeline(url, questions, on_progress))     nlm.py:133
  │    └─ async with client_factory() as client:            ← ★ 인증 개입 지점
  │         │    NotebookLMClient.from_storage(allow_headless=True)
  │         │
  │         ├─ on_progress("임시 노트북 생성 중")
  │         ├─ client.notebooks.create("tmp-<8자리>")
  │         │
  │         ├─ try:
  │         │    ├─ on_progress("자막 인덱싱 중 (최대 120초)")
  │         │    ├─ client.sources.add_url(nb.id, url, wait=True, wait_timeout=120)
  │         │    ├─ title = source.title or None
  │         │    │
  │         │    └─ for index, question in enumerate(questions, 1):
  │         │         ├─ on_progress(f"질문 {index}/{total}")
  │         │         ├─ if 이전 대화 있음: chat.delete_conversation(...)  ← 격리
  │         │         └─ _ask_one(client, nb.id, question)     nlm.py:249
  │         │              ├─ client.chat.ask(nb.id, question.text)
  │         │              ├─ _to_citations(result.references)  nlm.py:291
  │         │              └─ AnswerItem(...) 반환
  │         │
  │         └─ finally:
  │              └─ client.notebooks.delete(nb.id)      ← 반드시 삭제
  │
  │    → RunResult(url, video_id, items, title)
  │
  ├─ store.connect(db_path)                          store.py:95
  ├─ run_history.save_run(connection, result)        run_history.py:13
  ├─ connection.close()
  └─ registry.finish(run_id, result)                 runs.py:131
                                                     ← 여기서 비로소 "done"

━━━ ③ 폴링 프래그먼트 (1초마다, 화면 스레드) ━━━━━━━━━━━━━━━━━━━━━━

dashboard._render_runs()      @st.fragment(run_every="1s")   dashboard.py:23
  ├─ registry.list_all()      → 핸들 복사본 목록            runs.py:95
  └─ for handle: run_progress.render_run(handle)            run_progress.py:8
       ├─ running → st.info(최신 진행 문구)
       ├─ failed  → st.error / st.info (수준에 따라)
       └─ done    → st.success("완료 — 답변 N건")
```

---

## 3. 단계별 입력 / 출력

### 단계 1 — 화면 진입

| | |
|---|---|
| **호출** | `ask.render()` — `pages/ask.py:13` |
| **입력** | 없음 (Streamlit 이 페이지 전환 시 호출) |
| **출력** | 화면 렌더 |
| **부수효과** | `get_connection()`·`get_registry()` 로 공유 자원 획득, 질문 목록 조회 |

질문이 하나도 없으면 여기서 안내만 하고 **`return` 으로 끝낸다**(`ask.py:34-36`).
URL 입력칸은 그려도 실행할 대상이 없기 때문이다.

### 단계 2 — URL 검증

| | |
|---|---|
| **호출** | `youtube.is_valid(url)` → `extract_video_id(url)` — `core/youtube.py:59, 19` |
| **입력** | 사용자가 입력한 문자열 |
| **출력** | `bool` (내부적으로는 11자리 영상 ID 또는 `None`) |

검증 방식이 꼼꼼하다.

| 검사 | 내용 |
|---|---|
| 스킴 | `http`/`https` 만 |
| 호스트 | `youtube.com`·`www`·`m`·`music`·`youtu.be` — **`hostname` 을 파싱해 비교** |
| 경로 | `/watch?v=`, `youtu.be/<id>`, `/shorts/`, `/embed/`, `/live/`, `/v/` |
| ID 형식 | `^[A-Za-z0-9_-]{11}$` |

호스트를 문자열 포함으로 보지 않고 파싱해서 비교하므로 `evil.com/youtube.com/...` 같은
위장이 통과하지 못한다(`youtube.py:22-24`). 재생목록 파라미터가 붙어 있어도 영상 ID 만 뽑는다.

### 단계 3 — 질문 선택

| | |
|---|---|
| **호출** | `st.multiselect(options=question_list, format_func=...)` — `ask.py:38` |
| **입력** | `list[models.Question]` (DB 에서 읽은 템플릿) |
| **출력** | `list[models.Question]` (선택된 것들) |

`format_func=lambda question: question.title` 로 **객체를 그대로 옵션에 넣고 제목만 표시**한다.
그래서 선택 결과가 문자열이 아니라 `Question` 객체 자체다 — 뒤에서 `question.text` 가 필요하다.

### 단계 4 — 중복 실행 차단

| | |
|---|---|
| **호출** | `registry.running_count()` — `services/runs.py:106` |
| **입력** | 없음 |
| **출력** | `int` (status 가 `running` 인 실행 수) |
| **효과** | 0 보다 크면 안내 표시 + 실행 버튼 `disabled` |

버튼 활성 조건은 `disabled=busy or not (url_ok and selected)` 하나로 정리된다(`ask.py:53`).

### 단계 5 — 실행 시작

| | |
|---|---|
| **호출** | `runner.start_run(registry, url, selected, db_path)` — `runner.py:21` |
| **입력** | 레지스트리, URL, 질문 목록, **DB 경로** |
| **출력** | `runs.RunHandle` (호출자는 사실상 쓰지 않는다) |
| **부수효과** | 레지스트리에 `running` 핸들 등록, 데몬 스레드 시작 |

**DB 커넥션이 아니라 경로를 넘기는 게 핵심이다.** SQLite 커넥션은 만든 스레드에 묶이므로,
작업 스레드가 **자기 커넥션을 따로 연다**(`runner.py:123`).

죽은 스레드 정리도 여기서 한다.

```python
_threads[:] = [thread for thread in _threads if thread.is_alive()]
```

슬라이스 대입인 이유는 `join_all()` 이 **같은 리스트 객체**를 참조하기 때문이다.
`_threads = [...]` 로 재대입하면 다른 객체가 되어 연결이 끊긴다(`runner.py:45-48`).

### 단계 6 — 핸들 생성

| | |
|---|---|
| **호출** | `registry.create(url, video_id, question_texts)` — `runs.py:48` |
| **입력** | URL, 영상 ID, **질문 본문 튜플** |
| **출력** | `RunHandle` 복사본 (`run_id` = `uuid4().hex[:8]`) |

`RunHandle` 만 `frozen=True` 가 아니다(`runs.py:15`). 백그라운드 스레드가 상태를
갱신해야 하기 때문이며, 동시 접근은 레지스트리의 락이 막는다.

레지스트리에서 나가는 값은 **항상 복사본**이다(`_copy()`, `runs.py:173`). `progress`
리스트까지 새로 만든다. 화면이 순회하는 도중에 스레드가 원본을 바꿔도 안전하게 하려는 것이다.

### 단계 6-a — 인증 (파이프라인 진입 직후) ★

| | |
|---|---|
| **호출** | `async with client_factory() as client:` — `nlm.py:161` |
| **입력** | 라이브러리가 관리하는 저장소의 쿠키·토큰 |
| **출력** | 열린 클라이언트 / 또는 예외 |

`default_client_factory()`(`nlm.py:109`)가 `allow_headless=True` 로 클라이언트를 열고,
라이브러리가 필요하면 **토큰 재추출 → 쿠키 회전 → 무인 재인증**을 알아서 시도한다.

여기서 인증이 실패하면 예외가 `_work` 의 `except errors.MAPPED_ERRORS` 로 잡혀,
`to_message()` 가 만든 **"인증이 만료되었습니다. 터미널에서 `uv run notebooklm login` 을
다시 실행하세요."** 가 대시보드 카드에 뜬다(`errors.py:40-43`).

> 앱 기동 시의 인증 게이트와는 별개다. 게이트는 앱이 뜰 때 한 번 돌고, 이 지점은
> **질의를 실행할 때마다** 지나간다. 게이트를 통과한 뒤 시간이 지나 만료됐다면 여기서 걸린다.

### 단계 7 — 임시 노트북 생성

| | |
|---|---|
| **호출** | `client.notebooks.create(f"tmp-{uuid4().hex[:8]}")` — `nlm.py:163` |
| **입력** | `tmp-` 로 시작하는 제목 |
| **출력** | 노트북 객체 (`id`, `title`) |
| **진행 문구** | `"임시 노트북 생성 중"` |

`tmp-` 접두사는 **정리 화면이 이 노트북을 식별하는 표식**이다(`nlm.py:202`
`list_temp_notebooks`). 사용자가 손으로 만든 노트북은 건드리지 않는다.

### 단계 8 — 자막 소스 추가와 인덱싱 대기

| | |
|---|---|
| **호출** | `client.sources.add_url(nb.id, url, wait=True, wait_timeout=120.0)` — `nlm.py:168` |
| **입력** | 노트북 ID, 영상 URL |
| **출력** | 소스 객체 → `title = source.title or None` |
| **진행 문구** | `"자막 인덱싱 중 (최대 120초)"` |
| **소요** | 가장 오래 걸리는 단계 |

`wait=True` 라서 **인덱싱이 끝날 때까지 기다린다.** 자막이 준비되지 않은 상태로 질문하면
근거 없는 답변이 나오기 때문이다.

여기서 얻는 `source.title` 이 **영상 제목**이다. 빈 문자열이면 `None` 으로 바꾼다 —
화면이 `video_id` 로 대신 표시할 수 있게 하려는 것이다(`nlm.py:174-175`).

자막이 없는 영상이면 이 단계에서 예외가 나고, `to_message()` 가 이를 **`info` 수준**으로
분류한다. "자막이 없는 영상은 도구의 오류가 아니라 그 영상의 성질"이기 때문이다
(`errors.py:56-57`).

### 단계 9 — 질문 루프

| | |
|---|---|
| **호출** | `_ask_one(client, nb.id, question)` — `nlm.py:249` |
| **입력** | 열린 클라이언트, 노트북 ID, `models.Question` |
| **출력** | `(models.AnswerItem, 대화 ID \| None)` 튜플 |
| **진행 문구** | `"질문 1/3"`, `"질문 2/3"` … |

루프 한 바퀴가 이렇게 돈다.

```python
for index, question in enumerate(questions, start=1):
    on_progress(f"질문 {index}/{total}")
    if previous_conversation is not None:
        await client.chat.delete_conversation(notebook.id, previous_conversation)
    item, previous_conversation = await _ask_one(client, notebook.id, question)
    items.append(item)
```

**앞 질문의 대화를 지우고 다음 질문을 던진다.** NotebookLM 은 대화 맥락을 이어가므로,
지우지 않으면 2번 답변이 1번 질문에 물든다. 질문마다 독립적인 답을 받는 게 목적이므로
격리가 필요하다.

`_ask_one` 이 **대화 ID 를 함께 돌려주는 이유**가 여기 있다. 실패한 경우에는 `None` 을
돌려주는데(`nlm.py:276`), 끊을 대화가 없으므로 다음 질문이 헛되이 삭제를 시도하지 않게
하려는 것이다.

**질문 단위 실패는 예외로 올리지 않는다.**

```python
except exceptions.ChatError as error:
    return AnswerItem(..., answer=None, error=errors.to_message(error).text), None
```

3개 중 1개가 실패해도 나머지 2개는 살린다. `AnswerItem` 은 `answer` 와 `error` 가
**배타적**이다(`models.py:32-33`).

### 단계 10 — 인용 정규화

| | |
|---|---|
| **호출** | `_to_citations(result.references)` — `nlm.py:291` |
| **입력** | 라이브러리의 인용 목록 (세 필드 모두 `None` 일 수 있음) |
| **출력** | `tuple[models.Citation, ...]` |

| 상황 | 처리 |
|---|---|
| 번호 없음 또는 본문 없음 | **버린다** (근거로 보여 줄 값어치가 없음) |
| 점수만 없음 | `0.0` 으로 채운다 |

**경계에서 한 번 정리해 두면 화면과 저장 코드가 `None` 을 다루지 않아도 된다.**

### 단계 11 — 노트북 삭제 (`finally`)

| | |
|---|---|
| **호출** | `client.notebooks.delete(notebook.id)` — `nlm.py:192` |
| **입력** | 노트북 ID |
| **출력** | 없음 |

`try/finally` 라서 **중간에 무엇이 실패해도 실행된다.** NotebookLM 은 노트북 개수 상한이
있어서, 실패할 때마다 찌꺼기가 쌓이면 나중에 아예 만들 수 없게 된다.

여기서 `on_progress` 를 **부르지 않는** 게 중요하다.

```python
finally:
    # 여기서 on_progress 를 부르지 않는다. 진행 콜백은 Streamlit
    # API 를 호출하는데, 사용자가 페이지를 이동한 순간 스크립트가
    # 중단되어 아래 삭제에 도달하지 못하고 노트북이 남는다.
    await client.notebooks.delete(notebook.id)
```

정리 코드 안에서 중단될 수 있는 호출을 하면 정리 자체가 무산된다.

### 단계 12 — 결과 조립

| | |
|---|---|
| **위치** | `nlm.py:194` |
| **출력** | `models.RunResult(url, video_id, items, title)` |

`items` 는 `tuple` 이고 `RunResult` 는 `frozen=True` 다. 여기서부터는 **읽기 전용 값**으로
스레드 경계를 넘는다.

### 단계 13 — 이력 저장

| | |
|---|---|
| **호출** | `store.connect(db_path)` → `run_history.save_run(connection, result)` — `runner.py:123-125` |
| **입력** | DB 경로, `RunResult` |
| **출력** | 저장된 실행의 `id` (`int`) |
| **부수효과** | `runs` 1행 + `answers` N행 INSERT, commit, **커넥션 close** |

질문 제목과 본문을 `questions` 테이블 **외래키가 아니라 문자열로 복사**한다
(`run_history.py:16-18`). 나중에 질문 템플릿을 고치거나 지워도 **과거 이력은 그대로 남는다.**

인용은 `citations_to_json()` 으로 JSON 문자열이 되어 한 컬럼에 들어간다.
`ensure_ascii=False` 라 DB 를 직접 열어 봐도 한글이 읽힌다(`models.py:94-95`).

### 단계 14 — 완료 표시

| | |
|---|---|
| **호출** | `registry.finish(run_id, result)` — `runs.py:131` |
| **입력** | 실행 ID, `RunResult` |
| **출력** | 없음 |
| **효과** | `status="done"`, `result` 저장, `finished_at` 기록 |

**저장이 끝난 뒤에야 `done` 으로 바꾼다.** 순서가 뒤바뀌면 화면이 "완료"라고 말하는데
이력 화면에는 없는 상태가 생긴다.

### 단계 15 — 화면 갱신

| | |
|---|---|
| **호출** | `dashboard._render_runs()` — `@st.fragment(run_every="1s")` — `dashboard.py:23` |
| **입력** | 없음 |
| **출력** | 실행 카드 목록 (최근 것부터) |

| 상태 | 표시 |
|---|---|
| `running` | `st.info("실행 중 — <최신 진행 문구>")` |
| `failed` | `error_level` 에 따라 `st.error` 또는 `st.info` |
| `done` | `st.success("완료 — 답변 N건. 이력 화면에서 확인하세요.")` |

완료 카드는 **답변 본문을 그리지 않는다.** 저장이 끝난 뒤에만 `done` 이 되므로 이 실행은
반드시 이력 화면에 있고, 본문 확인과 수정은 거기서 한다(`run_progress.py:46-48`).
실패한 항목이 섞여 있으면 그 질문 제목만 경고로 알려 준다.

---

## 4. 실패했을 때 — 3중 `except`

`_work()`(`runner.py:94-120`)에 `except` 가 세 개 겹쳐 있다. **각각 다른 사고를 막는다.**

| 순서 | 잡는 것 | 처리 | 이유 |
|---|---|---|---|
| 1 | `errors.MAPPED_ERRORS` | `to_message()` 로 번역 → `registry.fail(..., level)` | 예상된 실패는 사람이 읽을 문구로 |
| 2 | `Exception` | `f"예상 못 한 오류({타입}): {메시지}"` → `fail` | **여기서 예외가 새면 화면이 영원히 "실행 중"에 머문다** |
| 3 | `BaseException` | 상태만 남기고 **`raise` 로 재전파** | `CancelledError` 등이 새도 핸들이 `running` 에 남지 않게 |

프로젝트 규칙은 맨 `except Exception:` 을 금지하는데, 여기는 **스레드 최상위**라는 예외
상황이라 주석으로 이유를 명시하고 허용했다. 스레드에서 예외가 새면 아무도 못 잡고,
사용자는 영원히 도는 스피너만 보게 된다.

저장 실패도 따로 잡는다(`runner.py:128`). **"답변은 받았으나 이력 저장에 실패했습니다"** 로
구분해서 알려 준다 — 답변을 받은 것과 못 받은 것은 사용자에게 전혀 다른 상황이다.

실패한 실행은 **이력에 저장하지 않는다**(`test_runner_start.py:134` 가 이걸 지킨다).

---

## 5. 알아 두면 헷갈리지 않는 것

**① 대시보드 프래그먼트는 읽기만 한다.**

```python
@st.fragment(run_every=_POLL_INTERVAL)
def _render_runs() -> None:
    """**이 프래그먼트는 레지스트리를 읽기만 한다.** 안에서 상태를 바꾸면
    그 변경이 다음 재실행을 부르고 다시 상태를 바꿔 무한 루프가 된다."""
```

1초마다 자동 재실행되는 함수 안에서 상태를 바꾸면 자기 자신을 계속 깨운다.
`discard()` 는 **사용자 클릭에서만** 일어나므로 안전하다.

**② 진행 문구는 Streamlit 을 거치지 않는다.**

`_work` 의 `on_progress` 는 `registry.append_progress()` 만 부른다. 작업 스레드가
Streamlit API 를 건드리면, 사용자가 페이지를 이동한 순간 그 스레드가 중단된다
(`runner.py:86-87`). 그래서 **스레드는 레지스트리에 적기만 하고, 화면이 따로 읽어 간다.**

**③ 서버를 재시작하면 진행 중이던 실행은 사라진다.**

레지스트리는 메모리(`@st.cache_resource`)다. 이력은 DB 에 남지만, 저장 전에 죽은 실행은
추적할 수 없다. 그때 남은 임시 노트북은 **정리 화면**에서 지운다(`dashboard.py:14-19` 안내).

**④ 동시 실행은 한 건으로 제한된다.**

`running_count() > 0` 이면 버튼이 잠긴다. 기술적 제약이라기보다 개인용 도구의 선택이다.

**⑤ 답변 원문은 손대지 않는다.**

인용 마커를 걷어내는 `core/answer_text.py` 는 **표시 직전에만** 적용된다. DB 에는 항상
원문이 남는다.

---

## 6. 데이터가 변해 가는 모양

```
"https://youtu.be/abc123XYZ_9"          ← 사용자 입력 (str)
        │  youtube.extract_video_id()
        ▼
"abc123XYZ_9"                            ← 영상 ID (str, 11자)
        │  registry.create()
        ▼
RunHandle(run_id="a1b2c3d4", status="running", progress=[])
        │  run_pipeline() … chat.ask()
        ▼
AnswerItem(question_title=..., answer="...", citations=(Citation, ...), error=None)
        │  × 질문 개수
        ▼
RunResult(url=..., video_id=..., items=(...), title="영상 제목")
        │  save_run()
        ▼
runs 테이블 1행  +  answers 테이블 N행   ← citations 는 JSON 문자열 1컬럼
        │  registry.finish()
        ▼
RunHandle(status="done", result=RunResult, finished_at=...)
```

---

## 7. 테스트 지도

| 테스트 | 확인하는 것 |
|---|---|
| `test_nlm.py:168` | 생성 → 인덱싱 → 질문 → **삭제** 순서가 지켜진다 |
| `test_nlm.py:186` | 소스 추가에 `wait=True` 와 타임아웃이 전달된다 |
| `test_nlm.py:197, 204` | **첫 질문은 대화를 안 지우고, 이후 질문은 새 대화로 시작한다** |
| `test_nlm.py:255, 269` | **한 질문의 실패가 다른 질문을 망치지 않는다** |
| `test_nlm.py:277` | **소스 실패해도 노트북은 삭제된다** (`finally` 보장) |
| `test_nlm.py:299, 323` | 불완전한 인용은 버리고, 점수 없으면 0.0 |
| `test_runner_start.py:49` | 성공하면 이력 저장 후 `done` |
| `test_runner_start.py:112` | **예상 못 한 오류가 나도 `running` 에 남지 않는다** |
| `test_runner_start.py:134` | 실패한 실행은 이력에 저장하지 않는다 |
| `test_runner_start.py:178` | 저장 실패도 `failed` 로 남는다 |
| `test_ask.py:98` | 실행 중이면 버튼이 잠긴다 |
| `test_dashboard.py:98` | **진짜 백그라운드 실행이 대시보드까지 도달한다** (통합) |

굵게 표시한 것들이 이 기능의 설계 의도를 박아 둔 테스트다. 파이프라인을 고칠 때 이것들이
깨지면 설계를 되돌린 것이니 멈추고 다시 보는 게 좋다.

---

## 8. 정리

- **화면은 시작만 하고 즉시 반환한다.** 질의가 몇 분 걸리므로 페이지 이동에 묶이면 안 된다.
- **레지스트리가 유일한 만남의 장소다.** 스레드는 쓰고, 화면은 1초마다 읽는다. 양쪽 다
  락 안에서 복사본을 주고받는다.
- **질문마다 앞 대화를 끊는다.** 답변이 서로 물들지 않게 하려는 것이 이 파이프라인의 핵심 규칙이다.
- **임시 노트북은 `finally` 로 반드시 지운다.** 노트북 개수 상한이 있기 때문이다.
- **`done` 은 DB 저장이 끝난 뒤에만 찍힌다.** 화면과 이력이 어긋나지 않게 하는 순서다.
- 실패 경로는 **세 겹으로 막혀 있다.** 어떤 예외가 나도 실행이 영원히 "진행 중"에 남지 않는다.
