# 커밋 전략 (rule)

이 규칙은 세션마다 자동 로드되어 **메인 에이전트와 커스텀 서브에이전트 모두**에 적용된다.
`/commit` 스킬은 이 규칙을 실행하는 도구이며, 스킬을 쓰지 않고 커밋할 때도 이 규칙을 따른다.

## 메시지 형식 (gitmoji + Conventional Commits)
헤더: `<emoji> <type>(<scope>)<!>: <subject>`
- **type**: `feat` `fix` `docs` `style` `refactor` `perf` `test` `build` `ci` `chore` `revert`
- **scope**(선택): 영향 모듈 — 예 `✨ feat(auth): …`
- **subject**: **한국어**·명령형("추가" not "추가됨")·마침표 없음·**≤50자**
- **본문**(선택): 제목과 빈 줄로 분리, **무엇을·왜**(어떻게는 코드가 말하게), 72자 줄바꿈
- **파괴적 변경**: 헤더에 `!` 또는 푸터 `BREAKING CHANGE: <설명>`
- 메시지 끝에 항상 트레일러:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

### gitmoji 맵
| emoji | type | | emoji | type |
|---|---|---|---|---|
| ✨ | feat | | ✅ | test |
| 🐛 | fix | | 📦️ | build |
| 📝 | docs | | 👷 | ci |
| 💄 | style | | 🔧 | chore |
| ♻️ | refactor | | ⚡️ | perf |
| ⏪️ | revert | | 🔥 | remove |

## 원칙
- **한 커밋 = 하나의 논리적 변경(atomic).** 성격이 섞이면(기능+리팩터, 포매팅-only) 분리한다.
- 제목은 구체적으로("파일 수정" 같은 모호 제목 금지). 모르는 정보는 지어내지 않는다.

## 안전 가드레일 (커밋 전 필수)
- **시크릿·키·`.env`·대용량 바이너리**가 스테이징됐는지 점검 → 있으면 멈추고 경고.
- 스테이징된 게 없으면 임의로 전체 `add` 하지 말고 무엇을 커밋할지 확인한다.
- 기본 브랜치(`master`) 이슈는 `.claude/rules/branch-strategy.md`를 따른다.
- 사용자가 요청할 때만 커밋한다. 요청 없는 `push` 금지, `--no-verify`·force 금지.

## 관련
- 브랜치 전략: `.claude/rules/branch-strategy.md`
- 커밋 실행 스킬: `.claude/skills/commit/SKILL.md`
