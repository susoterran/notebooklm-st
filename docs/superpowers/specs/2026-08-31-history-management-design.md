# 이력 관리 기능 설계 — 수정·삭제·영상 제목·인용 숨기기

- **작성일**: 2026-08-31
- **상태**: 설계 (구현 계획 수립 전)
- **대상**: 기존 기획서 `2026-08-28-youtube-qa-design.md` 의 이력 화면과 데이터
  모델을 **확장**한다. 실행 모델(`2026-08-28-background-execution-design.md`)은
  그대로 유효하며 건드리지 않는다.
- **범위**: 이력 화면의 네 기능. 실행 현황 화면과 질문 관리 화면은 동작이
  바뀌지 않는다.

---

## 1. 왜 바꾸는가

이력은 지금 **추가 전용(append-only)** 이다. `run_history` 에는 `save_run`,
`list_runs`, `load_run_items` 세 함수뿐이고 `UPDATE`·`DELETE` 문이 하나도
없다. 화면(`pages/history.py`)도 고르고 보여 주기만 한다.

실사용에서 네 가지가 걸렸다.

1. **답변에 잘못된 내용이 섞여도 웹에서 고칠 수 없다.** DB 파일을 직접 여는
   것이 유일한 방법이다.
2. **중복 항목을 지울 수 없다.** 같은 영상을 두 번 돌리면 둘 다 영원히 남는다.
3. **목록에서 어떤 이력인지 알 수 없다.** 라벨이
   `2026-08-28T10:00:00 · dQw4w9WgXcQ · 답변 5건` 이라 11자리 영상 ID 를 보고
   내용을 추측해야 한다.
4. **결과물만 뽑아 쓰기 어렵다.** 본문에 `[1]`, `[2, 3]` 같은 인용 마커가
   박혀 있고, 맨 아래에는 NotebookLM 이 붙인 후속 제안 문단이 따라온다.
   손으로 지워야 한다.

---

## 2. 조사로 확인한 사실

설계의 전제가 되는 값들은 추측이 아니라 실제 코드와 실제 저장 데이터에서
확인했다.

### 2.1 인용 숨기기는 컴포넌트를 고칠 필요가 없다

`components/answer_view.py` 는 이미 이렇게 되어 있다.

```python
if not item.citations:
    return
```

인용이 비어 있으면 expander 를 아예 그리지 않는다. 따라서 "인용 본문 숨기기"는
**표시용 사본의 `citations` 를 비우는 것만으로** 끝난다.

### 2.2 영상 제목은 이미 손에 들어와 있다

`services/nlm.py` 의 파이프라인은 `client.sources.add_url(...)` 의 반환값을
버린다. 그 반환값 `notebooklm._types.sources.Source` 에는

```python
title: str | None = None
```

가 있다. **새 의존성도, 추가 네트워크 호출도, API 키도 필요 없다.**

### 2.3 삭제는 외래키가 대신해 준다

`services/store.py` 의 `connect()` 가 `PRAGMA foreign_keys = ON` 을 켜고,
`answers.run_id` 에 `ON DELETE CASCADE` 가 걸려 있다. `runs` 한 행만 지우면
딸린 `answers` 는 함께 사라진다.

### 2.4 스키마 변경은 기존 DB 를 죽인다

`store.py` 에 명시된 결정이다.

> 이 프로젝트는 마이그레이션을 지원하지 않는다(의도된 결정). 예전 스키마의
> DB 파일은 지우고 새로 만드는 것이 유일한 해법

`_verify_schema()` 가 컬럼이 빠지면 `StaleSchemaError` 를 던진다. 그리고
**그 예외를 잡는 코드가 어디에도 없다.** `session.get_connection()` 을 타고
그대로 올라와 모든 화면에 파이썬 트레이스백이 노출된다.

이번 작업은 기존 `questions.db` 를 폐기하기로 결정했다(실측 `runs` 2행,
`answers` 2행). 마이그레이션 경로는 도입하지 않는다.

### 2.5 필터 규칙은 실제 답변으로 검증했다

저장된 답변 2건에 아래 규칙을 돌려 결과를 확인했다.

```
answer 1: 6477자 → 꼬리절단 6322자 → 마커제거 5894자
answer 2: 6246자 → 꼬리절단 6087자 → 마커제거 5742자
```

- 서로 모양이 다른 두 꼬리가 **둘 다** 잘렸다.
  - `--- / 📊 분석된 … 원하시면 말씀해 주세요.`
  - `--- / 💡 **다음으로 무엇을 하기를 원하시나요?** / 문단`
- 남은 대괄호는 `[추론]` 뿐이다. 의도대로 보존됐다.
- 문장부호가 깨지지 않았다.
  - `결정되며[2, 3], 멀티플은` → `결정되며, 멀티플은`
  - `판단 기준 [1-3]` → `판단 기준`

---

## 3. 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 수정 대상 | **답변 본문(`answers.answer`)만** | 질문 제목·원문은 "무엇을 물어서 이 답이 나왔는가"의 기록이다. 고치면 기록의 신뢰성이 사라진다 |
| 인용 숨기기 적용 범위 | **이력 화면만** | 요청 범위 그대로. 공유 컴포넌트에 플래그를 심지 않으므로 나중에 넓히기 쉽다 |
| 숨김 중 편집 | **차단한다** | 필터된 텍스트를 원본에 덮어쓰는 사고를 원천 차단한다. "결과물 뽑아 쓰기"와 "잘못된 내용 고치기"는 동시에 할 일이 아니다 |
| 꼬리 절단 규칙 | `---` 로 시작하는 **마지막 블록** | 고정 문구로 자르면 `💡` 형태만 잡히고 `📊` 형태를 놓친다 |
| 스키마 전환 | 컬럼 추가 + 기존 DB 폐기 | 쌓인 데이터가 2건뿐이다. 마이그레이션 정책은 바꾸지 않는다 |
| 수정 이력 기록 | **넣지 않는다** | 요청에 없다. 필요해지면 그때 컬럼을 더한다 |

---

## 4. 구조

기능을 공유 컴포넌트에 넣을지 이력 전용으로 뗄지가 유일한 갈림길이었다.
`answer_view.render_items` 를 이력 화면과 실행 현황 화면이 함께 쓰기 때문이다.

**채택: 표시용 변환 + 컴포넌트에 저장 훅 하나.**

- 필터는 `core/` 의 순수 함수로 격리한다. 이번 작업에서 유일하게 휴리스틱인
  부분이므로, Streamlit 없이 단위 테스트로 조일 수 있는 곳에 둔다.
- 이력 페이지가 `AnswerItem` → 표시용 `AnswerItem` 으로 바꿔 넘긴다. 인용
  숨김은 2.1 의 지렛대로 공짜다.
- `render_items` 에 `on_save` 훅 하나만 더한다. 기본값 `None` 이면 현재 동작과
  같으므로 실행 현황 화면은 영향을 받지 않는다.

기각한 안:

- **이력 전용 컴포넌트 신설** — 실행 현황과 완전히 격리되지만 카드 렌더가 두
  벌이 된다. 지금 두 화면의 카드는 "편집 가능" 한 가지만 다르다.
- **페이지에 직접 구현** — `.claude/rules/streamlit-implement.md` 의 "페이지에
  비즈니스 로직을 직접 쓰지 않는다" 와 300줄 제한에 걸린다.

---

## 5. 데이터 모델과 스키마

### 5.1 스키마

`runs` 에 컬럼 하나를 더한다. `answers` 는 그대로다 — `id` 는 이미 있고
읽어오기만 하면 된다.

```sql
CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY,
    url        TEXT NOT NULL,
    video_id   TEXT NOT NULL,
    title      TEXT,              -- 새 컬럼, NULL 허용
    created_at TEXT NOT NULL
);
```

`_EXPECTED_COLUMNS["runs"]` 에 `title` 을 더한다.

`title` 을 NULL 허용으로 두는 이유는 두 가지다. 제목을 못 얻는 실행이 있을 수
있고, 폴백(`video_id`)이 있으므로 화면이 깨지지 않는다.

### 5.2 모델

| 모델 | 변경 | 의미 |
|---|---|---|
| `AnswerItem` | `id: int \| None = None` 을 끝에 추가 | DB 에서 읽어온 항목만 값을 가진다. 파이프라인이 갓 만든 항목은 `None` |
| `RunResult` | `title: str \| None = None` 추가 | 파이프라인 → `save_run` 으로 제목을 나른다 |
| `RunSummary` | `title: str \| None` 추가 | 목록 라벨에 쓴다 |

`AnswerItem.id` 를 `int | None` 으로 두는 것이 이 설계의 안전장치다. 편집
상자는 `id` 가 있을 때만 그려지므로, **실행 현황 화면에 편집 UI 가 새어 나가는
것이 타입 수준에서 막힌다.**

### 5.3 목록 라벨

제목을 앞으로 뺀다. 제목이 없으면 `video_id` 로 폴백한다.

```
현재:  2026-08-28T10:00:00 · dQw4w9WgXcQ · 답변 5건
변경:  차트가 더 오를 것 같아서 따라 샀다면? … · 2026-08-28T10:00:00 · 답변 5건
```

제목이 길면 selectbox 한 줄을 넘기므로 **60자에서 자르고** `…` 를 붙인다.
질문 관리 화면의 `_TITLE_MAX_CHARS` 와 같은 값을 쓴다. 자르기는 라벨을 만드는
자리에서만 하며 저장된 제목은 건드리지 않는다.

---

## 6. 텍스트 필터 — `core/answer_text.py` (신규)

Streamlit 을 import 하지 않는 순수 함수 모듈이다.

### 6.1 꼬리 절단

줄 단위로 훑어 `^\s*---\s*$` 에 맞는 **마지막** 줄을 찾고, 그 줄부터 끝까지
버린다.

- `---` 가 없으면 원본을 그대로 돌려준다.
- 자른 결과가 비면 원본을 유지한다(안전장치). 본문 전체가 사라지는 것보다
  꼬리가 남는 편이 낫다.

### 6.2 마커 제거

```
[ \t]*\[\d+(?:\s*[-,]\s*\d+)*\](?!\()
```

- 앞 공백까지 먹는다: `기준 [1-3]` → `기준`
- 숫자·쉼표·하이픈만 매칭하므로 `[추론]` 은 건드리지 않는다
- `(?!\()` 로 마크다운 링크 `[1](url)` 을 방어한다

### 6.3 숨김의 대상과 대상이 아닌 것

체크박스가 숨기는 것은 셋뿐이다.

- 본문에 박힌 인용 마커 (6.2)
- 본문 맨 아래의 후속 제안 블록 (6.1)
- 인용 본문 expander (2.1)

**`질문 원문` expander 는 숨기지 않는다.** 그것은 인용이 아니라 "무엇을
물었는가"의 기록이고, 요청 범위에 들어 있지 않다. 답변 제목(`st.subheader`)도
그대로 남는다.

### 6.4 순서와 원본 보존

꼬리 절단 → 마커 제거 순으로 적용한다. 꼬리 안의 마커는 어차피 버려진다.

**DB 에는 항상 원문이 들어간다.** 필터는 화면에 그리기 직전에만 적용하며,
저장 경로를 절대 타지 않는다. 이 경계를 지키기 위해 인용 숨김이 켜진 동안에는
편집 상자를 그리지 않는다(3장 결정).

---

## 7. 서비스 계층

### 7.1 `services/run_history.py`

추가:

```python
def update_answer(connection, answer_id: int, answer: str) -> None
def delete_run(connection, run_id: int) -> None
```

- `update_answer` 는 `questions.update_question` 의 규약을 따른다. 빈 값을
  거부하고, `rowcount == 0` 이면 `ValueError` 를 던진다. 답변을 빈 문자열로
  만드는 것은 "고치기"가 아니라 "지우기"이고, 지우기는 이력 단위로 따로 있다.
- `delete_run` 은 멱등이다. `DELETE FROM runs WHERE id = ?` 한 줄이면 딸린
  `answers` 는 외래키가 함께 지운다(2.3).

수정:

- `save_run` — `title` 을 함께 INSERT
- `list_runs` — `title` 을 SELECT 해 `RunSummary` 에 채움
- `load_run_items` — `answers.id` 를 SELECT 해 `AnswerItem.id` 를 채움

### 7.2 `services/nlm.py`

```python
class SourceLike(Protocol):
    title: str | None
```

`SourcesLike.add_url` 의 반환 타입을 `Any` 에서 `SourceLike` 로 좁히고,
`run_pipeline` 이 그 `title` 을 `RunResult` 에 실어 보낸다. "반환된 Source 를
파이프라인이 쓰지 않으므로 모양을 고정하지 않는다"는 현재 주석도 갱신한다.

### 7.3 `services/runner.py` — 변경 없음

`_work` 는 이미 `run_history.save_run(connection, result)` 를 부르고, 제목은
`RunResult` 를 타고 실려 온다.

---

## 8. 화면

### 8.1 `components/answer_view.py`

```python
def render_items(
    items: Sequence[models.AnswerItem],
    *,
    on_save: Callable[[int, str], None] | None = None,
) -> None
```

편집 상자는 **`on_save` 가 있고 `item.id` 도 있을 때만** 그린다. 실행 현황은
`on_save` 를 주지 않고 파이프라인 항목은 `id` 가 `None` 이므로 두 겹으로
막힌다. 기본값에서는 현재 동작과 같다.

위젯에는 `key=f"answer_edit_{item.id}"` 를 명시한다.

### 8.2 `pages/history.py`

```
제목
실행 선택   (제목 · 시각 · 답변 N건)
URL
[ ] 인용 숨기기        ← 켜면 편집이 잠긴다는 안내를 옆에
▸ 이 이력 삭제         ← 접어 둠. 안에 확인 체크박스 + 삭제 버튼
── 답변 카드들 ──
```

- 숨김이 켜지면 `answer_text` 로 거른 표시용 `AnswerItem`(`citations=()`)을
  만들어 넘기고 `on_save=None` 을 준다.
- 삭제는 접은 영역 안에서 확인 체크박스를 거친다. 새 Streamlit API 를 끌어오지
  않는다.
- 삭제 직후 `st.session_state` 에서 `history_selected` 를 지우고 `st.rerun()`
  한다. 지우지 않으면 selectbox 가 사라진 객체를 가리킨다.

세션 키는 모듈 상수로 정의한다: `_SELECTED_KEY`, `_HIDE_CITATIONS_KEY`,
`_DELETE_CONFIRM_KEY`.

### 8.3 `components/schema_gate.py` (신규)

`auth_gate` 와 대칭인 게이트다. `app.py` 가 `auth_gate.render()` 앞에서
부른다.

`store.StaleSchemaError` 를 잡아 `st.error(str(error))` 로 보여 주고
`st.stop()` 한다. 예외 메시지가 이미 파일 경로와 "이 파일을 지우고 다시
실행하세요"를 담고 있으므로 그대로 쓴다.

이 게이트가 없으면 스키마를 바꾸는 순간 사용자는 모든 화면에서 날것의
트레이스백을 보게 된다(2.4).

---

## 9. 테스트

버그 수정이 아니라 기능 추가이므로, 각 단위마다 실패하는 테스트를 먼저 쓴다.

| 파일 | 확인할 것 |
|---|---|
| `tests/core/test_answer_text.py` (신규) | `[1]`·`[2, 3]`·`[1-3]` 제거 / **`[추론]` 보존** / `[1](url)` 링크 방어 / 마지막 `---` 부터 절단 / `---` 없으면 원본 / 절단 결과가 비면 원본 유지 |
| `tests/services/test_run_history.py` | `update_answer` 성공·빈값·없는 ID / `delete_run` 이 **`answers` 까지 지우는지** / `title` 저장·조회 / `load_run_items` 가 `id` 를 채우는지 |
| `tests/services/test_nlm.py` | 가짜 `Source` 의 `title` 이 `RunResult` 에 실리는지 / 제목이 없으면 `None` |
| `tests/services/test_store.py` | `title` 없는 DB 가 `StaleSchemaError` 를 내는지 (기존 패턴 재사용) |
| `tests/test_components.py` | **`on_save` 없으면 편집 상자가 없다** (실행 현황 무영향 회귀) / `on_save` + `id` 면 `text_area` 가 생긴다 |
| `tests/pages/test_history.py` | 체크박스를 켜면 마커·인용 expander·편집 상자가 사라진다 / 삭제 버튼이 실제로 지운다 / 제목이 라벨에 쓰인다 |

기존 `app_db` fixture 를 그대로 쓴다.

작업을 끝내기 전 `.claude/rules/streamlit-implement.md` 의 4종 검사를 순서대로
통과해야 한다: `ruff format` → `ruff check --fix` → `mypy src tests` →
`pytest`.

---

## 10. 건드리는 파일

**신규 2**

- `src/notebooklm_st/core/answer_text.py`
- `src/notebooklm_st/components/schema_gate.py`

**수정 7**

- `src/notebooklm_st/core/models.py`
- `src/notebooklm_st/services/store.py`
- `src/notebooklm_st/services/run_history.py`
- `src/notebooklm_st/services/nlm.py`
- `src/notebooklm_st/components/answer_view.py`
- `src/notebooklm_st/pages/history.py`
- `src/notebooklm_st/app.py`

**변경 없음**

- `src/notebooklm_st/services/runner.py`
- `src/notebooklm_st/services/runs.py`
- `src/notebooklm_st/components/run_progress.py`

---

## 11. 미검증 가정

유튜브 소스에서 `Source.title` 이 **실제로 영상 제목인지**는 실제 질의를 한 번
돌려야 확인된다. 구현 중 확인하고, 다른 값이면 그 자리에서 보고한다.

다른 값이더라도 폴백(`video_id`)이 동작하므로 화면이 깨지지는 않는다.

---

## 12. 범위 밖

- 마이그레이션 경로 도입
- 수정 이력(누가·언제 고쳤는지) 기록
- 실행 현황 화면의 인용 숨기기
- 질문 제목·원문·인용 본문의 편집
- 이력 검색·필터·정렬
