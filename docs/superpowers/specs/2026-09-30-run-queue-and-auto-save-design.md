# 질의 대기열·자동 저장·실행 현황 표 설계 — 넣어 두면 Outline 까지 가게 하기

- **작성일**: 2026-09-30
- **상태**: 표·자동 저장 단계 구현 완료 (2026-09-30). 대기열 단계는 구현 전
- **단계**: **표 → 자동 저장 → 대기열** 순서로 셋으로 나눠 만든다.
  단계마다 구현 계획을 따로 쓰고, 구현한 뒤 앱에서 확인하고 다음
  단계로 간다(→ 4.2). 요청서 번호로는 3 → 1 → 2 다.
- **대상**: 단계마다 다르다(→ 13).
  질문 관리(`services/questions.py`), 파이프라인(`services/nlm.py`),
  메타데이터 수집(`services/video_metadata.py`), Outline 호출
  (`services/outline.py`·`services/outline_parse.py`), 이력 동기화
  (`services/history_sync.py`·`services/run_history_sync.py`), 정리
  (`services/digest.py`·`services/digest_runner.py`·`core/digest*.py`),
  공유 자원(`session.py`), 배포 파일
  (`docker-compose.yml`·`Dockerfile`·`pyproject.toml`)은 건드리지 않는다.
- **범위**: 질의 화면에서 넣는 실행에 한해 (1) 실행 현황을 한 줄 표로
  바꾸고, (2) 체크 하나로 답변을 받자마자 인용을 뺀 채 Outline 에
  저장하고, (3) 실행 중에도 다음 질의를 대기열에 넣어 차례로 돌린다.
  채널 화면의 "요약" 버튼은 새 러너 입구를 쓰지만 동작(비어 있을
  때만 시작, 수동 저장)은 그대로다.
- **전제**: Outline 1.10.0 이상. 자동 저장은 이력 화면의 저장과 같은
  `documents.create` 를 쓴다.

---

## 1. 왜 바꾸는가

영상 하나를 요약해 위키에 올리기까지 사람이 네 번 손을 댄다. 질의
화면에서 실행하고, 실행 현황에서 끝났는지 보고, 이력에서 제목과 인용
여부를 정하고, 저장 버튼을 누른다. 실행이 도는 동안에는 다음 영상을
넣을 수 없어서(`pages/ask.py:45`) 여러 영상을 요약하려면 한 건이
끝날 때마다 돌아와야 한다. 실행 현황 화면은 실행 하나가 URL·캡션·
상자·버튼·구분선 다섯 층을 차지해 서너 건이면 화면이 찬다.

이 설계는 세 가지를 한다.

- 실행 현황을 **한 줄에 한 건**인 표로 바꾼다.
- 질의 화면에 **자동 저장** 체크를 둔다. 켜고 넣은 실행은 답변을
  받자마자 인용을 뺀 채 Outline 에 올라간다. 제목이 없거나 답변 일부가
  실패한 실행은 올리지 않고 이력에 미저장으로 남긴다.
- 실행 중에도 질의를 **대기열**에 넣는다. 앞 실행이 끝나면 다음 것이
  저절로 시작된다. NotebookLM 에는 여전히 한 번에 하나만 붙는다.

사람이 결과를 읽기 전에 위키에 올라간다는 점은 받아들인 비용이다.
영상과 질문은 사람이 직접 고르고, 자동 저장은 체크로 켠다. 인용은
올라가지 않고 로컬에도 남지 않으므로 사라진다(→ 2.5). 이 역시
받아들였다.

**성공 기준**

- 실행 현황 한 화면(1080p 모니터, wide 레이아웃)에 실행 10건 이상이
  보인다.
- 질의 화면에서 URL 을 연달아 넣으면 하나씩 끝까지 돈다. 넣는 동안 앞
  실행을 기다리지 않는다.
- 자동 저장을 켜고 넣은 실행은 사람의 추가 조작 없이 Outline 컬렉션에
  문서가 생기고, 이력 목록에 "문서" 로 보인다.
- 제목이 없거나 답변 일부가 실패한 실행은 이력에 "미저장" 으로 남고,
  실행 현황 표의 저장 칸에서 이유를 읽을 수 있다.
- 인증 만료·요청 한도·노트북 상한으로 실패하면 대기열이 멈추고 남은
  항목은 대기로 남는다. 원인을 푼 뒤 재개하면 이어 간다.
- 대기열이 도는 동안 정리본·임시 노트북 정리·원격 로그인이 NotebookLM
  을 동시에 쓰지 않는다.

---

## 2. 조사로 확인한 사실

### 2.1 "한 번에 하나" 가드는 다섯 곳에 있다

| 자리 | 지금 보는 것 | 막는 일 |
| --- | --- | --- |
| `pages/ask.py:45` | `running_count() > 0`, 정리 실행 중 | 실행 버튼 |
| `pages/digest.py:141` | `running_count() > 0` | 정리 시작 버튼 |
| `pages/maintenance.py:39` | `running_count()`, 정리 실행 중 | 임시 노트북 삭제 |
| `pages/_channel_check.py:186` | `running_count() > 0`, 정리 실행 중 | 채널 신규 영상의 "요약" 버튼 |
| `services/login_session.py:164` | `running_count() > 0`, 정리 실행 중 | 원격 로그인 시작 |

근거는 셋이다. NotebookLM 노트북 상한과 요청 한도
(`2026-08-28-background-execution-design.md` §6), 같은 쿠키로의 동시
접근이 검증된 적 없고 `tmp-` 노트북을 질의·정리가 함께 쓴다는 점
(`2026-09-23-digest-design.md` §2.5), 돌던 작업이 옛 쿠키를 되써 새
로그인을 덮을 수 있다는 점(`services/login_session.py:busy`)이다.
셋 모두 지키려는 것은 **NotebookLM 에 동시에 하나**이지, 화면이 한
건만 받는다는 것이 아니다.

### 2.2 러너는 실행마다 스레드를 띄운다

- `runner.start_run` 이 레지스트리에 running 핸들을 만들고 데몬 스레드
  하나를 띄운다(`services/runner.py:27`). 끝난 스레드는 다음 시작 때
  목록에서 걸러 낸다. `join_all` 은 테스트만 부른다.
- 스레드 본체 `_work` 의 순서는 메타데이터 조회 → 파이프라인 →
  `run_history.save_run` → `registry.finish` 다. 실패는 전부
  `registry.fail` 로 마감하고, `BaseException` 은 상태를 남긴 뒤 다시
  던진다. 스레드는 Streamlit API 를 부르지 않는다.
- `RunRegistry`(`services/runs.py`)는 락 하나와 dict 하나다.
  `list_all` 은 넣은 순서의 역순이고, `discard` 는 목록에서만 지운다.
- 레지스트리는 `@st.cache_resource` 라 모든 탭이 같은 것을 본다
  (`session.get_registry`). 서버를 재시작하면 빈다.

### 2.3 제목은 파이프라인이 끝나야 생긴다

- 문서 제목의 기본값은 `RunResult.title` 이다. NotebookLM 이 소스로
  읽은 영상 제목이며, 빈 제목은 `None` 이 된다(`services/nlm.py` 의
  `title = source.title or None`).
- 이력 화면은 `selected.title or selected.video_id` 를 제목 칸의
  초기값으로 쓰고 사람이 고친다(`pages/history.py:62`).
- yt-dlp 메타데이터는 채널·업로드일만 담는다(`models.VideoMetadata`).
- 그래서 대기 중이거나 실행 중인 항목의 제목은 알 수 없다.

### 2.4 답변 일부 실패는 결과 안에 담긴다

- 질문 하나가 `ChatError` 로 실패하면 파이프라인은 멈추지 않고 그
  항목의 `error` 에 문구를 담는다(`services/nlm.py:_ask_one`).
- 노트북 생성·자막 인덱싱처럼 질문 이전 단계의 실패는 예외로 올라와
  실행 전체가 실패한다. 이때는 이력이 생기지 않는다.

### 2.5 저장은 두 호출이고, 저장하면 답변이 지워진다

- 이력 화면의 저장(`pages/history.py:_export`)은
  `outline.create_document` → `run_links.mark_exported` 두 단계다.
  앞이 실패하면 로컬은 그대로다. 뒤가 실패하면 "문서는
  만들어졌습니다 … 다시 저장하면 문서가 둘이 됩니다" 를 보이며, 뒤는
  `ValueError`·`sqlite3.Error` 만 잡는다.
- `mark_exported` 는 `answers` 행을 지운다. `run_metadata` 는 남는다.
- "인용 포함" 을 끄면 `answer_text.for_display` 가 인용 번호·인용
  본문·맨 아래 후속 제안을 뺀 사본을 만들고, 그 사본이 올라간다.
- 따라서 인용을 뺀 채 저장하면 인용은 Outline 에도 로컬에도 남지
  않는다.
- `markdown_export.to_markdown` 은 `RunSummary` 를 받는다. 러너는
  `save_run` 이 돌려준 실행 ID 만 갖고 있고, 한 건을 `RunSummary` 로
  읽는 함수는 없다(`list_runs` 는 목록만 준다).

### 2.6 다음 실행도 같은 이유로 실패하는 오류가 셋 있다

`core/errors.py` 기준이다.

- `_LOGIN_ERRORS` — `AuthError`·`HeadlessLoginRequiredError`·로그인
  리다이렉트. 재로그인으로만 풀린다.
- `RateLimitError` — 시간이 지나야 풀린다.
- `NotebookLimitError` — 노트북을 지워야 풀린다.

그 밖의 매핑 오류(소스 추가·처리 실패, 소스 대기 시간 초과, 네트워크,
답변 실패)는 그 영상에 한정된다고 본다.

### 2.7 새 테이블은 DB 를 지우지 않고 붙는다

`store.connect` 는 `CREATE TABLE IF NOT EXISTS` 스크립트를 먼저 돌리고
`_EXPECTED_COLUMNS` 로 빠진 컬럼을 검사한다. 새 테이블은 기존 DB 에서
먼저 만들어진 뒤 검사를 통과한다. `channels` 가 같은 길로 들어왔다.

### 2.8 Streamlit 1.64 에서 쓸 수 있는 것

- `st.dataframe` 의 행 선택은 원래 데이터의 행 번호로 오고, key 를 준
  표는 데이터가 바뀌어도 고른 번호를 그대로 쥔다. 맨 위에 행이 끼면
  고른 번호가 다른 행을 가리킨다(`2026-09-23-digest-design.md` §2.7 에서
  실측). 표 칸 안에는 버튼을 둘 수 없다.
- `st.columns(spec, gap=…, vertical_alignment="center")`,
  `st.button(type="tertiary")`(테두리 없는 글자 버튼),
  `st.badge(label, color=…)` 가 있다. 좁은 화면에서 `st.columns` 는
  세로로 쌓인다.
- key 없는 `st.checkbox` 의 위젯 ID 에는 `value` 가 들어간다
  (`elements/widgets/checkbox.py` 의 `compute_and_register_element_id`
  호출). 초기값이 바뀌면 새 위젯이 된다. 그래서 초기값을 DB 에서
  읽는 key 없는 체크는 바꾼 값을 DB 에 적는 순간 다음 그림에서 ID 가
  바뀌고, 브라우저가 들고 있던 옛 위젯으로 보낸 **바로 다음 조작이
  버려진다.** AppTest 로 확인했다 — 켜고 곧바로 끄면 켜진 채 남는다.
- 위젯 값은 기본(`persist_state=None`)으로 다른 화면에 다녀오면
  버려진다. key 를 준 위젯도 같다. 그래서 세션에 키가 없을 때만 DB
  값으로 채우면, 다른 화면에 다녀올 때마다 DB 값으로 다시 시작한다.
  AppTest 로 확인했다.

---

## 3. 설계 결정

| 결정 | 이유 |
| --- | --- |
| NotebookLM 에는 **여전히 한 번에 하나** | 2.1 의 세 근거가 모두 그대로다. 대기열은 차례를 세울 뿐 동시에 돌리지 않는다 |
| 대기열은 **레지스트리 안, 메모리에만** | 실행 중 항목이 이미 메모리에만 있다. 대기 항목만 영속하면 재시작 뒤 "실행 중이던 것은 사라지고 그 뒤의 것은 남는" 어긋난 상태가 된다 |
| 워커는 **비면 끝나는 스레드 하나** | 할 일이 없을 때 떠 있는 스레드가 없다. 테스트가 `join_all` 로 기다리는 지금 방식이 그대로 통한다(→ 3.1) |
| 워커를 띄울지는 **레지스트리 락 안에서** 판정 | 워커가 끝나는 순간과 새 항목이 들어오는 순간이 겹쳐도 워커가 둘이 되거나 하나도 없게 되지 않는다(→ 8.2) |
| 정리본이 도는 동안에도 **넣을 수 있다** | 넣는 것은 NotebookLM 을 쓰지 않는다. 워커가 정리본이 끝날 때까지 시작을 미룬다 |
| 다음 실행도 실패할 오류면 **대기열을 멈춘다** | 남은 항목이 몇 초 간격으로 같은 이유로 줄줄이 실패하는 것을 막는다. 남은 항목은 대기로 남고 사람이 재개한다 |
| 멈춘 대기열은 **가드를 잠그지 않는다** | 멈춘 동안에는 NotebookLM 을 쓰지 않는다. 인증 만료를 풀려면 원격 로그인이 되어야 한다 |
| 대기 항목은 **취소할 수 있다**, 실행 중 항목은 멈출 수 없다 | 대기 항목은 아직 아무것도 만들지 않았다. 실행 중 항목을 멈추는 길은 지금도 없고, 노트북 정리와 얽혀 이번 범위가 아니다 |
| 같은 영상이 대기·실행 중이면 **넣지 않는다** | 두 번 누른 실수가 NotebookLM 호출 두 벌과 문서 두 개가 된다 |
| 자동 저장 체크는 **DB 에 기억한다** | 대부분의 실행에서 켜 둘 설정이라, 재시작하거나 다른 기기에서 열어도 켜져 있어야 한다 |
| 자동 저장 여부는 **넣는 순간 항목마다 고정** | 넣은 뒤 체크를 바꿔도 이미 넣은 항목의 동작이 바뀌지 않아야 사람이 예측할 수 있다 |
| 자동 저장은 **러너 스레드에서, 이력 저장 직후** | 저장 흐름을 사람이 없는 곳에서 끝까지 가게 하는 것이 목적이다. 이력을 먼저 남기므로 Outline 이 실패해도 결과가 사라지지 않는다 |
| 제목이 없거나 답변 일부가 실패하면 **건너뛴다** | 사람이 고쳐야 할 결과다. 영상 ID 를 제목으로 올리거나 빈 답변을 위키에 남기지 않는다 |
| 건너뛴 실행은 **이력에 미저장으로 남는다** | 이력 화면의 기존 저장 버튼이 그대로 다음 길이 된다. 새 화면이 필요 없다 |
| 인용은 **올리지 않는다** | 요청이다. `for_display` 가 이력 화면의 "인용 포함" 끔과 같은 사본을 만든다 |
| 이력 화면과 러너가 **저장 함수 하나를 함께 쓴다** | 두 저장 경로의 실패 처리("문서가 둘이 됩니다")가 어긋나지 않는다(→ 7.3) |
| 실행 현황은 **`st.columns` 한 줄 행** | 행마다 버튼을 두고, 버튼 키를 실행 ID 로 묶어 행이 밀려도 다른 행을 건드리지 않는다(→ 3.1) |
| 표의 순서는 **실행 중 → 대기(실행 순) → 끝난 것(최근 끝난 것부터)** | 위에서 아래로 "지금, 다음, 지난 것" 으로 읽힌다 |
| 영상 칸은 **끝난 뒤 제목, 그 전에는 영상 ID** | 제목은 파이프라인 끝에야 생긴다(→ 2.3). 제목을 위해 조회를 하나 더 두지 않는다 |
| 자동 저장의 결과는 **실행 현황에만 남긴다** | 건너뛴 이유는 다음 조치(이력에서 저장)를 고르는 데 쓰고 나면 쓸모가 없다. 이력에는 "미저장" 이 이미 보인다 |

### 3.1 기각한 안

- **상주 디스패처 스레드** — 교과서적이지만 Streamlit 에는 "앱이 뜰
  때" 가 따로 없어 `@st.cache_resource` 에 묶어야 하고, 테스트마다
  스레드를 멈추고 다시 띄우는 격리가 까다롭다. 할 일이 없어도 떠 있다.
- **항목마다 스레드 + 순번 락** — 기다리는 스레드가 쌓이고, 취소와
  멈춤을 스레드마다 확인해야 한다. 파이썬 락은 순서를 보장하지 않아
  순번 장치를 따로 만들어야 한다.
- **`st.dataframe` 표** — 칸 안에 버튼을 못 둔다. 지우기·취소를 행
  선택으로 하면 1초 폴링 사이에 맨 위에 행이 끼어 고른 번호가 다른
  행을 가리킨다(→ 2.8).
- **대기열을 DB 에 영속** — 재시작 뒤 이어 돌리려면 실행 중이던 항목의
  복구, 반쯤 만든 임시 노트북, 스키마가 함께 따라온다. 실행 중 항목이
  이미 메모리뿐이라 얻는 것이 적다.
- **멈추지 않고 계속 돌리기** — 인증이 만료되면 남은 항목이 전부 같은
  이유로 실패하고 표에 실패 줄만 쌓인다.
- **멈출 때 남은 항목을 건너뜀으로 비우기** — 원인을 푼 뒤 URL 과
  질문을 다시 넣어야 한다.
- **인증 회복을 감지해 저절로 재개** — 인증 게이트의 확인 주기와
  엮이고, 요청 한도·노트북 상한에는 감지할 신호가 없다. 재개는 버튼
  하나다.
- **제목이 없으면 영상 ID 로 저장** — 위키에 `ORMZHAz1fPE` 같은 문서가
  생긴다.
- **자동 저장 결과를 DB 에 기록** — 이력에는 "미저장" 이 이미 보인다.
  이유를 영구히 남길 곳을 만들면 언제 지울지가 관리 대상이 된다.
- **제목을 얻으려 대기 항목마다 yt-dlp 조회** — 네트워크 호출이 하나
  늘고, 파이프라인이 곧 같은 값을 준다.
- **채널 화면의 "요약" 도 대기열·자동 저장에 태우기** — 이번 범위가
  아니다. 뒤에 붙일 수 있도록 러너 입구를 하나로 둔다(→ 6.1).

---

## 4. 구조

### 4.1 모듈

```
pages/ask.py              URL·질문·자동 저장 체크·넣기 (자동 저장, 대기열)
pages/dashboard.py        실행 현황 표 · 재개 · 끝난 항목 지우기 (표, 대기열)
components/run_progress.py  표의 한 줄을 그리는 함수들 (표)
pages/history.py          저장 버튼이 공유 저장 함수를 부른다 (자동 저장)
pages/digest.py·maintenance.py·_channel_check.py  가드 교체 (대기열)
services/login_session.py busy 가 active_count 를 본다 (대기열)
services/runs.py          핸들·레지스트리 — 대기·멈춤·저장 결과 (셋 다)
services/runner.py        넣기·워커·자동 저장 부르기 (자동 저장, 대기열)
services/run_export.py    새 파일 — Outline 저장 한 벌과 자동 저장 한 번 (자동 저장)
services/settings.py      새 파일 — 자동 저장 설정 읽기·쓰기 (자동 저장)
services/store.py         settings 테이블 (자동 저장)
services/run_history.py   한 건 조회 load_run (자동 저장)
core/auto_save.py         새 파일 — 건너뛸 이유를 고르는 순수 함수 (자동 저장)
core/errors.py            대기열을 멈출 오류 판정 (대기열)
```

의존 방향은 지금과 같다. `core/` 는 `services/` 를, `services/` 는
Streamlit 을 import 하지 않는다. `runner` 는 `digest_runner` 를 import
하지 않는다. 정리본이 도는지는 화면이 넘겨 주는 함수로 묻는다(→ 8.3).

### 4.2 단계

| 단계 | 사람이 보는 결과 | 완료 기준 |
| --- | --- | --- |
| **표** | 실행 현황이 한 줄 표가 된다. 끝난 항목 모두 지우기 | §9 의 표가 실행 중·완료·실패를 그린다. 질의·저장 동작은 그대로다 |
| **자동 저장** | 질의 화면의 "자동 저장" 체크. 표에 저장 칸이 생긴다 | §7 전부. 실행은 여전히 한 번에 하나이고 실행 중이면 실행 버튼이 잠긴다 |
| **대기열** | 실행 중에도 넣는다. 표에 대기 줄·취소·멈춤·재개 | §8 전부. 다섯 가드가 §8.5 대로 바뀐다 |

각 단계는 앞 단계 위에서만 동작하며, 단계가 끝날 때마다 앱이 온전히
돈다. 이 문서의 절들은 **세 단계를 모두 마친 최종 상태**를 적는다.
단계마다 달라지는 부분은 그 절에 "(표 단계)" 처럼 표시한다.

---

## 5. `core/models.py` — 바뀌지 않는다

새 값 객체는 모두 `services/runs.py` 에 둔다. 실행 상태는 화면과
스레드가 만나는 곳의 사정이라 `core` 의 도메인 모델이 아니다.

---

## 6. 실행 레지스트리와 러너

### 6.1 `services/runs.py` — 핸들

```python
RunStatus = Literal["queued", "running", "done", "failed"]
SaveState = Literal["saved", "skipped", "failed"]


@dataclasses.dataclass(frozen=True, slots=True)
class SaveOutcome:
    """자동 저장 한 번의 결과."""

    state: SaveState
    message: str       # 표의 저장 칸에 그대로 쓰는 문구
    url: str | None    # 만들어진 문서 URL. 못 만들었으면 None


@dataclasses.dataclass(slots=True)
class RunHandle:
    run_id: str
    url: str
    video_id: str
    questions: tuple[models.Question, ...]
    auto_save: bool
    queued_at: str
    started_at: str | None     # 대기 중이면 None
    status: RunStatus
    progress: list[str]
    result: models.RunResult | None
    save: SaveOutcome | None   # 자동 저장을 시도했을 때만
    error_message: str | None
    error_level: MessageLevel | None
    finished_at: str | None
```

- `questions` 는 지금의 `question_texts` 를 대신한다. 워커가 나중에
  파이프라인에 넘겨야 하므로 제목까지 든 `Question` 을 쥔다(대기열
  단계). 표 단계와 자동 저장 단계에서는 `question_texts` 를 그대로 둔다.
- `auto_save`·`save` 는 자동 저장 단계에서, `queued_at`·`started_at`
  의 `None` 은 대기열 단계에서 들어온다. 표 단계에서 `started_at` 은
  지금처럼 만드는 순간의 시각이다.

### 6.2 `services/runs.py` — 레지스트리

모든 공개 메서드는 지금처럼 락 안에서 동작하고 복사본을 돌려준다.

| 메서드 | 하는 일 | 단계 |
| --- | --- | --- |
| `enqueue(url, video_id, questions, auto_save) -> RunHandle` | queued 핸들을 넣는다 | 대기열. 그 전까지는 `create` 가 running 핸들을 만들고, 자동 저장 단계에서 `create` 에 `auto_save` 인자가 붙는다 |
| `acquire_worker() -> bool` | 워커 자리가 비었고, 멈춤이 아니고, 대기 항목이 있으면 자리를 잡고 참 | 대기열 |
| `claim_next() -> RunHandle \| None` | 멈춤이 아니면 가장 먼저 넣은 대기 항목을 running 으로 바꾸고 `started_at` 을 찍어 돌려준다. 없거나 멈춤이면 **같은 락 안에서 워커 자리를 비우고** `None` | 대기열 |
| `release_worker() -> None` | 워커 자리를 비운다. 워커가 예외로 끝날 때만 쓴다 | 대기열 |
| `append_progress(run_id, message)` | 지금과 같다 | — |
| `finish(run_id, result, save=None)` | done 으로 표시하고 저장 결과를 싣는다 | `save` 는 자동 저장 |
| `fail(run_id, message, level)` | 지금과 같다 | — |
| `pause(reason) -> None` | 대기열을 멈춘다 | 대기열 |
| `resume() -> bool` | 멈춤을 풀고, `acquire_worker` 와 같은 판정으로 워커를 띄워야 하면 참 | 대기열 |
| `paused_reason() -> str \| None` | 멈춘 이유. 멈추지 않았으면 `None` | 대기열 |
| `cancel(run_id) -> bool` | 그 항목이 **아직 대기 중일 때만** 지우고 참. 마지막 대기 항목을 지우면 멈춤도 풀린다 | 대기열 |
| `discard(run_id)` | 목록에서 지운다(실행 중·끝난 항목) | — |
| `discard_finished() -> int` | done·failed 를 모두 지우고 지운 수를 돌려준다 | 표 |
| `get(run_id)`, `list_all()` | `list_all` 은 §9.1 의 순서로 돌려준다 | 표 |
| `active_count() -> int` | running 수 + (멈추지 않았으면) queued 수. 지금의 `running_count` 를 대신한다 | 대기열 |
| `is_pending(video_id) -> bool` | 그 영상이 queued 또는 running 인가 | 대기열 |

**멈춤은 대기 항목이 남아 있는 동안만 산다.** 대기 항목이 없는데 멈춤이
남아 있으면, 인증을 고친 뒤 새로 넣은 항목이 이유 없이 서 있게 된다.
그래서 `cancel` 이 마지막 대기 항목을 지울 때 멈춤도 함께 푼다.
멈춘 동안 새로 넣은 항목은 대기로 서서 재개를 기다린다.

### 6.3 `services/runner.py` — 입구

```python
def enqueue(
    registry: runs.RunRegistry,
    url: str,
    questions: Sequence[models.Question],
    db_path: pathlib.Path,
    auto_save: bool,
    is_blocked: Callable[[], bool],
    pipeline: PipelineCallable = nlm.run_pipeline,
) -> runs.RunHandle: ...

def resume(
    registry: runs.RunRegistry,
    db_path: pathlib.Path,
    is_blocked: Callable[[], bool],
    pipeline: PipelineCallable = nlm.run_pipeline,
) -> None: ...
```

- `enqueue` 는 `registry.enqueue` 로 넣고, `registry.acquire_worker()`
  가 참이면 워커 스레드를 띄운다. 즉시 반환한다.
- `resume` 은 `registry.resume()` 이 참이면 워커를 띄운다.
- `is_blocked` 는 "지금 NotebookLM 을 다른 일이 쓰고 있는가" 다. 화면이
  `session.get_digest_registry().is_running` 을 넘긴다(→ 8.3).
- 질의 화면과 채널 화면이 모두 `enqueue` 를 부른다. 채널 화면은
  `auto_save=False` 를 넘긴다.
- 표 단계와 자동 저장 단계에서는 지금의 `start_run` 이 남는다. 자동
  저장 단계가 `auto_save` 인자를 더하고, 대기열 단계가 `start_run` 을
  `enqueue` 로 바꾼다.

### 6.4 `services/runner.py` — 워커

```python
def _drain(registry, db_path, is_blocked, pipeline) -> None:
    try:
        while True:
            while is_blocked():
                time.sleep(_BLOCKED_POLL_SECONDS)   # 2.0
            handle = registry.claim_next()
            if handle is None:
                return          # claim_next 가 이미 자리를 비웠다
            _work(registry, handle, db_path, pipeline)
    except BaseException:
        registry.release_worker()
        raise
```

- 워커 스레드는 지금처럼 `_threads` 에 들어가 `join_all` 이 기다릴 수
  있다. 대기열이 비면 스스로 끝난다.
- 정상 종료에서 자리를 비우는 곳은 `claim_next` 한 곳뿐이다. `finally`
  에서 비우면, 이 워커가 `None` 을 받은 직후 들어온 항목이 새 워커를
  띄웠는데 옛 워커가 그 자리를 비워 버려 세 번째 워커가 뜰 수 있다.
  그래서 예외 경로에서만 비운다.
- `_work` 는 지금처럼 `Exception` 을 모두 잡아 `fail` 로 마감하므로,
  예외 경로는 `BaseException` 뿐이다.

### 6.5 `services/runner.py` — `_work`

지금 순서에 두 가지가 더해진다.

1. 메타데이터 조회 → 파이프라인. 파이프라인이 `errors.MAPPED_ERRORS`
   로 실패하면 지금처럼 `fail` 한 뒤, **`errors.stops_queue(error)` 가
   참이면 `registry.pause(message.text)`** 를 부른다(대기열 단계).
2. `run_history.save_run` 으로 이력을 남긴다. 실패하면 지금처럼
   `fail` 하고 끝낸다. 자동 저장을 하지 않는다.
3. 핸들의 `auto_save` 가 참이면 진행 문구 `Outline 에 저장 중` 을 남기고
   §7.4 의 자동 저장을 한다. 결과가 `SaveOutcome` 이다(자동 저장
   단계).
4. `registry.finish(run_id, result, save)`.

자동 저장이 어떻게 끝나든 실행은 **done** 이다. 답변은 이미 이력에
있고, 저장 결과는 표의 저장 칸이 따로 보여 준다.

### 6.6 `core/errors.py` — 대기열을 멈출 오류

```python
def stops_queue(error: BaseException) -> bool:
    """다음 실행도 같은 이유로 실패할 오류인가."""
```

`_LOGIN_ERRORS` 와 `RateLimitError`·`NotebookLimitError` 에 참이다
(→ 2.6). 판정을 `to_message` 곁에 두어, 매핑하는 오류 목록과 멈추는
오류 목록이 한 파일에서 함께 보이게 한다.

---

## 7. 자동 저장

### 7.1 설정 — `services/store.py`·`services/settings.py`

```sql
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

`_EXPECTED_COLUMNS` 에 `"settings": {"key", "value"}` 를 더한다. 기존
DB 는 지우지 않아도 된다(→ 2.7).

```python
def auto_save(connection: sqlite3.Connection) -> bool: ...
def set_auto_save(connection: sqlite3.Connection, enabled: bool) -> None: ...
```

- 키는 `auto_save`, 값은 `"1"`·`"0"`. 행이 없으면 `False` 다.
- 설정은 이 하나뿐이다. 범용 설정 API 를 만들지 않는다.

### 7.2 건너뛸 이유 — `core/auto_save.py`

```python
def skip_reason(result: models.RunResult) -> str | None:
    """자동 저장을 건너뛸 이유. 올려도 되면 None."""
```

위에서부터 처음 걸리는 것을 돌려준다.

| 조건 | 돌려주는 문구 |
| --- | --- |
| `error` 가 있는 항목이 하나라도 있다 | `답변 일부 실패` |
| `result.title` 이 `None` 이거나 공백뿐이다 | `제목 없음` |

Outline 설정이 없는 경우는 순수 함수가 알 수 없으므로 러너가 따로
본다(→ 7.4).

### 7.3 저장 한 벌 — `services/run_export.py`

```python
class RecordError(Exception):
    """문서는 만들어졌는데 로컬 기록에 실패했다."""

    def __init__(self, document: outline.SavedDocument, cause: Exception): ...
    # str(error) 는 지금 이력 화면의 문구와 같다:
    # "문서는 만들어졌습니다: {url} — 로컬 기록에 실패했습니다
    #  ({원인 타입}). 다시 저장하면 문서가 둘이 됩니다."


class SaveConflictError(Exception):
    """같은 실행을 이미 저장했거나 다른 길이 저장하고 있다."""

    # str(error): "이미 Outline 에 저장했거나 저장 중인 실행입니다.
    #  화면을 새로 고쳐 확인하세요."


def save(
    connection: sqlite3.Connection,
    config: outline.OutlineConfig,
    summary: models.RunSummary,
    title: str,
    items: Sequence[models.AnswerItem],
    metadata: models.VideoMetadata | None,
) -> outline.SavedDocument:
    """문서를 만들고 로컬에 링크를 적는다.

    Raises:
        SaveConflictError: 이미 저장했거나 다른 길이 저장하고 있다.
            문서를 만들지 않는다.
        outline.OutlineError: 문서를 만들지 못했다. 로컬은 그대로다.
        RecordError: 문서는 만들었는데 mark_exported 가 실패했다.
    """
```

- 본문은 `markdown_export.to_markdown(summary, items, title, metadata)`
  이다. `mark_exported` 에서 `ValueError`·`sqlite3.Error` 만 잡아
  `RecordError` 로 바꾼다. 지금 이력 화면이 잡는 범위와 같다.
- 이력 화면의 `_export` 는 이 함수를 부르고 세 예외(`OutlineError`·
  `RecordError`·`SaveConflictError`)를 `st.error` 로 보인다.
  `OutlineError` 는 연결·거부 사유를 옮긴 문구를, `RecordError` 는
  위 문구를 그대로 보인다. `SaveConflictError` 는 같은 실행을 겹쳐
  저장하려 할 때만 보인다(→ 11).
- `run_history.load_run(connection, run_id) -> RunSummary | None` 을
  더한다. `list_runs` 와 같은 SELECT 에 `WHERE r.id = ?` 를 붙인다.
  러너가 `to_markdown` 에 넘길 요약을 여기서 얻는다(→ 2.5).
- `save` 는 같은 실행을 동시에 두 번 올리지 않는다. 실행 ID 를
  선점하고, 선점한 뒤 이미 저장됐는지 다시 읽어 그렇다면
  `SaveConflictError` 를 낸다. `mark_exported` 도 이미 저장된
  실행에는 기록하지 않는다(`ValueError`).

### 7.4 러너의 자동 저장

§6.5 의 3번에서 러너가 `run_export.save_automatically` 를 부르고, 그
함수가 아래를 차례로 한다. 모두 러너 스레드가 연 자기 커넥션으로
한다. 판정·읽기·저장·결과 변환을 저장 한 벌 곁에 두어, 러너는 스레드
순서만 갖는다.

1. `auto_save.skip_reason(result)` 가 문구를 주면
   `SaveOutcome("skipped", f"미저장 · {문구}", None)`.
2. `outline.config_from_env()` 가 `None` 이면
   `SaveOutcome("skipped", "미저장 · Outline 설정 없음", None)`.
   질의 화면이 설정 없이는 체크를 잠그므로 실제로는 드물다.
3. `run_history.load_run` 으로 요약을, `load_run_items` 로 답변을
   읽고, 답변마다 `answer_text.for_display` 를 씌운다. 메타데이터는
   `_work` 가 이미 가진 값을 쓴다. 제목은 `result.title.strip()`.
4. `run_export.save(...)`.
   - 성공 → `SaveOutcome("saved", "저장됨", document.url)`
   - `OutlineError` → `SaveOutcome("failed", f"미저장 · 저장 실패: {error}", None)`
   - `RecordError` → `SaveOutcome("failed", str(error), error.document.url)`
5. 위에서 예상 못 한 예외가 나면 로그를 남기고
   `SaveOutcome("failed", f"미저장 · 예상 못 한 오류({타입})", None)`.
   이 자리의 넓은 `except` 는 스레드 최상위와 같은 이유다. 여기서
   예외가 새면 이미 이력에 남은 실행이 "실행 중" 에 멈춘다.

건너뛰거나 실패한 실행은 이력에 미저장으로 남는다. 이력 화면에서 제목을
고치고 인용 여부를 정해 기존 버튼으로 올리면 된다. `RecordError` 인
경우만 문서가 이미 있으므로 다시 올리지 않도록 문구가 경고한다.

### 7.5 질의 화면의 체크

- 라벨 `자동 저장`. 도움말: `켜면 답변을 받은 뒤 인용을 빼고 곧바로
  Outline 에 올립니다. 제목이 없거나 답변 일부가 실패하면 올리지 않고
  이력에 미저장으로 남깁니다.`
- 위젯 키는 `ask_auto_save` 다. 세션에 그 키가 없을 때만
  `settings.auto_save(connection)` 로 채우고, 체크의 `on_change`
  콜백이 바뀐 값을 `set_auto_save` 로 적는다(→ 2.8). 사람이 바꿀
  때만 DB 에 쓰므로 다른 기기에서 바꾼 값을 되덮지 않는다. 다른
  화면에 다녀오거나, 재시작하거나, 다른 기기에서 열면 DB 값이
  보인다.
- Outline 설정이 없으면 체크를 잠그고(`disabled=True`, 값 `False`)
  캡션 `Outline 연결이 설정되지 않아 자동 저장을 쓸 수 없습니다.` 를
  보인다. DB 값은 건드리지 않는다.
- 넣을 때 화면에 보이는 값을 핸들의 `auto_save` 로 넘긴다.

---

## 8. 대기열

### 8.1 상태 전이

```
            enqueue                 claim_next
 (없음) ─────────────▶ queued ────────────────▶ running ──▶ done
                        │                          │
                        │ cancel                   └──────▶ failed
                        ▼                                 (stops_queue 면 pause)
                     (없음)
```

- done·failed 는 `discard`·`discard_finished` 로만 목록에서 사라진다.
- running 은 `discard` 로 목록에서 치울 수 있지만 워커는 계속 돈다.
  지금의 "목록에서 제거 (실행은 계속됨)" 와 같다. 치운 실행은 목록과
  `active_count` 에서 함께 빠지므로 가드도 그 실행을 보지 못한다. 지금과
  같은 성질이며, 응답 없는 실행을 치우는 비상구라 남겨 둔다.

### 8.2 워커 자리

레지스트리가 `_worker_active: bool` 을 쥔다. 뜻은 "드레인 루프를 도는
워커가 있다" 다.

- `acquire_worker` 와 `claim_next` 가 같은 락 안에서 이 값을 읽고 쓴다.
  워커가 `claim_next` 에서 `None` 을 받는 순간 자리가 비므로, 그
  뒤에 들어온 항목은 반드시 새 워커를 띄운다. 그 전에 들어온 항목은
  옛 워커가 `claim_next` 로 가져간다. 어느 순서로 겹쳐도 워커는
  하나다.
- 워커가 예외로 죽으면 `release_worker` 가 자리를 비운다. 남은 대기
  항목은 다음 `enqueue`·`resume` 이 새 워커를 띄울 때 이어진다.

### 8.3 정리본과의 순서

- 정리본이 돌고 있으면 워커는 2초마다 `is_blocked()` 를 다시 보며
  기다린다. 기다리는 동안 대기 항목은 queued 그대로다.
- 정리 시작 버튼은 `active_count() > 0` 이면 잠긴다. 대기 항목이
  있으면 워커가 곧 NotebookLM 을 쓰기 때문이다.
- 화면이 그려진 뒤 버튼을 누르기 전에 상대가 시작하는 틈은 지금도
  있다. 1인 사용이 전제라 받아들인다(`2026-08-28-youtube-qa-design.md`
  의 동시성 전제).

### 8.4 멈춤과 재개

- `_work` 가 `stops_queue` 인 오류로 실패하면 그 실행은 failed 가 되고
  `pause(문구)` 가 불린다. 워커는 다음 `claim_next` 에서 `None` 을 받고
  끝난다. 남은 항목은 queued 그대로다.
- 멈춘 동안 넣은 항목도 queued 로 서서 기다린다.
- 실행 현황의 **재개** 가 `runner.resume` 을 부른다. 원인이 남아
  있으면 다음 실행이 같은 이유로 실패하고 다시 멈춘다.

### 8.5 가드

| 자리 | 바뀐 뒤 |
| --- | --- |
| `pages/ask.py` | 실행 중·대기 중·정리 중이어도 **막지 않는다.** 막는 것은 URL 이 틀렸을 때, 질문을 안 골랐을 때, 같은 영상이 대기·실행 중일 때(`is_pending`)다 |
| `pages/digest.py` | `active_count() > 0` 이면 정리 시작을 잠근다 |
| `pages/maintenance.py` | `active_count() > 0` 이면 삭제를 잠근다. 멈춘 대기 항목은 아직 노트북을 만들지 않았으므로 잠그지 않는다 |
| `pages/_channel_check.py` | `active_count() > 0` 이거나 `paused_reason()` 이 있으면 "요약" 을 잠근다. 멈춘 대기열에 넣으면 돌지 않고 서 있기 때문이다 |
| `services/login_session.busy` | `active_count() > 0 or digests.is_running()`. 멈춘 동안에는 로그인을 막지 않는다 |

잠글 때의 안내 문구는 "실행 중" 을 "실행 중이거나 대기 중" 으로 바꾼다.
채널 화면의 멈춤 안내는 `대기열이 멈춰 있습니다. 실행 현황에서
재개하거나 대기 항목을 취소한 뒤 시작하세요.` 다.

### 8.6 재시작

대기 항목도 메모리에만 있어 서버를 재시작하면 사라진다. 실행 현황의
캡션에 이 사실을 적는다(→ 9.4).

---

## 9. 실행 현황 표 — `pages/dashboard.py`·`components/run_progress.py`

### 9.1 모양

```
[끝난 항목 모두 지우기]

상태      영상                               시작         질문  결과                         저장               동작
실행 중   dQw4w9WgXcQ                        09-30 17:20  2개   질문 1/2                     자동                숨기기
대기 1    7KDQnEiPlCI                        —            1개                                자동                취소
대기 2    9Mu26Z5lOno                        —            1개                                —                   취소
완료      AI 에이전트 설계의 세 가지 원칙…  09-30 17:12  1개   답변 1건                     저장됨 (링크)       지우기
완료      ORMZHAz1fPE                        09-30 17:10  2개   답변 2건 · 1건 실패: 요약    미저장 · 답변 일부 실패  지우기
실패      …                                  09-30 17:08  1개   인증이 만료되었습니다. …      —                   지우기
```

- 한 행은 `st.columns(_WIDTHS, gap="small", vertical_alignment="center")`
  한 줄이다. 머리글 행도 같은 폭으로 굵은 글씨를 그린다. 행 사이에
  구분선을 두지 않는다.
- 행 순서: running → queued(넣은 순) → done·failed(`finished_at` 이
  최근인 것부터). `list_all` 이 이 순서로 준다.
- 1초 폴링 fragment 는 그대로 둔다. fragment 는 레지스트리를 읽기만
  하고, 상태를 바꾸는 것은 버튼 클릭뿐이다(지금 docstring 의 약속).

### 9.2 칸

| 칸 | 내용 | 단계 |
| --- | --- | --- |
| 상태 | `st.badge`. 실행 중(blue)·대기 n(gray, n 은 실행될 차례)·완료(green)·실패(red) | 대기는 대기열 |
| 영상 | done 이고 `result.title` 이 있으면 `labels.shorten(title, 40)`, 아니면 영상 ID. 둘 다 영상 URL 로 가는 링크 | 표 |
| 시작 | `started_at` 을 `MM-DD HH:MM`. 대기 중이면 `—` | 표 |
| 질문 | `{n}개` | 표 |
| 결과 | 실행 중: 마지막 진행 문구(없으면 `시작하는 중`). 실패: 오류 문구. 완료: `답변 {n}건`, 실패 항목이 있으면 `· {k}건 실패: {제목들}`. 대기: 비움 | 표 |
| 저장 | 자동 저장을 끈 항목: `—`. 켠 항목이 대기·실행 중: `자동`. 켠 항목의 실행이 실패: `—`. 켠 항목이 완료: `save.message`, `save.url` 이 있으면 그 문서로 가는 링크 | 자동 저장 |
| 동작 | 대기: `취소`. 실행 중: `숨기기`(도움말 `목록에서만 치웁니다. 실행은 계속됩니다.`). 끝남: `지우기`. 모두 `type="tertiary"` 이고 키에 실행 ID 를 넣는다 | 표 (취소는 대기열) |

- 실패 문구는 `st.error`·`st.info` 상자 대신 칸 안의 글자로 그린다.
  `error_level` 이 error 면 빨간 글자, info 면 보통 글자다. 긴 문구는
  칸 안에서 줄바꿈된다.
- 실행이 실패한 항목의 저장 칸은 `—` 다. 이력이 없어 올릴 것이 없다.

### 9.3 표 위

- **끝난 항목 모두 지우기** — `discard_finished()`. 끝난 항목이 없으면
  잠근다(표 단계).
- **멈춤 안내와 재개** — `paused_reason()` 이 있으면
  `st.warning(f"대기열을 멈췄습니다 — {이유} 원인을 해결한 뒤 재개하세요.")`
  와 **재개** 버튼(대기열 단계).
- **정리본 대기 안내** — 대기 항목이 있고 정리본이 돌고 있으면
  `st.info("정리본을 작성 중입니다. 끝나면 대기열이 이어집니다.")`
  (대기열 단계).

### 9.4 캡션

`질의는 백그라운드에서 돕니다. 이 화면을 닫거나 다른 화면으로 이동해도
실행은 계속됩니다. 서버를 재시작하면 진행 중이던 실행과 대기 중인
질의는 사라집니다. 남은 임시 노트북은 정리 화면에서 확인하세요.`
(대기열 단계. 표 단계와 자동 저장 단계는 지금 문구를 둔다.)

---

## 10. 질의 화면 — `pages/ask.py`

위에서 아래로: URL → 질문 선택 → 자동 저장 체크 → 안내 → **실행**
버튼.

아래의 **앞선 항목 수** n 은 `list_all()` 에서 queued·running 을 센
값이다. 멈춤과 상관없이 센다. 사람에게는 "내 앞에 몇 건이 서 있나" 가
궁금한 것이기 때문이다.

- **안내**(대기열 단계)
  - n > 0 → `st.info(f"실행 중이거나 대기 중인 질의가 {n}건 있습니다.
    넣으면 그 뒤에 실행됩니다.")`
  - 정리 중 → `st.info("정리본을 작성 중입니다. 넣은 질의는 정리본이
    끝난 뒤 시작합니다.")`
  - 멈춤 → `st.warning("대기열이 멈춰 있습니다. 넣은 질의는 실행
    현황에서 재개할 때까지 기다립니다.")`
  - 같은 영상 → `st.info("이 영상은 이미 대기 중이거나 실행 중입니다.")`
    와 함께 버튼을 잠근다.
- **넣은 뒤**(대기열 단계): URL 칸을 비우고 질문 선택은 남긴다. 다음
  영상을 바로 붙여 넣게 하기 위해서다. 버튼의 `on_click` 콜백에서
  넣고 URL 위젯의 키를 비운다. 콜백은 재실행 전에 돌므로 위젯 키를
  바꿔도 예외가 없다. 결과 문구는 세션 키에 적어 다음 그림에서 한 번
  보인다. n 은 넣기 직전에 센 값이다. 위에서부터 처음 맞는 것을 쓴다.
  - 멈춤 → `대기열에 넣었습니다. 대기열이 멈춰 있어 재개할 때까지
    기다립니다.`
  - n > 0 → `대기열에 넣었습니다 — 앞에 {n}건. 실행 현황 화면에서
    확인하세요.`
  - 정리 중 → `대기열에 넣었습니다. 정리본이 끝나면 시작합니다.`
  - 그 밖 → `실행을 시작했습니다. 실행 현황 화면에서 확인하세요.`
- 표 단계와 자동 저장 단계에서는 지금처럼 실행 중·정리 중이면 버튼을
  잠근다.

---

## 11. 오류 처리

| 상황 | 결과 |
| --- | --- |
| 파이프라인이 매핑 오류로 실패 | failed, 오류 문구. `stops_queue` 면 대기열 멈춤 |
| 파이프라인이 예상 못 한 예외 | failed, `예상 못 한 오류(…)`. 대기열은 이어진다 |
| 이력 저장 실패 | failed, 지금 문구. 자동 저장 없음. 대기열은 이어진다 |
| 자동 저장 — 답변 일부 실패·제목 없음·설정 없음 | done, 저장 칸 `미저장 · …`. 이력에 미저장 |
| 자동 저장 — Outline 이 거부·응답 없음 | done, 저장 칸 `미저장 · 저장 실패: …`. 이력에 미저장. 다시 올리면 된다 |
| 자동 저장 — 문서는 만들었고 로컬 기록 실패 | done, 저장 칸에 문서 링크와 "다시 저장하면 문서가 둘" 경고. 이력에는 미저장으로 보인다 |
| 자동 저장이 올리는 중에 이력 화면에서 같은 실행을 저장 | 먼저 시작한 쪽만 문서를 만든다. 이력 화면은 `이미 Outline 에 저장했거나 저장 중인 실행입니다. 화면을 새로 고쳐 확인하세요.` 를, 자동 저장은 저장 칸에 `이미 저장했거나 저장 중` 을 보인다. `run_export` 가 프로세스 안에서 실행 ID 를 선점하고, 선점한 뒤 저장 여부를 다시 읽는다 |
| 자동 저장 — 예상 못 한 예외 | done, 저장 칸 `미저장 · 예상 못 한 오류(…)`. 로그에 트레이스백 |
| 워커가 `BaseException` 으로 죽음 | 그 실행은 failed(지금 `_work` 가 하듯). 자리가 비고, 남은 대기 항목은 다음 넣기·재개 때 이어진다 |
| 정리본이 도는 중 | 워커가 2초마다 확인하며 기다린다 |
| 실행이 응답 없이 멈춤 | 워커가 그 실행에 묶여 뒤의 대기 항목도 서 있다. 숨기기는 목록에서만 치운다. 서버 재시작이 유일한 탈출구다. 지금도 멈춘 실행은 재시작으로만 끝나며, 파이프라인의 각 단계에는 시간 제한이 있다 |
| 서버 재시작 | 실행 중·대기 중 항목이 사라진다. 이력에 남은 것은 남는다 |

---

## 12. 테스트

`pytest` + `streamlit.testing.v1.AppTest`, 가짜 파이프라인 주입
(`pipeline=`), `video_metadata.fetch` 막기(`tests/services/
test_runner_start.py` 의 autouse fixture)는 지금 방식을 따른다.
Outline 은 `runner.run_export.save` 또는 `outline.create_document` 를
`monkeypatch` 로 막는다.

**표 단계**

- `runs`: `list_all` 순서(실행 중 먼저, 끝난 것은 최근 끝난 것부터),
  `discard_finished` 가 끝난 것만 지운다.
- `dashboard`(AppTest): 실행 중·완료·일부 실패·실패 행이 각각 상태
  배지·결과 칸을 그린다. 행의 `지우기` 가 그 실행만 지운다. 끝난 항목
  모두 지우기가 실행 중 항목을 남긴다. 실행이 없으면 안내 하나.

**자동 저장 단계**

- `core/auto_save`: 실패 항목 있음 → `답변 일부 실패`, 제목 `None`·
  공백 → `제목 없음`, 둘 다면 앞의 것, 정상 → `None`.
- `settings`: 행이 없으면 `False`, 켜고 끄기가 남는다.
- `store`: 기존 스키마의 DB 에 `settings` 가 붙고 검사를 통과한다.
- `run_export`: 성공하면 문서가 만들어지고 답변이 지워진다.
  `OutlineError` 면 로컬이 그대로다. `mark_exported` 가 실패하면
  `RecordError` 이고 문구가 지금 이력 화면 문구와 같다.
- `run_history.load_run`: 있는 ID·없는 ID.
- `runner`: 자동 저장을 켜면 done 이고 `save.state == "saved"`, 이력이
  문서가 되고 올라간 본문에 인용 번호가 없다. 제목 없음·일부 실패면
  `skipped` 이고 Outline 을 부르지 않으며 이력이 미저장이다. Outline
  실패면 `failed` 이고 이력이 미저장이다. 끄면 Outline 을 부르지 않고
  `save is None` 이다.
- `ask`(AppTest): 체크의 초기값이 DB 값이다. 바꾸면 DB 에 남고,
  곧바로 다시 바꿔도 남는다. Outline 설정이 없으면 잠긴다.
- `history`(AppTest): 기존 저장 테스트가 그대로 통과한다.
- `dashboard`: 저장 칸의 네 모양(`—`·`자동`·`저장됨` 링크·`미저장 · …`).

**대기열 단계**

- `runs`: 넣은 순서대로 `claim_next`. `acquire_worker` 는 자리가 찼거나
  멈췄거나 대기가 없으면 거짓. `claim_next` 가 `None` 을 줄 때 자리가
  빈다. `cancel` 은 대기 항목만 지우고, 마지막 대기를 지우면 멈춤이
  풀린다. `active_count` 는 멈춘 대기를 세지 않는다. `is_pending`.
- `runner`: 둘을 연달아 넣으면 **겹치지 않고** 넣은 순서대로 돈다(가짜
  파이프라인이 동시 진입 수를 세어 1 을 넘지 않음을 단언한다). 첫
  실행이 도는 동안 둘째는 queued 다. `is_blocked` 가 참인 동안 시작하지
  않는다(`_BLOCKED_POLL_SECONDS` 를 `monkeypatch` 로 줄여 2초를 기다리지
  않는다). `stops_queue` 오류면 멈추고 남은 항목이 queued 로 남으며,
  `resume` 뒤 이어진다. 그 밖의 오류는 멈추지 않는다. 워커가
  `BaseException` 으로 끝나면 자리가 빈다.
- `errors.stops_queue`: 세 부류는 참, 나머지 매핑 오류는 거짓.
- `ask`(AppTest): 실행 중에도 버튼이 열려 있고 누르면 대기에 들어간다.
  같은 영상이면 잠긴다. 넣은 뒤 URL 칸이 비고 질문 선택은 남는다.
- `digest`·`maintenance`·`channels`·`login_session`: 대기 항목만
  있을 때와 멈춘 대기열일 때 §8.5 대로 잠기거나 열린다.
- `dashboard`: 대기 행의 `취소`, 멈춤 안내와 `재개`.

각 단계의 마지막에 앱을 띄워 사람이 직접 확인한다. 대기열 단계에서는
실제 NotebookLM 으로 두세 건을 연달아 넣어 요청 한도에 걸리는지 본다
(→ 14).

---

## 13. 건드리는 파일과 다시 쓰는 문서

| 단계 | 코드 | 테스트 | 문서 |
| --- | --- | --- | --- |
| 표 | `services/runs.py`, `components/run_progress.py`, `pages/dashboard.py` | `tests/services/test_runs.py`, `tests/pages/test_dashboard.py`, `tests/test_components.py` | `README.md`(실행 현황 한 줄), `docs/ONBOARDING.md`(`run_progress` 설명) |
| 자동 저장 | `services/store.py`, `services/settings.py`(새), `core/auto_save.py`(새), `services/run_export.py`(새), `services/run_history.py`, `services/runs.py`, `services/runner.py`, `pages/ask.py`, `pages/history.py`, `pages/dashboard.py`, `components/run_progress.py` | 위 항목별 테스트 파일, 새 모듈마다 새 테스트 파일 | `README.md`(자동 저장 사용법), `2026-09-22-outline-storage-design.md` **다시 쓰기** |
| 대기열 | `core/errors.py`, `services/runs.py`, `services/runner.py`, `services/login_session.py`, `pages/ask.py`, `pages/dashboard.py`, `pages/digest.py`, `pages/maintenance.py`, `pages/_channel_check.py`, `components/run_progress.py` | 위 항목별 테스트 파일, `tests/test_session.py` | `README.md`(대기열), `docs/ONBOARDING.md`(러너·레지스트리 설명), `2026-08-28-background-execution-design.md`·`2026-09-23-channel-watch-design.md`·`2026-09-23-digest-design.md`·`2026-09-26-remote-login-design.md` **다시 쓰기** |

**다시 쓰는 문서를 고른 기준.** 지금의 동작이나 코드 이름을 적은
문장이 이 설계로 틀리게 되는 설계 문서만 다시 쓴다. 한 문서가 여러
단계에 걸리면 **마지막으로 걸리는 단계**에서 한 번만 다시 쓴다.
`background-execution` 은 표 단계와 대기열 단계에 걸리므로 대기열
단계에서 쓴다.

- `outline-storage` — "저장은 사람이 버튼으로", "저장 흐름은 이력 화면
  한 곳", 범위 밖의 "자동 저장" 이 틀리게 된다.
- `background-execution` — "동시 실행 1개, 실행 중이면 버튼 비활성",
  `running_count`, 실행 카드가 틀리게 된다.
- `channel-watch` — `runner.start_run`, `running_count() > 0` 가드,
  "대기열을 만들지 않는다" 가 틀리게 된다. 채널 화면이 대기열·자동
  저장을 쓰지 않는다는 사실은 그대로 적는다.
- `digest` — "질의 화면이 정리 중이면 실행을 막는다"(§10.5)가 틀리게
  된다. 이제 넣고 기다린다.
- `remote-login` — `running_count()` 로 적힌 가드가 틀리게 된다.

**다시 쓰지 않는 문서.** `2026-09-16-headless-auth-design.md` 와
`2026-09-22-video-metadata-design.md` 의 범위 밖 목록에 있는 "스케줄러 ·
실행 큐 — 무인 실행을 하지 않는다" 는 그 릴리스의 범위를 적은 것이고,
무인 실행은 여전히 하지 않으므로 틀리지 않는다. 운영 문서(`docs/how-to/`)
의 "실행 현황이 비었을 때 내린다" 는 대기 줄도 표에 보이므로 그대로
맞다.

설계 문서를 다시 쓸 때는 경위("원래는·바뀌었다")를 본문에 적지 않고
커밋 메시지에 적는다.

---

## 14. 미검증 가정

- **연달아 도는 실행이 요청 한도에 걸리는가.** 지금은 사람이 누르는
  간격이 있었다. 대기열은 앞 실행이 끝나자마자 다음을 시작한다. 걸리면
  `RateLimitError` 로 대기열이 멈추므로 피해는 한 건에서 끝난다. 잦게
  걸리면 실행 사이에 쉬는 시간을 두는 것을 다음 일로 삼는다.
- **`RateLimitError`·`NotebookLimitError` 가 실제로 이 타입으로
  올라오는가.** `errors.to_message` 가 이미 두 타입을 매핑하지만, 실물
  에서 본 적은 없다. 다른 타입으로 오면 멈추지 않고 한 건씩 실패할
  뿐이다.

---

## 15. 범위 밖

- **채널 화면의 대기열·자동 저장** — 나중에 붙인다. 러너 입구
  `enqueue` 가 이미 `auto_save` 를 받는다.
- **실행 중인 항목 멈추기** — 파이프라인 취소와 임시 노트북 정리가
  얽힌다.
- **대기 순서 바꾸기** — 취소하고 다시 넣으면 된다.
- **재시작 뒤 대기열 되살리기** — 3.1.
- **실행 사이 쉬는 시간** — 14 의 결과를 보고 정한다.
- **스케줄러·주기 실행·무인 요약** — 하지 않는다. 대기열은 사람이 넣은
  것만 돈다.
- **자동 저장 제목 규칙**(날짜 붙이기 등) — NotebookLM 이 준 영상
  제목을 그대로 쓴다.
