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

### 2.5 frontmatter 를 그대로 실으면 머리글 하나로 뭉친다

**실물로 확인했다.** R3 이 만든 YAML frontmatter 를 `text` 에 그대로
실었더니 네 줄이 통째로 **H2 머리글 하나**가 되었다.

```
## title: "…" channel: "어피티 UPPITY" upload_date: 2026-08-14 url: https://…
```

원인은 CommonMark 의 **setext 헤딩** 규칙이다. 텍스트 줄 바로 다음의
`---` 는 구분선이 아니라 "위 문단을 H2 로 만들라" 는 밑줄이다.

```
---            ← 구분선
title: "…"     ┐
channel: "…"   │ 문단
url: …         ┘
---            ← 이건 구분선이 아니라 H2 밑줄
```

YAML frontmatter 를 따로 알아보지 않는 렌더러에서는 피할 수 없다.
그래서 **메타데이터를 마크다운 리스트로 적는다**(→ 3, 7).

`markdown-it-py`(CommonMark)로 재현해 확인했고, 리스트 뒤에 빈 줄을
두고 놓은 `---` 는 앞이 문단이 아니라 리스트라서 setext 밑줄이 될 수
없고 온전한 구분선이 된다는 것도 같은 방법으로 확인했다.

---

## 3. 설계 결정

| 결정 | 근거 |
|---|---|
| 저장은 **사람이 버튼으로** 한다 | 위키는 오래 남는 자리다. 마음에 안 드는 결과가 자동으로 쌓이면 치우는 일이 사람에게 돌아온다 |
| 실행 결과의 첫 도착지는 **계속 SQLite** | 게이트가 사람이면 결과는 디스크에 있어야 한다. 메모리에 들고 있다가 재시작하면 몇 분 걸린 요약이 사라진다 |
| 저장에 성공하면 **본문을 지우고 링크만 남긴다** | 진실의 원천이 하나여야 한다. 양쪽에 두면 Outline 에서 고친 내용과 로컬이 영구히 어긋난다 |
| **옛 이력은 버린다** | 이관 도구를 만들 만큼의 가치가 없다. 스키마 가드가 이미 안내 문구를 갖고 있다 |
| 문서는 **고정 컬렉션 하나에 평평하게** | 분류는 Outline 이 사람보다 잘하지 못하고, 앱이 부모 문서를 찾고 만드는 로직을 지면 실패 경로가 늘어난다 |
| 메타데이터를 **마크다운 리스트로 적는다** | YAML frontmatter 는 Outline 에서 머리글 하나로 뭉친다(→ 2.5). 위키는 사람이 읽는 곳이므로 그 화면에서 읽히는 형식이 이긴다. R5 가 파싱할 자리는 리스트가 그대로 맡는다 |
| 메타데이터와 본문을 **구분선으로 가른다** | 리스트 바로 아래 답변 머리글이 붙으면 둘이 한 덩어리로 읽힌다. 리스트 뒤의 `---` 는 setext 밑줄이 될 수 없어 안전하다(→ 2.5) |
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
PUBLIC_URL_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_PUBLIC_URL"   # 선택


@dataclasses.dataclass(frozen=True, slots=True)
class OutlineConfig:
    """Outline 에 붙는 데 필요한 값들."""

    base_url: str      # 앱이 API 를 부를 주소
    public_url: str    # 사람이 브라우저로 열 주소
    token: str
    collection_id: str


def config_from_env() -> OutlineConfig | None:
    """환경변수에서 설정을 읽는다. 필수 셋이 다 있을 때만 설정으로 친다."""
```

이름은 `NOTEBOOKLM_ST_DB` 의 전례를 따른다.

**부분 설정은 설정이 아니다.** 필수 셋 중 하나라도 비면 `None` 을
돌려주고, 화면은 저장 버튼 대신 안내를 그린다. 토큰만 빠진 채로 호출해
401 을 맞는 것보다 처음부터 못 한다고 말하는 편이 진단하기 쉽다.

**공개 주소는 선택이다.** 비어 있으면 `base_url` 을 그대로 쓴다. 주소가
하나뿐인 흔한 구성에서는 설정이 늘지 않고, 화면의 안내 문구도 필수 셋만
나열한다.

#### 왜 주소가 둘인가

앱은 저장할 때 API 를 한 번 부르고, 문서 링크를 **문자열로 적어 둔다.**
나중에 그 링크를 여는 것은 브라우저이지 앱이 아니다. 둘이 같은 주소로
닿을 수 있으면 값 하나로 충분하다.

실제 배포에서 그렇지 않은 구성을 만났다. Outline 이 공인 도메인으로
서비스되는데 같은 호스트의 컨테이너가 그 도메인으로 되돌아 나가지
못했다(NAT 헤어핀, `ConnectionRefusedError`). 앱을 호스트 주소로
붙였더니 저장은 됐지만, 그 주소에는 사용자의 Outline 세션 쿠키가 없어
링크를 누르면 `auth.info` 가 401 을 냈다. **한 주소로는 두 조건을 동시에
만족할 수 없다.**

붙는 곳과 사람이 여는 곳은 원래 다른 개념이다. 도커 레지스트리나 S3
호환 스토리지가 내부 엔드포인트와 공개 엔드포인트를 따로 두는 것과 같다.

끝 슬래시는 **양쪽 다** 여기서 한 번 떼어 둔다. 붙이고 떼는 일이 호출
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

응답에서 `data.id`·`data.title`·`data.url` 을 꺼낸다. `data.url` 은
`/doc/…` 로 시작하는 **상대 경로다**(실측). 앞에 **`public_url`** 을
붙인다 — 이 값이 곧 사람이 나중에 누를 주소가 되므로 연결 주소가 아니라
공개 주소를 써야 한다(→ 5.1). `http` 로 시작하는 절대 URL 로 오는
배포판이 있을 수 있어 그때는 그대로 쓴다.

### 5.4 실패

메시지는 **"무엇부터 확인하라"** 를 말한다. 상태 코드만 남기는 것은
실패한 설계다 — 실제 배포에서 그 때문에 왕복을 세 번 했다.

| 상황 | 메시지 |
|---|---|
| 400 | 값을 받아들이지 않았습니다. **컬렉션 ID 가 UUID 인지** 확인하세요 — 이름은 받지 않습니다 |
| 401 | API 토큰을 받아들이지 않았습니다. 토큰이 맞는지·만료되지 않았는지 확인하세요 |
| 403 | 요청을 거부했습니다. **컬렉션 ID 를 먼저** 확인하세요 — 없는 컬렉션도 이 오류로 옵니다. 그다음 scope |
| 404 | 대상을 찾지 못했습니다. **주소**를 확인하세요 |
| 그 밖의 4xx · 5xx | Outline 이 오류를 냈습니다 (상태 코드 포함) |
| 타임아웃 · 연결 실패 · 주소가 URL 이 아님 | Outline 에 연결하지 못했습니다 |
| JSON 이 아니거나 `data` 가 없음 | 응답을 이해하지 못했습니다 |

#### 안내 순서가 왜 저런가 — 실측

- **없는 컬렉션 ID 는 404 가 아니라 403 으로 온다.** Outline 이
  `authorization_error` 로 "없다" 와 "권한 없다" 를 뭉쳐 돌려준다.
  존재 여부를 흘리지 않으려는 설계다. 그래서 403 에서 토큰을 먼저
  의심하게 하면 **멀쩡한 토큰을 파게 된다.** 실제로 그렇게 됐다.
- **컬렉션 이름을 UUID 자리에 넣으면 400 이다.** 검증 단계에서
  튕기므로 응답이 수십 밀리초 만에 온다.
- **404 는 이 엔드포인트에서 컬렉션 때문에 나오지 않는다.** 주소가
  틀렸을 때의 것이다.

#### Outline 이 보낸 설명을 함께 싣는다

우리가 지은 안내 뒤에 응답 본문의 `message`(없으면 `error`)를 한 줄로
접어 붙인다. 서버가 무엇이 틀렸는지 정확히 말해 줬는데 그것을 버리면
사람이 추측으로 파게 된다.

**토큰은 헤더에 있지 응답 본문에 없다.** 설계 초안이 "토큰이 샐까 봐"
본문을 통째로 버렸는데, 그 판단이 과했다. 다만 서버가 무엇을 돌려주든
화면에 무엇이 실리는지는 우리가 통제해야 하므로, 토큰이 본문에 섞여
있으면 설명째 버린다(`_detail`). 길이는 `DETAIL_LIMIT` 로 자른다 —
길면 정작 우리 안내가 밀려 안 읽힌다.

**httpx 의 원문 예외는 여전히 그대로 흘리지 않는다.** 요청 정보가 따라
나올 수 있고, 사람이 읽고 고칠 수 있는 문장이 아니다.

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
두 곳에서 따로 계산하면 어긋난다.

`to_filename()` 을 **지운다.** 내려받기가 사라지면 부르는 곳이 없다.
`MAX_STEM_CHARS`·`_FORBIDDEN`·`_REPEATED_SPACE`·`_sanitize` 도 함께
빠진다.

### 7.2 문서의 모양

```markdown
- 제목: '매수' 의견 믿으면 안 되는 이유 | 주식 초보를 위한 리포트 읽는 법
- 채널: 어피티 UPPITY
- 업로드 일자: 2026-08-14
- 영상 URL: https://www.youtube.com/watch?v=j2R_dgayplU

---

## 첫 질문

답변 본문…

### 인용 1건

- **[1]** 근거 구절
```

정한 것은 넷이다.

- **`# {title}` 머리글을 뺀다.** Outline 이 문서 제목을 따로 갖고 있어
  그대로 두면 제목이 두 번 보인다.
- **메타데이터는 한국어 라벨 리스트**다. 라벨은 `제목`·`채널`·
  `업로드 일자`·`영상 URL`. 값에 따옴표를 두르지 않는다 — YAML 이
  아니므로 따옴표가 문법적으로 할 일이 없고, 읽는 데 방해만 된다.
- **메타데이터와 본문 사이에 구분선을 둔다.** 앞이 리스트이고 빈 줄이
  끼어 있어 setext 밑줄이 되지 않는다(→ 2.5).
- **"출처 · 실행" 블록을 두지 않는다.** URL 은 리스트에 이미 있고,
  실행 시각은 Outline 이 문서 생성 시각으로 기록한다. 같은 것을 두 번
  적을 이유가 없다.

### 7.3 값 다듬기

`_one_line()` 이 제어문자를 지우고 남은 공백류를 공백 하나로 접는다.

제어문자를 지우는 이유는 R3 과 같다 — 영상 제목은 제3자 문자열이라
DEL·C1 이 섞여 들어올 수 있다. 공백류를 접는 이유는 새로 생겼다:
개행이 값에 남으면 **리스트 항목이 두 동강 나고 뒤쪽 줄이 리스트 밖의
문단이 된다.**

`url` 을 영상 ID 로 정규화하는 규칙과 값이 없는 항목을 줄째 빼는 규칙은
R3 이 정한 그대로다. 마크다운 메타문자(`*`·`` ` ``)는 이스케이프하지
않는다 — 제목에 섞이면 서식으로 렌더되지만 개인용 도구에서 그 값은
이스케이프 로직의 값어치에 못 미친다.

### 7.4 질문 원문을 싣지 않는다

답변 블록은 질문 제목(`## …`)과 답변 본문, 인용만 담는다. 질문 원문을
인용 블록으로 붙이던 것(`_quote`)을 지운다.

위키에 남길 것은 **답변**이지 무엇을 물었는지의 기록이 아니다. 원문은
이력 화면의 접은 영역에 그대로 남으므로 잃는 것도 없다.

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
      # 선택. 링크에 적을 주소가 붙는 주소와 다를 때만 채운다(→ 5.1).
      NOTEBOOKLM_ST_OUTLINE_PUBLIC_URL: "${NOTEBOOKLM_ST_OUTLINE_PUBLIC_URL:-}"
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
| `tests/core/test_markdown_export.py` | 확인한 제목이 메타데이터 리스트에 들어가는지, 본문에 `# 제목` 이 없는지, 리스트와 본문 사이에 구분선이 있는지, 질문 원문과 출처 블록이 **없는지**, 값 없는 항목이 줄째 빠지는지, 제어문자가 지워지고 개행이 공백으로 접히는지. `to_filename` 테스트는 삭제 |
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

남아 있는 것이 없다. 셋 다 실물로 확인했다.

**해소된 가정.**

- **`documents.create` 응답의 `data.url`** — **상대 경로가 맞다.**
  `/doc/제목-슬러그` 형태로 온다. 그래서 앞에 붙이는 주소가 곧 사람이
  누를 주소가 되고, 그 사실이 공개 주소를 따로 두게 만들었다(→ 5.1).
  절대 URL 로 오는 배포판을 위한 분기는 대비로 남겨 둔다.
- **Outline 의 frontmatter 렌더** — 틀렸다. "구분선과 맨 텍스트" 로
  볼 것이라 예측했으나 실물은 **H2 머리글 하나**였다. setext 헤딩
  규칙 때문이다. 메타데이터를 리스트로 바꿔 해소했다(→ 2.5, 7.2).
- **홈서버 컨테이너에서 Outline 으로 나가는 요청** — 막히지 않는다.
  다만 컨테이너에서 **공인 도메인으로 되돌아 나가는 경로**(NAT
  헤어핀)는 막혔다. 호스트 주소로 붙고 링크에는 공개 주소를 적어
  해소했다. 배포 문서가 이 함정을 다룬다.

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
| 메타데이터 형식 | `- 제목:`·`- 채널:`·`- 업로드 일자:`·`- 영상 URL:` 리스트다. 정리본이 되읽을 때 파싱할 자리이며, R3 의 YAML frontmatter 가 아니다(→ 2.5) |
| `services/outline.py` | 쓰기만 있다. 읽기(`documents.info`·`documents.list`)는 R5 가 더한다 |
| API 키 scope | `documents.create` 하나다. R5 가 읽기를 더하면 scope 도 넓혀야 한다 |
| 컬렉션 구조 | 평평하다. 정리본을 같은 컬렉션에 둘지 따로 둘지는 R5 가 정한다 |
