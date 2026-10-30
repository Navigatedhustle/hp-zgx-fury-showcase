<#
  HP Deck Builder launcher (Windows).
    .\run.ps1            first run installs everything, then starts the app at http://127.0.0.1:8765
    .\run.ps1 -Dev       backend with auto-reload + Vite dev server at http://localhost:5173
    .\run.ps1 -Mock      offline mode (no GB300): template slides for demos and UI work
    .\run.ps1 -Setup     install / update dependencies only
#>
param([switch]$Dev, [switch]$Mock, [switch]$Setup)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

function Install-Deps {
  # One setup, in start.py (.env, venv, packages, Chromium, UI); this launcher only calls it.
  python (Join-Path $root "start.py") --setup
  if ($LASTEXITCODE -ne 0) { throw "Setup failed (see the output above)." }
}

if ($Setup -or -not (Test-Path $py) -or -not (Test-Path (Join-Path $root "frontend\dist\index.html"))) { Install-Deps }
if ($Setup) { exit 0 }
if ($Mock) { $env:LLM_MOCK = "true" }

$port = if ($env:PORT) { $env:PORT } else { "8765" }
Push-Location (Join-Path $root "backend")
try {
  if ($Dev) {
    Start-Process -NoNewWindow -FilePath "npm" -ArgumentList "run", "dev" -WorkingDirectory (Join-Path $root "frontend")
    Write-Host "UI: http://localhost:5173  (API on $port)" -ForegroundColor Green
    & $py -m uvicorn app.main:app --host 127.0.0.1 --port $port --reload
  } else {
    Write-Host "HP Deck Builder: http://127.0.0.1:$port" -ForegroundColor Green
    Start-Process "http://127.0.0.1:$port"
    & $py -m uvicorn app.main:app --host 127.0.0.1 --port $port
  }
} finally { Pop-Location }
