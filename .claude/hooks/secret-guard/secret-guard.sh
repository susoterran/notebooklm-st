#!/usr/bin/env bash
# secret-guard — 시크릿 경로 접근 가드 (PreToolUse) — Linux/macOS (bash + jq)
# C4 이행: Read/Glob/Grep 대상이 시크릿 파일·자격증명 경로면 deny, 그 외 allow.
#   settings.deny 를 보완(커스텀 패턴·로깅). ⚠️ 임의 하위 프로세스는 못 막음 → sandbox 병행.
set -euo pipefail

input=$(cat)
target=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // .tool_input.pattern // empty')

decide() { jq -cn --arg d "$1" --arg r "$2" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:$d,permissionDecisionReason:$r}}'
  exit 0; }

n=$(printf '%s' "$target" | tr '\\' '/')
if printf '%s' "$n" | grep -Eq \
  '(^|/)\.env|\.pem$|\.key$|\.pfx$|id_rsa|(^|/)credentials$|/\.ssh/|/\.aws/|/\.gnupg/|/\.kube/|/\.azure/|secrets?\.(ya?ml|json)$|\.p12$'; then
  decide deny "시크릿 경로 접근 차단 (C4): ${target:-?}"
fi
decide allow "허용: ${target:-?}"
