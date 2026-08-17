# Start the Vite React frontend on http://localhost:5173
param(
    [int]$Port = 5173
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$ProjectRoot = Get-ProjectRoot
$FrontendDir = Join-Path $ProjectRoot "frontend"
$EnvExample = Join-Path $FrontendDir ".env.example"
$EnvFile = Join-Path $FrontendDir ".env"

if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Host "Created frontend/.env from .env.example"
    }
    else {
        throw "Missing frontend/.env and frontend/.env.example"
    }
}

Set-Location $FrontendDir

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "Installing frontend dependencies..."
    npm install | Out-Host
}

Write-Host "Starting frontend at http://localhost:$Port ..."
Write-Host "VITE_API_BASE_URL should point at the backend (default http://localhost:8000)."
npm run dev -- --host 127.0.0.1 --port $Port
