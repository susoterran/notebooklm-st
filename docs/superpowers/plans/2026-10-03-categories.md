# 카테고리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 관리하는 카테고리를 질의할 때 하나 이상 고르게 하고, Outline 문서 머리에 적고, 동기화로 되읽고, 정리본 재료 표에서 카테고리·채널로 거르게 한다.

**Architecture:** 카테고리는 새 테이블 셋(`categories`·`run_categories`·`channel_categories`)에 두고 기존 테이블은 건드리지 않는다. 대기열 핸들이 카테고리 **ID** 를 쥐고, 워커가 이력에 잇고, `RunSummary.categories`(이름 순)를 타고 저장 경로·정리본·재료 표로 흐른다. 문서 머리의 `- 카테고리:` 줄이 정본이며, 동기화가 그 줄을 읽어 로컬을 맞춘다. 이름 규칙은 `core/category_names.py` 한곳에 두어 관리 화면과 동기화가 함께 쓴다.

**Tech Stack:** Python 3.13 · Streamlit 1.64 · SQLite · pytest + `streamlit.testing.v1.AppTest` · uv · ruff · mypy

**Spec:** `docs/superpowers/specs/2026-10-03-categories-design.md` — 이 계획은 설계서 전부를 구현한다. 구현자는 설계서와 이 계획을 둘 다 읽는다.

## Global Constraints

- 브랜치는 `develop`. 에이전트는 커밋만 하고 **`git push` 하지 않는다.** `--no-verify`·force 금지. worktree 를 만들지 않고 저장소 그 자리에서 일한다.
- 커밋 메시지: `<gitmoji> <type>(<scope>): <한국어 명령형 제목, 50자 이내, 마침표 없음>`, 빈 줄, 본문(무엇을·왜, 72칸에서 줄바꿈), 빈 줄, 마지막 줄 `Assisted-by: <커밋하는 에이전트 자신의 모델 ID>`. AI 를 `Co-Authored-By:` 로 적지 않는다.
- **커밋은 Git Bash 에서 메시지 파일로 넣는다**(각 Task 의 커밋 단계 모양 그대로: `mktemp` 파일에 쓰고 `git commit -F`, 끝에 플래그 없는 `rm`). PowerShell here-string(`@'…'@`) 금지 — 메시지에 `@` 줄이 남는다. 커밋 뒤 `git log -1 --format=%B | grep -c "^@$"` 가 `0` 이어야 한다.
- 명령 가드 훅이 `rm -f`·`rm -r`, `cd /…`·`cd ..`, `curl` 등을 막는다. 디렉터리는 옮기지 말고 저장소 루트에서 부른다. **긴 파이썬 스크립트를 명령 문자열의 heredoc 에 넣으면 가드가 막을 수 있다.** Task 1·2 의 스크립트는 파일 편집 도구로 `.temp/` 아래(git 이 무시한다)에 쓰고 실행한 뒤 플래그 없는 `rm` 으로 지운다.
- `uv` 는 에이전트 셸 PATH 에 없다. 모든 명령은 `/c/Users/susot/.local/bin/uv.exe run …` 로 부른다.
- 완료 전 네 검사를 이 순서로 통과한다: `ruff format .` → `ruff check --fix .` → `mypy src tests` → `pytest`. 이 계획을 시작하기 전 기준은 `858 passed, 1 skipped` 이고, 끝나면 `1014 passed, 1 skipped` 다(Task 마다 기대 수를 적었다). 새 가상환경에서 처음 돌리면 AppTest 가 제한 시간에 걸려 화면 테스트 하나가 실패할 수 있다(예행에서 `tests/pages/test_channels.py::test_checking_lists_new_videos`, 다시 돌리면 통과). 같은 모양으로 한 건만 실패하면 한 번 더 돌려 확인하고, 그래도 실패하면 보고한다.
- `core/`·`services/` 에서 `import streamlit` 금지.
- import 는 모듈 단위(`from notebooklm_st.core import category_names`)로만. 함수·클래스를 직접 import 하지 않는다. 예외는 `typing`·`collections.abc`.
- 모든 모듈·클래스·함수·테스트 함수에 한국어 Google 형식 독스트링. 코드 80칸, 독스트링·주석 72칸. **ruff 는 표시 폭으로 재므로 한글 한 자가 2칸이다.** 독스트링 72칸은 ruff 가 검사하지 않으니 직접 지킨다(아래 코드는 모두 지켜져 있다).
- `from __future__ import annotations` 를 쓰지 않는다.
- 바꾸지 않는 파일: `services/run_export.py`·`services/run_links.py`·`services/outline_messages.py`·`services/digest.py`·`services/digest_runner.py`·`pages/digest.py`·`pages/dashboard.py`, 배포 파일(`docker-compose.yml`·`Dockerfile`·`pyproject.toml`). `services/outline.py`·`services/outline_parse.py` 는 Task 1 에서 import 만 바뀐다. 새 의존성은 없다. 기존 테이블의 컬럼은 바뀌지 않는다.
- 운영 이미지의 SQLite 는 3.40 이다. `group_concat(… ORDER BY …)` 같은 3.44 이상의 문법을 쓰지 않는다(설계서 §2.9). 개발 PC 는 3.50 이라 테스트로는 드러나지 않는다.
- 화면 문구는 글자 그대로(설계서 §8 과 아래 "이 계획이 정한 것"):
  - 카테고리가 없을 때(질의 화면·확인 탭) `카테고리 관리 화면에서 카테고리를 먼저 등록하세요. 카테고리를 고르지 않으면 질의할 수 없습니다.`
  - 질의 화면·확인 탭의 선택 라벨 `카테고리`, 도움말 `Outline 문서 머리에 적히고 정리본 재료를 거르는 데 씁니다. 하나 이상 고르세요.`
  - 확인 탭에서 고르지 않았을 때 `카테고리를 하나 이상 고르세요.`
  - 채널 등록·목록 탭의 라벨 `기본 카테고리`, 도움말 `이 채널의 새 영상을 넣을 때 미리 골라 둘 카테고리입니다. 비워 둘 수 있습니다.`
  - 관리 화면: 제목 `카테고리 관리`, 캡션 `카테고리는 질의할 때 하나 이상 골라야 합니다. Outline 문서 머리에 적히고, 정리본 재료를 거르는 데 쓰입니다.`, 입력 `새 카테고리 이름`·버튼 `등록`, 펼침 안 `이름`·`수정`·`삭제`, 쓰는 곳 `이력 N건`·`채널 N개의 기본 카테고리`(둘이면 ` · ` 로 잇는다)·없으면 `아직 쓰는 곳이 없습니다.`, 잠금 이유 `이력에서 쓰는 카테고리라 이름을 바꾸거나 지울 수 없습니다.`·`대기 중이거나 실행 중인 질의가 쓰는 카테고리라 이름을 바꾸거나 지울 수 없습니다.`, 채널 경고 `지우면 채널 N개의 기본 카테고리에서도 빠집니다.`
  - 서비스 오류: `카테고리 이름이 비어 있습니다.`·`카테고리 이름은 30자까지입니다.`·`카테고리 이름에는 글자·숫자·공백과 - . & + / ( ) · 만 쓸 수 있습니다.`·`'{name}' 카테고리가 이미 있습니다.`·`이력에서 쓰는 카테고리는 이름을 바꾸거나 지울 수 없습니다.`·`카테고리 {id} 을 찾을 수 없습니다.`
  - 동기화 설명에 덧붙는 문장 `카테고리는 문서 머리에서 읽어 맞추고, 모르는 이름은 새로 등록합니다.`, 개수 줄 `… · 채널·업로드일 갱신 K건 · 카테고리 갱신 R건 · 새 카테고리 C개 · 건너뛴 문서 S건`, 새 이름 줄 `**새 카테고리** 경제, 인공지능`, 결과 `동기화 완료 · 지움 N건 · 만듦 M건 · 갱신 K건 · 카테고리 갱신 R건 · 새 카테고리 C개`
  - 재료 표: 칸 `카테고리`, 필터 라벨 `카테고리`·`채널`, 도움말 `고른 카테고리 중 하나라도 붙은 요약본만 보입니다.`·`고른 채널의 요약본만 보입니다.`, 안내 끝 문장 ` 필터를 바꾸면 고른 재료가 풀립니다.`, 결과 없음 `고른 조건에 맞는 요약본이 없습니다.`
  - 이력 화면 저장 버튼 도움말 `지금 보이는 그대로 올립니다. 올린 뒤에는 로컬에 링크와 채널·업로드일·카테고리만 남습니다.`
- 설계·명세 문서(`docs/superpowers/specs/*`)는 최종 상태만 담는다. 경위("원래는·바뀌었다")는 본문에 적지 않고 커밋 메시지에 적는다. 고칠 때는 문서를 끝까지 읽고 전체를 다시 쓴다.
- 계획에 적힌 테스트 단언이 쓰인 그대로는 통과할 수 없으면, **구현을 비틀어 통과시키지 말고** 그 사실과 이유를 보고한다.
- 이 계획의 코드는 격리된 worktree 에서 Task 1~15 를 차례로 적용해 Task 마다 네 검사를 통과한 글자다. diff 와 새 파일은 예행 커밋에서 그대로 뽑았다 — `ruff format` 뒤의 모양이다. Review Focus 테스트는 각자의 Task 시점 커밋에서 따로 돌려 통과를 확인했다.

## 설계서에 없어 이 계획이 정한 것

- 위젯 key: 질의 화면 `ask_categories` · 관리 화면 `category_new_name`·`category_add`·`category_name_{id}`·`category_rename_{id}`·`category_delete_{id}` · 채널 등록 탭 `channels_new_categories` · 목록 탭 `channels_default_categories_{channel.id}` · 확인 탭 `channels_check_categories_{channel_pk}`(`_channel_check.categories_key`) · 재료 필터 `digest_filter_categories`·`digest_filter_channels`.
- `services/categories.CategoryUsage(runs, channels)` 를 서비스에 둔다. 관리 화면의 잠금 판정은 `usage(...).runs > 0` 또는 레지스트리의 대기·실행 중 핸들이 그 ID 를 쥐었는가다(`pages/category_admin._is_queued`).
- `core/markdown_export.CATEGORY_SEPARATOR = ","` — 이름 규칙(`category_names`)이 이 모듈을 import 하므로 구분자를 이쪽에 둔다(순환 import 를 피한다).
- `run_history.SUMMARY_SELECT` 의 카테고리 칸은 상관 서브쿼리 `group_concat(c.name, ',')` 이고, `row_to_summary` 가 쉼표로 나눠 `category_names.ordered` 로 정렬한다. `save_run`·`insert_exported`·채널 기본값의 연결은 모두 `INSERT OR IGNORE … SELECT … FROM categories WHERE …` 라 없는 ID·이름은 조용히 빠지고 중복은 한 번만 들어간다.
- `RunHandle.category_ids` 는 맨 끝에 기본값 `()` 로 둔다. `runner.enqueue` 의 `category_ids` 도 맨 끝 키워드(기본값 `()`)라 러너 테스트의 위치 인자 호출이 그대로 선다. 화면은 늘 넘긴다.
- `pages/_channel_check.py` 는 질문·카테고리 선택을 `_render_choices` 로 떼고 화면 전용 값 `_Choices(questions, category_ids, ready)` 를 돌려받는다. `_channel_enqueue.render` 와 콜백은 `categories_key` 와 고른 ID 를 더 받는다(인자 순서는 Task 10 의 diff 그대로).
- 정리본 재료 필터는 `st.columns(2)` 에 나란히 그린다. 선택지가 비면 그 필터는 그리지 않는다.
- 테스트 도우미: 질의 화면 테스트는 `category` 픽스처("경제" 한 개)와 `choose_categories`·`record_categories` 를 쓴다. 채널 화면의 `checked()` 는 카테고리 "경제" 를 등록해 **채널 기본값으로** 두어, 확인 탭이 미리 채운 값으로 기존 넣기 테스트가 그대로 돈다.
- `tests/test_app.py` 의 독스트링 "여덟 페이지" 는 "아홉 페이지" 가 된다.

## Review Focus

1. **고른 카테고리를 다른 탭에서 지움** — 다음 그림에서 화면이 깨지지 않고 그 값만 선택에서 빠져야 한다. 다른 카테고리를 고르기 전에는 실행 버튼이 잠긴다. → Task 8 `test_a_deleted_category_drops_out_of_the_choice`
2. **고른 카테고리의 이름이 바뀜** — 선택이 남고 새 이름으로 보여야 한다(값이 ID 인 이유). → Task 8 `test_a_renamed_category_stays_chosen`
3. **정리본 필터에서 고른 값이 재료에서 사라짐**(다른 탭의 삭제·동기화) — 깨지지 않고 그 값이 풀리며 표가 다시 넓어져야 한다. → Task 14 `test_a_filter_value_that_disappears_is_dropped`
4. **동기화 미리보기와 적용 사이에 다른 탭이 같은 이름을 등록** — 적용이 실패하지 않고, 결과의 새 카테고리 수는 이 적용이 실제로 등록한 수여야 한다. → Task 11 `test_apply_counts_only_the_categories_it_added`
5. **이력 화면에서 손으로 저장** — 목록이 준 요약을 넘기는 길에서도 문서 머리에 카테고리 줄이 들어가야 한다. → Task 7 `test_save_writes_the_category_line`

다섯 모두 구현이 이미 그렇게 동작하는 것을 지키는 테스트라 넣자마자 통과한다. 각 Task 의 해당 단계에 그렇게 적었다.

---

## File Structure

| 파일 | 책임 | Task |
|---|---|---|
| `src/notebooklm_st/core/sync_models.py` (새) | 동기화 값 객체 — `models.py` 에서 옮기고 카테고리 갱신을 더함 | 1, 11 |
| `src/notebooklm_st/services/run_steps.py` (새) | 워커 한 건의 두 단계 — `runner.py` 에서 옮기고 카테고리 ID 를 이력에 넘김 | 2, 5 |
| `src/notebooklm_st/core/category_names.py` (새) | 이름 규칙·정렬·줄 나누기 | 3 |
| `src/notebooklm_st/services/store.py` | 새 테이블 셋 | 4 |
| `src/notebooklm_st/core/models.py` | `Category`, `RunSummary.categories` | 4, 5 |
| `src/notebooklm_st/services/categories.py` (새) | 카테고리 CRUD·쓰는 곳 세기·`ensure` | 4 |
| `src/notebooklm_st/services/runs.py`·`run_store.py`·`runner.py` | 핸들이 카테고리 ID 를 쥠 | 5 |
| `src/notebooklm_st/services/run_history.py` | 요약에 카테고리 싣기, 이력에 잇기 | 5 |
| `src/notebooklm_st/pages/category_admin.py` (새)·`app.py` | 관리 화면과 네비게이션 | 6 |
| `src/notebooklm_st/core/markdown_export.py` | 구분자·라벨·카테고리 줄 | 3, 7 |
| `src/notebooklm_st/pages/history.py` | 저장 버튼 도움말 한 줄 | 7 |
| `src/notebooklm_st/components/category_picker.py` (새) | 카테고리 선택 위젯과 문구 | 8 |
| `src/notebooklm_st/pages/ask.py` | 질의 화면의 카테고리 선택 | 8 |
| `src/notebooklm_st/services/channels.py`·`pages/channels.py` | 채널 기본 카테고리 | 9 |
| `src/notebooklm_st/pages/_channel_check.py`·`_channel_enqueue.py` | 확인 탭의 카테고리 선택과 넣기 | 10 |
| `src/notebooklm_st/core/outline_import.py`·`services/run_history_sync.py`·`services/history_sync.py` | 동기화가 카테고리를 읽고 맞춤 | 11 |
| `src/notebooklm_st/pages/_history_sync.py` | 미리보기·결과 문구 | 12 |
| `src/notebooklm_st/core/digest_markdown.py` | 정리본 머리의 합집합 줄 | 13 |
| `src/notebooklm_st/core/material_filter.py` (새)·`pages/_digest_materials.py` | 재료 칸과 필터 | 14 |
| `README.md`·`docs/ONBOARDING.md` | 사용법과 모듈 표 | 15 |
| 기존 설계서 넷 | 카테고리 반영 | 16 |
| 카테고리 설계서 상태 | 구현 완료 표시 | 17 |

각 Task 가 끝난 시점에도 앱은 온전히 돈다. Task 1·2 는 동작을 바꾸지 않는 옮기기다. Task 5 뒤로 카테고리는 이력에 붙지만 질의 화면이 넘기지 않으므로(기본값 `()`) 동작은 그대로다. Task 8 부터 질의에 카테고리가 필수가 된다.

---

### Task 1: 동기화 값 객체를 `core/sync_models.py` 로 옮기기

**Files:**
- Create: `src/notebooklm_st/core/sync_models.py`
- Modify: `src/notebooklm_st/core/models.py`(다섯 클래스를 뺀다), `src/notebooklm_st/pages/_history_sync.py`, `src/notebooklm_st/services/history_sync.py`, `src/notebooklm_st/services/outline.py`, `src/notebooklm_st/services/outline_parse.py`, `src/notebooklm_st/services/run_history_sync.py`
- Test: `tests/pages/test_history.py`, `tests/services/test_history_sync.py`, `tests/services/test_run_history_sync.py`(참조만 바뀐다)

**Interfaces:**
- Produces: `core.sync_models.ListedDocument`·`SyncCreate`·`SyncSkip`·`SyncUpdate`·`SyncPlan` — 내용은 `core.models` 에 있던 그대로다. 이후 Task 는 `sync_models.<이름>` 으로 부른다. `RunSummary`·`VideoMetadata` 는 `core.models` 에 남는다.

동작을 바꾸지 않는 옮기기라 새 테스트가 없다. 기존 테스트 전부가 그대로 통과하는 것이 증거다(설계서 §5.3).

- [ ] **Step 1: 옮기는 스크립트를 쓴다**

파일 편집 도구로 `.temp/move_sync_models.py` 에 아래를 쓴다(`.temp/` 는 git 이 무시한다).

```python
"""동기화 값 객체 다섯을 core/sync_models.py 로 옮기고 참조를 바꾼다."""
import pathlib
import re

W = pathlib.Path(".")
models_path = W / "src/notebooklm_st/core/models.py"
src = models_path.read_text(encoding="utf-8")
start = src.index("@dataclasses.dataclass(frozen=True, slots=True)\nclass ListedDocument:")
end = src.index("@dataclasses.dataclass(frozen=True, slots=True)\nclass DigestSource:")
block = src[start:end]
models_path.write_text(src[:start] + src[end:], encoding="utf-8")
block = re.sub(r"(?<![\w.])RunSummary\b", "models.RunSummary", block)
block = re.sub(r"(?<![\w.])VideoMetadata\b", "models.VideoMetadata", block)
header = '''"""이력 동기화가 쓰는 값 객체.

Outline 문서 목록과 저장된 이력을 맞추는 계획을 담는다. 동기화만
쓰므로 ``core.models`` 에서 떼어 둔다(→ ``services.history_sync``).
"""

import dataclasses

from notebooklm_st.core import models


'''
(W / "src/notebooklm_st/core/sync_models.py").write_text(
    header + block.rstrip() + "\n", encoding="utf-8"
)
NAMES = ("ListedDocument", "SyncCreate", "SyncSkip", "SyncUpdate", "SyncPlan")
FILES = [
    "src/notebooklm_st/pages/_history_sync.py",
    "src/notebooklm_st/services/history_sync.py",
    "src/notebooklm_st/services/outline.py",
    "src/notebooklm_st/services/outline_parse.py",
    "src/notebooklm_st/services/run_history_sync.py",
    "tests/pages/test_history.py",
    "tests/services/test_history_sync.py",
    "tests/services/test_run_history_sync.py",
]
for rel in FILES:
    p = W / rel
    text = p.read_text(encoding="utf-8")
    for name in NAMES:
        text = re.sub(rf"\bmodels\.{name}\b", f"sync_models.{name}", text)
    m = re.search(r"^from notebooklm_st\.core import (.+)$", text, re.M)
    mods = [x.strip() for x in m.group(1).split(",")]
    mods.append("sync_models")
    if not re.search(r"(?<!sync_)\bmodels\.", text):
        mods.remove("models")
    new = "from notebooklm_st.core import " + ", ".join(sorted(set(mods)))
    text = text[: m.start()] + new + text[m.end():]
    p.write_text(text, encoding="utf-8")
    print(rel, "->", new)
```

- [ ] **Step 2: 스크립트를 돌리고 지운다**

```bash
/c/Users/susot/.local/bin/uv.exe run python .temp/move_sync_models.py
rm .temp/move_sync_models.py
```

기대: 여덟 줄이 찍힌다. 각 파일의 `from notebooklm_st.core import …` 가 `sync_models` 를 담고, `outline.py`·`outline_parse.py`·`_history_sync.py` 는 `models` 를 더는 import 하지 않는다.

- [ ] **Step 3: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `858 passed, 1 skipped`.

포매터가 네 파일(`history_sync.py`·`test_history_sync.py` 등)의 긴 줄을 감싼다. 끝난 뒤 `core/sync_models.py` 는 이 모양이다.

```python
"""이력 동기화가 쓰는 값 객체.

Outline 문서 목록과 저장된 이력을 맞추는 계획을 담는다. 동기화만
쓰므로 ``core.models`` 에서 떼어 둔다(→ ``services.history_sync``).
"""

import dataclasses

from notebooklm_st.core import models


@dataclasses.dataclass(frozen=True, slots=True)
class ListedDocument:
    """Outline 목록에서 읽어 온 문서 하나.

    정리본이 쓰는 ``services.outline.OutlineDocument`` 와
    다르다. 동기화는 링크와 생성 시각도 필요하다.
    """

    id: str
    title: str
    url: str
    """절대 URL. 상대 경로는 ``services.outline`` 이 붙여서 넘긴다."""
    created_at: str
    """로컬 시각의 초 단위 ISO 문자열. ``store.now()`` 와
    같은 형식."""
    markdown: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyncCreate:
    """동기화가 새로 만들 이력 한 건."""

    document: ListedDocument
    url: str
    """본문에서 읽은 영상 URL."""
    video_id: str
    metadata: models.VideoMetadata | None = None
    """문서 머리에서 읽은 채널·업로드 일자. 두 줄이 다 없으면 ``None``."""


@dataclasses.dataclass(frozen=True, slots=True)
class SyncSkip:
    """동기화가 건너뛴 문서 한 건과 그 사유."""

    document: ListedDocument
    reason: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyncUpdate:
    """동기화가 메타데이터를 갱신할 기존 행 한 건."""

    run: models.RunSummary
    metadata: models.VideoMetadata
    """쓸 값. 문서가 준 칸과 로컬에 남길 칸을 합친 결과다."""


@dataclasses.dataclass(frozen=True, slots=True)
class SyncPlan:
    """미리보기와 적용이 함께 쓰는 동기화 계획.

    기존 행 중 손대지 않는 것은 담지 않는다. 화면이
    보여 줄 것은 바뀌는 것뿐이다.
    """

    deletes: tuple[models.RunSummary, ...]
    creates: tuple[SyncCreate, ...]
    skips: tuple[SyncSkip, ...]
    updates: tuple[SyncUpdate, ...] = ()

    @property
    def is_empty(self) -> bool:
        """지울 것도 만들 것도 갱신할 것도 없다."""
        return not self.deletes and not self.creates and not self.updates
```

`core/models.py` 는 216줄이 된다.

- [ ] **Step 4: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
♻️ refactor(sync): 동기화 값 객체를 core/sync_models 로 옮기기

카테고리 기능이 동기화 값 객체를 늘리면 core/models.py 가 300줄을
넘는다. 동기화만 쓰는 다섯(ListedDocument·SyncCreate·SyncSkip·
SyncUpdate·SyncPlan)을 내용 그대로 옮기고 참조를 바꾼다. 동작은
바뀌지 않는다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/core/models.py \
  src/notebooklm_st/core/sync_models.py \
  src/notebooklm_st/pages/_history_sync.py \
  src/notebooklm_st/services/history_sync.py \
  src/notebooklm_st/services/outline.py \
  src/notebooklm_st/services/outline_parse.py \
  src/notebooklm_st/services/run_history_sync.py \
  tests/pages/test_history.py \
  tests/services/test_history_sync.py \
  tests/services/test_run_history_sync.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 2: 워커 단계를 `services/run_steps.py` 로 옮기기

**Files:**
- Create: `src/notebooklm_st/services/run_steps.py`
- Modify: `src/notebooklm_st/services/runner.py`(300줄 → 230줄)
- Test: `tests/services/test_runner_queue.py`, `tests/services/test_runner_start.py`(`runner.video_metadata` → `run_steps.video_metadata`)

**Interfaces:**
- Produces: `run_steps.fetch_metadata(registry, run_id, url) -> models.VideoMetadata | None`, `run_steps.save_history(registry, run_id, result, metadata, db_path) -> int | None` — `runner._fetch_metadata`·`_save_history` 의 본문 그대로다. Task 5 가 `save_history` 에 `category_ids` 인자를 더한다.

동작을 바꾸지 않는 옮기기다(설계서 §7.7). 테스트는 `video_metadata.fetch` 를 모듈 속성으로 바꿔 끼우므로, 그 모듈을 부르는 쪽이 `run_steps` 로 바뀌어도 같은 모듈 객체를 가리킨다 — 테스트의 이름만 고친다.

- [ ] **Step 1: 옮기는 스크립트를 쓴다**

파일 편집 도구로 `.temp/move_run_steps.py` 에 아래를 쓴다.

```python
"""워커 한 건의 두 단계를 services/run_steps.py 로 옮긴다."""
import pathlib

W = pathlib.Path(".")
runner_path = W / "src/notebooklm_st/services/runner.py"
src = runner_path.read_text(encoding="utf-8")
start = src.index("\n\ndef _save_history(")
moved = src[start:].strip("\n")
rest = src[:start].rstrip("\n") + "\n"
rest = rest.replace(
    "    metadata = _fetch_metadata(registry, run_id, handle.url)",
    "    metadata = run_steps.fetch_metadata(registry, run_id, handle.url)",
)
rest = rest.replace(
    "    history_id = _save_history(registry, run_id, result, metadata, db_path)",
    "    history_id = run_steps.save_history(\n"
    "        registry, run_id, result, metadata, db_path\n"
    "    )",
)
rest = rest.replace(
    "from notebooklm_st.services import (\n"
    "    nlm,\n"
    "    run_export,\n"
    "    run_history,\n"
    "    run_registry,\n"
    "    runs,\n"
    "    store,\n"
    "    video_metadata,\n"
    ")",
    "from notebooklm_st.services import (\n"
    "    nlm,\n"
    "    run_export,\n"
    "    run_registry,\n"
    "    run_steps,\n"
    "    runs,\n"
    ")",
)
assert "_fetch_metadata" not in rest and "_save_history" not in rest
runner_path.write_text(rest, encoding="utf-8")
moved = moved.replace("def _save_history(", "def save_history(")
moved = moved.replace("def _fetch_metadata(", "def fetch_metadata(")
header = '''"""워커가 실행 하나를 돌릴 때 거치는 단계들.

영상 정보를 받는 단계와 결과를 이력에 남기는 단계를 담는다.
대기열과 스레드는 ``runner`` 가 맡는다. Streamlit API 를 부르지
않는다 — 워커 스레드에서 돈다.
"""

import logging
import pathlib

from notebooklm_st.core import models
from notebooklm_st.services import (
    run_history,
    run_registry,
    store,
    video_metadata,
)

logger = logging.getLogger(__name__)


'''
(W / "src/notebooklm_st/services/run_steps.py").write_text(
    header + moved + "\n", encoding="utf-8"
)
for rel in (
    "tests/services/test_runner_queue.py",
    "tests/services/test_runner_start.py",
):
    p = W / rel
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "runner.video_metadata", "run_steps.video_metadata"
        ),
        encoding="utf-8",
    )
q = W / "tests/services/test_runner_queue.py"
q.write_text(
    q.read_text(encoding="utf-8").replace(
        "from notebooklm_st.services import run_registry, runner, store",
        "from notebooklm_st.services import run_registry, run_steps, runner, store",
    ),
    encoding="utf-8",
)
s = W / "tests/services/test_runner_start.py"
s.write_text(
    s.read_text(encoding="utf-8").replace(
        "    run_registry,\n    runner,\n",
        "    run_registry,\n    run_steps,\n    runner,\n",
        1,
    ),
    encoding="utf-8",
)
```

- [ ] **Step 2: 스크립트를 돌리고 지운다**

```bash
/c/Users/susot/.local/bin/uv.exe run python .temp/move_run_steps.py
rm .temp/move_run_steps.py
```

기대: 출력 없이 끝난다(`assert` 가 통과).

- [ ] **Step 3: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `858 passed, 1 skipped`.

끝난 뒤 `services/run_steps.py` 는 이 모양이다.

```python
"""워커가 실행 하나를 돌릴 때 거치는 단계들.

영상 정보를 받는 단계와 결과를 이력에 남기는 단계를 담는다.
대기열과 스레드는 ``runner`` 가 맡는다. Streamlit API 를 부르지
않는다 — 워커 스레드에서 돈다.
"""

import logging
import pathlib

from notebooklm_st.core import models
from notebooklm_st.services import (
    run_history,
    run_registry,
    store,
    video_metadata,
)

logger = logging.getLogger(__name__)


def save_history(
    registry: run_registry.RunRegistry,
    run_id: str,
    result: models.RunResult,
    metadata: models.VideoMetadata | None,
    db_path: pathlib.Path,
) -> int | None:
    """결과를 이력에 남기고 이력 ID 를 돌려준다.

    실패하면 실행을 실패로 마감하고 ``None`` 을 돌려준다. 이력이 없으면
    올릴 것도 없으므로 자동 저장도 하지 않는다.
    """
    try:
        connection = store.connect(db_path)
        try:
            return run_history.save_run(connection, result, metadata)
        finally:
            connection.close()
    except Exception as error:
        # 스레드 최상위에서만 넓게 잡는다. 이력 저장이 실패했는데
        # 상태를 남기지 않으면 화면이 영원히 "실행 중" 에 머문다.
        logger.exception("실행 %s 이력 저장 실패", run_id)
        registry.fail(
            run_id,
            "답변은 받았으나 이력 저장에 실패했습니다"
            f"({type(error).__name__}): {error}",
            "error",
        )
        return None


def fetch_metadata(
    registry: run_registry.RunRegistry, run_id: str, url: str
) -> models.VideoMetadata | None:
    """영상 메타데이터를 조회하고 진행 문구를 남긴다.

    ``video_metadata.fetch`` 는 실패를 예외가 아니라 값으로 돌려주는
    계약이지만, 그 계약이 어디선가 깨지더라도 이 함수 밖으로 예외가
    새면 안 된다. 메타데이터는 부가물이라 요약 자체를 막을 이유가
    없는데, 예외가 새는 순간 화면이 영원히 "실행 중" 에 머무는 이
    앱 최악의 실패 모드로 이어진다. ``fetch`` 자신의 계약 뒤에 놓는
    마지막 방어선이라 이 넓은 catch 를 둔다.

    Args:
        registry: 진행 문구를 남길 레지스트리.
        run_id: 진행 문구를 붙일 실행 ID.
        url: 조회할 영상 URL.

    Returns:
        조회된 메타데이터. 못 가져왔으면 ``None``.
    """
    registry.append_progress(run_id, "영상 정보 확인 중")
    try:
        meta = video_metadata.fetch(url)
    except Exception:
        # 위 docstring 참고 — 여기서 예외가 새면 요약 자체가
        # 시작되지 못한 채 실행이 running 에 머문다.
        logger.exception("실행 %s 메타데이터 조회 중 예외", run_id)
        registry.append_progress(run_id, "영상 정보를 가져오지 못했습니다")
        return None
    if meta.error is not None:
        # 메타데이터는 부가물이다. 못 가져와도 요약은 끝까지 간다.
        logger.info("실행 %s 메타데이터 실패: %s", run_id, meta.error)
        registry.append_progress(
            run_id, f"영상 정보를 가져오지 못했습니다: {meta.error}"
        )
        return None
    return meta.metadata
```

- [ ] **Step 4: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
♻️ refactor(runner): 워커 단계를 services/run_steps 로 옮기기

services/runner.py 가 이미 300줄이라 카테고리를 이력에 넘기는 인자를
더할 자리가 없다. 실행 하나의 두 단계(_fetch_metadata·_save_history)를
run_steps 의 공개 함수로 내용 그대로 옮긴다. 동작은 바뀌지 않는다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/services/runner.py \
  src/notebooklm_st/services/run_steps.py \
  tests/services/test_runner_queue.py \
  tests/services/test_runner_start.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 3: 카테고리 이름 규칙 — `core/category_names.py`

**Files:**
- Create: `src/notebooklm_st/core/category_names.py`, `tests/core/test_category_names.py`
- Modify: `src/notebooklm_st/core/markdown_export.py`(구분자 상수)

**Interfaces:**
- Produces: `markdown_export.CATEGORY_SEPARATOR = ","`; `category_names.MAX_LENGTH = 30`, `ALLOWED_SYMBOLS`, `validate(name: str) -> str`(어기면 `ValueError`), `is_valid(name: str) -> bool`, `ordered(names: Iterable[str]) -> tuple[str, ...]`(중복 제거·정렬), `split(value: str) -> tuple[str, ...]`(쉼표로 나누고 규칙 밖 조각은 버림).

설계서 §6.1. `category_names` 가 `markdown_export` 를 import 한다. 반대 방향 import 는 두지 않는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/core/test_category_names.py` 를 새로 만든다.

```python
"""카테고리 이름 규칙 테스트."""

import pytest

from notebooklm_st.core import category_names


def test_validate_trims_and_folds_whitespace() -> None:
    """앞뒤 공백을 자르고 겹친 공백을 하나로 접는다."""
    assert category_names.validate("  인공 \t 지능 ") == "인공 지능"


def test_validate_drops_control_characters() -> None:
    """제어문자를 지운다."""
    assert category_names.validate("경\x00제") == "경제"


@pytest.mark.parametrize("name", ["", "   ", "\x00"])
def test_validate_rejects_an_empty_name(name: str) -> None:
    """다듬은 뒤 비었으면 거부한다."""
    with pytest.raises(ValueError, match="비어 있습니다"):
        category_names.validate(name)


def test_validate_accepts_thirty_characters() -> None:
    """30자까지 받는다."""
    name = "가" * 30

    assert category_names.validate(name) == name


def test_validate_rejects_thirty_one_characters() -> None:
    """31자는 거부한다."""
    with pytest.raises(ValueError, match="30자"):
        category_names.validate("가" * 31)


@pytest.mark.parametrize(
    "char", [",", "*", "_", "`", "[", "]", "~", "=", "<", "#", "|", "\\"]
)
def test_validate_rejects_separator_and_markdown_characters(
    char: str,
) -> None:
    """쉼표와 마크다운 서식에 쓰이는 글자는 거부한다."""
    with pytest.raises(ValueError, match="쓸 수 있습니다"):
        category_names.validate(f"경제{char}정책")


@pytest.mark.parametrize(
    "name",
    [
        "경제",
        "AI",
        "Web3",
        "R&D",
        "C++",
        "A/B 테스트",
        "경제(거시)",
        "v1.2",
        "AI·데이터",
        "인공-지능",
    ],
)
def test_validate_accepts_letters_digits_and_allowed_symbols(
    name: str,
) -> None:
    """글자·숫자·공백과 허용한 기호는 그대로 받는다."""
    assert category_names.validate(name) == name


def test_is_valid_follows_validate() -> None:
    """``validate`` 가 받으면 참, 거부하면 거짓이다."""
    assert category_names.is_valid("경제")
    assert not category_names.is_valid("경제,정책")


def test_ordered_removes_duplicates_and_sorts() -> None:
    """중복을 빼고 파이썬 기본 문자열 순서로 늘어놓는다."""
    names = ["인공지능", "경제", "AI", "경제"]

    assert category_names.ordered(names) == ("AI", "경제", "인공지능")


def test_split_reads_comma_separated_names() -> None:
    """쉼표로 이은 값을 이름들로 나눈다."""
    assert category_names.split("인공지능, 경제") == ("경제", "인공지능")


def test_split_drops_empty_and_blank_pieces() -> None:
    """빈 조각과 공백뿐인 조각은 버린다."""
    assert category_names.split(" , 경제,, ") == ("경제",)


def test_split_drops_only_the_invalid_pieces() -> None:
    """규칙에 맞지 않는 조각만 버리고 나머지는 살린다."""
    value = "경제, *강조*, 인공지능"

    assert category_names.split(value) == ("경제", "인공지능")


def test_split_removes_duplicates() -> None:
    """같은 이름이 두 번 나오면 한 번만 남긴다."""
    assert category_names.split("경제, 경제") == ("경제",)


def test_split_of_an_empty_value_is_empty() -> None:
    """빈 값은 빈 결과다."""
    assert category_names.split("") == ()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest tests/core/test_category_names.py -q
```

기대: 수집 단계 오류 하나(`ImportError: cannot import name 'category_names'`).

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/core/markdown_export.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/core/markdown_export.py b/src/notebooklm_st/core/markdown_export.py
--- a/src/notebooklm_st/core/markdown_export.py
+++ b/src/notebooklm_st/core/markdown_export.py
@@ -38,6 +38,13 @@ CHANNEL_LABEL = "채널"
 UPLOAD_DATE_LABEL = "업로드 일자"
 """메타데이터 리스트에서 업로드 일자 줄의 라벨. 읽는 쪽은 채널과 같다."""
 
+CATEGORY_SEPARATOR = ","
+"""카테고리 줄에서 이름을 가르는 글자.
+
+``category_names`` 가 이 글자를 이름에 쓰지 못하게 막고, 같은 글자로
+줄을 다시 나눈다.
+"""
+
 
 def to_markdown(
     summary: models.RunSummary,
```

`src/notebooklm_st/core/category_names.py` 를 새로 만든다.

```python
"""카테고리 이름의 규칙.

관리 화면(``services.categories``)과 문서 읽기
(``core.outline_import``)가 같은 규칙을 쓴다. 그래야 앱이 받지 않는
이름이 동기화로 들어오지 않는다.

이름은 Outline 문서 머리의 한 줄에 쉼표로 이어 적힌다. 그래서 쉼표를
쓰지 못하고, Outline 이 서식으로 읽을 수 있는 마크다운 글자도 쓰지
못한다. 막을 글자를 늘어놓는 대신 쓸 수 있는 글자를 정한다 — 모르는
서식 글자가 새로 생겨도 새지 않는다.
"""

from collections.abc import Iterable

from notebooklm_st.core import markdown_export

MAX_LENGTH = 30
"""이름의 최대 글자 수."""

ALLOWED_SYMBOLS = frozenset(" -.&+/()·")
"""글자·숫자 말고 이름에 쓸 수 있는 글자. 공백을 포함한다."""


def validate(name: str) -> str:
    """이름을 다듬고 규칙에 맞는지 확인한다.

    제어문자를 지우고 공백을 접는다(``markdown_export.one_line``).
    글자·숫자는 ``str.isalnum`` 으로 가린다. 밑줄은 여기서 거짓이라
    막힌다.

    Args:
        name: 사람이 입력했거나 문서에서 읽은 이름.

    Returns:
        다듬은 이름.

    Raises:
        ValueError: 비었거나, 길거나, 쓸 수 없는 글자가 있는 경우.
    """
    cleaned = markdown_export.one_line(name)
    if not cleaned:
        raise ValueError("카테고리 이름이 비어 있습니다.")
    if len(cleaned) > MAX_LENGTH:
        raise ValueError(f"카테고리 이름은 {MAX_LENGTH}자까지입니다.")
    if not all(char.isalnum() or char in ALLOWED_SYMBOLS for char in cleaned):
        raise ValueError(
            "카테고리 이름에는 글자·숫자·공백과 - . & + / ( ) · 만"
            " 쓸 수 있습니다."
        )
    return cleaned


def is_valid(name: str) -> bool:
    """이름이 규칙에 맞는지 알려 준다.

    Args:
        name: 검사할 이름.

    Returns:
        ``validate`` 가 받으면 참.
    """
    try:
        validate(name)
    except ValueError:
        return False
    return True


def ordered(names: Iterable[str]) -> tuple[str, ...]:
    """중복을 빼고 파이썬 기본 문자열 순서로 늘어놓는다.

    저장·동기화·표가 모두 이 순서를 쓴다. SQL 로 정하지 않는 것은
    운영 이미지의 SQLite 가 집계 함수 안의 정렬을 모르기 때문이다
    (설계서 §2.9).

    Args:
        names: 늘어놓을 이름들.

    Returns:
        정렬한 이름들.
    """
    return tuple(sorted(set(names)))


def split(value: str) -> tuple[str, ...]:
    """문서 머리 줄의 값을 이름들로 나눈다.

    조각마다 ``validate`` 와 같게 다듬고, 비었거나 규칙에 맞지 않는
    조각은 버린다. 사람이 Outline 에서 줄을 고치며 섞어 넣은 것까지
    받지는 않는다.

    Args:
        value: ``- 카테고리:`` 뒤의 값. 역슬래시 이스케이프는 부르는
            쪽이 이미 걷었다.

    Returns:
        규칙에 맞는 이름들. 중복을 빼고 정렬했다.
    """
    pieces = value.split(markdown_export.CATEGORY_SEPARATOR)
    cleaned = (markdown_export.one_line(piece) for piece in pieces)
    return ordered(name for name in cleaned if is_valid(name))
```

- [ ] **Step 4: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `894 passed, 1 skipped`.

- [ ] **Step 5: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
✨ feat(categories): 카테고리 이름 규칙 추가

카테고리 이름은 Outline 문서 머리의 한 줄에 쉼표로 이어 적힌다.
관리 화면과 동기화가 같은 규칙을 쓰도록 core/category_names 에
다듬기·검사·정렬·나누기를 둔다. 마크다운 서식 글자가 새지 않게
쓸 수 있는 글자를 허용 목록으로 정한다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/core/category_names.py \
  src/notebooklm_st/core/markdown_export.py \
  tests/core/test_category_names.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 4: 카테고리 테이블과 저장소

**Files:**
- Create: `src/notebooklm_st/services/categories.py`, `tests/services/test_categories.py`
- Modify: `src/notebooklm_st/services/store.py`, `src/notebooklm_st/core/models.py`
- Test: `tests/services/test_store.py`

**Interfaces:**
- Consumes: `category_names.validate` (Task 3).
- Produces: 테이블 `categories(id, name UNIQUE, created_at, updated_at)`·`run_categories(run_id→runs CASCADE, category_id→categories RESTRICT)`·`channel_categories(channel_pk→channels CASCADE, category_id→categories CASCADE)`; `models.Category(id, name, created_at, updated_at)`; `categories.CategoryUsage(runs: int, channels: int)`, `list_categories(connection) -> list[models.Category]`(이름 순), `add_category(connection, name) -> models.Category`, `rename_category(connection, category_id, name) -> None`, `delete_category(connection, category_id) -> None`, `usage(connection, category_id) -> CategoryUsage`, `ensure(connection, names) -> int`(커밋하지 않음).

설계서 §5.1·§5.2·§7.2. 이 Task 의 테스트는 실행과 채널을 SQL 로 직접 잇는다 — 잇는 함수는 Task 5·9 가 만든다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_store.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/services/test_store.py b/tests/services/test_store.py
--- a/tests/services/test_store.py
+++ b/tests/services/test_store.py
@@ -4,7 +4,14 @@ import sqlite3
 
 import pytest
 
-from notebooklm_st.services import channels, settings, store
+from notebooklm_st.core import models
+from notebooklm_st.services import (
+    categories,
+    channels,
+    run_history,
+    settings,
+    store,
+)
 
 
 def test_default_db_path_honors_env_override(monkeypatch, tmp_path) -> None:
@@ -278,3 +285,102 @@ def test_connect_rejects_a_settings_table_without_the_value(tmp_path) -> None:
         store.connect(path)
     assert "settings 테이블" in str(excinfo.value)
     assert "['value']" in str(excinfo.value)
+
+
+def test_a_database_without_category_tables_still_opens(tmp_path) -> None:
+    """카테고리 테이블이 없는 기존 DB 도 지우지 않고 열린다."""
+    path = tmp_path / "old.db"
+    store.connect(path).close()
+    old = sqlite3.connect(path)
+    old.executescript(
+        "DROP TABLE run_categories; DROP TABLE channel_categories;"
+        " DROP TABLE categories;"
+    )
+    old.commit()
+    old.close()
+
+    connection = store.connect(path)
+    try:
+        assert categories.list_categories(connection) == []
+    finally:
+        connection.close()
+
+
+def _run_with_category(connection: sqlite3.Connection) -> tuple[int, int]:
+    """실행 하나와 카테고리 하나를 만들어 SQL 로 잇는다.
+
+    Returns:
+        (실행 ID, 카테고리 ID).
+    """
+    category = categories.add_category(connection, "경제")
+    run_id = run_history.save_run(
+        connection,
+        models.RunResult(
+            url="https://youtu.be/dQw4w9WgXcQ",
+            video_id="dQw4w9WgXcQ",
+            items=(),
+        ),
+    )
+    connection.execute(
+        "INSERT INTO run_categories (run_id, category_id) VALUES (?, ?)",
+        (run_id, category.id),
+    )
+    connection.commit()
+    return run_id, category.id
+
+
+def _count(connection: sqlite3.Connection, table: str) -> int:
+    """테이블의 행 수. 테이블 이름은 테스트가 쓴 리터럴이다."""
+    row = connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
+    return int(row["n"])
+
+
+def test_deleting_a_run_drops_its_category_links(tmp_path) -> None:
+    """실행을 지우면 카테고리 연결도 지워진다.
+
+    실행 ID 는 다시 쓰이므로, 연결이 남으면 같은 ID 를 받은 새 실행이
+    옛 카테고리를 물려받는다.
+    """
+    connection = store.connect(tmp_path / "test.db")
+    run_id, _ = _run_with_category(connection)
+
+    run_history.delete_run(connection, run_id)
+
+    assert _count(connection, "run_categories") == 0
+    connection.close()
+
+
+def test_a_category_on_a_run_cannot_be_deleted_by_sql(tmp_path) -> None:
+    """이력에 붙은 카테고리는 SQL 로도 지워지지 않는다(안전망)."""
+    connection = store.connect(tmp_path / "test.db")
+    _, category_id = _run_with_category(connection)
+
+    with pytest.raises(sqlite3.IntegrityError):
+        connection.execute(
+            "DELETE FROM categories WHERE id = ?", (category_id,)
+        )
+    connection.close()
+
+
+def test_deleting_a_channel_drops_its_default_categories(tmp_path) -> None:
+    """채널을 지우면 기본 카테고리 연결도 지워진다."""
+    connection = store.connect(tmp_path / "test.db")
+    category = categories.add_category(connection, "경제")
+    channel = channels.add_channel(
+        connection,
+        "UC" + "a" * 22,
+        "채널",
+        "https://www.youtube.com/@channel",
+        "2026-09-01",
+    )
+    connection.execute(
+        "INSERT INTO channel_categories (channel_pk, category_id)"
+        " VALUES (?, ?)",
+        (channel.id, category.id),
+    )
+    connection.commit()
+
+    channels.delete_channel(connection, channel.id)
+
+    assert _count(connection, "channel_categories") == 0
+    connection.close()
```

`tests/services/test_categories.py` 를 새로 만든다.

```python
"""카테고리 저장소 테스트."""

import sqlite3
from collections.abc import Iterator

import pytest

from notebooklm_st.core import models
from notebooklm_st.services import categories, channels, run_history, store


@pytest.fixture
def connection(tmp_path) -> Iterator[sqlite3.Connection]:
    """임시 파일 DB 커넥션을 열고 테스트 후 닫는다."""
    conn = store.connect(tmp_path / "test.db")
    yield conn
    conn.close()


def use_on_run(connection: sqlite3.Connection, category_id: int) -> int:
    """실행 하나를 만들어 그 카테고리를 SQL 로 잇는다.

    Returns:
        만든 실행의 ID.
    """
    run_id = run_history.save_run(
        connection,
        models.RunResult(
            url="https://youtu.be/dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
            items=(),
        ),
    )
    connection.execute(
        "INSERT INTO run_categories (run_id, category_id) VALUES (?, ?)",
        (run_id, category_id),
    )
    connection.commit()
    return run_id


def use_on_channel(connection: sqlite3.Connection, category_id: int) -> int:
    """채널 하나를 등록해 그 카테고리를 SQL 로 기본값에 잇는다.

    Returns:
        만든 채널의 행 ID.
    """
    channel = channels.add_channel(
        connection,
        "UC" + "a" * 22,
        "채널",
        "https://www.youtube.com/@channel",
        "2026-09-01",
    )
    connection.execute(
        "INSERT INTO channel_categories (channel_pk, category_id)"
        " VALUES (?, ?)",
        (channel.id, category_id),
    )
    connection.commit()
    return channel.id


def names(connection: sqlite3.Connection) -> list[str]:
    """등록된 이름을 목록 순서로."""
    return [item.name for item in categories.list_categories(connection)]


def test_add_category_returns_the_cleaned_name(connection) -> None:
    """앞뒤 공백을 잘라 저장하고 저장한 카테고리를 돌려준다."""
    category = categories.add_category(connection, "  경제  ")

    assert category.name == "경제"
    assert categories.list_categories(connection) == [category]


def test_list_categories_is_ordered_by_name(connection) -> None:
    """목록은 등록 순서가 아니라 이름 순서다."""
    for name in ("인공지능", "경제", "AI"):
        categories.add_category(connection, name)

    assert names(connection) == ["AI", "경제", "인공지능"]


def test_add_category_rejects_a_duplicate_name(connection) -> None:
    """같은 이름은 두 번 등록하지 않는다."""
    categories.add_category(connection, "경제")

    with pytest.raises(ValueError, match="'경제' 카테고리가 이미 있습니다"):
        categories.add_category(connection, " 경제 ")
    assert names(connection) == ["경제"]


def test_add_category_rejects_an_invalid_name(connection) -> None:
    """이름 규칙에 맞지 않으면 저장하지 않는다."""
    with pytest.raises(ValueError, match="쓸 수 있습니다"):
        categories.add_category(connection, "경제,정책")
    assert names(connection) == []


def test_rename_category_changes_the_name(connection) -> None:
    """이름을 바꾸고 고친 시각을 새로 적는다."""
    category = categories.add_category(connection, "경제")
    connection.execute(
        "UPDATE categories SET updated_at = '2000-01-01T00:00:00'"
    )
    connection.commit()

    categories.rename_category(connection, category.id, "거시경제")

    [renamed] = categories.list_categories(connection)
    assert renamed.name == "거시경제"
    assert renamed.updated_at != "2000-01-01T00:00:00"


def test_rename_category_to_its_own_name_is_allowed(connection) -> None:
    """자기 이름 그대로 저장해도 중복으로 보지 않는다."""
    category = categories.add_category(connection, "경제")

    categories.rename_category(connection, category.id, "경제")

    assert names(connection) == ["경제"]


def test_rename_category_rejects_another_category_name(connection) -> None:
    """다른 카테고리가 쓰는 이름으로는 바꾸지 않는다."""
    categories.add_category(connection, "경제")
    other = categories.add_category(connection, "정치")

    with pytest.raises(ValueError, match="이미 있습니다"):
        categories.rename_category(connection, other.id, "경제")
    assert names(connection) == ["경제", "정치"]


def test_rename_category_rejects_an_unknown_id(connection) -> None:
    """없는 카테고리는 바꿀 수 없다."""
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        categories.rename_category(connection, 99, "경제")


def test_rename_category_refuses_one_used_by_a_run(connection) -> None:
    """이력에서 쓰는 카테고리는 이름을 바꾸지 않는다.

    이미 Outline 문서 머리에 적힌 이름과 어긋나기 때문이다.
    """
    category = categories.add_category(connection, "경제")
    use_on_run(connection, category.id)

    with pytest.raises(ValueError, match="이력에서 쓰는 카테고리"):
        categories.rename_category(connection, category.id, "거시경제")
    assert names(connection) == ["경제"]


def test_delete_category_removes_it(connection) -> None:
    """쓰지 않는 카테고리는 지운다."""
    category = categories.add_category(connection, "경제")

    categories.delete_category(connection, category.id)

    assert names(connection) == []


def test_delete_category_refuses_one_used_by_a_run(connection) -> None:
    """이력에서 쓰는 카테고리는 지우지 않는다."""
    category = categories.add_category(connection, "경제")
    use_on_run(connection, category.id)

    with pytest.raises(ValueError, match="이력에서 쓰는 카테고리"):
        categories.delete_category(connection, category.id)
    assert names(connection) == ["경제"]


def test_delete_category_used_only_by_a_channel(connection) -> None:
    """채널 기본값으로만 쓰이면 지울 수 있고, 그 연결도 사라진다."""
    category = categories.add_category(connection, "경제")
    use_on_channel(connection, category.id)

    categories.delete_category(connection, category.id)

    assert names(connection) == []
    row = connection.execute(
        "SELECT COUNT(*) AS n FROM channel_categories"
    ).fetchone()
    assert row["n"] == 0


def test_usage_counts_runs_and_channels(connection) -> None:
    """이 카테고리를 쓰는 이력 수와 채널 수를 센다."""
    category = categories.add_category(connection, "경제")
    unused = categories.add_category(connection, "정치")
    use_on_run(connection, category.id)
    use_on_run(connection, category.id)
    use_on_channel(connection, category.id)

    assert categories.usage(connection, category.id) == (
        categories.CategoryUsage(runs=2, channels=1)
    )
    assert categories.usage(connection, unused.id) == (
        categories.CategoryUsage(runs=0, channels=0)
    )


def test_ensure_adds_only_new_names(connection) -> None:
    """없는 이름만 넣고 새로 넣은 수를 돌려준다."""
    categories.add_category(connection, "경제")

    added = categories.ensure(connection, ["경제", "인공지능", "정치"])
    connection.commit()

    assert added == 2
    assert names(connection) == ["경제", "인공지능", "정치"]


def test_ensure_does_not_commit(connection) -> None:
    """트랜잭션은 호출자가 소유한다."""
    categories.ensure(connection, ["경제"])
    connection.rollback()

    assert names(connection) == []
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest tests/services/test_categories.py tests/services/test_store.py -q
```

기대: 두 파일 모두 수집 단계 오류(`ImportError: cannot import name 'categories'`).

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/services/store.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/services/store.py b/src/notebooklm_st/services/store.py
--- a/src/notebooklm_st/services/store.py
+++ b/src/notebooklm_st/services/store.py
@@ -66,6 +66,29 @@ CREATE TABLE IF NOT EXISTS settings (
     key   TEXT PRIMARY KEY,
     value TEXT NOT NULL
 );
+
+CREATE TABLE IF NOT EXISTS categories (
+    id         INTEGER PRIMARY KEY,
+    name       TEXT NOT NULL UNIQUE,
+    created_at TEXT NOT NULL,
+    updated_at TEXT NOT NULL
+);
+
+CREATE TABLE IF NOT EXISTS run_categories (
+    run_id      INTEGER NOT NULL REFERENCES runs(id)
+                ON DELETE CASCADE,
+    category_id INTEGER NOT NULL REFERENCES categories(id)
+                ON DELETE RESTRICT,
+    PRIMARY KEY (run_id, category_id)
+);
+
+CREATE TABLE IF NOT EXISTS channel_categories (
+    channel_pk  INTEGER NOT NULL REFERENCES channels(id)
+                ON DELETE CASCADE,
+    category_id INTEGER NOT NULL REFERENCES categories(id)
+                ON DELETE CASCADE,
+    PRIMARY KEY (channel_pk, category_id)
+);
 """
 
 # 이 프로젝트는 마이그레이션을 지원하지 않는다(의도된 결정). 예전
@@ -106,6 +129,9 @@ _EXPECTED_COLUMNS: dict[str, frozenset[str]] = {
         {"id", "channel_id", "title", "url", "baseline", "created_at"}
     ),
     "settings": frozenset({"key", "value"}),
+    "categories": frozenset({"id", "name", "created_at", "updated_at"}),
+    "run_categories": frozenset({"run_id", "category_id"}),
+    "channel_categories": frozenset({"channel_pk", "category_id"}),
 }
```

`src/notebooklm_st/core/models.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/core/models.py b/src/notebooklm_st/core/models.py
--- a/src/notebooklm_st/core/models.py
+++ b/src/notebooklm_st/core/models.py
@@ -17,6 +17,19 @@ class Question:
     updated_at: str
 
 
+@dataclasses.dataclass(frozen=True, slots=True)
+class Category:
+    """사용자가 관리하는 주제 표시.
+
+    질의할 때 하나 이상 고르고, Outline 문서 머리에 적힌다.
+    """
+
+    id: int
+    name: str
+    created_at: str
+    updated_at: str
+
+
 @dataclasses.dataclass(frozen=True, slots=True)
 class Channel:
     """구독 중인 채널 하나."""
```

`src/notebooklm_st/services/categories.py` 를 새로 만든다.

```python
"""카테고리 저장소.

연결과 스키마는 ``store`` 가 맡고, 이름 규칙은
``core.category_names`` 가 맡는다. 실행과 채널에 잇는 일은 그 행을
쓰는 저장소(``run_history``·``channels``)가 한다.

**이력에서 쓰는 카테고리는 이름을 바꾸거나 지우지 않는다.** 이미
Outline 문서 머리에 적힌 이름과 어긋나기 때문이다. 대기 중인 질의가
쥔 카테고리는 레지스트리를 아는 화면이 따로 막는다.
"""

import dataclasses
import sqlite3
from collections.abc import Sequence

from notebooklm_st.core import category_names, models
from notebooklm_st.services import store

_IN_USE = "이력에서 쓰는 카테고리는 이름을 바꾸거나 지울 수 없습니다."


@dataclasses.dataclass(frozen=True, slots=True)
class CategoryUsage:
    """카테고리 하나를 쓰는 곳의 수."""

    runs: int
    """이 카테고리가 붙은 이력 행 수."""

    channels: int
    """이 카테고리를 기본값으로 둔 채널 수."""


def list_categories(
    connection: sqlite3.Connection,
) -> list[models.Category]:
    """등록된 카테고리를 이름 순서로 돌려준다.

    SQLite 의 기본 비교는 바이트 순이고, UTF-8 에서는 코드 포인트
    순과 같다. ``category_names.ordered`` 와 같은 순서다.

    Args:
        connection: 열린 커넥션.

    Returns:
        카테고리 목록.
    """
    rows = connection.execute(
        "SELECT id, name, created_at, updated_at FROM categories ORDER BY name"
    ).fetchall()
    return [_to_category(row) for row in rows]


def add_category(connection: sqlite3.Connection, name: str) -> models.Category:
    """새 카테고리를 등록한다.

    Args:
        connection: 열린 커넥션.
        name: 이름. ``category_names.validate`` 로 다듬는다.

    Returns:
        저장된 카테고리.

    Raises:
        ValueError: 이름이 규칙에 맞지 않거나 같은 이름이 이미 있는
            경우.
    """
    cleaned = category_names.validate(name)
    _require_unique_name(connection, cleaned, None)
    now = store.now()
    row = connection.execute(
        "INSERT INTO categories (name, created_at, updated_at)"
        " VALUES (?, ?, ?)"
        " RETURNING id, name, created_at, updated_at",
        (cleaned, now, now),
    ).fetchone()
    connection.commit()
    return _to_category(row)


def rename_category(
    connection: sqlite3.Connection, category_id: int, name: str
) -> None:
    """카테고리의 이름을 바꾼다.

    Args:
        connection: 열린 커넥션.
        category_id: 바꿀 카테고리의 ID.
        name: 새 이름. ``category_names.validate`` 로 다듬는다.

    Raises:
        ValueError: 이름이 규칙에 맞지 않거나, 다른 카테고리가 그
            이름을 쓰거나, 이력에서 쓰는 카테고리이거나, 그 ID 의
            카테고리가 없는 경우.
    """
    cleaned = category_names.validate(name)
    if usage(connection, category_id).runs > 0:
        raise ValueError(_IN_USE)
    _require_unique_name(connection, cleaned, category_id)
    cursor = connection.execute(
        "UPDATE categories SET name = ?, updated_at = ? WHERE id = ?",
        (cleaned, store.now(), category_id),
    )
    connection.commit()
    if cursor.rowcount == 0:
        raise ValueError(f"카테고리 {category_id} 을 찾을 수 없습니다.")


def delete_category(connection: sqlite3.Connection, category_id: int) -> None:
    """카테고리를 지운다. 이미 없으면 조용히 넘어간다.

    채널 기본값으로 둔 연결은 외래키가 함께 지운다.

    Args:
        connection: 열린 커넥션.
        category_id: 지울 카테고리의 ID.

    Raises:
        ValueError: 이력에서 쓰는 카테고리인 경우.
    """
    if usage(connection, category_id).runs > 0:
        raise ValueError(_IN_USE)
    connection.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    connection.commit()


def usage(connection: sqlite3.Connection, category_id: int) -> CategoryUsage:
    """카테고리 하나를 쓰는 이력과 채널의 수를 센다.

    Args:
        connection: 열린 커넥션.
        category_id: 셀 카테고리의 ID.

    Returns:
        이력 행 수와 채널 수.
    """
    row = connection.execute(
        "SELECT"
        " (SELECT COUNT(*) FROM run_categories WHERE category_id = ?)"
        " AS runs,"
        " (SELECT COUNT(*) FROM channel_categories WHERE category_id = ?)"
        " AS channels",
        (category_id, category_id),
    ).fetchone()
    return CategoryUsage(runs=int(row["runs"]), channels=int(row["channels"]))


def ensure(connection: sqlite3.Connection, names: Sequence[str]) -> int:
    """없는 이름만 카테고리로 넣는다.

    **커밋하지 않는다.** 이력 동기화가 쓰며, 트랜잭션은
    ``history_sync.apply`` 가 소유한다. 이름은 문서에서 읽을 때 이미
    규칙을 통과했다(``outline_import.find_categories``).

    Args:
        connection: 열린 커넥션.
        names: 넣을 이름들.

    Returns:
        새로 넣은 수.
    """
    now = store.now()
    added = 0
    for name in names:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO categories (name, created_at, updated_at)"
            " VALUES (?, ?, ?)",
            (name, now, now),
        )
        added += cursor.rowcount
    return added


def _require_unique_name(
    connection: sqlite3.Connection, name: str, category_id: int | None
) -> None:
    """같은 이름의 다른 카테고리가 있으면 예외를 던진다.

    ``id IS NOT ?`` 는 NULL 안전 비교라, ``category_id`` 가 ``None``
    이면 모든 행과 견주고 값이 있으면 그 행만 뺀다(질문과 같다).

    Raises:
        ValueError: 같은 이름의 다른 카테고리가 이미 있는 경우.
    """
    row = connection.execute(
        "SELECT id FROM categories WHERE name = ? AND id IS NOT ? LIMIT 1",
        (name, category_id),
    ).fetchone()
    if row is not None:
        raise ValueError(f"'{name}' 카테고리가 이미 있습니다.")


def _to_category(row: sqlite3.Row) -> models.Category:
    """DB 행을 ``Category`` 로 바꾼다."""
    return models.Category(
        id=int(row["id"]),
        name=row["name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
```

- [ ] **Step 4: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `913 passed, 1 skipped`.

- [ ] **Step 5: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
✨ feat(categories): 카테고리 테이블과 저장소 추가

categories·run_categories·channel_categories 세 테이블을 더한다.
기존 테이블은 그대로라 기존 DB 를 지우지 않고 연다. 카테고리 CRUD 는
질문과 같은 모양이고, 이력에서 쓰는 카테고리는 문서 머리와 어긋나지
않게 이름 변경과 삭제를 막는다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/core/models.py \
  src/notebooklm_st/services/categories.py \
  src/notebooklm_st/services/store.py \
  tests/services/test_categories.py \
  tests/services/test_store.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 5: 대기열 핸들과 이력이 카테고리를 쥐기

**Files:**
- Modify: `src/notebooklm_st/core/models.py`, `src/notebooklm_st/services/run_history.py`, `src/notebooklm_st/services/runs.py`, `src/notebooklm_st/services/run_store.py`, `src/notebooklm_st/services/runner.py`, `src/notebooklm_st/services/run_steps.py`
- Test: `tests/services/test_run_store.py`, `tests/services/test_run_history.py`, `tests/services/test_runner_start.py`

**Interfaces:**
- Consumes: `categories.add_category`·`delete_category` (Task 4, 테스트에서), `category_names.ordered` (Task 3).
- Produces: `models.RunSummary.categories: tuple[str, ...] = ()`(이름 순); `run_history.SUMMARY_SELECT` 의 `category_names` 칸; `run_history.save_run(connection, result, metadata=None, category_ids: Sequence[int] = ()) -> int`; `runs.RunHandle.category_ids: tuple[int, ...] = ()`(맨 끝); `RunStore.enqueue(url, video_id, questions, auto_save=False, category_ids: tuple[int, ...] = ())`; `runner.enqueue(registry, url, questions, db_path, auto_save, is_blocked, pipeline=…, category_ids: Sequence[int] = ())`; `run_steps.save_history(registry, run_id, result, metadata, category_ids, db_path)`.

설계서 §5.2·§5.4·§7.3·§7.7. `list_runs`·`load_run`·`list_exported` 가 같은 `SUMMARY_SELECT` 를 쓰므로 셋 모두 카테고리를 싣는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_run_store.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/services/test_run_store.py b/tests/services/test_run_store.py
--- a/tests/services/test_run_store.py
+++ b/tests/services/test_run_store.py
@@ -94,6 +94,22 @@ def test_enqueue_leaves_auto_save_off_by_default() -> None:
     assert handle.auto_save is False
 
 
+def test_enqueue_keeps_the_category_ids() -> None:
+    """넣는 순간 고른 카테고리 ID 를 핸들이 쥔다."""
+    store = run_store.RunStore()
+
+    handle = store.enqueue("u", "v", QUESTIONS, category_ids=(3, 1))
+
+    assert handle.category_ids == (3, 1)
+
+
+def test_enqueue_has_no_categories_by_default() -> None:
+    """카테고리를 넘기지 않으면 비어 있다."""
+    store = run_store.RunStore()
+
+    assert store.enqueue("u", "v", QUESTIONS).category_ids == ()
+
+
 def test_get_returns_none_for_unknown_id() -> None:
     """없는 ID 를 조회하면 None 을 돌려준다."""
     store = run_store.RunStore()
```

`tests/services/test_run_history.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/services/test_run_history.py b/tests/services/test_run_history.py
--- a/tests/services/test_run_history.py
+++ b/tests/services/test_run_history.py
@@ -6,7 +6,7 @@ from collections.abc import Iterator
 import pytest
 
 from notebooklm_st.core import models
-from notebooklm_st.services import run_history, run_links, store
+from notebooklm_st.services import categories, run_history, run_links, store
 
 
 @pytest.fixture
@@ -383,3 +383,83 @@ def test_load_run_carries_the_document_link(connection) -> None:
     assert summary is not None
     assert summary.exported_at is not None
     assert summary.answer_count == 0
+
+
+def add_categories(connection: sqlite3.Connection, *names: str) -> list[int]:
+    """카테고리를 등록하고 ID 를 넘긴 순서대로 돌려준다."""
+    return [categories.add_category(connection, name).id for name in names]
+
+
+def test_save_run_links_the_categories(connection) -> None:
+    """고른 카테고리를 이력에 잇고, 요약은 이름 순으로 싣는다."""
+    ids = add_categories(connection, "인공지능", "경제")
+
+    run_id = run_history.save_run(connection, make_result(), category_ids=ids)
+
+    summary = run_history.load_run(connection, run_id)
+    assert summary is not None
+    assert summary.categories == ("경제", "인공지능")
+
+
+def test_save_run_skips_a_category_deleted_meanwhile(connection) -> None:
+    """그사이 지워진 카테고리 ID 는 빼고 남긴다."""
+    kept, gone = add_categories(connection, "경제", "정치")
+    categories.delete_category(connection, gone)
+
+    run_id = run_history.save_run(
+        connection, make_result(), category_ids=[kept, gone]
+    )
+
+    summary = run_history.load_run(connection, run_id)
+    assert summary is not None
+    assert summary.categories == ("경제",)
+
+
+def test_save_run_ignores_a_repeated_category_id(connection) -> None:
+    """같은 ID 가 두 번 와도 한 번만 잇는다."""
+    [category_id] = add_categories(connection, "경제")
+
+    run_id = run_history.save_run(
+        connection, make_result(), category_ids=[category_id, category_id]
+    )
+
+    summary = run_history.load_run(connection, run_id)
+    assert summary is not None
+    assert summary.categories == ("경제",)
+
+
+def test_list_runs_carries_the_categories(connection) -> None:
+    """목록의 요약도 카테고리를 싣는다. 없으면 비어 있다."""
+    ids = add_categories(connection, "경제")
+    run_history.save_run(connection, make_result(), category_ids=ids)
+    run_history.save_run(connection, make_result())
+
+    newer, older = run_history.list_runs(connection)
+
+    assert newer.categories == ()
+    assert older.categories == ("경제",)
+
+
+def test_categories_do_not_inflate_the_answer_count(connection) -> None:
+    """카테고리가 여럿이어도 답변 수가 불지 않는다."""
+    ids = add_categories(connection, "경제", "정치", "AI")
+
+    run_id = run_history.save_run(connection, make_result(), category_ids=ids)
+
+    summary = run_history.load_run(connection, run_id)
+    assert summary is not None
+    assert summary.answer_count == 2
+
+
+def test_a_reused_run_id_inherits_no_categories(connection) -> None:
+    """지운 실행의 ID 를 다시 받은 실행은 카테고리를 물려받지 않는다."""
+    ids = add_categories(connection, "경제")
+    first = run_history.save_run(connection, make_result(), category_ids=ids)
+    run_history.delete_run(connection, first)
+
+    second = run_history.save_run(connection, make_result())
+
+    assert second == first
+    summary = run_history.load_run(connection, second)
+    assert summary is not None
+    assert summary.categories == ()
```

`tests/services/test_runner_start.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/services/test_runner_start.py b/tests/services/test_runner_start.py
--- a/tests/services/test_runner_start.py
+++ b/tests/services/test_runner_start.py
@@ -10,6 +10,7 @@ from notebooklm._auth import extraction as _auth_extraction
 
 from notebooklm_st.core import models
 from notebooklm_st.services import (
+    categories,
     outline,
     run_export,
     run_history,
@@ -698,3 +699,37 @@ def test_a_hidden_run_is_still_auto_saved(db_path, monkeypatch) -> None:
     assert registry.get(started.run_id) is None
     assert len(calls) == 1
     assert saved_runs(db_path)[0].outline_url == DOC_URL
+
+
+def test_finished_run_keeps_the_chosen_categories(db_path) -> None:
+    """넣을 때 고른 카테고리가 핸들을 거쳐 이력에 붙는다."""
+    connection = store.connect(db_path)
+    try:
+        ids = [categories.add_category(connection, "경제").id]
+    finally:
+        connection.close()
+    registry = run_registry.RunRegistry()
+
+    async def fake_pipeline(url, questions, on_progress, **kwargs):
+        """답변 없이 끝나는 가짜."""
+        return models.RunResult(url=url, video_id="dQw4w9WgXcQ", items=())
+
+    started = runner.enqueue(
+        registry,
+        URL,
+        make_questions("핵심 주장은?"),
+        db_path,
+        False,
+        never_blocked,
+        fake_pipeline,
+        category_ids=ids,
+    )
+    wait_for(registry, started.run_id)
+
+    assert started.category_ids == tuple(ids)
+    connection = store.connect(db_path)
+    try:
+        [summary] = run_history.list_runs(connection)
+    finally:
+        connection.close()
+    assert summary.categories == ("경제",)
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest tests/services/test_run_store.py tests/services/test_run_history.py tests/services/test_runner_start.py -q
```

기대: `9 failed` — 새로 쓴 아홉 건 모두(없는 키워드 인자 `category_ids`·속성 `category_ids`·`categories`).

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/core/models.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/core/models.py b/src/notebooklm_st/core/models.py
--- a/src/notebooklm_st/core/models.py
+++ b/src/notebooklm_st/core/models.py
@@ -146,6 +146,8 @@ class RunSummary:
     metadata: VideoMetadata | None = None
     """``run_metadata`` 행. 행이 없으면 ``None`` — 두 값이 빈 행과
     구분된다."""
+    categories: tuple[str, ...] = ()
+    """붙은 카테고리 이름. 이름 순이다."""
 
 
 @dataclasses.dataclass(frozen=True, slots=True)
```

`src/notebooklm_st/services/run_history.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/services/run_history.py b/src/notebooklm_st/services/run_history.py
--- a/src/notebooklm_st/services/run_history.py
+++ b/src/notebooklm_st/services/run_history.py
@@ -6,8 +6,9 @@
 """
 
 import sqlite3
+from collections.abc import Sequence
 
-from notebooklm_st.core import models
+from notebooklm_st.core import category_names, models
 from notebooklm_st.services import store
 
 
@@ -35,6 +36,10 @@ SUMMARY_SELECT = (
     "SELECT r.id, r.url, r.video_id, r.title, r.created_at,"
     " r.outline_id, r.outline_url, r.outline_title, r.exported_at,"
     " m.run_id AS metadata_run_id, m.channel, m.upload_date,"
+    " (SELECT group_concat(c.name, ',')"
+    " FROM run_categories AS rc"
+    " JOIN categories AS c ON c.id = rc.category_id"
+    " WHERE rc.run_id = r.id) AS category_names,"
     " COUNT(a.id) AS answer_count"
     " FROM runs AS r"
     " LEFT JOIN answers AS a ON a.run_id = r.id"
@@ -44,7 +49,10 @@ SUMMARY_SELECT = (
 함께 쓰는 SELECT 머리.
 
 ``run_metadata`` 는 실행 하나에 많아야 한 행이라 조인이 답변 행을
-불리지 않는다."""
+불리지 않는다. 카테고리는 서브쿼리라 마찬가지다. 이름에는 쉼표가
+없으므로(``core.category_names``) 쉼표로 이어도 다시 나눌 수 있다.
+순서는 SQL 이 아니라 ``row_to_summary`` 가 정한다 — 운영 이미지의
+SQLite 는 집계 함수 안의 정렬을 모른다."""
 
 
 def row_to_summary(row: sqlite3.Row) -> models.RunSummary:
@@ -53,6 +61,7 @@ def row_to_summary(row: sqlite3.Row) -> models.RunSummary:
     ``run_history_sync`` 도 이 함수를 그대로 가져다 쓴다. SQL 을
     두 모듈에 중복해 두지 않으려는 것이다.
     """
+    names = row["category_names"]
     metadata = None
     if row["metadata_run_id"] is not None:
         metadata = models.VideoMetadata(
@@ -70,6 +79,7 @@ def row_to_summary(row: sqlite3.Row) -> models.RunSummary:
         outline_title=row["outline_title"],
         exported_at=row["exported_at"],
         metadata=metadata,
+        categories=category_names.ordered(names.split(",")) if names else (),
     )
 
 
@@ -77,6 +87,7 @@ def save_run(
     connection: sqlite3.Connection,
     result: models.RunResult,
     metadata: models.VideoMetadata | None = None,
+    category_ids: Sequence[int] = (),
 ) -> int:
     """실행 결과를 이력으로 저장한다.
 
@@ -90,6 +101,9 @@ def save_run(
         metadata: 영상에서 뽑아 온 메타데이터. 없으면 행을 만들지
             않는다 — 빈 행과 없는 행이 같은 뜻이 되면 나중에
             구분하지 못한다.
+        category_ids: 넣을 때 고른 카테고리 ID. 그사이 지워진 ID 는
+            조용히 빠진다 — 이력 저장이 외래키 오류로 실패하는 것보다
+            낫다. 같은 ID 가 두 번 와도 한 번만 잇는다.
 
     Returns:
         저장된 실행의 ID.
@@ -124,6 +138,11 @@ def save_run(
             " VALUES (?, ?, ?)",
             (run_id, metadata.channel, metadata.upload_date),
         )
+    connection.executemany(
+        "INSERT OR IGNORE INTO run_categories (run_id, category_id)"
+        " SELECT ?, id FROM categories WHERE id = ?",
+        [(run_id, category_id) for category_id in category_ids],
+    )
     connection.commit()
     return run_id
```

`src/notebooklm_st/services/runs.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/services/runs.py b/src/notebooklm_st/services/runs.py
--- a/src/notebooklm_st/services/runs.py
+++ b/src/notebooklm_st/services/runs.py
@@ -66,3 +66,9 @@ class RunHandle:
     error_message: str | None
     error_level: MessageLevel | None
     finished_at: str | None
+    category_ids: tuple[int, ...] = ()
+    """넣는 순간 고른 카테고리 ID. 이름은 이력과 문서에 쓸 때 읽는다.
+
+    ID 로 쥐어, 대기 중에 이름이 바뀌어도 새 이름이 적힌다. 기본값이
+    있어 맨 끝에 둔다.
+    """
```

`src/notebooklm_st/services/run_store.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/services/run_store.py b/src/notebooklm_st/services/run_store.py
--- a/src/notebooklm_st/services/run_store.py
+++ b/src/notebooklm_st/services/run_store.py
@@ -31,6 +31,7 @@ class RunStore:
         video_id: str,
         questions: tuple[models.Question, ...],
         auto_save: bool = False,
+        category_ids: tuple[int, ...] = (),
     ) -> runs.RunHandle:
         """새 실행을 대기열 끝에 넣는다.
 
@@ -40,6 +41,7 @@ class RunStore:
             questions: 물어볼 질문들.
             auto_save: 답변을 받자마자 Outline 에 올릴지. 러너는 늘
                 값을 넘긴다. 기본값은 테스트가 핸들을 만들 때 쓴다.
+            category_ids: 고른 카테고리 ID. 기본값은 위와 같다.
 
         Returns:
             넣은 핸들. 보관소가 쥔 것과 같은 객체가 아니라 호출자가
@@ -60,6 +62,7 @@ class RunStore:
             error_message=None,
             error_level=None,
             finished_at=None,
+            category_ids=category_ids,
         )
         with self._lock:
             self._handles[handle.run_id] = handle
```

`src/notebooklm_st/services/runner.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/services/runner.py b/src/notebooklm_st/services/runner.py
--- a/src/notebooklm_st/services/runner.py
+++ b/src/notebooklm_st/services/runner.py
@@ -36,6 +36,7 @@ def enqueue(
     auto_save: bool,
     is_blocked: Callable[[], bool],
     pipeline: PipelineCallable = nlm.run_pipeline,
+    category_ids: Sequence[int] = (),
 ) -> runs.RunHandle:
     """질의를 대기열 끝에 넣고, 도는 워커가 없으면 띄운다.
 
@@ -55,6 +56,9 @@ def enqueue(
             동안 워커가 시작을 미룬다. 화면은 정리본 레지스트리의
             ``is_running`` 을 넘긴다.
         pipeline: 실행할 파이프라인. 테스트가 가짜를 넣게 뚫어 둔다.
+        category_ids: 고른 카테고리 ID. 핸들에 고정되고, 끝나면
+            이력에 붙는다. 화면은 늘 넘긴다. 기본값은 테스트의 기존
+            호출을 지킨다.
 
     Returns:
         넣은 실행의 핸들.
@@ -64,6 +68,7 @@ def enqueue(
         youtube.extract_video_id(url) or "",
         tuple(questions),
         auto_save,
+        tuple(category_ids),
     )
     if registry.acquire_worker():
         _start_worker(registry, db_path, is_blocked, pipeline)
@@ -217,7 +222,7 @@ def _work(
         raise
 
     history_id = run_steps.save_history(
-        registry, run_id, result, metadata, db_path
+        registry, run_id, result, metadata, handle.category_ids, db_path
     )
     if history_id is None:
         return
```

`src/notebooklm_st/services/run_steps.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/services/run_steps.py b/src/notebooklm_st/services/run_steps.py
--- a/src/notebooklm_st/services/run_steps.py
+++ b/src/notebooklm_st/services/run_steps.py
@@ -7,6 +7,7 @@
 
 import logging
 import pathlib
+from collections.abc import Sequence
 
 from notebooklm_st.core import models
 from notebooklm_st.services import (
@@ -24,6 +25,7 @@ def save_history(
     run_id: str,
     result: models.RunResult,
     metadata: models.VideoMetadata | None,
+    category_ids: Sequence[int],
     db_path: pathlib.Path,
 ) -> int | None:
     """결과를 이력에 남기고 이력 ID 를 돌려준다.
@@ -34,7 +36,9 @@ def save_history(
     try:
         connection = store.connect(db_path)
         try:
-            return run_history.save_run(connection, result, metadata)
+            return run_history.save_run(
+                connection, result, metadata, category_ids
+            )
         finally:
             connection.close()
     except Exception as error:
```

`RunSummary` 의 클래스 독스트링도 카테고리가 남는다고 고친다(설계서 §5.2).

```diff
diff --git a/src/notebooklm_st/core/models.py b/src/notebooklm_st/core/models.py
--- a/src/notebooklm_st/core/models.py
+++ b/src/notebooklm_st/core/models.py
@@ -129,8 +129,8 @@ class RunSummary:
     """이력 목록에 한 줄로 보여 줄 실행 요약.
 
     ``exported_at`` 이 채워져 있으면 이 실행은 Outline 으로 넘어갔고
-    로컬에는 링크와 영상 메타데이터만 남아 있다. 링크 넷은 항상 함께
-    채워지거나 함께 비어 있다.
+    로컬에는 링크와 영상 메타데이터, 카테고리만 남아 있다. 링크 넷은
+    항상 함께 채워지거나 함께 비어 있다.
     """
 
     id: int
```

- [ ] **Step 4: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `922 passed, 1 skipped`.

- [ ] **Step 5: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
✨ feat(categories): 대기열 핸들과 이력이 카테고리를 쥐기

넣는 순간 고른 카테고리 ID 를 핸들에 고정하고, 끝나면 이력에
잇는다. 그사이 지워진 ID 는 빼고 남긴다. 요약(RunSummary)은 이름 순
카테고리를 싣는다. 운영 SQLite 가 집계 함수 안의 정렬을 모르므로
순서는 파이썬에서 정한다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/core/models.py \
  src/notebooklm_st/services/run_history.py \
  src/notebooklm_st/services/run_steps.py \
  src/notebooklm_st/services/run_store.py \
  src/notebooklm_st/services/runner.py \
  src/notebooklm_st/services/runs.py \
  tests/services/test_run_history.py \
  tests/services/test_run_store.py \
  tests/services/test_runner_start.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 6: 카테고리 관리 화면

**Files:**
- Create: `src/notebooklm_st/pages/category_admin.py`, `tests/pages/test_category_admin.py`
- Modify: `src/notebooklm_st/app.py`
- Test: `tests/test_app.py`(독스트링 한 단어)

**Interfaces:**
- Consumes: `categories.*` (Task 4), `runs.PENDING`·`RunHandle.category_ids`·`session.get_registry()` (Task 5).
- Produces: `pages.category_admin.render()` — 네비게이션의 "카테고리 관리"(`url_path="categories"`, "질문 관리" 다음).

설계서 §8.1. 잠금은 화면이 먼저 판정하고, 서비스가 한 번 더 막는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_category_admin.py` 를 새로 만든다.

```python
"""카테고리 관리 화면 테스트."""

from streamlit.testing import v1

from notebooklm_st import session
from notebooklm_st.core import models
from notebooklm_st.services import categories, channels, run_history


def script():
    """AppTest 진입점 — 카테고리 관리 화면을 렌더한다."""
    from notebooklm_st.pages import category_admin

    category_admin.render()


def names(connection) -> list[str]:
    """등록된 이름을 목록 순서로."""
    return [item.name for item in categories.list_categories(connection)]


def captions(app) -> list[str]:
    """화면의 캡션 글자들."""
    return [item.value for item in app.caption]


def used_by_a_run(connection, category_id: int) -> None:
    """그 카테고리를 단 이력 하나를 남긴다."""
    run_history.save_run(
        connection,
        models.RunResult(
            url="https://youtu.be/dQw4w9WgXcQ",
            video_id="dQw4w9WgXcQ",
            items=(),
        ),
        category_ids=[category_id],
    )


def test_adding_a_category_lists_it(app_db) -> None:
    """이름을 넣고 등록하면 저장되고 목록에 나온다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input(key="category_new_name").set_value("경제").run()
    app.button(key="category_add").click().run()

    assert not app.exception
    assert names(app_db) == ["경제"]
    assert [item.label for item in app.expander] == ["경제"]


def test_a_duplicate_name_shows_the_reason(app_db) -> None:
    """같은 이름이면 오류를 보이고 저장하지 않는다."""
    categories.add_category(app_db, "경제")
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input(key="category_new_name").set_value("경제").run()
    app.button(key="category_add").click().run()

    assert any("이미 있습니다" in item.value for item in app.error)
    assert names(app_db) == ["경제"]


def test_an_invalid_name_shows_the_reason(app_db) -> None:
    """규칙에 맞지 않는 이름이면 쓸 수 있는 글자를 알린다."""
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input(key="category_new_name").set_value("경제,정치").run()
    app.button(key="category_add").click().run()

    assert any("쓸 수 있습니다" in item.value for item in app.error)
    assert names(app_db) == []


def test_renaming_a_category(app_db) -> None:
    """이름 칸을 고치고 수정을 누르면 이름이 바뀐다."""
    category = categories.add_category(app_db, "경제")
    app = v1.AppTest.from_function(script)
    app.run()
    app.text_input(key=f"category_name_{category.id}").set_value(
        "거시경제"
    ).run()
    app.button(key=f"category_rename_{category.id}").click().run()

    assert not app.exception
    assert names(app_db) == ["거시경제"]


def test_deleting_a_category(app_db) -> None:
    """삭제를 누르면 지워진다."""
    category = categories.add_category(app_db, "경제")
    app = v1.AppTest.from_function(script)
    app.run()
    app.button(key=f"category_delete_{category.id}").click().run()

    assert not app.exception
    assert names(app_db) == []


def test_an_unused_category_says_so(app_db) -> None:
    """쓰는 곳이 없으면 그렇다고 적고 잠그지 않는다."""
    category = categories.add_category(app_db, "경제")
    app = v1.AppTest.from_function(script).run()

    assert "아직 쓰는 곳이 없습니다." in captions(app)
    assert app.button(key=f"category_delete_{category.id}").disabled is False


def test_a_category_used_by_a_run_is_locked(app_db) -> None:
    """이력에서 쓰는 카테고리는 칸과 버튼이 잠기고 이유가 보인다."""
    category = categories.add_category(app_db, "경제")
    used_by_a_run(app_db, category.id)
    app = v1.AppTest.from_function(script).run()

    assert app.text_input(key=f"category_name_{category.id}").disabled
    assert app.button(key=f"category_rename_{category.id}").disabled
    assert app.button(key=f"category_delete_{category.id}").disabled
    assert "이력 1건" in captions(app)
    assert any("이력에서 쓰는 카테고리라" in text for text in captions(app))


def test_a_category_held_by_a_queued_run_is_locked(app_db) -> None:
    """대기 중인 질의가 쥔 카테고리도 잠긴다. 아직 이력은 없다."""
    category = categories.add_category(app_db, "경제")
    session.get_registry().enqueue(
        "https://youtu.be/dQw4w9WgXcQ",
        "dQw4w9WgXcQ",
        (),
        category_ids=(category.id,),
    )
    app = v1.AppTest.from_function(script).run()

    assert app.button(key=f"category_delete_{category.id}").disabled
    assert any("대기 중이거나 실행 중인 질의" in text for text in captions(app))


def test_a_channel_default_only_warns_before_deleting(app_db) -> None:
    """채널 기본값으로만 쓰이면 경고하고 지울 수 있게 둔다."""
    category = categories.add_category(app_db, "경제")
    channel = channels.add_channel(
        app_db,
        "UC" + "a" * 22,
        "채널",
        "https://www.youtube.com/@channel",
        "2026-09-01",
    )
    app_db.execute(
        "INSERT INTO channel_categories (channel_pk, category_id)"
        " VALUES (?, ?)",
        (channel.id, category.id),
    )
    app_db.commit()
    app = v1.AppTest.from_function(script)
    app.run()

    assert "채널 1개의 기본 카테고리" in captions(app)
    assert "지우면 채널 1개의 기본 카테고리에서도 빠집니다." in captions(app)
    app.button(key=f"category_delete_{category.id}").click().run()
    assert names(app_db) == []
```

`tests/test_app.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/test_app.py b/tests/test_app.py
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -4,6 +4,6 @@ from streamlit.testing import v1
 
 
 def test_app_boots_with_all_pages(app_db) -> None:
-    """여덟 페이지가 등록된 진입점이 예외 없이 부팅된다."""
+    """아홉 페이지가 등록된 진입점이 예외 없이 부팅된다."""
     app = v1.AppTest.from_file("../src/notebooklm_st/app.py").run()
     assert not app.exception
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest tests/pages/test_category_admin.py tests/test_app.py -q
```

기대: `9 failed, 1 passed` — 관리 화면 테스트 아홉 건(화면 모듈이 없다). 진입점 테스트는 그대로 통과한다.

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/pages/category_admin.py` 를 새로 만든다.

```python
"""카테고리 관리 화면.

질문 관리와 같은 모양이다. 이름을 바꾸거나 지울 수 없는 카테고리는
이름 칸과 버튼을 잠그고 이유를 적는다. 이력에서 쓰는 카테고리는
Outline 문서 머리에 적힌 이름과 어긋나게 되고, 대기 중인 질의가 쥔
카테고리는 곧 이력에 붙는다.
"""

import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import category_names, models
from notebooklm_st.services import categories, run_registry, runs

_NEW_NAME_KEY = "category_new_name"


def render() -> None:
    """새 카테고리 입력과 편집할 수 있는 목록을 그린다.

    등록 뒤에도 입력란의 글이 남는다. 질문 관리와 같은 이유로, 위젯이
    만들어진 뒤에 그 키를 건드리지 않는다.
    """
    st.title("카테고리 관리")
    st.caption(
        "카테고리는 질의할 때 하나 이상 골라야 합니다. Outline 문서"
        " 머리에 적히고, 정리본 재료를 거르는 데 쓰입니다."
    )
    connection = session.get_connection()
    name = st.text_input(
        "새 카테고리 이름",
        key=_NEW_NAME_KEY,
        max_chars=category_names.MAX_LENGTH,
    )
    if st.button("등록", key="category_add"):
        _add(connection, name)
    registry = session.get_registry()
    for category in categories.list_categories(connection):
        _render_row(connection, registry, category)


def _add(connection: sqlite3.Connection, name: str) -> None:
    """새 카테고리를 저장하고 화면을 다시 그린다."""
    try:
        categories.add_category(connection, name)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()


def _render_row(
    connection: sqlite3.Connection,
    registry: run_registry.RunRegistry,
    category: models.Category,
) -> None:
    """카테고리 하나를 쓰는 곳과 함께 그린다.

    잠그는 판정은 화면이 먼저 하고, 서비스가 한 번 더 막는다. 그사이
    다른 탭에서 이력이 생겨도 서비스가 거절한다.
    """
    usage = categories.usage(connection, category.id)
    queued = _is_queued(registry, category.id)
    locked = usage.runs > 0 or queued
    with st.expander(category.name):
        edited = st.text_input(
            "이름",
            value=category.name,
            key=f"category_name_{category.id}",
            max_chars=category_names.MAX_LENGTH,
            disabled=locked,
        )
        st.caption(_usage_text(usage))
        if locked:
            st.caption(_lock_reason(usage, queued))
        elif usage.channels:
            st.caption(
                f"지우면 채널 {usage.channels}개의 기본 카테고리에서도"
                " 빠집니다."
            )
        left, right = st.columns(2)
        if left.button(
            "수정", key=f"category_rename_{category.id}", disabled=locked
        ):
            _rename(connection, category.id, edited)
        if right.button(
            "삭제", key=f"category_delete_{category.id}", disabled=locked
        ):
            _delete(connection, category.id)


def _is_queued(registry: run_registry.RunRegistry, category_id: int) -> bool:
    """대기 중이거나 실행 중인 질의가 그 카테고리를 쥐었는가."""
    return any(
        handle.status in runs.PENDING and category_id in handle.category_ids
        for handle in registry.list_all()
    )


def _usage_text(usage: categories.CategoryUsage) -> str:
    """쓰는 곳을 한 줄로 적는다."""
    parts = []
    if usage.runs:
        parts.append(f"이력 {usage.runs}건")
    if usage.channels:
        parts.append(f"채널 {usage.channels}개의 기본 카테고리")
    return " · ".join(parts) or "아직 쓰는 곳이 없습니다."


def _lock_reason(usage: categories.CategoryUsage, queued: bool) -> str:
    """잠근 이유. 이력이 있으면 그쪽을 먼저 적는다."""
    holder = (
        "이력에서 쓰는 카테고리라"
        if usage.runs
        else "대기 중이거나 실행 중인 질의가 쓰는 카테고리라"
    )
    return f"{holder} 이름을 바꾸거나 지울 수 없습니다."


def _rename(
    connection: sqlite3.Connection, category_id: int, name: str
) -> None:
    """이름을 바꾸고 화면을 다시 그린다."""
    try:
        categories.rename_category(connection, category_id, name)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()


def _delete(connection: sqlite3.Connection, category_id: int) -> None:
    """카테고리를 지우고 화면을 다시 그린다."""
    try:
        categories.delete_category(connection, category_id)
    except ValueError as error:
        st.error(str(error))
        return
    st.rerun()
```

`src/notebooklm_st/app.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/app.py b/src/notebooklm_st/app.py
--- a/src/notebooklm_st/app.py
+++ b/src/notebooklm_st/app.py
@@ -21,6 +21,7 @@ from notebooklm_st.components import auth_gate, schema_gate
 from notebooklm_st.pages import (
     ask,
     auth,
+    category_admin,
     channels,
     dashboard,
     digest,
@@ -51,6 +52,11 @@ def main() -> None:
                 title="질문 관리",
                 url_path="questions",
             ),
+            st.Page(
+                category_admin.render,
+                title="카테고리 관리",
+                url_path="categories",
+            ),
             st.Page(history.render, title="이력", url_path="history"),
             st.Page(digest.render, title="정리본", url_path="digest"),
             st.Page(maintenance.render, title="정리", url_path="maintenance"),
```

- [ ] **Step 4: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `931 passed, 1 skipped`.

- [ ] **Step 5: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
✨ feat(categories): 카테고리 관리 화면 추가

질문 관리와 같은 모양의 화면을 더한다. 이력에서 쓰거나 대기 중인
질의가 쥔 카테고리는 이름 칸과 버튼을 잠그고 이유를 적는다.
채널 기본값으로만 쓰이면 지울 수 있고, 그 채널에서도 빠진다고
알린다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/app.py \
  src/notebooklm_st/pages/category_admin.py \
  tests/pages/test_category_admin.py \
  tests/test_app.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 7: 요약본 문서 머리에 카테고리 줄 쓰기

**Files:**
- Modify: `src/notebooklm_st/core/markdown_export.py`, `src/notebooklm_st/pages/history.py`(도움말 한 줄)
- Test: `tests/core/test_markdown_export.py`, `tests/services/test_runner_start.py`, `tests/services/test_run_export.py`

**Interfaces:**
- Consumes: `markdown_export.CATEGORY_SEPARATOR` (Task 3), `RunSummary.categories`·`runner.enqueue(category_ids=…)` (Task 5).
- Produces: `markdown_export.CATEGORY_LABEL = "카테고리"`, `markdown_export.category_line(names: Sequence[str]) -> str | None`. 정리본(Task 13)이 같은 줄 함수를 쓴다.

설계서 §6.2·§7.8·§8.7. 저장 경로(`run_export`)는 바뀌지 않는다 — 넘겨받은 요약의 `categories` 로 `to_markdown` 이 줄을 쓴다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/core/test_markdown_export.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/core/test_markdown_export.py b/tests/core/test_markdown_export.py
--- a/tests/core/test_markdown_export.py
+++ b/tests/core/test_markdown_export.py
@@ -6,6 +6,7 @@ from notebooklm_st.core import markdown_export, models
 def make_summary(
     title: str | None = "어떻게 AI는 생각하는가",
     video_id: str = "dQw4w9WgXcQ",
+    categories: tuple[str, ...] = (),
 ) -> models.RunSummary:
     """테스트용 실행 요약을 만든다."""
     return models.RunSummary(
@@ -15,6 +16,7 @@ def make_summary(
         title=title,
         created_at="2026-08-31T14:02:11",
         answer_count=1,
+        categories=categories,
     )
 
 
@@ -259,3 +261,51 @@ def test_to_markdown_keeps_a_raw_url_without_a_video_id() -> None:
     text = export(summary=make_summary(video_id=""))
 
     assert "- 영상 URL: https://youtu.be/dQw4w9WgXcQ" in text
+
+
+def test_category_line_joins_the_names_with_a_comma() -> None:
+    """이름들을 받은 순서대로 쉼표와 공백으로 잇는다."""
+    line = markdown_export.category_line(("경제", "인공지능"))
+
+    assert line == "- 카테고리: 경제, 인공지능"
+
+
+def test_category_line_is_none_without_names() -> None:
+    """이름이 없으면 줄을 만들지 않는다."""
+    assert markdown_export.category_line(()) is None
+
+
+def test_to_markdown_writes_the_categories_before_the_url() -> None:
+    """카테고리 줄은 업로드 일자 줄 다음, 영상 URL 줄 앞이다."""
+    metadata = models.VideoMetadata(
+        channel="안될공학", upload_date="2026-09-15"
+    )
+    summary = make_summary(categories=("경제", "인공지능"))
+
+    lines = export(summary=summary, metadata=metadata).splitlines()
+
+    assert lines[:5] == [
+        "- 제목: 어떻게 AI는 생각하는가",
+        "- 채널: 안될공학",
+        "- 업로드 일자: 2026-09-15",
+        "- 카테고리: 경제, 인공지능",
+        "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ",
+    ]
+
+
+def test_to_markdown_writes_categories_without_metadata() -> None:
+    """메타데이터가 없어도 카테고리 줄은 나온다."""
+    summary = make_summary(categories=("경제",))
+
+    lines = export(summary=summary).splitlines()
+
+    assert lines[:3] == [
+        "- 제목: 어떻게 AI는 생각하는가",
+        "- 카테고리: 경제",
+        "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ",
+    ]
+
+
+def test_to_markdown_omits_the_category_line_without_categories() -> None:
+    """카테고리가 없으면 줄째 뺀다."""
+    assert "- 카테고리:" not in export()
```

`tests/services/test_runner_start.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/services/test_runner_start.py b/tests/services/test_runner_start.py
--- a/tests/services/test_runner_start.py
+++ b/tests/services/test_runner_start.py
@@ -733,3 +733,33 @@ def test_finished_run_keeps_the_chosen_categories(db_path) -> None:
     finally:
         connection.close()
     assert summary.categories == ("경제",)
+
+
+def test_auto_save_writes_the_category_line(db_path, monkeypatch) -> None:
+    """자동 저장한 문서 머리에 고른 카테고리가 이름 순으로 적힌다."""
+    set_outline_env(monkeypatch)
+    calls = record_create(monkeypatch)
+    connection = store.connect(db_path)
+    try:
+        ids = [
+            categories.add_category(connection, name).id
+            for name in ("인공지능", "경제")
+        ]
+    finally:
+        connection.close()
+    registry = run_registry.RunRegistry()
+
+    started = runner.enqueue(
+        registry,
+        URL,
+        make_questions("핵심 주장은?"),
+        db_path,
+        True,
+        never_blocked,
+        answering(),
+        category_ids=ids,
+    )
+    wait_for(registry, started.run_id)
+
+    [(_, markdown)] = calls
+    assert "- 카테고리: 경제, 인공지능" in markdown.splitlines()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest tests/core/test_markdown_export.py tests/services/test_runner_start.py -q
```

기대: `5 failed` — `test_category_line_joins_the_names_with_a_comma`·`test_category_line_is_none_without_names`·`test_to_markdown_writes_the_categories_before_the_url`·`test_to_markdown_writes_categories_without_metadata`·`test_auto_save_writes_the_category_line`. `test_to_markdown_omits_the_category_line_without_categories` 는 지금도 참이라 통과한다 — 구현 뒤 줄이 새지 않게 지키는 테스트다.

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/core/markdown_export.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/core/markdown_export.py b/src/notebooklm_st/core/markdown_export.py
--- a/src/notebooklm_st/core/markdown_export.py
+++ b/src/notebooklm_st/core/markdown_export.py
@@ -45,6 +45,12 @@ CATEGORY_SEPARATOR = ","
 줄을 다시 나눈다.
 """
 
+CATEGORY_LABEL = "카테고리"
+"""메타데이터 리스트에서 카테고리 줄의 라벨.
+
+``outline_import.find_categories`` 가 같은 줄을 거꾸로 읽는다.
+"""
+
 
 def to_markdown(
     summary: models.RunSummary,
@@ -109,10 +115,32 @@ def _metadata_block(
         lines.append(f"- {CHANNEL_LABEL}: {one_line(metadata.channel)}")
     if metadata is not None and metadata.upload_date:
         lines.append(f"- {UPLOAD_DATE_LABEL}: {metadata.upload_date}")
+    categories = category_line(summary.categories)
+    if categories is not None:
+        lines.append(categories)
     lines.append(f"- {SOURCE_URL_LABEL}: {source_url(summary)}")
     return "\n".join(lines)
 
 
+def category_line(names: Sequence[str]) -> str | None:
+    """카테고리 이름들을 메타데이터 리스트의 한 줄로 만든다.
+
+    정리본도 같은 줄을 쓴다(→ ``digest_markdown``). 이름은 규칙을
+    통과한 값이라 다시 다듬지 않는다(→ ``category_names``).
+
+    Args:
+        names: 적을 이름. 부르는 쪽이 이름 순으로 넘긴다.
+
+    Returns:
+        ``- 카테고리: 경제, 인공지능`` 꼴의 줄. 이름이 없으면
+        ``None`` — 값이 없는 줄은 줄째 뺀다.
+    """
+    if not names:
+        return None
+    joined = f"{CATEGORY_SEPARATOR} ".join(names)
+    return f"- {CATEGORY_LABEL}: {joined}"
+
+
 def source_url(summary: models.RunSummary) -> str:
     """메타데이터에 적을 영상 URL 을 고른다.
```

이력 화면 저장 버튼의 도움말이 카테고리가 남는다고 말하게 고친다(설계서 §8.7).

```diff
diff --git a/src/notebooklm_st/pages/history.py b/src/notebooklm_st/pages/history.py
--- a/src/notebooklm_st/pages/history.py
+++ b/src/notebooklm_st/pages/history.py
@@ -162,7 +162,7 @@ def _render_export(
         key=f"history_export_{selected.id}",
         disabled=not title.strip(),
         help="지금 보이는 그대로 올립니다. 올린 뒤에는 로컬에 링크와"
-        " 채널·업로드일만 남습니다.",
+        " 채널·업로드일·카테고리만 남습니다.",
     ):
         _export(connection, config, selected, title.strip(), items, metadata)
```

- [ ] **Step 4: 지키는 테스트를 더한다 (Review Focus 5)**

이력 화면의 저장은 목록(`list_runs`)이 준 요약을 그대로 넘긴다. 그 길에서도 줄이 들어가는지 지킨다. 구현이 이미 그렇게 동작하므로 넣자마자 통과한다.

```diff
diff --git a/tests/services/test_run_export.py b/tests/services/test_run_export.py
--- a/tests/services/test_run_export.py
+++ b/tests/services/test_run_export.py
@@ -9,6 +9,7 @@ import pytest
 
 from notebooklm_st.core import models
 from notebooklm_st.services import (
+    categories,
     outline,
     run_export,
     run_history,
@@ -279,3 +280,29 @@ def test_save_releases_the_run_after_a_failure(connection, monkeypatch) -> None:
 
     assert document.url == DOC_URL
     assert len(calls) == 1
+
+
+def test_save_writes_the_category_line(connection, monkeypatch) -> None:
+    """이력 화면의 저장도 그 실행의 카테고리를 문서 머리에 적는다.
+
+    이력 화면은 목록(``list_runs``)이 준 요약을 그대로 넘긴다.
+    """
+    calls = record_create(monkeypatch)
+    category = categories.add_category(connection, "경제")
+    run_id = run_history.save_run(
+        connection,
+        models.RunResult(
+            url="https://youtu.be/dQw4w9WgXcQ",
+            video_id="dQw4w9WgXcQ",
+            title="어떤 영상",
+            items=(),
+        ),
+        category_ids=[category.id],
+    )
+    [summary] = run_history.list_runs(connection)
+    assert summary.id == run_id
+
+    run_export.save(connection, CONFIG, summary, "제목", [], None)
+
+    [(_, markdown)] = calls
+    assert "- 카테고리: 경제" in markdown.splitlines()
```

- [ ] **Step 5: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `938 passed, 1 skipped`.

- [ ] **Step 6: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
✨ feat(categories): 요약본 문서 머리에 카테고리 줄 쓰기

업로드 일자 줄 다음, 영상 URL 줄 앞에 `- 카테고리: …` 를 쓴다.
카테고리가 없으면 줄째 뺀다. 저장 경로는 요약이 들고 있는
카테고리를 쓰므로 바뀌지 않는다. 이력 화면 저장 버튼의 도움말도
카테고리가 남는다고 고친다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/core/markdown_export.py \
  src/notebooklm_st/pages/history.py \
  tests/core/test_markdown_export.py \
  tests/services/test_run_export.py \
  tests/services/test_runner_start.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 8: 질의 화면에서 카테고리를 하나 이상 고르기

**Files:**
- Create: `src/notebooklm_st/components/category_picker.py`
- Modify: `src/notebooklm_st/pages/ask.py`
- Test: `tests/pages/test_ask.py`

**Interfaces:**
- Consumes: `categories.list_categories` (Task 4), `runner.enqueue(category_ids=…)` (Task 5).
- Produces: `category_picker.NO_CATEGORIES`, `category_picker.QUERY_HELP`, `category_picker.render(label, category_list, key, help_text, on_change=None) -> list[int]`. Task 9·10 이 같은 컴포넌트를 쓴다.

설계서 §8.2. 질문 선택은 지금처럼 먼저 그리고, 카테고리가 없으면 그 뒤에서 안내하고 돌아간다. 기존 테스트 대부분이 실행 버튼까지 가므로 카테고리를 등록하고 고르게 고친다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_ask.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/pages/test_ask.py b/tests/pages/test_ask.py
--- a/tests/pages/test_ask.py
+++ b/tests/pages/test_ask.py
@@ -1,10 +1,26 @@
 """질의 화면 테스트."""
 
+import pytest
 from streamlit.testing import v1
 
 from notebooklm_st import session
 from notebooklm_st.core import models
-from notebooklm_st.services import outline, questions, runner, settings
+from notebooklm_st.services import (
+    categories,
+    outline,
+    questions,
+    runner,
+    settings,
+)
+
+
+@pytest.fixture
+def category(app_db) -> models.Category:
+    """질의에 고를 카테고리 하나를 등록한다.
+
+    카테고리가 하나도 없으면 화면이 실행 버튼까지 그리지 않는다.
+    """
+    return categories.add_category(app_db, "경제")
 
 
 def test_ask_asks_user_to_register_questions_first(app_db) -> None:
@@ -53,7 +69,7 @@ def test_ask_rejects_a_non_youtube_url(app_db) -> None:
     assert len(app.error) == 1
 
 
-def test_ask_run_button_is_disabled_without_input(app_db) -> None:
+def test_ask_run_button_is_disabled_without_input(app_db, category) -> None:
     """URL 과 질문 선택이 없으면 실행 버튼이 비활성화된다."""
     questions.add_question(app_db, "핵심 주장", "핵심 주장 3가지 정리")
 
@@ -66,7 +82,9 @@ def test_ask_run_button_is_disabled_without_input(app_db) -> None:
     assert app.button[0].disabled is True
 
 
-def test_run_button_starts_a_background_run(app_db, monkeypatch) -> None:
+def test_run_button_starts_a_background_run(
+    app_db, monkeypatch, category
+) -> None:
     """실행 버튼을 누르면 대기열에 넣고, URL 칸만 비운다."""
     questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
     started: list[str] = []
@@ -103,7 +121,9 @@ def put_other_video(state: str = "queued") -> None:
         registry.claim_next()
 
 
-def test_a_running_query_does_not_lock_the_button(app_db, monkeypatch) -> None:
+def test_a_running_query_does_not_lock_the_button(
+    app_db, monkeypatch, category
+) -> None:
     """실행 중인 질의가 있어도 넣을 수 있고, 몇 번째인지 알린다."""
     questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
     record_enqueue(monkeypatch)
@@ -114,6 +134,7 @@ def test_a_running_query_does_not_lock_the_button(app_db, monkeypatch) -> None:
         "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
     ).run()
     app.multiselect[0].set_value(questions.list_questions(app_db)).run()
+    choose_categories(app, app_db)
 
     assert app.button[0].disabled is False
     assert [item.value for item in app.info] == [
@@ -127,7 +148,9 @@ def test_a_running_query_does_not_lock_the_button(app_db, monkeypatch) -> None:
     ]
 
 
-def test_a_digest_does_not_lock_the_button(app_db, monkeypatch) -> None:
+def test_a_digest_does_not_lock_the_button(
+    app_db, monkeypatch, category
+) -> None:
     """정리본을 작성 중이어도 넣고, 끝난 뒤 시작한다고 알린다."""
     questions.add_question(app_db, "핵심 주장", "핵심 주장 3가지 정리")
     record_enqueue(monkeypatch)
@@ -138,6 +161,7 @@ def test_a_digest_does_not_lock_the_button(app_db, monkeypatch) -> None:
         "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
     ).run()
     app.multiselect[0].set_value(questions.list_questions(app_db)).run()
+    choose_categories(app, app_db)
 
     assert app.button[0].disabled is False
     assert [item.value for item in app.info] == [
@@ -150,7 +174,9 @@ def test_a_digest_does_not_lock_the_button(app_db, monkeypatch) -> None:
     ]
 
 
-def test_a_paused_queue_still_takes_a_query(app_db, monkeypatch) -> None:
+def test_a_paused_queue_still_takes_a_query(
+    app_db, monkeypatch, category
+) -> None:
     """멈춘 대기열에도 넣을 수 있고, 재개할 때까지 기다린다고 알린다."""
     questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
     record_enqueue(monkeypatch)
@@ -170,7 +196,9 @@ def test_a_paused_queue_still_takes_a_query(app_db, monkeypatch) -> None:
     ]
 
 
-def test_the_same_video_cannot_be_queued_twice(app_db, monkeypatch) -> None:
+def test_the_same_video_cannot_be_queued_twice(
+    app_db, monkeypatch, category
+) -> None:
     """대기 중이거나 실행 중인 영상을 다시 넣지 못한다."""
     questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
     received = record_enqueue(monkeypatch)
@@ -194,7 +222,7 @@ def test_the_same_video_cannot_be_queued_twice(app_db, monkeypatch) -> None:
 
 
 def test_a_press_after_the_video_was_queued_adds_nothing(
-    app_db, monkeypatch
+    app_db, monkeypatch, category
 ) -> None:
     """그린 뒤 같은 영상이 대기열에 들어가면 눌러도 넣지 않는다."""
     questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
@@ -205,6 +233,7 @@ def test_a_press_after_the_video_was_queued_adds_nothing(
         "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
     ).run()
     app.multiselect[0].set_value(questions.list_questions(app_db)).run()
+    choose_categories(app, app_db)
     assert app.button[0].disabled is False
 
     question = questions.list_questions(app_db)[0]
@@ -245,16 +274,25 @@ def record_enqueue(monkeypatch) -> list[bool]:
     return received
 
 
+def choose_categories(app: v1.AppTest, connection) -> None:
+    """등록된 카테고리를 모두 고른다."""
+    ids = [item.id for item in categories.list_categories(connection)]
+    app.multiselect(key="ask_categories").set_value(ids).run()
+
+
 def fill_and_run(app: v1.AppTest, connection) -> None:
-    """URL 과 질문을 채우고 실행을 누른다."""
+    """URL 과 질문과 카테고리를 채우고 실행을 누른다."""
     app.text_input[0].set_value(
         "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
     ).run()
     app.multiselect[0].set_value(questions.list_questions(connection)).run()
+    choose_categories(app, connection)
     app.button[0].click().run()
 
 
-def test_auto_save_starts_from_the_stored_setting(app_db, monkeypatch) -> None:
+def test_auto_save_starts_from_the_stored_setting(
+    app_db, monkeypatch, category
+) -> None:
     """자동 저장 체크는 DB 에 기억한 값으로 그려진다."""
     set_outline_env(monkeypatch)
     questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
@@ -269,7 +307,7 @@ def test_auto_save_starts_from_the_stored_setting(app_db, monkeypatch) -> None:
     assert box.disabled is False
 
 
-def test_auto_save_change_is_remembered(app_db, monkeypatch) -> None:
+def test_auto_save_change_is_remembered(app_db, monkeypatch, category) -> None:
     """체크를 바꾸면 DB 에 남고, 새로 연 화면도 그 값으로 시작한다."""
     set_outline_env(monkeypatch)
     questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
@@ -283,7 +321,9 @@ def test_auto_save_change_is_remembered(app_db, monkeypatch) -> None:
     assert fresh.checkbox(key="ask_auto_save").value is True
 
 
-def test_auto_save_survives_quick_toggles(app_db, monkeypatch) -> None:
+def test_auto_save_survives_quick_toggles(
+    app_db, monkeypatch, category
+) -> None:
     """켜고 곧바로 끄고 다시 켜도 조작 하나 버려지지 않는다.
 
     key 없는 체크에 DB 값을 초기값으로 주면 DB 에 적는 순간 위젯
@@ -306,7 +346,7 @@ def test_auto_save_survives_quick_toggles(app_db, monkeypatch) -> None:
     assert settings.auto_save(app_db) is True
 
 
-def test_auto_save_is_locked_without_outline(app_db) -> None:
+def test_auto_save_is_locked_without_outline(app_db, category) -> None:
     """Outline 설정이 없으면 체크를 꺼서 잠그고 DB 값은 그대로 둔다."""
     questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
     settings.set_auto_save(app_db, True)
@@ -326,7 +366,7 @@ def test_auto_save_is_locked_without_outline(app_db) -> None:
 
 
 def test_run_hands_the_shown_auto_save_to_the_runner(
-    app_db, monkeypatch
+    app_db, monkeypatch, category
 ) -> None:
     """방금 켠 체크 값이 그대로 러너로 넘어간다."""
     set_outline_env(monkeypatch)
@@ -341,7 +381,9 @@ def test_run_hands_the_shown_auto_save_to_the_runner(
     assert received == [True]
 
 
-def test_run_without_outline_hands_no_auto_save(app_db, monkeypatch) -> None:
+def test_run_without_outline_hands_no_auto_save(
+    app_db, monkeypatch, category
+) -> None:
     """Outline 설정이 없으면 DB 에 켜 두었어도 자동 저장 없이 넣는다."""
     questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
     settings.set_auto_save(app_db, True)
@@ -352,3 +394,73 @@ def test_run_without_outline_hands_no_auto_save(app_db, monkeypatch) -> None:
 
     assert not app.exception
     assert received == [False]
+
+
+def record_categories(monkeypatch) -> list[tuple[int, ...]]:
+    """``runner.enqueue`` 를 막고 넘어온 카테고리 ID 를 기록한다."""
+    received: list[tuple[int, ...]] = []
+
+    def fake_enqueue(registry, url, questions, db_path, **kwargs):
+        """스레드를 띄우지 않고 카테고리 ID 만 기록하는 가짜."""
+        received.append(tuple(kwargs["category_ids"]))
+        return registry.enqueue(url, "dQw4w9WgXcQ", tuple(questions))
+
+    monkeypatch.setattr(runner, "enqueue", fake_enqueue)
+    return received
+
+
+def test_without_categories_the_page_says_so(app_db) -> None:
+    """카테고리가 없으면 안내하고 실행 버튼을 그리지 않는다."""
+    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
+
+    app = v1.AppTest.from_function(ask_page).run()
+
+    assert not app.exception
+    assert [item.value for item in app.info] == [
+        "카테고리 관리 화면에서 카테고리를 먼저 등록하세요. 카테고리를"
+        " 고르지 않으면 질의할 수 없습니다."
+    ]
+    assert len(app.multiselect) == 1
+    assert len(app.button) == 0
+
+
+def test_category_options_show_names_in_order(app_db, category) -> None:
+    """카테고리 선택지는 이름 순으로 이름을 보인다."""
+    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
+    categories.add_category(app_db, "AI")
+
+    app = v1.AppTest.from_function(ask_page).run()
+
+    picker = app.multiselect(key="ask_categories")
+    assert picker.label == "카테고리"
+    assert picker.options == ["AI", "경제"]
+
+
+def test_the_run_button_waits_for_a_category(app_db, category) -> None:
+    """URL 과 질문이 있어도 카테고리를 고르기 전에는 잠겨 있다."""
+    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
+
+    app = v1.AppTest.from_function(ask_page).run()
+    app.text_input[0].set_value(
+        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
+    ).run()
+    app.multiselect[0].set_value(questions.list_questions(app_db)).run()
+
+    assert app.button[0].disabled is True
+    choose_categories(app, app_db)
+    assert app.button[0].disabled is False
+
+
+def test_run_hands_the_chosen_categories_to_the_runner(
+    app_db, monkeypatch, category
+) -> None:
+    """고른 카테고리 ID 가 러너로 가고, 넣은 뒤에도 선택이 남는다."""
+    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
+    received = record_categories(monkeypatch)
+
+    app = v1.AppTest.from_function(ask_page).run()
+    fill_and_run(app, app_db)
+
+    assert not app.exception
+    assert received == [(category.id,)]
+    assert app.multiselect(key="ask_categories").value == [category.id]
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest tests/pages/test_ask.py -q
```

기대: `11 failed, 9 passed` — 새 테스트 넷과 `ask_categories` 위젯을 찾는 기존 테스트 일곱(`KeyError` 또는 단언 실패).

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/components/category_picker.py` 를 새로 만든다.

```python
"""카테고리 선택 — 질의 화면과 채널 화면이 함께 쓴다.

값은 카테고리 ID 이고, 이름은 ``format_func`` 로 보인다. 객체를 값으로
쓰면 이름이 바뀐 카테고리가 선택지와 같지 않게 된다.
"""

from collections.abc import Callable, Sequence

import streamlit as st

from notebooklm_st.core import models

NO_CATEGORIES = (
    "카테고리 관리 화면에서 카테고리를 먼저 등록하세요."
    " 카테고리를 고르지 않으면 질의할 수 없습니다."
)
"""카테고리가 하나도 없을 때 질의를 넣는 화면이 보이는 안내."""

QUERY_HELP = (
    "Outline 문서 머리에 적히고 정리본 재료를 거르는 데 씁니다."
    " 하나 이상 고르세요."
)
"""질의를 넣는 화면의 카테고리 선택 도움말."""


def render(
    label: str,
    category_list: Sequence[models.Category],
    key: str,
    help_text: str,
    on_change: Callable[[], None] | None = None,
) -> list[int]:
    """카테고리 선택을 그리고 고른 ID 를 돌려준다.

    Args:
        label: 위젯 라벨.
        category_list: 선택지. 비어 있지 않다.
        key: 위젯 key. 화면마다 다르다.
        help_text: 위젯 도움말.
        on_change: 값이 바뀌면 부를 콜백. DB 에 기억하는 화면만 준다.

    Returns:
        고른 카테고리 ID.
    """
    names = {category.id: category.name for category in category_list}
    chosen: list[int] = st.multiselect(
        label,
        options=list(names),
        format_func=lambda category_id: names[category_id],
        key=key,
        help=help_text,
        on_change=on_change,
    )
    return chosen
```

`src/notebooklm_st/pages/ask.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/pages/ask.py b/src/notebooklm_st/pages/ask.py
--- a/src/notebooklm_st/pages/ask.py
+++ b/src/notebooklm_st/pages/ask.py
@@ -3,19 +3,30 @@
 import streamlit as st
 
 from notebooklm_st import session
-from notebooklm_st.components import auto_save_toggle, queue_notice
+from notebooklm_st.components import (
+    auto_save_toggle,
+    category_picker,
+    queue_notice,
+)
 from notebooklm_st.core import youtube
-from notebooklm_st.services import questions, run_registry, runner, store
+from notebooklm_st.services import (
+    categories,
+    questions,
+    run_registry,
+    runner,
+    store,
+)
 
 _URL_KEY = "ask_url"
 _SELECTED_KEY = "ask_selected"
+_CATEGORIES_KEY = "ask_categories"
 _AUTO_SAVE_KEY = "ask_auto_save"
 _AUTO_SAVE_LOCKED_KEY = "ask_auto_save_locked"
 _ENQUEUED_KEY = "ask_enqueued"
 
 
 def render() -> None:
-    """URL 입력, 질문 선택, 자동 저장 여부, 대기열에 넣기를 그린다.
+    """URL 입력, 질문·카테고리 선택, 자동 저장 여부, 넣기를 그린다.
 
     실행은 백그라운드 워커가 넣은 순서대로 맡는다. 이 화면은 넣기만
     하고 즉시 반환하므로, 앞 실행을 기다리지 않고 다음 영상을 넣을 수
@@ -45,6 +56,16 @@ def render() -> None:
         format_func=lambda question: question.title,
         key=_SELECTED_KEY,
     )
+    category_list = categories.list_categories(connection)
+    if not category_list:
+        st.info(category_picker.NO_CATEGORIES)
+        return
+    chosen = category_picker.render(
+        "카테고리",
+        category_list,
+        _CATEGORIES_KEY,
+        category_picker.QUERY_HELP,
+    )
     auto_save = auto_save_toggle.render(
         connection, _AUTO_SAVE_KEY, _AUTO_SAVE_LOCKED_KEY
     )
@@ -55,7 +76,7 @@ def render() -> None:
     st.button(
         "실행",
         key="ask_run",
-        disabled=duplicate or not (url_ok and selected),
+        disabled=duplicate or not (url_ok and selected and chosen),
         on_click=_enqueue,
         args=(registry, auto_save),
     )
@@ -87,10 +108,10 @@ def _enqueue(registry: run_registry.RunRegistry, auto_save: bool) -> None:
     """입력한 영상을 대기열에 넣고 URL 칸을 비운다.
 
     실행 버튼의 ``on_click`` 콜백이다. 콜백은 재실행 전에 돌므로 URL
-    위젯의 키를 바꿔도 예외가 없다. URL·질문은 버튼을 그릴 때가 아니라
-    누른 순간의 세션 값을 읽는다. 질문 선택은 남겨 다음 영상을 바로
-    붙여 넣게 한다. 결과 문구는 세션에 적어 다음 그림에서 한 번
-    보인다.
+    위젯의 키를 바꿔도 예외가 없다. URL·질문·카테고리는 버튼을 그릴
+    때가 아니라 누른 순간의 세션 값을 읽는다. 질문과 카테고리 선택은
+    남겨 다음 영상을 바로 붙여 넣게 한다. 결과 문구는 세션에 적어
+    다음 그림에서 한 번 보인다.
 
     Args:
         registry: 실행 레지스트리.
@@ -98,8 +119,14 @@ def _enqueue(registry: run_registry.RunRegistry, auto_save: bool) -> None:
     """
     url = st.session_state.get(_URL_KEY, "")
     selected = st.session_state.get(_SELECTED_KEY, [])
+    chosen = st.session_state.get(_CATEGORIES_KEY, [])
     video_id = youtube.extract_video_id(url)
-    if video_id is None or not selected or registry.is_pending(video_id):
+    if (
+        video_id is None
+        or not selected
+        or not chosen
+        or registry.is_pending(video_id)
+    ):
         return
     ahead = queue_notice.count_ahead(registry)
     paused = registry.paused_reason() is not None
@@ -112,6 +139,7 @@ def _enqueue(registry: run_registry.RunRegistry, auto_save: bool) -> None:
         store.default_db_path(),
         auto_save=auto_save,
         is_blocked=digests.is_running,
+        category_ids=chosen,
     )
     st.session_state[_URL_KEY] = ""
     st.session_state[_ENQUEUED_KEY] = queue_notice.enqueued_text(
```

- [ ] **Step 4: 지키는 테스트를 더한다 (Review Focus 1·2)**

선택지에서 사라진 값은 Streamlit 이 조용히 빼고, 값이 ID 라 이름이 바뀌어도 선택이 남는다. 그 동작을 지킨다. 넣자마자 통과한다.

```diff
diff --git a/tests/pages/test_ask.py b/tests/pages/test_ask.py
--- a/tests/pages/test_ask.py
+++ b/tests/pages/test_ask.py
@@ -464,3 +464,37 @@ def test_run_hands_the_chosen_categories_to_the_runner(
     assert not app.exception
     assert received == [(category.id,)]
     assert app.multiselect(key="ask_categories").value == [category.id]
+
+
+def test_a_deleted_category_drops_out_of_the_choice(app_db, category) -> None:
+    """고른 카테고리가 지워져도 화면이 깨지지 않고 선택에서 빠진다."""
+    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
+    categories.add_category(app_db, "정치")
+    app = v1.AppTest.from_function(ask_page).run()
+    app.text_input[0].set_value(
+        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
+    ).run()
+    app.multiselect[0].set_value(questions.list_questions(app_db)).run()
+    app.multiselect(key="ask_categories").set_value([category.id]).run()
+
+    categories.delete_category(app_db, category.id)
+    app.run()
+
+    assert not app.exception
+    assert app.multiselect(key="ask_categories").value == []
+    assert app.button[0].disabled is True
+
+
+def test_a_renamed_category_stays_chosen(app_db, category) -> None:
+    """고른 카테고리 이름이 바뀌어도 선택이 남고 새 이름으로 보인다."""
+    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
+    app = v1.AppTest.from_function(ask_page).run()
+    app.multiselect(key="ask_categories").set_value([category.id]).run()
+
+    categories.rename_category(app_db, category.id, "거시경제")
+    app.run()
+
+    picker = app.multiselect(key="ask_categories")
+    assert not app.exception
+    assert picker.value == [category.id]
+    assert picker.options == ["거시경제"]
```

- [ ] **Step 5: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `944 passed, 1 skipped`.

- [ ] **Step 6: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
✨ feat(ask): 질의할 때 카테고리를 하나 이상 고르게 하기

카테고리 선택을 components/category_picker 로 두고 질의 화면에
붙인다. 카테고리가 하나도 없으면 안내하고 실행 버튼을 그리지
않는다. 값은 ID 라 이름이 바뀌어도 선택이 남는다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/components/category_picker.py \
  src/notebooklm_st/pages/ask.py \
  tests/pages/test_ask.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 9: 채널마다 기본 카테고리 두기

**Files:**
- Modify: `src/notebooklm_st/services/channels.py`, `src/notebooklm_st/pages/channels.py`
- Test: `tests/services/test_channels.py`, `tests/pages/test_channels.py`

**Interfaces:**
- Consumes: `category_picker.render` (Task 8), `categories.list_categories` (Task 4).
- Produces: `channels.add_channel(connection, channel_id, title, url, baseline, category_ids: Sequence[int] = ())`, `channels.default_category_ids(connection, channel_pk) -> tuple[int, ...]`(ID 순), `channels.set_default_categories(connection, channel_pk, category_ids) -> None`(없는 채널이면 `ValueError`). Task 10 이 `default_category_ids` 로 확인 탭을 미리 채운다.

설계서 §7.5·§8.3. 목록 탭의 선택은 key 를 주고, 그 키가 세션에 없을 때만 DB 값으로 채우고, `on_change` 콜백이 적는다(설계서 §2.12). 연달아 두 번 바꾸는 테스트가 그 방식을 지킨다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/services/test_channels.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/services/test_channels.py b/tests/services/test_channels.py
--- a/tests/services/test_channels.py
+++ b/tests/services/test_channels.py
@@ -2,7 +2,7 @@
 
 import pytest
 
-from notebooklm_st.services import channels, store
+from notebooklm_st.services import categories, channels, store
 
 
 @pytest.fixture
@@ -13,7 +13,9 @@ def connection(tmp_path):
     conn.close()
 
 
-def add(connection, channel_id="UC" + "a" * 22, title="어떤 채널"):
+def add(
+    connection, channel_id="UC" + "a" * 22, title="어떤 채널", category_ids=()
+):
     """테스트용 채널 하나를 등록한다."""
     return channels.add_channel(
         connection,
@@ -21,6 +23,7 @@ def add(connection, channel_id="UC" + "a" * 22, title="어떤 채널"):
         title,
         f"https://www.youtube.com/channel/{channel_id}",
         "2026-09-23",
+        category_ids=category_ids,
     )
 
 
@@ -149,3 +152,61 @@ def test_update_title_rejects_an_unknown_channel(connection) -> None:
     """없는 채널의 이름은 고칠 수 없다."""
     with pytest.raises(ValueError):
         channels.update_title(connection, 999, "새 이름")
+
+
+def category_ids(connection, *names: str) -> list[int]:
+    """카테고리를 등록하고 ID 를 넘긴 순서대로 돌려준다."""
+    return [categories.add_category(connection, name).id for name in names]
+
+
+def test_a_channel_has_no_default_categories_at_first(connection) -> None:
+    """기본 카테고리 없이 등록하면 비어 있다."""
+    channel = add(connection)
+
+    assert channels.default_category_ids(connection, channel.id) == ()
+
+
+def test_add_channel_saves_the_default_categories(connection) -> None:
+    """등록할 때 준 기본 카테고리를 ID 순으로 돌려준다."""
+    ids = category_ids(connection, "경제", "정치")
+
+    channel = add(connection, category_ids=list(reversed(ids)))
+
+    assert channels.default_category_ids(connection, channel.id) == tuple(ids)
+
+
+def test_add_channel_skips_an_unknown_category(connection) -> None:
+    """없는 카테고리 ID 는 조용히 뺀다."""
+    [known] = category_ids(connection, "경제")
+
+    channel = add(connection, category_ids=[known, 999])
+
+    assert channels.default_category_ids(connection, channel.id) == (known,)
+
+
+def test_set_default_categories_replaces_them(connection) -> None:
+    """기본 카테고리를 통째로 바꾼다."""
+    first, second = category_ids(connection, "경제", "정치")
+    channel = add(connection, category_ids=[first])
+
+    channels.set_default_categories(connection, channel.id, [second])
+
+    assert channels.default_category_ids(connection, channel.id) == (second,)
+
+
+def test_set_default_categories_can_clear_them(connection) -> None:
+    """빈 목록을 주면 기본 카테고리가 없어진다."""
+    [first] = category_ids(connection, "경제")
+    channel = add(connection, category_ids=[first])
+
+    channels.set_default_categories(connection, channel.id, [])
+
+    assert channels.default_category_ids(connection, channel.id) == ()
+
+
+def test_set_default_categories_rejects_an_unknown_channel(
+    connection,
+) -> None:
+    """없는 채널이면 거부한다."""
+    with pytest.raises(ValueError, match="찾을 수 없습니다"):
+        channels.set_default_categories(connection, 99, [])
```

`tests/pages/test_channels.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/pages/test_channels.py b/tests/pages/test_channels.py
--- a/tests/pages/test_channels.py
+++ b/tests/pages/test_channels.py
@@ -18,6 +18,7 @@ from streamlit.testing import v1
 from notebooklm_st import session
 from notebooklm_st.core import models, youtube
 from notebooklm_st.services import (
+    categories,
     channel_feed,
     channel_lookup,
     channels,
@@ -929,3 +930,67 @@ def test_video_table_returns_the_picked_entries(app_db) -> None:
     assert "고른 영상: aaaaaaaaaaa,bbbbbbbbbbb" in [
         item.value for item in app.markdown
     ]
+
+
+def test_registering_saves_the_default_categories(app_db, fake_sources) -> None:
+    """등록 탭에서 고른 기본 카테고리가 채널과 함께 저장된다."""
+    economy = categories.add_category(app_db, "경제")
+    categories.add_category(app_db, "정치")
+
+    app = v1.AppTest.from_function(script)
+    app.run()
+    text_input_by(app, "채널 URL").set_value(HANDLE_URL).run()
+    app.multiselect(key="channels_new_categories").set_value([economy.id]).run()
+    button_by(app, "등록").click().run()
+
+    assert not app.exception
+    [channel] = channels.list_channels(app_db)
+    assert channels.default_category_ids(app_db, channel.id) == (economy.id,)
+
+
+def test_without_categories_there_is_no_default_picker(app_db) -> None:
+    """카테고리가 없으면 기본 카테고리 선택을 그리지 않는다."""
+    registered(app_db)
+
+    app = v1.AppTest.from_function(script).run()
+
+    assert not app.exception
+    assert all(item.label != "기본 카테고리" for item in app.multiselect)
+
+
+def test_the_default_categories_start_from_the_saved_ones(app_db) -> None:
+    """목록 탭의 기본 카테고리는 저장된 값으로 시작한다."""
+    economy = categories.add_category(app_db, "경제")
+    channel = registered(app_db)
+    channels.set_default_categories(app_db, channel.id, [economy.id])
+
+    app = v1.AppTest.from_function(script).run()
+
+    picker = app.multiselect(key=f"channels_default_categories_{channel.id}")
+    assert picker.label == "기본 카테고리"
+    assert picker.value == [economy.id]
+
+
+def test_default_categories_survive_quick_changes(app_db) -> None:
+    """목록 탭에서 연달아 바꿔도 조작 하나 버려지지 않고 저장된다.
+
+    key 없는 위젯에 DB 값을 초기값으로 주면 DB 에 적는 순간 위젯
+    ID 가 바뀌어, 바로 다음 조작이 옛 위젯으로 가서 버려진다.
+    """
+    economy = categories.add_category(app_db, "경제")
+    politics = categories.add_category(app_db, "정치")
+    channel = registered(app_db)
+    key = f"channels_default_categories_{channel.id}"
+
+    app = v1.AppTest.from_function(script).run()
+    app.multiselect(key=key).set_value([economy.id]).run()
+    app.multiselect(key=key).set_value([economy.id, politics.id]).run()
+
+    assert channels.default_category_ids(app_db, channel.id) == (
+        economy.id,
+        politics.id,
+    )
+    app.multiselect(key=key).set_value([]).run()
+
+    assert not app.exception
+    assert channels.default_category_ids(app_db, channel.id) == ()
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest tests/services/test_channels.py tests/pages/test_channels.py -q
```

기대: `17 failed` — 새 테스트 아홉과, 도우미 `add` 가 아직 없는 `category_ids` 인자를 넘겨 `TypeError` 가 나는 기존 저장소 테스트 여덟.

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/services/channels.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/services/channels.py b/src/notebooklm_st/services/channels.py
--- a/src/notebooklm_st/services/channels.py
+++ b/src/notebooklm_st/services/channels.py
@@ -6,6 +6,7 @@ SQLite 만 알고 네트워크도 Streamlit 도 모른다.
 
 import datetime
 import sqlite3
+from collections.abc import Sequence
 
 from notebooklm_st.core import models
 from notebooklm_st.services import store
@@ -40,6 +41,7 @@ def add_channel(
     title: str,
     url: str,
     baseline: str,
+    category_ids: Sequence[int] = (),
 ) -> models.Channel:
     """채널을 등록한다.
 
@@ -50,6 +52,7 @@ def add_channel(
         title: 화면에 보여 줄 채널명.
         url: 사람이 누를 채널 주소.
         baseline: ``YYYY-MM-DD`` 형식의 기준일.
+        category_ids: 기본 카테고리 ID. 없는 ID 는 조용히 빠진다.
 
     Returns:
         저장된 채널.
@@ -82,8 +85,58 @@ def add_channel(
             store.now(),
         ),
     ).fetchone()
+    channel = _to_channel(row)
+    _insert_defaults(connection, channel.id, category_ids)
+    connection.commit()
+    return channel
+
+
+def default_category_ids(
+    connection: sqlite3.Connection, channel_pk: int
+) -> tuple[int, ...]:
+    """채널의 기본 카테고리 ID 를 돌려준다.
+
+    Args:
+        connection: 열린 커넥션.
+        channel_pk: 채널의 행 ID.
+
+    Returns:
+        카테고리 ID. ID 순이다. 없으면 비어 있다.
+    """
+    rows = connection.execute(
+        "SELECT category_id FROM channel_categories WHERE channel_pk = ?"
+        " ORDER BY category_id",
+        (channel_pk,),
+    ).fetchall()
+    return tuple(int(row["category_id"]) for row in rows)
+
+
+def set_default_categories(
+    connection: sqlite3.Connection,
+    channel_pk: int,
+    category_ids: Sequence[int],
+) -> None:
+    """채널의 기본 카테고리를 통째로 바꾼다.
+
+    Args:
+        connection: 열린 커넥션.
+        channel_pk: 바꿀 채널의 행 ID.
+        category_ids: 새 기본 카테고리 ID. 비우면 기본값이 없어진다.
+            없는 ID 는 조용히 빠진다.
+
+    Raises:
+        ValueError: 그 채널이 없는 경우.
+    """
+    found = connection.execute(
+        "SELECT 1 FROM channels WHERE id = ?", (channel_pk,)
+    ).fetchone()
+    if found is None:
+        raise ValueError(f"채널 {channel_pk} 을 찾을 수 없습니다.")
+    connection.execute(
+        "DELETE FROM channel_categories WHERE channel_pk = ?", (channel_pk,)
+    )
+    _insert_defaults(connection, channel_pk, category_ids)
     connection.commit()
-    return _to_channel(row)
 
 
 def update_baseline(
@@ -150,6 +203,23 @@ def delete_channel(connection: sqlite3.Connection, channel_pk: int) -> None:
     connection.commit()
 
 
+def _insert_defaults(
+    connection: sqlite3.Connection,
+    channel_pk: int,
+    category_ids: Sequence[int],
+) -> None:
+    """기본 카테고리 연결을 넣는다. 커밋은 부르는 쪽이 한다.
+
+    ``categories`` 에서 골라 넣으므로 없는 ID 는 빠진다. 같은 ID 가
+    두 번 와도 한 번만 넣는다.
+    """
+    connection.executemany(
+        "INSERT OR IGNORE INTO channel_categories (channel_pk, category_id)"
+        " SELECT ?, id FROM categories WHERE id = ?",
+        [(channel_pk, category_id) for category_id in category_ids],
+    )
+
+
 def _exists(connection: sqlite3.Connection, channel_id: str) -> bool:
     """같은 채널 ID 가 이미 있는지 알려준다.
```

`src/notebooklm_st/pages/channels.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/pages/channels.py b/src/notebooklm_st/pages/channels.py
--- a/src/notebooklm_st/pages/channels.py
+++ b/src/notebooklm_st/pages/channels.py
@@ -10,17 +10,30 @@
 """
 
 import datetime
+import functools
 import sqlite3
 
 import streamlit as st
 
 from notebooklm_st import session
+from notebooklm_st.components import category_picker
 from notebooklm_st.core import models
 from notebooklm_st.pages import _channel_check
-from notebooklm_st.services import channel_feed, channel_lookup, channels
+from notebooklm_st.services import (
+    categories,
+    channel_feed,
+    channel_lookup,
+    channels,
+)
 
 _URL_KEY = "channels_url"
 _BASELINE_KEY = "channels_baseline"
+_NEW_CATEGORIES_KEY = "channels_new_categories"
+
+_DEFAULTS_HELP = (
+    "이 채널의 새 영상을 넣을 때 미리 골라 둘 카테고리입니다."
+    " 비워 둘 수 있습니다."
+)
 
 _EMPTY_NOTICE = "등록된 채널이 없습니다. 채널 등록 탭에서 먼저 등록하세요."
 
@@ -30,6 +43,7 @@ def render() -> None:
     st.title("채널")
     connection = session.get_connection()
     channel_list = channels.list_channels(connection)
+    category_list = categories.list_categories(connection)
     check_tab, add_tab, list_tab = st.tabs(
         ["새 영상 확인", "채널 등록", "등록된 채널"]
     )
@@ -39,16 +53,22 @@ def render() -> None:
         else:
             st.info(_EMPTY_NOTICE)
     with add_tab:
-        _render_register(connection)
+        _render_register(connection, category_list)
     with list_tab:
         if channel_list:
-            _render_list(connection, channel_list)
+            _render_list(connection, channel_list, category_list)
         else:
             st.info(_EMPTY_NOTICE)
 
 
-def _render_register(connection: sqlite3.Connection) -> None:
-    """채널 URL 과 처음 기준일을 받아 등록한다."""
+def _render_register(
+    connection: sqlite3.Connection,
+    category_list: list[models.Category],
+) -> None:
+    """채널 URL 과 처음 기준일, 기본 카테고리를 받아 등록한다.
+
+    카테고리가 하나도 없으면 기본 카테고리 선택을 그리지 않는다.
+    """
     url = st.text_input(
         "채널 URL",
         key=_URL_KEY,
@@ -61,11 +81,24 @@ def _render_register(connection: sqlite3.Connection) -> None:
         help="이 날짜 이후 업로드된 영상만 새 영상으로 봅니다."
         " 등록 뒤에는 새 영상 확인 탭에서 바꿉니다.",
     )
+    chosen: list[int] = []
+    if category_list:
+        chosen = category_picker.render(
+            "기본 카테고리",
+            category_list,
+            _NEW_CATEGORIES_KEY,
+            _DEFAULTS_HELP,
+        )
     if st.button("등록", key="channels_add", disabled=not url.strip()):
-        _add(connection, url, baseline)
+        _add(connection, url, baseline, chosen)
 
 
-def _add(connection: sqlite3.Connection, url: str, baseline: object) -> None:
+def _add(
+    connection: sqlite3.Connection,
+    url: str,
+    baseline: object,
+    category_ids: list[int],
+) -> None:
     """해석 · 피드 확인 · 저장을 차례로 한다.
 
     **피드를 등록 시점에 한 번 찔러 본다.** 피드가 없는 채널을
@@ -77,6 +110,7 @@ def _add(connection: sqlite3.Connection, url: str, baseline: object) -> None:
         url: 등록할 채널의 URL.
         baseline: ``st.date_input`` 이 돌려준 값. 범위 선택이면
             날짜가 아니므로 막는다.
+        category_ids: 고른 기본 카테고리 ID.
     """
     if not isinstance(baseline, datetime.date):
         st.error("기준일을 하나 고르세요.")
@@ -102,6 +136,7 @@ def _add(connection: sqlite3.Connection, url: str, baseline: object) -> None:
             found.title,
             found.url,
             baseline.isoformat(),
+            category_ids=category_ids,
         )
     except ValueError as error:
         st.error(str(error))
@@ -110,15 +145,19 @@ def _add(connection: sqlite3.Connection, url: str, baseline: object) -> None:
 
 
 def _render_list(
-    connection: sqlite3.Connection, channel_list: list[models.Channel]
+    connection: sqlite3.Connection,
+    channel_list: list[models.Channel],
+    category_list: list[models.Category],
 ) -> None:
-    """등록된 채널을 이름 수정·삭제와 함께 그린다."""
+    """등록된 채널을 이름·기본 카테고리 수정, 삭제와 함께 그린다."""
     for channel in channel_list:
-        _render_row(connection, channel)
+        _render_row(connection, channel, category_list)
 
 
 def _render_row(
-    connection: sqlite3.Connection, channel: models.Channel
+    connection: sqlite3.Connection,
+    channel: models.Channel,
+    category_list: list[models.Category],
 ) -> None:
     """채널 하나를 그린다.
 
@@ -138,6 +177,8 @@ def _render_row(
             help="등록할 때 yt-dlp 가 준 이름입니다. 목록은 이 이름"
             " 순으로 정렬됩니다.",
         )
+        if category_list:
+            _render_defaults(connection, channel.id, category_list)
         left, right = st.columns(2)
         if left.button("이름 저장", key=f"channels_save_{channel.id}"):
             _save_title(connection, channel.id, edited)
@@ -146,6 +187,46 @@ def _render_row(
             st.rerun()
 
 
+def _render_defaults(
+    connection: sqlite3.Connection,
+    channel_pk: int,
+    category_list: list[models.Category],
+) -> None:
+    """채널의 기본 카테고리를 그린다. 바꾸는 즉시 저장한다.
+
+    키가 세션에 없을 때만 DB 값으로 채운다. key 없는 위젯에 DB 값을
+    초기값으로 주면, 적는 순간 위젯 ID 가 바뀌어 바로 다음 조작이
+    버려진다. 다른 화면에 다녀오면 위젯 값이 버려져 DB 값으로 다시
+    시작한다.
+    """
+    key = f"channels_default_categories_{channel_pk}"
+    if key not in st.session_state:
+        st.session_state[key] = list(
+            channels.default_category_ids(connection, channel_pk)
+        )
+    category_picker.render(
+        "기본 카테고리",
+        category_list,
+        key,
+        _DEFAULTS_HELP,
+        on_change=functools.partial(
+            _save_defaults, connection, channel_pk, key
+        ),
+    )
+
+
+def _save_defaults(
+    connection: sqlite3.Connection, channel_pk: int, key: str
+) -> None:
+    """바뀐 기본 카테고리를 저장한다. 선택의 ``on_change`` 콜백이다."""
+    try:
+        channels.set_default_categories(
+            connection, channel_pk, st.session_state.get(key, [])
+        )
+    except ValueError as error:
+        st.error(str(error))
+
+
 def _save_title(
     connection: sqlite3.Connection, channel_pk: int, title: str
 ) -> None:
```

- [ ] **Step 4: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `954 passed, 1 skipped`.

- [ ] **Step 5: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
✨ feat(channels): 채널마다 기본 카테고리 두기

등록 탭과 등록된 채널 탭에서 기본 카테고리를 정한다. 목록 탭은
바꾸는 즉시 저장한다. key 를 주고 키가 없을 때만 DB 값으로 채워,
연달아 바꿔도 조작이 버려지지 않게 한다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/pages/channels.py \
  src/notebooklm_st/services/channels.py \
  tests/pages/test_channels.py \
  tests/services/test_channels.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 10: 새 영상 확인 탭에서 카테고리 고르기

**Files:**
- Modify: `src/notebooklm_st/pages/_channel_check.py`, `src/notebooklm_st/pages/_channel_enqueue.py`
- Test: `tests/pages/test_channels.py`

**Interfaces:**
- Consumes: `channels.default_category_ids` (Task 9), `category_picker` (Task 8), `runner.enqueue(category_ids=…)` (Task 5).
- Produces: `_channel_check.categories_key(channel_pk: int) -> str`; `_channel_enqueue.render(registry, entries, table_key, questions_key, categories_key, selected, chosen, category_ids, auto_save)`.

설계서 §8.4. 기존 넣기 테스트는 모두 `checked()` 를 거친다. 이 도우미가 카테고리 "경제" 를 채널 기본값으로 두므로, 확인 탭이 미리 채운 값으로 기존 테스트가 그대로 돈다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_channels.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/pages/test_channels.py b/tests/pages/test_channels.py
--- a/tests/pages/test_channels.py
+++ b/tests/pages/test_channels.py
@@ -168,7 +168,10 @@ def put_pending(connection, video_id) -> None:
 
 
 def checked(app_db, monkeypatch, *entries, choose=True):
-    """채널과 질문을 하나씩 두고 확인을 눌러 신규를 띄운다.
+    """채널·질문·카테고리를 하나씩 두고 확인을 눌러 신규를 띄운다.
+
+    카테고리는 채널의 기본값으로 둔다. 확인 탭이 그 값으로 미리
+    채우므로 넣기 버튼이 카테고리 때문에 잠기지 않는다.
 
     Args:
         app_db: 앱이 쓰는 임시 DB.
@@ -179,7 +182,9 @@ def checked(app_db, monkeypatch, *entries, choose=True):
     Returns:
         확인을 마친 AppTest.
     """
-    registered(app_db)
+    category = categories.add_category(app_db, "경제")
+    channel = registered(app_db)
+    channels.set_default_categories(app_db, channel.id, [category.id])
     questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
     check_feed(monkeypatch, feed_with(*entries))
     app = v1.AppTest.from_function(script)
@@ -994,3 +999,122 @@ def test_default_categories_survive_quick_changes(app_db) -> None:
 
     assert not app.exception
     assert channels.default_category_ids(app_db, channel.id) == ()
+
+
+def check_key(channel_pk: int) -> str:
+    """확인 탭의 카테고리 선택 key."""
+    return f"channels_check_categories_{channel_pk}"
+
+
+def record_categories(monkeypatch) -> list[tuple[int, ...]]:
+    """``runner.enqueue`` 를 막고 넘어온 카테고리 ID 를 기록한다."""
+    from notebooklm_st.pages import _channel_enqueue
+
+    received: list[tuple[int, ...]] = []
+
+    def fake_enqueue(registry, url, question_list, db_path, **kwargs):
+        """대기로만 넣고 카테고리 ID 를 기록한다."""
+        received.append(tuple(kwargs["category_ids"]))
+        return registry.enqueue(
+            url, youtube.extract_video_id(url) or "", tuple(question_list)
+        )
+
+    monkeypatch.setattr(_channel_enqueue.runner, "enqueue", fake_enqueue)
+    return received
+
+
+def test_the_check_tab_starts_from_the_channel_defaults(
+    app_db, monkeypatch
+) -> None:
+    """확인 탭의 카테고리는 그 채널의 기본값으로 시작한다."""
+    app = checked(app_db, monkeypatch, make_entry())
+    channel = channels.list_channels(app_db)[0]
+
+    picker = app.multiselect(key=check_key(channel.id))
+    assert picker.label == "카테고리"
+    assert picker.value == list(
+        channels.default_category_ids(app_db, channel.id)
+    )
+
+
+def test_a_changed_check_choice_is_not_saved_to_the_channel(
+    app_db, monkeypatch
+) -> None:
+    """확인 탭에서 바꾼 카테고리는 채널 기본값에 적지 않는다."""
+    app = checked(app_db, monkeypatch, make_entry())
+    channel = channels.list_channels(app_db)[0]
+    before = channels.default_category_ids(app_db, channel.id)
+
+    app.multiselect(key=check_key(channel.id)).set_value([]).run()
+
+    assert not app.exception
+    assert channels.default_category_ids(app_db, channel.id) == before
+
+
+def test_each_channel_starts_from_its_own_defaults(app_db, monkeypatch) -> None:
+    """채널을 바꾸면 그 채널의 기본값으로 시작한다."""
+    economy = categories.add_category(app_db, "경제")
+    politics = categories.add_category(app_db, "정치")
+    first = registered(app_db, title="가 채널")
+    second = registered(app_db, title="나 채널", channel_id=OTHER_CHANNEL_ID)
+    channels.set_default_categories(app_db, first.id, [economy.id])
+    channels.set_default_categories(app_db, second.id, [politics.id])
+    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
+    check_feed(monkeypatch, feed_with(make_entry()))
+
+    app = v1.AppTest.from_function(script)
+    app.run()
+    button_by(app, "새 영상 확인").click().run()
+    assert app.multiselect(key=check_key(first.id)).value == [economy.id]
+
+    app.selectbox[0].set_value(channels.list_channels(app_db)[1]).run()
+    button_by(app, "새 영상 확인").click().run()
+
+    assert not app.exception
+    assert app.multiselect(key=check_key(second.id)).value == [politics.id]
+
+
+def test_enqueue_waits_for_a_category(app_db, monkeypatch) -> None:
+    """질문과 행을 골랐어도 카테고리가 없으면 버튼이 잠긴다."""
+    entries = (make_entry(),)
+    app = checked(app_db, monkeypatch, *entries)
+    channel = channels.list_channels(app_db)[0]
+    app.multiselect(key=check_key(channel.id)).set_value([]).run()
+    select_videos(app, entries, [0])
+    app.run()
+
+    assert "카테고리를 하나 이상 고르세요." in [item.value for item in app.info]
+    button = app.button(key="channels_enqueue")
+    assert button.label == "선택한 영상 요약 (1건)"
+    assert button.disabled is True
+
+
+def test_enqueue_hands_the_chosen_categories(app_db, monkeypatch) -> None:
+    """고른 카테고리 ID 가 넣는 영상마다 러너로 넘어간다."""
+    received = record_categories(monkeypatch)
+    app = checked(app_db, monkeypatch, *BOTH)
+    [category] = categories.list_categories(app_db)
+
+    click_enqueue(app, BOTH, [0, 1])
+
+    assert not app.exception
+    assert received == [(category.id,), (category.id,)]
+
+
+def test_without_categories_the_check_tab_says_so(app_db, monkeypatch) -> None:
+    """카테고리가 없으면 안내하고, 넣기 버튼 없이 표만 보인다."""
+    registered(app_db)
+    questions.add_question(app_db, "핵심 주장", "핵심 주장은?")
+    check_feed(monkeypatch, feed_with(make_entry()))
+
+    app = v1.AppTest.from_function(script)
+    app.run()
+    button_by(app, "새 영상 확인").click().run()
+
+    assert not app.exception
+    assert (
+        "카테고리 관리 화면에서 카테고리를 먼저 등록하세요. 카테고리를"
+        " 고르지 않으면 질의할 수 없습니다."
+    ) in [item.value for item in app.info]
+    assert len(app.dataframe) == 1
+    assert all(item.key != "channels_enqueue" for item in app.button)
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest tests/pages/test_channels.py -q
```

기대: `6 failed` — 새로 쓴 여섯 건(확인 탭에 `channels_check_categories_…` 위젯이 없다).

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/pages/_channel_check.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/pages/_channel_check.py b/src/notebooklm_st/pages/_channel_check.py
--- a/src/notebooklm_st/pages/_channel_check.py
+++ b/src/notebooklm_st/pages/_channel_check.py
@@ -20,10 +20,15 @@ import sqlite3
 import streamlit as st
 
 from notebooklm_st import session
-from notebooklm_st.components import auto_save_toggle, queue_notice
+from notebooklm_st.components import (
+    auto_save_toggle,
+    category_picker,
+    queue_notice,
+)
 from notebooklm_st.core import models, new_videos
 from notebooklm_st.pages import _channel_enqueue, _channel_videos
 from notebooklm_st.services import (
+    categories,
     channel_feed,
     channels,
     questions,
@@ -54,6 +59,22 @@ class _Checked:
     """``entries`` 에서 뺀 신규 Shorts 의 건수."""
 
 
+@dataclasses.dataclass(frozen=True, slots=True)
+class _Choices:
+    """넣기에 쓸 질문과 카테고리. 화면 전용 값이다."""
+
+    questions: list[models.Question]
+    category_ids: list[int]
+    ready: bool
+    """질문과 카테고리가 둘 다 등록되어 있다. 거짓이면 넣기 쪽을 그리지
+    않는다."""
+
+
+def categories_key(channel_pk: int) -> str:
+    """확인 탭의 카테고리 선택 key. 기준일처럼 채널마다 다르다."""
+    return f"channels_check_categories_{channel_pk}"
+
+
 def render(
     connection: sqlite3.Connection, channel_list: list[models.Channel]
 ) -> None:
@@ -145,21 +166,10 @@ def _check(
 def _render_found(connection: sqlite3.Connection, found: _Checked) -> None:
     """확인 결과를 표로 그리고 고른 영상을 넣을 수 있게 한다.
 
-    질문 선택은 결과보다 먼저 그린다. 결과가 오류나 빈 목록이어도
-    위젯이 그려져야 고른 질문이 남는다.
+    질문과 카테고리 선택은 결과보다 먼저 그린다. 결과가 오류나 빈
+    목록이어도 위젯이 그려져야 고른 값이 남는다.
     """
-    question_list = questions.list_questions(connection)
-    chosen: list[models.Question] = []
-    if not question_list:
-        st.info("질문 관리 화면에서 질문을 먼저 등록하세요.")
-    else:
-        chosen = st.multiselect(
-            "질문 선택",
-            options=question_list,
-            format_func=lambda question: question.title,
-            key=_QUESTIONS_KEY,
-            help="고른 질문을 이번에 넣는 영상 모두에 씁니다.",
-        )
+    choices = _render_choices(connection, found.channel_pk)
     if found.error is not None:
         st.error(f"{found.title}: {found.error}")
         return
@@ -169,7 +179,7 @@ def _render_found(connection: sqlite3.Connection, found: _Checked) -> None:
         return
     registry = session.get_registry()
     auto_save = False
-    if question_list:
+    if choices.ready:
         auto_save = auto_save_toggle.render(
             connection, _AUTO_SAVE_KEY, _AUTO_SAVE_LOCKED_KEY
         )
@@ -180,18 +190,76 @@ def _render_found(connection: sqlite3.Connection, found: _Checked) -> None:
         found.entries, _channel_enqueue.generation()
     )
     selected = _channel_videos.render(found.entries, registry.list_all(), key)
-    if question_list:
+    if choices.ready:
         _channel_enqueue.render(
             registry,
             found.entries,
             key,
             _QUESTIONS_KEY,
+            categories_key(found.channel_pk),
             selected,
-            chosen,
+            choices.questions,
+            choices.category_ids,
             auto_save,
         )
 
 
+def _render_choices(
+    connection: sqlite3.Connection, channel_pk: int
+) -> _Choices:
+    """질문 선택과 카테고리 선택을 그린다.
+
+    둘 중 하나라도 등록된 것이 없으면 그 자리에 안내를 보인다.
+
+    Args:
+        connection: 열린 커넥션.
+        channel_pk: 확인한 채널. 카테고리 선택의 key 와 기본값을
+            정한다.
+
+    Returns:
+        고른 질문과 카테고리 ID, 넣기 쪽을 그릴 수 있는지.
+    """
+    question_list = questions.list_questions(connection)
+    chosen: list[models.Question] = []
+    if not question_list:
+        st.info("질문 관리 화면에서 질문을 먼저 등록하세요.")
+    else:
+        chosen = st.multiselect(
+            "질문 선택",
+            options=question_list,
+            format_func=lambda question: question.title,
+            key=_QUESTIONS_KEY,
+            help="고른 질문을 이번에 넣는 영상 모두에 씁니다.",
+        )
+    category_list = categories.list_categories(connection)
+    category_ids: list[int] = []
+    if not category_list:
+        st.info(category_picker.NO_CATEGORIES)
+    else:
+        category_ids = _render_categories(connection, channel_pk, category_list)
+    return _Choices(chosen, category_ids, bool(question_list and category_list))
+
+
+def _render_categories(
+    connection: sqlite3.Connection,
+    channel_pk: int,
+    category_list: list[models.Category],
+) -> list[int]:
+    """그 채널의 카테고리 선택을 그리고 고른 ID 를 돌려준다.
+
+    키가 세션에 없을 때만 채널의 기본 카테고리로 채운다. 바꾼 값은
+    채널에 적지 않는다 — 기본값은 등록된 채널 탭에서 고친다.
+    """
+    key = categories_key(channel_pk)
+    if key not in st.session_state:
+        st.session_state[key] = list(
+            channels.default_category_ids(connection, channel_pk)
+        )
+    return category_picker.render(
+        "카테고리", category_list, key, category_picker.QUERY_HELP
+    )
+
+
 def _render_shorts_note(count: int) -> None:
     """뺀 Shorts 의 건수를 알린다. 뺀 것이 없으면 그리지 않는다.
```

`src/notebooklm_st/pages/_channel_enqueue.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/pages/_channel_enqueue.py b/src/notebooklm_st/pages/_channel_enqueue.py
--- a/src/notebooklm_st/pages/_channel_enqueue.py
+++ b/src/notebooklm_st/pages/_channel_enqueue.py
@@ -44,11 +44,13 @@ def render(
     entries: tuple[models.FeedEntry, ...],
     table_key: str,
     questions_key: str,
+    categories_key: str,
     selected: list[models.FeedEntry],
     chosen: list[models.Question],
+    category_ids: list[int],
     auto_save: bool,
 ) -> None:
-    """질문 안내, 넣기 버튼, 넣은 뒤의 결과를 그린다.
+    """질문·카테고리 안내, 넣기 버튼, 넣은 뒤의 결과를 그린다.
 
     Args:
         registry: 실행 레지스트리.
@@ -56,18 +58,29 @@ def render(
         table_key: 표의 위젯 key. 콜백이 누른 순간의 선택을 읽는다.
         questions_key: 질문 선택의 위젯 key. 콜백이 누른 순간의
             질문을 읽는다.
+        categories_key: 카테고리 선택의 위젯 key. 질문과 같다.
         selected: 지금 표에서 고른 영상. 버튼 라벨과 잠금에 쓴다.
         chosen: 지금 고른 질문들. 버튼 잠금에 쓴다.
+        category_ids: 지금 고른 카테고리 ID. 버튼 잠금에 쓴다.
         auto_save: 화면에 보이는 자동 저장 값.
     """
     if not chosen:
         st.info("질문을 하나 이상 고르세요.")
+    if not category_ids:
+        st.info("카테고리를 하나 이상 고르세요.")
     st.button(
         f"선택한 영상 요약 ({len(selected)}건)",
         key="channels_enqueue",
-        disabled=not selected or not chosen,
+        disabled=not selected or not chosen or not category_ids,
         on_click=_enqueue_selected,
-        args=(registry, entries, table_key, questions_key, auto_save),
+        args=(
+            registry,
+            entries,
+            table_key,
+            questions_key,
+            categories_key,
+            auto_save,
+        ),
     )
     _render_result()
 
@@ -77,31 +90,34 @@ def _enqueue_selected(
     entries: tuple[models.FeedEntry, ...],
     table_key: str,
     questions_key: str,
+    categories_key: str,
     auto_save: bool,
 ) -> None:
     """고른 영상을 목록 순서로 대기열에 넣고 표의 선택을 비운다.
 
-    넣기 버튼의 ``on_click`` 콜백이다. 표 선택과 질문은 버튼을 그릴
-    때가 아니라 누른 순간의 세션 값을 읽는다. 결과 문구는 세션에
-    적어 다음 그림에서 한 번 보인다.
+    넣기 버튼의 ``on_click`` 콜백이다. 표 선택·질문·카테고리는 버튼을
+    그릴 때가 아니라 누른 순간의 세션 값을 읽는다. 결과 문구는
+    세션에 적어 다음 그림에서 한 번 보인다.
 
     Args:
         registry: 실행 레지스트리.
         entries: 표에 그린 신규 영상.
         table_key: 표의 위젯 key.
         questions_key: 질문 선택의 위젯 key.
+        categories_key: 카테고리 선택의 위젯 key.
         auto_save: 화면에 보이는 자동 저장 값. 넣은 실행마다 고정된다.
     """
     state = st.session_state.get(table_key) or {}
     rows = state.get("selection", {}).get("rows", [])
     chosen = st.session_state.get(questions_key, [])
+    category_ids = st.session_state.get(categories_key, [])
     targets = _channel_videos.selected_entries(entries, rows)
-    if not targets or not chosen:
+    if not targets or not chosen or not category_ids:
         return
     ahead = queue_notice.count_ahead(registry)
     paused = registry.paused_reason() is not None
     digesting = session.get_digest_registry().is_running()
-    added = _enqueue_each(registry, targets, chosen, auto_save)
+    added = _enqueue_each(registry, targets, chosen, category_ids, auto_save)
     st.session_state[_GENERATION_KEY] = generation() + 1
     if added == 0:
         st.session_state[_ENQUEUED_KEY] = _Enqueued(_ALL_PENDING, added=False)
@@ -120,6 +136,7 @@ def _enqueue_each(
     registry: run_registry.RunRegistry,
     targets: list[models.FeedEntry],
     chosen: list[models.Question],
+    category_ids: list[int],
     auto_save: bool,
 ) -> int:
     """대기·실행 중이 아닌 영상을 차례로 넣고 넣은 수를 돌려준다.
@@ -131,6 +148,7 @@ def _enqueue_each(
         registry: 실행 레지스트리.
         targets: 넣을 영상. 이 순서대로 대기열에 선다.
         chosen: 모든 영상에 쓸 질문들.
+        category_ids: 모든 영상에 붙일 카테고리 ID.
         auto_save: 넣은 실행에 고정할 자동 저장 값.
 
     Returns:
@@ -148,6 +166,7 @@ def _enqueue_each(
             store.default_db_path(),
             auto_save=auto_save,
             is_blocked=digests.is_running,
+            category_ids=category_ids,
         )
         added += 1
     return added
```

- [ ] **Step 4: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `960 passed, 1 skipped`.

- [ ] **Step 5: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
✨ feat(channels): 새 영상 확인 탭에서 카테고리 고르기

확인 탭의 카테고리 선택을 채널의 기본값으로 미리 채우고, 고른
카테고리 없이는 넣지 못하게 한다. 바꾼 값은 채널에 적지 않는다.
카테고리가 하나도 없으면 질의 화면처럼 넣기 쪽을 그리지 않는다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/pages/_channel_check.py \
  src/notebooklm_st/pages/_channel_enqueue.py \
  tests/pages/test_channels.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 11: 동기화가 문서의 카테고리를 읽고 맞추기

**Files:**
- Modify: `src/notebooklm_st/core/outline_import.py`, `src/notebooklm_st/core/sync_models.py`, `src/notebooklm_st/services/run_history_sync.py`, `src/notebooklm_st/services/history_sync.py`
- Test: `tests/core/test_outline_import.py`, `tests/services/test_run_history_sync.py`, `tests/services/test_history_sync.py`

**Interfaces:**
- Consumes: `category_names.split`·`ordered` (Task 3), `markdown_export.CATEGORY_LABEL` (Task 7), `categories.ensure` (Task 4).
- Produces: `outline_import.find_categories(markdown) -> tuple[str, ...] | None`; `sync_models.SyncCreate.categories`, `sync_models.SyncCategoryUpdate(run, categories)`, `SyncPlan.category_updates`·`new_categories`; `run_history_sync.replace_categories(connection, run_id, outline_id, names) -> bool`(커밋하지 않음); `history_sync.plan(exported, documents, known_categories=frozenset())`; `history_sync.SyncResult.recategorized`·`categories_added`. Task 12 가 미리보기에 쓴다.

설계서 §6.4·§7.4·§7.6. `test_list_exported_carries_the_categories` 는 Task 5 가 이미 참으로 만든 동작이라 넣자마자 통과한다(공유 SELECT 를 `list_exported` 쪽에서 지킨다).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/core/test_outline_import.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/core/test_outline_import.py b/tests/core/test_outline_import.py
--- a/tests/core/test_outline_import.py
+++ b/tests/core/test_outline_import.py
@@ -317,3 +317,92 @@ def test_reads_back_what_the_export_wrote() -> None:
     text = markdown_export.to_markdown(summary, [], "강의", metadata)
 
     assert outline_import.find_metadata(text) == metadata
+
+
+CATEGORIZED = (
+    "- 제목: 밸류에이션 강의\n"
+    "- 카테고리: 인공지능, 경제\n"
+    "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
+    "\n---\n\n세 가지다.\n"
+)
+
+
+def test_finds_the_categories_in_name_order() -> None:
+    """카테고리 줄을 이름들로 나눠 이름 순으로 돌려준다."""
+    assert outline_import.find_categories(CATEGORIZED) == ("경제", "인공지능")
+
+
+def test_categories_are_none_without_the_line() -> None:
+    """줄이 없으면 읽지 못한 것이다."""
+    assert outline_import.find_categories(SUMMARY) is None
+
+
+@pytest.mark.parametrize("bullet", ["*", "+"])
+def test_categories_accept_other_bullets(bullet: str) -> None:
+    """Outline 이 글머리표를 바꿔 돌려줘도 읽는다."""
+    markdown = f"{bullet} 카테고리: 경제\n"
+
+    assert outline_import.find_categories(markdown) == ("경제",)
+
+
+def test_unescapes_punctuation_in_the_categories() -> None:
+    """Outline 이 넣은 역슬래시 이스케이프를 걷는다."""
+    markdown = "- 카테고리: R\\&D, A\\/B 테스트\n"
+
+    assert outline_import.find_categories(markdown) == ("A/B 테스트", "R&D")
+
+
+def test_ignores_categories_after_the_rule() -> None:
+    """첫 구분선 뒤의 줄은 본문이다."""
+    markdown = "- 제목: 강의\n\n---\n\n- 카테고리: 경제\n"
+
+    assert outline_import.find_categories(markdown) is None
+
+
+def test_categories_drop_only_the_names_outside_the_rule() -> None:
+    """규칙에 맞지 않는 이름만 버린다."""
+    markdown = "- 카테고리: 경제, *강조*\n"
+
+    assert outline_import.find_categories(markdown) == ("경제",)
+
+
+@pytest.mark.parametrize("value", ["", "*강조*, _밑줄_", " , "])
+def test_categories_without_a_readable_name_are_none(value: str) -> None:
+    """읽을 이름이 하나도 없으면 읽지 못한 것이다."""
+    markdown = f"- 카테고리: {value}\n"
+
+    assert outline_import.find_categories(markdown) is None
+
+
+def test_takes_the_first_category_line() -> None:
+    """같은 라벨이 둘이면 첫 줄만 본다."""
+    markdown = "- 카테고리: 경제\n- 카테고리: 정치\n"
+
+    assert outline_import.find_categories(markdown) == ("경제",)
+
+
+def test_a_category_label_inside_another_value_is_not_read() -> None:
+    """다른 라벨의 값 안에 나온 글자는 카테고리 줄이 아니다."""
+    markdown = "- 제목: 카테고리: 경제\n"
+
+    assert outline_import.find_categories(markdown) is None
+
+
+def test_reads_back_the_categories_the_export_wrote() -> None:
+    """저장이 쓴 카테고리 줄을 같은 이름으로 되읽는다.
+
+    쓰는 쪽과 읽는 쪽이 라벨과 구분자를 함께 쓴다. 한쪽만 바뀌면
+    모든 문서의 카테고리가 조용히 사라진다.
+    """
+    summary = models.RunSummary(
+        id=1,
+        url="https://youtu.be/dQw4w9WgXcQ",
+        video_id="dQw4w9WgXcQ",
+        title="강의",
+        created_at="2026-09-20T10:00:00",
+        answer_count=0,
+        categories=("A/B 테스트", "R&D", "경제"),
+    )
+    markdown = markdown_export.to_markdown(summary, [], "강의", None)
+
+    assert outline_import.find_categories(markdown) == summary.categories
```

`tests/services/test_run_history_sync.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/services/test_run_history_sync.py b/tests/services/test_run_history_sync.py
--- a/tests/services/test_run_history_sync.py
+++ b/tests/services/test_run_history_sync.py
@@ -7,6 +7,7 @@ import pytest
 
 from notebooklm_st.core import models, sync_models
 from notebooklm_st.services import (
+    categories,
     run_history,
     run_history_sync,
     run_links,
@@ -69,6 +70,7 @@ def make_create(
     doc_id: str = "doc-9",
     video_id: str = "dQw4w9WgXcQ",
     metadata: models.VideoMetadata | None = None,
+    names: tuple[str, ...] = (),
 ) -> sync_models.SyncCreate:
     """동기화가 만들 이력 한 건."""
     document = sync_models.ListedDocument(
@@ -83,6 +85,7 @@ def make_create(
         url=f"https://www.youtube.com/watch?v={video_id}",
         video_id=video_id,
         metadata=metadata,
+        categories=names,
     )
 
 
@@ -352,3 +355,103 @@ def test_write_metadata_does_not_commit(connection) -> None:
     connection.rollback()
 
     assert run_history.load_metadata(connection, run_id) is None
+
+
+def register(connection: sqlite3.Connection, *names: str) -> list[int]:
+    """카테고리를 등록하고 ID 를 넘긴 순서대로 돌려준다."""
+    return [categories.add_category(connection, name).id for name in names]
+
+
+def exported_with(connection: sqlite3.Connection, *names: str) -> int:
+    """그 카테고리를 단 채 ``doc-1`` 에 저장된 실행 하나를 만든다."""
+    run_id = run_history.save_run(
+        connection, make_result(), category_ids=register(connection, *names)
+    )
+    export(connection, run_id)
+    return run_id
+
+
+def test_list_exported_carries_the_categories(connection) -> None:
+    """저장된 실행 목록도 카테고리를 싣는다."""
+    exported_with(connection, "경제")
+
+    assert run_history_sync.list_exported(connection)[0].categories == ("경제",)
+
+
+def test_insert_exported_links_the_categories_by_name(connection) -> None:
+    """되살린 행에 문서의 카테고리를 이름으로 잇는다."""
+    register(connection, "인공지능", "경제")
+
+    run_history_sync.insert_exported(
+        connection, make_create(names=("경제", "인공지능"))
+    )
+    connection.commit()
+
+    assert run_history_sync.list_exported(connection)[0].categories == (
+        "경제",
+        "인공지능",
+    )
+
+
+def test_insert_exported_skips_an_unregistered_name(connection) -> None:
+    """등록되지 않은 이름은 잇지 않는다. 등록은 적용이 먼저 한다."""
+    register(connection, "경제")
+
+    run_history_sync.insert_exported(
+        connection, make_create(names=("경제", "정치"))
+    )
+    connection.commit()
+
+    assert run_history_sync.list_exported(connection)[0].categories == ("경제",)
+
+
+def test_replace_categories_changes_them(connection) -> None:
+    """이름 집합이 다르면 바꾸고 참을 돌려준다."""
+    run_id = exported_with(connection, "경제")
+    register(connection, "정치")
+
+    changed = run_history_sync.replace_categories(
+        connection, run_id, "doc-1", ("정치",)
+    )
+    connection.commit()
+
+    assert changed is True
+    assert run_history_sync.list_exported(connection)[0].categories == ("정치",)
+
+
+def test_replace_categories_with_the_same_names_is_false(connection) -> None:
+    """이름 집합이 같으면 쓰지 않고 거짓을 돌려준다."""
+    run_id = exported_with(connection, "경제", "정치")
+
+    changed = run_history_sync.replace_categories(
+        connection, run_id, "doc-1", ("정치", "경제")
+    )
+
+    assert changed is False
+
+
+def test_replace_categories_needs_the_document_id_to_match(
+    connection,
+) -> None:
+    """문서 ID 가 다르면 쓰지 않는다. 다시 쓰인 ID 를 지킨다."""
+    run_id = exported_with(connection, "경제")
+    register(connection, "정치")
+
+    changed = run_history_sync.replace_categories(
+        connection, run_id, "other-doc", ("정치",)
+    )
+    connection.commit()
+
+    assert changed is False
+    assert run_history_sync.list_exported(connection)[0].categories == ("경제",)
+
+
+def test_replace_categories_does_not_commit(connection) -> None:
+    """트랜잭션은 호출자가 소유한다."""
+    run_id = exported_with(connection, "경제")
+    register(connection, "정치")
+
+    run_history_sync.replace_categories(connection, run_id, "doc-1", ("정치",))
+    connection.rollback()
+
+    assert run_history_sync.list_exported(connection)[0].categories == ("경제",)
```

`tests/services/test_history_sync.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/services/test_history_sync.py b/tests/services/test_history_sync.py
--- a/tests/services/test_history_sync.py
+++ b/tests/services/test_history_sync.py
@@ -7,6 +7,7 @@ import pytest
 
 from notebooklm_st.core import models, sync_models
 from notebooklm_st.services import (
+    categories,
     history_sync,
     run_history,
     run_history_sync,
@@ -32,11 +33,22 @@ DOC_METADATA = models.VideoMetadata(
     channel="어떤 채널", upload_date="2026-09-20"
 )
 
+CATEGORY_BODY = (
+    "- 제목: 밸류에이션 강의\n"
+    "- 카테고리: 인공지능, 경제\n"
+    "- 영상 URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
+    "\n---\n\n## 핵심 주장\n\n세 가지다.\n"
+)
+
+DOC_CATEGORIES = ("경제", "인공지능")
+"""``CATEGORY_BODY`` 에서 읽히는 이름. 이름 순이다."""
+
 
 def make_run(
     run_id: int,
     outline_id: str,
     metadata: models.VideoMetadata | None = None,
+    names: tuple[str, ...] = (),
 ) -> models.RunSummary:
     """저장된 실행 요약을 만든다."""
     return models.RunSummary(
@@ -51,6 +63,7 @@ def make_run(
         outline_title="정리한 제목",
         exported_at="2026-09-22T15:00:00",
         metadata=metadata,
+        categories=names,
     )
 
 
@@ -681,3 +694,207 @@ def test_a_channel_with_doubled_spaces_settles_after_one_apply(
         "투자 연구소"
     ]
     assert second.updates == ()
+
+
+def test_plan_carries_the_categories_of_a_new_document() -> None:
+    """만들 문서의 카테고리를 생성 대상에 싣는다."""
+    result = history_sync.plan([], [make_document("doc-9", CATEGORY_BODY)])
+
+    assert result.creates[0].categories == DOC_CATEGORIES
+
+
+def test_plan_creates_without_categories_when_the_head_has_none() -> None:
+    """카테고리 줄이 없으면 카테고리 없이 만든다."""
+    result = history_sync.plan([], [make_document("doc-9")])
+
+    assert result.creates[0].categories == ()
+
+
+def test_plan_updates_categories_that_differ() -> None:
+    """문서의 이름 집합이 로컬과 다르면 카테고리 갱신 대상이다."""
+    run = make_run(1, "doc-1", names=("경제",))
+
+    result = history_sync.plan(
+        [run], [make_document("doc-1", CATEGORY_BODY)], {"경제", "인공지능"}
+    )
+
+    assert result.category_updates == (
+        sync_models.SyncCategoryUpdate(run=run, categories=DOC_CATEGORIES),
+    )
+
+
+def test_plan_leaves_equal_categories_alone() -> None:
+    """이름 집합이 같으면 손대지 않는다."""
+    run = make_run(1, "doc-1", names=DOC_CATEGORIES)
+
+    result = history_sync.plan(
+        [run], [make_document("doc-1", CATEGORY_BODY)], set(DOC_CATEGORIES)
+    )
+
+    assert result.category_updates == ()
+
+
+def test_plan_never_clears_local_categories() -> None:
+    """문서에서 카테고리를 못 읽으면 로컬 값을 그대로 둔다."""
+    run = make_run(1, "doc-1", names=("경제",))
+
+    result = history_sync.plan([run], [make_document("doc-1")], {"경제"})
+
+    assert result.category_updates == ()
+
+
+def test_plan_lists_the_names_it_does_not_know() -> None:
+    """생성·갱신 대상의 이름 중 로컬에 없는 것을 이름 순으로 모은다."""
+    other = CATEGORY_BODY.replace("인공지능, 경제", "정치")
+
+    result = history_sync.plan(
+        [make_run(1, "doc-1")],
+        [make_document("doc-1", CATEGORY_BODY), make_document("new-1", other)],
+        {"경제"},
+    )
+
+    assert result.new_categories == ("인공지능", "정치")
+
+
+def test_a_category_update_only_plan_is_not_empty() -> None:
+    """카테고리 갱신만 있어도 적용할 것이 있다."""
+    plan = sync_models.SyncPlan(
+        deletes=(),
+        creates=(),
+        skips=(),
+        category_updates=(
+            sync_models.SyncCategoryUpdate(
+                run=make_run(1, "doc-1"), categories=("경제",)
+            ),
+        ),
+    )
+
+    assert not plan.is_empty
+
+
+def known_names(connection: sqlite3.Connection) -> set[str]:
+    """등록된 카테고리 이름들."""
+    return {item.name for item in categories.list_categories(connection)}
+
+
+def test_apply_registers_and_links_categories_in_one_commit(
+    connection,
+) -> None:
+    """새 이름을 등록하고, 되살린 행과 기존 행에 잇는다."""
+    save_exported(connection, "doc-1")
+    documents = [
+        make_document("doc-1", CATEGORY_BODY),
+        make_document("new-1", CATEGORY_BODY),
+    ]
+    plan = history_sync.plan(
+        run_history_sync.list_exported(connection),
+        documents,
+        known_names(connection),
+    )
+
+    result = history_sync.apply(connection, plan)
+
+    assert not connection.in_transaction
+    assert result == history_sync.SyncResult(
+        deleted=0, created=1, recategorized=1, categories_added=2
+    )
+    assert known_names(connection) == set(DOC_CATEGORIES)
+    runs = run_history_sync.list_exported(connection)
+    assert [run.categories for run in runs] == [DOC_CATEGORIES] * 2
+
+
+class FailingCategoryWrite:
+    """카테고리 연결을 지우는 문장에서만 터지는 커넥션 대역.
+
+    나머지 호출은 진짜 커넥션이 그대로 처리한다. 등록·삽입은 됐는데
+    카테고리 교체가 죽는 상황을 재현한다.
+    """
+
+    def __init__(self, connection: sqlite3.Connection) -> None:
+        """감쌀 진짜 커넥션을 받는다."""
+        self._connection = connection
+
+    def execute(self, sql, *args):
+        """카테고리 연결을 지우는 문장만 실패시킨다."""
+        if "DELETE FROM run_categories" in sql:
+            raise sqlite3.OperationalError("database is locked")
+        return self._connection.execute(sql, *args)
+
+    def __getattr__(self, name):
+        """나머지 속성은 진짜 커넥션에 맡긴다."""
+        return getattr(self._connection, name)
+
+
+def test_apply_rolls_back_when_a_category_replace_fails(connection) -> None:
+    """카테고리 교체가 죽으면 새 카테고리와 삽입도 되돌린다."""
+    save_exported(connection, "doc-1")
+    plan = history_sync.plan(
+        run_history_sync.list_exported(connection),
+        [make_document("doc-1", CATEGORY_BODY), make_document("new-1")],
+        known_names(connection),
+    )
+
+    with pytest.raises(sqlite3.OperationalError):
+        # 일부 호출만 가로채는 대역이라 nominal 타입이 아니다.
+        failing = FailingCategoryWrite(connection)
+        history_sync.apply(failing, plan)  # type: ignore[arg-type]
+
+    assert known_names(connection) == set()
+    runs = run_history_sync.list_exported(connection)
+    assert [run.outline_id for run in runs] == ["doc-1"]
+
+
+def test_apply_does_not_replace_categories_of_a_reused_id(connection) -> None:
+    """낡은 계획의 교체는 ID 를 다시 받은 미저장 실행에 쓰지 않는다."""
+    gone = save_exported(connection, "doc-1")
+    stale = history_sync.plan(
+        run_history_sync.list_exported(connection),
+        [make_document("doc-1", CATEGORY_BODY)],
+        known_names(connection),
+    )
+    assert [change.run.id for change in stale.category_updates] == [gone]
+    run_history.delete_run(connection, gone)
+    reused = run_history.save_run(
+        connection,
+        models.RunResult(
+            url="https://youtu.be/dQw4w9WgXcQ",
+            video_id="dQw4w9WgXcQ",
+            title="새 실행",
+            items=(),
+        ),
+    )
+    assert reused == gone
+
+    result = history_sync.apply(connection, stale)
+
+    assert result.recategorized == 0
+    summary = run_history.load_run(connection, reused)
+    assert summary is not None
+    assert summary.categories == ()
+
+
+def test_a_second_plan_after_apply_has_no_category_work(connection) -> None:
+    """적용한 뒤 다시 계획하면 카테고리 갱신도 새 카테고리도 없다."""
+    save_exported(connection, "doc-1")
+    documents = [
+        make_document("doc-1", CATEGORY_BODY),
+        make_document("new-1", CATEGORY_BODY),
+    ]
+    history_sync.apply(
+        connection,
+        history_sync.plan(
+            run_history_sync.list_exported(connection),
+            documents,
+            known_names(connection),
+        ),
+    )
+
+    again = history_sync.plan(
+        run_history_sync.list_exported(connection),
+        documents,
+        known_names(connection),
+    )
+
+    assert again.category_updates == ()
+    assert again.new_categories == ()
+    assert again.is_empty
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest tests/core/test_outline_import.py tests/services/test_run_history_sync.py tests/services/test_history_sync.py -q
```

기대: `37 failed, 84 passed` — 새 테스트(`find_categories` 없음, `SyncCreate` 에 `categories` 없음 등)와, 도우미 `make_create` 가 아직 없는 `categories` 필드를 넘겨 실패하는 기존 `insert_exported` 테스트 일곱.

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/core/outline_import.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/core/outline_import.py b/src/notebooklm_st/core/outline_import.py
--- a/src/notebooklm_st/core/outline_import.py
+++ b/src/notebooklm_st/core/outline_import.py
@@ -13,7 +13,7 @@ import datetime
 import re
 from collections.abc import Iterator
 
-from notebooklm_st.core import markdown_export, models
+from notebooklm_st.core import category_names, markdown_export, models
 
 _RULE = re.compile(r"^\s*---\s*$")
 """머리 블록을 끝내는 구분선."""
@@ -65,6 +65,7 @@ def _labeled_line(label: str) -> re.Pattern[str]:
 
 _CHANNEL_LINE = _labeled_line(markdown_export.CHANNEL_LABEL)
 _UPLOAD_DATE_LINE = _labeled_line(markdown_export.UPLOAD_DATE_LABEL)
+_CATEGORY_LINE = _labeled_line(markdown_export.CATEGORY_LABEL)
 
 
 def find_source_url(markdown: str) -> str | None:
@@ -114,6 +115,28 @@ def find_metadata(markdown: str) -> models.VideoMetadata | None:
     return models.VideoMetadata(channel=channel, upload_date=upload_date)
 
 
+def find_categories(markdown: str) -> tuple[str, ...] | None:
+    """문서 머리 블록에서 카테고리 이름들을 찾는다.
+
+    머리 블록의 범위, 글머리표 변형, 역슬래시 걷기, 라벨마다 첫 줄만
+    보는 것은 채널 줄과 같다(``find_metadata``). 값은
+    ``category_names.split`` 으로 나눈다 — 규칙에 맞지 않는 이름은
+    버린다.
+
+    Args:
+        markdown: Outline 이 돌려준 문서 본문.
+
+    Returns:
+        읽은 이름들. 이름 순이다. 줄이 없거나 읽을 이름이 하나도
+        없으면 ``None`` — 읽지 못한 것이다. 동기화는 그 행을 손대지
+        않는다.
+    """
+    value = _first_value(markdown, _CATEGORY_LINE)
+    if value is None:
+        return None
+    return category_names.split(value) or None
+
+
 def _head_lines(markdown: str) -> Iterator[str]:
     """머리 블록의 줄을 차례로 내준다.
```

`src/notebooklm_st/core/sync_models.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/core/sync_models.py b/src/notebooklm_st/core/sync_models.py
--- a/src/notebooklm_st/core/sync_models.py
+++ b/src/notebooklm_st/core/sync_models.py
@@ -37,6 +37,8 @@ class SyncCreate:
     video_id: str
     metadata: models.VideoMetadata | None = None
     """문서 머리에서 읽은 채널·업로드 일자. 두 줄이 다 없으면 ``None``."""
+    categories: tuple[str, ...] = ()
+    """문서 머리에서 읽은 카테고리 이름. 줄이 없으면 비어 있다."""
 
 
 @dataclasses.dataclass(frozen=True, slots=True)
@@ -56,6 +58,15 @@ class SyncUpdate:
     """쓸 값. 문서가 준 칸과 로컬에 남길 칸을 합친 결과다."""
 
 
+@dataclasses.dataclass(frozen=True, slots=True)
+class SyncCategoryUpdate:
+    """동기화가 카테고리를 바꿀 기존 행 한 건."""
+
+    run: models.RunSummary
+    categories: tuple[str, ...]
+    """문서 머리에서 읽은 이름. 이 집합으로 바꾼다."""
+
+
 @dataclasses.dataclass(frozen=True, slots=True)
 class SyncPlan:
     """미리보기와 적용이 함께 쓰는 동기화 계획.
@@ -68,8 +79,20 @@ class SyncPlan:
     creates: tuple[SyncCreate, ...]
     skips: tuple[SyncSkip, ...]
     updates: tuple[SyncUpdate, ...] = ()
+    category_updates: tuple[SyncCategoryUpdate, ...] = ()
+    new_categories: tuple[str, ...] = ()
+    """로컬에 없어 새로 등록할 이름. 이름 순이다."""
 
     @property
     def is_empty(self) -> bool:
-        """지울 것도 만들 것도 갱신할 것도 없다."""
-        return not self.deletes and not self.creates and not self.updates
+        """지울 것도 만들 것도 갱신할 것도 없다.
+
+        ``new_categories`` 는 보지 않는다. 새 이름은 생성 대상이나
+        카테고리 갱신 대상에서만 나온다.
+        """
+        return not (
+            self.deletes
+            or self.creates
+            or self.updates
+            or self.category_updates
+        )
```

`src/notebooklm_st/services/run_history_sync.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/services/run_history_sync.py b/src/notebooklm_st/services/run_history_sync.py
--- a/src/notebooklm_st/services/run_history_sync.py
+++ b/src/notebooklm_st/services/run_history_sync.py
@@ -50,7 +50,8 @@ def insert_exported(
 
     ``answers`` 행은 만들지 않는다. 저장된 실행은 원래 본문이 없다.
     문서 머리에서 읽은 메타데이터가 있으면 ``run_metadata`` 행을 함께
-    만든다.
+    만들고, 카테고리는 이름으로 잇는다. 이름은 ``history_sync.apply``
+    가 먼저 등록해 둔다.
 
     Args:
         connection: 열린 커넥션.
@@ -87,6 +88,7 @@ def insert_exported(
             " VALUES (?, ?, ?)",
             (run_id, create.metadata.channel, create.metadata.upload_date),
         )
+    _link_by_name(connection, run_id, create.categories)
     return run_id
 
 
@@ -162,3 +164,58 @@ def write_metadata(
         (metadata.channel, metadata.upload_date, run_id, outline_id),
     )
     return cursor.rowcount > 0
+
+
+def replace_categories(
+    connection: sqlite3.Connection,
+    run_id: int,
+    outline_id: str,
+    names: Sequence[str],
+) -> bool:
+    """저장된 행 하나의 카테고리를 이름들로 바꾼다.
+
+    **커밋하지 않는다.** 트랜잭션은 ``history_sync.apply`` 가 소유한다.
+    실행 ID 와 문서 ID 가 둘 다 맞는 행에만 쓴다 — ``write_metadata``
+    와 같은 이유로, 다시 쓰인 ID 의 미저장 실행을 건드리지 않는다.
+
+    Args:
+        connection: 열린 커넥션.
+        run_id: 바꿀 실행의 ID.
+        outline_id: 그 실행이 가리켜야 할 문서 ID.
+        names: 새 카테고리 이름. 등록되지 않은 이름은 빠진다.
+
+    Returns:
+        바꿨으면 ``True``. 맞는 행이 없거나 이름 집합이 이미 같으면
+        ``False``.
+    """
+    found = connection.execute(
+        "SELECT 1 FROM runs WHERE id = ? AND outline_id = ?",
+        (run_id, outline_id),
+    ).fetchone()
+    if found is None:
+        return False
+    rows = connection.execute(
+        "SELECT c.name FROM run_categories AS rc"
+        " JOIN categories AS c ON c.id = rc.category_id"
+        " WHERE rc.run_id = ?",
+        (run_id,),
+    ).fetchall()
+    if {row["name"] for row in rows} == set(names):
+        return False
+    connection.execute("DELETE FROM run_categories WHERE run_id = ?", (run_id,))
+    _link_by_name(connection, run_id, names)
+    return True
+
+
+def _link_by_name(
+    connection: sqlite3.Connection, run_id: int, names: Sequence[str]
+) -> None:
+    """실행 하나에 카테고리를 이름으로 잇는다. 커밋하지 않는다.
+
+    ``categories`` 에서 골라 넣으므로 등록되지 않은 이름은 빠진다.
+    """
+    connection.executemany(
+        "INSERT OR IGNORE INTO run_categories (run_id, category_id)"
+        " SELECT ?, id FROM categories WHERE name = ?",
+        [(run_id, name) for name in names],
+    )
```

`src/notebooklm_st/services/history_sync.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/services/history_sync.py b/src/notebooklm_st/services/history_sync.py
--- a/src/notebooklm_st/services/history_sync.py
+++ b/src/notebooklm_st/services/history_sync.py
@@ -7,11 +7,18 @@
 """
 
 import dataclasses
+import itertools
 import sqlite3
-from collections.abc import Iterator, Mapping, Sequence
+from collections.abc import Collection, Iterator, Mapping, Sequence
 
-from notebooklm_st.core import models, outline_import, sync_models, youtube
-from notebooklm_st.services import run_history_sync
+from notebooklm_st.core import (
+    category_names,
+    models,
+    outline_import,
+    sync_models,
+    youtube,
+)
+from notebooklm_st.services import categories, run_history_sync
 
 SKIP_NO_SOURCE_URL = "영상 URL 없음"
 """정리본이나 손으로 쓴 문서. 이력 문서가 아니다."""
@@ -23,19 +30,23 @@ SKIP_BAD_SOURCE_URL = "영상 URL 인식 불가"
 def plan(
     exported: Sequence[models.RunSummary],
     documents: Sequence[sync_models.ListedDocument],
+    known_categories: Collection[str] = frozenset(),
 ) -> sync_models.SyncPlan:
     """두 목록을 문서 ID 로 맞춰 동기화 계획을 세운다.
 
     문서 목록에 없는 행은 지우고, 어떤 행도 가리키지 않는
     문서는 본문에 영상 URL 이 있을 때만 만든다. 둘 다 있는 행은
     문서 머리의 채널·업로드 일자가 로컬과 다를 때만 메타데이터를
-    갱신한다. 같은 문서를 가리키는 행이 둘이어도, 같은 영상의 문서가
-    둘이어도 정리하지 않는다 — 동기화는 중복을 만들지 않을 뿐이다.
+    갱신하고, 카테고리 이름 집합이 다를 때만 카테고리를 바꾼다. 같은
+    문서를 가리키는 행이 둘이어도, 같은 영상의 문서가 둘이어도
+    정리하지 않는다 — 동기화는 중복을 만들지 않을 뿐이다.
 
     Args:
         exported: ``exported_at`` 이 있는 행들. 미저장
             실행은 여기 들어오지 않으므로 삭제될 수 없다.
         documents: 컬렉션의 문서 전부.
+        known_categories: 로컬에 등록된 카테고리 이름. 문서에 나온
+            이름 중 여기 없는 것이 새로 등록할 이름이 된다.
 
     Returns:
         입력 순서를 지킨 계획.
@@ -70,13 +81,21 @@ def plan(
                 url=url,
                 video_id=video_id,
                 metadata=outline_import.find_metadata(document.markdown),
+                categories=(
+                    outline_import.find_categories(document.markdown) or ()
+                ),
             )
         )
+    category_updates = tuple(_category_updates(exported, listed))
     return sync_models.SyncPlan(
         deletes=deletes,
         creates=tuple(creates),
         skips=tuple(skips),
         updates=tuple(_updates(exported, listed)),
+        category_updates=category_updates,
+        new_categories=_new_categories(
+            creates, category_updates, known_categories
+        ),
     )
 
 
@@ -102,6 +121,40 @@ def _updates(
             yield sync_models.SyncUpdate(run=run, metadata=merged)
 
 
+def _category_updates(
+    exported: Sequence[models.RunSummary],
+    listed: Mapping[str, sync_models.ListedDocument],
+) -> Iterator[sync_models.SyncCategoryUpdate]:
+    """문서의 카테고리 이름 집합이 로컬과 다른 행을 입력 순서로 고른다.
+
+    문서에서 카테고리를 못 읽으면 그 행은 건드리지 않는다. 메타데이터와
+    같은 이유다 — 직렬화가 바뀌어 파싱이 실패할 때 멀쩡한 로컬 값이
+    한꺼번에 비지 않게 한다.
+    """
+    for run in exported:
+        document = listed.get(run.outline_id or "")
+        if document is None:
+            continue
+        found = outline_import.find_categories(document.markdown)
+        if found is None:
+            continue
+        if set(found) != set(run.categories):
+            yield sync_models.SyncCategoryUpdate(run=run, categories=found)
+
+
+def _new_categories(
+    creates: Sequence[sync_models.SyncCreate],
+    category_updates: Sequence[sync_models.SyncCategoryUpdate],
+    known: Collection[str],
+) -> tuple[str, ...]:
+    """생성·카테고리 갱신 대상의 이름 중 로컬에 없는 것을 모은다."""
+    names = itertools.chain(
+        (name for create in creates for name in create.categories),
+        (name for change in category_updates for name in change.categories),
+    )
+    return category_names.ordered(name for name in names if name not in known)
+
+
 def _merge(
     local: models.VideoMetadata | None, found: models.VideoMetadata
 ) -> models.VideoMetadata:
@@ -129,12 +182,20 @@ class SyncResult:
     created: int
     updated: int = 0
     """메타데이터를 새로 넣거나 값을 바꾼 행 수."""
+    recategorized: int = 0
+    """카테고리를 바꾼 행 수."""
+    categories_added: int = 0
+    """새로 등록한 카테고리 수. 다른 탭이 먼저 등록했으면 계획보다
+    작다."""
 
 
 def apply(
     connection: sqlite3.Connection, sync_plan: sync_models.SyncPlan
 ) -> SyncResult:
-    """계획을 DB 에 쓴다. 삭제·삽입·갱신을 커밋 하나로 묶는다.
+    """계획을 DB 에 쓴다. 등록·삭제·삽입·갱신을 커밋 하나로 묶는다.
+
+    새 카테고리를 먼저 등록한다. 삽입과 카테고리 교체가 이름으로
+    잇기 때문이다.
 
     어느 것이든 실패하면 전부 되돌리고 다시 던진다. 커넥션은 앱
     전체가 함께 쓰므로 반쪽만 걸린 채 나가면 다른 곳의 commit 이
@@ -149,13 +210,16 @@ def apply(
         sync_plan: ``plan`` 이 세운 계획.
 
     Returns:
-        실제로 지운·만든·갱신한 개수.
+        실제로 지운·만든·갱신·등록한 개수.
 
     Raises:
-        sqlite3.Error: 삭제·삽입·갱신이 실패한 경우. 되돌린 뒤
+        sqlite3.Error: 등록·삭제·삽입·갱신이 실패한 경우. 되돌린 뒤
             던진다.
     """
     try:
+        categories_added = categories.ensure(
+            connection, sync_plan.new_categories
+        )
         deleted = run_history_sync.delete_runs(
             connection,
             [(run.id, run.outline_id or "") for run in sync_plan.deletes],
@@ -174,8 +238,23 @@ def apply(
                 update.metadata,
             ):
                 updated += 1
+        recategorized = 0
+        for change in sync_plan.category_updates:
+            if run_history_sync.replace_categories(
+                connection,
+                change.run.id,
+                change.run.outline_id or "",
+                change.categories,
+            ):
+                recategorized += 1
         connection.commit()
     except BaseException:
         connection.rollback()
         raise
-    return SyncResult(deleted=deleted, created=created, updated=updated)
+    return SyncResult(
+        deleted=deleted,
+        created=created,
+        updated=updated,
+        recategorized=recategorized,
+        categories_added=categories_added,
+    )
```

- [ ] **Step 4: 지키는 테스트를 더한다 (Review Focus 4)**

미리보기와 적용 사이에 다른 탭이 같은 이름을 먼저 등록해도 `ensure` 가 건너뛰어 적용이 실패하지 않는다. 그 동작과 결과 건수를 지킨다. 넣자마자 통과한다.

```diff
diff --git a/tests/services/test_history_sync.py b/tests/services/test_history_sync.py
--- a/tests/services/test_history_sync.py
+++ b/tests/services/test_history_sync.py
@@ -898,3 +898,25 @@ def test_a_second_plan_after_apply_has_no_category_work(connection) -> None:
     assert again.category_updates == ()
     assert again.new_categories == ()
     assert again.is_empty
+
+
+def test_apply_counts_only_the_categories_it_added(connection) -> None:
+    """적용 전에 다른 탭이 같은 이름을 등록해도 실패하지 않는다.
+
+    결과의 새 카테고리 수는 이 적용이 실제로 등록한 수다.
+    """
+    save_exported(connection, "doc-1")
+    plan = history_sync.plan(
+        run_history_sync.list_exported(connection),
+        [make_document("doc-1", CATEGORY_BODY)],
+        known_names(connection),
+    )
+    assert plan.new_categories == DOC_CATEGORIES
+    categories.add_category(connection, "경제")
+
+    result = history_sync.apply(connection, plan)
+
+    assert result.categories_added == 1
+    assert run_history_sync.list_exported(connection)[0].categories == (
+        DOC_CATEGORIES
+    )
```

- [ ] **Step 5: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `992 passed, 1 skipped`.

- [ ] **Step 6: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
✨ feat(sync): 동기화가 문서의 카테고리를 읽고 맞추기

문서 머리의 카테고리 줄을 읽어 되살리는 행에 잇고, 기존 행은 이름
집합이 다를 때만 바꾼다. 로컬에 없는 이름은 적용할 때 먼저 등록한다.
줄을 못 읽으면 손대지 않아 파싱 실패가 로컬 값을 지우지 않는다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/core/outline_import.py \
  src/notebooklm_st/core/sync_models.py \
  src/notebooklm_st/services/history_sync.py \
  src/notebooklm_st/services/run_history_sync.py \
  tests/core/test_outline_import.py \
  tests/services/test_history_sync.py \
  tests/services/test_run_history_sync.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 12: 동기화 미리보기에 카테고리 변화 보이기

**Files:**
- Modify: `src/notebooklm_st/pages/_history_sync.py`
- Test: `tests/pages/test_history.py`

**Interfaces:**
- Consumes: `history_sync.plan(…, known_categories)`·`SyncResult` (Task 11), `categories.list_categories` (Task 4).

설계서 §8.5. 개수 한 줄을 통째로 단언하는 기존 테스트(`test_sync_check_previews_the_counts_and_lists`)는 새 칸이 들어간 글자로 바뀐다. 결과 문구를 부분 문자열로 보는 나머지 테스트는 그대로 통과한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/pages/test_history.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/pages/test_history.py b/tests/pages/test_history.py
--- a/tests/pages/test_history.py
+++ b/tests/pages/test_history.py
@@ -6,6 +6,7 @@ from streamlit.testing import v1
 
 from notebooklm_st.core import models, sync_models, youtube
 from notebooklm_st.services import (
+    categories,
     history_sync,
     outline,
     run_export,
@@ -681,7 +682,7 @@ def test_sync_check_previews_the_counts_and_lists(app_db, monkeypatch) -> None:
     text = rendered_markdown(app)
     assert (
         "지울 이력 1건 · 만들 문서 1건 · 채널·업로드일 갱신 0건"
-        " · 건너뛴 문서 1건"
+        " · 카테고리 갱신 0건 · 새 카테고리 0개 · 건너뛴 문서 1건"
     ) in text
     assert "정리한 제목" in text
     assert "문서 new-1" in text
@@ -918,3 +919,79 @@ def test_sync_preview_survives_a_rerun(app_db, monkeypatch) -> None:
 
     assert not app.exception
     assert "history_sync_apply" in [e.key for e in app.button]
+
+
+SYNC_CATEGORY_BODY = (
+    "- 제목: 되살릴 문서\n"
+    "- 카테고리: 인공지능, 경제\n"
+    "- 영상 URL: https://www.youtube.com/watch?v=aaaaaaaaaaa\n"
+    "\n---\n\n## 핵심 주장\n\n세 가지다.\n"
+)
+
+
+def test_sync_explains_how_categories_are_matched(app_db, monkeypatch) -> None:
+    """설명 문구가 카테고리를 어떻게 맞추는지 알린다."""
+    set_outline_env(monkeypatch)
+
+    app = v1.AppTest.from_function(script).run()
+
+    captions = " ".join(element.value for element in app.caption)
+    assert "모르는 이름은 새로 등록합니다" in captions
+
+
+def test_sync_previews_category_changes_and_new_names(
+    app_db, monkeypatch
+) -> None:
+    """카테고리 갱신 건수와 새 이름이 보이고 적용 버튼이 나온다."""
+    set_outline_env(monkeypatch)
+    categories.add_category(app_db, "경제")
+    run_id = run_history.save_run(app_db, make_result())
+    export(app_db, run_id)
+    monkeypatch.setattr(
+        outline,
+        "list_documents",
+        fake_list([listed("doc-1", SYNC_CATEGORY_BODY)]),
+    )
+
+    app = v1.AppTest.from_function(script)
+    app.run()
+    app.button(key="history_sync_check").click().run()
+
+    assert not app.exception
+    text = rendered_markdown(app)
+    assert "카테고리 갱신 1건 · 새 카테고리 1개" in text
+    assert "**새 카테고리** 인공지능" in [
+        element.value for element in app.markdown
+    ]
+    assert "history_sync_apply" in [e.key for e in app.button]
+
+
+def test_sync_apply_links_the_categories_and_reports(
+    app_db, monkeypatch
+) -> None:
+    """적용하면 새 이름을 등록해 이력에 잇고 결과에 건수가 나온다."""
+    set_outline_env(monkeypatch)
+    categories.add_category(app_db, "경제")
+    run_id = run_history.save_run(app_db, make_result())
+    export(app_db, run_id)
+    monkeypatch.setattr(
+        outline,
+        "list_documents",
+        fake_list([listed("doc-1", SYNC_CATEGORY_BODY)]),
+    )
+
+    app = v1.AppTest.from_function(script)
+    app.run()
+    app.button(key="history_sync_check").click().run()
+    app.button(key="history_sync_apply").click().run()
+
+    assert not app.exception
+    assert "카테고리 갱신 1건 · 새 카테고리 1개" in app.success[0].value
+    assert [item.name for item in categories.list_categories(app_db)] == [
+        "경제",
+        "인공지능",
+    ]
+    assert run_history_sync.list_exported(app_db)[0].categories == (
+        "경제",
+        "인공지능",
+    )
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest tests/pages/test_history.py -q
```

기대: `4 failed` — 개수 한 줄을 바꾼 기존 테스트 하나와 새 테스트 셋.

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/pages/_history_sync.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/pages/_history_sync.py b/src/notebooklm_st/pages/_history_sync.py
--- a/src/notebooklm_st/pages/_history_sync.py
+++ b/src/notebooklm_st/pages/_history_sync.py
@@ -13,7 +13,12 @@ import sqlite3
 import streamlit as st
 
 from notebooklm_st.core import labels, sync_models
-from notebooklm_st.services import history_sync, outline, run_history_sync
+from notebooklm_st.services import (
+    categories,
+    history_sync,
+    outline,
+    run_history_sync,
+)
 
 _PLAN_KEY = "history_sync_plan"
 _RESULT_KEY = "history_sync_result"
@@ -33,6 +38,8 @@ def render(connection: sqlite3.Connection) -> None:
             "Outline 컬렉션의 문서 목록과 저장된 이력을 맞춥니다."
             " Outline 에 없는 이력은 지우고, 이력에 없는 문서는 새로"
             " 만듭니다. 채널·업로드일은 문서 머리에서 읽어 채웁니다."
+            " 카테고리는 문서 머리에서 읽어 맞추고, 모르는 이름은 새로"
+            " 등록합니다."
         )
         config = outline.config_from_env()
         if config is None:
@@ -66,7 +73,8 @@ def _check(
         st.error(str(error))
         return
     exported = run_history_sync.list_exported(connection)
-    st.session_state[_PLAN_KEY] = history_sync.plan(exported, documents)
+    known = {item.name for item in categories.list_categories(connection)}
+    st.session_state[_PLAN_KEY] = history_sync.plan(exported, documents, known)
 
 
 def _render_plan(
@@ -75,15 +83,20 @@ def _render_plan(
     """미리보기와 적용·취소 버튼을 그린다.
 
     expander 는 중첩할 수 없으므로 세 목록은 마크다운으로 그린다.
-    채널·업로드일 갱신은 개수만 그린다. 처음 채울 때는 저장된 요약본
-    전부가 대상이라 목록이 길다.
+    채널·업로드일 갱신과 카테고리 갱신은 개수만 그린다. 처음 채울
+    때는 저장된 요약본 전부가 대상이라 목록이 길다. 새로 등록할
+    카테고리는 사람이 알아야 할 변화라 이름까지 그린다.
     """
     st.markdown(
         f"지울 이력 {len(sync_plan.deletes)}건"
         f" · 만들 문서 {len(sync_plan.creates)}건"
         f" · 채널·업로드일 갱신 {len(sync_plan.updates)}건"
+        f" · 카테고리 갱신 {len(sync_plan.category_updates)}건"
+        f" · 새 카테고리 {len(sync_plan.new_categories)}개"
         f" · 건너뛴 문서 {len(sync_plan.skips)}건"
     )
+    if sync_plan.new_categories:
+        st.markdown("**새 카테고리** " + ", ".join(sync_plan.new_categories))
     if sync_plan.deletes:
         st.markdown(
             "**지울 이력**\n"
@@ -141,5 +154,7 @@ def _apply(
     st.session_state[_RESULT_KEY] = (
         f"동기화 완료 · 지움 {result.deleted}건 · 만듦 {result.created}건"
         f" · 갱신 {result.updated}건"
+        f" · 카테고리 갱신 {result.recategorized}건"
+        f" · 새 카테고리 {result.categories_added}개"
     )
     st.rerun()
```

- [ ] **Step 4: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `995 passed, 1 skipped`.

- [ ] **Step 5: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
✨ feat(sync): 동기화 미리보기에 카테고리 변화 보이기

개수 한 줄에 카테고리 갱신과 새 카테고리 수를 더하고, 새로 등록할
이름은 목록으로 보인다. 결과 문구에도 두 수를 싣는다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/pages/_history_sync.py \
  tests/pages/test_history.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 13: 정리본 머리에 재료들의 카테고리 적기

**Files:**
- Modify: `src/notebooklm_st/core/digest_markdown.py`
- Test: `tests/core/test_digest_markdown.py`

**Interfaces:**
- Consumes: `markdown_export.category_line` (Task 7), `category_names.ordered` (Task 3), `RunSummary.categories` (Task 5).

설계서 §6.3. 초안의 `sources` 는 재료 표에서 고른 요약 그대로라(`services/digest.build` 가 `tuple(runs)` 로 싣는다) 카테고리가 따라온다. 화면 쪽은 바뀌지 않는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/core/test_digest_markdown.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/core/test_digest_markdown.py b/tests/core/test_digest_markdown.py
--- a/tests/core/test_digest_markdown.py
+++ b/tests/core/test_digest_markdown.py
@@ -13,6 +13,7 @@ def make_source(
     title: str | None = "영상 제목",
     video_id: str = "dQw4w9WgXcQ",
     url: str = "https://youtu.be/dQw4w9WgXcQ?si=share",
+    categories: tuple[str, ...] = (),
 ) -> models.RunSummary:
     """저장된 요약본 하나를 만든다."""
     return models.RunSummary(
@@ -26,6 +27,7 @@ def make_source(
         outline_url=f"https://wiki.example.com/doc/summary-{run_id}",
         outline_title=outline_title,
         exported_at="2026-09-20T15:00:00",
+        categories=categories,
     )
 
 
@@ -139,3 +141,29 @@ def test_body_comes_last() -> None:
     assert "## 공통" not in head
     assert "셋 다 같은 말을 한다." in tail
     assert document.endswith("\n")
+
+
+def test_the_categories_of_the_sources_follow_the_date() -> None:
+    """재료들의 카테고리를 합쳐 중복을 빼고 이름 순으로 적는다."""
+    draft = make_draft(
+        sources=[
+            make_source(categories=("인공지능", "경제")),
+            make_source(run_id=2, categories=("경제", "정치")),
+        ]
+    )
+
+    lines = digest_markdown.to_markdown(draft).splitlines()
+
+    assert lines[:4] == [
+        "- 종류: 정리본",
+        "- 작성일자: 2026-09-23",
+        "- 카테고리: 경제, 인공지능, 정치",
+        "- 출처:",
+    ]
+
+
+def test_no_category_line_without_categories() -> None:
+    """재료에 카테고리가 하나도 없으면 줄째 뺀다."""
+    document = digest_markdown.to_markdown(make_draft())
+
+    assert "- 카테고리:" not in document
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest tests/core/test_digest_markdown.py -q
```

기대: `1 failed` — `test_the_categories_of_the_sources_follow_the_date`. `test_no_category_line_without_categories` 는 지금도 참이라 통과한다(구현 뒤 줄이 새지 않게 지킨다).

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/core/digest_markdown.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/core/digest_markdown.py b/src/notebooklm_st/core/digest_markdown.py
--- a/src/notebooklm_st/core/digest_markdown.py
+++ b/src/notebooklm_st/core/digest_markdown.py
@@ -4,7 +4,7 @@
 요약본 하나를 옮긴다면 이쪽은 정리본 하나를 옮긴다.
 """
 
-from notebooklm_st.core import markdown_export, models
+from notebooklm_st.core import category_names, markdown_export, models
 
 _NESTED_INDENT = "    "
 """하위 목록 항목 앞에 붙일 들여쓰기.
@@ -52,17 +52,25 @@ def _metadata_block(draft: models.DigestDraft) -> str:
     아래 순번 있는 하위 목록으로 적는다. 번호는 1 부터다 — CommonMark
     에서 문단 바로 뒤의 순번 목록은 1 로 시작해야 목록으로 읽힌다.
 
+    카테고리는 재료들의 것을 합쳐 중복을 빼고 이름 순으로 적는다.
+    하나도 없으면 줄째 뺀다. 정리본은 동기화가 건너뛰므로 이 줄은
+    Outline 에서 읽는 사람을 위한 표시다.
+
     Args:
         draft: 저장할 초안.
 
     Returns:
         ``- 라벨: 값`` 꼴의 마크다운 리스트.
     """
-    lines = [
-        "- 종류: 정리본",
-        f"- 작성일자: {draft.created_on}",
-        "- 출처:",
-    ]
+    lines = ["- 종류: 정리본", f"- 작성일자: {draft.created_on}"]
+    categories = markdown_export.category_line(
+        category_names.ordered(
+            name for run in draft.sources for name in run.categories
+        )
+    )
+    if categories is not None:
+        lines.append(categories)
+    lines.append("- 출처:")
     lines.extend(
         f"{_NESTED_INDENT}{number}. {_source_link(run)}"
         for number, run in enumerate(draft.sources, start=1)
```

- [ ] **Step 4: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `997 passed, 1 skipped`.

- [ ] **Step 5: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
✨ feat(digest): 정리본 머리에 재료들의 카테고리 적기

재료들의 카테고리를 합쳐 중복을 빼고 이름 순으로 작성일자 줄
다음에 적는다. 없으면 줄째 뺀다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/core/digest_markdown.py \
  tests/core/test_digest_markdown.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 14: 재료 표에 카테고리 칸과 필터 두기

**Files:**
- Create: `src/notebooklm_st/core/material_filter.py`, `tests/core/test_material_filter.py`
- Modify: `src/notebooklm_st/pages/_digest_materials.py`
- Test: `tests/pages/test_digest.py`

**Interfaces:**
- Consumes: `RunSummary.categories` (Task 5), `category_names.ordered` (Task 3).
- Produces: `material_filter.category_options(runs) -> tuple[str, ...]`, `channel_options(runs) -> tuple[str, ...]`, `filter_runs(runs, categories, channels) -> list[RunSummary]`.

설계서 §6.5·§8.6. 표의 행 번호와 `widget_key` 는 **거른 목록**의 것이다. 표 빈칸은 판다스 결측값으로 오므로 테스트는 `isna()` 로 본다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/core/test_material_filter.py` 를 새로 만든다.

```python
"""정리본 재료 거르기 테스트."""

from collections.abc import Sequence

from notebooklm_st.core import material_filter, models


def make_run(
    run_id: int, categories: tuple[str, ...] = (), channel: str | None = None
) -> models.RunSummary:
    """카테고리와 채널만 다른 저장된 요약본을 만든다."""
    metadata = None
    if channel is not None:
        metadata = models.VideoMetadata(channel=channel, upload_date=None)
    return models.RunSummary(
        id=run_id,
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        title=f"영상 {run_id}",
        created_at="2026-09-20T14:02:11",
        answer_count=0,
        metadata=metadata,
        categories=categories,
    )


RUNS = (
    make_run(1, ("경제",), "슈카월드"),
    make_run(2, ("경제", "인공지능"), "안될공학"),
    make_run(3, ("인공지능",)),
    make_run(4, (), "슈카월드"),
)
"""카테고리·채널이 섞인 재료 넷. 3 은 채널이, 4 는 카테고리가 없다."""


def ids(runs: Sequence[models.RunSummary]) -> list[int]:
    """남은 재료의 ID 를 순서대로."""
    return [run.id for run in runs]


def test_empty_filters_keep_every_run() -> None:
    """비운 필터는 거르지 않는다."""
    assert ids(material_filter.filter_runs(RUNS, [], [])) == [1, 2, 3, 4]


def test_a_category_filter_keeps_runs_with_any_chosen_name() -> None:
    """고른 카테고리 중 하나라도 붙은 재료를 남긴다."""
    kept = material_filter.filter_runs(RUNS, ["인공지능", "정치"], [])

    assert ids(kept) == [2, 3]


def test_a_channel_filter_keeps_runs_on_a_chosen_channel() -> None:
    """고른 채널 중 하나의 재료를 남긴다."""
    assert ids(material_filter.filter_runs(RUNS, [], ["슈카월드"])) == [1, 4]


def test_both_filters_must_match() -> None:
    """두 필터를 함께 주면 둘 다 맞아야 남는다."""
    kept = material_filter.filter_runs(RUNS, ["경제"], ["안될공학"])

    assert ids(kept) == [2]


def test_a_run_without_categories_drops_out_of_a_category_filter() -> None:
    """카테고리가 없는 재료는 카테고리 필터가 있으면 빠진다."""
    kept = material_filter.filter_runs(RUNS, ["경제", "인공지능"], [])

    assert ids(kept) == [1, 2, 3]


def test_a_run_without_a_channel_drops_out_of_a_channel_filter() -> None:
    """채널이 없는 재료는 채널 필터가 있으면 빠진다."""
    kept = material_filter.filter_runs(RUNS, [], ["슈카월드", "안될공학"])

    assert ids(kept) == [1, 2, 4]


def test_filtering_keeps_the_given_order() -> None:
    """남은 재료는 받은 순서를 지킨다."""
    kept = material_filter.filter_runs(list(reversed(RUNS)), ["경제"], [])

    assert ids(kept) == [2, 1]


def test_category_options_collect_the_names_in_order() -> None:
    """후보들에 붙은 카테고리를 중복 없이 이름 순으로 모은다."""
    assert material_filter.category_options(RUNS) == ("경제", "인공지능")


def test_channel_options_skip_runs_without_a_channel() -> None:
    """후보들의 채널을 중복 없이 정렬해 모으고 빈 값은 뺀다."""
    assert material_filter.channel_options(RUNS) == ("슈카월드", "안될공학")
```

`tests/pages/test_digest.py` 를 이 diff 대로 고친다.

```diff
diff --git a/tests/pages/test_digest.py b/tests/pages/test_digest.py
--- a/tests/pages/test_digest.py
+++ b/tests/pages/test_digest.py
@@ -6,8 +6,9 @@ import sqlite3
 import pytest
 from streamlit.testing import v1
 
-from notebooklm_st.core import models, youtube
+from notebooklm_st.core import material_filter, models, youtube
 from notebooklm_st.services import (
+    categories,
     nlm,
     outline,
     questions,
@@ -62,9 +63,24 @@ def save_exported(
     document_title: str = "밸류에이션 강의",
     document_id: str = "doc-1",
     metadata: models.VideoMetadata | None = None,
+    names: tuple[str, ...] = (),
 ) -> int:
-    """Outline 에 저장까지 끝난 실행 하나를 만든다."""
-    run_id = run_history.save_run(connection, make_result(), metadata)
+    """Outline 에 저장까지 끝난 실행 하나를 만든다.
+
+    ``names`` 의 카테고리는 없으면 등록해 잇는다.
+    """
+    known = {
+        item.name: item.id for item in categories.list_categories(connection)
+    }
+    ids = [
+        known[name]
+        if name in known
+        else categories.add_category(connection, name).id
+        for name in names
+    ]
+    run_id = run_history.save_run(
+        connection, make_result(), metadata, category_ids=ids
+    )
     run_links.mark_exported(
         connection,
         run_id,
@@ -237,6 +253,7 @@ def test_table_columns_come_in_order(app_db, outline_env) -> None:
 
     assert list(app.dataframe[0].value.columns) == [
         "title",
+        "categories",
         "channel",
         "upload_date",
         "created_at",
@@ -771,3 +788,134 @@ def test_discarded_draft_gets_a_fresh_title(app_db, outline_env) -> None:
 
     assert not app.exception
     assert app.text_input[0].value == "[정리] 2026-09-24"
+
+
+def channel_of(name: str) -> models.VideoMetadata:
+    """채널만 있는 메타데이터."""
+    return models.VideoMetadata(channel=name, upload_date=None)
+
+
+def three_materials(connection: sqlite3.Connection) -> None:
+    """카테고리·채널이 다른 재료 셋을 저장한다. 표에는 역순으로 선다."""
+    save_exported(
+        connection,
+        "경제 강의",
+        "doc-1",
+        channel_of("슈카월드"),
+        ("경제",),
+    )
+    save_exported(
+        connection,
+        "AI 경제",
+        "doc-2",
+        channel_of("안될공학"),
+        ("경제", "인공지능"),
+    )
+    save_exported(connection, "AI 강의", "doc-3", None, ("인공지능",))
+
+
+def test_table_shows_the_categories(app_db, outline_env) -> None:
+    """카테고리 칸에 이름이 쉼표로 이어지고, 없으면 빈칸이다."""
+    save_exported(app_db, document_id="doc-1")
+    save_exported(app_db, document_id="doc-2", names=("인공지능", "경제"))
+
+    app = v1.AppTest.from_function(script).run()
+
+    column = app.dataframe[0].value["categories"]
+    assert column.iloc[0] == "경제, 인공지능"
+    assert column.isna().tolist() == [False, True]
+
+
+def test_a_category_filter_narrows_the_table(app_db, outline_env) -> None:
+    """카테고리를 고르면 그 카테고리가 하나라도 붙은 재료만 남는다."""
+    three_materials(app_db)
+
+    app = v1.AppTest.from_function(script).run()
+    app.multiselect(key="digest_filter_categories").set_value(
+        ["인공지능"]
+    ).run()
+
+    assert not app.exception
+    assert table_titles(app) == ["AI 강의", "AI 경제"]
+
+
+def test_both_filters_must_match(app_db, outline_env) -> None:
+    """카테고리와 채널을 함께 고르면 둘 다 맞아야 남는다."""
+    three_materials(app_db)
+
+    app = v1.AppTest.from_function(script).run()
+    app.multiselect(key="digest_filter_categories").set_value(["경제"]).run()
+    app.multiselect(key="digest_filter_channels").set_value(["슈카월드"]).run()
+
+    assert table_titles(app) == ["경제 강의"]
+
+
+def test_no_match_shows_a_notice(app_db, outline_env) -> None:
+    """남는 재료가 없으면 표 대신 안내를 보인다."""
+    three_materials(app_db)
+
+    app = v1.AppTest.from_function(script).run()
+    app.multiselect(key="digest_filter_categories").set_value(
+        ["인공지능"]
+    ).run()
+    app.multiselect(key="digest_filter_channels").set_value(["슈카월드"]).run()
+
+    assert not app.exception
+    assert "고른 조건에 맞는 요약본이 없습니다." in [
+        element.value for element in app.info
+    ]
+    assert len(app.dataframe) == 0
+
+
+def test_filters_offer_only_values_in_the_materials(
+    app_db, outline_env
+) -> None:
+    """필터의 선택지는 재료에 실제로 나오는 값뿐이다."""
+    categories.add_category(app_db, "쓰지 않는 카테고리")
+    three_materials(app_db)
+
+    app = v1.AppTest.from_function(script).run()
+
+    assert app.multiselect(key="digest_filter_categories").options == [
+        "경제",
+        "인공지능",
+    ]
+    assert app.multiselect(key="digest_filter_channels").options == [
+        "슈카월드",
+        "안될공학",
+    ]
+
+
+def test_filters_are_hidden_without_values(app_db, outline_env) -> None:
+    """재료에 카테고리도 채널도 없으면 필터를 그리지 않는다."""
+    save_exported(app_db)
+
+    app = v1.AppTest.from_function(script).run()
+
+    assert len(app.multiselect) == 0
+
+
+def test_a_picked_row_points_into_the_filtered_table(
+    app_db, outline_env
+) -> None:
+    """고른 행 번호는 거른 표의 위치다."""
+    from notebooklm_st.pages import _digest_materials
+
+    three_materials(app_db)
+    add_instruction(app_db)
+    shown = material_filter.filter_runs(
+        run_history_sync.list_exported(app_db), ["인공지능"], []
+    )
+
+    app = v1.AppTest.from_function(script).run()
+    app.multiselect(key="digest_filter_categories").set_value(
+        ["인공지능"]
+    ).run()
+    app.session_state[_digest_materials.widget_key(shown)] = {
+        "selection": {"rows": [1], "columns": [], "cells": []}
+    }
+    app.run()
+
+    rendered = " ".join(element.value for element in app.markdown)
+    assert "- AI 경제" in rendered
+    assert "- AI 강의" not in rendered
```

- [ ] **Step 2: 실패를 확인한다**

```bash
/c/Users/susot/.local/bin/uv.exe run pytest tests/core/test_material_filter.py tests/pages/test_digest.py -q
```

기대: 두 파일 모두 수집 단계 오류(`ImportError: cannot import name 'material_filter'`).

- [ ] **Step 3: 구현한다**

`src/notebooklm_st/core/material_filter.py` 를 새로 만든다.

```python
"""정리본 재료를 카테고리와 채널로 거르는 순수 함수.

재료 표 위의 두 필터가 쓴다. Streamlit 도 DB 도 모른다.
"""

from collections.abc import Collection, Sequence

from notebooklm_st.core import category_names, models


def category_options(runs: Sequence[models.RunSummary]) -> tuple[str, ...]:
    """후보들에 붙은 카테고리를 중복 없이 이름 순으로 모은다.

    Args:
        runs: 재료 후보.

    Returns:
        필터에 보일 이름들. 고르면 빈 표가 되는 이름은 없다.
    """
    return category_names.ordered(
        name for run in runs for name in run.categories
    )


def channel_options(runs: Sequence[models.RunSummary]) -> tuple[str, ...]:
    """후보들의 채널을 중복 없이 정렬해 모은다. 빈 값은 뺀다.

    Args:
        runs: 재료 후보.

    Returns:
        필터에 보일 채널들.
    """
    return tuple(
        sorted(
            {
                run.metadata.channel
                for run in runs
                if run.metadata is not None and run.metadata.channel
            }
        )
    )


def filter_runs(
    runs: Sequence[models.RunSummary],
    categories: Collection[str],
    channels: Collection[str],
) -> list[models.RunSummary]:
    """두 필터에 맞는 재료만 받은 순서대로 남긴다.

    각 필터 안은 하나라도 맞으면, 두 필터 사이는 둘 다 맞아야
    남긴다. 비운 필터는 거르지 않는다. 카테고리가 없는 재료는 카테고리
    필터가 있으면 빠지고, 채널이 없는 재료는 채널 필터가 있으면
    빠진다.

    Args:
        runs: 재료 후보.
        categories: 고른 카테고리 이름.
        channels: 고른 채널.

    Returns:
        남은 재료.
    """
    return [
        run
        for run in runs
        if _has_category(run, categories) and _on_channel(run, channels)
    ]


def _has_category(run: models.RunSummary, categories: Collection[str]) -> bool:
    """카테고리 필터가 비었거나, 고른 이름 중 하나가 붙었는가."""
    return not categories or any(name in categories for name in run.categories)


def _on_channel(run: models.RunSummary, channels: Collection[str]) -> bool:
    """채널 필터가 비었거나, 고른 채널 중 하나의 재료인가."""
    if not channels:
        return True
    channel = run.metadata.channel if run.metadata is not None else None
    return channel is not None and channel in channels
```

`src/notebooklm_st/pages/_digest_materials.py` 를 이 diff 대로 고친다.

```diff
diff --git a/src/notebooklm_st/pages/_digest_materials.py b/src/notebooklm_st/pages/_digest_materials.py
--- a/src/notebooklm_st/pages/_digest_materials.py
+++ b/src/notebooklm_st/pages/_digest_materials.py
@@ -4,9 +4,10 @@
 않으므로 이름 앞에 밑줄을 둔다.
 
 저장된 요약본 전체를 표 하나로 보여 주고 행을 골라 재료로 삼는다.
-표는 선택을 **행 번호**로 돌려준다. 그래서 표의 key 를 재료 목록에서
-만들어, 목록이 바뀌면 선택이 다른 글로 밀리는 대신 비워지게 한다
-(``widget_key`` 참고).
+표 위의 카테고리·채널 필터로 후보를 좁힌다. 표는 선택을 **행
+번호**로 돌려준다. 그래서 표의 key 를 표에 오른 재료 목록에서 만들어,
+목록이 바뀌면 — 필터를 바꿔도 — 선택이 다른 글로 밀리는 대신
+비워지게 한다(``widget_key`` 참고).
 """
 
 import hashlib
@@ -14,47 +15,91 @@ from collections.abc import Sequence
 
 import streamlit as st
 
-from notebooklm_st.core import models
+from notebooklm_st.core import material_filter, models
 from notebooklm_st.services import nlm
 
 _KEY_PREFIX = "digest_materials_"
+_CATEGORY_FILTER_KEY = "digest_filter_categories"
+_CHANNEL_FILTER_KEY = "digest_filter_channels"
 
 
 def render(runs: Sequence[models.RunSummary]) -> list[models.RunSummary]:
-    """재료 표와 고른 재료 목록을 그린다.
+    """필터, 재료 표, 고른 재료 목록을 그린다.
 
     Args:
-        runs: 재료 후보. 표에 이 순서대로 나온다.
+        runs: 재료 후보. 필터를 거친 뒤 표에 이 순서대로 나온다.
 
     Returns:
         고른 실행. 사람이 누른 순서가 아니라 표의 순서를 따른다.
+        필터에 맞는 재료가 없으면 빈 목록이다.
     """
     st.markdown("**재료 선택**")
+    shown = _render_filters(runs)
     st.caption(
         f"행 왼쪽 칸을 눌러 고릅니다(최대 {nlm.DIGEST_SOURCE_LIMIT}건)."
         " 머리글을 누르면 정렬되고, 표 위 도구 막대에서 제목을"
-        " 검색합니다."
+        " 검색합니다. 필터를 바꾸면 고른 재료가 풀립니다."
     )
+    if not shown:
+        st.info("고른 조건에 맞는 요약본이 없습니다.")
+        return []
     event = st.dataframe(
-        [_row(run) for run in runs],
-        key=widget_key(runs),
+        [_row(run) for run in shown],
+        key=widget_key(shown),
         on_select="rerun",
         selection_mode="multi-row",
         hide_index=True,
         placeholder="",
         column_config={
             "title": st.column_config.TextColumn("문서 제목"),
+            "categories": st.column_config.TextColumn("카테고리"),
             "channel": st.column_config.TextColumn("채널"),
             "upload_date": st.column_config.TextColumn("업로드일"),
             "created_at": st.column_config.TextColumn("시각"),
             "url": st.column_config.LinkColumn("Outline", display_text="열기"),
         },
     )
-    selected = [runs[row] for row in sorted(event.selection.rows)]
+    selected = [shown[row] for row in sorted(event.selection.rows)]
     _render_picked(selected)
     return selected
 
 
+def _render_filters(
+    runs: Sequence[models.RunSummary],
+) -> list[models.RunSummary]:
+    """카테고리·채널 필터를 나란히 그리고 남은 재료를 돌려준다.
+
+    선택지는 재료에 실제로 나오는 값뿐이다. 선택지가 없는 필터는
+    그리지 않는다.
+
+    Args:
+        runs: 재료 후보.
+
+    Returns:
+        두 필터에 맞는 재료. 받은 순서를 지킨다.
+    """
+    category_choices = material_filter.category_options(runs)
+    channel_choices = material_filter.channel_options(runs)
+    left, right = st.columns(2)
+    chosen_categories: list[str] = []
+    chosen_channels: list[str] = []
+    if category_choices:
+        chosen_categories = left.multiselect(
+            "카테고리",
+            options=category_choices,
+            key=_CATEGORY_FILTER_KEY,
+            help="고른 카테고리 중 하나라도 붙은 요약본만 보입니다.",
+        )
+    if channel_choices:
+        chosen_channels = right.multiselect(
+            "채널",
+            options=channel_choices,
+            key=_CHANNEL_FILTER_KEY,
+            help="고른 채널의 요약본만 보입니다.",
+        )
+    return material_filter.filter_runs(runs, chosen_categories, chosen_channels)
+
+
 def widget_key(runs: Sequence[models.RunSummary]) -> str:
     """재료 표의 위젯 key 를 목록의 실행 ID 구성에서 만든다.
 
@@ -77,13 +122,15 @@ def widget_key(runs: Sequence[models.RunSummary]) -> str:
 def _row(run: models.RunSummary) -> dict[str, str | None]:
     """재료 하나를 표의 한 행으로 만든다.
 
-    열 순서가 곧 표의 열 순서다. 채널·업로드일은 고르는 기준이라
-    제목 바로 뒤에 둔다. 업로드일은 ``YYYY-MM-DD`` 문자열이라 머리글
-    정렬이 날짜 순서와 같다.
+    열 순서가 곧 표의 열 순서다. 카테고리·채널·업로드일은 고르는
+    기준이라 제목 바로 뒤에 둔다. 업로드일은 ``YYYY-MM-DD`` 문자열이라
+    머리글 정렬이 날짜 순서와 같다. 값이 없는 칸은 ``None`` 이라
+    빈칸으로 보인다.
     """
     metadata = run.metadata
     return {
         "title": _title(run),
+        "categories": ", ".join(run.categories) or None,
         "channel": metadata.channel if metadata else None,
         "upload_date": metadata.upload_date if metadata else None,
         "created_at": run.created_at,
```

- [ ] **Step 4: 지키는 테스트를 더한다 (Review Focus 3)**

필터에서 고른 값이 재료에서 사라지면(다른 탭의 삭제·동기화) Streamlit 이 그 값을 조용히 빼고 표가 다시 넓어진다. 그 동작을 지킨다. 넣자마자 통과한다.

```diff
diff --git a/tests/pages/test_digest.py b/tests/pages/test_digest.py
--- a/tests/pages/test_digest.py
+++ b/tests/pages/test_digest.py
@@ -919,3 +919,23 @@ def test_a_picked_row_points_into_the_filtered_table(
     rendered = " ".join(element.value for element in app.markdown)
     assert "- AI 경제" in rendered
     assert "- AI 강의" not in rendered
+
+
+def test_a_filter_value_that_disappears_is_dropped(app_db, outline_env) -> None:
+    """고른 필터 값이 재료에서 사라지면 깨지지 않고 그 값이 풀린다.
+
+    다른 탭이 이력을 지우거나 동기화를 적용하면 선택지가 줄어든다.
+    """
+    three_materials(app_db)
+    app = v1.AppTest.from_function(script).run()
+    app.multiselect(key="digest_filter_channels").set_value(["안될공학"]).run()
+    assert table_titles(app) == ["AI 경제"]
+    gone = run_history_sync.list_exported(app_db)[1]
+    assert gone.outline_title == "AI 경제"
+
+    run_history.delete_run(app_db, gone.id)
+    app.run()
+
+    assert not app.exception
+    assert app.multiselect(key="digest_filter_channels").value == []
+    assert table_titles(app) == ["AI 강의", "경제 강의"]
```

- [ ] **Step 5: 네 검사를 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `1014 passed, 1 skipped`.

- [ ] **Step 6: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
✨ feat(digest): 재료 표에 카테고리 칸과 필터 두기

재료 표에 카테고리 칸을 더하고, 표 위에 카테고리·채널 필터를 둔다.
필터 안은 하나라도 맞으면, 두 필터 사이는 둘 다 맞아야 남는다.
선택지는 재료에 나오는 값뿐이다. 필터를 바꾸면 고른 재료가 풀린다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add src/notebooklm_st/core/material_filter.py \
  src/notebooklm_st/pages/_digest_materials.py \
  tests/core/test_material_filter.py \
  tests/pages/test_digest.py
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 15: README 와 온보딩 문서

**Files:**
- Modify: `README.md`, `docs/ONBOARDING.md`

설계서 §12 "문서". 온보딩 문서는 모듈 표에 새 모듈과 바뀐 역할만 더한다 — 이번 변경과 무관하게 낡은 문장("화면 5개" 등)은 고치지 않는다.

- [ ] **Step 1: README 를 고친다**

사용 순서가 1~9 로 다시 매겨진다(카테고리 관리가 2번).

````diff
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -8,7 +8,7 @@ YouTube 영상 하나에 미리 등록해 둔 질문들을 던져, NotebookLM 
 
 URL 하나와 질문 목록을 넣으면 다음을 대신 처리합니다.
 
-1. 임시 노트북 생성 → 2. 영상 자막을 소스로 추가하고 인덱싱 대기 → 3. 질문마다 질의(앞 대화를 끊어 답변이 서로 물들지 않게 함) → 4. 임시 노트북 삭제 → 5. 결과를 SQLite 에 저장 → 6. 사람이 확인하고 Outline 에 올리면 로컬에는 링크와 채널·업로드일만 남음
+1. 임시 노트북 생성 → 2. 영상 자막을 소스로 추가하고 인덱싱 대기 → 3. 질문마다 질의(앞 대화를 끊어 답변이 서로 물들지 않게 함) → 4. 임시 노트북 삭제 → 5. 결과를 SQLite 에 저장 → 6. 사람이 확인하고 Outline 에 올리면 로컬에는 링크와 채널·업로드일·카테고리만 남음
 
 질의는 백그라운드 스레드에서 돌기 때문에 **페이지를 옮기거나 창을 닫아도 실행이 계속됩니다.**
 
@@ -108,13 +108,14 @@ docker compose pull && docker compose up -d
 ### 사용 순서
 
 1. **질문 관리** 화면에서 질문 템플릿을 먼저 등록합니다. (제목은 중복 불가) 이 목록은 **질의와 정리본 지시가 함께 씁니다.**
-2. **질의** 화면에서 YouTube URL 을 입력하고 질문을 선택한 뒤 실행합니다. 앞 실행이 끝나기를 기다리지 않고 다음 영상을 이어서 넣을 수 있습니다. 넣은 질의는 대기열에 서서 한 번에 하나씩 차례로 돌며, 넣고 나면 URL 칸만 비고 질문 선택은 남습니다. 같은 영상이 대기 중이거나 실행 중이면 넣지 않습니다. **자동 저장**을 켜 두면 답변을 받자마자 인용을 뺀 채 Outline 에 올라갑니다. NotebookLM 이 읽은 영상 제목이 문서 제목이 되며, 제목이 없거나 답변 일부가 실패한 실행은 올리지 않고 이력에 미저장으로 남깁니다. 이 체크는 기억되어 다음에 열어도 그대로입니다. 자동 저장한 실행의 인용은 Outline 에도 로컬에도 남지 않습니다.
-3. **채널** 화면은 **새 영상 확인 · 채널 등록 · 등록된 채널** 세 탭으로 갈립니다. 등록 탭에서 채널 URL 을 등록해 두고, 확인 탭에서 대상 채널과 기준일을 고른 뒤 **새 영상 확인**을 누르면 아직 요약하지 않은 영상만 표로 모입니다. Shorts 는 요약할 만큼 길지 않아 표에서 빠지며, 뺀 건수는 표 위에 알려 줍니다. 표에서 행을 골라 **선택한 영상 요약**을 누르면 고른 영상이 질의 대기열에 차례로 들어갑니다. 질의 화면과 같은 **자동 저장** 체크를 쓰고, 이미 대기 중이거나 실행 중인 영상은 빠집니다. (고른 기준일은 그 채널에 저장되며, 채널 피드는 Shorts 를 포함해 최신 15건까지 줍니다)
-4. **실행 현황** 화면에서 진행 상황을 한 줄에 한 건씩 봅니다. (1초마다 자동 갱신) 끝난 항목은 줄 끝의 **지우기**나 표 위의 **끝난 항목 모두 지우기**로 치웁니다. 치워도 이력은 남습니다. 자동 저장을 켠 실행은 **저장** 칸에 결과가 나옵니다. 저장됐으면 문서로 가는 링크이고, 올리지 못했으면 `미저장 · …` 로 이유가 나옵니다. 미저장 실행은 이력 화면에서 제목을 고쳐 올리면 됩니다. 대기 중인 질의는 **대기 1**·**대기 2** 처럼 차례가 보이고 **취소**로 뺄 수 있습니다. 인증 만료·요청 한도·노트북 상한으로 실패하면 대기열이 멈추고 남은 질의는 대기로 남습니다. 원인을 푼 뒤 표 위의 **재개**를 누르면 이어 갑니다. 서버를 재시작하면 대기 중인 질의는 사라집니다.
-5. **이력** 화면에서 답변을 확인하고, 제목을 정한 뒤 **Outline 에 저장**합니다. 저장하면 로컬에는 문서명·링크·채널·업로드일만 남고 수정·삭제·검색은 Outline 에서 합니다. 화면 위의 **Outline 과 동기화**는 저장된 이력과 Outline 컬렉션의 문서 목록을 맞춥니다. **확인**을 누르면 지울 이력·만들 문서·채널·업로드일 갱신·건너뛴 문서를 먼저 보여 주고, **적용**을 눌러야 바뀝니다. Outline 에 없는 이력은 링크만 지우고, 이력에 없는 문서는 본문의 영상 URL 로 이력을 되살립니다. 채널·업로드일은 문서 머리의 `채널`·`업로드 일자` 줄에서 읽어 채우며, 줄이 없는 문서는 빈칸으로 둡니다. 이 기능 전에 저장한 요약본은 동기화를 한 번 적용해야 정리본 재료 표에 채널·업로드일이 나옵니다. 영상 URL 줄이 없는 문서(정리본, 직접 쓴 글)는 건너뜁니다. Outline 휴지통이나 보관함에 있는 문서는 없는 것으로 보며, 복원하면 다음 동기화가 다시 만듭니다. 같은 영상의 문서가 둘이면 둘 다 이력이 되며 합치지 않습니다.
-6. **정리본** 화면에서 저장된 요약본 여럿을 골라 하나의 글로 정리합니다. 정리 지시는 질문 관리에 등록된 질문 중 하나를 골라 씁니다. 노트북의 소스 이름 앞에는 고른 재료 순서대로 `S1:`·`S2:` 번호가 자동으로 붙고 정리 지시 앞에 그 번호만 쓰라는 규칙이 붙으므로, 정리 지시에서 출처를 `(S1)` 처럼 적으라고 하면 저장된 문서의 출처 목록 `1.`·`2.` 와 번호가 맞습니다. 정리 지시에 소스 목록을 따로 적을 필요는 없습니다. 정리 지시는 질의가 아니라 임시 노트북의 맞춤 대화 설정에 들어가므로, NotebookLM 질의 길이 상한과 상관없이 길게 써도 됩니다(라이브러리 기준 10,000자). 제목은 NotebookLM 이 정리와 함께 지은 주제로 `[정리] <주제>` 가 기본값이며 고쳐 쓸 수 있습니다. 저장하면 Outline 에 문서가 생기며, 정리본은 로컬에 남지 않습니다.
-7. **정리** 화면에서 삭제되지 않고 남은 임시 노트북(`tmp-` 접두사)을 지웁니다.
-8. **인증** 화면에서 인증 상태를 봅니다. 만료되면 여기서 구글 로그인을 다시 합니다.
+2. **카테고리 관리** 화면에서 문서의 주제를 나타낼 카테고리를 등록합니다. (이름은 중복 불가, 30자까지, 글자·숫자·공백과 `- . & + / ( ) ·` 만) 질의할 때 카테고리를 하나 이상 골라야 하므로, **카테고리가 하나도 없으면 질의 화면과 채널 화면에서 질의를 넣을 수 없습니다.** 이력에서 쓰거나 대기 중인 질의가 쓰는 카테고리는 이름을 바꾸거나 지울 수 없습니다.
+3. **질의** 화면에서 YouTube URL 을 입력하고 질문과 카테고리를 선택한 뒤 실행합니다. 앞 실행이 끝나기를 기다리지 않고 다음 영상을 이어서 넣을 수 있습니다. 넣은 질의는 대기열에 서서 한 번에 하나씩 차례로 돌며, 넣고 나면 URL 칸만 비고 질문·카테고리 선택은 남습니다. 같은 영상이 대기 중이거나 실행 중이면 넣지 않습니다. **자동 저장**을 켜 두면 답변을 받자마자 인용을 뺀 채 Outline 에 올라갑니다. NotebookLM 이 읽은 영상 제목이 문서 제목이 되며, 제목이 없거나 답변 일부가 실패한 실행은 올리지 않고 이력에 미저장으로 남깁니다. 이 체크는 기억되어 다음에 열어도 그대로입니다. 자동 저장한 실행의 인용은 Outline 에도 로컬에도 남지 않습니다.
+4. **채널** 화면은 **새 영상 확인 · 채널 등록 · 등록된 채널** 세 탭으로 갈립니다. 등록 탭에서 채널 URL 을 등록해 두고, 확인 탭에서 대상 채널과 기준일을 고른 뒤 **새 영상 확인**을 누르면 아직 요약하지 않은 영상만 표로 모입니다. Shorts 는 요약할 만큼 길지 않아 표에서 빠지며, 뺀 건수는 표 위에 알려 줍니다. 표에서 행을 고르고 질문과 카테고리를 확인한 뒤 **선택한 영상 요약**을 누르면 고른 영상이 질의 대기열에 차례로 들어갑니다. 채널마다 **기본 카테고리**를 등록 탭과 등록된 채널 탭에서 정해 두면, 확인 탭의 카테고리 선택이 그 값으로 미리 채워집니다. 확인 탭에서 바꾼 카테고리는 채널에 저장되지 않습니다. 질의 화면과 같은 **자동 저장** 체크를 쓰고, 이미 대기 중이거나 실행 중인 영상은 빠집니다. (고른 기준일은 그 채널에 저장되며, 채널 피드는 Shorts 를 포함해 최신 15건까지 줍니다)
+5. **실행 현황** 화면에서 진행 상황을 한 줄에 한 건씩 봅니다. (1초마다 자동 갱신) 끝난 항목은 줄 끝의 **지우기**나 표 위의 **끝난 항목 모두 지우기**로 치웁니다. 치워도 이력은 남습니다. 자동 저장을 켠 실행은 **저장** 칸에 결과가 나옵니다. 저장됐으면 문서로 가는 링크이고, 올리지 못했으면 `미저장 · …` 로 이유가 나옵니다. 미저장 실행은 이력 화면에서 제목을 고쳐 올리면 됩니다. 대기 중인 질의는 **대기 1**·**대기 2** 처럼 차례가 보이고 **취소**로 뺄 수 있습니다. 인증 만료·요청 한도·노트북 상한으로 실패하면 대기열이 멈추고 남은 질의는 대기로 남습니다. 원인을 푼 뒤 표 위의 **재개**를 누르면 이어 갑니다. 서버를 재시작하면 대기 중인 질의는 사라집니다.
+6. **이력** 화면에서 답변을 확인하고, 제목을 정한 뒤 **Outline 에 저장**합니다. 저장하면 로컬에는 문서명·링크·채널·업로드일·카테고리만 남고 수정·삭제·검색은 Outline 에서 합니다. 화면 위의 **Outline 과 동기화**는 저장된 이력과 Outline 컬렉션의 문서 목록을 맞춥니다. **확인**을 누르면 지울 이력·만들 문서·채널·업로드일 갱신·카테고리 갱신·새 카테고리·건너뛴 문서를 먼저 보여 주고, **적용**을 눌러야 바뀝니다. Outline 에 없는 이력은 링크만 지우고, 이력에 없는 문서는 본문의 영상 URL 로 이력을 되살립니다. 채널·업로드일은 문서 머리의 `채널`·`업로드 일자` 줄에서 읽어 채우며, 줄이 없는 문서는 빈칸으로 둡니다. 카테고리는 문서 머리의 `카테고리` 줄에서 읽어 맞추고, 로컬에 없는 이름은 새로 등록합니다. 저장한 문서의 카테고리를 고치려면 Outline 에서 그 줄을 고친 뒤 동기화합니다. 이 기능 전에 저장한 요약본은 동기화를 한 번 적용해야 정리본 재료 표에 채널·업로드일이 나옵니다. 영상 URL 줄이 없는 문서(정리본, 직접 쓴 글)는 건너뜁니다. Outline 휴지통이나 보관함에 있는 문서는 없는 것으로 보며, 복원하면 다음 동기화가 다시 만듭니다. 같은 영상의 문서가 둘이면 둘 다 이력이 되며 합치지 않습니다.
+7. **정리본** 화면에서 저장된 요약본 여럿을 골라 하나의 글로 정리합니다. 재료 표 위의 **카테고리**·**채널** 필터로 후보를 좁힐 수 있으며, 필터를 바꾸면 고른 재료가 풀립니다. 정리 지시는 질문 관리에 등록된 질문 중 하나를 골라 씁니다. 노트북의 소스 이름 앞에는 고른 재료 순서대로 `S1:`·`S2:` 번호가 자동으로 붙고 정리 지시 앞에 그 번호만 쓰라는 규칙이 붙으므로, 정리 지시에서 출처를 `(S1)` 처럼 적으라고 하면 저장된 문서의 출처 목록 `1.`·`2.` 와 번호가 맞습니다. 정리 지시에 소스 목록을 따로 적을 필요는 없습니다. 정리 지시는 질의가 아니라 임시 노트북의 맞춤 대화 설정에 들어가므로, NotebookLM 질의 길이 상한과 상관없이 길게 써도 됩니다(라이브러리 기준 10,000자). 제목은 NotebookLM 이 정리와 함께 지은 주제로 `[정리] <주제>` 가 기본값이며 고쳐 쓸 수 있습니다. 저장하면 Outline 에 문서가 생기며, 문서 머리에는 재료들의 카테고리를 합친 줄이 들어갑니다. 정리본은 로컬에 남지 않습니다.
+8. **정리** 화면에서 삭제되지 않고 남은 임시 노트북(`tmp-` 접두사)을 지웁니다.
+9. **인증** 화면에서 인증 상태를 봅니다. 만료되면 여기서 구글 로그인을 다시 합니다.
 
 Outline 문서는 메타데이터 리스트로 시작하고 구분선 아래에 답변이
 이어집니다.
@@ -123,6 +124,7 @@ Outline 문서는 메타데이터 리스트로 시작하고 구분선 아래에
 - 제목: '매수' 의견 믿으면 안 되는 이유 | 증권사 리포트 읽는 법
 - 채널: 어피티 UPPITY
 - 업로드 일자: 2026-08-14
+- 카테고리: 경제, 투자
 - 영상 URL: https://www.youtube.com/watch?v=j2R_dgayplU
 
 ---
@@ -133,8 +135,9 @@ Outline 문서는 메타데이터 리스트로 시작하고 구분선 아래에
 ```
 
 제목과 영상 URL 은 항상 들어가고, 채널명과 업로드일자는 실행 시점에
-yt-dlp 로 가져와 저장해 둔 값이 있을 때만 들어갑니다. 값이 없으면 그
-줄 자체가 빠집니다.
+yt-dlp 로 가져와 저장해 둔 값이 있을 때만 들어갑니다. 카테고리는
+질의할 때 고른 것이 이름 순으로 들어갑니다. 값이 없으면 그 줄 자체가
+빠집니다.
 
 질문 원문은 문서에 싣지 않습니다. 이력 화면의 접은 영역에는 그대로
 남습니다.
@@ -191,7 +194,7 @@ NOTEBOOKLM_ST_OUTLINE_PUBLIC_URL=https://wiki.example.com   # 링크에 적을 
 NOTEBOOKLM_ST_DB=/path/to/my.db uv run streamlit run src/notebooklm_st/app.py
 ```
 
-> **주의**: 이 프로젝트는 DB 마이그레이션을 지원하지 않습니다(의도된 결정). 스키마가 바뀌면 앱이 연결 시점에 안내와 함께 멈추며, 해결책은 DB 파일을 지우고 새로 만드는 것뿐입니다. 이때 질문 템플릿·채널 등록·실행 이력이 함께 사라집니다. Outline 에 이미 올린 문서는 영향을 받지 않으며, 저장된 이력은 이력 화면의 **Outline 과 동기화**로 되살릴 수 있습니다. 미저장 실행·질문 템플릿·채널 등록은 되살릴 수 없습니다.
+> **주의**: 이 프로젝트는 DB 마이그레이션을 지원하지 않습니다(의도된 결정). 스키마가 바뀌면 앱이 연결 시점에 안내와 함께 멈추며, 해결책은 DB 파일을 지우고 새로 만드는 것뿐입니다. 이때 질문 템플릿·채널 등록·실행 이력이 함께 사라집니다. Outline 에 이미 올린 문서는 영향을 받지 않으며, 저장된 이력은 이력 화면의 **Outline 과 동기화**로 되살릴 수 있습니다. 카테고리도 동기화가 문서 머리에서 읽어 다시 등록합니다. 미저장 실행·질문 템플릿·채널 등록과 채널의 기본 카테고리는 되살릴 수 없습니다.
 
 ### 실계정 스모크 체크
````

- [ ] **Step 2: 온보딩 문서를 고친다**

```diff
diff --git a/docs/ONBOARDING.md b/docs/ONBOARDING.md
--- a/docs/ONBOARDING.md
+++ b/docs/ONBOARDING.md
@@ -137,8 +137,9 @@ Streamlit 은 **상호작용마다 스크립트를 처음부터 다시 실행한
 
 | 파일 | 복잡도 | 역할 |
 |---|---|---|
-| `pages/ask.py` | moderate | 질의 화면. URL 입력·질문 선택 후 대기열에 넣고 반환. 실행 중이어도 넣고, 같은 영상이 대기·실행 중이면 막는다. 넣기는 버튼 콜백이 한다 |
-| `pages/channels.py`·`_channel_check.py`·`_channel_videos.py`·`_channel_enqueue.py` | moderate | 채널 화면. 등록·목록 탭과 "새 영상 확인" 탭. 확인한 신규에서 Shorts 를 빼고(피드 링크로 가린다) 표로 보이고, 행을 골라 버튼 하나로 질의 대기열에 넣는다. 대기·실행 중인 영상은 뺀다. 넣기는 버튼 콜백이 한다 |
+| `pages/ask.py` | moderate | 질의 화면. URL 입력·질문·카테고리 선택 후 대기열에 넣고 반환. 카테고리가 하나도 없으면 안내만 하고 넣지 못한다. 실행 중이어도 넣고, 같은 영상이 대기·실행 중이면 막는다. 넣기는 버튼 콜백이 한다 |
+| `pages/channels.py`·`_channel_check.py`·`_channel_videos.py`·`_channel_enqueue.py` | moderate | 채널 화면. 등록·목록 탭과 "새 영상 확인" 탭. 등록·목록 탭에서 채널의 기본 카테고리를 정한다. 확인한 신규에서 Shorts 를 빼고(피드 링크로 가린다) 표로 보이고, 행을 골라 버튼 하나로 질의 대기열에 넣는다. 카테고리 선택은 그 채널의 기본값으로 미리 채운다. 대기·실행 중인 영상은 뺀다. 넣기는 버튼 콜백이 한다 |
+| `pages/category_admin.py` | moderate | 카테고리 CRUD. 이력이나 대기 중인 질의가 쓰는 카테고리는 이름 칸과 버튼을 잠그고 이유를 적는다 |
 | `pages/dashboard.py` | simple | 실행 현황. 레지스트리를 1초 fragment 로 폴링해 한 줄 표로 그린다. 지우기·취소·재개는 버튼 콜백이 한다. 대기열이 멈추면 이유와 재개 버튼을 보인다 |
 | `pages/question_admin.py` | moderate | 질문 템플릿 CRUD. 검증 오류는 `st.error`, 성공 시 `st.rerun` |
 | `pages/history.py` | **complex** | 이력 조회·답변 수정·삭제·마크다운 내려받기. 인용 숨기기와 2단계 삭제 확인을 세션 키로 직접 관리 |
@@ -147,6 +148,7 @@ Streamlit 은 **상호작용마다 스크립트를 처음부터 다시 실행한
 | `components/run_progress.py` | simple | 실행 표의 머리글과 한 줄(queued/running/failed/done). 대기 줄은 차례 배지와 취소 버튼. 칸 글자는 순수 함수가 만든다. 완료 시 답변 수만, 상세는 이력 화면으로 |
 | `components/auto_save_toggle.py` | simple | 자동 저장 체크. 질의·채널 화면이 위젯 key 만 달리해 DB 설정 하나를 함께 쓴다 |
 | `components/queue_notice.py` | simple | 넣으면 언제 도는지 알리는 안내 셋과 넣은 뒤의 결과 문구. 질의·채널 화면이 함께 쓴다 |
+| `components/category_picker.py` | simple | 카테고리 선택. 값은 ID, 이름은 `format_func`. 질의·채널 화면이 함께 쓰고, 카테고리가 없을 때의 안내 문구도 여기 있다 |
 | `components/auth_gate.py` | simple | 자동 복구 실패 동안에만 재인증 안내 상자를 남긴다(브라우저 로그인 경로는 삭제됨 — `docs/how-to/2026-09-16-auth-reseed.md`) |
 | `components/schema_gate.py` | simple | 기동 직후 커넥션을 열어 보고 스키마 불일치면 안내 후 `st.stop()` |
 
@@ -158,11 +160,13 @@ Streamlit 은 **상호작용마다 스크립트를 처음부터 다시 실행한
 | `services/auth.py` | **complex** | 쿠키 확인 → 무인 복구 → 최후 수단으로 `sys.executable -m notebooklm login` 자식 프로세스. `AuthGate` 가 앱 수명 동안 한 번만 타게 통제 |
 | `services/run_history.py` | **complex** | `runs`·`answers` CRUD. 저장·목록·상세·답변 수정·삭제 |
 | `services/runner.py` | moderate | 대기열 워커. 넣은 순서대로 한 번에 하나씩 파이프라인을 돌린다. 모든 실패 경로에서 레지스트리를 실패로 마감하고, 다음 실행도 실패할 오류면 대기열을 멈춘다 |
+| `services/run_steps.py` | simple | 워커가 실행 하나에서 거치는 두 단계 — 영상 정보 받기, 결과와 고른 카테고리를 이력에 남기기 |
 | `services/runs.py` | simple | `RunHandle`·`SaveOutcome` 값 객체와 상태 묶음(`FINISHED`·`PENDING`) |
 | `services/run_store.py` | moderate | 스레드 안전 핸들 보관소. 넣기·조회·진행 기록·치우기 |
 | `services/run_registry.py` | moderate | 보관소에 대기열 규칙(워커 자리·차례·멈춤·재개·취소)과 가드 판정(`active_count`·`is_pending`)을 더한다 |
 | `services/store.py` | moderate | 커넥션과 전체 스키마 소유. 마이그레이션 없이 즉시 실패 |
 | `services/questions.py` | moderate | 질문 템플릿 CRUD. 제목 중복·빈 값을 `ValueError` 로 강제 |
+| `services/categories.py` | moderate | 카테고리 CRUD. 이름 규칙·중복과, 이력에서 쓰는 카테고리의 이름 변경·삭제를 `ValueError` 로 막는다. 동기화가 쓰는 `ensure` 는 커밋하지 않는다 |
 
 ### 코어 도메인 — 순수, I/O 없음
 
@@ -173,6 +177,9 @@ Streamlit 은 **상호작용마다 스크립트를 처음부터 다시 실행한
 | `core/answer_text.py` | moderate | 인용 번호와 후속 제안 블록 제거. 표시 직전에만 호출, 원문 불변 |
 | `core/markdown_export.py` | moderate | 이력 1건 → 마크다운 문서 + 파일명 |
 | `core/youtube.py` | simple | `youtu.be` · `watch?v=` · `/shorts/` 세 형태에서 11자 영상 id 추출 |
+| `core/category_names.py` | simple | 카테고리 이름 규칙(허용 글자·30자)과 이름 순서, 문서 머리 줄 나누기. 관리 화면과 동기화가 같은 규칙을 쓴다 |
+| `core/material_filter.py` | simple | 정리본 재료를 카테고리·채널로 거르는 순수 함수와 필터 선택지 |
+| `core/sync_models.py` | simple | 이력 동기화의 값 객체(문서 목록·계획·생성·갱신·카테고리 갱신) |
 
 ### 데이터 — SQLite 3테이블
```

- [ ] **Step 3: 확인한다**

```bash
grep -n "^[0-9]\. \*\*" README.md
```

기대: `1. **질문 관리**` 부터 `9. **인증**` 까지 아홉 줄, 2 가 `**카테고리 관리**`.

- [ ] **Step 4: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
📝 docs(categories): 사용법과 모듈 표에 카테고리 적기

README 사용 순서에 카테고리 관리를 질의 앞에 넣고, 질의·채널·
동기화·정리본 항목과 문서 모양 예시에 카테고리를 적는다. 온보딩
문서의 모듈 표에 새 모듈과 바뀐 역할을 더한다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add README.md \
  docs/ONBOARDING.md
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 16: 기존 설계서 넷에 카테고리를 반영해 다시 쓰기

**Files:**
- Modify: `docs/superpowers/specs/2026-09-22-outline-storage-design.md`, `docs/superpowers/specs/2026-09-28-history-sync-design.md`, `docs/superpowers/specs/2026-09-23-digest-design.md`, `docs/superpowers/specs/2026-09-30-saved-run-metadata-design.md`

설계서 §12 "문서". 네 문서는 이번 기능으로 **사실이 아니게 된 문장**만 바로잡는다. 이 기능과 무관하게 이미 낡은 문장(예: outline-storage 의 "엔드포인트는 `documents.create` 하나뿐", 상태 줄 "설계 (구현 계획 수립 전)", saved-run-metadata 의 "수정 — 소스 9" 개수)은 고치지 않는다 — 범위 밖이다.

규칙(Global Constraints 와 같다):
- 문서마다 **끝까지 읽고 전체를 다시 쓴다.** 아래 표의 자리만 바꾸고 나머지 글은 그대로 옮긴다.
- 경위("원래는·이번에 바뀌었다")를 본문에 적지 않는다. 최종 상태만 담고, 자세한 근거는 `2026-10-03-categories-design.md` 를 가리킨다.
- 줄 번호는 이 계획을 쓸 때(`develop` 의 `1df1eb2`)의 것이다. 앞 Task 들은 이 넷을 건드리지 않으므로 그대로다.
- 상태 줄은 바꾸지 않는다.

- [ ] **Step 1: `2026-09-22-outline-storage-design.md`**

| 자리(지금 줄) | 지금 | 바뀐 뒤 담을 사실 |
|---|---|---|
| L34 | "앱에는 문서명·링크와 영상 메타데이터(채널·업로드일)만 남는다." | 문서명·링크·영상 메타데이터와 **카테고리**가 남는다 |
| L132 결정 표 | 저장에 성공하면 답변을 지우고 링크와 영상 메타데이터를 남긴다 | 카테고리 연결(`run_categories`)도 같은 캐시로 남고, 이력 동기화가 문서 머리에서 다시 맞춘다(`2026-10-03-categories-design.md`) |
| L177 흐름도 | `요약 실행 끝 → SQLite 에 answers + run_metadata` | `… + run_metadata + run_categories` |
| L362~377 `RunSummary` 블록 | 네 칸을 더한 클래스를 전체처럼 보인다 | 블록을 지금 `core/models.py` 의 `RunSummary` 그대로로 — `metadata`·`categories` 칸까지 |
| L432~433 | `run_metadata` 는 지우지 않고 남긴다 | `run_categories` 도 지우지 않는다. 같은 이유다 |
| L475~490 문서의 모양 | 제목·채널·업로드 일자·영상 URL 넷 | 업로드 일자 다음에 `- 카테고리: 경제, 투자` 를 넣고, 카테고리가 없으면 줄째 빠진다고 적는다 |
| L496~497 | 라벨은 `제목`·`채널`·`업로드 일자`·`영상 URL` | `제목`·`채널`·`업로드 일자`·`카테고리`·`영상 URL` |
| L758 범위 밖 | "**채널별 폴더 분류 · 태그** — 고정 컬렉션 하나에 평평하게 둔다" | "**폴더·컬렉션으로 나누기** — 고정 컬렉션 하나에 평평하게 둔다. 주제는 문서 머리의 `- 카테고리:` 줄로 표시한다(`2026-10-03-categories-design.md`)" |
| L772 R5 표 | 메타데이터 형식에 카테고리 줄이 없다 | `- 제목:`·`- 채널:`·`- 업로드 일자:`·`- 카테고리:`·`- 영상 URL:` |

- [ ] **Step 2: `2026-09-28-history-sync-design.md`**

| 자리(지금 줄) | 지금 | 바뀐 뒤 담을 사실 |
|---|---|---|
| L8 대상, L665 건드리는 파일 | `core/models.py` — 값 객체 다섯 | 동기화 값 객체는 `core/sync_models.py` 에 있다 |
| L23~24 | `run_metadata` 에 채널·업로드일이 캐시로 남는다 | `run_categories` 에 카테고리도 캐시로 남는다 |
| L148 결정 표 "기존 행" | 메타데이터만 문서 값으로 갱신한다 | 메타데이터와 카테고리만 맞춘다. 카테고리는 이름 집합이 다를 때만 바꾸고, 로컬에 없는 이름은 먼저 등록한다 |
| L157 결정 표 "스키마" | 바꾸지 않는다 | 이 설계는 바꾸지 않는다. 카테고리 테이블은 카테고리 설계가 더하고 동기화가 쓴다 |
| L168~173 구조도 | `plan(exported, docs)`, `apply` 는 삭제 + 삽입 + 갱신 | `plan(exported, docs, 알려진 카테고리 이름)`; `apply` 는 새 카테고리 등록 + 삭제 + 삽입 + 메타데이터 갱신 + 카테고리 교체, 커밋 하나; 아래 호출에 `categories.ensure`·`run_history_sync.replace_categories`; `outline_import` 는 영상 URL·채널·업로드일·카테고리를 읽는다 |
| L180~184 | `plan` 은 두 목록을 받는다; 저장소 함수 넷 | `plan` 은 알려진 카테고리 이름도 받는다; `apply` 는 `services/categories.ensure` 로도 쓴다; 저장소 함수 다섯(`replace_categories`) |
| L206·L208 화면 흐름 | `plan(list_exported(conn), documents)`; 미리보기 개수 한 줄 + 세 목록 | `_check` 가 `categories.list_categories` 의 이름을 넘긴다; 개수 한 줄 + 새 카테고리 줄 + 세 목록 |
| L219 | `plan(exported, documents)` | `plan(exported, documents, known_categories)` |
| L227~228 비교 규칙 표 | 카테고리 규칙이 없다 | 행을 더한다: 행과 문서가 모두 있고 문서의 카테고리 이름 집합이 로컬과 다르면 **카테고리 갱신 대상**(연결만 바꾼다); 카테고리 줄이 없거나 읽을 이름이 없으면 카테고리는 손대지 않는다 |
| L241~243·L254~256 | 메타데이터를 행마다 판정, 같은 쌍으로 맞춤 | 카테고리도 행마다 판정하고 `(실행 ID, 문서 ID)` 쌍으로 맞춘다. 다른 탭이 같은 이름을 먼저 등록하면 `categories_added` 가 계획의 `new_categories` 수보다 작다 — 오류가 아니다 |
| L271~272 | 되살린 행에 `run_metadata` 를 만든다 | 문서의 카테고리를 이름으로 잇는다 |
| L283 | `core/models.py` 에 값 객체 다섯을 더한다 | `core/sync_models.py` 에 값 객체를 둔다. 카테고리 설계가 `SyncCategoryUpdate` 를 더해 여섯이다 |
| L300~309 `SyncCreate` 블록 | `metadata` 로 끝난다 | `categories: tuple[str, ...] = ()` 를 더한다 |
| L327~329 사이 | — | `SyncCategoryUpdate(run, categories)` 블록을 `SyncPlan` 위에 더한다 |
| L329~344 `SyncPlan` 블록 | `updates` 까지, `is_empty` 는 셋을 본다 | `category_updates`·`new_categories` 를 더하고, `is_empty` 는 `category_updates` 까지 본다 |
| L347~349 | `VideoMetadata` 를 `RunSummary`·`SyncCreate` 위에 | `VideoMetadata` 는 `core/models.py` 에서 `RunSummary` 위에 둔다. 동기화 값 객체는 `sync_models` 가 `models` 를 import 해 쓴다 |
| L373·L430~446·L480~495 서명 | `models.ListedDocument`·`models.SyncCreate`·`models.SyncPlan`; `SyncResult(deleted, created, updated)`; `plan` 인자 둘 | `sync_models.*`; `replace_categories(connection, run_id, outline_id, names) -> bool` 을 더한다; `SyncResult` 에 `recategorized`·`categories_added`; `plan` 에 `known_categories: Collection[str] = frozenset()` |
| L448~449 | `SUMMARY_SELECT` 는 `run_metadata` 를 LEFT JOIN | 카테고리 이름을 모으는 상관 서브쿼리 칸(`category_names`)도 있다 |
| L454~457 | `insert_exported` 는 `run_metadata` 까지 | 카테고리도 이름으로 잇는다 |
| L498~506 | 생성 대상에 메타데이터를 싣고, 삭제 → 삽입 → 갱신 | 생성 대상에 `find_categories` 결과도 싣고, `category_updates`·`new_categories` 를 세운다. 적용 순서는 새 카테고리 등록 → 삭제 → 삽입 → 메타데이터 갱신 → 카테고리 교체 |
| L509~513 | `SyncResult` 는 셋을 센다 | 다섯을 센다(`recategorized`·`categories_added` 포함) |
| L523~526·L549~550 | `find_source_url`·`find_metadata`; 라벨 상수 둘 | `find_categories(markdown) -> tuple[str, ...] \| None` 도 있다; `CATEGORY_LABEL` 도 함께 쓰는 상수다 |
| L566~576 화면 그림 | 설명 문구와 개수 한 줄에 카테고리가 없다 | 설명에 "카테고리는 문서 머리에서 읽어 맞추고, 모르는 이름은 새로 등록합니다." · 개수 줄에 `카테고리 갱신 K건 · 새 카테고리 C개`(건너뛴 문서 앞) · `**새 카테고리** …` 줄 |
| L587~595 | 개수 줄 순서, "갱신만 있어도", 결과 문구 "… · 갱신 K건", 세 목록 | 카테고리 갱신·새 카테고리도 건너뛴 문서 앞에 두고 새 이름은 줄로 보인다; 카테고리 갱신만 있어도 적용 버튼이 나온다; 결과 문구는 `… · 갱신 K건 · 카테고리 갱신 R건 · 새 카테고리 C개` |
| L631 테스트 표 | 빈 계획은 0·0·0 | `SyncResult` 는 다섯 칸이다 |

- [ ] **Step 3: `2026-09-23-digest-design.md`**

| 자리(지금 줄) | 지금 | 바뀐 뒤 담을 사실 |
|---|---|---|
| L40~42 | 저장된 요약본 전체를 한 표에 펼친다 | 표 위의 카테고리·채널 필터를 통과한 요약본을 한 표에 펼친다 |
| L170·L171 결정 표 | 목록 전체를 본다; key 는 재료 ID 목록에서 | 필터로 후보를 좁힌다; key 는 **거른** 목록에서 만들어 필터를 바꾸면 고른 재료가 풀린다 |
| L216 구조도 | `pages/_digest_materials.py 재료 표 · 고른 재료 목록` | 필터 · 재료 표 · 고른 재료 목록, 거르기는 `core/material_filter.py` |
| L502~504 | `sources` 는 출처 링크를 만들 요약들 | 카테고리 줄의 재료도 된다 |
| L563 화면 그림 | `표 · 저장된 실행 전부 · 행 체크 · 고른 재료 N/10` | 카테고리·채널 필터 · 거른 표 · 행 체크 · 고른 재료 N/10, 맞는 것이 없으면 "고른 조건에 맞는 요약본이 없습니다." |
| L608~611 | "열은 다섯이다." | 열은 여섯이다 — 문서 제목 · **카테고리**(`", ".join(run.categories)`) · 채널 · 업로드일 · 시각 · Outline |
| L617~618 | 표 위 안내 한 줄 | 안내 끝에 "필터를 바꾸면 고른 재료가 풀립니다." 가 붙고, 그 위에 필터 둘이 있다 |
| L624~629 | 목록이 바뀌면 key 가 달라진다, 메타데이터가 바뀌어도 고른 재료가 남는다 | `widget_key` 는 거른 목록을 받는다. 필터를 켠 채 동기화가 채널·카테고리를 바꾸면 행과 key 가 바뀔 수 있다 |
| L666~672 문서의 모양 | 종류·작성일자·출처 | 작성일자 다음에 `- 카테고리: <재료들의 합집합, 중복 없이 이름 순>`, 없으면 줄째 빠진다 |
| L704~706 | `one_line`·`source_url` 을 함께 쓴다 | `markdown_export.category_line` 과 `category_names.ordered` 도 쓴다 |
| L745 테스트 표 | 메타데이터가 종류·작성일자·출처 순 | 종류·작성일자·카테고리·출처 순, 합집합·중복 제거·없을 때 줄 빠짐 |
| L822~824 | 날짜·채널로 거르는 자리가 필요해진다 | 채널·카테고리 필터는 있다. 날짜로 거르는 자리만 없다 |
| L840 범위 밖 | "**재료 거르기(날짜·채널)** — 표의 정렬·검색으로 버틴다" | "**재료를 날짜로 거르기** — 표의 정렬로 버틴다" |

- [ ] **Step 4: `2026-09-30-saved-run-metadata-design.md`**

| 자리(지금 줄) | 지금 | 바뀐 뒤 담을 사실 |
|---|---|---|
| L71~79 머리 블록 | 제목·채널·업로드 일자·영상 URL | 업로드 일자 다음에 `- 카테고리: …`(없으면 빠짐) |
| L123~125 | 메타데이터가 바뀌어도 고른 재료가 비워지지 않는다 | 필터를 켜지 않았을 때 그렇다. key 는 거른 목록에서 만든다 |
| L145·L432~433 | 열 `문서 제목 · 채널 · 업로드일 · 시각 · Outline` | `문서 제목 · 카테고리 · 채널 · 업로드일 · 시각 · Outline` |
| L173~189 구조도 | 카테고리가 없다 | 실행 끝에 `run_categories` 도 쓰고, 문서 머리에 카테고리 줄, `mark_exported` 는 `run_categories` 도 남기고, `plan(…, 알려진 카테고리)` 에 `category_updates`·`new_categories`, `apply` 에 등록·교체, `list_exported → RunSummary.metadata·categories`, 재료 표에 필터와 카테고리 칸 |
| L245·L259~276 | `SyncCreate`·`SyncUpdate`·`SyncPlan` 을 `core/models.py` 에 | `core/sync_models.py` 에 있다. `is_empty` 는 `category_updates` 까지 본다 |
| L256~257 | 독스트링 "로컬에는 링크와 영상 메타데이터가 남아 있다" | "로컬에는 링크와 영상 메타데이터, 카테고리만 남아 있다" |
| L286~294 SQL | 카테고리 칸이 없다 | `(SELECT group_concat(c.name, ',') FROM run_categories AS rc JOIN categories AS c ON c.id = rc.category_id WHERE rc.run_id = r.id) AS category_names` 칸을 더한다 |
| L300~301·L313~315 | `row_to_summary`·`insert_exported` 는 메타데이터까지 | `row_to_summary` 는 카테고리를 파이썬에서 이름 순으로 싣고, `insert_exported` 는 카테고리를 이름으로 잇는다 |
| L358~362 | 두 칸 모두 못 읽으면 손대지 않음 | 메타데이터의 판정이다. 카테고리는 따로 판정한다 |
| L390~391 | 삭제 → 삽입 → 갱신 | 새 카테고리 등록 → 삭제 → 삽입 → 메타데이터 갱신 → 카테고리 교체 |
| L410~428 화면 그림·문구 | 카테고리 문장·칸·줄이 없다; "셋 다 없으면"; 결과 `… · 갱신 K건` | 설명 문장, `카테고리 갱신 K건 · 새 카테고리 C개`, `**새 카테고리**` 줄; "넷 다 없으면"; 결과 `… · 갱신 K건 · 카테고리 갱신 R건 · 새 카테고리 C개` |
| L436·L437 | `widget_key` 는 바꾸지 않는다; 표 위 안내 문구는 그대로다 | 함수는 그대로지만 거른 목록을 받는다; 안내 끝에 필터 문장이 붙고 위에 필터 둘이 있다 |
| L441~443 | 도움말 "…링크와 채널·업로드일만 남습니다." | "…링크와 채널·업로드일·카테고리만 남습니다." |
| L500~502 | Sync 값 객체를 `core/models.py` 에서 고친다 | `core/sync_models.py` 에 있다 |
| L519~522 README 고침 | "링크와 채널·업로드일만 남음" 류 | "링크와 채널·업로드일·카테고리만 남음" 류 |
| L576 범위 밖 | "재료 표를 채널·날짜로 거르기" | "재료 표를 날짜로 거르기" |

- [ ] **Step 5: 확인한다**

```bash
F=docs/superpowers/specs
grep -c -e "- 카테고리:" $F/2026-09-22-outline-storage-design.md   # 1 이상
grep -c "채널별 폴더 분류 · 태그" $F/2026-09-22-outline-storage-design.md   # 0
grep -c "값 객체 다섯" $F/2026-09-28-history-sync-design.md   # 0
grep -c "replace_categories" $F/2026-09-28-history-sync-design.md   # 1 이상
grep -c "열은 다섯이다\|재료 거르기(날짜·채널)" $F/2026-09-23-digest-design.md   # 0
grep -c "material_filter" $F/2026-09-23-digest-design.md   # 1 이상
grep -c "문서 제목 · 채널 · 업로드일 · 시각 · Outline\|재료 표를 채널·날짜로 거르기" $F/2026-09-30-saved-run-metadata-design.md   # 0
grep -c "링크와 채널·업로드일만" $F/2026-09-30-saved-run-metadata-design.md   # 0
```

기대: 주석에 적은 대로. 0 이어야 할 줄이 남았으면 그 문장을 최종 상태로 고친다. 다른 문서 자리에 같은 글자가 정당하게 남아야 하는 경우라 단언이 맞지 않으면, 고치지 말고 그 자리와 이유를 보고한다.

- [ ] **Step 6: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
📝 docs(specs): 기존 설계서 넷에 카테고리를 반영해 다시 쓰기

카테고리로 사실이 아니게 된 문장 — 문서 머리 형식, 동기화의 계획과
결과, 재료 표의 칸과 필터, 정리본 머리, 값 객체의 위치 — 을 최종
상태로 바로잡는다. 대상은 outline-storage·history-sync·digest·
saved-run-metadata 설계서다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add docs/superpowers/specs/2026-09-22-outline-storage-design.md \
  docs/superpowers/specs/2026-09-28-history-sync-design.md \
  docs/superpowers/specs/2026-09-23-digest-design.md \
  docs/superpowers/specs/2026-09-30-saved-run-metadata-design.md
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```

---

### Task 17: 전체 검증, 브라우저 확인, 설계서 상태

**Files:**
- Modify: `docs/superpowers/specs/2026-10-03-categories-design.md`(상태 줄)

- [ ] **Step 1: 네 검사를 다시 돌린다**

네 검사를 차례로 돌린다.

```bash
/c/Users/susot/.local/bin/uv.exe run ruff format .
/c/Users/susot/.local/bin/uv.exe run ruff check --fix .
/c/Users/susot/.local/bin/uv.exe run mypy src tests
/c/Users/susot/.local/bin/uv.exe run pytest -q
```

기대: 포매터·린트·mypy 통과, `1014 passed, 1 skipped`.

- [ ] **Step 2: 브라우저로 확인한다**

빈 임시 DB 로 띄운다. 저장소의 DB 를 건드리지 않는다.

```bash
NOTEBOOKLM_ST_DB=.temp/categories-check.db /c/Users/susot/.local/bin/uv.exe run streamlit run src/notebooklm_st/app.py
```

차례로 본다.

1. **질의** 화면 — 질문을 하나 등록한 뒤 들어가면, 질문 선택 아래에 카테고리 안내(`카테고리 관리 화면에서 …`)만 있고 실행 버튼이 없다.
2. **카테고리 관리** — `경제`·`인공지능` 을 등록한다. `경제,정치` 는 쓸 수 있는 글자 안내로 거부된다. 목록이 이름 순이다.
3. **질의** 화면 — 카테고리 선택이 생기고, 고르기 전에는 실행 버튼이 잠긴다.
4. **채널** 화면 — 실제 채널 하나를 등록하며 기본 카테고리로 `경제` 를 고른다. 등록된 채널 탭에서 기본 카테고리를 `인공지능` 으로 바꾸고 곧바로 `경제` 를 더해 둘이 남는지 본다(연달아 바꾸기). 새 영상 확인 탭에서 확인을 누르면 카테고리 선택이 그 둘로 미리 채워져 있다.
5. Outline 과 NotebookLM 인증이 있는 기기라면 — 자동 저장을 켜고 영상 하나를 넣어, 만들어진 문서 머리에 `- 카테고리: 경제, 인공지능` 줄이 업로드 일자 다음에 있는지 본다. Outline 에서 그 줄의 `인공지능` 을 `AI` 로 고친 뒤 이력 화면의 동기화를 확인하면 `카테고리 갱신 1건 · 새 카테고리 1개` 와 `**새 카테고리** AI` 가 보이고, 적용하면 결과 문구에 같은 수가 나온다. 정리본 화면에서 카테고리·채널 필터로 표가 줄고, 필터를 바꾸면 고른 재료가 풀리는지 본다.
6. **카테고리 관리** — 5 를 했다면 `경제` 의 이름 칸과 버튼이 잠기고 `이력 1건` 이 보인다.

브라우저를 닫고 서버를 멈춘 뒤 임시 DB 를 지운다.

```bash
rm .temp/categories-check.db
```

5 를 할 수 없는 기기면 그 사실을 보고에 적는다. 1~4·6 은 Outline·NotebookLM 없이 된다(6 은 5 를 했을 때만).

- [ ] **Step 3: 설계서를 구현 완료로 표시한다**

`docs/superpowers/specs/2026-10-03-categories-design.md` 의 상태 줄 `- **상태**: 설계 검토 중` 을 `- **상태**: 구현 완료 (<오늘 날짜 YYYY-MM-DD>)` 로 바꾼다.

- [ ] **Step 4: 커밋**

커밋한다. Git Bash 에서 메시지 파일로 넣는다.

```bash
msg=$(mktemp)
cat > "$msg" <<'EOF'
📝 docs(categories): 카테고리 설계서를 구현 완료로 표시

계획의 Task 1~16 을 적용하고 네 검사와 브라우저 확인을 마쳤다.

Assisted-by: <커밋하는 에이전트 자신의 모델 ID>
EOF
git add docs/superpowers/specs/2026-10-03-categories-design.md
git commit -F "$msg"
rm "$msg"
git log -1 --format=%B | grep -c "^@$"   # 0 이어야 한다
```
