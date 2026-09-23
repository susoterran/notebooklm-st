# 정리본 설계 — 요약본 여럿을 문서 하나로

- **작성일**: 2026-09-23
- **상태**: 구현됨
- **대상**: `services/digest.py`, `services/digest_runner.py`,
  `core/digest_markdown.py`, `core/digest_title.py`,
  `pages/digest.py`, `services/outline.py`, `services/nlm.py`,
  `core/models.py`, `core/markdown_export.py`,
  `pages/maintenance.py`, `pages/ask.py`, `app.py`, `session.py`.
  저장소(`services/store.py`·`services/run_history.py`)와 실행
  모델(`services/runs.py`·`services/runner.py`), 인증
  (`services/auth.py`), 메타데이터 조회
  (`services/video_metadata.py`), 질문 저장소
  (`services/questions.py`)는 건드리지 않는다.
- **범위**: 릴리스 R5. 기획 문서
  `docs/requests/2026-09-16-summary-pipeline-v2.md` 의 **요구 4**.
  선행 조건인 R1(무인 갱신 인증)·R2(컨테이너 배포)·R3(영상
  메타데이터)·R4(Outline 저장)는 완료되었다.

---

## 1. 왜 만드는가

R4 가 요약본의 집을 위키로 옮겼다. 이제 Outline 에 영상 하나당 문서
하나가 쌓인다. 기획 §2-3 이 말하는 불편은 그다음 자리에 있다 —
**쌓인 요약본을 가로질러 읽을 방법이 없다.** 같은 주제를 다룬 영상
넷을 봤어도, 넷이 무엇에 합의하고 어디서 갈라지는지는 사람이 네
문서를 번갈아 열어 직접 맞춰 봐야 한다.

R5 는 **고른 요약본들을 재료로 새 문서 하나를 만든다.** 앱은 재료를
모아 NotebookLM 에 넘기고, 돌아온 글을 사람에게 보여 주고, 승인받아
위키에 올린다. 그 뒤의 수정·삭제·검색은 R4 와 마찬가지로 Outline 이
한다.

### 1.1 무엇을 하지 않는가

- **정리본을 로컬에 보관하지 않는다.** 저장 전 초안은 세션에만 있고,
  저장하면 Outline 이 정본이다. 로컬에는 링크조차 남기지 않는다
  (→ 3, 11).
- **재료를 Outline 전체에서 고르지 않는다.** 이 앱이 올렸고
  `outline_id` 를 아는 요약본만 재료가 된다(→ 3).
- **DB 스키마를 바꾸지 않는다.** R4 와 달리 기존 `questions.db` 를
  지울 필요가 없다(→ 11).
- **정리 지시를 저장하는 새 테이블을 두지 않는다.** 질문 관리가 이미
  그 일을 한다(→ 3, 10.2).

---

## 2. 조사로 확인한 사실

### 2.1 `documents.info` 의 계약

공식 API 문서(https://www.getoutline.com/developers)에서 확인했다.

- `POST {base}/api/documents.info`
- 필수: `id`(문서 ID 또는 공유 URL 슬러그)
- 인증: `Authorization: Bearer <API 키>` — `create` 와 같다
- 응답: JSON. 문서 객체가 `data` 에 오고 본문이 `data.text` 다

R4 가 `runs.outline_id` 에 문서 ID 를 적어 두었으므로 재료를 다시
찾아 나설 필요가 없다.

### 2.2 `sources.add_text` 는 이미 있다

`notebooklm-py==0.8.1` 의 `SourcesAPI` 에 있다. 설치된 소스에서 직접
확인했다.

```
async def add_text(notebook_id, title, content, *,
                   wait=False, wait_timeout=120.0,
                   idempotent=False) -> Source
```

`idempotent=True` 는 호출을 **거부한다** — 텍스트 소스에는 서버 쪽
중복 판정 키가 없어 재시도가 곧 중복이기 때문이다. 기본값 `False` 는
내부 재시도 루프를 끄고 첫 실패를 그대로 올린다. 중복 소스가 조용히
생기는 것보다 이쪽이 우리에게 유리하므로 기본값을 그대로 쓴다.

새 의존성은 없다. 파이프라인이 이미 쓰는 클라이언트의 다른
메서드일 뿐이다.

### 2.3 API 키 scope 는 엔드포인트 단위다

R4 가 확인한 사실이다. 그때 만든 키의 scope 는 `documents.create`
하나였다. 읽기는 거기에 포함되지 않으므로 **그 키로는 R5 가 돌지
않는다.** 배포 문서가 이 사실을 말해야 하고, 실패 문구가 scope 를
짚어야 한다(→ 5.3, 12).

### 2.4 답변에는 인용 흔적이 남는다

NotebookLM 은 본문에 `[1]` `[2, 3]` 같은 번호를 박고, 끝에 수평선과
후속 제안 블록을 붙인다. R3 이 이를 걷어내는 순수 함수를
`core/answer_text.py` 에 만들어 두었다
(`strip_citation_markers`·`strip_trailing_block`).

정리본에서 이 번호는 **임시 노트북 안에서만 뜻이 있다.** 노트북은
정리가 끝나는 순간 지워지므로, 위키에 남은 번호는 아무 데도 가리키지
않는다. 그래서 정리본 본문은 두 함수를 반드시 거친다.

**후속 제안 블록을 자르는 규칙은 마지막 수평선을 기준으로 한다.**
답변이 제목 줄 뒤에 수평선을 두면 그 규칙이 본문 전체를 잘라낸다.
그래서 제목 줄을 이 두 함수보다 **먼저** 떼어낸다(→ 6.2).

### 2.5 임시 노트북은 공유 자원이다

`pages/maintenance.py` 는 `tmp-` 로 시작하는 노트북을 찾아 지운다.
질의 실행과 정리본이 **같은 이름의 노트북**을 만들므로, 가드가 양쪽을
함께 보지 않으면 정리 도중 그 노트북이 지워진다.

같은 이유로 질의와 정리를 **동시에 돌리지 않는다.** 둘 다 같은 쿠키
파일로 NotebookLM 에 붙는데, 동시 접근은 이 프로젝트에서 검증된 적이
없다. 양쪽 화면이 서로를 보고 막는다(→ 10.4).

### 2.6 선택지가 사라진 selectbox 는 Streamlit 이 되돌린다

정리 지시를 고른 뒤 다른 탭에서 그 질문을 지우면 세션에 남은 선택값이
현재 선택지 목록에 없다. 이 상황을 `AppTest` 로 실측했다 — Streamlit
은 예외를 내지 않고 **남은 첫 선택지로 스스로 되돌린다.** 그래서 이
화면에는 따로 걸러 내는 코드를 두지 않고, 그 동작에 의존한다는 사실을
테스트로 못 박는다(→ 13).

재료 선택(multiselect)은 사정이 다르다. 그쪽은 사라진 값이 남으면
라벨 문자열이 그대로 끼어들어 `KeyError` 가 되므로 화면이 직접
걸러 낸다(→ 10.1).

---

## 3. 설계 결정

| 결정 | 이유 |
| --- | --- |
| 가공 엔진은 **NotebookLM 임시 노트북** | 이미 있는 인증·클라이언트·정리 화면을 그대로 쓴다. 새 의존성도, API 키도, 토큰 비용도 늘지 않는다 |
| 정리 지시는 **질문 관리에 등록된 질문을 고른다** | 지시를 등록·수정·삭제하는 자리가 이미 있다. 화면에서 따로 쓰게 하면 고친 지시가 어디에도 남지 않아 매번 다시 쓰게 된다 |
| 질문 목록은 **질의 화면과 공유한다** | 용도 컬럼을 두는 쪽이 목록은 깔끔하지만, 이 프로젝트는 마이그레이션 경로가 없어(→ `services/store.py`) `questions.db` 를 지워야 하고 질문과 실행 이력이 함께 사라진다. 대가는 질의 화면에 정리용 지시가 섞여 보이는 것이며, 사람이 제목으로 구분한다 |
| 제목은 **NotebookLM 이 정리와 함께 짓는다** | 날짜만 붙은 제목은 문서가 무엇을 담았는지 목록에서 말해 주지 않는다 |
| 제목을 **같은 질의 한 번에 받는다** | 질의를 두 번 던지면 몇십 초가 늘고 실패할 자리가 하나 는다. 형식을 못 읽으면 날짜로 떨어질 뿐 본문은 손상되지 않는다(→ 6.2) |
| 재료는 **로컬 이력의 저장된 실행만** | 목록 라벨·시각·`outline_id` 가 이미 로컬에 있다. Outline 읽기는 `documents.info` 하나로 끝난다 |
| 실행은 **정리본 전용 백그라운드** | 몇 분이 걸린다. 화면을 떠나면 죽는 동기 실행은 R1 이 이미 기각한 설계다. 기존 `RunRegistry` 를 일반화하는 대신 정리용을 따로 둬 R1~R3 의 심장을 건드리지 않는다 |
| 저장 전 초안은 **세션에만** | 새 테이블이 없고, "로컬에 본문을 두지 않는다" 는 R4 의 원칙이 이어진다. 대가는 재시작하면 초안이 사라지는 것이며, 같은 재료로 다시 돌리면 된다 |
| 정리본은 **요약본과 같은 컬렉션** | 설정이 늘지 않는다. 문서가 불어나 나누고 싶어지면 Outline 에서 옮기면 된다 |
| 읽기가 한 건이라도 실패하면 **멈춘다** | 넷 중 셋으로 만든 정리본은 다섯을 정리한 것과 같은 모양이다. 문서에는 그 사실을 알아차릴 단서가 없다 |

### 3.1 기각한 안

- **`run_pipeline` 을 일반화해 재사용** — 소스 추가 방식만 주입받게
  고치는 안. 정리는 소스가 여럿이고 질문이 하나라 루프 구조가
  반대다. 일반화된 함수가 두 경우를 다 어색하게 섬기고, 잘 도는
  R1~R3 의 경로에 분기가 들어간다.
- **`services/digest.py` 한 파일에 전부** — Outline 읽기와
  NotebookLM 호출과 마크다운 조립을 한 모듈에서. `nlm.py` 가 가진
  "NotebookLM 은 여기서만" 경계가 깨지고, 테스트 하나가 가짜
  클라이언트와 가짜 HTTP 를 동시에 세워야 한다.
- **제목을 받으러 질의를 한 번 더 던지기** — 파싱이 없어 제목이
  안정적이지만, 매 정리마다 응답을 한 번 더 기다리고 실패할 단계가
  하나 는다. 형식을 못 읽는 대가(날짜 제목)가 그보다 싸다.
- **정리 지시를 담는 새 테이블** — 질문 관리와 거의 같은 화면을 하나
  더 만들어야 한다. 지시와 질문은 "NotebookLM 에 던지는 글" 이라는
  같은 것이다.
- **별도 LLM API** — 형식 통제는 낫지만 새 의존성·API 키·토큰
  비용·인증 경로가 하나씩 늘어난다.
- **LLM 없이 기계적 병합** — 실패할 곳이 없지만 기획이 말한
  "가공" 이 아니다. 묶음 문서일 뿐이다.

---

## 4. 구조

```
pages/digest.py
    │  재료 선택 · 지시 선택 · 진행 표시 · 미리보기 · 저장
    ├──► services/questions.py    list_questions (읽기만)
    ▼
services/digest_runner.py      스레드 · 핸들 · 레지스트리(슬롯 1)
    ▼
services/digest.py             잇는 자리
    ├──► services/outline.py   fetch_document × N
    └──► services/nlm.py       run_digest_pipeline
             │                     └─ tmp- 노트북 → add_text × N
             │                        → ask 1회 → 노트북 삭제
             └──► core/digest_title.py   지시에 제목 요구 · 답변 파싱
    ▼
core/digest_markdown.py        저장할 본문 조립(순수 함수)
    ▼
services/outline.py            create_document      (R4 그대로)
```

`digest.py` 가 Outline 과 NotebookLM 을 **둘 다 아는 유일한
모듈**이다. 그 둘은 서로를 모른다.

---

## 5. `services/outline.py` — 읽기가 들어온다

### 5.1 인터페이스

```python
@dataclasses.dataclass(frozen=True, slots=True)
class OutlineDocument:
    """위키에 있는 문서 하나."""

    id: str
    title: str
    markdown: str


def fetch_document(
    config: OutlineConfig,
    document_id: str,
    timeout: float = FETCH_TIMEOUT,
    poster: PostLike = httpx.post,
) -> OutlineDocument
```

`create_document` 와 같은 모양이다 — 설정을 받고, 요청 함수를 인자로
뚫어 두고, 실패는 사람이 읽을 `OutlineError` 로 올린다.

### 5.2 호출

```python
# httpx.post(
#     f"{config.base_url}/api/documents.info",
#     headers={"Authorization": f"Bearer {config.token}"},
#     json={"id": document_id},
#     timeout=timeout,
# )
```

**연결 주소를 쓴다.** 공개 주소는 사람이 누를 링크를 만들 때만 쓴다
(R4 §5.1). 여기서 공개 주소를 쓰면 NAT 헤어핀이 막힌 망에서 앱이
자기 위키를 못 읽는다.

### 5.3 실패

상태 코드 문구를 **쓰기와 따로 쓴다.** `create` 쪽 `_status_message`
는 403 에서 "컬렉션 ID 부터 확인하라" 고 말하는데, 이는 쓰기 실측에서
나온 순서다. 읽기에 그 안내를 내면 멀쩡한 컬렉션을 파게 된다.

| 상태 | 무엇부터 보라고 말하나 |
| --- | --- |
| 401 | **토큰 scope 에 읽기 권한이 있는지.** 저장만 하던 키(`documents.create` 하나)로 읽으면 403 이 아니라 401 과 `Authentication required` 가 온다 |
| 403 | 토큰 scope 에 읽기 권한이 있는지 |
| 404 | 문서를 찾지 못했다. 위키에서 지워졌을 수 있다. 그 이력을 선택에서 빼고 다시 시도하라 |
| 그 외 | `Outline 이 오류를 냈습니다(HTTP …)` |

응답 본문에서 설명을 한 줄 뽑아 붙이는 `_detail` 은 그대로 함께
쓴다. 토큰이 섞여 있으면 설명째 버리는 규칙도 같다.

---

## 6. `services/nlm.py` — 정리 파이프라인

### 6.1 인터페이스

```python
async def run_digest_pipeline(
    sources: Sequence[models.DigestSource],
    instruction: str,
    on_progress: Callable[[str], None],
    client_factory: ClientFactory = default_client_factory,
) -> tuple[str | None, str]
```

`models.DigestSource` 는 `title` 과 `text` 둘뿐인 값 객체다.
`nlm.py` 는 그 글이 위키에서 왔다는 사실을 모른다.

돌려주는 것은 `(주제, 본문)` 이다. 답변이 제목 줄을 주지 않으면 첫
값이 `None` 이다.

`SourcesLike` Protocol 에 `add_text` 를 더한다. 라이브러리 클래스를
경계에서 한 번 캐스팅하는 기존 방식은 그대로다.

### 6.2 하는 일

기존 `run_pipeline` 과 대칭이다. 임시 노트북을 만들고, **`finally`
에서 반드시 지우고**, 그 `finally` 안에서는 진행 콜백을 부르지
않는다 — 콜백이 Streamlit 을 건드리는데 사용자가 페이지를 옮기면
스크립트가 중단되어 삭제에 닿지 못한다(R1 이 실측한 함정).

```
임시 노트북 생성 중
소스 1/3 등록 중 (최대 120초)
소스 2/3 등록 중
소스 3/3 등록 중
정리 중
```

소스는 `wait=True`, `wait_timeout=SOURCE_WAIT_TIMEOUT` 로 등록해
준비될 때까지 기다린다. 다 되면 `chat.ask` 를 **한 번** 부른다.
질문은 `digest_title.wrap(instruction)` — 사람이 고른 지시 뒤에 제목
요구가 붙은 글이다.

돌아온 답변은 **이 순서로** 다듬는다.

1. `digest_title.split` — 제목 줄을 떼어 주제와 본문으로 가른다
2. `answer_text.strip_trailing_block` → `strip_citation_markers` —
   본문에서 후속 제안 블록과 인용 번호를 걷어낸다
3. 주제에서도 인용 번호를 걷어낸다

**1 이 2 보다 앞서는 것이 중요하다.** 2 는 마지막 수평선을 기준으로
자르므로, 답변이 제목 줄 바로 뒤에 수평선을 두면 본문 전체가 잘려
나간다(→ 2.4).

소스 등록이 하나라도 실패하면 예외가 올라간다. 노트북은 `finally`
가 지운다.

### 6.3 소스 상한은 10건

소스 하나에 최대 120초를 기다리므로 상한이 곧 최악의 대기 시간이다
(10건이면 약 20분). 상한은 `nlm.py` 의 상수로 두고 화면이 초과
선택을 막는다(→ 10.1).

---

## 7. `core/digest_title.py` — 제목을 받아 오는 순수 함수

지시를 만드는 쪽과 그 형식을 되읽는 쪽이 **한 파일에 있다.** 갈라지면
한쪽만 고쳐도 조용히 어긋나고, 어긋난 자리는 제목이 날짜로 떨어지는
것으로만 드러나 알아차리기 어렵다.

```python
DIRECTIVE: str
DOCUMENT_PREFIX = "[정리]"
TOPIC_MAX_CHARS = 60

def wrap(instruction: str) -> str
def split(text: str) -> tuple[str | None, str]
def compose(topic: str | None, created_on: str) -> str
```

- `wrap` — 사람의 지시는 손대지 않고 뒤에 빈 줄과 `DIRECTIVE` 를
  붙인다. `DIRECTIVE` 는 "첫 줄에 `제목: ` 으로 시작하는 줄을 두고
  주제를 30자 이내 명사구로, 둘째 줄은 비우고, 셋째 줄부터 본문" 을
  요구한다.
- `split` — 첫 비어 있지 않은 줄에서 주제를 뽑는다. 모델이
  `**제목:**` 이나 `## 제목:` 처럼 꾸며 쓰는 것, 전각 콜론,
  주제를 감싼 따옴표를 모두 받는다. **표시를 못 읽으면 관용이 곧
  성공률이다.**
- `compose` — `[정리] <주제>`. 주제를 못 받았거나 공백뿐이면
  `[정리] <날짜>`. 접두어는 폴백에도 붙여 Outline 에서 정리본만 한
  번에 찾는 손잡이로 쓴다. 주제는 한 줄로 접고
  `TOPIC_MAX_CHARS` 에서 자른다 — 지시가 30자를 요구하지만 모델이
  그 말을 반드시 지키지는 않는다.

**본문을 잃지 않는 것이 제목을 얻는 것보다 앞선다.** 표시를 못 읽거나
제목 줄을 떼어낸 뒤 본문이 남지 않으면 받은 글을 그대로 돌려주고
주제를 포기한다.

---

## 8. `services/digest.py` — 잇는 자리

```python
def build(
    config: outline.OutlineConfig,
    runs: Sequence[models.RunSummary],
    instruction: str,
    on_progress: Callable[[str], None],
) -> models.DigestDraft
```

1. `runs` 를 돌며 `outline.fetch_document(config, run.outline_id)`
   — 진행 문구 `재료 2/4 읽는 중`. 화면이 `exported_at` 이 있는
   실행만 넘기고, `RunSummary` 의 계약상 그 넷은 함께 채워지거나
   함께 비므로 `outline_id` 는 있다
2. 읽은 문서를 `models.DigestSource` 로 옮겨
   `nlm.run_digest_pipeline` 에 넘긴다. 이 함수는 `asyncio.run` 으로
   부른다 — 스레드 본체에서 호출되므로 이벤트 루프가 없다
3. 결과를 `models.DigestDraft(body, sources, instruction,
   created_on, topic)` 로 돌려준다. `sources` 는 출처 링크를 만들
   `RunSummary` 들이고, `topic` 은 제목 기본값이 된다

**한 건이라도 못 읽으면 거기서 멈춘다.** `OutlineError` 의 메시지
앞에 **어느 문서**에서 막혔는지를 제목으로 붙여 다시 올린다. 이미
읽은 것은 버린다 — 부분 정리본을 만들지 않는다(→ 3).

---

## 9. `services/digest_runner.py` — 백그라운드

### 9.1 핸들과 레지스트리

핸들·레지스트리·스레드 시작을 한 파일에 둔다. 정리는 한 번에 한
건이라 `runs.py` + `runner.py` 처럼 둘로 나눌 만큼 크지 않다.

```python
@dataclasses.dataclass(slots=True)
class DigestHandle:
    status: Literal["running", "done", "failed"]
    progress: list[str]
    draft: models.DigestDraft | None
    error_message: str | None
    error_level: Literal["info", "error"] | None
    started_at: str
    finished_at: str | None
```

`DigestRegistry` 는 **슬롯 하나**다. 모든 공개 메서드가 락 안에서
돌고, 읽기는 복사본을 돌려준다 — `RunRegistry` 와 같은 규칙이다.
이미 `running` 이면 새 정리를 거절한다.

`session.get_digest_registry()` 를 `@st.cache_resource` 로 감싸
탭이 달라도 같은 것을 본다.

### 9.2 실패 계단

스레드 본체는 `runner.py` 와 같은 계단을 쓴다.

| 잡는 것 | 화면에 나가는 것 |
| --- | --- |
| `outline.OutlineError` | 메시지 그대로(이미 사람이 읽을 문장이다) |
| `errors.MAPPED_ERRORS` | `errors.to_message` 의 문구. 인증 만료면 재로그인 안내 |
| `Exception` | `예상 못 한 오류(…)` |
| `BaseException` | 상태만 남기고 재전파 |

어느 쪽이든 핸들이 `running` 에 영원히 남지 않게 한다. 스레드는
Streamlit API 를 부르지 않는다.

---

## 10. 화면

### 10.1 `pages/digest.py`

```
정리본
├ [설정 없음]   Outline 연결 안내 — 이력 화면과 같은 문구 패턴
├ [재료 없음]   "먼저 이력에서 요약본을 Outline 에 저장하세요"
├ 재료 선택     multiselect · 저장된 실행만 · 최대 10건
├ 정리 지시     selectbox · 질문 관리의 질문 · 본문은 접어서 보여 준다
│              [질문 없음] "질문 관리 화면에서 먼저 등록하세요"
├ [정리 시작]   질의 중이면 비활성 + 이유
├ 진행 중       fragment(run_every="1s") — 레지스트리를 읽기만 한다
└ 완료          미리보기 · 제목 입력 · [Outline 에 저장] [버리기]
```

- 재료는 `run_history.list_runs` 중 `exported_at` 이 있는 것.
  라벨은 `문서 제목 · 시각`
- **1건도 고를 수 있다.** 여러 건을 가로지르는 것이 이 기능의 요점
  이지만, 한 건을 다른 틀로 다시 쓰는 것도 쓸모가 있다. 0건일 때만
  버튼이 잠긴다
- 다른 탭에서 이력이 지워지면 재료 선택값이 남은 채로 위젯이
  되살아나고, Streamlit 이 그 자리에 원본 라벨 문자열을 끼워 넣는다.
  목록에 없는 값은 조용히 걸러 트레이스백을 막는다
- 등록된 질문이 하나도 없으면 안내만 내고 **시작 버튼을 그리지
  않는다.** 지시 없이 정리할 수 있는 상태가 없어야 한다
- 지시가 공백인지 화면에서 검사하지 않는다. 질문 등록이 이미 공백을
  막으므로(`services/questions.py`) 도달할 수 없는 분기다
- 제목 기본값은 `digest_title.compose(draft.topic,
  draft.created_on)` 다. 사람이 고쳐 쓸 수 있다
- 진행 프래그먼트는 **레지스트리를 읽기만 한다.** 안에서 상태를
  바꾸면 그 변경이 다음 재실행을 부르고 무한 루프가 된다(R1 실측)
- 저장은 `outline.create_document` 한 번이다. 실패하면 초안이 화면에
  그대로 남아 다시 누르면 된다 — R4 의 "문서는 만들어졌는데 로컬
  기록이 실패" 같은 틈이 없다. 로컬에 쓸 것이 없기 때문이다
- 저장이 끝나면 링크와 함께 **"이 정리본은 로컬에 남지 않습니다"**
  를 적는다. 세션에만 들고 있기로 한 결정의 결과를 사람이 그 자리에서
  알아야 한다
- 초안을 저장·버리거나 재시도할 때 제목 입력 키를 지운다. Streamlit
  은 위젯의 `value=` 를 그 key 가 `session_state` 에 처음 나타날 때만
  반영하므로, 지우지 않으면 다음 초안에 이전 제목이 남는다

### 10.2 정리 지시는 질문 관리가 가진다

화면은 `questions.list_questions` 를 **읽기만** 한다. 등록·수정·삭제는
질문 관리 화면이 그대로 맡고, 이 화면은 지시를 만들지 않는다.

목록은 영상 질의 화면과 같은 것이다. 그래서 질의 화면의 질문 목록에도
정리용 지시가 함께 보인다. 용도를 나누려면 `questions` 에 컬럼이
필요하고, 마이그레이션 경로가 없는 이 프로젝트에서는 그 대가가 DB
삭제다(→ 3). 사람이 제목으로 구분하는 쪽을 택했다.

### 10.3 `app.py`

네비게이션에 `st.Page(digest.render, title="정리본",
url_path="digest")` 를 이력 다음 자리에 둔다.

### 10.4 가드 두 곳

- `pages/maintenance.py` — 삭제 버튼이 **정리 실행 중에도** 잠긴다.
  진행 중인 정리본의 `tmp-` 노트북을 지우는 사고를 막는다(→ 2.5)
- `pages/ask.py` — 정리 중이면 실행을 막고 이유를 말한다. 반대
  방향은 정리본 화면이 막는다

---

## 11. `core/digest_markdown.py` — 문서의 모양

```python
def to_markdown(draft: models.DigestDraft) -> str
```

```markdown
- 종류: 정리본
- 만든 날: 2026-09-23
- 정리 지시: 세 영상의 공통 주장과 엇갈리는 지점을 뽑아 비교해 줘

## 출처

- [요약본 제목 A](https://wiki.example.com/doc/a-slug)
- [요약본 제목 B](https://wiki.example.com/doc/b-slug)

---

(NotebookLM 이 쓴 정리 본문)
```

메타데이터에 적는 것은 지시의 **본문**이다. 고른 질문의 제목이 아니라
실제로 문서를 만든 글이 그것이고, 제목은 질문 관리에서 언제든 바뀐다.

R4 가 실물로 배운 두 가지를 그대로 지킨다.

- **`#` 머리글을 넣지 않는다.** Outline 이 문서 제목을 따로 가진다.
- **YAML frontmatter 를 쓰지 않는다.** CommonMark 에서 문단 바로
  뒤의 `---` 는 구분선이 아니라 setext H2 밑줄이라, 메타데이터 세
  줄이 머리글 하나로 뭉친다. 그래서 여기서도 리스트를 쓰고, 본문 앞
  구분선은 **빈 줄과 머리글 뒤**에 온다.

출처 링크는 로컬에 적힌 `outline_url` 이다. 공개 주소로 만들어진
값이라 위키에서 눌러 원본 요약본으로 갈 수 있다. 링크가 없는 옛
기록이면 제목만 적는다.

값 다듬기는 `markdown_export` 와 같은 규칙을 쓴다 — 제어문자를
지우고 공백류를 하나로 접는다. 규칙이 두 벌로 갈라지지 않도록
`markdown_export.one_line` 을 공개해 두 모듈이 함께 쓴다.
`digest_title.compose` 도 같은 함수로 주제를 접는다.

---

## 12. 저장소는 그대로다

`services/store.py` 의 스키마도, `run_history` 의 함수도, `questions`
의 함수도 바뀌지 않는다. 정리본은 로컬에 아무 행도 남기지 않는다.

그래서 **R5 를 올려도 기존 `questions.db` 를 그대로 연다.** R4 는
DB 삭제를 요구했지만 R5 는 요구하지 않는다. 배포는 이미지를 바꾸는
것으로 끝난다.

---

## 13. 배포 설정과 문서

환경변수는 늘지 않는다. `docker-compose.yml` 도 그대로다.

**API 키 scope 만 넓어진다.** 배포 문서
(`docs/how-to/2026-09-16-homeserver-deploy.md`)의 "4.1 API 키
만들기" 절에 읽기 권한이 필요하다는 사실과, 쓰기 전용 키로는 정리가
401 로 막힌다는 사실을 적는다.

`README.md` 에는 화면 하나가 늘었다는 사실, 정리 지시를 질문 관리에서
고른다는 사실, 정리본이 로컬에 남지 않는다는 사실을 적는다.

---

## 14. 테스트

| 대상 | 무엇을 단언하나 |
| --- | --- |
| `core/digest_title` | 지시가 프롬프트 맨 앞에 남음 · 꾸민 제목 표시·전각 콜론·따옴표를 읽음 · 표시가 없으면 본문을 손대지 않음 · 본문이 남지 않으면 아무것도 자르지 않음 · 접두어·한 줄 접기·길이 상한 · 주제가 없으면 날짜 |
| `core/digest_markdown` | `#` 머리글 없음 · `---` 가 문단 바로 뒤에 오지 않음 · 출처가 링크로 나옴 · 링크 없는 출처는 제목만 · 제어문자와 개행이 리스트를 두 동강 내지 않음 |
| `outline.fetch_document` | 가짜 `poster` 로 성공 · 401(scope 를 짚는지) · 403 · 404 · 깨진 JSON · 토큰이 섞인 설명은 통째로 버려짐 |
| `nlm.run_digest_pipeline` | `add_text` 가 소스 수만큼 · `ask` 는 한 번 · 프롬프트에 사람의 지시와 제목 요구가 함께 실림 · 제목 줄이 주제가 되고 본문에서 빠짐 · 제목 줄 뒤 수평선이 본문을 삼키지 않음 · 주제와 본문 양쪽에서 인용 번호가 사라짐 · 소스 등록이 실패해도 노트북이 지워짐 |
| `services/digest` | 읽기가 한 건 실패하면 멈추고 메시지에 그 문서 제목이 들어감 · 주제가 초안에 실림 |
| `services/digest_runner` | 스레드 종료 후 상태 전이 · 인증 만료가 재로그인 안내로 매핑됨 · 이미 돌고 있으면 거절 |
| `pages/digest` | 설정 없음 · 재료 없음 · **질문 없음** · 상한 초과 · 질의 중 각 상태에서 버튼이 잠기거나 그려지지 않고 이유가 보임 · 고른 질문의 본문이 지시로 넘어감 · 지워진 질문이 화면을 깨뜨리지 않음 · 제목 기본값이 주제 또는 날짜 · 저장 성공과 실패 |
| `pages/maintenance`·`pages/ask` | 정리 중일 때 각각의 버튼이 잠김 |

`AppTest` 의 selectbox 는 `select()` 에 **원본 옵션 객체**를 받는다.
라벨 문자열을 주면 `format_func` 을 한 번 더 먹여 찾으므로 실패한다.
`select_index` 도 같은 이유로 쓸 수 없다.

검증은 CI 와 같은 네 단이다 — `ruff format --check .`,
`ruff check .`, `mypy src tests`, `pytest`.

---

## 15. 건드리는 파일

**신규**

- `services/digest.py` · `services/digest_runner.py`
- `core/digest_markdown.py` · `core/digest_title.py` ·
  `pages/digest.py`
- 각 대응 테스트

**수정**

- `services/outline.py` — `OutlineDocument`·`fetch_document`
- `services/nlm.py` — `run_digest_pipeline`, `SourcesLike.add_text`,
  소스 상한 상수
- `core/models.py` — `DigestSource`·`DigestDraft`
- `core/markdown_export.py` — `_one_line` → `one_line`
- `pages/maintenance.py`·`pages/ask.py` — 가드
- `app.py` — 네비게이션 · `session.py` — 레지스트리
- `docs/how-to/2026-09-16-homeserver-deploy.md` — API 키 scope
- `README.md` — 정리본 화면

**건드리지 않음**: `services/store.py`, `services/run_history.py`,
`services/runs.py`, `services/runner.py`, `services/auth.py`,
`services/video_metadata.py`, `services/questions.py`(읽기만 한다),
`pages/question_admin.py`, `docker-compose.yml`, `Dockerfile`,
`pyproject.toml`.

---

## 16. 미검증 가정

- **모델이 제목 요구를 얼마나 지키는지 실측하지 않았다** — 형식을 못
  읽으면 제목이 `[정리] <날짜>` 로 떨어진다. 화면의 제목 칸에서 바로
  보이고, 사람이 고쳐 쓸 수 있으므로 조용히 나빠지지는 않는다.
  자주 떨어지면 `DIRECTIVE` 를 고친다.
- **소스 10건이 한 노트북에 들어간다** — 계정 등급에 따라 소스
  한도가 다르다. 상한을 넘기면 등록이 실패하고 그 자리에서 보인다.
- **텍스트 소스가 긴 요약본을 받아 준다** — `add_text` 의 본문 길이
  한도를 확인하지 못했다. 막히면 예외가 그대로 화면에 뜬다.

---

## 17. 범위 밖

- **스케줄러 · 즐겨찾기 채널 자동 요약 · 알림** — 하지 않는다(R6a §16)
- **정리본을 다시 재료로 쓰기** — 정리본은 로컬에 기록이 없어
  재료 목록에 나타나지 않는다
- **정리본 재생성 이력 · 로컬 보관** — 세션에만 둔다(→ 3)
- **질문의 용도 구분** — 스키마 변경이 곧 DB 삭제다(→ 3, 10.2)
- **Outline 컬렉션 전체에서 재료 고르기** — `documents.list` 와
  목록·검색 화면이 필요하다
- **정리본 수정·삭제를 앱에서** — 위키에 위임한 것이 R4 의 요점이고
  R5 도 그대로 따른다
- **질의와 정리의 동시 실행** — 서로 막는다(→ 2.5)

---

## 18. 남겨 둔 것

| 것 | 상태 |
| --- | --- |
| `services/outline.py` | 쓰기와 읽기가 다 있다. 목록(`documents.list`)은 아직 없다 |
| API 키 scope | `documents.create` + 읽기. 목록을 더하면 또 넓혀야 한다 |
| 질문 목록 | 질의용과 정리용이 한 목록에 섞여 있다. 수가 불어나면 용도 구분이 필요해진다 |
| 컬렉션 구조 | 여전히 평평하다. 요약본과 정리본이 한 컬렉션에 섞인다 |
