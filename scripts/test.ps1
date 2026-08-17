# Run project test suites
param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$ProjectRoot = Get-ProjectRoot
$Python = Ensure-BackendVenv -ProjectRoot $ProjectRoot

Write-Host "Ensuring Python test dependencies..."
& $Python -m pip install -r (Join-Path $ProjectRoot "backend\requirements.txt") | Out-Host
& $Python -m pip install -r (Join-Path $ProjectRoot "crawler\requirements.txt") | Out-Host
& $Python -m pip install -r (Join-Path $ProjectRoot "processor\requirements.txt") | Out-Host

$pytestArgs = @("-m", "pytest")
if ($Quiet) {
    $pytestArgs += "-q"
}
else {
    $pytestArgs += "-v"
}

Write-Host "Running pytest from $ProjectRoot ..."
Set-Location $ProjectRoot
& $Python @pytestArgs
$pythonExit = $LASTEXITCODE

Write-Host "Running frontend production build (typecheck)..."
Set-Location (Join-Path $ProjectRoot "frontend")
if (-not (Test-Path "node_modules")) {
    npm install | Out-Host
}
npm run build
$frontendExit = $LASTEXITCODE

if ($pythonExit -ne 0 -or $frontendExit -ne 0) {
    throw "Tests failed (pytest exit=$pythonExit, frontend build exit=$frontendExit)."
}

Write-Host "All tests passed."
