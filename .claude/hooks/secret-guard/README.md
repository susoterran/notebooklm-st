# secret-guard

시크릿 **파일 접근 가드**(PreToolUse hook). 헌법 **C4**(시크릿·민감정보) 이행.

| 파일 | 환경 | 비고 |
|---|---|---|
| `secret-guard.ps1` | Windows | PowerShell, `jq` 불필요 |
| `secret-guard.sh` | Linux / macOS | bash + `jq` |

## 동작
`Read`·`Glob`·`Grep` 대상 경로가 시크릿 패턴이면 **deny**, 그 외 **allow**.
- 차단 패턴: `.env*`, `*.pem`/`*.key`/`*.pfx`/`*.p12`, `id_rsa`, `credentials`, `secrets.{yml,json}`, `~/.ssh`·`~/.aws`·`~/.gnupg`·`~/.kube`·`~/.azure`.

`settings.deny` 와 **이중**으로 건다: settings 는 Claude Code 내장 파일 도구를, 이 hook 은 커스텀 패턴·로깅을 담당.

## 등록 (settings.json)
`assets/settings/settings.secure.*.example.jsonc` 의 `hooks.PreToolUse`(matcher `Read|Glob|Grep`) 참고. 스크립트는 `<프로젝트>/.claude/hooks/secret-guard/` 에 배치.

## 한계
`settings`·hook 모두 Claude Code가 인식하는 도구에만 적용된다. 임의 하위 프로세스(`python -c "open('secret')"`)는 **Linux/WSL2 `sandbox.filesystem.denyRead`** 로만 막힌다(헌법 P3).

## 관련
- 커밋 시점 시크릿 차단: [`../../secret-scan/README.md`](../../secret-scan/README.md) (gitleaks)
