# 최초 실행 인증 코드로 배우는 파이썬 문법 5가지

> 온보딩 문서 [`docs/onboard/2026-09-01-first-run-authentication-flow.md`](../onboard/2026-09-01-first-run-authentication-flow.md) 의 짝 문서.
> 저쪽이 **"인증이 어떻게 흐르는가"** 라면, 이 문서는 **"그 코드에 쓰인 문법이 무엇인가"** 를 다룬다.
> 대상 코드: `services/auth.py` · `components/auth_gate.py` · `services/nlm.py` · `core/errors.py`
> 작성 2026-09-01 · 기준 커밋 `38a390f`

---

## 이 문서가 다루는 것

인증 경로 코드에서 **반복해서 등장하는** 문법 5가지다. 등장 횟수 기준으로 추렸다.

| # | 문법 | 왜 자주 나오나 |
|---|---|---|
| 1 | 함수를 값으로 주고받기 | `services/` 가 Streamlit 을 못 쓰므로 UI 를 콜백으로 주입받는다 |
| 2 | `Callable[...]` 과 타입 별칭 | 1번의 콜백을 타입으로 적으면 따라온다 |
| 3 | `Protocol` + 본문 `...` | 테스트가 가짜 객체를 끼워 넣을 수 있어야 한다 |
| 4 | `with` 컨텍스트 매니저 | 락·비동기 클라이언트·진행 상자 세 종류가 섞인다 |
| 5 | 예외를 튜플 변수로 모아 다루기 | 잡는 범위와 번역하는 범위를 한 곳에서 정의한다 |

---

## 1. 함수를 값으로 주고받기 (콜백 · 의존성 주입)

### 1.1 핵심 — 넘기는 것과 부르는 것은 별개의 사건

파이썬에서 함수는 **값**이다. 정수 `3` 을 변수에 담는 것과 문법적으로 똑같다.

```python
def greet(name):
    print(f"안녕 {name}")

f = greet        # 괄호 없음 — 함수 자체를 담음. 실행 안 됨
f("김철수")       # 여기서 비로소 실행
```

실행을 일으키는 건 오직 **괄호 `()`** 다. 이 프로젝트에서는 이렇게 나타난다.

```python
# auth.py:147
def __init__(self, probe=is_authenticated, login=run_login):
    self._probe = probe        # ← 넘기고 받고, 여전히 실행 안 됨
    self._login = login

# auth.py:224
self._ok = self._probe() or self._login(on_progress)   # ← 여기서 실행
```

### 1.2 괄호를 붙였다면 어떻게 달라지나

```python
def __init__(self, probe=is_authenticated()):   # ← 정의 시점에 딱 한 번 실행
    ...
```

클래스가 정의되는 순간(=모듈 import 시점) **실제로 NotebookLM 에 접속해 버린다.**
그 결과 `True`/`False` 가 영원히 기본값으로 굳고, 나중에 `self._probe()` 를 부르면
`bool` 은 호출 불가라 `TypeError` 가 난다.

> 기본 인자는 함수 정의 시점에 **한 번만** 평가된다. 가변 기본 인자(`def f(items=[])`)가
> 위험한 것도 같은 이유다. 다만 여기 담기는 건 함수 객체라서 문제가 없다.

### 1.3 실행 위치 — 별도 스레드가 아니라 부른 자리

```python
self._ok = self._probe() or self._login(on_progress)
```

`self._probe()` 는 **이 줄에서, 이 스레드로, 동기적으로** 실행된다. 함수 본문이 끝날
때까지 다음으로 넘어가지 않는다. **"콜백"이라고 해서 "나중에 알아서 불린다"는 뜻이 아니다.**
누가 언제 부르는지 코드에 그대로 적혀 있다.

실제 호출 사슬:

```
_verify()  ──▶ self._probe()          ⟹ 실제로는 is_authenticated()
                                          └─ asyncio.run(...)   ← 몇 초 블로킹
           ──▶ self._login(on_progress) ⟹ 실제로는 run_login(on_progress)
                                          └─ subprocess.Popen(...)
```

예외도 평범하게 전파된다. `is_authenticated` 안에서 `RuntimeError` 가 나면
`_verify()` → `ensure()` → `auth_gate._run()` 으로 그대로 올라간다. 콜백이라고 특별 취급되지 않는다.

### 1.4 어느 함수가 실행되는지는 런타임에 정해진다

```python
gate = AuthGate()                        # self._probe is is_authenticated
gate = AuthGate(probe=Recorder([True]))  # self._probe is Recorder 인스턴스
```

**`self._probe()` 라는 코드는 한 줄인데 실행되는 대상이 다르다.** 테스트가 이걸 이용한다
(`test_auth.py:190-194`). 프로덕션에서는 진짜 네트워크 함수가, 테스트에서는 정해진 값만
뱉는 가짜가 같은 자리에 들어간다. 이것이 **의존성 주입**이다.

### 1.5 계약은 이름이 아니라 시그니처

호출부가 `self._probe()` 라고 **인자 0개로** 부르므로, 여기 들어올 함수는 인자 없이 호출
가능해야 한다.

```python
def is_authenticated(client_factory=nlm.default_client_factory) -> bool:
```

인자가 있지만 **전부 기본값이 있어서** `is_authenticated()` 가 유효하다. 그래서
`ProbeLike = Callable[[], bool]`(`auth.py:55`)과 들어맞는다.

`self._login(on_progress)` 는 인자 1개로 부르므로, `run_login(on_progress, timeout=..., popen=...)`
의 나머지 두 개가 기본값을 가진 게 필수 조건이다.

### 1.6 바운드 메서드는 `self` 가 이미 붙어 있다

```python
# auth_gate.py:35
_run(gate.ensure, "인증 확인 중")

# auth_gate.py:61  (_run 내부)
ok = action(st.write)
```

`gate.ensure` 는 `AuthGate.ensure` 함수에 `gate` 인스턴스가 **묶인 새 객체**다.
그래서 `action(st.write)` 한 번이 `gate.ensure(st.write)` 가 되고, `self` 는 이미
채워져 있으므로 인자 하나만 넘기면 된다.

`st.write` 도 마찬가지로 그냥 함수 값이다. **호출하지 않고 넘겨서**, `services/` 가
Streamlit 을 import 하지 않고도 화면에 글을 쓰게 만든다.

### 1.7 등장 위치

| 위치 | 무엇 |
|---|---|
| `auth.py:60, 84, 147-148` | 기본 인자로 함수 객체 (`client_factory`, `popen`, `probe`, `login`) |
| `auth.py:82, 176, 193, 211` | `on_progress` 파라미터 |
| `auth.py:121, 129, 132, 223, 224` | 그 콜백 호출 |
| `auth_gate.py:35, 41` | 바운드 메서드 `gate.ensure` / `gate.relogin` 전달 |
| `auth_gate.py:61` | `action(st.write)` |

> **한 줄 정리** — 함수 이름 뒤에 괄호가 없으면 값이고, 괄호가 붙는 그 자리에서
> 그 시점에 동기적으로 실행된다. 어느 함수가 실행될지는 런타임에 정해진다.

---

## 2. `Callable[...]` 중첩 타입과 타입 별칭

### 2.1 왜 필요한가

타입 힌트는 "이 변수에 뭐가 들어오는지" 적는 것이다.

```python
name: str = "김철수"
scores: list[int] = [90, 80]
```

그런데 1장에서 봤듯 **함수도 변수에 담긴다.** 이때 `str` 도 `int` 도 아닌 무언가가 필요하다.

```python
f: Callable[[str], None] = greet
```

`Callable` 은 영어로 **"부를 수 있는 것"** 이라는 뜻이다.

### 2.2 읽는 법

```
Callable[[str], None]
         ─────  ────
         인자     반환
```

**"문자열 하나를 받고, 아무것도 안 돌려주는 함수"** 라고 읽는다.
앞칸은 인자 목록, 뒷칸은 반환 타입. **딱 두 칸이다.**

| 함수 정의 | 타입 표기 |
|---|---|
| `def f(x: str) -> None` | `Callable[[str], None]` |
| `def f(x: int) -> bool` | `Callable[[int], bool]` |
| `def f(a: int, b: int) -> int` | `Callable[[int, int], int]` |
| `def f() -> bool` | `Callable[[], bool]` |

**함수 정의를 그대로 옮겨 적는 것**이다. 인자 타입들을 순서대로 앞칸에, 화살표 뒤
반환 타입을 뒷칸에.

반환이 없는 함수(= `return` 문이 없는 함수)는 반환 타입이 `None` 이다. "돌려줄 게 없다"를
`None` 으로 적는다.

### 2.3 가장 많이 틀리는 것 — 안쪽 대괄호

인자 목록은 **항상 대괄호로 감싼다.** 인자가 하나여도, 없어도 마찬가지다.

```python
Callable[[str], None]      # (O) 인자 1개
Callable[str, None]        # (X) 대괄호 빠짐 → 에러

Callable[[], bool]         # (O) 인자 0개 — 빈 대괄호
Callable[bool]             # (X) 칸이 하나뿐 → 에러
```

그래서 대괄호가 2겹으로 보인다.

```python
Callable[ [str] , None ]
        └─ 이건 인자 목록
```

바깥 대괄호는 "Callable 에 정보를 넣는 괄호", 안쪽은 "인자들의 목록"이다. **역할이 다른
두 괄호가 붙어 있을 뿐이다.**

### 2.4 중첩된 것 읽기

가장 복잡해 보이는 것.

```python
LoginLike = Callable[[Callable[[str], None]], bool]     # auth.py:56
```

**안쪽부터** 읽으면 어렵지 않다.

**1단계** — 안쪽 덩어리를 이름으로 바꿔 본다.

```python
Callable[[str], None]    →   "진행콜백"
```

**2단계** — 그 자리에 끼워 넣는다.

```python
Callable[[ 진행콜백 ], bool]
```

→ **"진행콜백 하나를 인자로 받아 `bool` 을 돌려주는 함수"**

`run_login` 의 모양 그대로다.

```python
def run_login(on_progress: Callable[[str], None], ...) -> bool:
      ↑         ↑                                        ↑
   이 함수가   진행콜백을 인자로 받고              bool 을 돌려준다
```

**함수를 인자로 받는 함수**라서 `Callable` 이 `Callable` 안에 들어갔다. 대괄호가 3겹으로
보이는 이유는 이것뿐이다.

### 2.5 실제로 쓰인 곳

```python
# auth.py:82 — 진행 콜백
def run_login(on_progress: Callable[[str], None], ...) -> bool:
```

여기 들어오는 건 `st.write` 다(`auth_gate.py:61`). `st.write("안녕")` 은 화면에 글자를
찍고 끝난다 — 문자열을 받고, 돌려주는 값이 없다. 그래서 들어맞는다.

```python
# auth.py:55 — 확인 함수
ProbeLike = Callable[[], bool]
```

**"인자 없이 부를 수 있고 `True`/`False` 를 주는 함수"**. `is_authenticated()` 가 이 모양이다.

### 2.6 타입 별칭 — 이름 붙여 두기

```python
PopenLike = Callable[..., ProcessLike]                    # auth.py:54
ProbeLike = Callable[[], bool]                            # auth.py:55
LoginLike = Callable[[Callable[[str], None]], bool]       # auth.py:56
_ProgressAction = Callable[[Callable[[str], None]], bool] # auth_gate.py:20
```

새로운 문법이 아니라 **그냥 변수 대입**이다. 오른쪽 타입 표기에 이름을 붙여 재사용한다.
이름 끝의 `-Like` 는 "이런 모양의 것"이라는 이 프로젝트의 명명 관례다.

이득이 셋 있다.

1. **시그니처가 읽힌다.** `def __init__(self, probe: ProbeLike = ..., login: LoginLike = ...)`
   가 중첩 대괄호로 도배되지 않는다.
2. **한 곳만 고치면 된다.** 진행 콜백이 다른 걸 받게 되면 별칭 하나만 바뀐다.
3. **이름이 의도를 말한다.** `ProbeLike` 와 `LoginLike` 는 구조가 달라도 역할을 드러낸다.

`_ProgressAction` 은 `LoginLike` 와 글자까지 똑같은 타입인데, 파일이 달라 이름만 따로 붙었다.

### 2.7 세 종류의 `...` 구분 — 이 코드베이스에서 가장 헷갈리는 부분

같은 `...` 이 **위치에 따라 세 가지 뜻**으로 쓰인다.

| 위치 | 표기 | 의미 |
|---|---|---|
| `auth.py:54` | `Callable[..., ProcessLike]` | **인자는 아무거나** (개수·타입 검사 포기) |
| `auth.py:43` | `def stdout(self): ...` | **본문 없음** (`Ellipsis` 값 한 줄) |
| `errors.py:17` | `tuple[type[Exception], ...]` | **길이 미정의 동종 튜플** |

`PopenLike = Callable[..., ProcessLike]` 에서 `...` 을 쓴 이유는, `subprocess.Popen` 의
인자가 20개가 넘고 이 코드가 그중 7개를 키워드로 넘기기 때문이다. 전부 타입으로 적는 건
실익이 없어 **"인자는 안 보고 반환값만 본다"** 로 뒀다.

### 2.8 인자·반환의 방향

타입 검사기는 함수 타입을 **인자는 넓게, 반환은 좁게** 허용한다.

```python
Callable[[str], None]   자리에

def f(x: str) -> None          # OK  (정확히 일치)
def g(x: object) -> None       # OK  (더 넓은 인자 — str 도 object 니까)
def h(x: str) -> bool          # OK  (반환값을 버리는 자리라 허용)
def i(x: int) -> None          # NG  (str 을 못 받음)
```

`st.write` 가 `Callable[[str], None]` 자리에 들어가는 것도 이 규칙 덕이다.
`st.write` 는 실제로는 훨씬 넓은 인자를 받는다.

### 2.9 import 위치

```python
from collections.abc import Callable, Iterable    # auth.py:16
```

`typing.Callable` 은 구식이다. `list[str]` 을 쓰고 `typing.List` 를 안 쓰는 것과 같은 맥락.

이 프로젝트 규칙은 원래 "개별 심볼 import 금지"인데, `typing`·`collections.abc` 는 예외로
허용된다. 그래서 이 줄은 규칙 위반이 아니다.

> **한 줄 정리** — `Callable[[받는것들], 돌려주는것]` 은 **함수 정의를 타입 표기로 옮겨
> 적은 것**이고, 안쪽 대괄호는 인자가 하나든 없든 항상 붙는다.

---

## 3. `Protocol` + 본문 `...`

### 3.1 출발점 — 파이썬은 원래 타입을 안 본다

```python
def make_sound(animal):
    animal.speak()          # speak() 만 있으면 뭐든 상관없음
```

개든 오리든 로봇이든 `speak()` 만 있으면 돌아간다. 이걸 **덕 타이핑**이라고 한다 —
"오리처럼 꽥꽥거리면 오리로 친다".

파이썬의 큰 장점인데, **타입 힌트를 붙이려 하면 곤란해진다.**

```python
def make_sound(animal: ???) -> None:
```

`???` 자리에 "`speak()` 가 있는 아무거나"를 적을 방법이 없다.

### 3.2 옛날 방법 — 상속으로 묶기

```python
class Animal:
    def speak(self) -> None: ...

class Dog(Animal):          # ← 반드시 Animal 을 상속해야 함
    def speak(self) -> None:
        print("멍")
```

**명목적 타이핑**이다. "`Animal` 이라고 **선언**해야 `Animal` 로 인정".

문제는 **남이 만든 클래스에는 이걸 못 시킨다는 것**이다. 라이브러리의 `Popen` 에게
"우리 `Animal` 을 상속해라"라고 할 수는 없다.

### 3.3 Protocol — 모양으로 타입 적기

```python
from typing import Protocol

class Speaker(Protocol):        # ← 이게 Protocol
    def speak(self) -> None: ...

class Dog:                      # ← Speaker 를 상속하지 않음!
    def speak(self) -> None:
        print("멍")

def make_sound(animal: Speaker) -> None:
    animal.speak()

make_sound(Dog())               # 통과. speak() 가 있으니까
```

`Dog` 는 `Speaker` 의 존재조차 모른다. 그래도 **모양이 맞아서** 통과한다.
이게 **구조적 타이핑**이다.

| | 인정 기준 |
|---|---|
| 상속 (`class Dog(Animal)`) | **선언**했으면 그 타입 |
| Protocol | **모양**이 맞으면 그 타입 |

Protocol 은 파이썬의 덕 타이핑을 **타입 검사기가 이해할 수 있게 적어 둔 것**이다.

### 3.4 문법 세 가지

**① `Protocol` 을 상속해서 선언한다**

```python
class Speaker(Protocol):
```

`Protocol` 이 붙은 클래스는 "실제로 만들어 쓸 물건"이 아니라 **"모양을 적어 둔 명세서"** 다.

**② 멤버를 적는다** — 메서드는 `def`, 속성은 `이름: 타입`

```python
class ProcessLike(Protocol):          # auth.py:37 — 메서드
    @property
    def stdout(self) -> Iterable[str] | None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def kill(self) -> None: ...

class ReferenceLike(Protocol):        # nlm.py:17 — 속성
    citation_number: int | None
    cited_text: str | None
    score: float | None

class ClientLike(Protocol):           # nlm.py:98 — 중첩 Protocol
    chat: ChatLike
    notebooks: NotebooksLike
    sources: SourcesLike
```

`stdout` 만 `@property` 로 선언된 건 **읽기 전용**임을 표현하기 위해서다. 속성 방식으로
적으면 "쓸 수도 있다"는 뜻이 된다.

`ClientLike` 는 Protocol 이 Protocol 을 품는 형태다. `client.chat.ask(...)` 같은 다단계
접근이 전부 타입 검사된다.

**③ 본문은 `...` 로 둔다**

```python
def speak(self) -> None: ...       # 관례
def speak(self) -> None: pass      # 같은 효과
```

이 `...` 은 **`Ellipsis` 라는 값**이고, 여기서는 `pass` 와 같은 뜻이다. "몸통 없음"을
나타내는 관례적 표기이며, **여기에 실제 코드를 적지 않는다.** 명세서니까.

### 3.5 가장 중요한 것 — 실행 중엔 아무 일도 안 한다

가장 많이 하는 오해다.

```python
def make_sound(animal: Speaker) -> None:
    animal.speak()

make_sound(42)          # 실행하면? → AttributeError. 그냥 터짐
```

Protocol 은 **mypy 같은 검사 도구만 읽는다.** 파이썬이 실행할 때는 타입 힌트를 무시한다.
위 코드는 `uv run mypy` 에서 걸리지만, 그냥 실행하면 평소처럼 `AttributeError` 가 난다.

**Protocol 은 실행을 막아 주는 장치가 아니라, 코드를 짜는 동안 실수를 미리 알려 주는
장치다.**

`isinstance(x, Speaker)` 도 기본적으로는 못 쓴다. 쓰려면 `@runtime_checkable` 을 붙여야
하고, 그것도 **메서드 이름이 있는지만** 보지 시그니처는 안 본다. 이 프로젝트는 필요가
없어서 쓰지 않는다.

### 3.6 실제로 쓰인 곳

```python
# auth.py:37
class ProcessLike(Protocol):
    @property
    def stdout(self) -> Iterable[str] | None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def kill(self) -> None: ...
```

**"`stdout` 이 있고 `wait()` 와 `kill()` 을 가진 아무거나"** 라는 뜻이고, 여기에 둘이 들어간다.

| 들어오는 것 | 언제 | 상속 관계 |
|---|---|---|
| `subprocess.Popen` | 실제 실행 | **없음** |
| `FakeProcess` (`test_auth.py:25`) | 테스트 | **없음** |

둘 다 `ProcessLike` 를 상속하지 않는다. 모양만 맞다. **진짜 브라우저를 띄우지 않고
테스트할 수 있는 게 이 덕분이다.**

### 3.7 "최소한의 모양"만 적는다

```python
# nlm.py:73
class SourceLike(Protocol):
    """...라이브러리의 ``Source`` 는 필드가 많지만 파이프라인은 제목만 쓴다."""
    title: str | None
```

라이브러리의 진짜 `Source` 에 필드가 20개 있어도, **이 코드가 쓰는 건 `title` 하나**라서
그것만 적었다.

이게 Protocol 의 요령이다. **적게 요구할수록 좋다.** 요구가 적으면 들어맞는 객체가
많아지고, 테스트용 가짜도 한 줄로 만들 수 있다.

### 3.8 왜 ABC 가 아니라 Protocol 인가

`abc.ABC` 로 만들면 **가짜 객체가 반드시 그 ABC 를 상속해야** 한다. 남의 라이브러리
클래스(`subprocess.Popen`, `NotebookLMClient`)는 우리 ABC 를 상속할 수 없으므로 애초에
불가능하다. Protocol 은 **소유하지 않은 타입에도 사후에 적용**된다.

이유는 결국 하나다 — **테스트에서 진짜 대신 가짜를 끼워 넣기 위해서.**

```python
auth.run_login(콜백)                       # 진짜: 브라우저를 띄운다
auth.run_login(콜백, popen=fake_popen)     # 테스트: 아무것도 실행하지 않는다
```

`popen` 자리의 타입이 진짜 `Popen` 으로 못 박혀 있었다면 가짜를 넣는 순간 mypy 가
거부했을 것이다.

### 3.9 그런데 왜 `cast` 가 필요한가

```python
# nlm.py:127
return cast(
    contextlib.AbstractAsyncContextManager[ClientLike],
    notebooklm.NotebookLMClient.from_storage(allow_headless=True),
)
```

주석대로 "라이브러리 클래스는 위 Protocol 을 선언하지 않으므로 경계에서 한 번만 캐스팅"한다.
구조적 타이핑이라도 라이브러리의 반환 타입 정보가 불충분하면 검사기가 스스로 연결하지
못한다. `cast` 는 **런타임에 아무 일도 하지 않고** 검사기에게만 "이 타입으로 봐라"라고
말한다. 그래서 경계 한 곳에만 두고, 내부는 Protocol 로 정상 검사받게 한다.

### 3.10 헷갈리기 쉬운 두 가지

**① `...` 이 여러 뜻으로 나온다** (→ 2.7 표)
클래스 본문에 있으면 "구현 없음"이다.

**② Protocol 클래스는 만들어 쓰지 않는다**

```python
p = ProcessLike()        # 이렇게 쓰는 물건이 아님
```

명세서일 뿐이라 인스턴스를 만들 일이 없다. **타입 힌트 자리에만 등장한다.**

> **한 줄 정리** — `class X(Protocol):` 은 **"이런 멤버를 가진 것"이라는 모양의 명세서**이고,
> 상속 없이 모양만 맞으면 인정되며, 실행 중이 아니라 **타입 검사할 때만** 쓰인다.

---

## 4. `with` 컨텍스트 매니저 (세 종류가 섞여 나옴)

### 4.1 무엇인가

"들어갈 때 무언가 하고, **어떻게 빠져나가든** 뒷정리를 보장"하는 구문이다.
예외가 나든, `return` 하든, 정상 종료하든 마무리가 실행된다.

인증 경로에는 세 종류가 섞여 나온다.

```python
with self._lock:                  # auth.py:188  — 잠그고, 예외가 나도 반드시 푼다
    ...
async with client_factory():      # auth.py:236  — 비동기 진입/종료
    return
with st.status(label) as status:  # auth_gate.py:60 — 상자를 열고 닫는다
    ...
```

| 위치 | 대상 | 들어갈 때 | 나올 때 |
|---|---|---|---|
| `auth.py:188, 208` | `threading.Lock` | 락 획득 | 락 해제 |
| `auth.py:236` | 비동기 클라이언트 | 접속·인증 확인 | 접속 정리 |
| `auth_gate.py:60` | `st.status` | 진행 상자 표시 | 상자 마감 |

### 4.2 헷갈리는 지점 ① — `async with`

`with` 의 비동기판이다. `__enter__`/`__exit__` 대신 `__aenter__`/`__aexit__` 를 부르며,
**`async def` 함수 안에서만** 쓸 수 있다.

```python
# auth.py:228
async def _open_once(client_factory: nlm.ClientFactory) -> None:
    async with client_factory():
        return
```

`async with ...: return` 이 이상해 보이는데, **여는 행위 자체가 목적**이라 몸통이 비어 있는
것이다. 열렸다 = 인증이 살아 있다. 그래서 요청을 하나도 보내지 않는다.

### 4.3 헷갈리는 지점 ② — `threading.Lock` 은 재진입이 안 된다

같은 스레드가 이미 쥔 락을 **또 잡으면 자기 자신과 교착**한다.

```python
# auth.py:188
def ensure(self, on_progress) -> bool:
    with self._lock:
        if self._tried:
            return self._ok
        return self._verify(on_progress)     # ← _verify 는 락을 잡지 않는다
```

그래서 `_verify()` 는 락을 잡지 않고, 대신 이렇게만 적혀 있다.

```python
"""...

호출자가 ``self._lock`` 을 쥔 채로 불러야 한다.
"""
```

**코드가 강제하지 않는 규약**이라, 이 부분을 고칠 때는 주의해야 한다. `_verify()` 안에
`with self._lock:` 을 넣으면 앱이 그 자리에서 멈춘다.

> 참고: 재진입이 필요하면 `threading.RLock` 을 쓴다. 이 코드는 규약으로 해결했다.

### 4.4 이 락이 막는 것과 못 막는 것

`threading.Lock` 은 **같은 프로세스 안의** Streamlit 세션 스레드들을 막는다.
탭을 세 개 열어도 브라우저 로그인 창은 하나만 뜬다.

반대로 앱 자체를 두 번 띄우면(프로세스가 둘) 창이 두 개 뜬다. 프로세스 간 잠금은 아니다.

> **한 줄 정리** — `with` 는 **뒷정리 보장**이 핵심이고, `async` 가 붙으면 비동기판이며,
> `threading.Lock` 은 재진입이 안 되므로 "누가 락을 쥐는가"를 코드 밖 규약으로 관리하는
> 부분이 있다.

---

## 5. 예외를 튜플 변수로 모아 다루기

### 5.1 `except` 는 원래 튜플을 받는다

```python
except (ValueError, TypeError):        # 흔히 보는 형태
except SOME_TUPLE_VARIABLE:            # 변수여도 됨 — 같은 것
```

파이썬은 `except` 뒤의 **값**을 평가해서, 그게 예외 클래스이거나 예외 클래스의 튜플이면
받아들인다. **리터럴이어야 한다는 제약이 없다.**

```python
except errors.MAPPED_ERRORS:           # auth.py:76
    return False
```

`isinstance` 도 같은 규칙이라 튜플을 그대로 넘길 수 있다.

```python
if isinstance(error, _LOGIN_ERRORS):   # errors.py:85
```

> `errors.py:78-81` 에는 `isinstance(error, A | B)` 형태도 있다. `isinstance` 는 튜플과
> `|` 유니온을 **둘 다** 받는다. 한 파일에 두 표기가 공존하는 건 이유가 있다 —
> 고정된 두 개는 `|` 로 인라인, 조건부로 늘었다 줄었다 하는 목록은 변수 튜플로.

### 5.2 `type[Exception]` — 인스턴스가 아니라 클래스

```python
MAPPED_ERRORS: tuple[type[Exception], ...]
```

| 표기 | 가리키는 것 | 예 |
|---|---|---|
| `Exception` | 예외 **인스턴스** | `ValueError("boom")` |
| `type[Exception]` | 예외 **클래스 자체** | `ValueError` |

`except` 와 `isinstance` 에 넘기는 건 클래스이므로 `type[...]` 이 맞다.
`raise` 하는 대상이나 `as error` 로 받는 값은 인스턴스다.

### 5.3 `tuple[X, ...]` — 또 다른 `...`

```python
tuple[int, str]        # 정확히 2개, 첫째 int 둘째 str   (고정 길이)
tuple[int, ...]        # int 가 0개 이상                (가변 길이)
```

여기서 `...` 은 **"길이를 정하지 않겠다"** 는 표기다(→ 2.7 세 종류의 `...`).
예외 목록은 조건부 import 결과에 따라 1개일 수도 2개일 수도 있어서 이 형태가 필요하다.

### 5.4 `*` 언패킹

```python
MAPPED_ERRORS = (
    exceptions.NotebookLMError,
    *_LOGIN_REDIRECT_ERRORS,        # errors.py:25
)
```

`*` 는 튜플을 **펼쳐서** 넣는다. 중첩이 아니라 평탄화다.

```python
_LOGIN_REDIRECT_ERRORS = (_LoginRedirectError,)
→ MAPPED_ERRORS = (NotebookLMError, _LoginRedirectError)      # 2개

_LOGIN_REDIRECT_ERRORS = ()
→ MAPPED_ERRORS = (NotebookLMError,)                          # 1개
```

`*` 없이 그냥 넣었다면 `(NotebookLMError, (_LoginRedirectError,))` 라는 **중첩 튜플**이
되고, `except` 에 넘기면 `TypeError` 가 난다.

### 5.5 조건부 import + 빈 튜플 폴백

```python
try:                                                    # errors.py:14
    from notebooklm._auth import extraction as _auth_extraction

    _LOGIN_REDIRECT_ERRORS: tuple[type[Exception], ...] = (
        _auth_extraction._LoginRedirectError,
    )
except (ImportError, AttributeError):   # pragma: no cover
    _LOGIN_REDIRECT_ERRORS = ()
```

읽을 점이 넷이다.

1. **모듈 최상위의 `try`** — import 는 함수 안이 아니어도 실패할 수 있다.
2. **`(x,)` 의 쉼표** — 원소 하나짜리 튜플이다. 쉼표가 없으면 그냥 클래스 하나가 되고
   `*` 언패킹이 깨진다.
3. **두 예외를 잡는 이유** — 모듈이 통째로 사라지면 `ImportError`, 모듈은 있는데 클래스
   이름이 바뀌면 `AttributeError` 다.
4. **빈 튜플로 떨어뜨림** — 실패해도 앱은 뜬다. 매핑만 포기하고 나머지 예외 처리는 정상
   작동한다.

`_LoginRedirectError` 는 이름 앞 `_` 가 두 번 나오는 private 접근이다(`_auth` 모듈,
`_LoginRedirectError` 클래스). 남의 라이브러리 내부에 손을 대는 거라 언제든 깨질 수 있고,
그래서 이렇게 방어적으로 감쌌다.

### 5.6 왜 굳이 이 클래스를 잡아야 했나

라이브러리 예외는 보통 `NotebookLMError` 아래에 모여 있다. 그런데 토큰 조회가 구글 로그인
화면으로 튕기는 경우, 라이브러리가 이걸 **공개 예외로 감싸지 않고 private `ValueError`
하위 클래스로** 흘린다(`errors.py:8-11`).

`NotebookLMError` 만 잡으면 이게 빠져나가서 화면에 **내부 클래스명과 구글 URL 이 그대로
노출된다.** 라이브러리 자신의 CLI 도 이걸 "Unexpected error" 로 흘린다고 주석에 적혀 있다.

### 5.7 목록을 상수로 묶은 진짜 이유

```python
"""``to_message`` 가 화면 문구로 바꿀 수 있는 예외들.

호출자는 이 튜플로 ``except`` 를 잡는다. 잡는 범위와 바꾸는 범위를 한
곳에서 같이 정의해 두면 둘이 어긋나지 않는다.
"""
```

`auth.py:76` 이 **잡는 범위**와 `to_message()` 가 **번역할 수 있는 범위**가 같아야 한다.
따로 적어 두면 한쪽만 늘어났을 때, 잡히긴 했는데 번역이 안 되는 예외가 생기고 화면에
엉뚱한 기본 문구가 뜬다. **상수 하나가 두 범위의 단일 출처 역할**을 한다.

> **한 줄 정리** — `except` 와 `isinstance` 는 예외 클래스의 **튜플**을 받으므로 목록을
> 변수로 뺄 수 있고, 그 덕에 "잡는 범위"를 한 곳에서 정의하고 조건부로 늘렸다 줄였다 할 수 있다.
