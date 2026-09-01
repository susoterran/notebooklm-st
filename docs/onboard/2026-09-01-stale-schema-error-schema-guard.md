# StaleSchemaError — 마이그레이션 없는 프로젝트의 스키마 가드

> 대상 코드: `src/notebooklm_st/services/store.py`, `src/notebooklm_st/components/schema_gate.py`
> 작성 2026-09-01 · 기준 커밋 `38a390f`

---

## 1. 한 줄 요약

`StaleSchemaError` 는 **"지금 열려는 DB 파일이 현재 코드가 기대하는 스키마가 아니다"** 를
알리는 전용 예외 타입이다. 클래스 본문은 독스트링뿐이고, 판정 로직은 전부
`store._verify_schema()` 에 있다.

---

## 2. 왜 필요한가 — 의도된 "마이그레이션 없음"

이 프로젝트는 **스키마 마이그레이션 경로를 두지 않기로 결정했다**(`store.py:46-49` 주석).
개인용 도구이고 DB 는 `questions.db` 파일 하나뿐이라, 스키마가 바뀌면 해결책이
"예전 파일을 지우고 새로 만든다" 하나뿐이다.

문제는 그 상황이 **조용히 통과한다**는 점이다.

```python
connection.executescript(_SCHEMA)   # store.py:114
```

`_SCHEMA` 안의 문장은 전부 `CREATE TABLE IF NOT EXISTS` 다. 이 구문은 테이블이 이미
있으면 **아무것도 하지 않는다.** 컬럼이 부족해도 손대지 않는다.

그래서 가드가 없으면 이런 일이 벌어진다.

| 시점 | 일어나는 일 |
|---|---|
| 코드에 컬럼 추가 | `_SCHEMA` 만 바뀐다 |
| 앱 기동 | 예전 `questions.db` 로 연결 **성공** (`IF NOT EXISTS` 가 무시) |
| 한참 뒤 질의/이력 화면 | `sqlite3.OperationalError: no such column: ...` 로 엉뚱한 데서 터짐 |

사용자는 "이력 페이지가 깨졌다"고 인식하지만 진짜 원인은 DB 파일이다.
`_verify_schema()` 가 이 간극을 **연결 시점으로 앞당긴다.**

---

## 3. 동작 흐름

```
connect(db_path)                                  # store.py:95
  ├ sqlite3.connect(check_same_thread=False)      # Streamlit 재실행 스레드 대응
  ├ row_factory = sqlite3.Row
  ├ PRAGMA foreign_keys = ON
  ├ executescript(_SCHEMA)                        # 없는 테이블만 새로 생성
  ├ commit()
  └ _verify_schema(connection, db_path)           # store.py:120
       └ _EXPECTED_COLUMNS 의 테이블마다:
            PRAGMA table_info(<table>)  →  실제 컬럼 이름 집합
            missing = 기대 컬럼 − 실제 컬럼
            missing 이 비어 있지 않으면 → raise StaleSchemaError(안내 메시지)
```

판정은 **집합 차집합** 하나다.

- **기대값**: `_EXPECTED_COLUMNS`(`store.py:53`) — `questions` / `runs` / `answers`
  세 테이블의 컬럼 이름을 `frozenset` 으로 박아 둔 상수. 코드가 기대하는 스키마의
  단일 출처다.
- **현실값**: `PRAGMA table_info(<table>)` 결과의 `name` 컬럼 — 파일에 실제로 있는 컬럼.

```python
missing = expected - actual
```

`missing` 이 비어 있지 않다 = 코드는 아는데 파일에는 없는 컬럼이 있다 = 파일이 낡았다.

> **반대 방향은 검사하지 않는다.** 파일에만 있고 코드가 모르는 여분 컬럼은 통과한다.
> `SELECT` 는 컬럼을 이름으로 지정하므로 여분 컬럼이 있어도 동작이 깨지지 않기 때문이다.

### SQL 인젝션이 아닌 이유

```python
rows = connection.execute(f"PRAGMA table_info({table})")
```

`PRAGMA` 는 파라미터 바인딩을 지원하지 않아 f-string 을 쓸 수밖에 없다.
안전한 근거는 `table` 이 **`_EXPECTED_COLUMNS` 의 리터럴 키에서만** 온다는 것이다
(`store.py:51-52`, `store.py:138` 주석). 사용자 입력이 이 경로에 닿지 않는다.

---

## 4. 누가 잡는가 — `components/schema_gate.py`

```python
def render() -> None:
    try:
        session.get_connection()
    except store.StaleSchemaError as error:
        st.error(str(error))
        st.stop()
```

앱이 뜰 때 **가장 먼저** 커넥션을 한 번 열어 보는 게 전부다. 성공하면 조용히 지나가고,
실패하면 사람이 읽을 수 있는 안내로 바꾸고 `st.stop()` 으로 멈춘다.

메시지를 가공하지 않고 `str(error)` 를 그대로 넘기는데, 예외 메시지가 이미 필요한 정보를
다 담고 있기 때문이다(`store.py:143-148`).

예를 들어 `runs.title` 이 없는 예전 파일이라면 이렇게 나온다.

```
<경로>/no_title.db 의 runs 테이블이 오래된 스키마입니다
(없는 컬럼: ['title']). 이 파일을 지우고 다시 실행하세요.
저장된 질문 템플릿과 실행 이력이 함께 사라집니다.
```

파일 경로 · 어떤 테이블 · 어떤 컬럼 · 할 일 · **부작용 경고**까지 한 덩어리다.
마지막 문장이 중요하다 — "지우세요"만 있으면 사용자가 이력이 날아가는 걸 모른 채 지운다.

### 왜 전용 타입이어야 하는가

`RuntimeError` 를 그대로 던졌다면 `schema_gate` 의 `except` 가 **다른 런타임 오류까지**
같이 잡는다. 그러면 진짜 버그가 "DB 파일을 지우세요"라는 **잘못된 안내로 덮인다.**
사용자는 멀쩡한 이력을 지우고, 원인은 그대로 남는다.

전용 타입의 존재 이유는 `except store.StaleSchemaError` 라고 **좁게** 잡을 수 있게 하는 것,
그 하나다.

---

## 5. 클래스 본문이 비어 있는 이유

```python
class StaleSchemaError(RuntimeError):
    """DB 파일의 스키마가 현재 코드가 기대하는 컬럼과 맞지 않는다.

    이 프로젝트는 마이그레이션 경로를 두지 않기로 했다(의도된
    결정). 스키마가 바뀌면 예전 DB 파일을 지우고 새로 만드는 것이
    유일한 해법이며, 이 예외의 메시지가 그 안내를 담는다.
    """
```

**예외 클래스는 타입 자체가 정보다.** 세 가지로 나뉜다.

### (1) 필요한 기능은 전부 상속받는다

`RuntimeError` 가 `__init__` · `args` · `__str__` 을 이미 제공한다.
`StaleSchemaError("메시지")` 가 그대로 동작하고 `str(error)` 도 그대로 나온다.
덧붙일 게 없다.

### (2) 들고 다닐 상태가 없다

`missing_columns` 같은 필드를 추가할 수도 있었지만, 잡는 쪽(`schema_gate`)이 하는 일은
`str(error)` 를 출력하는 것뿐이다. 아무도 안 읽는 필드를 만들 이유가 없다.

### (3) 메시지는 raise 시점에 만들어진다

어떤 테이블의 어떤 컬럼이 빠졌는지는 `_verify_schema()` 만 안다.
안내 문구를 클래스 안에 고정해 둘 수 없다.

### `pass` 조차 필요 없다

Python 에서 **독스트링은 그 자체로 유효한 문장**이라, 독스트링만 있으면 본문이 채워진
것으로 취급된다. 게다가 이 프로젝트의 ruff 설정은 `D` 규칙(pydocstyle)을 켜 두고 있어
클래스 독스트링이 어차피 필수다. `pass` 를 덧붙이면 군더더기다.

이건 Python 에서 도메인 전용 예외를 만드는 **표준 관용구**다.

```python
class MyError(BaseError):
    """언제 발생하는지 설명."""
```

---

## 6. 스키마를 바꿀 때 해야 할 일

컬럼을 추가·변경하면 **두 곳을 함께** 고쳐야 한다. 하나만 고치면 가드가 무력해진다.

1. `_SCHEMA`(`store.py:17`) — `CREATE TABLE` 문
2. `_EXPECTED_COLUMNS`(`store.py:53`) — 검증용 컬럼 집합

`_SCHEMA` 만 고치면 새 DB 는 잘 만들어지지만 **낡은 파일이 검증을 통과해** 3장의
`OperationalError` 시나리오로 돌아간다. 두 상수가 짝이라는 점을 기억할 것.

로컬 DB 를 새로 만드는 방법은 파일을 지우는 것뿐이다.

```powershell
Remove-Item questions.db      # 질문 템플릿과 실행 이력이 함께 사라진다
```

`NOTEBOOKLM_ST_DB` 환경 변수로 경로를 덮어쓸 수 있다(`default_db_path()`, `store.py:79`).
테스트가 임시 디렉터리를 가리키는 것도 이 변수를 쓴다.

---

## 7. 관련 테스트

| 테스트 | 검증 내용 |
|---|---|
| `test_store.py:58` | 낡은 `questions` 테이블 → 예외 발생, 메시지에 **DB 경로**와 테이블 이름이 들어간다 |
| `test_store.py:63` | `test_connect_accepts_a_fresh_database` — 새로 만든 DB 는 그대로 통과 |
| `test_store.py:107` | `runs.title` 누락 → 메시지에 테이블·컬럼 이름과 **"질문 템플릿"** 경고가 들어간다 |
| `test_components.py:486` | `schema_gate` 가 트레이스백 대신 안내 화면을 그리는지 (`get_connection` 을 monkeypatch) |

메시지 문구를 문자열로 assert 한다는 점이 눈에 띈다. 이 예외는 **메시지가 곧 UI** 라서
(4장) 안내 문구가 계약의 일부다. 문구를 고칠 때 테스트도 같이 봐야 한다.

---

## 8. 정리

- `IF NOT EXISTS` 는 낡은 테이블을 고쳐 주지 않는다 → 명시적 검증이 필요하다.
- 검증은 `_EXPECTED_COLUMNS`(기대)와 `PRAGMA table_info`(현실)의 차집합 하나다.
- 실패는 **연결 시점에** 터진다. 나중에 엉뚱한 쿼리에서 터지지 않는다.
- 전용 예외 타입은 `schema_gate` 가 이 상황만 **좁게** 잡기 위한 것이다.
- 본문이 빈 건 미완성이 아니라 **의도된 최소 형태**다. 상속만으로 충분하다.
