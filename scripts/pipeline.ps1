# Crawl BMI Hub, process pages, and update the vector index.
param(
    [ValidateSet("full", "incremental")]
    [string]$Mode = "incremental",
    [int]$MaxPages = 50,
    [int]$MaxDepth = 8,
    [switch]$Reauth,
    [switch]$Headed,
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$ProjectRoot = Get-ProjectRoot
Set-Location $ProjectRoot

$crawlArgs = @{
    Mode = $Mode
    MaxPages = $MaxPages
    MaxDepth = $MaxDepth
}
if ($Reauth) { $crawlArgs.Reauth = $true }
if ($Headed) { $crawlArgs.Headed = $true }
if ($InstallDeps) { $crawlArgs.InstallDeps = $true }

Write-Host "=== 1/3 Crawl ($Mode) ==="
& (Join-Path $PSScriptRoot "crawl.ps1") @crawlArgs

Write-Host "=== 2/3 Process ==="
& (Join-Path $PSScriptRoot "process.ps1")

$indexMode = if ($Mode -eq "full") { "full" } else { "incremental" }
Write-Host "=== 3/3 Index ($indexMode) ==="
& (Join-Path $PSScriptRoot "index.ps1") -Mode $indexMode
