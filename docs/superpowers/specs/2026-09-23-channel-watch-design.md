# 채널 구독 설계 — 새 영상을 찾아 요약으로 잇기

- **작성일**: 2026-09-23
- **상태**: 설계 (구현 계획 수립 전)
- **대상**: `core/new_videos.py`(신규), `services/channels.py`(신규),
  `services/channel_feed.py`(신규),
  `services/channel_lookup.py`(신규), `pages/channels.py`(신규),
  `core/models.py`, `core/youtube.py`, `core/markdown_export.py`,
  `services/store.py`, `services/run_history.py`, `app.py`.
  실행 모델(`services/runner.py`·`services/runs.py`), NotebookLM
  (`services/nlm.py`), Outline(`services/outline.py`), 정리본
  (`services/digest*.py`·`core/digest*.py`), 인증
  (`services/auth.py`), 질문 저장소(`services/questions.py`)는
  건드리지 않는다.
- **범위**: 릴리스 R6a. 기획 문서
  `docs/requests/2026-09-16-summary-pipeline-v2.md` 의 **요구 5** 중
  **구독과 감지**. 주기 실행과 무인 요약은 R6b 로 미룬다(→ 16).
  선행 조건 R1~R5 는 완료되었다.

---

## 1. 왜 만드는가

기획 요구 5 는 "즐겨찾기 채널의 새 영상을 주기적으로 확인해 요약본을
자동 생성" 이다. 그 문장에는 두 가지가 겹쳐 있다 — **무엇을 요약할지
찾는 일**과 **사람 없이 돌리는 일**이다.

둘의 위험이 다르다. 찾는 일은 새 테이블 하나와 조회 경로 하나로
끝나고 기존 실행 경로를 건드리지 않는다. 사람 없이 돌리는 일은
프로세스 구조·크로스 프로세스 잠금·무인 인증 실패 정책·사람 승인
게이트 제거까지 함께 결정해야 한다. R1~R5 가 의존하는 실행 모델의
심장이 거기 있다.

R6a 는 **찾는 일만** 한다. 즐겨찾기 채널을 등록해 두고, 버튼을 눌러
"아직 요약하지 않은 새 영상" 목록을 받고, 거기서 바로 요약을
시작한다. 지금은 사람이 유튜브를 뒤져 URL 을 복사해 오는 일을 이
화면이 대신한다.

### 1.1 무엇을 하지 않는가

- **주기 실행을 하지 않는다.** 사람이 버튼을 누를 때만 확인한다
  (→ 2.5, 16).
- **여러 건을 한 번에 돌리지 않는다.** 지금의 "한 번에 하나" 가드를
  그대로 쓴다. 대기열은 R6b 가 필요해질 때 만든다(→ 3).
- **신규 영상을 로컬에 저장하지 않는다.** 조회 결과는 세션에만 있다
  (→ 10.3).
- **채널별 질문 세트를 두지 않는다.** 무인 실행이 생길 때
  `channel_questions` **새 테이블**로 붙이면 되고, 새 테이블은 DB
  삭제를 부르지 않는다(→ 2.3).
- **영상을 시청·다운로드하지 않는다.** 메타데이터만 읽는다.

---

## 2. 조사로 확인한 사실

### 2.1 채널 목록에는 업로드 시각이 없다

`yt-dlp --flat-playlist -J` 로 채널을 읽어 실물로 확인했다.

```
entries[].id          wGA27zJEnaU
entries[].title       Keira Riff reacts to her Watch History
entries[].duration    387
entries[].view_count  2200000
entries[].timestamp   None        ← 업로드 시각이 오지 않는다
```

**`timestamp` 가 `None` 이다.** 그래서 flat 목록만으로는 "등록 이후
업로드" 를 판정할 수 없다. 항목당 다시 조회하면 영상 하나에 수 초가
더 들어 채널 하나 확인에 분이 걸린다.

### 2.2 채널 RSS 피드에는 있다

`https://www.youtube.com/feeds/videos.xml?channel_id=<UC…>` 를 실물로
확인했다.

| 채널 | 상태 | 항목 | 본문 |
| --- | --- | --- | --- |
| Google for Developers | 200 | 15 | 24 KB |
| Fireship | 200 | 15 | 22 KB |
| YouTube 공식 | 첫 조회 500, 다시 조회 404 | — | — |

항목마다 `yt:videoId`, `atom:title`, `atom:published` 가 온다.
`published` 는 `2026-09-22T23:00:10+00:00` 꼴의 **타임존이 붙은 UTC**
다. 판정에 필요한 것이 다 있고, 비용은 HTTP 한 번이다.

두 가지를 함께 배웠다.

- **피드가 없는 채널이 실제로 있다.** 공식 @YouTube 채널이 404 다.
  그래서 피드 확인을 **등록 시점**으로 당긴다(→ 3).
- **같은 URL 이 5xx 를 냈다가 404 를 냈다.** 위 표의 마지막 줄은 한
  번의 실수가 아니라 두 번의 조회다. 5xx 는 일시적일 수 있으므로
  404 와 **다른 문구**로 다뤄야 한다. 멀쩡한 채널을 일시적 오류로
  거부하고 사람이 원인을 모르면 안 된다(→ 7.1).
- **피드는 최신 15건까지다.** 그보다 많이 밀리면 오래된 신규는
  목록에서 빠진다(→ 14).

### 2.3 새 테이블은 DB 를 지우지 않아도 된다

`services/store.py` 는 마이그레이션을 두지 않고, `connect()` 가
`_EXPECTED_COLUMNS` 와 실제 컬럼을 견줘 빠진 컬럼이 있으면 실패한다.
**이 검사는 테이블마다 "기대하는 컬럼이 있는지" 만 본다.**

새 테이블은 `CREATE TABLE IF NOT EXISTS` 가 만들어 주므로 검사를
그대로 통과한다. 기존 테이블에 **컬럼**을 더할 때만 DB 삭제가
강제된다. 그래서 `channels` 는 안전하고, 나중에 붙일
`channel_questions` 도 안전하다.

### 2.4 채널 URL 해석은 한 번이면 된다

`yt-dlp --flat-playlist -J --playlist-end 1 https://www.youtube.com/@Fireship`
로 확인했다. `/videos` 를 붙이지 않은 핸들 URL 로도 최상위에
`channel_id`(`UCsBjURrPoezykLs9EqgamOA`)·`channel`(`Fireship`)·
`channel_url` 이 온다. 항목은 1건만 받아 조회를 가볍게 한다.

등록할 때 한 번 해석해 `channel_id` 를 저장해 두면, 그 뒤로는 피드만
읽으면 된다.

### 2.5 Streamlit 스크립트는 세션이 있어야 돈다

컨테이너는 `streamlit run` 한 프로세스다. Streamlit 은 브라우저
세션이 붙을 때 스크립트를 돌리고, 헬스체크(`/_stcore/health`)는
스크립트를 실행하지 않는다.

따라서 `@st.cache_resource` 로 스케줄러 스레드를 띄우는 안은
**아무도 페이지를 열지 않는 동안 돌지 않는다.** 주기 실행은 별도
프로세스나 외부 cron 을 요구하며, 그것이 R6b 를 따로 떼어 낸 이유다
(→ 16).

### 2.6 자격증명은 쿠키 파일 하나다

질의와 정리는 같은 쿠키로 NotebookLM 에 붙으므로 서로를 막는다
(R5 §2.5). 그 가드는 프로세스 안의 메모리 레지스트리다. R6a 는
같은 프로세스 안에서 같은 러너를 부르므로 그 가드가 그대로 듣는다.
프로세스가 둘이 되는 순간 듣지 않으며, 그 문제도 R6b 의 것이다.

---

## 3. 설계 결정

| 결정 | 이유 |
| --- | --- |
| 감지 소스는 **채널 RSS 피드** | 업로드 시각이 오는 유일한 싼 경로다. HTTP 한 번이라 R6b 가 주기로 돌려도 부담이 없다(→ 2.1, 2.2) |
| 채널 해석은 **등록 시 yt-dlp 한 번** | 핸들·채널 URL 을 `channel_id` 로 바꾸는 일은 등록할 때 한 번이면 된다. 매 확인마다 yt-dlp 를 부를 이유가 없다(→ 2.4) |
| 피드 확인을 **등록 시점에 당긴다** | 피드 없는 채널이 실재한다. 등록을 통과한 채널은 확인이 도는 채널이다(→ 2.2) |
| 신규는 **기준일 이후 업로드 + 아직 요약 안 한 것** | 등록 즉시 과거 영상이 쏟아지지 않고, 이번에 건너뛴 영상도 요약할 때까지 목록에 남는다. "마지막 확인 시점" 커서는 갱신 시점이 애매하고 건너뛴 영상을 영영 감춘다 |
| 기준일은 **새 테이블의 컬럼** | `channels` 자체가 새 테이블이라 DB 삭제가 없다(→ 2.3) |
| 실행은 **한 건씩, 기존 러너 그대로** | `runner.start_run` 과 "한 번에 하나" 가드를 그대로 쓴다. R1~R5 가 기대는 실행 모델을 건드리지 않는다 |
| 질문은 **목록 위에서 한 번** 고른다 | 영상마다 고르면 클릭이 배로 는다. 질의 화면과 같은 질문 목록을 쓴다 |
| 조회 결과는 **세션에만** | 신규 영상은 언제든 다시 계산할 수 있는 파생물이다. 저장하면 무효화 시점을 관리해야 한다(정리본 초안과 같은 원칙) |
| 확인 중 한 채널이 실패해도 **계속한다** | 부분 목록임이 화면에 드러나고 실패한 채널이 사유와 함께 남는다. 정리본이 멈추는 이유(부분 결과가 완전해 보인다)가 여기엔 없다 |

### 3.1 기각한 안

- **yt-dlp 로 채널을 매번 훑기** — flat 목록에 업로드 시각이 없어
  항목마다 다시 조회해야 한다. 채널 하나 확인에 분이 걸리고, R6b 가
  주기로 돌리면 그 비용이 매번 든다.
- **YouTube Data API** — 할당량 관리와 API 키가 늘고, 이 프로젝트가
  지금까지 피해 온 외부 계정 의존이 하나 생긴다. 피드로 되는 일이다.
- **"마지막 확인 시점" 커서** — 목록은 가장 깔끔하지만, 커서를 언제
  올릴지(목록을 본 순간? 요약한 순간?)가 애매하고 그때 건너뛴 영상이
  영영 보이지 않는다.
- **신규 영상 테이블** — 조회 결과를 DB 에 쌓으면 언제 지울지,
  채널을 지울 때 함께 지울지, 이미 요약한 것을 어떻게 걷어낼지가
  전부 관리 대상이 된다. 파생물은 계산하면 된다.
- **여러 건 대기열을 R6a 에 넣기** — R6b 의 무인 큐와 같은 물건이라
  지금 만들면 R6b 가 가벼워지지만, 실행 모델(`RunRegistry`·가드)을
  건드려야 한다. 그 자리는 R1~R5 가 모두 기대고 있는 심장이고,
  무인 실행의 요구가 확정되기 전에는 무엇을 만들어야 할지도 정확히
  모른다.
- **스케줄러 스레드를 Streamlit 안에** — 세션이 없으면 돌지 않는다
  (→ 2.5).

---

## 4. 구조

```
pages/channels.py
    │  채널 등록 · 새 영상 확인 · 질문 선택 · 요약 시작
    ├──► services/channel_lookup.py   URL → channel_id (등록 시 1회, yt-dlp)
    ├──► services/channels.py         구독 CRUD (SQLite)
    ├──► services/channel_feed.py     피드 읽기 (httpx, 확인마다 채널당 1회)
    ├──► services/run_history.py      list_video_ids (이미 요약한 것)
    ├──► core/new_videos.py           신규 판정(순수 함수)
    ├──► services/questions.py        list_questions (읽기만)
    └──► services/runner.py           start_run (R1 그대로)
```

`core/new_videos.py` 는 **아무 I/O 도 모른다.** 피드에서 온 값
객체와 기준일과 이미 요약한 ID 집합을 받아 거르고 정렬할 뿐이다.
네트워크를 세우지 않고 경계 조건을 테스트할 수 있다.

---

## 5. `core/models.py` — 값 객체 둘

```python
@dataclasses.dataclass(frozen=True, slots=True)
class Channel:
    """구독 중인 채널 하나."""

    id: int
    channel_id: str
    """``UC`` 로 시작하는 YouTube 채널 ID."""
    title: str
    url: str
    baseline: str
    """``YYYY-MM-DD``. 이 날짜 이후 업로드만 신규로 본다."""
    created_at: str


@dataclasses.dataclass(frozen=True, slots=True)
class FeedEntry:
    """채널 피드의 항목 하나."""

    video_id: str
    title: str
    published: datetime.datetime
    """타임존이 붙은 시각. 피드가 UTC 로 준다."""
```

`services/channel_feed` 가 만들고 `core/new_videos` 가 거른다.
`VideoMetadata` 가 `services/video_metadata` 에서 만들어져 여러
모듈에 쓰이는 것과 같은 자리다 — `core/` 가 `services/` 를 import
하지 않기 위해 값 객체는 `models` 에 둔다.

---

## 6. `services/channel_lookup.py` — 등록 시 한 번

```python
@dataclasses.dataclass(frozen=True, slots=True)
class LookupResult:
    """채널 해석 결과. ``error`` 가 있으면 나머지는 비어 있다."""

    channel_id: str | None
    title: str | None
    url: str | None
    error: str | None


LOOKUP_TIMEOUT = 30.0

def lookup(
    url: str,
    runner: RunnerLike = subprocess.run,
    timeout: float = LOOKUP_TIMEOUT,
) -> LookupResult
```

`services/video_metadata.py` 와 같은 모양이다.

- 자식 프로세스로 `sys.executable -m yt_dlp --flat-playlist -J
  --playlist-end 1 <url>` 을 부른다. **`uv` 로 부르지 않는다** —
  PATH 에 없을 수 있고, 앱은 이미 yt-dlp 가 있는 인터프리터 안에서
  돈다(`auth.py`·`video_metadata.py` 와 같은 근거).
- `--playlist-end 1` 로 항목을 1건만 받는다. 쓰는 것은 최상위
  `channel_id`·`channel`·`channel_url` 뿐이다(→ 2.4).
- **실패를 예외가 아니라 값으로 돌려준다.** 타임아웃, yt-dlp 실행
  불가, 0 이 아닌 종료 코드, 해석 불가 JSON, `channel_id` 없음을
  각각 사람이 읽을 사유로 만든다.
- `channel_id` 가 없으면(영상 URL·재생목록 URL 등) "채널 URL 이
  아닙니다" 로 돌려준다.

타임아웃이 `video_metadata.FETCH_TIMEOUT`(20초)보다 길다. 채널
페이지 해석이 영상 하나보다 무겁고, 등록은 사람이 기다리는
한 번뿐이다.

---

## 7. `services/channel_feed.py` — 확인마다 한 번

```python
FEED_URL = "https://www.youtube.com/feeds/videos.xml"
FETCH_TIMEOUT = 20.0
MAX_FEED_BYTES = 1 << 20

@dataclasses.dataclass(frozen=True, slots=True)
class FeedResult:
    """피드 조회 결과. ``error`` 가 있으면 ``entries`` 는 비어 있다."""

    entries: tuple[models.FeedEntry, ...]
    error: str | None


def fetch(
    channel_id: str,
    getter: GetLike = httpx.get,
    timeout: float = FETCH_TIMEOUT,
) -> FeedResult
```

`services/outline.py` 가 `poster` 를 뚫어 둔 것과 같은 방식으로
`getter` 를 뚫는다. 테스트가 가짜 응답을 넣는다.

### 7.1 호출과 판정

```python
# httpx.get(
#     FEED_URL,
#     params={"channel_id": channel_id},
#     timeout=timeout,
#     follow_redirects=True,
# )
```

| 상태 | 사유 문구가 짚는 것 |
| --- | --- |
| 200 | 파싱으로 넘어간다 |
| 404 | 이 채널에는 피드가 없다. 등록할 수 없는 채널이다 |
| 5xx | **잠시 뒤 다시 시도하라.** 일시적일 수 있다(→ 2.2) |
| 그 외 | `YouTube 가 오류를 냈습니다(HTTP …)` |

404 와 5xx 를 가르는 것이 이 표의 요점이다. 둘을 한 문구로 묶으면
사람이 "이 채널은 안 되는구나" 와 "이따 다시 해 보자" 를 구분하지
못한다. 실측에서 같은 URL 이 두 답을 다 냈다.

### 7.2 파싱

`xml.etree.ElementTree` 로 읽는다. 네임스페이스는
`atom`(`http://www.w3.org/2005/Atom`) 과
`yt`(`http://www.youtube.com/xml/schemas/2015`) 둘이다.

항목마다 `yt:videoId`·`atom:title`·`atom:published` 를 읽고, 셋 중
하나라도 없는 항목은 **조용히 건너뛴다.** 피드 하나의 흠집이 채널
전체를 실패로 만들 이유가 없다.

`published` 는 `datetime.datetime.fromisoformat` 으로 읽는다. 값에
타임존이 붙어 있으므로 결과는 aware 다. 타임존이 없는 값이 오면 그
항목을 건너뛴다 — naive 와 aware 를 섞어 비교하면 `TypeError` 가
난다.

**응답 크기에 상한을 둔다.** `MAX_FEED_BYTES` 를 넘으면 파싱하지
않고 사유를 돌려준다. `ElementTree` 는 엔티티 확장 공격("billion
laughs")에 취약하고, 우리는 제3자가 주는 XML 을 읽는다. 실측한
피드가 24 KB 이므로 1 MiB 는 넉넉하다.

항목이 하나도 없는 피드는 **성공**이다(`entries=()`, `error=None`).
아직 영상을 올리지 않은 채널도 등록할 수 있어야 한다.

---

## 8. `core/new_videos.py` — 신규 판정

```python
def select(
    entries: Sequence[models.FeedEntry],
    baseline: str,
    known_ids: Container[str],
    tz: datetime.tzinfo | None = None,
) -> tuple[models.FeedEntry, ...]
```

1. `baseline`(`YYYY-MM-DD`)의 **00:00 을 `tz` 로 읽어** aware
   datetime 으로 만든다. `tz` 가 `None` 이면 시스템 로컬을 쓴다 —
   컨테이너는 `TZ=Asia/Seoul` 로 돈다.
2. `entry.published >= 기준시각` 이고 `entry.video_id not in
   known_ids` 인 항목만 남긴다.
3. `published` 내림차순으로 정렬해 돌려준다.

**타임존을 명시하는 것이 이 함수의 요점이다.** 피드는 UTC 로 주고
사람은 KST 날짜로 생각한다. 그냥 문자열을 자르거나 naive 로 비교하면
9시간 차이만큼 경계가 밀려, 한국 시각 오전에 올라온 영상이 하루
일찍/늦게 잡힌다.

경계는 **기준일 당일을 포함**한다(`>=`). 오늘 등록하고 오늘 올라온
영상은 신규다.

---

## 9. `services/channels.py` — 구독 저장소

`services/questions.py` 와 같은 모양이다. 연결과 스키마는 `store` 가
맡는다.

```python
def list_channels(connection) -> list[models.Channel]
def add_channel(connection, channel_id, title, url, baseline) -> models.Channel
def update_baseline(connection, channel_pk: int, baseline: str) -> None
def delete_channel(connection, channel_pk: int) -> None
```

- 목록 순서는 `title` 오름차순이다. 채널은 등록 순서보다 이름으로
  찾는다.
- 빈 값·공백뿐인 값은 `ValueError` 로 막는다(`questions` 와 같은
  계약).
- `baseline` 형식(`YYYY-MM-DD`)을 검사한다. 저장소가 형식을 지키면
  `new_videos.select` 가 형식을 다시 의심하지 않아도 된다.
- 같은 `channel_id` 를 다시 넣으면 `ValueError` 로 "이미 등록된
  채널입니다" 를 올린다. DB 의 `UNIQUE` 가 마지막 방어선이고,
  화면에 보여 줄 문장은 여기서 만든다.
- 삭제는 없으면 조용히 넘어간다(`delete_question` 과 같다).

### 9.1 스키마

`services/store.py` 의 `_SCHEMA` 에 더한다.

```sql
CREATE TABLE IF NOT EXISTS channels (
    id         INTEGER PRIMARY KEY,
    channel_id TEXT NOT NULL UNIQUE,
    title      TEXT NOT NULL,
    url        TEXT NOT NULL,
    baseline   TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

`_EXPECTED_COLUMNS` 에 같은 컬럼 집합을 적는다. **기존
`questions.db` 를 지울 필요가 없다**(→ 2.3).

### 9.2 `run_history.list_video_ids`

```python
def list_video_ids(connection: sqlite3.Connection) -> set[str]
```

`SELECT DISTINCT video_id FROM runs WHERE video_id <> ''` 를 집합으로
돌려준다. 테이블은 바뀌지 않고 조회 함수 하나가 는다.

빈 문자열을 거르는 이유는 옛 이력이다. `RunSummary.video_id` 는
`youtube.extract_video_id(url) or ""` 로 채워지므로 ID 를 못 뽑은
실행은 빈 문자열을 가진다. 그것이 집합에 섞이면 ID 가 빈 피드
항목과 엉뚱하게 맞부딪힌다.

---

## 10. 화면 — `pages/channels.py`

네비게이션에서 **질의 다음** 자리에 둔다(`app.py`). 둘 다 요약을
시작하는 화면이다.

```
채널
├ 채널 등록       URL 입력 · 기준일(기본 오늘) · [등록]
├ [새 영상 확인]   등록된 채널을 차례로 조회
├ 질문 선택        multiselect — 질의 화면과 같은 목록, 한 번만 고른다
├ 신규 영상        채널별 묶음 · 제목 · 업로드일 · 링크 · [요약]
└ 등록된 채널      expander: 링크 · 기준일 수정 · [삭제]
```

### 10.1 등록

1. `channel_lookup.lookup(url)` — 실패하면 사유를 그대로 보여 주고
   멈춘다.
2. `channel_feed.fetch(channel_id)` — 실패하면 등록하지 않는다.
   피드 없는 채널을 등록해 두면 확인할 때마다 실패한다(→ 2.2).
3. `channels.add_channel(...)` — 중복이면 그 문구를 보여 준다.

해석과 피드 확인은 둘 다 네트워크라 `st.spinner` 로 감싼다.

기준일 기본값은 **오늘(로컬)** 이다. 과거로 당길 수 있지만 피드가
최신 15건까지만 주므로 그보다 거슬러 올라가지는 못한다 — 도움말에
적는다.

### 10.2 확인

등록된 채널을 **순서대로** 조회한다. 채널당 HTTP 한 번이고 수백
ms 다.

한 채널이 실패해도 나머지를 계속하고, 실패한 채널은 그 자리에 사유를
적는다(→ 3). 결과는 `(채널, 신규 목록 또는 사유)` 의 목록이다.

### 10.3 신규 목록과 실행

- 조회 결과는 **세션에만** 둔다. 화면을 떠났다 오면 다시 확인한다.
- 질문은 목록 위에서 한 번 고른다. 등록된 질문이 없으면 안내만 내고
  `[요약]` 을 그리지 않는다(정리본 화면과 같은 패턴).
- `[요약]` 은 `runner.start_run(registry, url, questions,
  store.default_db_path())` 를 부른다. 질의 화면과 **같은 함수**다.
- 다음 셋 중 하나라도 참이면 `[요약]` 이 잠기고 이유가 보인다 —
  질의 실행 중(`running_count() > 0`), 정리 실행 중, 질문 미선택.
- 시작한 영상은 그 줄에 "실행 중" 을 적고 그 줄의 버튼만 잠근다.
  실행이 끝나야 `runs` 에 들어가므로 목록에서 즉시 사라지지 않으며,
  이 표시가 같은 영상을 두 번 시작하는 것도 막는다. 세션에 이번에
  시작한 `video_id` 집합을 둔다.
- 진행 상황과 결과는 **실행 현황 화면**에서 본다. 이 화면은 시작만
  한다.

### 10.4 목록과 삭제

채널마다 `expander` 로 접어 둔다(질문 관리와 같은 모양). 안에서
기준일을 고치고 삭제한다. 삭제해도 이미 만든 요약본과 이력은 그대로
남는다.

기준일을 고쳐도 **화면에 떠 있는 신규 목록은 바뀌지 않는다.** 목록은
확인을 누른 시점의 결과이고 세션에만 있다(→ 10.3). 새 기준일로 보려면
확인을 다시 누른다. 기준일 입력 옆에 그 사실을 한 줄로 적는다.

---

## 11. 실패와 엣지

| 상황 | 화면이 하는 일 |
| --- | --- |
| 채널로 해석되지 않는 URL | 등록 거부. "채널 URL 이 아닙니다" |
| yt-dlp 타임아웃·실행 불가 | 등록 거부 + 사유 |
| 피드가 404 | 등록 거부. 피드 없는 채널이다 |
| 피드가 5xx | 등록 거부하되 **다시 시도하라**고 말한다(→ 7.1) |
| 이미 등록된 채널 | 등록 거부. "이미 등록된 채널입니다" |
| 확인 중 한 채널 실패 | 나머지는 계속. 그 채널 자리에 사유 |
| 피드 항목에 필드가 빠짐 | 그 항목만 건너뛴다 |
| 등록된 채널 없음 | 안내. 확인 버튼을 그리지 않는다 |
| 신규 없음 | "새 영상이 없습니다" |
| 등록된 질문 없음 | 질문 관리로 안내. `[요약]` 없음 |
| 질의·정리 실행 중 | `[요약]` 잠금 + 이유 |
| 확인 뒤 채널을 삭제 | 세션의 결과는 채널 제목을 복사해 두므로 그대로 보인다 |

---

## 12. 테스트

| 대상 | 무엇을 단언하나 |
| --- | --- |
| `core/new_videos` | 기준일 직전·당일·직후 경계 · 이미 요약한 것 제외 · 최신 우선 정렬 · KST 기준일과 UTC 피드가 하루 밀리지 않음 · 빈 입력 |
| `services/channel_feed` | 가짜 getter 로 정상 파싱(ID·제목·시각) · 404 와 5xx 가 **다른 문구** · 그 밖의 상태 · 깨진 XML · 빈 피드는 성공 · 필드 빠진 항목은 건너뜀 · 크기 상한 초과 · 타임존 없는 시각은 건너뜀 |
| `services/channel_lookup` | 가짜 runner 로 `channel_id` 추출 · 채널이 아닌 URL · 0 이 아닌 종료 코드 · 타임아웃 · 깨진 JSON |
| `services/channels` | 등록·목록(이름순)·기준일 수정·삭제 · 중복 거부 · 빈 값 거부 · 잘못된 기준일 형식 거부 |
| `run_history.list_video_ids` | 저장된 ID 를 모두 돌려줌 · 빈 문자열 제외 · 중복 제거 |
| `pages/channels` | 채널 없음 안내 · 등록 성공과 실패 각 사유 · 확인 후 신규 목록 · 신규 없음 · 질문 없음 · 실행 중 잠금 · `[요약]` 이 러너에 URL·질문을 넘김 · 한 채널이 실패해도 나머지가 보임 |

화면 테스트는 `AppTest` 로 한다. `selectbox`·`multiselect` 의
`select()` 에는 **원본 옵션 객체**를 넘긴다 — 라벨 문자열을 주면
`format_func` 을 한 번 더 먹여 찾으므로 실패한다(R5 에서 실물로
확인).

검증은 CI 와 같은 네 단이다 — `ruff format --check .`,
`ruff check .`, `mypy src tests`, `pytest`.

---

## 13. 건드리는 파일

**신규**

- `core/new_videos.py`
- `services/channels.py` · `services/channel_feed.py` ·
  `services/channel_lookup.py`
- `pages/channels.py`
- 각 대응 테스트

**수정**

- `core/models.py` — `Channel`·`FeedEntry`
- `core/youtube.py` — `watch_url(video_id)` 를 더한다. 신규 목록이
  영상 URL 을 지어야 하는데 같은 f-string 이
  `core/markdown_export.py` 에도 있다. 한 줄짜리 중복이지만 지금
  세 번째가 생기므로 여기로 모으고, `markdown_export._source_url`
  이 그것을 쓰게 한다
- `services/store.py` — `channels` 스키마와 기대 컬럼
- `services/run_history.py` — `list_video_ids`
- `app.py` — 네비게이션에 채널 페이지
- `README.md` — 화면 하나와 사용 순서

**건드리지 않음**: `services/runner.py`, `services/runs.py`,
`services/nlm.py`, `services/outline.py`, `services/auth.py`,
`services/questions.py`, `services/video_metadata.py`,
`services/digest*.py`, `core/digest*.py`, `pages/ask.py`,
`pages/history.py`, `pages/digest.py`, `session.py`,
`docker-compose.yml`, `Dockerfile`, `pyproject.toml`.

새 의존성은 없다. `httpx` 와 `yt-dlp` 는 이미 있고 XML 은 표준
라이브러리로 읽는다.

---

## 14. 미검증 가정

- **피드 엔드포인트가 계속 산다** — 공식 API 문서에 실린 경로가
  아니라 오래 유지돼 온 공개 경로다. 두 채널에서 200 을 실물로
  확인했다. 죽으면 등록과 확인이 사유와 함께 실패하고, 그때
  yt-dlp 경로로 되돌릴 수 있다.
- **피드 15건이 실무에 충분하다** — 한 채널에서 16건 넘게 밀리면
  가장 오래된 신규가 목록에서 빠진다. 확인 주기가 주 단위를 넘지
  않으면 문제가 되지 않을 것으로 본다. 빠진 영상은 URL 을 직접 넣어
  질의 화면에서 요약할 수 있다.
- **핸들이 아닌 채널 URL 도 해석된다** — `@handle` 로는 실물로
  확인했다. `/channel/UC…` 와 `/c/…` 는 yt-dlp 가 같은 추출기로
  처리하므로 될 것으로 보나 확인하지 않았다. 안 되면 등록이 사유와
  함께 거부되므로 조용히 나빠지지 않는다.
- **채널 제목이 바뀌면 저장된 이름이 낡는다** — 등록 시점의 이름을
  보관하고 갱신하지 않는다. 사람이 지우고 다시 등록하면 된다.

---

## 15. 범위 밖

- **주기 실행과 무인 요약** — R6b(→ 16)
- **여러 건 한 번에 요약** — 대기열이 필요하고 실행 모델을 건드린다
  (→ 3.1)
- **채널별 질문 세트** — 무인 실행이 요구할 때 새 테이블로 붙인다
- **신규 영상을 Outline 에 자동 저장** — 저장은 사람이 제목을
  확인하는 지점이다(R4·R5)
- **채널 검색·추천·인기순 정렬** — 목록은 이름순 하나면 된다
- **영상 필터(길이·라이브·쇼츠 제외)** — 피드가 구분 값을 주지
  않는다. 필요해지면 그때 `video_metadata` 로 확인하는 비용을 다시
  따진다
- **알림** — R6b 가 무인 실행을 만들 때 함께 본다

---

## 16. R6b 로 넘기는 것

R6a 를 쓰다 보면 답이 나올 질문들이다. **지금 답하지 않는다.**

| 질문 | 지금 아는 것 |
| --- | --- |
| 스케줄러를 어디에 두나 | Streamlit 안은 안 된다(→ 2.5). 두 번째 compose 서비스(같은 이미지·다른 CMD)와 외부 cron 이 후보다 |
| 프로세스가 둘일 때 NotebookLM 을 어떻게 막나 | 지금 가드는 프로세스 안 메모리다(→ 2.6). SQLite 임대나 `/data` 의 파일 잠금이 후보다 |
| 무인 실행은 어떤 질문으로 도나 | `channel_questions` 새 테이블. DB 삭제 없이 붙는다(→ 2.3) |
| 무인 결과를 Outline 에 자동 저장하나 | R4·R5 는 사람이 제목을 확인하는 게이트를 뒀다. 그것을 없앨지가 가장 큰 결정이다 |
| 무인 실행의 실패와 인증 만료를 사람이 어떻게 아나 | 지금은 화면이 알려 준다. 무인에는 그 사람이 없다 |
| 회차당 몇 건까지 도나 | 영상 하나에 수 분이다. 채널 5개 × 신규 3건이면 한 회차가 한 시간에 가깝다 |
