# 저장된 이력의 채널·업로드일 설계 — 정리본 재료 표에 두 열 더하기

- **작성일**: 2026-09-30
- **상태**: 구현 완료 (2026-09-30)
- **대상**: 수정 `core/markdown_export.py`·`core/outline_import.py`·
  `core/models.py`·`services/run_history.py`·
  `services/run_history_sync.py`·`services/history_sync.py`·
  `pages/_history_sync.py`·`pages/_digest_materials.py`·
  `pages/history.py`(도움말 한 줄)·`README.md`.
  스키마(`services/store.py`), Outline 호출(`services/outline.py`·
  `services/outline_parse.py`), 러너(`services/runner.py`), 메타데이터
  수집(`services/video_metadata.py`), 정리 파이프라인
  (`services/digest*.py`·`core/digest*.py`), 배포 파일
  (`docker-compose.yml`·`Dockerfile`·`pyproject.toml`)은 건드리지 않는다.
- **범위**: 정리본 재료 표에 **채널**·**업로드일** 열을 더한다. 그
  값을 저장된 이력에 남기고, 이력 동기화가 Outline 문서에서 읽어
  채운다.
- **전제**: Outline 1.10.0 이상. 이력 동기화
  (`2026-09-28-history-sync-design.md`)와 같다.

---

## 1. 왜 바꾸는가

정리본 화면은 저장된 요약본 전부를 표 하나로 펼쳐 재료를 고르게 한다
(`2026-09-23-digest-design.md` §10.2). 지금 표는 문서 제목·시각·
Outline 링크만 보여 준다. 같은 주제를 다룬 영상이 여럿 쌓이면 **어느
채널의 언제 영상인지**가 고르는 기준이 되는데, 표에는 그 단서가 없다.

두 값은 요약을 실행할 때 이미 받는다(R3). 그런데 저장된 요약본의
로컬 행에는 남아 있지 않다. Outline 에 저장하는 순간 지우기 때문이다
(2.1). 그래서 열만 더하면 모든 칸이 빈다.

이 설계는 두 값을 저장된 이력에 **캐시로** 남긴다. 정본은 여전히
Outline 문서이고, 로컬 값은 표를 그리려고 들고 있는 사본이다. 이미
저장된 요약본과 DB 를 지운 뒤 되살린 요약본은 이력 동기화가 문서에서
읽어 채운다.

**성공 기준**

- 새로 저장하는 요약본은 저장 직후 재료 표에 두 값이 나온다.
- 이미 저장된 요약본은 이력 화면의 "Outline 과 동기화" 를 한 번
  적용하면 나온다.
- DB 파일을 지우고 동기화로 되살려도 나온다.
- 문서 머리에 두 줄이 없는 요약본은 빈칸으로 남고, 다른 동작은 막히지
  않는다.

---

## 2. 조사로 확인한 사실

### 2.1 값은 실행 때 받고, 저장할 때 지운다

- 요약 실행이 끝나면 `run_history.save_run` 이 `run_metadata` 행
  (`run_id`·`channel`·`upload_date`)을 만든다. 메타데이터를 못 받았으면
  행을 만들지 않는다 — "빈 행과 없는 행이 같은 뜻이 되면 안 된다"
  (`2026-09-22-video-metadata-design.md`).
- 업로드일은 `services/video_metadata._to_date` 가 `YYYY-MM-DD` 로
  만든다.
- `run_links.mark_exported` 는 링크를 적는 UPDATE 와 함께
  `answers`·`run_metadata` 를 DELETE 하고 커밋 하나로 묶는다. R4
  (`2026-09-22-outline-storage-design.md`)의 "저장에 성공하면 본문을
  지우고 링크만 남긴다 — 진실의 원천이 하나여야 한다" 는 결정이다.
- 이력 동기화의 `run_history_sync.insert_exported` 도 되살린 행에
  `answers`·`run_metadata` 를 만들지 않는다.

그래서 지금 재료 표에 오르는 행은 **전부** `run_metadata` 가 없다.

### 2.2 값은 Outline 문서 머리 블록에 남아 있다

`core/markdown_export._metadata_block` 은 문서 첫머리에 이 리스트를
쓴다. 값이 없는 줄은 통째로 빠진다. 카테고리가 없으면 카테고리 줄도
빠진다(`2026-10-03-categories-design.md`).

```markdown
- 제목: …
- 채널: …
- 업로드 일자: 2026-09-20
- 카테고리: …
- 영상 URL: https://www.youtube.com/watch?v=…
```

- 라벨 `영상 URL` 은 `markdown_export.SOURCE_URL_LABEL` 상수이고,
  `채널`·`업로드 일자` 는 f-string 안의 글자다.
- 채널명은 `one_line` 으로 제어문자를 지우고 공백을 접을 뿐, 마크다운
  메타문자를 이스케이프하지 않는다(R4 가 정한 그대로).
- R3(영상 메타데이터)이 R4(Outline 저장)보다 먼저 들어갔다. 그래서 이
  앱이 Outline 에 올린 요약본 문서는 실행 때 받은 값의 줄을 **전부**
  갖는다. 줄이 없는 것은 수집이 실패한 요약본뿐이다. 운영 위키에서 그
  비율을 재 보지는 않았다(15).
- Outline 은 본문을 다시 직렬화해 돌려준다. 글머리표가 `*`·`+` 로
  바뀌고 값 안에 역슬래시 이스케이프가 들어올 수 있다. 영상 URL 줄은
  이미 이 변형을 받는다(`core/outline_import.find_source_url`).

### 2.3 동기화는 이미 문서 본문을 전부 받는다

`outline.list_documents` 가 돌려주는 `ListedDocument` 에는 본문
`markdown` 이 실려 있다. 목록 응답에 `text` 가 오기 때문이다(이력
동기화 §2.1). 두 값을 읽으려고 **Outline 호출을 더 할 필요가 없다.**

### 2.4 "기존 행은 손대지 않는다" 의 이유

이력 동기화 §3 은 기존 행을 손대지 않기로 했다. 이유는 둘이다 — 전부
지우고 재구축하면 **ID 가 바뀌어 다른 탭의 선택이 풀리고**, **원래
실행 시각이 덮인다.** `run_metadata` 를 쓰는 것은 `runs` 행의 ID 도
시각도 바꾸지 않는다. 그래서 이 설계는 그 결정의 이유를 거스르지 않고
기존 행의 메타데이터를 갱신한다.

### 2.5 실행 ID 는 다시 쓰인다

`runs.id` 에는 `AUTOINCREMENT` 가 없다. 계획이 세션에 남은 사이 가장 큰
ID 의 행이 지워지고 새 미저장 실행이 그 ID 를 받을 수 있다(이력 동기화
§2.6). 삭제가 `(실행 ID, 문서 ID)` 쌍으로 맞추는 이유이고, 갱신도 같은
위험을 진다.

### 2.6 Python 3.13 은 주석을 바로 평가한다

`core/models.py` 에서 `VideoMetadata` 는 `RunSummary` 보다 **아래**에
있다. 이 프로젝트는 `from __future__ import annotations` 를 쓰지 않으므로
(`.claude/rules/streamlit-implement.md` §5), `RunSummary` 의 필드 주석에
`VideoMetadata` 를 쓰려면 정의 순서를 바꿔야 한다.

### 2.7 재료 표의 key 는 실행 ID 로만 만든다

`pages/_digest_materials.widget_key` 는 표에 오른 목록 — 카테고리·채널
필터로 거른 목록 — 의 실행 ID 를 순서대로 이은 문자열에서 key 를
만든다. 필터를 켜지 않았으면 메타데이터가 바뀌어도 ID 와 순서는
그대로이므로, 동기화로 두 값이 채워져도 **고른 재료가 비워지지
않는다.** 필터를 켠 채 동기화가 채널·카테고리를 바꾸면 거른 목록이
달라져 key 도 바뀔 수 있다(`2026-10-03-categories-design.md`).

---

## 3. 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 저장 뒤 메타데이터 | **로컬에 남긴다** | 방금 문서에 적은 값과 사실상 같다(9.1 의 수렴 참고). 정본은 Outline 이고 로컬은 캐시다. 로컬 값을 고치는 화면이 없으므로 흐름은 Outline → 로컬 한 방향뿐이다 |
| 이미 저장된 행 | **이력 동기화가 문서에서 읽어 채운다** | 사람이 버튼을 누를 때만 Outline 을 읽는 원칙이 유지된다. 호출이 늘지 않는다(2.3) |
| 문서 값이 로컬과 다름 | **문서 값으로 덮는다** | 정본이 이긴다 |
| 문서에서 못 읽은 칸 | **로컬 값을 그대로 둔다** | Outline 직렬화가 바뀌어 파싱이 실패하면, "없으면 지운다" 규칙은 멀쩡한 캐시를 한꺼번에 비운다. 대가는 Outline 에서 줄을 지워도 로컬 값이 남는 것이다 |
| 두 값이 모두 없는 행 | **`run_metadata` 행을 만들지 않는다** | 빈 행과 없는 행을 같은 뜻으로 만들지 않는다(2.1) |
| 갱신을 쓰는 기준 | **실행 ID 와 문서 ID 가 둘 다 맞을 때만** | 삭제와 같은 이유다(2.5) |
| 갱신 건수 | **값이 실제로 바뀐 행만 센다** | `SyncResult` 는 "실제로 바꾼 개수" 다. 낡은 계획을 다른 탭에서 한 번 더 적용하면 중복 생성이 0 건으로 나오듯 갱신도 0 건이어야 한다 |
| 갱신의 미리보기 | **개수만 보여 준다** | 처음 채울 때는 저장된 요약본 전부가 대상이라 목록이 수십 줄이 된다. 지우는 것이 아니라 캐시를 채우는 일이라 한 건씩 확인할 이유가 약하다 |
| 조회 | **`SUMMARY_SELECT` 에 `run_metadata` 를 LEFT JOIN 한다** | 재료 표와 동기화 계획이 같은 쿼리 하나로 값을 받는다. 화면이 실행마다 따로 조회하지 않는다 |
| `RunSummary` 에 싣는 모양 | **`metadata: VideoMetadata \| None`** | 행이 없으면 `None`. "행 없음" 과 "값 빔" 의 구분이 조회 뒤에도 남는다 |
| 업로드일 형식 | **`YYYY-MM-DD` 로 읽히는 값만 받는다** | 우리가 쓴 형식이다. 다른 모양은 손상으로 보고 그 칸을 읽지 못한 것으로 친다 |
| 라벨 문자열 | **`markdown_export` 의 상수를 쓰는 쪽과 읽는 쪽이 함께 쓴다** | `SOURCE_URL_LABEL` 과 같다. 한쪽만 바뀌면 모든 문서가 조용히 빈칸이 된다 |
| 표의 열 | **문서 제목 · 카테고리 · 채널 · 업로드일 · 시각 · Outline** | 고르는 기준이 제목 다음에 온다. 시각은 요약한 때라 뒤로 민다. 카테고리 칸은 `2026-10-03-categories-design.md` 가 둔다 |
| 스키마 | **바꾸지 않는다** | `run_metadata` 가 이미 있다. DB 파일을 지울 일이 없다 |

### 3.1 기각한 안

- **저장할 때는 지금처럼 지우고 동기화로만 채우기** — 저장할 때마다
  값이 사라졌다가 다음 동기화에서야 돌아온다.
- **저장할 때만 남기고 동기화는 그대로** — 이미 저장된 요약본은 계속
  빈칸이고, DB 를 지우면 다시 사라진다.
- **화면을 열 때 Outline 에서 읽기** — 재료 수만큼 `documents.info` 를
  부른다. Outline 이 죽으면 정리본 화면이 멈춘다.
- **yt-dlp 로 다시 받기** — 영상마다 몇 초가 걸리고 네트워크를 탄다.
  정본인 문서와 다른 값이 로컬에 생길 수 있다.
- **"메타데이터 채우기" 버튼을 따로 두기** — 동기화가 이미 문서 목록을
  받는다. 버튼이 둘이면 같은 목록을 두 번 읽고, 사람은 무엇을 먼저
  눌러야 하는지 알아야 한다.
- **문서에 줄이 없으면 로컬도 지우기** — 정본 원칙에는 맞지만 파싱
  실패가 곧 캐시 전체 소실이 된다(3).
- **갱신 대상을 목록으로 다 보여 주기** — 첫 동기화에서 수십 줄이
  된다(3).
- **`channel`·`upload_date` 를 `RunSummary` 에 평평하게 두 필드로** —
  행이 없는 것과 두 값이 빈 행을 구분하지 못한다.

---

## 4. 구조

```
요약 실행 끝 → runs + answers + run_metadata + run_categories   (그대로)
        ↓
이력 화면 "Outline 에 저장"
  to_markdown() → 문서 머리에 채널·업로드 일자·카테고리 줄       (그대로)
  mark_exported() → 링크 기록 + answers 삭제    (run_metadata·run_categories 는 남김)
        ↓
이력 화면 "Outline 과 동기화"
  list_documents() → ListedDocument(markdown 포함)    (그대로)
  plan(list_exported(), documents, 알려진 카테고리)
     ├ creates           : 새 행 + 문서에서 읽은 메타데이터·카테고리
     ├ updates           : 기존 행 중 문서 값과 다른 것        (신규)
     ├ category_updates  : 기존 행 중 카테고리 이름 집합이 다른 것
     ├ new_categories    : 로컬에 없는 카테고리 이름
     ├ deletes  / skips                                        (그대로)
  apply() → 새 카테고리 등록 · 삭제 · 삽입 · 갱신 · 카테고리 교체를 커밋 하나로
        ↓
정리본 화면
  list_exported() → RunSummary.metadata·categories    (LEFT JOIN · 서브쿼리)
  재료 표: 카테고리·채널 필터 → 문서 제목 · 카테고리 · 채널 · 업로드일 · 시각 · Outline
```

카테고리 쪽(`run_categories`·`category_updates`·`new_categories`·필터·
카테고리 칸)은 `2026-10-03-categories-design.md` 가 다룬다.

모듈 경계는 그대로다. `core/outline_import` 가 문서를 읽고,
`services/history_sync` 가 계획을 세우고 적용하며,
`services/run_history_sync` 가 DB 에 쓴다. 화면은 계획과 요약을 그릴
뿐이다.

---

## 5. `core/markdown_export.py` — 라벨 상수

```python
CHANNEL_LABEL = "채널"
UPLOAD_DATE_LABEL = "업로드 일자"
```

`_metadata_block` 이 f-string 안의 글자 대신 두 상수를 쓴다. 문서에
나가는 글자는 바뀌지 않는다.

---

## 6. `core/outline_import.py` — 머리 블록에서 두 값 읽기

```python
def find_metadata(markdown: str) -> models.VideoMetadata | None
```

- 머리 블록의 규칙은 `find_source_url` 과 같다. 첫 `^\s*---\s*$` 줄
  앞까지이고, 구분선이 없으면 전체다. 두 함수가 이 규칙을 따로 들고
  있지 않도록 머리 블록 줄을 내주는 내부 함수 하나를 함께 쓴다.
- 줄 모양은 `^\s*[-*+]\s*<라벨>:\s*(?P<value>.*?)\s*$` 다. 라벨은 5 의
  상수를 `re.escape` 해 쓴다. 값은 비어 있어도 줄이 맞는다.
- 라벨마다 **라벨이 맞는 첫 줄만 본다.** 그 값이 비었거나 날짜로
  읽히지 않아도 뒤의 같은 라벨 줄로 넘어가지 않고, 그 칸은 `None` 이다.
  우리는 라벨마다 한 줄만 쓰므로 둘째 줄은 사람이 고친 흔적이고, 어느
  줄이 맞는지 앱이 고를 근거가 없다. 값이 빈 줄을 건너뛰는
  `find_source_url`(`\S+`)과 다르다 — 그쪽은 URL 이 없으면 이력을
  못 만드니 뒤의 줄이라도 찾는 편이 낫고, 이쪽은 빈칸이 곧 안전한
  실패다.
- 꺼낸 값에서 **ASCII 문장부호 앞의 역슬래시**를 걷는다. CommonMark 가
  이스케이프로 인정하는 범위이고, 채널명에는 `_`·`-`·`*`·`[`·`!` 등이
  흔하다. 영상 URL 줄의 `_ESCAPE`(`_`·`-`·`*`·`#` 넷)보다 넓다 — URL 에는
  나올 수 없는 문자까지 채널명에는 나온다.
- **채널**: 걷어 낸 값이 비었으면 `None`.
- **업로드 일자**: 걷어 낸 값이 `^\d{4}-\d{2}-\d{2}$` 에 맞고
  `datetime.date.fromisoformat` 이 받아야 한다. 아니면 `None`.
- 두 칸이 모두 `None` 이면 `None` 을 돌려준다. 하나라도 있으면
  `VideoMetadata` 를 돌려주고, 못 읽은 칸은 `None` 이다.
- `- 제목: 채널: …` 처럼 다른 라벨의 값 안에 나온 글자는 줄 머리에서
  라벨을 맞추므로 걸리지 않는다.

`core` 모듈끼리의 import(`core.models`)라 경계 규칙에 걸리지 않는다.

---

## 7. `core/models.py`·`core/sync_models.py`

- `VideoMetadata` 를 `RunSummary` **위로** 옮긴다(2.6). 내용은 그대로다.
- `RunSummary` 에 필드를 더한다. 기본값이 있어 기존 생성 코드가
  깨지지 않는다.

  ```python
  metadata: VideoMetadata | None = None
  """``run_metadata`` 행. 행이 없으면 ``None``."""
  ```

  클래스 독스트링의 "로컬에는 링크만 남아 있다" 는 "로컬에는 링크와
  영상 메타데이터, 카테고리만 남아 있다" 로 고친다.

- 아래 동기화 값 객체는 `core/sync_models.py` 에 있다
  (`2026-10-03-categories-design.md` 5.3). `core/models.py` 를 import 해
  `models.RunSummary`·`models.VideoMetadata` 로 쓴다.
- `SyncCreate` 에 `metadata: models.VideoMetadata | None = None` 을
  더한다. 문서에서 읽은 값이다.
- 새 값 객체를 더한다. `SyncPlan` 이 주석에 쓰므로 **`SyncPlan` 위에**
  둔다(2.6 과 같은 이유).

  ```python
  @dataclasses.dataclass(frozen=True, slots=True)
  class SyncUpdate:
      """동기화가 메타데이터를 갱신할 기존 행 한 건."""

      run: models.RunSummary
      metadata: models.VideoMetadata
      """쓸 값. 문서가 준 칸과 로컬에 남길 칸을 합친 결과다."""
  ```

- `SyncPlan` 에 `updates: tuple[SyncUpdate, ...] = ()` 를 더하고,
  `is_empty` 는 `updates` 와 `category_updates` 까지 비었을 때만 참이다.
  독스트링의 "지울 것도 만들 것도 없다" 는 "지울 것도 만들 것도 갱신할
  것도 없다" 가 된다.

---

## 8. 저장소

### 8.1 `services/run_history.py`

**`SUMMARY_SELECT`** 에 조인과 세 컬럼을 더한다. 카테고리 이름 칸
(`category_names`)은 `2026-10-03-categories-design.md` 7.3 의 상관
서브쿼리다.

```sql
SELECT r.id, r.url, r.video_id, r.title, r.created_at,
       r.outline_id, r.outline_url, r.outline_title, r.exported_at,
       m.run_id AS metadata_run_id, m.channel, m.upload_date,
       (SELECT group_concat(c.name, ',')
          FROM run_categories AS rc
          JOIN categories AS c ON c.id = rc.category_id
         WHERE rc.run_id = r.id) AS category_names,
       COUNT(a.id) AS answer_count
FROM runs AS r
LEFT JOIN answers AS a ON a.run_id = r.id
LEFT JOIN run_metadata AS m ON m.run_id = r.id
```

`run_metadata` 는 `run_id` 가 기본 키라 실행 하나에 많아야 한 행이다.
조인이 답변 행을 불리지 않으므로 `COUNT(a.id)` 는 그대로다. 뒤에 붙는
`GROUP BY r.id` 도 그대로다.

**`row_to_summary`** 는 `metadata_run_id` 가 `NULL` 이면
`metadata=None`, 아니면 `VideoMetadata(channel, upload_date)` 를 싣는다.
카테고리는 `category_names` 를 쉼표로 나눠 파이썬에서 이름 순으로
`categories` 에 싣는다. `list_runs` 와 `run_history_sync.list_exported`
가 이 둘을 함께 쓰므로 두 목록 모두 메타데이터와 카테고리를 싣고 온다.

**`mark_exported`** 는 `run_metadata` DELETE 를 뺀다. UPDATE 와
`answers` DELETE 를 커밋 하나로 묶고 어떤 예외든 롤백해 다시 던지는
구조는 그대로다. 독스트링은 첫 줄이 "문서 링크를 적고 로컬 답변을
지운다" 가 되고, "세 문장을 커밋 하나로" 는 "두 문장을" 이 된다.
메타데이터는 문서 머리와 같은 값의 캐시로 남긴다는 문장을 더한다.

### 8.2 `services/run_history_sync.py`

**`insert_exported`** — `create.metadata` 가 있으면 새 행의 ID 로
`run_metadata` 행도 넣는다. 없으면 넣지 않는다. `create.categories` 의
카테고리는 이름으로 잇는다(`2026-10-03-categories-design.md` 7.4).
같은 문서의 행이 이미 있어 `None` 을 돌려주는 경우에는 아무것도 쓰지
않는다. 커밋하지 않는 규칙은 그대로다.

**`write_metadata`** 를 더한다.

```python
def write_metadata(
    connection: sqlite3.Connection,
    run_id: int,
    outline_id: str,
    metadata: models.VideoMetadata,
) -> bool
```

- 실행 ID 와 문서 ID 가 **둘 다 맞는 `runs` 행이 있을 때만** 그 행의
  `run_metadata` 를 넣거나 덮는다. 하나의 문장으로 쓴다 — `runs` 에서
  두 조건으로 고른 ID 를 `INSERT … SELECT` 하고 `ON CONFLICT(run_id)
  DO UPDATE` 로 덮는다. SQLite 는 `INSERT … SELECT` 에 `WHERE` 가
  있어야 뒤의 `ON CONFLICT` 를 upsert 절로 읽는다 — 두 조건이 곧 그
  `WHERE` 다.
- `DO UPDATE` 에는 `WHERE channel IS NOT excluded.channel OR
  upload_date IS NOT excluded.upload_date` 를 붙인다. 값이 같으면
  덮지 않고 바뀐 행 수도 0 이다(3 의 "갱신 건수").
- 새로 넣었거나 값을 바꿨으면 `True`. 맞는 `runs` 행이 없거나 값이
  이미 같으면 `False`.
- **커밋하지 않는다.** 트랜잭션은 `history_sync.apply` 가 소유한다.

`list_exported` 는 바뀌지 않는다. `SUMMARY_SELECT` 를 통해 메타데이터를
싣고 온다.

---

## 9. `services/history_sync.py`

### 9.1 `plan`

기존 네 규칙(이력 동기화 §5)은 그대로다. 두 가지가 더해진다.

**생성 대상**에는 `outline_import.find_metadata(document.markdown)` 의
결과를 `SyncCreate.metadata` 로 싣는다.

**행과 문서가 모두 있는 경우**를 더 나눈다.

| 문서가 준 값 | 판정 |
|---|---|
| 두 칸 모두 못 읽음(`find_metadata` 가 `None`) | 손대지 않음 — 로컬에 값이 있든 없든 |
| 합친 값이 로컬과 같음 | 손대지 않음 |
| 합친 값이 로컬과 다름 | **갱신 대상** |

이 표는 메타데이터의 판정이다. 카테고리는 따로 판정한다
(`2026-10-03-categories-design.md` 7.6).

"합친 값" 은 칸마다 정한다. 문서가 준 칸은 문서 값, 문서가 주지 않은
칸은 로컬 값이다. 로컬에 행이 없으면 로컬 값은 두 칸 모두 `None` 으로
본다.

예) 로컬 `채널=A · 업로드일=없음`, 문서 `채널=없음 · 업로드일=2026-09-20`
→ 합친 값 `채널=A · 업로드일=2026-09-20` → 갱신.

엣지 케이스.

- **같은 문서를 가리키는 행 둘**은 행마다 따로 판정한다. 둘 다 갱신
  대상일 수 있다.
- **지울 행**은 문서 목록에 없으므로 갱신 판정에 오르지 않는다.
- **미저장 실행**은 `list_exported` 가 돌려주지 않는다. 계획에 오르지
  않는다.
- 갱신 대상의 순서는 입력(`exported`) 순서를 따른다.
- **멱등이다.** 적용한 뒤 같은 문서 목록으로 다시 계획을 세우면 갱신
  대상이 없다. 생성 대상도 마찬가지다 — 새 행이 문서 값을 그대로
  들고 있으므로 다음 계획에서 갱신에 오르지 않는다.
- **수렴.** 로컬 값은 yt-dlp 값의 앞뒤 공백만 뗀 것이고
  (`video_metadata._clean`), 문서의 값은 `one_line` 으로 제어문자를
  지우고 공백을 접은 것이다. 채널명에 겹친 공백이나 제어문자가 있으면
  보통의 저장 뒤 첫 동기화에서 그 행이 한 번 갱신 대상이 되고, 적용
  뒤로는 같아진다. 오류가 아니다.

### 9.2 `apply`

새 카테고리 등록 → 삭제 → 삽입 → 메타데이터 갱신 → 카테고리 교체 순으로
쓰고 **커밋 하나**로 묶는다. 카테고리 등록과 교체는
`2026-10-03-categories-design.md` 7.6 이 다룬다. 어느 쪽이든 실패하면
전부 되돌리고 다시 던지는 구조는 그대로다.

갱신은 `write_metadata(connection, update.run.id,
update.run.outline_id or "", update.metadata)` 로 쓴다. `False` 면
개수에 넣지 않는다. 미리보기와 적용 사이에 그 행이 지워졌거나, ID 가
다른 실행에 다시 쓰였거나(2.5), 다른 탭이 같은 계획을 먼저 적용해 값이
이미 같은 경우다.

`SyncResult` 에 `updated: int = 0` 을 더한다. 기본값을 두어 기존
테스트의 `SyncResult(deleted=…, created=…)` 비교가 그대로 선다.

---

## 10. 화면

### 10.1 `pages/_history_sync.py`

```
▸ Outline 과 동기화
    Outline 컬렉션의 문서 목록과 저장된 이력을 맞춥니다.
    Outline 에 없는 이력은 지우고, 이력에 없는 문서는 새로 만듭니다.
    채널·업로드일은 문서 머리에서 읽어 채웁니다.
    카테고리는 문서 머리에서 읽어 맞추고, 모르는 이름은 새로 등록합니다.
    [ 확인 ]

    ── 확인 후 ──
    지울 이력 2건 · 만들 문서 3건 · 채널·업로드일 갱신 40건 · 카테고리 갱신 5건 · 새 카테고리 2개 · 건너뛴 문서 1건
    **새 카테고리** 경제, 인공지능
    지울 이력      - 제목 · 실행 시각
    만들 문서      - 제목 · 문서 생성 시각 · 영상 URL
    건너뛴 문서    - 제목 · 사유
    [ 적용 ]  [ 취소 ]
```

- 설명 문구에 셋째 문장을 더한다. 넷째 문장(카테고리)과 개수 한 줄의
  `카테고리 갱신 R건 · 새 카테고리 C개`, `**새 카테고리**` 줄은
  `2026-10-03-categories-design.md` 8.5 가 다룬다.
- 개수 한 줄에 `채널·업로드일 갱신 K건` 을 `만들 문서` 와 `건너뛴 문서`
  사이에 넣는다. 갱신 대상의 **목록은 그리지 않는다**(3).
- 갱신만 있어도 적용 버튼이 나온다(`is_empty` 가 거짓이다). 지울 것·
  만들 것·갱신할 것·카테고리 갱신 넷 다 없으면 "이미 맞습니다.
  건너뛴 문서 N건." 만 내고 적용 버튼을 그리지 않는다.
- 결과 문구는 `동기화 완료 · 지움 N건 · 만듦 M건 · 갱신 K건 · 카테고리
  갱신 R건 · 새 카테고리 C개` 이다.

### 10.2 `pages/_digest_materials.py`

- 표의 열은 **문서 제목 · 카테고리 · 채널 · 업로드일 · 시각 · Outline**
  순서다. `_row` 가 `run.metadata` 에서 두 값을 꺼내고, 없으면 빈칸이다.
- 업로드일은 `YYYY-MM-DD` 문자열이라 머리글 정렬이 날짜 순서와 같다.
  날짜 열 형식(`DateColumn`)으로 바꾸지 않는다.
- `widget_key` 함수는 바꾸지 않는다(2.7). 다만 카테고리·채널 필터로
  거른 목록을 받는다.
- 표 위 안내 문구는 고르는 법·상한·정렬·검색을 말한 뒤 "필터를 바꾸면
  고른 재료가 풀립니다." 로 끝나고, 그 위에 카테고리·채널 필터 둘이
  있다(`2026-10-03-categories-design.md` 8.6).

### 10.3 `pages/history.py`

"Outline 에 저장" 버튼의 도움말만 고친다. 지금 문구 "올린 뒤에는
로컬에 링크만 남습니다." 는 이 설계 뒤로 사실이 아니다. "올린 뒤에는
로컬에 링크와 채널·업로드일·카테고리만 남습니다." 로 바꾼다.

저장된 실행을 그리는 `_render_saved` 는 두 값을 보여 주지 않는다(16).

---

## 11. 오류 처리

| 상황 | 처리 |
|---|---|
| 머리 블록에 두 줄이 없음 | 오류 아님. 생성이면 메타데이터 없이 만들고, 기존 행이면 손대지 않는다 |
| 채널 줄이 이상한 모양으로 돌아옴 | 오류 아님. 그 칸을 못 읽은 것으로 친다. 로컬 값은 남는다 |
| 업로드 일자가 날짜로 읽히지 않음 | 위와 같다 |
| 적용 중 SQLite 오류(갱신 포함) | 기존과 같다. 전부 롤백하고 `st.error`, 계획은 남긴다 |
| 갱신할 행이 그사이 지워지거나 ID 가 다시 쓰임 | 오류 아님. 쓰지 않고 개수에도 넣지 않는다 |

사용자 문구가 바뀌는 곳은 10.1 의 설명·개수·결과 문구와 10.3 의
도움말이다.

---

## 12. 테스트

기능마다 실패하는 테스트를 먼저 쓴다. 실제 네트워크는 타지 않는다.

| 파일 | 확인할 것 |
|---|---|
| `tests/core/test_outline_import.py` | `find_metadata`: 두 줄 다 읽음 · 한 줄만 있으면 다른 칸은 `None` · 둘 다 없으면 `None` · 정리본 본문(종류·작성일자)은 `None` · 첫 `---` 뒤의 같은 줄은 무시 · `*`·`+` 글머리표 · 채널명의 `\_`·`\*`·`\[`·`\!` 이스케이프를 걷음 · `2026\-09\-20` 을 날짜로 읽음 · `2026-13-40`·`20260920`·빈 값은 그 칸만 `None` · `- 제목: 채널: X` 는 채널로 읽지 않음 · 같은 라벨이 둘이면 첫 줄 · **첫 줄의 값이 비었거나 날짜가 아니면 뒤의 줄이 멀쩡해도 그 칸은 `None`** / **왕복**: `markdown_export.to_markdown` 이 쓴 문서를 `find_metadata` 가 같은 값으로 읽음 — 라벨 상수가 한쪽만 바뀌면 깨진다 |
| `tests/services/test_run_history.py` | `mark_exported` 가 `run_metadata` 를 **남김**(지금의 `test_mark_exported_deletes_the_local_metadata` 를 뒤집는다) · 답변은 여전히 지움 · 답변 삭제가 실패하면 롤백(기존 테스트 그대로) / `list_runs` 가 메타데이터 행이 있으면 싣고, 없으면 `None` · 답변이 여럿이어도 `answer_count` 가 불지 않음 |
| `tests/services/test_run_history_sync.py` | `list_exported` 가 메타데이터를 싣고 옴 / `insert_exported` 가 `metadata` 가 있으면 `run_metadata` 를 만들고 없으면 만들지 않음(지금의 `test_insert_exported_writes_no_answers` 의 `load_metadata is None` 은 `metadata` 없는 경우로 남는다) · 이미 있는 문서면 아무것도 쓰지 않음 / `write_metadata` 가 행이 없으면 넣고 있으면 덮음 · 값이 이미 같으면 `False` · 문서 ID 가 다르면(ID 를 다시 받은 미저장 실행) `False` 이고 쓰지 않음 · 커밋하지 않음 |
| `tests/services/test_history_sync.py` | `plan`: 생성 대상에 문서 메타데이터가 실림 · 기존 행의 9.1 세 판정 각각 · 칸별 합치기(예시 그대로) · 로컬에 행이 없고 문서가 값을 주면 갱신 · 같은 문서를 가리키는 행 둘을 따로 판정 · 지울 행은 갱신에 오르지 않음 · 갱신만 있으면 `is_empty` 가 거짓 / `apply`: 갱신이 삭제·삽입과 한 커밋 · 갱신 실패 시 삭제·삽입도 롤백 · 낡은 계획의 갱신이 다시 쓰인 ID 의 미저장 실행에 쓰이지 않고 `updated` 에 안 셈 · 같은 계획을 두 번 적용하면 두 번째 `updated` 가 0 / **멱등**: 계획 → 적용 → `list_exported` → 다시 계획하면 `updates == ()` — 갱신 경로와 메타데이터를 실은 생성 경로 각각 |
| `tests/pages/test_history.py` | 개수 한 줄에 갱신 건수가 나옴(지금의 `"지울 이력 1건 · 만들 문서 1건 · 건너뛴 문서 1건"` 단언은 갱신 칸이 들어간 문자열로 바뀐다) · 갱신만 있어도 적용 버튼 · 적용 뒤 결과 문구의 갱신 건수와 DB 의 메타데이터 · 이미 같으면 "이미 맞습니다" |
| `tests/pages/test_digest.py` | 재료 표에 채널·업로드일 열이 값과 함께 나옴 · 메타데이터가 없는 행은 빈칸 · 열 순서 · 실행 ID 가 같고 메타데이터만 다른 두 목록의 `widget_key` 가 같음(2.7) |

화면 테스트는 기존처럼 `monkeypatch.setattr(outline, "list_documents",
…)` 로 목록을 바꿔 끼운다.

작업을 끝내기 전 `.claude/rules/streamlit-implement.md` 의 네 검사를
순서대로 통과한다: `ruff format` → `ruff check --fix` →
`mypy src tests` → `pytest`.

**브라우저 확인**: 저장된 요약본이 있고 메타데이터가 없는 임시 DB 에서
동기화를 확인·적용해 갱신 건수를 보고, 정리본 표에 두 열이 채워지는지
본다. 선택 유지는 **브라우저 탭 둘**로 본다 — 한 탭에서 재료를 고르고,
다른 탭에서 동기화를 적용한 뒤, 첫 탭에서 행 하나를 더 눌러 앞서 고른
재료가 남는지 본다. 한 탭 안에서 이력 화면으로 옮기면 표가 그려지지
않아 Streamlit 이 선택을 버리므로, 한 탭으로는 2.7 을 볼 수 없다.

---

## 13. 건드리는 파일

**수정 — 소스 9**

- `src/notebooklm_st/core/markdown_export.py` — 라벨 상수 둘
- `src/notebooklm_st/core/outline_import.py` — `find_metadata`, 머리
  블록 줄 공유
- `src/notebooklm_st/core/models.py` — `VideoMetadata` 위치,
  `RunSummary.metadata`. 동기화 값 객체(`SyncCreate.metadata`,
  `SyncUpdate`, `SyncPlan.updates`)는 `core/sync_models.py` 에 있다
- `src/notebooklm_st/services/run_history.py` — `SUMMARY_SELECT`,
  `row_to_summary`
- `src/notebooklm_st/services/run_links.py` — `mark_exported`
- `src/notebooklm_st/services/run_history_sync.py` —
  `insert_exported`, `write_metadata`
- `src/notebooklm_st/services/history_sync.py` — `plan`, `apply`,
  `SyncResult`
- `src/notebooklm_st/pages/_history_sync.py` — 설명·개수·결과 문구
- `src/notebooklm_st/pages/_digest_materials.py` — 두 열
- `src/notebooklm_st/pages/history.py` — 저장 버튼 도움말 한 줄(10.3)

**수정 — 테스트 6**: 12 의 표 그대로.

**수정 — 문서**

- `README.md` — 사실이 아니게 되는 두 문장과 동기화 설명을 고친다.
  - 처리 순서의 "Outline 에 올리면 로컬에는 링크만 남음" → "링크와
    채널·업로드일·카테고리만 남음"
  - 사용 순서 6 의 "로컬에는 문서명과 링크만 남고" → "문서명·링크·
    채널·업로드일·카테고리만 남고", 미리보기 목록에 "채널·업로드일
    갱신" 을 더하고, "채널·업로드일은 문서 머리에서 읽어 채우며 줄이 없는
    문서는 빈칸으로 둔다" 와 "올린 직후 한 번 동기화해야 기존 재료가
    채워진다" 를 적는다
- 기존 명세 셋을 이 설계가 끝난 상태로 **통째로 다시 쓴다.**
  - `2026-09-22-outline-storage-design.md` — 저장이 `run_metadata` 를
    남긴다
  - `2026-09-28-history-sync-design.md` — 갱신 대상, 생성 행의
    메타데이터, "기존 행" 결정의 범위
  - `2026-09-23-digest-design.md` — 재료 표의 열, "채널 열을 두지
    않는다" 의 이유가 사라짐

**변경 없음**

- `src/notebooklm_st/services/store.py` — 스키마 그대로
- `src/notebooklm_st/services/outline.py`·`outline_parse.py`·
  `outline_messages.py`
- `src/notebooklm_st/services/video_metadata.py`·`runner.py`·`runs.py`
- `src/notebooklm_st/services/digest.py`·`digest_runner.py`,
  `src/notebooklm_st/pages/digest.py`
- `docker-compose.yml`, `Dockerfile`, `pyproject.toml`

새 의존성은 없다.

---

## 14. 배포와 옮겨 가기

- 스키마가 그대로이므로 **기존 `questions.db` 를 그대로 연다.** 이미지를
  바꾸는 것으로 끝난다.
- 올린 직후에는 기존 재료의 두 칸이 비어 있다. 이력 화면에서 "Outline
  과 동기화" 를 **확인 → 적용** 한 번 하면 채워진다. README 에 적는다.
- 그 뒤로 새로 저장하는 요약본은 동기화 없이 바로 채워진다.

---

## 15. 미검증 가정

- **운영 위키 문서 대부분이 두 줄을 갖는다.** R3 이 R4 보다 먼저라는
  사실에서 추론했다(2.2). 첫 동기화의 갱신 건수가 저장된 요약본 수보다
  크게 적으면 이 가정부터 본다.
- **Outline 이 채널명을 어떻게 재직렬화하는지 미실측.** 역슬래시
  이스케이프는 받는다(6). 채널명에 `*…*`·`_…_` 처럼 짝을 이룬 기호가
  있으면 Outline 이 강조로 읽어 다른 모양으로 돌려줄 수 있고, 그때는
  기호가 빠지거나 남은 채로 읽힌다. 값이 틀려도 표의 한 칸일 뿐이다.
- **업로드 일자 줄은 모양이 바뀌지 않는다.** 숫자와 하이픈뿐이라
  바뀌어도 `\-` 정도로 본다.

---

## 16. 범위 밖

- 이력 화면에 채널·업로드일을 보여 주기
- 줄이 없는 문서를 yt-dlp 로 다시 받아 채우기
- 재료 표를 날짜로 거르기
- Outline 에서 줄을 지운 것을 로컬에 반영하기(지우지 않는다, 3)
- 정리본 문서에 채널·업로드일을 적기
- 동기화 없이 기존 행을 채우는 자동 경로
