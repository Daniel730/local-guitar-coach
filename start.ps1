# Riff — start everything: Ollama, the web app, the browser.
# Usage: double-click start.bat, or: powershell -ExecutionPolicy Bypass -File start.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$port = if ($env:PORT) { [int]$env:PORT } else { 8000 }
while (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { $port++ }

function Test-Ollama {
    try { Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 2 | Out-Null; return $true }
    catch { return $false }
}

if (-not (Test-Ollama)) {
    Write-Host "Iniciando Ollama..."
    Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
    for ($i = 0; $i -lt 20 -and -not (Test-Ollama); $i++) { Start-Sleep -Milliseconds 500 }
}

if (-not $env:RIFF_OLLAMA_MODEL) {
    $models = @()
    if (Test-Ollama) { $models = (Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags").models.name }
    $pick = @("llama3.1:8b", "gpt-oss:20b") | Where-Object { $models -contains $_ } | Select-Object -First 1
    if (-not $pick) { $pick = $models | Select-Object -First 1 }
    if ($pick) { $env:RIFF_OLLAMA_MODEL = $pick }
    else { Write-Warning "Ollama sem modelos: o professor vai usar o fallback. Rode: ollama pull llama3.1:8b" }
}
if ($env:RIFF_OLLAMA_MODEL -like "gpt-oss*" -and -not $env:RIFF_OLLAMA_THINK) { $env:RIFF_OLLAMA_THINK = "low" }
Write-Host "Professor: $($env:RIFF_OLLAMA_MODEL)  |  App: http://localhost:$port"

Start-Job -ScriptBlock { param($p) Start-Sleep 3; Start-Process "http://localhost:$p" } -ArgumentList $port | Out-Null
& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port $port
