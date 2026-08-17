# End-to-end local smoke checks against running services (no fake fixtures).
param(
    [string]$BackendUrl = "http://127.0.0.1:8000",
    [string]$FrontendUrl = "http://127.0.0.1:5173",
    [string]$Question = "What information is available on BMI Hub?"
)

$ErrorActionPreference = "Stop"

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw $Message
    }
}

Write-Host "1) Backend health..."
$health = Invoke-RestMethod -Uri "$BackendUrl/health" -Method Get
Assert-True ($health.status -eq "healthy") "Backend /health did not return healthy."
Write-Host "   OK: $($health | ConvertTo-Json -Compress)"

Write-Host "2) Frontend reachable..."
$frontend = Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing
Assert-True ($frontend.StatusCode -eq 200) "Frontend did not return HTTP 200."
Write-Host "   OK: HTTP $($frontend.StatusCode)"

Write-Host "3) Frontend -> backend /api/health (direct API base)..."
$apiHealth = Invoke-RestMethod -Uri "$BackendUrl/api/health" -Method Get
Assert-True ($apiHealth.status -eq "healthy") "Backend /api/health failed."
Write-Host "   OK: $($apiHealth | ConvertTo-Json -Compress)"

Write-Host "4) Chatbot query against Chroma + LLM..."
if (-not (Test-Path (Join-Path (Split-Path $PSScriptRoot -Parent) ".env"))) {
    throw "Missing project .env with Azure OpenAI settings. Copy .env.example to .env and configure credentials before chat verification."
}

$body = @{
    message = $Question
    conversationId = "integration-smoke"
} | ConvertTo-Json

try {
    $chat = Invoke-RestMethod -Uri "$BackendUrl/api/chat" -Method Post -ContentType "application/json" -Body $body
}
catch {
    $detail = $_.ErrorDetails.Message
    throw "Chat request failed. Ensure .env credentials are valid and the Chroma index is populated (crawl -> process -> index). Details: $detail"
}
Assert-True (-not [string]::IsNullOrWhiteSpace($chat.answer)) "Chat returned an empty answer."
Assert-True ($null -ne $chat.sources) "Chat response missing sources array."
Assert-True ($chat.sources.Count -gt 0) "Chat returned no sources. Index BMI Hub content first."
Assert-True (-not [string]::IsNullOrWhiteSpace($chat.sources[0].url)) "Source URL missing."
Assert-True (-not [string]::IsNullOrWhiteSpace($chat.sources[0].title)) "Source title missing."

Write-Host "   OK: answer chars=$($chat.answer.Length), sources=$($chat.sources.Count)"
Write-Host "   First source: $($chat.sources[0].title) | $($chat.sources[0].section) | $($chat.sources[0].url)"
Write-Host "Integration smoke checks passed."
