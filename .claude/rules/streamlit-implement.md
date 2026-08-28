---
description: This guide defines the definitive Python best practices for our team, focusing on readability, maintainability, and modern development standards. Adhere to these rules for consistent, high-quality Python code.
paths:
  - "**/*.py"
  - "pyproject.toml"
---

<!--
유지보수 노트 (Claude 컨텍스트에는 주입되지 않음)
- 패키지명 `myapp` 은 실제 패키지 이름으로 일괄 치환할 것.
- frontmatter 의 paths 를 지우면 이 규칙이 모든 세션 시작 시 항상 로드된다.
-->

# Python / Streamlit 작성 규칙

대상은 **Python 3.13 + Streamlit 웹앱**, 툴체인은 **uv · ruff · mypy · pytest** 로 고정한다.
코딩 스타일은 **PEP 8 + Google Python Style Guide** 를 따르고, 둘이 충돌하면 Google 쪽을 택한다.

## 1. 실행은 항상 uv 를 거친다

- 의존성 조작은 `uv add`, `uv add --dev`, `uv remove` 만 사용한다. `pip install` 과 `requirements.txt` 수동 편집은 금지한다.
- 모든 명령에 `uv run` 을 붙인다. 가상환경을 직접 activate 하지 않는다.
- `uv.lock` 은 커밋 대상이며 손으로 편집하지 않는다.
- 앱 실행: `uv run streamlit run src/myapp/app.py`

**작업을 끝내기 전 아래 4개를 순서대로 실행하고, 전부 통과해야 완료로 보고한다.**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run mypy src tests
uv run pytest
```

실패가 남아 있으면 "완료"라고 말하지 말고 실패 내용을 그대로 보고한다.

## 2. 디렉터리 구조

src 레이아웃을 사용한다. 새 파일은 아래 위치 규칙에 맞춰 만든다.

```
pyproject.toml
src/myapp/
├── app.py          # 진입점. st.navigation 으로 페이지 등록만 담당
├── pages/          # 페이지별 렌더 함수. Streamlit 위젯 호출은 여기까지
├── components/     # 재사용 UI 조각
├── services/       # 외부 I/O (DB, API, 파일). Streamlit 미의존
└── core/           # 도메인 로직, 모델, 순수 계산. Streamlit 미의존
tests/              # src/myapp 과 동일한 구조로 미러링
```

- **`core/` 와 `services/` 에서 `import streamlit` 을 금지한다.** UI 없이 pytest 로 검증 가능해야 한다.
- 페이지에 비즈니스 로직을 직접 쓰지 않는다. 계산은 `core/`, I/O 는 `services/` 에 두고 페이지는 호출과 렌더만 한다.
- 한 파일이 300줄을 넘으면 위 경계를 기준으로 분리한다.

## 3. Streamlit 코딩 규칙

Streamlit 스크립트는 위젯 조작마다 **위에서 아래로 전체 재실행**된다. 이 전제를 깨는 코드를 쓰지 않는다.

- 모듈 최상위에서 무거운 연산이나 네트워크 호출을 하지 않는다. 함수로 감싸고 캐시한다.
- 캐싱: 직렬화 가능한 **값**은 `@st.cache_data`, DB 커넥션·클라이언트·모델 같은 공유 **객체**는 `@st.cache_resource`. 폐기된 `@st.cache` 는 쓰지 않는다.
- 캐시 대상 함수는 부작용이 없어야 한다. 해시 불가 인자는 `_conn` 처럼 `_` 접두사를 붙인다.
- `st.session_state` 키는 리터럴로 흩뿌리지 말고 모듈 상수(`SESSION_USER_ID = "user_id"`)로 정의하고, 초기화는 `if KEY not in st.session_state:` 패턴으로 한 곳에서 한다.
- 위젯에는 `key=` 를 명시한다. 같은 위젯이 여러 페이지에 있으면 상태가 충돌한다.
- `st.rerun()` 은 상태 변경 후 즉시 재렌더가 꼭 필요할 때만 쓴다. 조건 없이 호출해 무한 루프를 만들지 않는다.
- 비밀값은 `st.secrets` 로만 읽는다. 하드코딩하지 않고 `.streamlit/secrets.toml` 은 `.gitignore` 에 둔다.
- 입력 검증 실패는 예외를 그대로 노출하지 말고 `st.error()` 로 표시한다.

## 4. 코딩 스타일 (PEP 8 + Google)

- 줄 길이는 최대 **80자**. 들여쓰기는 스페이스 4칸이며 탭을 쓰지 않는다.
- 세미콜론으로 줄을 끝내거나 한 줄에 두 문장을 넣지 않는다.
- 명명: `module_name.py`, `ClassName`, `function_name`, `CONSTANT_NAME`, `_internal`. 한 글자 이름은 짧은 루프 변수에만 쓰고, 뜻이 깎이는 축약은 피한다(`cfg` 대신 `config`).
- 함수가 40줄을 넘으면 분리를 검토한다.
- `except:` 와 맨 `except Exception:` 은 금지한다. 구체적인 예외를 잡고, `try` 블록에는 예외가 날 수 있는 최소한의 코드만 둔다.
- 가변 객체를 기본 인자로 쓰지 않는다. `def f(items: list[int] | None = None)` 형태로 쓴다.
- `from x import *` 와 상대 import 를 금지한다. 항상 절대 import 를 쓴다.

### 4.1 import 는 모듈 단위로

**개별 클래스·함수를 import 하지 않는다.** 모듈이나 패키지를 import 한 뒤 정규화된 이름으로 접근한다.

```python
# 권장
import dataclasses
from myapp.core import pricing

@dataclasses.dataclass(frozen=True, slots=True)
class Quote: ...
amount = pricing.calculate(items)

# 금지
from dataclasses import dataclass
from myapp.core.pricing import calculate
```

- 예외로 허용: `typing`, `collections.abc`, `typing_extensions` 에서의 심볼 import.
- **이 규칙은 ruff 가 검사하지 않는다.** 코드를 쓸 때 직접 지키고 리뷰에서 확인한다.
- import 순서는 표준 라이브러리 → 서드파티 → 프로젝트 내부. 정렬은 `ruff check --fix` 의 `I` 규칙이 처리한다.

### 4.2 독스트링

`src/` 와 `tests/` 의 모든 모듈·클래스·함수에 `"""` 삼중 큰따옴표 독스트링을 단다. Google 형식을 쓴다.

```python
def calculate_total(items: list[Item], rate: float) -> decimal.Decimal:
    """장바구니 합계를 세금 포함 금액으로 계산한다.

    Args:
        items: 수량과 단가를 가진 상품 목록.
        rate: 0 이상 1 미만의 세율.

    Returns:
        세금이 더해진 총액.
    """
```

- 예외를 던지면 `Returns:` 다음에 `Raises:` 절을 추가한다.
- 타입은 시그니처에 이미 있으므로 `Args:` 에 다시 적지 않는다.
- 독스트링과 주석은 72자 안에서 줄바꿈한다.

## 5. 타입 힌트 (Python 3.13)

- 모든 함수·메서드에 인자와 반환 타입을 붙인다. 반환이 없으면 `-> None`.
- 내장 제네릭과 유니온을 쓴다: `list[str]`, `dict[str, int]`, `str | None`. `typing.List`, `Dict`, `Optional`, `Union` 은 쓰지 않는다.
- 3.13 이므로 `from __future__ import annotations` 는 넣지 않는다.
- 값 묶음은 `@dataclasses.dataclass(frozen=True, slots=True)` 를 기본으로 하고, 외부 입력 검증이 필요하면 pydantic 을 쓴다.
- `Any` 를 쓸 때는 바로 위에 이유를 한 줄 주석으로 남긴다.

## 6. ruff

- 설정의 단일 출처는 `pyproject.toml` 의 `[tool.ruff]` 다. 인라인 설정으로 우회하지 않는다.
- 포매팅은 `ruff format` 에 위임한다. 줄바꿈과 들여쓰기를 손으로 맞추지 않는다.
- `# noqa` 는 규칙 코드를 반드시 명시하고(`# noqa: E501`) 사유를 함께 남긴다. 코드 없는 맨 `# noqa` 는 금지한다.
- `ruff format` 은 긴 문자열과 주석을 쪼개지 않아 `E501` 이 남을 수 있다. URL, 경로, 긴 import 는 Google 가이드도 예외로 인정하니 이때만 `# noqa: E501` 을 허용하고, 그 외에는 코드를 고친다.

설정이 없으면 아래 값으로 추가한다.

```toml
[tool.ruff]
target-version = "py313"
line-length = 80

[tool.ruff.lint]
select = ["E", "W", "F", "I", "N", "D", "UP", "B", "SIM", "ANN", "RUF"]
ignore = ["ANN401"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["ANN"]
```

`convention = "google"` 을 설정하면 Google 형식과 충돌하는 `D` 규칙은 ruff 가 알아서 비활성화한다. 개별로 ignore 에 나열하지 않는다.

## 7. mypy — 점진적 강화

기본 설정에서 시작해 아래 순서로 조인다. **이미 통과하는 범위를 완화하는 방향의 수정은 하지 않는다.**

1. 전체: 기본값 + `warn_unused_ignores`, `warn_redundant_casts`, `no_implicit_optional`
2. `core/`, `services/`: `disallow_untyped_defs = true`
3. 위 두 단계가 안정되면 `pages/`, `components/` 로 확대

```toml
[tool.mypy]
python_version = "3.13"
warn_unused_ignores = true
warn_redundant_casts = true
no_implicit_optional = true

[[tool.mypy.overrides]]
module = ["myapp.core.*", "myapp.services.*"]
disallow_untyped_defs = true
```

- 억제는 `# type: ignore[attr-defined]` 처럼 오류 코드를 명시한다.
- 스텁이 없는 서드파티는 `[[tool.mypy.overrides]]` 에 `ignore_missing_imports = true` 로 모듈 단위 처리한다. 전역으로 켜지 않는다.
- 오류를 없애려고 `Any` 로 뭉개지 않는다.

## 8. pytest

- 테스트는 `tests/` 아래에 `src/myapp` 구조를 그대로 미러링한다. (`src/myapp/core/pricing.py` → `tests/core/test_pricing.py`)
- `core/`, `services/` 는 Streamlit 없이 일반 단위 테스트로 검증한다. 커버리지는 여기를 우선한다.
- 화면 동작은 `AppTest` 로 테스트한다. 모듈 단위 import 규칙에 따라 `from streamlit.testing import v1` 로 가져와 `v1.AppTest(...)` 로 쓴다. 브라우저 자동화 도구는 쓰지 않는다.
- 외부 네트워크·DB 는 반드시 fake 나 mock 으로 대체한다. 실제 호출을 하는 테스트를 추가하지 않는다.
- 캐시된 함수를 테스트할 때는 실행 전 `대상함수.clear()` 로 캐시를 비운다.
- 버그를 고칠 때는 먼저 그 버그를 재현하는 실패 테스트를 추가한 뒤 수정한다.

## 9. context7 MCP 사용

Streamlit·ruff·mypy·uv 는 API 와 설정 키가 자주 바뀐다. **기억에 의존해 API 를 쓰지 않는다.**

- 처음 쓰는 API, 시그니처가 불확실한 호출, Streamlit 최신 기능(`st.navigation`, `st.fragment`, `st.dialog` 등), `pyproject.toml` 에 새로 넣는 ruff/mypy 설정 키는 코드 작성 전에 context7 으로 문서를 조회한다.
- 사용 순서: 라이브러리 ID 를 먼저 확인한 뒤, 그 ID 와 topic 을 지정해 문서를 가져온다. topic 은 "caching", "session state" 처럼 좁게 준다.
- 조회 결과가 기존 코드와 충돌하면 임의로 한쪽을 고르지 말고 사용자에게 알린다.
- context7 이 응답하지 않으면 추측으로 진행하지 말고 그 사실을 보고한다.

## 10. 모르면 묻는다

- 요구사항이 모호하거나 위 규칙끼리 충돌하면 추측해서 구현하지 말고 질문한다.
- 규칙을 어겨야 할 이유가 있으면 먼저 이유를 설명하고 동의를 구한다.
- 기존 파일을 광범위하게 리팩터링해야 할 것 같으면 착수 전에 범위를 먼저 제시한다.