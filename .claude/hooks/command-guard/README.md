# command-guard

메인 세션 **명령 실행 가드**(PreToolUse hook). 헌법 **C2**(명령 실행) 이행.

| 파일 | 환경 | 비고 |
|---|---|---|
| `command-guard.ps1` | Windows | PowerShell, `jq` 불필요 |
| `command-guard.sh` | Linux / macOS | bash + `jq` |

## 동작
`Bash`·`PowerShell` 도구 호출 시 명령 문자열을 검사해 결정한다.
- **deny** — 권한상승(`sudo`/`su`), 파괴(`rm`/`Remove-Item`/`dd`/`shred`), 이그레스(`curl`/`wget`/`Invoke-WebRequest`/`scp`/`ssh`/`nc`), 권한변경(`chmod`/`chown`/`icacls`), 디렉터리 이탈(`cd /`·`cd ..`).
- **ask** — 상태변경(`git push`/`merge`/`commit`, 패키지 install, `npx`).
- **allow** — 조회성(`git status`/`diff`/`log`, `ls`/`cat`/`head` 등).

## 모드
- `guard`(기본) — 위 분류 외 명령은 **허용**(usable). settings·기본 프롬프트가 나머지를 보완.
- `allowlist` — 위 분류 외 명령을 **전부 deny**. 자동실행·고보안 세션(C7) 권장. 스크립트 상단 `$Mode`/`MODE` 변경.

## 등록 (settings.json)
`assets/settings/settings.secure.*.example.jsonc` 의 `hooks.PreToolUse` 블록 참고. 스크립트는 `<프로젝트>/.claude/hooks/command-guard/` 에 배치.

```jsonc
// Windows
{ "matcher": "Bash|PowerShell", "hooks": [{ "type": "command",
  "command": "powershell -NoProfile -ExecutionPolicy Bypass -File \"%CLAUDE_PROJECT_DIR%\\.claude\\hooks\\command-guard\\command-guard.ps1\"" }] }
// Linux/macOS
{ "matcher": "Bash", "hooks": [{ "type": "command",
  "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/command-guard/command-guard.sh" }] }
```

## 한계
문자열 패턴 검사라 **서브프로세스(`python -c`, `node -e`) 우회는 못 막는다**(헌법 P3). 진짜 격리는 Linux/WSL2 `sandbox`. 이 hook은 다층 방어의 한 계층이다.

## 전제
- Linux: `jq` 설치, `.sh` 실행권한(`chmod +x`).
- Windows: PowerShell(`-ExecutionPolicy Bypass` 호출).
