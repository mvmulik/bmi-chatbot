# Shared helpers for BMI chatbot PowerShell scripts.
$ErrorActionPreference = "Stop"

function Get-ProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-PythonExe {
    param(
        [string]$ProjectRoot = (Get-ProjectRoot)
    )

    $candidates = @(
        (Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"),
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    throw "Python was not found. Create backend\.venv first (see README)."
}

function Ensure-BackendVenv {
    param([string]$ProjectRoot = (Get-ProjectRoot))

    $venvPython = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "Creating backend virtual environment..."
        Push-Location (Join-Path $ProjectRoot "backend")
        try {
            python -m venv .venv
        }
        finally {
            Pop-Location
        }
    }
    return $venvPython
}

function Import-DotEnv {
    param([string]$EnvFile)

    if (-not (Test-Path $EnvFile)) {
        return
    }

    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or ($line -notmatch "=")) {
            return
        }
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}
