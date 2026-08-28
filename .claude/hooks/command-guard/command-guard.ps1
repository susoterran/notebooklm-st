# command-guard — 메인 세션 명령 실행 가드 (PreToolUse) — Windows (PowerShell, jq 불필요)
# C2 이행: 위험=deny / 상태변경=ask / 조회성=allow. 기본 모드는 usable한 'guard'.
#   $Mode='allowlist' 로 바꾸면 미승인 명령을 전부 deny(자동실행·고보안 세션 권장).
# ⚠️ 문자열 패턴이라 서브프로세스(python -c 등) 우회는 못 막음 → Linux sandbox 병행(헌법 P3).
$ErrorActionPreference = 'Stop'
$Mode = 'guard'   # 'guard' | 'allowlist'

$raw = [Console]::In.ReadToEnd()
try { $in = $raw | ConvertFrom-Json } catch { $in = $null }
$cmd = $in.tool_input.command
if (-not $cmd) { $cmd = '' }

function Respond($d, $r) {
  @{ hookSpecificOutput = @{ hookEventName = 'PreToolUse'; permissionDecision = $d; permissionDecisionReason = $r } } |
    ConvertTo-Json -Compress -Depth 5
  exit 0
}
function Allow($r) { Respond 'allow' $r }
function Ask($r)   { Respond 'ask'   $r }
function Deny($r)  { Respond 'deny'  $r }

# 1) 위험 = 항상 거부 (권한상승·파괴·이그레스·디렉터리 이탈·권한변경)
$denyPatterns = @(
  '(^|[\s;&|(])sudo\s', '(^|[\s;&|(])su\s', '(^|[\s;&|(])doas\s',
  '(^|[\s;&|(])rm\s', 'Remove-Item', 'Format-Volume', 'Clear-Disk', '(^|[\s;&|(])dd\s', 'mkfs', 'shred',
  '(^|[\s;&|(])curl(\.exe)?\s', '(^|[\s;&|(])wget\s', 'Invoke-WebRequest', 'Invoke-RestMethod', 'Start-BitsTransfer',
  '(^|[\s;&|(])scp\s', '(^|[\s;&|(])ssh\s', '(^|[\s;&|(])nc\s', 'ncat',
  '(^|[\s;&|(])chmod\s', '(^|[\s;&|(])chown\s', '(^|[\s;&|(])icacls\s',
  'cd\s+/', 'cd\s+~', 'cd\s+\.\.', 'pushd'
)
foreach ($p in $denyPatterns) { if ($cmd -match $p) { Deny "위험 명령 차단 (C2): $cmd" } }

# 2) 상태변경 = 사람 확인
$askPatterns = @(
  'git\s+push', 'git\s+merge', 'git\s+commit', 'git\s+reset\s+--hard', 'git\s+clean',
  '(npm|pnpm|yarn)\s+(install|add|i)\b', 'pip\s+install', '(^|[\s;&|(])npx\s'
)
foreach ($p in $askPatterns) { if ($cmd -match $p) { Ask "상태변경 명령 — 승인 필요 (C2): $cmd" } }

# 3) 조회성 안전 = 허용
$safePatterns = @(
  'git\s+(status|diff|log|show|branch|fetch|remote)\b',
  '(^|[\s;&|(])(ls|dir|pwd|echo|cat|type|head|tail|find|where|whoami)\b',
  'Get-(ChildItem|Content|Location)', 'Select-String'
)
foreach ($p in $safePatterns) { if ($cmd -match $p) { Allow "조회성 명령 허용 (C2): $cmd" } }

# 4) 기본 정책
if ($Mode -eq 'allowlist') { Deny "allowlist 모드: 미승인 명령 차단 (C2): $cmd" }
Allow "guard 모드 기본 허용: $cmd"
