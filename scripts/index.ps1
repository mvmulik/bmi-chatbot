# Build or update the Chroma vector index from processed chunks
param(
    [ValidateSet("full", "incremental", "stats", "clear")]
    [string]$Mode = "incremental",
    [string]$ProcessDir = "",
    [switch]$VerboseLogging,
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$ProjectRoot = Get-ProjectRoot
$EnvFile = Join-Path $ProjectRoot ".env"
Import-DotEnv -EnvFile $EnvFile

$Python = Ensure-BackendVenv -ProjectRoot $ProjectRoot

if ($InstallDeps) {
    Write-Host "Installing indexer dependencies..."
    & $Python -m pip install -r (Join-Path $ProjectRoot "crawler\requirements.txt") | Out-Host
}

$argsList = @("-m", "crawler.indexer")
if ($VerboseLogging) {
    $argsList += "-v"
}
if ($ProcessDir) {
    $argsList += @("--process-dir", $ProcessDir)
}
$argsList += $Mode

Write-Host "Running indexer mode=$Mode ..."
Set-Location $ProjectRoot
& $Python @argsList
