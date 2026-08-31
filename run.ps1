#Requires -Version 5.1
<#
.SYNOPSIS
    notebooklm-st Streamlit 앱을 실행한다.

.DESCRIPTION
    프로젝트 루트로 이동해 uv 로 의존성을 동기화한 뒤 Streamlit 서버를
    띄운다. 바인딩 주소와 포트는 .streamlit/config.toml 이 정한다.

.PARAMETER NoSync
    uv sync 를 건너뛰고 바로 앱을 실행한다. 의존성이 이미 최신일 때 쓴다.

.PARAMETER StreamlitArgs
    나머지 인수는 streamlit run 에 그대로 전달된다.

.EXAMPLE
    .\run.ps1

.EXAMPLE
    .\run.ps1 -NoSync -- --server.port 8612
#>
[CmdletBinding()]
param(
    [switch]$NoSync,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$StreamlitArgs
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# uv 는 PATH 에 없을 수 있다. 기본 설치 경로를 대안으로 본다.
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    $fallback = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
    if (Test-Path $fallback) { $uv = $fallback }
}
if (-not $uv) {
    Write-Host 'uv 를 찾을 수 없습니다. https://docs.astral.sh/uv/ 를 보고 설치하세요.' -ForegroundColor Red
    exit 1
}

if (-not $NoSync) {
    Write-Host '==> 의존성 동기화 (uv sync)' -ForegroundColor Cyan
    & $uv sync
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# 주소·포트의 정본은 config.toml 이다. 안내 문구가 어긋나지 않게 읽어 쓴다.
$address = '127.0.0.1'
$port = '8501'
$configPath = Join-Path $root '.streamlit\config.toml'
if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw
    if ($config -match '(?m)^\s*address\s*=\s*"([^"]+)"') { $address = $Matches[1] }
    if ($config -match '(?m)^\s*port\s*=\s*(\d+)') { $port = $Matches[1] }
}

Write-Host "==> http://${address}:${port} (Ctrl+C 로 종료)" -ForegroundColor Cyan
& $uv run streamlit run src/notebooklm_st/app.py @StreamlitArgs
exit $LASTEXITCODE
