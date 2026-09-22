# 영상 메타데이터 frontmatter 설계 — 요약본에 출처를 새기기

- **작성일**: 2026-09-22
- **상태**: 설계 (구현 계획 수립 전)
- **대상**: `services/video_metadata.py`(신규), `services/store.py`,
  `services/run_history.py`, `services/runner.py`, `core/models.py`,
  `core/markdown_export.py`, `pages/history.py`, `pyproject.toml`.
  질의 파이프라인(`services/nlm.py`)과 실행 모델(`services/runs.py`),
  인증(`services/auth.py`)은 건드리지 않는다.
- **범위**: 릴리스 R3. 기획 문서
  `docs/requests/2026-09-16-summary-pipeline-v2.md` 의 **요구 1·2**.
  선행 조건인 R1(무인 갱신 인증)과 R2(컨테이너 배포)는 완료되었다.

---

## 1. 왜 바꾸는가

요약본에는 **출처가 거의 남지 않는다.** `to_markdown` 이 만드는 머리글은
제목 한 줄과 출처·실행 두 줄이 전부다.

```python
# core/markdown_export.py:44-46
blocks = [
    f"# {summary.title or summary.video_id}",
    f"- 출처: {summary.url}\n- 실행: {summary.created_at}",
]
```

채널명과 업로드일자는 **애초에 저장되지 않는다.** `models.RunSummary` 에도
`runs` 테이블에도 그 자리가 없다. 문서를 나중에 다시 읽을 때 "누가 언제 올린
영상이었나" 를 알 길이 앱 안에 없다.

R4 가 요약본을 outline 으로 옮기면 이 결손이 그대로 따라간다. **문서가
저장소를 떠나기 전에 출처를 새겨 두는 것**이 이 릴리스다.

### 1.1 무엇을 고치지 않는가

기획 §2-1 이 말하는 불편은 **본문 "개요" 의 채널명이 "모름" 으로 찍히는
것**이다. 이 릴리스는 그것을 고치지 않는다.

- 고치는 것은 **문서 머리의 메타데이터**다. 본문은 NotebookLM 이 답한
  그대로 남는다.
- 따라서 한 문서 안에 정확한 채널명(frontmatter)과 "모름"(본문 개요)이
  함께 있을 수 있다.
- 본문을 고치려면 질문을 보낼 때 메타데이터를 프롬프트에 주입해야 하고,
  그러면 질의 파이프라인이 범위에 들어온다. 이 릴리스는 거기까지 가지
  않는다(→ 13).

**질문 템플릿은 코드가 아니라 사용자 데이터다.** `services/questions.py` 에
기본 템플릿이 없고 사용자가 DB 에 직접 넣는다. 본문의 "모름" 은 질문에서
채널명을 묻지 않는 것으로 사용자가 스스로 없앨 수 있다.

---

## 2. 조사로 확인한 사실

### 2.1 yt-dlp 가 주는 필드

공식 README 의 OUTPUT TEMPLATE 절에서 확인했다.

| 필드 | 문서의 설명 |
|---|---|
| `title` | Video title |
| `channel` | Full name of the channel the video is uploaded on |
| `uploader` | Full name of the video uploader |
| `upload_date` | Video upload date **in UTC** (YYYYMMDD) |
| `timestamp` | UNIX timestamp of the moment the video became available |
| `webpage_url` | A URL to the video webpage |

**채널명은 `channel` 을 쓴다.** `uploader` 는 업로더 이름이라 채널명과 다를
수 있다.

**`upload_date` 는 UTC 다.** 앱은 `TZ=Asia/Seoul` 로 돈다(R2 가 `Dockerfile`
에 박아 두었다). 한국 시각 이른 아침에 올라온 영상은 전날 날짜로 찍힌다.
`timestamp` 가 함께 오므로 그것을 로컬 시각으로 바꿔 쓴다.

### 2.2 `-J` 와 `--print`

- `-J`/`--dump-single-json` — URL 하나마다 JSON 한 덩어리를 찍는다.
- `-O`/`--print "{a,b}"` — 지정한 키만 담은 compact JSON 을 찍는다. 출력이
  훨씬 작다.

`--print "{a,b}"` 는 내부에서 `%(.{a,b})j` 로 바뀌어 지정한 키만 담은 dict 를
JSON 으로 찍는다. 그런데 **값이 없는 키가 그 dict 에서 어떻게 표기되는지는
확인하지 못했다.** `-J` 는 그냥 추출 결과 전체라서 없는 키에 `.get()` 이
`None` 을 준다는 것이 자명하다. 그래서 `-J` 를 쓴다(→ 3).

### 2.3 CLI 를 자식 프로세스로 부르는 전례가 있다

`services/auth.py` 가 `notebooklm` CLI 를 그렇게 부르고, 결과를 예외가 아니라
`ImportResult` 값으로 돌려준다. 화면은 그 `detail` 을 그대로 보여 준다.
메타데이터 조회도 같은 모양을 따른다.

### 2.4 이 프로젝트에는 마이그레이션이 없다

`services/store.py` 가 명시한 **의도된 결정**이다. `runs` 에 컬럼을 더하면
`_verify_schema` 가 기존 DB 를 `StaleSchemaError` 로 막고, 사용자가 할 수
있는 일은 파일을 지우는 것뿐이다 — **질문 템플릿과 실행 이력이 함께
사라진다.** R2 로 홈서버에 배포한 뒤이므로 이것은 실제 손실이다.

그런데 **새 테이블은 다르다.** `connect()` 가 매번 `executescript(_SCHEMA)`
를 돌리므로 옛 DB 파일에도 그 테이블이 생기고, `_verify_schema` 는 방금
만들어진 테이블을 검사하니 통과한다. 마이그레이션 정책을 건드리지 않고
컬럼을 늘리는 길이다.

### 2.5 런타임 이미지에는 갱신 수단이 없다

`Dockerfile` 이 `pip`·`setuptools` 를 지우고 `uv` 도 넣지 않는다(playwright
가 되살아나는 것을 막기 위한 R2 의 결정). **yt-dlp 를 올리는 방법은 이미지
재빌드뿐이다.** yt-dlp 는 유튜브 변경에 맞춰 자주 릴리스되므로 언젠가 낡아
추출이 실패한다. 이 설계는 그것을 **고장이 아니라 예정된 상태**로 다룬다.

---

## 3. 설계 결정

| 결정 | 선택 | 근거 |
|---|---|---|
| 저장 위치 | **새 테이블 `run_metadata`** | 2.4 — 기존 이력과 질문 템플릿을 지키면서 마이그레이션 정책도 건드리지 않는다 |
| 조회 시점 | **요약 실행 스레드 앞머리** | 화면이 멈추지 않는다. 그 시점의 영상은 살아 있다 |
| 호출 방식 | **`sys.executable -m yt_dlp` 서브프로세스** | 타임아웃을 확실히 건다. 실행파일이 PATH 에 있는지에 의존하지 않는다 |
| 출력 형식 | **`-J`** | 2.2 — `--print` 의 빈 값 표기를 확인하지 못했다 |
| 실패 처리 | **결과 객체로 돌려주고 요약은 계속** | 메타데이터는 부가물이다. 이것 때문에 요약이 죽으면 안 된다 |
| 날짜 기준 | **KST** | 2.1 — 사용자가 유튜브에서 보는 날짜와 맞춘다 |
| YAML 직렬화 | **직접 쓴다** | 내보내는 스칼라가 넷뿐이다. 의존성을 더할 값이 없다 |
| yt-dlp 갱신 | **수동** | 2.5. 주기적 재빌드·dependabot 은 범위 밖 |
| 본문 "개요" 수정 | **하지 않음** | 1.1 |
| 화면에 채널명 표시 | **하지 않음** | 요구에 없다. 필요해지면 그때 넣는다 |

---

## 4. 구조

```
사용자가 URL 을 넣고 실행
        │
        ▼
runner.start_run ──► 백그라운드 스레드 _work
                          │
                          ├─ video_metadata.fetch(url)      ← 새로 붙는 곳
                          │     yt_dlp 자식 프로세스, 20초
                          │     실패해도 멈추지 않는다
                          │
                          ├─ nlm.run_pipeline(...)          ← 건드리지 않음
                          │
                          └─ run_history.save_run(conn, result, metadata)
                                runs · answers · run_metadata 를 한 커밋으로

이력 화면에서 내려받기
        │
        ▼
pages/history ─ run_history.load_metadata(conn, run_id)
        └────► markdown_export.to_markdown(summary, items, metadata)
                     frontmatter + 지금과 똑같은 본문
```

**경계**: `core/` 와 `services/` 는 `streamlit` 을 import 하지 않는다.
yt-dlp 를 아는 모듈은 `services/video_metadata.py` 하나뿐이다.

---

## 5. `services/video_metadata.py` (신규)

### 5.1 인터페이스

```python
@dataclasses.dataclass(frozen=True, slots=True)
class MetadataResult:
    """메타데이터 조회 결과.

    둘 중 하나만 채워진다. 예외를 던지지 않는 것이 이 모듈의 계약이다.
    """

    metadata: models.VideoMetadata | None
    error: str | None


def fetch(url: str, timeout: float = 20.0) -> MetadataResult: ...
```

**이 함수는 예외를 던지지 않는다.** 호출자는 `runner._work` 의 백그라운드
스레드이고, 거기서 예외가 새면 요약 실행 전체가 죽는다. 모든 실패는
`error` 로 수렴한다.

### 5.2 호출

```python
video_id = youtube.extract_video_id(url)
if video_id is None:
    return MetadataResult(None, "영상 URL 이 아닙니다")

command = [
    sys.executable, "-m", "yt_dlp",
    "--no-playlist", "-J",
    f"https://www.youtube.com/watch?v={video_id}",
]
```

- **`sys.executable -m` 으로 부른다.** `yt-dlp` 실행파일은 윈도우
  `.venv/Scripts/` 와 컨테이너 `/app/.venv/bin/` 으로 위치가 갈리고 PATH 에
  있다는 보장이 없다. 2.3 의 전례와 같은 방식이다.
- **URL 을 다시 만들어 넘긴다.** 사용자가 넣은 원문에는 재생목록·추적
  파라미터가 붙어 있을 수 있다. 검증된 11자리 ID 로 정규 URL 을 짓고
  `--no-playlist` 를 함께 준다.
- **`shell=False`** 로 실행한다(`subprocess.run` 의 기본값). 인자가 셸을
  거치지 않으므로 주입 여지가 없다.
- **`timeout=20.0`.** 초과하면 `subprocess.run` 이 자식을 죽이고
  `TimeoutExpired` 를 던진다. 이것을 잡아 `error` 로 바꾼다. 파이썬 API 대신
  서브프로세스를 고른 이유가 이 한 줄이다 — `YoutubeDL` 에는 전체 시간을
  막는 수단이 없다.

### 5.3 파싱과 날짜

```python
info = json.loads(completed.stdout)
channel = info.get("channel") or None
upload_date = _to_local_date(info.get("timestamp"), info.get("upload_date"))
```

`_to_local_date` 의 규칙은 둘이다.

1. `timestamp` 가 있으면
   `datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")`.
   컨테이너가 `TZ=Asia/Seoul` 이므로 로컬 변환이 곧 KST 이고,
   `store.now()` 가 이미 같은 방식으로 로컬 시각을 쓴다.
2. `timestamp` 가 없고 `upload_date`(`YYYYMMDD`) 만 있으면 **모양만**
   `YYYY-MM-DD` 로 바꾼다. 이때 값은 UTC 기준이다.

빈 문자열은 `None` 으로 접는다. yt-dlp 가 값을 모를 때 키를 빼는 경우와 빈
문자열을 주는 경우가 섞이므로 한쪽으로 모은다.

### 5.4 실패

| 상황 | `error` 에 담기는 것 |
|---|---|
| 종료 코드 ≠ 0 | stderr 의 **뒤에서 500자**. 실제 원인은 마지막 줄에 있고, 앞쪽은 경고로 채워지는 일이 많다 |
| stdout 이 JSON 이 아님 | `출력을 해석하지 못했습니다` |
| 20초 초과 | `영상 정보 조회가 20초를 넘겨 중단했습니다` |
| `yt_dlp` 미설치 | 종료 코드 ≠ 0 경로로 들어온다(`No module named yt_dlp`) |
| URL 이 영상이 아님 | `영상 URL 이 아닙니다` (프로세스를 띄우지 않는다) |

**stderr 에 자격증명이 섞이지 않는다.** 이 호출은 `--cookies` 를 주지 않으므로
인증 정보 자체가 경로에 없다.

---

## 6. 저장

### 6.1 `core/models.py`

```python
@dataclasses.dataclass(frozen=True, slots=True)
class VideoMetadata:
    """영상에서 뽑아 온 메타데이터."""

    channel: str | None
    upload_date: str | None
```

`upload_date` 는 `YYYY-MM-DD` 문자열이다. **영상명과 URL 은 넣지 않는다** —
`runs` 에 `title`·`url`·`video_id` 가 이미 있어 중복이 된다. frontmatter 를
만들 때 둘을 합친다.

### 6.2 `services/store.py`

`_SCHEMA` 에 테이블을 더하고 `_EXPECTED_COLUMNS` 에 같은 항목을 추가한다.

```sql
CREATE TABLE IF NOT EXISTS run_metadata (
    run_id      INTEGER PRIMARY KEY REFERENCES runs(id)
                ON DELETE CASCADE,
    channel     TEXT,
    upload_date TEXT
);
```

- `run_id` 를 기본키로 두어 **1:1 을 스키마가 강제**한다.
- `ON DELETE CASCADE` 는 `answers` 와 같다. `connect()` 가
  `PRAGMA foreign_keys = ON` 을 켜므로 `delete_run` 이 그대로 정리한다.
- **기존 DB 는 깨지지 않는다** (2.4).

### 6.3 `services/run_history.py`

```python
def save_run(
    connection: sqlite3.Connection,
    result: models.RunResult,
    metadata: models.VideoMetadata | None = None,
) -> int: ...


def load_metadata(
    connection: sqlite3.Connection, run_id: int
) -> models.VideoMetadata | None: ...
```

- `metadata` 는 **기본값이 있다.** 기존 호출자는 고치지 않아도 된다.
- `metadata` 가 `None` 이면 **행을 만들지 않는다.** 빈 행과 없는 행이 같은
  뜻이 되면 나중에 "조회를 안 했다" 와 "조회했는데 값이 없다" 를 구분하지
  못한다. 지금은 구분할 필요가 없으므로 단순한 쪽을 고른다.
- 저장은 `runs`·`answers` 와 **같은 커밋** 안에서 한다. 현재도 둘을 한
  `commit()` 으로 묶는다.

---

## 7. `core/markdown_export.py`

### 7.1 출력

```
---
title: "AI 에이전트의 미래"
channel: "안될공학"
upload_date: 2026-09-14
url: https://www.youtube.com/watch?v=dQw4w9WgXcQ
---

# AI 에이전트의 미래

- 출처: https://www.youtube.com/watch?v=dQw4w9WgXcQ
- 실행: 2026-09-22T10:00:00

## 첫 질문
...
```

**frontmatter 아래 본문은 지금과 한 글자도 다르지 않다.** 기존 테스트가 그
계약을 지킨다.

### 7.2 키

```python
def to_markdown(
    summary: models.RunSummary,
    items: Sequence[models.AnswerItem],
    metadata: models.VideoMetadata | None = None,
) -> str: ...
```

- `title` 과 `url` 은 `RunSummary` 에서 오므로 **항상 나온다.** 덕분에
  메타데이터가 없는 옛 이력도 두 줄짜리 frontmatter 를 얻는다.
- `channel`·`upload_date` 는 값이 없으면 **키째로 생략한다.** `null` 을
  적으면 읽는 쪽이 "값이 null 인 채널" 과 "모르는 채널" 을 구분하지 못한다.
- `title` 이 `None` 이면 본문 제목과 같은 규칙으로 `video_id` 를 쓴다.

### 7.3 값 표기

| 키 | 표기 | 이유 |
|---|---|---|
| `title`·`channel` | **큰따옴표로 감싼다** | 자유 문자열이다. 유튜브 제목에는 `"` 와 `:` 가 흔하다 |
| `upload_date` | 따옴표 없음 | `YYYY-MM-DD` 는 YAML 이 날짜로 읽는다. 읽는 도구가 정렬·필터에 쓸 수 있다 |
| `url` | 따옴표 없음 | 7.4 가 안전을 보장한다 |

### 7.4 `url` 을 정규화해서 쓴다

`summary.url` 은 **사용자가 입력한 원문**이다. 재생목록 파라미터나 `#` 이
붙어 있으면 따옴표 없는 YAML 값으로는 위험하다. 그래서 저장된
`summary.video_id` 로 `https://www.youtube.com/watch?v=<id>` 를 다시 짓는다.

- `video_id` 는 `core/youtube.py` 가 `[A-Za-z0-9_-]{11}` 로 검증한 값이라
  YAML 특수문자가 들어갈 수 없다.
- 추적 파라미터도 함께 떨어진다.
- `video_id` 가 빈 문자열인 이력(추출에 실패한 채 저장된 경우)에서는
  `summary.url` 을 **큰따옴표로 감싸** 넣는다.

### 7.5 이스케이프

큰따옴표로 감싸는 값에만 적용한다.

1. `\` → `\\`
2. `"` → `\"`
3. 개행·탭·캐리지리턴 → `\n`·`\t`·`\r`
4. 남은 C0 제어문자(`\x00`–`\x1f`)는 **지운다**

4번은 YAML 이중따옴표 스칼라가 `\x41` 형태의 표기를 요구하는 자리인데, 이
값들이 문서에 남아야 할 이유가 없다. 파일명을 만들 때 이미 같은 범위를
거르고 있다(`_FORBIDDEN`).

---

## 8. 연결

### 8.1 `services/runner.py`

`_work` 가 파이프라인을 돌리기 **전에** 세 줄을 더한다.

```python
on_progress("영상 정보 확인 중")
meta = video_metadata.fetch(url)
if meta.error is not None:
    on_progress(f"영상 정보를 가져오지 못했습니다: {meta.error}")
```

- 이미 백그라운드 스레드 안이라 **화면이 멈추지 않는다.**
- 진행 문구는 `components/run_progress.py` 가 그리던 경로를 그대로 탄다.
  Streamlit API 를 부르지 않는다는 `_work` 의 규칙을 지킨다.
- **실패해도 `return` 하지 않는다.** 파이프라인이 끝나면
  `run_history.save_run(connection, result, meta.metadata)` 로 넘어간다.
  조회에 실패했으면 `meta.metadata` 가 `None` 이고, 6.3 대로 행이 생기지
  않는다.

### 8.2 `pages/history.py`

`to_markdown` 을 부르는 유일한 자리다(`:84`). 다운로드 버튼을 그리기 전에
`run_history.load_metadata()` 를 한 번 불러 넘긴다.

---

## 9. `pyproject.toml`

```
uv add yt-dlp
```

- **버전을 좁게 고정하지 않는다.** 2.5 가 말하듯 낡으면 깨지는 물건이라,
  다시 구울 때 최신을 받는 편이 낫다. 재현성은 `uv.lock` 이 맡는다.
- **`Dockerfile` 은 건드리지 않는다.** yt-dlp 는 순수 파이썬이고 메타데이터
  추출에 ffmpeg 이 필요 없다(다운로드·병합에만 쓴다). `uv sync --no-dev` 가
  런타임 의존성으로 함께 넣는다.

---

## 10. 테스트

| 파일 | 넣을 것 |
|---|---|
| `tests/services/test_video_metadata.py` (신규) | 정상 JSON 파싱 · `timestamp` → KST 변환 · `timestamp` 없을 때 `upload_date` 폴백 · 종료코드 ≠ 0 · JSON 깨짐 · 타임아웃 · 영상 URL 이 아님. **모두 `error` 로 수렴하고 예외가 새지 않는 것** |
| `tests/services/test_store.py` | **`run_metadata` 가 없는 옛 DB 파일을 열면 테이블이 생기고 `StaleSchemaError` 가 나지 않는 것** |
| `tests/services/test_run_history.py` | 저장·조회 · `metadata=None` 이면 행을 안 만드는 것 · `delete_run` 이 CASCADE 로 함께 지우는 것 |
| `tests/core/test_markdown_export.py` | frontmatter 전체 · 일부 키 생략 · **따옴표·역슬래시·개행이 든 제목** · `video_id` 가 빈 이력 · **본문이 안 바뀐 것** |
| `tests/services/test_runner_start.py` | 메타데이터 조회가 실패해도 **요약 실행이 끝까지 가는 것** |
| `tests/pages/test_history.py` | 내려받는 데이터에 frontmatter 가 실리는 것 |

**자식 프로세스는 실제로 띄우지 않는다.** `tests/services/test_auth.py` 가
쓰는 방식대로 실행 함수를 가짜로 바꾼다. 네트워크에 기대는 테스트를 만들지
않는다.

**KST 변환 테스트는 타임존을 고정한다.** 개발 기계가 어느 타임존이든 같은
결과가 나와야 한다. 변환 함수가 쓸 타임존을 주입받게 두거나 테스트가 환경을
고정한다 — 구현 계획에서 둘 중 하나를 고른다.

---

## 11. 건드리는 파일

| 파일 | 변경 |
|---|---|
| `src/notebooklm_st/services/video_metadata.py` | 신규 (5절) |
| `src/notebooklm_st/core/models.py` | `VideoMetadata` 추가 (6.1) |
| `src/notebooklm_st/services/store.py` | `run_metadata` 테이블 (6.2) |
| `src/notebooklm_st/services/run_history.py` | `save_run` 인자·`load_metadata` (6.3) |
| `src/notebooklm_st/core/markdown_export.py` | frontmatter (7절) |
| `src/notebooklm_st/services/runner.py` | `_work` 에 조회 세 줄 (8.1) |
| `src/notebooklm_st/pages/history.py` | 메타데이터를 읽어 넘김 (8.2) |
| `pyproject.toml` · `uv.lock` | `yt-dlp` 추가 (9절) |
| `tests/` 6개 파일 | 10절 |
| `README.md` | 요약본에 frontmatter 가 붙는다는 한 문단 |

건드리지 않는 것: `services/nlm.py`, `services/runs.py`, `services/auth.py`,
`core/errors.py`, `core/answer_text.py`, `components/` 전체, `pages/` 의
나머지, `Dockerfile`, `docker-compose.yml`, `.github/workflows/`.

---

## 12. 미검증 가정

1. **`-J` 응답에 `channel` 과 `timestamp` 가 실제로 담기는지.** 2.1 은 공식
   문서가 그 필드를 정의한다는 것까지 확인했다. 특정 영상의 실제 응답으로는
   확인하지 않았다. 담기지 않으면 키가 생략될 뿐이고, 설계가 기대하는
   동작(`None` → 키 생략)과 같다.
2. **컨테이너에서 유튜브로 나가는 요청이 막히지 않는지.** 홈서버의 아웃바운드
   정책은 확인하지 않았다. 막히면 `error` 로 수렴하고 요약은 계속된다.
3. **조회에 실제로 얼마나 걸리는지.** 20초는 넉넉히 잡은 값이고 실측이
   아니다. 요약 한 건이 분 단위로 걸리므로 20초가 체감을 크게 바꾸지는
   않는다.

---

## 13. 범위 밖

- **본문 "개요" 의 채널명** — 1.1. 질의 파이프라인에 메타데이터를 주입하는
  일이고, 그 순간 `services/nlm.py` 가 범위에 들어온다
- **URL 입력 직후 영상 정보 미리보기** — 조회가 Streamlit 메인 스레드에서
  돌아 화면이 멈춘다. 대시보드 입력 흐름을 바꿔야 한다
- **대시보드·이력 화면에 채널명 표시** — 요구에 없다
- **yt-dlp 자동 갱신(주기적 재빌드·dependabot)** — 2.5. 수동으로 둔다
- **옛 이력의 메타데이터 소급 채우기** — 이미 저장된 실행에 대해 yt-dlp 를
  다시 도는 일. 필요해지면 별도로 다룬다
- **Outline 저장** — R4
- **정리본** — R5
- **스케줄러 · 실행 큐 · Slack 알림** — R6
