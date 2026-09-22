# Outline 저장 설계 — 요약본의 집을 위키로 옮기기

- **작성일**: 2026-09-22
- **상태**: 설계 (구현 계획 수립 전)
- **대상**: `services/outline.py`(신규), `services/store.py`,
  `services/run_history.py`, `core/models.py`,
  `core/markdown_export.py`, `components/answer_view.py`,
  `pages/history.py`, `pyproject.toml`, `docker-compose.yml`.
  질의 파이프라인(`services/nlm.py`)과 실행 모델(`services/runs.py`),
  러너(`services/runner.py`), 인증(`services/auth.py`),
  메타데이터 조회(`services/video_metadata.py`)는 건드리지 않는다.
- **범위**: 릴리스 R4. 기획 문서
  `docs/requests/2026-09-16-summary-pipeline-v2.md` 의 **요구 3**.
  선행 조건인 R1(무인 갱신 인증)·R2(컨테이너 배포)·R3(영상 메타데이터)는
  완료되었다.

---

## 1. 왜 바꾸는가

요약본이 **홈서버 안에만 있다.** `questions.db` 는 컨테이너 볼륨에 있고,
그 파일을 읽는 길은 이 앱의 이력 화면 하나뿐이다. 기획 §2-2 가 말하는
불편이 여기서 나온다 — 밖에서 볼 수 없고, 검색할 수 없고, 백업은 직접
챙겨야 한다.

이력 화면이 제공하는 것도 요약본을 **가공하는 수단**이 아니다. 답변 하나를
고치는 텍스트 상자와, 파일 하나를 내려받는 버튼이 전부다. 위키가 이미
하는 일을 앱 안에서 작게 흉내 내고 있다.

R4 는 **요약본의 집을 Outline 으로 옮긴다.** 앱은 요약을 만들어 사람에게
확인받고 위키에 올리는 데까지만 책임지고, 그 뒤의 수정·삭제·검색·백업은
Outline 이 한다. 앱에는 문서명과 링크만 남는다.

### 1.1 무엇을 옮기지 않는가

- **질문 템플릿**은 계속 SQLite 에 있다. 앱의 설정이지 문서가 아니다.
- **실행 결과의 첫 도착지**도 계속 SQLite 다. 저장 게이트가 사람이므로
  버튼을 누를 때까지 결과가 디스크에 있어야 한다(→ 3, C안 기각).
- **본문 "개요" 의 "모름"** 은 R3 이 남긴 그대로다. 고치려면 질의
  파이프라인을 건드려야 한다(→ 14).

---

## 2. 조사로 확인한 사실

### 2.1 `documents.create` 의 계약

공식 API 문서(https://www.getoutline.com/developers)에서 확인했다.

- `POST {base}/api/documents.create`
- 필수: `title`, `collectionId`. 선택: `text`(마크다운), `publish`,
  `parentDocumentId`
- 인증: `Authorization: Bearer <API 키>`
- 응답: JSON. 만들어진 문서 객체가 `data` 에 온다
- 문서는 CommonMark 마크다운으로 저장된다

**문서 제목은 `title` 파라미터가 정한다.** 본문과 별개의 필드다.

### 2.2 API 키는 사용자 권한을 상속하고, scope 는 엔드포인트 단위다

Outline 가이드(https://docs.getoutline.com/s/guide/doc/api-1rEIXDfLF6)와
`outline/outline#8186` 에서 확인했다.

- API 키는 **개인 액세스 토큰**이다. 만든 사용자의 권한을 그대로 갖는다
- `scopes` 는 **공백으로 구분한 엔드포인트 목록**이다(`documents.*`,
  `*.info` 같은 와일드카드 가능). 비우면 제한이 없다
- **"이 컬렉션에만" 이라는 범위 지정은 없다.** 컬렉션 단위로 가두려면
  그 컬렉션에만 접근 가능한 사용자를 따로 만들어 그 사용자로 키를
  발급해야 한다

이 앱이 부르는 엔드포인트는 `documents.create` **하나뿐**이므로, 키의
scope 는 그 한 줄이면 된다(→ 9.2).

### 2.3 `httpx` 는 이미 락 파일에 있다

`notebooklm-py==0.8.1` 의 직접 의존이다(`uv.lock`). 새 패키지를 받지
않아도 되지만, **전이 의존을 직접 쓰는 것은 다른 얘기다.**
`notebooklm-py` 가 다음 버전에서 갈아타면 조용히 깨진다. `pyproject.toml`
에 직접 의존으로 명시한다(→ 10).

### 2.4 이 프로젝트에는 마이그레이션이 없다

`services/store.py` 가 의도적으로 정한 것이다. `_EXPECTED_COLUMNS` 와
실제 컬럼을 비교해 어긋나면 `StaleSchemaError` 를 던지고, 화면은 "이
파일을 지우고 다시 실행하세요" 를 안내한다.

R4 는 `runs` 에 컬럼을 넷 더하므로 **기존 `questions.db` 는 열리지
않는다.** 옛 이력을 버리기로 했으므로(→ 3) 의도한 동작이고, 배포 절차에
파일을 지우는 한 줄을 넣는다.

### 2.5 frontmatter 는 Outline 화면에서 맨 텍스트로 보인다

Outline 편집기는 `---` 를 구분선으로 렌더한다. 따라서 R3 이 만든 YAML
frontmatter 를 `text` 에 그대로 실으면 위키에서는 "구분선 → `title: …`
같은 텍스트 네 줄 → 구분선" 으로 보인다. 링크도 걸리지 않는다.

그럼에도 **형식을 그대로 싣기로 했다**(→ 3). 대신 사람이 클릭할 출처
링크는 본문 첫 블록이 따로 맡는다(→ 7.2).

---

## 3. 설계 결정

| 결정 | 근거 |
|---|---|
| 저장은 **사람이 버튼으로** 한다 | 위키는 오래 남는 자리다. 마음에 안 드는 결과가 자동으로 쌓이면 치우는 일이 사람에게 돌아온다 |
| 실행 결과의 첫 도착지는 **계속 SQLite** | 게이트가 사람이면 결과는 디스크에 있어야 한다. 메모리에 들고 있다가 재시작하면 몇 분 걸린 요약이 사라진다 |
| 저장에 성공하면 **본문을 지우고 링크만 남긴다** | 진실의 원천이 하나여야 한다. 양쪽에 두면 Outline 에서 고친 내용과 로컬이 영구히 어긋난다 |
| **옛 이력은 버린다** | 이관 도구를 만들 만큼의 가치가 없다. 스키마 가드가 이미 안내 문구를 갖고 있다 |
| 문서는 **고정 컬렉션 하나에 평평하게** | 분류는 Outline 이 사람보다 잘하지 못하고, 앱이 부모 문서를 찾고 만드는 로직을 지면 실패 경로가 늘어난다 |
| frontmatter 를 **그대로 싣는다** | R3 이 확정한 형식이다. R5 가 문서를 다시 읽어 가공할 때 파싱할 자리가 필요하다. 사람이 읽을 링크는 본문 첫 블록이 맡는다 |
| 저장 흐름은 **이력 화면 한 곳**에 둔다 | 실행 현황의 레지스트리는 메모리라 재시작하면 빈다. 놓친 실행을 다시 만날 곳이 결국 이력이므로, 저장 UI 를 두 화면에 두는 것은 중복이다 |
| 앱은 Outline 을 **읽지 않는다** | 문서명·URL 을 로컬에 적어 두면 목록을 그리는 데 호출이 없다. Outline 이 죽어도 이력은 뜨고 저장 버튼만 실패한다 |
| 본문 편집과 마크다운 내려받기를 **없앤다** | 수정은 Outline 에 위임했다. 내려받기는 저장 후엔 대상이 없고 저장 전엔 위키에 올리는 길과 목적이 겹친다 |

---

## 4. 구조

```
pages/history.py       제목 확인 · 인용 포함 결정 · 저장 · 결과 표시
  ├── core/markdown_export.to_markdown()   본문 마크다운
  ├── services/outline.create_document()   documents.create 한 번
  └── services/run_history.mark_exported() 링크 기록 + 본문 삭제
```

경계는 이렇다.

- **`services/outline.py` 는 Outline 만 안다.** SQLite 도 Streamlit 도
  모른다.
- **`services/run_history.py` 는 Outline 을 모른다.** 문서 ID·제목·URL
  이라는 문자열 셋을 받을 뿐이다.
- 둘을 잇는 것은 화면이고, 화면이 아는 것은 "만들고 → 기록한다" 는
  순서뿐이다.

데이터 흐름.

```
요약 실행 끝 → SQLite 에 answers + run_metadata   (runner 변경 없음)
                        ↓
        이력에서 사람이 읽고 제목 확인 → 저장 버튼
                        ↓
   to_markdown() → outline.create_document() → 문서 ID·제목·URL
                        ↓
     runs 행에 링크 기록 + answers·run_metadata 행 삭제 (커밋 하나)
                        ↓
              그 실행은 목록에서 링크 한 줄이 된다
```

---

## 5. `services/outline.py` (신규)

### 5.1 설정

```python
URL_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_URL"
TOKEN_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_TOKEN"
COLLECTION_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_COLLECTION"


@dataclasses.dataclass(frozen=True, slots=True)
class OutlineConfig:
    """Outline 에 붙는 데 필요한 값 셋."""

    base_url: str
    token: str
    collection_id: str


def config_from_env() -> OutlineConfig | None:
    """환경변수에서 설정을 읽는다. 셋 다 있을 때만 설정으로 친다."""
```

이름은 `NOTEBOOKLM_ST_DB` 의 전례를 따른다.

**부분 설정은 설정이 아니다.** 하나라도 비면 `None` 을 돌려주고, 화면은
저장 버튼 대신 안내를 그린다. 토큰만 빠진 채로 호출해 401 을 맞는 것보다
처음부터 못 한다고 말하는 편이 진단하기 쉽다.

`base_url` 의 끝 슬래시는 여기서 한 번 떼어 둔다. 붙이고 떼는 일이 호출
지점마다 흩어지면 `//api/…` 같은 URL 이 언젠가 나온다.

### 5.2 인터페이스

```python
@dataclasses.dataclass(frozen=True, slots=True)
class SavedDocument:
    """Outline 에 만들어진 문서."""

    id: str
    title: str
    url: str    # 사람이 브라우저에 붙여 넣을 수 있는 절대 URL


class OutlineError(RuntimeError):
    """Outline 에 문서를 만들지 못했다.

    메시지는 사람이 화면에서 읽는 문장이다. 토큰은 절대 담지 않는다.
    """


def create_document(
    config: OutlineConfig,
    title: str,
    markdown: str,
    timeout: float = 20.0,
    poster: PostLike = httpx.post,
) -> SavedDocument:
    """컬렉션에 문서를 하나 만든다.

    Raises:
        OutlineError: 설정이 틀렸거나, 연결이 안 되거나, 응답이
            기대한 모양이 아닌 경우.
    """
```

`poster` 는 `video_metadata.fetch(runner=subprocess.run)` 와 같은 주입
구멍이다. 테스트가 가짜를 넣어 네트워크를 타지 않는다.

**실패를 예외로 던진다.** `video_metadata.fetch` 는 실패를 값으로
돌려주는데, 그것은 백그라운드 스레드에서 요약을 멈출 수 없기 때문이었다.
여기는 사람이 버튼을 누른 자리고, 실패하면 화면이 빨간 줄을 띄우고 끝나면
된다.

타임아웃 기본값 20초는 `video_metadata` 와 같은 값을 쓴다. 홈 LAN 안의
호출이라 넉넉하다.

### 5.3 호출

```python
# httpx.post(
#     f"{config.base_url}/api/documents.create",
#     headers={"Authorization": f"Bearer {config.token}"},
#     json={
#         "title": title,
#         "text": markdown,
#         "collectionId": config.collection_id,
#         "publish": True,
#     },
#     timeout=timeout,
# )
```

`publish` 를 켠다. 끄면 초안으로 남아 컬렉션에서 보이지 않는다.

응답에서 `data.id`·`data.title`·`data.url` 을 꺼낸다. `data.url` 이
`/doc/…` 로 시작하는 상대 경로면 앞에 `base_url` 을 붙이고, `http` 로
시작하면 그대로 쓴다(→ 13.1).

### 5.4 실패

상태 코드를 사람이 읽을 문장으로 옮긴다.

| 상황 | 메시지 |
|---|---|
| 401 · 403 | API 토큰이 거부되었습니다 |
| 404 | 컬렉션 ID 나 Outline 주소를 확인하세요 |
| 그 밖의 4xx · 5xx | Outline 이 오류를 냈습니다 (상태 코드 포함) |
| 타임아웃 · 연결 실패 | Outline 에 연결하지 못했습니다 |
| JSON 이 아니거나 `data` 가 없음 | 응답을 이해하지 못했습니다 |

**httpx 의 원문 예외를 그대로 흘리지 않는다.** 요청 정보가 따라 나올 수
있고, 무엇보다 사람이 읽고 고칠 수 있는 문장이 아니다. 같은 이유로 토큰은
메시지에도 로그에도 싣지 않는다.

---

## 6. 저장

### 6.1 `core/models.py`

`RunSummary` 에 네 칸을 더한다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class RunSummary:
    id: int
    url: str
    video_id: str
    title: str | None
    created_at: str
    answer_count: int
    outline_id: str | None = None
    outline_url: str | None = None
    outline_title: str | None = None
    exported_at: str | None = None
```

`SavedDocument` 는 여기가 아니라 `services/outline.py` 에 둔다. `core` 는
화면과 저장소가 함께 쓰는 값 객체의 자리이고, Outline 이라는 외부 개념을
알 이유가 없다.

### 6.2 `services/store.py`

```sql
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY,
    url           TEXT NOT NULL,
    video_id      TEXT NOT NULL,
    title         TEXT,
    created_at    TEXT NOT NULL,
    outline_id    TEXT,
    outline_url   TEXT,
    outline_title TEXT,
    exported_at   TEXT
);
```

`_EXPECTED_COLUMNS["runs"]` 에 네 이름을 더한다.

**별도 테이블로 빼지 않는다.** 실행 하나당 문서 하나라 1:1 이고,
`run_metadata` 를 따로 둔 이유("빈 행과 없는 행이 같은 뜻이 되면 안
된다")가 여기엔 없다. `exported_at IS NULL` 이 곧 "아직 안 올렸다" 이고
그 해석은 하나뿐이다.

**`outline_id` 를 함께 적는다.** 화면은 URL 만 쓰지만, R5 가 정리본을
만들며 저장된 문서를 다시 읽으려면 `documents.info` 에 넘길 ID 가 필요하다.
지금 한 칸 적어 두는 비용이 나중에 전부 다시 훑는 비용보다 싸다.

### 6.3 `services/run_history.py`

**더한다.**

```python
def mark_exported(
    connection: sqlite3.Connection,
    run_id: int,
    *,
    document_id: str,
    document_title: str,
    document_url: str,
) -> None:
    """문서 링크를 적고 로컬 본문을 지운다.

    Raises:
        ValueError: 그 ID 의 실행이 없는 경우.
    """
```

`runs` UPDATE + `answers` DELETE + `run_metadata` DELETE 를 **커밋
하나로** 묶는다. 중간에 죽어도 "본문은 사라졌는데 링크는 없는" 상태가
생기지 않는다. `exported_at` 은 `store.now()` 를 쓴다.

인자를 문자열로 받는다. `SavedDocument` 를 받으면 저장소가 Outline 을 알게
된다(→ 4).

**바꾼다.** `list_runs` 의 SELECT 에 네 컬럼을 더해 `RunSummary` 에
싣는다. 저장된 실행은 `answers` 가 비어 `answer_count` 가 0 이 되는데,
목록 라벨이 저장 여부로 갈리므로 오해될 자리가 없다(→ 8.1).

**지운다.** `update_answer`. 본문 편집을 Outline 에 위임했으므로 부르는
곳이 없어진다.

**그대로 둔다.** `delete_run`. 다만 저장된 실행을 지우면 **로컬의 링크만
사라지고 Outline 문서는 남는다.** 화면의 확인 문구를 그 사실에 맞게
고친다(→ 8.1).

---

## 7. `core/markdown_export.py`

### 7.1 시그니처

```python
def to_markdown(
    summary: models.RunSummary,
    items: Sequence[models.AnswerItem],
    title: str,
    metadata: models.VideoMetadata | None,
) -> str:
```

`title` 을 인자로 받는다. 사람이 저장 직전에 확인·수정한 제목이고, 같은
값이 Outline 문서 제목이 된다. 제목 계산을 함수 안에서 다시 하지 않는다 —
두 곳에서 따로 계산하면 어긋난다(R3 이 같은 이유로 `_frontmatter` 에
제목을 넘기게 해 두었다).

`to_filename()` 을 **지운다.** 내려받기가 사라지면 부르는 곳이 없다.
`MAX_STEM_CHARS`·`_FORBIDDEN`·`_REPEATED_SPACE`·`_sanitize` 도 함께
빠진다. `_CONTROL` 과 `_yaml_string` 은 frontmatter 가 계속 쓰므로 남는다.

### 7.2 본문 첫 블록

`# {title}` 머리글을 **뺀다.** Outline 이 문서 제목을 따로 갖고 있어
그대로 두면 제목이 두 번 보인다.

"출처 · 실행" 두 줄 블록은 **남긴다.**

```markdown
---
title: "AI 에이전트의 미래"
channel: "어떤 채널"
upload_date: 2026-09-20
url: https://www.youtube.com/watch?v=xxxxxxxxxxx
---

- 출처: https://www.youtube.com/watch?v=xxxxxxxxxxx
- 실행: 2026-09-22T14:03:00

## 첫 질문
...
```

URL 이 두 번 나온다. 중복이지만 **목적이 다르다.** frontmatter 는 R5 가
파싱할 자리이고, 아래 블록은 사람이 Outline 화면에서 클릭할 링크다.
frontmatter 안의 URL 은 구분선 사이 맨 텍스트로 렌더되어 클릭되지 않는다
(→ 2.5).

### 7.3 그대로 두는 것

frontmatter 의 키 집합(`title`·`channel`·`upload_date`·`url`), 값이 없는
키를 빼는 규칙, `url` 을 영상 ID 로 정규화하는 규칙, 이스케이프 규칙,
답변 블록의 모양은 R3 이 정한 그대로다.

---

## 8. 화면

### 8.1 `pages/history.py`

한 화면이 두 상태를 그린다. 고른 실행의 `exported_at` 으로 갈린다.

**목록 라벨** — 저장 여부가 한 줄에 보여야 한다.

```
청소년기의 뇌 발달 · 2026-09-22T14:03:00 · 미저장 · 답변 5건
AI 에이전트의 미래 · 2026-09-21T09:11:00 · 문서
```

미저장 항목은 지금처럼 영상 제목(없으면 영상 ID)을 쓰고, 저장된 항목은
`outline_title` 을 쓴다. 사람이 고친 제목이 위키에 있는 이름이므로,
저장 뒤에는 그쪽이 찾는 데 맞다. 자르기 규칙(`_shorten`)은 양쪽에 그대로
적용한다.

**저장된 실행을 고르면** 문서명, "Outline 에서 열기" 링크 버튼,
저장 시각만 보인다. 본문은 로컬에 없으니 그릴 것이 없다. 삭제는 남기되
문구를 바꾼다 — 지금의 "딸린 답변도 함께 사라집니다" 는 저장된 항목에
대해서는 거짓말이다. **"로컬 링크만 지웁니다. Outline 문서는 그대로
남습니다."**

**미저장 실행을 고르면** 위에서부터 이렇게 배치한다.

```
문서 제목  [ 청소년기의 뇌 발달                     ]
[x] 인용 포함
[ Outline 에 저장 ]

── 답변 카드들 (읽기 전용) ──
```

- 제목 입력의 기본값은 저장된 영상 제목, 비었으면 영상 ID. 위젯 키는
  실행마다 달라야 하므로 `f"history_title_{run.id}"` 를 쓴다
- 공백만 남으면 저장 버튼을 막는다. 제목 없는 문서를 위키에 만들 이유가
  없다
- "인용 포함" 은 지금의 "인용 숨기기" 를 뒤집은 것이다(기본 켬). 끄면
  `answer_text.for_display` 가 만든 걸러진 사본이 **화면과 저장 문서
  양쪽에** 쓰인다. 화면에 보이는 것이 곧 올라가는 것이라는 기존 원칙을
  그대로 지킨다

**저장 버튼의 순서.**

1. `st.spinner` 를 띄우고 `to_markdown()` 으로 본문을 만든다
2. `outline.create_document()` 를 부른다. `OutlineError` 면 `st.error` 로
   메시지를 띄우고 **로컬은 손대지 않는다.** 원인을 고친 뒤 같은 버튼을
   다시 누르면 된다
3. 성공하면 `mark_exported()` 로 링크를 적고 본문을 지운 뒤 `st.rerun()`.
   같은 항목이 링크 한 줄로 다시 그려진다

**설정이 없으면**(`config_from_env()` 가 `None`) 저장 버튼 자리에
안내를 띄운다. 이력 열람 자체는 막지 않는다.

**남은 실패 틈 하나.** 문서는 만들어졌는데 2 와 3 사이에서 로컬 기록이
실패하는 경우다. 되돌리려면 방금 만든 문서를 지워야 하는데 그 삭제도
실패할 수 있어 틈이 한 겹 더 생길 뿐이다. 그래서 **되돌리지 않고 사실대로
보여 준다.**

> 문서는 만들어졌습니다: `<URL>` — 로컬 기록에 실패했습니다. 다시
> 저장하면 문서가 둘이 됩니다.

사람이 링크를 들고 판단하면 된다. 개인용 도구에서 몇 년에 한 번 날까 말까
한 경로에 자동 보상 로직을 놓는 것은 값에 비해 비싸다.

**지운다.** 마크다운 내려받기 버튼과 `_render_download`, 답변 저장
콜백 `_save`.

### 8.2 `components/answer_view.py`

`on_save`·`SaveCallback` 과 편집 상자 분기를 지운다. `render_items` 는
읽기 전용 컴포넌트가 되고, `_render_answer` 는 `st.markdown` 한 줄로
줄어든다.

### 8.3 인증 게이트 — 전제가 바뀌지 않았다

R1 스펙 §7.3 은 "R4 에서 이력이 Outline 을 읽게 되면 이 전제가 바뀐다"
고 적어 두었다. **바뀌지 않는다.** 문서명과 URL 을 로컬에 적어 두므로
이력 목록을 그리는 데 Outline 호출이 없다. Outline 이 죽어도 이력은 뜨고
저장 버튼만 실패한다. R1 스펙의 그 문단을 정정한다.

---

## 9. 배포 설정

### 9.1 `docker-compose.yml`

지금 compose 에는 `environment:` 가 없고 "앱 환경변수는 이미지에 있으므로
여기서 다시 적지 않는다" 는 원칙이 적혀 있다. **여기서 처음 예외가
생긴다.** 토큰은 시크릿이라 이미지에 구울 수 없다. `PUID`/`PGID` 가 이미
쓰고 있는 길을 그대로 쓴다.

```yaml
    environment:
      # 이미지에 굽지 않는다 — 토큰은 시크릿이다. 값은 배포
      # 디렉터리의 compose 환경 파일에서 온다.
      NOTEBOOKLM_ST_OUTLINE_URL: "${NOTEBOOKLM_ST_OUTLINE_URL:-}"
      NOTEBOOKLM_ST_OUTLINE_TOKEN: "${NOTEBOOKLM_ST_OUTLINE_TOKEN:-}"
      NOTEBOOKLM_ST_OUTLINE_COLLECTION: "${NOTEBOOKLM_ST_OUTLINE_COLLECTION:-}"
```

빈 값이면 앱은 뜨되 저장 버튼 자리에 안내가 나온다. **기동을 막지
않는다** — 컨테이너가 안 뜨는 것보다 버튼 하나가 잠기는 편이 진단하기
쉽다. 그 환경 파일은 이미 gitignore·dockerignore 에 들어 있다.

### 9.2 API 키

Outline 웹의 **Settings → API Keys → New API Key** 에서 만든다.

- **scope 는 `documents.create` 하나로 충분하다.** 앱이 그 엔드포인트만
  부른다. 키가 새더라도 읽기·삭제·사용자 조회가 막힌다
- 컬렉션 ID(UUID)는 `collections.list` 를 한 번 불러 확인한다. 그때만
  scope 를 넓힌 임시 키가 필요하고, 확인이 끝나면 지운다
- 컬렉션 단위 격리가 정말 필요하면 그 컬렉션에만 접근 가능한 사용자를
  따로 만들어 그 사용자로 키를 발급해야 한다(→ 2.2). 1인용 홈서버에는
  과하다고 보고 채택하지 않는다

절차의 실물은 `docs/how-to/2026-09-16-homeserver-deploy.md` 에 "Outline
연결하기" 절로 넣는다.

---

## 10. `pyproject.toml`

```toml
dependencies = [
    "httpx>=0.28",
    "notebooklm-py==0.8.1",
    "streamlit>=1.63.0",
    "yt-dlp>=2026.8.19",
]
```

하한만 건다. 상한을 걸면 `notebooklm-py` 가 올릴 때 해석이 막힌다(→ 2.3).

---

## 11. 테스트

네트워크를 타지 않는다.

| 파일 | 무엇을 |
|---|---|
| `tests/services/test_outline.py` (신규) | 주입한 `poster` 가 진짜 `httpx.Response` 를 돌려준다. 성공 파싱, 상대·절대 URL 조립, 401·404·5xx·타임아웃이 각각 제 메시지의 `OutlineError` 가 되는지, 토큰이 예외 메시지에 안 새는지, `config_from_env` 의 부분 설정이 `None` 인지, 끝 슬래시가 붙은 주소로도 URL 이 바르게 만들어지는지 |
| `tests/services/test_run_history.py` | `mark_exported` 가 링크를 적고 `answers`·`run_metadata` 를 지우는지, 없는 ID 면 `ValueError` 인지, `list_runs` 가 저장 상태를 싣는지. `update_answer` 테스트 넷은 삭제 |
| `tests/pages/test_history.py` | 미저장·저장됨 두 상태의 렌더, 저장 버튼이 `create_document` 와 `mark_exported` 를 순서대로 부르는지, `OutlineError` 면 로컬이 그대로인지, `mark_exported` 가 실패하면 문서 URL 이 메시지에 실리는지, 설정이 없으면 버튼이 없는지, 제목이 공백이면 막히는지 |
| `tests/core/test_markdown_export.py` | 확인한 제목이 frontmatter 에 들어가는지, 본문에 `# 제목` 이 없는지, 출처 블록이 남는지. `to_filename` 테스트는 삭제 |
| `tests/test_components.py` | 편집 상자 관련 테스트 삭제 |
| `tests/services/test_store.py` | 새 컬럼이 빠진 DB 가 `StaleSchemaError` 를 내는지 |

기존 테스트가 쓰는 Streamlit 가짜 객체 방식을 그대로 따른다.

---

## 12. 건드리는 파일

**신규** — `src/notebooklm_st/services/outline.py`,
`tests/services/test_outline.py`

**수정** — `core/models.py`, `core/markdown_export.py`,
`services/store.py`, `services/run_history.py`,
`components/answer_view.py`, `pages/history.py`, `pyproject.toml`,
`docker-compose.yml`, 그리고 테스트 다섯.

**문서** — `README.md`(저장 흐름과 환경변수),
`docs/how-to/2026-09-16-homeserver-deploy.md`(Outline 연결하기 절,
기존 `questions.db` 를 지우는 한 줄),
`docs/superpowers/specs/2026-09-16-headless-auth-design.md` §7.3 정정.

**건드리지 않는다** — `services/nlm.py`, `services/runner.py`,
`services/runs.py`, `services/auth.py`, `services/video_metadata.py`,
`services/questions.py`, `core/answer_text.py`, `core/errors.py`,
`core/youtube.py`, `pages/ask.py`, `pages/dashboard.py`,
`pages/maintenance.py`, `pages/question_admin.py`, `Dockerfile`,
`.github/workflows/`.

---

## 13. 미검증 가정

1. **`documents.create` 응답의 `data.url` 이 상대 경로다.** `/doc/제목-
   슬러그` 형태로 본다. 절대 URL 로 오는 배포판이 있을 수 있어 `http` 로
   시작하면 그대로 쓰도록 양쪽을 받는다. 구현 단계에서 실물로 한 번
   확인한다.
2. **Outline 이 `text` 의 frontmatter 를 특별 취급하지 않는다.** 구분선과
   맨 텍스트로 렌더한다고 본다(→ 2.5). 만약 제목을 흡수하는 동작이 있다면
   문서 제목이 덮일 수 있다. 첫 문서를 올린 뒤 눈으로 확인한다.
3. **홈서버 컨테이너에서 Outline 으로 나가는 요청이 막히지 않는다.** 둘
   다 같은 홈 LAN 에 있으므로 무리한 가정은 아니지만 실측은 아니다.
   막히면 "연결하지 못했습니다" 로 수렴한다.

---

## 14. 범위 밖

- **정리본**(여러 요약본을 골라 가공) — R5
- **스케줄러 · 즐겨찾기 채널 자동 요약 · 알림** — R6
- **Outline 에서 문서를 다시 읽어오기** — R4 는 쓰기만 한다. R5 가
  필요해질 때 `documents.info` 로 연다
- **자동 저장 · 실패 재전송 큐** — 사람이 버튼으로 올리기로 했다
- **채널별 폴더 분류 · 태그** — 고정 컬렉션 하나에 평평하게 둔다
- **옛 이력 이관** — 버리기로 했다
- **본문 "개요" 의 "모름"** — R3 이 남긴 그대로. 질의 파이프라인을
  건드려야 한다
- **Outline 문서 삭제·수정을 앱에서** — 위키에 위임한 것이 이 릴리스의
  요점이다

---

## 15. R5 로 넘기는 것

| 것 | 상태 |
|---|---|
| `outline_id` | `runs` 에 적힌다. `documents.info` 로 문서를 다시 읽을 때 쓴다 |
| frontmatter 형식 | R3 이 정한 그대로 문서에 실린다. 정리본이 파싱할 자리다 |
| `services/outline.py` | 쓰기만 있다. 읽기(`documents.info`·`documents.list`)는 R5 가 더한다 |
| API 키 scope | `documents.create` 하나다. R5 가 읽기를 더하면 scope 도 넓혀야 한다 |
| 컬렉션 구조 | 평평하다. 정리본을 같은 컬렉션에 둘지 따로 둘지는 R5 가 정한다 |
