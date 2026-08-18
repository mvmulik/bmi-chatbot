# Crawl BMI Hub (interactive login on first run / --reauth)
param(
    [int]$MaxPages = 50,
    [int]$MaxDepth = 8,
    [ValidateSet("full", "incremental")]
    [string]$Mode = "incremental",
    [switch]$Reauth,
    [switch]$Headed,
    [string]$StartUrl = "",
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$ProjectRoot = Get-ProjectRoot
$EnvFile = Join-Path $ProjectRoot ".env"
Import-DotEnv -EnvFile $EnvFile

$Python = Ensure-BackendVenv -ProjectRoot $ProjectRoot

if ($InstallDeps) {
    Write-Host "Installing crawler dependencies..."
    & $Python -m pip install -r (Join-Path $ProjectRoot "crawler\requirements.txt") | Out-Host
    & $Python -m playwright install chromium | Out-Host
}

$argsList = @(
    "-m", "crawler",
    "--mode", $Mode,
    "--max-pages", "$MaxPages",
    "--max-depth", "$MaxDepth"
)

if ($Reauth) { $argsList += "--reauth" }
if ($Headed) { $argsList += "--headed" }
if ($StartUrl) {
    $argsList += @("--start-url", $StartUrl)
}

Write-Host "Running crawler from $ProjectRoot ..."
Set-Location $ProjectRoot
& $Python @argsList
