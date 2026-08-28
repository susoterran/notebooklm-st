#!/usr/bin/env bash
# command-guard — 메인 세션 명령 실행 가드 (PreToolUse) — Linux/macOS (bash + jq)
# C2 이행: 위험=deny / 상태변경=ask / 조회성=allow. 기본 모드는 usable한 'guard'.
#   MODE="allowlist" 로 바꾸면 미승인 명령을 전부 deny(자동실행·고보안 세션 권장).
# ⚠️ 문자열 패턴이라 서브프로세스(python -c 등) 우회는 못 막음 → sandbox 병행(헌법 P3).
set -euo pipefail
MODE="guard"   # guard | allowlist

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')

decide() { jq -cn --arg d "$1" --arg r "$2" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:$d,permissionDecisionReason:$r}}'
  exit 0; }
allow() { decide allow "$1"; }
ask()   { decide ask   "$1"; }
deny()  { decide deny  "$1"; }

# 1) 위험 = 항상 거부
if printf '%s' "$cmd" | grep -Eq \
  '(^|[[:space:];&|(])(sudo|su|doas)[[:space:]]|(^|[[:space:];&|(])rm[[:space:]]|(^|[[:space:];&|(])dd[[:space:]]|mkfs|shred|(^|[[:space:];&|(])(curl|wget|scp|ssh|nc|ncat)[[:space:]]|(^|[[:space:];&|(])(chmod|chown)[[:space:]]|cd[[:space:]]+/|cd[[:space:]]+~|cd[[:space:]]+\.\.|pushd'; then
  deny "위험 명령 차단 (C2): $cmd"
fi

# 2) 상태변경 = 사람 확인
if printf '%s' "$cmd" | grep -Eq \
  'git[[:space:]]+(push|merge|commit|reset[[:space:]]+--hard|clean)|(npm|pnpm|yarn)[[:space:]]+(install|add|i)([[:space:]]|$)|pip[[:space:]]+install|(^|[[:space:]])npx[[:space:]]'; then
  ask "상태변경 명령 — 승인 필요 (C2): $cmd"
fi

# 3) 조회성 안전 = 허용
if printf '%s' "$cmd" | grep -Eq \
  'git[[:space:]]+(status|diff|log|show|branch|fetch|remote)|(^|[[:space:];&|(])(ls|pwd|echo|cat|head|tail|find|whoami)([[:space:]]|$)'; then
  allow "조회성 명령 허용 (C2): $cmd"
fi

# 4) 기본 정책
[ "$MODE" = "allowlist" ] && deny "allowlist 모드: 미승인 명령 차단 (C2): $cmd"
allow "guard 모드 기본 허용: $cmd"
