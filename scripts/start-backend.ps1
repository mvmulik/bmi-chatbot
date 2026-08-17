# Start the FastAPI backend on http://localhost:8000
param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$NoReload,
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$ProjectRoot = Get-ProjectRoot
$BackendDir = Join-Path $ProjectRoot "backend"
$EnvFile = Join-Path $ProjectRoot ".env"

if (-not (Test-Path $EnvFile)) {
    Write-Warning "No .env found at $EnvFile. Copy .env.example to .env and configure Azure OpenAI settings."
}

Import-DotEnv -EnvFile $EnvFile
$Python = Ensure-BackendVenv -ProjectRoot $ProjectRoot

if ($InstallDeps) {
    Write-Host "Installing/updating backend dependencies..."
    & $Python -m pip install -r (Join-Path $BackendDir "requirements.txt") | Out-Host
}

$reloadArgs = @()
if (-not $NoReload) {
    $reloadArgs += "--reload"
}

Write-Host "Starting backend at http://localhost:$Port ..."
Set-Location $BackendDir
& $Python -m uvicorn app.main:app @reloadArgs --host $HostAddress --port $Port
