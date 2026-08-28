# 백그라운드 실행 전환 설계

- **작성일**: 2026-08-28
- **상태**: 설계 (구현 계획 수립 전)
- **대상**: 기존 기획서 `2026-08-28-youtube-qa-design.md` 의 **6.1 실행 모델을
  대체**한다. 나머지 장(계층 경계, 파이프라인, 대화 격리, 데이터 모델, 정리
  기능)은 그대로 유효하다.
- **범위**: 1단계(즉시 수정) + 2단계(백그라운드 실행). **완료 알림(3단계)은
  범위에서 제외한다.**

---

## 1. 왜 바꾸는가

### 1.1 실제로 벌어진 일

첫 실사용에서 다음이 관찰됐다.

- 질의를 실행하고 다른 페이지로 이동했다가 돌아오니 **결과가 없고 화면이 비어
  있었다.**
- **이력에도 남지 않았다** (`runs` 테이블 0행).
- NotebookLM 에는 **임시 노트북이 생성된 채 남아 있었다.**
- 터미널에는 **예외 흔적이 없었다.**

### 1.2 원인

Streamlit 은 사용자가 페이지를 이동하거나 위젯을 조작하면 **실행 중이던
스크립트를 중단**하고 재실행한다. 중단은 스크립트가 **다음 Streamlit API 를
호출하는 순간** `StopException` 으로 일어나며, 정상 흐름 제어이므로 터미널에
traceback 을 남기지 않는다.

현재 파이프라인은 진행 문구를 콜백으로 알리는데, 그 콜백이
`status.update()` 와 `st.write()` 를 부른다 — **둘 다 Streamlit API 다.**
따라서 진행 문구가 갱신되는 지점마다 중단될 수 있다.

```
on_progress("임시 노트북 생성 중")      ← 중단 지점 1
notebooks.create(...)                    ← 노트북 생성됨
try:
    on_progress("자막 인덱싱 중 ...")    ← 중단 지점 2
    sources.add_url(...)
    on_progress("질문 N/M")              ← 중단 지점 3
    ...
finally:
    on_progress("임시 노트북 삭제 중")   ← 중단 지점 4 ★
    notebooks.delete(notebook.id)        ← 도달하지 못함
```

`finally` 의 **첫 줄이 Streamlit API 호출**이라, 정리를 보장하려고 둔 블록이
정작 정리를 하지 못한다. 관찰된 네 증상이 이 하나로 전부 설명된다.

### 1.3 기존 설계의 오판

기존 기획서 6.1 은 백그라운드 스레드 안을 기각하면서 그 대가를 "실행 중에는
그 탭이 묶이고 취소 버튼을 만들 수 없다" 로만 적었다. **실제 대가는 "사용자가
기다리지 못하고 이동하면 작업이 통째로 날아가고 노트북이 남는다" 였다.**
기각 판단 자체가 틀렸다기보다 비용 산정이 틀렸다.

---

## 2. 채택 구조

```
[질의 페이지]   트리거만 ──┐
                            ├──> 실행 레지스트리 (세션 간 공유)
[대시보드 페이지] 폴링 조회 ─┘         ↑
                                  백그라운드 스레드
                                    ├─ 진행 문구 기록
                                    └─ 완료 시 DB 에 직접 저장
```

세 가지가 핵심이다.

1. **질의 페이지는 실행을 시작만 하고 즉시 반환한다.** 더 이상 페이지가
   파이프라인에 묶이지 않으므로, 이동해도 작업이 중단되지 않는다.
2. **진행 상황과 결과는 `st.session_state` 가 아니라 레지스트리에 둔다.**
   `session_state` 는 브라우저 탭마다 별개이고 위젯 상태는 페이지를 떠나면
   버려지지만, 레지스트리는 그렇지 않다.
3. **완료 시 스레드가 직접 DB 에 저장한다.** 화면 재실행을 기다리지 않으므로
   사용자가 어느 페이지에 있든 이력이 남는다.

### 2.1 레지스트리가 세션 간 공유된다는 근거

`@st.cache_resource` 로 감싼 객체는 **모든 세션·모든 브라우저 탭에서 동일한
인스턴스**다. 실측으로 확인했다 — 서로 다른 두 `AppTest` 세션이 같은 객체
`id` 를 받았고 한쪽이 쓴 값을 다른 쪽이 읽었다.

이 성질이 없으면 "다른 페이지에서 진행 상황 확인" 이 성립하지 않는다.
`st.session_state` 로는 불가능하다.

### 2.2 스레드가 Streamlit API 를 부르지 않는다

스레드에 `add_script_run_ctx` 를 붙이면 `st.*` 를 부를 수 있지만, **그러면
그 스레드도 중단 대상이 되어 지금 문제가 재현된다.** 따라서 붙이지 않는다.

스레드는 순수 파이썬 객체(레지스트리, 리스트, 락)와 자신의 DB 커넥션에만
쓴다. 화면 갱신은 메인 스크립트가 레지스트리를 읽어서 한다.

---

## 3. 계층과 파일

### 3.1 바뀌지 않는 것

| 파일 | 이유 |
|---|---|
| `services/nlm.py` | 이미 Streamlit 미의존. `on_progress` 콜백이 `st.write` 대신 리스트에 append 하면 그만이다 |
| `core/` 전체 | 순수 계산. 영향 없음 |
| `services/store.py` | `check_same_thread=False` 로 이미 열려 있다 |
| `pages/question_admin.py`, `pages/history.py` | 영향 없음 |

기획 때 정한 계층 경계 덕분에 **파이프라인 코드가 한 줄도 바뀌지 않는다.**

### 3.2 바뀌는 것

| 파일 | 작업 | 계층 |
|---|---|---|
| `services/runner.py` | **신규** — 실행 핸들·레지스트리·스레드 | services (Streamlit 미의존) |
| `session.py` | 레지스트리를 `@st.cache_resource` 로 감싸는 접근자 추가 | UI |
| `pages/ask.py` | 트리거 전용으로 **단순화** | UI |
| `pages/dashboard.py` | **신규** — 실행 현황 | UI |
| `components/run_progress.py` | **폐기 후 재작성** — 컨텍스트 매니저 → 핸들 렌더러 | UI |
| `app.py` | 대시보드 페이지 등록 | UI |

**중요한 경계**: 레지스트리 클래스 자체는 `services/runner.py` 에 두고
Streamlit 을 import 하지 않는다. `@st.cache_resource` 로 감싸는 것은
`session.py` 의 몫이다. 이래야 runner 를 Streamlit 없이 테스트할 수 있다.

---

## 4. 핵심 데이터

### 4.1 실행 핸들

```python
@dataclasses.dataclass
class RunHandle:
    """진행 중이거나 끝난 실행 하나."""

    run_id: str  # uuid4().hex[:8]
    url: str
    video_id: str
    question_texts: tuple[str, ...]
    started_at: str
    status: Literal["running", "done", "failed"]
    progress: list[str]  # 진행 문구 누적
    result: models.RunResult | None
    error_message: str | None  # errors.to_message() 로 변환한 사용자 문구
    error_level: Literal["info", "error"] | None
    finished_at: str | None
```

기존 값 객체와 달리 **frozen 이 아니다** — 스레드가 상태를 갱신한다. 대신
레지스트리의 락으로 보호한다.

`error_message` 를 사용자 문구로 저장하는 이유: `core/errors.to_message` 는
순수 함수이고 스레드에서 부를 수 있다. 화면은 문구만 그리면 된다.

### 4.2 레지스트리

```python
class RunRegistry:
    """실행 핸들을 세션 간에 공유하는 보관소."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handles: dict[str, RunHandle] = {}

    def create(self, url, video_id, question_texts) -> RunHandle: ...
    def get(self, run_id) -> RunHandle | None: ...
    def list_all(self) -> list[RunHandle]: ...  # 최신순 복사본
    def running_count(self) -> int: ...
    def append_progress(self, run_id, message) -> None: ...
    def finish(self, run_id, result) -> None: ...
    def fail(self, run_id, message, level) -> None: ...
```

**모든 공개 메서드가 락 안에서 동작한다.** `list_all` 은 화면이 순회하는
동안 스레드가 바꾸지 못하도록 **복사본**을 돌려준다.

---

## 5. 동작 흐름

### 5.1 실행 시작 (질의 페이지)

```
[실행] 클릭
  → runner.start_run(registry, url, questions, db_path)
      ├─ registry.create(...) 로 핸들 생성 (status="running")
      ├─ threading.Thread(target=_worker, daemon=True).start()
      └─ run_id 반환
  → st.info("실행을 시작했습니다. 대시보드에서 확인하세요.")
  → 페이지 렌더 종료 (묶이지 않음)
```

### 5.2 스레드가 하는 일

```python
def _worker(registry, handle, questions, db_path) -> None:
    def on_progress(message: str) -> None:
        registry.append_progress(handle.run_id, message)

    try:
        result = asyncio.run(
            nlm.run_pipeline(handle.url, questions, on_progress)
        )
    except exceptions.NotebookLMError as error:
        message = errors.to_message(error)
        registry.fail(handle.run_id, message.text, message.level)
        return

    connection = store.connect(db_path)  # 스레드 전용 커넥션
    try:
        store.save_run(connection, result)
    finally:
        connection.close()
    registry.finish(handle.run_id, result)
```

세 가지가 지켜져야 한다.

- **Streamlit API 를 부르지 않는다.** `on_progress` 는 리스트에 append 만 한다.
- **DB 커넥션을 새로 연다.** 앱이 공유하는 `session.get_connection()` 을
  스레드에서 재사용하지 않는다.
- **`save_run` 을 먼저 하고 `finish` 를 나중에 한다.** 순서가 뒤바뀌면 화면이
  "완료" 를 본 직후 이력을 조회했을 때 아직 없을 수 있다.

### 5.3 대시보드 폴링

```python
@st.fragment(run_every="1s")
def render_runs() -> None:
    for handle in registry.list_all():
        ...  # 상태별 렌더
```

프래그먼트만 재실행되므로 페이지 전체가 다시 그려지지 않는다.

---

## 6. 동시성 규칙

| 규칙 | 이유 |
|---|---|
| 동시 실행은 **1개**로 제한한다 | NotebookLM 노트북 상한·요청 한도. 실행 중이면 [실행] 버튼을 비활성화한다 |
| 레지스트리 접근은 전부 락 안에서 | 여러 탭이 동시에 읽고 스레드가 동시에 쓴다 |
| `list_all()` 은 복사본 반환 | 화면이 순회하는 중에 스레드가 바꾸면 깨진다 |
| 스레드는 `daemon=True` | 서버 종료 시 프로세스가 매달리지 않는다 |
| 스레드에서 `st.*` 호출 금지 | 중단 대상이 되어 원래 문제가 재현된다 |
| 스레드는 자기 DB 커넥션을 열고 닫는다 | 공유 커넥션 동시 사용을 피한다 |

---

## 7. 화면

### 7.1 질의 (변경)

- YouTube URL 입력 (그대로)
- 질문 다중 선택 (그대로)
- **[실행] — 시작만 하고 즉시 반환.** 이미 실행 중이면 비활성 + 안내
- **진행 표시·답변 렌더를 제거한다.** 대시보드로 옮긴다
- 실행 직후 "대시보드에서 확인하세요" 안내

페이지가 82줄에서 **더 짧아진다.**

### 7.2 대시보드 (신규)

- `@st.fragment(run_every="1s")` 로 1초마다 갱신
- 실행별로 한 블록:

| 상태 | 표시 |
|---|---|
| `running` | 영상 URL, 경과 시간, **진행 문구 최신 것**, 질문 수 |
| `done` | 영상 URL, 소요 시간, `answer_view.render_items(result.items)` |
| `failed` | 영상 URL, `error_level` 에 따라 `st.info` / `st.error` |

- 완료·실패 항목을 목록에서 지우는 [지우기] 버튼 (레지스트리에서만 제거,
  이력은 DB 에 남는다)

### 7.3 이력·질문 관리·정리

변경 없음. 이력은 여전히 DB 를 읽으므로 스레드가 저장한 결과가 그대로 보인다.

---

## 8. 테스트 전략

### 8.1 `services/runner.py` — 결정적으로 테스트한다

Streamlit 을 모르므로 일반 단위 테스트가 가능하다. **여기에 커버리지를
집중한다.**

- 가짜 파이프라인 함수를 주입(`run_pipeline` 을 인자로 받게 설계)
- 스레드 완료는 `handle_thread.join(timeout=5)` 로 기다린다
- 검증 항목: 진행 문구 누적, 성공 시 `save_run` 호출과 `status="done"`,
  실패 시 `error_message`/`error_level` 과 `status="failed"`,
  동시 실행 제한, 락 아래에서의 목록 복사

### 8.2 UI — 얕게 검증한다

레지스트리에 **미리 만들어 둔 핸들**을 넣고 렌더 결과만 본다. 스레드를
띄우지 않으므로 타이밍 의존이 없다.

- 실행 중 핸들 → 진행 문구가 화면에 보이는가
- 완료 핸들 → 답변과 인용이 보이는가
- 실패 핸들 → `info`/`error` 수준이 맞는가
- 질의 페이지: 실행 중이면 버튼이 비활성인가

### 8.3 착수 전 확인할 것

**`st.fragment(run_every=)` 가 `AppTest` 에서 자동 재실행되는지 확인되지
않았다.** 되지 않는다면 대시보드 테스트는 "핸들을 넣고 한 번 렌더" 방식으로
가고, 폴링 자체는 수동 확인에 맡긴다. 30분이면 판별된다.

기존 101개 테스트는 전부 결정적이다. **그 성질을 잃지 않는 것이 이 전략의
목적이다.**

---

## 9. 위험과 한계

| 항목 | 내용 | 대응 |
|---|---|---|
| 서버 재시작 | 레지스트리가 메모리에만 있어 사라진다. 실행 중이던 작업 추적 불가 | 노트북은 정리 화면(F-10)이 회수한다. 문서에 명시하고 감수한다 |
| 브라우저를 닫아도 실행이 계속됨 | 의도된 이점이지만 통제 수단이 없다 | 2단계에서는 취소 기능을 넣지 않는다. 필요해지면 협조적 취소 플래그를 추가한다 |
| 대시보드를 열어두지 않으면 완료를 모름 | 알림을 범위에서 제외했으므로 사용자가 직접 확인한다 | 질의 페이지에서 "실행 중 N건" 정도를 표시해 유도한다 |
| 1초 폴링의 부하 | 1인 로컬 도구라 실질 부담은 없다 | 실행이 없을 때는 폴링 간격을 늘리는 최적화가 가능하나 지금은 하지 않는다 |
| 스레드 예외 누락 | `NotebookLMError` 가 아닌 예외가 나면 스레드가 조용히 죽고 상태가 `running` 에 머문다 | `except Exception` 은 규칙상 금지이나, **스레드 최상위에서는 예외**로 허용하고 사유 주석을 단다. 잡아서 `fail()` 로 기록해야 한다 |

마지막 항목은 프로젝트 규칙(`except Exception` 금지)과 부딪힌다. 스레드에서
예외가 새면 화면이 영원히 "실행 중" 으로 남으므로, **최상위에서만** 넓게 잡고
그 사유를 주석으로 남기는 것을 이 설계의 예외로 명시한다.

---

## 10. 작업 단계

### 1단계 — 즉시 수정 (독립적)

`services/nlm.py` 의 `finally` 에서 `on_progress("임시 노트북 삭제 중")` 한 줄을
제거한다. 중단되더라도 노트북 삭제가 완료된다. 2단계와 무관하게 값을 하며,
2단계 이후에도 이 줄은 없는 편이 맞다.

### 2단계 — 백그라운드 실행

1. `services/runner.py` 작성 + 단위 테스트
2. `session.py` 에 레지스트리 접근자 추가
3. `components/run_progress.py` 재작성 (핸들 렌더러)
4. `pages/dashboard.py` 작성 + 테스트
5. `pages/ask.py` 단순화 + 테스트 수정
6. `app.py` 에 대시보드 등록

순서가 중요하다. 1이 끝나야 3~5 가 의미를 갖고, 5 를 먼저 하면 그 사이 앱이
동작하지 않는다.

### 범위 밖 (이번에 하지 않음)

- 완료 알림 (`st.toast` / `st.dialog`)
- 실행 취소 기능
- 레지스트리 영속화 (서버 재시작 대응)
- `pages/maintenance.py` 의 백그라운드화 — 작업이 짧아 현재 방식으로 충분하다

---

## 11. 기존 기획서와의 관계

이 문서는 기존 기획서의 **6.1 실행 모델만** 대체한다. 다음은 그대로 유효하다.

- 6.2 계층 경계 — 오히려 이 변경이 그 값어치를 증명한다
- 6.3 질의 파이프라인 (`finally` 삭제, 부분 실패) — 1단계의 한 줄 외 변경 없음
- 6.4 대화 격리 — 변경 없음
- 6.5 임시 노트북 수명 — 변경 없음. 오히려 F-10 의 중요성이 커진다
- 7장 데이터 모델 — 변경 없음. 레지스트리는 메모리에만 산다
- 9장 오류 처리 — 변경 없음. 스레드가 같은 `to_message` 를 쓴다
