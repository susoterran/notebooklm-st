# secret-guard — 시크릿 경로 접근 가드 (PreToolUse) — Windows (PowerShell, jq 불필요)
# C4 이행: Read/Glob/Grep 대상이 시크릿 파일·자격증명 경로면 deny, 그 외 allow.
#   settings.deny 를 보완(커스텀 패턴·로깅). ⚠️ 임의 하위 프로세스는 못 막음 → sandbox 병행.
$ErrorActionPreference = 'Stop'

$raw = [Console]::In.ReadToEnd()
try { $in = $raw | ConvertFrom-Json } catch { $in = $null }
$target = $in.tool_input.file_path
if (-not $target) { $target = $in.tool_input.path }
if (-not $target) { $target = $in.tool_input.pattern }
if (-not $target) { $target = '' }

function Respond($d, $r) {
  @{ hookSpecificOutput = @{ hookEventName = 'PreToolUse'; permissionDecision = $d; permissionDecisionReason = $r } } |
    ConvertTo-Json -Compress -Depth 5
  exit 0
}

$n = $target -replace '\\', '/'
$secretPatterns = @(
  '(^|/)\.env', '\.pem$', '\.key$', '\.pfx$', 'id_rsa', '(^|/)credentials$',
  '/\.ssh/', '/\.aws/', '/\.gnupg/', '/\.kube/', '/\.azure/',
  'secrets?\.(ya?ml|json)$', '\.p12$'
)
foreach ($p in $secretPatterns) {
  if ($n -match $p) { Respond 'deny' "시크릿 경로 접근 차단 (C4): $target" }
}
Respond 'allow' "허용: $target"
