# 이력 동기화 설계 — 저장된 이력을 Outline 문서 목록과 맞추기

- **작성일**: 2026-09-28
- **상태**: 설계 (구현 계획 수립 전)
- **대상**: `services/history_sync.py`(신규), `core/outline_import.py`(신규),
  `pages/_history_sync.py`(신규), `services/outline.py`,
  `services/run_history.py`, `core/models.py`, `pages/history.py`,
  `README.md`.
  스키마(`services/store.py`), 러너(`services/runner.py`),
  정리본(`services/digest*.py`·`core/digest*.py`), 채널
  (`services/channels.py`·`services/channel_feed.py`), 배포 파일
  (`docker-compose.yml`·`Dockerfile`·`pyproject.toml`)은 건드리지 않는다.
- **범위**: 이력 화면의 "Outline 과 동기화" 한 기능. 기존 저장·삭제 흐름은
  동작이 바뀌지 않는다.

---

## 1. 왜 바꾸는가

R4(`2026-09-22-outline-storage-design.md`) 이후 요약본의 진실 원천은
Outline 이고, 로컬 `runs` 에는 문서 ID·URL·제목·저장 시각만 남는다. 이
링크 장부는 세 가지 일을 한다.

- 이력 화면의 목록을 Outline 호출 없이 그린다.
- 정리본 화면이 재료 후보를 고르고 `outline_id` 로 문서를 다시 읽는다.
- 채널 감시가 `video_id` 집합으로 "이미 요약한 영상"을 거른다.

장부와 Outline 이 어긋나면 이 셋이 함께 어긋난다. 어긋나는 경로는 셋이다.

1. **DB 파일을 지운 경우.** 이 프로젝트는 마이그레이션을 두지 않으므로
   스키마가 바뀔 때마다 `questions.db` 를 지운다. 그때 장부가 통째로
   사라진다. 정리본 재료 목록이 비고, 채널 감시가 이미 요약한 영상을 다시
   권한다.
2. **Outline 에서 문서를 지운 경우.** 장부에는 남아 있어 정리본이 그
   문서를 읽다 404 를 받고 멈춘다. 지금은 사람이 404 문구를 읽고 "이 이력
   삭제" 로 하나씩 푼다.
3. **저장 중 로컬 기록만 실패한 경우.** 문서는 생겼는데 장부에 없다.

세 경우 모두 앱이 알아차리지 못하거나 사람이 손으로 푼다. 이 설계는
사람이 버튼을 눌러 두 목록을 맞추는 길을 만든다. 목적은 "불일치 해소"
보다 **"장부를 Outline 에서 언제든 다시 만들 수 있게 하기"** 다. 파일을
지운 뒤 버튼 한 번으로 저장된 이력이 돌아오면, 마이그레이션 없음 정책의
이력 쪽 통증이 정책을 바꾸지 않고 사라진다.

---

## 2. 조사로 확인한 사실

### 2.1 되살리는 데 필요한 값은 전부 Outline 에 있다

`runs` 의 NOT NULL 컬럼은 `url`·`video_id`·`created_at` 셋이다.

- `core/markdown_export.py` 의 `_metadata_block` 은 문서 본문 첫머리에
  `- 영상 URL: <정규 URL>` 줄을 **항상** 넣는다. 채널·업로드 일자 줄은
  값이 없으면 빠지지만 이 줄은 빠지지 않는다.
- `youtube.extract_video_id` 가 그 URL 에서 `video_id` 를 돌려준다.
- Outline API 의 `Document` 객체는 `id`·`title`·`text`·`url`·`createdAt`
  을 싣는다. `url` 은 상대 경로이며, `services/outline.py` 의 `_absolute`
  가 이미 이를 `public_url` 에 붙이는 일을 한다.

### 2.2 목록 호출은 컬렉션 필터와 페이지네이션을 지원한다

`POST /api/documents.list` 는 `filters: [{field: "collectionId",
operator: "eq", value: ...}]` 로 컬렉션을 거르고, `limit`·`offset` 으로
넘기며, 응답 `pagination.nextPath` 가 다음 페이지 경로를 준다. 휴지통과
보관 문서는 이 목록에 나오지 않는다(각각 `documents.deleted`·
`documents.archived` 가 따로 있다).

### 2.3 같은 컬렉션에 이력 문서가 아닌 것이 섞여 있다

정리본(`pages/digest.py`)도 같은 컬렉션에 `documents.create` 로 문서를
만든다. 그 본문(`core/digest_markdown.py`)은 `- 만든 날:`·`- 정리 지시:`
줄로 시작하고 `- 영상 URL:` 줄이 없다. 재료 목록은
`- [제목](outline_url)` 꼴의 리스트 항목이라 역시 걸리지 않는다. 사람이
직접 쓴 문서도 있을 수 있다.

### 2.4 기존 코드가 이미 가진 것

- `run_history.mark_exported` 는 UPDATE 와 DELETE 를 커밋 하나로 묶고
  어떤 예외든 롤백해 다시 던진다. 같은 패턴을 쓴다.
- `pages/history.py` 의 삭제 UI 는 위젯 키가 아닌 우리 세션 키
  (`_DELETE_ARMED_KEY`)에 확인 상태를 두는 2단계다. 같은 패턴을 쓴다.
- `pages/history.py` 는 226줄이다. `.claude/rules/streamlit-implement.md`
  의 300줄 규칙 때문에 새 화면 조각은 `pages/_channel_check.py` 처럼
  별도 파일로 뗀다.
- `tests/pages/test_history.py` 는 `monkeypatch.setattr(outline,
  "create_document", ...)` 로 Outline 호출을 바꿔 끼운다. 목록 호출도
  같은 방법으로 바꿔 끼운다.
- `outline._read_status_message` 의 401·403 문구는 "documents.info"
  scope 를 짚는다. 목록 호출에는 "documents.list" 를 짚는 문구가 따로
  필요하다.

### 2.5 실행 선택은 ID 기준이다

`pages/history.py` 의 selectbox 는 `RunSummary` 객체가 아니라 `run.id`
를 값으로 쓴다. 동기화가 기존 행을 건드리지 않으면 적용 뒤에도 선택이
살아남는다. 지워진 행을 고르고 있었다면 Streamlit 이 첫 항목으로 되돌린다
(기존 삭제에서 AppTest 로 확인한 동작).

---

## 3. 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 실행 시점 | **사람이 버튼을 눌렀을 때만** | "앱은 Outline 을 읽지 않는다" 원칙의 취지는 Outline 장애가 이력 화면을 막지 않는 것이다. 사람이 누를 때만 읽으면 그 취지가 유지된다. 자동·주기 실행은 두지 않는다 |
| 적용 방식 | **미리보기 후 적용** | 무엇이 지워지는지 먼저 본다. 기존 삭제 UI 의 2단계와 같다 |
| 기존 행 | **손대지 않는다** | 전부 지우고 재구축하면 ID 가 바뀌어 다른 탭의 선택이 풀리고 원래 실행 시각이 덮인다. 차이만 적용한다 |
| 미저장 실행 | **입력에서 뺀다** | `exported_at` 이 없는 행은 아직 올리지 않은 것이다. 삭제될 수 없어야 한다 |
| 미저장 실행과 같은 영상의 문서 | **새 행을 만들고 미저장은 그대로** | 그 문서가 정말 그 실행에서 나왔는지 확인할 길이 없다. 본문을 지우는 판단은 사람이 한다 |
| 같은 영상의 문서 둘 | **둘 다 만든다** | 동기화는 위키를 정리하지 않는다. 합치는 판단도 사람이 한다 |
| 영상 URL 줄이 없는 문서 | **건너뛰고 사유를 보여 준다** | 정리본·손으로 쓴 문서는 이력이 아니다. 조용히 무시하면 왜 안 들어왔는지 알 수 없다 |
| 휴지통·보관 문서 | **"없음"으로 본다** | 목록에 나오지 않는다. 복원하면 다음 동기화가 다시 만든다 |
| 부분 목록 | **계획을 세우지 않는다** | 절반만 본 목록으로 지우면 멀쩡한 이력이 사라진다 |
| 스키마 | **바꾸지 않는다** | 필요한 컬럼이 전부 있다. DB 파일을 지울 일이 없다 |

---

## 4. 구조

```
pages/_history_sync.py           버튼·미리보기·적용 (Streamlit 만 안다)
   │
   ├─► services/outline.list_documents(config)     컬렉션 문서 전부
   ├─► services/run_history.list_exported(conn)     exported_at 이 있는 행
   ├─► services/history_sync.plan(exported, docs)   순수 비교 → SyncPlan
   └─► services/history_sync.apply(conn, plan)      삭제 + 삽입, 커밋 하나
             ├─► run_history.delete_runs
             └─► run_history.insert_exported
core/outline_import.py           문서 본문 → 영상 URL·video_id (순수 함수)
```

경계는 이렇다.

- **`core/outline_import.py` 는 마크다운 문자열만 받는다.** `markdown_export`
  가 쓴 줄을 거꾸로 읽는 짝이므로 그 모듈 옆에 둔다.
- **`services/history_sync.py` 는 `plan` 과 `apply` 둘뿐이다.** httpx 도
  Streamlit 도 모른다. `plan` 은 두 목록을 받아 `SyncPlan` 을 돌려주는
  순수 함수이고, `apply` 는 그것을 DB 에 쓴다.
- **`services/outline.py` 는 목록 호출 하나가 는다.** Outline 을 아는
  유일한 모듈이라는 자리는 그대로다.
- **`pages/_history_sync.py` 는 `pages/history.py` 가 부른다.**

흐름은 이렇다.

```
"확인" 버튼
    ↓
config_from_env() 없음 → 안내 문구, 끝
    ↓
list_documents(config) ── OutlineError → st.error, 끝
    ↓
plan(list_exported(conn), documents) → 세션 history_sync_plan
    ↓
미리보기: 개수 한 줄 + 세 표
    ↓
"적용" → apply(conn, plan) → 세션 plan 삭제, 결과 문구 세션에 저장, rerun
"취소" → 세션 plan 삭제, rerun
```

---

## 5. 비교 규칙과 엣지 케이스

`plan(exported, documents)` 은 두 집합을 **문서 ID** 로 맞춘다.

| 상태 | 판정 | 결과 |
|---|---|---|
| 행의 `outline_id` 가 문서 목록에 없음 | Outline 에 없음 | **삭제 대상** |
| 문서를 가리키는 행이 없고, 본문에 영상 URL 줄이 있고 ID 가 뽑힘 | 이력에 없음 | **생성 대상** |
| 문서를 가리키는 행이 없고, 영상 URL 줄이 없음 | 이력 문서가 아님 | **건너뜀** — 사유 "영상 URL 없음" |
| 문서를 가리키는 행이 없고, 영상 URL 줄은 있으나 ID 를 못 뽑음 | 손상된 메타데이터 | **건너뜀** — 사유 "영상 URL 인식 불가" |
| 행과 문서가 모두 있음 | 정상 | 손대지 않음 |

엣지 케이스는 이렇게 다룬다.

- **미저장 실행**은 `list_exported` 가 돌려주지 않으므로 `plan` 의 입력에
  없다. 삭제될 수 없다. 같은 영상의 문서가 있으면 새 행이 생기고 미저장은
  그대로 남는다. 목록에 같은 영상이 두 줄 보이며, 사람이 미저장 쪽을
  지우거나 다시 저장한다.
- **같은 영상의 문서 둘**은 둘 다 생성 대상이다.
- **같은 문서를 가리키는 행 둘**(저장 도중 동기화가 돈 경합의 결과)은 둘 다
  정상으로 두고 손대지 않는다. 동기화는 중복을 만들지 않을 뿐 정리하지
  않는다.
- **휴지통·보관 문서**는 목록에 없으므로 그 행은 삭제 대상이다. 사람이
  복원하면 다음 동기화가 다시 만든다. README 에 적는다.
- **영상 URL 줄은 첫 `---` 구분선 앞에서만 찾는다.** 답변 본문에 같은
  문구가 인용될 가능성을 막는다. 구분선이 없으면 본문 전체에서 찾는다.
- **미리보기와 적용 사이에 다른 탭이 DB 를 바꾼 경우**는 적용 직전에 다시
  확인하지 않는다. 지울 행이 이미 없으면 `DELETE` 가 0건일 뿐이고, 만들
  문서의 `outline_id` 가 이미 있으면 그 항목만 건너뛴다. 결과 문구에는
  실제 개수를 적는다.

생성 행의 값은 이렇다.

| 컬럼 | 값 |
|---|---|
| `url` | 본문의 영상 URL 그대로 |
| `video_id` | `youtube.extract_video_id(url)` |
| `title` | Outline 문서 제목 |
| `created_at` | 문서 `createdAt` 을 로컬 시각의 초 단위 ISO 문자열로 바꾼 값(`store.now()` 와 같은 형식) |
| `exported_at` | `created_at` 과 같은 값 |
| `outline_id` | 문서 ID |
| `outline_title` | 문서 제목 |
| `outline_url` | 상대 URL 을 `public_url` 에 붙인 절대 URL (`_absolute` 재사용) |

`answers`·`run_metadata` 행은 만들지 않는다. 저장된 실행은 원래 본문이
없다.

`created_at` 에 문서 생성 시각을 쓰는 이유는 목록 정렬이다. 목록은 `id`
내림차순이므로 되살린 행은 어차피 맨 위에 오지만, 라벨에 찍히는 시각이
동기화 시각이면 "언제 요약했는가"의 단서가 사라진다. 문서 생성 시각은
저장 시각과 거의 같다.

---

## 6. 데이터 모델

스키마는 바꾸지 않는다. `core/models.py` 에 값 객체 넷을 더한다. 전부
`frozen=True, slots=True` 다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class ListedDocument:
    """Outline 목록에서 읽어 온 문서 하나."""

    id: str
    title: str
    url: str
    """절대 URL. 상대 경로는 services/outline 이 붙여서 넘긴다."""
    created_at: str
    """로컬 시각의 초 단위 ISO 문자열. store.now() 와 같은 형식."""
    markdown: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyncCreate:
    """동기화가 새로 만들 이력 한 건."""

    document: ListedDocument
    url: str
    """본문에서 읽은 영상 URL."""
    video_id: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyncSkip:
    """동기화가 건너뛴 문서 한 건과 그 사유."""

    document: ListedDocument
    reason: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyncPlan:
    """미리보기와 적용이 함께 쓰는 동기화 계획."""

    deletes: tuple[RunSummary, ...]
    creates: tuple[SyncCreate, ...]
    skips: tuple[SyncSkip, ...]

    @property
    def is_empty(self) -> bool:
        """지울 것도 만들 것도 없다."""
        return not self.deletes and not self.creates
```

`ListedDocument` 는 기존 `OutlineDocument`(`services/outline.py`, 정리본이
쓴다)와 다르다. 정리본은 ID·제목·본문만 필요하고, 동기화는 URL 과 생성
시각도 필요하다. `OutlineDocument` 에 필드를 더하면 정리본 테스트가 함께
바뀌므로 따로 둔다. `core` 에 두는 이유는 `SyncPlan` 이 담아야 하고
`SyncPlan` 은 화면과 서비스가 함께 쓰기 때문이다.

---

## 7. 서비스 계층

### 7.1 `services/outline.py`

```python
LIST_PAGE_SIZE = 100
LIST_PAGE_LIMIT = 50


def list_documents(
    config: OutlineConfig,
    timeout: float = FETCH_TIMEOUT,
    poster: PostLike = httpx.post,
) -> list[models.ListedDocument]
```

- `_LIST_PATH = "/api/documents.list"` 를 `filters` 컬렉션 조건과
  `limit: LIST_PAGE_SIZE`, `sort: "createdAt"`, `direction: "DESC"` 로
  부른다. 응답 `pagination.nextPath` 가 있으면 `base_url` 에 붙여 계속
  부른다.
- `LIST_PAGE_LIMIT` 페이지를 넘기면 `OutlineError` 다. 잘못된 `nextPath`
  로 무한히 돌지 않게 한다.
- 어느 페이지든 실패하면 지금까지 모은 것을 버리고 `OutlineError` 다.
- 상대 URL 은 `_absolute(config.public_url, url)` 로 절대화한다.
- `createdAt`(UTC ISO) 은 로컬 시각의 초 단위 ISO 문자열로 바꾼다.
  `datetime.fromisoformat` → `astimezone()` → `isoformat(timespec=
  "seconds")` 이며 tz 접미는 뗀다. `store.now()` 와 같은 모양이어야 목록
  라벨이 섞여도 어색하지 않다.
- 상태 문구는 `_list_status_message` 를 새로 둔다. 401·403 은
  "documents.list" scope 를 짚고, 404 는 "주소를 확인하라", 429 는 "잠시
  후 다시 시도" 다. 나머지는 `_read_status_message` 와 같다. 함수 하나가
  느는 대신 `_failure_message` 를 그대로 재사용한다.
- `services/outline.py` 는 지금 429줄이다. 목록 호출과 문구가 더해지면
  300줄 규칙에서 더 멀어지므로, 상태 문구 세 함수(`_status_message`·
  `_read_status_message`·`_list_status_message`)와 `_failure_message`·
  `_detail` 을 `services/outline_messages.py` 로 옮긴다. 공개 API 는 바뀌지
  않으며 `tests/services/test_outline.py` 는 그대로 통과해야 한다.

### 7.2 `services/run_history.py`

```python
def list_exported(connection) -> list[models.RunSummary]
def insert_exported(connection, create: models.SyncCreate) -> int | None
def delete_runs(connection, run_ids: Sequence[int]) -> int
```

- `list_exported` 는 `list_runs` 와 같은 SELECT 에 `WHERE r.exported_at
  IS NOT NULL` 을 더하고 `LIMIT` 을 두지 않는다. 동기화는 전부 봐야 한다.
- `insert_exported` 는 여덟 컬럼을 채운 `runs` 행 하나를 넣고 ID 를
  돌려준다. 같은 `outline_id` 를 가진 행이 이미 있으면 넣지 않고 `None`
  을 돌려준다. **커밋하지 않는다.** 트랜잭션은 `apply` 가 소유한다.
- `delete_runs` 는 `DELETE FROM runs WHERE id IN (...)` 을 실행하고
  `rowcount` 를 돌려준다. 없는 ID 는 무시한다. **커밋하지 않는다.**
- 기존 `save_run`·`mark_exported`·`delete_run` 은 각자 커밋하는 채로
  둔다. 규약이 갈리는 것을 독스트링에 적는다.

### 7.3 `services/history_sync.py`

```python
def plan(
    exported: Sequence[models.RunSummary],
    documents: Sequence[models.ListedDocument],
) -> models.SyncPlan


@dataclasses.dataclass(frozen=True, slots=True)
class SyncResult:
    deleted: int
    created: int


def apply(connection: sqlite3.Connection, plan: models.SyncPlan) -> SyncResult
```

- `plan` 은 5장의 규칙을 그대로 옮긴다. 순서는 입력 순서를 유지한다.
- `apply` 는 `delete_runs` → 각 `insert_exported` 를 돌리고 커밋한다.
  어떤 예외든 롤백하고 다시 던진다. `mark_exported` 와 같은 모양이다.
  `SyncResult` 는 실제 지운 개수와 실제 만든 개수다.
- `SyncResult` 는 화면이 문구 하나 만드는 데만 쓰므로 `core/models.py`
  가 아니라 이 모듈에 둔다.

---

## 8. `core/outline_import.py`

Streamlit 을 import 하지 않는 순수 함수 모듈이다.

```python
def find_source_url(markdown: str) -> str | None
```

- 첫 `^\s*---\s*$` 줄 앞까지를 머리 블록으로 본다. 구분선이 없으면 전체가
  머리 블록이다.
- 머리 블록에서 `^\s*-\s*영상 URL:\s*(\S+)\s*$` 에 맞는 **첫** 줄의 값을
  돌려준다. 없으면 `None`.
- `video_id` 는 여기서 뽑지 않는다. `youtube.extract_video_id` 가 이미
  있고, `plan` 이 그 결과로 "인식 불가"를 판정한다.

`markdown_export._metadata_block` 이 쓰는 라벨 문자열 `영상 URL` 을 두
곳에 따로 적지 않는다. `markdown_export` 에 `SOURCE_URL_LABEL = "영상
URL"` 상수를 두고 양쪽이 쓴다. 한쪽만 바뀌는 사고를 막는다.

---

## 9. 화면

### 9.1 `pages/history.py`

`st.title("이력")` 바로 아래에서 `_history_sync.render(connection)` 을
부른다. "아직 저장된 실행이 없습니다" 분기보다 **앞**이다. DB 를 막 지운
직후가 이 기능을 가장 필요로 하는 순간이기 때문이다.

### 9.2 `pages/_history_sync.py`

```
▸ Outline 과 동기화
    Outline 컬렉션의 문서 목록과 저장된 이력을 맞춥니다.
    Outline 에 없는 이력은 지우고, 이력에 없는 문서는 새로 만듭니다.
    [ 확인 ]

    ── 확인 후 ──
    지울 이력 2건 · 만들 문서 3건 · 건너뛴 문서 1건
    ▾ 지울 이력        제목 · 실행 시각
    ▾ 만들 문서        제목 · 문서 생성 시각 · 영상 URL
    ▾ 건너뛴 문서      제목 · 사유
    [ 적용 ]  [ 취소 ]
```

- 접은 영역(`st.expander`)이다. 기본은 접혀 있다.
- Outline 설정이 없으면 확인 버튼 대신 기존 저장 버튼과 같은 안내를 낸다.
  세 환경 변수 이름을 적는다.
- 확인 결과는 세션 키 `history_sync_plan` 에 둔다. 위젯 키가 아니라 우리가
  소유한 키다. 적용·취소 후 지운다.
- 지울 것도 만들 것도 없으면 "이미 맞습니다. 건너뛴 문서 N건" 만 내고 적용
  버튼을 그리지 않는다. 건너뛴 표는 그린다.
- 적용 후 결과 문구("지움 N건 · 만듦 M건")는 세션 키 `history_sync_result`
  에 담고 `st.rerun()` 한다. 다시 그릴 때 영역 위에 `st.success` 로 한 번
  내고 지운다.
- 세 표는 `st.dataframe` 이 아니라 `st.markdown` 리스트로 그린다. 항목이
  많지 않고, AppTest 로 문자열을 확인하기 쉽다.
- 실행 선택 selectbox 는 건드리지 않는다(2.5).
- 세션 키는 모듈 상수 `_PLAN_KEY`·`_RESULT_KEY` 로 둔다.

---

## 10. 오류 처리

| 상황 | 처리 |
|---|---|
| Outline 설정 없음 | 확인 버튼 자리에 안내 문구. 앱은 그대로 뜬다 |
| 목록 호출 실패(연결·401·403·404·429·5xx) | `OutlineError` 문구를 `st.error` 로. 세션에 plan 을 남기지 않는다 |
| 페이지네이션 도중 실패 | 부분 목록 없이 `OutlineError`. 위와 같이 처리 |
| 페이지 상한 초과 | `OutlineError`. "문서가 너무 많거나 목록 응답이 이상합니다" |
| 응답이 기대한 모양이 아님(JSON 깨짐·`data` 없음) | `OutlineError`. 기존 `_parse_document` 와 같은 방어 |
| 적용 중 SQLite 오류 | 롤백 후 `st.error`. 세션의 plan 은 **남겨** 다시 적용할 수 있게 한다 |
| 적용 중 다른 탭이 먼저 바꿈 | 오류 아님. 실제 개수를 결과 문구에 적는다 |

토큰은 어떤 문구에도 담지 않는다. `_failure_message` 가 이미 지킨다.

---

## 11. 테스트

기능 추가이므로 단위마다 실패하는 테스트를 먼저 쓴다. 실제 네트워크는
타지 않는다.

| 파일 | 확인할 것 |
|---|---|
| `tests/core/test_outline_import.py` (신규) | 영상 URL 줄에서 URL 추출 / 줄이 없으면 `None` / 첫 `---` 뒤의 같은 문구는 무시 / 구분선이 없으면 전체에서 찾음 / 정리본 본문(만든 날·정리 지시)은 `None` / 앞 공백·뒤 공백 허용 |
| `tests/services/test_outline.py` | `list_documents`: 컬렉션 필터가 요청 본문에 실림 · `nextPath` 를 따라 두 페이지를 합침 · 상한 초과 시 `OutlineError` · 두 번째 페이지 실패 시 부분 목록 없이 `OutlineError` · 401/403/404/429/5xx 가 각자 문구 · 토큰이 메시지에 안 샘 · 상대 URL 절대화 · `createdAt` 이 로컬 초 단위 ISO 로 바뀜 / 기존 테스트가 `outline_messages` 분리 뒤에도 그대로 통과 |
| `tests/services/test_history_sync.py` (신규) | `plan`: 5장의 다섯 규칙 각각 · 같은 영상 문서 둘은 둘 다 생성 · 같은 문서를 가리키는 행 둘은 손대지 않음 · 입력 순서 유지 · `is_empty` / `apply`: 삭제·삽입이 한 커밋 · 삽입 실패 시 삭제도 롤백 · 이미 있는 `outline_id` 는 건너뛰고 개수에 안 셈 · 없는 삭제 ID 는 개수에 안 셈 |
| `tests/services/test_run_history.py` | `list_exported` 가 `exported_at` 없는 행을 빼고 `LIMIT` 이 없음 / `insert_exported` 가 여덟 컬럼을 채우고 `answers` 를 만들지 않으며 커밋하지 않음 / 같은 `outline_id` 는 `None` / `delete_runs` 가 여러 ID 를 지우고 없는 ID 는 무시하며 커밋하지 않음 / `list_video_ids` 가 되살린 행의 ID 도 돌려줌 |
| `tests/pages/test_history.py` | AppTest: 설정 없으면 안내 · 확인 후 개수 한 줄과 세 표 · 적용이 DB 를 바꾸고 결과 문구 · 취소가 plan 만 비움 · 맞을 때 적용 버튼 없음 · 저장된 실행이 0건이어도 영역이 그려짐 · 목록 실패 시 `st.error` · 적용 후 선택이 살아남음 |

`plan` 과 `apply` 는 가짜 `poster` 없이 돈다. 화면 테스트는
`monkeypatch.setattr(outline, "list_documents", ...)` 로 바꿔 끼운다.
기존 `app_db` fixture 를 그대로 쓴다.

작업을 끝내기 전 `.claude/rules/streamlit-implement.md` 의 4종 검사를
순서대로 통과해야 한다: `ruff format` → `ruff check --fix` →
`mypy src tests` → `pytest`.

---

## 12. 건드리는 파일

**신규 — 소스 4, 테스트 2**

- `src/notebooklm_st/core/outline_import.py`
- `src/notebooklm_st/services/history_sync.py`
- `src/notebooklm_st/services/outline_messages.py` (7.1 의 분리)
- `src/notebooklm_st/pages/_history_sync.py`
- `tests/core/test_outline_import.py`
- `tests/services/test_history_sync.py`

**수정 8**

- `src/notebooklm_st/core/models.py` — 값 객체 넷
- `src/notebooklm_st/core/markdown_export.py` — `SOURCE_URL_LABEL` 상수
- `src/notebooklm_st/services/outline.py` — `list_documents`, 문구 분리
- `src/notebooklm_st/services/run_history.py` — 함수 셋
- `src/notebooklm_st/pages/history.py` — 호출 한 줄, 분기 위치
- `README.md` — 사용 순서에 동기화 단락, 한계(휴지통·중복·다른 문서 무시),
  DB 삭제 주의 문구에 "저장된 이력은 동기화로 되살릴 수 있다" 추가
- `tests/services/test_outline.py`, `tests/services/test_run_history.py`,
  `tests/pages/test_history.py`

**변경 없음**

- `src/notebooklm_st/services/store.py` — 스키마 그대로
- `src/notebooklm_st/services/runner.py`, `services/runs.py`
- `src/notebooklm_st/services/digest.py`, `digest_runner.py`,
  `core/digest_markdown.py`, `core/digest_title.py`
- `src/notebooklm_st/services/channels.py`, `channel_feed.py`,
  `pages/channels.py`, `pages/_channel_check.py`
- `docker-compose.yml`, `Dockerfile`, `pyproject.toml`

새 의존성은 없다. `httpx` 는 이미 있다.

---

## 13. 미검증 가정

- **목록 응답에 `text` 가 실리는가.** Outline OpenAPI 명세의 `Document`
  객체는 `text` 를 갖고 `documents.list` 가 `Document[]` 를 돌려준다.
  실제 배포판이 목록 응답에서 본문을 비운다면 문서마다
  `documents.info` 를 다시 불러야 한다. 구현 중 첫 실측에서 확인하고,
  다르면 그 자리에서 보고한다.
- **`nextPath` 의 모양.** 명세 예시는
  `/api/documents.list?limit=25&offset=25` 다. `base_url` 에 그대로 붙여
  `POST` 하되, 원래 요청 본문(`filters`·`sort`·`direction`)을 함께 다시
  보낸다. 쿼리 문자열만으로 필터가 유지되지 않을 수 있기 때문이다.
- **`createdAt` 의 시간대.** UTC ISO(`Z` 접미)로 온다고 본다. 접미가 없으면
  UTC 로 간주한다.
- **목록이 휴지통·보관 문서를 빼는가.** `documents.deleted` 와
  `documents.archived` 가 따로 있으므로 `documents.list` 는 발행된 문서만
  준다고 본다. 실측에서 휴지통 문서가 섞여 나오면 응답의 `deletedAt`·
  `archivedAt` 이 비어 있지 않은 항목을 앱이 걸러야 한다. 그 경우 5장의
  "휴지통 문서는 없음으로 본다" 는 그대로이고 거르는 자리만 는다.

---

## 14. 범위 밖

- 자동·주기 동기화
- 같은 영상 문서의 병합
- 미저장 실행과 문서의 자동 연결
- 정리본 문서의 이력화
- 질문 템플릿·채널 등록의 복구
- Outline 쪽 문서 삭제·수정
- 휴지통 문서의 조회(`documents.deleted`)
