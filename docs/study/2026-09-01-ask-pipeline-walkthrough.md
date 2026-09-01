# 영상 질의 코드로 배우는 파이썬 문법 4가지

> 온보딩 문서 [`docs/onboard/2026-09-01-ask-pipeline-walkthrough.md`](../onboard/2026-09-01-ask-pipeline-walkthrough.md) 의 짝 문서.
> 저쪽이 **"질의가 어떻게 흐르는가"** 라면, 이 문서는 **"그 코드에 쓰인 문법이 무엇인가"** 를 다룬다.
> 대상 코드: `services/nlm.py` · `services/runner.py` · `services/runs.py` ·
> `services/run_history.py` · `core/models.py` · `core/youtube.py` · `components/run_progress.py`
> 작성 2026-09-01 · 기준 커밋 `38a390f`

---

## 이 문서가 다루는 것

질의 파이프라인 경로에서 **반복해서 등장하는** 문법이다. 등장 횟수 기준으로 추렸다.

| # | 문법 | 왜 자주 나오나 |
|---|---|---|
| 1 | 데이터클래스와 `replace` | 값이 스레드 경계를 넘나들어야 해서 값 객체가 많다 |
| 2 | 컴프리헨션과 제너레이터 표현식 | 목록을 걸러 내고 옮겨 담는 일이 잦다 |
| 3 | `None` 을 안전하게 다루는 관용구 | `title`·`answer`·`error`·`result` 가 모두 `\| None` 이다 |
| 4 | 비동기 3종 (`async def`·`await`·`asyncio.run`) | 네트워크 대기가 길고, 그걸 스레드에 얹었다 |

1과 3은 짝이다. 값 객체를 `frozen` 으로 굳혀 스레드 경계를 넘기는 대신, 없을 수 있는 필드를
`| None` 으로 두었기 때문에 그걸 풀어 쓰는 관용구가 곳곳에 나온다.

> **제외한 것**: `try`/`except`/`finally` 계층은 이 문서에서 다루지 않는다.
> 예외를 다루는 문법은 [인증 편 문법 정리](2026-09-01-first-run-authentication-flow.md) 의
> 5장(예외를 튜플 변수로 모아 다루기)을 참고할 것.
>
> 그 문서에서 이미 다룬 **함수를 값으로 주고받기 · `Callable[...]` · `Protocol` · `with`** 도
> 이 경로에 반복 등장한다(`runner.py:16, 26`, `nlm.py:17-104, 137`).

---

## 1. 데이터클래스와 `replace`

### 1.1 무엇인가

`__init__`·`__eq__`·`__repr__` 을 자동으로 만들어 주는 데코레이터다. **이 프로젝트의 값 객체는
전부 이 형태다.**

```python
@dataclasses.dataclass(frozen=True, slots=True)      # models.py:28
class AnswerItem:
    question_title: str
    question_text: str
    answer: str | None
    citations: tuple[Citation, ...]
    error: str | None
    id: int | None = None
```

필드를 타입과 함께 나열하기만 하면 생성자가 생긴다.

```python
item = AnswerItem(question_title="요약", question_text="...", answer="...",
                  citations=(), error=None)
```

### 1.2 두 옵션

| 옵션 | 효과 |
|---|---|
| `frozen=True` | 생성 후 필드 변경 금지 — `item.answer = "..."` 하면 예외 |
| `slots=True` | `__dict__` 없이 고정 슬롯만 — 메모리 절약, **오타 속성 대입 차단** |

`slots=True` 는 실수를 잡아 준다. 일반 객체는 `item.anwser = "x"` (오타)를 조용히 새 속성으로
받아들이지만, 슬롯이 있으면 그 자리에서 `AttributeError` 가 난다.

### 1.3 헷갈리는 지점 셋

**① 기본값 있는 필드는 뒤에 와야 한다**

```python
id: int | None = None        # models.py:48 — 맨 아래인 건 취향이 아니라 문법 제약
```

함수 인자와 같은 규칙이다. 기본값 있는 필드 뒤에 없는 필드가 오면 `TypeError` 로 클래스
정의 자체가 실패한다.

`AnswerItem.id` 가 왜 `None` 일 수 있는지도 독스트링에 적혀 있다 — **이력에서 읽어온
항목만 `id` 를 가지고**, 파이프라인이 갓 만든 항목은 아직 저장 전이라 없다. 화면은 이
값이 있을 때만 편집 상자를 그린다(`models.py:38-40`).

**② `RunHandle` 만 `frozen` 이 아니다**

```python
@dataclasses.dataclass(slots=True)                   # runs.py:15 — frozen 없음
class RunHandle:
    """...다른 값 객체와 달리 frozen 이 아니다. 백그라운드 스레드가 상태를
    갱신하며, 동시 접근은 ``RunRegistry`` 의 락이 막는다."""
```

백그라운드 스레드가 `status` 를 `running` → `done` 으로 바꿔야 해서다. **예외라는 사실과
그 안전장치(락)를 독스트링에 명시해 뒀다.**

**③ `@property` 는 필드가 아니다**

```python
@property
def succeeded(self) -> bool:                         # models.py:50
    """실패 메시지가 없으면 참."""
    return self.error is None
```

저장되지 않고 **매번 계산된다.** 생성자 인자에도 들어가지 않는다.

### 1.4 `replace` — 필드 하나 바꾼 새 객체

```python
def _copy(handle: RunHandle) -> RunHandle:           # runs.py:173
    """진행 목록까지 새로 만든 복사본을 돌려준다."""
    return dataclasses.replace(handle, progress=list(handle.progress))
```

`replace(객체, 필드=새값)` 은 **나머지 필드를 그대로 복사한 새 객체**를 만든다.
`frozen` 객체를 "수정"하는 표준 방법이기도 하다.

그런데 여기서의 목적은 다르다 — **얕은 복사의 구멍을 메우는 것**이다.

```
replace 만 했다면:
    새 handle ─┐
               ├─▶ 같은 progress 리스트   ← 스레드가 append 하면 화면도 영향받음
    원본 handle ┘

list(...) 로 감싸면:
    새 handle ──▶ 새 progress 리스트      ← 완전히 분리
    원본 handle ──▶ 원래 리스트
```

레지스트리에서 나가는 값은 **항상 이 복사본**이다(`runs.py:80, 93, 103`). 화면이 목록을
순회하는 도중 스레드가 원본을 바꿔도 안전하다.

> **한 줄 정리** — `frozen=True, slots=True` 가 이 프로젝트의 값 객체 기본형이고,
> `RunHandle` 만 예외이며, `replace` + `list(...)` 조합은 리스트 필드까지 떼어 내는 복사다.

---

## 2. 컴프리헨션과 제너레이터 표현식

### 2.1 무엇인가

`for` 루프 + `append` 를 한 줄로 쓰는 축약 문법이다.

```python
# 이 두 개가 같다
result = []
for thread in _threads:
    if thread.is_alive():
        result.append(thread)

result = [thread for thread in _threads if thread.is_alive()]   # runner.py:48
```

읽는 순서는 **가운데 → 오른쪽 → 왼쪽** 이다.

```
[ thread          for thread in _threads      if thread.is_alive() ]
  ③ 이걸 담아라     ① 여기를 돌면서             ② 이 조건이 참일 때만
```

### 2.2 대괄호냐 괄호냐

```python
[x for x in items]        # 리스트 — 즉시 전부 만든다
(x for x in items)        # 제너레이터 — 필요할 때 하나씩 만든다
```

```python
return sum(                                          # runs.py:113
    1
    for handle in self._handles.values()
    if handle.status == "running"
)
```

**개수를 세려고 리스트를 만들지 않는다.** 조건에 맞을 때마다 `1` 을 흘려보내고 `sum` 이
더한다. 함수 인자로 넘길 때는 바깥 괄호가 인자 괄호를 겸해서 **괄호가 하나만 보인다.**

`", ".join(item.question_title for item in failed)`(`run_progress.py:58`)도 같은 형태다.

### 2.3 대괄호가 겹칠 때

가장 눈이 미끄러지는 자리다.

```python
connection.executemany(                              # run_history.py:34
    "INSERT INTO answers (run_id, question_title, ...) VALUES (?, ?, ?, ?, ?, ?)",
    [
        (
            run_id,
            item.question_title,
            item.question_text,
            item.answer,
            models.citations_to_json(item.citations),
            item.error,
        )
        for item in result.items
    ],
)
```

**튜플의 리스트**를 만들고 있다. `executemany` 는 "행 여러 개"를 받으므로 안쪽 괄호가
한 행, 바깥 대괄호가 행 묶음이다.

### 2.4 조건으로 걸러 내기

```python
return [                                             # nlm.py:218
    models.TempNotebook(id=item.id, title=item.title)
    for item in notebooks
    if item.title.startswith(TEMP_TITLE_PREFIX)
]
```

한 줄에 **변환**(`TempNotebook` 만들기)과 **필터**(`tmp-` 로 시작하는 것만)가 함께 있다.
정리 화면이 사용자가 손으로 만든 노트북을 건드리지 않는 근거가 이 `if` 한 줄이다.

### 2.5 이 경로에서의 등장

| 위치 | 무엇 |
|---|---|
| `runner.py:48` | 죽은 스레드 걸러 내기 |
| `runs.py:102-104` | 핸들 복사본 목록 (역순) |
| `runs.py:113-117` | `sum` + 제너레이터로 개수 세기 |
| `nlm.py:218-222` | 임시 노트북만 골라 변환 |
| `run_history.py:39-49` | `executemany` 파라미터 묶음 |
| `models.py:103-106, 123-126` | JSON 직렬화·역직렬화 양쪽 |
| `run_progress.py:55, 58` | 실패 항목 필터 + `join` |
| `runner.py:51` | `tuple(question.text for question in questions)` |

> **한 줄 정리** — 대괄호면 리스트를 즉시 만들고 괄호면 하나씩 흘려보내며,
> 읽는 순서는 가운데(`for`) → 오른쪽(`if`) → 왼쪽(담을 값)이다.

---

## 3. `None` 을 안전하게 다루는 관용구

이 경로에는 `X | None` 타입이 많다 — `title`, `answer`, `error`, `result`, `finished_at`.
그래서 이를 풀어 쓰는 관용구가 반복되는데, **세 가지가 섞여 나오고 서로 다르다.**

### 3.1 `or` — falsy 면 오른쪽

```python
title = source.title or None                     # nlm.py:175
video_id = youtube.extract_video_id(url) or ""   # nlm.py:196
hostname = (parsed.hostname or "").lower()       # youtube.py:40
```

`or` 는 왼쪽이 **falsy** 면 오른쪽을 돌려준다. falsy 는 `None`, `""`, `0`, `0.0`, `[]`, `{}` 다.

`nlm.py:175` 는 이걸 이용해 **빈 문자열과 `None` 을 하나로 접는다.**

```python
# 빈 제목은 없는 것으로 본다. 화면이 video_id 로 대신한다.
title = source.title or None
```

"제목 없음"을 표현하는 값이 둘이면 화면과 저장 코드가 매번 두 가지를 검사해야 한다.
**경계에서 한 번 정리해 두는 편이 낫다.**

### 3.2 `is not None` — 값이 falsy 여도 지켜야 할 때

```python
score=score if score is not None else 0.0        # nlm.py:317
```

**여기서 `or` 를 쓰면 위험하다.** 지금은 기본값이 `0.0` 이라 `score or 0.0` 도 우연히
같은 결과지만, 기본값이 `1.0` 이었다면 **진짜 점수 `0.0` 이 `1.0` 으로 둔갑한다.**

```python
0.0 or 1.0      # → 1.0    ← 0.0 이 falsy 라서 버려진다
```

**"값이 없다"와 "값이 0이다"를 구분해야 하는 자리에서는 항상 `is not None`.**
숫자·빈 문자열·빈 리스트가 정상 값일 수 있는 곳이 전부 여기 해당한다.

### 3.3 삼항 표현식 — 조건에 따라 다른 값

```python
return _copy(handle) if handle is not None else None              # runs.py:93
latest = handle.progress[-1] if handle.progress else "시작하는 중"  # run_progress.py:30
text = handle.error_message or "알 수 없는 오류로 실패했습니다."      # run_progress.py:36
```

`A if 조건 else B` 순서라 **값이 먼저, 조건이 나중**이다. 다른 언어의 `조건 ? A : B` 와
순서가 반대여서 처음엔 눈에 안 들어온다.

`progress[-1]` 은 **마지막 원소**다(음수 인덱스는 뒤에서부터 센다). 빈 리스트면
`IndexError` 가 나므로 앞의 조건이 그걸 막는다.

### 3.4 dict 에서 꺼낼 때

```python
handle = self._handles.get(run_id)               # 없으면 None (KeyError 아님)
if handle is not None:
    handle.progress.append(message)

self._handles.pop(run_id, None)                  # runs.py:170 — 없어도 조용히
```

| 표기 | 없을 때 |
|---|---|
| `d[key]` | `KeyError` 발생 |
| `d.get(key)` | `None` 반환 |
| `d.get(key, 기본값)` | 기본값 반환 |
| `d.pop(key, 기본값)` | 기본값 반환 (예외 없음) |

`runs.py` 의 갱신 메서드 넷(`append_progress`·`finish`·`fail`·`get`)이 전부 이 패턴이고,
독스트링에 **"없는 ID 면 조용히 넘어간다"** 라고 적혀 있다. 사용자가 대시보드에서 지운
실행을 스레드가 뒤늦게 갱신하려 할 수 있기 때문이다.

### 3.5 정리 — 셋 중 무엇을 쓸까

| 상황 | 쓸 것 |
|---|---|
| `""`·`0`·`[]` 를 "없음"으로 함께 접고 싶다 | `or` |
| `0`·`""` 가 **정상 값**이라 지켜야 한다 | `is not None` |
| 두 값 중 하나를 고르는 계산이다 | `A if 조건 else B` |
| dict 에 없을 수도 있다 | `.get()` / `.pop(key, None)` |

> **한 줄 정리** — `or` 는 falsy 전체를 접고 `is not None` 은 `None` 만 걸러 내며,
> 이 차이가 `0.0` 같은 값에서 버그가 된다.

---

## 4. 비동기 3종 (`async def` · `await` · `asyncio.run`)

### 4.1 `async def` 는 코루틴 함수

```python
async def run_pipeline(...) -> models.RunResult:     # nlm.py:133
```

일반 함수와 결정적으로 다른 점: **호출해도 실행되지 않는다.**

```python
coro = run_pipeline(url, questions, cb)   # 코루틴 객체만 만들어짐. 아무 일도 안 함
```

`await` 하거나 `asyncio.run` 에 넣어야 비로소 돈다. 이걸 모르면 **"함수를 불렀는데 왜
아무 일도 안 일어나지?"** 로 한참 헤맨다. (파이썬이 "coroutine was never awaited" 경고를
띄워 주긴 한다.)

이 경로의 `async def` 는 넷이다 — `run_pipeline`(133), `list_temp_notebooks`(202),
`delete_notebooks`(225), `_ask_one`(249).

### 4.2 `await` 는 "기다리는 동안 자리를 비켜 준다"

```python
notebook = await client.notebooks.create(...)    # nlm.py:163
source = await client.sources.add_url(...)       # nlm.py:168
result = await client.chat.ask(...)              # nlm.py:266
```

네트워크 응답을 기다리는 동안 **CPU 를 붙잡고 있지 않는다.** 코드는 위에서 아래로 순서대로
읽히지만, 그 지점에서 다른 작업이 끼어들 수 있다.

**`await` 는 `async def` 안에서만 쓸 수 있다.** 이 제약 때문에 `run_pipeline` 이 비동기면
그걸 부르는 쪽도 비동기여야 하고, 사슬이 위로 전파된다. 그 사슬이 끊기는 곳이 4.3 이다.

### 4.3 `asyncio.run` — 동기 세계에서 비동기로 들어가는 문

```python
result = asyncio.run(pipeline(url, questions, on_progress))   # runner.py:95
```

`_work` 는 평범한 동기 함수(스레드 본체)다. 그 안에서 비동기 코드를 돌리려면 **이벤트
루프를 만들어 코루틴을 끝까지 돌리고 결과를 꺼내는** 이 함수가 필요하다. **여기가 두
세계의 경계다.**

같은 경계가 세 군데 더 있다 — `auth.py:75`(인증 확인), `pages/maintenance.py`(정리 화면).

### 4.4 `async with`

```python
async with client_factory() as client:           # nlm.py:161, 216, 243
```

`with` 의 비동기판이다. 진입(`__aenter__`)과 종료(`__aexit__`)가 `await` 될 수 있어서,
접속과 정리에 네트워크가 필요한 자원에 쓴다. 역시 **`async def` 안에서만** 가능하다.

`try/finally` 안에 `await` 가 들어가는 형태(`nlm.py:188-192`)도 같은 맥락이다 —
**정리 코드조차 비동기**다.

### 4.5 가장 헷갈리는 지점 — 비동기와 스레드는 다른 것

이 프로젝트는 **둘을 겹쳐서** 쓴다.

| 도구 | 목적 | 위치 |
|---|---|---|
| **스레드** (`threading.Thread`) | 화면을 막지 않으려고 | `runner.py:54` |
| **비동기** (`async`/`await`) | 네트워크 대기 중 낭비를 줄이려고 | `nlm.py` 전반 |

구조는 이렇게 된다.

```
화면 스레드 ──▶ Thread 시작 ──┐
                              │
                     작업 스레드 (동기)
                              └─ asyncio.run(...)   ← 여기서 비동기 세계로
                                    └─ await, await, await ...
```

**`asyncio.run` 이 스레드 안에서 불린다.** 파이프라인 하나는 비동기로 돌지만, 그 전체가
별도 스레드에 얹혀 있어서 Streamlit 화면과 분리된다. 둘 중 하나만으로는 안 됐다 —
비동기만 쓰면 화면이 묶이고, 스레드만 쓰면 네트워크 대기가 그대로 낭비된다.

> **한 줄 정리** — `async def` 는 부른다고 실행되지 않고, `await` 는 `async` 안에서만 쓰며,
> `asyncio.run` 이 동기 코드에서 비동기로 들어가는 유일한 문이다.

---

## 부록 A. 요약

| # | 문법 | 한 줄 |
|---|---|---|
| 1 | 데이터클래스 | `frozen=True, slots=True` 가 기본형. `replace`+`list()` 로 리스트까지 떼어 낸 복사 |
| 2 | 컴프리헨션 | 대괄호면 즉시 리스트, 괄호면 하나씩 흘리는 제너레이터 |
| 3 | `None` 관용구 | `or` 는 falsy 전체를, `is not None` 은 `None` 만 |
| 4 | 비동기 3종 | 부른다고 실행 안 됨. `asyncio.run` 이 동기↔비동기 경계 |

## 부록 B. 자주 틀리는 세 가지

| 상황 | 잘못 | 올바르게 |
|---|---|---|
| 점수 `0.0` 을 기본값으로 채울 때 | `score or 1.0` → 진짜 `0.0` 이 사라짐 | `score if score is not None else 1.0` |
| `frozen` 객체의 리스트 필드 복사 | `replace(h)` → 리스트를 공유 | `replace(h, progress=list(h.progress))` |
| 코루틴 함수 호출 | `run_pipeline(...)` → 아무 일도 안 함 | `asyncio.run(run_pipeline(...))` |

## 부록 C. 코드 위치 색인

| 파일 | 줄 | 문법 |
|---|---|---|
| `core/models.py` | 8, 19, 28, 56, 71, 83 | `@dataclass(frozen=True, slots=True)` 6개 |
| | 48 | 기본값 있는 필드는 뒤에 |
| | 50 | `@property succeeded` |
| | 103-106, 123-126 | 컴프리헨션 / 제너레이터 |
| `services/runs.py` | 15 | `@dataclass(slots=True)` — **`frozen` 없는 유일한 것** |
| | 93 | 삼항 + `is not None` |
| | 102-104 | 리스트 컴프리헨션 (`reversed`) |
| | 113-117 | `sum` + 제너레이터 |
| | 128, 140, 155 | `.get()` 후 `None` 검사 (3회 반복) |
| | 170 | `.pop(key, None)` |
| | 175 | `dataclasses.replace` + `list(...)` |
| `services/nlm.py` | 133, 202, 225, 249 | `async def` |
| | 161, 216, 243 | `async with` |
| | 163, 168, 181, 192, 266 | `await` |
| | 175 | `source.title or None` |
| | 196 | `extract_video_id(url) or ""` |
| | 218-222 | 조건부 리스트 컴프리헨션 |
| | 317 | `score if score is not None else 0.0` |
| `services/runner.py` | 48 | 컴프리헨션 + 슬라이스 대입 |
| | 51 | `tuple(제너레이터)` |
| | 95 | `asyncio.run(...)` |
| `services/run_history.py` | 34-50 | `executemany` + 튜플의 리스트 |
| `core/youtube.py` | 40 | `(parsed.hostname or "").lower()` |
| `components/run_progress.py` | 30, 36 | 삼항 / `or` 기본값 |
| | 55, 58 | 필터 + `join(제너레이터)` |
