# Process crawled pages into cleaned RAG chunks
param(
    [string]$CrawlDir = "",
    [int]$ChunkSize = 1000,
    [int]$ChunkOverlap = 150,
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$ProjectRoot = Get-ProjectRoot
$EnvFile = Join-Path $ProjectRoot ".env"
Import-DotEnv -EnvFile $EnvFile

$Python = Ensure-BackendVenv -ProjectRoot $ProjectRoot

if ($InstallDeps) {
    Write-Host "Installing processor dependencies..."
    & $Python -m pip install -r (Join-Path $ProjectRoot "processor\requirements.txt") | Out-Host
}

$argsList = @(
    "-m", "processor",
    "--chunk-size", "$ChunkSize",
    "--chunk-overlap", "$ChunkOverlap"
)

if ($CrawlDir) {
    $argsList += @("--crawl-dir", $CrawlDir)
}

Write-Host "Processing content from data/raw ..."
Set-Location $ProjectRoot
& $Python @argsList
