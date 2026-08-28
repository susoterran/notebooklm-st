# 브랜치 전략 (rule)

이 규칙은 세션마다 자동 로드되어 **메인 에이전트와 커스텀 서브에이전트 모두**에 적용된다.

## 브랜치 구조

- `master` — 통합·배포 브랜치. 항상 배포 가능한 상태를 유지한다.
- `develop` — 작업 브랜치. 모든 변경은 여기서 커밋한다.
- `master`에 **직접 커밋하지 않는다.** 통합은 PR을 거친다.

## 작업 흐름

- 작업 전 최신화: `git fetch $(git remote)` 후 필요 시 `git pull`(빠른 전진).
- fast-forward 불가 시: `git pull --rebase $(git remote) develop`.
- 변경은 **하나의 논리적 단위(atomic)** 로 나눠 `develop`에 커밋한다.
- 깨진 상태를 커밋하지 않는다.
- 현재 브랜치가 `master`면 **작업 전에** `develop`**으로 전환**하거나 사용자에게 확인한다.

## 승인 게이트는 push 와 PR 이다

커밋은 로컬이라 되돌릴 수 있으므로 **에이전트가 자유롭게 커밋한다**(규약은 `commit-strategy.md`). 사람의 승인은 **되돌리기 어려운 지점**에만 둔다.

| 지점 | 누가 | 무슨 일이 일어나나 |
| --- | --- | --- |
| `git commit` | **에이전트** — 승인 불필요 | 로컬 히스토리에만 남는다 |
| `git push` | **사람** — 에이전트 차단 | 원격 반영 → 테스트 환경 배포 |
| PR 생성·merge | **관리자** — 에이전트 차단 | 운영 배포 |
| 태그·Release | **관리자** — 에이전트 차단 | 버전 확정. GitHub에서만 만든다 |

- 태그는 **GitHub이 정본**이다. 로컬에서 만들지 않고 `git fetch <remote> --tags` 로 받아온다. 조회(`git tag -l`·`-n1`·`--sort`)는 허용되고, 생성·삭제(`git tag <이름>`·`-a`·`-d`·`-f`)는 hook이 거부한다.

## 지켜야 할 것

- **에이전트는** `git push`**를 실행하지 않는다.** push는 사람이 직접 한다(hook·settings 에서 deny).
- `--force`·`--no-verify` 금지. 되돌리기 어려운 조작(force push, 히스토리 재작성)은 사용자 확인 없이 하지 않는다.
- 커밋 전 시크릿·키·대용량 바이너리 스테이징 여부를 점검한다(→ `commit-strategy.md`).

## PR

- 통합은 `develop` **→** `master` **PR**. 비교 기준은 `$(git remote)/master..develop`.
- **PR 생성·merge는 사람이 GitHub 웹에서** 한다(보안 정책). 에이전트는 `gh pr create`·`merge`·`edit`·`review` 등 상태를 바꾸는 `gh pr` 명령과 `git push`를 실행하지 않으며, 초안이 필요하면 `/pr` 스킬로 **채팅 출력만** 한다.

## 관련

- 커밋 메시지 규약: `.claude/rules/commit-strategy.md`
- PR 초안 스킬: `.claude/skills/pr/SKILL.md`