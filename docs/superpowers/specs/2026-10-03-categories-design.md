# 카테고리 설계 — 문서에 주제를 달고 정리본 재료를 거르기

- **작성일**: 2026-10-03
- **상태**: 구현 완료 (2026-10-03)
- **대상**: 신규 `core/category_names.py`·`core/material_filter.py`·
  `core/sync_models.py`·`services/categories.py`·
  `services/run_steps.py`·`components/category_picker.py`·
  `pages/category_admin.py`.
  수정 `services/store.py`·`core/models.py`·`core/markdown_export.py`·
  `core/digest_markdown.py`·`core/outline_import.py`·
  `services/run_history.py`·`services/run_history_sync.py`·
  `services/history_sync.py`·`services/channels.py`·`services/runs.py`·
  `services/run_store.py`·`services/runner.py`·`pages/ask.py`·
  `pages/channels.py`·`pages/_channel_check.py`·
  `pages/_channel_enqueue.py`·`pages/_history_sync.py`·
  `pages/_digest_materials.py`·`app.py`·`README.md`·`docs/ONBOARDING.md`.
  `services/outline.py`·`services/outline_parse.py` 는 값 객체를 옮긴
  탓에 import 만 바뀐다(5.3). Outline 호출, 저장 경로
  (`services/run_export.py`·`services/run_links.py`), 정리 파이프라인
  (`services/digest*.py`·`pages/digest.py`), 배포 파일은 건드리지 않는다.
- **범위**: 사용자가 관리하는 **카테고리**를 질의할 때 하나 이상 고르게
  하고, Outline 문서 머리에 적고, 정리본 재료 표에서 카테고리와 채널로
  거르게 한다. 채널마다 기본 카테고리를 둔다.
- **전제**: Outline 1.10.0 이상. 이력 동기화
  (`2026-09-28-history-sync-design.md`)와 같다.

---

## 1. 왜 바꾸는가

이 앱은 요약본과 정리본을 Outline 컬렉션 **하나**에 쌓는다. 주제가 다른
문서가 섞여 쌓이면서, 정리본 재료 표에서 주제가 전혀 맞지 않는 문서를
고르는 일이 생긴다. 표는 문서 제목·채널·업로드일·시각만 보여 주어,
문서의 대체적인 주제를 분간할 단서가 부족하다.

이 설계는 문서마다 **주제 표시(카테고리)** 를 단다. 사람이 카테고리를
미리 등록해 두고, 질의를 넣을 때 하나 이상 고른다. 고른 카테고리는
Outline 문서 머리에 한 줄로 적히고, 정리본 재료 표에 칸으로 나오며,
표 위의 필터로 후보를 좁힌다. 채널 필터도 함께 둔다.

정본은 지금처럼 Outline 문서다. 로컬의 카테고리는 표를 그리고 거르려고
들고 있는 사본이고, DB 를 지운 뒤에는 이력 동기화가 문서에서 읽어
되살린다(`2026-09-30-saved-run-metadata-design.md` 의 채널·업로드일과
같은 원칙).

**성공 기준**

- 카테고리가 하나도 없으면 질의 화면과 채널 화면에서 질의를 넣을 수
  없고, 그 이유와 할 일이 화면에 보인다.
- 카테고리를 고르지 않으면 넣기 버튼이 잠긴다.
- 새로 저장하는 요약본 문서의 머리에 `- 카테고리:` 줄이 있다. 정리본
  문서에는 재료들의 카테고리를 합친 줄이 있다.
- 정리본 재료 표에 카테고리 칸이 있고, 카테고리·채널 필터로 후보가
  줄어든다.
- DB 파일을 지우고 동기화로 되살려도 카테고리가 돌아온다.
- Outline 에서 카테고리 줄을 고친 뒤 동기화하면 로컬이 따라온다.
- 기존 `questions.db` 를 그대로 연다.

---

## 2. 조사로 확인한 사실

### 2.1 Outline 에는 쓸 만한 문서 분류 기능이 없다

- Outline 에는 문서 태그가 없다.
- 최신 API 문서에는 문서별 사용자 정의 속성(`dataAttributes`)이 있다.
  그러나 운영 버전 v1.10.1 소스의 `server/routes/api` 목록에
  `dataAttributes` 가 없고, `documents.create`·`documents.update` 의
  스키마에도 그 필드가 없다. 공개 저장소의 `main` 에도 없다. 클라우드
  전용으로 보인다.

### 2.2 문서는 한 컬렉션, 한 부모 아래에만 놓인다

컬렉션과 상위 문서는 문서 하나에 하나뿐이다. "카테고리를 여러 개
고른다" 는 요구를 Outline 의 위치로는 표현할 수 없다. 그래서 컬렉션은
하나로 두고, 카테고리는 문서 머리의 줄로 적는다.

### 2.3 동기화는 컬렉션 하나만 읽고, 목록에 없는 이력을 지운다

`services/history_sync.plan` 은 문서 목록에 없는 저장된 행을 모두 지울
대상으로 잡는다. 목록은 설정한 컬렉션 하나에서만 온다
(`outline._list_page` 의 `filters`). 카테고리별 컬렉션에 문서를 나눠
두면, 다른 컬렉션의 문서를 가리키는 이력이 동기화 한 번에 지워진다.

### 2.4 하위 문서 방식은 가능하지만 이 설계에는 필요 없다

v1.10.1 의 `documents.create` 는 `parentDocumentId` 를 받고,
`documents.move` 로 기존 문서를 옮길 수 있다. `documents.list` 의
컬렉션 조건은 "컬렉션 ID 가 같은 문서" 라 하위 문서도 함께 돌려준다
(소스 확인). 카테고리별 상위 문서 아래로 정리하는 일은 나중에 **대표
카테고리** 를 정해 얹을 수 있다(14).

### 2.5 문서 일부만 고치는 API 가 있다

v1.10.1 의 `documents.update` 는 `editMode: "patch"` 와 `findText` 를
받는다. 지금 문서를 마크다운으로 직렬화한 글에서 `findText` 가 **처음
나오는 한 곳**만 바꾸고, 나머지 노드는 보존한다. 찾지 못하면 400
(`"The specified text was not found in the document"`)이다.
`documents.update` 에는 별도 요청 한도가 없어 기본값(IP 당 분당
1,000건)을 따른다. `documents.list` 는 분당 100회다.

사용 중인 카테고리의 이름을 바꿀 때 Outline 문서까지 고치려면 이것을
쓴다. 이 설계는 그 대신 **사용 중인 카테고리의 이름 변경과 삭제를
막는다**(3). 나중에 붙여도 문서 머리 줄의 모양은 바뀌지 않는다.

### 2.6 머리 블록을 읽는 규칙이 이미 있다

`core/outline_import` 는 첫 `---` 앞까지를 머리 블록으로 보고, 라벨마다
첫 줄만 읽고(`_first_value`), 글머리표 `-`·`*`·`+` 를 받고, ASCII
문장부호 앞의 역슬래시를 걷는다(`_PUNCTUATION_ESCAPE`). 라벨 글자는
`core/markdown_export` 의 상수를 쓰는 쪽과 읽는 쪽이 함께 쓴다.
카테고리 줄도 이 규칙 위에 얹는다.

### 2.7 마이그레이션이 없다

`services/store.connect` 는 `_EXPECTED_COLUMNS` 와 실제 컬럼을 비교해,
기존 테이블에 칸이 빠졌으면 `StaleSchemaError` 를 낸다. 이때 사람이 할
수 있는 일은 DB 파일을 지우는 것뿐이고, 질문과 이력이 함께 사라진다.
새 **테이블**은 `CREATE TABLE IF NOT EXISTS` 로 생기므로 이 문제가 없다.

### 2.8 이력·재료·저장은 모두 `SUMMARY_SELECT` 를 거친다

- `run_history.list_runs`·`load_run` 과 `run_history_sync.list_exported`
  가 같은 SELECT 머리와 `row_to_summary` 를 쓴다.
- 이력 화면의 저장은 `list_runs` 가 준 요약을 `run_export.save` 에
  넘기고, 자동 저장은 `run_export._upload` 가 `load_run` 으로 다시 읽은
  요약을 넘긴다. 둘 다 그 요약으로 `markdown_export.to_markdown` 을
  부른다.
- 정리본 초안의 `sources` 는 재료 표에서 고른 요약 그대로다.

그래서 `RunSummary` 에 카테고리를 실으면 저장 경로와 정리 경로의 함수
서명을 바꾸지 않고 문서 머리에 쓸 수 있다.

### 2.9 운영 이미지의 SQLite 는 3.40 이다

`Dockerfile` 의 실행 단계는 `python:3.13-slim-bookworm` 이고, 공식
Python 이미지는 Debian bookworm 의 `libsqlite3`(3.40)에 링크된다.
`group_concat(… ORDER BY …)` 는 SQLite 3.44 부터라 쓸 수 없다. 개발
PC 는 3.50 이라 테스트로는 이 차이가 드러나지 않는다. 이름의 순서는
파이썬에서 정한다.

### 2.10 대기열 핸들은 넣는 순간의 값을 쥔다

`runs.RunHandle` 은 질문 객체와 `auto_save` 를 넣는 순간 고정한다.
워커는 영상 정보를 받고(`_fetch_metadata`), 파이프라인을 돌리고, 이력을
남긴 뒤(`_save_history`), 필요하면 자동 저장한다. 카테고리도 넣는
순간 고정하되 **ID 로** 쥔다. 이름은 이력과 문서에 쓸 때 읽는다.

### 2.11 두 파일이 300줄에 닿아 있다

`services/runner.py` 는 300줄, `core/models.py` 는 282줄이다. 규칙
(`.claude/rules/streamlit-implement.md` §2)은 300줄을 넘으면 경계를
따라 나누라고 한다. 이 설계의 추가분은 둘 다 그 선을 넘긴다(5.3, 8.6).

### 2.12 DB 에 기억하는 위젯은 key 와 콜백으로 만든다

key 없는 위젯에 DB 값을 `value` 로 주면, 값을 적는 순간 위젯 ID 가
바뀌어 바로 다음 조작이 버려진다
(`2026-09-30-run-queue-and-auto-save-design.md` §2.8).
맞는 방식은 key 를 주고, 그 키가 세션에 없을 때만
DB 값으로 채우고, `on_change` 콜백이 DB 에 적는 것이다. 다른 화면에
다녀오면 위젯 값이 버려져 DB 값으로 다시 시작한다.

### 2.13 재료 표의 선택은 행 번호이고 key 는 실행 ID 목록이다

`pages/_digest_materials.widget_key` 는 표에 오른 실행 ID 를 이은
문자열에서 key 를 만든다. 필터로 표의 행이 바뀌면 key 가 바뀌고
Streamlit 이 선택을 비운다. 행 번호가 다른 문서를 가리키게 되는 것보다
안전하다.

---

## 3. 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| Outline 구조 | **컬렉션 하나를 유지하고, 문서 머리에 `- 카테고리:` 줄을 적는다** | 여러 카테고리를 위치로 표현할 수 없다(2.2). 카테고리별 컬렉션은 동기화를 다시 짜야 한다(2.3) |
| 개수 | **하나 이상, 여러 개** | 사용자 결정 |
| 고르는 때 | **질의 화면과 채널 화면에서 넣을 때. 고르지 않으면 넣지 못한다** | 사용자 결정. 넣은 뒤에는 바꾸는 화면이 없다 |
| 카테고리가 하나도 없을 때 | **넣는 자리를 그리지 않고 "카테고리 관리 화면에서 먼저 등록하세요" 를 보인다** | 질문이 없을 때와 같은 모양이다. 왜 막혔는지 사람이 안다 |
| 로컬 저장 | **새 테이블 셋**(5.1) | 기존 테이블에 칸을 더하면 DB 를 지워야 한다(2.7) |
| 정본 | **Outline 문서의 머리 줄**. 로컬은 사본이고, 미저장 실행에서만 로컬이 유일하다 | 채널·업로드일과 같은 원칙이다 |
| 이름 규칙 | **공백을 접고 앞뒤를 자른 뒤 1~30자, 글자·숫자·공백과 `- . & + / ( ) ·` 만** | 쉼표는 줄 안의 구분자다. 마크다운 문법 글자(`*`·`_`·`` ` ``·`[`·`~`·`=` …)를 Outline 이 서식으로 읽으면 다시 읽을 때 이름이 바뀐다. 허용 목록이 금지 목록보다 새는 곳이 없다 |
| 같은 이름 | **허용하지 않는다. 대소문자를 구분한다** | 질문 제목과 같은 규칙이다 |
| 사용 중 | **이력 행에 붙어 있거나, 레지스트리의 대기·실행 중 핸들이 쥐고 있으면 사용 중이다** | 이력에 붙은 것은 Outline 문서에 적혔거나 적힐 이름이다. 대기 중인 실행은 아직 이력이 없지만 곧 붙는다 |
| 사용 중일 때 | **이름 변경과 삭제를 막는다. 이력 쪽은 서비스의 검사와 외래키(`RESTRICT`)가 막고, 핸들 쪽은 관리 화면의 레지스트리 판정만 막는다** | 사용자 결정. 바꾸면 이미 저장된 문서의 줄과 어긋난다(2.5). 서비스는 레지스트리를 모른다. 실행 현황에서 숨긴 실행 중 핸들은 레지스트리에 없어 어디서도 막지 못한다(9) |
| 채널 기본값으로만 쓰일 때 | **사용 중이 아니다. 지우면 채널 기본값에서도 빠진다** | 채널 기본값은 로컬 설정일 뿐 문서에 적히지 않는다 |
| 핸들이 쥐는 값 | **카테고리 ID** | 이름을 쥐면 대기 중에 바뀐 이름이 반영되지 않는다(2.10) |
| 이력을 남길 때 없어진 ID | **빼고 남긴다** | 사용 중 판정과 삭제 사이의 경합을 막는 안전망이다. 외래키 오류로 이력 저장이 실패하는 것보다 낫다 |
| 문서 머리 줄 | **`- 카테고리: 경제, 인공지능`. 업로드 일자 줄 다음, 영상 URL 줄 앞. 카테고리가 없으면 줄째 뺀다** | 값이 없는 줄을 빼는 기존 규칙과 같다 |
| 이름의 순서 | **파이썬 기본 문자열 정렬** | 저장·동기화·표가 같은 순서를 쓴다. SQL 로는 정할 수 없다(2.9) |
| 정리본 | **재료들의 카테고리를 합치고 중복을 뺀 줄을 작성일자 다음에 적는다. 없으면 뺀다** | 사용자 결정 |
| 동기화가 읽는 값 | **줄이 없거나 읽을 이름이 하나도 없으면 그 행을 손대지 않는다** | 직렬화가 바뀌어 파싱이 실패할 때 멀쩡한 로컬 값이 한꺼번에 비지 않게 한다(saved-run-metadata §3) |
| 동기화가 모르는 이름 | **자동으로 등록한다. 미리보기에 이름을 보인다** | 사용자 결정. DB 를 새로 만들고 동기화로 되살릴 때 카테고리도 돌아온다 |
| 동기화의 비교 | **이름 집합으로 비교한다** | 순서와 중복은 뜻이 없다 |
| 동기화가 쓰는 기준 | **실행 ID 와 문서 ID 가 둘 다 맞을 때만** | 실행 ID 가 다시 쓰이기 때문이다(history-sync §2.6) |
| 동기화 미리보기 | **카테고리 갱신은 개수만, 새 카테고리는 이름까지** | 갱신은 처음 채울 때 길다. 새 카테고리는 사람이 알아야 할 변화다 |
| 재료 표의 칸 | **문서 제목 · 카테고리 · 채널 · 업로드일 · 시각 · Outline** | 주제가 제목 다음의 고르는 기준이다 |
| 재료 표의 필터 | **카테고리 필터와 채널 필터. 각 필터 안은 하나라도 맞으면, 두 필터 사이는 둘 다 맞아야 남긴다. 비운 필터는 거르지 않는다** | 사용자 결정 |
| 필터의 선택지 | **재료 후보에 실제로 나오는 값만** | 고르면 빈 표가 되는 선택지를 두지 않는다 |
| 필터를 바꾸면 | **고른 재료가 풀린다. 표 위 안내에 적는다** | 2.13. 선택을 이어 가려면 ID 로 옮겨 담아 다시 주입해야 해 이득보다 복잡하다 |
| 채널 기본 카테고리 | **비울 수 있다. 등록 탭과 목록 탭에서 정한다. 목록 탭은 바꾸는 즉시 저장한다** | 사용자 결정. 저장은 2.12 의 방식 |
| 새 영상 확인 탭 | **그 채널의 기본 카테고리로 미리 채운다. 바꿀 수 있고, 바꾼 값은 채널에 저장하지 않는다** | 기본값과 이번 선택을 가른다. 기준일처럼 채널마다 key 를 둔다 |
| 질의 화면의 선택 | **넣은 뒤에도 남긴다. DB 에 기억하지 않는다** | 질문 선택과 같다 |
| 선택 위젯의 값 | **카테고리 ID. 이름은 `format_func` 로 보인다** | 객체를 값으로 쓰면 이름이 바뀐 객체가 선택지와 같지 않게 된다 |
| 기존 문서 | **손대지 않는다. 표에서 빈칸이다** | 사용자 결정. 시험 중인 문서는 지우고 다시 만든다 |
| 문서별 카테고리 수정 | **앱에 두지 않는다. Outline 에서 줄을 고치고 동기화한다** | 사용자 결정. 동기화가 줄을 읽으므로 그것으로 충분하다 |

### 3.1 기각한 안

- **카테고리별 컬렉션** — 여러 카테고리를 표현할 수 없고(2.2), 동기화가
  다른 컬렉션의 이력을 지운다(2.3). 컬렉션 ID 는 `collections.create`
  로 앱이 만들 수 있지만 이 두 문제는 남는다.
- **카테고리별 상위 문서(지금)** — 가능하지만(2.4) 대표 카테고리라는
  새 개념이 필요하다. 지금 문제는 재료 표에서 생기므로 머리 줄로 충분하다.
- **Outline 문서 속성(`dataAttributes`)** — 운영 버전에 없다(2.1).
- **제목 앞에 `[경제]` 붙이기** — 여러 카테고리와 이름 변경에 약하고,
  NotebookLM 이 지은 제목과 섞인다.
- **사용 중 카테고리 이름 변경을 Outline 까지 반영** — `patch` 로
  가능하다(2.5). 그러나 컬렉션 목록 읽기, 문서마다 수정, 진행 표시,
  일부 실패와 다시 시도 화면이 붙는다. 사용자 결정으로 지금은 막는다.
- **`runs` 에 `categories` 칸 추가** — DB 를 지워야 한다(2.7).
- **핸들이 이름이나 `Category` 객체를 쥐기** — 대기 중 이름 변경이
  반영되지 않는다(2.10).
- **NotebookLM 에게 카테고리 고르게 하기** — 영상마다 질의가 하나 늘어
  요청 한도를 더 쓰고, 정확도를 보장할 수 없다.
- **금지 문자 목록** — 쉼표와 알려진 마크다운 글자를 막아도 Outline 이
  서식으로 읽는 글자(`~~`·`==` 등)가 새로 생기면 샌다. 허용 목록을 쓴다.
- **필터를 바꿔도 선택 유지** — 2.13.

---

## 4. 구조

```
카테고리 관리 화면 ── categories (CRUD, 사용 중이면 잠금)
채널 화면 등록·목록 탭 ── channel_categories (기본값)

질의 화면 / 채널 화면 확인 탭
  카테고리 선택(ID, 필수) ─→ runner.enqueue(category_ids=…)
        ↓  RunHandle.category_ids
워커: run_steps.save_history → run_history.save_run
        → runs + answers + run_metadata + run_categories(있는 ID 만)
        ↓
저장(이력 화면 / 자동 저장)
  load_run / list_runs → RunSummary.categories (이름 순)
  markdown_export.to_markdown → "- 카테고리: …" 줄
        ↓
이력 화면 "Outline 과 동기화"
  list_documents() → plan(exported, documents, 알려진 이름)
     ├ creates           : 문서의 카테고리를 싣는다
     ├ category_updates  : 문서 줄과 로컬 집합이 다른 행    (신규)
     ├ new_categories    : 로컬에 없는 이름                (신규)
     └ deletes / updates / skips                          (그대로)
  apply() → 새 카테고리 등록 · 삭제 · 삽입 · 갱신 · 카테고리 교체를 커밋 하나로
        ↓
정리본 화면
  list_exported() → 카테고리·채널 필터 → 재료 표(카테고리 칸)
  정리본 저장 → "- 카테고리: 재료들의 합집합" 줄
```

모듈 경계는 그대로다. 이름 규칙과 줄 읽기는 `core`, DB 는 `services`,
화면은 호출과 렌더만 한다. Outline 호출은 늘지 않는다.

---

## 5. 데이터 모델

### 5.1 스키마 — 새 테이블 셋

```sql
CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_categories (
    run_id      INTEGER NOT NULL REFERENCES runs(id)
                ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id)
                ON DELETE RESTRICT,
    PRIMARY KEY (run_id, category_id)
);

CREATE TABLE IF NOT EXISTS channel_categories (
    channel_pk  INTEGER NOT NULL REFERENCES channels(id)
                ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id)
                ON DELETE CASCADE,
    PRIMARY KEY (channel_pk, category_id)
);
```

- `_SCHEMA` 끝에 셋을 더하고 `_EXPECTED_COLUMNS` 에 세 테이블을 더한다.
  기존 테이블은 바뀌지 않으므로 기존 DB 파일을 그대로 연다.
- `store.connect` 가 커넥션마다 `PRAGMA foreign_keys = ON` 을 켜므로
  `ON DELETE` 가 동작한다. 워커가 여는 커넥션도 같은 함수를 거친다.
- **실행 행을 지우면 연결도 지워진다.** 실행 ID 가 다시 쓰여도 새 실행이
  옛 카테고리를 물려받지 않는다.
- `run_categories` 의 `RESTRICT` 는 안전망이다. 서비스가 이력에서 쓰는
  카테고리의 삭제를 먼저 막고, 검사와 삭제 사이에 이력이 생기면 이것이
  거절한다. 그때 서비스는 트랜잭션을 되돌리고 같은 `ValueError` 로
  바꾼다(7.2).
- 채널을 지우면 기본값 연결도 지워진다. 기본값으로만 쓰인 카테고리를
  지우면 그 연결이 지워진다.

### 5.2 `core/models.py`

- `Category` 를 더한다. `Question`·`Channel` 과 같은 모양이다.

  ```python
  @dataclasses.dataclass(frozen=True, slots=True)
  class Category:
      """사용자가 관리하는 주제 표시."""

      id: int
      name: str
      created_at: str
      updated_at: str
  ```

- `RunSummary` 에 필드를 더한다. 기본값이 있어 기존 생성 코드가
  깨지지 않는다.

  ```python
  categories: tuple[str, ...] = ()
  """붙은 카테고리 이름. 이름 순이다."""
  ```

  클래스 독스트링의 "로컬에는 링크와 영상 메타데이터만 남아 있다" 는
  "로컬에는 링크와 영상 메타데이터, 카테고리만 남아 있다" 가 된다.

### 5.3 `core/sync_models.py` — 동기화 값 객체를 옮긴다

`models.py` 가 5.2 와 동기화 추가분을 받으면 300줄을 넘는다(2.11).
동기화만 쓰는 값 객체 다섯 — `ListedDocument`·`SyncCreate`·`SyncSkip`·
`SyncUpdate`·`SyncPlan` — 을 **내용을 바꾸지 않고** `core/sync_models.py`
로 옮긴다. 이 이동은 기능 변경 없는 별도 커밋이다. 참조하는 곳은
`services/outline.py`·`services/outline_parse.py`·
`services/run_history_sync.py`·`services/history_sync.py`·
`pages/_history_sync.py` 와 테스트 셋이다.

옮긴 뒤 이 설계의 추가분을 얹는다.

- `SyncCreate` 에 `categories: tuple[str, ...] = ()` — 문서 머리에서
  읽은 이름. 줄이 없으면 비어 있다.
- 새 값 객체. `SyncPlan` 이 주석에 쓰므로 그 위에 둔다.

  ```python
  @dataclasses.dataclass(frozen=True, slots=True)
  class SyncCategoryUpdate:
      """동기화가 카테고리를 바꿀 기존 행 한 건."""

      run: models.RunSummary
      categories: tuple[str, ...]
      """문서 머리에서 읽은 이름. 이 집합으로 바꾼다."""
  ```

- `SyncPlan` 에 둘을 더한다.

  ```python
  category_updates: tuple[SyncCategoryUpdate, ...] = ()
  new_categories: tuple[str, ...] = ()
  """로컬에 없어 새로 등록할 이름. 이름 순이다."""
  ```

  `is_empty` 는 `category_updates` 까지 비었을 때만 참이다.
  `new_categories` 는 따로 보지 않는다. 새 이름은 생성 대상이나 카테고리
  갱신 대상에서만 나오기 때문이다. 기존 행이 모르는 이름을 가질 수는
  없으므로, 문서가 모르는 이름을 주면 그 행은 반드시 갱신 대상이다.

### 5.4 `services/runs.py`·`services/run_store.py`

- `RunHandle` 에 `category_ids: tuple[int, ...] = ()` 를 **맨 끝에**
  더한다. 넣는 순간 고정한다(2.10). 핸들을 직접 만드는 테스트가 여럿이라
  기본값이 있어야 하고, 기본값이 있는 필드는 dataclass 에서 맨 끝에
  와야 한다.
- `RunStore.enqueue` 에 `category_ids: tuple[int, ...] = ()` 를 더한다.
  기본값은 `auto_save` 와 같이 테스트가 핸들을 만들 때 쓴다.

---

## 6. `core` 모듈

### 6.1 `core/category_names.py` — 이름 규칙 (신규)

카테고리 이름의 규칙을 한곳에 둔다. 관리 화면(서비스)과 문서 읽기
(`outline_import`)가 같은 규칙을 써야, 앱이 받지 않는 이름이 동기화로
들어오지 않는다.

```python
MAX_LENGTH = 30

def validate(name: str) -> str
def is_valid(name: str) -> bool
def ordered(names: Iterable[str]) -> tuple[str, ...]
def split(value: str) -> tuple[str, ...]
```

- **`validate`** — `markdown_export.one_line` 으로 제어문자를 지우고
  공백을 접는다. 비었으면 `ValueError("카테고리 이름이 비어 있습니다.")`,
  30자를 넘으면 `ValueError("카테고리 이름은 30자까지입니다.")`, 허용하지
  않는 글자가 있으면 `ValueError` 로 쓸 수 있는 글자를 알린다. 통과하면
  다듬은 값을 돌려준다.
- 허용 글자는 유니코드 글자·숫자(`str.isalnum`), 공백, `- . & + / ( ) ·`
  다. 밑줄은 `isalnum` 이 거짓이라 막힌다.
- **`is_valid`** — `validate` 가 예외 없이 돌면 참.
- **`ordered`** — 중복을 빼고 파이썬 기본 정렬로 늘어놓는다(2.9).
- **`split`** — 문서 머리 줄의 값을 이름들로 나눈다. 쉼표로 나누고
  조각마다 `one_line` 을 거친 뒤, 비었거나 `is_valid` 가 거짓인 조각을
  버리고 `ordered` 로 돌려준다.

`core/markdown_export` 를 import 한다. 반대 방향 import 는 없다(6.2).

### 6.2 `core/markdown_export.py` — 머리 줄

```python
CATEGORY_SEPARATOR = ","
CATEGORY_LABEL = "카테고리"

def category_line(names: Sequence[str]) -> str | None
```

- `CATEGORY_SEPARATOR` 는 줄 안에서 이름을 가르는 글자다.
  `category_names` 가 이 글자로 줄을 나누고, 이름에 쓰지 못하게 막는다.
  `category_names` 가 이 모듈을 import 하므로 상수는 이쪽에 둔다.
- `category_line` 은 이름이 없으면 `None` 이다. 있으면 이름을 구분자와
  공백으로 이은 뒤 라벨을 앞에 붙인다. 곧 `- 카테고리: 경제, 인공지능`
  이다. 순서는 받은 그대로다 — 부르는 쪽이 이미 이름 순으로 들고 있다.

  ```python
  if not names:
      return None
  joined = f"{CATEGORY_SEPARATOR} ".join(names)
  return f"- {CATEGORY_LABEL}: {joined}"
  ```
- `_metadata_block` 은 업로드 일자 줄 다음, 영상 URL 줄 앞에
  `category_line(summary.categories)` 를 넣는다. `None` 이면 넣지 않는다.
- 이름은 6.1 의 규칙을 통과한 값이라 다시 다듬지 않는다.

### 6.3 `core/digest_markdown.py` — 정리본 머리 줄

`_metadata_block` 은 `- 작성일자:` 줄 다음에
`markdown_export.category_line(category_names.ordered(이름들))` 을
넣는다. 이름들은 `draft.sources` 의 `categories` 를 모두 이은 것이다.
`None` 이면 넣지 않는다. `- 출처:` 목록은 그대로 그 뒤에 온다.

정리본에는 `영상 URL` 줄이 없어 동기화가 건너뛴다(history-sync §2.3).
이 줄은 Outline 에서 읽는 사람을 위한 표시뿐이다.

### 6.4 `core/outline_import.py` — 줄 읽기

```python
def find_categories(markdown: str) -> tuple[str, ...] | None
```

- `_labeled_line(markdown_export.CATEGORY_LABEL)` 패턴으로
  `_first_value` 를 쓴다. 머리 블록 범위, 글머리표 변형, 역슬래시
  걷기, "라벨이 맞는 첫 줄만 본다" 는 채널 줄과 같다(2.6).
- 걷어 낸 값을 `category_names.split` 으로 나눈다.
- 줄이 없거나 나눈 결과가 비었으면 `None` — **읽지 못한 것**이다.
- `- 제목: 카테고리: X` 처럼 다른 라벨의 값 안의 글자는 줄 머리에서
  라벨을 맞추므로 걸리지 않는다.

### 6.5 `core/material_filter.py` — 재료 거르기 (신규)

```python
def category_options(runs: Sequence[RunSummary]) -> tuple[str, ...]
def channel_options(runs: Sequence[RunSummary]) -> tuple[str, ...]
def filter_runs(
    runs: Sequence[RunSummary],
    categories: Collection[str],
    channels: Collection[str],
) -> list[RunSummary]
```

- `category_options` — 후보들의 카테고리를 모아 `ordered`.
- `channel_options` — 후보들의 `metadata.channel` 중 빈 값이 아닌 것을
  모아 중복을 빼고 정렬.
- `filter_runs` — 받은 순서를 지킨다. `categories` 가 비어 있지 않으면
  카테고리가 하나라도 겹치는 행만, `channels` 가 비어 있지 않으면 채널이
  그 안에 있는 행만 남긴다. 둘 다 주면 둘 다 맞아야 한다. 카테고리가
  없는 행은 카테고리 필터가 있으면 빠지고, 채널이 없는 행은 채널 필터가
  있으면 빠진다.

---

## 7. 저장소

### 7.1 `services/store.py`

5.1 그대로.

### 7.2 `services/categories.py` (신규)

`services/questions.py` 와 같은 모양의 CRUD 다. 화면은 `ValueError` 를
`st.error` 로 보인다.

```python
@dataclasses.dataclass(frozen=True, slots=True)
class CategoryUsage:
    runs: int      # 이 카테고리가 붙은 이력 행 수
    channels: int  # 이 카테고리를 기본값으로 둔 채널 수

def list_categories(connection) -> list[models.Category]       # 이름 순
def add_category(connection, name: str) -> models.Category
def rename_category(connection, category_id: int, name: str) -> None
def delete_category(connection, category_id: int) -> None
def usage(connection, category_id: int) -> CategoryUsage
def ensure(connection, names: Sequence[str]) -> int
```

- `add_category`·`rename_category` 는 `category_names.validate` 를 거친
  값을 쓴다. 같은 이름이 있으면(이름을 바꾸는 자기 자신은 빼고)
  `ValueError(f"'{name}' 카테고리가 이미 있습니다.")`.
- `rename_category`·`delete_category` 는 `usage(...).runs > 0` 이면
  `ValueError` 로 막는다. 문구는 "이력에서 쓰는 카테고리는 이름을
  바꾸거나 지울 수 없습니다." 다. 대기·실행 중인 실행의 판정은
  레지스트리를 아는 화면이 한다(8.1).
- 확인과 쓰기 사이에 다른 탭이나 워커가 끼어들면 제약이 거절한다
  — 등록·이름 변경은 `UNIQUE`, 삭제는 `RESTRICT`(5.1). 세 쓰기는
  `sqlite3.IntegrityError` 를 잡아 `connection.rollback()` 한 뒤 같은
  뜻의 `ValueError`(이미 있음 / 이력에서 쓰는 카테고리)로 바꿔 던진다.
  레거시 트랜잭션 모드는 그때 연 `BEGIN` 을 남기므로, 되돌리지 않으면
  공유 커넥션이 쓰기 잠금을 쥔 채 남아 워커의 이력 저장이 실패한다.
- 이름 변경은 없는 ID 면 `ValueError`, 삭제는 조용히 넘어간다(질문과
  같다).
- `list_categories` 는 `ORDER BY name` 이다. SQLite 의 기본 비교는
  바이트 순이고 UTF-8 에서 코드 포인트 순과 같으므로 6.1 의 정렬과
  같다.
- **`ensure`** 는 동기화가 쓴다. 이름마다
  `INSERT OR IGNORE INTO categories (name, created_at, updated_at)` 로
  넣고 새로 넣은 수를 돌려준다. **커밋하지 않는다** — 트랜잭션은
  `history_sync.apply` 가 소유한다. 이름은 `find_categories` 를 거쳐
  이미 규칙을 통과했다.

### 7.3 `services/run_history.py`

**`SUMMARY_SELECT`** 에 상관 서브쿼리 한 칸을 더한다.

```sql
(SELECT group_concat(c.name, ',')
   FROM run_categories AS rc
   JOIN categories AS c ON c.id = rc.category_id
  WHERE rc.run_id = r.id) AS category_names
```

- 서브쿼리라 답변 조인의 행을 불리지 않는다. `COUNT(a.id)` 와
  `GROUP BY r.id` 는 그대로다.
- 이름에 쉼표가 없으므로(6.1) 쉼표로 이어도 다시 나눌 수 있다.

**`row_to_summary`** 는 `category_names` 가 `NULL` 이면 `()`, 아니면
쉼표로 나눠 `category_names.ordered` 로 싣는다. 순서를 SQL 이 아니라
여기서 정한다(2.9).

**`save_run`** 에 `category_ids: Sequence[int] = ()` 를 더한다. 같은
커밋 안에서 ID 마다

```sql
INSERT OR IGNORE INTO run_categories (run_id, category_id)
SELECT ?, id FROM categories WHERE id = ?
```

를 넣는다. 그사이 지워진 ID 는 `SELECT` 가 빈 결과라 조용히 빠진다(3).
`OR IGNORE` 라 이미 있는 연결은 오류 없이 건너뛴다 — 같은 ID 가 두 번
와도 한 번만 들어간다.

### 7.4 `services/run_history_sync.py`

**`insert_exported`** — 새 행을 넣은 뒤 `create.categories` 의 이름마다

```sql
INSERT OR IGNORE INTO run_categories (run_id, category_id)
SELECT ?, id FROM categories WHERE name = ?
```

를 넣는다. 이름은 `apply` 가 먼저 `ensure` 로 등록해 두었다. 등록되지
않은 이름은 7.3 과 같이 `SELECT` 가 빈 결과라 조용히 빠지고, 이미 있는
연결은 `OR IGNORE` 가 건너뛴다. 이미 있는 문서여서 `None` 을 돌려주는
경우에는 아무것도 쓰지 않는다. 커밋하지 않는 규칙은 그대로다.

**`replace_categories`** 를 더한다.

```python
def replace_categories(
    connection, run_id: int, outline_id: str, names: Sequence[str]
) -> bool
```

- 실행 ID 와 문서 ID 가 **둘 다 맞는 `runs` 행이 없으면** `False` 이고
  쓰지 않는다(`write_metadata` 와 같은 이유).
- 지금 붙은 이름 집합이 `names` 와 같으면 `False` 이고 쓰지 않는다.
- 다르면 그 행의 연결을 모두 지우고 `names` 로 다시 넣은 뒤 `True`.
  다시 넣는 것은 `insert_exported` 와 같은 `INSERT OR IGNORE … SELECT`
  다.
- **커밋하지 않는다.**

`list_exported` 는 바뀌지 않는다. `SUMMARY_SELECT` 를 통해 카테고리를
싣고 온다.

### 7.5 `services/channels.py`

- `add_channel` 에 `category_ids: Sequence[int] = ()` 를 더한다. 같은
  커밋 안에서 `channel_categories` 에 넣는다. 넣는 문장은 7.3 과 같은
  `INSERT OR IGNORE … SELECT … WHERE id = ?` 라, 없는 ID 는 조용히
  빠지고 같은 ID 가 두 번 와도 한 번만 들어간다.
- `default_category_ids(connection, channel_pk) -> tuple[int, ...]` —
  카테고리 ID 순.
- `set_default_categories(connection, channel_pk, category_ids) -> None`
  — 그 채널의 연결을 지우고 같은 문장으로 다시 넣고 커밋한다. 없는
  채널이면 `ValueError`.
- `delete_channel` 은 바뀌지 않는다. 외래키가 연결을 지운다.

### 7.6 `services/history_sync.py`

**`plan`** 은 인자를 하나 더 받는다.

```python
def plan(
    exported: Sequence[models.RunSummary],
    documents: Sequence[sync_models.ListedDocument],
    known_categories: Collection[str] = frozenset(),
) -> sync_models.SyncPlan
```

- 기존 판정(삭제·생성·건너뜀·메타데이터 갱신)은 그대로다.
- **생성 대상**에 `find_categories(document.markdown) or ()` 를 싣는다.
- **카테고리 갱신 대상** — 행과 문서가 모두 있을 때 판정한다.

  | 문서가 준 값 | 판정 |
  |---|---|
  | 읽지 못함(`find_categories` 가 `None`) | 손대지 않음 |
  | 이름 집합이 로컬과 같음 | 손대지 않음 |
  | 이름 집합이 로컬과 다름 | **갱신 대상** |

  같은 문서를 가리키는 행 둘은 따로 판정한다. 순서는 입력(`exported`)
  순서다.
- **`new_categories`** — 생성 대상과 카테고리 갱신 대상의 이름 중
  `known_categories` 에 없는 것을 `ordered` 로.
- **멱등이다.** 적용한 뒤 같은 문서 목록과 새 이름 목록으로 다시
  계획하면 카테고리 갱신도 새 카테고리도 없다.

**`apply`** 는 이 순서로 쓰고 **커밋 하나**로 묶는다. 어느 단계든
실패하면 전부 되돌리고 다시 던진다.

1. `categories.ensure` — 생성 대상과 카테고리 갱신 대상이 가리키는
   이름을 **모두** `ordered` 로 넘긴다. `new_categories` 만 넘기지 않는
   것은 미리보기 때 있던 이름을 그사이 다른 탭이 지웠어도 다시 등록해
   잇기 위해서다. 이미 있는 이름은 `OR IGNORE` 가 건너뛴다
2. 삭제 (그대로)
3. 삽입 — `insert_exported` 가 카테고리까지 잇는다
4. 메타데이터 갱신 (그대로)
5. 카테고리 교체 — `replace_categories`. `False` 면 세지 않는다

`SyncResult` 에 두 칸을 더한다. 기본값을 두어 기존 테스트의 비교가
그대로 선다.

```python
recategorized: int = 0
"""카테고리를 바꾼 행 수."""
categories_added: int = 0
"""새로 등록한 카테고리 수."""
```

`categories_added` 는 `ensure` 가 실제로 넣은 수다. **미리보기와 적용
사이**에 다른 탭이 같은 이름을 먼저 등록했으면 `ensure` 가 그 이름을
건너뛰어 계획의 `new_categories` 수보다 작다. 반대로 미리보기 때 있던
이름을 다른 탭이 지웠으면 그 이름을 다시 넣어 계획보다 크다. 둘 다
오류가 아니다.

### 7.7 `services/runner.py` → `services/run_steps.py`

`runner.py` 는 이미 300줄이다(2.11). 워커 한 건의 두 단계,
`_fetch_metadata` 와 `_save_history` 를 `services/run_steps.py` 의 공개
함수 `fetch_metadata`·`save_history` 로 **내용 그대로** 옮긴다. 이
이동은 기능 변경 없는 별도 커밋이다. 테스트가
`runner.video_metadata` 를 바꿔 끼우는 곳
(`tests/services/test_runner_queue.py`·`test_runner_start.py`)은
`run_steps.video_metadata` 로 바꾼다.

옮긴 뒤 이 설계의 추가분을 얹는다.

- `runner.enqueue` 에 `category_ids: Sequence[int] = ()` 를 더해
  `registry.enqueue` 로 넘긴다. 기본값은 테스트의 기존 호출을 지킨다.
  화면은 늘 넘긴다. 화면 테스트는 화면이 `runner.enqueue` 에 넘긴
  `category_ids` 를 가짜 `runner.enqueue` 로 받아 보고, 핸들이 그 값을
  쥐는지는 대기열·러너 테스트가 본다(11).
- `_work` 는 `run_steps.save_history(…, handle.category_ids, …)` 를
  부르고, `save_history` 는 그 값을 `run_history.save_run` 에 넘긴다.

### 7.8 저장 경로는 바뀌지 않는다

`run_export.save`·`save_automatically`·`_upload`, `run_links`,
`outline` 은 그대로다. 2.8 대로 넘겨받은 요약이 카테고리를 들고 있고,
`to_markdown` 이 그것으로 줄을 쓴다.

---

## 8. 화면

### 8.1 `pages/category_admin.py` (신규)

`app.py` 의 네비게이션에서 "질문 관리" 다음에
`st.Page(category_admin.render, title="카테고리 관리",
url_path="categories")` 로 등록한다.

```
카테고리 관리
  카테고리는 질의할 때 하나 이상 골라야 합니다. Outline 문서 머리에
  적히고, 정리본 재료를 거르는 데 쓰입니다.
  새 카테고리 이름 [__________]   [등록]
  ▸ 경제
      이름 [경제]
      이력 3건 · 채널 1개의 기본 카테고리
      이력에서 쓰는 카테고리라 이름을 바꾸거나 지울 수 없습니다.
      [수정] [삭제]                       (둘 다 잠김)
  ▸ 인공지능
      이름 [인공지능]
      채널 2개의 기본 카테고리
      지우면 채널 2개의 기본 카테고리에서도 빠집니다.
      [수정] [삭제]
```

- 입력은 `max_chars=category_names.MAX_LENGTH` 다.
- 쓰는 곳은 한 줄로 적는다. `이력 N건`·`채널 N개의 기본 카테고리` 이고,
  둘 다 있으면 ` · ` 로 잇고, 둘 다 없으면 "아직 쓰는 곳이 없습니다."
  다. 잠기지 않은 행이 채널 기본값으로 쓰이면 그 아래에 "지우면 채널
  N개의 기본 카테고리에서도 빠집니다." 를 적는다.
- 행마다 `categories.usage` 를 읽고, 레지스트리의 대기·실행 중 핸들
  (`runs.PENDING`)이 그 ID 를 쥐었는지 본다. 둘 중 하나라도 있으면
  이름 칸과 두 버튼을 잠그고 이유를 한 줄 적는다. 이력이 있으면 "이력에서
  쓰는 카테고리라 …", 없으면 "대기 중이거나 실행 중인 질의가 쓰는
  카테고리라 …" 로 적는다.
- 서비스의 `ValueError` 는 `st.error` 로 보인다. 무엇이 무엇을 막는지는
  이렇다.
  - **이력에서 쓰는 카테고리** — 화면이 잠근 뒤 다른 탭에서 이력이
    생기면 서비스의 검사가 막고, 검사와 쓰기 사이에 생기면 외래키
    (`RESTRICT`)가 거절해 서비스가 같은 `ValueError` 로 바꾼다(7.2).
  - **대기·실행 중 핸들이 쥔 카테고리** — 이 화면의 레지스트리 판정만
    막는다. 서비스는 레지스트리를 모른다. 판정 뒤 대기열에 들어간
    실행이 쥔 ID 가 지워지면 이력을 남길 때 빠진다(9).
  - **실행 현황에서 숨긴 실행 중 핸들이 쥔 카테고리** — 막지 않는다.
    숨기면 핸들이 레지스트리에서 빠져 이 화면이 보지 못한다(9).
- 성공하면 `st.rerun()` 한다(질문 관리와 같다).

### 8.2 `pages/ask.py`

```
YouTube 영상 URL [__________________]
질문 선택       [핵심 주장 ×] [요약 ×]
카테고리        [경제 ×]                    ← 신규, 필수
☐ 자동 저장
[실행]
```

- 카테고리 선택은 질의 화면과 채널 화면 세 곳이 함께 쓰므로
  `components/category_picker.py` 로 뗀다. `render(label, category_list,
  key, help_text, on_change=None) -> list[int]` 가 값은 ID, 이름은
  `format_func` 인 `st.multiselect` 를 그린다. 안내 문구 상수
  `NO_CATEGORIES` 와 도움말 상수 `QUERY_HELP` 도 여기 둔다.
  `keep_registered(connection, chosen) -> list[int]` 는 고른 ID 중 지금
  등록된 것만 고른 순서대로 남긴다. 넣기 콜백 둘이 쓴다.
- 질문 선택은 지금처럼 먼저 그린다. 그다음 카테고리를 읽고, 하나도
  없으면 `NO_CATEGORIES` — "카테고리 관리 화면에서 카테고리를 먼저
  등록하세요. 카테고리를 고르지 않으면 질의할 수 없습니다." — 를
  `st.info` 로 보이고 돌아간다. 자동 저장 체크와 실행 버튼은 그리지
  않는다.
- 카테고리 선택은 `category_picker.render("카테고리", …, key=
  "ask_categories", QUERY_HELP)` 다. 도움말은 "Outline 문서 머리에
  적히고 정리본 재료를 거르는 데 씁니다. 하나 이상 고르세요." 다.
- 실행 버튼은 URL·질문·카테고리가 모두 있어야 열린다.
- `_enqueue` 콜백은 누른 순간의 세션 값을 읽고, 비었으면 넣지 않는다.
  카테고리는 `keep_registered` 로 지금 등록된 ID 만 남긴 뒤 본다. 다른
  탭이 고른 카테고리를 지운 뒤 이 탭이 다시 그려지기 전에 누르면 직전
  그림의 버튼이 열려 있어 콜백이 돌기 때문이다. 남은 것이 없으면 넣지
  않고, 다음 그림에서 선택이 비어 보인다. 넣은 뒤 카테고리 선택은 질문
  선택처럼 남긴다.

### 8.3 `pages/channels.py` — 등록 탭과 목록 탭

- **등록 탭** — 카테고리가 하나라도 있으면 기준일 아래에
  `category_picker.render("기본 카테고리", …,
  key="channels_new_categories", …)` 를 그린다. 비워도 된다. `_add` 가 `channels.add_channel(…,
  category_ids=…)` 로 넘긴다. 카테고리가 없으면 그리지 않는다.
- **목록 탭** — 채널 행의 펼침 안, 채널명 칸 아래에 "기본 카테고리"
  선택을 그린다. key 는 `f"channels_default_categories_{channel.id}"`
  다. 2.12 의 방식을 따른다 — 그 키가 세션에 없을 때만
  `channels.default_category_ids` 로 채우고, `on_change` 콜백이
  `channels.set_default_categories` 로 적는다. 카테고리가 없으면 그리지
  않는다.

### 8.4 `pages/_channel_check.py`·`pages/_channel_enqueue.py`

- `_render_found` 는 질문 선택 다음에 카테고리 선택을 그린다. 결과가
  오류나 빈 목록이어도 위젯이 그려져야 고른 값이 남는다(질문과 같다).
- key 는 `f"channels_check_categories_{found.channel_pk}"` 다. 그 키가
  세션에 없을 때만 그 채널의 기본 카테고리(지금 있는 ID 만)로 채운다.
  바꾼 값은 채널에 적지 않는다.
- 카테고리가 하나도 없으면 위젯 대신 8.2 와 같은 안내를 보이고, 넣기
  쪽(자동 저장 체크·대기열 안내·넣기 버튼)을 그리지 않는다. 표는
  그린다. 질문이 없을 때와 같은 모양이다.
- 질문 선택과 카테고리 선택은 `_render_choices` 로 묶어 떼고, 고른
  질문·카테고리 ID·넣기 쪽을 그릴 수 있는지를 화면 전용 값
  `_Choices` 로 돌려준다. `_render_found` 가 40줄을 크게 넘지 않게
  한다.
- `_channel_enqueue.render` 는 카테고리 선택 key 와 지금 고른 값을 더
  받는다. 고른 것이 없으면 "카테고리를 하나 이상 고르세요." 를 보이고
  버튼을 잠근다. 콜백은 누른 순간의 세션 값을 읽고, 질의 화면과 같이
  `keep_registered` 로 지금 등록된 ID 만 남겨 `runner.enqueue(…,
  category_ids=…)` 로 넘긴다. 남은 것이 없으면 넣지 않는다.

### 8.5 `pages/_history_sync.py`

- 설명 문구에 "카테고리는 문서 머리에서 읽어 맞추고, 모르는 이름은 새로
  등록합니다." 를 더한다.
- `_check` 는 `categories.list_categories` 의 이름들을 `plan` 의
  `known_categories` 로 넘긴다.
- 개수 한 줄은 `지울 이력 · 만들 문서 · 채널·업로드일 갱신 · 카테고리
  갱신 K건 · 새 카테고리 C개 · 건너뛴 문서` 순서다.
- 새 카테고리가 있으면 `**새 카테고리** 경제, 인공지능` 을 한 줄로
  그린다. 카테고리 갱신 대상의 목록은 그리지 않는다(3).
- 카테고리 갱신만 있어도 적용 버튼이 나온다(`is_empty` 가 거짓).
- 결과 문구는 `동기화 완료 · 지움 N건 · 만듦 M건 · 갱신 K건 · 카테고리
  갱신 R건 · 새 카테고리 C개` 다.

### 8.6 `pages/_digest_materials.py`

```
재료 선택
  카테고리 [경제 ×]          채널 [슈카월드 ×]
  행 왼쪽 칸을 눌러 고릅니다(최대 N건). … 필터를 바꾸면 고른 재료가
  풀립니다.
  ┌ ☐ │ 문서 제목 │ 카테고리 │ 채널 │ 업로드일 │ 시각 │ Outline ┐
```

- 표 위에 두 선택을 나란히 그린다. key 는 `digest_filter_categories`·
  `digest_filter_channels`, 선택지는 `material_filter.category_options`·
  `channel_options` 다. 선택지가 비면 그 선택은 그리지 않는다.
- 표에는 `material_filter.filter_runs` 가 남긴 행만 오른다. 남은 행이
  없으면 "고른 조건에 맞는 요약본이 없습니다." 를 `st.info` 로 보이고
  빈 선택을 돌려준다.
- `카테고리` 칸은 문서 제목 다음이고, 값은 `", ".join(run.categories)`
  다. 없으면 빈칸이다.
- 선택 행 번호는 **거른 목록**의 위치다. `widget_key` 도 거른 목록으로
  만든다(2.13).
- `pages/digest.py` 는 바뀌지 않는다. 돌려받은 선택이 곧 초안의
  `sources` 이고 카테고리를 들고 있다.

### 8.7 바뀌지 않는 화면

이력 화면(`pages/history.py`)과 실행 현황(`pages/dashboard.py`)은
카테고리를 보이지 않는다(14). 이력 화면은 "Outline 에 저장" 버튼의
도움말 한 줄만 고친다. 지금 문구 "올린 뒤에는 로컬에 링크와
채널·업로드일만 남습니다." 는 카테고리가 빠져 사실이 아니게 되므로
"올린 뒤에는 로컬에 링크와 채널·업로드일·카테고리만 남습니다." 로
바꾼다.

---

## 9. 실패와 엣지

| 상황 | 처리 |
|---|---|
| 카테고리가 하나도 없음 | 질의 화면은 안내 후 돌아가고, 채널 화면은 안내하고 넣기 쪽을 그리지 않는다(표는 보인다) |
| 이름이 비었거나 30자 초과, 허용하지 않는 글자 | `ValueError` → `st.error`. 저장하지 않는다 |
| 같은 이름 | 위와 같다 |
| 이력에서 쓰는 카테고리의 이름 변경·삭제 | 화면이 잠그고 이유를 적는다. 경합으로 버튼이 눌려도 서비스가 `ValueError` 로 막는다 |
| 서비스의 검사와 쓰기 사이에 이력이 생기거나 같은 이름이 등록됨 | `RESTRICT`·`UNIQUE` 가 거절한다. 서비스가 트랜잭션을 되돌리고 같은 `ValueError` 로 바꾼다. 커넥션에 쓰기 트랜잭션이 남지 않는다 |
| 대기·실행 중 핸들이 쥔 카테고리의 이름 변경·삭제 | 관리 화면만 잠그고 이유를 적는다. 서비스는 막지 않는다 |
| 대기 중 실행의 카테고리가 경합으로 지워짐 | 이력을 남길 때 그 ID 를 뺀다. 다 빠지면 카테고리 줄 없이 저장된다 |
| 실행 중인 질의를 실행 현황에서 숨긴 뒤 그 카테고리를 지움 | **알려진 엣지, 막지 않는다.** 숨기면 핸들이 레지스트리에서 빠지고 워커는 계속 돈다. 관리 화면은 그 카테고리를 쓰는 곳이 없다고 보고 잠그지 않는다. 지우면 이력을 남길 때 그 ID 가 빠지고, 그것이 유일한 카테고리였다면 자동 저장 문서가 카테고리 줄 없이 올라간다. 이름 변경은 핸들이 ID 를 쥐므로 해가 없다. Outline 에서 줄을 고쳐 동기화하면 되돌릴 수 있다. 숨기기의 뜻은 이 설계가 바꾸지 않는다. README 에 적는다 |
| 고른 카테고리를 다른 탭이 지운 뒤, 다시 그려지기 전에 넣기를 누름 | 콜백이 지금 등록된 ID 만 남긴다. 남은 것이 없으면 넣지 않고, 다음 그림에서 선택이 비어 보인다 |
| 실행 실패 | 이력이 없으므로 카테고리도 남지 않는다(지금의 실패와 같다) |
| 자동 저장을 건너뛰거나 실패한 실행 | 카테고리는 이력에 남고, 이력 화면에서 저장하면 같은 줄이 적힌다 |
| 문서 머리에 카테고리 줄이 없음 | 생성이면 카테고리 없이 만들고, 기존 행은 손대지 않는다 |
| 줄의 값이 비었거나 모든 이름이 규칙에 맞지 않음 | 읽지 못한 것과 같다 |
| 줄에 규칙에 맞지 않는 이름이 섞임 | 그 이름만 버린다 |
| Outline 에서 이름을 직접 바꿈 | 동기화가 새 이름을 등록하고 연결을 바꾼다. 옛 이름은 다른 이력이 쓰지 않으면 미사용으로 남아 지울 수 있다 |
| 이력을 지워 미사용이 된 카테고리의 이름을 바꿈 | Outline 에 옛 이름의 문서가 남아 있으면, 다음 동기화가 옛 이름을 다시 등록하고 되살린 이력에 잇는다 |
| 동기화 미리보기와 적용 사이에 다른 탭이 같은 이름을 등록함 | 적용이 그 이름을 건너뛰고 잇는다. 새 카테고리 수는 실제로 등록한 수다 |
| 동기화 미리보기 때 있던 이름을 적용 전에 다른 탭이 지움 | 적용이 그 이름을 다시 등록해 잇는다. 새 카테고리 수에 든다 |
| 적용 중 SQLite 오류 | 기존과 같다. 전부 되돌리고 `st.error`, 계획은 남긴다 |
| 갱신할 행이 그사이 지워지거나 ID 가 다시 쓰임 | 쓰지 않고 세지 않는다 |
| 필터 결과가 비었음 | 안내를 보이고 선택은 비어 있다 |
| 필터를 바꿈 | 고른 재료가 풀린다(안내 문구) |
| 채널을 지움 | 기본 카테고리 연결이 함께 지워진다 |

사용자 문구가 새로 생기거나 바뀌는 곳은 8.1~8.6 과 9 의 안내다.

---

## 10. 배포와 옮겨 가기

- 새 테이블만 더하므로 **기존 `questions.db` 를 그대로 연다.**
- 올린 직후에는 카테고리가 없어 질의가 막힌다. 카테고리 관리 화면에서
  먼저 등록한다. README 에 적는다.
- 기존 문서와 이력에는 카테고리가 없다. 사용자 결정으로 손대지 않는다
  (시험 중인 문서는 지우고 다시 만든다).

---

## 11. 테스트

기능마다 실패하는 테스트를 먼저 쓴다. 실제 네트워크는 타지 않는다.

| 파일 | 확인할 것 |
|---|---|
| `tests/core/test_category_names.py` (신규) | `validate`: 앞뒤 공백·겹친 공백·제어문자를 다듬음 · 빈 값 · 30자 통과와 31자 거부 · 쉼표·`*`·`_`·`` ` ``·`[`·`~`·`=` 거부 · 한글·영문·숫자와 `- . & + / ( ) ·` 통과 / `ordered`: 중복 제거와 정렬 / `split`: `"경제, 인공지능"` · 빈 조각과 공백 조각 버림 · 규칙에 맞지 않는 조각만 버림 · 중복 제거 |
| `tests/core/test_markdown_export.py` | `category_line` 이 쉼표와 공백으로 잇고, 이름이 없으면 `None` · 카테고리 줄이 업로드 일자 줄 다음, 영상 URL 줄 앞 · 카테고리가 없으면 줄이 없음 · 메타데이터가 없어도 카테고리 줄은 나옴 |
| `tests/core/test_digest_markdown.py` | 재료들의 카테고리 합집합이 이름 순으로 작성일자 다음 · 겹친 이름은 한 번 · 재료에 카테고리가 하나도 없으면 줄이 없음 |
| `tests/core/test_outline_import.py` | `find_categories`: 줄을 읽음 · `*`·`+` 글머리표 · 역슬래시 이스케이프를 걷음 · 첫 `---` 뒤의 줄은 무시 · 줄이 없으면 `None` · 값이 비었거나 모든 이름이 규칙 밖이면 `None` · 일부만 규칙 밖이면 그것만 버림 · 같은 라벨이 둘이면 첫 줄 · `- 제목: 카테고리: X` 는 카테고리로 읽지 않음 / **왕복**: `markdown_export.to_markdown` 이 쓴 문서를 `find_categories` 가 같은 이름으로 읽음 — 라벨 상수가 한쪽만 바뀌면 깨진다 |
| `tests/core/test_material_filter.py` (신규) | 빈 필터는 그대로 · 카테고리 필터 안은 하나라도 겹치면 · 채널 필터 · 두 필터는 둘 다 · 카테고리 없는 행과 채널 없는 행이 필터에서 빠짐 · 순서 유지 / 두 선택지 함수 |
| `tests/services/test_store.py` | 새 테이블이 없는 기존 DB 를 열어도 `StaleSchemaError` 가 없음 · 실행을 지우면 연결이 지워짐 · 채널을 지우면 기본값 연결이 지워짐 · 이력에 붙은 카테고리를 SQL 로 지우면 `IntegrityError`(안전망) |
| `tests/services/test_categories.py` (신규) | 등록·이름순 목록·이름 변경·삭제 · 같은 이름 거부(자기 자신은 허용) · 규칙 위반 거부 · 이력이 쓰면 이름 변경과 삭제를 거부 · 채널 기본값으로만 쓰이면 지울 수 있고 연결이 사라짐 · `usage` 두 숫자 · `ensure` 가 새 이름만 넣고 수를 돌려주며 커밋하지 않음 · 검사와 삭제 사이에 이력이 생겨 외래키가 거절하면 되돌리고 사용 중 `ValueError`, 커넥션에 트랜잭션이 남지 않음 · 검사와 등록·이름 변경 사이에 같은 이름이 생겨 `UNIQUE` 가 거절해도 같음 |
| `tests/services/test_run_history.py` | `save_run` 이 카테고리를 잇고, 없는 ID 는 뺌 · 요약이 이름 순 카테고리를 실음(`list_runs`·`load_run`) · 카테고리가 여럿이어도 `answer_count` 가 불지 않음 · 지운 실행의 ID 를 다시 받은 새 실행이 카테고리를 물려받지 않음 |
| `tests/services/test_run_history_sync.py` | `insert_exported` 가 이름으로 잇고 이미 있는 문서면 아무것도 안 씀 · `replace_categories` 가 다르면 바꾸고 `True`, 같으면 `False`, 문서 ID 가 다르면 `False` 이고 쓰지 않음 · 커밋하지 않음 · `list_exported` 가 카테고리를 실음 |
| `tests/services/test_history_sync.py` | `plan`: 생성 대상에 카테고리 · 7.6 의 세 판정 · `new_categories` 가 알려진 이름을 빼고 이름 순 · 카테고리 갱신만 있으면 `is_empty` 가 거짓 / `apply`: 새 카테고리 등록과 연결과 교체가 한 커밋 · 교체가 실패하면 앞 단계도 되돌림 · 낡은 계획이 다시 쓰인 ID 의 미저장 실행에 쓰지 않음 · 미리보기 뒤 다른 탭이 같은 이름을 등록해도 실패하지 않고 새 카테고리 수는 실제로 넣은 수 · 미리보기 때 있던 이름이 지워져도 다시 등록해 잇고 수에 듦 / **멱등**: 계획 → 적용 → 다시 계획하면 카테고리 갱신과 새 카테고리가 없음 |
| `tests/services/test_channels.py` | 기본값과 함께 등록 · 기본값 읽기와 바꾸기 · 없는 채널이면 거부 |
| `tests/services/test_run_store.py`·`test_runner_start.py` | 핸들이 `category_ids` 를 쥠 · 끝난 실행의 이력에 카테고리가 붙음 · 자동 저장이 만드는 문서 본문에 카테고리 줄이 있음(가짜 `create_document` 가 받은 본문으로 본다). 옮긴 워커 단계는 러너 테스트가 그대로 덮는다 |
| `tests/services/test_run_export.py` | 이력 화면의 저장(목록이 준 요약을 넘기는 길)도 문서 머리에 카테고리 줄을 쓴다 |
| `tests/pages/test_category_admin.py` (신규) | 등록 · 같은 이름과 규칙 위반의 오류 · 이름 변경 · 삭제 · 이력이 쓰는 카테고리는 이름 칸과 버튼이 잠기고 이유가 보임 · 대기 중 핸들이 쥔 카테고리도 잠김 · 채널 기본값으로만 쓰이면 경고 문구와 함께 지울 수 있음 |
| `tests/pages/test_ask.py` | 카테고리가 없으면 안내만 있고 실행 버튼이 없음 · 카테고리를 고르기 전에는 버튼이 잠김 · 고른 ID 를 `runner.enqueue` 에 넘김(가짜 러너가 받은 값으로 본다) · 넣은 뒤 카테고리 선택이 남음 · 그린 뒤 고른 카테고리가 지워지면 눌러도 넣지 않음 |
| `tests/pages/test_channels.py` | 기본값과 함께 등록 · 목록 탭에서 기본값을 **연달아 두 번** 바꿔도 둘째 값이 DB 에 남음(2.12) · 확인 탭이 채널마다 기본값으로 미리 채움 · 확인 탭에서 바꾼 값이 채널에 적히지 않음 · 카테고리를 고르지 않으면 넣기 버튼이 잠김 · 넣는 영상마다 고른 ID 를 `runner.enqueue` 에 넘김(가짜 러너가 받은 값) · 그린 뒤 고른 카테고리가 지워지면 눌러도 넣지 않음 · 카테고리가 없으면 안내 |
| `tests/pages/test_history.py` | 개수 한 줄에 카테고리 갱신과 새 카테고리 수 · 새 카테고리 이름 줄 · 카테고리 갱신만 있어도 적용 버튼 · 결과 문구와 DB 의 연결 |
| `tests/pages/test_digest.py` | 카테고리 칸이 제목 다음 · 필터가 행을 줄임(하나라도·둘 다) · 결과가 없으면 안내 · 고른 행 번호가 거른 목록을 가리킴 · 저장한 정리본 본문에 합집합 줄 |

화면 테스트는 기존처럼 `monkeypatch` 로 Outline 목록과 러너를 바꿔
끼운다.

작업을 끝내기 전 `.claude/rules/streamlit-implement.md` 의 네 검사를
순서대로 통과한다: `ruff format` → `ruff check --fix` →
`mypy src tests` → `pytest`.

**브라우저 확인**: 빈 임시 DB 로 띄워 질의 화면이 카테고리 안내로 막히는지
보고, 카테고리 둘을 등록한 뒤 영상 하나를 자동 저장으로 돌려 Outline
문서 머리에 줄이 생기는지 본다. Outline 에서 그 줄의 이름 하나를 바꾸고
동기화를 확인·적용해 새 카테고리와 갱신 건수를 본다. 정리본 화면에서
두 필터로 표가 줄어드는지 보고, 정리본을 저장해 합집합 줄을 본다.

---

## 12. 건드리는 파일

**신규 — 소스 7**

- `src/notebooklm_st/core/category_names.py` — 이름 규칙(6.1)
- `src/notebooklm_st/core/material_filter.py` — 재료 거르기(6.5)
- `src/notebooklm_st/core/sync_models.py` — 옮긴 동기화 값 객체와
  추가분(5.3)
- `src/notebooklm_st/services/categories.py` — CRUD 와 `ensure`(7.2)
- `src/notebooklm_st/services/run_steps.py` — 워커 두 단계(7.7)
- `src/notebooklm_st/components/category_picker.py` — 카테고리 선택
  위젯과 안내 문구, 넣기 콜백이 쓰는 `keep_registered`(8.2)
- `src/notebooklm_st/pages/category_admin.py` — 관리 화면(8.1)

**수정 — 소스**

- `services/store.py` — 새 테이블 셋(5.1)
- `core/models.py` — `Category`, `RunSummary.categories`, 동기화 값
  객체를 뺌(5.2·5.3)
- `core/markdown_export.py` — 라벨과 줄(6.2)
- `core/digest_markdown.py` — 합집합 줄(6.3)
- `core/outline_import.py` — `find_categories`(6.4)
- `services/run_history.py` — `SUMMARY_SELECT`·`row_to_summary`·
  `save_run`(7.3)
- `services/run_history_sync.py` — `insert_exported`·
  `replace_categories`, import(7.4)
- `services/history_sync.py` — `plan`·`apply`·`SyncResult`, import(7.6)
- `services/channels.py` — 기본값(7.5)
- `services/runs.py`·`services/run_store.py` — 핸들(5.4)
- `services/runner.py` — 두 단계를 뺌, `category_ids`(7.7)
- `services/outline.py`·`services/outline_parse.py` — import 만(5.3)
- `pages/ask.py`(8.2), `pages/channels.py`(8.3),
  `pages/_channel_check.py`·`pages/_channel_enqueue.py`(8.4),
  `pages/_history_sync.py`(8.5), `pages/_digest_materials.py`(8.6)
- `app.py` — 네비게이션(8.1)
- `pages/history.py` — 저장 버튼 도움말 한 줄(8.7)

**테스트**: 11 의 표 그대로. 신규 넷(`test_category_names`·
`test_material_filter`·`test_categories`·`test_category_admin`).
화면이 하나 늘므로 `tests/test_app.py` 의 독스트링 "여덟 페이지" 는
"아홉 페이지" 가 된다.

**문서**

- `README.md` — 사용 순서에 카테고리 관리를 질의 앞에 넣고, 질의·채널·
  동기화·정리본 항목에 카테고리를 적는다. 올린 직후 카테고리를 먼저
  등록해야 질의할 수 있다는 것과, 실행 현황에서 숨긴 실행 중 질의가
  쓰는 카테고리는 잠기지 않는다는 것(9)을 적는다.
- `docs/ONBOARDING.md` — 모듈 표에 새 모듈과 바뀐 역할.
- 기존 명세 중 이 설계로 사실이 아니게 되는 넷을 이 설계가 끝난 상태로
  **통째로 다시 쓴다.**
  - `2026-09-22-outline-storage-design.md` — 문서 머리 줄
  - `2026-09-28-history-sync-design.md` — 카테고리 갱신·새 카테고리
  - `2026-09-23-digest-design.md` — 재료 표의 칸과 필터, 정리본 머리 줄
  - `2026-09-30-saved-run-metadata-design.md` — 재료 표의 칸, 범위 밖의
    "재료 표를 채널·날짜로 거르기"

**변경 없음**

- `services/run_export.py`·`services/run_links.py`·
  `services/outline_messages.py`
- `services/digest.py`·`services/digest_runner.py`·`pages/digest.py`
- `pages/dashboard.py`
- `docker-compose.yml`·`Dockerfile`·`pyproject.toml`

새 의존성은 없다.

---

## 13. 미검증 가정

- **Outline 이 카테고리 줄을 바꾸지 않고 돌려준다.** 허용 글자에는
  마크다운 문법이 없다고 보았다. `+`·`-`·`.`·`(`·`)` 는 줄 머리가 아닌
  자리라 목록이나 링크로 읽히지 않는다. 다른 모양으로 돌아오면
  `find_categories` 가 이름을 버리고, 그 행은 손대지 않는다(읽지 못함).
- **운영 이미지의 SQLite 는 3.40 이다.** Debian bookworm 패키지 버전에서
  추론했다(2.9). 이 설계는 어느 쪽이든 3.40 에서 도는 SQL 만 쓴다.
- **`st.multiselect` 의 세션 값을 위젯 생성 전에 채우는 방식**이 체크
  상자와 같이 동작한다. 2.12 는 체크 상자로 확인했다. 계획 단계에서
  AppTest 로 연달아 두 번 바꾸는 테스트를 먼저 돌린다(11).

---

## 14. 범위 밖

- 사용 중인 카테고리의 이름 변경을 Outline 문서까지 반영(2.5 의
  `patch` 로 가능)
- 앱 안에서 저장된 문서의 카테고리 고치기
- 카테고리별 상위 문서나 컬렉션으로 Outline 정리(2.4)
- 이력 화면과 실행 현황에 카테고리 보이기
- 기존 문서와 이력에 카테고리 지정
- 필터를 바꿔도 고른 재료 유지
- NotebookLM 이 카테고리를 고르거나 추천
- 질의 화면의 카테고리 선택을 DB 에 기억
