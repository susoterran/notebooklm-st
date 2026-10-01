# 채널 신규 영상 표 설계 — 골라서 한 번에 대기열에 넣기

- **작성일**: 2026-10-01
- **상태**: 구현 계획 수립 (계획:
  `docs/superpowers/plans/2026-10-01-channel-video-table.md`)
- **대상**: 신규 `pages/_channel_videos.py`·`pages/_channel_enqueue.py`·
  `components/auto_save_toggle.py`·`components/queue_notice.py`,
  수정 `pages/_channel_check.py`·`pages/ask.py`·
  `services/run_store.py`(독스트링 한 줄)·`README.md`·
  `docs/ONBOARDING.md`. 러너·레지스트리의 동작(`services/runner.py`·
  `services/run_registry.py`·`services/run_store.py`·
  `services/runs.py`), 피드·채널 저장소(`services/channel_feed.py`·
  `services/channels.py`·`services/channel_lookup.py`), 신규 판정
  (`core/new_videos.py`), 설정 저장소(`services/settings.py`), 스키마
  (`services/store.py`), 배포 파일(`docker-compose.yml`·`Dockerfile`·
  `pyproject.toml`)은 건드리지 않는다.
- **범위**: 채널 화면 "새 영상 확인" 탭의 신규 목록. (1) 한 줄씩
  그리던 목록을 표로 바꾸고, (2) 표에서 여러 영상을 골라 한 번에
  질의 대기열에 넣고, (3) 질의 화면의 자동 저장 설정을 함께 쓴다.
- **전제**: Streamlit 1.64(`2026-09-30-run-queue-and-auto-save-design.md`
  §2.8). 대기열·자동 저장이 이미 들어가 있다.

---

## 1. 왜 바꾸는가

채널의 새 영상을 요약하려면 지금은 한 건씩 돌아와야 한다. 영상마다
`[요약]` 버튼이 있지만 하나를 누르면 그 실행이 끝날 때까지 나머지
버튼이 모두 잠긴다(2.1). 새 영상이 다섯 건이면 화면을 다섯 번 다시
찾아와 눌러야 하고, 끝난 요약은 이력 화면에서 하나씩 저장해야 한다.

질의 화면은 이미 대기열에 넣고 떠나는 흐름이다. 채널 화면만 "비어
있을 때 한 건" 에 묶여 있다. 채널 화면을 만들 때는 사람이 한 건씩
시작하는 흐름으로 충분하다고 보았지만, 대기열이 생긴 뒤에는 그 제약이
지키는 것이 없다. NotebookLM 에는 여전히 워커 하나가 한 번에 하나만
붙는다.

목록 모양도 문제다. 한 줄이 "제목 링크 · 시각" 과 버튼이라 머리글이
없고 칸이 맞지 않는다.

이 설계는 세 가지를 한다.

- 신규 목록을 **표**로 바꾼다. 행을 체크해 고른다.
- 고른 영상을 **버튼 하나로 대기열에** 넣는다. 앞선 질의가 있어도,
  정리본을 작성 중이어도, 대기열이 멈춰 있어도 넣는다. 질의 화면과
  같은 규칙이다.
- 질의 화면의 **자동 저장** 체크를 채널 화면에도 둔다. 설정은 하나다.

**성공 기준**

- 새 영상 n건을 체크하고 버튼을 한 번 누르면 실행 현황 표에 n건이
  대기로 나타나고 차례로 돈다.
- 자동 저장을 켜 둔 채 넣으면 끝난 실행이 이력 화면을 거치지 않고
  Outline 에 올라간다.
- 이미 대기 중이거나 실행 중인 영상은 다시 들어가지 않는다.
- 질의 화면의 동작과 문구는 하나도 바뀌지 않는다.

---

## 2. 조사로 확인한 사실

### 2.1 지금은 한 줄에 한 건, 한 번에 한 건이다

- `_channel_check._render_entry` 가 영상마다 `st.columns([4, 1])` 한
  줄을 그린다. 왼쪽은 `[제목](URL) · 업로드 시각` 마크다운, 오른쪽은
  `[요약]` 버튼이나 "실행 중" 캡션이다.
- `_blocked_reason` 은 넷 중 하나라도 참이면 모든 `[요약]` 을 잠근다 —
  `active_count() > 0`, `paused_reason()` 있음, 정리본 실행 중, 질문
  미선택.
- 시작한 영상은 세션의 `_STARTED_KEY` 집합에 적고 그 줄에 "실행
  중" 을 쓴다. 실행이 끝나 `runs` 에 들어가기 전까지 목록에서 빠지지
  않으므로 이 집합이 같은 영상을 두 번 시작하는 것을 막는다.
- 제목은 `labels.shorten` 으로 줄일 뿐 마크다운 이스케이프를 하지
  않는다. 제목에 `[`·`]`·`$` 가 있으면 링크가 깨질 수 있다. 실행
  현황 표는 `run_progress._escape` 로 이 문제를 막는다.

### 2.2 러너 입구는 이미 여러 건과 자동 저장을 받는다

`runner.enqueue(registry, url, questions, db_path, auto_save,
is_blocked)` 는 대기열 끝에 넣고, 도는 워커가 없으면 띄운 뒤 즉시
반환한다. 여러 번 부르면 첫 호출이 워커를 띄우고 나머지는 줄만 선다.
대기열 설계 §15 가 "채널 화면의 대기열·자동 저장 — 나중에 붙인다.
러너 입구 `enqueue` 가 이미 `auto_save` 를 받는다" 로 남겨 둔 자리다.
러너·레지스트리의 동작은 바꿀 것이 없다.

`run_store.RunStore.enqueue` 의 `auto_save` 독스트링은 "사람이 저장하는
입구(채널 화면)는 기본값을 쓴다" 고 적는다. 소스에서 이 메서드를 부르는
곳은 `runner.enqueue` 하나이고 늘 값을 넘긴다. 기본값을 쓰는 것은
핸들을 만드는 테스트뿐이다.

### 2.3 표의 선택은 원래 목록의 위치로 온다

`st.dataframe(..., on_select="rerun", selection_mode="multi-row")` 은
고른 행을 **원래 데이터의 위치 번호**로 돌려준다. 머리글을 눌러
정렬해도 번호는 원래 순서 기준이다(Streamlit 문서 "Row selections are
returned by positional index"). 정리본 재료 표에서 실제 브라우저로
정렬 뒤 선택을 확인했다.

위치 번호라서 목록이 바뀌면 같은 번호가 다른 행을 가리킨다. 재료 표는
key 를 목록의 ID 구성에서 만들어, 목록이 바뀌면 새 표로 보고 선택을
비우게 한다(`_digest_materials.widget_key`).

### 2.4 표는 행마다 선택을 막지 못한다

`st.dataframe` 의 행 선택에는 특정 행을 고르지 못하게 하는 옵션이 없다.
이미 대기열에 있는 영상도 체크된다. 넣는 순간 거르고 알리는 수밖에
없다.

### 2.5 AppTest 는 표를 클릭하지 못한다

정리본 테스트의 `select_rows` 는 표의 key 에 `{"selection": {"rows":
[...], "columns": [], "cells": []}}` 를 세션 상태로 넣어 선택을
흉내 낸다. 선택은 바로 다음 실행 한 번에만 반영된다. AppTest 는 직전
실행에서 잠긴 버튼을 누르지 못하게 막으므로, 한 번 골라 버튼을 풀고
누르는 실행에서 다시 고른다. 채널 화면 테스트도 같은 방법을 쓴다.

### 2.6 레지스트리에서 영상의 상태를 읽을 수 있다

- `registry.list_all()` 은 진행 중 → 대기 중(넣은 순서) → 끝난 것
  (최근 것부터) 순서의 복사본이다. 그래서 같은 영상의 핸들이 여럿이면
  **처음 만나는 것**이 지금 가장 의미 있는 상태다.
- 상태는 `queued`·`running`·`done`·`failed` 넷이다(`runs.RunStatus`).
- 대기 항목 취소(`registry.cancel`)와 실행 현황의 숨기기·지우기
  (`run_store.discard`·`discard_finished`)는 핸들을 목록에서 뺀다.
- `registry.is_pending(video_id)` 는 그 영상의 `queued`·`running`
  핸들이 있는지 본다. 질의 화면이 같은 영상을 두 번 넣지 않으려고
  쓴다.
- 실행 현황에서 **진행 중인 실행을 숨기면** 핸들이 빠지므로
  `is_pending` 이 거짓이 된다. 그 사이 같은 영상을 다시 넣을 수 있다.
  질의 화면에도 있는 한계다(→ 13).

### 2.7 자동 저장 체크는 화면마다 key 를 달리 해도 설정 하나를 쓴다

질의 화면의 `_render_auto_save` 는 세션에 key 가 없을 때만 DB 값
(`settings.auto_save`)으로 채우고, 사람이 바꿀 때만 `on_change` 콜백이
DB 에 적는다. 다른 화면에 다녀오면 위젯 값이 버려지므로 다시 DB 값으로
시작한다. key 없는 체크에 DB 값을 초기값으로 주면 DB 에 적는 순간 위젯
ID 가 바뀌어 다음 조작이 버려진다 — 그래서 이 모양이다.

두 화면이 이 방식을 각자의 key 로 쓰면, 한쪽에서 바꾼 값이 DB 에 적히고
다른 쪽은 열릴 때 DB 에서 읽는다. 같은 위젯 key 를 두 화면에 쓰지
않는다는 작성 규칙(`.claude/rules/streamlit-implement.md` §3)과도
맞는다.

### 2.8 표는 15행을 넘지 않는다

피드는 최신 15건까지만 준다(`channel_feed.fetch`). 신규는 그중 기준일
이후이고 아직 요약하지 않은 것이므로 표는 많아야 15행이다. 정렬·검색은
덤이고, 고르기 쉬운 모양이 핵심이다.

### 2.9 버튼 콜백에서 표 선택을 읽을 수 있다

넣기 버튼의 `on_click` 콜백에서 `st.session_state[표 key]` 의
`selection.rows` 로 표에서 고른 행을 읽는다. AppTest 는 주입한 값을
읽을 뿐이라 증거가 되지 않으므로, 실제 브라우저(Streamlit 1.64,
1920×950)에서 가짜 피드·가짜 파이프라인으로 확인했다(2026-10-01).

- 셋째 줄을 먼저, 첫째 줄을 나중에 고르고 넣었더니 첫째 줄 영상이
  먼저 시작하고 셋째 줄 영상이 대기로 섰다. 누른 순서가 아니라 목록
  순서다.
- 넣은 뒤 버튼이 `(0건)` 으로 돌아오고 체크가 모두 풀렸다.
- 실행 중인 영상과 새 영상을 함께 고르자 새 영상만 들어가고 결과
  끝에 "이미 대기 중이거나 실행 중인 1건은 뺐습니다." 가 붙었다.
- 표의 상태 칸이 "실행 중"·"대기 중" 을 보였고, 대괄호가 든 제목이
  글자 그대로 보였다.

### 2.10 확인 탭 한 파일에 넣기까지 두면 300줄을 넘는다

표를 `pages/_channel_videos.py` 로 떼어도, 넣기 버튼·콜백·결과
문구를 `pages/_channel_check.py` 에 두면 323줄이 된다(예행 실측). 한
파일이 300줄을 넘으면 쪼개는 것이 이 저장소의 규약이다
(`.claude/rules/streamlit-implement.md` §2).

---

## 3. 설계 결정

| 결정 | 이유 |
| --- | --- |
| 표는 **`st.dataframe` 다중 행 선택** | "여러 개 골라 한 번에" 라는 조작을 정리본 재료 표와 같게 한다. 사람이 익힐 고르는 방식이 하나다 |
| 열은 **제목 · 업로드일 · 상태 · 영상(링크)** | 제목과 업로드일이 고르는 기준이다. 채널 이름은 표 위 소제목에 한 번 적는다 |
| 고른 영상을 **목록 순서(최신 먼저)로** 넣는다 | 표의 기본 순서와 같아 실행 현황의 대기 순서가 예상과 맞는다. 정렬해도 바뀌지 않는다(2.3) |
| **잠그지 않고 넣는다** — 앞선 질의, 정리본 작성, 멈춘 대기열 모두 | 질의 화면과 같은 규칙이다. 언제 도는지는 안내 문구로 알린다. 한 번에 하나는 워커가 지킨다 |
| **대기·실행 중인 영상만 건너뛴다** | `is_pending` 기준으로 질의 화면과 같다. 끝났거나 실패한 영상은 다시 넣을 수 있다 — 실패한 영상을 다시 돌리는 길이다 |
| 자동 저장은 **질의 화면과 설정 하나** | 여러 건을 넣고 이력에서 하나씩 저장하는 수고를 없앤다. 설정이 둘이면 어느 쪽이 적용됐는지 헷갈린다(2.7) |
| 상태 열은 **레지스트리에서 읽는다** | 세션 집합(`_STARTED_KEY`)은 취소·실패를 모른다. 레지스트리는 취소하면 빈칸으로, 실패하면 "실패" 로 돌아온다(2.6) |
| 넣은 뒤 **선택을 비운다** | 같은 영상을 두 번 넣는 클릭을 막는다. 표 key 에 넣기 횟수를 섞어 새 표로 그린다(2.3) |
| 넣는 일은 **버튼의 `on_click` 콜백** | 질의 화면과 같다. 콜백은 재실행 전에 돌아 바뀐 key·상태·결과 문구가 다음 그림에 바로 보인다. `st.rerun()` 이 필요 없다(2.9) |
| 넣기는 **`pages/_channel_enqueue.py`** 로 뗀다 | 확인 탭 한 파일이 300줄을 넘는다(2.10). 버튼·콜백·결과 문구는 넣기 한 덩어리라 함께 떼어도 경계가 깔끔하다 |
| 공유할 것은 **`components/` 로 뗀다** | 자동 저장 체크와 대기열 안내를 두 화면이 똑같이 그려야 한다. 복사하면 문구가 어긋난다 |

### 3.1 기각한 안

- **`st.columns` 행 + 행마다 체크박스** — 대기 중인 영상의 체크를
  비활성으로 그릴 수 있고 AppTest 로 클릭까지 시험할 수 있다. 하지만
  "골라서 한 번에" 를 정리본 화면과 다르게 하게 되고, 표 모양을 손으로
  맞춰야 한다.
- **`st.data_editor` 체크박스 열** — 선택이 값으로 와 위치 번호 문제는
  없지만 편집 위젯이라 제목 칸까지 고칠 수 있는 것처럼 보인다. 이 앱에서
  쓰는 곳도 없다.
- **행마다 `[요약]` 버튼을 남긴 표** — 한 건씩 넣는 것은 여러 건을 고르는
  것의 특수한 경우다. 두 길을 두면 버튼이 15개 늘어날 뿐이다.
- **채널 화면 전용 자동 저장 설정** — 화면마다 다르게 쓸 수 있지만
  설정이 둘이 되고, 사람이 어느 쪽을 켰는지 기억해야 한다.
- **채널 화면은 계속 수동 저장** — 여러 건을 넣을수록 이력 화면의 저장
  클릭이 늘어 이 설계의 이득이 반으로 준다.
- **끝난 영상도 건너뛰기** — 실수로 다시 요약하는 것은 막지만, 실패한
  영상만 다시 넣을 수 있게 되어 기준이 질의 화면과 갈린다. 상태 열이
  "끝남" 을 보여 주므로 사람이 알아본다.
- **잠금 유지(비어 있을 때만 넣기)** — 한 번에 여러 건을 넣는 순간 이미
  "비어 있을 때만" 이 아니다. 잠금을 남길 이유가 없다.
- **넣기를 `_channel_videos.py` 에 합치기** — 표 모듈이 300줄 가까이로
  커지고, "무엇을 보여 주나" 와 "무엇을 넣나" 가 한 파일에 섞인다.

---

## 4. 구조

| 파일 | 할 일 |
| --- | --- |
| `components/auto_save_toggle.py`(신규) | 자동 저장 체크. `ask.py` 의 `_render_auto_save`·`_remember_auto_save`·도움말을 옮기고 위젯 key 를 인자로 받는다 |
| `components/queue_notice.py`(신규) | 대기열 안내 세 줄, 앞선 질의 수, 넣은 뒤 결과 문구. `ask.py` 의 `_count_ahead`·`_enqueued_text` 와 안내 세 줄을 옮긴다 |
| `pages/_channel_videos.py`(신규) | 신규 영상 표. 행 만들기, 상태 라벨, 고른 행을 영상으로 옮기기, 표 key. 고른 영상을 돌려준다 |
| `pages/_channel_enqueue.py`(신규) | 넣기. 질문 안내·버튼·결과 문구를 그리고, 버튼 콜백이 고른 영상을 대기열에 넣는다. 넣기 횟수를 쥔다 |
| `pages/_channel_check.py` | `_render_found` 를 위 넷으로 다시 짠다. `_render_entry`·`_STARTED_KEY`·`_blocked_reason` 을 지운다 |
| `pages/ask.py` | 옮긴 함수를 부르게만 바꾼다. 동작·문구·위젯 key 는 그대로다 |
| `services/run_store.py` | `enqueue` 독스트링의 `auto_save` 한 줄을 사실에 맞춘다(2.2) |

```
pages/_channel_check.py ──┬─ components/auto_save_toggle.py ── services/settings·outline
                          ├─ components/queue_notice.py ── services/runs
                          ├─ pages/_channel_videos.py ── services/runs (상태 이름)
                          └─ pages/_channel_enqueue.py ──┬─ pages/_channel_videos.py
                                                          ├─ components/queue_notice.py
                                                          └─ services/runner.enqueue
pages/ask.py ─────────────┬─ components/auto_save_toggle.py
                          └─ components/queue_notice.py
```

---

## 5. `components/auto_save_toggle.py`

```python
HELP = (
    "켜면 답변을 받은 뒤 인용을 빼고 곧바로 Outline 에 올립니다."
    " 제목이 없거나 답변 일부가 실패하면 올리지 않고 이력에 미저장으로"
    " 남깁니다."
)


def render(connection: sqlite3.Connection, key: str, locked_key: str) -> bool:
    """자동 저장 체크를 그리고, 넣을 실행에 줄 값을 돌려준다."""
```

- 본문은 `ask._render_auto_save` 를 그대로 옮긴다. 바뀌는 것은 위젯
  key 두 개를 인자로 받는 것뿐이다.
  - Outline 설정이 없으면 `locked_key` 로 꺼진 채 잠긴 체크와 캡션
    "Outline 연결이 설정되지 않아 자동 저장을 쓸 수 없습니다." 를 그리고
    거짓을 돌려준다. DB 값은 건드리지 않는다.
  - 있으면 `key` 가 세션에 없을 때만 `settings.auto_save` 로 채우고,
    `on_change` 콜백이 `settings.set_auto_save` 로 적는다.
- 질의 화면은 지금 key(`ask_auto_save`·`ask_auto_save_locked`)를
  그대로 넘긴다. 채널 화면은 `channels_auto_save`·
  `channels_auto_save_locked` 를 넘긴다.

---

## 6. `components/queue_notice.py`

```python
def count_ahead(registry: run_registry.RunRegistry) -> int:
    """지금 넣으면 앞에 설 질의 수. 멈춤과 상관없이 센다."""


def render(registry: run_registry.RunRegistry) -> None:
    """넣으면 언제 돌지 알리는 안내를 그린다."""


def enqueued_text(
    *, added: int, skipped: int, ahead: int, paused: bool, digesting: bool
) -> str:
    """넣은 뒤 한 번 보일 문구. ``added`` 는 1 이상이다."""
```

`render` 는 `ask._render_queue_notices` 의 앞 세 줄을 옮긴 것이다. 같은
영상이 이미 들어 있는지 보는 마지막 부분은 질의 화면 몫이라 `ask.py`
에 남는다.

| 조건 | 안내 |
| --- | --- |
| 앞선 질의 m건 | `st.info` 실행 중이거나 대기 중인 질의가 m건 있습니다. 넣으면 그 뒤에 실행됩니다. |
| 정리본 작성 중 | `st.info` 정리본을 작성 중입니다. 넣은 질의는 정리본이 끝난 뒤 시작합니다. |
| 대기열 멈춤 | `st.warning` 대기열이 멈춰 있습니다. 넣은 질의는 실행 현황에서 재개할 때까지 기다립니다. |

`enqueued_text` 는 인자를 이름으로만 받는다. 숫자 셋과 참거짓 둘이
자리로 섞이면 알아보기 어렵다. 위에서부터 처음 맞는 줄을 쓰고, `added`
가 1 이면 **지금 질의 화면 문구와 글자 하나 다르지 않다.**

| 조건 | `added == 1` | `added > 1` |
| --- | --- | --- |
| 멈춤 | 대기열에 넣었습니다. 대기열이 멈춰 있어 재개할 때까지 기다립니다. | n건을 대기열에 넣었습니다. 대기열이 멈춰 있어 재개할 때까지 기다립니다. |
| 앞선 질의 | 대기열에 넣었습니다 — 앞에 m건. 실행 현황 화면에서 확인하세요. | n건을 대기열에 넣었습니다 — 앞에 m건. 실행 현황 화면에서 확인하세요. |
| 정리본 작성 중 | 대기열에 넣었습니다. 정리본이 끝나면 시작합니다. | n건을 대기열에 넣었습니다. 정리본이 끝나면 시작합니다. |
| 그 밖 | 실행을 시작했습니다. 실행 현황 화면에서 확인하세요. | n건을 넣고 첫 영상부터 시작했습니다. 실행 현황 화면에서 확인하세요. |

`skipped` 가 1 이상이면 끝에 ` 이미 대기 중이거나 실행 중인 k건은
뺐습니다.` 를 붙인다. 질의 화면은 늘 `added=1, skipped=0` 으로 부른다.

---

## 7. `pages/_channel_videos.py`

```python
STATUS_LABELS: dict[runs.RunStatus, str] = {
    "queued": "대기 중",
    "running": "실행 중",
    "done": "끝남",
    "failed": "실패",
}


def render(
    entries: Sequence[models.FeedEntry],
    handles: Sequence[runs.RunHandle],
    key: str,
) -> list[models.FeedEntry]:
    """신규 영상 표를 그리고 고른 영상을 돌려준다."""


def selected_entries(
    entries: Sequence[models.FeedEntry], rows: Sequence[int]
) -> list[models.FeedEntry]:
    """고른 행 번호를 영상으로 옮긴다."""


def widget_key(entries: Sequence[models.FeedEntry], generation: int) -> str:
    """표의 위젯 key 를 영상 ID 구성과 넣기 횟수에서 만든다."""


def status_label(
    video_id: str, handles: Sequence[runs.RunHandle]
) -> str | None:
    """그 영상의 실행 상태를 표에 적을 말로 옮긴다."""
```

- **표**: `st.dataframe(rows, key=key, on_select="rerun",
  selection_mode="multi-row", hide_index=True, placeholder="",
  column_config=...)`. 표 위에 캡션 "행 왼쪽 칸을 눌러 고릅니다." 를
  둔다.

  | 열 | 값 | 설정 |
  | --- | --- | --- |
  | `title` | 영상 제목 그대로 | `TextColumn("제목")` |
  | `published` | 로컬 시각 `YYYY-MM-DD HH:MM` | `TextColumn("업로드일")`. 문자열이라 머리글 정렬이 시간 순서와 같다 |
  | `status` | `status_label` 결과 | `TextColumn("상태")`. 없으면 빈칸 |
  | `url` | `youtube.watch_url(video_id)` | `LinkColumn("영상", display_text="열기")` |

  표 칸은 일반 글자라 2.1 의 마크다운 이스케이프 문제가 없다. 긴
  제목은 칸에서 잘리고 칸에 올리면 전체가 보인다.
- **`selected_entries`**: 번호를 정렬해 목록 순서로 영상을 돌려주고,
  목록 밖의 번호는 버린다. `render` 와 넣기 콜백(8.2)이 함께 쓴다.
- **`widget_key`**: `channels_videos_` + `sha256(",".join(video_ids) +
  f"#{generation}")` 앞 16자. 확인을 다시 눌러 목록이 바뀌거나 넣기를
  한 번 하면 key 가 바뀌어 선택이 비워진다. 상태 칸은 key 에 넣지
  않는다 — 고르는 사이 실행이 끝나기만 해도 고른 것이 사라지면 안 된다.
- **`status_label`**: `handles` 를 앞에서부터 보아 `video_id` 가 같은
  첫 핸들의 상태를 `STATUS_LABELS` 로 옮긴다. `handles` 는
  `registry.list_all()` 이다(2.6).

---

## 8. `pages/_channel_check.py` · `pages/_channel_enqueue.py`

### 8.1 그리는 순서 — `_channel_check._render_found`

확인 결과(`_Checked`)가 지금 고른 채널의 것일 때만 그린다(지금과
같다).

1. 등록된 질문이 없으면 `st.info("질문 관리 화면에서 질문을 먼저
   등록하세요.")`. 있으면 `질문 선택` multiselect(`_QUESTIONS_KEY`).
   지금처럼 결과보다 먼저 그려, 결과가 오류나 빈 목록이어도 고른 질문이
   남는다.
2. 조회가 실패했으면 `st.error(f"{채널}: {사유}")` 하고 멈춘다.
3. 신규가 없으면 `st.info("새 영상이 없습니다.")` 하고 멈춘다.
4. 질문이 있으면 `auto_save_toggle.render(connection,
   "channels_auto_save", "channels_auto_save_locked")` 와
   `queue_notice.render(registry)`.
5. `st.subheader(채널 이름)`.
6. `_channel_videos.render(found.entries, registry.list_all(), key)`.
   `key` 는 `widget_key(found.entries, _channel_enqueue.generation())`
   다.
7. 질문이 있으면 `_channel_enqueue.render(registry, found.entries, key,
   _QUESTIONS_KEY, selected, chosen, auto_save)`.

### 8.2 넣기 — `_channel_enqueue`

```python
def generation() -> int:
    """이 화면에서 넣기를 한 횟수. 표의 key 에 섞는다."""


def render(
    registry: run_registry.RunRegistry,
    entries: tuple[models.FeedEntry, ...],
    table_key: str,
    questions_key: str,
    selected: list[models.FeedEntry],
    chosen: list[models.Question],
    auto_save: bool,
) -> None:
    """질문 안내, 넣기 버튼, 넣은 뒤의 결과를 그린다."""
```

**`generation`** 은 세션의 `channels_generation` 이고 없으면 0 이다.

**`render`** 가 그리는 것:

- 질문을 하나도 고르지 않았으면 `st.info("질문을 하나 이상
  고르세요.")`.
- 버튼 `선택한 영상 요약 (n건)`(`key="channels_enqueue"`). 고른 행이
  없거나 질문을 고르지 않았으면 잠긴다. `on_click` 은 아래 콜백이다.
- 세션(`channels_enqueued`)에 결과가 있으면 꺼내 한 번 보인다. 넣은
  것이 있으면 `st.success`, 모두 건너뛰었으면 `st.info`.

**넣기 콜백** `_enqueue_selected(registry, entries, table_key,
questions_key, auto_save)`:

1. 표 선택은 `st.session_state[table_key]` 의 `selection.rows`, 질문은
   `st.session_state[questions_key]` 에서 **누른 순간의 값**을 읽는다
   (2.9). 고른 영상이나 질문이 없으면 아무것도 하지 않는다.
2. 넣기 전에 `queue_notice.count_ahead`·`paused_reason()`·정리본
   `is_running()` 을 한 번 읽어 둔다. 결과 문구가 "넣기 직전" 을
   말하게 한다(질의 화면과 같다).
3. `_channel_videos.selected_entries` 로 고른 영상을 목록 순서로 돈다.
   `registry.is_pending(video_id)` 이면 건너뛴다. 아니면
   `runner.enqueue(registry, youtube.watch_url(video_id), 질문들,
   store.default_db_path(), auto_save=auto_save,
   is_blocked=digests.is_running)`.
4. 넣기 횟수를 1 올려 다음 그림의 표 key 를 바꾼다.
5. 결과를 세션에 적는다. 하나라도 넣었으면
   `queue_notice.enqueued_text(...)`, 모두 건너뛰었으면 "고른 영상은
   모두 이미 대기 중이거나 실행 중입니다." 다.

`auto_save` 는 버튼을 그릴 때 화면에 보이던 값이다. 체크를 바꾸면 그
자리에서 재실행되므로 누르는 순간의 값과 같다(질의 화면과 같다). 넣은
실행의 핸들에 고정되므로 나중에 체크를 바꿔도 이미 넣은 실행은
그대로다.

### 8.3 지우는 것

- `_render_entry` — 표가 대신한다.
- `_STARTED_KEY` 와 `_start_check` 의 초기화 — 상태 열이 대신한다.
- `_blocked_reason` — 잠금 셋(실행·대기 중, 멈춤, 정리본)은 안내로
  바뀌고, 남는 "질문을 하나 이상 고르세요" 는 `_channel_enqueue.render`
  가 그린다.

---

## 9. `pages/ask.py`

- `_render_auto_save`·`_remember_auto_save`·`_AUTO_SAVE_HELP` 를 지우고
  `auto_save_toggle.render(connection, _AUTO_SAVE_KEY,
  _AUTO_SAVE_LOCKED_KEY)` 를 부른다.
- `_render_queue_notices` 는 `queue_notice.render(registry)` 를 부른 뒤
  같은 영상 확인만 한다.
- `_count_ahead`·`_enqueued_text` 를 지우고 `queue_notice.count_ahead`·
  `queue_notice.enqueued_text(added=1, skipped=0, ahead=…, paused=…,
  digesting=…)` 를 부른다.

질의 화면 테스트(`tests/pages/test_ask.py`)는 이 파일의 내부 이름을
쓰지 않는다. **손대지 않고 통과하는 것**이 옮기기가 동작을 바꾸지
않았다는 증거다.

---

## 10. 실패와 엣지

| 상황 | 동작 |
| --- | --- |
| 등록된 질문이 없음 | 질문 관리 안내. 표는 그리고 자동 저장·안내·버튼은 그리지 않는다 |
| 질문을 고르지 않음 | "질문을 하나 이상 고르세요." 안내, 버튼 잠김 |
| 행을 고르지 않음 | 버튼 잠김 `(0건)` |
| 고른 영상 일부가 대기·실행 중 | 나머지만 넣고 "이미 대기 중이거나 실행 중인 k건은 뺐습니다." |
| 고른 영상 전부가 대기·실행 중 | 넣지 않고 `st.info` "고른 영상은 모두 이미 대기 중이거나 실행 중입니다." 선택은 비운다 |
| 끝났거나 실패한 영상 | 다시 넣는다. 상태 열이 "끝남"·"실패" 로 알려 준다 |
| 앞선 질의가 있음 | 넣고 그 뒤에 선다. 안내가 미리 알린다 |
| 정리본 작성 중 | 넣는다. 워커가 정리본이 끝날 때까지 시작을 미룬다(`is_blocked`) |
| 대기열 멈춤 | 넣는다. 재개할 때까지 선다. 안내는 `st.warning` |
| Outline 설정 없음 | 자동 저장이 꺼진 채 잠기고 이유를 적는다. 넣은 실행은 수동 저장 |
| 대상 채널을 바꿈 | 결과를 그리지 않는다(지금과 같다) |
| 확인을 다시 누름 | 목록이 새로 계산되고 key 가 바뀌어 선택이 비워진다. 끝나 이력에 남은 영상은 목록에서 빠진다 |
| 넣은 뒤 실행 현황에서 취소·지우기 | 핸들이 빠져 상태가 빈칸으로 돌아오고 다시 넣을 수 있다 |
| 상태가 바뀜(대기 → 실행 → 끝남) | 이 탭은 스스로 새로 고치지 않는다. 다음 재실행 때 반영된다. 지켜보는 곳은 실행 현황 화면이다 |

---

## 11. 테스트

외부 호출은 지금처럼 가짜로 막는다. 피드는 `check_feed`, 러너는
`monkeypatch` 로 `_channel_enqueue.runner.enqueue` 를 바꾼다. 가짜
러너는 스레드를 띄우지 않고 레지스트리에 대기로만 넣어, 같은 영상
판정과 상태 칸이 실제처럼 돌게 한다.

| 파일 | 내용 |
| --- | --- |
| `tests/pages/test_ask.py` | **바꾸지 않는다.** 그대로 통과해야 한다 |
| `tests/test_components.py` | `auto_save_toggle` — key 가 다른 두 화면이 설정 하나를 쓴다 · `queue_notice.enqueued_text` — `added == 1` 의 네 문구가 지금 질의 화면 문구와 같음 · `added > 1` 의 네 문구 · `skipped` 꼬리 · 위에서부터 처음 맞는 줄 · `queue_notice.render` — 아무것도 없으면 안내도 없다 |
| `tests/pages/test_channels.py` | 아래 |

`test_channels.py` 는 정리본의 `select_rows`·`click_start` 처럼 표
key 에 선택을 주입하는 `select_videos(app, entries, rows,
generation=0)` 와, 골라 버튼을 푼 뒤 누르는 `click_enqueue(app,
entries, rows)` 를 둔다(2.5).

- **표**: 확인하면 채널 이름 아래 표 하나에 신규가 행으로 나온다 ·
  제목·업로드일·상태·링크 값과 열 순서 · 캡션 · 대기열에 있는 영상은
  상태 "대기 중".
- **순수 함수**: `status_label` — 없음·대기·실행·끝남·실패, 같은
  영상이 여럿이면 `list_all` 의 첫 핸들 · `widget_key` — 같은 목록과
  횟수는 같은 key, 목록이나 횟수가 바뀌면 다른 key ·
  `selected_entries` — 목록 순서, 목록 밖 번호는 버림.
- **넣기**: 두 건을 거꾸로 골라도 목록 순서로 두 번 `enqueue` ·
  URL·질문이 넘어간다 · 자동 저장 체크 값이 `auto_save` 로 간다(DB
  값에서 시작, 끈 값) · Outline 설정이 없으면 `auto_save=False` 이고
  체크가 잠긴다 · 넣은 뒤 결과 문구 · 넣기 전 key 로 다시 고른 선택이
  새 표에 붙지 않는다.
- **건너뛰기**: 대기 중인 영상은 건너뛰고 꼬리 문구 · 전부 건너뛰면
  `enqueue` 를 부르지 않고 안내.
- **잠그지 않음**: 질의가 실행 중이어도, 대기열이 멈춰도, 정리본을
  작성 중이어도 넣고 안내한다. 지금의 잠금 테스트 세 건
  (`test_a_queued_query_blocks_the_summary`·
  `test_a_paused_queue_blocks_the_summary`·
  `test_a_running_query_blocks_the_summary`)을 이 기대로 뒤집는다.
- **질문**: 질문이 없으면 표만 있고 체크·버튼이 없다 · 질문이나 행을
  고르지 않으면 버튼이 잠긴다.
- 지금의 `test_summary_hands_the_video_to_the_runner`·
  `test_summary_never_auto_saves`·`test_no_questions_blocks_the_summary`
  는 위 테스트로 바뀐다. 마크다운에서 제목을 찾던 두 테스트
  (`test_checking_lists_new_videos`·
  `test_switching_the_target_channel_clears_the_result`)는 표에서
  찾는다.

AppTest 는 표를 클릭하지 못하므로 클릭 선택, 정렬 뒤 선택, 링크 열,
넣은 뒤 선택이 비는 모습은 **실제 브라우저에서 확인한다**(2.9).

---

## 12. 건드리는 파일과 다시 쓰는 문서

**코드**

| 파일 | 변경 |
| --- | --- |
| `src/notebooklm_st/components/auto_save_toggle.py` | 신규(5) |
| `src/notebooklm_st/components/queue_notice.py` | 신규(6) |
| `src/notebooklm_st/pages/_channel_videos.py` | 신규(7) |
| `src/notebooklm_st/pages/_channel_enqueue.py` | 신규(8.2) |
| `src/notebooklm_st/pages/_channel_check.py` | 8.1·8.3 |
| `src/notebooklm_st/pages/ask.py` | 9 |
| `src/notebooklm_st/services/run_store.py` | 독스트링 한 줄(2.2) |
| `tests/test_components.py` | 11 |
| `tests/pages/test_channels.py` | 11 |

**문서** — 결정이 바뀐 문서는 지금 결정 기준으로 다시 쓴다. 바뀐 경위는
적지 않는다.

- `2026-09-23-channel-watch-design.md` — 머리의 대상(대기열이 채널
  화면에 더하는 것), §1 의 "바로 요약을 시작한다", §1.1 "여러 건을 한
  번에 돌리지 않는다", §3 "실행은 한 건씩", §3.1 "여러 건 대기열" 기각,
  §4 구조 그림, §10 화면 그림, §10.3 신규 목록과 실행, §11 엣지의 질문·
  잠금 줄, §12 테스트의 "실행 중 잠금"과 AppTest 메모, §13 의 다른 설계
  가리키기, §15 범위 밖의 "여러 건 한 번에 요약"·"자동 저장" 이 틀리게
  된다.
- `2026-09-30-run-queue-and-auto-save-design.md` — 머리의 범위
  ("채널 화면의 요약 버튼은 … 동작은 그대로다"), §3.1 "채널 화면의
  요약도 대기열·자동 저장에 태우기" 기각, §6.3 "채널 화면은
  `auto_save=False`", §8.5 가드 표의 채널 줄과 멈춤 안내, §13
  "채널 화면이 대기열·자동 저장을 쓰지 않는다", §15 범위 밖의 "채널
  화면의 대기열·자동 저장" 이 틀리게 된다. §2.1 의 가드 표는 대기열을
  설계할 때 조사한 사실이라 그대로 둔다.
- `README.md` — 채널 사용법 줄(고른 영상을 대기열에, 자동 저장 체크)과
  Outline 설정이 없을 때 잠기는 체크.
- `docs/ONBOARDING.md` — UI 레이어 표에 공유 컴포넌트 둘과 채널 화면.

지난 구현 계획(`docs/superpowers/plans/`)은 그때의 기록이라 고치지
않는다.

**구현 순서**(커밋 단위)

1. 자동 저장 체크를 공유 컴포넌트로 떼어내기 — 질의 화면 동작 불변.
2. 대기열 안내를 공유 컴포넌트로 떼어내기 — 질의 화면 동작 불변,
   여러 건 문구 추가.
3. 신규 영상 표 모듈과 그 순수 함수 테스트.
4. 채널 화면에서 여러 건 넣기와 자동 저장.
5. 문서.

---

## 13. 미검증 가정

| 가정 | 확인 방법 | 틀리면 |
| --- | --- | --- |
| 표 key 가 바뀌면 이전 key 의 선택 상태가 세션에 쌓이지 않는다 | 그려지지 않은 위젯의 상태는 Streamlit 이 다음 실행에서 버린다. 브라우저에서 여러 번 넣으며 세션 상태를 본다 | 넣을 때 이전 key 를 세션에서 지운다 |
| 진행 중 실행을 숨기면 같은 영상을 다시 넣을 수 있다(2.6) | 질의 화면과 같은 한계로 받아들인다 | 고치려면 `is_pending` 이 숨긴 실행도 봐야 한다. 이번 범위가 아니다 |

---

## 14. 범위 밖

- **피드 404·500 처리** — YouTube 피드가 일시적으로 404 를 내면 등록과
  확인이 "피드가 없다" 로 실패한다. 따로 고친다.
- **영상마다 다른 질문** — 질문은 표 위에서 한 번 고른다.
- **표 자동 새로 고침** — 진행은 실행 현황 화면에서 본다.
- **끝난 영상을 표에서 바로 숨기기** — 확인을 다시 누르면 이력에 남은
  영상이 빠진다.
- **여러 채널을 한 번에 확인** — 기준일이 무엇에 걸리는지 말할 수
  없어 기각한 그대로다(채널 감시 설계 §3.1).
- **대기 순서 바꾸기·실행 중 항목 멈추기** — 대기열 설계의 범위 밖
  그대로다.
