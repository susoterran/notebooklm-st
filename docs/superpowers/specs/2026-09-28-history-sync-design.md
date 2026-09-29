# 이력 동기화 설계 — 저장된 이력을 Outline 문서 목록과 맞추기

- **작성일**: 2026-09-28
- **상태**: 구현 완료 (2026-09-28)
- **대상**: 신규 `services/history_sync.py`·`services/run_history_sync.py`·
  `services/outline_parse.py`·`services/outline_messages.py`·
  `core/outline_import.py`·`pages/_history_sync.py`, 수정
  `services/outline.py`·`services/run_history.py`·`core/models.py`·
  `core/markdown_export.py`·`pages/history.py`·`README.md`.
  스키마(`services/store.py`), 러너(`services/runner.py`),
  정리본(`services/digest*.py`·`core/digest*.py`), 채널
  (`services/channels.py`·`services/channel_feed.py`), 배포 파일
  (`docker-compose.yml`·`Dockerfile`·`pyproject.toml`)은 건드리지 않는다.
- **범위**: 이력 화면의 "Outline 과 동기화" 한 기능. 기존 저장·삭제 흐름은
  동작이 바뀌지 않는다.
- **전제**: Outline 1.10.0 이상. 목록의 컬렉션 조건이 이 버전에 생겼다(2.2).

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
  을 싣는다. `url` 은 상대 경로이며, `services/outline_parse.py` 의
  `absolute` 가 이를 `public_url` 에 붙인다.
- **목록 응답에도 `text` 가 실린다.** 문서마다 `documents.info` 를 다시
  부를 필요가 없다. 운영 서버(1.5.0·1.10.1)에서 확인을 눌러 목록을 받아
  보았다. `parse_listed_page` 는 `text` 가 빠진 항목이 하나라도 있으면
  목록 전체를 실패로 돌리는데, 두 버전 모두 계획까지 세워졌다.
- Outline 은 본문을 ProseMirror 편집기에 담아 두었다가 읽을 때 마크다운으로
  **다시 직렬화**한다. 그래서 우리가 쓴 줄이 글자 그대로 돌아온다고 보지
  않는다. 글머리표가 `*`·`+` 로 바뀌거나, 값이 `<URL>` 자동 링크나
  `[글](URL)` 링크로 감싸이거나, 값 안에 `\_`·`\-` 같은 역슬래시
  이스케이프가 들어와도 읽는 쪽이 받는다(8장). 영상 ID 에는 밑줄과
  하이픈이 흔하므로 이스케이프를 걷지 않으면 그런 문서가 전부 "인식
  불가"가 된다. 다만 실제 Outline 배포판이 머리 블록을 어떤 모양으로
  돌려주는지는 **아직 실측하지 않았다**(13장).

### 2.2 목록 호출은 Outline 1.10.0 부터 컬렉션을 거른다

`POST /api/documents.list` 는 `filters: [{field: "collectionId",
operator: "eq", value: ...}]` 로 컬렉션을 거르고, `sort`·`direction` 으로
정렬하며, `limit`·`offset` 으로 넘긴다. `limit` 의 상한은 100 이다.
휴지통과 보관 문서는 이 목록에 나오지 않는다(각각 `documents.deleted`·
`documents.archived` 가 따로 있다).

**`filters` 는 Outline 1.10.0 에 생겼다.** 그 아래 버전의 요청 스키마에는
이 키가 없고, 스키마가 모르는 키를 오류 없이 버린다. 컬렉션 조건이 빠진
요청에 서버는 사용자가 접근할 수 있는 **모든 컬렉션**의 문서를
돌려준다. 1.5.0 운영 서버에서 실제로 다른 컬렉션 문서가 "건너뛴 문서"
목록에 섞여 나왔다.

- 최상위 `collectionId` 하나만 보내면 1.5.0 과 1.10 모두 컬렉션을
  거른다. 다만 1.10 에서 deprecated 이고, `filters` 와 함께 보내면
  400 이다.
- 이 기능은 `filters` 를 쓰고 **Outline 1.10.0 이상**을 전제한다(3장).
- 앱은 응답 문서가 어느 컬렉션에 속하는지 다시 확인하지 않는다. 1.10.0
  미만 서버에 붙으면 오류 없이 다른 컬렉션 문서가 계획에 섞인다. 배포
  how-to(`docs/how-to/2026-09-16-homeserver-deploy.md`)의 검증 표가
  실제 서버에서 이것을 본다.

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
- `.claude/rules/streamlit-implement.md` 의 300줄 규칙이 있다. 새 코드를
  기존 파일에 더하면 `pages/history.py`·`services/run_history.py`·
  `services/outline.py` 가 그 선을 넘는다. 그래서 새 코드는
  `pages/_channel_check.py` 처럼 별도 파일로 뗀다(4장).
- `tests/pages/test_history.py` 는 `monkeypatch.setattr(outline,
  "create_document", ...)` 로 Outline 호출을 바꿔 끼운다. 목록 호출도
  같은 방법으로 바꿔 끼운다.
- `outline_messages.read_status_message` 의 401·403 문구는 조회용
  scope("documents.info"·읽기 권한)를 짚는다. 목록 호출에는
  "documents.list" 를 짚는 문구가 따로 필요하다.

### 2.5 실행 선택은 ID 기준이다

`pages/history.py` 의 selectbox 는 `RunSummary` 객체가 아니라 `run.id`
를 값으로 쓴다. 동기화가 기존 행을 건드리지 않으면 적용 뒤에도 선택이
살아남는다. 지워진 행을 고르고 있었다면 Streamlit 이 첫 항목으로 되돌린다
(기존 삭제에서 AppTest 로 확인한 동작).

### 2.6 실행 ID 는 다시 쓰인다

`runs.id` 는 `INTEGER PRIMARY KEY` 이고 `AUTOINCREMENT` 가 없다. SQLite 는
가장 큰 ID 의 행이 지워지면 다음 삽입에 그 ID 를 다시 준다. 실행 ID 하나만
으로는 "미리보기 때 본 그 행"을 가리킨다고 보장할 수 없다.

---

## 3. 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 실행 시점 | **사람이 버튼을 눌렀을 때만** | "앱은 Outline 을 읽지 않는다" 원칙의 취지는 Outline 장애가 이력 화면을 막지 않는 것이다. 사람이 누를 때만 읽으면 그 취지가 유지된다. 자동·주기 실행은 두지 않는다 |
| 적용 방식 | **미리보기 후 적용** | 무엇이 지워지는지 먼저 본다. 기존 삭제 UI 의 2단계와 같다 |
| 컬렉션 조건 | **`filters` 로 보내고 Outline 1.10.0 이상을 요구한다** | 1.10 이 권하는 방식이다. 최상위 `collectionId` 는 두 버전에서 모두 동작하지만 1.10 에서 deprecated 다. 1.10.0 미만은 `filters` 를 조용히 버리므로(2.2) 지원하지 않는다 |
| 기존 행 | **손대지 않는다** | 전부 지우고 재구축하면 ID 가 바뀌어 다른 탭의 선택이 풀리고 원래 실행 시각이 덮인다. 차이만 적용한다 |
| 미저장 실행 | **입력에서 뺀다** | `exported_at` 이 없는 행은 아직 올리지 않은 것이다. 삭제될 수 없어야 한다 |
| 삭제 기준 | **실행 ID 와 문서 ID 가 둘 다 맞을 때만** | 계획은 적용·취소 전까지 세션에 남고, 그사이 ID 가 다른 실행에 다시 쓰일 수 있다(2.6). 문서 ID 까지 맞춰야 미저장 실행이 지워지지 않는다 |
| 미저장 실행과 같은 영상의 문서 | **새 행을 만들고 미저장은 그대로** | 그 문서가 정말 그 실행에서 나왔는지 확인할 길이 없다. 본문을 지우는 판단은 사람이 한다 |
| 같은 영상의 문서 둘 | **둘 다 만든다** | 동기화는 위키를 정리하지 않는다. 합치는 판단도 사람이 한다 |
| 영상 URL 줄이 없는 문서 | **건너뛰고 사유를 보여 준다** | 정리본·손으로 쓴 문서는 이력이 아니다. 조용히 무시하면 왜 안 들어왔는지 알 수 없다 |
| 영상 URL 줄의 모양 | **Outline 의 재직렬화 변형을 받는다** | 우리가 쓴 줄이 그대로 돌아온다는 보장이 없다(2.1). 한 가지 모양만 받으면 변형 하나에 모든 요약본이 건너뛰어진다 |
| 휴지통·보관 문서 | **"없음"으로 본다** | 목록에 나오지 않는다. 복원하면 다음 동기화가 다시 만든다 |
| 부분 목록 | **계획을 세우지 않는다** | 절반만 본 목록으로 지우면 멀쩡한 이력이 사라진다 |
| 스키마 | **바꾸지 않는다** | 필요한 컬럼이 전부 있다. DB 파일을 지울 일이 없다 |

---

## 4. 구조

```
pages/_history_sync.py           버튼·미리보기·적용 (Streamlit 만 안다)
   │
   ├─► services/outline.list_documents(config)          컬렉션 문서 전부
   ├─► services/run_history_sync.list_exported(conn)    exported_at 이 있는 행
   ├─► services/history_sync.plan(exported, docs)       순수 비교 → SyncPlan
   └─► services/history_sync.apply(conn, plan)          삭제 + 삽입, 커밋 하나
             ├─► run_history_sync.delete_runs           (id, outline_id) 쌍
             └─► run_history_sync.insert_exported
core/outline_import.py           문서 본문 → 영상 URL (순수 함수)
```

경계는 이렇다.

- **`core/outline_import.py` 는 마크다운 문자열만 받는다.** `markdown_export`
  가 쓴 줄을 거꾸로 읽는 짝이므로 그 모듈 옆에 둔다.
- **`services/history_sync.py` 는 `plan`·`apply` 와 결과 값 `SyncResult`
  뿐이다.** httpx 도 Streamlit 도 모른다. `plan` 은 두 목록을 받아
  `SyncPlan` 을 돌려주는 순수 함수이고, `apply` 는 그것을 DB 에 쓴다. DB 를
  직접 읽고 쓰는 일은 `services/run_history_sync.py` 에 맡긴다.
- **`services/run_history_sync.py` 는 동기화만 쓰는 저장소 함수 셋이다.**
  `run_history.py` 에 두면 300줄을 넘고, 커밋 규약도 다르다 — 이쪽은
  커밋하지 않고 트랜잭션을 `apply` 에 맡긴다. SELECT 머리와 행 변환은
  `run_history` 의 것을 함께 쓴다(7.2).
- **`services/outline.py` 는 목록 호출 하나가 는다.** Outline 을 부르는
  유일한 모듈이라는 자리는 그대로다. 대신 300줄 안에 머물도록 호출과 상태
  코드 판정만 남기고 둘을 뗀다. 값 객체와 응답 본문 해석은
  `services/outline_parse.py`, 실패 상태를 사람이 읽을 문장으로 옮기는
  일은 `services/outline_messages.py` 가 맡는다(7.1).
- **`pages/_history_sync.py` 는 `pages/history.py` 가 부른다.**

흐름은 이렇다.

```
이력 화면의 "Outline 과 동기화" 접은 영역
    ↓
config_from_env() 없음 → 안내 문구, 끝 (확인 버튼 없음)
    ↓
"확인" 버튼
    ↓
list_documents(config) (스피너) ── OutlineError → st.error, 지난 plan 삭제, 끝
    ↓
plan(list_exported(conn), documents) → 세션 history_sync_plan
    ↓
미리보기: 개수 한 줄 + 세 목록
    ↓
"적용" → apply(conn, plan) → 세션 plan 삭제, 결과 문구 세션에 저장, rerun
         └ sqlite3.Error → st.error, plan 은 남김
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
  줄의 모양은 Outline 의 재직렬화 변형을 받는다(8장).
- **미리보기와 적용 사이에 DB 가 바뀐 경우**는 적용 직전에 목록을 다시
  읽지 않는다. 대신 쓰는 쪽이 스스로 지킨다. 삭제는 **실행 ID 와 문서
  ID 가 둘 다 맞는 행만** 지운다. 다른 탭이 지울 행을 먼저 지웠으면 그
  쌍은 0건일 뿐이다. 사람이 그 행을 손으로 지운 뒤 새로 실행해 같은 ID
  가 다시 쓰였어도(2.6), 새 실행은 `outline_id` 가 비어 있어 쌍과 맞지
  않으므로 지워지지 않는다. 만들 문서의 `outline_id` 가 이미 있으면 그
  항목만 건너뛴다. 결과 문구에는 실제 개수를 적는다.

생성 행의 값은 이렇다.

| 컬럼 | 값 |
|---|---|
| `url` | 본문의 영상 URL (이스케이프를 걷은 값) |
| `video_id` | `youtube.extract_video_id(url)` |
| `title` | Outline 문서 제목 |
| `created_at` | 문서 `createdAt` 을 로컬 시각의 초 단위 ISO 문자열로 바꾼 값(`store.now()` 와 같은 형식) |
| `exported_at` | `created_at` 과 같은 값 |
| `outline_id` | 문서 ID |
| `outline_title` | 문서 제목 |
| `outline_url` | 상대 URL 을 `public_url` 에 붙인 절대 URL (`outline_parse.absolute` 재사용) |

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
    """미리보기와 적용이 함께 쓰는 동기화 계획.

    기존 행 중 손대지 않는 것은 담지 않는다.
    """

    deletes: tuple[RunSummary, ...]
    creates: tuple[SyncCreate, ...]
    skips: tuple[SyncSkip, ...]

    @property
    def is_empty(self) -> bool:
        """지울 것도 만들 것도 없다."""
        return not self.deletes and not self.creates
```

`ListedDocument` 는 기존 `OutlineDocument`(정리본이 쓴다.
`services/outline_parse.py` 에 정의하고 `services/outline.py` 가 같은
이름으로 내보낸다)와 다르다. 정리본은 ID·제목·본문만 필요하고, 동기화는
URL 과 생성 시각도 필요하다. `OutlineDocument` 에 필드를 더하면 정리본
테스트가 함께 바뀌므로 따로 둔다. `core` 에 두는 이유는 `SyncPlan` 이
담아야 하고 `SyncPlan` 은 화면과 서비스가 함께 쓰기 때문이다.

---

## 7. 서비스 계층

### 7.1 `services/outline.py` 와 두 보조 모듈

```python
LIST_PAGE_SIZE = 100
LIST_PAGE_LIMIT = 50


def list_documents(
    config: OutlineConfig,
    timeout: float = FETCH_TIMEOUT,
    poster: PostLike = httpx.post,
) -> list[models.ListedDocument]
```

- **세 호출 경로(생성·조회·목록)는 `_post` 하나를 거친다.**
  `_post(config, path, payload, timeout, poster, status_message)` 는
  연결 주소에 경로를 붙이고 Bearer 헤더를 실어 보낸다. 연결 실패
  (`httpx.HTTPError`·`httpx.InvalidURL`)와 400 이상 상태를 `OutlineError`
  로 옮기고, 그 문장은 경로마다 넘긴 `status_message` 함수가 정한다.
  경로마다 다른 것은 주소·본문·상태 문구뿐이다.
- **목록은 offset 으로 넘긴다.** `list_documents` 는 `_list_page(config,
  offset, timeout, poster)` 를 `offset` 0, `LIST_PAGE_SIZE`,
  `2 × LIST_PAGE_SIZE` … 로 이어 부른다. `_list_page` 는
  `_LIST_PATH = "/api/documents.list"` 에 `filters` 컬렉션 조건(2.2),
  `sort: "createdAt"`, `direction: "DESC"`, `limit: LIST_PAGE_SIZE`,
  `offset` 을 싣는다. 한 페이지가 `LIST_PAGE_SIZE` 보다 짧게 오면(빈
  페이지 포함) 끝으로 본다. 응답의 `pagination.nextPath` 는 쓰지 않는다 —
  마지막 페이지에도 실려 올 수 있어 끝을 알려 주지 못한다.
- **`LIST_PAGE_LIMIT` 페이지를 가득 채워 받아도 끝나지 않으면
  `OutlineError` 다.** 응답이 이상해 짧은 페이지가 끝내 오지 않아도
  무한히 돌지 않게 한다. 5,000 건이면 개인 위키의 요약본으로는 충분하다.
- **어느 페이지든 실패하면 지금까지 모은 것을 버리고 `OutlineError` 다.**
- **응답 해석은 `outline_parse.parse_listed_page(config, response)` 가
  한다.** 한 항목이라도 기대한 키가 없거나 시각이 읽히지 않으면 페이지
  전체가 실패다 — 그 항목만 조용히 빼면 다음 동기화가 그 행을 지운다.
  상대 URL 은 `outline_parse.absolute(config.public_url, url)` 로
  절대화한다. `createdAt`(UTC ISO) 은 `outline_parse.to_local_time` 이
  로컬 시각의 초 단위 ISO 문자열로 바꾼다. `datetime.fromisoformat` →
  접미가 없으면 UTC 로 간주 → `astimezone()` → tz 를 떼고
  `isoformat(timespec="seconds")` 다. `store.now()` 와 같은 모양이어야
  목록 라벨이 섞여도 어색하지 않다.
- **상태 문구는 `outline_messages.list_status_message` 다.** 401·403 은
  "documents.list" scope 를 먼저 짚고, 404 는 "주소를 확인하라", 429 는
  "잠시 뒤 다시 시도" 다. 나머지는 `read_status_message` 와 같이 상태
  코드를 그대로 보여 준다. scope 밖 호출에 Outline 1.10 은 403 을,
  1.5.0 은 401 을 준다. 그래서 두 코드 모두 scope 를 짚는다. 429 를 따로
  두는 것은 목록이 여러 페이지를 연달아 부르는 유일한 경로이기
  때문이다. 1.10 은 rate limiter 가 기본으로 켜져 있고 목록은 분당
  100회까지다. 응답 설명을 붙이고 토큰을 가리는 일은 기존
  `outline_messages.failure_message` 를 그대로 쓴다.
- **모듈은 셋으로 나뉜다.** 300줄 규칙 때문이다.
  - `services/outline.py` — `config_from_env`·`_post`·`create_document`·
    `fetch_document`·`list_documents`·`_list_page`. 호출과 상태 코드
    판정만 한다.
  - `services/outline_parse.py` — 값 객체(`OutlineConfig`·
    `SavedDocument`·`OutlineDocument`·`OutlineError`)와 응답 본문 해석
    (`parse_saved_document`·`parse_outline_document`·
    `parse_listed_page`·`to_local_time`·`absolute`). HTTP 호출도 상태
    코드도 모른다.
  - `services/outline_messages.py` — 상태 코드를 안내 문장으로 옮기는
    `create_status_message`·`read_status_message`·`list_status_message`
    와 `failure_message`·`detail`.

  `services/outline.py` 가 값 객체를 같은 이름으로 다시 내보내므로 호출자와
  `tests/services/test_outline.py` 의 기존 테스트는 그대로다.

### 7.2 `services/run_history_sync.py`

```python
def list_exported(
    connection: sqlite3.Connection,
) -> list[models.RunSummary]
def insert_exported(
    connection: sqlite3.Connection, create: models.SyncCreate
) -> int | None
def delete_runs(
    connection: sqlite3.Connection, keys: Sequence[tuple[int, str]]
) -> int
```

- `list_exported` 는 `run_history.SUMMARY_SELECT` 에 `WHERE r.exported_at
  IS NOT NULL`·`GROUP BY r.id`·`ORDER BY r.id DESC` 를 붙이고 `LIMIT` 을
  두지 않는다. 동기화는 전부 봐야 한다. 행은 `run_history.row_to_summary`
  로 요약이 된다. 두 이름은 `list_runs` 와 이 모듈이 함께 쓰도록
  `run_history` 가 공개한다 — 같은 SQL 을 두 모듈에 두지 않는다.
- `insert_exported` 는 여덟 컬럼을 채운 `runs` 행 하나를 넣고 ID 를
  돌려준다. 같은 `outline_id` 를 가진 행이 이미 있으면 넣지 않고 `None`
  을 돌려준다. **커밋하지 않는다.**
- `delete_runs` 는 `(실행 ID, 문서 ID)` 쌍을 받아 `DELETE FROM runs WHERE
  id = ? AND outline_id = ?` 를 `executemany` 로 돌리고 `rowcount` 를
  돌려준다. sqlite3 는 `executemany` 의 DML `rowcount` 를 문장마다
  더해 준다. 맞는 행이 없는 쌍은 무시하고, 빈 입력은 SQL 없이 0 이다.
  딸린 답변은 외래키의 `ON DELETE CASCADE` 가 지운다. **커밋하지 않는다.**
  ID 만으로 지우지 않는 이유는 2.6 과 5장에 있다.
- 트랜잭션은 `history_sync.apply` 가 소유한다. 기존 `save_run`·
  `mark_exported`·`delete_run` 은 `run_history` 에 남아 각자 커밋한다.
  규약이 갈리는 것을 모듈 독스트링에 적는다.

### 7.3 `services/history_sync.py`

```python
SKIP_NO_SOURCE_URL = "영상 URL 없음"
SKIP_BAD_SOURCE_URL = "영상 URL 인식 불가"


def plan(
    exported: Sequence[models.RunSummary],
    documents: Sequence[models.ListedDocument],
) -> models.SyncPlan


@dataclasses.dataclass(frozen=True, slots=True)
class SyncResult:
    deleted: int
    created: int


def apply(
    connection: sqlite3.Connection, sync_plan: models.SyncPlan
) -> SyncResult
```

- `plan` 은 5장의 규칙을 그대로 옮긴다. 순서는 입력 순서를 유지한다.
- `apply` 는 `delete_runs` 에 `[(run.id, run.outline_id or "") for run in
  sync_plan.deletes]` 를 넘긴 뒤 각 `insert_exported` 를 돌리고 커밋한다.
  어떤 예외든 롤백하고 다시 던진다. `mark_exported` 와 같은 모양이다.
  저장된 행은 `outline_id` 가 늘 있으므로 `or ""` 는 타입을 맞출 뿐이고,
  빈 문자열은 어떤 행과도 맞지 않는다.
- `SyncResult` 는 **실제로** 지운 개수(`delete_runs` 의 `rowcount`)와
  **실제로** 만든 개수(`insert_exported` 가 `None` 이 아닌 수)다. 계획의
  개수와 다를 수 있다 — 미리보기와 적용 사이에 다른 탭이 먼저 지우거나
  저장했을 수 있다.
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
- 머리 블록에서 영상 URL 줄에 맞는 **첫** 줄의 값을 돌려준다. 없으면
  `None`. 라벨만 있고 값이 없는 줄은 맞지 않는다.
- 줄의 모양은 Outline 의 재직렬화 변형(2.1)을 받는다.
  - 글머리표는 `-`·`*`·`+` 중 하나다. 앞뒤와 라벨 뒤 공백을 허용한다.
  - 값은 맨 URL, `<URL>` 자동 링크, `[글](URL)` 링크 셋 중 하나다.
    자동 링크면 괄호 안을, 링크면 글이 URL 이든 아니든 주소 쪽을 쓴다.
    주소는 공백이 없는 한 덩어리다.
  - 꺼낸 값에서 `\_`·`\-`·`\*`·`\#` 의 역슬래시를 걷는다.
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
    지울 이력      - 제목 · 실행 시각
    만들 문서      - 제목 · 문서 생성 시각 · 영상 URL
    건너뛴 문서    - 제목 · 사유
    [ 적용 ]  [ 취소 ]
```

- 접은 영역(`st.expander`)이다. 기본은 접혀 있다.
- Outline 설정이 없으면 확인 버튼 대신 기존 저장 버튼과 같은 안내를 낸다.
  세 환경 변수 이름을 적는다.
- 확인을 누르면 목록을 읽는 동안 "Outline 문서 목록을 읽는 중" 스피너를
  띄운다. 목록은 여러 페이지를 이어 부를 수 있다.
- 확인 결과는 세션 키 `history_sync_plan` 에 둔다. 위젯 키가 아니라 우리가
  소유한 키다. 적용·취소 후 지운다. 목록 읽기가 실패해도 지운다 — 지난
  계획이 남으면 실패한 뒤에도 적용 버튼이 보인다.
- 지울 것도 만들 것도 없으면 "이미 맞습니다. 건너뛴 문서 N건." 만 내고 적용
  버튼을 그리지 않는다. 건너뛴 목록은 그린다.
- 적용 후 결과 문구("동기화 완료 · 지움 N건 · 만듦 M건")는 세션 키
  `history_sync_result` 에 담고 `st.rerun()` 한다. 다시 그릴 때 영역 위에
  `st.success` 로 한 번 내고 지운다.
- 세 목록은 굵은 제목 아래 `st.markdown` 리스트로 그린다. expander 는
  중첩할 수 없고, 항목이 많지 않으며, AppTest 로 문자열을 확인하기 쉽다.
- 실행 선택 selectbox 는 건드리지 않는다(2.5).
- 세션 키는 모듈 상수 `_PLAN_KEY`·`_RESULT_KEY` 로 둔다.

---

## 10. 오류 처리

| 상황 | 처리 |
|---|---|
| Outline 설정 없음 | 확인 버튼 자리에 안내 문구. 앱은 그대로 뜬다 |
| 목록 호출 실패(연결·401·403·404·429·5xx) | `OutlineError` 문구를 `st.error` 로. 세션의 지난 plan 도 지운다 |
| 페이지네이션 도중 실패 | 부분 목록 없이 `OutlineError`. 위와 같이 처리 |
| 페이지 상한 초과 | `OutlineError`. "Outline 문서 목록이 너무 길거나 목록 응답이 이상합니다(페이지 상한 50)." |
| 응답이 기대한 모양이 아님(JSON 깨짐·`data` 없음·항목의 키 없음·시각 못 읽음) | `OutlineError`. `outline_parse.parse_listed_page` 가 페이지째 거부한다 |
| Outline 이 1.10.0 미만 | 오류가 나지 않는다. 다른 컬렉션 문서가 계획에 섞인다(2.2). 앱은 막지 않고, 배포 검증이 잡는다 |
| 적용 중 SQLite 오류 | 롤백 후 `st.error`("적용에 실패했습니다(오류 이름). 다시 적용할 수 있습니다."). 세션의 plan 은 **남겨** 다시 적용할 수 있게 한다 |
| 적용 중 다른 탭이 먼저 바꿈 | 오류 아님. 실제 개수를 결과 문구에 적는다 |
| 지울 행의 ID 가 다른 실행에 다시 쓰임 | 오류 아님. 문서 ID 가 맞지 않아 지우지 않고 개수에도 들지 않는다 |

토큰은 어떤 문구에도 담지 않는다. `outline_messages.failure_message` 가
이미 지킨다.

---

## 11. 테스트

기능 추가이므로 단위마다 실패하는 테스트를 먼저 쓴다. 버그를 고칠 때는
그 버그를 재현하는 테스트를 먼저 쓴다. 실제 네트워크는 타지 않는다.

| 파일 | 확인할 것 |
|---|---|
| `tests/core/test_outline_import.py` (신규) | 영상 URL 줄에서 URL 추출 / 줄이 없으면 `None` / 첫 `---` 뒤의 같은 문구는 무시 / 구분선이 없으면 전체에서 찾음 / 정리본 본문(만든 날·정리 지시)은 `None` / 앞 공백·뒤 공백 허용 / 같은 줄이 둘이면 첫 줄 / 값 없는 라벨은 `None` / 재직렬화 변형: `*` 글머리표 · `+` 글머리표 · `<URL>` 자동 링크 · `[URL](URL)` 링크 · `[글](URL)` 링크 · 영상 ID 안의 `\_`·`\-` · `\*`·`\#` · 글머리표·링크·이스케이프가 겹친 줄 · 구분선 뒤의 변형 줄은 무시 |
| `tests/services/test_outline.py` | `list_documents`: 주소·헤더·본문(컬렉션 필터·정렬·`limit`·`offset`)이 API 계약대로 나감 · 다섯 값을 꺼내고 URL 을 공개 주소로 절대화 · `createdAt` 이 로컬 초 단위 ISO 로 바뀜 · 접미 없는 `createdAt` 은 UTC · 가득 찬 페이지 뒤에는 다음 `offset` 으로 다시 부르고 짧은 페이지에서 멈춤 · 빈 페이지에서 멈춤 · 상한 초과 시 `OutlineError` · 두 번째 페이지 실패 시 부분 목록 없이 `OutlineError` · `data` 없음·`text` 없음·읽히지 않는 `createdAt` 은 목록 전체 실패 · 연결 실패 문구 · 401/403/404/429/5xx 가 각자 문구 · 토큰이 메시지에 안 샘 / 기존 테스트가 `outline_parse`·`outline_messages` 분리 뒤에도 그대로 통과 |
| `tests/services/test_run_history_sync.py` (신규) | `list_exported` 가 `exported_at` 없는 행을 빼고 상한이 없음 / `insert_exported` 가 여덟 컬럼을 채우고 `answers`·`run_metadata` 를 만들지 않으며 커밋하지 않음 · 같은 `outline_id` 는 `None` / `delete_runs` 가 여러 쌍을 지우고 개수를 돌려줌 · 없는 ID 는 세지 않음 · ID 가 같아도 문서 ID 가 다르면(미저장 실행 포함) 지우지 않음 · 빈 입력은 0 · 커밋하지 않음 / `list_video_ids` 가 되살린 행의 ID 도 돌려줌 |
| `tests/services/test_history_sync.py` (신규) | `plan`: 5장의 다섯 규칙 각각 · 컬렉션이 비면 저장된 행 전부 삭제 · 같은 영상 문서 둘은 둘 다 생성 · 같은 문서를 가리키는 행 둘은 손대지 않음 · 입력 순서 유지 · `is_empty` / `apply`: 삭제·삽입이 한 커밋(적용 뒤 열린 트랜잭션이 없음) · 삽입 실패 시 삭제도 롤백 · 이미 있는 `outline_id` 는 건너뛰고 개수에 안 셈 · 없는 삭제 ID 는 개수에 안 셈 · 빈 계획은 0·0 · 낡은 계획: 저장된 행을 손으로 지우고 같은 ID 를 받은 미저장 실행을 만든 뒤 적용해도 그 실행과 답변이 남고 `deleted` 가 0 |
| `tests/pages/test_history.py` | AppTest: 저장된 실행이 0건이어도 영역이 그려지고 설정 없으면 안내만 · 설정 있으면 확인 버튼 · 확인 후 개수 한 줄과 세 목록, DB 는 그대로 · 적용이 DB 를 바꾸고 결과 문구, 적용 버튼 사라짐 · 취소가 plan 만 비움 · 맞을 때 적용 버튼 없고 건너뛴 문서는 보임 · 목록 실패 시 `st.error` 와 함께, 먼저 성공한 확인으로 만든 실제 plan 이 지워짐 · 적용 실패 시 문구를 내고, 한 번 더 다시 그려도 적용 버튼과 plan 이 남음 · 적용 뒤 선택 유지(살아남는 실행 둘 중 고른 쪽이 그대로) · 다른 위젯을 건드려도 미리보기가 남음 |

`plan` 과 `apply` 는 가짜 `poster` 없이 돈다. 화면 테스트는
`monkeypatch.setattr(outline, "list_documents", ...)` 로 바꿔 끼운다.
기존 `app_db` fixture 를 그대로 쓴다.

가짜 `poster` 는 우리가 보낸 본문만 본다. 서버가 그 컬렉션 조건을
받아들이는지는 확인하지 못한다. 그것은 배포 how-to 의 검증 표가 실제
서버에서 본다(2.2).

작업을 끝내기 전 `.claude/rules/streamlit-implement.md` 의 4종 검사를
순서대로 통과해야 한다: `ruff format` → `ruff check --fix` →
`mypy src tests` → `pytest`.

---

## 12. 건드리는 파일

**신규 — 소스 6, 테스트 3**

- `src/notebooklm_st/core/outline_import.py`
- `src/notebooklm_st/services/history_sync.py`
- `src/notebooklm_st/services/run_history_sync.py` (7.2)
- `src/notebooklm_st/services/outline_parse.py` (7.1 의 분리)
- `src/notebooklm_st/services/outline_messages.py` (7.1 의 분리)
- `src/notebooklm_st/pages/_history_sync.py`
- `tests/core/test_outline_import.py`
- `tests/services/test_run_history_sync.py`
- `tests/services/test_history_sync.py`

**수정 8**

- `src/notebooklm_st/core/models.py` — 값 객체 넷
- `src/notebooklm_st/core/markdown_export.py` — `SOURCE_URL_LABEL` 상수
- `src/notebooklm_st/services/outline.py` — `_post`·`list_documents`·
  `_list_page`, 값 객체·응답 해석·상태 문구를 두 모듈로 분리
- `src/notebooklm_st/services/run_history.py` — `SUMMARY_SELECT`·
  `row_to_summary` 공개(`run_history_sync` 와 공유)
- `src/notebooklm_st/pages/history.py` — 호출 한 줄, 분기 위치
- `README.md` — 사용 순서에 동기화 단락, 한계(휴지통·보관함·중복·다른
  문서 무시), DB 삭제 주의 문구에 "저장된 이력은 동기화로 되살릴 수
  있다" 추가
- `tests/services/test_outline.py`, `tests/pages/test_history.py`

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

- **`createdAt` 의 시간대.** UTC ISO(`Z` 접미)로 온다고 본다. 접미가 없으면
  UTC 로 간주한다.
- **목록이 휴지통·보관 문서를 빼는가.** `documents.deleted` 와
  `documents.archived` 가 따로 있으므로 `documents.list` 는 발행된 문서만
  준다고 본다. 실측에서 휴지통 문서가 섞여 나오면 응답의 `deletedAt`·
  `archivedAt` 이 비어 있지 않은 항목을 앱이 걸러야 한다. 그 경우 5장의
  "휴지통 문서는 없음으로 본다" 는 그대로이고 거르는 자리만 는다.
- **실제 Outline 이 머리 블록을 어떻게 재직렬화하는지 미실측.** 8장은
  ProseMirror 직렬화기가 낼 법한 변형(글머리표 `*`·`+`, `<URL>`,
  `[글](URL)`, 역슬래시 이스케이프)을 받지만, 실제 배포판이 돌려준 본문을
  아직 본 적이 없다. 첫 실측에서 모든 요약본이 "영상 URL 없음"이나 "인식
  불가"로 건너뛰어지면 이 자리부터 본다. 구분선이 `***`·`___` 로 바뀌어
  돌아오면 머리 블록의 끝을 못 찾아 전체에서 찾게 되지만, 첫 줄이
  이기므로 머리 블록의 줄이 먼저 잡힌다.

---

## 14. 범위 밖

- 자동·주기 동기화
- 같은 영상 문서의 병합
- 미저장 실행과 문서의 자동 연결
- 정리본 문서의 이력화
- 질문 템플릿·채널 등록의 복구
- Outline 쪽 문서 삭제·수정
- 휴지통 문서의 조회(`documents.deleted`)
- Outline 1.10.0 미만 서버 지원과, 응답 문서의 컬렉션을 앱이 다시
  확인하는 일
